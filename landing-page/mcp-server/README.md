# VidRank Blog MCP Server 🤖✍️

A Model Context Protocol (MCP) Server that allows AI Agents (Claude, Gemini, Cursor, OpenCode, Antigravity) to research, draft, edit, and publish YouTube SEO blog posts directly to the VidRank platform.

---

## 🛠️ Available MCP Tools

| Tool Name | Description |
| :--- | :--- |
| `publish_blog_post` | Creates and publishes a complete YouTube SEO guide or article with title, slug, metadata, category, tags, and Markdown body. |
| `list_blog_posts` | Lists all existing blog posts with filters for category, author, and date. |
| `get_blog_post` | Fetches the full Markdown content and SEO metadata for a specific article. |
| `update_blog_post` | Updates existing content, titles, keywords, or descriptions. |
| `delete_blog_post` | Unpublishes or deletes an article by its slug. |

---

## 🚀 Setup & Installation

### 1. Install Dependencies
```bash
cd mcp-server
pnpm install
```

### 2. Build the Server
```bash
pnpm build
```

---

## 🔌 Connecting to AI Clients

### 1. Claude Desktop (`claude_desktop_config.json`)
Add the following to your Claude Desktop configuration:
```json
{
  "mcpServers": {
    "vidrank-blog": {
      "command": "node",
      "args": [
        "/Users/macm1/Desktop/vidrank/landing-page/mcp-server/dist/index.js"
      ]
    }
  }
}
```

### 2. Cursor / Antigravity IDE (`mcp.json`)
```json
{
  "mcpServers": {
    "vidrank-blog": {
      "command": "node",
      "args": ["/Users/macm1/Desktop/vidrank/landing-page/mcp-server/dist/index.js"]
    }
  }
}
```

---

## 📝 Example AI Prompt
Once connected, you can tell your AI Agent:
> *"Write a comprehensive 1000-word guide on how to optimize YouTube video tags for high search intent in 2026, and publish it using the `publish_blog_post` tool."*

The AI agent will draft the article and publish it automatically!
