import type { AskResponse, StreamChunkEvent } from "@/lib/schemas";
import { askResponseSchema } from "@/lib/schemas";

export function parseStreamEvent(line: string) {
  if (!line.startsWith("data: ")) {
    return null;
  }

  try {
    return JSON.parse(line.slice(6)) as StreamChunkEvent;
  } catch {
    return null;
  }
}

export async function readChatStream(
  response: Response,
  handlers: {
    onChunk: (event: StreamChunkEvent) => void;
    onComplete: (answer: string) => void;
  }
) {
  if (!response.body) {
    throw new Error("Streaming response body is missing.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalAnswer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const segments = buffer.split("\n\n");
    buffer = segments.pop() ?? "";

    for (const segment of segments) {
      for (const line of segment.split("\n")) {
        const event = parseStreamEvent(line.trim());
        if (!event) {
          continue;
        }

        if (event.chunk) {
          finalAnswer += event.chunk;
        }

        if (event.answer) {
          finalAnswer = event.answer;
        }

        handlers.onChunk(event);

        if (event.done) {
          handlers.onComplete(finalAnswer);
          return finalAnswer;
        }

        if (event.error) {
          throw new Error(event.error);
        }
      }
    }
  }

  handlers.onComplete(finalAnswer);
  return finalAnswer;
}

export async function readJsonResponse<T>(response: Response, schema: { parse: (value: unknown) => T }) {
  if (!response.ok) {
    const payload = await safeJson(response);
    throw new Error(payload?.error ?? payload?.detail ?? `Request failed with status ${response.status}`);
  }

  const json = await response.json();
  return schema.parse(json);
}

async function safeJson(response: Response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function readAskResponse(response: Response): Promise<AskResponse> {
  return readJsonResponse(response, askResponseSchema);
}
