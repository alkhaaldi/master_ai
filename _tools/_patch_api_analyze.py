"""Add /api/analyze endpoint to server.py for analysis.html Gemini page."""
import sys

FILE = "/home/pi/master_ai/server.py"
with open(FILE) as f:
    content = f.read()

# Insert before the KAIROS section
marker = "# ── Task Manager API (Tier2 #8 integration)"
idx = content.find(marker)
if idx < 0:
    # Fallback: find KAIROS
    marker = "# ── KAIROS Agent API"
    idx = content.find(marker)
if idx < 0:
    print("Could not find insertion marker")
    sys.exit(1)

endpoint = '''
# ── Stock Analysis API (Gemini 2.5 Pro via stock_analyzer.py) ──
@app.get("/api/analyze")
async def api_analyze(symbol: str = ""):
    """Full technical analysis for a stock using Gemini 2.5 Pro + Bridge data."""
    if not symbol:
        return {"error": "symbol parameter required"}
    symbol = symbol.upper().strip()
    try:
        from stock_analyzer import analyze_stock
        result = await asyncio.to_thread(analyze_stock, symbol)
        return result
    except Exception as e:
        logger.error("analyze error for %s: %s", symbol, e)
        return {"error": str(e)}


'''

content = content[:idx] + endpoint + content[idx:]

with open(FILE, "w") as f:
    f.write(content)

print("PATCHED server.py — added /api/analyze endpoint")
