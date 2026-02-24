import shutil
shutil.copy("/home/pi/master_ai/server.py", "/home/pi/master_ai/server.py.pre_memory_bak")
with open("/home/pi/master_ai/memory_patch.py") as f:
    patch = f.read()
with open("/home/pi/master_ai/server.py") as f:
    code = f.read()
marker = 'if __name__ == "__main__":'
if "SMART MEMORY" in code:
    print("ALREADY_PATCHED")
elif marker in code:
    code = code.replace(marker, patch + "\n" + marker)
    with open("/home/pi/master_ai/server.py", "w") as f:
        f.write(code)
    print("PATCHED_OK")
else:
    print("MARKER_NOT_FOUND")
