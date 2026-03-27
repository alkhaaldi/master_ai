import urllib.request, json

base = "http://localhost:8123"

# Step 1: Create login flow
req1 = urllib.request.Request(
    f"{base}/auth/login_flow",
    headers={"Content-Type": "application/json"},
    data=json.dumps({
        "client_id": "http://192.168.109.123:8123/",
        "handler": ["homeassistant", None],
        "redirect_uri": "http://192.168.109.123:8123/?auth_callback=1"
    }).encode(),
    method="POST"
)
r1 = urllib.request.urlopen(req1, timeout=10)
flow = json.loads(r1.read())
flow_id = flow.get("flow_id")
print(f"Step 1: flow_id={flow_id}")
print(f"  type={flow.get('type')}, step_id={flow.get('step_id')}")

# Step 2: Submit credentials
req2 = urllib.request.Request(
    f"{base}/auth/login_flow/{flow_id}",
    headers={"Content-Type": "application/json"},
    data=json.dumps({
        "client_id": "http://192.168.109.123:8123/",
        "username": "salem",
        "password": "Oaa011oaa011"
    }).encode(),
    method="POST"
)
r2 = urllib.request.urlopen(req2, timeout=10)
result = json.loads(r2.read())
print(f"Step 2: type={result.get('type')}")

if result.get("type") == "create_entry":
    code = result.get("result")
    print(f"  AUTH CODE: {code}")
    
    # Step 3: Exchange code for tokens
    import urllib.parse
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": "http://192.168.109.123:8123/",
        "code": code
    }).encode()
    req3 = urllib.request.Request(
        f"{base}/auth/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=data, method="POST"
    )
    r3 = urllib.request.urlopen(req3, timeout=10)
    tokens = json.loads(r3.read())
    print(f"Step 3: ACCESS TOKEN obtained!")
    print(f"  access_token: {tokens.get('access_token','')[:60]}...")
    print(f"  refresh_token: {tokens.get('refresh_token','')[:60]}...")
    with open("/tmp/ha_tokens.json", "w") as f:
        json.dump(tokens, f)
    print("  Saved to /tmp/ha_tokens.json")
else:
    print(f"  FAILED: {json.dumps(result)}")
