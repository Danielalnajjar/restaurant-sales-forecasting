# Sales Forecasting System

Daily sales forecasting system for restaurant operations (Wok to Walk, Fashion Show Mall, Las Vegas).

## Overview

This system produces daily net-sales forecasts for 2026 with P50/P80/P90 quantiles using:
- GBM short-horizon model (H=1-14 days)
- GBM long-horizon model (H=15-380 days)
- Chronos-2 univariate model (optional)
- Ensemble with horizon-based weighting

## Project Structure

```
/src/forecasting/          # Source code
  /io/                     # Data I/O utilities
  /features/               # Feature engineering
  /models/                 # Model implementations
  /backtest/               # Backtesting framework
  /pipeline/               # End-to-end pipeline
/configs/                  # Configuration files
/data/                     # Data files
  /raw/                    # Raw input data
  /processed/              # Processed datasets
  /events/                 # Event calendars
  /overrides/              # Manual overrides
  /models/                 # Trained model artifacts
/outputs/                  # Output files
  /forecasts/              # 2026 forecasts
  /backtests/              # Backtest results
  /reports/                # Reports and logs
```

## Installation

```bash
pip install -e .
```

Optional (for Chronos-2):
```bash
pip install -e ".[chronos]"
```

## Usage

### Run full pipeline

```bash
python -m forecasting.pipeline.run_daily
```

### Run with specific issue date

```bash
python -m forecasting.pipeline.run_daily --issue-date 2025-12-22
```

### Run with custom config

```bash
python -m forecasting.pipeline.run_daily --config configs/config.yaml
```

## Configuration

Edit `configs/config.yaml` to adjust:
- Forecast horizons
- Quantiles
- Backtest parameters
- Event feature settings

## Outputs

### Daily forecasts
- `/outputs/forecasts/forecast_daily_2026.csv` - Daily P50/P80/P90 forecasts

### Backtests
- `/outputs/backtests/metrics_*.csv` - Model metrics
- `/outputs/backtests/preds_*.parquet` - Row-level predictions
- `/outputs/backtests/summary.md` - Backtest summary report

### Rollups
- `/outputs/forecasts/rollups_ordering.csv` - Ordering projections
- `/outputs/forecasts/rollups_scheduling.csv` - Scheduling projections

## Development

The system is built following 13 sequential prompts from `PROMPTS_v2.md`:
1. Project bootstrap + environment setup
2. Ingest sales data
3. Build hours calendars
4. Load event calendars
5. Build event features
6. Compute event uplift priors
7. Build supervised datasets
8. Implement baselines + backtest harness
9. Train GBM short-horizon
10. Train GBM long-horizon
11. Integrate Chronos-2
12. Ensemble + forecast generation
13. End-to-end pipeline integration

See `SPEC_v2.md` for complete system specification.
