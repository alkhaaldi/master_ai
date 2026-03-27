#!/usr/bin/env python3
"""Reload HA dashboard + verify templates render."""
import subprocess, json

HA = open("/home/pi/.ha_token").read().strip()

# Reload lovelace
r = subprocess.run(["curl", "-s", "-X", "POST",
    "-H", f"Authorization: Bearer {HA}",
    "http://localhost:8123/api/services/lovelace/reload"],
    capture_output=True, text=True)
print("Lovelace reload:", r.stdout[:50] if r.stdout else "OK")

# Test template rendering
import time; time.sleep(2)
template = '{% set d = "sensor.master_ai_dashboard" %}{{ state_attr(d, "version") }} {{ state_attr(d, "shift_today") }}'
r2 = subprocess.run(["curl", "-s", "-X", "POST",
    "-H", f"Authorization: Bearer {HA}",
    "-H", "Content-Type: application/json",
    "http://localhost:8123/api/template",
    "-d", json.dumps({"template": template})],
    capture_output=True, text=True)
print("Template test:", repr(r2.stdout))

# Test radar sensor
template2 = '{% set r = "sensor.master_ai_radar" %}{{ state_attr(r, "radar_daily_context") | length }} stocks'
r3 = subprocess.run(["curl", "-s", "-X", "POST",
    "-H", f"Authorization: Bearer {HA}",
    "-H", "Content-Type: application/json",
    "http://localhost:8123/api/template",
    "-d", json.dumps({"template": template2})],
    capture_output=True, text=True)
print("Radar test:", repr(r3.stdout))
