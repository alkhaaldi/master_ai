#!/usr/bin/env python3
"""Phase 5: Update home page — add portfolio preview after stock teaser."""
import os

DASH = "/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml"
if not os.path.exists(DASH):
    DASH = os.path.join(os.path.dirname(__file__), "..", "..", "master_ai_dashboard.yaml")

with open(DASH, "r", encoding="utf-8") as f:
    content = f.read()

original_len = len(content)

# Add portfolio preview card after stock teaser, before COMMAND FEEDBACK
# Insert a small portfolio preview card
portfolio_preview = '''
          # ── PORTFOLIO PREVIEW ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: linear-gradient(135deg, rgba(39,174,96,0.06), rgba(39,174,96,0.03));
                  border: 1px solid rgba(39,174,96,0.12);
                  border-radius: 18px;
                  padding: 10px 16px;
                  margin-top: 6px;
                  cursor: pointer;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.7; }
            content: >
              {% set p = 'sensor.master_ai_portfolio' %}
              {% set opens = state_attr(p,'open_positions') or [] %}
              {% if opens | length > 0 %}
              \U0001f4c2 **{{ opens | length }} \u0635\u0641\u0642\u0629 \u0645\u0641\u062a\u0648\u062d\u0629**{% set total_pnl = namespace(v=0) %}{% for t in opens %}{% if t.pnl_fils is defined %}{% set total_pnl.v = total_pnl.v + t.pnl_fils %}{% endif %}{% endfor %}{% if total_pnl.v != 0 %} \u00b7 {% if total_pnl.v > 0 %}\U0001f7e2{% else %}\U0001f534{% endif %} {{ total_pnl.v | round(0) }} \u0641\u0644\u0633{% endif %}
              {% else %}
              \U0001f4c2 \u0644\u0627 \u0635\u0641\u0642\u0627\u062a \u0645\u0641\u062a\u0648\u062d\u0629
              {% endif %}

'''

# Find the first COMMAND FEEDBACK on home page (line ~221)
marker = "          # \u2500\u2500 6. COMMAND FEEDBACK (V12: hidden when empty) \u2500\u2500"
if marker in content:
    content = content.replace(marker, portfolio_preview + marker, 1)  # only first occurrence
    print("OK: Portfolio preview inserted on home page")
else:
    print("WARN: COMMAND FEEDBACK marker not found")

new_len = len(content)
if new_len > original_len:
    with open(DASH, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"DONE — {original_len} -> {new_len} chars (+{new_len - original_len})")
else:
    print("ERROR: no changes made")
