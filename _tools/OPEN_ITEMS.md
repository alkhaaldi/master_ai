# OPEN ITEMS — everything still outstanding, in order

- Written 2026-08-16 by claude.ai, after Sections C–G.
- This file is the single list. If it is not here, it is done or it is parked.
- Rules unchanged: minimal, backward-compatible, do not break endpoints,
  **BUY_NOW stays shadowed** until the window closes (~2026-08-30).

---

## NOW — small, and blocking nothing else

**1. Commit the two dashboard pages** (claude.ai edited them, not committed)
```
www/trading/positions.html   data-state banner, pnl_valid gating, capital deployment
www/trading/radar.html       data-state banner, source_state precedence
```
Explicit paths, never `-A`.

**2. `/dashboard/radar` is still speaking April**
Returns `degraded: true`, `data_source: "cache"`, and **no** `source_state`,
`source`, or `source_reason` — while `/dashboard/swing` has all three.
Either bring it onto the contract, or, if the D-5 counter (due 22 Aug) shows it
has no consumer, say so **in the payload**. A live endpoint answering in a dead
vocabulary is how April's numbers survived.

**3. `adx or 0` in `golden_engine`** — found while verifying the atom fix.
A missing ADX becomes 0, which is `< 20`, which mints the atom `adx_lt_20`
("weak trend") out of nothing. Same family as `rsi or 99`, same fix: absence
produces no atom.

---

## NEXT — the two-source leftovers (Section G tail)

**4. Two writers on `stock_radar_daily`**
`refresh_daily_snapshot` (bridge-era) and `backfill_daily_bars` (Yahoo) both
write the same table, and only one writes `indicator_source` / `bars_used` /
`coverage_pct`. All 132 rows are currently `local`, so the damage is latent —
but this is exactly the shape that produced the two clocks in `decision_time`.
Retire the bridge-era writer or make it write the same columns.

**4b. Two clocks in `captured_at` — found 2026-08-17 while measuring the feed delay**
The same column is stamped with two different meanings, and nothing in the
value says which you are holding:

```
_tools/intraday_refresh.py:91   captured_at = the SOURCE's regularMarketTime
stock_radar.py:1519             captured_at = datetime.utcnow()   ← our clock
```

They differ by the feed delay — measured 15 minutes, floor, never less. So a
`MAX(captured_at)` across mixed rows silently prefers the our-clock rows, which
always look ~15 minutes fresher than they are.

Latent today, not harmless: 131 of 132 rows are source-clock and one April row
is our-clock, so `MAX` lands on the right meaning **by weight of rows, not by
construction**. One post-close `refresh_daily_snapshot` run flips that.

Affected paths:
- `/dashboard/swing` → `as_of`, and now `as_of_kind: "source_market_time"` and
  `as_of_age_minutes` — all three built on `MAX(captured_at)` in
  `dashboard_api.py:2115`. `as_of_kind` currently asserts a label this column
  cannot guarantee.
- `price_source._from_db:381` → `as_of` for every DB-sourced quote
- `signal_engine.py:200,582` → `as_of` on signals
- `dashboard_api.py:586` → `_session_freshness(captured_at, ...)`, i.e. the
  five-state banner on every page reading it

Fix: `stock_radar.py` stamps from the source like `intraday_refresh` does, or
the column splits into two honestly-named ones. Same family as item 4 and the
same shape as the two clocks in `decision_time` — a name shared by two
variables is how April's numbers survived.

**4c. `yahoo_gate`'s state is per-process — found 2026-08-17 routing both paths through it**
The gate's throttle, circuit and counters live in module globals
(`_lock`, `_last_request`, `_state`). Nothing is shared or persisted, so each
process gets its own private door and believes it is the only caller.

Two consequences, both live now:

1. **`quick_check`'s circuit check is vacuous.** It prints
   `yahoo circuit — closed, 0 requests, 0 rate-limited` because it just
   imported the module in its own fresh process. It will read zero for ever,
   whatever the server or cron is doing. Verified: a single process that
   calls `get_quote` sees `requests: 0 → 1`, and `quick_check` still says 0.
   A green check that cannot go red is not a check.
2. **Cron runs do not space against each other.** `*/15` (234s, 117 symbols)
   and `*/2` (positions) coincide every 30 minutes as separate processes,
   each spacing its own requests 2s apart — so Yahoo can see two interleaved
   streams. Within-run bursts are solved; cross-run overlap is not.

Yahoo's limit is burst-sensitive, not volume-sensitive (G-1: 9 back-to-back
all 429'd, 33 spaced 2s were clean), so two slow streams is a modest risk —
but it is unmeasured, which is the part that matters.

Fix: move the throttle's `_last_request` and the circuit state into
`life.db` (or a lock file) so every caller shares one door, and make
`quick_check` read that shared state instead of its own.

**4d. One telegram destination, not 28 — found 2026-08-17 proving the channel**
`ADMIN_TELEGRAM_ID or "669769765"` appears in **28 places, 18 of them in
`server.py`**. The literal matches the configured id today, so it is redundant
rather than wrong — and that is exactly why it is dangerous. Change the id in
`.env` tomorrow and eighteen call sites keep sending to the old chat, in
silence, with every one of them reporting success.

It survived for months because the falsy-defaults sentinel only looked at
numbers. Widened on 2026-08-17 to count `or "<literal>"`; the first
measurement is 9 in decision paths and 81 elsewhere, 42 of the 81 in
`server.py`. Baselines declared in `falsy_baseline.json`, ratcheted in
`quick_check`, and the widened sentinel is itself proved in `prove_guards.py`.

Fix: one resolver, as `run_witness.telegram_credentials()` already is for the
credentials, and the 28 sites call it. Scope is wide — 18 edits in server.py
alone — so it is a batch of its own, not a rider on someone else's.

Related, and the one that actually invents a decision rather than a
destination:

```
position_engine.py:176   direction = row["direction"] or "long"
```

A missing trade direction becomes a BUY. Same family as `rsi or 50`: absence
producing a confident reading. Five of the other eight string defaults in
decision paths are display placeholders (`'—'`, `'?'`) that render absence AS
absence, which is correct and should stay.

**4e. `direction` is read three ways — one fixed 2026-08-17, two open**
`position_engine.py:176` invented a default and is fixed: an unrecognised
direction now refuses to compute P&L and logs why, instead of reading as
`long`. The other two readers still disagree with it and with each other:

```
journal_engine.py:211   direction = trade["direction"]
                        if direction == "long": … else: …   -> anything else
                                                              computes a SHORT
journal_engine.py:410   trade.get("direction", "long")      -> the key EXISTS
                                                              with a falsy value,
                                                              so the default never
                                                              fires; falls to SHORT
```

So the same row can produce **+10% in one module and −10% in another**. This
is the `decision_time` two-clock shape applied to the sign of money.

What the schema actually allows, measured rather than assumed:

```
direction TEXT NOT NULL DEFAULT 'long'
  NULL        impossible - the constraint holds
  ''          ACCEPTED, and falsy: this is what `or "long"` fired on
  'lomg'      ACCEPTED, and TRUTHY: it sailed past the default and landed in
              the else branch, so one mistyped letter inverted the P&L sign
```

And `DEFAULT 'long'` is the same defect one layer down: an INSERT that omits
the column gets a BUY, silently, before any code is involved. A CHECK
constraint (`direction IN ('long','short')`) plus dropping the default would
close it at the source — but that is a schema migration on the trades table,
which is its own batch.

Fix: `VALID_DIRECTIONS` already exists in `position_engine`. The two
`journal_engine` sites should use it and refuse the same way. Proved in
`prove_guards.py` for the fixed site: empty and typo both refuse, a stated
long reads −10% and a stated short +10% — the two answers the default used to
choose between without telling anyone.

**4f. `trades.direction` — the default lives in the SCHEMA, before any code runs**
All three code readers were unified on `VALID_DIRECTIONS` on 2026-08-17
(`position_engine.py:176`, `journal_engine.py:211` and `:410`). The remaining
default is one layer below them:

```sql
direction TEXT NOT NULL DEFAULT 'long'
```

An INSERT that omits the column gets a BUY — silently, correctly, before a
single line of Python is involved. And `NOT NULL` is weaker than it looks:
measured on a copy, `''` is accepted (falsy — what `or "long"` used to fire
on) and `'lomg'` is accepted (truthy — it sailed past the default straight
into the short branch, so one mistyped letter inverted the P&L sign).

Fix, as a migration of its own on the trades table:

```sql
CHECK (direction IN ('long','short'))   -- '' and typos rejected at the door
-- and DROP the DEFAULT: an omitted direction should fail the insert, not
-- become a position nobody chose
```

Why it is its own batch: SQLite cannot add a CHECK constraint in place. It
needs the create-new-table / copy / drop / rename dance on `trades` — the
user's money records, 10 rows today but the table every engine writes to.
That wants a backup, a verified row count either side, and a rollback path,
none of which belongs riding on another change.

Until then the code refuses what the schema permits, which holds — but it
holds by three modules agreeing, not by construction.

**4g — MEASURED 2026-08-17. Inventory below; nothing fixed yet.**

AST inventory of `.get(key, <number>)`, classified by what the value becomes.
The first pass counted 699 and the second 180, both of them wrong in the same
direction: they counted the pattern rather than its consequence. A `.get(k,0)`
filling a field of a record that gets appended is one wrong number. A
`.get(k,0)` that becomes an ELEMENT of a scalar sequence is a point on a
curve, and the consumer reads a shape from it.

```
TOTAL 699
  trajectory (this item)  22    decision 12 · elsewhere 10
  row field in a loop     37    decision 22 · elsewhere 15
  plain scalar           640    decision 240 · elsewhere 400
```

**Size verdict: a session, not a section** — for the 22. The 640 plain
scalars are a separate and much larger problem that should not be smuggled in
under this heading.

The 22 are not one family. Reading them:

*Worth acting on (~14).* The richest is VWAP, and it is a decision path with
**three stacked defaults**, the last of which hides the first two:

```
signal_engine.py:1213-16  [b.get("high", b.get("h", 0)) for b in bars]  (+low, close, volume)
signal_engine.py:1539     sig["vwap"] = vwap_data.get("vwap", 0)
signal_engine.py:1542     sig["scalping_vwap_ok"] = ... == "above"   → unknown becomes False
stock_radar.py:785        vwap = ind.get("vwap") or price            → the 0 is RESCUED into the price
```

A missing bar field becomes a price of zero, which drags the VWAP down;
an unavailable VWAP becomes 0; and then `or price` replaces that 0 with
something plausible, so nothing downstream can tell the difference. Note
`_get_vwap_for_symbol` still takes `bridge_data` — the bridge is retired, so
check whether this path computes anything at all before repairing it.

Others in the same tier:
```
trading_brain.py:595-596   weights.get(ind, 1.0)   a missing LEARNED weight becomes FULL weight
confidence_engine.py:72    s.get("score", 0.5)     absence becomes the midpoint of the scale
sr_engine.py:85            x.get("volume", 0)      drags a cluster's average volume down
stock_analyzer.py:400      b.get("volume", 0)      survived my own 2026-08-17 rewrite
journal_engine.py:357      t.get("pnl_fils", 0)    sums P&L; an unrecorded trade counts as break-even
paper_trading.py:156,157,159   the same shape over slippage and commission
equity_tracker.py:120      s.get("drawdown_pct", 0)
```

*Deliberate sentinels, harmless (4).* `brain_backfill.py:155-156, 361-362`
use `max(b.get("high", 0))` and `min(b.get("low", 999999))`. The sentinel is
chosen so it cannot win the comparison. Correct as written, though it depends
on the reader knowing why 999999 is there — worth a comment, not a change.

*Diagnostics, not decisions (4).* `_tools/verify_sunday.py:185-186` and
`health_watchdog.py:147-148`, summing circuit counters.

**On a fourth sentinel family: not yet.** The count that matters is 22, and a
ratchet over all 699 would be a number nobody could act on. A narrow family
over the trajectory shape is defensible — but this classifier needed two
corrections to stop lying, and a sentinel that misclassifies is worse than no
sentinel, which is the lesson of this whole phase. Triage the 22 first, then
add the family with the classifier validated against them as known cases, and
prove it in `prove_guards.py` like the other three.

The original finding, kept for the record:

**The `rsi_traj` shape — fixed in `stock_analyzer` 2026-08-17**
Fixed in `stock_analyzer` on 2026-08-17, not looked for anywhere else:

```python
rsi_traj = [round(b.get("rsi_14", 0), 1) for b in bars[-20:]]
```

Twenty points went to Gemini, and any bar the bridge had not enriched
contributed **0** — a reading that says "maximum oversold" and means "not
measured". A single number carrying an invented value is bad; a *trajectory*
is worse, because the consumer reads a SHAPE out of it. Two unenriched bars
in the middle of a rising RSI look like a crash and a recovery that never
happened, and no scalar check would catch it: every individual value is in
range.

Why it is its own item: the falsy sentinel does not see this. `b.get("rsi_14",
0)` is `dict.get` with a default, not `or 0`, and the widened string family
does not cover it either. So this class is currently unmeasured — we do not
know how many exist.

To audit, in this order:
1. every list comprehension over bars feeding an LLM prompt or a report
2. `.get(key, 0)` and `.get(key, 0.0)` inside any list/series construction
3. anything that then computes a slope, a trend or a "direction" from such a
   series — that is where an invented point becomes an invented conclusion

Known consumers worth checking first: `trading_brain` (report text),
`gemini_scanner`, `brain_analytics`, `confluence_engine`, and any dashboard
card drawing a sparkline. The fix pattern is settled: compute per window and
let a window that cannot answer contribute `None`, as
`stock_analyzer._trail` now does.

Consider extending `falsy_defaults_inventory` with a fourth family —
`.get(k, <number>)` inside a comprehension — once the manual sweep says how
big the problem is.

**4h. Human-entry sweep — 2026-08-17. Everything a person can start.**

Opened because two of these were missed by reading rather than calling:
`analysis.html` answered "Bridge offline" for every symbol with the bridge
already unreachable in code, and `check_symbol` returned
`price 0 · rsi 0 · vwap 0` down a live Telegram command. Both looked fine on
the page and in the source.

Tools, both read-only and re-runnable:
`_tools/inventory_human_paths.py` (static: entry points, and a name-based call
graph to the retired stubs) and `_tools/call_human_paths.py` (calls every
page-reachable GET and asks whether it fails loudly or with zeros).

```
221 routes defined · 44 called from a page · 24 telegram handlers
static graph: 7 entries reach a retired stub, all via one chain
              build_signals -> _get_bridge_data_safe, which returns
              {"bridge_online": false, "bridge_status": "retired"} - loud
called:       loud 5 · ok 18 · suspect 3 · expensive-skipped 1
telegram:     5 read-only radar commands called, all honest
```

**Nothing else fabricates a full zero snapshot.** The two known cases are
fixed. But the sweep found something else.

*The real finding — two endpoints outside the data contract.* Three sibling
endpoints, three different vocabularies for the same fact:

```
/dashboard/signals        131 signals · bridge_online:false · NO data_state,
                          NO source_state, NO as_of
/dashboard/signals-daily  131 signals · identical, same gap
/dashboard/signals-30m      0 signals · layer_state, layer_reason,
                          layer_rebuildable - the full vocabulary
```

The first two serve real data from the local store, so they are not
fabricating. But a reader cannot tell how old it is, where it came from, or
whether the source was reachable — and their only state marker names a
*retired* dependency as though it might return. This is the same gap
`/dashboard/radar` had (item 2), closed there and on `swing`, never closed
here. Fix: give them `source`/`source_state`/`source_delay_minutes`/`as_of`/
`as_of_kind` like `/dashboard/swing`, and drop `bridge_online` or rename it
to say retired.

*Minor, diagnostics only.* Two endpoints invent an average of nothing:
`/api/latency-stats` returns `avg_total_ms: 0` alongside `samples: 0`, and
`/api/intent-analytics` returns `avg_duration_ms: 0` alongside
`today_total: 0`. The count beside it makes the zero readable, so this is
noted rather than urgent — but a mean over no samples is `None`.
`/api/tasks` is clean: its zeros are counts of events that did not happen.

*Also minor.* `tg_radar_last` answers "آخر إشارات الرادار" with signals from
**2026-03-25**. The dates are printed, so it is not hiding anything, but
nothing marks them as five months old.

**Limits of this sweep, stated so the next one knows what was not covered:**
- only routes whose URL appears in `www/**` were called. 177 of 221 routes
  are not page-reachable and were not exercised; some are reachable by a
  human typing a URL, by HA sensors, or by the bot.
- the call graph matches by NAME and caps at depth 8, so it over-reports and
  can still miss a path that goes through a dynamic dispatch.
- `/api/analyze` was skipped deliberately: each call burns a Gemini 2.5 Pro
  request. It was verified by hand earlier the same day.
- the three `tg_radar_*` commands that mutate state (add/remove/toggle) were
  not called.

**4i. THE SECOND CLASS — correct numbers with no context**

The class this whole phase was built to catch is *invented numbers*: `rsi or
50`, `direction or "long"`, a fabricated all-zero snapshot. Every guard we
have looks for a wrong value.

This is the other one, and it is quieter: **numbers that are entirely
correct, served with no way to judge them.** `/dashboard/signals` carried 131
real signals for months with no `data_state`, no `source`, no `as_of`.
Nothing in that payload was wrong. Nothing in it could be checked either.

**Why no existing guard finds it.** The falsy sentinel reads syntax. db_sanity
reads values. quick_check reads endpoints for presence and shape. All three
pass a payload of correct undated numbers, because there is nothing in it to
fail. A value check cannot ask a question about what is *absent from the
frame around* the value.

**The only method that works** is a sweep that calls each endpoint and asks
it directly: *do you declare your age and your source?* Implemented in
`_tools/call_human_paths.py` (the SECOND CLASS section) against
`as_of · as_of_kind · source · source_state · data_state`.

First measurement, 2026-08-17, page-reachable GETs:

```
NO CONTEXT 20 · partial 1 · full 3 · n/a 3
```

- **full 3** — `/dashboard/swing`, `/dashboard/signals`,
  `/dashboard/signals-daily`. The last two joined today; all three now build
  the contract from one place, `dashboard_api._data_contract()`.
- **partial 1** — `/dashboard/radar` has source and data_state but no `as_of`
  or `as_of_kind`. That is item 2, still open, now with a number on it.
- **NO CONTEXT 20** — including `/dashboard/portfolio`, `/dashboard/equity`,
  `/dashboard/journal`, `/dashboard/reviews`, `/dashboard/risk-status`,
  `/api/decisions-now`. Several of these are money surfaces.

**A known false positive, left in rather than tuned away.**
`/dashboard/signals-30m` is listed as NO CONTEXT and is not: it declares
`layer_state` / `layer_reason` / `layer_rebuildable`, which is the right
vocabulary for an offline layer but not the contract's five keys. The
classifier is syntactic and this is its limit. Widening it to accept
`layer_state` would make the tool flatter its author's own earlier work,
which is how a sweep stops being evidence.

**Not a ratchet yet, and deliberately.** Twenty is too many to hold at zero
and too varied to fix in one pass - a diagnostics endpoint and a portfolio
endpoint do not owe the reader the same thing. Triage first: which of the 20
serve numbers a human acts on. Those get the contract; the rest get a written
reason for not having it. Then, and only then, a ratchet at whatever the
number is.

**4j. `name_ar` is asked of a trade record that an opportunity does not have**
Found 2026-08-17 while fixing the swing page's field names. Empty in 18 of 18
opportunities, on every endpoint built by `build_signals`.

```
signal_engine.py:409   "name_ar": (trade or {}).get("name_ar", "")
signal_engine.py:530   "name_ar": trade.get("name_ar", "")
```

An opportunity is not a trade, so `trade` is None and the default wins —
every time, by construction, not by accident. Meanwhile the same repository
already has a working symbol→Arabic-name map, used two files away:

```
dashboard_api.py:451   "name_ar": KSE_STOCKS.get(_sym, str(_sym))
```

Fix: `signal_engine` uses `KSE_STOCKS` for the non-trade case, keeping the
trade's own name when there is one. It is a small change with a wide reach —
`/dashboard/signals`, `/dashboard/signals-daily`, `/dashboard/swing` and
`/api/decisions-now` all read from `build_signals` — so it is recorded rather
than ridden in on a page fix.

**Note this makes an existing fix inert.** swing.html now reads
`o.name || o.name_ar` where it used to read only `o.name`, so the company
name will appear the moment the payload carries one. Until then the fallback
resolves to an empty string and the card shows no name, exactly as before.
The page is ready; the payload is not.

**5. The 30m layer**
`/dashboard/signals-30m` returns nothing. G-1 proved Yahoo **does** serve 30m
for `.KW` (41 bars, tier-1 names 100% populated). So the layer is rebuildable
locally — it is not dead. Until it is rebuilt, `signals.html`'s live tab must
say the intraday layer is offline **and why**, not show daily data under a 30m
label.

**6. F-4 — unify targets, as E-2 unified stops**
`chosen_plan` and `trade_plan` still ship different targets for the same symbol
(`246.186` vs `216.407`, R/R `1.90` vs `2.55`). `chosen_plan` is authoritative;
`trade_plan` moves to a diagnostic `plan_candidates`, with `plan_source`
alongside `stop_source`. The decisions page currently patches over this with a
warning — a frontend plaster on a payload problem.

---

## THEN — the remaining falsy-default family (15 left of 19)

The sentinel (`_tools/falsy_defaults_inventory.py`) holds the line at 211; these
are the ones that still invent a reading. Order by blast radius:

```
golden_engine:572   p_value or 1          "no significance" from "not computed"
golden_engine:124   baseline_win_rate 0.3 a prior invented per call
golden_engine:551-553  target/stop pcts   3 / 5 / -3 — trade geometry from nothing
trading_brain:487-488  base_weight 1.0 / rolling_hit_rate 0.5
risk_engine:475     max_single_position_pct 40
gemini_scanner:376  vol_score 30
```

Same rule every time: **`None` propagates, the consumer decides, and the
decision is visible.** Do not swap one invented number for another.

---

## SCHEDULED — time, not work

| when | what |
|---|---|
| **2026-08-17, 09:00** | Live proof of the forming-bar rule: fetch twice ~2 min apart while the market is open and compare `close`/`volume` on the newest bar. Yesterday's run was a control, not a proof — it was run on a closed market. |
| **2026-08-17 onward** | First live rows in `confidence_census` (not backfill) |
| **2026-08-22** | D-5 counter review — decide `/dashboard/radar`'s fate on evidence |
| **~2026-08-30** | `buy_now_shadow` review: what would have fired, and was it right |

---

## C-27 — still gated, and the gate has grown

Preconditions now, all of them:
1. `confidence_census` maturity (~4 weeks of sessions)
2. Scales declared — done (`_tools/SCALES.md`), keep it current as G-2 adds more
3. Exclusions honoured: `trade_kind='void'`, `entry_basis='consolidated_restart'`,
   `graded_mode` buckets, rows with unknown `entry_date_precision`
4. **StochK patterns are recalibrated from zero, not reweighted.** Bridge vs
   local differ by up to 242% on the same symbol and session (ACICO 2026-08-05:
   26.3 vs 90.0) — the atom `stoch_gt_80` is absent under one and present under
   the other. A weight fitted across that seam is fitted to two different
   variables sharing a name.
5. A run manifest: inputs, exclusions with counts, clock, commit, weights
   before/after. A second run on unchanged inputs must reproduce the first.

---

## claude.ai's remaining work

- **Archived pages**: 15 of 20 pages are April-era with zero state awareness.
  Not worth rewriting — one banner each: "archived page, not on the current
  data contract". Cheap, honest, and stops them serving confident numbers.
- `signals.html` — only after item 5 resolves the 30m question.

## The user's own two

- Rotate the `rpi_backup` password (steps in `_tools/NAS_BACKUP_SETUP.md`)
- Tunnel exposure — **parked by his decision**, not forgotten. Anyone with the
  hostname can still read positions, P&L, and capital. `/ssh/run` and
  `/system/context` are key-protected; the dashboards are not.

---

## HANDOFF — 2026-08-17, for the next Claude Code session

The previous session hit its context limit mid-work. Everything below is
verified on the wire, not taken from a report.

**State as of 2026-08-17 ~09:45 Kuwait, market open:**

```
source=yahoo · source_state=ok · data_state=live · as_of works (age ~15 min)
132 rows in stock_radar_daily, liquidity stats and G-2 evidence intact
buy_now_shadow: 5 rows, acted=0, day 2 of 14
falsy sentinel: 210 / 228 (baseline held)
quick_check 20/20 · smoke 4/4 · db_sanity 6/9 (the three known radar ones)
```

**Done since OPEN_ITEMS was written:** all of NOW, all of NEXT, plus the
forming-bar proof (4/4, proven by the timestamp advancing, not by price),
`as_of` on the swing payload, `trade_plan.rr_ratio` removed, and the probe now
reads the symbol map instead of a hand-written list.

### Decision taken — implement this

**Poll open positions every 2 minutes; leave the 117-symbol universe at 15.**
Cost measured: +120 requests per session, +6%. The throttle handles it, and
the positions cycle finishes in ~2 seconds so it never collides with the
234-second full scan.

But implement it with the caveat below, because the caveat matters more than
the polling.

### The caveat, and it is the real work

**Yahoo's feed is delayed ~15 minutes. That is a hard floor.** Faster polling
reduces *our* staleness, not the *source's*. So after this change the worst
case is still ~17 minutes old, not 2.

Which means `data_state: "live"` is currently making a claim the feed cannot
support. That is the same defect this whole phase removed, one level up: the
label is more confident than the measurement behind it.

**Required alongside the polling change:**
1. Add `source_delay_minutes: 15` to the payload — a declared property of the
   source, next to `source` and `source_state`.
2. `as_of` must say what it stamps: the bar time, or our fetch time. Right now
   a reader cannot tell, and they differ by the feed delay.
3. The pages should read "live (15-min delayed feed)" rather than "live".
   The user trades a market where that gap is real money.

Do not skip 1–3 and ship only the polling. Faster wrong-labelling is worse
than slower honest labelling.

### Still open

- Section THEN: the 15 remaining non-zero falsy defaults
  (`p_value or 1`, `target_1_pct or 3`, `baseline_win_rate or 0.3`,
  `base_weight or 1.0`, `max_single_position_pct or 40`, `vol_score or 30`)
- The 30m layer: `layer_state: offline`, `layer_rebuildable: true`.
  G-1 proved Yahoo serves 30m for `.KW` — it is unbuilt, not dead.
- Shadow review ~Aug 30 · C-27 still gated on census maturity

### Two things for the user, not for Claude Code

- Rotate the `rpi_backup` password (`_tools/NAS_BACKUP_SETUP.md`)
- Tunnel exposure — parked by his decision, not forgotten
