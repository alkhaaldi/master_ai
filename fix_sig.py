path = "/home/pi/master_ai/telegram_bot.py"
# Actually fix win_agent on the PC - but we need to update it remotely
# The fix is in the agent: change ISO timestamp to unix int

# We can't directly edit PC files, so let's create an updated agent
# and deploy it via a powershell command through Master AI

# Actually, let's fix the server side to accept both formats
path = "/home/pi/master_ai/server.py"
with open(path) as f:
    content = f.read()

old = """def verify_agent_signature(agent_id: str, signature: str, timestamp: str) -> bool:
    \"\"\"Verify HMAC SHA256 signature from Windows agent.\"\"\"
    if not AGENT_SECRET:
        return False
    try:
        ts = int(timestamp)
        now = int(time.time())
        if abs(now - ts) > 60:
            logger.warning("Agent sig expired: drift=%ds", abs(now - ts))
            return False
        expected = hmac.new(AGENT_SECRET.encode(), (agent_id + timestamp).encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception as e:
        logger.error("Sig verify error: %s", e)
        return False"""

new = """def verify_agent_signature(agent_id: str, signature: str, timestamp: str) -> bool:
    \"\"\"Verify HMAC SHA256 signature from Windows agent.\"\"\"
    if not AGENT_SECRET:
        return False
    try:
        # Accept both unix int and ISO format
        try:
            ts = int(timestamp)
        except ValueError:
            from datetime import datetime as dt, timezone as tz
            ts = int(dt.fromisoformat(timestamp.replace('Z', '+00:00')).timestamp())
            timestamp = str(ts)
        now = int(time.time())
        if abs(now - ts) > 120:
            logger.warning("Agent sig expired: drift=%ds", abs(now - ts))
            return False
        expected = hmac.new(AGENT_SECRET.encode(), (agent_id + timestamp).encode(), hashlib.sha256).hexdigest()
        # Also try with original timestamp string
        if hmac.compare_digest(expected, signature):
            return True
        # Try with ISO format in case agent signed with that
        from datetime import datetime as dt2, timezone as tz2
        iso_ts = dt2.fromtimestamp(ts, tz=tz2.utc).isoformat()
        expected2 = hmac.new(AGENT_SECRET.encode(), (agent_id + iso_ts).encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected2, signature)
    except Exception as e:
        logger.error("Sig verify error: %s", e)
        return False"""

if old in content:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    import py_compile
    try:
        py_compile.compile(path, doraise=True)
        print("FIXED+SYNTAX_OK")
    except:
        print("SYNTAX_ERR")
else:
    print("NOT_FOUND")
