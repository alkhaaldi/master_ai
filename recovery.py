#!/usr/bin/env python3
"""Master AI Recovery Service - port 9001
Lightweight emergency service for when master-ai crashes.
"""
import subprocess, json, os
from http.server import HTTPServer, BaseHTTPRequestHandler

# Read API key from .env
API_KEY = ""
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    for line in open(env_path):
        if line.startswith("MASTER_AI_API_KEY="):
            API_KEY = line.split("=", 1)[1].strip()
WORK_DIR = "/home/pi/master_ai"

class Handler(BaseHTTPRequestHandler):
    def _auth(self):
        key = self.headers.get("X-API-Key", "")
        if key != API_KEY:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":"unauthorized"}')
            return False
        return True

    def _json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "X-API-Key, Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _run(self, cmd, timeout=30):
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=WORK_DIR)
            return {"stdout": r.stdout.strip(), "stderr": r.stderr.strip(), "code": r.returncode}
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": "timeout", "code": -1}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "X-API-Key, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._json({"status": "recovery_ok", "port": 9001})
            return
        if not self._auth(): return
        actions = {
            "/status": lambda: {"master_ai": self._run("sudo systemctl is-active master-ai")["stdout"]},
            "/logs": lambda: {"logs": self._run("journalctl -u master-ai -n 30 --no-pager 2>&1")["stdout"]},
            "/check": lambda: (lambda r: {"syntax_ok": r["code"]==0, "error": r["stderr"]})(self._run("python3 -c \"compile(open('server.py').read(),'s','exec')\"")),
            "/gitlog": lambda: {"log": self._run("git log --oneline -10")["stdout"]},
        }
        fn = actions.get(self.path)
        if fn: self._json(fn())
        else: self._json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._auth(): return
        if self.path == "/run":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            cmd = body.get("cmd", "")
            if not cmd:
                self._json({"error": "no cmd"}, 400)
                return
            blocked = ["rm -rf /", "mkfs", "dd if=", "> /dev/"]
            if any(b in cmd for b in blocked):
                self._json({"error": "blocked"}, 403)
                return
            self._json(self._run(cmd, timeout=body.get("timeout", 30)))
            return
        actions = {
            "/restart": "sudo systemctl restart master-ai",
            "/stop": "sudo systemctl stop master-ai",
            "/start": "sudo systemctl start master-ai",
            "/revert": "git revert --no-edit HEAD && sudo systemctl restart master-ai",
            "/reset1": "git reset --hard HEAD~1 && sudo systemctl restart master-ai",
        }
        cmd = actions.get(self.path)
        if cmd:
            self._json({"action": self.path, "result": self._run(cmd)})
        else:
            self._json({"error": "not found"}, 404)

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    print(f"Recovery service on :9001 (key={'set' if API_KEY else 'MISSING'})")
    HTTPServer(("0.0.0.0", 9001), Handler).serve_forever()
