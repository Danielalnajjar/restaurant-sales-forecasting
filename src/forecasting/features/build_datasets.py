"""Build supervised training datasets and inference features."""

import logging
from pathlib import Path

import pandas as pd

from forecasting.features.feature_builders import (
    build_features_long,
    build_features_short,
)

logger = logging.getLogger(__name__)


def build_train_datasets(
    config: dict,
    sales_fact_path: str = "data/processed/fact_sales_daily.parquet",
    hours_history_path: str = "data/processed/hours_calendar_history.parquet",
    events_history_path: str = "data/processed/features/events_daily_history.parquet",
    output_short_path: str = "data/processed/train_short.parquet",
    output_long_path: str = "data/processed/train_long.parquet",
    short_horizons: list = None,
    long_horizons: list = None,
) -> tuple:
    """
    Build supervised training datasets for short and long horizons.

    Parameters
    ----------
    config : dict
        Configuration dictionary

    Returns
    -------
    tuple
        (df_train_short, df_train_long)
    """
    logger.info("Building supervised training datasets")

    if short_horizons is None:
        short_horizons = config["short_horizons"]
    if long_horizons is None:
        long_horizons = config["long_horizons"]

    # Load data
    df_sales = pd.read_parquet(sales_fact_path)
    df_hours = pd.read_parquet(hours_history_path)
    df_events = pd.read_parquet(events_history_path)

    ds_min = df_sales["ds"].min()
    ds_max = df_sales["ds"].max()

    logger.info(f"Historical date range: {ds_min} to {ds_max}")
    logger.info(f"Short horizons: {min(short_horizons)} to {max(short_horizons)}")
    logger.info(f"Long horizons: {min(long_horizons)} to {max(long_horizons)}")

    # Build supervised rows
    train_rows_short = []
    train_rows_long = []

    # Iterate through issue dates
    issue_dates = df_sales["ds"].values

    for issue_date in issue_dates:
        issue_date_ts = pd.Timestamp(issue_date)

        # Short horizon targets
        for h in short_horizons:
            target_date = issue_date_ts + pd.Timedelta(days=h)

            # Check if label exists
            if target_date > ds_max:
                continue

            label_row = df_sales[df_sales["ds"] == target_date]
            if len(label_row) == 0:
                continue

            # Skip closed days (optional but preferred)
            if label_row.iloc[0]["is_closed"]:
                continue

            train_rows_short.append(
                {
                    "issue_date": issue_date_ts,
                    "target_date": target_date,
                    "horizon": h,
                    "y": label_row.iloc[0]["y"],
                }
            )

        # Long horizon targets
        for h in long_horizons:
            target_date = issue_date_ts + pd.Timedelta(days=h)

            # Check if label exists
            if target_date > ds_max:
                continue

            label_row = df_sales[df_sales["ds"] == target_date]
            if len(label_row) == 0:
                continue

            # Skip closed days
            if label_row.iloc[0]["is_closed"]:
                continue

            train_rows_long.append(
                {
                    "issue_date": issue_date_ts,
                    "target_date": target_date,
                    "horizon": h,
                    "y": label_row.iloc[0]["y"],
                }
            )

    logger.info(f"Generated {len(train_rows_short)} short-horizon training rows")
    logger.info(f"Generated {len(train_rows_long)} long-horizon training rows")

    # Build features for short horizon
    logger.info("Building short-horizon features...")
    df_train_short = pd.DataFrame(train_rows_short)

    if len(df_train_short) > 0:
        # Group by issue_date to build features efficiently
        all_features_short = []

        for issue_date, group in df_train_short.groupby("issue_date"):
            target_dates = group["target_date"].tolist()

            df_features = build_features_short(
                issue_date=issue_date,
                target_dates=target_dates,
                df_sales=df_sales,
                df_hours=df_hours,
                df_events=df_events,
            )

            # Merge with labels
            df_features = df_features.merge(
                group[["target_date", "y"]], on="target_date", how="left"
            )

            all_features_short.append(df_features)

        df_train_short = pd.concat(all_features_short, ignore_index=True)

        # Save
        output_path_obj = Path(output_short_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        df_train_short.to_parquet(output_short_path, index=False)
        logger.info(
            f"Saved short-horizon training data to {output_short_path} ({len(df_train_short)} rows, {len(df_train_short.columns)} columns)"
        )

    # Build features for long horizon
    logger.info("Building long-horizon features...")
    df_train_long = pd.DataFrame(train_rows_long)

    if len(df_train_long) > 0:
        # Group by issue_date to build features efficiently
        all_features_long = []

        for issue_date, group in df_train_long.groupby("issue_date"):
            target_dates = group["target_date"].tolist()

            df_features = build_features_long(
                issue_date=issue_date,
                target_dates=target_dates,
                df_hours=df_hours,
                df_events=df_events,
            )

            # Merge with labels
            df_features = df_features.merge(
                group[["target_date", "y"]], on="target_date", how="left"
            )

            all_features_long.append(df_features)

        df_train_long = pd.concat(all_features_long, ignore_index=True)

        # Save
        output_path_obj = Path(output_long_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        df_train_long.to_parquet(output_long_path, index=False)
        logger.info(
            f"Saved long-horizon training data to {output_long_path} ({len(df_train_long)} rows, {len(df_train_long.columns)} columns)"
        )

    return df_train_short, df_train_long


def build_inference_features_2026(
    config: dict,
    sales_fact_path: str = "data/processed/fact_sales_daily.parquet",
    hours_2026_path: str | None = None,
    events_2026_path: str | None = None,
    output_short_path: str | None = None,
    output_long_path: str | None = None,
) -> tuple:
    """
    Build inference features for forecast period.

    Returns
    -------
    tuple
        (df_inf_short, df_inf_long)
    """
    from pathlib import Path

    from forecasting.utils.runtime import find_project_root, forecast_slug, get_forecast_window

    forecast_start, forecast_end = get_forecast_window(config)
    slug = forecast_slug(forecast_start, forecast_end)
    logger.info(
        f"Building inference features for {forecast_start} to {forecast_end} (slug: {slug})"
    )

    # Build paths from slug if not provided
    root = find_project_root()
    data_dir = root / "data" / "processed"

    if hours_2026_path is None:
        hours_2026_path = str(data_dir / f"hours_calendar_{slug}.parquet")
    if events_2026_path is None:
        events_2026_path = str(data_dir / "features" / f"events_daily_{slug}.parquet")
    if output_short_path is None:
        output_short_path = str(data_dir / f"inference_features_short_{slug}.parquet")
    if output_long_path is None:
        output_long_path = str(data_dir / f"inference_features_long_{slug}.parquet")

    short_horizons = config["short_horizons"]
    long_horizons = config["long_horizons"]

    # Load data
    df_sales = pd.read_parquet(sales_fact_path)
    df_hours = pd.read_parquet(hours_2026_path)
    df_events = pd.read_parquet(events_2026_path)

    # Issue date is last date in history
    issue_date = df_sales["ds"].max()

    logger.info(f"Issue date: {issue_date}")

    # Forecast date range (from config)
    dates_forecast = pd.date_range(start=forecast_start, end=forecast_end, freq="D")
    logger.info(f"Forecast window: {forecast_start} to {forecast_end}")

    # Build short-horizon features (H=1-14)
    logger.info("Building short-horizon inference features...")
    target_dates_short = [
        d for d in dates_forecast if 1 <= (d - issue_date).days <= max(short_horizons)
    ]

    df_inf_short = build_features_short(
        issue_date=issue_date,
        target_dates=target_dates_short,
        df_sales=df_sales,
        df_hours=df_hours,
        df_events=df_events,
    )

    # Save
    output_path_obj = Path(output_short_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    df_inf_short.to_parquet(output_short_path, index=False)
    logger.info(
        f"Saved short-horizon 2026 features to {output_short_path} ({len(df_inf_short)} rows)"
    )

    # Build long-horizon features (H=15-380)
    logger.info("Building long-horizon 2026 features...")
    target_dates_long = [
        d
        for d in dates_forecast
        if min(long_horizons) <= (d - issue_date).days <= max(long_horizons)
    ]

    df_inf_long = build_features_long(
        issue_date=issue_date,
        target_dates=target_dates_long,
        df_hours=df_hours,
        df_events=df_events,
    )

    # Save
    output_path_obj = Path(output_long_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    df_inf_long.to_parquet(output_long_path, index=False)
    logger.info(f"Saved long-horizon 2026 features to {output_long_path} ({len(df_inf_long)} rows)")

    return df_inf_short, df_inf_long


