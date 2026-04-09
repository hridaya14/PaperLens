import { NextRequest, NextResponse } from "next/server";
import { getApiBaseUrl } from "@/lib/env";

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const response = await fetch(`${getApiBaseUrl()}/uploads/paper`, {
      method: "POST",
      body: formData
    });

    const payload = await safeJson(response);
    return NextResponse.json(payload ?? { error: "Empty response from backend" }, { status: response.status });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unexpected proxy error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

async function safeJson(response: Response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}
