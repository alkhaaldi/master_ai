#!/usr/bin/env python3
"""Add Confluence nav button to trading nav + home page."""
from pathlib import Path

YAML_PATH = Path("/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml")
content = YAML_PATH.read_text(encoding="utf-8")
changed = False

# 1. Add to radar trading nav links
OLD_RADAR_NAV = "[المحفظة](/master-ai-dashboard/sub-portfolio) · [التحليل](/master-ai-dashboard/sub-analysis) · [السجل](/master-ai-dashboard/sub-journal) · [التنبيهات](/master-ai-dashboard/sub-alerts)"
NEW_RADAR_NAV = "[المحفظة](/master-ai-dashboard/sub-portfolio) · [التحليل](/master-ai-dashboard/sub-analysis) · [السجل](/master-ai-dashboard/sub-journal) · [التنبيهات](/master-ai-dashboard/sub-alerts) · [🎯 Confluence](/master-ai-dashboard/sub-confluence)"

if OLD_RADAR_NAV in content:
    content = content.replace(OLD_RADAR_NAV, NEW_RADAR_NAV, 1)
    changed = True
    print("1. Radar trading nav — Confluence link added ✓")
else:
    print("1. Radar nav — SKIP (pattern not found)")

# 2. Add Confluence nav button to home page (after الأخبار button)
OLD_HOME_NEWS_BTN = """              - type: button
                name: الأخبار
                icon: mdi:newspaper-variant-outline
                tap_action:
                  action: navigate
                  navigation_path: /master-ai-dashboard/sub-news
                show_state: false"""

NEW_HOME_NEWS_BTN = """              - type: button
                name: الأخبار
                icon: mdi:newspaper-variant-outline
                tap_action:
                  action: navigate
                  navigation_path: /master-ai-dashboard/sub-news
                show_state: false
              - type: button
                name: القرار
                icon: mdi:target
                tap_action:
                  action: navigate
                  navigation_path: /master-ai-dashboard/sub-confluence
                show_state: false"""

if OLD_HOME_NEWS_BTN in content:
    # Also update columns from 7 to 8
    content = content.replace("          # ── 7. NAVIGATION (V12: 7 columns) ──\n          - type: grid\n            columns: 7",
                              "          # ── 7. NAVIGATION (V12: 8 columns) ──\n          - type: grid\n            columns: 8", 1)
    content = content.replace(OLD_HOME_NEWS_BTN, NEW_HOME_NEWS_BTN, 1)
    changed = True
    print("2. Home page nav — Confluence button added ✓")
else:
    print("2. Home page nav — SKIP")

if changed:
    YAML_PATH.write_text(content, encoding="utf-8")
    import yaml
    try:
        yaml.safe_load(content)
        print("YAML validation: OK ✓")
    except yaml.YAMLError as e:
        print(f"YAML ERROR: {e}")
