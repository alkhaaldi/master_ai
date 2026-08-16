#!/bin/bash
# Master AI — Off-device Backup to Google Drive
# Broken silently 2026-04-02..08-16: CRLF endings turned "set -euo
# pipefail" into option name "pipefail\r" and bash refused it on every
# run. Rewritten LF-only. The old tg_notify read TG_BOT_TOKEN /
# TG_CHAT_ID, names that do not exist in .env, so its alerts could never
# fire even when the script ran - alerts now go through the witness.
# audit.db is copied with the sqlite3 backup API - the old checkpoint+cp
# on a live db is this project's named disease (see PHASE2_SECTION_F).
# NOTE, unchanged existing behaviour the user should rule on: the
# archive still includes .env (as dot_env) - plaintext secrets on Drive.
set -euo pipefail

DIR=/home/pi/master_ai
DATA=$DIR/data
REMOTE=gdrive:master-ai-backups
TMP=/tmp/master_ai_backup
LOG=$DATA/gdrive_backup.log
KEEP_DAYS=7
DATE=$(date +%Y-%m-%d)
TIME=$(date +%H%M)
T0=$SECONDS
WITNESS="$DIR/venv/bin/python3 $DIR/_tools/witness_cli.py"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"; echo "$1"; }

fail() {
    log "ERROR: $1"
    $WITNESS log gdrive_backup failed $((SECONDS - T0)) "$1" || true
    rm -rf "$TMP" "${ARCHIVE:-}" 2>/dev/null || true
    exit 1
}
trap 'fail "line $LINENO"' ERR

log "=== Backup START ==="

rm -rf "$TMP"
mkdir -p "$TMP"

# backup API snapshot, never cp on the live file
python3 - "$DATA/audit.db" "$TMP/audit.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
src.close()
dst.close()
PY
log "DB copied"

cp "$DIR/server.py" "$TMP/"
cp "$DIR/.env" "$TMP/dot_env"
cp "$DIR/update.sh" "$TMP/" 2>/dev/null || true
cp -r "$DIR/scripts" "$TMP/scripts" 2>/dev/null || true
cp -r "$DIR/tests" "$TMP/tests" 2>/dev/null || true
cp "$DIR/policy.json" "$TMP/" 2>/dev/null || true
cp "$DIR/memory_db.py" "$TMP/" 2>/dev/null || true
cp "$DIR/tasks_db.py" "$TMP/" 2>/dev/null || true
cp "$DIR/tg_tasks.py" "$TMP/" 2>/dev/null || true
cp "$DATA/last_good_commit.txt" "$TMP/" 2>/dev/null || true
log "Files copied"

ARCHIVE=/tmp/master_ai_${DATE}_${TIME}.tar.gz
tar -czf "$ARCHIVE" -C /tmp master_ai_backup
SIZE=$(du -h "$ARCHIVE" | cut -f1)
log "Archive: $SIZE"

if ! rclone copy "$ARCHIVE" "$REMOTE/" --log-level ERROR 2>>"$LOG"; then
    fail "upload failed"
fi
log "Uploaded OK"

CUTOFF=$(date -d "-$KEEP_DAYS days" +%Y-%m-%d)
rclone lsf "$REMOTE/" 2>/dev/null | while read -r f; do
    FDATE=$(echo "$f" | grep -oP '\d{4}-\d{2}-\d{2}' || true)
    if [ -n "$FDATE" ] && [ "$FDATE" \< "$CUTOFF" ]; then
        rclone deletefile "$REMOTE/$f" 2>/dev/null && log "Cleaned: $f"
    fi
done

rm -rf "$TMP" "$ARCHIVE"

REMOTE_COUNT=$(rclone lsf "$REMOTE/" 2>/dev/null | wc -l)
trap - ERR
$WITNESS log gdrive_backup success $((SECONDS - T0)) || true
log "=== Backup DONE ($SIZE) — $REMOTE_COUNT files on Drive ==="
