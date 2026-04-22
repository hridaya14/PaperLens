import { NextRequest, NextResponse } from "next/server";
import { openChatStream } from "@/lib/api/backend";

export async function POST(request: NextRequest) {
    try {
        const payload = await request.json();
        const response = await openChatStream(payload);

        return new NextResponse(response.body, {
            status: 200,
            headers: {
                "Content-Type": "text/event-stream; charset=utf-8",
                "Cache-Control": "no-cache, no-transform",
                Connection: "keep-alive",
                "X-Accel-Buffering": "no",
            },
        });
    } catch (error) {
        const message =
            error instanceof Error ? error.message : "Unexpected proxy error";
        return NextResponse.json({ error: message }, { status: 500 });
    }
}
