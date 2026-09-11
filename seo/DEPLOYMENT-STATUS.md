# SEO-GOD Deployment — vidrank.tech (Deployed Sep 11, 2026)

## What is running

| Component | Detail |
|---|---|
| OpenSEO container | `ghcr.io/every-app/open-seo:latest` v0.1.7, `127.0.0.1:3001`, `local_noauth` (loopback only, never expose), data volume `openseo-data` |
| Registered project | `vidrank.tech` — id `6a31ad86-e10c-45e0-8c06-737c9a23692b`, market US/en |
| State file | `landing-page/seo-god.json` (committed; no secrets in it) |
| Daily schedule | launchd `com.seo-god.daily`, **09:00 local**, runner copied to `landing-page/scripts/daily-run.sh`, plist at `~/Library/LaunchAgents/com.seo-god.daily.plist` |
| Daily loop order | inputs → may-we-edit → regressions → quick wins (pos 4–15) → max 1 new page → dated readout |
| Safety | never commits/pushes; edits wait in working tree; 48h missed-run warning; free path = zero paid keys |
| Build gate | `Bash(npm run build:*)` allowed in `~/.claude/settings.json` (user scope — required for unattended builds) |

## Daily operations

- Readout of each run: `landing-page/dist/seo/readouts/<date>.md` (dist is gitignored — local artifacts)
- Run marker / logs: `landing-page/.seo-god/` (gitignored)
- Manual run anytime: `cd landing-page && bash scripts/daily-run.sh --skill-dir ~/.claude/skills/seo-god`
- Dry run: `SEO_GOD_DRY_RUN=1 bash scripts/daily-run.sh --skill-dir ~/.claude/skills/seo-god`
- Stop/start container: `cd landing-page && docker compose -p seo-god -f .seo-god/docker-compose.yml down|up -d`
- Uninstall schedule: `launchctl bootout gui/501/com.seo-god.daily && rm ~/Library/LaunchAgents/com.seo-god.daily.plist`
- If Mac asleep at 09:00: launchd coalesces into one run on wake. Skip days = skipped.

## API cost answer (verified Sep 11, 2026)

**The automation runs 100% free.** Free plane: OpenSEO crawler (local), GSC (first-party), Google autocomplete mining, IndexNow, locked-prompt search checks.

| Paid API | Price | When to add |
|---|---|---|
| DataForSEO | $1 free signup credit; **$50 min deposit** for live; $0.0006/SERP, keyword data $0.06/1K keywords; seo-god caps at **$0.50/day** (`SEO_GOD_D4S_BUDGET_USD`) | When you want real volumes/KD/backlinks |
| SerpApi | 250 free searches/mo | Alternative probe source |
| LLM keys | pay per call, per-run capped | Direct AI-answer probing (free path = search-results proxy only) |

## Remaining to unlock the full loop

1. **Connect GSC**: open `http://127.0.0.1:3001`, project vidrank.tech → connect Search Console (one Google auth click in your browser). Then run `/seo-god measure` → snapshot #1.
2. `/seo-god audit` — first full crawl + impact-triaged fixes in `landing-page/`.
3. `/seo-god ai_visibility` — locks the 10 niche prompts.
4. From snapshot #1: the 09:00 loop computes regressions/quick-wins/gaps on real data.
5. Optional power-ups: DataForSEO key (budget-capped), Telegram digest.
