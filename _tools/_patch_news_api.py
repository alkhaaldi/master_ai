"""Add missing functions to news_engine.py that server.py expects."""

FILE = "/home/pi/master_ai/news_engine.py"
with open(FILE, "a") as f:
    f.write('''

# ═══════════════════════════════════════════════════
# API FUNCTIONS (expected by server.py)
# ═══════════════════════════════════════════════════

last_boursa_refresh = None
last_gemini_refresh = None


def refresh_boursa():
    """Refresh Boursa Kuwait news sources."""
    global last_boursa_refresh
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        items = loop.run_until_complete(fetch_category("boursa"))
        loop.close()
        last_boursa_refresh = datetime.now().isoformat()
        return {"ok": True, "count": len(items)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def refresh_gemini():
    """Refresh Gemini/AI-summarized news."""
    global last_gemini_refresh
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        items = loop.run_until_complete(fetch_category("market"))
        loop.close()
        last_gemini_refresh = datetime.now().isoformat()
        return {"ok": True, "count": len(items)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_news(category=None, sub=None, limit=50, min_priority=1):
    """Get news items for API. Returns list of dicts."""
    try:
        conn = _conn()
        if category:
            rows = conn.execute(
                "SELECT * FROM news_digests WHERE category=? ORDER BY created_at DESC LIMIT ?",
                (category, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM news_digests ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_counts():
    """Get news digest counts by category."""
    try:
        conn = _conn()
        today = date.today().isoformat()
        rows = conn.execute(
            "SELECT category, COUNT(*) as c FROM news_digests "
            "WHERE digest_date=? GROUP BY category", (today,)
        ).fetchall()
        conn.close()
        return {r["category"]: r["c"] for r in rows} if rows else {}
    except Exception:
        return {}


def get_urgent_items():
    """Get urgent/breaking news items (last 24h)."""
    try:
        conn = _conn()
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        rows = conn.execute(
            "SELECT * FROM news_digests WHERE created_at >= ? ORDER BY created_at DESC LIMIT 10",
            (cutoff,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def cleanup_old(days=30):
    """Remove news digests older than N days."""
    try:
        conn = _conn()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cur = conn.execute("DELETE FROM news_digests WHERE created_at < ?", (cutoff,))
        deleted = cur.rowcount
        conn.commit()
        conn.close()
        return {"deleted": deleted}
    except Exception as e:
        return {"error": str(e)}
''')

print("APPENDED 6 missing functions + 2 module vars to news_engine.py")
