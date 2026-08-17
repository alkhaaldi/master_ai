#!/bin/bash
# PreToolUse guard: no blanket git staging in this repo.
# Exit 2 = block the Bash call; stderr goes back to the model.

CMD=$(jq -r '.tool_input.command // empty')

# --- blanket `git add` ---
if printf '%s' "$CMD" | grep -qE 'git[[:space:]]+add[[:space:]]+(-A\b|--all\b|\.[[:space:]]*$|\.[[:space:]]+)'; then
  echo "BLOCKED: blanket 'git add' is not allowed in this repo." >&2
  echo "The tree regularly carries unrelated in-flight work from a parallel session." >&2
  echo "Run 'git status --short', then stage only the paths you changed by name." >&2
  exit 2
fi

# --- `git commit -a` / -am / -ma / --all ---
# The prefix is a chain of dash-led tokens only, so the match stops at the
# first quote and never slides into the commit MESSAGE. An earlier version
# used ([^|;&]*[[:space:]])? here and blocked messages containing words like
# "re-analysis". Known accepted gap: `git commit -m "x" -a` passes.
if printf '%s' "$CMD" | grep -qE 'git[[:space:]]+commit([[:space:]]+-[^[:space:]]*)*[[:space:]]+(-[a-zA-Z]*a[a-zA-Z]*\b|--all\b)'; then
  echo "BLOCKED: 'git commit -a/-am/--all' commits every modified tracked file with no staging." >&2
  echo "Stage the specific paths first, then commit without -a." >&2
  exit 2
fi

exit 0
