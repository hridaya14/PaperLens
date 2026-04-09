import { z } from "zod";

export const paperSchema = z.object({
  id: z.string().uuid(),
  arxiv_id: z.string().nullable().optional(),
  title: z.string(),
  authors: z.array(z.string()).default([]),
  abstract: z.string().default(""),
  categories: z.array(z.string()).default([]),
  published_date: z.string().or(z.date()),
  pdf_url: z.string(),
  raw_text: z.string().nullable().optional(),
  sections: z.array(z.record(z.string(), z.any())).nullable().optional(),
  references: z.array(z.record(z.string(), z.any())).nullable().optional(),
  parser_used: z.string().nullable().optional(),
  parser_metadata: z.record(z.string(), z.any()).nullable().optional(),
  pdf_processed: z.boolean().default(false),
  pdf_processing_date: z.string().nullable().optional(),
  created_at: z.string().or(z.date()),
  updated_at: z.string().or(z.date()),
});

export const paperSearchResponseSchema = z.object({
  papers: z.array(paperSchema),
  total: z.number(),
});

export const askResponseSchema = z.object({
  query: z.string(),
  answer: z.string(),
  sources: z.array(z.string().url()),
  chunks_used: z.number(),
  search_mode: z.string(),
});

export const mindMapNodeSchema: z.ZodType<MindMapNode> = z.lazy(() =>
  z.object({
    id: z.string(),
    label: z.string(),
    description: z.string().nullable().optional(),
    node_type: z.enum([
      "root",
      "problem",
      "approach",
      "concept",
      "finding",
      "limitation",
      "contribution",
    ]),
    importance: z.enum(["primary", "secondary", "tertiary"]),
    source_section: z.string().nullable().optional(),
    children: z.array(mindMapNodeSchema).default([]),
  }),
);

export const mindMapSchema = z.object({
  paper_id: z.string(),
  arxiv_id: z.string().nullable().optional(),
  paper_title: z.string(),
  root: mindMapNodeSchema,
  sections_covered: z.array(z.string()).default([]),
  generated_at: z.string().or(z.date()),
  model_used: z.string(),
});

export const flashcardSchema = z.object({
  id: z.number().nullable().optional(),
  paper_id: z.string(),
  front: z.string(),
  back: z.string(),
  topic: z.string().nullable().optional(),
  difficulty: z.string().nullable().optional(),
  card_index: z.number(),
  generated_at: z.string().or(z.date()),
});

export const flashcardSetSchema = z.object({
  paper_id: z.string(),
  arxiv_id: z.string().nullable().optional(),
  paper_title: z.string(),
  flashcards: z.array(flashcardSchema),
  meta: z.record(z.string(), z.any()).default({}),
});

export const uploadAcceptedSchema = z.object({
  task_id: z.string(),
  message: z.string().optional(),
});

export const uploadStatusSchema = z.object({
  task_id: z.string(),
  status: z.enum(["pending", "processing", "completed", "failed"]),
  paper_id: z.string().uuid().nullable().optional(),
  original_filename: z.string().nullable().optional(),
  progress: z.record(z.string(), z.any()).nullable().optional(),
  error: z.string().nullable().optional(),
  created_at: z.string().or(z.date()),
  updated_at: z.string().or(z.date()),
});

export const uploadedPaperSchema = z.object({
  id: z.string().uuid(),
  source: z.string(),
  original_filename: z.string().nullable().optional(),
  uploaded_at: z.string().or(z.date()).nullable().optional(),
  title: z.string(),
  authors: z.array(z.string()).default([]),
  abstract: z.string().default(""),
  categories: z.array(z.string()).default([]),
  published_date: z.string().or(z.date()),
  pdf_url: z.string(),
  raw_text: z.string().nullable().optional(),
  sections: z.array(z.record(z.string(), z.any())).nullable().optional(),
  references: z.array(z.record(z.string(), z.any())).nullable().optional(),
  pdf_processed: z.boolean(),
  pdf_processing_date: z.string().or(z.date()).nullable().optional(),
  parser_used: z.string().nullable().optional(),
  parser_metadata: z.record(z.string(), z.any()).nullable().optional(),
  chunks_indexed: z.number().nullable().optional(),
  created_at: z.string().or(z.date()),
  updated_at: z.string().or(z.date()),
});

export const chatRequestSchema = z.object({
  query: z.string().min(1).max(1000),
  top_k: z.number().min(1).max(10),
  use_hybrid: z.boolean(),
  model: z.string(),
  categories: z.array(z.string()).nullable().optional(),
});

export type Paper = z.infer<typeof paperSchema>;
export type PaperSearchResponse = z.infer<typeof paperSearchResponseSchema>;
export type AskResponse = z.infer<typeof askResponseSchema>;
export type MindMap = z.infer<typeof mindMapSchema>;
export type FlashcardSetResponse = z.infer<typeof flashcardSetSchema>;
export type UploadAcceptedResponse = z.infer<typeof uploadAcceptedSchema>;
export type UploadStatusResponse = z.infer<typeof uploadStatusSchema>;
export type UploadedPaperResponse = z.infer<typeof uploadedPaperSchema>;
export type ChatRequest = z.infer<typeof chatRequestSchema>;

export type MindMapNode = {
  id: string;
  label: string;
  description?: string | null;
  node_type:
    | "root"
    | "problem"
    | "approach"
    | "concept"
    | "finding"
    | "limitation"
    | "contribution";
  importance: "primary" | "secondary" | "tertiary";
  source_section?: string | null;
  children: MindMapNode[];
};

export type StreamMetadataEvent = {
  sources?: string[];
  chunks_used?: number;
  search_mode?: string;
};

export type StreamChunkEvent = {
  chunk?: string;
  answer?: string;
  done?: boolean;
  error?: string;
  sources?: string[];
  chunks_used?: number;
  search_mode?: string;
};
