"""
Out-of-fold spike overlay for systematic spike-day correction.

FIXED in V4.2 based on ChatGPT 5.2 Pro audit:
- Schema normalization (handles target_date/ds, p50/yhat_p50)
- Non-compounding multipliers (max, not product)
- Shrinkage and caps for stability
"""
import logging
import numpy as np
import pandas as pd
from typing import Dict, List

logger = logging.getLogger(__name__)


def compute_oof_spike_multipliers(
    df_predictions: pd.DataFrame,
    df_actuals: pd.DataFrame,
    df_spike_flags: pd.DataFrame,
    id_col: str = "ds",
    min_observations: int = 1,  # Allow single-observation holidays (data-limited)
    shrinkage: float = 0.65,    # Shrink toward 1.0 for stability
    cap_low: float = 0.85,      # Prevent over-correction downward
    cap_high: float = 1.80      # Prevent over-correction upward
) -> Dict[str, float]:
    """
    Compute multipliers from OOF residual ratios on spike days.
    
    For each spike flag:
        ratio = actual / prediction
    Then shrink toward 1.0 and cap for stability.
    
    FIXED: Schema normalization, deduplication, shrinkage, caps
    
    Parameters
    ----------
    df_predictions : pd.DataFrame
        OOF predictions with date column and prediction column
        Accepts: ds/target_date, p50/yhat_p50/yhat
    df_actuals : pd.DataFrame
        Actuals with date and sales columns
        Accepts: ds/target_date, y/Net sales
    df_spike_flags : pd.DataFrame
        Spike flags with date and is_* columns
    id_col : str
        Date column name (default: "ds")
    min_observations : int
        Minimum observations needed to compute multiplier
    shrinkage : float
        Shrinkage factor toward 1.0 (0.65 = shrink 35% toward neutral)
    cap_low : float
        Lower bound for multiplier
    cap_high : float
        Upper bound for multiplier
        
    Returns
    -------
    Dict[str, float]
        Multipliers for each spike flag
    """
    preds = df_predictions.copy()
    
    # ---- Schema Normalization ----
    # Handle different date column names
    if id_col not in preds.columns:
        if "target_date" in preds.columns:
            preds = preds.rename(columns={"target_date": id_col})
        else:
            raise ValueError(f"df_predictions missing '{id_col}' or 'target_date'")
    
    # Handle different prediction column names
    if "yhat_p50" not in preds.columns:
        if "p50" in preds.columns:
            preds = preds.rename(columns={"p50": "yhat_p50"})
        elif "yhat" in preds.columns:
            preds = preds.rename(columns={"yhat": "yhat_p50"})
        else:
            raise ValueError("df_predictions missing 'yhat_p50' (or 'p50'/'yhat')")
    
    preds[id_col] = pd.to_datetime(preds[id_col])
    
    # If multiple predictions per day exist, reduce to one (median is robust)
    preds = preds.groupby(id_col, as_index=False)["yhat_p50"].median()
    
    # ---- Normalize Actuals ----
    actuals = df_actuals.copy()
    if "y" not in actuals.columns:
        if "Net sales" in actuals.columns:
            actuals = actuals.rename(columns={"Net sales": "y"})
        else:
            raise ValueError("df_actuals missing 'y' (or 'Net sales')")
    
    actuals[id_col] = pd.to_datetime(actuals[id_col])
    
    # ---- Normalize Flags ----
    flags = df_spike_flags.copy()
    flags[id_col] = pd.to_datetime(flags[id_col])
    
    # ---- Merge ----
    merged = preds.merge(actuals[[id_col, "y"]], on=id_col, how="inner") \
                  .merge(flags, on=id_col, how="left").fillna(0)
    
    merged["ratio"] = np.where(merged["yhat_p50"] > 0, merged["y"] / merged["yhat_p50"], np.nan)
    
    # ---- Compute Multipliers ----
    multipliers = {}
    flag_cols = [c for c in flags.columns if c.startswith("is_")]
    
    for flag in flag_cols:
        rows = merged[merged[flag].astype(int) == 1]
        rows = rows[np.isfinite(rows["ratio"])]
        
        if len(rows) < min_observations:
            logger.warning(f"Spike flag '{flag}' has only {len(rows)} observations (min: {min_observations}), skipping")
            continue
        
        # Compute raw multiplier (median is robust to outliers)
        raw = float(np.median(rows["ratio"]))
        
        # Shrink toward 1.0 for stability
        shrunk = 1.0 + shrinkage * (raw - 1.0)
        
        # Cap to prevent instability
        capped = float(np.clip(shrunk, cap_low, cap_high))
        
        multipliers[flag] = capped
        
        logger.info(f"Spike flag '{flag}': {len(rows)} obs, raw={raw:.3f}, shrunk={shrunk:.3f}, capped={capped:.3f}")
    
    return multipliers


def apply_spike_overlay(
    df_forecast: pd.DataFrame,
    df_spike_flags: pd.DataFrame,
    multipliers: Dict[str, float],
    id_col: str = "ds"
) -> pd.DataFrame:
    """
    Apply a SINGLE overlay multiplier per day.
    
    FIXED: If multiple spike flags are active on the same day, use the maximum
    multiplier (prevents compounding from overlapping flags like is_black_friday
    + is_day_after_thanksgiving which are identical).
    
    Parameters
    ----------
    df_forecast : pd.DataFrame
        Forecast with date and quantile columns (p50, p80, p90)
        Accepts: ds/target_date as date column
    df_spike_flags : pd.DataFrame
        Spike flags with date and is_* columns
    multipliers : Dict[str, float]
        Multipliers for each spike flag
    id_col : str
        Date column name (default: "ds")
        
    Returns
    -------
    pd.DataFrame
        Forecast with overlay applied
    """
    df = df_forecast.copy()
    
    # Normalize forecast date column
    forecast_date_col = id_col
    if id_col not in df.columns:
        if "target_date" in df.columns:
            forecast_date_col = "target_date"
        else:
            raise ValueError(f"df_forecast missing '{id_col}' or 'target_date'")
    
    # Normalize spike flags date column
    flags_date_col = id_col
    if id_col not in df_spike_flags.columns:
        if "target_date" in df_spike_flags.columns:
            flags_date_col = "target_date"
        else:
            raise ValueError(f"df_spike_flags missing '{id_col}' or 'target_date'")
    
    # Merge spike flags (handle different column names)
    flag_cols = list(multipliers.keys())
    if forecast_date_col == flags_date_col:
        df = df.merge(df_spike_flags[[flags_date_col] + flag_cols], on=forecast_date_col, how="left").fillna(0)
    else:
        # Rename to match before merge
        df_flags_temp = df_spike_flags[[flags_date_col] + flag_cols].copy()
        df_flags_temp = df_flags_temp.rename(columns={flags_date_col: forecast_date_col})
        df = df.merge(df_flags_temp, on=forecast_date_col, how="left").fillna(0)
    
    # Build per-row multiplier = max(multiplier for any active flag)
    # This prevents compounding when multiple flags are active
    mult = np.ones(len(df), dtype=float)
    
    for flag, m in multipliers.items():
        if flag not in df.columns:
            logger.warning(f"Spike flag '{flag}' not found in forecast, skipping")
            continue
        
        active = df[flag].astype(int).values == 1
        mult = np.where(active, np.maximum(mult, m), mult)
        
        n_active = active.sum()
        if n_active > 0:
            logger.info(f"Spike flag '{flag}': {n_active} days active, multiplier={m:.3f}")
    
    df["overlay_multiplier"] = mult
    
    # Apply to quantile columns
    for q in ["p50", "p80", "p90"]:
        if q in df.columns:
            df[q] = df[q] * df["overlay_multiplier"]
    
    n_adjusted = (mult > 1.0).sum()
    logger.info(f"Applied overlay to {n_adjusted} days (multipliers > 1.0)")
    
    return df


def generate_oof_overlay_report(
    multipliers: Dict[str, float],
    df_forecast: pd.DataFrame,
    output_path: str
) -> None:
    """
    Generate a report of OOF overlay multipliers and affected dates.
    
    Parameters
    ----------
    multipliers : Dict[str, float]
        Multipliers for each spike flag
    df_forecast : pd.DataFrame
        Forecast with overlay applied (must have overlay_multiplier column)
    output_path : str
        Path to save report
    """
    report = []
    report.append("# OOF Spike Overlay Report")
    report.append("")
    report.append("## Multipliers by Spike Flag")
    report.append("")
    report.append("| Spike Flag | Multiplier |")
    report.append("|------------|------------|")
    
    for flag, mult in sorted(multipliers.items(), key=lambda x: x[1], reverse=True):
        report.append(f"| {flag} | {mult:.3f}x |")
    
    report.append("")
    report.append("## Affected Dates")
    report.append("")
    
    if "overlay_multiplier" in df_forecast.columns:
        affected = df_forecast[df_forecast["overlay_multiplier"] > 1.0].copy()
        
        if len(affected) > 0:
            report.append(f"Total days with overlay: {len(affected)}")
            report.append("")
            report.append("| Date | Multiplier | P50 Before | P50 After |")
            report.append("|------|------------|------------|-----------|")
            
            for _, row in affected.head(20).iterrows():
                date = row["ds"] if "ds" in row else row.name
                mult = row["overlay_multiplier"]
                p50_after = row["p50"] if "p50" in row else "N/A"
                p50_before = p50_after / mult if p50_after != "N/A" else "N/A"
                
                if p50_after != "N/A":
                    report.append(f"| {date} | {mult:.3f}x | ${p50_before:,.0f} | ${p50_after:,.0f} |")
                else:
                    report.append(f"| {date} | {mult:.3f}x | N/A | N/A |")
        else:
            report.append("No dates with overlay applied (all multipliers = 1.0)")
    else:
        report.append("Overlay not applied (overlay_multiplier column not found)")
    
    with open(output_path, 'w') as f:
        f.write('\n'.join(report))
    
    logger.info(f"OOF overlay report saved to {output_path}")
