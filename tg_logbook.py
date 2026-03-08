"""Log Book Analyzer — Unit 114 E-Log Book PDF analysis via LLM."""
import os, json, logging, base64, re
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("tg_logbook")
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
_GMAIL_CREDS_FILE = BASE_DIR / "gmail_credentials.json"
_GMAIL_TOKEN_FILE = DATA_DIR / "gmail_token.json"

_LOGBOOK_PATTERNS = [
    r"log\s*book",
    r"e-?log",
    r"unit.?114.*controller",
    r"controller.*logbook",
]


def _is_logbook_email(subject, snippet=""):
    text = f"{subject} {snippet}".lower()
    return any(re.search(p, text) for p in _LOGBOOK_PATTERNS)


def _gmail_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = None
    if _GMAIL_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(_GMAIL_TOKEN_FILE), _GMAIL_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _GMAIL_TOKEN_FILE.write_text(creds.to_json())
        else:
            return None
    return build("gmail", "v1", credentials=creds)


async def find_latest_logbook(hours=48):
    """Find the latest log book email with PDF attachment."""
    try:
        service = _gmail_service()
        if not service:
            return None, "Gmail not connected"
        after_ts = int((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp())
        query = f"after:{after_ts} (log book OR logbook OR e-log) unit 114"
        results = service.users().messages().list(userId="me", q=query, maxResults=10).execute()
        messages = results.get("messages", [])
        if not messages:
            query2 = f"after:{after_ts} log book"
            results = service.users().messages().list(userId="me", q=query2, maxResults=10).execute()
            messages = results.get("messages", [])
        for msg_ref in messages:
            msg = service.users().messages().get(userId="me", id=msg_ref["id"], format="full").execute()
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            subject = headers.get("Subject", "")
            if not _is_logbook_email(subject, msg.get("snippet", "")):
                continue
            parts = msg.get("payload", {}).get("parts", [])
            for part in parts:
                filename = part.get("filename", "")
                mime = part.get("mimeType", "")
                if filename.lower().endswith(".pdf") or mime == "application/pdf":
                    att_id = part.get("body", {}).get("attachmentId")
                    if att_id:
                        return {"msg_id": msg_ref["id"], "subject": subject,
                                "sender": headers.get("From", ""), "date": headers.get("Date", ""),
                                "filename": filename, "attachment_id": att_id}, None
        return None, "No log book found in last 48h"
    except Exception as e:
        logger.error(f"Find logbook error: {e}")
        return None, str(e)


async def download_logbook_pdf(msg_id, attachment_id):
    """Download PDF attachment from Gmail."""
    try:
        service = _gmail_service()
        if not service:
            return None
        att = service.users().messages().attachments().get(
            userId="me", messageId=msg_id, id=attachment_id).execute()
        data = att.get("data", "")
        if not data:
            return None
        return base64.urlsafe_b64decode(data)
    except Exception as e:
        logger.error(f"Download PDF error: {e}")
        return None


async def analyze_logbook(pdf_bytes):
    """Send PDF to Claude for analysis and get structured summary."""
    try:
        import httpx
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return None, "No API key"
        pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()
        prompt = """You are analyzing a KNPC Unit 114 Hydrocracker Controller E-Log Book PDF.
Extract and respond in Arabic (Kuwaiti dialect OK). Be concise:

1. DATE/SHIFT: Date, Shift, Controller name
2. KEY READINGS: STG1 Feed Rate (USGPM+KBPSD), UCO bleed %, Unit Conversion %
3. REACTOR TEMPS: TOTAL WABT for V-119/120/121, flag any bed peak >740F
4. YIELDS: Diesel/ATK/Conversion %
5. QUALITY: ATK Flash Point (flag <110F), ATK Freeze Point (flag > -47C), LT Naphtha RVP
6. CHEMICALS: Any pump NOT running, any stock=0
7. COMMENTS: List ALL comments translated to Arabic - THIS IS MOST IMPORTANT
8. HANDOVER: Who to whom, Maximo status
9. ALERTS: Generate warnings for abnormal readings

Use emoji headers. Max 2000 chars. Telegram-friendly (no markdown)."""

        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "content-type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2500,
                    "messages": [{"role": "user", "content": [
                        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                        {"type": "text", "text": prompt}
                    ]}],
                    "temperature": 0.1,
                }
            )
            if r.status_code != 200:
                logger.error(f"Anthropic API error: {r.status_code}")
                return None, f"API error {r.status_code}"
            text = r.json().get("content", [{}])[0].get("text", "")
            return text, None
    except Exception as e:
        logger.error(f"Analyze logbook error: {e}")
        return None, str(e)


async def get_logbook_report(hours=48):
    """Full pipeline: find > download > analyze > format."""
    info, err = await find_latest_logbook(hours)
    if not info:
        sep = chr(0x2501) * 24
        return f"\U0001f4d3 \u0644\u0648\u0642 \u0628\u0648\u0643 114\n{sep}\n\u274c {err or 'not found'}"
    pdf_bytes = await download_logbook_pdf(info["msg_id"], info["attachment_id"])
    if not pdf_bytes:
        sep = chr(0x2501) * 24
        return f"\U0001f4d3 \u0644\u0648\u0642 \u0628\u0648\u0643 114\n{sep}\n\u274c PDF download failed"
    analysis, err = await analyze_logbook(pdf_bytes)
    if not analysis:
        sep = chr(0x2501) * 24
        return f"\U0001f4d3 \u0644\u0648\u0642 \u0628\u0648\u0643 114\n{sep}\n\u274c {err}"
    sep = chr(0x2501) * 24
    header = f"\U0001f4d3 \u0644\u0648\u0642 \u0628\u0648\u0643 \u064a\u0648\u0646\u062a 114\n{sep}\n"
    header += f"\U0001f4ce {info['filename']}\n{sep}\n\n"
    return header + analysis
