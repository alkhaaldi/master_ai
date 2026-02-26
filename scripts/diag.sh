#!/usr/bin/env bash
cd ~/master_ai

echo "=== SERVICE STATUS ==="
systemctl is-active master-ai
systemctl is-active master-ai-recovery

echo ""
echo "=== LAST 80 LINES OF LOG ==="
tail -80 server.log

echo ""
echo "=== DISK USAGE ==="
df -h /home/pi

echo ""
echo "=== PYTHON VERSION ==="
python3 --version

echo ""
echo "=== LISTENING PORTS ==="
ss -lntp

echo ""
echo "=== GIT STATUS ==="
git log -3 --oneline

echo ""
echo "=== UPTIME ==="
uptime
