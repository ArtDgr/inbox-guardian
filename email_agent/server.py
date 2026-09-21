"""
Headless server — runs 24/7 without a laptop.
- Background scheduler: polls ALL Outlook folders every poll_interval_seconds
- HTTP API: GET /highlights, GET /health, POST /classify, POST /trigger (manual sweep)
- Designed for Azure Container Apps / App Service / Fly.io / any Docker host
- Auth: API_KEY env protects endpoints (optional)

Run locally headless-sim: python -m email_agent.server
In cloud: docker run -e AZURE_CLIENT_ID=... -e AZURE_CLIENT_SECRET=... -e MAILBOX_UPN=... -p 8000:8000 email-agent
"""
import os
import threading
import time
import json
from pathlib import Path
from datetime import datetime, timezone

from .config import load_config

def scheduler_loop(cfg):
    from .monitor import run_once
    interval = cfg["graph"]["poll_interval_seconds"]
    print(f"[scheduler] headless polling every {interval}s — mailbox={cfg['env'].get('mailbox','/me')} mode={cfg['env']['auth_mode']}")
    while True:
        try:
            # don't run if no credentials yet — sleep & retry
            if not cfg["env"]["client_id"]:
                print("[scheduler] no AZURE_CLIENT_ID — skipping sweep (set secrets in container env)")
            else:
                run_once(cfg, dry_run=not cfg["env"]["allow_write"])
        except Exception as e:
            print(f"[scheduler] sweep failed: {e}")
        time.sleep(interval)

def create_app():
    try:
        from fastapi import FastAPI, Header, HTTPException, Request
        from fastapi.responses import JSONResponse
    except ImportError:
        # fallback to stdlib http.server if fastapi not installed (still headless, but simpler)
        print("FastAPI not installed — falling back to stdlib HTTP server")
        from .copilot_plugin import serve
        return None

    from fastapi import FastAPI, Header, HTTPException, Request
    from fastapi.responses import JSONResponse
    cfg = load_config()
    app = FastAPI(title="Inbox Guardian — Headless", version="0.1.0")

    def require_key(x_api_key: str = Header(None)):
        expected = cfg["env"].get("api_key")
        if expected and x_api_key != expected:
            # allow empty if no API_KEY configured (open for Copilot plugin with auth None)
            if expected:
                raise HTTPException(status_code=401, detail="invalid API_KEY")

    @app.get("/health")
    def health():
        p = Path(cfg["monitoring"]["state_file"])
        state = {}
        if p.exists():
            try:
                state = json.loads(p.read_text(encoding="utf-8"))
            except: pass
        return {"status": "ok", "last_run": state.get("last_run"), "mailbox": cfg["env"].get("mailbox") or "me", "mode": cfg["env"]["auth_mode"]}

    @app.get("/highlights")
    def highlights(x_api_key: str = Header(None)):
        # FIX: Copilot plugin uses auth=None so it sends no X-API-Key. Make /highlights public for Copilot,
        # keep X-API-Key optional: only reject if header is present but wrong.
        expected = cfg["env"].get("api_key")
        if expected and x_api_key is not None and x_api_key != expected:
            raise HTTPException(status_code=401, detail="invalid API_KEY")
        p = Path(cfg["monitoring"]["dashboard_file"])
        if not p.exists():
            return {"generated": None, "highlights": [], "note": "no sweep yet — scheduler runs every {}s".format(cfg["graph"]["poll_interval_seconds"])}
        return json.loads(p.read_text(encoding="utf-8"))

    @app.post("/trigger")
    def trigger(x_api_key: str = Header(None)):
        if cfg["env"].get("api_key") and x_api_key != cfg["env"]["api_key"]:
            raise HTTPException(status_code=401, detail="invalid API_KEY")
        from .monitor import run_once
        h = run_once(cfg, dry_run=not cfg["env"]["allow_write"])
        return {"triggered": True, "highlights": h, "count": len(h)}

    @app.post("/classify")
    async def classify_ep(request: Request, x_api_key: str = Header(None)):
        if cfg["env"].get("api_key") and x_api_key != cfg["env"]["api_key"]:
            raise HTTPException(status_code=401, detail="invalid API_KEY")
        body = await request.json()
        from .classifier import classify as do_classify
        email = {
            "subject": body.get("subject", ""),
            "bodyPreview": body.get("bodyPreview") or body.get("body", ""),
            "from": {"emailAddress": {"address": body.get("from", "")}},
            "importance": body.get("importance", "normal"),
            "hasAttachments": body.get("hasAttachments", False),
            "isRead": body.get("isRead", False),
        }
        return do_classify(email, cfg)

    @app.get("/openapi.yaml")
    def openapi():
        from fastapi.responses import PlainTextResponse
        p = Path(__file__).resolve().parent.parent / "copilot" / "openapi.yaml"
        if p.exists():
            return PlainTextResponse(p.read_text(encoding="utf-8"), media_type="text/yaml")
        return PlainTextResponse("not found", status_code=404)

    @app.get("/")
    def root():
        return {"name": "Inbox Guardian headless", "health": "/health", "highlights": "/highlights", "trigger": "POST /trigger", "copilot": "point declarative-agent to https://YOUR_HOST/highlights"}

    return app

def main():
    cfg = load_config()
    # start scheduler in background thread (headless, no laptop)
    t = threading.Thread(target=scheduler_loop, args=(cfg,), daemon=True)
    t.start()

    # try FastAPI
    app = create_app()
    if app is not None:
        import uvicorn
        port = int(os.getenv("PORT", "8000"))
        print(f"[server] headless API listening on :{port}  (GET /highlights, POST /trigger)")
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        # fallback
        from .copilot_plugin import serve
        serve(port=int(os.getenv("PORT", "8000")))

if __name__ == "__main__":
    main()
