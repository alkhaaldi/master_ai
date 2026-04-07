import ast
try:
    ast.parse(open('/home/pi/master_ai/server.py').read())
    print("SYNTAX OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR at line {e.lineno}: {e.msg}")
    print(f"Text: {e.text}")
