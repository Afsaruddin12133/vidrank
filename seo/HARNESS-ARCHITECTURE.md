# How Agentic SEO Harnesses Work — and How Ours Is Built

*Research: Sep 11, 2026. Sources: seo-god internals (local), buttonblock.com architecture guide, slashdev.io, seobot.dk, searchatlas.com, Talko90/seo-agentic-system (8-agent pattern).*

---

## 1. The anatomy of a harness (5 components — every source agrees)

| Component | What it is | What WE have |
|---|---|---|
| **Tools** | MCP/API connections the agent may call | ✅ OpenSEO MCP (46 tools: audit, GSC, keywords, rank tracking, AI visibility) |
| **Memory** | State that survives runs | ✅ `seo-god.json` (phase state), `dist/seo/snapshots/` (daily GSC snapshots), readouts |
| **Instructions** | Goal + constraints + fixed operating order | ✅ seo-god phase files: "regressions → quick wins → max 1 new page → readout" |
| **Knowledge** | Live data inputs | ✅ GSC (first-party), DataForSEO (volumes/KD), local crawler, autocomplete |
| **Feedback loop** | Verify whether changes worked | ✅ GSC +14/+30 day deltas vs snapshot diffs; rank tracker |

The agent loop: **Goal → Plan → Tool call → Observe → Re-evaluate → Output.** A script runs a fixed sequence; an agent adapts based on what it observes.

## 2. The reliability ladder (Button Block — the key insight)

Four layers, reliability falls off a cliff as you climb:

1. One-off prompts — fine
2. **Reusable skill specs** (instruction file + tool whitelist + output template) — most value lives here
3. **Multi-step workflows** (skills chained with branching) — where our daily loop sits
4. Fully autonomous agents — where marketing lives; ship last

**Implication for vidrank:** our loop is layer 3 with a human approval gate — exactly where the sources say to be. Don't chase "fully hands-off"; chase "hands-off between reviews."

## 3. The 8 rules that make a harness survive production

1. **Build the reviewer first.** A findings-reviewer (checks every issue against quality criteria before it ships) is the most-rewritten file in every production harness. Without it you can't measure quality at all.
2. **Strict output templates, not better prompts.** "If your agent output looks different every run, you need a template file." Locked field names + schema check before downstream consumption.
3. **Anti-hallucination: every number carries `data_source` + `fetched_at`.** Confidence scores per source: GSC 0.90, DataForSEO 0.95, web search 0.60. No data → say "not measured", never estimate. (seo-god's honesty model matches exactly.)
4. **Proposal buffers.** Multiple agents never write the master database directly — they write proposals; ONE orchestrator merges, resolves conflicts, and applies the priority formula `(Value × Urgency × Confidence) / Effort`.
5. **Build gate = truth.** An issue is fixed only when the build/typecheck exits 0. Never commit; changes wait in the working tree for human review.
6. **Fixed priority order.** Regressions first (a quick win is worthless on a site that broke), then striking-distance (pos 4–15), then max ONE new page per run — bulk publishing is what search engines are built to catch.
7. **Tool whitelist per skill.** Agents given unrestricted access invent integrations. Lock the toolbox (seo-god grants exactly: curl + read-only git).
8. **Shared gotchas file.** Lessons must transfer between runs/agents — e.g., ours: "Cloudflare email-obfuscation rewrites footer mailto: links into /cdn-cgi/l/email-protection which 404s for crawlers = 16 false-positive 'broken link' audit findings."

## 4. Known failure modes + the fix

| Failure mode | Fix |
|---|---|
| Output drift on similar inputs | Output template + schema check |
| Confident hallucinations ("missing H1" that exists) | Reviewer verifies every claim against pulled data |
| Infinite tool loops | `max_iterations` (seo-god: `--max-turns 80`) |
| Rate limits (429 storms) | Backoff + jitter; cache with 24h TTL |
| Math in prompts (agents can't calculate) | Raw data → tool function → return result |
| Knowledge doesn't transfer between agents | Shared references/gotchas directory |

## 5. Measurement: how you know the harness works

- **LLM-as-judge**: a second model grades outputs on a rubric (accuracy / relevance / safety / brief compliance). Target 75–90% agreement with human labels.
- **A/B split**: 50 low-performing pages → 25 get agent-suggested titles, 25 keep old → measure CTR delta in GSC after 14 days. This is the only honest proof.
- **Deltas, not dashboards**: tag every shipped change with date+URL, pull +14/+30 day outcomes.
- **ROI instrumentation**: time saved, pages shipped, positions improved, traffic gained per agent action.

## 6. Where OUR harness stands vs this blueprint

**Already built (deployed Sep 11):**
- ✅ Orchestrator + phase files (seo-god) with fixed order + honesty rules
- ✅ Tool registry locked to whitelist (curl + read-only git) + `--max-turns 80`
- ✅ Build gate (`npm run build` permitted at user scope)
- ✅ launchd daily 09:00 + 48h missed-run self-check
- ✅ Never-commit + human review of working tree
- ✅ GSC + DataForSEO + AI visibility data plane, all free/cheap

**Build next (in order of ROI):**
1. **Gotchas file** (`.seo-god/gotchas.md`): start with the Cloudflare email-protection false positive + "www vs apex canonical" — 1 hour, prevents repeat false findings
2. **Readout template** with locked fields (date, regressions[], quick_wins[], new_page, deltas, data_sources) — 1 hour
3. **Reviewer pass**: before shipping any fix, re-verify against the raw audit/GSC row — half day
4. **Change ledger** with +14/+30 outcome tracking per change (currently manual: readouts + GSC diffs) — 1 day
5. **Programmatic tag-page engine** with quality gate: template + 3 unique data points minimum + reviewer pass — the volume wave (25–30/week) AFTER the per-page gates exist
6. **Priority formula** in the daily loop: `(Value × Urgency × Confidence) / Effort` for the action queue — 2 hours

## 7. What NOT to build

- Multi-agent crews (8 specialized agents) — overkill for a 17-page site; one orchestrator + phase files wins until the site is 100+ pages
- Vector DB memory — overkill; JSON snapshots + git history are the memory at this scale
- Full autonomy (layer 4) — every source says keep the human approval gate; the agent proposes, you approve
- n8n/Zapier pipelines — the sources document these breaking on GSC exports and cost blowups; the agent IS the orchestrator
