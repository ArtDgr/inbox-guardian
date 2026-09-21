# Email Copilot Agent — HEADLESS (no laptop)

Monitors **ALL Outlook folders** 24/7 via Microsoft Graph, classifies every new mail (heuristics + LLM), and surfaces **Urgent 🔴 / Needs Attention 🟡** inside Microsoft 365 Copilot + Outlook flags + Teams digest — **entirely in the cloud**, no laptop involved.

## Architecture — headless
```
Outlook (M365) ──Graph API (app-only)──> email_agent/server.py  ──> data/highlights.json
                                          ├─ scheduler thread: polls ALL folders every 3 min (delta queries, state.json)
                                          ├─ REST API: GET /highlights, POST /trigger, GET /health  (for Copilot)
                                          ├─ Outlook actions: flag + category "Urgent 🔴" (when ALLOW_WRITE=true)
                                          └─ Teams webhook digest
                                                             │
M365 Copilot Chat ── Declarative Agent (copilot/declarative-agent.json) ──> https://YOUR_HOST/highlights
```
Host = Azure Container Apps (recommended, in Microsoft cloud), Fly.io, Render, or any Docker host. Also provided: GitHub Actions deploy + Bicep infra.

## Quick start — headless vs local

| Mode | Where it runs | Auth | Laptop needed? |
|------|---------------|------|----------------|
| **Headless app-only** (work/school M365) | Container in Azure/Fly | `client_credentials` + `MAILBOX_UPN` | **No** — one-time admin consent only |
| **Headless delegated** (personal Outlook.com) | Same container | `MS_REFRESH_TOKEN` after 1 bootstrap | **No after bootstrap** (1 local run to capture refresh token) |
| Local demo/mock | Your machine | none (mock data) | Yes — for testing only |

## 1) Mock demo (no Azure, proves classifier works)
```powershell
cd "C:\Users\Admin\Documents\Default Project\email-agent"
py -m pip install -r requirements.txt
copy .env.example .env   # leave AZURE_CLIENT_ID empty
py -m email_agent.main --dry-run   # classifies 4 synthetic mails → data/highlights.json
```

## 2) Headless deploy — Work/School M365 (app-only, recommended)

### Azure setup (once, 5 min)
1. Portal → App registrations → New → `Inbox Guardian Headless` → Accounts in this org only → Register.
2. API permissions → **Application** (not Delegated) → Add `Mail.Read`, `Mail.ReadWrite`, `MailboxSettings.Read` → **Grant admin consent**.
3. Certificates & secrets → New client secret → copy value.
4. Copy Application (client) ID + Directory (tenant) ID.

### Deploy to Azure Container Apps (zero laptop after this)
```powershell
az group create -n rg-inbox-guardian -l eastus
az acr create -n myacr -g rg-inbox-guardian --sku Basic
docker build -t myacr.azurecr.io/inbox-guardian:latest ./email-agent
az acr login -n myacr; docker push myacr.azurecr.io/inbox-guardian:latest

az deployment group create -g rg-inbox-guardian -f infra/azure-containerapp.bicep `
  -p containerImage=myacr.azurecr.io/inbox-guardian:latest mailboxUpn="you@company.com" azureClientId="..." azureClientSecret="..." azureTenantId="..." apiKey="strong-32-char" openAiKey="sk-..."
```
Check: `curl -H "X-API-Key: strong-32-char" https://<fqdn>/health`  → `{"status":"ok"}`
Highlights: `curl -H "X-API-Key: strong-32-char" https://<fqdn>/highlights`

Fly.io / Render alternative: `fly launch --dockerfile Dockerfile; fly secrets set AZURE_CLIENT_ID=... AZURE_TENANT_ID=... AZURE_CLIENT_SECRET=... MAILBOX_UPN=... OPENAI_API_KEY=... API_KEY=...; fly deploy` — see `infra/README.md`.

### Personal Outlook.com (no tenant admin) — headless via refresh_token
App-only won’t work. Do one local bootstrap once, then it’s headless forever:
```powershell
$env:ALLOW_DEVICE_FLOW="true"; $env:AUTH_MODE="device_flow"; py bootstrap_refresh_token.py
# paste the printed MS_REFRESH_TOKEN into your cloud secrets, set AUTH_MODE=delegated
```

## 3) Copilot integration (makes Copilot manage your email)
1. Deploy headless host first (above) → note `https://YOUR_HOST`.
2. Edit `copilot/openapi.yaml` → set `servers.url` to `https://YOUR_HOST`.
3. Import `copilot/declarative-agent.json` + `copilot/api-plugin.json` via **Teams Toolkit** or **M365 Admin Center → Integrated apps → Upload custom app**.
4. In Copilot Chat: "What urgent emails need my attention?" → agent calls `GET https://YOUR_HOST/highlights` and answers with triaged list (reason, score, folder, webLink), with actions to open/flag in Outlook.

If you cannot host: use **Power Automate** pure-cloud flow (trigger: When new email arrives V3 → call OpenAI classify → flag) — no container needed. Ask me to generate the flow JSON.

## 4) Configure urgency
Edit `config.yaml`:
- `vip_senders` / `vip_domains` — boss, key clients always attention+
- `urgent_keywords` / `attention_keywords`
- `thresholds` (urgent 75, attention 50)
- `classifier.llm` — headless defaults to `openai:gpt-4o-mini`; set `enabled:false` for pure heuristics or switch to `ollama` if you self-host.
- `exclude_folders`: `["Drafts","Conversation History"]`
- `ALLOW_WRITE=false` until you’ve verified dry-run highlights, then flip to `true` to let it flag/categorize in Outlook.

## Verify
```powershell
py -m email_agent.main --dry-run          # mock or live read-only sweep
py -m email_agent.server                  # headless-sim locally: scheduler + API on :8000
curl http://localhost:8000/health
curl http://localhost:8000/highlights
curl -X POST http://localhost:8000/trigger
```

## Security — headless
- No tokens in repo (`.env`, `msal_cache.bin` gitignored; secrets in Container App / Key Vault).
- `API_KEY` protects `/highlights` when hosted; Copilot plugin can send `X-API-Key`.
- Full bodies never logged; only subject/sender snippet sent to LLM.
- `ALLOW_WRITE=false` default — read-only until you explicitly enable.

## Files
- `email_agent/server.py` — headless entrypoint (scheduler + FastAPI, `PORT` env, `Dockerfile` CMD)
- `email_agent/graph.py` — Graph client (app-only `/users/{mailbox}` + refresh_token headless, delta queries)
- `email_agent/classifier.py` — heuristic + OpenAI/Ollama scorer
- `email_agent/monitor.py` — ALL-folders sweep → `data/highlights.json` + Teams
- `infra/azure-containerapp.bicep` + `.github/workflows/deploy.yml` — one-command cloud deploy
- `copilot/` — declarative-agent + OpenAPI for Copilot grounding

## Need me to finish?
Tell me: work M365 vs personal Outlook.com, and I’ll pre-fill the secrets template and run the Bicep deploy (or generate the Power Automate flow if you prefer zero infra).
