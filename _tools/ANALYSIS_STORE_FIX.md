# Fix: Analysis Page — Store & Serve (No Live Bridge Dependency)
# Date: 2026-04-04 (Updated)
# Priority: HIGH — current design is broken
# Status: READY FOR EXECUTION

## Problem:
analysis.html calls /api/analyze → stock_analyzer.py → Bridge API LIVE.
Every time user opens analysis = 30-60 sec wait + Bridge MUST be online.
If Bridge offline = no analysis at all.
This is WRONG. Analysis should be PRE-COMPUTED and STORED.

## IMPORTANT FACTS:
## 1. Analysis covers ALL 128 KSE stocks, NOT just Whitelist 10.
## 2. TradingView has ALL historical data 24/7 — NOT only during market hours.
## 3. Bridge can pull data ANY TIME — it connects to TradingView servers, not the exchange.
## 4. The daily scheduled refresh at 2:15 PM is for FRESHNESS (after new candles close),
##    but a manual refresh-all can run ANY TIME Bridge is running.
## 5. Bridge not running = PC issue, NOT a market issue.

---

## 1. Scheduled Job (daily after market close ~2:15 PM KWT)

After market closes (Sunday-Thursday):
  for each symbol in ALL_128_SYMBOLS:
    1. Fetch bars from Bridge (TradingView data available 24/7)
    2. Send to Gemini 2.5 Pro for analysis
    3. Store result in DB table stock_analysis_cache
    4. Rate limit: sleep 3-5 sec between stocks (Gemini free tier)
  
  Telegram: "تحليل فني محدث ل 128 سهم"
  Total time estimate: 128 stocks x ~10 sec each = ~20 min
  This runs in background — doesnt block anything.

  NOTE: The 2:15 PM schedule is optimal (after new daily candle closes)
  but refresh-all can run ANY TIME Bridge is online on the PC.
  TradingView data is available 24/7 — not limited to market hours.

---

## 2. DB Table

```sql
CREATE TABLE IF NOT EXISTS stock_analysis_cache (
    symbol TEXT NOT NULL,
    analysis_date TEXT NOT NULL,
    analysis_json TEXT NOT NULL,
    structured_json TEXT,
    signal TEXT,
    confidence INTEGER,
    bridge_data TEXT,
    gemini_model TEXT DEFAULT 'gemini-2.5-pro',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, analysis_date)
);
CREATE INDEX IF NOT EXISTS idx_sac_symbol ON stock_analysis_cache(symbol);
CREATE INDEX IF NOT EXISTS idx_sac_date ON stock_analysis_cache(analysis_date);
```

---

## 3. Endpoint Changes

GET /api/analyze?symbol=ACICO
  OLD: calls Bridge live then Gemini then returns (30+ sec, fails without Bridge)
  NEW: reads from stock_analysis_cache then returns instantly
       If no cached analysis: returns {error: "no analysis yet"}
       NEVER calls Bridge live from this endpoint
       Returns latest analysis_date entry for that symbol

POST /api/analyze/refresh?symbol=ACICO  (API key protected)
  Manual trigger to refresh one stock NOW
  Uses Bridge + Gemini, stores in DB, returns result

POST /api/analyze/refresh-all  (API key protected)
  Manual trigger to refresh ALL 128 stocks
  Background task — returns immediately, runs in background
  Telegram progress updates every 20 stocks

---

## 4. Scheduled Refresh Logic

```python
async def scheduled_analysis_refresh():
    """Run daily at 14:15 KWT after market close. Analyzes ALL 128 stocks."""
    if not is_trading_day():
        return
    
    # Use all symbols from stock_profiles table (128 stocks)
    all_symbols = db.execute("SELECT symbol FROM stock_profiles ORDER BY symbol").fetchall()
    all_symbols = [r[0] for r in all_symbols]
    
    total = len(all_symbols)
    done = 0
    errors = 0
    
    for symbol in all_symbols:
        try:
            result = analyze_stock(symbol)
            # Store in DB
            db.execute("""
                INSERT OR REPLACE INTO stock_analysis_cache
                (symbol, analysis_date, analysis_json, structured_json, signal, confidence)
                VALUES (?, date('now'), ?, ?, ?, ?)
            """, (symbol, json.dumps(result), 
                  json.dumps(result.get('structured',{})),
                  result.get('structured',{}).get('signal',''),
                  result.get('structured',{}).get('confidence',0)))
            db.commit()
            done += 1
        except Exception as e:
            logger.error(f"Analysis failed for {symbol}: {e}")
            errors += 1
        
        if done % 20 == 0:
            send_telegram(f"analyzing: {done}/{total} ({errors} errors)")
        
        await asyncio.sleep(4)  # Gemini free tier rate limit
    
    send_telegram(f"analysis complete: {done}/{total} ({errors} errors)")
```

---

## 5. Frontend (analysis.html) — New Design

LEFT PANEL: Stock list (all 128, searchable)
  - Search box at top (filter by name)
  - Whitelist stocks: gold badge
  - Each row shows: symbol + signal icon + last update
  - Sorted by: signal strength or alphabetical
  - Click = instant switch (data from cache)

RIGHT PANEL: Full analysis for selected stock
  - Shows cached Gemini analysis
  - "Last updated: yesterday 2:15 PM"
  - If stale > 24h: amber warning
  - If no analysis: "Not analyzed yet"
  - Manual "Refresh" button (uses Bridge, rare)

NO LOADING SPINNER for cached stocks.
Loading spinner ONLY for manual refresh.

---

## 6. Files to Modify

### Claude Code:
- MODIFY: stock_analyzer.py
  - Add store_analysis() and get_cached_analysis()
  - Add stock_analysis_cache table creation on init
  - Change analyze_stock() behavior: cache-first
- MODIFY: server.py
  - Change GET /api/analyze to read from cache
  - Add POST /api/analyze/refresh endpoint
  - Add POST /api/analyze/refresh-all endpoint (background)
  - Add scheduled job at 14:15 KWT (Sun-Thu)
  - Add stock_analysis_cache to OPEN_PATHS if needed

### claude.ai:
- MODIFY: www/trading/analysis.html
  - Two-panel layout: stock list + analysis
  - Instant switching between stocks
  - Last updated timestamp
  - Stale warning
  - Manual refresh button

---

## Claude Code Command:
> Read _tools/ANALYSIS_STORE_FIX.md — Analysis must be stored in DB and auto-updated daily at 2:15 PM for ALL 128 stocks. GET /api/analyze reads from cache only. Add POST /api/analyze/refresh and /api/analyze/refresh-all. Add scheduled job. Never call Bridge from GET /api/analyze.
