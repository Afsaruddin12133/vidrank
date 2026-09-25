# Mac-OFF Runbook (2-Day Period) — What Runs, What Waits, Resume Checklist

*Prepared Sep 11, 2026 for the Mac-off period.*

---

## Runs WITHOUT the Mac (fully online)

| Automation | Schedule | What it does |
|---|---|---|
| **seo-agent Worker** (`seo-agent.fahad288ali.workers.dev`) | Daily 09:00 Dhaka | DataForSEO keyword gaps → AI brain (free model) → decides up to 3 title/meta fixes → **commits fixes to GitHub** → writes run log to KV |
| GSC rankings pull | Same run | **Only after** the online OpenSEO is deployed + GSC connected (see Pending) |

The agent's commits land on `github.com/Afsaruddin12133/vidrank` — visible from any phone/browser.

## Does NOT run while the Mac is off

- Local OpenSEO container (Docker) — paused, irrelevant for the cloud loop
- Mac launchd seo-god loop — skipped (coalesces on wake when you return)
- Local GSC OAuth capture — superseded by the online OpenSEO GSC connection

## The 2 pending user tasks (block cloud completeness)

1. **R2 activation** — checkout page (`dash.cloudflare.com/.../r2/checkout/payment`): fill card → tick 2 checkboxes → Activate R2. Unblocks: OpenSEO online deployment.
2. **CLOUDFLARE_API_TOKEN** — [API Tokens](https://dash.cloudflare.com/profile/api-tokens) → Create Token → Edit Cloudflare Workers template → **+ add permission: Account → Cloudflare Pages → Edit** → paste the token (unblocks: auto-deploy of agent fixes).

## Resume checklist (when Mac returns)

1. `cd /tmp/open-seo && pnpm deploy:selfhost --yes` — deploy OpenSEO online (needs R2 done first; alchemy login may need refresh: `pnpm alchemy login`)
2. Open the printed Worker URL → sign in via CF Access (fahad288ali@gmail.com) → register vidrank.tech project → Settings → connect Google Search Console (Google consent in browser)
3. `cd ~/seo-agent-worker && npx wrangler secret put ONLINE_OPENSEO_URL` → paste the online OpenSEO URL → the agent's GSC path activates automatically
4. Trigger a manual test: open `https://seo-agent.fahad288ali.workers.dev/?run=1&token=<RUN_TOKEN in ~/seo-agent-worker/.run-token>`
5. `cd /Users/macm1/Desktop/vidrank/landing-page && npm run pages:deploy` — publish any agent fixes that accumulated on GitHub (or set the CLOUDFLARE_API_TOKEN GH secret so pushes auto-deploy)
6. Check `gh run list` / GitHub commits for what the agent produced over the 2 days

## Where things live

| Thing | Location |
|---|---|
| Agent code + secrets | `~/seo-agent-worker/` (`.run-token` has the manual trigger token) |
| Online OpenSEO | `<alchemy-deployed workers.dev URL>` (printed at deploy end) |
| Agent's commits | GitHub main branch, message prefix `seo-agent:` |
| Mac fallback loop | launchd `com.seo-god.daily` 09:00 (kept as safety net) |
| Docs | `seo/DEPLOYMENT-STATUS.md`, `seo/HARNESS-ARCHITECTURE.md`, `seo/AGENTIC-SEO-RESEARCH.md` |
