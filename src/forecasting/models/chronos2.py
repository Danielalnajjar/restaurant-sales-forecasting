"""Chronos-2 univariate model integration (optional)."""

import pandas as pd
import numpy as np
import logging
from pathlib import Path

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
    """Chronos-2 univariate forecasting model (optional)."""
    
    def __init__(self):
        self.model = None
        self.available = CHRONOS_AVAILABLE
    
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
        
        # Prepare data for AutoGluon
        df_train = df_sales[~df_sales['is_closed']].copy()
        df_train = df_train.rename(columns={'ds': 'timestamp', 'y': 'target'})
        df_train['item_id'] = 'restaurant'  # Single time series
        
        try:
            # Create TimeSeriesDataFrame
            ts_df = TimeSeriesDataFrame.from_data_frame(
                df_train[['item_id', 'timestamp', 'target']],
                id_column='item_id',
                timestamp_column='timestamp'
            )
            
            # Train predictor
            self.model = TimeSeriesPredictor(
                prediction_length=14,
                quantile_levels=[0.5, 0.8, 0.9],
                eval_metric='MAPE',
                verbosity=0,
            )
            
            self.model.fit(
                ts_df,
                hyperparameters={'Chronos': {}},
                time_limit=300,  # 5 minutes max
            )
            
            logger.info("Chronos-2 training complete")
        except Exception as e:
            logger.error(f"Chronos-2 training failed: {e}")
            self.model = None
    
    def predict(self, prediction_length: int) -> pd.DataFrame:
        """
        Predict for next N days.
        
        Parameters
        ----------
        prediction_length : int
            Number of days to forecast
            
        Returns
        -------
        pd.DataFrame
            Predictions with target_date, p50, p80, p90
        """
        if not self.available or self.model is None:
            logger.warning("Chronos-2 not available or not trained, returning empty predictions")
            return pd.DataFrame(columns=['target_date', 'p50', 'p80', 'p90'])
        
        try:
            # Predict
            predictions = self.model.predict(
                ts_df=None,  # Use training data
                quantile_levels=[0.5, 0.8, 0.9]
            )
            
            # Extract predictions
            # (Implementation depends on AutoGluon output format)
            # For now, return placeholder
            logger.warning("Chronos-2 prediction format conversion not fully implemented")
            return pd.DataFrame(columns=['target_date', 'p50', 'p80', 'p90'])
        
        except Exception as e:
            logger.error(f"Chronos-2 prediction failed: {e}")
            return pd.DataFrame(columns=['target_date', 'p50', 'p80', 'p90'])


def run_chronos2_backtest(
    sales_fact_path: str = "data/processed/fact_sales_daily.parquet",
    output_metrics_path: str = "outputs/backtests/metrics_chronos2.csv",
    output_preds_path: str = "outputs/backtests/preds_chronos2.parquet",
) -> tuple:
    """
    Run backtest for Chronos-2 model (if available).
    
    Returns
    -------
    tuple
        (df_metrics, df_preds) or (None, None) if unavailable
    """
    if not CHRONOS_AVAILABLE:
        logger.warning("Chronos-2 not available. Skipping backtest.")
        logger.warning("This is expected and does not block the pipeline.")
        
        # Create empty outputs to satisfy pipeline requirements
        df_metrics = pd.DataFrame(columns=['horizon_bucket', 'n', 'wmape', 'rmse', 'bias', 'model_name'])
        df_preds = pd.DataFrame(columns=['cutoff_date', 'model_name', 'issue_date', 'target_date', 
                                        'horizon', 'horizon_bucket', 'p50', 'p80', 'p90', 'y', 'is_closed'])
        
        # Save empty files
        Path(output_metrics_path).parent.mkdir(parents=True, exist_ok=True)
        df_metrics.to_csv(output_metrics_path, index=False)
        
        Path(output_preds_path).parent.mkdir(parents=True, exist_ok=True)
        df_preds.to_parquet(output_preds_path, index=False)
        
        logger.info("Created empty Chronos-2 output files (model unavailable)")
        return None, None
    
    # If available, implement full backtest
    logger.info("Chronos-2 is available but full backtest not implemented in this version")
    logger.info("For production use, implement full rolling-origin backtest similar to GBM models")
    
    # Create placeholder outputs
    df_metrics = pd.DataFrame(columns=['horizon_bucket', 'n', 'wmape', 'rmse', 'bias', 'model_name'])
    df_preds = pd.DataFrame(columns=['cutoff_date', 'model_name', 'issue_date', 'target_date', 
                                    'horizon', 'horizon_bucket', 'p50', 'p80', 'p90', 'y', 'is_closed'])
    
    Path(output_metrics_path).parent.mkdir(parents=True, exist_ok=True)
    df_metrics.to_csv(output_metrics_path, index=False)
    
    Path(output_preds_path).parent.mkdir(parents=True, exist_ok=True)
    df_preds.to_parquet(output_preds_path, index=False)
    
    return df_metrics, df_preds


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Run Chronos-2 backtest
    df_metrics, df_preds = run_chronos2_backtest()
    
    if df_metrics is None:
        print("\n=== Chronos-2 Not Available ===")
        print("This is expected and does not block the pipeline.")
        print("The system will continue with GBM models only.")
    else:
        print("\n=== Chronos-2 Backtest Results ===")
        print("(Placeholder implementation)")
