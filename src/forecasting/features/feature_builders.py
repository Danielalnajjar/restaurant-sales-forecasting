"""Feature builders for training and inference."""

import logging

import holidays
import numpy as np
import pandas as pd

from forecasting.features.holiday_distance import add_holiday_distance_features
from forecasting.features.spike_days import add_spike_day_features

logger = logging.getLogger(__name__)


def build_calendar_features(
    df: pd.DataFrame, ds_col: str = "ds", reference_date: str = "2024-11-19"
) -> pd.DataFrame:
    """
    Build calendar features for given dates.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with date column
    ds_col : str
        Name of date column
    reference_date : str
        Reference date for trend calculation (default: first date in training data)

    Returns
    -------
    pd.DataFrame
        DataFrame with calendar features added
    """
    df = df.copy()

    # Trend feature REMOVED in V5.0
    # Reason: With only 13 months of data, model cannot distinguish trend from seasonality.
    # This was causing Q1 over-prediction (+21.5% instead of +10%).
    # Growth will be handled by explicit calibration layer (Step 5) if needed.
    #
    # If you need to re-enable trend (not recommended with <2 years data):
    # ref_date = pd.to_datetime(reference_date)
    # days_since = (df[ds_col] - ref_date).dt.days.clip(lower=0)
    # df['days_since_open_capped_365'] = days_since.clip(upper=365)

    # Basic date features
    df["dow"] = df[ds_col].dt.dayofweek  # Monday=0, Sunday=6
    df["is_weekend"] = df["dow"].isin([5, 6]).astype(int)
    df["month"] = df[ds_col].dt.month
    df["weekofyear"] = df[ds_col].dt.isocalendar().week
    df["dayofyear"] = df[ds_col].dt.dayofyear

    # Month start/end
    df["is_month_start"] = df[ds_col].dt.is_month_start.astype(int)
    df["is_month_end"] = df[ds_col].dt.is_month_end.astype(int)

    # Fourier terms for seasonality (increased from 2 to 4 orders in V5.0)
    # More flexibility to capture complex annual patterns
    fourier_order = 4  # Can be made configurable if needed
    for k in range(1, fourier_order + 1):
        df[f"doy_sin_{k}"] = np.sin(2 * np.pi * k * df["dayofyear"] / 365.25)
        df[f"doy_cos_{k}"] = np.cos(2 * np.pi * k * df["dayofyear"] / 365.25)

    # US Federal holidays
    us_holidays = holidays.US(years=range(2024, 2027))
    df["is_us_federal_holiday"] = df[ds_col].apply(lambda x: int(x in us_holidays))

    # New Year's Eve
    df["is_new_years_eve"] = ((df[ds_col].dt.month == 12) & (df[ds_col].dt.day == 31)).astype(int)

    # Add spike-day features
    df = add_spike_day_features(df.rename(columns={ds_col: "ds"}))
    df = df.rename(columns={"ds": ds_col})

    # Add holiday distance features
    df = add_holiday_distance_features(df.rename(columns={ds_col: "ds"}), clamp_days=60)
    df = df.rename(columns={"ds": ds_col})

    return df


def build_lag_features(
    df_sales: pd.DataFrame, issue_date: pd.Timestamp, target_dates: list
) -> pd.DataFrame:
    """
    Build lag features for target dates as of issue_date.

    FIXED V5.0: Lag features are now computed relative to issue_date (what we know at forecast time),
    not target_date (which is in the future). This preserves "most recent sales" signal and prevents
    flattened amplitude.

    Parameters
    ----------
    df_sales : pd.DataFrame
        Sales history with ds, y, is_closed
    issue_date : pd.Timestamp
        Issue date (no data after this date can be used)
    target_dates : list
        List of target dates

    Returns
    -------
    pd.DataFrame
        DataFrame with target_date and lag features (same lag values for all target_dates)
    """
    # Filter sales to issue_date (only use data available at forecast time)
    df = df_sales[~df_sales["is_closed"]].copy()
    df = df[df["ds"] <= issue_date].sort_values("ds")

    if len(df) == 0:
        # No data available - return NaNs
        out = pd.DataFrame({"target_date": pd.to_datetime(target_dates)})
        for col in [
            "y_last",
            "y_lag_1",
            "y_lag_7",
            "y_lag_14",
            "y_lag_21",
            "y_lag_28",
            "y_roll_mean_7",
            "y_roll_mean_14",
            "y_roll_mean_28",
        ]:
            out[col] = np.nan
        return out

    y_by_ds = df.set_index("ds")["y"]

    def get_y(d):
        """Get y value for date d, or NaN if not available."""
        return float(y_by_ds.loc[d]) if d in y_by_ds.index else np.nan

    # Last observed day (issue_date or closest prior)
    if issue_date in y_by_ds.index:
        y_last = float(y_by_ds.loc[issue_date])
    else:
        # Fallback: most recent available <= issue_date
        y_last = float(y_by_ds.iloc[-1]) if len(y_by_ds) > 0 else np.nan

    # Compute lag features ONCE (relative to issue_date, not target_date)
    feats = {
        "y_last": y_last,
        "y_lag_1": get_y(issue_date - pd.Timedelta(days=1)),
        "y_lag_7": get_y(issue_date - pd.Timedelta(days=7)),
        "y_lag_14": get_y(issue_date - pd.Timedelta(days=14)),
        "y_lag_21": get_y(issue_date - pd.Timedelta(days=21)),
        "y_lag_28": get_y(issue_date - pd.Timedelta(days=28)),
    }

    # Rolling means (last N days ending at issue_date)
    for window in [7, 14, 28]:
        window_start = issue_date - pd.Timedelta(days=window)
        window_data = df[(df["ds"] > window_start) & (df["ds"] <= issue_date)]
        feats[f"y_roll_mean_{window}"] = window_data["y"].mean() if len(window_data) > 0 else np.nan

    # Broadcast to all target_dates (same lag values for all horizons from same issue_date)
    out = pd.DataFrame({"target_date": pd.to_datetime(target_dates)})
    for k, v in feats.items():
        out[k] = v

    return out


def build_features_short(
    issue_date: pd.Timestamp,
    target_dates: list,
    df_sales: pd.DataFrame,
    df_hours: pd.DataFrame,
    df_events: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build features for short-horizon forecasting (includes lags).

    Parameters
    ----------
    issue_date : pd.Timestamp
        Issue date
    target_dates : list
        List of target dates
    df_sales : pd.DataFrame
        Sales history
    df_hours : pd.DataFrame
        Hours calendar
    df_events : pd.DataFrame
        Event features

    Returns
    -------
    pd.DataFrame
        Feature matrix
    """
    # Create base dataframe
    df = pd.DataFrame({"target_date": target_dates})
    df["issue_date"] = issue_date
    df["horizon"] = (df["target_date"] - df["issue_date"]).dt.days

    # Calendar features for target date
    df = build_calendar_features(df, ds_col="target_date")

    # Hours features
    df = df.merge(df_hours.rename(columns={"ds": "target_date"}), on="target_date", how="left")

    # Event features
    df = df.merge(df_events.rename(columns={"ds": "target_date"}), on="target_date", how="left")

    # Lag features
    df_lags = build_lag_features(df_sales, issue_date, target_dates)
    df = df.merge(df_lags, on="target_date", how="left")

    return df


def build_features_long(
    issue_date: pd.Timestamp,
    target_dates: list,
    df_hours: pd.DataFrame,
    df_events: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build features for long-horizon forecasting (no lags).

    Parameters
    ----------
    issue_date : pd.Timestamp
        Issue date
    target_dates : list
        List of target dates
    df_hours : pd.DataFrame
        Hours calendar
    df_events : pd.DataFrame
        Event features

    Returns
    -------
    pd.DataFrame
        Feature matrix
    """
    # Create base dataframe
    df = pd.DataFrame({"target_date": target_dates})
    df["issue_date"] = issue_date
    df["horizon"] = (df["target_date"] - df["issue_date"]).dt.days

    # Calendar features for target date
    df = build_calendar_features(df, ds_col="target_date")

    # Hours features
    df = df.merge(df_hours.rename(columns={"ds": "target_date"}), on="target_date", how="left")

    # Event features
    df = df.merge(df_events.rename(columns={"ds": "target_date"}), on="target_date", how="left")

    return df
