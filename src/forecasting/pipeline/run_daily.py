"""End-to-end daily forecasting pipeline."""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime

# Import all pipeline components
from forecasting.io.sales_ingest import ingest_sales
from forecasting.io.hours_calendar import build_hours_calendar_2026, build_hours_calendar_history
from forecasting.io.events_ingest import ingest_events_2026_exact, ingest_recurring_event_mapping
from forecasting.features.events_daily import build_events_daily_history, build_events_daily_2026
from forecasting.features.event_uplift import compute_event_uplift_priors, generate_uplift_report
from forecasting.features.build_datasets import build_train_datasets, build_inference_features_2026
from forecasting.backtest.rolling_origin import run_baseline_backtest
from forecasting.models.gbm_short import run_gbm_short_backtest
from forecasting.models.gbm_long import run_gbm_long_backtest
from forecasting.models.chronos2 import run_chronos2_backtest
from forecasting.models.ensemble import EnsembleModel
from forecasting.pipeline.export import generate_2026_forecast

logger = logging.getLogger(__name__)


def run_pipeline(
    issue_date: str = None,
    run_backtests: bool = False,
    skip_chronos: bool = True,
    dry_run: bool = False,
):
    """
    Run the full forecasting pipeline.
    
    Parameters
    ----------
    issue_date : str
        Issue date for forecast (YYYY-MM-DD). If None, uses last date in history.
    run_backtests : bool
        Whether to run backtests
    skip_chronos : bool
        Whether to skip Chronos-2 integration
    dry_run : bool
        If True, runs data prep only without training/forecasting
    """
    logger.info("=" * 80)
    logger.info("DAILY SALES FORECASTING PIPELINE")
    logger.info("=" * 80)
    
    try:
        # Step 1: Ingest sales
        logger.info("\n[1/9] Ingesting sales data...")
        ingest_sales()
        
        # Step 2: Build hours calendars
        logger.info("\n[2/9] Building hours calendars...")
        build_hours_calendar_2026()
        build_hours_calendar_history()
        
        # Step 3: Ingest events
        logger.info("\n[3/9] Ingesting and normalizing events...")
        ingest_events_2026_exact()
        ingest_recurring_event_mapping()
        
        # Step 4: Build event features
        logger.info("\n[4/9] Building event daily features...")
        build_events_daily_history()
        build_events_daily_2026()
        
        # Step 5: Compute uplift priors
        logger.info("\n[5/9] Computing event uplift priors...")
        import pandas as pd
        df_sales = pd.read_parquet("data/processed/fact_sales_daily.parquet")
        ds_max = df_sales['ds'].max().strftime('%Y-%m-%d')
        df_uplift = compute_event_uplift_priors(ds_max=ds_max)
        df_uplift.to_parquet("data/processed/event_uplift_priors.parquet", index=False)
        generate_uplift_report(df_uplift)
        
        # Step 6: Build datasets
        logger.info("\n[6/9] Building supervised datasets and inference features...")
        build_train_datasets()
        build_inference_features_2026()
        
        if dry_run:
            logger.info("\n✓ DRY RUN COMPLETE - Data preparation successful")
            logger.info("To generate forecasts, run without --dry-run flag")
            return
        
        # Step 7: Run backtests (optional)
        if run_backtests:
            logger.info("\n[7/9] Running backtests...")
            
            logger.info("  - Running baseline backtest...")
            run_baseline_backtest()
            
            logger.info("  - Running GBM short backtest...")
            run_gbm_short_backtest()
            
            logger.info("  - Running GBM long backtest...")
            run_gbm_long_backtest()
            
            if not skip_chronos:
                logger.info("  - Running Chronos-2 backtest...")
                run_chronos2_backtest()
        else:
            logger.info("\n[7/9] Skipping backtests (use --run-backtests to enable)")
            
            # Check if backtest outputs exist
            backtest_files = [
                "outputs/backtests/preds_baselines.parquet",
                "outputs/backtests/preds_gbm_short.parquet",
                "outputs/backtests/preds_gbm_long.parquet",
            ]
            
            missing_backtests = [f for f in backtest_files if not Path(f).exists()]
            
            if missing_backtests:
                logger.warning("  ⚠ Backtest files missing. Ensemble weights may be unavailable.")
                logger.warning("  Run with --run-backtests to generate backtest outputs.")
        
        # Step 8: Fit ensemble
        logger.info("\n[8/9] Fitting ensemble model...")
        
        backtest_preds_paths = {
            'seasonal_naive_weekly': 'outputs/backtests/preds_baselines.parquet',
            'weekday_rolling_median': 'outputs/backtests/preds_baselines.parquet',
            'gbm_short': 'outputs/backtests/preds_gbm_short.parquet',
            'gbm_long': 'outputs/backtests/preds_gbm_long.parquet',
        }
        
        # Check if backtest predictions exist
        available_preds = {k: v for k, v in backtest_preds_paths.items() if Path(v).exists()}
        
        if len(available_preds) == 0:
            logger.error("  ✗ No backtest predictions available. Cannot fit ensemble.")
            logger.error("  Run with --run-backtests first to generate predictions.")
            sys.exit(1)
        
        ensemble = EnsembleModel()
        ensemble.fit(available_preds)
        ensemble.save('outputs/models/ensemble_weights.csv')
        
        # Step 9: Generate 2026 forecast
        logger.info("\n[9/9] Generating 2026 forecast...")
        df_forecast = generate_2026_forecast()
        
        logger.info("\n" + "=" * 80)
        logger.info("✓ PIPELINE COMPLETE")
        logger.info("=" * 80)
        logger.info(f"\nForecast generated: {len(df_forecast)} days")
        logger.info(f"Total p50: ${df_forecast['p50'].sum():,.2f}")
        logger.info(f"Closed days: {df_forecast['is_closed'].sum()}")
        logger.info("\nOutputs:")
        logger.info("  - outputs/forecasts/forecast_daily_2026.csv")
        logger.info("  - outputs/forecasts/rollups_ordering.csv")
        logger.info("  - outputs/forecasts/rollups_scheduling.csv")
        
    except Exception as e:
        logger.error(f"\n✗ PIPELINE FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Daily sales forecasting pipeline for Las Vegas restaurant"
    )
    
    parser.add_argument(
        '--issue-date',
        type=str,
        default=None,
        help='Issue date for forecast (YYYY-MM-DD). Defaults to last date in history.'
    )
    
    parser.add_argument(
        '--run-backtests',
        action='store_true',
        help='Run backtests (computationally expensive)'
    )
    
    parser.add_argument(
        '--skip-chronos',
        action='store_true',
        default=True,
        help='Skip Chronos-2 integration (default: True)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run data prep only without training/forecasting'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default='configs/config.yaml',
        help='Path to config file'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run pipeline
    run_pipeline(
        issue_date=args.issue_date,
        run_backtests=args.run_backtests,
        skip_chronos=args.skip_chronos,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
