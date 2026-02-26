#!/usr/bin/env bash
set -e
cd ~/master_ai

# Save current commit for rollback
PREV=$(git rev-parse HEAD)
echo "== Current commit: $PREV =="

echo "== Pull latest from origin/main =="
git pull --rebase

NEW=$(git rev-parse HEAD)
echo "== New commit: $NEW =="

echo "== Python syntax check =="
python3 -m py_compile server.py

echo "== Restart master-ai service =="
sudo systemctl restart master-ai

echo "== Health check (waiting 3s) =="
sleep 3

HEALTH=$(curl -sf http://localhost:9000/health)
if echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='ok'" 2>/dev/null; then
    echo "== Health OK =="
    echo "$HEALTH" | python3 -m json.tool
    echo "== Deployment completed successfully =="
else
    echo "!! HEALTH CHECK FAILED — ROLLING BACK !!"
    git reset --hard "$PREV"
    python3 -m py_compile server.py
    sudo systemctl restart master-ai
    sleep 3
    HEALTH2=$(curl -sf http://localhost:9000/health)
    if echo "$HEALTH2" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='ok'" 2>/dev/null; then
        echo "== Rollback successful, service restored =="
        echo "$HEALTH2" | python3 -m json.tool
    else
        echo "!! CRITICAL: Rollback also failed !!"
        echo "!! Manual intervention required !!"
        exit 2
    fi
    exit 1
fi
