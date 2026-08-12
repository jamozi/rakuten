import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  createPublicDisclosureAffiliateCandidate,
  validatePublicDisclosureAffiliateCandidate,
} from '../../packages/web-ui/src/disclosure-affiliate-cta.ts';

const HASH = '0123456789abcdef'.repeat(4);

function input() {
  return {
    screenId: 'PUB-003' as const,
    route: '/articles/{slug}' as const,
    coordinate: {
      kind: 'SYNTHETIC_ST1004_SEMANTIC_FIXTURE' as const,
      expectedSha256: HASH,
      observedSha256: HASH,
    },
  };
}

function assertDeepFrozen(value: unknown, visited = new Set<object>()): void {
  if (value === null || typeof value !== 'object' || visited.has(value)) return;
  visited.add(value);
  assert.ok(Object.isFrozen(value));
  for (const child of Object.values(value)) assertDeepFrozen(child, visited);
}

describe('ST-1004 headless semantic model', () => {
  it('is deterministic, detached, JSON-safe, and deeply frozen', () => {
    const source = input();
    const first = createPublicDisclosureAffiliateCandidate(source);
    const second = createPublicDisclosureAffiliateCandidate(source);
    assert.deepEqual(first, second);
    assert.notEqual(first, second);
    assert.notEqual(first.coordinate, source.coordinate);
    assert.deepEqual(
      validatePublicDisclosureAffiliateCandidate(JSON.parse(JSON.stringify(first))),
      first,
    );
    assertDeepFrozen(first);
  });

  it('keeps disclosure renderer-owned and topmost without inventing copy or policy truth', () => {
    const disclosure = createPublicDisclosureAffiliateCandidate(input()).semantics.disclosure;
    assert.equal(disclosure.rendererOwned, true);
    assert.equal(disclosure.editorRemovable, false);
    assert.equal(disclosure.placementRequirement, 'ARTICLE_TOP_FIRST_VIEWPORT');
    assert.equal(disclosure.disclosurePolicyVersionRef, null);
    assert.equal(disclosure.articleDisclosureContextRef, null);
    assert.equal(disclosure.renderedCopy, null);
    assert.deepEqual(disclosure.policyCurrentness, {
      status: 'NOT_EVALUATED',
      evidenceRef: null,
      verified: false,
    });
  });

  it('declares link requirements while keeping the CTA disabled and valueless', () => {
    const cta = createPublicDisclosureAffiliateCandidate(input()).semantics.affiliateCta;
    assert.equal(cta.renderable, false);
    assert.equal(cta.interactive, false);
    assert.equal(cta.enabled, false);
    assert.equal(cta.affiliateUrl, null);
    assert.equal(cta.destinationHost, null);
    assert.equal(cta.renderedDestinationLabel, null);
    assert.deepEqual(cta.destinationRequirement, {
      marketplace: 'RAKUTEN_MARKETPLACE',
      mustBeClearBeforeActivation: true,
      verified: false,
    });
    assert.deepEqual(cta.relationRequirement, {
      requiredContractValue: 'sponsored nofollow',
      renderedAttribute: null,
      verified: false,
    });
    assert.deepEqual(cta.navigationRequirement, {
      directProviderUrlRequired: true,
      raosRedirectAllowed: false,
      cloakingAllowed: false,
      urlModificationAllowed: false,
    });
  });

  it('makes API credit applicability and beacon independence explicit without effects', () => {
    const semantics = createPublicDisclosureAffiliateCandidate(input()).semantics;
    assert.equal(semantics.apiCredit.renderable, false);
    assert.equal(semantics.apiCredit.providerDataUsage, 'NOT_EVALUATED');
    assert.equal(semantics.apiCredit.requiredWhenProviderDataUsed, true);
    assert.equal(semantics.apiCredit.policySourceRef, null);
    assert.equal(semantics.apiCredit.renderedCopy, null);
    assert.equal(semantics.beaconIndependence.navigationMustNotDependOnBeacon, true);
    assert.equal(semantics.beaconIndependence.beaconConfigured, false);
    assert.equal(semantics.beaconIndependence.beaconExecuted, false);
    assert.equal(semantics.beaconIndependence.navigationExecuted, false);
    assert.equal(semantics.beaconIndependence.browserVerified, false);
  });

  it('keeps restrained semantic ordering without selecting a layout', () => {
    const composition = createPublicDisclosureAffiliateCandidate(input()).composition;
    assert.equal(composition.disclosureMustPrecedeAffiliateCta, true);
    assert.equal(composition.disclosureAndCtaMustRemainSemanticallySeparate, true);
    assert.equal(composition.ctaMustNotDominateEditorialEvidence, true);
    assert.equal(composition.selectedLayout, null);
    assert.equal(composition.domStatus, 'DOM_NOT_IMPLEMENTED');
  });
});
