"""
tv_advisor.py - AI Trading Advisor for Master AI
Combines technical analysis + user strategies + LLM for opinions.
"""
import logging
logger = logging.getLogger("tv_advisor")

USER_STRATEGIES = {
    "CLEANING": {
        "name": "CLEANING V3", "method": "SSA+VWAP+Trail", "returns": "117%",
        "trail": {"pct":4,"step":1.5,"sl":3},
        "notes": "Institutional accumulation pattern",
    },
    "SENERGY": {
        "name": "SENERGY V5", "method": "HH+HL+RSI rising+Trail", "returns": "104%",
        "trail": {"pct":4,"step":1.5,"sl":3},
        "notes": "Khurafi group pattern, target 140-180",
    },
    "INOVEST": {
        "name": "INOVEST V5", "method": "HMA-Kahlman+Trail", "returns": "N/A",
        "trail": {"pct":4,"step":1.5,"sl":3}, "notes": "",
    },
}

TRAIL_PARAMS = {
    "small_tf": {"trail":4,"step":1.5,"sl":3},
    "daily_tf": {"trail":12,"step":2,"sl":4},
}

def build_advisor_prompt(analysis, question=""):
    t = analysis.get("ticker","")
    strat = USER_STRATEGIES.get(t)
    ind = analysis.get("indicators",{})
    lv = analysis.get("levels",{})
    vol = analysis.get("volume_signal",{})
    parts = [
        "\u0623\u0646\u062a \u0645\u0633\u062a\u0634\u0627\u0631 \u062a\u062f\u0627\u0648\u0644 \u0645\u062d\u062a\u0631\u0641 \u0641\u064a \u0628\u0648\u0631\u0635\u0629 \u0627\u0644\u0643\u0648\u064a\u062a. \u0623\u062c\u0628 \u0628\u0627\u0644\u0639\u0631\u0628\u064a \u0627\u0644\u0643\u0648\u064a\u062a\u064a.",
        f"\u0627\u0644\u0633\u0647\u0645: {analysis.get('name_ar',t)} ({t})",
        f"\u0627\u0644\u0633\u0639\u0631: {analysis.get('price','N/A')} fils",
        f"\u0627\u0644\u062a\u063a\u064a\u0631: {analysis.get('change_pct',0):+.2f}%",
        f"\u0627\u0644\u062d\u062c\u0645: {analysis.get('volume',0):,}",
    ]
    if ind.get("rsi_14"): parts.append(f"RSI(14)={ind['rsi_14']} ({ind.get('rsi_zone','')})")
    if ind.get("ema_9") and ind.get("ema_21"): parts.append(f"EMA9={ind['ema_9']}, EMA21={ind['ema_21']} ({ind.get('ema_signal','')})")
    if ind.get("vwap"): parts.append(f"VWAP={ind['vwap']}")
    if ind.get("macd"): parts.append(f"MACD={ind['macd'].get('macd','N/A')}")
    if lv: parts.append(f"R: {lv.get('resistance_1','?')}/{lv.get('resistance_2','?')} S: {lv.get('support_1','?')}/{lv.get('support_2','?')}")
    if vol.get("signal","normal")!="normal": parts.append(f"Volume: {vol['signal']} x{vol.get('ratio',0)}")
    if strat:
        parts.append(f"\n\u0627\u0633\u062a\u0631\u0627\u062a\u064a\u062c\u064a\u0629: {strat['name']} ({strat['method']})")
        parts.append(f"Returns: {strat['returns']}, Trail: {strat['trail']['pct']}%/{strat['trail']['step']}%/SL{strat['trail']['sl']}%")
        if strat.get("notes"): parts.append(f"Notes: {strat['notes']}")
    parts.append(f"\nAuto verdict: {analysis.get('verdict','N/A')} (score={analysis.get('score',0)}), Trend: {analysis.get('trend','N/A')}")
    if question: parts.append(f"\n\u0633\u0624\u0627\u0644: {question}")
    parts.append("\n\u0627\u0639\u0637\u0646\u064a \u0631\u0623\u064a\u0643 \u0627\u0644\u0645\u062e\u062a\u0635\u0631: 1)\u062d\u0643\u0645 2)\u062f\u062e\u0648\u0644 3)\u0648\u0642\u0641/\u0647\u062f\u0641 4)\u0645\u0644\u0627\u062d\u0638\u0629. \u0627\u0633\u062a\u062e\u062f\u0645 \u0623\u0631\u0642\u0627\u0645.")
    return chr(10).join(parts)

def get_strategy_for_ticker(ticker):
    return USER_STRATEGIES.get(ticker)

def format_advisor_response(analysis, llm_response):
    from tv_analysis import format_analysis_arabic
    ta = format_analysis_arabic(analysis)
    return ta + chr(10)*2 + "\u2500"*30 + chr(10) + "\U0001f9e0 \u0631\u0623\u064a \u0627\u0644\u0645\u0633\u062a\u0634\u0627\u0631:" + chr(10) + llm_response
