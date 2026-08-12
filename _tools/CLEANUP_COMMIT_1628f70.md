# CLEANUP: split commit 1628f70 + stop committing logs/binaries

Date: 2026-08-12
Owner: Claude Code (RPi)
Type: git hygiene only - NO code logic changes
Risk: low (branch is 118 commits ahead of origin, nothing was ever pushed)

## Problem

Commit `1628f70` was made with `git add -A` and swallowed 47 files / ~394k
insertions. It contains, besides the actual BRIDGE_URL fix:

- `_inbox/surah_zalzalah_3hours_clean.mp3` - **64 MB binary**, permanent repo bloat
- `server.log.1`, `server.log.2`, `server.log.3` - ~570k lines of rotated logs
  (`server.log.1` is ALREADY dirty again - every future commit will be noisy)
- `tmp/` scratch scripts (7 files) + assorted `_tools/` backtest CSVs
- An unrelated in-progress change: "on-demand analysis, no cache"
  (`server.py` +120, `stock_analyzer.py` +22, `dashboard_api.py` +12)

The WIP change is now LIVE - the service restart loaded it into production.
It passed quick_check 13/13 and smoke_test 4/4, so leave the code as-is on
disk. This task only fixes the git history, not the running code.

## Step 1 - Confirm nothing was pushed

```bash
cd /home/pi/master_ai
git status -sb | head -2      # expect: ## main...origin/main [ahead N]
git log origin/main..HEAD --oneline | wc -l
```
If the branch turns out to be pushed, STOP and report back - do not rewrite.

## Step 2 - Backup pointer before rewriting

```bash
git branch backup/pre-cleanup-20260812 HEAD
```

## Step 3 - Unwind the two commits (keeps every file on disk)

```bash
git reset --soft af6c0c8
git reset                     # unstage everything, working tree untouched
git status --short | head -30
```

## Step 4 - Fix .gitignore FIRST

Append (only lines not already present):
```
server.log*
*.log.[0-9]
_inbox/
tmp/
*.mp3
```
Then untrack what is already tracked:
```bash
git rm -r --cached server.log.1 server.log.2 server.log.3 _inbox tmp 2>/dev/null || true
```

## Step 5 - Re-commit in three clean commits

**a) the actual fix**
```bash
git add .gitignore bridge_client.py bridge_client_new.py stock_analyzer.py \
        kse_data_collector.py stock_radar.py journal_engine.py \
        dashboard_api.py brain_backfill.py server.py \
        _tools/_fetch_30m.py _tools/_fetch_daily.py _tools/_system_check.py \
        _tools/test_bridge.py _tools/test_fractal_quick.py \
        _tools/fractal_backtest.py _tools/fractal_backtest_v2.py \
        _tools/fractal_backtest_v3.py _tools/fractal_backtest_v4.py
git commit -m "fix: BRIDGE_URL via env + no 5xx on /api/analyze business errors"
```
NOTE: `server.py`, `stock_analyzer.py`, `dashboard_api.py` carry BOTH the fix
and the on-demand WIP. Do not try to split them by hunk - just say so in the
commit body:
```
Also includes pre-existing in-progress "on-demand analysis, no cache" edits
to server.py / stock_analyzer.py / dashboard_api.py that were already on disk.
```

**b) docs**
```bash
git add _tools/*.md
git commit -m "docs: Cloudflare 5xx-masking rule + task plans"
```

**c) research scripts**
```bash
git add _tools/kse_*.py _tools/*.csv _tools/*.pine
git commit -m "chore: KSE indicator/backtest research scripts"
```

Leave `_inbox/`, `tmp/`, and the log files UNCOMMITTED and ignored.

## Step 6 - Verify

```bash
git log --oneline -5
git show --stat HEAD~2 | tail -5     # must be small, no mp3, no server.log
git status --short | head            # logs/_inbox/tmp should not appear
du -sh .git
python3 _tools/quick_check.py
```

Do NOT restart the service - no code changed in this task.
Report `du -sh .git` before/after so we know if the 64 MB actually dropped.
