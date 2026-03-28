"""
trading_decision_engine.py — Entry Timing + Trade Plan.
Converts golden opportunities into actionable trade decisions.

Entry statuses:
  enter_now     — الآن هو الوقت المناسب
  wait_pullback — انتظر رجوع للمنطقة
  watch         — راقب، التأكيد ناقص
  missed        — فات القطار
  avoid         — تجنب
"""
import logging

logger = logging.getLogger("decision_engine")

STATUS_AR = {
    "enter_now":     "🟢 ادخل الآن",
    "wait_pullback": "🟡 انتظر pullback",
    "watch":         "⚪ راقب",
    "missed":        "🔴 فات القطار",
    "avoid":         "⛔ تجنب",
}


def _status(key, score, reasons, trade_plan):
    return {
        "entry_status":    key,
        "entry_status_ar": STATUS_AR.get(key, key),
        "entry_score":     score,
        "reasoning_ar":    reasons,
        "trade_plan":      trade_plan,
    }


def compute_entry_status(opp: dict, profile: dict) -> dict:
    """
    Determine entry timing for an opportunity.

    opp: opportunity dict from golden_engine
         (needs: price, support/key_support, resistance/key_resistance, atr_14,
          current_vol, current_stoch, current_rsi, confidence, win_rate, avg_gain_pct)
    profile: stock_profiles row (key_support, key_resistance, etc.)

    Returns dict with entry_status, entry_status_ar, entry_score, reasoning_ar, trade_plan.
    """
    price = float(opp.get("price") or 0)
    if price <= 0:
        return _status("watch", 30, ["لا يوجد سعر حي"], None)

    # S/R levels — prefer profile (from sr_engine), fallback to live opp
    support    = float(profile.get("key_support")    or opp.get("key_support")    or opp.get("support")    or 0)
    resistance = float(profile.get("key_resistance") or opp.get("key_resistance") or opp.get("resistance") or 0)
    atr        = float(opp.get("atr_14") or opp.get("atr") or price * 0.02)

    # ─── Entry zone ────────────────────────────────────────────
    if support > 0:
        entry_low  = max(support * 0.998, price - atr * 0.8)
        entry_high = min(price + atr * 0.2, support + atr * 1.5)
        # Guard: support far below price → zone becomes inverted; fall back
        if entry_high < entry_low:
            entry_low  = price - atr * 0.5
            entry_high = price + atr * 0.2
    else:
        entry_low  = price - atr * 0.5
        entry_high = price + atr * 0.2

    # ─── Stop loss ─────────────────────────────────────────────
    if support > 0 and entry_low > 0 and (entry_low - support) / entry_low < 0.10:
        # Support is close to entry — place stop just below it
        stop = min(support - atr * 0.6, entry_low - atr * 0.5)
    else:
        # Support far away (or absent) — use tight ATR stop from entry zone
        stop = entry_low - atr * 0.5

    # ─── Targets ───────────────────────────────────────────────
    hist_gain = float(opp.get("avg_gain_pct") or 0)
    target_1  = resistance if resistance > price else price * (1 + max(hist_gain, 3) / 100)
    target_2  = price * (1 + max(hist_gain * 1.5, 5) / 100)
    if resistance > price:
        target_2 = max(target_2, resistance * 1.02)

    # ─── R/R ───────────────────────────────────────────────────
    entry_mid = (entry_low + entry_high) / 2
    risk      = entry_mid - stop
    reward    = target_1 - entry_mid
    rr        = round(reward / risk, 2) if risk > 0 else 0

    trade_plan = {
        "entry_zone_low":   round(entry_low, 3),
        "entry_zone_high":  round(entry_high, 3),
        "entry_mid":        round(entry_mid, 3),
        "stop_loss":        round(stop, 3),
        "stop_distance_pct": round((entry_mid - stop) / entry_mid * 100, 1) if entry_mid > 0 else 0,
        "target_1":         round(target_1, 3),
        "target_2":         round(target_2, 3),
        "rr_ratio":         rr,
    }

    # ─── Indicator readings ────────────────────────────────────
    reasons    = []
    in_zone    = entry_low <= price <= entry_high
    vol_ok     = float(opp.get("current_vol") or opp.get("vol_ratio") or 0) >= 1.2
    stoch      = float(opp.get("current_stoch") or opp.get("stoch_k") or 50)
    rsi        = float(opp.get("current_rsi")   or opp.get("rsi_14") or opp.get("rsi") or 50)
    confidence = float(opp.get("confidence") or 0)

    # ─── Decision logic ────────────────────────────────────────

    # ⛔ AVOID — broken support
    if support > 0 and price < support * 0.99:
        reasons.append("السعر كسر الدعم")
        return _status("avoid", 10, reasons, trade_plan)

    # ⛔ AVOID — poor R/R
    if rr < 1.2:
        reasons.append("العائد/المخاطرة ضعيف ({:.1f}x)".format(rr))
        return _status("avoid", 15, reasons, trade_plan)

    # 🟢 ENTER NOW — full confirmation
    if in_zone and vol_ok and rr >= 1.8 and confidence >= 75:
        reasons.append("السعر داخل منطقة الدخول")
        reasons.append("الحجم يؤكد")
        if stoch < 30:
            reasons.append("Stoch متشبع بيعياً — ارتداد متوقع")
        if rsi < 35:
            reasons.append("RSI متشبع بيعياً")
        reasons.append("R/R {:.1f}x ممتاز".format(rr))
        return _status("enter_now", 90, reasons, trade_plan)

    # 🟢 ENTER NOW — relaxed (strong confidence, volume weak)
    if in_zone and rr >= 2.0 and confidence >= 80:
        reasons.append("السعر بمنطقة الدخول")
        if not vol_ok:
            reasons.append("الحجم مقبول — ادخل بحذر")
        reasons.append("Confidence {:.0f} عالي".format(confidence))
        return _status("enter_now", 80, reasons, trade_plan)

    # 🟡 WAIT PULLBACK — price above zone
    if price > entry_high and rr >= 1.5:
        pct_above = (price - entry_high) / entry_high * 100
        reasons.append("السعر فوق منطقة الدخول بـ{:.1f}%".format(pct_above))
        reasons.append("انتظر رجوع لمنطقة {:.0f}-{:.0f}".format(entry_low, entry_high))
        if resistance > 0 and (resistance - price) / price * 100 < 2:
            reasons.append("المقاومة قريبة — لا تطارد")
        return _status("wait_pullback", 65, reasons, trade_plan)

    # 🔴 MISSED — price near target already
    if resistance > 0 and price >= target_1 * 0.95:
        reasons.append("السعر وصل قرب الهدف")
        reasons.append("الحركة تحققت — فات القطار")
        return _status("missed", 20, reasons, trade_plan)

    # ⚪ WATCH
    reasons.append("النمط جيد بس التأكيد ناقص")
    if not vol_ok:
        reasons.append("الحجم ضعيف — انتظر تأكيد")
    if rr < 1.8:
        reasons.append("R/R {:.1f}x متوسط".format(rr))
    return _status("watch", 50, reasons, trade_plan)
