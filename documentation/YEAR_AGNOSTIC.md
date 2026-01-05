# Year-Agnostic Forecasting Guide

**Version:** 5.4.3  
**Date:** January 4, 2026  
**Status:** Production-ready

---

## Overview

The forecasting system is now **fully year-agnostic**. You can forecast any year (2026, 2027, 2028+) by simply:
1. Updating 2 lines in `configs/config.yaml`
2. Providing year-specific raw input files
3. Running the same pipeline command

**No code changes required.**

---

## Quick Start: Forecasting 2027

### Step 1: Update Config

Edit `configs/config.yaml`:

```yaml
# Change these two lines:
forecast_start: 2027-01-01
forecast_end: 2027-12-31
```

### Step 2: Prepare 2027 Data Files

Place these files in your data directories:

```
data/events/events_2027_exact_dates_clean_v2.csv
data/raw/hours_calendar_2027_v2.csv
data/raw/hours_overrides_2027_v2.csv
```

**Recurring events:** Update `data/events/recurring_event_mapping_2025_2026_clean.csv` to include `start_2027` and `end_2027` columns.

### Step 3: Run Pipeline

```bash
python -m forecasting.pipeline.run_daily --config configs/config.yaml
```

### Step 4: Get Outputs

The pipeline will generate:

**Year-specific outputs:**
```
outputs/forecasts/forecast_daily_2027.csv
outputs/reports/run_log_2027.json
outputs/reports/spike_uplift_log_2027.csv
outputs/reports/growth_calibration_log_2027.csv
outputs/reports/monthly_calibration_scales_2027.csv
```

**Stable pointers (always point to latest run):**
```
outputs/forecasts/forecast_daily.csv
outputs/reports/run_log.json
outputs/reports/spike_uplift_log.csv
outputs/reports/growth_calibration_log.csv
outputs/reports/monthly_calibration_scales.csv
```

---

## How It Works

### Config-Driven Year Templates

The system uses **year templates** in `configs/config.yaml`:

#### Input Templates

```yaml
paths:
  # Raw input templates (with {year} placeholder)
  raw_events_exact_template: "data/events/events_{year}_exact_dates_clean_v2.csv"
  raw_hours_calendar_template: "data/raw/hours_calendar_{year}_v2.csv"
  raw_hours_overrides_template: "data/raw/hours_overrides_{year}_v2.csv"
  raw_recurring_mapping_template: "data/events/recurring_event_mapping_2025_2026_clean.csv"
  
  # Legacy 2026-specific paths (fallback for backward compatibility)
  raw_events_2026_exact: data/events/events_2026_exact_dates_clean_v2.csv
  raw_hours_calendar_2026: data/raw/hours_calendar_2026_v2.csv
  raw_hours_overrides_2026: data/raw/hours_overrides_2026_v2.csv
  raw_recurring_events: data/events/recurring_event_mapping_2025_2026_clean.csv
```

#### Output Templates

```yaml
paths:
  # Output templates (with {year} placeholder)
  output_forecast_daily_template: "outputs/forecasts/forecast_daily_{year}.csv"
  output_run_log_template: "outputs/reports/run_log_{year}.json"
  output_spike_uplift_log_template: "outputs/reports/spike_uplift_log_{year}.csv"
  output_growth_calibration_log_template: "outputs/reports/growth_calibration_log_{year}.csv"
  output_monthly_calibration_scales_template: "outputs/reports/monthly_calibration_scales_{year}.csv"
  
  # Stable pointers (always point to latest run)
  output_forecast_daily_pointer: "outputs/forecasts/forecast_daily.csv"
  output_run_log_pointer: "outputs/reports/run_log.json"
  output_spike_uplift_log_pointer: "outputs/reports/spike_uplift_log.csv"
  output_growth_calibration_log_pointer: "outputs/reports/growth_calibration_log.csv"
  output_monthly_calibration_scales_pointer: "outputs/reports/monthly_calibration_scales.csv"
```

### Path Resolution Logic

At runtime, the pipeline uses `resolve_year_path()` which:

1. Extracts the forecast year from `forecast_start` (e.g., 2027)
2. Looks for template key (e.g., `raw_hours_calendar_template`)
3. If found, substitutes `{year}` → actual year (e.g., `data/raw/hours_calendar_2027_v2.csv`)
4. If not found, falls back to legacy key (e.g., `raw_hours_calendar_2026`)
5. If neither found, raises clear error

This ensures:
- ✅ **New configs** use templates (year-agnostic)
- ✅ **Old configs** still work (fallback to 2026 paths)
- ✅ **Clear errors** if files missing

### Year-Generic Event Mapping

The recurring event mapping ingestion now:
- **Detects all year columns** using regex (`start_YYYY`, `end_YYYY`)
- **Preserves all years** found in the file (2025, 2026, 2027, 2028+)
- **Validates dates** for each year pair

This means you can add `start_2028`/`end_2028` columns and the system will automatically use them when forecasting 2028.

### Generic Function Names

Core functions have been renamed to be year-agnostic:
- `generate_forecast()` (was `generate_2026_forecast()`)
- `build_events_daily_forecast()` (was `build_events_daily_2026()`)
- `build_hours_calendar_forecast()` (was `build_hours_calendar_2026()`)
- `build_inference_features_forecast()` (was `build_inference_features_2026()`)

**Backward compatibility:** Old function names still work as aliases.

---

## Data File Requirements

### For 2027 Forecasting

**Required files:**
1. `data/events/events_2027_exact_dates_clean_v2.csv`
   - Columns: `event_name`, `start_date`, `end_date`, `is_multiday`
   - Format: Same as 2026 file

2. `data/raw/hours_calendar_2027_v2.csv`
   - Columns: `date`, `day_of_week`, `open_time`, `close_time`, `is_closed`
   - Format: Same as 2026 file

3. `data/raw/hours_overrides_2027_v2.csv`
   - Columns: `date`, `open_time`, `close_time`, `is_closed`, `reason`
   - Format: Same as 2026 file

4. `data/events/recurring_event_mapping_2025_2026_clean.csv` (updated)
   - Add columns: `start_2027`, `end_2027`
   - Existing columns: `event_family`, `start_2025`, `end_2025`, `start_2026`, `end_2026`

### File Format Examples

**events_2027_exact_dates_clean_v2.csv:**
```csv
event_name,start_date,end_date,is_multiday
New Year's Day,2027-01-01,2027-01-01,False
Memorial Day,2027-05-31,2027-05-31,False
Independence Day,2027-07-04,2027-07-04,False
Thanksgiving,2027-11-25,2027-11-25,False
Black Friday,2027-11-26,2027-11-26,False
Christmas,2027-12-25,2027-12-25,False
```

**recurring_event_mapping (with 2027):**
```csv
event_family,start_2025,end_2025,start_2026,end_2026,start_2027,end_2027
memorial_day_weekend,2025-05-24,2025-05-26,2026-05-23,2026-05-25,2027-05-29,2027-05-31
labor_day_weekend,2025-08-30,2025-09-01,2026-09-05,2026-09-07,2027-09-04,2027-09-06
year_end_week,2025-12-26,2026-01-01,2026-12-26,2027-01-01,2027-12-26,2028-01-01
```

---

## Testing Year-Agnostic Behavior

### Smoke Test for 2027

1. Create a test config override:
   ```yaml
   # test_config_2027.yaml
   forecast_start: 2027-01-01
   forecast_end: 2027-12-31
   ```

2. Run with override:
   ```bash
   python -m forecasting.pipeline.run_daily --config test_config_2027.yaml
   ```

3. Expected behavior:
   - If 2027 files exist: Pipeline runs successfully
   - If 2027 files missing: Clear error message:
     ```
     ValueError: Path not found in config: template_key='raw_hours_calendar_template', 
     fallback_key='raw_hours_calendar_2026', year=2027
     ```

---

## Backward Compatibility

### Old Configs Still Work

If your config.yaml only has legacy keys:
```yaml
paths:
  raw_hours_2026: data/raw/hours_calendar_2026_v2.csv
  raw_events_2026_exact: data/events/events_2026_exact_dates_clean_v2.csv
```

The system will:
1. Try template keys (not found)
2. Fall back to legacy keys (found)
3. Use 2026 files

**Result:** Pipeline works exactly as before.

### Migration Path

To migrate from legacy to year-agnostic config:

1. Add template keys to config.yaml (keep legacy keys for now)
2. Test with 2026 (should work with both template and fallback)
3. Add 2027 files
4. Test with 2027 (should use templates)
5. Remove legacy keys once confident

---

## Troubleshooting

### Error: "Path not found in config"

**Cause:** Missing both template and fallback keys

**Solution:** Add template key to config.yaml:
```yaml
paths:
  raw_hours_calendar_template: "data/raw/hours_calendar_{year}_v2.csv"
```

### Error: "File not found: data/raw/hours_calendar_2027_v2.csv"

**Cause:** Config resolved path correctly, but file doesn't exist

**Solution:** Create the 2027 file or use 2026 data as a placeholder for testing

### Outputs Still Named "2026"

**Cause:** Using old config keys without templates

**Solution:** Update config.yaml to use `output_*_template` keys (see above)

---

## Summary

**V5.4.3 makes forecasting truly year-agnostic:**

✅ **Config-only year changes** (2 lines)  
✅ **Template-based path resolution** (with fallback)  
✅ **Year-specific + pointer outputs** (both slugged and stable)  
✅ **Backward compatible** (old configs still work)  
✅ **Clear error messages** (if files missing)

**No code changes required to forecast 2027, 2028, 2029+**

---

**Last Updated:** January 4, 2026  
**Version:** 5.4.3
