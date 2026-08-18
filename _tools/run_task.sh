#!/bin/bash
# claude.ai's invoker for a headless task run.  Usage: _tools/run_task.sh NAME
# Sets the session marker so the Stop gate applies, then clears it either way.
set -u
NAME="${1:?usage: run_task.sh NAME}"
REPO=/home/pi/master_ai
cd "$REPO" || exit 1

TASK="_tools/TASK_${NAME}.md"
REPORT="${REPO}/_tools/REPORT_${NAME}.md"
[ -f "$TASK" ] || { echo "no such task file: $TASK"; exit 1; }

echo "$REPORT" > _tools/.session_task
trap 'unlink '"${REPO}"'/_tools/.session_task 2>/dev/null' EXIT

/usr/bin/claude -p "Read ${TASK} and execute it. Write your report to ${REPORT} before you finish; it must contain the headings '## What changed', '## Who consumes it', '## What might break', '## What is left'. Stay inside the task's scope - if something forces a decision outside it, stop and write that in the report." \
  --permission-mode acceptEdits 2>&1 | tail -60

echo "---- report ----"
[ -f "$REPORT" ] && wc -l "$REPORT" || echo "NO REPORT WRITTEN"

# index the run, so there is one chronological list and not a folder to trawl
if [ -f "$REPORT" ]; then
  printf -- '- %s  %s  ->  _tools/REPORT_%s.md\n' \
    "$(TZ=Asia/Kuwait date '+%Y-%m-%d %H:%M')" "$NAME" "$NAME" >> _tools/CHANGE_LOG.md
fi
