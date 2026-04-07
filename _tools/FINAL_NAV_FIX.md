# FINAL Nav + Cache Fix — Claude Code Task
# Date: 2026-03-27
# Priority: CRITICAL

## TWO PROBLEMS TO FIX

### Problem 1: Browser/Cloudflare caching old HTML files
The navTo fix was deployed to disk but browser still loads old version.

**FIX:** Add no-cache headers to all HTML responses in modules/panel.py:
```python
# In the function that serves trading HTML files:
response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
response.headers["Pragma"] = "no-cache"  
response.headers["Expires"] = "0"
```

### Problem 2: Navigation from HTTPS page to HTTP HA fails
The page is served from `https://ai.salem-home.com` (Cloudflare tunnel).
Trying to navigate to `http://192.168.109.123:8123/...` fails because:
- Mixed content (HTTPS → HTTP blocked by browser)
- Cross-origin restrictions

**FIX:** ALL navigation should stay on same origin (ai.salem-home.com).
The navTo function should:
- For trading pages (radar, signals, positions, journal, brain) → navigate to `/trading/xxx` (same origin)
- For home page → navigate to `/trading/home`
- For HA-only pages (calendar, home-control, assistant, system, email, news) → these DON'T have HTML equivalents, so show a message or disable them

**Updated navTo function for home.html:**
```javascript
function navTo(haPath) {
  // Map HA paths to same-origin HTML pages
  const MAP = {
    '/master-ai-dashboard/sub-radar': '/trading/radar',
    '/master-ai-dashboard/sub-signals': '/trading/signals',
    '/master-ai-dashboard/sub-brain': '/trading/brain',
    '/master-ai-dashboard/sub-positions': '/trading/positions',
    '/master-ai-dashboard/sub-journal': '/trading/journal',
    '/master-ai-dashboard/master-ai': '/trading/home',
  };
  
  if (MAP[haPath]) {
    window.location.href = MAP[haPath];
    return;
  }
  
  // For HA-only pages, show toast message
  const names = {
    '/master-ai-dashboard/sub-calendar-tasks': 'المواعيد',
    '/master-ai-dashboard/sub-home': 'البيت',
    '/master-ai-dashboard/sub-assistant': 'المساعد',
    '/master-ai-dashboard/sub-system-health': 'النظام',
    '/master-ai-dashboard/sub-email': 'البريد',
    '/master-ai-dashboard/sub-news': 'الأخبار',
  };
  const name = names[haPath] || haPath;
  
  // Try to navigate to HA (works when accessed from local network)
  // If inside HA iframe (same origin), use parent navigation
  try {
    if (window !== window.top) {
      window.top.location.href = haPath;
      return;
    }
  } catch(e) {}
  
  // Standalone: show message that this page is HA-only
  alert('صفحة "' + name + '" متوفرة فقط داخل Home Assistant');
}
```

## FILES TO EDIT

### 1. modules/panel.py — add no-cache headers
Find the function that serves trading HTML files and add cache-control headers to the response.

### 2. www/trading/home.html — fix navTo function
Replace the current navTo with the version above that uses same-origin routing.

## VALIDATION
After fix:
1. Hard refresh (Ctrl+Shift+R) should load new version
2. Click "التداول" → should go to /trading/radar (same origin, works!)
3. Click "الإشارات" → should go to /trading/signals
4. Click "المواعيد" → should show alert (HA-only page)
5. No "refused to connect" errors

## ALSO
- git commit
- restart master-ai (for panel.py cache headers to take effect)
