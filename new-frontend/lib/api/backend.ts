import { getApiBaseUrl } from "@/lib/env";
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

export type FlashcardFetchOptions = {
  numCards?: number;
  forceRefresh?: boolean;
  topics?: string[];
};

export async function fetchPaperSearch(filters: Partial<PaperSearchParams> = {}): Promise<PaperSearchResponse> {
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

  const response = await requestBackend(`/papers/search?${searchParams.toString()}`);
  const payload = await response.json();
  return PaperSearchResponseSchema.parse(payload);
}

export async function askQuestion(payload: ChatRequest): Promise<ChatResponse> {
  const requestPayload = ChatRequestSchema.parse(payload);
  const response = await requestBackend("/ask", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(requestPayload)
  });

  const body = await response.json();
  return ChatResponseSchema.parse(body);
}

export async function openChatStream(payload: ChatRequest) {
  const requestPayload = ChatRequestSchema.parse(payload);
  const response = await fetch(buildBackendUrl("/stream"), {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/plain"
    },
    body: JSON.stringify(requestPayload)
  });

  if (!response.ok) {
    throw await createRequestError(response, buildBackendUrl("/stream"));
  }

  if (!response.body) {
    throw new Error("Streaming response body is missing.");
  }

  return response;
}

export async function fetchMindMap(paperId: string): Promise<MindMap> {
  const response = await requestBackend(`/visualization/${encodeURIComponent(paperId)}/mindmap`);
  const payload = await response.json();
  return MindMapSchema.parse(payload);
}

export async function fetchFlashcards(paperId: string, options: FlashcardFetchOptions = {}): Promise<FlashcardSet> {
  const searchParams = new URLSearchParams();

  if (typeof options.numCards === "number") {
    searchParams.set("num_cards", String(options.numCards));
  }

  if (options.forceRefresh) {
    searchParams.set("force_refresh", "true");
  }

  if (options.topics?.length) {
    searchParams.set("topics", options.topics.join(","));
  }

  const query = searchParams.toString();
  const suffix = query ? `?${query}` : "";

  const response = await requestBackend(`/visualization/${encodeURIComponent(paperId)}/flashcards${suffix}`);
  const payload = await response.json();
  return FlashcardSetSchema.parse(payload);
}

async function requestBackend(path: string, init: RequestInit = {}) {
  const url = buildBackendUrl(path);
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
    throw await createRequestError(response, url);
  }

  return response;
}

function buildBackendUrl(path: string) {
  const baseUrl = `${getApiBaseUrl()}/`;
  const normalizedPath = path.replace(/^\/+/, "");
  return new URL(normalizedPath, baseUrl).toString();
}

async function createRequestError(response: Response, requestUrl: string) {
  const prefix = `Backend request failed (${response.status} ${response.statusText})`;

  try {
    const payload = await response.json();
    const parsed = ApiErrorSchema.safeParse(payload);

    if (parsed.success) {
      const detailMessage = extractDetail(parsed.data.detail);
      const explicitMessage = parsed.data.error;
      if (explicitMessage || detailMessage) {
        return new Error(`${prefix}: ${explicitMessage ?? detailMessage}`);
      }
    }
  } catch {
    // Ignore JSON parsing failures and fallback to generic error below.
  }

  return new Error(`${prefix} at ${requestUrl}`);
}

function extractDetail(detail: unknown): string {
  if (!detail) {
    return "";
  }

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail.map((item) => extractDetail(item)).filter(Boolean).join("; ");
  }

  if (typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      return "";
    }
  }

  return String(detail);
}
