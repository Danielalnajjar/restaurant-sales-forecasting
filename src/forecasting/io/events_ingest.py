"""Event data ingestion and normalization."""

import pandas as pd
import logging
from pathlib import Path
from datetime import datetime
import unicodedata
import re

logger = logging.getLogger(__name__)


def to_ascii(text: str) -> str:
    """Convert text to ASCII-safe string."""
    if pd.isna(text):
        return ""
    # Normalize unicode
    text = unicodedata.normalize('NFKD', str(text))
    # Remove non-ASCII
    text = text.encode('ascii', 'ignore').decode('ascii')
    return text.strip()


def to_snake_case(text: str) -> str:
    """Convert text to snake_case."""
    if pd.isna(text):
        return ""
    text = str(text).strip()
    # Replace spaces and special chars with underscore
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', '_', text)
    return text.lower()


def ingest_events_2026_exact(
    input_path: str = "data/events/events_2026_exact_dates_clean_v2.csv",
    output_path: str = "data/processed/events_2026_exact.parquet",
) -> pd.DataFrame:
    """
    Ingest and normalize 2026 exact events.
    
    Returns DataFrame with columns:
    - event_name, event_name_ascii, category, proximity, start_date, end_date
    """
    logger.info(f"Reading 2026 exact events from {input_path}")
    
    # Read CSV with encoding handling
    try:
        df = pd.read_csv(input_path, encoding='utf-8-sig')
    except:
        df = pd.read_csv(input_path, encoding='latin1')
    
    # Normalize column names
    df.columns = [to_snake_case(col) for col in df.columns]
    
    # Extract required columns
    df_clean = pd.DataFrame()
    
    # Event name
    if 'event_name_clean' in df.columns:
        df_clean['event_name'] = df['event_name_clean']
    elif 'event_name' in df.columns:
        df_clean['event_name'] = df['event_name']
    else:
        raise ValueError("Could not find event_name column")
    
    # Event name ASCII
    if 'event_name_ascii' in df.columns:
        df_clean['event_name_ascii'] = df['event_name_ascii']
    else:
        df_clean['event_name_ascii'] = df_clean['event_name'].apply(to_ascii)
    
    # Category and proximity
    df_clean['category'] = df.get('category', '')
    df_clean['proximity'] = df.get('proximity', '')
    
    # Dates
    df_clean['start_date'] = pd.to_datetime(df['start_date'])
    df_clean['end_date'] = pd.to_datetime(df['end_date'])
    
    # Validate dates
    invalid_dates = df_clean['start_date'] > df_clean['end_date']
    if invalid_dates.any():
        logger.warning(f"Found {invalid_dates.sum()} rows with start_date > end_date. Fixing...")
        # Swap dates
        mask = invalid_dates
        df_clean.loc[mask, ['start_date', 'end_date']] = df_clean.loc[mask, ['end_date', 'start_date']].values
    
    # Remove duplicates
    before_dedup = len(df_clean)
    df_clean = df_clean.drop_duplicates(subset=['event_name_ascii', 'start_date', 'end_date'])
    after_dedup = len(df_clean)
    if before_dedup != after_dedup:
        logger.info(f"Removed {before_dedup - after_dedup} duplicate rows")
    
    # Sort and save
    df_clean = df_clean.sort_values(['start_date', 'event_name']).reset_index(drop=True)
    
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    df_clean.to_parquet(output_path, index=False)
    logger.info(f"Saved 2026 exact events to {output_path} ({len(df_clean)} rows)")
    
    return df_clean


def ingest_recurring_event_mapping(
    input_path: str = "data/events/recurring_event_mapping_2025_2026_clean.csv",
    output_path: str = "data/processed/recurring_event_mapping.parquet",
) -> pd.DataFrame:
    """
    Ingest and normalize recurring event mapping.
    
    Returns DataFrame with columns:
    - event_family, event_family_ascii, category, proximity,
      start_2025, end_2025, start_2026, end_2026
    """
    logger.info(f"Reading recurring event mapping from {input_path}")
    
    # Read CSV
    try:
        df = pd.read_csv(input_path, encoding='utf-8-sig')
    except:
        df = pd.read_csv(input_path, encoding='latin1')
    
    # Normalize column names
    df.columns = [to_snake_case(col) for col in df.columns]
    
    # Extract required columns
    df_clean = pd.DataFrame()
    
    # Event family
    if 'event_family' in df.columns:
        df_clean['event_family'] = df['event_family']
    else:
        raise ValueError("Could not find event_family column")
    
    # Event family ASCII
    if 'event_family_ascii' in df.columns:
        df_clean['event_family_ascii'] = df['event_family_ascii']
    else:
        df_clean['event_family_ascii'] = df_clean['event_family'].apply(to_ascii)
    
    # Category and proximity
    df_clean['category'] = df.get('category', '')
    df_clean['proximity'] = df.get('proximity', '')
    
    # Dates
    df_clean['start_2025'] = pd.to_datetime(df['start_2025'])
    df_clean['end_2025'] = pd.to_datetime(df['end_2025'])
    df_clean['start_2026'] = pd.to_datetime(df['start_2026'])
    df_clean['end_2026'] = pd.to_datetime(df['end_2026'])
    
    # Validate dates
    invalid_2025 = df_clean['start_2025'] > df_clean['end_2025']
    invalid_2026 = df_clean['start_2026'] > df_clean['end_2026']
    
    if invalid_2025.any():
        logger.warning(f"Found {invalid_2025.sum()} rows with start_2025 > end_2025. Fixing...")
        mask = invalid_2025
        df_clean.loc[mask, ['start_2025', 'end_2025']] = df_clean.loc[mask, ['end_2025', 'start_2025']].values
    
    if invalid_2026.any():
        logger.warning(f"Found {invalid_2026.sum()} rows with start_2026 > end_2026. Fixing...")
        mask = invalid_2026
        df_clean.loc[mask, ['start_2026', 'end_2026']] = df_clean.loc[mask, ['end_2026', 'start_2026']].values
    
    # Remove duplicates
    before_dedup = len(df_clean)
    df_clean = df_clean.drop_duplicates(subset=['event_family_ascii'])
    after_dedup = len(df_clean)
    if before_dedup != after_dedup:
        logger.info(f"Removed {before_dedup - after_dedup} duplicate rows")
    
    # Sort and save
    df_clean = df_clean.sort_values('event_family').reset_index(drop=True)
    
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

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 2026 Exact Events

- **Total Events**: {len(df_exact)}
- **Date Range**: {df_exact['start_date'].min().strftime('%Y-%m-%d')} to {df_exact['end_date'].max().strftime('%Y-%m-%d')}
- **Missing Category**: {df_exact['category'].isna().sum() + (df_exact['category'] == '').sum()}
- **Missing Proximity**: {df_exact['proximity'].isna().sum() + (df_exact['proximity'] == '').sum()}

### Category Distribution

"""
    
    cat_counts = df_exact['category'].value_counts()
    for cat, count in cat_counts.head(10).items():
        report += f"- {cat}: {count}\n"
    
    report += f"\n### Proximity Distribution\n\n"
    prox_counts = df_exact['proximity'].value_counts()
    for prox, count in prox_counts.items():
        report += f"- {prox}: {count}\n"
    
    report += f"\n## Recurring Event Mapping\n\n"
    report += f"- **Total Event Families**: {len(df_recurring)}\n"
    report += f"- **2025 Date Range**: {df_recurring['start_2025'].min().strftime('%Y-%m-%d')} to {df_recurring['end_2025'].max().strftime('%Y-%m-%d')}\n"
    report += f"- **2026 Date Range**: {df_recurring['start_2026'].min().strftime('%Y-%m-%d')} to {df_recurring['end_2026'].max().strftime('%Y-%m-%d')}\n"
    report += f"- **Missing Category**: {df_recurring['category'].isna().sum() + (df_recurring['category'] == '').sum()}\n"
    report += f"- **Missing Proximity**: {df_recurring['proximity'].isna().sum() + (df_recurring['proximity'] == '').sum()}\n"
    
    report += f"\n### Category Distribution\n\n"
    cat_counts_rec = df_recurring['category'].value_counts()
    for cat, count in cat_counts_rec.items():
        report += f"- {cat}: {count}\n"
    
    # Save report
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    output_path_obj.write_text(report)
    logger.info(f"Saved events audit report to {output_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Ingest exact events
    df_exact = ingest_events_2026_exact()
    
    # Ingest recurring mapping
    df_recurring = ingest_recurring_event_mapping()
    
    # Generate audit
    generate_events_audit(df_exact, df_recurring)
    
    print(f"\nEvents ingestion complete!")
    print(f"2026 exact events: {len(df_exact)}")
    print(f"Recurring mappings: {len(df_recurring)}")
