import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const ARTICLE_WORKSPACE_SCREEN_IDS = createJsonValue([
  'EDT-002',
  'EDT-003',
  'EDT-005',
  'EDT-006',
  'EDT-007',
  'EDT-009',
]) as unknown as readonly ['EDT-002', 'EDT-003', 'EDT-005', 'EDT-006', 'EDT-007', 'EDT-009'];

export type ArticleWorkspaceScreenId = (typeof ARTICLE_WORKSPACE_SCREEN_IDS)[number];

export const ARTICLE_WORKSPACE_EXCLUDED_SCREEN_IDS = createJsonValue([
  'EDT-001',
  'EDT-004',
  'EDT-008',
  'EDT-010',
]) as unknown as readonly ['EDT-001', 'EDT-004', 'EDT-008', 'EDT-010'];

export type ArticleWorkspaceRole = 'MANAGING_EDITOR' | 'EDITOR' | 'REVIEWER';

export interface ArticleWorkspaceScreenMetadata {
  readonly id: ArticleWorkspaceScreenId;
  readonly name: string;
  readonly route: string;
  readonly area: 'editorial';
  readonly roles: readonly ArticleWorkspaceRole[];
  readonly purpose: string;
  readonly mvp: true;
  readonly criticalAction: boolean;
  readonly apiDependencies: readonly string[];
  readonly designStatus: 'APPROVED_FOR_IMPLEMENTATION';
  readonly implementationStatus: 'NOT_STARTED';
  readonly runtimeVerification: 'NOT_EXECUTED';
}

const screenMetadataSource = [
  {
    id: 'EDT-002',
    name: 'Article Workspace',
    route: '/admin/articles/{id}',
    area: 'editorial',
    roles: ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
    purpose: '企画から公開までの統合Workspace',
    mvp: true,
    criticalAction: false,
    apiDependencies: ['Article', 'ArticleVersion', 'Findings'],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'EDT-003',
    name: 'Content AST Editor',
    route: '/admin/articles/{id}/versions/{versionId}/content',
    area: 'editorial',
    roles: ['MANAGING_EDITOR', 'EDITOR'],
    purpose: '型付きBlockを編集し未知Fieldを拒否',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'EDT-005',
    name: 'AI Diff Review',
    route: '/admin/articles/{id}/ai-diff',
    area: 'editorial',
    roles: ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
    purpose: 'AI提案と人間編集差分を比較',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'EDT-006',
    name: 'Claim–Evidence Matrix',
    route: '/admin/articles/{id}/claims',
    area: 'editorial',
    roles: ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
    purpose: 'ClaimごとのEvidence、時刻、Conflictを確認',
    mvp: true,
    criticalAction: true,
    apiDependencies: ['Claim', 'ClaimEvidenceLink'],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'EDT-007',
    name: 'Comparison Preview',
    route: '/admin/articles/{id}/comparison',
    area: 'editorial',
    roles: ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
    purpose: '比較軸・単位・Unknown・Variantを検査',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'EDT-009',
    name: 'SEO Preview',
    route: '/admin/articles/{id}/seo',
    area: 'editorial',
    roles: ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
    purpose: 'Title、Canonical、Robots、JSON-LD Preview',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
] as const;

export const ARTICLE_WORKSPACE_SCREENS = createJsonValue(
  screenMetadataSource,
) as unknown as readonly ArticleWorkspaceScreenMetadata[];

export const ARTICLE_WORKSPACE_COMPONENT_IDS = createJsonValue([
  'UI-C014',
  'UI-C015',
  'UI-C021',
  'UI-C022',
  'UI-C023',
  'UI-C036',
]) as unknown as readonly ['UI-C014', 'UI-C015', 'UI-C021', 'UI-C022', 'UI-C023', 'UI-C036'];

export type ArticleWorkspaceComponentId = (typeof ARTICLE_WORKSPACE_COMPONENT_IDS)[number];

export interface ArticleWorkspaceComponentMetadata {
  readonly id: ArticleWorkspaceComponentId;
  readonly name: string;
  readonly area: 'admin' | 'shared';
  readonly purpose: string;
  readonly keyboardRequired: true;
  readonly screenReaderRequired: true;
  readonly designStatus: 'APPROVED_FOR_IMPLEMENTATION';
  readonly implementationStatus: 'NOT_STARTED';
  readonly runtimeVerification: 'NOT_EXECUTED';
}

const componentMetadataSource = [
  {
    id: 'UI-C014',
    name: 'UnsavedChangesGuard',
    area: 'admin',
    purpose: '離脱防止',
    keyboardRequired: true,
    screenReaderRequired: true,
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'UI-C015',
    name: 'VersionDiff',
    area: 'admin',
    purpose: '追加/削除/変更と出所を比較',
    keyboardRequired: true,
    screenReaderRequired: true,
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'UI-C021',
    name: 'ClaimEvidenceMatrix',
    area: 'admin',
    purpose: 'Claim×Evidence、Conflict、Freshness',
    keyboardRequired: true,
    screenReaderRequired: true,
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'UI-C022',
    name: 'ContentBlockEditor',
    area: 'admin',
    purpose: 'Typed AST Block編集',
    keyboardRequired: true,
    screenReaderRequired: true,
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'UI-C023',
    name: 'ComparisonTableEditor',
    area: 'admin',
    purpose: '商品×軸、Unit、Unknown',
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

export const ARTICLE_WORKSPACE_COMPONENTS = createJsonValue(
  componentMetadataSource,
) as unknown as readonly ArticleWorkspaceComponentMetadata[];

export interface ArticleWorkspaceSourceReference {
  readonly scope: 'STORY' | 'SCREENS' | 'COMPONENTS' | 'DESIGN' | 'SLICE' | 'TESTS' | 'DEPENDENCY';
  readonly path: string;
  readonly locator: string;
  readonly sha256: string;
  readonly commit: string | null;
  readonly consumption: 'STATIC_METADATA_ONLY' | 'REFERENCE_ONLY_NO_RUNTIME_IMPORT';
}

const sourceReferenceSource = [
  {
    scope: 'STORY',
    path: 'docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml',
    locator: 'ST-1102',
    sha256: '4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d',
    commit: null,
    consumption: 'STATIC_METADATA_ONLY',
  },
  {
    scope: 'SCREENS',
    path: 'docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml',
    locator: 'EDT-002,EDT-003,EDT-005,EDT-006,EDT-007,EDT-009',
    sha256: 'dae723c7e423febe4abc0ab8752420411e6e95586069b75186bda7e92de85050',
    commit: null,
    consumption: 'STATIC_METADATA_ONLY',
  },
  {
    scope: 'COMPONENTS',
    path: 'docs/canonical/02_ui/RAOS_08_component_catalog_v1.0.yaml',
    locator: 'UI-C014,UI-C015,UI-C021,UI-C022,UI-C023,UI-C036',
    sha256: '986ed1682b0f6b48c7e9fab04ff51229c000f4673e3cc3981e50903832f208f2',
    commit: null,
    consumption: 'STATIC_METADATA_ONLY',
  },
  {
    scope: 'DESIGN',
    path: 'docs/canonical/02_ui/RAOS_08_ui_ux_design_v1.0.md',
    locator: 'sections 2,5,8,10,11,13,14',
    sha256: '0cec24c40dfa69c14d51fb73e56977790ee19ed0ad5ed74d0339553ff25b860e',
    commit: null,
    consumption: 'STATIC_METADATA_ONLY',
  },
  {
    scope: 'SLICE',
    path: 'docs/canonical/02_ui/RAOS_08_implementation_slices_v1.0.yaml',
    locator: 'UI-SLICE-006',
    sha256: '2540548f6e7c84ef3878fd77311e8bf455b85de73cfcb83aa5f1fe684087eb9d',
    commit: null,
    consumption: 'STATIC_METADATA_ONLY',
  },
  {
    scope: 'TESTS',
    path: 'docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml',
    locator: 'TST-022,TST-024',
    sha256: '7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b',
    commit: null,
    consumption: 'STATIC_METADATA_ONLY',
  },
  {
    scope: 'DEPENDENCY',
    path: 'changes/st-0806/README.md',
    locator: 'ST-0806',
    sha256: 'fd29d5a9e07a02d92d4440f952899d3e977f53e9016f2b27ea3367a6c7829f2a',
    commit: '3999b953a983034a6395f9f6678a72965453abe6',
    consumption: 'REFERENCE_ONLY_NO_RUNTIME_IMPORT',
  },
  {
    scope: 'DEPENDENCY',
    path: 'changes/st-1101/README.md',
    locator: 'ST-1101',
    sha256: 'b2bb91e89d5948f8081853e39596951adcee16974ce2a6ffa159892310ead08c',
    commit: '6933612a49863591555137868ca0cec935cf65e4',
    consumption: 'REFERENCE_ONLY_NO_RUNTIME_IMPORT',
  },
] as const;

export const ARTICLE_WORKSPACE_SOURCE_REFS = createJsonValue(
  sourceReferenceSource,
) as unknown as readonly ArticleWorkspaceSourceReference[];

export const ARTICLE_WORKSPACE_PROJECTION_IDS = createJsonValue([
  'AST',
  'AI_DIFF',
  'CLAIMS',
  'COMPARISON',
  'SEO',
]) as unknown as readonly ['AST', 'AI_DIFF', 'CLAIMS', 'COMPARISON', 'SEO'];

export type ArticleWorkspaceProjectionId = (typeof ARTICLE_WORKSPACE_PROJECTION_IDS)[number];

export const ARTICLE_WORKSPACE_SEMANTIC_IDS = createJsonValue({
  skipLink: 'article-workspace-skip-link',
  header: 'article-workspace-header',
  navigation: 'article-workspace-navigation',
  main: 'article-workspace-main',
  heading: 'article-workspace-heading',
  errorSummary: 'article-workspace-error-summary',
  paneRegion: 'article-workspace-pane-region',
  footer: 'article-workspace-footer',
}) as unknown as Readonly<{
  skipLink: 'article-workspace-skip-link';
  header: 'article-workspace-header';
  navigation: 'article-workspace-navigation';
  main: 'article-workspace-main';
  heading: 'article-workspace-heading';
  errorSummary: 'article-workspace-error-summary';
  paneRegion: 'article-workspace-pane-region';
  footer: 'article-workspace-footer';
}>;

export const ARTICLE_WORKSPACE_ERROR_CODES = createJsonValue([
  'ARTICLE_WORKSPACE_INPUT_INVALID',
  'ARTICLE_WORKSPACE_SCREEN_UNKNOWN',
  'ARTICLE_WORKSPACE_CANDIDATE_INVALID',
  'ARTICLE_WORKSPACE_DUPLICATE_ID',
  'ARTICLE_WORKSPACE_DUPLICATE_ROUTE',
  'ARTICLE_WORKSPACE_METADATA_INVALID',
  'ARTICLE_WORKSPACE_STATE_INVALID',
  'ARTICLE_WORKSPACE_ACCESSIBILITY_INVALID',
  'ARTICLE_WORKSPACE_AUTHORITY_INVALID',
  'ARTICLE_WORKSPACE_PROHIBITED_SURFACE',
]) as unknown as readonly [
  'ARTICLE_WORKSPACE_INPUT_INVALID',
  'ARTICLE_WORKSPACE_SCREEN_UNKNOWN',
  'ARTICLE_WORKSPACE_CANDIDATE_INVALID',
  'ARTICLE_WORKSPACE_DUPLICATE_ID',
  'ARTICLE_WORKSPACE_DUPLICATE_ROUTE',
  'ARTICLE_WORKSPACE_METADATA_INVALID',
  'ARTICLE_WORKSPACE_STATE_INVALID',
  'ARTICLE_WORKSPACE_ACCESSIBILITY_INVALID',
  'ARTICLE_WORKSPACE_AUTHORITY_INVALID',
  'ARTICLE_WORKSPACE_PROHIBITED_SURFACE',
];

export type ArticleWorkspaceErrorCode = (typeof ARTICLE_WORKSPACE_ERROR_CODES)[number];

export class ArticleWorkspaceError extends TypeError {
  readonly code: ArticleWorkspaceErrorCode;

  constructor(code: ArticleWorkspaceErrorCode) {
    const closedCode = (ARTICLE_WORKSPACE_ERROR_CODES as readonly unknown[]).includes(code)
      ? code
      : 'ARTICLE_WORKSPACE_CANDIDATE_INVALID';
    super(closedCode);
    this.name = 'ArticleWorkspaceError';
    this.code = closedCode;
    Object.freeze(this);
  }
}

export interface ArticleWorkspaceInput {
  readonly screenId: ArticleWorkspaceScreenId;
}

export interface ArticleWorkspaceLoadSlot {
  readonly status: 'NOT_LOADED';
  readonly value: null;
}

export interface ArticleWorkspaceProjection {
  readonly id: ArticleWorkspaceProjectionId;
  readonly status: 'NOT_LOADED';
  readonly reason:
    | 'ARTICLE_VERSION_NOT_LOADED'
    | 'AI_DIFF_INPUT_NOT_LOADED'
    | 'CLAIM_EVIDENCE_NOT_LOADED'
    | 'COMPARISON_INPUT_NOT_LOADED'
    | 'SEO_INPUT_NOT_LOADED';
  readonly componentIds: readonly ArticleWorkspaceComponentId[];
  readonly payload: null;
}

export interface ArticleWorkspaceCandidate {
  readonly classification: 'SOURCE_DERIVED_DISABLED_HEADLESS_ARTICLE_WORKSPACE_CANDIDATE';
  readonly storyId: 'ST-1102';
  readonly objective: 'AST/AI diff/Claim/Comparison/SEOを統合';
  readonly screen: ArticleWorkspaceScreenMetadata;
  readonly catalogScreens: readonly ArticleWorkspaceScreenMetadata[];
  readonly canonicalScreenOrder: readonly ArticleWorkspaceScreenId[];
  readonly excludedScreenIds: typeof ARTICLE_WORKSPACE_EXCLUDED_SCREEN_IDS;
  readonly components: readonly ArticleWorkspaceComponentMetadata[];
  readonly sourceRefs: readonly ArticleWorkspaceSourceReference[];
  readonly availability: 'DISABLED';
  readonly roleInputAccepted: false;
  readonly roleMetadataAuthority: 'DISPLAY_ONLY_NOT_AUTHORIZATION';
  readonly routeRegistered: false;
  readonly renderEnabled: false;
  readonly authenticationEstablished: false;
  readonly authorizationGranted: false;
  readonly mutationEnabled: false;
  readonly persistenceEnabled: false;
  readonly providerInvocationEnabled: false;
  readonly externalActionEnabled: false;
  readonly publicationAuthorized: false;
  readonly criticalActionExecutionEnabled: false;
  readonly coordinateSlots: {
    readonly article: ArticleWorkspaceLoadSlot;
    readonly version: ArticleWorkspaceLoadSlot;
    readonly state: ArticleWorkspaceLoadSlot;
    readonly etag: ArticleWorkspaceLoadSlot;
  };
  readonly workspaceSignals: {
    readonly blockers: ArticleWorkspaceLoadSlot;
    readonly unknowns: ArticleWorkspaceLoadSlot;
    readonly stale: ArticleWorkspaceLoadSlot;
    readonly evidenceGaps: ArticleWorkspaceLoadSlot;
  };
  readonly projections: readonly ArticleWorkspaceProjection[];
  readonly concurrency: {
    readonly etag: null;
    readonly ifMatch: null;
    readonly conflictDetection: 'NOT_EVALUATED';
    readonly overwriteEnabled: false;
  };
  readonly unsavedChangesGuard: {
    readonly componentId: 'UI-C014';
    readonly status: 'NOT_EVALUATED';
    readonly unsavedChangesKnown: false;
    readonly navigationInterceptionEnabled: false;
  };
  readonly seoPreview: {
    readonly status: 'NOT_LOADED';
    readonly computationEnabled: false;
    readonly canonical: null;
    readonly robots: null;
    readonly jsonLd: null;
  };
  readonly actions: readonly [];
  readonly accessibility: {
    readonly candidateOnly: true;
    readonly semanticOrder: readonly [
      'skip-link',
      'header',
      'navigation',
      'main',
      'error-summary',
      'pane-region',
      'footer',
    ];
    readonly elements: readonly {
      readonly kind:
        'skip-link' | 'header' | 'navigation' | 'main' | 'error-summary' | 'pane-region' | 'footer';
      readonly id: string;
      readonly role: 'link' | 'banner' | 'navigation' | 'main' | 'alert' | 'region' | 'contentinfo';
    }[];
    readonly h1: {
      readonly id: 'article-workspace-heading';
      readonly count: 1;
      readonly level: 1;
      readonly textSource: 'SCREEN_NAME';
    };
    readonly focusOrder: readonly [
      'article-workspace-skip-link',
      'article-workspace-main',
      'article-workspace-error-summary',
      'article-workspace-pane-region',
    ];
    readonly keyboardRequired: true;
    readonly screenReaderRequired: true;
    readonly visibleFocusRequired: true;
    readonly statusPresentation: {
      readonly textRequired: true;
      readonly codeRequired: true;
      readonly iconRequired: true;
      readonly colorOnly: false;
    };
    readonly motion: 'NONE';
  };
  readonly verification: {
    readonly formalTst022: 'NOT_EXECUTED';
    readonly formalTst024: 'NOT_EXECUTED';
    readonly browser: 'NOT_EXECUTED';
    readonly accessibility: 'NOT_EXECUTED';
    readonly keyboard: 'NOT_EXECUTED';
    readonly screenReader: 'NOT_EXECUTED';
    readonly live: 'NOT_EXECUTED';
    readonly staging: 'NOT_EXECUTED';
    readonly release: 'NOT_EXECUTED';
    readonly publication: 'NOT_EXECUTED';
    readonly production: 'NOT_EXECUTED';
  };
  readonly acceptanceAchieved: false;
  readonly storyComplete: false;
  readonly decision: 'NOT_READY';
  readonly productionEligible: false;
}

const projectionSource = [
  {
    id: 'AST',
    status: 'NOT_LOADED',
    reason: 'ARTICLE_VERSION_NOT_LOADED',
    componentIds: ['UI-C022'],
    payload: null,
  },
  {
    id: 'AI_DIFF',
    status: 'NOT_LOADED',
    reason: 'AI_DIFF_INPUT_NOT_LOADED',
    componentIds: ['UI-C015'],
    payload: null,
  },
  {
    id: 'CLAIMS',
    status: 'NOT_LOADED',
    reason: 'CLAIM_EVIDENCE_NOT_LOADED',
    componentIds: ['UI-C021'],
    payload: null,
  },
  {
    id: 'COMPARISON',
    status: 'NOT_LOADED',
    reason: 'COMPARISON_INPUT_NOT_LOADED',
    componentIds: ['UI-C023', 'UI-C036'],
    payload: null,
  },
  {
    id: 'SEO',
    status: 'NOT_LOADED',
    reason: 'SEO_INPUT_NOT_LOADED',
    componentIds: [],
    payload: null,
  },
] as const;

const semanticElementsSource = [
  { kind: 'skip-link', id: ARTICLE_WORKSPACE_SEMANTIC_IDS.skipLink, role: 'link' },
  { kind: 'header', id: ARTICLE_WORKSPACE_SEMANTIC_IDS.header, role: 'banner' },
  {
    kind: 'navigation',
    id: ARTICLE_WORKSPACE_SEMANTIC_IDS.navigation,
    role: 'navigation',
  },
  { kind: 'main', id: ARTICLE_WORKSPACE_SEMANTIC_IDS.main, role: 'main' },
  {
    kind: 'error-summary',
    id: ARTICLE_WORKSPACE_SEMANTIC_IDS.errorSummary,
    role: 'alert',
  },
  {
    kind: 'pane-region',
    id: ARTICLE_WORKSPACE_SEMANTIC_IDS.paneRegion,
    role: 'region',
  },
  { kind: 'footer', id: ARTICLE_WORKSPACE_SEMANTIC_IDS.footer, role: 'contentinfo' },
] as const;

function reject(code: ArticleWorkspaceErrorCode): never {
  throw new ArticleWorkspaceError(code);
}

const dangerousKeys = new Set(['__proto__', 'constructor', 'prototype']);

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
    for (const key of keys) {
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

function isJsonObject(value: JsonValue | undefined): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function cloneStrict(value: unknown, code: ArticleWorkspaceErrorCode): JsonValue {
  if (!isStrictPlainTree(value)) {
    return reject(code);
  }
  try {
    return createJsonValue(value);
  } catch {
    return reject(code);
  }
}

function validatedScreenId(input: ArticleWorkspaceInput): ArticleWorkspaceScreenId {
  const value = cloneStrict(input, 'ARTICLE_WORKSPACE_INPUT_INVALID');
  if (!isJsonObject(value)) {
    return reject('ARTICLE_WORKSPACE_INPUT_INVALID');
  }
  const keys = Object.keys(value);
  if (keys.length !== 1 || keys[0] !== 'screenId') {
    return reject('ARTICLE_WORKSPACE_INPUT_INVALID');
  }
  const screenId = value['screenId'];
  if (typeof screenId !== 'string') {
    return reject('ARTICLE_WORKSPACE_INPUT_INVALID');
  }
  if (!(ARTICLE_WORKSPACE_SCREEN_IDS as readonly string[]).includes(screenId)) {
    return reject('ARTICLE_WORKSPACE_SCREEN_UNKNOWN');
  }
  return screenId as ArticleWorkspaceScreenId;
}

function buildCandidate(screenId: ArticleWorkspaceScreenId): ArticleWorkspaceCandidate {
  const screen = ARTICLE_WORKSPACE_SCREENS.find((item) => item.id === screenId);
  if (screen === undefined) {
    return reject('ARTICLE_WORKSPACE_SCREEN_UNKNOWN');
  }
  const unloaded = { status: 'NOT_LOADED', value: null } as const;
  return createJsonValue({
    classification: 'SOURCE_DERIVED_DISABLED_HEADLESS_ARTICLE_WORKSPACE_CANDIDATE',
    storyId: 'ST-1102',
    objective: 'AST/AI diff/Claim/Comparison/SEOを統合',
    screen,
    catalogScreens: ARTICLE_WORKSPACE_SCREENS,
    canonicalScreenOrder: ARTICLE_WORKSPACE_SCREEN_IDS,
    excludedScreenIds: ARTICLE_WORKSPACE_EXCLUDED_SCREEN_IDS,
    components: ARTICLE_WORKSPACE_COMPONENTS,
    sourceRefs: ARTICLE_WORKSPACE_SOURCE_REFS,
    availability: 'DISABLED',
    roleInputAccepted: false,
    roleMetadataAuthority: 'DISPLAY_ONLY_NOT_AUTHORIZATION',
    routeRegistered: false,
    renderEnabled: false,
    authenticationEstablished: false,
    authorizationGranted: false,
    mutationEnabled: false,
    persistenceEnabled: false,
    providerInvocationEnabled: false,
    externalActionEnabled: false,
    publicationAuthorized: false,
    criticalActionExecutionEnabled: false,
    coordinateSlots: {
      article: unloaded,
      version: unloaded,
      state: unloaded,
      etag: unloaded,
    },
    workspaceSignals: {
      blockers: unloaded,
      unknowns: unloaded,
      stale: unloaded,
      evidenceGaps: unloaded,
    },
    projections: projectionSource,
    concurrency: {
      etag: null,
      ifMatch: null,
      conflictDetection: 'NOT_EVALUATED',
      overwriteEnabled: false,
    },
    unsavedChangesGuard: {
      componentId: 'UI-C014',
      status: 'NOT_EVALUATED',
      unsavedChangesKnown: false,
      navigationInterceptionEnabled: false,
    },
    seoPreview: {
      status: 'NOT_LOADED',
      computationEnabled: false,
      canonical: null,
      robots: null,
      jsonLd: null,
    },
    actions: [],
    accessibility: {
      candidateOnly: true,
      semanticOrder: [
        'skip-link',
        'header',
        'navigation',
        'main',
        'error-summary',
        'pane-region',
        'footer',
      ],
      elements: semanticElementsSource,
      h1: {
        id: ARTICLE_WORKSPACE_SEMANTIC_IDS.heading,
        count: 1,
        level: 1,
        textSource: 'SCREEN_NAME',
      },
      focusOrder: [
        ARTICLE_WORKSPACE_SEMANTIC_IDS.skipLink,
        ARTICLE_WORKSPACE_SEMANTIC_IDS.main,
        ARTICLE_WORKSPACE_SEMANTIC_IDS.errorSummary,
        ARTICLE_WORKSPACE_SEMANTIC_IDS.paneRegion,
      ],
      keyboardRequired: true,
      screenReaderRequired: true,
      visibleFocusRequired: true,
      statusPresentation: {
        textRequired: true,
        codeRequired: true,
        iconRequired: true,
        colorOnly: false,
      },
      motion: 'NONE',
    },
    verification: {
      formalTst022: 'NOT_EXECUTED',
      formalTst024: 'NOT_EXECUTED',
      browser: 'NOT_EXECUTED',
      accessibility: 'NOT_EXECUTED',
      keyboard: 'NOT_EXECUTED',
      screenReader: 'NOT_EXECUTED',
      live: 'NOT_EXECUTED',
      staging: 'NOT_EXECUTED',
      release: 'NOT_EXECUTED',
      publication: 'NOT_EXECUTED',
      production: 'NOT_EXECUTED',
    },
    acceptanceAchieved: false,
    storyComplete: false,
    decision: 'NOT_READY',
    productionEligible: false,
  }) as unknown as ArticleWorkspaceCandidate;
}

function jsonEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function recordArray(value: JsonValue | undefined): readonly JsonObject[] | null {
  if (!Array.isArray(value) || !value.every((item) => isJsonObject(item))) {
    return null;
  }
  return value;
}

function valuesFor(records: readonly JsonObject[] | null, key: string): readonly string[] {
  if (records === null) {
    return [];
  }
  return records.flatMap((record) => {
    const value = record[key];
    return typeof value === 'string' ? [value] : [];
  });
}

function hasDuplicate(values: readonly string[]): boolean {
  return new Set(values).size !== values.length;
}

const prohibitedKeys = new Set([
  'rawhtml',
  'html',
  'script',
  'scripts',
  'iframe',
  'srcdoc',
  'rawprompt',
  'prompt',
  'prompttext',
  'rawsource',
  'sourcebody',
  'sourcetext',
  'rawarticle',
  'articlebody',
  'articletext',
  'financedata',
  'revenue',
  'revenuedata',
  'affiliaterate',
  'epc',
  'rpm',
  'profit',
  'callback',
  'callbacks',
  'handler',
  'url',
  'urls',
  'origin',
  'origins',
  'public',
  'publicdata',
  'publicfield',
  'publicfields',
  'authoritytoken',
]);
const absoluteAddress = /^(?:(?:https?|ftp|file|mailto|tel|javascript):|\/\/)/i;
const htmlMarkup = /<\/?(?:[a-z][^>]*)>/i;

function normalizedKey(key: string): string {
  return key.replace(/[\s_-]+/g, '').toLowerCase();
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
      prohibitedKeys.has(normalized) ||
      /^on(?:click|submit|load|error|change|input|focus|blur|key|mouse|pointer)/.test(normalized) ||
      hasProhibitedSurface(item)
    );
  });
}

function candidateSemanticIds(value: JsonValue | undefined): readonly string[] {
  if (!isJsonObject(value)) {
    return [];
  }
  const elements = recordArray(value['elements']);
  const ids = [...valuesFor(elements, 'id')];
  const h1 = value['h1'];
  if (isJsonObject(h1) && typeof h1['id'] === 'string') {
    ids.push(h1['id']);
  }
  return ids;
}

function classifyCandidateFailure(
  value: Readonly<Record<string, JsonValue>>,
  expected: ArticleWorkspaceCandidate,
): ArticleWorkspaceErrorCode {
  if (hasProhibitedSurface(value)) {
    return 'ARTICLE_WORKSPACE_PROHIBITED_SURFACE';
  }
  const screens = recordArray(value['catalogScreens']);
  const components = recordArray(value['components']);
  if (
    hasDuplicate(valuesFor(screens, 'id')) ||
    hasDuplicate(valuesFor(components, 'id')) ||
    hasDuplicate(candidateSemanticIds(value['accessibility']))
  ) {
    return 'ARTICLE_WORKSPACE_DUPLICATE_ID';
  }
  if (hasDuplicate(valuesFor(screens, 'route'))) {
    return 'ARTICLE_WORKSPACE_DUPLICATE_ROUTE';
  }
  if (
    !jsonEqual(value['screen'], expected.screen) ||
    !jsonEqual(value['catalogScreens'], expected.catalogScreens) ||
    !jsonEqual(value['canonicalScreenOrder'], expected.canonicalScreenOrder) ||
    !jsonEqual(value['excludedScreenIds'], expected.excludedScreenIds) ||
    !jsonEqual(value['components'], expected.components) ||
    !jsonEqual(value['sourceRefs'], expected.sourceRefs)
  ) {
    return 'ARTICLE_WORKSPACE_METADATA_INVALID';
  }
  if (
    !jsonEqual(value['coordinateSlots'], expected.coordinateSlots) ||
    !jsonEqual(value['workspaceSignals'], expected.workspaceSignals) ||
    !jsonEqual(value['projections'], expected.projections) ||
    !jsonEqual(value['concurrency'], expected.concurrency) ||
    !jsonEqual(value['unsavedChangesGuard'], expected.unsavedChangesGuard) ||
    !jsonEqual(value['seoPreview'], expected.seoPreview)
  ) {
    return 'ARTICLE_WORKSPACE_STATE_INVALID';
  }
  if (!jsonEqual(value['accessibility'], expected.accessibility)) {
    return 'ARTICLE_WORKSPACE_ACCESSIBILITY_INVALID';
  }
  const authorityKeys = [
    'availability',
    'roleInputAccepted',
    'roleMetadataAuthority',
    'routeRegistered',
    'renderEnabled',
    'authenticationEstablished',
    'authorizationGranted',
    'mutationEnabled',
    'persistenceEnabled',
    'providerInvocationEnabled',
    'externalActionEnabled',
    'publicationAuthorized',
    'criticalActionExecutionEnabled',
    'actions',
    'verification',
    'acceptanceAchieved',
    'storyComplete',
    'decision',
    'productionEligible',
  ] as const;
  if (authorityKeys.some((key) => !jsonEqual(value[key], expected[key]))) {
    return 'ARTICLE_WORKSPACE_AUTHORITY_INVALID';
  }
  return 'ARTICLE_WORKSPACE_CANDIDATE_INVALID';
}

export function validateArticleWorkspaceCandidate(value: unknown): ArticleWorkspaceCandidate {
  const clone = cloneStrict(value, 'ARTICLE_WORKSPACE_CANDIDATE_INVALID');
  if (!isJsonObject(clone)) {
    return reject('ARTICLE_WORKSPACE_CANDIDATE_INVALID');
  }
  const screen = clone['screen'];
  if (!isJsonObject(screen)) {
    return reject('ARTICLE_WORKSPACE_CANDIDATE_INVALID');
  }
  const screenId = screen['id'];
  if (
    typeof screenId !== 'string' ||
    !(ARTICLE_WORKSPACE_SCREEN_IDS as readonly string[]).includes(screenId)
  ) {
    return reject('ARTICLE_WORKSPACE_SCREEN_UNKNOWN');
  }
  const expected = buildCandidate(screenId as ArticleWorkspaceScreenId);
  if (!jsonEqual(clone, expected)) {
    return reject(classifyCandidateFailure(clone, expected));
  }
  return clone as unknown as ArticleWorkspaceCandidate;
}

export function createArticleWorkspaceCandidate(
  input: ArticleWorkspaceInput,
): ArticleWorkspaceCandidate {
  return validateArticleWorkspaceCandidate(buildCandidate(validatedScreenId(input)));
}

export const createArticleWorkspaceModel = createArticleWorkspaceCandidate;
export type ArticleWorkspaceModel = ArticleWorkspaceCandidate;
