"""
One-time helper for personal Outlook.com headless: run locally with ALLOW_DEVICE_FLOW=true,
then prints MS_REFRESH_TOKEN to paste into cloud env.
"""
import msal
from pathlib import Path
from email_agent.config import load_config
cfg = load_config()
app = msal.PublicClientApplication(cfg["env"]["client_id"], authority=f"https://login.microsoftonline.com/{cfg['env']['tenant_id']}")
flow = app.initiate_device_flow(scopes=cfg["graph"]["scopes"])
print(flow["message"])
result = app.acquire_token_by_device_flow(flow)
print("\n=== RESULT ===")
print(result)
# cache file holds refresh_token; extract via msal cache
cache_path = Path(cfg["monitoring"]["state_file"]).parent / "msal_cache.bin"
print(f"\nCache written to {cache_path}")
# msal stores refresh tokens inside serialized cache JSON — grep for it
if cache_path.exists():
    txt = cache_path.read_text()
    # naive extract
    import json, re
    try:
        data = json.loads(txt)
        # tokens under RefreshToken
        for k,v in data.get("RefreshToken", {}).items():
            print(f"\nMS_REFRESH_TOKEN (paste into hosting secrets):\n{v.get('secret')}\n")
            break
    except Exception as e:
        print(f"Could not parse cache: {e}")
        print(txt[:2000])
