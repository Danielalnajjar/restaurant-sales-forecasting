"""
Spike-day uplift overlay for preventing model smoothing of rare one-day spikes.

Computes historical uplift multipliers for spike days (Black Friday, Memorial Day, etc.)
and applies them as a post-processing overlay to forecasts.
"""

import pandas as pd
import numpy as np
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def compute_spike_uplift_priors(
    df_sales: pd.DataFrame,
    ds_max: pd.Timestamp = None,
    min_observations: int = 2,
    shrinkage_factor: float = 0.5
) -> pd.DataFrame:
    """
    Compute uplift multipliers for spike-day flags using historical data.
    
    Uplift = median(y on spike days) / median(y on comparable baseline days)
    
    Args:
        df_sales: Sales history with ds, y, is_closed, and spike-day flags
        ds_max: Maximum date to use (for backtest OOF computation)
        min_observations: Minimum spike-day observations required
        shrinkage_factor: Shrinkage toward 1.0 (no uplift)
    
    Returns:
        DataFrame with spike_flag, uplift_multiplier, confidence, n_obs
    """
    if ds_max is not None:
        df_sales = df_sales[df_sales['ds'] <= ds_max].copy()
    else:
        df_sales = df_sales.copy()
    
    # Filter to open days only
    df_open = df_sales[~df_sales['is_closed']].copy()
    
    if len(df_open) == 0:
        logger.warning("No open days in sales history")
        return pd.DataFrame(columns=['spike_flag', 'uplift_multiplier', 'confidence', 'n_obs'])
    
    # Baseline median (all open days)
    baseline_median = df_open['y'].median()
    
    # Spike flags to compute uplift for
    spike_flags = [
        'is_black_friday',
        'is_thanksgiving_day',
        'is_day_after_thanksgiving',
        'is_memorial_day',
        'is_memorial_day_weekend',
        'is_labor_day',
        'is_labor_day_weekend',
        'is_independence_day',
        'is_christmas_eve',
        'is_day_after_christmas',
        'is_year_end_week',
    ]
    
    # Filter to flags that exist in data
    spike_flags = [f for f in spike_flags if f in df_open.columns]
    
    results = []
    
    for flag in spike_flags:
        # Get spike days
        spike_days = df_open[df_open[flag] == True]
        n_obs = len(spike_days)
        
        if n_obs < min_observations:
            # Insufficient data, use neutral multiplier
            results.append({
                'spike_flag': flag,
                'uplift_multiplier': 1.0,
                'confidence': 'insufficient',
                'n_obs': n_obs
            })
            continue
        
        # Compute raw uplift
        spike_median = spike_days['y'].median()
        raw_uplift = spike_median / baseline_median if baseline_median > 0 else 1.0
        
        # Apply shrinkage toward 1.0
        shrunk_uplift = 1.0 + shrinkage_factor * (raw_uplift - 1.0)
        
        # Cap to reasonable range [0.7, 2.5]
        capped_uplift = np.clip(shrunk_uplift, 0.7, 2.5)
        
        # Confidence based on sample size
        if n_obs >= 5:
            confidence = 'high'
        elif n_obs >= 3:
            confidence = 'medium'
        else:
            confidence = 'low'
        
        results.append({
            'spike_flag': flag,
            'uplift_multiplier': capped_uplift,
            'confidence': confidence,
            'n_obs': n_obs
        })
        
        logger.info(f"{flag}: {n_obs} obs, raw={raw_uplift:.3f}, shrunk={shrunk_uplift:.3f}, final={capped_uplift:.3f}")
    
    return pd.DataFrame(results)


def apply_spike_uplift_overlay(
    df_forecast: pd.DataFrame,
    df_uplift: pd.DataFrame,
    spike_flags: list = None
) -> pd.DataFrame:
    """
    Apply spike-day uplift overlay to forecasts.
    
    For each row where a spike flag is True, multiply forecast by uplift_multiplier.
    
    Args:
        df_forecast: Forecast dataframe with ds, p50, p80, p90, and spike flags
        df_uplift: Uplift priors with spike_flag, uplift_multiplier
        spike_flags: List of spike flags to apply (default: all in df_uplift)
    
    Returns:
        DataFrame with adjusted forecasts and adjustment_log column
    """
    df = df_forecast.copy()
    
    if spike_flags is None:
        spike_flags = df_uplift['spike_flag'].tolist()
    
    # Create uplift lookup
    uplift_map = dict(zip(df_uplift['spike_flag'], df_uplift['uplift_multiplier']))
    
    # Track adjustments
    df['adjustment_log'] = ''
    df['adjustment_multiplier'] = 1.0
    
    for flag in spike_flags:
        if flag not in df.columns:
            logger.warning(f"Spike flag {flag} not in forecast dataframe")
            continue
        
        if flag not in uplift_map:
            logger.warning(f"No uplift multiplier for {flag}")
            continue
        
        multiplier = uplift_map[flag]
        
        # Apply to rows where flag is True
        mask = df[flag] == True
        n_adjusted = mask.sum()
        
        if n_adjusted > 0:
            df.loc[mask, 'p50'] *= multiplier
            df.loc[mask, 'p80'] *= multiplier
            df.loc[mask, 'p90'] *= multiplier
            df.loc[mask, 'adjustment_multiplier'] *= multiplier
            df.loc[mask, 'adjustment_log'] += f"{flag}={multiplier:.3f}; "
            
            logger.info(f"Applied {flag} uplift ({multiplier:.3f}) to {n_adjusted} days")
    
    return df


def save_spike_uplift_log(df_forecast: pd.DataFrame, output_path: str):
    """
    Save a log of spike-day adjustments for transparency.
    
    Args:
        df_forecast: Forecast with adjustment_log column
        output_path: Path to save log CSV
    """
    adjusted = df_forecast[df_forecast['adjustment_log'] != ''].copy()
    
    if len(adjusted) == 0:
        logger.info("No spike-day adjustments applied")
        return
    
    log_df = adjusted[['ds', 'p50', 'adjustment_multiplier', 'adjustment_log']].copy()
    log_df = log_df.sort_values('ds')
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    log_df.to_csv(output_path, index=False)
    
    logger.info(f"Saved spike uplift log to {output_path} ({len(log_df)} adjusted days)")


if __name__ == '__main__':
    # Test spike uplift computation
    import sys
    sys.path.insert(0, '/home/ubuntu/forecasting/src')
    
    from forecasting.features.spike_days import add_spike_day_features
    
    # Load sales data
    df_sales = pd.read_parquet('/home/ubuntu/forecasting/data/processed/fact_sales_daily.parquet')
    
    # Add spike-day features
    df_sales = add_spike_day_features(df_sales)
    
    # Compute uplift priors
    df_uplift = compute_spike_uplift_priors(df_sales)
    
    print("Spike-day uplift priors:")
    print(df_uplift.to_string(index=False))
    
    # Save
    df_uplift.to_csv('/home/ubuntu/forecasting/outputs/models/spike_uplift_priors.csv', index=False)
    print("\nSaved to outputs/models/spike_uplift_priors.csv")
