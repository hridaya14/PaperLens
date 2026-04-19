import { NextResponse } from "next/server";
import { getApiBaseUrl } from "@/lib/env";

export async function GET(
  _: Request,
  context: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await context.params;
    const response = await fetch(`${getApiBaseUrl()}/papers/${id}/pdf`, {
      cache: "no-store",
    });

    if (!response.ok) {
      const payload = await safeJson(response);
      return NextResponse.json(payload ?? { error: "Failed to fetch PDF" }, {
        status: response.status,
      });
    }

    if (!response.body) {
      return NextResponse.json(
        { error: "PDF response had no body" },
        { status: 502 },
      );
    }

    const headers = new Headers();
    const contentType = response.headers.get("content-type");
    const contentDisposition = response.headers.get("content-disposition");
    const fallbackFilename = `${id}.pdf`;

    if (contentType) {
      headers.set("content-type", contentType);
    }
    if (contentDisposition) {
      const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/i);
      const filename = filenameMatch?.[1] ?? fallbackFilename;
      headers.set("content-disposition", `inline; filename="${filename}"`);
    } else {
      headers.set(
        "content-disposition",
        `inline; filename="${fallbackFilename}"`,
      );
    }

    return new Response(response.body, {
      status: 200,
      headers,
    });
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
