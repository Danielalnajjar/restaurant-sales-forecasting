"""
Test year template path resolution for config-driven 2027+ forecasting.
"""

from pathlib import Path

import pytest


def test_format_year_path():
    """Test that format_year_path correctly substitutes year placeholder."""
    from forecasting.utils.runtime import format_year_path

    p = format_year_path("data/raw/events_{year}_exact.csv", 2027)
    assert str(p).endswith("data/raw/events_2027_exact.csv")

    p = format_year_path("data/events/events_{year}_exact_dates_clean_v2.csv", 2026)
    assert str(p).endswith("data/events/events_2026_exact_dates_clean_v2.csv")

    p = format_year_path("data/raw/hours_calendar_{year}_v2.csv", 2028)
    assert str(p).endswith("data/raw/hours_calendar_2028_v2.csv")


def test_forecast_year_from_config():
    """Test that forecast_year_from_config extracts year correctly."""
    from forecasting.utils.runtime import forecast_year_from_config

    cfg = {
        "forecast_start": "2027-01-01",
        "forecast_end": "2027-12-31",
    }
    assert forecast_year_from_config(cfg) == 2027

    cfg = {
        "forecast_start": "2026-01-01",
        "forecast_end": "2026-12-31",
    }
    assert forecast_year_from_config(cfg) == 2026

    cfg = {
        "forecast_start": "2028-06-01",
        "forecast_end": "2028-12-31",
    }
    assert forecast_year_from_config(cfg) == 2028


def test_forecast_year_and_paths_from_config(tmp_path: Path):
    """Test full path resolution workflow from config."""
    from forecasting.utils.runtime import forecast_year_from_config, format_year_path

    # Minimal config for test
    cfg = {
        "forecast_start": "2027-01-01",
        "forecast_end": "2027-12-31",
        "paths": {
            "raw_events_exact_template": "data/events/events_{year}_exact_dates_clean_v2.csv",
            "raw_hours_calendar_template": "data/raw/hours_calendar_{year}_v2.csv",
            "raw_hours_overrides_template": "data/raw/hours_overrides_{year}_v2.csv",
            "raw_recurring_mapping_template": "data/events/recurring_event_mapping_clean.csv",
        },
    }

    y = forecast_year_from_config(cfg)
    assert y == 2027

    events = format_year_path(cfg["paths"]["raw_events_exact_template"], y)
    assert str(events).endswith("data/events/events_2027_exact_dates_clean_v2.csv")

    hours = format_year_path(cfg["paths"]["raw_hours_calendar_template"], y)
    assert str(hours).endswith("data/raw/hours_calendar_2027_v2.csv")

    overrides = format_year_path(cfg["paths"]["raw_hours_overrides_template"], y)
    assert str(overrides).endswith("data/raw/hours_overrides_2027_v2.csv")

    # Recurring mapping doesn't use year template
    recurring = Path(cfg["paths"]["raw_recurring_mapping_template"])
    assert str(recurring).endswith("data/events/recurring_event_mapping_clean.csv")


def test_format_year_path_with_different_patterns():
    """Test that format_year_path works with various path patterns."""
    from forecasting.utils.runtime import format_year_path

    # Absolute path
    p = format_year_path("/data/events_{year}.csv", 2027)
    assert str(p) == "/data/events_2027.csv"

    # Multiple occurrences of {year} (edge case - should only have one)
    p = format_year_path("data/{year}/events_{year}.csv", 2027)
    assert str(p) == "data/2027/events_2027.csv"

    # No extension
    p = format_year_path("data/events_{year}", 2027)
    assert str(p) == "data/events_2027"
