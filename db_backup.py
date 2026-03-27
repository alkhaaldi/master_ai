"""
db_backup.py - Database Backup & Restore for Master AI
Phase 3D: Daily backups with 7-day retention, weekly compressed, restore capability
"""
import os
import gzip
import shutil
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("db_backup")

BACKUP_DIR = "/home/pi/master_ai/data/backups"
DB_FILES = [
    "data/audit.db",
    "data/structured_memory.db",
    "data/traces.db",
]
DAILY_KEEP = 7
WEEKLY_KEEP = 30


def init():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    os.makedirs(os.path.join(BACKUP_DIR, "weekly"), exist_ok=True)
    log.info("[Backup] Initialized")


def backup_db(db_path):
    """Backup a single SQLite DB using .backup API (WAL-safe)."""
    if not os.path.exists(db_path):
        return None, f"DB not found: {db_path}"
    try:
        name = os.path.basename(db_path).replace(".db", "")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(BACKUP_DIR, f"{name}_{ts}.db")
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(dest)
        src.backup(dst)
        src.close()
        dst.close()
        size = os.path.getsize(dest)
        log.info(f"[Backup] {db_path} -> {dest} ({size} bytes)")
        return dest, "ok"
    except Exception as e:
        return None, str(e)


def backup_all():
    """Backup all databases."""
    results = []
    for db in DB_FILES:
        path, status = backup_db(db)
        results.append({"db": db, "backup": path, "status": status})
    return results


def cleanup_daily():
    """Remove daily backups older than DAILY_KEEP days."""
    cutoff = datetime.now() - timedelta(days=DAILY_KEEP)
    removed = 0
    for f in Path(BACKUP_DIR).glob("*.db"):
        if f.stat().st_mtime < cutoff.timestamp():
            f.unlink()
            removed += 1
    if removed:
        log.info(f"[Backup] Cleaned {removed} old daily backups")
    return removed


def create_weekly():
    """Create compressed weekly backup."""
    ts = datetime.now().strftime("%Y%m%d")
    weekly_dir = os.path.join(BACKUP_DIR, "weekly")
    created = []
    for db in DB_FILES:
        if not os.path.exists(db):
            continue
        name = os.path.basename(db).replace(".db", "")
        dest = os.path.join(weekly_dir, f"{name}_weekly_{ts}.db.gz")
        if os.path.exists(dest):
            continue
        try:
            src = sqlite3.connect(db)
            temp = os.path.join(BACKUP_DIR, f"_temp_{name}.db")
            dst = sqlite3.connect(temp)
            src.backup(dst)
            src.close()
            dst.close()
            with open(temp, "rb") as f_in:
                with gzip.open(dest, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            os.unlink(temp)
            size = os.path.getsize(dest)
            created.append({"db": db, "file": dest, "size": size})
            log.info(f"[Backup] Weekly: {dest} ({size} bytes)")
        except Exception as e:
            log.error(f"[Backup] Weekly failed for {db}: {e}")
    return created


def cleanup_weekly():
    """Remove weekly backups older than WEEKLY_KEEP days."""
    cutoff = datetime.now() - timedelta(days=WEEKLY_KEEP)
    weekly_dir = os.path.join(BACKUP_DIR, "weekly")
    removed = 0
    for f in Path(weekly_dir).glob("*.gz"):
        if f.stat().st_mtime < cutoff.timestamp():
            f.unlink()
            removed += 1
    return removed


def get_status():
    """Get backup status."""
    daily_files = sorted(Path(BACKUP_DIR).glob("*.db"), key=lambda f: f.stat().st_mtime, reverse=True)
    weekly_files = sorted(Path(os.path.join(BACKUP_DIR, "weekly")).glob("*.gz"), key=lambda f: f.stat().st_mtime, reverse=True)
    
    last_daily = None
    if daily_files:
        f = daily_files[0]
        last_daily = {"file": f.name, "size": f.stat().st_size, "age_hours": int((datetime.now().timestamp() - f.stat().st_mtime) / 3600)}
    
    last_weekly = None
    if weekly_files:
        f = weekly_files[0]
        last_weekly = {"file": f.name, "size": f.stat().st_size, "age_days": int((datetime.now().timestamp() - f.stat().st_mtime) / 86400)}
    
    return {
        "daily_count": len(daily_files),
        "weekly_count": len(weekly_files),
        "last_daily": last_daily,
        "last_weekly": last_weekly,
    }


def format_status():
    """Format backup status for TG."""
    s = get_status()
    lines = ["\U0001f4be *Backup Status:*", ""]
    if s["last_daily"]:
        d = s["last_daily"]
        lines.append(f"Daily: {d['file']} ({d['size']//1024}KB, {d['age_hours']}h ago)")
    else:
        lines.append("Daily: None")
    lines.append(f"Daily backups: {s['daily_count']} (keep {DAILY_KEEP})")
    lines.append("")
    if s["last_weekly"]:
        w = s["last_weekly"]
        lines.append(f"Weekly: {w['file']} ({w['size']//1024}KB, {w['age_days']}d ago)")
    else:
        lines.append("Weekly: None")
    lines.append(f"Weekly backups: {s['weekly_count']} (keep {WEEKLY_KEEP}d)")
    return "\n".join(lines)


def run_daily():
    """Full daily backup routine."""
    init()
    results = backup_all()
    cleaned = cleanup_daily()
    # Create weekly on Sundays
    if datetime.now().weekday() == 6:
        create_weekly()
        cleanup_weekly()
    ok = all(r["status"] == "ok" for r in results)
    return ok, results, cleaned
