import {
  ST1102_RECORDED_WORKSPACE_V2_JSON,
  ST1102_RECORDED_WORKSPACE_V2_SHA256,
} from './article-workspace-recorded.v2.ts';
import {
  ARTICLE_WORKSPACE_SCREEN_IDS,
  ARTICLE_WORKSPACE_SCREENS,
  type ArticleWorkspaceScreenId,
  type ArticleWorkspaceScreenMetadata,
} from './article-workspace.ts';
import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const ARTICLE_WORKSPACE_V2_CLASSIFICATION =
  'LOCAL_EXECUTABLE_RECORDED_ARTICLE_WORKSPACE_V2' as const;

export const ARTICLE_WORKSPACE_V2_PROJECTION_IDS = createJsonValue([
  'AST',
  'AI_DIFF',
  'CLAIMS',
  'COMPARISON',
  'SEO',
]) as unknown as readonly ['AST', 'AI_DIFF', 'CLAIMS', 'COMPARISON', 'SEO'];

export type ArticleWorkspaceV2ProjectionId = (typeof ARTICLE_WORKSPACE_V2_PROJECTION_IDS)[number];

export const ARTICLE_WORKSPACE_V2_ERROR_CODES = createJsonValue([
  'ARTICLE_WORKSPACE_V2_INPUT_INVALID',
  'ARTICLE_WORKSPACE_V2_SCREEN_UNKNOWN',
  'ARTICLE_WORKSPACE_V2_FIXTURE_INVALID',
  'ARTICLE_WORKSPACE_V2_BINDING_INVALID',
  'ARTICLE_WORKSPACE_V2_PROJECTION_INVALID',
  'ARTICLE_WORKSPACE_V2_MODEL_INVALID',
  'ARTICLE_WORKSPACE_V2_PROHIBITED_SURFACE',
  'ARTICLE_WORKSPACE_V2_ETAG_INPUT_INVALID',
  'ARTICLE_WORKSPACE_V2_ETAG_INVALID',
  'ARTICLE_WORKSPACE_V2_UNSAVED_INPUT_INVALID',
  'ARTICLE_WORKSPACE_V2_AST_SHA256_INVALID',
]) as unknown as readonly [
  'ARTICLE_WORKSPACE_V2_INPUT_INVALID',
  'ARTICLE_WORKSPACE_V2_SCREEN_UNKNOWN',
  'ARTICLE_WORKSPACE_V2_FIXTURE_INVALID',
  'ARTICLE_WORKSPACE_V2_BINDING_INVALID',
  'ARTICLE_WORKSPACE_V2_PROJECTION_INVALID',
  'ARTICLE_WORKSPACE_V2_MODEL_INVALID',
  'ARTICLE_WORKSPACE_V2_PROHIBITED_SURFACE',
  'ARTICLE_WORKSPACE_V2_ETAG_INPUT_INVALID',
  'ARTICLE_WORKSPACE_V2_ETAG_INVALID',
  'ARTICLE_WORKSPACE_V2_UNSAVED_INPUT_INVALID',
  'ARTICLE_WORKSPACE_V2_AST_SHA256_INVALID',
];

export type ArticleWorkspaceV2ErrorCode = (typeof ARTICLE_WORKSPACE_V2_ERROR_CODES)[number];

export class ArticleWorkspaceV2Error extends TypeError {
  readonly code: ArticleWorkspaceV2ErrorCode;

  constructor(code: ArticleWorkspaceV2ErrorCode) {
    const closed = (ARTICLE_WORKSPACE_V2_ERROR_CODES as readonly unknown[]).includes(code)
      ? code
      : 'ARTICLE_WORKSPACE_V2_MODEL_INVALID';
    super(closed);
    this.name = 'ArticleWorkspaceV2Error';
    this.code = closed;
    Object.freeze(this);
  }
}

export interface ArticleWorkspaceV2Input {
  readonly screenId: ArticleWorkspaceScreenId;
}

export interface ArticleWorkspaceV2StatusCue {
  readonly code: 'AVAILABLE_RECORDED' | 'PARTIAL_RECORDED';
  readonly text: string;
  readonly icon: string;
  readonly colorOnly: false;
}

export interface ArticleWorkspaceV2Projection {
  readonly status: 'AVAILABLE_RECORDED' | 'PARTIAL_RECORDED';
  readonly sourceStoryIds: readonly string[];
  readonly componentIds: readonly string[];
  readonly payload: JsonObject;
  readonly statusCue: ArticleWorkspaceV2StatusCue;
}

export interface ArticleWorkspaceV2Model {
  readonly classification: typeof ARTICLE_WORKSPACE_V2_CLASSIFICATION;
  readonly storyId: 'ST-1102';
  readonly localStatus: 'LOCAL_IMPLEMENTATION_COMPLETE';
  readonly canonicalStatus: {
    readonly implementation: 'NOT_STARTED';
    readonly verification: 'NOT_EXECUTED';
  };
  readonly sourceMode: 'RECORDED_SYNTHETIC_DEV_CI_ONLY';
  readonly sourceFixtureSha256: string;
  readonly screen: ArticleWorkspaceScreenMetadata;
  readonly screenOrder: typeof ARTICLE_WORKSPACE_SCREEN_IDS;
  readonly article: JsonObject;
  readonly header: JsonObject;
  readonly paneOrder: readonly ArticleWorkspaceV2ProjectionId[];
  readonly panes: readonly ArticleWorkspaceV2Projection[];
  readonly route: {
    readonly registered: false;
    readonly renderEnabled: false;
    readonly status: 'DISABLED_AUTH_TRANSPORT_UNRESOLVED';
    readonly roleMetadataOnly: true;
  };
  readonly concurrency: {
    readonly baselineEtag: string;
    readonly ifMatchRequired: true;
    readonly evaluatorAvailable: true;
    readonly overwriteAllowed: false;
    readonly automaticMergeAllowed: false;
    readonly saveCommandAvailable: false;
    readonly dispatch: 'NOT_EXECUTED';
    readonly persistence: 'NOT_EXECUTED';
  };
  readonly unsavedGuard: {
    readonly componentId: 'UI-C014';
    readonly evaluatorAvailable: true;
    readonly navigationInterceptionImplemented: false;
    readonly navigationEffectEnabled: false;
    readonly saveAuthorized: false;
    readonly discardAuthorized: false;
  };
  readonly accessibility: {
    readonly candidateOnly: true;
    readonly semanticOrder: readonly [
      'skip-link',
      'header',
      'navigation',
      'main',
      'error-summary',
      'workspace-tabs',
      'pane-region',
      'footer',
    ];
    readonly semanticIds: {
      readonly skipLink: 'article-workspace-v2-skip-link';
      readonly header: 'article-workspace-v2-header';
      readonly navigation: 'article-workspace-v2-navigation';
      readonly main: 'article-workspace-v2-main';
      readonly heading: 'article-workspace-v2-heading';
      readonly errorSummary: 'article-workspace-v2-error-summary';
      readonly workspaceTabs: 'article-workspace-v2-tabs';
      readonly paneRegion: 'article-workspace-v2-pane';
      readonly footer: 'article-workspace-v2-footer';
      readonly unsavedDialog: 'article-workspace-v2-unsaved-dialog';
    };
    readonly h1: {
      readonly count: 1;
      readonly level: 1;
      readonly textSource: 'SCREEN_NAME';
    };
    readonly keyboardModel: readonly [
      'Tab',
      'Shift+Tab',
      'ArrowLeft',
      'ArrowRight',
      'Home',
      'End',
      'Escape',
    ];
    readonly statusTextPresent: true;
    readonly statusCodePresent: true;
    readonly statusIconPresent: true;
    readonly statusNotColorOnly: true;
    readonly tableCaptionRequired: true;
    readonly columnHeadersRequired: true;
    readonly rowHeaderRequired: true;
    readonly zoomTargetPercent: 200;
    readonly rendered: false;
    readonly browserVerified: false;
    readonly screenReaderVerified: false;
  };
  readonly security: JsonObject;
  readonly authority: JsonObject;
  readonly verification: {
    readonly localModel: 'EXECUTED';
    readonly TST_022: 'NOT_EXECUTED';
    readonly TST_024: 'NOT_EXECUTED';
    readonly formalValidation: 'NOT_EXECUTED';
    readonly browser: 'NOT_EXECUTED';
    readonly keyboard: 'NOT_EXECUTED';
    readonly zoom: 'NOT_EXECUTED';
    readonly screenReader: 'NOT_EXECUTED';
    readonly hostedCi: 'NOT_EXECUTED';
    readonly live: 'NOT_EXECUTED';
    readonly staging: 'NOT_EXECUTED';
    readonly release: 'NOT_EXECUTED';
    readonly publication: 'NOT_EXECUTED';
    readonly production: 'NOT_EXECUTED';
  };
  readonly localImplementationComplete: true;
  readonly formalAcceptanceAchieved: false;
  readonly productionEligible: false;
}

export interface ArticleWorkspaceEtagInputV2 {
  readonly ifMatch: string | null;
  readonly observedEtag: string;
}

export interface ArticleWorkspaceEtagDecisionV2 {
  readonly classification: 'LOCAL_EFFECT_FREE_ETAG_DECISION_V2';
  readonly storyId: 'ST-1102';
  readonly code: 'PRECONDITION_REQUIRED' | 'PRECONDITION_FAILED' | 'MATCHED_NO_COMMAND';
  readonly httpStatus: 428 | 412 | null;
  readonly ifMatch: string | null;
  readonly observedEtag: string;
  readonly matched: boolean;
  readonly overwriteAllowed: false;
  readonly automaticMergeAllowed: false;
  readonly conflictResolutionRequired: boolean;
  readonly commandAvailable: false;
  readonly dispatch: 'NOT_EXECUTED';
  readonly persistence: 'NOT_EXECUTED';
  readonly mutationAuthorized: false;
  readonly publicationAuthorized: false;
}

export interface ArticleWorkspaceUnsavedInputV2 {
  readonly baselineAstSha256: string;
  readonly currentAstSha256: string;
  readonly targetScreenId: ArticleWorkspaceScreenId;
}

export interface ArticleWorkspaceUnsavedDecisionV2 {
  readonly classification: 'LOCAL_EFFECT_FREE_UNSAVED_NAVIGATION_DECISION_V2';
  readonly storyId: 'ST-1102';
  readonly componentId: 'UI-C014';
  readonly targetScreenId: ArticleWorkspaceScreenId;
  readonly baselineAstSha256: string;
  readonly currentAstSha256: string;
  readonly dirty: boolean;
  readonly code: 'ALLOW_CLEAN' | 'BLOCK_UNSAVED_CHANGES';
  readonly dialogRequired: boolean;
  readonly focusTargetId: 'article-workspace-v2-main' | 'article-workspace-v2-unsaved-dialog';
  readonly statusCue: {
    readonly text: string;
    readonly code: 'ALLOW_CLEAN' | 'BLOCK_UNSAVED_CHANGES';
    readonly icon: 'arrow-right' | 'triangle-alert';
    readonly colorOnly: false;
  };
  readonly navigationPerformed: false;
  readonly navigationInterceptionImplemented: false;
  readonly saveAuthorized: false;
  readonly discardAuthorized: false;
  readonly mutationAuthorized: false;
}

const SHA256 = /^[0-9a-f]{64}$/u;
const STRONG_ETAG = /^"[A-Za-z0-9._:-]{1,120}"$/u;
const COMPONENT = /^UI-C0(?:0[1-9]|[1-3][0-9]|4[0-6])$/u;
const ICON = /^[a-z]+(?:-[a-z]+)*$/u;
const dangerousKeys = new Set(['__proto__', 'constructor', 'prototype']);

const expectedBindings = createJsonValue({
  canonical: {
    integration: '540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a',
    canonicalDecisions: '6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626',
    openDecisions: 'a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e',
    uiDesign: '0cec24c40dfa69c14d51fb73e56977790ee19ed0ad5ed74d0339553ff25b860e',
    screenCatalog: 'dae723c7e423febe4abc0ab8752420411e6e95586069b75186bda7e92de85050',
    componentCatalog: '986ed1682b0f6b48c7e9fab04ff51229c000f4673e3cc3981e50903832f208f2',
    workflowCatalog: '59983683ec920cf450d0d887ee43f0b9871e500c2025562f9bec5c6bbc6fe87e',
    accessibilityChecklist: '690233f34abb08608e3e1241e6108fb93d4c6bb47ffe23be02e34f2a02b6d77e',
    securityDesign: '6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b',
    securityCatalog: 'c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8',
    roleMatrix: 'dfd67960ca8a004bbe6f3249ca9fa64ab1b24e94a57a2e88fc282267adc8b984',
    testDesign: '28d60d379c28b72ab0e700f0be1b40fc06b8e4bda531eef1749ce1e4f9ce93ac',
    testCatalog: '7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b',
    storyBacklog: '4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d',
    adminOpenApi: '6a22ee7a5f13ed89ac3bb6ceeffe49aad8b11e4f2a3a137c927542461c2ace70',
    contentAstSchema: 'a9e9f927d1646bb56f5124c70e5cc8a34e5e3b0de57d4fd1ac6633da1cfb2bac',
  },
  dependencies: {
    st0806Completion: '55347f6ce7d85dfc2b92ebeb41e8c51bfbb4ee83398a490e7022946b634d1556',
    st0806Plan: '02b066093f9bcc66058b05314437deae35260b33a21b26a048d48e33a4015867',
    st0806Fixture: '656e434ab1b8c6b7af3a0c4bc75dcd880ef487744a50bc870ca0ab70ad9361c6',
    st0806Contract: '42715fc526bcb4eddccbd836084769f7ef8886b7767ad806f33accdff4843bdd',
    st0806Domain: 'a033b7baac023179ea5cd245f399986e9969f2f1c611d6f4faf7cf98363e81b7',
    st0806Adapter: '5f43a7e69eb6430ba2fa190635d0e4d1bc16e01f66e3b3043625277ffedda85c',
    st0806BeforeAstFixture: '8467c824215c548479f1ccba5877797910c3a4abec736af37627605059422489',
    st1101Serializable: '56adb1e0356fba66e147be4c055b7a40f1115608a3e29bbee4584234f8b3273d',
    st1101RouteGuard: '8395f542c7c65445fa3d1bec4a0e037c96610da8589e1807604b4fb3fa6a584f',
    st1101AppShell: '600c7aa29ddf9572390f7e2eec8710ed726746aa41125fe23abe2f72ba820129',
    st1101DataTable: 'bb999786019d1c01ece36929124359af00c5362134c4ee4faf50ce496d3689f4',
    st1101Dialog: '494ac8b9e2a4087de2d003dd6c28bfcab7c85961f418a5892453c865058724bc',
    st1102HistoricalV1: '01d2f680ddfb5a64fa9d84db1c10e1ae9cd3de490520e67f135f3be63260db89',
    securePublicationHelper: '38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e',
  },
});

const paneByScreen = createJsonValue({
  'EDT-002': ['AST', 'AI_DIFF', 'CLAIMS', 'COMPARISON', 'SEO'],
  'EDT-003': ['AST'],
  'EDT-005': ['AI_DIFF'],
  'EDT-006': ['CLAIMS'],
  'EDT-007': ['COMPARISON'],
  'EDT-009': ['SEO'],
}) as unknown as Readonly<
  Record<ArticleWorkspaceScreenId, readonly ArticleWorkspaceV2ProjectionId[]>
>;

const semanticIds = createJsonValue({
  skipLink: 'article-workspace-v2-skip-link',
  header: 'article-workspace-v2-header',
  navigation: 'article-workspace-v2-navigation',
  main: 'article-workspace-v2-main',
  heading: 'article-workspace-v2-heading',
  errorSummary: 'article-workspace-v2-error-summary',
  workspaceTabs: 'article-workspace-v2-tabs',
  paneRegion: 'article-workspace-v2-pane',
  footer: 'article-workspace-v2-footer',
  unsavedDialog: 'article-workspace-v2-unsaved-dialog',
}) as unknown as ArticleWorkspaceV2Model['accessibility']['semanticIds'];

function reject(code: ArticleWorkspaceV2ErrorCode): never {
  throw new ArticleWorkspaceV2Error(code);
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
    for (const key of Reflect.ownKeys(value)) {
      if (typeof key !== 'string') {
        return false;
      }
      if (key === 'length') {
        continue;
      }
      if (dangerousKeys.has(key)) {
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

function strictClone(value: unknown, code: ArticleWorkspaceV2ErrorCode): JsonValue {
  if (!isStrictPlainTree(value)) {
    return reject(code);
  }
  try {
    return createJsonValue(value);
  } catch {
    return reject(code);
  }
}

function objectValue(value: JsonValue | undefined): JsonObject | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as JsonObject)
    : null;
}

function exactKeys(value: JsonObject, keys: readonly string[]): boolean {
  const observed = Object.keys(value).sort();
  const expected = [...keys].sort();
  return (
    observed.length === expected.length && observed.every((key, index) => key === expected[index])
  );
}

function jsonEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

const prohibitedKeys = new Set([
  'rawprompt',
  'rawsourcebody',
  'reviewbody',
  'rawhtml',
  'script',
  'iframe',
  'eventhandler',
  'arbitraryurl',
  'financedata',
  'revenue',
  'profit',
  'affiliaterate',
  'epc',
  'rpm',
  'credential',
  'secret',
  'password',
  'token',
  'personaldata',
  'callback',
  'publicprojection',
]);
const absoluteAddress = /^(?:(?:https?|ftp|file|mailto|tel|javascript):|\/\/)/iu;
const htmlMarkup = /<\/?(?:[a-z][^>]*)>/iu;

function normalizedKey(key: string): string {
  return key.replace(/[\s_-]+/gu, '').toLowerCase();
}

function hasProhibitedSurface(value: JsonValue): boolean {
  if (typeof value === 'string') {
    return absoluteAddress.test(value) || htmlMarkup.test(value);
  }
  if (value === null || typeof value !== 'object') {
    return false;
  }
  if (Array.isArray(value)) {
    return value.some((item) => hasProhibitedSurface(item));
  }
  return Object.entries(value).some(([key, item]) => {
    const normalized = normalizedKey(key);
    return (
      (prohibitedKeys.has(normalized) && item !== false && item !== null) ||
      /^on(?:click|submit|load|error|change|input|focus|blur|key|mouse|pointer)/u.test(
        normalized,
      ) ||
      hasProhibitedSurface(item)
    );
  });
}

function fixture(): JsonObject {
  let parsed: unknown;
  try {
    parsed = JSON.parse(ST1102_RECORDED_WORKSPACE_V2_JSON) as unknown;
  } catch {
    return reject('ARTICLE_WORKSPACE_V2_FIXTURE_INVALID');
  }
  const cloned = strictClone(parsed, 'ARTICLE_WORKSPACE_V2_FIXTURE_INVALID');
  const root = objectValue(cloned);
  if (
    root === null ||
    !exactKeys(root, [
      'article',
      'authority',
      'bindings',
      'canonicalStatus',
      'classification',
      'evaluatedAt',
      'header',
      'localStatus',
      'projections',
      'schemaVersion',
      'screenOrder',
      'security',
      'storyId',
      'verification',
    ]) ||
    root['schemaVersion'] !== 2 ||
    root['storyId'] !== 'ST-1102' ||
    root['classification'] !== ARTICLE_WORKSPACE_V2_CLASSIFICATION ||
    root['localStatus'] !== 'LOCAL_IMPLEMENTATION_COMPLETE' ||
    root['evaluatedAt'] !== '2026-08-24T02:00:00Z' ||
    !jsonEqual(root['screenOrder'], ARTICLE_WORKSPACE_SCREEN_IDS)
  ) {
    return reject('ARTICLE_WORKSPACE_V2_FIXTURE_INVALID');
  }
  if (!jsonEqual(root['bindings'], expectedBindings)) {
    return reject('ARTICLE_WORKSPACE_V2_BINDING_INVALID');
  }
  const article = objectValue(root['article']);
  const projections = objectValue(root['projections']);
  const security = objectValue(root['security']);
  const authority = objectValue(root['authority']);
  if (
    article === null ||
    projections === null ||
    security === null ||
    authority === null ||
    !exactKeys(projections, ARTICLE_WORKSPACE_V2_PROJECTION_IDS) ||
    typeof article['baselineAstSha256'] !== 'string' ||
    !SHA256.test(article['baselineAstSha256']) ||
    typeof article['proposalAstSha256'] !== 'string' ||
    !SHA256.test(article['proposalAstSha256']) ||
    article['baselineAstSha256'] === article['proposalAstSha256'] ||
    typeof article['recordedEtag'] !== 'string' ||
    !STRONG_ETAG.test(article['recordedEtag']) ||
    article['proposalDisposition'] !== 'HUMAN_EDITABLE_PROPOSAL_ONLY' ||
    article['proposalApplied'] !== false ||
    article['publicationAuthorized'] !== false
  ) {
    return reject('ARTICLE_WORKSPACE_V2_PROJECTION_INVALID');
  }
  for (const projectionId of ARTICLE_WORKSPACE_V2_PROJECTION_IDS) {
    const projection = objectValue(projections[projectionId]);
    const expectedStatus = projectionId === 'SEO' ? 'PARTIAL_RECORDED' : 'AVAILABLE_RECORDED';
    const cue = projection === null ? null : objectValue(projection['statusCue']);
    if (
      projection === null ||
      !exactKeys(projection, [
        'componentIds',
        'payload',
        'sourceStoryIds',
        'status',
        'statusCue',
      ]) ||
      projection['status'] !== expectedStatus ||
      !Array.isArray(projection['sourceStoryIds']) ||
      !Array.isArray(projection['componentIds']) ||
      !projection['componentIds'].every(
        (item) => typeof item === 'string' && COMPONENT.test(item),
      ) ||
      objectValue(projection['payload']) === null ||
      cue === null ||
      cue['code'] !== expectedStatus ||
      typeof cue['text'] !== 'string' ||
      !cue['text'] ||
      typeof cue['icon'] !== 'string' ||
      !ICON.test(cue['icon']) ||
      cue['colorOnly'] !== false
    ) {
      return reject('ARTICLE_WORKSPACE_V2_PROJECTION_INVALID');
    }
  }
  for (const value of Object.values(authority)) {
    if (value !== false) {
      return reject('ARTICLE_WORKSPACE_V2_FIXTURE_INVALID');
    }
  }
  for (const field of [
    'rawPromptPresent',
    'rawSourcePresent',
    'reviewBodyPresent',
    'rawHtmlPresent',
    'arbitraryUrlPresent',
    'financeOrAffiliateEconomicsPresent',
    'credentialPresent',
    'personalDataPresent',
    'publicProjectionPresent',
  ]) {
    if (security[field] !== false) {
      return reject('ARTICLE_WORKSPACE_V2_PROHIBITED_SURFACE');
    }
  }
  if (hasProhibitedSurface(root)) {
    return reject('ARTICLE_WORKSPACE_V2_PROHIBITED_SURFACE');
  }
  return root;
}

function validatedScreenId(input: ArticleWorkspaceV2Input): ArticleWorkspaceScreenId {
  const cloned = strictClone(input, 'ARTICLE_WORKSPACE_V2_INPUT_INVALID');
  const record = objectValue(cloned);
  if (record === null || !exactKeys(record, ['screenId'])) {
    return reject('ARTICLE_WORKSPACE_V2_INPUT_INVALID');
  }
  const screenId = record['screenId'];
  if (typeof screenId !== 'string') {
    return reject('ARTICLE_WORKSPACE_V2_INPUT_INVALID');
  }
  if (!(ARTICLE_WORKSPACE_SCREEN_IDS as readonly string[]).includes(screenId)) {
    return reject('ARTICLE_WORKSPACE_V2_SCREEN_UNKNOWN');
  }
  return screenId as ArticleWorkspaceScreenId;
}

function buildModel(screenId: ArticleWorkspaceScreenId): ArticleWorkspaceV2Model {
  const source = fixture();
  const screen = ARTICLE_WORKSPACE_SCREENS.find((candidate) => candidate.id === screenId);
  const projections = objectValue(source['projections']);
  const article = objectValue(source['article']);
  const header = objectValue(source['header']);
  const security = objectValue(source['security']);
  const authority = objectValue(source['authority']);
  if (
    screen === undefined ||
    projections === null ||
    article === null ||
    header === null ||
    security === null ||
    authority === null ||
    typeof article['recordedEtag'] !== 'string'
  ) {
    return reject('ARTICLE_WORKSPACE_V2_FIXTURE_INVALID');
  }
  const paneOrder = paneByScreen[screenId];
  const panes = paneOrder.map((projectionId) => projections[projectionId]);
  if (panes.some((pane) => objectValue(pane) === null)) {
    return reject('ARTICLE_WORKSPACE_V2_PROJECTION_INVALID');
  }
  return createJsonValue({
    classification: ARTICLE_WORKSPACE_V2_CLASSIFICATION,
    storyId: 'ST-1102',
    localStatus: 'LOCAL_IMPLEMENTATION_COMPLETE',
    canonicalStatus: {
      implementation: 'NOT_STARTED',
      verification: 'NOT_EXECUTED',
    },
    sourceMode: 'RECORDED_SYNTHETIC_DEV_CI_ONLY',
    sourceFixtureSha256: ST1102_RECORDED_WORKSPACE_V2_SHA256,
    screen,
    screenOrder: ARTICLE_WORKSPACE_SCREEN_IDS,
    article,
    header,
    paneOrder,
    panes,
    route: {
      registered: false,
      renderEnabled: false,
      status: 'DISABLED_AUTH_TRANSPORT_UNRESOLVED',
      roleMetadataOnly: true,
    },
    concurrency: {
      baselineEtag: article['recordedEtag'],
      ifMatchRequired: true,
      evaluatorAvailable: true,
      overwriteAllowed: false,
      automaticMergeAllowed: false,
      saveCommandAvailable: false,
      dispatch: 'NOT_EXECUTED',
      persistence: 'NOT_EXECUTED',
    },
    unsavedGuard: {
      componentId: 'UI-C014',
      evaluatorAvailable: true,
      navigationInterceptionImplemented: false,
      navigationEffectEnabled: false,
      saveAuthorized: false,
      discardAuthorized: false,
    },
    accessibility: {
      candidateOnly: true,
      semanticOrder: [
        'skip-link',
        'header',
        'navigation',
        'main',
        'error-summary',
        'workspace-tabs',
        'pane-region',
        'footer',
      ],
      semanticIds,
      h1: { count: 1, level: 1, textSource: 'SCREEN_NAME' },
      keyboardModel: ['Tab', 'Shift+Tab', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'Escape'],
      statusTextPresent: true,
      statusCodePresent: true,
      statusIconPresent: true,
      statusNotColorOnly: true,
      tableCaptionRequired: true,
      columnHeadersRequired: true,
      rowHeaderRequired: true,
      zoomTargetPercent: 200,
      rendered: false,
      browserVerified: false,
      screenReaderVerified: false,
    },
    security,
    authority,
    verification: {
      localModel: 'EXECUTED',
      TST_022: 'NOT_EXECUTED',
      TST_024: 'NOT_EXECUTED',
      formalValidation: 'NOT_EXECUTED',
      browser: 'NOT_EXECUTED',
      keyboard: 'NOT_EXECUTED',
      zoom: 'NOT_EXECUTED',
      screenReader: 'NOT_EXECUTED',
      hostedCi: 'NOT_EXECUTED',
      live: 'NOT_EXECUTED',
      staging: 'NOT_EXECUTED',
      release: 'NOT_EXECUTED',
      publication: 'NOT_EXECUTED',
      production: 'NOT_EXECUTED',
    },
    localImplementationComplete: true,
    formalAcceptanceAchieved: false,
    productionEligible: false,
  }) as unknown as ArticleWorkspaceV2Model;
}

export function validateArticleWorkspaceV2Model(value: unknown): ArticleWorkspaceV2Model {
  const cloned = strictClone(value, 'ARTICLE_WORKSPACE_V2_MODEL_INVALID');
  if (hasProhibitedSurface(cloned)) {
    return reject('ARTICLE_WORKSPACE_V2_PROHIBITED_SURFACE');
  }
  const root = objectValue(cloned);
  const screen = root === null ? null : objectValue(root['screen']);
  const screenId = screen === null ? null : screen['id'];
  if (
    root === null ||
    typeof screenId !== 'string' ||
    !(ARTICLE_WORKSPACE_SCREEN_IDS as readonly string[]).includes(screenId)
  ) {
    return reject('ARTICLE_WORKSPACE_V2_MODEL_INVALID');
  }
  const expected = buildModel(screenId as ArticleWorkspaceScreenId);
  if (!jsonEqual(cloned, expected)) {
    return reject('ARTICLE_WORKSPACE_V2_MODEL_INVALID');
  }
  return cloned as unknown as ArticleWorkspaceV2Model;
}

export function createArticleWorkspaceV2(input: ArticleWorkspaceV2Input): ArticleWorkspaceV2Model {
  return validateArticleWorkspaceV2Model(buildModel(validatedScreenId(input)));
}

function validatedEtagInput(input: ArticleWorkspaceEtagInputV2): {
  readonly ifMatch: string | null;
  readonly observedEtag: string;
} {
  const cloned = strictClone(input, 'ARTICLE_WORKSPACE_V2_ETAG_INPUT_INVALID');
  const record = objectValue(cloned);
  if (record === null || !exactKeys(record, ['ifMatch', 'observedEtag'])) {
    return reject('ARTICLE_WORKSPACE_V2_ETAG_INPUT_INVALID');
  }
  const ifMatch = record['ifMatch'];
  const observedEtag = record['observedEtag'];
  if (
    (ifMatch !== null && (typeof ifMatch !== 'string' || !STRONG_ETAG.test(ifMatch))) ||
    typeof observedEtag !== 'string' ||
    !STRONG_ETAG.test(observedEtag)
  ) {
    return reject('ARTICLE_WORKSPACE_V2_ETAG_INVALID');
  }
  return { ifMatch, observedEtag };
}

export function evaluateArticleWorkspaceEtagV2(
  input: ArticleWorkspaceEtagInputV2,
): ArticleWorkspaceEtagDecisionV2 {
  const { ifMatch, observedEtag } = validatedEtagInput(input);
  const code =
    ifMatch === null
      ? 'PRECONDITION_REQUIRED'
      : ifMatch === observedEtag
        ? 'MATCHED_NO_COMMAND'
        : 'PRECONDITION_FAILED';
  return createJsonValue({
    classification: 'LOCAL_EFFECT_FREE_ETAG_DECISION_V2',
    storyId: 'ST-1102',
    code,
    httpStatus:
      code === 'PRECONDITION_REQUIRED' ? 428 : code === 'PRECONDITION_FAILED' ? 412 : null,
    ifMatch,
    observedEtag,
    matched: code === 'MATCHED_NO_COMMAND',
    overwriteAllowed: false,
    automaticMergeAllowed: false,
    conflictResolutionRequired: code === 'PRECONDITION_FAILED',
    commandAvailable: false,
    dispatch: 'NOT_EXECUTED',
    persistence: 'NOT_EXECUTED',
    mutationAuthorized: false,
    publicationAuthorized: false,
  }) as unknown as ArticleWorkspaceEtagDecisionV2;
}

function validatedUnsavedInput(input: ArticleWorkspaceUnsavedInputV2): {
  readonly baselineAstSha256: string;
  readonly currentAstSha256: string;
  readonly targetScreenId: ArticleWorkspaceScreenId;
} {
  const cloned = strictClone(input, 'ARTICLE_WORKSPACE_V2_UNSAVED_INPUT_INVALID');
  const record = objectValue(cloned);
  if (
    record === null ||
    !exactKeys(record, ['baselineAstSha256', 'currentAstSha256', 'targetScreenId'])
  ) {
    return reject('ARTICLE_WORKSPACE_V2_UNSAVED_INPUT_INVALID');
  }
  const baselineAstSha256 = record['baselineAstSha256'];
  const currentAstSha256 = record['currentAstSha256'];
  const targetScreenId = record['targetScreenId'];
  if (
    typeof baselineAstSha256 !== 'string' ||
    !SHA256.test(baselineAstSha256) ||
    typeof currentAstSha256 !== 'string' ||
    !SHA256.test(currentAstSha256)
  ) {
    return reject('ARTICLE_WORKSPACE_V2_AST_SHA256_INVALID');
  }
  if (
    typeof targetScreenId !== 'string' ||
    !(ARTICLE_WORKSPACE_SCREEN_IDS as readonly string[]).includes(targetScreenId)
  ) {
    return reject('ARTICLE_WORKSPACE_V2_SCREEN_UNKNOWN');
  }
  return {
    baselineAstSha256,
    currentAstSha256,
    targetScreenId: targetScreenId as ArticleWorkspaceScreenId,
  };
}

export function evaluateArticleWorkspaceUnsavedGuardV2(
  input: ArticleWorkspaceUnsavedInputV2,
): ArticleWorkspaceUnsavedDecisionV2 {
  const { baselineAstSha256, currentAstSha256, targetScreenId } = validatedUnsavedInput(input);
  const dirty = baselineAstSha256 !== currentAstSha256;
  const code = dirty ? 'BLOCK_UNSAVED_CHANGES' : 'ALLOW_CLEAN';
  return createJsonValue({
    classification: 'LOCAL_EFFECT_FREE_UNSAVED_NAVIGATION_DECISION_V2',
    storyId: 'ST-1102',
    componentId: 'UI-C014',
    targetScreenId,
    baselineAstSha256,
    currentAstSha256,
    dirty,
    code,
    dialogRequired: dirty,
    focusTargetId: dirty ? semanticIds.unsavedDialog : semanticIds.main,
    statusCue: {
      text: dirty ? 'Unsaved changes block navigation' : 'No unsaved changes',
      code,
      icon: dirty ? 'triangle-alert' : 'arrow-right',
      colorOnly: false,
    },
    navigationPerformed: false,
    navigationInterceptionImplemented: false,
    saveAuthorized: false,
    discardAuthorized: false,
    mutationAuthorized: false,
  }) as unknown as ArticleWorkspaceUnsavedDecisionV2;
}
