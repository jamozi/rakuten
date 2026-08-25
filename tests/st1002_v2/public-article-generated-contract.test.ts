import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { ST1002_RECORDED_PUBLIC_ARTICLE_SOURCE_V2 } from '../../packages/web-ui/src/public-article-recorded.v2.ts';
import { createRecordedPublicArticleViewModelV2 } from '../../packages/web-ui/src/public-article-renderer.ts';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const fixture = JSON.parse(
  readFileSync(
    resolve(root, 'changes/st-1002/generated/public-article-renderer-recorded.v2.json'),
    'utf8',
  ),
) as Record<string, unknown>;

describe('ST-1002 V2 generated public contract', () => {
  it('keeps the TypeScript mapper byte-semantically equal to the generated fixture', () => {
    assert.deepEqual(createRecordedPublicArticleViewModelV2(), fixture);
  });

  it('contains no internal identifiers, products, offers, CTA, finance or raw artifacts', () => {
    const serialized = JSON.stringify(fixture);
    assert.doesNotMatch(
      serialized,
      /articleId|publicationId|publicationSnapshotId|approvalIds|claimIds|evidence|finance|commission|revenue|profit|epc|rpm|rawPrompt|reviewBody|sourcePacket/i,
    );
    assert.doesNotMatch(serialized, /affiliateUrl|callToAction|canonicalPath/i);
    const article = fixture['article'] as Record<string, unknown>;
    const metadata = fixture['metadata'] as Record<string, unknown>;
    for (const key of ['productCards', 'offers', 'structuredData', 'canonicalPath']) {
      assert.equal(Object.hasOwn(article, key), false, key);
      assert.equal(Object.hasOwn(metadata, key), false, key);
    }
    assert.doesNotMatch(serialized, /https?:\/\/|javascript:|<script|<iframe|onerror/i);
  });

  it('keeps source routing and external authority disabled', () => {
    const source = ST1002_RECORDED_PUBLIC_ARTICLE_SOURCE_V2 as Record<string, unknown>;
    const route = source['route'] as Record<string, unknown>;
    assert.equal(route['sourceRouteActivated'], false);
    assert.equal(route['exactSlugOnly'], true);
    const runtime = fixture['runtimeBoundary'] as Record<string, unknown>;
    assert.equal(runtime['remotePublicReadModel'], 'DISCONNECTED');
    assert.equal(runtime['outboundIo'], 'NONE');
    assert.equal(runtime['clientComponentCount'], 0);
  });
});
