import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  createPublicComparisonComponentsCandidate,
  validatePublicComparisonComponentsCandidate,
} from '../../packages/web-ui/src/comparison-product-components.ts';

const HASH = '0123456789abcdef'.repeat(4);

function input() {
  return {
    screenId: 'PUB-003' as const,
    route: '/articles/{slug}' as const,
    coordinate: {
      kind: 'SYNTHETIC_ST1003_SEMANTIC_FIXTURE' as const,
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

describe('ST-1003 headless semantic model', () => {
  it('is deterministic, detached, JSON-safe, and deeply frozen', () => {
    const source = input();
    const first = createPublicComparisonComponentsCandidate(source);
    const second = createPublicComparisonComponentsCandidate(source);
    assert.deepEqual(first, second);
    assert.notEqual(first, second);
    assert.notEqual(first.coordinate, source.coordinate);
    assert.deepEqual(
      validatePublicComparisonComponentsCandidate(JSON.parse(JSON.stringify(first))),
      first,
    );
    assertDeepFrozen(first);
  });

  it('declares association requirements without selecting or claiming DOM', () => {
    const table = createPublicComparisonComponentsCandidate(input()).semantics.comparisonTable;
    assert.deepEqual(table.caption, { required: true, renderedCopy: null });
    assert.equal(table.headerAssociation.captionHeadersAndScopeRequired, true);
    assert.equal(table.headerAssociation.domStatus, 'DOM_NOT_IMPLEMENTED');
    assert.equal(table.headerAssociation.verificationStatus, 'NOT_VERIFIED');
    assert.equal(table.mobileRelationship.productAndAxisRelationshipMustBePreserved, true);
    assert.equal(table.mobileRelationship.selectedPresentation, null);
    assert.equal(table.mobileRelationship.layoutDecisionStatus, 'UNAVAILABLE');
  });

  it('keeps Unknown visible and non-imputed with no value or copy', () => {
    const unknown = createPublicComparisonComponentsCandidate(input()).semantics.unknownValue;
    assert.equal(unknown.visibilityRequirement, 'MUST_REMAIN_VISIBLE_WHEN_RENDERED');
    assert.equal(unknown.imputationAllowed, false);
    assert.equal(unknown.zeroSubstitutionAllowed, false);
    assert.equal(unknown.emptyStringSubstitutionAllowed, false);
    assert.equal(unknown.value, null);
    assert.equal(unknown.renderedCopy, null);
  });

  it('keeps product and tradeoff payloads unavailable', () => {
    const semantics = createPublicComparisonComponentsCandidate(input()).semantics;
    assert.equal(semantics.productCard.productIdentityRef, null);
    assert.equal(semantics.productCard.productName.value, null);
    assert.equal(semantics.productCard.verifiedFacts.value, null);
    assert.deepEqual(semantics.productCard.image, {
      available: false,
      source: null,
      alternativeText: null,
    });
    assert.equal(semantics.productCard.price.value, null);
    assert.equal(semantics.productCard.offers.value, null);
    assert.equal(semantics.productCard.affiliateCta.value, null);
    assert.equal(semantics.tradeoff.catalogComponentId, null);
    assert.equal(semantics.tradeoff.subjectRef, null);
    assert.deepEqual(semantics.tradeoff.slots, {
      benefit: { available: false, renderedCopy: null },
      costOrLimitation: { available: false, renderedCopy: null },
      appliesWhen: { available: false, renderedCopy: null },
    });
  });
});
