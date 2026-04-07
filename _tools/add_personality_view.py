#!/usr/bin/env python3
"""Add personality view to HA dashboard YAML."""
import sys

YAML_PATH = "/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml"
MARKER = "  - path: sub-calendar-tasks"

NEW_VIEW = """  - path: sub-personality
    title: "\u0627\u0644\u0634\u062e\u0635\u064a\u0629"
    icon: mdi:account-star
    subview: true
    type: panel
    cards:
      - type: iframe
        url: https://ai.salem-home.com/trading/personality
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

if "sub-personality" in content:
    print("Already exists!")
    sys.exit(0)

if MARKER not in content:
    print(f"Marker not found: {MARKER}")
    sys.exit(1)

content = content.replace(MARKER, NEW_VIEW + MARKER)

with open(YAML_PATH, "w") as f:
    f.write(content)

print("Done! Personality view added.")
