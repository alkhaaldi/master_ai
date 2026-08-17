# SKILLS ADOPTION PLAN

Owner: claude.ai (plan) -> Claude Code (execute)
Date: 2026-08-17
Scope: add Agent Skills to the master_ai repo so Claude Code loads
our own operating rules automatically instead of being told to
read a .md file every session.

## Why

Skill loading model: at session start Claude Code reads ONLY the
frontmatter (name + description, ~100 tokens each) of every
SKILL.md it finds. The body loads only when a task matches.
So a skill is cheaper than CLAUDE.md, which loads every turn.

Our problem is not missing general knowledge. It is that the
agent forgets OUR rules. That is exactly what skills fix.

## Decision

- Add 2 internal skills (written below, full text).
- Add 2 external skills from the community index.
- Add nothing else. More skills = description budget noise.

Location: PROJECT scope, not personal.
  /home/pi/master_ai/.claude/skills/<name>/SKILL.md
Reason: project skills travel with the repo in git; personal
skills (~/.claude/skills/) are not loaded in every context.

## Step 1 - create the directories

    mkdir -p /home/pi/master_ai/.claude/skills/master-ai-backend
    mkdir -p /home/pi/master_ai/.claude/skills/master-ai-dashboard-field

Do NOT gitignore .claude/skills/ - these are meant to be committed.

## Step 2 - skill: master-ai-backend

File: .claude/skills/master-ai-backend/SKILL.md

NOTE before writing: verify which restart entrypoint actually
exists in the repo (ctl.sh restart vs _tools/restart_master_ai.sh)
and keep only the real one in the file below.

```markdown
---
name: master-ai-backend
description: Rules for editing Python in the Master AI FastAPI
  service on the Raspberry Pi. Use for any change to server.py or
  other .py files, DB migrations, pip installs, restarts, or
  deploys. Covers the required verify-then-restart sequence.
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
```

```markdown
## Required sequence after ANY Python change

    python3 _tools/quick_check.py
    python3 _tools/smoke_test.py
    python3 _tools/db_sanity.py      # only if the DB was touched
    git add -A && git commit -m "<what changed>"
    bash _tools/restart_master_ai.sh

Commit BEFORE restart, never after. If quick_check or smoke_test
fails, fix it before committing - do not commit a red state.

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
```

## Step 3 - skill: master-ai-dashboard-field

File: .claude/skills/master-ai-dashboard-field/SKILL.md

NOTE: this skill must not duplicate
`_tools/ADDING_NEW_DASHBOARD_FIELDS.md` - it points at it. If the
two ever disagree, the .md file wins and the skill gets fixed.

```markdown
---
name: master-ai-dashboard-field
description: The full chain for adding or changing a field shown
  on a Master AI dashboard page. Use whenever a new value must
  reach an HTML dashboard page or a Home Assistant sensor -
  endpoint, JSON, configuration.yaml, sensor, page, verification.
---

## The chain - no step is optional

1. Endpoint change (Python, this agent).
2. Test the raw JSON before touching anything downstream.
3. Update `configuration.yaml` if `json_attributes` needs the new
   key. Restart HA if the sensor definition changed.
4. Confirm the `sensor` state in HA actually carries the value.
   Never assume an entity_id - verify it.
5. HTML page change - NOT this agent. claude.ai owns HTML/CSS/JS.
   Stop here and report which page needs the edit.
6. Visual verification on the page.

Reference: `_tools/ADDING_NEW_DASHBOARD_FIELDS.md`

## Truth order

API -> DB -> logs -> sensor states. The dashboard is never the
source of truth. If the page shows a value the endpoint cannot
produce, the page is lying.
```

```markdown
## Data state rule

Four dashboard pages are on the data contract: swing, decisions,
positions, radar. The other 10 market-data pages carry the shared
`datastate-notice.js` banner saying they do not declare their
data state. If you put fresh data on one of those 10, either wire
it to the contract or leave the banner alone - do not quietly
remove the banner.

Known debt (do not "fix" by guessing): positions.html and
radar.html still run April logic and show P&L without
`pnl_valid` or `price_state`. See `_tools/OPEN_ITEMS.md`.
```

## Step 4 - two external skills

Source index: https://github.com/VoltAgent/awesome-agent-skills
(~1500 curated skills; we take exactly two)

1. `trailofbits/modern-python` - modern Python tooling and
   patterns (uv, ruff, pytest). Rationale: server.py keeps
   growing; catch bad patterns before they set.
2. `trailofbits/differential-review` - security-focused review of
   a git diff. Rationale: maps directly onto our "commit before
   restart" rule - review the diff, then commit.

Install: locate the Trail of Bits skills repo, clone it to a temp
dir, and copy ONLY those two skill directories into
`/home/pi/master_ai/.claude/skills/`. Do not copy the whole set.

VERIFY the repo path before cloning rather than trusting this
file - it was written from an index, not from the repo itself.
Deleting the temp clone afterwards is fine.

## Step 5 - verification

1. Start a new Claude Code session in /home/pi/master_ai and run
   `/skills`. All four must be listed.
2. If any skill is missing or does not trigger, run `/doctor` -
   it reports invalid frontmatter and description-budget
   overflow (overflow silently drops keywords).
3. Trigger test - ask, without naming the skill:
   "what do I run after changing server.py?"
   Expected: master-ai-backend loads and the answer is the
   quick_check -> smoke_test -> commit -> restart sequence.
4. Trigger test 2:
   "add a new field to the radar page"
   Expected: master-ai-dashboard-field loads and the agent stops
   at the HTML step and hands it back to claude.ai.
5. Commit:
   `git add .claude/skills && git commit -m "add agent skills"`

No service restart is needed - skills are read by Claude Code,
not by the FastAPI service.

## Explicitly NOT adopted

- Microsoft Azure skills (133) - no Azure in this stack.
- Binance skills - crypto/on-chain, not Boursa Kuwait.
- testmu-ai test-generation skills - quick_check.py and
  smoke_test.py already work. Do not replace working tooling.
- frontend/theme skills - design system is fixed (Navy+Gold) and
  HTML is owned by claude.ai, not Claude Code.

## Follow-up

If a third internal skill is ever needed, the candidate is a
`master-ai-verify` skill - but only if the verify sequence starts
drifting from what master-ai-backend already states. Do not add
it pre-emptively.
