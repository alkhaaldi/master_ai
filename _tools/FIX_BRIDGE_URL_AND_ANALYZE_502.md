# FIX: Bridge URL hardcoded + /api/analyze returns 502

Date: 2026-08-12
Owner: Claude Code (RPi)
Type: Python + config
Scope: minimal, backward-compatible

## Root cause (verified)

1. PC IP changed: `192.168.111.158` -> `192.168.111.214`
   - From RPi: `curl 192.168.111.158:8059/health` = 000 (dead)
   - From RPi: `curl 192.168.111.214:8059/health` = 200 (alive)
   - Bridge URL is hardcoded in 19+ files.

2. `/api/analyze` returns HTTP 502 with a JSON body when Bridge is offline.
   Cloudflare Tunnel replaces ANY origin 5xx with its own HTML error page,
   so the browser gets `<!DOCTYPE html>` and `resp.json()` throws:
   `Unexpected token '<', "<!DOCTYPE "... is not valid JSON`
   - Verified on RPi: `LOCAL_HTTP=502` + body `{"error":"Bridge offline ...","symbol":"NBK"}`

## Task 1 - Centralize BRIDGE_URL (do NOT hardcode a new IP again)

### 1a. Add to `.env` on RPi
```
BRIDGE_URL=http://192.168.111.214:8059
```

### 1b. Single config source
```python
import os
BRIDGE_URL = os.getenv("BRIDGE_URL", "http://192.168.111.214:8059").rstrip("/")
```

### 1c. Replace hardcoded occurrences
Prefer importing BRIDGE_URL from the config module. Minimum acceptable:
```python
BRIDGE_BASE_URL = os.getenv("BRIDGE_URL", "http://192.168.111.214:8059")
```

Files with hardcoded `192.168.111.158:8059` (verified by grep):
- bridge_client.py:14
- bridge_client_new.py:14
- stock_analyzer.py:11
- kse_data_collector.py:23
- stock_radar.py:687, 1161
- journal_engine.py:293
- dashboard_api.py:742, 2746
- _tools/: test_bridge.py, test_fractal_quick.py, fractal_backtest.py,
  fractal_backtest_v2.py, fractal_backtest_v3.py, fractal_backtest_v4.py,
  _fetch_30m.py, _fetch_daily.py, _system_check.py

Production files FIRST (bridge_client, dashboard_api, stock_radar,
stock_analyzer, kse_data_collector, journal_engine). `_tools/` scripts second.
Do NOT run blind `sed` on production files - edit and verify each one.

## Task 2 - Stop returning 5xx for business errors

File: `dashboard_api.py` - the `/api/analyze` handler (and `/api/analyze/refresh`).

Current: "Bridge offline" is returned with `status_code=502`.
Cloudflare swallows origin 5xx and serves its own HTML error page,
so the frontend never sees the JSON message.

Required change:
- "Bridge offline" / "no data" is a BUSINESS error, not a gateway failure.
- Return HTTP 200 with the same JSON body plus a flag:
```json
{"error": "Bridge offline - ...", "symbol": "NBK", "bridge_online": false}
```
- The frontend already checks `data.error` -> backward-compatible.
- Keep 5xx ONLY for real unhandled exceptions.

Rule to record in OPERATIONAL_ACCESS_MATRIX.md:
any endpoint consumed by the dashboard must NEVER return 5xx for an
expected/business condition - Cloudflare masks it with HTML.

## Task 3 - Verify

```bash
cd /home/pi/master_ai
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
git add -A && git commit -m "fix: BRIDGE_URL via env + no 5xx on /api/analyze business errors"
bash _tools/restart_master_ai.sh
```

Confirm:
```bash
curl -s -o /tmp/a.txt -w "HTTP=%{http_code}\n" "http://127.0.0.1:9000/api/analyze?symbol=NBK"; head -c 300 /tmp/a.txt
curl -s -m 5 -o /dev/null -w "BRIDGE=%{http_code}\n" "http://192.168.111.214:8059/health"
```
Expected: `HTTP=200` with a real analysis payload.

## Follow-up (user action, not code)

Set a DHCP reservation for the PC on the Ruijie router so the Bridge IP
stops moving. Either pin the PC back to `192.168.111.158`, or pin `.214`
and keep `BRIDGE_URL` in `.env` as the single source of truth.
