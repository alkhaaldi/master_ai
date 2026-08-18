# REPORT — WORKFLOW_SETUP

Date: 2026-08-18

## What was changed

| File | Change |
|------|--------|
| `CLAUDE.md` | Added item 7 to "First Step — Every Session": pointer to `_tools/WORKFLOW.md` |
| `_tools/WORKFLOW.md` | Committed (was untracked) |
| `_tools/TASK_TELEGRAM_ALERTS.md` | Committed (was untracked) |
| `_tools/REPORT_TELEGRAM_ALERTS.md` | Committed (was untracked) |
| `_tools/ACTIVE_DEVICE_DEFINITION.md` | Committed (was untracked) — listed as "any other untracked _tools/*.md" |

## Commit hash

`8ff28be`

## What was left out (intentionally)

The following modified files were present in the working tree and were NOT staged or committed, per the "never git add -A" rule and the explicit constraint to not commit `avg_volume_fill.json` or touch code outside CLAUDE.md:

- `_tools/OPEN_ITEMS.md` — modified but not listed in the instruction
- `_tools/run_witness.py` — code file, out of scope
- `dashboard_api.py` — code file, out of scope
- `signal_review.py` — code file, out of scope
- `www/trading/home-control.html` — UI file, out of scope
- `www/trading/home.html` — UI file, out of scope

`avg_volume_fill.json` was not present in git status at all (untracked data file); it did not need to be excluded explicitly.

## Anything in the instruction that turned out wrong

Nothing was factually wrong. One minor gap: the instruction said "any other untracked _tools/*.md" without listing them by name. `_tools/ACTIVE_DEVICE_DEFINITION.md` and `_tools/REPORT_TELEGRAM_ALERTS.md` matched that criterion and were included. If either should have been excluded, they can be removed in a follow-up commit.

## Service

Not restarted. No code was changed. Market is open — constraint respected.
