# TG Noise Reduction Plan
# Date: 2026-04-18
# Executor: Claude Code
# Goal: Reduce Telegram spam from ~100+ daily messages to essential alerts only

## Problem Summary
Server.log analysis (Apr 13-18) shows:
- **Confluence scan**: sends same 3 signals every 30min during market hours = ~30 msgs/day
- **Entity health check**: sends "5 dead, 53 new" 3x/day (same msg repeated)
- **TG send error (empty)**: network timeouts flood log = ~20-30 errors/day
- **Stats saved log spam**: 48 entries/day ("Stats saved: total=0")
- **Brain changes log spam**: 161 entries/day
- **Analysis scheduler timeouts**: 20-40% of 128 stocks fail daily

## Changes Required (server.py unless noted)

---

### FIX 1: Confluence Deduplication (HIGHEST IMPACT)
**File:** server.py, `confluence_scan_loop()` (~line 8963)
**Problem:** Same actionable signals sent every 30min = massive spam
**Fix:** Add daily dedup set — don't re-alert same symbol+signal_type same day

```python
# BEFORE (line ~8963):
async def confluence_scan_loop():
    """Run confluence scan every 30 min during KSE market hours..."""
    logger.info("Confluence scan loop started")
    while True:

# AFTER:
async def confluence_scan_loop():
    """Run confluence scan every 30 min during KSE market hours..."""
    logger.info("Confluence scan loop started")
    _sent_today = {}  # {date_str: set(symbol|signal_type)}
    while True:
```

Then inside the loop, before sending:
```python
# BEFORE:
if actionable:
    _chat = ADMIN_TELEGRAM_ID or "669769765"
    for sig in actionable[:3]:
        text, kb = confluence_build_tg_alert(sig)
        await tg_send(int(_chat), text, reply_markup=kb)
    logger.info(f"Confluence: {len(actionable)} actionable signals sent to TG")

# AFTER:
if actionable:
    _chat = ADMIN_TELEGRAM_ID or "669769765"
    _today = datetime.now().strftime("%Y-%m-%d")
    if _today not in _sent_today:
        _sent_today.clear()
        _sent_today[_today] = set()
    _new_sigs = []
    for sig in actionable:
        _key = f"{sig.get('symbol','')}|{sig.get('signal','')}"
        if _key not in _sent_today[_today]:
            _sent_today[_today].add(_key)
            _new_sigs.append(sig)
    if _new_sigs:
        for sig in _new_sigs[:3]:
            text, kb = confluence_build_tg_alert(sig)
            await tg_send(int(_chat), text, reply_markup=kb)
        logger.info(f"Confluence: {len(_new_sigs)} NEW signals sent to TG (filtered from {len(actionable)})")
    else:
        logger.debug(f"Confluence: {len(actionable)} signals already sent today, skipped")
```

**Expected impact:** ~30 msgs/day → ~3-5 msgs/day (first alert only)

---

### FIX 2: Disable Entity Health Alerts (QUICK WIN)
**File:** server.py, `entity_health_check_loop()` (~line 8559)
**Problem:** Sends "5 dead, 53 new" 3x/day — entity_map is outdated after recent changes
**Fix:** Disable the TG alert part, keep the log. Add feature flag gate.

```python
# BEFORE (inside entity_health_check_loop):
if alerts:
    _msg = "🔍 فحص صحة الأجهزة:" + chr(10) + chr(10).join(alerts)
    try:
        _tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        ...

# AFTER:
if alerts:
    _msg = "🔍 فحص صحة الأجهزة:" + chr(10) + chr(10).join(alerts)
    logger.info(f"Entity health: {dead} dead, {len(_new_missing)} new (TG alert disabled)")
    # TG alert disabled — entity_map needs update first
    # Uncomment when entity_map is refreshed:
    # try:
    #     _tg_url = ...
```

**Expected impact:** -3 msgs/day, stops false alerts

---

### FIX 3: Suppress Empty TG Send Error Logs
**File:** server.py, `tg_send()` (~line 5198)
**Problem:** `logger.error(f"TG send error: {e}")` logs empty string when exception has no message
**Fix:** Add more detail to the error log

```python
# BEFORE:
except Exception as e:
    _cb_tg.record_failure()
    logger.error(f"TG send error: {e}")

# AFTER:
except Exception as e:
    _cb_tg.record_failure()
    logger.error(f"TG send error: {type(e).__name__}: {e or 'no details'}")
```

**Expected impact:** Better debugging, same count but useful info

---

### FIX 4: Reduce Stats Saved Log Spam
**File:** server.py, `stats_save_loop()` (~line 8481)
**Problem:** Logs "Stats saved: total=0" every 30min = 48/day of useless logs
**Fix:** Only log if total > 0

```python
# BEFORE:
async def stats_save_loop():
    while True:
        await asyncio.sleep(1800)
        _save_router_stats()
        logger.info(f"Stats saved: total={_router_stats.get('total', 0)}")

# AFTER:
async def stats_save_loop():
    while True:
        await asyncio.sleep(1800)
        _save_router_stats()
        _t = _router_stats.get('total', 0)
        if _t > 0:
            logger.info(f"Stats saved: total={_t}")
        else:
            logger.debug(f"Stats saved: total=0")
```

**Expected impact:** -48 log lines/day (still saves, just quieter)

---

### FIX 5: Reduce Brain Changes Log Noise
**File:** server.py, `brain_snapshot_loop()` (~line 8554)
**Problem:** Logs "Brain: X changes" every 5min = 161/day
**Fix:** Only log if changes > 5 (significant), otherwise debug

```python
# BEFORE:
if result.get("changes", 0) > 0:
    logger.info(f"Brain: {result['changes']} changes")

# AFTER:
_changes = result.get("changes", 0)
if _changes >= 5:
    logger.info(f"Brain: {_changes} changes")
elif _changes > 0:
    logger.debug(f"Brain: {_changes} changes")
```

**Expected impact:** -150 log lines/day

---

### FIX 6: Nightly Summary — Suppress Extra Brain Digest TG
**File:** server.py, inside `nightly_summary_scheduler()` (~line 8818)
**Problem:** Brain digest is sent as SEPARATE TG message after nightly summary
**Fix:** Merge brain digest INTO the nightly summary message (one msg instead of two)

```python
# BEFORE (two separate tg_send calls):
await tg_send(_chat, _msg)  # nightly summary
...
if BRAIN_OK:
    ...
    await tg_send(_chat, chr(10).join(_bd))  # brain digest = second message

# AFTER: append brain digest to _msg before sending:
if BRAIN_OK:
    try:
        _bs = get_daily_summary()
        if _bs.get("total", 0) > 0:
            _bd = ["\n\n🧠 *ملخص البرين:*"]
            _bd.append(f"  📊 {_bs['total']} تغيير")
            if _bs.get("by_domain"):
                _dom_ar = {"light":"أضواء","switch":"مفاتيح","climate":"مكيفات","cover":"ستائر","fan":"شفاطات/منقيات","media_player":"سماعات"}
                _bd.append("  " + " | ".join(f"{_dom_ar.get(d,d)}:{c}" for d,c in _bs["by_domain"].items()))
            if _bs.get("top"):
                _bd.append("  🏆 أكثر: " + ", ".join(f"{e.split('.')[-1].replace('_',' ')}({c})" for e,c in _bs["top"][:3]))
            _msg += chr(10).join(_bd)
            # Auto-cleanup: keep only 30 days
            _cleaned = cleanup_old_data(30)
            if _cleaned > 0:
                logger.info(f"Brain cleanup: deleted {_cleaned} old records")
    except Exception as e:
        logger.error(f"Brain digest: {e}")

await tg_send(_chat, _msg)  # ONE combined message
# REMOVE the separate brain digest tg_send below
```

**Expected impact:** -1 TG msg per night, cleaner summary

---

### FIX 7: Weather Alert — Better Error Logging
**File:** server.py, `weather_alert_loop()` (~line 8617)
**Problem:** "Weather alert error:" with no details
**Fix:** Same pattern as FIX 3

```python
# BEFORE:
except Exception as e:
    logger.error(f"Weather alert error: {e}")

# AFTER:
except Exception as e:
    logger.error(f"Weather alert error: {type(e).__name__}: {e or 'no details'}")
```

---

### FIX 8: Watchdog Cron Cleanup (OPTIONAL)
**Note from memory:** `watchdog_tg.sh` cron runs every minute trying to start disabled `master-ai-telegram`
**Fix:** Remove from crontab

```bash
# On RPi, check:
crontab -l | grep watchdog
# If found, remove it:
crontab -l | grep -v watchdog_tg | crontab -
```

---

## Execution Order
1. FIX 1 (Confluence dedup) — biggest TG spam reduction
2. FIX 2 (Entity health disable) — quick win
3. FIX 3 + FIX 7 (Error logging) — better debugging
4. FIX 4 + FIX 5 (Log noise) — cleaner logs
5. FIX 6 (Nightly merge) — minor cleanup
6. FIX 8 (Watchdog cron) — optional cleanup

## After Applying
```bash
cd ~/master_ai
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
git add -A && git commit -m "TG noise reduction: confluence dedup, entity health disable, better error logs"
bash _tools/restart_master_ai.sh
```

## Expected Total Impact
- TG messages: ~100+/day → ~15-20/day
- Log noise: ~200+ lines/day removed
- False alerts: eliminated (entity health)
- Duplicate signals: eliminated (confluence)
