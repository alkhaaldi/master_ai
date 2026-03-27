#!/usr/bin/env python3
"""Phase 2: Update PE email action_label to suggest task conversion."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patch

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

# Update the email_high action_label
OLD = '            "action_label": "افتح البريد",\n            "action_target": "/master-ai/sub-email", "status": "action_needed",\n            "freshness_minutes": 0,\n            "source": {"endpoint": "/dashboard/extended", "field": "email_high"},'
NEW = '            "action_label": "راجع البريد أو حوّله لمهمة",\n            "action_target": "/master-ai/sub-email", "status": "action_needed",\n            "freshness_minutes": 0,\n            "source": {"endpoint": "/dashboard/extended", "field": "email_high"},'

result = apply_patch(FILE, OLD, NEW, backup=True)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
