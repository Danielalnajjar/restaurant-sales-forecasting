"""
OOF-calibrated spike overlay for peak-day forecasting.

Computes calibration multipliers as y / yhat_p50 for spike days,
using out-of-fold methodology to avoid double-counting.
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


def compute_oof_spike_multipliers(
    df_actuals: pd.DataFrame,
    df_predictions: pd.DataFrame,
    spike_flags: List[str],
    shrinkage: float = 0.3,
    min_multiplier: float = 0.8,
    max_multiplier: float = 1.8,
    min_observations: int = 2
) -> Dict[str, float]:
    """
    Compute OOF calibration multipliers for spike days.
    
    Parameters
    ----------
    df_actuals : pd.DataFrame
        Actual sales with columns: ds, y, is_closed, spike flags
    df_predictions : pd.DataFrame
        Model predictions with columns: ds, yhat_p50, cutoff_date
    spike_flags : List[str]
        List of spike flag column names (e.g., 'is_black_friday')
    shrinkage : float
        Shrinkage toward 1.0 (0 = no shrinkage, 1 = full shrinkage to 1.0)
    min_multiplier : float
        Minimum allowed multiplier
    max_multiplier : float
        Maximum allowed multiplier
    min_observations : int
        Minimum observations required to compute multiplier
        
    Returns
    -------
    Dict[str, float]
        Multipliers for each spike flag
    """
    # Merge actuals with predictions
    df_merged = df_predictions.merge(
        df_actuals[['ds', 'y', 'is_closed'] + spike_flags],
        on='ds',
        how='inner'
    )
    
    # Filter to open days only
    df_merged = df_merged[~df_merged['is_closed']].copy()
    
    # Compute ratio y / yhat_p50
    df_merged['ratio'] = df_merged['y'] / df_merged['yhat_p50'].clip(lower=1.0)
    
    multipliers = {}
    
    for flag in spike_flags:
        # Get spike days for this flag
        df_spike = df_merged[df_merged[flag] == 1].copy()
        
        if len(df_spike) < min_observations:
            logger.warning(f"Spike flag '{flag}': only {len(df_spike)} observations, using 1.0")
            multipliers[flag] = 1.0
            continue
        
        # Compute median ratio
        median_ratio = df_spike['ratio'].median()
        
        # Apply shrinkage toward 1.0
        multiplier = 1.0 + (median_ratio - 1.0) * (1.0 - shrinkage)
        
        # Clip to bounds
        multiplier = np.clip(multiplier, min_multiplier, max_multiplier)
        
        multipliers[flag] = multiplier
        
        logger.info(f"Spike flag '{flag}': {len(df_spike)} obs, median ratio {median_ratio:.3f}, "
                   f"multiplier {multiplier:.3f} (after shrinkage {shrinkage})")
    
    return multipliers


def apply_spike_overlay(
    df_forecast: pd.DataFrame,
    multipliers: Dict[str, float],
    spike_flags: List[str],
    quantile_cols: List[str] = ['p50', 'p80', 'p90']
) -> pd.DataFrame:
    """
    Apply spike overlay multipliers to forecast.
    
    Parameters
    ----------
    df_forecast : pd.DataFrame
        Forecast with columns: ds, p50, p80, p90, spike flags
    multipliers : Dict[str, float]
        Multipliers for each spike flag
    spike_flags : List[str]
        List of spike flag column names
    quantile_cols : List[str]
        Quantile columns to adjust
        
    Returns
    -------
    pd.DataFrame
        Forecast with overlay applied
    """
    df = df_forecast.copy()
    
    # Track which dates were adjusted
    df['overlay_applied'] = False
    df['overlay_multiplier'] = 1.0
    
    for flag in spike_flags:
        if flag not in df.columns:
            logger.warning(f"Spike flag '{flag}' not found in forecast")
            continue
        
        if flag not in multipliers:
            logger.warning(f"No multiplier found for spike flag '{flag}'")
            continue
        
        multiplier = multipliers[flag]
        
        # Apply multiplier to spike days
        mask = (df[flag] == 1)
        n_adjusted = mask.sum()
        
        if n_adjusted > 0:
            for col in quantile_cols:
                if col in df.columns:
                    df.loc[mask, col] = df.loc[mask, col] * multiplier
            
            df.loc[mask, 'overlay_applied'] = True
            df.loc[mask, 'overlay_multiplier'] = multiplier
            
            logger.info(f"Applied {multiplier:.3f}x multiplier to {n_adjusted} days for flag '{flag}'")
    
    return df


def generate_oof_overlay_report(
    df_actuals: pd.DataFrame,
    df_predictions: pd.DataFrame,
    multipliers: Dict[str, float],
    spike_flags: List[str],
    output_path: str
) -> None:
    """
    Generate report on OOF spike overlay calibration.
    
    Parameters
    ----------
    df_actuals : pd.DataFrame
        Actual sales
    df_predictions : pd.DataFrame
        Model predictions
    multipliers : Dict[str, float]
        Computed multipliers
    spike_flags : List[str]
        Spike flag names
    output_path : str
        Path to save report
    """
    # Merge actuals with predictions
    df_merged = df_predictions.merge(
        df_actuals[['ds', 'y', 'is_closed'] + spike_flags],
        on='ds',
        how='inner'
    )
    
    df_merged = df_merged[~df_merged['is_closed']].copy()
    df_merged['ratio'] = df_merged['y'] / df_merged['yhat_p50'].clip(lower=1.0)
    
    report_lines = [
        "# OOF Spike Overlay Calibration Report\n",
        f"Generated: {pd.Timestamp.now()}\n",
        "\n## Calibration Multipliers\n",
        "\n| Spike Flag | Observations | Median Ratio | Multiplier | Status |",
        "|------------|--------------|--------------|------------|--------|"
    ]
    
    for flag in spike_flags:
        df_spike = df_merged[df_merged[flag] == 1]
        n_obs = len(df_spike)
        
        if n_obs > 0:
            median_ratio = df_spike['ratio'].median()
            multiplier = multipliers.get(flag, 1.0)
            status = "✓" if multiplier != 1.0 else "default"
        else:
            median_ratio = np.nan
            multiplier = 1.0
            status = "no data"
        
        report_lines.append(
            f"| {flag} | {n_obs} | {median_ratio:.3f if not np.isnan(median_ratio) else 'N/A'} | "
            f"{multiplier:.3f} | {status} |"
        )
    
    report_lines.extend([
        "\n## Spike Day Performance\n",
        "\n| Spike Flag | Date | Actual | Predicted | Ratio | Multiplier Applied |",
        "|------------|------|--------|-----------|-------|-------------------|"
    ])
    
    for flag in spike_flags:
        df_spike = df_merged[df_merged[flag] == 1].sort_values('ds')
        for _, row in df_spike.iterrows():
            multiplier = multipliers.get(flag, 1.0)
            report_lines.append(
                f"| {flag} | {row['ds'].strftime('%Y-%m-%d')} | ${row['y']:.0f} | "
                f"${row['yhat_p50']:.0f} | {row['ratio']:.3f} | {multiplier:.3f}x |"
            )
    
    report_lines.append("\n## Notes\n")
    report_lines.append("- Multipliers computed using out-of-fold (OOF) methodology\n")
    report_lines.append("- Shrinkage applied toward 1.0 to prevent overfitting\n")
    report_lines.append("- Multipliers capped to [0.8, 1.8] range\n")
    report_lines.append("- Applied consistently to p50, p80, and p90 quantiles\n")
    
    with open(output_path, 'w') as f:
        f.write('\n'.join(report_lines))
    
    logger.info(f"OOF overlay report saved to {output_path}")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Test with sample data
    df_actuals = pd.DataFrame({
        'ds': pd.date_range('2025-11-01', periods=30),
        'y': np.random.uniform(2000, 3000, 30),
        'is_closed': [False] * 30,
        'is_black_friday': [0] * 27 + [1] + [0] * 2,
        'is_memorial_day': [0] * 30
    })
    
    # Simulate Black Friday being 2x higher
    df_actuals.loc[df_actuals['is_black_friday'] == 1, 'y'] = 6000
    
    df_predictions = pd.DataFrame({
        'ds': df_actuals['ds'],
        'yhat_p50': np.random.uniform(2000, 3000, 30),
        'cutoff_date': pd.Timestamp('2025-10-31')
    })
    
    spike_flags = ['is_black_friday', 'is_memorial_day']
    
    multipliers = compute_oof_spike_multipliers(
        df_actuals, df_predictions, spike_flags
    )
    
    print(f"Computed multipliers: {multipliers}")
