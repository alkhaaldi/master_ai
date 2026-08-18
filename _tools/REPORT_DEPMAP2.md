# REPORT_DEPMAP2 — Close the Three Consumer Surfaces

**Date:** 2026-08-18
**Commit:** 5ac6428
**Task file:** _tools/TASK_DEPMAP2.md

---

## What changed

Three new scanner functions were added to `_tools/depmap.py`. No other file was touched.

### Scanner 5b — `scan_ha_commands(config_path)`
Parses `configuration.yaml` for `rest_command:` and `shell_command:` blocks.

- **`rest_command:`** — only entries that call port 9000 or contain "master_ai" in the URL are kept.
  - `master_ai_event` → `http://192.168.109.123:9000/webhook/event/TOKEN` (configuration.yaml:49)
  - `master_ai_tg_cmd` → `http://192.168.109.123:9000/dashboard/cmd` (configuration.yaml:62)
- **`shell_command:`** — all 7 entries recorded (all call `tuya_lock.py` for door locks; none reference master_ai). Stored for completeness; no endpoint to link.

Data keys added: `ha_rest_commands` (2 entries), `ha_shell_commands` (7 entries).

### Scanner 5c — `scan_ha_yaml_files(automations_path, scripts_path, rest_commands)`
Scans `automations.yaml` and `scripts.yaml` for `action: rest_command.*` / `action: shell_command.*` calls and direct `:9000` URL references.

**automations.yaml — 4 ha_automation edges:**
| alias | via | endpoint |
|---|---|---|
| Master AI - HA Started | master_ai_event | /webhook/event/{token} |
| Master AI - Door Unlocked | master_ai_event | /webhook/event/{token} |
| Master AI - Baby Crying | master_ai_event | /webhook/event/{token} |
| Quran Watchdog - Restart if stopped or hung | master_ai_event | /webhook/event/{token} |

**scripts.yaml — 13 ha_script edges (11 rest_command + 2 shell_command):**
| alias | via | endpoint |
|---|---|---|
| تشغيل/إيقاف الرادار | master_ai_tg_cmd | /dashboard/cmd |
| فحص السوق | master_ai_tg_cmd | /dashboard/cmd |
| تقرير الصباح | master_ai_tg_cmd | /dashboard/cmd |
| Backup | master_ai_tg_cmd | /dashboard/cmd |
| حالة الرادار | master_ai_tg_cmd | /dashboard/cmd |
| نظرة الأسهم | master_ai_tg_cmd | /dashboard/cmd |
| تحديث الأخبار | master_ai_tg_cmd | /dashboard/cmd |
| إطفاء الكل | master_ai_tg_cmd | /dashboard/cmd |
| تحديث البريد | master_ai_tg_cmd | /dashboard/cmd |
| مراجعة التداول | master_ai_tg_cmd | /dashboard/cmd |
| TV Sync | master_ai_tg_cmd | /dashboard/cmd |
| Unlock Diwaniya Door UI | unlock_diwaniya_door (shell) | (none) |
| Unlock Kitchen Door UI | unlock_kitchen_door (shell) | (none) |

Data key added: `ha_yaml_edges` (17 entries).

### Scanner 5d — `scan_telegram_commands(py_files)`
Scans all Python files for `if cmd == "/x":` and `cmd.startswith("/x")` patterns.

- **124 entries found total.**
- **110 from `server.py`** — the authoritative dispatch handler.
- 14 from patcher/tool files (`_tools/`, `scripts/`) that contain old code snippets being patched in. These are not live dispatch entries; they are false positives from the scanner reading patcher file content.

**Telegram command mapping in `tg_intent_router.py`:** This file handles natural-language intent routing (device control by room/keyword), not slash commands. There is no static dict or decorator table for slash commands in this file. The slash-command dispatch lives in `server.py` as an if/elif chain starting at line ~5358. The chain is not a data structure but the command strings are static literals, so they are extractable — and were extracted.

Data key added: `telegram_commands` (124 entries).

### `build_reverse_index` update
Added route-pattern normalization (`_norm_ep`): URL paths extracted from YAML (e.g. `/webhook/event/6Co3ca...`) are matched against known `{param}`-style route patterns and normalized to the route path (e.g. `/webhook/event/{token}`). This ensures YAML-sourced consumers appear under the correct route key in the reverse index.

### `COVERAGE_NOTE` update
Added 5 new domains: `ha_rest_command`, `ha_shell_command`, `ha_automation`, `ha_script`, `telegram_command`. Removed the stale "Telegram command dispatch" entry from the "Not covered" line.

### Outputs regenerated
- `_tools/dependency_map.json` — new top-level keys: `ha_rest_commands`, `ha_shell_commands`, `ha_yaml_edges`, `telegram_commands`. Counts updated.
- `_tools/DEPENDENCY_MAP.md` — four new sections: HA rest_command definitions, HA shell_command definitions, HA automation/script references, Telegram slash-command dispatch.

---

## Who consumes it

### `/webhook/event/{token}` — 5 consumers (was 0)

| kind | file | line | detail |
|---|---|---|---|
| ha_rest_command | configuration.yaml | 49 | name=master_ai_event |
| ha_automation | automations.yaml | 455 | alias=Master AI - HA Started |
| ha_automation | automations.yaml | 480 | alias=Master AI - Door Unlocked |
| ha_automation | automations.yaml | 499 | alias=Master AI - Baby Crying |
| ha_automation | automations.yaml | 694 | alias=Quran Watchdog - Restart if stopped or hung |

Verified live with: `python3 _tools/depmap.py --who-consumes /webhook/event/{token}`

### `/dashboard/cmd` — 12 consumers (was 0)

| kind | file | line | detail |
|---|---|---|---|
| ha_rest_command | configuration.yaml | 62 | name=master_ai_tg_cmd |
| ha_script | scripts.yaml | 19 | alias=تشغيل/إيقاف الرادار |
| ha_script | scripts.yaml | 37 | alias=فحص السوق |
| ha_script | scripts.yaml | 55 | alias=تقرير الصباح |
| ha_script | scripts.yaml | 73 | alias=Backup |
| ha_script | scripts.yaml | 91 | alias=حالة الرادار |
| ha_script | scripts.yaml | 109 | alias=نظرة الأسهم |
| ha_script | scripts.yaml | 127 | alias=تحديث الأخبار |
| ha_script | scripts.yaml | 145 | alias=إطفاء الكل |
| ha_script | scripts.yaml | 163 | alias=تحديث البريد |
| ha_script | scripts.yaml | 181 | alias=مراجعة التداول |
| ha_script | scripts.yaml | 199 | alias=TV Sync |

Verified live with: `python3 _tools/depmap.py --who-consumes /dashboard/cmd`

### Pre-existing queries verified unchanged

```
python3 _tools/depmap.py --who-consumes /dashboard/radar
→ [ha_sensor] configuration.yaml:294  sensor_id=master_ai_radar  (plus 3 fetch consumers)

python3 _tools/depmap.py --who-consumes check_symbol
→ Imported by 3 files (stock_radar.py, test_radar.py, tradingview_bridge.py)
```

Both produce identical output before and after the change.

---

## What might break

**Nothing breaks.** All changes are additive:

- No existing data keys removed or renamed in `dependency_map.json`.
- No existing endpoint consumers removed or modified.
- No changes to `server.py`, `dashboard_api.py`, any runtime module, or any HA file.
- The zero-consumer count changed from 148 to 146. Any downstream tooling that expects exactly 148 will see 146 instead — this is the intended correction, not a regression.

The 14 false-positive telegram_command entries (from patcher/tool files in `_tools/`) are noise in that list. They do not affect the reverse index (telegram_commands are stored separately from the endpoint consumer index). If filtered by `server.py` only, the real count is 110.

---

## Before / after zero-consumer counts

| Metric | Before | After |
|---|---|---|
| Zero-consumer endpoints | **148** | **146** |
| Total endpoints in index | 195 | 195 |
| yaml_files_scanned | 1 | 3 |
| ha_rest_commands_found | — | 2 |
| ha_shell_commands_found | — | 7 |
| ha_yaml_edges_found | — | 17 |
| telegram_commands_found | — | 124 (110 from server.py) |

**False zeros corrected: 2** (`/webhook/event/{token}` and `/dashboard/cmd`).
**False zeros that survive: 146.** These are endpoints with no detected consumer in any of the 5 scanned surfaces (HTML fetch, HA REST sensor, HA rest_command, HA automation/script, Telegram dispatch). They may be consumed by direct Telegram user messages, curl calls from other scripts, or inter-process calls not visible to static analysis.

---

## What is left

1. **Telegram false positives (14 entries from non-server files).** The scanner reads all .py files including patchers and scripts that contain old code. If the list needs to be clean, either add `_tools/` to `EXCLUDED_DIRS` (which would affect all scanners, not just telegram) or scope `scan_telegram_commands` to `server.py` only. This was not done because the task says not to restructure `depmap.py`, and the impact is minor (false positives are clearly identifiable by file).

2. **Remaining 146 zero-consumer endpoints.** These require either log-based traffic counting (explicitly out of scope per the task) or manual review. Per the task, this is a separate job.

3. **`/webhook/event` (no token) still shows 0 consumers.** The automations call the tokenized URL `/webhook/event/TOKEN`, which normalizes to `/webhook/event/{token}` — correct. The un-tokenized endpoint `/webhook/event` at server.py:5004 has no detected callers.

4. **`tg_intent_router.py` slash-command table.** Confirmed: this file contains no slash-command dict or decorator. It routes natural language to HA device calls. No further scanning needed here.
