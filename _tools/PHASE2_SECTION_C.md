# Phase 2, Section C — backlog

Standalone items agreed during the 2026-08-14 session but deliberately not
implemented yet. Each needs its own commit and its own approval.

Ordered by priority, not by number. C-13 leads because C-17 shows what it cost.

---

## C-13. snapshot_signals runs every tick, not every two hours

`server.py` `_brain_scheduler` sleeps 600s and its snapshot branch has no
interval gate:

```python
# Snapshot signals every 2 hours during market hours   <- the comment
if wd in _KSE_DAYS and 9 <= hour < 13:
    snapshot_signals()                                  <- fires on every tick
```

A four-hour session is therefore about 24 snapshots, not 2. `signal_snapshots`
already holds 67,109 rows, the largest table in `life.db`, and this is why. Any
pruning of that table should start by deciding the intended interval, otherwise
it grows straight back.

Found 2026-08-14 while correcting the window. Not fixed: changing the cadence
changes what the brain learns from, and Sunday's run is the first observation of
this loop on a trading day at all.

---

## C-10. build_signals() must read from the DB, not the bridge

**Rule this violates.** `_tools/OPERATIONAL_ACCESS_MATRIX.md` already prohibits
it, under Prohibited: *"Heavy operations inside request path — causes timeout on
`/dashboard/extended` etc."* This is that, in the signals path.

**Current chain.**

```
HA REST sensors (scan_interval 120)
  -> GET /dashboard/portfolio  and  GET /dashboard/signals
    -> build_signals()  /  build_signals_30m()
      -> _get_bridge_data_safe()  -> get_multi_analysis(128 symbols)
```

A sensor poll therefore reaches out to the bridge for the entire watchlist. Two
mitigations sit in front of it today, and neither addresses the shape:

- a 5-minute module-level cache in `signal_engine._get_bridge_data_safe`
- a breaker back-off added 2026-08-14 (`026a9c1`), which skips the fetch while
  the bridge circuit is open

Both make the symptom rarer. Neither stops a dashboard read from doing live
outbound work.

**Why it matters beyond load.** The bridge is started by hand for analysis
sessions. When it is up, the current design has HA sensors pulling 128 symbols
through it every few minutes for as long as the dashboard is open — measured at
about 128 requests per 5 minutes with the bridge down, and there is no reason to
think it is gentler when the bridge answers.

**Shape of the fix.** `build_signals()` reads the stored snapshot
(`stock_radar_daily` / `stock_radar_state`) and reports its age, exactly as
`/dashboard/radar` already does through `get_daily_snapshot()`. Refreshing that
snapshot stays a deliberate act: the daily scheduler, or `POST
/daily-snapshot/refresh`.

**What to check before doing it.**

- which fields of `build_signals()` output actually require live prices, if any
- whether `signals.html` presents the live tab as real-time, and what it should
  show when the snapshot is stale (`daily_context_reason` already carries this
  vocabulary)
- `/dashboard/portfolio` calls `build_signals()` only to enrich open trades with
  `signal_health`; that may not need live data at all

---

## C-11. confluence_engine expiry compares local timestamps to a UTC threshold

`confluence_engine.py:271`:

```sql
UPDATE confluence_signals SET is_active = 0
WHERE created_at < datetime('now', '-24 hours')
```

`created_at` is written as `datetime.now().isoformat()`, which is Asia/Kuwait
local. SQLite's `datetime('now')` is UTC. Signals therefore stay active for 27
hours rather than 24. Same fault class as the timezone rule in
`CLAUDE_CONTEXT.md`.

---

## C-14. the evaluation window can catch two ticks

Same loop. The gate is `hour == 13 and 25 <= minute <= 35` - eleven minutes wide
- while the loop ticks every ten. Two ticks can land inside it, running
`evaluate_pending_signals()` twice in one day.

Whether that is harmful depends on whether the evaluation is idempotent; it does
`UPDATE signal_snapshots SET outcome=..., outcome_evaluated_at=CURRENT_TIMESTAMP`
over pending rows, so a second pass would re-evaluate rows the first pass just
closed. `_tools/verify_sunday.py --step 9` reports the number of distinct
evaluation clusters precisely so this can be observed rather than assumed.

---

## C-15. signal_snapshots mixes two clocks in one table

`signal_time` is written from `datetime.now()` (Asia/Kuwait local).
`outcome_evaluated_at` is written by SQLite `CURRENT_TIMESTAMP` (UTC).

Any query that compares or subtracts the two is off by three hours. Nothing is
known to do so today, but the table invites it, and the same pairing has already
produced two live faults elsewhere - see the timezone rule in
`CLAUDE_CONTEXT.md`.

---

## C-17. 78% of the brain's training data was captured before the market opened

`signal_snapshots` holds 67,109 rows. By hour of `signal_time` (local):

| hour | rows | |
|---|---|---|
| 03:00 | 99 | |
| 05:00 | 2 | |
| 06:00 | 26,470 | |
| 07:00 | 13,444 | |
| 08:00 | 12,520 | |
| 09:00 | 13,006 | inside the session |
| 10:00 | 1,568 | inside the session |

**52,535 rows - 78.3% - carry a signal_time before 09:00**, and none at all
after 13:00. The shape matches the old `6 <= hour <= 10` gate exactly, so this
is that bug's full footprint, now fixed forward but not backward.

Who reads it:

- `trading_brain.py` - the important one. It selects
  `WHERE outcome IN ('hit','miss')` to score indicators and adjust
  `indicator_performance.current_weight`. Four fifths of that training sample is
  signals computed on pre-market data and then graded as if they had been live.
- `dashboard_api.py` - timeframe comparison panel
- `stock_personality_engine.py`

This is why C-13 leads this list. Deciding the cadence is the cheap part;
deciding what to do with 52,535 mislabelled training rows is not, and the
learned weights derived from them are already in `indicator_performance`.

Nothing pruned, nothing recomputed. Recorded 2026-08-14.

---

## C-12. server.py signal snapshot loop: wrong hours and a missing trading day

`server.py` around line 2981, in the loop that calls `snapshot_signals()` and
`evaluate_pending_signals()`:

```python
now = _dt.now()
hour, minute, weekday = now.hour, now.minute, now.isoweekday()
# Snapshot signals every 2 hours during market hours (Sun-Thu 9-13 KWT = 6-10 UTC)
if weekday <= 4 and 6 <= hour <= 10:
```

Three separate faults:

1. The comment converts to UTC but `datetime.now()` is local, so snapshots run
   06:00-10:59 instead of 09:00-13:00.
2. The evaluation branch (`hour == 10 and 25 <= minute <= 35`) is commented as
   13:30 KWT and runs at 10:30 local.
3. `isoweekday()` is Mon=1 .. Sun=7, so `weekday <= 4` means Mon-Thu. KSE trades
   **Sun**-Thu, so Sunday is skipped entirely — no snapshot, no evaluation.

The weekly-report branch (`weekday == 5`) does correctly mean Friday, but runs at
11:00 local under a comment saying 14:00.

**Fixed 2026-08-14.** Day set moved to weekday() with (6,0,1,2,3) = Sun-Thu,
snapshots 09:00-12:59 local, evaluation 13:30 local, weekly report Friday
14:00 local. Verified against ten simulated timestamps including the Sunday
case that previously did nothing. Sunday 2026-08-16 is the first time this
loop will run on a trading day - watched by verify_sunday.py steps 8 and 9.

---

## C-16. quick_check.py is unreliable for its first ~2 minutes after a restart

Its endpoint probes hit the service before startup completes, so it reports
failures that clear on their own. Observed twice on 2026-08-14: 9/13 and 10/13
immediately after a restart, both 13/13 once uptime passed roughly two minutes.

Cost so far is wasted investigation, twice. A settle-wait or a readiness probe
before the endpoint section would remove a real source of false alarms in the
one tool that is supposed to tell you whether a change was safe.

---
