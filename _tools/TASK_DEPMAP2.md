# TASK DEPMAP2 - close the three consumer surfaces the first pass missed

The generator from TASK_DEPMAP works and its output is deterministic. This is a
narrow extension, not a rewrite. Do not restructure `depmap.py`.

## Why

The map's purpose is to answer "who breaks if I retire this". Right now 148 of
188 endpoints report zero consumers, and that number is wrong rather than
alarming: three real consumer surfaces are not scanned at all. Verified by hand:

- `configuration.yaml` has a `shell_command:` block at line 30 and a
  `rest_command:` block at line 48. Only `resource:` REST sensors (9 of them)
  were scanned. Anything called through those two blocks is invisible.
- `automations.yaml` has 7 lines referencing master_ai or port 9000.
  `scripts.yaml` has 44. None are in the map.
- `tg_intent_router.py` maps Telegram commands to functions. Your own report
  named this as a blind spot.

Those are precisely the "interactive paths that appear in no log and no
schedule" that this map exists to surface.

## Do

1. Extend the YAML scanner to cover, in the Home Assistant config directory
   `/var/lib/homeassistant/homeassistant/`:
   - `configuration.yaml` `rest_command:` and `shell_command:` entries - the URL
     or command, the endpoint it resolves to, file and line
   - `automations.yaml` and `scripts.yaml` - any reference to port 9000, to
     192.168.109.123, to an endpoint path, or to a `rest_command.*` /
     `shell_command.*` service call
   Each becomes a consumer edge of kind `ha_rest_command`, `ha_shell_command`,
   `ha_automation`, `ha_script`.
2. Extend the Telegram scanner: if the command-to-function mapping in
   `tg_intent_router.py` (and any sibling router) is a static dict or a
   decorator table, extract it into edges of kind `telegram_command`.
   If it is built at runtime, do NOT guess - record it in the existing
   `dynamic_requests` style section with file and line, and say so in the
   report.
3. Regenerate `dependency_map.json` and `DEPENDENCY_MAP.md`.
4. Report the before/after zero-consumer counts for endpoints. State how many of
   the 148 were false, and how many survive.
5. Add the new kinds to the coverage list that `--who-consumes` prints when it
   finds nothing. That message is the honest part of the tool; it must stay
   accurate.

## Verify

- The two `--who-consumes` answers that already worked must still work
  unchanged: `check_symbol` and `/dashboard/radar`.
- Pick two endpoints that moved out of the zero-consumer list and show the
  actual consumer line for each in the report. Do not report a count you have
  not looked at.
- Run twice; data fields must still be identical apart from meta.

## Out of scope

- No edits to `server.py`, `dashboard_api.py`, any runtime module, or any Home
  Assistant file. You are reading HA config, never writing it.
- No database writes, no restart, no network calls.
- Do not attempt log-based traffic counting. There is no per-endpoint hit table
  (`request_log` is a goal log, not an HTTP counter) and that is a separate job.
- If a surface turns out not to exist as described, stop and write that in the
  report rather than widening.

## Commit

Stage by name only: `_tools/depmap.py`, `_tools/dependency_map.json`,
`_tools/DEPENDENCY_MAP.md`. Blanket staging is blocked by a hook.
