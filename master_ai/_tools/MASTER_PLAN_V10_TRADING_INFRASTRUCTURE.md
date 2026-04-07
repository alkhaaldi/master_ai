# ═══════════════════════════════════════════════
# المرحلة 2: محرك إدارة المراكز + التنبيهات
# ═══════════════════════════════════════════════

## 2.1 — محرك المراكز

### الهدف:
متابعة المراكز المفتوحة يومياً وإرسال تنبيهات عند:
- ضرب الستوب
- تحقيق الهدف الأول
- تحقيق الهدف الثاني
- المركز ما تحرّك 7 أيام
- السعر قفز تحت الستوب (gap down)

### الملف الجديد:
```
position_engine.py
```

### تحسين جدول الصفقات الموجود: `journal_trades`

أضف الأعمدة التالية (ALTER TABLE):
```sql
ALTER TABLE journal_trades ADD COLUMN target_1 REAL;
ALTER TABLE journal_trades ADD COLUMN target_2 REAL;
ALTER TABLE journal_trades ADD COLUMN target_1_hit BOOLEAN DEFAULT 0;
ALTER TABLE journal_trades ADD COLUMN target_2_hit BOOLEAN DEFAULT 0;
ALTER TABLE journal_trades ADD COLUMN target_1_hit_date DATE;
ALTER TABLE journal_trades ADD COLUMN target_2_hit_date DATE;
ALTER TABLE journal_trades ADD COLUMN stop_hit BOOLEAN DEFAULT 0;
ALTER TABLE journal_trades ADD COLUMN stop_hit_date DATE;
ALTER TABLE journal_trades ADD COLUMN trailing_stop REAL;
ALTER TABLE journal_trades ADD COLUMN original_stop REAL;
ALTER TABLE journal_trades ADD COLUMN strategy_tag TEXT;
ALTER TABLE journal_trades ADD COLUMN sector TEXT;
ALTER TABLE journal_trades ADD COLUMN data_quality_at_entry INTEGER;
ALTER TABLE journal_trades ADD COLUMN last_monitored DATETIME;
```

### الجدول الجديد: `position_alerts`
```sql
CREATE TABLE IF NOT EXISTS position_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    alert_type TEXT NOT NULL,    -- 'stop_hit' / 'target_1_hit' / 'target_2_hit' / 
                                -- 'stale_position' / 'gap_below_stop' / 'breakeven_set'
    alert_data TEXT,             -- JSON مع التفاصيل
    sent_via TEXT,               -- 'telegram' / 'dashboard'
    sent_at DATETIME,
    acknowledged BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trade_id) REFERENCES journal_trades(id)
);
```

### المنطق الرئيسي:
```python
class PositionEngine:
    """
    يُشغّل مرتين يومياً:
    1. بعد إغلاق السوق (2 PM) — فحص شامل
    2. أثناء السوق إذا البردج شغّال (كل 15 دقيقة) — فحص سريع
    """
    
    def daily_monitor(self):
        """الفحص اليومي الشامل بعد الإغلاق"""
        open_trades = get_open_trades()
        
        for trade in open_trades:
            price = get_latest_price(trade.symbol)
            if not price:
                continue
            
            alerts = []
            
            # 1. فحص الستوب
            stop = trade.trailing_stop or trade.stop_loss
            if stop and price <= stop:
                alerts.append({
                    'type': 'stop_hit',
                    'msg_ar': f'⛔ {trade.symbol} ضرب الستوب! السعر {price} تحت الستوب {stop}',
                    'action_ar': 'بيع فوراً',
                    'urgency': 'critical',
                })
            
            # 2. فحص gap تحت الستوب
            if stop and price < stop * 0.97:  # أكثر من 3% تحت الستوب
                alerts.append({
                    'type': 'gap_below_stop',
                    'msg_ar': f'🔴 {trade.symbol} قفز تحت الستوب! السعر {price} بعيد عن الستوب {stop}',
                    'urgency': 'critical',
                })
            
            # 3. فحص الهدف الأول
            if trade.target_1 and not trade.target_1_hit and price >= trade.target_1:
                alerts.append({
                    'type': 'target_1_hit',
                    'msg_ar': f'🎯 {trade.symbol} وصل الهدف الأول! السعر {price} ≥ الهدف {trade.target_1}',
                    'action_ar': 'بيع نص أو رفع الستوب لسعر الدخول',
                    'urgency': 'high',
                })
                mark_target_hit(trade.id, target=1)
                
                # رفع الستوب لسعر الدخول تلقائياً (breakeven)
                if not trade.trailing_stop or trade.trailing_stop < trade.entry_price:
                    update_trailing_stop(trade.id, trade.entry_price)
                    alerts.append({
                        'type': 'breakeven_set',
                        'msg_ar': f'🔒 {trade.symbol} الستوب ارتفع لسعر الدخول {trade.entry_price}',
                        'urgency': 'info',
                    })
            
            # 4. فحص الهدف الثاني
            if trade.target_2 and not trade.target_2_hit and price >= trade.target_2:
                alerts.append({
                    'type': 'target_2_hit',
                    'msg_ar': f'🏆 {trade.symbol} وصل الهدف الثاني! السعر {price} ≥ الهدف {trade.target_2}',
                    'action_ar': 'بيع الباقي أو trailing stop',
                    'urgency': 'high',
                })
                mark_target_hit(trade.id, target=2)
            
            # 5. فحص الجمود (ما تحرّك 7 أيام)
            days_held = (today - trade.entry_date).days
            if days_held >= 7 and abs(price - trade.entry_price) / trade.entry_price < 0.02:
                alerts.append({
                    'type': 'stale_position',
                    'msg_ar': f'⏰ {trade.symbol} ما تحرّك {days_held} يوم — راجع المركز',
                    'urgency': 'low',
                })
            
            # إرسال التنبيهات
            for alert in alerts:
                save_alert(trade.id, trade.symbol, alert)
                await send_telegram_alert(alert)
            
            # تحديث P&L
            update_position_pnl(trade.id, price)
            mark_monitored(trade.id)
    
    def get_portfolio_summary(self):
        """ملخص المحفظة — يستخدم في Dashboard"""
        trades = get_open_trades()
        total_invested = sum(t.entry_price * t.quantity for t in trades)
        total_current = sum(get_latest_price(t.symbol) * t.quantity for t in trades)
        total_pnl = total_current - total_invested
        
        return {
            'total_positions': len(trades),
            'total_invested_kwd': total_invested / 1000,
            'total_current_kwd': total_current / 1000,
            'total_pnl_kwd': total_pnl / 1000,
            'total_pnl_pct': (total_pnl / total_invested * 100) if total_invested > 0 else 0,
            'positions': [{
                'symbol': t.symbol,
                'entry': t.entry_price,
                'current': get_latest_price(t.symbol),
                'pnl_pct': ...,
                'stop': t.trailing_stop or t.stop_loss,
                'target_1': t.target_1,
                'target_1_hit': t.target_1_hit,
                'days_held': ...,
                'sector': t.sector,
            } for t in trades],
        }
```

## 2.2 — التنبيهات عبر تلقرام

### التكامل مع النظام الحالي:
النظام عنده أصلاً `tg_intent_router.py` وتلقرام شغّال.
نضيف نوع تنبيه جديد:

```python
# في tg_intent_router.py أو ملف جديد tg_position_alerts.py

async def send_position_alert(alert):
    """يرسل تنبيه مركز عبر تلقرام"""
    
    urgency_emoji = {
        'critical': '🚨',
        'high': '🎯',
        'low': '⏰',
        'info': 'ℹ️',
    }
    
    emoji = urgency_emoji.get(alert['urgency'], '📊')
    
    msg = f"{emoji} تنبيه مراكز\n\n"
    msg += alert['msg_ar'] + "\n"
    if 'action_ar' in alert:
        msg += f"\n✅ الإجراء: {alert['action_ar']}"
    
    await bot.send_message(chat_id, msg)
```

## 2.3 — Endpoint جديد للمراكز المحسّن

### `/api/portfolio-status`
```python
@app.get("/api/portfolio-status")
async def portfolio_status():
    engine = PositionEngine()
    summary = engine.get_portfolio_summary()
    alerts = get_unacknowledged_alerts()
    
    return {
        "portfolio": summary,
        "active_alerts": alerts,
        "last_monitored": get_last_monitor_time(),
    }
```

---


# ═══════════════════════════════════════════════
# المرحلة 2: محرك إدارة المراكز + التنبيهات
# ═══════════════════════════════════════════════

## 2.1 — محرك المراكز

### الهدف:
متابعة المراكز المفتوحة يومياً وإرسال تنبيهات تلقرام عند:
ضرب الستوب / تحقيق الهدف / المركز ما تحرّك / قفزة تحت الستوب

### الملف الجديد: `position_engine.py`

### تعديل جدول `journal_trades` — أضف أعمدة:
```sql
ALTER TABLE journal_trades ADD COLUMN target_1 REAL;
ALTER TABLE journal_trades ADD COLUMN target_2 REAL;
ALTER TABLE journal_trades ADD COLUMN target_1_hit BOOLEAN DEFAULT 0;
ALTER TABLE journal_trades ADD COLUMN target_2_hit BOOLEAN DEFAULT 0;
ALTER TABLE journal_trades ADD COLUMN stop_hit BOOLEAN DEFAULT 0;
ALTER TABLE journal_trades ADD COLUMN trailing_stop REAL;
ALTER TABLE journal_trades ADD COLUMN original_stop REAL;
ALTER TABLE journal_trades ADD COLUMN strategy_tag TEXT;
ALTER TABLE journal_trades ADD COLUMN sector TEXT;
ALTER TABLE journal_trades ADD COLUMN last_monitored DATETIME;
```

### جدول جديد: `position_alerts`
```sql
CREATE TABLE IF NOT EXISTS position_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    alert_data TEXT,
    sent_via TEXT DEFAULT 'telegram',
    sent_at DATETIME,
    acknowledged BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### المنطق — يشتغل يومياً بعد إغلاق السوق:
```python
class PositionEngine:
    def daily_monitor(self):
        for trade in get_open_trades():
            price = get_latest_price(trade.symbol)
            stop = trade.trailing_stop or trade.stop_loss
            
            # ستوب انضرب
            if stop and price <= stop:
                alert("stop_hit", f"⛔ {trade.symbol} ضرب الستوب! {price} ≤ {stop}")
            
            # هدف 1 تحقق
            if trade.target_1 and not trade.target_1_hit and price >= trade.target_1:
                alert("target_1_hit", f"🎯 {trade.symbol} وصل الهدف الأول!")
                # ارفع الستوب لسعر الدخول (breakeven)
                update_trailing_stop(trade.id, trade.entry_price)
            
            # هدف 2 تحقق
            if trade.target_2 and not trade.target_2_hit and price >= trade.target_2:
                alert("target_2_hit", f"🏆 {trade.symbol} وصل الهدف الثاني!")
            
            # جمود — ما تحرّك 7 أيام
            days = (today - trade.entry_date).days
            if days >= 7 and abs(price - trade.entry_price)/trade.entry_price < 0.02:
                alert("stale", f"⏰ {trade.symbol} ما تحرّك {days} يوم")
            
            update_pnl(trade.id, price)
```

### Endpoint: `GET /api/portfolio-status`
يرجع: عدد المراكز، إجمالي الربح/الخسارة، التنبيهات النشطة

---

# ═══════════════════════════════════════════════
# المرحلة 3: بوابة المخاطر + حماية من التركّز
# ═══════════════════════════════════════════════

## 3.1 — خريطة القطاعات

### الملف الجديد: `sector_map.py`

### جدول جديد: `symbol_metadata`
```sql
CREATE TABLE IF NOT EXISTS symbol_metadata (
    symbol TEXT PRIMARY KEY,
    name_ar TEXT,
    name_en TEXT,
    sector TEXT NOT NULL,       -- 'بنوك' / 'عقار' / 'صناعة' / 'خدمات' / 'طاقة' / 'اتصالات' / 'مالي' / 'استهلاكي'
    market TEXT DEFAULT 'premier', -- 'premier' / 'main' / 'auction'
    liquidity_tier TEXT,        -- 'high' / 'medium' / 'low'
    avg_daily_value REAL,       -- متوسط القيمة المتداولة يومياً (آخر 20 يوم)
    avg_daily_volume INTEGER,
    updated_at DATETIME
);
```

### البيانات الأولية — 128 سهم مصنّف بالقطاع:
```python
SECTOR_MAP = {
    # بنوك
    'NBK': 'بنوك', 'KFH': 'بنوك', 'CBK': 'بنوك', 'GBK': 'بنوك',
    'ABK': 'بنوك', 'KIB': 'بنوك', 'WARBA': 'بنوك', 'BURG': 'بنوك',
    'BOUBYAN': 'بنوك',
    
    # عقار
    'MABANEE': 'عقار', 'AAYANRE': 'عقار', 'NRE': 'عقار',
    'ALDEERA': 'عقار', 'URC': 'عقار',
    
    # اتصالات
    'ZAIN': 'اتصالات', 'STC': 'اتصالات', 'VIVA': 'اتصالات',
    
    # صناعة
    'NICBM': 'صناعة', 'ACICO': 'صناعة', 'CABLE': 'صناعة',
    'PAPCO': 'صناعة', 'PCEM': 'صناعة',
    
    # خدمات مالية
    'KAMCO': 'مالي', 'INOVEST': 'مالي', 'NINV': 'مالي',
    'KMEFIC': 'مالي', 'WETHAQ': 'مالي',
    
    # ... يُكمل لكل 128 سهم
}
```

## 3.2 — محرك المخاطر

### الملف الجديد: `risk_engine.py`

### المنطق:
```python
class RiskEngine:
    # الإعدادات
    MAX_SAME_SECTOR = 2        # ماكس سهمين من نفس القطاع في "ادخل"
    MAX_TOTAL_POSITIONS = 8    # ماكس 8 مراكز مفتوحة
    MIN_LIQUIDITY_VALUE = 5000 # حد أدنى 5000 دينار تداول يومي
    MAX_POSITION_SIZE_PCT = 20 # ماكس 20% من المحفظة بسهم واحد
    
    def apply_risk_gate(self, opportunities, open_positions):
        """
        يُطبّق بعد Smart Decision وقبل العرض النهائي.
        يعدّل أو يخفّض القرارات بناءً على:
        1. تركّز القطاع
        2. عدد المراكز
        3. السيولة
        4. التكرار مع مراكز موجودة
        """
        
        # حساب التركّز الحالي
        sector_count = {}
        for pos in open_positions:
            s = get_sector(pos.symbol)
            sector_count[s] = sector_count.get(s, 0) + 1
        
        enter_by_sector = {}
        
        for opp in opportunities:
            if opp['smart_decision'] != 'ENTER':
                continue
            
            sector = get_sector(opp['symbol'])
            
            # فحص 1: تركّز القطاع
            existing = sector_count.get(sector, 0)
            new_enters = enter_by_sector.get(sector, 0)
            if existing + new_enters >= self.MAX_SAME_SECTOR:
                opp['smart_decision'] = 'WAIT'
                opp['smart_decision_ar'] = '⏳ انتظر — تركّز بالقطاع'
                opp['smart_reason_ar'] = f'عندك {existing} مركز بقطاع {sector} — تركّز زايد'
                opp['risk_flag'] = 'sector_concentration'
                continue
            
            # فحص 2: عدد المراكز الكلي
            if len(open_positions) + sum(enter_by_sector.values()) >= self.MAX_TOTAL_POSITIONS:
                opp['smart_decision'] = 'WAIT'
                opp['smart_decision_ar'] = '⏳ انتظر — محفظة مليانة'
                opp['smart_reason_ar'] = f'عندك {len(open_positions)} مركز — الحد الأقصى {self.MAX_TOTAL_POSITIONS}'
                opp['risk_flag'] = 'max_positions'
                continue
            
            # فحص 3: سيولة
            avg_value = get_avg_daily_value(opp['symbol'])
            if avg_value and avg_value < self.MIN_LIQUIDITY_VALUE:
                opp['smart_decision'] = 'WAIT'
                opp['smart_decision_ar'] = '⏳ انتظر — سيولة ضعيفة'
                opp['smart_reason_ar'] = f'متوسط التداول اليومي {avg_value:.0f} دينار فقط'
                opp['risk_flag'] = 'low_liquidity'
                continue
            
            # فحص 4: هل السهم موجود بالمحفظة؟
            if any(p.symbol == opp['symbol'] for p in open_positions):
                opp['smart_decision'] = 'WAIT'
                opp['smart_decision_ar'] = '⏳ انتظر — عندك مركز'
                opp['smart_reason_ar'] = 'عندك مركز مفتوح بنفس السهم'
                opp['risk_flag'] = 'duplicate_position'
                continue
            
            # مرّ كل الفحوصات
            enter_by_sector[sector] = enter_by_sector.get(sector, 0) + 1
        
        return opportunities
```

### التكامل مع `/api/decisions-now`:
```python
# في نهاية scan_opportunities()، قبل الترتيب النهائي:

risk = RiskEngine()
open_positions = get_open_trades()
all_opportunities = risk.apply_risk_gate(all_opportunities, open_positions)
```

---


# ═══════════════════════════════════════════════
# المرحلة 4: سجل التدقيق + حلقة التعلم
# ═══════════════════════════════════════════════

## 4.1 — سجل تدقيق القرارات

### الهدف:
كل قرار يتسجّل عشان نعرف: لما النظام قال "ادخل" — هل كان صح ولا غلط؟

### جدول جديد: `decision_audit`
```sql
CREATE TABLE IF NOT EXISTS decision_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    decision_time DATETIME NOT NULL,
    market_date DATE NOT NULL,
    smart_decision TEXT NOT NULL,     -- 'ENTER' / 'WAIT' / 'SKIP'
    chosen_plan_source TEXT,          -- 'golden' / 'strategy'
    entry_price REAL,
    stop_price REAL,
    target_1 REAL,
    target_2 REAL,
    rr_ratio REAL,
    confidence REAL,
    data_quality INTEGER,
    data_freshness TEXT,
    sr_status TEXT,
    strategy_id TEXT,
    strategy_ev REAL,
    pattern_atoms TEXT,
    risk_flags TEXT,                  -- JSON: sector_concentration, low_liquidity, etc.
    -- النتيجة (تُملأ لاحقاً)
    outcome TEXT,                     -- 'hit_target1' / 'hit_target2' / 'stopped_out' / 'expired' / 'pending'
    outcome_date DATE,
    actual_gain_pct REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_audit_symbol ON decision_audit(symbol, market_date);
CREATE INDEX idx_audit_decision ON decision_audit(smart_decision);
```

### المنطق:
```python
# كل مرة يطلع قرار ENTER، يتسجّل:
def log_decision(opp, decision):
    insert_decision_audit(
        symbol=opp['symbol'],
        market_date=today,
        smart_decision=decision['action'],
        chosen_plan_source=decision['chosen_plan']['source'],
        entry_price=decision['chosen_plan']['entry'],
        stop_price=decision['chosen_plan']['stop'],
        target_1=decision['chosen_plan']['target1'],
        rr_ratio=decision['chosen_plan']['rr'],
        confidence=opp['confidence'],
        data_quality=opp.get('data_quality'),
        strategy_id=opp.get('strategy_match', {}).get('strategy_id'),
        strategy_ev=opp.get('strategy_match', {}).get('ev'),
    )
```

### حلقة التعلم (مستقبلية):
```
بعد 7 أيام من كل قرار ENTER:
  → شوف شنو صار بالسعر
  → هل وصل الهدف؟ هل ضرب الستوب؟
  → سجّل النتيجة
  → هالبيانات ترجع تغذّي Strategy Mining
```

---

# ═══════════════════════════════════════════════
# ترتيب التنفيذ — الجدول الزمني
# ═══════════════════════════════════════════════

## الأسبوع 1: بوابة جودة البيانات + S/R fallback
### Claude Code ينفذ:
1. إنشاء `data_integrity.py` — فحص الطزاجة + الجودة
2. تعديل `golden_engine.py` — إضافة بوابة الجودة قبل التقييم
3. إضافة fallback للدعم/المقاومة الفاضية
4. إضافة حقول `data_quality`, `data_freshness`, `sr_status` في النتائج
### Claude.ai ينفذ:
5. تحديث `decisions.html` — عرض حالة البيانات (طازة/قديمة/غير متوفرة)

## الأسبوع 2: محرك المراكز
### Claude Code ينفذ:
1. إنشاء `position_engine.py`
2. ALTER TABLE لإضافة الأعمدة الجديدة
3. إنشاء جدول `position_alerts`
4. تنبيهات تلقرام (stop_hit, target_hit, stale)
5. Endpoint: `/api/portfolio-status`
6. Cron job للفحص اليومي
### Claude.ai ينفذ:
7. تحديث `positions.html` — عرض التنبيهات + حالة الأهداف

## الأسبوع 3: بوابة المخاطر + القطاعات
### Claude Code ينفذ:
1. إنشاء `sector_map.py` — تصنيف 128 سهم
2. إنشاء `risk_engine.py` — قواعد التركّز والسيولة
3. إنشاء جدول `symbol_metadata`
4. تكامل مع `scan_opportunities()`
### Claude.ai ينفذ:
5. عرض القطاع + أعلام المخاطر في `decisions.html`

## الأسبوع 4: مصدر بيانات مستقل + سجل التدقيق
### Claude Code ينفذ:
1. إنشاء `kse_data_collector.py`
2. إنشاء جدول `daily_bars` + `data_fetch_runs`
3. إنشاء `decision_audit` table
4. ربط الكل مع بعض
### Claude.ai ينفذ:
5. صفحة النظام تعرض حالة البيانات + آخر جمع

---

# ═══════════════════════════════════════════════
# ملخص الملفات والجداول الجديدة
# ═══════════════════════════════════════════════

## ملفات Python جديدة (Claude Code ينفذ):
```
data_integrity.py          # بوابة جودة البيانات
position_engine.py         # محرك المراكز والتنبيهات
risk_engine.py             # بوابة المخاطر والتركّز
sector_map.py              # تصنيف القطاعات
kse_data_collector.py      # مجمّع البيانات اليومي
kse_source_primary.py      # مصدر البيانات الأول
```

## ملفات Python تُعدّل (Claude Code ينفذ):
```
golden_engine.py           # إضافة بوابات الجودة والمخاطر
server.py                  # إضافة endpoints جديدة
```

## جداول جديدة:
```
daily_bars                 # بيانات يومية تاريخية
data_fetch_runs            # سجل عمليات الجمع
position_alerts            # تنبيهات المراكز
symbol_metadata            # القطاع + السيولة + التصنيف
decision_audit             # سجل تدقيق القرارات
```

## جداول تُعدّل:
```
journal_trades             # + target_1, target_2, stop_hit, trailing_stop, sector
```

## صفحات HTML تُحدّث (Claude.ai ينفذ):
```
decisions.html             # + حالة البيانات + أعلام المخاطر + القطاع
positions.html             # + التنبيهات + الأهداف + trailing stop
system.html                # + حالة جمع البيانات
```

---

# ═══════════════════════════════════════════════
# ما لا نبنيه (حسب اتفاقنا مع ChatGPT)
# ═══════════════════════════════════════════════

- ❌ نظام ارتباطات معقد
- ❌ تنفيذ تلقائي للصفقات
- ❌ تحليل داخل اليوم
- ❌ ذكاء اصطناعي معقد للدعم/المقاومة
- ❌ محاكاة تنفيذ الأوامر
- ❌ نظام ضرائب/محاسبة
- ❌ طبقات شرح إضافية قبل إصلاح البيانات
