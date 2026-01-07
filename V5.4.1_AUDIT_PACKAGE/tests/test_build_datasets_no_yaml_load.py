"""
Test that build_datasets.py does not load YAML directly (config centralization).
"""

import re
from pathlib import Path


def test_build_datasets_no_yaml_load():
    """Test that build_datasets.py does not load config.yaml directly."""
    build_datasets_path = Path("src/forecasting/features/build_datasets.py")

    if not build_datasets_path.exists():
        import pytest

        pytest.fail(f"build_datasets.py not found at {build_datasets_path}")

    content = build_datasets_path.read_text()

    # Check for yaml.safe_load
    if "yaml.safe_load" in content:
        import pytest

        pytest.fail(
            "build_datasets.py contains yaml.safe_load - config should be passed as parameter"
        )

    # Check for open(...config.yaml...)
    if re.search(r"open\([^)]*config\.yaml", content):
        import pytest

        pytest.fail(
            "build_datasets.py opens config.yaml directly - config should be passed as parameter"
        )

    # Verify that functions accept config parameter
    if "def build_train_datasets(" in content:
        # Find the function signature
        match = re.search(r"def build_train_datasets\([^)]*\)", content, re.DOTALL)
        if match:
            signature = match.group(0)
            assert "config:" in signature or "config :" in signature, (
                "build_train_datasets should accept config parameter"
            )

    print("✓ build_datasets.py does not load YAML directly")
    print("✓ Config is properly centralized")
