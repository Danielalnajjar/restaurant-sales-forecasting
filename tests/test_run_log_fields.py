"""
Test run_log.json schema and correctness (Step 7.4).

Tests:
- run_log contains all required fields
- calibration_mode is not "unknown" when monthly calibration ran
"""

import pytest
import json
from pathlib import Path


def test_run_log_schema():
    """Test that run_log.json contains all required fields."""
    root = Path(__file__).parent.parent
    
    # Look for most recent run_log
    reports_dir = root / "outputs" / "reports"
    if not reports_dir.exists():
        pytest.skip("No outputs/reports directory found")
    
    run_logs = list(reports_dir.glob("run_log_*.json"))
    if not run_logs:
        pytest.skip("No run_log_*.json files found")
    
    # Use most recent
    run_log_path = max(run_logs, key=lambda p: p.stat().st_mtime)
    
    with open(run_log_path) as f:
        run_log = json.load(f)
    
    # Required fields per Step 5
    required_fields = [
        'timestamp_utc',
        'git_commit',
        'config_path',
        'config_hash',
        'data_through',
        'forecast_start',
        'forecast_end',
        'forecast_days',
        'annual_total_p50',
        'annual_total_p80',
        'annual_total_p90',
        'spike_days_adjusted',
        'calibration_mode',
        'outputs',
    ]
    
    missing = [f for f in required_fields if f not in run_log]
    assert not missing, f"Missing required fields in run_log: {missing}"
    
    # Check types
    assert isinstance(run_log['forecast_days'], int)
    assert isinstance(run_log['annual_total_p50'], (int, float))
    assert isinstance(run_log['spike_days_adjusted'], int)
    assert isinstance(run_log['calibration_mode'], str)
    assert isinstance(run_log['outputs'], dict)


def test_calibration_mode_not_unknown():
    """Test that calibration_mode is not 'unknown' when calibration ran."""
    root = Path(__file__).parent.parent
    reports_dir = root / "outputs" / "reports"
    
    if not reports_dir.exists():
        pytest.skip("No outputs/reports directory found")
    
    run_logs = list(reports_dir.glob("run_log_*.json"))
    if not run_logs:
        pytest.skip("No run_log_*.json files found")
    
    run_log_path = max(run_logs, key=lambda p: p.stat().st_mtime)
    
    with open(run_log_path) as f:
        run_log = json.load(f)
    
    calibration_mode = run_log.get('calibration_mode', 'unknown')
    
    # Check if growth calibration log exists
    growth_log_path = reports_dir / "growth_calibration_log.csv"
    if growth_log_path.exists():
        # If calibration log exists, mode should not be "unknown"
        assert calibration_mode != "unknown", \
            "calibration_mode is 'unknown' but growth_calibration_log.csv exists"
        assert calibration_mode in ["monthly", "annual", "none"], \
            f"Invalid calibration_mode: {calibration_mode}"


def test_run_log_outputs_exist():
    """Test that files listed in run_log.outputs actually exist."""
    root = Path(__file__).parent.parent
    reports_dir = root / "outputs" / "reports"
    
    if not reports_dir.exists():
        pytest.skip("No outputs/reports directory found")
    
    run_logs = list(reports_dir.glob("run_log_*.json"))
    if not run_logs:
        pytest.skip("No run_log_*.json files found")
    
    run_log_path = max(run_logs, key=lambda p: p.stat().st_mtime)
    
    with open(run_log_path) as f:
        run_log = json.load(f)
    
    outputs = run_log.get('outputs', {})
    
    for key, path in outputs.items():
        if path and path != "unknown":
            # Convert to absolute path if relative
            if not Path(path).is_absolute():
                path = root / path
            else:
                path = Path(path)
            
            # Check existence (some outputs may be optional)
            if key == "forecast_daily":
                assert path.exists(), f"Required output missing: {path}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
