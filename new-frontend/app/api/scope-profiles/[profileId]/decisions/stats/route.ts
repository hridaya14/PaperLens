import { NextRequest } from "next/server";
import { proxyBackendRequest } from "@/lib/api/proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ profileId: string }> },
) {
  const { profileId } = await params;
  return proxyBackendRequest(request, `/scope-profiles/${profileId}/decisions/stats`);
}
