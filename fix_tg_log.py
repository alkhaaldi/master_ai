path = "/home/pi/master_ai/telegram_bot.py"
with open(path) as f:
    content = f.read()

# Remove FileHandler - let systemd handle logging
old = """logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/home/pi/master_ai/telegram_bot.log"),
    ],
)"""

new = """logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)"""

if old in content:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    print("FIXED")
else:
    print("NOT FOUND")
