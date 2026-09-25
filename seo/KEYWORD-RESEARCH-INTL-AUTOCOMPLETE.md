# International Keyword Research — Autocomplete Mining (Sep 25, 2026)

Source: `seo/scripts/autocomplete-mine.py` — hits `suggestqueries.google.com` (the
public endpoint behind YouTube/Google's own search-box suggestions). Free, no
API key, no ToS issue. Cross-checked against one free Ahrefs keyword-generator
pull (banded volume) for pt-BR.

Context: this extends `KEYWORD-RESEARCH-AUTOCOMPLETE.md` (EN/US, Sep 11–16) to
the non-English markets identified as candidates after shipping the pt-BR
(`/pt-br/`) site — see `SERP-HARVEST-ANALYSIS.md` for the EN competitive
formula this validates against.

## Consistent cross-market finding

In every non-English market tested, the **"generator/tool-name" phrasing has
near-zero autocomplete volume**, while **"how-to" instructional phrasing has
real, rich depth**. This is a real difference from English, where "youtube tag
generator" is itself a high-volume head term (Medium KD, >1000/mo per the
Sep 16 Ahrefs pull). Implication: non-English tool pages should lead their
title/H1 with the how-to framing the market actually searches, not a literal
translation of the English tool-name framing — the tool itself stays the same,
just the headline hook changes.

## Ranked opportunity (autocomplete depth as proxy for real demand)

| Market | Best seed | Suggestions | Verdict |
|---|---|---|---|
| 🇮🇳 Hindi/Hinglish (IN) | `youtube title kaise banaye` | **10** (incl. 1 native Devanagari variant) | Strongest signal found. Searchers type romanized Hindi ("kaise banaye"), not Devanagari — build headlines in Hinglish. |
| 🇮🇩 Indonesian (ID) | `cara membuat judul youtube` | **10** | Also very strong. `cara membuat tag otomatis youtube` ("how to make automatic tags") is literally our tool's use case. |
| 🇧🇷 Portuguese (BR) | `como colocar tags no youtube` | 5 | Real but thinner. `gerador de tags` (our shipped page's current hook) only expands to 1 suggestion — matches the Ahrefs <100/mo finding for that exact phrase. |
| 🇹🇷 Turkish (TR) | `youtube etiket nasıl eklenir` | 1 | Thin across the board. Deprioritize. |

## Raw suggestion dumps

### Portuguese (pt-BR/BR)

**"gerador de tags"** — gerador de tags para youtube *(1 suggestion — thin, confirms Ahrefs <100/mo)*

**"como colocar tags no youtube"**
- como colocar tags no youtube
- como colocar tags no youtube pelo celular
- como colocar tags no youtube studio
- como colocar tags no youtube shorts
- como colocar tags no canal do youtube

**"extrator de tags do youtube"**, **"verificador de ranking do youtube"**, **"gerador de títulos"** — no suggestions returned (too new/unestablished a phrasing in this market).

### Indonesian (id-ID/ID)

**"cara membuat tag youtube"**
- cara membuat tag youtube
- cara membuat tag youtube agar banyak viewers
- cara membuat tag youtube short
- cara membuat tag di youtube
- cara membuat tag video youtube agar banyak penonton
- cara membuat tag otomatis youtube ← direct match to our tool's value prop

**"cara membuat judul youtube"**
- cara membuat judul youtube
- cara membuat judul youtube yang menarik
- cara membuat judul youtube berbagai bahasa
- cara membuat judul di youtube
- cara membuat judul video youtube agar mudah ditemukan
- cara membuat judul video youtube
- cara membuat judul di youtube short
- cara membuat judul dan deskripsi youtube
- cara membuat foto judul di youtube
- cara membuat tanda seru merah di judul youtube

**"cara menambahkan tag youtube"** — 2 suggestions (adding tags, incl. product tags). **"pembuat tag youtube"** (literal tool-name) — no suggestions.

### Hindi/Hinglish (hi-IN/IN)

**"youtube title kaise banaye"**
- youtube title kaise banaye
- youtube pe title kaise banaye
- youtube channel title kaise banaye
- youtube me title kaise banaye
- youtube video title kaise banaye
- यूट्यूब टाइटल कैसे बनाएं (native script variant)
- youtube video me title kaise banaye
- youtube video ka title kaise banaye
- youtube channel me title kaise banaye
- youtube channel ka title kaise banaye

**"youtube tag kaise banaye"**
- youtube tag kaise banaye
- youtube tag video kaise banaye
- tag length youtube kaise banaye
- youtube par apna tag kaise banaye
- youtube channel ka tag kaise banaye

**"youtube video tag kaise dale"**
- youtube video mein tag kaise dalen
- youtube video par tag kaise dalen
- youtube video me tag kaise dalen
- youtube short video mein tag kaise dalen

### Turkish (tr/TR)

**"youtube etiket nasıl eklenir"** — youtube etiket nasıl eklenir *(1)*
**"youtube başlık nasıl yazılır"** — youtube başlık nasıl yazılır *(1)*
**"youtube etiket oluşturucu"** (tool-name) — no suggestions.

## UPDATE (same day) — real Ahrefs volume bands, manually pulled via free keyword-generator tool

Ahrefs free tier: banded volume + KD, ~6-7 queries before rate limit. Pulled for the top autocomplete winners plus a critical cross-check.

| Query | Market | Volume | KD |
|---|---|---|---|
| como colocar tags no youtube (+3 variants) | BR | all **<100/mo** | Easy |
| cara membuat judul youtube (+2 variants) | ID | all **<100/mo** | Easy |
| youtube title kaise banaye | IN (Hindi) | **<100/mo** | N/A |
| **youtube tag generator** (English) | **IN (India)** | **>10,000/mo** | Hard |
| youtube tag generator (English) | ID | >100/mo | Medium |
| youtube tag generator (English) | US | >1,000/mo | Hard |

**This overturns the autocomplete-only read.** The native-language "how-to" long-tail phrasings that looked promising by suggestion-count all turned out to be genuinely low absolute volume (<100/mo) once checked against real numbers — autocomplete breadth is not the same as search volume; a phrase can have many completions while each one is rarely searched.

**The actual finding that matters: India searches this category in English, at 10x US volume, same competition level (Hard) as the US.** This is not a translation opportunity — it requires zero new content, since the English tool pages are already live. It's an indexing/technical-targeting question: is India-based search traffic actually reaching and ranking our existing English pages.

## Recommendation (revised)

1. **Priority 1 — verify/strengthen India targeting for the existing English pages**, not a new language build. Check Search Console for India-specific impressions/position on `/tools/youtube-tag-generator` et al.; confirm nothing blocks Indian traffic (no geo-restriction, CDN issue, etc.); consider whether `hreflang="en-IN"` or an India-specific signal is worth adding. Zero new content required — highest ROI-to-effort finding of this research pass.
2. **Do not build new Hindi-language content on this evidence** — the Hinglish/Devanagari long-tail phrasings tested are real but low-volume (<100/mo each), same story as Portuguese and Indonesian.
3. **pt-BR retitle recommendation is downgraded too** — "como colocar tags" is <100/mo, same as "gerador de tags". No clear win from retitling; the already-shipped pt-BR pages are fine as-is until better keyword evidence appears.
4. Indonesian and further language builds: no longer recommended on current evidence — every native-language long-tail phrase checked across 3 markets came back <100/mo. The one real signal in this entire pass is the India-English volume gap.
