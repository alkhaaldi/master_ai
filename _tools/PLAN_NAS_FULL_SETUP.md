# PLAN: HOMECLOUD NAS — full setup, phased, interactive

Date: 2026-08-13
Owner: Claude Code (runs ON THE RPi, connects to NAS over SSH)
Target: HOMECLOUD @ 192.168.109.45 (MAC 90-09-D0-A1-EB-41)
Style: **ONE PHASE AT A TIME.** Stop and report after each phase.
       Wait for the user to say continue. Do NOT run ahead.

## Verified state (probed 2026-08-12/13)

```
Open ports : 5000/5001 DSM · 445 SMB · 6690 Synology Drive
Closed     : 22 SSH · 873 rsync · 2049 NFS
Installed  : Active Backup for Business, Synology Photos, Synology Drive
NOT there  : Container Manager (Docker)
QuickConnect: ID=alkhaaldi, relay ON, all services enabled
Health     : CPU 2%, RAM 45%, uptime ~19h, LAN1 gigabit, ~21.9 MB/s observed
Cert       : self-signed (browser warns on local IP)
Unknown    : model, RAM size, disk count, RAID type, volume filesystem
```

## Known open issues to fix

1. Shared folders (e.g. `documents`) do not appear in the Synology Drive
   mobile app — Team Folder not enabled.
2. `work` folder under My Drive: uploads from the phone report success but
   files do not appear.
3. Photo upload from phone stalls between files (indexing/thumbnail bound,
   not network bound).
4. Self-signed certificate.

## Ground rules

- NOTHING destructive without asking: no volume changes, no deleting shares,
  no wiping, no package removal.
- Do not touch Master AI production code in this plan.
- Secrets never printed to chat or committed to git.
- Every phase ends with a short report: what changed, what was verified,
  what the user must click on his side.

---

# PHASE 0 — Access (USER first, then CC)

### 0a. USER, in DSM (local network only)
1. `Control Panel → Terminal & SNMP → Enable SSH service` (port 22)
2. `Control Panel → User → Create` a user named `svc-claude`
   - Group: `users` only, NOT administrators
   - Shared folder permissions: **no access to anything yet**
   - Applications: allow DSM only
3. `Control Panel → User → svc-claude → Edit → Permissions` — later phases
   will tell you exactly which folders to grant.

Report to CC: SSH enabled yes/no, `svc-claude` created yes/no.

### 0b. CC, on the RPi
```bash
ssh-keygen -t ed25519 -f ~/.ssh/nas_svc -N "" -C "claude-code-to-nas"
ssh-copy-id -i ~/.ssh/nas_svc.pub svc-claude@192.168.109.45
ssh -i ~/.ssh/nas_svc svc-claude@192.168.109.45 "whoami; uname -a"
```
Add to `~/.ssh/config` on the RPi:
```
Host nas
    HostName 192.168.109.45
    User svc-claude
    IdentityFile ~/.ssh/nas_svc
```
Verify: `ssh nas "echo OK"` returns OK.

**STOP. Report and wait.**

---

# PHASE 1 — Full inventory (CC, read-only)

Collect and report as ONE table. Nothing is changed in this phase.

```bash
ssh nas "cat /etc/synoinfo.conf | grep -E '^upnpmodelname|^unique'"
ssh nas "cat /proc/meminfo | head -3; nproc; uname -m"
ssh nas "cat /etc/VERSION"
ssh nas "df -h | grep -E 'volume|/dev/md'"
ssh nas "sudo btrfs filesystem show 2>/dev/null || echo 'NOT_BTRFS_OR_NO_SUDO'"
ssh nas "cat /proc/mdstat"
ssh nas "ls /var/packages/"
ssh nas "sudo synosetkeyvalue --help >/dev/null 2>&1 && echo HAS_SUDO || echo NO_SUDO"
```

Report specifically:
| Item | Value |
|---|---|
| Model / CPU arch / cores | |
| RAM total | |
| DSM version | |
| Disk count + size each | |
| RAID type (from mdstat) | |
| **Filesystem: Btrfs or ext4** | |
| Volume size / used / free | |
| Installed packages | |
| Does `svc-claude` have sudo | |

**Filesystem is the critical one.** If it is ext4, snapshots are impossible
and the whole snapshot layer of this plan is dead — say so loudly, because
changing it later means wiping the volume.

**STOP. Report and wait.**

---

# PHASE 2 — Fix the four open issues

### 2a. Team Folders (USER, DSM UI — CC verifies)
User: `Synology Drive Admin Console → Team Folder` → Enable for every shared
folder that should appear in the mobile app (`documents`, `family`, `media`).

CC verifies from the API afterwards and reports which folders are enabled.

### 2b. The `work` folder upload problem (CC diagnoses)
```bash
ssh nas "ls -la /var/services/homes/salem/Drive/work/ 2>/dev/null || \
         ls -la /volume1/homes/salem/Drive/ 2>/dev/null"
ssh nas "df -h | tail -5"
ssh nas "sudo synouser --get salem 2>/dev/null | grep -i quota"
```
Check in order: (1) are the files actually on disk under a different path,
(2) is the volume or user quota full, (3) Drive server log:
```bash
ssh nas "sudo tail -50 /var/log/synologydrive*.log 2>/dev/null"
```
Report the actual cause — do not guess.

### 2c. Photos indexing (CC measures, then advise)
```bash
ssh nas "sudo synoindexd --status 2>/dev/null; ps aux | grep -iE 'synoindex|converter' | head"
```
Report whether conversion/indexing is still running and roughly how backed up
it is. If it is still catching up, the correct advice is patience, not tuning.

### 2d. Certificate — deferred to Phase 6.

**STOP. Report and wait.**

---

# PHASE 3 — Storage hygiene + snapshots (mixed)

Only if Phase 1 confirmed **Btrfs**.

USER, DSM UI:
1. `Storage Manager → Storage Pool → Schedule` → monthly Data Scrubbing
2. `Storage Manager → HDD/SSD → Health Info` → monthly extended S.M.A.R.T.
3. Install **Snapshot Replication** from Package Center
4. Snapshot schedules:

| Share | Frequency | Retention |
|---|---|---|
| `documents`, `vault`, `backup-masterai` | hourly | 24h · 14d · 8w |
| `photo`, `home` | daily | 30d · 12m |
| `family` | daily | 30d |
| `media` | **none** | — |

`media` gets no snapshots and no recycle bin — video files are huge and
replaceable. Photos are not.

5. Enable immutable snapshots if this DSM version offers it.

CC verifies afterwards:
```bash
ssh nas "sudo synoschedtask --get 2>/dev/null | head -40"
ssh nas "sudo btrfs subvolume list /volume1 | head -20"
```

**STOP. Report and wait.**

---

# PHASE 4 — Backups (the actual point of the NAS)

### 4a. USER: create shares
`backup-masterai` (svc-rpi write only) · `backup-pc` (admin only) ·
`vault` (**encrypted**, admin only). Grant `svc-claude` write on
`backup-masterai` only.

### 4b. CC: RPi → NAS nightly backup
Create `_tools/nas_backup.sh` on the RPi:
- Mount via CIFS, credentials in `/root/.nas_cred` mode 600, fstab uses
  `credentials=` — never an inline password.
- SQLite DBs via `sqlite3 <db> ".backup '<dest>'"`. **Never `cp` a live DB.**
- Code via `git bundle create master_ai.bundle --all`
- Config: `.env`, `_tools/`, HA `configuration.yaml`, systemd units
- `.env` and tokens → `vault` share, NOT `backup-masterai`
- Retention 14 daily + 8 weekly, prune older
- Log to the NAS, exit non-zero on failure
- systemd timer, 03:00 Kuwait time

### 4c. CC: move rotated logs off the SD card
Point logrotate's archive dir at the NAS. Keep only the active log locally.
Context: rotated logs once got committed to git (~570k lines) — see
`_tools/CLEANUP_COMMIT_1628f70.md`.

### 4d. RESTORE TEST — mandatory
```bash
mkdir -p /tmp/restore_test && cd /tmp/restore_test
git clone /mnt/nas-backup/rpi/<date>/master_ai.bundle restored
sqlite3 /mnt/nas-backup/rpi/<date>/<db>.sqlite "PRAGMA integrity_check;"
```
Must print `ok` and clone cleanly. Report both outputs verbatim.
A backup that was never restored is not a backup.

### 4e. USER: Active Backup agent on the PC → `backup-pc`, then build the
recovery USB immediately. Verify by browsing single files inside the image.

### 4f. USER: Hyper Backup → external USB or C2. RAID is not a backup.

**STOP. Report and wait.**

---

# PHASE 5 — Container Manager + monitoring

Only if Phase 1 shows the model supports it (Package Center lists it and
RAM ≥ 2 GB).

USER: install **Container Manager** from Package Center.

CC: deploy **Uptime Kuma** via docker compose on the NAS.

```
http://192.168.111.214:8059/health   TradingView Bridge   60s
http://192.168.109.123:9000/health   Master AI            60s
http://192.168.109.123:8123          Home Assistant       60s
https://ai.salem-home.com/health     Cloudflare tunnel    300s
192.168.108.1                        Router (ping)        300s
192.168.109.45                       NAS itself           300s
```

Notifications → the existing Master AI Telegram bot.

**Why this matters and why it goes on the NAS:** on 2026-08-12 the Bridge was
down for an unknown period and the only symptom was a broken dashboard page.
A monitor must live on a machine independent of what it watches — putting it
on the RPi means an RPi outage goes unreported.

**Do NOT move the TradingView Bridge to the NAS.** It needs Chrome CDP for
TradingView JWT handling and the NAS has no desktop Chrome session. It stays
on the PC; `BRIDGE_URL` in `.env` already makes its address swappable.

**STOP. Report and wait.**

---

# PHASE 6 — Valid certificate (optional, cosmetic)

DSM's built-in Let's Encrypt button uses HTTP-01 and needs port 80 open from
the internet. We are deliberately not opening ports, so use DNS-01 instead.

The user already owns `salem-home.com` on Cloudflare (used by the Master AI
tunnel), so:

1. Cloudflare API token scoped to **DNS:Edit on salem-home.com only**
2. Issue a cert for `nas.salem-home.com` via acme.sh or lego, DNS-01 challenge
3. Import into DSM: `Control Panel → Security → Certificate`
4. Assign it to DSM services and set as default
5. Add a **local DNS record** so `nas.salem-home.com` → `192.168.109.45`
   inside the house (avoids NAT hairpinning)
6. Schedule auto-renewal (certs last 90 days)

Note for the user: browsing by raw IP will ALWAYS show a warning regardless —
certificates bind to hostnames, not IPs. Access by hostname after this.

**STOP. Report and wait.**

---

# PHASE 7 — Master AI integration (CC + claude.ai)

- CC: add `/system/nas-status` returning `last_backup_at`, `size_bytes`,
  `free_space`, `ok`, `reason`. Business errors return **HTTP 200** with
  `{"error": ...}` — see the Cloudflare 5xx-masking rule in
  `_tools/OPERATIONAL_ACCESS_MATRIX.md`.
- CC: Telegram alert if no successful backup in 36 hours.
- claude.ai: NAS card on `system.html` — last backup, green/amber/red, free
  space.

# Execution order

```
0 access · 1 inventory · 2 fix issues · 3 storage+snapshots ·
4 backups+restore test · 5 containers+monitoring · 6 certificate ·
7 dashboard
```

Phases 0, 1, 4 are the ones that actually matter. 6 is cosmetic.
