"""
relationships_engine.py — Relationships + Occasions for Master AI v8 Phase 3
Single-file engine: DB schema, CRUD, lookup, calendar sync, TG formatting, occasion scheduler.

Tables in life.db:
  - contacts: people (name, relationship, aliases, birth_date)
  - occasions: events tied to people (birthday, anniversary, custom)
  - relationship_notes: facts/preferences about people

Design: minimal, practical, expandable later.
"""
import os
import re
import sqlite3
import logging
from datetime import datetime, date, timedelta
from pathlib import Path

logger = logging.getLogger("relationships")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")

# ═══════════════════════════════════════════════════
# DB SCHEMA + INIT
# ═══════════════════════════════════════════════════

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL UNIQUE,
    display_name TEXT,
    relationship_type TEXT,
    aliases TEXT DEFAULT '',
    birth_date TEXT,
    phone TEXT,
    email TEXT,
    notes TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS occasions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER,
    title TEXT NOT NULL,
    occasion_type TEXT NOT NULL DEFAULT 'custom',
    occasion_date TEXT NOT NULL,
    is_recurring INTEGER NOT NULL DEFAULT 1,
    reminder_days TEXT DEFAULT '7,1,0',
    calendar_event_id INTEGER,
    gift_hint TEXT,
    notes TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS relationship_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL,
    note_type TEXT NOT NULL DEFAULT 'fact',
    note_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(canonical_name);
CREATE INDEX IF NOT EXISTS idx_occasions_date ON occasions(occasion_date);
CREATE INDEX IF NOT EXISTS idx_occasions_contact ON occasions(contact_id);
CREATE INDEX IF NOT EXISTS idx_rel_notes_contact ON relationship_notes(contact_id);
"""


def _conn():
    """Get WAL-mode connection to life.db."""
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init_schema():
    """Create tables if not exist."""
    with _conn() as c:
        c.executescript(_SCHEMA_SQL)
    logger.info("relationships schema initialized")


# ═══════════════════════════════════════════════════
# CONTACTS CRUD
# ═══════════════════════════════════════════════════

def _normalize(name: str) -> str:
    """Normalize Arabic name for matching."""
    n = name.strip().lower()
    n = n.replace("\u0629", "\u0647")  # taa marbuta -> haa
    n = n.replace("\u0623", "\u0627").replace("\u0625", "\u0627").replace("\u0622", "\u0627")
    n = re.sub(r"\s+", " ", n)
    return n


def add_contact(canonical_name: str, display_name: str = None,
                relationship_type: str = None, aliases: list = None,
                birth_date: str = None, phone: str = None,
                email: str = None, notes: str = None) -> dict:
    """Add a new contact. Returns {ok, contact_id} or {ok:false, error}."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    alias_str = ",".join(aliases) if aliases else ""
    try:
        with _conn() as c:
            c.execute("""INSERT INTO contacts
                (canonical_name, display_name, relationship_type, aliases,
                 birth_date, phone, email, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (canonical_name, display_name or canonical_name,
                 relationship_type, alias_str, birth_date, phone, email,
                 notes, now, now))
            cid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        return {"ok": True, "contact_id": cid, "canonical_name": canonical_name}
    except sqlite3.IntegrityError:
        return {"ok": False, "error": f"'{canonical_name}' already exists"}


def update_contact(contact_id: int, **kwargs) -> dict:
    """Update contact fields. Pass only fields to change."""
    allowed = {"display_name", "relationship_type", "aliases", "birth_date",
               "phone", "email", "notes", "is_active"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return {"ok": False, "error": "nothing to update"}
    if "aliases" in updates and isinstance(updates["aliases"], list):
        updates["aliases"] = ",".join(updates["aliases"])
    updates["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k}=?" for k in updates)
    vals = list(updates.values()) + [contact_id]
    with _conn() as c:
        c.execute(f"UPDATE contacts SET {set_clause} WHERE id=?", vals)
    return {"ok": True, "contact_id": contact_id}


def get_contact(contact_id: int) -> dict | None:
    """Get contact by ID."""
    with _conn() as c:
        r = c.execute("SELECT * FROM contacts WHERE id=? AND is_active=1", (contact_id,)).fetchone()
    return dict(r) if r else None


def find_contact(name: str) -> dict | None:
    """Find contact by name or alias. Fuzzy Arabic matching."""
    norm = _normalize(name)
    with _conn() as c:
        r = c.execute("SELECT * FROM contacts WHERE is_active=1 AND canonical_name=?", (name,)).fetchone()
        if r:
            return dict(r)
        rows = c.execute("SELECT * FROM contacts WHERE is_active=1").fetchall()
    for row in rows:
        d = dict(row)
        targets = [d["canonical_name"], d.get("display_name") or ""]
        if d.get("aliases"):
            targets.extend(d["aliases"].split(","))
        for t in targets:
            if _normalize(t) == norm or norm in _normalize(t):
                return d
    return None


def list_contacts(limit: int = 50) -> list:
    """List all active contacts."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM contacts WHERE is_active=1 ORDER BY canonical_name LIMIT ?",
            (limit,)).fetchall()
    return [dict(r) for r in rows]


def search_contacts(query: str) -> list:
    """Search contacts by name/alias."""
    norm = _normalize(query)
    results = []
    for c in list_contacts(200):
        targets = [c["canonical_name"], c.get("display_name") or ""]
        if c.get("aliases"):
            targets.extend(c["aliases"].split(","))
        for t in targets:
            if norm in _normalize(t):
                results.append(c)
                break
    return results


# ═══════════════════════════════════════════════════
# OCCASIONS CRUD
# ═══════════════════════════════════════════════════

def add_occasion(title: str, occasion_date: str, occasion_type: str = "custom",
                 contact_id: int = None, is_recurring: bool = True,
                 reminder_days: str = "7,1,0", gift_hint: str = None,
                 notes: str = None) -> dict:
    """Add an occasion. occasion_date = YYYY-MM-DD."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        c.execute("""INSERT INTO occasions
            (contact_id, title, occasion_type, occasion_date, is_recurring,
             reminder_days, gift_hint, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (contact_id, title, occasion_type, occasion_date,
             1 if is_recurring else 0, reminder_days, gift_hint, notes, now, now))
        oid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"ok": True, "occasion_id": oid, "title": title}


def get_occasions_for_contact(contact_id: int) -> list:
    """Get all occasions for a contact."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM occasions WHERE contact_id=? AND is_active=1 ORDER BY occasion_date",
            (contact_id,)).fetchall()
    return [dict(r) for r in rows]


def get_today_occasions() -> list:
    """Get occasions for today (matching MM-DD for recurring)."""
    today = date.today()
    md = today.strftime("%m-%d")
    with _conn() as c:
        rows = c.execute("""
            SELECT o.*, c.display_name as contact_name, c.relationship_type
            FROM occasions o
            LEFT JOIN contacts c ON o.contact_id = c.id
            WHERE o.is_active=1 AND (
                o.occasion_date = ? OR
                (o.is_recurring=1 AND substr(o.occasion_date, 6) = ?)
            )
        """, (today.isoformat(), md)).fetchall()
    return [dict(r) for r in rows]


def get_upcoming_occasions(days: int = 30) -> list:
    """Get occasions in the next N days (handles recurring yearly)."""
    today = date.today()
    results = []
    with _conn() as c:
        rows = c.execute("""
            SELECT o.*, c.display_name as contact_name, c.relationship_type
            FROM occasions o
            LEFT JOIN contacts c ON o.contact_id = c.id
            WHERE o.is_active=1
        """).fetchall()
    for row in rows:
        d = dict(row)
        odate = d["occasion_date"]
        try:
            orig = date.fromisoformat(odate)
        except ValueError:
            continue
        if d["is_recurring"]:
            this_year = orig.replace(year=today.year)
            if this_year < today:
                this_year = orig.replace(year=today.year + 1)
            next_occ = this_year
        else:
            next_occ = orig
        delta = (next_occ - today).days
        if 0 <= delta <= days:
            d["next_date"] = next_occ.isoformat()
            d["days_away"] = delta
            results.append(d)
    results.sort(key=lambda x: x["days_away"])
    return results


def get_tomorrow_occasions() -> list:
    """Get occasions for tomorrow."""
    tomorrow = date.today() + timedelta(days=1)
    md = tomorrow.strftime("%m-%d")
    with _conn() as c:
        rows = c.execute("""
            SELECT o.*, c.display_name as contact_name, c.relationship_type
            FROM occasions o
            LEFT JOIN contacts c ON o.contact_id = c.id
            WHERE o.is_active=1 AND (
                o.occasion_date = ? OR
                (o.is_recurring=1 AND substr(o.occasion_date, 6) = ?)
            )
        """, (tomorrow.isoformat(), md)).fetchall()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════
# RELATIONSHIP NOTES
# ═══════════════════════════════════════════════════

def add_note(contact_id: int, note_text: str, note_type: str = "fact") -> dict:
    """Add a note about a person."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        c.execute("INSERT INTO relationship_notes (contact_id, note_type, note_text, created_at) VALUES (?,?,?,?)",
                  (contact_id, note_type, note_text, now))
        nid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"ok": True, "note_id": nid}


def get_notes(contact_id: int) -> list:
    """Get all notes for a contact."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM relationship_notes WHERE contact_id=? ORDER BY created_at DESC",
            (contact_id,)).fetchall()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════
# CONTACT SNAPSHOT (for LLM / TG)
# ═══════════════════════════════════════════════════

def build_contact_snapshot(name: str) -> dict | None:
    """Build complete snapshot: contact + occasions + notes."""
    contact = find_contact(name)
    if not contact:
        return None
    cid = contact["id"]
    occasions = get_occasions_for_contact(cid)
    notes = get_notes(cid)
    age = None
    if contact.get("birth_date"):
        try:
            bd = date.fromisoformat(contact["birth_date"])
            today = date.today()
            age_y = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
            age_m = (today.year - bd.year) * 12 + today.month - bd.month
            if age_y >= 1:
                age = f"{age_y} \u0633\u0646\u0629" if age_y > 1 else "\u0633\u0646\u0629"
            else:
                age = f"{age_m} \u0634\u0647\u0631"
        except ValueError:
            pass
    return {"contact": contact, "occasions": occasions, "notes": notes, "age": age}


# ═══════════════════════════════════════════════════
# TG FORMATTING
# ═══════════════════════════════════════════════════

_TYPE_EMOJI = {"birthday": "\U0001f382", "anniversary": "\U0001f492", "custom": "\U0001f4c5"}
_REL_EMOJI = {"wife": "\u2764\ufe0f", "husband": "\u2764\ufe0f", "son": "\U0001f466",
              "daughter": "\U0001f467", "mother": "\U0001f469", "father": "\U0001f468",
              "friend": "\U0001f91d", "coworker": "\U0001f4bc"}


def format_contacts_tg(contacts: list) -> str:
    if not contacts:
        return "\U0001f4d6 \u0645\u0627 \u0641\u064a\u0647 \u0623\u0634\u062e\u0627\u0635 \u0645\u0633\u062c\u0644\u064a\u0646"
    lines = ["\U0001f4d6 *\u0627\u0644\u0623\u0634\u062e\u0627\u0635 \u0627\u0644\u0645\u0633\u062c\u0644\u064a\u0646:*\n"]
    for c in contacts:
        emoji = _REL_EMOJI.get(c.get("relationship_type", ""), "\U0001f464")
        rel = c.get("relationship_type") or ""
        line = f"{emoji} *{c['display_name']}*"
        if rel:
            line += f" \u2014 {rel}"
        lines.append(line)
    return "\n".join(lines)


def format_upcoming_tg(occasions: list) -> str:
    if not occasions:
        return "\U0001f4c5 \u0644\u0627 \u062a\u0648\u062c\u062f \u0645\u0646\u0627\u0633\u0628\u0627\u062a \u0642\u0631\u064a\u0628\u0629"
    lines = ["\U0001f4c5 *\u0627\u0644\u0645\u0646\u0627\u0633\u0628\u0627\u062a \u0627\u0644\u0642\u0627\u062f\u0645\u0629:*\n"]
    for o in occasions:
        emoji = _TYPE_EMOJI.get(o.get("occasion_type", "custom"), "\U0001f4c5")
        days = o.get("days_away", 0)
        when = "*\u0627\u0644\u064a\u0648\u0645!*" if days == 0 else "*\u0628\u0627\u062c\u0631*" if days == 1 else f"\u0628\u0639\u062f {days} \u064a\u0648\u0645"
        lines.append(f"{emoji} {o['title']} \u2014 {o.get('next_date', o['occasion_date'])} ({when})")
    return "\n".join(lines)


def format_today_tg(occasions: list) -> str:
    if not occasions:
        return "\U0001f4c5 \u0644\u0627 \u062a\u0648\u062c\u062f \u0645\u0646\u0627\u0633\u0628\u0627\u062a \u0627\u0644\u064a\u0648\u0645"
    lines = ["\U0001f389 *\u0645\u0646\u0627\u0633\u0628\u0627\u062a \u0627\u0644\u064a\u0648\u0645:*\n"]
    for o in occasions:
        emoji = _TYPE_EMOJI.get(o.get("occasion_type", "custom"), "\U0001f4c5")
        lines.append(f"{emoji} {o['title']}")
    return "\n".join(lines)


def format_person_tg(snapshot: dict) -> str:
    c = snapshot["contact"]
    emoji = _REL_EMOJI.get(c.get("relationship_type", ""), "\U0001f464")
    lines = [f"{emoji} *{c['display_name']}*"]
    if c.get("relationship_type"):
        lines.append(f"\U0001f4cc \u0627\u0644\u0639\u0644\u0627\u0642\u0629: {c['relationship_type']}")
    if snapshot.get("age"):
        lines.append(f"\U0001f382 \u0627\u0644\u0639\u0645\u0631: {snapshot['age']}")
    if c.get("birth_date"):
        lines.append(f"\U0001f4c5 \u0627\u0644\u0645\u064a\u0644\u0627\u062f: {c['birth_date']}")
    if c.get("aliases"):
        lines.append(f"\U0001f50d \u0623\u0633\u0645\u0627\u0621 \u062b\u0627\u0646\u064a\u0629: {c['aliases']}")
    if snapshot["occasions"]:
        lines.append("\n\U0001f4c5 *\u0627\u0644\u0645\u0646\u0627\u0633\u0628\u0627\u062a:*")
        for o in snapshot["occasions"]:
            em = _TYPE_EMOJI.get(o.get("occasion_type", ""), "\U0001f4c5")
            lines.append(f"  {em} {o['title']} \u2014 {o['occasion_date']}")
    if snapshot["notes"]:
        lines.append("\n\U0001f4dd *\u0645\u0644\u0627\u062d\u0638\u0627\u062a:*")
        for n in snapshot["notes"][:5]:
            lines.append(f"  \u2022 {n['note_text']}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════
# MORNING REPORT INTEGRATION
# ═══════════════════════════════════════════════════

def get_morning_occasions_text() -> str:
    today_occ = get_today_occasions()
    upcoming = [o for o in get_upcoming_occasions(7) if o.get("days_away", 0) > 0]
    parts = []
    if today_occ:
        parts.append(f"\U0001f389 \u0645\u0646\u0627\u0633\u0628\u0627\u062a \u0627\u0644\u064a\u0648\u0645: {', '.join(o['title'] for o in today_occ)}")
    if upcoming:
        cl = upcoming[0]
        parts.append(f"\U0001f4c5 \u0623\u0642\u0631\u0628 \u0645\u0646\u0627\u0633\u0628\u0629: {cl['title']} \u0628\u0639\u062f {cl['days_away']} \u064a\u0648\u0645")
    return "\n".join(parts) if parts else ""


# ═══════════════════════════════════════════════════
# SEED DATA FROM family_assistant.py
# ═══════════════════════════════════════════════════

_SEED_DATA = [
    {"canonical_name": "\u0623\u0648\u0627\u0646\u0627", "display_name": "\u0623\u0648\u0627\u0646\u0627",
     "relationship_type": "wife", "aliases": "\u0632\u0648\u062c\u062a\u064a,\u0623\u0645 \u0639\u0628\u0648\u062f,\u0627\u0644\u062d\u0631\u0645\u0629,Oana"},
    {"canonical_name": "\u0639\u0628\u062f\u0627\u0644\u0644\u0647", "display_name": "\u0639\u0628\u0648\u062f",
     "relationship_type": "son", "aliases": "\u0639\u0628\u0648\u062f,\u0639\u0628\u0648\u062f\u064a,\u0627\u0644\u0648\u0644\u062f,\u0648\u0644\u062f\u064a,Abdullah",
     "birth_date": "2026-02-04"},
    {"canonical_name": "\u0639\u0627\u0626\u0634\u0629", "display_name": "\u0639\u064a\u0648\u0634\u0629",
     "relationship_type": "daughter", "aliases": "\u0639\u064a\u0648\u0634\u0629,\u0627\u0644\u0628\u0646\u062a,\u0628\u0646\u062a\u064a,Aisha"},
    {"canonical_name": "\u0646\u0627\u0647\u062f", "display_name": "\u0623\u0645 \u0633\u0627\u0644\u0645",
     "relationship_type": "mother", "aliases": "\u0623\u0645\u064a,\u0627\u0644\u0648\u0627\u0644\u062f\u0629,\u0623\u0645 \u0633\u0627\u0644\u0645,\u0645\u0627\u0645\u0627"},
]


def seed_family_data():
    """Seed family data from family_assistant.py. Idempotent."""
    count = 0
    for p in _SEED_DATA:
        if find_contact(p["canonical_name"]):
            continue
        result = add_contact(
            canonical_name=p["canonical_name"],
            display_name=p.get("display_name"),
            relationship_type=p.get("relationship_type"),
            aliases=p.get("aliases", "").split(",") if isinstance(p.get("aliases"), str) else p.get("aliases"),
            birth_date=p.get("birth_date"),
        )
        if result.get("ok"):
            count += 1
            if p.get("birth_date"):
                add_occasion(
                    title=f"\u0639\u064a\u062f \u0645\u064a\u0644\u0627\u062f {p.get('display_name', p['canonical_name'])}",
                    occasion_date=p["birth_date"],
                    occasion_type="birthday",
                    contact_id=result["contact_id"],
                    is_recurring=True,
                )
    if count:
        logger.info(f"Seeded {count} family contacts")
    return count


# ═══════════════════════════════════════════════════
# QUICK QUERY HANDLERS (zero-LLM)
# ═══════════════════════════════════════════════════

def handle_occasions_upcoming() -> str:
    return format_upcoming_tg(get_upcoming_occasions(30))

def handle_occasions_today() -> str:
    return format_today_tg(get_today_occasions())

def handle_occasions_tomorrow() -> str:
    occ = get_tomorrow_occasions()
    if not occ:
        return "\U0001f4c5 \u0644\u0627 \u062a\u0648\u062c\u062f \u0645\u0646\u0627\u0633\u0628\u0627\u062a \u0628\u0627\u062c\u0631"
    lines = ["\U0001f4c5 *\u0645\u0646\u0627\u0633\u0628\u0627\u062a \u0628\u0627\u062c\u0631:*\n"]
    for o in occ:
        emoji = _TYPE_EMOJI.get(o.get("occasion_type", ""), "\U0001f4c5")
        lines.append(f"{emoji} {o['title']}")
    return "\n".join(lines)

def handle_birthday_lookup(name: str) -> str:
    contact = find_contact(name)
    if not contact:
        return f"\u274c \u0645\u0627 \u0644\u0642\u064a\u062a '{name}' \u0628\u0627\u0644\u0623\u0634\u062e\u0627\u0635"
    if not contact.get("birth_date"):
        return f"\U0001f464 {contact['display_name']} \u2014 \u0645\u0627 \u0639\u0646\u062f\u064a \u062a\u0627\u0631\u064a\u062e \u0645\u064a\u0644\u0627\u062f"
    bd = date.fromisoformat(contact["birth_date"])
    today = date.today()
    this_year = bd.replace(year=today.year)
    if this_year < today:
        this_year = bd.replace(year=today.year + 1)
    days_away = (this_year - today).days
    when = "*\u0627\u0644\u064a\u0648\u0645!* \U0001f389" if days_away == 0 else "*\u0628\u0627\u062c\u0631!*" if days_away == 1 else f"\u0628\u0639\u062f {days_away} \u064a\u0648\u0645"
    return f"\U0001f382 \u0639\u064a\u062f \u0645\u064a\u0644\u0627\u062f {contact['display_name']}: {contact['birth_date']} ({when})"
