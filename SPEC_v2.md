# Sales Forecasting System Specification

## 1. Overview

### 1.1 Objective
Produce **daily** forecasts of **net sales** (excluding tax, service charges, delivery fees, comps, refunds, voids) for a **single Toast POS location** in **Las Vegas (America/Los_Angeles)** for **2026-01-01 through 2026-12-31**.

Forecast outputs must be operationally usable for:
- Staffing projections
- Ordering/purchasing projections
- Prep projections
- Scheduling
- Light scenario planning (base/high/low)

### 1.2 Forecast products (what ops consumes)
Per day:
- p50, p80, p90 forecast quantiles
- is_closed flag and open_minutes for that day
- optional rollups aligned to ordering/scheduling cycles

### 1.3 Forecast horizons
We support multiple horizons off a given issue_date:
- **Short horizon:** 1–14 days (daily ops: ordering and scheduling)
- **Long horizon:** 15–380 days (budgeting / longer-range planning)

Notes:
- 2026 full-year forecast from last history day (2025-12-22) requires reaching 2026-12-31 which is 374 days ahead; use H up to 380.

### 1.4 Constraints / rules
- **No leakage:** all features must be available at forecast time.
- **Closures:** treat any day with net sales < $200 as closed (for modeling).
- **Hours:** known by date; default hours plus overrides; holiday closures/reduced hours allowed.
- **Events:** many demand drivers shift year-to-year; system must incorporate event-aware modeling without leaking target.

### 1.5 Data sources (high-level)
- Toast daily sales export (historical)
- Hours calendar (history + 2026)
- Event calendar for 2026 (exact dates) + 2025↔2026 recurring mapping
- Optional manual override file for operational adjustments

### 1.6 Recommended model architecture (v1)
- Baselines (for sanity + fallback)
- GBM short-horizon (1–14) with lags + calendar + hours + events
- GBM long-horizon (15–380) with known-future features only (calendar + hours + events)
- Chronos-2 univariate (if available) as an additional signal for ensemble
- Ensemble weights learned per horizon bucket from backtests; export quantiles with guardrails + overrides

---

## 2. Data Model

### 2.1 Input Files (what you provide)

#### 2.1.1 Toast daily sales export (history)
**Path:**
- `/data/raw/Sales by day.csv`

**Required columns (minimum):**
- `business_date` (date) — already exported by Toast as business date
- `net_sales` (numeric) — net of discounts; excludes tax/service charges/delivery fees/comps/refunds/voids (per operator)
- (optional) `transactions` (integer) — not required for v1

**Closure rule:** any day with `net_sales < 200` should be treated as closed (is_closed=1).

#### 2.1.2 Hours calendars (2026)
**Paths:**
- `/data/raw/hours_calendar_2026_v2.csv`
- `/data/raw/hours_overrides_2026_v2.csv`

Hours defaults:
- Mon–Thu 11:00–20:00
- Fri–Sat 10:00–21:00
- Sun 11:00–19:00
- December extended hours repeat: **Dec 8–Dec 30** (Mon–Thu extended per operator)

Holiday closures/reduced hours:
- New Year’s Eve / New Year’s Day: closed/short hours as provided
- Christmas Eve: 10:00–18:00
- Any other closures appear via hours calendar

#### 2.1.3 Events calendars
**Paths:**
- `/data/events/events_2026_exact_dates_clean_v2.csv` (exact 2026 event dates)
- `/data/events/recurring_event_mapping_2025_2026_clean.csv` (maps 2025 event windows to 2026)

Notes:
- `/data/events/events_2026_exact_dates_clean_v2.csv` (only events with exact start/end dates; 2026-only QA/scenario input; NOT sufficient for historical model-training features because it contains only 2026 dates)

#### 2.1.4 Manual overrides (optional but supported)
**Path:**
- `/data/overrides/demand_overrides.csv`

Used for one-off adjustments when operator knowledge exceeds model (e.g., known mall closures, known staffing constraints, extraordinary events).

Override application rule:
- Overrides apply **after** model ensembling + initial guardrails, but **before** operational rollups.
- After applying overrides, re-apply guardrails: `is_closed` => all quantiles = 0, clamp >= 0, and enforce monotonicity `p50 <= p80 <= p90`.

---

### 2.2 Generated Files (what the system creates)

#### 2.2.1 Canonical fact table (history)
**Path:**
- `/data/processed/fact_sales_daily.parquet`

Schema:
- `ds` (date, local timezone business date)
- `y` (float; net sales target)
- `is_closed` (bool; derived from y < 200 and/or hours calendar)
- `open_minutes` (int; derived from hours calendar; 0 if closed)
- `data_source` (string; e.g., "toast_export")
- `notes` (string, optional)

#### 2.2.2 Hours calendar (history + 2026)
**Paths:**
- `/data/processed/hours_calendar_history.parquet` (for 2024-11-19→2025-12-22)
- `/data/processed/hours_calendar_2026.parquet` (for 2026-01-01→2026-12-31)

Schema:
- `ds` (date)
- `open_time_local` (time, optional)
- `close_time_local` (time, optional)
- `open_minutes` (int)
- `is_closed` (bool)

#### 2.2.3 Event daily features (history + 2026)
**Paths:**
- `/data/processed/features/events_daily_history.parquet` (for 2024-11-19→2025-12-22)
- `/data/processed/features/events_daily_2026.parquet` (for 2026-01-01→2026-12-31)

Schema:
- `ds` (date)
- `events_active_total` (int)
- `events_active_by_category__*` (int; optional)
- `events_active_by_proximity__*` (int; optional)
- `event_family__{name}` (0/1; top-K recurring families)

#### 2.2.4 Uplift priors (optional feature, but included in v1)
**Path:**
- `/data/processed/event_uplift_priors.parquet`

Schema (per event_family):
- `event_family`
- `uplift_mean` (float; multiplicative or additive, as specified)
- `uplift_strength` (float; shrinkage strength)
- `confidence_bucket` (string)

#### 2.2.5 Model-ready datasets
**Paths:**
- `/data/processed/train_short.parquet` (issue_date, target_date, h=1..14)
- `/data/processed/train_long.parquet` (issue_date, target_date, h=15..380)

#### 2.2.6 Inference feature sets (2026)
**Paths:**
- `/data/processed/inference_features_short_2026.parquet`
- `/data/processed/inference_features_long_2026.parquet`

---

### 2.3 Output Files (what operations consumes)

#### 2.3.1 Daily forecast (2026)
**Path:**
- `/outputs/forecasts/forecast_daily_2026.csv`

Schema:
- `ds` (YYYY-MM-DD)
- `p50`, `p80`, `p90` (float)
- `is_closed` (bool)
- `open_minutes` (int)
- `data_through` (YYYY-MM-DD; last history date used, e.g. 2025-12-22)

Rules:
- If `is_closed=1` then `p50=p80=p90=0`.

#### 2.3.2 Operational rollups (optional)
**Paths:**
- `/outputs/forecasts/rollups_ordering.csv`
- `/outputs/forecasts/rollups_scheduling.csv`

Rollups should include:
- snapshot_date (when produced)
- coverage_start, coverage_end
- p50/p80/p90 totals over coverage window
- notes

#### 2.3.3 Audit / diagnostics
**Paths:**
- `/outputs/reports/run_log.json`
- `/outputs/reports/data_audit_summary.md`

#### 2.3.4 Backtest report artifacts
**Paths:**
- `/outputs/backtests/metrics_baselines.csv`
- `/outputs/backtests/metrics_gbm_short.csv`
- `/outputs/backtests/metrics_gbm_long.csv`
- `/outputs/backtests/metrics_chronos2.csv` (if available)
- `/outputs/backtests/metrics_ensemble.csv`
- `/outputs/backtests/preds_baselines.parquet` (row-level; required for ensemble fitting)
- `/outputs/backtests/preds_gbm_short.parquet` (row-level; required for ensemble fitting)
- `/outputs/backtests/preds_gbm_long.parquet` (row-level; required for ensemble fitting)
- `/outputs/backtests/preds_chronos2.parquet` (row-level; required for ensemble fitting if Chronos-2 is available)
- `/outputs/backtests/preds_ensemble.parquet` (row-level; optional)
- `/outputs/backtests/summary.md`

---

## 3. Feature Engineering

### 3.1 Calendar Features
Required:
- `dow` (0=Mon..6=Sun)
- `is_weekend`
- `weekofyear`, `month`, `dayofyear`
- `is_month_start`, `is_month_end`
- Fourier terms: `doy_sin_1`, `doy_cos_1` (optionally 2nd harmonic)
- Holiday flags (required):
  - `is_us_federal_holiday` (bool)
  - `is_new_years_eve` (bool; ds month-day == 12-31)
  - `holiday_name` (string, optional)
  - Note: major holidays may also appear in the event calendar; avoid double-counting by keeping these as separate calendar flags (do not add them into events_active_total).

### 3.2 Lag Features (short-horizon only)
Computed as-of issue_date:
- `y_lag_1`, `y_lag_7`, `y_lag_14`
- `y_roll_mean_7` (mean of open days in [T-7, T-1])
- optional `y_roll_mean_28`

Constraints:
- Must use only ds <= issue_date (no leakage)
- Lags are NOT used for horizons >= 15

### 3.3 Event Features

#### 3.3.1 Daily event expansion
Build model-training event instances from `recurring_event_mapping_2025_2026_clean.csv` so event features exist in both history and 2026:

- For history (2024-11-19..2025-12-22): treat each row as an event instance with `start_date = start_2025`, `end_date = end_2025`
- For 2026: treat each row as an event instance with `start_date = start_2026`, `end_date = end_2026`

Expand each instance into daily rows for all `ds` in `[start_date, end_date]` (inclusive).

Note:
- `events_2026_exact_dates_clean_v2.csv` includes many 2026 one-offs/new events that do NOT exist in `recurring_event_mapping_2025_2026_clean.csv`.
- Do not filter the 2026 event list down to only mapped recurring events; the mapping is for priors/learning, not for defining which 2026 events exist.

#### 3.3.2 Multi-day windows and lead/lag
For each day ds, compute:
- active window indicators (event active on ds)
- optional lead/lag counts (e.g., events in next 3 days, past 3 days)
- category aggregates: `events_active_by_category__{cat}`
- proximity aggregates: `events_active_by_proximity__{prox}`

#### 3.3.3 Top-K event families (one-hot)
To avoid high-dimensional sparse features:
- Select top-K event families by **active days in history** (K default 40)
- Create one-hot columns: `event_family__{family}`

Event family definition:
- Use `event_family` from recurring mapping as the family key.

### 3.4 Hours Features
From hours calendar:
- `open_minutes`
- `is_closed` (open_minutes==0)

Optional derived:
- `is_extended_hours` (open_minutes above default for that weekday)
- `is_short_hours` (open_minutes below default)

---

## 4. Models

### 4.1 Baselines

#### 4.1.1 Seasonal naive (weekly)
- `y_hat(ds) = y(ds - 7 days)` for open days
- For multi-step horizons, seasonal naive must be computed recursively: at horizon h>7, use the forecasted value for ds-7 if ds-7 is beyond the last known actual.

#### 4.1.2 Weekday rolling median
- For each weekday, median of last N open observations (e.g., N=8)

Baselines produce p50; set p80/p90 = p50 (or use residual-based spread) but document choice.

### 4.2 GBM (Short-Horizon)
**Purpose:** maximize accuracy for 1–14 days using lags + known-future features.

- Model: LightGBM quantile regression (or 3 separate quantile models)
- Features: calendar(target_date), hours(target_date), event(target_date), lags(issue_date)
- Horizons: h in [1..14]

### 4.3 GBM (Long-Horizon)
**Purpose:** stable forecasts for 15–380 days using only known-future features.

- Model: LightGBM quantile regression
- Features: calendar(target_date), hours(target_date), event(target_date)
- Horizons: `h in [15..380]`
- No lags; do not use future y-derived features.

### 4.4 Chronos-2
**Purpose:** add a strong pretrained time-series prior and reduce reliance on limited local history.

- Run as a separate forecaster on the univariate sales series (open-adjusted).
- Use Chronos-2 via a wrapper (e.g., AutoGluon TimeSeries) if available.

Covariates:
- **v1 requirement:** run Chronos-2 in **univariate** mode (no covariates passed to the model).
  - Reason: history ends at 2025-12-22, but a full-year 2026 forecast issued from that endpoint requires predicting through the 2025-12-23..2025-12-31 bridge days; we do not require covariate rows for those dates in v1.
- **optional (v2):** if the installed Chronos-2 wrapper supports known future covariates, you may supply:
  - calendar features
  - hours features
  - aggregated event features
  In that case, covariates must be generated for the entire prediction span starting at `ds_max + 1` (including 2025-12-23..2025-12-31), even if final outputs are sliced to 2026 only.

### 4.5 Ensemble Logic
Combine forecasts from:
- GBM short (h=1..14)
- GBM long (h=15..380)
- Chronos-2 (if available)
- Baselines (as fallback)

Rules:
- For each horizon bucket, compute weights from backtests:
  - horizon buckets:
    - 1–7
    - 8–14
    - 15–30
    - 31–90
      - 91–380

Weights are learned from merged row-level backtest prediction files (not from aggregated metrics-only CSVs).
If a horizon bucket has insufficient evaluation rows, fall back to the nearest shorter-bucket weights and log the fallback.

Final forecast per day and quantile:
- Use weighted average of model quantile outputs per bucket
- Apply closure/hour guardrails
- Apply manual overrides (if any) then re-apply guardrails

---

## 5. Evaluation

### 5.1 Backtest Design
Rolling-origin backtest:
- choose cutoffs T spaced every 14 days
- minimum training window: 120 days
- for each cutoff:
  - train on data available up to cutoff
  - forecast the next 1–90 days (minimum); forecast up to 380 days when evaluation data exists (i.e., only where labels exist in history)
  - save row-level prediction outputs per model and cutoff to `/outputs/backtests/preds_*.parquet`

### 5.2 Metrics
Primary:
- wMAPE (weighted MAPE; weights by actual sales)
- Bias (mean forecast / mean actual - 1)
- Peak-day error (top 5% actual days)

Secondary:
- RMSE
- MASE (optional)

Quantile sanity:
- p50 <= p80 <= p90 always
- quantile coverage approximate (diagnostic)

### 5.3 Acceptance Thresholds
No guaranteed numeric target; accept if:
- Improves wMAPE vs seasonal naive for horizons 1–14 and 15–90
- Controls bias within reasonable bounds (e.g., |bias| < 5–10% over backtest)
- Peak-day error materially reduced vs baseline
- Forecast supports “don’t run out / don’t understaff” operational constraints

---

## 6. Production Pipeline

### 6.1 Daily Run Flow
Daily scheduled run (once per day):
1. Ingest latest sales CSV (or Toast API export)
2. Build/update processed fact table
3. Update hours calendar (history + 2026)
4. Update events calendar (refresh as needed; v1 assumes provided event files)
5. Build features for issue_date = ds_max
6. Generate forecasts:
   - GBM short, GBM long
   - Chronos-2 if available
   - Ensemble with weights
7. Apply guardrails + overrides
8. Export forecast and rollups

### 6.2 Snapshot Generation
Create rollups aligned to operational cadence:
- Ordering windows:
  - Sunday order covers through Saturday
  - Wednesday order covers through next Wednesday
- Scheduling windows:
  - Schedule week: Wednesday–Tuesday
  - Publish on Friday

Each rollup file includes totals for p50/p80/p90 and indicates coverage window.

### 6.3 Override Workflow
- Operator edits `/data/overrides/demand_overrides.csv` with date-specific adjustments
- Overrides can set:
  - absolute p50 override (and optionally p80/p90)
  - multiplicative uplift factor
  - closure forced
- Overrides apply after ensemble and initial guardrails but before export rollups.
- After applying overrides, re-apply monotonicity and closure guardrails to ensure `p50 <= p80 <= p90` and closed days are 0.

---

## 7. File Manifest (complete list of all files with paths)

### 7.1 Raw inputs (provided by operator)
- `/data/raw/Sales by day.csv`
- `/data/raw/hours_calendar_2026_v2.csv`
- `/data/raw/hours_overrides_2026_v2.csv`
- `/data/events/events_2026_exact_dates_clean_v2.csv`
- `/data/events/recurring_event_mapping_2025_2026_clean.csv`
- `/data/overrides/demand_overrides.csv` (optional)

### 7.2 Processed data (system-generated)
- `/data/processed/fact_sales_daily.parquet`
- `/data/processed/hours_calendar_history.parquet`
- `/data/processed/hours_calendar_2026.parquet`
- `/data/processed/features/events_daily_history.parquet`
- `/data/processed/features/events_daily_2026.parquet`
- `/data/processed/event_uplift_priors.parquet`
- `/data/processed/train_short.parquet`
- `/data/processed/train_long.parquet`
- `/data/processed/inference_features_short_2026.parquet`
- `/data/processed/inference_features_long_2026.parquet`

### 7.3 Outputs (evaluation and reports)
- `/outputs/forecasts/forecast_daily_2026.csv`
- `/outputs/forecasts/rollups_ordering.csv`
- `/outputs/forecasts/rollups_scheduling.csv`
- `/outputs/reports/run_log.json`
- `/outputs/reports/data_audit_summary.md`
- `/outputs/backtests/metrics_baselines.csv`
- `/outputs/backtests/metrics_gbm_short.csv`
- `/outputs/backtests/metrics_gbm_long.csv`
- `/outputs/backtests/metrics_chronos2.csv` (if available)
- `/outputs/backtests/metrics_ensemble.csv`
- `/outputs/backtests/preds_baselines.parquet` (row-level; required for ensemble fitting)
- `/outputs/backtests/preds_gbm_short.parquet` (row-level; required for ensemble fitting)
- `/outputs/backtests/preds_gbm_long.parquet` (row-level; required for ensemble fitting)
- `/outputs/backtests/preds_chronos2.parquet` (row-level; required for ensemble fitting if Chronos-2 is available)
- `/outputs/backtests/preds_ensemble.parquet` (row-level; optional)
- `/outputs/backtests/summary.md`
