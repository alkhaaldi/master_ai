#!/usr/bin/env python3
"""Backfill daily_bars from Yahoo history and refresh stock_radar_daily.

Per symbol (131 mapped; PAPER has no Yahoo listing and is skipped):
- fetch 1y of daily bars (the extra months are indicator warm-up only)
- INSERT OR REPLACE sessions 2026-04-02..today into daily_bars, source
  "yahoo", is_final=1 - these are completed-session closes
- UPDATE the symbol's single stock_radar_daily row (PK symbol+exchange):
  price/volume/change_pct + RSI14, EMA9/21, MACD(12,26,9) computed over
  the full series, captured_at = the bar's own timestamp from the source,
  market_was_open=0 (verified closing values). Columns outside that list
  - trend, verdict, score, the liquidity census - are not touched.
- the four recovered symbols with no row yet are INSERTed, their
  liquidity census columns filled from _tools/liquidity_median.json with
  that census's own as_of.

Sweep rules honoured: sentinel (EQUIPMENT) every 10 requests - on sentinel
failure the sweep STOPS and later symbols are recorded as not_scanned,
never as failures; errors are classified by name; one commit per symbol.
"""
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, "/home/pi/master_ai")
from price_source import _yahoo_opener, _UA, YAHOO_TIMEOUT

BASE = "/home/pi/master_ai"
DB = BASE + "/data/life.db"
FROM_DATE = "2026-04-02"


def fetch_bars(symbol):
    """1y of daily bars. Returns (bars, error_name). bars = list of
    (trading_date, ts_iso, open, high, low, close, volume)."""
    url = ("https://query2.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(symbol + ".KW") + "?range=1y&interval=1d")
    try:
        with _yahoo_opener().open(urllib.request.Request(url, headers=_UA),
                                  timeout=YAHOO_TIMEOUT) as f:
            res = json.loads(f.read().decode())["chart"]["result"][0]
    except urllib.error.HTTPError as e:
        return None, ("not_found" if e.code == 404
                      else "rate_limited" if e.code == 429
                      else "forbidden" if e.code in (401, 403)
                      else "http_%d" % e.code)
    except urllib.error.URLError:
        return None, "timeout"
    except (OSError, json.JSONDecodeError, KeyError, IndexError, TypeError):
        return None, "bad_payload"
    stamps = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    if not stamps:
        return None, "empty_result"
    bars = []
    for i, ts in enumerate(stamps):
        c = (q.get("close") or [])[i] if i < len(q.get("close") or []) else None
        if c is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        bars.append((dt.strftime("%Y-%m-%d"), dt.isoformat(),
                     (q.get("open") or [])[i], (q.get("high") or [])[i],
                     (q.get("low") or [])[i], float(c),
                     (q.get("volume") or [])[i]))
    return (bars, None) if bars else (None, "empty_result")


def ema_series(vals, n):
    if len(vals) < n:
        return [None] * len(vals)
    out = [None] * (n - 1)
    seed = sum(vals[:n]) / n
    out.append(seed)
    k = 2.0 / (n + 1)
    for v in vals[n:]:
        seed = v * k + seed * (1 - k)
        out.append(seed)
    return out


def rsi14(vals):
    n = 14
    if len(vals) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = vals[i] - vals[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / n, losses / n
    for i in range(n + 1, len(vals)):
        d = vals[i] - vals[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
    if al == 0:
        return 100.0
    return round(100 - 100 / (1 + ag / al), 2)


def _wilder(seed_vals, rest, n):
    a = sum(seed_vals) / n
    out = [a]
    for v in rest:
        a = (a * (n - 1) + v) / n
        out.append(a)
    return out


def full_indicators(bars):
    """ADX(14), ATR(14), Stoch %K(14), BB(20,2) bandwidth+squeeze,
    rolling 20-bar support/resistance. All from daily_bars OHLC -
    mathematics, zero tokens. None-safe."""
    H = [b[3] for b in bars]
    L = [b[4] for b in bars]
    C = [b[5] for b in bars]
    out = {}
    if len(C) < 30 or any(v is None for v in H[-30:]) or any(v is None for v in L[-30:]):
        return out
    n = 14
    trs, pdms, ndms = [], [], []
    for i in range(1, len(C)):
        hi, lo, pc = H[i], L[i], C[i - 1]
        if hi is None or lo is None or pc is None:
            hi, lo, pc = C[i], C[i], pc or C[i]
        trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
        up = (H[i] or 0) - (H[i - 1] or 0)
        dn = (L[i - 1] or 0) - (L[i] or 0)
        pdms.append(up if up > dn and up > 0 else 0.0)
        ndms.append(dn if dn > up and dn > 0 else 0.0)
    if len(trs) < n * 2:
        return out
    atr_s = _wilder(trs[:n], trs[n:], n)
    out["atr"] = round(atr_s[-1], 6)
    pdm_s = _wilder(pdms[:n], pdms[n:], n)
    ndm_s = _wilder(ndms[:n], ndms[n:], n)
    dxs = []
    for a, p, m in zip(atr_s, pdm_s, ndm_s):
        if a <= 0:
            dxs.append(0.0)
            continue
        pdi, ndi = 100 * p / a, 100 * m / a
        dxs.append(100 * abs(pdi - ndi) / (pdi + ndi) if (pdi + ndi) else 0.0)
    if len(dxs) >= n * 2:
        adx_s = _wilder(dxs[:n], dxs[n:], n)
        out["adx"] = round(adx_s[-1], 6)
    hh, ll = max(h for h in H[-n:] if h is not None), min(l for l in L[-n:] if l is not None)
    if hh > ll:
        out["stoch_k"] = round(100 * (C[-1] - ll) / (hh - ll), 6)
    w = [c for c in C[-20:] if c is not None]
    if len(w) == 20:
        mid = sum(w) / 20
        sd = (sum((c - mid) ** 2 for c in w) / 20) ** 0.5
        if mid > 0:
            bw = round(400 * sd / mid, 6)      # (upper-lower)/mid*100 = 4*sd/mid*100
            out["bb_bandwidth"] = bw
            # squeeze threshold declared here: bandwidth under 12 percent
            out["bb_squeeze"] = 1 if bw < 12 else 0
    lows20 = [l for l in L[-21:-1] if l is not None]
    highs20 = [h for h in H[-21:-1] if h is not None]
    if lows20 and highs20:
        out["support"] = round(min(lows20), 6)
        out["resistance"] = round(max(highs20), 6)
    return out


def declared_confluence(ind, vol_ratio):
    """Confluence from the store with SIMPLE DECLARED weights - written
    here and nowhere else, by user decision 2026-08-15. NOT the learned
    indicator_performance weights: their basis is the suspect hit/miss
    sample (Section C, C-27). Six equal votes, one rule each:

        ema9 > ema21 . macd > signal . macd > 0
        rsi > 50 . stoch_k > 50 . vol_ratio > 1

    score = 100 * bullish_votes / votes_present (absent indicators do not
    vote and are not fabricated). direction: >=60 bullish, <=40 bearish.
    """
    votes = []
    if ind.get("ema_fast") is not None and ind.get("ema_slow") is not None:
        votes.append(1 if ind["ema_fast"] > ind["ema_slow"] else 0)
    if ind.get("macd") is not None and ind.get("macd_signal") is not None:
        votes.append(1 if ind["macd"] > ind["macd_signal"] else 0)
    if ind.get("macd") is not None:
        votes.append(1 if ind["macd"] > 0 else 0)
    if ind.get("rsi") is not None:
        votes.append(1 if ind["rsi"] > 50 else 0)
    if ind.get("stoch_k") is not None:
        votes.append(1 if ind["stoch_k"] > 50 else 0)
    if vol_ratio is not None:
        votes.append(1 if vol_ratio > 1 else 0)
    if not votes:
        return {}
    score = round(100 * sum(votes) / len(votes))
    direction = "bullish" if score >= 60 else ("bearish" if score <= 40 else "neutral")
    return {"confluence_score": score, "confluence_direction": direction}


def indicators(closes):
    """RSI14, EMA9/21, MACD(12,26,9) at the last bar. None-safe."""
    if len(closes) < 35:
        return {}
    e9 = ema_series(closes, 9)
    e21 = ema_series(closes, 21)
    e12 = ema_series(closes, 12)
    e26 = ema_series(closes, 26)
    macd_s = [a - b for a, b in zip(e12[25:], e26[25:]) if a is not None and b is not None]
    sig_s = ema_series(macd_s, 9)
    macd_v = macd_s[-1] if macd_s else None
    sig_v = sig_s[-1] if sig_s and sig_s[-1] is not None else None
    out = {
        "rsi": rsi14(closes),
        "ema_fast": round(e9[-1], 6) if e9[-1] is not None else None,
        "ema_slow": round(e21[-1], 6) if e21[-1] is not None else None,
    }
    out["daily_ema9"] = out["ema_fast"]
    out["daily_ema21"] = out["ema_slow"]
    if out["ema_fast"] is not None and out["ema_slow"] is not None:
        out["daily_ema_cross"] = "bullish" if out["ema_fast"] > out["ema_slow"] else "bearish"
    if macd_v is not None and sig_v is not None:
        out["macd"] = round(macd_v, 6)
        out["macd_signal"] = round(sig_v, 6)
        out["macd_histogram"] = round(macd_v - sig_v, 6)
        out["macd_cross"] = "bullish" if macd_v > sig_v else "bearish"
        out["macd_above_zero"] = 1 if macd_v > 0 else 0
    return out


def main():
    sys.path.insert(0, BASE + "/_tools")
    import run_witness
    _t0 = time.time()
    m = json.load(open(BASE + "/_tools/kse_symbol_map.json"))
    symbols = sorted(r["our_symbol"] for r in m["records"]
                     if r.get("verdict") == "confirmed")
    med = {r["symbol"]: r for r in
           json.load(open(BASE + "/_tools/liquidity_median.json"))["rows"]}
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row

    stats = {"ok": 0, "bars_inserted": 0, "snapshot_updated": 0,
             "snapshot_inserted": 0}
    errors = {}
    not_scanned = []
    aborted = None
    req = 0

    for idx, sym in enumerate(symbols):
        if req and req % 10 == 0:
            sb, se = fetch_bars("EQUIPMENT")
            req += 1
            if not sb:
                aborted = ("sentinel EQUIPMENT failed (%s) after %d symbols - "
                           "STOPPED; remaining recorded as not_scanned" % (se, idx))
                not_scanned = symbols[idx:]
                break
        bars, err = fetch_bars(sym)
        req += 1
        if err:
            errors.setdefault(err, []).append(sym)
            continue

        ins = 0
        for d, ts, o, h, l, c, v in bars:
            if d < FROM_DATE:
                continue
            val = round(c * v / 1000.0, 3) if v else None
            conn.execute(
                "INSERT OR REPLACE INTO daily_bars "
                "(symbol, trading_date, open, high, low, close, volume,"
                " value_kwd, source, is_final) "
                "VALUES (?,?,?,?,?,?,?,?,'yahoo',1)",
                (sym, d, o, h, l, c, v, val))
            ins += 1
        closes = [b[5] for b in bars]
        ind = indicators(closes)
        ind.update(full_indicators(bars))
        last = bars[-1]
        chg = (round((closes[-1] / closes[-2] - 1) * 100, 2)
               if len(closes) >= 2 and closes[-2] else None)

        row = conn.execute(
            "SELECT symbol FROM stock_radar_daily WHERE symbol=?", (sym,)
        ).fetchone()
        fields = {"price": last[5], "volume": last[6], "change_pct": chg,
                  "source_timeframe": "1D", "captured_at": last[1],
                  "updated_at": last[1], "market_was_open": 0}
        fields.update(ind)
        # vol_ratio against the median census, never a mean
        med20 = conn.execute(
            "SELECT med_vol_20 FROM stock_radar_daily WHERE symbol=?",
            (sym,)).fetchone()
        vr = None
        if med20 and med20["med_vol_20"] and last[6]:
            vr = round(last[6] / med20["med_vol_20"], 3)
            fields["vol_ratio"] = vr
        fields.update(declared_confluence(ind, vr))
        if row:
            sets = ", ".join("%s=?" % k for k in fields)
            conn.execute("UPDATE stock_radar_daily SET %s WHERE symbol=?" % sets,
                         (*fields.values(), sym))
            stats["snapshot_updated"] += 1
        else:
            lm = med.get(sym) or {}
            if lm.get("status") == "ok":
                fields.update({"med_vol_20": lm.get("med20"),
                               "med_vol_60": lm.get("med60"),
                               "liq_vol": lm.get("liq_vol"),
                               "liq_value_kwd": lm.get("liq_value_kwd"),
                               "avg_vol_as_of": lm.get("as_of"),
                               "avg_vol_source": "yahoo-median"})
            cols = ", ".join(fields)
            ph = ", ".join("?" * len(fields))
            conn.execute(
                "INSERT INTO stock_radar_daily (symbol, exchange, %s) "
                "VALUES (?, 'KSE', %s)" % (cols, ph),
                (sym, *fields.values()))
            stats["snapshot_inserted"] += 1
        conn.commit()          # one commit per symbol - a crash keeps the done ones
        stats["ok"] += 1
        stats["bars_inserted"] += ins

    conn.close()
    print("symbols ok      :", stats["ok"], "/", len(symbols))
    print("bars inserted   :", stats["bars_inserted"])
    print("snapshot updated:", stats["snapshot_updated"],
          "| inserted:", stats["snapshot_inserted"])
    for name, syms in errors.items():
        print("error[%s]: %d -> %s" % (name, len(syms), ",".join(syms)))
    if aborted:
        print("ABORTED:", aborted)
        print("not_scanned:", ",".join(not_scanned))
    print("requests:", req)

    # ── proof of life, by user decision 2026-08-15 ──
    err_txt = "; ".join("%s:%d" % (k, len(v)) for k, v in errors.items()) or None
    if aborted:
        status = "failed"
        err_txt = (err_txt + "; " if err_txt else "") + aborted
    elif stats["bars_inserted"] == 0:
        status = "failed"
    elif errors:
        status = "partial"
    else:
        status = "success"
    run_witness.log_run("yahoo_close", status, stats["ok"], len(symbols),
                        time.time() - _t0, err_txt)
    if stats["bars_inserted"] == 0 or aborted:
        run_witness.send_telegram(
            "⚠️ تعبئة الإغلاق فشلت: %d صف، %d/%d رمزاً (%s)"
            % (stats["bars_inserted"], stats["ok"], len(symbols),
               err_txt or "بلا تفاصيل"))
    # cross-watch: on a trading day, the intraday feed must have run too
    if run_witness.is_trading_day() and run_witness.runs_today("yahoo_intraday") == 0:
        run_witness.send_telegram(
            "⚠️ التحديث اللحظي لم يعمل اليوم إطلاقاً — تحقق من cron")


if __name__ == "__main__":
    main()
