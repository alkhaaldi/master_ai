# TRADING PLATFORM BUILD — Claude Code Task
# Date: 2026-03-26
# Priority: HIGH
# Scope: 4 professional HTML pages + HA dashboard integration

## READ FIRST
1. Read CLAUDE.md
2. Read _tools/OPERATIONAL_ACCESS_MATRIX.md  
3. Read _tools/ADDING_NEW_DASHBOARD_FIELDS.md
4. Read this file completely before starting

---

## GOAL
Build a professional KSE (Kuwait Stock Exchange) trading platform as 4 standalone HTML pages,
served from Master AI and displayed inside HA dashboard via iframe cards.

Design language: **Boursa Kuwait institutional** — dark navy (#070D17) + gold (#C6974B) theme.
Font: Tajawal + Noto Kufi Arabic + IBM Plex Mono.
RTL Arabic with LTR numbers (unicode-bidi: isolate).

---

## CURRENT STATE

### Existing files to REFERENCE (design):
- `/home/pi/master_ai/www/trading.html` — current working single-page dashboard (KEEP as reference)

### Existing endpoints (ALL tested and working, NO changes needed):
```
GET /dashboard/signals    (OPEN — no auth needed)
  → market_open, bridge_online, bridge_cached_count, timestamp
  → decision_card: {symbol, name_ar, price, change_pct, verdict, verdict_key, trade_state, 
     confluence_score, ema_state, rsi_14, macd_state, macd_momentum, adx, vol_ratio, 
     support, resistance, atr_14, bb_squeeze, stoch_k, rsi_divergence, ema_cross, confluence_detail}
  → opportunities: list[10] (same fields as decision_card)
  → all_signals: list[11] (same fields)
  → open_positions: list[{symbol, name_ar, entry, current, pnl_pct, pnl_kwd, state, quantity, entry_date}]
  → signal_counts: {discovery, setup, ready, entered, manage}

GET /dashboard/radar      (needs X-API-Key)
  → radar_enabled, radar_watch_count (128)
  → radar_watchlist: list[12] {symbol, name_ar, price, change_pct, timeframe, watch_reason}
  → radar_recent_signals: list[10] {symbol, type, signal_type, price, time, timeframe, 
     ema_fast, ema_slow, strength, rsi, volume, score, verdict, support, resistance, vol_ratio}
  → radar_daily_context: list[10] {symbol, price, trend, rsi, support, resistance, score, 
     verdict, volume, vol_ratio, change_pct, macd, confluence, ...}
  → journal_open, journal_stats

GET /dashboard/portfolio  (needs X-API-Key)
  → open_positions: list[{id, symbol, name_ar, direction, status, entry_price, entry_date, 
     quantity, current_price, support, resistance, pnl}]
  → closed_trades: list[]
  → stats_30d, stats_7d: {total_trades, wins, losses, win_rate, avg_profit_pct, avg_loss_pct, total_pnl_fils}
  → signal_vs_trade: {signals_7d, confirmed_7d, skip_rate}

GET /dashboard/journal    (needs X-API-Key)
  → open_positions, closed_trades, stats_30d, stats_7d
  → portfolio_summary: {open_count, total_net_pnl_kwd, total_gross_pnl_kwd, total_fees_kwd}
  → monthly_stats, best_trade, worst_trade
```

### HA Dashboard (master_ai_dashboard.yaml at H:\ via Samba):
- sub-radar: Trading page (lines 310-615) — currently has iframe + native cards
- sub-signals: Signals page (lines 616-761)  
- sub-journal: Journal page (lines 2050-2247)

---

## WHAT TO BUILD

### File structure:
```
/home/pi/master_ai/www/trading/
  radar.html        ← Command Center (replaces sub-radar)
  signals.html      ← Signal Matrix + Deep Analysis
  positions.html    ← Position Management + Risk
  journal.html      ← Performance Review + Stats
```

### Shared across ALL pages:
- Same topbar: brand (KSE logo + "منصة التداول" + "Master AI") + status dots + clock + refresh button
- Same nav bar: 4 buttons (الرادار | الإشارات | المراكز | السجل) — current page highlighted
- Same color scheme (CSS variables)
- Same helper functions (formatters, badge generators)
- Auto-refresh every 120 seconds
- Kuwait time clock (Asia/Kuwait)
- Responsive (mobile + tablet + desktop)

### Page 1: radar.html — غرفة العمليات
**Question it answers: "وين الفرصة الحين؟"**
**Endpoint: /dashboard/signals (no auth)**

Layout:
1. Topbar + Status (market open/closed, bridge status)
2. Ticker strip — top 8 stocks scrolling
3. Signal counts bar — 6 chips (all/manage/entered/ready/setup/discovery) — clickable filters
4. Decision Card (Hero) — best stock with ALL indicators, color-coded by confluence
5. Top Opportunities table — up to 15 rows, 11 columns
6. Mini Open Positions strip — compact P&L if positions exist
7. Nav bar
8. Footer disclaimer

### Page 2: signals.html — مصفوفة التحليل
**Question it answers: "ليش هالفرصة قوية؟"**
**Endpoint: /dashboard/signals (no auth)**

Layout:
1. Topbar + Status
2. Signal Pulse — total count, avg confluence, discovery/setup/ready counts
3. Full Signal Matrix table — ALL stocks, 17 columns:
   السهم | الحالة | السعر | %التغير | Confluence | القرار | EMA | RSI | StochK | Momentum | ADX | Vol | BB Squeeze | RSI Div | الدعم | المقاومة | ATR
4. Sortable columns (click header to sort)
5. Filter bar — by state, by minimum confluence, search by symbol
6. Nav bar

### Page 3: positions.html — إدارة المراكز
**Question it answers: "شسوي بالمراكز؟"**
**Endpoint: /dashboard/portfolio (needs auth — pass key from URL param)**

Layout:
1. Topbar + Status
2. Portfolio Pulse — open count, total P&L KWD, fees, net
3. Open Positions cards — detailed:
   Symbol | Entry | Current | P&L% | P&L KWD | Days held | Quantity | Support | Resistance | Strategy
4. Signal vs Trade stats — signals generated vs confirmed vs skip rate
5. 7-day and 30-day mini stats
6. Nav bar

### Page 4: journal.html — سجل الأداء
**Question it answers: "كيف أدائي؟"**
**Endpoint: /dashboard/journal (needs auth)**

Layout:
1. Topbar + Status
2. Journal Pulse — win rate, total P&L, trades this month, open count
3. Open Positions table
4. Closed Trades table (when available)
5. Monthly Stats cards
6. Best/Worst trade cards
7. 7d vs 30d comparison
8. Nav bar

---

## DESIGN SYSTEM (use exactly these)

### Colors (CSS variables):
```css
--navy-900:#070D17; --navy-800:#0C1525; --navy-700:#111E32;
--navy-600:#162840; --navy-500:#1C334F; --navy-400:#24405F;
--gold:#C6974B; --gold-bright:#D4A95C; --gold-dim:#9E7A3D;
--green:#4CAF82; --green-bright:#5BC492;
--red:#D94452; --red-bright:#E5606C;
--amber:#E8A838; --cyan:#38BDF8;
--text:#E8ECF0; --text-2:#A0ADBC; --text-3:#6B7D90;
```

### Confluence color mapping:
- ≥71: green (strong bullish)
- 50-70: gold (moderate bullish)  
- 40-49: amber (neutral)
- 30-39: red-light (moderate bearish)
- <30: red (strong bearish)

### Typography:
- Arabic headings: Noto Kufi Arabic, weight 800
- Arabic body: Tajawal, weight 400-700
- Numbers/tickers: IBM Plex Mono, weight 500-700
- Table headers: 0.62rem, uppercase, letter-spacing 0.8px, color: gold-dim
- Table data: 0.78rem

### Card styling:
- Background: linear-gradient navy-800 → card
- Border: 1px solid card-border
- Border-radius: 10-14px
- Decision card: border-right 4px colored by confluence

---

## DEPLOYMENT STEPS

1. Create directory: `mkdir -p /home/pi/master_ai/www/trading/`
2. Write 4 HTML files to that directory
3. Add route in server.py to serve these files (or use existing www serving)
4. Add `/dashboard/signals` already in OPEN_PATHS ✓
5. Add `/dashboard/portfolio` and `/dashboard/journal` to OPEN_PATHS (patch server.py)
6. Update HA dashboard YAML:
   - sub-radar → single iframe card pointing to /trading/radar.html
   - sub-signals → single iframe card pointing to /trading/signals.html  
   - sub-journal → single iframe card pointing to /trading/journal.html
   - Add new sub-positions page with iframe card
7. quick_check + smoke_test
8. git commit + restart
9. HA YAML reload

## IMPORTANT RULES
- All Python edits via apply_text_patch.py
- Dashboard YAML: write via Filesystem then Samba copy
- Arabic text: never Python \uXXXX in YAML
- Backward compatible: existing endpoints stay
- Test each page after writing: curl http://localhost:9000/trading/radar.html
- The nav between pages uses relative URLs: href="radar.html", href="signals.html", etc.
