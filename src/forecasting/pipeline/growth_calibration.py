"""
Growth calibration layer for aligning forecast totals with expected YoY growth.

V5.2: Monthly growth calibration mode added to fix seasonal allocation problems.
With only 13 months of data, the model's seasonal shape can be wrong even when
annual total is correct. Monthly mode forces each month to hit +10% YoY while
preserving spike-day corrections.

Key features:
- Config-driven (target_yoy growth rate)
- Two modes: "annual" (single scale) or "monthly" (per-month scales)
- Applies to non-spike days only (preserves peak corrections)
- Scales forecast to match target totals
- Leakage-safe for backtests (uses only data <= cutoff)
"""

import logging
from typing import List, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def apply_growth_calibration(
    df_forecast: pd.DataFrame,
    df_history: pd.DataFrame,
    target_yoy_rate: float = 0.10,
    excluded_spike_flags: List[str] | None = None,
    mode: str = "annual",
    min_scale: float = 0.70,
    max_scale: float = 1.30,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Apply growth calibration to align forecast with target YoY growth.

    Two modes:
    - "annual": Single scale factor for all non-spike days (V5.1 behavior)
    - "monthly": Per-month scale factors to hit target growth for each month

    Monthly mode fixes seasonal allocation problems:
    - Ensures each month grows by target_yoy_rate (e.g., +10%)
    - Prevents winter over-prediction and summer under-prediction
    - Preserves spike-day corrections (excluded from scaling)

    Args:
        df_forecast: Forecast dataframe with ds, p50, p80, p90, spike flags
        df_history: Historical actuals with ds, y columns
        target_yoy_rate: Target year-over-year growth (e.g., 0.10 for +10%)
        excluded_spike_flags: Spike flags to exclude from scaling (preserve peaks)
        mode: "annual" or "monthly"
        min_scale: Minimum allowed scale factor (safety bound)
        max_scale: Maximum allowed scale factor (safety bound)

    Returns:
        Tuple of (calibrated forecast DataFrame, calibration log DataFrame)
    """
    # Make copies to avoid modifying inputs
    df = df_forecast.copy()
    df["ds"] = pd.to_datetime(df["ds"])

    df_hist = df_history.copy()
    df_hist["ds"] = pd.to_datetime(df_hist["ds"])

    # Default excluded spike flags (if not provided)
    if excluded_spike_flags is None:
        excluded_spike_flags = [
            "is_black_friday",
            "is_year_end_week",
            "is_memorial_day",
            "is_labor_day",
            "is_independence_day",
            "is_christmas_eve",
            "is_day_after_christmas",
        ]

    # Get baseline year (most recent COMPLETE year in history)
    max_date = df_hist["ds"].max()
    max_year = max_date.year

    # If max_date is not Dec 31, use previous year as baseline
    if max_date.month == 12 and max_date.day == 31:
        baseline_year = max_year
    else:
        baseline_year = max_year - 1
        logger.info(
            f"Max date {max_date} is not Dec 31, using baseline_year={baseline_year} (last complete year)"
        )

    df_hist_year = df_hist[df_hist["ds"].dt.year == baseline_year].copy()

    logger.info(
        f"Growth calibration mode={mode}, baseline_year={baseline_year}, target_yoy={target_yoy_rate:+.1%}"
    )

    # Identify excluded days (spike flags + closed days)
    df["is_excluded"] = False
    for flag in excluded_spike_flags:
        if flag in df.columns:
            df["is_excluded"] |= df[flag]

    # Also exclude closed days
    if "is_closed" in df.columns:
        df["is_excluded"] |= df["is_closed"]

    # Save before state for logging
    df_before = df[["ds", "p50", "p80", "p90"]].copy()
    df_before.columns = ["ds", "p50_before", "p80_before", "p90_before"]

    # Apply calibration based on mode
    if mode == "annual":
        df = _apply_annual_calibration(df, df_hist_year, target_yoy_rate, min_scale, max_scale)
    elif mode == "monthly":
        df = _apply_monthly_calibration(df, df_hist_year, target_yoy_rate, min_scale, max_scale)
    else:
        raise ValueError(f"Invalid mode: {mode}. Must be 'annual' or 'monthly'")

    # Build calibration log
    df_log = df[["ds", "is_excluded"]].copy()
    df_log["month"] = df_log["ds"].dt.month
    df_log = df_log.merge(df_before, on="ds", how="left")
    df_log["p50_after"] = df["p50"]
    df_log["p80_after"] = df["p80"]
    df_log["p90_after"] = df["p90"]
    df_log["calibration_scale"] = df["calibration_scale"]
    df_log["mode"] = mode
    df_log["baseline_year"] = baseline_year

    # Clean up temporary columns
    df = df.drop(columns=["is_excluded"])

    return df, df_log


def _apply_annual_calibration(
    df: pd.DataFrame,
    df_hist_year: pd.DataFrame,
    target_yoy_rate: float,
    min_scale: float,
    max_scale: float,
) -> pd.DataFrame:
    """Apply single scale factor to all non-excluded days."""

    # Compute baseline total (exclude closed days if present)
    if "is_closed" in df_hist_year.columns:
        baseline_total = df_hist_year[~df_hist_year["is_closed"]]["y"].sum()
    else:
        baseline_total = df_hist_year["y"].sum()

    if baseline_total <= 0:
        logger.warning("Baseline total is zero or negative, skipping calibration")
        df["calibration_scale"] = 1.0
        return df

    # Compute target total
    target_total = baseline_total * (1 + target_yoy_rate)

    # Compute current forecast totals
    current_total_excluded = df[df["is_excluded"]]["p50"].sum()
    current_total_nonexcluded = df[~df["is_excluded"]]["p50"].sum()

    if current_total_nonexcluded <= 0:
        logger.warning("No non-excluded days to calibrate, skipping")
        df["calibration_scale"] = 1.0
        return df

    # Compute scale factor
    # target_total = scale * current_nonexcluded + current_excluded
    # scale = (target_total - current_excluded) / current_nonexcluded
    target_nonexcluded_total = target_total - current_total_excluded
    raw_scale = target_nonexcluded_total / current_total_nonexcluded
    clamped_scale = np.clip(raw_scale, min_scale, max_scale)

    if raw_scale != clamped_scale:
        logger.warning(f"Annual scale clamped: raw={raw_scale:.3f}, clamped={clamped_scale:.3f}")

    # Apply scaling
    mask_nonexcluded = ~df["is_excluded"]
    df.loc[mask_nonexcluded, "p50"] *= clamped_scale
    df.loc[mask_nonexcluded, "p80"] *= clamped_scale
    df.loc[mask_nonexcluded, "p90"] *= clamped_scale

    df["calibration_scale"] = 1.0
    df.loc[mask_nonexcluded, "calibration_scale"] = clamped_scale

    logger.info(
        f"Annual calibration: baseline=${baseline_total:,.0f}, target=${target_total:,.0f}, scale={clamped_scale:.3f}"
    )

    return df


def _apply_monthly_calibration(
    df: pd.DataFrame,
    df_hist_year: pd.DataFrame,
    target_yoy_rate: float,
    min_scale: float,
    max_scale: float,
) -> pd.DataFrame:
    """Apply per-month scale factors to hit target growth for each month."""

    # Compute historical monthly totals (baseline year)
    df_hist_year["month"] = df_hist_year["ds"].dt.month

    # Exclude closed days from baseline if present
    if "is_closed" in df_hist_year.columns:
        hist_month_totals = df_hist_year[~df_hist_year["is_closed"]].groupby("month")["y"].sum()
    else:
        hist_month_totals = df_hist_year.groupby("month")["y"].sum()

    # Add month column to forecast
    df["month"] = df["ds"].dt.month

    # Initialize calibration_scale
    df["calibration_scale"] = 1.0

    # Process each month
    for month in range(1, 13):
        if month not in hist_month_totals.index:
            logger.warning(f"Month {month} not in baseline history, skipping")
            continue

        # Target total for this month
        hist_month_total = hist_month_totals[month]
        target_month_total = hist_month_total * (1 + target_yoy_rate)

        # Current forecast totals for this month
        mask_month = df["month"] == month
        mask_month_excluded = mask_month & df["is_excluded"]
        mask_month_nonexcluded = mask_month & ~df["is_excluded"]

        current_excluded_total = df[mask_month_excluded]["p50"].sum()
        current_nonexcluded_total = df[mask_month_nonexcluded]["p50"].sum()

        if current_nonexcluded_total <= 0:
            logger.warning(f"Month {month}: No non-excluded days, skipping")
            continue

        # Compute scale for this month
        # target_month_total = scale_m * current_nonexcluded + current_excluded
        # scale_m = (target_month_total - current_excluded) / current_nonexcluded
        target_nonexcluded_total = target_month_total - current_excluded_total
        raw_scale_m = target_nonexcluded_total / current_nonexcluded_total
        clamped_scale_m = np.clip(raw_scale_m, min_scale, max_scale)

        if raw_scale_m != clamped_scale_m:
            logger.warning(
                f"Month {month}: scale clamped from {raw_scale_m:.3f} to {clamped_scale_m:.3f}"
            )

        # Apply scaling to non-excluded days in this month
        n_scaled = mask_month_nonexcluded.sum()
        df.loc[mask_month_nonexcluded, "p50"] *= clamped_scale_m
        df.loc[mask_month_nonexcluded, "p80"] *= clamped_scale_m
        df.loc[mask_month_nonexcluded, "p90"] *= clamped_scale_m
        df.loc[mask_month_nonexcluded, "calibration_scale"] = clamped_scale_m

        logger.info(
            f"Month {month:2d}: baseline=${hist_month_total:,.0f}, target=${target_month_total:,.0f}, "
            f"scale={clamped_scale_m:.3f}, scaled {n_scaled} days"
        )

    # Verify final totals
    final_total = df["p50"].sum()
    baseline_total = hist_month_totals.sum()
    final_growth = (final_total / baseline_total) - 1

    logger.info(
        f"Monthly calibration complete: final_total=${final_total:,.0f} ({final_growth:+.1%} vs baseline)"
    )

    return df



