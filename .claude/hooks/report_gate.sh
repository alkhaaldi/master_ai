#!/bin/bash
# Stop hook: a task run does not get to end without its change log.
# Only active when claude.ai started the run through _tools/run_task.sh.
# Interactive sessions on the RPi are untouched.

INPUT=$(cat)
[ "$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false')" = "true" ] && exit 0

MARK=/home/pi/master_ai/_tools/.session_task
[ -f "$MARK" ] || exit 0
REPORT=$(head -1 "$MARK")
[ -n "$REPORT" ] || exit 0

if [ ! -f "$REPORT" ]; then
  echo "NOT FINISHED: $REPORT was never written. stdout is not the channel - the file is." >&2
  echo "Write it now with these headings, then stop:" >&2
  echo "  ## What changed | ## Who consumes it | ## What might break | ## What is left" >&2
  exit 2
fi

MISSING=""
for H in "## What changed" "## Who consumes it" "## What might break" "## What is left"; do
  grep -qF "$H" "$REPORT" || MISSING="$MISSING  $H"
done

if [ -n "$MISSING" ]; then
  echo "NOT FINISHED: $REPORT is missing:$MISSING" >&2
  echo "'Who consumes it' is the one that has bitten twice - name the pages, endpoints," >&2
  echo "sensors and schedules that read what you touched, or say none and how you checked." >&2
  exit 2
fi
exit 0
