# Operational Access Matrix

## Task → Tool

| Task Type | Tool | Notes |
|-----------|------|-------|
| Python files inside `master_ai/` | SSH + `apply_text_patch.py` | Always. No exceptions. |
| HA YAML / config files | DC `edit_block` first, SSH fallback | DC only if edit is small and clear |
| DB queries / checks | SSH (`sqlite3` or `python3`) | Use `_tools/db_sanity.py` for radar |
| Logs | SSH (`journalctl`, `tail`) | |
| Git (status, commit, log) | SSH | Always `git commit` before restart |
| Service restart | SSH (`_tools/restart_master_ai.sh`) | |
| API / endpoint tests | SSH (`curl`) | Use `_tools/quick_check.py` |
| Radar field verification | SSH (`_tools/smoke_test.py`) | |
| Dashboard / Chrome | Visual review only | Never a source of truth |

## Post-Change Validation Order

1. `python3 _tools/quick_check.py` — syntax + service + endpoints + git
2. `python3 _tools/smoke_test.py` — radar fields
3. `python3 _tools/db_sanity.py` — DB tables
4. Visual check in browser (last, optional)

## Prohibited

| Action | Why |
|--------|-----|
| `append` on Python files | Corrupts indentation, causes SyntaxError |
| DC `edit_block` on `\\share\master_ai\` UNC | Unreliable on large files, encoding issues |
| Heavy operations inside request path | Causes timeout on `/dashboard/extended` etc. |
| Editing dashboard YAML before endpoint check | Wastes time — if endpoint is wrong, dashboard won't help |
| `copy/paste` deployment | Always git deploy: commit → restart |
| Modifying `server.py` without reading `/system/context` first | Missing current state = blind changes |
| SSH file transfer (scp/sftp) for code | Use Samba `S:\master_ai\` or deploy endpoint |
| Returning 5xx from a dashboard-consumed endpoint for an expected/business condition (e.g. 'Bridge offline', 'no data') | Cloudflare Tunnel replaces ANY origin 5xx with its own HTML error page — frontend gets `<!DOCTYPE html>` instead of JSON and `resp.json()` throws. Return HTTP 200 with the error in the JSON body instead; keep 5xx only for real unhandled exceptions. |

## File Transfer

| Direction | Method |
|-----------|--------|
| Read/edit Master AI files | Samba `S:\master_ai\` = `\\192.168.109.123\share\master_ai` |
| Read/edit HA config | Samba `H:\` = `\\192.168.109.123\config` |
| Commands on RPi | SSH via `/ssh/run` endpoint or direct `ssh pi@192.168.109.123` |
| Deploy code changes | `git commit` → `_tools/restart_master_ai.sh` |

## Quick Reference Commands

```bash
# Full health check
python3 _tools/quick_check.py

# Radar fields only
python3 _tools/smoke_test.py

# DB tables
python3 _tools/db_sanity.py

# Safe restart
bash _tools/restart_master_ai.sh

# Patch a Python file
python3 _tools/patchers/apply_text_patch.py server.py --old "OLD" --new "NEW" --backup
```
