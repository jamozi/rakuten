import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PUBLIC_ARTICLE_METADATA_BLOCK_TYPES,
  PUBLIC_ARTICLE_RENDERER_CLASSIFICATION,
  PUBLIC_ARTICLE_RENDERER_ERROR_CODES,
  PUBLIC_ARTICLE_RENDERER_SCREEN,
  createPublicArticleRendererCandidate,
} from '../../packages/web-ui/src/index.ts';

const HASH = 'a'.repeat(64);

describe('ST-1002 disabled public article contract', () => {
  it('pins only PUB-003 and keeps its route metadata unregistered', () => {
    assert.deepEqual(PUBLIC_ARTICLE_RENDERER_SCREEN, {
      id: 'PUB-003',
      name: '記事詳細',
      route: '/articles/{slug}',
      area: 'public',
      roles: [],
      purpose: '承認済みPublication Snapshotを表示',
      mvp: true,
      criticalAction: false,
      apiDependencies: [],
      designStatus: 'APPROVED_FOR_IMPLEMENTATION',
      implementationStatus: 'NOT_STARTED',
      runtimeVerification: 'NOT_EXECUTED',
    });
    const candidate = createPublicArticleRendererCandidate({
      screenId: 'PUB-003',
      route: '/articles/{slug}',
      coordinate: {
        kind: 'SYNTHETIC_PUBLIC_PROJECTION_FIXTURE',
        expectedSha256: HASH,
        observedSha256: HASH,
      },
      slots: [],
    });
    assert.equal(
      candidate.classification,
      'UNREGISTERED_DISABLED_HEADLESS_PUBLIC_ARTICLE_RENDERER_CANDIDATE',
    );
    assert.equal(candidate.classification, PUBLIC_ARTICLE_RENDERER_CLASSIFICATION);
    assert.deepEqual(candidate.route, {
      template: '/articles/{slug}',
      routeRegistered: false,
      interactive: false,
      focusable: false,
    });
  });

  it('exposes only generic metadata block types owned by this safe slice', () => {
    assert.deepEqual(PUBLIC_ARTICLE_METADATA_BLOCK_TYPES, [
      'heading',
      'paragraph',
      'summary',
      'selection_criteria',
      'pros_cons',
      'suitable_unsuitable',
      'warning',
      'faq_content',
      'source_note',
    ]);
    assert.ok(!PUBLIC_ARTICLE_METADATA_BLOCK_TYPES.includes('comparison_table' as never));
    assert.ok(!PUBLIC_ARTICLE_METADATA_BLOCK_TYPES.includes('product_card' as never));
    assert.ok(!PUBLIC_ARTICLE_METADATA_BLOCK_TYPES.includes('call_to_action' as never));
  });

  it('keeps a stable closed error vocabulary', () => {
    assert.deepEqual(PUBLIC_ARTICLE_RENDERER_ERROR_CODES, [
      'PUBLIC_ARTICLE_INPUT_INVALID',
      'PUBLIC_ARTICLE_SCREEN_INVALID',
      'PUBLIC_ARTICLE_ROUTE_INVALID',
      'PUBLIC_ARTICLE_HASH_INVALID',
      'PUBLIC_ARTICLE_HASH_MISMATCH',
      'PUBLIC_ARTICLE_SLOT_INVALID',
      'PUBLIC_ARTICLE_SLOT_ORDER_INVALID',
      'PUBLIC_ARTICLE_DUPLICATE_BLOCK_KEY',
      'PUBLIC_ARTICLE_CONTENT_PROHIBITED',
      'PUBLIC_ARTICLE_INTERNAL_FIELD_PROHIBITED',
      'PUBLIC_ARTICLE_PROHIBITED_SURFACE',
      'PUBLIC_ARTICLE_METADATA_INVALID',
      'PUBLIC_ARTICLE_AUTHORITY_INVALID',
      'PUBLIC_ARTICLE_CANDIDATE_INVALID',
    ]);
    assert.equal(new Set(PUBLIC_ARTICLE_RENDERER_ERROR_CODES).size, 14);
  });
});
