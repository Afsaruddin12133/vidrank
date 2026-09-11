import seedPosts from "../data/posts.json";
import comparisonPosts from "../data/comparison-posts.json";
import type { BlogPost, CreateBlogPostInput } from "./types";

/**
 * In-memory / seed fallback blog store.
 * Supports Cloudflare D1 runtime bindings when deployed on Cloudflare,
 * or fast local JSON/SQLite storage for development & static generation.
 */
// ponytail: merge seed + comparison JSON so new posts always render even when prod D1 has rows (D1 wins per slug)
let inMemoryPosts: BlogPost[] = [...(seedPosts as BlogPost[]), ...(comparisonPosts as BlogPost[])];

export async function getAllPosts(env?: { DB?: any }): Promise<BlogPost[]> {
  // If Cloudflare D1 binding is provided at runtime
  if (env?.DB) {
    try {
      const result = await env.DB.prepare(
        "SELECT * FROM posts WHERE is_published = 1 ORDER BY created_at DESC"
      ).all();
      if (result.results) {
        const dbPosts: BlogPost[] = result.results.map((row: any) => ({
          ...row,
          tags: typeof row.tags === "string" ? JSON.parse(row.tags) : row.tags,
          is_published: Boolean(row.is_published),
        }));
        // ponytail: D1 wins per slug; seed/comparison posts still render when D1 lacks them
        const bySlug = new Map<string, BlogPost>();
        for (const p of [...inMemoryPosts, ...dbPosts]) bySlug.set(p.slug, p);
        return [...bySlug.values()].sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
      }
    } catch (err) {
      console.warn("D1 query error, falling back to local store:", err);
    }
  }

  return inMemoryPosts
    .filter((post) => Boolean(post.is_published))
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
}

export async function getPostBySlug(slug: string, env?: { DB?: any }): Promise<BlogPost | null> {
  if (env?.DB) {
    try {
      const result = await env.DB.prepare("SELECT * FROM posts WHERE slug = ?").bind(slug).first();
      if (result) {
        return {
          ...result,
          tags: typeof result.tags === "string" ? JSON.parse(result.tags) : result.tags,
          is_published: Boolean(result.is_published),
        };
      }
    } catch (err) {
      console.warn("D1 query error, falling back to local store:", err);
    }
  }

  return inMemoryPosts.find((p) => p.slug === slug) || null;
}

export async function createPost(input: CreateBlogPostInput, env?: { DB?: any }): Promise<BlogPost> {
  const newPost: BlogPost = {
    ...input,
    id: input.id || `post_${Date.now()}`,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  if (env?.DB) {
    try {
      await env.DB.prepare(`
        INSERT INTO posts (id, slug, title, description, content_markdown, category, tags, author, read_time, cover_image, accent_gradient, icon, is_published, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).bind(
        newPost.id,
        newPost.slug,
        newPost.title,
        newPost.description,
        newPost.content_markdown,
        newPost.category,
        JSON.stringify(newPost.tags || []),
        newPost.author || "VidRank Team",
        newPost.read_time || "5 min read",
        newPost.cover_image || null,
        newPost.accentGradient || "from-cyan/20 via-blue-500/10 to-transparent",
        newPost.icon || "wand-sparkles",
        newPost.is_published ? 1 : 0,
        newPost.created_at,
        newPost.updated_at
      ).run();
    } catch (err) {
      console.error("Failed to insert into Cloudflare D1:", err);
    }
  }

  // Update in-memory list
  inMemoryPosts = inMemoryPosts.filter((p) => p.slug !== newPost.slug);
  inMemoryPosts.unshift(newPost);

  return newPost;
}

export async function updatePost(slug: string, updates: Partial<BlogPost>, env?: { DB?: any }): Promise<BlogPost | null> {
  const existing = await getPostBySlug(slug, env);
  if (!existing) return null;

  const updated: BlogPost = {
    ...existing,
    ...updates,
    updated_at: new Date().toISOString(),
  };

  if (env?.DB) {
    try {
      await env.DB.prepare(`
        UPDATE posts SET title = ?, description = ?, content_markdown = ?, category = ?, tags = ?, author = ?, read_time = ?, is_published = ?, updated_at = ?
        WHERE slug = ?
      `).bind(
        updated.title,
        updated.description,
        updated.content_markdown,
        updated.category,
        JSON.stringify(updated.tags || []),
        updated.author,
        updated.read_time,
        updated.is_published ? 1 : 0,
        updated.updated_at,
        slug
      ).run();
    } catch (err) {
      console.error("Failed to update in Cloudflare D1:", err);
    }
  }

  inMemoryPosts = inMemoryPosts.map((p) => (p.slug === slug ? updated : p));
  return updated;
}

export async function deletePost(slug: string, env?: { DB?: any }): Promise<boolean> {
  if (env?.DB) {
    try {
      await env.DB.prepare("DELETE FROM posts WHERE slug = ?").bind(slug).run();
    } catch (err) {
      console.error("Failed to delete in Cloudflare D1:", err);
    }
  }

  const initialLen = inMemoryPosts.length;
  inMemoryPosts = inMemoryPosts.filter((p) => p.slug !== slug);
  return inMemoryPosts.length < initialLen;
}
