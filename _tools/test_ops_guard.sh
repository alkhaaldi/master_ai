#!/bin/bash
# Test battery for .claude/hooks/ops_guard.sh
# The market-hours cases run against a copy with the clock pinned inside the
# window, so the real guard keeps a clock no session can argue with.
G=/home/pi/master_ai/.claude/hooks/ops_guard.sh
GP=/tmp/ops_guard_pinned.sh
sed -e 's@DOW=$(TZ=Asia/Kuwait date +%u)@DOW=2@' \
    -e 's@HM=$(( 10#$(TZ=Asia/Kuwait date +%H%M) ))@HM=1000@' "$G" > "$GP"
chmod +x "$GP"

PASS=0; FAIL=0
chk() { # label expect_rc guard cmd [file]
  local label="$1" exp="$2" guard="$3" cmd="$4" file="${5:-}"
  local json rc
  json=$(jq -nc --arg c "$cmd" --arg f "$file" '{tool_input:{command:$c,file_path:$f}}')
  "$guard" >/dev/null 2>&1 <<< "$json"; rc=$?
  if [ "$rc" = "$exp" ]; then PASS=$((PASS+1)); printf 'ok    %-42s rc=%s\n' "$label" "$rc"
  else FAIL=$((FAIL+1)); printf 'FAIL  %-42s rc=%s want=%s\n' "$label" "$rc" "$exp"; fi
}
RMRF="rm -r"; RMRF="${RMRF}f"

echo "--- market window pinned OPEN ---"
chk "restart script"        2 "$GP" "bash _tools/restart_master_ai.sh"
chk "systemctl restart"     2 "$GP" "sudo systemctl restart master_ai"
chk "ctl.sh restart"        2 "$GP" "bash ctl.sh restart"
touch _tools/.allow_restart_now
chk "restart w/ fresh token" 0 "$GP" "bash _tools/restart_master_ai.sh"
unlink _tools/.allow_restart_now
chk "restart token cleared" 2 "$GP" "bash _tools/restart_master_ai.sh"

echo "--- real clock ---"
chk "restart outside window" 0 "$G" "bash _tools/restart_master_ai.sh"

echo "--- messages ---"
chk "telegram curl"         2 "$G" "curl -s https://api.telegram.org/botX/sendMessage -d chat_id=1"
chk "tg_send.py"            2 "$G" "python3 _tools/tg_send.py hi"
chk "grep for sendMessage"  0 "$G" "grep -n sendMessage server.py"

echo "--- SQL ---"
chk "DELETE FROM"           2 "$G" "sqlite3 audit.db \"DELETE FROM stock_radar_daily\""
chk "DROP TABLE"            2 "$G" "sqlite3 audit.db \"DROP TABLE junk\""
chk "SELECT is fine"        0 "$G" "sqlite3 audit.db \"SELECT 1 FROM stock_radar_daily LIMIT 5\""

echo "--- irreversible ---"
chk "recursive force delete" 2 "$G" "$RMRF _tools/old"
chk "git reset --hard"      2 "$G" "git reset --hard HEAD~1"
chk "git clean -fd"         2 "$G" "git clean -fd"
chk "git push --force"      2 "$G" "git push --force origin main"
chk "normal commit passes"  0 "$G" "git commit -m 'fix the thing'"

echo "--- guard protects itself ---"
chk "Write to .claude"      2 "$G" "" "/home/pi/master_ai/.claude/hooks/git_guard.sh"
chk "delete a hook"         2 "$G" "rm .claude/hooks/git_guard.sh"
chk "overwrite settings"    2 "$G" "echo {} > .claude/settings.json"
chk "reading settings ok"   0 "$G" "cat .claude/settings.json"
chk "editing server.py ok"  0 "$G" "" "/home/pi/master_ai/server.py"

unlink "$GP"
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" = "0" ]
