import { NextResponse } from "next/server";
import { getApiBaseUrl } from "@/lib/env";

export async function DELETE(
  _: Request,
  context: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await context.params;
    const response = await fetch(`${getApiBaseUrl()}/papers/${id}`, {
      method: "DELETE",
    });

    if (!response.ok) {
      const payload = await safeJson(response);
      return NextResponse.json(payload ?? { error: "Delete failed" }, {
        status: response.status,
      });
    }

    return new NextResponse(null, { status: 204 });
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
