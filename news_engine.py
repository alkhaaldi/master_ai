"""
news_engine.py — News Digest Engine for Master AI v8 Phase 4
Single-file: RSS fetch, LLM summarization, DB storage, TG formatting, scheduler.
Tables in life.db: news_digests
"""
import os
import re
import json
import sqlite3
import hashlib
import logging
import httpx
from datetime import datetime, date, timedelta
from xml.etree import ElementTree

from circuit_breaker import CircuitBreaker

logger = logging.getLogger("news")

# Integration: cursor-based processing (Tier1 #7)
try:
    from processing_cursor import ProcessingCursor
    _digest_cursor = ProcessingCursor("news_last_digest_id", cursor_type="id")
except ImportError:
    _digest_cursor = None

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")

# Per-source circuit breakers: stop hitting a source after 3 consecutive failures
_source_breakers: dict[str, CircuitBreaker] = {}

# ═══════════════════════════════════════════════════
# NEWS SOURCES (hardcoded, curated)
# ═══════════════════════════════════════════════════

SOURCES = [
    # === BREAKING / WORLD ===
    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "category": "world", "mode": "rss"},
    {"name": "BBC Middle East", "url": "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml", "category": "world", "mode": "rss"},
    {"name": "Al Jazeera EN", "url": "https://www.aljazeera.com/xml/rss/all.xml", "category": "world", "mode": "rss"},
    {"name": "NYT World", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "category": "world", "mode": "rss"},

    # === ECONOMY / MARKETS ===
    {"name": "CNBC Top", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "category": "economy", "mode": "rss"},
    {"name": "Bloomberg", "url": "https://feeds.bloomberg.com/markets/news.rss", "category": "economy", "mode": "rss"},
    {"name": "BBC Business", "url": "https://feeds.bbci.co.uk/news/business/rss.xml", "category": "economy", "mode": "rss"},
    {"name": "FT Markets", "url": "https://www.ft.com/markets?format=rss", "category": "economy", "mode": "rss"},
    {"name": "Google Boursa", "url": "https://news.google.com/rss/search?q=boursa+kuwait+stock+exchange&hl=en&gl=KW&ceid=KW:en", "category": "economy", "mode": "rss"},
    {"name": "NYT Business", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "category": "economy", "mode": "rss"},

    # === KUWAIT / LOCAL ===
    {"name": "Google Kuwait AR", "url": "https://news.google.com/rss/search?q=الكويت&hl=ar&gl=KW&ceid=KW:ar", "category": "kuwait", "mode": "rss"},
    {"name": "Google Kuwait EN", "url": "https://news.google.com/rss/search?q=kuwait&hl=en&gl=KW&ceid=KW:en", "category": "kuwait", "mode": "rss"},
    {"name": "Al Jazeera AR", "url": "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4571-a358-a3a4f68f135d/73d0e1b4-532f-45ef-b135-bfdba6e76a42", "category": "kuwait", "mode": "rss"},
    {"name": "BBC Arabic", "url": "https://feeds.bbci.co.uk/arabic/rss.xml", "category": "kuwait", "mode": "rss"},

    # === TECHNOLOGY ===
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "category": "technology", "mode": "rss"},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "category": "technology", "mode": "rss"},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "category": "technology", "mode": "rss"},
    {"name": "Wired", "url": "https://www.wired.com/feed/rss", "category": "technology", "mode": "rss"},
    {"name": "Hacker News", "url": "https://hnrss.org/frontpage?points=100", "category": "technology", "mode": "rss"},

    # === AI ===
    {"name": "Google AI News", "url": "https://news.google.com/rss/search?q=artificial+intelligence+OR+ChatGPT+OR+Claude+OR+GPT&hl=en&gl=US&ceid=US:en", "category": "ai", "mode": "rss"},
    {"name": "MIT AI", "url": "https://news.mit.edu/rss/topic/artificial-intelligence2", "category": "ai", "mode": "rss"},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/", "category": "ai", "mode": "rss"},

    # === GADGETS ===
    {"name": "9to5Mac", "url": "https://9to5mac.com/feed/", "category": "gadgets", "mode": "rss"},
    {"name": "9to5Google", "url": "https://9to5google.com/feed/", "category": "gadgets", "mode": "rss"},
    {"name": "GSMArena", "url": "https://www.gsmarena.com/rss-news-reviews.php3", "category": "gadgets", "mode": "rss"},
]

CATEGORIES = {
    "world": {"ar": "عالمي", "emoji": "🌍"},
    "economy": {"ar": "الاقتصاد", "emoji": "💰"},
    "kuwait": {"ar": "الكويت", "emoji": "🇰🇼"},
    "technology": {"ar": "التكنولوجيا", "emoji": "💻"},
    "ai": {"ar": "ذكاء اصطناعي", "emoji": "🤖"},
    "gadgets": {"ar": "أجهزة", "emoji": "📱"},
}

# ═══════════════════════════════════════════════════
# DB SCHEMA
# ═══════════════════════════════════════════════════

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS news_digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    digest_date TEXT NOT NULL,
    digest_slot TEXT NOT NULL DEFAULT 'manual',
    category TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    item_count INTEGER NOT NULL DEFAULT 0,
    raw_titles_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_news_digest_date ON news_digests(digest_date);
CREATE INDEX IF NOT EXISTS idx_news_digest_cat ON news_digests(category);
"""


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_schema():
    with _conn() as c:
        c.executescript(_SCHEMA_SQL)
    logger.info("news schema initialized")


# ═══════════════════════════════════════════════════
# RSS FETCH
# ═══════════════════════════════════════════════════

def _strip_html(text):
    """Remove HTML tags."""
    return re.sub(r'<[^>]+>', '', text or '').strip()


def _get_source_breaker(url: str) -> CircuitBreaker:
    """Get or create a circuit breaker for an RSS source URL."""
    if url not in _source_breakers:
        _source_breakers[url] = CircuitBreaker(name=url[:40], failure_threshold=3, cooldown_seconds=300)
    return _source_breakers[url]


async def fetch_rss(url, max_items=10, timeout=15):
    """Fetch RSS feed and return list of {title, link, published, summary}."""
    cb = _get_source_breaker(url)
    if not cb.allow_request():
        logger.debug(f"RSS circuit breaker open for {url[:40]}, skipping")
        return []
    items = []
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code != 200:
                cb.record_failure()
                logger.warning(f"RSS {url}: status {r.status_code}")
                return items
            root = ElementTree.fromstring(r.text)
            # Standard RSS
            for item in root.findall('.//item')[:max_items]:
                title = item.findtext('title', '').strip()
                link = item.findtext('link', '').strip()
                pub = item.findtext('pubDate', '').strip()
                desc = _strip_html(item.findtext('description', ''))
                if title:
                    items.append({"title": title, "link": link, "published": pub, "summary": desc[:300]})
            # Atom fallback
            if not items:
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                for entry in root.findall('.//atom:entry', ns)[:max_items]:
                    title = entry.findtext('atom:title', '', ns).strip()
                    link_el = entry.find('atom:link', ns)
                    link = link_el.get('href', '') if link_el is not None else ''
                    pub = entry.findtext('atom:updated', '', ns).strip()
                    desc = _strip_html(entry.findtext('atom:summary', '', ns))
                    if title:
                        items.append({"title": title, "link": link, "published": pub, "summary": desc[:300]})
        cb.record_success()
    except Exception as e:
        cb.record_failure()
        logger.warning(f"RSS fetch error {url}: {e}")
    return items


async def fetch_category(category=None, max_per_source=10):
    """Fetch all sources for a category (or all if None)."""
    all_items = []
    seen_titles = set()
    for src in SOURCES:
        if category and src["category"] != category:
            continue
        items = await fetch_rss(src["url"], max_items=max_per_source)
        for item in items:
            # Dedupe by title hash
            h = hashlib.md5(item["title"].encode()).hexdigest()[:12]
            if h not in seen_titles:
                seen_titles.add(h)
                item["source"] = src["name"]
                item["category"] = src["category"]
                all_items.append(item)
    return all_items


# ═══════════════════════════════════════════════════
# LLM SUMMARIZATION
# ═══════════════════════════════════════════════════

async def generate_digest(category=None, slot="manual"):
    """Fetch news + summarize with LLM. Returns digest dict."""
    items = await fetch_category(category)
    if not items:
        return {"ok": False, "error": "No news items fetched"}

    cat_label = CATEGORIES.get(category, {}).get("ar", category or "mixed")

    # Build prompt for LLM
    headlines = []
    for i, item in enumerate(items[:50], 1):
        headlines.append(f"{i}. [{item['source']}] {item['title']}")
        if item.get("summary"):
            headlines.append(f"   {item['summary'][:150]}")

    headlines_text = chr(10).join(headlines)

    prompt = f"""أنت محرر أخبار محترف في وكالة أنباء عربية. اكتب ملخص الأخبار بهذا الشكل:

القواعد:
- كل خبر في سطر واحد بأسلوب وكالة أنباء رسمية
- ابدأ كل خبر بـ emoji تصنيف حسب القواعد التالية (مهم جداً — لا تخلط):
  🔥 عاجل: أحداث كبرى عاجلة
  💰 اقتصادي: أسواق، نفط، بنوك، عملات، أرباح شركات
  🇰🇼 محلي: أخبار الكويت والخليج
  🌍 عالمي: سياسة دولية، أحداث عالمية
  ⚔️ عسكري: حروب، أسلحة، صراعات عسكرية فقط (ليس تقنية!)
  ⚡ تقني: برمجيات، شركات تقنية، أمن سيبراني، إنترنت، تطبيقات (ليس AI وليس أجهزة!)
  🤖 ذكاء اصطناعي: OpenAI, Claude, Gemini, ChatGPT, LLM, نماذج ذكية، تدريب نماذج (فقط AI!)
  📱 أجهزة: هواتف، لابتوب، ساعات، سماعات، كاميرات، أي منتج/جهاز مادي جديد (Samsung, Apple, Google Pixel, إلخ)
- تأكد أن كل فئة فيها 3+ أخبار على الأقل. إذا ما في أخبار أجهزة، ابحث عن أي خبر عن منتج جديد أو جهاز
- أضف المصدر بين أقواس في نهاية كل خبر: (Reuters) (BBC) (KUNA) (الراي) (القبس) (Bloomberg)
- أضف أرقام وإحصائيات حيثما أمكن: أسعار، نسب تغيير، أرقام
- وضّح التأثير على الأسواق الخليجية والكويتية إذا كان واضحاً
- اكتب 20-25 خبر (وليس أقل من 18)
- رتّب: عاجل → اقتصادي → محلي → عالمي → تقني → AI → أجهزة
- اللغة: عربية فصيحة رسمية — لا عامية — أسلوب صحفي محترف
- تجاهل أخبار المشاهير والرياضة
- أمثلة (التزم بهذا التصنيف بالضبط):
  💰 ارتفع خام برنت 2.3% إلى 73.50 دولاراً وسط تصاعد التوترات في مضيق هرمز (Reuters)
  🇰🇼 وافق مجلس الوزراء الكويتي على مشروع قانون الدين العام بسقف 30 مليار دينار (KUNA)
  ⚡ رفعت مايكروسوفت أسعار Microsoft 365 بنسبة 15% عالمياً (Bloomberg)
  🤖 أطلقت Anthropic نموذج Claude 4.6 مع قدرات برمجة متقدمة (TechCrunch)
  📱 أعلنت سامسونج عن Galaxy S25 Ultra بمعالج Snapdragon 8 Gen 4 (GSMArena)

العناوين:
{headlines_text}

الملخص:"""

    # Call Anthropic API
    try:
        import anthropic
        client = anthropic.Anthropic()
        _news_model = __import__("model_tiers").MODEL_ROUTINE
        response = client.messages.create(
            model=_news_model,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        summary = response.content[0].text
        try:
            from cost_tracker import track_cost
            track_cost(response.usage, _news_model, source="news_digest")
        except Exception:
            pass
    except Exception as e:
        logger.error(f"LLM digest error: {e}")
        # Fallback: just list titles
        summary = chr(10).join(f"\u2022 {item['title']}" for item in items[:8])

    # Save to DB
    now = datetime.now()
    titles_json = json.dumps([{"title": i["title"], "source": i["source"]} for i in items[:50]], ensure_ascii=False)

    with _conn() as c:
        c.execute("""INSERT INTO news_digests
            (digest_date, digest_slot, category, summary_text, item_count, raw_titles_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (now.strftime("%Y-%m-%d"), slot, category or "mixed", summary, len(items), titles_json, now.strftime("%Y-%m-%d %H:%M:%S")))
        did = c.execute("SELECT last_insert_rowid()").fetchone()[0]

    return {
        "ok": True,
        "digest_id": did,
        "category": category or "mixed",
        "category_ar": cat_label,
        "summary": summary,
        "item_count": len(items),
    }


# ═══════════════════════════════════════════════════
# READ DIGESTS
# ═══════════════════════════════════════════════════

def get_latest_digest(category=None):
    """Get most recent digest, optionally filtered by category."""
    with _conn() as c:
        if category:
            row = c.execute("SELECT * FROM news_digests WHERE category=? ORDER BY created_at DESC LIMIT 1", (category,)).fetchone()
        else:
            row = c.execute("SELECT * FROM news_digests ORDER BY created_at DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def get_today_digests():
    """Get all digests from today."""
    today = date.today().isoformat()
    with _conn() as c:
        rows = c.execute("SELECT * FROM news_digests WHERE digest_date=? ORDER BY created_at DESC", (today,)).fetchall()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════
# TG FORMATTING
# ═══════════════════════════════════════════════════

def format_digest_tg(digest):
    """Format digest for Telegram."""
    if not digest:
        return "\U0001f4f0 \u0645\u0627 \u0639\u0646\u062f\u064a digest \u062c\u0627\u0647\u0632 \u2014 \u0627\u0633\u062a\u062e\u062f\u0645 /news_now"
    cat_info = CATEGORIES.get(digest.get("category", ""), {"ar": digest.get("category", ""), "emoji": "\U0001f4f0"})
    lines = [
        f"{cat_info['emoji']} *\u0623\u062e\u0628\u0627\u0631 {cat_info['ar']}* \u2014 {digest['digest_date']}",
        "",
        digest["summary_text"],
        "",
        f"\U0001f4ca {digest['item_count']} \u062e\u0628\u0631 \u0645\u0646 \u0627\u0644\u0645\u0635\u0627\u062f\u0631",
    ]
    return "\n".join(lines)


def format_sources_tg():
    """Format sources list for Telegram."""
    lines = ["\U0001f4f0 *\u0627\u0644\u0645\u0635\u0627\u062f\u0631:*\n"]
    for cat_key, cat_info in CATEGORIES.items():
        srcs = [s for s in SOURCES if s["category"] == cat_key]
        if srcs:
            lines.append(f"{cat_info['emoji']} *{cat_info['ar']}:*")
            for s in srcs:
                lines.append(f"  \u2022 {s['name']}")
            lines.append("")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════
# MORNING REPORT
# ═══════════════════════════════════════════════════

def get_morning_news_text():
    """One-liner for morning report."""
    digest = get_latest_digest()
    if not digest:
        return ""
    # Check if it's from today or yesterday
    if digest["digest_date"] == date.today().isoformat():
        return f"\U0001f4f0 \u0645\u0644\u062e\u0635 \u0627\u0644\u0623\u062e\u0628\u0627\u0631 \u062c\u0627\u0647\u0632 \u2014 /news"
    return ""


# ═══════════════════════════════════════════════════
# QUICK QUERY HANDLERS
# ═══════════════════════════════════════════════════

def handle_news_latest(category=None):
    """Handler for 'شنو آخر الأخبار'."""
    digest = get_latest_digest(category)
    return format_digest_tg(digest)


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
        # column format (space, local) - a T cutoff dropped every row
        # sharing the cutoff date, truncating the 24h window at midnight
        cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
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
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")  # space, not T: a T cutoff deleted boundary-day rows early
        cur = conn.execute("DELETE FROM news_digests WHERE created_at < ?", (cutoff,))
        deleted = cur.rowcount
        conn.commit()
        conn.close()
        return {"deleted": deleted}
    except Exception as e:
        return {"error": str(e)}
