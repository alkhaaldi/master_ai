# Sync HTML Files: Eliminate Duplicate Dashboard Path
# Status: READY FOR EXECUTION
# Executor: Claude Code
# Date: 2026-04-02
# Risk: LOW — config/www/trading/ is NOT served, just a stale copy

---

## Problem

Two copies of dashboard HTML files exist:
1. `share/master_ai/www/trading/` — **LIVE** (served by FastAPI)
2. `config/www/trading/` — **STALE** (HA local www, not served)

The config copy has outdated files that will confuse future edits.
Worst case: someone edits config/www/ thinking it's the live version.

## Solution

Overwrite config/www/trading/ with the live files from share/master_ai/www/trading/.

## Command

```bash
cd /home/pi

# Backup config copy first
cp -r /var/lib/homeassistant/config/www/trading /var/lib/homeassistant/config/www/trading.bak_sync_$(date +%Y%m%d)

# Sync: copy live → config (overwrite)
cp /var/lib/homeassistant/share/master_ai/www/trading/*.html /var/lib/homeassistant/config/www/trading/
cp /var/lib/homeassistant/share/master_ai/www/trading/*.css /var/lib/homeassistant/config/www/trading/
cp /var/lib/homeassistant/share/master_ai/www/trading/*.js /var/lib/homeassistant/config/www/trading/

# Verify
echo "=== Line count comparison ==="
for f in home radar positions journal news system email home-control; do
  a=$(wc -l < /var/lib/homeassistant/share/master_ai/www/trading/$f.html)
  b=$(wc -l < /var/lib/homeassistant/config/www/trading/$f.html)
  if [ "$a" = "$b" ]; then
    echo "✅ $f.html: $a lines (match)"
  else
    echo "❌ $f.html: live=$a config=$b (MISMATCH)"
  fi
done
```

## Expected Output
All files should show "match" after sync.

## Note
This is a one-time sync. The real fix is documenting that
**only share/master_ai/www/trading/ is the live path**.
config/www/trading/ exists for legacy reasons only.
