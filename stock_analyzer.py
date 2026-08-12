"""Stock Deep Analysis — Bridge bars + Gemini 2.5 Pro analysis."""
import os, json, time, re, logging, sqlite3, csv, asyncio, urllib.request, urllib.error

logger = logging.getLogger("stock_analyzer")

GEMINI_KEY = ""
_gk = os.path.expanduser("~/.gemini_key")
if os.path.exists(_gk):
    GEMINI_KEY = open(_gk).read().strip()

BRIDGE_BASE = os.getenv("BRIDGE_URL", "http://192.168.111.214:8059")

# DISABLED 2026-05-10: cache removed — every call goes to Gemini live.
# _analysis_cache = {}
# CACHE_TTL = 1800


def _bridge_available():
    """Quick check if Bridge is reachable (2s timeout)."""
    try:
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
    """Fetch enriched bars from Bridge API."""
    url = f"{BRIDGE_BASE}/bars?symbol={symbol}&interval={interval}&count={count}"
    req = urllib.request.urlopen(url, timeout=30)
    return json.loads(req.read().decode())


def _summarize_bars(bars_data, label):
    """Create smart summary of bars for Gemini — saves tokens but keeps key info."""
    bars = bars_data.get("bars", [])
    if not bars:
        return {"error": "no data"}

    latest_5 = bars[-5:]

    rsi_traj = [round(b.get("rsi_14", 0), 1) for b in bars[-20:]]
    macd_traj = [round(b.get("macd", 0), 3) for b in bars[-20:]]

    vols = [b.get("volume", 0) for b in bars]
    vol_20 = sum(vols[-20:]) / max(len(vols[-20:]), 1)
    vol_5 = sum(vols[-5:]) / max(len(vols[-5:]), 1)

    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]

    peak_bar = max(bars, key=lambda b: b["high"])
    trough_bar = min(bars, key=lambda b: b["low"])

    return {
        "timeframe": label,
        "total_bars": len(bars),
        "latest": bars[-1],
        "latest_5_bars": latest_5,
        "price_range": {
            "period_high": max(highs),
            "period_low": min(lows),
            "first_open": bars[0]["open"],
            "last_close": bars[-1]["close"],
            "change_pct": round((bars[-1]["close"] - bars[0]["open"]) / bars[0]["open"] * 100, 2),
        },
        "peak": {"time": peak_bar["time"], "high": peak_bar["high"]},
        "trough": {"time": trough_bar["time"], "low": trough_bar["low"]},
        "rsi_last_20": rsi_traj,
        "macd_last_20": macd_traj,
        "volume": {
            "avg_20": round(vol_20),
            "avg_5": round(vol_5),
            "latest": bars[-1].get("volume", 0),
            "ratio_5_to_20": round(vol_5 / max(vol_20, 1), 2),
        },
        "ema_current": {
            "ema_9": bars[-1].get("ema_9"),
            "ema_21": bars[-1].get("ema_21"),
            "ema_50": bars[-1].get("ema_50"),
            "ema_200": bars[-1].get("ema_200"),
        },
        "adx": bars[-1].get("adx"),
        "stoch_k": bars[-1].get("stoch_k"),
        "atr": bars[-1].get("atr_14"),
    }


# ═══════════════════════════════════
# Gemini Analysis
# ═══════════════════════════════════

ANALYSIS_PROMPT = """أنت محلل فني محترف لبورصة الكويت. حلّل سهم {symbol} بالتفصيل.

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


def analyze_stock(symbol):
    """Full stock analysis with Gemini 2.5 Pro."""
    # 1. Quick Bridge health check (2s) before heavy calls
    if not _bridge_available():
        return {"error": "Bridge offline — التحليل يحتاج Bridge شغّال"}

    # 3. Fetch bars from Bridge
    try:
        bars_30m = _fetch_bridge_bars(symbol, "30", 100)
        bars_daily = _fetch_bridge_bars(symbol, "D", 60)
    except Exception as e:
        return {"error": f"Bridge error: {e}"}

    # 4. Summarize
    summary_30m = _summarize_bars(bars_30m, "30m")
    summary_daily = _summarize_bars(bars_daily, "daily")

    if summary_30m.get("error") and summary_daily.get("error"):
        return {"error": "No bar data from Bridge for " + symbol}

    # 5. Build prompt
    prompt = ANALYSIS_PROMPT.format(
        symbol=symbol,
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
        "data": {
            "bars_30m": summary_30m.get("total_bars", 0),
            "bars_daily": summary_daily.get("total_bars", 0),
            "price": summary_30m.get("latest", {}).get("close"),
        },
    }

    return analysis
