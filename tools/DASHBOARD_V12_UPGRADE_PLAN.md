# Dashboard V12 Upgrade Plan — Full Execution Guide for Claude Code
> Generated: 2026-03-21 | Source: Full audit of all 7 pages + 3 API endpoints
> Execute on RPi via Claude Code at `/var/lib/homeassistant/share/master_ai/`

---

## PRE-FLIGHT: Read Before Any Change

```bash
# 1. Read context
cat CLAUDE.md
cat _tools/OPERATIONAL_ACCESS_MATRIX.md
cat _tools/ADDING_NEW_DASHBOARD_FIELDS.md

# 2. Backup current dashboard
sudo cp /var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml \
        /var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml.bak_v11

# 3. Health check
python3 _tools/quick_check.py

# 4. Git commit current state
cd /var/lib/homeassistant/share/master_ai && git add -A && git commit -m "backup: pre-V12 upgrade"
```

---

## PHASE 1: Backend Fixes (server.py patches)
> Priority: HIGH — these fix data issues that affect multiple pages
> Method: `_tools/patchers/apply_text_patch.py` for ALL server.py changes

### 1A. Fix Command Feedback Unicode Escapes
**Problem:** Trading, Email, Calendar pages show `\u2705` instead of ✅
**Root cause:** YAML `content: >` block with Python `\uXXXX` literals instead of actual UTF-8 emoji
**Fix:** This is a YAML issue, not server.py — will be fixed in Phase 3 (dashboard YAML rebuild)

### 1B. News Endpoint — Return Structured Items Array
**Problem:** `/dashboard/extended` returns `news_digest` as a flat object with text blobs per category. The News page can't render individual items, can't hide empty categories, can't show "top 3".
**Current structure:**
```json
{
  "news_digest": {
    "summary": "**ملخص الأخبار**\n\n🔥 ...",
    "urgent": "🔥 line1\n🔥 line2\n...",
    "economic": "💰 line1\n💰 line2\n...",
    "local": "...",
    "tech": "...",
    "ai": "...",
    "gadgets": "...",
    "item_count": 25,
    "date": "2026-03-21"
  }
}
```
**Target structure** (add `news_items` field alongside existing fields for backward compatibility):
```json
{
  "news_digest": {
    ... existing fields unchanged ...
    "news_items": [
      {
        "category": "urgent",
        "category_ar": "عاجل",
        "emoji": "🔥",
        "text": "كشف تحليل جديد أن الضربات الإيرانية...",
        "source": "BBC",
        "priority": 1
      },
      ...
    ]
  }
}
```

**Patch instructions for server.py:**
Find the function that builds `news_digest` (likely in the `/dashboard/extended` endpoint or a helper).
After the existing category text is built, add parsing logic:

```python
# Parse news text blobs into structured items
def _parse_news_items(digest):
    """Parse news category text blobs into structured items array."""
    items = []
    categories = [
        ("urgent", "عاجل", "🔥", 1),
        ("economic", "اقتصاد", "💰", 2),
        ("local", "محلي", "🇰🇼", 3),
        ("tech", "تقنية", "💻", 4),
        ("ai", "ذكاء اصطناعي", "🤖", 5),
        ("gadgets", "أجهزة", "📱", 6),
    ]
    for key, ar, emoji, pri in categories:
        text = digest.get(key, "") or ""
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # Remove leading emoji if present
            clean = line.lstrip("🔥💰🇰🇼💻🤖📱⚡ ").strip()
            if not clean:
                continue
            # Extract source in parentheses at end
            source = ""
            if clean.endswith(")") and "(" in clean:
                idx = clean.rfind("(")
                source = clean[idx+1:-1].strip()
                clean = clean[:idx].strip()
            items.append({
                "category": key,
                "category_ar": ar,
                "emoji": emoji,
                "text": clean,
                "source": source,
                "priority": pri,
            })
    return items
```

Then in the extended endpoint, after `news_digest` is built:
```python
if news_digest:
    news_digest["news_items"] = _parse_news_items(news_digest)
```

**Validation:**
```bash
curl -s -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000/dashboard/extended | python3 -c "
import json, sys
d = json.load(sys.stdin)
items = d.get('news_digest', {}).get('news_items', [])
print(f'news_items count: {len(items)}')
for i in items[:3]:
    print(f'  [{i[\"category\"]}] {i[\"text\"][:50]}... (src: {i[\"source\"]})')
"
```

### 1C. Add `later_today` to Dashboard Sensor
**Problem:** Home page only shows `top_action` from `assistant_surface`. The `later_today` array (e.g. MRC stock review) is returned by API but not displayed.
**Fix:** Already in `assistant_surface` → just needs YAML change (Phase 3).

### 1D. Fix News Typo
**Problem:** Hero shows "آخر تحيث" instead of "آخر تحديث"
**Fix:** YAML change in Phase 3.

---

## PHASE 2: Configuration.yaml Updates
> Method: Edit via Samba (H:\configuration.yaml) or SSH
> Only needed if new `json_attributes` are added to sensors

### 2A. Add `news_items` to Extended Sensor
**Check current `json_attributes` for `sensor.master_ai_extended`:**
```bash
grep -A 50 'master_ai_extended' /var/lib/homeassistant/homeassistant/configuration.yaml | head -60
```
**If `news_digest` is already in json_attributes, no change needed** — `news_items` lives inside `news_digest`.
**If not, add `news_digest` to the json_attributes list.**

### 2B. Verify All Three Sensors Have Correct Attributes
```bash
# Dashboard sensor (60s)
grep -A 30 'master_ai_dashboard' /var/lib/homeassistant/homeassistant/configuration.yaml

# Extended sensor (120s)
grep -A 30 'master_ai_extended' /var/lib/homeassistant/homeassistant/configuration.yaml

# Radar sensor (120s)
grep -A 30 'master_ai_radar' /var/lib/homeassistant/homeassistant/configuration.yaml
```

**After any configuration.yaml change:**
```bash
# Validate YAML
python3 -c "import yaml; yaml.safe_load(open('/var/lib/homeassistant/homeassistant/configuration.yaml'))"
# Then reload via HA API or restart
```

---

## PHASE 3: Dashboard YAML Rebuild (All 7 Pages)
> Method: Write YAML on Windows via Filesystem:write_file → Samba → rebuild script
> CRITICAL: Arabic text must be written via this workflow, NOT Python \uXXXX

### Page-by-Page Changes:

---

### PAGE 1: HOME (master-ai) — Grade B → A

**Changes:**
1. **Remove Quick Actions row (3b)** — duplicates Navigation row
2. **Add later_today section** between Decision Card and Status Grid:
   ```yaml
   # ── LATER TODAY ──
   - type: markdown
     card_mod:
       style: |
         ha-card {
           {% set d = 'sensor.master_ai_dashboard' %}
           {% set asf = state_attr(d,'assistant_surface') %}
           {% if not asf or not asf.later_today or asf.later_today | length == 0 %}
           display: none;
           {% else %}
           background: rgba(255,255,255,0.02);
           border: 1px solid rgba(255,255,255,0.06);
           border-radius: 16px;
           padding: 8px 14px;
           margin: 4px 8px 0;
           {% endif %}
         }
         ha-markdown { font-size: 14px; direction: rtl; line-height: 1.7; }
     content: >
       {% set d = 'sensor.master_ai_dashboard' %}
       {% set asf = state_attr(d,'assistant_surface') %}
       {% if asf and asf.later_today and asf.later_today | length > 0 %}
       ⏳ **لاحقاً اليوم**
       {% for item in asf.later_today[:3] %}
       · {{ item.headline }}{% if item.delay_cost %} — {{ item.delay_cost }}{% endif %}
       {% endfor %}
       {% endif %}
   ```

3. **Hide Command Feedback when empty** — add `display: none` condition:
   ```yaml
   # In card_mod style:
   {% if not state_attr('sensor.master_ai_dashboard','last_cmd_command') %}
   display: none;
   {% endif %}
   ```

4. **Add next event preview to Events status card** — show event name not just count

5. **Merge Navigation from 6 columns to 7** (add المساعد button):
   ```yaml
   columns: 7
   # Add:
   - type: button
     name: المساعد
     icon: mdi:robot-outline
     tap_action:
       action: navigate
       navigation_path: /master-ai-dashboard/sub-assistant
     show_state: false
   ```

---

### PAGE 2: TRADING (sub-radar) — Grade A → A+

**Changes:**
1. **Add Quick Actions row** after Market Pulse:
   ```yaml
   - type: grid
     columns: 4
     square: false
     cards:
       - type: button
         name: تبديل الرادار
         icon: mdi:radar
         tap_action:
           action: call-service
           service: script.turn_on
           target:
             entity_id: script.master_ai_radar_toggle
         show_state: false
         card_mod:
           style: |
             ha-card { border-radius: 14px; height: 48px; }
             ha-card .name { font-size: 11px !important; }
       - type: button
         name: الأسهم
         icon: mdi:chart-bar
         tap_action:
           action: call-service
           service: script.turn_on
           target:
             entity_id: script.master_ai_stocks
         show_state: false
         card_mod:
           style: |
             ha-card { border-radius: 14px; height: 48px; }
             ha-card .name { font-size: 11px !important; }
       - type: button
         name: أعلى
         icon: mdi:arrow-up-bold
         tap_action:
           action: call-service
           service: script.turn_on
           target:
             entity_id: script.master_ai_radar_top
         show_state: false
         card_mod:
           style: |
             ha-card { border-radius: 14px; height: 48px; }
             ha-card .name { font-size: 11px !important; }
       - type: button
         name: الحالة
         icon: mdi:information-outline
         tap_action:
           action: call-service
           service: script.turn_on
           target:
             entity_id: script.master_ai_radar_status
         show_state: false
         card_mod:
           style: |
             ha-card { border-radius: 14px; height: 48px; }
             ha-card .name { font-size: 11px !important; }
   ```

2. **Cap Watchlist to 6 items** — change `wl[:12]` to `wl[:6]`

3. **Fix Command Feedback** — replace `\u2705` with actual ✅ emoji (write via Windows workflow)

---

### PAGE 3: CALENDAR (sub-calendar-tasks) — Grade C → B+

**Changes:**
1. **Convert Events from markdown dump to card-per-event**:
   Instead of one big markdown with `---` separators, use conditional individual markdown cards.
   Since HA doesn't support dynamic card generation, keep as single markdown but improve formatting:
   ```yaml
   content: |
     {% set e = 'sensor.master_ai_extended' %}
     {% set evts = state_attr(e,'events_list') %}
     {% if evts and evts | length > 0 %}
     {% for ev in evts %}
     {% set is_shift = ev.summary and ('Morning' in ev.summary or 'Afternoon' in ev.summary or 'Night' in ev.summary or 'off' in ev.summary) %}
     {% if not is_shift %}
     📅 **{{ ev.summary }}** · {{ ev.start_ts[:16] if ev.start_ts else '' }}{% if ev.location %} · 📍 {{ ev.location }}{% endif %}

     {% endif %}
     {% endfor %}
     {% else %}
     ✅ لا مواعيد — وقتك متاح
     {% endif %}
   ```
   Key improvement: **Filter out shift events** (they're already in the shift section).

2. **Highlight today in Shift Schedule**:
   Already done (has `◀️` marker), but improve with background color via card_mod.

3. **Add action buttons**:
   ```yaml
   - type: grid
     columns: 3
     square: false
     cards:
       - type: button
         name: المورنينق
         icon: mdi:weather-sunny
         tap_action:
           action: call-service
           service: script.turn_on
           target:
             entity_id: script.master_ai_morning
         show_state: false
         card_mod:
           style: |
             ha-card { border-radius: 14px; height: 48px; }
             ha-card .name { font-size: 11px !important; }
       - type: button
         name: الرئيسية
         icon: mdi:home
         tap_action:
           action: navigate
           navigation_path: /master-ai-dashboard/master-ai
         show_state: false
         card_mod:
           style: |
             ha-card { border-radius: 14px; height: 48px; }
             ha-card .name { font-size: 11px !important; }
       - type: button
         name: البريد
         icon: mdi:email-outline
         tap_action:
           action: navigate
           navigation_path: /master-ai-dashboard/sub-email
         show_state: false
         card_mod:
           style: |
             ha-card { border-radius: 14px; height: 48px; }
             ha-card .name { font-size: 11px !important; }
   ```

4. **Fix Command Feedback unicode**

---

### PAGE 4: HOME CONTROL (sub-home) — Grade C → B+

**Changes:**
1. **Remove Live Status grid (section 3)** — duplicates Pulse Hero
2. **Convert Rooms Grid from text to structured format**:
   Keep 2-column grid but improve content — show room name as bold header with device status below:
   ```yaml
   content: |
     {% set d = 'sensor.master_ai_dashboard' %}
     {% set rooms = state_attr(d, 'rooms_summary') %}
     {% if rooms %}
     {% for r in rooms %}
     {% set lo = r.lights_on | int(0) %}
     {% set ac = r.ac_state | default('off') %}
     {% set tp = r.ac_temp %}
     {% if lo > 0 or ac != 'off' %}
     **{{ r.room }}** {% if lo > 0 %}💡{{ lo }}{% endif %}{% if ac != 'off' %} ❄️{% if tp %} {{ tp | round(0) | int }}°{% endif %}{% endif %}

     {% endif %}
     {% endfor %}
     {% endif %}
   ```

3. **Add control buttons**:
   ```yaml
   - type: grid
     columns: 3
     square: false
     cards:
       - type: button
         name: أطفئ الكل
         icon: mdi:power
         tap_action:
           action: call-service
           service: script.turn_on
           target:
             entity_id: script.master_ai_alloff
         show_state: false
       - type: button
         name: الرئيسية
         icon: mdi:home
         tap_action:
           action: navigate
           navigation_path: /master-ai-dashboard/master-ai
         show_state: false
       - type: button
         name: النظام
         icon: mdi:server
         tap_action:
           action: navigate
           navigation_path: /master-ai-dashboard/sub-system-health
         show_state: false
   ```

4. **Fix Arabic encoding** — "هادية" etc. must be rewritten via Windows workflow

---

### PAGE 5: SYSTEM (sub-system-health) — Grade B → A

**Changes:**
1. **Add Git Log section** (last 5 commits):
   ```yaml
   - type: markdown
     card_mod:
       style: |
         ha-card {
           background: rgba(255,255,255,0.02);
           border: 1px solid rgba(255,255,255,0.05);
           border-radius: 18px;
           padding: 12px 16px;
           margin-top: 8px;
         }
         ha-markdown { font-size: 13px; opacity: 0.85; line-height: 1.8; font-family: var(--font-mono, monospace); }
     content: |
       **📝 آخر التعديلات**
       {% set e = 'sensor.master_ai_extended' %}
       {% set log = state_attr(e,'git_log') %}
       {% if log and log | length > 0 %}
       {% for l in log[:5] %}
       `{{ l[:60] }}`
       {% endfor %}
       {% else %}
       لا سجل متاح
       {% endif %}
   ```

2. **Add Tool Usage breakdown**:
   ```yaml
   - type: markdown
     card_mod:
       style: |
         ha-card {
           background: rgba(255,255,255,0.02);
           border: 1px solid rgba(255,255,255,0.05);
           border-radius: 18px;
           padding: 10px 16px;
           margin-top: 8px;
         }
         ha-markdown { font-size: 14px; direction: rtl; line-height: 1.8; }
     content: >
       {% set e = 'sensor.master_ai_extended' %}
       {% set tu = state_attr(e,'tool_usage') %}
       {% if tu %}
       🔧 **الأدوات:**
       {% for k, v in tu.items() %}{{ k }}: {{ v }}{% if not loop.last %} · {% endif %}{% endfor %}
       {% endif %}
   ```

3. **Format Memory + Cost as mini cards in grid**

---

### PAGE 6: EMAIL (sub-email) — Grade C → B

**Changes:**
1. **Replace HTML div blocks with pure markdown** — remove `<div style="...">` blocks:
   ```yaml
   content: |
     ### الرسائل — آخر 24 ساعة
     {% set e = 'sensor.master_ai_extended' %}
     {% set msgs = state_attr(e,'email_messages') %}
     {% if msgs and msgs | length > 0 %}
     {% for m in msgs %}
     {% set pri = m.priority | default(1) %}
     {% if pri >= 3 %}🔴{% elif pri == 2 %}🟡{% else %}🟢{% endif %} **{{ m.subject[:50] }}**
     {{ m['from'][:30] }} · {{ m.source_label }} · {{ m.time }}

     {% endfor %}
     {% else %}
     ✅ صندوقك فاضي
     {% endif %}
   ```

2. **Add refresh button**:
   ```yaml
   - type: button
     name: تحديث البريد
     icon: mdi:email-sync
     tap_action:
       action: call-service
       service: script.turn_on
       target:
         entity_id: script.master_ai_inbox  # May need to create this script
     show_state: false
   ```

3. **Fix Command Feedback unicode**

---

### PAGE 7: NEWS (sub-news) — Grade D → B

**Changes (requires Phase 1B backend change first):**
1. **Add Top 3 Decision Layer** after Hero:
   ```yaml
   - type: markdown
     card_mod:
       style: |
         ha-card {
           background: linear-gradient(135deg, rgba(231,76,60,0.06), rgba(231,76,60,0.02));
           border: 1px solid rgba(231,76,60,0.12);
           border-radius: 18px;
           padding: 12px 16px;
           margin: 6px 8px 0;
         }
         ha-markdown { font-size: 14px; direction: rtl; line-height: 2.0; }
     content: |
       {% set e = 'sensor.master_ai_extended' %}
       {% set d = state_attr(e,'news_digest') %}
       {% if d and d.news_items is defined and d.news_items | length > 0 %}
       **⚡ أهم 3 أخبار**
       {% for item in d.news_items[:3] %}
       {{ item.emoji }} **{{ item.text[:80] }}**{% if item.source %} ({{ item.source }}){% endif %}

       {% endfor %}
       {% else %}
       📰 لا أخبار — استخدم /news_now
       {% endif %}
   ```

2. **Hide empty categories** — wrap each in conditional display:none
3. **Fix typo** — "تحيث" → "تحديث"
4. **Add /news_now button**:
   ```yaml
   - type: button
     name: تحديث الأخبار
     icon: mdi:newspaper-variant
     tap_action:
       action: call-service
       service: script.turn_on
       target:
         entity_id: script.master_ai_news
     show_state: false
   ```

---

## PHASE 4: Validation & Deploy

### Step-by-step validation:
```bash
# 1. After server.py patches
python3 _tools/quick_check.py
python3 _tools/smoke_test.py

# 2. Test endpoints
curl -s -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000/dashboard | python3 -m json.tool | head -20
curl -s -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000/dashboard/extended | python3 -c "import json,sys; d=json.load(sys.stdin); print('news_items:', len(d.get('news_digest',{}).get('news_items',[])))"
curl -s -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000/dashboard/radar | python3 -m json.tool | head -10

# 3. After dashboard YAML
python3 -c "import yaml; yaml.safe_load(open('/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml')); print('YAML OK')"

# 4. HA reload
# Via HA API or restart

# 5. Git commit
cd /var/lib/homeassistant/share/master_ai
git add -A
git commit -m "V12: Dashboard upgrade — 7 pages improved, news items API, unicode fixes"

# 6. Visual check via Chrome
# Open each page and verify rendering
```

---

## EXECUTION ORDER (for Claude Code)

```
1. PRE-FLIGHT (backup + health check)
2. PHASE 1B: Patch server.py — add _parse_news_items() + wire into extended endpoint
3. PHASE 1: Run quick_check + smoke_test + restart
4. PHASE 2: Check configuration.yaml — verify json_attributes
5. PHASE 3: Write all 7 pages YAML → deploy via rebuild script
6. PHASE 4: Validate all endpoints + YAML + visual check
7. Git commit
```

## IMPORTANT RULES
- **server.py changes**: ONLY via `_tools/patchers/apply_text_patch.py`
- **Dashboard YAML**: Write on machine with correct UTF-8 → copy to RPi → rebuild
- **Arabic text**: NEVER use Python \uXXXX in YAML — always actual UTF-8
- **Backward compatible**: All existing API fields MUST remain unchanged
- **Minimal changes**: Don't rewrite what works — patch what's broken
- **Test after each phase**: Don't proceed to next phase if current fails

## FILES THAT WILL CHANGE
1. `server.py` — add `_parse_news_items()` function + wire into extended endpoint
2. `/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml` — all 7 pages
3. `/var/lib/homeassistant/homeassistant/configuration.yaml` — ONLY if json_attributes need update
4. `/var/lib/homeassistant/homeassistant/scripts.yaml` — ONLY if new scripts needed (inbox refresh)

## ESTIMATED SCOPE
- server.py: ~40 new lines (news parser)
- dashboard YAML: ~1581 → ~1650 lines (net +70 lines)
- Risk: LOW (backward compatible, existing endpoints unchanged)
- Time: ~45 min for Claude Code execution
