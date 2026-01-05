"""
Test that backward-compatible wrappers still work after renaming to generic names.
"""



def test_generate_2026_forecast_wrapper_exists():
    """Test that generate_2026_forecast wrapper still exists and imports."""
    from forecasting.pipeline.export import generate_2026_forecast

    assert callable(generate_2026_forecast)
    assert generate_2026_forecast.__doc__ is not None
    assert "wrapper" in generate_2026_forecast.__doc__.lower()


def test_build_events_daily_2026_wrapper_exists():
    """Test that build_events_daily_2026 wrapper still exists and imports."""
    from forecasting.features.events_daily import build_events_daily_2026

    assert callable(build_events_daily_2026)
    assert build_events_daily_2026.__doc__ is not None
    assert "wrapper" in build_events_daily_2026.__doc__.lower()


def test_build_hours_calendar_2026_wrapper_exists():
    """Test that build_hours_calendar_2026 wrapper still exists and imports."""
    from forecasting.io.hours_calendar import build_hours_calendar_2026

    assert callable(build_hours_calendar_2026)
    assert build_hours_calendar_2026.__doc__ is not None
    assert "wrapper" in build_hours_calendar_2026.__doc__.lower()


def test_generic_functions_exist():
    """Test that new generic-named functions exist."""
    from forecasting.features.events_daily import build_events_daily_forecast
    from forecasting.io.hours_calendar import build_hours_calendar_forecast
    from forecasting.pipeline.export import generate_forecast

    assert callable(generate_forecast)
    assert callable(build_events_daily_forecast)
    assert callable(build_hours_calendar_forecast)


def test_wrappers_have_same_signature():
    """Test that wrappers have same signature as original functions."""
    import inspect

    from forecasting.features.events_daily import (
        build_events_daily_2026,
        build_events_daily_forecast,
    )
    from forecasting.io.hours_calendar import (
        build_hours_calendar_2026,
        build_hours_calendar_forecast,
    )
    from forecasting.pipeline.export import generate_2026_forecast, generate_forecast

    # Check generate_forecast
    sig_old = inspect.signature(generate_2026_forecast)
    sig_new = inspect.signature(generate_forecast)
    assert list(sig_old.parameters.keys()) == list(sig_new.parameters.keys())

    # Check build_events_daily_forecast
    sig_old = inspect.signature(build_events_daily_2026)
    sig_new = inspect.signature(build_events_daily_forecast)
    assert list(sig_old.parameters.keys()) == list(sig_new.parameters.keys())

    # Check build_hours_calendar_forecast
    sig_old = inspect.signature(build_hours_calendar_2026)
    sig_new = inspect.signature(build_hours_calendar_forecast)
    assert list(sig_old.parameters.keys()) == list(sig_new.parameters.keys())
