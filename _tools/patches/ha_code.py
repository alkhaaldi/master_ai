import urllib.request, json

base = "http://localhost:8123"
req1 = urllib.request.Request(
    f"{base}/auth/login_flow",
    headers={"Content-Type": "application/json"},
    data=json.dumps({"client_id": "http://192.168.109.123:8123/", "handler": ["homeassistant", None], "redirect_uri": "http://192.168.109.123:8123/?auth_callback=1"}).encode(),
    method="POST")
flow = json.loads(urllib.request.urlopen(req1, timeout=10).read())
flow_id = flow["flow_id"]

req2 = urllib.request.Request(
    f"{base}/auth/login_flow/{flow_id}",
    headers={"Content-Type": "application/json"},
    data=json.dumps({"client_id": "http://192.168.109.123:8123/", "username": "salem", "password": "Oaa011oaa011"}).encode(),
    method="POST")
result = json.loads(urllib.request.urlopen(req2, timeout=10).read())
code = result.get("result", "")
print(code)
