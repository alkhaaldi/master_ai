# Fix: Trading HTML routes — بدون .html
# Date: 2026-03-28
# Problem: HA dashboard uses /trading/signals (no .html) but StaticFiles only serves /trading/signals.html
# Solution: Add redirect routes for all 12 pages

# In server.py, BEFORE the StaticFiles mount line, add these routes:

from fastapi.responses import FileResponse
import os

TRADING_HTML_DIR = os.path.join(os.path.dirname(__file__), "www", "trading")
TRADING_PAGES = ["home", "radar", "signals", "brain", "positions", "journal",
                 "calendar", "home-control", "system", "email", "news", "assistant"]

@app.get("/trading/{page}")
async def serve_trading_page(page: str):
    """Serve trading HTML pages with or without .html extension."""
    # If already has .html, serve directly
    if page.endswith(".html"):
        filepath = os.path.join(TRADING_HTML_DIR, page)
    else:
        filepath = os.path.join(TRADING_HTML_DIR, page + ".html")
    
    if os.path.isfile(filepath):
        return FileResponse(filepath, media_type="text/html")
    
    # Fallback: try exact filename
    exact = os.path.join(TRADING_HTML_DIR, page)
    if os.path.isfile(exact):
        return FileResponse(exact)
    
    return JSONResponse({"detail": "Not Found"}, status_code=404)

# IMPORTANT: This route MUST be defined BEFORE the StaticFiles mount
# because StaticFiles catches everything under /trading/

# DELETE or COMMENT OUT the existing StaticFiles mount:
# app.mount("/trading", StaticFiles(directory="www/trading", html=True), name="trading")

# Test after:
# curl -s -o /dev/null -w '%{http_code}' http://localhost:9000/trading/home        → 200
# curl -s -o /dev/null -w '%{http_code}' http://localhost:9000/trading/home.html    → 200
# curl -s -o /dev/null -w '%{http_code}' http://localhost:9000/trading/signals      → 200
# curl -s -o /dev/null -w '%{http_code}' http://localhost:9000/trading/signals.html → 200

# Commit:
# git add server.py
# git commit -m "fix: serve trading HTML pages with and without .html extension"
# bash _tools/restart_master_ai.sh
