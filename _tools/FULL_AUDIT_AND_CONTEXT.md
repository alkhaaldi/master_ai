# FULL AUDIT + CONTEXT UPDATE — Claude Code Task
# Date: 2026-03-27
# Priority: HIGH
# Scope: Comprehensive audit of all trading platform work + update CLAUDE_CONTEXT.md

## TASK 1: Full System Audit

Run a complete audit of everything built today. Check each component and report status.

### A) Master AI Health
```bash
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
python3 _tools/db_sanity.py
```

### B) Trading Platform HTML Pages
Test each page loads and returns 200:
```bash
for page in radar signals positions journal brain; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/trading/$page)
  SIZE=$(curl -s http://localhost:9000/trading/$page | wc -c)
  echo "$page: HTTP $STATUS ($SIZE bytes)"
done
```

### C) API Endpoints
Test each endpoint returns valid JSON:
```bash
KEY=$(cat /home/pi/.master_ai_key)
for ep in /dashboard/signals /dashboard/portfolio /dashboard/journal /dashboard/brain /api/symbols; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "X-API-Key: $KEY" http://localhost:9000$ep)
  echo "$ep: HTTP $STATUS"
done
```

Also test the trade management endpoints exist:
```bash
# These should return 422 (validation error) not 404
for ep in /api/trade/open /api/trade/close /api/trade/update; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{}' http://localhost:9000$ep)
  echo "$ep: HTTP $STATUS (expect 422 or 200)"
done
```

### D) Database Tables
Check all new tables exist and have correct schema:
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('data/life.db')
c = conn.cursor()

# Check tables exist
tables = ['trades', 'stock_radar_daily', 'confluence_signals', 'confluence_decisions',
          'signal_snapshots', 'indicator_performance', 'brain_weekly_reports']
for t in tables:
    c.execute(f'SELECT COUNT(*) FROM {t}')
    count = c.fetchone()[0]
    print(f'{t}: {count} rows')

# Check trades table has new columns
c.execute('PRAGMA table_info(trades)')
cols = [r[1] for r in c.fetchall()]
print(f'\ntrades columns: {cols}')

# Check open positions
c.execute('SELECT id, symbol, entry_price, quantity, status FROM trades WHERE status=\"open\"')
for row in c.fetchall():
    print(f'OPEN: id={row[0]} {row[1]} entry={row[2]} qty={row[3]}')

conn.close()
"
```

### E) Trading Brain Status
```bash
curl -s http://localhost:9000/dashboard/brain | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('Brain active:', d.get('brain_active'))
print('Total tracked:', d.get('total_tracked'))
print('Indicators:', len(d.get('indicator_weights', {})))
for name, info in d.get('indicator_weights', {}).items():
    print(f'  {name}: weight={info.get(\"weight\")} hit_rate={info.get(\"hit_rate\")} signals={info.get(\"signals\")}')
"
```

### F) HA Dashboard YAML
Check all iframe URLs point to correct external URL:
```bash
grep -n 'url:.*trading' /var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml
```
All should show `https://ai.salem-home.com/trading/...`

### G) Git Status
```bash
cd /home/pi/master_ai
git log --oneline -10
git status
```

### H) File Inventory
```bash
echo "=== Trading HTML ==="
ls -la www/trading/
echo ""
echo "=== New Python files ==="
ls -la trading_brain.py signal_tracker.py indicator_scorecard.py decision_journal.py trade_api.py 2>/dev/null
echo ""
echo "=== Core files size ==="
wc -l server.py dashboard_api.py journal_engine.py signal_engine.py trading_brain.py 2>/dev/null
```

## TASK 2: Update CLAUDE_CONTEXT.md

After the audit, update CLAUDE_CONTEXT.md to reflect ALL new components built today.

### Add these sections:

#### Trading Platform (HTML)
```
Trading Platform v2: 5 professional HTML pages served from /www/trading/
  - radar.html (30KB) — Command Center: ticker strip, signal filters, hero decision card, opportunities table, mini positions
  - signals.html (32KB) — Signal Matrix: 18-column sortable table, search/filter, indicator legend
  - positions.html (46KB) — Position Management: add/close/edit trades, signal health alerts, P&L with fees
  - journal.html (24KB) — Performance Review: pulse stats, open/closed trades, monthly stats, best/worst, period comparison
  - brain.html (24KB) — Trading Brain: indicator weights, evaluation history, learning status
  
Design: Boursa Kuwait institutional dark navy (#070D17) + gold (#C6974B), Tajawal + Noto Kufi Arabic + IBM Plex Mono
All pages: responsive, RTL Arabic, auto-refresh 120s, shared nav bar, Kuwait time clock
Served via /trading/{page} route in modules/panel.py
HA dashboard: each page displayed via iframe card in corresponding sub-page
```

#### Trade Management API
```
Trade API endpoints (in dashboard_api.py):
  POST /api/trade/open — Open new trade (symbol, entry_price, quantity, strategy, stop_loss, take_profit)
  POST /api/trade/close — Close trade (trade_id, exit_price, reason)
  POST /api/trade/update — Update SL/TP (trade_id, stop_loss, take_profit)
  GET /api/symbols — List all 128 tracked symbols

P&L Calculation: 2-layer pricing (bridge cache → stock_radar_daily fallback)
  Each position includes: pnl_pct, pnl_kwd, fees_kwd, net_pnl_kwd, quote_source, quote_stale
  Broker fee: 0.125% per transaction (0.25% round trip)

Signal Health Alerts on positions:
  - confluence < 40 → "بيع — confluence ضعيف" (danger)
  - RSI divergence bearish → "مراجعة — divergence سلبي" (warning)
  - Price below stop_loss → "بيع فوراً" (danger)
  - Bearish MACD + confluence < 50 → "مراجعة — momentum سلبي" (warning)
```

#### Trading Brain
```
Trading Brain (trading_brain.py, 666 lines):
  - TRACK: snapshot_signals() every 2h during market (Sun-Thu 9-13 KWT)
  - EVALUATE: evaluate_pending_signals() daily 13:30 KWT
  - LEARN: update_indicator_performance() after each evaluation
  - ADJUST: adjust_weights() weekly Sunday
  - REPORT: generate_weekly_report() Friday 14:00 KWT → Telegram

  7 indicators tracked: RSI, MACD, EMA, ADX, VOL, STOCH, OBV
  Adaptive weight formula: new_weight = base_weight × (0.5 + rolling_hit_rate_50)
  Weight range: 0.3 (terrible) → 2.0 (excellent)
  Minimum 30 signals before adjustment

  DB tables: signal_snapshots, indicator_performance, brain_weekly_reports
  Endpoint: GET /dashboard/brain
  Dashboard: /trading/brain (brain.html)
```

#### OPEN_PATHS update
```
OPEN_PATHS now includes:
  /trading, /trading/*, /dashboard/signals, /dashboard/portfolio, /dashboard/journal, /dashboard/brain,
  /api/trade/open, /api/trade/close, /api/trade/update, /api/symbols
```

#### HA Dashboard Trading Pages
```
HA Dashboard trading pages (iframe cards):
  sub-radar → iframe https://ai.salem-home.com/trading/radar
  sub-signals → iframe https://ai.salem-home.com/trading/signals
  sub-positions → iframe https://ai.salem-home.com/trading/positions
  sub-journal → iframe https://ai.salem-home.com/trading/journal
  sub-brain → iframe https://ai.salem-home.com/trading/brain
  
Home page nav: 9 buttons (added العقل/brain)
```

### IMPORTANT
- Read the current CLAUDE_CONTEXT.md first
- Don't remove existing content — ADD the new sections
- Keep it concise and factual
- After updating, commit: git commit -m "docs: update CLAUDE_CONTEXT.md with trading platform v2 + brain + trade management"
