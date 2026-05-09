import { NextRequest, NextResponse } from "next/server";
import { fetchMindMap } from "@/lib/api/backend";

export async function GET(_: NextRequest, context: { params: Promise<{ paperId: string }> }) {
  try {
    const { paperId } = await context.params;
    const mindMap = await fetchMindMap(paperId);
    return NextResponse.json(mindMap);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unexpected proxy error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
