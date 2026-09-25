# Online Automation — Status & How to Recheck

*Cloud worker: `seo-agent.fahad288ali.workers.dev` — daily 09:00 Dhaka (cron `0 3 * * *` UTC). Deployed & verified Sep 12, 2026.*

## One command to recheck everything

```bash
bash ~/seo-agent-worker/check.sh
```

Shows: last run time + result, cron config, agent commits, CI deploy status.

## What "working" looks like

| Check | Healthy | Broken |
|---|---|---|
| KV `lastRun` | `ok:true`, timestamp within ~25h | timestamp older than 25h = cron stopped; missing = never ran |
| KV `lastRun` day-over-day | timestamp advances daily | stuck = cron not firing → `cd ~/seo-agent-worker && npx wrangler deploy` |
| GitHub | `seo-agent:` commits appear as fixes found | `fatal` in lastRun log = read the `notes` field |
| CI | green "Deploy landing page" runs | red = check CLOUDFLARE_API_TOKEN secret |

## Manual trigger (instant proof, no waiting for 09:00)

```bash
curl -s "https://seo-agent.fahad288ali.workers.dev/?run=1&token=$(cat ~/seo-agent-worker/.run-token)"
```

Returns the full run log as JSON: `gsc_rows` count, `classified` regressions/quickWins, `brain_fixes` slugs, `committed` list. HTTP 200 + `ok:true` = pipeline healthy.

## What each run does

1. Pulls GSC last-28d queries (direct OAuth)
2. Classifies regressions (dropped >3 positions) + quick wins (pos 4–20, ≥3 impressions)
3. DataForSEO keyword gaps (cached weekly)
4. AI brain (free OpenRouter model) picks max 3 title/meta fixes on comparison pages
5. Commits to GitHub → CI auto-deploys to Cloudflare Pages
6. Writes positions to KV = tomorrow's regression baseline

## Known weak points

1. **GSC refresh token expiry** — if the Google OAuth app is in "Testing" status, token dies in ~7 days → `gsc_degraded` in log, agent runs DataForSEO-only. Fix: redo OAuth consent once. Surviving past day 10 = durable.
2. **Free OpenRouter model** (`nex-n2.5-pro:free`) — rate-limit/delisting = that day's brain step fails, logged, retried next day. Swap model in `wrangler.toml` `BRAIN_MODEL` if it becomes chronic.
3. **No alerting** — nothing pings you if it dies. check.sh weekly is the discipline.
4. **v1 scope** — title/meta only, max 3 fixes/day, never publishes new pages. By design.

## Local Mac loop — DELETED Sep 12

launchd job, Docker OpenSEO container + volume, `.seo-god/` secrets, `daily-run.sh` — all removed. Cloud worker is the only automation.
