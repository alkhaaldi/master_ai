import urllib.request, json, time

# Wait for server
for i in range(15):
    time.sleep(4)
    try:
        r = urllib.request.urlopen('http://localhost:9000/health', timeout=5)
        d = json.loads(r.read())
        print(f"HEALTH: {d['status']} (uptime={d.get('uptime_seconds')}s)")
        break
    except:
        print(f"Waiting... attempt {i+1}")
else:
    print("SERVER NOT UP - checking logs")
    import subprocess
    result = subprocess.run(['tail', '-30', '/home/pi/master_ai/server.log'], capture_output=True, text=True)
    # Find the actual error
    for line in result.stdout.split('\n'):
        if 'Error' in line or 'error' in line or 'Traceback' in line or 'SyntaxError' in line:
            print(f"  >>> {line}")
    exit(1)

# Test ema-crosses
try:
    r = urllib.request.urlopen('http://localhost:9000/dashboard/ema-crosses?hours=240', timeout=10)
    d = json.loads(r.read())
    print(f"EMA-CROSSES: OK (total={d['total']})")
except Exception as e:
    print(f"EMA-CROSSES: FAIL ({e})")

# Test ema-active if it exists
try:
    r = urllib.request.urlopen('http://localhost:9000/dashboard/ema-active', timeout=10)
    d = json.loads(r.read())
    print(f"EMA-ACTIVE: OK (bull={d['bullish_count']}, bear={d['bearish_count']})")
except Exception as e:
    print(f"EMA-ACTIVE: FAIL ({e})")
