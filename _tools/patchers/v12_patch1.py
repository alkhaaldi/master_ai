#!/usr/bin/env python3
"""V12 Patch 1: Add _parse_news_items() and wire into /dashboard/extended."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patches

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

PATCH1_OLD = '''@app.get("/dashboard/extended")
async def ha_dashboard_extended():
    """Extended data for HA subviews: radar details, tasks list, events, system health."""'''

PATCH1_NEW = '''def _parse_news_items(digest: dict) -> list:
    """Parse news category text blobs into structured items array."""
    items = []
    categories = [
        ("urgent", "عاجل", "🔥", 1),
        ("economic", "اقتصاد", "💰", 2),
        ("local", "محلي", "🇰🇼", 3),
        ("tech", "تقنية", "💻", 4),
        ("ai", "ذكاء اصطناعي", "🤖", 5),
        ("gadgets", "أجهزة", "📱", 6),
    ]
    for key, ar, emoji, pri in categories:
        text = digest.get(key, "") or ""
        for line in text.strip().split("\\n"):
            line = line.strip()
            if not line:
                continue
            clean = line
            for ch in ["🔥", "💰", "🇰🇼", "💻", "🤖", "📱", "⚡", "🛡"]:
                clean = clean.lstrip(ch)
            clean = clean.strip(" \\u200f\\u200e")
            if not clean:
                continue
            source = ""
            if clean.endswith(")") and "(" in clean:
                idx = clean.rfind("(")
                source = clean[idx+1:-1].strip()
                clean = clean[:idx].strip()
            items.append({
                "category": key,
                "category_ar": ar,
                "emoji": emoji,
                "text": clean,
                "source": source,
                "priority": pri,
            })
    return items


@app.get("/dashboard/extended")
async def ha_dashboard_extended():
    """Extended data for HA subviews: radar details, tasks list, events, system health."""'''

# Patch 2: Wire _parse_news_items into news_digest
PATCH2_OLD = '''            data["news_available"] = True
        else:
            data["news_digest"] = {}'''

PATCH2_NEW = '''            data["news_available"] = True
            data["news_digest"]["news_items"] = _parse_news_items(data["news_digest"])
        else:
            data["news_digest"] = {}'''

result = apply_patches(FILE, [(PATCH1_OLD, PATCH1_NEW), (PATCH2_OLD, PATCH2_NEW)], backup=True)
print(result)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
