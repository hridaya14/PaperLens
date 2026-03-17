import type { ZodType } from "zod";
import {
  ApiErrorSchema,
  ChatRequestSchema,
  ChatResponseSchema,
  FlashcardSetSchema,
  MindMapSchema,
  PaperSearchParamsSchema,
  PaperSearchResponseSchema,
  type ChatRequest,
  type ChatResponse,
  type FlashcardSet,
  type MindMap,
  type PaperSearchParams,
  type PaperSearchResponse
} from "@/lib/schemas";

type FlashcardOptions = {
  numCards?: number;
  forceRefresh?: boolean;
};

export async function getPapers(filters: Partial<PaperSearchParams> = {}): Promise<PaperSearchResponse> {
  const normalized = PaperSearchParamsSchema.parse(filters);
  const searchParams = new URLSearchParams();

  if (normalized.query) {
    searchParams.set("q", normalized.query);
  }

  for (const category of normalized.categories) {
    searchParams.append("categories", category);
  }

  if (normalized.pdfProcessed !== null) {
    searchParams.set("pdf_processed", String(normalized.pdfProcessed));
  }

  searchParams.set("limit", String(normalized.limit));
  searchParams.set("offset", String(normalized.offset));

  return fetchJson(`/api/papers/search?${searchParams.toString()}`, PaperSearchResponseSchema);
}

export async function postChat(payload: ChatRequest): Promise<ChatResponse> {
  const requestPayload = ChatRequestSchema.parse(payload);
  return fetchJson("/api/chat", ChatResponseSchema, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(requestPayload)
  });
}

export async function postChatStream(payload: ChatRequest, signal?: AbortSignal) {
  const requestPayload = ChatRequestSchema.parse(payload);
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/plain"
    },
    body: JSON.stringify(requestPayload),
    cache: "no-store",
    signal
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, `Streaming request failed (${response.status})`));
  }

  if (!response.body) {
    throw new Error("Streaming response body is missing.");
  }

  return response;
}

export async function getMindMap(paperId: string): Promise<MindMap> {
  const safeId = encodeURIComponent(paperId);
  return fetchJson(`/api/visualization/${safeId}/mindmap`, MindMapSchema);
}

export async function getFlashcards(paperId: string, options: FlashcardOptions = {}): Promise<FlashcardSet> {
  const safeId = encodeURIComponent(paperId);
  const searchParams = new URLSearchParams();

  if (typeof options.numCards === "number") {
    searchParams.set("num_cards", String(options.numCards));
  }

  if (options.forceRefresh) {
    searchParams.set("force_refresh", "true");
  }

  const query = searchParams.toString();
  const suffix = query ? `?${query}` : "";

  return fetchJson(`/api/visualization/${safeId}/flashcards${suffix}`, FlashcardSetSchema);
}

async function fetchJson<T>(url: string, schema: ZodType<T>, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  const response = await fetch(url, {
    ...init,
    headers,
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, `Request failed (${response.status})`));
  }

  const payload = await response.json();
  return schema.parse(payload);
}

async function getErrorMessage(response: Response, fallback: string) {
  try {
    const payload = await response.json();
    const parsed = ApiErrorSchema.safeParse(payload);
    if (!parsed.success) {
      return fallback;
    }

    const detail = parsed.data.detail;
    if (parsed.data.error) {
      return parsed.data.error;
    }

    if (typeof detail === "string") {
      return detail;
    }

    if (Array.isArray(detail)) {
      return detail.map((item) => String(item)).join("; ");
    }
  } catch {
    // Ignore JSON parsing errors.
  }

  return fallback;
}
