"""
risk_engine.py — Risk Gate Engine
Phase 3 of Master Plan V10

Prevents over-concentration, over-trading, and low-liquidity entries.
Runs after Smart Trade Decision, before final ranking.
"""

import os
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger("risk_engine")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=5)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


class RiskEngine:
    """
    Risk gate that modifies opportunities based on portfolio constraints.

    Rules:
    1. Max 2 stocks from the same sector can be ENTER
    2. Max 8 total open positions
    3. No duplicate — if stock already in portfolio, no ENTER
    4. Low liquidity stocks (<5000 KWD daily avg) downgraded to WAIT
    """

    MAX_SAME_SECTOR = 2
    MAX_TOTAL_POSITIONS = 8
    MIN_LIQUIDITY_VALUE = 5000  # KWD daily average

    def apply_risk_gate(self, opportunities: list, open_positions: list = None) -> list:
        """
        Apply risk checks to all opportunities.
        Modifies opportunities in-place (downgrades ENTER → WAIT where needed).
        Returns the same list.

        Args:
            opportunities: list of opportunity dicts from scan_opportunities
            open_positions: list of open trade dicts from journal_engine.get_open_trades()
        """
        from sector_map import get_sector

        if open_positions is None:
            open_positions = []

        # ── Build current portfolio state ────────────────
        portfolio_symbols = set()
        sector_count = {}  # sectors already in portfolio
        for pos in open_positions:
            sym = (pos.get("symbol") or "").upper()
            if sym:
                portfolio_symbols.add(sym)
                sec = get_sector(sym)
                sector_count[sec] = sector_count.get(sec, 0) + 1

        total_open = len(open_positions)

        # Track how many new ENTERs per sector we're allowing
        enter_by_sector = {}

        for opp in opportunities:
            sym = (opp.get("symbol") or "").upper()

            # Attach sector to every opportunity
            sec = get_sector(sym)
            opp["sector"] = sec

            # Only check ENTER decisions
            if opp.get("smart_decision") != "ENTER":
                continue

            # ── Check 1: Duplicate position ──────────────
            if sym in portfolio_symbols:
                self._downgrade(opp, "duplicate_position",
                                "عندك مركز مفتوح بنفس السهم")
                continue

            # ── Check 2: Max total positions ─────────────
            new_enters_total = sum(enter_by_sector.values())
            if total_open + new_enters_total >= self.MAX_TOTAL_POSITIONS:
                self._downgrade(opp, "max_positions",
                                f"المحفظة مليانة — {total_open} مركز مفتوح (الحد {self.MAX_TOTAL_POSITIONS})")
                continue

            # ── Check 3: Sector concentration ────────────
            existing_in_sector = sector_count.get(sec, 0)
            new_in_sector = enter_by_sector.get(sec, 0)
            if existing_in_sector + new_in_sector >= self.MAX_SAME_SECTOR:
                self._downgrade(opp, "sector_concentration",
                                f"تركّز بقطاع {sec} — عندك {existing_in_sector} مركز + {new_in_sector} جديد")
                continue

            # ── Check 4: Liquidity ───────────────────────
            avg_value = self._get_avg_daily_value(sym)
            if avg_value is not None and avg_value < self.MIN_LIQUIDITY_VALUE:
                self._downgrade(opp, "low_liquidity",
                                f"سيولة ضعيفة — متوسط التداول {avg_value:,.0f} د.ك/يوم")
                continue

            # ✅ Passed all checks — allow ENTER
            enter_by_sector[sec] = enter_by_sector.get(sec, 0) + 1

        return opportunities

    def _downgrade(self, opp: dict, flag: str, reason_ar: str):
        """Downgrade ENTER → WAIT with risk flag."""
        opp["smart_decision"]    = "WAIT"
        opp["smart_decision_ar"] = "\u23f3 \u0627\u0646\u062a\u0638\u0631"
        opp["smart_reason_ar"]   = reason_ar
        opp["opportunity_type"]  = "\u23f3 \u0627\u0646\u062a\u0638\u0631"
        opp["risk_flag"]         = flag
        opp["confidence"]        = min(opp.get("confidence", 0), 75)
        logger.info("Risk gate: %s downgraded to WAIT (%s): %s",
                     opp.get("symbol"), flag, reason_ar)

    def _get_avg_daily_value(self, symbol: str):
        """
        Get average daily traded value (KWD) for a symbol.
        Uses avg_volume × price from stock_radar_daily.
        Returns KWD value or None if unavailable.
        """
        try:
            with _conn() as c:
                row = c.execute(
                    "SELECT price, avg_volume, volume FROM stock_radar_daily WHERE symbol=? ORDER BY rowid DESC LIMIT 1",
                    (symbol.upper(),),
                ).fetchone()
                if row:
                    price = float(row["price"] or 0)
                    avg_vol = float(row["avg_volume"] or row["volume"] or 0)
                    if price > 0 and avg_vol > 0:
                        # price is in fils (1 KWD = 1000 fils)
                        return (price * avg_vol) / 1000.0  # KWD
        except Exception as e:
            logger.debug("Avg daily value lookup failed for %s: %s", symbol, e)
        return None


def calculate_position_risk(entry_price: float, stop_loss: float, target: float = 0,
                            capital: float = 1000) -> dict:
    """
    Calculate risk/reward and position size for a trade.
    Safe against ZeroDivisionError when entry == stop.
    """
    if not entry_price or entry_price <= 0:
        return {"error": "invalid entry_price", "risk_reward": 0, "position_size": 0}
    if not stop_loss or stop_loss <= 0:
        return {"error": "invalid stop_loss", "risk_reward": 0, "position_size": 0}
    if abs(entry_price - stop_loss) < 0.001:
        return {"error": "entry equals stop loss", "risk_reward": 0, "position_size": 0}

    risk = abs(entry_price - stop_loss)
    risk_pct = (risk / entry_price) * 100
    reward = abs(target - entry_price) if target and target > entry_price else 0
    rr = round(reward / risk, 2) if risk > 0 else 0

    # Position size: risk 1% of capital
    risk_amount = capital * 0.01
    position_size = int(risk_amount / risk) if risk > 0 else 0

    return {
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "target": target,
        "risk_per_share": round(risk, 3),
        "risk_pct": round(risk_pct, 2),
        "reward_per_share": round(reward, 3),
        "risk_reward": rr,
        "position_size": position_size,
        "capital_at_risk": round(risk * position_size, 2),
    }
