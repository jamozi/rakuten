import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const PUBLIC_SEO_ROUTE_POLICY_CLASSIFICATION =
  'UNREGISTERED_DISABLED_HEADLESS_ST1005_SEO_ROUTE_POLICY_CANDIDATE' as const;

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

export const PUBLIC_SEO_ROUTE_POLICY_SCREEN = createJsonValue(
  screenSource,
) as unknown as typeof screenSource;

export const PUBLIC_SEO_ROUTE_POLICY_PAGE_CLASSES = Object.freeze([
  'DRAFT',
  'PREVIEW',
  'FACET',
  'PUBLIC_ARTICLE',
] as const);

export type PublicSeoRoutePolicyPageClass = (typeof PUBLIC_SEO_ROUTE_POLICY_PAGE_CLASSES)[number];

export type PublicSeoRouteOriginMode = 'ROUTE_ONLY' | 'CALLER_SUPPLIED_ORIGIN';

export const PUBLIC_SEO_ROUTE_POLICY_ERROR_CODES = Object.freeze([
  'PUBLIC_SEO_ROUTE_INPUT_INVALID',
  'PUBLIC_SEO_ROUTE_SCREEN_INVALID',
  'PUBLIC_SEO_ROUTE_TEMPLATE_INVALID',
  'PUBLIC_SEO_ROUTE_COORDINATE_INVALID',
  'PUBLIC_SEO_ROUTE_HASH_INVALID',
  'PUBLIC_SEO_ROUTE_HASH_MISMATCH',
  'PUBLIC_SEO_ROUTE_ORIGIN_MODE_INVALID',
  'PUBLIC_SEO_ROUTE_ORIGIN_INVALID',
  'PUBLIC_SEO_ROUTE_ORIGIN_MODE_MISMATCH',
  'PUBLIC_SEO_ROUTE_CONTENT_PROHIBITED',
  'PUBLIC_SEO_ROUTE_INTERNAL_FIELD_PROHIBITED',
  'PUBLIC_SEO_ROUTE_EFFECT_PROHIBITED',
  'PUBLIC_SEO_ROUTE_METADATA_INVALID',
  'PUBLIC_SEO_ROUTE_POLICY_INVALID',
  'PUBLIC_SEO_ROUTE_AUTHORITY_INVALID',
  'PUBLIC_SEO_ROUTE_CANDIDATE_INVALID',
] as const);

export type PublicSeoRoutePolicyErrorCode = (typeof PUBLIC_SEO_ROUTE_POLICY_ERROR_CODES)[number];

export class PublicSeoRoutePolicyError extends TypeError {
  readonly code: PublicSeoRoutePolicyErrorCode;

  constructor(code: PublicSeoRoutePolicyErrorCode) {
    super(code);
    this.name = 'PublicSeoRoutePolicyError';
    this.code = code;
    Object.freeze(this);
  }
}

export interface PublicSeoRouteSyntheticCoordinateInput {
  readonly kind: 'SYNTHETIC_ST1005_SEO_ROUTE_FIXTURE';
  readonly expectedSha256: string;
  readonly observedSha256: string;
}

export interface PublicSeoRouteOriginInput {
  readonly mode: PublicSeoRouteOriginMode;
  readonly callerSuppliedOrigin: string | null;
}

export interface PublicSeoRoutePolicyInput {
  readonly screenId: 'PUB-003';
  readonly route: '/articles/{slug}';
  readonly coordinate: PublicSeoRouteSyntheticCoordinateInput;
  readonly origin: PublicSeoRouteOriginInput;
}

export interface PublicSeoRouteBoundaryResult {
  readonly value: false;
  readonly status: 'NOT_EXECUTED';
  readonly reason: string;
}

export interface PublicSeoRoutePolicyBoundaries {
  readonly routeRegistered: PublicSeoRouteBoundaryResult;
  readonly slugResolved: PublicSeoRouteBoundaryResult;
  readonly facetResolved: PublicSeoRouteBoundaryResult;
  readonly dom: PublicSeoRouteBoundaryResult;
  readonly react: PublicSeoRouteBoundaryResult;
  readonly ssr: PublicSeoRouteBoundaryResult;
  readonly api: PublicSeoRouteBoundaryResult;
  readonly network: PublicSeoRouteBoundaryResult;
  readonly database: PublicSeoRouteBoundaryResult;
  readonly publicReadModel: PublicSeoRouteBoundaryResult;
  readonly authoritativeSnapshot: PublicSeoRouteBoundaryResult;
  readonly currentPublication: PublicSeoRouteBoundaryResult;
  readonly currentRoute: PublicSeoRouteBoundaryResult;
  readonly canonicalActivation: PublicSeoRouteBoundaryResult;
  readonly canonicalGraph: PublicSeoRouteBoundaryResult;
  readonly canonicalUniqueness: PublicSeoRouteBoundaryResult;
  readonly sitemapGeneration: PublicSeoRouteBoundaryResult;
  readonly sitemapPublication: PublicSeoRouteBoundaryResult;
  readonly robotsRuntime: PublicSeoRouteBoundaryResult;
  readonly browser: PublicSeoRouteBoundaryResult;
  readonly security: PublicSeoRouteBoundaryResult;
  readonly formalTst020: PublicSeoRouteBoundaryResult;
  readonly formalTst022: PublicSeoRouteBoundaryResult;
  readonly live: PublicSeoRouteBoundaryResult;
  readonly staging: PublicSeoRouteBoundaryResult;
  readonly publicationAuthorization: PublicSeoRouteBoundaryResult;
  readonly release: PublicSeoRouteBoundaryResult;
  readonly production: PublicSeoRouteBoundaryResult;
  readonly localEligibility: PublicSeoRouteBoundaryResult;
}

export interface PublicSeoRouteNotEvaluatedAssessment {
  readonly state: 'NOT_EVALUATED';
  readonly evidenceRef: null;
  readonly verified: false;
}

export interface PublicSeoRouteFixedNoindexPolicy {
  readonly pageClass: 'DRAFT' | 'PREVIEW' | 'FACET';
  readonly state: 'LOCAL_FIXED_REQUIREMENT';
  readonly requiredIndexState: 'noindex';
  readonly requiredRobotsDirectives: readonly ('noindex' | 'nofollow')[];
  readonly sitemapInclusionAllowed: false;
  readonly runtimeApplied: false;
}

export interface PublicSeoRoutePublicArticlePolicy {
  readonly pageClass: 'PUBLIC_ARTICLE';
  readonly state: 'NOT_EVALUATED';
  readonly requiredIndexState: null;
  readonly requiredRobotsDirectives: readonly [];
  readonly sitemapInclusionAllowed: null;
  readonly runtimeApplied: false;
}

export type PublicSeoRoutePagePolicy =
  PublicSeoRouteFixedNoindexPolicy | PublicSeoRoutePublicArticlePolicy;

export interface PublicSeoRoutePolicyCandidate {
  readonly classification: typeof PUBLIC_SEO_ROUTE_POLICY_CLASSIFICATION;
  readonly screen: typeof PUBLIC_SEO_ROUTE_POLICY_SCREEN;
  readonly route: {
    readonly template: '/articles/{slug}';
    readonly routeRegistered: false;
    readonly currentRoute: null;
    readonly canonicalRoute: null;
    readonly slugResolved: false;
    readonly facetResolved: false;
  };
  readonly coordinate: PublicSeoRouteSyntheticCoordinateInput;
  readonly hashBinding: {
    readonly profile: 'OPAQUE_CALLER_BOUND_EQUALITY_ONLY';
    readonly expectedSha256: string;
    readonly observedSha256: string;
    readonly equal: true;
    readonly recomputed: false;
    readonly canonicalized: false;
    readonly routeVerified: false;
    readonly snapshotVerified: false;
    readonly formalEvidence: false;
  };
  readonly origin: {
    readonly mode: PublicSeoRouteOriginMode;
    readonly source: 'NONE' | 'CALLER_SUPPLIED_UNAPPROVED';
    readonly callerSuppliedOrigin: string | null;
    readonly acceptedOnlyAsUnapprovedInput: boolean;
    readonly domainApproved: false;
    readonly productionDomainSelected: false;
    readonly absoluteUrlRenderingAllowed: false;
  };
  readonly pagePolicies: readonly PublicSeoRoutePagePolicy[];
  readonly canonical: {
    readonly selfReferencingRequiredForPublicCanonical: true;
    readonly singleCanonicalRequired: true;
    readonly canonicalRouteRef: null;
    readonly canonicalRoute: null;
    readonly absoluteCanonicalUrl: null;
    readonly activated: false;
    readonly uniqueness: PublicSeoRouteNotEvaluatedAssessment;
    readonly graphAcyclic: PublicSeoRouteNotEvaluatedAssessment;
    readonly routeExistence: PublicSeoRouteNotEvaluatedAssessment;
    readonly currentRouteEquality: PublicSeoRouteNotEvaluatedAssessment;
  };
  readonly sitemap: {
    readonly requiredEligibilityFacts: readonly [
      'PUBLISHED',
      'HTTP_200',
      'INDEX_STATE_INDEX',
      'SELF_CANONICAL',
      'NOT_PAUSED',
      'NOT_REDIRECT_SOURCE',
      'CURRENT_PUBLICATION_SNAPSHOT',
    ];
    readonly entries: readonly [];
    readonly serializedDocument: null;
    readonly lastmod: null;
    readonly inclusionEligibility: PublicSeoRouteNotEvaluatedAssessment;
    readonly generated: false;
    readonly published: false;
  };
  readonly robots: {
    readonly serializedDocument: null;
    readonly runtimeApplied: false;
    readonly routeResponseVerified: false;
  };
  readonly externalAssessments: {
    readonly publicationSnapshotCurrency: PublicSeoRouteNotEvaluatedAssessment;
    readonly currentPublication: PublicSeoRouteNotEvaluatedAssessment;
    readonly http200: PublicSeoRouteNotEvaluatedAssessment;
    readonly runtimeIndexability: PublicSeoRouteNotEvaluatedAssessment;
    readonly pauseOrRedirectSourceState: PublicSeoRouteNotEvaluatedAssessment;
  };
  readonly conditionalLocalEligibility: false;
  readonly eligibilityReasons: readonly string[];
  readonly authorization: {
    readonly approval: false;
    readonly publication: false;
    readonly release: false;
    readonly production: false;
    readonly formalEvidence: false;
  };
  readonly boundaries: PublicSeoRoutePolicyBoundaries;
  readonly actions: readonly [];
}

const boundaryReasons = {
  routeRegistered: 'NO_RUNTIME_ROUTE_REGISTERED',
  slugResolved: 'SLUG_RESOLUTION_NOT_IMPLEMENTED',
  facetResolved: 'FACET_RESOLUTION_NOT_IMPLEMENTED',
  dom: 'DOM_NOT_IMPLEMENTED',
  react: 'REACT_NOT_IMPLEMENTED',
  ssr: 'SSR_NOT_IMPLEMENTED',
  api: 'PUBLIC_API_NOT_CONNECTED',
  network: 'NETWORK_NOT_USED',
  database: 'DATABASE_NOT_USED',
  publicReadModel: 'PUBLIC_READMODEL_NOT_CONNECTED',
  authoritativeSnapshot: 'AUTHORITATIVE_PUBLICATION_SNAPSHOT_UNAVAILABLE',
  currentPublication: 'CURRENT_PUBLICATION_NOT_SELECTED',
  currentRoute: 'CURRENT_ROUTE_NOT_ESTABLISHED',
  canonicalActivation: 'CANONICAL_ABSOLUTE_URL_NOT_ACTIVATED',
  canonicalGraph: 'CANONICAL_GRAPH_NOT_EVALUATED',
  canonicalUniqueness: 'CANONICAL_UNIQUENESS_NOT_EVALUATED',
  sitemapGeneration: 'SITEMAP_NOT_GENERATED',
  sitemapPublication: 'SITEMAP_NOT_PUBLISHED',
  robotsRuntime: 'ROBOTS_RUNTIME_NOT_IMPLEMENTED',
  browser: 'BROWSER_NOT_EXECUTED',
  security: 'PUBLIC_ISOLATION_NOT_RUNTIME_VERIFIED',
  formalTst020: 'FORMAL_TST_020_NOT_EXECUTED',
  formalTst022: 'FORMAL_TST_022_NOT_EXECUTED',
  live: 'LIVE_NOT_AUTHORIZED',
  staging: 'STAGING_NOT_AUTHORIZED',
  publicationAuthorization: 'PUBLICATION_NOT_AUTHORIZED',
  release: 'RELEASE_NOT_AUTHORIZED',
  production: 'PRODUCTION_NOT_AUTHORIZED',
  localEligibility: 'ROUTE_PUBLICATION_AND_RUNTIME_FACTS_UNAVAILABLE',
} as const;

const INPUT_KEYS = ['coordinate', 'origin', 'route', 'screenId'] as const;
const COORDINATE_KEYS = ['expectedSha256', 'kind', 'observedSha256'] as const;
const ORIGIN_KEYS = ['callerSuppliedOrigin', 'mode'] as const;
const SHA256 = /^[0-9a-f]{64}$/;
const HOST = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
const ACTIVE_MARKUP = /<\s*(?:script|iframe)\b|\bon[a-z]+\s*=/i;
const CONTENT_KEY_FRAGMENTS = [
  'copy',
  'description',
  'headline',
  'html',
  'payload',
  'text',
  'title',
];
const INTERNAL_KEY_FRAGMENTS = [
  'approvalid',
  'articleid',
  'evidence',
  'finance',
  'internal',
  'profit',
  'prompt',
  'publicationid',
  'revenue',
  'secret',
  'sourcepacket',
];
const EFFECT_KEY_FRAGMENTS = [
  'analytics',
  'callback',
  'cookie',
  'database',
  'event',
  'fetch',
  'navigate',
  'network',
  'publish',
  'request',
  'script',
  'tracking',
];
const URL_KEY_FRAGMENTS = ['absoluteurl', 'canonicalurl', 'href', 'sitemapentry', 'url'];

function reject(code: PublicSeoRoutePolicyErrorCode): never {
  throw new PublicSeoRoutePolicyError(code);
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
    const isArray = Array.isArray(value);
    if (Object.getPrototypeOf(value) !== (isArray ? Array.prototype : Object.prototype)) {
      return false;
    }
    for (const key of Reflect.ownKeys(value)) {
      if (typeof key !== 'string' || key === '__proto__' || key === 'prototype') return false;
      if (key === 'length') continue;
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

function scanProhibitedSurface(value: JsonValue): PublicSeoRoutePolicyErrorCode | null {
  if (typeof value === 'string') {
    return ACTIVE_MARKUP.test(value) ? 'PUBLIC_SEO_ROUTE_CONTENT_PROHIBITED' : null;
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
    if (
      CONTENT_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment)) ||
      URL_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))
    ) {
      return 'PUBLIC_SEO_ROUTE_CONTENT_PROHIBITED';
    }
    if (INTERNAL_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))) {
      return 'PUBLIC_SEO_ROUTE_INTERNAL_FIELD_PROHIBITED';
    }
    if (
      normalized.startsWith('on') ||
      EFFECT_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))
    ) {
      return 'PUBLIC_SEO_ROUTE_EFFECT_PROHIBITED';
    }
    const finding = scanProhibitedSurface(item);
    if (finding !== null) return finding;
  }
  return null;
}

function clonePlainObject(value: unknown, scanSurface = true): JsonObject {
  if (!isStrictPlainTree(value)) return reject('PUBLIC_SEO_ROUTE_INPUT_INVALID');
  let clone: JsonValue;
  try {
    clone = createJsonValue(value);
  } catch {
    return reject('PUBLIC_SEO_ROUTE_INPUT_INVALID');
  }
  if (!isJsonObject(clone)) return reject('PUBLIC_SEO_ROUTE_INPUT_INVALID');
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

function requireCoordinate(value: JsonValue | undefined): PublicSeoRouteSyntheticCoordinateInput {
  if (!isJsonObject(value) || !hasExactKeys(value, COORDINATE_KEYS)) {
    return reject('PUBLIC_SEO_ROUTE_COORDINATE_INVALID');
  }
  const kind = value['kind'];
  const expectedSha256 = value['expectedSha256'];
  const observedSha256 = value['observedSha256'];
  if (kind !== 'SYNTHETIC_ST1005_SEO_ROUTE_FIXTURE') {
    return reject('PUBLIC_SEO_ROUTE_COORDINATE_INVALID');
  }
  if (
    typeof expectedSha256 !== 'string' ||
    typeof observedSha256 !== 'string' ||
    !SHA256.test(expectedSha256) ||
    !SHA256.test(observedSha256)
  ) {
    return reject('PUBLIC_SEO_ROUTE_HASH_INVALID');
  }
  if (expectedSha256 !== observedSha256) return reject('PUBLIC_SEO_ROUTE_HASH_MISMATCH');
  return { kind, expectedSha256, observedSha256 };
}

function normalizedHttpsOrigin(value: string): string | null {
  if (!value.startsWith('https://')) return null;
  const normalized = value.endsWith('/') ? value.slice(0, -1) : value;
  const authority = normalized.slice('https://'.length);
  if (
    authority.length === 0 ||
    authority.length > 259 ||
    authority.includes('/') ||
    authority.includes('?') ||
    authority.includes('#') ||
    authority.includes('@')
  ) {
    return null;
  }
  const separator = authority.lastIndexOf(':');
  const host = separator < 0 ? authority : authority.slice(0, separator);
  const port = separator < 0 ? null : authority.slice(separator + 1);
  if (port !== null) {
    if (!/^[1-9][0-9]*$/.test(port)) return null;
    const numericPort = Number(port);
    if (!Number.isSafeInteger(numericPort) || numericPort > 65535 || numericPort === 443) {
      return null;
    }
  }
  return host.length <= 253 && HOST.test(host) ? normalized : null;
}

function requireOrigin(value: JsonValue | undefined): PublicSeoRouteOriginInput {
  if (!isJsonObject(value) || !hasExactKeys(value, ORIGIN_KEYS)) {
    return reject('PUBLIC_SEO_ROUTE_ORIGIN_INVALID');
  }
  const mode = value['mode'];
  const rawOrigin = value['callerSuppliedOrigin'];
  if (mode !== 'ROUTE_ONLY' && mode !== 'CALLER_SUPPLIED_ORIGIN') {
    return reject('PUBLIC_SEO_ROUTE_ORIGIN_MODE_INVALID');
  }
  if (mode === 'ROUTE_ONLY') {
    if (rawOrigin !== null) return reject('PUBLIC_SEO_ROUTE_ORIGIN_MODE_MISMATCH');
    return { mode, callerSuppliedOrigin: null };
  }
  if (typeof rawOrigin !== 'string') return reject('PUBLIC_SEO_ROUTE_ORIGIN_MODE_MISMATCH');
  const origin = normalizedHttpsOrigin(rawOrigin);
  if (origin === null) return reject('PUBLIC_SEO_ROUTE_ORIGIN_INVALID');
  return { mode, callerSuppliedOrigin: origin };
}

function validatedInput(input: PublicSeoRoutePolicyInput): PublicSeoRoutePolicyInput {
  const value = clonePlainObject(input);
  if (!hasExactKeys(value, INPUT_KEYS)) return reject('PUBLIC_SEO_ROUTE_INPUT_INVALID');
  if (value['screenId'] !== 'PUB-003') return reject('PUBLIC_SEO_ROUTE_SCREEN_INVALID');
  if (value['route'] !== '/articles/{slug}') {
    return reject('PUBLIC_SEO_ROUTE_TEMPLATE_INVALID');
  }
  return {
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: requireCoordinate(value['coordinate']),
    origin: requireOrigin(value['origin']),
  };
}

function notEvaluated(): PublicSeoRouteNotEvaluatedAssessment {
  return { state: 'NOT_EVALUATED', evidenceRef: null, verified: false };
}

function makeBoundaries(): PublicSeoRoutePolicyBoundaries {
  return Object.fromEntries(
    Object.entries(boundaryReasons).map(([key, reason]) => [
      key,
      { value: false, status: 'NOT_EXECUTED', reason },
    ]),
  ) as unknown as PublicSeoRoutePolicyBoundaries;
}

function pagePolicies(): readonly PublicSeoRoutePagePolicy[] {
  return [
    {
      pageClass: 'DRAFT',
      state: 'LOCAL_FIXED_REQUIREMENT',
      requiredIndexState: 'noindex',
      requiredRobotsDirectives: ['noindex'],
      sitemapInclusionAllowed: false,
      runtimeApplied: false,
    },
    {
      pageClass: 'PREVIEW',
      state: 'LOCAL_FIXED_REQUIREMENT',
      requiredIndexState: 'noindex',
      requiredRobotsDirectives: ['noindex', 'nofollow'],
      sitemapInclusionAllowed: false,
      runtimeApplied: false,
    },
    {
      pageClass: 'FACET',
      state: 'LOCAL_FIXED_REQUIREMENT',
      requiredIndexState: 'noindex',
      requiredRobotsDirectives: ['noindex'],
      sitemapInclusionAllowed: false,
      runtimeApplied: false,
    },
    {
      pageClass: 'PUBLIC_ARTICLE',
      state: 'NOT_EVALUATED',
      requiredIndexState: null,
      requiredRobotsDirectives: [],
      sitemapInclusionAllowed: null,
      runtimeApplied: false,
    },
  ];
}

function buildCandidate(input: PublicSeoRoutePolicyInput): PublicSeoRoutePolicyCandidate {
  const callerOrigin = input.origin.callerSuppliedOrigin;
  const eligibilityReasons = [
    ...(callerOrigin === null ? ['ROUTE_ONLY_ORIGIN_UNAVAILABLE'] : ['CALLER_ORIGIN_UNAPPROVED']),
    'CURRENT_ROUTE_NOT_EVALUATED',
    'CANONICAL_UNIQUENESS_NOT_EVALUATED',
    'PUBLICATION_SNAPSHOT_CURRENCY_NOT_EVALUATED',
    'SITEMAP_ELIGIBILITY_NOT_EVALUATED',
    'RUNTIME_NOT_EXECUTED',
  ];
  return createJsonValue({
    classification: PUBLIC_SEO_ROUTE_POLICY_CLASSIFICATION,
    screen: PUBLIC_SEO_ROUTE_POLICY_SCREEN,
    route: {
      template: input.route,
      routeRegistered: false,
      currentRoute: null,
      canonicalRoute: null,
      slugResolved: false,
      facetResolved: false,
    },
    coordinate: input.coordinate,
    hashBinding: {
      profile: 'OPAQUE_CALLER_BOUND_EQUALITY_ONLY',
      expectedSha256: input.coordinate.expectedSha256,
      observedSha256: input.coordinate.observedSha256,
      equal: true,
      recomputed: false,
      canonicalized: false,
      routeVerified: false,
      snapshotVerified: false,
      formalEvidence: false,
    },
    origin: {
      mode: input.origin.mode,
      source: callerOrigin === null ? 'NONE' : 'CALLER_SUPPLIED_UNAPPROVED',
      callerSuppliedOrigin: callerOrigin,
      acceptedOnlyAsUnapprovedInput: callerOrigin !== null,
      domainApproved: false,
      productionDomainSelected: false,
      absoluteUrlRenderingAllowed: false,
    },
    pagePolicies: pagePolicies(),
    canonical: {
      selfReferencingRequiredForPublicCanonical: true,
      singleCanonicalRequired: true,
      canonicalRouteRef: null,
      canonicalRoute: null,
      absoluteCanonicalUrl: null,
      activated: false,
      uniqueness: notEvaluated(),
      graphAcyclic: notEvaluated(),
      routeExistence: notEvaluated(),
      currentRouteEquality: notEvaluated(),
    },
    sitemap: {
      requiredEligibilityFacts: [
        'PUBLISHED',
        'HTTP_200',
        'INDEX_STATE_INDEX',
        'SELF_CANONICAL',
        'NOT_PAUSED',
        'NOT_REDIRECT_SOURCE',
        'CURRENT_PUBLICATION_SNAPSHOT',
      ],
      entries: [],
      serializedDocument: null,
      lastmod: null,
      inclusionEligibility: notEvaluated(),
      generated: false,
      published: false,
    },
    robots: {
      serializedDocument: null,
      runtimeApplied: false,
      routeResponseVerified: false,
    },
    externalAssessments: {
      publicationSnapshotCurrency: notEvaluated(),
      currentPublication: notEvaluated(),
      http200: notEvaluated(),
      runtimeIndexability: notEvaluated(),
      pauseOrRedirectSourceState: notEvaluated(),
    },
    conditionalLocalEligibility: false,
    eligibilityReasons,
    authorization: {
      approval: false,
      publication: false,
      release: false,
      production: false,
      formalEvidence: false,
    },
    boundaries: makeBoundaries(),
    actions: [],
  }) as unknown as PublicSeoRoutePolicyCandidate;
}

function jsonEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function unexpectedProhibitedSurface(
  value: JsonValue | undefined,
  expected: JsonValue | undefined,
): PublicSeoRoutePolicyErrorCode | null {
  if (jsonEqual(value, expected)) return null;
  if (!isJsonObject(value) || !isJsonObject(expected)) return null;
  for (const [key, item] of Object.entries(value)) {
    if (!Object.hasOwn(expected, key)) return scanProhibitedSurface({ [key]: item });
    const nested = unexpectedProhibitedSurface(item, expected[key]);
    if (nested !== null) return nested;
  }
  return null;
}

function candidateInput(value: JsonObject): PublicSeoRoutePolicyInput {
  const screen = value['screen'];
  const coordinate = value['coordinate'];
  const origin = value['origin'];
  if (!isJsonObject(screen) || !isJsonObject(coordinate) || !isJsonObject(origin)) {
    return reject('PUBLIC_SEO_ROUTE_CANDIDATE_INVALID');
  }
  return {
    screenId: screen['id'] as 'PUB-003',
    route: screen['route'] as '/articles/{slug}',
    coordinate: coordinate as unknown as PublicSeoRouteSyntheticCoordinateInput,
    origin: {
      mode: origin['mode'] as PublicSeoRouteOriginMode,
      callerSuppliedOrigin: origin['callerSuppliedOrigin'] as string | null,
    },
  };
}

function classifyCandidateFailure(
  value: JsonObject,
  expected: PublicSeoRoutePolicyCandidate,
): PublicSeoRoutePolicyErrorCode {
  const prohibited = unexpectedProhibitedSurface(value, expected as unknown as JsonValue);
  if (prohibited !== null) return prohibited;
  if (
    !jsonEqual(value['screen'], expected.screen) ||
    !jsonEqual(value['route'], expected.route) ||
    !jsonEqual(value['hashBinding'], expected.hashBinding) ||
    !jsonEqual(value['origin'], expected.origin)
  ) {
    return 'PUBLIC_SEO_ROUTE_METADATA_INVALID';
  }
  if (
    !jsonEqual(value['pagePolicies'], expected.pagePolicies) ||
    !jsonEqual(value['canonical'], expected.canonical) ||
    !jsonEqual(value['sitemap'], expected.sitemap) ||
    !jsonEqual(value['robots'], expected.robots) ||
    !jsonEqual(value['externalAssessments'], expected.externalAssessments) ||
    value['conditionalLocalEligibility'] !== false ||
    !jsonEqual(value['eligibilityReasons'], expected.eligibilityReasons)
  ) {
    return 'PUBLIC_SEO_ROUTE_POLICY_INVALID';
  }
  if (
    !jsonEqual(value['authorization'], expected.authorization) ||
    !jsonEqual(value['boundaries'], expected.boundaries) ||
    !jsonEqual(value['actions'], expected.actions)
  ) {
    return 'PUBLIC_SEO_ROUTE_AUTHORITY_INVALID';
  }
  return 'PUBLIC_SEO_ROUTE_CANDIDATE_INVALID';
}

export function validatePublicSeoRoutePolicyCandidate(
  value: unknown,
): PublicSeoRoutePolicyCandidate {
  const clone = clonePlainObject(value, false);
  let input: PublicSeoRoutePolicyInput;
  try {
    input = validatedInput(candidateInput(clone));
  } catch (error) {
    if (error instanceof PublicSeoRoutePolicyError) throw error;
    return reject('PUBLIC_SEO_ROUTE_CANDIDATE_INVALID');
  }
  const expected = buildCandidate(input);
  if (!jsonEqual(clone, expected)) return reject(classifyCandidateFailure(clone, expected));
  return clone as unknown as PublicSeoRoutePolicyCandidate;
}

export function createPublicSeoRoutePolicyCandidate(
  input: PublicSeoRoutePolicyInput,
): PublicSeoRoutePolicyCandidate {
  return validatePublicSeoRoutePolicyCandidate(buildCandidate(validatedInput(input)));
}
