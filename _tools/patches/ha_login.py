"""Use HA auth API to login and get access+refresh tokens"""
import urllib.request, json

# HA auth login flow
data = json.dumps({
    "client_id": "http://192.168.109.123:8123/",
    "grant_type": "password",
    "username": "salem",
    "password": "Love@ausha12"
}).encode()

req = urllib.request.Request(
    "http://localhost:8123/auth/token",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data="grant_type=password&client_id=http%3A%2F%2F192.168.109.123%3A8123%2F&username=salem&password=Love%40ausha12".encode(),
    method="POST"
)

try:
    r = urllib.request.urlopen(req, timeout=10)
    result = json.loads(r.read())
    print(f"SUCCESS!")
    print(f"access_token: {result.get('access_token', '')[:50]}...")
    print(f"token_type: {result.get('token_type')}")
    print(f"refresh_token: {result.get('refresh_token', '')[:50]}...")
    print(f"expires_in: {result.get('expires_in')}")
    # Write full token for injection
    with open("/tmp/ha_auth_result.json", "w") as f:
        json.dump(result, f)
    print("Saved to /tmp/ha_auth_result.json")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"ERROR {e.code}: {body}")
except Exception as e:
    print(f"ERROR: {e}")
