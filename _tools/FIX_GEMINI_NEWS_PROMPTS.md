# Fix Gemini News Prompts — More Specific Headlines
# Claude Code: Execute on RPi

## Problem
Current Gemini prompts generate GENERIC summaries instead of ACTUAL news headlines.
Example: "الحرب الأمريكية الإسرائيلية على إيران" instead of "حريق كبير في مطار الكويت بعد اعتداءات بمسيّرات إيرانية"

## Solution
Update the prompts in `news_engine.py` to explicitly ask for:
1. REAL headlines from REAL sources (not summaries)
2. Source name for each headline
3. Specific events, not general topics

## Find the GEMINI_PROMPTS dict in news_engine.py and replace with:

```python
GEMINI_PROMPTS = {
    "economy": """Search Google for today's latest Kuwait and GCC economic news.
Find the ACTUAL headlines from real news sources (Reuters, Bloomberg, CNBC Arabia, Al Qabas, Al Rai, Argaam, Mubasher, Sky News Arabia, CNN Arabic).
Include: oil prices with exact numbers, Kuwait government decisions, GCC banking news, real estate market updates, central bank decisions.
Return ONLY a JSON array. Each item must have:
- "headline": the EXACT real headline in Arabic (not a summary, the actual title)
- "summary": 1 sentence Arabic summary of the key fact
- "source": the English name of the news outlet
- "priority": 5 for breaking/urgent, 4 for important, 3 for normal
Return 8-12 items sorted by importance. Output raw JSON only, no markdown fences.""",

    "world": """Search Google for today's most important global news RIGHT NOW.
Find ACTUAL headlines from major sources (BBC Arabic, Al Jazeera, Reuters, CNN Arabic, Sky News Arabia, France 24).
Include: wars/conflicts updates with specific events, major political decisions, natural disasters, health crises.
Focus on events that happened TODAY or in the last few hours.
Return ONLY a JSON array. Each item must have:
- "headline": the EXACT real headline in Arabic (copy from the source, not your summary)
- "summary": 1 sentence Arabic summary with specific facts/numbers
- "source": the English name of the news outlet
- "priority": 5 for breaking/war/disaster, 4 for major political, 3 for normal
Return 8-12 items sorted by importance. Output raw JSON only, no markdown fences.""",

    "tech": """Search Google for today's latest technology and AI news.
Find ACTUAL headlines from real tech sources (TechCrunch, Ars Technica, The Verge, Wired, VentureBeat, MIT Technology Review).
Include: AI model releases, major funding rounds, cybersecurity incidents, product launches, tech company earnings, regulatory decisions.
Return ONLY a JSON array. Each item must have:
- "headline": the EXACT real headline in Arabic (translate the actual title, not a summary)
- "summary": 1 sentence Arabic summary with company names and numbers
- "source": the English name of the tech outlet
- "priority": 5 for major AI breakthrough/security incident, 4 for big funding/launch, 3 for normal
Return 8-12 items sorted by importance. Output raw JSON only, no markdown fences."""
}
```

## Key Changes:
1. "EXACT real headline" not "summarize"
2. Named specific sources to search
3. "TODAY or last few hours" for recency
4. Priority scoring instructions included in prompt
5. "copy from the source, not your summary" — explicit instruction

## Also: Use priority from Gemini response
In the parsing code, if Gemini returns a "priority" field, use it instead of defaulting to 3.
Find where items are created after parsing and add:
```python
"priority": item.get("priority", 3),
```

## Test after change:
```bash
curl -X POST http://localhost:9000/api/news/refresh-gemini
sleep 5
curl http://localhost:9000/api/news?category=world&limit=5
```
Verify headlines are specific (mentioning places, names, numbers) not generic summaries.
