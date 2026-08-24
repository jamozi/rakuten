import path from 'node:path';
import { fileURLToPath } from 'node:url';

import type { NextConfig } from 'next';

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

export const PUBLIC_POLICY_ROUTE_SOURCES = Object.freeze([
  '/editorial-policy',
  '/affiliate-disclosure',
  '/privacy',
  '/about',
] as const);

export const PUBLIC_POLICY_RESPONSE_HEADERS = Object.freeze([
  {
    key: 'Cache-Control',
    value: 'private, no-store, max-age=0, must-revalidate',
  },
  {
    key: 'Content-Security-Policy',
    value:
      "default-src 'none'; base-uri 'none'; connect-src 'self'; font-src 'self'; form-action 'none'; frame-ancestors 'none'; img-src 'self' data:; manifest-src 'self'; media-src 'none'; object-src 'none'; script-src 'none'; style-src 'self'",
  },
  { key: 'Cross-Origin-Opener-Policy', value: 'same-origin' },
  { key: 'Cross-Origin-Resource-Policy', value: 'same-origin' },
  {
    key: 'Permissions-Policy',
    value: 'camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()',
  },
  { key: 'Referrer-Policy', value: 'no-referrer' },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'X-Frame-Options', value: 'DENY' },
  {
    key: 'X-Robots-Tag',
    value: 'noindex, nofollow, noarchive, nosnippet, noimageindex',
  },
] as const);

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  outputFileTracingRoot: repositoryRoot,
  turbopack: {
    root: repositoryRoot,
  },
  async headers() {
    return PUBLIC_POLICY_ROUTE_SOURCES.map((source) => ({
      source,
      headers: PUBLIC_POLICY_RESPONSE_HEADERS.map((header) => ({ ...header })),
    }));
  },
};

export default nextConfig;
