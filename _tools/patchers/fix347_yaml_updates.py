#!/usr/bin/env python3
"""Fix 3 (config), 4 (portfolio trade_review button), 7 (system backup button)."""
import os

# ── Fix 3: Add daily_summary to analysis sensor in configuration.yaml ──
CONF = "/var/lib/homeassistant/homeassistant/configuration.yaml"
with open(CONF, "r", encoding="utf-8") as f:
    conf = f.read()

old_analysis_attrs = """        json_attributes:
          - tv_alerts
          - signal_history
          - signal_stats
          - radar_accuracy"""

new_analysis_attrs = """        json_attributes:
          - tv_alerts
          - signal_history
          - signal_stats
          - radar_accuracy
          - daily_summary"""

if old_analysis_attrs in conf:
    conf = conf.replace(old_analysis_attrs, new_analysis_attrs)
    with open(CONF, "w", encoding="utf-8") as f:
        f.write(conf)
    print("Fix3: daily_summary added to analysis sensor config")
else:
    print("Fix3: SKIP — analysis attrs not found or already added")


# ── Fix 4: Ensure trade_review button in portfolio page ──
# Fix 7: Add backup button to system page
DASH = "/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml"
with open(DASH, "r", encoding="utf-8") as f:
    dash = f.read()

original_len = len(dash)

# Fix 4: The portfolio page already has a "\u0645\u0631\u0627\u062c\u0639\u0629" button but it uses
# rest_command.master_ai_tg_cmd directly. Let's update it to use the script instead.
old_review = """              - type: button
                name: \u0645\u0631\u0627\u062c\u0639\u0629
                icon: mdi:clipboard-check-outline
                tap_action:
                  action: call-service
                  service: rest_command.master_ai_tg_cmd
                  data:
                    command: "/trade_review"
                show_state: false"""

new_review = """              - type: button
                name: \u0645\u0631\u0627\u062c\u0639\u0629
                icon: mdi:clipboard-check-outline
                tap_action:
                  action: call-service
                  service: script.turn_on
                  target:
                    entity_id: script.master_ai_trade_review
                show_state: false"""

if old_review in dash:
    dash = dash.replace(old_review, new_review)
    print("Fix4: trade_review button updated to use script")
else:
    print("Fix4: SKIP — review button not found or already correct")

# Fix 7: Add backup button to system page
# Find the system page quick actions or diagnostics area
# Let's search for the system page section
system_marker = "# \u2500\u2500 SYSTEM ACTIONS \u2500\u2500"
if system_marker not in dash:
    # Find the system page command feedback section and add backup button before it
    sys_feedback = None
    # Look for system page structure
    import re
    # Find sub-system-health page
    sys_match = re.search(r'(  - path: sub-system-health.*?)(  # \u2550{30,})', dash, re.DOTALL)
    if sys_match:
        sys_page = sys_match.group(1)
        # Check if there's already a grid with buttons in system page
        if "master_ai_backup" not in sys_page:
            # Find the COMMAND FEEDBACK in system page and insert backup button before it
            # Find the last COMMAND FEEDBACK that belongs to system page
            sys_start = dash.find("  - path: sub-system-health")
            if sys_start > 0:
                # Find next page after system
                next_page = dash.find("  # \u2550\u2550\u2550", sys_start + 10)
                sys_section = dash[sys_start:next_page] if next_page > 0 else dash[sys_start:]

                # Find COMMAND FEEDBACK in system section
                cf_pos = sys_section.find("# \u2500\u2500 COMMAND FEEDBACK")
                if cf_pos > 0:
                    insert_pos = sys_start + cf_pos
                    backup_button = """
          # \u2500\u2500 SYSTEM ACTIONS \u2500\u2500
          - type: grid
            columns: 3
            square: false
            cards:
              - type: button
                name: Backup
                icon: mdi:backup-restore
                tap_action:
                  action: call-service
                  service: script.turn_on
                  target:
                    entity_id: script.master_ai_backup
                show_state: false
              - type: button
                name: \u0627\u0644\u0631\u0626\u064a\u0633\u064a\u0629
                icon: mdi:home
                tap_action:
                  action: navigate
                  navigation_path: /master-ai-dashboard/master-ai
                show_state: false
              - type: button
                name: \u0627\u0644\u0646\u0638\u0627\u0645
                icon: mdi:information-outline
                tap_action:
                  action: call-service
                  service: script.turn_on
                  target:
                    entity_id: script.master_ai_radar_status
                show_state: false

"""
                    dash = dash[:insert_pos] + backup_button + dash[insert_pos:]
                    print("Fix7: Backup button added to system page")
                else:
                    print("Fix7: SKIP — COMMAND FEEDBACK not found in system page")
            else:
                print("Fix7: SKIP — sub-system-health page not found")
        else:
            print("Fix7: SKIP — backup button already exists")
    else:
        print("Fix7: SKIP — system page regex not matched")
else:
    print("Fix7: SKIP — SYSTEM ACTIONS already exists")

new_len = len(dash)
if new_len != original_len:
    with open(DASH, "w", encoding="utf-8") as f:
        f.write(dash)
    print(f"Dashboard: {original_len} -> {new_len} chars ({new_len - original_len:+d})")
else:
    print("Dashboard: no changes")
