import subprocess
result = subprocess.run(
    ["/home/pi/master_ai/venv/bin/pip", "install", "python-telegram-bot"],
    capture_output=True, text=True, timeout=120
)
print(f"EXIT:{result.returncode}")
if result.returncode != 0:
    print(result.stderr[-300:])
