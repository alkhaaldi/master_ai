#!/usr/bin/env python3
"""Check if confluence sensor is available in HA."""
import subprocess, json

HA = open("/home/pi/.ha_token").read().strip()
r = subprocess.run(["curl", "-s", "-H", f"Authorization: Bearer {HA}",
    "http://localhost:8123/api/states/sensor.master_ai_confluence"],
    capture_output=True, text=True)
try:
    d = json.loads(r.stdout)
    attrs = d.get("attributes", {})
    print(f"State: {d.get('state', '?')}")
    print(f"Attributes: {list(attrs.keys())[:10]}")
    print(f"scan_active: {attrs.get('scan_active')}")
    print(f"actionable_count: {attrs.get('actionable_count')}")
    print(f"watch_count: {attrs.get('watch_count')}")
except Exception as e:
    print(f"Error: {e}")
    print(f"Response: {r.stdout[:200]}")
