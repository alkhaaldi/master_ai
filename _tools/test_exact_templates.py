#!/usr/bin/env python3
"""Extract the exact watchlist and daily context markdown templates from the dashboard YAML."""
import yaml, json

YAML_PATH = "/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml"
with open(YAML_PATH, 'r', encoding='utf-8') as f:
    d = yaml.safe_load(f)

for v in d.get('views', []):
    if v.get('path') == 'sub-radar':
        cards = v['cards'][0]['cards']  # main stack-in-card children
        for i, card in enumerate(cards):
            t = card.get('type', '?')
            if t == 'custom:stack-in-card':
                for j, sub in enumerate(card.get('cards', [])):
                    st = sub.get('type', '?')
                    if st == 'markdown':
                        content = sub.get('content', '')
                        if 'radar_watchlist' in content or 'radar_daily_context' in content:
                            print(f"=== Card[{i}].Sub[{j}] - {st} ===")
                            print(f"Content preview (first 200 chars):")
                            print(content[:200])
                            print(f"...")
                            print(f"Content length: {len(content)} chars")
                            print()
                            
                            # Test render via HA API
                            import subprocess
                            token = open('/home/pi/.ha_token').read().strip()
                            body = json.dumps({"template": content})
                            cmd = ['curl', '-s', '-H', f'Authorization: Bearer {token}',
                                   '-H', 'Content-Type: application/json',
                                   '-X', 'POST', 'http://localhost:8123/api/template',
                                   '-d', body]
                            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                            result = r.stdout[:300]
                            print(f"HA RENDER RESULT: {result}")
                            print()
