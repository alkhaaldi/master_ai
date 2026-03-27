# Home Page Redesign — Claude Code Task
# Date: 2026-03-27
# Priority: HIGH
# Scope: Replace HA native home page with professional HTML (navy+gold theme)
# Source: ChatGPT consultation + user approval

## READ FIRST
1. Read CLAUDE.md
2. Read _tools/OPERATIONAL_ACCESS_MATRIX.md
3. Read current home page YAML: lines 3-309 of master_ai_dashboard.yaml

## GOAL
Replace the Master AI home page (currently native HA cards) with a single iframe
showing a professional HTML page in the same Boursa Kuwait navy+gold theme as the trading platform.

## CRITICAL CONSTRAINT — DO NOT BREAK NAVIGATION
The 9 nav buttons MUST navigate to the correct HA dashboard subviews.
Inside iframe, use: `window.top.location.href = '/master-ai-dashboard/sub-radar'`
NOT `window.location.href` (that stays inside iframe).

## CURRENT HOME PAGE SECTIONS (from YAML lines 3-309):
1. **Hero** — "Master AI" v9.0.0, uptime, status badge
2. **AI Insight** — important messages, priority alerts
3. **Daily Note** — "لاحظ اليوم" observation
4. **Status Grid** — 4 chips: shift, home heartbeat, radar, life 
5. **Top3 Trading Teaser** — golden bar with best stock
6. **Navigation** — 9 buttons: التداول, المواعيد, البيت, المساعد, النظام, البريد, الأخبار, الإشارات, العقل

## EXISTING ENDPOINTS TO USE
Data comes from TWO existing endpoints (DO NOT create new endpoints):

### GET /dashboard (sensor.master_ai_dashboard, 60s refresh)
Returns:
- version, uptime_seconds, status, autonomy_level
- shift info (shift_label, shift_type, next_shift)
- ai_insight (text, level, timestamp)
- active_devices_count, active_lights, climate_summary
- anomaly_count, pending_tasks

### GET /dashboard/extended (sensor.master_ai_extended, 120s refresh)  
Returns:
- daily_note (observation text)
- home_status (entities summary, health)
- radar_top3 (best 3 stocks from radar)
- email_unread, calendar_next
- system_health (cpu, mem, temp, disk)

### GET /dashboard/signals (already open, no auth)
Returns:
- decision_card (best stock with confluence)
- signal_counts
- market_open, bridge_online

## NEW FILE TO CREATE
```
/home/pi/master_ai/www/home.html
```

Served at: `/trading/home` (add route in modules/panel.py)
Or better: create a dedicated route `/home` 

## HTML PAGE DESIGN

### Same design system as trading pages:
- Background: #070D17 (navy-900)
- Gold accent: #C6974B
- Fonts: Tajawal + Noto Kufi Arabic + IBM Plex Mono
- RTL Arabic
- Responsive

### Layout (top to bottom):

#### 1. TOPBAR (compact)
- "Master AI" brand + version
- Status dot (green=online, red=offline)
- Uptime
- Clock (Kuwait time)

#### 2. HERO SECTION
- Large "Master AI" title with gold accent
- Version + uptime + status badge
- Autonomy level indicator

#### 3. AI INSIGHT CARD
- Priority-colored border (green=info, amber=warning, red=alert)
- Icon + title + message text
- Timestamp

#### 4. DAILY NOTE (لاحظ اليوم)
- Compact card with observation text
- If no note: show "لا ملاحظات"

#### 5. STATUS GRID (4 cards)
- الشفت: shift label + type + next shift
- نبض البيت: active devices + lights + climate
- الرادار: signal counts + market status + bridge status
- النظام: CPU + Memory + Temp

#### 6. TRADING TEASER (gold accent bar)
- Best stock from decision_card
- Symbol + price + confluence score + verdict
- Click → goes to trading radar page

#### 7. NAVIGATION GRID (9 buttons)
- Same 9 destinations as current
- Each button: icon + Arabic label
- onClick: `window.top.location.href = '/master-ai-dashboard/sub-xxx'`
- Active/hover: gold border glow

### Navigation paths (EXACT — do not change):
```
التداول  → /master-ai-dashboard/sub-radar
المواعيد → /master-ai-dashboard/sub-calendar-tasks
البيت   → /master-ai-dashboard/sub-home
المساعد → /master-ai-dashboard/sub-assistant
النظام  → /master-ai-dashboard/sub-system-health
البريد  → /master-ai-dashboard/sub-email
الأخبار → /master-ai-dashboard/sub-news
الإشارات → /master-ai-dashboard/sub-signals
العقل   → /master-ai-dashboard/sub-brain
```

### Data fetching:
```javascript
// Fetch both endpoints
const [dash, ext, sig] = await Promise.all([
  fetch('/dashboard').then(r => r.json()),
  fetch('/dashboard/extended').then(r => r.json()),
  fetch('/dashboard/signals').then(r => r.json()).catch(() => null)
]);
```

Auto-refresh: 60 seconds

## HA DASHBOARD YAML CHANGES

Replace the entire home page content (lines ~3-309) with a single iframe card:

```yaml
  - path: master-ai
    title: Master AI
    icon: mdi:brain
    type: panel
    cards:
      - type: iframe
        url: https://ai.salem-home.com/trading/home
        aspect_ratio: 100%
        card_mod:
          style: |
            ha-card {
              overflow: hidden;
              border: none;
              border-radius: 0;
              background: #070D17;
            }
```

IMPORTANT: Keep ALL subview pages (sub-radar, sub-signals, etc.) exactly as they are!
Only replace the main "master-ai" page content.

## OPEN_PATHS
Add `/dashboard` and `/dashboard/extended` to OPEN_PATHS if not already there.
These are needed for the HTML page to fetch data without auth.

## EXECUTION STEPS
1. Check what /dashboard and /dashboard/extended return (curl test)
2. Check if they're in OPEN_PATHS, if not add them
3. Create www/home.html (~600-800 lines)
4. Add route for /trading/home in modules/panel.py  
5. Backup current home page YAML section
6. Replace home page in master_ai_dashboard.yaml with single iframe
7. quick_check + smoke_test
8. git commit + restart
9. HA YAML reload
10. Visual verification

## IMPORTANT RULES
- Python edits via apply_text_patch.py
- YAML via Samba (Filesystem:write_file → H:\)
- Arabic text: never Python \uXXXX
- DO NOT modify any subview pages
- DO NOT break existing navigation paths
- Backward compatible
- Test navigation from iframe: window.top.location must work
