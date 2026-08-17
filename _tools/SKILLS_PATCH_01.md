# SKILLS PATCH 01

Owner: claude.ai (plan) -> Claude Code (execute)
Date: 2026-08-17
Scope: two gaps found by the Aug 17 trigger tests. Both skills
passed; these are corrections, not a rewrite.

Do NOT touch anything else in either SKILL.md.

## Gap 1 - staging without looking first

Seen in BOTH tests: the agent went straight to `git add <file>`
and never ran `git status --short`. Specific staging is correct,
but the point of `status` is to SEE what else is moving in the
tree before touching it. On the day of the tests four unrelated
files appeared mid-session from a parallel task. That is the
whole reason rule 3 was fixed in CLAUDE.md.

File: .claude/skills/master-ai-backend/SKILL.md

In the "Required sequence" block, the staging step must read:

    git status --short          # look BEFORE you stage
    git add <only the paths you changed>
    git commit -m "<what changed>"

Add one line under the block:

    `git status --short` is not optional. The tree regularly
    carries unrelated in-flight work. Staging blind is how that
    work ends up in someone else's commit.

## Gap 2 - configuration.yaml ownership

In test 2 the agent listed step 3 (edit configuration.yaml,
restart HA) as its own work. Per the role split, Home Assistant
YAML and config belong to claude.ai, not Claude Code.

File: .claude/skills/master-ai-dashboard-field/SKILL.md

Step 3 in "The chain" must read:

    3. If `json_attributes` needs the new key: report the exact
       edit needed in `configuration.yaml` and hand it to
       claude.ai. Do NOT edit HA YAML and do NOT restart HA.

Everything else in the chain stays as written. Steps 5 and 6
already hand off correctly - leave them alone.

## Verify

1. Re-read both files and confirm only these two areas changed.
2. `/skills` still lists both, and neither description grew.
3. Re-run test 1: `شنو أشغّل بعد ما أعدل server.py؟`
   `git status --short` must now appear before `git add`.
4. Commit: `git status --short`, then
   `git add .claude/skills`, then commit. Nothing else staged.

## Not in scope

Step 4 of SKILLS_ADOPTION_PLAN.md (the two external Trail of
Bits skills) is deferred deliberately - the internal skills earn
their keep first. Do not install them as part of this patch.
