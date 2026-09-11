import type { APIRoute } from "astro";

export const prerender = false;

function extractVideoId(input: string): string | null {
  const trimmed = input.trim();
  if (/^[\w-]{11}$/.test(trimmed)) return trimmed;
  const m = trimmed.match(/(?:v=|\/shorts\/|youtu\.be\/|\/embed\/|\/live\/)([\w-]{11})/);
  return m ? m[1] : null;
}

function parseTags(html: string): { tags: string[]; title: string | null } {
  const titleMatch = html.match(/<title>([^<]*)<\/title>/);
  const title = titleMatch ? titleMatch[1].replace(/ - YouTube$/, "").trim() : null;
  const kw = html.match(/<meta\s+name="keywords"\s+content="([^"]*)"/i)
    || html.match(/<meta\s+content="([^"]*)"\s+name="keywords"/i);
  if (!kw) return { tags: [], title };
  const tags = kw[1]
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean)
    .filter((t, i, a) => a.indexOf(t) === i);
  return { tags, title };
}

export const GET: APIRoute = async ({ url }) => {
  const videoId = extractVideoId(url.searchParams.get("url") || "");
  if (!videoId) {
    return new Response(JSON.stringify({ error: "Paste a valid YouTube video URL or 11-character video ID." }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const target = `https://www.youtube.com/watch?v=${videoId}&hl=en`;
  try {
    const res = await fetch(target, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        Cookie: "CONSENT=YES+cb; SOCS=CAI",
      },
    });
    if (!res.ok) throw new Error(`YouTube returned ${res.status}`);
    const { tags, title } = parseTags(await res.text());
    return new Response(JSON.stringify({ videoId, title, tags }), {
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: "Could not fetch that video. It may be unavailable — try another URL." }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }
};
