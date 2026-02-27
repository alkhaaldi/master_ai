#!/bin/bash
set -a; source /home/pi/master_ai/.env; set +a
cd /home/pi/master_ai
export MASTER_AI_API_KEY
/home/pi/master_ai/venv/bin/python3 -m pytest tests/test_smoke.py -v --tb=short 2>&1
