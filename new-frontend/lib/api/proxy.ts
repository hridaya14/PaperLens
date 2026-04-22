import "server-only";

import { NextRequest, NextResponse } from "next/server";
import { getApiBaseUrl } from "@/lib/env";

export async function proxyBackendRequest(
    request: NextRequest,
    backendPath: string,
) {
    try {
        const targetUrl = new URL(`${getApiBaseUrl()}${backendPath}`);
        targetUrl.search = request.nextUrl.search;

        const headers = new Headers();
        const accept = request.headers.get("accept");
        const contentType = request.headers.get("content-type");

        if (accept) {
            headers.set("Accept", accept);
        }

        const init: RequestInit = {
            method: request.method,
            headers,
            cache: "no-store",
        };

        if (request.method !== "GET" && request.method !== "HEAD") {
            if (contentType?.includes("multipart/form-data")) {
                init.body = await request.formData();
            } else {
                if (contentType) {
                    headers.set("Content-Type", contentType);
                }

                const body = await request.text();
                if (body) {
                    init.body = body;
                }
            }
        }

        const response = await fetch(targetUrl, init);
        return buildProxyResponse(response);
    } catch (error) {
        const message =
            error instanceof Error ? error.message : "Unexpected proxy error";
        return NextResponse.json({ error: message }, { status: 500 });
    }
}

function buildProxyResponse(response: Response) {
    if (response.status === 204) {
        return new NextResponse(null, { status: 204 });
    }

    const headers = new Headers();

    for (const headerName of [
        "content-type",
        "cache-control",
        "connection",
        "x-accel-buffering",
    ]) {
        const value = response.headers.get(headerName);
        if (value) {
            headers.set(headerName, value);
        }
    }

    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("text/event-stream")) {
        headers.set("Connection", headers.get("Connection") ?? "keep-alive");
        headers.set(
            "Cache-Control",
            headers.get("Cache-Control") ?? "no-cache",
        );
        headers.set(
            "X-Accel-Buffering",
            headers.get("X-Accel-Buffering") ?? "no",
        );
    }

    return new NextResponse(response.body, {
        status: response.status,
        headers,
    });
}
