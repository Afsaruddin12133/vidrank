import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const POSTS_JSON_PATH = path.resolve(__dirname, "../../src/data/posts.json");

interface BlogPostRecord {
  id: string;
  slug: string;
  title: string;
  description: string;
  content_markdown: string;
  category: string;
  categoryColor?: string;
  tags: string[];
  author: string;
  read_time: string;
  accentGradient?: string;
  icon?: string;
  is_published: boolean;
  created_at: string;
  updated_at: string;
}

function loadPosts(): BlogPostRecord[] {
  try {
    if (fs.existsSync(POSTS_JSON_PATH)) {
      const data = fs.readFileSync(POSTS_JSON_PATH, "utf-8");
      return JSON.parse(data);
    }
  } catch (err) {
    console.error("Error reading posts.json:", err);
  }
  return [];
}

function savePosts(posts: BlogPostRecord[]) {
  try {
    fs.mkdirSync(path.dirname(POSTS_JSON_PATH), { recursive: true });
    fs.writeFileSync(POSTS_JSON_PATH, JSON.stringify(posts, null, 2), "utf-8");
  } catch (err) {
    console.error("Error saving posts.json:", err);
  }
}

// Initialize MCP Server
const server = new McpServer({
  name: "vidrank-blog-publisher",
  version: "1.0.0",
});

// Tool 1: publish_blog_post
server.tool(
  "publish_blog_post",
  "Generate and publish a new YouTube SEO blog post to the VidRank blog database",
  {
    title: z.string().describe("The catchy, SEO-optimized title for the blog article"),
    slug: z.string().describe("URL-friendly slug (e.g. 'how-to-write-youtube-titles-2026')"),
    description: z.string().describe("A compelling 1-2 sentence meta description for search snippets"),
    content_markdown: z.string().describe("The complete body of the article in Markdown formatting"),
    category: z.enum([
      "Algorithm Breakdown",
      "Keyword Strategy",
      "Metadata Blueprint",
      "CTR Optimization",
      "Channel Growth",
    ]).describe("The topic category of the article"),
    tags: z.array(z.string()).describe("List of keyword tags associated with this guide"),
    author: z.string().optional().default("VidRank AI Strategist").describe("Author attribution"),
    read_time: z.string().optional().default("5 min read").describe("Estimated reading time (e.g. '6 min read')"),
  },
  async ({ title, slug, description, content_markdown, category, tags, author, read_time }) => {
    const posts = loadPosts();

    // Check if slug already exists
    const existingIdx = posts.findIndex((p) => p.slug === slug);
    const newPost: BlogPostRecord = {
      id: `post_${Date.now()}`,
      slug,
      title,
      description,
      content_markdown,
      category,
      categoryColor:
        category === "Algorithm Breakdown"
          ? "text-cyan bg-cyan/10 border-cyan/20"
          : category === "Keyword Strategy"
          ? "text-red bg-red/10 border-red/20"
          : "text-[#3df2a4] bg-[#3df2a4]/10 border-[#3df2a4]/20",
      tags,
      author: author || "VidRank AI Strategist",
      read_time: read_time || "5 min read",
      accentGradient: "from-cyan/20 via-blue-500/10 to-transparent",
      icon: "wand-sparkles",
      is_published: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    if (existingIdx >= 0) {
      posts[existingIdx] = newPost;
    } else {
      posts.unshift(newPost);
    }

    savePosts(posts);

    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(
            {
              success: true,
              message: `Blog post '${title}' successfully published!`,
              url: `/blog/${slug}`,
              post: newPost,
            },
            null,
            2
          ),
        },
      ],
    };
  }
);

// Tool 2: list_blog_posts
server.tool(
  "list_blog_posts",
  "List all published blog posts currently in the VidRank blog database",
  {
    category: z.string().optional().describe("Optional category to filter by"),
    limit: z.number().optional().default(10).describe("Maximum number of posts to return"),
  },
  async ({ category, limit }) => {
    let posts = loadPosts();
    if (category) {
      posts = posts.filter((p) => p.category.toLowerCase() === category.toLowerCase());
    }
    const summary = posts.slice(0, limit).map((p) => ({
      id: p.id,
      slug: p.slug,
      title: p.title,
      category: p.category,
      author: p.author,
      read_time: p.read_time,
      created_at: p.created_at,
      url: `/blog/${p.slug}`,
    }));

    return {
      content: [
        {
          type: "text",
          text: JSON.stringify({ total: posts.length, posts: summary }, null, 2),
        },
      ],
    };
  }
);

// Tool 3: get_blog_post
server.tool(
  "get_blog_post",
  "Retrieve the full markdown content and metadata of a specific blog post by its slug",
  {
    slug: z.string().describe("The URL slug of the post to retrieve"),
  },
  async ({ slug }) => {
    const posts = loadPosts();
    const post = posts.find((p) => p.slug === slug);

    if (!post) {
      return {
        isError: true,
        content: [{ type: "text", text: `Error: Blog post with slug '${slug}' was not found.` }],
      };
    }

    return {
      content: [{ type: "text", text: JSON.stringify(post, null, 2) }],
    };
  }
);

// Tool 4: update_blog_post
server.tool(
  "update_blog_post",
  "Update the content, title, or metadata of an existing blog post",
  {
    slug: z.string().describe("The slug of the post to update"),
    title: z.string().optional().describe("Updated title"),
    description: z.string().optional().describe("Updated description"),
    content_markdown: z.string().optional().describe("Updated markdown content"),
    tags: z.array(z.string()).optional().describe("Updated tags"),
  },
  async ({ slug, title, description, content_markdown, tags }) => {
    const posts = loadPosts();
    const idx = posts.findIndex((p) => p.slug === slug);

    if (idx === 0 && !posts[idx]) {
      return {
        isError: true,
        content: [{ type: "text", text: `Error: Post '${slug}' not found.` }],
      };
    }

    if (title) posts[idx].title = title;
    if (description) posts[idx].description = description;
    if (content_markdown) posts[idx].content_markdown = content_markdown;
    if (tags) posts[idx].tags = tags;
    posts[idx].updated_at = new Date().toISOString();

    savePosts(posts);

    return {
      content: [
        {
          type: "text",
          text: JSON.stringify({ success: true, message: `Post '${slug}' updated successfully!`, post: posts[idx] }, null, 2),
        },
      ],
    };
  }
);

// Tool 5: delete_blog_post
server.tool(
  "delete_blog_post",
  "Delete a blog post from the database by its slug",
  {
    slug: z.string().describe("The slug of the post to delete"),
  },
  async ({ slug }) => {
    let posts = loadPosts();
    const initialLen = posts.length;
    posts = posts.filter((p) => p.slug !== slug);

    if (posts.length === initialLen) {
      return {
        isError: true,
        content: [{ type: "text", text: `Error: Post '${slug}' does not exist.` }],
      };
    }

    savePosts(posts);

    return {
      content: [
        {
          type: "text",
          text: JSON.stringify({ success: true, message: `Post '${slug}' deleted successfully.` }, null, 2),
        },
      ],
    };
  }
);

// Start MCP Server on Stdio Transport
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("VidRank Blog MCP Server running on stdio");
}

main().catch((err) => {
  console.error("Fatal error in MCP Server:", err);
  process.exit(1);
});
