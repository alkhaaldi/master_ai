#!/usr/bin/env python3
"""
db_sanity.py — Check stock_radar tables in life.db.
Run: python3 _tools/db_sanity.py
"""
import sqlite3, os, sys, json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIFE_DB = os.path.join(BASE_DIR, "data", "life.db")

PASS = 0
FAIL = 0

TABLES = [
    "stock_radar_events",
    "stock_radar_daily",
    "stock_radar_watchlist",
    "stock_radar_state",
]

def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
    status = "PASS" if ok else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")


def main():
    print("=" * 60)
    print("DB Sanity — life.db radar tables")
    print("=" * 60)

    if not os.path.exists(LIFE_DB):
        print(f"\n  [FAIL] life.db not found at {LIFE_DB}")
        sys.exit(1)

    conn = sqlite3.connect(LIFE_DB)
    conn.row_factory = sqlite3.Row

    # Get existing tables
    existing = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    print()
    for table in TABLES:
        if table not in existing:
            check(table, False, "TABLE NOT FOUND")
            continue

        # Count
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        check(f"{table} exists", True, f"rows={count}")

        # Last 3 rows
        try:
            cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT 3").fetchall()
            if rows:
                print(f"    Last {len(rows)} rows:")
                for row in rows:
                    row_dict = dict(row)
                    # Truncate long values
                    for k, v in row_dict.items():
                        if isinstance(v, str) and len(v) > 80:
                            row_dict[k] = v[:77] + "..."
                    print(f"      {json.dumps(row_dict, ensure_ascii=False, default=str)}")
            else:
                print(f"    (empty)")
        except Exception as e:
            print(f"    Error reading rows: {e}")

        # Check for critical nulls
        try:
            for col in cols:
                null_count = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL"
                ).fetchone()[0]
                if null_count > 0 and count > 0:
                    pct = null_count * 100 / count
                    if pct > 50:
                        check(f"  {table}.{col} nulls", False, f"{null_count}/{count} ({pct:.0f}%) NULL")
        except Exception:
            pass

        print()

    conn.close()

    print("=" * 60)
    total = PASS + FAIL
    print(f"Results: {PASS}/{total} passed, {FAIL} failed")
    print("=" * 60)
    return FAIL == 0


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
