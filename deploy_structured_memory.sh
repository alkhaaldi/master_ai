#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# deploy_structured_memory.sh
# Master AI — Structured Memory Deployment
# ═══════════════════════════════════════════════════════════════
# 
# Usage: 
#   1. Copy these files to RPi /home/pi/master_ai/:
#      - structured_memory.py
#      - patch_server_structured_memory.py
#      - patch_chat_v7_structured_memory.py
#   2. Run: bash deploy_structured_memory.sh
#
# ═══════════════════════════════════════════════════════════════

set -e
cd /home/pi/master_ai

echo "═══════════════════════════════════════════"
echo "  Structured Memory Deployment"
echo "═══════════════════════════════════════════"

# ── Step 0: Git safety ──
echo ""
echo "[0] Git status check..."
git status --short
echo ""
echo "Committing current state before patches..."
git add -A
git commit -m "pre-structured-memory snapshot" --allow-empty
echo "✅ Safety commit done"

# ── Step 1: Verify files exist ──
echo ""
echo "[1] Checking files..."
for f in structured_memory.py patch_server_structured_memory.py patch_chat_v7_structured_memory.py; do
    if [ ! -f "$f" ]; then
        echo "❌ Missing: $f"
        exit 1
    fi
    echo "  ✅ $f"
done

# ── Step 2: Test structured_memory.py standalone ──
echo ""
echo "[2] Testing structured_memory.py import..."
python3 -c "
import structured_memory as smem
print(f'  DB: {smem.DB_PATH}')
print(f'  Tables: OK')
stats = smem.get_stats()
print(f'  Active memories: {stats[\"total_active\"]}')
print('  ✅ Module works')
"

# ── Step 3: Patch server.py ──
echo ""
echo "[3] Patching server.py..."
cp server.py server.py.bak
python3 patch_server_structured_memory.py

# ── Step 4: Patch chat_v7.py ──
echo ""
echo "[4] Patching chat_v7.py..."
cp chat_v7.py chat_v7.py.bak
python3 patch_chat_v7_structured_memory.py

# ── Step 5: Syntax check ──
echo ""
echo "[5] Syntax check..."
python3 -m py_compile server.py && echo "  ✅ server.py OK" || echo "  ❌ server.py FAILED"
python3 -m py_compile chat_v7.py && echo "  ✅ chat_v7.py OK" || echo "  ❌ chat_v7.py FAILED"
python3 -m py_compile structured_memory.py && echo "  ✅ structured_memory.py OK" || echo "  ❌ structured_memory.py FAILED"

# ── Step 6: Seed initial facts ──
echo ""
echo "[6] Seeding initial facts..."
python3 -c "
import structured_memory as smem
result = smem.seed_initial()
print(f'  Seeded: {result[\"seeded\"]} memories')
stats = smem.get_stats()
print(f'  Total active: {stats[\"total_active\"]}')
print(f'  By type: {stats[\"by_type\"]}')
"

# ── Step 7: Migrate old memory (if exists) ──
echo ""
echo "[7] Migrating old memory..."
python3 -c "
import structured_memory as smem
result = smem.migrate_from_old_db()
print(f'  Result: {result}')
"

# ── Step 8: Git commit ──
echo ""
echo "[8] Git commit..."
git add -A
git commit -m "feat: structured_memory.py — typed memory system with LLM context, tools, migration, seed"

# ── Step 9: Restart ──
echo ""
echo "[9] Restarting Master AI..."
kill -9 $(pgrep -f 'uvicorn.*server:app') 2>/dev/null || true
sleep 2

# Check if it auto-restarts via systemd
sleep 5
if pgrep -f 'uvicorn.*server:app' > /dev/null; then
    echo "  ✅ Master AI restarted"
else
    echo "  ⚠️ Not auto-restarted. Starting manually..."
    cd /home/pi/master_ai
    nohup python3 -m uvicorn server:app --host 0.0.0.0 --port 9000 >> data/master_ai.log 2>&1 &
    sleep 3
    if pgrep -f 'uvicorn.*server:app' > /dev/null; then
        echo "  ✅ Started manually"
    else
        echo "  ❌ Failed to start!"
        exit 1
    fi
fi

# ── Step 10: Test endpoints ──
echo ""
echo "[10] Testing endpoints..."
sleep 2

# Stats
echo -n "  /structured-memory: "
curl -s http://localhost:9000/structured-memory | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'OK — {d.get(\"total_active\",0)} active')" 2>/dev/null || echo "FAILED"

# Context
echo -n "  /structured-memory/context: "
curl -s "http://localhost:9000/structured-memory/context?q=test" | python3 -c "import sys,json; d=json.load(sys.stdin); ctx=d.get('context',''); print(f'OK — {len(ctx)} chars')" 2>/dev/null || echo "FAILED"

# Health
echo -n "  /health: "
curl -s http://localhost:9000/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'OK — v{d.get(\"version\",\"?\")}')" 2>/dev/null || echo "FAILED"

echo ""
echo "═══════════════════════════════════════════"
echo "  ✅ Deployment Complete!"
echo "═══════════════════════════════════════════"
echo ""
echo "Test from tunnel:"
echo "  curl https://ai.salem-home.com/structured-memory"
echo "  curl 'https://ai.salem-home.com/structured-memory/context?q=عبود'"
echo "  curl -X POST https://ai.salem-home.com/structured-memory/seed"
echo ""
echo "Backups:"
echo "  server.py.bak"
echo "  chat_v7.py.bak"
