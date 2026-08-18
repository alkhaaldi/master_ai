# REPORT_DEPMAP — Dependency Map Task

**Date:** 2026-08-18
**Commit:** 4b2ecd8
**Run time:** 2.6 s

---

## What changed

Three new files committed (by name only, no other files touched):

| File | Purpose |
|------|---------|
| `_tools/depmap.py` | Static-analysis generator (~470 lines, stdlib only) |
| `_tools/dependency_map.json` | Machine-readable output, regenerated on every run |
| `_tools/DEPENDENCY_MAP.md` | Human-readable report (~10 k lines) |

No edits to `server.py`, `dashboard_api.py`, or any runtime module.

---

## Who consumes it

`depmap.py` is a standalone tool. It is not imported by any runtime module.
It is consumed by developers running:

```
python3 _tools/depmap.py                          # regenerate
python3 _tools/depmap.py --who-consumes THING     # query
```

Intended consumers of `DEPENDENCY_MAP.md` / `dependency_map.json`:
- Any session that wants to know whether retiring a route, table, or module is safe
- Pre-commit review when deleting endpoints or modules

---

## What might break

**Nothing in the running service.** The generator does not import project modules,
does not touch any database, does not call the network, and does not restart
or signal the service.

**Known limitations (scanner blind spots):**

| Gap | Detail |
|-----|--------|
| Telegram dispatch | `tg_intent_router.py` maps commands to functions at runtime; none of those call paths appear in the consumers lists |
| Dynamic endpoint construction | `fetch('/api/'+variable)` — captured in the `dynamic_requests` section with file+line but endpoint not resolved |
| `import module` + `module.func()` calls | Only `from X import Y` edges are in the symbol index; dot-access calls are in the module-import list but not the per-symbol list |
| HA template sensors | Sensors that read `state_attr(...)` rather than polling a URL are not in `ha_sensors` |
| Runtime importlib / `__import__` | Not detectable by `ast` |
| `_archive/` directory | Excluded by design — deprecated code, but if anything there were un-archived it would be invisible |

**Zero-consumer count is high (148 endpoints, 30 write-only tables, 254 read-only tables).**
This is expected: many endpoints are called via Telegram commands, HA button cards,
or direct curl — none of which appear in the scanned HTML or YAML.
The zero-consumer list is where blind spots surface first; treat it as a starting
point for review, not a safe-to-delete list.

---

## What is left

Nothing within the task's scope is left incomplete.

**Pending decisions raised during the task (none require widening scope):**

1. **Timestamp in idempotency check** — the JSON differs by `generated_at` and `elapsed_sec`
   on each run by design. All data fields are byte-identical across runs (verified with
   a stripped comparison). If strict byte-identity is needed, the timestamp could be
   supplied as an environment variable or flag; that is a caller decision, not a
   generator decision.

2. **`tables_never_written: 254`** — most of these are tables that are read via
   string patterns that the scanner matches but whose writes use parameterised SQL
   or ORM methods that the regex does not catch. A follow-up could add ORM-aware
   scanning (e.g., SQLAlchemy `.execute()` calls). Out of scope for this task.

3. **`schedules_found: 55`** — the asyncio startup tasks are captured, but the
   internal sleep-loop periods inside each scheduler function (e.g., "every 2h")
   are not extracted. Those are prose in the source, not structured data.
   Out of scope.

**Verification checklist (all passed):**

- [x] `python3 _tools/depmap.py` completes without error in 2.6 s
- [x] `--who-consumes www/trading/analysis.html` → nav_link in nav.js:22, dynamic call line 253
- [x] `--who-consumes check_symbol` → imported by tradingview_bridge.py, test_radar.py, test_radar_venv.py
- [x] `--who-consumes /dashboard/radar` → defined dashboard_api.py:441, consumed by personality.html (×2), signals.html, sensor master_ai_radar
- [x] Second run data identical (excluding timestamp/elapsed)
- [x] Only `_tools/depmap.py`, `_tools/dependency_map.json`, `_tools/DEPENDENCY_MAP.md` staged; pre-existing modified files left untouched
- [x] No edits to server.py, dashboard_api.py, or any runtime module
- [x] No DB writes, no network calls, no service restart
