import json
with open("/var/lib/homeassistant/homeassistant/.storage/auth") as f:
    d = json.load(f)
users = d.get("data", {}).get("users", [])
for u in users:
    print(f"name={u.get('name','')} id={u.get('id','')} system={u.get('system_generated',False)}")
