import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import { createPublicDisclosureAffiliateCandidate } from '../../packages/web-ui/src/disclosure-affiliate-cta.ts';

const HASH = 'b'.repeat(64);

function candidate() {
  return createPublicDisclosureAffiliateCandidate({
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: {
      kind: 'SYNTHETIC_ST1004_SEMANTIC_FIXTURE',
      expectedSha256: HASH,
      observedSha256: HASH,
    },
  });
}

describe('ST-1004 safety boundaries', () => {
  it('keeps every runtime, formal, and authority boundary false', () => {
    const value = candidate();
    for (const boundary of Object.values(value.boundaries)) {
      assert.equal(boundary.value, false);
      assert.equal(boundary.status, 'NOT_EXECUTED');
    }
    assert.deepEqual(value.actions, []);
  });

  it('contains no executable link, disclosure copy, reference, or policy evidence', () => {
    const value = candidate();
    assert.equal(value.semantics.disclosure.renderedCopy, null);
    assert.equal(value.semantics.disclosure.disclosurePolicyVersionRef, null);
    assert.equal(value.semantics.affiliateCta.offerRef, null);
    assert.equal(value.semantics.affiliateCta.affiliateLinkObservationRef, null);
    assert.equal(value.semantics.affiliateCta.affiliateUrl, null);
    assert.equal(value.semantics.affiliateCta.destinationHost, null);
    assert.equal(value.semantics.affiliateCta.renderedDestinationLabel, null);
    assert.equal(value.semantics.affiliateCta.relationRequirement.renderedAttribute, null);
    assert.equal(value.semantics.apiCredit.renderedCopy, null);
    assert.doesNotMatch(JSON.stringify(value), /https?:\/\//i);
  });

  it('does not import a runtime framework or perform effects', () => {
    const source = readFileSync(
      new URL('../../packages/web-ui/src/disclosure-affiliate-cta.ts', import.meta.url),
      'utf8',
    );
    assert.doesNotMatch(source, /\bfetch\s*\(/);
    assert.doesNotMatch(source, /\b(?:Date\.now|Math\.random|process\.env)\b/);
    assert.doesNotMatch(source, /from ['"](?:react|next|@aws-sdk\/|playwright|openai)/i);
    assert.doesNotMatch(source, /\b(?:window|document|location)\s*\./);
  });
});
