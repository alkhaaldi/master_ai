#!/usr/bin/env python3
"""F-1: back up life.db to the NAS over CIFS - no SSH on the NAS at all.

Transport redesigned by user decision 2026-08-16: the NAS stays closed
(no DSM SSH, no admin credentials on this exposed machine). The RPi
mounts //192.168.109.45/backups with the dedicated low-privilege user
rpi_backup (users group, R/W on that share alone), credentials in
/etc/cifs-credentials-nas mode 600, written by the user himself.

The snapshot is taken on the RPi with the sqlite3 backup API - never cp
on the LIVE db; copying the finished gz onto the mount is fine because
the gz is already a consistent, closed file. Keeps the newest 14.
Every run lands in data_fetch_runs (source=nas_backup); failures alert
Telegram; quick_check turns red past 24h.

  --verify-restore : restore the newest backup to scratch, run
                     PRAGMA integrity_check, compare row counts.
"""
import gzip
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, "/home/pi/master_ai")
sys.path.insert(0, "/home/pi/master_ai/_tools")
import run_witness

DB = "/home/pi/master_ai/data/life.db"
NAS_HOST = "192.168.109.45"
SHARE = "backups"
CREDS = "/etc/cifs-credentials-nas"
# B4: the fstab entry owns the mount now (x-systemd.automount, nofail,
# _netdev). This script no longer runs `sudo mount` itself - touching the
# path is what triggers it, and a NAS outage degrades to a failed backup
# with an alert instead of a boot that hangs.
MOUNT = "/mnt/nas-backups"
SUBDIR = "master_ai"          # -> /volume1/backups/master_ai on the NAS
KEEP = 14
SOURCE = "nas_backup"


def ensure_mounted():
    """Trigger the systemd automount and confirm it took.

    The credentials never pass through this process: mount.cifs reads the
    root-owned 600 file itself. A blank or wrong credential shows up here
    as a mount that did not happen, which is exactly what should be
    reported rather than worked around.
    """
    try:
        os.listdir(MOUNT)          # the access that fires the automount
    except OSError as e:
        raise RuntimeError("cannot reach %s: %s" % (MOUNT, e))
    if not os.path.ismount(MOUNT):
        hint = ""
        try:
            if os.path.getsize(CREDS) == 0:
                hint = " - %s is empty (password not set yet)" % CREDS
        except OSError:
            hint = " - %s is unreadable from here (expected: root 600)" % CREDS
        raise RuntimeError("%s is not mounted%s" % (MOUNT, hint))


def make_backup():
    t0 = time.time()
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    tmp_db = "/tmp/life_backup_%s.db" % stamp
    tmp_gz = tmp_db + ".gz"
    try:
        ensure_mounted()
        dest_dir = os.path.join(MOUNT, SUBDIR)
        os.makedirs(dest_dir, exist_ok=True)

        # consistent snapshot of the live db via the backup API
        src = sqlite3.connect(DB, timeout=30)
        dst = sqlite3.connect(tmp_db)
        src.backup(dst)
        dst.close()
        src.close()
        with open(tmp_db, "rb") as f_in, gzip.open(tmp_gz, "wb", compresslevel=6) as f_out:
            while chunk := f_in.read(1 << 20):
                f_out.write(chunk)
        size = os.path.getsize(tmp_gz)

        dest = os.path.join(dest_dir, "life_%s.db.gz" % stamp)
        shutil.copyfile(tmp_gz, dest + ".part")
        os.replace(dest + ".part", dest)

        # verify what actually landed on the NAS: size + gzip integrity
        landed = os.path.getsize(dest)
        if landed != size:
            raise RuntimeError("size mismatch local %d vs nas %d" % (size, landed))
        with gzip.open(dest, "rb") as f:
            while f.read(1 << 20):
                pass

        # prune to the newest KEEP
        files = sorted(f for f in os.listdir(dest_dir)
                       if f.startswith("life_") and f.endswith(".db.gz"))
        for old in files[:-KEEP]:
            os.remove(os.path.join(dest_dir, old))

        dur = time.time() - t0
        run_witness.log_run(SOURCE, "success", 1, 1, dur, None)
        print("backup ok: %s (%d bytes, %.1fs, kept %d)"
              % (dest, size, dur, min(len(files), KEEP)))
        return True
    except Exception as e:
        run_witness.log_run(SOURCE, "failed", 0, 1, time.time() - t0, str(e)[:300])
        run_witness.send_telegram("⚠️ النسخ الاحتياطي إلى الناس فشل: %s" % str(e)[:200])
        print("backup FAILED: %r" % e)
        return False
    finally:
        for p in (tmp_db, tmp_gz):
            if os.path.exists(p):
                os.remove(p)


def verify_restore():
    ensure_mounted()
    dest_dir = os.path.join(MOUNT, SUBDIR)
    files = sorted(f for f in os.listdir(dest_dir)
                   if f.startswith("life_") and f.endswith(".db.gz"))
    if not files:
        print("verify FAILED: no backup on the share")
        return False
    newest = os.path.join(dest_dir, files[-1])
    print("newest on nas:", newest)
    scratch_db = "/tmp/restore_check.db"
    try:
        with gzip.open(newest, "rb") as f_in, open(scratch_db, "wb") as f_out:
            while chunk := f_in.read(1 << 20):
                f_out.write(chunk)
        rc = sqlite3.connect(scratch_db)
        integ = rc.execute("PRAGMA integrity_check").fetchone()[0]
        print("integrity_check:", integ)
        live = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
        for t in ("trades", "signal_snapshots", "stock_radar_daily", "confidence_census"):
            a = rc.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
            b = live.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
            print("  %-20s restored=%-7d live=%-7d %s"
                  % (t, a, b, "match" if a == b else "differs (live moved on)"))
        rc.close()
        live.close()
        return integ == "ok"
    finally:
        if os.path.exists(scratch_db):
            os.remove(scratch_db)


if __name__ == "__main__":
    ok = verify_restore() if "--verify-restore" in sys.argv else make_backup()
    sys.exit(0 if ok else 1)
