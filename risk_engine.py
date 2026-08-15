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
    # Liquidity is a property of (stock, position size), so the flat
    # MIN_LIQUIDITY_VALUE = 5000 average is gone - checked 2026-08-15,
    # zero importers outside this class. What stays absolute is a floor
    # under which a stock is untradeable at any size; above it, the
    # per-position cap decides.
    LIQUIDITY_FLOOR_KWD = 1000        # median session value, KWD
    MAX_POSITION_LIQ_SHARE = 0.20     # consume at most 20% of a session
    MAX_POSITION_EXIT_SESSIONS = 3    # and be able to exit inside 3
    # D-10: the smallest slice worth calling "available to open with" -
    # below 1 percent of the book, can_open_new says no. 1,295 KWD left
    # of 144,000 is not an openable position, it is noise.
    MIN_OPEN_CAPITAL_PCT = 1.0

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
            liq = self._get_session_liq_value(sym)
            avg_value = liq.get("value_kwd")
            if liq.get("state") == "missing" or avg_value is None:
                # no dated liquidity figure: say so rather than let the symbol
                # through as if it had passed a check that never ran
                logger.warning("liquidity unknown for %s (%s) - not gating on it",
                               sym, liq.get("reason") or liq.get("source"))
            elif avg_value < self.LIQUIDITY_FLOOR_KWD:
                _age = ""
                if liq.get("state") == "stale":
                    _age = f" (بيانات {liq.get('as_of', '')[:10]})"
                self._downgrade(opp, "illiquid",
                                f"سيولة غائبة — وسيط الجلسة {avg_value:,.0f} د.ك{_age}")
                continue
            else:
                # Attach the cap for the sizing layer - no downgrade here,
                # because position size is unknown at this gate. state and
                # as_of ride along: a cap built on a stale price reads
                # stale, not confident.
                opp["max_position_kwd"] = round(
                    avg_value * self.MAX_POSITION_LIQ_SHARE
                    * self.MAX_POSITION_EXIT_SESSIONS)
                opp["max_position_state"] = liq.get("state")
                opp["max_position_as_of"] = liq.get("as_of")

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

    def _get_session_liq_value(self, symbol: str) -> dict:
        """Median session traded value in KWD, with the age of the answer.

        Two numbers of different vintage meet here. The price is live when a
        source answers - price_source reaches the bridge or Yahoo. The volume
        is liq_vol = min(median_20, median_60) from the stored census: a slow
        statistic, acceptable while under a week old, so it does not degrade
        the verdict by itself. combine() still enforces the contract - worst
        state, oldest as_of - because a value built on a stale price must
        read stale, or we rebuild the -2.51% lie from fresher parts.

        Returns {value_kwd, price, liq_vol, as_of, source, state}. value_kwd
        is None only when an input is truly absent; a genuine zero median
        passes through as 0 and fails the floor honestly.
        """
        from price_source import get_quote, combine

        quote = get_quote(symbol)

        liq_vol, vol_part = None, {"as_of": None, "source": "db", "state": "missing"}
        try:
            with _conn() as c:
                row = c.execute(
                    "SELECT liq_vol, avg_vol_as_of "
                    "FROM stock_radar_daily WHERE symbol=? "
                    "ORDER BY captured_at DESC LIMIT 1",
                    (symbol.upper(),),
                ).fetchone()
            if row and row["liq_vol"] is not None and row["avg_vol_as_of"]:
                # liq_vol = min(median_20, median_60) from the volume census.
                # The old fallback `avg_volume or volume` is gone with the old
                # threshold: it substituted one session turnover for an average
                # that was 0 in every row, so the check measured something
                # other than its name. A symbol without a census row now reads
                # missing - and says so - instead of borrowing a wrong number.
                liq_vol = float(row["liq_vol"])
                stamp = str(row["avg_vol_as_of"])
                # A median over 20-60 sessions moves slowly: a census under a
                # week old does not degrade the verdict; the price decides.
                _age_days = None
                try:
                    _dt = _iso(stamp)
                    if _dt is not None:
                        _age_days = (datetime.utcnow() - _dt).days
                except Exception:
                    pass
                vol_part = {"as_of": stamp, "source": "db",
                            "state": "live" if (_age_days is not None and _age_days <= 7)
                                     else "stale"}
        except Exception as e:
            logger.warning("liq_vol lookup failed for %s: %r", symbol, e)

        price = quote.get("close")
        out = combine(quote, vol_part, price=price, liq_vol=liq_vol)
        # price is in fils; 1 KWD = 1000 fils. liq_vol == 0 is a real
        # measurement (a median of zero-volume sessions) and must reach the
        # floor check as 0.0, not vanish into None.
        out["value_kwd"] = ((price * liq_vol) / 1000.0
                            if price and price > 0 and liq_vol is not None
                            else None)
        return out


def _iso(stamp):
    """Census as_of parser: ISO string (tz-aware or not) -> naive UTC."""
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(str(stamp))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


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
        # D-10: a single position above this share of capital is worth
        # saying out loud - never blocked, the user sizes his own book
        "max_single_position_pct": 40,
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
    total_risk_fils = 0.0
    no_stop = 0
    for p in positions:
        entry = p.get("entry_price", 0)
        stop = p.get("stop_loss", 0)
        qty = p.get("quantity", 0)
        if not entry or not qty:
            continue
        if stop and entry > stop:
            total_risk_fils += (entry - stop) * qty
        else:
            # No usable stop: the FULL position value is at risk. The old
            # code contributed 0 here, converting absence into "no risk"
            # inside a decision engine (PHASE2_SECTION_D, D-2).
            total_risk_fils += entry * qty
            no_stop += 1
    # Prices are fils, capital is KWD. The old code divided fils by KWD -
    # a 1000x overstatement that never fired only because no open trade
    # ever had a stop. total_risk_kwd now means what its name says.
    total_risk_kwd = total_risk_fils / 1000.0
    heat_pct = (total_risk_kwd / capital) * 100 if capital > 0 else 0
    heat_complete = no_stop == 0
    return {
        "capital": capital, "total_risk_kwd": round(total_risk_kwd, 3),
        "heat_pct": round(heat_pct, 1), "max_heat_pct": cfg["max_portfolio_heat_pct"],
        "within_limit": heat_pct <= cfg["max_portfolio_heat_pct"],
        "heat_complete": heat_complete,
        "positions_without_stop": no_stop,
        "heat_note": None if heat_complete else (
            "%d position(s) have no stop_loss; their full value is counted"
            " as at risk" % no_stop),
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
    deploy = _capital_deployment(positions, cfg)
    # D-12: a gate whose reasoning is invisible is a gate nobody can
    # audit. Every failing constraint is named; the wire carries them.
    _blockers = []
    if len(positions) >= int(cfg["max_open_positions"]):
        _blockers.append("slots: %d of %d positions open"
                         % (len(positions), int(cfg["max_open_positions"])))
    if not heat["within_limit"]:
        _blockers.append("heat: %.1f%% over the %.1f%% cap"
                         % (heat["heat_pct"], heat["max_heat_pct"]))
    if not heat.get("heat_complete", False):
        _blockers.append("heat incomplete: %s position(s) without a stop"
                         % heat.get("positions_without_stop"))
    _floor_kwd = (cfg.get("account_capital") or 0) * RiskEngine.MIN_OPEN_CAPITAL_PCT / 100
    if deploy["capital_available_kwd"] < _floor_kwd:
        _blockers.append(
            "capital floor: %s KWD available < %s KWD (%.0f%% of capital) - "
            "below that is noise, not a position"
            % (format(round(deploy["capital_available_kwd"]), ","),
               format(round(_floor_kwd), ","), RiskEngine.MIN_OPEN_CAPITAL_PCT))
    return {
        "capital": cfg["account_capital"],
        "risk_per_trade_pct": cfg["risk_per_trade_pct"],
        "open_positions": len(positions),
        "max_positions": int(cfg["max_open_positions"]),
        "can_open_new": not _blockers,
        "can_open_new_reason": "; ".join(_blockers) if _blockers else None,
        "portfolio_heat_pct": heat["heat_pct"],
        "max_heat_pct": heat["max_heat_pct"],
        "heat_complete": heat.get("heat_complete"),
        "positions_without_stop": heat.get("positions_without_stop"),
        "heat_note": heat.get("heat_note"),
        "capital_note": _capital_note(positions, cfg["account_capital"]),
        **deploy,
        "sector_exposure": sectors,
    }


def _capital_deployment(positions, cfg):
    """PHASE2_SECTION_D D-10: heat measures loss-if-stopped; this measures
    committed capital. Two different questions - both get asked now."""
    capital = cfg.get("account_capital") or 0
    vals = [((p.get("entry_price") or 0) * (p.get("quantity") or 0) / 1000.0, p)
            for p in positions]
    deployed = sum(v for v, _ in vals)
    out = {
        "capital_deployed_kwd": round(deployed, 1),
        "capital_deployed_pct": round(deployed / capital * 100, 1) if capital else None,
        "capital_available_kwd": round(capital - deployed, 1),
        "concentration_note": None,
    }
    share_cap = cfg.get("max_single_position_pct") or 40
    for v, p in vals:
        if capital and v / capital * 100 > share_cap:
            out["concentration_note"] = (
                "%s is %d%% of capital (limit note at %d%%) - not blocked,"
                " not silent" % (p.get("symbol"), round(v / capital * 100),
                                 share_cap))
            break
    return out


def _capital_note(positions, capital):
    """PHASE2_SECTION_D D-8: a single position larger than stated capital
    means the capital figure is stale or sizing has no ceiling - either
    way, say it instead of sizing silently past it."""
    if not capital or capital <= 0:
        return "account_capital is not set"
    for p in positions:
        entry, qty = p.get("entry_price") or 0, p.get("quantity") or 0
        val = entry * qty / 1000.0
        if val > capital:
            return ("position %s is %s KWD = %d%% of stated capital %s KWD - "
                    "capital figure stale or sizing unchecked"
                    % (p.get("symbol"), format(round(val), ","),
                       round(val / capital * 100), format(round(capital), ",")))
    return None
