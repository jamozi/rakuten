import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const source = readFileSync(
  resolve(repositoryRoot, 'packages/web-ui/src/public-event-instrumentation.ts'),
  'utf8',
);
const page = readFileSync(resolve(repositoryRoot, 'apps/web/src/public-article-page.tsx'), 'utf8');
const proxy = readFileSync(resolve(repositoryRoot, 'apps/web/proxy.ts'), 'utf8');
const marker = '\n// V2 is additive.';

describe('ST-1202 V2 static effect boundary', () => {
  it('preserves the complete V1 implementation bytes before the additive V2 marker', () => {
    const markerIndex = source.indexOf(marker);
    assert.ok(markerIndex > 0);
    const v1 = source.slice(0, markerIndex);
    assert.equal(
      createHash('sha256').update(v1).digest('hex'),
      '3d5e96e34383349dbc106d370e18c21a7c31c2a4fe795446a8932e981da0ff39',
    );
  });

  it('contains no browser collection, clock, random, network, storage, or credential call', () => {
    const v2 = source.slice(source.indexOf(marker));
    assert.doesNotMatch(v2, /\bnavigator\s*\.\s*sendBeacon\s*\(/);
    assert.doesNotMatch(v2, /\bfetch\s*\(/);
    assert.doesNotMatch(v2, /\bnew\s+PerformanceObserver\s*\(/);
    assert.doesNotMatch(v2, /\b(?:localStorage|sessionStorage|indexedDB)\s*\./);
    assert.doesNotMatch(v2, /\b(?:document\.cookie|Date\.now|Math\.random)\b/);
    assert.doesNotMatch(v2, /\b(?:process\.env|import\.meta\.env)\b/);
    assert.doesNotMatch(v2, /\b(?:XMLHttpRequest|WebSocket|EventSource)\b/);
    assert.doesNotMatch(v2, /from ['"](?:node:|react|react-dom|next)/);
  });

  it('integrates only a server-side disabled boundary into the exact no-script route', () => {
    assert.match(page, /createDisabledPublicEventInstrumentationRouteBoundaryV2\(/);
    assert.match(page, /articleId: null/);
    assert.match(page, /snapshotId: null/);
    assert.match(page, /state: disclosureAffiliate\.affiliateCta\.state/);
    assert.doesNotMatch(page, /['"]use client['"]/);
    assert.doesNotMatch(page, /\b(?:onClick|onLoad|onView|useEffect)\s*=/);
    assert.match(proxy, /connect-src 'none'/);
    assert.match(proxy, /script-src 'none'/);
  });

  it('exposes no event body, history, query, or persistence method', async () => {
    const runtimeModule = await import('../../packages/web-ui/src/public-event-instrumentation.ts');
    const fixture = JSON.parse(
      readFileSync(
        resolve(
          repositoryRoot,
          'changes/st-1202/generated/public-event-instrumentation-recorded.v2.json',
        ),
        'utf8',
      ),
    ).recordedFixture;
    const recorder = runtimeModule.createRecordedPublicEventInstrumentationV2(fixture);
    for (const name of [
      'body',
      'events',
      'history',
      'items',
      'query',
      'repository',
      'store',
      'persist',
    ]) {
      assert.equal(name in recorder, false);
    }
  });
});
