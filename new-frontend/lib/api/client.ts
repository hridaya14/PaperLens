import { z } from "zod";
import {
    addProjectSourceResponseSchema,
    askResponseSchema,
    chatRequestSchema,
    chatSessionDetailSchema,
    chatSessionSchema,
    createProjectSchema,
    flashcardSetSchema,
    mindMapSchema,
    paperSearchResponseSchema,
    projectAskResponseSchema,
    projectChatHistorySchema,
    projectDetailSchema,
    projectSummarySchema,
    renameSessionSchema,
    sessionAskResponseSchema,
    uploadAcceptedSchema,
    uploadStatusSchema,
    uploadedPaperSchema,
    type ChatRequest,
} from "@/lib/schemas";
import { buildQueryString } from "@/lib/utils";

export async function getPapers(params: {
    query?: string;
    categories?: string[];
    pdfProcessed?: boolean | null;
    source?: string | null;
    limit?: number;
    offset?: number;
}) {
    const query = buildQueryString({
        q: params.query,
        categories: params.categories,
        pdf_processed: params.pdfProcessed ?? undefined,
        source: params.source ?? undefined,
        limit: params.limit ?? 20,
        offset: params.offset ?? 0,
    });

    const response = await fetch(`/api/papers/search?${query}`, {
        cache: "no-store",
    });

    return readClientJson(response, paperSearchResponseSchema);
}

export async function deletePaper(paperId: string) {
    return requestNoContent(`/api/papers/${paperId}`, {
        method: "DELETE",
    });
}

export async function getMindMap(paperId: string) {
    const response = await fetch(`/api/visualization/${paperId}/mindmap`, {
        cache: "no-store",
    });

    return readClientJson(response, mindMapSchema);
}

export async function getFlashcards(
    paperId: string,
    options: { numCards?: number; forceRefresh?: boolean } = {},
) {
    const query = buildQueryString({
        num_cards: options.numCards ?? 15,
        force_refresh: options.forceRefresh ?? false,
    });

    const response = await fetch(
        `/api/visualization/${paperId}/flashcards?${query}`,
        {
            cache: "no-store",
        },
    );

    return readClientJson(response, flashcardSetSchema);
}

export async function uploadPaper(formData: FormData) {
    const response = await fetch("/api/uploads/paper", {
        method: "POST",
        body: formData,
    });

    return readClientJson(response, uploadAcceptedSchema);
}

export async function getUploadStatus(taskId: string) {
    const response = await fetch(`/api/uploads/${taskId}/status`, {
        cache: "no-store",
    });

    return readClientJson(response, uploadStatusSchema);
}

export async function getUploadedPaper(paperId: string) {
    const response = await fetch(`/api/uploads/${paperId}/detail`, {
        cache: "no-store",
    });

    return readClientJson(response, uploadedPaperSchema);
}

export async function deleteUploadedPaper(paperId: string) {
    return requestNoContent(`/api/uploads/${paperId}`, {
        method: "DELETE",
    });
}

export async function listProjects() {
    const response = await fetch("/api/projects", {
        cache: "no-store",
    });

    return readClientJson(response, z.array(projectSummarySchema));
}

export async function createProject(payload: {
    name: string;
    description?: string | null;
}) {
    const body = createProjectSchema.parse({
        name: payload.name,
        description: normalizeOptionalText(payload.description),
    });

    const response = await fetch("/api/projects", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify(body),
    });

    return readClientJson(response, projectSummarySchema);
}

export async function getProject(projectId: string) {
    const response = await fetch(`/api/projects/${projectId}`, {
        cache: "no-store",
    });

    return readClientJson(response, projectDetailSchema);
}

export async function deleteProject(projectId: string) {
    return requestNoContent(`/api/projects/${projectId}`, {
        method: "DELETE",
    });
}

export async function addPaperToProject(projectId: string, paperId: string) {
    const response = await fetch(`/api/projects/${projectId}/sources`, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({ paper_id: paperId }),
    });

    return readClientJson(response, addProjectSourceResponseSchema);
}

export async function removePaperFromProject(
    projectId: string,
    paperId: string,
) {
    return requestNoContent(`/api/projects/${projectId}/sources/${paperId}`, {
        method: "DELETE",
    });
}

export async function getProjectChat(projectId: string) {
    const response = await fetch(`/api/projects/${projectId}/chat`, {
        cache: "no-store",
    });

    return readClientJson(response, projectChatHistorySchema);
}

export async function clearProjectChat(projectId: string) {
    return requestNoContent(`/api/projects/${projectId}/chat`, {
        method: "DELETE",
    });
}

export async function askProjectChat(projectId: string, payload: ChatRequest) {
    const response = await fetch(`/api/projects/${projectId}/ask`, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify(chatRequestSchema.parse(payload)),
    });

    return readClientJson(response, projectAskResponseSchema);
}

export async function streamProjectChat(
    projectId: string,
    payload: ChatRequest,
    signal?: AbortSignal,
) {
    const response = await fetch(`/api/projects/${projectId}/stream`, {
        method: "POST",
        headers: {
            ...jsonHeaders(),
            Accept: "text/event-stream",
        },
        body: JSON.stringify(chatRequestSchema.parse(payload)),
        signal,
    });

    return ensureStreamingResponse(response);
}

export async function createChatSession() {
    const response = await fetch("/api/chat/sessions", {
        method: "POST",
    });

    return readClientJson(response, chatSessionSchema);
}

export async function listChatSessions() {
    const response = await fetch("/api/chat/sessions", {
        cache: "no-store",
    });

    return readClientJson(response, z.array(chatSessionSchema));
}

export async function getChatSession(sessionId: string) {
    const response = await fetch(`/api/chat/sessions/${sessionId}`, {
        cache: "no-store",
    });

    return readClientJson(response, chatSessionDetailSchema);
}

export async function renameChatSession(sessionId: string, title: string) {
    const response = await fetch(`/api/chat/sessions/${sessionId}`, {
        method: "PATCH",
        headers: jsonHeaders(),
        body: JSON.stringify(renameSessionSchema.parse({ title })),
    });

    return readClientJson(response, chatSessionSchema);
}

export async function deleteChatSession(sessionId: string) {
    return requestNoContent(`/api/chat/sessions/${sessionId}`, {
        method: "DELETE",
    });
}

export async function clearChatSession(sessionId: string) {
    return requestNoContent(`/api/chat/sessions/${sessionId}/messages`, {
        method: "DELETE",
    });
}

export async function askChatSession(sessionId: string, payload: ChatRequest) {
    const response = await fetch(`/api/chat/sessions/${sessionId}/ask`, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify(chatRequestSchema.parse(payload)),
    });

    return readClientJson(response, sessionAskResponseSchema);
}

export async function streamChatSession(
    sessionId: string,
    payload: ChatRequest,
    signal?: AbortSignal,
) {
    const response = await fetch(`/api/chat/sessions/${sessionId}/stream`, {
        method: "POST",
        headers: {
            ...jsonHeaders(),
            Accept: "text/event-stream",
        },
        body: JSON.stringify(chatRequestSchema.parse(payload)),
        signal,
    });

    return ensureStreamingResponse(response);
}

export async function postChat(payload: ChatRequest) {
    const response = await fetch("/api/chat", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify(chatRequestSchema.parse(payload)),
    });

    return readClientJson(response, askResponseSchema);
}

export async function postChatStream(
    payload: ChatRequest,
    signal?: AbortSignal,
) {
    const response = await fetch("/api/chat/stream", {
        method: "POST",
        headers: {
            ...jsonHeaders(),
            Accept: "text/event-stream",
        },
        body: JSON.stringify(chatRequestSchema.parse(payload)),
        signal,
    });

    return ensureStreamingResponse(response);
}

function jsonHeaders() {
    return {
        "Content-Type": "application/json",
    };
}

function normalizeOptionalText(value?: string | null) {
    const trimmed = value?.trim();
    return trimmed ? trimmed : null;
}

async function ensureStreamingResponse(response: Response) {
    if (!response.ok || !response.body) {
        const error = await safeError(response);
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

async function requestNoContent(input: RequestInfo | URL, init?: RequestInit) {
    const response = await fetch(input, init);

    if (!response.ok) {
        const error = await safeError(response);
        throw new Error(
            error ?? `Request failed with status ${response.status}`,
        );
    }
}

async function readClientJson<T>(
    response: Response,
    schema: { parse: (value: unknown) => T },
) {
    if (!response.ok) {
        const error = await safeError(response);
        throw new Error(
            error ?? `Request failed with status ${response.status}`,
        );
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
