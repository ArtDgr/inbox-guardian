# Free headless (no laptop) — 3 options

## Recommended: GitHub Actions (free, no Docker, no VM)
- **Cost:** $0 — public repo unlimited mins, private 2000 mins/mo (sweep 15m ~ 0.3 min/run = ~900 min/mo)
- **How:** `email-agent/.github/workflows/sweep-free.yml:1` runs `python -m email_agent.main --once` every 15m on GitHub runners. Commits `data/highlights.json`. Copilot plugin `spec.url` = `https://raw.githubusercontent.com/<you>/<repo>/main/email-agent/data/highlights.json` (no server needed).
- **Setup 2 min:**
  1. Push `email-agent` to GitHub (public or private)
  2. Repo → Settings → Secrets and variables → Actions:
     - Secrets: `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` (or `MS_REFRESH_TOKEN` for personal Outlook), `OPENAI_API_KEY` (optional)
     - Variables: `MAILBOX_UPN=suckityouhackers@outlook.com`, `AUTH_MODE=delegated`, `HEADLESS_MOCK=false`
  3. Actions → `sweep-free` → Run workflow → check `data/highlights.json` committed
  4. Point `copilot/openapi.yaml:5` to raw URL or keep local tunnel for dev; repack zip → upload to Copilot

## Alt 1: Cloudflare Workers (free 100k req/d, cron)
- Workers cron triggers sweep, stores highlights in KV, serves `GET /highlights`. Secrets via `wrangler secret put`. Free.

## Alt 2: Render / Fly / Koyeb free tier (container, but spins down)
- `Dockerfile:1` + `deploy.ps1 -Target render` — Render free spins down after 15m, cron wakes it. Fly free allowance ~$5 credit covers 1x 256MB always-on for ~month. Less stable than GH Actions.

## Why not `loca.lt` / `ngrok`?
Ephemeral tunnel = laptop must stay on. GitHub Actions is laptop-free and survives reboot.

## Switch now
Want me to push current `email-agent` to a new GitHub repo and enable `sweep-free.yml`? Or generate Cloudflare Worker instead?
