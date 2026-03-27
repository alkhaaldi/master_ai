#!/usr/bin/env python3
"""Check which modules are actually loadable."""
import subprocess
result = subprocess.run(
    ["journalctl", "-u", "master-ai.service", "--no-pager", "-n", "50"],
    capture_output=True, text=True
)
for line in result.stdout.splitlines():
    low = line.lower()
    if any(x in low for x in ["not loaded", "learning", "email_ok", "tg_email", "brain_", "warning"]):
        print(line.strip())
