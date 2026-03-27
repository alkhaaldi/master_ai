#!/usr/bin/env python3
"""Add sub-email and sub-news pages to dashboard + activate news & email nav buttons.
Run on RPi: /var/lib/homeassistant/venv/bin/python /var/lib/homeassistant/share/master_ai/_tools/add_pages.py
"""
import sys

YAML_PATH = "/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml"

with open(YAML_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# ──────────────────────────────────────────────
# 1. Activate the "news" nav button (full pattern from actual file)
# ──────────────────────────────────────────────
old_news_btn = """                  - type: custom:button-card
                    name: \u0627\u0644\u0623\u062e\u0628\u0627\u0631
                    icon: mdi:newspaper-variant-outline
                    tap_action:
                      action: none
                    styles:
                      card:
                        - height: 72px
                        - border-radius: 20px
                        - background: rgba(255,255,255,0.02)
                        - border: 1px solid rgba(255,255,255,0.06)
                        - opacity: "0.4"
                      name:
                        - font-size: 13px
                        - font-weight: 700
                      icon:
                        - width: 26px
                        - color: grey"""

new_news_btn = """                  - type: custom:button-card
                    name: \u0627\u0644\u0623\u062e\u0628\u0627\u0631
                    icon: mdi:newspaper-variant-outline
                    tap_action:
                      action: navigate
                      navigation_path: /master-ai-dashboard/sub-news
                    styles:
                      card:
                        - height: 72px
                        - border-radius: 20px
                        - background: "linear-gradient(135deg, rgba(255,200,60,0.10), rgba(255,200,60,0.03))"
                        - border: 1px solid rgba(255,200,60,0.16)
                      name:
                        - font-size: 13px
                        - font-weight: 700
                      icon:
                        - width: 26px
                        - color: rgb(255,200,60)"""

if old_news_btn in content:
    content = content.replace(old_news_btn, new_news_btn)
    changes += 1
    print("[1/4] NEWS button activated")
else:
    print("[1/4] WARNING: news button not found (may already be active)")

# ──────────────────────────────────────────────
# 2. Change nav grid from columns:3 to columns:4
# ──────────────────────────────────────────────
old_grid = """              - type: grid
                columns: 3
                square: false
                cards:
                  - type: custom:button-card
                    name: \u0627\u0644\u0631\u0627\u062f\u0627\u0631"""

new_grid = """              - type: grid
                columns: 4
                square: false
                cards:
                  - type: custom:button-card
                    name: \u0627\u0644\u0631\u0627\u062f\u0627\u0631"""

if old_grid in content:
    content = content.replace(old_grid, new_grid)
    changes += 1
    print("[2/4] Grid changed to 4 columns")
else:
    print("[2/4] WARNING: grid pattern not found")

# ──────────────────────────────────────────────
# 3. Insert EMAIL nav button before news button
# ──────────────────────────────────────────────
email_btn = """                  - type: custom:button-card
                    name: \u0627\u0644\u0628\u0631\u064a\u062f
                    icon: mdi:email-outline
                    tap_action:
                      action: navigate
                      navigation_path: /master-ai-dashboard/sub-email
                    styles:
                      card:
                        - height: 72px
                        - border-radius: 20px
                        - background: "linear-gradient(135deg, rgba(0,140,255,0.10), rgba(0,140,255,0.03))"
                        - border: 1px solid rgba(0,140,255,0.16)
                      name:
                        - font-size: 13px
                        - font-weight: 700
                      icon:
                        - width: 26px
                        - color: rgb(0,140,255)

"""

news_marker = """                  - type: custom:button-card
                    name: \u0627\u0644\u0623\u062e\u0628\u0627\u0631
                    icon: mdi:newspaper-variant-outline"""

if news_marker in content:
    content = content.replace(news_marker, email_btn + news_marker, 1)
    changes += 1
    print("[3/4] EMAIL button inserted")
else:
    print("[3/4] WARNING: news marker not found")

# ──────────────────────────────────────────────
# 4. Add sub-email and sub-news subviews at end
# ──────────────────────────────────────────────
email_view = (
  "\n"
  "  # \u2550\u2550\u2550 EMAIL PAGE \u2550\u2550\u2550\n"
  "  - path: sub-email\n"
  '    title: "\u0627\u0644\u0628\u0631\u064a\u062f"\n'
  "    icon: mdi:email-outline\n"
  "    type: panel\n"
  "    cards:\n"
  "      - type: custom:stack-in-card\n"
  "        mode: vertical\n"
  "        card_mod:\n"
  "          style: |\n"
  "            ha-card { background: transparent; box-shadow: none; padding: 8px; }\n"
  "        cards:\n"
  "          - type: custom:mushroom-title-card\n"
  '            title: "\U0001f4e8 \u0627\u0644\u0628\u0631\u064a\u062f"\n'
  "            subtitle: >\n"
  "              {%- set e = 'sensor.master_ai_extended' -%}\n"
  "              {{ state_attr(e,'email_total') | default(0) }} \u0631\u0633\u0627\u0644\u0629 \u00b7 {{ state_attr(e,'email_unread') | default(0) }} \u063a\u064a\u0631 \u0645\u0642\u0631\u0648\u0621\u0629\n"
  "            tap_action:\n"
  "              action: navigate\n"
  "              navigation_path: /master-ai-dashboard/master-ai\n"
  "\n"
)
email_view += (
  "          # Email Stats\n"
  "          - type: custom:stack-in-card\n"
  "            mode: vertical\n"
  "            card_mod:\n"
  "              style: |\n"
  "                ha-card {\n"
  "                  background: linear-gradient(180deg, rgba(17,24,34,0.98), rgba(10,12,16,0.99));\n"
  "                  border: 1px solid rgba(0,140,255,0.10);\n"
  "                  border-radius: 26px;\n"
  "                  padding: 14px;\n"
  "                }\n"
  "            cards:\n"
  "              - type: grid\n"
  "                columns: 4\n"
  "                square: false\n"
  "                cards:\n"
  "                  - type: custom:mushroom-template-card\n"
  "                    primary: \"{{ state_attr('sensor.master_ai_extended','email_total') | default(0) }}\"\n"
  '                    secondary: "\u0625\u062c\u0645\u0627\u0644\u064a"\n'
  "                    icon: mdi:email\n"
  "                    icon_color: blue\n"
  "                  - type: custom:mushroom-template-card\n"
  "                    primary: \"{{ state_attr('sensor.master_ai_extended','email_unread') | default(0) }}\"\n"
  '                    secondary: "\u063a\u064a\u0631 \u0645\u0642\u0631\u0648\u0621"\n'
  "                    icon: mdi:email-alert\n"
  "                    icon_color: amber\n"
  "                  - type: custom:mushroom-template-card\n"
  "                    primary: \"{{ state_attr('sensor.master_ai_extended','email_critical') | default(0) }}\"\n"
  '                    secondary: "\u0639\u0627\u062c\u0644"\n'
  "                    icon: mdi:alert-circle\n"
  "                    icon_color: red\n"
)
email_view += (
  "                  - type: custom:mushroom-template-card\n"
  "                    primary: \"{{ state_attr('sensor.master_ai_extended','email_high') | default(0) }}\"\n"
  '                    secondary: "\u0645\u0647\u0645"\n'
  "                    icon: mdi:alert\n"
  "                    icon_color: orange\n"
  "\n"
  "          # Email List\n"
  "          - type: custom:stack-in-card\n"
  "            mode: vertical\n"
  "            card_mod:\n"
  "              style: |\n"
  "                ha-card {\n"
  "                  background: linear-gradient(180deg, rgba(17,24,34,0.98), rgba(10,12,16,0.99));\n"
  "                  border: 1px solid rgba(0,140,255,0.10);\n"
  "                  border-radius: 26px;\n"
  "                  padding: 14px;\n"
  "                  margin-top: 12px;\n"
  "                }\n"
  "            cards:\n"
  "              - type: custom:mushroom-title-card\n"
  '                title: "\u0627\u0644\u0631\u0633\u0627\u0626\u0644"\n'
  '                subtitle: "\u0622\u062e\u0631 24 \u0633\u0627\u0639\u0629"\n'
  "              - type: markdown\n"
  "                card_mod:\n"
  "                  style: |\n"
  "                    ha-card { background: rgba(0,0,0,0.25); border-radius: 16px; padding: 8px 14px; }\n"
  "                    ha-markdown { font-size: 13px; }\n"
  "                content: |\n"
  "                  {%- set e = 'sensor.master_ai_extended' -%}\n"
)
email_view += (
  "                  {%- set msgs = state_attr(e,'email_messages') -%}\n"
  "                  {%- if msgs and msgs | length > 0 -%}\n"
  "                  {%- for m in msgs -%}\n"
  "                  {{ m.priority_label }} **{{ m['from'] }}** \u00b7 {{ m.source_label }}\n"
  "                  {{ m.subject }}{% if m.time %} \u23f0 {{ m.time }}{% endif %}\n"
  "\n"
  "                  {%- endfor -%}\n"
  "                  {%- else -%}\n"
  "                  \U0001f4ec \u0644\u0627 \u062a\u0648\u062c\u062f \u0631\u0633\u0627\u0626\u0644\n"
  "                  {%- endif -%}\n"
)

# ── NEWS VIEW ──
news_view = (
  "\n"
  "  # \u2550\u2550\u2550 NEWS PAGE \u2550\u2550\u2550\n"
  "  - path: sub-news\n"
  '    title: "\u0627\u0644\u0623\u062e\u0628\u0627\u0631"\n'
  "    icon: mdi:newspaper-variant-outline\n"
  "    type: panel\n"
  "    cards:\n"
  "      - type: custom:stack-in-card\n"
  "        mode: vertical\n"
  "        card_mod:\n"
  "          style: |\n"
  "            ha-card { background: transparent; box-shadow: none; padding: 8px; }\n"
  "        cards:\n"
  "          - type: custom:mushroom-title-card\n"
  '            title: "\U0001f4f0 \u0627\u0644\u0623\u062e\u0628\u0627\u0631"\n'
)
news_view += (
  "            subtitle: >\n"
  "              {%- set e = 'sensor.master_ai_extended' -%}\n"
  "              {%- if state_attr(e,'news_available') -%}\n"
  "              \u0622\u062e\u0631 \u0645\u0644\u062e\u0635 \u062c\u0627\u0647\u0632\n"
  "              {%- else -%}\n"
  "              \u0644\u0627 \u064a\u0648\u062c\u062f \u0645\u0644\u062e\u0635 \u2014 \u0627\u0633\u062a\u062e\u062f\u0645 /news_now\n"
  "              {%- endif -%}\n"
  "            tap_action:\n"
  "              action: navigate\n"
  "              navigation_path: /master-ai-dashboard/master-ai\n"
  "\n"
  "          # News Digest\n"
  "          - type: custom:stack-in-card\n"
  "            mode: vertical\n"
  "            card_mod:\n"
  "              style: |\n"
  "                ha-card {\n"
  "                  background: linear-gradient(180deg, rgba(17,24,34,0.98), rgba(10,12,16,0.99));\n"
  "                  border: 1px solid rgba(255,200,60,0.10);\n"
  "                  border-radius: 26px;\n"
  "                  padding: 14px;\n"
  "                }\n"
  "            cards:\n"
  "              - type: custom:mushroom-title-card\n"
  '                title: "\u0645\u0644\u062e\u0635 \u0627\u0644\u0623\u062e\u0628\u0627\u0631"\n'
  "                subtitle: >\n"
  "                  {%- set e = 'sensor.master_ai_extended' -%}\n"
  "                  {%- set d = state_attr(e,'news_digest') -%}\n"
)
news_view += (
  "                  {%- if d and d.category_ar -%}\n"
  "                  {{ d.category_emoji | default('\U0001f4f0') }} {{ d.category_ar }} \u00b7 {{ d.item_count | default(0) }} \u062e\u0628\u0631\n"
  "                  {%- else -%}\n"
  "                  \u0644\u0627 \u064a\u0648\u062c\u062f \u0645\u0644\u062e\u0635\n"
  "                  {%- endif -%}\n"
  "              - type: markdown\n"
  "                card_mod:\n"
  "                  style: |\n"
  "                    ha-card { background: rgba(0,0,0,0.25); border-radius: 16px; padding: 8px 14px; }\n"
  "                    ha-markdown { font-size: 14px; line-height: 1.7; }\n"
  "                content: |\n"
  "                  {%- set e = 'sensor.master_ai_extended' -%}\n"
  "                  {%- set d = state_attr(e,'news_digest') -%}\n"
  "                  {%- if d and d.summary -%}\n"
  "                  {{ d.summary }}\n"
  "\n"
  "                  ---\n"
  "                  \U0001f4c5 {{ d.date | default('') }} \u00b7 {{ d.created_at | default('') | truncate(16, true, '') }}\n"
  "                  {%- else -%}\n"
  "                  \u0644\u0627 \u064a\u0648\u062c\u062f \u0645\u0644\u062e\u0635 \u062c\u0627\u0647\u0632.\n"
  "\n"
  "                  \u0627\u0633\u062a\u062e\u062f\u0645 **/news_now** \u0639\u0628\u0631 \u062a\u0644\u064a\u0642\u0631\u0627\u0645 \u0644\u062a\u0648\u0644\u064a\u062f \u0645\u0644\u062e\u0635 \u062c\u062f\u064a\u062f.\n"
  "                  {%- endif -%}\n"
)

# Apply views
if 'path: sub-email' in content:
    print("[4a/4] SKIP: sub-email already exists")
else:
    content = content.rstrip() + '\n' + email_view
    changes += 1
    print("[4a/4] sub-email view added")

if 'path: sub-news' in content:
    print("[4b/4] SKIP: sub-news already exists")
else:
    content = content.rstrip() + '\n' + news_view
    changes += 1
    print("[4b/4] sub-news view added")

# ──────────────────────────────────────────────
# Write back
# ──────────────────────────────────────────────
if changes == 0:
    print("NO CHANGES - already applied?")
    sys.exit(1)

with open(YAML_PATH, 'w', encoding='utf-8') as f:
    f.write(content)

total_lines = content.count('\n')
print(f"DONE - {changes} changes, {len(content)} chars, {total_lines} lines")
