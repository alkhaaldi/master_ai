import subprocess
result = subprocess.run(
    ["/home/pi/master_ai/venv/bin/pip", "install", "aiohttp"],
    capture_output=True, text=True, timeout=120
)
print(f"EXIT:{result.returncode}")
