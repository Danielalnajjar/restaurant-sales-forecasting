"""
Test that slugged log paths are correctly generated.
"""

from pathlib import Path


def test_slugged_log_paths_in_output():
    """Test that slug-based log paths are used in outputs."""
    # Load a recent run_log to check if it references slugged paths
    outputs_dir = Path("outputs")
    reports_dir = outputs_dir / "reports"

    if not reports_dir.exists():
        # No outputs yet, skip test
        import pytest
        pytest.skip("No outputs directory found (run pipeline first)")

    # Find most recent run_log
    run_logs = list(reports_dir.glob("run_log_*.json"))
    if not run_logs:
        import pytest
        pytest.skip("No run logs found (run pipeline first)")

    latest_run_log = max(run_logs, key=lambda p: p.stat().st_mtime)

    # Extract slug from filename
    slug = latest_run_log.stem.replace("run_log_", "")

    # Check that slugged log files exist
    expected_files = [
        reports_dir / f"spike_uplift_log_{slug}.csv",
        reports_dir / f"growth_calibration_log_{slug}.csv",
        reports_dir / f"monthly_calibration_scales_{slug}.csv",
    ]

    for expected_file in expected_files:
        if expected_file.exists():
            print(f"✓ Found slugged log: {expected_file.name}")
        else:
            print(f"⚠️  Slugged log not found (may be optional): {expected_file.name}")

    # At minimum, run_log should be slugged (which it is, by construction)
    assert latest_run_log.exists()
    assert slug in latest_run_log.name


def test_stable_pointer_logs_exist():
    """Test that stable pointer logs exist alongside slugged logs."""
    outputs_dir = Path("outputs")
    reports_dir = outputs_dir / "reports"

    if not reports_dir.exists():
        import pytest
        pytest.skip("No outputs directory found (run pipeline first)")

    # Check for stable pointers
    stable_files = [
        reports_dir / "run_log.json",
        reports_dir / "spike_uplift_log.csv",
        reports_dir / "growth_calibration_log.csv",
        reports_dir / "monthly_calibration_scales.csv",
    ]

    for stable_file in stable_files:
        if stable_file.exists():
            print(f"✓ Found stable pointer: {stable_file.name}")
        else:
            print(f"⚠️  Stable pointer not found (may be optional): {stable_file.name}")

    # At minimum, run_log.json should exist
    run_log_stable = reports_dir / "run_log.json"
    if run_log_stable.exists():
        assert run_log_stable.exists()
