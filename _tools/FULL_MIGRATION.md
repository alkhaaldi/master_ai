# FULL DASHBOARD HTML MIGRATION — Claude Code Task
# Date: 2026-03-27
# Priority: CRITICAL
# Scope: Build 6 remaining HTML pages + fix ALL navigation

## BACKGROUND
We already have 6 HTML pages working:
- /trading/home (الرئيسية) ✅
- /trading/radar (التداول) ✅  
- /trading/signals (الإشارات) ✅
- /trading/positions (المراكز) ✅
- /trading/journal (السجل) ✅
- /trading/brain (العقل) ✅

But 6 pages are still HA-native and when user clicks their nav buttons,
it breaks because the page tries to navigate from HTTPS (ai.salem-home.com) 
to HTTP (192.168.109.123:8123) which is blocked by mixed-content policy.

## GOAL
Build 6 NEW HTML pages for the remaining dashboard sections.
Same navy+gold Boursa Kuwait design. Same shared nav bar.
ALL pages must be same-origin navigation (no HA links needed).

## NEW PAGES TO BUILD

### 1. www/trading/calendar.html — المواعيد
Endpoint: GET /dashboard/extended (has calendar_next, calendar_events)
Also: GET /dashboard (has pending_tasks)
Content:
- Next event card
- Today's events list  
- Upcoming events
- Tasks/reminders

### 2. www/trading/home-control.html — البيت
Endpoint: GET /dashboard (has active_devices_count, active_lights, climate_summary)
Also: GET /dashboard/extended (has home_status, entities summary)
Content:
- Active devices count
- Lights status
- Climate summary (AC/temperature)
- Covers/blinds status
- Device health overview

### 3. www/trading/assistant.html — المساعد
Endpoint: GET /dashboard (has ai_insight, autonomy_level, last_interaction)
Also: GET /dashboard/extended (has assistant data)
Content:
- AI Insight card (current analysis)
- Autonomy level
- Recent interactions
- System suggestions

### 4. www/trading/system.html — النظام
Endpoint: GET /dashboard (has cpu, memory, temp)
Also: GET /dashboard/extended (has system_health details)
Content:
- CPU usage gauge
- Memory usage gauge
- Temperature gauge
- Disk usage
- Service status (Master AI, HA, Bridge)
- Uptime
- Network status

### 5. www/trading/email.html — البريد
Endpoint: GET /dashboard/extended (has email_unread, email_priority)
Also: GET /dashboard (has email summary)
Content:
- Unread count
- Priority emails list
- Recent emails
- Email categories

### 6. www/trading/news.html — الأخبار
Endpoint: GET /dashboard/extended (has news items from RSS feeds)
Content:
- Top news headlines
- News by category (economy, world, tech, KSE)
- Source labels
- Refresh timestamp

## NAVIGATION FIX (CRITICAL)
Update navTo() in ALL pages (home.html + all 6 existing + all 6 new) to use same-origin:

```javascript
function navTo(path) {
  const MAP = {
    '/master-ai-dashboard/master-ai': '/trading/home',
    '/master-ai-dashboard/sub-radar': '/trading/radar',
    '/master-ai-dashboard/sub-signals': '/trading/signals',
    '/master-ai-dashboard/sub-brain': '/trading/brain',
    '/master-ai-dashboard/sub-positions': '/trading/positions',
    '/master-ai-dashboard/sub-journal': '/trading/journal',
    '/master-ai-dashboard/sub-calendar-tasks': '/trading/calendar',
    '/master-ai-dashboard/sub-home': '/trading/home-control',
    '/master-ai-dashboard/sub-assistant': '/trading/assistant',
    '/master-ai-dashboard/sub-system-health': '/trading/system',
    '/master-ai-dashboard/sub-email': '/trading/email',
    '/master-ai-dashboard/sub-news': '/trading/news',
  };
  window.location.href = MAP[path] || path;
}
```

## ALSO UPDATE home.html nav buttons
Change the onclick to use direct paths instead of HA paths:
```html
<a class="nav-btn" onclick="window.location.href='/trading/radar'">التداول</a>
<a class="nav-btn" onclick="window.location.href='/trading/calendar'">المواعيد</a>
<!-- etc -->
```

## HA DASHBOARD YAML
Update all sub-pages to use iframe cards pointing to the new HTML pages:
- sub-calendar-tasks → iframe https://ai.salem-home.com/trading/calendar
- sub-home → iframe https://ai.salem-home.com/trading/home-control
- sub-assistant → iframe https://ai.salem-home.com/trading/assistant
- sub-system-health → iframe https://ai.salem-home.com/trading/system
- sub-email → iframe https://ai.salem-home.com/trading/email
- sub-news → iframe https://ai.salem-home.com/trading/news

## OPEN_PATHS
Ensure /dashboard and /dashboard/extended are in OPEN_PATHS (should already be done).

## DESIGN SYSTEM (same as trading pages)
- Background: #070D17
- Gold: #C6974B
- Fonts: Tajawal + Noto Kufi Arabic + IBM Plex Mono
- RTL Arabic, responsive
- Shared topbar + nav bar across all pages
- Auto-refresh 60s

## EXECUTION ORDER
1. First: Fix navTo in home.html to use direct paths (no HA paths at all)
2. Build 6 new HTML pages
3. Add routes in modules/panel.py for new pages
4. Update HA YAML for all sub-pages to use iframes
5. Test all 12 pages
6. Test all nav buttons between pages
7. git commit + restart + HA reload

## IMPORTANT
- Read existing HTML pages (radar.html, home.html) for design reference
- Use same CSS variables, same topbar, same nav bar
- Each page fetches data from /dashboard and/or /dashboard/extended
- Pages should gracefully handle missing data (show "لا بيانات")
- No HA internal links anywhere — everything is same-origin
