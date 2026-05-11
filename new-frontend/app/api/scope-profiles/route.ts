import { NextRequest } from "next/server";
import { proxyBackendRequest } from "@/lib/api/proxy";

export async function GET(request: NextRequest) {
  return proxyBackendRequest(request, "/scope-profiles");
}

export async function POST(request: NextRequest) {
  return proxyBackendRequest(request, "/scope-profiles");
}
