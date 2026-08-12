import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PUBLIC_SEO_ROUTE_POLICY_CLASSIFICATION,
  PUBLIC_SEO_ROUTE_POLICY_ERROR_CODES,
  PUBLIC_SEO_ROUTE_POLICY_PAGE_CLASSES,
  PUBLIC_SEO_ROUTE_POLICY_SCREEN,
  createPublicSeoRoutePolicyCandidate,
} from '../../packages/web-ui/src/index.ts';

const HASH = 'a'.repeat(64);

function routeOnlyInput() {
  return {
    screenId: 'PUB-003' as const,
    route: '/articles/{slug}' as const,
    coordinate: {
      kind: 'SYNTHETIC_ST1005_SEO_ROUTE_FIXTURE' as const,
      expectedSha256: HASH,
      observedSha256: HASH,
    },
    origin: { mode: 'ROUTE_ONLY' as const, callerSuppliedOrigin: null },
  };
}

describe('ST-1005 disabled SEO route policy contract', () => {
  it('pins PUB-003 and the exact four local page classes without registering a route', () => {
    assert.equal(PUBLIC_SEO_ROUTE_POLICY_SCREEN.id, 'PUB-003');
    assert.equal(PUBLIC_SEO_ROUTE_POLICY_SCREEN.route, '/articles/{slug}');
    assert.deepEqual(PUBLIC_SEO_ROUTE_POLICY_PAGE_CLASSES, [
      'DRAFT',
      'PREVIEW',
      'FACET',
      'PUBLIC_ARTICLE',
    ]);
    const candidate = createPublicSeoRoutePolicyCandidate(routeOnlyInput());
    assert.equal(candidate.classification, PUBLIC_SEO_ROUTE_POLICY_CLASSIFICATION);
    assert.equal(candidate.route.routeRegistered, false);
    assert.equal(candidate.route.currentRoute, null);
    assert.equal(candidate.route.canonicalRoute, null);
  });

  it('fixes Draft and Facet to noindex and excludes all non-public classes from sitemap', () => {
    const policies = createPublicSeoRoutePolicyCandidate(routeOnlyInput()).pagePolicies;
    const draft = policies.find(({ pageClass }) => pageClass === 'DRAFT');
    const preview = policies.find(({ pageClass }) => pageClass === 'PREVIEW');
    const facet = policies.find(({ pageClass }) => pageClass === 'FACET');
    assert.deepEqual(draft?.requiredRobotsDirectives, ['noindex']);
    assert.equal(draft?.sitemapInclusionAllowed, false);
    assert.deepEqual(preview?.requiredRobotsDirectives, ['noindex', 'nofollow']);
    assert.equal(preview?.sitemapInclusionAllowed, false);
    assert.deepEqual(facet?.requiredRobotsDirectives, ['noindex']);
    assert.equal(facet?.sitemapInclusionAllowed, false);
    assert.ok(policies.every(({ runtimeApplied }) => runtimeApplied === false));
  });

  it('requires all seven canonical sitemap facts without treating them as evidence', () => {
    const sitemap = createPublicSeoRoutePolicyCandidate(routeOnlyInput()).sitemap;
    assert.deepEqual(sitemap.requiredEligibilityFacts, [
      'PUBLISHED',
      'HTTP_200',
      'INDEX_STATE_INDEX',
      'SELF_CANONICAL',
      'NOT_PAUSED',
      'NOT_REDIRECT_SOURCE',
      'CURRENT_PUBLICATION_SNAPSHOT',
    ]);
    assert.deepEqual(sitemap.inclusionEligibility, {
      state: 'NOT_EVALUATED',
      evidenceRef: null,
      verified: false,
    });
    assert.deepEqual(sitemap.entries, []);
  });

  it('keeps a unique closed error vocabulary and deeply frozen source metadata', () => {
    assert.equal(PUBLIC_SEO_ROUTE_POLICY_ERROR_CODES.length, 16);
    assert.equal(new Set(PUBLIC_SEO_ROUTE_POLICY_ERROR_CODES).size, 16);
    assert.ok(Object.isFrozen(PUBLIC_SEO_ROUTE_POLICY_SCREEN));
    assert.ok(Object.isFrozen(PUBLIC_SEO_ROUTE_POLICY_SCREEN.roles));
    assert.ok(Object.isFrozen(PUBLIC_SEO_ROUTE_POLICY_SCREEN.apiDependencies));
  });
});
