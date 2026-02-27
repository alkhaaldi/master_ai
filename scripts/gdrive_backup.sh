#!/bin/bash
# Master AI — Off-device Backup to Google Drive
set -euo pipefail

DIR=/home/pi/master_ai
DATA=$DIR/data
REMOTE=gdrive:master-ai-backups
TMP=/tmp/master_ai_backup
LOG=$DATA/gdrive_backup.log
KEEP_DAYS=7
DATE=$(date +%Y-%m-%d)
TIME=$(date +%H%M)

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"; echo "$1"; }

tg_notify() {
    source "$DIR/.env" 2>/dev/null || true
    if [ -n "${TG_BOT_TOKEN:-}" ] && [ -n "${TG_CHAT_ID:-}" ]; then
        curl -sS --max-time 5 -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
            -d chat_id="${TG_CHAT_ID}" -d parse_mode=Markdown -d text="$1" >/dev/null 2>&1 || true
    fi
}

log "=== Backup START ==="

rm -rf "$TMP"
mkdir -p "$TMP"

sqlite3 "$DATA/audit.db" "PRAGMA wal_checkpoint(TRUNCATE);" 2>/dev/null || true
cp "$DATA/audit.db" "$TMP/audit.db"
log "DB copied"

cp "$DIR/server.py" "$TMP/"
cp "$DIR/.env" "$TMP/dot_env"
cp "$DIR/update.sh" "$TMP/"
cp -r "$DIR/scripts" "$TMP/scripts" 2>/dev/null || true
cp -r "$DIR/tests" "$TMP/tests" 2>/dev/null || true
cp "$DIR/policy.json" "$TMP/" 2>/dev/null || true
cp "$DIR/memory_db.py" "$TMP/" 2>/dev/null || true
cp "$DIR/tasks_db.py" "$TMP/" 2>/dev/null || true
cp "$DIR/tg_tasks.py" "$TMP/" 2>/dev/null || true
cp "$DIR/daily_stats.py" "$TMP/" 2>/dev/null || true
cp "$DATA/last_good_commit.txt" "$TMP/" 2>/dev/null || true
log "Files copied"

ARCHIVE=/tmp/master_ai_${DATE}_${TIME}.tar.gz
tar -czf "$ARCHIVE" -C /tmp master_ai_backup
SIZE=$(du -h "$ARCHIVE" | cut -f1)
log "Archive: $SIZE"

rclone copy "$ARCHIVE" "$REMOTE/" --log-level ERROR 2>>"$LOG"
RC=$?
if [ "$RC" -ne 0 ]; then
    log "ERROR: Upload failed (rc=$RC)"
    tg_notify "❌ *Backup FAILED*: upload error"
    rm -rf "$TMP" "$ARCHIVE"
    exit 1
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
log "=== Backup DONE ($SIZE) — $REMOTE_COUNT files on Drive ==="
tg_notify "✅ *GDrive Backup OK* ($SIZE) — $REMOTE_COUNT files on Drive"
