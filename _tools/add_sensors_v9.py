#!/usr/bin/env python3
"""Add v9 sensors (journal + alerts) to HA configuration.yaml"""
from pathlib import Path

CONFIG = Path("/var/lib/homeassistant/homeassistant/configuration.yaml")
API_KEY = "jFVbxQN6EtcHToRr6JtRokjhUdIdqYo5JlZCy7CcfNc"

content = CONFIG.read_text(encoding="utf-8")

if "master_ai_journal" in content:
    print("Journal sensor already exists — skipping")
elif "master_ai_analysis" not in content:
    print("ERROR: Cannot find analysis sensor — cannot determine insert point")
else:
    # Append after the analysis sensor section (end of file)
    NEW_SENSORS = f'''
  # v9.0 Journal sensor
  - resource: "http://192.168.109.123:9000/dashboard/journal"
    method: GET
    headers:
      X-API-Key: "{API_KEY}"
      Authorization: "Bearer {API_KEY}"
    scan_interval: 120
    timeout: 20
    sensor:
      - name: "Master AI Journal"
        unique_id: master_ai_journal
        value_template: "{{{{ value_json.portfolio_summary.open_count | default(0) }}}}"
        json_attributes:
          - open_positions
          - closed_trades
          - stats_30d
          - stats_7d
          - portfolio_summary
          - monthly_stats
          - best_trade
          - worst_trade
  # v9.0 Alerts sensor
  - resource: "http://192.168.109.123:9000/dashboard/alerts"
    method: GET
    headers:
      X-API-Key: "{API_KEY}"
      Authorization: "Bearer {API_KEY}"
    scan_interval: 300
    timeout: 20
    sensor:
      - name: "Master AI Alerts"
        unique_id: master_ai_alerts
        value_template: >-
          {{% set vs = value_json.volume_spikes | default([]) | length %}}
          {{% set sr = value_json.sr_proximity | default([]) | length %}}
          {{% set ca = value_json.confluence_alerts | default([]) | length %}}
          {{% set re = value_json.rsi_extremes | default([]) | length %}}
          {{{{ vs + sr + ca + re }}}}
        json_attributes:
          - volume_spikes
          - sr_proximity
          - confluence_alerts
          - rsi_extremes
'''
    content += NEW_SENSORS
    CONFIG.write_text(content, encoding="utf-8")
    print("Journal + Alerts sensors added to configuration.yaml ✓")
    print(f"File: {len(content.split(chr(10)))} lines")
