"""Email Summary Module — Gmail + Outlook/365 support for Telegram bot."""
import os, json, logging, base64, re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime

logger = logging.getLogger("tg_email")
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# ===== Gmail via Google API =====

_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
_GMAIL_CREDS_FILE = BASE_DIR / "gmail_credentials.json"
_GMAIL_TOKEN_FILE = DATA_DIR / "gmail_token.json"

# Labels to skip (promotions, social, spam)
_SKIP_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "SPAM", "TRASH", "CATEGORY_FORUMS"}

# Priority senders (always show)
_PRIORITY_SENDERS = {"knpc", "kipic", "petrochemical", "maximo", "sap"}


def _gmail_service():
    """Get authenticated Gmail API service."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if _GMAIL_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(_GMAIL_TOKEN_FILE), _GMAIL_SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif _GMAIL_CREDS_FILE.exists():
            flow = InstalledAppFlow.from_client_secrets_file(str(_GMAIL_CREDS_FILE), _GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        else:
            return None
        _GMAIL_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _GMAIL_TOKEN_FILE.write_text(creds.to_json())
    
    return build("gmail", "v1", credentials=creds)


def _is_important(msg):
    """Check if email is important (not promotions/social/spam)."""
    labels = set(msg.get("labelIds", []))
    # Skip promotional/social/spam
    if labels & _SKIP_LABELS:
        return False
    # Always include if IMPORTANT label
    if "IMPORTANT" in labels:
        return True
    # Include INBOX primary
    if "INBOX" in labels and "CATEGORY_UPDATES" in labels:
        return True
    if "INBOX" in labels and not (labels & _SKIP_LABELS):
        return True
    return False


def _is_priority_sender(from_addr):
    """Check if sender is a priority contact."""
    from_lower = from_addr.lower()
    return any(p in from_lower for p in _PRIORITY_SENDERS)


def _extract_sender(from_header):
    """Extract clean sender name from From header."""
    # "Name <email>" -> "Name"
    match = re.match(r'"?([^"<]+)"?\s*<', from_header)
    if match:
        return match.group(1).strip()
    return from_header.split("<")[0].strip() or from_header


def _extract_subject_ar(subject):
    """Clean up subject line."""
    # Remove Re:/Fwd: prefixes
    subject = re.sub(r'^(Re|Fwd|FW|RE):\s*', '', subject).strip()
    return subject[:80] if subject else "(\u0628\u062f\u0648\u0646 \u0639\u0646\u0648\u0627\u0646)"


async def get_gmail_summary(hours=24, limit=10):
    """Get summary of important Gmail messages."""
    try:
        service = _gmail_service()
        if not service:
            return None, "\u26a0\ufe0f Gmail \u063a\u064a\u0631 \u0645\u0631\u0628\u0648\u0637 - \u064a\u062d\u062a\u0627\u062c \u0625\u0639\u062f\u0627\u062f OAuth"
        
        # Search for recent messages
        after_ts = int((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp())
        query = f"after:{after_ts} in:inbox"
        
        results = service.users().messages().list(
            userId="me", q=query, maxResults=50
        ).execute()
        
        messages = results.get("messages", [])
        if not messages:
            return [], "\u2705 \u0644\u0627 \u0625\u064a\u0645\u064a\u0644\u0627\u062a \u062c\u062f\u064a\u062f\u0629"
        
        # Fetch message details
        important = []
        for msg_ref in messages:
            msg = service.users().messages().get(
                userId="me", id=msg_ref["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
            ).execute()
            
            if not _is_important(msg):
                continue
            
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            from_addr = headers.get("From", "?")
            sender = _extract_sender(from_addr)
            subject = _extract_subject_ar(headers.get("Subject", ""))
            is_unread = "UNREAD" in msg.get("labelIds", [])
            is_priority = _is_priority_sender(from_addr)
            
            important.append({
                "id": msg["id"],
                "sender": sender,
                "subject": subject,
                "snippet": msg.get("snippet", "")[:100],
                "unread": is_unread,
                "priority": is_priority,
                "date": headers.get("Date", ""),
                "source": "gmail",
            })
            
            if len(important) >= limit:
                break
        
        return important, None
    except Exception as e:
        logger.error(f"Gmail error: {e}")
        return None, f"\u26a0\ufe0f Gmail: {str(e)[:60]}"


# ===== Outlook/365 via Microsoft Graph =====

_MS_CONFIG_FILE = BASE_DIR / "outlook_config.json"
_MS_TOKEN_FILE = DATA_DIR / "outlook_token.json"


async def get_outlook_summary(hours=24, limit=10):
    """Get summary of important Outlook/365 messages."""
    try:
        import msal
        import httpx
        
        if not _MS_CONFIG_FILE.exists():
            return None, "\u26a0\ufe0f Outlook \u063a\u064a\u0631 \u0645\u0631\u0628\u0648\u0637 - \u064a\u062d\u062a\u0627\u062c \u0625\u0639\u062f\u0627\u062f"
        
        config = json.loads(_MS_CONFIG_FILE.read_text())
        client_id = config.get("client_id", "")
        tenant_id = config.get("tenant_id", "")
        client_secret = config.get("client_secret", "")
        user_email = config.get("user_email", "")
        
        if not all([client_id, tenant_id, client_secret, user_email]):
            return None, "\u26a0\ufe0f Outlook config \u0646\u0627\u0642\u0635"
        
        # Get token via client credentials flow
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id, authority=authority, client_credential=client_secret
        )
        
        # Try cached token first
        token_data = None
        if _MS_TOKEN_FILE.exists():
            try:
                cached = json.loads(_MS_TOKEN_FILE.read_text())
                if cached.get("expires_at", 0) > datetime.now(timezone.utc).timestamp():
                    token_data = cached
            except Exception:
                pass
        
        if not token_data:
            result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
            if "access_token" not in result:
                return None, f"\u26a0\ufe0f Outlook auth: {result.get('error_description', '?')[:60]}"
            token_data = {
                "access_token": result["access_token"],
                "expires_at": datetime.now(timezone.utc).timestamp() + result.get("expires_in", 3600)
            }
            _MS_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            _MS_TOKEN_FILE.write_text(json.dumps(token_data))
        
        # Fetch recent messages from Graph API
        after_dt = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"https://graph.microsoft.com/v1.0/users/{user_email}/messages",
                headers={"Authorization": f"Bearer {token_data['access_token']}"},
                params={
                    "$top": str(limit),
                    "$orderby": "receivedDateTime desc",
                    "$filter": f"receivedDateTime ge {after_dt}",
                    "$select": "id,subject,from,receivedDateTime,isRead,importance,bodyPreview",
                }
            )
            
            if r.status_code != 200:
                return None, f"\u26a0\ufe0f Outlook API: {r.status_code}"
            
            data = r.json()
            messages = data.get("value", [])
        
        important = []
        for msg in messages:
            sender_data = msg.get("from", {}).get("emailAddress", {})
            sender = sender_data.get("name", sender_data.get("address", "?"))
            subject = _extract_subject_ar(msg.get("subject", ""))
            
            important.append({
                "id": msg["id"],
                "sender": sender,
                "subject": subject,
                "snippet": msg.get("bodyPreview", "")[:100],
                "unread": not msg.get("isRead", True),
                "priority": msg.get("importance", "") == "high",
                "date": msg.get("receivedDateTime", ""),
                "source": "outlook",
            })
        
        return important, None
    except Exception as e:
        logger.error(f"Outlook error: {e}")
        return None, f"\u26a0\ufe0f Outlook: {str(e)[:60]}"


# ===== Combined Email Summary =====

async def get_email_summary(hours=24, limit=10):
    """Get combined email summary from all connected accounts."""
    all_emails = []
    errors = []
    
    # Gmail
    gmail_msgs, gmail_err = await get_gmail_summary(hours, limit)
    if gmail_msgs:
        all_emails.extend(gmail_msgs)
    if gmail_err and not gmail_msgs:
        errors.append(gmail_err)
    
    # Outlook
    outlook_msgs, outlook_err = await get_outlook_summary(hours, limit)
    if outlook_msgs:
        all_emails.extend(outlook_msgs)
    if outlook_err and not outlook_msgs:
        errors.append(outlook_err)
    
    return all_emails, errors


async def format_email_report(hours=24, limit=10):
    """Format email summary for Telegram."""
    emails, errors = await get_email_summary(hours, limit)
    
    lines = [f"\U0001f4e7 \u0645\u0644\u062e\u0635 \u0627\u0644\u0625\u064a\u0645\u064a\u0644 (\u0622\u062e\u0631 {hours} \u0633\u0627\u0639\u0629):", ""]
    
    if not emails and not errors:
        lines.append("\u2705 \u0644\u0627 \u0625\u064a\u0645\u064a\u0644\u0627\u062a \u062c\u062f\u064a\u062f\u0629")
        return chr(10).join(lines)
    
    # Show errors first
    for err in errors:
        lines.append(err)
    if errors:
        lines.append("")
    
    if emails:
        # Sort: priority first, then unread, then date
        emails.sort(key=lambda e: (not e["priority"], not e["unread"]))
        
        # Group by source
        gmail_msgs = [e for e in emails if e["source"] == "gmail"]
        outlook_msgs = [e for e in emails if e["source"] == "outlook"]
        
        if gmail_msgs:
            unread_count = sum(1 for e in gmail_msgs if e["unread"])
            lines.append(f"\U0001f4e8 Gmail ({len(gmail_msgs)} \u0645\u0647\u0645, {unread_count} \u063a\u064a\u0631 \u0645\u0642\u0631\u0648\u0621):")
            for e in gmail_msgs[:limit]:
                icon = "\U0001f534" if e["priority"] else ("\U0001f535" if e["unread"] else "\u26aa")
                lines.append(f"  {icon} {e['sender'][:20]}")
                lines.append(f"     {e['subject'][:55]}")
            lines.append("")
        
        if outlook_msgs:
            unread_count = sum(1 for e in outlook_msgs if e["unread"])
            lines.append(f"\U0001f3e2 KNPC ({len(outlook_msgs)}, {unread_count} \u063a\u064a\u0631 \u0645\u0642\u0631\u0648\u0621):")
            for e in outlook_msgs[:limit]:
                icon = "\U0001f534" if e["priority"] else ("\U0001f535" if e["unread"] else "\u26aa")
                lines.append(f"  {icon} {e['sender'][:20]}")
                lines.append(f"     {e['subject'][:55]}")
    
    return chr(10).join(lines)


async def get_email_for_morning():
    """Short email summary for morning report."""
    emails, errors = await get_email_summary(hours=12, limit=5)
    
    if not emails:
        if errors:
            return errors[0]
        return "\u2705 \u0644\u0627 \u0625\u064a\u0645\u064a\u0644\u0627\u062a \u062c\u062f\u064a\u062f\u0629"
    
    unread = sum(1 for e in emails if e["unread"])
    priority = sum(1 for e in emails if e["priority"])
    
    lines = [f"{len(emails)} \u0625\u064a\u0645\u064a\u0644 \u0645\u0647\u0645 ({unread} \u063a\u064a\u0631 \u0645\u0642\u0631\u0648\u0621)"]
    if priority:
        lines[0] += f" \U0001f534{priority} \u0639\u0627\u062c\u0644"
    
    # Show top 3
    for e in emails[:3]:
        icon = "\U0001f534" if e["priority"] else "\U0001f535"
        src = "\U0001f3e2" if e["source"] == "outlook" else ""
        lines.append(f"  {icon}{src} {e['sender'][:15]}: {e['subject'][:40]}")
    
    return chr(10).join(lines)
