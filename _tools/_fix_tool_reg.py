"""Fix: use already-imported journal functions, don't re-import."""
import os, shutil

with open("server.py", "r") as f:
    content = f.read()

old = '''    # -- Journal --
    if JOURNAL_OK:
        try:
            from journal_engine import get_open_trades, get_trade_stats
            tool_reg.register("open_trades", get_open_trades, category="trading",
                              description="Current open trading positions")
            tool_reg.register("trade_stats", get_trade_stats, category="trading",
                              description="Trading statistics summary")
        except Exception:
            pass'''

new = '''    # -- Journal --
    if JOURNAL_OK:
        try:
            tool_reg.register("open_trades", get_open_trades, category="trading",
                              description="Current open trading positions")
            tool_reg.register("trade_stats", get_trade_stats, category="trading",
                              description="Trading statistics summary")
        except Exception:
            pass'''

content = content.replace(old, new, 1)
print("Fixed: removed redundant journal import in tool registration")

with open("/tmp/server_patched.py", "w") as f:
    f.write(content)
os.remove("server.py")
shutil.move("/tmp/server_patched.py", "server.py")
print("Done.")
