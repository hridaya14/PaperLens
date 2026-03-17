import {
  askResponseSchema,
  chatRequestSchema,
  flashcardSetSchema,
  mindMapSchema,
  paperSearchResponseSchema,
  type ChatRequest
} from "@/lib/schemas";
import { buildQueryString } from "@/lib/utils";

export async function getPapers(params: {
  query?: string;
  categories?: string[];
  pdfProcessed?: boolean | null;
  limit?: number;
  offset?: number;
}) {
  const query = buildQueryString({
    q: params.query,
    categories: params.categories,
    pdf_processed: params.pdfProcessed ?? undefined,
    limit: params.limit ?? 20,
    offset: params.offset ?? 0
  });

  const response = await fetch(`/api/papers/search?${query}`, {
    cache: "no-store"
  });

  return readClientJson(response, paperSearchResponseSchema);
}

export async function getMindMap(paperId: string) {
  const response = await fetch(`/api/visualization/${paperId}/mindmap`, {
    cache: "no-store"
  });

  return readClientJson(response, mindMapSchema);
}

export async function getFlashcards(paperId: string, options: { numCards?: number; forceRefresh?: boolean } = {}) {
  const query = buildQueryString({
    num_cards: options.numCards ?? 15,
    force_refresh: options.forceRefresh ?? false
  });

  const response = await fetch(`/api/visualization/${paperId}/flashcards?${query}`, {
    cache: "no-store"
  });

  return readClientJson(response, flashcardSetSchema);
}

export async function postChat(payload: ChatRequest) {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(chatRequestSchema.parse(payload))
  });

  return readClientJson(response, askResponseSchema);
}

export async function postChatStream(payload: ChatRequest, signal?: AbortSignal) {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(chatRequestSchema.parse(payload)),
    signal
  });

  if (!response.ok || !response.body) {
    const error = await safeError(response);
    throw new Error(error ?? `Streaming request failed with status ${response.status}`);
  }

  return response;
}

async function readClientJson<T>(response: Response, schema: { parse: (value: unknown) => T }) {
  if (!response.ok) {
    const error = await safeError(response);
    throw new Error(error ?? `Request failed with status ${response.status}`);
  }

  const json = await response.json();
  return schema.parse(json);
}

async function safeError(response: Response) {
  try {
    const json = await response.json();
    return json.error ?? json.detail ?? null;
  } catch {
    return null;
  }
}
