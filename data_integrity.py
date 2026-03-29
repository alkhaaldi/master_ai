"""
data_integrity.py — Data Integrity Gate for Trading Decisions
Phase 1 of Master Plan V10

Checks data freshness, quality, and S/R availability before allowing
the system to make trading decisions. Prevents false signals from stale data.
"""

import os
import time
import sqlite3
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("data_integrity")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=5)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


# ═══════════════════════════════════════════════════
# FRESHNESS THRESHOLDS
# ════════════���══════════════════════════════════════

# Bridge live: <5 min = fresh
FRESH_THRESHOLD_SEC = 300
# Radar daily: <26 hours = stale_1d (acceptable for daily timeframe)
STALE_1D_THRESHOLD_SEC = 26 * 3600
# Anything older = stale_old (unreliable)
STALE_OLD_THRESHOLD_SEC = 72 * 3600


class DataIntegrityGate:
    """
    Gate that checks data quality before trading decisions.

    Usage:
        gate = DataIntegrityGate()
        result = gate.check(symbol, live_data)
        # result = {
        #   "freshness": "fresh" | "stale_1d" | "stale_old" | "missing",
        #   "quality_score": 0-100,
        #   "sr_status": "valid" | "stale" | "missing",
        #   "gate_decision": "allow_all" | "wait_only" | "force_skip",
        #   "fallback_levels": None | {"stop": ..., "target1": ..., "target2": ...},
        # }
    """

    def check(self, symbol: str, live: dict, sr_data: dict = None) -> dict:
        """Run all integrity checks for a symbol."""
        freshness = self.check_freshness(symbol, live)
        sr_status = self.check_sr_quality(symbol, live, sr_data)
        quality = self.get_quality_score(symbol, live, freshness, sr_status)
        gate = self.gate_decision(symbol, quality)

        # Compute fallback S/R if needed
        fallback = None
        if sr_status in ("stale", "missing"):
            price = float(live.get("price") or 0)
            atr = float(live.get("atr_14") or live.get("atr") or 0)
            if price > 0 and atr > 0:
                fallback = self.compute_fallback_levels(price, atr)

        return {
            "freshness": freshness,
            "quality_score": quality,
            "sr_status": sr_status,
            "gate_decision": gate,
            "fallback_levels": fallback,
        }

    # ───────────────────────────────────────────────
    # 1. FRESHNESS
    # ─��────────────────────���────────────────────────

    def check_freshness(self, symbol: str, live: dict = None) -> str:
        """
        Check how fresh the price data is.
        Returns: 'fresh' | 'stale_1d' | 'stale_old' | 'missing'
        """
        symbol = symbol.upper()

        # Method 1: Bridge cache timestamp
        age_sec = self._get_bridge_age(symbol)
        if age_sec is not None:
            if age_sec <= FRESH_THRESHOLD_SEC:
                return "fresh"
            elif age_sec <= STALE_1D_THRESHOLD_SEC:
                return "stale_1d"
            elif age_sec <= STALE_OLD_THRESHOLD_SEC:
                return "stale_old"
            else:
                return "stale_old"

        # Method 2: Radar daily updated_at
        age_sec = self._get_radar_daily_age(symbol)
        if age_sec is not None:
            if age_sec <= STALE_1D_THRESHOLD_SEC:
                return "stale_1d"
            elif age_sec <= STALE_OLD_THRESHOLD_SEC:
                return "stale_old"
            else:
                return "stale_old"

        # Method 3: Check if live dict has price at all
        if live and live.get("price"):
            # We have data but can't verify age — assume stale_1d
            return "stale_1d"

        return "missing"

    def _get_bridge_age(self, symbol: str):
        """Get age in seconds from bridge cache. Returns None if not cached."""
        try:
            from bridge_client import get_bridge_client
            client = get_bridge_client()
            for key, entry in client._cache.items():
                if key.startswith("analysis:") and key.split(":")[-1] == symbol:
                    ts = entry.get("ts", 0)
                    if ts > 0:
                        return time.time() - ts
            # Also check quote cache
            for key, entry in client._cache.items():
                if key.startswith("quote:") and key.split(":")[-1] == symbol:
                    ts = entry.get("ts", 0)
                    if ts > 0:
                        return time.time() - ts
        except Exception:
            pass
        return None

    def _get_radar_daily_age(self, symbol: str):
        """Get age in seconds from stock_radar_daily.updated_at."""
        try:
            with _conn() as c:
                row = c.execute(
                    "SELECT updated_at FROM stock_radar_daily WHERE symbol=? ORDER BY rowid DESC LIMIT 1",
                    (symbol,),
                ).fetchone()
                if row and row["updated_at"]:
                    updated_str = row["updated_at"]
                    # SQLite CURRENT_TIMESTAMP format: YYYY-MM-DD HH:MM:SS
                    updated_dt = datetime.strptime(updated_str[:19], "%Y-%m-%d %H:%M:%S")
                    return (datetime.utcnow() - updated_dt).total_seconds()
        except Exception as e:
            logger.debug("radar_daily age check failed for %s: %s", symbol, e)
        return None

    # ─────────���─────────────────────────────────────
    # 2. QUALITY SCORE
    # ───────────────���───────────────────────────────

    def get_quality_score(self, symbol: str, live: dict,
                          freshness: str = None, sr_status: str = None) -> int:
        """
        Composite quality score 0-100.
        Based on: freshness, indicator completeness, S/R status, volume.
        """
        score = 0

        # --- Freshness (0-35 points) ---
        if freshness is None:
            freshness = self.check_freshness(symbol, live)
        freshness_points = {
            "fresh": 35,
            "stale_1d": 20,
            "stale_old": 5,
            "missing": 0,
        }
        score += freshness_points.get(freshness, 0)

        # --- Indicator completeness (0-35 points) ---
        # Check which critical indicators are present and non-zero
        indicators_numeric = {
            "price": live.get("price"),
            "rsi_14": live.get("rsi_14") or live.get("rsi"),
            "adx": live.get("adx"),
            "atr_14": live.get("atr_14") or live.get("atr"),
            "vol_ratio": live.get("vol_ratio"),
            "stoch_k": live.get("stoch_k"),
        }
        indicators_text = {
            "macd_state": live.get("macd_state"),
        }
        present = sum(1 for v in indicators_numeric.values() if v and float(v) != 0)
        present += sum(1 for v in indicators_text.values() if v)
        total = len(indicators_numeric) + len(indicators_text)
        score += round((present / total) * 35)

        # --- S/R status (0-20 points) ---
        if sr_status is None:
            sr_status = self.check_sr_quality(symbol, live)
        sr_points = {"valid": 20, "stale": 10, "missing": 0}
        score += sr_points.get(sr_status, 0)

        # --- Volume sanity (0-10 points) ---
        vol = float(live.get("vol_ratio") or 0)
        if vol >= 0.5:
            score += 10
        elif vol >= 0.2:
            score += 5

        return min(score, 100)

    # ──��──────────────────────────────��─────────────
    # 3. S/R QUALITY
    # ──────────────���────────────────────────────────

    def check_sr_quality(self, symbol: str, live: dict = None,
                         sr_data: dict = None) -> str:
        """
        Check support/resistance data quality.
        Returns: 'valid' | 'stale' | 'missing'
        """
        symbol = symbol.upper()

        # Check from sr_data (passed from profile.sr_json)
        if sr_data:
            sup = sr_data.get("key_support")
            res = sr_data.get("key_resistance")
            if sup and res and float(sup) > 0 and float(res) > 0:
                # Check if S/R levels make sense vs price
                price = float(live.get("price") or 0) if live else 0
                if price > 0:
                    sup_f = float(sup)
                    res_f = float(res)
                    # S/R should bracket the price somewhat reasonably
                    if sup_f < price * 1.5 and res_f > price * 0.5:
                        return "valid"
                    else:
                        return "stale"  # levels exist but look outdated
                return "valid"

        # Check from live data
        if live:
            sup = float(live.get("support") or 0)
            res = float(live.get("resistance") or 0)
            if sup > 0 and res > 0:
                return "valid"
            elif sup > 0 or res > 0:
                return "stale"  # partial data

        # Check from DB
        try:
            with _conn() as c:
                row = c.execute(
                    "SELECT support, resistance FROM stock_radar_daily WHERE symbol=? ORDER BY rowid DESC LIMIT 1",
                    (symbol,),
                ).fetchone()
                if row:
                    s = float(row["support"] or 0)
                    r = float(row["resistance"] or 0)
                    if s > 0 and r > 0:
                        return "valid"
                    elif s > 0 or r > 0:
                        return "stale"
        except Exception:
            pass

        return "missing"

    # ─────���──────────────────────────────���──────────
    # 4. GATE DECISION
    # ─────────────────────────────��─────────────────

    def gate_decision(self, symbol: str, quality_score: int) -> str:
        """
        Decide what the system is allowed to do based on data quality.
        Returns: 'allow_all' | 'wait_only' | 'force_skip'

        Thresholds:
          ≥60 → allow_all   (data good enough for full decisions)
          ≥30 → wait_only   (data incomplete, only WAIT allowed, no ENTER)
          <30 → force_skip  (data too bad, skip entirely)
        """
        if quality_score >= 60:
            return "allow_all"
        elif quality_score >= 30:
            return "wait_only"
        else:
            return "force_skip"

    # ─────────────────────────────────────���─────────
    # 5. FALLBACK S/R LEVELS
    # ───────────────────────────────────────────────

    @staticmethod
    def compute_fallback_levels(price: float, atr: float) -> dict:
        """
        Compute fallback stop/target when S/R data is missing.
        Uses ATR-based levels:
          stop    = price - 1.5 × ATR
          target1 = price + 2.0 × ATR
          target2 = price + 3.5 × ATR
        """
        if price <= 0 or atr <= 0:
            return None
        return {
            "stop": round(price - 1.5 * atr, 3),
            "target1": round(price + 2.0 * atr, 3),
            "target2": round(price + 3.5 * atr, 3),
            "method": "atr_fallback",
        }
