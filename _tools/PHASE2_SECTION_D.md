# PHASE 2 — SECTION D: Enforce the price contract at the endpoint layer

- Date: 2026-08-15
- Plan by: claude.ai | Executor: **Claude Code (RPi)**
- Read first: `_tools/PHASE2_SECTION_C.md`, `_tools/mixed_clock_census.md`
- Rules: minimal, backward-compatible, do NOT break existing endpoints.

## Why this section exists

Section C built one price contract (`price_source.get_price/get_quote` —
always returns price + as_of + state, never a bare number). The contract was
built but **never enforced at the endpoint layer**. A live probe on
2026-08-15 found four different dialects for the same concept, all serving
traffic right now:

| endpoint | fields it emits |
|---|---|
| `/dashboard/portfolio` | `quote_as_of, quote_state, quote_source, quote_stale` — **no `pnl_valid`** |
| `/dashboard/radar` -> `journal_open` | `price_as_of, price_source, price_state, price_age_days, price_captured_mid_session, pnl_valid, pnl_invalid_reason` |
| `/dashboard/swing` -> `active_positions` | `price_state, last_known_price` — no `as_of` |
| `/dashboard/signals-daily` -> `open_positions` | `state, price_state, price_as_of` |

Consequence: `positions.html` reads `/dashboard/portfolio`, which cannot tell
it whether a P&L number is trustworthy. The page therefore **cannot be fixed
from the frontend alone** — that is the blocker this section removes.

Note: `/dashboard/positions` does not exist (404). The portfolio endpoint is
the real one. Do not create `/dashboard/positions`.

---

## D-1 — Unify `/dashboard/portfolio` onto the canonical contract

**Problem:** `open_positions[]` uses `quote_*` naming and omits `pnl_valid`.

**Canonical field names** (already used by `journal_open` in `/dashboard/radar`
— treat those as the reference implementation, do not invent new ones):

```
price_as_of, price_source, price_state, price_age_days,
price_captured_mid_session, pnl_valid, pnl_invalid_reason
```

**Change:**
1. In the portfolio builder (`dashboard_api.py`), route every position price
   through `price_source.get_quote()` — the same call `journal_open` uses.
   Do not compute price inline.
2. Emit the canonical fields above on each item of `open_positions[]`.
3. **Keep the old keys as aliases** (`quote_as_of = price_as_of`,
   `quote_state = price_state`, `quote_source = price_source`,
   `quote_stale = (price_state != 'live')`) so nothing that reads them
   breaks. Mark them deprecated in a comment with this file's name.
4. `closed_trades[]` needs no price fields — it settles on `exit_price`.
   Leave it alone.

**Acceptance:**
- `GET /dashboard/portfolio` returns both key sets on every open position.
- For the same symbol, `/dashboard/portfolio` and `/dashboard/radar` report
  an identical `price_state` and `price_as_of`. If they differ, one of them
  is not using `get_quote()` — find it before moving on.

---

## D-2 — A missing stop must never be read as zero risk

**Problem A — missing stop reads as zero risk.** Observed 2026-08-15 17:5x,
with trade id=9 (EQUIPMENT, 150,000 @ 294) carrying `stop_loss = null`:

```
portfolio_heat_pct = 0.0   (max_heat_pct = 6.0)
can_open_new       = true
```

The heat calculation finds no stop, contributes 0, and the risk engine
concludes there is no risk in the book. Section C's disease — absence
converted into a reassuring value — except it sits in a **decision engine**,
not a display, so its blast radius is wider than any dashboard bug.

**Problem B — `portfolio_heat_pct` is off by 1000x (units).** Observed
2026-08-15 19:0x, with trade id=10 (EQUIPMENT, 637,076 @ 224, stop 214):

```
portfolio_heat_pct = 5265.1   (max_heat_pct = 6.0)
can_open_new       = false
```

Hand-check: risk/share = 10 fils; 10 x 637,076 = 6,370,760 fils = 6,370.76
KWD; against capital 121,000 KWD that is **5.27%** — just under the 6% cap.
The emitted 5265.1 is `risk_in_fils / capital_in_kwd * 100`: the numerator is
fils, the denominator KWD. Confirm: 6,370,760 / 121,000 = 5265.1.

This means the gate is currently **right by accident**. Any position with a
stop produces a number ~1000x too large, so the engine blocks everything the
moment a stop exists, and allowed everything while stops were missing. Both
behaviours were wrong; only one looked wrong.

**Change:**
1. In the heat/risk calculation, a position with no `stop_loss` must NOT
   contribute 0. Contribute a worst-case figure (full position value at risk,
   or the configured max-loss assumption) AND set a flag.
2. Add to the `/dashboard/risk-status` payload:
   - `heat_complete` (bool) — false when any open position lacks a stop
   - `positions_without_stop` (int)
   - `heat_note` (str) — why the number is incomplete
3. `can_open_new` must be `false` while `heat_complete` is false, unless the
   user explicitly overrides. A slot count is not a risk assessment.

**Acceptance:**
- With trade id=9 stopless, `portfolio_heat_pct` is no longer 0.0 and
  `heat_complete = false`.
- Setting a stop on id=9 flips `heat_complete` to true and lowers heat.
- No silent path: if heat cannot be computed, `heat_note` says so.

---

## D-3 — `entry_date` currently records when the row was typed, not when the trade happened

**Problem:** The user buys at the broker first and logs the trade later.
Trade id=9 carries `entry_date = 2026-08-15`; the actual purchase was roughly
three months earlier, at the same 294 price. So the row claims a same-day
-24% move that in reality unfolded over a quarter.

This is not one bad row. Every backdated manual entry inherits it, and
`entry_date` is the anchor for:
- `days_held`
- **C-27 hit/miss re-scoring and the weight re-derivation that follows it**

C-27 is about to re-measure everything with corrected windows. If the window
start is the typing date, C-27 replaces one broken ruler with another.

**Change:**
1. `entry_date` = date of the actual trade. `created_at` = row creation.
   They are already separate columns — enforce the distinction in every
   write path, and stop defaulting `entry_date` to today.
2. `ALTER TABLE`: add `entry_date_precision TEXT` — `'exact' | 'approx'`.
   Backfilled trades where the user cannot recall the day are stored as
   `approx`, never as a confident date. Same principle as `price_state`.
3. Any consumer computing a holding period or a scoring window must check
   `entry_date_precision` and degrade rather than assume.
4. Fix trade id=9: set `entry_date` to the real purchase date and
   `entry_date_precision` accordingly.
   **The exact date is still pending from the user — do not guess it.**
   Leave id=9 untouched until it is supplied.

**Acceptance:**
- New manual entries require an explicit trade date.
- `db_sanity.py` flags any open trade whose `entry_date == created_at::date`
  as suspect, so this cannot silently recur.

---

## D-4 — Kill the `data_age_hours = 999` sentinel in `/dashboard/radar`

**Problem:** Two endpoints, same source data (2026-08-13), same moment,
opposite verdicts:

```
/dashboard/swing : data_state = "normal", data_sessions_old = 0
/dashboard/radar : is_stale = true, freshness = "stale",
                   data_age_hours = 999
```

The true gap is about 60 hours. `999` is a sentinel standing in for "could
not compute" and being read downstream as a real age. `radar_daily_context`
also still speaks the old vocabulary (`data_age_hours`, `is_stale`,
`freshness`, `market_was_open`) instead of the session-based states from
Section C.

**Change:**
1. Remove the `999` fallback. If age cannot be computed, emit `null` plus a
   `reason` — never a number.
2. Migrate `radar_daily_context` items to the Section C state vocabulary
   (session-aged), keeping the old keys as aliases for one release.
3. Reconcile with `/dashboard/swing` so the same data cannot yield two
   verdicts. Swing's session-based answer is the correct one.

## D-5 — `/dashboard/radar` may have no consumer

`radar.html` fetches `/dashboard/signals-daily` and `/dashboard/swing`. No
page found fetching `/dashboard/radar`.

**Do not delete it.** Add a request counter or a log line, run for a week,
and report. If it is genuinely dead it is carrying stale-data logic that
nobody validates — which is how April's frozen numbers survived.

---

## D-6 — Whitelist is suspended but still shipping

`/dashboard/signals-daily` still returns `whitelist` with 10 entries, and
`flags.whitelist_mode` exists in the payload.

**Change:** verify the actual value of `flags.whitelist_mode`. If the
whitelist is suspended (it is — its evaluator was broken), the endpoint must
either omit the array or return it empty with a `whitelist_suspended_reason`.
A populated list on the wire will be treated as authoritative by the next
consumer that finds it.

---

## Out of scope for Section D

- The ~36 remaining price paths not yet migrated to `get_price` (separate).
- C-27 hit/miss re-scoring — **blocked on D-3 landing first**, otherwise the
  window start dates are still wrong.
- `positions.html` and `radar.html` frontends — claude.ai handles those once
  D-1 ships. Frontend work can start in parallel using the canonical field
  names with a `quote_*` fallback.

## Verification (run in order, do not skip)

```
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
python3 _tools/db_sanity.py
git add <explicit paths only — never -A in this repo>
git commit -m "Phase 2 Section D: enforce price contract at endpoint layer"
bash _tools/restart_master_ai.sh
```

Then re-probe and confirm: `/dashboard/portfolio` and `/dashboard/radar`
agree on `price_state` for the same symbol; `portfolio_heat_pct` is no longer
0.0 with a stopless position open; no `999` anywhere in a radar payload.

## Report back
Files changed, validation output, what still fails, and anything in this plan
that turned out to be wrong about the codebase.

---

## D-7 — Bookkeeping closes are polluting the outcome dataset (added 19:0x)

On 2026-08-15 the user restated one position by closing the existing rows and
opening a corrected one. The closes were an **accounting action, not trade
outcomes**, but the DB cannot tell the difference. Current state:

- id=9 EQUIPMENT: `entry_date = exit_date = 2026-08-15`, `exit_price = 223`,
  `pnl_pct = -24.15`, `pnl_fils = -10,650,000`. This trade never happened.
- `stats_30d` now reads: `total_trades=2, wins=0, losses=1, win_rate=0.0,`
  `avg_loss_pct=-24.15, total_pnl_fils=-10,650,000`.
- `best_trade` and `worst_trade` are the same row (-24.15%). The stats builder
  emits a confident "best trade" from a single loss — no guard for n=1.

**Why this blocks C-27:** C-27 re-scores hit/miss and re-derives weights from
exactly this table. A synthetic -24% loss and a phantom 10,650 KWD drawdown
would be learned from as if real.

**Change:**
1. `ALTER TABLE`: add `trade_kind TEXT DEFAULT 'real'` — `'real' | 'void'`.
   Do NOT delete rows; deleting hides the correction.
2. Mark id=9 (and any other row closed the same minute it was created) as
   `'void'`, with the reason in `exit_reason`.
3. Every stats, win-rate, P&L and scoring query filters `trade_kind='real'`.
   C-27 must filter too — add it to that plan's prerequisites.
4. `db_sanity.py`: flag rows where `created_at::date == exit_date` as
   candidate bookkeeping closes.
5. Guard the stats builder: with fewer than 2 closed trades, return
   `best_trade = null` and a reason rather than naming the only row.

## D-8 — Position size exceeds stated capital

id=10 entry value is 142,705 KWD against `risk-status.capital = 121,000` —
118% of capital, with `risk_per_trade_pct = 2.0` and `max_positions = 3`.
Either the capital figure is stale or position sizing has no ceiling check.
**Ask the user which before changing anything.** Then add a `capital_note`
when a single position exceeds capital, instead of sizing silently past it.

---

## STATUS — independent verification by claude.ai, 2026-08-15 (post `3d5f8b0`)

Probed live against the tunnel, not read from the report.

| item | verdict | evidence on the wire |
|---|---|---|
| D-1 | **green** | `/dashboard/portfolio` open[0]: `price_state=live, price_as_of=2026-08-13T10:14:18+00:00, price_source=yahoo, price_age_days=2, pnl_valid=true`; identical in `/dashboard/radar -> journal_open[0]`; `quote_*` aliases still present |
| D-2 | **green** | `portfolio_heat_pct=5.3` (was 5265.1), `heat_complete=true`, `positions_without_stop=0`, `can_open_new=true`. Units bug resolved; hand-check agrees |
| D-3 | **partial** | column added and write paths gated, but `entry_date_precision` is **absent from the `/dashboard/portfolio` payload**. DB-only is not enough — C-27 and positions.html read the wire, not the table. Emit it. |
| D-4 | **green** | `data_age_hours=58.1` (real), `data_state=normal`, `sessions_old=0`, no `999` anywhere in the radar payload |
| D-5 | **green** | counter live, no deletion |
| D-6 | **green** | `whitelist=[]`, `whitelist_suspended_reason` present, `flags.whitelist_mode=false` |
| D-7 | **NOT DONE** | `trade_kind` absent on the wire; id=9 unmarked; `stats_30d` still reports `losses=1, win_rate=0.0, avg_loss_pct=-24.15, total_pnl_fils=-10,650,000` — the phantom trade is still being taught |
| D-8 | **NOT DONE** | position value 142,705 KWD vs `capital=121,000` — untouched |

D-7 and D-8 were appended to this file at ~19:0x, likely after the executing
session had already read it. They are not failures of that session. They are
still open, and **D-7 blocks C-27** for the same reason D-3 did: C-27 reads
`stats`/closed trades, and one synthetic -24.15% loss is currently in there.

Also confirmed from the executing session's own report: `git add -A` in the
verification block was wrong for this repo — corrected above.

---

## D-9 — Record the consolidated restart as what it is (user decision, 2026-08-15)

The user confirmed reading **(b)**: `id=10` is a deliberate restart. The older
EQUIPMENT exposure (first bought ~May 2026 at 294, averaged down) was closed
on the books, and the position is now tracked from 2026-08-15 at avg 224. The
-24% is written off by intent, not by error.

So `entry_date = 2026-08-15` is correct **as an accounting fact**. What is
missing is that nothing on the row says so, and `entry_date_precision=exact`
is currently carrying that meaning by accident.

**Change:**

1. **Split the two claims that are sharing one field.**
   - `entry_date_precision` — how well the date is known: `exact | approx`.
     Nothing else. Never set by a confirmation step.
   - `user_confirmed_at` (TEXT, nullable) — when a human reviewed and settled
     this row. This is what silences a checker, not the precision value.
   - Rework the D-3 and D-7 checkers to key off `user_confirmed_at`. A row
     may be confirmed AND approx at the same time; today that is unsayable.

2. **Add `entry_basis TEXT DEFAULT 'new'`** — `'new' | 'consolidated_restart'`.
   Set `id=10` to `'consolidated_restart'`.

3. **C-27 must EXCLUDE `entry_basis='consolidated_restart'` from hit/miss
   scoring.** This is not a filter of convenience — such a row has
   `entry_signal_id = NULL` and no originating signal, so scoring it measures
   a bookkeeping date against a price series and calls the result evidence.
   Same class of error as the void rows, arriving by a different door.

4. Write the intent into `entry_reason` on id=10, in plain words: restart of a
   prior position, avg cost 224 after averaging down from 294, first purchase
   ~May 2026, P&L tracked from 2026-08-15.

5. Link the audit trail: `notes` on id=10 references the void rows it
   supersedes (id=2, id=9), so the older cost basis stays traceable after it
   left the P&L.

## D-10 — Concentration is not measured (the real remainder of D-8)

`capital` is now 144,000 KWD and `portfolio_heat_pct = 4.4` with
`heat_complete = true` — both correct. But id=10 is worth 142,705 KWD, i.e.
**99% of capital in one position**, and the engine still reports
`can_open_new = true` because heat (4.4%) sits under the 6% cap.

Heat measures loss-if-stopped. It says nothing about how much capital is
committed. Two different questions; only one is being asked.

**Change:**
1. Compute `capital_deployed_pct` = sum(open position value) / capital.
2. Add `capital_available_kwd` and `concentration_note`.
3. `can_open_new` must be false when there is no capital left to open with,
   regardless of heat. A slot count and a heat figure are not a cash balance.
4. If a single position exceeds a configurable share of capital (suggest 40%),
   emit `concentration_note` saying so. Do not block — the user sizes his own
   positions — but do not stay silent either.

**Acceptance:** with id=10 open, `capital_deployed_pct ~= 99`,
`can_open_new = false`, and `concentration_note` is non-null.

---

## Open items after D-9/D-10 land

- C-27 — clear to start **only once D-9.3 is in place** (restart rows excluded).
- `positions.html` / `radar.html` — claude.ai, canonical fields are on the wire.
- ~36 remaining price paths → `get_price`.
- D-5 counter review (one week from 2026-08-15).

---

## D-11 — Two clocks in one row, in a column created today

Verified on the wire, `id=10`:

```
created_at        = 2026-08-15 18:59:50
user_confirmed_at = 2026-08-15 16:31:11
```

The confirmation appears to happen **2h28m before the row existed**. It did
not. The row was created ~19:00 Kuwait time and confirmed ~19:31 Kuwait time.
So:

- `created_at` is being written in **local** (+03)
- `user_confirmed_at` is being written in **UTC**

`user_confirmed_at` is the correct one — it follows the project convention
that every stored timestamp is UTC. `created_at` is the pre-existing offender
already named in `mixed_clock_census.md`. The new column did nothing wrong;
it landed next to an old bug and made the contradiction visible.

But the pair is now unusable: any check of the form "was this row confirmed
after it was created?" returns a negative interval and will either fire
falsely or be silently swallowed. This is precisely the case the census rule
covers — *a column read alongside another written by a different path gets
both paths audited together before either is trusted.*

**Change:**
1. Do not "fix" this by writing `user_confirmed_at` in local to match.
   The convention is UTC; move `created_at` onto it.
2. Audit every consumer that compares `created_at` to anything, including the
   D-7 checker rule `created_at::date == exit_date` — that comparison mixes a
   local date against a UTC one and can misclassify rows near midnight.
3. Add both columns to `mixed_clock_census.md` with their proven clock.

## D-12 — The gate that closed does not say why

`can_open_new = false` is now correct, and `concentration_note` explains the
99%. But nothing on the wire states the rule that produced the false: the
"below 1% of book is noise, not a position" floor is applied in code and
described only in a commit message.

Add `can_open_new_reason` naming the binding constraint (heat / capital floor
/ slots). A gate whose reasoning is invisible is a gate nobody can audit —
rule 11 of the project's own strict list.

---

## Section D closed — verified on the wire 2026-08-15 (post `a54c508`)

D-11: `created_at = 15:59:50 UTC`, `user_confirmed_at = 16:31:11 UTC` —
+31 min, the real interval. Spot-checked the migrated rows: no row crossed a
calendar boundary under the -3h shift (earliest `created_at` is 06:06, so the
00:00–02:59 local danger window is empty). `entry_date` / `exit_date` were
correctly left alone.

D-12: `can_open_new_reason = "capital floor: 1,295 KWD available < 1,440 KWD
(1% of capital) - below that is noise, not a position"`. The rule is on the
wire where it can be argued with.

D-1..D-12 all green.

---

## C-27 — two preconditions before it starts

**1. Seven closed trades carry `entry_date_precision = NULL`.**
ids 1,3,4,5,6,7,8. In every one, `date(created_at) == entry_date`, which is
good evidence the dates are real — but *evidence* is not *stated*, and NULL
is not `exact`. C-27 will otherwise score seven rows as if their dates were
confirmed. Either backfill precision with the derivation recorded in `notes`
(derived from same-day logging, not user-stated), or have C-27 report the
count of rows it scored at unknown precision. Do not let NULL read as exact —
that is the whole disease in one field.

**2. C-27 must emit a run manifest, or it cannot be trusted either.**
The reason we are here is that the system's previous learning was measured
with a broken ruler and *nobody could tell from the output*. If C-27
re-derives weights and does not record how, we get a fresh set of numbers
that are equally unfalsifiable — better numbers, same epistemics.

Each run writes, versioned and stored:
- run timestamp **and its clock**, code commit
- window definition used, in words
- counts included / excluded with the reason per exclusion bucket
  (`trade_kind=void`, `entry_basis=consolidated_restart`, precision unknown)
- weights before and after, side by side
- the input row/signal ids, or a hash of them

Acceptance: a second run on unchanged inputs reproduces the first exactly,
and a human can read the manifest and say *why* a weight moved.

**3. C-27 must read `signal_reviews.graded_mode` and treat the four values
differently.** (Added by Section E follow-up, 2026-08-15.) The column is
never NULL: `live` = graded on the first session after the decision,
`backfill` = graded later from Yahoo history (E-1 backfill, 20 rows),
`legacy` = graded in Mar-Apr 2026 by the pre-E-1 loop on bridge bars
(5 rows), `ungraded` = `no_data`, nothing measured (currently today's 6,
replaced next session). C-27's hit-rate basis may use `live` and `backfill`
rows; `legacy` rows were measured on the old price path and belong in the
same suspicion bucket as everything else C-27 exists to re-measure;
`ungraded` rows are not outcomes at all and must be counted as coverage
gaps, never as neutral results. The manifest's exclusion buckets
(precondition 2) gain one axis: counts per `graded_mode`.
