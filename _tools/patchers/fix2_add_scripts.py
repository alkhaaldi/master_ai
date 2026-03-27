#!/usr/bin/env python3
"""Fix 2: Add master_ai_trade_review and master_ai_tv_sync to scripts.yaml."""
import os

SCRIPTS = "/var/lib/homeassistant/homeassistant/scripts.yaml"
if not os.path.exists(SCRIPTS):
    print("WARN: scripts.yaml not found at expected path")
    exit(1)

block = """
master_ai_trade_review:
  alias: "\u0645\u0631\u0627\u062c\u0639\u0629 \u0627\u0644\u062a\u062f\u0627\u0648\u0644"
  sequence:
    - action: persistent_notification.create
      data:
        title: "\U0001f916 Master AI"
        message: "\u23f3 \u0645\u0631\u0627\u062c\u0639\u0629 \u0627\u0644\u062a\u062f\u0627\u0648\u0644..."
        notification_id: "master_ai_cmd"
    - action: rest_command.master_ai_tg_cmd
      continue_on_error: true
      data:
        command: "/trade_review"
    - action: persistent_notification.create
      data:
        title: "\U0001f916 Master AI"
        message: "\u2705 \u062a\u0645 \u062a\u0646\u0641\u064a\u0630: \u0645\u0631\u0627\u062c\u0639\u0629 \u0627\u0644\u062a\u062f\u0627\u0648\u0644"
        notification_id: "master_ai_cmd"

master_ai_tv_sync:
  alias: "TV Sync"
  sequence:
    - action: persistent_notification.create
      data:
        title: "\U0001f916 Master AI"
        message: "\u23f3 \u0645\u0632\u0627\u0645\u0646\u0629 TV..."
        notification_id: "master_ai_cmd"
    - action: rest_command.master_ai_tg_cmd
      continue_on_error: true
      data:
        command: "/tv_sync"
    - action: persistent_notification.create
      data:
        title: "\U0001f916 Master AI"
        message: "\u2705 \u062a\u0645: \u0645\u0632\u0627\u0645\u0646\u0629 TV"
        notification_id: "master_ai_cmd"
"""

with open(SCRIPTS, "a", encoding="utf-8") as f:
    f.write(block)
print("OK: master_ai_trade_review + master_ai_tv_sync added to scripts.yaml")
