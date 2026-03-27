#!/usr/bin/env python3
"""Verify HA sensors have the correct attributes after v9 fixes."""
import json, subprocess

HA_TOKEN = open("/home/pi/.ha_token").read().strip()

def check_sensor(entity_id, expected_attrs):
    result = subprocess.run(
        ["curl", "-s", "-H", f"Authorization: Bearer {HA_TOKEN}",
         f"http://localhost:8123/api/states/{entity_id}"],
        capture_output=True, text=True
    )
    try:
        data = json.loads(result.stdout)
        attrs = data.get("attributes", {})
        state = data.get("state", "?")
        print(f"\n{entity_id}: state={state}")
        for a in expected_attrs:
            val = attrs.get(a, "MISSING")
            status = "✓" if val != "MISSING" else "✗ MISSING"
            if isinstance(val, (dict, list)):
                val = f"({type(val).__name__} len={len(val)})"
            print(f"  {a}: {status} = {val}")
    except Exception as e:
        print(f"  ERROR: {e}")

check_sensor("sensor.master_ai_journal", [
    "open_positions", "closed_trades", "best_trade", "worst_trade",
    "stats_30d", "portfolio_summary", "monthly_stats"
])

check_sensor("sensor.master_ai_extended", [
    "avg_cost_per_request", "cpu", "memory_pct"
])

check_sensor("sensor.master_ai_alerts", [
    "volume_spikes", "sr_proximity", "confluence_alerts", "rsi_extremes"
])
