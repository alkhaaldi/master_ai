#!/usr/bin/env python3
"""Build 5 new dashboard pages from scratch (bak_v12 style).
Pages: sub-portfolio, sub-analysis, sub-assistant, sub-journal, sub-alerts
"""
import subprocess, json, sys
from pathlib import Path

YAML_PATH = Path("/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml")

content = YAML_PATH.read_text(encoding="utf-8")
orig_lines = len(content.split("\n"))
print(f"Starting: {orig_lines} lines")

# ═══════════════════════════════════════════════════
# PAGE: sub-portfolio
# ═══════════════════════════════════════════════════
SUB_PORTFOLIO = """
  # ═══ SUB-PORTFOLIO ═══
  - path: sub-portfolio
    title: المحفظة
    icon: mdi:wallet
    subview: true
    type: panel
    cards:
      - type: vertical-stack
        cards:

          # ── PULSE ──
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
                ha-markdown { font-size: 14px; direction: rtl; }
            content: |
              ## المحفظة
              {% set p = 'sensor.master_ai_portfolio' %}
              {% set s30 = state_attr(p,'stats_30d') or {} %}
              📂 {{ state_attr(p,'open_positions') | length if state_attr(p,'open_positions') else 0 }} مفتوحة · 📊 {{ s30.get('total_trades',0) }} صفقة (30 يوم) · 🏆 {{ (s30.get('win_rate',0) * 100) | round(0) }}% فوز

          # ── OPEN POSITIONS ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(39,174,96,0.04);
                  border: 1px solid rgba(39,174,96,0.10);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set p = 'sensor.master_ai_portfolio' %}
              {% set trades = state_attr(p,'open_positions') %}
              {% if trades and trades | length > 0 %}
              **📂 صفقات مفتوحة** ({{ trades | length }})

              | السهم | الدخول | الحالي | الكمية | %P&L |
              |:------|------:|------:|------:|-----:|
              {% for t in trades %}| {{ t.name_ar | default(t.symbol) }} | {{ t.entry_price }} | {{ t.current_price | default('—') }} | {{ t.quantity }} | {% if t.pnl_pct is defined %}{% if t.pnl_pct >= 0 %}🟢 +{% else %}🔴 {% endif %}{{ t.pnl_pct | round(1) }}%{% else %}—{% endif %} |
              {% endfor %}
              {% else %}
              📂 لا صفقات مفتوحة
              {% endif %}

          # ── SIGNAL VS TRADE ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(0,170,255,0.04);
                  border: 1px solid rgba(0,170,255,0.10);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set p = 'sensor.master_ai_portfolio' %}
              {% set svt = state_attr(p,'signal_vs_trade') %}
              {% if svt %}
              **📡 إشارات vs صفقات** (7 أيام)

              📡 إشارات: {{ svt.total_signals | default(0) }} · 📂 صفقات: {{ svt.trades_taken | default(0) }} · ✅ نفذت: {{ svt.acted_on | default(0) }} · ⏭️ تخطيت: {{ svt.skipped | default(0) }}
              {% else %}
              📡 لا بيانات مقارنة
              {% endif %}

          # ── 30D STATS ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(255,255,255,0.02);
                  border: 1px solid rgba(255,255,255,0.04);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set p = 'sensor.master_ai_portfolio' %}
              {% set s = state_attr(p,'stats_30d') or {} %}
              {% if s %}
              **📊 إحصائيات 30 يوم**

              📈 صفقات: {{ s.get('total_trades',0) }} · ✅ ربح: {{ s.get('wins',0) }} · ❌ خسارة: {{ s.get('losses',0) }} · 🏆 {{ (s.get('win_rate',0) * 100) | round(0) }}%
              💰 P&L: {{ ((s.get('total_pnl_fils',0)) / 1000) | round(3) }} د.ك · 📈 متوسط ربح: {{ s.get('avg_profit_pct',0) | round(1) }}% · 📉 متوسط خسارة: {{ s.get('avg_loss_pct',0) | round(1) }}%
              {% endif %}

          # ── NAV ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(255,255,255,0.02);
                  border-radius: 14px;
                  padding: 6px 16px;
                  margin: 6px 8px 12px;
                }
                ha-markdown { font-size: 14px; direction: rtl; }
            content: >
              [الرادار](/master-ai-dashboard/sub-radar) · [التحليل](/master-ai-dashboard/sub-analysis) · [السجل](/master-ai-dashboard/sub-journal) · [الرئيسية](/master-ai-dashboard/0)
"""

# ═══════════════════════════════════════════════════
# PAGE: sub-analysis
# ═══════════════════════════════════════════════════
SUB_ANALYSIS = """
  # ═══ SUB-ANALYSIS ═══
  - path: sub-analysis
    title: التحليل
    icon: mdi:chart-scatter-plot
    subview: true
    type: panel
    cards:
      - type: vertical-stack
        cards:

          # ── PULSE ──
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
                ha-markdown { font-size: 14px; direction: rtl; }
            content: |
              ## التحليل
              {% set a = 'sensor.master_ai_analysis' %}
              {% set ra = state_attr(a,'radar_accuracy') or {} %}
              📡 {{ ra.get('total_signals',0) }} إشارة · 🟢 {{ ra.get('bullish',0) }} صاعد · 🔴 {{ ra.get('bearish',0) }} هابط · ⭐ {{ ra.get('avg_score',0) }} متوسط

          # ── RADAR ACCURACY GRID ──
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
                    ha-card { background: rgba(255,170,0,0.05); border: 1px solid rgba(255,170,0,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set ra = state_attr('sensor.master_ai_analysis','radar_accuracy') or {} %}
                  ⭐ **{{ ra.get('avg_score',0) }}**

                  Score

          # ── SIGNAL HISTORY ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(180,120,255,0.04);
                  border: 1px solid rgba(180,120,255,0.10);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set a = 'sensor.master_ai_analysis' %}
              {% set hist = state_attr(a,'signal_history') %}
              {% if hist and hist | length > 0 %}
              **📜 سجل الإشارات** (آخر {{ hist | length }})

              | السهم | النوع | السعر | Score | الوقت |
              |:------|:-----:|------:|:-----:|:-----:|
              {% for s in hist[:25] %}| {{ s.symbol }} | {% if s.type == 'bullish_cross' %}🟢{% else %}🔴{% endif %} | {{ s.price }} | {{ s.score }} | {{ s.time[-11:-3] if s.time | length > 11 else s.time }} |
              {% endfor %}
              {% else %}
              📜 لا سجل إشارات
              {% endif %}

          # ── TV ALERTS ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(0,170,255,0.04);
                  border: 1px solid rgba(0,170,255,0.10);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set a = 'sensor.master_ai_analysis' %}
              {% set tv = state_attr(a,'tv_alerts') %}
              {% if tv and tv | length > 0 %}
              **📺 تنبيهات TradingView** ({{ tv | length }})

              {% for t in tv[:10] %}📌 **{{ t.symbol }}** — {{ t.type | default('alert') }} · {{ t.message[:40] | default('—') }} · {{ t.time | default('—') }}
              {% endfor %}
              {% else %}
              📺 لا تنبيهات TV
              {% endif %}

          # ── SIGNAL STATS PER TICKER ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(255,255,255,0.02);
                  border: 1px solid rgba(255,255,255,0.04);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set a = 'sensor.master_ai_analysis' %}
              {% set ss = state_attr(a,'signal_stats') %}
              {% if ss and ss | length > 0 %}
              **📊 إحصائيات الإشارات**

              | السهم | إشارات | صاعد | هابط | Score |
              |:------|------:|-----:|-----:|------:|
              {% for s in ss[:15] %}| {{ s.symbol }} | {{ s.total | default(0) }} | {{ s.bullish | default(0) }} | {{ s.bearish | default(0) }} | {{ s.avg_score | default(0) | round(1) }} |
              {% endfor %}
              {% else %}
              📊 لا إحصائيات
              {% endif %}

          # ── DAILY SUMMARY ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(255,170,0,0.04);
                  border: 1px solid rgba(255,170,0,0.10);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set a = 'sensor.master_ai_analysis' %}
              {% set ds = state_attr(a,'daily_summary') %}
              {% if ds %}
              **📅 ملخص اليوم**

              {{ ds.summary | default('لا ملخص') }}
              {% endif %}

          # ── NAV ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(255,255,255,0.02);
                  border-radius: 14px;
                  padding: 6px 16px;
                  margin: 6px 8px 12px;
                }
                ha-markdown { font-size: 14px; direction: rtl; }
            content: >
              [الرادار](/master-ai-dashboard/sub-radar) · [المحفظة](/master-ai-dashboard/sub-portfolio) · [السجل](/master-ai-dashboard/sub-journal) · [الرئيسية](/master-ai-dashboard/0)
"""

# ═══════════════════════════════════════════════════
# PAGE: sub-assistant
# ═══════════════════════════════════════════════════
SUB_ASSISTANT = """
  # ═══ SUB-ASSISTANT ═══
  - path: sub-assistant
    title: المساعد
    icon: mdi:robot
    subview: true
    type: panel
    cards:
      - type: vertical-stack
        cards:

          # ── PULSE ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: linear-gradient(135deg, rgba(0,170,255,0.10), rgba(0,170,255,0.04));
                  border: 1px solid rgba(0,170,255,0.12);
                  border-radius: 18px;
                  padding: 10px 16px 6px;
                  margin: 6px 8px 0;
                }
                h2 { font-size: 18px !important; margin: 0 !important; }
                ha-markdown { font-size: 14px; direction: rtl; }
            content: |
              ## المساعد
              {% set e = 'sensor.master_ai_extended' %}
              💰 اليوم: ${{ state_attr(e,'cost_today') | default(0) | round(3) }} · الإجمالي: ${{ state_attr(e,'cost_total') | default(0) | round(2) }} · 📊 {{ state_attr(e,'total_requests') | default(0) }} طلب · ⚡ ${{ state_attr(e,'avg_cost_per_request') | default(0) | round(4) }}/طلب

          # ── MEMORY STATS ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(0,170,255,0.04);
                  border: 1px solid rgba(0,170,255,0.10);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set e = 'sensor.master_ai_extended' %}
              {% set mem = state_attr(e,'memory_by_type') %}
              {% if mem %}
              **🧠 الذاكرة**

              {% for k, v in mem.items() %}📁 {{ k }}: {{ v }}
              {% endfor %}
              {% else %}
              🧠 لا بيانات ذاكرة
              {% endif %}

          # ── COST GRID ──
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
                  💰 **${{ state_attr(e,'cost_today') | default(0) | round(3) }}**

                  اليوم
              - type: markdown
                card_mod:
                  style: |
                    ha-card { background: rgba(0,170,255,0.05); border: 1px solid rgba(0,170,255,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set e = 'sensor.master_ai_extended' %}
                  📊 **{{ state_attr(e,'total_requests') | default(0) }}**

                  طلب
              - type: markdown
                card_mod:
                  style: |
                    ha-card { background: rgba(255,170,0,0.05); border: 1px solid rgba(255,170,0,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set e = 'sensor.master_ai_extended' %}
                  💵 **${{ state_attr(e,'cost_total') | default(0) | round(2) }}**

                  الإجمالي

          # ── TOOL USAGE ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(255,255,255,0.02);
                  border: 1px solid rgba(255,255,255,0.04);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set e = 'sensor.master_ai_extended' %}
              {% set tools = state_attr(e,'tool_usage') %}
              {% if tools and tools | length > 0 %}
              **🔧 الأدوات**

              | الأداة | الاستخدام |
              |:------|----------:|
              {% for t in tools[:10] %}| {{ t.name | default(t.tool) }} | {{ t.count }} |
              {% endfor %}
              {% else %}
              🔧 لا بيانات أدوات
              {% endif %}

          # ── GIT LOG ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(255,255,255,0.02);
                  border: 1px solid rgba(255,255,255,0.04);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: ltr; line-height: 1.8; font-family: monospace; }
            content: |
              {% set e = 'sensor.master_ai_extended' %}
              {% set gl = state_attr(e,'git_log') %}
              {% if gl and gl | length > 0 %}
              **📦 Git Log**

              {% for g in gl[:8] %}```{{ g.hash[:7] }}``` {{ g.message[:50] }} ({{ g.date[-5:] }})
              {% endfor %}
              {% else %}
              📦 لا سجل Git
              {% endif %}

          # ── NAV ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(255,255,255,0.02);
                  border-radius: 14px;
                  padding: 6px 16px;
                  margin: 6px 8px 12px;
                }
                ha-markdown { font-size: 14px; direction: rtl; }
            content: >
              [النظام](/master-ai-dashboard/sub-system-health) · [الرئيسية](/master-ai-dashboard/0)
"""

# ═══════════════════════════════════════════════════
# PAGE: sub-journal
# ═══════════════════════════════════════════════════
SUB_JOURNAL = """
  # ═══ SUB-JOURNAL ═══
  - path: sub-journal
    title: سجل الصفقات
    icon: mdi:book-open-page-variant
    subview: true
    type: panel
    cards:
      - type: vertical-stack
        cards:

          # ── PULSE ──
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
                ha-markdown { font-size: 14px; direction: rtl; }
            content: |
              ## سجل الصفقات
              {% set j = 'sensor.master_ai_journal' %}
              {% set ps = state_attr(j,'portfolio_summary') or {} %}
              {% set s30 = state_attr(j,'stats_30d') or {} %}
              📂 مفتوحة: **{{ ps.get('open_count',0) }}** · الربح الصافي: {% if ps.get('total_net_pnl_kwd',0) >= 0 %}🟢 +{{ ps.get('total_net_pnl_kwd',0) }}{% else %}🔴 {{ ps.get('total_net_pnl_kwd',0) }}{% endif %} د.ك · العمولات: {{ ps.get('total_fees_kwd',0) }} د.ك
              آخر 30 يوم: {{ s30.get('total_trades',0) }} صفقة · {{ (s30.get('win_rate',0) * 100) | round(0) }}% فوز

          # ── OPEN POSITIONS (KWD P&L) ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(39,174,96,0.04);
                  border: 1px solid rgba(39,174,96,0.10);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.9; }
            content: |
              {% set j = 'sensor.master_ai_journal' %}
              {% set trades = state_attr(j,'open_positions') %}
              {% if trades and trades | length > 0 %}
              **📂 صفقات مفتوحة** ({{ trades | length }})

              {% for t in trades %}📊 **{{ t.name_ar | default(t.symbol) }}** — {{ t.direction | default('long') }}
              الدخول: {{ t.entry_price }} فلس × {{ t.quantity }}{% if t.pnl is defined and t.pnl %} = {{ t.pnl.entry_total_kwd }} د.ك
              الحالي: {{ t.current_price }} فلس = {{ t.pnl.current_total_kwd }} د.ك
              الربح: {% if t.pnl.net_pnl_kwd >= 0 %}🟢 +{% else %}🔴 {% endif %}{{ t.pnl.net_pnl_kwd }} د.ك ({% if t.pnl.net_pnl_pct >= 0 %}+{% endif %}{{ t.pnl.net_pnl_pct }}%) · عمولة: {{ t.pnl.total_fees_kwd }} د.ك{% endif %}
              {{ t.strategy | default('manual') }} · {{ t.entry_date | default('—') }}
              {% endfor %}
              {% else %}
              📂 لا صفقات مفتوحة
              {% endif %}

          # ── CLOSED TRADES ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(255,255,255,0.02);
                  border: 1px solid rgba(255,255,255,0.04);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set j = 'sensor.master_ai_journal' %}
              {% set closed = state_attr(j,'closed_trades') %}
              {% if closed and closed | length > 0 %}
              **📋 آخر الصفقات المغلقة** ({{ closed | length }})

              | السهم | الدخول | الخروج | P&L د.ك | % | التاريخ |
              |:------|------:|------:|--------:|--:|:------:|
              {% for t in closed[:10] %}| {{ t.name_ar | default(t.symbol) }} | {{ t.entry_price }} | {{ t.exit_price }} | {% if t.pnl is defined and t.pnl %}{% if t.pnl.net_pnl_kwd >= 0 %}+{% endif %}{{ t.pnl.net_pnl_kwd }}{% else %}—{% endif %} | {% if t.pnl is defined and t.pnl %}{{ t.pnl.net_pnl_pct }}{% else %}{{ t.pnl_pct | default(0) | round(1) }}{% endif %} | {{ t.exit_date | default('—') }} |
              {% endfor %}
              {% else %}
              📋 لا صفقات مغلقة
              {% endif %}

          # ── MONTHLY STATS ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(0,170,255,0.04);
                  border: 1px solid rgba(0,170,255,0.10);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set j = 'sensor.master_ai_journal' %}
              {% set monthly = state_attr(j,'monthly_stats') %}
              {% if monthly and monthly | length > 0 %}
              **📅 إحصائيات شهرية**

              | الشهر | صفقات | فوز | خسارة | P&L د.ك | Win% |
              |:------|------:|----:|------:|--------:|-----:|
              {% for m in monthly %}| {{ m.month }} | {{ m.total }} | {{ m.wins }} | {{ m.losses }} | {% if m.total_pnl_kwd >= 0 %}+{% endif %}{{ m.total_pnl_kwd }} | {{ m.win_rate | round(0) }}% |
              {% endfor %}
              {% else %}
              📅 لا بيانات شهرية
              {% endif %}

          # ── BEST/WORST ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(255,255,255,0.02);
                  border: 1px solid rgba(255,255,255,0.04);
                  border-radius: 14px;
                  padding: 8px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set j = 'sensor.master_ai_journal' %}
              {% set best = state_attr(j,'best_trade') %}
              {% set worst = state_attr(j,'worst_trade') %}
              {% if best or worst %}
              **🏆 أبرز الصفقات (30 يوم)**

              {% if best %}🟢 أفضل: **{{ best.symbol }}** +{{ best.pnl_pct | round(1) }}%{% endif %}
              {% if worst %}🔴 أسوأ: **{{ worst.symbol }}** {{ worst.pnl_pct | round(1) }}%{% endif %}
              {% endif %}

          # ── NAV ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(255,255,255,0.02);
                  border-radius: 14px;
                  padding: 6px 16px;
                  margin: 6px 8px 12px;
                }
                ha-markdown { font-size: 14px; direction: rtl; }
            content: >
              [الرادار](/master-ai-dashboard/sub-radar) · [المحفظة](/master-ai-dashboard/sub-portfolio) · [التنبيهات](/master-ai-dashboard/sub-alerts) · [الرئيسية](/master-ai-dashboard/0)
"""

# ═══════════════════════════════════════════════════
# PAGE: sub-alerts
# ═══════════════════════════════════════════════════
SUB_ALERTS = """
  # ═══ SUB-ALERTS ═══
  - path: sub-alerts
    title: التنبيهات
    icon: mdi:alert-decagram
    subview: true
    type: panel
    cards:
      - type: vertical-stack
        cards:

          # ── PULSE ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: linear-gradient(135deg, rgba(231,76,60,0.10), rgba(231,76,60,0.04));
                  border: 1px solid rgba(231,76,60,0.12);
                  border-radius: 18px;
                  padding: 10px 16px 6px;
                  margin: 6px 8px 0;
                }
                h2 { font-size: 18px !important; margin: 0 !important; }
                ha-markdown { font-size: 14px; direction: rtl; }
            content: |
              ## التنبيهات الذكية
              {% set a = 'sensor.master_ai_alerts' %}
              {% set vs = state_attr(a,'volume_spikes') or [] %}
              {% set sr = state_attr(a,'sr_proximity') or [] %}
              {% set ca = state_attr(a,'confluence_alerts') or [] %}
              {% set re = state_attr(a,'rsi_extremes') or [] %}
              🔥 حجم: **{{ vs | length }}** · 📍 دعم/مقاومة: **{{ sr | length }}** · 🎯 Confluence: **{{ ca | length }}** · ⚠️ RSI: **{{ re | length }}**

          # ── VOLUME SPIKES ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(231,76,60,0.04);
                  border: 1px solid rgba(231,76,60,0.10);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set a = 'sensor.master_ai_alerts' %}
              {% set vs = state_attr(a,'volume_spikes') or [] %}
              {% if vs | length > 0 %}
              **🔥 ارتفاع الحجم** ({{ vs | length }})

              {% for v in vs[:8] %}🔥 **{{ v.name_ar | default(v.symbol) }}** — حجم ×{{ v.vol_ratio | round(1) }}{% if v.is_spike %} — **spike!**{% endif %}
              {% endfor %}
              {% else %}
              🔥 لا ارتفاعات حجم
              {% endif %}

          # ── S/R PROXIMITY ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(0,170,255,0.04);
                  border: 1px solid rgba(0,170,255,0.10);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set a = 'sensor.master_ai_alerts' %}
              {% set sr = state_attr(a,'sr_proximity') or [] %}
              {% if sr | length > 0 %}
              **📍 قرب الدعم/المقاومة** ({{ sr | length }})

              {% for s in sr[:8] %}📍 **{{ s.name_ar | default(s.symbol) }}** — {% if s.type == 'support' %}دعم {{ s.level }}{% else %}مقاومة {{ s.level }}{% endif %} ({{ s.distance_pct }}%) · {{ s.price }}ف
              {% endfor %}
              {% else %}
              📍 لا أسهم قريبة من دعم/مقاومة
              {% endif %}

          # ── CONFLUENCE ALERTS ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(39,174,96,0.04);
                  border: 1px solid rgba(39,174,96,0.10);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set a = 'sensor.master_ai_alerts' %}
              {% set ca = state_attr(a,'confluence_alerts') or [] %}
              {% if ca | length > 0 %}
              **🎯 Confluence Alerts** ({{ ca | length }})

              {% for c in ca[:8] %}{% if c.confluence_score > 0 %}🟢{% else %}🔴{% endif %} **{{ c.name_ar | default(c.symbol) }}** — Score: {{ c.confluence_score }} · {{ c.direction }}{% if c.macd_cross is defined and c.macd_cross != 'none' %} · MACD {{ c.macd_cross }}{% endif %}
              {% endfor %}
              {% else %}
              🎯 لا confluence
              {% endif %}

          # ── RSI EXTREMES ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(255,170,0,0.04);
                  border: 1px solid rgba(255,170,0,0.10);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 8px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set a = 'sensor.master_ai_alerts' %}
              {% set re = state_attr(a,'rsi_extremes') or [] %}
              {% if re | length > 0 %}
              **⚠️ RSI Extremes** ({{ re | length }})

              {% for r in re[:8] %}{% if r.type == 'overbought' %}⚠️{% else %}💡{% endif %} **{{ r.name_ar | default(r.symbol) }}** RSI {{ r.rsi | round(0) }} — {{ r.type_ar | default(r.type) }} · {{ r.price }}ف
              {% endfor %}
              {% else %}
              ⚠️ لا RSI متطرف
              {% endif %}

          # ── NAV ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(255,255,255,0.02);
                  border-radius: 14px;
                  padding: 6px 16px;
                  margin: 6px 8px 12px;
                }
                ha-markdown { font-size: 14px; direction: rtl; }
            content: >
              [الرادار](/master-ai-dashboard/sub-radar) · [السجل](/master-ai-dashboard/sub-journal) · [المحفظة](/master-ai-dashboard/sub-portfolio) · [الرئيسية](/master-ai-dashboard/0)
"""

# ═══════════════════════════════════════════════════
# APPEND ALL PAGES
# ═══════════════════════════════════════════════════
content += SUB_PORTFOLIO
print("Added: sub-portfolio")
content += SUB_ANALYSIS
print("Added: sub-analysis")
content += SUB_ASSISTANT
print("Added: sub-assistant")
content += SUB_JOURNAL
print("Added: sub-journal")
content += SUB_ALERTS
print("Added: sub-alerts")

YAML_PATH.write_text(content, encoding="utf-8")
final_lines = len(content.split("\n"))
print(f"\nFinal: {final_lines} lines (was {orig_lines}, added {final_lines - orig_lines})")

# Count pages
import re
pages = re.findall(r"  - path: (\S+)", content)
print(f"Pages: {len(pages)} → {', '.join(pages)}")

# Validate YAML
import yaml
try:
    yaml.safe_load(content)
    print("\nYAML validation: OK ✓")
except yaml.YAMLError as e:
    print(f"\nYAML ERROR: {e}")
    sys.exit(1)
