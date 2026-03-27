#!/usr/bin/env python3
"""Phase 3+4: Add portfolio (sub-portfolio) and analysis (sub-analysis) pages."""
import os

DASH = "/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml"
if not os.path.exists(DASH):
    DASH = os.path.join(os.path.dirname(__file__), "..", "..", "master_ai_dashboard.yaml")

with open(DASH, "r", encoding="utf-8") as f:
    content = f.read()

original_len = len(content)

# ── PORTFOLIO PAGE ──
portfolio_page = '''
  # ═══════════════════════════════════════
  - path: sub-portfolio
    title: المحفظة
    icon: mdi:wallet-outline
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
                  background: linear-gradient(135deg, rgba(39,174,96,0.10), rgba(39,174,96,0.04));
                  border: 1px solid rgba(39,174,96,0.12);
                  border-radius: 18px;
                  padding: 10px 16px 6px;
                  margin: 6px 8px 0;
                }
                h2 { font-size: 18px !important; margin: 0 !important; }
                ha-markdown { font-size: 14px; opacity: 0.85; direction: rtl; }
            content: |
              ## المحفظة
              {% set p = 'sensor.master_ai_portfolio' %}
              {% set opens = state_attr(p,'open_positions') or [] %}
              {% set s30 = state_attr(p,'stats_30d') or {} %}
              📂 {{ opens | length }} صفقة مفتوحة · {{ s30.get('total_trades',0) }} صفقة (30 يوم) · {{ (s30.get('win_rate',0) * 100) | round(0) }}% فوز

          # ── OPEN POSITIONS ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: linear-gradient(135deg, rgba(39,174,96,0.06), rgba(39,174,96,0.02));
                  border: 2px solid rgba(39,174,96,0.15);
                  border-radius: 18px;
                  padding: 14px 16px;
                  margin: 10px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.9; }
            content: |
              {% set p = 'sensor.master_ai_portfolio' %}
              {% set trades = state_attr(p,'open_positions') or [] %}
              {% if trades | length > 0 %}
              **📂 صفقات مفتوحة** ({{ trades | length }})

              | السهم | الدخول | الحالي | P&L | الكمية | الاستراتيجية |
              |:------|------:|------:|----:|------:|:------------|
              {% for t in trades %}| {{ t.name_ar | default(t.symbol) }} | {{ t.entry_price }} | {{ t.current_price | default('—') }} | {% if t.pnl_pct is defined %}{% if t.pnl_pct >= 0 %}🟢 +{{ t.pnl_pct }}%{% else %}🔴 {{ t.pnl_pct }}%{% endif %}{% else %}—{% endif %} | {{ t.quantity }} | {{ t.strategy | default('—') }} |
              {% endfor %}
              {% else %}
              📂 لا صفقات مفتوحة — استخدم /trade أو اضغط "شريت" على إشارة الرادار
              {% endif %}

          # ── SIGNAL vs TRADE ──
          - type: grid
            columns: 3
            square: false
            cards:
              - type: markdown
                card_mod:
                  style: |
                    ha-card { border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set p = 'sensor.master_ai_portfolio' %}
                  {% set svt = state_attr(p,'signal_vs_trade') or {} %}
                  📡 **{{ svt.get('signals_7d',0) }}**

                  إشارات 7 أيام
              - type: markdown
                card_mod:
                  style: |
                    ha-card { border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set p = 'sensor.master_ai_portfolio' %}
                  {% set svt = state_attr(p,'signal_vs_trade') or {} %}
                  ✅ **{{ svt.get('confirmed_7d',0) }}**

                  صفقات منفذة
              - type: markdown
                card_mod:
                  style: |
                    ha-card { border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set p = 'sensor.master_ai_portfolio' %}
                  {% set svt = state_attr(p,'signal_vs_trade') or {} %}
                  ⏭ **{{ svt.get('skip_rate',0) }}%**

                  نسبة التجاهل

          # ── CLOSED TRADES ──
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
              {% set p = 'sensor.master_ai_portfolio' %}
              {% set closed = state_attr(p,'closed_trades') or [] %}
              {% if closed | length > 0 %}
              **📊 صفقات مغلقة** (آخر {{ closed | length }})

              | السهم | الدخول | الإغلاق | P&L | السبب |
              |:------|------:|------:|----:|:-----:|
              {% for t in closed[:10] %}| {{ t.symbol }} | {{ t.entry_price }} | {{ t.exit_price | default('—') }} | {% if t.pnl_pct is defined %}{% if t.pnl_pct >= 0 %}🟢{% else %}🔴{% endif %} {{ t.pnl_pct }}%{% else %}—{% endif %} | {{ t.exit_reason | default('—') }} |
              {% endfor %}
              {% else %}
              📊 لا صفقات مغلقة بعد
              {% endif %}

          # ── 30-DAY STATS ──
          - type: grid
            columns: 4
            square: false
            cards:
              - type: markdown
                card_mod:
                  style: |
                    ha-card { background: rgba(39,174,96,0.05); border: 1px solid rgba(39,174,96,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set s = (state_attr('sensor.master_ai_portfolio','stats_30d') or {}) %}
                  📊 **{{ s.get('total_trades',0) }}**

                  صفقة
              - type: markdown
                card_mod:
                  style: |
                    ha-card { background: rgba(39,174,96,0.05); border: 1px solid rgba(39,174,96,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set s = (state_attr('sensor.master_ai_portfolio','stats_30d') or {}) %}
                  🎯 **{{ (s.get('win_rate',0) * 100) | round(0) }}%**

                  فوز
              - type: markdown
                card_mod:
                  style: |
                    ha-card { background: rgba(39,174,96,0.05); border: 1px solid rgba(39,174,96,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set s = (state_attr('sensor.master_ai_portfolio','stats_30d') or {}) %}
                  💰 **{{ s.get('total_pnl_fils',0) | round(0) }}**

                  فلس P&L
              - type: markdown
                card_mod:
                  style: |
                    ha-card { border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set s7 = (state_attr('sensor.master_ai_portfolio','stats_7d') or {}) %}
                  📅 **{{ s7.get('total_trades',0) }}**

                  هالأسبوع

          # ── QUICK ACTIONS ──
          - type: grid
            columns: 4
            square: false
            cards:
              - type: button
                name: الرادار
                icon: mdi:radar
                tap_action:
                  action: navigate
                  navigation_path: /master-ai-dashboard/sub-radar
                show_state: false
              - type: button
                name: التحليل
                icon: mdi:chart-scatter-plot
                tap_action:
                  action: navigate
                  navigation_path: /master-ai-dashboard/sub-analysis
                show_state: false
              - type: button
                name: مراجعة
                icon: mdi:clipboard-check-outline
                tap_action:
                  action: call-service
                  service: rest_command.master_ai_tg_cmd
                  data:
                    command: "/trade_review"
                show_state: false
              - type: button
                name: الرئيسية
                icon: mdi:home
                tap_action:
                  action: navigate
                  navigation_path: /master-ai-dashboard/master-ai
                show_state: false

'''

# ── ANALYSIS PAGE ──
analysis_page = '''
  # ═══════════════════════════════════════
  - path: sub-analysis
    title: التحليل
    icon: mdi:chart-scatter-plot
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
                  background: linear-gradient(135deg, rgba(180,120,255,0.10), rgba(180,120,255,0.04));
                  border: 1px solid rgba(180,120,255,0.12);
                  border-radius: 18px;
                  padding: 10px 16px 6px;
                  margin: 6px 8px 0;
                }
                h2 { font-size: 18px !important; margin: 0 !important; }
                ha-markdown { font-size: 14px; opacity: 0.85; direction: rtl; }
            content: |
              ## التحليل
              {% set a = 'sensor.master_ai_analysis' %}
              {% set ra = state_attr(a,'radar_accuracy') or {} %}
              📡 {{ ra.get('total_signals',0) }} إشارة · 🟢 {{ ra.get('bullish',0) }} صاعد · 🔴 {{ ra.get('bearish',0) }} هابط · ⭐ {{ ra.get('avg_score',0) }} متوسط Score

          # ── RADAR ACCURACY ──
          - type: grid
            columns: 4
            square: false
            cards:
              - type: markdown
                card_mod:
                  style: |
                    ha-card { background: rgba(180,120,255,0.05); border: 1px solid rgba(180,120,255,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set ra = state_attr('sensor.master_ai_analysis','radar_accuracy') or {} %}
                  📡 **{{ ra.get('total_signals',0) }}**

                  إشارة
              - type: markdown
                card_mod:
                  style: |
                    ha-card { background: rgba(39,174,96,0.05); border: 1px solid rgba(39,174,96,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set ra = state_attr('sensor.master_ai_analysis','radar_accuracy') or {} %}
                  🟢 **{{ ra.get('bullish',0) }}**

                  صاعد
              - type: markdown
                card_mod:
                  style: |
                    ha-card { background: rgba(231,76,60,0.05); border: 1px solid rgba(231,76,60,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set ra = state_attr('sensor.master_ai_analysis','radar_accuracy') or {} %}
                  🔴 **{{ ra.get('bearish',0) }}**

                  هابط
              - type: markdown
                card_mod:
                  style: |
                    ha-card { border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set ra = state_attr('sensor.master_ai_analysis','radar_accuracy') or {} %}
                  ⭐ **{{ ra.get('avg_score',0) }}**

                  متوسط Score

          # ── SIGNAL HISTORY ──
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
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set a = 'sensor.master_ai_analysis' %}
              {% set hist = state_attr(a,'signal_history') or [] %}
              {% if hist | length > 0 %}
              **📜 سجل الإشارات** (آخر {{ hist | length }})

              | السهم | النوع | السعر | Score | الوقت |
              |:------|:-----:|------:|:-----:|:-----:|
              {% for s in hist[:15] %}| {{ s.symbol }} | {% if s.type == 'bullish_cross' %}🟢{% else %}🔴{% endif %} | {{ s.price }} | {{ s.score }} | {{ s.time[-11:-3] if s.time | length > 11 else s.time }} |
              {% endfor %}
              {% else %}
              📜 لا سجل إشارات
              {% endif %}

          # ── TV ALERT LOG ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(52,152,219,0.04);
                  border: 1px solid rgba(52,152,219,0.10);
                  border-radius: 18px;
                  padding: 14px 16px;
                  margin: 10px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set a = 'sensor.master_ai_analysis' %}
              {% set alerts = state_attr(a,'tv_alerts') or [] %}
              {% if alerts | length > 0 %}
              **📺 تنبيهات TradingView** ({{ alerts | length }})

              | السهم | الإشارة | السعر | الاستراتيجية | الوقت |
              |:------|:------:|------:|:------------|:-----:|
              {% for t in alerts[:10] %}| {{ t.ticker }} | {{ t.signal }} | {{ t.price }} | {{ t.strategy | default('—') }} | {{ t.time[-11:-3] if t.time and t.time | length > 11 else t.time | default('—') }} |
              {% endfor %}
              {% else %}
              📺 لا تنبيهات TradingView بعد
              {% endif %}

          # ── SIGNAL STATS PER TICKER ──
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
              {% set a = 'sensor.master_ai_analysis' %}
              {% set stats = state_attr(a,'signal_stats') or [] %}
              {% if stats | length > 0 %}
              **📊 إحصائيات الإشارات** ({{ stats | length }} سهم)

              | السهم | الاستراتيجية | النوع | العدد | آخر ظهور |
              |:------|:------------|:-----:|------:|:--------:|
              {% for s in stats[:10] %}| {{ s.ticker }} | {{ s.strategy | default('—') }} | {{ s.signal_type | default('—') }} | {{ s.count }} | {{ s.last_seen[-11:-3] if s.last_seen and s.last_seen | length > 11 else s.last_seen | default('—') }} |
              {% endfor %}
              {% else %}
              📊 لا إحصائيات بعد
              {% endif %}

          # ── QUICK ACTIONS ──
          - type: grid
            columns: 4
            square: false
            cards:
              - type: button
                name: الرادار
                icon: mdi:radar
                tap_action:
                  action: navigate
                  navigation_path: /master-ai-dashboard/sub-radar
                show_state: false
              - type: button
                name: المحفظة
                icon: mdi:wallet-outline
                tap_action:
                  action: navigate
                  navigation_path: /master-ai-dashboard/sub-portfolio
                show_state: false
              - type: button
                name: TV Sync
                icon: mdi:sync
                tap_action:
                  action: call-service
                  service: rest_command.master_ai_tg_cmd
                  data:
                    command: "/tv_sync"
                show_state: false
              - type: button
                name: الرئيسية
                icon: mdi:home
                tap_action:
                  action: navigate
                  navigation_path: /master-ai-dashboard/master-ai
                show_state: false

'''

# Insert both pages before sub-calendar-tasks
cal_marker = "  # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\n  - path: sub-calendar-tasks"

if cal_marker in content:
    content = content.replace(cal_marker, portfolio_page + analysis_page + cal_marker)
    print("OK: Portfolio + Analysis pages inserted")
else:
    print("WARN: calendar marker not found")

new_len = len(content)
if new_len > original_len:
    with open(DASH, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"DONE — {original_len} -> {new_len} chars (+{new_len - original_len})")
else:
    print("ERROR: no changes made")
