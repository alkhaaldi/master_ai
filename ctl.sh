#!/bin/bash
# Master AI Control Script - called from HA shell_commands
ACTION=${1:-status}
cd /home/pi/master_ai

case "$ACTION" in
  restart)  sudo systemctl restart master-ai && echo "RESTARTED" ;;
  stop)     sudo systemctl stop master-ai && echo "STOPPED" ;;
  start)    sudo systemctl start master-ai && echo "STARTED" ;;
  status)   sudo systemctl is-active master-ai ;;
  logs)     journalctl -u master-ai -n 20 --no-pager 2>&1 | tail -20 ;;
  check)    python3 -c "compile(open('server.py').read(),'s','exec')" 2>&1 && echo "OK" || echo "BROKEN" ;;
  gitlog)   git log --oneline -5 ;;
  revert)   git revert --no-edit HEAD && sudo systemctl restart master-ai && echo "REVERTED" ;;
  reset1)   git reset --hard HEAD~1 && sudo systemctl restart master-ai && echo "RESET_TO_PREV" ;;
  fixstart) python3 -c "compile(open('server.py').read(),'s','exec')" 2>&1 && sudo systemctl restart master-ai && echo "FIX_OK" || echo "SYNTAX_ERROR" ;;
  *)        echo "Usage: ctl.sh {restart|stop|start|status|logs|check|gitlog|revert|reset1|fixstart}" ;;
esac
