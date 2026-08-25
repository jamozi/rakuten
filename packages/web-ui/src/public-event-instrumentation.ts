import { createJsonValue, type JsonObject } from './serializable.ts';

export const PUBLIC_EVENT_INSTRUMENTATION_CLASSIFICATION =
  'UNREGISTERED_DISABLED_HEADLESS_ST1202_PUBLIC_EVENT_INSTRUMENTATION_REQUIREMENTS_CANDIDATE' as const;

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

export const PUBLIC_EVENT_INSTRUMENTATION_SCREEN = createJsonValue(
  screenSource,
) as unknown as typeof screenSource;

export const PUBLIC_EVENT_INSTRUMENTATION_EVENT_IDS = Object.freeze([
  'EVT-001',
  'EVT-002',
  'EVT-003',
  'EVT-004',
  'EVT-006',
  'EVT-012',
] as const);

export type PublicEventInstrumentationEventId =
  (typeof PUBLIC_EVENT_INSTRUMENTATION_EVENT_IDS)[number];

export const PUBLIC_EVENT_INSTRUMENTATION_PROHIBITED_PARAMETERS = Object.freeze([
  'email',
  'phone',
  'raw_ip',
  'full_user_agent',
  'raw_search_query',
  'article_body',
  'source_packet_text',
  'affiliate_url_query_secret',
] as const);

export const PUBLIC_EVENT_INSTRUMENTATION_ERROR_CODES = Object.freeze([
  'PUBLIC_EVENT_INSTRUMENTATION_INPUT_INVALID',
  'PUBLIC_EVENT_INSTRUMENTATION_SCREEN_INVALID',
  'PUBLIC_EVENT_INSTRUMENTATION_ROUTE_INVALID',
  'PUBLIC_EVENT_INSTRUMENTATION_COORDINATE_INVALID',
  'PUBLIC_EVENT_INSTRUMENTATION_HASH_INVALID',
  'PUBLIC_EVENT_INSTRUMENTATION_HASH_MISMATCH',
  'PUBLIC_EVENT_INSTRUMENTATION_METADATA_INVALID',
  'PUBLIC_EVENT_INSTRUMENTATION_REQUIREMENTS_INVALID',
  'PUBLIC_EVENT_INSTRUMENTATION_PRIVACY_INVALID',
  'PUBLIC_EVENT_INSTRUMENTATION_RUNTIME_PROHIBITED',
  'PUBLIC_EVENT_INSTRUMENTATION_AUTHORITY_INVALID',
  'PUBLIC_EVENT_INSTRUMENTATION_CANDIDATE_INVALID',
] as const);

export type PublicEventInstrumentationErrorCode =
  (typeof PUBLIC_EVENT_INSTRUMENTATION_ERROR_CODES)[number];

export class PublicEventInstrumentationError extends TypeError {
  readonly code: PublicEventInstrumentationErrorCode;

  constructor(code: PublicEventInstrumentationErrorCode) {
    super(code);
    this.name = 'PublicEventInstrumentationError';
    this.code = code;
    Object.freeze(this);
  }
}

export interface PublicEventInstrumentationSyntheticCoordinateInput {
  readonly kind: 'SYNTHETIC_ST1202_INSTRUMENTATION_REQUIREMENTS_FIXTURE';
  readonly expectedSha256: string;
  readonly observedSha256: string;
}

export interface PublicEventInstrumentationInput {
  readonly screenId: 'PUB-003';
  readonly route: '/articles/{slug}';
  readonly coordinate: PublicEventInstrumentationSyntheticCoordinateInput;
}

export interface PublicEventInstrumentationUnknownValue {
  readonly state: 'NOT_EVALUATED';
  readonly value: null;
}

export interface PublicEventInstrumentationEventRequirement {
  readonly id: PublicEventInstrumentationEventId;
  readonly eventName:
    | 'article_view'
    | 'qualified_decision_engagement'
    | 'affiliate_cta_impression'
    | 'affiliate_click'
    | 'comparison_interaction'
    | 'web_vital';
  readonly source: 'public_web';
  readonly purpose: string;
  readonly mvp: true;
  readonly parameters: readonly string[];
  readonly prohibitedParameters: typeof PUBLIC_EVENT_INSTRUMENTATION_PROHIBITED_PARAMETERS;
  readonly trigger: PublicEventInstrumentationUnknownValue;
  readonly identity: PublicEventInstrumentationUnknownValue;
  readonly eventValues: PublicEventInstrumentationUnknownValue;
  readonly threshold: PublicEventInstrumentationUnknownValue;
  readonly transport: PublicEventInstrumentationUnknownValue;
  readonly collector: PublicEventInstrumentationUnknownValue;
  readonly instrumentationImplemented: false;
  readonly emissionEnabled: false;
}

export interface PublicEventInstrumentationBoundaryResult {
  readonly value: false;
  readonly status: 'NOT_EXECUTED';
  readonly reason: string;
}

export interface PublicEventInstrumentationBoundaries {
  readonly routeRegistered: PublicEventInstrumentationBoundaryResult;
  readonly rendererConnected: PublicEventInstrumentationBoundaryResult;
  readonly ctaInstanceAvailable: PublicEventInstrumentationBoundaryResult;
  readonly dom: PublicEventInstrumentationBoundaryResult;
  readonly react: PublicEventInstrumentationBoundaryResult;
  readonly next: PublicEventInstrumentationBoundaryResult;
  readonly lifecycleHooks: PublicEventInstrumentationBoundaryResult;
  readonly browser: PublicEventInstrumentationBoundaryResult;
  readonly performanceObserver: PublicEventInstrumentationBoundaryResult;
  readonly clock: PublicEventInstrumentationBoundaryResult;
  readonly randomness: PublicEventInstrumentationBoundaryResult;
  readonly cookieAccess: PublicEventInstrumentationBoundaryResult;
  readonly storageAccess: PublicEventInstrumentationBoundaryResult;
  readonly sendBeacon: PublicEventInstrumentationBoundaryResult;
  readonly fetchKeepalive: PublicEventInstrumentationBoundaryResult;
  readonly network: PublicEventInstrumentationBoundaryResult;
  readonly publicApiPub004: PublicEventInstrumentationBoundaryResult;
  readonly collectorConnected: PublicEventInstrumentationBoundaryResult;
  readonly eventConstruction: PublicEventInstrumentationBoundaryResult;
  readonly eventEmission: PublicEventInstrumentationBoundaryResult;
  readonly persistence: PublicEventInstrumentationBoundaryResult;
  readonly durableDedupe: PublicEventInstrumentationBoundaryResult;
  readonly formalTst022: PublicEventInstrumentationBoundaryResult;
  readonly formalTst030: PublicEventInstrumentationBoundaryResult;
  readonly live: PublicEventInstrumentationBoundaryResult;
  readonly staging: PublicEventInstrumentationBoundaryResult;
  readonly release: PublicEventInstrumentationBoundaryResult;
  readonly production: PublicEventInstrumentationBoundaryResult;
}

export interface PublicEventInstrumentationCandidate {
  readonly classification: typeof PUBLIC_EVENT_INSTRUMENTATION_CLASSIFICATION;
  readonly screen: typeof PUBLIC_EVENT_INSTRUMENTATION_SCREEN;
  readonly route: {
    readonly template: '/articles/{slug}';
    readonly registered: false;
    readonly rendererConnected: false;
    readonly interactive: false;
  };
  readonly coordinate: PublicEventInstrumentationSyntheticCoordinateInput;
  readonly hashBinding: {
    readonly profile: 'OPAQUE_CALLER_BOUND_EQUALITY_ONLY';
    readonly expectedSha256: string;
    readonly observedSha256: string;
    readonly equal: true;
    readonly recomputed: false;
    readonly canonicalized: false;
    readonly rendererVerified: false;
    readonly instrumentationVerified: false;
    readonly runtimeVerified: false;
    readonly formalEvidence: false;
  };
  readonly slice: {
    readonly id: 'AN-SLICE-002';
    readonly name: 'Public event instrumentation';
    readonly dependsOn: readonly ['AN-SLICE-001'];
    readonly deliverables: readonly ['article view', 'CTA impression/click', 'comparison', 'RUM'];
    readonly implementationStatus: 'NOT_STARTED';
    readonly runtimeVerification: 'NOT_EXECUTED';
  };
  readonly eventRequirements: readonly PublicEventInstrumentationEventRequirement[];
  readonly privacy: {
    readonly decisionId: 'OD-012';
    readonly decisionStatus: 'HUMAN_DECISION_REQUIRED';
    readonly blocking: true;
    readonly safeDefault: 'NONESSENTIAL_TRACKING_DISABLED';
    readonly firstPartyMinimalEventEligibility: 'NOT_EVALUATED';
    readonly consentState: 'NOT_EVALUATED';
    readonly consentInferred: false;
    readonly sessionPseudonym: null;
    readonly cookiesUsed: false;
    readonly storageUsed: false;
    readonly fingerprintingUsed: false;
    readonly trackingEnabled: false;
    readonly eventEmissionAllowed: false;
  };
  readonly navigation: {
    readonly directProviderNavigationRequired: true;
    readonly raosRedirectAllowed: false;
    readonly navigationMustNotWaitForInstrumentation: true;
    readonly collectorFailureMustNotBlockNavigation: true;
    readonly navigationExecuted: false;
    readonly beaconExecuted: false;
    readonly browserVerified: false;
    readonly selectedTransport: null;
  };
  readonly boundaries: PublicEventInstrumentationBoundaries;
  readonly authorization: {
    readonly approval: false;
    readonly publication: false;
    readonly release: false;
    readonly production: false;
    readonly formalEvidence: false;
  };
  readonly events: readonly [];
  readonly actions: readonly [];
  readonly effects: readonly [];
}

const LOWER_SHA256 = /^[0-9a-f]{64}$/;

function reject(code: PublicEventInstrumentationErrorCode): never {
  throw new PublicEventInstrumentationError(code);
}

function isJsonObject(value: unknown): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function hasExactKeys(value: JsonObject, keys: readonly string[]): boolean {
  const observed = Object.keys(value);
  return observed.length === keys.length && keys.every((key) => observed.includes(key));
}

function cloneObject(value: unknown, code: PublicEventInstrumentationErrorCode): JsonObject {
  try {
    const cloned = createJsonValue(value);
    if (!isJsonObject(cloned)) return reject(code);
    return cloned;
  } catch (error) {
    if (error instanceof PublicEventInstrumentationError) throw error;
    return reject(code);
  }
}

function validateInput(value: unknown): PublicEventInstrumentationInput {
  const input = cloneObject(value, 'PUBLIC_EVENT_INSTRUMENTATION_INPUT_INVALID');
  if (!hasExactKeys(input, ['screenId', 'route', 'coordinate'])) {
    return reject('PUBLIC_EVENT_INSTRUMENTATION_INPUT_INVALID');
  }
  if (input['screenId'] !== 'PUB-003') {
    return reject('PUBLIC_EVENT_INSTRUMENTATION_SCREEN_INVALID');
  }
  if (input['route'] !== '/articles/{slug}') {
    return reject('PUBLIC_EVENT_INSTRUMENTATION_ROUTE_INVALID');
  }
  const coordinate = input['coordinate'];
  if (
    !isJsonObject(coordinate) ||
    !hasExactKeys(coordinate, ['kind', 'expectedSha256', 'observedSha256']) ||
    coordinate['kind'] !== 'SYNTHETIC_ST1202_INSTRUMENTATION_REQUIREMENTS_FIXTURE'
  ) {
    return reject('PUBLIC_EVENT_INSTRUMENTATION_COORDINATE_INVALID');
  }
  const expectedSha256 = coordinate['expectedSha256'];
  const observedSha256 = coordinate['observedSha256'];
  if (
    typeof expectedSha256 !== 'string' ||
    typeof observedSha256 !== 'string' ||
    !LOWER_SHA256.test(expectedSha256) ||
    !LOWER_SHA256.test(observedSha256)
  ) {
    return reject('PUBLIC_EVENT_INSTRUMENTATION_HASH_INVALID');
  }
  if (expectedSha256 !== observedSha256) {
    return reject('PUBLIC_EVENT_INSTRUMENTATION_HASH_MISMATCH');
  }
  return {
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: {
      kind: 'SYNTHETIC_ST1202_INSTRUMENTATION_REQUIREMENTS_FIXTURE',
      expectedSha256,
      observedSha256,
    },
  };
}

const notEvaluated = (): PublicEventInstrumentationUnknownValue => ({
  state: 'NOT_EVALUATED',
  value: null,
});

const eventSources = [
  {
    id: 'EVT-001',
    eventName: 'article_view',
    purpose: '承認済み記事閲覧',
    parameters: [
      'event_id',
      'occurred_at',
      'anonymous_session_id',
      'article_id',
      'snapshot_id',
      'category_id',
      'referrer_class',
      'consent_state',
    ],
  },
  {
    id: 'EVT-002',
    eventName: 'qualified_decision_engagement',
    purpose: '比較/選び方への有意な関与',
    parameters: ['article_id', 'snapshot_id', 'component_type', 'engagement_kind'],
  },
  {
    id: 'EVT-003',
    eventName: 'affiliate_cta_impression',
    purpose: 'CTAがViewportに表示',
    parameters: [
      'article_id',
      'snapshot_id',
      'cta_id',
      'offer_id',
      'placement',
      'visibility_threshold',
    ],
  },
  {
    id: 'EVT-004',
    eventName: 'affiliate_click',
    purpose: '楽天CTAクリック',
    parameters: [
      'article_id',
      'snapshot_id',
      'cta_id',
      'offer_id',
      'placement',
      'beacon_transport',
      'consent_state',
    ],
  },
  {
    id: 'EVT-006',
    eventName: 'comparison_interaction',
    purpose: '比較表の展開/Sort/Filter',
    parameters: ['article_id', 'snapshot_id', 'interaction', 'axis_code'],
  },
  {
    id: 'EVT-012',
    eventName: 'web_vital',
    purpose: 'RUM性能',
    parameters: [
      'article_id',
      'snapshot_id',
      'metric_name',
      'metric_value',
      'rating',
      'navigation_type',
    ],
  },
] as const;

function eventRequirements(): readonly PublicEventInstrumentationEventRequirement[] {
  return eventSources.map((event) => ({
    ...event,
    source: 'public_web' as const,
    mvp: true as const,
    parameters: [...event.parameters],
    prohibitedParameters: [...PUBLIC_EVENT_INSTRUMENTATION_PROHIBITED_PARAMETERS],
    trigger: notEvaluated(),
    identity: notEvaluated(),
    eventValues: notEvaluated(),
    threshold: notEvaluated(),
    transport: notEvaluated(),
    collector: notEvaluated(),
    instrumentationImplemented: false as const,
    emissionEnabled: false as const,
  }));
}

const boundaryReasons = {
  routeRegistered: 'NO_RUNTIME_ROUTE_REGISTERED',
  rendererConnected: 'ST1002_RENDERER_NOT_CONNECTED',
  ctaInstanceAvailable: 'ST1004_CTA_INSTANCE_UNAVAILABLE',
  dom: 'DOM_NOT_IMPLEMENTED',
  react: 'REACT_NOT_IMPLEMENTED',
  next: 'NEXT_RUNTIME_NOT_IMPLEMENTED',
  lifecycleHooks: 'BROWSER_LIFECYCLE_NOT_IMPLEMENTED',
  browser: 'BROWSER_NOT_EXECUTED',
  performanceObserver: 'PERFORMANCE_OBSERVER_NOT_IMPLEMENTED',
  clock: 'CLOCK_NOT_USED',
  randomness: 'RANDOMNESS_NOT_USED',
  cookieAccess: 'COOKIE_ACCESS_NOT_USED',
  storageAccess: 'STORAGE_ACCESS_NOT_USED',
  sendBeacon: 'SEND_BEACON_NOT_SELECTED_OR_EXECUTED',
  fetchKeepalive: 'FETCH_KEEPALIVE_NOT_SELECTED_OR_EXECUTED',
  network: 'NETWORK_NOT_USED',
  publicApiPub004: 'PUB004_NOT_MAPPED_OR_CONNECTED',
  collectorConnected: 'ST1201_RECORDED_COLLECTOR_NOT_CONNECTED',
  eventConstruction: 'EVENT_IDENTITIES_VALUES_AND_TIMES_UNAVAILABLE',
  eventEmission: 'EVENT_EMISSION_DISABLED',
  persistence: 'PERSISTENCE_NOT_EXECUTED',
  durableDedupe: 'DURABLE_DEDUPE_NOT_EXECUTED',
  formalTst022: 'FORMAL_TST_022_NOT_EXECUTED',
  formalTst030: 'FORMAL_TST_030_NOT_EXECUTED',
  live: 'LIVE_NOT_EXECUTED',
  staging: 'STAGING_NOT_EXECUTED',
  release: 'RELEASE_NOT_AUTHORIZED',
  production: 'PRODUCTION_NOT_AUTHORIZED',
} as const;

function boundaries(): PublicEventInstrumentationBoundaries {
  return Object.fromEntries(
    Object.entries(boundaryReasons).map(([name, reason]) => [
      name,
      { value: false, status: 'NOT_EXECUTED', reason },
    ]),
  ) as unknown as PublicEventInstrumentationBoundaries;
}

function buildCandidate(
  input: PublicEventInstrumentationInput,
): PublicEventInstrumentationCandidate {
  const candidate = {
    classification: PUBLIC_EVENT_INSTRUMENTATION_CLASSIFICATION,
    screen: PUBLIC_EVENT_INSTRUMENTATION_SCREEN,
    route: {
      template: '/articles/{slug}',
      registered: false,
      rendererConnected: false,
      interactive: false,
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
      instrumentationVerified: false,
      runtimeVerified: false,
      formalEvidence: false,
    },
    slice: {
      id: 'AN-SLICE-002',
      name: 'Public event instrumentation',
      dependsOn: ['AN-SLICE-001'],
      deliverables: ['article view', 'CTA impression/click', 'comparison', 'RUM'],
      implementationStatus: 'NOT_STARTED',
      runtimeVerification: 'NOT_EXECUTED',
    },
    eventRequirements: eventRequirements(),
    privacy: {
      decisionId: 'OD-012',
      decisionStatus: 'HUMAN_DECISION_REQUIRED',
      blocking: true,
      safeDefault: 'NONESSENTIAL_TRACKING_DISABLED',
      firstPartyMinimalEventEligibility: 'NOT_EVALUATED',
      consentState: 'NOT_EVALUATED',
      consentInferred: false,
      sessionPseudonym: null,
      cookiesUsed: false,
      storageUsed: false,
      fingerprintingUsed: false,
      trackingEnabled: false,
      eventEmissionAllowed: false,
    },
    navigation: {
      directProviderNavigationRequired: true,
      raosRedirectAllowed: false,
      navigationMustNotWaitForInstrumentation: true,
      collectorFailureMustNotBlockNavigation: true,
      navigationExecuted: false,
      beaconExecuted: false,
      browserVerified: false,
      selectedTransport: null,
    },
    boundaries: boundaries(),
    authorization: {
      approval: false,
      publication: false,
      release: false,
      production: false,
      formalEvidence: false,
    },
    events: [],
    actions: [],
    effects: [],
  } as const;
  return createJsonValue(candidate) as unknown as PublicEventInstrumentationCandidate;
}

function jsonEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function inputFromCandidate(value: JsonObject): PublicEventInstrumentationInput {
  const screen = value['screen'];
  const coordinate = value['coordinate'];
  if (!isJsonObject(screen) || !isJsonObject(coordinate)) {
    return reject('PUBLIC_EVENT_INSTRUMENTATION_CANDIDATE_INVALID');
  }
  return validateInput({
    screenId: screen['id'],
    route: screen['route'],
    coordinate,
  });
}

function classifyCandidateFailure(
  value: JsonObject,
  expected: PublicEventInstrumentationCandidate,
): PublicEventInstrumentationErrorCode {
  if (
    !jsonEqual(value['screen'], expected.screen) ||
    !jsonEqual(value['route'], expected.route) ||
    !jsonEqual(value['coordinate'], expected.coordinate) ||
    !jsonEqual(value['hashBinding'], expected.hashBinding)
  ) {
    return 'PUBLIC_EVENT_INSTRUMENTATION_METADATA_INVALID';
  }
  if (
    !jsonEqual(value['slice'], expected.slice) ||
    !jsonEqual(value['eventRequirements'], expected.eventRequirements)
  ) {
    return 'PUBLIC_EVENT_INSTRUMENTATION_REQUIREMENTS_INVALID';
  }
  if (!jsonEqual(value['privacy'], expected.privacy)) {
    return 'PUBLIC_EVENT_INSTRUMENTATION_PRIVACY_INVALID';
  }
  if (
    !jsonEqual(value['navigation'], expected.navigation) ||
    !jsonEqual(value['boundaries'], expected.boundaries) ||
    !jsonEqual(value['events'], expected.events) ||
    !jsonEqual(value['actions'], expected.actions) ||
    !jsonEqual(value['effects'], expected.effects)
  ) {
    return 'PUBLIC_EVENT_INSTRUMENTATION_RUNTIME_PROHIBITED';
  }
  if (!jsonEqual(value['authorization'], expected.authorization)) {
    return 'PUBLIC_EVENT_INSTRUMENTATION_AUTHORITY_INVALID';
  }
  return 'PUBLIC_EVENT_INSTRUMENTATION_CANDIDATE_INVALID';
}

export function validatePublicEventInstrumentationCandidate(
  value: unknown,
): PublicEventInstrumentationCandidate {
  const clone = cloneObject(value, 'PUBLIC_EVENT_INSTRUMENTATION_CANDIDATE_INVALID');
  let expected: PublicEventInstrumentationCandidate;
  try {
    expected = buildCandidate(inputFromCandidate(clone));
  } catch (error) {
    if (error instanceof PublicEventInstrumentationError) throw error;
    return reject('PUBLIC_EVENT_INSTRUMENTATION_CANDIDATE_INVALID');
  }
  if (!jsonEqual(clone, expected)) {
    return reject(classifyCandidateFailure(clone, expected));
  }
  return clone as unknown as PublicEventInstrumentationCandidate;
}

export function createPublicEventInstrumentationCandidate(
  input: PublicEventInstrumentationInput,
): PublicEventInstrumentationCandidate {
  return buildCandidate(validateInput(input));
}

// V2 is additive. The V1 disabled requirements candidate above remains byte-for-byte
// compatible; this local runtime adds only a deterministic, process-local recorded seam.
export const PUBLIC_EVENT_INSTRUMENTATION_CLASSIFICATION_V2 =
  'LOCAL_DEFAULT_DISABLED_PROCESS_LOCAL_RECORDED_PUBLIC_EVENT_INSTRUMENTATION_V2' as const;

export const PUBLIC_EVENT_INSTRUMENTATION_EVENT_IDS_V2 = Object.freeze([
  'EVT-001',
  'EVT-002',
  'EVT-003',
  'EVT-004',
  'EVT-006',
  'EVT-012',
] as const);

export type PublicEventInstrumentationEventIdV2 =
  (typeof PUBLIC_EVENT_INSTRUMENTATION_EVENT_IDS_V2)[number];

export const PUBLIC_EVENT_INSTRUMENTATION_EVENT_NAMES_V2 = Object.freeze([
  'article_view',
  'qualified_decision_engagement',
  'affiliate_cta_impression',
  'affiliate_click',
  'comparison_interaction',
  'web_vital',
] as const);

export type PublicEventInstrumentationEventNameV2 =
  (typeof PUBLIC_EVENT_INSTRUMENTATION_EVENT_NAMES_V2)[number];

export const PUBLIC_EVENT_INSTRUMENTATION_ERROR_CODES_V2 = Object.freeze([
  'PUBLIC_INSTRUMENTATION_V2_INPUT_INVALID',
  'PUBLIC_INSTRUMENTATION_V2_ROUTE_CONTEXT_INVALID',
  'PUBLIC_INSTRUMENTATION_V2_MODE_INVALID',
  'PUBLIC_INSTRUMENTATION_V2_CONSENT_INVALID',
  'PUBLIC_INSTRUMENTATION_V2_EVENT_SCHEMA_INVALID',
  'PUBLIC_INSTRUMENTATION_V2_EVENT_IDENTITY_INVALID',
  'PUBLIC_INSTRUMENTATION_V2_EVENT_PARAMETER_INVALID',
  'PUBLIC_INSTRUMENTATION_V2_PII_FORBIDDEN',
  'PUBLIC_INSTRUMENTATION_V2_EVENT_NOT_ALLOWED',
  'PUBLIC_INSTRUMENTATION_V2_EVENT_ID_CONFLICT',
  'PUBLIC_INSTRUMENTATION_V2_RECORDED_SCRIPT_MISMATCH',
  'PUBLIC_INSTRUMENTATION_V2_RECORDED_SCRIPT_EXHAUSTED',
  'PUBLIC_INSTRUMENTATION_V2_RECORDED_FAILURE',
  'PUBLIC_INSTRUMENTATION_V2_RECORDER_INVALID',
] as const);

export type PublicEventInstrumentationErrorCodeV2 =
  (typeof PUBLIC_EVENT_INSTRUMENTATION_ERROR_CODES_V2)[number];

export class PublicEventInstrumentationErrorV2 extends TypeError {
  readonly code: PublicEventInstrumentationErrorCodeV2;

  constructor(code: PublicEventInstrumentationErrorCodeV2) {
    super(code);
    this.name = 'PublicEventInstrumentationErrorV2';
    this.code = code;
    Object.freeze(this);
  }
}

export interface PublicEventInstrumentationRouteContextInputV2 {
  readonly schemaVersion: 2;
  readonly screenId: 'PUB-003';
  readonly routePath: '/articles/synthetic-recorded-policy-seo';
  readonly sourceProfile: 'EXACT_ST1002_RECORDED_PUBLIC_ARTICLE_V2';
  readonly identities: {
    readonly articleId: null;
    readonly snapshotId: null;
    readonly categoryId: null;
  };
  readonly affiliateCta: {
    readonly state: 'UNAVAILABLE_SOURCE';
    readonly ctaId: null;
    readonly offerId: null;
    readonly rendered: false;
  };
}

export interface PublicEventInstrumentationRouteBoundaryV2 {
  readonly schemaVersion: 2;
  readonly storyId: 'ST-1202';
  readonly classification: typeof PUBLIC_EVENT_INSTRUMENTATION_CLASSIFICATION_V2;
  readonly screenId: 'PUB-003';
  readonly routePath: '/articles/synthetic-recorded-policy-seo';
  readonly sourceProfile: 'EXACT_ST1002_RECORDED_PUBLIC_ARTICLE_V2';
  readonly mode: 'DISABLED_OD_012';
  readonly consentAuthority: 'UNRESOLVED_OD_012';
  readonly safeDefault: 'NONESSENTIAL_TRACKING_DISABLED_FIRST_PARTY_MINIMAL_ONLY';
  readonly serverBoundaryEvaluated: true;
  readonly clientInstrumentationInstalled: false;
  readonly clientComponentCount: 0;
  readonly identityAvailable: false;
  readonly affiliateCtaAvailable: false;
  readonly eligibleEventIds: readonly [];
  readonly blockedEventIds: typeof PUBLIC_EVENT_INSTRUMENTATION_EVENT_IDS_V2;
  readonly events: readonly [];
  readonly effects: readonly [];
  readonly browserStorageUsed: false;
  readonly cookiesUsed: false;
  readonly fingerprintingUsed: false;
  readonly networkUsed: false;
  readonly beaconUsed: false;
  readonly fetchUsed: false;
  readonly providerUsed: false;
  readonly trackingEnabled: false;
  readonly measurementObserved: false;
  readonly reason: 'OD_012_UNRESOLVED_AND_PUBLIC_IDENTITIES_OR_VERIFIED_CTA_UNAVAILABLE';
  readonly authority: {
    readonly publication: false;
    readonly staging: false;
    readonly release: false;
    readonly production: false;
    readonly TST022: 'NOT_EXECUTED';
    readonly TST030: 'NOT_EXECUTED';
  };
}

export type PublicEventInstrumentationParameterScalarV2 = string | number | boolean;

export interface PublicEventInstrumentationParameterV2 {
  readonly name: string;
  readonly value: PublicEventInstrumentationParameterScalarV2;
}

export interface PublicEventInstrumentationEnvelopeV2 {
  readonly catalogId: PublicEventInstrumentationEventIdV2;
  readonly eventId: string;
  readonly eventName: PublicEventInstrumentationEventNameV2;
  readonly schemaVersion: '1.0';
  readonly occurredAt: string;
  readonly receivedAt: string;
  readonly source: 'public_web';
  readonly siteId: string;
  readonly correlationId: string;
  readonly parameters: readonly PublicEventInstrumentationParameterV2[];
}

export interface PublicEventInstrumentationRecordedConsentV2 {
  readonly fixtureKind: 'SYNTHETIC_ST1202_RECORDED_FULL_CONSENT_FIXTURE';
  readonly consentState: 'GRANTED';
  readonly privacyMode: 'FULL_CONSENT';
  readonly authority: 'UNRESOLVED_OD_012';
  readonly trackingActivation: 'DISABLED';
}

export interface PublicEventInstrumentationRecordedFixtureV2 {
  readonly kind: 'SYNTHETIC_ST1202_RECORDED_INSTRUMENTATION_FIXTURE';
  readonly mode: 'RECORDED_TEST_ONLY';
  readonly consent: PublicEventInstrumentationRecordedConsentV2;
  readonly events: readonly PublicEventInstrumentationEnvelopeV2[];
  readonly faultEventIds: readonly string[];
}

export type PublicEventInstrumentationRecordedDispositionV2 =
  'RECORDED_ACCEPTED' | 'RECORDED_DUPLICATE' | 'DROPPED_LOCAL_FAILURE';

export interface PublicEventInstrumentationRecordedResultV2 {
  readonly eventIdentity: null | {
    readonly catalogId: PublicEventInstrumentationEventIdV2;
    readonly eventId: string;
    readonly eventName: PublicEventInstrumentationEventNameV2;
  };
  readonly disposition: PublicEventInstrumentationRecordedDispositionV2;
  readonly execution: 'RECORDED_TEST_ONLY';
  readonly trackingActivation: 'DISABLED';
  readonly persistence: 'NOT_EXECUTED';
  readonly consentAuthority: 'UNRESOLVED_OD_012';
  readonly measurementObserved: false;
  readonly navigationBlocked: false;
  readonly navigationAwaitedInstrumentation: false;
  readonly networkUsed: false;
  readonly browserStorageUsed: false;
  readonly TST022: 'NOT_EXECUTED';
  readonly TST030: 'NOT_EXECUTED';
  readonly failureReason: null | 'RECORDED_FAILURE_SWALLOWED';
}

export interface PublicEventInstrumentationRecorderSnapshotV2 {
  readonly mode: 'RECORDED_TEST_ONLY';
  readonly scriptLength: 6;
  readonly nextIndex: number;
  readonly remaining: number;
  readonly acceptedCount: number;
  readonly duplicateCount: number;
  readonly swallowedFailureCount: number;
  readonly complete: boolean;
  readonly trackingActivation: 'DISABLED';
  readonly persistence: 'NOT_EXECUTED';
  readonly measurementObserved: false;
}

const V2_UUID7 = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const V2_UTC_TIMESTAMP = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{3})Z$/;
const V2_SAFE_TEXT = /^[ -~]+$/;
const V2_EMAIL = /[^@\s]+@[^@\s]+\.[^@\s]+/;
const V2_PHONE = /^\+?[0-9][0-9 ()-]{8,}[0-9]$/;
const V2_IPV4 = /^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/;
const V2_IPV6 = /^(?:[0-9a-f]*:){2,}[0-9a-f:]*$/i;
const V2_ACTIVE_OR_SENSITIVE_TEXT =
  /^(?:(?:https?|ftp|file|mailto|tel|javascript|data|vbscript):|\/\/)|(?:api[_-]?key|apikey|password|secret|token)=|mozilla\//i;
const V2_ID_PARAMETER_NAMES = new Set([
  'article_id',
  'snapshot_id',
  'category_id',
  'cta_id',
  'offer_id',
]);

const V2_EVENT_DEFINITIONS = [
  {
    catalogId: 'EVT-001',
    eventName: 'article_view',
    parameters: [
      'anonymous_session_id',
      'article_id',
      'snapshot_id',
      'category_id',
      'referrer_class',
      'consent_state',
    ],
  },
  {
    catalogId: 'EVT-002',
    eventName: 'qualified_decision_engagement',
    parameters: ['article_id', 'snapshot_id', 'component_type', 'engagement_kind'],
  },
  {
    catalogId: 'EVT-003',
    eventName: 'affiliate_cta_impression',
    parameters: [
      'article_id',
      'snapshot_id',
      'cta_id',
      'offer_id',
      'placement',
      'visibility_threshold',
    ],
  },
  {
    catalogId: 'EVT-004',
    eventName: 'affiliate_click',
    parameters: [
      'article_id',
      'snapshot_id',
      'cta_id',
      'offer_id',
      'placement',
      'beacon_transport',
      'consent_state',
    ],
  },
  {
    catalogId: 'EVT-006',
    eventName: 'comparison_interaction',
    parameters: ['article_id', 'snapshot_id', 'interaction', 'axis_code'],
  },
  {
    catalogId: 'EVT-012',
    eventName: 'web_vital',
    parameters: [
      'article_id',
      'snapshot_id',
      'metric_name',
      'metric_value',
      'rating',
      'navigation_type',
    ],
  },
] as const;

function rejectV2(code: PublicEventInstrumentationErrorCodeV2): never {
  throw new PublicEventInstrumentationErrorV2(code);
}

function cloneObjectV2(value: unknown, code: PublicEventInstrumentationErrorCodeV2): JsonObject {
  try {
    const clone = createJsonValue(value);
    if (!isJsonObject(clone)) return rejectV2(code);
    return clone;
  } catch (error) {
    if (error instanceof PublicEventInstrumentationErrorV2) throw error;
    return rejectV2(code);
  }
}

function requireExactKeysV2(
  value: JsonObject,
  keys: readonly string[],
  code: PublicEventInstrumentationErrorCodeV2,
): void {
  if (!hasExactKeys(value, keys)) rejectV2(code);
}

function isLeapYearV2(year: number): boolean {
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
}

function requireUtcTimestampV2(value: unknown): string {
  if (typeof value !== 'string') {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_EVENT_IDENTITY_INVALID');
  }
  const match = V2_UTC_TIMESTAMP.exec(value);
  if (match === null) {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_EVENT_IDENTITY_INVALID');
  }
  const parts = match.slice(1).map(Number);
  const [year, month, day, hour, minute, second] = parts;
  if (
    year === undefined ||
    month === undefined ||
    day === undefined ||
    hour === undefined ||
    minute === undefined ||
    second === undefined
  ) {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_EVENT_IDENTITY_INVALID');
  }
  const days = [31, isLeapYearV2(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (
    year < 2000 ||
    year > 9999 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > (days[month - 1] ?? 0) ||
    hour > 23 ||
    minute > 59 ||
    second > 59
  ) {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_EVENT_IDENTITY_INVALID');
  }
  return value;
}

function requireUuid7V2(value: unknown): string {
  if (typeof value !== 'string' || !V2_UUID7.test(value)) {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_EVENT_IDENTITY_INVALID');
  }
  return value;
}

function looksSensitiveV2(value: string): boolean {
  const digits = [...value].filter((character) => /[0-9]/.test(character)).length;
  return (
    V2_EMAIL.test(value) ||
    (V2_PHONE.test(value) && digits >= 10) ||
    V2_IPV4.test(value) ||
    V2_IPV6.test(value) ||
    V2_ACTIVE_OR_SENSITIVE_TEXT.test(value) ||
    value.includes('?') ||
    value.includes('#')
  );
}

function requireSafeParameterValueV2(
  name: string,
  value: unknown,
): PublicEventInstrumentationParameterScalarV2 {
  if (PUBLIC_EVENT_INSTRUMENTATION_PROHIBITED_PARAMETERS.includes(name as never)) {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_PII_FORBIDDEN');
  }
  if (name === 'visibility_threshold' || name === 'metric_value') {
    if (
      typeof value !== 'number' ||
      !Number.isFinite(value) ||
      value < 0 ||
      (name === 'visibility_threshold' && value > 1)
    ) {
      return rejectV2('PUBLIC_INSTRUMENTATION_V2_EVENT_PARAMETER_INVALID');
    }
    return Object.is(value, -0) ? 0 : value;
  }
  if (typeof value !== 'string') {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_EVENT_PARAMETER_INVALID');
  }
  if (
    value.length < 1 ||
    value.length > 512 ||
    value !== value.trim() ||
    !V2_SAFE_TEXT.test(value) ||
    looksSensitiveV2(value)
  ) {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_PII_FORBIDDEN');
  }
  if (V2_ID_PARAMETER_NAMES.has(name)) requireUuid7V2(value);
  if (name === 'consent_state' && value !== 'GRANTED') {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_CONSENT_INVALID');
  }
  if (name === 'beacon_transport' && value !== 'RECORDED_NOT_EXECUTED') {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_EVENT_PARAMETER_INVALID');
  }
  return value;
}

function definitionForV2(
  catalogId: unknown,
  eventName: unknown,
): (typeof V2_EVENT_DEFINITIONS)[number] {
  const matches = V2_EVENT_DEFINITIONS.filter(
    (definition) => definition.catalogId === catalogId && definition.eventName === eventName,
  );
  if (matches.length !== 1) {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_EVENT_NOT_ALLOWED');
  }
  return matches[0] as (typeof V2_EVENT_DEFINITIONS)[number];
}

export function validatePublicEventInstrumentationEnvelopeV2(
  value: unknown,
): PublicEventInstrumentationEnvelopeV2 {
  const input = cloneObjectV2(value, 'PUBLIC_INSTRUMENTATION_V2_EVENT_SCHEMA_INVALID');
  requireExactKeysV2(
    input,
    [
      'catalogId',
      'eventId',
      'eventName',
      'schemaVersion',
      'occurredAt',
      'receivedAt',
      'source',
      'siteId',
      'correlationId',
      'parameters',
    ],
    'PUBLIC_INSTRUMENTATION_V2_EVENT_SCHEMA_INVALID',
  );
  if (input['schemaVersion'] !== '1.0' || input['source'] !== 'public_web') {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_EVENT_SCHEMA_INVALID');
  }
  const definition = definitionForV2(input['catalogId'], input['eventName']);
  const eventId = requireUuid7V2(input['eventId']);
  const siteId = requireUuid7V2(input['siteId']);
  const correlationId = requireUuid7V2(input['correlationId']);
  const occurredAt = requireUtcTimestampV2(input['occurredAt']);
  const receivedAt = requireUtcTimestampV2(input['receivedAt']);
  if (receivedAt < occurredAt) {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_EVENT_IDENTITY_INVALID');
  }
  const parameters = input['parameters'];
  if (!Array.isArray(parameters) || parameters.length !== definition.parameters.length) {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_EVENT_PARAMETER_INVALID');
  }
  const normalizedParameters = parameters.map((parameter, index) => {
    if (!isJsonObject(parameter)) {
      return rejectV2('PUBLIC_INSTRUMENTATION_V2_EVENT_PARAMETER_INVALID');
    }
    requireExactKeysV2(
      parameter,
      ['name', 'value'],
      'PUBLIC_INSTRUMENTATION_V2_EVENT_PARAMETER_INVALID',
    );
    const expectedName = definition.parameters[index];
    const observedName = parameter['name'];
    if (
      typeof observedName === 'string' &&
      PUBLIC_EVENT_INSTRUMENTATION_PROHIBITED_PARAMETERS.includes(observedName as never)
    ) {
      return rejectV2('PUBLIC_INSTRUMENTATION_V2_PII_FORBIDDEN');
    }
    if (observedName !== expectedName || typeof expectedName !== 'string') {
      return rejectV2('PUBLIC_INSTRUMENTATION_V2_EVENT_PARAMETER_INVALID');
    }
    return {
      name: expectedName,
      value: requireSafeParameterValueV2(expectedName, parameter['value']),
    };
  });
  const normalized = {
    catalogId: definition.catalogId,
    eventId,
    eventName: definition.eventName,
    schemaVersion: '1.0' as const,
    occurredAt,
    receivedAt,
    source: 'public_web' as const,
    siteId,
    correlationId,
    parameters: normalizedParameters,
  };
  return createJsonValue(normalized) as unknown as PublicEventInstrumentationEnvelopeV2;
}

function validateRecordedConsentV2(value: unknown): PublicEventInstrumentationRecordedConsentV2 {
  const consent = cloneObjectV2(value, 'PUBLIC_INSTRUMENTATION_V2_CONSENT_INVALID');
  requireExactKeysV2(
    consent,
    ['fixtureKind', 'consentState', 'privacyMode', 'authority', 'trackingActivation'],
    'PUBLIC_INSTRUMENTATION_V2_CONSENT_INVALID',
  );
  if (
    consent['fixtureKind'] !== 'SYNTHETIC_ST1202_RECORDED_FULL_CONSENT_FIXTURE' ||
    consent['consentState'] !== 'GRANTED' ||
    consent['privacyMode'] !== 'FULL_CONSENT' ||
    consent['authority'] !== 'UNRESOLVED_OD_012' ||
    consent['trackingActivation'] !== 'DISABLED'
  ) {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_CONSENT_INVALID');
  }
  return consent as unknown as PublicEventInstrumentationRecordedConsentV2;
}

export function validatePublicEventInstrumentationRecordedFixtureV2(
  value: unknown,
): PublicEventInstrumentationRecordedFixtureV2 {
  const input = cloneObjectV2(value, 'PUBLIC_INSTRUMENTATION_V2_INPUT_INVALID');
  requireExactKeysV2(
    input,
    ['kind', 'mode', 'consent', 'events', 'faultEventIds'],
    'PUBLIC_INSTRUMENTATION_V2_INPUT_INVALID',
  );
  if (
    input['kind'] !== 'SYNTHETIC_ST1202_RECORDED_INSTRUMENTATION_FIXTURE' ||
    input['mode'] !== 'RECORDED_TEST_ONLY'
  ) {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_MODE_INVALID');
  }
  const consent = validateRecordedConsentV2(input['consent']);
  if (!Array.isArray(input['events']) || input['events'].length !== 6) {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_RECORDED_SCRIPT_MISMATCH');
  }
  const events = input['events'].map((event) =>
    validatePublicEventInstrumentationEnvelopeV2(event),
  );
  if (
    events.some(
      (event, index) =>
        event.catalogId !== PUBLIC_EVENT_INSTRUMENTATION_EVENT_IDS_V2[index] ||
        event.eventName !== PUBLIC_EVENT_INSTRUMENTATION_EVENT_NAMES_V2[index],
    ) ||
    new Set(events.map((event) => event.eventId)).size !== events.length
  ) {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_RECORDED_SCRIPT_MISMATCH');
  }
  const faultEventIds = input['faultEventIds'];
  if (!Array.isArray(faultEventIds)) {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_RECORDED_SCRIPT_MISMATCH');
  }
  const scriptIds = events.map((event) => event.eventId);
  if (
    faultEventIds.some(
      (eventId, index) =>
        typeof eventId !== 'string' ||
        !scriptIds.includes(eventId) ||
        faultEventIds.indexOf(eventId) !== index,
    ) ||
    scriptIds.filter((eventId) => faultEventIds.includes(eventId)).join('|') !==
      faultEventIds.join('|')
  ) {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_RECORDED_SCRIPT_MISMATCH');
  }
  return createJsonValue({
    kind: 'SYNTHETIC_ST1202_RECORDED_INSTRUMENTATION_FIXTURE',
    mode: 'RECORDED_TEST_ONLY',
    consent,
    events,
    faultEventIds,
  }) as unknown as PublicEventInstrumentationRecordedFixtureV2;
}

export function createDisabledPublicEventInstrumentationRouteBoundaryV2(
  value: PublicEventInstrumentationRouteContextInputV2,
): PublicEventInstrumentationRouteBoundaryV2 {
  const input = cloneObjectV2(value, 'PUBLIC_INSTRUMENTATION_V2_ROUTE_CONTEXT_INVALID');
  requireExactKeysV2(
    input,
    ['schemaVersion', 'screenId', 'routePath', 'sourceProfile', 'identities', 'affiliateCta'],
    'PUBLIC_INSTRUMENTATION_V2_ROUTE_CONTEXT_INVALID',
  );
  const identities = input['identities'];
  const affiliateCta = input['affiliateCta'];
  if (!isJsonObject(identities) || !isJsonObject(affiliateCta)) {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_ROUTE_CONTEXT_INVALID');
  }
  requireExactKeysV2(
    identities,
    ['articleId', 'snapshotId', 'categoryId'],
    'PUBLIC_INSTRUMENTATION_V2_ROUTE_CONTEXT_INVALID',
  );
  requireExactKeysV2(
    affiliateCta,
    ['state', 'ctaId', 'offerId', 'rendered'],
    'PUBLIC_INSTRUMENTATION_V2_ROUTE_CONTEXT_INVALID',
  );
  if (
    input['schemaVersion'] !== 2 ||
    input['screenId'] !== 'PUB-003' ||
    input['routePath'] !== '/articles/synthetic-recorded-policy-seo' ||
    input['sourceProfile'] !== 'EXACT_ST1002_RECORDED_PUBLIC_ARTICLE_V2' ||
    identities['articleId'] !== null ||
    identities['snapshotId'] !== null ||
    identities['categoryId'] !== null ||
    affiliateCta['state'] !== 'UNAVAILABLE_SOURCE' ||
    affiliateCta['ctaId'] !== null ||
    affiliateCta['offerId'] !== null ||
    affiliateCta['rendered'] !== false
  ) {
    return rejectV2('PUBLIC_INSTRUMENTATION_V2_ROUTE_CONTEXT_INVALID');
  }
  const boundary = {
    schemaVersion: 2,
    storyId: 'ST-1202',
    classification: PUBLIC_EVENT_INSTRUMENTATION_CLASSIFICATION_V2,
    screenId: 'PUB-003',
    routePath: '/articles/synthetic-recorded-policy-seo',
    sourceProfile: 'EXACT_ST1002_RECORDED_PUBLIC_ARTICLE_V2',
    mode: 'DISABLED_OD_012',
    consentAuthority: 'UNRESOLVED_OD_012',
    safeDefault: 'NONESSENTIAL_TRACKING_DISABLED_FIRST_PARTY_MINIMAL_ONLY',
    serverBoundaryEvaluated: true,
    clientInstrumentationInstalled: false,
    clientComponentCount: 0,
    identityAvailable: false,
    affiliateCtaAvailable: false,
    eligibleEventIds: [],
    blockedEventIds: [...PUBLIC_EVENT_INSTRUMENTATION_EVENT_IDS_V2],
    events: [],
    effects: [],
    browserStorageUsed: false,
    cookiesUsed: false,
    fingerprintingUsed: false,
    networkUsed: false,
    beaconUsed: false,
    fetchUsed: false,
    providerUsed: false,
    trackingEnabled: false,
    measurementObserved: false,
    reason: 'OD_012_UNRESOLVED_AND_PUBLIC_IDENTITIES_OR_VERIFIED_CTA_UNAVAILABLE',
    authority: {
      publication: false,
      staging: false,
      release: false,
      production: false,
      TST022: 'NOT_EXECUTED',
      TST030: 'NOT_EXECUTED',
    },
  } as const;
  return createJsonValue(boundary) as unknown as PublicEventInstrumentationRouteBoundaryV2;
}

function canonicalEventV2(event: PublicEventInstrumentationEnvelopeV2): string {
  return JSON.stringify(event);
}

function recordedResultV2(
  event: PublicEventInstrumentationEnvelopeV2,
  disposition: PublicEventInstrumentationRecordedDispositionV2,
): PublicEventInstrumentationRecordedResultV2 {
  const dropped = disposition === 'DROPPED_LOCAL_FAILURE';
  return createJsonValue({
    eventIdentity: {
      catalogId: event.catalogId,
      eventId: event.eventId,
      eventName: event.eventName,
    },
    disposition,
    execution: 'RECORDED_TEST_ONLY',
    trackingActivation: 'DISABLED',
    persistence: 'NOT_EXECUTED',
    consentAuthority: 'UNRESOLVED_OD_012',
    measurementObserved: false,
    navigationBlocked: false,
    navigationAwaitedInstrumentation: false,
    networkUsed: false,
    browserStorageUsed: false,
    TST022: 'NOT_EXECUTED',
    TST030: 'NOT_EXECUTED',
    failureReason: dropped ? 'RECORDED_FAILURE_SWALLOWED' : null,
  }) as unknown as PublicEventInstrumentationRecordedResultV2;
}

const RECORDER_V2_TOKEN = Object.freeze({ storyId: 'ST-1202' });

export class RecordedPublicEventInstrumentationV2 {
  readonly #events: readonly PublicEventInstrumentationEnvelopeV2[];
  readonly #faultEventIds: ReadonlySet<string>;
  readonly #seen = new Map<string, string>();
  #nextIndex = 0;
  #acceptedCount = 0;
  #duplicateCount = 0;
  #swallowedFailureCount = 0;

  private constructor(
    token: typeof RECORDER_V2_TOKEN,
    fixture: PublicEventInstrumentationRecordedFixtureV2,
  ) {
    if (token !== RECORDER_V2_TOKEN) {
      rejectV2('PUBLIC_INSTRUMENTATION_V2_RECORDER_INVALID');
    }
    this.#events = fixture.events;
    this.#faultEventIds = new Set(fixture.faultEventIds);
    Object.freeze(this);
  }

  static create(
    value: PublicEventInstrumentationRecordedFixtureV2,
  ): RecordedPublicEventInstrumentationV2 {
    return new RecordedPublicEventInstrumentationV2(
      RECORDER_V2_TOKEN,
      validatePublicEventInstrumentationRecordedFixtureV2(value),
    );
  }

  record(value: PublicEventInstrumentationEnvelopeV2): PublicEventInstrumentationRecordedResultV2 {
    const event = validatePublicEventInstrumentationEnvelopeV2(value);
    const canonical = canonicalEventV2(event);
    const prior = this.#seen.get(event.eventId);
    if (prior !== undefined) {
      if (prior !== canonical) {
        return rejectV2('PUBLIC_INSTRUMENTATION_V2_EVENT_ID_CONFLICT');
      }
      this.#duplicateCount += 1;
      return recordedResultV2(event, 'RECORDED_DUPLICATE');
    }
    const expected = this.#events[this.#nextIndex];
    if (expected === undefined) {
      return rejectV2('PUBLIC_INSTRUMENTATION_V2_RECORDED_SCRIPT_EXHAUSTED');
    }
    if (canonicalEventV2(expected) !== canonical) {
      return rejectV2('PUBLIC_INSTRUMENTATION_V2_RECORDED_SCRIPT_MISMATCH');
    }
    if (this.#faultEventIds.has(event.eventId)) {
      return rejectV2('PUBLIC_INSTRUMENTATION_V2_RECORDED_FAILURE');
    }
    this.#seen.set(event.eventId, canonical);
    this.#nextIndex += 1;
    this.#acceptedCount += 1;
    return recordedResultV2(event, 'RECORDED_ACCEPTED');
  }

  recordSafely(
    value: PublicEventInstrumentationEnvelopeV2,
  ): PublicEventInstrumentationRecordedResultV2 {
    let event: PublicEventInstrumentationEnvelopeV2;
    try {
      event = validatePublicEventInstrumentationEnvelopeV2(value);
      return this.record(event);
    } catch {
      this.#swallowedFailureCount += 1;
      try {
        event = validatePublicEventInstrumentationEnvelopeV2(value);
      } catch {
        return createJsonValue({
          eventIdentity: null,
          disposition: 'DROPPED_LOCAL_FAILURE',
          execution: 'RECORDED_TEST_ONLY',
          trackingActivation: 'DISABLED',
          persistence: 'NOT_EXECUTED',
          consentAuthority: 'UNRESOLVED_OD_012',
          measurementObserved: false,
          navigationBlocked: false,
          navigationAwaitedInstrumentation: false,
          networkUsed: false,
          browserStorageUsed: false,
          TST022: 'NOT_EXECUTED',
          TST030: 'NOT_EXECUTED',
          failureReason: 'RECORDED_FAILURE_SWALLOWED',
        }) as unknown as PublicEventInstrumentationRecordedResultV2;
      }
      return recordedResultV2(event, 'DROPPED_LOCAL_FAILURE');
    }
  }

  snapshot(): PublicEventInstrumentationRecorderSnapshotV2 {
    return createJsonValue({
      mode: 'RECORDED_TEST_ONLY',
      scriptLength: 6,
      nextIndex: this.#nextIndex,
      remaining: this.#events.length - this.#nextIndex,
      acceptedCount: this.#acceptedCount,
      duplicateCount: this.#duplicateCount,
      swallowedFailureCount: this.#swallowedFailureCount,
      complete: this.#nextIndex === this.#events.length,
      trackingActivation: 'DISABLED',
      persistence: 'NOT_EXECUTED',
      measurementObserved: false,
    }) as unknown as PublicEventInstrumentationRecorderSnapshotV2;
  }
}

export function createRecordedPublicEventInstrumentationV2(
  value: PublicEventInstrumentationRecordedFixtureV2,
): RecordedPublicEventInstrumentationV2 {
  return RecordedPublicEventInstrumentationV2.create(value);
}
