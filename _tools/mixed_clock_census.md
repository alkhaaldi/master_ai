# Mixed-clock census — 2026-08-15

Every comparison between a Python-built timestamp and a stored column, swept
after the C-17 correction. Scope: all runtime .py (venv, _archive,
_deprecated, examples excluded). Read-only sweep; nothing below was fixed
except trading_brain.py:174/:277 (committed separately).

The two fault axes:
- **clock**: datetime.now() is Kuwait local (+03); CURRENT_TIMESTAMP /
  datetime("now") is UTC.
- **format**: isoformat() separates with "T"; SQLite writes a space.
  On same-date strings, space (0x20) sorts BEFORE "T" (0x54), so a
  space-format row always compares LESS THAN a T-format cutoff of the
  same date - regardless of the actual times.

## A. Live lies (measured on the box)

1. domain_kpis.py:106 - "News: N today" is permanently 0.
   Param today+"T00:00:00" vs news_digests.created_at, which
   news_engine.py:270 writes local space-format. Same date, space < T,
   every row of today fails the >=. Measured 2026-08-15: T-param 0 rows,
   space-param 9, actual today 9.

2. brain_proactive.py:79 _get_recent_alerts - the duplicate-alert gate
   finds 0 almost always. Cutoff utcnow().isoformat() (T); column filled
   by DEFAULT datetime("now") (space). With hours=6 the cutoff date is
   today for most of the day; every same-date row sorts below it. The
   dedup that should suppress repeat alerts is open.

3. brain_proactive.py:105 _count_alerts_last_hour - same mechanism, so
   the hourly alert cap counts 0 and never trips.

4. server.py:3695 dashboard_ema_crosses (hours=4 default) - cutoff
   utcnow().isoformat() vs stock_radar_events.created_at (UTC space).
   Whenever the cutoff falls on today (any call after 04:00 UTC), every
   row is same-date-or-older and the endpoint returns empty. Currently
   masked: the events table is stale (last row 2026-03-25).

## B. Window distortions (works, but the window is not what it says)

5. news_engine.py:437 get_urgent_items - local T cutoff vs local space
   column: rows on the cutoff calendar day after the cutoff time are
   dropped; the "24h" window truncates at the day boundary.
6. stock_radar.py:1154 tg_radar_top - UTC T cutoff vs UTC space column:
   same truncation; "last 24h" behaves as "since midnight of today".
7. brain_analytics.py:98 - UTC T cutoff vs UTC space request_log rows:
   boundary-day rows dropped from the 7d analytics window.
8. corrections_loop.py:326 decay - local T cutoff vs UTC space
   created_at/last_applied: 3h skew plus boundary-day truncation on the
   30d decay window.
9. dream_consolidator.py:120,211,215 - local T cutoff vs UTC "Z"-suffixed
   memory.created_at (audit.db, writer memory_db.py:17): 3h skew on the
   90d/1d/7d windows.
10. confluence_engine.py:271,411,504,528,553 vs writer :395
    (datetime.now().isoformat(), local T) - C-11, now verified: UTC
    threshold vs local column = 27h lifetime instead of 24h, plus the
    same-date T quirk. Stored proof: created_at "2026-08-13T06:01:53".
11. dashboard_api.py:926 - trades.created_at is local space
    (journal_engine.py:148 datetime.now()); threshold datetime("now")
    UTC: the 7d window runs 3h long.
12. trading_brain.py:733-736 weekly report - date.today() local date-only
    vs UTC signal_time: 3h edge error at week boundaries.
13. journal_engine.py:547 - local date-only vs UTC
    stock_radar_events.created_at: 3h edge on the 7d stats window.
14. dashboard_api.py:3051 - local date-only week_ago vs UTC "Z" column:
    3h edge.
15. domain_kpis.py:82 - local date-only vs tasks.updated_at: see #17;
    that column cannot be reasoned about until its two writers agree.

## C. Two-writer columns (the rule in CLAUDE_CONTEXT.md)

16. memory (audit.db): created_at written UTC isoformat+"Z"
    (memory_db.py:17) while dream_consolidator.py:114 writes updated_at
    local isoformat, no Z - two clocks and two formats inside one table.
17. tasks.updated_at (life.db): INSERT default datetime("now") = UTC;
    server.py:2534 UPDATE sets datetime("now","localtime") = local.
    Same column, two clocks, indistinguishable after the fact.
18. signal_snapshots.signal_time and stock_radar_events.candle_time -
    already recorded (C-17 correction, C-26).

## D. Fragile but currently correct

19. server.py:8237 - today_start = utcnow().replace(0,0,0).timestamp():
    .timestamp() reads the naive value as LOCAL, shifting the epoch -3h,
    which happens to land exactly on Kuwait midnight. Correct today by
    double error; breaks the day the box timezone changes.

## E. Verified consistent (no action)

- brain_proactive.py:95,304,326 (UTC date-only vs UTC), :343 date("now")
- structured_memory.py:369; cost_tracker.py:216,285,286
- context_compactor.py:189; dashboard_api.py:923
- server.py:2261 (local vs local); kairos.py:85 (UTC vs UTC)
- journal_engine.py:319,516 (local date vs local-date entry_date column)
