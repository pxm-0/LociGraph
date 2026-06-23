/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_ORIGIN || "http://localhost:8000"
const nextConfig = {
  output: "standalone",
  async rewrites() {
    // Dev only: in prod, Caddy proxies /api/* → backend and this app is served as static/standalone.
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }]
  },
}
export default nextConfig
