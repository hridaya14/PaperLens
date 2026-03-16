import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
const nextConfig = {
  typedRoutes: true,
  output: "standalone",
  outputFileTracingRoot: fileURLToPath(new URL(".", import.meta.url))
};

export default nextConfig;
