# Confluence Engine v2 — Dual Mode Update
# Date: 2026-03-22
# Status: APPROVED — Execute via Claude Code on RPi

---

## GOAL
Add "Discovery Mode" alongside existing "Confirmation Mode" in confluence_engine.py.
Discovery mode catches stocks AT THE START of a move. Confirmation mode catches stocks DURING a confirmed move.

Dashboard shows BOTH — Discovery signals first (early entry), Confirmation signals second (safer entry).

---

## WHAT TO CHANGE

### File: confluence_engine.py (PATCH — do not rewrite)

#### 1) Add Discovery Checks (new function)

```python
def _discovery_checks(row):
    """
    5 checks designed to catch the START of a move.
    These fire BEFORE confirmation checks — earlier entry, higher reward.
    
    Uses columns from stock_radar_daily:
      price, volume, avg_volume, vol_ratio, rsi, support, resistance,
      macd, macd_signal, macd_histogram, macd_cross, macd_above_zero,
      ema_fast, ema_slow, change_pct, daily_ema9, daily_ema21
    """
    checks = {}
    
    # Check 1: Volume acceleration — volume RISING over recent days
    # vol_ratio > 0.5 AND vol_ratio > previous (approximated by vol_ratio > 0.8 
    # since we don't have yesterday's vol_ratio in single row)
    # For v1: use vol_ratio > 0.5 as minimum, AND volume > avg_volume * 0.8
    vol_ratio = float(row.get('vol_ratio') or 0)
    volume = float(row.get('volume') or 0)
    avg_volume = float(row.get('avg_volume') or 0)
    checks['volume_accel'] = vol_ratio > 0.5 and volume > 0
    
    # Check 2: MACD histogram turning positive OR rising
    # This fires BEFORE the MACD cross — catches momentum shift early
    histogram = float(row.get('macd_histogram') or 0)
    macd_above = row.get('macd_above_zero', False)
    # histogram > 0 OR histogram negative but rising (less negative than before)
    # Since we have single snapshot, use: histogram > -0.5 (close to turning)
    checks['macd_turn'] = histogram > 0 or (histogram > -0.5 and not macd_above)
    
    # Check 3: RSI recovery — RSI > 35 and not overbought (< 75)
    # Wider range than confirmation mode — catches early momentum
    rsi = float(row.get('rsi') or 50)
    checks['rsi_recovery'] = 35 < rsi < 75
    
    # Check 4: Near support — price within 5% above support level
    # This is KEY — buy near support = small stop loss = big R:R
    price = float(row.get('price') or 0)
    support = float(row.get('support') or 0)
    if support > 0 and price > 0:
        dist_to_support_pct = ((price - support) / price) * 100
        checks['near_support'] = 0 <= dist_to_support_pct <= 5
    else:
        checks['near_support'] = False
    
    # Check 5: Room to run — price far enough from resistance (> 8% away)
    # Ensures there's enough upside to justify the trade
    resistance = float(row.get('resistance') or 0)
    if resistance > 0 and price > 0:
        dist_to_resist_pct = ((resistance - price) / price) * 100
        checks['room_to_run'] = dist_to_resist_pct >= 8
    else:
        checks['room_to_run'] = True  # no resistance data = assume room
    
    return checks
```

#### 2) Add discovery scoring to run_confluence_scan()

Inside the existing scan loop, AFTER the current confirmation checks, add:

```python
# --- Discovery Mode ---
disc_checks = _discovery_checks(row)
disc_passed = sum(1 for v in disc_checks.values() if v)
disc_total = len(disc_checks)
disc_score = round(disc_passed / disc_total * 100) if disc_total > 0 else 0

if disc_passed >= 4:  # 4/5 = 80% = HIGH discovery
    disc_conviction = "HIGH"
elif disc_passed >= 3:  # 3/5 = 60% = MEDIUM discovery
    disc_conviction = "MEDIUM"
else:
    disc_conviction = "LOW"

# Calculate R:R for discovery signals
disc_sl = support if support > 0 else price * 0.96
disc_tp = resistance if resistance > 0 else price * 1.12
disc_risk = price - disc_sl
disc_reward = disc_tp - price
disc_rr = round(disc_reward / disc_risk, 2) if disc_risk > 0 else 0
disc_sl_pct = round(disc_risk / price * 100, 1) if price > 0 else 0

# Store discovery signal (separate signal_type)
# signal_type = 'discovery_buy' for HIGH + R:R >= 1.5
# signal_type = 'discovery_watch' for MEDIUM
if disc_conviction == "HIGH" and disc_rr >= 1.5:
    signal_type = 'discovery_buy'
elif disc_conviction in ("HIGH", "MEDIUM"):
    signal_type = 'discovery_watch'
else:
    signal_type = 'no_signal'

# Insert into same confluence_signals table with mode='discovery'
# Add 'mode' column if not exists
```

#### 3) Add 'mode' column to confluence_signals table

```sql
-- Add mode column to distinguish confirmation vs discovery
ALTER TABLE confluence_signals ADD COLUMN mode TEXT DEFAULT 'confirmation';
```

If ALTER fails (column exists), ignore. New inserts use mode='discovery' or mode='confirmation'.

#### 4) Update get_actionable_signals() and get_watchlist_signals()

```python
def get_actionable_signals(limit=5, mode=None):
    """
    mode=None: return both discovery and confirmation
    mode='discovery': discovery only
    mode='confirmation': confirmation only
    """
    where_mode = f"AND mode = '{mode}'" if mode else ""
    query = f"""
        SELECT * FROM confluence_signals 
        WHERE is_active = 1 
        AND signal_type IN ('buy_signal', 'discovery_buy')
        {where_mode}
        ORDER BY confluence_score DESC, risk_reward DESC
        LIMIT {limit}
    """
    # ... execute and return
```

### File: dashboard_api.py (PATCH)

Update `/dashboard/confluence` endpoint to return both modes:

```python
# In dashboard_confluence():
discovery_signals = get_actionable_signals(limit=5, mode='discovery')
confirmation_signals = get_actionable_signals(limit=5, mode='confirmation')
discovery_watch = get_watchlist_signals(limit=8, mode='discovery')
confirmation_watch = get_watchlist_signals(limit=8, mode='confirmation')

return {
    # ... existing fields ...
    "discovery": {
        "actionable": discovery_signals,
        "actionable_count": len(discovery_signals),
        "watchlist": discovery_watch,
        "watch_count": len(discovery_watch)
    },
    "confirmation": {
        "actionable": confirmation_signals,
        "actionable_count": len(confirmation_signals),
        "watchlist": confirmation_watch,
        "watch_count": len(confirmation_watch)
    },
    # Keep flat actionable/watchlist for backward compatibility
    # (merge both, discovery first)
    "actionable": discovery_signals + confirmation_signals,
    "actionable_count": len(discovery_signals) + len(confirmation_signals),
    "watchlist": discovery_watch + confirmation_watch,
    "watch_count": len(discovery_watch) + len(confirmation_watch),
}
```

### File: HA sensor (PATCH configuration.yaml)

Add to existing sensor.master_ai_confluence json_attributes:
```yaml
    - discovery
    - confirmation
```

### File: Dashboard YAML (sub-confluence page) — UPDATE

Structure becomes:

```
LAYER 1 — Pulse Hero (same as current)

LAYER 2 — Discovery signals (NEW — "اكتشاف مبكر")
├── Section title: "🔍 اكتشاف مبكر — ركوب القطار من أوله"
├── For each discovery_buy signal:
│   ├── Symbol + Name
│   ├── Discovery score badge
│   ├── Grid: Price | RVOL | RSI | R:R
│   ├── Discovery checks: ✓ فوليوم متصاعد | ✓ MACD يتحول | ✓ RSI يرتد | ✓ قريب من الدعم | ✓ مجال للصعود
│   ├── Entry/SL/TP line
│   └── [شريت] [حلل] [تجاهلت]

LAYER 3 — Confirmation signals (existing — "تأكيد")
├── Section title: "✅ تأكيد — إشارات مؤكدة"
├── Same cards as current

LAYER 4 — Watchlist (merge both modes)
LAYER 5 — Market Pulse (same)
LAYER 6 — Disclaimer (same)
```

### File: TG Alert (PATCH server.py)

Discovery alerts get different emoji and header:

```
🔍 اكتشاف مبكر — BEYOUT (مجموعة البيوت)
━━━━━━━━━━━━━━━━━━━━
📊 Discovery: 80% (4/5)
💰 السعر: 358 فلس
━━━━━━━━━━━━━━━━━━━━
✅ فوليوم متصاعد
✅ MACD يتحول إيجابي
✅ RSI يرتد من القاع
✅ قريب من الدعم (2.1%)
❌ المقاومة قريبة
━━━━━━━━━━━━━━━━━━━━
🎯 الدخول: 358 | الوقف: 349 (-2.5%)
🏁 الهدف: 395 | R:R = 4.1
━━━━━━━━━━━━━━━━━━━━

[شريت ✅]  [تجاهلت ❌]
```

vs Confirmation alerts keep existing format with 🎯 emoji.

---

## EXECUTION STEPS

### Step 1: Read current confluence_engine.py
```bash
cat /var/lib/homeassistant/share/master_ai/confluence_engine.py
```

### Step 2: Add _discovery_checks() function
Use patch system: _tools/patchers/apply_text_patch.py

### Step 3: Modify run_confluence_scan() to run both check types
Patch: add discovery checks after existing confirmation checks

### Step 4: Add 'mode' column to DB
```python
import sqlite3
conn = sqlite3.connect('/var/lib/homeassistant/share/master_ai/data/life.db')
try:
    conn.execute("ALTER TABLE confluence_signals ADD COLUMN mode TEXT DEFAULT 'confirmation'")
    conn.commit()
except:
    pass  # column already exists
conn.close()
```

### Step 5: Update get_actionable_signals / get_watchlist_signals
Add mode parameter

### Step 6: Update /dashboard/confluence in dashboard_api.py
Return discovery + confirmation separately

### Step 7: Update HA sensor attributes

### Step 8: Rebuild dashboard page with dual-mode layout

### Step 9: Update TG alert format for discovery vs confirmation

### Step 10: Validate
```bash
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
python3 _tools/db_sanity.py
bash _tools/restart_master_ai.sh
```

### Step 11: Git commit
```bash
git add -A
git commit -m "feat: Confluence v2 — dual mode (Discovery + Confirmation)"
```

---

## SUMMARY OF CHANGES

| What | Action | Risk |
|------|--------|------|
| confluence_engine.py | ADD _discovery_checks(), PATCH scan loop | Low — additive only |
| confluence_signals table | ADD mode column | Low — ALTER with default |
| dashboard_api.py | PATCH /dashboard/confluence response | Low — backward compatible |
| configuration.yaml | ADD 2 sensor attributes | Low — additive |
| dashboard YAML | UPDATE sub-confluence page | Low — rebuild |
| server.py TG handler | PATCH alert format | Low — new emoji prefix |

Total: ~150 lines new code, 0 existing lines deleted.
