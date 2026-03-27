#!/usr/bin/env python3
"""Fix 7: Add backup button to system page."""
import os

DASH = "/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml"
if not os.path.exists(DASH):
    print("WARN: dashboard not found")
    exit(1)

with open(DASH, "r", encoding="utf-8") as f:
    content = f.read()

# Find the system page's COMMAND FEEDBACK (the one right before sub-email)
# Unique marker: the COMMAND FEEDBACK followed by "EMAIL PAGE"
marker = """          # \u2500\u2500 COMMAND FEEDBACK \u2500\u2500
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  {% if not state_attr('sensor.master_ai_dashboard','last_cmd_command') %}
                  display: none;
                  {% else %}
                  background: rgba(255,255,255,0.02);
                  border: 1px solid rgba(255,255,255,0.06);
                  border-radius: 16px;
                  padding: 6px 14px;
                  margin-top: 6px;
                  {% endif %}
                }
                ha-markdown { font-size: 14px; opacity: 0.85; direction: rtl; }
            content: >
              {% set d = 'sensor.master_ai_dashboard' %}
              {% set cmd = state_attr(d,'last_cmd_command') | default('') %}
              {% if cmd %}
              {% set st = state_attr(d,'last_cmd_status') | default('?') %}
              {% if st == 'done' %}\u2705{% elif st == 'error' %}\u274c{% elif st == 'timeout' %}\u23f3{% else %}\U0001f504{% endif %}
              **{{ cmd }}** @ {{ state_attr(d,'last_cmd_time') | default('') }}
              \u00b7 {{ state_attr(d,'last_cmd_result') | default('') | truncate(60) }}
              {% endif %}


  # \u2550\u2550\u2550 EMAIL PAGE \u2550\u2550\u2550"""

backup_section = """          # \u2500\u2500 SYSTEM ACTIONS \u2500\u2500
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
                icon: mdi:cog-outline
                tap_action:
                  action: call-service
                  service: script.turn_on
                  target:
                    entity_id: script.master_ai_radar_status
                show_state: false

"""

if marker in content:
    content = content.replace(marker, backup_section + marker)
    with open(DASH, "w", encoding="utf-8") as f:
        f.write(content)
    print("Fix7: Backup button added to system page")
else:
    print("Fix7: WARN — marker not found. Trying alternative...")
    # Try simpler marker
    alt = "  # \u2550\u2550\u2550 EMAIL PAGE \u2550\u2550\u2550"
    if alt in content:
        content = content.replace(alt, backup_section + alt, 1)
        with open(DASH, "w", encoding="utf-8") as f:
            f.write(content)
        print("Fix7: Backup button added (alt method)")
    else:
        print("Fix7: FAILED — no marker found")
