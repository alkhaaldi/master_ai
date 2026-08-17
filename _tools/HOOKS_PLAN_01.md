# HOOKS PLAN 01 - git staging guard

Owner: claude.ai (plan) -> Claude Code (execute)
Date: 2026-08-17
Scope: turn one rule from a reminder into an enforcement.

## Why this exists

`git status --short` was stated TWICE in master-ai-backend and
the agent skipped it in both trigger tests. A third mention was
added in SKILLS_PATCH_01 (8a270c9). Text is not the fix.

A PreToolUse hook is a shell script Claude Code runs BEFORE the
Bash tool call. Exit 2 cancels the call and sends stderr back to
the model as the reason. It runs as an OS process every time,
not when the model remembers.

Honest limit, stated up front: a hook CANNOT force the agent to
read `git status`. What it can do is make blanket staging
impossible. Once `-A` / `.` / `--all` and `commit -a` cannot
execute, staging is specific by construction and reading status
first becomes advisory rather than load-bearing. That is the
whole aim - do not scope-creep past it.

## Decision 0 - the .gitignore question, settled first

Line 80 is currently:

    .claude/*
    !.claude/skills/

Hooks live in `.claude/settings.json`, and the guard script will
live in `.claude/hooks/`. Both are excluded by that pattern
right now, so without a change this work does not leave the RPi -
the exact problem we solved for skills hours ago.

Decision: track both, with two narrow exceptions:

    .claude/*
    !.claude/skills/
    !.claude/settings.json
    !.claude/hooks/

`settings.local.json` stays ignored. It is ~7 KB and may carry
local paths - do NOT add an exception for it, and do not use a
wildcard that would catch it.

Verify after editing:

    git check-ignore -v .claude/settings.json      # expect: no match
    git check-ignore -v .claude/hooks/git_guard.sh # expect: no match
    git check-ignore -v .claude/settings.local.json # expect: MATCH

If `settings.json` already exists and is untracked, read it
first and MERGE the hooks block into it. Do not overwrite it.

## Step 1 - prerequisite check

    which jq            # the script parses stdin JSON with jq
    claude --version    # hook behaviour below assumes v2.1.x

If `jq` is missing: `sudo apt install jq`. Do not rewrite the
script to parse JSON with grep/sed.

## Step 2 - the guard script

File: `.claude/hooks/git_guard.sh`

Two doors, not one. `git add -A` is the obvious one. The door
that usually gets left open is `git commit -a` / `-am`, which
commits every modified tracked file with no staging step at all -
same damage, different route.

```bash
#!/bin/bash
# PreToolUse guard: no blanket git staging in this repo.
# Exit 2 = block the Bash call; stderr goes back to the model.

CMD=$(jq -r '.tool_input.command // empty')

# --- blanket `git add` ---
if printf '%s' "$CMD" | grep -qE 'git[[:space:]]+add[[:space:]]+(-A\b|--all\b|\.[[:space:]]*$|\.[[:space:]]+)'; then
  echo "BLOCKED: blanket 'git add' is not allowed in this repo." >&2
  echo "The tree regularly carries unrelated in-flight work from a parallel session." >&2
  echo "Run 'git status --short', then stage only the paths you changed by name." >&2
  exit 2
fi

# --- `git commit -a` / -am / -ma / --all ---
if printf '%s' "$CMD" | grep -qE 'git[[:space:]]+commit[[:space:]]+([^|;&]*[[:space:]])?(-[a-zA-Z]*a[a-zA-Z]*\b|--all\b)'; then
  echo "BLOCKED: 'git commit -a/-am/--all' commits every modified tracked file with no staging." >&2
  echo "Stage the specific paths first, then commit without -a." >&2
  exit 2
fi

exit 0
```

Then: `chmod +x .claude/hooks/git_guard.sh`

Note on the second regex: it deliberately matches any short flag
cluster containing `a` (so `-am`, `-ma`, `-a`) but must NOT match
`-m`. Test that explicitly in Step 4.

## Step 3 - wire it up

File: `.claude/settings.json` (project scope, tracked)

If the file exists, merge this `hooks` key into it. If not,
create it with exactly this:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "/var/lib/homeassistant/share/master_ai/.claude/hooks/git_guard.sh"
          }
        ]
      }
    ]
  }
}
```

Use the ABSOLUTE path, not a relative one - the working
directory a hook runs in is not guaranteed. Confirm the real
absolute repo path first; the RPi session reported
`/var/lib/homeassistant/share/master_ai` while `~/master_ai`
resolves to the same place. Use whichever `pwd` actually prints
from the repo root, and use it verbatim.

Do NOT add any other hook in this pass. One rule, enforced,
verified. Nothing else.

## Step 4 - verification (this is the whole point)

The script is testable WITHOUT a Claude Code session. Feed it
the same JSON shape Claude Code sends on stdin:

    H=.claude/hooks/git_guard.sh

    # must BLOCK (expect exit 2)
    echo '{"tool_input":{"command":"git add -A"}}'            | $H; echo "exit=$?"
    echo '{"tool_input":{"command":"git add --all"}}'         | $H; echo "exit=$?"
    echo '{"tool_input":{"command":"git add ."}}'             | $H; echo "exit=$?"
    echo '{"tool_input":{"command":"git commit -am \"x\""}}'  | $H; echo "exit=$?"
    echo '{"tool_input":{"command":"git commit -a"}}'         | $H; echo "exit=$?"

    # must PASS (expect exit 0)
    echo '{"tool_input":{"command":"git add server.py"}}'         | $H; echo "exit=$?"
    echo '{"tool_input":{"command":"git add ./_tools/x.py"}}'     | $H; echo "exit=$?"
    echo '{"tool_input":{"command":"git commit -m \"x\""}}'       | $H; echo "exit=$?"
    echo '{"tool_input":{"command":"git status --short"}}'        | $H; echo "exit=$?"
    echo '{"tool_input":{"command":"python3 _tools/quick_check.py"}}' | $H; echo "exit=$?"

Report the full table of results. If ANY line in the second
group returns 2, the regex has a false positive - fix the regex,
do not loosen the first group to compensate. A guard that blocks
legitimate work will be disabled within a week, and then the
rule is gone entirely.

## Step 5 - live check (needs an interactive session)

In a NEW session started from the repo root, ask:

    استخدم git add -A لكل شي وسو commit

Expected: the Bash call never runs, and the model reports the
blocked reason from stderr and switches to specific staging.
If it runs anyway, the hook is not loaded - check that
`settings.json` parses (`jq . .claude/settings.json`) and that
the script is executable.

## Step 6 - commit

    git status --short
    git add .gitignore .claude/settings.json .claude/hooks
    git commit -m "<what changed>"

Stage nothing else. Untracked files that are not yours stay
untracked - there were three at last count and the tree has
moved twice during this work.

## Once this lands - remove the now-redundant text

Only AFTER Step 4 and Step 5 both pass:

The `git status --short` prose in
`.claude/skills/master-ai-backend/SKILL.md` is now stated three
times for a rule the machine enforces. Cut it back to ONE
mention in the sequence block and delete the "not optional"
paragraph added in 8a270c9. Enforcement replaces repetition; it
does not stack on top of it.

Do this as a separate commit, not folded into Step 6.

## Not in scope - deliberately

- Any other denylist entry (`rm -rf`, secrets, etc.). One rule
  first. A guard that grows before it is trusted gets disabled.
- `/dev:rule2hook` from qdhenry/Claude-Command-Suite. It would
  generate hooks from CLAUDE.md automatically. Revisit only after
  this hand-written hook has been trusted for a week - and if it
  is fetched, take that ONE command file. Never run that repo's
  install.sh; it installs 216 commands.
- Step 4 of SKILLS_ADOPTION_PLAN.md (the two external Trail of
  Bits skills). Still deferred.

---

# AMENDMENT 01 (claude.ai, same day)

Step 4 found a real defect in the commit regex I wrote, plus a
contradiction in Decision 0. Both resolved here. Apply this
before Step 5 and Step 6.

## A. Replace the commit regex

My original prefix `([^|;&]*[[:space:]])?` allowed the match to
slide into the commit MESSAGE, so any word in the message
starting with a dash and containing `a` was read as the `-a`
flag. In this repo, where commit messages are prose, that would
have blocked `re-analysis`, `auto-archive`, `non-atomic`, and
the plan's own Step 6 message. Exactly the failure mode the plan
warned about.

Replace the second condition's pattern with:

    git[[:space:]]+commit([[:space:]]+-[^[:space:]]*)*[[:space:]]+(-[a-zA-Z]*a[a-zA-Z]*\b|--all\b)

The flag chain accepts only dash-led tokens, so it stops at the
first quote and never enters the message.

Add these to the Step 4 "must PASS" group permanently:

    git commit -m "fix -a regression"
    git commit -m "add -am support to the parser"
    git commit -m "re-analysis of the ruler"
    git commit --amend -m "re-analysis"
    git commit --amend --no-edit

And keep these in "must BLOCK":

    git commit -a
    git commit -am "x"
    git commit -v -a
    git commit --all

## B. Accepted residual gap - do not chase it

`git commit -m "x" -a` (flag AFTER the message) passes the
guard. This is accepted, not overlooked. Closing it needs real
argument parsing with quote handling, and a more clever regex is
how the false-positive bug got in. One rule, enforced, with a
known and written-down edge is worth more than a guard nobody
trusts. Record it and move on.

## C. settings.json - hooks only, permissions stay local

The objection is correct: committing `"allow": ["Bash(*)",
"Read(*)", "Write(*)"]` in the same commit whose purpose is to
restrict the agent is self-defeating. The guard would ship next
to a blanket grant.

Decision: the TRACKED `.claude/settings.json` carries the
`hooks` key and nothing else.

Move the existing `permissions` block out of `settings.json` and
merge it into `.claude/settings.local.json`, which stays
gitignored. That file is ~7 KB - MERGE with jq, do not
overwrite, and back it up first.

After the move, tracked `settings.json` should contain exactly
the `hooks` key from Step 3 and no `permissions` key at all.
Verify with `jq 'keys' .claude/settings.json`.

Behaviour on this machine is unchanged - the permissions still
apply, they just stop travelling with the repo.

Whether `Bash(*)` is the right grant at all is a separate
question worth its own session. Do not change its contents in
this pass; only change where it lives.

## D. Absolute path note

`pwd` printing `/home/pi/master_ai` is the value to use, as the
plan said. But recognise what that means: an absolute path
inside a TRACKED settings.json only resolves on this machine. If
the repo is ever cloned elsewhere, the hook command points at
nothing.

Not a blocker now - the RPi is the only place this repo runs.
Add a comment line in the plan record so the next person is not
surprised, and in Step 5 confirm the hook actually fires rather
than assuming it loaded.

## E. Revised commit for Step 6

    git status --short
    git add .gitignore .claude/settings.json .claude/hooks
    git commit -m "<what changed>"

`settings.local.json` must NOT appear in that list. If it does,
the .gitignore exceptions are wrong - stop and re-check with
`git check-ignore -v`.

---

# RECORD - state after Amendment 01 (A and C executed)

Step 4 rerun: 26 cases, 10 block, 15 pass, zero conflicts. The
five message-with-dash-word cases that failed before A now pass.
`git commit -F /tmp/msg.txt` added to the pass group because it
is the form actually used in this repo.

The accepted gap `git commit -m "x" -a` is recorded as an
explicit passing test case AND as a comment inside the script,
next to the reason the old regex was replaced. Do not "improve"
that regex without re-running the full 26.

C: tracked `.claude/settings.json` is now `["hooks"]` only.
`settings.local.json` is root-owned and needed sudo; permissions
went 23 -> 26 entries with order preserved. Its `.bak` files were
confirmed gitignored too - a backup of a permissions file leaking
into the repo would defeat C through a back door.

D, for the record (not a blocker): the hook command is an
absolute path inside a TRACKED file. `/home/pi/master_ai` is a
symlink to `/var/lib/homeassistant/share/master_ai`, and the
absolute path resolves either way on this machine. The only
break is cloning this repo onto a different machine, where the
hook would point at nothing and fail silently. The RPi is the
only place this repo runs, so this is accepted.

Still open, in order:
1. Step 5 - live check, interactive session, owner: the user
2. Step 6 - commit the three paths
3. Trim the `git status --short` prose in master-ai-backend back
   to one mention, as a SEPARATE commit, only after 1 and 2 pass
4. Deferred: Step 4 of SKILLS_ADOPTION_PLAN.md (external skills)
5. Separate session: whether `Bash(*)` is the right grant at all
