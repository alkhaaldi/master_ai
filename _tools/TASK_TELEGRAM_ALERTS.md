# TASK — Telegram alerts have never actually fired

- Written 2026-08-18 by claude.ai. Measured, not reported.
- **Scope is narrow. Read "Out of scope" before starting.**

## What was measured

```
telegram_sends — every row is a deliberate failure from prove_guards.py
  id 9,10,11,12 · delivered=0 · http 401 · caller prove_guards.py
  the one successful send on 2026-08-17 was manual, from an interactive shell

logs/signal_review.log     "Telegram credentials not found"  ×2
data_fetch_runs            no signal_review row for 2026-08-18
server.log                 only "Telegram polling started" — no send lines
```

So: the 14:20 cron slot did not produce a run yesterday or today, and
`signal_review` still cannot resolve credentials despite the unified resolver
committed on 2026-08-17.

**No scheduled alert has ever been delivered.** Every guard built this week
reports into a channel that has not been shown to work from cron.

## Questions to answer with numbers, before changing anything

1. Did the 14:20 cron entry run at all? Show the crontab line and the system
   cron log for that slot on 08-17 and 08-18. If it did not fire, why.
2. `signal_review` still logs "credentials not found". Does it use
   `telegram_credentials()` from the unified resolver, or its own path? Show
   the line.
3. When did `logs/signal_review.log` last get written, and by which run?
4. Are there other schedulers that were supposed to alert and did not?
   Check every caller of `send_telegram` and report the last real (non-probe)
   attempt for each.

## Then fix

Only after the four answers. The fix is whatever they point to — do not
assume it is the resolver.

## Acceptance

- One alert delivered from a **cron-invoked** run, recorded in
  `telegram_sends` with `delivered=1` and a caller that is not `prove_guards`.
- `logs/signal_review.log` no longer contains "credentials not found".
- The user confirms it arrived on his phone.

## Out of scope — do not touch in this task

```
home_covers_open · active_devices_count · the cover direction question
the "active device" definition · quick_query's counting rule
positions.html · the 20 read-not-shipped fields · the 15 falsy defaults
```

Those are separate open items. This task drifted into them once already.
If something here forces a decision about them, **stop and ask** rather than
widening.

## Report back

The four answers with numbers first, then what changed, then the acceptance
line. Nothing else.
