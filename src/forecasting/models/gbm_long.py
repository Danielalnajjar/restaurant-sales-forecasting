"""GBM long-horizon model (H=15-380) with known-future features only."""

import logging
import pickle
from pathlib import Path

import lightgbm as lgb
import pandas as pd

from forecasting.features.feature_builders import build_features_long

logger = logging.getLogger(__name__)


class GBMLongHorizon:
    """Quantile GBM model for long horizons (15-380 days)."""

    def __init__(self, quantiles=[0.5, 0.8, 0.9]):
        self.quantiles = quantiles
        self.models = {}  # One model per quantile
        self.feature_cols = None

    def fit(self, df_train: pd.DataFrame):
        """
        Train GBM models for each quantile.

        Parameters
        ----------
        df_train : pd.DataFrame
            Training data with features and y label (NO LAG FEATURES)
        """
        # Identify feature columns (exclude metadata and label)
        exclude_cols = ['issue_date', 'target_date', 'horizon', 'y', 'is_closed',
                       'open_time_local', 'close_time_local']
        self.feature_cols = [col for col in df_train.columns if col not in exclude_cols]

        # Verify no lag features
        lag_cols = [col for col in self.feature_cols if 'lag' in col or 'roll' in col]
        if lag_cols:
            raise ValueError(f"Long-horizon model should not have lag features: {lag_cols}")

        logger.info(f"Training GBM long-horizon with {len(self.feature_cols)} features")
        logger.info(f"Training samples: {len(df_train)}")

        X_train = df_train[self.feature_cols].fillna(0)
        y_train = df_train['y'].values

        # Train one model per quantile
        for q in self.quantiles:
            logger.info(f"Training quantile {q}...")

            params = {
                'objective': 'quantile',
                'alpha': q,
                'metric': 'quantile',
                'num_leaves': 31,
                'learning_rate': 0.05,
                'feature_fraction': 0.8,
                'bagging_fraction': 0.8,
                'bagging_freq': 5,
                'verbose': -1,
            }

            train_data = lgb.Dataset(X_train, label=y_train)

            model = lgb.train(
                params,
                train_data,
                num_boost_round=200,
                valid_sets=[train_data],
                callbacks=[lgb.early_stopping(stopping_rounds=20, verbose=False)]
            )

            self.models[q] = model

        logger.info("GBM long-horizon training complete")

    def predict(self, df_features: pd.DataFrame) -> pd.DataFrame:
        """
        Predict for given features.

        Parameters
        ----------
        df_features : pd.DataFrame
            Features for prediction

        Returns
        -------
        pd.DataFrame
            Predictions with target_date, p50, p80, p90
        """
        # Add missing columns with 0
        for col in self.feature_cols:
            if col not in df_features.columns:
                df_features[col] = 0

        X_pred = df_features[self.feature_cols].fillna(0)

        predictions = df_features[['target_date']].copy()

        for q in self.quantiles:
            col_name = f'p{int(q*100)}'
            predictions[col_name] = self.models[q].predict(X_pred)

        return predictions

    def save(self, path: str):
        """Save model to disk."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump({
                'models': self.models,
                'feature_cols': self.feature_cols,
                'quantiles': self.quantiles,
            }, f)
        logger.info(f"Saved GBM long model to {path}")

    @classmethod
    def load(cls, path: str):
        """Load model from disk."""
        with open(path, 'rb') as f:
            data = pickle.load(f)

        model = cls(quantiles=data['quantiles'])
        model.models = data['models']
        model.feature_cols = data['feature_cols']

        logger.info(f"Loaded GBM long model from {path}")
        return model


def run_gbm_long_backtest(
    train_data_path: str = "data/processed/train_long.parquet",
    sales_fact_path: str = "data/processed/fact_sales_daily.parquet",
    hours_history_path: str = "data/processed/hours_calendar_history.parquet",
    events_history_path: str = "data/processed/features/events_daily_history.parquet",
    output_metrics_path: str = "outputs/backtests/metrics_gbm_long.csv",
    output_preds_path: str = "outputs/backtests/preds_gbm_long.parquet",
    min_train_days: int = 120,
    step_days: int = 28,  # Use larger step for long horizon
    max_horizon: int = 380,
) -> tuple:
    """Run rolling-origin backtest for GBM long-horizon model."""

    logger.info("Running GBM long-horizon backtest")

    # Load data
    df_train_full = pd.read_parquet(train_data_path)
    df_sales = pd.read_parquet(sales_fact_path)
    df_hours = pd.read_parquet(hours_history_path)
    df_events = pd.read_parquet(events_history_path)

    ds_min = df_sales['ds'].min()
    ds_max = df_sales['ds'].max()

    # Define cutoff dates (fewer cutoffs for long horizon)
    first_cutoff = ds_min + pd.Timedelta(days=min_train_days)
    cutoff_dates = pd.date_range(start=first_cutoff, end=ds_max - pd.Timedelta(days=30), freq=f'{step_days}D')

    logger.info(f"Running backtest with {len(cutoff_dates)} cutoffs")

    all_preds = []

    for cutoff_date in cutoff_dates:
        logger.info(f"Cutoff: {cutoff_date}")

        # Train data: issue_date <= cutoff AND target_date <= cutoff
        df_train = df_train_full[
            (df_train_full['issue_date'] <= cutoff_date) &
            (df_train_full['target_date'] <= cutoff_date)
        ]

        if len(df_train) < 500:
            logger.warning(f"Insufficient training data at cutoff {cutoff_date}")
            continue

        # Train model
        model = GBMLongHorizon()
        model.fit(df_train)

        # Eval horizon
        h_eval = min(max_horizon, (ds_max - cutoff_date).days)

        if h_eval < 15:
            continue

        # Predict for H=15 to H_eval
        target_dates = pd.date_range(
            start=cutoff_date + pd.Timedelta(days=15),
            end=cutoff_date + pd.Timedelta(days=h_eval),
            freq='D'
        ).tolist()

        # Filter to dates that exist in sales
        target_dates = [d for d in target_dates if d in df_sales['ds'].values]

        if len(target_dates) == 0:
            continue

        # Build features
        df_features = build_features_long(
            issue_date=cutoff_date,
            target_dates=target_dates,
            df_hours=df_hours,
            df_events=df_events,
        )

        # Predict
        preds = model.predict(df_features)
        preds['cutoff_date'] = cutoff_date
        preds['issue_date'] = cutoff_date
        preds['model_name'] = 'gbm_long'

        # Add labels
        preds = preds.merge(
            df_sales[['ds', 'y', 'is_closed']].rename(columns={'ds': 'target_date'}),
            on='target_date',
            how='left'
        )

        # Add horizon and bucket
        preds['horizon'] = (preds['target_date'] - preds['issue_date']).dt.days

        def assign_bucket(h):
            if 15 <= h <= 30:
                return '15-30'
            elif 31 <= h <= 90:
                return '31-90'
            elif 91 <= h <= 380:
                return '91-380'
            else:
                return 'other'

        preds['horizon_bucket'] = preds['horizon'].apply(assign_bucket)

        all_preds.append(preds)

    # Combine predictions
    df_preds = pd.concat(all_preds, ignore_index=True)

    logger.info(f"Total predictions: {len(df_preds)}")

    # Compute metrics
    from forecasting.backtest.rolling_origin import compute_metrics
    df_metrics = compute_metrics(df_preds)
    df_metrics['model_name'] = 'gbm_long'

    # Save outputs
    Path(output_metrics_path).parent.mkdir(parents=True, exist_ok=True)
    df_metrics.to_csv(output_metrics_path, index=False)
    logger.info(f"Saved metrics to {output_metrics_path}")

    Path(output_preds_path).parent.mkdir(parents=True, exist_ok=True)
    df_preds.to_parquet(output_preds_path, index=False)
    logger.info(f"Saved predictions to {output_preds_path}")

    return df_metrics, df_preds


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Run backtest
    df_metrics, df_preds = run_gbm_long_backtest()

    print("\n=== GBM Long-Horizon Backtest Results ===")
    print("\nMetrics by horizon bucket:")
    print(df_metrics.to_string(index=False))

    # Compare with baseline
    df_baseline = pd.read_csv("outputs/backtests/metrics_baselines.csv")
    df_baseline_wm = df_baseline[df_baseline['model_name'] == 'weekday_rolling_median']

    print("\n=== Comparison with Weekday Median ===")
    for bucket in ['15-30', '31-90', '91-380']:
        if bucket in df_metrics['horizon_bucket'].values:
            gbm_wmape = df_metrics[df_metrics['horizon_bucket'] == bucket]['wmape'].values[0]
            wm_wmape = df_baseline_wm[df_baseline_wm['horizon_bucket'] == bucket]['wmape'].values[0]
            improvement = (wm_wmape - gbm_wmape) / wm_wmape * 100
            print(f"{bucket}: GBM {gbm_wmape:.3f} vs WM {wm_wmape:.3f} ({improvement:+.1f}% improvement)")
