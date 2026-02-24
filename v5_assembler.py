#!/usr/bin/env python3
import sys, base64, os, glob
d = "/home/pi/master_ai"
chunks = sorted(glob.glob(f"{d}/v5_chunk_*"))
if not chunks:
    print("ERROR: no chunks found"); sys.exit(1)
b64 = "".join(open(c).read() for c in chunks)
content = base64.b64decode(b64).decode("utf-8")
with open(f"{d}/server.py", "w") as f:
    f.write(content)
print(f"OK: assembled {len(chunks)} chunks -> {len(content)} bytes -> server.py")
for c in chunks:
    os.remove(c)
