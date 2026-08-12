import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const PUBLIC_COMPARISON_COMPONENT_CLASSIFICATION =
  'UNREGISTERED_DISABLED_HEADLESS_ST1003_SEMANTIC_METADATA_CANDIDATE' as const;

export const PUBLIC_COMPARISON_COMPONENT_IDS = Object.freeze([
  'UI-C032',
  'UI-C033',
  'UI-C036',
] as const);

export type PublicComparisonComponentId = (typeof PUBLIC_COMPARISON_COMPONENT_IDS)[number];

export const PUBLIC_COMPARISON_COMPONENT_ERROR_CODES = Object.freeze([
  'PUBLIC_COMPONENT_INPUT_INVALID',
  'PUBLIC_COMPONENT_SCREEN_INVALID',
  'PUBLIC_COMPONENT_ROUTE_INVALID',
  'PUBLIC_COMPONENT_COORDINATE_INVALID',
  'PUBLIC_COMPONENT_HASH_INVALID',
  'PUBLIC_COMPONENT_HASH_MISMATCH',
  'PUBLIC_COMPONENT_CONTENT_PROHIBITED',
  'PUBLIC_COMPONENT_REFERENCE_PROHIBITED',
  'PUBLIC_COMPONENT_INTERNAL_FIELD_PROHIBITED',
  'PUBLIC_COMPONENT_PROHIBITED_SURFACE',
  'PUBLIC_COMPONENT_METADATA_INVALID',
  'PUBLIC_COMPONENT_SEMANTICS_INVALID',
  'PUBLIC_COMPONENT_AUTHORITY_INVALID',
  'PUBLIC_COMPONENT_CANDIDATE_INVALID',
] as const);

export type PublicComparisonComponentErrorCode =
  (typeof PUBLIC_COMPARISON_COMPONENT_ERROR_CODES)[number];

export class PublicComparisonComponentError extends TypeError {
  readonly code: PublicComparisonComponentErrorCode;

  constructor(code: PublicComparisonComponentErrorCode) {
    super(code);
    this.name = 'PublicComparisonComponentError';
    this.code = code;
    Object.freeze(this);
  }
}

export interface PublicComparisonComponentMetadata {
  readonly id: PublicComparisonComponentId;
  readonly name: 'ProductCard' | 'ComparisonTable' | 'UnknownValue';
  readonly area: 'public' | 'shared';
  readonly purpose: string;
  readonly keyboardRequired: true;
  readonly screenReaderRequired: true;
  readonly designStatus: 'APPROVED_FOR_IMPLEMENTATION';
  readonly implementationStatus: 'NOT_STARTED';
  readonly runtimeVerification: 'NOT_EXECUTED';
}

const componentSource = [
  {
    id: 'UI-C032',
    name: 'ProductCard',
    area: 'public',
    purpose: '商品名、Verified Fact、CTA、更新時刻',
    keyboardRequired: true,
    screenReaderRequired: true,
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'UI-C033',
    name: 'ComparisonTable',
    area: 'public',
    purpose: 'Responsiveな比較表',
    keyboardRequired: true,
    screenReaderRequired: true,
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'UI-C036',
    name: 'UnknownValue',
    area: 'shared',
    purpose: '欠損を推測せず表示',
    keyboardRequired: true,
    screenReaderRequired: true,
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
] as const;

export const PUBLIC_COMPARISON_COMPONENTS = createJsonValue(
  componentSource,
) as unknown as readonly PublicComparisonComponentMetadata[];

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

export const PUBLIC_COMPARISON_COMPONENT_SCREEN = createJsonValue(
  screenSource,
) as unknown as typeof screenSource;

export interface PublicComparisonSyntheticCoordinateInput {
  readonly kind: 'SYNTHETIC_ST1003_SEMANTIC_FIXTURE';
  readonly expectedSha256: string;
  readonly observedSha256: string;
}

export interface PublicComparisonComponentsInput {
  readonly screenId: 'PUB-003';
  readonly route: '/articles/{slug}';
  readonly coordinate: PublicComparisonSyntheticCoordinateInput;
}

export interface PublicComparisonBoundaryResult {
  readonly value: false;
  readonly status: 'NOT_EXECUTED';
  readonly reason: string;
}

export interface PublicComparisonComponentBoundaries {
  readonly routeRegistered: PublicComparisonBoundaryResult;
  readonly interactive: PublicComparisonBoundaryResult;
  readonly dom: PublicComparisonBoundaryResult;
  readonly react: PublicComparisonBoundaryResult;
  readonly api: PublicComparisonBoundaryResult;
  readonly network: PublicComparisonBoundaryResult;
  readonly database: PublicComparisonBoundaryResult;
  readonly publicReadModel: PublicComparisonBoundaryResult;
  readonly st1002ContentMapping: PublicComparisonBoundaryResult;
  readonly st0803ValueMapping: PublicComparisonBoundaryResult;
  readonly productIdentity: PublicComparisonBoundaryResult;
  readonly valueRendering: PublicComparisonBoundaryResult;
  readonly mobileRendering: PublicComparisonBoundaryResult;
  readonly headerAssociationVerification: PublicComparisonBoundaryResult;
  readonly recommendation: PublicComparisonBoundaryResult;
  readonly affiliateCta: PublicComparisonBoundaryResult;
  readonly disclosure: PublicComparisonBoundaryResult;
  readonly browser: PublicComparisonBoundaryResult;
  readonly accessibility: PublicComparisonBoundaryResult;
  readonly formalTst022: PublicComparisonBoundaryResult;
  readonly formalTst024: PublicComparisonBoundaryResult;
  readonly live: PublicComparisonBoundaryResult;
  readonly staging: PublicComparisonBoundaryResult;
  readonly publicationAuthorization: PublicComparisonBoundaryResult;
  readonly release: PublicComparisonBoundaryResult;
  readonly production: PublicComparisonBoundaryResult;
  readonly localEligibility: PublicComparisonBoundaryResult;
}

interface UnavailableValue<T extends null = null> {
  readonly available: false;
  readonly value: T;
}

interface UnavailableCopy {
  readonly available: false;
  readonly renderedCopy: null;
}

export interface PublicProductCardSemanticMetadata {
  readonly componentId: 'UI-C032';
  readonly renderable: false;
  readonly interactive: false;
  readonly productIdentityRef: null;
  readonly recommendationRef: null;
  readonly displayPolicyRef: null;
  readonly productName: UnavailableValue;
  readonly verifiedFacts: UnavailableValue;
  readonly image: {
    readonly available: false;
    readonly source: null;
    readonly alternativeText: null;
  };
  readonly price: UnavailableValue;
  readonly freshness: UnavailableValue;
  readonly offers: UnavailableValue;
  readonly affiliateCta: UnavailableValue;
}

export interface PublicComparisonTableSemanticMetadata {
  readonly componentId: 'UI-C033';
  readonly renderable: false;
  readonly interactive: false;
  readonly comparisonTableRef: null;
  readonly comparisonAxisRefs: null;
  readonly productSelectionRefs: null;
  readonly matrix: UnavailableValue;
  readonly caption: {
    readonly required: true;
    readonly renderedCopy: null;
  };
  readonly headerAssociation: {
    readonly required: true;
    readonly rowHeadersRequired: true;
    readonly columnHeadersRequired: true;
    readonly captionHeadersAndScopeRequired: true;
    readonly domStatus: 'DOM_NOT_IMPLEMENTED';
    readonly verificationStatus: 'NOT_VERIFIED';
  };
  readonly mobileRelationship: {
    readonly productAndAxisRelationshipMustBePreserved: true;
    readonly selectedPresentation: null;
    readonly layoutDecisionStatus: 'UNAVAILABLE';
    readonly domStatus: 'DOM_NOT_IMPLEMENTED';
    readonly verificationStatus: 'NOT_VERIFIED';
  };
}

export interface PublicUnknownValueSemanticMetadata {
  readonly componentId: 'UI-C036';
  readonly renderable: false;
  readonly visibilityRequirement: 'MUST_REMAIN_VISIBLE_WHEN_RENDERED';
  readonly imputationAllowed: false;
  readonly zeroSubstitutionAllowed: false;
  readonly emptyStringSubstitutionAllowed: false;
  readonly value: null;
  readonly renderedCopy: null;
  readonly reason: null;
}

export interface PublicTradeoffSemanticMetadata {
  readonly catalogComponentId: null;
  readonly blockType: 'tradeoff';
  readonly renderable: false;
  readonly claimRefs: null;
  readonly subjectRef: null;
  readonly slots: {
    readonly benefit: UnavailableCopy;
    readonly costOrLimitation: UnavailableCopy;
    readonly appliesWhen: UnavailableCopy;
  };
}

export interface PublicComparisonComponentsCandidate {
  readonly classification: typeof PUBLIC_COMPARISON_COMPONENT_CLASSIFICATION;
  readonly screen: typeof PUBLIC_COMPARISON_COMPONENT_SCREEN;
  readonly route: {
    readonly template: '/articles/{slug}';
    readonly routeRegistered: false;
    readonly interactive: false;
    readonly focusable: false;
  };
  readonly coordinate: PublicComparisonSyntheticCoordinateInput;
  readonly hashBinding: {
    readonly profile: 'OPAQUE_CALLER_BOUND_EQUALITY_ONLY';
    readonly expectedSha256: string;
    readonly observedSha256: string;
    readonly equal: true;
    readonly recomputed: false;
    readonly canonicalized: false;
    readonly publicProjectionVerified: false;
    readonly comparisonVerified: false;
    readonly hashesAttested: false;
    readonly formalEvidence: false;
  };
  readonly components: readonly PublicComparisonComponentMetadata[];
  readonly semantics: {
    readonly productCard: PublicProductCardSemanticMetadata;
    readonly comparisonTable: PublicComparisonTableSemanticMetadata;
    readonly unknownValue: PublicUnknownValueSemanticMetadata;
    readonly tradeoff: PublicTradeoffSemanticMetadata;
  };
  readonly boundaries: PublicComparisonComponentBoundaries;
  readonly actions: readonly [];
}

const boundaryReasons = {
  routeRegistered: 'NO_RUNTIME_ROUTE_REGISTERED',
  interactive: 'INTERACTION_DISABLED',
  dom: 'DOM_NOT_IMPLEMENTED',
  react: 'REACT_NOT_IMPLEMENTED',
  api: 'PUBLIC_API_NOT_CONNECTED',
  network: 'NETWORK_NOT_USED',
  database: 'DATABASE_NOT_USED',
  publicReadModel: 'PUBLIC_READMODEL_NOT_CONNECTED',
  st1002ContentMapping: 'ST_1002_CONTENT_MAPPING_UNAVAILABLE',
  st0803ValueMapping: 'ST_0803_TEST_ONLY_VALUES_NOT_PUBLIC_INPUT',
  productIdentity: 'PRODUCT_IDENTITY_UNAVAILABLE',
  valueRendering: 'VALUE_AND_COPY_RENDERING_PROHIBITED',
  mobileRendering: 'MOBILE_PRESENTATION_NOT_SELECTED_OR_RENDERED',
  headerAssociationVerification: 'DOM_HEADER_ASSOCIATION_NOT_VERIFIED',
  recommendation: 'RECOMMENDATION_NOT_AVAILABLE',
  affiliateCta: 'AFFILIATE_CTA_OUT_OF_SCOPE',
  disclosure: 'DISCLOSURE_OUT_OF_SCOPE',
  browser: 'BROWSER_NOT_EXECUTED',
  accessibility: 'ACCESSIBILITY_NOT_EXECUTED',
  formalTst022: 'FORMAL_TST_022_NOT_EXECUTED',
  formalTst024: 'FORMAL_TST_024_NOT_EXECUTED',
  live: 'LIVE_NOT_AUTHORIZED',
  staging: 'STAGING_NOT_AUTHORIZED',
  publicationAuthorization: 'PUBLICATION_NOT_AUTHORIZED',
  release: 'RELEASE_NOT_AUTHORIZED',
  production: 'PRODUCTION_NOT_AUTHORIZED',
  localEligibility: 'CONTENT_DOM_AND_RUNTIME_GATES_UNSATISFIED',
} as const;

const INPUT_KEYS = ['coordinate', 'route', 'screenId'] as const;
const COORDINATE_KEYS = ['expectedSha256', 'kind', 'observedSha256'] as const;
const SHA256 = /^[0-9a-f]{64}$/;
const ABSOLUTE_OR_ACTIVE_SCHEME =
  /^(?:(?:https?|ftp|file|mailto|tel|javascript|data|vbscript):|\/\/)/i;
const ACTIVE_MARKUP = /<\s*(?:script|iframe)\b|\bon[a-z]+\s*=/i;
const CONTENT_KEY_FRAGMENTS = [
  'availability',
  'axis',
  'badge',
  'benefit',
  'caption',
  'copy',
  'displayname',
  'fact',
  'freshness',
  'header',
  'identity',
  'image',
  'limitation',
  'matrix',
  'offer',
  'price',
  'product',
  'recommendation',
  'text',
  'tradeoff',
  'value',
];
const REFERENCE_KEY_FRAGMENTS = [
  'claimref',
  'comparisonref',
  'evidenceref',
  'productref',
  'recommendationref',
  'sourceref',
  'subjectref',
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
const PROHIBITED_KEY_FRAGMENTS = [
  'affiliate',
  'analytics',
  'beacon',
  'callback',
  'cookie',
  'cta',
  'disclosure',
  'href',
  'html',
  'release',
  'script',
  'structureddata',
  'url',
];

function reject(code: PublicComparisonComponentErrorCode): never {
  throw new PublicComparisonComponentError(code);
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

function scanProhibitedSurface(value: JsonValue): PublicComparisonComponentErrorCode | null {
  if (typeof value === 'string') {
    return ABSOLUTE_OR_ACTIVE_SCHEME.test(value) || ACTIVE_MARKUP.test(value)
      ? 'PUBLIC_COMPONENT_PROHIBITED_SURFACE'
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
    if (REFERENCE_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))) {
      return 'PUBLIC_COMPONENT_REFERENCE_PROHIBITED';
    }
    if (INTERNAL_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))) {
      return 'PUBLIC_COMPONENT_INTERNAL_FIELD_PROHIBITED';
    }
    if (CONTENT_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))) {
      return 'PUBLIC_COMPONENT_CONTENT_PROHIBITED';
    }
    if (
      normalized.startsWith('on') ||
      PROHIBITED_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))
    ) {
      return 'PUBLIC_COMPONENT_PROHIBITED_SURFACE';
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
    return reject('PUBLIC_COMPONENT_INPUT_INVALID');
  }
  let clone: JsonValue;
  try {
    clone = createJsonValue(value);
  } catch {
    return reject('PUBLIC_COMPONENT_INPUT_INVALID');
  }
  if (!isJsonObject(clone)) {
    return reject('PUBLIC_COMPONENT_INPUT_INVALID');
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

function requireCoordinate(value: JsonValue | undefined): PublicComparisonSyntheticCoordinateInput {
  if (!isJsonObject(value) || !hasExactKeys(value, COORDINATE_KEYS)) {
    return reject('PUBLIC_COMPONENT_COORDINATE_INVALID');
  }
  const kind = value['kind'];
  const expectedSha256 = value['expectedSha256'];
  const observedSha256 = value['observedSha256'];
  if (kind !== 'SYNTHETIC_ST1003_SEMANTIC_FIXTURE') {
    return reject('PUBLIC_COMPONENT_COORDINATE_INVALID');
  }
  if (
    typeof expectedSha256 !== 'string' ||
    typeof observedSha256 !== 'string' ||
    !SHA256.test(expectedSha256) ||
    !SHA256.test(observedSha256)
  ) {
    return reject('PUBLIC_COMPONENT_HASH_INVALID');
  }
  if (expectedSha256 !== observedSha256) {
    return reject('PUBLIC_COMPONENT_HASH_MISMATCH');
  }
  return { kind, expectedSha256, observedSha256 };
}

function validatedInput(input: PublicComparisonComponentsInput): PublicComparisonComponentsInput {
  const value = clonePlainObject(input);
  if (!hasExactKeys(value, INPUT_KEYS)) {
    return reject('PUBLIC_COMPONENT_INPUT_INVALID');
  }
  if (value['screenId'] !== 'PUB-003') {
    return reject('PUBLIC_COMPONENT_SCREEN_INVALID');
  }
  if (value['route'] !== '/articles/{slug}') {
    return reject('PUBLIC_COMPONENT_ROUTE_INVALID');
  }
  return {
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: requireCoordinate(value['coordinate']),
  };
}

function makeBoundaries(): PublicComparisonComponentBoundaries {
  return Object.fromEntries(
    Object.entries(boundaryReasons).map(([key, reason]) => [
      key,
      { value: false, status: 'NOT_EXECUTED', reason },
    ]),
  ) as unknown as PublicComparisonComponentBoundaries;
}

function buildCandidate(
  input: PublicComparisonComponentsInput,
): PublicComparisonComponentsCandidate {
  return createJsonValue({
    classification: PUBLIC_COMPARISON_COMPONENT_CLASSIFICATION,
    screen: PUBLIC_COMPARISON_COMPONENT_SCREEN,
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
      comparisonVerified: false,
      hashesAttested: false,
      formalEvidence: false,
    },
    components: PUBLIC_COMPARISON_COMPONENTS,
    semantics: {
      productCard: {
        componentId: 'UI-C032',
        renderable: false,
        interactive: false,
        productIdentityRef: null,
        recommendationRef: null,
        displayPolicyRef: null,
        productName: { available: false, value: null },
        verifiedFacts: { available: false, value: null },
        image: { available: false, source: null, alternativeText: null },
        price: { available: false, value: null },
        freshness: { available: false, value: null },
        offers: { available: false, value: null },
        affiliateCta: { available: false, value: null },
      },
      comparisonTable: {
        componentId: 'UI-C033',
        renderable: false,
        interactive: false,
        comparisonTableRef: null,
        comparisonAxisRefs: null,
        productSelectionRefs: null,
        matrix: { available: false, value: null },
        caption: { required: true, renderedCopy: null },
        headerAssociation: {
          required: true,
          rowHeadersRequired: true,
          columnHeadersRequired: true,
          captionHeadersAndScopeRequired: true,
          domStatus: 'DOM_NOT_IMPLEMENTED',
          verificationStatus: 'NOT_VERIFIED',
        },
        mobileRelationship: {
          productAndAxisRelationshipMustBePreserved: true,
          selectedPresentation: null,
          layoutDecisionStatus: 'UNAVAILABLE',
          domStatus: 'DOM_NOT_IMPLEMENTED',
          verificationStatus: 'NOT_VERIFIED',
        },
      },
      unknownValue: {
        componentId: 'UI-C036',
        renderable: false,
        visibilityRequirement: 'MUST_REMAIN_VISIBLE_WHEN_RENDERED',
        imputationAllowed: false,
        zeroSubstitutionAllowed: false,
        emptyStringSubstitutionAllowed: false,
        value: null,
        renderedCopy: null,
        reason: null,
      },
      tradeoff: {
        catalogComponentId: null,
        blockType: 'tradeoff',
        renderable: false,
        claimRefs: null,
        subjectRef: null,
        slots: {
          benefit: { available: false, renderedCopy: null },
          costOrLimitation: { available: false, renderedCopy: null },
          appliesWhen: { available: false, renderedCopy: null },
        },
      },
    },
    boundaries: makeBoundaries(),
    actions: [],
  }) as unknown as PublicComparisonComponentsCandidate;
}

function jsonEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function unexpectedProhibitedSurface(
  value: JsonValue | undefined,
  expected: JsonValue | undefined,
): PublicComparisonComponentErrorCode | null {
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

function candidateInput(value: JsonObject): PublicComparisonComponentsInput {
  const screen = value['screen'];
  const coordinate = value['coordinate'];
  if (!isJsonObject(screen) || !isJsonObject(coordinate)) {
    return reject('PUBLIC_COMPONENT_CANDIDATE_INVALID');
  }
  return {
    screenId: screen['id'] as 'PUB-003',
    route: screen['route'] as '/articles/{slug}',
    coordinate: coordinate as unknown as PublicComparisonSyntheticCoordinateInput,
  };
}

function classifyCandidateFailure(
  value: JsonObject,
  expected: PublicComparisonComponentsCandidate,
): PublicComparisonComponentErrorCode {
  const prohibited = unexpectedProhibitedSurface(value, expected as unknown as JsonValue);
  if (prohibited !== null) {
    return prohibited;
  }
  if (
    !jsonEqual(value['screen'], expected.screen) ||
    !jsonEqual(value['route'], expected.route) ||
    !jsonEqual(value['components'], expected.components)
  ) {
    return 'PUBLIC_COMPONENT_METADATA_INVALID';
  }
  if (!jsonEqual(value['semantics'], expected.semantics)) {
    return 'PUBLIC_COMPONENT_SEMANTICS_INVALID';
  }
  if (
    !jsonEqual(value['boundaries'], expected.boundaries) ||
    !jsonEqual(value['actions'], expected.actions)
  ) {
    return 'PUBLIC_COMPONENT_AUTHORITY_INVALID';
  }
  return 'PUBLIC_COMPONENT_CANDIDATE_INVALID';
}

export function validatePublicComparisonComponentsCandidate(
  value: unknown,
): PublicComparisonComponentsCandidate {
  const clone = clonePlainObject(value, false);
  let input: PublicComparisonComponentsInput;
  try {
    input = validatedInput(candidateInput(clone));
  } catch (error) {
    if (error instanceof PublicComparisonComponentError) {
      throw error;
    }
    return reject('PUBLIC_COMPONENT_CANDIDATE_INVALID');
  }
  const expected = buildCandidate(input);
  if (!jsonEqual(clone, expected)) {
    return reject(classifyCandidateFailure(clone, expected));
  }
  return clone as unknown as PublicComparisonComponentsCandidate;
}

export function createPublicComparisonComponentsCandidate(
  input: PublicComparisonComponentsInput,
): PublicComparisonComponentsCandidate {
  return validatePublicComparisonComponentsCandidate(buildCandidate(validatedInput(input)));
}
