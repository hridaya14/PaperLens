import { z } from "zod";

const dateValueSchema = z.string().or(z.date());
const nullableStringSchema = z.string().nullable().optional();
const jsonRecordSchema = z.record(z.string(), z.any());
const chatRoleSchema = z.enum(["user", "assistant"]);

export const paperSchema = z.object({
  id: z.string().uuid(),
  arxiv_id: nullableStringSchema,
  title: z.string(),
  authors: z.array(z.string()).default([]),
  abstract: z.string().default(""),
  categories: z.array(z.string()).default([]),
  published_date: dateValueSchema,
  pdf_url: z.string(),
  raw_text: z.string().nullable().optional(),
  sections: z.array(jsonRecordSchema).nullable().optional(),
  references: z.array(jsonRecordSchema).nullable().optional(),
  parser_used: nullableStringSchema,
  parser_metadata: jsonRecordSchema.nullable().optional(),
  pdf_processed: z.boolean().default(false),
  pdf_processing_date: nullableStringSchema,
  created_at: dateValueSchema,
  updated_at: dateValueSchema,
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
  project_id: z.string().uuid().nullable().optional(),
});

export const projectPaperSummarySchema = z.object({
  id: z.string().uuid(),
  source: z.string(),
  arxiv_id: nullableStringSchema,
  original_filename: nullableStringSchema,
  title: z.string(),
  authors: z.array(z.string()).default([]),
  abstract: z.string().default(""),
  categories: z.array(z.string()).default([]),
  published_date: dateValueSchema,
  pdf_processed: z.boolean().default(false),
  added_at: dateValueSchema,
});

export const projectSummarySchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  description: nullableStringSchema,
  overview: nullableStringSchema,
  source_count: z.number().default(0),
  created_at: dateValueSchema,
  updated_at: dateValueSchema,
});

export const projectDetailSchema = projectSummarySchema.extend({
  overview_generated_at: dateValueSchema.nullable().optional(),
  sources: z.array(projectPaperSummarySchema).default([]),
});

export const addProjectSourceResponseSchema = z.object({
  project_id: z.string().uuid(),
  paper_id: z.string().uuid(),
  added_at: dateValueSchema,
  paper: projectPaperSummarySchema,
});

export const projectChatMessageSchema = z.object({
  id: z.string().uuid(),
  project_id: z.string().uuid(),
  role: chatRoleSchema,
  content: z.string(),
  created_at: dateValueSchema,
});

export const projectChatHistorySchema = z.object({
  project_id: z.string().uuid(),
  messages: z.array(projectChatMessageSchema).default([]),
});

export const chatSessionMessageSchema = z.object({
  id: z.string().uuid(),
  session_id: z.string().uuid(),
  role: chatRoleSchema,
  content: z.string(),
  created_at: dateValueSchema,
});

export const chatSessionSchema = z.object({
  id: z.string().uuid(),
  title: nullableStringSchema,
  message_count: z.number().default(0),
  created_at: dateValueSchema,
  updated_at: dateValueSchema,
});

export const chatSessionDetailSchema = chatSessionSchema.extend({
  messages: z.array(chatSessionMessageSchema).default([]),
});

export const createProjectSchema = z.object({
  name: z.string().trim().min(1).max(255),
  description: z.string().trim().max(4000).nullable().optional(),
});

export const renameSessionSchema = z.object({
  title: z.string().trim().min(1).max(255),
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
  arxiv_id: nullableStringSchema,
  paper_title: z.string(),
  root: mindMapNodeSchema,
  sections_covered: z.array(z.string()).default([]),
  generated_at: dateValueSchema,
  model_used: z.string(),
});

export const flashcardSchema = z.object({
  id: z.number().nullable().optional(),
  paper_id: z.string(),
  front: z.string(),
  back: z.string(),
  topic: nullableStringSchema,
  difficulty: nullableStringSchema,
  card_index: z.number(),
  generated_at: dateValueSchema,
});

export const flashcardSetSchema = z.object({
  paper_id: z.string(),
  arxiv_id: nullableStringSchema,
  paper_title: z.string(),
  flashcards: z.array(flashcardSchema),
  meta: jsonRecordSchema.default({}),
});

export const uploadAcceptedSchema = z.object({
  task_id: z.string(),
  message: z.string().optional(),
});

export const uploadStatusSchema = z.object({
  task_id: z.string(),
  status: z.enum(["pending", "processing", "completed", "failed"]),
  paper_id: z.string().uuid().nullable().optional(),
  original_filename: nullableStringSchema,
  progress: jsonRecordSchema.nullable().optional(),
  error: nullableStringSchema,
  created_at: dateValueSchema,
  updated_at: dateValueSchema,
});

export const uploadedPaperSchema = z.object({
  id: z.string().uuid(),
  source: z.string(),
  original_filename: nullableStringSchema,
  uploaded_at: dateValueSchema.nullable().optional(),
  title: z.string(),
  authors: z.array(z.string()).default([]),
  abstract: z.string().default(""),
  categories: z.array(z.string()).default([]),
  published_date: dateValueSchema,
  pdf_url: z.string(),
  raw_text: z.string().nullable().optional(),
  sections: z.array(jsonRecordSchema).nullable().optional(),
  references: z.array(jsonRecordSchema).nullable().optional(),
  pdf_processed: z.boolean(),
  pdf_processing_date: dateValueSchema.nullable().optional(),
  parser_used: nullableStringSchema,
  parser_metadata: jsonRecordSchema.nullable().optional(),
  chunks_indexed: z.number().nullable().optional(),
  created_at: dateValueSchema,
  updated_at: dateValueSchema,
});

export const chatRequestSchema = z.object({
  query: z.string().min(1).max(1000),
  top_k: z.number().min(1).max(10),
  use_hybrid: z.boolean(),
  model: z.string(),
  categories: z.array(z.string()).nullable().optional(),
});

export const sessionAskResponseSchema = askResponseSchema.extend({
  session_id: z.string().uuid(),
  user_message_id: z.string().uuid(),
  assistant_message_id: z.string().uuid(),
});

export const projectAskResponseSchema = askResponseSchema.extend({
  project_id: z.string().uuid(),
  user_message_id: z.string().uuid(),
  assistant_message_id: z.string().uuid(),
});

export type Paper = z.infer<typeof paperSchema>;
export type PaperSearchResponse = z.infer<typeof paperSearchResponseSchema>;
export type AskResponse = z.infer<typeof askResponseSchema>;
export type ProjectPaperSummary = z.infer<typeof projectPaperSummarySchema>;
export type ProjectSummary = z.infer<typeof projectSummarySchema>;
export type ProjectDetail = z.infer<typeof projectDetailSchema>;
export type AddProjectSourceResponse = z.infer<
  typeof addProjectSourceResponseSchema
>;
export type ProjectChatMessage = z.infer<typeof projectChatMessageSchema>;
export type ProjectChatHistory = z.infer<typeof projectChatHistorySchema>;
export type ChatSession = z.infer<typeof chatSessionSchema>;
export type ChatSessionDetail = z.infer<typeof chatSessionDetailSchema>;
export type MindMap = z.infer<typeof mindMapSchema>;
export type FlashcardSetResponse = z.infer<typeof flashcardSetSchema>;
export type UploadAcceptedResponse = z.infer<typeof uploadAcceptedSchema>;
export type UploadStatusResponse = z.infer<typeof uploadStatusSchema>;
export type UploadedPaperResponse = z.infer<typeof uploadedPaperSchema>;
export type ChatRequest = z.infer<typeof chatRequestSchema>;
export type SessionAskResponse = z.infer<typeof sessionAskResponseSchema>;
export type ProjectAskResponse = z.infer<typeof projectAskResponseSchema>;

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
  session_id?: string;
  project_id?: string;
  user_message_id?: string;
  assistant_message_id?: string;
};

export type StreamChunkEvent = {
  chunk?: string;
  answer?: string;
  done?: boolean;
  error?: string;
  sources?: string[];
  chunks_used?: number;
  search_mode?: string;
  session_id?: string;
  project_id?: string;
  user_message_id?: string;
  assistant_message_id?: string;
};
