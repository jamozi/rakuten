import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  createPublicArticleRendererCandidate,
  validatePublicArticleRendererCandidate,
} from '../../packages/web-ui/src/public-article-renderer.ts';

const HASH = '0123456789abcdef'.repeat(4);

function input() {
  return {
    screenId: 'PUB-003' as const,
    route: '/articles/{slug}' as const,
    coordinate: {
      kind: 'SYNTHETIC_PUBLIC_PROJECTION_FIXTURE' as const,
      expectedSha256: HASH,
      observedSha256: HASH,
    },
    slots: [
      {
        blockKey: 'section-heading',
        blockType: 'heading' as const,
        position: 0,
        headingLevel: 2 as const,
        renderedCopy: null,
        renderedHtml: null,
        renderPayload: null,
      },
      {
        blockKey: 'section-body',
        blockType: 'paragraph' as const,
        position: 1,
        headingLevel: null,
        renderedCopy: null,
        renderedHtml: null,
        renderPayload: null,
      },
    ],
  };
}

function assertDeepFrozen(value: unknown, visited = new Set<object>()): void {
  if (value === null || typeof value !== 'object' || visited.has(value)) {
    return;
  }
  visited.add(value);
  assert.ok(Object.isFrozen(value));
  for (const child of Object.values(value)) {
    assertDeepFrozen(child, visited);
  }
}

describe('ST-1002 headless metadata-only model', () => {
  it('returns deterministic detached deeply frozen JSON-safe candidates', () => {
    const source = input();
    const first = createPublicArticleRendererCandidate(source);
    const second = createPublicArticleRendererCandidate(source);
    assert.deepEqual(first, second);
    assert.notEqual(first, second);
    assert.notEqual(first.coordinate, source.coordinate);
    assert.notEqual(first.article.body.slots, source.slots);
    assert.deepEqual(JSON.parse(JSON.stringify(first)), first);
    assertDeepFrozen(first);
    assert.deepEqual(
      validatePublicArticleRendererCandidate(JSON.parse(JSON.stringify(first))),
      first,
    );
  });

  it('binds only opaque caller coordinates without computing or attesting a hash', () => {
    const candidate = createPublicArticleRendererCandidate(input());
    assert.deepEqual(candidate.coordinate, {
      kind: 'SYNTHETIC_PUBLIC_PROJECTION_FIXTURE',
      expectedSha256: HASH,
      observedSha256: HASH,
    });
    assert.deepEqual(candidate.hashBinding, {
      profile: 'OPAQUE_CALLER_BOUND_EQUALITY_ONLY',
      expectedSha256: HASH,
      observedSha256: HASH,
      equal: true,
      recomputed: false,
      canonicalized: false,
      snapshotVerified: false,
      projectionVerified: false,
      hashesAttested: false,
      formalEvidence: false,
    });
  });

  it('preserves ordered metadata slots while exposing no copy, HTML, or payload', () => {
    const candidate = createPublicArticleRendererCandidate(input());
    assert.equal(candidate.article.semanticRole, 'article');
    assert.equal(candidate.article.renderable, false);
    assert.equal(candidate.article.interactive, false);
    assert.deepEqual(candidate.article.header, {
      semanticRole: 'header',
      headingLevel: 1,
      renderedCopy: null,
    });
    assert.deepEqual(
      candidate.article.body.slots.map(({ blockKey, blockType, position }) => ({
        blockKey,
        blockType,
        position,
      })),
      [
        { blockKey: 'section-heading', blockType: 'heading', position: 0 },
        { blockKey: 'section-body', blockType: 'paragraph', position: 1 },
      ],
    );
    for (const slot of candidate.article.body.slots) {
      assert.equal(slot.renderedCopy, null);
      assert.equal(slot.renderedHtml, null);
      assert.equal(slot.renderPayload, null);
    }
  });

  it('permits an empty synthetic projection without interpreting it as success', () => {
    const source = input();
    source.slots.splice(0);
    const candidate = createPublicArticleRendererCandidate(source);
    assert.deepEqual(candidate.article.body.slots, []);
    assert.equal(candidate.article.body.copyAvailable, false);
    assert.equal(candidate.boundaries.localEligibility.value, false);
  });
});
