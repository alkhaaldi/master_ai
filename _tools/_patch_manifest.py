"""Patch brain_core.py to add observation manifest functions (Tier2 #9)."""
import sys

FILE = "/home/pi/master_ai/brain_core.py"
with open(FILE) as f:
    content = f.read()

# Insert after save_conversation function (find the end of it)
insert_after = "def save_conversation(role: str, content: str, channel: str = \"telegram\"):"
idx = content.find(insert_after)
if idx < 0:
    print("Could not find save_conversation")
    sys.exit(1)

# Find the next function or section after save_conversation
# Look for the next "\ndef " or "\n# " at column 0 after the function
search_start = idx + len(insert_after)
next_def = content.find("\ndef ", search_start)
next_section = content.find("\n# ", search_start)

# Pick the closest one
candidates = [x for x in [next_def, next_section] if x > 0]
if not candidates:
    insert_point = len(content)
else:
    insert_point = min(candidates)

new_code = '''

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OBSERVATION MANIFEST — Lightweight Index (Tier2 #9)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_observation_manifest(category: str = None, max_items: int = 200) -> list:
    """Return lightweight memory headers for LLM ranking.
    Each item: {id, category, type, summary (first 100 chars), age_str, timestamp}.
    Sorted newest-first, capped at max_items."""
    try:
        conn = sqlite3.connect(_AUDIT_DB, timeout=5)
        conn.row_factory = sqlite3.Row
        if category:
            rows = conn.execute(
                "SELECT id, category, type, SUBSTR(content, 1, 100) AS summary, "
                "COALESCE(updated_at, created_at) AS ts "
                "FROM memory WHERE active=1 AND category=? "
                "ORDER BY COALESCE(updated_at, created_at) DESC LIMIT ?",
                (category, max_items)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, category, type, SUBSTR(content, 1, 100) AS summary, "
                "COALESCE(updated_at, created_at) AS ts "
                "FROM memory WHERE active=1 "
                "ORDER BY COALESCE(updated_at, created_at) DESC LIMIT ?",
                (max_items,)
            ).fetchall()
        conn.close()
        return [
            {
                "id": r["id"],
                "category": r["category"],
                "type": r["type"] or "fact",
                "summary": r["summary"],
                "age_str": memory_age(r["ts"]),
                "timestamp": r["ts"],
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("get_observation_manifest error: %s", e)
        return []


def format_observation_manifest(observations: list) -> str:
    """Format observations as text manifest for LLM ranking.
    One line per observation: - [category/type] (age): summary..."""
    lines = []
    for obs in observations:
        line = f"- [{obs['category']}/{obs['type']}] ({obs['age_str']}): {obs['summary']}"
        lines.append(line)
    return chr(10).join(lines)


def get_full_observations(observation_ids: list) -> list:
    """Load full observation text for selected IDs only.
    Called AFTER LLM selects relevant items from the manifest."""
    if not observation_ids:
        return []
    try:
        conn = sqlite3.connect(_AUDIT_DB, timeout=5)
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(observation_ids))
        rows = conn.execute(
            f"SELECT id, category, type, content, context, confidence, "
            f"COALESCE(updated_at, created_at) AS ts "
            f"FROM memory WHERE id IN ({placeholders})",
            observation_ids,
        ).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            d["staleness_warning"] = memory_freshness_warning(r["ts"])
            result.append(d)
        return result
    except Exception as e:
        logger.warning("get_full_observations error: %s", e)
        return []

'''

content = content[:insert_point] + new_code + content[insert_point:]

with open(FILE, "w") as f:
    f.write(content)

print(f"PATCHED OK — inserted at position {insert_point}")
