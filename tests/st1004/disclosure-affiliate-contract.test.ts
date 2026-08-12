import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PUBLIC_DISCLOSURE_AFFILIATE_CLASSIFICATION,
  PUBLIC_DISCLOSURE_AFFILIATE_COMPONENT_IDS,
  PUBLIC_DISCLOSURE_AFFILIATE_COMPONENTS,
  PUBLIC_DISCLOSURE_AFFILIATE_ERROR_CODES,
  PUBLIC_DISCLOSURE_AFFILIATE_SCREEN,
  createPublicDisclosureAffiliateCandidate,
} from '../../packages/web-ui/src/index.ts';

const HASH = 'a'.repeat(64);

describe('ST-1004 disabled disclosure and affiliate contract', () => {
  it('pins exactly the canonical DisclosureBanner and AffiliateCTA metadata', () => {
    assert.deepEqual(PUBLIC_DISCLOSURE_AFFILIATE_COMPONENT_IDS, ['UI-C031', 'UI-C034']);
    assert.deepEqual(
      PUBLIC_DISCLOSURE_AFFILIATE_COMPONENTS.map(({ id, name, purpose }) => ({
        id,
        name,
        purpose,
      })),
      [
        { id: 'UI-C031', name: 'DisclosureBanner', purpose: '広告・Affiliate開示' },
        {
          id: 'UI-C034',
          name: 'AffiliateCTA',
          purpose: '楽天遷移を明示しSponsored属性',
        },
      ],
    );
    assert.ok(
      PUBLIC_DISCLOSURE_AFFILIATE_COMPONENTS.every(
        (component) => component.keyboardRequired && component.screenReaderRequired,
      ),
    );
  });

  it('pins PUB-003 while leaving the route unregistered and inert', () => {
    assert.equal(PUBLIC_DISCLOSURE_AFFILIATE_SCREEN.id, 'PUB-003');
    assert.equal(PUBLIC_DISCLOSURE_AFFILIATE_SCREEN.route, '/articles/{slug}');
    const candidate = createPublicDisclosureAffiliateCandidate({
      screenId: 'PUB-003',
      route: '/articles/{slug}',
      coordinate: {
        kind: 'SYNTHETIC_ST1004_SEMANTIC_FIXTURE',
        expectedSha256: HASH,
        observedSha256: HASH,
      },
    });
    assert.equal(candidate.classification, PUBLIC_DISCLOSURE_AFFILIATE_CLASSIFICATION);
    assert.equal(candidate.route.routeRegistered, false);
    assert.equal(candidate.route.interactive, false);
    assert.equal(candidate.route.focusable, false);
  });

  it('deep-freezes exported screen and component metadata', () => {
    assert.ok(Object.isFrozen(PUBLIC_DISCLOSURE_AFFILIATE_SCREEN));
    assert.ok(Object.isFrozen(PUBLIC_DISCLOSURE_AFFILIATE_SCREEN.roles));
    assert.ok(Object.isFrozen(PUBLIC_DISCLOSURE_AFFILIATE_SCREEN.apiDependencies));
    assert.ok(Object.isFrozen(PUBLIC_DISCLOSURE_AFFILIATE_COMPONENTS));
    assert.ok(Object.isFrozen(PUBLIC_DISCLOSURE_AFFILIATE_COMPONENTS[0]));
    assert.throws(() => {
      (PUBLIC_DISCLOSURE_AFFILIATE_SCREEN.roles as unknown as string[]).push('admin');
    }, TypeError);
    assert.throws(() => {
      (PUBLIC_DISCLOSURE_AFFILIATE_COMPONENTS as unknown as unknown[]).push('CTA');
    }, TypeError);
  });

  it('keeps a stable closed error vocabulary', () => {
    assert.equal(PUBLIC_DISCLOSURE_AFFILIATE_ERROR_CODES.length, 15);
    assert.equal(new Set(PUBLIC_DISCLOSURE_AFFILIATE_ERROR_CODES).size, 15);
  });
});
