import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

def load_config():
    load_dotenv(ROOT / ".env")
    cfg_path = ROOT / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # env overrides — headless cloud-native defaults to client_credentials
    cfg.setdefault("env", {})
    cfg["env"]["allow_write"] = os.getenv("ALLOW_WRITE", "false").lower() == "true"
    cfg["env"]["client_id"] = os.getenv("AZURE_CLIENT_ID", "")
    cfg["env"]["tenant_id"] = os.getenv("AZURE_TENANT_ID", "common")
    cfg["env"]["client_secret"] = os.getenv("AZURE_CLIENT_SECRET", "")
    cfg["env"]["auth_mode"] = os.getenv("AUTH_MODE", "client_credentials")  # headless default
    cfg["env"]["mailbox"] = os.getenv("MAILBOX_UPN", "")  # required for app-only: user@domain.com
    cfg["env"]["teams_webhook"] = os.getenv("TEAMS_WEBHOOK_URL", cfg.get("notifications", {}).get("teams_webhook_url", ""))
    cfg["env"]["llm_api_key"] = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "ollama"
    cfg["env"]["api_key"] = os.getenv("API_KEY", "")  # protect /highlights endpoint when hosted
    if os.getenv("LLM_BASE_URL"):
        cfg["classifier"]["llm"]["base_url"] = os.getenv("LLM_BASE_URL")
    if os.getenv("LLM_MODEL"):
        cfg["classifier"]["llm"]["model"] = os.getenv("LLM_MODEL")
    # allow palette: also support delegated refresh_token for personal Outlook.com via headless
    cfg["env"]["refresh_token"] = os.getenv("MS_REFRESH_TOKEN", "")
    return cfg
