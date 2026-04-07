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

# Ensure project root is on path
PROJECT_ROOT = os.path.expanduser("~/master_ai")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

BASE = "http://localhost:9000"
DB_PATH = os.path.expanduser("~/master_ai/data/life.db")
AUDIT_DB = os.path.expanduser("~/master_ai/data/audit.db")
RESULTS = []

def check(name, ok, detail=""):
    status = "\u2705" if ok else "\u274c"
    RESULTS.append({"name": name, "ok": ok, "detail": detail})
    print(f"  {status} {name}: {detail}")

def api_get(path):
    try:
        r = urllib.request.urlopen(f"{BASE}{path}", timeout=10)
        return json.loads(r.read()), r.status
    except Exception as e:
        return None, str(e)

print("=" * 60)
print("MASTER AI \u2014 FULL INTEGRATION AUDIT")
print("=" * 60)

# === SECTION 1: Module Imports (14 new modules) ===
print("\n\U0001f4e6 Section 1: Module Imports")
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

# === SECTION 2: Integration Wiring (is module actually USED?) ===
print("\n\U0001f50c Section 2: Integration Wiring")

# Check stock_radar imports
try:
    src = open(os.path.expanduser("~/master_ai/stock_radar.py")).read()
    check("stock_radar \u2190 coalesced_executor",
          "coalesced_executor" in src or "CoalescedExecutor" in src,
          "found" if "coalesced_executor" in src else "NOT FOUND")
    check("stock_radar \u2190 processing_cursor",
          "processing_cursor" in src or "ProcessingCursor" in src,
          "found" if "processing_cursor" in src else "NOT FOUND")
except Exception as e:
    check("stock_radar wiring", False, str(e)[:80])

# Check tg_intent_router imports
try:
    src = open(os.path.expanduser("~/master_ai/tg_intent_router.py")).read()
    check("tg_intent_router \u2190 intent_state_machine",
          "intent_state_machine" in src or "IntentContext" in src,
          "found" if "IntentContext" in src or "intent_state_machine" in src else "NOT FOUND")
except Exception as e:
    check("tg_intent_router wiring", False, str(e)[:80])

# Check chat_v7 imports
try:
    src = open(os.path.expanduser("~/master_ai/chat_v7.py")).read()
    check("chat_v7 \u2190 context_manager",
          "context_manager" in src or "manage_context" in src,
          "found" if "context_manager" in src or "manage_context" in src else "NOT FOUND")
except Exception as e:
    check("chat_v7 wiring", False, str(e)[:80])

# Check server.py imports
try:
    src = open(os.path.expanduser("~/master_ai/server.py")).read()
    check("server.py \u2190 auto_memory_extractor",
          "auto_memory_extractor" in src or "AutoMemoryExtractor" in src,
          "found" if "auto_memory_extractor" in src or "AutoMemoryExtractor" in src else "NOT FOUND")
    check("server.py \u2190 session_memory",
          "session_memory" in src or "SessionTracker" in src,
          "found" if "session_memory" in src or "SessionTracker" in src else "NOT FOUND")
    check("server.py \u2190 task_manager",
          "task_manager" in src or "TaskManager" in src,
          "found" if "task_manager" in src or "TaskManager" in src else "NOT FOUND")
    check("server.py tg_send 400 fallback",
          "fallback" in src.lower() or ("strip" in src.lower() and "plain" in src.lower()),
          "found fallback logic")
except Exception as e:
    check("server.py wiring", False, str(e)[:80])

# Check news_engine imports
try:
    src = open(os.path.expanduser("~/master_ai/news_engine.py")).read()
    check("news_engine \u2190 circuit_breaker",
          "circuit_breaker" in src or "CircuitBreaker" in src,
          "found" if "circuit_breaker" in src else "NOT FOUND")
    check("news_engine \u2190 processing_cursor",
          "processing_cursor" in src or "ProcessingCursor" in src,
          "found" if "processing_cursor" in src or "ProcessingCursor" in src else "NOT FOUND")
except Exception as e:
    check("news_engine wiring", False, str(e)[:80])

# Check brain_core staleness + manifest
try:
    src = open(os.path.expanduser("~/master_ai/brain_core.py")).read()
    check("brain_core: memory_age()",
          "def memory_age(" in src, "found" if "def memory_age(" in src else "MISSING")
    check("brain_core: memory_freshness_warning()",
          "def memory_freshness_warning(" in src, "found" if "def memory_freshness_warning(" in src else "MISSING")
    check("brain_core: get_observation_manifest()",
          "def get_observation_manifest(" in src, "found" if "def get_observation_manifest(" in src else "MISSING")
    check("brain_core: get_full_observations()",
          "def get_full_observations(" in src, "found" if "def get_full_observations(" in src else "MISSING")
except Exception as e:
    check("brain_core functions", False, str(e)[:80])

# === SECTION 3: API Endpoints ===
print("\n\U0001f310 Section 3: API Endpoints")
endpoints = [
    ("/health", "Server Health"),
    ("/api/service-health", "Service Health"),
    ("/api/tasks", "Live Tasks"),
    ("/api/memory-extraction/stats", "Memory Extraction"),
    ("/api/intent-analytics", "Intent Analytics"),
    ("/api/brain/stats", "Brain Stats"),
    ("/api/context-health", "Context Health"),
    ("/api/latency-stats", "Latency Stats"),
    ("/api/radar/progress", "Radar Progress"),
    ("/api/kairos/status", "KAIROS"),
    ("/api/flags", "Feature Flags"),
    ("/api/skills", "Skills"),
    ("/api/news", "News"),
    ("/api/analyze?symbol=TEST", "Gemini Analyze"),
]
for path, name in endpoints:
    data, status = api_get(path)
    ok = status == 200
    detail = f"status={status}"
    if ok and isinstance(data, dict):
        if "error" in data and data["error"] and "not loaded" in str(data.get("error","")):
            ok = False
            detail += f" error={data['error'][:60]}"
    check(f"GET {path} ({name})", ok, detail)

# === SECTION 4: Database Tables ===
print("\n\U0001f4be Section 4: Database Tables")

# audit.db tables
try:
    conn = sqlite3.connect(AUDIT_DB)
    existing = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for t in ["memory", "conversations", "intent_audit", "session_summaries", "processing_cursors"]:
        check(f"audit.db: {t}", t in existing, "exists" if t in existing else "MISSING")

    # Check memory table has scope column
    cols = [r[1] for r in conn.execute("PRAGMA table_info(memory)").fetchall()]
    check("memory.scope column", "scope" in cols, "found" if "scope" in cols else "MISSING")

    # Row counts
    for t in ["memory", "intent_audit", "session_summaries"]:
        if t in existing:
            cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            check(f"{t} rows", True, str(cnt))
    conn.close()
except Exception as e:
    check("audit.db access", False, str(e)[:80])

# life.db tables
try:
    conn = sqlite3.connect(DB_PATH)
    existing = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for t in ["news_digests", "feature_flags", "stock_radar_watchlist"]:
        check(f"life.db: {t}", t in existing, "exists" if t in existing else "MISSING")
    conn.close()
except Exception as e:
    check("life.db access", False, str(e)[:80])

# === SECTION 5: Skills Directory ===
print("\n\U0001f4dd Section 5: Skills")
skills_dir = os.path.expanduser("~/master_ai/skills")
if os.path.isdir(skills_dir):
    skills = [f for f in os.listdir(skills_dir) if f.endswith('.md')]
    check("skills/ directory", True, f"{len(skills)} skills: {skills}")
    # Test skill loading
    try:
        from skill_loader import SkillLoader
        loader = SkillLoader()
        loaded = loader.load_all()
        check("SkillLoader.load_all()", loaded > 0, f"{loaded} skills loaded")
    except Exception as e:
        check("SkillLoader", False, str(e)[:80])
else:
    check("skills/ directory", False, "MISSING")

# === SECTION 6: Dashboard HTML ===
print("\n\U0001f4ca Section 6: Dashboard HTML")
html_dir = os.path.expanduser("~/master_ai/www/trading")
expected_html = ["system.html", "home.html", "radar.html", "positions.html",
                 "journal.html", "news.html", "analysis.html"]
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

# === SUMMARY ===
print("\n" + "=" * 60)
total = len(RESULTS)
passed = sum(1 for r in RESULTS if r["ok"])
failed = sum(1 for r in RESULTS if not r["ok"])
print(f"TOTAL: {total} checks | \u2705 {passed} passed | \u274c {failed} failed")
pct = round(passed / total * 100) if total > 0 else 0
print(f"SCORE: {pct}%")
if failed > 0:
    print(f"\nFAILED CHECKS ({failed}):")
    for r in RESULTS:
        if not r["ok"]:
            print(f"  \u274c {r['name']}: {r['detail']}")
print("=" * 60)
