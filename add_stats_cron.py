import subprocess
# Add daily stats cron (twice daily: midnight + noon)
result = subprocess.run("(crontab -l 2>/dev/null | grep -v daily_stats; echo '0 0,12 * * * /home/pi/master_ai/venv/bin/python3 /home/pi/master_ai/daily_stats.py') | crontab -",
    shell=True, capture_output=True, text=True)
print("CRON:", result.returncode)
result2 = subprocess.run("crontab -l", shell=True, capture_output=True, text=True)
print(result2.stdout)
