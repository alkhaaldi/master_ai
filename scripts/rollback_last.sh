#!/usr/bin/env bash
set -e
cd ~/master_ai

echo "Current commit:"
git log -1 --oneline

echo ""
echo "Rolling back to previous commit..."
git reset --hard HEAD~1

echo ""
echo "Syntax check:"
python3 -m py_compile server.py

echo ""
echo "Restarting service:"
sudo systemctl restart master-ai

echo ""
echo "Waiting 3 seconds..."
sleep 3

echo ""
echo "Health check:"
curl -s http://localhost:9000/health

echo ""
echo "New current commit:"
git log -1 --oneline

echo ""
echo "Rollback complete."
