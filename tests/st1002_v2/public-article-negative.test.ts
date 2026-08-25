import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { ST1002_RECORDED_PUBLIC_ARTICLE_SOURCE_V2 } from '../../packages/web-ui/src/public-article-recorded.v2.ts';
import {
  PublicArticleV2Error,
  createPublicArticleViewModelV2,
  createRecordedPublicArticleViewModelV2,
  requireRecordedPublicArticleV2,
  validatePublicArticleViewModelV2,
} from '../../packages/web-ui/src/public-article-renderer.ts';

function closedError(operation: () => unknown): PublicArticleV2Error {
  try {
    operation();
  } catch (error) {
    assert.ok(error instanceof PublicArticleV2Error);
    assert.equal(error.message, error.code);
    assert.ok(Object.isFrozen(error));
    return error;
  }
  assert.fail('expected ST-1002 V2 operation to fail');
}

function sourceClone(): Record<string, unknown> {
  return structuredClone(ST1002_RECORDED_PUBLIC_ARTICLE_SOURCE_V2) as Record<string, unknown>;
}

describe('ST-1002 V2 fail-closed boundaries', () => {
  it('rejects any source drift with a redacted stable code', () => {
    const canary = 'sensitive-st1002-v2-canary';
    const mutations: readonly ((source: Record<string, unknown>) => void)[] = [
      (source) => {
        source['unexpected'] = canary;
      },
      (source) => {
        const binding = source['sourceBinding'] as Record<string, unknown>;
        binding['fixtureSha256'] = '0'.repeat(64);
      },
      (source) => {
        const route = source['route'] as Record<string, unknown>;
        route['slug'] = canary;
      },
      (source) => {
        const article = source['article'] as Record<string, unknown>;
        article['title'] = `<script>${canary}</script>`;
      },
      (source) => {
        const article = source['article'] as Record<string, unknown>;
        const blocks = article['blocks'] as Record<string, unknown>[];
        blocks[0] = { ...blocks[0], blockType: 'product_card' };
      },
      (source) => {
        const article = source['article'] as Record<string, unknown>;
        article['finance'] = canary;
      },
    ];
    for (const mutate of mutations) {
      const source = sourceClone();
      mutate(source);
      const error = closedError(() => createPublicArticleViewModelV2(source));
      assert.equal(error.code, 'PUBLIC_ARTICLE_V2_SOURCE_MISMATCH');
      assert.doesNotMatch(error.message, new RegExp(canary));
    }
  });

  it('rejects subclasses, accessors, symbols, cycles and hostile proxies without getters', () => {
    class HostileSource {
      schemaVersion = 2;
    }
    let getterCalled = false;
    const accessor = sourceClone();
    Object.defineProperty(accessor, 'storyId', {
      enumerable: true,
      get() {
        getterCalled = true;
        return 'ST-1002';
      },
    });
    const symbolic = sourceClone() as Record<PropertyKey, unknown>;
    symbolic[Symbol('hidden')] = 'hidden';
    const cyclic = sourceClone();
    cyclic['cycle'] = cyclic;
    const proxy = new Proxy(sourceClone(), {
      ownKeys() {
        throw new TypeError('proxy-canary');
      },
    });
    for (const value of [new HostileSource(), accessor, symbolic, cyclic, proxy]) {
      assert.equal(
        closedError(() => createPublicArticleViewModelV2(value)).code,
        'PUBLIC_ARTICLE_V2_SOURCE_INVALID',
      );
    }
    assert.equal(getterCalled, false);
  });

  it('rejects view and authority mutations and keeps successful values immutable', () => {
    const valid = createRecordedPublicArticleViewModelV2();
    const title = structuredClone(valid) as unknown as Record<string, Record<string, unknown>>;
    title['article']!['title'] = 'changed';
    assert.equal(
      closedError(() => validatePublicArticleViewModelV2(title)).code,
      'PUBLIC_ARTICLE_V2_VIEW_INVALID',
    );
    const authority = structuredClone(valid) as unknown as Record<string, Record<string, unknown>>;
    authority['authority']!['production_authorized'] = true;
    assert.equal(
      closedError(() => validatePublicArticleViewModelV2(authority)).code,
      'PUBLIC_ARTICLE_V2_VIEW_INVALID',
    );
    assert.throws(() => {
      (valid.article.sections as unknown as unknown[]).push('new');
    }, TypeError);
    assert.throws(() => {
      (valid.authority as Record<string, unknown>)['production_authorized'] = true;
    }, TypeError);
  });

  it('does not echo an unknown slug in the closed not-found error', () => {
    const canary = 'unknown-sensitive-slug';
    const error = closedError(() => requireRecordedPublicArticleV2(canary));
    assert.equal(error.code, 'PUBLIC_ARTICLE_V2_SLUG_INVALID');
    assert.doesNotMatch(error.message, new RegExp(canary));
  });
});
