#!/usr/bin/env python3
"""Add confluence sensor to HA configuration.yaml"""
from pathlib import Path

CONFIG = Path("/var/lib/homeassistant/homeassistant/configuration.yaml")
content = CONFIG.read_text(encoding="utf-8")

if "master_ai_confluence" in content:
    print("Confluence sensor already exists — SKIP")
else:
    SENSOR = '''
  # v9.x Confluence Decision Engine sensor
  - resource: "http://192.168.109.123:9000/dashboard/confluence"
    method: GET
    headers:
      X-API-Key: !secret master_ai_key
      Authorization: !secret master_ai_bearer
    scan_interval: 120
    timeout: 20
    sensor:
      - name: "Master AI Confluence"
        unique_id: master_ai_confluence
        value_template: "{{ value_json.actionable_count }}"
        json_attributes:
          - scan_active
          - last_scan
          - scan_stale
          - stocks_scanned
          - actionable_count
          - watch_count
          - actionable
          - watchlist
          - market_summary
'''
    content += SENSOR
    CONFIG.write_text(content, encoding="utf-8")
    print(f"Confluence sensor added ✓ ({len(content.split(chr(10)))} lines)")
