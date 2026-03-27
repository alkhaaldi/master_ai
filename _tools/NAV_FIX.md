# Nav Button Fix — Claude Code Task
# Date: 2026-03-27
# Priority: CRITICAL
# Scope: Fix navigation buttons in home.html (and all trading pages that have nav)

## PROBLEM
The navTo() function in home.html uses `window.top.location.href = path`
where path is like `/master-ai-dashboard/sub-radar`.

This works ONLY when the page is inside an HA iframe (same origin).
But it FAILS when:
1. Page is opened standalone (ai.salem-home.com/trading/home)
2. Page is inside iframe but cross-origin (HA on different port/domain)

Because `window.top.location.href = '/master-ai-dashboard/sub-radar'` 
navigates to `https://ai.salem-home.com/master-ai-dashboard/sub-radar` which is 404.

## FIX
Update navTo() in home.html to detect context and use the correct HA base URL:

```javascript
function navTo(haPath) {
  // HA base URL — where Home Assistant lives
  const HA_BASE = 'http://192.168.109.123:8123';
  
  try {
    // If inside iframe AND same origin — use window.top (normal HA iframe)
    if (window !== window.top && window.top.location.origin.includes('8123')) {
      window.top.location.href = haPath;
      return;
    }
  } catch(e) {
    // Cross-origin iframe — can't access window.top.location
  }
  
  // Fallback: navigate to full HA URL
  window.location.href = HA_BASE + haPath;
}
```

This way:
- Inside HA iframe → uses window.top (stays inside HA)
- Standalone or cross-origin → opens full HA URL (works correctly)

## FILES TO FIX
1. `/home/pi/master_ai/www/trading/home.html` — the navTo function
2. Also check the trading teaser "click to radar" link
3. Also check any other onclick handlers that navigate to HA paths

## ALSO FIX in trading pages
The nav bars in radar.html, signals.html, positions.html, journal.html, brain.html
link to each other via `href="radar.html"` etc. — these are fine (same server).
But if any of them have links BACK to the HA home page, those need the same fix.

## VALIDATION
After fix:
1. Open https://ai.salem-home.com/trading/home directly → click التداول → should go to HA
2. Open inside HA iframe → click التداول → should navigate within HA
3. All 9 buttons work in both contexts

## AFTER FIX
- git commit -m "fix: navTo uses full HA URL when outside iframe"
