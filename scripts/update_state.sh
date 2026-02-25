#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
echo "== Generating PROJECT_STATE.md =="
python3 tools/generate_project_state.py
echo "== Done =="
head -40 PROJECT_STATE.md
