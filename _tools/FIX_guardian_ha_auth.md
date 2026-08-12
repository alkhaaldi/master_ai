# FIX: system_guardian HA check triggers invalid-auth spam

## Decision
- Task: stop HA "invalid authentication" warnings every 5 minutes
- File type: Python (system_guardian.py)
- Executor: Claude Code
- Plan: one-line change inside _check_ha()

## Problem
HA core logs every ~5 min:
  WARNING [homeassistant.components.http.ban] Login attempt or request with
  invalid authentication from 192.168.109.123 ... URL: '/api/' (python-httpx/0.28.1)

Risk: http.ban counts failed logins -> could IP-ban the RPi and break the
legitimate ha_get_state / ha_call_service calls from Master AI.

## Root cause
File: /home/pi/master_ai/system_guardian.py
Function: _check_ha() (around line 35-42)
It sends an UNAUTHENTICATED GET to HA /api/ which requires a bearer token,
so HA returns 401 and logs an invalid-auth warning on every poll.
The function already treats 401 as "HA up" (return r.status_code in (200,401)),
so the fix is only to stop hitting an auth-protected endpoint.

## Change (minimal, backward-compatible)
In _check_ha(), replace the request URL with a no-auth health endpoint.
Verified today: GET http://192.168.109.123:8123/auth/providers -> 200 (no token).

BEFORE:
    r = httpx.get("http://192.168.109.123:8123/api/", timeout=5)
    return r.status_code in (200, 401)  # 401 = auth needed but HA is up

AFTER:
    # /auth/providers returns 200 without a token; confirms HA core is up
    # without tripping HA's http.ban invalid-auth counter.
    r = httpx.get("http://192.168.109.123:8123/auth/providers", timeout=5)
    return r.status_code in (200, 401)

Do NOT change anything else. Keep the (200,401) tuple as a safety net.

## Steps (Claude Code)
1. Edit system_guardian.py _check_ha() as above (patch system or direct edit).
2. python3 _tools/quick_check.py
3. python3 _tools/smoke_test.py
4. git add system_guardian.py && git commit -m "fix(guardian): use /auth/providers for HA check to stop invalid-auth spam"
5. bash _tools/restart_master_ai.sh

## Verify (after ~6 min = next guardian cycle)
  sudo -n docker logs --since 8m homeassistant 2>&1 | grep "invalid authentication"
Expect: NO new lines dated after the restart.

## Rollback
Revert the one-line URL back to "/api/" and restart.
