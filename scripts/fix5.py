#!/usr/bin/env python3
with open('/home/pi/master_ai/server.py','r') as f: c=f.read()

# 1) Add filter: only keep _inverted covers
old1 = 'and s.get("state") not in ("unavailable",)]'
new1 = old1 + '\n        relevant = [s for s in relevant if not (s["entity_id"].startswith("cover.") and not s["entity_id"].endswith("_inverted"))]'
c = c.replace(old1, new1, 1)
print('Step 1: filter added')

# 2) Fix cover: closed=\u0645\u0633\u0643\u0631\u0629 (no inversion)
old2 = '"\u0645\u0633\u0643\u0631\u0629" if state == "open"'
new2 = '"\u0645\u0633\u0643\u0631\u0629" if state == "closed"'
c = c.replace(old2, new2, 1)
print('Step 2: closed=mskra')

# 3) Remove the double inversion of pos
old3 = 'real_pos = 100 - pos'
new3 = 'real_pos = int(float(pos))'
c = c.replace(old3, new3, 1)
print('Step 3: pos direct')

# 4) Update comment
old4 = '# ALL covers inverted: open=closed physically, 100%=closed'
new4 = '# _inverted templates: state already correct (closed=mskra)'
c = c.replace(old4, new4, 1)
print('Step 4: comment')

with open('/home/pi/master_ai/server.py','w') as f: f.write(c)
print('Done!')