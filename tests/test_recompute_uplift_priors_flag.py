"""Test that recompute_uplift_priors flag is honored in run_pipeline."""

import inspect

from forecasting.pipeline.run_daily import run_pipeline


def test_run_pipeline_has_recompute_uplift_priors_parameter():
    """Verify run_pipeline has recompute_uplift_priors parameter."""
    sig = inspect.signature(run_pipeline)
    assert "recompute_uplift_priors" in sig.parameters, (
        "run_pipeline must have recompute_uplift_priors parameter"
    )


def test_recompute_uplift_priors_default_is_false():
    """Verify recompute_uplift_priors defaults to False."""
    sig = inspect.signature(run_pipeline)
    param = sig.parameters["recompute_uplift_priors"]
    assert param.default is False, (
        "recompute_uplift_priors should default to False (skip recompute)"
    )


def test_run_pipeline_source_has_conditional_uplift_priors():
    """Verify run_pipeline source code has 'if recompute_uplift_priors:' guard."""
    import forecasting.pipeline.run_daily

    source = inspect.getsource(forecasting.pipeline.run_daily.run_pipeline)

    # Check for conditional guard
    assert "if recompute_uplift_priors:" in source, (
        "run_pipeline must have 'if recompute_uplift_priors:' guard"
    )

    # Check that compute_event_uplift_priors appears AFTER the if statement
    # (simpler check: just verify both exist and uplift call comes after the if)
    if_pos = source.find("if recompute_uplift_priors:")
    compute_pos = source.find("compute_event_uplift_priors")

    assert if_pos > 0, "Must have 'if recompute_uplift_priors:' statement"
    assert compute_pos > 0, "Must call compute_event_uplift_priors"
    assert compute_pos > if_pos, (
        "compute_event_uplift_priors must appear after 'if recompute_uplift_priors:' guard"
    )

    # Check for else clause (skip message)
    assert "else:" in source[if_pos:], (
        "Must have 'else:' clause for when recompute_uplift_priors is False"
    )
    assert "Skipping event uplift priors recompute" in source, (
        "Must log skip message when recompute_uplift_priors is False"
    )
