"""
Peak-sensitive evaluation metrics for operational forecasting.

Focuses on preventing stockouts and understaffing on high-demand days.
"""

import pandas as pd
import numpy as np


def compute_peak_metrics(df_preds: pd.DataFrame, peak_percentile: float = 0.9) -> dict:
    """
    Compute peak-day specific metrics.
    
    Args:
        df_preds: Predictions dataframe with y (actual), p50, p80, p90
        peak_percentile: Percentile threshold for "peak days" (default: 90th = top decile)
    
    Returns:
        Dictionary of metrics
    """
    df = df_preds.copy()
    
    # Remove rows with missing actuals
    df = df[df['y'].notna()].copy()
    
    if len(df) == 0:
        return {
            'overall_wmape': np.nan,
            'overall_mase': np.nan,
            'peak_threshold': np.nan,
            'peak_wmape': np.nan,
            'peak_underprediction_rate': np.nan,
            'peak_p80_coverage': np.nan,
            'peak_p90_coverage': np.nan,
            'n_total': 0,
            'n_peak': 0
        }
    
    # Identify peak days
    peak_threshold = df['y'].quantile(peak_percentile)
    df['is_peak'] = df['y'] >= peak_threshold
    
    # Overall metrics
    overall_wmape = np.sum(np.abs(df['y'] - df['p50'])) / np.sum(np.abs(df['y']))
    
    # MASE (Mean Absolute Scaled Error) - scale by naive forecast MAE
    naive_mae = np.mean(np.abs(df['y'].diff().dropna()))
    if naive_mae > 0:
        overall_mase = np.mean(np.abs(df['y'] - df['p50'])) / naive_mae
    else:
        overall_mase = np.nan
    
    # Peak-day metrics
    df_peak = df[df['is_peak']].copy()
    n_peak = len(df_peak)
    
    if n_peak > 0:
        peak_wmape = np.sum(np.abs(df_peak['y'] - df_peak['p50'])) / np.sum(np.abs(df_peak['y']))
        peak_underprediction_rate = (df_peak['p50'] < df_peak['y']).mean()
        peak_p80_coverage = (df_peak['y'] <= df_peak['p80']).mean()
        peak_p90_coverage = (df_peak['y'] <= df_peak['p90']).mean()
    else:
        peak_wmape = np.nan
        peak_underprediction_rate = np.nan
        peak_p80_coverage = np.nan
        peak_p90_coverage = np.nan
    
    return {
        'overall_wmape': overall_wmape,
        'overall_mase': overall_mase,
        'peak_threshold': peak_threshold,
        'peak_wmape': peak_wmape,
        'peak_underprediction_rate': peak_underprediction_rate,
        'peak_p80_coverage': peak_p80_coverage,
        'peak_p90_coverage': peak_p90_coverage,
        'n_total': len(df),
        'n_peak': n_peak
    }


def compute_peak_metrics_by_horizon(df_preds: pd.DataFrame, peak_percentile: float = 0.9) -> pd.DataFrame:
    """
    Compute peak metrics grouped by horizon bucket.
    
    Args:
        df_preds: Predictions with y, p50, p80, p90, horizon_bucket
        peak_percentile: Peak threshold percentile
    
    Returns:
        DataFrame with metrics per horizon bucket
    """
    if 'horizon_bucket' not in df_preds.columns:
        # Add horizon bucket if missing
        df_preds = df_preds.copy()
        df_preds['horizon_bucket'] = df_preds['horizon'].apply(assign_horizon_bucket)
    
    results = []
    
    for bucket, df_bucket in df_preds.groupby('horizon_bucket'):
        metrics = compute_peak_metrics(df_bucket, peak_percentile)
        metrics['horizon_bucket'] = bucket
        results.append(metrics)
    
    return pd.DataFrame(results)


def assign_horizon_bucket(h):
    """Assign horizon to bucket."""
    if h <= 7:
        return "1-7"
    elif h <= 14:
        return "8-14"
    elif h <= 30:
        return "15-30"
    elif h <= 90:
        return "31-90"
    else:
        return "91-380"


def compute_combined_score(metrics: dict, weights: dict = None) -> float:
    """
    Compute combined operational score for model selection.
    
    Score = overall_wmape + 2.0 * peak_wmape + 1.0 * peak_underprediction_rate
    
    Lower is better. Weights peak performance to avoid stockouts.
    
    Args:
        metrics: Dictionary of metrics
        weights: Custom weights (default: {'overall': 1.0, 'peak_wmape': 2.0, 'peak_under': 1.0})
    
    Returns:
        Combined score (lower is better)
    """
    if weights is None:
        weights = {
            'overall': 1.0,
            'peak_wmape': 2.0,
            'peak_under': 1.0
        }
    
    score = (
        weights['overall'] * metrics.get('overall_wmape', 0) +
        weights['peak_wmape'] * metrics.get('peak_wmape', 0) +
        weights['peak_under'] * metrics.get('peak_underprediction_rate', 0)
    )
    
    return score


if __name__ == '__main__':
    # Test with sample data
    np.random.seed(42)
    
    # Simulate predictions
    n = 100
    y_true = np.random.lognormal(7, 0.5, n)  # Skewed distribution (like sales)
    y_pred = y_true * np.random.normal(1.0, 0.15, n)  # 15% error
    
    df = pd.DataFrame({
        'y': y_true,
        'p50': y_pred,
        'p80': y_pred * 1.1,
        'p90': y_pred * 1.2,
        'horizon': np.random.randint(1, 100, n)
    })
    
    # Compute metrics
    metrics = compute_peak_metrics(df)
    
    print("Peak metrics test:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    
    print(f"\nCombined score: {compute_combined_score(metrics):.4f}")
