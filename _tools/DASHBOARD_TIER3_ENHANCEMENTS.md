# Dashboard Tier 3 Enhancements Plan
# Date: 2026-04-03
# Pre-req: Tier 3 patterns implemented, endpoints needed (see below)

---

## Overview: 6 dashboard enhancements for Tier 3 patterns

Each enhancement needs:
1. Backend endpoint (Claude Code builds it)
2. Frontend HTML section (claude.ai builds it)

---

## Enhancement 1: Auto-Learning Card (system.html)

### Backend Endpoint Needed: GET /api/memory-extraction/stats
Returns:
```json
{
  "today_extracted": 7,
  "week_extracted": 34,
  "last_extraction_at": "2026-04-03T11:18:00",
  "last_topics": ["CLEANING", "bedroom_ac", "Bridge"],
  "total_observations": 1847
}
```
Source: auto_memory_extractor.py extraction log + brain_observations count

### Frontend: New section in system.html after Live Tasks
```html
<div class="section">
  <div class="section-hdr">🧠 التعلم التلقائي</div>
  <div class="card" id="learning-panel">loading...</div>
</div>
```
JS: fetch /api/memory-extraction/stats, render card with:
- Today/week extraction counts
- Last extraction time (human-readable age)
- Recent topics as colored badges
- Total observations count by scope (global/stock/device)

Refresh: every 60s

---

## Enhancement 2: Intent Analytics (system.html)

### Backend Endpoint Needed: GET /api/intent-analytics
Returns:
```json
{
  "today_total": 47,
  "today_success": 43,
  "today_failed": 4,
  "avg_duration_ms": 1800,
  "top_intents": [
    {"intent": "فرص", "count": 12},
    {"intent": "تقييم", "count": 8},
    {"intent": "status", "count": 7}
  ],
  "recent": [
    {
      "timestamp": "2026-04-03T11:30:00",
      "intent": "فرص",
      "state": "responded",
      "duration_ms": 1200,
      "transitions": ["received→classified(15ms)", "classified→validated(2ms)", "validated→executing(1200ms)", "executing→responded"]
    }
  ]
}
```
Source: intent_state_machine.py audit logs (intent_audit table)

### Frontend: New section in system.html
Show:
- Summary bar: total | success | failed | avg time
- Top intents as horizontal bars
- Recent 5 intents as timeline with state badges
- Color: green=responded, red=failed, amber=slow(>3s)

Refresh: every 30s

---

## Enhancement 3: Brain Stats Card (system.html)

### Backend Endpoint Needed: GET /api/brain/stats
Returns:
```json
{
  "total_observations": 1847,
  "by_scope": {"global": 235, "stock": 1200, "device": 412},
  "recent_24h": 23,
  "oldest_observation_days": 45,
  "staleness_distribution": {"fresh": 120, "recent": 500, "old": 1227}
}
```
Source: brain_core.py brain_observations table with scope column

### Frontend: Compact card in system.html
- Total with scope breakdown as colored segments
- Fresh/recent/old distribution bar
- Link to brain.html (if re-activated) or just informational

Refresh: every 60s

---

## Enhancement 4: Context Health (system.html)

### Backend Endpoint Needed: GET /api/context-health
Returns:
```json
{
  "current_tokens_estimate": 45000,
  "max_tokens": 180000,
  "active_layer": "idle",
  "compactions_today": 3,
  "layer_stats": {
    "trim": {"fires": 5, "last": "2026-04-03T10:00:00"},
    "compress": {"fires": 2, "last": "2026-04-03T09:30:00"},
    "summarize": {"fires": 1, "last": "2026-04-03T08:00:00"},
    "emergency": {"fires": 0, "last": null}
  }
}
```
Source: context_manager.py internal counters

### Frontend: Compact gauge + layer status
- Token gauge (like CPU/RAM gauges already in system.html)
- Layer status: 4 dots (green=idle, amber=active, red=emergency)
- Compactions today counter

Refresh: every 30s

---

## Enhancement 5: Radar Parallel Progress (radar.html)

### Backend Endpoint Needed: GET /api/radar/progress
Returns:
```json
{
  "status": "running",
  "total_stocks": 128,
  "completed": 89,
  "workers": 5,
  "elapsed_ms": 12300,
  "eta_ms": 2000,
  "last_completed": "THURAYA"
}
```
Source: parallel_coordinator.py + task_manager.py during radar refresh

### Frontend: Progress bar in radar.html header
- Only visible during active refresh
- Shows: completed/total, elapsed time, ETA
- Disappears when refresh complete

Refresh: every 5s (only during refresh)

---

## Enhancement 6: Response Latency (system.html)

### Backend Endpoint Needed: GET /api/latency-stats
Returns:
```json
{
  "avg_total_ms": 1800,
  "avg_intent_ms": 180,
  "avg_memory_ms": 220,
  "avg_llm_ms": 800,
  "prefetch_savings_ms": 400,
  "samples": 47
}
```
Source: memory_prefetch.py timing + intent_state_machine.py durations

### Frontend: Compact latency bar in system.html
- Horizontal stacked bar: intent(green) + memory(blue) + LLM(gold)
- "Prefetch saved ~400ms" note
- Average total response time

Refresh: every 60s

---

## Execution Plan

### Step 1: Claude Code builds 6 endpoints
Give Claude Code: "Read _tools/DASHBOARD_TIER3_ENHANCEMENTS.md — build 6 new GET endpoints in dashboard_api.py. Each endpoint reads from the corresponding Tier 3 module. Return mock data if module not yet integrated."

### Step 2: claude.ai builds frontend
Once endpoints are live, claude.ai updates system.html and radar.html.

### Step 3: Test and iterate

## Files to modify:
- dashboard_api.py (6 new endpoints)
- system.html (5 new sections)
- radar.html (1 progress bar)
