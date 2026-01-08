"""Event data ingestion and normalization."""

import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def to_ascii(text: str) -> str:
    """Convert text to ASCII-safe string."""
    if pd.isna(text):
        return ""
    # Normalize unicode
    text = unicodedata.normalize("NFKD", str(text))
    # Remove non-ASCII
    text = text.encode("ascii", "ignore").decode("ascii")
    return text.strip()


def to_snake_case(text: str) -> str:
    """Convert text to snake_case."""
    if pd.isna(text):
        return ""
    text = str(text).strip()
    # Replace spaces and special chars with underscore
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", "_", text)
    return text.lower()


def ingest_events_exact(
    input_path: str,
    output_path: str | None = None,
) -> pd.DataFrame:
    """
    Generic ingest for exact events CSV (year-agnostic).

    Reads exact events (one-off events) from CSV.
    Ensures dates are parsed as datetimes.

    Returns DataFrame with columns:
    - event_name, event_name_ascii, category, proximity, start_date, end_date
    """
    logger.info(f"Reading exact events from {input_path}")

    # Default output path if not provided
    if output_path is None:
        output_path = "data/processed/events_2026_exact.parquet"

    # Read CSV with encoding handling
    try:
        df = pd.read_csv(input_path, encoding="utf-8-sig")
    except Exception as e:
        logger.warning(f"UTF-8 encoding failed ({e}), trying latin1")
        df = pd.read_csv(input_path, encoding="latin1")

    # Normalize column names
    df.columns = [to_snake_case(col) for col in df.columns]

    # Extract required columns
    df_clean = pd.DataFrame()

    # Event name
    if "event_name_clean" in df.columns:
        df_clean["event_name"] = df["event_name_clean"]
    elif "event_name" in df.columns:
        df_clean["event_name"] = df["event_name"]
    else:
        raise ValueError("Could not find event_name column")

    # Event name ASCII
    if "event_name_ascii" in df.columns:
        df_clean["event_name_ascii"] = df["event_name_ascii"]
    else:
        df_clean["event_name_ascii"] = df_clean["event_name"].apply(to_ascii)

    # Category and proximity
    df_clean["category"] = df.get("category", "")
    df_clean["proximity"] = df.get("proximity", "")

    # Dates
    df_clean["start_date"] = pd.to_datetime(df["start_date"])
    df_clean["end_date"] = pd.to_datetime(df["end_date"])

    # Validate dates
    invalid_dates = df_clean["start_date"] > df_clean["end_date"]
    if invalid_dates.any():
        logger.warning(f"Found {invalid_dates.sum()} rows with start_date > end_date. Fixing...")
        # Swap dates
        mask = invalid_dates
        df_clean.loc[mask, ["start_date", "end_date"]] = df_clean.loc[
            mask, ["end_date", "start_date"]
        ].values

    # Remove duplicates
    before_dedup = len(df_clean)
    df_clean = df_clean.drop_duplicates(subset=["event_name_ascii", "start_date", "end_date"])
    after_dedup = len(df_clean)
    if before_dedup != after_dedup:
        logger.info(f"Removed {before_dedup - after_dedup} duplicate rows")

    # Sort and save
    df_clean = df_clean.sort_values(["start_date", "event_name"]).reset_index(drop=True)

    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    df_clean.to_parquet(output_path, index=False)
    logger.info(f"Saved exact events to {output_path} ({len(df_clean)} rows)")

    return df_clean


def ingest_events_2026_exact(
    input_path: str = "data/events/events_2026_exact_dates_clean_v2.csv",
    output_path: str = "data/processed/events_2026_exact.parquet",
) -> pd.DataFrame:
    """Backward-compatible wrapper for ingest_events_exact()."""
    return ingest_events_exact(
        input_path=input_path,
        output_path=output_path,
    )


def ingest_recurring_event_mapping(
    input_path: str = "data/events/recurring_event_mapping_2025_2026_clean.csv",
    output_path: str = "data/processed/recurring_event_mapping.parquet",
) -> pd.DataFrame:
    """
    Ingest and normalize recurring event mapping (year-generic via regex).

    Detects year columns dynamically (start_YYYY, end_YYYY) and validates pairs.
    Supports any year range (2025-2030+).

    Returns DataFrame with columns:
    - event_family, event_family_ascii, category, proximity, recurrence_pattern
    - start_YYYY, end_YYYY (for each detected year)
    """
    logger.info(f"Reading recurring event mapping from {input_path}")

    # Read CSV
    try:
        df = pd.read_csv(input_path, encoding="utf-8-sig")
    except Exception as e:
        logger.warning(f"UTF-8 encoding failed ({e}), trying latin1")
        df = pd.read_csv(input_path, encoding="latin1")

    # Normalize column names
    df.columns = [to_snake_case(col) for col in df.columns]
    # Required base columns (only event_family is truly required)
    required = {"event_family"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Recurring mapping missing required columns: {sorted(missing)}")

    # Add optional columns if missing
    if "category" not in df.columns:
        df["category"] = ""
    if "proximity" not in df.columns:
        df["proximity"] = ""
    if "recurrence_pattern" not in df.columns:
        df["recurrence_pattern"] = ""

    # Detect year columns via regex: start_YYYY, end_YYYY
    _YEAR_COL_RE = re.compile(r"^(start|end)_(\d{4})$")
    year_cols = [c for c in df.columns if _YEAR_COL_RE.match(c)]
    years = sorted({int(_YEAR_COL_RE.match(c).group(2)) for c in year_cols})

    if not years:
        raise ValueError(
            "Recurring mapping has no year columns. Expected columns like start_2026/end_2026."
        )

    # Validate start/end pairs and parse datetimes
    for y in years:
        s = f"start_{y}"
        e = f"end_{y}"
        if s not in df.columns or e not in df.columns:
            raise ValueError(f"Recurring mapping missing required pair: {s} and {e}")

        df[s] = pd.to_datetime(df[s], errors="coerce")
        df[e] = pd.to_datetime(df[e], errors="coerce")

    # Normalize categorical fields
    df["event_family"] = df["event_family"].astype(str).str.strip()
    df["category"] = df["category"].astype(str).str.strip()
    df["recurrence_pattern"] = df["recurrence_pattern"].astype(str).str.strip()

    # Create event_family_ascii if missing
    if "event_family_ascii" not in df.columns:
        df["event_family_ascii"] = df["event_family"].apply(to_ascii)

    # Select final columns
    base_cols = [
        "event_family",
        "event_family_ascii",
        "category",
        "proximity",
        "recurrence_pattern",
    ]
    df_clean = df[base_cols + year_cols].copy()

    # Remove duplicates
    before_dedup = len(df_clean)
    df_clean = df_clean.drop_duplicates(subset=["event_family_ascii"])
    after_dedup = len(df_clean)
    if before_dedup != after_dedup:
        logger.info(f"Removed {before_dedup - after_dedup} duplicate rows")

    # Sort and save
    df_clean = df_clean.sort_values("event_family").reset_index(drop=True)

    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    df_clean.to_parquet(output_path, index=False)
    logger.info(f"Saved recurring event mapping to {output_path} ({len(df_clean)} rows)")

    return df_clean


def generate_events_audit(
    df_exact: pd.DataFrame,
    df_recurring: pd.DataFrame,
    output_path: str = "outputs/reports/events_audit.md",
) -> None:
    """Generate audit report for event data."""

    report = f"""# Events Data Audit

Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 2026 Exact Events

- **Total Events**: {len(df_exact)}
- **Date Range**: {df_exact["start_date"].min().strftime("%Y-%m-%d")} to {df_exact["end_date"].max().strftime("%Y-%m-%d")}
- **Missing Category**: {df_exact["category"].isna().sum() + (df_exact["category"] == "").sum()}
- **Missing Proximity**: {df_exact["proximity"].isna().sum() + (df_exact["proximity"] == "").sum()}

### Category Distribution

"""

    cat_counts = df_exact["category"].value_counts()
    for cat, count in cat_counts.head(10).items():
        report += f"- {cat}: {count}\n"

    report += "\n### Proximity Distribution\n\n"
    prox_counts = df_exact["proximity"].value_counts()
    for prox, count in prox_counts.items():
        report += f"- {prox}: {count}\n"

    report += "\n## Recurring Event Mapping\n\n"
    report += f"- **Total Event Families**: {len(df_recurring)}\n"
    report += f"- **2025 Date Range**: {df_recurring['start_2025'].min().strftime('%Y-%m-%d')} to {df_recurring['end_2025'].max().strftime('%Y-%m-%d')}\n"
    report += f"- **2026 Date Range**: {df_recurring['start_2026'].min().strftime('%Y-%m-%d')} to {df_recurring['end_2026'].max().strftime('%Y-%m-%d')}\n"
    report += f"- **Missing Category**: {df_recurring['category'].isna().sum() + (df_recurring['category'] == '').sum()}\n"
    report += f"- **Missing Proximity**: {df_recurring['proximity'].isna().sum() + (df_recurring['proximity'] == '').sum()}\n"

    report += "\n### Category Distribution\n\n"
    cat_counts_rec = df_recurring["category"].value_counts()
    for cat, count in cat_counts_rec.items():
        report += f"- {cat}: {count}\n"

    # Save report
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    output_path_obj.write_text(report)
    logger.info(f"Saved events audit report to {output_path}")
