#!/usr/bin/env bash
# ============================================================
# Master AI — Safe Deploy v2
# Smoke tests + Canary + Auto-rollback + Telegram notify
# ============================================================
set -euo pipefail

DIR="${HOME}/master_ai"
cd "$DIR"

# Load secrets
set -a; source "$DIR/.env"; set +a

TG_API="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage"
API_KEY="${MASTER_AI_API_KEY}"
ADMIN_ID="${ADMIN_TELEGRAM_ID}"
VENV="$DIR/venv/bin/python3"

tg_notify() {
    curl -sS --max-time 10 -X POST "$TG_API" \
        -d "chat_id=$ADMIN_ID" -d "text=$1" -d "parse_mode=Markdown" >/dev/null 2>&1 || true
}

# ============================================================
# PHASE 0: Save current state
# ============================================================
PREV=$(git rev-parse HEAD)
PREV_SHORT=$(git rev-parse --short HEAD)
echo "== Current: $PREV_SHORT =="

# ============================================================
# PHASE 1: Pull + syntax check
# ============================================================
echo "== Pulling latest =="
git pull --rebase || { echo "!! Git pull failed"; exit 1; }

NEW=$(git rev-parse HEAD)
NEW_SHORT=$(git rev-parse --short HEAD)

if [ "$PREV" = "$NEW" ]; then
    echo "== No changes, exiting =="
    exit 0
fi

echo "== New: $NEW_SHORT =="
echo "== Syntax check =="
"$VENV" -m py_compile server.py || {
    echo "!! Syntax error — rolling back"
    git reset --hard "$PREV"
    tg_notify "❌ *Deploy FAILED* (syntax)
\`$NEW_SHORT\` → rolled back to \`$PREV_SHORT\`"
    exit 1
}

# ============================================================
# PHASE 2: Canary — test on :9002 before touching production
# ============================================================
echo "== Canary test on :9002 =="
CANARY_PID=""
canary_cleanup() { [ -n "$CANARY_PID" ] && kill "$CANARY_PID" 2>/dev/null; wait "$CANARY_PID" 2>/dev/null; }
trap canary_cleanup EXIT

# Start canary (suppress output)
CANARY_MODE=1 PORT=9002 "$VENV" -m uvicorn server:app --host 127.0.0.1 --port 9002 --log-level error &
CANARY_PID=$!
sleep 6

CANARY_OK=true
# Quick health on canary
if ! curl -fsS --max-time 3 http://127.0.0.1:9002/health >/dev/null 2>&1; then
    CANARY_OK=false
    echo "!! Canary health failed"
fi

# Kill canary
canary_cleanup
CANARY_PID=""
trap - EXIT

if [ "$CANARY_OK" != "true" ]; then
    echo "!! Canary failed — rolling back"
    git reset --hard "$PREV"
    "$VENV" -m py_compile server.py
    tg_notify "❌ *Deploy FAILED* (canary)
\`$NEW_SHORT\` → rolled back to \`$PREV_SHORT\`"
    exit 1
fi
echo "== Canary passed =="

# ============================================================
# PHASE 3: Deploy to production
# ============================================================
echo "== Restarting production =="
sudo systemctl restart master-ai
sleep 5

# ============================================================
# PHASE 4: Smoke tests (6 checks)
# ============================================================
echo "== Running smoke tests =="
SMOKE_FAIL=0
SMOKE_LOG=""

smoke() {
    local name="$1" url="$2" auth="${3:-no}"
    local code
    if [ "$auth" = "auth" ]; then
        code=$(curl -sS --max-time 5 -o /dev/null -w "%{http_code}" -H "X-API-Key: $API_KEY" "$url" 2>/dev/null || echo "000")
    else
        code=$(curl -sS --max-time 5 -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    fi
    if [ "$code" -ge 200 ] && [ "$code" -lt 400 ]; then
        echo "  ✅ $name ($code)"
        SMOKE_LOG="$SMOKE_LOG\n✅ $name"
    else
        echo "  ❌ $name ($code)"
        SMOKE_LOG="$SMOKE_LOG\n❌ $name ($code)"
        SMOKE_FAIL=$((SMOKE_FAIL + 1))
    fi
}

smoke "health"          "http://localhost:9000/health"
smoke "system/context"  "http://localhost:9000/system/context"  auth
smoke "plugins"         "http://localhost:9000/plugins"         auth
smoke "brain/stats"     "http://localhost:9000/brain/stats"     auth
smoke "approvals"       "http://localhost:9000/approvals/pending" auth
smoke "tasks"           "http://localhost:9000/tasks"           auth

echo ""
if [ "$SMOKE_FAIL" -gt 0 ]; then
    echo "!! $SMOKE_FAIL smoke test(s) FAILED — rolling back"
    git reset --hard "$PREV"
    "$VENV" -m py_compile server.py
    sudo systemctl restart master-ai
    sleep 3
    tg_notify "❌ *Deploy FAILED* ($SMOKE_FAIL smoke tests)
\`$NEW_SHORT\` → rolled back to \`$PREV_SHORT\`
$SMOKE_LOG"
    exit 1
fi

# ============================================================
# PHASE 5: Success — update last_good + notify
# ============================================================
echo "$NEW" > "$DIR/data/last_good_commit.txt"
echo ""
echo "========================================="
echo "  ✅ Deploy SUCCESS: $PREV_SHORT → $NEW_SHORT"
echo "  Smoke tests: all passed"
echo "========================================="

tg_notify "✅ *Deploy SUCCESS*
\`$PREV_SHORT\` → \`$NEW_SHORT\`
Canary ✅ | Smoke 6/6 ✅"
