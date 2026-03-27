import yaml
with open("/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml") as f:
    d = yaml.safe_load(f)
print(f"YAML VALID: {len(str(d))} chars")
views = d.get("views", [])
print(f"Views: {len(views)}")
for v in views:
    cards = v.get("cards", [])
    print(f"  {v.get('title','?')}: {len(cards)} cards")
