"""
sr_engine.py — Support & Resistance Engine.
Computes S/R levels from swing high/low clustering.
Can use Bridge daily bars or fall back to stock_radar_daily.
"""
import os
import sqlite3
import logging
import json
from datetime import datetime

logger = logging.getLogger("sr_engine")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def init_sr_schema():
    """Add sr columns to stock_profiles if not exist."""
    conn = _conn()
    for col in [
        "ALTER TABLE stock_profiles ADD COLUMN sr_json TEXT",
        "ALTER TABLE stock_profiles ADD COLUMN sr_updated_at TEXT",
    ]:
        try:
            conn.execute(col)
        except Exception:
            pass
    conn.commit()
    conn.close()


def find_pivots(bars, left=3, right=3):
    """Find swing highs and swing lows from OHLC bars."""
    highs = []
    lows  = []
    for i in range(left, len(bars) - right):
        h  = bars[i].get("high") or bars[i].get("h") or 0
        lo = bars[i].get("low")  or bars[i].get("l") or 0

        is_high = all(
            h >= (bars[j].get("high") or bars[j].get("h") or 0)
            for j in range(i - left, i + right + 1) if j != i
        )
        is_low = all(
            lo <= (bars[j].get("low") or bars[j].get("l") or 0)
            for j in range(i - left, i + right + 1) if j != i
        )

        if is_high:
            highs.append({"index": i, "price": round(h, 3),  "volume": bars[i].get("volume", 0)})
        if is_low:
            lows.append({"index":  i, "price": round(lo, 3), "volume": bars[i].get("volume", 0)})

    return highs, lows


def cluster_levels(levels, tolerance_pct=1.5):
    """Group nearby price levels into clusters. Returns sorted by score (strength)."""
    if not levels:
        return []
    levels = sorted(levels, key=lambda x: x["price"])
    clusters = []
    current  = [levels[0]]

    for lev in levels[1:]:
        avg  = sum(x["price"] for x in current) / len(current)
        diff = abs(lev["price"] - avg) / avg * 100 if avg > 0 else 999
        if diff <= tolerance_pct:
            current.append(lev)
        else:
            clusters.append(current)
            current = [lev]
    clusters.append(current)

    result = []
    for cl in clusters:
        avg_p   = round(sum(x["price"] for x in cl) / len(cl), 3)
        touches = len(cl)
        latest  = max(x["index"] for x in cl)
        avg_vol = sum(x.get("volume", 0) for x in cl) / max(1, len(cl))
        # Score: more touches + more recent + more volume = stronger level
        score = round(touches * 3 + (latest * 0.1) + (avg_vol / 1_000_000), 2)
        result.append({
            "price":        avg_p,
            "touches":      touches,
            "score":        score,
            "latest_index": latest,
        })
    return sorted(result, key=lambda x: x["score"], reverse=True)


def compute_sr(symbol, bars, current_price):
    """
    Compute support and resistance for a symbol from OHLC bars.
    Returns dict with key_support, key_resistance, and all levels.
    """
    if not bars or len(bars) < 20:
        return {
            "symbol": symbol, "key_support": None, "key_resistance": None,
            "support_levels": [], "resistance_levels": [],
        }

    pivot_highs, pivot_lows = find_pivots(bars, left=3, right=3)
    sup_clusters = cluster_levels(pivot_lows,  tolerance_pct=1.5)
    res_clusters = cluster_levels(pivot_highs, tolerance_pct=1.5)

    # Nearest support below current price
    sups_below = [s for s in sup_clusters if s["price"] < current_price]
    key_sup    = max(sups_below, key=lambda x: x["price"], default=None)

    # Nearest resistance above current price
    res_above = [r for r in res_clusters if r["price"] > current_price]
    key_res   = min(res_above, key=lambda x: x["price"], default=None)

    return {
        "symbol":                  symbol,
        "current_price":           current_price,
        "key_support":             key_sup["price"]   if key_sup else None,
        "key_support_touches":     key_sup["touches"] if key_sup else 0,
        "key_support_score":       key_sup["score"]   if key_sup else 0,
        "key_resistance":          key_res["price"]   if key_res else None,
        "key_resistance_touches":  key_res["touches"] if key_res else 0,
        "key_resistance_score":    key_res["score"]   if key_res else 0,
        "support_levels":          [s["price"] for s in sup_clusters[:5]],
        "resistance_levels":       [r["price"] for r in res_clusters[:5]],
    }


def refresh_sr_for_all(bridge_data=None):
    """
    Refresh S/R for all symbols.
    bridge_data: dict of {symbol: {bars: [...], price: X}} from Bridge API.
    If None, falls back to support/resistance from stock_radar_daily.
    """
    init_sr_schema()
    conn    = _conn()
    updated = 0

    if bridge_data:
        for sym, data in bridge_data.items():
            bars  = data.get("bars", [])
            price = data.get("price", 0)
            if not bars or not price:
                continue
            sr = compute_sr(sym, bars, price)
            conn.execute(
                "UPDATE stock_profiles SET key_support=?, key_resistance=?, sr_json=?, sr_updated_at=? WHERE symbol=?",
                (sr["key_support"], sr["key_resistance"],
                 json.dumps(sr), datetime.utcnow().isoformat(), sym)
            )
            updated += 1
    else:
        # Fallback: use support/resistance from stock_radar_daily
        rows = conn.execute(
            "SELECT symbol, support, resistance, price FROM stock_radar_daily WHERE support IS NOT NULL"
        ).fetchall()
        for r in rows:
            conn.execute(
                "UPDATE stock_profiles SET key_support=?, key_resistance=? WHERE symbol=?",
                (r["support"], r["resistance"], r["symbol"])
            )
            updated += 1

    conn.commit()
    conn.close()
    logger.info(f"S/R refreshed for {updated} symbols")
    return {"updated": updated}
