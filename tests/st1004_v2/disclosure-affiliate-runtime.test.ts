import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  PUBLIC_AFFILIATE_CTA_COPY_V2,
  PUBLIC_AFFILIATE_REL_V2,
  PUBLIC_AFFILIATE_SYNTHETIC_RECEIPT_V2,
  PUBLIC_DISCLOSURE_AFFILIATE_RECORDED_INPUT_V2,
  PUBLIC_DISCLOSURE_COPY_V2,
  createPublicDisclosureAffiliateArticleViewV2,
  createRecordedPublicDisclosureAffiliateRuntimeV2,
  createSyntheticPublicAffiliateCtaV2,
  validatePublicAffiliateCtaSyntheticViewV2,
  validatePublicDisclosureAffiliateArticleViewV2,
} from '../../packages/web-ui/src/index.ts';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const recorded = JSON.parse(
  readFileSync(
    resolve(root, 'changes/st-1004/generated/disclosure-affiliate-recorded.v2.json'),
    'utf8',
  ),
) as unknown;

function assertDeepFrozen(value: unknown, seen = new Set<object>()): void {
  if (value === null || typeof value !== 'object' || seen.has(value)) return;
  seen.add(value);
  assert.ok(Object.isFrozen(value));
  for (const child of Object.values(value)) assertDeepFrozen(child, seen);
}

describe('ST-1004 V2 recorded disclosure and affiliate runtime', () => {
  it('matches the owner-generated recorded output and is deeply immutable', () => {
    const runtime = createRecordedPublicDisclosureAffiliateRuntimeV2();
    assert.deepEqual(runtime, recorded);
    assertDeepFrozen(runtime);
    assert.notEqual(runtime, createRecordedPublicDisclosureAffiliateRuntimeV2());
  });

  it('renders the fixed, required disclosure before body while preserving one heading', () => {
    const view = createPublicDisclosureAffiliateArticleViewV2(
      PUBLIC_DISCLOSURE_AFFILIATE_RECORDED_INPUT_V2,
    );
    assert.deepEqual(validatePublicDisclosureAffiliateArticleViewV2(view), view);
    assert.equal(view.componentOrder[0], 'UI-C031');
    assert.equal(view.disclosure.componentId, 'UI-C031');
    assert.equal(view.disclosure.copy, PUBLIC_DISCLOSURE_COPY_V2);
    assert.equal(view.disclosure.required, true);
    assert.equal(view.disclosure.rendererOwned, true);
    assert.equal(view.disclosure.editorRemovable, false);
    assert.equal(view.disclosure.headingCount, 1);
    assert.equal(view.disclosure.placement, 'AFTER_H1_BEFORE_LEAD_AND_ARTICLE_BODY');
    assert.equal(view.disclosure.precedesArticleBody, true);
    assert.equal(view.disclosure.firstViewRequired, true);
  });

  it('omits the route CTA when ST-0503 has no affiliate URL', () => {
    const cta = createRecordedPublicDisclosureAffiliateRuntimeV2().articleView.affiliateCta;
    assert.equal(cta.state, 'UNAVAILABLE_SOURCE');
    assert.equal(cta.rendered, false);
    assert.equal(cta.enabled, false);
    assert.equal(cta.anchor, null);
    assert.equal(cta.source.affiliateUrl, null);
    assert.equal(cta.notice.rendered, true);
    assert.equal(cta.fixedCopy, PUBLIC_AFFILIATE_CTA_COPY_V2);
    assert.equal(cta.requiredRel, PUBLIC_AFFILIATE_REL_V2);
    assert.doesNotMatch(JSON.stringify(cta), /https?:\/\//u);
    assert.ok(
      Object.values(cta.gates).every(
        (state) => state === 'UNAVAILABLE_SOURCE' || state === 'NOT_EVALUATED',
      ),
    );
  });

  it('provides one exact example.invalid synthetic native-anchor fixture only', () => {
    const cta = createSyntheticPublicAffiliateCtaV2(PUBLIC_AFFILIATE_SYNTHETIC_RECEIPT_V2);
    assert.deepEqual(validatePublicAffiliateCtaSyntheticViewV2(cta), cta);
    assert.equal(cta.href, 'https://example.invalid/rakuten-marketplace/item');
    assert.equal(cta.rel, 'sponsored nofollow');
    assert.equal(cta.copy, '楽天市場で写真・価格・在庫を見る');
    assert.equal(cta.destinationLabel, '楽天市場');
    assert.equal(cta.keyboardInteraction, 'NATIVE_ANCHOR');
    assert.equal(cta.minimumTargetBlockSizePx, 44);
    assert.equal(cta.minimumTargetInlineSizePx, 44);
    assert.equal(cta.beaconConfigured, false);
    assert.equal(cta.beaconRequiredForNavigation, false);
    assert.equal(cta.instrumentationFailureBlocksNavigation, false);
    assert.equal(cta.raosRedirect, false);
    assert.equal(cta.cloaking, false);
    assert.equal(cta.urlMutation, false);
    assert.equal(cta.routeRendered, false);
  });

  it('keeps the future verified-receipt port disconnected and valueless', () => {
    const port = createRecordedPublicDisclosureAffiliateRuntimeV2().receiptPort;
    assert.deepEqual(port, {
      profile: 'CLOSED_VERIFIED_AFFILIATE_DESTINATION_RECEIPT_PORT_V1',
      connected: false,
      acceptsArbitraryUrl: false,
      acceptsReturnUrl: false,
      liveReceiptAcceptedByThisSlice: false,
      reason: 'URL_HOST_AND_LINK_HEALTH_AUTHORITY_UNAVAILABLE',
    });
  });
});
