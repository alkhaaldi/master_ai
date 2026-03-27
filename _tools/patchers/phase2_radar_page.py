#!/usr/bin/env python3
"""Phase 2: Improve radar page — add signal history + navigation."""
import os

DASH = "/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml"
# Fallback for local testing
if not os.path.exists(DASH):
    DASH = os.path.join(os.path.dirname(__file__), "..", "..", "master_ai_dashboard.yaml")

with open(DASH, "r", encoding="utf-8") as f:
    content = f.read()

original_len = len(content)

# 1. Insert SIGNAL HISTORY before DIAGNOSTICS FOOTER
signal_history_block = '''
          # ── SIGNAL HISTORY ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(180,120,255,0.04);
                  border: 1px solid rgba(180,120,255,0.10);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 10px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set a = 'sensor.master_ai_analysis' %}
              {% set hist = state_attr(a,'signal_history') %}
              {% if hist and hist | length > 0 %}
              **\U0001f4dc \u0633\u062c\u0644 \u0627\u0644\u0625\u0634\u0627\u0631\u0627\u062a** (\u0622\u062e\u0631 {{ hist | length }})

              | \u0627\u0644\u0633\u0647\u0645 | \u0627\u0644\u0646\u0648\u0639 | \u0627\u0644\u0633\u0639\u0631 | Score | \u0627\u0644\u0648\u0642\u062a |
              |:------|:-----:|------:|:-----:|:-----:|
              {% for s in hist[:10] %}| {{ s.symbol }} | {% if s.type == 'bullish_cross' %}\U0001f7e2{% else %}\U0001f534{% endif %} | {{ s.price }} | {{ s.score }} | {{ s.time[-11:-3] if s.time | length > 11 else s.time }} |
              {% endfor %}
              {% else %}
              \U0001f4dc \u0644\u0627 \u0633\u062c\u0644 \u0625\u0634\u0627\u0631\u0627\u062a
              {% endif %}

'''

marker = "          # ── L7: DIAGNOSTICS FOOTER ──"
if marker in content:
    content = content.replace(marker, signal_history_block + marker)
    print("OK: Signal History inserted before DIAGNOSTICS")
else:
    print("WARN: DIAGNOSTICS marker not found")

# 2. Insert NAVIGATION before the next page separator
nav_block = '''
          # ── TRADING NAV ──
          - type: grid
            columns: 3
            square: false
            cards:
              - type: button
                name: \u0627\u0644\u0645\u062d\u0641\u0638\u0629
                icon: mdi:wallet-outline
                tap_action:
                  action: navigate
                  navigation_path: /master-ai-dashboard/sub-portfolio
                show_state: false
              - type: button
                name: \u0627\u0644\u062a\u062d\u0644\u064a\u0644
                icon: mdi:chart-scatter-plot
                tap_action:
                  action: navigate
                  navigation_path: /master-ai-dashboard/sub-analysis
                show_state: false
              - type: button
                name: \u0627\u0644\u0631\u0626\u064a\u0633\u064a\u0629
                icon: mdi:home
                tap_action:
                  action: navigate
                  navigation_path: /master-ai-dashboard/master-ai
                show_state: false

'''

# Insert before calendar page
cal_marker = "  # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\n  - path: sub-calendar-tasks"
if cal_marker in content:
    content = content.replace(cal_marker, nav_block + cal_marker)
    print("OK: Navigation inserted before calendar page")
else:
    print("WARN: calendar marker not found")

new_len = len(content)
if new_len > original_len:
    with open(DASH, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"DONE — {original_len} -> {new_len} chars (+{new_len - original_len})")
else:
    print("ERROR: no changes made, not writing")
