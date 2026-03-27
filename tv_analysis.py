"""
tv_analysis.py - Technical Analysis Engine for Master AI
Computes RSI, EMA, VWAP, support/resistance, signals. Zero LLM cost.
"""
import logging
logger = logging.getLogger("tv_analysis")

def compute_rsi(closes, period=14):
    if len(closes) < period + 1: return None
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    recent = deltas[-period:]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_g = sum(gains)/period if gains else 0
    avg_l = sum(losses)/period if losses else 0.0001
    return round(100 - 100/(1 + avg_g/avg_l), 2)

def compute_ema(closes, period):
    if len(closes) < period: return None
    k = 2/(period+1)
    ema = sum(closes[:period])/period
    for p in closes[period:]: ema = p*k + ema*(1-k)
    return round(ema, 3)

def compute_vwap(highs, lows, closes, volumes):
    if not highs or not volumes: return None
    tpv = sum((h+l+c)/3*v for h,l,c,v in zip(highs,lows,closes,volumes))
    vs = sum(volumes)
    return round(tpv/vs, 3) if vs else None

def compute_sma(values, period):
    if len(values) < period: return None
    return round(sum(values[-period:])/period, 3)

def find_support_resistance(highs, lows, closes, lookback=20):
    lb = min(lookback, len(closes))
    h, l, c = max(highs[-lb:]), min(lows[-lb:]), closes[-1]
    pivot = (h+l+c)/3
    return {
        "pivot": round(pivot,3), "resistance_1": round(2*pivot-l,3),
        "resistance_2": round(pivot+(h-l),3), "support_1": round(2*pivot-h,3),
        "support_2": round(pivot-(h-l),3), "range_high": round(h,3), "range_low": round(l,3),
    }

def compute_macd(closes):
    if len(closes) < 26: return None
    e12, e26 = compute_ema(closes,12), compute_ema(closes,26)
    if not e12 or not e26: return None
    ml = round(e12-e26, 3)
    return {"macd": ml, "ema12": e12, "ema26": e26}

def compute_atr(highs, lows, closes, period=14):
    if len(closes) < period+1: return None
    trs = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1,len(closes))]
    return round(sum(trs[-period:])/period, 3)

def detect_trend(closes):
    e9, e21 = compute_ema(closes,9), compute_ema(closes,21)
    if not e9 or not e21: return "unknown"
    return "bullish" if e9>e21 else "bearish" if e9<e21 else "neutral"

def detect_volume_signal(volumes, lookback=20):
    if len(volumes) < lookback+1: return {"signal":"insufficient_data"}
    avg = sum(volumes[-lookback-1:-1])/lookback
    cur = volumes[-1]
    r = cur/avg if avg else 0
    sig = "extreme_volume" if r>3 else "high_volume" if r>2 else "dry_volume" if r<0.3 else "normal"
    return {"signal": sig, "current_volume": int(cur), "avg_volume": int(avg), "ratio": round(r,2)}

def full_analysis(price_data):
    if "error" in price_data: return price_data
    h = price_data.get("history",{})
    cl, hi, lo, vol = h.get("close",[]), h.get("high",[]), h.get("low",[]), h.get("volume",[])
    if not cl: return {"error":"No history"}
    rsi = compute_rsi(cl)
    e9, e21, e50 = compute_ema(cl,9), compute_ema(cl,21), compute_ema(cl,50) if len(cl)>=50 else None
    vwap = compute_vwap(hi,lo,cl,vol)
    macd = compute_macd(cl)
    atr = compute_atr(hi,lo,cl)
    sr = find_support_resistance(hi,lo,cl)
    trend = detect_trend(cl)
    vsig = detect_volume_signal(vol)
    rsi_zone = "oversold" if rsi and rsi<=30 else "overbought" if rsi and rsi>=70 else "neutral"
    ema_sig = "bullish_cross" if e9 and e21 and e9>e21 else "bearish_cross" if e9 and e21 else "neutral"
    score, reasons = 0, []
    if rsi and rsi<=30: score+=2; reasons.append(f"RSI={rsi} oversold")
    elif rsi and rsi>=70: score-=2; reasons.append(f"RSI={rsi} overbought")
    if ema_sig=="bullish_cross": score+=1; reasons.append("EMA9>EMA21")
    elif ema_sig=="bearish_cross": score-=1; reasons.append("EMA9<EMA21")
    if vsig["signal"] in ("high_volume","extreme_volume"):
        if trend=="bullish": score+=1; reasons.append(f"Volume spike + uptrend x{vsig['ratio']}")
        else: score-=1; reasons.append(f"Volume spike + downtrend x{vsig['ratio']}")
    price = price_data["price"]
    if vwap and price<vwap*0.97: score+=1; reasons.append(f"Below VWAP({vwap})")
    elif vwap and price>vwap*1.03: score-=1; reasons.append(f"Above VWAP({vwap})")
    verdict = "STRONG_BUY" if score>=3 else "BUY" if score>=1 else "STRONG_SELL" if score<=-3 else "SELL" if score<=-1 else "HOLD"
    return {
        "ticker": price_data["ticker"], "name_ar": price_data.get("name_ar",""),
        "price": price, "change": price_data["change"], "change_pct": price_data["change_pct"],
        "volume": price_data["volume"], "market_open": price_data.get("market_open",False),
        "indicators": {"rsi_14":rsi,"rsi_zone":rsi_zone,"ema_9":e9,"ema_21":e21,"ema_50":e50,
            "ema_signal":ema_sig,"sma_20":compute_sma(cl,20),"vwap":vwap,"macd":macd,"atr":atr},
        "levels": sr, "trend": trend, "volume_signal": vsig,
        "score": score, "verdict": verdict, "reasons": reasons,
        "timestamp": price_data.get("timestamp",""),
    }

def format_analysis_arabic(a):
    if "error" in a: return f"\u274c {a['error']}"
    t, n, p = a["ticker"], a.get("name_ar",a["ticker"]), a["price"]
    ch, cp = a["change"], a["change_pct"]
    ind, lv = a["indicators"], a["levels"]
    arrow = "\u2b06\ufe0f" if ch>=0 else "\u2b07\ufe0f"
    mkt = "\U0001f7e2 \u0645\u0641\u062a\u0648\u062d" if a.get("market_open") else "\U0001f534 \u0645\u063a\u0644\u0642"
    vd = {"STRONG_BUY":"\U0001f7e2 \u0634\u0631\u0627\u0621 \u0642\u0648\u064a","BUY":"\U0001f7e2 \u0634\u0631\u0627\u0621",
          "HOLD":"\U0001f7e1 \u0627\u0646\u062a\u0638\u0627\u0631","SELL":"\U0001f534 \u0628\u064a\u0639",
          "STRONG_SELL":"\U0001f534 \u0628\u064a\u0639 \u0642\u0648\u064a"}.get(a["verdict"],a["verdict"])
    lines = [f"\U0001f4ca {n} ({t})", f"{arrow} {p} fils | {ch:+.1f} ({cp:+.2f}%)",
             f"\U0001f4c8 Vol: {a['volume']:,} | {mkt}", ""]
    if ind["rsi_14"]: lines.append(f"  RSI(14)={ind['rsi_14']} {ind['rsi_zone']}")
    if ind["ema_9"] and ind["ema_21"]: lines.append(f"  EMA 9={ind['ema_9']}|21={ind['ema_21']} {ind['ema_signal']}")
    if ind["vwap"]: lines.append(f"  VWAP={ind['vwap']}")
    if ind["macd"]: lines.append(f"  MACD={ind['macd']['macd']}")
    if ind["atr"]: lines.append(f"  ATR={ind['atr']}")
    lines += ["", f"  R2:{lv['resistance_2']} R1:{lv['resistance_1']}", f"  Pivot:{lv['pivot']}",
              f"  S1:{lv['support_1']} S2:{lv['support_2']}", "", f"\U0001f3c1 {vd}"]
    if a["reasons"]: lines += [""] + [f"  \u2022 {r}" for r in a["reasons"]]
    return chr(10).join(lines)


def compute_stoch_k(highs, lows, closes, k_period=14, d_period=3):
    """Stochastic %K oscillator."""
    if len(closes) < k_period: return None
    h_max = max(highs[-k_period:])
    l_min = min(lows[-k_period:])
    if h_max == l_min: return 50.0
    raw_k = ((closes[-1] - l_min) / (h_max - l_min)) * 100
    return round(raw_k, 2)


def compute_adx(highs, lows, closes, period=14):
    """Average Directional Index (ADX)."""
    if len(closes) < period * 2: return None
    plus_dm, minus_dm, tr_list = [], [], []
    for i in range(1, len(closes)):
        h_diff = highs[i] - highs[i-1]
        l_diff = lows[i-1] - lows[i]
        plus_dm.append(h_diff if h_diff > l_diff and h_diff > 0 else 0)
        minus_dm.append(l_diff if l_diff > h_diff and l_diff > 0 else 0)
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        tr_list.append(tr)
    if len(tr_list) < period: return None
    k = 2 / (period + 1)
    atr = sum(tr_list[:period]) / period
    plus_di_sm = sum(plus_dm[:period]) / period
    minus_di_sm = sum(minus_dm[:period]) / period
    dx_list = []
    for i in range(period, len(tr_list)):
        atr = atr * (1 - k) + tr_list[i] * k
        plus_di_sm = plus_di_sm * (1 - k) + plus_dm[i] * k
        minus_di_sm = minus_di_sm * (1 - k) + minus_dm[i] * k
        if atr == 0: continue
        plus_di = (plus_di_sm / atr) * 100
        minus_di = (minus_di_sm / atr) * 100
        di_sum = plus_di + minus_di
        dx = abs(plus_di - minus_di) / di_sum * 100 if di_sum != 0 else 0
        dx_list.append(dx)
    if len(dx_list) < period: return None
    adx = sum(dx_list[-period:]) / period
    return round(adx, 2)


def detect_rsi_divergence(closes, rsi_values=None, period=14, lookback=10):
    """Detect bullish/bearish RSI divergence."""
    if len(closes) < period + lookback + 5: return None
    if rsi_values is None:
        rsi_values = []
        for i in range(period + 1, len(closes) + 1):
            r = compute_rsi(closes[:i], period)
            if r is not None: rsi_values.append(r)
    if len(rsi_values) < lookback: return None
    recent_rsi = rsi_values[-lookback:]
    recent_price = closes[-lookback:]
    price_rising = recent_price[-1] > recent_price[0]
    rsi_falling = recent_rsi[-1] < recent_rsi[0]
    price_falling = recent_price[-1] < recent_price[0]
    rsi_rising = recent_rsi[-1] > recent_rsi[0]
    if price_falling and rsi_rising: return "bullish"
    if price_rising and rsi_falling: return "bearish"
    return None
