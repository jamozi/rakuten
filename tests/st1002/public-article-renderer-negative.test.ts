import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PublicArticleRendererError,
  createPublicArticleRendererCandidate,
  validatePublicArticleRendererCandidate,
} from '../../packages/web-ui/src/public-article-renderer.ts';

const HASH = 'c'.repeat(64);

function input(): Record<string, unknown> {
  return {
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: {
      kind: 'SYNTHETIC_PUBLIC_PROJECTION_FIXTURE',
      expectedSha256: HASH,
      observedSha256: HASH,
    },
    slots: [
      {
        blockKey: 'heading-one',
        blockType: 'heading',
        position: 0,
        headingLevel: 2,
        renderedCopy: null,
        renderedHtml: null,
        renderPayload: null,
      },
    ],
  };
}

function rendererError(operation: () => unknown): PublicArticleRendererError {
  try {
    operation();
  } catch (error) {
    assert.ok(error instanceof PublicArticleRendererError);
    assert.equal(error.message, error.code);
    assert.ok(Object.isFrozen(error));
    return error;
  }
  assert.fail('expected public article renderer operation to fail');
}

function create(value: unknown) {
  return createPublicArticleRendererCandidate(value as never);
}

describe('ST-1002 strict negative boundary', () => {
  it('rejects malformed screen, route, hash, and additional input with redacted codes', () => {
    const canary = 'sensitive-st1002-canary';
    const cases: readonly [unknown, string][] = [
      [null, 'PUBLIC_ARTICLE_INPUT_INVALID'],
      [[], 'PUBLIC_ARTICLE_INPUT_INVALID'],
      [{}, 'PUBLIC_ARTICLE_INPUT_INVALID'],
      [{ ...input(), screenId: 'PUB-004' }, 'PUBLIC_ARTICLE_SCREEN_INVALID'],
      [{ ...input(), route: '/articles/demo' }, 'PUBLIC_ARTICLE_ROUTE_INVALID'],
      [
        { ...input(), route: 'https://example.invalid/articles/demo' },
        'PUBLIC_ARTICLE_PROHIBITED_SURFACE',
      ],
      [{ ...input(), extra: canary }, 'PUBLIC_ARTICLE_INPUT_INVALID'],
      [
        {
          ...input(),
          coordinate: {
            kind: 'SYNTHETIC_PUBLIC_PROJECTION_FIXTURE',
            expectedSha256: 'A'.repeat(64),
            observedSha256: 'A'.repeat(64),
          },
        },
        'PUBLIC_ARTICLE_HASH_INVALID',
      ],
      [
        {
          ...input(),
          coordinate: {
            kind: 'SYNTHETIC_PUBLIC_PROJECTION_FIXTURE',
            expectedSha256: HASH,
            observedSha256: 'd'.repeat(64),
          },
        },
        'PUBLIC_ARTICLE_HASH_MISMATCH',
      ],
    ];
    for (const [value, expectedCode] of cases) {
      const error = rendererError(() => create(value));
      assert.equal(error.code, expectedCode);
      assert.doesNotMatch(error.message, new RegExp(canary));
    }
  });

  it('rejects content, HTML, payload, product, CTA, disclosure, links, and internal fields', () => {
    const cases: readonly [string, (value: Record<string, unknown>) => void][] = [
      [
        'PUBLIC_ARTICLE_CONTENT_PROHIBITED',
        (value) => {
          ((value['slots'] as Record<string, unknown>[])[0] as Record<string, unknown>)[
            'renderedCopy'
          ] = 'copy';
        },
      ],
      [
        'PUBLIC_ARTICLE_CONTENT_PROHIBITED',
        (value) => {
          ((value['slots'] as Record<string, unknown>[])[0] as Record<string, unknown>)[
            'renderedHtml'
          ] = '<p>copy</p>';
        },
      ],
      [
        'PUBLIC_ARTICLE_CONTENT_PROHIBITED',
        (value) => {
          ((value['slots'] as Record<string, unknown>[])[0] as Record<string, unknown>)[
            'renderPayload'
          ] = {};
        },
      ],
      [
        'PUBLIC_ARTICLE_PROHIBITED_SURFACE',
        (value) => {
          value['productCards'] = [];
        },
      ],
      [
        'PUBLIC_ARTICLE_PROHIBITED_SURFACE',
        (value) => {
          value['cta'] = null;
        },
      ],
      [
        'PUBLIC_ARTICLE_PROHIBITED_SURFACE',
        (value) => {
          value['disclosureText'] = null;
        },
      ],
      [
        'PUBLIC_ARTICLE_PROHIBITED_SURFACE',
        (value) => {
          value['href'] = '/out';
        },
      ],
      [
        'PUBLIC_ARTICLE_INTERNAL_FIELD_PROHIBITED',
        (value) => {
          value['approvalIds'] = [];
        },
      ],
      [
        'PUBLIC_ARTICLE_INTERNAL_FIELD_PROHIBITED',
        (value) => {
          value['financeProjection'] = null;
        },
      ],
    ];
    for (const [expectedCode, mutate] of cases) {
      const value = structuredClone(input());
      mutate(value);
      assert.equal(rendererError(() => create(value)).code, expectedCode);
    }
  });

  it('rejects unsupported block types, invalid heading metadata, duplicates, and position drift', () => {
    const unsupported = input();
    ((unsupported['slots'] as Record<string, unknown>[])[0] as Record<string, unknown>)[
      'blockType'
    ] = 'product_card';
    assert.equal(rendererError(() => create(unsupported)).code, 'PUBLIC_ARTICLE_SLOT_INVALID');

    const heading = input();
    ((heading['slots'] as Record<string, unknown>[])[0] as Record<string, unknown>)[
      'headingLevel'
    ] = null;
    assert.equal(rendererError(() => create(heading)).code, 'PUBLIC_ARTICLE_SLOT_INVALID');

    const position = input();
    ((position['slots'] as Record<string, unknown>[])[0] as Record<string, unknown>)['position'] =
      1;
    assert.equal(rendererError(() => create(position)).code, 'PUBLIC_ARTICLE_SLOT_ORDER_INVALID');

    const duplicate = input();
    const first = (duplicate['slots'] as Record<string, unknown>[])[0] as Record<string, unknown>;
    (duplicate['slots'] as Record<string, unknown>[]).push({ ...first, position: 1 });
    assert.equal(rendererError(() => create(duplicate)).code, 'PUBLIC_ARTICLE_DUPLICATE_BLOCK_KEY');
  });

  it('rejects subclasses, accessors, symbols, cycles, and hostile proxies without reading getters', () => {
    class HostileInput {
      screenId = 'PUB-003';
    }
    let getterCalled = false;
    const accessor = input();
    Object.defineProperty(accessor, 'route', {
      enumerable: true,
      get() {
        getterCalled = true;
        return '/articles/{slug}';
      },
    });
    const symbol = input() as Record<PropertyKey, unknown>;
    symbol[Symbol('hidden')] = 'hidden';
    const cycle = input();
    cycle['cycle'] = cycle;
    const hostileProxy = new Proxy(input(), {
      ownKeys() {
        throw new TypeError('proxy-canary');
      },
    });
    for (const value of [new HostileInput(), accessor, symbol, cycle, hostileProxy]) {
      assert.equal(rendererError(() => create(value)).code, 'PUBLIC_ARTICLE_INPUT_INVALID');
    }
    assert.equal(getterCalled, false);
  });

  it('rejects route, metadata, and authority escalation on candidate validation', () => {
    const valid = create(input());
    const route = JSON.parse(JSON.stringify(valid)) as Record<string, unknown>;
    (route['route'] as Record<string, unknown>)['routeRegistered'] = true;
    assert.equal(
      rendererError(() => validatePublicArticleRendererCandidate(route)).code,
      'PUBLIC_ARTICLE_METADATA_INVALID',
    );

    const metadata = JSON.parse(JSON.stringify(valid)) as Record<string, unknown>;
    (metadata['metadata'] as Record<string, unknown>)['browserTitle'] = 'invented';
    assert.equal(
      rendererError(() => validatePublicArticleRendererCandidate(metadata)).code,
      'PUBLIC_ARTICLE_CONTENT_PROHIBITED',
    );

    const authority = JSON.parse(JSON.stringify(valid)) as Record<string, unknown>;
    const boundaries = authority['boundaries'] as Record<string, Record<string, unknown>>;
    (boundaries['production'] as Record<string, unknown>)['value'] = true;
    assert.equal(
      rendererError(() => validatePublicArticleRendererCandidate(authority)).code,
      'PUBLIC_ARTICLE_AUTHORITY_INVALID',
    );
  });

  it('returns immutable candidates that cannot gain copy, actions, or authority', () => {
    const valid = create(input());
    assert.throws(() => {
      (valid.article.body.slots[0] as { renderedCopy: string | null }).renderedCopy = 'copy';
    }, TypeError);
    assert.throws(() => {
      (valid.actions as unknown as unknown[]).push('publish');
    }, TypeError);
    assert.throws(() => {
      (valid.boundaries.production as { value: boolean }).value = true;
    }, TypeError);
  });
});
