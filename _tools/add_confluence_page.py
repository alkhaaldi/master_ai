#!/usr/bin/env python3
"""Add sub-confluence dashboard page + nav buttons."""
from pathlib import Path

YAML_PATH = Path("/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml")
content = YAML_PATH.read_text(encoding="utf-8")

if "sub-confluence" in content:
    print("sub-confluence page already exists — SKIP")
else:
    PAGE = """

  # ═══ SUB-CONFLUENCE — محرك القرار الذكي ═══
  - path: sub-confluence
    title: Confluence
    icon: mdi:target
    subview: true
    type: panel
    cards:
      - type: vertical-stack
        cards:

          # ── L1: PULSE HERO ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: linear-gradient(135deg, rgba(39,174,96,0.12), rgba(39,174,96,0.04));
                  border: 1px solid rgba(39,174,96,0.15);
                  border-radius: 18px;
                  padding: 14px 16px 8px;
                  margin: 6px 8px 0;
                }
                h2 { font-size: 18px !important; margin: 0 !important; }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.9; }
            content: |
              ## محرك القرار الذكي
              {% set c = 'sensor.master_ai_confluence' %}
              {% set sa = state_attr(c,'scan_active') %}
              {% set ac = state_attr(c,'actionable_count') | int(0) %}
              {% set wc = state_attr(c,'watch_count') | int(0) %}
              {% set sc = state_attr(c,'stocks_scanned') | int(0) %}
              {% set ls = state_attr(c,'last_scan') | default('') %}
              {% if sa %}🟢{% else %}🔴{% endif %} Confluence {% if sa %}active{% else %}inactive{% endif %} — {{ sc }} سهم
              {% if ac > 0 %}🎯 **{{ ac }} فرص شراء الآن**{% else %}⏳ لا فرص عالية الآن — المحرك يفحص كل 30 دقيقة{% endif %}
              📋 مراقبة: {{ wc }} · آخر فحص: {{ ls[-8:] if ls | length > 8 else ls }}

          # ── L2: ACTIONABLE CARDS (HIGH conviction) ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(39,174,96,0.06);
                  border: 2px solid rgba(39,174,96,0.20);
                  border-radius: 18px;
                  padding: 14px 16px;
                  margin: 10px 8px 0;
                  box-shadow: 0 4px 16px rgba(39,174,96,0.08);
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.9; }
            content: |
              {% set c = 'sensor.master_ai_confluence' %}
              {% set sigs = state_attr(c,'actionable') or [] %}
              {% if sigs | length > 0 %}
              **🎯 فرص الشراء** ({{ sigs | length }})

              {% for s in sigs[:5] %}
              ━━━━━━━━━━━━━━━━━━━━
              🎯 **{{ s.name_ar | default(s.symbol) }}** ({{ s.symbol }}) {% if s.sector %}· {{ s.sector }}{% endif %}
              📊 Confluence: **{{ s.confluence_score }}%** ({{ s.checks_passed | default('') | replace(',','✓ ') }})
              💰 السعر: {{ s.price }} فلس{% if s.change_pct is defined %} · {% if s.change_pct >= 0 %}🟢 +{% else %}🔴 {% endif %}{{ s.change_pct | round(1) }}%{% endif %}
              📈 RVOL: {% if s.rvol %}×{{ s.rvol | round(1) }}{% else %}—{% endif %} | RSI: {{ s.rsi | round(0) if s.rsi else '—' }}
              {% set ck = s.checks | default({}) %}{% if ck.rvol | default(false) %}✅{% else %}❌{% endif %} حجم {% if ck.macd | default(false) %}✅{% else %}❌{% endif %} MACD {% if ck.rsi | default(false) %}✅{% else %}❌{% endif %} RSI {% if ck.trend | default(false) %}✅{% else %}❌{% endif %} ترند {% if ck.ema | default(false) %}✅{% else %}❌{% endif %} EMA {% if ck.not_ob | default(false) %}✅{% else %}❌{% endif %} OB
              🎯 الدخول: {{ s.entry | default(s.entry_price) }} | الوقف: {{ s.stop | default(s.stop_loss) | default('—') }}{% if s.sl_pct %} (-{{ s.sl_pct }}%){% endif %}
              🏁 الهدف: {{ s.target | default(s.target_price) | default('—') }} | R:R = {{ s.risk_reward | default('—') }}
              {% if s.support %}📍 دعم: {{ s.support }}{% endif %}{% if s.resistance %} | مقاومة: {{ s.resistance }}{% endif %}
              {% endfor %}
              {% else %}
              ⏳ لا فرص شراء عالية الآن

              المحرك يفحص 128 سهم كل 30 دقيقة خلال ساعات السوق (أحد-خميس 9:00-12:40)
              عندما تتحقق 5+ شروط من 6 مع R:R ≥ 2.0 — تصلك الإشارة على تليقرام تلقائياً
              {% endif %}

          # ── L3: WATCHLIST (MEDIUM conviction) ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(255,170,0,0.04);
                  border: 1px solid rgba(255,170,0,0.10);
                  border-radius: 16px;
                  padding: 10px 16px;
                  margin: 10px 8px 0;
                }
                ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
            content: |
              {% set c = 'sensor.master_ai_confluence' %}
              {% set wl = state_attr(c,'watchlist') or [] %}
              {% if wl | length > 0 %}
              **📋 قائمة المراقبة** ({{ wl | length }} — MEDIUM conviction)

              | السهم | السعر | Conf% | RVOL | RSI | R:R | لماذا |
              |:------|------:|:-----:|-----:|----:|:---:|:------|
              {% for w in wl[:10] %}| {{ w.name_ar | default(w.symbol) }} | {{ w.price }} | {{ w.confluence_score }}% | {% if w.rvol %}×{{ w.rvol | round(1) }}{% else %}—{% endif %} | {{ w.rsi | round(0) if w.rsi else '—' }} | {{ w.risk_reward | default('—') }} | {{ w.checks_passed | default('') }} |
              {% endfor %}
              {% else %}
              📋 لا أسهم في المراقبة
              {% endif %}

          # ── L4: MARKET PULSE ──
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
                  {% set ms = state_attr('sensor.master_ai_confluence','market_summary') or {} %}
                  🟢 **{{ ms.get('high_count',0) }}**

                  HIGH
              - type: markdown
                card_mod:
                  style: |
                    ha-card { background: rgba(255,170,0,0.05); border: 1px solid rgba(255,170,0,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set ms = state_attr('sensor.master_ai_confluence','market_summary') or {} %}
                  🟡 **{{ ms.get('medium_count',0) }}**

                  MEDIUM
              - type: markdown
                card_mod:
                  style: |
                    ha-card { background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.04); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set ms = state_attr('sensor.master_ai_confluence','market_summary') or {} %}
                  ⚪ **{{ ms.get('low_count',0) }}**

                  LOW
              - type: markdown
                card_mod:
                  style: |
                    ha-card { background: rgba(0,170,255,0.05); border: 1px solid rgba(0,170,255,0.10); border-radius: 18px; padding: 12px 8px; text-align: center; }
                    ha-markdown { font-size: 14px; direction: rtl; }
                content: |
                  {% set ms = state_attr('sensor.master_ai_confluence','market_summary') or {} %}
                  📊 **{{ ms.get('avg_confluence',0) }}%**

                  متوسط

          # ── DISCLAIMER ──
          - type: markdown
            card_mod:
              style: |
                ha-card {
                  background: rgba(231,76,60,0.04);
                  border: 1px solid rgba(231,76,60,0.10);
                  border-radius: 14px;
                  padding: 6px 16px;
                  margin: 6px 8px 0;
                }
                ha-markdown { font-size: 12px; direction: rtl; opacity: 0.7; }
            content: >
              ⚠️ هذا النظام يعطي إشارات بناءً على تحليل فني — مو توصية مالية.
              كل قرار تداول مسؤوليتك. استخدم وقف خسارة دائمًا.

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
              [الرادار](/master-ai-dashboard/sub-radar) · [المحفظة](/master-ai-dashboard/sub-portfolio) · [السجل](/master-ai-dashboard/sub-journal) · [التنبيهات](/master-ai-dashboard/sub-alerts) · [الرئيسية](/master-ai-dashboard/0)
"""
    content += PAGE
    YAML_PATH.write_text(content, encoding="utf-8")
    lines = len(content.split("\n"))
    print(f"sub-confluence page added ✓ ({lines} lines)")

    # Validate YAML
    import yaml
    try:
        yaml.safe_load(content)
        print("YAML validation: OK ✓")
    except yaml.YAMLError as e:
        print(f"YAML ERROR: {e}")

# Count pages
import re
pages = re.findall(r"  - path: (\S+)", content)
print(f"Pages: {len(pages)} → {', '.join(pages)}")
