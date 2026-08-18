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

## Where the protections live (built 2026-08-18)

```
.claude/hooks/git_guard.sh     no blanket staging
.claude/hooks/ops_guard.sh     the five refusals below
.claude/hooks/report_gate.sh   Stop hook: no report, no ending
_tools/run_task.sh NAME        claude.ai's invoker for TASK_<NAME>.md
_tools/test_ops_guard.sh       24 cases, all passing
_tools/CHANGE_LOG.md           one line per run, written by run_task.sh
_tools/depmap.py               who-consumes queries, see below
```

`ops_guard.sh` refuses, on Bash and on Write/Edit:

1. editing `.claude/` from a session it governs - a guard a session can switch
   off is not a guard
2. restarting while the Kuwait market is open, Sun-Thu 08:45-13:15, on the real
   clock with no environment override
3. any outbound Telegram or mail send, including a test probe
4. destructive SQL, but only when an executor is present, so searching the
   codebase for the phrase still works
5. irreversible disk or git operations - recursive force delete, reset --hard,
   clean -f, push --force

Two override tokens, each valid 30 minutes from its mtime:

```
_tools/.allow_restart_now
_tools/.allow_db_write
```

They work because claude.ai places them over `/ssh/run`, which the hooks do not
govern. The override deliberately lives outside the session it overrides. Both
are gitignored, and a session inside the repo cannot create one - touching it is
a Bash command and the guard sees it.

## Before retiring anything, ask the map

```
python3 _tools/depmap.py                        regenerate, ~3 s
python3 _tools/depmap.py --who-consumes THING   file, endpoint, table, symbol
```

Exit 1 means no consumer was found, and the tool then prints what it does and
does not cover. Read that list before treating an empty answer as permission.
It resolves indirection: `/dashboard/cmd` shows 11 Home Assistant scripts that
never name the endpoint, only the `rest_command` that points at it.

Known blind spots, stated so nobody trusts a zero: external callers over curl or
the tunnel, runtime `importlib`, HA template sensors that read attributes rather
than URLs, and endpoint paths built by string concatenation - those last are
kept in a `dynamic_requests` section with file and line rather than dropped.

146 of 188 endpoints still report zero consumers. That is a review queue, not a
delete list.

## The CLI never spends API credit (pinned 2026-08-18)

`/ssh/run` puts the app's `sk-ant-` key into the environment of everything it
launches, and the Claude Code CLI prefers that key over the subscription login.
That is how a headless run can quietly bill API credit. Three layers now stop it:

```
/usr/local/bin/claude    wrapper, first in PATH, execs the real binary with
                         env -u ANTHROPIC_API_KEY - covers every caller
_tools/run_task.sh       invokes with env -u explicitly
ops_guard.sh rule 4      blocks "claude -p" that names /usr/bin/claude directly
                         without env -u, which is the only way around the wrapper
```

The key itself stays where it is. It is the app's, not the CLI's - `server.py:624`
and `:736`, `chat_v7.py:487`, `inbox_engine.py:30` all read it. Removing it from
`.env` would break those, so it was left alone.

To undo the wrapper: delete `/usr/local/bin/claude`. The real binary is untouched
at `/usr/bin/claude`.
