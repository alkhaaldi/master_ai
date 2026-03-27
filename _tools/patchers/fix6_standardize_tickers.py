#!/usr/bin/env python3
"""Fix 6: Standardize tickers to English in trades table."""
import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), "..", "..", "data", "life.db")
conn = sqlite3.connect(DB, timeout=10)
conn.row_factory = sqlite3.Row

# Arabic to English ticker map
ARABIC_TO_ENGLISH = {
    "تنظيف": "CLEANING",
    "سنرجي": "SENERGY",
    "اينوفست": "INOVEST",
    "زين": "ZAIN",
    "بيتك": "KFH",
}

# Check current state
rows = conn.execute("SELECT id, symbol FROM trades").fetchall()
fixed = 0
for r in rows:
    sym = r["symbol"]
    if sym in ARABIC_TO_ENGLISH:
        new_sym = ARABIC_TO_ENGLISH[sym]
        conn.execute("UPDATE trades SET symbol=? WHERE id=?", (new_sym, r["id"]))
        print(f"  #{r['id']}: {sym} -> {new_sym}")
        fixed += 1

conn.commit()
conn.close()
print(f"Fix6: standardized {fixed} tickers")
