"""
Test forecast window parameterization (Step 7.2 from ChatGPT 5.2 Pro's plan).

Tests:
- get_forecast_window() extracts dates from config
- forecast_slug() returns correct slug format
"""

import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from forecasting.utils.runtime import forecast_slug, get_forecast_window


def test_get_forecast_window_2026():
    """Test forecast window extraction for 2026."""
    config = {"forecast_start": "2026-01-01", "forecast_end": "2026-12-31"}
    start, end = get_forecast_window(config)
    assert start == "2026-01-01"
    assert end == "2026-12-31"


def test_get_forecast_window_2027():
    """Test forecast window extraction for 2027."""
    config = {"forecast_start": "2027-01-01", "forecast_end": "2027-12-31"}
    start, end = get_forecast_window(config)
    assert start == "2027-01-01"
    assert end == "2027-12-31"


def test_get_forecast_window_defaults():
    """Test that defaults work if keys missing."""
    config = {}
    start, end = get_forecast_window(config)
    # Should have defaults (2026)
    assert start == "2026-01-01"
    assert end == "2026-12-31"


def test_forecast_slug_full_year():
    """Test that full-year windows get YYYY slug."""
    # 2026 full year
    slug = forecast_slug("2026-01-01", "2026-12-31")
    assert slug == "2026"

    # 2027 full year
    slug = forecast_slug("2027-01-01", "2027-12-31")
    assert slug == "2027"


def test_forecast_slug_partial_year():
    """Test that partial-year windows get YYYYMMDD_YYYYMMDD slug."""
    slug = forecast_slug("2026-01-01", "2026-06-30")
    assert slug == "20260101_20260630"

    slug = forecast_slug("2026-07-01", "2026-12-31")
    assert slug == "20260701_20261231"


def test_forecast_window_validation():
    """Test that invalid windows raise errors."""
    # End before start
    config = {"forecast_start": "2026-12-31", "forecast_end": "2026-01-01"}
    with pytest.raises(ValueError, match="must be >= forecast_start"):
        get_forecast_window(config)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
