"""End-to-end daily forecasting pipeline."""

import argparse
import logging
import sys
from pathlib import Path

from forecasting.backtest.rolling_origin import run_baseline_backtest
from forecasting.features.build_datasets import build_inference_features_2026, build_train_datasets
from forecasting.features.event_uplift import compute_event_uplift_priors, generate_uplift_report
from forecasting.features.events_daily import build_events_daily_2026, build_events_daily_history
from forecasting.io.events_ingest import ingest_events_2026_exact, ingest_recurring_event_mapping
from forecasting.io.hours_calendar import build_hours_calendar_2026, build_hours_calendar_history

# Import all pipeline components
from forecasting.io.sales_ingest import ingest_sales
from forecasting.models.chronos2 import run_chronos2_backtest
from forecasting.models.ensemble import EnsembleModel
from forecasting.models.gbm_long import run_gbm_long_backtest
from forecasting.models.gbm_short import run_gbm_short_backtest
from forecasting.pipeline.export import generate_2026_forecast

logger = logging.getLogger(__name__)


def run_pipeline(
    config_path: str = "configs/config.yaml",
    issue_date: str = None,
    run_backtests: bool = False,
    skip_chronos: bool = False,
    dry_run: bool = False,
):
    """
    Run the full forecasting pipeline.

    Parameters
    ----------
    config_path : str
        Path to configuration file
    issue_date : str
        Issue date for forecast (YYYY-MM-DD). If None, uses last date in history.
    run_backtests : bool
        Whether to run backtests
    skip_chronos : bool
        Whether to skip Chronos-2 integration
    dry_run : bool
        If True, runs data prep only without training/forecasting
    """
    from forecasting.utils.runtime import file_sha256, load_yaml, resolve_config_path

    logger.info("=" * 80)
    logger.info("DAILY SALES FORECASTING PIPELINE")
    logger.info("=" * 80)

    # Load configuration with hash
    logger.info("\nResolving config path...")
    resolved_config_path = resolve_config_path(config_path)
    logger.info(f"Loading config from: {resolved_config_path}")
    config = load_yaml(resolved_config_path)
    config_hash = file_sha256(resolved_config_path)
    logger.info(f"Config hash: {config_hash[:8]}...")

    # Get forecast window and slug
    from forecasting.utils.runtime import (
        forecast_slug,
        forecast_year_from_config,
        resolve_year_path,
        get_forecast_window,
    )

    forecast_start, forecast_end = get_forecast_window(config)
    slug = forecast_slug(forecast_start, forecast_end)
    forecast_year = forecast_year_from_config(config)
    logger.info(
        f"Forecast period: {forecast_start} to {forecast_end} (year: {forecast_year}, slug: {slug})"
    )

    # Resolve year-based raw input paths from templates (with fallback)
    events_exact_path = resolve_year_path(
        config,
        template_key="raw_events_exact_template",
        fallback_key="raw_events_2026_exact",
        year=forecast_year,
        required=True,
    )
    hours_calendar_path = resolve_year_path(
        config,
        template_key="raw_hours_calendar_template",
        fallback_key="raw_hours_calendar_2026",
        year=forecast_year,
        required=True,
    )
    hours_overrides_path = resolve_year_path(
        config,
        template_key="raw_hours_overrides_template",
        fallback_key="raw_hours_overrides_2026",
        year=forecast_year,
        required=True,
    )
    recurring_mapping_path = resolve_year_path(
        config,
        template_key="raw_recurring_mapping_template",
        fallback_key="raw_recurring_events",
        year=forecast_year,
        required=True,
    )

    logger.info(f"Raw events path: {events_exact_path}")
    logger.info(f"Raw hours calendar path: {hours_calendar_path}")
    logger.info(f"Raw hours overrides path: {hours_overrides_path}")
    logger.info(f"Raw recurring mapping path: {recurring_mapping_path}")

    try:
        # Step 1: Ingest sales
        logger.info("\n[1/9] Ingesting sales data...")
        ingest_sales()

        # Step 2: Build hours calendars
        logger.info("\n[2/9] Building hours calendars...")
        build_hours_calendar_2026(
            calendar_path=str(hours_calendar_path),
            overrides_path=str(hours_overrides_path),
        )
        build_hours_calendar_history()

        # Step 3: Ingest events
        logger.info("\n[3/9] Ingesting and normalizing events...")
        ingest_events_2026_exact(input_path=str(events_exact_path))
        ingest_recurring_event_mapping(input_path=str(recurring_mapping_path))

        # Step 4: Build event features
        logger.info("\n[4/9] Building event daily features...")
        build_events_daily_history()
        build_events_daily_2026(config)

        # Step 5: Compute uplift priors
        logger.info("\n[5/9] Computing event uplift priors...")
        import pandas as pd

        df_sales = pd.read_parquet("data/processed/fact_sales_daily.parquet")
        ds_max = df_sales["ds"].max().strftime("%Y-%m-%d")
        df_uplift = compute_event_uplift_priors(ds_max=ds_max)
        df_uplift.to_parquet("data/processed/event_uplift_priors.parquet", index=False)
        generate_uplift_report(df_uplift)

        # Step 6: Build datasets
        logger.info("\n[6/9] Building supervised datasets and inference features...")
        build_train_datasets(config=config)
        build_inference_features_2026(config)

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
            "seasonal_naive_weekly": "outputs/backtests/preds_baselines.parquet",
            "weekday_rolling_median": "outputs/backtests/preds_baselines.parquet",
            "gbm_short": "outputs/backtests/preds_gbm_short.parquet",
            "gbm_long": "outputs/backtests/preds_gbm_long.parquet",
        }

        # Check if backtest predictions exist
        available_preds = {k: v for k, v in backtest_preds_paths.items() if Path(v).exists()}

        if len(available_preds) == 0:
            logger.error("  ✗ No backtest predictions available. Cannot fit ensemble.")
            logger.error("  Run with --run-backtests first to generate predictions.")
            sys.exit(1)

        ensemble = EnsembleModel()
        ensemble.fit(available_preds)
        ensemble.save("outputs/models/ensemble_weights.csv")

        # Step 9: Generate forecast
        logger.info(f"\n[9/9] Generating forecast for {forecast_start} to {forecast_end}...")
        df_forecast = generate_2026_forecast(
            config=config, config_path=str(resolved_config_path), config_hash=config_hash
        )

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

        # Run log is written by generate_forecast() in export.py
        # (both slugged run_log_{slug}.json and stable run_log.json pointer)
        logger.info(f"  ✓ Run log written by export.py: outputs/reports/run_log_{slug}.json")

        # Optional: compute ensemble backtest metrics (requires backtests outputs)
        if run_backtests:
            try:
                import numpy as np
                import pandas as pd

                from forecasting.backtest.rolling_origin import (
                    assign_horizon_bucket,
                    compute_metrics,
                )

                # Load learned weights
                df_w = pd.read_csv("outputs/models/ensemble_weights.csv")
                weights_by_bucket = {
                    b: dict(zip(g["model_name"], g["weight"]))
                    for b, g in df_w.groupby("horizon_bucket")
                }

                # Load backtest predictions (filtering baseline file by model_name)
                backtest_preds_paths = {
                    "seasonal_naive_weekly": "outputs/backtests/preds_baselines.parquet",
                    "weekday_rolling_median": "outputs/backtests/preds_baselines.parquet",
                    "gbm_short": "outputs/backtests/preds_gbm_short.parquet",
                    "gbm_long": "outputs/backtests/preds_gbm_long.parquet",
                }

                frames = []
                for model_name, path in backtest_preds_paths.items():
                    if not Path(path).exists():
                        continue
                    df = pd.read_parquet(path)
                    if len(df) == 0:
                        continue
                    if "model_name" in df.columns:
                        df = df[df["model_name"] == model_name].copy()
                        if len(df) == 0:
                            continue
                    else:
                        df = df.copy()
                        df["model_name"] = model_name
                    frames.append(df)

                df_all = pd.concat(frames, ignore_index=True)
                if "horizon_bucket" not in df_all.columns:
                    df_all["horizon_bucket"] = df_all["horizon"].apply(assign_horizon_bucket)

                # Blend p50 per (cutoff_date, target_date) within each bucket
                ens_rows = []
                for bucket, df_b in df_all.groupby("horizon_bucket"):
                    w = weights_by_bucket.get(bucket, {})
                    df_p = df_b.pivot_table(
                        index=["cutoff_date", "target_date", "horizon", "y"],
                        columns="model_name",
                        values="p50",
                        aggfunc="first",
                    )

                    for (cutoff_date, target_date, horizon, y), row in df_p.iterrows():
                        avail = row.dropna()
                        if len(avail) == 0:
                            continue
                        raw_w = np.array([w.get(m, 0.0) for m in avail.index], dtype=float)
                        if raw_w.sum() <= 0:
                            norm_w = np.ones(len(avail), dtype=float) / len(avail)
                        else:
                            norm_w = raw_w / raw_w.sum()
                        p50 = float((avail.values * norm_w).sum())
                        ens_rows.append(
                            {
                                "cutoff_date": cutoff_date,
                                "target_date": target_date,
                                "horizon": int(horizon),
                                "y": float(y),
                                "p50": p50,
                                "horizon_bucket": bucket,
                                "model_name": "ensemble",
                            }
                        )

                df_ens = pd.DataFrame(ens_rows)
                df_metrics = compute_metrics(df_ens)
                df_metrics["model_name"] = "ensemble"

                Path("outputs/backtests").mkdir(parents=True, exist_ok=True)
                df_metrics.to_csv("outputs/backtests/metrics_ensemble.csv", index=False)
                logger.info("  ✓ Wrote outputs/backtests/metrics_ensemble.csv")
            except Exception as e:
                logger.warning(f"Could not compute metrics_ensemble.csv: {e}")

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
        "--issue-date",
        type=str,
        default=None,
        help="Issue date for forecast (YYYY-MM-DD). Defaults to last date in history.",
    )

    parser.add_argument(
        "--run-backtests", action="store_true", help="Run backtests (computationally expensive)"
    )

    parser.add_argument(
        "--skip-chronos",
        action="store_true",
        help="Skip Chronos-2 integration (default: False, Chronos enabled)",
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Run data prep only without training/forecasting"
    )

    parser.add_argument(
        "--config", type=str, default="configs/config.yaml", help="Path to config file"
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run pipeline
    run_pipeline(
        config_path=args.config,
        issue_date=args.issue_date,
        run_backtests=args.run_backtests,
        skip_chronos=args.skip_chronos,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
