"""Export 2026 forecasts with guardrails and rollups."""

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from forecasting.models.baselines import SeasonalNaiveWeekly, WeekdayRollingMedian
from forecasting.models.chronos2 import Chronos2Model
from forecasting.models.ensemble import EnsembleModel
from forecasting.models.gbm_long import GBMLongHorizon
from forecasting.models.gbm_short import GBMShortHorizon
from forecasting.utils.runtime import forecast_year_from_config

logger = logging.getLogger(__name__)


def _select_baseline_year(df_hist: pd.DataFrame) -> int:
    """
    Select baseline year using the same logic as growth calibration.

    If max_date in history is Dec 31 → baseline_year = max_year
    Else baseline_year = max_year - 1

    Parameters
    ----------
    df_hist : pd.DataFrame
        Historical sales dataframe with 'ds' column

    Returns
    -------
    int
        Baseline year to use
    """
    max_date = pd.to_datetime(df_hist["ds"]).max()
    max_year = max_date.year
    if max_date.month == 12 and max_date.day == 31:
        return max_year
    return max_year - 1


def _to_relpath(absolute_path: str | Path, project_root: Path) -> str:
    """
    Convert absolute path to relative path from project root.

    Per V5.4.3 PHASE 3: Make run_log.json portable.

    Parameters
    ----------
    absolute_path : str or Path
        Absolute path to convert
    project_root : Path
        Project root directory

    Returns
    -------
    str
        Relative path from project root

    Examples
    --------
    >>> _to_relpath("/path/to/project/outputs/forecasts/forecast_daily_2026.csv",
    ...             Path("/path/to/project"))
    'outputs/forecasts/forecast_daily_2026.csv'
    """
    try:
        return str(Path(absolute_path).relative_to(project_root))
    except ValueError:
        # Path is not relative to project_root, return as-is
        return str(absolute_path)


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
    if "target_date" in df.columns and "ds" not in df.columns:
        df = df.rename(columns={"target_date": "ds"})

    # Merge with hours
    df = df.merge(df_hours[["ds", "is_closed"]], on="ds", how="left", suffixes=("", "_hours"))

    # Use is_closed from hours if not already present
    if "is_closed_hours" in df.columns:
        df["is_closed"] = df["is_closed_hours"]
        df = df.drop(columns=["is_closed_hours"])

    # Fill missing is_closed with False
    if "is_closed" not in df.columns:
        df["is_closed"] = False
    df["is_closed"] = df["is_closed"].fillna(False)

    # Closed days: set all quantiles to 0
    df.loc[df["is_closed"], ["p50", "p80", "p90"]] = 0

    # Clamp to non-negative
    df["p50"] = df["p50"].clip(lower=0)
    df["p80"] = df["p80"].clip(lower=0)
    df["p90"] = df["p90"].clip(lower=0)

    # Enforce monotonicity: p50 <= p80 <= p90
    df["p80"] = df[["p50", "p80"]].max(axis=1)
    df["p90"] = df[["p80", "p90"]].max(axis=1)

    return df


def apply_overrides(
    df: pd.DataFrame, overrides_path: str = "data/overrides/demand_overrides.csv"
) -> pd.DataFrame:
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
    df_overrides["ds"] = pd.to_datetime(df_overrides["ds"])

    # Merge and apply overrides
    df = df.merge(df_overrides, on="ds", how="left", suffixes=("", "_override"))

    for q in ["p50", "p80", "p90"]:
        override_col = f"{q}_override"
        if override_col in df.columns:
            df[q] = df[override_col].fillna(df[q])
            df = df.drop(columns=[override_col])

    return df


def generate_forecast(
    config: dict,
    config_path: str | None = None,
    config_hash: str | None = None,
    sales_fact_path: str = "data/processed/fact_sales_daily.parquet",
    hours_2026_path: str | None = None,
    events_2026_path: str | None = None,
    hours_history_path: str = "data/processed/hours_calendar_history.parquet",
    events_history_path: str = "data/processed/features/events_daily_history.parquet",
    inf_short_path: str | None = None,
    inf_long_path: str | None = None,
    ensemble_weights_path: str = "outputs/models/ensemble_weights.csv",
    output_daily_path: str | None = None,
    output_ordering_path: str | None = None,
    output_scheduling_path: str | None = None,
) -> pd.DataFrame:
    """
    Generate final forecast with ensemble, guardrails, and rollups.

    Returns
    -------
    pd.DataFrame
        Daily forecast for configured period
    """
    from pathlib import Path

    from forecasting.utils.runtime import find_project_root, forecast_slug, get_forecast_window

    forecast_start, forecast_end = get_forecast_window(config)
    forecast_year = pd.Timestamp(forecast_start).year
    slug = forecast_slug(forecast_start, forecast_end)

    logger.info(f"Generating forecast for {forecast_start} to {forecast_end} (slug: {slug})")

    # Build output paths from slug if not provided
    root = find_project_root()
    outputs_dir = root / "outputs"
    forecasts_dir = outputs_dir / "forecasts"
    reports_dir = outputs_dir / "reports"
    data_dir = root / "data" / "processed"

    if hours_2026_path is None:
        hours_2026_path = str(data_dir / f"hours_calendar_{slug}.parquet")
    if events_2026_path is None:
        events_2026_path = str(data_dir / "features" / f"events_daily_{slug}.parquet")
    if inf_short_path is None:
        inf_short_path = str(data_dir / f"inference_features_short_{slug}.parquet")
    if inf_long_path is None:
        inf_long_path = str(data_dir / f"inference_features_long_{slug}.parquet")
    if output_daily_path is None:
        output_daily_path = str(forecasts_dir / f"forecast_daily_{slug}.csv")
    if output_ordering_path is None:
        output_ordering_path = str(forecasts_dir / f"rollups_ordering_{slug}.csv")
    if output_scheduling_path is None:
        output_scheduling_path = str(forecasts_dir / f"rollups_scheduling_{slug}.csv")

    # Get training data paths from config (or use defaults)
    train_short_path = config["paths"].get(
        "processed_train_short", "data/processed/train_short.parquet"
    )
    train_long_path = config["paths"].get(
        "processed_train_long", "data/processed/train_long.parquet"
    )

    # Load data
    df_sales = pd.read_parquet(sales_fact_path)
    df_hours_2026 = pd.read_parquet(hours_2026_path)
    df_events_2026 = pd.read_parquet(events_2026_path)
    df_hours_history = pd.read_parquet(hours_history_path)
    df_events_history = pd.read_parquet(events_history_path)

    issue_date = df_sales["ds"].max()
    data_through = issue_date.strftime("%Y-%m-%d")

    logger.info(f"Issue date: {issue_date}")

    # Generate model predictions
    model_predictions = {}

    # Ensure datetime types
    df_sales["ds"] = pd.to_datetime(df_sales["ds"])
    df_hours_2026["ds"] = pd.to_datetime(df_hours_2026["ds"])

    # Baselines (provide full 2026 coverage so ensemble weights apply correctly)
    logger.info("Generating baseline predictions...")
    target_dates = df_hours_2026["ds"].sort_values().tolist()

    sn = SeasonalNaiveWeekly()
    sn.fit(df_sales)
    preds_sn = sn.predict(target_dates)
    preds_sn["horizon"] = (preds_sn["target_date"] - issue_date).dt.days
    model_predictions["seasonal_naive_weekly"] = preds_sn

    wm = WeekdayRollingMedian()
    wm.fit(df_sales)
    preds_wm = wm.predict(target_dates)
    preds_wm["horizon"] = (preds_wm["target_date"] - issue_date).dt.days
    model_predictions["weekday_rolling_median"] = preds_wm

    # GBM Short (H=1-14)
    logger.info("Generating GBM short predictions...")
    df_inf_short = pd.read_parquet(inf_short_path)

    if len(df_inf_short) > 0:
        model_short = GBMShortHorizon()

        # Train on full history
        df_train_short = pd.read_parquet(train_short_path)
        model_short.fit(df_train_short)

        preds_short = model_short.predict(df_inf_short)
        preds_short["horizon"] = (preds_short["target_date"] - issue_date).dt.days
        model_predictions["gbm_short"] = preds_short

    # GBM Long (H=15-380)
    logger.info("Generating GBM long predictions...")
    df_inf_long = pd.read_parquet(inf_long_path)

    if len(df_inf_long) > 0:
        model_long = GBMLongHorizon()

        # Train on full history
        df_train_long = pd.read_parquet(train_long_path)
        model_long.fit(df_train_long)

        preds_long = model_long.predict(df_inf_long)
        preds_long["horizon"] = (preds_long["target_date"] - issue_date).dt.days
        model_predictions["gbm_long"] = preds_long

    # Chronos-2 (H=1-90)
    logger.info("Generating Chronos-2 predictions...")
    try:
        model_chronos = Chronos2Model(prediction_length=90)
        model_chronos.fit(df_sales)

        if model_chronos.model is not None:
            preds_chronos = model_chronos.predict()

            if len(preds_chronos) > 0:
                preds_chronos["horizon"] = (preds_chronos["target_date"] - issue_date).dt.days
                # Only use Chronos for forecast year dates
                preds_chronos = preds_chronos[preds_chronos["target_date"].dt.year == forecast_year]
                model_predictions["chronos2"] = preds_chronos
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
    ensemble.models = df_weights["model_name"].unique().tolist()
    ensemble.weights = {}

    for bucket in df_weights["horizon_bucket"].unique():
        df_bucket_weights = df_weights[df_weights["horizon_bucket"] == bucket]
        ensemble.weights[bucket] = dict(
            zip(df_bucket_weights["model_name"], df_bucket_weights["weight"])
        )

    df_forecast = ensemble.predict(model_predictions)

    # --- V5.1: Standardize date column for all downstream post-processing ---
    if "target_date" in df_forecast.columns and "ds" not in df_forecast.columns:
        df_forecast = df_forecast.rename(columns={"target_date": "ds"})
    df_forecast["ds"] = pd.to_datetime(df_forecast["ds"])
    logger.info(f"Forecast dataframe standardized: {len(df_forecast)} rows with 'ds' column")

    # Apply spike uplift overlay (REWRITTEN in V5.0)
    # Replaces OOF overlay with improved matched-baseline approach
    # Key fixes: min_observations=1, matched baseline (DOW+month), non-compounding
    logger.info("Spike uplift overlay: ENABLED (V5.0 matched baseline)")
    ENABLE_SPIKE_UPLIFT = True

    if ENABLE_SPIKE_UPLIFT:
        try:
            from forecasting.features.spike_days import add_spike_day_features
            from forecasting.features.spike_uplift import (
                apply_spike_uplift_overlay,
                compute_spike_uplift_priors,
                save_spike_uplift_log,
            )

            # Add spike-day features to historical sales
            df_sales_with_flags = add_spike_day_features(df_sales.copy())

            # Compute uplift priors from historical sales
            # V5.0: Uses matched baseline (DOW+month), min_observations=1
            # V5.1: Tuned shrinkage (0.25) and max_multiplier (1.6) per ChatGPT 5.2 Pro
            # V5.4: Parameters from config
            spike_config = config.get("spike_uplift", {})
            df_uplift = compute_spike_uplift_priors(
                df_sales=df_sales_with_flags,
                ds_max=None,  # Use all available data for production forecast
                min_observations=spike_config.get("min_observations", 1),
                shrinkage_factor=spike_config.get("shrinkage_factor", 0.25),
                max_multiplier=spike_config.get("max_multiplier", 1.6),
            )

            logger.info(f"Computed spike uplift priors for {len(df_uplift)} flags")

            # Save priors for transparency
            df_uplift.to_csv("outputs/models/spike_uplift_priors.csv", index=False)

            # V5.1: Add spike flags directly from ds (no join; deterministic)
            df_forecast = add_spike_day_features(df_forecast)

            # Ensure the flags referenced by priors exist on df_forecast
            spike_flags_available = [
                f for f in df_uplift["spike_flag"].tolist() if f in df_forecast.columns
            ]
            logger.info(f"Spike flags available on forecast: {spike_flags_available}")

            # Apply uplift overlay to forecast
            # V5.0: Non-compounding (uses max multiplier)
            df_forecast = apply_spike_uplift_overlay(df_forecast=df_forecast, df_uplift=df_uplift)

            # V5.1: Check if overlay actually applied
            n_adjusted = (df_forecast.get("adjustment_multiplier", pd.Series([1.0])) != 1.0).sum()
            if n_adjusted == 0:
                logger.warning(
                    "Spike uplift applied to 0 days — expected >0. Check spike flags / date alignment."
                )
            else:
                logger.info(f"Spike uplift applied to {n_adjusted} days.")

                # Ensure is_closed is in df_forecast before saving log (Step 6 requirement)
                if "is_closed" not in df_forecast.columns:
                    if "is_closed" in df_hours_2026.columns:
                        df_forecast = df_forecast.merge(
                            df_hours_2026[["ds", "is_closed"]], on="ds", how="left"
                        )
                        df_forecast["is_closed"] = df_forecast["is_closed"].fillna(False)

                # Save adjustment log (slugged + stable pointer)
                spike_log_path_slug = reports_dir / f"spike_uplift_log_{slug}.csv"
                save_spike_uplift_log(df_forecast=df_forecast, output_path=str(spike_log_path_slug))
                # Per V5.4.3 PHASE 4: Write stable pointer as exact copy of slugged log
                spike_log_path_stable = reports_dir / "spike_uplift_log.csv"
                import shutil

                shutil.copy2(spike_log_path_slug, spike_log_path_stable)
                logger.info(f"Copied {spike_log_path_slug.name} to {spike_log_path_stable.name}")
                logger.info("Spike uplift overlay applied successfully (V5.4.3)")

        except Exception as e:
            logger.error(f"Spike uplift overlay failed: {e}")
            logger.warning("Continuing without spike uplift (forecasts may under-predict peaks)")
            # Don't raise - allow pipeline to continue without uplift

    # V5.1: Apply guardrails FIRST (before growth calibration)
    # This ensures closed days are set to 0 before calibration computes totals
    logger.info("Applying guardrails (pre-calibration)...")
    df_forecast = apply_guardrails(df_forecast, df_hours_2026)

    # Apply growth calibration (V5.2: MONTHLY MODE)
    # V5.1: Applied AFTER guardrails so closures are already enforced
    # V5.2: Monthly mode fixes seasonal allocation (Jan too high, Jul too low)
    # Aligns forecast total with target YoY growth (from config)
    # Applied AFTER spike uplift to preserve peak corrections
    ENABLE_GROWTH_CALIBRATION = config.get("growth_calibration", {}).get("enabled", True)
    TARGET_YOY_GROWTH = config.get("growth_calibration", {}).get("target_yoy_rate", 0.10)

    # Track calibration mode for run_log
    calibration_mode_used = "none"

    if ENABLE_GROWTH_CALIBRATION:
        try:
            from forecasting.pipeline.growth_calibration import apply_growth_calibration

            if len(df_sales) > 0:
                # V5.2: Get excluded spike flags from spike priors (not hardcoded)
                # This ensures growth calibration excludes exactly the days that spike uplift adjusted
                if ENABLE_SPIKE_UPLIFT and "df_uplift" in locals():
                    excluded_spike_flags = df_uplift["spike_flag"].tolist()
                    logger.info(
                        f"Excluding {len(excluded_spike_flags)} spike flags from growth calibration: {excluded_spike_flags}"
                    )
                else:
                    # Fallback if spike uplift disabled
                    excluded_spike_flags = [
                        "is_black_friday",
                        "is_year_end_week",
                        "is_memorial_day",
                        "is_labor_day",
                        "is_independence_day",
                        "is_christmas_eve",
                        "is_day_after_christmas",
                    ]
                    logger.warning("Spike uplift not available, using fallback excluded flags")

                # V5.2: Apply MONTHLY growth calibration
                # V5.4: Parameters from config
                growth_config = config.get("growth_calibration", {})
                calibration_mode_used = growth_config.get("mode", "monthly")
                df_forecast, df_growth_log = apply_growth_calibration(
                    df_forecast=df_forecast,
                    df_history=df_sales,
                    target_yoy_rate=TARGET_YOY_GROWTH,
                    excluded_spike_flags=excluded_spike_flags,
                    mode=calibration_mode_used,
                    min_scale=growth_config.get("min_scale", 0.80),
                    max_scale=growth_config.get("max_scale", 1.25),
                )

                # Save calibration log (slugged + stable pointer)
                growth_log_path_slug = reports_dir / f"growth_calibration_log_{slug}.csv"
                df_growth_log.to_csv(growth_log_path_slug, index=False)
                # Per V5.4.3 PHASE 4: Write stable pointer as exact copy
                growth_log_path_stable = reports_dir / "growth_calibration_log.csv"
                import shutil

                shutil.copy2(growth_log_path_slug, growth_log_path_stable)
                logger.info(f"Growth calibration log saved: {growth_log_path_slug} (V5.4.3)")

                # V5.2: Generate monthly calibration scales summary
                # V5.4.5: Compute forecast_year and baseline_year (year-agnostic)
                forecast_year = forecast_year_from_config(config)
                baseline_year = _select_baseline_year(df_sales)

                df_monthly_scales = (
                    df_growth_log[~df_growth_log["is_excluded"]]
                    .groupby("month")
                    .agg({"calibration_scale": "first", "p50_before": "sum", "p50_after": "sum"})
                    .reset_index()
                )
                df_monthly_scales.columns = [
                    "month",
                    "month_scale",
                    "forecast_nonspike_total_before",
                    "forecast_nonspike_total_after",
                ]

                # Add baseline and target totals (year-agnostic column names)
                df_sales["month"] = pd.to_datetime(df_sales["ds"]).dt.month
                df_sales_baseline = df_sales[
                    pd.to_datetime(df_sales["ds"]).dt.year == baseline_year
                ]
                baseline_month_totals = df_sales_baseline.groupby("month")["y"].sum().reset_index()
                baseline_month_totals.columns = ["month", "baseline_year_month_total"]

                df_monthly_scales = df_monthly_scales.merge(
                    baseline_month_totals, on="month", how="left"
                )
                df_monthly_scales["target_year_month_total"] = df_monthly_scales[
                    "baseline_year_month_total"
                ] * (1 + TARGET_YOY_GROWTH)

                # Add year metadata columns
                df_monthly_scales["baseline_year"] = baseline_year
                df_monthly_scales["forecast_year"] = forecast_year

                # Add spike totals
                spike_totals = (
                    df_growth_log[df_growth_log["is_excluded"]]
                    .groupby("month")["p50_after"]
                    .sum()
                    .reset_index()
                )
                spike_totals.columns = ["month", "forecast_spike_total"]
                df_monthly_scales = df_monthly_scales.merge(spike_totals, on="month", how="left")
                df_monthly_scales["forecast_spike_total"] = df_monthly_scales[
                    "forecast_spike_total"
                ].fillna(0)

                # Compute achieved total
                df_monthly_scales["achieved_month_total_after"] = (
                    df_monthly_scales["forecast_nonspike_total_after"]
                    + df_monthly_scales["forecast_spike_total"]
                )

                # V5.4.5: Reorder columns to standard schema
                df_monthly_scales = df_monthly_scales[
                    [
                        "month",
                        "baseline_year",
                        "forecast_year",
                        "baseline_year_month_total",
                        "target_year_month_total",
                        "forecast_nonspike_total_before",
                        "forecast_nonspike_total_after",
                        "forecast_spike_total",
                        "achieved_month_total_after",
                        "month_scale",
                    ]
                ]

                # Save monthly scales summary (slugged + stable pointer)
                monthly_scales_path_slug = reports_dir / f"monthly_calibration_scales_{slug}.csv"
                df_monthly_scales.to_csv(monthly_scales_path_slug, index=False)
                # Per V5.4.3 PHASE 4: Write stable pointer as exact copy
                monthly_scales_path_stable = reports_dir / "monthly_calibration_scales.csv"
                import shutil

                shutil.copy2(monthly_scales_path_slug, monthly_scales_path_stable)
                logger.info(
                    f"Monthly calibration scales saved: {monthly_scales_path_slug} (V5.4.3)"
                )

                logger.info(
                    f"Growth calibration applied: mode=monthly, target={TARGET_YOY_GROWTH:+.1%}"
                )
            else:
                logger.warning("No historical sales found, skipping growth calibration")

        except Exception:
            logger.exception("Growth calibration failed; continuing without growth calibration")

    # Apply overrides
    df_forecast = apply_overrides(df_forecast)

    # Re-apply guardrails after overrides
    df_forecast = apply_guardrails(df_forecast, df_hours_2026)

    # Add metadata
    df_forecast = df_forecast.merge(df_hours_2026[["ds", "open_minutes"]], on="ds", how="left")
    df_forecast["data_through"] = data_through

    # Sort and select columns
    df_forecast = df_forecast.sort_values("ds")
    df_forecast = df_forecast[
        ["ds", "p50", "p80", "p90", "is_closed", "open_minutes", "data_through"]
    ]

    # Save daily forecast
    Path(output_daily_path).parent.mkdir(parents=True, exist_ok=True)
    df_forecast.to_csv(output_daily_path, index=False)
    logger.info(f"Saved daily forecast to {output_daily_path} ({len(df_forecast)} rows)")

    # Backwards compatibility: Also save legacy 2026 filenames if slug is 2026
    if slug == "2026":
        legacy_daily = forecasts_dir / "forecast_daily_2026.csv"
        if str(legacy_daily) != output_daily_path:
            df_forecast.to_csv(legacy_daily, index=False)
            logger.info(f"Saved legacy 2026 forecast to {legacy_daily}")

    # Save run metadata log
    import json

    from forecasting.utils.runtime import get_git_commit

    # Count spike days adjusted (not closed)
    spike_days_adjusted = 0
    if "n_adjusted" in locals():
        spike_days_adjusted = int(n_adjusted)

    # Per V5.4.3 PHASE 3: Use relative paths in run_log for portability
    run_log = {
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "git_commit": get_git_commit(),
        "project_root": str(root),  # Added for context
        "config_path": _to_relpath(config_path, root) if config_path else "unknown",
        "config_hash": config_hash if config_hash else "unknown",
        "data_through": str(data_through),
        "forecast_start": forecast_start,
        "forecast_end": forecast_end,
        "forecast_days": len(df_forecast),
        "annual_total_p50": float(df_forecast["p50"].sum()),
        "annual_total_p80": float(df_forecast["p80"].sum()),
        "annual_total_p90": float(df_forecast["p90"].sum()),
        "spike_days_adjusted": spike_days_adjusted,
        "calibration_mode": calibration_mode_used,
        "outputs": {
            "forecast_daily": _to_relpath(output_daily_path, root),
            "rollups_ordering": _to_relpath(output_ordering_path, root),
            "rollups_scheduling": _to_relpath(output_scheduling_path, root),
            "run_log": _to_relpath(reports_dir / f"run_log_{slug}.json", root),
        },
    }
    # Save run log with slug
    run_log_path = str(reports_dir / f"run_log_{slug}.json")
    reports_dir.mkdir(parents=True, exist_ok=True)
    with open(run_log_path, "w") as f:
        json.dump(run_log, f, indent=2)
    logger.info(f"Saved run metadata to {run_log_path}")

    # Write a stable pointer to the latest run log (exact copy of slugged log)
    run_log_latest_path = reports_dir / "run_log.json"
    shutil.copy2(run_log_path, run_log_latest_path)
    logger.info(f"Copied {Path(run_log_path).name} to {run_log_latest_path.name}")

    # Generate rollups (aligned to operations)
    logger.info("Generating rollups...")

    snapshot_date = datetime.now().strftime("%Y-%m-%d")

    df_forecast_roll = df_forecast.copy()
    df_forecast_roll["ds"] = pd.to_datetime(df_forecast_roll["ds"])
    df_forecast_roll = df_forecast_roll.sort_values("ds")

    forecast_end = df_forecast_roll["ds"].max()

    def sum_window(start: pd.Timestamp, end: pd.Timestamp) -> dict:
        end_capped = min(end, forecast_end)
        mask = (df_forecast_roll["ds"] >= start) & (df_forecast_roll["ds"] <= end_capped)
        totals = df_forecast_roll.loc[mask, ["p50", "p80", "p90"]].sum()
        notes = []
        if end_capped < end:
            notes.append("window_truncated_at_forecast_end")
        return {
            "snapshot_date": snapshot_date,
            "coverage_start": start.strftime("%Y-%m-%d"),
            "coverage_end": end_capped.strftime("%Y-%m-%d"),
            "p50": float(totals["p50"]),
            "p80": float(totals["p80"]),
            "p90": float(totals["p90"]),
            "notes": ";".join(notes) if notes else "",
        }

    # Ordering rollups:
    # - Sunday order covers Sunday→Saturday (7 days)
    # - Wednesday order covers Wednesday→next Wednesday (8 days, inclusive)
    ordering_rows = []

    # Sundays (dayofweek: Mon=0 ... Sun=6)
    sunday_starts = df_forecast_roll[df_forecast_roll["ds"].dt.dayofweek == 6]["ds"].tolist()
    for start in sunday_starts:
        row = sum_window(start, start + pd.Timedelta(days=6))
        row["notes"] = row["notes"] + (";" if row["notes"] else "") + "order_cycle=sun_sat"
        ordering_rows.append(row)

    # Wednesdays (dayofweek=2)
    wed_starts = df_forecast_roll[df_forecast_roll["ds"].dt.dayofweek == 2]["ds"].tolist()
    for start in wed_starts:
        row = sum_window(start, start + pd.Timedelta(days=7))
        row["notes"] = row["notes"] + (";" if row["notes"] else "") + "order_cycle=wed_wed"
        ordering_rows.append(row)

    df_ordering = pd.DataFrame(ordering_rows).sort_values(["coverage_start", "notes"])
    Path(output_ordering_path).parent.mkdir(parents=True, exist_ok=True)
    df_ordering.to_csv(output_ordering_path, index=False)
    logger.info(f"Saved ordering rollup to {output_ordering_path}")

    # Scheduling rollups:
    # - Schedule week is Wednesday→Tuesday (7 days inclusive)
    scheduling_rows = []
    sched_starts = wed_starts  # Wednesday starts
    for start in sched_starts:
        row = sum_window(start, start + pd.Timedelta(days=6))
        row["notes"] = row["notes"] + (";" if row["notes"] else "") + "schedule_week=wed_tue"
        scheduling_rows.append(row)

    df_scheduling = pd.DataFrame(scheduling_rows).sort_values(["coverage_start"])
    Path(output_scheduling_path).parent.mkdir(parents=True, exist_ok=True)
    df_scheduling.to_csv(output_scheduling_path, index=False)
    logger.info(f"Saved scheduling rollup to {output_scheduling_path}")

    return df_forecast


# Backward-compatible alias (V5.4.2+)
def generate_2026_forecast(
    config: dict,
    config_path: str | None = None,
    config_hash: str | None = None,
    hours_2026_path: str | None = None,
    inference_short_path: str | None = None,
    inference_long_path: str | None = None,
    output_daily_path: str | None = None,
    output_ordering_path: str | None = None,
    output_scheduling_path: str | None = None,
) -> pd.DataFrame:
    """
    Backward-compatible wrapper for generate_forecast().

    Per V5.4.2 PHASE 5: Generic naming with backward compatibility.
    """
    return generate_forecast(
        config=config,
        config_path=config_path,
        config_hash=config_hash,
        hours_2026_path=hours_2026_path,
        inference_short_path=inference_short_path,
        inference_long_path=inference_long_path,
        output_daily_path=output_daily_path,
        output_ordering_path=output_ordering_path,
        output_scheduling_path=output_scheduling_path,
    )
