import os
path = '/home/pi/master_ai/server.py'
with open(path, 'r') as f:
    content = f.read()

old = 'sqlite3.connect(os.path.join(BASE_DIR, "data", "audit.db"))'
new = 'sqlite3.connect(os.path.join(BASE_DIR, "data", "life.db"))'
count = content.count(old)
print(f"Found {count} occurrences of audit.db connect")

content = content.replace(old, new)

# Verify
count2 = content.count(new)
print(f"After replace: {count2} occurrences of life.db connect")

with open(path, 'w') as f:
    f.write(content)

print("DONE")
