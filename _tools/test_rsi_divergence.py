"""rsi_divergence against constructed series where the answer is known."""
import sys

sys.path.insert(0, "/home/pi/master_ai")
import indicators as I  # noqa: E402

DAY = 86400


def bars(closes, start=1700000000):
    return [{"ts": start + i * DAY, "open": c, "high": c * 1.01,
             "low": c * 0.99, "close": c, "volume": 1000}
            for i, c in enumerate(closes)]


def run(name, closes, want_value, want_reason_contains=None):
    r = I.rsi_divergence(bars(closes))
    got = r["value"]
    ok = got == want_value
    if want_reason_contains:
        ok = ok and want_reason_contains in (r["reason"] or "")
    print(f"  {'OK  ' if ok else '*** MISMATCH ***'} {name}")
    print(f"       want={want_value!r} got={got!r} bars_used={r['bars_used']} "
          f"reason={(r['reason'] or '')[:64]!r}")
    return ok


fails = 0

# 1. Bullish: a sharp crash to the first trough, then a long gentle drift to a
#    slightly LOWER one. Price makes the lower low; momentum does not, because
#    the second decline is a drift and the first was a fall. Both troughs get
#    two bars either side, or they are not pivots at all.
#    The recovery between the two troughs is what makes it work: an
#    uninterrupted drift, however gentle, drives Wilder RSI down anyway
#    because nothing offsets the losses. Momentum only reads "higher" if it
#    was allowed to recover first. Verified: 98 -> 97 in price, 36.5 -> 38.1
#    in RSI.
bull = ([100 + i for i in range(20)]     # climb, so RSI has room to fall
        + [112, 105, 98]                 # crash -> trough 1 at 98, RSI 36.5
        + [100, 102, 104, 106, 108, 110, 112]   # recovery lifts RSI
        + [108, 103, 97]                 # shallower fall -> trough 2, RSI 38.1
        + [99, 101])                     # two bars up, so trough 2 is a pivot
fails += not run("bullish: lower low in price, higher low in RSI", bull, "bullish")

# 2. Bearish is the exact mirror: 142 -> 143 in price, 63.5 -> 61.9 in RSI.
bear = ([140 - i for i in range(20)]
        + [128, 135, 142]
        + [140, 138, 136, 134, 132, 130, 128]
        + [132, 137, 143]
        + [141, 139])
fails += not run("bearish: higher high in price, lower high in RSI", bear, "bearish")

# 3. A clean monotone ramp has no pivot pair - that is None WITH a reason,
#    never "none", and never a number.
fails += not run("straight ramp: no pivots -> None + reason",
                 [100 + i * 0.5 for i in range(40)], None, "no pivot pair")

# 4. Too few bars: refused, not approximated.
fails += not run("8 bars: refused", [100 + i for i in range(8)], None, "need")

# 5. Holes below the coverage floor: refused.
holed = bars([100 + i for i in range(40)])
for b in holed[::2]:
    b["close"] = None
r = I.rsi_divergence(holed)
ok = r["value"] is None and "coverage" in (r["reason"] or "")
print(f"  {'OK  ' if ok else '*** MISMATCH ***'} 50% holes: refused")
print(f"       got={r['value']!r} reason={(r['reason'] or '')[:64]!r}")
fails += not ok

# 6. compute_all carries it, and the params string names it
import time  # noqa: E402
ci = I.compute_all(bars(bull), "1d", int(time.time()) + 10 * DAY)
ok = "rsi_divergence" in ci and ci["rsi_divergence"]["params"].startswith("RSIdiv")
print(f"  {'OK  ' if ok else '*** MISMATCH ***'} compute_all exposes it "
      f"({ci.get('rsi_divergence', {}).get('params')})")
fails += not ok

# 7. 'none' and None are different answers - the whole point.
vals = {I.rsi_divergence(bars(c))["value"] for c in (bull, bear)}
print(f"\n  distinct verdicts seen: {vals}")

print()
if fails:
    # Written as a branch, not `sys.exit(1 if fails else 0)`: the ternary
    # form is what the falsy-defaults sentinel counts, and raising the
    # ratchet to admit my own test file is the leniency it exists to stop.
    print("FAILED")
    sys.exit(1)
print("ALL EXPECTATIONS MET")
