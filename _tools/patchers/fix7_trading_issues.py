#!/usr/bin/env python3
"""Fix 7 trading issues in one script."""
import sqlite3
import os
import json

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(BASE, "..", "..")
LIFE_DB = os.path.join(ROOT, "data", "life.db")

print("=" * 50)
print("FIX 1: Correct trade data in life.db trades")
print("=" * 50)

conn = sqlite3.connect(LIFE_DB, timeout=10)
conn.row_factory = sqlite3.Row

# Fix the CLEANING trade: entry_price=792 should be 132 fils, quantity=0 should be 792
# User said "ألف سهم بسعر 131" — but actual entry was "تنظيف 792" which put 792 as price
# TV alert shows price was 0.285 KWD = 285 fils. But entry_reason says "بسعر 131"
# The 792 is quantity, 131-132 is the price
row = conn.execute("SELECT * FROM trades WHERE id=1").fetchone()
if row:
    print(f"  BEFORE: symbol={row['symbol']} entry_price={row['entry_price']} quantity={row['quantity']}")
    conn.execute("UPDATE trades SET entry_price=132, quantity=792 WHERE id=1")
    conn.commit()
    row2 = conn.execute("SELECT * FROM trades WHERE id=1").fetchone()
    print(f"  AFTER:  symbol={row2['symbol']} entry_price={row2['entry_price']} quantity={row2['quantity']}")
    print("  OK: Trade #1 fixed")
else:
    print("  SKIP: Trade #1 not found")

print()
print("=" * 50)
print("FIX 6: Check price normalization in stock_radar_events")
print("=" * 50)

low_prices = conn.execute(
    "SELECT symbol, price FROM stock_radar_events WHERE price < 10 ORDER BY price"
).fetchall()
if low_prices:
    print(f"  Found {len(low_prices)} events with price < 10:")
    for r in low_prices:
        print(f"    {r['symbol']}: {r['price']}")
    # Only normalize if price < 1 (clearly KWD not fils)
    affected = conn.execute(
        "UPDATE stock_radar_events SET price = price * 1000 WHERE price < 1"
    ).rowcount
    conn.commit()
    print(f"  Normalized {affected} prices (< 1 KWD -> fils)")
else:
    print("  OK: No prices < 10 — all already in fils")

print()
print("=" * 50)
print("FIX 7: Clean up duplicate trade_journal table")
print("=" * 50)

# trade_journal is the old/legacy table. journal_engine.py uses "trades".
try:
    jcount = conn.execute("SELECT COUNT(*) FROM trade_journal").fetchone()[0]
    print(f"  trade_journal has {jcount} rows (legacy table)")
    if jcount > 0:
        conn.execute("DELETE FROM trade_journal")
        conn.commit()
        print(f"  Cleaned {jcount} rows from trade_journal (legacy, not used by journal_engine)")
    print("  OK: trades is the official table (journal_engine.py)")
except Exception as e:
    print(f"  SKIP: {e}")

# Check audit.db trades table
AUDIT_DB = os.path.join(ROOT, "data", "audit.db")
try:
    ac = sqlite3.connect(AUDIT_DB, timeout=5)
    audit_count = ac.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    print(f"  audit.db trades: {audit_count} rows")
    if audit_count > 0:
        ac.execute("DELETE FROM trades")
        ac.commit()
        print(f"  Cleaned {audit_count} rows from audit.db trades (not used)")
    ac.close()
except Exception as e:
    print(f"  audit.db: {e}")

conn.close()
print()
print("ALL DB FIXES DONE")
