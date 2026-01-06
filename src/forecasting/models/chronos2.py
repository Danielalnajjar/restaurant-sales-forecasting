"""Chronos-2 univariate model integration."""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Try to import AutoGluon
try:
    from autogluon.timeseries import TimeSeriesDataFrame, TimeSeriesPredictor

    CHRONOS_AVAILABLE = True
    logger.info("Chronos-2 (AutoGluon) is available")
except ImportError:
    CHRONOS_AVAILABLE = False
    logger.warning("Chronos-2 (AutoGluon) is NOT available. Skipping Chronos integration.")


class Chronos2Model:
    """Chronos-2 univariate forecasting model."""

    def __init__(self, prediction_length: int = 90, quantiles: list | None = None):
        self.model = None
        self.train_data = None  # Store training data for predictions
        self.available = CHRONOS_AVAILABLE
        self.prediction_length = prediction_length
        self.quantiles = quantiles or [0.5, 0.8, 0.9]

    def fit(self, df_sales: pd.DataFrame):
        """
        Train Chronos-2 model.

        Parameters
        ----------
        df_sales : pd.DataFrame
            Sales history with ds, y, is_closed
        """
        if not self.available:
            logger.warning("Chronos-2 not available, skipping training")
            return

        logger.info("Training Chronos-2 model (univariate)")

        # Prepare data for AutoGluon - use only open days
        df_train = df_sales[~df_sales["is_closed"]].copy()
        df_train = df_train.rename(columns={"ds": "timestamp", "y": "target"})
        df_train["item_id"] = "restaurant"  # Single time series

        try:
            # Fill missing dates with forward fill to create regular time series
            # AutoGluon requires regular frequency
            df_train = df_train.set_index("timestamp")
            df_train = df_train.asfreq("D", method="ffill")  # Daily frequency, forward fill gaps
            df_train = df_train.reset_index()
            df_train["item_id"] = "restaurant"

            # Create TimeSeriesDataFrame
            ts_df = TimeSeriesDataFrame.from_data_frame(
                df_train[["item_id", "timestamp", "target"]],
                id_column="item_id",
                timestamp_column="timestamp",
            )

            logger.info(f"Training data shape: {ts_df.shape}")
            logger.info(
                f"Date range: {ts_df.index.get_level_values('timestamp').min()} to {ts_df.index.get_level_values('timestamp').max()}"
            )

            # Train predictor with Chronos model
            self.model = TimeSeriesPredictor(
                freq="D",  # Daily frequency
                prediction_length=self.prediction_length,
                quantile_levels=self.quantiles,
                eval_metric="MAPE",
                verbosity=2,
            )

            self.model.fit(
                ts_df,
                hyperparameters={
                    "Chronos": {"model_path": "tiny"}
                },  # Use tiny model for faster training
                time_limit=300,  # 5 minutes max
            )

            # Store training data for predictions
            self.train_data = ts_df

            logger.info("Chronos-2 training complete")
        except Exception:
            logger.exception("Chronos-2 fit failed")
            self.model = None

    def predict(self, prediction_length: int = None) -> pd.DataFrame:
        """
        Predict for next N days.

        Parameters
        ----------
        prediction_length : int
            Number of days to forecast (if None, uses self.prediction_length)

        Returns
        -------
        pd.DataFrame
            Predictions with target_date, p50, p80, p90
        """
        if not self.available or self.model is None:
            logger.warning("Chronos-2 not available or not trained, returning empty predictions")
            return pd.DataFrame(columns=["target_date", "p50", "p80", "p90"])

        if prediction_length is None:
            prediction_length = self.prediction_length

        try:
            # Predict
            logger.info(f"Generating Chronos-2 predictions for {prediction_length} days")
            predictions = self.model.predict(data=self.train_data)  # Use stored training data

            # Extract predictions for 'restaurant' item
            preds_df = predictions.reset_index()
            preds_df = preds_df[preds_df["item_id"] == "restaurant"].copy()

            # Rename columns
            preds_df = preds_df.rename(
                columns={
                    "timestamp": "target_date",
                    "0.5": "p50",
                    "0.8": "p80",
                    "0.9": "p90",
                }
            )

            # Select only needed columns
            preds_df = preds_df[["target_date", "p50", "p80", "p90"]]

            # Limit to requested prediction length
            preds_df = preds_df.head(prediction_length)

            logger.info(f"Generated {len(preds_df)} predictions")

            return preds_df

        except Exception:
            logger.exception("Chronos-2 predict failed")
            return pd.DataFrame(columns=["target_date", "p50", "p80", "p90"])


def run_chronos2_backtest(
    sales_fact_path: str = "data/processed/fact_sales_daily.parquet",
    output_metrics_path: str = "outputs/backtests/metrics_chronos2.csv",
    output_preds_path: str = "outputs/backtests/preds_chronos2.parquet",
) -> tuple:
    """
    Run backtest for Chronos-2 model (simplified version).

    Note: Full rolling-origin backtest would take very long due to repeated training.
    This version trains once on full history and generates predictions.

    Returns
    -------
    tuple
        (df_metrics, df_preds) or (None, None) if unavailable
    """
    if not CHRONOS_AVAILABLE:
        logger.warning("Chronos-2 not available. Skipping backtest.")
        logger.warning("This is expected and does not block the pipeline.")

        # Create empty outputs
        df_metrics = pd.DataFrame(
            columns=["horizon_bucket", "n", "wmape", "rmse", "bias", "model_name"]
        )
        df_preds = pd.DataFrame(
            columns=[
                "cutoff_date",
                "model_name",
                "issue_date",
                "target_date",
                "horizon",
                "horizon_bucket",
                "p50",
                "p80",
                "p90",
                "y",
                "is_closed",
            ]
        )

        Path(output_metrics_path).parent.mkdir(parents=True, exist_ok=True)
        df_metrics.to_csv(output_metrics_path, index=False)

        Path(output_preds_path).parent.mkdir(parents=True, exist_ok=True)
        df_preds.to_parquet(output_preds_path, index=False)

        logger.info("Created empty Chronos-2 output files (model unavailable)")
        return None, None

    logger.info("Running Chronos-2 backtest (simplified - single training run)")

    # Load sales data
    df_sales = pd.read_parquet(sales_fact_path)

    # Train on full history with reduced prediction length to fit data
    # We have ~399 days, use 90-day prediction length (conservative for limited data)
    model = Chronos2Model(prediction_length=90)
    model.fit(df_sales)

    if model.model is None:
        logger.error("Chronos-2 training failed, creating empty outputs")
        df_metrics = pd.DataFrame(
            columns=["horizon_bucket", "n", "wmape", "rmse", "bias", "model_name"]
        )
        df_preds = pd.DataFrame(
            columns=[
                "cutoff_date",
                "model_name",
                "issue_date",
                "target_date",
                "horizon",
                "horizon_bucket",
                "p50",
                "p80",
                "p90",
                "y",
                "is_closed",
            ]
        )

        Path(output_metrics_path).parent.mkdir(parents=True, exist_ok=True)
        df_metrics.to_csv(output_metrics_path, index=False)

        Path(output_preds_path).parent.mkdir(parents=True, exist_ok=True)
        df_preds.to_parquet(output_preds_path, index=False)

        return None, None

    # Generate predictions
    preds = model.predict()

    logger.info(f"Chronos-2 generated {len(preds)} predictions")

    # For simplified backtest, just save predictions without full evaluation
    # (Full rolling-origin backtest would require training multiple times)
    df_preds = preds.copy()
    df_preds["model_name"] = "chronos2"
    df_preds["cutoff_date"] = df_sales["ds"].max()
    df_preds["issue_date"] = df_sales["ds"].max()
    df_preds["horizon"] = (df_preds["target_date"] - df_preds["issue_date"]).dt.days

    # Assign horizon buckets
    def assign_horizon_bucket(h):
        if 1 <= h <= 7:
            return "1-7"
        elif 8 <= h <= 14:
            return "8-14"
        elif 15 <= h <= 30:
            return "15-30"
        elif 31 <= h <= 90:
            return "31-90"
        elif 91 <= h <= 380:
            return "91-380"
        else:
            return "other"

    df_preds["horizon_bucket"] = df_preds["horizon"].apply(assign_horizon_bucket)

    # Add actuals (will be NaN for future dates)
    df_preds = df_preds.merge(
        df_sales[["ds", "y", "is_closed"]].rename(columns={"ds": "target_date"}),
        on="target_date",
        how="left",
    )

    # Save predictions
    Path(output_preds_path).parent.mkdir(parents=True, exist_ok=True)
    df_preds.to_parquet(output_preds_path, index=False)
    logger.info(f"Saved Chronos-2 predictions to {output_preds_path}")

    # Create placeholder metrics (can't compute without actuals for future dates)
    df_metrics = pd.DataFrame(
        {
            "horizon_bucket": ["1-7", "8-14", "15-30", "31-90", "91-380"],
            "n": [0, 0, 0, 0, 0],
            "wmape": [np.nan, np.nan, np.nan, np.nan, np.nan],
            "rmse": [np.nan, np.nan, np.nan, np.nan, np.nan],
            "bias": [np.nan, np.nan, np.nan, np.nan, np.nan],
            "model_name": ["chronos2"] * 5,
        }
    )

    Path(output_metrics_path).parent.mkdir(parents=True, exist_ok=True)
    df_metrics.to_csv(output_metrics_path, index=False)
    logger.info(f"Saved Chronos-2 metrics to {output_metrics_path}")

    return df_metrics, df_preds
