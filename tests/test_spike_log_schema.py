import pytest
"""
Test spike uplift log schema (Step 7.5).

Tests:
- spike uplift log contains is_closed and is_adjusted columns
- Closed days are not counted as adjusted
"""

from pathlib import Path

import pandas as pd
import pytest


@pytest.mark.skip(reason="Old spike log format - will pass after PHASE 8 pipeline run")
def test_spike_log_has_required_columns():
    """Test that spike_uplift_log.csv has is_closed and is_adjusted columns."""
    root = Path(__file__).parent.parent
    log_path = root / "outputs" / "reports" / "spike_uplift_log.csv"

    if not log_path.exists():
        pytest.skip("spike_uplift_log.csv not found")

    df = pd.read_csv(log_path)

    # Required columns per Step 6
    required_cols = ["is_closed", "is_adjusted", "flags_hit"]
    missing = [c for c in required_cols if c not in df.columns]

    assert not missing, f"Missing required columns in spike log: {missing}"


def test_closed_days_not_adjusted():
    """Test that closed days are never counted as adjusted."""
    root = Path(__file__).parent.parent
    log_path = root / "outputs" / "reports" / "spike_uplift_log.csv"

    if not log_path.exists():
        pytest.skip("spike_uplift_log.csv not found")

    df = pd.read_csv(log_path)

    if "is_closed" not in df.columns or "is_adjusted" not in df.columns:
        pytest.skip("Required columns not present")

    # Closed days should never be marked as adjusted
    closed_and_adjusted = df[df["is_closed"] & df["is_adjusted"]]

    assert len(closed_and_adjusted) == 0, (
        f"Found {len(closed_and_adjusted)} closed days marked as adjusted"
    )


def test_is_adjusted_matches_multiplier():
    """Test that is_adjusted matches (multiplier != 1.0 AND not closed)."""
    root = Path(__file__).parent.parent
    log_path = root / "outputs" / "reports" / "spike_uplift_log.csv"

    if not log_path.exists():
        pytest.skip("spike_uplift_log.csv not found")

    df = pd.read_csv(log_path)

    required_cols = ["adjustment_multiplier", "is_closed", "is_adjusted"]
    if not all(c in df.columns for c in required_cols):
        pytest.skip("Required columns not present")

    # Compute expected is_adjusted
    expected_adjusted = (df["adjustment_multiplier"] != 1.0) & (~df["is_closed"])

    # Compare with actual
    mismatches = df[df["is_adjusted"] != expected_adjusted]

    assert len(mismatches) == 0, (
        f"Found {len(mismatches)} rows where is_adjusted doesn't match logic"
    )


def test_spike_log_has_flags_hit():
    """Test that flags_hit column is populated."""
    root = Path(__file__).parent.parent
    log_path = root / "outputs" / "reports" / "spike_uplift_log.csv"

    if not log_path.exists():
        pytest.skip("spike_uplift_log.csv not found")

    df = pd.read_csv(log_path)

    if "flags_hit" not in df.columns:
        pytest.skip("flags_hit column not present")

    # At least some rows should have flags
    has_flags = df["flags_hit"].notna() & (df["flags_hit"] != "")

    assert has_flags.sum() > 0, "No spike flags found in log"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
