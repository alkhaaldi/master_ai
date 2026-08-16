# PHASE 2 — SECTION G: One source (Yahoo), and the dashboard catch-up

- Date: 2026-08-16
- Plan by: claude.ai | Executors: **Claude Code** (G-1..G-5) · **claude.ai** (G-6)
- Read first: `_tools/SCALES.md`, `_tools/PHASE2_SECTION_F.md`,
  `_tools/mixed_clock_census.md`
- Rules: minimal, backward-compatible, do not break existing endpoints.

## The decision and what it costs

The user has decided: **one price/indicator source — Yahoo (`.KW`)** — and the
Bridge retired if it is a problem. That is a good simplification: the Bridge
needs a PC powered on, a TradingView session, and a second machine on the LAN.
Every one of those is a way to fail silently, and this phase exists because of
silent failures.

But state the cost plainly, because the plan must design against it:

**One source is one point of failure.** Yahoo is free, unauthenticated, has no
SLA, and rate-limits. Proof from today: a probe of 9 requests from the RPi got
`HTTP 429 Too Many Requests` on every one. The current `_from_yahoo` fetches
`range=5d&interval=1d` per symbol; a 132-symbol scan is 132 requests. Single
sourcing without throttling turns a rate limit into a total outage.

So single-source is right **only if** the system degrades loudly. This section
is as much about the failure path as the happy path.

## G-1 — Measure before you commit (BLOCKING)

Do not assume Yahoo serves intraday for `.KW`. **Measure it**, from the RPi,
spaced out to avoid the 429 I hit:

```
for interval in 30m, 60m, 1d:
  for a sample of ~10 symbols across liquidity tiers:
    bars returned, non-null closes, oldest and newest timestamp, and the
    timezone the timestamps arrive in
```

Space requests (1–2s apart), and report the raw table. Three outcomes:

- **30m present and populated** → single source covers both layers.
- **30m present but sparse/null for thin names** → single source for liquid
  names only; the rest are declared `blind`, never interpolated.
- **30m absent** → the 30m layer *ends*. It does not silently become daily.
  `signals.html`'s live tab must say the intraday layer is retired, with the
  reason, rather than showing daily data under a "30m" label. That relabelling
  would be the exact disease this phase removed.

**Report the table and stop.** The rest of G depends on which outcome holds.

---

## G-2 — Compute indicators locally, from Yahoo bars

The Bridge supplied RSI, MACD, EMA, S/R, ATR, StochK, ADX, Volume. All of them
are **derivable from OHLCV** — Yahoo gives OHLCV. Nothing is lost except
TradingView's exact parameterisation.

**Change:**
1. One module — `indicators.py` — computing each from bars. Pure functions,
   no network, no DB.
2. **Declare every scale in `_tools/SCALES.md` as you add it** (F-3 rule):
   RSI 0–100, StochK 0–100, ADX 0–100, MACD unbounded and signed, ATR in fils.
3. **State the parameters explicitly** (RSI 14, MACD 12/26/9, ATR 14, ADX 14)
   and record them next to each stored value. Values computed with different
   parameters are not comparable, and history from the Bridge era was computed
   by TradingView with its own defaults.
4. **Mark the discontinuity.** Add `indicator_source` (`bridge` | `local`) to
   every stored indicator row. Any series that crosses 2026-08-16 has a seam
   in it, and C-27 must be able to see the seam rather than average across it.
   This is the same lesson as `graded_mode` and `entry_basis`.
5. Insufficient bars → return `None`, never a neutral default. F-3/F-4 rules
   apply here from day one: no `rsi or 50`.

**Acceptance:** for a symbol with Bridge history, the locally computed value
and the last Bridge value are compared and the delta reported. Do not assume
they match — report by how much they differ.

## G-3 — Throttle, cache, and a loud circuit breaker

Today's 429 is the design constraint, not a footnote.

**Change:**
1. **Batch where possible.** Yahoo's chart endpoint is per-symbol, but the
   quote endpoint accepts multiple symbols per call. Use it for prices and
   reserve per-symbol chart calls for history.
2. **Throttle**: a shared rate limiter across every caller, with jitter, plus
   exponential backoff on 429. One scan must not be able to burst 132 requests.
3. **Cache**: daily bars change once per session. Store them; do not refetch
   the same bar. The census-style question is "what did we fetch and when",
   and it should be answerable.
4. **Circuit breaker with a witness.** `price_source` already has
   `bridge_circuit_state()` — mirror it for Yahoo: consecutive failures open
   it, `/dashboard/*` reports `source_state` and `source_reason`, and the
   dashboards render `blind` rather than the last good value.
5. **A 429 is not "no data".** It is "we could not ask". Those are different
   states and must not collapse into the same one.

**Acceptance:** a forced 429 storm leaves every dashboard showing `blind` with
the reason, no stale price rendered as current, and `quick_check` red.

---

## G-4 — Retire the Bridge properly

The Bridge is already off by the user's decision. Retiring it means removing
the *dependency*, not deleting the history.

**Change:**
1. Remove Bridge calls from every live path. `bridge_client.py` stays in the
   tree, marked deprecated with the date and the reason.
2. **Keep the historical rows.** Anything the Bridge produced stays, tagged
   `indicator_source='bridge'` per G-2.4.
3. Any config still pointing at `192.168.111.158:8059` is removed or clearly
   marked dead — a dangling endpoint that times out is a silent failure
   waiting to be misread as "no signal".
4. `bridge_circuit_state()` and its dashboards state `retired`, not `down`.
   The difference matters: `down` invites someone to restart it.
5. Search for any code path whose fallback was "Bridge unavailable → use X".
   With the Bridge retired, those branches are now the only path and were
   probably never exercised. `no_gemini` taught us exactly this: **a fallback
   promoted to primary keeps the fallback's looser thresholds.**

**Acceptance:** no live request reaches 8059; `grep` for the address returns
only deprecated markers; and every former fallback branch is listed with its
threshold so the user can see which ones became primary.

## G-5 — Everything that still assumes two sources

Sweep and report before changing:
- `refresh_daily_snapshot()` — the plan says it uses the Bridge API
- `signals.html` 30m tab and `/dashboard/signals`
- `radar_daily_context` and its `daily_context_reason`
- `stock_radar_daily` writers

For each: what it reads, what it will read after G-2, and whether its
staleness vocabulary is the session-based one from Section C.

---

## G-6 — The dashboard catch-up  (claude.ai)

Audited 2026-08-16. Of 20 pages, **two** read the state contract:

```
swing.html      8 refs   updated 15 Aug   ✓
decisions.html  3 refs   updated 16 Aug   ✓
positions.html  4 refs   updated 16 Aug   ✓ (this session)
radar.html      3 refs   file dated 15 Apr — inherited, not updated
system.html     1 ref
the other 15    0 refs   all dated 15 Apr
```

Order, by what the user actually opens:
1. **radar.html** — reads `/dashboard/signals-daily` and `/dashboard/swing`,
   both already on the contract. Frontend-only.
2. **signals.html** — depends on G-1's outcome. If the 30m layer is retired,
   this page must say so on the live tab.
3. **home.html** — the entry point; it should show source state, not a summary
   that outlives its data.
4. The rest are archived; leave them, but **do not let an archived page render
   confident numbers**. Cheapest honest fix: a banner reading "archived page —
   not on the current data contract" rather than 15 rewrites.

Point 4 matters more than it looks. An April-era page still serves numbers to
anyone who opens it, and it has no way to say they are old.

## Order of execution

```
G-1  measure, report, STOP        ← everything else depends on the outcome
G-2  indicators locally           ← the real replacement for the Bridge
G-3  throttle + breaker           ← without this, one source is one outage
G-4  retire the Bridge
G-5  sweep the two-source assumptions
G-6  radar.html, then the rest    ← claude.ai, in parallel from G-2 onward
```

**BUY_NOW stays shadowed throughout.** Every item here changes decision inputs,
and the two-week shadow window started 2026-08-16.

## Report back

The G-1 table first and nothing else. Then, per item: files changed,
validation, what still fails, and anything in this plan that turned out wrong
about the codebase.
