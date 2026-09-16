import type { APIRoute } from "astro";
import { getAllPosts } from "../lib/blog";

const SITE = "https://vidrank.tech";

export const GET: APIRoute = async ({ locals }) => {
  const env = (locals as any)?.runtime?.env;
  const posts = await getAllPosts(env);

  const urls = [
    {
      loc: `${SITE}/`,
      lastmod: new Date().toISOString().slice(0, 10),
      changefreq: "weekly",
      priority: "1.0",
    },
    {
      loc: `${SITE}/blog`,
      changefreq: "weekly",
      priority: "0.8",
    },
    {
      loc: `${SITE}/privacy`,
      changefreq: "yearly",
      priority: "0.3",
    },
    {
      loc: `${SITE}/tools/youtube-tag-extractor`,
      changefreq: "monthly",
      priority: "0.9",
    },
    {
      loc: `${SITE}/tools/youtube-rank-checker`,
      changefreq: "monthly",
      priority: "0.9",
    },
    {
      loc: `${SITE}/tools/youtube-tag-generator`,
      changefreq: "monthly",
      priority: "0.9",
    },
    ...posts.map((post) => ({
      loc: `${SITE}/blog/${post.slug}`,
      lastmod: post.updated_at ? new Date(post.updated_at).toISOString().slice(0, 10) : undefined,
      priority: "0.7",
    })),
  ];

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls
  .map(
    (u) => `  <url>
    <loc>${u.loc}</loc>${u.lastmod ? `\n    <lastmod>${u.lastmod}</lastmod>` : ""}${u.changefreq ? `\n    <changefreq>${u.changefreq}</changefreq>` : ""}\n    <priority>${u.priority}</priority>
  </url>`
  )
  .join("\n")}
</urlset>`;

  return new Response(xml, {
    headers: { "Content-Type": "application/xml; charset=utf-8" },
  });
};
