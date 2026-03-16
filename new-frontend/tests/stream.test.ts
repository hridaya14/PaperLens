import { describe, expect, it } from "vitest";
import { parseStreamEvent } from "@/lib/stream";

describe("stream parsing", () => {
  it("parses a valid SSE-style data line", () => {
    const event = parseStreamEvent('data: {"chunk":"Hello","done":false}');
    expect(event).toEqual({
      chunk: "Hello",
      done: false
    });
  });

  it("returns null for invalid lines", () => {
    expect(parseStreamEvent("event: noop")).toBeNull();
    expect(parseStreamEvent("data: nope")).toBeNull();
  });
});
