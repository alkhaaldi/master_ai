import json, subprocess
r = subprocess.run(['curl','-s','-H','Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI1ZDVlZWRkMzk0MjY0MDk2OTY0YThlNjYyZDU0NTYzYiIsImlhdCI6MTc3MTI1NDI4NywiZXhwIjoyMDg2NjE0Mjg3fQ.Ws_86k8u0abSGfBZMYxKVSxzO8r6kX2yyIXPicjyFd0','http://localhost:8123/api/states'], capture_output=True, text=True)
entities = json.loads(r.stdout)
result = {}
for e in entities:
    eid = e['entity_id']
    name = e['attributes'].get('friendly_name', '')
    domain = eid.split('.')[0]
    if domain in ['light','switch','cover','climate','fan','media_player','scene']:
        if domain not in result:
            result[domain] = []
        result[domain].append({'id': eid, 'name': name})

with open('/home/pi/master_ai/entities.json', 'w') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

for d in sorted(result):
    print(f"{d}: {len(result[d])}")
print(f"Total: {sum(len(v) for v in result.values())}")
