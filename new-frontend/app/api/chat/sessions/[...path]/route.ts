import { NextRequest } from "next/server";
import { proxyBackendRequest } from "@/lib/api/proxy";

async function resolvePath(params: Promise<{ path: string[] }>) {
  const { path } = await params;
  return path.join("/");
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const path = await resolvePath(context.params);
  return proxyBackendRequest(request, `/chat/sessions/${path}`);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const path = await resolvePath(context.params);
  return proxyBackendRequest(request, `/chat/sessions/${path}`);
}

export async function PATCH(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const path = await resolvePath(context.params);
  return proxyBackendRequest(request, `/chat/sessions/${path}`);
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const path = await resolvePath(context.params);
  return proxyBackendRequest(request, `/chat/sessions/${path}`);
}
