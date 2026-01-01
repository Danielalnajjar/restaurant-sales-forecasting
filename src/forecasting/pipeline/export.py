"""Export 2026 forecasts with guardrails and rollups."""

import pandas as pd
import numpy as np
import logging
from pathlib import Path
from datetime import datetime

from forecasting.models.gbm_short import GBMShortHorizon
from forecasting.models.gbm_long import GBMLongHorizon
from forecasting.models.chronos2 import Chronos2Model
from forecasting.models.baselines import SeasonalNaiveWeekly, WeekdayRollingMedian
from forecasting.models.ensemble import EnsembleModel
from forecasting.features.feature_builders import build_features_short, build_features_long
from forecasting.features.oof_spike_overlay import compute_oof_spike_multipliers, apply_spike_overlay, generate_oof_overlay_report

logger = logging.getLogger(__name__)


def apply_guardrails(df: pd.DataFrame, df_hours: pd.DataFrame) -> pd.DataFrame:
    """
    Apply guardrails to forecasts.
    
    Parameters
    ----------
    df : pd.DataFrame
        Forecasts with target_date (or ds), p50, p80, p90
    df_hours : pd.DataFrame
        Hours calendar with ds, is_closed
        
    Returns
    -------
    pd.DataFrame
        Forecasts with guardrails applied
    """
    df = df.copy()
    
    # Rename target_date to ds if needed
    if 'target_date' in df.columns and 'ds' not in df.columns:
        df = df.rename(columns={'target_date': 'ds'})
    
    # Merge with hours
    df = df.merge(df_hours[['ds', 'is_closed']], on='ds', how='left', suffixes=('', '_hours'))
    
    # Use is_closed from hours if not already present
    if 'is_closed_hours' in df.columns:
        df['is_closed'] = df['is_closed_hours']
        df = df.drop(columns=['is_closed_hours'])
    
    # Fill missing is_closed with False
    if 'is_closed' not in df.columns:
        df['is_closed'] = False
    df['is_closed'] = df['is_closed'].fillna(False)
    
    # Closed days: set all quantiles to 0
    df.loc[df['is_closed'] == True, ['p50', 'p80', 'p90']] = 0
    
    # Clamp to non-negative
    df['p50'] = df['p50'].clip(lower=0)
    df['p80'] = df['p80'].clip(lower=0)
    df['p90'] = df['p90'].clip(lower=0)
    
    # Enforce monotonicity: p50 <= p80 <= p90
    df['p80'] = df[['p50', 'p80']].max(axis=1)
    df['p90'] = df[['p80', 'p90']].max(axis=1)
    
    return df


def apply_overrides(df: pd.DataFrame, overrides_path: str = "data/overrides/demand_overrides.csv") -> pd.DataFrame:
    """
    Apply demand overrides if file exists.
    
    Parameters
    ----------
    df : pd.DataFrame
        Forecasts with ds, p50, p80, p90
    overrides_path : str
        Path to overrides CSV
        
    Returns
    -------
    pd.DataFrame
        Forecasts with overrides applied
    """
    if not Path(overrides_path).exists():
        logger.info("No demand overrides file found, skipping")
        return df
    
    logger.info(f"Applying demand overrides from {overrides_path}")
    
    df_overrides = pd.read_csv(overrides_path)
    df_overrides['ds'] = pd.to_datetime(df_overrides['ds'])
    
    # Merge and apply overrides
    df = df.merge(df_overrides, on='ds', how='left', suffixes=('', '_override'))
    
    for q in ['p50', 'p80', 'p90']:
        override_col = f'{q}_override'
        if override_col in df.columns:
            df[q] = df[override_col].fillna(df[q])
            df = df.drop(columns=[override_col])
    
    return df


def generate_2026_forecast(
    sales_fact_path: str = "data/processed/fact_sales_daily.parquet",
    hours_2026_path: str = "data/processed/hours_calendar_2026.parquet",
    events_2026_path: str = "data/processed/features/events_daily_2026.parquet",
    hours_history_path: str = "data/processed/hours_calendar_history.parquet",
    events_history_path: str = "data/processed/features/events_daily_history.parquet",
    inf_short_path: str = "data/processed/inference_features_short_2026.parquet",
    inf_long_path: str = "data/processed/inference_features_long_2026.parquet",
    ensemble_weights_path: str = "outputs/models/ensemble_weights.csv",
    output_daily_path: str = "outputs/forecasts/forecast_daily_2026.csv",
    output_ordering_path: str = "outputs/forecasts/rollups_ordering.csv",
    output_scheduling_path: str = "outputs/forecasts/rollups_scheduling.csv",
) -> pd.DataFrame:
    """
    Generate final 2026 forecast with ensemble, guardrails, and rollups.
    
    Returns
    -------
    pd.DataFrame
        Daily forecast for 2026
    """
    logger.info("Generating 2026 forecast")
    
    # Load data
    df_sales = pd.read_parquet(sales_fact_path)
    df_hours_2026 = pd.read_parquet(hours_2026_path)
    df_events_2026 = pd.read_parquet(events_2026_path)
    df_hours_history = pd.read_parquet(hours_history_path)
    df_events_history = pd.read_parquet(events_history_path)
    
    issue_date = df_sales['ds'].max()
    data_through = issue_date.strftime('%Y-%m-%d')
    
    logger.info(f"Issue date: {issue_date}")
    
    # Generate model predictions
    model_predictions = {}
    
    # Ensure datetime types
    df_sales['ds'] = pd.to_datetime(df_sales['ds'])
    df_hours_2026['ds'] = pd.to_datetime(df_hours_2026['ds'])

    # Baselines (provide full 2026 coverage so ensemble weights apply correctly)
    logger.info("Generating baseline predictions...")
    target_dates = df_hours_2026['ds'].sort_values().tolist()

    sn = SeasonalNaiveWeekly()
    sn.fit(df_sales)
    preds_sn = sn.predict(target_dates)
    preds_sn['horizon'] = (preds_sn['target_date'] - issue_date).dt.days
    model_predictions['seasonal_naive_weekly'] = preds_sn

    wm = WeekdayRollingMedian()
    wm.fit(df_sales)
    preds_wm = wm.predict(target_dates)
    preds_wm['horizon'] = (preds_wm['target_date'] - issue_date).dt.days
    model_predictions['weekday_rolling_median'] = preds_wm
    
    # GBM Short (H=1-14)
    logger.info("Generating GBM short predictions...")
    df_inf_short = pd.read_parquet(inf_short_path)
    
    if len(df_inf_short) > 0:
        model_short = GBMShortHorizon()
        
        # Train on full history
        df_train_short = pd.read_parquet("data/processed/train_short.parquet")
        model_short.fit(df_train_short)
        
        preds_short = model_short.predict(df_inf_short)
        preds_short['horizon'] = (preds_short['target_date'] - issue_date).dt.days
        model_predictions['gbm_short'] = preds_short
    
    # GBM Long (H=15-380)
    logger.info("Generating GBM long predictions...")
    df_inf_long = pd.read_parquet(inf_long_path)
    
    if len(df_inf_long) > 0:
        model_long = GBMLongHorizon()
        
        # Train on full history
        df_train_long = pd.read_parquet("data/processed/train_long.parquet")
        model_long.fit(df_train_long)
        
        preds_long = model_long.predict(df_inf_long)
        preds_long['horizon'] = (preds_long['target_date'] - issue_date).dt.days
        model_predictions['gbm_long'] = preds_long
    
    # Chronos-2 (H=1-90)
    logger.info("Generating Chronos-2 predictions...")
    try:
        model_chronos = Chronos2Model(prediction_length=90)
        model_chronos.fit(df_sales)
        
        if model_chronos.model is not None:
            preds_chronos = model_chronos.predict()
            
            if len(preds_chronos) > 0:
                preds_chronos['horizon'] = (preds_chronos['target_date'] - issue_date).dt.days
                # Only use Chronos for 2026 dates
                preds_chronos = preds_chronos[preds_chronos['target_date'].dt.year == 2026]
                model_predictions['chronos2'] = preds_chronos
                logger.info(f"Chronos-2 generated {len(preds_chronos)} predictions for 2026")
            else:
                logger.warning("Chronos-2 generated no predictions")
        else:
            logger.warning("Chronos-2 model not available")
    except Exception as e:
        logger.warning(f"Chronos-2 prediction failed: {e}")
    
    # Load ensemble and blend
    logger.info("Blending with ensemble weights...")
    ensemble = EnsembleModel()
    
    # Load weights manually
    df_weights = pd.read_csv(ensemble_weights_path)
    ensemble.models = df_weights['model_name'].unique().tolist()
    ensemble.weights = {}
    
    for bucket in df_weights['horizon_bucket'].unique():
        df_bucket_weights = df_weights[df_weights['horizon_bucket'] == bucket]
        ensemble.weights[bucket] = dict(zip(df_bucket_weights['model_name'], df_bucket_weights['weight']))
    
    df_forecast = ensemble.predict(model_predictions)
    
    # Apply OOF spike overlay (if backtest predictions available)
    logger.info("Applying OOF spike overlay...")
    try:
        # Load backtest predictions for OOF calibration
        df_preds_gbm = pd.read_parquet("outputs/backtests/preds_gbm_short.parquet")
        
        # Define spike flags
        spike_flags = [
            'is_black_friday',
            'is_memorial_day',
            'is_memorial_day_weekend',
            'is_labor_day_weekend',
            'is_year_end_week'
        ]
        
        # Load spike flags from training data
        df_train_short = pd.read_parquet("data/processed/train_short.parquet")
        
        # Get unique ds + spike flags from training data
        spike_cols_available = [f for f in spike_flags if f in df_train_short.columns]
        df_spike_history = df_train_short[['ds'] + spike_cols_available].drop_duplicates('ds')
        
        # Merge spike flags into actuals
        df_actuals_with_flags = df_sales.merge(
            df_spike_history,
            on='ds',
            how='left'
        )
        
        # Fill missing spike flags with 0
        for flag in spike_flags:
            if flag in df_actuals_with_flags.columns:
                df_actuals_with_flags[flag] = df_actuals_with_flags[flag].fillna(0).astype(int)
            else:
                df_actuals_with_flags[flag] = 0
        
        # Compute OOF multipliers
        multipliers = compute_oof_spike_multipliers(
            df_actuals=df_actuals_with_flags,
            df_predictions=df_preds_gbm,
            spike_flags=spike_flags,
            shrinkage=0.3,
            min_multiplier=0.8,
            max_multiplier=1.8,
            min_observations=2
        )
        
        # Load spike flags for 2026 from inference data
        df_inf_long = pd.read_parquet(inf_long_path)
        spike_cols_2026 = [f for f in spike_flags if f in df_inf_long.columns]
        df_spike_2026 = df_inf_long[['ds'] + spike_cols_2026].drop_duplicates('ds')
        
        # Merge spike flags into forecast
        df_forecast = df_forecast.merge(df_spike_2026, on='ds', how='left')
        
        # Fill missing spike flags with 0
        for flag in spike_flags:
            if flag in df_forecast.columns:
                df_forecast[flag] = df_forecast[flag].fillna(0).astype(int)
            else:
                df_forecast[flag] = 0
        
        # Apply overlay
        df_forecast = apply_spike_overlay(
            df_forecast,
            multipliers,
            spike_flags,
            quantile_cols=['p50', 'p80', 'p90']
        )
        
        # Generate overlay report
        generate_oof_overlay_report(
            df_actuals=df_actuals_with_flags,
            df_predictions=df_preds_gbm,
            multipliers=multipliers,
            spike_flags=spike_flags,
            output_path="outputs/reports/oof_spike_overlay_report.md"
        )
        
        logger.info(f"OOF spike overlay applied with multipliers: {multipliers}")
        
    except Exception as e:
        logger.warning(f"OOF spike overlay failed: {e}. Continuing without overlay.")
    
    # Apply guardrails
    logger.info("Applying guardrails...")
    df_forecast = apply_guardrails(df_forecast, df_hours_2026)
    
    # Apply overrides
    df_forecast = apply_overrides(df_forecast)
    
    # Re-apply guardrails after overrides
    df_forecast = apply_guardrails(df_forecast, df_hours_2026)
    
    # Add metadata
    df_forecast = df_forecast.merge(
        df_hours_2026[['ds', 'open_minutes']],
        on='ds',
        how='left'
    )
    df_forecast['data_through'] = data_through
    
    # Sort and select columns
    df_forecast = df_forecast.sort_values('ds')
    df_forecast = df_forecast[['ds', 'p50', 'p80', 'p90', 'is_closed', 'open_minutes', 'data_through']]
    
    # Save daily forecast
    Path(output_daily_path).parent.mkdir(parents=True, exist_ok=True)
    df_forecast.to_csv(output_daily_path, index=False)
    logger.info(f"Saved daily forecast to {output_daily_path} ({len(df_forecast)} rows)")
    
    # Generate rollups (aligned to operations)
    logger.info("Generating rollups...")

    snapshot_date = datetime.now().strftime('%Y-%m-%d')

    df_forecast_roll = df_forecast.copy()
    df_forecast_roll['ds'] = pd.to_datetime(df_forecast_roll['ds'])
    df_forecast_roll = df_forecast_roll.sort_values('ds')

    forecast_end = df_forecast_roll['ds'].max()

    def sum_window(start: pd.Timestamp, end: pd.Timestamp) -> dict:
        end_capped = min(end, forecast_end)
        mask = (df_forecast_roll['ds'] >= start) & (df_forecast_roll['ds'] <= end_capped)
        totals = df_forecast_roll.loc[mask, ['p50', 'p80', 'p90']].sum()
        notes = []
        if end_capped < end:
            notes.append("window_truncated_at_forecast_end")
        return {
            'snapshot_date': snapshot_date,
            'coverage_start': start.strftime('%Y-%m-%d'),
            'coverage_end': end_capped.strftime('%Y-%m-%d'),
            'p50': float(totals['p50']),
            'p80': float(totals['p80']),
            'p90': float(totals['p90']),
            'notes': ";".join(notes) if notes else ""
        }

    # Ordering rollups:
    # - Sunday order covers Sunday→Saturday (7 days)
    # - Wednesday order covers Wednesday→next Wednesday (8 days, inclusive)
    ordering_rows = []

    # Sundays (dayofweek: Mon=0 ... Sun=6)
    sunday_starts = df_forecast_roll[df_forecast_roll['ds'].dt.dayofweek == 6]['ds'].tolist()
    for start in sunday_starts:
        row = sum_window(start, start + pd.Timedelta(days=6))
        row['notes'] = (row['notes'] + (";" if row['notes'] else "") + "order_cycle=sun_sat")
        ordering_rows.append(row)

    # Wednesdays (dayofweek=2)
    wed_starts = df_forecast_roll[df_forecast_roll['ds'].dt.dayofweek == 2]['ds'].tolist()
    for start in wed_starts:
        row = sum_window(start, start + pd.Timedelta(days=7))
        row['notes'] = (row['notes'] + (";" if row['notes'] else "") + "order_cycle=wed_wed")
        ordering_rows.append(row)

    df_ordering = pd.DataFrame(ordering_rows).sort_values(['coverage_start', 'notes'])
    Path(output_ordering_path).parent.mkdir(parents=True, exist_ok=True)
    df_ordering.to_csv(output_ordering_path, index=False)
    logger.info(f"Saved ordering rollup to {output_ordering_path}")

    # Scheduling rollups:
    # - Schedule week is Wednesday→Tuesday (7 days inclusive)
    scheduling_rows = []
    sched_starts = wed_starts  # Wednesday starts
    for start in sched_starts:
        row = sum_window(start, start + pd.Timedelta(days=6))
        row['notes'] = (row['notes'] + (";" if row['notes'] else "") + "schedule_week=wed_tue")
        scheduling_rows.append(row)

    df_scheduling = pd.DataFrame(scheduling_rows).sort_values(['coverage_start'])
    Path(output_scheduling_path).parent.mkdir(parents=True, exist_ok=True)
    df_scheduling.to_csv(output_scheduling_path, index=False)
    logger.info(f"Saved scheduling rollup to {output_scheduling_path}")
    
    return df_forecast


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Generate 2026 forecast
    df_forecast = generate_2026_forecast()
    
    print("\n=== 2026 Forecast Generated ===")
    print(f"Total days: {len(df_forecast)}")
    print(f"Closed days: {df_forecast['is_closed'].sum()}")
    print(f"Total p50: ${df_forecast['p50'].sum():,.2f}")
    print(f"\nSample forecast:")
    print(df_forecast.head(10).to_string(index=False))
    
    # Verify guardrails
    print("\n=== Guardrail Checks ===")
    print(f"Negative forecasts: {(df_forecast['p50'] < 0).sum()}")
    print(f"Monotonicity violations: {((df_forecast['p50'] > df_forecast['p80']) | (df_forecast['p80'] > df_forecast['p90'])).sum()}")
    print(f"Closed days with non-zero forecast: {((df_forecast['is_closed']) & (df_forecast['p50'] > 0)).sum()}")
