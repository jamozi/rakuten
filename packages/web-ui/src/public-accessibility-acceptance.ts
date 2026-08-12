import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const PUBLIC_ACCESSIBILITY_ACCEPTANCE_CLASSIFICATION =
  'UNREGISTERED_DISABLED_HEADLESS_ST1007_ACCESSIBILITY_EVIDENCE_REQUIREMENTS_CANDIDATE' as const;

const checklistSource = [
  ['A11Y-001', '全Pageに一意で説明的なtitleとH1', 'WCAG 2.4.2/2.4.6', 'automated+manual'],
  ['A11Y-002', 'Skip linkとlandmarkを提供', 'WCAG 2.4.1/1.3.1', 'manual'],
  ['A11Y-003', '全操作をKeyboardのみで実行可能', 'WCAG 2.1.1', 'manual'],
  ['A11Y-004', 'Focus順が視覚順と一致', 'WCAG 2.4.3', 'manual'],
  ['A11Y-005', 'Focus indicatorを隠さない', 'WCAG 2.4.7/2.4.11', 'automated+manual'],
  ['A11Y-006', 'DialogはFocus trap、Escape、return focusを実装', 'ARIA APG Dialog', 'manual'],
  ['A11Y-007', 'Statusを色だけで表現しない', 'WCAG 1.4.1', 'automated+manual'],
  ['A11Y-008', '通常文字Contrast 4.5:1以上を目標', 'WCAG 1.4.3', 'automated'],
  ['A11Y-009', 'UI Component/Focus Contrast 3:1以上を目標', 'WCAG 1.4.11', 'automated'],
  ['A11Y-010', '200% Zoomで情報・操作を失わない', 'WCAG 1.4.4', 'manual'],
  [
    'A11Y-011',
    '320 CSS px幅で2次元Scrollを避ける（比較表等の例外は説明）',
    'WCAG 1.4.10',
    'manual',
  ],
  ['A11Y-012', 'Form label、instruction、requiredを明示', 'WCAG 1.3.1/3.3.2', 'automated+manual'],
  ['A11Y-013', 'Validation errorをFieldとSummaryへ関連付け', 'WCAG 3.3.1/3.3.3', 'manual'],
  ['A11Y-014', '破壊的/財務Actionは確認・取消または訂正機会', 'WCAG 3.3.4', 'manual'],
  ['A11Y-015', 'Tableにcaption/headers/scopeを使用', 'WCAG 1.3.1', 'automated+manual'],
  ['A11Y-016', 'Responsive比較表でも商品名と軸の関係を保持', 'WCAG 1.3.1', 'screen-reader'],
  ['A11Y-017', 'Image altは目的を記述し装飾画像は空alt', 'WCAG 1.1.1', 'manual'],
  ['A11Y-018', 'Link textだけで目的が分かる', 'WCAG 2.4.4', 'manual'],
  ['A11Y-019', '楽天へ移動するCTAを事前明示', 'RAOS policy', 'manual'],
  ['A11Y-020', 'Motionはprefers-reduced-motionを尊重', 'WCAG 2.3.3', 'manual'],
  ['A11Y-021', '自動更新はFocusを奪わず必要時のみlive region', 'WCAG 4.1.3', 'manual'],
  ['A11Y-022', 'Timeout前に警告し可能なら延長', 'WCAG 2.2.1', 'manual'],
  ['A11Y-023', 'DragだけでなくButton/Keyboard代替を提供', 'WCAG 2.5.7', 'manual'],
  ['A11Y-024', 'Target sizeを確保し密集操作を避ける', 'WCAG 2.5.8', 'manual'],
  ['A11Y-025', '認証で記憶・Puzzleだけを要求しない', 'WCAG 3.3.8', 'manual'],
  ['A11Y-026', 'Screen readerでLoading/Success/Failureが分かる', 'WCAG 4.1.3', 'screen-reader'],
  [
    'A11Y-027',
    'Markdown/AST Previewと公開RendererのHeading構造一致',
    'RAOS policy',
    'automated+manual',
  ],
  ['A11Y-028', 'ChartはTableまたはText summaryを併設', 'WCAG 1.1.1/1.3.1', 'manual'],
  ['A11Y-029', 'PDF等をMVPの唯一情報経路にしない', 'RAOS policy', 'manual'],
  ['A11Y-030', '主要FlowをNVDAまたは同等Screen readerで確認', 'acceptance', 'manual'],
] as const;

const screenSource = [
  ['PUB-001', 'ホーム', '/', 'カテゴリと主要ガイドへの入口'],
  ['PUB-002', 'カテゴリハブ', '/categories/{slug}', 'カテゴリの選び方・記事Journeyを提示'],
  ['PUB-003', '記事詳細', '/articles/{slug}', '承認済みPublication Snapshotを表示'],
  ['PUB-004', '編集方針', '/editorial-policy', '比較・推薦・根拠・AI利用方針を説明'],
  ['PUB-005', '広告・Affiliate開示', '/affiliate-disclosure', '広告関係と送客先を説明'],
  ['PUB-006', 'Privacy Policy', '/privacy', '取得データ、目的、保持、問い合わせを説明'],
  ['PUB-007', '運営者・問い合わせ', '/about', '運営主体と連絡経路を表示'],
  ['PUB-008', 'Not Found', '/404', '存在しないURLを安全に案内'],
  ['PUB-009', '障害・Maintenance', '/status', '縮退または障害状態を表示'],
  [
    'PUB-010',
    '取り下げ記事',
    '/articles/{slug}/withdrawn',
    '旧URLを維持し取り下げ理由と代替導線を表示',
  ],
] as const;

const componentSource = [
  ['UI-C002', 'PublicHeader', 'public', 'Brand、Breadcrumb入口、Primary navigation'],
  ['UI-C003', 'PublicFooter', 'public', '運営者、Policy、Disclosure'],
  ['UI-C004', 'Breadcrumbs', 'shared', '階層と現在位置'],
  ['UI-C031', 'DisclosureBanner', 'public', '広告・Affiliate開示'],
  ['UI-C032', 'ProductCard', 'public', '商品名、Verified Fact、CTA、更新時刻'],
  ['UI-C033', 'ComparisonTable', 'public', 'Responsiveな比較表'],
  ['UI-C034', 'AffiliateCTA', 'public', '楽天遷移を明示しSponsored属性'],
  ['UI-C036', 'UnknownValue', 'shared', '欠損を推測せず表示'],
] as const;

export type PublicAccessibilityVerificationMethod =
  'automated' | 'automated+manual' | 'manual' | 'screen-reader';

export const PUBLIC_ACCESSIBILITY_CHECKLIST = createJsonValue(
  checklistSource.map(([id, requirement, reference, verification]) => ({
    id,
    requirement,
    reference,
    verification,
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    testStatus: 'NOT_EXECUTED',
  })),
) as unknown as readonly {
  readonly id: string;
  readonly requirement: string;
  readonly reference: string;
  readonly verification: PublicAccessibilityVerificationMethod;
  readonly designStatus: 'APPROVED_FOR_IMPLEMENTATION';
  readonly implementationStatus: 'NOT_STARTED';
  readonly testStatus: 'NOT_EXECUTED';
}[];

export const PUBLIC_ACCESSIBILITY_SCREENS = createJsonValue(
  screenSource.map(([id, name, route, purpose]) => ({
    id,
    name,
    route,
    area: 'public',
    roles: [],
    purpose,
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  })),
) as unknown as readonly JsonObject[];

export const PUBLIC_ACCESSIBILITY_COMPONENTS = createJsonValue(
  componentSource.map(([id, name, area, purpose]) => ({
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
) as unknown as readonly JsonObject[];

const suiteSource = [
  {
    id: 'TST-023',
    name: 'Accessibility automated',
    layer: 'ui',
    purpose: 'axe等による機械検査',
    candidateTools: ['axe-core', 'Playwright'],
    releaseBlocking: true,
    environments: ['CI'],
    owner: 'Engineering',
  },
  {
    id: 'TST-024',
    name: 'Accessibility manual',
    layer: 'ui',
    purpose: 'Keyboard、Zoom、Screen reader、cognitive checks',
    candidateTools: ['NVDA/VoiceOver', 'manual checklist'],
    releaseBlocking: true,
    environments: ['staging'],
    owner: 'QA/Accessibility',
  },
] as const;

export const PUBLIC_ACCESSIBILITY_EVIDENCE_SUITES = createJsonValue(
  suiteSource.map((suite) => ({
    ...suite,
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    executionStatus: 'NOT_EXECUTED',
  })),
) as unknown as readonly JsonObject[];

export const PUBLIC_ACCESSIBILITY_ACCEPTANCE_ERROR_CODES = Object.freeze([
  'PUBLIC_ACCESSIBILITY_INPUT_INVALID',
  'PUBLIC_ACCESSIBILITY_STORY_INVALID',
  'PUBLIC_ACCESSIBILITY_COORDINATE_INVALID',
  'PUBLIC_ACCESSIBILITY_HASH_INVALID',
  'PUBLIC_ACCESSIBILITY_HASH_MISMATCH',
  'PUBLIC_ACCESSIBILITY_CONTENT_PROHIBITED',
  'PUBLIC_ACCESSIBILITY_INTERNAL_FIELD_PROHIBITED',
  'PUBLIC_ACCESSIBILITY_EVIDENCE_PROHIBITED',
  'PUBLIC_ACCESSIBILITY_EFFECT_PROHIBITED',
  'PUBLIC_ACCESSIBILITY_CATALOG_INVALID',
  'PUBLIC_ACCESSIBILITY_CHECKLIST_INVALID',
  'PUBLIC_ACCESSIBILITY_EVIDENCE_STATE_INVALID',
  'PUBLIC_ACCESSIBILITY_AUTHORITY_INVALID',
  'PUBLIC_ACCESSIBILITY_CANDIDATE_INVALID',
] as const);

export type PublicAccessibilityAcceptanceErrorCode =
  (typeof PUBLIC_ACCESSIBILITY_ACCEPTANCE_ERROR_CODES)[number];

export class PublicAccessibilityAcceptanceError extends TypeError {
  readonly code: PublicAccessibilityAcceptanceErrorCode;

  constructor(code: PublicAccessibilityAcceptanceErrorCode) {
    super(code);
    this.name = 'PublicAccessibilityAcceptanceError';
    this.code = code;
    Object.freeze(this);
  }
}

export interface PublicAccessibilitySyntheticCoordinateInput {
  readonly kind: 'SYNTHETIC_ST1007_ACCESSIBILITY_REQUIREMENTS_FIXTURE';
  readonly expectedSha256: string;
  readonly observedSha256: string;
}

export interface PublicAccessibilityAcceptanceInput {
  readonly storyId: 'ST-1007';
  readonly coordinate: PublicAccessibilitySyntheticCoordinateInput;
}

export interface PublicAccessibilityBoundaryResult {
  readonly value: false;
  readonly status: 'NOT_EXECUTED';
  readonly reason: string;
}

export interface PublicAccessibilityAssessment {
  readonly checklistItem: (typeof PUBLIC_ACCESSIBILITY_CHECKLIST)[number];
  readonly requiredSuiteIds: readonly ('TST-023' | 'TST-024')[];
  readonly applicability: 'NOT_EVALUATED';
  readonly executionStatus: 'NOT_EXECUTED';
  readonly verificationResult: 'NOT_VERIFIED';
  readonly evidenceRefs: readonly [];
  readonly environment: null;
  readonly evaluator: null;
  readonly executedAt: null;
}

export interface PublicAccessibilityAcceptanceCandidate {
  readonly classification: typeof PUBLIC_ACCESSIBILITY_ACCEPTANCE_CLASSIFICATION;
  readonly story: {
    readonly id: 'ST-1007';
    readonly objective: 'manual/automated改善';
    readonly deliverable: 'a11y evidence';
    readonly acceptanceCriterion: 'P0 checklist pass';
    readonly dependencies: readonly ['ST-1003', 'ST-1004', 'ST-1005'];
    readonly requiredSuites: readonly ['TST-023', 'TST-024'];
    readonly designStatus: 'APPROVED_FOR_IMPLEMENTATION';
    readonly implementationStatus: 'NOT_STARTED';
    readonly verificationStatus: 'NOT_EXECUTED';
  };
  readonly coordinate: PublicAccessibilitySyntheticCoordinateInput;
  readonly hashBinding: {
    readonly profile: 'OPAQUE_CALLER_BOUND_EQUALITY_ONLY';
    readonly expectedSha256: string;
    readonly observedSha256: string;
    readonly equal: true;
    readonly recomputed: false;
    readonly canonicalized: false;
    readonly runtimeVerified: false;
    readonly formalEvidence: false;
  };
  readonly catalog: {
    readonly screens: typeof PUBLIC_ACCESSIBILITY_SCREENS;
    readonly components: typeof PUBLIC_ACCESSIBILITY_COMPONENTS;
    readonly directDependencyComponentIds: readonly [
      'UI-C031',
      'UI-C032',
      'UI-C033',
      'UI-C034',
      'UI-C036',
    ];
    readonly applicabilityMapping: 'NOT_EVALUATED';
  };
  readonly dependencyReadiness: readonly JsonObject[];
  readonly checklistAssessments: readonly PublicAccessibilityAssessment[];
  readonly evidenceSuites: typeof PUBLIC_ACCESSIBILITY_EVIDENCE_SUITES;
  readonly evidenceState: {
    readonly acceptsClaimedEvidence: false;
    readonly browserExecuted: false;
    readonly domAvailable: false;
    readonly automatedAuditExecuted: false;
    readonly keyboardExecuted: false;
    readonly zoomExecuted: false;
    readonly responsive320Executed: false;
    readonly screenReaderExecuted: false;
    readonly cognitiveReviewExecuted: false;
    readonly ciExecuted: false;
    readonly stagingExecuted: false;
    readonly wcagConformanceClaim: false;
    readonly evidenceRefs: readonly [];
  };
  readonly aggregate: {
    readonly p0ChecklistPass: false;
    readonly allItemsVerified: false;
    readonly conditionalLocalEligibility: false;
    readonly reasons: readonly string[];
  };
  readonly authorization: {
    readonly approval: false;
    readonly publication: false;
    readonly release: false;
    readonly production: false;
    readonly formalEvidence: false;
    readonly accessibilityConformance: false;
  };
  readonly boundaries: Readonly<Record<string, PublicAccessibilityBoundaryResult>>;
  readonly events: readonly [];
  readonly actions: readonly [];
  readonly effects: readonly [];
}

const boundaryReasons = {
  routeRegistration: 'PUBLIC_ROUTES_NOT_REGISTERED',
  renderer: 'ST_1002_RUNTIME_RENDERER_ABSENT',
  dom: 'DOM_NOT_IMPLEMENTED',
  browser: 'BROWSER_NOT_EXECUTED',
  automatedAudit: 'AXE_PLAYWRIGHT_NOT_EXECUTED',
  keyboard: 'KEYBOARD_ACCEPTANCE_NOT_EXECUTED',
  zoom: 'ZOOM_ACCEPTANCE_NOT_EXECUTED',
  responsive320: 'RESPONSIVE_320_CSS_PX_NOT_EXECUTED',
  screenReader: 'SCREEN_READER_ACCEPTANCE_NOT_EXECUTED',
  cognitiveReview: 'COGNITIVE_REVIEW_NOT_EXECUTED',
  formalTst023: 'FORMAL_TST_023_NOT_EXECUTED',
  formalTst024: 'FORMAL_TST_024_NOT_EXECUTED',
  ci: 'CI_ACCESSIBILITY_NOT_EXECUTED',
  staging: 'STAGING_ACCESSIBILITY_NOT_EXECUTED',
  live: 'LIVE_NOT_AUTHORIZED',
  publication: 'PUBLICATION_NOT_AUTHORIZED',
  release: 'RELEASE_NOT_AUTHORIZED',
  production: 'PRODUCTION_NOT_AUTHORIZED',
  localEligibility: 'ACCESSIBILITY_RUNTIME_AND_EVIDENCE_GATES_UNSATISFIED',
} as const;

const INPUT_KEYS = ['coordinate', 'storyId'] as const;
const COORDINATE_KEYS = ['expectedSha256', 'kind', 'observedSha256'] as const;
const SHA256 = /^[0-9a-f]{64}$/;
const ACTIVE_MARKUP = /<\s*(?:script|iframe)\b|\bon[a-z]+\s*=/i;
const CONTENT_KEY_FRAGMENTS = ['articlebody', 'copy', 'html', 'rawprompt', 'text'];
const INTERNAL_KEY_FRAGMENTS = [
  'evidencebody',
  'finance',
  'internal',
  'sourcepacket',
  'aiartifact',
];
const EVIDENCE_KEY_FRAGMENTS = [
  'axe',
  'browser',
  'dom',
  'evidenceref',
  'keyboard',
  'manualaudit',
  'nvda',
  'playwright',
  'screenreader',
  'voiceover',
  'wcagpass',
  'zoom',
];
const EFFECT_KEY_FRAGMENTS = [
  'callback',
  'emit',
  'fetch',
  'handler',
  'network',
  'provider',
  'track',
];

function reject(code: PublicAccessibilityAcceptanceErrorCode): never {
  throw new PublicAccessibilityAcceptanceError(code);
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
    const array = Array.isArray(value);
    if (Object.getPrototypeOf(value) !== (array ? Array.prototype : Object.prototype)) return false;
    for (const key of Reflect.ownKeys(value)) {
      if (typeof key !== 'string' || key === 'length') {
        if (key === 'length') continue;
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

function scanProhibitedSurface(value: JsonValue): PublicAccessibilityAcceptanceErrorCode | null {
  if (typeof value === 'string') {
    return ACTIVE_MARKUP.test(value) ? 'PUBLIC_ACCESSIBILITY_CONTENT_PROHIBITED' : null;
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
    if (CONTENT_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))) {
      return 'PUBLIC_ACCESSIBILITY_CONTENT_PROHIBITED';
    }
    if (INTERNAL_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))) {
      return 'PUBLIC_ACCESSIBILITY_INTERNAL_FIELD_PROHIBITED';
    }
    if (EVIDENCE_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))) {
      return 'PUBLIC_ACCESSIBILITY_EVIDENCE_PROHIBITED';
    }
    if (
      normalized.startsWith('on') ||
      EFFECT_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))
    ) {
      return 'PUBLIC_ACCESSIBILITY_EFFECT_PROHIBITED';
    }
    if (
      normalized.includes('approval') ||
      normalized.includes('eligible') ||
      normalized.includes('passed') ||
      normalized.includes('verified')
    ) {
      return 'PUBLIC_ACCESSIBILITY_AUTHORITY_INVALID';
    }
    const finding = scanProhibitedSurface(item);
    if (finding !== null) return finding;
  }
  return null;
}

function clonePlainObject(value: unknown, scanSurface = true): JsonObject {
  if (!isStrictPlainTree(value)) return reject('PUBLIC_ACCESSIBILITY_INPUT_INVALID');
  let clone: JsonValue;
  try {
    clone = createJsonValue(value);
  } catch {
    return reject('PUBLIC_ACCESSIBILITY_INPUT_INVALID');
  }
  if (!isJsonObject(clone)) return reject('PUBLIC_ACCESSIBILITY_INPUT_INVALID');
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

function requireCoordinate(
  value: JsonValue | undefined,
): PublicAccessibilitySyntheticCoordinateInput {
  if (!isJsonObject(value) || !hasExactKeys(value, COORDINATE_KEYS)) {
    return reject('PUBLIC_ACCESSIBILITY_COORDINATE_INVALID');
  }
  const kind = value['kind'];
  const expectedSha256 = value['expectedSha256'];
  const observedSha256 = value['observedSha256'];
  if (kind !== 'SYNTHETIC_ST1007_ACCESSIBILITY_REQUIREMENTS_FIXTURE') {
    return reject('PUBLIC_ACCESSIBILITY_COORDINATE_INVALID');
  }
  if (
    typeof expectedSha256 !== 'string' ||
    typeof observedSha256 !== 'string' ||
    !SHA256.test(expectedSha256) ||
    !SHA256.test(observedSha256)
  ) {
    return reject('PUBLIC_ACCESSIBILITY_HASH_INVALID');
  }
  if (expectedSha256 !== observedSha256) return reject('PUBLIC_ACCESSIBILITY_HASH_MISMATCH');
  return { kind, expectedSha256, observedSha256 };
}

function validatedInput(
  input: PublicAccessibilityAcceptanceInput,
): PublicAccessibilityAcceptanceInput {
  const value = clonePlainObject(input);
  if (!hasExactKeys(value, INPUT_KEYS)) return reject('PUBLIC_ACCESSIBILITY_INPUT_INVALID');
  if (value['storyId'] !== 'ST-1007') return reject('PUBLIC_ACCESSIBILITY_STORY_INVALID');
  return { storyId: 'ST-1007', coordinate: requireCoordinate(value['coordinate']) };
}

function requiredSuites(
  method: PublicAccessibilityVerificationMethod,
): readonly ('TST-023' | 'TST-024')[] {
  if (method === 'automated') return ['TST-023'];
  if (method === 'automated+manual') return ['TST-023', 'TST-024'];
  return ['TST-024'];
}

function assessments(): readonly PublicAccessibilityAssessment[] {
  return PUBLIC_ACCESSIBILITY_CHECKLIST.map((checklistItem) => ({
    checklistItem,
    requiredSuiteIds: requiredSuites(checklistItem.verification),
    applicability: 'NOT_EVALUATED',
    executionStatus: 'NOT_EXECUTED',
    verificationResult: 'NOT_VERIFIED',
    evidenceRefs: [],
    environment: null,
    evaluator: null,
    executedAt: null,
  }));
}

function makeBoundaries(): Readonly<Record<string, PublicAccessibilityBoundaryResult>> {
  return Object.fromEntries(
    Object.entries(boundaryReasons).map(([key, reason]) => [
      key,
      { value: false, status: 'NOT_EXECUTED', reason },
    ]),
  );
}

function buildCandidate(
  input: PublicAccessibilityAcceptanceInput,
): PublicAccessibilityAcceptanceCandidate {
  return createJsonValue({
    classification: PUBLIC_ACCESSIBILITY_ACCEPTANCE_CLASSIFICATION,
    story: {
      id: 'ST-1007',
      objective: 'manual/automated改善',
      deliverable: 'a11y evidence',
      acceptanceCriterion: 'P0 checklist pass',
      dependencies: ['ST-1003', 'ST-1004', 'ST-1005'],
      requiredSuites: ['TST-023', 'TST-024'],
      designStatus: 'APPROVED_FOR_IMPLEMENTATION',
      implementationStatus: 'NOT_STARTED',
      verificationStatus: 'NOT_EXECUTED',
    },
    coordinate: input.coordinate,
    hashBinding: {
      profile: 'OPAQUE_CALLER_BOUND_EQUALITY_ONLY',
      expectedSha256: input.coordinate.expectedSha256,
      observedSha256: input.coordinate.observedSha256,
      equal: true,
      recomputed: false,
      canonicalized: false,
      runtimeVerified: false,
      formalEvidence: false,
    },
    catalog: {
      screens: PUBLIC_ACCESSIBILITY_SCREENS,
      components: PUBLIC_ACCESSIBILITY_COMPONENTS,
      directDependencyComponentIds: ['UI-C031', 'UI-C032', 'UI-C033', 'UI-C034', 'UI-C036'],
      applicabilityMapping: 'NOT_EVALUATED',
    },
    dependencyReadiness: [
      {
        storyId: 'ST-1003',
        classification: 'UNREGISTERED_DISABLED_HEADLESS_ST1003_SEMANTIC_METADATA_CANDIDATE',
        representedComponentIds: ['UI-C032', 'UI-C033', 'UI-C036'],
        domAvailable: false,
        browserAvailable: false,
        acceptanceEvidenceAvailable: false,
      },
      {
        storyId: 'ST-1004',
        classification: 'UNREGISTERED_DISABLED_HEADLESS_ST1004_DISCLOSURE_AFFILIATE_CANDIDATE',
        representedComponentIds: ['UI-C031', 'UI-C034'],
        domAvailable: false,
        browserAvailable: false,
        acceptanceEvidenceAvailable: false,
      },
      {
        storyId: 'ST-1005',
        classification: 'UNREGISTERED_DISABLED_HEADLESS_ST1005_SEO_ROUTE_POLICY_CANDIDATE',
        representedComponentIds: [],
        domAvailable: false,
        browserAvailable: false,
        acceptanceEvidenceAvailable: false,
      },
    ],
    checklistAssessments: assessments(),
    evidenceSuites: PUBLIC_ACCESSIBILITY_EVIDENCE_SUITES,
    evidenceState: {
      acceptsClaimedEvidence: false,
      browserExecuted: false,
      domAvailable: false,
      automatedAuditExecuted: false,
      keyboardExecuted: false,
      zoomExecuted: false,
      responsive320Executed: false,
      screenReaderExecuted: false,
      cognitiveReviewExecuted: false,
      ciExecuted: false,
      stagingExecuted: false,
      wcagConformanceClaim: false,
      evidenceRefs: [],
    },
    aggregate: {
      p0ChecklistPass: false,
      allItemsVerified: false,
      conditionalLocalEligibility: false,
      reasons: [
        'PUBLIC_RUNTIME_DOM_ABSENT',
        'CHECKLIST_APPLICABILITY_NOT_EVALUATED',
        'AUTOMATED_AUDIT_NOT_EXECUTED',
        'KEYBOARD_ZOOM_SCREEN_READER_COGNITIVE_REVIEW_NOT_EXECUTED',
        'FORMAL_TST_023_NOT_EXECUTED',
        'FORMAL_TST_024_NOT_EXECUTED',
      ],
    },
    authorization: {
      approval: false,
      publication: false,
      release: false,
      production: false,
      formalEvidence: false,
      accessibilityConformance: false,
    },
    boundaries: makeBoundaries(),
    events: [],
    actions: [],
    effects: [],
  }) as unknown as PublicAccessibilityAcceptanceCandidate;
}

function jsonEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function candidateInput(value: JsonObject): PublicAccessibilityAcceptanceInput {
  const story = value['story'];
  const coordinate = value['coordinate'];
  if (!isJsonObject(story) || !isJsonObject(coordinate)) {
    return reject('PUBLIC_ACCESSIBILITY_CANDIDATE_INVALID');
  }
  return {
    storyId: story['id'] as 'ST-1007',
    coordinate: coordinate as unknown as PublicAccessibilitySyntheticCoordinateInput,
  };
}

function classifyCandidateFailure(
  value: JsonObject,
  expected: PublicAccessibilityAcceptanceCandidate,
): PublicAccessibilityAcceptanceErrorCode {
  if (
    !jsonEqual(value['story'], expected.story) ||
    !jsonEqual(value['coordinate'], expected.coordinate) ||
    !jsonEqual(value['hashBinding'], expected.hashBinding)
  ) {
    return 'PUBLIC_ACCESSIBILITY_CATALOG_INVALID';
  }
  if (
    !jsonEqual(value['catalog'], expected.catalog) ||
    !jsonEqual(value['dependencyReadiness'], expected.dependencyReadiness)
  ) {
    return 'PUBLIC_ACCESSIBILITY_CATALOG_INVALID';
  }
  if (!jsonEqual(value['checklistAssessments'], expected.checklistAssessments)) {
    return 'PUBLIC_ACCESSIBILITY_CHECKLIST_INVALID';
  }
  if (
    !jsonEqual(value['evidenceSuites'], expected.evidenceSuites) ||
    !jsonEqual(value['evidenceState'], expected.evidenceState)
  ) {
    return 'PUBLIC_ACCESSIBILITY_EVIDENCE_STATE_INVALID';
  }
  if (
    value['classification'] !== PUBLIC_ACCESSIBILITY_ACCEPTANCE_CLASSIFICATION ||
    !jsonEqual(value['aggregate'], expected.aggregate) ||
    !jsonEqual(value['authorization'], expected.authorization) ||
    !jsonEqual(value['boundaries'], expected.boundaries) ||
    !jsonEqual(value['events'], expected.events) ||
    !jsonEqual(value['actions'], expected.actions) ||
    !jsonEqual(value['effects'], expected.effects)
  ) {
    return 'PUBLIC_ACCESSIBILITY_AUTHORITY_INVALID';
  }
  return 'PUBLIC_ACCESSIBILITY_CANDIDATE_INVALID';
}

export function validatePublicAccessibilityAcceptanceCandidate(
  value: unknown,
): PublicAccessibilityAcceptanceCandidate {
  const clone = clonePlainObject(value, false);
  let input: PublicAccessibilityAcceptanceInput;
  try {
    input = validatedInput(candidateInput(clone));
  } catch (error) {
    if (error instanceof PublicAccessibilityAcceptanceError) throw error;
    return reject('PUBLIC_ACCESSIBILITY_CANDIDATE_INVALID');
  }
  const expected = buildCandidate(input);
  if (!jsonEqual(clone, expected)) return reject(classifyCandidateFailure(clone, expected));
  return clone as unknown as PublicAccessibilityAcceptanceCandidate;
}

export function createPublicAccessibilityAcceptanceCandidate(
  input: PublicAccessibilityAcceptanceInput,
): PublicAccessibilityAcceptanceCandidate {
  return validatePublicAccessibilityAcceptanceCandidate(buildCandidate(validatedInput(input)));
}
