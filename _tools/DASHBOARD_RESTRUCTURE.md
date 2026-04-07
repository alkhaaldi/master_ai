# Trading Dashboard Restructure — Complete Plan
# Claude Code: Execute on RPi + claude.ai handles HTML/YAML

## Context
Gemini 2.5 Pro is now the primary stock analyst. Several old pages are redundant.
This plan restructures the dashboard from 15 pages to 8 core trading pages.

## Agreed Final Structure (7 Core Pages)

### KEEP:
1. `home.html` — Command center
2. `radar.html` — 128-stock surveillance  
3. `analysis.html` — Gemini deep technical analysis ⭐ (THE STAR)
4. `positions.html` — Portfolio monitoring & P&L
5. `journal.html` — Trade journal & learning
6. `news.html` — Boursa RSS + Gemini news
7. `system.html` — System health

### REMOVE from dashboard (pages stay on disk, just hidden):
- `scalper.html` — Will be rebuilt later with Gemini prompt (not accurate enough now)
- `decisions.html` — Replaced by analysis.html
- `personality.html` — Replaced by analysis.html  
- `brain.html` — Developer stats, not trader-facing
- `signals.html` — Merged into radar/analysis
- `assistant.html` — Merged into analysis (follow-up chat later)

### MOVE OUT of trading nav (keep accessible but not in main menu):
- `home-control.html` — Smart home, separate from trading
- `email.html` — Utility, not trading-core
- `calendar.html` — Widget in home, not standalone

---

## Step 1: Update `master_ai_dashboard.yaml`

**Location:** `/var/lib/homeassistant/config/master_ai_dashboard.yaml`
(Accessible via Samba: `\\192.168.109.123\config\master_ai_dashboard.yaml`)

### New YAML structure (replace entire file):

```yaml
title: Master AI
views:
  # ═══ MAIN: Home ═══
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

  # ═══ RADAR ═══
  - path: sub-radar
    title: الرادار
    icon: mdi:chart-areaspline
    subview: true
    type: panel
    cards:
      - type: iframe
        url: https://ai.salem-home.com/trading/radar
        aspect_ratio: 100%
        card_mod:
          style: |
            ha-card {
              overflow: hidden;
              border: none;
              border-radius: 0;
              background: #070D17;
            }

  # ═══ ANALYSIS (Gemini) ═══
  - path: sub-analysis
    title: التحليل الفني
    icon: mdi:chart-line
    subview: true
    type: panel
    cards:
      - type: iframe
        url: https://ai.salem-home.com/trading/analysis
        aspect_ratio: 100%
        card_mod:
          style: |
            ha-card {
              overflow: hidden;
              border: none;
              border-radius: 0;
              background: #070D17;
            }

  # ═══ POSITIONS ═══
  - path: sub-positions
    title: المراكز
    icon: mdi:briefcase-outline
    subview: true
    type: panel
    cards:
      - type: iframe
        url: https://ai.salem-home.com/trading/positions
        aspect_ratio: 100%
        card_mod:
          style: |
            ha-card {
              overflow: hidden;
              border: none;
              border-radius: 0;
              background: #070D17;
            }

  # ═══ JOURNAL ═══
  - path: sub-journal
    title: اليومية
    icon: mdi:book-open-page-variant
    subview: true
    type: panel
    cards:
      - type: iframe
        url: https://ai.salem-home.com/trading/journal
        aspect_ratio: 100%
        card_mod:
          style: |
            ha-card {
              overflow: hidden;
              border: none;
              border-radius: 0;
              background: #070D17;
            }

  # ═══ NEWS ═══
  - path: sub-news
    title: الأخبار
    icon: mdi:newspaper-variant-outline
    subview: true
    type: panel
    cards:
      - type: iframe
        url: https://ai.salem-home.com/trading/news
        aspect_ratio: 100%
        card_mod:
          style: |
            ha-card {
              overflow: hidden;
              border: none;
              border-radius: 0;
              background: #070D17;
            }

  # ═══ SYSTEM ═══
  - path: sub-system
    title: النظام
    icon: mdi:server
    subview: true
    type: panel
    cards:
      - type: iframe
        url: https://ai.salem-home.com/trading/system
        aspect_ratio: 100%
        card_mod:
          style: |
            ha-card {
              overflow: hidden;
              border: none;
              border-radius: 0;
              background: #070D17;
            }

  # ═══ UTILITY PAGES (hidden from main nav, accessible via URL) ═══
  - path: sub-home-control
    title: البيت
    icon: mdi:home-thermometer-outline
    subview: true
    type: panel
    cards:
      - type: iframe
        url: https://ai.salem-home.com/trading/home-control
        aspect_ratio: 100%
        card_mod:
          style: |
            ha-card {
              overflow: hidden;
              border: none;
              border-radius: 0;
              background: #070D17;
            }

  - path: sub-email
    title: البريد
    icon: mdi:email-outline
    subview: true
    type: panel
    cards:
      - type: iframe
        url: https://ai.salem-home.com/trading/email
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

## Step 2: Update home.html nav links

The home page nav bar needs to reflect the new 8-page structure.
Find the nav section in `www/trading/home.html` and update to:

### New Nav Links (Arabic):
```
🏠 الرئيسية (home) — current page
📡 الرادار (radar)
🔍 التحليل الفني (analysis) — THE STAR
💼 المراكز (positions)
📓 اليومية (journal)
📰 الأخبار (news)
⚙️ النظام (system)
```

Remove links to: scalper, decisions, personality, brain, signals, assistant, calendar, email, home-control
(These pages still exist on disk, just not in the main nav)

### How to find and edit:
Look for the `.nav-bar` or nav links section in home.html.
Replace all navigation links with the 8 core pages.

---

## Step 3: Update nav links in ALL remaining pages

Each HTML page has a nav bar at the bottom. Update these pages:
- `radar.html`  
- `positions.html`
- `journal.html`
- `news.html`
- `system.html`
- `analysis.html`
- `home.html`

### Standard nav bar HTML for all pages:
```html
<div class="nav-bar">
  <a class="nav-link" href="home">🏠 الرئيسية</a>
  <a class="nav-link" href="radar">📡 الرادار</a>
  <a class="nav-link" href="analysis">🔍 التحليل</a>
  <a class="nav-link" href="positions">💼 المراكز</a>
  <a class="nav-link" href="journal">📓 اليومية</a>
  <a class="nav-link" href="news">📰 الأخبار</a>
  <a class="nav-link" href="system">⚙️ النظام</a>
</div>
```

The `active` class should be set on the current page's link.

---

## Step 4: Backend engines — NO CHANGES needed

All backend engines stay as they are:
- signal_engine.py → feeds scalper/radar
- trading_brain.py → internal stats, not user-facing
- trading_decision_engine.py → kept as fallback/data source
- golden_engine.py → pattern data for Gemini
- stock_personality_engine.py → metadata for analysis
- sr_engine.py → S/R levels fed to Gemini prompt
- risk_engine.py → deterministic risk limits
- position_engine.py → portfolio monitoring
- stock_radar.py → 128 stock surveillance
- journal_engine.py → trade journal
- bridge_client.py → TradingView data
- stock_analyzer.py → NEW: Gemini analysis orchestrator
- news_engine.py → NEW: Boursa RSS + Gemini news

No Python files need to be modified for this restructure.

---

## Step 5: Update CLAUDE_CONTEXT.md

Update the Dashboard section in CLAUDE_CONTEXT.md:

```markdown
## Dashboard Pages (7 core + 2 utility)
All served as iframes in Home Assistant via Cloudflare tunnel.

### Core Trading Pages:
1. home.html — Command center, workflow launcher
2. radar.html — 128-stock surveillance, market-wide monitoring
3. analysis.html — Gemini 2.5 Pro deep technical analysis (click any stock) ⭐
4. positions.html — Portfolio monitoring, P&L, active trade management
5. journal.html — Trade journal, performance review
6. news.html — Boursa RSS + Gemini news (economy/world/tech)
7. system.html — System health monitoring

### Utility (accessible but outside main nav):
- home-control.html — Smart home controls
- email.html — Email management

### Archived (files kept on disk, removed from nav):
- scalper.html — To be rebuilt later with Gemini-powered scanning
- decisions.html — Replaced by analysis.html
- personality.html — Replaced by analysis.html
- brain.html — Developer stats only
- signals.html — Merged into radar
- assistant.html — To be merged into analysis
- calendar.html — To be merged into home

### Workflow:
Discover (radar) → Analyze (analysis/news) → Execute (positions) → Review (journal)
```

---

## Step 6: Verify after changes

1. Reload HA dashboards: Settings → Dashboards → Reload
2. Check all 8 pages load correctly via HA
3. Check nav links work on all pages
4. Verify analysis.html shows in HA as "التحليل الفني"
5. Test click-to-analyze on scalper page still works

---

## Execution Summary

| Task | Who | File(s) |
|------|-----|---------|
| Write new dashboard YAML | Claude Code | `master_ai_dashboard.yaml` |
| Update home.html nav | Claude Code | `www/trading/home.html` |
| Update nav in all 6 other pages | Claude Code | `www/trading/*.html` |
| Update CLAUDE_CONTEXT.md | Claude Code | `CLAUDE_CONTEXT.md` |
| Reload HA dashboards | User | HA UI |

## IMPORTANT NOTES
- Do NOT delete any HTML files — just remove from dashboard YAML and nav
- Do NOT modify any Python backend files
- The nav update is simple find-and-replace in each HTML file
- Backup dashboard YAML before overwriting: `cp master_ai_dashboard.yaml master_ai_dashboard.yaml.bak`
- After YAML write: user must reload HA dashboards from Settings
- scalper.html stays on disk — will be rebuilt later with Gemini-powered prompt
- 7 core pages total (was 15)
