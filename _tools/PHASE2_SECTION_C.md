# Phase 2, Section C — backlog

Standalone items agreed during the 2026-08-14 session but deliberately not
implemented yet. Each needs its own commit and its own approval.

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

Reported 2026-08-14, left unfixed pending approval.
