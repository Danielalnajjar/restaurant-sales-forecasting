"""Baseline forecasting models."""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


class SeasonalNaiveWeekly:
    """Seasonal naive baseline using weekly lag (recursive for multi-step)."""

    def __init__(self):
        self.history = None
        self.forecasts = {}  # Store forecasts for recursive prediction

    def fit(self, df_sales: pd.DataFrame):
        """
        Fit the model (just store history).

        Parameters
        ----------
        df_sales : pd.DataFrame
            Sales history with ds, y, is_closed
        """
        self.history = df_sales.copy()
        self.forecasts = {}

    def predict(self, target_dates: list) -> pd.DataFrame:
        """
        Predict for target dates.

        Parameters
        ----------
        target_dates : list
            List of target dates

        Returns
        -------
        pd.DataFrame
            Predictions with target_date, p50, p80, p90
        """
        predictions = []

        for target_date in target_dates:
            # Look back 7 days
            lag_date = target_date - pd.Timedelta(days=7)

            # Check if lag_date is in history
            lag_row = self.history[self.history["ds"] == lag_date]

            if len(lag_row) > 0:
                # Use actual historical value
                p50 = lag_row.iloc[0]["y"]
            elif lag_date in self.forecasts:
                # Use previously forecasted value (recursive)
                p50 = self.forecasts[lag_date]
            else:
                # No data available, use mean
                p50 = self.history[~self.history["is_closed"]]["y"].mean()

            # Store forecast for future recursive use
            self.forecasts[target_date] = p50

            predictions.append(
                {
                    "target_date": target_date,
                    "p50": p50,
                    "p80": p50,  # Simple baseline: use same value
                    "p90": p50,
                }
            )

        return pd.DataFrame(predictions)


class WeekdayRollingMedian:
    """Weekday-specific rolling median baseline."""

    def __init__(self, n_weeks: int = 8):
        self.n_weeks = n_weeks
        self.history = None

    def fit(self, df_sales: pd.DataFrame):
        """
        Fit the model (just store history).

        Parameters
        ----------
        df_sales : pd.DataFrame
            Sales history with ds, y, is_closed
        """
        self.history = df_sales.copy()

    def predict(self, target_dates: list) -> pd.DataFrame:
        """
        Predict for target dates.

        Parameters
        ----------
        target_dates : list
            List of target dates

        Returns
        -------
        pd.DataFrame
            Predictions with target_date, p50, p80, p90
        """
        predictions = []

        for target_date in target_dates:
            target_dow = target_date.dayofweek

            # Get last N same-weekday observations
            same_dow = self.history[
                (self.history["ds"].dt.dayofweek == target_dow) & (~self.history["is_closed"])
            ].sort_values("ds", ascending=False)

            if len(same_dow) > 0:
                recent = same_dow.head(self.n_weeks)
                p50 = recent["y"].median()
            else:
                # Fallback to overall median
                p50 = self.history[~self.history["is_closed"]]["y"].median()

            predictions.append(
                {
                    "target_date": target_date,
                    "p50": p50,
                    "p80": p50,
                    "p90": p50,
                }
            )

        return pd.DataFrame(predictions)


