import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { createPublicSeoRoutePolicyCandidate } from '../../packages/web-ui/src/seo-route-policy.ts';

const HASH = 'f'.repeat(64);

function candidate() {
  return createPublicSeoRoutePolicyCandidate({
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: {
      kind: 'SYNTHETIC_ST1005_SEO_ROUTE_FIXTURE',
      expectedSha256: HASH,
      observedSha256: HASH,
    },
    origin: { mode: 'ROUTE_ONLY', callerSuppliedOrigin: null },
  });
}

describe('ST-1005 protected boundaries', () => {
  it('keeps every runtime, data, browser, formal, and authorization boundary closed', () => {
    const value = candidate();
    for (const boundary of Object.values(value.boundaries)) {
      assert.deepEqual(
        { value: boundary.value, status: boundary.status },
        { value: false, status: 'NOT_EXECUTED' },
      );
      assert.ok(boundary.reason.length > 0);
    }
    assert.deepEqual(value.authorization, {
      approval: false,
      publication: false,
      release: false,
      production: false,
      formalEvidence: false,
    });
    assert.deepEqual(value.actions, []);
  });

  it('emits no sitemap, robots, canonical URL, current route, or publication claim', () => {
    const value = candidate();
    assert.deepEqual(value.sitemap.entries, []);
    assert.equal(value.sitemap.serializedDocument, null);
    assert.equal(value.sitemap.lastmod, null);
    assert.equal(value.sitemap.generated, false);
    assert.equal(value.sitemap.published, false);
    assert.equal(value.robots.serializedDocument, null);
    assert.equal(value.robots.runtimeApplied, false);
    assert.equal(value.canonical.absoluteCanonicalUrl, null);
    assert.equal(value.canonical.activated, false);
    assert.equal(value.route.currentRoute, null);
    assert.equal(value.externalAssessments.currentPublication.state, 'NOT_EVALUATED');
  });

  it('contains no executable callback or mutable effect surface', () => {
    const value = candidate();
    assert.equal(
      JSON.stringify(value).includes('https://'),
      false,
      'route-only candidate must not invent or expose an origin',
    );
    const functions: string[] = [];
    const visit = (item: unknown): void => {
      if (typeof item === 'function') functions.push('function');
      if (item !== null && typeof item === 'object') {
        for (const child of Object.values(item)) visit(child);
      }
    };
    visit(value);
    assert.deepEqual(functions, []);
  });
});
