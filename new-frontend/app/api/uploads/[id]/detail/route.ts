import { NextResponse } from "next/server";
import { getApiBaseUrl } from "@/lib/env";

export async function GET(
  _: Request,
  context: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await context.params;
    const response = await fetch(`${getApiBaseUrl()}/uploads/${id}/detail`, {
      cache: "no-store",
    });

    const payload = await safeJson(response);
    return NextResponse.json(
      payload ?? { error: "Empty response from backend" },
      { status: response.status },
    );
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unexpected proxy error";
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
