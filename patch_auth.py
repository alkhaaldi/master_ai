import re

with open("/home/pi/master_ai/server.py", "r") as f:
    content = f.read()

# --- Add API key loading after AGENT_SECRET ---
old_agent = 'AGENT_SECRET = os.getenv("AGENT_SECRET", "")'
new_agent = """AGENT_SECRET = os.getenv("AGENT_SECRET", "")
MASTER_API_KEY = os.getenv("MASTER_AI_API_KEY", "")
if MASTER_API_KEY:
    logger.info("MASTER_AI_API_KEY loaded (ends ...%s)", MASTER_API_KEY[-4:])
else:
    logger.warning("MASTER_AI_API_KEY not set - tunnel endpoints UNPROTECTED!")"""

if old_agent in content:
    content = content.replace(old_agent, new_agent)
    print("Added API key loading")
else:
    print("WARNING: Could not find AGENT_SECRET line")

# --- Add auth dependency function after imports ---
# Find the CORSMiddleware line and add auth after it
old_cors = 'app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])'
new_cors = """app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- API Key Authentication for external access ---
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader, APIKeyQuery

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)

async def verify_api_key(
    header_key: str = Security(api_key_header),
    query_key: str = Security(api_key_query),
):
    \"\"\"Check API key from header or query param. Skip if request is local.\"\"\"
    # Allow local requests without key
    key = header_key or query_key
    if not MASTER_API_KEY:
        return True  # No key configured = no auth
    if key == MASTER_API_KEY:
        return True
    return False

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

class APIKeyMiddleware(BaseHTTPMiddleware):
    OPEN_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}
    LOCAL_PREFIXES = ("127.0.0.1", "192.168.", "172.", "10.")

    async def dispatch(self, request: StarletteRequest, call_next):
        path = request.url.path
        client_ip = request.client.host if request.client else ""

        # Allow open paths
        if path in self.OPEN_PATHS:
            return await call_next(request)

        # Allow local network without key
        if any(client_ip.startswith(p) for p in self.LOCAL_PREFIXES):
            return await call_next(request)

        # External request - require API key
        if MASTER_API_KEY:
            key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
            if key != MASTER_API_KEY:
                from starlette.responses import JSONResponse
                return JSONResponse(status_code=401, content={"error": "Invalid or missing API key"})

        return await call_next(request)

app.add_middleware(APIKeyMiddleware)"""

if old_cors in content:
    content = content.replace(old_cors, new_cors)
    print("Added API key middleware")
else:
    print("WARNING: Could not find CORS line")

with open("/home/pi/master_ai/server.py", "w") as f:
    f.write(content)
print("server.py saved with auth")
