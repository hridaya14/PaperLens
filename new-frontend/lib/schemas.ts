import { z } from "zod";

export const ApiErrorSchema = z
  .object({
    error: z.string().optional(),
    detail: z.unknown().optional()
  })
  .passthrough();

export const PaperSchema = z.object({
  id: z.union([z.string(), z.number()]).transform((value) => String(value)),
  arxiv_id: z.string(),
  title: z.string(),
  authors: z.array(z.string()).default([]),
  abstract: z.string().default(""),
  categories: z.array(z.string()).default([]),
  published_date: z.union([z.string(), z.date().transform((value) => value.toISOString())]),
  pdf_url: z.string(),
  pdf_processed: z.boolean().default(false)
});

export const PaperSearchResponseSchema = z.object({
  papers: z.array(PaperSchema),
  total: z.number().int().nonnegative()
});

export const PaperSearchParamsSchema = z.object({
  query: z.string().trim().optional(),
  categories: z.array(z.string()).default([]),
  pdfProcessed: z.boolean().nullable().default(null),
  limit: z.number().int().min(1).max(100).default(20),
  offset: z.number().int().min(0).default(0)
});

export const ChatRequestSchema = z.object({
  query: z.string().trim().min(1),
  top_k: z.number().int().min(1).max(10).default(3),
  use_hybrid: z.boolean().default(true),
  model: z.string().min(1),
  categories: z.array(z.string()).nullable().default(null)
});

export const ChatResponseSchema = z.object({
  query: z.string().optional(),
  answer: z.string(),
  sources: z.array(z.string()).default([]),
  chunks_used: z.number().int().nonnegative(),
  search_mode: z.string()
});

export type MindMapNode = {
  id: string;
  label: string;
  description?: string | null;
  node_type: "root" | "problem" | "approach" | "concept" | "finding" | "limitation" | "contribution";
  importance: "primary" | "secondary" | "tertiary";
  source_section?: string | null;
  children: MindMapNode[];
};

export const MindMapNodeSchema: z.ZodType<MindMapNode> = z.lazy(() =>
  z.object({
    id: z.string(),
    label: z.string(),
    description: z.string().nullable().optional(),
    node_type: z.enum(["root", "problem", "approach", "concept", "finding", "limitation", "contribution"]),
    importance: z.enum(["primary", "secondary", "tertiary"]),
    source_section: z.string().nullable().optional(),
    children: z.array(MindMapNodeSchema).default([])
  })
);

export const MindMapSchema = z.object({
  paper_id: z.string(),
  arxiv_id: z.string(),
  paper_title: z.string(),
  root: MindMapNodeSchema,
  sections_covered: z.array(z.string()).default([]),
  generated_at: z.string(),
  model_used: z.string()
});

export const FlashcardSchema = z.object({
  id: z.union([z.number(), z.string()]).nullable().optional(),
  paper_id: z.string(),
  front: z.string(),
  back: z.string(),
  topic: z.string().nullable().optional(),
  difficulty: z.string().nullable().optional(),
  card_index: z.number().int().nonnegative(),
  generated_at: z.string()
});

export const FlashcardMetaSchema = z
  .object({
    total_cards: z.number().int().nonnegative().optional(),
    generated_at: z.string().optional(),
    expires_at: z.string().optional(),
    is_fresh: z.boolean().optional(),
    is_cached: z.boolean().optional(),
    topics_covered: z.array(z.string()).optional(),
    model_used: z.string().optional()
  })
  .passthrough();

export const FlashcardSetSchema = z.object({
  paper_id: z.string(),
  arxiv_id: z.string().nullable().optional(),
  paper_title: z.string(),
  flashcards: z.array(FlashcardSchema),
  meta: FlashcardMetaSchema.default({})
});

export const StreamChunkEventSchema = z.object({
  chunk: z.string().optional(),
  answer: z.string().optional(),
  sources: z.array(z.string()).optional(),
  chunks_used: z.number().int().nonnegative().optional(),
  search_mode: z.string().optional(),
  done: z.boolean().optional(),
  error: z.string().optional()
});

export type Paper = z.infer<typeof PaperSchema>;
export type PaperSearchResponse = z.infer<typeof PaperSearchResponseSchema>;
export type PaperSearchParams = z.infer<typeof PaperSearchParamsSchema>;
export type ChatRequest = z.infer<typeof ChatRequestSchema>;
export type ChatResponse = z.infer<typeof ChatResponseSchema>;
export type MindMap = z.infer<typeof MindMapSchema>;
export type Flashcard = z.infer<typeof FlashcardSchema>;
export type FlashcardSet = z.infer<typeof FlashcardSetSchema>;
export type StreamChunkEvent = z.infer<typeof StreamChunkEventSchema>;
