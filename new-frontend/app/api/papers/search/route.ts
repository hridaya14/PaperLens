import { NextRequest, NextResponse } from "next/server";
import { fetchPaperSearch } from "@/lib/api/backend";

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const q = searchParams.get("q");
    const categories = searchParams.getAll("categories");
    const pdfProcessed = parseBoolean(searchParams.get("pdf_processed"));
    const source = searchParams.get("source");
    const limit = parseNumber(searchParams.get("limit"), 20);
    const offset = parseNumber(searchParams.get("offset"), 0);

    const papers = await fetchPaperSearch({
      query: q,
      categories: categories.length ? categories : null,
      pdfProcessed,
      source,
      limit,
      offset,
    });

    return NextResponse.json(papers);
  } catch (error) {
    return toErrorResponse(error);
  }
}

function parseBoolean(value: string | null) {
  if (value === "true") {
    return true;
  }
  if (value === "false") {
    return false;
  }
  return null;
}

function parseNumber(value: string | null, fallback: number) {
  if (!value) {
    return fallback;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isNaN(parsed) ? fallback : parsed;
}

function toErrorResponse(error: unknown) {
  const message =
    error instanceof Error ? error.message : "Unexpected proxy error";
  return NextResponse.json({ error: message }, { status: 500 });
}
