# SCALES — every value that feeds a score or a decision

- Written 2026-08-16 for PHASE2_SECTION_F, F-3. Referenced by C-27's
  preconditions in `_tools/PHASE2_SECTION_C.md`.
- **Every range below is MEASURED against the live DB on 2026-08-16**, not
  read from a docstring. Where the code's claim and the data disagree, both
  are shown — the disagreement is the point.
- Rule this file exists to enforce: *an unlabelled number crossing a function
  boundary is the defect class of this whole phase.* Two clocks in one column,
  two staleness vocabularies, three stops in one record, and
  `final_confidence = −9.73` are all the same shape.

---

## The critical one: `confluence_score` is TWO scales sharing one name

| where | range | distinct | n | shape |
|---|---|---|---|---|
| `signal_snapshots.confluence_score` | 50 … 100 | 6 | 67,185 | **ordinal**, effectively 4 levels (50/67/83/100) + 2 stray rows (75, 80) |
| `stock_radar_daily.confluence_score` | −13 … 100 | 10 | 132 | **ordinal 7-level** 0/17/33/50/67/83/100 + **3 legacy rows on a dead signed scale** (−13, 75, 80) |

- **`signal_snapshots`**: floor of 50 is a **storage filter** —
  `snapshot_signals` skips anything under 50 — not a computed minimum. The
  variable never produced a value below 50 because such values were never
  written, not because they never occurred.
- **`stock_radar_daily`**: the 7 levels are `declared_confluence` in
  `_tools/backfill_daily_bars.py` — `100 × bullish_votes / votes_present`
  over 6 equal declared votes, so the only reachable values are
  0/17/33/50/67/83/100. Before 2026-08-15 this column held a **signed ±100**
  score where negative meant bearish; 3 rows still carry those old values
  (−13, 75, 80) because `declared_confluence` returned nothing for them and
  the row was left untouched. **They are on a different scale from their 129
  neighbours.**
- Direction lives in a separate column (`confluence_direction`:
  bullish 58 / bearish 53 / neutral 21) — the score itself is unsigned now.

**For C-27: never take a mean, a z-score or a linear weight on either
column.** Seven ordinal levels are not a continuous variable, and the two
columns are not interchangeable despite the shared name.

---

## Scores

| name | declared | measured | negative? | shape | notes |
|---|---|---|---|---|---|
| `brain_score` | none | **−62.4 … 66.0** (n=305) | **yes, meaningful** | continuous | `gemini_scanner.py:310`: `min(confluence * 1.2, 100) if confluence else 40`. **Capped above at 100, never below** — that asymmetry is the direct cause of `final_confidence = −9.73`. Fed from the old signed radar confluence. Also note the key it reads is `confluence`, not `confluence_score`. |
| `golden_score` | 0–100 implied by its 0.20 weight | **0.0 … 0.0, one distinct value, n=305** | no | constant | `golden_opps.get(sym, 0)` has **never once resolved**. A fifth of the prefilter weight is a constant zero that drags every score down. Not fixed here — F-3.4 forbids papering over a symptom before its cause is understood. |
| `prefilter_score` | 0–100 by construction | **−13.9 … 46.8** (n=305) | not intended | continuous | Weighted sum of six inputs, two of which break the assumption: `brain_score` can be negative and `golden_score` is always 0. Never observed above 47 — the 70/75 decision thresholds against it have effectively never fired. |
| `fused_score` | 0–100, **clamped** | −13.9 … 49.1 (n=305) | not intended | continuous | `max(0, min(100, …))` clamps the Gemini branch only. The no-Gemini branch (`prefilter × 0.7`) is unclamped, which is where all 41 negative rows came from. |
| `final_confidence` | 0–100 | **−9.73 … 63.5** (n=305) | not intended | continuous | Two formulas: `fused × 0.6 + gemini_conf × 0.4` (Gemini present) or `prefilter × 0.7` (absent, unclamped). |
| `confidence` (decision layer) | 0–100 | `decision_audit` **80.56 … 96.41** (n=34) · `confidence_census` **60.0 … 93.97** (n=27) | no | continuous | `golden_engine.calc_confidence`, explicitly clamped `max(0, min(100, …))`. The audit table's 80-floor is **selection, not generation**: it stores only emitted decisions. The census (all examined candidates, from 2026-08-16) proves the generator reaches 60.0. **A weight derived from the audit sample alone would be fitted on a truncated variable.** |
| `gemini_confidence` | 0–100 | 25.0 … 85.0 (n=173, 132 NULL) | no | continuous | External model output. `structured.get("confidence", 50)` defaults to 50 when absent or non-numeric — an absent value becomes a confident midpoint. |

## Sub-scores inside `calc_confidence` (`golden_engine.py:102`)

All six are normalised to 0–100 before weighting, and the result is clamped:

| input | source range | normalisation |
|---|---|---|
| `match_ratio` | 0–1 | `× 100` |
| `win_rate` | **0–1 fraction** | `(wr − baseline + 0.10) / 0.30 × 100`, clamped 0–100 |
| `baseline_win_rate` | 0–1 fraction, default 0.3 | subtracted from `win_rate` |
| `occurrences` | count ≥ 0 | `log1p(occ) / log1p(50) × 100`, saturates at 50 occurrences |
| `pattern_score` | assumed ≤ 100 | `min(100, …)` — no lower guard |
| `avg_gain_pct` | percent | `/ 12 × 100`, saturates at +12% |
| `align` | discrete {50, 75, 80, 85, 90} | ordinal, used directly |

**`win_rate` is a fraction (0–1) here and a percentage elsewhere** —
`golden_engine.py:639` formats it `{:.0f}%`, i.e. it prints 0.6 as "0%".
Declared, not fixed, per F-3.4.

## Other decision inputs

| name | measured | shape | notes |
|---|---|---|---|
| `regime_confidence` | **1 … 3** (n=40,966) | ordinal, 3 levels | **not 0–100.** Any formula treating it as a percentage is off by ~33×. |
| `data_quality` | 60 … 85 (n=39) | continuous 0–100 | |
| `rr_ratio` | 1.78 … 24.85 (n=39) | ratio, unbounded above | not a score; never normalise it into a 0–100 blend without saying so |
| `strategy_ev` | 2.25 … 15.5 (n=39) | expected value, unbounded | same |
| `confidence` in `signal_reviews` | 80.56 … 96.41 (n=31) | continuous | inherited from `decision_audit`; same truncation |
| `liq_value_kwd` | KWD/session | continuous | median-derived (`liq_vol × price ÷ 1000`); **fils × shares ÷ 1000 = KWD** — the unit slip that made a 50,000 threshold behave as 50 |
| prices | **fils**, integers | continuous | 1 KWD = 1000 fils. Every stored price in this system is fils; every value is KWD |

---

## Locally computed indicators (G-2, `indicators.py`, from 2026-08-16)

Computed from Yahoo OHLCV. Every one returns
`{value, bars_used, coverage_pct, params, reason}` - never a bare number,
never a neutral default when the data is insufficient.

| name | range | endpoints mean | negative? | shape | params |
|---|---|---|---|---|---|
| `rsi` | 0-100 | 0 = pure loss run, 100 = pure gain run, **50 is a real reading** | no | continuous | RSI 14, Wilder |
| `stoch_k` | 0-100 | position of close within the window's high-low range | no | continuous | %K 14 |
| `adx` | 0-100 | trend STRENGTH only - **carries no direction** | no | continuous | ADX 14, Wilder |
| `macd` / `signal` / `histogram` | unbounded | **signed**; sign is the direction | **yes, meaningful** | continuous | 12/26/9 |
| `ema_9`, `ema_21` | price domain | in **fils**, like every price here | no | continuous | EMA 9 / EMA 21 |
| `atr` | >= 0 | average true range in **fils** | no | continuous | ATR 14, Wilder |
| `support` / `resistance` | price domain | rolling extremes in **fils**, newest bar excluded | no | continuous | 20-bar rolling |

Two gates every one of them passes through:

- **`bar_complete`** - the forming bar is dropped before anything is
  computed. Yahoo's newest intraday element is stamped off the interval
  grid (G-1 measured 09:45Z on a 30m series) and its close and volume
  still move. An indicator computed on it changes retroactively.
- **`coverage_pct` >= 80** - a thin name whose 30m grid is 65% non-null
  (URC, measured) gets `None` and a reason, not a number computed across
  holes. `bars_used` and `coverage_pct` are stored beside every value so
  a reader can judge the evidence, not just the answer.

**`indicator_source`** (`bridge` | `local`) marks the 2026-08-16 seam.
Values either side of it are NOT comparable and must never be averaged
across - measured deltas below.

### Measured: local vs bridge, same symbol, same date

| symbol | date | RSI | ADX | StochK | ATR |
|---|---|---|---|---|---|
| URC | 2026-08-13 | -3.1% | +10.2% | **+44.6%** | +3.3% |
| RASIYAT | 2026-08-05 | +0.1% | +10.7% | -2.5% | +5.3% |
| ACICO | 2026-08-05 | +9.3% | -14.9% | **+242%** | -0.3% |
| URC | 2026-07-08 | -14.0% | -2.2% | **-48.1%** | -0.2% |
| ALFTAQA | 2026-07-08 | -13.6% | -4.2% | **-90.4%** | -2.5% |

They do NOT match, and the pattern is informative rather than random:

- **ATR agrees within ~5%** and **ADX within ~15%** - long-window Wilder
  averages are dominated by the same price history whoever computes them.
- **RSI diverges up to 14%** - seeding and smoothing choices matter.
- **StochK diverges wildly, up to 242%** - a 14-bar window oscillator is
  dominated by which bars are in the window, so any difference in the
  bar set or the as-of instant moves it enormously.

The practical consequence, and the reason `indicator_source` exists: a
StochK of 26.3 from the bridge and 90.0 computed locally are not two
measurements of one thing. Any threshold tuned on bridge-era values is
not transferable, and C-27 must treat the seam as a break in the series.

## Rules for anything that consumes these

1. **State the scale at the point of use.** A comment naming the range and
   whether negative is meaningful, next to the line that reads the value.
2. **Never mean/z-score/linear-weight an ordinal.** `confluence_score` (both
   columns), `regime_confidence`, and `align` are ordinal.
3. **A truncated sample is not a population.** `decision_audit.confidence` is
   post-gate. Wait for `confidence_census`.
4. **Do not clamp to hide a symptom** (F-3.4). The uncapped branch is what
   revealed 41 negative rows; capping it first would have taught us nothing.
   Clamp only after the cause is written down here.
5. **Units travel with values.** fils vs KWD, fraction vs percent, sessions vs
   hours. Every one of those pairs has already produced a live fault in this
   project.
