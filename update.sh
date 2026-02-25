#!/usr/bin/env bash
set -e
cd ~/master_ai
echo "== Pull latest from origin/main =="
git pull --rebase
echo "== Python syntax check =="
python3 -m py_compile server.py
echo "== Restart master-ai service =="
sudo systemctl restart master-ai
echo "== Health check =="
sleep 2
curl -s http://localhost:9000/health | python3 -m json.tool
echo "== Deployment completed successfully =="
