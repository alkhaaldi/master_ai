# TRADING JOURNAL + SMART ALERTS — V12 Plan
# ================================================================
# تاريخ: 2026-03-20
# الهدف: Trading Journal (تسجيل الصفقات) + Smart Alerts (إشعارات ذكية)
# المبدأ: Backend أولاً (ملف جديد + server.py patches) ثم Dashboard
# ================================================================

---

# ما هو Trading Journal؟

نظام لتسجيل كل صفقة — دخول، خروج، سبب الدخول، سبب الخروج، الربح/الخسارة.
هذا أهم أداة لتطوير المتداول — بدون journal ما تعرف شنو يشتغل وشنو لا.

## الحد الأدنى (MVP):
- تسجيل صفقة (سهم، سعر دخول، كمية، سبب)
- إغلاق صفقة (سعر خروج، سبب الخروج)
- حساب P&L تلقائي
- عرض الصفقات المفتوحة والمغلقة
- إحصائيات: win rate, avg profit, avg loss, total P&L

## لاحقاً (V13+):
- ربط مع الـ radar signals (auto-suggest entry عند إشارة)
- تقييم أداء كل استراتيجية
- risk management (position sizing calculator)

---

# ما هو Smart Alerts؟

إشعارات Telegram فورية عند حدوث events مهمة:
- إشارة radar جديدة (score ≥ 70 أو A-class)
- سهم في الـ watchlist وصل هدف/دعم/مقاومة
- تحذير stop loss لصفقة مفتوحة
- ملخص يومي آخر اليوم

## الفرق عن الموجود:
- الـ radar الحالي يرسل كل إشارة لتيليجرام — بدون filter
- Smart Alerts = filter ذكي: فقط الإشارات القوية أو المتعلقة بصفقاتك

---

# Phase A — Trading Journal Backend

## Package A1: Create journal_engine.py (ملف جديد)

### DB Tables (في life.db):

```sql
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    name_ar TEXT,
    direction TEXT NOT NULL DEFAULT 'long',  -- long/short
    status TEXT NOT NULL DEFAULT 'open',     -- open/closed/cancelled
    -- Entry
    entry_price REAL NOT NULL,
    entry_date TEXT NOT NULL,
    entry_reason TEXT,           -- "EMA cross bullish + RSI oversold"
    entry_signal_id INTEGER,     -- optional: link to radar signal
    quantity INTEGER DEFAULT 0,
    -- Exit
    exit_price REAL,
    exit_date TEXT,
    exit_reason TEXT,            -- "hit target" / "stop loss" / "manual"
    -- Calculated
    pnl_fils REAL,              -- profit/loss in fils
    pnl_pct REAL,               -- profit/loss %
    -- Metadata
    strategy TEXT,               -- "CLEANING V3" / "manual" / "radar"
    timeframe TEXT,              -- "30m" / "1D"
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(entry_date);
```

### Functions:

```python
# journal_engine.py

def open_trade(symbol, entry_price, quantity=0, entry_reason="", strategy="manual", timeframe="1D", direction="long", name_ar=""):
    """Open a new trade. Returns trade_id."""

def close_trade(trade_id, exit_price, exit_reason="manual"):
    """Close a trade. Calculates P&L. Returns updated trade dict."""

def cancel_trade(trade_id):
    """Cancel a trade (never executed)."""

def get_open_trades():
    """Get all open trades. Returns list of dicts."""

def get_recent_trades(limit=20):
    """Get recent trades (open + closed). Returns list of dicts."""

def get_trade_stats(days=30):
    """Get trading statistics. Returns dict with:
    - total_trades, open_trades, closed_trades
    - wins, losses, win_rate
    - avg_profit_pct, avg_loss_pct
    - total_pnl_fils, best_trade, worst_trade
    """

def get_trade(trade_id):
    """Get single trade by ID."""

def update_trade_notes(trade_id, notes):
    """Add/update notes on a trade."""
```

### Git: V12-A1: create journal_engine.py with trades table and core functions

---

## Package A2: Journal API Endpoints (server.py)

### Add endpoints:

```python
# POST /journal/open
# Body: {"symbol": "ZAIN", "entry_price": 566, "quantity": 1000, "entry_reason": "EMA bullish cross", "strategy": "radar", "timeframe": "1D"}
# Returns: {"ok": true, "trade_id": 1, "trade": {...}}

# POST /journal/close
# Body: {"trade_id": 1, "exit_price": 580, "exit_reason": "hit target"}
# Returns: {"ok": true, "trade": {..., "pnl_fils": 14000, "pnl_pct": 2.47}}

# GET /journal/open
# Returns: {"trades": [...], "count": 3}

# GET /journal/recent?limit=20
# Returns: {"trades": [...], "count": 20}

# GET /journal/stats?days=30
# Returns: {"total_trades": 15, "win_rate": 0.6, ...}
```

### Git: V12-A2: add journal API endpoints to server.py

---

## Package A3: Telegram Commands

### Add commands:

```
/trade ZAIN 566 1000 EMA bullish
  → فتح صفقة: ZAIN @ 566 × 1000 — EMA bullish
  → يرجع: ✅ صفقة #1 مفتوحة: ZAIN @ 566 × 1000

/close 1 580 hit target
  → إغلاق صفقة #1 @ 580
  → يرجع: ✅ صفقة #1 مغلقة: ZAIN @ 566→580 (+2.47%) — hit target

/trades
  → يعرض الصفقات المفتوحة

/journal
  → يعرض آخر 10 صفقات + إحصائيات
```

### Git: V12-A3: add TG journal commands

---

# Phase B — Smart Alerts Backend

## Package B1: Smart Alert Filter (server.py)

### المبدأ:
الـ radar loop الحالي يرسل كل إشارة. نضيف filter:

```python
def should_alert(signal):
    """Decide if a radar signal deserves a TG alert."""
    # Always alert for A-class
    if signal.get("score_class") == "A":
        return True, "🔴 A-class signal"
    # Alert for B-class with bullish cross
    if signal.get("score_class") == "B" and signal.get("type") == "bullish_cross":
        return True, "🟡 B-class bullish"
    # Alert if symbol is in open trades (stop loss warning)
    open_symbols = [t["symbol"] for t in get_open_trades()]
    if signal.get("symbol") in open_symbols:
        return True, "⚠️ Open position alert"
    # Alert if symbol is in watchlist with high score
    if signal.get("score", 0) >= 70:
        return True, "📊 High score signal"
    return False, ""
```

### التعديل في radar loop:
بدل إرسال كل إشارة → فلتر عبر `should_alert()` أولاً.

### Git: V12-B1: add smart alert filter to radar loop

---

## Package B2: Daily Trading Summary (TG)

### إضافة تقرير يومي آخر اليوم (6:30 PM بعد إغلاق السوق):

```python
async def daily_trading_summary():
    """Generate end-of-day trading summary."""
    stats = get_trade_stats(days=1)
    open_trades = get_open_trades()
    
    lines = ["📊 *ملخص التداول اليومي*\n"]
    
    if open_trades:
        lines.append(f"📂 صفقات مفتوحة: {len(open_trades)}")
        for t in open_trades:
            # Calculate unrealized P&L from latest price
            lines.append(f"  • {t['name_ar']} @ {t['entry_price']} — {t['strategy']}")
    
    if stats["closed_trades"] > 0:
        lines.append(f"\n✅ مغلقة اليوم: {stats['closed_trades']}")
        lines.append(f"📈 Win rate: {stats['win_rate']:.0%}")
        lines.append(f"💰 P&L: {stats['total_pnl_fils']:+.0f} فلس")
    
    return "\n".join(lines)
```

### Scheduler: كل يوم 6:30 PM (بعد إغلاق بورصة الكويت)

### Git: V12-B2: add daily trading summary to TG at market close

---

# Phase C — Dashboard

## Package C1: Journal Section in Trading Page

### الملف: master_ai_dashboard.yaml (sub-radar)

### إضافة endpoint في /dashboard/radar:
```python
# أضف في radar endpoint response:
"journal_open": get_open_trades(),
"journal_stats": get_trade_stats(days=30),
```

### إضافة في configuration.yaml (json_attributes):
```yaml
- journal_open
- journal_stats
```

### إضافة كارت في صفحة التداول (بعد Watchlist, قبل Diagnostics):

```yaml
# ── JOURNAL: OPEN POSITIONS ──
- type: markdown
  card_mod:
    style: |
      ha-card {
        background: rgba(39,174,96,0.04);
        border: 1px solid rgba(39,174,96,0.10);
        border-right: 3px solid rgba(39,174,96,0.30);
        border-radius: 0;
        padding: 14px 16px;
        margin: 10px 8px 0;
      }
      ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
  content: |
    {% set r = 'sensor.master_ai_radar' %}
    {% set trades = state_attr(r,'journal_open') %}
    {% set stats = state_attr(r,'journal_stats') %}
    {% if trades and trades | length > 0 %}
    **📂 صفقات مفتوحة** ({{ trades | length }})

    | السهم | الدخول | الكمية | السبب | الاستراتيجية |
    |:------|------:|------:|:------|:------------|
    {% for t in trades %}| {{ t.name_ar | default(t.symbol) }} | {{ t.entry_price }} | {{ t.quantity }} | {{ t.entry_reason[:20] | default('—') }} | {{ t.strategy | default('—') }} |
    {% endfor %}

    {% if stats %}
    📊 آخر 30 يوم: {{ stats.total_trades | default(0) }} صفقة · {{ (stats.win_rate | default(0) * 100) | round(0) }}% فوز · {{ stats.total_pnl_fils | default(0) | round(0) }} فلس P&L
    {% endif %}
    {% else %}
    📂 لا صفقات مفتوحة — استخدم /trade لفتح صفقة
    {% endif %}
```

### Git: V12-C1: add journal section to trading dashboard

---

# Execution Order

```
Phase A (Backend — يحتاج apply_text_patch.py):
A1 → A2 → A3 → اختبار عبر /trade + /trades + /journal
(ملف جديد → endpoints → TG commands)

Phase B (Smart Alerts):
B1 → B2 → اختبار عبر radar cycle
(filter → daily summary)

Phase C (Dashboard):
C1 → اختبار بصري
(journal section)
```

---

# Claude Code Instructions

## لـ A1:
```
1. أنشئ journal_engine.py (ملف جديد بـ /home/pi/master_ai/)
2. أضف DB schema + init_schema
3. أضف كل الـ functions
4. quick_check.py
5. اختبر: python3 -c "from journal_engine import init_schema; init_schema(); print('OK')"
6. git commit
```

## لـ A2:
```
1. في server.py: أضف import journal_engine
2. أضف 5 endpoints (POST /journal/open, POST /journal/close, GET /journal/open, GET /journal/recent, GET /journal/stats)
3. أضف journal_open + journal_stats في /dashboard/radar endpoint
4. استخدم apply_text_patch.py
5. quick_check + smoke_test
6. git commit + restart
```

## لـ A3:
```
1. في server.py tg_handle_command: أضف /trade, /close, /trades, /journal
2. استخدم apply_text_patch.py
3. quick_check
4. git commit + restart
5. اختبر من Telegram
```

## لـ B1:
```
1. أضف should_alert() function
2. عدّل radar alert sending لتمر عبر الفلتر
3. apply_text_patch.py
4. git commit + restart
```

## لـ B2:
```
1. أضف daily_trading_summary() function
2. أضف scheduler loop (6:30 PM Kuwait time = 15:30 UTC)
3. apply_text_patch.py
4. git commit + restart
```

## لـ C1:
```
1. حدّث configuration.yaml: أضف journal_open + journal_stats لـ radar sensor json_attributes
2. عدّل master_ai_dashboard.yaml: أضف Journal card
3. YAML validate + git commit + YAML reload
```

## ما لا يُلمس:
- لا تعدل DB schema الموجود (أضف جدول جديد فقط)
- لا تعدل radar_daily_context أو radar_recent_signals
- لا تعدل الصفحات الأخرى
- لا تكسر endpoints الحالية

---

# Acceptance Criteria

## بعد Phase A:
- [ ] /trade ZAIN 566 1000 يفتح صفقة
- [ ] /close 1 580 يغلق صفقة ويحسب P&L
- [ ] /trades يعرض الصفقات المفتوحة
- [ ] /journal يعرض إحصائيات
- [ ] API endpoints تشتغل

## بعد Phase B:
- [ ] إشارات A-class فقط ترسل TG alert
- [ ] صفقة مفتوحة على سهم فيه إشارة → alert
- [ ] ملخص يومي 6:30 PM

## بعد Phase C:
- [ ] صفحة التداول تعرض الصفقات المفتوحة كجدول
- [ ] إحصائيات 30 يوم ظاهرة

## المعيار النهائي:
- [ ] أقدر أسجل صفقة من Telegram وأشوفها بالداشبورد
- [ ] الإشعارات ذكية — ما تزعجني بكل إشارة
