"""
cost_tracker.py — Per-request cost tracking for Master AI
Phase 2 Week 1: tracks input/output tokens + calculates USD cost

DB: data/traces.db (shared WAL DB), table: cost_log
Pricing: Anthropic API (as of 2025-05)
"""

import sqlite3
import logging
import time
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("cost_tracker")

DB_PATH = Path("data/traces.db")

# ═══ PRICING (USD per 1M tokens) ═══
PRICING = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-opus-4-6":   {"input": 5.0, "output": 25.0},
    # OpenAI fallback
    "gpt-4o":                   {"input": 2.5, "output": 10.0},
}

# Fallback for unknown models
DEFAULT_PRICING = {"input": 3.0, "output": 15.0}


def _init_cost_db():
    """Create cost_log table if not exists."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS cost_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model TEXT NOT NULL,
        input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        cache_read_tokens INTEGER DEFAULT 0,
        cache_creation_tokens INTEGER DEFAULT 0,
        cost_usd REAL DEFAULT 0.0,
        user_id TEXT DEFAULT 'default',
        source TEXT DEFAULT 'chat_v7',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_cost_created 
                    ON cost_log(created_at)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_cost_model 
                    ON cost_log(model)""")
    conn.commit()
    conn.close()


def track_cost(usage, model, user_id="default", source="chat_v7"):
    """
    Track token usage and cost from an Anthropic/OpenAI response.
    
    Args:
        usage: resp.usage object (has input_tokens, output_tokens)
        model: model name string
        user_id: who made the request
        source: which path (chat_v7, stream, etc.)
    """
    try:
        if not usage:
            return
        
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        
        # Anthropic may include cache tokens
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        
        # Calculate cost
        prices = PRICING.get(model, DEFAULT_PRICING)
        cost = (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000
        
        _init_cost_db()
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.execute(
            """INSERT INTO cost_log 
               (model, input_tokens, output_tokens, cache_read_tokens, 
                cache_creation_tokens, cost_usd, user_id, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (model or "unknown", input_tokens, output_tokens, 
             cache_read, cache_creation, round(cost, 6), user_id, source)
        )
        conn.commit()
        conn.close()
        
        logger.info(f"Cost: {input_tokens}in/{output_tokens}out = ${cost:.4f} ({model})")
        
    except Exception as e:
        logger.warning(f"Cost tracking error: {e}")


def track_cost_openai(usage_dict, model="gpt-4o", user_id="default"):
    """Track cost from OpenAI response (dict-based usage)."""
    try:
        if not usage_dict:
            return
        input_tokens = usage_dict.get("prompt_tokens", 0)
        output_tokens = usage_dict.get("completion_tokens", 0)
        
        prices = PRICING.get(model, DEFAULT_PRICING)
        cost = (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000
        
        _init_cost_db()
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.execute(
            """INSERT INTO cost_log 
               (model, input_tokens, output_tokens, cost_usd, user_id, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (model, input_tokens, output_tokens, round(cost, 6), user_id, "openai_fallback")
        )
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.warning(f"OpenAI cost tracking error: {e}")


def get_cost_summary():
    """Get comprehensive cost summary for /cost endpoint."""
    try:
        _init_cost_db()
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.row_factory = sqlite3.Row
        
        result = {}
        
        # Total all-time
        row = conn.execute(
            """SELECT COUNT(*) as requests, 
                      SUM(input_tokens) as total_input,
                      SUM(output_tokens) as total_output,
                      SUM(cost_usd) as total_cost,
                      AVG(input_tokens) as avg_input,
                      AVG(output_tokens) as avg_output,
                      AVG(cost_usd) as avg_cost
               FROM cost_log"""
        ).fetchone()
        result["all_time"] = {
            "requests": row["requests"] or 0,
            "total_input_tokens": row["total_input"] or 0,
            "total_output_tokens": row["total_output"] or 0,
            "total_cost_usd": round(row["total_cost"] or 0, 4),
            "avg_input_tokens": round(row["avg_input"] or 0, 1),
            "avg_output_tokens": round(row["avg_output"] or 0, 1),
            "avg_cost_per_request": round(row["avg_cost"] or 0, 6),
        }
        
        # Today
        row = conn.execute(
            """SELECT COUNT(*) as requests,
                      SUM(input_tokens) as total_input,
                      SUM(output_tokens) as total_output,
                      SUM(cost_usd) as total_cost
               FROM cost_log
               WHERE date(created_at) = date('now')"""
        ).fetchone()
        result["today"] = {
            "requests": row["requests"] or 0,
            "input_tokens": row["total_input"] or 0,
            "output_tokens": row["total_output"] or 0,
            "cost_usd": round(row["total_cost"] or 0, 4),
        }
        
        # This month
        row = conn.execute(
            """SELECT COUNT(*) as requests,
                      SUM(input_tokens) as total_input,
                      SUM(output_tokens) as total_output,
                      SUM(cost_usd) as total_cost
               FROM cost_log
               WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')"""
        ).fetchone()
        result["this_month"] = {
            "requests": row["requests"] or 0,
            "input_tokens": row["total_input"] or 0,
            "output_tokens": row["total_output"] or 0,
            "cost_usd": round(row["total_cost"] or 0, 4),
            "budget_usd": 300.0,
            "remaining_usd": round(300.0 - (row["total_cost"] or 0), 2),
            "usage_pct": round((row["total_cost"] or 0) / 300.0 * 100, 1),
        }
        
        # By model
        rows = conn.execute(
            """SELECT model, COUNT(*) as requests,
                      SUM(input_tokens) as total_input,
                      SUM(output_tokens) as total_output,
                      SUM(cost_usd) as total_cost
               FROM cost_log
               GROUP BY model
               ORDER BY total_cost DESC"""
        ).fetchall()
        result["by_model"] = {
            r["model"]: {
                "requests": r["requests"],
                "input_tokens": r["total_input"] or 0,
                "output_tokens": r["total_output"] or 0,
                "cost_usd": round(r["total_cost"] or 0, 4),
            } for r in rows
        }
        
        # Daily breakdown (last 7 days)
        rows = conn.execute(
            """SELECT date(created_at) as day,
                      COUNT(*) as requests,
                      SUM(cost_usd) as cost
               FROM cost_log
               WHERE created_at >= datetime('now', '-7 days')
               GROUP BY date(created_at)
               ORDER BY day DESC"""
        ).fetchall()
        result["daily_last_7"] = [
            {"date": r["day"], "requests": r["requests"], "cost_usd": round(r["cost"] or 0, 4)}
            for r in rows
        ]
        
        # Top 5 most expensive requests today
        rows = conn.execute(
            """SELECT model, input_tokens, output_tokens, cost_usd, 
                      user_id, source, created_at
               FROM cost_log
               WHERE date(created_at) = date('now')
               ORDER BY cost_usd DESC
               LIMIT 5"""
        ).fetchall()
        result["top_expensive_today"] = [dict(r) for r in rows]
        
        conn.close()
        
        # Add pricing reference
        result["pricing_ref"] = {k: v for k, v in PRICING.items()}
        
        return result
        
    except Exception as e:
        logger.error(f"Cost summary error: {e}")
        return {"error": str(e)}


def get_cost_for_kpi():
    """Lightweight cost info for /kpi endpoint."""
    try:
        _init_cost_db()
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        
        today = conn.execute(
            "SELECT SUM(cost_usd) FROM cost_log WHERE date(created_at) = date('now')"
        ).fetchone()[0] or 0
        
        month = conn.execute(
            "SELECT SUM(cost_usd) FROM cost_log WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')"
        ).fetchone()[0] or 0
        
        avg = conn.execute(
            "SELECT AVG(cost_usd) FROM cost_log"
        ).fetchone()[0] or 0
        
        conn.close()
        
        return {
            "today_usd": round(today, 4),
            "month_usd": round(month, 4),
            "month_budget_usd": 300.0,
            "month_pct": round(month / 300.0 * 100, 1),
            "avg_per_request_usd": round(avg, 6),
        }
        
    except Exception:
        return {"today_usd": 0, "month_usd": 0, "month_budget_usd": 300.0, "month_pct": 0, "avg_per_request_usd": 0}

def cleanup_old_data(days=30):
    """Delete traces and cost_log older than N days."""
    import sqlite3
    deleted = {}
    try:
        conn = sqlite3.connect('/home/pi/master_ai/data/traces.db', timeout=5)
        d1 = conn.execute(f"DELETE FROM traces WHERE created_at < datetime('now', '-{days} days')").rowcount
        d2 = conn.execute(f"DELETE FROM cost_log WHERE created_at < datetime('now', '-{days} days')").rowcount
        conn.commit()
        conn.close()
        deleted = {"traces": d1, "cost_log": d2}
    except Exception as e:
        deleted = {"error": str(e)}
    
    try:
        conn2 = sqlite3.connect('/home/pi/master_ai/data/home_brain.db', timeout=5)
        d3 = conn2.execute(f"DELETE FROM state_changes WHERE ts < datetime('now', '-{days} days', 'localtime')").rowcount
        d4 = conn2.execute(f"DELETE FROM climate_log WHERE ts < datetime('now', '-{days} days', 'localtime')").rowcount
        conn2.commit()
        conn2.close()
        deleted["state_changes"] = d3
        deleted["climate_log"] = d4
    except Exception as e:
        deleted["brain_error"] = str(e)
    
    return deleted
