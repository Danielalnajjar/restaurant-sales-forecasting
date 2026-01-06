"""Daily event feature engineering."""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def _mapping_cols_for_year(year: int) -> tuple[str, str]:
    """Return mapping column names for a given year."""
    return f"start_{year}", f"end_{year}"


def expand_events_to_daily(
    events_df: pd.DataFrame, start_col: str, end_col: str, id_col: str
) -> pd.DataFrame:
    """
    Expand event instances to daily rows.

    Parameters
    ----------
    events_df : pd.DataFrame
        Events with start/end dates
    start_col : str
        Column name for start date
    end_col : str
        Column name for end date
    id_col : str
        Column name for event identifier

    Returns
    -------
    pd.DataFrame
        Daily rows with ds, event_id, and other event attributes
    """
    daily_rows = []

    for _, event in events_df.iterrows():
        start_date = event[start_col]
        end_date = event[end_col]

        # Skip if dates are missing
        if pd.isna(start_date) or pd.isna(end_date):
            continue

        # Generate daily rows
        date_range = pd.date_range(start=start_date, end=end_date, freq="D")

        for ds in date_range:
            row = {"ds": ds, id_col: event[id_col]}
            # Copy other attributes
            for col in ["category", "proximity"]:
                if col in event.index:
                    row[col] = event[col]
            daily_rows.append(row)

    if not daily_rows:
        return pd.DataFrame(columns=["ds", id_col, "category", "proximity"])

    return pd.DataFrame(daily_rows)


def build_events_daily_history(
    sales_fact_path: str = "data/processed/fact_sales_daily.parquet",
    recurring_mapping_path: str = "data/processed/recurring_event_mapping.parquet",
    output_path: str = "data/processed/features/events_daily_history.parquet",
    top_k_families: int = 40,
) -> pd.DataFrame:
    """
    Build daily event features for historical period.

    Returns DataFrame with one row per historical date.
    """
    logger.info("Building historical event features")

    # Load sales fact to get date range
    df_sales = pd.read_parquet(sales_fact_path)
    ds_min = df_sales["ds"].min()
    ds_max = df_sales["ds"].max()

    logger.info(f"Historical date range: {ds_min} to {ds_max}")

    # Load recurring event mapping
    df_recurring = pd.read_parquet(recurring_mapping_path)

    # Expand events for all years present in history (year-aware)
    years = sorted(df_sales["ds"].dt.year.unique())
    all_expanded = []

    for y in years:
        start_col, end_col = _mapping_cols_for_year(int(y))
        if start_col not in df_recurring.columns or end_col not in df_recurring.columns:
            logger.warning(
                f"Recurring mapping missing columns for year {y}: {start_col}/{end_col}. Skipping."
            )
            continue

        logger.info(f"Expanding {y} recurring events to daily rows")
        df_year = expand_events_to_daily(
            df_recurring, start_col=start_col, end_col=end_col, id_col="event_family_ascii"
        )
        # Filter to this year's date range in history
        df_year = df_year[(df_year["ds"] >= ds_min) & (df_year["ds"] <= ds_max)]
        all_expanded.append(df_year)

    # Concatenate all years
    if all_expanded:
        df_daily = pd.concat(all_expanded, ignore_index=True)
        df_daily = df_daily.drop_duplicates(subset=["ds", "event_family_ascii"])
    else:
        logger.warning("No recurring events expanded for any year in history")
        df_daily = pd.DataFrame(columns=["ds", "event_family_ascii"])

    # Create full date range
    all_dates = pd.DataFrame({"ds": pd.date_range(start=ds_min, end=ds_max, freq="D")})

    # Aggregate features by date
    logger.info("Aggregating event features by date")

    # Total events active
    events_total = df_daily.groupby("ds").size().reset_index(name="events_active_total")

    # Events by category
    events_by_cat = df_daily.groupby(["ds", "category"]).size().reset_index(name="count")
    events_by_cat["category_safe"] = (
        events_by_cat["category"].str.lower().str.replace(" ", "_").str.replace("-", "_")
    )
    events_cat_pivot = events_by_cat.pivot_table(
        index="ds", columns="category_safe", values="count", fill_value=0
    ).reset_index()
    events_cat_pivot.columns = ["ds"] + [
        f"events_active_by_category__{col}" for col in events_cat_pivot.columns[1:]
    ]

    # Events by proximity
    events_by_prox = df_daily.groupby(["ds", "proximity"]).size().reset_index(name="count")
    events_by_prox["proximity_safe"] = (
        events_by_prox["proximity"]
        .str.lower()
        .str.replace(" ", "_")
        .str.replace("-", "_")
        .str.replace("/", "_")
    )
    events_prox_pivot = events_by_prox.pivot_table(
        index="ds", columns="proximity_safe", values="count", fill_value=0
    ).reset_index()
    events_prox_pivot.columns = ["ds"] + [
        f"events_active_by_proximity__{col}" for col in events_prox_pivot.columns[1:]
    ]

    # Top-K event families (one-hot)
    logger.info(f"Creating top-{top_k_families} event family one-hots")
    family_days = (
        df_daily.groupby("event_family_ascii")["ds"].nunique().sort_values(ascending=False)
    )
    top_families = family_days.head(top_k_families).index.tolist()

    # Create one-hot for top families
    df_daily_top = df_daily[df_daily["event_family_ascii"].isin(top_families)].copy()
    family_pivot = (
        df_daily_top.groupby(["ds", "event_family_ascii"]).size().reset_index(name="active")
    )
    family_pivot["active"] = 1
    family_pivot = family_pivot.pivot_table(
        index="ds", columns="event_family_ascii", values="active", fill_value=0
    ).reset_index()
    family_pivot.columns = ["ds"] + [f"event_family__{col}" for col in family_pivot.columns[1:]]

    # Merge all features
    df_features = all_dates.copy()
    df_features = df_features.merge(events_total, on="ds", how="left")
    df_features = df_features.merge(events_cat_pivot, on="ds", how="left")
    df_features = df_features.merge(events_prox_pivot, on="ds", how="left")
    df_features = df_features.merge(family_pivot, on="ds", how="left")

    # Fill NaN with 0
    df_features = df_features.fillna(0)

    # Convert to int where appropriate
    for col in df_features.columns:
        if col != "ds":
            df_features[col] = df_features[col].astype(int)

    # Sort
    df_features = df_features.sort_values("ds").reset_index(drop=True)

    # Save
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    df_features.to_parquet(output_path, index=False)
    logger.info(
        f"Saved historical event features to {output_path} ({len(df_features)} rows, {len(df_features.columns)} columns)"
    )

    return df_features


def build_events_daily_forecast(
    config: dict,
    exact_events_path: str | None = None,
    recurring_mapping_path: str = "data/processed/recurring_event_mapping.parquet",
    output_path: str | None = None,
    top_k_families: int = 40,
) -> pd.DataFrame:
    """
    Build daily event features for forecast period.

    Returns DataFrame with one row per day in forecast period.
    """
    from pathlib import Path

    from forecasting.utils.runtime import find_project_root, forecast_slug, get_forecast_window

    forecast_start, forecast_end = get_forecast_window(config)
    slug = forecast_slug(forecast_start, forecast_end)
    logger.info(f"Building event features for {forecast_start} to {forecast_end} (slug: {slug})")

    # Build paths from slug if not provided
    root = find_project_root()
    data_dir = root / "data" / "processed"

    if exact_events_path is None:
        exact_events_path = str(data_dir / f"events_{slug}_exact.parquet")
    if output_path is None:
        output_path = str(data_dir / "features" / f"events_daily_{slug}.parquet")

    # Date range from config
    ds_min = pd.Timestamp(forecast_start)
    ds_max = pd.Timestamp(forecast_end)

    # Load exact events
    df_exact = pd.read_parquet(exact_events_path)

    # Load recurring mapping
    df_recurring = pd.read_parquet(recurring_mapping_path)

    # Expand exact events to daily
    logger.info("Expanding 2026 exact events to daily rows")
    df_daily_exact = expand_events_to_daily(
        df_exact, start_col="start_date", end_col="end_date", id_col="event_name_ascii"
    )
    df_daily_exact["event_family_ascii"] = df_daily_exact[
        "event_name_ascii"
    ]  # Use event name as family

    # Expand recurring events for forecast year (year-aware)
    forecast_year = pd.to_datetime(forecast_start).year
    start_col, end_col = _mapping_cols_for_year(forecast_year)

    if start_col not in df_recurring.columns or end_col not in df_recurring.columns:
        raise ValueError(
            f"Recurring mapping file missing {start_col}/{end_col} for forecast_year={forecast_year}. "
            f"Available columns: {df_recurring.columns.tolist()}"
        )

    logger.info(f"Expanding {forecast_year} recurring events to daily rows")
    df_daily_recurring = expand_events_to_daily(
        df_recurring, start_col=start_col, end_col=end_col, id_col="event_family_ascii"
    )

    # Union both sources (keep all events for debugging/reporting)
    df_daily_all = pd.concat([df_daily_exact, df_daily_recurring], ignore_index=True)
    df_daily_all = df_daily_all.drop_duplicates(subset=["ds", "event_family_ascii"])

    # FIXED V4.2: Use ONLY recurring events for model-facing aggregates
    # This prevents distribution shift (training only saw recurring events)
    # Exact events are kept in df_daily_all for reporting but not used for features
    df_daily = df_daily_recurring.copy()
    logger.info(
        f"Using {len(df_daily_recurring)} recurring event-days for aggregates (excluding {len(df_daily_exact)} exact events to match training)"
    )

    # Create full date range
    all_dates = pd.DataFrame({"ds": pd.date_range(start=ds_min, end=ds_max, freq="D")})

    # Aggregate features by date (FROM RECURRING ONLY)
    logger.info("Aggregating event features by date (recurring events only)")

    # Total events active
    events_total = df_daily.groupby("ds").size().reset_index(name="events_active_total")

    # Events by category
    events_by_cat = df_daily.groupby(["ds", "category"]).size().reset_index(name="count")
    events_by_cat["category_safe"] = (
        events_by_cat["category"].str.lower().str.replace(" ", "_").str.replace("-", "_")
    )
    events_cat_pivot = events_by_cat.pivot_table(
        index="ds", columns="category_safe", values="count", fill_value=0
    ).reset_index()
    events_cat_pivot.columns = ["ds"] + [
        f"events_active_by_category__{col}" for col in events_cat_pivot.columns[1:]
    ]

    # Events by proximity
    events_by_prox = df_daily.groupby(["ds", "proximity"]).size().reset_index(name="count")
    events_by_prox["proximity_safe"] = (
        events_by_prox["proximity"]
        .str.lower()
        .str.replace(" ", "_")
        .str.replace("-", "_")
        .str.replace("/", "_")
    )
    events_prox_pivot = events_by_prox.pivot_table(
        index="ds", columns="proximity_safe", values="count", fill_value=0
    ).reset_index()
    events_prox_pivot.columns = ["ds"] + [
        f"events_active_by_proximity__{col}" for col in events_prox_pivot.columns[1:]
    ]

    # Top-K event families (use same families as history for consistency)
    # Load history to get top families
    history_path = Path(config["paths"]["processed_events_daily_history_path"])
    df_history = pd.read_parquet(history_path)
    family_cols = [col for col in df_history.columns if col.startswith("event_family__")]
    top_families = [col.replace("event_family__", "") for col in family_cols]

    logger.info(f"Using {len(top_families)} event families from history")

    # Create one-hot for top families
    df_daily_top = df_daily[df_daily["event_family_ascii"].isin(top_families)].copy()
    if len(df_daily_top) > 0:
        family_pivot = (
            df_daily_top.groupby(["ds", "event_family_ascii"]).size().reset_index(name="active")
        )
        family_pivot["active"] = 1
        family_pivot = family_pivot.pivot_table(
            index="ds", columns="event_family_ascii", values="active", fill_value=0
        ).reset_index()
        family_pivot.columns = ["ds"] + [f"event_family__{col}" for col in family_pivot.columns[1:]]

        # Add missing families from history (set to 0)
        for fam in top_families:
            col_name = f"event_family__{fam}"
            if col_name not in family_pivot.columns:
                family_pivot[col_name] = 0
    else:
        family_pivot = all_dates.copy()
        for fam in top_families:
            family_pivot[f"event_family__{fam}"] = 0

    # Merge all features
    df_features = all_dates.copy()
    df_features = df_features.merge(events_total, on="ds", how="left")
    df_features = df_features.merge(events_cat_pivot, on="ds", how="left")
    df_features = df_features.merge(events_prox_pivot, on="ds", how="left")
    df_features = df_features.merge(family_pivot, on="ds", how="left")

    # Fill NaN with 0
    df_features = df_features.fillna(0)

    # Convert to int where appropriate
    for col in df_features.columns:
        if col != "ds":
            df_features[col] = df_features[col].astype(int)

    # Sort
    df_features = df_features.sort_values("ds").reset_index(drop=True)

    # Save
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    df_features.to_parquet(output_path, index=False)
    logger.info(
        f"Saved 2026 event features to {output_path} ({len(df_features)} rows, {len(df_features.columns)} columns)"
    )

    return df_features


# Backward-compatible alias (V5.4.2+)
def build_events_daily_2026(config: dict) -> pd.DataFrame:
    """
    Backward-compatible wrapper for build_events_daily_forecast().

    Per V5.4.2 PHASE 5: Generic naming with backward compatibility.

    Parameters
    ----------
    config : dict
        Configuration dictionary

    Returns
    -------
    pd.DataFrame
        Event features for forecast period
    """
    return build_events_daily_forecast(config)
