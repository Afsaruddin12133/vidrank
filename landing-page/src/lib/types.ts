export interface BlogPost {
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
  cover_image?: string;
  accentGradient?: string;
  icon?: string;
  is_published: boolean | number;
  created_at: string;
  updated_at: string;
}

export type CreateBlogPostInput = Omit<BlogPost, "id" | "created_at" | "updated_at"> & {
  id?: string;
};
