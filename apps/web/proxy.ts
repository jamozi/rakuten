import { NextResponse } from 'next/server';

export const PUBLIC_ARTICLE_LOCAL_PREVIEW_HEADERS = Object.freeze([
  { key: 'Cache-Control', value: 'private, no-store, max-age=0, must-revalidate' },
  {
    key: 'Content-Security-Policy',
    value:
      "default-src 'none'; base-uri 'none'; connect-src 'none'; font-src 'self'; form-action 'none'; frame-ancestors 'none'; img-src 'none'; manifest-src 'none'; media-src 'none'; object-src 'none'; script-src 'none'; style-src 'self'",
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

export function proxy() {
  const response = NextResponse.next();
  for (const { key, value } of PUBLIC_ARTICLE_LOCAL_PREVIEW_HEADERS) {
    response.headers.set(key, value);
  }
  return response;
}

export const config = {
  matcher: ['/articles/:path*'],
};
