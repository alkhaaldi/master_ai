"""google_auth_ext.py — Unified Google OAuth for Master AI v8

Manages a single Google Workspace token with multiple scopes:
- Gmail (readonly)
- Google Calendar (read/write)

Token file: data/google_workspace_token.json
Credentials: gmail_credentials.json (web type)
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("google_auth")

BASE_DIR = Path(__file__).parent
CREDENTIALS_FILE = BASE_DIR / "gmail_credentials.json"
TOKEN_FILE = BASE_DIR / "data" / "google_workspace_token.json"
LEGACY_GMAIL_TOKEN = BASE_DIR / "data" / "gmail_token.json"

# Combined scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
]

REDIRECT_URI = "https://ai.salem-home.com/google/callback"


def load_credentials() -> dict | None:
    """Load OAuth client credentials from gmail_credentials.json."""
    if not CREDENTIALS_FILE.exists():
        logger.error("gmail_credentials.json not found")
        return None
    data = json.loads(CREDENTIALS_FILE.read_text())
    return data.get("web") or data.get("installed")


def get_google_creds():
    """Get valid Google credentials with all required scopes.
    
    Returns Credentials object or None if token missing/invalid.
    Auto-refreshes expired tokens.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    creds = None

    # Try unified token first
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception as e:
            logger.warning(f"Failed to load workspace token: {e}")

    # Fallback to legacy gmail token (read-only, no calendar)
    if not creds and LEGACY_GMAIL_TOKEN.exists():
        try:
            creds = Credentials.from_authorized_user_file(
                str(LEGACY_GMAIL_TOKEN),
                ["https://www.googleapis.com/auth/gmail.readonly"]
            )
            logger.info("Using legacy gmail token (no calendar scope)")
        except Exception as e:
            logger.warning(f"Failed to load legacy gmail token: {e}")

    if not creds:
        return None

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Save refreshed token
            _save_token(creds)
            logger.info("Google token refreshed successfully")
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            return None

    if not creds.valid:
        logger.warning("Google credentials not valid")
        return None

    return creds


def has_calendar_scope() -> bool:
    """Check if current token has calendar scope."""
    if not TOKEN_FILE.exists():
        return False
    try:
        data = json.loads(TOKEN_FILE.read_text())
        scopes = data.get("scopes", [])
        return "https://www.googleapis.com/auth/calendar" in scopes
    except Exception:
        return False


def build_gmail_service():
    """Get authenticated Gmail API service."""
    creds = get_google_creds()
    if not creds:
        return None
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=creds)


def build_calendar_service():
    """Get authenticated Google Calendar API service."""
    creds = get_google_creds()
    if not creds:
        logger.warning("No valid Google credentials for Calendar")
        return None

    # Check if calendar scope is present
    if hasattr(creds, 'scopes') and creds.scopes:
        if "https://www.googleapis.com/auth/calendar" not in creds.scopes:
            logger.warning("Calendar scope missing — visit /google/auth to re-authenticate")
            return None

    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=creds)


def build_auth_url(state: str) -> str | None:
    """Build Google OAuth authorization URL with all scopes."""
    from urllib.parse import urlencode

    client = load_credentials()
    if not client:
        return None

    params = {
        "client_id": client["client_id"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)


async def exchange_code(code: str) -> dict | None:
    """Exchange authorization code for tokens."""
    import httpx

    client = load_credentials()
    if not client:
        return None

    async with httpx.AsyncClient(timeout=15) as http:
        resp = await http.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        token_data = resp.json()

    if "error" in token_data:
        logger.error(f"Token exchange error: {token_data}")
        return None

    # Save as Credentials format
    from google.oauth2.credentials import Credentials
    creds = Credentials(
        token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client["client_id"],
        client_secret=client["client_secret"],
        scopes=SCOPES,
    )
    _save_token(creds)

    return token_data


def _save_token(creds):
    """Save credentials to workspace token file."""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json())
    logger.info(f"Google workspace token saved to {TOKEN_FILE}")


def get_auth_status() -> dict:
    """Get current authentication status."""
    has_creds = CREDENTIALS_FILE.exists()
    has_workspace_token = TOKEN_FILE.exists()
    has_legacy_token = LEGACY_GMAIL_TOKEN.exists()
    has_cal = has_calendar_scope()

    status = "not_configured"
    if has_workspace_token and has_cal:
        status = "full"  # Gmail + Calendar
    elif has_workspace_token:
        status = "gmail_only_new"
    elif has_legacy_token:
        status = "gmail_only_legacy"

    return {
        "status": status,
        "credentials_file": has_creds,
        "workspace_token": has_workspace_token,
        "legacy_gmail_token": has_legacy_token,
        "calendar_scope": has_cal,
        "scopes_needed": SCOPES,
        "auth_url": "/google/auth",
    }
