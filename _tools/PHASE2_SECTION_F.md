# PHASE 2 — SECTION F: Unblocking C-27, and protecting what we built

- Date: 2026-08-16
- Plan by: claude.ai | Executor: **Claude Code (RPi)** unless noted
- Read first: `_tools/PHASE2_SECTION_D.md`, `_tools/PHASE2_SECTION_E.md`,
  `_tools/mixed_clock_census.md`
- Rules: minimal, backward-compatible, do not break existing endpoints.
- **Out of scope by the user's decision:** public exposure of the tunnel.
  Do not change Cloudflare or auth settings in this section.

## Where we are

Sections C/D/E fixed how the system *reports*. Section F is about what it
*knows*. Five silent faults surfaced on 2026-08-15/16, and the pattern behind
four of them is one thing: **a value crossing a boundary without declaring its
unit or its scale.**

- two clocks in one column (`decision_time` local vs `user_confirmed_at` UTC)
- two vocabularies for staleness (`stale_1d` days vs session-based states)
- three stop levels in one record
- `brain_score` on ±100 consumed by a formula expecting 0–100
- and a truncated sample read as a population (confidence)

C-27 cannot start until the inputs it will learn from declare themselves.

## Priority order

1. **F-1** protect the data (backup) — nothing else survives its loss
2. **F-2** the Brain — its output carries weight 0.30 in live decisions
3. **F-3** declare the scales — the precondition C-27 actually needs
4. **F-4** unify targets — the last E-2 leftover
5. **F-5** census maturity — time, not work
6. **F-6** small open questions

---

## F-1 — Back up `life.db` to the NAS (do this first)

Everything built on 2026-08-15/16 lives on an SD card: the trade journal,
`decision_audit`, `signal_reviews`, `stock_radar_daily`, and the brand-new
`confidence_census` that C-27 is now waiting on. SD cards fail without
warning. There is currently no off-device copy.

**Change:**
1. Pick or create a NAS share for backups. **Do not reuse the `Quran` share**
   — that one is mounted read-only by Music Assistant and is a media share.
   Confirm the target path with the user before writing to it.
2. Back up with `sqlite3 .backup` (or `VACUUM INTO`), **never `cp`** — copying
   a live SQLite file mid-write produces a corrupt snapshot that restores
   silently and fails later. That failure mode is exactly this project's
   disease in backup form.
3. Daily, after the close job. Keep the last 14. Gzip.
4. Log a success or failure line at INFO. Now that logging works (Section E),
   a silent backup failure is no longer acceptable.
5. Add `last_backup_at` and `backup_age_hours` somewhere queryable, so a
   stopped backup announces itself instead of being discovered later.
6. **Verify a restore once.** A backup never restored is a hope, not a backup.
   Restore the newest file to a scratch path and run `PRAGMA integrity_check`
   plus a row count against the live DB. Report both numbers.

**Acceptance:** a gzipped backup exists on the NAS, `backup_age_hours` reads
under 24, and the restore check reports `ok` with matching row counts.

---

## F-2 — The Brain is frozen, and its output carries weight in live decisions

Evidence from 2026-08-15:

```
server.log : "Brain reload failed: name '_ensure_memory_table' is not defined"  x38
/api/brain/stats : total_observations 47 · recent_24h 0 · oldest 170 days
                   staleness: fresh 0 · recent 0 · old 47
gemini formula   : brain_score weight = 0.30
```

So a component that has recorded nothing new in months, and throws a
`NameError` on every boot, contributes 30% of a decision score. It stayed
invisible because the log line sat below the root logger threshold.

**Change:**
1. Fix the `NameError` — `_ensure_memory_table` is referenced but not defined
   or not imported. Small fix; the value is in what it unblocks.
2. Then answer, with numbers, before changing anything else:
   - Did observation recording stop *because* of this error, or separately?
   - 47 observations, all `old`, 0 in 24h — since when? Give the last write
     date per scope (`global` / `stock` / `device`).
   - **Does C-27 read from `brain_observations`, or from another source?**
     This decides whether C-27 is still blocked on the Brain at all.
3. Do not backfill or synthesise observations. If the Brain learned nothing
   for 170 days, that gap is a fact C-27 must see, not a hole to fill.

**Acceptance:** clean boot with no reload failure, `recent_24h` moves above 0
after a session, and the three questions above are answered in the report.

---

## F-3 — Declare every scale before C-27 derives anything from it

The `final_confidence = −9.73` bug was not an arithmetic slip. `brain_score`
lives on ±100 where negative means bearish; the prefilter formula consumed it
as if it were 0–100, weighted 0.30, on an uncapped branch. Two scales, one
name — the same shape as the two clocks and the two staleness vocabularies.

C-27 is about to combine several of these into weights. If the scales are not
declared, it will produce numbers nobody can check — which is the exact
condition we spent two days removing.

**Change:**
1. Write `_tools/SCALES.md` listing every value that feeds a score or a
   decision, and for each: name, range, what the endpoints mean, whether
   negative is meaningful, and whether it is continuous or ordinal. Known so
   far:
   - `brain_score` — ±100, sign carries direction
   - `confluence_score` — ordinal, 5 levels (50/67/83/100 + 2 outliers in
     67,185 rows); its floor of 50 is a **storage filter** in
     `snapshot_signals`, not a computed minimum
   - `confidence` — 0–100, generator confirmed to reach 60.0
   - `regime_confidence` — 1–3, not 0–100
   - `pattern_score`, `entry_score`, `win_rate`, `baseline_wr` — to be filled
2. Every formula that consumes one of these asserts or documents the scale at
   the point of use. An unlabelled number crossing a function boundary is the
   defect class of this whole phase.
3. **Never take a mean or fit a linear weight on `confluence_score`** — five
   ordinal levels are not a continuous variable. Record this in C-27's
   requirements.
4. Do not clamp anything to fix a symptom. The uncapped branch revealed the
   bug; capping it would have hidden 41 rows and taught us nothing.

**Acceptance:** `_tools/SCALES.md` exists and is referenced from C-27's
preconditions; no formula consumes a value whose scale is not listed there.

---

## F-4 — Unify targets, as E-2 unified stops

E-2 collapsed three stop levels into `chosen_plan.stop` with a `stop_source`.
Targets were left behind, and the payload still ships two answers:

```
chosen_plan : target1 211.906 · target2 246.186 · rr 1.90
trade_plan  : target_1 208.938 · target_2 216.407 · rr 2.55
```

30 fils apart on target 2, for the same symbol, in the same record. The
decisions page currently renders `chosen_plan` and prints a warning when it
detects the divergence — a frontend patch over a payload problem.

**Change:** `chosen_plan.target1/target2/rr` are authoritative. Move
`trade_plan` into a diagnostic `plan_candidates` block, mirroring
`stop_candidates`. Emit `plan_source` alongside `stop_source`.

**Acceptance:** one target set per record; the page's divergence warning stops
firing on its own, without touching the page.

## F-5 — Census maturity (time, not work)

`confidence_census` went live 2026-08-16 and already proved the generator
reaches 60.0 with 5 of 23 candidates under 80 in a single scan. It needs
sessions, not code. Review after ~4 weeks of trading days and report: n,
range, distribution by decile, and the emitted/not-emitted split.

C-27 stays blocked until then, plus F-2's third question and F-3.

## F-6 — Open oddities (not urgent, do not fix blind)

1. **Eleven candidates sitting on exactly `80.0`** in one scan. A repeated
   round number across many symbols suggests a floor, a default, or a clamp.
   Investigate and report before touching it.
2. **D-5 counter review** — due 2026-08-22. Decide `/dashboard/radar`'s fate
   on the evidence, not on assumption.
3. `signal_reviews` still carries 6 `no_data` rows from before the Yahoo
   source. Now that history is available, can they be graded?

## Verification (all items)

```
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
python3 _tools/db_sanity.py
git add <explicit paths only — never -A in this repo>
git commit -m "Phase 2 Section F: backup, brain fix, scale declarations"
bash _tools/restart_master_ai.sh
```

## Report back

Files changed, validation output, what still fails, anything in this plan that
turned out wrong about the codebase — and the three F-2 questions answered
with dates and counts, not summaries.
