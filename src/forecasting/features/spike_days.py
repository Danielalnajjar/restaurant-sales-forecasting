"""
Spike-day feature engineering for peak demand days.

Captures single-day spikes (Black Friday, Memorial Day, etc.) and multi-day regimes
(year-end week, holiday weekends) that are systematically underpredicted by smoothing models.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def add_spike_day_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add spike-day boolean features to a dataframe with 'ds' column.
    
    Features added:
    - is_black_friday: Friday after 4th Thursday in November
    - is_thanksgiving_day: 4th Thursday in November
    - is_day_after_thanksgiving: Friday after Thanksgiving (same as Black Friday)
    - is_memorial_day: Last Monday in May
    - is_memorial_day_weekend: Sat/Sun/Mon of Memorial Day weekend
    - is_labor_day: First Monday in September
    - is_labor_day_weekend: Sat/Sun/Mon of Labor Day weekend
    - is_independence_day: July 4th
    - is_independence_day_observed: July 3rd if 4th is Sunday, July 5th if 4th is Saturday
    - is_christmas_eve: December 24th
    - is_christmas_day: December 25th
    - is_day_after_christmas: December 26th
    - is_year_end_week: December 26-31
    - is_new_years_eve: December 31st (already exists but included for completeness)
    
    Args:
        df: DataFrame with 'ds' column (datetime)
    
    Returns:
        DataFrame with spike-day features added
    """
    df = df.copy()
    
    # Ensure ds is datetime
    if not pd.api.types.is_datetime64_any_dtype(df['ds']):
        df['ds'] = pd.to_datetime(df['ds'])
    
    # Extract year, month, day, day of week
    df['_year'] = df['ds'].dt.year
    df['_month'] = df['ds'].dt.month
    df['_day'] = df['ds'].dt.day
    df['_dow'] = df['ds'].dt.dayofweek  # 0=Monday, 6=Sunday
    
    # Thanksgiving: 4th Thursday in November
    # Black Friday: Friday after Thanksgiving
    df['is_thanksgiving_day'] = False
    df['is_black_friday'] = False
    df['is_day_after_thanksgiving'] = False
    
    for year in df['_year'].unique():
        # Find 4th Thursday in November
        nov_days = pd.date_range(f'{year}-11-01', f'{year}-11-30', freq='D')
        thursdays = [d for d in nov_days if d.dayofweek == 3]  # Thursday = 3
        if len(thursdays) >= 4:
            thanksgiving = thursdays[3]
            black_friday = thanksgiving + timedelta(days=1)
            
            df.loc[df['ds'] == thanksgiving, 'is_thanksgiving_day'] = True
            df.loc[df['ds'] == black_friday, 'is_black_friday'] = True
            df.loc[df['ds'] == black_friday, 'is_day_after_thanksgiving'] = True
    
    # Memorial Day: Last Monday in May
    df['is_memorial_day'] = False
    df['is_memorial_day_weekend'] = False
    
    for year in df['_year'].unique():
        may_days = pd.date_range(f'{year}-05-01', f'{year}-05-31', freq='D')
        mondays = [d for d in may_days if d.dayofweek == 0]  # Monday = 0
        if len(mondays) > 0:
            memorial_day = mondays[-1]  # Last Monday
            memorial_sat = memorial_day - timedelta(days=2)
            memorial_sun = memorial_day - timedelta(days=1)
            
            df.loc[df['ds'] == memorial_day, 'is_memorial_day'] = True
            df.loc[df['ds'].isin([memorial_sat, memorial_sun, memorial_day]), 'is_memorial_day_weekend'] = True
    
    # Labor Day: First Monday in September
    df['is_labor_day'] = False
    df['is_labor_day_weekend'] = False
    
    for year in df['_year'].unique():
        sep_days = pd.date_range(f'{year}-09-01', f'{year}-09-30', freq='D')
        mondays = [d for d in sep_days if d.dayofweek == 0]
        if len(mondays) > 0:
            labor_day = mondays[0]  # First Monday
            labor_sat = labor_day - timedelta(days=2)
            labor_sun = labor_day - timedelta(days=1)
            
            df.loc[df['ds'] == labor_day, 'is_labor_day'] = True
            df.loc[df['ds'].isin([labor_sat, labor_sun, labor_day]), 'is_labor_day_weekend'] = True
    
    # Independence Day: July 4th + observed
    df['is_independence_day'] = (df['_month'] == 7) & (df['_day'] == 4)
    df['is_independence_day_observed'] = False
    
    for year in df['_year'].unique():
        july4 = pd.Timestamp(f'{year}-07-04')
        if july4.dayofweek == 6:  # Sunday -> observed Monday July 5
            df.loc[df['ds'] == july4 + timedelta(days=1), 'is_independence_day_observed'] = True
        elif july4.dayofweek == 5:  # Saturday -> observed Friday July 3
            df.loc[df['ds'] == july4 - timedelta(days=1), 'is_independence_day_observed'] = True
        else:
            df.loc[df['ds'] == july4, 'is_independence_day_observed'] = True
    
    # Christmas and year-end
    df['is_christmas_eve'] = (df['_month'] == 12) & (df['_day'] == 24)
    df['is_christmas_day'] = (df['_month'] == 12) & (df['_day'] == 25)
    df['is_day_after_christmas'] = (df['_month'] == 12) & (df['_day'] == 26)
    df['is_year_end_week'] = (df['_month'] == 12) & (df['_day'] >= 26) & (df['_day'] <= 31)
    df['is_new_years_eve'] = (df['_month'] == 12) & (df['_day'] == 31)
    
    # Drop temporary columns
    df = df.drop(columns=['_year', '_month', '_day', '_dow'])
    
    return df


def add_event_regime_features(df: pd.DataFrame, events_daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add multi-day event regime features (event_day_index, days_to_event_end).
    
    For each active event family, adds:
    - event_family__<name>__day_index: 0-indexed day within event window (0, 1, 2, ...)
    - event_family__<name>__days_to_end: Days remaining until event ends
    
    Args:
        df: Base dataframe with 'ds' column
        events_daily_df: Events daily features with event_family__* columns
    
    Returns:
        DataFrame with regime features added
    """
    df = df.copy()
    
    # Merge with events
    df = df.merge(events_daily_df, on='ds', how='left')
    
    # Find event family columns
    event_cols = [c for c in events_daily_df.columns if c.startswith('event_family__') and not c.endswith('__day_index') and not c.endswith('__days_to_end')]
    
    for event_col in event_cols:
        family_name = event_col.replace('event_family__', '')
        day_index_col = f'event_family__{family_name}__day_index'
        days_to_end_col = f'event_family__{family_name}__days_to_end'
        
        # Initialize
        df[day_index_col] = 0
        df[days_to_end_col] = 0
        
        # Find contiguous event windows
        df['_active'] = df[event_col] > 0
        df['_group'] = (df['_active'] != df['_active'].shift()).cumsum()
        
        for group_id, group_df in df[df['_active']].groupby('_group'):
            if len(group_df) == 0:
                continue
            
            indices = group_df.index
            window_length = len(indices)
            
            # Assign day_index (0, 1, 2, ...)
            df.loc[indices, day_index_col] = range(window_length)
            
            # Assign days_to_end (n-1, n-2, ..., 0)
            df.loc[indices, days_to_end_col] = list(reversed(range(window_length)))
        
        # Clean up
        df = df.drop(columns=['_active', '_group'])
    
    return df


if __name__ == '__main__':
    # Quick test
    dates = pd.date_range('2025-01-01', '2025-12-31', freq='D')
    df = pd.DataFrame({'ds': dates})
    
    df = add_spike_day_features(df)
    
    # Show key dates
    spike_cols = [c for c in df.columns if c.startswith('is_')]
    spike_dates = df[df[spike_cols].any(axis=1)]
    
    print("Spike days in 2025:")
    print(spike_dates[['ds'] + spike_cols].to_string(index=False))
