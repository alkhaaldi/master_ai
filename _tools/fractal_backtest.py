#!/usr/bin/env python3
"""
Fractal v3 Backtest Engine — Final
يختبر استراتيجية Fractal v3 على كل أسهم الرادار (128 سهم)
بيانات 30m من Bridge API (300 شمعة = ~10 أيام تداول)
"""
import json, sys, time, urllib.request, urllib.parse
from datetime import datetime
from pathlib import Path

BRIDGE_URL = "http://192.168.111.158:8059"
PIVOT_PERIOD = 10
BROKER_FEE_PCT = 0.125

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent
REPORT_PATH = PROJECT_DIR / "www" / "trading" / "fractal_report.html"


def get_radar_symbols():
    try:
        sys.path.insert(0, str(PROJECT_DIR))
        from stock_radar import WATCHLIST
        symbols = list(WATCHLIST) if hasattr(WATCHLIST, '__iter__') else []
        if symbols:
            print(f"  {len(symbols)} symbols from WATCHLIST")
            return symbols
    except Exception as e:
        print(f"  WATCHLIST err: {e}")
    try:
        import sqlite3
        db = PROJECT_DIR / "data" / "life.db"
        conn = sqlite3.connect(str(db))
        syms = [r[0] for r in conn.execute(
            "SELECT DISTINCT symbol FROM stock_radar_daily ORDER BY symbol")]
        conn.close()
        if syms:
            print(f"  {len(syms)} symbols from DB")
            return syms
    except Exception as e:
        print(f"  DB err: {e}")
    return []


def fetch_bars(symbol):
    """Fetch 300 bars of 30m data from Bridge"""
    url = f"{BRIDGE_URL}/analysis?symbol={symbol}&interval=30"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        bars = data.get("bars", [])
        return bars if bars else None
    except Exception:
        return None


def detect_pivots(bars, period=10):
    n = len(bars)
    ph, pl = [], []
    for i in range(period, n - period):
        h = bars[i]["high"]
        if all(bars[j]["high"] < h for j in range(i-period, i)) and \
           all(bars[j]["high"] < h for j in range(i+1, i+period+1)):
            ph.append((i, h))
        lo = bars[i]["low"]
        if all(bars[j]["low"] > lo for j in range(i-period, i)) and \
           all(bars[j]["low"] > lo for j in range(i+1, i+period+1)):
            pl.append((i, lo))
    return ph, pl


def classify(ph, pl):
    sigs = []
    for i in range(1, len(pl)):
        t = "HL" if pl[i][1] > pl[i-1][1] else "LL"
        sigs.append({"bar": pl[i][0], "p": pl[i][1], "t": t, "a": "buy"})
    for i in range(1, len(ph)):
        t = "HH" if ph[i][1] > ph[i-1][1] else "LH"
        sigs.append({"bar": ph[i][0], "p": ph[i][1], "t": t, "a": "sell"})
    sigs.sort(key=lambda x: x["bar"])
    return sigs


def simulate(sigs, bars, fee=0.125):
    trades, pos = [], None
    for s in sigs:
        if s["a"] == "buy" and pos is None:
            eb = min(s["bar"] + PIVOT_PERIOD, len(bars)-1)
            pos = {"ep": bars[eb]["close"], "eb": eb, "et": s["t"]}
        elif s["a"] == "sell" and pos is not None:
            xb = min(s["bar"] + PIVOT_PERIOD, len(bars)-1)
            xp = bars[xb]["close"]
            gp = ((xp - pos["ep"]) / pos["ep"]) * 100
            np_ = gp - (fee * 2)
            trades.append({"ep": pos["ep"], "xp": xp, "et": pos["et"],
                          "xt": s["t"], "gp": round(gp,3), "np": round(np_,3),
                          "bh": xb - pos["eb"]})
            pos = None
    return trades


def analyze(sym, trades):
    if not trades:
        return {"s": sym, "nt": 0, "w": 0, "l": 0, "wr": 0,
                "tr": 0, "ar": 0, "best": 0, "worst": 0, "abh": 0}
    w = len([t for t in trades if t["np"] > 0])
    tr = sum(t["np"] for t in trades)
    return {"s": sym, "nt": len(trades), "w": w, "l": len(trades)-w,
            "wr": round(w/len(trades)*100, 1), "tr": round(tr, 2),
            "ar": round(tr/len(trades), 2),
            "best": round(max(t["np"] for t in trades), 2),
            "worst": round(min(t["np"] for t in trades), 2),
            "abh": round(sum(t["bh"] for t in trades)/len(trades), 1)}


def gen_report(results, elapsed):
    results.sort(key=lambda x: x["tr"], reverse=True)
    swt = [r for r in results if r["nt"] > 0]
    snd = [r for r in results if r["nt"] == 0]
    at = sum(r["nt"] for r in results)
    aw = sum(r["w"] for r in results)
    owr = round(aw/at*100,1) if at else 0
    otr = round(sum(r["tr"] for r in results), 2)
    ps = len([r for r in results if r["tr"] > 0])
    ls = len([r for r in results if r["tr"] < 0 and r["nt"] > 0])
    avs = round(otr/len(swt),2) if swt else 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows = ""
    rk = 0
    for r in results:
        if r["nt"] == 0: continue
        rk += 1
        rc = "#00c853" if r["tr"] > 0 else "#ff5252"
        wc = "#00c853" if r["wr"] >= 50 else "#ff5252"
        rows += f'<tr><td>{rk}</td><td style="text-align:right;font-weight:700;color:#e8c56d">{r["s"]}</td>'
        rows += f'<td>{r["nt"]}</td><td style="color:{wc}">{r["wr"]}%</td>'
        rows += f'<td>{r["w"]}</td><td>{r["l"]}</td>'
        rows += f'<td style="color:{rc};font-weight:700">{r["tr"]:+.2f}%</td>'
        rows += f'<td>{r["ar"]:+.2f}%</td>'
        rows += f'<td style="color:#00c853">{r["best"]:+.2f}%</td>'
        rows += f'<td style="color:#ff5252">{r["worst"]:+.2f}%</td>'
        rows += f'<td>{r["abh"]}</td></tr>\n'

    top5 = ""
    for r in swt[:5]:
        top5 += f'<div style="background:rgba(0,200,83,0.1);border:1px solid rgba(0,200,83,0.3);border-radius:10px;padding:14px;text-align:center">'
        top5 += f'<div style="font-weight:700;font-size:1.1em">{r["s"]}</div>'
        top5 += f'<div style="font-family:IBM Plex Mono,monospace;font-size:1.4em;font-weight:700;color:#00c853">+{r["tr"]:.1f}%</div>'
        top5 += f'<div style="color:#8899aa;font-size:0.8em">{r["nt"]}t | WR {r["wr"]}%</div></div>\n'

    bot5 = ""
    for r in list(reversed(swt))[:5]:
        bot5 += f'<div style="background:rgba(255,82,82,0.1);border:1px solid rgba(255,82,82,0.3);border-radius:10px;padding:14px;text-align:center">'
        bot5 += f'<div style="font-weight:700;font-size:1.1em">{r["s"]}</div>'
        bot5 += f'<div style="font-family:IBM Plex Mono,monospace;font-size:1.4em;font-weight:700;color:#ff5252">{r["tr"]:.1f}%</div>'
        bot5 += f'<div style="color:#8899aa;font-size:0.8em">{r["nt"]}t | WR {r["wr"]}%</div></div>\n'

    nd = ""
    if snd:
        nd = f'<div style="background:#0f2444;border:1px solid rgba(212,168,67,0.2);border-radius:12px;padding:20px;margin-bottom:20px">'
        nd += f'<h2 style="color:#d4a843;border-bottom:1px solid rgba(212,168,67,0.2);padding-bottom:8px">No Data ({len(snd)})</h2>'
        nd += f'<p style="color:#8899aa;font-size:0.9em">{", ".join(r["s"] for r in snd)}</p></div>'

    rc = "#00c853" if otr > 0 else "#ff5252"
    wrc = "#00c853" if owr >= 50 else "#ff5252"
    avc = "#00c853" if avs > 0 else "#ff5252"

    html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Fractal v3 Backtest</title>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Tajawal',sans-serif;background:#0a1628;color:#e0e6ed;min-height:100vh;padding:20px}}
.c{{max-width:1400px;margin:0 auto}}
.hdr{{text-align:center;padding:30px 20px;background:linear-gradient(135deg,#0f2444,#1a3a5c);border-radius:16px;border:1px solid rgba(212,168,67,0.2);margin-bottom:20px}}
.hdr h1{{font-size:2em;color:#d4a843;margin-bottom:8px;font-weight:800}}
.hdr .sub{{color:#8899aa}} .hdr .ts{{color:#e8c56d;font-size:0.85em;margin-top:8px;font-family:'IBM Plex Mono',monospace}}
.pg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:20px}}
.pc{{background:#0f2444;border:1px solid rgba(212,168,67,0.2);border-radius:12px;padding:16px;text-align:center}}
.pc .lb{{color:#8899aa;font-size:0.8em;margin-bottom:6px}}
.pc .vl{{font-size:1.8em;font-weight:800;font-family:'IBM Plex Mono',monospace}}
.sec{{background:#0f2444;border:1px solid rgba(212,168,67,0.2);border-radius:12px;padding:20px;margin-bottom:20px}}
.sec h2{{color:#d4a843;font-size:1.2em;margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid rgba(212,168,67,0.2)}}
.tg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}}
.tw{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:0.85em}}
th{{background:#1a3a5c;color:#d4a843;padding:10px 8px;text-align:center;position:sticky;top:0;font-weight:600}}
td{{padding:8px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.05);font-family:'IBM Plex Mono',monospace;font-size:0.9em}}
tr:hover{{background:rgba(212,168,67,0.05)}}
.ft{{text-align:center;padding:16px;color:#8899aa;font-size:0.8em}}
@media(max-width:768px){{.hdr h1{{font-size:1.4em}}.pg{{grid-template-columns:repeat(2,1fr)}}.pc .vl{{font-size:1.3em}}table{{font-size:0.75em}}td,th{{padding:6px 4px}}}}
</style></head>
<body><div class="c">
<div class="hdr"><h1>Fractal v3 Backtest</h1>
<div class="sub">HL/LL &#x0634;&#x0631;&#x0627;&#x0621; | HH/LH &#x0628;&#x064A;&#x0639; | Pivot {PIVOT_PERIOD} | 30m | Fee {BROKER_FEE_PCT}%</div>
<div class="ts">{now} | {elapsed:.0f}s | {len(swt)} stocks</div></div>

<div class="pg">
<div class="pc"><div class="lb">&#x0625;&#x062C;&#x0645;&#x0627;&#x0644;&#x064A; &#x0627;&#x0644;&#x0639;&#x0627;&#x0626;&#x062F;</div><div class="vl" style="color:{rc}">{otr:+.1f}%</div></div>
<div class="pc"><div class="lb">&#x0646;&#x0633;&#x0628;&#x0629; &#x0627;&#x0644;&#x0646;&#x062C;&#x0627;&#x062D;</div><div class="vl" style="color:{wrc}">{owr}%</div></div>
<div class="pc"><div class="lb">&#x0635;&#x0641;&#x0642;&#x0627;&#x062A;</div><div class="vl" style="color:#d4a843">{at}</div></div>
<div class="pc"><div class="lb">&#x0631;&#x0627;&#x0628;&#x062D;&#x0629;</div><div class="vl" style="color:#00c853">{ps}</div></div>
<div class="pc"><div class="lb">&#x062E;&#x0627;&#x0633;&#x0631;&#x0629;</div><div class="vl" style="color:#ff5252">{ls}</div></div>
<div class="pc"><div class="lb">&#x0645;&#x062A;&#x0648;&#x0633;&#x0637;/&#x0633;&#x0647;&#x0645;</div><div class="vl" style="color:{avc}">{avs:+.2f}%</div></div>
</div>
<div class="sec"><h2>&#x1F3C6; &#x0623;&#x0641;&#x0636;&#x0644; 5</h2><div class="tg">{top5}</div></div>
<div class="sec"><h2>&#x26A0; &#x0623;&#x0633;&#x0648;&#x0623; 5</h2><div class="tg">{bot5}</div></div>
<div class="sec"><h2>&#x0627;&#x0644;&#x0646;&#x062A;&#x0627;&#x0626;&#x062C; ({len(swt)})</h2><div class="tw"><table>
<thead><tr><th>#</th><th>&#x0633;&#x0647;&#x0645;</th><th>&#x0635;&#x0641;&#x0642;&#x0627;&#x062A;</th><th>&#x0646;&#x062C;&#x0627;&#x062D;</th><th>&#x0631;&#x0627;&#x0628;&#x062D;</th><th>&#x062E;&#x0627;&#x0633;&#x0631;</th><th>&#x0625;&#x062C;&#x0645;&#x0627;&#x0644;&#x064A;</th><th>&#x0645;&#x062A;&#x0648;&#x0633;&#x0637;</th><th>&#x0623;&#x0641;&#x0636;&#x0644;</th><th>&#x0623;&#x0633;&#x0648;&#x0623;</th><th>&#x0634;&#x0645;&#x0648;&#x0639;</th></tr></thead>
<tbody>{rows}</tbody></table></div></div>
{nd}
<div class="ft">Fractal v3 Backtest | Master AI v9.0.0 | 300 bars 30m per stock</div>
</div></body></html>"""
    return html


def main():
    t0 = time.time()
    print("=" * 60)
    print("  Fractal v3 Backtest")
    print(f"  Pivot={PIVOT_PERIOD} | 30m | Fee={BROKER_FEE_PCT}%")
    print("=" * 60)

    # Bridge check
    print("\n[1] Bridge check...")
    try:
        with urllib.request.urlopen(f"{BRIDGE_URL}/analysis?symbol=NBK&interval=30", timeout=10) as r:
            if r.status == 200: print("  OK")
    except Exception as e:
        print(f"  FAIL: {e}"); sys.exit(1)

    # Symbols
    print("\n[2] Symbols...")
    symbols = get_radar_symbols()
    if not symbols: print("  NONE"); sys.exit(1)

    # Backtest
    print(f"\n[3] Backtest {len(symbols)} stocks...")
    results = []
    for i, sym in enumerate(symbols):
        p = f"[{i+1}/{len(symbols)}]"
        bars = fetch_bars(sym)
        if not bars or len(bars) < PIVOT_PERIOD * 3:
            c = len(bars) if bars else 0
            print(f"  {p} {sym}: X ({c})")
            results.append(analyze(sym, []))
            continue
        ph, pl = detect_pivots(bars, PIVOT_PERIOD)
        if len(ph) < 2 and len(pl) < 2:
            print(f"  {p} {sym}: no pivots")
            results.append(analyze(sym, []))
            continue
        sigs = classify(ph, pl)
        trades = simulate(sigs, bars, BROKER_FEE_PCT)
        r = analyze(sym, trades)
        results.append(r)
        ret = f"{r['tr']:+.1f}%" if trades else "-"
        wr = f"WR{r['wr']}%" if trades else ""
        print(f"  {p} {sym}: {len(bars)}b {len(trades)}t {ret} {wr}")
        time.sleep(0.3)

    # Report
    elapsed = time.time() - t0
    print(f"\n[4] Report...")
    html = gen_report(results, elapsed)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Saved: {REPORT_PATH}")

    # Summary
    swt = [r for r in results if r["nt"] > 0]
    at = sum(r["nt"] for r in results)
    aw = sum(r["w"] for r in results)
    tr = sum(r["tr"] for r in results)

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"  Stocks: {len(swt)}/{len(results)}")
    print(f"  Trades: {at} | Win: {aw} | Loss: {at-aw}")
    print(f"  Win Rate: {round(aw/at*100,1) if at else 0}%")
    print(f"  Total Return: {tr:+.1f}%")
    print(f"  Time: {elapsed:.0f}s")
    print(f"{'='*60}")

    swt.sort(key=lambda x: x["tr"], reverse=True)
    print(f"\n  TOP 5:")
    for r in swt[:5]:
        print(f"    {r['s']:12s} {r['tr']:+8.2f}% | {r['nt']}t WR{r['wr']}%")
    print(f"\n  BOTTOM 5:")
    for r in list(reversed(swt))[:5]:
        print(f"    {r['s']:12s} {r['tr']:+8.2f}% | {r['nt']}t WR{r['wr']}%")


if __name__ == "__main__":
    main()
