# Gemini Scanner Engine — Implementation Plan
# Date: 2026-04-01
# Author: claude.ai (plan) → Claude Code (execute Python)
# Status: READY FOR EXECUTION

## Overview
Automated Gemini 2.5 Pro stock scanner for 128 KSE stocks.
3-stage funnel: Fast prefilter (128) → Engine scoring (20) → Gemini deep (10-15).
Produces ranked BUY_NOW / WAIT / SELL list every 30 minutes during market hours.

## Architecture Decision
- ChatGPT recommended 9 separate files → too complex for Phase 1
- Gemini recommended 3 files → too simple, missing important pieces
- **Our approach:** 1 main engine file + DB tables + endpoints in dashboard_api.py
- Later: split if it grows beyond 800 lines

---

## Phase 1: Backend (Claude Code executes)

### Step 1: DB Migration
Add tables to `data/life.db`:

```sql
-- Scan run tracking
CREATE TABLE IF NOT EXISTS gemini_scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_uuid TEXT UNIQUE NOT NULL,
    scan_type TEXT NOT NULL DEFAULT 'scheduled',  -- scheduled/event/manual
    started_at TEXT NOT NULL,
    completed_at TEXT,
    market_session TEXT,  -- pre_market/open/closed
    symbols_universe INTEGER DEFAULT 128,
    symbols_prefiltered INTEGER DEFAULT 0,
    symbols_analyzed INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',  -- running/completed/partial/failed/skipped
    avg_latency_ms INTEGER,
    notes TEXT
);

-- Per-symbol analysis results
CREATE TABLE IF NOT EXISTS gemini_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_uuid TEXT NOT NULL,
    symbol TEXT NOT NULL,
    scan_time TEXT NOT NULL,
    
    -- Gemini raw output
    gemini_decision TEXT,          -- BUY/SELL/HOLD
    gemini_confidence REAL,        -- 0-100
    gemini_entry REAL,
    gemini_target REAL,
    gemini_stop REAL,
    gemini_risk_reward REAL,
    gemini_analysis TEXT,          -- Arabic narrative
    gemini_reasons TEXT,           -- JSON array of key reasons
    gemini_latency_ms INTEGER,
    
    -- Local engine scores (snapshot at scan time)
    brain_score REAL,
    golden_score REAL,
    radar_signal TEXT,             -- bullish/bearish/neutral
    prefilter_score REAL,          -- 0-100, local ranking
    
    -- Indicator snapshot
    current_price REAL,
    price_change_pct REAL,
    rsi REAL,
    macd REAL,
    ema_9 REAL,
    ema_21 REAL,
    adx REAL,
    atr REAL,
    volume REAL,
    vol_ratio REAL,
    stoch_k REAL,
    
    -- Fusion output
    fused_score REAL,              -- 0-100, combined score
    final_decision TEXT,           -- BUY_NOW/WAIT/SELL
    final_confidence REAL,         -- 0-100
    
    -- Meta
    from_cache INTEGER DEFAULT 0,
    cache_key TEXT,
    alert_sent INTEGER DEFAULT 0,
    alert_sent_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_gd_symbol_time ON gemini_decisions(symbol, scan_time DESC);
CREATE INDEX IF NOT EXISTS idx_gd_run ON gemini_decisions(run_uuid);
CREATE INDEX IF NOT EXISTS idx_gd_decision ON gemini_decisions(final_decision, fused_score DESC);

-- Alert dedup log
CREATE TABLE IF NOT EXISTS gemini_alert_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    alert_type TEXT,               -- buy_now/sell/momentum
    decision TEXT,
    confidence REAL,
    fused_score REAL,
    dedup_key TEXT UNIQUE,
    sent_at TEXT NOT NULL,
    run_uuid TEXT
);
```

### Step 2: Create gemini_scanner.py (~500-700 lines)

Location: `/home/pi/master_ai/gemini_scanner.py`

#### Class: GeminiScanner

```python
class GeminiScanner:
    """
    Automated Gemini 2.5 Pro stock scanner.
    3-stage funnel: prefilter → score → analyze.
    Runs every 30m during KSE market hours.
    """
    
    def __init__(self, db_path, bridge_client, brain, golden_engine, signal_engine):
        self.db_path = db_path
        self.bridge = bridge_client
        self.brain = brain
        self.golden = golden_engine
        self.signal_engine = signal_engine
        self.semaphore = asyncio.Semaphore(3)  # max 3 concurrent Gemini calls
        self.cache = {}  # candle_key -> analysis result
        self.cache_ttl = 1800  # 30 min
        self.is_running = False
        self.current_run = None
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=300  # 5 min cooldown
        )
```

#### Key Methods:

```python
async def run_scan(self, scan_type="scheduled", symbols=None, force=False):
    """Main scan cycle. Called by scheduler or manually."""
    # 1. Check market hours (09:00-12:40 KWT)
    # 2. Create run record
    # 3. Stage 1: Fast prefilter (all 128)
    # 4. Stage 2: Engine scoring (top 20)
    # 5. Stage 3: Gemini analysis (top 10-15)
    # 6. Fusion scoring
    # 7. Save results
    # 8. Send alerts
    # 9. Mark run complete

async def _prefilter_universe(self):
    """Stage 1: Fast filter using Bridge data.
    Criteria:
    - volume > 0 (traded today)
    - price_change_pct != 0 (some movement)
    - data freshness < 5 min
    Returns: list of ~40-60 active stocks with indicators
    """

async def _score_candidates(self, active_stocks):
    """Stage 2: Score using local engines.
    For each stock:
    - brain_score from Trading Brain
    - golden_match from Golden Engine  
    - radar_signal from Signal Engine
    - technical_alignment (EMA, MACD, RSI direction)
    - volume_spike (vol_ratio > 2)
    
    prefilter_score = weighted combination:
      0.30 * brain_score_norm +
      0.20 * golden_score_norm +
      0.15 * radar_score +
      0.15 * volume_score +
      0.10 * ema_alignment +
      0.10 * momentum_score
    
    Returns: top 12-15 by prefilter_score (buy candidates)
           + top 5 lowest scores (sell candidates)
    """

async def _analyze_with_gemini(self, symbol, indicators):
    """Stage 3: Call /api/analyze (self-call to existing endpoint).
    - Check cache first (candle signature)
    - Use semaphore for concurrency limit
    - Circuit breaker for failures
    - Timeout: 30s per call
    - Returns structured Gemini analysis
    """

def _fuse_scores(self, prefilter_data, gemini_result):
    """Combine Gemini with local engines.
    
    Strategy: Gemini as CONFIRMATION FACTOR (ChatGPT's recommendation)
    
    base_score = prefilter_score  # already combined local engines
    
    confirmation_factor = 1.0
    if gemini aligns with local direction:
        confirmation_factor += 0.15 * (gemini_confidence / 100)
    elif gemini conflicts:
        confirmation_factor -= 0.20 * (gemini_confidence / 100)
    
    fused_score = base_score * confirmation_factor
    
    Final decision:
    - BUY_NOW: fused >= 75 AND gemini == BUY AND brain >= 60
    - SELL:    fused <= 30 OR (gemini == SELL AND brain < 40)
    - WAIT:    everything else
    """

async def _send_alerts(self, results, run_uuid):
    """Telegram alerts for high-conviction decisions.
    BUY_NOW: confidence >= 80, fused >= 78, not sent in last 60 min
    SELL: confidence >= 75, not sent in last 60 min
    """

def get_latest_results(self):
    """Return latest scan results for dashboard."""

def get_scan_status(self):
    """Return current scan progress."""

def get_symbol_history(self, symbol, days=7):
    """Return historical analyses for a symbol."""
```

### Step 3: Add endpoints to dashboard_api.py

Add these endpoints (minimal changes to existing file):

```python
# ============ GEMINI SCANNER ============

@app.get("/api/scanner/latest")
async def get_scanner_latest(decision: str = None, limit: int = 30):
    """Latest scan results, ranked by fused_score.
    Optional: filter by decision (BUY_NOW/WAIT/SELL)"""
    return scanner.get_latest_results(decision=decision, limit=limit)

@app.get("/api/scanner/status")
async def get_scanner_status():
    """Current scan status + progress."""
    return scanner.get_scan_status()

@app.post("/api/scanner/scan")
async def trigger_scan(scan_type: str = "manual", symbols: list = None):
    """Manually trigger a scan. Optional: specific symbols only."""
    asyncio.create_task(scanner.run_scan(scan_type=scan_type, symbols=symbols))
    return {"status": "started"}

@app.get("/api/scanner/symbol/{symbol}/history")
async def get_symbol_scanner_history(symbol: str, days: int = 7):
    """Historical Gemini analyses for one symbol."""
    return scanner.get_symbol_history(symbol, days=days)

@app.post("/api/scanner/symbol/{symbol}/reanalyze")
async def reanalyze_symbol(symbol: str):
    """Force re-analyze one symbol with Gemini."""
    asyncio.create_task(scanner.run_scan(scan_type="manual", symbols=[symbol], force=True))
    return {"status": "started", "symbol": symbol}
```

### Step 4: Register scheduler in server.py

```python
# In server.py startup:
from gemini_scanner import GeminiScanner

scanner = GeminiScanner(
    db_path="data/life.db",
    bridge_client=bridge_client,
    brain=trading_brain,
    golden_engine=golden_engine,
    signal_engine=signal_engine
)

# Scheduler: every 30 min during market hours (KWT = UTC+3)
# Market: 09:00-12:40 KWT = 06:00-09:40 UTC
# Scan at: XX:05 and XX:35 (5 min after candle close for data settlement)
scheduler.add_job(
    scanner.run_scan,
    'cron',
    hour='6-9',
    minute='5,35',
    timezone='Asia/Kuwait',
    id='gemini_scanner_30m',
    name='Gemini Scanner (30m)',
    replace_existing=True
)
```

### Step 5: Integration with existing /api/analyze

The scanner calls the EXISTING `/api/analyze?symbol=X` endpoint internally.
This means:
- No new Gemini API code needed
- Reuses the proven analysis prompt
- Same structured JSON output
- Just needs to be called via HTTP or direct function call

Recommendation: Call the analyze function DIRECTLY (not via HTTP) to avoid network overhead:
```python
# Instead of: requests.get(f"http://localhost:9000/api/analyze?symbol={symbol}")
# Do: result = await analyze_stock(symbol)  # direct function call
```

### Step 6: Testing Checklist
1. `quick_check.py` — syntax + imports
2. `smoke_test.py` — endpoint accessibility
3. Manual scan trigger: `POST /api/scanner/scan`
4. Check DB: `SELECT * FROM gemini_decisions LIMIT 5`
5. Dashboard loads: `GET /api/scanner/latest`
6. Telegram alert test (lower threshold temporarily)

---

## Phase 2: Frontend (claude.ai builds directly)

### decisions.html — Gemini Trading Decisions Dashboard

Design specs:
- Navy+Gold theme (Boursa Kuwait design system)
- RTL Arabic
- Fonts: Tajawal + IBM Plex Mono
- Auto-refresh every 60s
- Responsive for mobile

Sections:
1. **Scan Status Bar** — last scan, next scan, progress, market session
2. **Summary Cards** — BUY_NOW count, WAIT count, SELL count, top pick
3. **Ranked Table** — sorted by fused_score, color-coded by decision
4. **Detail Modal** — click symbol → full Gemini analysis + indicators

Data source: `GET /api/scanner/latest`
Status source: `GET /api/scanner/status`

---

## Phase 3: Future Enhancements (later)
- Outcome tracking table (was decision correct?)
- Gemini confidence calibration (over/under-confident?)
- Event-driven mini-scans (volume spike → immediate rescan)
- Tiered analysis (Flash quick screen → Pro deep)
- Learning feedback: scanner outcomes → Brain weight updates

---

## Execution Order
1. **Claude Code:** Read this plan → Create DB tables → Build gemini_scanner.py → Add endpoints → Register scheduler → Test
2. **claude.ai:** Build decisions.html dashboard page
3. **User:** Test end-to-end during market hours
4. **Review:** Calibrate thresholds after first week of data

---

## File Summary
| What | Who | Where |
|------|-----|-------|
| gemini_scanner.py | Claude Code | /home/pi/master_ai/ |
| DB migration | Claude Code | data/life.db |
| dashboard_api.py changes | Claude Code | /home/pi/master_ai/ |
| server.py scheduler | Claude Code | /home/pi/master_ai/ |
| decisions.html | claude.ai | www/trading/ |

## Important Notes
- gemini_scanner.py calls analyze_stock() DIRECTLY, not via HTTP
- Cache by candle timestamp: same 30m candle = skip re-analysis
- Circuit breaker: 3 failures → 5 min cooldown → local-only mode
- Graceful degradation: if Gemini down, show local scores only (fused_score = prefilter_score)
- Market hours check: skip scan if outside 09:00-12:40 KWT (allow manual override)
- Max 3 concurrent Gemini calls (semaphore)
- Store raw Gemini response in gemini_analysis column for debugging
