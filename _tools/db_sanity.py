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

    # PHASE2_SECTION_D D-3: an open trade whose entry_date equals its
    # creation date may record the typing day, not the trade day.
    # created_at is UTC (D-11); entry/exit dates are Kuwait calendar
    # days, so the comparison localises (+3, no DST) first.
    # user_confirmed_at is the review that silences this (D-9) -
    # precision only says how well a date is known.
    try:
        _sus = conn.execute(
            "SELECT id, symbol, entry_date FROM trades WHERE status='open' "
            "AND entry_date = DATE(datetime(created_at, '+3 hours')) "
            "AND user_confirmed_at IS NULL"
        ).fetchall()
        _det = ", ".join("#%s %s %s" % (r[0], r[1], r[2]) for r in _sus)
        check("open trades entry_date vs created_at", len(_sus) == 0,
              ("suspect typed-date: " + _det) if _sus
              else "no open trade dated by its typing day")
    except Exception as _e:
        check("open trades entry_date vs created_at", False, str(_e))

    # PHASE2_SECTION_D D-7: a closed row created and exited the same day
    # is a candidate bookkeeping close, not a trade outcome
    try:
        _bk = conn.execute(
            "SELECT id, symbol, exit_date FROM trades WHERE status='closed' "
            "AND DATE(datetime(created_at, '+3 hours')) = exit_date "
            "AND COALESCE(trade_kind, 'real') != 'void' "
            "AND user_confirmed_at IS NULL"
        ).fetchall()
        _bd = ", ".join("#%s %s %s" % (r[0], r[1], r[2]) for r in _bk)
        check("closed trades bookkeeping candidates", len(_bk) == 0,
              ("candidate bookkeeping close: " + _bd) if _bk
              else "no same-day create-and-exit rows unmarked")
    except Exception as _e:
        check("closed trades bookkeeping candidates", False, str(_e))

    conn.close()

    print("=" * 60)
    total = PASS + FAIL
    print(f"Results: {PASS}/{total} passed, {FAIL} failed")
    print("=" * 60)
    return FAIL == 0


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
