"""
tg_tasks.py - Task management commands for Telegram
Commands: /tasks, /task add <title>, /task done <id>
"""
import logging
from tasks_db import get_tasks, get_summary, add_task, update_task

logger = logging.getLogger("tg_tasks")

PRIORITY_ICONS = {"high": "\U0001f534", "medium": "\U0001f7e1", "low": "\U0001f7e2"}
STATUS_ICONS = {"pending": "\u23f3", "in_progress": "\U0001f527", "done": "\u2705", "blocked": "\u26d4"}
CAT_ICONS = {"ha": "\U0001f3e0", "trading": "\U0001f4c8", "personal": "\U0001f464", "work": "\u2699\ufe0f", "project": "\U0001f680"}


async def cmd_tasks(args: str = "") -> str:
    """Handle /tasks [category|summary]"""
    args = args.strip().lower()
    
    if args == "summary" or not args:
        summary = await get_summary()
        if not summary:
            return "\u2705 \u0645\u0627 \u0641\u064a\u0647 \u0645\u0647\u0627\u0645!"
        
        lines = ["\U0001f4cb \u0645\u0644\u062e\u0635 \u0627\u0644\u0645\u0647\u0627\u0645:\n"]
        for item in summary:
            cat = item.get("category", "other")
            icon = CAT_ICONS.get(cat, "\U0001f4cc")
            lines.append(f"{icon} {cat}: {item.get('pending',0)} \u0645\u0639\u0644\u0642 / {item.get('total',0)} \u0625\u062c\u0645\u0627\u0644\u064a")
        return "\n".join(lines)
    
    # Filter by category
    category = args if args in ("ha", "trading", "personal", "work", "project") else None
    tasks = await get_tasks(category=category, status="pending", limit=10)
    
    if not tasks:
        return f"\u2705 \u0644\u0627 \u0645\u0647\u0627\u0645 \u0645\u0639\u0644\u0642\u0629{' \u0628\u0640 ' + args if args else ''}"
    
    lines = [f"\U0001f4cb \u0627\u0644\u0645\u0647\u0627\u0645 ({len(tasks)}):\n"]
    for t in tasks:
        pri = PRIORITY_ICONS.get(t.get("priority","medium"), "")
        lines.append(f"{pri} #{t['id']} {t['title']}")
    return "\n".join(lines)


async def cmd_task_add(text: str) -> str:
    """Handle /task add <category> <title>"""
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 1:
        return "\u0627\u0644\u0627\u0633\u062a\u062e\u062f\u0627\u0645: /task add \u0627\u0644\u0639\u0646\u0648\u0627\u0646"
    
    title = parts[0] if len(parts) == 1 else parts[1]
    cat = "personal"
    
    # Auto-detect category from title
    title_lower = title.lower()
    if any(kw in title_lower for kw in ["ha ", "home", "\u0628\u064a\u062a", "\u0645\u0643\u064a\u0641", "\u0636\u0648", "\u0633\u062a\u0627\u0631"]):
        cat = "ha"
    elif any(kw in title_lower for kw in ["\u0633\u0647\u0645", "\u062a\u062f\u0627\u0648\u0644", "stock", "trade", "cleaning", "senergy"]):
        cat = "trading"
    elif any(kw in title_lower for kw in ["\u0634\u063a\u0644", "\u062f\u0648\u0627\u0645", "unit", "shift", "work"]):
        cat = "work"
    
    task = await add_task(cat, title)
    if task:
        return f"\u2705 \u0645\u0647\u0645\u0629 #{task['id']}: {title} ({cat})"
    return "\u26a0 \u0641\u0634\u0644 \u0625\u0636\u0627\u0641\u0629 \u0627\u0644\u0645\u0647\u0645\u0629"


async def cmd_task_done(task_id: str) -> str:
    """Handle /task done <id>"""
    try:
        tid = int(task_id.strip())
    except (ValueError, AttributeError):
        return "\u0627\u0644\u0627\u0633\u062a\u062e\u062f\u0627\u0645: /task done <\u0631\u0642\u0645>"
    
    result = await update_task(tid, status="done")
    if result:
        return f"\u2705 \u0645\u0647\u0645\u0629 #{tid} \u062e\u0644\u0635\u062a!"
    return f"\u26a0 \u0645\u0627 \u0644\u0642\u064a\u062a \u0645\u0647\u0645\u0629 #{tid}"
