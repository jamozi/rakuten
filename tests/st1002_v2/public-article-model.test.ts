import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { ST1002_RECORDED_PUBLIC_ARTICLE_SOURCE_V2 } from '../../packages/web-ui/src/public-article-recorded.v2.ts';
import {
  PUBLIC_ARTICLE_RECORDED_PATH_V2,
  PUBLIC_ARTICLE_RECORDED_SLUG_V2,
  createPublicArticleViewModelV2,
  createRecordedPublicArticleViewModelV2,
  resolveRecordedPublicArticleV2,
  validatePublicArticleViewModelV2,
} from '../../packages/web-ui/src/public-article-renderer.ts';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const recordedView = JSON.parse(
  readFileSync(
    resolve(root, 'changes/st-1002/generated/public-article-renderer-recorded.v2.json'),
    'utf8',
  ),
) as unknown;

function assertDeepFrozen(value: unknown, visited = new Set<object>()): void {
  if (value === null || typeof value !== 'object' || visited.has(value)) return;
  visited.add(value);
  assert.ok(Object.isFrozen(value));
  for (const child of Object.values(value)) assertDeepFrozen(child, visited);
}

describe('ST-1002 V2 recorded article model', () => {
  it('maps the exact generated ST-0904 source to the owner-recorded view fixture', () => {
    const model = createPublicArticleViewModelV2(ST1002_RECORDED_PUBLIC_ARTICLE_SOURCE_V2);
    assert.deepEqual(model, recordedView);
    assert.deepEqual(createRecordedPublicArticleViewModelV2(), model);
    assert.deepEqual(validatePublicArticleViewModelV2(recordedView), model);
    assertDeepFrozen(model);
  });

  it('resolves only the exact local fixture slug without interpreting aliases', () => {
    assert.equal(PUBLIC_ARTICLE_RECORDED_SLUG_V2, 'synthetic-recorded-policy-seo');
    assert.equal(PUBLIC_ARTICLE_RECORDED_PATH_V2, '/articles/synthetic-recorded-policy-seo');
    assert.deepEqual(
      resolveRecordedPublicArticleV2('synthetic-recorded-policy-seo'),
      createRecordedPublicArticleViewModelV2(),
    );
    for (const slug of [
      '',
      'Synthetic-recorded-policy-seo',
      'synthetic-recorded-policy-seo/',
      'synthetic-recorded-policy-seo?next=1',
      '../synthetic-recorded-policy-seo',
      'not-found',
      null,
      1,
      {},
    ]) {
      assert.equal(resolveRecordedPublicArticleV2(slug), null);
    }
  });

  it('renders source text only while omitting the two downstream or empty blocks', () => {
    const model = createRecordedPublicArticleViewModelV2();
    assert.deepEqual(model.article.lead, [
      'この合成Fixtureは、対象条件に応じた商品選びを説明します。',
    ]);
    assert.deepEqual(
      model.article.sections.map(({ kind, heading, items }) => ({ kind, heading, items })),
      [
        {
          kind: 'SUMMARY',
          heading: '要点',
          items: ['条件Aを優先する場合', '商品Aを第一候補として比較します。'],
        },
        {
          kind: 'CONDITIONS',
          heading: '想定する条件',
          items: ['日本国内で購入する前提', '条件Aを重視する人', '条件Bを最優先する人'],
        },
        {
          kind: 'METHODOLOGY',
          heading: '選定方法',
          items: [
            '公開条件を満たす3商品を比較対象としました。',
            '商品同定が未解決',
            '公式仕様を確認できる',
          ],
        },
        {
          kind: 'CRITERIA',
          heading: '選ぶ基準',
          items: ['持ち運び条件に影響する軸です。', '重量'],
        },
        {
          kind: 'DECISION',
          heading: '条件別の考え方',
          items: ['条件Aを優先する場合', '条件A向け'],
        },
        {
          kind: 'WARNING',
          heading: '確認しておきたいこと',
          items: ['価格と在庫は楽天市場で最新情報を確認してください。'],
        },
      ],
    );
    assert.deepEqual(model.article.omittedBlocks, [
      { blockKey: 'block-006', reason: 'OMITTED_DOWNSTREAM_EMPTY_ONLY' },
      { blockKey: 'block-009', reason: 'OMITTED_EMPTY_SOURCE' },
    ]);
  });

  it('binds exact fixture/projection hashes while retaining zero external authority', () => {
    const model = createRecordedPublicArticleViewModelV2();
    assert.deepEqual(model.sourceBinding, {
      fixtureHashVerifiedByOwner: true,
      fixtureSha256: 'a15edb77dcebb3f4b18c9f40737ebc949ab7564191a88052c5b8c54b3ddab7ce',
      fixtureUri: 'repo://changes/st-0904/generated/public-projection-recorded.v2.json',
      profile: 'ST0904_PUBLIC_PROJECTION_RECORDED_LOCAL_V2',
      projectionHashVerifiedByOwner: true,
      projectionSha256: '4c5d4c8e2f2465d53d2ead84cd20e9ea9328b353854d0b365bcde63211ef1980',
    });
    for (const [key, value] of Object.entries(model.authority)) {
      assert.ok(value === false || value === 'NOT_EXECUTED', key);
    }
    assert.deepEqual(model.actions, []);
  });
});
