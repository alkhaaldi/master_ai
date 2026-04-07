# News Engine — Full Architecture Plan
# Claude Code: Execute this plan on RPi

## Overview
Build a complete news system with 2 data sources:
1. **Boursa Kuwait RSS** — live company disclosures (FREE, official, real-time)
2. **Gemini API + Google Search** — economic, world, tech/AI news

---

## NEWS HIERARCHY — 5 Main Sections

### Section 1: 🏦 بورصة الكويت (Boursa Kuwait) — FROM RSS
This is the MAIN section with **6 sub-tabs** the user can toggle:

| Sub-tab | RSS Type | Arabic | What it covers |
|---------|----------|--------|----------------|
| 📊 نتائج مالية | T=9 | النتائج المالية | Quarterly/annual earnings reports |
| 💰 توزيعات أرباح | T=4,5,20 | توزيع الأرباح | Dividend distributions + date changes |
| 📋 مجلس الإدارة | T=7,8,10,11,12,13,14,15 | مجلس الإدارة | Board meetings, results, resignations, elections |
| 🏛️ جمعيات عمومية | T=1,2,3,19,21,22 | الجمعيات العامة | AGM meetings, amendments, postponements |
| ⚡ إفصاحات جوهرية | T=23,24,25,34,35,36 | إفصاحات | Material info, unusual trade, judicial, credit rating |
| 👤 إفصاحات مطلعين | RSS filter T=6 | المطلعين | Insider trading disclosures |

**Additional Boursa sub-types (lower priority, grouped under "أخرى"):**
- T=16,30,39,41 → Delisting
- T=17 → Monthly info
- T=18 → Fund financials
- T=31,32 → Name/ticker changes
- T=40 → Other announcements

### Section 2: 📈 اقتصاد (Economy) — FROM GEMINI
Kuwait/GCC economic news: oil prices, government policies, banking, real estate, budget

### Section 3: 🌍 عالمي (World) — FROM GEMINI  
Major global events: geopolitics, conflicts, major economic events, climate

### Section 4: 🤖 تكنولوجيا و AI (Tech) — FROM GEMINI
AI developments, tech companies, product launches, cybersecurity, startups

### Section 5: 📰 أخبار السوق (Market News) — FROM RSS
Trading system announcements from X-Stream: `feedmarket.aspx`

---

## PRIORITY / IMPORTANCE SCORING

Each news item gets a priority score (1-5):

### Boursa RSS Priority Rules:
```
Priority 5 (URGENT - Red):
  - Financial Results (T=9) → Always top
  - Material Information (T=34) → Always top
  - Unusual Trade Disclosure (T=23) → Always top

Priority 4 (HIGH - Gold):
  - Dividend Distribution (T=4,20) → Money event
  - Board Meeting Results (T=8) → Decision made
  - Supplementary/Amendment Disclosures (T=35,36)

Priority 3 (MEDIUM - Default):
  - Board Meeting announced (T=7)
  - AGM Meeting (T=1)
  - Credit Rating (T=25)
  - Insider Disclosures (T=6 from insider feed)

Priority 2 (LOW):
  - Date changes (T=2,5,10,11,21)
  - Postponements (T=3,22)
  - Board membership changes (T=12,13,14,15)

Priority 1 (INFO):
  - Monthly info (T=17)
  - Name/ticker changes (T=31,32)
  - Delisting (T=16,30,39,41)
  - Other (T=40)
```

### Gemini News Priority Rules:
```
Priority 5: Breaking/urgent (Gemini prompt asks it to flag)
Priority 4: Major impact on Kuwait/GCC
Priority 3: Important global/tech news
Priority 2: General interest
```

---

## VISUAL LAYOUT — Dashboard Design

```
┌─────────────────────────────────────────────────┐
│ [TICKER BAR - scrolling headlines]              │
├─────────────────────────────────────────────────┤
│  Stats: Total | Boursa | Economy | Tech | World │
├─────────────────────────────────────────────────┤
│  MAIN TABS:                                     │
│  [🏦 البورصة] [📈 اقتصاد] [🌍 عالمي] [🤖 تقنية]│
├─────────────────────────────────────────────────┤
│  When "البورصة" selected → SUB-TABS:            │
│  [الكل] [نتائج مالية] [توزيعات] [مجلس إدارة]  │
│  [جمعيات] [إفصاحات] [مطلعين]                   │
├─────────────────────────────────────────────────┤
│                                                 │
│  ⬛ Priority 5 card (RED accent, larger)        │
│  ⬛ Priority 4 card (GOLD accent)               │
│  ⬛ Priority 3 card (normal)                    │
│  ⬛ Priority 3 card (normal)                    │
│  ⬛ Priority 2 card (dimmer, compact)           │
│                                                 │
├─────────────────────────────────────────────────┤
│  Last update: 14:32 | Auto-refresh: 5m/30m     │
│  [🔄 تحديث البورصة] [🔄 تحديث الأخبار]         │
└─────────────────────────────────────────────────┘
```

### Card Design by Priority:
```
Priority 5 (URGENT):
  - Left border: 4px RED
  - Background: slightly red-tinted
  - Badge: "عاجل" red badge
  - Headline: larger font (0.9rem)
  - Appears FIRST always

Priority 4 (HIGH):
  - Left border: 3px GOLD
  - Badge: category colored
  - Headline: bold (0.82rem)

Priority 3 (MEDIUM):
  - Left border: 2px category color
  - Standard card

Priority 2-1 (LOW):
  - No border accent
  - Compact layout (less padding)
  - Dimmer text
```

---

## BACKEND IMPLEMENTATION

### Step 1: Create `news_engine.py`

```python
"""News Engine — Boursa RSS + Gemini Search"""
import os, json, time, logging, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

logger = logging.getLogger("news_engine")

GEMINI_KEY = ""
_key_file = os.path.expanduser("~/.gemini_key")
if os.path.exists(_key_file):
    GEMINI_KEY = open(_key_file).read().strip()

# --- RSS FEEDS ---
BOURSA_RSS = {
    "all":       "https://rss.boursakuwait.com.kw/A/rss/FeedFull.aspx",
    "disclosures": "https://rss.boursakuwait.com.kw/A/rss/FeedFull.aspx?T=4",
    "agm":       "https://rss.boursakuwait.com.kw/A/rss/FeedFull.aspx?T=5",
    "insider":   "https://rss.boursakuwait.com.kw/A/rss/FeedFull.aspx?T=6",
    "trading":   "https://rss.boursakuwait.com.kw/A/rss/FeedFull.aspx?T=0",
    "market":    "https://rss.boursakuwait.com.kw/A/rss/feedmarket.aspx",
    "issuers":   "https://rss.boursakuwait.com.kw/A/rss/feedboursa.aspx",
}

# Priority mapping by newstype
PRIORITY_MAP = {
    9: 5,   # Financial Results
    34: 5,  # Material Information
    23: 5,  # Unusual Trade
    4: 4, 20: 4,  # Dividends
    8: 4,   # Board Results
    35: 4, 36: 4,  # Supplementary/Amendment
    7: 3,   # Board Meeting
    1: 3,   # AGM
    25: 3,  # Credit Rating
    6: 3,   # Insider (from feed)
    2: 2, 5: 2, 10: 2, 11: 2, 21: 2,  # Date changes
    3: 2, 22: 2,  # Postponements
    12: 2, 13: 2, 14: 2, 15: 2,  # Board changes
    17: 1, 31: 1, 32: 1,  # Monthly/name
    16: 1, 30: 1, 39: 1, 41: 1,  # Delisting
    40: 1,  # Other
}

# Sub-category mapping for Boursa tab
SUB_CATEGORY_MAP = {
    9: "financial_results",
    4: "dividends", 5: "dividends", 20: "dividends",
    7: "board", 8: "board", 10: "board", 11: "board",
    12: "board", 13: "board", 14: "board", 15: "board",
    1: "agm", 2: "agm", 3: "agm", 19: "agm", 21: "agm", 22: "agm",
    23: "disclosures", 24: "disclosures", 25: "disclosures",
    34: "disclosures", 35: "disclosures", 36: "disclosures",
    # insider comes from feed filter, not newstype
}
```

### Key Functions:

```python
def fetch_boursa_rss(url: str) -> list[dict]:
    """Fetch and parse Boursa Kuwait RSS feed"""
    # Returns list of:
    # {
    #   "source": "boursa",
    #   "category": "boursa",
    #   "sub_category": "financial_results" | "dividends" | "board" | etc,
    #   "headline": str (Arabic),
    #   "summary": str,
    #   "company": str (extracted from title if possible),
    #   "newstype": int,
    #   "priority": int (1-5),
    #   "published": datetime,
    #   "link": str
    # }

def fetch_gemini_news(category: str, prompt: str) -> list[dict]:
    """Fetch news from Gemini with Google Search grounding"""
    # Returns list of:
    # {
    #   "source": "gemini",
    #   "category": "economy" | "world" | "tech",
    #   "headline": str (Arabic),
    #   "summary": str,
    #   "source_name": str,
    #   "priority": int (2-5, based on Gemini flagging),
    #   "fetched_at": datetime
    # }

def refresh_boursa():
    """Fetch all Boursa RSS feeds, deduplicate, store in DB"""

def refresh_gemini():
    """Fetch 3 Gemini categories, store in DB"""

def get_news(category=None, sub_category=None, limit=50, min_priority=1):
    """Read news from DB for API endpoint"""
```

### Step 2: DB Table — `data/life.db`

```sql
CREATE TABLE IF NOT EXISTS news_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,          -- 'boursa' or 'gemini'
    category TEXT NOT NULL,        -- 'boursa','economy','world','tech'
    sub_category TEXT,             -- 'financial_results','dividends','board','agm','disclosures','insider','market','other'
    headline TEXT NOT NULL,
    summary TEXT,
    company TEXT,                  -- company name if boursa
    newstype INTEGER,             -- RSS newstype number
    priority INTEGER DEFAULT 3,   -- 1-5
    source_name TEXT,             -- 'Boursa Kuwait' or Gemini source
    link TEXT,
    published_at TEXT,            -- ISO datetime
    fetched_at TEXT NOT NULL,     -- when we fetched it
    hash TEXT UNIQUE              -- dedup: hash of headline
);
CREATE INDEX IF NOT EXISTS idx_news_cat ON news_items(category);
CREATE INDEX IF NOT EXISTS idx_news_pri ON news_items(priority DESC);
CREATE INDEX IF NOT EXISTS idx_news_date ON news_items(fetched_at DESC);
```

### Step 3: Add to `dashboard_api.py`

```python
@app.get("/api/news")
async def api_news(
    category: str = None,       # boursa, economy, world, tech
    sub: str = None,            # financial_results, dividends, board, agm, disclosures, insider
    limit: int = 50,
    min_priority: int = 1
):
    items = news_engine.get_news(category, sub, limit, min_priority)
    boursa_count = len([i for i in all_items if i["category"] == "boursa"])
    economy_count = len([i for i in all_items if i["category"] == "economy"])
    world_count = len([i for i in all_items if i["category"] == "world"])
    tech_count = len([i for i in all_items if i["category"] == "tech"])
    return {
        "items": items,
        "counts": {
            "total": len(all_items),
            "boursa": boursa_count,
            "economy": economy_count,
            "world": world_count,
            "tech": tech_count
        },
        "last_boursa_refresh": news_engine.last_boursa_refresh,
        "last_gemini_refresh": news_engine.last_gemini_refresh
    }
```

### Step 4: Add Schedulers to `server.py`

```python
# Boursa RSS: every 5 minutes (lightweight, free)
scheduler.add_job(news_engine.refresh_boursa, 'interval', minutes=5, id='news_boursa')

# Gemini news: every 30 minutes (API cost)
scheduler.add_job(news_engine.refresh_gemini, 'interval', minutes=30, id='news_gemini')

# Cleanup old news: daily at midnight
scheduler.add_job(news_engine.cleanup_old, 'cron', hour=0, id='news_cleanup')
# cleanup_old: delete items older than 7 days
```

### Step 5: Telegram Command (optional)

```python
# /أخبار → latest 5 high-priority news
# /أخبار بورصة → latest boursa disclosures
# /أخبار تقنية → latest tech/AI news
```

---

## FRONTEND (claude.ai builds)

claude.ai will update `www/trading/news.html` to:
1. Fetch from `/api/news` instead of calling Gemini directly
2. Show 4 main tabs + Boursa sub-tabs
3. Priority-based card design (5 styles)
4. Ticker bar with top headlines
5. Separate refresh buttons for Boursa (5m) and Gemini (30m)
6. Stats bar with counts per section
7. Auto-refresh: Boursa every 5m, Gemini every 30m

---

## EXECUTION ORDER

1. Claude Code: Create `news_engine.py` (this file has all the logic)
2. Claude Code: Add DB table to life.db
3. Claude Code: Add `/api/news` endpoint to `dashboard_api.py`
4. Claude Code: Add schedulers to `server.py`
5. Claude Code: Test with `quick_check.py` + `smoke_test.py`
6. Claude Code: `restart_master_ai.sh`
7. claude.ai: Update `news.html` to use `/api/news`
8. Test end-to-end

---

## IMPORTANT NOTES

- API Key: Read from `~/.gemini_key` on RPi (need to copy it there first)
- RSS is Arabic by default (using /A/ path)
- Dedup by hash of headline (same news from different feeds)
- Store max 7 days of news, cleanup daily
- Boursa RSS is FREE and unlimited — refresh aggressively
- Gemini costs tokens — refresh conservatively (30m)
- Priority 5 items should trigger Telegram notification
