# PHASE 2 — SECTION E: The decisions page and its dead feedback loop

- Date: 2026-08-15
- Plan by: claude.ai | Executors: **Claude Code** (E-1, E-2, E-4) and
  **claude.ai** (E-3, E-5)
- Read first: `_tools/PHASE2_SECTION_C.md`, `_tools/PHASE2_SECTION_D.md`,
  `_tools/mixed_clock_census.md`, `_tools/FIX_AUTO_LOG_DECISIONS.md`
- Rules: minimal, backward-compatible, do not break existing endpoints.

## What was found

`decisions.html` -> `GET /api/decisions-now` (golden_engine), refresh 120s.
The endpoint is alive and partly modernised: `total_scanned = 132` (corrected
universe), and `max_position_state` / `max_position_as_of` already carry the
Section C contract.

The page **does** have a feedback loop, and it is well designed:

- `decision_audit` — every ENTER decision logged at emission
- `signal_reviews` — graded next session: next-day OHLCV, `max_favorable`,
  `max_adverse`, `hit_target_1`, `hit_stop`, `error_type`, `lesson_ar`

Measured state of that loop, 2026-08-15:

```
signal_reviews — 23 rows, entire lifetime
  no_data : 18   (78%)
  partial :  4
  ongoing :  1
  hit_target_1 : 0        hit_stop : 0

decision_audit
  pending : 23 · partial : 4 · ongoing : 1 · resolved : 0

last review_date : 2026-04-23     today : 2026-08-15   (114 days)
```

Today's three ENTER decisions (ABAR 90.2, KINV 86.1, JTC 83.4 — all
`data_freshness=stale_1d`) are logged `pending` and nothing will grade them.

**Read this correctly:** `no_data` is the loop behaving *well* — it refused to
invent an outcome it could not measure. This table is the one place in the
system that never converted absence into a value. The failure is that nobody
opened it, and the page kept emitting confidence as if the loop were closed.

---

## E-1 — Revive the review engine on Yahoo  (Claude Code) — highest value

**Why first:** 18 of 23 reviews are `no_data` because the reviewer could not
fetch next-session prices. That is the same source failure Section C already
solved. `signal_reviews` needs exactly `next_day_open/high/low/close/volume`,
and Yahoo (`.KW`) now covers 131/132 symbols. The loop can work for the first
time in its life.

Note the sequencing argument: **C-27 re-measures the past. E-1 is the only
item that makes the future measurable.** Without it, C-27 finishes and the
system goes right back to emitting ungraded decisions.

**Change:**
1. Point the reviewer's price fetch at `price_source.get_price` / the daily
   bars from Yahoo. Do not reintroduce a direct Bridge dependency — the
   Bridge is manual-only by standing decision.
2. Restore the scheduler entry that runs the review (per
   `FIX_AUTO_LOG_DECISIONS.md` the intended slot is ~14:00 local, after the
   close job). Confirm why it stopped after 2026-04-23 before re-enabling —
   if it was silently swallowed, that is a separate bug (rule 11).
3. Keep `no_data` as a first-class result. Never let a missing bar become a
   0% return. When a symbol genuinely has no data, `no_data` plus a reason is
   the correct output.
4. Backfill the 23 pending/partial rows where Yahoo history covers the dates
   (Mar–Apr 2026 and today's three). Mark backfilled rows so C-27 can tell
   them from live-graded ones.
5. Add a liveness signal: `last_review_date` and `sessions_since_last_review`
   on an endpoint. A loop that dies silently for 114 days must not be able to
   do that again.

**Acceptance:**
- `signal_reviews` gains resolved rows (`hit_target_1` / `hit_stop` non-zero
  somewhere), and `no_data` share drops sharply on backfilled dates.
- Today's ABAR/KINV/JTC rows leave `pending` on the next session.
- `sessions_since_last_review` is queryable and currently 0.

---

## E-2 — Three stop levels in one record  (Claude Code) — direct money risk

Observed in the ABAR record from `/api/decisions-now` (price 194.0):

```
stop_loss.stop_price   = 171.295   (-11.7%)   method: support_atr
trade_plan.stop_loss   = 186.591   ( -3.3%)
chosen_plan.stop       = 184.494   ( -4.9%)   source: strategy
```

`chosen_plan` resolves the choice, but all three travel in the same payload
and `decision_audit.stop_price` recorded 184.494 for today's row — so the
audit trail follows `chosen_plan`. What is **not** verified is which one
`decisions.html` renders.

This is not an aesthetic problem. The user moves stops by hand at the broker,
and the system's stated job is to *advise* the stop level. The gap between
-3.3% and -11.7% on a 142,705 KWD book is real money.

**Change:**
1. Determine which value the page renders today. Report it before changing.
2. One authoritative stop per record: `chosen_plan.stop`. Keep the other two
   only as clearly-labelled diagnostics (`stop_candidates`), never at a key a
   renderer would grab by default.
3. Emit `stop_source` naming the method that won, so the advice can be argued
   with.

**Acceptance:** the page, `decision_audit.stop_price`, and `chosen_plan` show
the same number for the same symbol, and the record says why.

## E-4 — `decision_time` has no declared clock  (Claude Code)

`decision_audit.decision_time` and `signal_reviews.review_date` carry no
timezone, and C-27 will read both. After D-11 this is a known trap, not a new
discovery. Prove each column's clock, convert writers to UTC, and add both to
`mixed_clock_census.md` with the proven value. Audit every comparator first —
the census rule requires both write paths audited together.

---

## E-3 — Confidence is unearned until the loop produces resolved outcomes  (claude.ai)

The page shows `smart_decision: ENTER` at 90.2% confidence. That figure, and
`win_rate` / `pattern_score` / `profit_factor` / `ev` / `baseline_wr`, derive
from Brain patterns and strategy backtests measured with the evaluation
windows C-27 exists to correct. The same basis, with the same words, is
already quoted on the wire as the reason the whitelist is suspended:

`whitelist_suspended_reason: "C-27: hit-rate basis was measured with broken
evaluation windows"`

One basis is currently treated two ways: the whitelist is suspended, and the
page that says ENTER NOW is not.

**Change (frontend):**
1. Hide every hit/miss-derived figure behind one collapsed block with a single
   banner carrying **the identical suspension string**, so both lift from one
   place when C-27 lands.
2. Keep the facts visible: price, change, matched conditions / live atoms,
   support/resistance, ATR, liquidity, sector, position ceiling, timestamps.
3. Replace the confidence badge with the loop's real record until it has one:
   graded decisions, resolved count, `no_data` share, sessions since last
   review. If the honest answer is "0 resolved outcomes", show that.
4. Do **not** take the page down. The raw scan of 132 symbols has value, and
   removing it pushes the user toward less disciplined sources.

## E-5 — The page is blind to data state  (claude.ai)

`decisions.html` contains no reference to any state field — no `stale`, no
`as_of`, no `price_state` — and refreshes every 120s, which reads as live.
Meanwhile the payload carries `data_freshness: "stale_1d"` on every row and
today's decisions were emitted on it.

Also: `data_freshness` speaks in days (`stale_1d`), a **fourth dialect**
alongside `price_state`, session-based `data_state`, and the old
`freshness/is_stale` pair. And `generated_at` is naive.

**Change:** render the state banner used on `swing.html`, map `data_freshness`
onto the Section C session vocabulary (keeping the old key as an alias), and
show `generated_at` with its clock once E-4 declares it.

---

## Order of execution

1. **E-2** — smallest, and the only item that is direct money risk today.
2. **E-1** — revive the loop. Everything downstream depends on it.
3. **E-4** — clocks, before C-27 reads these tables.
4. **E-3 / E-5** — frontend, claude.ai, can run in parallel with the above.

C-27 stays gated on its own two preconditions (Section D tail), not on E.
But note E-1 is what keeps C-27 from being a one-time exercise.

## Out of scope

- Rewriting `golden_engine` scoring — that is C-27's job, not this section's.
- The ~36 remaining price paths.
- `positions.html` / `radar.html` (Section D tail, claude.ai).

## Verification (Claude Code)

```
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
python3 _tools/db_sanity.py
git add <explicit paths only — never -A in this repo>
git commit -m "Phase 2 Section E: revive decision review loop, single stop, clocks"
bash _tools/restart_master_ai.sh
```

Then confirm on the wire: `sessions_since_last_review = 0`; today's three
decisions no longer `pending` after the next session; one stop value agreeing
across page, `chosen_plan`, and `decision_audit`.

## Report back

Files changed, validation output, what still fails, and — specifically —
**why the reviewer stopped on 2026-04-23**. That answer matters more than the
fix: a loop that died silently for 114 days is a monitoring failure, and if
the cause is still present it will kill the next loop too.
