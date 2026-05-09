import { NextRequest } from "next/server";
import { proxyBackendRequest } from "@/lib/api/proxy";

export async function GET(request: NextRequest) {
  return proxyBackendRequest(request, "/chat/sessions");
}

export async function POST(request: NextRequest) {
  return proxyBackendRequest(request, "/chat/sessions");
}
