# Add /api/tasks Endpoint — Task Manager Dashboard Integration
# Date: 2026-04-03
# Status: READY FOR CLAUDE CODE
# Context: system.html and home.html already call /api/tasks every 10s/30s
#          Currently returns 404 — needs this endpoint built

---

## Goal
Expose task_manager.py data via `/api/tasks` so the dashboard can show running and recent tasks.

## Frontend Already Done
- system.html: "المهام الجارية" section fetches `/api/tasks` every 10s
- home.html: Health Pulse Bar fetches `/api/tasks` every 30s for task count
- Both handle 404 gracefully (show "غير متاح" / "Tasks: --")

## Required Endpoint

### GET /api/tasks
No auth required (same as /api/service-health, /api/flags, etc.)

### Expected Response Format:
```json
{
  "running": [
    {
      "task_id": "abc123",
      "task_type": "daily_snapshot_refresh",
      "status": "running",
      "progress": "45/128 stocks",
      "duration_ms": 12340,
      "started_at": "2026-04-03T10:00:00Z"
    }
  ],
  "recent": [
    {
      "task_id": "def456",
      "task_type": "news_refresh",
      "status": "completed",
      "result": "fetched 12 articles",
      "duration_ms": 3200,
      "completed_at": "2026-04-03T09:55:00Z"
    },
    {
      "task_id": "ghi789",
      "task_type": "bridge_health_check",
      "status": "failed",
      "error": "connection refused",
      "duration_ms": 5000,
      "completed_at": "2026-04-03T09:50:00Z"
    }
  ],
  "stats": {
    "total_today": 42,
    "completed_today": 40,
    "failed_today": 2
  }
}
```

### Fields:
- `running[]`: Currently executing tasks (status=running or pending)
- `recent[]`: Last 10 completed/failed tasks (most recent first)
- `stats`: Optional summary counts for the day

### Task fields:
- `task_id`: Unique identifier
- `task_type`: String name (e.g. "daily_snapshot_refresh", "news_refresh", "radar_scan")
- `status`: "running" | "pending" | "completed" | "failed"
- `progress`: Optional progress string (free text)
- `duration_ms`: Time elapsed (running) or total time (completed)
- `result`: Optional success message (for completed)
- `error`: Optional error message (for failed)
- `started_at` / `completed_at`: ISO timestamps

## Implementation Notes

### Option A: If task_manager.py already tracks tasks internally
- Just add a FastAPI route in dashboard_api.py or server.py
- Query task_manager for current state
- Return the JSON format above

### Option B: If task_manager.py needs state tracking
- Add a simple in-memory dict of running tasks + a deque of recent tasks (max 20)
- Register/complete/fail tasks as they run
- Background tasks already exist (daily_snapshot, news_refresh, radar, etc.)
- Wrap existing background task calls with register/complete

### Where to add the route:
- Likely in `dashboard_api.py` alongside `/api/service-health` and `/api/flags`
- Or in `server.py` if that's where other `/api/` routes live

### Validation:
1. `curl http://localhost:9000/api/tasks` should return valid JSON
2. `running` array should reflect actual background tasks
3. Dashboard should show tasks instead of "غير متاح"

## After Implementation:
- system.html will auto-show running tasks with pulse animation + recent completed
- home.html will show "Tasks: N running" or "Tasks: idle" in the health bar
- No frontend changes needed
