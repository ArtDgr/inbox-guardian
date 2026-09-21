"""
Copilot plugin helper — exposes highlights.json as an API for M365 Copilot declarative agent.
Run: python -m email_agent.copilot_plugin --serve --port 8000
Endpoints:
  GET /highlights  -> current urgent/attention list
  GET /health
  POST /classify  {subject, bodyPreview, from}
"""
import json
import argparse
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from .config import load_config

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        cfg = load_config()
        if self.path.startswith("/highlights"):
            p = Path(cfg["monitoring"]["dashboard_file"])
            data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"highlights": [], "generated": None}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        elif self.path.startswith("/health"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"not found"}')

    def do_POST(self):
        if self.path.startswith("/classify"):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            import json as _json
            payload = _json.loads(body.decode() or "{}")
            from .classifier import classify
            from .config import load_config as lc
            cfg = lc()
            # build minimal email dict
            email = {
                "subject": payload.get("subject", ""),
                "bodyPreview": payload.get("bodyPreview") or payload.get("body", ""),
                "from": {"emailAddress": {"address": payload.get("from", "")}},
                "importance": payload.get("importance", "normal"),
                "hasAttachments": payload.get("hasAttachments", False),
                "isRead": payload.get("isRead", False),
            }
            result = classify(email, cfg)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_json.dumps(result).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        print(fmt % args)

def serve(port=8000):
    server_address = ("", port)
    httpd = HTTPServer(server_address, Handler)
    print(f"Copilot plugin API listening on http://localhost:{port}  (GET /highlights, POST /classify)")
    httpd.serve_forever()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.serve:
        serve(args.port)
    else:
        cfg = load_config()
        p = Path(cfg["monitoring"]["dashboard_file"])
        print(p.read_text(encoding="utf-8") if p.exists() else "No highlights yet — run python -m email_agent.main --once")
