path = "/home/pi/master_ai/server.py"
with open(path) as f:
    content = f.read()

old = "- For statistics/counts/status of HA devices: use ha_get_state with entity_id=\"*\" then summarize"
new = """- For statistics/counts/status of HA devices: use ha_get_state with entity_id="*" then summarize
- For comparing devices over time: use ssh_run with cmd="curl -s http://localhost:9000/stats/daily?days=7" to get historical stats
- /stats/daily returns daily snapshots with total_entities, online, offline counts per day"""

if old in content:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    import py_compile
    try:
        py_compile.compile(path, doraise=True)
        print("OK")
    except:
        print("ERR")
else:
    print("NOT_FOUND")
