#!/usr/bin/env python3
"""Diagnose sub-radar rendering by checking each card individually."""
import yaml, json, subprocess

YAML_PATH = "/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml"
token = open('/home/pi/.ha_token').read().strip()

with open(YAML_PATH, 'r', encoding='utf-8') as f:
    d = yaml.safe_load(f)

for v in d.get('views', []):
    if v.get('path') == 'sub-radar':
        main_stack = v['cards'][0]  # The outer stack-in-card
        children = main_stack.get('cards', [])
        print(f"Main stack has {len(children)} children")
        
        for i, card in enumerate(children):
            ctype = card.get('type', '?')
            has_cards = 'cards' in card
            cards_count = len(card.get('cards', []))
            
            # Check for nested stack-in-cards without cards
            problems = []
            if ctype == 'custom:stack-in-card' and not has_cards:
                problems.append("MISSING 'cards' key!")
            if ctype == 'custom:stack-in-card' and cards_count == 0:
                problems.append("EMPTY cards array!")
            
            # Check nested children
            for j, sub in enumerate(card.get('cards', [])):
                stype = sub.get('type', '?')
                if stype == 'custom:stack-in-card':
                    if 'cards' not in sub:
                        problems.append(f"  sub[{j}] {stype} MISSING 'cards'!")
                    elif len(sub.get('cards', [])) == 0:
                        problems.append(f"  sub[{j}] {stype} EMPTY cards!")
                
                # Check markdown templates for errors
                if stype == 'markdown':
                    content = sub.get('content', '')
                    body = json.dumps({"template": content})
                    cmd = ['curl', '-s', '-H', f'Authorization: Bearer {token}',
                           '-H', 'Content-Type: application/json',
                           '-X', 'POST', 'http://localhost:8123/api/template', '-d', body]
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    if 'error' in r.stdout.lower() or 'Error' in r.stdout:
                        problems.append(f"  sub[{j}] markdown TEMPLATE ERROR: {r.stdout[:100]}")
            
            status = "PROBLEMS: " + "; ".join(problems) if problems else "OK"
            print(f"  [{i}] {ctype} ({cards_count} children) - {status}")
