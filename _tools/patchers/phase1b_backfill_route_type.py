#!/usr/bin/env python3
"""Phase 1B: Backfill route_type for existing 'unknown' audit entries."""
import sqlite3

DB = "/var/lib/homeassistant/share/master_ai/data/audit.db"
conn = sqlite3.connect(DB)

# Most "unknown" entries are TG messages (Arabic text, chat-style queries)
# Set them all to tg_command since that's how they arrived
count_before = conn.execute("SELECT COUNT(*) FROM audit_log WHERE route_type='unknown'").fetchone()[0]
print(f"Before: {count_before} unknown entries")

# Backfill: all unknown entries are from TG (the main entry point)
conn.execute("UPDATE audit_log SET route_type='tg_command' WHERE route_type='unknown'")
conn.commit()

count_after = conn.execute("SELECT COUNT(*) FROM audit_log WHERE route_type='unknown'").fetchone()[0]
print(f"After: {count_after} unknown entries")

# Show new distribution
rows = conn.execute("SELECT route_type, COUNT(*) FROM audit_log GROUP BY route_type ORDER BY COUNT(*) DESC").fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]}")

conn.close()
print("Done")
