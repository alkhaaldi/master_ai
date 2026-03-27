#!/usr/bin/env python3
"""Fix 5: Add TV Sync button to Radar Quick Actions (change 4 -> 5 columns)."""
import os

DASH = "/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml"
if not os.path.exists(DASH):
    print("WARN: dashboard not found")
    exit(1)

with open(DASH, "r", encoding="utf-8") as f:
    content = f.read()

original_len = len(content)

# Find the Radar Quick Actions section and change columns: 4 -> 5
# Then add TV Sync button before the STALE DATA WARNING

old_status_button = """              - type: button
                name: \u0627\u0644\u062d\u0627\u0644\u0629
                icon: mdi:information-outline
                tap_action:
                  action: call-service
                  service: script.turn_on
                  target:
                    entity_id: script.master_ai_radar_status
                show_state: false
                card_mod:
                  style: |
                    ha-card { border-radius: 14px; height: 48px; }
                    ha-card .name { font-size: 11px !important; }

          # \u2500\u2500 STALE DATA WARNING \u2500\u2500"""

new_buttons = """              - type: button
                name: \u0627\u0644\u062d\u0627\u0644\u0629
                icon: mdi:information-outline
                tap_action:
                  action: call-service
                  service: script.turn_on
                  target:
                    entity_id: script.master_ai_radar_status
                show_state: false
                card_mod:
                  style: |
                    ha-card { border-radius: 14px; height: 48px; }
                    ha-card .name { font-size: 11px !important; }
              - type: button
                name: TV Sync
                icon: mdi:sync
                tap_action:
                  action: call-service
                  service: script.turn_on
                  target:
                    entity_id: script.master_ai_tv_sync
                show_state: false
                card_mod:
                  style: |
                    ha-card { border-radius: 14px; height: 48px; }
                    ha-card .name { font-size: 11px !important; }

          # \u2500\u2500 STALE DATA WARNING \u2500\u2500"""

if old_status_button in content:
    content = content.replace(old_status_button, new_buttons, 1)
    # Also change columns: 4 to columns: 5 for the quick actions grid
    # This is the first grid with columns: 4 after "V12: QUICK ACTIONS"
    old_grid = "          # \u2500\u2500 V12: QUICK ACTIONS \u2500\u2500\n          - type: grid\n            columns: 4"
    new_grid = "          # \u2500\u2500 V12: QUICK ACTIONS \u2500\u2500\n          - type: grid\n            columns: 5"
    if old_grid in content:
        content = content.replace(old_grid, new_grid, 1)
        print("OK: Changed Quick Actions to 5 columns")
    print("OK: TV Sync button added")
else:
    print("WARN: Status button marker not found")

new_len = len(content)
if new_len > original_len:
    with open(DASH, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"DONE — +{new_len - original_len} chars")
else:
    print("ERROR: no changes made")
