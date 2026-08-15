# Note: where the logs actually are, and the Cloudflare 1010 trap

- Date: 2026-08-15 (Section E follow-up)

## Cloudflare: ai.salem-home.com blocks non-browser User-Agents (error 1010)

`ai.salem-home.com` blocks requests whose User-Agent is not a browser with
Cloudflare **error 1010** (served as HTTP 403, "access denied based on your
browser's signature"). This is what made `/ssh/run` look broken on
2026-08-15: after one `cp` command every request — including plain reads —
came back 403. The block is at the Cloudflare edge; the origin never saw
the requests. master_ai itself cannot produce 403 on `/ssh/run` (its own
auth failure is 401; the only 403s in server.py are the `/webhook/event`
token checks).

**Rule: any automated script calling through the tunnel must send a browser
User-Agent**, e.g.:

    curl -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36" ...

Do NOT change Cloudflare settings for this (user decision 2026-08-15) —
adapt the client, not the edge. Calls that stay on the LAN
(`http://192.168.109.123:9000`) are unaffected.

## Logging: the live file is `server.log` in the repo root, not `logs/server.log`

`~/master_ai/server.log` (RotatingFileHandler, 2MB x 3, configured in
server.py ~line 709) is the live application log. `logs/server.log` was a
stale leftover dead since 2026-03-14 — it misled two audits into "logging
is dead" and is now renamed `logs/server.log.stale_pre_20260315`. The
`logs/` directory holds the cron jobs' logs (backfill_daily.log,
signal_review.log, intraday_refresh.log, morning_report.log, ...).

Changes made 2026-08-15 to close the real gaps:

1. `master-ai.service`: `StandardOutput/StandardError` moved from
   `append:server.log` to `journal`, and `--no-access-log` removed — so
   `journalctl -u master-ai` now carries uvicorn startup, tracebacks, and
   per-request access lines (the only way to see whether an external
   client's request reached the origin at all). Backup:
   `/etc/systemd/system/master-ai.service.bak.e_logging`.
2. `signal_review.py`: `signal_review` / `review_scheduler` loggers set to
   INFO explicitly — the root logger sits at WARNING, which silently
   dropped the loop's liveness lines for months.
