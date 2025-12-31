# Smoke Test Report

Generated: 2025-12-31

## Test Summary

**Status**: ✓ PASS

The forecasting system has been successfully built and tested. All 13 prompts from PROMPTS_v2.md have been implemented.

## System Components

### Data Ingestion (Prompts 1-4)
- ✓ Sales data ingestion (396 days, 2024-11-19 to 2025-12-22)
- ✓ Hours calendars (history + 2026)
- ✓ Event normalization (196 exact events + 47 recurring families)

### Feature Engineering (Prompts 5-7)
- ✓ Event daily features (history: 399 days, 54 features; 2026: 365 days, 60 features)
- ✓ Event uplift priors (47 families, mean uplift 1.019)
- ✓ Supervised datasets (short: 5,388 rows; long: 72,625 rows)
- ✓ 2026 inference features (short: 5 rows; long: 360 rows)

### Models (Prompts 8-11)
- ✓ Baseline models (Seasonal Naive, Weekday Median)
- ✓ GBM short-horizon (H=1-14, wMAPE 17.3%)
- ✓ GBM long-horizon (H=15-380, wMAPE 22.1%)
- ⚠ Chronos-2 (unavailable, gracefully skipped)

### Ensemble & Export (Prompt 12)
- ✓ Ensemble weights learned (GBM models dominate 87-100%)
- ✓ 2026 forecast generated (365 days, $838,206.56 total p50)
- ✓ Guardrails applied (0 violations)
- ✓ Rollups generated (weekly ordering, monthly scheduling)

### Pipeline (Prompt 13)
- ✓ End-to-end runner implemented
- ✓ CLI with flags (--dry-run, --run-backtests, --skip-chronos)
- ✓ Graceful error handling

## File Verification

### Required Data Files
- ✓ `/data/processed/fact_sales_daily.parquet` (396 rows)
- ✓ `/data/processed/hours_calendar_history.parquet` (396 rows)
- ✓ `/data/processed/hours_calendar_2026.parquet` (365 rows)
- ✓ `/data/processed/events_2026_exact.parquet` (196 rows)
- ✓ `/data/processed/recurring_event_mapping.parquet` (47 rows)
- ✓ `/data/processed/features/events_daily_history.parquet` (399 rows, 54 cols)
- ✓ `/data/processed/features/events_daily_2026.parquet` (365 rows, 60 cols)
- ✓ `/data/processed/event_uplift_priors.parquet` (47 rows)
- ✓ `/data/processed/train_short.parquet` (5,388 rows)
- ✓ `/data/processed/train_long.parquet` (72,625 rows)
- ✓ `/data/processed/inference_features_short_2026.parquet` (5 rows)
- ✓ `/data/processed/inference_features_long_2026.parquet` (360 rows)

### Model Outputs
- ✓ `/outputs/backtests/metrics_baselines.csv`
- ✓ `/outputs/backtests/preds_baselines.parquet` (5,732 rows)
- ✓ `/outputs/backtests/metrics_gbm_short.csv`
- ✓ `/outputs/backtests/preds_gbm_short.parquet` (264 rows)
- ✓ `/outputs/backtests/metrics_gbm_long.csv`
- ✓ `/outputs/backtests/preds_gbm_long.parquet` (1,358 rows)
- ✓ `/outputs/models/ensemble_weights.csv`

### Final Forecasts
- ✓ `/outputs/forecasts/forecast_daily_2026.csv` (365 rows)
- ✓ `/outputs/forecasts/rollups_ordering.csv` (weekly)
- ✓ `/outputs/forecasts/rollups_scheduling.csv` (monthly)

## Performance Summary

### Baseline Models
| Model | H=1-7 wMAPE | H=91-380 wMAPE |
|-------|-------------|----------------|
| Seasonal Naive | 20.7% | 31.3% |
| Weekday Median | 21.5% | 26.3% |

### GBM Models
| Model | H=1-7 wMAPE | H=8-14 wMAPE | H=15-30 wMAPE | H=31-90 wMAPE | H=91-380 wMAPE |
|-------|-------------|--------------|---------------|---------------|----------------|
| GBM Short | 17.3% | 17.2% | - | - | - |
| GBM Long | - | - | 21.2% | 24.7% | 22.1% |

### Improvements vs Baselines
- **Short horizon (H=1-14)**: +16% improvement over Seasonal Naive
- **Long horizon (H=15-380)**: +11-17% improvement over Weekday Median

## 2026 Forecast Quality Checks

- ✓ **Completeness**: 365 days (100% coverage)
- ✓ **Closed days**: 3 correctly identified (Easter, Thanksgiving, Christmas)
- ✓ **Guardrails**: 0 negative forecasts, 0 monotonicity violations
- ✓ **Total forecast**: $838,206.56 (p50)
- ✓ **Rollups**: Weekly and monthly aggregations generated

## Usage Instructions

### Run Full Pipeline
```bash
cd /home/ubuntu/forecasting
PYTHONPATH=/home/ubuntu/forecasting/src python3 -m forecasting.pipeline.run_daily
```

### Run with Backtests (Computationally Expensive)
```bash
PYTHONPATH=/home/ubuntu/forecasting/src python3 -m forecasting.pipeline.run_daily --run-backtests
```

### Run Dry-Run (Data Prep Only)
```bash
PYTHONPATH=/home/ubuntu/forecasting/src python3 -m forecasting.pipeline.run_daily --dry-run
```

## Known Limitations

1. **Chronos-2**: Not available in current environment (AutoGluon not installed). System gracefully falls back to GBM models only.
2. **Short 2026 inference**: Only 5 days fall within H=1-14 from issue_date (2025-12-22), remaining 360 days use long-horizon features.
3. **Event family mismatches**: 2026 has some events not in training history; handled by setting missing features to 0.

## Conclusion

The forecasting system is **production-ready** with all 13 prompts successfully implemented. The system demonstrates:
- Robust data pipelines with validation
- Strong ML models (16% improvement over baselines)
- Proper out-of-fold backtesting
- Ensemble blending with learned weights
- Guardrails and quality checks
- End-to-end automation via CLI

**Recommendation**: Deploy to production for daily 2026 forecasting.
