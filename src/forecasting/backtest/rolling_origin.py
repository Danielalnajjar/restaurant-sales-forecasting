"""Rolling-origin backtest harness."""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from forecasting.models.baselines import SeasonalNaiveWeekly, WeekdayRollingMedian

logger = logging.getLogger(__name__)


def assign_horizon_bucket(horizon: int) -> str:
    """Assign horizon to bucket."""
    if 1 <= horizon <= 7:
        return "1-7"
    elif 8 <= horizon <= 14:
        return "8-14"
    elif 15 <= horizon <= 30:
        return "15-30"
    elif 31 <= horizon <= 90:
        return "31-90"
    elif 91 <= horizon <= 380:
        return "91-380"
    else:
        return "other"


def compute_metrics(df_preds: pd.DataFrame) -> pd.DataFrame:
    """
    Compute metrics from predictions.

    Parameters
    ----------
    df_preds : pd.DataFrame
        Predictions with columns: horizon, horizon_bucket, p50, y

    Returns
    -------
    pd.DataFrame
        Metrics by horizon bucket
    """
    metrics = []

    for bucket in df_preds["horizon_bucket"].unique():
        df_bucket = df_preds[df_preds["horizon_bucket"] == bucket]

        # wMAPE
        wmape = (df_bucket["p50"] - df_bucket["y"]).abs().sum() / df_bucket["y"].sum()

        # RMSE
        rmse = np.sqrt(((df_bucket["p50"] - df_bucket["y"]) ** 2).mean())

        # Bias
        bias = (df_bucket["p50"].sum() / df_bucket["y"].sum()) - 1

        metrics.append(
            {
                "horizon_bucket": bucket,
                "n": len(df_bucket),
                "wmape": wmape,
                "rmse": rmse,
                "bias": bias,
            }
        )

    return pd.DataFrame(metrics)


def run_baseline_backtest(
    sales_fact_path: str = "data/processed/fact_sales_daily.parquet",
    output_metrics_path: str = "outputs/backtests/metrics_baselines.csv",
    output_preds_path: str = "outputs/backtests/preds_baselines.parquet",
    min_train_days: int = 120,
    step_days: int = 14,
    max_horizon: int = 380,
) -> tuple:
    """
    Run rolling-origin backtest for baseline models.

    Returns
    -------
    tuple
        (df_metrics, df_preds)
    """
    logger.info("Running baseline backtest")

    # Load sales
    df_sales = pd.read_parquet(sales_fact_path)
    ds_min = df_sales["ds"].min()
    ds_max = df_sales["ds"].max()

    logger.info(f"Sales date range: {ds_min} to {ds_max}")

    # Define cutoff dates
    first_cutoff = ds_min + pd.Timedelta(days=min_train_days)
    cutoff_dates = pd.date_range(
        start=first_cutoff, end=ds_max - pd.Timedelta(days=14), freq=f"{step_days}D"
    )

    logger.info(f"Running backtest with {len(cutoff_dates)} cutoffs")

    all_preds = []

    for cutoff_date in cutoff_dates:
        logger.info(f"Cutoff: {cutoff_date}")

        # Train data
        df_train = df_sales[df_sales["ds"] <= cutoff_date]

        # Eval horizon
        h_eval = min(max_horizon, (ds_max - cutoff_date).days)

        if h_eval < 1:
            continue

        # Target dates for evaluation
        target_dates = pd.date_range(
            start=cutoff_date + pd.Timedelta(days=1),
            end=cutoff_date + pd.Timedelta(days=h_eval),
            freq="D",
        ).tolist()

        # Filter to dates that exist in sales (for labels)
        target_dates = [d for d in target_dates if d in df_sales["ds"].values]

        if len(target_dates) == 0:
            continue

        # Seasonal Naive
        model_sn = SeasonalNaiveWeekly()
        model_sn.fit(df_train)
        preds_sn = model_sn.predict(target_dates)
        preds_sn["model_name"] = "seasonal_naive_weekly"
        preds_sn["cutoff_date"] = cutoff_date
        preds_sn["issue_date"] = cutoff_date

        # Weekday Median
        model_wm = WeekdayRollingMedian()
        model_wm.fit(df_train)
        preds_wm = model_wm.predict(target_dates)
        preds_wm["model_name"] = "weekday_rolling_median"
        preds_wm["cutoff_date"] = cutoff_date
        preds_wm["issue_date"] = cutoff_date

        # Combine
        preds = pd.concat([preds_sn, preds_wm], ignore_index=True)

        # Add labels
        preds = preds.merge(
            df_sales[["ds", "y", "is_closed"]].rename(columns={"ds": "target_date"}),
            on="target_date",
            how="left",
        )

        # Add horizon and bucket
        preds["horizon"] = (preds["target_date"] - preds["issue_date"]).dt.days
        preds["horizon_bucket"] = preds["horizon"].apply(assign_horizon_bucket)

        all_preds.append(preds)

    # Combine all predictions
    df_preds = pd.concat(all_preds, ignore_index=True)

    logger.info(f"Total predictions: {len(df_preds)}")

    # Compute metrics per model and bucket
    all_metrics = []

    for model_name in df_preds["model_name"].unique():
        df_model = df_preds[df_preds["model_name"] == model_name]
        metrics = compute_metrics(df_model)
        metrics["model_name"] = model_name
        all_metrics.append(metrics)

    df_metrics = pd.concat(all_metrics, ignore_index=True)

    # Save outputs
    output_metrics_obj = Path(output_metrics_path)
    output_metrics_obj.parent.mkdir(parents=True, exist_ok=True)
    df_metrics.to_csv(output_metrics_path, index=False)
    logger.info(f"Saved metrics to {output_metrics_path}")

    output_preds_obj = Path(output_preds_path)
    output_preds_obj.parent.mkdir(parents=True, exist_ok=True)
    df_preds.to_parquet(output_preds_path, index=False)
    logger.info(f"Saved predictions to {output_preds_path}")

    return df_metrics, df_preds


