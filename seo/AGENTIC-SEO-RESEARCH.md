# Agentic SEO: Research + Free Setup for vidrank.tech

*Research date: Sep 11, 2026. Sources: Ahrefs blog (May 2026), Aristral (May 2026), thestacc (Jul 2026), RankHive (May 2026), Fountain City production guide (Apr 2026), gomega.ai, GitHub repos: AKCodez/seo-god, every-app/open-seo (OpenSEO, 15.8k★), theshajha/OpenSEO.*

---

## 1. What agentic SEO is

**Agentic SEO = AI agents that plan, execute, and iterate SEO work on their own schedule, under goal-level instructions ("keep this site ranking") instead of per-task prompts ("write me a title").**

The agent loop (all serious implementations converge on this):

1. **Observe** — pull GSC data, crawl the site, watch rankings/competitors
2. **Decide** — score findings by impact × effort, pick the next 5 things (never 200)
3. **Draft** — produce the concrete artifact: rewritten title, content diff, internal links, new page
4. **Act/Coordinate** — ship behind a build gate or queue for human approval
5. **Verify** — measure +14/+30 day deltas, feed back into the loop

Key distinction (Aristral's test): a *tool* answers one prompt. An *agent* has durable state (remembers what it tried), a tool registry (picks APIs dynamically), retry-and-branch failure recovery, and human-in-the-loop gates. If it errors out and restarts, it's a script with an LLM in one slot.

Second meaning (thestacc): optimizing content so AI agents (ChatGPT/Perplexity/AIO) that search on behalf of users can find and cite it — i.e., GEO. The two meanings converge: agentic systems are what run GEO at measurable cadence.

## 2. How "daily without human touch" actually works

The production pattern (seo-god + Fountain City + RankHive all match):

- **Scheduled loop**: cron/launchd/Task Scheduler runs the agent daily (e.g., 05:00) with a fixed order: **inputs → regressions first → quick wins (positions 4–15) → at most one new page → dated readout**. Regressions outrank new content; a quick win is worthless on a site that broke yesterday.
- **Completion-triggered, not cron-chained**: finishing one stage triggers the next (Fountain City moved off fixed crons — 10 AM briefs shouldn't wait for 2 PM writing crons).
- **Human in the approval seat, not the prompt seat**: agent queues drafts + evidence; human approves/edits/denies in ~10 min/day. RankHive's real numbers: 8–15 proposals/week, 60–70% approved, ~71 shipped changes in month one, ~3 hours total human time vs ~24 hours manual.
- **Unattended runs degrade, never guess**: if a data source is unreachable, the run does what available data supports and names what was missing.
- **Never auto-commit to prod**: changes wait in the working tree + dated readout; rollback links everywhere.

Realistic weekly cadence for a small site: Monday GSC pull → striking-distance fixes (pos 4–15 = biggest lever) → title/meta/internal-link drafts → Tuesday 10-min human review → ship → Friday alt-text/batch passes.

## 3. OpenSEO — what it actually is

**OpenSEO (openseo.so / github.com/every-app/open-seo, MIT, ~15.8k★)** = open-source Semrush/Ahrefs alternative:

- **Features**: keyword research (volume/KD/intent + live SERPs), domain overview, backlinks, rank tracking, site audit crawler, AI visibility + prompt explorer
- **Data**: powered by DataForSEO (bring-your-own API key, pay-per-query ~$0.02–0.10/keyword, ~$5–20/mo solo) — the site audit/crawl part is **free** (local Docker container)
- **MCP server**: connects Claude Code/Cursor/Codex agents to keyword research, SERPs, backlinks, GSC (read-only, no Google Cloud setup needed, no credits for GSC tools)
- **Self-host**: Docker (local) or Cloudflare Workers (free tier)
- Ships with agent "Skills" for common SEO workflows

(Not to be confused with theshajha/OpenSEO, a 56★ WIP API suite — less mature.)

## 4. The free path — how to do this with zero paid APIs

**The stack that answers "free, daily, no human touch": seo-god (AKCodez/seo-god, MIT, 88★)** — a Claude Code skill built exactly for this:

```bash
git clone https://github.com/AKCodez/seo-god ~/.claude/skills/seo-god
# open Claude Code in the site's repo, then:
/seo-god
```

Five phases: setup (boots OpenSEO in Docker locally) → audit (crawl + impact-triaged fixes in your repo, gated by your build) → measure (GSC snapshots + day-over-day diff) → ai_visibility (10 locked prompts, tracks your domain's presence in search results) → schedule (installs the daily OS job). The `act` phase is the daily loop: fix regressions → improve 2–3 near-ranking pages → max one new page if data demands → dated readout.

**Free data plane (no paid keys, no scraping Google):**
| Source | Cost | Gives |
|---|---|---|
| OpenSEO local crawler (Docker) | free | technical audit, titles/metas/links/thin content |
| Google Search Console | free | clicks, impressions, positions, queries (first-party truth) |
| Locked-prompt search check | free | AI/search visibility proxy |
| Google autocomplete (suggestqueries) | free | keyword mining (what we used today) |
| Bing Webmaster Tools + IndexNow | free | second engine + instant indexing |
| vidrank's own tag data | free | unique data content (the +156% citation play) |

**What free does NOT give** (seo-god's honesty model — reported as "not measured", never zero-filled): rank positions across engines, search volume, KD, backlinks. Those need the DataForSEO power-up (~$0.50/run capped) or live without.

**Honest limits of full autonomy** (from all sources): agents still hallucinate like their underlying model; big crawls break them; long hands-off workflows break more than short ones; voice drift hits ~1 in 5 AI drafts even with review infrastructure. The winning pattern is 30-min human review per week, not zero human. And "AI visibility" on the free path = search-results presence proxy, NOT proof of citation.

## 5. Recommended setup for vidrank.tech

1. **Install seo-god** (`git clone` above) → run setup + audit + measure this week → schedule the daily loop at 05:00. Cost: $0.
2. **vidrank-specific daily loop** (what `act` should do here):
   - GSC diff → fix regressions on the 13 live pages
   - Quick wins: "ranked tags" cluster pages sitting at pos 41 → title/meta rewrites
   - New page: programmatic tag pages, max 1/day (data-gated)
   - IndexNow ping every shipped change (already wired in deploy script)
3. **Weekly 30-min review**: approve queued changes, read the dated readouts.
4. **Optional $0.50/day power-up later**: DataForSEO key for real volume/KD once organic clicks justify it.
5. Consider OpenSEO's hosted MCP later for backlink context; the local crawler covers audits free.
