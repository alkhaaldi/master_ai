"""
Brain Observability & Recovery — Phase 4.5
System diagnostics, auto-backups, safe mode monitoring.
"""
import os, time, shutil, sqlite3, logging, asyncio
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("brain.observability")

DATA_DIR = Path(__file__).parent / "data"
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_KEEP_DAYS = 7
DB_PATH = DATA_DIR / "audit.db"

# ═══════════════════════════════════════
# Error tracking (in-memory ring buffer)
# ═══════════════════════════════════════
_error_log = []  # list of (timestamp, module, message)
MAX_ERRORS = 500

def record_error(module: str, message: str):
    """Record an error for diagnostics."""
    _error_log.append((datetime.utcnow().isoformat(), module, str(message)[:200]))
    if len(_error_log) > MAX_ERRORS:
        _error_log.pop(0)

def errors_last_hour():
    cutoff = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    return len([e for e in _error_log if e[0] > cutoff])

# ═══════════════════════════════════════
# System diagnostics
# ═══════════════════════════════════════
def get_system_diag(brain_stats: dict = None) -> dict:
    """Full system diagnostics endpoint data."""
    import psutil
    
    # DB size
    db_size = 0
    if DB_PATH.exists():
        db_size = round(DB_PATH.stat().st_size / (1024 * 1024), 2)
    
    # Check DB locked
    db_locked = False
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=1)
        conn.execute("SELECT 1")
        conn.close()
    except:
        db_locked = True
    
    # Backup info
    last_backup = None
    backup_count = 0
    if BACKUP_DIR.exists():
        backups = sorted(BACKUP_DIR.glob("backup_*"))
        backup_count = len(backups)
        if backups:
            last_backup = backups[-1].name
    
    diag = {
        "timestamp": datetime.utcnow().isoformat(),
        "errors_last_hour": errors_last_hour(),
        "recent_errors": _error_log[-5:] if _error_log else [],
        "db_size_mb": db_size,
        "db_locked": db_locked,
        "backup_count": backup_count,
        "last_backup": last_backup,
        "system": {
            "cpu_percent": psutil.cpu_percent(interval=0.5),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage("/").percent,
            "temperature": _get_cpu_temp(),
        },
    }
    
    if brain_stats:
        diag["brain_modules"] = brain_stats.get("modules", {})
        diag["total_memories"] = brain_stats.get("total_memories", 0)
    
    return diag

def _get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except:
        return None

# ═══════════════════════════════════════
# Auto-backups
# ═══════════════════════════════════════
def run_backup():
    """Backup DB + knowledge + policy. Keep 7 days."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"backup_{stamp}"
    backup_path.mkdir(exist_ok=True)
    
    files_to_backup = [
        DATA_DIR / "audit.db",
        Path(__file__).parent / "knowledge.json",
        Path(__file__).parent / "policy.json",
    ]
    
    backed = []
    for f in files_to_backup:
        if f.exists():
            shutil.copy2(str(f), str(backup_path / f.name))
            backed.append(f.name)
    
    # Cleanup old backups
    _cleanup_old_backups()
    
    logger.info(f"Backup created: {backup_path.name} ({backed})")
    return {"path": str(backup_path), "files": backed}

def _cleanup_old_backups():
    if not BACKUP_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(days=BACKUP_KEEP_DAYS)
    for d in BACKUP_DIR.iterdir():
        if d.is_dir() and d.name.startswith("backup_"):
            try:
                ts = datetime.strptime(d.name, "backup_%Y%m%d_%H%M%S")
                if ts < cutoff:
                    shutil.rmtree(str(d))
                    logger.info(f"Deleted old backup: {d.name}")
            except:
                pass

async def backup_loop():
    """Daily backup at 3 AM."""
    while True:
        now = datetime.now()
        next_3am = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if now >= next_3am:
            next_3am += timedelta(days=1)
        wait = (next_3am - now).total_seconds()
        await asyncio.sleep(wait)
        try:
            run_backup()
        except Exception as e:
            record_error("backup", str(e))
            logger.error(f"Backup failed: {e}")
