import { NextRequest, NextResponse } from "next/server";
import { askQuestion } from "@/lib/api/backend";

export async function POST(request: NextRequest) {
  try {
    const payload = await request.json();
    const answer = await askQuestion(payload);
    return NextResponse.json(answer);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unexpected proxy error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
