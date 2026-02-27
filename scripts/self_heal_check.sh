#!/bin/bash
# ============================================================
# Master AI Self-Heal Watchdog
# Runs every minute via systemd timer
# Checks health → restart → recovery → rollback → notify
# ============================================================
set -euo pipefail

DIR="/home/pi/master_ai"
DATA="$DIR/data"
LOG="$DATA/watchdog.log"
LAST_GOOD="$DATA/last_good_commit.txt"
ALERT_LOCK="$DATA/watchdog_alert.lock"
HEALTH_URL="http://localhost:9000/health"
RECOVERY_URL="http://localhost:9001/restart"
VENV="$DIR/venv/bin/python3"

# Load secrets
set -a
source "$DIR/.env"
set +a

TG_API="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage"

# --- Helpers ---
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"; }

tg_notify() {
    local msg="$1"
    # Anti-spam: skip if alerted in last 15 min (unless rollback)
    local force="${2:-false}"
    if [ "$force" != "true" ] && [ -f "$ALERT_LOCK" ]; then
        local lock_age=$(( $(date +%s) - $(stat -c %Y "$ALERT_LOCK" 2>/dev/null || echo 0) ))
        if [ "$lock_age" -lt 900 ]; then
            log "NOTIFY: suppressed (last alert ${lock_age}s ago)"
            return
        fi
    fi
    curl -sS --max-time 10 -X POST "$TG_API" \
        -d "chat_id=${ADMIN_TELEGRAM_ID}" \
        -d "text=$msg" \
        -d "parse_mode=Markdown" >/dev/null 2>&1 || true
    touch "$ALERT_LOCK"
    log "NOTIFY: sent"
}

check_health() {
    curl -fsS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1
}

get_head() { git -C "$DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown"; }

get_journal() { journalctl -u master-ai --no-pager -n 8 --output=cat 2>/dev/null | tail -5 || echo "(no journal)"; }

# --- Main Logic ---
log "CHECK: starting"

# Step 0: Health OK
if check_health; then
    # Update last_good_commit
    CURRENT=$(git -C "$DIR" rev-parse HEAD 2>/dev/null)
    if [ -n "$CURRENT" ]; then
        echo "$CURRENT" > "${LAST_GOOD}.tmp"
        mv "${LAST_GOOD}.tmp" "$LAST_GOOD"
    fi
    log "OK: healthy ($(get_head))"
    exit 0
fi

log "FAIL: health check failed"

# Step 1: Restart via systemd
log "STEP1: systemctl restart"
sudo systemctl restart master-ai 2>/dev/null || true
sleep 8

if check_health; then
    log "STEP1: restart fixed it ($(get_head))"
    tg_notify "🔄 *Master AI* restarted successfully
Commit: `$(get_head)`"
    exit 0
fi

# Step 2: Recovery service
log "STEP2: recovery endpoint"
curl -fsS --max-time 5 -H "X-API-Key: ${MASTER_AI_API_KEY}" \
    -X POST "$RECOVERY_URL" >/dev/null 2>&1 || true
sleep 8

if check_health; then
    log "STEP2: recovery fixed it ($(get_head))"
    tg_notify "🔧 *Master AI* recovered via :9001
Commit: `$(get_head)`"
    exit 0
fi

# Step 3: Auto-rollback
log "STEP3: rollback"
ROLLBACK_TARGET=""
if [ -f "$LAST_GOOD" ]; then
    CANDIDATE=$(cat "$LAST_GOOD" 2>/dev/null | head -1)
    if echo "$CANDIDATE" | grep -qE '^[0-9a-f]{7,40}$'; then
        ROLLBACK_TARGET="$CANDIDATE"
    fi
fi

if [ -z "$ROLLBACK_TARGET" ]; then
    # Fallback: go back 3 commits
    ROLLBACK_TARGET=$(git -C "$DIR" rev-parse HEAD~3 2>/dev/null || echo "")
fi

if [ -z "$ROLLBACK_TARGET" ]; then
    log "STEP3: no rollback target found — giving up"
    tg_notify "🚨 *Master AI DOWN* — no rollback target!
Manual intervention required.
$(get_journal)" "true"
    exit 1
fi

BEFORE_HEAD=$(get_head)
log "STEP3: rolling back to $ROLLBACK_TARGET (from $BEFORE_HEAD)"
git -C "$DIR" reset --hard "$ROLLBACK_TARGET" 2>/dev/null || true

# Verify syntax
if ! "$VENV" -m py_compile "$DIR/server.py" 2>/dev/null; then
    log "STEP3: rollback target has syntax error — going back one more"
    git -C "$DIR" reset --hard HEAD~1 2>/dev/null || true
    if ! "$VENV" -m py_compile "$DIR/server.py" 2>/dev/null; then
        log "STEP3: still broken after double rollback"
        tg_notify "🚨 *Master AI DOWN* — rollback failed!
From: `$BEFORE_HEAD`
Target: `$(get_head)`
Manual fix required." "true"
        exit 1
    fi
fi

sudo systemctl restart master-ai 2>/dev/null || true
sleep 8

if check_health; then
    # Update last_good after successful rollback
    git -C "$DIR" rev-parse HEAD > "${LAST_GOOD}.tmp" 2>/dev/null
    mv "${LAST_GOOD}.tmp" "$LAST_GOOD" 2>/dev/null || true
    log "STEP3: rollback SUCCESS ($(get_head))"
    tg_notify "⚠️ *Master AI ROLLBACK*
From: `$BEFORE_HEAD` → `$(get_head)`
Service restored automatically." "true"
    exit 0
fi

# Step 4: Everything failed
log "STEP3: rollback did NOT fix it"
tg_notify "🚨 *Master AI DOWN*
Restart ❌ | Recovery ❌ | Rollback ❌
From: `$BEFORE_HEAD` → `$(get_head)`
Last 5 journal lines:
```
$(get_journal)
```
Manual intervention required." "true"
exit 1
