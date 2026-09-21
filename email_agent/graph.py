import msal
import requests
import time
import os
from pathlib import Path

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

class GraphClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self.env = cfg["env"]
        self.client_id = self.env["client_id"]
        self.tenant_id = self.env["tenant_id"] or "common"
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.scopes = cfg["graph"]["scopes"]
        self.mailbox = self.env.get("mailbox", "")  # UPN for app-only: user@tenant.onmicrosoft.com
        # msal cache on disk (persisted to volume in container)
        self.cache_path = Path(cfg["monitoring"]["state_file"]).parent / "msal_cache.bin"
        self.cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            try:
                self.cache.deserialize(self.cache_path.read_text())
            except Exception:
                pass
        self.app = msal.PublicClientApplication(
            self.client_id, authority=self.authority, token_cache=self.cache
        )
        self._confidential_app = None
        if self.env.get("client_secret"):
            self._confidential_app = msal.ConfidentialClientApplication(
                self.client_id, authority=self.authority,
                client_credential=self.env["client_secret"],
                token_cache=self.cache
            )

    def _save_cache(self):
        if self.cache.has_state_changed:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(self.cache.serialize())

    def acquire_token(self) -> str:
        # 1) Headless app-only (client_credentials) — PREFERRED for no-laptop
        if self._confidential_app and self.env.get("auth_mode") == "client_credentials":
            result = self._confidential_app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
            if "access_token" in result:
                self._save_cache()
                return result["access_token"]
            raise RuntimeError(f"client_credentials flow failed: {result} — ensure app has Application permissions + admin consent")

        # 2) Headless delegated via stored refresh_token (personal Outlook.com without tenant admin)
        if self.env.get("refresh_token"):
            # exchange refresh_token for access token via confidential or public client
            try:
                import requests as _req
                data = {
                    "client_id": self.client_id,
                    "scope": " ".join(self.scopes) + " offline_access",
                    "refresh_token": self.env["refresh_token"],
                    "grant_type": "refresh_token",
                }
                if self.env.get("client_secret"):
                    data["client_secret"] = self.env["client_secret"]
                token_url = f"{self.authority}/oauth2/v2.0/token"
                r = _req.post(token_url, data=data, timeout=15)
                r.raise_for_status()
                j = r.json()
                if "access_token" in j:
                    # persist new refresh_token if rotated
                    if j.get("refresh_token"):
                        # Note: caller should rotate MS_REFRESH_TOKEN in env/KeyVault
                        pass
                    return j["access_token"]
            except Exception as e:
                raise RuntimeError(f"refresh_token exchange failed: {e}")

        # 3) Silent cache (if previously authenticated headlessly via one-time bootstrap)
        accounts = self.app.get_accounts()
        result = None
        if accounts:
            result = self.app.acquire_token_silent(self.scopes, account=accounts[0])
            if result and "access_token" in result:
                self._save_cache()
                return result["access_token"]

        # 4) Interactive device_flow — NOT headless, only for local bootstrap
        if os.getenv("ALLOW_DEVICE_FLOW", "false").lower() == "true":
            flow = self.app.initiate_device_flow(scopes=self.scopes)
            if "user_code" not in flow:
                raise RuntimeError(f"Failed to create device flow: {flow}")
            print(flow["message"])
            print(f"User code: {flow['user_code']}  — open {flow['verification_uri']}")
            result = self.app.acquire_token_by_device_flow(flow)
            if "access_token" not in result:
                raise RuntimeError(f"Device flow failed: {result}")
            self._save_cache()
            return result["access_token"]

        raise RuntimeError(
            "No headless auth available. Set AUTH_MODE=client_credentials + AZURE_CLIENT_SECRET + MAILBOX_UPN (app-only, recommended) "
            "OR set MS_REFRESH_TOKEN (delegated headless after one-time bootstrap). "
            "For initial bootstrap locally, set ALLOW_DEVICE_FLOW=true and run once to capture refresh token."
        )

    def _headers(self, token):
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _base_path(self):
        # headless app-only must address /users/{mailbox}, delegated uses /me
        if self.env.get("auth_mode") == "client_credentials" and self.mailbox:
            return f"{GRAPH_BASE}/users/{self.mailbox}"
        return f"{GRAPH_BASE}/me"

    def list_folders(self, token):
        base = self._base_path()
        url = f"{base}/mailFolders?$top=100"
        resp = requests.get(url, headers=self._headers(token))
        resp.raise_for_status()
        folders = resp.json().get("value", [])
        # expand child folders
        all_folders = list(folders)
        for f in folders:
            if f.get("childFolderCount", 0) > 0:
                url2 = f"{base}/mailFolders/{f['id']}/childFolders?$top=100"
                r2 = requests.get(url2, headers=self._headers(token))
                if r2.ok:
                    all_folders.extend(r2.json().get("value", []))
        return all_folders

    def list_messages(self, token, folder_id, top=25, delta_link=None):
        # delta for efficient polling if enabled
        if delta_link:
            url = delta_link
        else:
            base = self._base_path()
            url = f"{base}/mailFolders/{folder_id}/messages?$top={top}&$orderby=receivedDateTime desc&$select=id,subject,from,receivedDateTime,bodyPreview,importance,hasAttachments,isRead,flag,parentFolderId,webLink,categories"
        resp = requests.get(url, headers=self._headers(token))
        resp.raise_for_status()
        data = resp.json()
        return data.get("value", []), data.get("@odata.deltaLink"), data.get("@odata.nextLink")

    def update_message(self, token, message_id, patch: dict):
        """Apply flag/category/importance. Only if ALLOW_WRITE true."""
        if not self.cfg["env"]["allow_write"]:
            return {"dry_run": True, "patch": patch}
        url = f"{self._base_path()}/messages/{message_id}"
        resp = requests.patch(url, headers=self._headers(token), json=patch)
        resp.raise_for_status()
        return resp.json()

    def flag_urgent(self, token, msg: dict, label: str):
        actions = self.cfg["monitoring"]["actions"].get(label, {})
        patch = {}
        if actions.get("flag"):
            patch["flag"] = {"flagStatus": "flagged"}
        if actions.get("category"):
            # categories is array; Graph will replace
            existing = msg.get("categories", []) or []
            cat = actions["category"]
            if cat not in existing:
                patch["categories"] = existing + [cat]
        if actions.get("importance"):
            patch["importance"] = actions["importance"]
        if not patch:
            return None
        return self.update_message(token, msg["id"], patch)
