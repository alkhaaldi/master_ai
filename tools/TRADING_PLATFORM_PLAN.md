# Master AI v8.5 — Integrated Trading Platform
> Goal: منصة تداول متكاملة — الرادار + TradingView + Journal مترابطين
> TradingView Premium account available

---

## الوضع الحالي (ملخص التحقيق)

### مصادر البيانات:
1. **الرادار (stock_radar.py)** → يستخدم `tvDatafeed` library (TradingView unofficial API)
   - يجيب بيانات من TradingView مباشرة عبر `TvDatafeed.get_hist()`
   - الأسعار بالفلس (مثل 99.1 fils)
   - يراقب 128 سهم KSE
   - يفحص EMA9/21 crossover على 30m candles
   - يشتغل فقط وقت السوق (أحد-خميس 9:00-12:40)

2. **TradingView Webhook (tradingview_bridge.py)** → يستقبل alerts من TV
   - الأسعار بالدينار KWD (مثل 0.285 = 285 fils)
   - يعتمد على alerts أنت تسويها يدوي في TV
   - TV watchlist فاضي (0 أسهم) — يعني ما فيه auto-monitoring

3. **tv_data.py** → `get_price()` يجيب سعر أي سهم عبر tvDatafeed
   - يرجع: price, open, high, low, close, volume, change
   - Cache مع TTL

### المشاكل:
- **السعر غلط بالـ webhook**: TV يرسل 0.285 KWD، الداشبورد يعرض بالفلس → وحدات مختلفة
- **النظامين منفصلين**: الرادار يراقب 128 سهم بس إشاراته ما تتحول لأزرار تأكيد
- **TV watchlist فاضي**: الـ webhook يعتمد على alerts يدوية، مو أتوماتيكي
- **Journal فاضي**: ما فيه ربط بين الإشارات والصفقات الفعلية

---

## PRE-FLIGHT
```bash
cat CLAUDE.md
git add -A && git commit -m "backup: pre-v8.5 trading platform"
```

---

## PHASE 1: Fix Price Units — توحيد الأسعار بالفلس

### المشكلة:
- الرادار (tvDatafeed) يرجع أسعار: أحياناً بالفلس (99.1) وأحياناً بالدينار (0.285)
- TradingView webhook يرسل بالدينار دائماً
- الداشبورد يعرض بالفلس
- لازم نوحّد: **كل شي بالفلس** داخلياً

### الحل:
أضف function `_normalize_price_to_fils(price, symbol)` في `tv_data.py`:
```python
def _normalize_price_to_fils(price, symbol=None):
    """Normalize price to fils. TradingView returns KWD for KSE stocks.
    If price < 10, it's likely KWD → multiply by 1000.
    If price >= 10, it's likely already fils."""
    if price is None:
        return None
    price = float(price)
    # KSE stocks: if price looks like KWD (< 10), convert to fils
    if price < 10:
        return round(price * 1000, 1)
    return round(price, 1)
```

### أماكن التطبيق:
1. **tradingview_bridge.py** → `save_tv_alert()` و `handle_webhook()`: نورمالايز السعر قبل الحفظ
2. **الرسالة في _send_trade_confirmation()**: اعرض السعر بالفلس مع توضيح
3. **journal_engine.py** → `record_trade()` / `open_trade()`: نورمالايز قبل الحفظ

### Validation:
```bash
python3 -c "
from tv_data import _normalize_price_to_fils
print(_normalize_price_to_fils(0.285))   # → 285.0
print(_normalize_price_to_fils(99.1))     # → 99.1
print(_normalize_price_to_fils(566.0))    # → 566.0
print(_normalize_price_to_fils(0.099))    # → 99.0
"
```

```bash
python3 _tools/quick_check.py && python3 _tools/smoke_test.py
bash _tools/restart_master_ai.sh
git add -A && git commit -m "fix: normalize all prices to fils across radar, webhook, journal"
```

---

## PHASE 2: Radar → TG Confirmation (الأهم)

### الفكرة:
الرادار يراقب 128 سهم. لما يرصد إشارة (EMA cross)، بدل ما بس يرسل رسالة عادية → يرسل رسالة مع أزرار "شريت / تجاهلت" نفس اللي سويناها للـ webhook.

### التنفيذ:
ابحث في `stock_radar.py` عن المكان اللي يرسل فيه إشارة عبر Telegram:
```bash
grep -n 'send_fn\|send_alert\|send_message\|تقاطع\|cross.*alert' stock_radar.py
```

عدّل: بعد ما يرسل الرسالة العادية، أضف رسالة ثانية مع inline keyboard:

```python
# After the normal alert message is sent via send_fn(text)
# Send confirmation buttons
try:
    from tradingview_bridge import _send_trade_confirmation_tg
    await _send_trade_confirmation_tg({
        "symbol": symbol,
        "price": price,  # already in fils from radar
        "type": signal_type,  # "bullish_cross" or "bearish_cross"
        "strategy": "Radar EMA9/21",
        "score": score,
        "score_class": score_class,
        "rsi": rsi,
        "source": "radar"
    })
except Exception as e:
    logger.warning(f"Trade confirmation send failed: {e}")
```

### الرسالة المحسّنة:
```
📡 إشارة الرادار — KSE:CLEANING

📈 تقاطع صاعد (EMA9 > EMA21)
السعر: 99.1 فلس
Score: 85/A
RSI: 64
Volume: ×2.6

شريت ولا تجاهلت؟

[شريت ✅]  [تجاهلت ❌]
```

### ملاحظة مهمة:
- الرادار يشتغل فقط وقت السوق — يعني الأزرار بتجي بس وقت التداول
- كل إشارة تجي مع score وتقييم — المستخدم يقرر إذا يشتري
- إذا ضغط "شريت" → يسأله عن الكمية (رسالة follow-up) أو يسجّلها بكمية 0 (يحدّثها لاحقاً)

### Callback handler:
عدّل الـ callback handler الموجود (اللي انبنى في Phase 4 السابقة):
- `trade_confirm:SYMBOL:PRICE:ACTION:SOURCE` → إضافة source (radar vs webhook)
- لما المصدر radar → السعر بالفلس جاهز
- لما المصدر webhook → نورمالايز أول

### Validation:
```bash
python3 _tools/quick_check.py && python3 _tools/smoke_test.py
bash _tools/restart_master_ai.sh
# Simulate: manually trigger a radar signal
# Check: TG message arrives with buttons
git add -A && git commit -m "feat: radar signals now include buy/skip confirmation buttons"
```

---

## PHASE 3: Sync TV Watchlist with Radar

### المشكلة:
- TV watchlist = 0 أسهم (فاضي)
- Radar watchlist = 128 سهم
- لما تسوي alert على TradingView يدوي، لازم يكون السهم معروف في النظام

### الحل:
أضف أمر `/tv_sync` يملأ TV watchlist من radar watchlist:
```python
async def cmd_tv_sync():
    """Sync TV watchlist from radar watchlist."""
    from tv_data import KSE_STOCKS
    import sqlite3
    conn = sqlite3.connect(str(LIFE_DB))
    # Get all radar symbols
    radar_symbols = [r[0] for r in conn.execute(
        "SELECT symbol FROM stock_radar_watchlist"
    ).fetchall()]
    # Clear old TV watchlist
    conn.execute("DELETE FROM tv_watchlists")
    # Insert all radar symbols
    for sym in radar_symbols:
        name = KSE_STOCKS.get(sym, sym)
        conn.execute(
            "INSERT OR IGNORE INTO tv_watchlists (symbol, name, active) VALUES (?, ?, 1)",
            (sym, name)
        )
    conn.commit()
    conn.close()
    return f"✅ تم مزامنة {len(radar_symbols)} سهم من الرادار إلى TV watchlist"
```

### Auto-sync:
أضف auto-sync عند بداية radar_loop — لما الرادار يبدأ، يزامن الـ TV watchlist تلقائياً.

### Validation:
```bash
# Test
curl -s -X POST ... /dashboard/cmd -d '{"command":"/tv_sync"}'
# Check
sqlite3 data/life.db "SELECT COUNT(*) FROM tv_watchlists"  # Should be 128
```

```bash
git add -A && git commit -m "feat: /tv_sync command + auto-sync TV watchlist from radar"
```

---

## PHASE 4: Journal Dashboard Integration

### المشكلة:
الـ journal card في Trading page يعرض trades بس ما فيها أي data لأن ما أحد يسجّل.

### الحل:
بعد Phase 2، لما المستخدم يضغط "شريت"، الصفقة تتسجل تلقائي. الحين لازم نتأكد إن:

1. **journal_open** في `/dashboard/radar` يرجع الصفقات المفتوحة فعلاً
2. **journal_stats** يحسب win_rate و P&L صح
3. **الداشبورد يعرض** السعر الحالي vs سعر الدخول (P&L live)

### إضافة P&L حي:
```python
# In the radar endpoint, for each open trade:
for trade in open_trades:
    current_price = get_current_price(trade["symbol"])  # from tv_data
    trade["current_price"] = current_price
    trade["pnl_fils"] = (current_price - trade["entry_price"]) * trade["quantity"]
    trade["pnl_pct"] = ((current_price / trade["entry_price"]) - 1) * 100 if trade["entry_price"] else 0
```

### Dashboard YAML update:
عدّل Journal card في Trading page ليعرض P&L:
```yaml
| السهم | الدخول | الحالي | P&L | الكمية |
```

### Validation:
```bash
python3 _tools/quick_check.py && python3 _tools/smoke_test.py
bash _tools/restart_master_ai.sh
git add -A && git commit -m "feat: live P&L in journal dashboard card"
```

---

## PHASE 5: Daily Trading Summary

### إضافة ملخص تداول يومي:
كل يوم الساعة 1:00 PM (بعد إغلاق السوق)، أرسل ملخص:

```
📊 ملخص التداول — 2026-03-21

📡 إشارات اليوم: 5 (3 صاعد, 2 هابط)
✅ صفقات نُفذت: 2
⏭ إشارات متجاهلة: 3

📂 صفقات مفتوحة: 3
   CLEANING: +2.1% (ربح 210 فلس)
   ZAIN: -0.5% (خسارة 50 فلس)
   SENERGY: +1.2% (ربح 120 فلس)

📈 P&L الإجمالي: +280 فلس

🎯 أفضل أسهم الأسبوع:
   1. MRC — Score 85/A
   2. ZAIN — Score 80/A
   3. CLEANING — Score 75/B
```

### التنفيذ:
- أضف function `_build_daily_trading_summary()` في server.py أو ملف جديد `trading_summary.py`
- أضفها في الـ scheduler (نفس مكان morning report)
- Wire في `/dashboard/extended` كـ `trading_summary` field

```bash
git add -A && git commit -m "feat: daily trading summary at market close"
```

---

## PHASE 6: Version Bump + Context

### 6A. VERSION = "8.5.0"
### 6B. Update CLAUDE_CONTEXT.md:
- Price normalization (fils-first)
- Radar → TG confirmation buttons
- TV watchlist sync
- Journal P&L tracking
- Daily trading summary
### 6C. Final validation

```bash
python3 _tools/quick_check.py && python3 _tools/smoke_test.py && python3 _tools/db_sanity.py
wc -l server.py
git add -A && git commit -m "v8.5.0: integrated trading platform — radar confirm, price normalization, live P&L"
```

---

## EXECUTION ORDER
```
Phase 1: Fix price units (توحيد بالفلس) → test → commit
Phase 2: Radar → TG confirmation buttons → test → commit
Phase 3: Sync TV watchlist from radar → test → commit
Phase 4: Journal P&L integration → test → commit
Phase 5: Daily trading summary → test → commit
Phase 6: v8.5.0 + context update → final commit
```

## RULES
- server.py: عبر _tools/patchers/apply_text_patch.py
- ملفات جديدة: مباشرة
- test بعد كل phase
- git commit بعد كل phase
- الأسعار دائماً بالفلس داخلياً
- backward compatible
