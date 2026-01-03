from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml


def find_project_root(start: Path | None = None) -> Path:
    """
    Find repo root robustly (works under cron with arbitrary CWD).
    Looks for sentinel directories/files: code/, configs/, data/, .git
    """
    p = (start or Path(__file__).resolve()).parent
    for candidate in [p] + list(p.parents):
        # Check for src/forecasting structure (current structure)
        if (candidate / "src" / "forecasting").is_dir():
            return candidate
        # Check for code/ and configs/ (legacy structure)
        if (candidate / "code").is_dir() and (candidate / "configs").is_dir():
            return candidate
        if (candidate / ".git").exists():
            return candidate
    # Fallback to current working directory if not found
    return Path.cwd()


def resolve_config_path(config_path: str | None) -> Path:
    """
    Resolution order:
    1) explicit CLI path (if provided)
    2) env var FORECASTING_CONFIG (if set)
    3) repo_root/configs/config.yaml
    4) repo_root/code/config.yaml (legacy)
    """
    root = find_project_root()
    candidates: list[Path] = []

    if config_path:
        candidates.append(Path(config_path))

    env_path = os.getenv("FORECASTING_CONFIG")
    if env_path:
        candidates.append(Path(env_path))

    candidates.append(root / "configs" / "config.yaml")
    candidates.append(root / "code" / "config.yaml")

    for c in candidates:
        if c.exists():
            return c.resolve()

    raise FileNotFoundError(
        "Could not locate config.yaml. Tried: " + ", ".join(str(c) for c in candidates)
    )


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config YAML must be a dict at top level. Got: {type(data)}")
    return data


def get_forecast_window(config: Dict[str, Any]) -> Tuple[str, str]:
    """
    Returns (forecast_start, forecast_end) as ISO YYYY-MM-DD strings.
    """
    import datetime

    fs = config.get("forecast_start", "2026-01-01")
    fe = config.get("forecast_end", "2026-12-31")

    # Convert datetime.date to string if needed (YAML parser returns date objects)
    if isinstance(fs, datetime.date):
        fs = fs.strftime("%Y-%m-%d")
    if isinstance(fe, datetime.date):
        fe = fe.strftime("%Y-%m-%d")

    # Validation
    if not isinstance(fs, str) or not isinstance(fe, str):
        raise ValueError(
            "forecast_start/forecast_end must be strings or dates in YYYY-MM-DD format"
        )
    if fe < fs:
        raise ValueError(f"forecast_end ({fe}) must be >= forecast_start ({fs})")
    return fs, fe


def forecast_slug(forecast_start: str, forecast_end: str) -> str:
    """
    Naming slug used in output artifacts. If full-year, use YYYY; else YYYYMMDD_YYYYMMDD.
    """
    if (
        forecast_start.endswith("-01-01")
        and forecast_end.endswith("-12-31")
        and forecast_start[:4] == forecast_end[:4]
    ):
        return forecast_start[:4]
    return forecast_start.replace("-", "") + "_" + forecast_end.replace("-", "")


def safe_json_dump(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True, default=str)
    tmp.replace(path)


def load_config(config_path: str | None = None) -> Dict[str, Any]:
    """
    Load configuration from YAML file with validation.

    Parameters
    ----------
    config_path : str, optional
        Path to config file. If None, uses default resolution order.

    Returns
    -------
    dict
        Configuration dictionary

    Raises
    ------
    FileNotFoundError
        If config file cannot be found
    ValueError
        If config is invalid or missing required fields
    """
    try:
        resolved_path = resolve_config_path(config_path)
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Configuration file not found: {e}")

    try:
        config = load_yaml(resolved_path)
    except Exception as e:
        raise ValueError(f"Failed to parse configuration file {resolved_path}: {e}")

    # Validate required fields
    required_fields = ["forecast_start", "forecast_end", "short_horizons", "long_horizons"]
    missing_fields = [f for f in required_fields if f not in config]
    if missing_fields:
        raise ValueError(f"Configuration missing required fields: {missing_fields}")

    # Validate forecast window
    try:
        get_forecast_window(config)
    except Exception as e:
        raise ValueError(f"Invalid forecast window in configuration: {e}")

    return config


def get_git_commit() -> str:
    """
    Get current git commit hash. Returns 'unknown' if not in a git repo or git not available.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown"
