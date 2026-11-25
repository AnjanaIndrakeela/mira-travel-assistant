import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // No round "N" badge in the corner while developing (it never appears in a production build).
  devIndicators: false,
};

export default nextConfig;
