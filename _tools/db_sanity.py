#!/usr/bin/env python3
"""
db_sanity.py — Check stock_radar tables in life.db.
Run: python3 _tools/db_sanity.py
"""
import sqlite3, os, sys, json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The path is overridable so this file can be aimed at a doctored COPY of
# the database. _tools/prove_guards.py uses it to drive every check below
# into its failing state without touching a byte of production data - which
# is the only way to know the checks can go red at all.
LIFE_DB = os.environ.get("DB_SANITY_DB") or os.path.join(BASE_DIR, "data", "life.db")

PASS = 0
FAIL = 0

TABLES = [
    "stock_radar_events",
    "stock_radar_daily",
    "stock_radar_watchlist",
    "stock_radar_state",
]

# Declared null expectations, added 2026-08-17.
#
# What was here before could not change colour. `{table} exists` was called
# with a literal True, so it was green whatever happened; the null checks
# were called with a literal False AND only reached when a column was more
# than half empty, so they were red when they appeared and simply vanished
# when the data was healthy - there was no way to tell "this column is fine"
# from "this column was never looked at". Seven of nine checks were fixed in
# advance. A guard that cannot change colour carries no information.
#
# Now every entry below is asserted on every run and prints its verdict
# either way. `max_null_pct` is the claim being made about the column; to
# add one, state the number you expect and why, not the number you observe.
NULL_EXPECTATIONS = [
    # (table, column, max_null_pct, why this number)
    ("stock_radar_daily", "price", 0.0,
     "a radar row without a price is not a row"),
    ("stock_radar_daily", "captured_at", 0.0,
     "a number whose date we lost is worse than no number"),
    ("stock_radar_daily", "rsi_divergence", 10.0,
     "computed locally by indicators.rsi_divergence since 2026-08-17; NULL "
     "only where the bars cannot answer (too few, or no pivot pair), which "
     "measured 2 of 132 on the day it was filled"),
]

# Columns deliberately NOT checked, and why. Kept in the file rather than
# deleted from it, so the next reader finds the reasoning instead of the
# absence.
NULL_CHECKS_RETIRED = [
    ("stock_radar_state", "prev_ema_fast prev_ema_slow",
     "30m-layer state. Both columns are 100% NULL across all 60 rows and the "
     "table has not been written since 2026-03-25 - the layer is offline, "
     "not the columns broken. This check was measuring the absence of the "
     "30m layer, which OPEN_ITEMS item 5 already tracks under a name that "
     "says so ('layer_state: offline, layer_rebuildable: true'). Two guards "
     "for one fact, and this one was stuck red, so it carried nothing. It "
     "comes back when the layer does."),
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

        # Count. Asserted, not assumed: `table in existing` is the whole
        # reason this line can be red.
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        check(f"{table} exists", table in existing and count > 0,
              f"rows={count}" if count else "table present but EMPTY")

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

        # Declared null expectations for this table - printed every run,
        # green or red. Silence used to mean "healthy"; it also meant
        # "never looked", and the two were indistinguishable.
        for _t, _col, _max_pct, _why in NULL_EXPECTATIONS:
            if _t != table:
                continue
            name = f"  {table}.{_col} nulls"
            if _col not in cols:
                check(name, False, "COLUMN MISSING - the expectation above "
                                   "no longer matches the schema")
                continue
            if not count:
                check(name, False, "table is empty, so the column cannot be judged")
                continue
            try:
                nulls = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {_col} IS NULL"
                ).fetchone()[0]
            except Exception as _ce:
                check(name, False, f"unreadable: {_ce}")
                continue
            pct = nulls * 100.0 / count
            check(name, pct <= _max_pct,
                  f"{nulls}/{count} ({pct:.1f}%) NULL, limit {_max_pct:.1f}% - {_why}"
                  if pct > _max_pct
                  else f"{nulls}/{count} ({pct:.1f}%) NULL, within {_max_pct:.1f}%")

        # Undeclared columns are surveyed, never scored: a column nobody has
        # made a claim about cannot fail a claim. Printed so that a new hole
        # is visible without inventing a threshold for it.
        try:
            declared = {c for t, c, _, _ in NULL_EXPECTATIONS if t == table}
            surveyed = []
            for col in cols:
                if col in declared or not count:
                    continue
                n = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL"
                ).fetchone()[0]
                if n * 100.0 / count > 50:
                    surveyed.append(f"{col} {n}/{count}")
            if surveyed:
                print(f"    (survey, not scored - over half empty: "
                      f"{', '.join(surveyed)})")
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

    for _t, _cols, _why in NULL_CHECKS_RETIRED:
        print(f"  [ -- ] {_t}.{_cols} — retired, not silently dropped")
        print(f"         {_why}")

    conn.close()

    print("=" * 60)
    total = PASS + FAIL
    print(f"Results: {PASS}/{total} passed, {FAIL} failed")
    print("=" * 60)
    return FAIL == 0


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
