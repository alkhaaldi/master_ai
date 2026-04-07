# Fix: Daily Indicators Missing in Dashboard
# Date: 2026-03-28
# Problem: 6 fields show null/none in daily tab
# Root cause: refresh_daily_snapshot reads from wrong JSON paths

---

## المشكلة بالتفصيل

`refresh_daily_snapshot()` في `stock_radar.py` يقرأ المؤشرات من أماكن غلط بالـ Bridge response:

| Field | الكود الحالي | الصحيح | الحالة |
|-------|-------------|--------|--------|
| support | `ind.get("support_1")` | `raw.get("support", [])[0]` | ❌ ALL NULL |
| resistance | `ind.get("resistance_1")` | `raw.get("resistance", [])[0]` | ❌ ALL NULL |
| macd_cross | `"bullish" if macd > sig` (position) | Compare with previous (already fixed but cross detection fails on first run) | ❌ ALL "none" |
| daily_ema_cross | Requires previous EMA | Same issue — needs 2 runs | ❌ ALL "none" |
| volume_spike | `1 if vol_ratio >= 3 else 0` | Correct logic but stored as 0 | ❌ ALL 0 (false) |
| rsi_divergence | `raw.get("signals",{}).get("rsi_divergence")` | Correct path but Bridge returns null for most | ⚠️ Mostly "none" |
| bb_squeeze | NOT stored in stock_radar_daily | Missing column entirely | ❌ NOT IN DB |

## Bridge API Response Structure:
```json
{
  "symbol": "KSE:CLEANING",
  "price": 135.0,
  "indicators": {
    "rsi_14": 68.2, "macd": 7.9, "macd_signal": 4.3,
    "ema_9": 127, "ema_20": 118, "ema_50": 114,
    "adx": 38.8, "stoch_k": 92.8, "atr_14": 6.5,
    "bb_squeeze": false, "bb_bandwidth": 54.4,
    "vol_ratio": 2.41,
    "support_1": null,      ← EMPTY in indicators!
    "resistance_1": null     ← EMPTY in indicators!
  },
  "support": [106, 108, 110, 117, 121, 126],    ← HERE (top-level array)
  "resistance": [153, 163, 172, 173, 192],       ← HERE (top-level array)
  "signals": {
    "rsi_divergence": "bearish",
    "macd_momentum": "decelerating_bullish",
    "ema_cross": {"type": "golden", "bars_ago": 9},
    "confluence": {"score": 100, "direction": "strong_bullish"}
  }
}
```

---

## الإصلاحات المطلوبة

### Fix 1: Support & Resistance — read from top-level arrays
**File:** `stock_radar.py` → `refresh_daily_snapshot()`

Find (~line 1207):
```python
support    = ind.get("support_1") or ind.get("pivot_low")
resistance = ind.get("resistance_1") or ind.get("pivot_high")
```

Replace with:
```python
# Support/Resistance are top-level arrays in Bridge response, not in indicators
sup_arr = raw.get("support", [])
res_arr = raw.get("resistance", [])
support    = sup_arr[0] if sup_arr else None
resistance = res_arr[0] if res_arr else None
```

### Fix 2: BB Squeeze — add column + store it
**File:** `stock_radar.py` → `init_radar_db()` and `refresh_daily_snapshot()`

In `init_radar_db()`, add ALTER TABLE (safe if exists):
```python
"ALTER TABLE stock_radar_daily ADD COLUMN bb_squeeze BOOLEAN DEFAULT 0",
"ALTER TABLE stock_radar_daily ADD COLUMN bb_bandwidth REAL",
```

In `refresh_daily_snapshot()`, read from indicators:
```python
bb_squeeze_val = ind.get("bb_squeeze") or False
bb_bandwidth_val = ind.get("bb_bandwidth")
```

Add to the INSERT statement columns and values.

### Fix 3: RSI Divergence — use signals dict
**File:** `stock_radar.py` → `refresh_daily_snapshot()`

Current code reads from `(raw.get("signals") or {}).get("rsi_divergence")` which is correct.
But check if it's storing correctly:

```python
rsi_div_val = (raw.get("signals") or {}).get("rsi_divergence")
# Make sure "none" string becomes None
if rsi_div_val == "none" or rsi_div_val == "":
    rsi_div_val = None
```

### Fix 4: Volume Spike threshold
Currently `1 if vol_ratio >= 3 else 0` — this is very aggressive. Lower to 2:
```python
volume_spike = 1 if vol_ratio >= 2 else 0
```

### Fix 5: Dashboard endpoint — expose bb_squeeze and full S/R
**File:** `dashboard_api.py` or wherever `/dashboard/radar` builds `radar_daily_context`

Make sure the endpoint returns:
- `support` (first level)
- `resistance` (first level)  
- `bb_squeeze`
- `bb_bandwidth`

Check the DB query and add any missing columns.

### Fix 6: Also fix check_symbol (30m) — same support/resistance issue
**File:** `stock_radar.py` → `check_symbol()` (~line 716)

Same fix:
```python
# OLD:
_sup = ind.get("support_1") or ind.get("pivot_low")
_res = ind.get("resistance_1") or ind.get("pivot_high")

# NEW:
sup_arr = raw.get("support", [])
res_arr = raw.get("resistance", [])
_sup = sup_arr[0] if sup_arr else None
_res = res_arr[0] if res_arr else None
```

---

## Testing

```bash
cd /home/pi/master_ai

# 1. After code changes, restart:
bash _tools/restart_master_ai.sh

# 2. Re-run daily refresh to populate new columns:
venv/bin/python3 -c "
from stock_radar import refresh_daily_snapshot
import json
r = refresh_daily_snapshot()
print(json.dumps(r, default=str))
"

# 3. Check DB has values now:
sqlite3 data/life.db "SELECT symbol, support, resistance, bb_squeeze, rsi_divergence, volume_spike FROM stock_radar_daily WHERE support IS NOT NULL LIMIT 5"

# 4. Check API:
KEY=$(cat ~/.master_ai_key)
curl -s -H "X-API-Key: $KEY" http://localhost:9000/dashboard/radar | python3 -c "
import sys,json
d=json.load(sys.stdin)
ctx=d.get('radar_daily_context',[])
if ctx:
    s=ctx[0]
    print(f'support={s.get(\"support\")} resistance={s.get(\"resistance\")} bb={s.get(\"bb_squeeze\")} rsi_div={s.get(\"rsi_divergence\")} spike={s.get(\"volume_spike\")}')
"
```

## Commit:
```bash
git add stock_radar.py dashboard_api.py
git commit -m "fix: daily indicators — S/R from top-level arrays, add bb_squeeze column, fix rsi_div/vol_spike"
bash _tools/restart_master_ai.sh
```

---

## HOW TO EXECUTE

Tell Claude Code:
```
اقرأ _tools/FIX_DAILY_INDICATORS_V2.md ونفذ:
Fix 1: Support/Resistance من top-level arrays
Fix 2: أضف bb_squeeze + bb_bandwidth columns
Fix 3: RSI Divergence — "none" → None
Fix 4: Volume spike threshold 3→2
Fix 5: Dashboard endpoint يرجع الأعمدة الجديدة
Fix 6: check_symbol نفس إصلاح S/R
ثم restart + daily refresh + اختبر
```
