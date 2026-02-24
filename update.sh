#!/bin/bash
set -e
cd /home/pi/master_ai

echo "=== Master AI Update ==="
echo "Time: $(date)"
echo ""

PREV_COMMIT=$(git rev-parse HEAD)
echo "1. Current: $PREV_COMMIT"

echo "2. Pulling latest..."
git pull origin main
NEW_COMMIT=$(git rev-parse HEAD)
echo "   New: $NEW_COMMIT"

if [ "$PREV_COMMIT" = "$NEW_COMMIT" ]; then
    echo "   Already up to date."
    exit 0
fi

echo "3. Syntax check..."
/home/pi/master_ai/venv/bin/python3 -m py_compile server.py
if [ $? -ne 0 ]; then
    echo "   SYNTAX ERROR - Rolling back..."
    git reset --hard $PREV_COMMIT
    echo "   Rolled back to $PREV_COMMIT"
    exit 1
fi
echo "   OK"

echo "4. Restarting service..."
sudo systemctl restart master-ai
sleep 4

echo "5. Health check..."
HTTP_CODE=$(curl -s -o /tmp/health_response -w "%{http_code}" http://127.0.0.1:9000/health)

if [ "$HTTP_CODE" = "200" ]; then
    echo "   Health OK (HTTP $HTTP_CODE)"
    cat /tmp/health_response | python3 -m json.tool 2>/dev/null | head -5
    echo ""
    echo "=== Updated Successfully ==="
    echo "   $PREV_COMMIT -> $NEW_COMMIT"
else
    echo "   HEALTH FAILED (HTTP $HTTP_CODE) - Rolling back..."
    git reset --hard $PREV_COMMIT
    sudo systemctl restart master-ai
    sleep 4
    ROLLBACK_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9000/health)
    if [ "$ROLLBACK_CODE" = "200" ]; then
        echo "   Rollback OK - back to $PREV_COMMIT"
    else
        echo "   CRITICAL: Rollback failed! Manual fix needed."
    fi
    exit 1
fi