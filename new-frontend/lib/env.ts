import "server-only";

export function getApiBaseUrl() {
  return process.env.PAPERLENS_API_BASE_URL ?? "http://localhost:8000/api/v1";
}
