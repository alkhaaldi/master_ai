# Trading Decision Engine V2 — Entry Timing + S/R + Trade Plan + Telegram Alerts
# Date: 2026-03-28
# Author: claude.ai + ChatGPT consultation → Claude Code execution
# Scope: تحويل "الفرص الذهبية" من معلومات إلى قرارات تداول كاملة

---

## الهدف الكبير

تحويل صفحة "قرارات الآن" من:
❌ "هذا النمط نجح 72%" (المستخدم ما يعرف يسوي شي)

إلى:
✅ "ادخل الآن بسعر 130-135 / وقف 122 / هدف 153 / R:R 2.7x" (المستخدم يعرف بالضبط)

---

## 3 ملفات جديدة + تحديث 2 ملف:

| الملف | الدور | المنفذ |
|-------|-------|--------|
| `sr_engine.py` (جديد) | حساب الدعم والمقاومة من swing highs/lows | Claude Code |
| `trading_decision_engine.py` (جديد) | Entry timing + Trade plan + Entry status | Claude Code |
| `golden_engine.py` (تحديث) | دمج S/R + Trade Plan + Entry Status | Claude Code |
| `server.py` (تحديث) | Telegram alerts عند فرصة جديدة | Claude Code |
| `decisions.html` (تحديث) | عرض Entry Zone + Stop + Target + Status | claude.ai |

---

## PHASE 1 — S/R Engine (`sr_engine.py`)

### المكان: `/home/pi/master_ai/sr_engine.py`

```python
"""
sr_engine.py — Support & Resistance Engine.
Computes S/R levels from Bridge API daily bars using swing high/low clustering.
"""
import os
import sqlite3
import logging
import json
from datetime import datetime

logger = logging.getLogger("sr_engine")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def init_sr_schema():
    """Add sr columns to stock_profiles if not exist."""
    conn = _conn()
    for col in [
        "ALTER TABLE stock_profiles ADD COLUMN sr_json TEXT",
        "ALTER TABLE stock_profiles ADD COLUMN sr_updated_at TEXT",
    ]:
        try:
            conn.execute(col)
        except Exception:
            pass
    conn.commit()
    conn.close()


def find_pivots(bars, left=3, right=3):
    """Find swing highs and swing lows from OHLC bars."""
    highs = []
    lows = []
    for i in range(left, len(bars) - right):
        h = bars[i].get("high") or bars[i].get("h") or 0
        lo = bars[i].get("low") or bars[i].get("l") or 0

        is_high = all(
            h >= (bars[j].get("high") or bars[j].get("h") or 0)
            for j in range(i - left, i + right + 1) if j != i
        )
        is_low = all(
            lo <= (bars[j].get("low") or bars[j].get("l") or 0)
            for j in range(i - left, i + right + 1) if j != i
        )

        if is_high:
            highs.append({"index": i, "price": round(h, 3), "volume": bars[i].get("volume", 0)})
        if is_low:
            lows.append({"index": i, "price": round(lo, 3), "volume": bars[i].get("volume", 0)})

    return highs, lows


def cluster_levels(levels, tolerance_pct=1.5):
    """Group nearby price levels into clusters. Returns sorted by score."""
    if not levels:
        return []
    levels = sorted(levels, key=lambda x: x["price"])
    clusters = []
    current = [levels[0]]

    for lev in levels[1:]:
        avg = sum(x["price"] for x in current) / len(current)
        diff = abs(lev["price"] - avg) / avg * 100 if avg > 0 else 999
        if diff <= tolerance_pct:
            current.append(lev)
        else:
            clusters.append(current)
            current = [lev]
    clusters.append(current)

    result = []
    for cl in clusters:
        avg_p = round(sum(x["price"] for x in cl) / len(cl), 3)
        touches = len(cl)
        latest = max(x["index"] for x in cl)
        avg_vol = sum(x.get("volume", 0) for x in cl) / max(1, len(cl))
        # Score: more touches + more recent + more volume = stronger level
        score = round(touches * 3 + (latest * 0.1) + (avg_vol / 1_000_000), 2)
        result.append({
            "price": avg_p,
            "touches": touches,
            "score": score,
            "latest_index": latest,
        })
    return sorted(result, key=lambda x: x["score"], reverse=True)


def compute_sr(symbol, bars, current_price):
    """
    Compute support and resistance for a symbol.
    bars: list of dicts with high, low, close, volume keys.
    Returns dict with key_support, key_resistance, all levels, etc.
    """
    if not bars or len(bars) < 20:
        return {"symbol": symbol, "key_support": None, "key_resistance": None,
                "support_levels": [], "resistance_levels": []}

    pivot_highs, pivot_lows = find_pivots(bars, left=3, right=3)
    sup_clusters = cluster_levels(pivot_lows, tolerance_pct=1.5)
    res_clusters = cluster_levels(pivot_highs, tolerance_pct=1.5)

    # Find nearest support below current price
    sups_below = [s for s in sup_clusters if s["price"] < current_price]
    key_sup = max(sups_below, key=lambda x: x["price"], default=None)

    # Find nearest resistance above current price
    res_above = [r for r in res_clusters if r["price"] > current_price]
    key_res = min(res_above, key=lambda x: x["price"], default=None)

    return {
        "symbol": symbol,
        "current_price": current_price,
        "key_support": key_sup["price"] if key_sup else None,
        "key_support_touches": key_sup["touches"] if key_sup else 0,
        "key_support_score": key_sup["score"] if key_sup else 0,
        "key_resistance": key_res["price"] if key_res else None,
        "key_resistance_touches": key_res["touches"] if key_res else 0,
        "key_resistance_score": key_res["score"] if key_res else 0,
        "support_levels": [s["price"] for s in sup_clusters[:5]],
        "resistance_levels": [r["price"] for r in res_clusters[:5]],
    }


def refresh_sr_for_all(bridge_data=None):
    """
    Refresh S/R for all symbols using Bridge daily data.
    bridge_data: dict of {symbol: {bars: [...], price: X}} from Bridge API.
    If None, uses stock_radar_daily prices + whatever bars are available.
    """
    init_sr_schema()
    conn = _conn()
    updated = 0

    if bridge_data:
        for sym, data in bridge_data.items():
            bars = data.get("bars", [])
            price = data.get("price", 0)
            if not bars or not price:
                continue
            sr = compute_sr(sym, bars, price)
            conn.execute(
                "UPDATE stock_profiles SET key_support=?, key_resistance=?, sr_json=?, sr_updated_at=? WHERE symbol=?",
                (sr["key_support"], sr["key_resistance"], json.dumps(sr), datetime.utcnow().isoformat(), sym)
            )
            updated += 1
    else:
        # Fallback: use support/resistance from stock_radar_daily
        rows = conn.execute(
            "SELECT symbol, support, resistance, price FROM stock_radar_daily WHERE support IS NOT NULL"
        ).fetchall()
        for r in rows:
            conn.execute(
                "UPDATE stock_profiles SET key_support=?, key_resistance=? WHERE symbol=?",
                (r["support"], r["resistance"], r["symbol"])
            )
            updated += 1

    conn.commit()
    conn.close()
    logger.info(f"S/R refreshed for {updated} symbols")
    return {"updated": updated}
```

---

## PHASE 2 — Trading Decision Engine (`trading_decision_engine.py`)

### المكان: `/home/pi/master_ai/trading_decision_engine.py`

```python
"""
trading_decision_engine.py — Entry Timing + Trade Plan.
Converts golden opportunities into actionable trade decisions.
"""
import logging
import math

logger = logging.getLogger("decision_engine")


# ═══════════════════════════════════
# ENTRY STATUS — متى أدخل؟
# ═══════════════════════════════════

def compute_entry_status(opp, profile):
    """
    Determine entry timing for an opportunity.
    Returns: {entry_status, entry_status_ar, entry_score, reasoning_ar, rr_ratio}

    opp: opportunity dict from golden_engine (has price, support, resistance, etc)
    profile: stock_profiles row (has key_support, key_resistance, sr_json, etc)
    """
    price = float(opp.get("price") or 0)
    if price <= 0:
        return _status("watch", 30, ["\u0644\u0627 \u064A\u0648\u062C\u062F \u0633\u0639\u0631 \u062D\u064A"], None)

    # Get S/R levels
    support = float(profile.get("key_support") or opp.get("support") or 0)
    resistance = float(profile.get("key_resistance") or opp.get("resistance") or 0)
    atr = float(opp.get("atr_14") or opp.get("atr") or price * 0.02)

    # Compute entry zone
    if support > 0:
        entry_low = max(support * 0.998, price - atr * 0.8)
        entry_high = min(price + atr * 0.2, support + atr * 1.5)
    else:
        entry_low = price - atr * 0.5
        entry_high = price + atr * 0.2

    # Compute stop loss
    if support > 0:
        stop = min(support - atr * 0.6, entry_low - atr * 0.5)
    else:
        stop = entry_low - atr * 1.0

    # Compute targets
    hist_gain = float(opp.get("avg_gain_pct") or 0)
    target_1 = resistance if resistance > price else price * (1 + max(hist_gain, 3) / 100)
    target_2 = price * (1 + max(hist_gain * 1.5, 5) / 100)
    if resistance > price:
        target_2 = max(target_2, resistance * 1.02)

    # R/R ratio
    entry_mid = (entry_low + entry_high) / 2
    risk = entry_mid - stop
    reward = target_1 - entry_mid
    rr = round(reward / risk, 2) if risk > 0 else 0

    trade_plan = {
        "entry_zone_low": round(entry_low, 3),
        "entry_zone_high": round(entry_high, 3),
        "entry_mid": round(entry_mid, 3),
        "stop_loss": round(stop, 3),
        "stop_distance_pct": round((entry_mid - stop) / entry_mid * 100, 1) if entry_mid > 0 else 0,
        "target_1": round(target_1, 3),
        "target_2": round(target_2, 3),
        "rr_ratio": rr,
    }

    # ═══ DECISION LOGIC ═══

    reasons = []
    in_entry_zone = entry_low <= price <= entry_high
    vol_ok = float(opp.get("current_vol") or opp.get("vol_ratio") or 0) >= 1.2
    stoch = float(opp.get("current_stoch") or opp.get("stoch_k") or 50)
    rsi = float(opp.get("current_rsi") or opp.get("rsi_14") or 50)
    confidence = float(opp.get("confidence") or 0)
    win_rate = float(opp.get("win_rate") or 0)

    # ⛔ AVOID
    if support > 0 and price < support * 0.99:
        reasons.append("\u0627\u0644\u0633\u0639\u0631 \u0643\u0633\u0631 \u0627\u0644\u062F\u0639\u0645")
        return _status("avoid", 10, reasons, trade_plan)

    if rr < 1.2:
        reasons.append("\u0627\u0644\u0639\u0627\u0626\u062F/\u0627\u0644\u0645\u062E\u0627\u0637\u0631\u0629 \u0636\u0639\u064A\u0641 ({:.1f}x)".format(rr))
        return _status("avoid", 15, reasons, trade_plan)

    # 🟢 ENTER NOW
    if in_entry_zone and vol_ok and rr >= 1.8 and confidence >= 75:
        reasons.append("\u0627\u0644\u0633\u0639\u0631 \u062F\u0627\u062E\u0644 \u0645\u0646\u0637\u0642\u0629 \u0627\u0644\u062F\u062E\u0648\u0644")
        if vol_ok:
            reasons.append("\u0627\u0644\u062D\u062C\u0645 \u064A\u0624\u0643\u062F")
        if stoch < 30:
            reasons.append("Stoch \u0645\u062A\u0634\u0628\u0639 \u0628\u064A\u0639\u064A\u0627\u064B — \u0627\u0631\u062A\u062F\u0627\u062F \u0645\u062A\u0648\u0642\u0639")
        if rsi < 35:
            reasons.append("RSI \u0645\u062A\u0634\u0628\u0639 \u0628\u064A\u0639\u064A\u0627\u064B")
        reasons.append("R/R {:.1f}x \u0645\u0645\u062A\u0627\u0632".format(rr))
        return _status("enter_now", 90, reasons, trade_plan)

    # 🟢 ENTER NOW (relaxed — in zone but volume weak)
    if in_entry_zone and rr >= 2.0 and confidence >= 80:
        reasons.append("\u0627\u0644\u0633\u0639\u0631 \u0628\u0645\u0646\u0637\u0642\u0629 \u0627\u0644\u062F\u062E\u0648\u0644")
        if not vol_ok:
            reasons.append("\u0627\u0644\u062D\u062C\u0645 \u0645\u0642\u0628\u0648\u0644 \u2014 \u0627\u062F\u062E\u0644 \u0628\u062D\u0630\u0631")
        reasons.append("Confidence {:.0f} \u0639\u0627\u0644\u064A".format(confidence))
        return _status("enter_now", 80, reasons, trade_plan)

    # 🟡 WAIT PULLBACK
    if price > entry_high and rr >= 1.5:
        pct_above = (price - entry_high) / entry_high * 100
        reasons.append("\u0627\u0644\u0633\u0639\u0631 \u0641\u0648\u0642 \u0645\u0646\u0637\u0642\u0629 \u0627\u0644\u062F\u062E\u0648\u0644 \u0628{:.1f}%".format(pct_above))
        reasons.append("\u0627\u0646\u062A\u0638\u0631 \u0631\u062C\u0648\u0639 \u0644\u0645\u0646\u0637\u0642\u0629 {:.0f}-{:.0f}".format(entry_low, entry_high))
        if resistance > 0 and (resistance - price) / price * 100 < 2:
            reasons.append("\u0627\u0644\u0645\u0642\u0627\u0648\u0645\u0629 \u0642\u0631\u064A\u0628\u0629 \u2014 \u0644\u0627 \u062A\u0637\u0627\u0631\u062F")
        return _status("wait_pullback", 65, reasons, trade_plan)

    # 🔴 MISSED
    if resistance > 0 and price >= target_1 * 0.95:
        reasons.append("\u0627\u0644\u0633\u0639\u0631 \u0648\u0635\u0644 \u0642\u0631\u0628 \u0627\u0644\u0647\u062F\u0641")
        reasons.append("\u0627\u0644\u062D\u0631\u0643\u0629 \u062A\u062D\u0642\u0642\u062A \u2014 \u0641\u0627\u062A \u0627\u0644\u0642\u0637\u0627\u0631")
        return _status("missed", 20, reasons, trade_plan)

    # ⚪ WATCH
    reasons.append("\u0627\u0644\u0646\u0645\u0637 \u062C\u064A\u062F \u0628\u0633 \u0627\u0644\u062A\u0623\u0643\u064A\u062F \u0646\u0627\u0642\u0635")
    if not vol_ok:
        reasons.append("\u0627\u0644\u062D\u062C\u0645 \u0636\u0639\u064A\u0641 \u2014 \u0627\u0646\u062A\u0638\u0631 \u062A\u0623\u0643\u064A\u062F")
    if rr < 1.8:
        reasons.append("R/R {:.1f}x \u0645\u062A\u0648\u0633\u0637".format(rr))
    return _status("watch", 50, reasons, trade_plan)


def _status(key, score, reasons, trade_plan):
    STATUS_AR = {
        "enter_now": "\U0001f7e2 \u0627\u062F\u062E\u0644 \u0627\u0644\u0622\u0646",
        "wait_pullback": "\U0001f7e1 \u0627\u0646\u062A\u0638\u0631 pullback",
        "watch": "\u26AA \u0631\u0627\u0642\u0628",
        "missed": "\U0001f534 \u0641\u0627\u062A \u0627\u0644\u0642\u0637\u0627\u0631",
        "avoid": "\u26D4 \u062A\u062C\u0646\u0628",
    }
    return {
        "entry_status": key,
        "entry_status_ar": STATUS_AR.get(key, key),
        "entry_score": score,
        "reasoning_ar": reasons,
        "trade_plan": trade_plan,
    }
```


---

## PHASE 3 — تحديث `golden_engine.py` — دمج S/R + Trade Plan + Entry Status

### التعديل في `scan_opportunities()`:

بعد ما يبني الـ `opp` dict لكل فرصة، أضف:

```python
# بعد بناء opp dict وقبل all_opportunities.append(best_opp):

# Enrich with S/R from profile
from trading_decision_engine import compute_entry_status
from sr_engine import compute_sr

# Get S/R from profile or compute
sr_json = profile.get("sr_json")
if sr_json:
    try:
        sr_data = json.loads(sr_json) if isinstance(sr_json, str) else sr_json
        opp["key_support"] = sr_data.get("key_support")
        opp["key_resistance"] = sr_data.get("key_resistance")
        opp["support_levels"] = sr_data.get("support_levels", [])
        opp["resistance_levels"] = sr_data.get("resistance_levels", [])
        opp["support_touches"] = sr_data.get("key_support_touches", 0)
        opp["resistance_touches"] = sr_data.get("key_resistance_touches", 0)
    except Exception:
        pass

# Fallback: use live data S/R
if not opp.get("key_support"):
    opp["key_support"] = float(live.get("support") or 0) or None
if not opp.get("key_resistance"):
    opp["key_resistance"] = float(live.get("resistance") or 0) or None

# Compute entry decision
decision = compute_entry_status(opp, profile)
opp["entry_status"] = decision["entry_status"]
opp["entry_status_ar"] = decision["entry_status_ar"]
opp["entry_score"] = decision["entry_score"]
opp["reasoning_ar"] = decision["reasoning_ar"]
opp["trade_plan"] = decision["trade_plan"]
```

### أيضاً أضف S/R لـ stock_profiles load:

```python
# عند تحميل profiles من DB، أضف sr_json:
for r in conn.execute("SELECT *, sr_json FROM stock_profiles").fetchall():
    profiles[r["symbol"]] = dict(r)
```

---

## PHASE 4 — Telegram Alerts

### الملف: `server.py` أو ملف مستقل `telegram_alerts.py`

### الـ Schema:
```sql
CREATE TABLE IF NOT EXISTS alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    pattern_key TEXT,
    entry_status TEXT,
    confidence REAL,
    dedup_key TEXT UNIQUE,
    sent_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### الـ Alert Logic:
```python
import requests

def send_golden_alert(opp):
    """Send Telegram alert for a golden opportunity."""
    # Read bot token and chat_id from config
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN") or _read_file("~/.telegram_bot_token")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or _read_file("~/.telegram_chat_id")
    if not bot_token or not chat_id:
        return False

    tp = opp.get("trade_plan") or {}

    text = (
        f"\U0001f6a8 <b>\u0641\u0631\u0635\u0629 \u0630\u0647\u0628\u064a\u0629 \u2014 {opp['symbol']}</b>\n\n"
        f"\U0001f4ca <b>\u0627\u0644\u0646\u0645\u0637:</b> {opp.get('pattern_ar', '')}\n"
        f"\u2705 <b>\u0646\u0633\u0628\u0629 \u0646\u062c\u0627\u062d:</b> {opp.get('win_rate', 0):.0f}% ({opp.get('occurrences', 0)} \u0645\u0631\u0629)\n"
        f"{opp.get('entry_status_ar', '')}\n\n"
        f"\U0001f4b0 <b>\u0627\u0644\u0633\u0639\u0631:</b> {opp.get('price', 0)}\n"
        f"\U0001f3af <b>\u0645\u0646\u0637\u0642\u0629 \u0627\u0644\u062f\u062e\u0648\u0644:</b> {tp.get('entry_zone_low', '')} - {tp.get('entry_zone_high', '')}\n"
        f"\U0001f6d1 <b>\u0648\u0642\u0641:</b> {tp.get('stop_loss', '')} ({tp.get('stop_distance_pct', '')}%)\n"
        f"\U0001f3c1 <b>\u0647\u062f\u0641 1:</b> {tp.get('target_1', '')}\n"
        f"\U0001f3c1 <b>\u0647\u062f\u0641 2:</b> {tp.get('target_2', '')}\n"
        f"\u2696\ufe0f <b>R/R:</b> {tp.get('rr_ratio', 0)}x\n\n"
    )

    # Add reasons
    reasons = opp.get("reasoning_ar", [])
    if reasons:
        text += "<b>\u0627\u0644\u0633\u0628\u0628:</b>\n"
        text += "\n".join(f"- {r}" for r in reasons[:4])

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"Telegram alert failed: {e}")
        return False


def should_alert(conn, opp):
    """Check if we should send alert (dedup)."""
    status = opp.get("entry_status", "")
    if status not in ("enter_now", "wait_pullback"):
        return False
    if opp.get("confidence", 0) < 75:
        return False

    dedup = f"{opp['symbol']}:{opp.get('pattern_atoms', '')}:{status}"
    row = conn.execute("SELECT id FROM alert_history WHERE dedup_key=?", (dedup,)).fetchone()
    if row:
        return False
    return True


def record_alert(conn, opp):
    """Record sent alert for dedup."""
    dedup = f"{opp['symbol']}:{opp.get('pattern_atoms', '')}:{opp.get('entry_status', '')}"
    conn.execute(
        "INSERT OR IGNORE INTO alert_history (symbol, pattern_key, entry_status, confidence, dedup_key) VALUES (?,?,?,?,?)",
        (opp["symbol"], opp.get("pattern_atoms"), opp.get("entry_status"), opp.get("confidence"), dedup)
    )
    conn.commit()
```

### دمج بالـ `scan_opportunities()`:

```python
# بعد حساب كل الفرص وقبل return:

# Send Telegram alerts for new "enter_now" opportunities
alert_conn = _conn()
for opp in all_opportunities:
    if opp.get("entry_status") == "enter_now" and opp.get("confidence", 0) >= 80:
        if should_alert(alert_conn, opp):
            if send_golden_alert(opp):
                record_alert(alert_conn, opp)
alert_conn.close()
```

---

## PHASE 5 — تحديث S/R يومياً

### أضف لـ `server.py` scheduler أو لـ daily refresh:

```python
# بعد daily snapshot refresh:
from sr_engine import refresh_sr_for_all
refresh_sr_for_all()  # Uses stock_radar_daily S/R as fallback
```

### أو لو Bridge شغال (أفضل):

```python
# بعد ما Bridge يسحب daily bars:
from sr_engine import compute_sr
from bridge_client import get_bridge_client
import asyncio

async def refresh_sr_with_bridge():
    client = get_bridge_client()
    from stock_radar import get_watchlist
    wl = get_watchlist()
    symbols = [w["symbol"] for w in wl]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    updated = 0

    for sym in symbols:
        try:
            analysis = await client.get_analysis(sym)
            bars = analysis.get("bars", [])
            price = analysis.get("price", 0)
            if bars and price:
                sr = compute_sr(sym, bars, price)
                conn.execute(
                    "UPDATE stock_profiles SET key_support=?, key_resistance=?, sr_json=?, sr_updated_at=? WHERE symbol=?",
                    (sr["key_support"], sr["key_resistance"],
                     json.dumps(sr, ensure_ascii=False), datetime.utcnow().isoformat(), sym)
                )
                updated += 1
        except Exception as e:
            pass

    conn.commit()
    conn.close()
    return {"updated": updated}
```

---

## PHASE 6 — Testing

```bash
cd /home/pi/master_ai

# 1. Create files:
# sr_engine.py (الكود أعلاه)
# trading_decision_engine.py (الكود أعلاه)

# 2. Refresh S/R from existing daily data:
venv/bin/python3 -c "
from sr_engine import refresh_sr_for_all
print(refresh_sr_for_all())
"

# 3. Test decision engine on one opportunity:
venv/bin/python3 -c "
from trading_decision_engine import compute_entry_status
opp = {
    'symbol': 'CLEANING', 'price': 135, 'confidence': 84,
    'win_rate': 72, 'avg_gain_pct': 10.2, 'current_vol': 2.3,
    'current_stoch': 18, 'current_rsi': 28, 'atr_14': 6.5,
    'support': 106, 'resistance': 153,
}
profile = {'key_support': 106, 'key_resistance': 153}
result = compute_entry_status(opp, profile)
import json
print(json.dumps(result, ensure_ascii=False, indent=2))
"

# 4. Test full pipeline:
KEY=\$(cat ~/.master_ai_key)
curl -s -H \"X-API-Key: \$KEY\" http://localhost:9000/api/decisions-now | python3 -c "
import sys, json
d = json.load(sys.stdin)
for o in (d.get('top_10') or d.get('all_opportunities', []))[:3]:
    print(f\"{o['symbol']}: {o.get('entry_status_ar','')} | conf={o.get('confidence')} | tp={o.get('trade_plan',{}).get('rr_ratio','')}\")
"

# 5. Init alert_history table:
venv/bin/python3 -c "
import sqlite3
c = sqlite3.connect('data/life.db')
c.execute('''CREATE TABLE IF NOT EXISTS alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    pattern_key TEXT,
    entry_status TEXT,
    confidence REAL,
    dedup_key TEXT UNIQUE,
    sent_at TEXT DEFAULT CURRENT_TIMESTAMP
)''')
c.commit()
print('alert_history table ready')
"

# 6. Commit + restart:
git add sr_engine.py trading_decision_engine.py golden_engine.py server.py
git commit -m 'feat: trading decision engine V2 — entry timing + S/R + trade plan + telegram alerts'
sudo systemctl restart master-ai.service
```

---

## PHASE 7 — Dashboard (claude.ai يعدّل decisions.html)

بعد ما Claude Code يخلص، claude.ai يحدّث decisions.html عشان يعرض:

### لكل بطاقة فرصة:
1. **Entry Status badge**: 🟢 ادخل الآن / 🟡 انتظر / 🔴 فات القطار
2. **Entry Zone**: منطقة الدخول (low - high) مع bar بصري
3. **Stop Loss + Target**: بخط أحمر (stop) وخط أخضر (target)
4. **R/R ratio**: بلون حسب الجودة
5. **Reasoning**: أسباب القرار بالعربي
6. **Support/Resistance levels**: مع عدد اللمسات
7. **تنبيه Telegram**: badge لو تم الإرسال

---

## SUMMARY — قبل وبعد

### قبل:
```
🔥 CLEANING — فرصة ذهبية (84.6)
   النمط: Stoch<20 + MACD bearish → 72% نجاح
   (وبس... ما أدري وين أدخل أو متى)
```

### بعد:
```
🔥 CLEANING — فرصة ذهبية (84.6)
   🟢 ادخل الآن
   📊 النمط: Stoch<20 + MACD bearish → 72% نجاح
   🎯 منطقة الدخول: 130 - 135
   🛑 وقف: 122 (-9.6%)
   🏁 هدف 1: 153 | هدف 2: 163
   ⚖️ R/R: 2.7x
   🛡️ دعم: 106 (8 لمسات) | مقاومة: 153 (5 لمسات)
   السبب: السعر بمنطقة الدخول + الحجم يؤكد + Stoch متشبع بيعياً
   📱 تم إرسال تنبيه Telegram
```

---

## HOW TO EXECUTE

Tell Claude Code:
```
اقرأ _tools/TRADING_DECISION_ENGINE_V2.md ونفذ:
Phase 1: أنشئ sr_engine.py
Phase 2: أنشئ trading_decision_engine.py
Phase 3: عدّل golden_engine.py — دمج S/R + entry_status + trade_plan
Phase 4: أضف alert_history table + telegram alert logic
Phase 5: أضف sr refresh لـ daily refresh
Phase 6: اختبر كل شي
ثم commit + restart
```
