# G-4 / G-5 — what the Bridge's retirement promoted, and what still assumes two sources

- Written 2026-08-16 (PHASE2_SECTION_G, G-4.5 + G-5).
- **Survey. Nothing in this file has been changed** except where noted as
  done in G-4 - the point is that the user sees which loose branch became
  the only branch before anything acts on it.

## The lesson this file exists for

> *a fallback promoted to primary keeps the fallback's looser thresholds.*

The `no_gemini` branch proved it on 2026-08-16: it fired five times in one
scan at threshold 70 while the confirmed branch requires 75. It had never
fired before because a constant-zero `golden_score` held a fifth of the
weight down. Retiring the Bridge does the same thing to every branch below.

## A. Fallback branches that are now the ONLY branch

| # | site | condition that used to select it | threshold now in force | confirmed-path threshold it replaced |
|---|---|---|---|---|
| 1 | `gemini_scanner._fuse_scores` no-Gemini branch | `if not gemini_result` | **BUY 70 / SELL 30**, `prefilter x 0.7`, **unclamped** | fused branch: **75** + `gemini_is_buy` + `brain_score >= 55` |
| 2 | `gemini_scanner._prefilter_universe` snapshot fallback | `if len(sym_data) < 20` | **always** - the bridge never fills `sym_data` now | bridge multi-analysis, 120s timeout |
| 3 | `signal_engine.build_signals` snapshot universe | added 2026-08-15 (C-10 shape) | **always** - bridge only enriched | bridge symbol set |
| 4 | `signal_engine._assign_trade_state` | `if symbol in _get_bridge_symbols_set()` -> `manage` | **never true**: the bridge cache is never populated, so an open position can only ever be `entered` in the signals list | `manage` was the bridge-present state |
| 5 | `price_source` source order | `bridge -> yahoo -> db` | **`yahoo -> db`** (done in G-4) | bridge first |

**#1 is the live risk**: it is looser in three ways at once - lower bar (70
vs 75), no second opinion required, and no clamp on the branch. It is also
the only branch that can currently reach BUY_NOW. This is exactly why
BUY_NOW stays shadowed; the shadow rows are the evidence for whether 70 is
defensible without confirmation.

**#4 is a silent semantic change**, not a threshold: `manage` is now
unreachable in that function. `swing`'s open positions were already moved
off it (they key on `price_state == "live"`), so no dashboard is wrong -
but any future reader of `trade_state` should know `manage` is dead there.

## B. Still assuming two sources (G-5 sweep)

| site | reads today | after G-2 | staleness vocabulary |
|---|---|---|---|
| `stock_radar.refresh_daily_snapshot` (stock_radar.py:1282) | Bridge `/analysis` per symbol (stock_radar.py:753) | **must move to `yahoo_gate.chart` + `indicators.compute_all`**; unconverted | its own (`market_was_open` guard, correct in spirit) |
| `stock_radar.py:1249` bridge probe | `BRIDGE_URL/health` | dead call; unconverted | n/a |
| `kse_data_collector.collect_daily_bars` (:138) | Bridge `/multi-analysis` | superseded by `_tools/backfill_daily_bars.py`, which already fills `daily_bars` from Yahoo | run-level, in `data_fetch_runs` |
| `/dashboard/signals` (dashboard_api:1779) | `build_signals()` | already on the snapshot universe | session-based via `/dashboard/swing` fields |
| `/dashboard/signals-30m` (dashboard_api:1919) | `build_signals_30m()` -> bridge only | **returns nothing now.** G-1 proved Yahoo serves 30m for `.KW` (41 bars, 5d), so this CAN be rebuilt locally - but until it is, the tab must say the intraday layer is unavailable rather than render daily data under a 30m label | none |
| `radar_daily_context` / `daily_context_reason` | `stock_radar_daily` | on the session vocabulary already (D-4) | **session-based, correct** |
| `stock_radar_daily` writers | `refresh_daily_snapshot` (bridge) **and** `backfill_daily_bars` (Yahoo) | two writers, one table - the two-writer rule from `mixed_clock_census.md` applies and both must be audited together before either is trusted | mixed |

The last row is the one to act on next: **two writers, one table**, which is
the exact shape that produced `candle_time`'s two clocks and
`tasks.updated_at`'s two clocks. `backfill_daily_bars` now writes
`indicator_source='local'` with `bars_used`/`coverage_pct`;
`refresh_daily_snapshot` writes none of that and would leave rows that look
local but are not.

## C. Config

`.env` holds `BRIDGE_URL=http://192.168.111.214:8059`. Left in place
deliberately: `bridge_client.py` still reads it and the module is kept for
history. No live path calls it - the health probe in `dashboard_api` and the
S/R side-trip were removed in G-4, and `price_source` no longer lists bridge
in `SOURCE_ORDER`. The plan mentioned `.158`; the actual configured address
is `.214`, which is the user's own Windows PC.
