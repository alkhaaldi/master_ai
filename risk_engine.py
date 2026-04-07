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


# ═══════════════════════════════════════════════════
# Trading V2 Phase 2: Enhanced Risk Engine
# ═══════════════════════════════════════════════════
STOCK_SECTORS = {
    "INOVEST": "financial_services", "URC": "industrial", "ACICO": "industrial",
    "AAYANRE": "real_estate", "OOREDOO": "telecom", "ALFTAQA": "financial_services",
    "NINV": "financial_services", "MUBARRAD": "industrial",
    "NRE": "real_estate", "RASIYAT": "real_estate",
}
SECTOR_NAMES_AR = {
    "financial_services": "\u062e\u062f\u0645\u0627\u062a \u0645\u0627\u0644\u064a\u0629",
    "industrial": "\u0635\u0646\u0627\u0639\u064a",
    "real_estate": "\u0639\u0642\u0627\u0631\u064a",
    "telecom": "\u0627\u062a\u0635\u0627\u0644\u0627\u062a",
    "unknown": "\u063a\u064a\u0631 \u0645\u062d\u062f\u062f",
}


def _get_risk_config() -> dict:
    defaults = {
        "account_capital": 10000, "risk_per_trade_pct": 2.0,
        "max_open_positions": 3, "max_portfolio_heat_pct": 6.0,
        "max_sector_positions": 2,
    }
    try:
        c = _conn()
        for k, v in c.execute("SELECT key, value FROM risk_config").fetchall():
            defaults[k] = v
        c.close()
    except Exception:
        pass
    return defaults


def calculate_position_size(entry_price: float, stop_price: float,
                            capital: float = None, risk_pct: float = None) -> dict:
    cfg = _get_risk_config()
    capital = capital or cfg["account_capital"]
    risk_pct = risk_pct or cfg["risk_per_trade_pct"]
    risk_kwd = capital * (risk_pct / 100)
    risk_per_share = entry_price - stop_price
    if risk_per_share <= 0 or entry_price <= 0:
        return {"shares": 0, "position_value_kwd": 0, "risk_kwd": 0,
                "risk_per_share": 0, "pct_of_capital": 0}
    shares = int(risk_kwd / risk_per_share)
    position_value = shares * entry_price
    return {
        "shares": shares, "position_value_kwd": round(position_value, 3),
        "risk_kwd": round(risk_kwd, 3), "risk_per_share": round(risk_per_share, 3),
        "pct_of_capital": round((position_value / capital) * 100, 1),
    }


def _get_open_positions() -> list:
    try:
        c = _conn()
        rows = c.execute(
            "SELECT symbol, entry_price, quantity, stop_loss FROM trades WHERE status='open'"
        ).fetchall()
        c.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_portfolio_heat() -> dict:
    cfg = _get_risk_config()
    capital = cfg["account_capital"]
    positions = _get_open_positions()
    total_risk = 0
    for p in positions:
        entry = p.get("entry_price", 0)
        stop = p.get("stop_loss", 0)
        qty = p.get("quantity", 0)
        if entry and stop and qty and entry > stop:
            total_risk += (entry - stop) * qty
    heat_pct = (total_risk / capital) * 100 if capital > 0 else 0
    return {
        "capital": capital, "total_risk_kwd": round(total_risk, 3),
        "heat_pct": round(heat_pct, 1), "max_heat_pct": cfg["max_portfolio_heat_pct"],
        "within_limit": heat_pct <= cfg["max_portfolio_heat_pct"],
    }


def get_sector_exposure(positions: list = None) -> dict:
    cfg = _get_risk_config()
    max_per_sector = int(cfg.get("max_sector_positions", 2))
    positions = positions or _get_open_positions()
    sectors = {}
    for p in positions:
        sym = (p.get("symbol") or "").upper()
        sector = STOCK_SECTORS.get(sym, "unknown")
        sectors.setdefault(sector, []).append(sym)
    return {
        s: {"count": len(syms), "symbols": syms, "max": max_per_sector,
            "full": len(syms) >= max_per_sector,
            "name_ar": SECTOR_NAMES_AR.get(s, s)}
        for s, syms in sectors.items()
    }


def check_can_open(symbol: str, entry_price: float = 0, stop_price: float = 0) -> dict:
    cfg = _get_risk_config()
    positions = _get_open_positions()
    heat = get_portfolio_heat()
    sector_exp = get_sector_exposure(positions)
    sym_upper = symbol.upper()
    sym_sector = STOCK_SECTORS.get(sym_upper, "unknown")
    checks = {
        "max_positions": {"ok": len(positions) < int(cfg["max_open_positions"]),
                          "current": len(positions), "max": int(cfg["max_open_positions"])},
        "portfolio_heat": {"ok": heat["within_limit"],
                           "current_pct": heat["heat_pct"], "max_pct": heat["max_heat_pct"]},
        "sector": {"ok": not sector_exp.get(sym_sector, {}).get("full", False),
                   "sector": sym_sector,
                   "sector_ar": SECTOR_NAMES_AR.get(sym_sector, sym_sector),
                   "current": sector_exp.get(sym_sector, {}).get("count", 0),
                   "max": int(cfg.get("max_sector_positions", 2))},
        "not_duplicate": {"ok": sym_upper not in [p["symbol"].upper() for p in positions]},
    }
    sizing = {}
    if entry_price and stop_price and entry_price > stop_price:
        sizing = calculate_position_size(entry_price, stop_price)
    can_open = all(c["ok"] for c in checks.values())
    return {
        "symbol": sym_upper, "can_open": can_open, "checks": checks,
        "reasons": [k for k, v in checks.items() if not v["ok"]],
        "sizing": sizing, "heat": heat, "sector_exposure": sector_exp, "config": cfg,
    }


def get_risk_status() -> dict:
    cfg = _get_risk_config()
    positions = _get_open_positions()
    heat = get_portfolio_heat()
    sectors = get_sector_exposure(positions)
    return {
        "capital": cfg["account_capital"],
        "risk_per_trade_pct": cfg["risk_per_trade_pct"],
        "open_positions": len(positions),
        "max_positions": int(cfg["max_open_positions"]),
        "can_open_new": len(positions) < int(cfg["max_open_positions"]) and heat["within_limit"],
        "portfolio_heat_pct": heat["heat_pct"],
        "max_heat_pct": heat["max_heat_pct"],
        "sector_exposure": sectors,
    }
