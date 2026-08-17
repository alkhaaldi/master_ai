# PLAN: Synology NAS (HOMECLOUD) - full setup & integration

Date: 2026-08-12
Target: 192.168.109.45 (HOMECLOUD), MAC 90-09-D0-A1-EB-41
Owner split: USER = DSM web UI (needs login) · CC = Claude Code on RPi · AI = claude.ai

## Verified starting state (probed 2026-08-12 from PC)

```
Open : 5000/5001 DSM · 445 SMB · 6690 Synology Drive
Closed: 22 SSH · 873 rsync · 2049 NFS
Installed: Active Backup for Business, Synology Photos, Synology Drive
NOT installed: Container Manager (Docker)
Storage/volume state: UNKNOWN - Phase 0 must confirm
```

## Goals (user-stated)
1. Backups for Master AI + RPi
2. Family files & photos
3. Docker services
4. Remote access via QuickConnect
5. Get value out of the full package set

## Ground rules
- NOTHING in this plan touches Master AI application logic.
- Secrets (`.env`, `~/.master_ai_key`, `~/.ha_token`) go to a RESTRICTED share only,
  never to a share that family accounts can browse.
- Do not enable SSH on the NAS until Phase 3 needs it; close it again after.
- Every phase ends with a verification step. Do not skip.

---

## PHASE 0 - Discovery (USER, ~10 min)

Log into `http://192.168.109.45:5000` and report back these values.
Everything after this depends on them.

| Where | What to report |
|---|---|
| Control Panel > Info Center | Model, DSM version, RAM |
| Storage Manager > Storage | Storage Pool exists? RAID type? Volume created? Size + free |
| Storage Manager > HDD/SSD | How many disks, size each, health status |
| Package Center | Is "Container Manager" listed as available to install? |
| Control Panel > Shared Folder | Which shares exist already |
| Control Panel > User | Which accounts exist besides admin |

Note: if the model is a "j" or "Value" series with low RAM, Container Manager
may not be offered at all. That decides whether Phase 5 happens.

## PHASE 1 - Foundation (USER, DSM UI)

1. **Storage** - if no Volume exists: create Storage Pool + Volume.
   - 2 disks -> SHR or RAID 1 (mirror). 4+ disks -> SHR-2 or RAID 6.
   - Filesystem: **Btrfs** (required for snapshots - do not pick ext4).
2. **Accounts** - disable the default `admin` account, create a personal admin
   user with a strong password. Create separate limited users for family.
3. **Security**
   - Control Panel > Security > Account: enable auto-block (5 fails / 30 min)
   - Enable 2FA on the admin account
   - Control Panel > Security > Advisor: run the scan, fix what it flags
   - DSM > Firewall: allow LAN subnet `192.168.108.0/22`, deny the rest
4. **Network** - reserve `192.168.109.45` for MAC `90-09-D0-A1-EB-41` on the
   BE800 (`http://192.168.108.1`). Do the PC reservation in the same visit.
5. **QuickConnect** - Control Panel > External Access > QuickConnect.
   Pick a QuickConnect ID, enable 2FA first. Do NOT port-forward 5000/5001.

**Verify:** volume healthy, Security Advisor clean, QuickConnect reachable from
mobile data (not WiFi).

## PHASE 2 - Shared folder layout (USER, DSM UI)

Create these shares. Enable **Btrfs snapshots** on all except `scratch`.

| Share | Purpose | Access |
|---|---|---|
| `backup-masterai` | RPi / Master AI backups | admin + `svc-rpi` only |
| `backup-pc` | Active Backup target for the PC | admin only |
| `secrets` | `.env`, tokens, key material | admin only, **encrypted share** |
| `family` | shared documents | family users |
| `photos` | Synology Photos library | family users |
| `media` | video/audio | family users, read-only for kids |
| `scratch` | temp, no snapshots | anyone |

Create a service account `svc-rpi` with write access to `backup-masterai` ONLY.
This is the account the Raspberry Pi will use - it must not see anything else.

**Snapshot schedule** (Snapshot Replication package):
- `backup-masterai`, `secrets`: hourly, keep 24 hourly / 14 daily / 8 weekly
- `family`, `photos`: daily, keep 30 daily / 12 monthly
- Enable "immutable snapshots" if the DSM version offers it - this is the real
  ransomware defense.

## PHASE 3 - Master AI / RPi backup (CC does the RPi side)

### 3a. USER enables access (DSM UI)
- Control Panel > File Services > SMB: ensure enabled
- Control Panel > Terminal & SNMP > enable SSH **temporarily** (Phase 3 only)

### 3b. CC work on the RPi

Create `_tools/nas_backup.sh`. Requirements:

1. Mount the NAS share via CIFS with credentials in `/root/.nas_cred`
   (mode 600), fstab entry using `credentials=`, NEVER inline password.
   Mount point: `/mnt/nas-backup`.
2. Back up, into `/mnt/nas-backup/rpi/<YYYY-MM-DD>/`:
   - **SQLite DBs**: use `sqlite3 <db> ".backup '<dest>'"` — do NOT `cp` a live
     DB, it will produce a corrupt/torn file.
   - **Git**: `git bundle create master_ai.bundle --all` (single restorable file)
   - **Config**: `.env`, `_tools/`, HA `configuration.yaml`, dashboards
   - **systemd units** for master-ai and cloudflared
3. `.env` and any token file go to the `secrets` share, not `backup-masterai`.
4. Retention: keep 14 daily + 8 weekly, prune older.
5. Log to `/mnt/nas-backup/rpi/backup.log` and exit non-zero on failure.
6. systemd timer, nightly at 03:00 Kuwait time.

### 3c. Move Master AI logs off the RPi (CC)

Today `server.log.1` alone is 4.6 MB and rotated logs got committed to git
(~570k lines) - see `_tools/CLEANUP_COMMIT_1628f70.md`.

- Point logrotate's archive destination at `/mnt/nas-backup/rpi/logs/`
- Keep only the ACTIVE log on the SD card
- Benefit: less SD card wear, and log history survives an SD failure

### 3d. RESTORE TEST - mandatory, do not skip
A backup that was never restored is not a backup.

```bash
# on the RPi, into a scratch dir - must NOT touch production
mkdir -p /tmp/restore_test && cd /tmp/restore_test
git clone /mnt/nas-backup/rpi/<date>/master_ai.bundle restored
sqlite3 /mnt/nas-backup/rpi/<date>/<db>.sqlite "PRAGMA integrity_check;"
```
Expected: clone succeeds, `integrity_check` returns `ok`.
Report both outputs before calling Phase 3 done.

### 3e. USER: disable SSH on the NAS again once 3d passes.

## PHASE 4 - PC backup (USER, ~20 min)

Active Backup for Business is already installed.
1. DSM > Active Backup for Business > Physical Server > download the Windows agent
2. Install on the PC, point it at `192.168.109.45`, target share `backup-pc`
3. Task: **entire device**, weekly full + daily incremental, retention 4 weeks
4. Create the recovery media (USB) from ABB Portal - do this NOW, not after a
   disk dies

**Verify:** run one backup, then open ABB > Restore and confirm you can browse
individual files inside the image.

## PHASE 5 - Docker / Container Manager (only if Phase 0 says it's supported)

Install Container Manager from Package Center, then deploy in this order.

### 5a. Uptime Kuma - HIGHEST VALUE, do this first
Directly prevents a repeat of the 2026-08-12 incident, where the Bridge was
down for an unknown period and the only symptom was a broken dashboard page.

Monitors to create:
```
http://192.168.111.214:8059/health     TradingView Bridge   every 60s
http://192.168.109.123:9000/health     Master AI            every 60s
http://192.168.109.123:8123            Home Assistant       every 60s
https://ai.salem-home.com/health       Cloudflare tunnel    every 300s
192.168.108.1                          Router (ping)        every 300s
```
Notification channel: Telegram (Master AI already has a bot - reuse it).

### 5b. Optional containers, by value
- **Watchtower** - auto-update containers
- **Vaultwarden** - self-hosted password manager (needs HTTPS via QuickConnect)
- **Paperless-ngx** - scan/index household documents
- **Syncthing** - PC <-> NAS folder sync outside Synology Drive

### NOT recommended: moving the TradingView Bridge to the NAS
The Bridge depends on Chrome CDP for TradingView JWT token management. That
needs a real desktop Chrome session, which the NAS does not have. Leave the
Bridge on the PC. `BRIDGE_URL` in `.env` already makes its address swappable.

## PHASE 6 - Everything else worth turning on (USER)

- **Synology Photos** - point at `photos`, enable mobile auto-upload for the
  family. Face/subject grouping runs locally, nothing goes to a cloud.
- **Synology Drive** - already running (port 6690). Sync `family` to the PC.
- **Surveillance Station** - 2 camera licenses are included free. You have 6
  Dahua cameras on an NVR; putting even 2 on the NAS gives a second independent
  recording path if the NVR fails.
- **Hyper Backup** - the NAS itself needs a backup. Target: external USB drive
  or Synology C2. This is the "3-2-1" off-box copy. RAID is not a backup.
- **Storage Analyzer**, **Log Center** (point RPi syslog at it later).

## PHASE 7 - Master AI integration (CC + AI)

Only after Phases 3 and 5 are green.

- **CC**: add a `/system/backup-status` endpoint reading the backup log -
  returns `last_backup_at`, `size_bytes`, `ok`, `reason`. Business errors return
  HTTP 200 with `{"error": ...}` — see the Cloudflare 5xx rule in
  `OPERATIONAL_ACCESS_MATRIX.md`.
- **AI (claude.ai)**: add a backup/NAS card to `system.html` - last backup time,
  green/amber/red, free space on the NAS.
- **CC**: Telegram alert if no successful backup in 36 hours.

## Execution order (short version)

```
Phase 0  USER  discovery            <- START HERE, blocks everything
Phase 1  USER  storage + security + QuickConnect
Phase 2  USER  shares + snapshots
Phase 3  CC    RPi backup + logs + RESTORE TEST
Phase 4  USER  PC image backup
Phase 5  USER  Container Manager + Uptime Kuma
Phase 6  USER  Photos / Drive / Surveillance / Hyper Backup
Phase 7  CC+AI dashboard integration
```

## Things that must not be skipped
1. Btrfs, not ext4 - no snapshots otherwise, and it cannot be changed later
   without wiping the volume.
2. The restore test in 3d.
3. Hyper Backup off-box copy in Phase 6. RAID protects against a dead disk,
   not against deletion, ransomware, fire, or theft.
4. Secrets to the encrypted `secrets` share only.
5. Disable SSH on the NAS after Phase 3.
