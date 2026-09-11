# SEO + AEO + GEO Playbook: The Complete Research to 10k–20k Clicks

*Research date: Sep 11, 2026. Sources: Princeton GEO study (KDD 2024), Ahrefs, Seer Interactive, Search Engine Land, Pew Research, BrightEdge, Authoritas, 2026 practitioner case studies, r/DigitalMarketing & r/aeo threads.*

---

## 1. The reality first (why "just do SEO" fails now)

- AI Overviews cut **CTR of the #1 organic result by 58%** (Ahrefs, Dec 2025 — was -34.5% in April 2025; impact is accelerating)
- Pew Research: users click **only 8% of the time** when an AI answer is present (vs 15% without)
- Informational queries ("what is X", "how to X") lost **55–61% of CTR**. These are dead for traffic.
- **BUT**: brands cited *inside* AI answers get **+35% organic CTR** (Seer Interactive) and +91% paid CTR
- **BUT**: only ~4% of transactional/ecommerce searches trigger AI Overviews at all
- Featured snippets still exist on 12–15% of queries with **~42.9% CTR**

**Translation**: clicks didn't disappear — they *moved*. They moved to (a) bottom-funnel queries, (b) citations inside AI answers, (c) Reddit, (d) tools/comparisons AI can't replace.

## 2. The three layers (one system, not three jobs)

| Layer | Goal | Unit of optimization |
|---|---|---|
| **SEO** | Rank top 10 (the entry ticket — 76% of AI citations come from pages already in top 10) | The page |
| **AEO** | Win featured snippets (still ~43% CTR) + direct answers | The answer block (40–60 words) |
| **GEO** | Get quoted *inside* ChatGPT/Perplexity/AI Overview answers | The sentence |

The work overlaps ~80%. Do it once, win everywhere.

Key counterintuitive finding: **~80% of pages cited by ChatGPT/Claude/Perplexity do NOT rank in Google's top 10** for the same query. Search Console is NOT a proxy for AI visibility. Treat them as related but separate channels.

## 3. The click math (how 10k–20k actually happens)

From the 512-page programmatic SEO case study (real 18-month data, B2B SaaS):

- **One page-1 ranking = 30–80 clicks/month**
- **70+ page-1 rankings = 2,000–5,000 clicks/month** (the inflection point)
- Timeline: 240 clicks/mo → 1,140 (mo 3) → 3,420 (mo 6) → 6,890 (mo 9) → **11,840 (mo 18)**
- Top 10% of pages capture **42% of all clicks**. Next 20% capture 31%. Bottom 30% capture 5%.

So 10k–20k clicks = **~100–150 page-1 rankings** reached through compounding: ~100–200 pages of long-tail content, published 25–30/week, with quarterly refresh sprints on the bottom 20%.

**Timeline expectations**: compounding starts month 6, steepens month 9. Most programs get killed at month 4–5, right before the slope changes. First 6 months = foundation (240 → 1,140 clicks is normal).

**Other real case studies:**
- Gluten-free supplement brand: 3,000+ programmatic pages in 60 days → 45K+ monthly clicks, 24.8K keywords, $0 ad spend
- SaaS supply chain company: +398% traffic (1,920 → 9,571 users/mo) from just ~100 pages over 18 months
- Educational site: 200 → 50,214 monthly visits in 8.5 months via 5,000+ automated pages
- Preply: ~500K → ~4M monthly visits over 3 years (3 content engines: blog + forum UGC + programmatic commercial pages + digital PR)

## 4. What content gets clicks in 2026 (priority order)

1. **Comparison + bottom-funnel pages** — "X vs Y", "best X for Y", "X alternatives", "X pricing". Only 4% trigger AI Overviews; convert at 6–8% vs 2% for generic pages. Listicle/comparison formats = **25.37% of ALL AI citations**. Most categories have these queries with almost zero competition.
2. **Tools, calculators, databases, interactive stuff** — AI cannot replace a working tool. People must click.
3. **Programmatic long-tail pages** — `[query] + [modifier]` templates from real data. Rules: **3+ unique data points per page minimum** (pages with 1–2 struggle to index), hub + spoke internal linking, 25–30 pages/week max (bulk publishing 100+ tanks indexing).
4. **Original data / research** — pages with original statistics get **+156% AI Overview citations** (Authoritas 2026). Your own data is the #1 thing that makes AI cite YOU instead of the ten pages restating consensus.
5. **Reddit presence** — Perplexity cites Reddit in **38% of queries**, AI Overviews surface it in ~25% of informational queries, ChatGPT search references it more than any other social platform.

**Avoid**: informational "what is X" content as your traffic strategy. It's the exact query type AI eats.

**Programmatic template patterns that work:**
- `[service] in [location]`
- `[product] for [use case]`
- `[software category] for [industry]`
- `[competitor] alternative`
- `[Tool A] vs [Tool B]` (require both tools ≥200 monthly searches or skip)
- glossary terms (index reliably, decay slowly — best starting template)

## 5. The on-page GEO/AEO stack (evidence-backed lifts)

| Tactic | Measured lift |
|---|---|
| Expert quotations (named humans) | **+41%** AI visibility |
| Statistics (specific, sourced numbers) | **+33%** |
| Citing your sources inline | **+28%** |
| Stats + citations combined | **~+61%** |
| Structured FAQ (real Q&A + FAQPage schema) | **+44%** AIO citation rate |
| Author/Organization schema | **3×** citation likelihood |
| Content refreshed within 30 days | **3.2×** citation lift |
| Tables vs paragraphs for comparisons | **81% vs 23%** extraction rate |
| Multi-modal content (text+images+video+schema) | strongest AIO inclusion (r=0.92) |
| Keyword stuffing | **−8%** (actively harmful) |
| Bullet lists vs prose (Claude) | **+30%** |

### The core writing rule

**Question-shaped H2/H3 heading → 40–60 word self-contained direct answer → then expand.**

- The answer must survive being lifted out of context: no pronouns ("it"/"they"), one complete claim per sentence (10–20 words)
- Concrete numbers over adjectives: "$3.99/month for unlimited generations" is citable; "affordable" is not
- First 200 words of every page must stand alone as the answer — no throat-clearing, no "in this article we will explore"
- 72.4% of ChatGPT-cited pages had exactly this structure (Search Engine Land)
- 44.2% of LLM citations come from the first 30% of text on a page
- Define key terms in plain language in the first 100 words — the definition you write is the definition the engine quotes

### Engine specifics

- **ChatGPT** runs on **Bing's index** → set up Bing Webmaster Tools + IndexNow (30 min, most competitors haven't). Favors consensus sources: Wikipedia ~7.8% of citations, Reddit ~12%. Pages with FCP <0.4s average 6.7 citations vs 2.1 for slow pages.
- **Perplexity** rewards freshness hardest — retrieves real-time over 200B URL index, cites 8–12 sources per answer, can cite a page published today, tomorrow. Demotes stale content aggressively.
- **Google AI Overviews** lean on existing organic rank (54% of citations from top 20 organic) — but 48% of cited URLs are outside top 100. Trigger on ~13% of US desktop searches, mostly informational.
- **Claude** loves bullet lists, clear definitions, technical docs, PDFs. Weights evidence quality heavily.
- **Gemini** pulls from Google ecosystem: Knowledge Graph, Google Business Profile, YouTube.
- Query fan-out: one buyer question becomes 3–5 internal sub-searches. Your page must win individual sub-queries, not the whole prompt.
- Retrieval works on **chunks of a few hundred words** — each section is a separate retrieval surface. Every genuinely distinct sub-question answered = another citation opportunity.

## 6. Technical checklist

1. **Crawler access** (#1 silent killer — verify BOTH layers):
   - robots.txt allows: `OAI-SearchBot`, `ChatGPT-User`, `PerplexityBot`, `Claude-SearchBot`, `Googlebot`, `Bingbot`
   - Cloudflare edge: Security → "Block AI bots" toggle (deprecating 2026-09-15) AND Overview → "Manage your robots.txt" card (injects Disallow into served file)
   - Verify: `curl -s https://SITE/robots.txt | grep -c "Cloudflare Managed"` → 0, and `curl -sI https://SITE/ -A "GPTBot/1.0" | head -1` → 200
   - Re-check after every CDN/deploy change
2. **Schema stack** (JSON-LD in head, priority order): Organization (with `sameAs` → socials, Crunchbase, store listings) → FAQPage → Article (dateModified) → HowTo → SoftwareApplication (name, operatingSystem "Chrome", installUrl to store) → BreadcrumbList
3. **Entity consistency** — identical one-liner description on site, LinkedIn, Crunchbase, GitHub, Chrome Web Store, review sites. Contradictory descriptions = low-confidence entity = AI hedges away from you.
4. **llms.txt** — cheap insurance, NOT a strategy (Google officially ignores it; OpenAI/Microsoft crawlers do read it; only ~10% of domains have one)
5. **Site speed** — FCP <0.4s (see ChatGPT citation stat above)
6. **Server-rendered FAQ** — visible in HTML, not JS-only (collapsed-by-CSS fine, client-only not)
7. **Freshness signals** — visible "Last updated" date + dateModified in schema; quarterly refresh sweep on top 20 commercial pages
8. **Cannibalization check** — thin pages answering the same question compete with each other for the same retrieval slot

## 7. The off-page moat (mentions beat backlinks ~3:1 for AI visibility)

- **Reddit play**:
  - 30 days of genuine answers first (no links, no brand mentions) — build 500+ karma before any self-posts
  - Aged accounts matter: mods check age + karma; 7-year-old account with 50K karma carries citation weight
  - "Comparison comment" format that gets cited: *"I've used A, B, C. A is best for X because [specific reason]. B breaks when [condition]."*
  - Lead with the answer, specific numbers, acknowledge caveats ("works for teams under 50; above that you need X")
  - Second-hand traffic method: find threads already ranking on Google for target queries, add detailed experience-based comments (the thread has Google's attention, your comment gets indexed with it)
  - Add a TL;DR summary at top of threads — +30% extraction rate
  - Never paste raw AI output — mods run AI detection, threads with LLM cadence get downvoted/reported
  - Reddit-referred users convert better: one B2B SaaS saw 18% trial→paid vs 11% for generic organic
- **Review platforms**: brands on G2/Capterra/Trustpilot are **~3× more likely to be cited**
- Third-party publishers earn **6.5× more AI citations** than your own domain (Axis Intelligence 2026) — pitch guest posts, get into "best X" roundups, YouTube (transcripts are training data), niche newsletters, podcast transcripts
- In one logged sample of 23 Perplexity citations: 14 were vendors' own domains, 7 listicles, 1 Reddit, 0 G2/Capterra/Wikipedia — mixed evidence; earn mentions broadly but your own well-structured pages DO get cited
- Wikipedia/Wikidata when notable enough

## 8. Featured snippets (still alive, concentrated)

- Snippets trigger on 12–15% of desktop queries, ~42.9% average CTR, mostly long-tail
- 99.58% come from pages already in top 10 — but only 30.9% from #1, so positions 2–10 can leapfrog with cleaner formatting
- Format rules: question as H2 → 54–58 word direct paragraph below; lists of 5–8 items starting with action verbs; tables for comparisons (81% extraction)
- Snippets and AI Overviews rarely coexist (7.42% overlap) — Google makes a binary choice: one clear answer → snippet; needs multi-source synthesis → AIO
- Snippets that fully resolve the query cost you the click; lists/processes/partial tables intrigue and pay
- Snippets can seed AI Overviews via fan-out queries

## 9. CTR optimization (GSC method)

- Pull top 50 pages by impressions → flag every page with CTR <3% → check Queries tab for intent mismatch → rewrite titles
- Question-based titles: **+14% CTR**; titles 15–40 chars: +8.6%
- "Power words" like "ultimate"/"best": **−14% CTR** (signal fatigue)
- Front-load primary keyword in first 40 pixels, as part of a natural noun phrase; mechanical stuffing reads as spam
- Title formula: primary keyword + specific value proposition + optional subtle CTA (commercial only)
- Measure titles in **pixels** (≤580 title, ≤920 description), not characters
- Google rewrites meta descriptions **62–71%** of the time — write intent-matched copy so rewrites pull good source material
- Adding year/freshness signal "(2026 Data)" lifts CTR when competitors show older dates
- Segment CTR by query type: branded queries lost least to AIO (-8–13%), informational worst (-55–61%), commercial middle (-36–44%)
- Positions 6–10 earn 1–4% CTR regardless of title quality — fix rankings before optimizing snippets

## 10. Measurement (no Search Console for AI exists)

- Fixed set of **30–50 buyer questions** (write as full sentences with constraints: team size, budget, stack — mine sales calls, support tickets, "what should I use for" subreddit threads)
- Run weekly across ChatGPT/Perplexity/AI Overviews/Gemini. Track:
  - **Mention rate** — % of answers naming you (headline number)
  - **Cited-when-present rate** — of AIO appearances, how often you're the source
  - **Share of voice** vs competitors
  - Which URLs get cited (always shorter and more surprising than you expect — 58 of 96 cited pages in one audit weren't in Google top 100)
  - Grounded vs ungrounded flag (ungrounded = model memory, not citation — mixing wrecks your numbers)
  - AI answers are non-deterministic (same query → different results ~99% of time) — use rolling windows, never single checks
- AI referral traffic: classify server-side, GA4 misses most of it
- Grep access logs for AI bot UAs hitting llms.txt
- Watch branded search volume — it rises BEFORE AI referral traffic when LLMs start recognizing your entity
- Manual tracking = 30 min/month, gets 80% of the insight. Tools when it matters: OtterlyAI (~$29/mo), Profound (enterprise)

## 11. Anti-patterns

- Wall of fluff before the answer (300-word warm-up = nothing extracted)
- Pronoun-heavy prose (dies out of context)
- Schema as the whole strategy ("wrapper ≠ work")
- Blocked crawler discovered months later (check after every CDN/deploy change)
- Chasing every citation flicker (rotation is normal; act on durable drops)
- Treating "AI search" as one channel (Perplexity grounds everything; ChatGPT decides per query; AIO carries SEO over)
- Optimizing only for the engine that's easiest to measure (Perplexity = smallest by usage)
- Publishing volume as strategy: 20 thin pages answering one question badly lose to one page answering 20 questions well
- 20 thin pages also compete with each other for the same retrieval slot

## 12. 90-day execution plan

**Days 1–30 (Foundation)**
- Crawler audit (robots.txt + Cloudflare edge, both layers)
- Schema deployment on top 20 pages (Organization, FAQPage, Article, SoftwareApplication)
- Bing Webmaster Tools + IndexNow setup
- Rewrite top 10 commercial pages: answer capsules, FAQ sections matching real query patterns
- Launch first comparison pages (vs / alternatives / best-for)
- Start Reddit karma building (30 days of pure value, no links)

**Days 31–60 (Content engine)**
- Programmatic template #1 (comparisons or glossary), 25–30 pages/week
- Publish first original-data piece from product data
- First Reddit reference thread (400–1,000 words, zero links)
- Entity cleanup pass (LinkedIn, Crunchbase, GitHub, store listing — same one-liner everywhere)

**Days 61–90 (Optimize + measure)**
- Second template family
- GSC CTR sweep (high impressions + <3% CTR → title rewrites)
- Weekly citation tracking live (30–50 question matrix)
- Audit bottom 20% of published pages: refresh / merge / noindex

**Speed expectations**: Perplexity citations within days/weeks; ChatGPT live search similar; AI Overviews 2–8 weeks; ChatGPT training-data answers lag months–a year. Traffic inflection at month 6–9.

## 13. Applied to vidrank.tech

Highest-leverage moves:
1. **Comparison pages**: `[tool] vs vidrank`, `vidrank alternatives`, `best YouTube ranking tools for [use case]` — bottom-funnel, low competition, 6–8% conversion, minimal AIO presence
2. **Original data study** from vidrank's own ranking data: "we analyzed N videos' ranking factors" — the +156% AIO citation play; becomes the asset other pages cite
3. **Reddit threads** in r/youtubers / r/NewTubers / r/PartneredYoutube with real numbers from the data study (comparison comment format)
4. **Schema + capsule work** already scoped in the aeo-geo-optimization skill (SoftwareApplication schema with Chrome store installUrl, FAQPage, llms.txt, Cloudflare bot audit — previously found the edge blocker killing GPTBot)
5. **Glossary/programmatic template** for YouTube SEO terms — safest indexing, slow decay
6. **Chrome extension pages in roundup posts** — third-party "best Chrome extensions for YouTubers" placements earn 6.5× more citations than owned pages

---

## Source index

- Princeton GEO paper (Aggarwal et al., KDD 2024) — the only controlled study; 10k queries, 9 tactics
- Ahrefs Dec 2025 study (300k keywords) — AIO CTR impact
- Seer Interactive — cited-brand CTR lift
- Pew Research Center — user click behavior with AI answers
- BrightEdge 2026 — FAQ schema +44%, author schema 3×
- Authoritas 2026 — original statistics +156% AIO citations
- Search Engine Land — 72.4% ChatGPT-cited pages structure; AIO vs snippets comparison
- theStacc 512-page pSEO case study (2026) — click math, timeline, cohort data
- Kick Ads, Cuescout, aidev.com, aicitationmonitor.com, Soku — 2026 GEO playbooks
- growreddit.com, thestacc.com Reddit guides + r/DigitalMarketing, r/aeo threads — practitioner reality checks
- Knownful, SERPs.io, Sabian Zhupa — featured snippet state in AIO era
- quickseo.ai, astroseoblog.com — GSC CTR method, title tag data
