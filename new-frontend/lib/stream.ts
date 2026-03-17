import { StreamChunkEventSchema, type StreamChunkEvent } from "@/lib/schemas";

type StreamHandlers = {
  onChunk?: (event: StreamChunkEvent) => void;
  onComplete?: (fullAnswer: string) => void;
  onError?: (error: Error) => void;
};

export function parseStreamEvent(line: string): StreamChunkEvent | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith("data:")) {
    return null;
  }

  const payload = trimmed.slice(5).trim();
  if (!payload) {
    return null;
  }

  if (payload === "[DONE]") {
    return { done: true };
  }

  try {
    const parsed = JSON.parse(payload);
    const event = StreamChunkEventSchema.safeParse(parsed);
    return event.success ? event.data : null;
  } catch {
    return null;
  }
}

export async function readChatStream(response: Response, handlers: StreamHandlers = {}) {
  if (!response.ok) {
    throw new Error(`Streaming request failed (${response.status})`);
  }

  if (!response.body) {
    throw new Error("Streaming response did not include a body.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  let answer = "";
  let buffer = "";
  let done = false;

  try {
    while (!done) {
      const result = await reader.read();
      if (result.done) {
        break;
      }

      buffer += decoder.decode(result.value, { stream: true });
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const event = parseStreamEvent(line);
        if (!event) {
          continue;
        }

        handlers.onChunk?.(event);

        if (event.error) {
          throw new Error(event.error);
        }

        if (typeof event.answer === "string") {
          answer = event.answer;
        } else if (typeof event.chunk === "string") {
          answer += event.chunk;
        }

        if (event.done) {
          done = true;
          break;
        }
      }
    }

    if (buffer) {
      const event = parseStreamEvent(buffer);
      if (event) {
        handlers.onChunk?.(event);
        if (event.error) {
          throw new Error(event.error);
        }
        if (typeof event.answer === "string") {
          answer = event.answer;
        } else if (typeof event.chunk === "string") {
          answer += event.chunk;
        }
      }
    }

    handlers.onComplete?.(answer);
    return answer;
  } catch (error) {
    const streamError = error instanceof Error ? error : new Error("Failed while parsing stream.");
    handlers.onError?.(streamError);
    throw streamError;
  } finally {
    reader.releaseLock();
  }
}
