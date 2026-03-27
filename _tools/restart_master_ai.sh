#!/bin/bash
# restart_master_ai.sh — Restart master-ai service and show status.
# Run: bash _tools/restart_master_ai.sh

echo "=== Restarting master-ai.service ==="
sudo systemctl restart master-ai.service
sleep 2

echo ""
echo "=== Service Status ==="
systemctl is-active master-ai.service
echo ""
systemctl status master-ai.service --no-pager -l | head -15

echo ""
echo "=== Quick health check ==="
sleep 3
curl -s http://localhost:9000/health | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(f\"  status={d.get('status')} version={d.get('version')} uptime={d.get('uptime_seconds',0):.0f}s\")
except:
    print('  ERROR: /health not responding yet')
"

echo ""
echo "=== Done ==="
