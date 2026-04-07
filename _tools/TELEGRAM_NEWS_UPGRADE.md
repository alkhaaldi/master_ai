# Telegram News Upgrade — Use news_engine.py data
# Claude Code: Execute this plan on RPi

## Problem
Current `/news` command calls `handle_news_latest()` which returns 8 items flat.
We want structured, categorized, priority-sorted news from news_engine.

## Solution
Replace the Telegram news handling with a proper function that:
1. Pulls from news_engine.get_news() (same DB as dashboard)
2. Groups by section with Arabic headers and emoji
3. Shows priority badges (🔴 عاجل for P5, 🟡 for P4)
4. Supports sub-commands: `/أخبار` (all), `/أخبار بورصة`, `/أخبار اقتصاد`, etc.

---

## Step 1: Add new function to `news_engine.py`

Add `format_news_telegram(category=None, sub_category=None, limit=30)`:

```python
def format_news_telegram(category=None, sub_category=None, limit=30):
    """Format news for Telegram — grouped by section, priority-sorted."""
    items = get_news(category=category, sub_category=sub_category, limit=limit, min_priority=1)
    if not items:
        return "📰 لا أخبار حالياً"

    # Priority badges
    def badge(pri):
        if pri >= 5: return "🔴"
        if pri >= 4: return "🟡"
        if pri >= 3: return "▪️"
        return "▫️"

    # If showing all categories, group them
    if not category:
        sections = {
            "boursa":  {"emoji": "🏦", "label": "بورصة الكويت", "items": []},
            "economy": {"emoji": "📈", "label": "اقتصاد",       "items": []},
            "world":   {"emoji": "🌍", "label": "عالمي",        "items": []},
            "tech":    {"emoji": "🤖", "label": "تكنولوجيا",    "items": []},
        }
        for it in items:
            cat = it.get("category", "other")
            if cat in sections:
                sections[cat]["items"].append(it)

        lines = ["📰 *آخر الأخبار*\n"]
        for key, sec in sections.items():
            if not sec["items"]:
                continue
            lines.append(f"\n{sec['emoji']} *{sec['label']}*")
            for it in sec["items"][:8]:  # max 8 per section
                b = badge(it.get("priority", 3))
                headline = it.get("headline", "")
                # Truncate long headlines
                if len(headline) > 80:
                    headline = headline[:77] + "..."
                company = it.get("company")
                tag = f" [{company}]" if company else ""
                lines.append(f"{b} {headline}{tag}")

        # Stats footer
        total = len(items)
        urgent = len([i for i in items if i.get("priority", 0) >= 5])
        lines.append(f"\n📊 {total} خبر")
        if urgent:
            lines.append(f"🔴 {urgent} عاجل")
        return "\n".join(lines)

    else:
        # Single category view
        CAT_LABELS = {"boursa": "🏦 بورصة الكويت", "economy": "📈 اقتصاد", "world": "🌍 عالمي", "tech": "🤖 تكنولوجيا"}
        label = CAT_LABELS.get(category, category)
        lines = [f"📰 *{label}*\n"]

        if category == "boursa" and not sub_category:
            # Group by sub_category
            SUB_LABELS = {
                "financial_results": "📊 نتائج مالية",
                "dividends": "💰 توزيعات",
                "board": "📋 مجلس إدارة",
                "agm": "🏛️ جمعيات",
                "disclosures": "⚡ إفصاحات",
                "insider": "👤 مطلعين",
                "other": "📄 أخرى",
            }
            from collections import defaultdict
            grouped = defaultdict(list)
            for it in items:
                grouped[it.get("sub_category", "other")].append(it)
            for sub_key, sub_label in SUB_LABELS.items():
                sub_items = grouped.get(sub_key, [])
                if not sub_items:
                    continue
                lines.append(f"\n{sub_label}")
                for it in sub_items[:5]:
                    b = badge(it.get("priority", 3))
                    headline = it.get("headline", "")[:80]
                    company = it.get("company")
                    tag = f" [{company}]" if company else ""
                    lines.append(f"{b} {headline}{tag}")
        else:
            for it in items[:15]:
                b = badge(it.get("priority", 3))
                headline = it.get("headline", "")[:80]
                source = it.get("source_name", "")
                tag = f" ({source})" if source and source != "Boursa Kuwait" else ""
                lines.append(f"{b} {headline}{tag}")

        return "\n".join(lines)
```

Also update `get_morning_news_text()` to use the new format:
```python
def get_morning_news_text():
    return format_news_telegram(limit=20)
```

---

## Step 2: Update `/news` command in `server.py`

### Replace the current handler (around line 5937):

**Old:**
```python
    if cmd == "/news" or cmd.startswith("/news "):
        if not NEWS_ENGINE_OK:
            return "❌ news engine not loaded"
        args_t = text.strip()[5:].strip() if len(text.strip()) > 5 else ""
        cat = None
        if args_t in ("kuwait", "economy", "technology", "tech"):
            cat = "technology" if args_t == "tech" else args_t
        return handle_news_latest(cat)
```

**New:**
```python
    if cmd in ("/news", "/أخبار") or text.strip().startswith(("/news ", "/أخبار ")):
        if not NEWS_ENGINE_OK:
            return "❌ news engine not loaded"
        from news_engine import format_news_telegram
        # Parse argument
        raw = text.strip()
        if raw.startswith("/أخبار"):
            args_t = raw[6:].strip()
        else:
            args_t = raw[5:].strip()
        
        # Map Arabic/English to category
        CAT_MAP = {
            "": None,
            "بورصة": "boursa", "البورصة": "boursa", "boursa": "boursa",
            "اقتصاد": "economy", "الاقتصاد": "economy", "economy": "economy",
            "عالمي": "world", "world": "world",
            "تقنية": "tech", "تكنولوجيا": "tech", "tech": "tech", "ai": "tech",
            "نتائج": ("boursa", "financial_results"),
            "توزيعات": ("boursa", "dividends"),
            "إفصاحات": ("boursa", "disclosures"),
            "مطلعين": ("boursa", "insider"),
        }
        
        mapped = CAT_MAP.get(args_t)
        if isinstance(mapped, tuple):
            return format_news_telegram(category=mapped[0], sub_category=mapped[1])
        return format_news_telegram(category=mapped)
```

---

## Step 3: Add import to server.py

Make sure `format_news_telegram` is imported at the top with the other news_engine imports:
```python
from news_engine import (
    ...existing imports...,
    format_news_telegram,
)
```

---

## Step 4: Remove old tg_news.py dependency

The old `/news` path at line ~6200 that calls `get_news_digest()` from `tg_news` should be REMOVED or guarded to not conflict. The new handler above should take priority.

---

## Telegram Commands After This:

```
/أخبار              → All news, grouped by section
/أخبار بورصة        → Boursa Kuwait only (grouped by sub-category)
/أخبار اقتصاد       → Economy news only
/أخبار عالمي        → World news only
/أخبار تقنية        → Tech & AI only
/أخبار نتائج        → Financial results only
/أخبار توزيعات      → Dividends only
/أخبار إفصاحات      → Material disclosures only
/أخبار مطلعين       → Insider disclosures only
/news               → Same as /أخبار (English alias)
/news boursa        → Same as /أخبار بورصة
```

---

## Test Checklist
1. `/أخبار` → shows all 4 sections with priority badges
2. `/أخبار بورصة` → shows Boursa with sub-category grouping
3. `/أخبار تقنية` → shows Gemini tech news
4. `/أخبار نتائج` → shows only financial results
5. Morning report still works (uses format_news_telegram)
6. Old `/news` English alias still works
