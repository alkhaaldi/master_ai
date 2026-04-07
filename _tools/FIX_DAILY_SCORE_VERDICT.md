# Fix: Daily Score/Verdict/Crosses Always Zero
# Date: 2026-03-28
# Root Cause: refresh_daily_snapshot computes score/verdict/crosses from scratch
#   but daily_signal=None (no cross detected between runs) → score=0, verdict=""
# Solution: Use Bridge's pre-computed signals + compute score independently of cross

---

## المشكلة بالتفصيل

### score = 0 دائماً
`_compute_score(daily_signal, ...)` — أول سطر: `if not signal: return 0, "D"`
`daily_signal` = None لأنه يعتمد على cross detection بين run حالي وسابق.
بس البيانات اليومية ثابتة → ما يتغير شي بين runs → لا cross → لا signal → لا score.

### verdict = "" دائماً  
`_smart_verdict(daily_signal, ...)` — نفس المشكلة: daily_signal = None → verdict فاضي.

### macd_cross = "none" دائماً
يقارن MACD الحالي مع MACD المحفوظ من الـ run السابق. بس الـ Bridge يرجع نفس البيانات → ما فيه تغيير → "none".

### daily_ema_cross = "none" دائماً
نفس السبب بالضبط.

---

## الحل: 3 إصلاحات

### Fix A: استخدم Bridge signals مباشرة لـ cross detection

Bridge يرجع `signals.ema_cross` و `signals.macd_momentum` جاهزين.
بدل ما نحسب cross من الصفر، نستخدمهم:

```python
# بعد ما نقرأ ind و q، نقرأ signals من Bridge:
bridge_signals = raw.get("signals") or {}
bridge_ema_cross = bridge_signals.get("ema_cross") or {}
bridge_confluence = bridge_signals.get("confluence") or {}
bridge_macd_mom = bridge_signals.get("macd_momentum") or ""

# EMA cross من Bridge
if isinstance(bridge_ema_cross, dict) and bridge_ema_cross.get("type"):
    cross_type = bridge_ema_cross["type"]  # "golden" or "death"
    cross_bars_ago = bridge_ema_cross.get("bars_ago", 0)
    if cross_type == "golden":
        daily_ema_cross = "bullish"
    elif cross_type == "death":
        daily_ema_cross = "bearish"
    else:
        daily_ema_cross = "none"
else:
    # Fallback: direction from EMA values
    daily_ema_cross = "bullish" if ema9 > ema21 else "bearish" if ema9 < ema21 else "none"

# MACD cross من histogram
if macd_hist > 0:
    macd_cross = "bullish"
elif macd_hist < 0:
    macd_cross = "bearish"
else:
    macd_cross = "none"
```

### Fix B: score يُحسب بدون الاعتماد على daily_signal

المشكلة إن `_compute_score` يحتاج `signal` (bullish_cross/bearish_cross) كأول parameter.
لو = None → return 0.

**الحل: أضف scoring بديل للتاب اليومي يستخدم Bridge confluence مباشرة:**

```python
# بدل:
score, score_class = _compute_score(daily_signal, rsi, None, price, vol_sig_proxy, ema9, ema21, None)

# استخدم:
# Option 1: Bridge confluence score (if available)
bridge_conf_score = bridge_confluence.get("score", 0)
if bridge_conf_score > 0:
    score = bridge_conf_score
    if score >= 75: score_class = "A"
    elif score >= 50: score_class = "B"
    elif score >= 30: score_class = "C"
    else: score_class = "D"
else:
    # Option 2: Brain-weighted confluence
    conf_result = _compute_confluence(None, {
        "daily_ema_cross": daily_ema_cross,
        "macd_cross": macd_cross,
        "macd_above_zero": macd_above_zero,
        "vol_ratio": vol_ratio,
        "rsi": rsi,
    })
    score = conf_result.get("confluence_score", 0)
    if score >= 75: score_class = "A"
    elif score >= 50: score_class = "B"
    elif score >= 30: score_class = "C"
    else: score_class = "D"
```

### Fix C: verdict يُحسب من Bridge data مباشرة

```python
# بدل:
verdict = _smart_verdict(daily_signal, rsi, None, price, vol_sig_proxy, ema9, ema21)

# استخدم verdict ذكي مبني على كل البيانات:
if score >= 70 and daily_ema_cross == "bullish" and vol_ratio >= 1.2:
    verdict = "\U0001f525 فرصة قوية"
elif score >= 50 and daily_ema_cross == "bullish":
    verdict = "\U0001f7e2 صاعد — مراقبة"
elif score >= 50 and macd_cross == "bullish":
    verdict = "\U0001f7e2 زخم صاعد"
elif score >= 40:
    verdict = "\U0001f7e1 محايد — انتظار"
elif score >= 20 and daily_ema_cross == "bearish":
    verdict = "\U0001f534 ضغط بيعي"
elif rsi and rsi < 30:
    verdict = "\U0001f7e2 تشبع بيعي — فرصة محتملة"
elif rsi and rsi > 70:
    verdict = "\U0001f534 تشبع شرائي — حذر"
else:
    verdict = "\u26AA محايد"
```

---

## الكود الكامل المعدّل

استبدل الكتلة من بعد قراءة `ema9, ema21` حتى قبل `conn.execute(INSERT...)`
(تقريباً من سطر 1159 إلى 1240) بهذا الكود:

```python
                # === EMA Direction (always set) ===
                if ema9 and ema21:
                    if ema9 > ema21:
                        trend_ar = "\u0635\u0627\u0639\u062f"
                    elif ema9 < ema21:
                        trend_ar = "\u0647\u0627\u0628\u0637"
                    else:
                        trend_ar = "\u0645\u062d\u0627\u064a\u062f"
                else:
                    trend_ar = "\u0645\u062d\u0627\u064a\u062f"

                # === Bridge pre-computed signals ===
                bridge_signals = raw.get("signals") or {}
                bridge_ema_cross = bridge_signals.get("ema_cross") or {}
                bridge_confluence = bridge_signals.get("confluence") or {}
                bridge_macd_mom = bridge_signals.get("macd_momentum") or ""

                # === EMA Cross from Bridge ===
                if isinstance(bridge_ema_cross, dict) and bridge_ema_cross.get("type"):
                    cross_type = bridge_ema_cross["type"]
                    if cross_type == "golden":
                        daily_ema_cross = "bullish"
                    elif cross_type == "death":
                        daily_ema_cross = "bearish"
                    else:
                        daily_ema_cross = "none"
                else:
                    daily_ema_cross = "bullish" if ema9 and ema21 and ema9 > ema21 else "bearish" if ema9 and ema21 and ema9 < ema21 else "none"

                # === MACD ===
                macd_val  = ind.get("macd") or 0
                macd_sig  = ind.get("macd_signal") or 0
                macd_hist = ind.get("macd_hist") or 0
                macd_cross = "bullish" if macd_hist > 0 else "bearish" if macd_hist < 0 else "none"
                macd_above_zero = bool(macd_val > 0)

                # === Other indicators ===
                stoch_k_val = ind.get("stoch_k")
                adx_val     = ind.get("adx")
                atr_val     = ind.get("atr_14")
                rsi_div_val = bridge_signals.get("rsi_divergence")
                if rsi_div_val == "none" or rsi_div_val == "":
                    rsi_div_val = None

                # S/R from top-level arrays
                sup_arr = raw.get("support", [])
                res_arr = raw.get("resistance", [])
                support    = sup_arr[0] if sup_arr else None
                resistance = res_arr[0] if res_arr else None

                # BB from indicators
                bb_squeeze_val  = bool(ind.get("bb_squeeze") or False)
                bb_bandwidth_val = ind.get("bb_bandwidth")

                # === Volume spike ===
                volume_spike = 1 if vol_ratio >= 2 else 0

                # === Score: use Bridge confluence if available, else compute ===
                bridge_conf_score = bridge_confluence.get("score", 0)
                if bridge_conf_score > 0:
                    score = bridge_conf_score
                else:
                    vol_sig_proxy = {"signal": "high_volume" if vol_ratio >= 1.5 else "normal", "ratio": vol_ratio}
                    conf_result = _compute_confluence(None, {
                        "daily_ema_cross": daily_ema_cross,
                        "macd_cross": macd_cross,
                        "macd_above_zero": macd_above_zero,
                        "vol_ratio": vol_ratio,
                        "rsi": rsi,
                    })
                    score = conf_result.get("confluence_score", 0)

                if score >= 75: score_class = "A"
                elif score >= 50: score_class = "B"
                elif score >= 30: score_class = "C"
                else: score_class = "D"

                # === Confluence for DB ===
                vol_sig_proxy = {"signal": "high_volume" if vol_ratio >= 1.5 else "normal", "ratio": vol_ratio}
                confluence = _compute_confluence(None, {
                    "daily_ema_cross": daily_ema_cross,
                    "macd_cross": macd_cross,
                    "macd_above_zero": macd_above_zero,
                    "vol_ratio": vol_ratio,
                    "rsi": rsi,
                })

                # === Verdict: smart, based on all data ===
                if score >= 70 and daily_ema_cross == "bullish" and vol_ratio >= 1.2:
                    verdict = "\U0001f525 \u0641\u0631\u0635\u0629 \u0642\u0648\u064a\u0629"
                elif score >= 50 and daily_ema_cross == "bullish":
                    verdict = "\U0001f7e2 \u0635\u0627\u0639\u062f \u2014 \u0645\u0631\u0627\u0642\u0628\u0629"
                elif score >= 50 and macd_cross == "bullish":
                    verdict = "\U0001f7e2 \u0632\u062e\u0645 \u0635\u0627\u0639\u062f"
                elif score >= 40:
                    verdict = "\U0001f7e1 \u0645\u062d\u0627\u064a\u062f \u2014 \u0627\u0646\u062a\u0638\u0627\u0631"
                elif daily_ema_cross == "bearish" and score < 40:
                    verdict = "\U0001f534 \u0636\u063a\u0637 \u0628\u064a\u0639\u064a"
                elif rsi and rsi < 30:
                    verdict = "\U0001f7e2 \u062a\u0634\u0628\u0639 \u0628\u064a\u0639\u064a \u2014 \u0641\u0631\u0635\u0629"
                elif rsi and rsi > 70:
                    verdict = "\U0001f534 \u062a\u0634\u0628\u0639 \u0634\u0631\u0627\u0626\u064a \u2014 \u062d\u0630\u0631"
                else:
                    verdict = "\u26AA \u0645\u062d\u0627\u064a\u062f"
```

---

## Testing

```bash
cd /home/pi/master_ai

# 1. Restart after changes:
bash _tools/restart_master_ai.sh 2>/dev/null || sudo systemctl restart master-ai.service

# 2. Run daily refresh:
venv/bin/python3 -c "
from stock_radar import refresh_daily_snapshot
import json
print(json.dumps(refresh_daily_snapshot(), default=str))
"

# 3. Check DB — should have scores and verdicts now:
venv/bin/python3 -c "
import sqlite3, json
c = sqlite3.connect('data/life.db')
c.row_factory = sqlite3.Row
rows = c.execute('SELECT symbol, score, score_class, verdict, macd_cross, daily_ema_cross, support, resistance FROM stock_radar_daily WHERE score > 0 LIMIT 10').fetchall()
print(f'Symbols with score > 0: {len(rows)}')
for r in rows:
    print(json.dumps(dict(r), ensure_ascii=False))
c.close()
"
# Expected: most symbols have score > 0 and verdicts in Arabic

# 4. Check API:
KEY=$(cat ~/.master_ai_key)
curl -s -H "X-API-Key: $KEY" http://localhost:9000/dashboard/radar | python3 -c "
import sys,json
d=json.load(sys.stdin)
ctx=d.get('radar_daily_context',[])
for s in ctx[:3]:
    print(f\"{s['symbol']}: score={s.get('score')} verdict={s.get('verdict')} sup={s.get('support')} res={s.get('resistance')} cross={s.get('daily_ema_cross')} macd={s.get('macd_cross')}\")
"
```

## Commit:
```bash
git add stock_radar.py
git commit -m "fix: daily score/verdict/crosses — use Bridge signals, remove cross-between-runs dependency"
```

---

## HOW TO EXECUTE

Tell Claude Code:
```
اقرأ _tools/FIX_DAILY_SCORE_VERDICT.md ونفذ:
استبدل الكتلة في refresh_daily_snapshot() — من بعد قراءة ema9/ema21 حتى قبل conn.execute(INSERT) — بالكود الجديد.
ثم restart + daily refresh + اختبر
```
