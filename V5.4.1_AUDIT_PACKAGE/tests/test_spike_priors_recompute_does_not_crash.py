"""
Test that spike uplift priors computation does not crash with boolean filtering.

This test ensures the fix for the `not df_open[flag]` bug is working.
"""

import pandas as pd


def test_spike_priors_recompute_does_not_crash():
    """Test that compute_spike_uplift_priors works with boolean filtering."""
    from forecasting.features.spike_uplift import compute_spike_uplift_priors

    # Create synthetic history with one spike day
    dates = pd.date_range("2025-01-01", periods=30, freq="D")
    df_hist = pd.DataFrame(
        {
            "ds": dates,
            "y": [1000.0] * 30,
            "is_closed": [False] * 30,
            "dow": dates.dayofweek,
            "month": dates.month,
            "is_black_friday": [False] * 29 + [True],  # Last day is spike
        }
    )

    # This should not crash (would crash if using `not df_open[flag]`)
    result = compute_spike_uplift_priors(
        df_sales=df_hist, ds_max=None, min_observations=1, shrinkage_factor=0.25
    )

    # Verify result structure
    assert isinstance(result, pd.DataFrame)
    assert "spike_flag" in result.columns
    assert "uplift_multiplier" in result.columns
    assert "confidence" in result.columns
    assert "n_obs" in result.columns
    assert "baseline_method" in result.columns

    # Should have computed prior for is_black_friday
    assert "is_black_friday" in result["spike_flag"].values

    # Multiplier should be reasonable (not NaN, not infinite)
    black_friday_row = result[result["spike_flag"] == "is_black_friday"].iloc[0]
    assert pd.notna(black_friday_row["uplift_multiplier"])
    assert black_friday_row["uplift_multiplier"] > 0
    assert black_friday_row["uplift_multiplier"] < 10  # Sanity check


def test_spike_priors_with_no_spike_days():
    """Test that compute_spike_uplift_priors handles no spike days gracefully."""
    from forecasting.features.spike_uplift import compute_spike_uplift_priors

    # Create synthetic history with NO spike days
    dates = pd.date_range("2025-01-01", periods=30, freq="D")
    df_hist = pd.DataFrame(
        {
            "ds": dates,
            "y": [1000.0] * 30,
            "is_closed": [False] * 30,
            "dow": dates.dayofweek,
            "month": dates.month,
            "is_black_friday": [False] * 30,  # No spikes
        }
    )

    # This should not crash
    result = compute_spike_uplift_priors(
        df_sales=df_hist, ds_max=None, min_observations=1, shrinkage_factor=0.25
    )

    # Should return neutral multiplier (1.0) for insufficient data
    assert isinstance(result, pd.DataFrame)
    black_friday_row = result[result["spike_flag"] == "is_black_friday"].iloc[0]
    assert black_friday_row["uplift_multiplier"] == 1.0
    assert black_friday_row["confidence"] == "insufficient"
