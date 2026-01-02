"""Feature builders for training and inference."""

import pandas as pd
import numpy as np
import logging
from datetime import datetime
import holidays
from forecasting.features.spike_days import add_spike_day_features
from forecasting.features.holiday_distance import add_holiday_distance_features

logger = logging.getLogger(__name__)


def build_calendar_features(df: pd.DataFrame, ds_col: str = 'ds', reference_date: str = '2024-11-19') -> pd.DataFrame:
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
    
    # Trend feature (days since reference date)
    # FIXED: Cap at 365 days to prevent extrapolated additive growth into 2026
    # This prevents Q1 over-prediction by stopping the "ramp-up" from continuing
    ref_date = pd.to_datetime(reference_date)
    days_since = (df[ds_col] - ref_date).dt.days.clip(lower=0)
    
    df['days_since_open_capped_365'] = days_since.clip(upper=365)
    df['days_since_open_log1p'] = np.log1p(days_since.clip(upper=365))
    
    # Basic date features
    df['dow'] = df[ds_col].dt.dayofweek  # Monday=0, Sunday=6
    df['is_weekend'] = df['dow'].isin([5, 6]).astype(int)
    df['month'] = df[ds_col].dt.month
    df['weekofyear'] = df[ds_col].dt.isocalendar().week
    df['dayofyear'] = df[ds_col].dt.dayofyear
    
    # Month start/end
    df['is_month_start'] = df[ds_col].dt.is_month_start.astype(int)
    df['is_month_end'] = df[ds_col].dt.is_month_end.astype(int)
    
    # Fourier terms for seasonality
    df['doy_sin_1'] = np.sin(2 * np.pi * df['dayofyear'] / 365.25)
    df['doy_cos_1'] = np.cos(2 * np.pi * df['dayofyear'] / 365.25)
    df['doy_sin_2'] = np.sin(4 * np.pi * df['dayofyear'] / 365.25)
    df['doy_cos_2'] = np.cos(4 * np.pi * df['dayofyear'] / 365.25)
    
    # US Federal holidays
    us_holidays = holidays.US(years=range(2024, 2027))
    df['is_us_federal_holiday'] = df[ds_col].apply(lambda x: int(x in us_holidays))
    
    # New Year's Eve
    df['is_new_years_eve'] = ((df[ds_col].dt.month == 12) & (df[ds_col].dt.day == 31)).astype(int)
    
    # Add spike-day features
    df = add_spike_day_features(df.rename(columns={ds_col: 'ds'}))
    df = df.rename(columns={'ds': ds_col})
    
    # Add holiday distance features
    df = add_holiday_distance_features(df.rename(columns={ds_col: 'ds'}), clamp_days=60)
    df = df.rename(columns={'ds': ds_col})
    
    return df


def build_lag_features(df_sales: pd.DataFrame, issue_date: pd.Timestamp, target_dates: list) -> pd.DataFrame:
    """
    Build lag features for target dates as of issue_date.
    
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
        DataFrame with target_date and lag features
    """
    # Filter sales to issue_date
    df_sales_filtered = df_sales[df_sales['ds'] <= issue_date].copy()
    
    lag_features = []
    
    for target_date in target_dates:
        features = {'target_date': target_date}
        
        # Lag 1
        lag1_date = target_date - pd.Timedelta(days=1)
        lag1 = df_sales_filtered[df_sales_filtered['ds'] == lag1_date]
        features['y_lag_1'] = lag1['y'].values[0] if len(lag1) > 0 else np.nan
        
        # Lag 7
        lag7_date = target_date - pd.Timedelta(days=7)
        lag7 = df_sales_filtered[df_sales_filtered['ds'] == lag7_date]
        features['y_lag_7'] = lag7['y'].values[0] if len(lag7) > 0 else np.nan
        
        # Lag 14
        lag14_date = target_date - pd.Timedelta(days=14)
        lag14 = df_sales_filtered[df_sales_filtered['ds'] == lag14_date]
        features['y_lag_14'] = lag14['y'].values[0] if len(lag14) > 0 else np.nan
        
        # Rolling mean 7 (mean of open days in [T-7, T-1])
        recent_7 = df_sales_filtered[
            (df_sales_filtered['ds'] >= target_date - pd.Timedelta(days=7)) &
            (df_sales_filtered['ds'] < target_date) &
            (~df_sales_filtered['is_closed'])
        ]
        features['y_roll_mean_7'] = recent_7['y'].mean() if len(recent_7) > 0 else np.nan
        
        # Rolling mean 28
        recent_28 = df_sales_filtered[
            (df_sales_filtered['ds'] >= target_date - pd.Timedelta(days=28)) &
            (df_sales_filtered['ds'] < target_date) &
            (~df_sales_filtered['is_closed'])
        ]
        features['y_roll_mean_28'] = recent_28['y'].mean() if len(recent_28) > 0 else np.nan
        
        lag_features.append(features)
    
    return pd.DataFrame(lag_features)


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
    df = pd.DataFrame({'target_date': target_dates})
    df['issue_date'] = issue_date
    df['horizon'] = (df['target_date'] - df['issue_date']).dt.days
    
    # Calendar features for target date
    df = build_calendar_features(df, ds_col='target_date')
    
    # Hours features
    df = df.merge(
        df_hours.rename(columns={'ds': 'target_date'}),
        on='target_date',
        how='left'
    )
    
    # Event features
    df = df.merge(
        df_events.rename(columns={'ds': 'target_date'}),
        on='target_date',
        how='left'
    )
    
    # Lag features
    df_lags = build_lag_features(df_sales, issue_date, target_dates)
    df = df.merge(df_lags, on='target_date', how='left')
    
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
    df = pd.DataFrame({'target_date': target_dates})
    df['issue_date'] = issue_date
    df['horizon'] = (df['target_date'] - df['issue_date']).dt.days
    
    # Calendar features for target date
    df = build_calendar_features(df, ds_col='target_date')
    
    # Hours features
    df = df.merge(
        df_hours.rename(columns={'ds': 'target_date'}),
        on='target_date',
        how='left'
    )
    
    # Event features
    df = df.merge(
        df_events.rename(columns={'ds': 'target_date'}),
        on='target_date',
        how='left'
    )
    
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test feature builders
    df_sales = pd.read_parquet("data/processed/fact_sales_daily.parquet")
    df_hours = pd.read_parquet("data/processed/hours_calendar_history.parquet")
    df_events = pd.read_parquet("data/processed/features/events_daily_history.parquet")
    
    issue_date = pd.Timestamp('2025-12-01')
    target_dates = pd.date_range(start='2025-12-02', end='2025-12-15', freq='D').tolist()
    
    print("Testing short-horizon features...")
    df_short = build_features_short(issue_date, target_dates, df_sales, df_hours, df_events)
    print(f"Shape: {df_short.shape}")
    print(f"Columns: {df_short.columns.tolist()[:10]}...")
    print(f"Sample:\n{df_short[['target_date', 'horizon', 'dow', 'y_lag_7', 'events_active_total']].head()}")
    
    print("\nTesting long-horizon features...")
    target_dates_long = pd.date_range(start='2025-12-16', end='2025-12-31', freq='D').tolist()
    df_long = build_features_long(issue_date, target_dates_long, df_hours, df_events)
    print(f"Shape: {df_long.shape}")
    print(f"Has lag features: {'y_lag_7' in df_long.columns}")
