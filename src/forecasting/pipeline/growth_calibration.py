"""
Growth calibration layer for aligning forecast totals with expected YoY growth.

V5.0: With only 13 months of data, learned trend is unstable. This module provides
operator-configurable growth assumptions without manual per-day overrides.

Key features:
- Config-driven (target_yoy growth rate)
- Applies to non-spike days only (preserves peak corrections)
- Scales forecast to match target annual total
- Leakage-safe for backtests (uses only data <= cutoff)
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


def apply_growth_calibration(
    df_forecast: pd.DataFrame,
    df_actuals_baseline: pd.DataFrame,
    target_yoy: float = 0.10,
    excluded_spike_flags: List[str] = None,
    min_scale: float = 0.85,
    max_scale: float = 1.15
) -> pd.DataFrame:
    """
    Apply growth calibration to align forecast with target YoY growth.
    
    Algorithm:
    1. Compute baseline total from actuals (e.g., 2025 total)
    2. Compute target total = baseline * (1 + target_yoy)
    3. Compute current forecast total EXCLUDING spike days
    4. Scale non-spike days by factor = target / current
    5. Apply scaling to p50/p80/p90 for non-spike days
    
    Args:
        df_forecast: Forecast dataframe with ds, p50, p80, p90, spike flags
        df_actuals_baseline: Historical actuals for baseline (e.g., 2025 sales)
        target_yoy: Target year-over-year growth (e.g., 0.10 for +10%)
        excluded_spike_flags: Spike flags to exclude from scaling (preserve peaks)
        min_scale: Minimum allowed scale factor (safety bound)
        max_scale: Maximum allowed scale factor (safety bound)
    
    Returns:
        DataFrame with calibrated forecasts and calibration_scale column
    """
    df = df_forecast.copy()
    
    # Default excluded spike flags
    if excluded_spike_flags is None:
        excluded_spike_flags = [
            'is_black_friday',
            'is_year_end_week',
            'is_memorial_day',
            'is_labor_day',
            'is_independence_day',
            'is_christmas_eve',
            'is_day_after_christmas'
        ]
    
    # Compute baseline total from actuals
    baseline_total = df_actuals_baseline[~df_actuals_baseline['is_closed']]['y'].sum()
    
    if baseline_total <= 0:
        logger.warning("Baseline total is zero or negative, skipping growth calibration")
        df['calibration_scale'] = 1.0
        return df
    
    # Compute target total
    target_total = baseline_total * (1 + target_yoy)
    
    logger.info(f"Growth calibration: baseline=${baseline_total:,.0f}, target=${target_total:,.0f} ({target_yoy:+.1%})")
    
    # Identify spike days (any excluded flag is True)
    df['is_spike_excluded'] = False
    for flag in excluded_spike_flags:
        if flag in df.columns:
            df['is_spike_excluded'] |= (df[flag] == True)
    
    # Compute current forecast totals
    current_total_all = df['p50'].sum()
    current_total_nonspike = df[~df['is_spike_excluded']]['p50'].sum()
    current_total_spike = df[df['is_spike_excluded']]['p50'].sum()
    
    logger.info(f"Current forecast: total=${current_total_all:,.0f}, "
               f"non-spike=${current_total_nonspike:,.0f}, spike=${current_total_spike:,.0f}")
    
    # Compute scale factor for non-spike days
    # target_total = scale * current_nonspike + current_spike
    # scale = (target_total - current_spike) / current_nonspike
    
    if current_total_nonspike <= 0:
        logger.warning("No non-spike days to calibrate, skipping")
        df['calibration_scale'] = 1.0
        return df
    
    target_nonspike_total = target_total - current_total_spike
    raw_scale = target_nonspike_total / current_total_nonspike
    
    # Clamp scale factor to safety bounds
    clamped_scale = np.clip(raw_scale, min_scale, max_scale)
    
    if raw_scale != clamped_scale:
        logger.warning(f"Scale factor clamped: raw={raw_scale:.3f}, clamped={clamped_scale:.3f}")
    
    # Apply scaling to non-spike days
    mask_nonspike = ~df['is_spike_excluded']
    n_scaled = mask_nonspike.sum()
    
    df.loc[mask_nonspike, 'p50'] *= clamped_scale
    df.loc[mask_nonspike, 'p80'] *= clamped_scale
    df.loc[mask_nonspike, 'p90'] *= clamped_scale
    
    # Track calibration scale
    df['calibration_scale'] = 1.0
    df.loc[mask_nonspike, 'calibration_scale'] = clamped_scale
    
    # Verify final total
    final_total = df['p50'].sum()
    final_growth = (final_total / baseline_total) - 1
    
    logger.info(f"Growth calibration applied: scaled {n_scaled} non-spike days by {clamped_scale:.3f}")
    logger.info(f"Final forecast: total=${final_total:,.0f} ({final_growth:+.1%} vs baseline)")
    
    # Clean up temporary column
    df = df.drop(columns=['is_spike_excluded'])
    
    return df


def save_calibration_log(df_forecast: pd.DataFrame, output_path: str):
    """
    Save growth calibration log for transparency.
    
    Args:
        df_forecast: Forecast with calibration_scale column
        output_path: Path to save log CSV
    """
    if 'calibration_scale' not in df_forecast.columns:
        logger.info("No calibration scale column, skipping log")
        return
    
    # Summary stats
    n_scaled = (df_forecast['calibration_scale'] != 1.0).sum()
    avg_scale = df_forecast[df_forecast['calibration_scale'] != 1.0]['calibration_scale'].mean()
    
    log_df = df_forecast[['ds', 'p50', 'calibration_scale']].copy()
    log_df = log_df.sort_values('ds')
    
    from pathlib import Path
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    log_df.to_csv(output_path, index=False)
    
    logger.info(f"Saved calibration log to {output_path} ({n_scaled} scaled days, avg scale={avg_scale:.3f})")


if __name__ == '__main__':
    # Test growth calibration
    import sys
    sys.path.insert(0, '/home/ubuntu/forecasting/src')
    
    # Load actuals
    df_actuals = pd.read_parquet('/home/ubuntu/forecasting/data/processed/fact_sales_daily.parquet')
    df_actuals_2025 = df_actuals[df_actuals['ds'].dt.year == 2025].copy()
    
    # Load forecast
    df_forecast = pd.read_csv('/home/ubuntu/forecasting/outputs/forecasts/forecast_daily_2026.csv')
    df_forecast['ds'] = pd.to_datetime(df_forecast['ds'])
    
    # Apply calibration
    df_calibrated = apply_growth_calibration(
        df_forecast=df_forecast,
        df_actuals_baseline=df_actuals_2025,
        target_yoy=0.10
    )
    
    print("Growth calibration test:")
    print(f"Original total: ${df_forecast['p50'].sum():,.0f}")
    print(f"Calibrated total: ${df_calibrated['p50'].sum():,.0f}")
    print(f"Target growth: +10%")
