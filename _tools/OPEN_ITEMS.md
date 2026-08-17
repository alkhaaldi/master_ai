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
