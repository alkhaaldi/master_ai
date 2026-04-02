# Dashboard Updates Plan — Post Tier 1+2 Implementation
# Date: 2026-04-03
# Status: ✅ COMPLETE

---

## Workaround for DC read_file Bug on HTML files

DC read_file has a bug with some files on Samba UNC paths (EPERM realpath).
DC write_file also has EPERM on UNC paths (discovered during this work).

### Permanent Workflow:
- READ: `ssh -T pi@192.168.109.123 cat /home/pi/master_ai/www/trading/FILE.html > C:\Users\MS1\Temp\FILE_read.html`
  then `DC:read_file C:\Users\MS1\Temp\FILE_read.html`
- WRITE: Write to `C:\Users\MS1\Temp\FILE_new.html` then `scp` to RPi
  `scp C:\Users\MS1\Temp\FILE_new.html pi@192.168.109.123:/home/pi/master_ai/www/trading/FILE.html`

### After writing, fix ownership:
`ssh -T pi@192.168.109.123 sudo chown pi:pi /home/pi/master_ai/www/trading/FILE.html`

---

## Update 1: system.html — Add Live Tasks Panel ✅ DONE

### Changes Made:
1. **NEW section: ⚡ المهام الجارية** — between صحة الخدمات and KAIROS
   - Fetches from `/api/tasks` every 10s
   - Shows running tasks with pulse animation, recent completed at 55% opacity
   - Graceful 404 handling ("غير متاح") until endpoint is built
2. **BUG FIX: Service Health dots were ALL RED**
   - Old code used `v.is_available` but API returns `v.status === "up"/"down"`
   - Fixed to: `const isUp = v.status==='up' || v.is_available===true` (backward-compatible)
3. **Circuit Breaker enhancement** in loadHealth
   - Checks both `v.circuit_breaker` and `v.details` for CB state
   - Shows "circuit open (N failures, cooldown Xs)" in amber
4. **New CSS**: `.task-running` pulse animation, `.cb-info` styling
5. **New helper**: `fmtDur(ms)` for duration formatting

### File: www/trading/system.html (257 → 317 lines)

---

## Update 2: home.html — Add System Health Bar ✅ DONE

### Changes Made:
1. **NEW: Health Pulse Bar** — after Hero, before Degraded Banner
   - Shows: Bridge 🟢/🔴 | HA 🟢/🔴 | Telegram 🟢/🔴 | News 🟢/🔴 | Tasks: idle/N running
   - Fetches from `/api/service-health` + `/api/tasks` every 30s
   - Uses `v.status` (same fix as system.html)
2. **New CSS**: `.health-pulse`, `.hp-sep`, `.hp-dot` classes
3. All existing sections preserved unchanged

### File: www/trading/home.html (440 → 470 lines)

---

## All Items Complete:
- ✅ `/api/tasks` endpoint — built by Claude Code, returns 200 with running/recent/stats
- ✅ Circuit Breaker display — frontend reads from `v.details.state` and `v.details.circuit_open`
  Currently all circuits are closed (normal). Will display amber when a circuit opens.

## Files on disk:
- C:\Users\MS1\Temp\system_new.html (deployed)
- C:\Users\MS1\Temp\home_new.html (deployed)
- C:\Users\MS1\Temp\system_read.html (old backup)
- C:\Users\MS1\Temp\home_read.html (old backup)
