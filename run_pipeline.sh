#!/bin/bash
# Wrapper script to run pipeline with correct PYTHONPATH
cd /home/ubuntu/forecasting
export PYTHONPATH=/home/ubuntu/forecasting/src
python3 -m forecasting.pipeline.run_daily "$@"
