# System Fixes Plan — 3 Issues
# Date: 2026-04-04
# Status: READY FOR EXECUTION
# Priority: Low-Medium

---

## Issue 1: news_boursa repeated "never refreshed" alerts

### Problem:
Telegram queue shows 4 duplicate alerts in 15 minutes:
```
#235 "⚠️ news_boursa غير متاح — never refreshed" 09:30
#236 same 09:34
#237 same 09:39
#238 same 09:44
```
The alert fires every ~5 min cycle but never deduplicates.

### Root Cause:
Likely in `news_engine.py` or wherever the health check runs.
The check sees news_boursa has never been refreshed and sends alert every cycle.

### Fix (Claude Code):
```python
# In the news health check (news_engine.py or server.py scheduler):
# Add dedup: only send "never refreshed" alert ONCE per day

# Option A: Use a simple flag
_news_alert_sent_today = set()

def check_news_health():
    for source in NEWS_SOURCES:
        if source.never_refreshed:
            key = f"news_{source.name}_{today()}"
            if key not in _news_alert_sent_today:
                send_telegram_alert(f"⚠️ {source.name} غير متاح")
                _news_alert_sent_today.add(key)
            # else: skip duplicate

# Option B: Check DB before sending
# Before sending alert, check telegram_queue:
#   SELECT COUNT(*) FROM telegram_queue 
#   WHERE message LIKE '%news_boursa%' 
#   AND created_at > datetime('now', '-6 hours')
# If count > 0, skip.
```

### Steps:
1. Find where news health alerts are sent (grep "news_boursa\|never refreshed")
2. Add dedup logic (Option A or B above)
3. Test: trigger health check twice — should only send once
4. git commit

**Files:** news_engine.py or server.py (wherever scheduler runs)

---

## Issue 2: daily_bars needs more history

### Problem:
`daily_bars` has only 384 rows (should be ~128 stocks × 20+ days = 2560+).
V2 Daily Trend Filter uses SMA 20 which needs 20 bars per stock.
Currently most stocks have insufficient data → trend = UNKNOWN → no buy signals.

### Root Cause:
`daily_bars` is populated by `refresh_daily_snapshot()` which runs during market hours
via Bridge. Since V2 was just deployed, only a few days of data exist.

### Fix (Claude Code):
```python
# Add a backfill function to populate daily_bars from Bridge historical data
# This should run ONCE to seed the DB, then daily refresh maintains it

async def backfill_daily_bars(days=60):
    """
    Pull 60 days of daily OHLCV for all 128 stocks from Bridge.
    Run once to seed daily_bars table.
    
    For each stock:
    1. GET /bars?symbol={sym}&exchange=KSE&interval=1D&bars=60
    2. Insert into daily_bars: symbol, date, open, high, low, close, volume
    3. Skip if already exists (upsert)
    """
    from bridge_client import BridgeClient
    client = BridgeClient()
    
    for symbol in ALL_SYMBOLS:  # or SCANNER_UNIVERSE
        try:
            bars = await client.get_bars(symbol, interval='1D', bars=60)
            if not bars:
                continue
            for bar in bars:
                # Upsert: INSERT OR REPLACE
                db.execute("""
                    INSERT OR REPLACE INTO daily_bars 
                    (symbol, date, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (symbol, bar['date'], bar['open'], bar['high'], 
                      bar['low'], bar['close'], bar['volume']))
            db.commit()
            logger.info(f"Backfilled {len(bars)} daily bars for {symbol}")
        except Exception as e:
            logger.warning(f"Failed to backfill {symbol}: {e}")
        await asyncio.sleep(0.5)  # Rate limit
```

### Steps:
1. Check if `backfill_daily_bars()` already exists
2. If not, add it to signal_engine.py or a new file
3. Add endpoint: `POST /api/backfill-daily` (API key protected)
4. Run it once when Bridge is online (Sunday market hours)
5. Verify: `SELECT COUNT(DISTINCT symbol), COUNT(*) FROM daily_bars`
6. git commit

### Trigger:
```bash
curl -X POST https://ai.salem-home.com/api/backfill-daily \
  -H "X-API-Key: $(cat ~/.master_ai_key)"
```

**Files:** signal_engine.py or new backfill_daily.py
**Requires:** Bridge online (PC running + market hours)

---

## Issue 3: systemd service inactive

### Problem:
Master AI runs via `uvicorn` directly (PID 1878013) but `systemctl` shows inactive.
If the process crashes, it won't auto-restart.

### Current state:
```
pi 1878013 /home/pi/master_ai/venv/bin/python3 .../uvicorn server:app --host 0.0.0.0 --port 9000
```

### Fix (Claude Code):
```bash
# Check if service file exists:
cat /etc/systemd/system/master_ai.service

# If it exists but is inactive, fix and enable:
sudo systemctl daemon-reload
sudo systemctl enable master_ai
sudo systemctl start master_ai

# If it doesn't exist, create it:
sudo tee /etc/systemd/system/master_ai.service << 'EOF'
[Unit]
Description=Master AI Trading Platform
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/master_ai
Environment=PATH=/home/pi/master_ai/venv/bin:/usr/bin:/bin
EnvironmentFile=/home/pi/master_ai/.env
ExecStart=/home/pi/master_ai/venv/bin/uvicorn server:app --host 0.0.0.0 --port 9000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable master_ai
sudo systemctl start master_ai
```

### Steps:
1. Check if `/etc/systemd/system/master_ai.service` exists
2. If exists: `sudo systemctl enable master_ai && sudo systemctl restart master_ai`
3. If not: create service file (above)
4. Kill existing uvicorn process
5. Start via systemd: `sudo systemctl start master_ai`
6. Verify: `systemctl status master_ai` → active (running)

### After fix:
- Auto-restart on crash
- Logs via `journalctl -u master_ai`
- `ctl.sh restart` should use `sudo systemctl restart master_ai`

**Files:** /etc/systemd/system/master_ai.service, _tools/restart_master_ai.sh

---

## Execution Order

```
Issue 3 → FIRST (systemd — prevents data loss on crash)
Issue 2 → SECOND (daily_bars backfill — needs Bridge online Sunday)
Issue 1 → THIRD (news dedup — cosmetic fix)
```

## Claude Code Command:

> اقرأ `_tools/SYSTEM_FIXES_PLAN.md` وابدأ بـ Issue 3 (systemd service) — تأكد إن الـ service file موجود ومفعّل. بعدين Issue 1 (news dedup). Issue 2 ينتظر لما Bridge يشتغل يوم الأحد.
