import subprocess, sys

# Check if tvDatafeed is installed
print("=== Checking tvDatafeed ===")
try:
    import tvDatafeed
    print(f"tvDatafeed version: {tvDatafeed.__version__}")
except ImportError:
    print("tvDatafeed NOT INSTALLED!")

# Check pip packages
print("\n=== pip list (tv related) ===")
result = subprocess.run([sys.executable, "-m", "pip", "list"], capture_output=True, text=True)
for line in result.stdout.split("\n"):
    if "tv" in line.lower() or "trading" in line.lower() or "datafeed" in line.lower():
        print(f"  {line}")

# Check which python
print(f"\n=== Python: {sys.executable} ===")

# Check venv
import os
venv_pip = "/home/pi/master_ai/venv/bin/pip"
if os.path.exists(venv_pip):
    print(f"\nvenv pip exists: {venv_pip}")
    result = subprocess.run([venv_pip, "list"], capture_output=True, text=True)
    for line in result.stdout.split("\n"):
        if "tv" in line.lower() or "trading" in line.lower() or "datafeed" in line.lower():
            print(f"  {line}")
    if not any("tvdatafeed" in l.lower() for l in result.stdout.split("\n")):
        print("  *** tvDatafeed NOT in venv! ***")
