import { createJsonValue } from './serializable.ts';

export const PORTFOLIO_CATALOG_SCREEN_IDS = createJsonValue([
  'PORT-001',
  'PORT-002',
  'PORT-003',
  'PORT-004',
  'PORT-005',
  'PORT-006',
  'CAT-001',
  'CAT-002',
  'CAT-003',
  'CAT-004',
  'CAT-005',
  'CAT-006',
]) as unknown as readonly [
  'PORT-001',
  'PORT-002',
  'PORT-003',
  'PORT-004',
  'PORT-005',
  'PORT-006',
  'CAT-001',
  'CAT-002',
  'CAT-003',
  'CAT-004',
  'CAT-005',
  'CAT-006',
];

export type PortfolioCatalogScreenId = (typeof PORTFOLIO_CATALOG_SCREEN_IDS)[number];

export type PortfolioCatalogRole =
  | 'PRODUCT_OWNER'
  | 'MANAGING_EDITOR'
  | 'EDITOR'
  | 'REVIEWER'
  | 'ANALYST'
  | 'OPERATOR'
  | 'SECURITY_AUDITOR';

export type PortfolioCatalogArea = 'portfolio' | 'catalog';

export interface PortfolioCatalogScreenMetadata {
  readonly id: PortfolioCatalogScreenId;
  readonly name: string;
  readonly route: string;
  readonly area: PortfolioCatalogArea;
  readonly roles: readonly PortfolioCatalogRole[];
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
    id: 'PORT-001',
    name: 'カテゴリ一覧',
    route: '/admin/portfolio/categories',
    area: 'portfolio',
    roles: ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'EDITOR', 'ANALYST'],
    purpose: 'カテゴリとMVP Scope管理',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'PORT-002',
    name: 'カテゴリ詳細',
    route: '/admin/portfolio/categories/{id}',
    area: 'portfolio',
    roles: ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'EDITOR', 'ANALYST'],
    purpose: 'カテゴリ設定、Freshness、Identity Rule参照',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'PORT-003',
    name: 'Keyword一覧',
    route: '/admin/portfolio/keywords',
    area: 'portfolio',
    roles: ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'EDITOR', 'ANALYST'],
    purpose: 'Keyword、意図、Source、優先度を管理',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'PORT-004',
    name: 'Intent Cluster',
    route: '/admin/portfolio/intents',
    area: 'portfolio',
    roles: ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'EDITOR', 'ANALYST'],
    purpose: '同一意思決定のKeywordをCluster化',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'PORT-005',
    name: 'Opportunity Queue',
    route: '/admin/portfolio/opportunities',
    area: 'portfolio',
    roles: ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'EDITOR', 'ANALYST'],
    purpose: 'AI/Ruleによる候補を人間が評価',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'PORT-006',
    name: 'Article Plan',
    route: '/admin/portfolio/article-plans/{id}',
    area: 'portfolio',
    roles: ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'EDITOR'],
    purpose: '記事目的、候補Universe、記事型を確定',
    mvp: true,
    criticalAction: false,
    apiDependencies: ['ArticlePlan', 'IntentCluster'],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'CAT-001',
    name: '楽天取込Run',
    route: '/admin/catalog/ingestion-runs',
    area: 'catalog',
    roles: ['EDITOR', 'OPERATOR', 'ANALYST'],
    purpose: '取得状況、Rate Limit、Raw Artifactを確認',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'CAT-002',
    name: '商品候補一覧',
    route: '/admin/catalog/candidates',
    area: 'catalog',
    roles: ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
    purpose: '未統合候補を検索・絞込',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'CAT-003',
    name: '商品同一性Workbench',
    route: '/admin/catalog/identity-workbench',
    area: 'catalog',
    roles: ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
    purpose: '型番・Variant・Bundleを根拠付きで統合/分離',
    mvp: true,
    criticalAction: true,
    apiDependencies: ['ProductCandidate', 'GroupingDecision'],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'CAT-004',
    name: 'Canonical Product',
    route: '/admin/catalog/products/{id}',
    area: 'catalog',
    roles: ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER', 'ANALYST'],
    purpose: '商品属性、Variant、Evidence、履歴を表示',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'CAT-005',
    name: 'Offer詳細',
    route: '/admin/catalog/offers/{id}',
    area: 'catalog',
    roles: ['EDITOR', 'REVIEWER', 'ANALYST'],
    purpose: 'ショップ別Offer、価格、在庫、送料、鮮度を表示',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'CAT-006',
    name: 'Raw Artifact Viewer',
    route: '/admin/artifacts/{id}',
    area: 'catalog',
    roles: ['EDITOR', 'REVIEWER', 'OPERATOR', 'SECURITY_AUDITOR'],
    purpose: '原本Hash、取得情報、許可された表示を確認',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
] as const;

export const PORTFOLIO_CATALOG_SCREENS = createJsonValue(
  screenMetadataSource,
) as unknown as readonly PortfolioCatalogScreenMetadata[];

export interface PortfolioCatalogSourceArtifact {
  readonly path: string;
  readonly sha256: string;
}

export interface PortfolioCatalogSourceBinding {
  readonly storyId: 'ST-0501' | 'ST-0504' | 'ST-1101';
  readonly commit: string;
  readonly artifacts: readonly PortfolioCatalogSourceArtifact[];
  readonly semantics: Readonly<Record<string, unknown>>;
}

const sourceBindingsSource = [
  {
    storyId: 'ST-0501',
    commit: '1021982aff6bcab504e2c060ea0f82797b4dccf2',
    artifacts: [
      {
        path: 'changes/st-0501/README.md',
        sha256: '7c1e37d68bbb149641099c805db65f41544136d52f35c9a620196c7c9ce654c2',
      },
      {
        path: 'python/raos/adapters/recorded_portfolio_workflow.py',
        sha256: 'b8c1ff8d6b6d1cda8abf6a2d045d5bd1b37dd42a2bf744d7af36818a03b74873',
      },
      {
        path: 'python/raos/application/portfolio/workflow.py',
        sha256: '9a95d050aef5811402c6a8f47df2d896e1214838ab924bbd049d717b3184939e',
      },
      {
        path: 'python/raos/domain/editorial/article_plan.py',
        sha256: 'e3f885409a3b38ea495a75fa9fc4f63ac6bac40a96607ec2f98a1993c154ce3e',
      },
      {
        path: 'python/raos/domain/portfolio/workflow.py',
        sha256: '3ca1aee58d9e733d1181a31af4e3fea2945a001170a759263a6787b29ed689d8',
      },
      {
        path: 'python/raos/ports/portfolio_workflow.py',
        sha256: '24266b23830d4f2e4fdbb066797201c14fc131ea4d5fb40d937d5c2ed559f9a1',
      },
      {
        path: 'tests/st0501/conftest.py',
        sha256: 'fdb3c0ec7462a9a6e0f45f38ba061bbfbc9c34cea752d3c5fc8dda0b6ff029cb',
      },
      {
        path: 'tests/st0501/test_boundaries.py',
        sha256: 'f123906786f49646c40ca09ab4c63b67c8c7458bd37e16d1ba933524659f2e74',
      },
      {
        path: 'tests/st0501/test_workflow.py',
        sha256: 'd3b691bd4ffc1bb0525524b2631a99aa0f3eddaad18174a705eece3536d3a757',
      },
    ],
    semantics: {
      classification: 'MAXIMUM_SAFE_LOCAL_RECORDED_NON_PERSISTENT_PORTFOLIO_WORKFLOW_SEAM',
      operationCount: 16,
      operations: ['LIST', 'CREATE', 'GET', 'UPDATE'],
      deleteRepresented: false,
      repository: 'ABSENT',
      persistence: 'NOT_EXECUTED',
      transaction: 'ABSENT',
      realSiteSelected: false,
      identityAction: 'NOT_EXECUTED',
      financeAction: 'NOT_EXECUTED',
      publicationAction: 'NOT_EXECUTED',
    },
  },
  {
    storyId: 'ST-0504',
    commit: 'b78b4e3330faadc571207ccec889ba107eaf3bb7',
    artifacts: [
      {
        path: 'changes/st-0504/README.md',
        sha256: 'f53d62f70eddc08820a2f7c4b854fd8f3e05a86b148d107307ca3baf32bab958',
      },
      {
        path: 'changes/st-0504/contracts/product-identity-human-review-reference-plan.v1.yaml',
        sha256: '246c21aa1d79489ed8c8a02fe0b7d1a50ffe1b2f7e85fcc4ba210369477512b8',
      },
      {
        path: 'changes/st-0504/generated/product-identity-human-review-reference-plan.v1.json',
        sha256: '468e587b12856cd1c9732a34b1da985c0126b0de58026c0169f5c30e7357156e',
      },
      {
        path: 'changes/st-0504/manifest.yaml',
        sha256: '2c2a8e08816d618825957c9e1c8fae21e45877ee44eeb21f30b21daa8b9eefc6',
      },
      {
        path: 'scripts/build_st0504_product_identity_human_review_reference_plan.py',
        sha256: '4e41ba75ea941fecba3c4152b8ee0742d106406f38063ae3270e5ec1bce87c86',
      },
      {
        path: 'tests/st0504/conftest.py',
        sha256: 'e76a58c45929decedbbcc268bf0b56f8aadfe8c44332de3674523812ab5bc530',
      },
      {
        path: 'tests/st0504/test_contract.py',
        sha256: '53d0a82d3441c6dba1845658175d699d3919180bd76abad238ca7b037572aa75',
      },
      {
        path: 'tests/st0504/test_generation.py',
        sha256: '5e86d5f8c8662f290890c8eaf9ac78a62060c6013d420eb8974ec1a77d82f9a8',
      },
      {
        path: 'tests/st0504/test_negative_cases.py',
        sha256: '9e74abaa1be9d514edb6be64d07613b42d75db578cb5e8c31a3c430f26bc9764',
      },
    ],
    semantics: {
      classification: 'SOURCE_DERIVED_NON_EXECUTABLE_PRODUCT_IDENTITY_HUMAN_REVIEW_REFERENCE_PLAN',
      openDecision: 'OD-006',
      decision: 'NOT_READY',
      automaticMergeEnabled: false,
      automaticSplitEnabled: false,
      humanReviewRequired: true,
      humanReviewStatus: 'REQUIRED_NOT_EXECUTED',
      identityDecisions: [],
      memberships: [],
      merges: [],
      splits: [],
      reviewRecords: [],
      approval: null,
      persistence: 'NOT_EXECUTED',
    },
  },
  {
    storyId: 'ST-1101',
    commit: '6933612a49863591555137868ca0cec935cf65e4',
    artifacts: [
      {
        path: 'changes/st-1101/README.md',
        sha256: 'b2bb91e89d5948f8081853e39596951adcee16974ce2a6ffa159892310ead08c',
      },
      {
        path: 'packages/web-ui/src/app-shell.ts',
        sha256: '600c7aa29ddf9572390f7e2eec8710ed726746aa41125fe23abe2f72ba820129',
      },
      {
        path: 'packages/web-ui/src/data-table.ts',
        sha256: 'bb999786019d1c01ece36929124359af00c5362134c4ee4faf50ce496d3689f4',
      },
      {
        path: 'packages/web-ui/src/dialog.ts',
        sha256: '494ac8b9e2a4087de2d003dd6c28bfcab7c85961f418a5892453c865058724bc',
      },
      {
        path: 'packages/web-ui/src/form.ts',
        sha256: '6dd2a9a71ce4d7949485c3d1eedcf05cc123fcf038961486f693090c9c5cd327',
      },
      {
        path: 'packages/web-ui/src/index.ts',
        sha256: '0b1c11f13023eaedd2dc871df8d629d215f56bd69a501de69d1342f4ecc2985a',
      },
      {
        path: 'packages/web-ui/src/route-guard.ts',
        sha256: '8395f542c7c65445fa3d1bec4a0e037c96610da8589e1807604b4fb3fa6a584f',
      },
      {
        path: 'packages/web-ui/src/serializable.ts',
        sha256: '56adb1e0356fba66e147be4c055b7a40f1115608a3e29bbee4584234f8b3273d',
      },
      {
        path: 'packages/web-ui/src/tokens.ts',
        sha256: '548dddcf8410c95daae7e5fb6a27521949ed4512c581b97c92bb0cb2484507ef',
      },
      {
        path: 'packages/web-ui/tsconfig.json',
        sha256: 'f3b3977032741514c83608c6de93529b5bc2bb0151a5518e767714d78e815b32',
      },
      {
        path: 'tests/st1101/app-shell-and-route-guard.test.ts',
        sha256: '194e7e97244007b0b17217b581d0ddb68b426e662615959ab22905251aebb24c',
      },
      {
        path: 'tests/st1101/data-table.test.ts',
        sha256: '670329de6711bc0e8266b8c5022af33876d40b5668446b1abf2be62da5ad2b51',
      },
      {
        path: 'tests/st1101/form-and-dialog.test.ts',
        sha256: '754c451fd08c0579336796cd9b558f2fd8f38ad5134b6e491bbf514115704337',
      },
      {
        path: 'tests/st1101/serializable-and-tokens.test.ts',
        sha256: 'd500f6fba8eefe66d27a2ba1d1ca91f2ca4585502c8a654f91ca973791b58f5b',
      },
    ],
    semantics: {
      registeredScreenIds: ['ADM-001'],
      registeredPaths: ['/admin'],
      adminAvailability: 'DISABLED_AUTH_TRANSPORT_UNRESOLVED',
      portfolioCatalogScreenIdsRegistered: [],
      portfolioCatalogRoutesRegistered: [],
      navigationExecution: 'NOT_EXECUTED',
      renderExecution: 'NOT_EXECUTED',
      backendReauthenticationRequired: true,
      backendReauthorizationRequired: true,
    },
  },
] as const;

export const PORTFOLIO_CATALOG_SOURCE_BINDINGS = createJsonValue(
  sourceBindingsSource,
) as unknown as readonly [
  PortfolioCatalogSourceBinding,
  PortfolioCatalogSourceBinding,
  PortfolioCatalogSourceBinding,
];

export const PORTFOLIO_CATALOG_MODEL_ERROR_CODES = createJsonValue([
  'PORTFOLIO_CATALOG_INPUT_INVALID',
  'PORTFOLIO_CATALOG_SCREEN_UNKNOWN',
]) as unknown as readonly ['PORTFOLIO_CATALOG_INPUT_INVALID', 'PORTFOLIO_CATALOG_SCREEN_UNKNOWN'];

export type PortfolioCatalogModelErrorCode = (typeof PORTFOLIO_CATALOG_MODEL_ERROR_CODES)[number];

export class PortfolioCatalogModelError extends TypeError {
  readonly code: PortfolioCatalogModelErrorCode;

  constructor(code: PortfolioCatalogModelErrorCode) {
    super(code);
    this.name = 'PortfolioCatalogModelError';
    this.code = code;
    Object.freeze(this);
  }
}

export interface PortfolioCatalogWorkspaceInput {
  readonly screenId: PortfolioCatalogScreenId;
}

export interface PortfolioCatalogWorkspaceModel {
  readonly classification: 'SOURCE_DERIVED_DISABLED_HEADLESS_PORTFOLIO_CATALOG_WORKSPACE_MODEL';
  readonly screen: PortfolioCatalogScreenMetadata;
  readonly canonicalScreenOrder: readonly PortfolioCatalogScreenId[];
  readonly sourceBindings: readonly PortfolioCatalogSourceBinding[];
  readonly availability: 'DISABLED';
  readonly routeRegistration: 'UNREGISTERED';
  readonly navigationEligible: false;
  readonly renderEligible: false;
  readonly authorizationGranted: false;
  readonly roleMetadataAuthority: 'DISPLAY_ONLY_NOT_AUTHORIZATION';
  readonly backendReauthenticationRequired: true;
  readonly backendReauthorizationRequired: true;
  readonly authentication: 'NOT_EXECUTED';
  readonly dataAccess: 'NOT_EXECUTED';
  readonly apiAccess: 'NOT_EXECUTED';
  readonly crudExecution: 'NOT_EXECUTED';
  readonly identityExecution: 'NOT_EXECUTED';
  readonly commandExecution: 'NOT_EXECUTED';
  readonly effectExecution: 'NOT_EXECUTED';
  readonly dataState: {
    readonly status: 'NOT_LOADED';
    readonly items: readonly [];
    readonly itemCount: null;
  };
  readonly actions: readonly [];
  readonly concurrency: {
    readonly etag: null;
    readonly ifMatch: null;
    readonly lockVersion: null;
    readonly status: 'NOT_EVALUATED';
  };
  readonly identityBoundary: {
    readonly openDecision: 'OD-006';
    readonly automaticMergeEnabled: false;
    readonly automaticSplitEnabled: false;
    readonly humanReviewRequired: true;
    readonly humanReviewStatus: 'REQUIRED_NOT_EXECUTED';
    readonly identityDecisions: readonly [];
    readonly reviews: readonly [];
    readonly approvals: readonly [];
    readonly merges: readonly [];
    readonly splits: readonly [];
  };
  readonly financeBoundary: {
    readonly visibility: 'HIDDEN';
    readonly fields: readonly [];
    readonly access: 'NOT_EXECUTED';
  };
  readonly accessibility: {
    readonly keyboardOperabilityRequired: true;
    readonly visibleFocusRequired: true;
    readonly semanticStructureRequired: true;
    readonly screenReaderLabelsRequired: true;
    readonly browserVerification: 'NOT_EXECUTED';
    readonly automatedAccessibilityVerification: 'NOT_EXECUTED';
    readonly manualKeyboardVerification: 'NOT_EXECUTED';
    readonly screenReaderVerification: 'NOT_EXECUTED';
  };
  readonly decision: 'NOT_READY';
  readonly productionEligible: false;
}

function reject(code: PortfolioCatalogModelErrorCode): never {
  throw new PortfolioCatalogModelError(code);
}

function validatedScreenId(input: PortfolioCatalogWorkspaceInput): PortfolioCatalogScreenId {
  let value: ReturnType<typeof createJsonValue>;
  try {
    value = createJsonValue(input);
  } catch {
    return reject('PORTFOLIO_CATALOG_INPUT_INVALID');
  }
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return reject('PORTFOLIO_CATALOG_INPUT_INVALID');
  }
  const record = value as Readonly<Record<string, unknown>>;
  const keys = Object.keys(record);
  if (keys.length !== 1 || keys[0] !== 'screenId') {
    return reject('PORTFOLIO_CATALOG_INPUT_INVALID');
  }
  const screenId = record['screenId'];
  if (typeof screenId !== 'string') {
    return reject('PORTFOLIO_CATALOG_INPUT_INVALID');
  }
  if (!(PORTFOLIO_CATALOG_SCREEN_IDS as readonly string[]).includes(screenId)) {
    return reject('PORTFOLIO_CATALOG_SCREEN_UNKNOWN');
  }
  return screenId as PortfolioCatalogScreenId;
}

export function createPortfolioCatalogWorkspaceModel(
  input: PortfolioCatalogWorkspaceInput,
): PortfolioCatalogWorkspaceModel {
  const screenId = validatedScreenId(input);
  const screen = PORTFOLIO_CATALOG_SCREENS.find((item) => item.id === screenId);
  if (screen === undefined) {
    return reject('PORTFOLIO_CATALOG_SCREEN_UNKNOWN');
  }
  return createJsonValue({
    classification: 'SOURCE_DERIVED_DISABLED_HEADLESS_PORTFOLIO_CATALOG_WORKSPACE_MODEL',
    screen,
    canonicalScreenOrder: PORTFOLIO_CATALOG_SCREEN_IDS,
    sourceBindings: PORTFOLIO_CATALOG_SOURCE_BINDINGS,
    availability: 'DISABLED',
    routeRegistration: 'UNREGISTERED',
    navigationEligible: false,
    renderEligible: false,
    authorizationGranted: false,
    roleMetadataAuthority: 'DISPLAY_ONLY_NOT_AUTHORIZATION',
    backendReauthenticationRequired: true,
    backendReauthorizationRequired: true,
    authentication: 'NOT_EXECUTED',
    dataAccess: 'NOT_EXECUTED',
    apiAccess: 'NOT_EXECUTED',
    crudExecution: 'NOT_EXECUTED',
    identityExecution: 'NOT_EXECUTED',
    commandExecution: 'NOT_EXECUTED',
    effectExecution: 'NOT_EXECUTED',
    dataState: {
      status: 'NOT_LOADED',
      items: [],
      itemCount: null,
    },
    actions: [],
    concurrency: {
      etag: null,
      ifMatch: null,
      lockVersion: null,
      status: 'NOT_EVALUATED',
    },
    identityBoundary: {
      openDecision: 'OD-006',
      automaticMergeEnabled: false,
      automaticSplitEnabled: false,
      humanReviewRequired: true,
      humanReviewStatus: 'REQUIRED_NOT_EXECUTED',
      identityDecisions: [],
      reviews: [],
      approvals: [],
      merges: [],
      splits: [],
    },
    financeBoundary: {
      visibility: 'HIDDEN',
      fields: [],
      access: 'NOT_EXECUTED',
    },
    accessibility: {
      keyboardOperabilityRequired: true,
      visibleFocusRequired: true,
      semanticStructureRequired: true,
      screenReaderLabelsRequired: true,
      browserVerification: 'NOT_EXECUTED',
      automatedAccessibilityVerification: 'NOT_EXECUTED',
      manualKeyboardVerification: 'NOT_EXECUTED',
      screenReaderVerification: 'NOT_EXECUTED',
    },
    decision: 'NOT_READY',
    productionEligible: false,
  }) as unknown as PortfolioCatalogWorkspaceModel;
}
