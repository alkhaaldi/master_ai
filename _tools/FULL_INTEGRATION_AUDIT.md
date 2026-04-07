# Full Integration Audit — Verify All 21 Patterns Are Live
# Date: 2026-04-03
# For: Claude Code (RPi) — run this audit and report results

---

## Task
Run a comprehensive check on ALL 21 Claude Code patterns + 7 integrations.
For each: verify import works, verify it's actually CALLED in the live system,
verify the dashboard endpoint returns data. Generate a full report.

## Run this Python script on the RPi:

```python
#!/usr/bin/env python3
"""
Master AI — Full Integration Audit
Tests all 21 patterns, 7 integrations, 7 dashboard endpoints.
"""
import importlib
import json
import sqlite3
import os
import sys
import urllib.request
import time

BASE = "http://localhost:9000"
DB_PATH = os.path.expanduser("~/master_ai/data/life.db")
RESULTS = []

def check(name, ok, detail=""):
    status = "✅" if ok else "❌"
    RESULTS.append({"name": name, "ok": ok, "detail": detail})
    print(f"  {status} {name}: {detail}")

def api_get(path):
    try:
        r = urllib.request.urlopen(f"{BASE}{path}", timeout=10)
        return json.loads(r.read()), r.status
    except Exception as e:
        return None, str(e)

print("=" * 60)
print("MASTER AI — FULL INTEGRATION AUDIT")
print("=" * 60)

# ═══ SECTION 1: Module Imports (15 new modules) ═══
print("\n📦 Section 1: Module Imports")
modules = [
    "circuit_breaker", "processing_cursor", "tool_registry",
    "task_manager", "memory_recall", "master_ai_tool",
    "coalesced_executor", "session_memory", "memory_prefetch",
    "auto_memory_extractor", "parallel_coordinator", "context_manager",
    "intent_state_machine", "skill_loader",
]
for mod in modules:
    try:
        importlib.import_module(mod)
        check(f"import {mod}", True, "loaded")
    except Exception as e:
        check(f"import {mod}", False, str(e)[:80])

# ═══ SECTION 2: Integration Wiring (is module actually USED?) ═══
print("\n🔌 Section 2: Integration Wiring")

# Check stock_radar imports coalesced_executor
try:
    src = open(os.path.expanduser("~/master_ai/stock_radar.py")).read()
    check("stock_radar ← coalesced_executor",
          "coalesced_executor" in src or "CoalescedExecutor" in src,
          "found" if "coalesced_executor" in src else "NOT FOUND")
    check("stock_radar ← processing_cursor",
          "processing_cursor" in src or "ProcessingCursor" in src,
          "found" if "processing_cursor" in src else "NOT FOUND")
except Exception as e:
    check("stock_radar wiring", False, str(e)[:80])

# Check tg_intent_router imports
try:
    src = open(os.path.expanduser("~/master_ai/tg_intent_router.py")).read()
    check("tg_intent_router ← intent_state_machine",
          "intent_state_machine" in src or "IntentContext" in src,
          "found" if "IntentContext" in src or "intent_state_machine" in src else "NOT FOUND")
    check("tg_intent_router ← memory_prefetch",
          "memory_prefetch" in src or "MemoryPrefetcher" in src,
          "found" if "memory_prefetch" in src or "MemoryPrefetcher" in src else "NOT FOUND")
    check("tg_intent_router ← master_ai_tool",
          "master_ai_tool" in src or "TOOL_DEFS" in src,
          "found" if "master_ai_tool" in src or "TOOL_DEFS" in src else "NOT FOUND")
except Exception as e:
    check("tg_intent_router wiring", False, str(e)[:80])

# Check chat_v7 imports
try:
    src = open(os.path.expanduser("~/master_ai/chat_v7.py")).read()
    check("chat_v7 ← context_manager",
          "context_manager" in src or "manage_context" in src,
          "found" if "context_manager" in src or "manage_context" in src else "NOT FOUND")
    check("chat_v7 ← memory_recall",
          "memory_recall" in src or "find_relevant_memories" in src,
          "found" if "memory_recall" in src or "find_relevant_memories" in src else "NOT FOUND")
except Exception as e:
    check("chat_v7 wiring", False, str(e)[:80])

# Check server.py imports
try:
    src = open(os.path.expanduser("~/master_ai/server.py")).read()
    check("server.py ← auto_memory_extractor",
          "auto_memory_extractor" in src or "AutoMemoryExtractor" in src,
          "found" if "auto_memory_extractor" in src or "AutoMemoryExtractor" in src else "NOT FOUND")
    check("server.py ← session_memory",
          "session_memory" in src or "SessionTracker" in src,
          "found" if "session_memory" in src or "SessionTracker" in src else "NOT FOUND")
    check("server.py ← task_manager",
          "task_manager" in src or "TaskManager" in src,
          "found" if "task_manager" in src or "TaskManager" in src else "NOT FOUND")
except Exception as e:
    check("server.py wiring", False, str(e)[:80])

# Check news_engine imports
try:
    src = open(os.path.expanduser("~/master_ai/news_engine.py")).read()
    check("news_engine ← circuit_breaker",
          "circuit_breaker" in src or "CircuitBreaker" in src,
          "found" if "circuit_breaker" in src else "NOT FOUND")
    check("news_engine ← processing_cursor",
          "processing_cursor" in src or "ProcessingCursor" in src,
          "found" if "processing_cursor" in src or "ProcessingCursor" in src else "NOT FOUND")
except Exception as e:
    check("news_engine wiring", False, str(e)[:80])

# ═══ SECTION 3: API Endpoints ═══
print("\n🌐 Section 3: API Endpoints")
endpoints = [
    ("/health", "Server Health"),
    ("/api/service-health", "Service Health"),
    ("/api/tasks", "Live Tasks"),
    ("/api/memory-extraction/stats", "Memory Extraction"),
    ("/api/intent-analytics", "Intent Analytics"),
    ("/api/brain/stats", "Brain Stats"),
    ("/api/context-health", "Context Health"),
    ("/api/latency-stats", "Latency Stats"),
    ("/api/kairos/status", "KAIROS"),
    ("/api/flags", "Feature Flags"),
    ("/api/skills", "Skills"),
    ("/api/news", "News"),
]
for path, name in endpoints:
    data, status = api_get(path)
    check(f"GET {path}", status == 200, f"status={status}")

# ═══ SECTION 4: Database Tables ═══
print("\n💾 Section 4: Database Tables")
expected_tables = ["intent_audit", "session_summaries", "brain_observations", "news_items", "feature_flags"]
try:
    conn = sqlite3.connect(DB_PATH)
    existing = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for t in expected_tables:
        check(f"table: {t}", t in existing, "exists" if t in existing else "MISSING")
    # Check brain_observations has scope column
    cols = [r[1] for r in conn.execute("PRAGMA table_info(brain_observations)").fetchall()]
    check("brain_observations.scope column", "scope" in cols, "found" if "scope" in cols else "MISSING")
    # Row counts
    for t in ["intent_audit", "brain_observations"]:
        if t in existing:
            cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            check(f"{t} rows", True, str(cnt))
    conn.close()
except Exception as e:
    check("DB access", False, str(e)[:80])

# ═══ SECTION 5: Skills Directory ═══
print("\n📝 Section 5: Skills")
skills_dir = os.path.expanduser("~/master_ai/skills")
if os.path.isdir(skills_dir):
    skills = [f for f in os.listdir(skills_dir) if f.endswith('.md')]
    check("skills/ directory", True, f"{len(skills)} skills: {skills}")
else:
    check("skills/ directory", False, "MISSING")

# ═══ SECTION 6: Dashboard HTML ═══
print("\n📊 Section 6: Dashboard HTML")
html_dir = os.path.expanduser("~/master_ai/www/trading")
expected_html = ["system.html", "home.html", "radar.html", "positions.html",
                 "journal.html", "news.html", "analysis.html", "email.html", "home-control.html"]
for f in expected_html:
    path = os.path.join(html_dir, f)
    exists = os.path.isfile(path)
    size = os.path.getsize(path) if exists else 0
    check(f"html: {f}", exists, f"{size} bytes" if exists else "MISSING")

# Check system.html has Tier3 sections
try:
    sys_html = open(os.path.join(html_dir, "system.html")).read()
    tier3_ids = ["learning-panel", "intent-panel", "brain-panel", "context-panel", "latency-panel"]
    for tid in tier3_ids:
        check(f"system.html #{tid}", tid in sys_html, "found" if tid in sys_html else "MISSING")
except:
    check("system.html Tier3 sections", False, "cannot read")

# ═══ SECTION 7: Telegram Integration ═══
print("\n📨 Section 7: Telegram")
try:
    src = open(os.path.expanduser("~/master_ai/server.py")).read()
    check("tg_send_safe (400 fix)", "tg_send" in src and ("fallback" in src.lower() or "strip" in src.lower() or "plain" in src.lower()), "found fallback logic")
except:
    check("tg_send_safe", False, "cannot read server.py")

# ═══ SUMMARY ═══
print("\n" + "=" * 60)
total = len(RESULTS)
passed = sum(1 for r in RESULTS if r["ok"])
failed = sum(1 for r in RESULTS if not r["ok"])
print(f"TOTAL: {total} checks | ✅ {passed} passed | ❌ {failed} failed")
if failed > 0:
    print("\nFAILED CHECKS:")
    for r in RESULTS:
        if not r["ok"]:
            print(f"  ❌ {r['name']}: {r['detail']}")
print("=" * 60)
```

## How to run:
```bash
cd ~/master_ai
python3 /path/to/audit_script.py
```

Or save as `_tools/full_audit.py` and run:
```bash
cd ~/master_ai
python3 _tools/full_audit.py
```

## Report back the full output.
