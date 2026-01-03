"""Event uplift prior computation with rolling/OOF methodology."""

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_weekday_baseline(
    df_sales: pd.DataFrame, target_ds: pd.Timestamp, lookback_weeks: int = 8
) -> float:
    """
    Compute baseline for a given date using median of same weekday over prior weeks.

    Parameters
    ----------
    df_sales : pd.DataFrame
        Sales history with ds, y, is_closed
    target_ds : pd.Timestamp
        Target date
    lookback_weeks : int
        Number of prior same-weekday occurrences to use

    Returns
    -------
    float
        Baseline sales value
    """
    target_dow = target_ds.dayofweek

    # Get prior same-weekday dates
    prior_sales = df_sales[
        (df_sales["ds"] < target_ds)
        & (df_sales["ds"].dt.dayofweek == target_dow)
        & (~df_sales["is_closed"])
    ].sort_values("ds", ascending=False)

    if len(prior_sales) == 0:
        return np.nan

    # Take last N occurrences
    recent_sales = prior_sales.head(lookback_weeks)["y"]

    if len(recent_sales) == 0:
        return np.nan

    return recent_sales.median()


def compute_event_uplift_priors(
    ds_max: str,
    sales_fact_path: str = "data/processed/fact_sales_daily.parquet",
    recurring_mapping_path: str = "data/processed/recurring_event_mapping.parquet",
    shrink_k: float = 10.0,
) -> pd.DataFrame:
    """
    Compute event uplift priors using only data up to ds_max (out-of-fold).

    Parameters
    ----------
    ds_max : str
        Maximum date to use for computing priors (YYYY-MM-DD)
    sales_fact_path : str
        Path to sales fact table
    recurring_mapping_path : str
        Path to recurring event mapping
    shrink_k : float
        Shrinkage parameter (higher = more shrinkage toward prior mean of 1.0)

    Returns
    -------
    pd.DataFrame
        Uplift priors per event family
    """
    logger.info(f"Computing event uplift priors with ds_max={ds_max}")

    ds_max_ts = pd.Timestamp(ds_max)

    # Load sales (filter to ds_max)
    df_sales = pd.read_parquet(sales_fact_path)
    df_sales = df_sales[df_sales["ds"] <= ds_max_ts].copy()

    logger.info(f"Using sales data up to {ds_max} ({len(df_sales)} days)")

    # Load recurring event mapping
    df_events = pd.read_parquet(recurring_mapping_path)

    # Compute uplift for each event family
    uplift_results = []

    for _, event in df_events.iterrows():
        event_family = event["event_family_ascii"]

        # Try 2025 window first
        start_2025 = event["start_2025"]
        end_2025 = event["end_2025"]

        event_days_2025 = []
        if pd.notna(start_2025) and pd.notna(end_2025):
            # Get event days in 2025 that are <= ds_max
            event_date_range = pd.date_range(start=start_2025, end=end_2025, freq="D")
            event_days_2025 = [d for d in event_date_range if d <= ds_max_ts]

        # Try 2024 fallback if 2025 has no coverage
        event_days_2024 = []
        if len(event_days_2025) == 0:
            # Shift to 2024
            if pd.notna(start_2025) and pd.notna(end_2025):
                try:
                    start_2024 = start_2025.replace(year=2024)
                    end_2024 = end_2025.replace(year=2024)
                    event_date_range_2024 = pd.date_range(start=start_2024, end=end_2024, freq="D")
                    event_days_2024 = [d for d in event_date_range_2024 if d <= ds_max_ts]
                except:
                    pass  # Handle leap year edge cases

        # Combine 2025 and 2024 event days
        event_days = event_days_2025 + event_days_2024

        if len(event_days) == 0:
            # No data available
            uplift_results.append(
                {
                    "event_family_ascii": event_family,
                    "uplift_mean_raw": np.nan,
                    "uplift_mean_shrunk": np.nan,
                    "n_days": 0,
                    "confidence_bucket": "missing",
                }
            )
            continue

        # Compute uplift for each event day
        uplift_ratios = []

        for event_ds in event_days:
            # Get actual sales
            actual_sales = df_sales[df_sales["ds"] == event_ds]

            if len(actual_sales) == 0 or actual_sales.iloc[0]["is_closed"]:
                continue

            actual_y = actual_sales.iloc[0]["y"]

            # Compute baseline
            baseline = compute_weekday_baseline(df_sales, event_ds)

            if pd.notna(baseline) and baseline > 0:
                uplift_ratio = actual_y / baseline
                uplift_ratios.append(uplift_ratio)

        if len(uplift_ratios) == 0:
            # Could not compute uplift
            uplift_results.append(
                {
                    "event_family_ascii": event_family,
                    "uplift_mean_raw": np.nan,
                    "uplift_mean_shrunk": np.nan,
                    "n_days": len(event_days),
                    "confidence_bucket": "no_baseline",
                }
            )
            continue

        # Aggregate uplift
        n_days = len(uplift_ratios)
        uplift_mean_raw = np.median(uplift_ratios)

        # Apply shrinkage toward 1.0 (no uplift)
        prior_mean = 1.0
        uplift_mean_shrunk = (n_days / (n_days + shrink_k)) * uplift_mean_raw + (
            shrink_k / (n_days + shrink_k)
        ) * prior_mean

        # Confidence bucket
        if n_days >= 5:
            confidence_bucket = "high"
        elif n_days >= 2:
            confidence_bucket = "medium"
        else:
            confidence_bucket = "low"

        uplift_results.append(
            {
                "event_family_ascii": event_family,
                "uplift_mean_raw": uplift_mean_raw,
                "uplift_mean_shrunk": uplift_mean_shrunk,
                "n_days": n_days,
                "confidence_bucket": confidence_bucket,
            }
        )

    df_uplift = pd.DataFrame(uplift_results)

    logger.info(f"Computed uplift priors for {len(df_uplift)} event families")
    logger.info(f"  High confidence: {(df_uplift['confidence_bucket'] == 'high').sum()}")
    logger.info(f"  Medium confidence: {(df_uplift['confidence_bucket'] == 'medium').sum()}")
    logger.info(f"  Low confidence: {(df_uplift['confidence_bucket'] == 'low').sum()}")
    logger.info(
        f"  Missing/no baseline: {df_uplift['confidence_bucket'].isin(['missing', 'no_baseline']).sum()}"
    )

    return df_uplift


def generate_uplift_report(
    df_uplift: pd.DataFrame,
    output_path: str = "outputs/reports/event_uplift_report.md",
) -> None:
    """Generate uplift report."""

    report = f"""# Event Uplift Priors Report

Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Summary

- **Total Event Families**: {len(df_uplift)}
- **High Confidence**: {(df_uplift["confidence_bucket"] == "high").sum()}
- **Medium Confidence**: {(df_uplift["confidence_bucket"] == "medium").sum()}
- **Low Confidence**: {(df_uplift["confidence_bucket"] == "low").sum()}
- **Missing/No Baseline**: {df_uplift["confidence_bucket"].isin(["missing", "no_baseline"]).sum()}

## Top 10 Positive Uplift Events (Shrunk)

"""

    top_positive = df_uplift[df_uplift["uplift_mean_shrunk"].notna()].nlargest(
        10, "uplift_mean_shrunk"
    )

    report += "| Event Family | Raw Uplift | Shrunk Uplift | Days | Confidence |\n"
    report += "|--------------|------------|---------------|------|------------|\n"

    for _, row in top_positive.iterrows():
        report += f"| {row['event_family_ascii'][:50]} | {row['uplift_mean_raw']:.3f} | {row['uplift_mean_shrunk']:.3f} | {row['n_days']} | {row['confidence_bucket']} |\n"

    report += "\n## Top 10 Negative Uplift Events (Shrunk)\n\n"

    top_negative = df_uplift[df_uplift["uplift_mean_shrunk"].notna()].nsmallest(
        10, "uplift_mean_shrunk"
    )

    report += "| Event Family | Raw Uplift | Shrunk Uplift | Days | Confidence |\n"
    report += "|--------------|------------|---------------|------|------------|\n"

    for _, row in top_negative.iterrows():
        report += f"| {row['event_family_ascii'][:50]} | {row['uplift_mean_raw']:.3f} | {row['uplift_mean_shrunk']:.3f} | {row['n_days']} | {row['confidence_bucket']} |\n"

    report += "\n## Missing/No Data Events\n\n"

    missing = df_uplift[df_uplift["confidence_bucket"].isin(["missing", "no_baseline"])]

    if len(missing) > 0:
        report += "| Event Family | Reason |\n"
        report += "|--------------|--------|\n"

        for _, row in missing.iterrows():
            report += f"| {row['event_family_ascii'][:50]} | {row['confidence_bucket']} |\n"
    else:
        report += "No missing events.\n"

    # Save report
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    output_path_obj.write_text(report)
    logger.info(f"Saved uplift report to {output_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Compute priors using full history
    df_sales = pd.read_parquet("data/processed/fact_sales_daily.parquet")
    ds_max = df_sales["ds"].max().strftime("%Y-%m-%d")

    df_uplift = compute_event_uplift_priors(ds_max=ds_max)

    # Save priors
    output_path = "data/processed/event_uplift_priors.parquet"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df_uplift.to_parquet(output_path, index=False)
    logger.info(f"Saved uplift priors to {output_path}")

    # Generate report
    generate_uplift_report(df_uplift)

    print("\nUplift priors complete!")
    print(f"Mean uplift (shrunk): {df_uplift['uplift_mean_shrunk'].mean():.3f}")
    print(f"Median uplift (shrunk): {df_uplift['uplift_mean_shrunk'].median():.3f}")
