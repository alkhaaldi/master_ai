#!/usr/bin/env bash
# Local snapshot backup (03:10 cron). Broken silently 2026-04-02..08-16:
# the file carried CRLF endings, so $TS interpolated a \r into a Python
# string literal and every for-loop died on $'\r'. Rewritten LF-only;
# .gitattributes now forces LF on *.sh. Every run reports to the witness.
set -euo pipefail
cd /home/pi/master_ai

T0=$SECONDS
TS=$(date +%Y%m%d_%H%M%S)
DIR="backups/$TS"
WITNESS="venv/bin/python3 _tools/witness_cli.py"

fail() {
    $WITNESS log local_backup failed $((SECONDS - T0)) "$1" || true
    echo "=== Backup FAILED: $1 ==="
    exit 1
}
trap 'fail "line $LINENO"' ERR

mkdir -p "$DIR"
echo "=== Backup $TS ==="

# SQLite safe backup via python (backup API, never cp on a live db).
# life.db is deliberately NOT here: 88MB x 14 would eat the SD card,
# and the NAS path (nas_backup.py) is its designated off-device copy.
python3 - "$DIR" <<'PY'
import sqlite3, os, sys
outdir = sys.argv[1]
for db in ["data/audit.db", "data/tasks.db"]:
    if os.path.exists(db):
        src = sqlite3.connect(db)
        dst = sqlite3.connect(os.path.join(outdir, os.path.basename(db)))
        src.backup(dst)
        src.close()
        dst.close()
        print("  DB backed up:", db)
PY

# JSON files
for f in data/policy.json data/stock_alerts.json data/ruijie_token.json knowledge.json; do
    if [ -f "$f" ]; then
        cp "$f" "$DIR/"
        echo "  Copied: $f"
    fi
done

# Keep only last 14 backups
ls -dt backups/2* 2>/dev/null | tail -n +15 | xargs rm -rf 2>/dev/null || true

trap - ERR
$WITNESS log local_backup success $((SECONDS - T0)) || true
echo "=== Backup complete: $DIR ==="
ls -la "$DIR/"
