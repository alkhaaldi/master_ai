import ast, sys
# Check the backup (original + ema-crosses/proximity from Claude Code)
try:
    ast.parse(open('/home/pi/master_ai/server.py.bak_ema21').read())
    print("bak_ema21: SYNTAX OK")
except SyntaxError as e:
    print(f"bak_ema21: SYNTAX ERROR: {e}")

# Check the broken one (with ema-active added by script)
import os
broken = '/home/pi/master_ai/server.py.bak_ema21'
# Actually we need to check what the script produced
# Let's regenerate it properly
