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
