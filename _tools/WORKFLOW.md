# WORKFLOW — how claude.ai and Claude Code work together

- Agreed 2026-08-18. Supersedes the old "user relays messages by hand" model.
- Read this at the start of any Claude Code session. Referenced from `CLAUDE.md`.

## The problem this replaces

The user was copying every instruction from claude.ai to Claude Code and every
report back. A two-hour task was mostly waiting on him, and he does not read
the technical detail he was relaying. He asked to stop being the courier.

## How it works now

```
1. The user states the problem in one sentence.
2. claude.ai investigates directly — API, DB, logs, code. It does not ask him
   to look things up.
3. claude.ai writes a task file: _tools/TASK_<NAME>.md
4. claude.ai invokes Claude Code itself, headless:

     claude -p "read _tools/TASK_<NAME>.md and execute it.
                Write your report to _tools/REPORT_<NAME>.md before you finish."

   Run from /home/pi/master_ai so project skills load.
5. Claude Code works and writes the report file.
6. claude.ai reads the report, verifies the numbers on the wire itself, and
   re-invokes with corrections if needed. Cap of ~3 rounds.
7. claude.ai reports the outcome to the user in plain Arabic.
```

The user is not in steps 2–6.

## What Claude Code must do in every headless run

1. **Write the report file.** stdout is truncated and unreliable; the file is
   the channel. Report structure: what was measured, what changed, what still
   fails, what in the task turned out wrong about the codebase.
2. **Stay inside the task's scope.** Every task file has an "Out of scope"
   section. If something inside forces a decision outside it, **stop and write
   that in the report** instead of widening. This has gone wrong before: a
   Telegram task drifted into cover counting and the original problem went
   unsolved for a day.
3. **Commit before finishing**, with explicit paths — never `git add -A`. The
   guard at `.claude/hooks/git_guard.sh` enforces this inside the repo.
4. **Leave the tree clean**, or say in the report exactly what is left and why.

## What Claude Code must NOT do without asking

- Restart the service while the market is open (Sun–Thu 09:00–13:00 Kuwait).
  A restart costs a scan cycle. Write the request in the report instead.
- Send any Telegram message on the user's behalf, other than a probe that is
  designed to fail.
- Delete data, or migrate a table, without the request being in the task file.
- Open the `BUY_NOW` gate. It is shadowed until the observation window closes.

## Decision rights

claude.ai decides everything except four cases, which go to the user:

```
1. Only his eyes can settle it
   how many curtains are open · did the message arrive · does the page look right
2. It touches his money
   a trade · the BUY_NOW gate · position size · capital
3. It cannot be undone
   deleting data · migrating a table
4. It is a large architectural choice
   e.g. retiring the Bridge
```

Everything else — technical route, ordering, code correction, which endpoint to
change — is claude.ai's call. **Do not ask the user technical questions he has
no basis to answer.** A guessed answer from him is worse than a decided one.

## Why the protections exist

Automation without them means faster mistakes, not less work. Three layers:

- **A dependency map** — which file reads from where, and who consumes it.
  Sessions have twice broken a page by retiring something it depended on
  (`analysis.html`, `check_symbol`), because interactive paths appear in no log
  and no schedule.
- **Hooks that refuse** — a rule written in prose gets skipped; a hook cannot
  be. `git add -A` was stated twice in a skill and skipped in both trigger
  tests.
- **A change log per task** — what changed, who consumes it, what might break.

## Standing facts

```
Claude Code   /usr/bin/claude  v2.1.80 on the RPi · Node v24.13.1 · auth OK
Invocation    run from /home/pi/master_ai so project skills load
Task files    _tools/TASK_<NAME>.md
Reports       _tools/REPORT_<NAME>.md
Open work     _tools/OPEN_ITEMS.md — the single list
Scales        _tools/SCALES.md — what every number means
Storage       _tools/STORAGE_POLICY.md — where a growing file belongs
```
