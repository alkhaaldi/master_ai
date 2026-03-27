# Bridge Integration Task — Claude Code Instructions

## READ FIRST
1. Read `_tools/BRIDGE_INTEGRATION_PLAN.md` — this is the full plan with code
2. Read `CLAUDE.md` (existing) for project conventions
3. Read `_tools/OPERATIONAL_ACCESS_MATRIX.md` for edit rules

## TASK: Integrate TradingView Bridge API with Master AI

### What is Bridge API?
- FastAPI service running on Windows PC at http://192.168.111.156:8059
- Provides live KSE stock technical analysis (RSI, MACD, EMA, S/R)
- Bridge COMPLEMENTS the existing radar (tv_data.py), does NOT replace it

### What to build (in order):

#### Step 1: Install httpx
```bash
pip install httpx --break-system-packages
```

#### Step 2: Create bridge_client.py
- New file in project root (next to server.py)
- Full code is in BRIDGE_INTEGRATION_PLAN.md
- Use apply_text_patch.py? NO — this is a NEW file, just create it directly
- Key class: BridgeClient with health/quote/analysis/multi_analysis
- In-memory TTL cache + stale fallback + circuit breaker

#### Step 3: Add endpoints to dashboard_api.py
- `/dashboard/bridge` — multi-symbol compact analysis
- `/dashboard/bridge/{symbol}` — single symbol detail
- Use apply_text_patch.py for this edit
- Add imports at top, endpoints at bottom
- The _get_bridge_candidates() function selects symbols from portfolio+watchlist+top radar

#### Step 4: Wire into server.py lifespan
- Add `from bridge_client import init_bridge_client` 
- Call `await init_bridge_client()` in lifespan startup
- Use apply_text_patch.py for this edit

#### Step 5: Validate
```bash
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
```

#### Step 6: Test
```bash
curl -s -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000/dashboard/bridge
curl -s -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000/dashboard/bridge/CLEANING
```

#### Step 7: Git commit
```bash
git add bridge_client.py
git add -u
git commit -m "feat: Bridge API client + /dashboard/bridge endpoints"
```

#### Step 8: Restart
```bash
bash _tools/restart_master_ai.sh
```

### IMPORTANT RULES
- Bridge PC IP: 192.168.111.156:8059 (on same /22 subnet as RPi)
- No API key needed for Bridge (internal LAN)
- httpx timeout: connect=1.5s, read=5.0s
- Circuit breaker: 3 failures → 60s cooldown
- Cache: quote 30s, analysis 120s
- Normalize 75KB raw response to ~1-2KB compact object
- If bridge offline → serve stale cache → never fail hard
- Max 15 symbols per bridge call
- Follow existing code patterns (see dashboard_api.py for reference)

### DO NOT
- Do not modify tv_data.py or stock_radar.py websocket logic
- Do not add Bridge data to HA sensors yet (Phase 4, later)
- Do not remove or change existing /dashboard/radar endpoint
- Do not use pandas or heavy libraries
