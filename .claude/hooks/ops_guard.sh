#!/bin/bash
# PreToolUse guard: refuses what a headless run must not decide alone.
# Exit 2 = block the tool call; stderr is handed back to the model.
#
# Scope, stated so nobody is surprised later: this governs Claude Code
# sessions started inside /home/pi/master_ai on the RPi. It does NOT govern
# claude.ai's own /ssh/run calls. That is deliberate - the override for a
# guard has to live outside the session the guard is restraining.

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT"  | jq -r '.tool_input.command   // empty')
FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')

REPO=/home/pi/master_ai
TOK_RESTART="$REPO/_tools/.allow_restart_now"
TOK_DB="$REPO/_tools/.allow_db_write"

# a token counts only if claude.ai placed it in the last 30 minutes
fresh() {
  [ -f "$1" ] || return 1
  [ $(( $(date +%s) - $(stat -c %Y "$1") )) -lt 1800 ]
}

# ---------- 0. the guard protects itself ----------
if [ -n "$FILE" ] && printf '%s' "$FILE" | grep -q '/\.claude/'; then
  echo "BLOCKED: .claude/ (hooks + settings) is not editable from a session it governs." >&2
  echo "If a guard is genuinely wrong, say so in the report. claude.ai changes it out of band." >&2
  exit 2
fi
if printf '%s' "$CMD" | grep -qE '\.claude/(hooks|settings)' \
   && printf '%s' "$CMD" | grep -qE '(\brm\b|\bmv\b|\bcp\b|chmod|sed[[:space:]]+-i|truncate|tee\b|>>?[[:space:]]*[^ ]*\.claude)'; then
  echo "BLOCKED: this command would modify or remove .claude/hooks or .claude/settings.json." >&2
  echo "A guard a session can switch off is not a guard. Put the request in the report." >&2
  exit 2
fi

# ---------- 1. restart while the market is open ----------
if printf '%s' "$CMD" | grep -qE '(restart_master_ai\.sh|ctl\.sh[[:space:]]+restart|systemctl([[:space:]]+--user)?[[:space:]]+restart|service[[:space:]]+[A-Za-z0-9_-]+[[:space:]]+restart)'; then
  DOW=$(TZ=Asia/Kuwait date +%u)
  HM=$(( 10#$(TZ=Asia/Kuwait date +%H%M) ))
  if [ "$DOW" != "5" ] && [ "$DOW" != "6" ] && [ "$HM" -ge 845 ] && [ "$HM" -le 1315 ]; then
    if ! fresh "$TOK_RESTART"; then
      echo "BLOCKED: the Kuwait market is open (Sun-Thu 09:00-13:00). A restart costs a scan cycle." >&2
      echo "Do not restart. Write the request at the end of your report file and finish the rest." >&2
      exit 2
    fi
  fi
fi

# ---------- 2. no message goes out on his behalf ----------
if printf '%s' "$CMD" | grep -qEi '(api\.telegram\.org|sendmessage|send_telegram|tg_send|/telegram/send|notify\.send|smtplib|sendmail)'; then
  if printf '%s' "$CMD" | grep -qEi '(curl|wget|python3?|http[[:space:]]|requests\.|invoke-rest)'; then
    echo "BLOCKED: nothing is sent to him from a headless run - not a test, not a probe." >&2
    echo "Name the message and why it is needed in the report. claude.ai sends it or asks him." >&2
    exit 2
  fi
fi

# ---------- 3a. destructive SQL ----------
if printf '%s' "$CMD" | grep -qEi '(DROP[[:space:]]+(TABLE|INDEX|VIEW)|TRUNCATE[[:space:]]+TABLE|DELETE[[:space:]]+FROM|ALTER[[:space:]]+TABLE[[:space:]]+[A-Za-z0-9_]+[[:space:]]+DROP)'; then
  # only when it is actually being executed - searching the codebase for the
  # phrase is how you find out who does it, and must not be blocked
  if printf '%s' "$CMD" | grep -qEi '(sqlite3|executescript|\.execute|cursor|psql|mysql)'; then
    if ! fresh "$TOK_DB"; then
      echo "BLOCKED: destructive SQL. This is one of the four calls that are his, not yours." >&2
      echo "Write the exact statement and the reason in the report and stop there." >&2
      exit 2
    fi
  fi
fi

# ---------- 3b. irreversible on disk or in git ----------
if printf '%s' "$CMD" | grep -qE '(\brm[[:space:]]+(-[A-Za-z]*[rR][A-Za-z]*f|-[A-Za-z]*f[A-Za-z]*[rR])|git[[:space:]]+reset[[:space:]]+--hard|git[[:space:]]+clean[[:space:]]+-[A-Za-z]*f|git[[:space:]]+push[[:space:]]+.*--force|git[[:space:]]+checkout[[:space:]]+--[[:space:]]+\.|\bshred\b|\bmk[f]s|dd[[:space:]]+.*of=)'; then
  echo "BLOCKED: irreversible. The tree carries in-flight work from a parallel session." >&2
  echo "Undo what you can by name, and report what you could not." >&2
  exit 2
fi

# ---------- 4. the CLI never spends API credit ----------
# /usr/local/bin/claude already unsets the key for anything resolved via PATH.
# This catches the one way around that: naming the real binary directly.
if printf '%s' "$CMD" | grep -qE '(^|[;&[:space:]])(/usr/bin/)?claude[[:space:]]+(-p\b|--print\b)'; then
  if ! printf '%s' "$CMD" | grep -q 'env -u ANTHROPIC_API_KEY'; then
    echo "BLOCKED: this would run Claude Code on the sk-ant- API key, not the subscription." >&2
    echo "That key belongs to the app, not to the CLI. Call it as 'claude' so the wrapper" >&2
    echo "at /usr/local/bin/claude applies, or prefix it with 'env -u ANTHROPIC_API_KEY'." >&2
    exit 2
  fi
fi

exit 0
