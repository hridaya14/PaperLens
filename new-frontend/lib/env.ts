const DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1";

export function getApiBaseUrl() {
  return (process.env.PAPERLENS_API_BASE_URL ?? DEFAULT_API_BASE_URL).replace(/\/+$/, "");
}
