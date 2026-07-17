/** @type {import('next').NextConfig} */
const nextConfig = {
  // Rewrites so the browser only ever talks to `web`'s own origin — the
  // proxy-in-front-of-api pattern from overview.md §3.2, done here at the
  // Next.js layer instead of a separate Caddy container for local dev.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_INTERNAL_URL ?? "http://api:8000"}/:path*`,
      },
    ];
  },
  // react-pdf's underlying pdfjs-dist has an optional `require("canvas")`
  // path (server-side PDF rendering, which this project never uses — the
  // PDF viewer is a client-only component). Without this, webpack tries
  // to resolve that module and fails the build since `canvas` isn't
  // installed (it needs native bindings we have no use for here).
  webpack: (config) => {
    config.resolve.alias.canvas = false;
    return config;
  },
};

export default nextConfig;
