import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const PUBLIC_ARTICLE_RENDERER_CLASSIFICATION =
  'UNREGISTERED_DISABLED_HEADLESS_PUBLIC_ARTICLE_RENDERER_CANDIDATE' as const;

export const PUBLIC_ARTICLE_RENDERER_SCREEN = Object.freeze({
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
} as const);

export const PUBLIC_ARTICLE_METADATA_BLOCK_TYPES = Object.freeze([
  'heading',
  'paragraph',
  'summary',
  'selection_criteria',
  'pros_cons',
  'suitable_unsuitable',
  'warning',
  'faq_content',
  'source_note',
] as const);

export type PublicArticleMetadataBlockType = (typeof PUBLIC_ARTICLE_METADATA_BLOCK_TYPES)[number];

export const PUBLIC_ARTICLE_RENDERER_ERROR_CODES = Object.freeze([
  'PUBLIC_ARTICLE_INPUT_INVALID',
  'PUBLIC_ARTICLE_SCREEN_INVALID',
  'PUBLIC_ARTICLE_ROUTE_INVALID',
  'PUBLIC_ARTICLE_HASH_INVALID',
  'PUBLIC_ARTICLE_HASH_MISMATCH',
  'PUBLIC_ARTICLE_SLOT_INVALID',
  'PUBLIC_ARTICLE_SLOT_ORDER_INVALID',
  'PUBLIC_ARTICLE_DUPLICATE_BLOCK_KEY',
  'PUBLIC_ARTICLE_CONTENT_PROHIBITED',
  'PUBLIC_ARTICLE_INTERNAL_FIELD_PROHIBITED',
  'PUBLIC_ARTICLE_PROHIBITED_SURFACE',
  'PUBLIC_ARTICLE_METADATA_INVALID',
  'PUBLIC_ARTICLE_AUTHORITY_INVALID',
  'PUBLIC_ARTICLE_CANDIDATE_INVALID',
] as const);

export type PublicArticleRendererErrorCode = (typeof PUBLIC_ARTICLE_RENDERER_ERROR_CODES)[number];

export class PublicArticleRendererError extends TypeError {
  readonly code: PublicArticleRendererErrorCode;

  constructor(code: PublicArticleRendererErrorCode) {
    super(code);
    this.name = 'PublicArticleRendererError';
    this.code = code;
    Object.freeze(this);
  }
}

export interface PublicArticleProjectionCoordinateInput {
  readonly kind: 'SYNTHETIC_PUBLIC_PROJECTION_FIXTURE';
  readonly expectedSha256: string;
  readonly observedSha256: string;
}

export interface PublicArticleMetadataSlotInput {
  readonly blockKey: string;
  readonly blockType: PublicArticleMetadataBlockType;
  readonly position: number;
  readonly headingLevel: 2 | 3 | 4 | null;
  readonly renderedCopy: null;
  readonly renderedHtml: null;
  readonly renderPayload: null;
}

export interface PublicArticleRendererInput {
  readonly screenId: 'PUB-003';
  readonly route: '/articles/{slug}';
  readonly coordinate: PublicArticleProjectionCoordinateInput;
  readonly slots: readonly PublicArticleMetadataSlotInput[];
}

export interface PublicArticleBoundaryResult {
  readonly value: false;
  readonly status: 'NOT_EXECUTED';
  readonly reason: string;
}

export interface PublicArticleRendererBoundaries {
  readonly routeRegistered: PublicArticleBoundaryResult;
  readonly interactive: PublicArticleBoundaryResult;
  readonly dom: PublicArticleBoundaryResult;
  readonly react: PublicArticleBoundaryResult;
  readonly ssr: PublicArticleBoundaryResult;
  readonly api: PublicArticleBoundaryResult;
  readonly network: PublicArticleBoundaryResult;
  readonly database: PublicArticleBoundaryResult;
  readonly publicReadModel: PublicArticleBoundaryResult;
  readonly executableProjection: PublicArticleBoundaryResult;
  readonly authoritativeSnapshot: PublicArticleBoundaryResult;
  readonly contentRendering: PublicArticleBoundaryResult;
  readonly htmlRendering: PublicArticleBoundaryResult;
  readonly schemaMarkup: PublicArticleBoundaryResult;
  readonly browser: PublicArticleBoundaryResult;
  readonly accessibility: PublicArticleBoundaryResult;
  readonly formalTst021: PublicArticleBoundaryResult;
  readonly formalTst022: PublicArticleBoundaryResult;
  readonly formalTst023: PublicArticleBoundaryResult;
  readonly live: PublicArticleBoundaryResult;
  readonly staging: PublicArticleBoundaryResult;
  readonly publicationAuthorization: PublicArticleBoundaryResult;
  readonly release: PublicArticleBoundaryResult;
  readonly production: PublicArticleBoundaryResult;
  readonly localEligibility: PublicArticleBoundaryResult;
}

export interface PublicArticleRendererCandidate {
  readonly classification: typeof PUBLIC_ARTICLE_RENDERER_CLASSIFICATION;
  readonly screen: typeof PUBLIC_ARTICLE_RENDERER_SCREEN;
  readonly route: {
    readonly template: '/articles/{slug}';
    readonly routeRegistered: false;
    readonly interactive: false;
    readonly focusable: false;
  };
  readonly metadata: {
    readonly browserTitle: null;
    readonly description: null;
    readonly robots: {
      readonly index: false;
      readonly follow: false;
      readonly directive: 'noindex,nofollow';
    };
  };
  readonly coordinate: PublicArticleProjectionCoordinateInput;
  readonly hashBinding: {
    readonly profile: 'OPAQUE_CALLER_BOUND_EQUALITY_ONLY';
    readonly expectedSha256: string;
    readonly observedSha256: string;
    readonly equal: true;
    readonly recomputed: false;
    readonly canonicalized: false;
    readonly snapshotVerified: false;
    readonly projectionVerified: false;
    readonly hashesAttested: false;
    readonly formalEvidence: false;
  };
  readonly article: {
    readonly semanticRole: 'article';
    readonly renderable: false;
    readonly interactive: false;
    readonly header: {
      readonly semanticRole: 'header';
      readonly headingLevel: 1;
      readonly renderedCopy: null;
    };
    readonly body: {
      readonly semanticRole: 'body';
      readonly copyAvailable: false;
      readonly slots: readonly PublicArticleMetadataSlotInput[];
    };
  };
  readonly boundaries: PublicArticleRendererBoundaries;
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
  executableProjection: 'ST_0904_EXECUTABLE_PROJECTION_ABSENT',
  authoritativeSnapshot: 'AUTHORITATIVE_SNAPSHOT_ABSENT',
  contentRendering: 'CONTENT_MAPPING_NOT_AUTHORIZED',
  htmlRendering: 'HTML_RENDERING_PROHIBITED',
  schemaMarkup: 'STRUCTURED_DATA_OUT_OF_SCOPE',
  browser: 'BROWSER_NOT_EXECUTED',
  accessibility: 'ACCESSIBILITY_NOT_EXECUTED',
  formalTst021: 'FORMAL_TST_021_NOT_EXECUTED',
  formalTst022: 'FORMAL_TST_022_NOT_EXECUTED',
  formalTst023: 'FORMAL_TST_023_NOT_EXECUTED',
  live: 'LIVE_NOT_AUTHORIZED',
  staging: 'STAGING_NOT_AUTHORIZED',
  publicationAuthorization: 'PUBLICATION_NOT_AUTHORIZED',
  release: 'RELEASE_NOT_AUTHORIZED',
  production: 'PRODUCTION_NOT_AUTHORIZED',
  localEligibility: 'CONTENT_ROUTE_AND_RUNTIME_GATES_UNSATISFIED',
} as const;

const INPUT_KEYS = ['coordinate', 'route', 'screenId', 'slots'] as const;
const COORDINATE_KEYS = ['expectedSha256', 'kind', 'observedSha256'] as const;
const SLOT_KEYS = [
  'blockKey',
  'blockType',
  'headingLevel',
  'position',
  'renderPayload',
  'renderedCopy',
  'renderedHtml',
] as const;
const SHA256 = /^[0-9a-f]{64}$/;
const BLOCK_KEY = /^[a-z][a-z0-9_-]{1,79}$/;
const MAX_SLOTS = 250;
const ABSOLUTE_OR_ACTIVE_SCHEME =
  /^(?:(?:https?|ftp|file|mailto|tel|javascript|data|vbscript):|\/\/)/i;
const ACTIVE_MARKUP = /<\s*(?:script|iframe)\b|\bon[a-z]+\s*=/i;
const CONTENT_KEYS = new Set([
  'browsertitle',
  'content',
  'headingtext',
  'html',
  'renderpayload',
  'renderedcopy',
  'renderedhtml',
  'text',
]);
const INTERNAL_KEY_FRAGMENTS = [
  'approvalid',
  'articleid',
  'claim',
  'evidence',
  'finance',
  'inputhash',
  'internal',
  'publicationid',
  'qualityresult',
  'rawprompt',
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
  'iframe',
  'link',
  'offer',
  'product',
  'script',
  'structureddata',
  'url',
];

function reject(code: PublicArticleRendererErrorCode): never {
  throw new PublicArticleRendererError(code);
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

function scanProhibitedSurface(value: JsonValue): PublicArticleRendererErrorCode | null {
  if (typeof value === 'string') {
    return ABSOLUTE_OR_ACTIVE_SCHEME.test(value) || ACTIVE_MARKUP.test(value)
      ? 'PUBLIC_ARTICLE_PROHIBITED_SURFACE'
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
    if (CONTENT_KEYS.has(normalized) && item !== null) {
      return 'PUBLIC_ARTICLE_CONTENT_PROHIBITED';
    }
    if (INTERNAL_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))) {
      return 'PUBLIC_ARTICLE_INTERNAL_FIELD_PROHIBITED';
    }
    if (
      normalized.startsWith('on') ||
      PROHIBITED_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))
    ) {
      return 'PUBLIC_ARTICLE_PROHIBITED_SURFACE';
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
    return reject('PUBLIC_ARTICLE_INPUT_INVALID');
  }
  let clone: JsonValue;
  try {
    clone = createJsonValue(value);
  } catch {
    return reject('PUBLIC_ARTICLE_INPUT_INVALID');
  }
  if (!isJsonObject(clone)) {
    return reject('PUBLIC_ARTICLE_INPUT_INVALID');
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

function requireCoordinate(value: JsonValue | undefined): PublicArticleProjectionCoordinateInput {
  if (!isJsonObject(value) || !hasExactKeys(value, COORDINATE_KEYS)) {
    return reject('PUBLIC_ARTICLE_INPUT_INVALID');
  }
  const kind = value['kind'];
  const expectedSha256 = value['expectedSha256'];
  const observedSha256 = value['observedSha256'];
  if (kind !== 'SYNTHETIC_PUBLIC_PROJECTION_FIXTURE') {
    return reject('PUBLIC_ARTICLE_INPUT_INVALID');
  }
  if (
    typeof expectedSha256 !== 'string' ||
    typeof observedSha256 !== 'string' ||
    !SHA256.test(expectedSha256) ||
    !SHA256.test(observedSha256)
  ) {
    return reject('PUBLIC_ARTICLE_HASH_INVALID');
  }
  if (expectedSha256 !== observedSha256) {
    return reject('PUBLIC_ARTICLE_HASH_MISMATCH');
  }
  return { kind, expectedSha256, observedSha256 };
}

function requireSlots(value: JsonValue | undefined): readonly PublicArticleMetadataSlotInput[] {
  if (!Array.isArray(value) || value.length > MAX_SLOTS) {
    return reject('PUBLIC_ARTICLE_SLOT_INVALID');
  }
  const slots: PublicArticleMetadataSlotInput[] = [];
  const blockKeys = new Set<string>();
  for (let index = 0; index < value.length; index += 1) {
    const item = value[index];
    if (!isJsonObject(item) || !hasExactKeys(item, SLOT_KEYS)) {
      return reject('PUBLIC_ARTICLE_SLOT_INVALID');
    }
    const blockKey = item['blockKey'];
    const blockType = item['blockType'];
    const position = item['position'];
    const headingLevel = item['headingLevel'];
    if (typeof blockKey !== 'string' || !BLOCK_KEY.test(blockKey)) {
      return reject('PUBLIC_ARTICLE_SLOT_INVALID');
    }
    if (blockKeys.has(blockKey)) {
      return reject('PUBLIC_ARTICLE_DUPLICATE_BLOCK_KEY');
    }
    blockKeys.add(blockKey);
    if (
      typeof blockType !== 'string' ||
      !(PUBLIC_ARTICLE_METADATA_BLOCK_TYPES as readonly string[]).includes(blockType)
    ) {
      return reject('PUBLIC_ARTICLE_SLOT_INVALID');
    }
    if (!Number.isSafeInteger(position) || position !== index) {
      return reject('PUBLIC_ARTICLE_SLOT_ORDER_INVALID');
    }
    if (
      (blockType === 'heading' && ![2, 3, 4].includes(headingLevel as number)) ||
      (blockType !== 'heading' && headingLevel !== null)
    ) {
      return reject('PUBLIC_ARTICLE_SLOT_INVALID');
    }
    if (
      item['renderedCopy'] !== null ||
      item['renderedHtml'] !== null ||
      item['renderPayload'] !== null
    ) {
      return reject('PUBLIC_ARTICLE_CONTENT_PROHIBITED');
    }
    slots.push({
      blockKey,
      blockType: blockType as PublicArticleMetadataBlockType,
      position,
      headingLevel: headingLevel as 2 | 3 | 4 | null,
      renderedCopy: null,
      renderedHtml: null,
      renderPayload: null,
    });
  }
  return slots;
}

function validatedInput(input: PublicArticleRendererInput): PublicArticleRendererInput {
  const value = clonePlainObject(input);
  if (!hasExactKeys(value, INPUT_KEYS)) {
    return reject('PUBLIC_ARTICLE_INPUT_INVALID');
  }
  if (value['screenId'] !== 'PUB-003') {
    return reject('PUBLIC_ARTICLE_SCREEN_INVALID');
  }
  if (value['route'] !== '/articles/{slug}') {
    return reject('PUBLIC_ARTICLE_ROUTE_INVALID');
  }
  return {
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: requireCoordinate(value['coordinate']),
    slots: requireSlots(value['slots']),
  };
}

function makeBoundaries(): PublicArticleRendererBoundaries {
  return Object.fromEntries(
    Object.entries(boundaryReasons).map(([key, reason]) => [
      key,
      { value: false, status: 'NOT_EXECUTED', reason },
    ]),
  ) as unknown as PublicArticleRendererBoundaries;
}

function buildCandidate(input: PublicArticleRendererInput): PublicArticleRendererCandidate {
  return createJsonValue({
    classification: PUBLIC_ARTICLE_RENDERER_CLASSIFICATION,
    screen: PUBLIC_ARTICLE_RENDERER_SCREEN,
    route: {
      template: input.route,
      routeRegistered: false,
      interactive: false,
      focusable: false,
    },
    metadata: {
      browserTitle: null,
      description: null,
      robots: { index: false, follow: false, directive: 'noindex,nofollow' },
    },
    coordinate: input.coordinate,
    hashBinding: {
      profile: 'OPAQUE_CALLER_BOUND_EQUALITY_ONLY',
      expectedSha256: input.coordinate.expectedSha256,
      observedSha256: input.coordinate.observedSha256,
      equal: true,
      recomputed: false,
      canonicalized: false,
      snapshotVerified: false,
      projectionVerified: false,
      hashesAttested: false,
      formalEvidence: false,
    },
    article: {
      semanticRole: 'article',
      renderable: false,
      interactive: false,
      header: { semanticRole: 'header', headingLevel: 1, renderedCopy: null },
      body: {
        semanticRole: 'body',
        copyAvailable: false,
        slots: input.slots,
      },
    },
    boundaries: makeBoundaries(),
    actions: [],
  }) as unknown as PublicArticleRendererCandidate;
}

function jsonEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function unexpectedProhibitedSurface(
  value: JsonValue | undefined,
  expected: JsonValue | undefined,
): PublicArticleRendererErrorCode | null {
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
    const expectedItem = expected[key];
    const normalized = normalizedKey(key);
    if (CONTENT_KEYS.has(normalized) && item !== null && !jsonEqual(item, expectedItem)) {
      return 'PUBLIC_ARTICLE_CONTENT_PROHIBITED';
    }
    const nested = unexpectedProhibitedSurface(item, expectedItem);
    if (nested !== null) {
      return nested;
    }
  }
  return null;
}

function candidateInput(value: JsonObject): PublicArticleRendererInput {
  const screen = value['screen'];
  const coordinate = value['coordinate'];
  const article = value['article'];
  if (!isJsonObject(screen) || !isJsonObject(coordinate) || !isJsonObject(article)) {
    return reject('PUBLIC_ARTICLE_CANDIDATE_INVALID');
  }
  const body = article['body'];
  if (!isJsonObject(body)) {
    return reject('PUBLIC_ARTICLE_CANDIDATE_INVALID');
  }
  return {
    screenId: screen['id'] as 'PUB-003',
    route: screen['route'] as '/articles/{slug}',
    coordinate: coordinate as unknown as PublicArticleProjectionCoordinateInput,
    slots: body['slots'] as unknown as readonly PublicArticleMetadataSlotInput[],
  };
}

function classifyCandidateFailure(
  value: JsonObject,
  expected: PublicArticleRendererCandidate,
): PublicArticleRendererErrorCode {
  const prohibited = unexpectedProhibitedSurface(value, expected as unknown as JsonValue);
  if (prohibited !== null) {
    return prohibited;
  }
  if (
    !jsonEqual(value['screen'], expected.screen) ||
    !jsonEqual(value['route'], expected.route) ||
    !jsonEqual(value['metadata'], expected.metadata)
  ) {
    return 'PUBLIC_ARTICLE_METADATA_INVALID';
  }
  if (
    !jsonEqual(value['boundaries'], expected.boundaries) ||
    !jsonEqual(value['actions'], expected.actions)
  ) {
    return 'PUBLIC_ARTICLE_AUTHORITY_INVALID';
  }
  return 'PUBLIC_ARTICLE_CANDIDATE_INVALID';
}

export function validatePublicArticleRendererCandidate(
  value: unknown,
): PublicArticleRendererCandidate {
  const clone = clonePlainObject(value, false);
  let input: PublicArticleRendererInput;
  try {
    input = validatedInput(candidateInput(clone));
  } catch (error) {
    if (error instanceof PublicArticleRendererError) {
      throw error;
    }
    return reject('PUBLIC_ARTICLE_CANDIDATE_INVALID');
  }
  const expected = buildCandidate(input);
  if (!jsonEqual(clone, expected)) {
    return reject(classifyCandidateFailure(clone, expected));
  }
  return clone as unknown as PublicArticleRendererCandidate;
}

export function createPublicArticleRendererCandidate(
  input: PublicArticleRendererInput,
): PublicArticleRendererCandidate {
  return validatePublicArticleRendererCandidate(buildCandidate(validatedInput(input)));
}
