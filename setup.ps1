# One-click headless setup for suckityouhackers@outlook.com (no laptop after bootstrap)
# Run: powershell -ExecutionPolicy Bypass -File setup.ps1
param(
  [string]$ClientId = "",
  [switch]$BootstrapOnly
)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

Write-Host "== Inbox Guardian — headless setup ==" -ForegroundColor Cyan
Write-Host "Mailbox: suckityouhackers@outlook.com | Mode: delegated (personal Outlook.com)" -ForegroundColor Yellow

# 1) Python + deps
try { py --version | Out-Null } catch { Write-Error "Python not found — install Python 3.11+ and retry"; exit 1 }
py -m pip install -q -r requirements.txt
Write-Host "[1/4] deps installed" -ForegroundColor Green

# 2) .env
if (-not (Test-Path ".env")) { Copy-Item ".env.suckityouhackers.example" ".env" }
if ($ClientId) {
  (Get-Content ".env") -replace "AZURE_CLIENT_ID=.*", "AZURE_CLIENT_ID=$ClientId" | Set-Content ".env" -Encoding utf8
  Write-Host "[2/4] AZURE_CLIENT_ID set to $ClientId" -ForegroundColor Green
} else {
  $cur = (Get-Content ".env" | Where-Object { $_ -match "^AZURE_CLIENT_ID=" })
  if ($cur -match "PASTE" -or $cur -eq "AZURE_CLIENT_ID=") {
    Write-Host "[2/4] ACTION REQUIRED: Create App Registration then re-run: .\setup.ps1 -ClientId YOUR_GUID" -ForegroundColor Red
    Write-Host "  Portal: https://portal.azure.com -> App registrations -> New -> Inbox Guardian Personal -> Any org + personal -> Register"
    Write-Host "  API perms Delegated: Mail.Read, Mail.ReadWrite, MailboxSettings.Read, offline_access -> Grant for yourself -> copy Client ID"
  } else { Write-Host "[2/4] .env already has Client ID" -ForegroundColor Green }
}

# 3) Bootstrap refresh token (one-time, needs browser)
if (-not $BootstrapOnly -and (Get-Content ".env" | Where-Object { $_ -match "^MS_REFRESH_TOKEN=PASTE" -or $_ -match "^MS_REFRESH_TOKEN=$" })) {
  Write-Host "[3/4] Bootstrap needed — will open device login" -ForegroundColor Yellow
  Write-Host "  Running: ALLOW_DEVICE_FLOW=true py bootstrap_refresh_token.py"
  Write-Host "  Sign in as suckityouhackers@outlook.com at https://microsoft.com/devicelogin"
  $env:ALLOW_DEVICE_FLOW="true"
  py bootstrap_refresh_token.py
  Write-Host "  -> Copy the printed MS_REFRESH_TOKEN into .env (MS_REFRESH_TOKEN=...), then re-run setup.ps1" -ForegroundColor Yellow
  exit 0
}
if (Test-Path "data/msal_cache.bin") { Write-Host "[3/4] msal cache present" -ForegroundColor Green }

# 4) Verify headless (mock + live if configured)
Write-Host "[4/4] Verifying..." -ForegroundColor Cyan
py -m email_agent.main --dry-run
Write-Host ""
Write-Host "To run headless 24/7 locally (demo): py -m email_agent.server  (then curl http://localhost:8000/health)" -ForegroundColor Cyan
Write-Host "To deploy headless cloud (no laptop): .\deploy.ps1  (needs Docker + secrets in .env)" -ForegroundColor Cyan
Write-Host "Copilot package ready: copilot/inbox-guardian-copilot.zip -> upload at https://admin.microsoft.com -> Integrated apps" -ForegroundColor Cyan
