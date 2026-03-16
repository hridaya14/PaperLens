import { NextRequest, NextResponse } from "next/server";
import { fetchFlashcards } from "@/lib/api/backend";

export async function GET(request: NextRequest, context: { params: Promise<{ paperId: string }> }) {
  try {
    const { paperId } = await context.params;
    const params = request.nextUrl.searchParams;
    const flashcards = await fetchFlashcards(paperId, {
      numCards: parseNumber(params.get("num_cards"), 15),
      forceRefresh: params.get("force_refresh") === "true"
    });

    return NextResponse.json(flashcards);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unexpected proxy error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

function parseNumber(value: string | null, fallback: number) {
  if (!value) {
    return fallback;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isNaN(parsed) ? fallback : parsed;
}
