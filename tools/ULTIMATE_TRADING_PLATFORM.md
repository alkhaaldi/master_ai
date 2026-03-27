# Master AI v9.0 — Ultimate Trading Platform
> Goal: منصة تداول ذكية متكاملة — P&L حقيقي، إشارات متعددة الفريمات، تحليل ذكي
> TradingView Premium | 128 KSE stocks | بورصة الكويت

---

## ما يطلبه المستخدم:
1. حسبة P&L واضحة — نسبة مئوية + مبلغ بالدينار
2. إشارات EMA 9/21 على 30m + Daily مع MACD والحجم
3. جداول مفيدة فعلاً تساعد على اتخاذ القرار
4. اقتراحات ذكية لتحسين المنصة

## اقتراحاتي (كخبير):
5. Multi-Timeframe Confluence — لما 30m AND Daily كلهم bullish = إشارة قوية
6. Volume Spike Alert — لما الحجم يقفز 3x+ فوق المتوسط
7. P&L Tracker بالدينار الكويتي مع عمولة البروكر
8. Smart Watchlist — أسهم تقترب من مناطق مهمة (support/resistance)
9. Weekly Performance Report — تقرير أسبوعي شامل

---

## PRE-FLIGHT
```bash
cat CLAUDE.md
cat _tools/OPERATIONAL_ACCESS_MATRIX.md
cat _tools/ADDING_NEW_DASHBOARD_FIELDS.md
git add -A && git commit -m "backup: pre-v9.0 ultimate trading platform"
```

---

## PHASE 1: Enhanced P&L Tracking

### المشكلة:
- الحين P&L يعرض: entry=132, current=133, +0.76%
- المستخدم يبي: ربح بالدينار الكويتي، مع حساب العمولة

### الحل: تحسين journal_engine.py

أضف function `calculate_real_pnl()`:
```python
def calculate_real_pnl(entry_price_fils, current_price_fils, quantity, broker_fee_pct=0.125):
    """Calculate real P&L with broker commission.
    KSE broker fee: ~0.125% per trade (entry + exit = 0.25% total)
    Prices in fils. Returns dict with KWD and fils values.
    """
    entry_total_fils = entry_price_fils * quantity
    current_total_fils = current_price_fils * quantity
    
    # Broker fees (entry + estimated exit)
    entry_fee_fils = entry_total_fils * (broker_fee_pct / 100)
    exit_fee_fils = current_total_fils * (broker_fee_pct / 100)
    total_fees_fils = entry_fee_fils + exit_fee_fils
    
    # Net P&L
    gross_pnl_fils = current_total_fils - entry_total_fils
    net_pnl_fils = gross_pnl_fils - total_fees_fils
    
    # Convert to KWD
    gross_pnl_kwd = gross_pnl_fils / 1000
    net_pnl_kwd = net_pnl_fils / 1000
    entry_total_kwd = entry_total_fils / 1000
    current_total_kwd = current_total_fils / 1000
    
    # Percentages
    pnl_pct = ((current_price_fils / entry_price_fils) - 1) * 100 if entry_price_fils else 0
    net_pnl_pct = (net_pnl_fils / entry_total_fils) * 100 if entry_total_fils else 0
    
    return {
        "entry_total_kwd": round(entry_total_kwd, 3),
        "current_total_kwd": round(current_total_kwd, 3),
        "gross_pnl_fils": round(gross_pnl_fils),
        "gross_pnl_kwd": round(gross_pnl_kwd, 3),
        "net_pnl_fils": round(net_pnl_fils),
        "net_pnl_kwd": round(net_pnl_kwd, 3),
        "pnl_pct": round(pnl_pct, 2),
        "net_pnl_pct": round(net_pnl_pct, 2),
        "total_fees_kwd": round(total_fees_fils / 1000, 3),
        "broker_fee_pct": broker_fee_pct,
    }
```

### Wire into /dashboard/portfolio:
كل open position يرجع:
```json
{
  "symbol": "CLEANING",
  "entry_price": 132,
  "current_price": 133,
  "quantity": 792000,
  "pnl": {
    "entry_total_kwd": 104.544,
    "current_total_kwd": 105.336,
    "gross_pnl_kwd": 0.792,
    "net_pnl_kwd": 0.529,
    "pnl_pct": 0.76,
    "net_pnl_pct": 0.51,
    "total_fees_kwd": 0.263
  }
}
```

### Fix quantity:
```sql
UPDATE trades SET quantity = 792000 WHERE id = 1 AND symbol = 'CLEANING';
```

### Dashboard YAML — Portfolio page:
```
📊 CLEANING
الدخول: 132 فلس × 792,000 = 104.544 د.ك
الحالي: 133 فلس × 792,000 = 105.336 د.ك
━━━━━━━━━━━━━━━━
الربح الإجمالي: +0.792 د.ك (+0.76%)
العمولة: -0.263 د.ك
الربح الصافي: +0.529 د.ك (+0.51%)
```

### Validation:
```bash
python3 -c "
from journal_engine import calculate_real_pnl
r = calculate_real_pnl(132, 133, 792000)
print(f'Gross: {r[\"gross_pnl_kwd\"]} KWD ({r[\"pnl_pct\"]}%)')
print(f'Net: {r[\"net_pnl_kwd\"]} KWD ({r[\"net_pnl_pct\"]}%)')
print(f'Fees: {r[\"total_fees_kwd\"]} KWD')
"
```

```bash
git add -A && git commit -m "feat: real P&L with KWD amounts and broker fees"
```

---

## PHASE 2: Multi-Timeframe EMA + MACD + Volume

### المشكلة:
الرادار يراقب EMA 9/21 على 30m فقط. اليومي فيه بس daily snapshot (RSI + trend). ما فيه MACD. ما فيه confluence.

### الحل: توسيع الرادار ليشمل فريمين + MACD

#### 2A. أضف MACD calculation في stock_radar.py:
```python
def _compute_macd(closes, fast=12, slow=26, signal=9):
    """Calculate MACD, Signal, Histogram."""
    if len(closes) < slow + signal:
        return None
    ema_fast = _compute_ema(closes, fast)
    ema_slow = _compute_ema(closes, slow)
    
    # Build MACD line series
    macd_line = []
    for i in range(slow, len(closes)+1):
        ef = _compute_ema(closes[:i], fast)
        es = _compute_ema(closes[:i], slow)
        macd_line.append(ef - es)
    
    if len(macd_line) < signal:
        return None
    
    signal_line = _compute_ema(macd_line, signal)
    macd_current = macd_line[-1]
    histogram = macd_current - signal_line
    
    # MACD cross detection
    if len(macd_line) >= 2:
        prev_hist = macd_line[-2] - _compute_ema(macd_line[:-1], signal)
        if prev_hist <= 0 and histogram > 0:
            cross = "bullish"
        elif prev_hist >= 0 and histogram < 0:
            cross = "bearish"
        else:
            cross = "none"
    else:
        cross = "none"
    
    return {
        "macd": round(macd_current, 3),
        "signal": round(signal_line, 3),
        "histogram": round(histogram, 3),
        "cross": cross,
        "above_zero": macd_current > 0
    }
```

#### 2B. أضف Daily timeframe scan:
في `refresh_daily_snapshot()`, بالإضافة للبيانات الموجودة:
```python
# Get daily candles for MACD
from tv_data import get_price
daily = get_price(symbol, n_bars=50)  # Need 50 bars for MACD(12,26,9)
if daily and not daily.get("error"):
    closes = [daily["close"]]  # Need full series
    # Actually need to get full OHLCV series
    from tvDatafeed import Interval
    df = _get_tv().get_hist(symbol, "KSE", Interval.in_daily, n_bars=50)
    if df is not None and not df.empty:
        daily_closes = df["close"].tolist()
        macd_data = _compute_macd(daily_closes)
        
        # Daily EMA cross
        daily_ema9 = _compute_ema(daily_closes, 9)
        daily_ema21 = _compute_ema(daily_closes, 21)
        daily_ema_cross = "bullish" if daily_ema9 > daily_ema21 else "bearish"
```

#### 2C. أضف الحقول الجديدة في daily snapshot schema:
```python
# Add to stock_radar_daily table (ALTER or recreate):
# macd REAL, macd_signal REAL, macd_histogram REAL, macd_cross TEXT
# daily_ema9 REAL, daily_ema21 REAL, daily_ema_cross TEXT
# volume_avg_20 INTEGER, volume_spike BOOLEAN
```

#### 2D. Confluence Score:
```python
def _compute_confluence(signal_30m, daily_data):
    """Multi-timeframe confluence. Higher = stronger signal."""
    score = 0
    reasons = []
    
    # 30m EMA cross
    if signal_30m.get("ema_cross") == "bullish":
        score += 25
        reasons.append("30m EMA صاعد")
    elif signal_30m.get("ema_cross") == "bearish":
        score -= 25
        reasons.append("30m EMA هابط")
    
    # Daily EMA cross
    if daily_data.get("daily_ema_cross") == "bullish":
        score += 30
        reasons.append("Daily EMA صاعد")
    elif daily_data.get("daily_ema_cross") == "bearish":
        score -= 30
        reasons.append("Daily EMA هابط")
    
    # MACD daily
    if daily_data.get("macd_cross") == "bullish":
        score += 20
        reasons.append("MACD تقاطع صاعد")
    elif daily_data.get("macd_cross") == "bearish":
        score -= 20
        reasons.append("MACD تقاطع هابط")
    
    # MACD above/below zero
    if daily_data.get("macd_above_zero"):
        score += 10
        reasons.append("MACD فوق الصفر")
    else:
        score -= 10
    
    # Volume spike
    vol_ratio = daily_data.get("vol_ratio", 1)
    if vol_ratio >= 3:
        score += 15
        reasons.append(f"حجم ×{vol_ratio:.1f} (spike)")
    elif vol_ratio >= 2:
        score += 10
        reasons.append(f"حجم ×{vol_ratio:.1f}")
    
    # RSI
    rsi = daily_data.get("rsi", 50)
    if 40 <= rsi <= 60:
        score += 5  # neutral zone = room to move
    elif rsi > 70:
        score -= 10
        reasons.append("RSI تشبع شرائي")
    elif rsi < 30:
        score += 15
        reasons.append("RSI تشبع بيعي — فرصة")
    
    direction = "bullish" if score > 0 else "bearish" if score < 0 else "neutral"
    strength = "strong" if abs(score) >= 60 else "moderate" if abs(score) >= 30 else "weak"
    
    return {
        "confluence_score": score,
        "direction": direction,
        "strength": strength,
        "strength_ar": "قوي" if strength == "strong" else "متوسط" if strength == "moderate" else "ضعيف",
        "reasons": reasons
    }
```

### Wire into radar endpoint and daily snapshot:
كل سهم في daily_context يرجع:
```json
{
  "symbol": "ZAIN",
  "price": 566,
  "ema9_30m": 558.39, "ema21_30m": 549.94, "ema_cross_30m": "bullish",
  "ema9_daily": 555.2, "ema21_daily": 548.1, "ema_cross_daily": "bullish",
  "macd": 3.2, "macd_signal": 1.8, "macd_histogram": 1.4, "macd_cross": "none",
  "rsi": 64.1,
  "volume": 17397296, "avg_volume": 6717103, "vol_ratio": 2.59,
  "confluence": {"score": 75, "direction": "bullish", "strength_ar": "قوي", "reasons": ["30m EMA صاعد", "Daily EMA صاعد", "حجم ×2.6"]}
}
```

```bash
git add -A && git commit -m "feat: multi-timeframe EMA + MACD + confluence scoring"
```

---

## PHASE 3: Smart Signal Dashboard (sub-radar improvements)

### Redesign the Opportunities Table:
بدل الجدول الحالي (9 أعمدة مزدحمة)، 
اعرض جدول مفيد فعلاً:

```
| السهم | السعر | 30m | Daily | MACD | Vol | Score | الاتجاه |
|-------|-------|-----|-------|------|-----|-------|---------|
| ZAIN  | 566   | 📈  | 📈    | 📈   | ×2.6| 85/A  | 🟢 قوي صاعد |
| MRC   | 99.1  | 📈  | ➡️    | ➡️   | ×1.2| 75/B  | 🟡 صاعد     |
| ARGAN | 358   | 📉  | 📈    | 📉   | ×0.8| 40/C  | ⚪ متضارب   |
```

**الأعمدة المهمة:**
- 30m: EMA cross على نص ساعة (📈/📉/➡️)
- Daily: EMA cross على اليومي (📈/📉/➡️)
- MACD: MACD daily cross (📈/📉/➡️)
- Vol: نسبة الحجم للمتوسط
- Score: التقييم مع الحرف
- الاتجاه: Confluence direction + strength

**القاعدة:** لما 30m AND Daily كلهم صاعد + MACD صاعد = **🟢🟢🟢 فرصة قوية** → هالسهم يستاهل نظرة

### Signal Flash Table (30m):
بدل الجدول الحالي، أضف MACD:
```
| السهم | السعر | الوقت | EMA | MACD | Vol | Score | الحكم |
|-------|-------|-------|-----|------|-----|-------|-------|
| ALFTAQA | 283 | 06:33 | 🟢 | ➡️  | ×1.3| 35/C  | ⚪ ضعيف |
```

```bash
git add -A && git commit -m "feat: smart signal tables with multi-TF confluence"
```

---

## PHASE 4: New Page — سجل الصفقات (sub-journal)

### صفحة جديدة مخصصة لتاريخ الصفقات:

1. **Pulse Hero**: إجمالي الربح/الخسارة بالدينار + عدد الصفقات + نسبة الفوز
2. **Open Positions (detailed)**:
   ```
   📊 CLEANING — شراء
   الدخول: 132 فلس × 792,000 = 104.544 د.ك
   الحالي: 133 فلس × 792,000 = 105.336 د.ك
   الربح: +0.529 د.ك (+0.51%) بعد العمولة
   المدة: 1 يوم | الاستراتيجية: manual
   ```
3. **Closed Trades History**: آخر 20 صفقة مغلقة مع P&L لكل واحدة
4. **Monthly Stats**:
   ```
   | الشهر | صفقات | فوز | خسارة | الربح | Win% |
   | مارس  | 5     | 3   | 2     | +2.1  | 60%  |
   ```
5. **Best/Worst Trades**: أفضل وأسوأ صفقة بالدينار
6. **Signal Accuracy**: من الإشارات اللي أكدتها، كم واحدة ربحت؟

```bash
git add -A && git commit -m "feat: new journal page with detailed P&L in KWD"
```

---

## PHASE 5: Smart Alerts Page (sub-alerts) — اقتراح جديد

### صفحة تنبيهات ذكية:

1. **Volume Spike Alert**: أسهم حجمها قفز 3x+ عن المتوسط
   ```
   🔥 ZAIN — حجم ×2.6 (17.4M vs avg 6.7M) — حركة غير عادية
   🔥 MRC — حجم ×5.7 — انتبه! volume spike
   ```

2. **Near Support/Resistance**:
   ```
   📍 CLEANING قريب من الدعم 121.7 (حالي 133, -8.5%)
   📍 ARGAN قريب من المقاومة 584.7 (حالي 566, +3.3%)
   ```

3. **Multi-TF Confluence Alerts**:
   ```
   🟢🟢🟢 ZAIN — 30m صاعد + Daily صاعد + MACD صاعد = فرصة قوية
   🔴🔴🔴 BEYOUT — 30m هابط + Daily هابط + MACD هابط = ابتعد
   ```

4. **RSI Extremes**:
   ```
   ⚠️ ALFTAQA RSI 70.6 — تشبع شرائي، حذر
   💡 EKTTITAB RSI 28.3 — تشبع بيعي، فرصة محتملة
   ```

```bash
git add -A && git commit -m "feat: smart alerts page — volume spikes, S/R proximity, confluence, RSI extremes"
```

---

## PHASE 6: Weekly Performance Report

### ملخص أسبوعي يُرسل كل جمعة الساعة 2 PM:

```
📊 تقرير التداول الأسبوعي — 16-20 مارس 2026

📈 الأداء:
  صفقات: 5 (3 فوز, 2 خسارة) — 60% win rate
  الربح الصافي: +1.250 د.ك
  أفضل صفقة: ZAIN +0.8 د.ك
  أسوأ صفقة: MRC -0.3 د.ك

📡 الرادار:
  إشارات: 42 (30 صاعد, 12 هابط)
  أكدت: 5 (12% من الإشارات)
  الإشارات المؤكدة اللي ربحت: 3/5 (60%)

🏆 أفضل أسهم الأسبوع (بالنقاط):
  1. ZAIN — Score 85, Confluence +75
  2. MRC — Score 80, Confluence +60
  3. CLEANING — Score 75, Confluence +45

📊 ملاحظات ذكية:
  - حجم ZAIN كان مرتفع كل الأسبوع (×2.5 avg)
  - MACD تقاطع صاعد على 3 أسهم جديدة
  - السوق بشكل عام صاعد (65% من الإشارات bullish)
```

```bash
git add -A && git commit -m "feat: weekly performance report with signal accuracy"
```

---

## PHASE 7: Update All Dashboards + Navigation

### تحديث Home nav:
الحين 10 صفحات — Home nav فيه 7 أزرار. التداول يشمل 5 صفحات فرعية (radar, portfolio, analysis, journal, alerts). بدل إضافة أزرار، خل "التداول" يروح للرادار والباقي cross-nav داخلياً.

### Cross-navigation in all trading pages:
كل صفحة تداول فيها:
```
[الرادار] [المحفظة] [التحليل] [السجل] [التنبيهات] [الرئيسية]
```

### Add to radar endpoint:
الـ API endpoints الجديدة:
- `/dashboard/portfolio` — P&L with KWD + fees (تحسين الموجود)
- `/dashboard/analysis` — + MACD + confluence data (تحسين الموجود)
- `/dashboard/journal` — NEW: detailed trade history + monthly stats
- `/dashboard/alerts` — NEW: volume spikes + S/R proximity + RSI extremes

### HA Sensors:
- `sensor.master_ai_journal` — 120s scan
- `sensor.master_ai_alerts` — 120s scan (أو 300s لأنها أثقل)

```bash
git add -A && git commit -m "feat: trading hub navigation + new endpoints"
```

---

## PHASE 8: Version Bump + Context

### 8A. VERSION = "9.0.0" (major — this is a platform rewrite)
### 8B. Update CLAUDE_CONTEXT.md
### 8C. Final validation

```bash
python3 _tools/quick_check.py && python3 _tools/smoke_test.py && python3 _tools/db_sanity.py
wc -l server.py dashboard_api.py stock_radar.py journal_engine.py
git add -A && git commit -m "v9.0.0: ultimate trading platform — multi-TF, MACD, P&L KWD, smart alerts, weekly report"
```

---

## EXECUTION ORDER
```
Phase 1: P&L with KWD + fees + fix quantity → test → commit
Phase 2: MACD + Daily EMA + Volume + Confluence → test → commit
Phase 3: Redesign signal tables → test → commit
Phase 4: New Journal page → test → commit
Phase 5: New Alerts page → test → commit
Phase 6: Weekly performance report → test → commit
Phase 7: Navigation + endpoints → test → commit
Phase 8: v9.0.0 + context → final commit
```

## RULES
- stock_radar.py: عبر _tools/patchers/apply_text_patch.py (حساس)
- dashboard_api.py: عبر _tools/patchers/apply_text_patch.py
- journal_engine.py: عبر _tools/patchers/apply_text_patch.py
- Dashboard YAML: مباشر
- DB schema changes: ALTER TABLE + migration
- test بعد كل phase
- git commit بعد كل phase
- الأسعار دائماً بالفلس داخلياً
- MACD: standard 12/26/9
- broker fee: 0.125% per trade
- tvDatafeed needs at least 50 bars for MACD calculation

## DB SCHEMA ADDITIONS
```sql
-- Add to stock_radar_daily (ALTER TABLE):
ALTER TABLE stock_radar_daily ADD COLUMN macd REAL;
ALTER TABLE stock_radar_daily ADD COLUMN macd_signal REAL;
ALTER TABLE stock_radar_daily ADD COLUMN macd_histogram REAL;
ALTER TABLE stock_radar_daily ADD COLUMN macd_cross TEXT DEFAULT 'none';
ALTER TABLE stock_radar_daily ADD COLUMN daily_ema9 REAL;
ALTER TABLE stock_radar_daily ADD COLUMN daily_ema21 REAL;
ALTER TABLE stock_radar_daily ADD COLUMN daily_ema_cross TEXT DEFAULT 'none';
ALTER TABLE stock_radar_daily ADD COLUMN confluence_score INTEGER DEFAULT 0;
ALTER TABLE stock_radar_daily ADD COLUMN confluence_direction TEXT DEFAULT 'neutral';
ALTER TABLE stock_radar_daily ADD COLUMN avg_volume INTEGER;
ALTER TABLE stock_radar_daily ADD COLUMN volume_spike BOOLEAN DEFAULT 0;
```

## ESTIMATED IMPACT
- stock_radar.py: +200 lines (MACD, confluence, daily EMA)
- journal_engine.py: +50 lines (P&L calculator)
- dashboard_api.py: +150 lines (2 new endpoints)
- Dashboard YAML: +2 new pages (~400 lines each)
- Total: ~1000 new lines
- New pages: sub-journal, sub-alerts (12 pages total)
