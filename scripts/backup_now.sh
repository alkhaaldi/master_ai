#!/usr/bin/env bash
set -e
cd ~/master_ai

TS=$(date +%Y%m%d_%H%M%S)
DIR="backups/$TS"
mkdir -p "$DIR"

echo "=== Backup $TS ==="

# SQLite safe backup via python
python3 -c "
import sqlite3, shutil, os
for db in ['data/audit.db', 'data/tasks.db']:
    if os.path.exists(db):
        src = sqlite3.connect(db)
        dst = sqlite3.connect('$DIR/' + os.path.basename(db))
        src.backup(dst)
        src.close()
        dst.close()
        print(f'  DB backed up: {db}')
"

# JSON files
for f in data/policy.json data/stock_alerts.json data/ruijie_token.json knowledge.json; do
    if [ -f "$f" ]; then
        cp "$f" "$DIR/"
        echo "  Copied: $f"
    fi
done

# Keep only last 14 backups
ls -dt backups/2* 2>/dev/null | tail -n +15 | xargs rm -rf 2>/dev/null

echo "=== Backup complete: $DIR ==="
ls -la "$DIR/"
