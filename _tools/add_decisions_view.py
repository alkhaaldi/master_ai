#!/usr/bin/env python3
"""Add decisions view to HA dashboard YAML."""
YAML_PATH = "/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml"
MARKER = '  - path: sub-personality'

NEW_VIEW = """  - path: sub-decisions
    title: "\u0627\u0644\u0642\u0631\u0627\u0631\u0627\u062a"
    icon: mdi:lightning-bolt
    subview: true
    type: panel
    cards:
      - type: iframe
        url: https://ai.salem-home.com/trading/decisions
        aspect_ratio: 100%
        card_mod:
          style: |
            ha-card {
              overflow: hidden;
              border: none;
              border-radius: 0;
              background: #070D17;
            }

"""

with open(YAML_PATH, "r") as f:
    content = f.read()
if "sub-decisions" in content:
    print("Already exists!")
else:
    content = content.replace(MARKER, NEW_VIEW + MARKER)
    with open(YAML_PATH, "w") as f:
        f.write(content)
    print("Done! Decisions view added.")
