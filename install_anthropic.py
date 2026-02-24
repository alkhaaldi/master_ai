import subprocess, sys
result = subprocess.run(
    ["/home/pi/master_ai/venv/bin/pip", "install", "anthropic"],
    capture_output=True, text=True, timeout=120
)
with open("/tmp/pip_result.txt", "w") as f:
    f.write(f"EXIT: {result.returncode}\n")
    f.write(f"OUT: {result.stdout[-500:]}\n")
    f.write(f"ERR: {result.stderr[-500:]}\n")
print(f"EXIT:{result.returncode}")
