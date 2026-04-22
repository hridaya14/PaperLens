import { getApiBaseUrl } from "@/lib/env";
import {
    askResponseSchema,
    chatRequestSchema,
    flashcardSetSchema,
    mindMapSchema,
    paperSearchResponseSchema,
} from "@/lib/schemas";
import { buildQueryString } from "@/lib/utils";

export async function fetchPaperSearch(params: {
    query?: string | null;
    categories?: string[] | null;
    pdfProcessed?: boolean | null;
    source?: string | null;
    limit?: number;
    offset?: number;
}) {
    const query = buildQueryString({
        q: params.query ?? undefined,
        categories: params.categories ?? undefined,
        pdf_processed: params.pdfProcessed ?? undefined,
        source: params.source ?? undefined,
        limit: params.limit ?? 20,
        offset: params.offset ?? 0,
    });

    const response = await fetch(`${getApiBaseUrl()}/papers/search?${query}`, {
        next: { revalidate: 0 },
    });

    const json = await parseApiJson(response);
    return paperSearchResponseSchema.parse(json);
}

export async function fetchMindMap(paperId: string) {
    const response = await fetch(
        `${getApiBaseUrl()}/visualization/${paperId}/mindmap`,
        {
            next: { revalidate: 0 },
        },
    );
    const json = await parseApiJson(response);
    return mindMapSchema.parse(json);
}

export async function fetchFlashcards(
    paperId: string,
    params: { numCards?: number; forceRefresh?: boolean } = {},
) {
    const query = buildQueryString({
        num_cards: params.numCards ?? 15,
        force_refresh: params.forceRefresh ?? false,
    });

    const response = await fetch(
        `${getApiBaseUrl()}/visualization/${paperId}/flashcards?${query}`,
        {
            next: { revalidate: 0 },
        },
    );
    const json = await parseApiJson(response);
    return flashcardSetSchema.parse(json);
}

export async function askQuestion(payload: unknown) {
    const body = chatRequestSchema.parse(payload);
    const response = await fetch(`${getApiBaseUrl()}/ask`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
        cache: "no-store",
    });

    const json = await parseApiJson(response);
    return askResponseSchema.parse(json);
}

export async function openChatStream(payload: unknown) {
    const body = chatRequestSchema.parse(payload);
    const response = await fetch(`${getApiBaseUrl()}/stream`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
        },
        body: JSON.stringify(body),
        cache: "no-store",
    });

    if (!response.ok || !response.body) {
        const error = await tryReadError(response);
        throw new Error(
            error ?? `Streaming request failed with status ${response.status}`,
        );
    }

    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("text/event-stream")) {
        throw new Error("Streaming response did not return an event stream.");
    }

    return response;
}

async function parseApiJson(response: Response) {
    if (!response.ok) {
        const error = await tryReadError(response);
        throw new Error(
            error ?? `Request failed with status ${response.status}`,
        );
    }

    return response.json();
}

async function tryReadError(response: Response) {
    try {
        const json = await response.json();
        return json.detail ?? json.error ?? null;
    } catch {
        return null;
    }
}
