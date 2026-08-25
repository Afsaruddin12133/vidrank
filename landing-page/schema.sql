-- Cloudflare D1 Database Schema for VidRank Blog Posts

CREATE TABLE IF NOT EXISTS posts (
  id TEXT PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  content_markdown TEXT NOT NULL,
  category TEXT NOT NULL,
  category_color TEXT DEFAULT 'text-cyan bg-cyan/10 border-cyan/20',
  tags TEXT DEFAULT '[]', -- JSON array encoded as string
  author TEXT DEFAULT 'VidRank AI Strategist',
  read_time TEXT DEFAULT '5 min read',
  cover_image TEXT,
  accent_gradient TEXT DEFAULT 'from-cyan/20 via-blue-500/10 to-transparent',
  icon TEXT DEFAULT 'wand-sparkles',
  is_published INTEGER DEFAULT 1, -- 1 for true, 0 for false
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

-- Index for fast slug lookups and date sorting
CREATE INDEX IF NOT EXISTS idx_posts_slug ON posts (slug);
CREATE INDEX IF NOT EXISTS idx_posts_created ON posts (created_at DESC);
