"""
Holiday distance/ramp features for forecasting.

Computes days_until and days_since major holidays (Thanksgiving, Christmas, New Year).
Clamped to +/- 60 days to stabilize.
"""

from datetime import timedelta

import pandas as pd


def get_thanksgiving_date(year: int) -> pd.Timestamp:
    """Get Thanksgiving date (4th Thursday of November) for given year."""
    nov_1 = pd.Timestamp(year, 11, 1)
    # Find first Thursday
    days_until_thursday = (3 - nov_1.dayofweek) % 7
    first_thursday = nov_1 + timedelta(days=days_until_thursday)
    # 4th Thursday is 3 weeks later
    thanksgiving = first_thursday + timedelta(weeks=3)
    return thanksgiving


def get_christmas_date(year: int) -> pd.Timestamp:
    """Get Christmas date for given year."""
    return pd.Timestamp(year, 12, 25)


def get_new_year_date(year: int) -> pd.Timestamp:
    """Get New Year's Day for given year."""
    return pd.Timestamp(year, 1, 1)


def add_holiday_distance_features(df: pd.DataFrame, clamp_days: int = 60) -> pd.DataFrame:
    """
    Add holiday distance features to dataframe.

    Features added:
    - days_until_thanksgiving, days_since_thanksgiving
    - days_until_christmas, days_since_christmas
    - days_until_new_year, days_since_new_year

    Args:
        df: DataFrame with 'ds' column (datetime)
        clamp_days: Maximum distance to compute (default 60)

    Returns:
        DataFrame with holiday distance features added
    """
    df = df.copy()

    # Ensure ds is datetime
    if not pd.api.types.is_datetime64_any_dtype(df['ds']):
        df['ds'] = pd.to_datetime(df['ds'])

    # Get unique years in data
    years = sorted(df['ds'].dt.year.unique())

    # Build holiday date lookup
    holidays = {}
    for year in range(min(years) - 1, max(years) + 2):  # Include adjacent years
        holidays[f'thanksgiving_{year}'] = get_thanksgiving_date(year)
        holidays[f'christmas_{year}'] = get_christmas_date(year)
        holidays[f'new_year_{year}'] = get_new_year_date(year)

    # Initialize features
    df['days_until_thanksgiving'] = clamp_days
    df['days_since_thanksgiving'] = clamp_days
    df['days_until_christmas'] = clamp_days
    df['days_since_christmas'] = clamp_days
    df['days_until_new_year'] = clamp_days
    df['days_since_new_year'] = clamp_days

    # Compute distances for each row
    for idx, row in df.iterrows():
        ds = row['ds']
        year = ds.year

        # Thanksgiving - find closest
        min_until = clamp_days
        min_since = clamp_days
        for y in [year - 1, year, year + 1]:
            thanksgiving = get_thanksgiving_date(y)
            days_diff = (thanksgiving - ds).days
            if days_diff > 0:  # Future
                min_until = min(min_until, days_diff)
            elif days_diff < 0:  # Past
                min_since = min(min_since, -days_diff)
            elif days_diff == 0:  # On the holiday itself
                min_until = 0
                min_since = 0
        df.loc[idx, 'days_until_thanksgiving'] = min(min_until, clamp_days)
        df.loc[idx, 'days_since_thanksgiving'] = min(min_since, clamp_days)

        # Christmas - find closest
        min_until = clamp_days
        min_since = clamp_days
        for y in [year - 1, year, year + 1]:
            christmas = get_christmas_date(y)
            days_diff = (christmas - ds).days
            if days_diff > 0:  # Future
                min_until = min(min_until, days_diff)
            elif days_diff < 0:  # Past
                min_since = min(min_since, -days_diff)
            elif days_diff == 0:  # On the holiday itself
                min_until = 0
                min_since = 0
        df.loc[idx, 'days_until_christmas'] = min(min_until, clamp_days)
        df.loc[idx, 'days_since_christmas'] = min(min_since, clamp_days)

        # New Year - find closest
        min_until = clamp_days
        min_since = clamp_days
        for y in [year, year + 1, year + 2]:  # New Year is in January
            new_year = get_new_year_date(y)
            days_diff = (new_year - ds).days
            if days_diff > 0:  # Future
                min_until = min(min_until, days_diff)
            elif days_diff < 0:  # Past
                min_since = min(min_since, -days_diff)
            elif days_diff == 0:  # On the holiday itself
                min_until = 0
                min_since = 0
        df.loc[idx, 'days_until_new_year'] = min(min_until, clamp_days)
        df.loc[idx, 'days_since_new_year'] = min(min_since, clamp_days)

    return df


def test_holiday_distance_features():
    """Test holiday distance features on key dates."""
    # Test dates
    test_dates = [
        '2025-11-28',  # Black Friday 2025
        '2025-11-27',  # Thanksgiving 2025
        '2025-12-24',  # Christmas Eve 2025
        '2025-12-25',  # Christmas 2025
        '2025-12-31',  # New Year's Eve 2025
        '2026-01-01',  # New Year 2026
        '2026-11-26',  # Thanksgiving 2026
        '2026-11-27',  # Black Friday 2026
    ]

    df_test = pd.DataFrame({'ds': pd.to_datetime(test_dates)})
    df_test = add_holiday_distance_features(df_test)

    print("Holiday Distance Features Test:")
    print(df_test[['ds', 'days_until_thanksgiving', 'days_since_thanksgiving',
                    'days_until_christmas', 'days_since_christmas',
                    'days_until_new_year', 'days_since_new_year']].to_string(index=False))

    return df_test


if __name__ == '__main__':
    test_holiday_distance_features()
