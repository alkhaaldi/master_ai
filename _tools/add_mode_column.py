#!/usr/bin/env python3
"""Add mode column to confluence_signals table."""
import sqlite3
conn = sqlite3.connect("/var/lib/homeassistant/share/master_ai/data/life.db")
try:
    conn.execute("ALTER TABLE confluence_signals ADD COLUMN mode TEXT DEFAULT 'confirmation'")
    conn.commit()
    print("mode column added ✓")
except Exception as e:
    print(f"Column exists or error: {e}")
conn.close()
