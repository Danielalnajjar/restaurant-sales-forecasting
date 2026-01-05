# Year-Agnostic Forecasting Guide

**Version:** 5.4.2  
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

```
outputs/forecasts/forecast_daily_2027.csv
outputs/reports/run_log_2027.json
outputs/reports/spike_uplift_log_2027.csv
outputs/reports/growth_calibration_log_2027.csv
```

---

## How It Works

### Config-Driven Year Templates

The system uses **year templates** in config.yaml:

```yaml
paths:
  raw_events_exact_template: "data/events/events_{year}_exact_dates_clean_v2.csv"
  raw_hours_calendar_template: "data/raw/hours_calendar_{year}_v2.csv"
  raw_hours_overrides_template: "data/raw/hours_overrides_{year}_v2.csv"
```

At runtime, the pipeline:
1. Extracts the forecast year from `forecast_start` (e.g., 2027)
2. Substitutes `{year}` in templates to get actual paths
3. Loads data from those paths
4. Generates forecasts with year-specific slugs

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

**Backward compatibility:** Old function names still work as aliases.

---

## Data File Requirements

### 1. Exact Events File

**Path:** `data/events/events_{year}_exact_dates_clean_v2.csv`

**Required columns:**
- `event_name` - Name of the event
- `event_family` - Event category/family
- `start_date` - Start date (YYYY-MM-DD)
- `end_date` - End date (YYYY-MM-DD)
- `is_major` - Boolean flag for major events

**Example:**
```csv
event_name,event_family,start_date,end_date,is_major
New Year's Day,Holiday,2027-01-01,2027-01-01,TRUE
Super Bowl Sunday,Sports,2027-02-07,2027-02-07,TRUE
```

### 2. Hours Calendar File

**Path:** `data/raw/hours_calendar_{year}_v2.csv`

**Required columns:**
- `ds` - Date (YYYY-MM-DD)
- `open_time` - Opening time (HH:MM)
- `close_time` - Closing time (HH:MM)
- `is_closed` - Boolean flag for closed days

**Example:**
```csv
ds,open_time,close_time,is_closed
2027-01-01,00:00,00:00,TRUE
2027-01-02,11:00,21:00,FALSE
```

### 3. Hours Overrides File

**Path:** `data/raw/hours_overrides_{year}_v2.csv`

**Same format as hours calendar.** Used to override specific dates (holidays, special events).

### 4. Recurring Event Mapping

**Path:** `data/events/recurring_event_mapping_2025_2026_clean.csv`

**Required columns:**
- `event_family` - Event category
- `start_2025`, `end_2025` - 2025 date range
- `start_2026`, `end_2026` - 2026 date range
- `start_2027`, `end_2027` - 2027 date range (add as needed)
- `start_2028`, `end_2028` - 2028 date range (add as needed)

**Example:**
```csv
event_family,start_2025,end_2025,start_2026,end_2026,start_2027,end_2027
Black Friday,2025-11-28,2025-11-29,2026-11-27,2026-11-28,2027-11-26,2027-11-27
Christmas,2025-12-24,2025-12-26,2026-12-24,2026-12-26,2027-12-24,2027-12-26
```

---

## Output Naming

Outputs are named using a **slug** derived from the forecast period:

### Full-Year Forecasts
- **Slug:** `YYYY` (e.g., `2027`)
- **Example:** `forecast_daily_2027.csv`

### Partial-Year Forecasts
- **Slug:** `YYYYMMDD_YYYYMMDD` (e.g., `20270601_20271231`)
- **Example:** `forecast_daily_20270601_20271231.csv`

### Stable Pointers

For convenience, the system also creates **stable pointer files** without slugs:
- `outputs/forecasts/forecast_daily.csv` → latest forecast
- `outputs/reports/run_log.json` → latest run metadata
- `outputs/reports/spike_uplift_log.csv` → latest spike log

These are exact copies of the slugged versions, making it easy to find the latest outputs.

---

## Testing Year Changes

### Sanity Test: Forecast 2027 Q1

To test the year-agnostic system without a full year:

```yaml
forecast_start: 2027-01-01
forecast_end: 2027-03-31
```

This will generate a 90-day forecast with slug `20270101_20270331`.

### Validation Checklist

After changing years, verify:

1. ✅ **Config loads successfully** - No errors about missing fields
2. ✅ **Year extracted correctly** - Check logs for "Forecast period: 2027-01-01 to 2027-12-31 (year: 2027)"
3. ✅ **Paths resolved correctly** - Check logs for "Raw events path: data/events/events_2027_exact_dates_clean_v2.csv"
4. ✅ **Data files loaded** - No "file not found" errors
5. ✅ **Outputs generated** - Check for `forecast_daily_2027.csv`, `run_log_2027.json`
6. ✅ **Slug in filenames** - All outputs use correct year slug

---

## Troubleshooting

### Error: "File not found: data/events/events_2027_exact_dates_clean_v2.csv"

**Solution:** Create the 2027 exact events file. Copy the 2026 file and update dates:

```bash
cp data/events/events_2026_exact_dates_clean_v2.csv \
   data/events/events_2027_exact_dates_clean_v2.csv
# Edit the file to update dates to 2027
```

### Error: "Missing year columns for 2027 in recurring mapping"

**Solution:** Add `start_2027` and `end_2027` columns to `recurring_event_mapping_clean.csv`:

```python
import pandas as pd

df = pd.read_csv("data/events/recurring_event_mapping_2025_2026_clean.csv")

# Add 2027 columns by shifting 2026 dates forward 1 year
df["start_2027"] = pd.to_datetime(df["start_2026"]) + pd.DateOffset(years=1)
df["end_2027"] = pd.to_datetime(df["end_2026"]) + pd.DateOffset(years=1)

df.to_csv("data/events/recurring_event_mapping_2025_2026_clean.csv", index=False)
```

### Warning: "Skipping 2024 dates for Christmas (likely leap year issue)"

**Expected behavior.** The system tries to use 2024 data as a fallback if 2025 data is missing. Leap year edge cases (Feb 29) are handled gracefully.

### Error: "forecast_end (2027-01-01) must be >= forecast_start (2027-12-31)"

**Solution:** You have `forecast_start` and `forecast_end` swapped in config.yaml. Fix the order.

---

## Advanced Usage

### Forecasting Multiple Years

To generate forecasts for 2027, 2028, and 2029:

```bash
# 2027
python -m forecasting.pipeline.run_daily --config configs/config_2027.yaml

# 2028
python -m forecasting.pipeline.run_daily --config configs/config_2028.yaml

# 2029
python -m forecasting.pipeline.run_daily --config configs/config_2029.yaml
```

Create separate config files for each year, or use a script to update the single config.yaml between runs.

### Custom Output Directories

Override output paths in config.yaml:

```yaml
paths:
  forecasts_daily: "outputs/forecasts/forecast_daily_{slug}.csv"
  reports_run_log: "outputs/reports/run_log_{slug}.json"
```

The `{slug}` placeholder will be replaced with the year slug.

---

## Implementation Details

### V5.4.2 Changes

The year-agnostic system was implemented in V5.4.2 with these key changes:

1. **PHASE 1:** Year-generic recurring mapping ingest (preserves all year columns)
2. **PHASE 2:** NaN-safe spike flag casting (prevents edge case bugs)
3. **PHASE 3:** Repo hygiene (enhanced .gitignore)
4. **PHASE 4:** Config-driven year templates (enables config-only year changes)
5. **PHASE 5:** Generic naming + backward-compatible aliases
6. **PHASE 6:** Tightened exception handling (removed bare `except:`)
7. **PHASE 7:** Validation + documentation

### Numeric Parity

All V5.4.2 changes maintain **strict numeric parity** with V5.4.1:
- **Max difference (p50):** $0.00
- **Max difference (p80):** $0.00
- **Max difference (p90):** $0.00
- **Annual total:** $1,066,144.67 (identical)

This means the year-agnostic refactoring had **zero impact** on forecast values for 2026.

---

## FAQ

**Q: Do I need to change any code to forecast 2027?**  
A: No. Just update config.yaml and provide 2027 data files.

**Q: Can I forecast partial years (e.g., Q1 2027)?**  
A: Yes. Set `forecast_start: 2027-01-01` and `forecast_end: 2027-03-31`.

**Q: What if I don't have 2027 recurring event dates yet?**  
A: The system will fall back to 2026 dates shifted by 1 year. You can add `start_2027`/`end_2027` columns later.

**Q: Can I use the old function names (generate_2026_forecast)?**  
A: Yes. They're backward-compatible aliases that call the new generic functions.

**Q: Will this work for 2030 and beyond?**  
A: Yes. Just add `start_2030`/`end_2030` columns to recurring mapping and create 2030 data files.

**Q: How do I know which year the forecast is for?**  
A: Check the `run_log.json` file - it includes `forecast_start`, `forecast_end`, and `forecast_year`.

---

## Support

For issues or questions about year-agnostic forecasting:
1. Check this guide's Troubleshooting section
2. Review the V5.4.2 implementation logs in `documentation/V5.4.2_WORKLOG.md`
3. Contact the forecasting team

---

**Last Updated:** January 4, 2026  
**Version:** 5.4.2 10++
