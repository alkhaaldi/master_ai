# REPORT — Telegram alerts diagnosis
# Written 2026-08-18 by Claude (diagnosis-only run, no code changed)

---

## Q1. Did the 14:20 cron entry run at all?

YES — both days.

Crontab line (pi's crontab):
```
20 14 * * 0-4 cd /home/pi/master_ai && venv/bin/python3 _tools/daily_signal_review.py >> logs/signal_review.log 2>&1
```

System cron log (from journalctl -u cron):
```
Aug 17 14:20:01  CRON[1952945]: (pi) CMD (...daily_signal_review.py...)
Aug 17 14:20:13  CRON[1952943]: pam_unix: session closed for user pi   # 12 s runtime

Aug 18 14:20:01  CRON[2123086]: (pi) CMD (...daily_signal_review.py...)
Aug 18 14:20:15  CRON[2123084]: pam_unix: session closed for user pi   # 14 s runtime
```

Cron fired on time on both days. No cron-level failure.

---

## Q2. Does `signal_review` use `telegram_credentials()` from the unified resolver, or its own path?

It depends on which commit was in place at the time of each run.

The credential section of `_send_review_telegram` (signal_review.py:637-648):

```python
# One resolver (2026-08-17). This block used to read os.environ — empty
# under cron — then fall back to ~/.telegram_bot_token, a file that has
# never existed on this machine.
import sys as _sys
_sys.path.insert(0, ...)
from run_witness import telegram_credentials as _tc
bot_token, chat_id, _why = _tc()
if not bot_token or not chat_id:
    logger.warning("Telegram credentials unavailable: %s", _why)
    return False
```

- **Aug 16 & 17 runs**: the resolver was NOT yet committed — those runs used the old
  `os.environ` path which is empty under cron, then fell back to
  `~/.telegram_bot_token` which has never existed. Both logged
  "Telegram credentials not found" and returned False immediately.

- **Aug 18 14:20 run**: the resolver was already committed (on 08-17, after 14:20).
  The credential section succeeded (no "credentials not found" in the log).
  BUT the send section still used a bare `requests.post` (the uncommitted change
  that routes through `run_witness.send_telegram` was written at 14:22:09,
  two minutes AFTER the cron finished). So the Aug 18 run got credentials,
  attempted a bare HTTP send, and left no record anywhere.

Current committed line: `signal_review.py:644`
```python
from run_witness import telegram_credentials as _tc
```
Answer: YES, the unified resolver. But the send was still done bare (see Q4).

---

## Q3. When did `logs/signal_review.log` last get written, and by which run?

```
Modify: 2026-08-18 14:20:15
```

Written by the 14:20 cron on 08-18 (CRON[2123086]).

The file contains output from 3 runs:
```
Run 1 (2026-08-16 14:20):  "Telegram credentials not found"
                            scan: 7 ENTER decisions from 132 stocks
                            reviewed 2026-08-15: {success:1, partial:3, ongoing:2}
                            reviewed 2026-08-16: {no_data:10}
                            witness: signal_review success (graded 6 / considered 16)

Run 2 (2026-08-17 14:20):  "Telegram credentials not found"
                            scan: 6 ENTER decisions from 132 stocks
                            reviewed 2026-08-16: {ongoing:5, partial:3, success:1, fail:1}
                            reviewed 2026-08-17: {no_data:10}
                            witness: signal_review success (graded 10 / considered 20)

Run 3 (2026-08-18 14:20):  scan: 7 ENTER decisions from 132 stocks
                            reviewed 2026-08-17: {ongoing:4, partial:6, fail:1}
                            reviewed 2026-08-18: {no_data:12}
                            witness: signal_review success (graded 11 / considered 23)
```

Run 3 has no credential error AND no telegram outcome line. The bare
`requests.post` path printed nothing on success or failure — its `except`
block called `logger.error()` (goes to the logger, not stdout) and the
happy path returned silently. telegram_sends has zero rows from
daily_signal_review or signal_review.

---

## Q4. Other callers of `send_telegram` — last real (non-probe) attempt

`telegram_sends` full history (12 rows):
- id 1-2, 4-12: prove_guards.py, delivered=0, http 401
- id 3: `<stdin>:11`, delivered=1, http 200, sent 2026-08-17 15:03:55 — ONLY successful send

No other caller has ever reached `telegram_sends`. Breakdown of every caller:

### A. `signal_review._send_review_telegram` — via `daily_signal_review.py`
- Runs: 08-16, 08-17 — credential fail, returned False, never sent
- Run 08-18 — credentials OK, bare `requests.post`, NO record, outcome unknown
- Does NOT use `run_witness.send_telegram` (this is the uncommitted fix)

### B. `brain_proactive._send_telegram` (lines 398, 458)
- Credential path: `os.getenv("TELEGRAM_BOT_TOKEN", "")` (line 143)
- The FastAPI service loads .env via systemd so the token IS present there,
  but brain_proactive's proactive briefings fire on a schedule inside the
  running server. No telegram_sends entries = conditions (shift change, etc.)
  have either not triggered or the function path silently failed.
  Last real attempt: NONE (never in telegram_sends).

### C. `health_watchdog.send_telegram` (line 307)
- Credential path: `env.get("TELEGRAM_BOT_TOKEN", "")` from a .env dict
  loaded inside the script. Raises `RuntimeError` if missing (line 255).
- Cron does not inject .env — the RuntimeError would propagate to the caller
  and be swallowed or crash the send. No telegram_sends entries (does not
  use the witness).
- Last real attempt: NONE (no records anywhere).

### D. `dropzone_watcher.send_telegram` (lines 244, 303, 328-336)
- Credential path: `os.getenv("TG_BOT_TOKEN", "")` — note: `TG_BOT_TOKEN`,
  not `TELEGRAM_BOT_TOKEN`. The .env file declares `TELEGRAM_BOT_TOKEN`.
  Even if env were injected, the variable name mismatch means `TG_BOT_TOKEN`
  is always empty. Line 123: `if not TG_BOT_TOKEN or not TG_CHAT_ID: return`
  (silent skip). No telegram_sends entries (does not use witness).
- Last real attempt: NONE (silently skipped every time by name mismatch).

### E. `_tools/intraday_refresh.py` — `run_witness.send_telegram` (lines 144, 198, 210)
- Fires only on: circuit-breaker halt (2 consecutive failed cycles) or
  stale-data warnings.
- Would appear in telegram_sends. Zero entries from this caller.
- Last real attempt: NEVER TRIGGERED (no halt condition reached to date).

### F. `_tools/backfill_daily_bars.py` — `run_witness.send_telegram` (lines 400, 406)
- Fires only if `bars_inserted == 0` or the run was aborted, or if intraday
  never ran on a trading day.
- Zero entries in telegram_sends from this caller.
- Last real attempt: NEVER TRIGGERED (all close runs inserted bars OK).

### G. `_tools/nas_backup.py` — `run_witness.send_telegram` (line 114)
- Fires only on backup error.
- Zero entries in telegram_sends from this caller.
- Last real attempt: NEVER TRIGGERED (no backup errors).

### H. `yahoo_gate.py` — `run_witness.send_telegram` (line 300)
- Error-path only. No entries in telegram_sends.
- Last real attempt: NEVER TRIGGERED.

### I. `_tools/witness_cli.py` — `run_witness.send_telegram` (lines 30, 33)
- Manual CLI wrapper. Not a scheduler. Not evaluated here.

---

## Summary

The cron slot ran correctly on both measured days. The problem is threefold:

1. **Aug 16 & 17**: credential resolver not yet committed to signal_review.py.
   Every run returned False before sending.

2. **Aug 18**: resolver in place, credentials found, BUT the send used a
   bare `requests.post` that writes nothing to telegram_sends and prints
   nothing to stdout on the happy path. Whether the message was delivered
   cannot be determined from any existing record. The uncommitted fix
   (signal_review.py modified 14:22:09, 2 minutes post-cron) would route
   through run_witness and leave a trace — it was not in place for the
   14:20 run.

3. **All other scheduled callers**: either use `os.getenv()` paths that are
   empty under cron (brain_proactive, health_watchdog), have a credential
   variable name mismatch (dropzone_watcher: `TG_BOT_TOKEN` vs the .env key
   `TELEGRAM_BOT_TOKEN`), or are error-path-only and those error conditions
   have not occurred (intraday_refresh, backfill, nas_backup, yahoo_gate).

The fix that is sitting uncommitted in signal_review.py addresses defect 2
(routes through run_witness.send_telegram, which writes to telegram_sends
and reads `{"ok": true}` instead of trusting status_code). That fix is
correct and necessary, but has not yet been committed or tested from cron.
