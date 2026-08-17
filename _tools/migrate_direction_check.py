#!/usr/bin/env python3
"""Put the direction constraint in the schema, where it cannot be forgotten.

    python3 _tools/migrate_direction_check.py --target /path/to/copy.db   # rehearse
    python3 _tools/migrate_direction_check.py --live                      # do it

WHY
---
Three modules currently agree that a direction must be 'long' or 'short'
(position_engine, journal_engine x2, all on VALID_DIRECTIONS). That is an
agreement, not a constraint: a fourth reader written next month starts from
zero, and the schema will still tell it that an omitted direction is a BUY.

    direction TEXT NOT NULL DEFAULT 'long'

Measured on a copy, NOT NULL is weaker than it reads:
    ''       accepted - falsy, which is what `or "long"` used to fire on
    'lomg'   accepted - TRUTHY, so it sailed past the default into the
             short branch and inverted the sign of the money

After this the database itself refuses both, and an INSERT that omits the
column fails instead of inventing a position nobody chose.

ROLLBACK PATH - written before execution, per the user's condition
------------------------------------------------------------------
Three layers, in the order you would reach for them:

1. MID-RUN FAILURE: everything below runs inside a single transaction.
   Any error - including a row that violates the new CHECK - rolls the whole
   thing back and the table is untouched. Nothing to do by hand.

2. AFTER COMMIT, same session: the pre-migration copy of the table is left
   in the database as `trades_bak_precheck_<UTC stamp>`. To undo:

       sudo systemctl stop master-ai.service
       sqlite3 data/life.db "BEGIN; DROP TABLE trades;
         ALTER TABLE trades_bak_precheck_<stamp> RENAME TO trades;
         CREATE INDEX idx_trades_symbol ON trades(symbol);
         CREATE INDEX idx_trades_status ON trades(status);
         CREATE INDEX idx_trades_date   ON trades(entry_date); COMMIT;"
       sudo systemctl start master-ai.service

3. ANYTHING WORSE (file-level damage): a full database snapshot is taken
   with SQLite's own backup API before the transaction opens, at
   `backups/life_pre_direction_check_<stamp>.db`. To undo:

       sudo systemctl stop master-ai.service
       cp backups/life_pre_direction_check_<stamp>.db data/life.db
       sudo systemctl start master-ai.service

   Snapshot lives on `/` (92GB free), never in /tmp - that is RAM
   (STORAGE_POLICY Rule 3). Retention: kept until the next schema migration
   verifies clean, deleted by hand, owner Salem. That is Rule 4 satisfied.
"""
import argparse
import hashlib
import os
import sqlite3
import sys
from datetime import datetime, timezone

BASE = "/home/pi/master_ai"
LIVE_DB = os.path.join(BASE, "data", "life.db")
INDEXES = [
    ("idx_trades_symbol", "CREATE INDEX idx_trades_symbol ON trades(symbol)"),
    ("idx_trades_status", "CREATE INDEX idx_trades_status ON trades(status)"),
    ("idx_trades_date", "CREATE INDEX idx_trades_date ON trades(entry_date)"),
]


def fingerprint(conn):
    """(row count, content hash) - the two numbers compared either side.

    The hash covers every column of every row, ordered by id, so a migration
    that loses a column or reorders values is caught even when the count
    matches. A count alone would not have noticed the 19 columns that
    refresh_daily_snapshot used to NULL.
    """
    rows = conn.execute("SELECT * FROM trades ORDER BY id").fetchall()
    h = hashlib.sha256()
    for r in rows:
        h.update(repr(tuple(r)).encode("utf-8"))
    return len(rows), h.hexdigest()[:16]


def column_defs(conn):
    """Rebuild the column list from PRAGMA, so the 40 columns travel exactly
    as they are rather than as a hand-copied list that drifts."""
    out = []
    for cid, name, ctype, notnull, dflt, pk in conn.execute(
            "PRAGMA table_info(trades)"):
        piece = '"%s" %s' % (name, ctype or "")
        if pk:
            piece += " PRIMARY KEY AUTOINCREMENT" if ctype.upper() == "INTEGER" else " PRIMARY KEY"
        if notnull and not pk:
            piece += " NOT NULL"
        # The point of the exercise: direction keeps NOT NULL and LOSES its
        # default. Every other column keeps whatever it had.
        if dflt is not None and name != "direction":
            piece += " DEFAULT %s" % dflt
        out.append(piece.strip())
    return out


def migrate(db_path, live):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row

    before_n, before_h = fingerprint(conn)
    print(f"  before : {before_n} rows, fingerprint {before_h}")

    bad = conn.execute(
        "SELECT id, symbol, direction FROM trades"
        " WHERE direction NOT IN ('long','short')").fetchall()
    if bad:
        print("  ABORT: %d row(s) already violate the constraint - fix the "
              "data before constraining it:" % len(bad))
        for r in bad:
            print(f"     #{r['id']} {r['symbol']} direction={r['direction']!r}")
        conn.close()
        return False

    snapshot = None
    if live:
        os.makedirs(os.path.join(BASE, "backups"), exist_ok=True)
        snapshot = os.path.join(BASE, "backups",
                                "life_pre_direction_check_%s.db" % stamp)
        dst = sqlite3.connect(snapshot)
        conn.backup(dst)          # SQLite's own backup API, not a file copy
        dst.close()
        print(f"  snapshot: {snapshot} ({os.path.getsize(snapshot)//1024} KB)")

    cols = column_defs(conn)
    names = ",".join('"%s"' % r[1] for r in conn.execute("PRAGMA table_info(trades)"))
    bak = "trades_bak_precheck_%s" % stamp

    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN")
        conn.execute("CREATE TABLE %s AS SELECT * FROM trades" % bak)
        conn.execute(
            "CREATE TABLE trades_new (%s, CHECK (direction IN ('long','short')))"
            % ",\n  ".join(cols))
        conn.execute("INSERT INTO trades_new (%s) SELECT %s FROM trades"
                     % (names, names))
        conn.execute("DROP TABLE trades")
        conn.execute("ALTER TABLE trades_new RENAME TO trades")
        for _n, ddl in INDEXES:
            conn.execute(ddl)
        conn.execute("COMMIT")
    except Exception as e:
        conn.execute("ROLLBACK")
        conn.close()
        print(f"  FAILED, rolled back, table untouched: {e!r}")
        return False

    after_n, after_h = fingerprint(conn)
    print(f"  after  : {after_n} rows, fingerprint {after_h}")
    if (before_n, before_h) != (after_n, after_h):
        print("  *** FINGERPRINT MISMATCH - use the rollback path in the "
              "docstring ***")
        conn.close()
        return False
    print(f"  rows and content identical · rollback table kept as {bak}")

    # The constraint is only worth having if it refuses. Proved here, in the
    # migrated database, and rolled back so nothing is left behind.
    checks = []
    for label, sql in (
            ("omitted column", "INSERT INTO trades (symbol,status,entry_price,"
                               "entry_date,created_at) VALUES ('X','open',1,"
                               "date('now'),datetime('now'))"),
            ("empty string", "INSERT INTO trades (symbol,status,direction,"
                             "entry_price,entry_date,created_at) VALUES "
                             "('X','open','',1,date('now'),datetime('now'))"),
            ("typo 'lomg'", "INSERT INTO trades (symbol,status,direction,"
                            "entry_price,entry_date,created_at) VALUES "
                            "('X','open','lomg',1,date('now'),datetime('now'))"),
    ):
        try:
            conn.execute("BEGIN")
            conn.execute(sql)
            conn.execute("ROLLBACK")
            checks.append((label, "ACCEPTED - the constraint did not hold"))
        except sqlite3.IntegrityError as e:
            conn.execute("ROLLBACK")
            checks.append((label, "refused (%s)" % str(e)[:44]))
    try:
        conn.execute("BEGIN")
        conn.execute("INSERT INTO trades (symbol,status,direction,entry_price,"
                     "entry_date,created_at) VALUES ('X','open','short',1,"
                     "date('now'),datetime('now'))")
        conn.execute("ROLLBACK")
        checks.append(("a stated 'short'", "accepted, as it must be"))
    except Exception as e:
        conn.execute("ROLLBACK")
        checks.append(("a stated 'short'", "REJECTED - too strict: %r" % e))
    conn.close()

    ok = True
    for label, res in checks:
        bad_res = "ACCEPTED - the constraint" in res or "REJECTED" in res
        print(f"    {'!!' if bad_res else 'OK'}  {label:16} {res}")
        if bad_res:
            ok = False
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", help="a copy to rehearse on")
    ap.add_argument("--live", action="store_true", help="migrate data/life.db")
    a = ap.parse_args()
    if a.live and a.target:
        sys.exit("choose one: --target or --live")
    if not a.live and not a.target:
        sys.exit("nothing to do: pass --target <copy.db> or --live")
    path = LIVE_DB if a.live else a.target
    print(f"migrating {path}{' (LIVE)' if a.live else ' (rehearsal)'}")
    # A branch, not `0 if ok else 1`: the falsy sentinel counts the ternary
    # form, and it caught this line the moment the migration landed.
    if migrate(path, a.live):
        sys.exit(0)
    sys.exit(1)
