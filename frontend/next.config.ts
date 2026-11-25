import type { NextConfig } from "next";

// When hosted (Vercel), the browser calls /api/v1/* on the site itself and Next forwards it to
// the backend at BACKEND_ORIGIN (e.g. https://mira-backend.onrender.com). Same origin, so the
// staff sign-in cookie is first-party and no CORS is needed. Locally BACKEND_ORIGIN is unset and
// the browser calls NEXT_PUBLIC_API_URL (http://localhost:8000/api/v1) directly, as before.
const backend = process.env.BACKEND_ORIGIN?.replace(/\/+$/, "");

const nextConfig: NextConfig = {
  // No round "N" badge in the corner while developing (it never appears in a production build).
  devIndicators: false,
  async rewrites() {
    return backend ? [{ source: "/api/v1/:path*", destination: `${backend}/api/v1/:path*` }] : [];
  },
};

export default nextConfig;
