import urllib.request, urllib.parse, json

# Login via HA auth API
data = urllib.parse.urlencode({
    "grant_type": "password",
    "client_id": "http://192.168.109.123:8123/",
    "username": "salem",
    "password": "Oaa011oaa011"
}).encode()

req = urllib.request.Request(
    "http://localhost:8123/auth/token",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data=data, method="POST"
)

try:
    r = urllib.request.urlopen(req, timeout=10)
    result = json.loads(r.read())
    print("LOGIN SUCCESS!")
    print(json.dumps(result, indent=2))
    with open("/tmp/ha_tokens.json", "w") as f:
        json.dump(result, f)
except urllib.error.HTTPError as e:
    print(f"HTTP ERROR {e.code}: {e.read().decode()}")
except Exception as e:
    print(f"ERROR: {e}")
