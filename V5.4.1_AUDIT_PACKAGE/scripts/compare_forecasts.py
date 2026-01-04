#!/usr/bin/env python3
"""
Compare old vs new forecast for numeric parity validation.
Acceptance: abs diff <= $0.01 for p50/p80/p90 on all days.
"""

import sys
from pathlib import Path

import pandas as pd


def compare_forecasts(old_path, new_path):
    """Compare two forecast files for numeric parity."""
    print(f"Loading old forecast: {old_path}")
    df_old = pd.read_csv(old_path)

    print(f"Loading new forecast: {new_path}")
    df_new = pd.read_csv(new_path)

    print(f"\nRow counts: old={len(df_old)}, new={len(df_new)}")

    if len(df_old) != len(df_new):
        print("❌ FAIL: Different number of rows")
        return False

    # Merge on ds
    df_merged = df_old.merge(df_new, on='ds', suffixes=('_old', '_new'))

    if len(df_merged) != len(df_old):
        print("❌ FAIL: Date mismatch between files")
        return False

    print(f"✓ Same dates: {len(df_merged)} days")

    # Compare p50, p80, p90
    max_diff_p50 = (df_merged['p50_old'] - df_merged['p50_new']).abs().max()
    max_diff_p80 = (df_merged['p80_old'] - df_merged['p80_new']).abs().max()
    max_diff_p90 = (df_merged['p90_old'] - df_merged['p90_new']).abs().max()

    print("\nMax absolute differences:")
    print(f"  p50: ${max_diff_p50:.4f}")
    print(f"  p80: ${max_diff_p80:.4f}")
    print(f"  p90: ${max_diff_p90:.4f}")

    threshold = 0.01

    if max_diff_p50 > threshold:
        print(f"❌ FAIL: p50 diff ${max_diff_p50:.4f} > ${threshold}")
        # Show worst cases
        worst = df_merged.nlargest(5, (df_merged['p50_old'] - df_merged['p50_new']).abs())
        print("\nWorst p50 differences:")
        for _, row in worst.iterrows():
            diff = row['p50_old'] - row['p50_new']
            print(f"  {row['ds']}: ${diff:+.2f} (old=${row['p50_old']:.2f}, new=${row['p50_new']:.2f})")
        return False

    if max_diff_p80 > threshold:
        print(f"❌ FAIL: p80 diff ${max_diff_p80:.4f} > ${threshold}")
        return False

    if max_diff_p90 > threshold:
        print(f"❌ FAIL: p90 diff ${max_diff_p90:.4f} > ${threshold}")
        return False

    # Check closed days
    closed_old = (df_merged['p50_old'] == 0).sum()
    closed_new = (df_merged['p50_new'] == 0).sum()

    print(f"\nClosed days: old={closed_old}, new={closed_new}")

    if closed_old != closed_new:
        print("❌ FAIL: Different number of closed days")
        return False

    # Check totals
    total_old = df_merged['p50_old'].sum()
    total_new = df_merged['p50_new'].sum()
    total_diff = abs(total_old - total_new)

    print("\nAnnual totals (p50):")
    print(f"  Old: ${total_old:,.2f}")
    print(f"  New: ${total_new:,.2f}")
    print(f"  Diff: ${total_diff:,.2f}")

    if total_diff > 1.0:  # Allow $1 total difference due to rounding
        print(f"❌ FAIL: Total diff ${total_diff:.2f} > $1.00")
        return False

    print("\n" + "="*80)
    print("✓ PASS: Numeric parity validated")
    print("  - All days match within $0.01")
    print("  - Same closed days")
    print("  - Total within $1.00")
    print("="*80)

    return True


if __name__ == "__main__":
    root = Path(__file__).parent.parent
    old_path = root / "outputs" / "forecasts" / "forecast_daily_2026_OLD.csv"
    new_path = root / "outputs" / "forecasts" / "forecast_daily_2026.csv"

    if not old_path.exists():
        print(f"❌ Old forecast not found: {old_path}")
        sys.exit(1)

    if not new_path.exists():
        print(f"❌ New forecast not found: {new_path}")
        sys.exit(1)

    success = compare_forecasts(old_path, new_path)
    sys.exit(0 if success else 1)
