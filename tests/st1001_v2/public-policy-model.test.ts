import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PUBLIC_POLICY_PAGES,
  PUBLIC_POLICY_ROUTES,
  PUBLIC_POLICY_SCREEN_IDS,
  PublicPolicyError,
  createPublicPolicyMetadata,
  getPublicPolicyPage,
} from '../../apps/web/src/public-policy.ts';

function assertDeepFrozen(value: unknown, visited = new Set<object>()): void {
  if (typeof value !== 'object' || value === null || visited.has(value)) {
    return;
  }
  visited.add(value);
  assert.equal(Object.isFrozen(value), true);
  for (const child of Object.values(value)) {
    assertDeepFrozen(child, visited);
  }
}

describe('ST-1001 V2 public policy model', () => {
  it('binds exactly the four Canonical policy screens and routes', () => {
    assert.deepEqual(PUBLIC_POLICY_SCREEN_IDS, ['PUB-004', 'PUB-005', 'PUB-006', 'PUB-007']);
    assert.deepEqual(PUBLIC_POLICY_ROUTES, [
      '/editorial-policy',
      '/affiliate-disclosure',
      '/privacy',
      '/about',
    ]);
    assert.deepEqual(
      PUBLIC_POLICY_PAGES.map(({ screenId, route, title }) => ({ screenId, route, title })),
      [
        { screenId: 'PUB-004', route: '/editorial-policy', title: '編集方針' },
        { screenId: 'PUB-005', route: '/affiliate-disclosure', title: '広告・Affiliate開示' },
        { screenId: 'PUB-006', route: '/privacy', title: 'Privacy Policy' },
        { screenId: 'PUB-007', route: '/about', title: '運営者・問い合わせ' },
      ],
    );
    assert.equal(new Set(PUBLIC_POLICY_ROUTES).size, 4);
    assertDeepFrozen(PUBLIC_POLICY_PAGES);
  });

  it('keeps every page structured, text-only, and explicit about unresolved copy', () => {
    const allowedStates = new Set([
      'CANONICAL_PRINCIPLE',
      'SAFE_DEFAULT',
      'OWNER_DECISION_REQUIRED',
      'LEGAL_REVIEW_REQUIRED',
    ]);
    for (const page of PUBLIC_POLICY_PAGES) {
      assert.ok(page.sections.length >= 2);
      assert.equal(new Set(page.sections.map(({ id }) => id)).size, page.sections.length);
      for (const section of page.sections) {
        assert.match(section.id, /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/);
        assert.equal(allowedStates.has(section.state), true);
        assert.doesNotMatch(section.heading + section.body, /<[^>]*>|https?:\/\/|javascript:/i);
        assert.match(section.sourceRef, /^docs\/canonical\//);
      }
    }
    assert.equal(getPublicPolicyPage('PUB-006').sections[0]?.state, 'SAFE_DEFAULT');
    assert.equal(getPublicPolicyPage('PUB-005').sections.at(-1)?.state, 'LEGAL_REVIEW_REQUIRED');
    assert.ok(
      getPublicPolicyPage('PUB-007').sections.every(
        ({ state }) => state === 'OWNER_DECISION_REQUIRED',
      ),
    );
  });

  it('produces route-only noindex metadata without a canonical origin', () => {
    for (const screenId of PUBLIC_POLICY_SCREEN_IDS) {
      const page = getPublicPolicyPage(screenId);
      const metadata = createPublicPolicyMetadata(screenId);
      assert.equal(metadata.title, page.title);
      assert.equal(metadata.description, page.description);
      assert.equal(metadata.metadataBase, undefined);
      assert.equal(metadata.alternates, undefined);
      assert.equal(metadata.openGraph, undefined);
      assert.equal(metadata.twitter, undefined);
      assert.deepEqual(metadata.robots, {
        index: false,
        follow: false,
        noarchive: true,
        nosnippet: true,
        noimageindex: true,
        nocache: true,
        googleBot: {
          index: false,
          follow: false,
          noarchive: true,
          nosnippet: true,
          noimageindex: true,
        },
      });
    }
  });

  it('fails closed on an unknown screen without echoing input', () => {
    const canary = 'secret-policy-route-canary';
    assert.throws(
      () => getPublicPolicyPage(canary as never),
      (error: unknown) => {
        assert.ok(error instanceof PublicPolicyError);
        assert.equal(error.code, 'PUBLIC_POLICY_SCREEN_UNKNOWN');
        assert.equal(error.message, error.code);
        assert.doesNotMatch(error.message, new RegExp(canary));
        assert.equal(Object.isFrozen(error), true);
        return true;
      },
    );
  });
});
