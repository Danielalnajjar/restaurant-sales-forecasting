"""Test dynamic US holidays year span calculation."""

import datetime as dt

import holidays
import pandas as pd

from forecasting.features.feature_builders import _year_span_for_dates


def test_year_span_for_dates_includes_max_year():
    """Test that year span includes both min and max years."""
    ds = pd.Series(pd.to_datetime(["2026-12-31", "2027-01-01"]))
    years = _year_span_for_dates(ds)
    assert 2026 in years
    assert 2027 in years


def test_us_holidays_contains_2027_new_years_day():
    """Test that US holidays calendar includes 2027 New Year's Day."""
    ds = pd.Series(pd.to_datetime(["2026-12-31", "2027-01-01"]))
    years = _year_span_for_dates(ds)
    us_holidays = holidays.US(years=years)
    assert dt.date(2027, 1, 1) in us_holidays
