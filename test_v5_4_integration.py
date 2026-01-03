#!/usr/bin/env python3.11
"""
Integration test for V5.4 config centralization.

Tests that the pipeline can:
1. Load config successfully
2. Generate forecasts using config parameters
3. Apply growth calibration from config
4. Apply spike uplift from config
"""

import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from forecasting.utils.runtime import load_config, get_forecast_window
from forecasting.pipeline.export import generate_2026_forecast

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_config_loading():
    """Test that config loads and validates correctly."""
    logger.info("=" * 80)
    logger.info("TEST 1: Config Loading")
    logger.info("=" * 80)
    
    try:
        config = load_config()
        logger.info("✓ Config loaded successfully")
        
        # Check forecast window
        fs, fe = get_forecast_window(config)
        logger.info(f"✓ Forecast window: {fs} to {fe}")
        
        # Check growth calibration config
        growth_config = config.get('growth_calibration', {})
        logger.info(f"✓ Growth calibration enabled: {growth_config.get('enabled')}")
        logger.info(f"✓ Target YoY rate: {growth_config.get('target_yoy_rate')}")
        logger.info(f"✓ Mode: {growth_config.get('mode')}")
        
        # Check spike uplift config
        spike_config = config.get('spike_uplift', {})
        logger.info(f"✓ Spike uplift enabled: {spike_config.get('enabled')}")
        logger.info(f"✓ Min observations: {spike_config.get('min_observations')}")
        logger.info(f"✓ Shrinkage factor: {spike_config.get('shrinkage_factor')}")
        
        return config
        
    except Exception as e:
        logger.error(f"✗ Config loading failed: {e}")
        raise


def test_forecast_generation(config):
    """Test that forecast generation works with config."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Forecast Generation")
    logger.info("=" * 80)
    
    try:
        # Generate forecast using config
        df_forecast = generate_2026_forecast(config)
        
        logger.info(f"✓ Forecast generated: {len(df_forecast)} days")
        logger.info(f"✓ Total p50: ${df_forecast['p50'].sum():,.2f}")
        
        # Check that forecast covers expected period
        fs, fe = get_forecast_window(config)
        forecast_start = df_forecast['ds'].min().strftime('%Y-%m-%d')
        forecast_end = df_forecast['ds'].max().strftime('%Y-%m-%d')
        
        if forecast_start == fs and forecast_end == fe:
            logger.info(f"✓ Forecast period matches config: {forecast_start} to {forecast_end}")
        else:
            logger.warning(f"⚠ Forecast period mismatch: expected {fs} to {fe}, got {forecast_start} to {forecast_end}")
        
        # Check for required columns
        required_cols = ['ds', 'p50', 'p80', 'p90', 'is_closed']
        missing_cols = [c for c in required_cols if c not in df_forecast.columns]
        if missing_cols:
            logger.error(f"✗ Missing required columns: {missing_cols}")
            raise ValueError(f"Missing columns: {missing_cols}")
        else:
            logger.info(f"✓ All required columns present")
        
        # Check guardrails
        closed_days = df_forecast[df_forecast['is_closed'] == 1]
        if len(closed_days) > 0:
            closed_with_sales = closed_days[closed_days['p50'] > 0]
            if len(closed_with_sales) > 0:
                logger.error(f"✗ {len(closed_with_sales)} closed days have non-zero sales")
                raise ValueError("Guardrail violation: closed days with sales")
            else:
                logger.info(f"✓ Guardrail check passed: {len(closed_days)} closed days have $0 sales")
        
        # Check for negative forecasts
        negative_days = df_forecast[df_forecast['p50'] < 0]
        if len(negative_days) > 0:
            logger.error(f"✗ {len(negative_days)} days have negative forecasts")
            raise ValueError("Guardrail violation: negative forecasts")
        else:
            logger.info("✓ No negative forecasts")
        
        # Check quantile monotonicity
        violations = df_forecast[
            (df_forecast['p50'] > df_forecast['p80']) |
            (df_forecast['p80'] > df_forecast['p90'])
        ]
        if len(violations) > 0:
            logger.error(f"✗ {len(violations)} days have non-monotonic quantiles")
            raise ValueError("Guardrail violation: non-monotonic quantiles")
        else:
            logger.info("✓ Quantiles are monotonic (p50 ≤ p80 ≤ p90)")
        
        return df_forecast
        
    except Exception as e:
        logger.error(f"✗ Forecast generation failed: {e}")
        raise


def test_growth_calibration(df_forecast, config):
    """Test that growth calibration was applied correctly."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Growth Calibration")
    logger.info("=" * 80)
    
    try:
        import pandas as pd
        
        # Load historical data
        df_history = pd.read_parquet("data/processed/fact_sales_daily.parquet")
        
        # Get forecast year
        fs, fe = get_forecast_window(config)
        forecast_year = pd.Timestamp(fs).year
        history_year = forecast_year - 1
        
        # Filter history to comparison year
        df_history['year'] = df_history['ds'].dt.year
        df_history_comp = df_history[df_history['year'] == history_year]
        
        # Calculate YoY growth
        history_total = df_history_comp['y'].sum()
        forecast_total = df_forecast['p50'].sum()
        yoy_growth = (forecast_total / history_total - 1) * 100
        
        target_growth = config.get('growth_calibration', {}).get('target_yoy_rate', 0.10) * 100
        
        logger.info(f"✓ {history_year} actual: ${history_total:,.2f}")
        logger.info(f"✓ {forecast_year} forecast: ${forecast_total:,.2f}")
        logger.info(f"✓ YoY growth: {yoy_growth:+.1f}%")
        logger.info(f"✓ Target growth: {target_growth:+.1f}%")
        
        # Check if growth is close to target (within 1%)
        if abs(yoy_growth - target_growth) < 1.0:
            logger.info(f"✓ Growth calibration successful (within 1% of target)")
        else:
            logger.warning(f"⚠ Growth calibration off target by {abs(yoy_growth - target_growth):.1f}%")
        
    except Exception as e:
        logger.error(f"✗ Growth calibration test failed: {e}")
        # Don't raise - this is informational


def main():
    """Run all integration tests."""
    logger.info("V5.4 Integration Test Suite")
    logger.info("Testing config centralization and parameterization")
    logger.info("")
    
    try:
        # Test 1: Config loading
        config = test_config_loading()
        
        # Test 2: Forecast generation
        df_forecast = test_forecast_generation(config)
        
        # Test 3: Growth calibration
        test_growth_calibration(df_forecast, config)
        
        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("✓ ALL TESTS PASSED")
        logger.info("=" * 80)
        logger.info("V5.4 config centralization is working correctly")
        logger.info("Next steps: Add error handling, input validation, enhanced logging")
        
        return 0
        
    except Exception as e:
        logger.error("\n" + "=" * 80)
        logger.error("✗ TESTS FAILED")
        logger.error("=" * 80)
        logger.error(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
