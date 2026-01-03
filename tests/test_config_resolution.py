"""
Test config resolution logic (Step 7.1 from ChatGPT 5.2 Pro's plan).

Tests:
- resolve_config_path(None) finds configs/config.yaml when present
- Setting env FORECASTING_CONFIG overrides
- Passing explicit path overrides
"""

import os
import pytest
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from forecasting.utils.runtime import resolve_config_path, find_project_root


def test_resolve_config_finds_canonical():
    """Test that resolve_config_path(None) finds configs/config.yaml."""
    root = find_project_root()
    canonical_path = root / "configs" / "config.yaml"
    
    # Only run if canonical config exists
    if canonical_path.exists():
        resolved = resolve_config_path(None)
        assert resolved.exists(), "Resolved config path does not exist"
        assert resolved.name == "config.yaml", "Resolved config is not config.yaml"
        assert "configs" in str(resolved), "Resolved config is not in configs/ directory"


def test_explicit_path_overrides():
    """Test that passing explicit path overrides default resolution."""
    root = find_project_root()
    canonical_path = root / "configs" / "config.yaml"
    
    if canonical_path.exists():
        # Pass explicit path
        resolved = resolve_config_path(str(canonical_path))
        assert resolved == canonical_path.resolve()


def test_env_var_overrides(tmp_path):
    """Test that FORECASTING_CONFIG env var overrides default."""
    # Create a temporary config file
    temp_config = tmp_path / "test_config.yaml"
    temp_config.write_text("forecast_start: 2027-01-01\nforecast_end: 2027-12-31\n")
    
    # Set env var
    old_env = os.environ.get("FORECASTING_CONFIG")
    try:
        os.environ["FORECASTING_CONFIG"] = str(temp_config)
        resolved = resolve_config_path(None)
        assert resolved == temp_config.resolve()
    finally:
        # Restore env
        if old_env:
            os.environ["FORECASTING_CONFIG"] = old_env
        else:
            os.environ.pop("FORECASTING_CONFIG", None)


def test_find_project_root():
    """Test that find_project_root() finds the repo root."""
    root = find_project_root()
    assert root.exists(), "Project root does not exist"
    
    # Should have either src/forecasting or code/ directory
    has_src = (root / "src" / "forecasting").is_dir()
    has_code = (root / "code").is_dir()
    has_configs = (root / "configs").is_dir()
    
    assert has_src or has_code, "Project root missing src/forecasting or code/"
    assert has_configs, "Project root missing configs/"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
