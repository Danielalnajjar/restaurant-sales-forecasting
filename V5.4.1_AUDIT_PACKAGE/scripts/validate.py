#!/usr/bin/env python3
"""
Validation script for CI/CD.

Runs:
1. pytest (all tests)
2. ruff check (linting)
3. Config validation
4. Required outputs validation

Exits with non-zero code on any failure.
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run a command and report success/failure."""
    print(f"\n{'=' * 80}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print("=" * 80)

    result = subprocess.run(cmd, capture_output=False)

    if result.returncode != 0:
        print(f"\n❌ FAILED: {description}")
        return False
    else:
        print(f"\n✓ PASSED: {description}")
        return True


def check_file_exists(path, description):
    """Check if a file exists."""
    if path.exists():
        print(f"✓ Found: {description} ({path})")
        return True
    else:
        print(f"❌ Missing: {description} ({path})")
        return False


def main():
    root = Path(__file__).parent.parent
    print(f"Project root: {root}")

    all_passed = True

    # 1. Run pytest
    passed = run_command(
        [sys.executable, "-m", "pytest", str(root / "tests"), "-v"], "pytest (unit tests)"
    )
    all_passed &= passed

    # 2. Run ruff check
    try:
        passed = run_command(
            [sys.executable, "-m", "ruff", "check", str(root / "src")], "ruff check (linting)"
        )
        all_passed &= passed
    except FileNotFoundError:
        print("⚠️  WARNING: ruff not installed, skipping linting check")

    # 3. Validate config loads
    print(f"\n{'=' * 80}")
    print("Running: Config validation")
    print("=" * 80)

    try:
        from forecasting.utils.runtime import load_config

        config = load_config()
        print("✓ Config loaded successfully")
        print(f"  Forecast: {config.get('forecast_start')} to {config.get('forecast_end')}")
    except Exception as e:
        print(f"❌ Config loading failed: {e}")
        all_passed = False

    # 4. Validate required outputs exist
    print(f"\n{'=' * 80}")
    print("Validating required outputs from most recent run")
    print("=" * 80)

    outputs_dir = root / "outputs"
    forecasts_dir = outputs_dir / "forecasts"
    reports_dir = outputs_dir / "reports"
    models_dir = outputs_dir / "models"

    # Find most recent forecast file
    if forecasts_dir.exists():
        forecast_files = list(forecasts_dir.glob("forecast_daily_*.csv"))
        # Filter out baseline files
        forecast_files = [f for f in forecast_files if "BASELINE" not in f.name]

        if forecast_files:
            latest_forecast = max(forecast_files, key=lambda p: p.stat().st_mtime)

            # Extract slug from filename
            slug = latest_forecast.stem.replace("forecast_daily_", "")

            print(f"Validating outputs for slug: {slug}")

            # Required outputs
            all_passed &= check_file_exists(
                latest_forecast, f"Daily forecast (forecast_daily_{slug}.csv)"
            )
            all_passed &= check_file_exists(
                reports_dir / f"run_log_{slug}.json", f"Run log (run_log_{slug}.json)"
            )
            all_passed &= check_file_exists(
                forecasts_dir / f"rollups_ordering_{slug}.csv",
                f"Ordering rollup (rollups_ordering_{slug}.csv)",
            )
            all_passed &= check_file_exists(
                forecasts_dir / f"rollups_scheduling_{slug}.csv",
                f"Scheduling rollup (rollups_scheduling_{slug}.csv)",
            )
            all_passed &= check_file_exists(
                models_dir / f"ensemble_weights_{slug}.csv",
                f"Ensemble weights (ensemble_weights_{slug}.csv)",
            )

            # Optional but recommended outputs (don't fail if missing, just warn)
            spike_log = reports_dir / f"spike_uplift_log_{slug}.csv"
            if spike_log.exists():
                check_file_exists(spike_log, f"Spike uplift log (spike_uplift_log_{slug}.csv)")
            else:
                print(f"⚠️  Optional: Spike uplift log not found (spike_uplift_log_{slug}.csv)")

            growth_log = reports_dir / f"growth_calibration_log_{slug}.csv"
            if growth_log.exists():
                check_file_exists(
                    growth_log, f"Growth calibration log (growth_calibration_log_{slug}.csv)"
                )
            else:
                print(
                    f"⚠️  Optional: Growth calibration log not found (growth_calibration_log_{slug}.csv)"
                )
        else:
            print("❌ No forecast files found (run pipeline first)")
            all_passed = False
    else:
        print("❌ No outputs directory found (run pipeline first)")
        all_passed = False

    # Final result
    print(f"\n{'=' * 80}")
    if all_passed:
        print("✓ ALL VALIDATION CHECKS PASSED")
        print("=" * 80)
        return 0
    else:
        print("❌ SOME VALIDATION CHECKS FAILED")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    sys.exit(main())
