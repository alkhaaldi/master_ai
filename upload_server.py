#!/usr/bin/env python3
"""Lightweight upload server — receives raw file uploads on port 9001."""
import os, json, sys
from http.server import HTTPServer, BaseHTTPRequestHandler

API_KEY = os.getenv("MASTER_AI_API_KEY", "")
BASE = "/home/pi/master_ai"

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        key = self.headers.get("X-API-Key", "")
        if key != API_KEY:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":"unauthorized"}')
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        path = self.path.lstrip("/") or "upload.tmp"
        # Security: only allow files inside BASE
        target = os.path.join(BASE, os.path.basename(path))
        # Backup existing
        if os.path.exists(target):
            bak = target + ".bak"
            os.rename(target, bak)
        with open(target, "wb") as f:
            f.write(body)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        resp = {"ok": True, "path": target, "size": len(body)}
        self.wfile.write(json.dumps(resp).encode())
        print(f"Uploaded {target} ({len(body)} bytes)")
    
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"upload_server_ready","port":9001}')

    def log_message(self, format, *args):
        pass  # Quiet

print("Upload server starting on :9001")
HTTPServer(("0.0.0.0", 9001), H).serve_forever()
