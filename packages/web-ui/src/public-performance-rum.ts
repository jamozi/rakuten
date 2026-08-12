import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const PUBLIC_PERFORMANCE_RUM_CLASSIFICATION =
  'UNREGISTERED_DISABLED_HEADLESS_ST1006_PERFORMANCE_RUM_REQUIREMENTS_CANDIDATE' as const;

const screenSource = {
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
} as const;

export const PUBLIC_PERFORMANCE_RUM_SCREEN = createJsonValue(
  screenSource,
) as unknown as typeof screenSource;

export const PUBLIC_PERFORMANCE_RUM_METRICS = Object.freeze(['LCP', 'INP', 'CLS'] as const);

export type PublicPerformanceRumMetric = (typeof PUBLIC_PERFORMANCE_RUM_METRICS)[number];

export const PUBLIC_PERFORMANCE_RUM_ERROR_CODES = Object.freeze([
  'PUBLIC_PERFORMANCE_RUM_INPUT_INVALID',
  'PUBLIC_PERFORMANCE_RUM_SCREEN_INVALID',
  'PUBLIC_PERFORMANCE_RUM_ROUTE_INVALID',
  'PUBLIC_PERFORMANCE_RUM_COORDINATE_INVALID',
  'PUBLIC_PERFORMANCE_RUM_HASH_INVALID',
  'PUBLIC_PERFORMANCE_RUM_HASH_MISMATCH',
  'PUBLIC_PERFORMANCE_RUM_CONTENT_PROHIBITED',
  'PUBLIC_PERFORMANCE_RUM_INTERNAL_FIELD_PROHIBITED',
  'PUBLIC_PERFORMANCE_RUM_EFFECT_PROHIBITED',
  'PUBLIC_PERFORMANCE_RUM_METADATA_INVALID',
  'PUBLIC_PERFORMANCE_RUM_REQUIREMENT_INVALID',
  'PUBLIC_PERFORMANCE_RUM_OBSERVATION_INVALID',
  'PUBLIC_PERFORMANCE_RUM_PRIVACY_INVALID',
  'PUBLIC_PERFORMANCE_RUM_AUTHORITY_INVALID',
  'PUBLIC_PERFORMANCE_RUM_CANDIDATE_INVALID',
] as const);

export type PublicPerformanceRumErrorCode = (typeof PUBLIC_PERFORMANCE_RUM_ERROR_CODES)[number];

export class PublicPerformanceRumError extends TypeError {
  readonly code: PublicPerformanceRumErrorCode;

  constructor(code: PublicPerformanceRumErrorCode) {
    super(code);
    this.name = 'PublicPerformanceRumError';
    this.code = code;
    Object.freeze(this);
  }
}

export interface PublicPerformanceRumSyntheticCoordinateInput {
  readonly kind: 'SYNTHETIC_ST1006_PERFORMANCE_REQUIREMENTS_FIXTURE';
  readonly expectedSha256: string;
  readonly observedSha256: string;
}

export interface PublicPerformanceRumInput {
  readonly screenId: 'PUB-003';
  readonly route: '/articles/{slug}';
  readonly coordinate: PublicPerformanceRumSyntheticCoordinateInput;
}

export interface PublicPerformanceRumBoundaryResult {
  readonly value: false;
  readonly status: 'NOT_EXECUTED';
  readonly reason: string;
}

export interface PublicPerformanceRumBoundaries {
  readonly routeRegistered: PublicPerformanceRumBoundaryResult;
  readonly rendererConnected: PublicPerformanceRumBoundaryResult;
  readonly dom: PublicPerformanceRumBoundaryResult;
  readonly react: PublicPerformanceRumBoundaryResult;
  readonly ssr: PublicPerformanceRumBoundaryResult;
  readonly browserInstrumentation: PublicPerformanceRumBoundaryResult;
  readonly performanceObserver: PublicPerformanceRumBoundaryResult;
  readonly beaconTransport: PublicPerformanceRumBoundaryResult;
  readonly fetchTransport: PublicPerformanceRumBoundaryResult;
  readonly analyticsEventEmission: PublicPerformanceRumBoundaryResult;
  readonly cookieAccess: PublicPerformanceRumBoundaryResult;
  readonly storageAccess: PublicPerformanceRumBoundaryResult;
  readonly consentResolution: PublicPerformanceRumBoundaryResult;
  readonly eventCollector: PublicPerformanceRumBoundaryResult;
  readonly network: PublicPerformanceRumBoundaryResult;
  readonly cacheRuntime: PublicPerformanceRumBoundaryResult;
  readonly imageRuntime: PublicPerformanceRumBoundaryResult;
  readonly ctaLayoutRuntime: PublicPerformanceRumBoundaryResult;
  readonly browserLab: PublicPerformanceRumBoundaryResult;
  readonly fieldRum: PublicPerformanceRumBoundaryResult;
  readonly privacyVerification: PublicPerformanceRumBoundaryResult;
  readonly formalTst027: PublicPerformanceRumBoundaryResult;
  readonly live: PublicPerformanceRumBoundaryResult;
  readonly staging: PublicPerformanceRumBoundaryResult;
  readonly publicationAuthorization: PublicPerformanceRumBoundaryResult;
  readonly release: PublicPerformanceRumBoundaryResult;
  readonly production: PublicPerformanceRumBoundaryResult;
  readonly localEligibility: PublicPerformanceRumBoundaryResult;
}

export interface PublicPerformanceRumTarget {
  readonly metric: PublicPerformanceRumMetric;
  readonly state: 'PROVISIONAL_TARGET';
  readonly percentile: 75;
  readonly operator: '<=';
  readonly targetThreshold: number;
  readonly unit: 'MILLISECONDS' | 'SCORE';
  readonly fieldWindow: 'ROLLING_28_DAYS';
  readonly observedValue: null;
  readonly observedRating: null;
  readonly observationState: 'NOT_EVALUATED';
  readonly measurementImplemented: false;
  readonly measurementExecuted: false;
}

export interface PublicPerformanceRumNotEvaluated {
  readonly state: 'NOT_EVALUATED';
  readonly evidenceRef: null;
  readonly value: null;
  readonly verified: false;
}

export interface PublicPerformanceRumCandidate {
  readonly classification: typeof PUBLIC_PERFORMANCE_RUM_CLASSIFICATION;
  readonly screen: typeof PUBLIC_PERFORMANCE_RUM_SCREEN;
  readonly route: {
    readonly template: '/articles/{slug}';
    readonly routeRegistered: false;
    readonly rendererConnected: false;
  };
  readonly coordinate: PublicPerformanceRumSyntheticCoordinateInput;
  readonly hashBinding: {
    readonly profile: 'OPAQUE_CALLER_BOUND_EQUALITY_ONLY';
    readonly expectedSha256: string;
    readonly observedSha256: string;
    readonly equal: true;
    readonly recomputed: false;
    readonly canonicalized: false;
    readonly rendererVerified: false;
    readonly runtimeVerified: false;
    readonly formalEvidence: false;
  };
  readonly performanceTargets: readonly PublicPerformanceRumTarget[];
  readonly optimizationRequirements: {
    readonly state: 'LOCAL_FIXED_REQUIREMENTS_ONLY';
    readonly imageDimensionsReservedRequired: true;
    readonly affiliateOrAnalyticsScriptLayoutShiftAllowed: false;
    readonly ctaLayoutShiftAllowed: false;
    readonly cacheStrategy: null;
    readonly imageOptimizationStrategy: null;
    readonly ctaLayoutStrategy: null;
    readonly runtimeApplied: false;
    readonly cacheEvaluation: PublicPerformanceRumNotEvaluated;
    readonly imageEvaluation: PublicPerformanceRumNotEvaluated;
    readonly ctaLayoutShiftEvaluation: PublicPerformanceRumNotEvaluated;
  };
  readonly rumRequirements: {
    readonly eventCatalogId: 'EVT-012';
    readonly eventName: 'web_vital';
    readonly source: 'public_web';
    readonly purpose: 'RUM性能';
    readonly permittedParameters: readonly [
      'article_id',
      'snapshot_id',
      'metric_name',
      'metric_value',
      'rating',
      'navigation_type',
    ];
    readonly prohibitedParameters: readonly [
      'email',
      'phone',
      'raw_ip',
      'full_user_agent',
      'raw_search_query',
      'article_body',
      'source_packet_text',
      'affiliate_url_query_secret',
    ];
    readonly instrumentationImplemented: false;
    readonly collectorConnected: false;
    readonly transport: null;
    readonly provider: null;
    readonly eventEmissionEnabled: false;
  };
  readonly observations: {
    readonly labTarget: PublicPerformanceRumNotEvaluated;
    readonly noCtaCls: PublicPerformanceRumNotEvaluated;
    readonly fieldRum: PublicPerformanceRumNotEvaluated;
    readonly metricValues: readonly [];
    readonly emittedEvents: readonly [];
  };
  readonly privacy: {
    readonly decisionId: 'OD-012';
    readonly decisionStatus: 'HUMAN_DECISION_REQUIRED';
    readonly blocking: true;
    readonly safeDefault: 'NONESSENTIAL_TRACKING_DISABLED';
    readonly firstPartyMinimalEventEligibility: 'NOT_EVALUATED';
    readonly consentState: 'NOT_EVALUATED';
    readonly consentInferred: false;
    readonly cookiesUsed: false;
    readonly storageUsed: false;
    readonly fingerprintingUsed: false;
    readonly providerSelected: false;
    readonly eventEmissionAllowed: false;
  };
  readonly conditionalLocalEligibility: false;
  readonly eligibilityReasons: readonly [
    'ST_1002_RUNTIME_RENDERER_ABSENT',
    'ST_1201_COLLECTOR_NOT_CONNECTED',
    'ST_1202_INSTRUMENTATION_NOT_IMPLEMENTED',
    'OD_012_PRIVACY_CONSENT_UNRESOLVED',
    'LAB_TARGET_NOT_EVALUATED',
    'CTA_LAYOUT_SHIFT_NOT_EVALUATED',
    'FIELD_RUM_NOT_EVALUATED',
    'FORMAL_TST_027_NOT_EXECUTED',
  ];
  readonly authorization: {
    readonly approval: false;
    readonly publication: false;
    readonly release: false;
    readonly production: false;
    readonly formalEvidence: false;
  };
  readonly boundaries: PublicPerformanceRumBoundaries;
  readonly events: readonly [];
  readonly actions: readonly [];
  readonly effects: readonly [];
}

const boundaryReasons = {
  routeRegistered: 'NO_RUNTIME_ROUTE_REGISTERED',
  rendererConnected: 'ST_1002_RUNTIME_RENDERER_ABSENT',
  dom: 'DOM_NOT_IMPLEMENTED',
  react: 'REACT_NOT_IMPLEMENTED',
  ssr: 'SSR_NOT_IMPLEMENTED',
  browserInstrumentation: 'BROWSER_INSTRUMENTATION_NOT_IMPLEMENTED',
  performanceObserver: 'PERFORMANCE_OBSERVER_NOT_USED',
  beaconTransport: 'BEACON_TRANSPORT_NOT_USED',
  fetchTransport: 'FETCH_TRANSPORT_NOT_USED',
  analyticsEventEmission: 'ANALYTICS_EVENT_EMISSION_DISABLED',
  cookieAccess: 'COOKIE_ACCESS_NOT_USED',
  storageAccess: 'STORAGE_ACCESS_NOT_USED',
  consentResolution: 'OD_012_PRIVACY_CONSENT_UNRESOLVED',
  eventCollector: 'ST_1201_COLLECTOR_NOT_CONNECTED',
  network: 'NETWORK_NOT_USED',
  cacheRuntime: 'CACHE_RUNTIME_NOT_IMPLEMENTED',
  imageRuntime: 'IMAGE_RUNTIME_NOT_IMPLEMENTED',
  ctaLayoutRuntime: 'CTA_LAYOUT_RUNTIME_NOT_IMPLEMENTED',
  browserLab: 'BROWSER_RUM_LAB_NOT_EXECUTED',
  fieldRum: 'FIELD_RUM_NOT_EXECUTED',
  privacyVerification: 'PRIVACY_VERIFICATION_NOT_EXECUTED',
  formalTst027: 'FORMAL_TST_027_NOT_EXECUTED',
  live: 'LIVE_NOT_AUTHORIZED',
  staging: 'STAGING_NOT_AUTHORIZED',
  publicationAuthorization: 'PUBLICATION_NOT_AUTHORIZED',
  release: 'RELEASE_NOT_AUTHORIZED',
  production: 'PRODUCTION_NOT_AUTHORIZED',
  localEligibility: 'PERFORMANCE_RUNTIME_AND_EVIDENCE_GATES_UNSATISFIED',
} as const;

const INPUT_KEYS = ['coordinate', 'route', 'screenId'] as const;
const COORDINATE_KEYS = ['expectedSha256', 'kind', 'observedSha256'] as const;
const SHA256 = /^[0-9a-f]{64}$/;
const ACTIVE_MARKUP = /<\s*(?:script|iframe)\b|\bon[a-z]+\s*=/i;
const CONTENT_KEY_FRAGMENTS = ['articlebody', 'copy', 'html', 'rawsearchquery', 'text'];
const INTERNAL_KEY_FRAGMENTS = [
  'approvalid',
  'claim',
  'evidence',
  'finance',
  'publicationid',
  'rawprompt',
  'sourcepacket',
];
const EFFECT_KEY_FRAGMENTS = [
  'beacon',
  'callback',
  'consent',
  'cookie',
  'emit',
  'fetch',
  'handler',
  'network',
  'observer',
  'provider',
  'storage',
  'track',
];

function reject(code: PublicPerformanceRumErrorCode): never {
  throw new PublicPerformanceRumError(code);
}

function normalizedKey(key: string): string {
  return key.replace(/[\s_-]+/g, '').toLowerCase();
}

function isStrictPlainTree(value: unknown, ancestors = new WeakSet<object>()): boolean {
  if (
    value === null ||
    typeof value === 'string' ||
    typeof value === 'boolean' ||
    (typeof value === 'number' && Number.isFinite(value))
  ) {
    return true;
  }
  if (typeof value !== 'object' || ancestors.has(value)) return false;
  ancestors.add(value);
  try {
    const array = Array.isArray(value);
    if (Object.getPrototypeOf(value) !== (array ? Array.prototype : Object.prototype)) return false;
    for (const key of Reflect.ownKeys(value)) {
      if (typeof key !== 'string' || key === 'length') {
        if (key === 'length') continue;
        return false;
      }
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      if (
        descriptor === undefined ||
        !descriptor.enumerable ||
        !Object.hasOwn(descriptor, 'value') ||
        !isStrictPlainTree(descriptor.value, ancestors)
      ) {
        return false;
      }
    }
    return true;
  } catch {
    return false;
  } finally {
    ancestors.delete(value);
  }
}

function isJsonObject(value: JsonValue | undefined): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function scanProhibitedSurface(value: JsonValue): PublicPerformanceRumErrorCode | null {
  if (typeof value === 'string') {
    return ACTIVE_MARKUP.test(value) ? 'PUBLIC_PERFORMANCE_RUM_CONTENT_PROHIBITED' : null;
  }
  if (value === null || typeof value !== 'object') return null;
  if (Array.isArray(value)) {
    for (const item of value) {
      const finding = scanProhibitedSurface(item);
      if (finding !== null) return finding;
    }
    return null;
  }
  for (const [key, item] of Object.entries(value)) {
    const normalized = normalizedKey(key);
    if (CONTENT_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))) {
      return 'PUBLIC_PERFORMANCE_RUM_CONTENT_PROHIBITED';
    }
    if (INTERNAL_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))) {
      return 'PUBLIC_PERFORMANCE_RUM_INTERNAL_FIELD_PROHIBITED';
    }
    if (
      normalized.startsWith('on') ||
      EFFECT_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))
    ) {
      return 'PUBLIC_PERFORMANCE_RUM_EFFECT_PROHIBITED';
    }
    const finding = scanProhibitedSurface(item);
    if (finding !== null) return finding;
  }
  return null;
}

function clonePlainObject(value: unknown, scanSurface = true): JsonObject {
  if (!isStrictPlainTree(value)) return reject('PUBLIC_PERFORMANCE_RUM_INPUT_INVALID');
  let clone: JsonValue;
  try {
    clone = createJsonValue(value);
  } catch {
    return reject('PUBLIC_PERFORMANCE_RUM_INPUT_INVALID');
  }
  if (!isJsonObject(clone)) return reject('PUBLIC_PERFORMANCE_RUM_INPUT_INVALID');
  if (scanSurface) {
    const finding = scanProhibitedSurface(clone);
    if (finding !== null) return reject(finding);
  }
  return clone;
}

function hasExactKeys(value: JsonObject, expected: readonly string[]): boolean {
  const keys = Object.keys(value).sort();
  return keys.length === expected.length && keys.every((key, index) => key === expected[index]);
}

function requireCoordinate(
  value: JsonValue | undefined,
): PublicPerformanceRumSyntheticCoordinateInput {
  if (!isJsonObject(value) || !hasExactKeys(value, COORDINATE_KEYS)) {
    return reject('PUBLIC_PERFORMANCE_RUM_COORDINATE_INVALID');
  }
  const kind = value['kind'];
  const expectedSha256 = value['expectedSha256'];
  const observedSha256 = value['observedSha256'];
  if (kind !== 'SYNTHETIC_ST1006_PERFORMANCE_REQUIREMENTS_FIXTURE') {
    return reject('PUBLIC_PERFORMANCE_RUM_COORDINATE_INVALID');
  }
  if (
    typeof expectedSha256 !== 'string' ||
    typeof observedSha256 !== 'string' ||
    !SHA256.test(expectedSha256) ||
    !SHA256.test(observedSha256)
  ) {
    return reject('PUBLIC_PERFORMANCE_RUM_HASH_INVALID');
  }
  if (expectedSha256 !== observedSha256) return reject('PUBLIC_PERFORMANCE_RUM_HASH_MISMATCH');
  return { kind, expectedSha256, observedSha256 };
}

function validatedInput(input: PublicPerformanceRumInput): PublicPerformanceRumInput {
  const value = clonePlainObject(input);
  if (!hasExactKeys(value, INPUT_KEYS)) return reject('PUBLIC_PERFORMANCE_RUM_INPUT_INVALID');
  if (value['screenId'] !== 'PUB-003') return reject('PUBLIC_PERFORMANCE_RUM_SCREEN_INVALID');
  if (value['route'] !== '/articles/{slug}') return reject('PUBLIC_PERFORMANCE_RUM_ROUTE_INVALID');
  return {
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: requireCoordinate(value['coordinate']),
  };
}

function notEvaluated(): PublicPerformanceRumNotEvaluated {
  return { state: 'NOT_EVALUATED', evidenceRef: null, value: null, verified: false };
}

function performanceTargets(): readonly PublicPerformanceRumTarget[] {
  return [
    {
      metric: 'LCP',
      state: 'PROVISIONAL_TARGET',
      percentile: 75,
      operator: '<=',
      targetThreshold: 2500,
      unit: 'MILLISECONDS',
      fieldWindow: 'ROLLING_28_DAYS',
      observedValue: null,
      observedRating: null,
      observationState: 'NOT_EVALUATED',
      measurementImplemented: false,
      measurementExecuted: false,
    },
    {
      metric: 'INP',
      state: 'PROVISIONAL_TARGET',
      percentile: 75,
      operator: '<=',
      targetThreshold: 200,
      unit: 'MILLISECONDS',
      fieldWindow: 'ROLLING_28_DAYS',
      observedValue: null,
      observedRating: null,
      observationState: 'NOT_EVALUATED',
      measurementImplemented: false,
      measurementExecuted: false,
    },
    {
      metric: 'CLS',
      state: 'PROVISIONAL_TARGET',
      percentile: 75,
      operator: '<=',
      targetThreshold: 0.1,
      unit: 'SCORE',
      fieldWindow: 'ROLLING_28_DAYS',
      observedValue: null,
      observedRating: null,
      observationState: 'NOT_EVALUATED',
      measurementImplemented: false,
      measurementExecuted: false,
    },
  ];
}

function makeBoundaries(): PublicPerformanceRumBoundaries {
  return Object.fromEntries(
    Object.entries(boundaryReasons).map(([key, reason]) => [
      key,
      { value: false, status: 'NOT_EXECUTED', reason },
    ]),
  ) as unknown as PublicPerformanceRumBoundaries;
}

function buildCandidate(input: PublicPerformanceRumInput): PublicPerformanceRumCandidate {
  return createJsonValue({
    classification: PUBLIC_PERFORMANCE_RUM_CLASSIFICATION,
    screen: PUBLIC_PERFORMANCE_RUM_SCREEN,
    route: {
      template: input.route,
      routeRegistered: false,
      rendererConnected: false,
    },
    coordinate: input.coordinate,
    hashBinding: {
      profile: 'OPAQUE_CALLER_BOUND_EQUALITY_ONLY',
      expectedSha256: input.coordinate.expectedSha256,
      observedSha256: input.coordinate.observedSha256,
      equal: true,
      recomputed: false,
      canonicalized: false,
      rendererVerified: false,
      runtimeVerified: false,
      formalEvidence: false,
    },
    performanceTargets: performanceTargets(),
    optimizationRequirements: {
      state: 'LOCAL_FIXED_REQUIREMENTS_ONLY',
      imageDimensionsReservedRequired: true,
      affiliateOrAnalyticsScriptLayoutShiftAllowed: false,
      ctaLayoutShiftAllowed: false,
      cacheStrategy: null,
      imageOptimizationStrategy: null,
      ctaLayoutStrategy: null,
      runtimeApplied: false,
      cacheEvaluation: notEvaluated(),
      imageEvaluation: notEvaluated(),
      ctaLayoutShiftEvaluation: notEvaluated(),
    },
    rumRequirements: {
      eventCatalogId: 'EVT-012',
      eventName: 'web_vital',
      source: 'public_web',
      purpose: 'RUM性能',
      permittedParameters: [
        'article_id',
        'snapshot_id',
        'metric_name',
        'metric_value',
        'rating',
        'navigation_type',
      ],
      prohibitedParameters: [
        'email',
        'phone',
        'raw_ip',
        'full_user_agent',
        'raw_search_query',
        'article_body',
        'source_packet_text',
        'affiliate_url_query_secret',
      ],
      instrumentationImplemented: false,
      collectorConnected: false,
      transport: null,
      provider: null,
      eventEmissionEnabled: false,
    },
    observations: {
      labTarget: notEvaluated(),
      noCtaCls: notEvaluated(),
      fieldRum: notEvaluated(),
      metricValues: [],
      emittedEvents: [],
    },
    privacy: {
      decisionId: 'OD-012',
      decisionStatus: 'HUMAN_DECISION_REQUIRED',
      blocking: true,
      safeDefault: 'NONESSENTIAL_TRACKING_DISABLED',
      firstPartyMinimalEventEligibility: 'NOT_EVALUATED',
      consentState: 'NOT_EVALUATED',
      consentInferred: false,
      cookiesUsed: false,
      storageUsed: false,
      fingerprintingUsed: false,
      providerSelected: false,
      eventEmissionAllowed: false,
    },
    conditionalLocalEligibility: false,
    eligibilityReasons: [
      'ST_1002_RUNTIME_RENDERER_ABSENT',
      'ST_1201_COLLECTOR_NOT_CONNECTED',
      'ST_1202_INSTRUMENTATION_NOT_IMPLEMENTED',
      'OD_012_PRIVACY_CONSENT_UNRESOLVED',
      'LAB_TARGET_NOT_EVALUATED',
      'CTA_LAYOUT_SHIFT_NOT_EVALUATED',
      'FIELD_RUM_NOT_EVALUATED',
      'FORMAL_TST_027_NOT_EXECUTED',
    ],
    authorization: {
      approval: false,
      publication: false,
      release: false,
      production: false,
      formalEvidence: false,
    },
    boundaries: makeBoundaries(),
    events: [],
    actions: [],
    effects: [],
  }) as unknown as PublicPerformanceRumCandidate;
}

function jsonEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function unexpectedProhibitedSurface(
  value: JsonValue | undefined,
  expected: JsonValue | undefined,
): PublicPerformanceRumErrorCode | null {
  if (jsonEqual(value, expected)) return null;
  if (!isJsonObject(value) || !isJsonObject(expected)) return null;
  for (const [key, item] of Object.entries(value)) {
    if (!Object.hasOwn(expected, key)) return scanProhibitedSurface({ [key]: item });
    const nested = unexpectedProhibitedSurface(item, expected[key]);
    if (nested !== null) return nested;
  }
  return null;
}

function candidateInput(value: JsonObject): PublicPerformanceRumInput {
  const screen = value['screen'];
  const coordinate = value['coordinate'];
  if (!isJsonObject(screen) || !isJsonObject(coordinate)) {
    return reject('PUBLIC_PERFORMANCE_RUM_CANDIDATE_INVALID');
  }
  return {
    screenId: screen['id'] as 'PUB-003',
    route: screen['route'] as '/articles/{slug}',
    coordinate: coordinate as unknown as PublicPerformanceRumSyntheticCoordinateInput,
  };
}

function classifyCandidateFailure(
  value: JsonObject,
  expected: PublicPerformanceRumCandidate,
): PublicPerformanceRumErrorCode {
  const prohibited = unexpectedProhibitedSurface(value, expected as unknown as JsonValue);
  if (prohibited !== null) return prohibited;
  if (
    !jsonEqual(value['screen'], expected.screen) ||
    !jsonEqual(value['route'], expected.route) ||
    !jsonEqual(value['coordinate'], expected.coordinate) ||
    !jsonEqual(value['hashBinding'], expected.hashBinding)
  ) {
    return 'PUBLIC_PERFORMANCE_RUM_METADATA_INVALID';
  }
  if (
    !jsonEqual(value['performanceTargets'], expected.performanceTargets) ||
    !jsonEqual(value['optimizationRequirements'], expected.optimizationRequirements)
  ) {
    return 'PUBLIC_PERFORMANCE_RUM_REQUIREMENT_INVALID';
  }
  if (
    !jsonEqual(value['rumRequirements'], expected.rumRequirements) ||
    !jsonEqual(value['observations'], expected.observations)
  ) {
    return 'PUBLIC_PERFORMANCE_RUM_OBSERVATION_INVALID';
  }
  if (!jsonEqual(value['privacy'], expected.privacy)) {
    return 'PUBLIC_PERFORMANCE_RUM_PRIVACY_INVALID';
  }
  if (
    value['conditionalLocalEligibility'] !== false ||
    !jsonEqual(value['eligibilityReasons'], expected.eligibilityReasons) ||
    !jsonEqual(value['authorization'], expected.authorization) ||
    !jsonEqual(value['boundaries'], expected.boundaries) ||
    !jsonEqual(value['events'], expected.events) ||
    !jsonEqual(value['actions'], expected.actions) ||
    !jsonEqual(value['effects'], expected.effects)
  ) {
    return 'PUBLIC_PERFORMANCE_RUM_AUTHORITY_INVALID';
  }
  return 'PUBLIC_PERFORMANCE_RUM_CANDIDATE_INVALID';
}

export function validatePublicPerformanceRumCandidate(
  value: unknown,
): PublicPerformanceRumCandidate {
  const clone = clonePlainObject(value, false);
  let input: PublicPerformanceRumInput;
  try {
    input = validatedInput(candidateInput(clone));
  } catch (error) {
    if (error instanceof PublicPerformanceRumError) throw error;
    return reject('PUBLIC_PERFORMANCE_RUM_CANDIDATE_INVALID');
  }
  const expected = buildCandidate(input);
  if (!jsonEqual(clone, expected)) return reject(classifyCandidateFailure(clone, expected));
  return clone as unknown as PublicPerformanceRumCandidate;
}

export function createPublicPerformanceRumCandidate(
  input: PublicPerformanceRumInput,
): PublicPerformanceRumCandidate {
  return validatePublicPerformanceRumCandidate(buildCandidate(validatedInput(input)));
}
