"""Ensemble model with learned weights per horizon bucket."""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

logger = logging.getLogger(__name__)


def assign_horizon_bucket(horizon: int) -> str:
    """Assign horizon to bucket."""
    if 1 <= horizon <= 7:
        return "1-7"
    elif 8 <= horizon <= 14:
        return "8-14"
    elif 15 <= horizon <= 30:
        return "15-30"
    elif 31 <= horizon <= 90:
        return "31-90"
    elif 91 <= horizon <= 380:
        return "91-380"
    else:
        return "other"


class EnsembleModel:
    """Ensemble model with learned weights per horizon bucket."""

    def __init__(self):
        self.weights = {}  # weights per bucket per model
        self.models = []

    def fit(self, backtest_preds_paths: dict, min_rows: int = 50):
        """
        Learn ensemble weights from backtest predictions.

        Parameters
        ----------
        backtest_preds_paths : dict
            Dictionary of model_name -> parquet path
        min_rows : int
            Minimum rows required to fit weights
        """
        logger.info("Fitting ensemble weights from backtest predictions")

        # Load all backtest predictions
        all_preds = []

        for model_name, path in backtest_preds_paths.items():
            if not Path(path).exists():
                logger.warning(f"Backtest predictions not found: {path}")
                continue

            df = pd.read_parquet(path)

            if len(df) == 0:
                logger.warning(f"Empty backtest predictions: {model_name}")
                continue

            # IMPORTANT:
            # - If the parquet already contains model_name (e.g., preds_baselines.parquet),
            #   filter to the requested model_name rather than overwriting.
            # - If model_name is missing, inject it.
            if "model_name" in df.columns:
                df = df[df["model_name"] == model_name].copy()
                if len(df) == 0:
                    logger.warning(f"No rows for model_name={model_name} in {path}")
                    continue
            else:
                df = df.copy()
                df["model_name"] = model_name

            all_preds.append(df)

        if len(all_preds) == 0:
            logger.error("No backtest predictions available for ensemble")
            return

        df_all = pd.concat(all_preds, ignore_index=True)

        # Get unique models
        self.models = df_all["model_name"].unique().tolist()
        logger.info(f"Models available: {self.models}")

        # Fit weights per horizon bucket
        buckets = ["1-7", "8-14", "15-30", "31-90", "91-380"]

        for bucket in buckets:
            df_bucket = df_all[df_all["horizon_bucket"] == bucket]

            if len(df_bucket) < min_rows:
                logger.warning(
                    f"Insufficient data for bucket {bucket} ({len(df_bucket)} rows), using fallback"
                )
                # Fallback to previous bucket or equal weights
                if bucket == "1-7":
                    self.weights[bucket] = {m: 1.0 / len(self.models) for m in self.models}
                else:
                    # Use previous bucket weights
                    prev_bucket = buckets[buckets.index(bucket) - 1]
                    self.weights[bucket] = self.weights.get(
                        prev_bucket, {m: 1.0 / len(self.models) for m in self.models}
                    )
                continue

            # Pivot to get predictions per model
            df_pivot = df_bucket.pivot_table(
                index=["cutoff_date", "target_date"],
                columns="model_name",
                values="p50",
                aggfunc="first",
            ).reset_index()

            # Get actuals
            df_pivot = df_pivot.merge(
                df_bucket[["cutoff_date", "target_date", "y"]].drop_duplicates(),
                on=["cutoff_date", "target_date"],
                how="left",
            )

            # Drop rows with missing data
            df_pivot = df_pivot.dropna()

            if len(df_pivot) < min_rows:
                logger.warning(
                    f"Insufficient complete data for bucket {bucket}, using equal weights"
                )
                self.weights[bucket] = {m: 1.0 / len(self.models) for m in self.models}
                continue

            # Get models available in this bucket
            bucket_models = [m for m in self.models if m in df_pivot.columns]

            if len(bucket_models) == 0:
                logger.warning(f"No models available for bucket {bucket}, using equal weights")
                self.weights[bucket] = {m: 1.0 / len(self.models) for m in self.models}
                continue

            # Optimize weights
            y_true = df_pivot["y"].values
            X = df_pivot[bucket_models].values

            def objective(w):
                """Minimize wMAPE."""
                y_pred = X @ w
                wmape = np.abs(y_pred - y_true).sum() / y_true.sum()
                return wmape

            # Initial guess: equal weights
            w0 = np.ones(len(bucket_models)) / len(bucket_models)

            # Constraints: weights sum to 1
            constraints = {"type": "eq", "fun": lambda w: w.sum() - 1}

            # Bounds: weights in [0, 1]
            bounds = [(0, 1) for _ in bucket_models]

            result = minimize(objective, w0, method="SLSQP", bounds=bounds, constraints=constraints)

            if result.success:
                weights_opt = result.x
                # Set weights for bucket models, 0 for others
                self.weights[bucket] = {m: 0.0 for m in self.models}
                for m, w in zip(bucket_models, weights_opt):
                    self.weights[bucket][m] = w
                logger.info(f"Bucket {bucket}: weights = {self.weights[bucket]}")
            else:
                logger.warning(f"Optimization failed for bucket {bucket}, using equal weights")
                self.weights[bucket] = {
                    m: 1.0 / len(bucket_models) if m in bucket_models else 0.0 for m in self.models
                }

    def predict(self, model_predictions: dict) -> pd.DataFrame:
        """
        Generate ensemble predictions.

        Parameters
        ----------
        model_predictions : dict
            Dictionary of model_name -> DataFrame with columns [target_date, p50, p80, p90, horizon]

        Returns
        -------
        pd.DataFrame
            Ensemble predictions with target_date, p50, p80, p90
        """
        logger.info("Generating ensemble predictions")

        # Combine all model predictions
        all_preds = []

        for model_name, df in model_predictions.items():
            if len(df) == 0:
                continue
            df = df.copy()
            df["model_name"] = model_name
            all_preds.append(df)

        if len(all_preds) == 0:
            logger.error("No model predictions available")
            return pd.DataFrame(columns=["target_date", "p50", "p80", "p90"])

        df_all = pd.concat(all_preds, ignore_index=True)

        # Assign horizon buckets
        df_all["horizon_bucket"] = df_all["horizon"].apply(assign_horizon_bucket)

        # Ensemble per date
        ensemble_preds = []

        for target_date in df_all["target_date"].unique():
            df_date = df_all[df_all["target_date"] == target_date]

            if len(df_date) == 0:
                continue

            # Get horizon bucket
            bucket = df_date["horizon_bucket"].iloc[0]

            # Get weights for this bucket
            weights = self.weights.get(bucket, {m: 1.0 / len(self.models) for m in self.models})

            # Blend predictions
            # - Aggregate duplicates (defensive)
            # - Renormalize weights over models that are actually present for this target_date
            df_models = df_date.groupby("model_name", as_index=False)[["p50", "p80", "p90"]].mean()
            available_models = df_models["model_name"].tolist()

            raw_w = np.array([weights.get(m, 0.0) for m in available_models], dtype=float)
            if raw_w.sum() <= 0:
                # Fallback: equal weights across available models
                norm_w = np.ones(len(available_models), dtype=float) / max(1, len(available_models))
            else:
                norm_w = raw_w / raw_w.sum()

            p50_blend = float((df_models["p50"].values * norm_w).sum())
            p80_blend = float((df_models["p80"].values * norm_w).sum())
            p90_blend = float((df_models["p90"].values * norm_w).sum())

            ensemble_preds.append(
                {
                    "target_date": target_date,
                    "p50": p50_blend,
                    "p80": p80_blend,
                    "p90": p90_blend,
                }
            )

        df_ensemble = pd.DataFrame(ensemble_preds)

        return df_ensemble

    def save(self, path: str):
        """Save ensemble weights."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        # Convert to DataFrame
        rows = []
        for bucket, weights in self.weights.items():
            for model, weight in weights.items():
                rows.append(
                    {
                        "horizon_bucket": bucket,
                        "model_name": model,
                        "weight": weight,
                    }
                )

        df_weights = pd.DataFrame(rows)
        df_weights.to_csv(path, index=False)
        logger.info(f"Saved ensemble weights to {path}")
