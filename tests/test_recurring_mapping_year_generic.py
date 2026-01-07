from pathlib import Path

import pandas as pd
import pytest

from forecasting.io.events_ingest import ingest_recurring_event_mapping


def test_ingest_recurring_event_mapping_accepts_2027_columns(tmp_path: Path):
    # Create a synthetic mapping with 2026 + 2027 columns
    df = pd.DataFrame(
        {
            "event_family": ["Test Event"],
            "category": ["holiday"],
            "proximity": [0],
            "recurrence_pattern": ["fixed"],
            "start_2026": ["2026-01-01"],
            "end_2026": ["2026-01-02"],
            "start_2027": ["2027-01-01"],
            "end_2027": ["2027-01-02"],
        }
    )
    p = tmp_path / "mapping.csv"
    df.to_csv(p, index=False)

    out = ingest_recurring_event_mapping(str(p))
    assert "start_2027" in out.columns
    assert "end_2027" in out.columns
    assert pd.api.types.is_datetime64_any_dtype(out["start_2027"])
    assert pd.api.types.is_datetime64_any_dtype(out["end_2027"])


def test_ingest_recurring_event_mapping_requires_year_pairs(tmp_path: Path):
    # Missing end_2027 should fail
    df = pd.DataFrame(
        {
            "event_family": ["Test Event"],
            "category": ["holiday"],
            "proximity": [0],
            "recurrence_pattern": ["fixed"],
            "start_2027": ["2027-01-01"],
        }
    )
    p = tmp_path / "mapping.csv"
    df.to_csv(p, index=False)

    with pytest.raises(ValueError):
        ingest_recurring_event_mapping(str(p))
