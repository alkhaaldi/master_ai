#!/usr/bin/env python3
"""Phase 4: Fix /dashboard/extended cost tracking — use real cost_tracker instead of duration estimate."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patch

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

OLD = '''    # ── Cost ──
    try:
        conn = sqlite3.connect("data/audit.db", timeout=3)
        today_str = str(_d.today())
        # Estimate cost from audit_log duration (approx $0.003/1000ms for Sonnet)
        row = conn.execute("SELECT COALESCE(SUM(duration_ms),0) FROM audit_log WHERE timestamp LIKE ?", (today_str+"%",)).fetchone()
        data["cost_today_usd"] = round((row[0] or 0) * 0.000003, 4)
        row2 = conn.execute("SELECT COALESCE(SUM(duration_ms),0) FROM audit_log").fetchone()
        data["cost_total_usd"] = round((row2[0] or 0) * 0.000003, 2)
        conn.close()
    except Exception:
        data["cost_today_usd"] = 0; data["cost_total_usd"] = 0'''

NEW = '''    # ── Cost (real token tracking from cost_tracker.py) ──
    try:
        from cost_tracker import get_cost_for_kpi
        _ck = get_cost_for_kpi()
        data["cost_today_usd"] = _ck.get("today_usd", 0)
        data["cost_total_usd"] = _ck.get("total_usd", 0)
        data["avg_cost_per_request"] = _ck.get("avg_per_request_usd", 0)
    except Exception:
        data["cost_today_usd"] = 0; data["cost_total_usd"] = 0; data["avg_cost_per_request"] = 0'''

result = apply_patch(FILE, OLD, NEW, backup=True)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
