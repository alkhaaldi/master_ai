"""Phase B5: Daily News Digest for Telegram.

Sends a daily news summary (Kuwait + Tech) at 7:00 AM.
Manual trigger: /news
Uses RSS feeds - no API keys needed.
"""
import httpx, logging, asyncio, re
from datetime import datetime
from xml.etree import ElementTree as ET

logger = logging.getLogger("tg_news")

# RSS Feeds
FEEDS = [
    {"name": "الكويت", "url": "https://news.google.com/rss/search?q=Kuwait&hl=ar&gl=KW&ceid=KW:ar", "icon": "KW", "max": 3},
    {"name": "BBC عربي", "url": "https://feeds.bbci.co.uk/arabic/rss.xml", "icon": "📰", "max": 3},
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "icon": "💻", "max": 3},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "icon": "⚙️", "max": 2},
]

_sender_fn = None


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:200] + "..." if len(clean) > 200 else clean


async def _fetch_feed(client: httpx.AsyncClient, feed: dict) -> list:
    """Fetch and parse a single RSS feed."""
    try:
        resp = await client.get(feed["url"], timeout=10, follow_redirects=True)
        if resp.status_code != 200:
            logger.warning(f"Feed {feed['name']} returned {resp.status_code}")
            return []

        root = ET.fromstring(resp.text)
        items = []

        # Handle both RSS 2.0 and Atom
        for item in root.iter("item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = _strip_html(item.findtext("description", ""))
            if title:
                items.append({"title": title, "link": link, "desc": desc})
            if len(items) >= feed["max"]:
                break

        # Atom format
        if not items:
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall(".//atom:entry", ns):
                title = entry.findtext("atom:title", "", ns).strip()
                link_el = entry.find("atom:link", ns)
                link = link_el.get("href", "") if link_el is not None else ""
                desc = _strip_html(entry.findtext("atom:summary", "", ns))
                if title:
                    items.append({"title": title, "link": link, "desc": desc})
                if len(items) >= feed["max"]:
                    break

        return items
    except Exception as e:
        logger.error(f"Feed {feed['name']} error: {e}")
        return []


async def get_news_digest() -> str:
    """Fetch all feeds and build digest message."""
    async with httpx.AsyncClient() as client:
        sections = []
        for feed in FEEDS:
            items = await _fetch_feed(client, feed)
            if items:
                lines = [f"{feed['icon']} {feed['name']}:"]
                for it in items:
                    lines.append(f"  \u2022 {it['title']}")
                sections.append("\n".join(lines))

    if not sections:
        return "⚠ \u0645\u0627 \u0642\u062f\u0631\u062a \u0623\u062c\u064a\u0628 \u0623\u062e\u0628\u0627\u0631 \u0627\u0644\u062d\u064a\u0646"

    now = datetime.now()
    header = f"📰 \u0623\u062e\u0628\u0627\u0631 \u0627\u0644\u064a\u0648\u0645 \u2014 {now.strftime('%d/%m/%Y')}"
    return header + "\n\n" + "\n\n".join(sections)


async def news_scheduler(sender_fn):
    """Background scheduler - sends news at 7:00 AM daily."""
    global _sender_fn
    _sender_fn = sender_fn
    logger.info("📰 News scheduler started")
    while True:
        try:
            now = datetime.now()
            target_hour = 7
            target_min = 0
            # Calculate seconds until next 7:00 AM
            target = now.replace(hour=target_hour, minute=target_min, second=0, microsecond=0)
            if now >= target:
                # Already past 7 AM today, schedule for tomorrow
                from datetime import timedelta
                target += timedelta(days=1)
            wait = (target - now).total_seconds()
            logger.info(f"News digest scheduled in {wait/3600:.1f} hours")
            await asyncio.sleep(wait)
            # Send digest
            digest = await get_news_digest()
            await sender_fn(digest)
            # Sleep a bit to avoid double-send
            await asyncio.sleep(120)
        except Exception as e:
            logger.error(f"News scheduler error: {e}")
            await asyncio.sleep(300)
