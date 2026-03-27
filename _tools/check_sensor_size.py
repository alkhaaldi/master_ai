#!/usr/bin/env python3
"""Check HA sensor attribute sizes."""
import json, subprocess

token = open('/home/pi/.ha_token').read().strip()
cmd = ['curl', '-s', '-H', f'Authorization: Bearer {token}',
       'http://localhost:8123/api/states/sensor.master_ai_extended']
r = subprocess.run(cmd, capture_output=True, text=True)
d = json.loads(r.stdout)
attrs = d.get('attributes', {})
total = len(json.dumps(attrs))
print(f"Total attr size: {total} bytes ({total/1024:.1f} KB)")
print(f"HA limit: ~16384 bytes (16 KB)")
print(f"{'OVER LIMIT!' if total > 16384 else 'Within limit'}")
print()
for k, v in sorted(attrs.items(), key=lambda x: -len(json.dumps(x[1]))):
    sz = len(json.dumps(v))
    items = ''
    if isinstance(v, list):
        items = f' ({len(v)} items)'
    print(f"  {k}: {sz} bytes{items}")
