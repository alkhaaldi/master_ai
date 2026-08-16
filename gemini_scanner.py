"""Gemini Scanner — Automated 3-stage stock scanner.

Funnel: Fast Prefilter (92) → Engine Scoring (20) → Gemini Deep (12-15)
Produces ranked BUY_NOW / WAIT / SELL every 30m during market hours.
"""
import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import time
from scanner_universe import get_scanner_universe, get_market
import uuid
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("gemini_scanner")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")
KWT = timezone(timedelta(hours=3))

# ═══════════════════════════════════
# DB Schema
# ═══════════════════════════════════

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS gemini_scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_uuid TEXT UNIQUE NOT NULL,
    scan_type TEXT NOT NULL DEFAULT 'scheduled',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    market_session TEXT,
    symbols_universe INTEGER DEFAULT 128,
    symbols_prefiltered INTEGER DEFAULT 0,
    symbols_analyzed INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    avg_latency_ms INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS gemini_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_uuid TEXT NOT NULL,
    symbol TEXT NOT NULL,
    scan_time TEXT NOT NULL,
    gemini_decision TEXT,
    gemini_confidence REAL,
    gemini_entry REAL,
    gemini_target REAL,
    gemini_stop REAL,
    gemini_risk_reward REAL,
    gemini_analysis TEXT,
    gemini_reasons TEXT,
    gemini_latency_ms INTEGER,
    brain_score REAL,
    golden_score REAL,
    radar_signal TEXT,
    prefilter_score REAL,
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
    fused_score REAL,
    final_decision TEXT,
    final_confidence REAL,
    from_cache INTEGER DEFAULT 0,
    cache_key TEXT,
    market TEXT DEFAULT 'unknown',
    alert_sent INTEGER DEFAULT 0,
    alert_sent_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_gd_symbol_time ON gemini_decisions(symbol, scan_time DESC);
CREATE INDEX IF NOT EXISTS idx_gd_run ON gemini_decisions(run_uuid);
CREATE INDEX IF NOT EXISTS idx_gd_decision ON gemini_decisions(final_decision, fused_score DESC);

CREATE TABLE IF NOT EXISTS gemini_alert_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    alert_type TEXT,
    decision TEXT,
    confidence REAL,
    fused_score REAL,
    dedup_key TEXT UNIQUE,
    sent_at TEXT NOT NULL,
    run_uuid TEXT
);
"""


def init_schema(db_path=None):
    path = db_path or DB_PATH
    with sqlite3.connect(path) as c:
        c.executescript(_SCHEMA_SQL)
    logger.info("gemini_scanner schema OK")


def _conn(db_path=None):
    path = db_path or DB_PATH
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c


# ═══════════════════════════════════
# Circuit Breaker
# ═══════════════════════════════════

class CircuitBreaker:
    def __init__(self, failure_threshold=3, recovery_timeout=300):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed=OK, open=blocked

    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = "open"
            logger.warning("Circuit breaker OPEN — %d failures", self.failures)

    def record_success(self):
        self.failures = 0
        self.state = "closed"

    def allow_request(self):
        if self.state == "closed":
            return True
        if time.time() - self.last_failure_time > self.recovery_timeout:
            self.state = "closed"
            self.failures = 0
            logger.info("Circuit breaker reset (recovery timeout)")
            return True
        return False


# ═══════════════════════════════════
# Market Hours
# ═══════════════════════════════════

def _market_session():
    """Return current market session based on KWT time."""
    now = datetime.now(KWT)
    h, m = now.hour, now.minute
    t = h * 60 + m
    if now.weekday() >= 5:  # Sat/Sun
        return "weekend"
    if t < 540:  # before 09:00
        return "pre_market"
    if t <= 760:  # 09:00-12:40
        return "open"
    return "closed"


# ═══════════════════════════════════
# Scanner Engine
# ═══════════════════════════════════

class GeminiScanner:
    """Automated 3-stage stock scanner."""

    def __init__(self):
        self.semaphore = asyncio.Semaphore(3)
        self.cache = {}  # symbol -> {data, ts}
        self.cache_ttl = 1800  # 30 min
        self.is_running = False
        self.current_run = None
        self.circuit_breaker = CircuitBreaker(failure_threshold=6, recovery_timeout=120)
        self._tg_send = None  # set from server.py

    def set_tg_send(self, fn):
        """Set Telegram send function for alerts."""
        self._tg_send = fn

    # ─── Stage 1: Prefilter ───

    async def _prefilter_universe(self):
        """Stage 1: Fetch indicators for 92-stock universe.
        Bridge (live) → fallback to daily snapshot (DB).
        All stocks with valid price pass — Stage 2 handles ranking."""
        try:
            from bridge_client import get_bridge_client
            from stock_radar import get_daily_snapshot
        except ImportError as e:
            logger.error("Import error in prefilter: %s", e)
            return []

        from contract import expect
        symbols = get_scanner_universe()  # 92 active stocks
        if not symbols:
            logger.warning("Empty universe")
            return []

        session = _market_session()

        # Try Bridge with timeout
        sym_data = {}
        try:
            client = get_bridge_client()
            multi = await asyncio.wait_for(
                client.get_multi_analysis(symbols), timeout=120
            )
            if multi.get("bridge_online"):
                sym_data = multi.get("symbols", {})
                logger.info("Bridge returned %d symbols", len(sym_data))
        except asyncio.TimeoutError:
            logger.warning("Bridge multi_analysis timed out (120s)")
        except Exception as e:
            logger.warning("Bridge error: %s", e)

        # Fallback: daily snapshot from radar DB
        if len(sym_data) < 20:
            logger.info("Bridge returned %d — augmenting with daily snapshot", len(sym_data))
            try:
                snapshot = get_daily_snapshot(top_n=128, min_score=0)
                for s in snapshot:
                    sym = s["symbol"]
                    if sym in sym_data:
                        continue  # Bridge data takes priority
                    sym_data[sym] = {
                        "price": s.get("price", 0),
                        "change_pct": s.get("change_pct", 0),
                        "rsi": s.get("rsi", 0),
                        "macd": s.get("macd", 0),
                        "macd_state": s.get("macd_state", ""),
                        "ema_state": s.get("ema_state", ""),
                        "adx": s.get("adx", 0),
                        "volume": s.get("volume", 0),
                        "vol_ratio": s.get("vol_ratio", 1.0),
                        "stoch_k": s.get("stoch_k", 50),
                        # absence -> None, never 0: since 2026-08-15 a
                        # confluence_score of 0 is the MOST BEARISH ordinal
                        # level (SCALES.md), so defaulting a missing value
                        # to 0 would mint a maximally bearish reading out of
                        # nothing. `score` is a different scale and is no
                        # longer silently substituted.
                        "confluence_score": s.get("confluence_score"),
                    }
            except Exception as e:
                logger.error("Daily snapshot fallback failed: %s", e)

        # Build active list — all stocks with valid price pass Stage 1
        # Stage 2 scoring handles the ranking and top-N selection
        active = []
        for sym in symbols:  # iterate universe order, not dict order
            data = sym_data.get(sym)
            if not data or data.get("error"):
                continue
            price = data.get("price", 0) or 0
            if price <= 0:
                continue
            active.append({
                "symbol": sym,
                "price": price,
                "change_pct": data.get("change_pct", 0) or 0,
                "rsi": data.get("rsi") or data.get("rsi_14", 0),
                "macd": data.get("macd", 0),
                "macd_state": data.get("macd_state", ""),
                "ema_state": data.get("ema_state", ""),
                "ema_9": data.get("ema_9", 0),
                "ema_21": data.get("ema_21", 0),
                "adx": data.get("adx", 0),
                "atr": data.get("atr") or data.get("atr_14", 0),
                "volume": data.get("volume", 0) or 0,
                "vol_ratio": data.get("vol_ratio", 1.0),
                "stoch_k": data.get("stoch_k", 50),
                # One name end to end (was renamed to `confluence` here,
                # which is how the bridge path lost it: bridge payloads carry
                # signals.confluence, not confluence_score, so this read
                # returned the 0 default and every bridge-sourced stock
                # scored as maximally bearish. expect() puts that on the
                # record instead of defaulting in silence.
                "confluence_score": expect(
                    data, "confluence_score",
                    "prefilter symbol data -> scoring loop", None),
            })
        logger.info("Prefilter: %d/%d have valid data (session=%s)", len(active), len(symbols), session)
        return active

    # ─── Stage 2: Engine Scoring ───

    def _score_candidates(self, active_stocks):
        """Score using local engines → return top candidates."""
        scored = []
        # Get brain weights
        brain_weights = {}
        try:
            from trading_brain import get_indicator_weights
            brain_weights = get_indicator_weights() or {}
        except Exception:
            pass

        # Get golden opportunities.
        # The key was "opportunities" from 2026-04-07 to 2026-08-16; the
        # producer has emitted "all_opportunities" since 2026-03-28. The
        # reader was born wrong, and `.get(..., [])` plus a debug-level
        # except kept it invisible for 4.5 months while 0.20 of the weight
        # below sat at a constant zero. Read through the contract guard so
        # the next rename cannot repeat it silently.
        golden_opps = {}
        try:
            from golden_engine import scan_opportunities
            from contract import expect
            result = scan_opportunities(active_stocks)
            for opp in expect(result, "all_opportunities",
                              "golden_engine.scan_opportunities -> gemini prefilter",
                              []):
                golden_opps[opp["symbol"]] = opp.get("confidence", 50)
        except Exception as e:
            logger.warning("Golden engine unavailable: %r", e)

        for stock in active_stocks:
            sym = stock["symbol"]
            rsi = stock.get("rsi", 50) or 50
            adx = stock.get("adx", 0) or 0
            vol_ratio = stock.get("vol_ratio", 1.0) or 1.0
            stoch = stock.get("stoch_k", 50) or 50
            ema_state = stock.get("ema_state", "")
            macd_state = stock.get("macd_state", "")
            # `or 0` removed: it collapsed a legitimate 0 (most bearish)
            # and a missing value into the same number. None now means
            # "not measured" and is handled explicitly at every use below.
            confluence = stock.get("confluence_score")

            # SCALES.md: this formula's consumer (the weighted prefilter
            # below) is a 0-100 blend, so brain_score is clamped to 0-100 at
            # BOTH ends now. It was capped above only - measured -62.4..66.0
            # over 305 rows - and that asymmetry produced every negative
            # final_confidence. The clamp is allowed here because SCALES.md
            # rule 4 is satisfied: the cause is written down, so this hides
            # nothing. The 41 historical rows stay in the DB as evidence.
            # `if confluence else 40` tested truthiness, so a real 0 - the
            # most bearish level there is - took the absent-value branch and
            # came out as a neutral 40. The test is on None now: 0 scores as
            # 0, and only a genuinely missing measurement falls back.
            brain_score = (max(0.0, min(confluence * 1.2, 100.0))
                           if confluence is not None else 40)
            # SCALES.md: golden_score is DECLARED 0-100 and MEASURED constant
            # 0.0 across all 305 stored rows - this lookup has never once
            # resolved, so a fifth of the weighted sum below is a dead zero
            # dragging every score down. Recorded, not fixed: the cause (why
            # golden_opps never contains these symbols) is not yet known.
            golden_score = golden_opps.get(sym, 0)
            if golden_score == 0:
                logger.warning("prefilter: golden_score 0 for %s - 0.20 of the "
                               "weight is contributing nothing (SCALES.md)", sym)

            # EMA alignment score
            ema_score = 0
            if "bull" in str(ema_state).lower():
                ema_score = 70
            elif "bear" in str(ema_state).lower():
                ema_score = 20
            else:
                ema_score = 45

            # MACD momentum
            macd_score = 50
            if "bull" in str(macd_state).lower() or "positive" in str(macd_state).lower():
                macd_score = 75
            elif "bear" in str(macd_state).lower() or "negative" in str(macd_state).lower():
                macd_score = 25

            # Volume score
            vol_score = min(vol_ratio * 30, 100) if vol_ratio else 30

            # RSI momentum (30-70 is neutral, <30 oversold bounce, >70 overbought risk)
            momentum_score = 50
            if 30 <= rsi <= 50:
                momentum_score = 60 + (50 - rsi)  # oversold recovery zone
            elif 50 < rsi <= 70:
                momentum_score = 55 + (rsi - 50) * 0.5  # strength zone
            elif rsi > 70:
                momentum_score = max(30, 70 - (rsi - 70) * 2)  # overbought risk
            elif rsi < 30:
                momentum_score = 70  # oversold bounce

            # Radar signal
            radar_signal = "neutral"
            if confluence is not None and confluence >= 65:
                radar_signal = "bullish"
            elif confluence is not None and confluence <= 35:
                radar_signal = "bearish"

            # Weighted prefilter score. SCALES.md: this assumes every input
            # is 0-100. Two of them break that today - brain_score can be
            # negative, golden_score is always 0 - so the sum is MEASURED
            # -13.9..46.8 and has never reached the 70/75 thresholds tested
            # against it further down.
            prefilter_score = (
                0.30 * brain_score +
                0.20 * golden_score +
                0.15 * (confluence if confluence is not None else 40) +
                0.15 * vol_score +
                0.10 * ema_score +
                0.10 * momentum_score
            )

            scored.append({
                **stock,
                "brain_score": round(brain_score, 1),
                "golden_score": round(golden_score, 1),
                "radar_signal": radar_signal,
                "prefilter_score": round(prefilter_score, 1),
            })

        # Sort by prefilter_score descending
        scored.sort(key=lambda x: x["prefilter_score"], reverse=True)

        # Top 15 buy candidates + bottom 5 sell candidates
        buy_candidates = scored[:15]
        sell_candidates = [s for s in scored[-5:] if s["prefilter_score"] < 35]
        # Ensure no overlap
        buy_syms = {c["symbol"] for c in buy_candidates}
        sell_candidates = [s for s in sell_candidates if s["symbol"] not in buy_syms]

        candidates = buy_candidates + sell_candidates
        logger.info("Scored: %d total, %d buy candidates, %d sell candidates",
                     len(scored), len(buy_candidates), len(sell_candidates))
        return candidates

    # ─── Stage 3: Gemini Analysis ───

    async def _analyze_one(self, symbol, indicators):
        """Call analyze_stock with retry on 503/timeout + circuit breaker."""
        if not self.circuit_breaker.allow_request():
            logger.warning("Circuit breaker open — skipping %s", symbol)
            return None

        # Check cache
        cache_key = f"{symbol}_{int(time.time() // self.cache_ttl)}"
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug("Cache hit: %s", symbol)
            return {**cached, "from_cache": True, "cache_key": cache_key}

        MAX_RETRIES = 2
        async with self.semaphore:
            for attempt in range(MAX_RETRIES + 1):
                t0 = time.time()
                try:
                    from stock_analyzer import analyze_stock
                    result = await asyncio.to_thread(analyze_stock, symbol)
                    latency_ms = int((time.time() - t0) * 1000)
                    if result.get("error"):
                        err = str(result["error"])
                        # Retry on 503/429/timeout
                        if attempt < MAX_RETRIES and ("503" in err or "429" in err or "timed out" in err):
                            wait = 10 * (attempt + 1)
                            logger.info("Retrying %s in %ds (attempt %d): %s", symbol, wait, attempt + 1, err)
                            await asyncio.sleep(wait)
                            continue
                        self.circuit_breaker.record_failure()
                        logger.warning("Gemini error for %s: %s", symbol, err)
                        return None
                    self.circuit_breaker.record_success()
                    out = {
                        "structured": result.get("structured", {}),
                        "report": result.get("report", ""),
                        "latency_ms": latency_ms,
                        "from_cache": False,
                        "cache_key": cache_key,
                    }
                    self.cache[cache_key] = out
                    return out
                except Exception as e:
                    err = str(e)
                    if attempt < MAX_RETRIES and ("503" in err or "429" in err or "timed out" in err.lower()):
                        wait = 10 * (attempt + 1)
                        logger.info("Retrying %s in %ds (attempt %d): %s", symbol, wait, attempt + 1, err)
                        await asyncio.sleep(wait)
                        continue
                    self.circuit_breaker.record_failure()
                    logger.error("Gemini call failed for %s: %s", symbol, e)
                    return None

    # ─── Fusion ───

    @staticmethod
    def _shadow_buy_now(symbol, branch, score, gemini_conf, brain_score,
                        threshold=None):
        """Record a BUY_NOW that WOULD have fired, without firing it.

        Opened by user decision 2026-08-16 for a two-week observation
        window after golden_score stopped being a constant zero. The row
        is the evidence for that decision; nothing reads it to trade.
        """
        import sqlite3
        from datetime import datetime as _dt
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10)
            conn.execute("""CREATE TABLE IF NOT EXISTS buy_now_shadow (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                logged_at TEXT NOT NULL,
                symbol TEXT,
                branch TEXT NOT NULL,
                score REAL,
                gemini_confidence REAL,
                brain_score REAL,
                threshold REAL,
                acted BOOLEAN NOT NULL DEFAULT 0)""")
            cols = [r[1] for r in conn.execute(
                "PRAGMA table_info(buy_now_shadow)")]
            if "threshold" not in cols:
                conn.execute("ALTER TABLE buy_now_shadow ADD COLUMN threshold REAL")
            conn.execute(
                "INSERT INTO buy_now_shadow (logged_at, symbol, branch, score,"
                " gemini_confidence, brain_score, threshold, acted)"
                " VALUES (?,?,?,?,?,?,?,0)",
                (_dt.utcnow().strftime("%Y-%m-%d %H:%M:%S"), symbol, branch,
                 score, gemini_conf, brain_score, threshold))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("shadow BUY_NOW not recorded for %s: %r", symbol, e)
        logger.warning("SHADOW BUY_NOW (not acted): %s branch=%s score=%.1f "
                       "threshold=%s gemini_conf=%s brain=%.1f",
                       symbol, branch, score if score is not None else -1,
                       threshold, gemini_conf,
                       brain_score if brain_score is not None else -1)

    def _fuse_scores(self, prefilter_data, gemini_result):
        """Combine local prefilter with Gemini confirmation."""
        base_score = prefilter_data.get("prefilter_score", 50)

        if not gemini_result:
            # Gemini unavailable — use local only
            decision = "WAIT"
            if base_score >= 70:
                # SHADOW ONLY (user decision 2026-08-16): golden_score was a
                # constant 0 until today, so this branch has never once been
                # reachable. Two weeks of observation before it may act.
                self._shadow_buy_now(prefilter_data.get("symbol"), "no_gemini",
                                     base_score, None, base_score,
                                     threshold=70)
            elif base_score <= 30:
                decision = "SELL"
            return {
                "fused_score": base_score,
                "final_decision": decision,
                # SCALES.md: UNCLAMPED, unlike the Gemini branch below. Every
                # one of the 41 negative final_confidence rows in the DB came
                # through here, carrying a negative brain_score up from the
                # prefilter. Left as-is by F-3.4 - it is the only thing making
                # the upstream scale mismatch visible.
                "final_confidence": base_score * 0.7,
                "gemini_available": False,
            }

        structured = gemini_result.get("structured", {})
        gemini_signal = (structured.get("signal") or "").strip()
        # SCALES.md: 0-100, measured 25.0..85.0 over 173 non-null rows.
        # The default turns an ABSENT or malformed model confidence into a
        # confident midpoint - absence becoming a value, the disease this
        # phase is named for. Declared here; changing it changes decisions.
        gemini_conf = structured.get("confidence", 50)
        if not isinstance(gemini_conf, (int, float)):
            gemini_conf = 50

        # Map Gemini signal to direction
        gemini_is_buy = any(w in gemini_signal for w in ["شراء", "buy", "BUY"])
        gemini_is_sell = any(w in gemini_signal for w in ["بيع", "sell", "SELL"])
        local_is_bullish = base_score >= 55

        # Confirmation factor
        confirmation_factor = 1.0
        if gemini_is_buy and local_is_bullish:
            confirmation_factor += 0.15 * (gemini_conf / 100)
        elif gemini_is_sell and not local_is_bullish:
            confirmation_factor += 0.10 * (gemini_conf / 100)
        elif gemini_is_buy and not local_is_bullish:
            confirmation_factor += 0.05  # mild boost
        elif gemini_is_sell and local_is_bullish:
            confirmation_factor -= 0.20 * (gemini_conf / 100)  # conflict penalty

        fused_score = round(base_score * confirmation_factor, 1)
        fused_score = max(0, min(100, fused_score))

        # Final decision
        brain_score = prefilter_data.get("brain_score", 50)
        if fused_score >= 75 and gemini_is_buy and brain_score >= 55:
            # SHADOW ONLY (user decision 2026-08-16) - see _shadow_buy_now.
            # This gate has never fired: prefilter measured -13.9..46.8 while
            # a constant-zero golden_score held a fifth of its weight. Now
            # that the input is real the scores will move, and moving them
            # and acting on them in the same change would leave nothing to
            # compare against. Observe two weeks, then decide.
            self._shadow_buy_now(prefilter_data.get("symbol"), "fused",
                                 fused_score, gemini_conf, brain_score,
                                 threshold=75)
            final_decision = "WAIT"
        elif fused_score <= 30 or (gemini_is_sell and brain_score < 40):
            final_decision = "SELL"
        else:
            final_decision = "WAIT"

        final_confidence = round(fused_score * 0.6 + gemini_conf * 0.4, 1)

        return {
            "fused_score": fused_score,
            "final_decision": final_decision,
            "final_confidence": final_confidence,
            "gemini_available": True,
            "gemini_decision": gemini_signal,
            "gemini_confidence": gemini_conf,
            "gemini_entry": structured.get("entry"),
            "gemini_target": structured.get("targets", [None])[0] if structured.get("targets") else None,
            "gemini_stop": structured.get("stop_loss"),
            "gemini_report": gemini_result.get("report", ""),
            "gemini_latency_ms": gemini_result.get("latency_ms", 0),
            "from_cache": gemini_result.get("from_cache", False),
            "cache_key": gemini_result.get("cache_key", ""),
        }

    # ─── Alerts ───

    async def _send_alerts(self, results, run_uuid):
        """Send Telegram alerts for high-conviction decisions."""
        if not self._tg_send:
            return
        for r in results:
            decision = r.get("final_decision")
            confidence = r.get("final_confidence", 0)
            fused = r.get("fused_score", 0)
            symbol = r.get("symbol")

            should_alert = False
            alert_type = None
            if decision == "BUY_NOW" and confidence >= 78 and fused >= 75:
                should_alert = True
                alert_type = "buy_now"
            elif decision == "SELL" and confidence >= 72:
                should_alert = True
                alert_type = "sell"

            if not should_alert:
                continue

            # Dedup: same symbol+decision within 60 min
            dedup_key = f"{symbol}_{decision}_{int(time.time() // 3600)}"
            try:
                with _conn() as c:
                    exists = c.execute(
                        "SELECT 1 FROM gemini_alert_log WHERE dedup_key = ?", (dedup_key,)
                    ).fetchone()
                    if exists:
                        continue
                    c.execute(
                        "INSERT INTO gemini_alert_log (symbol, alert_type, decision, confidence, fused_score, dedup_key, sent_at, run_uuid) VALUES (?,?,?,?,?,?,?,?)",
                        (symbol, alert_type, decision, confidence, fused, dedup_key, datetime.utcnow().isoformat(), run_uuid),
                    )
            except Exception as e:
                logger.error("Alert dedup error: %s", e)
                continue

            # Format message
            emoji = "🟢" if decision == "BUY_NOW" else "🔴"
            entry = r.get("gemini_entry", "—")
            stop = r.get("gemini_stop", "—")
            target = r.get("gemini_target", "—")
            msg = (
                f"{emoji} *{symbol}* — {decision}\n"
                f"📊 ثقة: {confidence:.0f}% | نقاط: {fused:.0f}\n"
                f"💰 دخول: {entry} | وقف: {stop} | هدف: {target}\n"
                f"🔍 /تحليل {symbol}"
            )
            try:
                await self._tg_send(msg)
            except Exception as e:
                logger.error("Alert send failed for %s: %s", symbol, e)

    # ─── Main Scan ───

    async def run_scan(self, scan_type="scheduled", symbols=None, force=False):
        """Main scan cycle."""
        if self.is_running and not force:
            logger.info("Scan already running — skipped")
            return {"status": "skipped", "reason": "already_running"}

        session = _market_session()
        if scan_type == "scheduled" and session not in ("open", "pre_market"):
            logger.info("Market %s — scheduled scan skipped", session)
            return {"status": "skipped", "reason": f"market_{session}"}

        self.is_running = True
        run_uuid = str(uuid.uuid4())[:8]
        now_iso = datetime.utcnow().isoformat() + "Z"

        try:
            with _conn() as c:
                c.execute(
                    "INSERT INTO gemini_scan_runs (run_uuid, scan_type, started_at, market_session, status) VALUES (?,?,?,?,?)",
                    (run_uuid, scan_type, now_iso, session, "running"),
                )
        except Exception as e:
            logger.error("Failed to create run record: %s", e)

        self.current_run = {
            "run_uuid": run_uuid, "scan_type": scan_type,
            "started_at": now_iso, "status": "running",
            "stage": "prefilter", "progress": 0,
        }

        try:
            # Stage 1: Prefilter
            logger.info("Scan %s — Stage 1: Prefilter", run_uuid)
            self.current_run["stage"] = "prefilter"
            active = await self._prefilter_universe()
            if not active:
                self._finish_run(run_uuid, "failed", notes="no active stocks")
                return {"status": "failed", "reason": "no_active_stocks"}

            # Stage 2: Score
            logger.info("Scan %s — Stage 2: Scoring %d stocks", run_uuid, len(active))
            self.current_run["stage"] = "scoring"
            self.current_run["progress"] = 20
            candidates = self._score_candidates(active)

            # If specific symbols requested, filter
            if symbols:
                symbols_upper = [s.upper() for s in symbols]
                candidates = [c for c in candidates if c["symbol"] in symbols_upper]
                if not candidates:
                    # Force-add requested symbols from active list
                    candidates = [s for s in active if s["symbol"] in symbols_upper]
                    for c in candidates:
                        c.setdefault("prefilter_score", 50)
                        c.setdefault("brain_score", 50)
                        c.setdefault("golden_score", 0)
                        c.setdefault("radar_signal", "neutral")

            with _conn() as c:
                c.execute(
                    "UPDATE gemini_scan_runs SET symbols_universe=?, symbols_prefiltered=? WHERE run_uuid=?",
                    (len(active), len(candidates), run_uuid),
                )

            # Stage 3: Gemini analysis
            logger.info("Scan %s — Stage 3: Gemini analysis for %d candidates", run_uuid, len(candidates))
            self.current_run["stage"] = "gemini"
            self.current_run["progress"] = 40

            results = []
            total = len(candidates)
            latencies = []

            for i, cand in enumerate(candidates):
                sym = cand["symbol"]
                self.current_run["progress"] = 40 + int(50 * (i + 1) / total)
                self.current_run["current_symbol"] = sym

                gemini_result = await self._analyze_one(sym, cand)
                fused = self._fuse_scores(cand, gemini_result)

                row = {
                    **cand,
                    **fused,
                }
                results.append(row)

                if fused.get("gemini_latency_ms"):
                    latencies.append(fused["gemini_latency_ms"])

                # Pace calls to avoid Gemini rate limits (3s between calls)
                if i < total - 1:
                    await asyncio.sleep(3)

            # Save results
            self.current_run["stage"] = "saving"
            self.current_run["progress"] = 92
            self._save_results(results, run_uuid, now_iso)

            # Send alerts
            self.current_run["stage"] = "alerts"
            self.current_run["progress"] = 96
            await self._send_alerts(results, run_uuid)

            # Mark complete
            avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0
            self._finish_run(run_uuid, "completed",
                             symbols_analyzed=len(results), avg_latency=avg_latency)

            logger.info("Scan %s completed: %d results, avg latency %dms",
                        run_uuid, len(results), avg_latency)
            return {
                "status": "completed", "run_uuid": run_uuid,
                "results_count": len(results), "avg_latency_ms": avg_latency,
            }

        except Exception as e:
            logger.exception("Scan %s failed: %s", run_uuid, e)
            self._finish_run(run_uuid, "failed", notes=str(e))
            return {"status": "failed", "error": str(e)}
        finally:
            self.is_running = False
            self.current_run = None

    def _save_results(self, results, run_uuid, scan_time):
        """Persist scan results to DB."""
        with _conn() as c:
            for r in results:
                try:
                    c.execute("""
                        INSERT INTO gemini_decisions (
                            run_uuid, symbol, scan_time,
                            gemini_decision, gemini_confidence, gemini_entry, gemini_target, gemini_stop,
                            gemini_risk_reward, gemini_analysis, gemini_reasons, gemini_latency_ms,
                            brain_score, golden_score, radar_signal, prefilter_score,
                            current_price, price_change_pct, rsi, macd, ema_9, ema_21,
                            adx, atr, volume, vol_ratio, stoch_k,
                            fused_score, final_decision, final_confidence,
                            from_cache, cache_key, market
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        run_uuid, r["symbol"], scan_time,
                        r.get("gemini_decision"), r.get("gemini_confidence"),
                        _parse_price(r.get("gemini_entry")), _parse_price(r.get("gemini_target")),
                        _parse_price(r.get("gemini_stop")),
                        None, r.get("gemini_report", ""),
                        json.dumps(r.get("gemini_reasons", []), ensure_ascii=False) if r.get("gemini_reasons") else None,
                        r.get("gemini_latency_ms"),
                        r.get("brain_score"), r.get("golden_score"),
                        r.get("radar_signal"), r.get("prefilter_score"),
                        r.get("price"), r.get("change_pct"),
                        r.get("rsi"), r.get("macd"),
                        r.get("ema_9"), r.get("ema_21"),
                        r.get("adx"), r.get("atr"),
                        r.get("volume"), r.get("vol_ratio"), r.get("stoch_k"),
                        r.get("fused_score"), r.get("final_decision"), r.get("final_confidence"),
                        1 if r.get("from_cache") else 0, r.get("cache_key"),
                        get_market(r["symbol"]),
                    ))
                except Exception as e:
                    logger.error("Failed to save %s: %s", r.get("symbol"), e)

    def _finish_run(self, run_uuid, status, symbols_analyzed=0, avg_latency=0, notes=None):
        try:
            with _conn() as c:
                c.execute(
                    "UPDATE gemini_scan_runs SET status=?, completed_at=?, symbols_analyzed=?, avg_latency_ms=?, notes=? WHERE run_uuid=?",
                    (status, datetime.utcnow().isoformat() + "Z", symbols_analyzed, avg_latency, notes, run_uuid),
                )
        except Exception as e:
            logger.error("Failed to finish run %s: %s", run_uuid, e)

    # ─── Query API ───

    def get_latest_results(self, decision=None, limit=30):
        """Return latest scan results for dashboard."""
        with _conn() as c:
            # Get latest run
            run = c.execute(
                "SELECT run_uuid, started_at, status, symbols_analyzed, avg_latency_ms, market_session, scan_type FROM gemini_scan_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not run:
                return {"items": [], "run": None}

            run_uuid = run["run_uuid"]
            sql = """
                SELECT * FROM gemini_decisions
                WHERE run_uuid = ?
            """
            params = [run_uuid]
            if decision:
                sql += " AND final_decision = ?"
                params.append(decision)
            sql += " ORDER BY fused_score DESC LIMIT ?"
            params.append(limit)

            rows = c.execute(sql, params).fetchall()
            items = [dict(r) for r in rows]

        return {
            "items": items,
            "run": {
                "run_uuid": run["run_uuid"],
                "started_at": run["started_at"],
                "status": run["status"],
                "symbols_analyzed": run["symbols_analyzed"],
                "avg_latency_ms": run["avg_latency_ms"],
                "market_session": run["market_session"],
                "scan_type": run["scan_type"],
            },
            "counts": {
                "buy_now": len([i for i in items if i["final_decision"] == "BUY_NOW"]),
                "wait": len([i for i in items if i["final_decision"] == "WAIT"]),
                "sell": len([i for i in items if i["final_decision"] == "SELL"]),
            },
        }

    def get_scan_status(self):
        """Return current scan progress or last completed."""
        if self.current_run:
            return {
                "scanning": True,
                **self.current_run,
            }
        with _conn() as c:
            run = c.execute(
                "SELECT * FROM gemini_scan_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if run:
                return {
                    "scanning": False,
                    "last_run": dict(run),
                    "circuit_breaker": self.circuit_breaker.state,
                }
        return {"scanning": False, "last_run": None}

    def get_symbol_history(self, symbol, days=7):
        """Historical Gemini analyses for one symbol."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        with _conn() as c:
            rows = c.execute(
                "SELECT * FROM gemini_decisions WHERE symbol = ? AND scan_time > ? ORDER BY scan_time DESC LIMIT 50",
                (symbol.upper(), cutoff),
            ).fetchall()
        return {"symbol": symbol, "history": [dict(r) for r in rows]}


def _parse_price(val):
    """Extract numeric price from Gemini's sometimes-text responses."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val
    import re
    m = re.search(r'[\d.]+', str(val))
    return float(m.group()) if m else None


# Module-level singleton
_scanner = None

def get_scanner():
    global _scanner
    if _scanner is None:
        _scanner = GeminiScanner()
    return _scanner
