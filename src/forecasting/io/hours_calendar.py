"""Hours calendar creation for history and 2026."""

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def calculate_open_minutes(open_time_str: str, close_time_str: str) -> int:
    """Calculate open minutes from time strings."""
    if pd.isna(open_time_str) or pd.isna(close_time_str):
        return 0

    try:
        open_time = datetime.strptime(open_time_str, "%H:%M").time()
        close_time = datetime.strptime(close_time_str, "%H:%M").time()

        # Calculate minutes
        open_mins = open_time.hour * 60 + open_time.minute
        close_mins = close_time.hour * 60 + close_time.minute

        return close_mins - open_mins
    except:
        return 0


def get_default_hours(ds: pd.Timestamp) -> tuple:
    """
    Get default hours for a given date based on day of week.

    Returns (open_time, close_time, open_minutes)
    """
    dow = ds.dayofweek  # Monday=0, Sunday=6
    month = ds.month
    day = ds.day

    # December extended hours: Dec 8-30 for Mon-Thu
    if month == 12 and 8 <= day <= 30 and dow in [0, 1, 2, 3]:  # Mon-Thu
        return "10:00", "21:00", 660

    # Standard hours by day of week
    if dow in [0, 1, 2, 3]:  # Mon-Thu
        return "11:00", "20:00", 540
    elif dow in [4, 5]:  # Fri-Sat
        return "10:00", "21:00", 660
    else:  # Sunday
        return "11:00", "19:00", 480


def build_hours_calendar_2026(
    calendar_path: str = "data/raw/hours_calendar_2026_v2.csv",
    overrides_path: str = "data/raw/hours_overrides_2026_v2.csv",
    output_path: str = "data/processed/hours_calendar_2026.parquet",
) -> pd.DataFrame:
    """
    Build 2026 hours calendar with overrides applied.

    Returns DataFrame with columns: ds, open_time_local, close_time_local, open_minutes, is_closed
    """
    logger.info(f"Building 2026 hours calendar from {calendar_path}")

    # Read base calendar
    df_cal = pd.read_csv(calendar_path)
    df_cal["ds"] = pd.to_datetime(df_cal["ds"])

    # Read overrides
    df_overrides = pd.read_csv(overrides_path)
    df_overrides["ds"] = pd.to_datetime(df_overrides["ds"])

    # Apply overrides (override takes precedence)
    df_cal = df_cal.set_index("ds")
    df_overrides = df_overrides.set_index("ds")

    # Update with overrides
    for col in ["open_time", "close_time", "is_closed", "open_minutes", "notes"]:
        if col in df_overrides.columns:
            df_cal[col].update(df_overrides[col])

    df_cal = df_cal.reset_index()

    # Standardize columns
    df_result = pd.DataFrame()
    df_result["ds"] = df_cal["ds"]
    df_result["open_time_local"] = df_cal["open_time"]
    df_result["close_time_local"] = df_cal["close_time"]
    df_result["open_minutes"] = df_cal["open_minutes"].astype(int)
    df_result["is_closed"] = df_cal["is_closed"].astype(bool)

    # Validate
    assert (df_result["open_minutes"] >= 0).all(), "Found negative open_minutes"
    assert (df_result["is_closed"] == (df_result["open_minutes"] == 0)).all(), "is_closed mismatch"

    # Sort and save
    df_result = df_result.sort_values("ds").reset_index(drop=True)

    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    df_result.to_parquet(output_path, index=False)
    logger.info(f"Saved 2026 hours calendar to {output_path} ({len(df_result)} rows)")

    return df_result


def build_hours_calendar_history(
    sales_fact_path: str = "data/processed/fact_sales_daily.parquet",
    output_path: str = "data/processed/hours_calendar_history.parquet",
) -> pd.DataFrame:
    """
    Build historical hours calendar using default hours and sales data.

    Returns DataFrame with columns: ds, open_time_local, close_time_local, open_minutes, is_closed
    """
    logger.info(f"Building historical hours calendar from {sales_fact_path}")

    # Read sales fact table
    df_sales = pd.read_parquet(sales_fact_path)

    # Build hours for each date
    hours_data = []
    for _, row in df_sales.iterrows():
        ds = row["ds"]

        # Get default hours
        open_time, close_time, open_minutes = get_default_hours(ds)

        # Override if sales indicate closed
        if row["is_closed"]:
            open_time = None
            close_time = None
            open_minutes = 0
            is_closed = True
        else:
            is_closed = False

        hours_data.append(
            {
                "ds": ds,
                "open_time_local": open_time,
                "close_time_local": close_time,
                "open_minutes": open_minutes,
                "is_closed": is_closed,
            }
        )

    df_result = pd.DataFrame(hours_data)

    # Validate
    assert (df_result["open_minutes"] >= 0).all(), "Found negative open_minutes"
    assert (df_result["is_closed"] == (df_result["open_minutes"] == 0)).all(), "is_closed mismatch"

    # Sort and save
    df_result = df_result.sort_values("ds").reset_index(drop=True)

    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    df_result.to_parquet(output_path, index=False)
    logger.info(f"Saved historical hours calendar to {output_path} ({len(df_result)} rows)")

    return df_result


def generate_hours_audit(
    df_2026: pd.DataFrame,
    overrides_path: str = "data/raw/hours_overrides_2026_v2.csv",
    output_path: str = "outputs/reports/hours_audit.md",
) -> None:
    """Generate audit report for hours calendars."""

    # Read overrides for reporting
    df_overrides = pd.read_csv(overrides_path)
    df_overrides["ds"] = pd.to_datetime(df_overrides["ds"])

    # Stats
    closed_count = df_2026["is_closed"].sum()
    min_open = df_2026[df_2026["open_minutes"] > 0]["open_minutes"].min()
    max_open = df_2026["open_minutes"].max()

    # Build report
    report = f"""# Hours Calendar Audit

Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 2026 Calendar Summary

- **Total Days**: {len(df_2026)}
- **Closed Days**: {closed_count}
- **Open Days**: {len(df_2026) - closed_count}
- **Min Open Minutes** (when open): {min_open}
- **Max Open Minutes**: {max_open}

## Closed Days in 2026

"""

    closed_days = df_2026[df_2026["is_closed"]]
    for _, row in closed_days.iterrows():
        report += f"- {row['ds'].strftime('%Y-%m-%d')} ({row['ds'].strftime('%A')})\n"

    report += f"\n## Overrides Applied ({len(df_overrides)} total)\n\n"
    report += "| Date | Day | Open | Close | Minutes | Notes |\n"
    report += "|------|-----|------|-------|---------|-------|\n"

    for _, row in df_overrides.iterrows():
        open_time = row["open_time"] if pd.notna(row["open_time"]) else "Closed"
        close_time = row["close_time"] if pd.notna(row["close_time"]) else ""
        notes = row["notes"] if pd.notna(row["notes"]) else ""
        report += f"| {row['ds'].strftime('%Y-%m-%d')} | {row['ds'].strftime('%a')} | {open_time} | {close_time} | {row['open_minutes']} | {notes} |\n"

    # Save report
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    output_path_obj.write_text(report)
    logger.info(f"Saved hours audit report to {output_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Build 2026 calendar
    df_2026 = build_hours_calendar_2026()

    # Build historical calendar
    df_history = build_hours_calendar_history()

    # Generate audit
    generate_hours_audit(df_2026)

    print("\nHours calendars complete!")
    print(f"2026: {len(df_2026)} days, {df_2026['is_closed'].sum()} closed")
    print(f"History: {len(df_history)} days, {df_history['is_closed'].sum()} closed")
