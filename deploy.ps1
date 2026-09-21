# Deploy headless container (no laptop) — requires Docker + .env filled
# Supports: Azure Container Apps, Fly.io, or local Docker run
param([string]$Target = "local", [string]$Image = "inbox-guardian:latest")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# Load .env
Get-Content ".env" | ForEach-Object {
  if ($_ -match "^([^#=]+)=(.*)$") { $k=$Matches[1].Trim(); $v=$Matches[2].Trim(); Set-Item -Path "env:$k" -Value $v }
}
if (-not $env:AZURE_CLIENT_ID) { Write-Error ".env AZURE_CLIENT_ID empty — run .\setup.ps1 -ClientId YOUR_ID first"; exit 1 }
if (-not $env:MS_REFRESH_TOKEN) { Write-Warning "MS_REFRESH_TOKEN empty — bootstrap first: ALLOW_DEVICE_FLOW=true py bootstrap_refresh_token.py" }

switch ($Target) {
  "local" {
    Write-Host "Building Docker image $Image ..." -ForegroundColor Cyan
    docker build -t $Image .
    Write-Host "Running headless locally on :8000 ..." -ForegroundColor Green
    docker run --rm -p 8000:8000 --env-file .env $Image
  }
  "fly" {
    Write-Host "Deploying to Fly.io ..." -ForegroundColor Cyan
    flyctl launch --dockerfile Dockerfile --region syd --no-deploy 2>$null; flyctl secrets set AZURE_CLIENT_ID="$env:AZURE_CLIENT_ID" AZURE_TENANT_ID="$env:AZURE_TENANT_ID" AUTH_MODE="$env:AUTH_MODE" MAILBOX_UPN="$env:MAILBOX_UPN" MS_REFRESH_TOKEN="$env:MS_REFRESH_TOKEN" API_KEY="$env:API_KEY" OPENAI_API_KEY="$env:OPENAI_API_KEY" 2>&1 | Write-Host; flyctl deploy
  }
  "azure" {
    Write-Host "Azure Container Apps — ensure az login + rg-inbox-guardian exists" -ForegroundColor Cyan
    Write-Host "Example: az deployment group create -g rg-inbox-guardian -f infra/azure-containerapp.bicep -p containerImage=myacr.azurecr.io/inbox-guardian:latest mailboxUpn=$env:MAILBOX_UPN azureClientId=$env:AZURE_CLIENT_ID azureClientSecret=... azureTenantId=$env:AZURE_TENANT_ID apiKey=$env:API_KEY"
  }
  default { Write-Error "Unknown target $Target — use local|fly|azure" }
}
