import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PUBLIC_AFFILIATE_SYNTHETIC_RECEIPT_V2,
  PUBLIC_DISCLOSURE_AFFILIATE_RECORDED_INPUT_V2,
  PublicDisclosureAffiliateV2Error,
  createPublicDisclosureAffiliateArticleViewV2,
  createRecordedPublicDisclosureAffiliateArticleViewV2,
  createSyntheticPublicAffiliateCtaV2,
  validatePublicAffiliateCtaSyntheticViewV2,
  validatePublicDisclosureAffiliateArticleViewV2,
  type PublicDisclosureAffiliateV2ErrorCode,
} from '../../packages/web-ui/src/disclosure-affiliate-cta.ts';

function closedError(operation: () => unknown): PublicDisclosureAffiliateV2Error {
  try {
    operation();
  } catch (error) {
    assert.ok(error instanceof PublicDisclosureAffiliateV2Error);
    assert.equal(error.message, error.code);
    assert.ok(Object.isFrozen(error));
    return error;
  }
  assert.fail('expected ST-1004 V2 operation to fail');
}

function expectCode(operation: () => unknown, code: PublicDisclosureAffiliateV2ErrorCode): void {
  assert.equal(closedError(operation).code, code);
}

function articleInput(): Record<string, unknown> {
  return structuredClone(PUBLIC_DISCLOSURE_AFFILIATE_RECORDED_INPUT_V2) as Record<string, unknown>;
}

function receipt(): Record<string, unknown> {
  return structuredClone(PUBLIC_AFFILIATE_SYNTHETIC_RECEIPT_V2) as Record<string, unknown>;
}

describe('ST-1004 V2 hostile and open-redirect boundaries', () => {
  it('rejects source drift, arbitrary URLs, return URLs and unknown surface', () => {
    const actualUrl = articleInput();
    (actualUrl['affiliateSource'] as Record<string, unknown>)['affiliateUrl'] =
      'https://example.invalid/forbidden';
    expectCode(
      () => createPublicDisclosureAffiliateArticleViewV2(actualUrl as never),
      'PUBLIC_DISCLOSURE_V2_SOURCE_MISMATCH',
    );

    for (const [key, value] of [
      ['href', 'https://example.invalid/forbidden'],
      ['returnUrl', '/articles/synthetic-recorded-policy-seo'],
      ['redirect', true],
      ['clientHandler', 'navigate'],
    ] as const) {
      const input = articleInput();
      input[key] = value;
      expectCode(
        () => createPublicDisclosureAffiliateArticleViewV2(input as never),
        'PUBLIC_DISCLOSURE_V2_INPUT_INVALID',
      );
    }
  });

  it('accepts no synthetic destination other than the exact example.invalid fixture', () => {
    for (const href of [
      'https://www.rakuten.co.jp/item',
      'https://example.invalid/rakuten-marketplace/item?next=https://evil.invalid',
      'https://example.invalid/rakuten-marketplace/item#redirect',
      '//example.invalid/rakuten-marketplace/item',
      'javascript:alert(1)',
    ]) {
      const input = receipt();
      input['href'] = href;
      expectCode(
        () => createSyntheticPublicAffiliateCtaV2(input as never),
        'PUBLIC_AFFILIATE_CTA_V2_DESTINATION_INVALID',
      );
    }
    const withReturn = receipt();
    withReturn['returnUrl'] = '/';
    expectCode(
      () => createSyntheticPublicAffiliateCtaV2(withReturn as never),
      'PUBLIC_AFFILIATE_CTA_V2_RECEIPT_INVALID',
    );
  });

  it('fails closed when any synthetic verification gate is incomplete', () => {
    for (const key of [
      'directDestinationVerified',
      'urlIntegrityVerified',
      'hostAllowlistVerified',
      'reachabilityVerified',
      'linkHealthVerified',
      'freshnessVerified',
      'killSwitchAllows',
    ]) {
      const input = receipt();
      input[key] = false;
      expectCode(
        () => createSyntheticPublicAffiliateCtaV2(input as never),
        'PUBLIC_AFFILIATE_CTA_V2_VERIFICATION_INCOMPLETE',
      );
    }
  });

  it('rejects subclasses, accessors, symbols, cycles and throwing proxies without getters', () => {
    class HostileInput {
      schemaVersion = 2;
    }
    let getterCalled = false;
    const accessor = articleInput();
    Object.defineProperty(accessor, 'screenId', {
      enumerable: true,
      get() {
        getterCalled = true;
        return 'PUB-003';
      },
    });
    const symbolic = articleInput() as Record<PropertyKey, unknown>;
    symbolic[Symbol('hidden')] = true;
    const cyclic = articleInput();
    cyclic['cycle'] = cyclic;
    const proxy = new Proxy(articleInput(), {
      ownKeys() {
        throw new TypeError('sensitive-proxy-canary');
      },
    });
    for (const value of [new HostileInput(), accessor, symbolic, cyclic, proxy]) {
      expectCode(
        () => createPublicDisclosureAffiliateArticleViewV2(value as never),
        'PUBLIC_DISCLOSURE_V2_INPUT_INVALID',
      );
    }
    assert.equal(getterCalled, false);
  });

  it('rejects mutated views and exposes only closed non-reflecting errors', () => {
    const canary = 'sensitive-st1004-v2-canary';
    const article = structuredClone(
      createRecordedPublicDisclosureAffiliateArticleViewV2(),
    ) as unknown as Record<string, Record<string, unknown>>;
    article['disclosure']!['copy'] = canary;
    const articleError = closedError(() => validatePublicDisclosureAffiliateArticleViewV2(article));
    assert.equal(articleError.code, 'PUBLIC_DISCLOSURE_V2_VIEW_INVALID');
    assert.doesNotMatch(articleError.message, new RegExp(canary));

    const synthetic = structuredClone(
      createSyntheticPublicAffiliateCtaV2(PUBLIC_AFFILIATE_SYNTHETIC_RECEIPT_V2),
    ) as unknown as Record<string, unknown>;
    synthetic['href'] = `https://${canary}.invalid`;
    const syntheticError = closedError(() => validatePublicAffiliateCtaSyntheticViewV2(synthetic));
    assert.equal(syntheticError.code, 'PUBLIC_AFFILIATE_CTA_V2_VIEW_INVALID');
    assert.doesNotMatch(syntheticError.message, new RegExp(canary));
  });
});
