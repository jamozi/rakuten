import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  createPublicSeoRoutePolicyCandidate,
  validatePublicSeoRoutePolicyCandidate,
} from '../../packages/web-ui/src/seo-route-policy.ts';

const HASH = '0123456789abcdef'.repeat(4);

function input(mode: 'ROUTE_ONLY' | 'CALLER_SUPPLIED_ORIGIN' = 'ROUTE_ONLY') {
  return {
    screenId: 'PUB-003' as const,
    route: '/articles/{slug}' as const,
    coordinate: {
      kind: 'SYNTHETIC_ST1005_SEO_ROUTE_FIXTURE' as const,
      expectedSha256: HASH,
      observedSha256: HASH,
    },
    origin:
      mode === 'ROUTE_ONLY'
        ? { mode, callerSuppliedOrigin: null }
        : { mode, callerSuppliedOrigin: 'https://preview.example.invalid/' },
  };
}

function assertDeepFrozen(value: unknown, visited = new Set<object>()): void {
  if (value === null || typeof value !== 'object' || visited.has(value)) return;
  visited.add(value);
  assert.ok(Object.isFrozen(value));
  for (const child of Object.values(value)) assertDeepFrozen(child, visited);
}

describe('ST-1005 headless SEO route policy model', () => {
  it('is deterministic, detached, JSON-safe, and deeply frozen', () => {
    const source = input();
    const first = createPublicSeoRoutePolicyCandidate(source);
    const second = createPublicSeoRoutePolicyCandidate(source);
    assert.deepEqual(first, second);
    assert.notEqual(first, second);
    assert.notEqual(first.coordinate, source.coordinate);
    assert.deepEqual(
      validatePublicSeoRoutePolicyCandidate(JSON.parse(JSON.stringify(first))),
      first,
    );
    assertDeepFrozen(first);
  });

  it('keeps route-only mode originless and absolute canonical unavailable', () => {
    const candidate = createPublicSeoRoutePolicyCandidate(input());
    assert.deepEqual(candidate.origin, {
      mode: 'ROUTE_ONLY',
      source: 'NONE',
      callerSuppliedOrigin: null,
      acceptedOnlyAsUnapprovedInput: false,
      domainApproved: false,
      productionDomainSelected: false,
      absoluteUrlRenderingAllowed: false,
    });
    assert.equal(candidate.canonical.absoluteCanonicalUrl, null);
    assert.ok(candidate.eligibilityReasons.includes('ROUTE_ONLY_ORIGIN_UNAVAILABLE'));
  });

  it('normalizes caller origin only as unapproved data and never activates a URL', () => {
    const candidate = createPublicSeoRoutePolicyCandidate(input('CALLER_SUPPLIED_ORIGIN'));
    assert.equal(candidate.origin.mode, 'CALLER_SUPPLIED_ORIGIN');
    assert.equal(candidate.origin.source, 'CALLER_SUPPLIED_UNAPPROVED');
    assert.equal(candidate.origin.callerSuppliedOrigin, 'https://preview.example.invalid');
    assert.equal(candidate.origin.acceptedOnlyAsUnapprovedInput, true);
    assert.equal(candidate.origin.domainApproved, false);
    assert.equal(candidate.origin.productionDomainSelected, false);
    assert.equal(candidate.origin.absoluteUrlRenderingAllowed, false);
    assert.equal(candidate.canonical.absoluteCanonicalUrl, null);
    assert.ok(candidate.eligibilityReasons.includes('CALLER_ORIGIN_UNAPPROVED'));
  });

  it('keeps public article index, canonical, and sitemap truth not evaluated', () => {
    const candidate = createPublicSeoRoutePolicyCandidate(input());
    const article = candidate.pagePolicies.find(({ pageClass }) => pageClass === 'PUBLIC_ARTICLE');
    assert.equal(article?.state, 'NOT_EVALUATED');
    assert.equal(article?.requiredIndexState, null);
    assert.equal(article?.sitemapInclusionAllowed, null);
    assert.equal(candidate.canonical.uniqueness.state, 'NOT_EVALUATED');
    assert.equal(candidate.canonical.graphAcyclic.state, 'NOT_EVALUATED');
    assert.equal(candidate.conditionalLocalEligibility, false);
  });
});
