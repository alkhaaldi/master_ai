#!/usr/bin/env python3
"""
Google Drive Dropzone Deployment Watcher v2
Monitors gdrive:master_ai_dropzone/ for new Python files and deploys them safely.

Fixes from v1:
- Creates deployments table if missing
- Max 3 retries per file, then moves to .dropzone_failed/
- py_compile validation BEFORE deploy
- Health check with proper wait time after restart
- Telegram notifications on success/failure
- Cleans up GDrive file after successful deploy
"""
import asyncio
import os
import sys
import json
import sqlite3
import subprocess
import shutil
import logging
from datetime import datetime
from pathlib import Path

# Configuration
BASE_DIR = Path("/home/pi/master_ai")
DROPZONE_DIR = BASE_DIR / ".dropzone"
FAILED_DIR = BASE_DIR / ".dropzone_failed"
GDRIVE_REMOTE = "gdrive:master_ai_dropzone/"
HEALTH_URL = "https://ai.salem-home.com/health"
AUDIT_DB = BASE_DIR / "audit.db"
VENV_PYTHON = BASE_DIR / "venv" / "bin" / "python3"
POLL_INTERVAL = 60  # seconds between checks
HEALTH_WAIT = 15    # seconds to wait after restart before health check
HEALTH_RETRIES = 3  # number of health check attempts
MAX_DEPLOY_RETRIES = 3  # max retries per file before giving up

# File mapping whitelist — only these files can be deployed
FILE_MAP = {
    "quick_query.py": BASE_DIR / "quick_query.py",
    "entity_map_generator.py": BASE_DIR / "entity_map_generator.py",
    "brain.py": BASE_DIR / "brain.py",
    "tg_morning_report.py": BASE_DIR / "tg_morning_report.py",
    "entity_map.json": BASE_DIR / "entity_map.json",
    "tg_intent_router.py": BASE_DIR / "tg_intent_router.py",
    "server.py": BASE_DIR / "server.py",
    "tg_ask_router.py": BASE_DIR / "tg_ask_router.py",
    "tg_ask_router_v2.py": BASE_DIR / "tg_ask_router.py",
    "life_router.py": BASE_DIR / "life_router.py",
    "life_router_v2.py": BASE_DIR / "life_router.py",
    "telegram_bot.py": BASE_DIR / "telegram_bot.py",
    "life_stocks.py": BASE_DIR / "life_stocks.py",
    "llm_tools.py": BASE_DIR / "llm_tools.py",
    "system_prompt_v6.py": BASE_DIR / "system_prompt_v6.py",
    "chat_endpoint.py": BASE_DIR / "chat_endpoint.py",
}

# Retry tracker: filename -> attempt count
_retry_counts = {}

# Telegram config (from systemd env)
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(BASE_DIR / "dropzone.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ─── Helpers ───────────────────────────────────────────────

def run_cmd(cmd, timeout=30):
    """Run subprocess with timeout."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out: {cmd}")
        return False, "", "Timeout"


def _ensure_deployments_table():
    """Create deployments table if it doesn't exist."""
    try:
        with sqlite3.connect(AUDIT_DB) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS deployments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    rollback INTEGER DEFAULT 0,
                    details TEXT DEFAULT ''
                )
            """)
    except Exception as e:
        logger.error(f"Failed to ensure deployments table: {e}")


def log_deployment(filename, status, rollback=False, details=""):
    """Log deployment to audit.db."""
    try:
        _ensure_deployments_table()
        with sqlite3.connect(AUDIT_DB) as conn:
            conn.execute(
                "INSERT INTO deployments (filename, status, timestamp, rollback, details) VALUES (?, ?, ?, ?, ?)",
                (filename, status, datetime.utcnow().isoformat(), int(rollback), details)
            )
    except Exception as e:
        logger.error(f"Failed to log deployment: {e}")


def send_telegram(message):
    """Send Telegram notification."""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    try:
        import httpx
        httpx.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")


def check_health():
    """Check service health with retries."""
    for attempt in range(HEALTH_RETRIES):
        success, stdout, stderr = run_cmd(f"curl -sf {HEALTH_URL}", timeout=10)
        if success:
            try:
                data = json.loads(stdout)
                if data.get("status") == "ok":
                    return True
            except Exception:
                pass
        if attempt < HEALTH_RETRIES - 1:
            logger.info(f"Health check attempt {attempt+1}/{HEALTH_RETRIES} failed, retrying in 5s...")
            import time
            time.sleep(5)
    return False


def validate_python(filepath):
    """Validate Python file syntax using py_compile."""
    success, stdout, stderr = run_cmd(f"{VENV_PYTHON} -m py_compile {filepath}")
    if not success:
        logger.error(f"Validation failed for {filepath}: {stderr}")
    return success


def backup_file(target_path):
    """Create timestamped backup of target file."""
    if not target_path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = target_path.with_suffix(f".bak.{timestamp}")
    shutil.copy2(target_path, backup_path)
    logger.info(f"Backup created: {backup_path}")
    return backup_path


def restore_backup(backup_path, target_path):
    """Restore from backup."""
    if backup_path and backup_path.exists():
        shutil.copy2(backup_path, target_path)
        logger.info(f"Restored backup: {backup_path} -> {target_path}")
        backup_path.unlink()


def cleanup_gdrive(filename):
    """Remove file from GDrive dropzone after successful deploy."""
    success, _, stderr = run_cmd(f"rclone delete {GDRIVE_REMOTE}{filename}")
    if success:
        logger.info(f"Cleaned up GDrive: {filename}")
    else:
        logger.warning(f"Failed to clean GDrive {filename}: {stderr}")


def move_to_failed(local_file, filename):
    """Move failed file to .dropzone_failed/ for manual review."""
    FAILED_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = FAILED_DIR / f"{filename}.{ts}"
    if local_file.exists():
        shutil.move(str(local_file), str(dest))
        logger.info(f"Moved failed file to: {dest}")


# ─── Core Logic ────────────────────────────────────────────

async def check_dropzone():
    """Check for new files in Drive dropzone."""
    logger.info("Checking dropzone...")

    # List files in Drive
    success, stdout, stderr = run_cmd(f"rclone ls {GDRIVE_REMOTE}")
    if not success:
        logger.error(f"rclone ls failed: {stderr}")
        return

    if not stdout.strip():
        logger.debug("No files in dropzone")
        return

    # Process each file
    for line in stdout.strip().split('\n'):
        if not line.strip():
            continue

        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue

        size, filename = parts
        if not filename.endswith(".py"):
            logger.info(f"Ignoring non-Python file: {filename}")
            continue

        if filename not in FILE_MAP:
            logger.warning(f"Unknown file (not in whitelist): {filename}")
            continue

        # Check retry count
        retries = _retry_counts.get(filename, 0)
        if retries >= MAX_DEPLOY_RETRIES:
            logger.error(f"Max retries ({MAX_DEPLOY_RETRIES}) reached for {filename}, moving to failed")
            DROPZONE_DIR.mkdir(exist_ok=True)
            local = DROPZONE_DIR / filename
            run_cmd(f"rclone copy {GDRIVE_REMOTE}{filename} {DROPZONE_DIR}/")
            move_to_failed(local, filename)
            cleanup_gdrive(filename)
            _retry_counts.pop(filename, None)
            send_telegram(f"❌ *Dropzone:* `{filename}` failed after {MAX_DEPLOY_RETRIES} attempts. Moved to .dropzone_failed/")
            log_deployment(filename, "failed_max_retries", details=f"Gave up after {MAX_DEPLOY_RETRIES} attempts")
            continue

        await deploy_file(filename)


async def deploy_file(filename):
    """Deploy a single file safely."""
    logger.info(f"Deploying {filename} (attempt {_retry_counts.get(filename, 0) + 1}/{MAX_DEPLOY_RETRIES})")
    target_path = FILE_MAP[filename]
    backup_path = None

    try:
        # 1. Create staging dir
        DROPZONE_DIR.mkdir(exist_ok=True)

        # 2. Download from Drive
        local_file = DROPZONE_DIR / filename
        success, stdout, stderr = run_cmd(f"rclone copy {GDRIVE_REMOTE}{filename} {DROPZONE_DIR}/")
        if not success:
            raise Exception(f"rclone copy failed: {stderr}")

        if not local_file.exists():
            raise Exception(f"Downloaded file not found: {local_file}")

        logger.info(f"Downloaded {filename} ({local_file.stat().st_size} bytes)")

        # 3. Validate syntax BEFORE deployment
        if not validate_python(local_file):
            raise Exception("Python syntax validation failed (py_compile)")

        logger.info(f"Validation passed for {filename}")

        # 4. Backup current file
        backup_path = backup_file(target_path)

        # 5. Deploy (copy to target)
        shutil.copy2(local_file, target_path)
        logger.info(f"Deployed {filename} -> {target_path}")

        # 6. Restart service (only for server.py)
        if filename == "server.py":
            logger.info("Restarting master-ai service...")
            run_cmd("sudo systemctl restart master-ai.service", timeout=30)
            logger.info(f"Waiting {HEALTH_WAIT}s for service to start...")
            await asyncio.sleep(HEALTH_WAIT)

            # 7. Health check
            if not check_health():
                raise Exception("Health check failed after restart")
        else:
            # For non-server files, just verify service is still healthy
            if not check_health():
                logger.warning(f"Service unhealthy after deploying {filename}, but not server.py")

        # 8. Success!
        logger.info(f"✅ Successfully deployed {filename}")
        log_deployment(filename, "success")
        send_telegram(f"✅ *Dropzone Deploy:* `{filename}` deployed successfully")

        # 9. Cleanup
        cleanup_gdrive(filename)
        if local_file.exists():
            local_file.unlink()
        if backup_path and backup_path.exists():
            backup_path.unlink()
        _retry_counts.pop(filename, None)

    except Exception as e:
        logger.error(f"Deployment failed for {filename}: {e}")
        _retry_counts[filename] = _retry_counts.get(filename, 0) + 1

        # Rollback if we have a backup
        if backup_path:
            logger.info(f"Rolling back {filename}...")
            restore_backup(backup_path, target_path)
            log_deployment(filename, "rollback", rollback=True, details=str(e))

            if filename == "server.py":
                run_cmd("sudo systemctl restart master-ai.service", timeout=30)
                await asyncio.sleep(HEALTH_WAIT)
                if check_health():
                    logger.info("Rollback successful, service healthy")
                    send_telegram(f"⚠️ *Dropzone:* `{filename}` deploy failed, rolled back.\nError: {e}")
                else:
                    logger.error("Service STILL unhealthy after rollback!")
                    send_telegram(f"🚨 *Dropzone CRITICAL:* `{filename}` rollback failed!\nError: {e}")
            else:
                send_telegram(f"⚠️ *Dropzone:* `{filename}` deploy failed, rolled back.\nError: {e}")
        else:
            log_deployment(filename, "failed", details=str(e))
            send_telegram(f"❌ *Dropzone:* `{filename}` deploy failed.\nError: {e}")

        # Cleanup staging
        local_file = DROPZONE_DIR / filename
        if local_file.exists():
            local_file.unlink()


async def main():
    """Main polling loop."""
    logger.info("=" * 50)
    logger.info("Dropzone Watcher v2 starting...")
    logger.info(f"Watching: {GDRIVE_REMOTE}")
    logger.info(f"Whitelist: {list(FILE_MAP.keys())}")
    logger.info(f"Poll interval: {POLL_INTERVAL}s")
    logger.info(f"Max retries: {MAX_DEPLOY_RETRIES}")
    logger.info("=" * 50)

    _ensure_deployments_table()

    while True:
        try:
            await check_dropzone()
        except Exception as e:
            logger.error(f"Unexpected error in check_dropzone: {e}")
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
