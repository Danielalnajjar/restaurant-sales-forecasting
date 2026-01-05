"""
Test resolve_year_path() helper for V5.4.3 PHASE 2.

Per ChatGPT 5.2 Pro V5.4.3 plan: Verify year template resolution with fallback.
"""

import pytest

from forecasting.utils.runtime import resolve_year_path


def test_resolve_year_path_uses_template_when_available():
    """Template key exists → use it with year substitution"""
    config = {
        "forecast_start": "2027-01-01",
        "forecast_end": "2027-12-31",
        "paths": {
            "raw_hours_calendar_template": "data/raw/hours_calendar_{year}_v2.csv",
            "raw_hours_calendar_2026": "data/raw/hours_calendar_2026_v2.csv",
        },
    }
    result = resolve_year_path(
        config,
        template_key="raw_hours_calendar_template",
        fallback_key="raw_hours_calendar_2026",
    )
    assert result == "data/raw/hours_calendar_2027_v2.csv"


def test_resolve_year_path_uses_fallback_when_template_missing():
    """Template key missing → use fallback key"""
    config = {
        "forecast_start": "2026-01-01",
        "forecast_end": "2026-12-31",
        "paths": {
            "raw_hours_calendar_2026": "data/raw/hours_calendar_2026_v2.csv",
        },
    }
    result = resolve_year_path(
        config,
        template_key="raw_hours_calendar_template",
        fallback_key="raw_hours_calendar_2026",
    )
    assert result == "data/raw/hours_calendar_2026_v2.csv"


def test_resolve_year_path_explicit_year_overrides_config():
    """Explicit year parameter overrides forecast_start year"""
    config = {
        "forecast_start": "2026-01-01",
        "forecast_end": "2026-12-31",
        "paths": {
            "raw_hours_calendar_template": "data/raw/hours_calendar_{year}_v2.csv",
        },
    }
    result = resolve_year_path(
        config,
        template_key="raw_hours_calendar_template",
        year=2028,  # Override
    )
    assert result == "data/raw/hours_calendar_2028_v2.csv"


def test_resolve_year_path_raises_when_both_missing_and_required():
    """Neither template nor fallback exists + required=True → ValueError"""
    config = {
        "forecast_start": "2027-01-01",
        "forecast_end": "2027-12-31",
        "paths": {},
    }
    with pytest.raises(ValueError, match="Path not found in config"):
        resolve_year_path(
            config,
            template_key="nonexistent_template",
            fallback_key="nonexistent_fallback",
            required=True,
        )


def test_resolve_year_path_returns_none_when_both_missing_and_not_required():
    """Neither template nor fallback exists + required=False → None"""
    config = {
        "forecast_start": "2027-01-01",
        "forecast_end": "2027-12-31",
        "paths": {},
    }
    result = resolve_year_path(
        config,
        template_key="nonexistent_template",
        fallback_key="nonexistent_fallback",
        required=False,
    )
    assert result is None


def test_resolve_year_path_works_with_output_templates():
    """Output templates work the same as input templates"""
    config = {
        "forecast_start": "2027-01-01",
        "forecast_end": "2027-12-31",
        "paths": {
            "output_forecast_daily_template": "outputs/forecasts/forecast_daily_{year}.csv",
            "forecasts_daily": "outputs/forecasts/forecast_daily_2026.csv",
        },
    }
    result = resolve_year_path(
        config,
        template_key="output_forecast_daily_template",
        fallback_key="forecasts_daily",
    )
    assert result == "outputs/forecasts/forecast_daily_2027.csv"
