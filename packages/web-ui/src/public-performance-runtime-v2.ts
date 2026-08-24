import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const PUBLIC_PERFORMANCE_RUNTIME_V2_CLASSIFICATION =
  'LOCAL_RECORDED_PERFORMANCE_IMAGE_SAFETY_V2' as const;

export const PUBLIC_PERFORMANCE_METRICS_V2 = Object.freeze(['LCP', 'INP', 'CLS'] as const);

export type PublicPerformanceMetricV2 = (typeof PUBLIC_PERFORMANCE_METRICS_V2)[number];

export const PUBLIC_PERFORMANCE_V2_ERROR_CODES = Object.freeze([
  'PUBLIC_PERFORMANCE_V2_INPUT_INVALID',
  'PUBLIC_PERFORMANCE_V2_BUDGET_INVALID',
  'PUBLIC_PERFORMANCE_V2_IMAGE_INPUT_INVALID',
  'PUBLIC_PERFORMANCE_V2_IMAGE_DIMENSIONS_INVALID',
  'PUBLIC_PERFORMANCE_V2_IMAGE_RESPONSIVE_WIDTH_INVALID',
  'PUBLIC_PERFORMANCE_V2_CTA_LAYOUT_INPUT_INVALID',
  'PUBLIC_PERFORMANCE_V2_CTA_LAYOUT_RECT_INVALID',
  'PUBLIC_PERFORMANCE_V2_RUNTIME_INVALID',
] as const);

export type PublicPerformanceV2ErrorCode = (typeof PUBLIC_PERFORMANCE_V2_ERROR_CODES)[number];

export class PublicPerformanceV2Error extends TypeError {
  readonly code: PublicPerformanceV2ErrorCode;

  constructor(code: PublicPerformanceV2ErrorCode) {
    super(code);
    this.name = 'PublicPerformanceV2Error';
    this.code = code;
    Object.freeze(this);
  }
}

export interface PublicPerformanceBudgetInputV2 {
  readonly provenance: 'RECORDED_SYNTHETIC_ONLY';
  readonly formalEvidence: false;
  readonly browserObserved: false;
  readonly samples: {
    readonly LCP: readonly number[];
    readonly INP: readonly number[];
    readonly CLS: readonly number[];
  };
}

export interface PublicPerformanceBudgetResultV2 {
  readonly metric: PublicPerformanceMetricV2;
  readonly percentile: 75;
  readonly percentileMethod: 'NEAREST_RANK';
  readonly threshold: number;
  readonly unit: 'MILLISECONDS' | 'SCORE';
  readonly recordedSyntheticValue: number;
  readonly state: 'RECORDED_SYNTHETIC_PASS' | 'RECORDED_SYNTHETIC_FAIL';
  readonly formalEvidence: false;
  readonly browserObserved: false;
  readonly fieldMeasurement: false;
}

export interface PublicPerformanceBudgetAssessmentV2 {
  readonly provenance: 'RECORDED_SYNTHETIC_ONLY';
  readonly fieldWindow: 'ROLLING_28_DAYS';
  readonly results: readonly PublicPerformanceBudgetResultV2[];
  readonly state: 'RECORDED_SYNTHETIC_PASS' | 'RECORDED_SYNTHETIC_FAIL';
  readonly formalEvidence: false;
  readonly browserObserved: false;
  readonly fieldMeasurement: false;
}

export interface PublicImagePolicyInputV2 {
  readonly assetId: string;
  readonly sourceState: 'RECORDED_SYNTHETIC_ONLY';
  readonly placement: 'ABOVE_FOLD' | 'BELOW_FOLD';
  readonly intrinsicWidth: number;
  readonly intrinsicHeight: number;
  readonly responsiveWidths: readonly number[];
}

export interface PublicImagePresentationV2 {
  readonly assetId: string;
  readonly sourceState: 'RECORDED_SYNTHETIC_ONLY';
  readonly placement: 'ABOVE_FOLD' | 'BELOW_FOLD';
  readonly renderable: false;
  readonly src: null;
  readonly srcSet: null;
  readonly width: number;
  readonly height: number;
  readonly aspectRatio: string;
  readonly responsiveWidths: readonly number[];
  readonly sizes: string;
  readonly loading: 'eager' | 'lazy';
  readonly decoding: 'async';
  readonly fetchPriority: 'high' | 'auto';
  readonly layoutSpaceReserved: true;
  readonly upscaleAllowed: false;
  readonly croppingAllowed: false;
  readonly state: 'RECORDED_SYNTHETIC_PASS';
  readonly formalEvidence: false;
}

export interface PublicLayoutRectV2 {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

export interface PublicCtaLayoutInputV2 {
  readonly provenance: 'RECORDED_SYNTHETIC_ONLY';
  readonly before: PublicLayoutRectV2;
  readonly after: PublicLayoutRectV2;
}

export interface PublicCtaLayoutAssessmentV2 {
  readonly provenance: 'RECORDED_SYNTHETIC_ONLY';
  readonly stableReservation: boolean;
  readonly recordedLayoutShiftScore: 0 | null;
  readonly state: 'RECORDED_SYNTHETIC_PASS' | 'RECORDED_SYNTHETIC_FAIL';
  readonly browserObserved: false;
  readonly formalEvidence: false;
}

export interface PublicRumDisabledCaptureReceiptV2 {
  readonly status: 'DROPPED_DISABLED';
  readonly reason: 'OD_012_NONESSENTIAL_TRACKING_DISABLED';
  readonly inputInspected: false;
  readonly captured: false;
  readonly transported: false;
  readonly persisted: false;
}

export interface PublicRumDisabledHookV2 {
  readonly mode: 'DISABLED_OD_012';
  readonly enabled: false;
  readonly eventCatalogId: 'EVT-012';
  readonly capture: (candidate: unknown) => PublicRumDisabledCaptureReceiptV2;
  readonly snapshot: () => readonly [];
}

export interface PublicPerformanceRuntimeV2 {
  readonly schemaVersion: 2;
  readonly storyId: 'ST-1006';
  readonly classification: typeof PUBLIC_PERFORMANCE_RUNTIME_V2_CLASSIFICATION;
  readonly routeBoundary: {
    readonly screenId: 'PUB-003';
    readonly routeTemplate: '/articles/{slug}';
    readonly exactLocalPath: '/articles/synthetic-recorded-policy-seo';
    readonly localRouteRegistered: true;
    readonly sourceProjectionRouteActivated: false;
    readonly publicReadServed: false;
    readonly currentRouteImageCount: 0;
    readonly currentRouteAffiliateCtaRendered: false;
  };
  readonly performanceBudgets: {
    readonly targets: readonly {
      readonly metric: PublicPerformanceMetricV2;
      readonly percentile: 75;
      readonly operator: '<=';
      readonly threshold: number;
      readonly unit: 'MILLISECONDS' | 'SCORE';
      readonly fieldWindow: 'ROLLING_28_DAYS';
    }[];
    readonly recordedSyntheticAssessment: PublicPerformanceBudgetAssessmentV2;
    readonly fieldAssessment: 'NOT_EXECUTED';
    readonly browserLabAssessment: 'NOT_EXECUTED';
    readonly formalTst027: 'NOT_EXECUTED';
  };
  readonly imagePolicy: {
    readonly profile: 'VERIFIED_SOURCE_REQUIRED_RESERVED_RESPONSIVE_IMAGE_V1';
    readonly dimensionsRequired: true;
    readonly responsiveWidthsRequired: true;
    readonly sizesRequired: true;
    readonly reserveLayoutSpace: true;
    readonly upscaleAllowed: false;
    readonly croppingAllowed: false;
    readonly maximumDimensionPx: 8192;
    readonly maximumResponsiveCandidates: 8;
    readonly recordedSyntheticPresentation: PublicImagePresentationV2;
    readonly currentRouteImageApplied: false;
  };
  readonly ctaLayoutPolicy: {
    readonly layoutShiftAllowed: false;
    readonly reservationRequired: true;
    readonly recordedSyntheticAssessment: PublicCtaLayoutAssessmentV2;
    readonly currentRouteCtaApplied: false;
  };
  readonly rumHook: {
    readonly eventCatalogId: 'EVT-012';
    readonly eventName: 'web_vital';
    readonly source: 'public_web';
    readonly privacyDecisionId: 'OD-012';
    readonly privacyDecisionStatus: 'HUMAN_DECISION_REQUIRED';
    readonly safeDefault: 'NONESSENTIAL_TRACKING_DISABLED';
    readonly mode: 'DISABLED_OD_012';
    readonly enabled: false;
    readonly captureBehavior: 'DROP_WITHOUT_INSPECTION';
    readonly bufferCapacity: 0;
    readonly transport: null;
    readonly provider: null;
    readonly collectorConnected: false;
    readonly cookiesUsed: false;
    readonly storageUsed: false;
    readonly consentInferred: false;
    readonly capturedEvents: readonly [];
  };
  readonly cacheBoundary: {
    readonly currentRouteCacheControl: 'no-store';
    readonly currentRouteCacheMutationApplied: false;
    readonly publicCacheStrategySelected: false;
  };
  readonly authority: {
    readonly approvalAuthorized: false;
    readonly trackingAuthorized: false;
    readonly publicationAuthorized: false;
    readonly stagingAuthorized: false;
    readonly releaseAuthorized: false;
    readonly productionAuthorized: false;
    readonly externalWrite: false;
    readonly network: false;
    readonly persistence: false;
    readonly live: 'NOT_EXECUTED';
    readonly browserLab: 'NOT_EXECUTED';
    readonly fieldRum: 'NOT_EXECUTED';
    readonly formalTst027: 'NOT_EXECUTED';
    readonly staging: 'NOT_EXECUTED';
    readonly publication: 'NOT_EXECUTED';
    readonly release: 'NOT_EXECUTED';
    readonly production: 'NOT_EXECUTED';
  };
}

const BUDGET_TARGETS = Object.freeze([
  Object.freeze({ metric: 'LCP' as const, threshold: 2500, unit: 'MILLISECONDS' as const }),
  Object.freeze({ metric: 'INP' as const, threshold: 200, unit: 'MILLISECONDS' as const }),
  Object.freeze({ metric: 'CLS' as const, threshold: 0.1, unit: 'SCORE' as const }),
]);

const RECORDED_BUDGET_INPUT: PublicPerformanceBudgetInputV2 = {
  provenance: 'RECORDED_SYNTHETIC_ONLY',
  formalEvidence: false,
  browserObserved: false,
  samples: {
    LCP: [1600, 1800, 2100, 2400],
    INP: [80, 120, 160, 190],
    CLS: [0, 0.02, 0.05, 0.08],
  },
};

const RECORDED_IMAGE_INPUT: PublicImagePolicyInputV2 = {
  assetId: 'st1006-synthetic-image-001',
  sourceState: 'RECORDED_SYNTHETIC_ONLY',
  placement: 'BELOW_FOLD',
  intrinsicWidth: 640,
  intrinsicHeight: 360,
  responsiveWidths: [320, 640],
};

const RECORDED_CTA_LAYOUT_INPUT: PublicCtaLayoutInputV2 = {
  provenance: 'RECORDED_SYNTHETIC_ONLY',
  before: { x: 0, y: 100, width: 320, height: 48 },
  after: { x: 0, y: 100, width: 320, height: 48 },
};

export const PUBLIC_PERFORMANCE_RECORDED_BUDGET_INPUT_V2 = createJsonValue(
  RECORDED_BUDGET_INPUT,
) as unknown as PublicPerformanceBudgetInputV2;

export const PUBLIC_PERFORMANCE_RECORDED_IMAGE_INPUT_V2 = createJsonValue(
  RECORDED_IMAGE_INPUT,
) as unknown as PublicImagePolicyInputV2;

export const PUBLIC_PERFORMANCE_RECORDED_CTA_LAYOUT_INPUT_V2 = createJsonValue(
  RECORDED_CTA_LAYOUT_INPUT,
) as unknown as PublicCtaLayoutInputV2;

const BUDGET_INPUT_KEYS = ['browserObserved', 'formalEvidence', 'provenance', 'samples'] as const;
const SAMPLE_KEYS = ['CLS', 'INP', 'LCP'] as const;
const IMAGE_INPUT_KEYS = [
  'assetId',
  'intrinsicHeight',
  'intrinsicWidth',
  'placement',
  'responsiveWidths',
  'sourceState',
] as const;
const CTA_INPUT_KEYS = ['after', 'before', 'provenance'] as const;
const RECT_KEYS = ['height', 'width', 'x', 'y'] as const;
const ASSET_ID = /^st1006-synthetic-[a-z0-9-]{1,48}$/;
const MAX_SAMPLE_COUNT = 100;
const MAX_DURATION_MS = 600_000;
const MAX_CLS_SCORE = 100;
const MAX_IMAGE_DIMENSION_PX = 8192;
const MAX_RESPONSIVE_CANDIDATES = 8;

function reject(code: PublicPerformanceV2ErrorCode): never {
  throw new PublicPerformanceV2Error(code);
}

function isJsonObject(value: JsonValue | undefined): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function hasExactKeys(value: JsonObject, expected: readonly string[]): boolean {
  const keys = Object.keys(value).sort();
  return keys.length === expected.length && keys.every((key, index) => key === expected[index]);
}

function cloneObject(value: unknown, code: PublicPerformanceV2ErrorCode): JsonObject {
  try {
    const clone = createJsonValue(value);
    if (!isJsonObject(clone)) return reject(code);
    return clone;
  } catch (error) {
    if (error instanceof PublicPerformanceV2Error) throw error;
    return reject(code);
  }
}

function requireSamples(
  value: JsonValue | undefined,
): Readonly<Record<PublicPerformanceMetricV2, readonly number[]>> {
  if (!isJsonObject(value) || !hasExactKeys(value, SAMPLE_KEYS)) {
    return reject('PUBLIC_PERFORMANCE_V2_BUDGET_INVALID');
  }
  const result: Partial<Record<PublicPerformanceMetricV2, readonly number[]>> = {};
  for (const metric of PUBLIC_PERFORMANCE_METRICS_V2) {
    const raw = value[metric];
    if (!Array.isArray(raw) || raw.length === 0 || raw.length > MAX_SAMPLE_COUNT) {
      return reject('PUBLIC_PERFORMANCE_V2_BUDGET_INVALID');
    }
    const maximum = metric === 'CLS' ? MAX_CLS_SCORE : MAX_DURATION_MS;
    const samples: number[] = [];
    for (const item of raw) {
      if (typeof item !== 'number' || !Number.isFinite(item) || item < 0 || item > maximum) {
        return reject('PUBLIC_PERFORMANCE_V2_BUDGET_INVALID');
      }
      samples.push(item);
    }
    result[metric] = Object.freeze(samples);
  }
  return result as Readonly<Record<PublicPerformanceMetricV2, readonly number[]>>;
}

function validateBudgetInput(value: unknown): PublicPerformanceBudgetInputV2 {
  const input = cloneObject(value, 'PUBLIC_PERFORMANCE_V2_INPUT_INVALID');
  if (
    !hasExactKeys(input, BUDGET_INPUT_KEYS) ||
    input['provenance'] !== 'RECORDED_SYNTHETIC_ONLY' ||
    input['formalEvidence'] !== false ||
    input['browserObserved'] !== false
  ) {
    return reject('PUBLIC_PERFORMANCE_V2_BUDGET_INVALID');
  }
  return {
    provenance: 'RECORDED_SYNTHETIC_ONLY',
    formalEvidence: false,
    browserObserved: false,
    samples: requireSamples(input['samples']),
  };
}

function nearestRank75(samples: readonly number[]): number {
  const sorted = [...samples].sort((left, right) => left - right);
  return sorted[Math.ceil(sorted.length * 0.75) - 1]!;
}

export function evaluatePublicPerformanceBudgetV2(
  value: PublicPerformanceBudgetInputV2,
): PublicPerformanceBudgetAssessmentV2 {
  const input = validateBudgetInput(value);
  const results = BUDGET_TARGETS.map((target) => {
    const recordedSyntheticValue = nearestRank75(input.samples[target.metric]);
    return {
      metric: target.metric,
      percentile: 75 as const,
      percentileMethod: 'NEAREST_RANK' as const,
      threshold: target.threshold,
      unit: target.unit,
      recordedSyntheticValue,
      state:
        recordedSyntheticValue <= target.threshold
          ? ('RECORDED_SYNTHETIC_PASS' as const)
          : ('RECORDED_SYNTHETIC_FAIL' as const),
      formalEvidence: false as const,
      browserObserved: false as const,
      fieldMeasurement: false as const,
    };
  });
  const state = results.every((result) => result.state === 'RECORDED_SYNTHETIC_PASS')
    ? ('RECORDED_SYNTHETIC_PASS' as const)
    : ('RECORDED_SYNTHETIC_FAIL' as const);
  return createJsonValue({
    provenance: 'RECORDED_SYNTHETIC_ONLY',
    fieldWindow: 'ROLLING_28_DAYS',
    results,
    state,
    formalEvidence: false,
    browserObserved: false,
    fieldMeasurement: false,
  }) as unknown as PublicPerformanceBudgetAssessmentV2;
}

function requirePositiveInteger(value: JsonValue | undefined): number | null {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0 ? value : null;
}

function validateImageInput(value: unknown): PublicImagePolicyInputV2 {
  const input = cloneObject(value, 'PUBLIC_PERFORMANCE_V2_IMAGE_INPUT_INVALID');
  if (
    !hasExactKeys(input, IMAGE_INPUT_KEYS) ||
    typeof input['assetId'] !== 'string' ||
    !ASSET_ID.test(input['assetId']) ||
    input['sourceState'] !== 'RECORDED_SYNTHETIC_ONLY' ||
    (input['placement'] !== 'ABOVE_FOLD' && input['placement'] !== 'BELOW_FOLD')
  ) {
    return reject('PUBLIC_PERFORMANCE_V2_IMAGE_INPUT_INVALID');
  }
  const intrinsicWidth = requirePositiveInteger(input['intrinsicWidth']);
  const intrinsicHeight = requirePositiveInteger(input['intrinsicHeight']);
  if (
    intrinsicWidth === null ||
    intrinsicHeight === null ||
    intrinsicWidth > MAX_IMAGE_DIMENSION_PX ||
    intrinsicHeight > MAX_IMAGE_DIMENSION_PX
  ) {
    return reject('PUBLIC_PERFORMANCE_V2_IMAGE_DIMENSIONS_INVALID');
  }
  const rawWidths = input['responsiveWidths'];
  if (
    !Array.isArray(rawWidths) ||
    rawWidths.length === 0 ||
    rawWidths.length > MAX_RESPONSIVE_CANDIDATES
  ) {
    return reject('PUBLIC_PERFORMANCE_V2_IMAGE_RESPONSIVE_WIDTH_INVALID');
  }
  const responsiveWidths: number[] = [];
  for (const rawWidth of rawWidths) {
    const width = requirePositiveInteger(rawWidth);
    if (width === null || width > intrinsicWidth || (responsiveWidths.at(-1) ?? 0) >= width) {
      return reject('PUBLIC_PERFORMANCE_V2_IMAGE_RESPONSIVE_WIDTH_INVALID');
    }
    responsiveWidths.push(width);
  }
  if (responsiveWidths.at(-1) !== intrinsicWidth) {
    return reject('PUBLIC_PERFORMANCE_V2_IMAGE_RESPONSIVE_WIDTH_INVALID');
  }
  return {
    assetId: input['assetId'],
    sourceState: 'RECORDED_SYNTHETIC_ONLY',
    placement: input['placement'],
    intrinsicWidth,
    intrinsicHeight,
    responsiveWidths,
  };
}

export function createPublicImagePresentationV2(
  value: PublicImagePolicyInputV2,
): PublicImagePresentationV2 {
  const input = validateImageInput(value);
  const aboveFold = input.placement === 'ABOVE_FOLD';
  return createJsonValue({
    assetId: input.assetId,
    sourceState: input.sourceState,
    placement: input.placement,
    renderable: false,
    src: null,
    srcSet: null,
    width: input.intrinsicWidth,
    height: input.intrinsicHeight,
    aspectRatio: `${String(input.intrinsicWidth)} / ${String(input.intrinsicHeight)}`,
    responsiveWidths: input.responsiveWidths,
    sizes: `(max-width: ${String(input.intrinsicWidth)}px) 100vw, ${String(input.intrinsicWidth)}px`,
    loading: aboveFold ? 'eager' : 'lazy',
    decoding: 'async',
    fetchPriority: aboveFold ? 'high' : 'auto',
    layoutSpaceReserved: true,
    upscaleAllowed: false,
    croppingAllowed: false,
    state: 'RECORDED_SYNTHETIC_PASS',
    formalEvidence: false,
  }) as unknown as PublicImagePresentationV2;
}

function validateRect(value: JsonValue | undefined): PublicLayoutRectV2 {
  if (!isJsonObject(value) || !hasExactKeys(value, RECT_KEYS)) {
    return reject('PUBLIC_PERFORMANCE_V2_CTA_LAYOUT_RECT_INVALID');
  }
  const x = value['x'];
  const y = value['y'];
  const width = value['width'];
  const height = value['height'];
  if (
    typeof x !== 'number' ||
    typeof y !== 'number' ||
    typeof width !== 'number' ||
    typeof height !== 'number' ||
    !Number.isFinite(x) ||
    !Number.isFinite(y) ||
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    Math.abs(x) > 1_000_000 ||
    Math.abs(y) > 1_000_000 ||
    width <= 0 ||
    height <= 0 ||
    width > MAX_IMAGE_DIMENSION_PX ||
    height > MAX_IMAGE_DIMENSION_PX
  ) {
    return reject('PUBLIC_PERFORMANCE_V2_CTA_LAYOUT_RECT_INVALID');
  }
  return { x, y, width, height };
}

function validateCtaLayoutInput(value: unknown): PublicCtaLayoutInputV2 {
  const input = cloneObject(value, 'PUBLIC_PERFORMANCE_V2_CTA_LAYOUT_INPUT_INVALID');
  if (!hasExactKeys(input, CTA_INPUT_KEYS) || input['provenance'] !== 'RECORDED_SYNTHETIC_ONLY') {
    return reject('PUBLIC_PERFORMANCE_V2_CTA_LAYOUT_INPUT_INVALID');
  }
  return {
    provenance: 'RECORDED_SYNTHETIC_ONLY',
    before: validateRect(input['before']),
    after: validateRect(input['after']),
  };
}

function rectEqual(left: PublicLayoutRectV2, right: PublicLayoutRectV2): boolean {
  return (
    left.x === right.x &&
    left.y === right.y &&
    left.width === right.width &&
    left.height === right.height
  );
}

export function assessPublicCtaLayoutReservationV2(
  value: PublicCtaLayoutInputV2,
): PublicCtaLayoutAssessmentV2 {
  const input = validateCtaLayoutInput(value);
  const stableReservation = rectEqual(input.before, input.after);
  return createJsonValue({
    provenance: 'RECORDED_SYNTHETIC_ONLY',
    stableReservation,
    recordedLayoutShiftScore: stableReservation ? 0 : null,
    state: stableReservation ? 'RECORDED_SYNTHETIC_PASS' : 'RECORDED_SYNTHETIC_FAIL',
    browserObserved: false,
    formalEvidence: false,
  }) as unknown as PublicCtaLayoutAssessmentV2;
}

const DISABLED_CAPTURE_RECEIPT = Object.freeze({
  status: 'DROPPED_DISABLED',
  reason: 'OD_012_NONESSENTIAL_TRACKING_DISABLED',
  inputInspected: false,
  captured: false,
  transported: false,
  persisted: false,
} as const);
const EMPTY_RUM_SNAPSHOT = Object.freeze([] as const);

export function createDefaultDisabledPublicRumHookV2(): PublicRumDisabledHookV2 {
  return Object.freeze({
    mode: 'DISABLED_OD_012',
    enabled: false,
    eventCatalogId: 'EVT-012',
    capture: () => DISABLED_CAPTURE_RECEIPT,
    snapshot: () => EMPTY_RUM_SNAPSHOT,
  });
}

function buildRuntime(): PublicPerformanceRuntimeV2 {
  return createJsonValue({
    schemaVersion: 2,
    storyId: 'ST-1006',
    classification: PUBLIC_PERFORMANCE_RUNTIME_V2_CLASSIFICATION,
    routeBoundary: {
      screenId: 'PUB-003',
      routeTemplate: '/articles/{slug}',
      exactLocalPath: '/articles/synthetic-recorded-policy-seo',
      localRouteRegistered: true,
      sourceProjectionRouteActivated: false,
      publicReadServed: false,
      currentRouteImageCount: 0,
      currentRouteAffiliateCtaRendered: false,
    },
    performanceBudgets: {
      targets: BUDGET_TARGETS.map((target) => ({
        metric: target.metric,
        percentile: 75,
        operator: '<=',
        threshold: target.threshold,
        unit: target.unit,
        fieldWindow: 'ROLLING_28_DAYS',
      })),
      recordedSyntheticAssessment: evaluatePublicPerformanceBudgetV2(
        PUBLIC_PERFORMANCE_RECORDED_BUDGET_INPUT_V2,
      ),
      fieldAssessment: 'NOT_EXECUTED',
      browserLabAssessment: 'NOT_EXECUTED',
      formalTst027: 'NOT_EXECUTED',
    },
    imagePolicy: {
      profile: 'VERIFIED_SOURCE_REQUIRED_RESERVED_RESPONSIVE_IMAGE_V1',
      dimensionsRequired: true,
      responsiveWidthsRequired: true,
      sizesRequired: true,
      reserveLayoutSpace: true,
      upscaleAllowed: false,
      croppingAllowed: false,
      maximumDimensionPx: MAX_IMAGE_DIMENSION_PX,
      maximumResponsiveCandidates: MAX_RESPONSIVE_CANDIDATES,
      recordedSyntheticPresentation: createPublicImagePresentationV2(
        PUBLIC_PERFORMANCE_RECORDED_IMAGE_INPUT_V2,
      ),
      currentRouteImageApplied: false,
    },
    ctaLayoutPolicy: {
      layoutShiftAllowed: false,
      reservationRequired: true,
      recordedSyntheticAssessment: assessPublicCtaLayoutReservationV2(
        PUBLIC_PERFORMANCE_RECORDED_CTA_LAYOUT_INPUT_V2,
      ),
      currentRouteCtaApplied: false,
    },
    rumHook: {
      eventCatalogId: 'EVT-012',
      eventName: 'web_vital',
      source: 'public_web',
      privacyDecisionId: 'OD-012',
      privacyDecisionStatus: 'HUMAN_DECISION_REQUIRED',
      safeDefault: 'NONESSENTIAL_TRACKING_DISABLED',
      mode: 'DISABLED_OD_012',
      enabled: false,
      captureBehavior: 'DROP_WITHOUT_INSPECTION',
      bufferCapacity: 0,
      transport: null,
      provider: null,
      collectorConnected: false,
      cookiesUsed: false,
      storageUsed: false,
      consentInferred: false,
      capturedEvents: [],
    },
    cacheBoundary: {
      currentRouteCacheControl: 'no-store',
      currentRouteCacheMutationApplied: false,
      publicCacheStrategySelected: false,
    },
    authority: {
      approvalAuthorized: false,
      trackingAuthorized: false,
      publicationAuthorized: false,
      stagingAuthorized: false,
      releaseAuthorized: false,
      productionAuthorized: false,
      externalWrite: false,
      network: false,
      persistence: false,
      live: 'NOT_EXECUTED',
      browserLab: 'NOT_EXECUTED',
      fieldRum: 'NOT_EXECUTED',
      formalTst027: 'NOT_EXECUTED',
      staging: 'NOT_EXECUTED',
      publication: 'NOT_EXECUTED',
      release: 'NOT_EXECUTED',
      production: 'NOT_EXECUTED',
    },
  }) as unknown as PublicPerformanceRuntimeV2;
}

function jsonEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function validatePublicPerformanceRuntimeV2(value: unknown): PublicPerformanceRuntimeV2 {
  const clone = cloneObject(value, 'PUBLIC_PERFORMANCE_V2_RUNTIME_INVALID');
  const expected = buildRuntime();
  if (!jsonEqual(clone, expected)) return reject('PUBLIC_PERFORMANCE_V2_RUNTIME_INVALID');
  return clone as unknown as PublicPerformanceRuntimeV2;
}

export function createRecordedPublicPerformanceRuntimeV2(): PublicPerformanceRuntimeV2 {
  return validatePublicPerformanceRuntimeV2(buildRuntime());
}
