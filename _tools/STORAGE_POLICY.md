# STORAGE POLICY — what lives on the NAS, what must not, and why

- Written 2026-08-17. Referenced by every future plan that creates a file
  which grows.
- Companion to `_tools/SCALES.md`: that one declares what a number means,
  this one declares where a file belongs.

## The facts

```
RPi  /  (SD card)      117 G total, 21 G used (19%)   — not under pressure
RPi  /tmp              4 G tmpfs — this is RAM, not disk
NAS  /mnt/nas-backups  11 T available, 308 G used (3%)
```

`/tmp` filling up on 2026-08-17 cost 4 GB of the Pi's **memory**, not its disk.
Anything routed to `/tmp` competes with the running service for RAM. Large
temporary files belong on the NAS or on `/`, never in tmpfs.

## Rule 1 — the live database stays on the RPi. Not negotiable.

`data/life.db` must never be moved to, or opened from, the CIFS mount.
SQLite's locking does not work reliably over SMB/CIFS, and the database runs in
WAL mode, which is worse over a network filesystem. The failure mode is not a
clear error — it is silent corruption discovered later.

The same applies to `data/yahoo_gate.db`, which is written on the hot path of
every request.

**Backups of the database on the NAS: yes** (already done, `sqlite3 .backup`
then copy). **The database itself: never.**

## Rule 2 — the NAS can disappear, so nothing on the hot path depends on it

The mount is `nofail`, deliberately: a NAS outage must not stop the Pi booting
or trading. That means every write to `/mnt/nas-backups`:

1. is wrapped so a failure does not kill the calling process
2. logs the failure loudly (locally, on the RPi)
3. has a guard that goes red if writes have been failing

A log that silently stops being written because the NAS was unreachable is
precisely the class of failure this whole phase removed.

## Rule 3 — what belongs on the NAS

Anything **append-only, cold, or archival**:

- **Logs** — `server.log`, `cron.log`, `intraday_refresh.log`,
  `positions_refresh.log`, `nas_backup.log`, `gdrive_backup.log`.
  Today they rotate and are discarded. On the NAS they can be kept for months,
  which matters: the 114-day silence of the review loop would have been visible
  in a year of logs, and the two dead backup crons wrote their failures into a
  file nobody kept.
- **Database exports and archives** — when `signal_snapshots` (67,185 rows and
  growing) or `decision_audit` or `confidence_census` get large, archive old
  partitions to the NAS as compressed exports rather than deleting them.
  C-27 will want the history.
- **Large generated artifacts** — `avg_volume_fill.json` and its kind.
- **Working copies** — `prove_guards` copies the 87 MB database per case.
  Those belong on the NAS or `/`, not tmpfs.

## Rule 4 — nothing goes to the NAS without a retention rule

Space is not a reason to keep things forever. 11 TB fills too, and an
unbounded directory is a future incident. Every path added here declares:

```
what · why it grows · how long it is kept · who deletes it
```

The backup path already does this (keep 14). Logs need the same before they
move.

## Rule 5 — a guard for the space itself

Three different things share the word "space", and they fail differently:

```
/                  disk   — fills slowly, kills writes to life.db
/tmp               RAM    — fills fast, gets processes killed
/mnt/nas-backups   network — does not fill, it disappears
```

Do not collapse them into one check. Each gets its own threshold, its own
reason, and its own line in `prove_guards.py`.

## Open items this creates

1. Move log retention to the NAS, with Rule 2 wrapping and Rule 4 retention
2. Point `prove_guards` working copies away from tmpfs
3. The three-part space guard (Rule 5)
4. An archive path for `signal_snapshots` before it needs one, not after
