import sys, base64, os
b64_file = "/tmp/v5.b64"
target = "/home/pi/master_ai/server.py"
mode = sys.argv[1]
if mode == "init":
    open(b64_file, "w").close()
    print("initialized")
elif mode == "chunk":
    data = sys.argv[2]
    with open(b64_file, "a") as f:
        f.write(data)
    sz = os.path.getsize(b64_file)
    print(f"appended, total={sz}")
elif mode == "finalize":
    with open(b64_file) as f:
        b64 = f.read()
    content = base64.b64decode(b64).decode("utf-8")
    with open(target, "w") as f:
        f.write(content)
    print(f"written {len(content)} bytes to {target}")
    os.remove(b64_file)
