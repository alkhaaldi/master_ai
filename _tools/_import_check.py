import subprocess, sys
result = subprocess.run(
    ['/home/pi/master_ai/venv/bin/python', '-c', 
     'import server; print("IMPORT OK")'],
    capture_output=True, text=True, cwd='/home/pi/master_ai', timeout=30
)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
print("Return code:", result.returncode)
