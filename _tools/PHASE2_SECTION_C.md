# Phase 2, Section C — backlog

Standalone items agreed during the 2026-08-14 session but deliberately not
implemented yet. Each needs its own commit and its own approval.

Ordered by priority, not by number. C-13 leads because C-17 shows what it cost.

> **Status field (added 2026-08-15, by user decision):** every item carries
> one of three states. **مُتحقَّق** = re-verified against the live system with
> recorded evidence. **مزعوم** = recorded in a past session, not independently
> re-verified. **مُصلَح** = fixed and committed. **No مزعوم item may be
> implemented before it is verified** — C-17 below is the standing proof of
> why: acting on it as recorded would have destroyed 32,283 valid rows.

---

## C-13. snapshot_signals runs every tick, not every two hours

**الحالة:** مزعوم

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

**الحالة:** مزعوم

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

**الحالة:** مُصلَح 2026-08-15 — الكاتب صار يختم UTC بصيغة العمود (`confluence_engine.py`, رقعة تشوهات النوافذ). برهان بصفّين مزروعين عمرهما 25 ساعة: ختم قديم محلي بقي نشطاً (علّة الـ27 ساعة)، ختم جديد انتهى في موعده. الصفوف القديمة لم تُهاجَر — كلها منتهية الصلاحية أصلاً (آخرها 2026-08-13). 2026-08-15 — المسار مقيس: الكاتب confluence_engine.py:395 يكتب `datetime.now().isoformat()` محلياً بصيغة T، والقيمة المخزَّنة شاهدة (`2026-08-13T06:01:53`)، والقارئات الخمس تقارن بـ`datetime("now")` UTC. العمر 27 ساعة مؤكَّد، ويضاف إليه عطب الصيغة (المسافة قبل T في ترتيب اليوم نفسه). انظر `_tools/mixed_clock_census.md` بند 10.

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

**الحالة:** مزعوم

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

**الحالة:** مزعوم

`signal_time` is written from `datetime.now()` (Asia/Kuwait local).
`outcome_evaluated_at` is written by SQLite `CURRENT_TIMESTAMP` (UTC).

Any query that compares or subtracts the two is off by three hours. Nothing is
known to do so today, but the table invites it, and the same pairing has already
produced two live faults elsewhere - see the timezone rule in
`CLAUDE_CONTEXT.md`.

---

## C-17. 78% of the brain's training data was captured before the market opened

**الحالة:** مُتحقَّق — والاستنتاج الأصلي مدحوض، انظر تصحيح 2026-08-15 أدناه

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

**Correction 2026-08-15 — the 78% figure was a clock misread, and executing
this item as written would have destroyed 32,283 correct training rows.**

signal_time is UTC, not local. 99.74% of the table is backfill
(historical_backfill_30m 50,790 rows + historical_backfill 16,147), and its
signal_time is the candle timestamp built by
datetime.utcfromtimestamp(bar_time) — brain_backfill.py:223 and :350. The
supposed pre-open hours are the session itself: the 30m rows sit on a strict
06:00–10:00 UTC half-hour grid = 09:00–13:00 Kuwait, every second zero.

Measured 2026-08-15:

- training subset (outcome hit/miss): 41,068 rows.
  indicator_performance.total_signals = 41,068 — the weights are trained on
  exactly this set (last_updated 2026-08-14 08:04).
- genuinely pre-open rows in the training subset: **75** (03:xx/05:xx UTC),
  all from source=auto — the live capture path, 172 rows in the whole table,
  the only rows the old 6<=hour<=10 gate actually mislabelled.
- excluding everything before 09:00 read as local, as this item implied:
  32,358 rows gone. Excluding the genuinely pre-open ones: 75. The gap —
  **32,283 correct rows** — is what the fix would have destroyed.
- even under the wrong reading, hit rate pre-open vs in-session is
  35.05% vs 32.58% — no cliff.

What survives of the original item: the brain trains almost entirely on
backfill (only 102 hit/miss rows are live), and the table still mixes two
clocks per C-15 (outcome_evaluated_at is CURRENT_TIMESTAMP).

---

## C-12. server.py signal snapshot loop: wrong hours and a missing trading day

**الحالة:** مُصلَح

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

**الحالة:** مزعوم

Its endpoint probes hit the service before startup completes, so it reports
failures that clear on their own. Observed twice on 2026-08-14: 9/13 and 10/13
immediately after a restart, both 13/13 once uptime passed roughly two minutes.

Cost so far is wasted investigation, twice. A settle-wait or a readiness probe
before the endpoint section would remove a real source of false alarms in the
one tool that is supposed to tell you whether a change was safe.

---

---

## C-18. tg_logbook reads the Gmail token directly, bypassing the feature gate

**الحالة:** مزعوم

`tg_logbook.py:33` does its own `Credentials.from_authorized_user_file(...)` and
`creds.refresh(Request())`, exactly like the fallback in
`tg_email._gmail_service` that had to be gated during Section B. It therefore
ignores `google_integrations` entirely.

It cannot fire today: `tg_logbook` is one of the ten modules with zero importers
and it is not in cron, so nothing reaches it. Recorded because the moment anyone
wires it up, the invalid_grant loop returns and the flag will look like it is
lying.

The general shape is worth naming: a feature gate on a shared helper only holds
if every caller goes through that helper. Section B found two private token
readers behind one gate; this is the third.

Recorded 2026-08-14, not fixed - dead code, does not block Sunday.

---

## C-19. brain_core.reload() calls two functions that no longer exist

**الحالة:** مزعوم

`brain_core.py:342`, inside `reload()`:

```python
try:
    _ensure_memory_table()
    _apply_confidence_decay()
except Exception as e:
    logger.error(f"Brain reload failed: {e}")
```

Neither name is defined in `brain_core.py` or imported into it.
`_apply_confidence_decay` survives only in `_deprecated/brain_backup.py:209`;
`_ensure_memory_table` is gone entirely. The call raises `NameError` on the
first line, so **`_apply_confidence_decay()` has never run** - the except catches
it, logs one line, and carries on.

Surfaced by the C-8 import test on 2026-08-14, which printed "Brain reload
failed: name '_ensure_memory_table' is not defined" before its own summary.
`reload` is imported into `server.py:53` as `brain_reload`, so this fires at
every startup.

The same shape as commit 651b154 and as `_check_api_key` in `/anomalies`: code
was moved or archived and its callers were left behind, with a try/except
turning a hard failure into a log line nobody reads. Confidence decay on brain
memories has been silently off for however long that has been true.

Not fixed: restoring decay changes stored confidence values across
`memory`, `memory_archive` and `structured_memory.memories`, which is a data
decision, not a syntax one. Does not block Sunday.

---

## C-20. every `logger.info` in this codebase has always been invisible

**الحالة:** مُتحقَّق — بآلية مصحَّحة، انظر تصحيح 2026-08-15 أدناه

The root logger sits at WARNING. Before it was configured at all, module loggers
fell through to `logging.lastResort`, which is also WARNING. Either way, no
`logger.info` from any module has ever reached `server.log`.

Confirmed on 2026-08-14: `grep -c "Next daily collection" server.log` returns 0,
even though `daily_collection_scheduler` logs it on every cycle at INFO. The
same is true of the "Bridge daily cache refreshed", "Confluence scan loop
started" and "Daily trading summary scheduler started" lines, among others.

Two consequences already met in one day:

- verify_sunday step 5 could never have passed. It looks for the scheduler's
  skip line, which was logged at INFO. Raised to WARNING as part of that
  verification, since a deliberate skip leaving no trace is indistinguishable
  from the scheduler dying.
- the Google integrations notice had the same fault and was raised for the same
  reason.

Fixing this properly is a judgement call, not a sweep. Setting root to INFO
would surface hundreds of lines a day and re-flood the 2MB rotation the logging
work was meant to fix. The likely shape is a named list of operational loggers
raised to INFO while third-party libraries stay at WARNING - but that is a
decision about what is worth recording, and it should be made deliberately
rather than by flipping one level.

Recorded 2026-08-14. Two specific lines fixed where they blocked verification;
the rest untouched.

**Correction 2026-08-15 — the claim and the mechanism were both wrong.**

server.log carries 1,356 INFO lines, 948 of them from the master_ai logger,
the latest written minutes before measurement. So not every logger.info was
invisible — every logger.info **except through a logger whose own level is
INFO** was. The mechanism: a logger filters at emission by its own effective
level; parent LEVELS are never consulted afterwards, only parent HANDLERS
receive the record. Root at WARNING therefore does not suppress a child
explicitly set to INFO — and server.py:726 sets master_ai to INFO, which is
why its lines pass. The ~110 bare module loggers (getLogger with no
setLevel) inherit WARNING as their effective level and their INFO dies at
emission — the example in this item, the daily_collection_scheduler logger
in kse_data_collector.py:497, is one of those, and its Next daily collection
line indeed appears 0 times.

Also verified: the root file handler is level NOTSET (passes everything),
no module in the tree sets propagate=False, and WARNING+ reaches server.log
from every module. The double-write (every line twice, no logger name)
ended at the 2026-08-14 08:02 restart; the current config writes once.

The closing judgement of this item stands: which loggers deserve INFO is a
decision, not a sweep.

---

## C-21. two independent switches both called radar_enabled

**الحالة:** مزعوم

`stock_radar.py:798-812` gates the radar loop on both, in sequence:

```python
if not _ff.is_enabled("radar_enabled"):   # feature flag, currently True
    continue
cfg = _get_config()
if not cfg.get("enabled", True):          # data/ema_radar.json, currently False
    continue                              # <- the loop actually stops here
```

`/dashboard/radar` publishes `cfg["enabled"]`, and that is the switch genuinely
stopping the loop, so the published value is truthful. The hazard is for
readers: anyone checking `FeatureFlags.is_enabled("radar_enabled")` - the
obvious place to look, and the one the name suggests - concludes the radar is
running. It is not.

The radar was switched off on **2026-03-26 01:29**, the mtime of
`data/ema_radar.json`. `data/` is gitignored, so there is no commit, no message
and no recorded reason. `stock_radar_state` stops updating on 2026-03-25, which
is consistent. Why it was disabled is not recoverable from the repository.

Fixing this means deciding which switch keeps the name - the argument is that
`radar_enabled` should belong to the one that governs the loop - and renaming
the other explicitly. That changes a published field's value from false to true,
which is a value correction rather than a contract break, but it must be its own
commit and clearly announced, or it reads as a behaviour change.

Consumers, for whoever does it:
- feature flag: `stock_radar.py:804` only
- config `enabled`: `stock_radar.py:810`, `dashboard_api.py:178` and `:389`,
  `priority_engine.py:86`
- the published field: `www/trading/home.html:355` and the HA dashboard YAML

Recorded 2026-08-14, not fixed.

---

## C-22. journal_stats.open_trades is a state metric inside a 30-day window

**الحالة:** مزعوم

`journal_engine.get_trade_stats(days=30)` filters `WHERE entry_date >= cutoff`
and then reports `open_trades: len(open_t)` from that filtered set. EQUIPMENT
was entered 2026-03-26, 142 days ago, so it falls outside the window and the
dashboard says zero open trades while one is open.

Every other field in that function is legitimately windowed activity -
total_trades, closed_trades, wins, losses, win_rate, avg_profit, avg_loss,
total_pnl, best and worst trade. `open_trades` is the only state field among
them. A position is open regardless of when it was entered.

An AST sweep over every function taking a days/since/window argument found no
other genuine case; `feedback_learner.get_stats` matched only because
"proactive" contains "active".

Not fixed because it fails the isolation test. `get_trade_stats` is called from
eight places: `dashboard_api.py` five times across the radar, journal and
portfolio paths, `server.py:2847` with days=1, `server.py:6343` with days=30,
`tg_stocks.py:143` for Telegram, and `journal_engine.py:513` internally. It is
also registered as the agent tool `trade_stats` at `server.py:3061`. Changing
the semantics changes all of them at once.

Worth noting for that decision: the correction looks right in all eight. None of
those callers wants "how many opened inside the window and are still open" -
they all want "how many are open now".

Recorded 2026-08-14.

---

## C-23. the trailing stop is locked inside a target-hit branch

**الحالة:** مزعوم

`position_engine.py`, in `daily_monitor`, the only call to
`_update_trailing_stop` sits here:

```python
if t1 > 0 and not t1_hit and price >= t1:
    ...
    _mark_target_hit(trade_id, target=1)
    trailing = float(trade.get("trailing_stop") or 0)
    if trailing < entry_price:
        _update_trailing_stop(trade_id, entry_price)   # breakeven
```

So a stop can only ever move when target 1 is both set and hit. `t1` comes from
`target_1` or `take_profit`, and both are null on every trade in the journal, so
the branch has never opened. The engine runs, finds nothing it is allowed to do,
and returns quietly.

Whether that is wrong depends on intent. If the only trailing rule is
"breakeven after target 1", the code matches it. If a stop is meant to trail
price generally, the rule was never written. Deciding that is a trading
decision, not a code one.

Recorded 2026-08-14. Do not change before Sunday - it touches what the monitor
does to live positions.

---

## C-24. nothing stops a trade being opened with no stop loss

**الحالة:** مزعوم

Seven of the eight trades ever recorded have `stop_loss = NULL`. The single
exception is CLEANING on 2026-04-04 with `stop=140.0`. The one currently open
position, EQUIPMENT (entered 2026-03-26, 507,586 shares), has all six risk
fields null: `stop_loss`, `trailing_stop`, `original_stop`, `target_1`,
`target_2`, `take_profit`.

This is why C-23 has never fired, and it makes the risk engine, the stop
monitor and the trailing logic decorative for the position they are meant to
protect.

The fix is a policy question before it is a code one: refuse the trade, warn and
accept, or accept and flag it on the dashboard. `POST /api/trade/open` and the
Telegram `/trade` path would both need to agree, and there is existing history
to decide about - closing or annotating trades that predate the rule.

Recorded 2026-08-14.

---

## C-25. PAPER has no symbol on Yahoo

**الحالة:** مزعوم

Of the 128 watchlist symbols probed against Yahoo with the `.KW` suffix, 127
returned Kuwait-exchange equity data in KWF. `PAPER.KW` returned a clean 404 -
not a rate limit, not a block; thirteen AAPL controls passed through the run and
none failed.

So if Yahoo is ever used as a price source or a cross-check, PAPER needs either
a different ticker or an explicit exclusion. It should not silently become a
symbol that never has a price.

The full map is in `_tools/kse_symbol_map.json`.

Recorded 2026-08-14.

---

## C-26. stock_radar_events.candle_time is one column fed by two clocks and two formats

**الحالة:** مُتحقَّق — بقرار المستخدم 2026-08-15: يُسجَّل ولا يُلمَس.

Two write paths feed the column:

- the bridge candle path: exchange-local (Kuwait) candle stamps, length 19,
  on a strict 30m grid — **all 74 rows in the table today**.
- stock_radar.py:793: `candle_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M")`
  — UTC, length 16, no seconds. **Zero rows so far.**

Measured 2026-08-15: 74/74 rows are length 19 and grid-aligned; the
created_at-minus-candle_time distribution sits at -2h/-1h for 52 rows
(the +03 offset against a UTC created_at), with 20 rows at +18..21h and
2 at +137/138h — old candles alerted after a gap; not investigated further.

Two faults the moment path two fires:

1. The value is not a candle time at all — it is a **capture time written
   into a column named candle_time**. The absence of the real candle stamp
   becomes a confident value: the same disease class as C-17 and the
   avg_daily_value lie.
2. Post-hoc distinction between the paths currently works via
   LENGTH(candle_time) — but only because the fallback happens to use a
   different format. That is a coincidence, not a guarantee; nothing stops
   a future edit aligning the formats and erasing the only marker.

Recorded under the two-path rule in CLAUDE_CONTEXT.md (extension
2026-08-15). Not fixed, deliberately: the fallback has never produced a
row, and the radar loop that reaches it is off (C-21).

---

## C-27. Re-evaluate every learned judgement - the measurement it stands on was broken

**الحالة:** مقرَّر 2026-08-15 بقرار المستخدم — لم يُنفَّذ. الأهم بعد اليوم.

Everything the system "learned" was scored by an evaluator whose own
windows were broken until 2026-08-14/15: the snapshot loop ran on the
wrong hours and skipped Sundays entirely (C-12), the dedup window was
21h with a format quirk on top (fixed 0f04e0f), evaluate_pending
compared a local cutoff to a UTC column, and 78 percent of the "training
data" turned out to be UTC candle stamps misread as pre-open captures
(C-17 correction). On that measurement stand:

- indicator_performance.current_weight - trained on exactly the 41,068
  suspect hit/miss rows;
- get_optimal_thresholds() - the brain-learned state thresholds;
- WHITELIST and BLACKLIST in signal_engine.py - top/bottom 10 by that
  same hit rate. The symptoms that exposed them: KFH blacklisted at 2.8
  percent while being among the most liquid names on the exchange, and
  EQUIPMENT - the one profitable open position, +26 percent - on
  neither list.

**Suspended 2026-08-15, by user decision: both lists** (should_trade
returns True; WHITELIST_MODE off; the sets stay in the source for the
record). **معلّقتان — أساسهما مكسور.** Liquidity is the filter now: the
risk_engine floor (1,000 KWD median session) and the per-position cap.
Confluence is computed at the 14:00 run with simple declared weights
written in backfill_daily_bars.py - deliberately NOT the learned
weights, same reason.

**Precondition (F-3): read `_tools/SCALES.md` first.** It declares every
value that feeds a score - measured range, what the endpoints mean, whether
negative is meaningful, continuous or ordinal. No weight may be derived from
a value whose scale is not listed there. Three of its findings bind C-27
directly:

- **Never take a mean, a z-score or a linear weight on `confluence_score`.**
  It is ordinal in both tables that carry the name, and they are TWO DIFFERENT
  SCALES: `signal_snapshots` holds 50/67/83/100 (floor 50 is a storage filter),
  `stock_radar_daily` holds 0/17/33/50/67/83/100 with 3 legacy rows still on
  the pre-2026-08-15 signed scale. Same name, different meaning, not
  interchangeable.
- **StochK PATTERNS MUST BE RECALIBRATED FROM ZERO, NOT RE-WEIGHTED**
  (user decision 2026-08-16). Measured on the same symbol on the same day,
  bridge vs local: ACICO 2026-08-05 read **26.3** from the bridge and
  **90.0** computed locally. Those are not two estimates of one quantity -
  they fall on opposite sides of every threshold in the system. The atom
  `stoch_gt_80` is ABSENT under one and PRESENT under the other for the
  identical stock and session. So every pattern, atom and threshold
  involving StochK carries a hidden dependency on which era produced it,
  and re-deriving a weight for it would fit a coefficient onto a variable
  whose definition changed underneath. Discard the StochK-derived patterns
  and rebuild them from local-era data only. See `_tools/SCALES.md` for the
  full local-vs-bridge delta table (RSI up to 14%, ADX up to 15%, ATR ~5%,
  StochK up to 242%).
- **`regime_confidence` is 1-3, not 0-100** (n=40,966). Any formula reading it
  as a percentage is off by roughly 33x.
- **`decision_audit.confidence` is a post-gate sample** (80.56-96.41, n=34)
  while the generator reaches 60.0 (`confidence_census`, all examined
  candidates). Fit on the census, never on the audit.

Measured constraints on the inputs (2026-08-16, read-only diagnosis):

- `confluence_score` is ORDINAL, five levels, not continuous: 67,185 rows
  hold exactly 50/67/83/100 plus two stray rows (75, 80). The floor of 50
  is a STORAGE filter (snapshot_signals skips score < 50), not a computed
  minimum. Any re-derivation must treat it as a 5-level ordinal - means,
  z-scores and linear weights over it are category errors.
- `brain_score` is SIGNED (bearish negative, observed to -62.4) while at
  least one consumer (gemini prefilter) weights it as if 0-100 - the 41
  negative final_confidence rows trace to exactly this, via the unclamped
  no-Gemini branch (prefilter x 0.7). Two scales share one variable name;
  C-27 must declare which scale the re-derived weights live on.
- the decision-layer confidence (80.6-96.4, stdev 3.6, never below 80 in
  its life) is a POST-GATE sample - truncated by construction. The
  confidence_census table (golden_engine, 2026-08-16) now records every
  examined candidate; weight re-derivation over confidence waits until
  that census has a few weeks of rows.

Prerequisites before any scoring pass (D-3, D-7, D-9): exclude
`trade_kind = 'void'` AND `entry_basis = 'consolidated_restart'`. A restart
row has `entry_signal_id = NULL` and no originating signal - scoring it
measures a bookkeeping date against a price series and calls the result
evidence: the void-row error arriving by a different door.

The work, in order, when taken up:
1. re-run outcome evaluation over signal_snapshots with the corrected
   windows and clocks - hit/miss/expired recomputed, not trusted;
2. re-derive indicator weights and thresholds from the re-evaluated
   outcomes;
3. re-derive (or retire) the two lists from the same;
4. only then let the learned weights back into confluence.

Until that happens, every number the learning layer hands out is a
conclusion from a broken ruler, and nothing new should be trained on
the existing outcome labels.
