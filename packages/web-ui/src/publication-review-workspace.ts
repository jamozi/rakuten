import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const PUBLICATION_REVIEW_SCREEN_IDS = createJsonValue([
  'REV-001',
  'REV-002',
  'REV-003',
  'PUBA-001',
  'PUBA-002',
  'PUBA-003',
  'PUBA-004',
]) as unknown as readonly [
  'REV-001',
  'REV-002',
  'REV-003',
  'PUBA-001',
  'PUBA-002',
  'PUBA-003',
  'PUBA-004',
];

export type PublicationReviewScreenId = (typeof PUBLICATION_REVIEW_SCREEN_IDS)[number];
export type PublicationReviewRole = 'MANAGING_EDITOR' | 'REVIEWER' | 'OPERATOR';

export interface PublicationReviewScreenMetadata {
  readonly id: PublicationReviewScreenId;
  readonly name: string;
  readonly route: string;
  readonly area: 'review' | 'publishing';
  readonly roles: readonly PublicationReviewRole[];
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
    id: 'REV-001',
    name: 'Review Queue',
    route: '/admin/reviews',
    area: 'review',
    roles: ['MANAGING_EDITOR', 'REVIEWER'],
    purpose: 'レビュー対象をRisk/期限で優先表示',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'REV-002',
    name: 'Editorial Review',
    route: '/admin/reviews/{versionId}',
    area: 'review',
    roles: ['REVIEWER', 'MANAGING_EDITOR'],
    purpose: '75項目ChecklistとFindingを記録',
    mvp: true,
    criticalAction: true,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'REV-003',
    name: 'Final Approval',
    route: '/admin/approvals/{versionId}',
    area: 'review',
    roles: ['MANAGING_EDITOR'],
    purpose: '全Gateと差分を確認し承認/差戻し',
    mvp: true,
    criticalAction: true,
    apiDependencies: ['FinalApproval'],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'PUBA-001',
    name: 'Publication Queue',
    route: '/admin/publications',
    area: 'publishing',
    roles: ['MANAGING_EDITOR', 'OPERATOR'],
    purpose: '公開候補とBlockerを表示',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'PUBA-002',
    name: 'Snapshot Preview',
    route: '/admin/publications/{id}/preview',
    area: 'publishing',
    roles: ['MANAGING_EDITOR', 'REVIEWER', 'OPERATOR'],
    purpose: '実際の公開Snapshotを隔離Preview',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'PUBA-003',
    name: 'Publish Command',
    route: '/admin/publications/{id}/publish',
    area: 'publishing',
    roles: ['MANAGING_EDITOR', 'OPERATOR'],
    purpose: 'step-up後に冪等公開Commandを送る',
    mvp: true,
    criticalAction: true,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'PUBA-004',
    name: 'Rollback',
    route: '/admin/publications/{id}/rollback',
    area: 'publishing',
    roles: ['MANAGING_EDITOR', 'OPERATOR'],
    purpose: '旧Snapshotへ戻し理由を監査記録',
    mvp: true,
    criticalAction: true,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
] as const;

export const PUBLICATION_REVIEW_SCREENS = createJsonValue(
  screenMetadataSource,
) as unknown as readonly PublicationReviewScreenMetadata[];

export const PUBLICATION_REVIEW_COMPONENT_IDS = createJsonValue([
  'UI-C005',
  'UI-C006',
  'UI-C007',
  'UI-C008',
  'UI-C010',
  'UI-C011',
  'UI-C012',
  'UI-C013',
  'UI-C015',
  'UI-C016',
  'UI-C025',
  'UI-C026',
  'UI-C027',
  'UI-C028',
  'UI-C041',
]) as unknown as readonly [
  'UI-C005',
  'UI-C006',
  'UI-C007',
  'UI-C008',
  'UI-C010',
  'UI-C011',
  'UI-C012',
  'UI-C013',
  'UI-C015',
  'UI-C016',
  'UI-C025',
  'UI-C026',
  'UI-C027',
  'UI-C028',
  'UI-C041',
];

export type PublicationReviewComponentId = (typeof PUBLICATION_REVIEW_COMPONENT_IDS)[number];

export interface PublicationReviewComponentMetadata {
  readonly id: PublicationReviewComponentId;
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
  ['UI-C005', 'StatusBadge', 'shared', 'Text＋Iconで状態を表現'],
  ['UI-C006', 'SeverityBadge', 'admin', 'Finding/Incident severity'],
  ['UI-C007', 'DataTable', 'admin', '列選択、Sort、Pagination、Keyboard操作'],
  ['UI-C008', 'FilterBar', 'admin', 'URL同期Filter'],
  ['UI-C010', 'EmptyState', 'shared', '理由と次Action'],
  ['UI-C011', 'ErrorSummary', 'shared', 'Form errorを先頭へ集約'],
  ['UI-C012', 'ConfirmDialog', 'admin', '破壊的Actionの対象・影響・取消可能性を表示'],
  ['UI-C013', 'StepUpDialog', 'admin', '再認証が必要なCritical Action'],
  ['UI-C015', 'VersionDiff', 'admin', '追加/削除/変更と出所を比較'],
  ['UI-C016', 'AuditTimeline', 'admin', 'Actor、時刻、Correlation ID'],
  ['UI-C025', 'QualityGatePanel', 'admin', 'Gate結果とBlocking Finding'],
  ['UI-C026', 'ReviewChecklist', 'admin', '必須項目、Evidence、判定'],
  ['UI-C027', 'ApprovalPanel', 'admin', '承認対象Hashと差分'],
  ['UI-C028', 'PublicationPreview', 'admin', 'Public Snapshot Preview'],
  ['UI-C041', 'ToastRegion', 'shared', 'ARIA liveを乱用しない通知'],
] as const;

export const PUBLICATION_REVIEW_COMPONENTS = createJsonValue(
  componentMetadataSource.map(([id, name, area, purpose]) => ({
    id,
    name,
    area,
    purpose,
    keyboardRequired: true,
    screenReaderRequired: true,
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  })),
) as unknown as readonly PublicationReviewComponentMetadata[];

export interface PublicationReviewSourceReference {
  readonly scope:
    | 'STORY'
    | 'SCREENS'
    | 'COMPONENTS'
    | 'WORKFLOWS'
    | 'DESIGN'
    | 'ACCESSIBILITY'
    | 'SECURITY'
    | 'TESTS'
    | 'DEPENDENCY';
  readonly path: string;
  readonly locator: string;
  readonly sha256: string;
  readonly consumption: 'STATIC_METADATA_ONLY' | 'REFERENCE_ONLY_NO_RUNTIME_IMPORT';
}

const sourceReferenceSource = [
  {
    scope: 'STORY',
    path: 'docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml',
    locator: 'ST-0906',
    sha256: '4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d',
    consumption: 'STATIC_METADATA_ONLY',
  },
  {
    scope: 'SCREENS',
    path: 'docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml',
    locator: 'REV-001..REV-003,PUBA-001..PUBA-004',
    sha256: 'dae723c7e423febe4abc0ab8752420411e6e95586069b75186bda7e92de85050',
    consumption: 'STATIC_METADATA_ONLY',
  },
  {
    scope: 'COMPONENTS',
    path: 'docs/canonical/02_ui/RAOS_08_component_catalog_v1.0.yaml',
    locator: 'ST-0906 display requirements only',
    sha256: '986ed1682b0f6b48c7e9fab04ff51229c000f4673e3cc3981e50903832f208f2',
    consumption: 'STATIC_METADATA_ONLY',
  },
  {
    scope: 'WORKFLOWS',
    path: 'docs/canonical/02_ui/RAOS_08_workflow_catalog_v1.0.yaml',
    locator: 'UI-WF-005,UI-WF-006,UI-WF-007',
    sha256: '59983683ec920cf450d0d887ee43f0b9871e500c2025562f9bec5c6bbc6fe87e',
    consumption: 'STATIC_METADATA_ONLY',
  },
  {
    scope: 'DESIGN',
    path: 'docs/canonical/02_ui/RAOS_08_ui_ux_design_v1.0.md',
    locator: 'sections 2,4,6,8,13,14',
    sha256: '0cec24c40dfa69c14d51fb73e56977790ee19ed0ad5ed74d0339553ff25b860e',
    consumption: 'STATIC_METADATA_ONLY',
  },
  {
    scope: 'ACCESSIBILITY',
    path: 'docs/canonical/02_ui/RAOS_08_accessibility_checklist_v1.0.csv',
    locator: 'A11Y-001..A11Y-015,A11Y-020..A11Y-027,A11Y-030',
    sha256: '690233f34abb08608e3e1241e6108fb93d4c6bb47ffe23be02e34f2a02b6d77e',
    consumption: 'STATIC_METADATA_ONLY',
  },
  {
    scope: 'SECURITY',
    path: 'docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md',
    locator: 'sections 4,10,13,14',
    sha256: '6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b',
    consumption: 'STATIC_METADATA_ONLY',
  },
  {
    scope: 'SECURITY',
    path: 'docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml',
    locator: 'final_approve,publish,rollback',
    sha256: 'dfd67960ca8a004bbe6f3249ca9fa64ab1b24e94a57a2e88fc282267adc8b984',
    consumption: 'STATIC_METADATA_ONLY',
  },
  {
    scope: 'TESTS',
    path: 'docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml',
    locator: 'TST-022,TST-024',
    sha256: '7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b',
    consumption: 'STATIC_METADATA_ONLY',
  },
  {
    scope: 'DEPENDENCY',
    path: 'changes/st-0901/README_PR3.md',
    locator: 'recorded negative review decisions only',
    sha256: '38bd82a5d7586ee78f7852d27aabfd18360796f21c45f05487f404da2976ce6d',
    consumption: 'REFERENCE_ONLY_NO_RUNTIME_IMPORT',
  },
  {
    scope: 'DEPENDENCY',
    path: 'changes/st-0902/README.md',
    locator: 'non-executable final approval reference plan',
    sha256: '2f7a746f806f18f47acff531a73f2617e601b09fdaad555cbe17f934e586c7ca',
    consumption: 'REFERENCE_ONLY_NO_RUNTIME_IMPORT',
  },
  {
    scope: 'DEPENDENCY',
    path: 'changes/st-0903/README.md',
    locator: 'non-authoritative publication snapshot reference plan',
    sha256: 'e43d6e187acf7cae41fa3b57c429eef6bd846678ae22d42e2a128a3139e503d3',
    consumption: 'REFERENCE_ONLY_NO_RUNTIME_IMPORT',
  },
  {
    scope: 'DEPENDENCY',
    path: 'changes/st-0904/README.md',
    locator: 'non-executable public projection reference plan',
    sha256: 'e4015ac16ddd7383b0848283bebe2348020fb2fe7711d3a41a05e608b4ed2f16',
    consumption: 'REFERENCE_ONLY_NO_RUNTIME_IMPORT',
  },
  {
    scope: 'DEPENDENCY',
    path: 'changes/st-0905/README.md',
    locator: 'non-executable publication command reference plan',
    sha256: '93d1fa584086c8b2d528d09761e3bab9180bad8b09bb3fbcae4dfe11f81706cf',
    consumption: 'REFERENCE_ONLY_NO_RUNTIME_IMPORT',
  },
  {
    scope: 'DEPENDENCY',
    path: 'changes/st-1101/README.md',
    locator: 'disabled headless admin shell',
    sha256: 'b2bb91e89d5948f8081853e39596951adcee16974ce2a6ffa159892310ead08c',
    consumption: 'REFERENCE_ONLY_NO_RUNTIME_IMPORT',
  },
] as const;

export const PUBLICATION_REVIEW_SOURCE_REFS = createJsonValue(
  sourceReferenceSource,
) as unknown as readonly PublicationReviewSourceReference[];

export const PUBLICATION_REVIEW_LAYOUT_SECTION_IDS = createJsonValue([
  'ORIENTATION',
  'BLOCKERS',
  'REVIEW',
  'DIFF',
  'PREVIEW',
]) as unknown as readonly ['ORIENTATION', 'BLOCKERS', 'REVIEW', 'DIFF', 'PREVIEW'];

export type PublicationReviewLayoutSectionId =
  (typeof PUBLICATION_REVIEW_LAYOUT_SECTION_IDS)[number];

export interface PublicationReviewLayoutSection {
  readonly id: PublicationReviewLayoutSectionId;
  readonly heading: string;
  readonly purpose: string;
  readonly presentation: 'PLAIN_SECTION_WITH_DIVIDER';
  readonly card: false;
  readonly status: 'STATIC_METADATA_ONLY' | 'NOT_LOADED';
}

const layoutSectionSource = [
  {
    id: 'ORIENTATION',
    heading: 'Publication review context',
    purpose: 'Identify the selected workflow and its closed operating state.',
    presentation: 'PLAIN_SECTION_WITH_DIVIDER',
    card: false,
    status: 'STATIC_METADATA_ONLY',
  },
  {
    id: 'BLOCKERS',
    heading: 'Blockers',
    purpose: 'Show why runtime data and critical operations are unavailable.',
    presentation: 'PLAIN_SECTION_WITH_DIVIDER',
    card: false,
    status: 'STATIC_METADATA_ONLY',
  },
  {
    id: 'REVIEW',
    heading: 'Review status',
    purpose: 'Reserve checklist and gate context without recording a decision.',
    presentation: 'PLAIN_SECTION_WITH_DIVIDER',
    card: false,
    status: 'NOT_LOADED',
  },
  {
    id: 'DIFF',
    heading: 'Version diff',
    purpose: 'Reserve a text-labelled comparison region without version content.',
    presentation: 'PLAIN_SECTION_WITH_DIVIDER',
    card: false,
    status: 'NOT_LOADED',
  },
  {
    id: 'PREVIEW',
    heading: 'Publication preview',
    purpose: 'Reserve an isolated snapshot region without rendering a snapshot.',
    presentation: 'PLAIN_SECTION_WITH_DIVIDER',
    card: false,
    status: 'NOT_LOADED',
  },
] as const;

export const PUBLICATION_REVIEW_LAYOUT_SECTIONS = createJsonValue(
  layoutSectionSource,
) as unknown as readonly PublicationReviewLayoutSection[];

export const PUBLICATION_REVIEW_SEMANTIC_IDS = createJsonValue({
  skipLink: 'publication-review-skip-link',
  header: 'publication-review-header',
  main: 'publication-review-main',
  heading: 'publication-review-heading',
  orientation: 'publication-review-orientation',
  blockers: 'publication-review-blockers',
  review: 'publication-review-review',
  diff: 'publication-review-diff',
  preview: 'publication-review-preview',
  status: 'publication-review-status',
}) as unknown as Readonly<{
  skipLink: 'publication-review-skip-link';
  header: 'publication-review-header';
  main: 'publication-review-main';
  heading: 'publication-review-heading';
  orientation: 'publication-review-orientation';
  blockers: 'publication-review-blockers';
  review: 'publication-review-review';
  diff: 'publication-review-diff';
  preview: 'publication-review-preview';
  status: 'publication-review-status';
}>;

export const PUBLICATION_REVIEW_ERROR_CODES = createJsonValue([
  'PUBLICATION_REVIEW_INPUT_INVALID',
  'PUBLICATION_REVIEW_SCREEN_UNKNOWN',
  'PUBLICATION_REVIEW_CANDIDATE_INVALID',
  'PUBLICATION_REVIEW_DUPLICATE_ID',
  'PUBLICATION_REVIEW_DUPLICATE_ROUTE',
  'PUBLICATION_REVIEW_METADATA_INVALID',
  'PUBLICATION_REVIEW_LAYOUT_INVALID',
  'PUBLICATION_REVIEW_STATE_INVALID',
  'PUBLICATION_REVIEW_ACCESSIBILITY_INVALID',
  'PUBLICATION_REVIEW_AUTHORITY_INVALID',
  'PUBLICATION_REVIEW_PROHIBITED_SURFACE',
]) as unknown as readonly [
  'PUBLICATION_REVIEW_INPUT_INVALID',
  'PUBLICATION_REVIEW_SCREEN_UNKNOWN',
  'PUBLICATION_REVIEW_CANDIDATE_INVALID',
  'PUBLICATION_REVIEW_DUPLICATE_ID',
  'PUBLICATION_REVIEW_DUPLICATE_ROUTE',
  'PUBLICATION_REVIEW_METADATA_INVALID',
  'PUBLICATION_REVIEW_LAYOUT_INVALID',
  'PUBLICATION_REVIEW_STATE_INVALID',
  'PUBLICATION_REVIEW_ACCESSIBILITY_INVALID',
  'PUBLICATION_REVIEW_AUTHORITY_INVALID',
  'PUBLICATION_REVIEW_PROHIBITED_SURFACE',
];

export type PublicationReviewErrorCode = (typeof PUBLICATION_REVIEW_ERROR_CODES)[number];

export class PublicationReviewError extends TypeError {
  readonly code: PublicationReviewErrorCode;

  constructor(code: PublicationReviewErrorCode) {
    const closedCode = (PUBLICATION_REVIEW_ERROR_CODES as readonly unknown[]).includes(code)
      ? code
      : 'PUBLICATION_REVIEW_CANDIDATE_INVALID';
    super(closedCode);
    this.name = 'PublicationReviewError';
    this.code = closedCode;
    Object.freeze(this);
  }
}

export interface PublicationReviewWorkspaceInput {
  readonly screenId: PublicationReviewScreenId;
}

export interface PublicationReviewDependencyState {
  readonly storyId: 'ST-0901' | 'ST-0902' | 'ST-0903' | 'ST-0904' | 'ST-0905' | 'ST-1101';
  readonly relationship: 'DIRECT' | 'SCREEN_PREREQUISITE';
  readonly status:
    'RECORDED_LOCAL_REVIEW_ONLY' | 'NONEXECUTABLE_REFERENCE_PLAN' | 'DISABLED_HEADLESS_FOUNDATION';
  readonly runtimeConnected: false;
  readonly authoritative: false;
  readonly effectPermitted: false;
}

export interface PublicationReviewCapabilityState {
  readonly screenId: PublicationReviewScreenId;
  readonly availability:
    | 'STATIC_CATALOG_ONLY'
    | 'RECORDED_DEPENDENCY_REFERENCE_ONLY'
    | 'BLOCKED_DEPENDENCY_NOT_EXECUTABLE';
  readonly reasonCode:
    | 'ROUTE_AND_DATA_SOURCE_UNAVAILABLE'
    | 'RECORDED_REVIEW_IS_NOT_UI_OR_AUTHORITY'
    | 'FINAL_APPROVAL_AUTHORITY_UNAVAILABLE'
    | 'PUBLICATION_CANDIDATE_SOURCE_UNAVAILABLE'
    | 'AUTHORITATIVE_SNAPSHOT_UNAVAILABLE'
    | 'PUBLISH_COMMAND_AUTHORITY_UNAVAILABLE'
    | 'ROLLBACK_COMMAND_AUTHORITY_UNAVAILABLE';
  readonly payload: null;
  readonly effectPermitted: false;
  readonly intentEmittable: false;
}

export interface PublicationReviewWorkspaceModel {
  readonly classification: 'SOURCE_DERIVED_DISABLED_HEADLESS_PUBLICATION_REVIEW_WORKSPACE';
  readonly storyId: 'ST-0906';
  readonly objective: 'review/approval/preview/publish/rollback画面';
  readonly screen: PublicationReviewScreenMetadata;
  readonly catalogScreens: readonly PublicationReviewScreenMetadata[];
  readonly canonicalScreenOrder: typeof PUBLICATION_REVIEW_SCREEN_IDS;
  readonly componentRequirements: readonly PublicationReviewComponentMetadata[];
  readonly sourceRefs: readonly PublicationReviewSourceReference[];
  readonly dependencyStates: readonly PublicationReviewDependencyState[];
  readonly availability: 'DISABLED_DEPENDENCY_NOT_EXECUTABLE';
  readonly contentAuthority: 'STATIC_METADATA_ONLY';
  readonly roleMetadataAuthority: 'DISPLAY_ONLY_NOT_AUTHORIZATION';
  readonly roleInputAccepted: false;
  readonly routeCatalogOnly: true;
  readonly routeRegistered: false;
  readonly navigationEligible: false;
  readonly renderEnabled: false;
  readonly authenticationEstablished: false;
  readonly authorizationGranted: false;
  readonly backendReauthorizationRequired: true;
  readonly dataAccessEnabled: false;
  readonly runtimeDataLoaded: false;
  readonly mutationEnabled: false;
  readonly persistenceEnabled: false;
  readonly storageEnabled: false;
  readonly providerInvocationEnabled: false;
  readonly networkEnabled: false;
  readonly externalActionEnabled: false;
  readonly publicationAuthorized: false;
  readonly criticalIntentEmittable: false;
  readonly actionIntents: readonly [];
  readonly layout: {
    readonly visualThesis: 'CALM_CARDLESS_UTILITY_WORKSPACE';
    readonly sequence: typeof PUBLICATION_REVIEW_LAYOUT_SECTION_IDS;
    readonly sections: readonly PublicationReviewLayoutSection[];
    readonly marketingHero: false;
    readonly cardMosaic: false;
    readonly ornamentalMotion: false;
  };
  readonly orientation: {
    readonly screenId: PublicationReviewScreenId;
    readonly screenName: string;
    readonly catalogRoute: string;
    readonly allowedRoles: readonly PublicationReviewRole[];
    readonly roleMeaning: 'DISPLAY_ONLY_NOT_AUTHORIZATION';
    readonly statusCode: 'DISABLED_DEPENDENCY_NOT_EXECUTABLE';
    readonly statusLabel: 'Unavailable';
  };
  readonly blockers: readonly [
    {
      readonly code: 'ROUTE_UNREGISTERED';
      readonly label: 'Catalog route is not registered.';
    },
    {
      readonly code: 'AUTH_TRANSPORT_UNRESOLVED';
      readonly label: 'Authentication and step-up transport are unavailable.';
    },
    {
      readonly code: 'DEPENDENCY_RUNTIME_NOT_EXECUTABLE';
      readonly label: 'Approval, snapshot, projection, and publication runtimes are unavailable.';
    },
    {
      readonly code: 'SERVER_AUTHORIZATION_NOT_ESTABLISHED';
      readonly label: 'Server authorization has not been established.';
    },
  ];
  readonly crossBoundarySafeguards: readonly [
    {
      readonly id: 'OD-005';
      readonly resolved: false;
      readonly decisionInferred: false;
      readonly safeDefault: 'PUBLICATION_BLOCKED';
    },
    {
      readonly id: 'OD-007';
      readonly resolved: false;
      readonly decisionInferred: false;
      readonly safeDefault: 'STALE_VALUES_HIDDEN_NO_PUBLICATION_AUTHORITY';
    },
    {
      readonly id: 'OD-008';
      readonly resolved: false;
      readonly decisionInferred: false;
      readonly safeDefault: 'LEGAL_JUDGMENT_NOT_SUBSTITUTED_PUBLICATION_BLOCKED';
    },
    {
      readonly id: 'OD-010';
      readonly resolved: false;
      readonly decisionInferred: false;
      readonly safeDefault: 'DEVELOPMENT_FAKE_AUTH_ONLY_EXTERNAL_PUBLICATION_BLOCKED';
    },
  ];
  readonly capabilityStates: readonly PublicationReviewCapabilityState[];
  readonly reviewProjection: {
    readonly status: 'NOT_LOADED';
    readonly checklist: null;
    readonly findings: null;
    readonly gates: null;
    readonly decision: null;
    readonly recordedDecisionExecutionEnabled: false;
    readonly finalApprovalExecutionEnabled: false;
  };
  readonly diffProjection: {
    readonly status: 'NOT_LOADED';
    readonly fromVersion: null;
    readonly toVersion: null;
    readonly changes: readonly [];
    readonly computationEnabled: false;
  };
  readonly previewProjection: {
    readonly status: 'NOT_LOADED';
    readonly snapshotId: null;
    readonly snapshotSha256: null;
    readonly content: null;
    readonly rendererEnabled: false;
    readonly hashMatchVerified: false;
  };
  readonly criticalBoundary: {
    readonly finalApproval: 'BLOCKED_DEPENDENCY_NOT_EXECUTABLE';
    readonly publish: 'BLOCKED_DEPENDENCY_NOT_EXECUTABLE';
    readonly rollback: 'BLOCKED_DEPENDENCY_NOT_EXECUTABLE';
    readonly finalApprovalStepUpRequirement: 'CONFLICT_UNRESOLVED_DENY';
    readonly publishStepUpRequirement: 'REQUIRED_BUT_UNAVAILABLE';
    readonly rollbackStepUpRequirement: 'REQUIRED_BUT_UNAVAILABLE';
    readonly confirmDialogIntentEnabled: false;
    readonly stepUpDialogEffectEnabled: false;
    readonly reasonInputEnabled: false;
    readonly idempotencyKeyAllocationEnabled: false;
    readonly auditCorrelationEnabled: false;
  };
  readonly accessibility: {
    readonly requirementsOnly: true;
    readonly conformanceClaimed: false;
    readonly semanticOrder: readonly [
      'skip-link',
      'header',
      'main',
      'orientation',
      'blockers',
      'review',
      'diff',
      'preview',
      'status',
    ];
    readonly elements: readonly {
      readonly kind:
        | 'skip-link'
        | 'header'
        | 'main'
        | 'orientation'
        | 'blockers'
        | 'review'
        | 'diff'
        | 'preview'
        | 'status';
      readonly id: string;
      readonly role: 'link' | 'banner' | 'main' | 'region' | 'status';
    }[];
    readonly h1: {
      readonly id: 'publication-review-heading';
      readonly count: 1;
      readonly level: 1;
      readonly textSource: 'SCREEN_NAME';
    };
    readonly focusOrder: readonly [
      'publication-review-skip-link',
      'publication-review-main',
      'publication-review-blockers',
      'publication-review-review',
      'publication-review-diff',
      'publication-review-preview',
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
    readonly diffPresentation: {
      readonly addedLabelRequired: true;
      readonly removedLabelRequired: true;
      readonly changedLabelRequired: true;
      readonly colorOnly: false;
    };
    readonly dialogImplemented: false;
    readonly stepUpDialogImplemented: false;
    readonly motion: 'NONE';
    readonly reducedMotion: 'NOT_APPLICABLE_NO_MOTION';
  };
  readonly verification: {
    readonly formalTst022: 'NOT_EXECUTED';
    readonly formalTst024: 'NOT_EXECUTED';
    readonly browser: 'NOT_EXECUTED';
    readonly accessibilityAutomation: 'NOT_EXECUTED';
    readonly manualAccessibility: 'NOT_EXECUTED';
    readonly keyboard: 'NOT_EXECUTED';
    readonly screenReader: 'NOT_EXECUTED';
    readonly authentication: 'NOT_EXECUTED';
    readonly authorization: 'NOT_EXECUTED';
    readonly stepUp: 'NOT_EXECUTED';
    readonly api: 'NOT_EXECUTED';
    readonly database: 'NOT_EXECUTED';
    readonly publication: 'NOT_EXECUTED';
    readonly rollback: 'NOT_EXECUTED';
    readonly live: 'NOT_EXECUTED';
    readonly staging: 'NOT_EXECUTED';
    readonly release: 'NOT_EXECUTED';
    readonly production: 'NOT_EXECUTED';
  };
  readonly acceptanceAchieved: false;
  readonly storyComplete: false;
  readonly decision: 'NOT_READY';
  readonly productionEligible: false;
}

const dependencyStateSource = [
  {
    storyId: 'ST-0901',
    relationship: 'DIRECT',
    status: 'RECORDED_LOCAL_REVIEW_ONLY',
    runtimeConnected: false,
    authoritative: false,
    effectPermitted: false,
  },
  {
    storyId: 'ST-0902',
    relationship: 'SCREEN_PREREQUISITE',
    status: 'NONEXECUTABLE_REFERENCE_PLAN',
    runtimeConnected: false,
    authoritative: false,
    effectPermitted: false,
  },
  {
    storyId: 'ST-0903',
    relationship: 'SCREEN_PREREQUISITE',
    status: 'NONEXECUTABLE_REFERENCE_PLAN',
    runtimeConnected: false,
    authoritative: false,
    effectPermitted: false,
  },
  {
    storyId: 'ST-0904',
    relationship: 'SCREEN_PREREQUISITE',
    status: 'NONEXECUTABLE_REFERENCE_PLAN',
    runtimeConnected: false,
    authoritative: false,
    effectPermitted: false,
  },
  {
    storyId: 'ST-0905',
    relationship: 'DIRECT',
    status: 'NONEXECUTABLE_REFERENCE_PLAN',
    runtimeConnected: false,
    authoritative: false,
    effectPermitted: false,
  },
  {
    storyId: 'ST-1101',
    relationship: 'DIRECT',
    status: 'DISABLED_HEADLESS_FOUNDATION',
    runtimeConnected: false,
    authoritative: false,
    effectPermitted: false,
  },
] as const;

const capabilityStateSource = [
  {
    screenId: 'REV-001',
    availability: 'STATIC_CATALOG_ONLY',
    reasonCode: 'ROUTE_AND_DATA_SOURCE_UNAVAILABLE',
    payload: null,
    effectPermitted: false,
    intentEmittable: false,
  },
  {
    screenId: 'REV-002',
    availability: 'RECORDED_DEPENDENCY_REFERENCE_ONLY',
    reasonCode: 'RECORDED_REVIEW_IS_NOT_UI_OR_AUTHORITY',
    payload: null,
    effectPermitted: false,
    intentEmittable: false,
  },
  {
    screenId: 'REV-003',
    availability: 'BLOCKED_DEPENDENCY_NOT_EXECUTABLE',
    reasonCode: 'FINAL_APPROVAL_AUTHORITY_UNAVAILABLE',
    payload: null,
    effectPermitted: false,
    intentEmittable: false,
  },
  {
    screenId: 'PUBA-001',
    availability: 'STATIC_CATALOG_ONLY',
    reasonCode: 'PUBLICATION_CANDIDATE_SOURCE_UNAVAILABLE',
    payload: null,
    effectPermitted: false,
    intentEmittable: false,
  },
  {
    screenId: 'PUBA-002',
    availability: 'BLOCKED_DEPENDENCY_NOT_EXECUTABLE',
    reasonCode: 'AUTHORITATIVE_SNAPSHOT_UNAVAILABLE',
    payload: null,
    effectPermitted: false,
    intentEmittable: false,
  },
  {
    screenId: 'PUBA-003',
    availability: 'BLOCKED_DEPENDENCY_NOT_EXECUTABLE',
    reasonCode: 'PUBLISH_COMMAND_AUTHORITY_UNAVAILABLE',
    payload: null,
    effectPermitted: false,
    intentEmittable: false,
  },
  {
    screenId: 'PUBA-004',
    availability: 'BLOCKED_DEPENDENCY_NOT_EXECUTABLE',
    reasonCode: 'ROLLBACK_COMMAND_AUTHORITY_UNAVAILABLE',
    payload: null,
    effectPermitted: false,
    intentEmittable: false,
  },
] as const;

const semanticElementsSource = [
  { kind: 'skip-link', id: PUBLICATION_REVIEW_SEMANTIC_IDS.skipLink, role: 'link' },
  { kind: 'header', id: PUBLICATION_REVIEW_SEMANTIC_IDS.header, role: 'banner' },
  { kind: 'main', id: PUBLICATION_REVIEW_SEMANTIC_IDS.main, role: 'main' },
  {
    kind: 'orientation',
    id: PUBLICATION_REVIEW_SEMANTIC_IDS.orientation,
    role: 'region',
  },
  { kind: 'blockers', id: PUBLICATION_REVIEW_SEMANTIC_IDS.blockers, role: 'region' },
  { kind: 'review', id: PUBLICATION_REVIEW_SEMANTIC_IDS.review, role: 'region' },
  { kind: 'diff', id: PUBLICATION_REVIEW_SEMANTIC_IDS.diff, role: 'region' },
  { kind: 'preview', id: PUBLICATION_REVIEW_SEMANTIC_IDS.preview, role: 'region' },
  { kind: 'status', id: PUBLICATION_REVIEW_SEMANTIC_IDS.status, role: 'status' },
] as const;

function reject(code: PublicationReviewErrorCode): never {
  throw new PublicationReviewError(code);
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

function isJsonObject(value: JsonValue | undefined): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function cloneStrict(value: unknown, code: PublicationReviewErrorCode): JsonValue {
  if (!isStrictPlainTree(value)) {
    return reject(code);
  }
  try {
    return createJsonValue(value);
  } catch {
    return reject(code);
  }
}

function validatedScreenId(input: PublicationReviewWorkspaceInput): PublicationReviewScreenId {
  const value = cloneStrict(input, 'PUBLICATION_REVIEW_INPUT_INVALID');
  if (!isJsonObject(value)) {
    return reject('PUBLICATION_REVIEW_INPUT_INVALID');
  }
  const keys = Object.keys(value);
  if (keys.length !== 1 || keys[0] !== 'screenId') {
    return reject('PUBLICATION_REVIEW_INPUT_INVALID');
  }
  const screenId = value['screenId'];
  if (typeof screenId !== 'string') {
    return reject('PUBLICATION_REVIEW_INPUT_INVALID');
  }
  if (!(PUBLICATION_REVIEW_SCREEN_IDS as readonly string[]).includes(screenId)) {
    return reject('PUBLICATION_REVIEW_SCREEN_UNKNOWN');
  }
  return screenId as PublicationReviewScreenId;
}

function buildModel(screenId: PublicationReviewScreenId): PublicationReviewWorkspaceModel {
  const screen = PUBLICATION_REVIEW_SCREENS.find((item) => item.id === screenId);
  if (screen === undefined) {
    return reject('PUBLICATION_REVIEW_SCREEN_UNKNOWN');
  }
  return createJsonValue({
    classification: 'SOURCE_DERIVED_DISABLED_HEADLESS_PUBLICATION_REVIEW_WORKSPACE',
    storyId: 'ST-0906',
    objective: 'review/approval/preview/publish/rollback画面',
    screen,
    catalogScreens: PUBLICATION_REVIEW_SCREENS,
    canonicalScreenOrder: PUBLICATION_REVIEW_SCREEN_IDS,
    componentRequirements: PUBLICATION_REVIEW_COMPONENTS,
    sourceRefs: PUBLICATION_REVIEW_SOURCE_REFS,
    dependencyStates: dependencyStateSource,
    availability: 'DISABLED_DEPENDENCY_NOT_EXECUTABLE',
    contentAuthority: 'STATIC_METADATA_ONLY',
    roleMetadataAuthority: 'DISPLAY_ONLY_NOT_AUTHORIZATION',
    roleInputAccepted: false,
    routeCatalogOnly: true,
    routeRegistered: false,
    navigationEligible: false,
    renderEnabled: false,
    authenticationEstablished: false,
    authorizationGranted: false,
    backendReauthorizationRequired: true,
    dataAccessEnabled: false,
    runtimeDataLoaded: false,
    mutationEnabled: false,
    persistenceEnabled: false,
    storageEnabled: false,
    providerInvocationEnabled: false,
    networkEnabled: false,
    externalActionEnabled: false,
    publicationAuthorized: false,
    criticalIntentEmittable: false,
    actionIntents: [],
    layout: {
      visualThesis: 'CALM_CARDLESS_UTILITY_WORKSPACE',
      sequence: PUBLICATION_REVIEW_LAYOUT_SECTION_IDS,
      sections: PUBLICATION_REVIEW_LAYOUT_SECTIONS,
      marketingHero: false,
      cardMosaic: false,
      ornamentalMotion: false,
    },
    orientation: {
      screenId: screen.id,
      screenName: screen.name,
      catalogRoute: screen.route,
      allowedRoles: screen.roles,
      roleMeaning: 'DISPLAY_ONLY_NOT_AUTHORIZATION',
      statusCode: 'DISABLED_DEPENDENCY_NOT_EXECUTABLE',
      statusLabel: 'Unavailable',
    },
    blockers: [
      { code: 'ROUTE_UNREGISTERED', label: 'Catalog route is not registered.' },
      {
        code: 'AUTH_TRANSPORT_UNRESOLVED',
        label: 'Authentication and step-up transport are unavailable.',
      },
      {
        code: 'DEPENDENCY_RUNTIME_NOT_EXECUTABLE',
        label: 'Approval, snapshot, projection, and publication runtimes are unavailable.',
      },
      {
        code: 'SERVER_AUTHORIZATION_NOT_ESTABLISHED',
        label: 'Server authorization has not been established.',
      },
    ],
    crossBoundarySafeguards: [
      {
        id: 'OD-005',
        resolved: false,
        decisionInferred: false,
        safeDefault: 'PUBLICATION_BLOCKED',
      },
      {
        id: 'OD-007',
        resolved: false,
        decisionInferred: false,
        safeDefault: 'STALE_VALUES_HIDDEN_NO_PUBLICATION_AUTHORITY',
      },
      {
        id: 'OD-008',
        resolved: false,
        decisionInferred: false,
        safeDefault: 'LEGAL_JUDGMENT_NOT_SUBSTITUTED_PUBLICATION_BLOCKED',
      },
      {
        id: 'OD-010',
        resolved: false,
        decisionInferred: false,
        safeDefault: 'DEVELOPMENT_FAKE_AUTH_ONLY_EXTERNAL_PUBLICATION_BLOCKED',
      },
    ],
    capabilityStates: capabilityStateSource,
    reviewProjection: {
      status: 'NOT_LOADED',
      checklist: null,
      findings: null,
      gates: null,
      decision: null,
      recordedDecisionExecutionEnabled: false,
      finalApprovalExecutionEnabled: false,
    },
    diffProjection: {
      status: 'NOT_LOADED',
      fromVersion: null,
      toVersion: null,
      changes: [],
      computationEnabled: false,
    },
    previewProjection: {
      status: 'NOT_LOADED',
      snapshotId: null,
      snapshotSha256: null,
      content: null,
      rendererEnabled: false,
      hashMatchVerified: false,
    },
    criticalBoundary: {
      finalApproval: 'BLOCKED_DEPENDENCY_NOT_EXECUTABLE',
      publish: 'BLOCKED_DEPENDENCY_NOT_EXECUTABLE',
      rollback: 'BLOCKED_DEPENDENCY_NOT_EXECUTABLE',
      finalApprovalStepUpRequirement: 'CONFLICT_UNRESOLVED_DENY',
      publishStepUpRequirement: 'REQUIRED_BUT_UNAVAILABLE',
      rollbackStepUpRequirement: 'REQUIRED_BUT_UNAVAILABLE',
      confirmDialogIntentEnabled: false,
      stepUpDialogEffectEnabled: false,
      reasonInputEnabled: false,
      idempotencyKeyAllocationEnabled: false,
      auditCorrelationEnabled: false,
    },
    accessibility: {
      requirementsOnly: true,
      conformanceClaimed: false,
      semanticOrder: [
        'skip-link',
        'header',
        'main',
        'orientation',
        'blockers',
        'review',
        'diff',
        'preview',
        'status',
      ],
      elements: semanticElementsSource,
      h1: {
        id: PUBLICATION_REVIEW_SEMANTIC_IDS.heading,
        count: 1,
        level: 1,
        textSource: 'SCREEN_NAME',
      },
      focusOrder: [
        PUBLICATION_REVIEW_SEMANTIC_IDS.skipLink,
        PUBLICATION_REVIEW_SEMANTIC_IDS.main,
        PUBLICATION_REVIEW_SEMANTIC_IDS.blockers,
        PUBLICATION_REVIEW_SEMANTIC_IDS.review,
        PUBLICATION_REVIEW_SEMANTIC_IDS.diff,
        PUBLICATION_REVIEW_SEMANTIC_IDS.preview,
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
      diffPresentation: {
        addedLabelRequired: true,
        removedLabelRequired: true,
        changedLabelRequired: true,
        colorOnly: false,
      },
      dialogImplemented: false,
      stepUpDialogImplemented: false,
      motion: 'NONE',
      reducedMotion: 'NOT_APPLICABLE_NO_MOTION',
    },
    verification: {
      formalTst022: 'NOT_EXECUTED',
      formalTst024: 'NOT_EXECUTED',
      browser: 'NOT_EXECUTED',
      accessibilityAutomation: 'NOT_EXECUTED',
      manualAccessibility: 'NOT_EXECUTED',
      keyboard: 'NOT_EXECUTED',
      screenReader: 'NOT_EXECUTED',
      authentication: 'NOT_EXECUTED',
      authorization: 'NOT_EXECUTED',
      stepUp: 'NOT_EXECUTED',
      api: 'NOT_EXECUTED',
      database: 'NOT_EXECUTED',
      publication: 'NOT_EXECUTED',
      rollback: 'NOT_EXECUTED',
      live: 'NOT_EXECUTED',
      staging: 'NOT_EXECUTED',
      release: 'NOT_EXECUTED',
      production: 'NOT_EXECUTED',
    },
    acceptanceAchieved: false,
    storyComplete: false,
    decision: 'NOT_READY',
    productionEligible: false,
  }) as unknown as PublicationReviewWorkspaceModel;
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
  'callback',
  'callbacks',
  'handler',
  'handlers',
  'endpoint',
  'endpoints',
  'fetch',
  'httpclient',
  'networkclient',
  'rawprompt',
  'prompttext',
  'rawsource',
  'sourcebody',
  'articlebody',
  'secret',
  'token',
  'credential',
]);

function normalizedKey(key: string): string {
  return key.replace(/[\s_-]+/g, '').toLowerCase();
}

function hasProhibitedSurface(value: JsonValue): boolean {
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
  expected: PublicationReviewWorkspaceModel,
): PublicationReviewErrorCode {
  if (hasProhibitedSurface(value)) {
    return 'PUBLICATION_REVIEW_PROHIBITED_SURFACE';
  }
  const screens = recordArray(value['catalogScreens']);
  const components = recordArray(value['componentRequirements']);
  if (
    hasDuplicate(valuesFor(screens, 'id')) ||
    hasDuplicate(valuesFor(components, 'id')) ||
    hasDuplicate(candidateSemanticIds(value['accessibility']))
  ) {
    return 'PUBLICATION_REVIEW_DUPLICATE_ID';
  }
  if (hasDuplicate(valuesFor(screens, 'route'))) {
    return 'PUBLICATION_REVIEW_DUPLICATE_ROUTE';
  }
  if (
    !jsonEqual(value['screen'], expected.screen) ||
    !jsonEqual(value['catalogScreens'], expected.catalogScreens) ||
    !jsonEqual(value['canonicalScreenOrder'], expected.canonicalScreenOrder) ||
    !jsonEqual(value['componentRequirements'], expected.componentRequirements) ||
    !jsonEqual(value['sourceRefs'], expected.sourceRefs) ||
    !jsonEqual(value['dependencyStates'], expected.dependencyStates)
  ) {
    return 'PUBLICATION_REVIEW_METADATA_INVALID';
  }
  if (!jsonEqual(value['layout'], expected.layout)) {
    return 'PUBLICATION_REVIEW_LAYOUT_INVALID';
  }
  if (
    !jsonEqual(value['orientation'], expected.orientation) ||
    !jsonEqual(value['blockers'], expected.blockers) ||
    !jsonEqual(value['crossBoundarySafeguards'], expected.crossBoundarySafeguards) ||
    !jsonEqual(value['capabilityStates'], expected.capabilityStates) ||
    !jsonEqual(value['reviewProjection'], expected.reviewProjection) ||
    !jsonEqual(value['diffProjection'], expected.diffProjection) ||
    !jsonEqual(value['previewProjection'], expected.previewProjection) ||
    !jsonEqual(value['criticalBoundary'], expected.criticalBoundary)
  ) {
    return 'PUBLICATION_REVIEW_STATE_INVALID';
  }
  if (!jsonEqual(value['accessibility'], expected.accessibility)) {
    return 'PUBLICATION_REVIEW_ACCESSIBILITY_INVALID';
  }
  const authorityKeys = [
    'availability',
    'contentAuthority',
    'roleMetadataAuthority',
    'roleInputAccepted',
    'routeCatalogOnly',
    'routeRegistered',
    'navigationEligible',
    'renderEnabled',
    'authenticationEstablished',
    'authorizationGranted',
    'backendReauthorizationRequired',
    'dataAccessEnabled',
    'runtimeDataLoaded',
    'mutationEnabled',
    'persistenceEnabled',
    'storageEnabled',
    'providerInvocationEnabled',
    'networkEnabled',
    'externalActionEnabled',
    'publicationAuthorized',
    'criticalIntentEmittable',
    'actionIntents',
    'verification',
    'acceptanceAchieved',
    'storyComplete',
    'decision',
    'productionEligible',
  ] as const;
  if (authorityKeys.some((key) => !jsonEqual(value[key], expected[key]))) {
    return 'PUBLICATION_REVIEW_AUTHORITY_INVALID';
  }
  return 'PUBLICATION_REVIEW_CANDIDATE_INVALID';
}

export function validatePublicationReviewWorkspaceModel(
  value: unknown,
): PublicationReviewWorkspaceModel {
  const clone = cloneStrict(value, 'PUBLICATION_REVIEW_CANDIDATE_INVALID');
  if (!isJsonObject(clone)) {
    return reject('PUBLICATION_REVIEW_CANDIDATE_INVALID');
  }
  const screen = clone['screen'];
  if (!isJsonObject(screen)) {
    return reject('PUBLICATION_REVIEW_CANDIDATE_INVALID');
  }
  const screenId = screen['id'];
  if (
    typeof screenId !== 'string' ||
    !(PUBLICATION_REVIEW_SCREEN_IDS as readonly string[]).includes(screenId)
  ) {
    return reject('PUBLICATION_REVIEW_SCREEN_UNKNOWN');
  }
  const expected = buildModel(screenId as PublicationReviewScreenId);
  if (!jsonEqual(clone, expected)) {
    return reject(classifyCandidateFailure(clone, expected));
  }
  return clone as unknown as PublicationReviewWorkspaceModel;
}

export function createPublicationReviewWorkspaceModel(
  input: PublicationReviewWorkspaceInput,
): PublicationReviewWorkspaceModel {
  return validatePublicationReviewWorkspaceModel(buildModel(validatedScreenId(input)));
}
