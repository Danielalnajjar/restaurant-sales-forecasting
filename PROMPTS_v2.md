# PROMPTS.md — Sequential Agent Prompts (DAG)

> Notes:
> - Each prompt is independently executable and contains all required context.
> - Assume data files live under `/data/` and outputs go to `/outputs/`.
> - Python 3.11+, pip available; local GPU (4090) available; cloud optional.

---

## Prompt 1: Project bootstrap + environment setup

### Dependencies
- Requires outputs from: None — starting point

### Input Files
- None required (but ensure `/data/` exists)

### Goal
Set up a reproducible project structure, Python environment, and configuration that all later prompts will reuse.

### Prompt
```text
Create the project skeleton for a restaurant sales forecasting system.

Requirements:
- Python 3.11
- Use a `pyproject.toml` (preferred) or `requirements.txt`
- Create these directories:
  - /src/forecasting/
  - /src/forecasting/io/
  - /src/forecasting/features/
  - /src/forecasting/models/
  - /src/forecasting/backtest/
  - /src/forecasting/pipeline/
  - /configs/
  - /outputs/
  - /outputs/backtests/
  - /outputs/forecasts/
  - /outputs/reports/
  - /data/raw/
  - /data/processed/
  - /data/processed/features/
  - /data/overrides/

Create a config file at /configs/config.yaml with:
- timezone: America/Los_Angeles
- target: net_sales_excl_tax_service_delivery_fees_comps_refunds_voids
- closed_sales_threshold: 200
- short_horizons: [1..14]
- long_horizons: [15..380]
- forecast_start: 2026-01-01
- forecast_end: 2026-12-31
- quantiles: [0.5, 0.8, 0.9]
- top_k_event_families: 40
- backtest:
  - min_train_days: 120
  - step_days: 14
  - max_horizon_days: 380

Also create a CLI entrypoint:
- `python -m forecasting.pipeline.run_daily --issue-date YYYY-MM-DD` (issue-date optional; defaults to last date in history)

Deliverables:
- Project structure
- Config file
- Minimal `README.md` describing how to run each step
```

### Expected Outputs
- `/configs/config.yaml`
- `/src/forecasting/__init__.py`
- `/src/forecasting/pipeline/run_daily.py`
- `README.md`

### Acceptance Criteria
- Running `python -m forecasting.pipeline.run_daily --help` prints usage and does not crash
- Repo has the required directories and files

---

## Prompt 2: Ingest Toast daily sales CSV → canonical daily fact table

### Dependencies
- Requires outputs from: Prompt 1

### Input Files
- `/data/raw/Sales by day.csv`

### Goal
Create a clean, canonical daily sales fact table with one row per business date and the target `y`.

### Prompt
```text
Implement a sales ingestion + cleaning step.

Input:
- Toast export at /data/raw/Sales by day.csv
- Assumptions:
  - Toast already exports by business date (no timestamp conversion required)
  - Target = net sales excluding tax/service charges/delivery fees/comps/refunds/voids
  - Any day with net_sales < 200 should be marked closed (is_closed=1)

Tasks:
1) Read the CSV robustly (handle commas, $ signs, whitespace in headers).
2) Identify the business date column and net sales column.
3) Produce /data/processed/fact_sales_daily.parquet with columns:
   - ds (date)
   - y (float)
   - is_closed (bool; y < 200)
   - data_source (string)
   - notes (optional)

Cleaning rules:
- Ensure ds is unique; if duplicates exist, aggregate by sum and log a warning.
- Ensure y is numeric; coerce invalid values to NaN then drop rows with missing y and log.
- Sort by ds ascending.
- Save a simple audit report to /outputs/reports/data_audit_summary.md including:
  - min(ds), max(ds), row count
  - count of closed days (y < 200)
  - top 10 largest y days
  - any missing dates (gaps) in the date range

Expected history range (verify from file):
- ds_min = 2024-11-19
- ds_max = 2025-12-22

Deliverables:
- ingestion module in /src/forecasting/io/sales_ingest.py
- fact table parquet
- audit summary markdown
```

### Expected Outputs
- `/data/processed/fact_sales_daily.parquet`
- `/outputs/reports/data_audit_summary.md`
- `/src/forecasting/io/sales_ingest.py`

### Acceptance Criteria
- fact_sales_daily.parquet loads with pandas and has required columns
- data_audit_summary.md includes min/max dates and row counts
- ds is unique and sorted

---

## Prompt 3: Build hours calendar (history + 2026)

### Dependencies
- Requires outputs from: Prompt 1, Prompt 2

### Input Files
- `/data/raw/hours_calendar_2026_v2.csv`
- `/data/raw/hours_overrides_2026_v2.csv`

### Goal
Generate open_minutes and is_closed for every day in history and for every day in 2026.

### Prompt
```text
Implement hours calendar creation.

Inputs:
- /data/raw/hours_calendar_2026_v2.csv (base calendar for 2026)
- /data/raw/hours_overrides_2026_v2.csv (overrides)
- fact sales date range from /data/processed/fact_sales_daily.parquet

Tasks:
1) Create /data/processed/hours_calendar_2026.parquet with:
   - ds (date)
   - open_time_local (time; optional)
   - close_time_local (time; optional)
   - open_minutes (int)
   - is_closed (bool; open_minutes==0)

2) Create /data/processed/hours_calendar_history.parquet for ds in the historical range:
   - If hours are not explicitly provided for history, infer open_minutes using the default rules:
     - Mon–Thu 11:00–20:00
     - Fri–Sat 10:00–21:00
     - Sun 11:00–19:00
     - December extended hours repeat: Dec 8–Dec 30 (Mon–Thu extended per operator)
   - For any date where fact_sales_daily indicates is_closed=1 (y<200), set open_minutes=0 and is_closed=1 regardless of default hours.

3) Validate:
- open_minutes >= 0
- is_closed == (open_minutes == 0)

Write an audit summary to /outputs/reports/hours_audit.md:
- count of closed days in 2026 calendar
- list of override days applied
- min/max open_minutes in 2026

Deliverables:
- /src/forecasting/io/hours_calendar.py
- output parquets
- hours audit report
```

### Expected Outputs
- `/data/processed/hours_calendar_2026.parquet`
- `/data/processed/hours_calendar_history.parquet`
- `/outputs/reports/hours_audit.md`
- `/src/forecasting/io/hours_calendar.py`

### Acceptance Criteria
- 2026 calendar has exactly 365 rows (2026-01-01..2026-12-31)
- history calendar covers all ds in fact_sales_daily.parquet
- no negative open_minutes

---

## Prompt 4: Normalize event files → processed event tables

### Dependencies
- Requires outputs from: Prompt 1

### Input Files
- `/data/events/events_2026_exact_dates_clean_v2.csv`
- `/data/events/recurring_event_mapping_2025_2026_clean.csv`

### Goal
Convert raw event inputs into clean, standardized parquet tables.

### Prompt
```text
Create a robust event ingestion/normalization step.

Inputs:
- /data/events/events_2026_exact_dates_clean_v2.csv
- /data/events/recurring_event_mapping_2025_2026_clean.csv

Tasks:
1) Read both CSVs robustly (handle non-standard characters in headers and event names).
2) Normalize column names to snake_case, ASCII where feasible.
3) Output:
- /data/processed/events_2026_exact.parquet
  Required columns:
    - event_name (string)
    - event_name_ascii (string; safe key)
    - category (string; optional)
    - proximity (string; optional)
    - start_date (date)
    - end_date (date)

- /data/processed/recurring_event_mapping.parquet
  Required columns:
    - event_family (string)
    - event_family_ascii (string; safe key)
    - category (string; optional)
    - proximity (string; optional)
    - start_2025 (date)
    - end_2025 (date)
    - start_2026 (date)
    - end_2026 (date)

4) Validate:
- start_date <= end_date for exact events
- start_2025 <= end_2025; start_2026 <= end_2026 for recurring mapping
- All dates parse correctly
- No duplicate rows after normalization (dedupe by key columns)

Write an audit report /outputs/reports/events_audit.md:
- row counts for each table
- min/max date ranges for each table
- count of missing category/proximity
```

### Expected Outputs
- `/data/processed/events_2026_exact.parquet`
- `/data/processed/recurring_event_mapping.parquet`
- `/outputs/reports/events_audit.md`
- `/src/forecasting/io/events_ingest.py`

### Acceptance Criteria
- Parquets load with pandas
- Date columns are real date types (not strings)
- Audit report includes row counts and min/max date

---

## Prompt 5: Build daily event features (history + 2026)

### Dependencies
- Requires outputs from: Prompt 2, Prompt 4

### Input Files
- `/data/processed/fact_sales_daily.parquet`
- `/data/processed/events_2026_exact.parquet`
- `/data/processed/recurring_event_mapping.parquet`

### Goal
Create daily event feature tables for history and 2026, including multi-day events and lead/lag windows. For 2026, features must be built from events_2026_exact.parquet (do not drop one-offs that are not in recurring_event_mapping).

### Prompt
```text
Implement event feature engineering and write daily event feature tables.

Global requirements:
- Output one row per date ds for each target range:
  1) history range: ds_min..ds_max from /data/processed/fact_sales_daily.parquet
  2) forecast range: 2026-01-01..2026-12-31
- Do NOT rely on /data/processed/events_2026_exact.parquet as the sole source of event instances for history; it contains only 2026 dates.
- Historical event instances (so models can learn event impacts) come from /data/processed/recurring_event_mapping.parquet:
  - start_date = start_2025; end_date = end_2025
- 2026 event instances are the UNION of:
  - all instances from /data/processed/events_2026_exact.parquet (includes one-offs not in mapping)
  - recurring instances from /data/processed/recurring_event_mapping.parquet:
    - start_date = start_2026; end_date = end_2026
- Expand each event instance into daily rows for ds in [start_date, end_date] inclusive.

Event expansion rules:
- If an event spans multiple days, all those days are active.
- Create optional lead/lag aggregates:
  - events_next_3d_total, events_prev_3d_total (counts)

Core features per ds:
- events_active_total (count of active events)
- events_active_by_category__{cat} (count per category; safe keys)
- events_active_by_proximity__{prox} (count per proximity; safe keys)

Also generate top-K recurring event family one-hots (for learning + interpretation):
- Choose K configurable (default 40)
- Define event family id as event_family_ascii from recurring_event_mapping.parquet
- Rank families by number of active days in the historical range (using start_2025/end_2025 expanded to days)
- Create columns: event_family__{event_family_ascii} (0/1) for the top-K families

Outputs:
- /data/processed/features/events_daily_history.parquet
- /data/processed/features/events_daily_2026.parquet

Deliverables:
- /src/forecasting/features/events_daily.py
```

### Expected Outputs
- `/data/processed/features/events_daily_history.parquet`
- `/data/processed/features/events_daily_2026.parquet`
- `/src/forecasting/features/events_daily.py`

### Acceptance Criteria
- history event features cover ds_min..ds_max exactly (one row per day)
- 2026 event features have exactly 365 rows (2026-01-01..2026-12-31)
- Column `events_active_total` equals the row-wise sum of `events_active_by_category__*` (if category columns are generated)
- On history open days, `events_active_total` is not all zeros (at least one ds has events_active_total > 0)

---

## Prompt 6: Compute event uplift priors from historical sales

### Dependencies
- Requires outputs from: Prompt 2, Prompt 4

### Input Files
- `/data/processed/fact_sales_daily.parquet`
- `/data/processed/recurring_event_mapping.parquet`

### Goal
Compute event-family uplift priors from historical sales to support event-aware forecasting.

### Prompt
```text
Compute uplift priors per recurring event family using historical sales.

Inputs:
- fact_sales_daily.parquet (ds, y, is_closed)
- recurring_event_mapping.parquet:
  - event_family_ascii
  - start_2025/end_2025 (2025 instances)

Method (v1):
For each event_family:
1) Identify event days in 2025: ds in [start_2025, end_2025].
2) For each event day, compute a baseline expectation using recent history:
   - baseline = median of same-weekday y over the prior 8 occurrences (excluding closed days)
3) Compute daily uplift ratio:
   - uplift_day = y(ds) / baseline   (if baseline > 0)
4) Aggregate uplift per family:
   - uplift_mean = median(uplift_day) over event days
   - n_days = number of event days used
5) Shrinkage:
   - prior_mean = 1.0 (no uplift)
   - uplift_shrunk = (n_days/(n_days+k)) * uplift_mean + (k/(n_days+k)) * prior_mean
   - choose k (e.g., 10) as shrink strength

Outputs:
- /data/processed/event_uplift_priors.parquet with columns:
  - event_family_ascii
  - uplift_mean_raw
  - uplift_mean_shrunk
  - n_days
  - confidence_bucket (e.g., high/med/low based on n_days)

Guardrails:
- Do not compute uplift for windows with n_days==0 (set uplift fields to null and flag it).
- Ensure no leakage: baseline for each event day must be computed using only prior dates (< that day).

Rolling/OOF priors requirement (Option B):
- Implement priors as a function of a cutoff date: `compute_event_uplift_priors(ds_max: YYYY-MM-DD)`.
  - The function must use ONLY sales with ds <= ds_max.
  - Backtests: call compute_event_uplift_priors(ds_max=T) inside each cutoff loop so priors are out-of-fold.
  - Final production priors file: call compute_event_uplift_priors(ds_max=history_ds_max).

Holiday fallback (Option A):
- If the 2025 window for an event has n_days==0 because the window is beyond ds_max or outside history coverage, attempt a 2024 fallback window:
  - start_2024 = start_2025 shifted to year 2024 (same month/day)
  - end_2024 = end_2025 shifted to year 2024 (same month/day)
  - Only use fallback dates that exist in sales history and are <= ds_max.
- If both 2025 and 2024 windows have n_days==0, set uplift fields to null, set confidence_bucket="missing", and log it.

Deliverables:
- /src/forecasting/features/event_uplift.py
- /data/processed/event_uplift_priors.parquet
- /outputs/reports/event_uplift_report.md summarizing top families by uplift and missing families
```

### Expected Outputs
- `/data/processed/event_uplift_priors.parquet`
- `/outputs/reports/event_uplift_report.md`
- `/src/forecasting/features/event_uplift.py`

### Acceptance Criteria
- Priors parquet loads and contains one row per event_family_ascii
- Report lists at least top 10 uplift families and any missing/no-data families
- No baseline uses future dates

---

## Prompt 7: Build model-ready features + supervised datasets (short and long horizon)

### Dependencies
- Requires outputs from: Prompt 2, Prompt 3, Prompt 5, Prompt 6

### Input Files
- `/data/processed/fact_sales_daily.parquet`
- `/data/processed/hours_calendar_history.parquet`
- `/data/processed/features/events_daily_history.parquet`
- `/data/processed/event_uplift_priors.parquet`

### Goal
Create two supervised training datasets (short and long horizon) AND reusable feature builders for inference (including 2026).

### Prompt
```text
...
- event_uplift_priors.parquet: per event_family priors (used to create aggregate priors per day, if desired)

Tasks:
1) Build deterministic calendar features for any ds:
   - dow (0-6), is_weekend, month, weekofyear, dayofyear
   - Fourier terms: doy_sin_1, doy_cos_1 (and optionally sin/cos_2)
   - is_month_start, is_month_end
   - is_us_federal_holiday (bool), is_new_years_eve (bool; ds month-day == 12-31)

2) Build lag features computed as-of issue_date (no leakage):
   - y_lag_1, y_lag_7, y_lag_14
   - y_roll_mean_7 (mean over [T-7, T-1] open-adjusted y)
   - Optionally: y_roll_mean_28
These lags must use only ds <= issue_date.

3) Build supervised rows:
   For each issue_date T in the historical date range where future labels exist:
   - For each horizon h in the relevant set:
     - target_date = T + h days
     - label = y(target_date)
     - features:
       - calendar features at target_date
       - hours features at target_date (from hours_calendar_history)
       - event features at target_date (from events_daily_history)
       - issue_date calendar features (optional)
       - lags computed at issue_date (SHORT DATASET ONLY)

4) Exclusions:
   - Exclude any row where label date is outside the available history.
   - Exclude rows where label date is closed (is_closed=1) for training (optional but preferred); if excluded, document it in code.

5) Inference feature builders (required):
   Implement functions that build feature matrices for inference (no labels), using the SAME feature definitions as training:
   - `build_features_short(issue_date, target_dates)`:
       - target_dates can be any dates; for this system it must support the subset where horizon in 1..14
       - must include lag/rolling features computed from sales history up to issue_date
   - `build_features_long(issue_date, target_dates)`:
       - for horizons >=15
       - must NOT include lag/rolling y features

   Create 2026 inference feature artifacts using:
   - issue_date = max(ds) in fact_sales_daily (data_through)
   - target_dates = all ds in 2026-01-01..2026-12-31

   Write:
   - /data/processed/inference_features_short_2026.parquet
   - /data/processed/inference_features_long_2026.parquet

Outputs:
- /data/processed/train_short.parquet (issue_date, target_date, horizon, y, features...)
- /data/processed/train_long.parquet (issue_date, target_date, horizon, y, features...)
- /data/processed/inference_features_short_2026.parquet
- /data/processed/inference_features_long_2026.parquet

Deliverables:
- /src/forecasting/features/build_datasets.py
- /src/forecasting/features/feature_builders.py
```

### Expected Outputs
- `/data/processed/train_short.parquet`
- `/data/processed/train_long.parquet`
- `/data/processed/inference_features_short_2026.parquet`
- `/data/processed/inference_features_long_2026.parquet`
- `/src/forecasting/features/build_datasets.py`
- `/src/forecasting/features/feature_builders.py`

### Acceptance Criteria
- train_short has horizons only in [1..14]
- train_long has horizons only in [15..380] (but may be empty near end of history if labels don’t exist; that is acceptable)
- train_long does NOT include any y_lag_* or y_roll_* columns
- No NaNs in required calendar/hour/event feature columns (NaNs allowed in lag columns for earliest dates)
- Calendar features include: is_us_federal_holiday and is_new_years_eve
- inference_features_short_2026.parquet exists and only includes ds in 2026 with horizon in [1..14]
- inference_features_long_2026.parquet exists and includes ds in 2026 with horizon in [15..380]

---

## Prompt 8: Backtest harness + baselines

### Dependencies
- Requires outputs from: Prompt 2, Prompt 7

### Input Files
- `/data/processed/fact_sales_daily.parquet`
- `/data/processed/train_short.parquet`
- `/data/processed/train_long.parquet`

### Goal
Implement rolling-origin backtesting harness and baseline models, produce baseline metrics.

### Prompt
```text
Implement a backtest harness and baselines.

Backtest design:
- Use rolling cutoffs T with:
  - minimum train window: 120 days
  - step: 14 days
- For each cutoff:
  - Train baselines on ds <= T
  - Let H_eval = min(380, (ds_max - T).days)  # only evaluate where labels exist
  - Forecast horizons 1..H_eval using only info available at T
  - Score on ds in (T, T+H_eval]

Baselines to implement:
1) Seasonal naive weekly (recursive, no lookahead):
   - p50 = y(ds-7)
   - IMPORTANT: if (ds-7) > train_end_date (i.e., beyond last known actual), use the already-forecast p50 for (ds-7) instead of the true y.
   - p80/p90 can be approximated using historical residual distr...you can set p80/p90 equal to p50 for baseline (document choice).
2) Weekday rolling median:
   - For each weekday, median of last N=8 open observations prior to T.

Metrics:
- wMAPE
- RMSE
- bias (mean forecast / mean actual - 1)
Compute per horizon bucket:
- {1-7, 8-14, 15-30, 31-90, 91-380}

Write outputs:
- /outputs/backtests/metrics_baselines.csv
- /outputs/backtests/preds_baselines.parquet (row-level predictions; required for ensemble fitting)
  Schema (minimum): cutoff_date, model_name, issue_date, target_date, horizon, horizon_bucket, p50, p80, p90, y, is_closed

Backtest runner will call: fit(T) then predict(T, [T+1..T+H_eval])

Deliverables:
- /src/forecasting/backtest/rolling_origin.py
- /src/forecasting/models/baselines.py
```

### Expected Outputs
- `/outputs/backtests/metrics_baselines.csv`
- `/outputs/backtests/preds_baselines.parquet`
- `/src/forecasting/backtest/rolling_origin.py`
- `/src/forecasting/models/baselines.py`

### Acceptance Criteria
- metrics_baselines.csv exists and has at least one row per cutoff per baseline model
- preds_baselines.parquet exists and contains at least one row per cutoff per baseline model
- horizon_bucket values are only in {1-7, 8-14, 15-30, 31-90, 91-380}
- No future leakage in baseline computations

---

## Prompt 9: Train + backtest GBM short-horizon model (H=1–14)

### Dependencies
- Requires outputs from: Prompt 7, Prompt 8

### Input Files
- `/data/processed/train_short.parquet`
- `/outputs/backtests/metrics_baselines.csv`

### Goal
Train a quantile GBM model for horizons 1–14 and evaluate it fairly via rolling-origin backtest.

### Prompt
```text
Implement the GBM short-horizon model.

Requirements:
- Horizons: 1..14
- Quantiles: 0.5, 0.8, 0.9
- Use lag features and known-future features (calendar, hours, events)
- Use LightGBM (preferred) 
- Train either:
  - one model per quantile per horizon, OR
  - one multi-quantile approach (document choice)
- Must integrate with the backtest harness from Prompt 8:
  - For each cutoff T:
    - Train on rows where issue_date <= T and target_date <= T (labels available)
    - Predict for target dates in (T, T+14] for evaluation

Outputs:
- /outputs/backtests/metrics_gbm_short.csv
- /outputs/backtests/preds_gbm_short.parquet (required; store per cutoff, per date predictions)

Deliverables:
- /src/forecasting/models/gbm_short.py
```

### Expected Outputs
- `/outputs/backtests/metrics_gbm_short.csv`
- `/outputs/backtests/preds_gbm_short.parquet`
- `/src/forecasting/models/gbm_short.py`

### Acceptance Criteria
- metrics_gbm_short.csv exists and matches the metric schema used for baselines
- preds_gbm_short.parquet exists and includes columns: cutoff_date, issue_date, target_date, horizon, p50, p80, p90, y
- wMAPE improves vs seasonal naive for horizons 1–14 on average (report delta in summary)

---

## Prompt 10: Train + backtest GBM long-horizon model (H=15–380)

### Dependencies
- Requires outputs from: Prompt 7, Prompt 8

### Input Files
- `/data/processed/train_long.parquet`
- `/outputs/backtests/metrics_baselines.csv`

### Goal
Train a quantile GBM model for horizons 15–380 using only known-future features and evaluate it.

### Prompt
```text
Implement the GBM long-horizon model.

Requirements:
- Horizons: 15..380
- Quantiles: 0.5, 0.8, 0.9
- Use only known-future features (calendar, hours, events). DO NOT use lag/rolling y features.
- Use LightGBM (preferred) 
- Must integrate with the backtest harness:
  - For each cutoff T:
    - Train on rows where issue_date <= T and target_date <= T (labels available)
    - Let H_eval = min(380, (ds_max - T).days)  # only evaluate where labels exist
    - target_dates = [T+15 .. T+H_eval] (only where labels exist for evaluation)
    - X_pred = build_features_long(issue_date=T, target_dates=target_dates)
  - Predict for target dates in (T, T+H_eval] for evaluation (longer horizons only where labels exist)

Outputs:
- /outputs/backtests/metrics_gbm_long.csv
- /outputs/backtests/preds_gbm_long.parquet (required; store per cutoff, per date predictions)

Deliverables:
- /src/forecasting/models/gbm_long.py
```

### Expected Outputs
- `/outputs/backtests/metrics_gbm_long.csv`
- `/outputs/backtests/preds_gbm_long.parquet`
- `/src/forecasting/models/gbm_long.py`

### Acceptance Criteria
- metrics_gbm_long.csv exists and matches metric schema
- preds_gbm_long.parquet exists and includes columns: cutoff_date, issue_date, target_date, horizon, p50, p80, p90, y
- Long-horizon metrics are computed for buckets including 91–380 when labels exist

---

## Prompt 11: Integrate Chronos-2 forecasting (optional) + backtest outputs

### Dependencies
- Requires outputs from: Prompt 2, Prompt 8

### Input Files
- `/data/processed/fact_sales_daily.parquet`
- `/data/processed/inference_features_short_2026.parquet` (optional; only if covariates supported)
- `/data/processed/inference_features_long_2026.parquet` (optional; only if covariates supported)

### Goal
Integrate Chronos-2 forecasting via AutoGluon TimeSeries and produce quantile forecasts.

### Notes (v1 requirements)
- Run Chronos-2 in **univariate** mode (no covariates passed).
- Generate a full prediction path starting at ds_max + 1 through 2026-12-31, then slice outputs to 2026-01-01..2026-12-31.
- Bridge days 2025-12-23..2025-12-31 are included in the prediction path to reach 2026; in v1 we do not require covariate rows for those dates.

### Prompt
```text
Implement Chronos-2 forecasting integration.

Requirements:
- Use AutoGluon TimeSeries if available.
- Forecast quantiles 0.5, 0.8, 0.9.
- Input series is daily y from fact_sales_daily.parquet.
- Closed days:
  - Option A: keep them as zeros in the series
  - Option B: mark them as missing and impute
  Choose one and document it.

Covariates:
- **v1 requirement:** run univariate (do NOT pass covariates).
- **optional (v2):** if the installed Chronos-2 wrapper supports known future covariates, you may include:
  - open_minutes
  - is_closed
  - aggregated event features (events_active_total etc.)
  In that case, covariates must be generated for the entire prediction span starting at ds_max + 1 (including 2025-12-23..2025-12-31 bridge days), even if final outputs are sliced to 2026 only.

Backtest:
- Integrate with rolling-origin backtest runner and use the same H_eval logic (min(380, ds_max - T)).
- Write /outputs/backtests/metrics_chronos2.csv
- If Chronos-2 is available, also write /outputs/backtests/preds_chronos2.parquet (row-level predictions; required for ensemble fitting)

Deliverables:
- /src/forecasting/models/chronos2.py
```

### Expected Outputs
- `/outputs/backtests/metrics_chronos2.csv`
- `/outputs/backtests/preds_chronos2.parquet` (if available)
- `/src/forecasting/models/chronos2.py`

### Acceptance Criteria
- If Chronos-2 is available, metrics_chronos2.csv is produced and non-empty
- If Chronos-2 is available, preds_chronos2.parquet is produced and non-empty
- If Chronos-2 is NOT available, code gracefully skips and logs a warning

---

## Prompt 12: Ensemble + guardrails + overrides + final 2026 forecast export

### Dependencies
- Requires outputs from: Prompt 2, Prompt 3, Prompt 5, Prompt 7, Prompt 8, Prompt 9, Prompt 10, Prompt 11 (optional)

### Input Files
- /data/processed/fact_sales_daily.parquet
- /data/processed/hours_calendar_2026.parquet
- /data/processed/features/events_daily_2026.parquet
- /data/processed/inference_features_short_2026.parquet
- /data/processed/inference_features_long_2026.parquet
- /data/overrides/demand_overrides.csv (optional)
- /outputs/backtests/metrics_baselines.csv
- /outputs/backtests/metrics_gbm_short.csv
- /outputs/backtests/metrics_gbm_long.csv
- /outputs/backtests/metrics_chronos2.csv (if available)
- /outputs/backtests/preds_baselines.parquet
- /outputs/backtests/preds_gbm_short.parquet
- /outputs/backtests/preds_gbm_long.parquet
- /outputs/backtests/preds_chronos2.parquet (if available)

### Goal
Generate the final 2026 daily forecast file and operational rollups with guardrails and overrides.

### Prompt
```text
Implement ensemble weight fitting, inference forecast generation, guardrails, overrides, and export.

Ensemble fitting:
- Use backtest metrics and predictions to learn weights per model per horizon bucket.
- Models to combine:
  - gbm_short (for h=1..14)
  - gbm_long (for h=15..380)
  - chronos2 (if available)
  - baselines (as fallback)
- Learn weights per horizon bucket {1-7, 8-14, 15-30, 31-90, 91-380}
- Optimization objective: minimize wMAPE of p50 (open days) using merged row-level backtest predictions (preds_*.parquet joined to actual y) per horizon bucket
- Constrain weights to [0,1] and sum to 1
   - If a horizon bucket has insufficient evaluation rows, fall back to the nearest shorter-bucket weights and log the fallback.

Inference:
- issue_date = ds_max from fact_sales_daily.parquet (e.g., 2025-12-22)
- For 2026:
  - get gbm_short predictions for horizons 1..14
  - get gbm_long predictions for horizons 15..380
  - get chronos2 predictions if available (ensure prediction path reaches 2026-12-31; slice to 2026)
  - blend quantiles using weights per bucket

Guardrails:
- If is_closed=1 on ds (from hours_calendar_2026), set p50=p80=p90=0
- Clamp p50/p80/p90 >= 0
- Enforce monotonicity: p50 <= p80 <= p90

Overrides:
- If /data/overrides/demand_overrides.csv exists, apply overrides after initial guardrails and before rollups.
- After applying overrides, re-apply guardrails: is_closed => all quantiles=0, clamp >=0, and enforce monotonicity p50<=p80<=p90.

Exports:
- /outputs/forecasts/forecast_daily_2026.csv with columns:
  - ds, p50, p80, p90, is_closed, open_minutes, data_through
- Create rollups aligned to operations:
  - /outputs/forecasts/rollups_ordering.csv
  - /outputs/forecasts/rollups_scheduling.csv

Also write:
- /outputs/backtests/metrics_ensemble.csv
- /outputs/backtests/summary.md

Deliverables:
- /src/forecasting/models/ensemble.py
- /src/forecasting/pipeline/export.py
```

### Expected Outputs
- `/outputs/forecasts/forecast_daily_2026.csv`
- `/outputs/forecasts/rollups_ordering.csv`
- `/outputs/forecasts/rollups_scheduling.csv`
- `/outputs/backtests/metrics_ensemble.csv`
- `/outputs/backtests/summary.md`
- `/src/forecasting/models/ensemble.py`
- `/src/forecasting/pipeline/export.py`

### Acceptance Criteria
- forecast_daily_2026.csv has exactly 365 rows
- All closed days have p50=p80=p90=0
- No negative forecasts
- Monotonicity holds for all rows (p50<=p80<=p90)
- Rollups cover correct windows and totals match daily sums

---

## Prompt 13: End-to-end daily runner orchestration + smoke test

### Dependencies
- Requires outputs from: Prompts 1–12

### Input Files
- All prior inputs

### Goal
Create a single daily runner that executes the full pipeline in correct order and verify with a smoke test.

### Prompt
```text
Implement the end-to-end runner that ties all steps together.

Runner requirements:
- `python -m forecasting.pipeline.run_daily` should:
  1) ingest sales
  2) build hours calendars
  3) ingest/normalize events
  4) build event daily features
  5) compute priors
  6) build datasets and inference features
  7) run backtests (optional flag)
  8) train models
  9) ensemble + export forecast + rollups

Add CLI flags:
- --issue-date YYYY-MM-DD (default ds_max)
- --run-backtests true/false (default false)
- --skip-chronos true/false (default false)
- --dry-run true/false (default false; runs through data prep only)

Smoke test:
- Run dry-run on provided history and event files
- Run full forecast export for 2026 (without training if models missing; must fail gracefully with clear messages)

Deliverables:
- /src/forecasting/pipeline/run_daily.py updated
- /outputs/reports/smoke_test.md with results and file checks
```

### Expected Outputs
- `/outputs/reports/smoke_test.md`
- Updated `/src/forecasting/pipeline/run_daily.py`

### Acceptance Criteria
- Runner executes without crashing on dry-run
- If models are not trained, runner logs clear next steps
- When models are trained, runner produces forecast_daily_2026.csv and rollups
