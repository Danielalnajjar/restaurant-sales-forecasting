"""
Test that run_pipeline has skip_chronos=False by default (Chronos enabled).
"""

import inspect


def test_run_pipeline_default_chronos_enabled():
    """Test that Chronos is enabled by default in run_pipeline."""
    from forecasting.pipeline.run_daily import run_pipeline

    # Get function signature
    sig = inspect.signature(run_pipeline)

    # Check skip_chronos parameter default
    assert "skip_chronos" in sig.parameters, "skip_chronos parameter missing"

    skip_chronos_param = sig.parameters["skip_chronos"]

    # Default should be False (Chronos enabled)
    assert skip_chronos_param.default is False, (
        f"Expected skip_chronos default=False, got {skip_chronos_param.default}"
    )
