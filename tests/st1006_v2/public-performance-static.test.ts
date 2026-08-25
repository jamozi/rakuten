import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

function source(relative: string): string {
  return readFileSync(resolve(root, relative), 'utf8');
}

describe('ST-1006 V2 static side-effect and dependency boundaries', () => {
  it('adds no browser observer, transport, network, storage, cookie or client runtime', () => {
    const runtime = source('packages/web-ui/src/public-performance-runtime-v2.ts');
    assert.deepEqual(
      [...runtime.matchAll(/^import .* from ['"]([^'"]+)['"];$/gmu)].map((match) => match[1]),
      ['./serializable.ts'],
    );
    assert.doesNotMatch(
      runtime,
      /\b(?:PerformanceObserver|sendBeacon|fetch|XMLHttpRequest|WebSocket|EventSource)\s*\(/u,
    );
    assert.doesNotMatch(
      runtime,
      /\b(?:document\.cookie|localStorage|sessionStorage|indexedDB|process\.env|Date\.now|Math\.random)\b/u,
    );
    assert.doesNotMatch(runtime, /['"]use client['"]|from ['"](?:react|next)/u);
    assert.doesNotMatch(runtime, /https?:\/\//u);
  });

  it('does not modify the inherited route to render images or an affiliate CTA', () => {
    const page = source('apps/web/src/public-article-page.tsx');
    const route = source('apps/web/app/articles/[slug]/page.tsx');
    assert.doesNotMatch(page, /<img\b|<Image\b/u);
    assert.doesNotMatch(
      page.slice(page.indexOf('export function PublicArticlePage')),
      /<AffiliateCTA\b/u,
    );
    assert.doesNotMatch(route, /public-performance-runtime-v2|PerformanceObserver/u);
  });

  it('keeps real/formal performance states explicitly NOT_EXECUTED', () => {
    const completion = source('changes/st-1006/completion/completion.v2.yaml');
    const readme = source('changes/st-1006/README-v2.md');
    assert.match(completion, /real_measurements_claimed: false/u);
    assert.match(completion, /formal TST-027/u);
    assert.match(readme, /RECORDED_SYNTHETIC_ONLY/u);
    assert.match(readme, /not a browser lab run/u);
    assert.match(readme, /OD-012/u);
  });
});
