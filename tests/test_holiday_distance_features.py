"""Test holiday distance features."""

import pandas as pd

from forecasting.features.holiday_distance import add_holiday_distance_features


def test_holiday_distance_is_zero_on_holiday_itself():
    """Test that days_until and days_since are both 0 on the holiday itself."""
    # Thanksgiving 2025 = 2025-11-27; Christmas 2025 = 2025-12-25; New Year 2025 = 2025-01-01
    df = pd.DataFrame({"ds": pd.to_datetime(["2025-11-27", "2025-12-25", "2025-01-01"])})
    out = add_holiday_distance_features(df.copy())

    # On Thanksgiving, both until and since should be 0
    assert out.loc[out["ds"] == "2025-11-27", "days_until_thanksgiving"].iloc[0] == 0
    assert out.loc[out["ds"] == "2025-11-27", "days_since_thanksgiving"].iloc[0] == 0

    # On Christmas, both until and since should be 0
    assert out.loc[out["ds"] == "2025-12-25", "days_until_christmas"].iloc[0] == 0
    assert out.loc[out["ds"] == "2025-12-25", "days_since_christmas"].iloc[0] == 0

    # On New Year, both until and since should be 0
    assert out.loc[out["ds"] == "2025-01-01", "days_until_new_year"].iloc[0] == 0
    assert out.loc[out["ds"] == "2025-01-01", "days_since_new_year"].iloc[0] == 0
