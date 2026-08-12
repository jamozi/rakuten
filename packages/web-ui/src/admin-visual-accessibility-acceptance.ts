import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const ADMIN_VISUAL_ACCESSIBILITY_ACCEPTANCE_CLASSIFICATION =
  'INCOMPLETE_DISABLED_HEADLESS_ST1105_ADMIN_VISUAL_ACCESSIBILITY_ACCEPTANCE_CANDIDATE' as const;

const screenGroupsSource = [
  {
    storyId: 'ST-0506',
    screenIds: [
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
    ],
  },
  { storyId: 'ST-0606', screenIds: ['EVD-001', 'EVD-002', 'EVD-003', 'EVD-004'] },
  { storyId: 'ST-0709', screenIds: ['GOV-001'] },
  {
    storyId: 'ST-0906',
    screenIds: ['REV-001', 'REV-002', 'REV-003', 'PUBA-001', 'PUBA-002', 'PUBA-003', 'PUBA-004'],
  },
  {
    storyId: 'ST-1102',
    screenIds: ['EDT-002', 'EDT-003', 'EDT-005', 'EDT-006', 'EDT-007', 'EDT-009'],
  },
  {
    storyId: 'ST-1103',
    screenIds: [
      'FRESH-001',
      'FRESH-002',
      'FRESH-003',
      'OPS-001',
      'OPS-002',
      'OPS-003',
      'OPS-004',
      'OPS-005',
    ],
  },
  {
    storyId: 'ST-1104',
    screenIds: ['ANA-001', 'ANA-002', 'ANA-003', 'FIN-001', 'FIN-002', 'FIN-003'],
  },
] as const;

export const ADMIN_VISUAL_ACCESSIBILITY_SCREEN_GROUPS = createJsonValue(
  screenGroupsSource,
) as unknown as readonly {
  readonly storyId:
    'ST-0506' | 'ST-0606' | 'ST-0709' | 'ST-0906' | 'ST-1102' | 'ST-1103' | 'ST-1104';
  readonly screenIds: readonly string[];
}[];

export const ADMIN_VISUAL_ACCESSIBILITY_SCREEN_IDS = createJsonValue(
  screenGroupsSource.flatMap(({ screenIds }) => screenIds),
) as unknown as readonly [
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
  'EVD-001',
  'EVD-002',
  'EVD-003',
  'EVD-004',
  'GOV-001',
  'REV-001',
  'REV-002',
  'REV-003',
  'PUBA-001',
  'PUBA-002',
  'PUBA-003',
  'PUBA-004',
  'EDT-002',
  'EDT-003',
  'EDT-005',
  'EDT-006',
  'EDT-007',
  'EDT-009',
  'FRESH-001',
  'FRESH-002',
  'FRESH-003',
  'OPS-001',
  'OPS-002',
  'OPS-003',
  'OPS-004',
  'OPS-005',
  'ANA-001',
  'ANA-002',
  'ANA-003',
  'FIN-001',
  'FIN-002',
  'FIN-003',
];

export type AdminVisualAccessibilityScreenId =
  (typeof ADMIN_VISUAL_ACCESSIBILITY_SCREEN_IDS)[number];

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

export type AdminVisualAccessibilityVerificationMethod =
  'automated' | 'automated+manual' | 'manual' | 'screen-reader';

export const ADMIN_VISUAL_ACCESSIBILITY_CHECKLIST = createJsonValue(
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
  readonly verification: AdminVisualAccessibilityVerificationMethod;
  readonly designStatus: 'APPROVED_FOR_IMPLEMENTATION';
  readonly implementationStatus: 'NOT_STARTED';
  readonly testStatus: 'NOT_EXECUTED';
}[];

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
  {
    id: 'TST-025',
    name: 'Visual regression',
    layer: 'ui',
    purpose: '主要Template/Component差分',
    candidateTools: ['Playwright screenshots'],
    releaseBlocking: false,
    environments: ['CI'],
    owner: 'Engineering',
  },
] as const;

export const ADMIN_VISUAL_ACCESSIBILITY_SUITES = createJsonValue(
  suiteSource.map((suite) => ({
    ...suite,
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    executionStatus: 'NOT_EXECUTED',
  })),
) as unknown as readonly JsonObject[];

export const ADMIN_VISUAL_ACCESSIBILITY_ERROR_CODES = createJsonValue([
  'ADMIN_VISUAL_ACCESSIBILITY_INPUT_INVALID',
  'ADMIN_VISUAL_ACCESSIBILITY_SCREEN_UNKNOWN',
  'ADMIN_VISUAL_ACCESSIBILITY_CANDIDATE_INVALID',
  'ADMIN_VISUAL_ACCESSIBILITY_SCOPE_INVALID',
  'ADMIN_VISUAL_ACCESSIBILITY_CHECKLIST_INVALID',
  'ADMIN_VISUAL_ACCESSIBILITY_SUITE_INVALID',
  'ADMIN_VISUAL_ACCESSIBILITY_BASELINE_INVALID',
]) as unknown as readonly [
  'ADMIN_VISUAL_ACCESSIBILITY_INPUT_INVALID',
  'ADMIN_VISUAL_ACCESSIBILITY_SCREEN_UNKNOWN',
  'ADMIN_VISUAL_ACCESSIBILITY_CANDIDATE_INVALID',
  'ADMIN_VISUAL_ACCESSIBILITY_SCOPE_INVALID',
  'ADMIN_VISUAL_ACCESSIBILITY_CHECKLIST_INVALID',
  'ADMIN_VISUAL_ACCESSIBILITY_SUITE_INVALID',
  'ADMIN_VISUAL_ACCESSIBILITY_BASELINE_INVALID',
];

export type AdminVisualAccessibilityErrorCode =
  (typeof ADMIN_VISUAL_ACCESSIBILITY_ERROR_CODES)[number];

export class AdminVisualAccessibilityError extends TypeError {
  readonly code: AdminVisualAccessibilityErrorCode;

  constructor(code: AdminVisualAccessibilityErrorCode) {
    const closedCode = (ADMIN_VISUAL_ACCESSIBILITY_ERROR_CODES as readonly unknown[]).includes(code)
      ? code
      : 'ADMIN_VISUAL_ACCESSIBILITY_CANDIDATE_INVALID';
    super(closedCode);
    this.name = 'AdminVisualAccessibilityError';
    this.code = closedCode;
    Object.freeze(this);
  }
}

export interface AdminVisualAccessibilityInput {
  readonly screenId: AdminVisualAccessibilityScreenId;
}

export interface AdminVisualAccessibilityAssessment {
  readonly checklistItem: (typeof ADMIN_VISUAL_ACCESSIBILITY_CHECKLIST)[number];
  readonly applicability: 'NOT_EVALUATED';
  readonly executionStatus: 'NOT_EXECUTED';
  readonly verificationResult: 'NOT_VERIFIED';
}

export interface AdminVisualAccessibilityCandidate {
  readonly classification: typeof ADMIN_VISUAL_ACCESSIBILITY_ACCEPTANCE_CLASSIFICATION;
  readonly storyId: 'ST-1105';
  readonly selectedScreenId: AdminVisualAccessibilityScreenId;
  readonly screenScope: {
    readonly groups: typeof ADMIN_VISUAL_ACCESSIBILITY_SCREEN_GROUPS;
    readonly screenIds: typeof ADMIN_VISUAL_ACCESSIBILITY_SCREEN_IDS;
    readonly completeness: 'INCOMPLETE_DEPENDENCY_EXPOSED_SCREEN_SCOPE';
    readonly applicability: 'NOT_EVALUATED';
  };
  readonly components: readonly [];
  readonly componentOwnership: 'NOT_INFERRED';
  readonly criticalWorkflowIds: readonly [];
  readonly criticalWorkflowSelection: 'NOT_EVALUATED';
  readonly checklistAssessments: readonly AdminVisualAccessibilityAssessment[];
  readonly suites: typeof ADMIN_VISUAL_ACCESSIBILITY_SUITES;
  readonly visualBaseline: {
    readonly availability: 'UNAVAILABLE';
    readonly refs: readonly [];
    readonly results: readonly [];
    readonly screenshots: readonly [];
    readonly profile: null;
    readonly tolerance: null;
    readonly approved: false;
  };
}

function reject(code: AdminVisualAccessibilityErrorCode): never {
  throw new AdminVisualAccessibilityError(code);
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

function cloneStrict(value: unknown): JsonValue {
  if (!isStrictPlainTree(value)) return reject('ADMIN_VISUAL_ACCESSIBILITY_INPUT_INVALID');
  try {
    return createJsonValue(value);
  } catch {
    return reject('ADMIN_VISUAL_ACCESSIBILITY_INPUT_INVALID');
  }
}

function isJsonObject(value: JsonValue | undefined): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function validatedScreenId(input: AdminVisualAccessibilityInput): AdminVisualAccessibilityScreenId {
  const value = cloneStrict(input);
  if (!isJsonObject(value)) return reject('ADMIN_VISUAL_ACCESSIBILITY_INPUT_INVALID');
  const keys = Object.keys(value);
  if (keys.length !== 1 || keys[0] !== 'screenId' || typeof value['screenId'] !== 'string') {
    return reject('ADMIN_VISUAL_ACCESSIBILITY_INPUT_INVALID');
  }
  if (!(ADMIN_VISUAL_ACCESSIBILITY_SCREEN_IDS as readonly string[]).includes(value['screenId'])) {
    return reject('ADMIN_VISUAL_ACCESSIBILITY_SCREEN_UNKNOWN');
  }
  return value['screenId'] as AdminVisualAccessibilityScreenId;
}

function assessments(): readonly AdminVisualAccessibilityAssessment[] {
  return ADMIN_VISUAL_ACCESSIBILITY_CHECKLIST.map((checklistItem) => ({
    checklistItem,
    applicability: 'NOT_EVALUATED',
    executionStatus: 'NOT_EXECUTED',
    verificationResult: 'NOT_VERIFIED',
  }));
}

function buildCandidate(
  screenId: AdminVisualAccessibilityScreenId,
): AdminVisualAccessibilityCandidate {
  return createJsonValue({
    classification: ADMIN_VISUAL_ACCESSIBILITY_ACCEPTANCE_CLASSIFICATION,
    storyId: 'ST-1105',
    selectedScreenId: screenId,
    screenScope: {
      groups: ADMIN_VISUAL_ACCESSIBILITY_SCREEN_GROUPS,
      screenIds: ADMIN_VISUAL_ACCESSIBILITY_SCREEN_IDS,
      completeness: 'INCOMPLETE_DEPENDENCY_EXPOSED_SCREEN_SCOPE',
      applicability: 'NOT_EVALUATED',
    },
    components: [],
    componentOwnership: 'NOT_INFERRED',
    criticalWorkflowIds: [],
    criticalWorkflowSelection: 'NOT_EVALUATED',
    checklistAssessments: assessments(),
    suites: ADMIN_VISUAL_ACCESSIBILITY_SUITES,
    visualBaseline: {
      availability: 'UNAVAILABLE',
      refs: [],
      results: [],
      screenshots: [],
      profile: null,
      tolerance: null,
      approved: false,
    },
  }) as unknown as AdminVisualAccessibilityCandidate;
}

function jsonEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function classifyCandidateFailure(
  value: JsonObject,
  expected: AdminVisualAccessibilityCandidate,
): AdminVisualAccessibilityErrorCode {
  if (
    !jsonEqual(value['selectedScreenId'], expected.selectedScreenId) ||
    !jsonEqual(value['screenScope'], expected.screenScope) ||
    !jsonEqual(value['components'], expected.components) ||
    !jsonEqual(value['componentOwnership'], expected.componentOwnership) ||
    !jsonEqual(value['criticalWorkflowIds'], expected.criticalWorkflowIds) ||
    !jsonEqual(value['criticalWorkflowSelection'], expected.criticalWorkflowSelection)
  ) {
    return 'ADMIN_VISUAL_ACCESSIBILITY_SCOPE_INVALID';
  }
  if (!jsonEqual(value['checklistAssessments'], expected.checklistAssessments)) {
    return 'ADMIN_VISUAL_ACCESSIBILITY_CHECKLIST_INVALID';
  }
  if (!jsonEqual(value['suites'], expected.suites)) {
    return 'ADMIN_VISUAL_ACCESSIBILITY_SUITE_INVALID';
  }
  if (!jsonEqual(value['visualBaseline'], expected.visualBaseline)) {
    return 'ADMIN_VISUAL_ACCESSIBILITY_BASELINE_INVALID';
  }
  return 'ADMIN_VISUAL_ACCESSIBILITY_CANDIDATE_INVALID';
}

export function validateAdminVisualAccessibilityCandidate(
  value: unknown,
): AdminVisualAccessibilityCandidate {
  let clone: JsonValue;
  try {
    clone = cloneStrict(value);
  } catch (error) {
    if (error instanceof AdminVisualAccessibilityError) {
      return reject('ADMIN_VISUAL_ACCESSIBILITY_CANDIDATE_INVALID');
    }
    return reject('ADMIN_VISUAL_ACCESSIBILITY_CANDIDATE_INVALID');
  }
  if (!isJsonObject(clone) || typeof clone['selectedScreenId'] !== 'string') {
    return reject('ADMIN_VISUAL_ACCESSIBILITY_CANDIDATE_INVALID');
  }
  if (
    !(ADMIN_VISUAL_ACCESSIBILITY_SCREEN_IDS as readonly string[]).includes(
      clone['selectedScreenId'],
    )
  ) {
    return reject('ADMIN_VISUAL_ACCESSIBILITY_SCREEN_UNKNOWN');
  }
  const expected = buildCandidate(clone['selectedScreenId'] as AdminVisualAccessibilityScreenId);
  if (!jsonEqual(clone, expected)) return reject(classifyCandidateFailure(clone, expected));
  return clone as unknown as AdminVisualAccessibilityCandidate;
}

export function createAdminVisualAccessibilityCandidate(
  input: AdminVisualAccessibilityInput,
): AdminVisualAccessibilityCandidate {
  return validateAdminVisualAccessibilityCandidate(buildCandidate(validatedScreenId(input)));
}
