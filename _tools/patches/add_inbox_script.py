#!/usr/bin/env python3
"""Add master_ai_inbox script to scripts.yaml."""
import yaml

SCRIPTS_FILE = "/var/lib/homeassistant/homeassistant/scripts.yaml"

with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
    content = f.read()

if "master_ai_inbox" in content:
    print("ALREADY EXISTS — skipping")
else:
    inbox_block = """
master_ai_inbox:
  alias: "تحديث البريد"
  sequence:
    - action: persistent_notification.create
      data:
        title: "🤖 Master AI"
        message: "⏳ تحديث البريد..."
        notification_id: "master_ai_cmd"
    - action: rest_command.master_ai_tg_cmd
      continue_on_error: true
      data:
        command: "/inbox"
    - action: persistent_notification.create
      data:
        title: "🤖 Master AI"
        message: "✅ تم تنفيذ: تحديث البريد"
        notification_id: "master_ai_cmd"
"""
    with open(SCRIPTS_FILE, "a", encoding="utf-8") as f:
        f.write(inbox_block)
    # Validate
    with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
        yaml.safe_load(f.read())
    print("ADDED + YAML OK")
