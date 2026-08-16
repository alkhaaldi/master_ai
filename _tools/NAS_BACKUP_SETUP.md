# NAS BACKUP — ready-to-apply setup

- Prepared by: claude.ai, 2026-08-16
- NAS: `192.168.109.45` (Synology) — SMB 445 open, `mount.cifs` present at
  `/sbin/mount.cifs`, RPi reaches it (ping ok). Network is NOT the blocker.
- Blocker: the RPi has **no CIFS mount, no fstab entry, no credentials**.
  The only NAS access today is inside Music Assistant's own SMB client.

## PART A — on the NAS (DSM web UI) — the user only

Two things nobody else should do: creating the account, and setting its
password.

1. **Control Panel → Shared Folder → Create**
   - Name: `backups`
   - Enable Recycle Bin
   - Do NOT enable "Hide in My Network Places"

2. **Control Panel → User & Group → User → Create**
   - Name: `rpi_backup`
   - Groups: **`users` only — NOT `administrators`**
   - Permissions: `backups` = Read/Write · **every other share = No Access**
     (explicitly No Access on `Quran` — it stays media-only)
   - Do NOT grant SSH / Terminal to this user

Why a dedicated user: the RPi is reachable from the internet through the
tunnel. Whatever credential sits on it is exposed if the RPi is. A
write-to-one-folder account limits that to one folder. An admin account would
hand over the whole NAS — including the backups it is meant to protect.

## PART B — on the RPi (Claude Code)

### B1. Credentials file — the user types the password, nobody else

```
sudo install -m 600 -o root -g root /dev/null /etc/cifs-credentials-nas
sudo nano /etc/cifs-credentials-nas
```

Contents (exactly three lines):

```
username=rpi_backup
password=<typed by the user, never pasted into a chat or a repo>
domain=WORKGROUP
```

Confirm afterwards: `ls -l /etc/cifs-credentials-nas` shows `-rw------- root root`.
This file must never enter git. Verify it is outside the repo — it is.

### B2. Mount point and fstab

```
sudo mkdir -p /mnt/nas-backups
```

Append to `/etc/fstab` (one line, exactly this — `nofail` and `_netdev` keep a
missing NAS from blocking boot):

```
//192.168.109.45/backups /mnt/nas-backups cifs credentials=/etc/cifs-credentials-nas,uid=pi,gid=pi,file_mode=0640,dir_mode=0750,vers=3.0,_netdev,nofail,x-systemd.automount,x-systemd.mount-timeout=30 0 0
```

Notes on the options, so they are not cargo-culted:
- `nofail` — the RPi must still boot if the NAS is down. Without it a NAS
  outage becomes an RPi outage.
- `x-systemd.automount` — mounts on first access rather than at boot, which
  survives the NAS booting slower than the Pi.
- `vers=3.0` — if the mount fails with `Unable to negotiate`, try `vers=2.1`.
  Do not fall back to `vers=1.0`; SMB1 is deprecated and unsafe.
- `uid=pi` — so the service (running as pi) can write without sudo.

Apply and verify:

```
sudo systemctl daemon-reload
sudo mount -a
mountpoint /mnt/nas-backups && echo MOUNTED
```

### B3. Prove write access before scheduling anything

```
mkdir -p /mnt/nas-backups/master_ai
date > /mnt/nas-backups/master_ai/.write_test
cat /mnt/nas-backups/master_ai/.write_test && rm /mnt/nas-backups/master_ai/.write_test
```

If this fails, stop. A scheduled backup pointing at a path it cannot write is
worse than no backup — it looks configured and produces nothing.

### B4. Point `nas_backup.py` at the mount

`_tools/nas_backup.py` was written against an ssh-push design (blocked, since
`svc-claude` SSH is off and should stay off). Retarget it at
`/mnt/nas-backups/master_ai`. Everything else in it stays: `sqlite3` backup API
rather than `cp`, gzip, keep 14, witness row, Telegram on failure.

Then run it once by hand, and run `--verify-restore` on the result before
trusting the cron at 14:30.

## PART C — the two dead backups (do this in the same pass)

Discovered 2026-08-16 and more urgent than the NAS work itself: two backup
crons have been running nightly and **failing since 2026-04-02**.

```
03:10  scripts/backup_now.sh      → last successful dir: backups/20260402_031001
       line 23: $'\r': command not found      (CRLF line endings)
       SyntaxError: unterminated string literal

03:30  scripts/gdrive_backup.sh   → fails on EVERY run
       line 3: set: pipefail: invalid option name   (running under sh, not bash)
```

`backups/cron.log` has grown to 156 KB of failure messages that nobody opened.

So the last off-device copy of anything is from 2 April — the same date as the
frozen prices that started this whole phase. Everything since, including the
journal, `decision_audit`, `signal_reviews` and `confidence_census`, exists on
one SD card.

**Fix or delete — do not leave them failing:**
1. `backup_now.sh`: convert to LF (`dos2unix` or `sed -i 's/\r$//'`), then fix
   the Python string error it also reports.
2. `gdrive_backup.sh`: either give it `#!/bin/bash` or drop `pipefail`.
3. Add `.gitattributes` forcing `*.sh text eol=lf` — these files are edited
   from Windows over Samba, so CRLF will come back otherwise. This is the
   actual root cause, not the individual script.
4. Every backup path alerts on failure. A nightly job that fails into a log
   file is not monitoring.
5. `quick_check` gets a backup-age check **per path**, not only for the NAS.

## Order

1. PART C first — two broken paths already exist; a third is not the priority
2. PART A — the user, on DSM
3. PART B — Claude Code, after A
4. `--verify-restore` before anyone calls this done

## Acceptance

`mountpoint /mnt/nas-backups` succeeds · a gzipped backup lands under
`master_ai/` · `--verify-restore` reports `integrity_check ok` with matching
row counts · `quick_check` returns 15/15 · and the 03:10 and 03:30 jobs either
succeed or no longer exist.

---

## OPEN ITEM — rotate the rpi_backup password (deferred by the user, 2026-08-16)

The password currently in `/etc/cifs-credentials-nas` was pasted into a chat
session twice (once as terminal output, once in a screenshot of the nano
buffer). Treat it as disclosed.

Blast radius, stated honestly: the account is `users`-group only, R/W on the
`backups` share alone, denied Quran and every other share, no DSM and no SSH.
So the exposure is bounded to one folder - but that folder is the off-device
copy of everything, and whoever holds this credential can read or delete it.

The user chose to finish the setup first and rotate in a later session. That
is a legitimate call; recording it here so "I'll change it later" does not
become the silent-failure pattern this whole phase exists to remove.

**To close it:**
1. DSM: `Control Panel → User → rpi_backup → Edit → Password` - new value,
   never pasted into a chat or a screenshot.
2. RPi: `sudo nano /etc/cifs-credentials-nas`, replace the `password=` line,
   save (`Ctrl+O`, `Enter`, `Ctrl+X`).
3. `sudo umount /mnt/nas-backups 2>/dev/null; ls /mnt/nas-backups` to force a
   fresh automount with the new credential.
4. `venv/bin/python3 _tools/nas_backup.py` - a green run confirms it; a failed
   one alerts by itself now.

Nothing else in the system holds this password: `mount.cifs` reads the file
directly and `nas_backup.py` never touches it.
