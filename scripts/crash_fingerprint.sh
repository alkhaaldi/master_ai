#!/bin/bash
# ============================================================
# Crash Fingerprint — Collects diagnostic info after failure
# Called by self_heal_check.sh or manually
# Output: data/crash_fingerprint.txt + returns TG-formatted summary
# ============================================================
set -uo pipefail

DIR="/home/pi/master_ai"
DATA="$DIR/data"
REPORT="$DATA/crash_fingerprint.txt"
VENV="$DIR/venv/bin/python3"

# Load secrets
set -a; source "$DIR/.env" 2>/dev/null; set +a

TS=$(date '+%Y-%m-%d %H:%M:%S')
HEAD=$(git -C "$DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
HEAD_FULL=$(git -C "$DIR" rev-parse HEAD 2>/dev/null || echo "unknown")
LAST_GOOD=$(cat "$DATA/last_good_commit.txt" 2>/dev/null | head -c 12 || echo "none")

# === Collect Data ===
{
echo "=========================================="
echo "CRASH FINGERPRINT — $TS"
echo "=========================================="
echo ""

echo "--- GIT ---"
echo "HEAD: $HEAD_FULL"
echo "Last good: $LAST_GOOD"
echo "Last 5 commits:"
git -C "$DIR" log --oneline -5 2>/dev/null || echo "(git error)"
echo ""

echo "--- LAST TRACEBACK (server.log) ---"
# Find the last Python traceback in log
grep -n "Traceback\|Error\|Exception\|CRITICAL" "$DIR/server.log" 2>/dev/null | tail -10 || echo "(no errors)"
echo ""
echo "Last traceback block:"
# Extract last traceback block (from "Traceback" to next non-indented line)
tac "$DIR/server.log" 2>/dev/null | awk '/^[^ ]/ && found {exit} /Traceback/ {found=1} found {print}' | tac | tail -20 || echo "(none)"
echo ""

echo "--- JOURNAL (last 15 lines) ---"
journalctl -u master-ai --no-pager -n 15 --output=short 2>/dev/null || echo "(no journal)"
echo ""

echo "--- SERVICE STATUS ---"
systemctl is-active master-ai 2>/dev/null || echo "unknown"
echo ""

echo "--- SYSTEM RESOURCES ---"
echo "Uptime: $(uptime -p 2>/dev/null || echo 'unknown')"
echo "Memory: $(free -m 2>/dev/null | awk '/^Mem:/ {printf "%dMB/%dMB (%.0f%%)", $3, $2, $3/$2*100}')"
echo "Disk: $(df -h /home/pi 2>/dev/null | awk 'NR==2 {printf "%s/%s (%s)", $3, $2, $5}')"
echo "CPU temp: $(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null | awk '{printf "%.1f°C", $1/1000}' || echo 'unknown')"
echo ""

echo "--- LAST 5 HTTP REQUESTS (server.log) ---"
grep "HTTP/1.1" "$DIR/server.log" 2>/dev/null | tail -5 || echo "(none)"
echo ""

echo "--- DB STATUS ---"
"$VENV" -c "
import sqlite3
c = sqlite3.connect('$DATA/audit.db')
print('WAL:', c.execute('PRAGMA journal_mode').fetchone()[0])
print('Tables:', [r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()])
# Recent events
evts = c.execute('SELECT created_at, type, risk FROM events ORDER BY rowid DESC LIMIT 3').fetchall()
print('Last 3 events:', evts)
c.close()
" 2>/dev/null || echo "(db error)"
echo ""

echo "--- WATCHDOG LOG (last 10) ---"
tail -10 "$DATA/watchdog.log" 2>/dev/null || echo "(no log)"
echo ""
echo "=========================================="
echo "END FINGERPRINT"
echo "=========================================="
} > "$REPORT" 2>&1

# === Build TG Summary (compact, max ~3000 chars for Telegram) ===
TRACEBACK=$(tac "$DIR/server.log" 2>/dev/null | awk '/^[^ ]/ && found {exit} /Traceback/ {found=1} found {print}' | tac | tail -8)
JOURNAL=$(journalctl -u master-ai --no-pager -n 5 --output=cat 2>/dev/null | tail -5)
LAST_COMMIT_MSG=$(git -C "$DIR" log --oneline -1 2>/dev/null || echo "?")
MEM=$(free -m 2>/dev/null | awk '/^Mem:/ {printf "%dMB/%dMB", $3, $2}')
TEMP=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null | awk '{printf "%.0f°C", $1/1000}' || echo "?")

# Output TG message to stdout
cat << TGEOF
🔍 *Crash Fingerprint* — $TS

📌 *Commit:* \`$HEAD\` — $LAST_COMMIT_MSG
📌 *Last good:* \`$LAST_GOOD\`
💾 *Mem:* $MEM | 🌡 *CPU:* $TEMP

📋 *Last traceback:*
\`\`\`
$(echo "$TRACEBACK" | head -8 | cut -c1-80)
\`\`\`

📜 *Journal:*
\`\`\`
$(echo "$JOURNAL" | head -5 | cut -c1-80)
\`\`\`

📄 Full report: \`$REPORT\`
TGEOF
