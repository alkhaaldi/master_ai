"""
confluence_engine.py — Smart Trading Confluence Decision Engine
Master AI v9.x — Scans 128 KSE stocks, outputs BUY/SKIP decisions.
Tables in life.db: confluence_signals, confluence_decisions
"""
import os
import sqlite3
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("confluence")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")


# ═══════════════════════════════════════════════════
# DEDUP HELPER — keeps latest per (symbol, signal_type, mode)
# ═══════════════════════════════════════════════════

def _dedup_items_keep_latest(items):
    """Dedup by (symbol, signal_type, mode), keep newest."""
    def _safe_dt(value):
        if not value:
            return datetime.min
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return datetime.min

    deduped = {}
    for item in items or []:
        symbol = str(item.get("symbol", "")).strip().upper()
        signal_type = str(item.get("signal_type", "")).strip().lower()
        mode = str(item.get("mode", "")).strip().lower()
        if not symbol:
            continue
        key = (symbol, signal_type, mode)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = item
            continue
        item_dt = max(_safe_dt(item.get("updated_at")), _safe_dt(item.get("created_at")))
        existing_dt = max(_safe_dt(existing.get("updated_at")), _safe_dt(existing.get("created_at")))
        item_id = int(item.get("id", 0) or 0)
        existing_id = int(existing.get("id", 0) or 0)
        if item_dt > existing_dt or (item_dt == existing_dt and item_id > existing_id):
            deduped[key] = item
    return list(deduped.values())

# ═══════════════════════════════════════════════════
# DB SCHEMA
# ═══════════════════════════════════════════════════

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS confluence_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    name_ar TEXT,
    price REAL,
    confluence_score INTEGER,
    conviction TEXT,
    checks_passed TEXT,
    rvol REAL,
    rsi REAL,
    macd_conf INTEGER DEFAULT 0,
    trend INTEGER DEFAULT 0,
    ema_position INTEGER DEFAULT 0,
    not_overbought INTEGER DEFAULT 0,
    support REAL,
    resistance REAL,
    entry_price REAL,
    stop_loss REAL,
    target_price REAL,
    risk_reward REAL,
    sl_pct REAL,
    signal_type TEXT DEFAULT 'buy',
    timeframe TEXT DEFAULT '1D',
    change_pct REAL,
    sector TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_conf_sig_symbol ON confluence_signals(symbol);
CREATE INDEX IF NOT EXISTS idx_conf_sig_active ON confluence_signals(is_active);
CREATE INDEX IF NOT EXISTS idx_conf_sig_created ON confluence_signals(created_at);

CREATE TABLE IF NOT EXISTS confluence_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    symbol TEXT NOT NULL,
    decision TEXT,
    entry_price REAL,
    decided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (signal_id) REFERENCES confluence_signals(id)
);
CREATE INDEX IF NOT EXISTS idx_conf_dec_signal ON confluence_decisions(signal_id);
"""


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_schema():
    with _conn() as c:
        c.executescript(_SCHEMA_SQL)
    logger.info("confluence schema initialized")


# ═══════════════════════════════════════════════════
# CONFLUENCE CHECKS (6 total)
# ═══════════════════════════════════════════════════

def _check_rvol(row):
    """Volume >= 1.5x average"""
    vr = row.get("vol_ratio")
    return vr is not None and vr >= 1.5


def _check_macd(row):
    """MACD bullish: cross bullish OR (macd > signal AND above zero)"""
    mc = row.get("macd_cross", "none")
    if mc == "bullish":
        return True
    macd = row.get("macd")
    sig = row.get("macd_signal")
    above = row.get("macd_above_zero", False)
    if macd is not None and sig is not None:
        return macd > sig and above
    return False


def _check_rsi(row):
    """RSI in ideal zone: 40-65"""
    rsi = row.get("rsi")
    return rsi is not None and 40 <= rsi <= 65


def _check_trend(row):
    """Uptrend: EMA fast > EMA slow OR not falling hard"""
    ef = row.get("ema_fast")
    es = row.get("ema_slow")
    if ef is not None and es is not None and ef > es:
        return True
    cp = row.get("change_pct")
    return cp is not None and cp > -2


def _check_ema_position(row):
    """Price above daily EMA21"""
    price = row.get("price")
    ema21 = row.get("daily_ema21")
    if price is not None and ema21 is not None and ema21 > 0:
        return price > ema21
    return False


def _check_not_overbought(row):
    """Not overbought: RSI < 70 AND change < 25%"""
    rsi = row.get("rsi")
    cp = row.get("change_pct")
    rsi_ok = rsi is None or rsi < 70
    cp_ok = cp is None or cp < 25
    return rsi_ok and cp_ok


ALL_CHECKS = [
    ("rvol", _check_rvol),
    ("macd", _check_macd),
    ("rsi", _check_rsi),
    ("trend", _check_trend),
    ("ema", _check_ema_position),
    ("not_ob", _check_not_overbought),
]


# ═══════════════════════════════════════════════════
# DISCOVERY CHECKS (5 total) — catches START of a move
# ═══════════════════════════════════════════════════

def _discovery_checks(row):
    """5 checks to catch the START of a move — earlier entry, higher reward."""
    checks = {}

    # Check 1: Volume acceleration — vol_ratio > 0.5 and volume > 0
    vol_ratio = float(row.get("vol_ratio") or 0)
    volume = float(row.get("volume") or 0)
    checks["volume_accel"] = vol_ratio > 0.5 and volume > 0

    # Check 2: MACD histogram turning positive or close to turning
    histogram = float(row.get("macd_histogram") or 0)
    macd_above = row.get("macd_above_zero", False)
    checks["macd_turn"] = histogram > 0 or (histogram > -0.5 and not macd_above)

    # Check 3: RSI recovery — wider range than confirmation (35-75)
    rsi = float(row.get("rsi") or 50)
    checks["rsi_recovery"] = 35 < rsi < 75

    # Check 4: Near support — price within 5% above support
    price = float(row.get("price") or 0)
    support = float(row.get("support") or 0)
    if support > 0 and price > 0:
        dist_to_support_pct = ((price - support) / price) * 100
        checks["near_support"] = 0 <= dist_to_support_pct <= 5
    else:
        checks["near_support"] = False

    # Check 5: Room to run — price > 8% from resistance
    resistance = float(row.get("resistance") or 0)
    if resistance > 0 and price > 0:
        dist_to_resist_pct = ((resistance - price) / price) * 100
        checks["room_to_run"] = dist_to_resist_pct >= 8
    else:
        checks["room_to_run"] = True

    return checks


DISCOVERY_CHECK_LABELS = {
    "volume_accel": "فوليوم متصاعد",
    "macd_turn": "MACD يتحول إيجابي",
    "rsi_recovery": "RSI يرتد من القاع",
    "near_support": "قريب من الدعم",
    "room_to_run": "مجال للصعود",
}


# ═══════════════════════════════════════════════════
# SECTOR MAP (KSE tickers → Arabic sector)
# ═══════════════════════════════════════════════════

_SECTOR_MAP = {
    "ZAIN": "الاتصالات", "OOREDOO": "الاتصالات", "STC": "الاتصالات",
    "NBK": "البنوك", "KFH": "البنوك", "CBK": "البنوك", "BKME": "البنوك",
    "GBK": "البنوك", "ABK": "البنوك", "BURG": "البنوك", "WARBA": "البنوك",
    "BOUBYAN": "البنوك", "AUB": "البنوك",
    "AGILITY": "النقل", "HUMANSOFT": "التعليم", "ALIMTIAZ": "الاستثمار",
    "MABANEE": "العقار", "KIPCO": "الاستثمار", "AAYAN": "الاستثمار",
}

_NAME_AR_MAP = {
    "ZAIN": "زين", "NBK": "الوطني", "KFH": "بيت التمويل", "CLEANING": "الاتصالات المتنقلة",
    "OOREDOO": "أوريدو", "HUMANSOFT": "هيومن سوفت", "AGILITY": "أجيليتي",
    "MABANEE": "المباني", "KIPCO": "كيبكو", "STC": "STC",
    "GBK": "الخليج", "ABK": "الأهلي", "CBK": "التجاري",
    "AAYAN": "أعيان", "BOUBYAN": "بوبيان", "AUB": "الأهلي المتحد",
    "WARBA": "وربة", "BURG": "برقان", "BKME": "الشرق الأوسط",
    "ALIMTIAZ": "الامتياز", "SENERGY": "سينرجي", "INOVEST": "إينوفست",
}


# ═══════════════════════════════════════════════════
# CORE: RUN CONFLUENCE SCAN
# ═══════════════════════════════════════════════════

def run_confluence_scan():
    """Scan all stocks in stock_radar_daily, compute confluence, store results.
    Returns list of HIGH conviction actionable signals.
    """
    try:
        conn = _conn()

        # Expire old signals
        conn.execute(
            "UPDATE confluence_signals SET is_active = 0 WHERE created_at < datetime('now', '-24 hours')"
        )

        # Read all daily data
        rows = conn.execute(
            "SELECT * FROM stock_radar_daily WHERE source_timeframe = '1D' ORDER BY score DESC"
        ).fetchall()

        if not rows:
            logger.info("No daily data for confluence scan")
            conn.close()
            return []

        results = []
        for row in rows:
            rd = dict(row)
            symbol = rd.get("symbol", "")
            price = rd.get("price")
            if not price or price <= 0:
                continue

            # Run 6 checks
            checks = {}
            passed = 0
            for name, fn in ALL_CHECKS:
                ok = fn(rd)
                checks[name] = ok
                if ok:
                    passed += 1

            score = round(passed / len(ALL_CHECKS) * 100)
            if passed >= 5:
                conviction = "HIGH"
            elif passed >= 4:
                conviction = "MEDIUM"
            else:
                conviction = "LOW"

            # Calculate R:R
            support = rd.get("support")
            resistance = rd.get("resistance")
            entry = price
            stop_loss = support if support and support > 0 else None
            target = resistance if resistance and resistance > 0 else None
            rr = None
            sl_pct = None

            if stop_loss and target and entry > stop_loss:
                risk = entry - stop_loss
                reward = target - entry
                if risk > 0:
                    rr = round(reward / risk, 2)
                    sl_pct = round((risk / entry) * 100, 1)

            results.append({
                "symbol": symbol,
                "name_ar": _NAME_AR_MAP.get(symbol, rd.get("name_ar", symbol)),
                "price": price,
                "confluence_score": score,
                "conviction": conviction,
                "checks": checks,
                "passed": passed,
                "rvol": rd.get("vol_ratio"),
                "rsi": rd.get("rsi"),
                "change_pct": rd.get("change_pct"),
                "support": support,
                "resistance": resistance,
                "entry": entry,
                "stop_loss": stop_loss,
                "target": target,
                "risk_reward": rr,
                "sl_pct": sl_pct,
                "sector": _SECTOR_MAP.get(symbol, ""),
                "macd_cross": rd.get("macd_cross"),
                "ema_cross": rd.get("daily_ema_cross"),
                "mode": "confirmation",
            })

            # --- Discovery Mode ---
            disc_checks = _discovery_checks(rd)
            disc_passed = sum(1 for v in disc_checks.values() if v)
            disc_total = len(disc_checks)
            disc_score = round(disc_passed / disc_total * 100) if disc_total > 0 else 0

            if disc_passed >= 4:
                disc_conviction = "HIGH"
            elif disc_passed >= 3:
                disc_conviction = "MEDIUM"
            else:
                disc_conviction = "LOW"

            disc_sl = support if support and support > 0 else price * 0.96
            disc_tp = resistance if resistance and resistance > 0 else price * 1.12
            disc_risk = price - disc_sl
            disc_reward = disc_tp - price
            disc_rr = round(disc_reward / disc_risk, 2) if disc_risk > 0 else 0
            disc_sl_pct = round(disc_risk / price * 100, 1) if price > 0 else 0

            if disc_conviction in ("HIGH", "MEDIUM"):
                results.append({
                    "symbol": symbol,
                    "name_ar": _NAME_AR_MAP.get(symbol, rd.get("name_ar", symbol)),
                    "price": price,
                    "confluence_score": disc_score,
                    "conviction": disc_conviction,
                    "checks": disc_checks,
                    "passed": disc_passed,
                    "rvol": rd.get("vol_ratio"),
                    "rsi": rd.get("rsi"),
                    "change_pct": rd.get("change_pct"),
                    "support": support,
                    "resistance": resistance,
                    "entry": price,
                    "stop_loss": disc_sl,
                    "target": disc_tp,
                    "risk_reward": disc_rr,
                    "sl_pct": disc_sl_pct,
                    "sector": _SECTOR_MAP.get(symbol, ""),
                    "macd_cross": rd.get("macd_cross"),
                    "ema_cross": rd.get("daily_ema_cross"),
                    "mode": "discovery",
                })

        # Store signals in DB (only HIGH and MEDIUM) — with dedup
        # UTC, column format: every reader compares these against SQLite
        # datetime("now") (UTC, space). The old local isoformat stamps
        # gave every signal a 27h lifetime instead of 24 (C-11), plus the
        # same-date T-vs-space sort quirk on top.
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        expires = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        stored = 0
        for r in results:
            if r["conviction"] in ("HIGH", "MEDIUM"):
                _mode = r.get("mode", "confirmation")
                _sig_type = "discovery_buy" if _mode == "discovery" and r["conviction"] == "HIGH" and (r.get("risk_reward") or 0) >= 1.5 else \
                            "discovery_watch" if _mode == "discovery" else \
                            "buy_signal" if r["conviction"] == "HIGH" and (r.get("risk_reward") or 0) >= 2.0 else \
                            "watch"
                _checks_str = ",".join(k for k, v in r["checks"].items() if v)
                # Dedup: check if same symbol+signal_type+mode already active within 24h
                existing = conn.execute(
                    """SELECT id FROM confluence_signals
                       WHERE symbol = ? AND signal_type = ? AND mode = ?
                         AND is_active = 1
                         AND created_at > datetime('now', '-24 hours')
                       LIMIT 1""",
                    (r["symbol"], _sig_type, _mode)
                ).fetchone()
                if existing:
                    # Update existing signal instead of creating duplicate
                    conn.execute("""
                        UPDATE confluence_signals
                        SET price = ?, confluence_score = ?, conviction = ?,
                            checks_passed = ?, rvol = ?, rsi = ?,
                            macd_conf = ?, trend = ?, ema_position = ?, not_overbought = ?,
                            support = ?, resistance = ?,
                            entry_price = ?, stop_loss = ?, target_price = ?,
                            risk_reward = ?, sl_pct = ?, change_pct = ?, sector = ?,
                            expires_at = ?
                        WHERE id = ?
                    """, (
                        r["price"], r["confluence_score"], r["conviction"],
                        _checks_str, r["rvol"], r["rsi"],
                        1 if r["checks"].get("macd") or r["checks"].get("macd_turn") else 0,
                        1 if r["checks"].get("trend") or r["checks"].get("volume_accel") else 0,
                        1 if r["checks"].get("ema") or r["checks"].get("near_support") else 0,
                        1 if r["checks"].get("not_ob") or r["checks"].get("room_to_run") else 0,
                        r["support"], r["resistance"],
                        r["entry"], r["stop_loss"], r["target"],
                        r["risk_reward"], r["sl_pct"], r["change_pct"], r["sector"],
                        expires,
                        existing["id"],
                    ))
                else:
                    conn.execute("""
                        INSERT INTO confluence_signals
                        (symbol, name_ar, price, confluence_score, conviction, checks_passed,
                         rvol, rsi, macd_conf, trend, ema_position, not_overbought,
                         support, resistance, entry_price, stop_loss, target_price,
                         risk_reward, sl_pct, signal_type, change_pct, sector,
                         mode, created_at, expires_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        r["symbol"], r["name_ar"], r["price"], r["confluence_score"],
                        r["conviction"], _checks_str,
                        r["rvol"], r["rsi"],
                        1 if r["checks"].get("macd") or r["checks"].get("macd_turn") else 0,
                        1 if r["checks"].get("trend") or r["checks"].get("volume_accel") else 0,
                        1 if r["checks"].get("ema") or r["checks"].get("near_support") else 0,
                        1 if r["checks"].get("not_ob") or r["checks"].get("room_to_run") else 0,
                        r["support"], r["resistance"],
                        r["entry"], r["stop_loss"], r["target"],
                        r["risk_reward"], r["sl_pct"], _sig_type,
                        r["change_pct"], r["sector"],
                        _mode, now, expires,
                    ))
                stored += 1

        conn.commit()
        conn.close()

        # Actionable: confirmation (R:R>=2) + discovery (R:R>=1.5)
        actionable = [r for r in results
                      if r["conviction"] == "HIGH"
                      and r["risk_reward"] is not None
                      and ((r.get("mode") == "confirmation" and r["risk_reward"] >= 2.0)
                           or (r.get("mode") == "discovery" and r["risk_reward"] >= 1.5))]

        disc_count = sum(1 for r in results if r.get("mode") == "discovery")
        conf_count = sum(1 for r in results if r.get("mode") == "confirmation")
        logger.info(
            f"Confluence scan: {len(rows)} stocks, "
            f"conf={conf_count} disc={disc_count}, "
            f"{len(actionable)} actionable, {stored} stored"
        )
        return actionable

    except Exception as e:
        logger.error(f"Confluence scan error: {e}")
        return []


# ═══════════════════════════════════════════════════
# QUERY FUNCTIONS
# ═══════════════════════════════════════════════════

def get_actionable_signals(limit=5, mode=None):
    """Return latest HIGH conviction signals.
    mode=None: both discovery+confirmation, mode='discovery'/'confirmation': filter.
    """
    try:
        with _conn() as c:
            mode_filter = f"AND mode = '{mode}'" if mode else ""
            rows = c.execute(f"""
                SELECT * FROM confluence_signals
                WHERE is_active = 1
                  AND signal_type IN ('buy_signal', 'discovery_buy')
                  AND created_at > datetime('now', '-24 hours')
                  {mode_filter}
                ORDER BY confluence_score DESC, risk_reward DESC
                LIMIT ?
            """, (limit * 3,)).fetchall()  # fetch extra to allow dedup
            all_items = [_sig_to_dict(r) for r in rows]
            deduped = _dedup_items_keep_latest(all_items)
            return deduped[:limit]
    except Exception as e:
        logger.error(f"get_actionable error: {e}")
        return []


def get_watchlist_signals(limit=10, mode=None):
    """Return MEDIUM conviction or watch signals.
    mode=None: both, mode='discovery'/'confirmation': filter.
    """
    try:
        with _conn() as c:
            mode_filter = f"AND mode = '{mode}'" if mode else ""
            rows = c.execute(f"""
                SELECT * FROM confluence_signals
                WHERE is_active = 1
                  AND signal_type IN ('watch', 'discovery_watch')
                  AND created_at > datetime('now', '-24 hours')
                  {mode_filter}
                ORDER BY confluence_score DESC, risk_reward DESC
                LIMIT ?
            """, (limit * 3,)).fetchall()  # fetch extra to allow dedup
            all_items = [_sig_to_dict(r) for r in rows]
            deduped = _dedup_items_keep_latest(all_items)
            return deduped[:limit]
    except Exception as e:
        logger.error(f"get_watchlist error: {e}")
        return []


def get_confluence_stats():
    """Stats for dashboard"""
    try:
        with _conn() as c:
            recent = c.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN conviction='HIGH' THEN 1 ELSE 0 END) as high_count,
                    SUM(CASE WHEN conviction='MEDIUM' THEN 1 ELSE 0 END) as med_count,
                    AVG(confluence_score) as avg_score,
                    MAX(created_at) as last_scan
                FROM confluence_signals
                WHERE is_active = 1 AND created_at > datetime('now', '-24 hours')
            """).fetchone()
            if recent:
                return {
                    "total_scanned": recent["total"] or 0,
                    "high_count": recent["high_count"] or 0,
                    "medium_count": recent["med_count"] or 0,
                    "avg_confluence": round(recent["avg_score"] or 0),
                    "last_scan": recent["last_scan"] or "",
                }
            return {"total_scanned": 0, "high_count": 0, "medium_count": 0,
                    "avg_confluence": 0, "last_scan": ""}
    except Exception as e:
        logger.error(f"confluence_stats error: {e}")
        return {}


def record_decision(signal_id, symbol, decision, price=None):
    """Record user's buy/skip decision"""
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO confluence_decisions (signal_id, symbol, decision, entry_price) VALUES (?,?,?,?)",
                (signal_id, symbol, decision, price)
            )
        logger.info(f"Confluence decision: {decision} {symbol} signal={signal_id}")
    except Exception as e:
        logger.error(f"record_decision error: {e}")


def _sig_to_dict(row):
    """Convert DB row to API-friendly dict"""
    d = dict(row)
    cp = d.get("checks_passed", "")
    checks_list = [c.strip() for c in cp.split(",") if c.strip()] if cp else []
    passed_set = set(checks_list)
    _mode = d.get("mode", "confirmation")
    if _mode == "discovery":
        # Discovery check names: volume_accel, macd_turn, rsi_recovery, near_support, room_to_run
        d["checks"] = {
            "volume_accel": "volume_accel" in passed_set,
            "macd_turn": "macd_turn" in passed_set,
            "rsi_recovery": "rsi_recovery" in passed_set,
            "near_support": "near_support" in passed_set,
            "room_to_run": "room_to_run" in passed_set,
        }
    else:
        # Confirmation check names: rvol, macd, rsi, trend, ema, not_ob
        d["checks"] = {
            "rvol": "rvol" in passed_set,
            "macd": "macd" in passed_set,
            "rsi": "rsi" in passed_set,
            "trend": "trend" in passed_set,
            "ema": "ema" in passed_set,
            "not_ob": "not_ob" in passed_set,
        }
    d["entry"] = d.get("entry_price")
    d["stop"] = d.get("stop_loss")
    d["target"] = d.get("target_price")
    return d


# ═══════════════════════════════════════════════════
# TG ALERT BUILDER
# ═══════════════════════════════════════════════════

def build_tg_alert(signal):
    """Build Telegram alert message + inline keyboard for a HIGH conviction signal."""
    sym = signal.get("symbol", "?")
    name = signal.get("name_ar", sym)
    price = signal.get("price", 0)
    score = signal.get("confluence_score", 0)
    passed = sum(1 for v in signal.get("checks", {}).values() if v)
    total = len(signal.get("checks", {})) or 6
    rsi = signal.get("rsi")
    rvol = signal.get("rvol")
    entry = signal.get("entry", price)
    stop = signal.get("stop_loss") or signal.get("stop")
    target = signal.get("target_price") or signal.get("target")
    rr = signal.get("risk_reward")
    sl_pct = signal.get("sl_pct")
    checks = signal.get("checks", {})
    sig_id = signal.get("id", 0)
    mode = signal.get("mode", "confirmation")

    is_discovery = mode == "discovery"

    if is_discovery:
        header = f"🔍 اكتشاف مبكر — {sym} ({name})"
        score_label = "Discovery"
    else:
        header = f"🎯 فرصة شراء — {sym} ({name})"
        score_label = "Confluence"

    lines = [
        header,
        "━━━━━━━━━━━━━━━━━━━━",
        f"📊 {score_label}: {score}% ({passed}/{total})",
        f"💰 السعر: {price} فلس",
        f"📈 RVOL: {round(rvol, 1) if rvol else '—'}x | RSI: {round(rsi) if rsi else '—'}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    if is_discovery:
        check_labels = DISCOVERY_CHECK_LABELS
    else:
        check_labels = {
            "rvol": "الفوليوم يدعم",
            "macd": "MACD صاعد",
            "rsi": "RSI منطقة مثالية",
            "trend": "الترند صاعد",
            "ema": "فوق EMA21",
            "not_ob": "مو overbought",
        }
    for k, label in check_labels.items():
        if checks.get(k):
            lines.append(f"✅ {label}")
        else:
            lines.append(f"❌ {label}")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(
        f"🎯 الدخول: {entry} | الوقف: {stop or '—'}"
        + (f" (-{sl_pct}%)" if sl_pct else "")
    )
    lines.append(
        f"🏁 الهدف: {target or '—'} | R:R = {rr or '—'}"
    )

    text = "\n".join(lines)

    # Inline keyboard — same pattern as trade_confirm
    cb_data = f"{sym}|{price}|buy|confluence|0|{sig_id}"
    keyboard = {
        "inline_keyboard": [[
            {"text": "شريت ✅", "callback_data": f"confluence_buy:{cb_data}"},
            {"text": "تجاهلت ❌", "callback_data": f"confluence_skip:{sig_id}|{sym}"},
        ]]
    }

    return text, keyboard
