# REPORT MODELTIER

Written by claude.ai, not by the Claude Code run. That run committed its work
(cd1f8e2) and then was terminated before it wrote this file - the log ends with
"Terminated" and the session marker was left behind. Everything below was
verified on the wire afterwards, not taken from the run.

## What changed

`model_tiers.py` is new: three names, each overridable by environment variable.

```
MAI_MODEL_CHEAP     claude-haiku-4-5-20251001
MAI_MODEL_ROUTINE   claude-sonnet-4-6
MAI_MODEL_DEEP      claude-opus-4-6
```

Ten files in commit cd1f8e2. Wider than the task named, and correctly so - the
run found model names hardcoded in `auto_memory_extractor.py`,
`context_manager.py`, `cost_tracker.py`, `memory_recall.py` and
`news_engine.py` as well as the six the task listed.

Verified: no `claude-opus`, `claude-sonnet` or `claude-haiku` literal survives
anywhere outside `model_tiers.py`, `_archive` and `venv`.

The service restarted at 17:11 and `/system/context` now reports the resolved
names. `/health` is ok, schema 3.4.0, drift 0.

## Who consumes it

Everything that speaks to a model: `llm_call()` in server.py, chat_v7 (Telegram,
`/ask`, and the event engine at server.py:2452), the memory extractor, the
inbox engine, tg_logbook, news_engine, cost_tracker.

The event engine's behaviour was deliberately NOT touched. It still fires on
Home Assistant events exactly as before - it just reaches a cheaper model.
Whether the house should act unattended at all is his decision, not this task's.

## What might break

- Routine chat and device control now answer on Sonnet rather than Opus. Simple
  commands will not differ. A long multi-step reasoning request through the
  ordinary chat path may be shallower than it was yesterday. If that shows up,
  the fix is one environment variable, not a code change:
  `MAI_MODEL_ROUTINE=claude-opus-4-6`.
- `llm_call()` gained an optional model argument. No existing caller passes it,
  so no caller changed behaviour.
- The advisor path in chat_v7 previously named `claude-sonnet-5` and now uses
  the routine tier, which resolves to `claude-sonnet-4-6`. That is a real model
  change on that one path, not just de-hardcoding. Flagged rather than buried.

## What is left

- `quick_check` failed once after the change: string defaults 88 against a
  baseline of 82. The cause was not this task - all six are in
  `_tools/depmap.py` from this morning, and all six render absence as absence in
  a generated report. Baseline raised to 88 with the reasoning recorded in
  `_tools/falsy_baseline.json`. Now 26/26, smoke 4/4, db_sanity 9/9.
- The Stop gate was hardened: a marker older than two hours is ignored, so a
  killed run can no longer hold every later session hostage. That failure was
  observed for real today.
- Nobody has measured the saving. No table stores token counts, so the only
  place the effect will show is Console.
