"""Sales data ingestion and cleaning."""

import pandas as pd
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


def ingest_sales(
    input_path: str = "data/raw/Sales by day.csv",
    output_path: str = "data/processed/fact_sales_daily.parquet",
    closed_threshold: float = 200.0,
) -> pd.DataFrame:
    """
    Ingest Toast daily sales CSV and produce canonical fact table.
    
    Parameters
    ----------
    input_path : str
        Path to Toast sales CSV
    output_path : str
        Path to output parquet file
    closed_threshold : float
        Sales threshold below which day is considered closed
        
    Returns
    -------
    pd.DataFrame
        Canonical fact table with columns: ds, y, is_closed, data_source, notes
    """
    logger.info(f"Reading sales data from {input_path}")
    
    # Read CSV
    df = pd.read_csv(input_path)
    
    # Identify columns (handle various naming conventions)
    date_col = None
    sales_col = None
    
    for col in df.columns:
        col_lower = col.lower().strip()
        if 'date' in col_lower or col == 'yyyyMMdd':
            date_col = col
        elif 'net' in col_lower and 'sales' in col_lower:
            sales_col = col
    
    if date_col is None or sales_col is None:
        raise ValueError(f"Could not identify date or sales columns. Columns: {df.columns.tolist()}")
    
    logger.info(f"Identified date column: {date_col}, sales column: {sales_col}")
    
    # Extract and clean
    df_clean = pd.DataFrame()
    
    # Parse date (handle yyyyMMdd format)
    if df[date_col].dtype == 'int64' or df[date_col].astype(str).str.match(r'^\d{8}$').all():
        df_clean['ds'] = pd.to_datetime(df[date_col].astype(str), format='%Y%m%d')
    else:
        df_clean['ds'] = pd.to_datetime(df[date_col])
    
    # Parse sales (handle $ signs, commas)
    if df[sales_col].dtype == 'object':
        sales_str = df[sales_col].astype(str).str.replace('$', '').str.replace(',', '').str.strip()
        df_clean['y'] = pd.to_numeric(sales_str, errors='coerce')
    else:
        df_clean['y'] = pd.to_numeric(df[sales_col], errors='coerce')
    
    # Drop rows with missing y
    missing_y = df_clean['y'].isna().sum()
    if missing_y > 0:
        logger.warning(f"Dropping {missing_y} rows with missing/invalid sales values")
        df_clean = df_clean.dropna(subset=['y'])
    
    # Check for duplicates
    duplicates = df_clean['ds'].duplicated().sum()
    if duplicates > 0:
        logger.warning(f"Found {duplicates} duplicate dates. Aggregating by sum.")
        df_clean = df_clean.groupby('ds', as_index=False).agg({'y': 'sum'})
    
    # Add metadata columns
    df_clean['is_closed'] = df_clean['y'] < closed_threshold
    df_clean['data_source'] = 'toast_export'
    df_clean['notes'] = ''
    
    # Sort by date
    df_clean = df_clean.sort_values('ds').reset_index(drop=True)
    
    # Save to parquet
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    df_clean.to_parquet(output_path, index=False)
    logger.info(f"Saved fact table to {output_path}")
    
    return df_clean


def generate_audit_report(
    df: pd.DataFrame,
    output_path: str = "outputs/reports/data_audit_summary.md"
) -> None:
    """
    Generate audit report for sales data.
    
    Parameters
    ----------
    df : pd.DataFrame
        Fact table with ds, y, is_closed columns
    output_path : str
        Path to output markdown report
    """
    # Basic stats
    ds_min = df['ds'].min()
    ds_max = df['ds'].max()
    row_count = len(df)
    closed_count = df['is_closed'].sum()
    
    # Top 10 sales days
    top_10 = df.nlargest(10, 'y')[['ds', 'y']].copy()
    top_10['ds'] = top_10['ds'].dt.strftime('%Y-%m-%d')
    
    # Check for missing dates
    date_range = pd.date_range(start=ds_min, end=ds_max, freq='D')
    missing_dates = date_range.difference(df['ds'])
    
    # Build report
    report = f"""# Sales Data Audit Summary

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Overview

- **Date Range**: {ds_min.strftime('%Y-%m-%d')} to {ds_max.strftime('%Y-%m-%d')}
- **Total Days**: {row_count}
- **Closed Days** (sales < $200): {closed_count}
- **Open Days**: {row_count - closed_count}

## Top 10 Sales Days

| Date | Net Sales |
|------|-----------|
"""
    
    for _, row in top_10.iterrows():
        report += f"| {row['ds']} | ${row['y']:,.2f} |\n"
    
    report += f"\n## Missing Dates\n\n"
    if len(missing_dates) > 0:
        report += f"Found {len(missing_dates)} missing dates in the range:\n\n"
        for date in missing_dates[:20]:  # Show first 20
            report += f"- {date.strftime('%Y-%m-%d')}\n"
        if len(missing_dates) > 20:
            report += f"\n... and {len(missing_dates) - 20} more\n"
    else:
        report += "No missing dates found. Data is continuous.\n"
    
    report += f"\n## Sales Distribution\n\n"
    report += f"- **Mean**: ${df['y'].mean():,.2f}\n"
    report += f"- **Median**: ${df['y'].median():,.2f}\n"
    report += f"- **Min**: ${df['y'].min():,.2f}\n"
    report += f"- **Max**: ${df['y'].max():,.2f}\n"
    report += f"- **Std Dev**: ${df['y'].std():,.2f}\n"
    
    # Save report
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    output_path_obj.write_text(report)
    logger.info(f"Saved audit report to {output_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Run ingestion
    df = ingest_sales()
    
    # Generate audit report
    generate_audit_report(df)
    
    print(f"\nIngestion complete!")
    print(f"Date range: {df['ds'].min()} to {df['ds'].max()}")
    print(f"Total days: {len(df)}")
    print(f"Closed days: {df['is_closed'].sum()}")
