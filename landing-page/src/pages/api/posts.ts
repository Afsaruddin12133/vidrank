import type { APIRoute } from "astro";
import { getAllPosts, getPostBySlug, createPost, updatePost } from "../../lib/blog";

export const prerender = false; // Always dynamic API endpoint

const API_SECRET = import.meta.env.BLOG_API_SECRET || "vidrank-secret-n8n-key";

export const GET: APIRoute = async ({ locals }) => {
  const env = (locals as any)?.runtime?.env;
  const posts = await getAllPosts(env);
  return new Response(JSON.stringify({ success: true, count: posts.length, posts }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
};

export const POST: APIRoute = async ({ request, locals }) => {
  try {
    const env = (locals as any)?.runtime?.env;
    const configuredSecret = env?.BLOG_API_SECRET || import.meta.env.BLOG_API_SECRET || "vidrank-secret-n8n-key";

    // 1. Authenticate Request
    const authHeader = request.headers.get("x-api-key") || request.headers.get("authorization")?.replace("Bearer ", "");
    if (authHeader !== configuredSecret) {
      return new Response(JSON.stringify({ success: false, error: "Unauthorized: Invalid API key" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }

    // 2. Parse Body
    const body = await request.json();
    const { title, slug, description, content_markdown, category, tags, author, read_time, cover_image } = body;

    if (!title || !slug || !content_markdown || !category) {
      return new Response(
        JSON.stringify({
          success: false,
          error: "Missing required fields: 'title', 'slug', 'content_markdown', and 'category' are required.",
        }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    const existing = await getPostBySlug(slug, env);

    if (existing) {
      const updated = await updatePost(
        slug,
        {
          title,
          description: description || existing.description,
          content_markdown,
          category,
          tags: tags || existing.tags,
          author: author || existing.author,
          read_time: read_time || existing.read_time,
          cover_image: cover_image || existing.cover_image,
          is_published: 1,
        },
        env
      );
      return new Response(JSON.stringify({ success: true, message: `Post '${slug}' updated successfully`, post: updated }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    const newPost = await createPost(
      {
        slug,
        title,
        description: description || "",
        content_markdown,
        category,
        tags: Array.isArray(tags) ? tags : [],
        author: author || "VidRank AI Strategist",
        read_time: read_time || "5 min read",
        cover_image,
        accentGradient: "from-cyan/20 via-blue-500/10 to-transparent",
        icon: "wand-sparkles",
        is_published: 1,
      },
      env
    );

    return new Response(JSON.stringify({ success: true, message: `Post '${slug}' published successfully!`, post: newPost }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err: any) {
    return new Response(JSON.stringify({ success: false, error: err.message || "Internal server error" }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
};
