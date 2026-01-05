"""
Test that recurring mapping ingest preserves future year columns (2027+).
"""

from pathlib import Path

import pandas as pd


def test_recurring_mapping_ingest_preserves_future_year_columns(tmp_path: Path):
    """Test that recurring mapping ingest preserves 2027+ columns."""
    # Create a minimal recurring mapping CSV with 2025, 2026, AND 2027 columns
    df = pd.DataFrame(
        {
            "event_family": ["Test Event"],
            "event_family_ascii": ["test_event"],
            "category": ["convention"],
            "proximity": ["local"],
            "start_2025": ["2025-01-10"],
            "end_2025": ["2025-01-12"],
            "start_2026": ["2026-01-09"],
            "end_2026": ["2026-01-11"],
            "start_2027": ["2027-01-08"],
            "end_2027": ["2027-01-10"],
        }
    )
    path = tmp_path / "recurring_mapping.csv"
    df.to_csv(path, index=False)

    # Import ingestion function
    from forecasting.io.events_ingest import ingest_recurring_event_mapping

    out = ingest_recurring_event_mapping(
        input_path=str(path), output_path=str(tmp_path / "out.parquet")
    )

    # Must preserve all year columns (including 2027)
    assert "start_2027" in out.columns, "start_2027 column missing"
    assert "end_2027" in out.columns, "end_2027 column missing"

    # Must parse to datetime
    assert pd.api.types.is_datetime64_any_dtype(out["start_2027"]), "start_2027 not datetime"
    assert pd.api.types.is_datetime64_any_dtype(out["end_2027"]), "end_2027 not datetime"

    # Verify 2025 and 2026 still work
    assert "start_2025" in out.columns
    assert "end_2025" in out.columns
    assert "start_2026" in out.columns
    assert "end_2026" in out.columns


def test_recurring_mapping_ingest_handles_missing_optional_columns(tmp_path: Path):
    """Test that missing optional columns are handled gracefully."""
    # Create mapping without event_family_ascii, category, proximity
    df = pd.DataFrame(
        {
            "event_family": ["Test Event"],
            "start_2025": ["2025-01-10"],
            "end_2025": ["2025-01-12"],
            "start_2026": ["2026-01-09"],
            "end_2026": ["2026-01-11"],
        }
    )
    path = tmp_path / "recurring_mapping_minimal.csv"
    df.to_csv(path, index=False)

    from forecasting.io.events_ingest import ingest_recurring_event_mapping

    out = ingest_recurring_event_mapping(
        input_path=str(path), output_path=str(tmp_path / "out.parquet")
    )

    # Should create event_family_ascii automatically
    assert "event_family_ascii" in out.columns
    assert out["event_family_ascii"].iloc[0] == "Test Event"

    # Should create empty category/proximity
    assert "category" in out.columns
    assert "proximity" in out.columns
