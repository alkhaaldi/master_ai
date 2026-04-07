# Remove Stale HTML Duplicate: config/www/trading/
# Status: READY FOR EXECUTION
# Executor: Claude Code
# Date: 2026-04-02

---

## Problem
Two copies of dashboard HTML exist:
- `share/master_ai/www/trading/` — LIVE (served by FastAPI) ✅
- `config/www/trading/` — STALE DUPLICATE (not used by anything) ❌

The YAML dashboard uses `https://ai.salem-home.com/trading/*` URLs (FastAPI),
NOT `/local/trading/*` (HA www). So config/www/trading/ is dead weight that
causes confusion when editing HTML files.

## Verification before delete

```bash
# Confirm YAML doesn't reference /local/trading/
grep -r "local/trading" /var/lib/homeassistant/config/master_ai_dashboard.yaml
# Expected: no output

# Confirm no automation uses /local/trading/
grep -r "local/trading" /var/lib/homeassistant/config/automations.yaml
# Expected: no output
```

## Commands

```bash
# Remove the stale duplicate
rm -rf /var/lib/homeassistant/config/www/trading/

# Remove the backup we made earlier today
rm -rf /var/lib/homeassistant/config/www/trading.bak_sync_20260402/

# Verify it's gone
ls /var/lib/homeassistant/config/www/
# Expected: adhan_makkah.mp3, alexa_tts, community, floorplan, images, tapo_control
# NO trading/ or trading.bak_sync_20260402/

# Verify live pages still work
curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/trading/home
# Expected: 200
```

## What stays
- `share/master_ai/www/trading/` — the ONLY copy, served by FastAPI ✅
- `config/www/adhan_makkah.mp3` — used by HA adhan automation ✅
- `config/www/images/`, `config/www/community/` etc — used by HA ✅
