#!/bin/bash
set -e
cd /home/pi/master_ai
echo "=== Master AI Update ==="
echo "1. Pulling latest..."
git pull origin main
echo "2. Syntax check..."
python3 -c "import py_compile; py_compile.compile('server.py', doraise=True)"
echo "3. Restarting..."
sudo systemctl restart master-ai
sleep 3
echo "4. Health check..."
curl -sf http://localhost:9000/health | python3 -m json.tool | head -3
if [ $? -eq 0 ]; then
  echo "=== Updated Successfully ==="
else
  echo "=== FAILED - Rolling back ==="
  git checkout HEAD~1 -- server.py
  sudo systemctl restart master-ai
fi