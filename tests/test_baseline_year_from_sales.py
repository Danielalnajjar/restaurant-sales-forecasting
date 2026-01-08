"""Test _baseline_year_from_sales helper function."""

import pandas as pd
import pytest

from forecasting.features.event_uplift import _baseline_year_from_sales


def test_baseline_year_dec_31():
    """If max_date is Dec 31, baseline_year = max_year."""
    df = pd.DataFrame({"ds": pd.date_range("2024-01-01", "2025-12-31", freq="D")})
    assert _baseline_year_from_sales(df) == 2025


def test_baseline_year_mid_year():
    """If max_date is mid-year, baseline_year = max_year - 1."""
    df = pd.DataFrame({"ds": pd.date_range("2024-01-01", "2025-06-30", freq="D")})
    assert _baseline_year_from_sales(df) == 2024


def test_baseline_year_jan_1():
    """If max_date is Jan 1, baseline_year = max_year - 1."""
    df = pd.DataFrame({"ds": pd.date_range("2024-01-01", "2025-01-01", freq="D")})
    assert _baseline_year_from_sales(df) == 2024


def test_baseline_year_missing_ds_column():
    """Raise ValueError if 'ds' column missing."""
    df = pd.DataFrame({"date": ["2025-01-01"]})
    with pytest.raises(ValueError, match="must contain a 'ds' column"):
        _baseline_year_from_sales(df)


def test_baseline_year_empty_ds():
    """Raise ValueError if 'ds' column has no valid dates."""
    df = pd.DataFrame({"ds": [pd.NaT, pd.NaT]})
    with pytest.raises(ValueError, match="contains no valid dates"):
        _baseline_year_from_sales(df)
