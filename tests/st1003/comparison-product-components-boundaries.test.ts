import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import { createPublicComparisonComponentsCandidate } from '../../packages/web-ui/src/comparison-product-components.ts';

const HASH = 'b'.repeat(64);

function candidate() {
  return createPublicComparisonComponentsCandidate({
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: {
      kind: 'SYNTHETIC_ST1003_SEMANTIC_FIXTURE',
      expectedSha256: HASH,
      observedSha256: HASH,
    },
  });
}

describe('ST-1003 safety boundaries', () => {
  it('keeps every runtime, formal, and authority boundary false', () => {
    const value = candidate();
    for (const boundary of Object.values(value.boundaries)) {
      assert.equal(boundary.value, false);
      assert.equal(boundary.status, 'NOT_EXECUTED');
    }
    assert.deepEqual(value.actions, []);
  });

  it('contains no public product values, copy, URLs, CTA, or finance fields', () => {
    const value = candidate();
    const serialized = JSON.stringify(value);
    assert.doesNotMatch(serialized, /https?:\/\//i);
    assert.doesNotMatch(
      serialized,
      /"(?:displayName|renderedHtml|affiliateUrl|offersPayload|priceJpy|revenue|profit|epc|rpm)"/i,
    );
    assert.equal(value.semantics.productCard.renderable, false);
    assert.equal(value.semantics.comparisonTable.renderable, false);
    assert.equal(value.semantics.tradeoff.renderable, false);
  });

  it('does not import a runtime framework or perform effects', () => {
    const source = readFileSync(
      new URL('../../packages/web-ui/src/comparison-product-components.ts', import.meta.url),
      'utf8',
    );
    assert.doesNotMatch(source, /\bfetch\s*\(/);
    assert.doesNotMatch(source, /\b(?:Date\.now|Math\.random|process\.env)\b/);
    assert.doesNotMatch(source, /from ['"](?:react|next|@aws-sdk\/|playwright|openai)/i);
  });
});
