import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import nextConfig, {
  PUBLIC_POLICY_RESPONSE_HEADERS,
  PUBLIC_POLICY_ROUTE_SOURCES,
} from '../../apps/web/next.config.ts';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

function source(relative: string): string {
  return readFileSync(resolve(root, relative), 'utf8');
}

describe('ST-1001 V2 route and security surface', () => {
  it('generates Next route declarations before a clean-checkout typecheck', () => {
    const manifest = JSON.parse(source('apps/web/package.json')) as {
      scripts?: Record<string, unknown>;
    };
    assert.equal(
      manifest.scripts?.typecheck,
      'next typegen && tsc --noEmit --project tsconfig.json',
    );
    assert.equal(
      manifest.scripts?.lint,
      'eslint --max-warnings=0 --no-warn-ignored app src next.config.ts next-env.d.ts ../../tests/st1001_v2 ../../scripts/check_st1001_public_shell_browser.mjs',
    );
  });

  it('registers every policy route as a force-dynamic server component', () => {
    const pages = [
      ['editorial-policy', 'PUB-004'],
      ['affiliate-disclosure', 'PUB-005'],
      ['privacy', 'PUB-006'],
      ['about', 'PUB-007'],
    ] as const;
    for (const [route, screenId] of pages) {
      const value = source(`apps/web/app/${route}/page.tsx`);
      assert.match(value, /export const dynamic = 'force-dynamic';/);
      assert.match(value, new RegExp(`createPublicPolicyMetadata\\('${screenId}'\\)`));
      assert.match(value, new RegExp(`screenId="${screenId}"`));
      assert.doesNotMatch(value, /['"]use client['"]/);
    }
  });

  it('keeps the shared renderer semantic, no-client, and text-only', () => {
    const renderer = source('apps/web/src/public-shell.tsx');
    assert.doesNotMatch(renderer, /['"]use client['"]|dangerouslySetInnerHTML|createPortal/);
    assert.doesNotMatch(
      renderer,
      /\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|localStorage|sessionStorage|document\.cookie)\b/,
    );
    assert.doesNotMatch(renderer, /https?:\/\/|mailto:|tel:|<script|iframe/i);
    for (const tag of ['header', 'nav', 'main', 'article', 'aside', 'section', 'footer']) {
      assert.match(renderer, new RegExp(`<${tag}\\b`));
    }
    assert.equal((renderer.match(/<h1\b/g) ?? []).length, 1);
    assert.match(renderer, /className="skip-link" href="#public-shell-main"/);
    assert.match(renderer, /aria-current=/);
    assert.match(renderer, /tabIndex=\{-1\}/);
  });

  it('applies exact local-preview headers to only the four Story routes', async () => {
    assert.deepEqual(PUBLIC_POLICY_ROUTE_SOURCES, [
      '/editorial-policy',
      '/affiliate-disclosure',
      '/privacy',
      '/about',
    ]);
    assert.equal(typeof nextConfig.headers, 'function');
    const records = await nextConfig.headers?.();
    assert.deepEqual(
      records?.map(({ source: route }) => route),
      PUBLIC_POLICY_ROUTE_SOURCES,
    );
    assert.equal(new Set(PUBLIC_POLICY_RESPONSE_HEADERS.map(({ key }) => key)).size, 9);
    const headers = Object.fromEntries(
      PUBLIC_POLICY_RESPONSE_HEADERS.map(({ key, value }) => [key.toLowerCase(), value]),
    );
    assert.match(headers['content-security-policy'] ?? '', /script-src 'none'/);
    assert.match(headers['content-security-policy'] ?? '', /frame-ancestors 'none'/);
    assert.equal(headers['referrer-policy'], 'no-referrer');
    assert.equal(headers['x-frame-options'], 'DENY');
    assert.equal(headers['x-content-type-options'], 'nosniff');
    assert.equal(headers['cross-origin-opener-policy'], 'same-origin');
    assert.match(headers['permissions-policy'] ?? '', /payment=\(\)/);
    assert.match(headers['x-robots-tag'] ?? '', /^noindex, nofollow/);
    assert.equal(nextConfig.poweredByHeader, false);
  });

  it('contains no provider, origin, identity, tracking, redirect, or publication surface', () => {
    const combined = [
      source('apps/web/src/public-policy.ts'),
      source('apps/web/src/public-policy-content.generated.ts'),
      source('apps/web/src/public-shell.tsx'),
      source('apps/web/next.config.ts'),
    ].join('\n');
    assert.doesNotMatch(combined, /example\.invalid|changes\/st-1701|siteKit|gtag|dataLayer/i);
    assert.doesNotMatch(combined, /\b(?:redirect|revalidatePath|cookies)\s*\(/);
    assert.doesNotMatch(combined, /process\.env|import\.meta\.env|Date\.now|Math\.random/);
    assert.doesNotMatch(combined, /@raos\/(?:admin|finance|evidence)|rawPrompt|sourcePacket/);
  });
});
