# Headless hosting — no laptop

### Option A: Azure Container Apps (recommended, stays in Microsoft cloud)
1. `az group create -n rg-inbox-guardian -l eastus`
2. Build & push image:
   ```powershell
   az acr create -n myacr -g rg-inbox-guardian --sku Basic
   docker build -t myacr.azurecr.io/inbox-guardian:latest ./email-agent
   az acr login -n myacr
   docker push myacr.azurecr.io/inbox-guardian:latest
   ```
3. Deploy:
   ```powershell
   az deployment group create -g rg-inbox-guardian -f infra/azure-containerapp.bicep `
     -p containerImage=myacr.azurecr.io/inbox-guardian:latest mailboxUpn="you@company.com" azureClientId="..." azureClientSecret="..." azureTenantId="..." apiKey="..." openAiKey="sk-..."
   ```
4. Test: `curl https://<fqdn>/health`  (or with `H: X-API-Key`)

### Option B: Fly.io / Render / any Docker host (1-click)
```powershell
fly launch --dockerfile Dockerfile --region syd
fly secrets set AZURE_CLIENT_ID=... AZURE_TENANT_ID=... AZURE_CLIENT_SECRET=... MAILBOX_UPN=... OPENAI_API_KEY=... API_KEY=...
fly deploy
```

### Option C: Pure Microsoft — no container (Power Automate + Copilot)
If you cannot create an Azure app registration, use Power Automate cloud flow: trigger "When a new email arrives (V3)" on Inbox + child folders, call OpenAI classify, flag via Outlook connector. No laptop, no code. Ask me and I’ll generate the flow JSON.

### Personal Outlook.com (no tenant admin)
App-only won’t work. Do one-time bootstrap on any machine:
```powershell
$env:ALLOW_DEVICE_FLOW="true"; $env:AUTH_MODE="device_flow"; py -m email_agent.main --once
# copy MS_REFRESH_TOKEN from data/msal_cache.bin (or capture via script) -> paste as secret MS_REFRESH_TOKEN in hosting, with AUTH_MODE=delegated
```
Then hosting runs headless using the stored refresh_token (auto-rotates).
