import urllib.request
with open("/home/pi/.ha_token") as f:
    t = f.read().strip()
r = urllib.request.urlopen(urllib.request.Request(
    "http://localhost:8123/api/services/homeassistant/restart",
    headers={"Authorization": f"Bearer {t}"},
    method="POST"), timeout=15)
print(f"HA restart: {r.status}")
