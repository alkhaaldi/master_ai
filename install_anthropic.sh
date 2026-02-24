#!/bin/bash
/home/pi/master_ai/venv/bin/pip install anthropic > /tmp/pip_anthropic.log 2>&1
echo "DONE: $?" >> /tmp/pip_anthropic.log
