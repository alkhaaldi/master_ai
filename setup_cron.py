import subprocess, os
# Make watchdog executable and add cron
os.system("chmod +x /home/pi/master_ai/watchdog_tg.sh")
# Set crontab
result = subprocess.run("echo '*/1 * * * * /bin/bash /home/pi/master_ai/watchdog_tg.sh' | crontab -", 
    shell=True, capture_output=True, text=True)
print("CRON:", result.returncode, result.stderr or "OK")
# Verify
result2 = subprocess.run("crontab -l", shell=True, capture_output=True, text=True)
print("LIST:", result2.stdout)
