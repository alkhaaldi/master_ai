---
name: master-ai-backend
description: Rules for editing Python in the Master AI FastAPI service on the Raspberry Pi. Use for any change to server.py or other .py files, DB migrations, pip installs, restarts, or deploys. Covers the required verify-then-restart sequence.
---

## Non-negotiable rules

1. Edits are minimal and backward-compatible. Never break an
   existing endpoint. No full rewrite unless explicitly asked.
2. Never append to a Python file. Edit in place or use
   `_tools/patchers/apply_text_patch.py`.
3. Never invent a new tooling path when `_tools/` already has one.
4. Never hardcode secrets. API key comes from `~/.master_ai_key`,
   HA token from `~/.ha_token`.
5. Never swallow an error. Every failure path must leave a log
   line or a `reason` field the dashboard can display. Absence of
   data is a state, not a value.
6. Deployment is git deploy only.

## Required sequence after ANY Python change

    python3 _tools/quick_check.py
    python3 _tools/smoke_test.py
    python3 _tools/db_sanity.py      # only if the DB was touched
    git status --short          # look BEFORE you stage
    git add <only the paths you changed>
    git commit -m "<what changed>"
    bash _tools/restart_master_ai.sh

`git status --short` is not optional. The tree regularly
carries unrelated in-flight work. Staging blind is how that
work ends up in someone else's commit.

Commit BEFORE restart, never after. If quick_check or smoke_test
fails, fix it before committing - do not commit a red state.

### Never `git add -A` in this repo

This working tree normally carries several modified-but-uncommitted
files that belong to someone else's unfinished work. `git add -A`
sweeps them into your commit and the commit message then lies about
what changed - that is what happened in commit `651b154`, whose
message claimed "archive 58 scripts" while it actually deleted two
live modules.

Run `git status --short` first and stage only the paths you touched.
If unexplained modified files are present, say so instead of
committing them.

### Which restart entrypoint

`bash _tools/restart_master_ai.sh` is the one an agent runs. It
restarts `master-ai.service` and then verifies
`http://localhost:9000/health` actually answers.

`ctl.sh restart` also exists and is real, but it is the entrypoint
Home Assistant calls from `shell_commands`. Do not use it as the
post-change restart - it does no health check.

## Price and data rules

- Never return a bare price. Use `price_source.get_price` /
  `get_quote`, which always return price + as_of + state.
- Yahoo Finance (.KW, values in fils/KWF) is the sole price and
  history source. The TradingView Bridge is RETIRED - bridge
  fetchers return empty and report `retired`, not `down`.
- Any scheduled or automatic caller of the Bridge is a bug.
- One Yahoo request per symbol. The multi-symbol quote endpoint
  returns 401 and must not be used.

## Read before a non-trivial change

- `_tools/OPERATIONAL_ACCESS_MATRIX.md`
- `_tools/OPEN_ITEMS.md`  (the single list of remaining work)
- `_tools/SCALES.md`      (declared scale of every value)

## Audit rule

Any code audit maps how the project is actually built
(architecture and data flows) FIRST, then fixes. Never fix off a
static scan alone.
