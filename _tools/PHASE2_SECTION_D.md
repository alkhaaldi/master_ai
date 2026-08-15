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
git add -A && git commit -m "Phase 2 Section D: enforce price contract at endpoint layer"
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
