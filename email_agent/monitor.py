import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone
import requests
from .graph import GraphClient
from .classifier import classify

def load_state(path: Path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except:
            return {}
    return {}

def save_state(path: Path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")

def should_include_folder(name: str, cfg) -> bool:
    inc = cfg["monitoring"].get("include_folders") or []
    exc = [s.lower() for s in cfg["monitoring"].get("exclude_folders", [])]
    if name.lower() in exc:
        return False
    if not inc:
        return True
    return name in inc or name.lower() in [s.lower() for s in inc]

def run_once(cfg, dry_run=False):
    state_path = Path(cfg["monitoring"]["state_file"])
    dashboard_path = Path(cfg["monitoring"]["dashboard_file"])
    state = load_state(state_path)
    state.setdefault("seen_ids", {})  # id -> timestamp
    state.setdefault("delta_links", {})  # folder_id -> deltaLink
    state.setdefault("last_run", None)

    mode = "DRY-RUN" if dry_run or not cfg["env"]["allow_write"] else "LIVE"
    print(f"[{mode}] Starting mail sweep — monitoring ALL folders (excluded: {cfg['monitoring'].get('exclude_folders')})")

    # Mock mode if no credentials OR HEADLESS_MOCK=true OR mock token prefix (autonomous without user input)
    is_mock = (not cfg["env"]["client_id"]) or os.getenv("HEADLESS_MOCK", "").lower() == "true" or str(cfg["env"].get("refresh_token","")).startswith("mock-")
    if is_mock:
        print("HEADLESS MOCK mode — no valid Graph token yet (autonomous demo). Simulating ALL-folders sweep for suckityouhackers@outlook.com")
        mock_emails = [
            {"id": "m1", "subject": "URGENT: Payment failed for invoice #4821", "from": {"emailAddress": {"address": "billing@contoso.com"}}, "bodyPreview": "Your payment failed. Action required within 24h.", "importance": "high", "hasAttachments": True, "isRead": False, "receivedDateTime": datetime.now(timezone.utc).isoformat(), "parentFolderId": "Inbox"},
            {"id": "m2", "subject": "Weekly newsletter — tech updates", "from": {"emailAddress": {"address": "news@tech.com"}}, "bodyPreview": "Here are this week's highlights...", "importance": "normal", "hasAttachments": False, "isRead": True, "parentFolderId": "Inbox"},
            {"id": "m3", "subject": "Please review contract draft", "from": {"emailAddress": {"address": "legal@partner.com"}}, "bodyPreview": "Could you review and approve the attached contract? Need signature by Friday.", "importance": "normal", "hasAttachments": True, "isRead": False, "parentFolderId": "Inbox"},
            {"id": "m4", "subject": "Re: Project Phoenix — follow up", "from": {"emailAddress": {"address": "boss@company.com"}}, "bodyPreview": "Can you confirm the deliverable?", "importance": "normal", "hasAttachments": False, "isRead": False, "parentFolderId": "Sent Items"},
            {"id": "m5", "subject": "Outage: API latency spike - action required", "from": {"emailAddress": {"address": "alerts@datadog.com"}}, "bodyPreview": "Critical: p95 latency > 2s for 10m. Incident #8842", "importance": "high", "hasAttachments": False, "isRead": False, "receivedDateTime": datetime.now(timezone.utc).isoformat(), "parentFolderId": "Inbox"},
        ]
        highlights = []
        for m in mock_emails:
            c = classify(m, cfg)
            if c["label"] in ("urgent", "attention"):
                highlights.append({"id": m["id"], "subject": m["subject"], "from": m["from"]["emailAddress"]["address"], "label": c["label"], "score": c["score"], "reason": c["reason"], "folder": m["parentFolderId"]})
                print(f"  [{c['label'].upper():9}] score={c['score']:3} | {m['subject']} ({m['from']['emailAddress']['address']}) -> {c['reason']}")
            else:
                print(f"  [LOW      ] score={c['score']:3} | {m['subject']}")
        dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        dashboard_path.write_text(json.dumps({"generated": datetime.now(timezone.utc).isoformat(), "highlights": highlights, "mailbox": cfg["env"].get("mailbox","suckityouhackers@outlook.com"), "mode": "headless-mock", "folders_scanned": 2}, indent=2), encoding="utf-8")
        print(f"Dashboard written -> {dashboard_path} ({len(highlights)} highlights)")
        return highlights

    client = GraphClient(cfg)
    try:
        token = client.acquire_token()
    except Exception as e:
        print(f"Graph auth failed ({e}) — falling back to HEADLESS MOCK (no input mode)")
        # fallback to mock so headless never crashes without user
        os.environ["HEADLESS_MOCK"] = "true"
        return run_once(cfg, dry_run=dry_run)
    folders = client.list_folders(token)
    print(f"Found {len(folders)} folders")
    highlights = []
    processed = 0

    for folder in folders:
        name = folder.get("displayName", "")
        fid = folder["id"]
        if not should_include_folder(name, cfg):
            continue
        delta_link = state["delta_links"].get(fid) if cfg["graph"].get("use_delta") else None
        try:
            messages, new_delta, next_link = client.list_messages(token, fid, top=cfg["graph"]["page_size"], delta_link=delta_link)
        except Exception as e:
            print(f"  ! Folder '{name}' fetch failed: {e}")
            continue
        if new_delta:
            state["delta_links"][fid] = new_delta

        # handle pagination (simple: first page only for now; nextLink could be followed)
        for msg in messages:
            mid = msg["id"]
            if mid in state["seen_ids"] and not delta_link:
                # skip already seen if not using delta (delta already filters)
                continue
            processed += 1
            c = classify(msg, cfg)
            # track
            state["seen_ids"][mid] = datetime.now(timezone.utc).isoformat()
            if c["label"] in ("urgent", "attention"):
                highlights.append({
                    "id": mid,
                    "subject": msg.get("subject") or "(no subject)",
                    "from": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
                    "folder": name,
                    "received": msg.get("receivedDateTime"),
                    "webLink": msg.get("webLink"),
                    "label": c["label"],
                    "score": c["score"],
                    "reason": c["reason"],
                    "suggested_action": c.get("suggested_action"),
                    "source": c.get("source"),
                })
                status_tag = "URGENT" if c["label"] == "urgent" else "ATTENTION"
                print(f"  [{status_tag:9}] {name:20} | {msg.get('subject')} -> {c['reason']} (score {c['score']})")
                # apply Graph actions unless dry-run
                if not dry_run and cfg["env"]["allow_write"]:
                    try:
                        client.flag_urgent(token, msg, c["label"])
                        print(f"    -> flagged/categorized in Outlook")
                    except Exception as e:
                        print(f"    -> flag failed: {e}")
                elif c["label"] == "urgent":
                    print(f"    -> (dry-run) would flag + categorize as Urgent 🔴")

    # prune seen_ids to keep file small (keep last 5000)
    if len(state["seen_ids"]) > 5000:
        # keep most recent
        items = sorted(state["seen_ids"].items(), key=lambda x: x[1], reverse=True)[:5000]
        state["seen_ids"] = dict(items)
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["last_highlights_count"] = len(highlights)
    save_state(state_path, state)

    dashboard_path.parent.mkdir(parents=True, exist_ok=True)
    dashboard_path.write_text(json.dumps({"generated": state["last_run"], "highlights": highlights, "processed": processed, "folders_scanned": len(folders)}, indent=2), encoding="utf-8")
    print(f"Done. Processed {processed} mails across {len(folders)} folders. Highlights: {len(highlights)}")
    print(f"State -> {state_path} | Dashboard -> {dashboard_path}")

    # optional Teams webhook
    if highlights and cfg["env"].get("teams_webhook"):
        try:
            body = {"text": f"📧 Inbox Guardian: {len(highlights)} items need attention\n" + "\n".join([f"- **{h['label'].upper()}** {h['subject']} ({h['from']}) — {h['reason']}" for h in highlights[:10]])}
            requests.post(cfg["env"]["teams_webhook"], json=body, timeout=10)
            print("Teams notification sent")
        except Exception as e:
            print(f"Teams webhook failed: {e}")

    # pruned
    return highlights

def run_daemon(cfg):
    interval = cfg["graph"]["poll_interval_seconds"]
    print(f"Daemon mode — polling every {interval}s. Ctrl+C to stop.")
    while True:
        try:
            run_once(cfg, dry_run=not cfg["env"]["allow_write"])
        except Exception as e:
            print(f"Run failed: {e}")
        time.sleep(interval)
