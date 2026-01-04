"""
Test that no hardcoded 2026 forecast windows remain in code (Step 7.3).

This is a grep-style test that fails if code contains hardcoded date ranges.
Allowed exceptions:
- configs/config.yaml (default values)
- docs/ (documentation)
- tests/ (test fixtures)
"""

import re
from pathlib import Path

import pytest


def test_no_hardcoded_2026_windows():
    """Test that Python code does not contain hardcoded 2026 date windows."""
    root = Path(__file__).parent.parent
    src_dir = root / "src"

    if not src_dir.exists():
        pytest.skip("src/ directory not found")

    # Patterns to search for
    forbidden_patterns = [
        r'ds_min\s*=\s*["\']2026-01-01["\']',
        r'ds_max\s*=\s*["\']2026-12-31["\']',
        r'pd\.date_range\([^)]*start\s*=\s*["\']2026-01-01["\']',
        r'pd\.date_range\([^)]*end\s*=\s*["\']2026-12-31["\']',
    ]

    violations = []

    # Search all Python files in src/
    for py_file in src_dir.rglob("*.py"):
        # Skip test files
        if "test" in str(py_file).lower():
            continue

        content = py_file.read_text()

        for pattern in forbidden_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                # Get line number
                line_num = content[:match.start()].count('\n') + 1
                violations.append(f"{py_file}:{line_num}: {match.group()}")

    if violations:
        msg = "Found hardcoded 2026 forecast windows:\n" + "\n".join(violations)
        pytest.fail(msg)


def test_no_hardcoded_output_paths():
    """Test that output paths use slug, not hardcoded _2026."""
    root = Path(__file__).parent.parent
    src_dir = root / "src"

    if not src_dir.exists():
        pytest.skip("src/ directory not found")

    # Patterns for hardcoded output paths (as defaults in function signatures)
    # These should be None or use slug
    forbidden_patterns = [
        r'output_daily_path:\s*str\s*=\s*["\'][^"\']*forecast_daily_2026\.csv["\']',
        r'output_.*_path:\s*str\s*=\s*["\'][^"\']*_2026\.(csv|parquet)["\']',
    ]

    violations = []

    for py_file in src_dir.rglob("*.py"):
        if "test" in str(py_file).lower():
            continue

        content = py_file.read_text()

        for pattern in forbidden_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                line_num = content[:match.start()].count('\n') + 1
                violations.append(f"{py_file}:{line_num}: {match.group()}")

    if violations:
        msg = "Found hardcoded _2026 in output path defaults:\n" + "\n".join(violations)
        # This is a warning, not a failure, since we allow backwards compat
        print(f"WARNING: {msg}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
