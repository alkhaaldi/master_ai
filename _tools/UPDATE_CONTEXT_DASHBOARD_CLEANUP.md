# Update CLAUDE_CONTEXT.md — Dashboard Cleanup + HTML Path Fix
# Status: READY FOR EXECUTION
# Executor: Claude Code
# Date: 2026-04-02

---

## Change 1: Add HTML Live Path warning (CRITICAL)

FIND (in Architecture section):
```
Dashboard: 9 HTML iframe pages in HA via Cloudflare tunnel (7 core + 2 utility).
```

REPLACE:
```
Dashboard: 9 HTML iframe pages in HA via Cloudflare tunnel (7 core + 2 utility).
**HTML live path:** `share/master_ai/www/trading/` (served by FastAPI). `config/www/trading/` was DELETED — do NOT recreate it.
```

---

## Change 2: Fix hooks.py description in Core Files table

FIND:
```
| hooks.py | Event hook system with 10 event types (Phase 6) |
```

REPLACE:
```
| hooks.py | Event hook system with 13 event types (Phase 6 + Layer 2) |
```

---

## Change 3: Fix Phase 1 flag count

FIND:
```
- **10 flags** in `feature_flags` table (life.db), DB-backed, thread-safe, 60s cache
```

REPLACE:
```
- **15 flags** in `feature_flags` table (life.db), DB-backed, thread-safe, 60s cache
```

---

## Change 4: Update Dashboard system.html section

FIND:
```
### Dashboard: system.html Updated
- Added: Service Health traffic lights (7 services)
- Added: KAIROS status + action log
- Added: Feature Flags toggle switches (10 flags)
- Auto-refresh: health 30s, KAIROS 60s, flags 60s
```

REPLACE:
```
### Dashboard: system.html Updated
- Added: Service Health traffic lights (7 services)
- Added: KAIROS status + action log
- Added: Feature Flags toggle switches (15 flags)
- Auto-refresh: health 30s, KAIROS 60s, flags 60s
```

---

## Change 5: Update EMA Scalper section — remove "Linked from home.html"

FIND:
```
- **Linked from home.html** as most important page
```

REPLACE:
```
- **Archived** — file kept on disk, removed from nav
```

---

## Change 6: Add Dashboard Cleanup section after Trading Integration

FIND (end of Layer 4 section):
```
- Total: 15 feature flags (10 infra + 5 trading)
```

ADD AFTER:
```

### Dashboard Cleanup (2026-04-02)
- **Duplicate HTML path eliminated:** `config/www/trading/` was a stale copy — DELETED. Only `share/master_ai/www/trading/` exists now (served by FastAPI via Cloudflare tunnel).
- **Nav bars unified:** All 9 active pages now have complete 9-link nav (home, radar, analysis, positions, journal, news, home-control, email, system). Zero links to archived pages.
- **Degraded banners:** home.html, radar.html, positions.html show amber ⚠️ banner when Bridge is offline. positions.html also shows "⚠ قديم" badge on stale prices.
- **home.html navTo MAP cleaned:** Removed 7 dead routes to archived pages, added sub-analysis and sub-system.
- **10 archived pages documented:** scalper, decisions, personality, brain, signals, assistant, calendar, reviews, strategies, fractal_report — files on disk, zero nav links.
```

---

## Validation

```bash
grep "share/master_ai/www/trading" CLAUDE_CONTEXT.md
grep "DELETED" CLAUDE_CONTEXT.md
grep "13 event" CLAUDE_CONTEXT.md
grep "15 flags" CLAUDE_CONTEXT.md
grep "9-link nav" CLAUDE_CONTEXT.md
grep "Archived" CLAUDE_CONTEXT.md | grep -i scalper

bash _tools/restart_master_ai.sh
```
