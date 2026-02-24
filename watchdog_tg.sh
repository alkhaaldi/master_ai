#!/bin/bash
# Check if telegram bot is running, restart if not
if ! sudo systemctl is-active --quiet master-ai-telegram; then
    sudo systemctl start master-ai-telegram
fi
