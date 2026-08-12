import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const PUBLIC_DISCLOSURE_AFFILIATE_CLASSIFICATION =
  'UNREGISTERED_DISABLED_HEADLESS_ST1004_DISCLOSURE_AFFILIATE_CANDIDATE' as const;

export const PUBLIC_DISCLOSURE_AFFILIATE_COMPONENT_IDS = Object.freeze([
  'UI-C031',
  'UI-C034',
] as const);

export type PublicDisclosureAffiliateComponentId =
  (typeof PUBLIC_DISCLOSURE_AFFILIATE_COMPONENT_IDS)[number];

export const PUBLIC_DISCLOSURE_AFFILIATE_ERROR_CODES = Object.freeze([
  'PUBLIC_DISCLOSURE_INPUT_INVALID',
  'PUBLIC_DISCLOSURE_SCREEN_INVALID',
  'PUBLIC_DISCLOSURE_ROUTE_INVALID',
  'PUBLIC_DISCLOSURE_COORDINATE_INVALID',
  'PUBLIC_DISCLOSURE_HASH_INVALID',
  'PUBLIC_DISCLOSURE_HASH_MISMATCH',
  'PUBLIC_DISCLOSURE_COPY_PROHIBITED',
  'PUBLIC_DISCLOSURE_LINK_VALUE_PROHIBITED',
  'PUBLIC_DISCLOSURE_REFERENCE_PROHIBITED',
  'PUBLIC_DISCLOSURE_INTERNAL_FIELD_PROHIBITED',
  'PUBLIC_DISCLOSURE_EFFECT_PROHIBITED',
  'PUBLIC_DISCLOSURE_METADATA_INVALID',
  'PUBLIC_DISCLOSURE_SEMANTICS_INVALID',
  'PUBLIC_DISCLOSURE_AUTHORITY_INVALID',
  'PUBLIC_DISCLOSURE_CANDIDATE_INVALID',
] as const);

export type PublicDisclosureAffiliateErrorCode =
  (typeof PUBLIC_DISCLOSURE_AFFILIATE_ERROR_CODES)[number];

export class PublicDisclosureAffiliateError extends TypeError {
  readonly code: PublicDisclosureAffiliateErrorCode;

  constructor(code: PublicDisclosureAffiliateErrorCode) {
    super(code);
    this.name = 'PublicDisclosureAffiliateError';
    this.code = code;
    Object.freeze(this);
  }
}

export interface PublicDisclosureAffiliateComponentMetadata {
  readonly id: PublicDisclosureAffiliateComponentId;
  readonly name: 'DisclosureBanner' | 'AffiliateCTA';
  readonly area: 'public';
  readonly purpose: string;
  readonly keyboardRequired: true;
  readonly screenReaderRequired: true;
  readonly designStatus: 'APPROVED_FOR_IMPLEMENTATION';
  readonly implementationStatus: 'NOT_STARTED';
  readonly runtimeVerification: 'NOT_EXECUTED';
}

const componentSource = [
  {
    id: 'UI-C031',
    name: 'DisclosureBanner',
    area: 'public',
    purpose: '広告・Affiliate開示',
    keyboardRequired: true,
    screenReaderRequired: true,
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'UI-C034',
    name: 'AffiliateCTA',
    area: 'public',
    purpose: '楽天遷移を明示しSponsored属性',
    keyboardRequired: true,
    screenReaderRequired: true,
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
] as const;

export const PUBLIC_DISCLOSURE_AFFILIATE_COMPONENTS = createJsonValue(
  componentSource,
) as unknown as readonly PublicDisclosureAffiliateComponentMetadata[];

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

export const PUBLIC_DISCLOSURE_AFFILIATE_SCREEN = createJsonValue(
  screenSource,
) as unknown as typeof screenSource;

export interface PublicDisclosureAffiliateSyntheticCoordinateInput {
  readonly kind: 'SYNTHETIC_ST1004_SEMANTIC_FIXTURE';
  readonly expectedSha256: string;
  readonly observedSha256: string;
}

export interface PublicDisclosureAffiliateInput {
  readonly screenId: 'PUB-003';
  readonly route: '/articles/{slug}';
  readonly coordinate: PublicDisclosureAffiliateSyntheticCoordinateInput;
}

export interface PublicDisclosureAffiliateBoundaryResult {
  readonly value: false;
  readonly status: 'NOT_EXECUTED';
  readonly reason: string;
}

export interface PublicDisclosureAffiliateBoundaries {
  readonly routeRegistered: PublicDisclosureAffiliateBoundaryResult;
  readonly interactive: PublicDisclosureAffiliateBoundaryResult;
  readonly dom: PublicDisclosureAffiliateBoundaryResult;
  readonly react: PublicDisclosureAffiliateBoundaryResult;
  readonly ssr: PublicDisclosureAffiliateBoundaryResult;
  readonly api: PublicDisclosureAffiliateBoundaryResult;
  readonly network: PublicDisclosureAffiliateBoundaryResult;
  readonly database: PublicDisclosureAffiliateBoundaryResult;
  readonly publicReadModel: PublicDisclosureAffiliateBoundaryResult;
  readonly st1002ContentMapping: PublicDisclosureAffiliateBoundaryResult;
  readonly st0503AffiliateSource: PublicDisclosureAffiliateBoundaryResult;
  readonly disclosurePolicyResolution: PublicDisclosureAffiliateBoundaryResult;
  readonly disclosureRendering: PublicDisclosureAffiliateBoundaryResult;
  readonly apiCreditRendering: PublicDisclosureAffiliateBoundaryResult;
  readonly affiliateUrlResolution: PublicDisclosureAffiliateBoundaryResult;
  readonly urlIntegrity: PublicDisclosureAffiliateBoundaryResult;
  readonly linkHealth: PublicDisclosureAffiliateBoundaryResult;
  readonly freshness: PublicDisclosureAffiliateBoundaryResult;
  readonly killSwitch: PublicDisclosureAffiliateBoundaryResult;
  readonly ctaActivation: PublicDisclosureAffiliateBoundaryResult;
  readonly navigation: PublicDisclosureAffiliateBoundaryResult;
  readonly beacon: PublicDisclosureAffiliateBoundaryResult;
  readonly browser: PublicDisclosureAffiliateBoundaryResult;
  readonly accessibility: PublicDisclosureAffiliateBoundaryResult;
  readonly security: PublicDisclosureAffiliateBoundaryResult;
  readonly formalTst020: PublicDisclosureAffiliateBoundaryResult;
  readonly formalTst022: PublicDisclosureAffiliateBoundaryResult;
  readonly formalTst026: PublicDisclosureAffiliateBoundaryResult;
  readonly live: PublicDisclosureAffiliateBoundaryResult;
  readonly staging: PublicDisclosureAffiliateBoundaryResult;
  readonly publicationAuthorization: PublicDisclosureAffiliateBoundaryResult;
  readonly release: PublicDisclosureAffiliateBoundaryResult;
  readonly production: PublicDisclosureAffiliateBoundaryResult;
  readonly localEligibility: PublicDisclosureAffiliateBoundaryResult;
}

interface NotEvaluatedAssessment {
  readonly status: 'NOT_EVALUATED';
  readonly evidenceRef: null;
  readonly verified: false;
}

export interface PublicDisclosureSemanticMetadata {
  readonly componentId: 'UI-C031';
  readonly renderable: false;
  readonly interactive: false;
  readonly rendererOwned: true;
  readonly editorRemovable: false;
  readonly placementRequirement: 'ARTICLE_TOP_FIRST_VIEWPORT';
  readonly disclosurePolicyVersionRef: null;
  readonly articleDisclosureContextRef: null;
  readonly renderedCopy: null;
  readonly policyCurrentness: NotEvaluatedAssessment;
}

export interface PublicAffiliateCtaSemanticMetadata {
  readonly componentId: 'UI-C034';
  readonly renderable: false;
  readonly interactive: false;
  readonly focusable: false;
  readonly enabled: false;
  readonly offerRef: null;
  readonly affiliateLinkObservationRef: null;
  readonly affiliateUrl: null;
  readonly destinationHost: null;
  readonly renderedDestinationLabel: null;
  readonly destinationRequirement: {
    readonly marketplace: 'RAKUTEN_MARKETPLACE';
    readonly mustBeClearBeforeActivation: true;
    readonly verified: false;
  };
  readonly relationRequirement: {
    readonly requiredContractValue: 'sponsored nofollow';
    readonly renderedAttribute: null;
    readonly verified: false;
  };
  readonly navigationRequirement: {
    readonly directProviderUrlRequired: true;
    readonly raosRedirectAllowed: false;
    readonly cloakingAllowed: false;
    readonly urlModificationAllowed: false;
  };
  readonly urlIntegrity: NotEvaluatedAssessment;
  readonly linkHealth: NotEvaluatedAssessment;
  readonly reachability: NotEvaluatedAssessment;
  readonly freshness: NotEvaluatedAssessment;
  readonly killSwitch: NotEvaluatedAssessment;
}

export interface PublicApiCreditSemanticMetadata {
  readonly renderable: false;
  readonly providerDataUsage: 'NOT_EVALUATED';
  readonly requiredWhenProviderDataUsed: true;
  readonly policySourceRef: null;
  readonly renderedCopy: null;
  readonly applicability: NotEvaluatedAssessment;
}

export interface PublicBeaconIndependenceSemanticMetadata {
  readonly navigationMustNotDependOnBeacon: true;
  readonly beaconConfigured: false;
  readonly beaconExecuted: false;
  readonly navigationExecuted: false;
  readonly browserVerified: false;
}

export interface PublicDisclosureAffiliateCandidate {
  readonly classification: typeof PUBLIC_DISCLOSURE_AFFILIATE_CLASSIFICATION;
  readonly screen: typeof PUBLIC_DISCLOSURE_AFFILIATE_SCREEN;
  readonly route: {
    readonly template: '/articles/{slug}';
    readonly routeRegistered: false;
    readonly interactive: false;
    readonly focusable: false;
  };
  readonly coordinate: PublicDisclosureAffiliateSyntheticCoordinateInput;
  readonly hashBinding: {
    readonly profile: 'OPAQUE_CALLER_BOUND_EQUALITY_ONLY';
    readonly expectedSha256: string;
    readonly observedSha256: string;
    readonly equal: true;
    readonly recomputed: false;
    readonly canonicalized: false;
    readonly publicProjectionVerified: false;
    readonly disclosureVerified: false;
    readonly affiliateLinkVerified: false;
    readonly hashesAttested: false;
    readonly formalEvidence: false;
  };
  readonly components: readonly PublicDisclosureAffiliateComponentMetadata[];
  readonly composition: {
    readonly disclosureMustPrecedeAffiliateCta: true;
    readonly disclosureAndCtaMustRemainSemanticallySeparate: true;
    readonly ctaMustNotDominateEditorialEvidence: true;
    readonly selectedLayout: null;
    readonly domStatus: 'DOM_NOT_IMPLEMENTED';
  };
  readonly semantics: {
    readonly disclosure: PublicDisclosureSemanticMetadata;
    readonly affiliateCta: PublicAffiliateCtaSemanticMetadata;
    readonly apiCredit: PublicApiCreditSemanticMetadata;
    readonly beaconIndependence: PublicBeaconIndependenceSemanticMetadata;
  };
  readonly boundaries: PublicDisclosureAffiliateBoundaries;
  readonly actions: readonly [];
}

const boundaryReasons = {
  routeRegistered: 'NO_RUNTIME_ROUTE_REGISTERED',
  interactive: 'INTERACTION_DISABLED',
  dom: 'DOM_NOT_IMPLEMENTED',
  react: 'REACT_NOT_IMPLEMENTED',
  ssr: 'SSR_NOT_IMPLEMENTED',
  api: 'PUBLIC_API_NOT_CONNECTED',
  network: 'NETWORK_NOT_USED',
  database: 'DATABASE_NOT_USED',
  publicReadModel: 'PUBLIC_READMODEL_NOT_CONNECTED',
  st1002ContentMapping: 'ST_1002_CONTENT_MAPPING_UNAVAILABLE',
  st0503AffiliateSource: 'ST_0503_AFFILIATE_URL_SOURCE_ABSENT',
  disclosurePolicyResolution: 'CURRENT_DISCLOSURE_POLICY_NOT_RESOLVED',
  disclosureRendering: 'DISCLOSURE_COPY_NOT_RENDERED',
  apiCreditRendering: 'API_CREDIT_APPLICABILITY_AND_COPY_NOT_RESOLVED',
  affiliateUrlResolution: 'AFFILIATE_URL_RESOLVER_NOT_CONNECTED',
  urlIntegrity: 'OFFICIAL_URL_HASH_AND_ALLOWLIST_NOT_EVALUATED',
  linkHealth: 'LINK_HEALTH_NOT_EVALUATED',
  freshness: 'LINK_FRESHNESS_NOT_EVALUATED',
  killSwitch: 'AFFILIATE_KILL_SWITCH_NOT_EVALUATED',
  ctaActivation: 'CTA_DISABLED',
  navigation: 'NAVIGATION_NOT_IMPLEMENTED',
  beacon: 'BEACON_NOT_IMPLEMENTED',
  browser: 'BROWSER_NOT_EXECUTED',
  accessibility: 'ACCESSIBILITY_NOT_EXECUTED',
  security: 'SECURITY_VERIFICATION_NOT_EXECUTED',
  formalTst020: 'FORMAL_TST_020_NOT_EXECUTED',
  formalTst022: 'FORMAL_TST_022_NOT_EXECUTED',
  formalTst026: 'FORMAL_TST_026_NOT_EXECUTED',
  live: 'LIVE_NOT_AUTHORIZED',
  staging: 'STAGING_NOT_AUTHORIZED',
  publicationAuthorization: 'PUBLICATION_NOT_AUTHORIZED',
  release: 'RELEASE_NOT_AUTHORIZED',
  production: 'PRODUCTION_NOT_AUTHORIZED',
  localEligibility: 'DISCLOSURE_LINK_AND_RUNTIME_GATES_UNSATISFIED',
} as const;

const INPUT_KEYS = ['coordinate', 'route', 'screenId'] as const;
const COORDINATE_KEYS = ['expectedSha256', 'kind', 'observedSha256'] as const;
const SHA256 = /^[0-9a-f]{64}$/;
const ABSOLUTE_OR_ACTIVE_SCHEME =
  /^(?:(?:https?|ftp|file|mailto|tel|javascript|data|vbscript):|\/\/)/i;
const ACTIVE_MARKUP = /<\s*(?:script|iframe)\b|\bon[a-z]+\s*=/i;
const COPY_KEY_FRAGMENTS = ['copy', 'label', 'message', 'text', 'title'];
const LINK_VALUE_KEY_FRAGMENTS = [
  'affiliateurl',
  'destinationhost',
  'href',
  'linkvalue',
  'redirectpath',
  'url',
];
const REFERENCE_KEY_FRAGMENTS = [
  'contextref',
  'linkref',
  'observationref',
  'offerref',
  'policyref',
  'policyversion',
];
const INTERNAL_KEY_FRAGMENTS = [
  'approvalid',
  'articleid',
  'evidence',
  'finance',
  'inputhash',
  'internal',
  'profit',
  'publicationid',
  'rawprompt',
  'revenue',
  'sourcepacket',
];
const EFFECT_KEY_FRAGMENTS = [
  'analytics',
  'beacon',
  'callback',
  'click',
  'cookie',
  'event',
  'fetch',
  'navigate',
  'script',
  'tracking',
];

function reject(code: PublicDisclosureAffiliateErrorCode): never {
  throw new PublicDisclosureAffiliateError(code);
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
  if (typeof value !== 'object' || ancestors.has(value)) {
    return false;
  }
  ancestors.add(value);
  try {
    const isArray = Array.isArray(value);
    if (Object.getPrototypeOf(value) !== (isArray ? Array.prototype : Object.prototype)) {
      return false;
    }
    const keys = Reflect.ownKeys(value);
    if (keys.some((key) => typeof key !== 'string')) {
      return false;
    }
    for (const key of keys) {
      if (key === 'length') {
        continue;
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

function scanProhibitedSurface(value: JsonValue): PublicDisclosureAffiliateErrorCode | null {
  if (typeof value === 'string') {
    return ABSOLUTE_OR_ACTIVE_SCHEME.test(value) || ACTIVE_MARKUP.test(value)
      ? 'PUBLIC_DISCLOSURE_LINK_VALUE_PROHIBITED'
      : null;
  }
  if (value === null || typeof value !== 'object') {
    return null;
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const finding = scanProhibitedSurface(item);
      if (finding !== null) {
        return finding;
      }
    }
    return null;
  }
  for (const [key, item] of Object.entries(value)) {
    const normalized = normalizedKey(key);
    if (COPY_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))) {
      return 'PUBLIC_DISCLOSURE_COPY_PROHIBITED';
    }
    if (LINK_VALUE_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))) {
      return 'PUBLIC_DISCLOSURE_LINK_VALUE_PROHIBITED';
    }
    if (REFERENCE_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))) {
      return 'PUBLIC_DISCLOSURE_REFERENCE_PROHIBITED';
    }
    if (INTERNAL_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))) {
      return 'PUBLIC_DISCLOSURE_INTERNAL_FIELD_PROHIBITED';
    }
    if (
      normalized.startsWith('on') ||
      EFFECT_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))
    ) {
      return 'PUBLIC_DISCLOSURE_EFFECT_PROHIBITED';
    }
    const finding = scanProhibitedSurface(item);
    if (finding !== null) {
      return finding;
    }
  }
  return null;
}

function clonePlainObject(value: unknown, scanSurface = true): JsonObject {
  if (!isStrictPlainTree(value)) {
    return reject('PUBLIC_DISCLOSURE_INPUT_INVALID');
  }
  let clone: JsonValue;
  try {
    clone = createJsonValue(value);
  } catch {
    return reject('PUBLIC_DISCLOSURE_INPUT_INVALID');
  }
  if (!isJsonObject(clone)) {
    return reject('PUBLIC_DISCLOSURE_INPUT_INVALID');
  }
  if (scanSurface) {
    const prohibited = scanProhibitedSurface(clone);
    if (prohibited !== null) {
      return reject(prohibited);
    }
  }
  return clone;
}

function hasExactKeys(value: JsonObject, expected: readonly string[]): boolean {
  const keys = Object.keys(value).sort();
  return keys.length === expected.length && keys.every((key, index) => key === expected[index]);
}

function requireCoordinate(
  value: JsonValue | undefined,
): PublicDisclosureAffiliateSyntheticCoordinateInput {
  if (!isJsonObject(value) || !hasExactKeys(value, COORDINATE_KEYS)) {
    return reject('PUBLIC_DISCLOSURE_COORDINATE_INVALID');
  }
  const kind = value['kind'];
  const expectedSha256 = value['expectedSha256'];
  const observedSha256 = value['observedSha256'];
  if (kind !== 'SYNTHETIC_ST1004_SEMANTIC_FIXTURE') {
    return reject('PUBLIC_DISCLOSURE_COORDINATE_INVALID');
  }
  if (
    typeof expectedSha256 !== 'string' ||
    typeof observedSha256 !== 'string' ||
    !SHA256.test(expectedSha256) ||
    !SHA256.test(observedSha256)
  ) {
    return reject('PUBLIC_DISCLOSURE_HASH_INVALID');
  }
  if (expectedSha256 !== observedSha256) {
    return reject('PUBLIC_DISCLOSURE_HASH_MISMATCH');
  }
  return { kind, expectedSha256, observedSha256 };
}

function validatedInput(input: PublicDisclosureAffiliateInput): PublicDisclosureAffiliateInput {
  const value = clonePlainObject(input);
  if (!hasExactKeys(value, INPUT_KEYS)) {
    return reject('PUBLIC_DISCLOSURE_INPUT_INVALID');
  }
  if (value['screenId'] !== 'PUB-003') {
    return reject('PUBLIC_DISCLOSURE_SCREEN_INVALID');
  }
  if (value['route'] !== '/articles/{slug}') {
    return reject('PUBLIC_DISCLOSURE_ROUTE_INVALID');
  }
  return {
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: requireCoordinate(value['coordinate']),
  };
}

function notEvaluated(): NotEvaluatedAssessment {
  return { status: 'NOT_EVALUATED', evidenceRef: null, verified: false };
}

function makeBoundaries(): PublicDisclosureAffiliateBoundaries {
  return Object.fromEntries(
    Object.entries(boundaryReasons).map(([key, reason]) => [
      key,
      { value: false, status: 'NOT_EXECUTED', reason },
    ]),
  ) as unknown as PublicDisclosureAffiliateBoundaries;
}

function buildCandidate(input: PublicDisclosureAffiliateInput): PublicDisclosureAffiliateCandidate {
  return createJsonValue({
    classification: PUBLIC_DISCLOSURE_AFFILIATE_CLASSIFICATION,
    screen: PUBLIC_DISCLOSURE_AFFILIATE_SCREEN,
    route: {
      template: input.route,
      routeRegistered: false,
      interactive: false,
      focusable: false,
    },
    coordinate: input.coordinate,
    hashBinding: {
      profile: 'OPAQUE_CALLER_BOUND_EQUALITY_ONLY',
      expectedSha256: input.coordinate.expectedSha256,
      observedSha256: input.coordinate.observedSha256,
      equal: true,
      recomputed: false,
      canonicalized: false,
      publicProjectionVerified: false,
      disclosureVerified: false,
      affiliateLinkVerified: false,
      hashesAttested: false,
      formalEvidence: false,
    },
    components: PUBLIC_DISCLOSURE_AFFILIATE_COMPONENTS,
    composition: {
      disclosureMustPrecedeAffiliateCta: true,
      disclosureAndCtaMustRemainSemanticallySeparate: true,
      ctaMustNotDominateEditorialEvidence: true,
      selectedLayout: null,
      domStatus: 'DOM_NOT_IMPLEMENTED',
    },
    semantics: {
      disclosure: {
        componentId: 'UI-C031',
        renderable: false,
        interactive: false,
        rendererOwned: true,
        editorRemovable: false,
        placementRequirement: 'ARTICLE_TOP_FIRST_VIEWPORT',
        disclosurePolicyVersionRef: null,
        articleDisclosureContextRef: null,
        renderedCopy: null,
        policyCurrentness: notEvaluated(),
      },
      affiliateCta: {
        componentId: 'UI-C034',
        renderable: false,
        interactive: false,
        focusable: false,
        enabled: false,
        offerRef: null,
        affiliateLinkObservationRef: null,
        affiliateUrl: null,
        destinationHost: null,
        renderedDestinationLabel: null,
        destinationRequirement: {
          marketplace: 'RAKUTEN_MARKETPLACE',
          mustBeClearBeforeActivation: true,
          verified: false,
        },
        relationRequirement: {
          requiredContractValue: 'sponsored nofollow',
          renderedAttribute: null,
          verified: false,
        },
        navigationRequirement: {
          directProviderUrlRequired: true,
          raosRedirectAllowed: false,
          cloakingAllowed: false,
          urlModificationAllowed: false,
        },
        urlIntegrity: notEvaluated(),
        linkHealth: notEvaluated(),
        reachability: notEvaluated(),
        freshness: notEvaluated(),
        killSwitch: notEvaluated(),
      },
      apiCredit: {
        renderable: false,
        providerDataUsage: 'NOT_EVALUATED',
        requiredWhenProviderDataUsed: true,
        policySourceRef: null,
        renderedCopy: null,
        applicability: notEvaluated(),
      },
      beaconIndependence: {
        navigationMustNotDependOnBeacon: true,
        beaconConfigured: false,
        beaconExecuted: false,
        navigationExecuted: false,
        browserVerified: false,
      },
    },
    boundaries: makeBoundaries(),
    actions: [],
  }) as unknown as PublicDisclosureAffiliateCandidate;
}

function jsonEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function unexpectedProhibitedSurface(
  value: JsonValue | undefined,
  expected: JsonValue | undefined,
): PublicDisclosureAffiliateErrorCode | null {
  if (jsonEqual(value, expected)) {
    return null;
  }
  if (!isJsonObject(value) || !isJsonObject(expected)) {
    return null;
  }
  for (const [key, item] of Object.entries(value)) {
    if (!Object.hasOwn(expected, key)) {
      return scanProhibitedSurface({ [key]: item });
    }
    const nested = unexpectedProhibitedSurface(item, expected[key]);
    if (nested !== null) {
      return nested;
    }
  }
  return null;
}

function candidateInput(value: JsonObject): PublicDisclosureAffiliateInput {
  const screen = value['screen'];
  const coordinate = value['coordinate'];
  if (!isJsonObject(screen) || !isJsonObject(coordinate)) {
    return reject('PUBLIC_DISCLOSURE_CANDIDATE_INVALID');
  }
  return {
    screenId: screen['id'] as 'PUB-003',
    route: screen['route'] as '/articles/{slug}',
    coordinate: coordinate as unknown as PublicDisclosureAffiliateSyntheticCoordinateInput,
  };
}

function classifyCandidateFailure(
  value: JsonObject,
  expected: PublicDisclosureAffiliateCandidate,
): PublicDisclosureAffiliateErrorCode {
  const prohibited = unexpectedProhibitedSurface(value, expected as unknown as JsonValue);
  if (prohibited !== null) {
    return prohibited;
  }
  if (
    !jsonEqual(value['screen'], expected.screen) ||
    !jsonEqual(value['route'], expected.route) ||
    !jsonEqual(value['components'], expected.components)
  ) {
    return 'PUBLIC_DISCLOSURE_METADATA_INVALID';
  }
  if (
    !jsonEqual(value['composition'], expected.composition) ||
    !jsonEqual(value['semantics'], expected.semantics)
  ) {
    return 'PUBLIC_DISCLOSURE_SEMANTICS_INVALID';
  }
  if (
    !jsonEqual(value['boundaries'], expected.boundaries) ||
    !jsonEqual(value['actions'], expected.actions)
  ) {
    return 'PUBLIC_DISCLOSURE_AUTHORITY_INVALID';
  }
  return 'PUBLIC_DISCLOSURE_CANDIDATE_INVALID';
}

export function validatePublicDisclosureAffiliateCandidate(
  value: unknown,
): PublicDisclosureAffiliateCandidate {
  const clone = clonePlainObject(value, false);
  let input: PublicDisclosureAffiliateInput;
  try {
    input = validatedInput(candidateInput(clone));
  } catch (error) {
    if (error instanceof PublicDisclosureAffiliateError) {
      throw error;
    }
    return reject('PUBLIC_DISCLOSURE_CANDIDATE_INVALID');
  }
  const expected = buildCandidate(input);
  if (!jsonEqual(clone, expected)) {
    return reject(classifyCandidateFailure(clone, expected));
  }
  return clone as unknown as PublicDisclosureAffiliateCandidate;
}

export function createPublicDisclosureAffiliateCandidate(
  input: PublicDisclosureAffiliateInput,
): PublicDisclosureAffiliateCandidate {
  return validatePublicDisclosureAffiliateCandidate(buildCandidate(validatedInput(input)));
}
