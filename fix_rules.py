path = "/home/pi/master_ai/server.py"
with open(path) as f:
    content = f.read()

old = """Rules:
- For Windows tasks (install software, check Windows status, run Windows commands) use win_* types
- For Home Assistant tasks use ha_* types
- For Raspberry Pi diagnostics use ssh_run
- win_diagnostics needs no args, it collects everything automatically
- win_powershell is for specific PowerShell commands on Windows
- win_winget_install requires a package_id
- Entity IDs: domain.name_with_underscores"""

new = """Rules:
- For Windows tasks (install software, check Windows status, run Windows commands) use win_* types
- For Home Assistant tasks use ha_* types
- For Raspberry Pi diagnostics use ssh_run
- win_diagnostics needs no args, it collects everything automatically
- win_powershell is for specific PowerShell commands on Windows
- win_winget_install requires a package_id
- Entity IDs: domain.name_with_underscores
- For statistics/counts/status of HA devices: use ha_get_state with entity_id="*" then summarize
- For questions you can answer from context (like shift schedule, general knowledge): use respond_text only
- NEVER refuse or say "could not plan". Always try: use ha_get_state * if unsure, or respond_text to explain
- User speaks Kuwaiti Arabic. Respond in Kuwaiti Arabic always
- If task is ambiguous, make your best guess and execute. Don't ask for clarification"""

if old in content:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    import py_compile
    try:
        py_compile.compile(path, doraise=True)
        print("OK")
    except:
        print("ERR")
else:
    print("NOT_FOUND")
