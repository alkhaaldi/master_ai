# Mixed-clock census — 2026-08-15

Every comparison between a Python-built timestamp and a stored column, swept
after the C-17 correction. Scope: all runtime .py (venv, _archive,
_deprecated, examples excluded). Read-only sweep at first writing; findings #1-#14 were then fixed on
2026-08-15 (see git log), each with a planted-row before/after proof.
#15/#17 were corrected instead - see below. #16, #18, #19 remain open.
Section F (E-4): #20 decision_audit.decision_time writer now UTC but
historical rows still local (conversion awaiting approval); #21
signal_reviews.review_date resolved to UTC dates.

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
11. RESOLVED 2026-08-15 (D-11): trades.created_at moved to UTC - the
    writer (journal open_trade) now stamps utcnow and the 10 existing
    rows were migrated -3h. Proven clocks: created_at UTC,
    user_confirmed_at UTC, entry_date/exit_date Kuwait calendar days -
    every comparison of a date column against created_at localises
    (+3, no DST) first. The dashboard 7d threshold went back to plain
    datetime("now"). Found because the D-9 column landed beside the old
    local stamp and a confirmation appeared to precede its row by 2h28m
    - the two-writer rule catching a one-day-old column.
12. trading_brain.py:733-736 weekly report - date.today() local date-only
    vs UTC signal_time: 3h edge error at week boundaries.
13. journal_engine.py:547 - local date-only vs UTC
    stock_radar_events.created_at: 3h edge on the 7d stats window.
14. dashboard_api.py:3051 - local date-only week_ago vs UTC "Z" column:
    3h edge.
15. domain_kpis.py:82 - WITHDRAWN as a clock finding, 2026-08-15. The
    tasks table domain_kpis reads (life.db) has 0 rows - its only writer,
    task_engine.py, apparently never ran - so "done/week" counts an empty
    table. The clocks are irrelevant; the defect is a dead table. Recorded,
    not fixed: reviving or retiring task_engine is its own decision.

## C. Two-writer columns (the rule in CLAUDE_CONTEXT.md)

16. memory (audit.db): created_at written UTC isoformat+"Z"
    (memory_db.py:17) while dream_consolidator.py:114 writes updated_at
    local isoformat, no Z - two clocks and two formats inside one table.
17. CORRECTED 2026-08-15: the original entry conflated two different
    tables that share the name tasks. server.py:2534 (localtime UPDATE)
    writes audit.db tasks (task_id/goal schema, 1,381 rows); the life.db
    tasks (title/status schema, UTC default) is a separate, empty table.
    No column has two writers here - the earlier claim was itself a
    single-name-two-things error, the same shape as radar_enabled.
    audit.db tasks IS written in two clocks though: its INSERT path needs
    checking before anything windows on its updated_at.
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

## F. Section E additions (E-4, 2026-08-15)

20. decision_audit.decision_time — PROVEN local +03, space format, at
    conversion time. Single writer: kse_data_collector.log_decision
    (was datetime.now()). Proof: rows id 29-31 stored "2026-08-15
    20:29:20" while the wall clock at that write was 20:29 +03 =
    17:29 UTC. Writer converted to utcnow() on 2026-08-15 (E-4).
    Rows written before 2026-08-15 ~17:30 UTC still hold LOCAL +03
    values — historical-row conversion (-3h, D-11 style) was prepared
    but NOT executed (blocked pending user approval); until then the
    column is two-clocked at the 2026-08-15 boundary. Comparators
    audited: dashboard_api.py:2567 ORDER BY only — months separate the
    local-era rows from the UTC-era rows, so the 3h skew cannot reorder
    anything. No WHERE/window reads this column. market_date in the
    same table is a KSE session date (local calendar), not a timestamp.

21. signal_reviews.review_date — PROVEN local calendar date (was
    date.today()). Single writer: signal_review.review_signals:333.
    Writer converted to utcnow().date() on 2026-08-15 (E-4); existing
    values needed no conversion because every historical run happened
    ~14:00-20:00 KWT, where local and UTC dates coincide (verified:
    review_date range 2026-03-30..2026-08-15, all written afternoon).
    Comparators audited, all date-vs-date within one convention:
    - signal_review.py:381 graded_mode vs daily_bars.trading_date
      (UTC-derived session date, backfill_daily_bars fetch_bars) — KSE
      sessions run 06:00-10:00 UTC so both dates always agree;
    - review_liveness() MAX(review_date) vs daily_bars.trading_date;
    - review_scheduler fallback guard :663 — converted to utcnow date
      in the same change (write path and comparator moved together).
    Same table carries created_at/updated_at as CURRENT_TIMESTAMP (UTC
    space) and outcome_date (decision_audit) = review_date — one
    declared clock family after E-4. decision_time_pre_e4 does NOT
    exist (the prepared migration column was never created).
