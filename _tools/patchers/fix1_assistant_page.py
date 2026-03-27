#!/usr/bin/env python3
"""Fix 1: Create sub-assistant page in dashboard YAML."""
import os

DASH = "/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml"
if not os.path.exists(DASH):
    print("WARN: dashboard not found")
    exit(1)

with open(DASH, "r", encoding="utf-8") as f:
    content = f.read()

original_len = len(content)

# Replace the empty placeholder with actual page
old_placeholder = """  # ===================================
  # SUBVIEW: ASSISTANT
  # ===================================
  # SUBVIEW: ASSISTANT
  # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
  - path: sub-system-health"""

new_page = """  # ═══════════════════════════════════════
  - path: sub-assistant
    title: المساعد
    icon: mdi:robot-outline
    subview: true
    type: panel
    cards:
      - type: vertical-stack
        cards:

          # ── PULSE HERO ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: linear-gradient(135deg, rgba(52,152,219,0.10), rgba(52,152,219,0.04));
                  border: 1px solid rgba(52,152,219,0.12);
                  border-radius: 18px;
                  padding: 10px 16px 6px;
                  margin: 6px 8px 0;
                }
                h2 { font-size: 18px !important; margin: 0 !important; }
                ha-markdown { font-size: 14px; opacity: 0.85; direction: rtl; }
            content: |
              ## المساعد الذكي
              {% set e = 'sensor.master_ai_extended' %}
              🧠 {{ state_attr(e,'memory_total') | int(0) }} ذاكرة · 📊 {{ state_attr(e,'total_requests') | int(0) }} طلب · 💰 ${{ state_attr(e,'cost_total_usd') | float(0) | round(2) }}

          # ── MEMORY STATS ──
          - type: grid
            columns: 4
            square: false
            cards:
              - type: markdown
                card_mod:
                  style: |
                    ha-card { background: rgba(52,152,219,0.05); border: 1px solid rgba(52,152,219,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set m = state_attr('sensor.master_ai_extended','memory_by_type') or {} %}
                  📅 **{{ m.get('event',0) }}**

                  أحداث
              - type: markdown
                card_mod:
                  style: |
                    ha-card { background: rgba(52,152,219,0.05); border: 1px solid rgba(52,152,219,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set m = state_attr('sensor.master_ai_extended','memory_by_type') or {} %}
                  📝 **{{ m.get('fact',0) }}**

                  حقائق
              - type: markdown
                card_mod:
                  style: |
                    ha-card { background: rgba(52,152,219,0.05); border: 1px solid rgba(52,152,219,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set m = state_attr('sensor.master_ai_extended','memory_by_type') or {} %}
                  🔧 **{{ m.get('correction',0) }}**

                  تصحيحات
              - type: markdown
                card_mod:
                  style: |
                    ha-card { background: rgba(52,152,219,0.05); border: 1px solid rgba(52,152,219,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set m = state_attr('sensor.master_ai_extended','memory_by_type') or {} %}
                  ⭐ **{{ m.get('preference',0) }}**

                  تفضيلات

          # ── COST CARDS ──
          - type: grid
            columns: 3
            square: false
            cards:
              - type: markdown
                card_mod:
                  style: |
                    ha-card { background: rgba(39,174,96,0.05); border: 1px solid rgba(39,174,96,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set e = 'sensor.master_ai_extended' %}
                  💰 **${{ state_attr(e,'cost_today_usd') | float(0) | round(3) }}**

                  تكلفة اليوم
              - type: markdown
                card_mod:
                  style: |
                    ha-card { background: rgba(39,174,96,0.05); border: 1px solid rgba(39,174,96,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set e = 'sensor.master_ai_extended' %}
                  💵 **${{ state_attr(e,'cost_total_usd') | float(0) | round(2) }}**

                  التكلفة الإجمالية
              - type: markdown
                card_mod:
                  style: |
                    ha-card { border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set e = 'sensor.master_ai_extended' %}
                  📊 **{{ state_attr(e,'total_requests') | int(0) }}**

                  طلب (${{ state_attr(e,'avg_cost_per_request') | float(0) | round(3) }}/req)

          # ── TOOL USAGE ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(255,255,255,0.02);
                  border: 1px solid rgba(255,255,255,0.06);
                  border-radius: 18px;
                  padding: 14px 16px;
                  margin: 10px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set e = 'sensor.master_ai_extended' %}
              {% set tools = state_attr(e,'tool_usage') or [] %}
              {% if tools | length > 0 %}
              **🔧 استخدام الأدوات**

              | الأداة | العدد |
              |:------|------:|
              {% for t in tools %}| {{ t.tool }} | {{ t.count }} |
              {% endfor %}
              {% else %}
              🔧 لا بيانات أدوات
              {% endif %}

          # ── GIT LOG ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(180,120,255,0.04);
                  border: 1px solid rgba(180,120,255,0.10);
                  border-radius: 18px;
                  padding: 14px 16px;
                  margin: 10px 8px 0;
                }
                ha-markdown { font-size: 13px; direction: ltr; line-height: 1.7; font-family: monospace; }
            content: |
              {% set e = 'sensor.master_ai_extended' %}
              {% set logs = state_attr(e,'git_log') or [] %}
              {% if logs | length > 0 %}
              **📜 Git Log** (آخر {{ logs | length }})

              {% for l in logs %}
              `{{ l }}`
              {% endfor %}
              {% else %}
              📜 لا سجل git
              {% endif %}

          # ── ANOMALIES ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  {% set a = state_attr('sensor.master_ai_extended','anomalies_today') | int(0) %}
                  {% if a > 0 %}
                  background: rgba(231,76,60,0.08);
                  border: 2px solid rgba(231,76,60,0.20);
                  {% else %}
                  background: rgba(39,174,96,0.04);
                  border: 1px solid rgba(39,174,96,0.10);
                  {% endif %}
                  border-radius: 18px;
                  padding: 10px 16px;
                  margin: 10px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; }
            content: |
              {% set e = 'sensor.master_ai_extended' %}
              {% set a = state_attr(e,'anomalies_today') | int(0) %}
              {% if a > 0 %}
              ⚠️ **{{ a }} شذوذ اليوم** — استخدم /anomaly للتفاصيل
              {% else %}
              ✅ لا شذوذ اليوم
              {% endif %}

          # ── QUICK ACTIONS ──
          - type: grid
            columns: 3
            square: false
            cards:
              - type: button
                name: النظام
                icon: mdi:server
                tap_action:
                  action: navigate
                  navigation_path: /master-ai-dashboard/sub-system-health
                show_state: false
              - type: button
                name: الرئيسية
                icon: mdi:home
                tap_action:
                  action: navigate
                  navigation_path: /master-ai-dashboard/master-ai
                show_state: false
              - type: button
                name: باك أب
                icon: mdi:backup-restore
                tap_action:
                  action: call-service
                  service: script.turn_on
                  target:
                    entity_id: script.master_ai_backup
                show_state: false

  # ═══════════════════════════════════════
  - path: sub-system-health"""

if old_placeholder in content:
    content = content.replace(old_placeholder, new_page)
    with open(DASH, "w", encoding="utf-8") as f:
        f.write(content)
    new_len = len(content)
    print(f"OK: sub-assistant page created ({original_len} -> {new_len}, +{new_len - original_len} chars)")
else:
    print("WARN: placeholder not found, trying alternative")
    # Try just inserting before sub-system-health
    alt_marker = "  # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\n  - path: sub-system-health"
    if alt_marker in content:
        # Build just the page part (without the system separator at end)
        page_only = new_page.rsplit("\n  # ", 1)[0] + "\n\n  # "
        content = content.replace(alt_marker, page_only + alt_marker)
        with open(DASH, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"OK: sub-assistant page inserted (alt method)")
    else:
        print("FAILED: no suitable marker found")
