# Trading Dashboard Expansion — All TG Features on Dashboard
> Goal: كل ميزة تداول موجودة بالتلقرام تظهر على الداشبورد
> Current: 1 trading page (sub-radar) with 10 sections
> Plan: Expand to 3 trading subviews for better organization

---

## CURRENT STATE

### Trading TG Commands (15 commands):
| Command | What it does | On Dashboard? |
|---------|-------------|:---:|
| /stocks | Portfolio summary (positions + P&L) | ❌ |
| /price TICKER | Live price for any stock | ❌ |
| /trade TICKER buy/sell PRICE QTY | Record trade | ❌ (button only) |
| /close TICKER PRICE | Close position | ❌ |
| /trades | List all trades | ❌ |
| /journal | 30-day stats (win rate, P&L, count) | Partial (stats line) |
| /trade_review | Review signals vs executed trades | ❌ |
| /radar_toggle | Toggle radar on/off | ✅ button |
| /radar_status | Radar health | ✅ Pulse bar |
| /radar_top | Top signals | ✅ Opportunities table |
| /radar_last | Last signal | ✅ 30m signals |
| /tv_watchlist | TradingView watchlist | ✅ Watchlist grid |
| /tv_summary | TV alert summary | ❌ |
| /tv_stats | TV signal statistics | ❌ |
| /tv_last | Last TV alert | ❌ |
| /tv_sync | Sync TV from radar | ❌ (needs button) |

### Current Dashboard Page (sub-radar): 10 sections
1. Market Pulse Bar (status + last signal)
2. Quick Actions (4 buttons)
3. Stale Data Warning
4. Decision Card (top stock)
5. Opportunities Table (9 stocks)
6. 30m Signal Flash (10 signals)
7. Watchlist Grid (6 stocks)
8. Journal Open Positions
9. Diagnostics Footer
10. Command Feedback

### Data Available in /dashboard/radar:
- radar_enabled, radar_watch_count, radar_watchlist (12 items)
- radar_recent_signals (10 items)
- radar_alerts_today
- radar_daily_context (10 items with full data)
- daily_context_stale, daily_context_reason
- journal_open (1 trade), journal_stats (30-day)

### Data Available in DB but NOT on dashboard:
- **stock_radar_events** (25 signal history entries with score)
- **tv_alert_events** (2 TV webhook alerts)
- **tv_signal_stats** (per-ticker signal stats)
- **trades table** (exists but empty — will fill via confirmation buttons)
- **/stocks** portfolio (positions from life_stocks.py)

---

## PRE-FLIGHT
```bash
cat CLAUDE.md
cat _tools/OPERATIONAL_ACCESS_MATRIX.md
cat _tools/ADDING_NEW_DASHBOARD_FIELDS.md
sudo cp /var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml \
        /var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml.bak_v85
git add -A && git commit -m "backup: pre-trading-dashboard-expansion"
```

---

## ARCHITECTURE: 3 Trading Subviews

Instead of cramming everything into one page, split into 3 focused pages:

### Page 1: الرادار (sub-radar) — EXISTING, improved
**Purpose:** Real-time market monitoring + signals
**What stays:** Market Pulse, Decision Card, Opportunities Table, 30m Signals
**What's added:** Signal History section, improved Quick Actions

### Page 2: المحفظة (sub-portfolio) — NEW
**Purpose:** Portfolio management + trade journal + P&L tracking
**Shows:** Open positions with live P&L, closed trades history, 30-day stats, trade review

### Page 3: التحليل (sub-analysis) — NEW  
**Purpose:** TV alerts analysis + signal statistics + performance metrics
**Shows:** TV alert log, signal performance stats, radar accuracy, daily/weekly P&L chart

---

## PHASE 1: Backend — Add New API Endpoints

### 1A. Add `/dashboard/portfolio` endpoint
This returns portfolio + journal data for the new portfolio page.

```python
@router.get("/dashboard/portfolio")
async def ha_dashboard_portfolio():
    """Portfolio data for HA dashboard."""
    import sqlite3
    data = {}
    
    # Open positions with live P&L
    try:
        from journal_engine import get_open_trades, get_trade_stats, get_recent_trades
        open_trades = get_open_trades()
        # Enrich with current prices
        for t in open_trades:
            try:
                from tv_data import get_price, _normalize_price_to_fils
                p = get_price(t["symbol"])
                if p and "price" in p:
                    current = _normalize_price_to_fils(p["price"])
                    entry = float(t.get("entry_price", 0))
                    t["current_price"] = current
                    t["pnl_pct"] = round(((current / entry) - 1) * 100, 2) if entry else 0
                    t["pnl_fils"] = round((current - entry) * t.get("quantity", 0), 1)
            except:
                pass
        data["open_positions"] = open_trades
    except:
        data["open_positions"] = []
    
    # Closed trades (last 30 days)
    try:
        data["closed_trades"] = get_recent_trades(limit=20, status="closed")
    except:
        data["closed_trades"] = []
    
    # 30-day stats
    try:
        data["stats_30d"] = get_trade_stats(days=30)
    except:
        data["stats_30d"] = {}
    
    # 7-day stats
    try:
        data["stats_7d"] = get_trade_stats(days=7)
    except:
        data["stats_7d"] = {}
    
    # Trade review: signals sent vs confirmed
    try:
        conn = sqlite3.connect(str(DATA_DIR / "life.db"))
        # Radar signals last 7 days
        signals_7d = conn.execute(
            "SELECT COUNT(*) FROM stock_radar_events WHERE created_at > datetime('now', '-7 days')"
        ).fetchone()[0]
        # Confirmed trades last 7 days
        confirmed_7d = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE created_at > datetime('now', '-7 days')"
        ).fetchone()[0]
        data["signal_vs_trade"] = {
            "signals_7d": signals_7d,
            "confirmed_7d": confirmed_7d,
            "skip_rate": round((1 - confirmed_7d / max(signals_7d, 1)) * 100, 1)
        }
        conn.close()
    except:
        data["signal_vs_trade"] = {}
    
    return data
```

### 1B. Add `/dashboard/analysis` endpoint
```python
@router.get("/dashboard/analysis")
async def ha_dashboard_analysis():
    """Trading analysis data for HA dashboard."""
    import sqlite3
    data = {}
    
    # TV alert history
    try:
        conn = sqlite3.connect(str(DATA_DIR / "life.db"))
        rows = conn.execute(
            "SELECT ticker, price, signal, strategy_name, score, event_time "
            "FROM tv_alert_events ORDER BY id DESC LIMIT 20"
        ).fetchall()
        data["tv_alerts"] = [
            {"ticker": r[0], "price": r[1], "signal": r[2], "strategy": r[3], "score": r[4], "time": r[5]}
            for r in rows
        ]
    except:
        data["tv_alerts"] = []
    
    # Signal history (radar events)
    try:
        rows = conn.execute(
            "SELECT symbol, signal_type, price, score, created_at "
            "FROM stock_radar_events ORDER BY created_at DESC LIMIT 30"
        ).fetchall()
        data["signal_history"] = [
            {"symbol": r[0], "type": r[1], "price": r[2], "score": r[3], "time": r[4]}
            for r in rows
        ]
    except:
        data["signal_history"] = []
    
    # Signal stats per ticker
    try:
        rows = conn.execute(
            "SELECT ticker, strategy_name, signal_type, count_total, last_seen_at "
            "FROM tv_signal_stats ORDER BY count_total DESC LIMIT 20"
        ).fetchall()
        data["signal_stats"] = [
            {"ticker": r[0], "strategy": r[1], "signal_type": r[2], "count": r[3], "last_seen": r[4]}
            for r in rows
        ]
    except:
        data["signal_stats"] = []
    
    # Radar accuracy (signals that became profitable trades)
    try:
        # Count bullish signals where price went up
        total_bull = conn.execute(
            "SELECT COUNT(*) FROM stock_radar_events WHERE signal_type='bullish_cross'"
        ).fetchone()[0]
        data["radar_accuracy"] = {
            "total_signals": conn.execute("SELECT COUNT(*) FROM stock_radar_events").fetchone()[0],
            "bullish": total_bull,
            "bearish": conn.execute("SELECT COUNT(*) FROM stock_radar_events WHERE signal_type='bearish_cross'").fetchone()[0],
            "avg_score": conn.execute("SELECT AVG(score) FROM stock_radar_events").fetchone()[0]
        }
        conn.close()
    except:
        data["radar_accuracy"] = {}
    
    # Daily trading summary (if available)
    try:
        data["daily_summary"] = _get_cached_trading_summary()
    except:
        data["daily_summary"] = None
    
    return data
```

### 1C. Add these endpoints to configuration.yaml as HA sensors
```yaml
# In configuration.yaml REST sensors section, add:
- platform: rest
  resource: http://192.168.109.123:9000/dashboard/portfolio
  name: master_ai_portfolio
  scan_interval: 120
  headers:
    X-API-Key: !secret master_ai_key
  json_attributes:
    - open_positions
    - closed_trades
    - stats_30d
    - stats_7d
    - signal_vs_trade

- platform: rest
  resource: http://192.168.109.123:9000/dashboard/analysis
  name: master_ai_analysis
  scan_interval: 300
  headers:
    X-API-Key: !secret master_ai_key
  json_attributes:
    - tv_alerts
    - signal_history
    - signal_stats
    - radar_accuracy
    - daily_summary
```

**IMPORTANT:** Check if `master_ai_key` is in HA secrets.yaml. If not, add it.

### Validation:
```bash
python3 _tools/quick_check.py && python3 _tools/smoke_test.py
bash _tools/restart_master_ai.sh

# Test new endpoints
KEY=$(cat ~/.master_ai_key)
curl -s -H "X-API-Key: $KEY" http://localhost:9000/dashboard/portfolio | python3 -m json.tool | head -20
curl -s -H "X-API-Key: $KEY" http://localhost:9000/dashboard/analysis | python3 -m json.tool | head -20
```

```bash
git add -A && git commit -m "feat: add /dashboard/portfolio and /dashboard/analysis endpoints"
```

---

## PHASE 2: Improve Existing Radar Page (sub-radar)

### 2A. Add Signal History section (after 30m Signals)
Shows last 10 radar events from stock_radar_events table:
```yaml
# ── SIGNAL HISTORY ──
- type: markdown
  card_mod:
    style: |
      ha-card {
        background: rgba(180,120,255,0.04);
        border: 1px solid rgba(180,120,255,0.10);
        border-radius: 16px;
        padding: 10px 16px;
        margin: 10px 8px 0;
      }
      ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
  content: |
    {% set a = 'sensor.master_ai_analysis' %}
    {% set hist = state_attr(a,'signal_history') %}
    {% if hist and hist | length > 0 %}
    **📜 سجل الإشارات** (آخر {{ hist | length }})

    | السهم | النوع | السعر | Score | الوقت |
    |:------|:-----:|------:|:-----:|:-----:|
    {% for s in hist[:10] %}| {{ s.symbol }} | {% if s.type == 'bullish_cross' %}🟢{% else %}🔴{% endif %} | {{ s.price }} | {{ s.score }} | {{ s.time[-11:-3] if s.time | length > 11 else s.time }} |
    {% endfor %}
    {% else %}
    📜 لا سجل إشارات
    {% endif %}
```

### 2B. Improve Quick Actions — add /tv_sync button
Add 5th button for TV sync, or replace one of the existing 4:
```yaml
# Change grid to 5 columns or keep 4 and add tv_sync as separate button
```

### 2C. Add navigation to new pages
Add buttons at bottom to navigate to Portfolio and Analysis:
```yaml
- type: grid
  columns: 3
  square: false
  cards:
    - type: button
      name: المحفظة
      icon: mdi:wallet-outline
      tap_action:
        action: navigate
        navigation_path: /master-ai-dashboard/sub-portfolio
      show_state: false
    - type: button
      name: التحليل
      icon: mdi:chart-scatter-plot
      tap_action:
        action: navigate
        navigation_path: /master-ai-dashboard/sub-analysis
      show_state: false
    - type: button
      name: الرئيسية
      icon: mdi:home
      tap_action:
        action: navigate
        navigation_path: /master-ai-dashboard/master-ai
      show_state: false
```

```bash
git add -A && git commit -m "feat: improve radar page — signal history + navigation to portfolio/analysis"
```

---

## PHASE 3: New Portfolio Page (sub-portfolio)

### Structure:
1. **Pulse Hero** — Total P&L + open count + win rate
2. **Open Positions Cards** — Each position: symbol, entry, current, P&L %, quantity
3. **Signal vs Trade Stats** — Signals sent vs confirmed (skip rate)
4. **Closed Trades Table** — Last 20 closed trades with P&L
5. **30-Day Journal Stats** — Win rate, total trades, total P&L, avg hold time
6. **Quick Actions** — Record trade, close trade, review, home
7. **Command Feedback**

### YAML (new subview):
```yaml
- path: sub-portfolio
  title: المحفظة
  icon: mdi:wallet-outline
  subview: true
  type: panel
  cards:
    - type: vertical-stack
      cards:

        # ── PULSE HERO ──
        - type: markdown
          card_mod:
            style: |
              ha-card {
                background: linear-gradient(135deg, rgba(39,174,96,0.10), rgba(39,174,96,0.04));
                border: 1px solid rgba(39,174,96,0.12);
                border-radius: 18px;
                padding: 10px 16px 6px;
                margin: 6px 8px 0;
              }
              h2 { font-size: 18px !important; margin: 0 !important; }
              ha-markdown { font-size: 14px; opacity: 0.85; direction: rtl; }
          content: |
            ## المحفظة
            {% set p = 'sensor.master_ai_portfolio' %}
            {% set opens = state_attr(p,'open_positions') or [] %}
            {% set s30 = state_attr(p,'stats_30d') or {} %}
            📂 {{ opens | length }} صفقة مفتوحة · {{ s30.get('total_trades',0) }} صفقة (30 يوم) · {{ (s30.get('win_rate',0) * 100) | round(0) }}% فوز

        # ── OPEN POSITIONS ──
        - type: markdown
          card_mod:
            style: |
              ha-card {
                background: linear-gradient(135deg, rgba(39,174,96,0.06), rgba(39,174,96,0.02));
                border: 2px solid rgba(39,174,96,0.15);
                border-radius: 18px;
                padding: 14px 16px;
                margin: 10px 8px 0;
              }
              ha-markdown { font-size: 14px; direction: rtl; line-height: 1.9; }
          content: |
            {% set p = 'sensor.master_ai_portfolio' %}
            {% set trades = state_attr(p,'open_positions') or [] %}
            {% if trades | length > 0 %}
            **📂 صفقات مفتوحة** ({{ trades | length }})

            | السهم | الدخول | الحالي | P&L | الكمية | الاستراتيجية |
            |:------|------:|------:|----:|------:|:------------|
            {% for t in trades %}| {{ t.name_ar | default(t.symbol) }} | {{ t.entry_price }} | {{ t.current_price | default('—') }} | {% if t.pnl_pct is defined %}{% if t.pnl_pct >= 0 %}🟢 +{{ t.pnl_pct }}%{% else %}🔴 {{ t.pnl_pct }}%{% endif %}{% else %}—{% endif %} | {{ t.quantity }} | {{ t.strategy | default('—') }} |
            {% endfor %}
            {% else %}
            📂 لا صفقات مفتوحة — استخدم /trade أو اضغط "شريت" على إشارة الرادار
            {% endif %}

        # ── SIGNAL vs TRADE ──
        - type: grid
          columns: 3
          square: false
          cards:
            - type: markdown
              card_mod:
                style: |
                  ha-card { border-radius: 18px; padding: 12px 8px; text-align: center; }
                  ha-markdown { font-size: 14px; direction: rtl; }
              content: |
                {% set p = 'sensor.master_ai_portfolio' %}
                {% set svt = state_attr(p,'signal_vs_trade') or {} %}
                📡 **{{ svt.get('signals_7d',0) }}**

                إشارات 7 أيام
            - type: markdown
              card_mod:
                style: |
                  ha-card { border-radius: 18px; padding: 12px 8px; text-align: center; }
                  ha-markdown { font-size: 14px; direction: rtl; }
              content: |
                {% set p = 'sensor.master_ai_portfolio' %}
                {% set svt = state_attr(p,'signal_vs_trade') or {} %}
                ✅ **{{ svt.get('confirmed_7d',0) }}**

                صفقات منفذة
            - type: markdown
              card_mod:
                style: |
                  ha-card { border-radius: 18px; padding: 12px 8px; text-align: center; }
                  ha-markdown { font-size: 14px; direction: rtl; }
              content: |
                {% set p = 'sensor.master_ai_portfolio' %}
                {% set svt = state_attr(p,'signal_vs_trade') or {} %}
                ⏭ **{{ svt.get('skip_rate',0) }}%**

                نسبة التجاهل

        # ── CLOSED TRADES ──
        - type: markdown
          card_mod:
            style: |
              ha-card {
                background: rgba(255,255,255,0.02);
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 18px;
                padding: 14px 16px;
                margin: 10px 8px 0;
              }
              ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
          content: |
            {% set p = 'sensor.master_ai_portfolio' %}
            {% set closed = state_attr(p,'closed_trades') or [] %}
            {% if closed | length > 0 %}
            **📊 صفقات مغلقة** (آخر {{ closed | length }})

            | السهم | الدخول | الإغلاق | P&L | المدة |
            |:------|------:|------:|----:|:-----:|
            {% for t in closed[:10] %}| {{ t.symbol }} | {{ t.entry_price }} | {{ t.exit_price | default('—') }} | {% if t.pnl_pct is defined %}{% if t.pnl_pct >= 0 %}🟢{% else %}🔴{% endif %} {{ t.pnl_pct }}%{% else %}—{% endif %} | {{ t.hold_days | default('—') }}d |
            {% endfor %}
            {% else %}
            📊 لا صفقات مغلقة بعد
            {% endif %}

        # ── 30-DAY STATS ──
        - type: grid
          columns: 4
          square: false
          cards:
            - type: markdown
              card_mod:
                style: |
                  ha-card { background: rgba(39,174,96,0.05); border: 1px solid rgba(39,174,96,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                  ha-markdown { font-size: 14px; direction: rtl; }
              content: |
                {% set s = (state_attr('sensor.master_ai_portfolio','stats_30d') or {}) %}
                📊 **{{ s.get('total_trades',0) }}**

                صفقة
            - type: markdown
              card_mod:
                style: |
                  ha-card { background: rgba(39,174,96,0.05); border: 1px solid rgba(39,174,96,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                  ha-markdown { font-size: 14px; direction: rtl; }
              content: |
                {% set s = (state_attr('sensor.master_ai_portfolio','stats_30d') or {}) %}
                🎯 **{{ (s.get('win_rate',0) * 100) | round(0) }}%**

                فوز
            - type: markdown
              card_mod:
                style: |
                  ha-card { background: rgba(39,174,96,0.05); border: 1px solid rgba(39,174,96,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                  ha-markdown { font-size: 14px; direction: rtl; }
              content: |
                {% set s = (state_attr('sensor.master_ai_portfolio','stats_30d') or {}) %}
                💰 **{{ s.get('total_pnl_fils',0) | round(0) }}**

                فلس P&L
            - type: markdown
              card_mod:
                style: |
                  ha-card { border-radius: 18px; padding: 12px 8px; text-align: center; }
                  ha-markdown { font-size: 14px; direction: rtl; }
              content: |
                {% set s7 = (state_attr('sensor.master_ai_portfolio','stats_7d') or {}) %}
                📅 **{{ s7.get('total_trades',0) }}**

                هالأسبوع

        # ── QUICK ACTIONS ──
        - type: grid
          columns: 4
          square: false
          cards:
            - type: button
              name: الرادار
              icon: mdi:radar
              tap_action:
                action: navigate
                navigation_path: /master-ai-dashboard/sub-radar
              show_state: false
            - type: button
              name: التحليل
              icon: mdi:chart-scatter-plot
              tap_action:
                action: navigate
                navigation_path: /master-ai-dashboard/sub-analysis
              show_state: false
            - type: button
              name: مراجعة
              icon: mdi:clipboard-check-outline
              tap_action:
                action: call-service
                service: script.turn_on
                target:
                  entity_id: script.master_ai_trade_review
              show_state: false
            - type: button
              name: الرئيسية
              icon: mdi:home
              tap_action:
                action: navigate
                navigation_path: /master-ai-dashboard/master-ai
              show_state: false
```

### Scripts needed:
```yaml
# Add to scripts.yaml:
master_ai_trade_review:
  alias: "مراجعة التداول"
  sequence:
    - action: persistent_notification.create
      data:
        title: "🤖 Master AI"
        message: "⏳ مراجعة التداول..."
        notification_id: "master_ai_cmd"
    - action: rest_command.master_ai_tg_cmd
      continue_on_error: true
      data:
        command: "/trade_review"
    - action: persistent_notification.create
      data:
        title: "🤖 Master AI"
        message: "✅ تم تنفيذ: مراجعة التداول"
        notification_id: "master_ai_cmd"
```

```bash
git add -A && git commit -m "feat: new portfolio page (sub-portfolio) with open/closed trades + stats"
```

---

## PHASE 4: New Analysis Page (sub-analysis)

### Structure:
1. **Pulse Hero** — Total signals + avg score + radar accuracy
2. **Radar Accuracy Cards** — Bullish/Bearish counts + avg score
3. **Signal History Table** — Last 30 radar events
4. **TV Alert Log** — TradingView webhook alerts
5. **Signal Stats per Ticker** — Which stocks signal most
6. **Daily Summary** — Today's trading summary
7. **Navigation**

### YAML (similar structure to portfolio, using sensor.master_ai_analysis)

```bash
git add -A && git commit -m "feat: new analysis page (sub-analysis) with signal stats + TV alerts"
```

---

## PHASE 5: Update Home Page Navigation

### Add المحفظة and التحليل to home nav
Current nav has 7 buttons. We need to either:
- Expand to 9 (might be too many)
- OR replace the "التداول" single button with a dropdown-like approach
- OR keep nav at 7 but make "التداول" go to radar, and add sub-navigation within trading pages

**Recommended:** Keep 7 nav buttons on home. The trading pages have their own cross-navigation.

### Update Home Top Stock Teaser
Add portfolio P&L preview:
```yaml
# After stock teaser, add:
{% set p = 'sensor.master_ai_portfolio' %}
{% set opens = state_attr(p,'open_positions') or [] %}
{% if opens | length > 0 %}
📂 {{ opens | length }} صفقة · {{ total_pnl }}
{% endif %}
```

```bash
git add -A && git commit -m "feat: update home page with portfolio preview"
```

---

## PHASE 6: Version Bump + Context

### 6A. VERSION = "8.6.0"
### 6B. Update CLAUDE_CONTEXT.md
### 6C. Final validation

```bash
python3 _tools/quick_check.py && python3 _tools/smoke_test.py
# Test all endpoints
for ep in /dashboard /dashboard/extended /dashboard/radar /dashboard/portfolio /dashboard/analysis; do
  echo "=== $ep ==="
  curl -s -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000$ep | python3 -c "import json,sys; d=json.load(sys.stdin); print('OK -', len(d), 'keys')" 2>/dev/null
done
# Check dashboard renders
wc -l /var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml
git add -A && git commit -m "v8.6.0: trading dashboard expansion — 3 trading pages, portfolio + analysis"
```

---

## EXECUTION ORDER
```
Phase 1: Backend — /dashboard/portfolio + /dashboard/analysis + HA sensors
Phase 2: Improve radar page — signal history + navigation
Phase 3: New portfolio page (sub-portfolio)
Phase 4: New analysis page (sub-analysis)
Phase 5: Update home page
Phase 6: v8.6.0 + context
```

## RULES
- Follow _tools/ADDING_NEW_DASHBOARD_FIELDS.md workflow
- server.py/dashboard_api.py: via _tools/patchers/apply_text_patch.py
- Dashboard YAML: write directly (on RPi, UTF-8 is fine)
- configuration.yaml: check secrets.yaml for master_ai_key
- Test endpoints BEFORE writing dashboard YAML
- Test HA sensors BEFORE writing dashboard YAML
- git commit after each phase
