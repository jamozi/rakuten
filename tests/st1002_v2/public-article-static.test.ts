import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

function source(relative: string): string {
  return readFileSync(resolve(root, relative), 'utf8');
}

describe('ST-1002 V2 route and SSR surface', () => {
  it('registers one force-dynamic exact-slug article route with no client component', () => {
    const page = source('apps/web/app/articles/[slug]/page.tsx');
    assert.match(page, /export const dynamic = 'force-dynamic';/);
    assert.match(page, /resolveRecordedPublicArticleV2/);
    assert.match(page, /\?\? notFound\(\)/);
    assert.match(page, /index: false/);
    assert.match(page, /follow: false/);
    assert.doesNotMatch(page, /['"]use client['"]|generateStaticParams|redirect\(/);
  });

  it('uses semantic text-only server rendering with one authored H1', () => {
    const renderer = source('apps/web/src/public-article-page.tsx');
    assert.doesNotMatch(renderer, /['"]use client['"]|dangerouslySetInnerHTML|createPortal/);
    assert.doesNotMatch(
      renderer,
      /\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|localStorage|sessionStorage|document\.cookie)\b/,
    );
    assert.doesNotMatch(renderer, /<img\b|<table\b|<form\b|<script\b|<iframe\b/);
    for (const tag of ['header', 'nav', 'main', 'article', 'aside', 'section', 'footer']) {
      assert.match(renderer, new RegExp(`<${tag}\\b`));
    }
    assert.equal((renderer.match(/<h1\b/g) ?? []).length, 1);
    assert.match(renderer, /href="#public-article-main"/);
    assert.match(renderer, /aria-current="page"/);
    assert.match(renderer, /tabIndex=\{-1\}/);
  });

  it('applies closed local-preview headers through the article-only proxy matcher', () => {
    const proxy = source('apps/web/proxy.ts');
    assert.match(proxy, /matcher: \['\/articles\/:path\*'\]/);
    for (const header of [
      'Cache-Control',
      'Content-Security-Policy',
      'Cross-Origin-Opener-Policy',
      'Cross-Origin-Resource-Policy',
      'Permissions-Policy',
      'Referrer-Policy',
      'X-Content-Type-Options',
      'X-Frame-Options',
      'X-Robots-Tag',
    ]) {
      assert.match(proxy, new RegExp(`key: '${header}'`));
    }
    assert.match(proxy, /script-src 'none'/);
    assert.match(proxy, /connect-src 'none'/);
    assert.match(proxy, /frame-ancestors 'none'/);
    assert.match(proxy, /value: 'DENY'/);
    assert.match(proxy, /value: 'nosniff'/);
    assert.match(proxy, /value: 'no-referrer'/);
    assert.match(proxy, /value: 'noindex, nofollow/);
    assert.match(proxy, /private, no-store/);
  });

  it('has no API, database, provider, tracking, cookie or publication call surface', () => {
    const combined = [
      source('packages/web-ui/src/public-article-renderer.ts'),
      source('packages/web-ui/src/public-article-recorded.v2.ts'),
      source('apps/web/src/public-article-page.tsx'),
      source('apps/web/app/articles/[slug]/page.tsx'),
      source('apps/web/proxy.ts'),
    ].join('\n');
    assert.doesNotMatch(combined, /process\.env|import\.meta\.env|Date\.now|Math\.random/);
    assert.doesNotMatch(combined, /\b(?:fetch|axios|XMLHttpRequest|WebSocket|EventSource)\s*\(/);
    assert.doesNotMatch(combined, /\b(?:cookies|headers|draftMode|revalidatePath)\s*\(/);
    assert.doesNotMatch(combined, /@raos\/(?:admin|finance|evidence)|openai|@aws-sdk/i);
  });
});
