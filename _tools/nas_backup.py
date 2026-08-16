#!/usr/bin/env python3
"""F-1: back up life.db to the NAS - sqlite3 backup API, never cp.

Copying a live SQLite file mid-write produces a corrupt snapshot that
restores silently and fails later: this project's disease in backup form.
The backup API takes a consistent snapshot while the service keeps writing.

Path: RPi -> ssh nas (svc-claude@HOMECLOUD). Target dir is NAS_BACKUP_DIR
(env) or the default below - confirmed with the user before first use.
Keeps the newest 14, gzipped. Every run lands in data_fetch_runs
(source=nas_backup) through run_witness; failure alerts Telegram.

  --verify-restore : pull the newest backup, restore to scratch, run
                     PRAGMA integrity_check and compare row counts with
                     the live DB. A backup never restored is a hope.
"""
import gzip
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, "/home/pi/master_ai")
sys.path.insert(0, "/home/pi/master_ai/_tools")
import run_witness

DB = "/home/pi/master_ai/data/life.db"
NAS_DIR = os.environ.get("NAS_BACKUP_DIR", "/volume1/backups/master_ai")
KEEP = 14
SOURCE = "nas_backup"


def _nas(cmd, inp=None, timeout=300):
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                           "nas", cmd], input=inp, capture_output=True, timeout=timeout)


def make_backup():
    t0 = time.time()
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    tmp_db = "/tmp/life_backup_%s.db" % stamp
    tmp_gz = tmp_db + ".gz"
    remote = "%s/life_%s.db.gz" % (NAS_DIR, stamp)
    try:
        # consistent snapshot via the backup API
        src = sqlite3.connect(DB, timeout=30)
        dst = sqlite3.connect(tmp_db)
        src.backup(dst)
        dst.close()
        src.close()
        with open(tmp_db, "rb") as f_in, gzip.open(tmp_gz, "wb", compresslevel=6) as f_out:
            while chunk := f_in.read(1 << 20):
                f_out.write(chunk)
        size = os.path.getsize(tmp_gz)

        r = _nas("mkdir -p %s && cat > %s.part && mv %s.part %s && gzip -t %s && stat -c%%s %s"
                 % (NAS_DIR, remote, remote, remote, remote, remote),
                 inp=open(tmp_gz, "rb").read())
        if r.returncode != 0:
            raise RuntimeError("nas transfer/verify failed: %s"
                               % r.stderr.decode(errors="replace").strip()[:300])
        remote_size = int(r.stdout.decode().strip().splitlines()[-1])
        if remote_size != size:
            raise RuntimeError("size mismatch local %d vs nas %d" % (size, remote_size))

        # prune to the newest KEEP
        _nas("cd %s && ls -1t life_*.db.gz 2>/dev/null | tail -n +%d | xargs -r rm --"
             % (NAS_DIR, KEEP + 1))

        dur = time.time() - t0
        run_witness.log_run(SOURCE, "success", 1, 1, dur, None)
        print("backup ok: %s (%d bytes, %.1fs)" % (remote, size, dur))
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
    r = _nas("ls -1t %s/life_*.db.gz | head -1" % NAS_DIR)
    newest = r.stdout.decode().strip()
    if r.returncode != 0 or not newest:
        print("verify FAILED: no backup found on nas (%s)"
              % r.stderr.decode(errors="replace").strip()[:200])
        return False
    print("newest on nas:", newest)
    r = _nas("cat %s" % newest, timeout=600)
    if r.returncode != 0:
        print("verify FAILED: pull failed")
        return False
    scratch_gz = "/tmp/restore_check.db.gz"
    scratch_db = "/tmp/restore_check.db"
    with open(scratch_gz, "wb") as f:
        f.write(r.stdout)
    with gzip.open(scratch_gz, "rb") as f_in, open(scratch_db, "wb") as f_out:
        while chunk := f_in.read(1 << 20):
            f_out.write(chunk)
    try:
        rc = sqlite3.connect(scratch_db)
        integ = rc.execute("PRAGMA integrity_check").fetchone()[0]
        live = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
        print("integrity_check:", integ)
        for t in ("trades", "signal_snapshots", "stock_radar_daily", "confidence_census"):
            a = rc.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
            b = live.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
            print("  %-20s restored=%-7d live=%-7d %s"
                  % (t, a, b, "match" if a == b else "differs (live moved on - fine if small)"))
        rc.close()
        live.close()
        return integ == "ok"
    finally:
        for p in (scratch_gz, scratch_db):
            if os.path.exists(p):
                os.remove(p)


if __name__ == "__main__":
    if "--verify-restore" in sys.argv:
        ok = verify_restore()
    else:
        ok = make_backup()
    sys.exit(0 if ok else 1)
