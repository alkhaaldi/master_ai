#!/usr/bin/env python3
"""Test radar templates directly against HA."""
import json, subprocess

token = open('/home/pi/.ha_token').read().strip()

templates = {
    "ctx_check": "{% set e = 'sensor.master_ai_extended' %}{% set ctx = state_attr(e,'radar_daily_context') %}CTX_LEN={{ ctx | length if ctx else 0 }}{% if ctx and ctx | length > 0 %} FIRST={{ ctx[0].symbol }} score={{ ctx[0].score }}{% endif %}",
    "wl_check": "{% set e = 'sensor.master_ai_extended' %}{% set wl = state_attr(e,'radar_watchlist') %}WL_LEN={{ wl | length if wl else 0 }}{% if wl and wl | length > 0 %} FIRST={{ wl[0].symbol }}{% endif %}",
    "sig_check": "{% set e = 'sensor.master_ai_extended' %}{% set sig = state_attr(e,'radar_recent_signals') %}SIG_LEN={{ sig | length if sig else 0 }}",
    "trend_check": "{% set e = 'sensor.master_ai_extended' %}{% set ctx = state_attr(e,'radar_daily_context') %}{% if ctx and ctx | length > 0 %}{% for s in ctx[:3] %}{{ s.symbol }}={{ s.trend }} {% endfor %}{% endif %}",
}

for name, tpl in templates.items():
    body = json.dumps({"template": tpl})
    cmd = ['curl', '-s', '-H', f'Authorization: Bearer {token}',
           '-H', 'Content-Type: application/json',
           '-X', 'POST', 'http://localhost:8123/api/template',
           '-d', body]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(f"{name}: {r.stdout.strip()}")
