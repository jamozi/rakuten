import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PUBLIC_PERFORMANCE_RECORDED_CTA_LAYOUT_INPUT_V2,
  PUBLIC_PERFORMANCE_RECORDED_IMAGE_INPUT_V2,
  PublicPerformanceV2Error,
  assessPublicCtaLayoutReservationV2,
  createPublicImagePresentationV2,
  type PublicPerformanceV2ErrorCode,
} from '../../packages/web-ui/src/public-performance-runtime-v2.ts';

function expectCode(operation: () => unknown, code: PublicPerformanceV2ErrorCode): void {
  try {
    operation();
  } catch (error) {
    assert.ok(error instanceof PublicPerformanceV2Error);
    assert.equal(error.code, code);
    assert.equal(error.message, code);
    assert.ok(Object.isFrozen(error));
    return;
  }
  assert.fail('expected ST-1006 V2 operation to fail');
}

describe('ST-1006 V2 responsive image and CTA reservation policy', () => {
  it('reserves explicit dimensions and lazily sizes the below-fold fixture', () => {
    const image = createPublicImagePresentationV2(PUBLIC_PERFORMANCE_RECORDED_IMAGE_INPUT_V2);
    assert.equal(image.renderable, false);
    assert.equal(image.src, null);
    assert.equal(image.srcSet, null);
    assert.equal(image.width, 640);
    assert.equal(image.height, 360);
    assert.equal(image.aspectRatio, '640 / 360');
    assert.deepEqual(image.responsiveWidths, [320, 640]);
    assert.equal(image.sizes, '(max-width: 640px) 100vw, 640px');
    assert.equal(image.loading, 'lazy');
    assert.equal(image.decoding, 'async');
    assert.equal(image.fetchPriority, 'auto');
    assert.equal(image.layoutSpaceReserved, true);
    assert.equal(image.upscaleAllowed, false);
    assert.equal(image.croppingAllowed, false);
  });

  it('uses eager/high only for an explicitly above-fold synthetic presentation', () => {
    const image = createPublicImagePresentationV2({
      ...PUBLIC_PERFORMANCE_RECORDED_IMAGE_INPUT_V2,
      assetId: 'st1006-synthetic-above-fold-001',
      placement: 'ABOVE_FOLD',
    });
    assert.equal(image.loading, 'eager');
    assert.equal(image.fetchPriority, 'high');
    assert.equal(image.layoutSpaceReserved, true);
    assert.equal(image.renderable, false);
  });

  it('rejects missing/unsafe dimensions, upscaling and unordered candidates', () => {
    for (const [mutation, code] of [
      [{ intrinsicWidth: 0 }, 'PUBLIC_PERFORMANCE_V2_IMAGE_DIMENSIONS_INVALID'],
      [{ intrinsicHeight: 8193 }, 'PUBLIC_PERFORMANCE_V2_IMAGE_DIMENSIONS_INVALID'],
      [{ responsiveWidths: [320, 641] }, 'PUBLIC_PERFORMANCE_V2_IMAGE_RESPONSIVE_WIDTH_INVALID'],
      [{ responsiveWidths: [640, 320] }, 'PUBLIC_PERFORMANCE_V2_IMAGE_RESPONSIVE_WIDTH_INVALID'],
      [{ responsiveWidths: [320] }, 'PUBLIC_PERFORMANCE_V2_IMAGE_RESPONSIVE_WIDTH_INVALID'],
    ] as const) {
      expectCode(
        () =>
          createPublicImagePresentationV2({
            ...PUBLIC_PERFORMANCE_RECORDED_IMAGE_INPUT_V2,
            ...mutation,
          } as never),
        code,
      );
    }
    expectCode(
      () =>
        createPublicImagePresentationV2({
          ...PUBLIC_PERFORMANCE_RECORDED_IMAGE_INPUT_V2,
          sourceUrl: 'https://example.invalid/image',
        } as never),
      'PUBLIC_PERFORMANCE_V2_IMAGE_INPUT_INVALID',
    );
  });

  it('proves only exact synthetic rectangle stability and never estimates a changed CLS', () => {
    const stable = assessPublicCtaLayoutReservationV2(
      PUBLIC_PERFORMANCE_RECORDED_CTA_LAYOUT_INPUT_V2,
    );
    assert.equal(stable.stableReservation, true);
    assert.equal(stable.recordedLayoutShiftScore, 0);
    assert.equal(stable.state, 'RECORDED_SYNTHETIC_PASS');
    assert.equal(stable.browserObserved, false);
    assert.equal(stable.formalEvidence, false);

    const changed = assessPublicCtaLayoutReservationV2({
      ...PUBLIC_PERFORMANCE_RECORDED_CTA_LAYOUT_INPUT_V2,
      after: {
        ...PUBLIC_PERFORMANCE_RECORDED_CTA_LAYOUT_INPUT_V2.after,
        y: 101,
      },
    });
    assert.equal(changed.stableReservation, false);
    assert.equal(changed.recordedLayoutShiftScore, null);
    assert.equal(changed.state, 'RECORDED_SYNTHETIC_FAIL');
  });
});
