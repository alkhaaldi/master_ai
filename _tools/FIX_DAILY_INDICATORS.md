# TASK: Fix Daily Snapshot Indicators (StochK, ADX, RSI Divergence, ATR)

## PROBLEM
The daily snapshot (`refresh_daily_snapshot()` in `stock_radar.py`) does NOT compute:
- StochK (Stochastic %K)
- ADX (Average Directional Index)  
- RSI Divergence
- ATR (Average True Range)

These are available in the 30m live data but missing from the 1D daily analysis.

Additionally:
1. The DB table `stock_radar_daily` is missing columns: `stoch_k`, `adx`, `rsi_divergence`, `atr`
2. The `refresh_daily_snapshot()` function uses `tvDatafeed` library which may not be installed — it should use Bridge API instead
3. The `/dashboard/radar` endpoint in `dashboard_api.py` needs to return these new fields
4. `www/trading/signals.html` needs updated mapping for the daily tab

## WHAT WAS ALREADY DONE (verify before re-doing)
- `tv_analysis.py` — 3 new functions were added at the bottom: `compute_stoch_k`, `compute_adx`, `detect_rsi_divergence`. VERIFY they exist and are correct.
- `stock_radar.py` — ALTER TABLE statements were added for the 4 columns. VERIFY.
- `stock_radar.py` — compute calls were added in `refresh_daily_snapshot()`. VERIFY.
- `stock_radar.py` — INSERT statement was updated with 4 new columns. VERIFY.
- `dashboard_api.py` — `stoch_k`, `adx`, `rsi_divergence`, `atr` fields added to daily_clean dict. VERIFY.
- `www/trading/signals.html` — mapping updated. VERIFY.

## STEP-BY-STEP FIX

### Step 1: Verify tv_analysis.py has the 3 new functions
Check bottom of file for: `compute_stoch_k`, `compute_adx`, `detect_rsi_divergence`
If missing, add them.

### Step 2: Fix DB columns
Run directly:
```python
import sqlite3
conn = sqlite3.connect('data/master_ai.db')
for col in ['stoch_k REAL', 'adx REAL', 'rsi_divergence TEXT', 'atr REAL']:
    try:
        conn.execute(f'ALTER TABLE stock_radar_daily ADD COLUMN {col}')
        print(f'Added: {col}')
    except: 
        print(f'Already exists: {col}')
conn.commit()
conn.close()
```

### Step 3: Verify stock_radar.py changes
In `refresh_daily_snapshot()`:
- After `volume_spike = ...` line, there should be imports and compute calls for stoch_k_val, adx_val, rsi_div_val, atr_val
- The INSERT statement should include these 4 columns
- The VALUES should have 4 extra `?` placeholders
- The params tuple should include `stoch_k_val, adx_val, rsi_div_val, atr_val`

### Step 4: Verify dashboard_api.py
In the `daily_clean.append({...})` block (around line 555), verify these fields exist:
```python
"stoch_k": d.get("stoch_k"),
"adx": d.get("adx"),
"rsi_divergence": d.get("rsi_divergence"),
"atr": d.get("atr"),
```

### Step 5: Fix tvDatafeed issue
The `refresh_daily_snapshot()` uses `from tvDatafeed import Interval` and `tv.get_hist()`.
If tvDatafeed is not installed, install it:
```bash
pip install tvDatafeed --break-system-packages
```
OR check if it's in the HA venv:
```bash
/srv/homeassistant/bin/pip install tvDatafeed
```

### Step 6: Run daily refresh test
```bash
cd /home/pi/master_ai
python3 -c "
from stock_radar import refresh_daily_snapshot
import json
r = refresh_daily_snapshot()
print(json.dumps(r, default=str))
"
```

### Step 7: Verify data in DB
```bash
python3 -c "
import sqlite3, json
c = sqlite3.connect('data/master_ai.db')
c.row_factory = sqlite3.Row
rows = c.execute('SELECT symbol, stoch_k, adx, rsi_divergence, atr FROM stock_radar_daily LIMIT 5').fetchall()
for r in rows:
    print(json.dumps(dict(r)))
"
```

### Step 8: Verify signals.html mapping
In fetchData(), the dailySignals mapping should include:
```javascript
adx: w.adx || null,
stoch_k: w.stoch_k || null,
atr_14: w.atr || null,
rsi_divergence: w.rsi_divergence || null,
```

### Step 9: Quick check + smoke test
```bash
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
```

### Step 10: Git commit + restart
```bash
git add tv_analysis.py stock_radar.py dashboard_api.py www/trading/signals.html
git commit -m "feat: add StochK, ADX, RSI Divergence, ATR to daily snapshot + fix tvDatafeed"
bash _tools/restart_master_ai.sh
```

### Step 11: Trigger fresh daily snapshot
After restart, trigger a fresh refresh:
```bash
python3 -c "from stock_radar import refresh_daily_snapshot; print(refresh_daily_snapshot())"
```

### Step 12: Final verify
Check /dashboard/radar returns the new fields:
```bash
curl -s -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000/dashboard/radar | python3 -m json.tool | grep -E "stoch_k|adx|rsi_div|atr"
```

## IMPORTANT NOTES
- Use `_tools/patchers/apply_text_patch.py` for Python file edits if available
- Run `_tools/quick_check.py` after every Python file change
- The daily snapshot runs automatically at market open (Sun-Thu 9:15 KWT)
- Bridge API must be running on PC (192.168.111.158:8059) for live data
- tvDatafeed is needed for daily snapshot (it fetches 1D candles from TradingView directly)
