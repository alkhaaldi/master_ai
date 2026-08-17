"""Stock Deep Analysis — Bridge bars + Gemini 2.5 Pro analysis."""
import os, json, time, re, logging, sqlite3, csv, asyncio, urllib.request, urllib.error

logger = logging.getLogger("stock_analyzer")

GEMINI_KEY = ""
_gk = os.path.expanduser("~/.gemini_key")
if os.path.exists(_gk):
    GEMINI_KEY = open(_gk).read().strip()

# RETIRED 2026-08-16 (G-4). Address kept as a deprecated marker; the
# guard below stops every call before it leaves the process.
BRIDGE_BASE = os.getenv("BRIDGE_URL", "http://192.168.111.214:8059")
BRIDGE_RETIRED = True

# DISABLED 2026-05-10: cache removed — every call goes to Gemini live.
# _analysis_cache = {}
# CACHE_TTL = 1800


def _bridge_available():
    """Quick check if Bridge is reachable (2s timeout)."""
    try:
        if BRIDGE_RETIRED:
            return False
        req = urllib.request.urlopen(f"{BRIDGE_BASE}/health", timeout=2)
        return req.status == 200
    except Exception:
        return False




# ═══════════════════════════════════
# DB Cache: stock_analysis_cache
# ═══════════════════════════════════
_LIFE_DB = "data/life.db"


def _db():
    c = sqlite3.connect(_LIFE_DB, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def init_analysis_cache_table():
    """Create stock_analysis_cache table if not exists."""
    c = _db()
    c.execute("""CREATE TABLE IF NOT EXISTS stock_analysis_cache (
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
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sac_symbol ON stock_analysis_cache(symbol)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sac_date ON stock_analysis_cache(analysis_date)")
    c.commit()
    c.close()


# Run on import
try:
    init_analysis_cache_table()
except Exception:
    pass


def store_analysis(symbol, result):
    """Store analysis result in DB."""
    structured = result.get("structured", {})
    c = _db()
    c.execute("""INSERT OR REPLACE INTO stock_analysis_cache
        (symbol, analysis_date, analysis_json, structured_json, signal, confidence, gemini_model)
        VALUES (?, date('now'), ?, ?, ?, ?, ?)""",
        (symbol.upper(),
         json.dumps(result, ensure_ascii=False),
         json.dumps(structured, ensure_ascii=False),
         structured.get("signal", ""),
         structured.get("confidence", 0),
         result.get("gemini_model", "gemini-2.5-pro")))
    c.commit()
    c.close()
    logger.info(f"Stored analysis for {symbol}")


def get_cached_analysis(symbol):
    """Get latest cached analysis for a symbol."""
    c = _db()
    row = c.execute(
        "SELECT * FROM stock_analysis_cache WHERE symbol=? ORDER BY analysis_date DESC LIMIT 1",
        (symbol.upper(),)).fetchone()
    c.close()
    if not row:
        return None
    r = dict(row)
    try:
        r["analysis_json"] = json.loads(r["analysis_json"])
    except Exception:
        pass
    try:
        r["structured_json"] = json.loads(r["structured_json"])
    except Exception:
        pass
    return r


def get_all_cached_analyses():
    """Get latest analysis for ALL symbols (one per symbol)."""
    c = _db()
    rows = c.execute("""
        SELECT s.* FROM stock_analysis_cache s
        INNER JOIN (
            SELECT symbol, MAX(analysis_date) as max_date
            FROM stock_analysis_cache GROUP BY symbol
        ) latest ON s.symbol = latest.symbol AND s.analysis_date = latest.max_date
        ORDER BY s.symbol
    """).fetchall()
    c.close()
    results = []
    for row in rows:
        r = dict(row)
        try:
            r["structured_json"] = json.loads(r["structured_json"])
        except Exception:
            pass
        # Don't parse full analysis_json here — too heavy for list view
        del r["analysis_json"]
        results.append(r)
    return results


def get_all_kse_symbols():
    """Get all 128 KSE symbols from csv."""
    csv_path = os.path.join(os.path.dirname(__file__) or ".", "data", "kse_stocks.csv")
    if not os.path.exists(csv_path):
        return []
    symbols = []
    with open(csv_path) as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            if row and row[0].strip():
                symbols.append(row[0].strip())
    return symbols


def refresh_all_analyses(send_update=None):
    """
    Refresh analysis for ALL 128 KSE stocks. Blocking (sync).
    send_update: optional callback(text) for progress messages.
    Returns summary dict.
    """
    symbols = get_all_kse_symbols()
    if not symbols:
        logger.error("refresh_all: no symbols found in kse_stocks.csv")
        return {"error": "no symbols found in kse_stocks.csv"}

    bridge_ok = _bridge_available()
    logger.info("refresh_all: symbols=%d, bridge=%s", len(symbols), bridge_ok)
    if not bridge_ok:
        logger.error("refresh_all: Bridge offline — aborting")
        return {"error": "Bridge offline — cant refresh analyses"}

    total = len(symbols)
    done = 0
    errors = 0
    error_list = []

    for sym in symbols:
        try:
            result = analyze_stock(sym)
            if result.get("error"):
                errors += 1
                error_list.append(f"{sym}: {result['error']}")
            else:
                store_analysis(sym, result)
                done += 1
        except Exception as e:
            errors += 1
            error_list.append(f"{sym}: {e}")
            logger.error(f"Analysis refresh failed for {sym}: {e}")

        if send_update and (done + errors) % 20 == 0:
            send_update(f"\u062a\u062d\u0644\u064a\u0644: {done + errors}/{total} ({errors} \u0623\u062e\u0637\u0627\u0621)")

        time.sleep(4)  # Gemini rate limit

    summary = {
        "total": total, "done": done, "errors": errors,
        "error_details": error_list[:10],
    }
    logger.info(f"Analysis refresh complete: {done}/{total} ({errors} errors)")
    return summary

async def refresh_all_analyses_parallel(send_update=None, max_concurrent=5):
    """
    Refresh ALL 128 KSE stocks using ParallelCoordinator.
    ~6 min with 5 parallel vs ~30 min sequential.
    send_update: optional async callback(text) for Telegram progress.
    """
    from parallel_coordinator import ParallelCoordinator

    symbols = get_all_kse_symbols()
    if not symbols:
        logger.error("refresh_parallel: no symbols found")
        return {"error": "no symbols found in kse_stocks.csv"}
    bridge_ok = _bridge_available()
    logger.info("refresh_parallel: symbols=%d, bridge=%s, concurrent=%d", len(symbols), bridge_ok, max_concurrent)
    if not bridge_ok:
        logger.error("refresh_parallel: Bridge offline — aborting")
        return {"error": "Bridge offline — cant refresh analyses"}

    total = len(symbols)
    done = 0
    errors = 0
    error_list = []

    coord = ParallelCoordinator("analysis_refresh")

    for sym in symbols:
        async def _do_analysis(s=sym):
            # analyze_stock is sync — run in thread
            result = await asyncio.to_thread(analyze_stock, s)
            if result and not result.get("error"):
                store_analysis(s, result)
            return result
        coord.add_worker(sym, _do_analysis)

    def _on_progress(name, completed, t):
        nonlocal done, errors, error_list
        # Progress callback is sync — just log
        if completed % 20 == 0 or completed == t:
            logger.info(f"Analysis progress: {completed}/{t}")

    results = await coord.run(max_concurrent=max_concurrent, timeout=120,
                              on_progress=_on_progress)

    for wr in results:
        if wr.success and wr.result and not wr.result.get("error"):
            done += 1
        else:
            errors += 1
            err = wr.error or (wr.result.get("error") if wr.result else "unknown")
            error_list.append(f"{wr.name}: {err}")

    summary = {
        "total": total, "done": done, "errors": errors,
        "error_details": error_list[:10],
        "parallel": max_concurrent,
    }
    logger.info(f"Parallel analysis complete: {done}/{total} ({errors} errors)")
    return summary


# ═══════════════════════════════════
# Bridge Data
# ═══════════════════════════════════

def _fetch_bridge_bars(symbol, interval, count):
    """RETIRED 2026-08-16 (G-4). Unreachable, kept so the history of how bars
    used to arrive is not deleted along with the dependency. See _bars_for."""
    return None


LOCAL_PARAMS = "RSI14 MACD12/26/9 ATR14 ADX14 StochK14 EMA9/21 SR20"


def _daily_bars_local(symbol, count):
    """Daily bars from `daily_bars` - the same series backfill_daily_bars
    maintains and every other module reads.

    Deliberately NOT a fresh Yahoo pull: a second daily series would be a
    second clock, and this project has spent long enough removing those.
    """
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT trading_date, open, high, low, close, volume FROM daily_bars"
            " WHERE symbol=? ORDER BY trading_date DESC LIMIT ?",
            (symbol.upper(), count)).fetchall()
    finally:
        conn.close()
    import datetime as _dt
    bars = []
    for r in reversed(rows):
        try:
            ts = int(_dt.datetime.strptime(r["trading_date"], "%Y-%m-%d")
                     .replace(hour=6, tzinfo=_dt.timezone.utc).timestamp())
        except (ValueError, TypeError):
            continue
        bars.append({"ts": ts, "open": r["open"], "high": r["high"],
                     "low": r["low"], "close": r["close"], "volume": r["volume"]})
    return bars, "daily_bars (local store)"


def _intraday_bars(symbol, interval, rng):
    """30m has no local store - that layer is offline (OPEN_ITEMS 5) - so it
    comes live through the one Yahoo door, cached ten minutes so a user
    clicking refresh twice does not spend two requests."""
    import yahoo_gate
    bars, src = yahoo_gate.chart(symbol.upper(), interval=interval, rng=rng,
                                 max_age_s=600)
    return bars, "yahoo %s (%s)" % (interval, src)


def _bars_for(symbol, kind):
    """(bars, source, error). Absence carries a reason, never an empty list
    pretending to be a flat market."""
    try:
        if kind == "30m":
            bars, src = _intraday_bars(symbol, "30m", "1mo")
        else:
            bars, src = _daily_bars_local(symbol, 120)
    except Exception as e:
        return [], None, "%s: %s" % (kind, repr(e)[:120])
    if not bars:
        return [], src, ("%s: no bars available for %s" % (kind, symbol))
    return bars, src, None


def _bar_time(bar):
    """UTC timestamp of a bar as a readable string, or None if it has no
    stamp - an undated bar is not given a made-up date."""
    import datetime as _dt
    ts = bar.get("ts")
    if ts is None:
        return None
    try:
        return _dt.datetime.fromtimestamp(int(ts), _dt.timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC")
    except (ValueError, OSError, TypeError):
        return None


def _trail(bars, pick, n=20):
    """The last n readings of an indicator, each computed from the bars up to
    that point.

    None where the window could not answer - a hole in a trajectory is a
    hole, and Gemini reading a 0 there would see a collapse that never
    happened. That is precisely the reading the bridge era used to invent.
    """
    import indicators as _I
    out = []
    start = len(bars) - n
    if start < 0:
        start = 0
    for i in range(start, len(bars)):
        out.append(pick(_I, bars[:i + 1]))
    return out


def _nonnull(bars, key):
    """The readings of one OHLCV field that are actually there.

    An absent field is a window the market did not trade in, not a zero, and
    the two must not meet the same arithmetic. `b.get("volume", 0)` returns
    None the moment the key exists holding None, and `max()` over a list with
    a None in it raises outright - which is how a single empty 30m bar turned
    into a 500 for the whole symbol (EQUIPMENT, 2026-08-17). The indicators
    had already refused those bars correctly; the raw summary below them was
    what fell over, so the coverage floor never got to answer.
    """
    return [b[key] for b in bars if b.get(key) is not None]


def _extreme_bar(bars, key, fn):
    """The bar carrying the highest high / lowest low, skipping bars that
    carry no such reading. None when not one of them does."""
    usable = [b for b in bars if b.get(key) is not None]
    if not usable:
        return None
    return fn(usable, key=lambda b: b[key])


def _stat(values, fn, why):
    """{value, reason} - the same shape indicators.py returns, so a hole
    reads identically wherever the reader meets it."""
    if not values:
        return {"value": None, "reason": why}
    return {"value": fn(values), "reason": None}


def _summarize_bars(bars_data, label, interval="1d", source=None):
    """Summary for Gemini, computed HERE rather than read off enriched bars.

    Every indicator now travels with its evidence - bars_used, coverage_pct,
    bar_complete - and an absent value is None WITH a reason, never a zero.
    The bridge used to send these pre-computed, on its own parameters and its
    own bar hygiene; StochK differed by up to 242% on the same symbol and
    session (ACICO 2026-08-05: 26.3 vs 90.0). So this is not the same number
    arriving by another road, and the summary says so out loud.
    """
    import time as _t
    import indicators as _I
    bars = bars_data.get("bars", [])
    if not bars:
        return {"error": "no data", "timeframe": label,
                "source": source, "reason": bars_data.get("reason")}
    ci = _I.compute_all(bars, interval, int(_t.time()))
    complete, _dropped, _why = _I.drop_incomplete(bars, interval, int(_t.time()))
    if complete:
        bars = complete

    latest_5 = bars[-5:]

    # Computed here, one window per point. `round(b.get("rsi_14", 0), 1)`
    # turned a bar the bridge had not enriched into an RSI of 0 - a reading
    # that says "maximum oversold" when it means "not measured".
    def _pick_rsi(_I, sub):
        v = _I.rsi(sub)["value"]
        if v is None:
            return None
        return round(v, 1)

    def _pick_macd(_I, sub):
        v = _I.macd(sub)["value"]
        if v is None:
            return None
        return round(v["macd"], 3)

    rsi_traj = _trail(bars, _pick_rsi)
    macd_traj = _trail(bars, _pick_macd)

    # Windows stay fixed in time and the nulls drop out of both the sum and
    # the count. Averaging "the last 20 readings" instead would quietly walk
    # the window backwards on exactly the thin names where it matters, and
    # report a 20-bar average measured over five weeks.
    def _vol_avg(n):
        w = _nonnull(bars[-n:], "volume")
        if not w:
            return {"value": None, "bars_counted": 0,
                    "reason": "no traded volume in the last %d bars" % n}
        return {"value": round(sum(w) / len(w)), "bars_counted": len(w),
                "reason": None}

    vol_20, vol_5 = _vol_avg(20), _vol_avg(5)

    highs = _nonnull(bars, "high")
    lows = _nonnull(bars, "low")

    peak_bar = _extreme_bar(bars, "high", max)
    trough_bar = _extreme_bar(bars, "low", min)

    # The window's own ends, each found rather than assumed: on a thin name
    # the first or last bar is often empty, and a change measured between two
    # different bars than the reader pictures is a wrong number wearing a
    # right one's name. So both ends travel with the time they were taken.
    first_open_bar = next((b for b in bars if b.get("open") is not None), None)
    last_close_bar = next((b for b in reversed(bars)
                           if b.get("close") is not None), None)

    def _end(bar, key, why):
        if not bar:
            return {"value": None, "at": None, "reason": why}
        return {"value": bar[key], "at": _bar_time(bar), "reason": None}

    def _change_pct():
        if not first_open_bar or not last_close_bar or not first_open_bar["open"]:
            return {"value": None,
                    "reason": "needs a first open and a last close, both "
                              "present and the open non-zero"}
        return {"value": round((last_close_bar["close"] - first_open_bar["open"])
                               / first_open_bar["open"] * 100, 2), "reason": None}

    def _vol_ratio():
        if vol_5["value"] is None or not vol_20["value"]:
            return {"value": None,
                    "reason": "needs both averages, with a non-zero 20-bar one"}
        return {"value": round(vol_5["value"] / vol_20["value"], 2), "reason": None}

    def _val(key):
        """{value, reason} - the reason survives when the value cannot."""
        r = ci.get(key, {})
        return {"value": r.get("value"), "reason": r.get("reason")}

    return {
        "timeframe": label,
        "source": source,
        # Stated so an analysis from today is never silently compared with one
        # from the bridge era. Different engine, different parameters.
        "indicator_source": "local (indicators.py)",
        "indicator_params": LOCAL_PARAMS,
        "bars_used": ci["bars_complete"],
        "bars_dropped_incomplete": ci["bars_dropped_incomplete"],
        "drop_reason": ci["drop_reason"],
        "coverage_pct": ci["coverage_pct"],
        "coverage_floor_pct": ci["coverage_floor_pct"],
        "bar_complete": ci["bar_complete"],
        "rsi": _val("rsi"),
        "macd": _val("macd"),
        "adx_now": _val("adx"),
        "atr_now": _val("atr"),
        "stoch_k_now": _val("stoch_k"),
        "support_resistance": _val("sr"),
        "ema_9_now": _val("ema_9"),
        "ema_21_now": _val("ema_21"),
        "total_bars": len(bars),
        "latest": bars[-1],
        "latest_5_bars": latest_5,
        "price_range": {
            "period_high": _stat(highs, max,
                                 "no bar in the window carries a high"),
            "period_low": _stat(lows, min,
                                "no bar in the window carries a low"),
            "first_open": _end(first_open_bar, "open",
                               "no bar in the window carries an open"),
            "last_close": _end(last_close_bar, "close",
                               "no bar in the window carries a close"),
            "change_pct": _change_pct(),
        },
        # `ts`, not `time`: bridge bars carried a preformatted time string,
        # ours carry an epoch. Rendered here so Gemini reads a date rather
        # than a number it would have to guess the unit of.
        "peak": ({"time": _bar_time(peak_bar), "high": peak_bar["high"]}
                 if peak_bar else
                 {"time": None, "high": None,
                  "reason": "no bar in the window carries a high"}),
        "trough": ({"time": _bar_time(trough_bar), "low": trough_bar["low"]}
                   if trough_bar else
                   {"time": None, "low": None,
                    "reason": "no bar in the window carries a low"}),
        "rsi_last_20": rsi_traj,
        "macd_last_20": macd_traj,
        "volume": {
            "avg_20": vol_20,
            "avg_5": vol_5,
            # `.get("volume", 0)` read the default only when the key was
            # missing; a key present holding None sailed straight through as
            # a volume of zero, which on this market reads as "nobody traded"
            # rather than "we were not told".
            "latest": bars[-1].get("volume"),
            "ratio_5_to_20": _vol_ratio(),
        },
        # ema_50 / ema_200 are absent on purpose: indicators.py does not
        # compute them, and carrying the keys with None would read as "we
        # looked and found nothing" rather than "we do not compute this".
        "ema_current": {
            "ema_9": ci["ema_9"]["value"],
            "ema_21": ci["ema_21"]["value"],
        },
        "adx": ci["adx"]["value"],
        "stoch_k": ci["stoch_k"]["value"],
        "atr": ci["atr"]["value"],
    }


# ═══════════════════════════════════
# Gemini Analysis
# ═══════════════════════════════════

ANALYSIS_PROMPT = """أنت محلل فني محترف لبورصة الكويت. حلّل سهم {symbol} بالتفصيل.

**مصدر الأرقام — اقرأ هذا أولاً:**
{provenance}

**بيانات 30 دقيقة ({count_30m} شمعة):**
```json
{summary_30m}
```

**بيانات يومية ({count_daily} شمعة):**
```json
{summary_daily}
```

حلّل السهم كمحلل فني خبير:

1. **القمة والتصحيح:** أين كانت أعلى قمة؟ كم نسبة الهبوط منها؟ هل انتهى التصحيح؟
2. **إشارات البيع/الشراء المبكرة:** شنو الإشارات اللي ظهرت عند القمة أو القاع؟ (Volume climax, MACD divergence, RSI levels)
3. **الوضع الحالي:** هل السهم بترند صاعد/هابط/محايد؟ شنو تقول المؤشرات الحين؟
4. **مسار RSI:** تتبع مسار RSI آخر 20 شمعة — هل يرتفع أو ينخفض؟ هل كسر 50؟
5. **MACD:** هل فيه تقاطع إيجابي أو سلبي؟ هل فوق أو تحت الصفر؟
6. **حجم التداول:** هل فيه دخول سيولة؟ قارن حجم آخر 5 شموع بمتوسط 20
7. **مستويات الدعم والمقاومة** من EMA والأسعار التاريخية
8. **خطة التداول:** نقطة دخول، وقف خسارة، أهداف
9. **تقييم المخاطر والثقة (0-100)**

اكتب التحليل بالعربي الكويتي بأسلوب محلل محترف. كن محدداً بالأرقام.
اكتب كنص مفصّل (مو JSON) — فقرات واضحة مع عناوين.
بالنهاية أعطني JSON مختصر بالهيكل:

```json
{{
  "signal": "شراء / بيع / انتظار / مراقبة",
  "confidence": 75,
  "direction": "صاعد / هابط / محايد",
  "entry": "السعر",
  "stop_loss": "السعر",
  "targets": ["هدف1", "هدف2"],
  "support": ["دعم1", "دعم2"],
  "resistance": ["مقاومة1", "مقاومة2"],
  "risk": "وصف المخاطر"
}}
```

ابدأ التحليل الآن."""


def _contract(summary):
    """What the page needs to judge a number by: where it came from, how many
    bars answered, how much of the grid was there, and whether the newest bar
    had closed. An error carries its reason instead."""
    if summary.get("error"):
        return {"state": "unavailable", "reason": summary.get("reason"),
                "source": summary.get("source")}
    return {
        "state": "ok",
        "source": summary.get("source"),
        "bars_used": summary.get("bars_used"),
        "bars_dropped_incomplete": summary.get("bars_dropped_incomplete"),
        "coverage_pct": summary.get("coverage_pct"),
        "coverage_floor_pct": summary.get("coverage_floor_pct"),
        "bar_complete": summary.get("bar_complete"),
    }


def analyze_stock(symbol):
    """Full stock analysis with Gemini 2.5 Pro.

    Rebuilt 2026-08-17. The bridge was retired on 2026-08-16 and this path
    was gated shut behind BRIDGE_RETIRED in three places, so analysis.html -
    a page the user opens by hand - answered "Bridge offline" for every
    symbol, and starting the bridge would not have helped: the code returned
    None before making a call.

    Bars now come from the same places as everything else: daily from the
    local `daily_bars` store, 30m live through yahoo_gate. Indicators are
    computed by indicators.py under its coverage floor, so absence produces
    a reason instead of a number.
    """
    b30, src30, err30 = _bars_for(symbol, "30m")
    bday, srcday, errday = _bars_for(symbol, "daily")

    summary_30m = _summarize_bars({"bars": b30, "reason": err30}, "30m",
                                  interval="30m", source=src30)
    summary_daily = _summarize_bars({"bars": bday, "reason": errday}, "daily",
                                    interval="1d", source=srcday)

    if summary_30m.get("error") and summary_daily.get("error"):
        # Both empty is "we could not ask", not "the market is flat".
        return {"error": "No bars for %s — 30m: %s | daily: %s"
                         % (symbol, err30, errday),
                "symbol": symbol, "source_30m": src30, "source_daily": srcday}

    # 5. Build prompt
    provenance = (
        "المؤشرات محسوبة محلياً بـ indicators.py (%s)، لا من الجسر.\n"
        "الجسر تقاعد في 2026-08-16، وأرقامه لم تكن بنفس المعايير: StochK "
        "اختلف حتى 242%% على نفس السهم والجلسة. فلا تقارن هذا التحليل "
        "بتحليل سابق من عهد الجسر — المحرّك مختلف.\n"
        "مصدر 30 دقيقة: %s · مصدر اليومي: %s\n"
        "كل مؤشر يحمل bars_used و coverage_pct و bar_complete. أي قيمة "
        "None معناها «تعذّر القياس» ومعها سبب — وليست صفراً ولا حياداً. "
        "لا تبنِ استنتاجاً على قيمة غائبة."
        % (LOCAL_PARAMS, summary_30m.get("source"), summary_daily.get("source"))
    )
    prompt = ANALYSIS_PROMPT.format(
        symbol=symbol,
        provenance=provenance,
        count_30m=summary_30m.get("total_bars", 0),
        count_daily=summary_daily.get("total_bars", 0),
        summary_30m=json.dumps(summary_30m, indent=2, ensure_ascii=False),
        summary_daily=json.dumps(summary_daily, indent=2, ensure_ascii=False),
    )

    # 6. Call Gemini API (retry + model fallback: pro → flash)
    if not GEMINI_KEY:
        return {"error": "Gemini API key not configured"}

    _MODELS = ["gemini-2.5-pro", "gemini-2.5-flash"]
    result = None
    _used_model = None

    for _model in _MODELS:
        gemini_url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{_model}:generateContent?key=" + GEMINI_KEY
        )
        body = json.dumps({
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 16384,
                "thinkingConfig": {"thinkingBudget": 2048},
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            gemini_url, data=body,
            headers={"Content-Type": "application/json", "User-Agent": "MasterAI/1.0"},
        )

        for _attempt in range(3):
            try:
                resp = urllib.request.urlopen(req, timeout=120)
                result = json.loads(resp.read().decode())
                _used_model = _model
                break
            except urllib.error.HTTPError as he:
                if he.code in (429, 503) and _attempt < 2:
                    _wait = (2 ** _attempt) * 10  # 10s, 20s
                    logger.warning(f"Gemini {he.code} for {symbol} ({_model}), retry in {_wait}s (attempt {_attempt+1})")
                    time.sleep(_wait)
                else:
                    logger.warning(f"Gemini HTTP {he.code} for {symbol} ({_model}): {he.reason}")
                    break  # try next model
            except Exception as e:
                logger.warning(f"Gemini error for {symbol} ({_model}): {e}")
                break  # try next model

        if result:
            break  # success, stop trying models

    if not result:
        return {"error": f"Gemini failed for {symbol} after retries on all models"}

    # 7. Extract non-thought text
    answer = ""
    for c in result.get("candidates", []):
        for p in c.get("content", {}).get("parts", []):
            if not p.get("thought", False):
                answer += p.get("text", "")

    # 8. Extract structured JSON from response
    analysis_json = {}
    try:
        json_matches = re.findall(r'\{[^{}]*"signal"[^{}]*\}', answer)
        if json_matches:
            analysis_json = json.loads(json_matches[-1])
    except Exception:
        pass

    # 8b. Fallback: if no structured JSON, ask Gemini Flash for extraction
    if not analysis_json.get("signal") and answer and GEMINI_KEY:
        try:
            _fx_url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                "gemini-2.5-flash:generateContent?key=" + GEMINI_KEY
            )
            _fx_prompt = (
                "من التقرير التالي، استخرج JSON فقط بدون أي نص:\n"
                + answer[:3000]
                + '\n\nارجع JSON فقط بهالشكل: {"signal":"شراء/بيع/انتظار/مراقبة","confidence":0-100,'
                  '"direction":"صاعد/هابط/محايد","entry":"السعر","stop_loss":"السعر",'
                  '"targets":["هدف1"],"support":["دعم1"],"resistance":["مقاومة1"],"risk":"وصف"}'
            )
            _fx_body = json.dumps({
                "contents": [{"role": "user", "parts": [{"text": _fx_prompt}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024},
            }).encode("utf-8")
            _fx_req = urllib.request.Request(
                _fx_url, data=_fx_body,
                headers={"Content-Type": "application/json", "User-Agent": "MasterAI/1.0"},
            )
            _fx_resp = urllib.request.urlopen(_fx_req, timeout=30)
            _fx_result = json.loads(_fx_resp.read().decode())
            _fx_text = ""
            for _fc in _fx_result.get("candidates", []):
                for _fp in _fc.get("content", {}).get("parts", []):
                    if not _fp.get("thought", False):
                        _fx_text += _fp.get("text", "")
            _fx_matches = re.findall(r'\{[^{}]*"signal"[^{}]*\}', _fx_text)
            if _fx_matches:
                analysis_json = json.loads(_fx_matches[-1])
                logger.info(f"Extracted structured via follow-up for {symbol}")
        except Exception as _fe:
            logger.debug(f"Follow-up extraction failed for {symbol}: {_fe}")

    # 8c. Last resort: extract signal from Arabic text
    if not analysis_json.get("signal") and answer:
        _text_lower = answer.lower()
        _signal = ""
        if any(w in answer for w in ["شراء", "شراء قوي", "شراء تدريجي"]):
            _signal = "شراء"
        elif any(w in answer for w in ["بيع", "جني أرباح"]):
            _signal = "بيع"
        elif "مراقبة" in answer:
            _signal = "مراقبة"
        elif "انتظار" in answer:
            _signal = "انتظار"
        if _signal:
            analysis_json["signal"] = _signal
            # Try to find confidence number near "ثقة" or "confidence"
            _conf_m = re.search(r'(?:ثقة|confidence)[:\s]*(\d{1,3})', answer, re.IGNORECASE)
            if _conf_m:
                analysis_json["confidence"] = int(_conf_m.group(1))
            logger.info(f"Text-parsed signal for {symbol}: {_signal}")

    # 9. Build result
    analysis = {
        "symbol": symbol,
        "report": answer,
        "structured": analysis_json,
        "analyzed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gemini_model": _used_model or "unknown",
        # The counts stay for the existing page, but a count on its own is
        # the shape this project keeps removing: 176 bars says nothing about
        # whether they were complete or whether the grid had holes. The
        # evidence travels with them now, per timeframe.
        "data": {
            "bars_30m": summary_30m.get("total_bars"),
            "bars_daily": summary_daily.get("total_bars"),
            "price": (summary_30m.get("latest") or {}).get("close"),
            "indicator_source": "local (indicators.py)",
            "indicator_params": LOCAL_PARAMS,
            "timeframes": {
                "30m": _contract(summary_30m),
                "daily": _contract(summary_daily),
            },
        },
    }

    return analysis
