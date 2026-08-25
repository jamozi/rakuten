import {
  ST1105_ADMIN_VISUAL_ACCESSIBILITY_RECORDED_V2,
  ST1105_ADMIN_VISUAL_ACCESSIBILITY_RECORDED_V2_SHA256,
} from './admin-visual-accessibility-recorded.v2.ts';
import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const ADMIN_VISUAL_ACCESSIBILITY_V2_CLASSIFICATION =
  'MAXIMUM_SAFE_LOCAL_RECORDED_SYNTHETIC_ADMIN_VISUAL_ACCESSIBILITY_ACCEPTANCE_V2' as const;

const recorded = ST1105_ADMIN_VISUAL_ACCESSIBILITY_RECORDED_V2;

export const ADMIN_VISUAL_ACCESSIBILITY_V2_SCREEN_IDS = recorded[
  'screen_order'
] as unknown as readonly string[];

export const ADMIN_VISUAL_ACCESSIBILITY_V2_COMPONENT_INVENTORY = recorded[
  'component_inventory'
] as unknown as readonly JsonObject[];

export const ADMIN_VISUAL_ACCESSIBILITY_V2_CRITICAL_WORKFLOWS = recorded[
  'critical_workflows'
] as unknown as readonly JsonObject[];

export const ADMIN_VISUAL_ACCESSIBILITY_V2_CHECKLIST = recorded[
  'accessibility_checklist'
] as unknown as readonly JsonObject[];

export const ADMIN_VISUAL_ACCESSIBILITY_V2_FORMAL_SUITES = recorded[
  'formal_suites'
] as unknown as readonly JsonObject[];

export const ADMIN_VISUAL_ACCESSIBILITY_V2_ERROR_CODES = createJsonValue([
  'ADMIN_VISUAL_ACCESSIBILITY_V2_INPUT_INVALID',
  'ADMIN_VISUAL_ACCESSIBILITY_V2_SCREEN_UNKNOWN',
  'ADMIN_VISUAL_ACCESSIBILITY_V2_CANDIDATE_INVALID',
  'ADMIN_VISUAL_ACCESSIBILITY_V2_INVENTORY_INVALID',
  'ADMIN_VISUAL_ACCESSIBILITY_V2_EVIDENCE_BOUNDARY_INVALID',
]) as unknown as readonly [
  'ADMIN_VISUAL_ACCESSIBILITY_V2_INPUT_INVALID',
  'ADMIN_VISUAL_ACCESSIBILITY_V2_SCREEN_UNKNOWN',
  'ADMIN_VISUAL_ACCESSIBILITY_V2_CANDIDATE_INVALID',
  'ADMIN_VISUAL_ACCESSIBILITY_V2_INVENTORY_INVALID',
  'ADMIN_VISUAL_ACCESSIBILITY_V2_EVIDENCE_BOUNDARY_INVALID',
];

export type AdminVisualAccessibilityV2ErrorCode =
  (typeof ADMIN_VISUAL_ACCESSIBILITY_V2_ERROR_CODES)[number];

export class AdminVisualAccessibilityV2Error extends TypeError {
  readonly code: AdminVisualAccessibilityV2ErrorCode;

  constructor(code: AdminVisualAccessibilityV2ErrorCode) {
    const closedCode = (ADMIN_VISUAL_ACCESSIBILITY_V2_ERROR_CODES as readonly unknown[]).includes(
      code,
    )
      ? code
      : 'ADMIN_VISUAL_ACCESSIBILITY_V2_CANDIDATE_INVALID';
    super(closedCode);
    this.name = 'AdminVisualAccessibilityV2Error';
    this.code = closedCode;
    Object.freeze(this);
  }
}

export interface AdminVisualAccessibilityV2Input {
  readonly screenId: string;
}

export interface AdminVisualAccessibilityV2Candidate {
  readonly classification: typeof ADMIN_VISUAL_ACCESSIBILITY_V2_CLASSIFICATION;
  readonly storyId: 'ST-1105';
  readonly localStatus: 'LOCAL_IMPLEMENTATION_COMPLETE';
  readonly sourceMode: 'RECORDED_SYNTHETIC_DEV_CI_ONLY';
  readonly selectedScreen: JsonObject;
  readonly screenInventory: {
    readonly count: 44;
    readonly screenIds: readonly string[];
    readonly completeness: 'COMPLETE_DEPENDENCY_EXPOSED_SCOPE';
    readonly catalogRoutesRegistered: false;
  };
  readonly componentInventory: readonly JsonObject[];
  readonly componentInventoryCompleteness: 'COMPLETE_DEPENDENCY_EXPOSED_SCOPE';
  readonly criticalWorkflows: readonly JsonObject[];
  readonly criticalWorkflowCompleteness: 'COMPLETE_CANONICAL_CATALOG_SCOPE';
  readonly checklistAssessments: readonly JsonObject[];
  readonly formalSuites: readonly JsonObject[];
  readonly localBrowserEvidence: JsonObject;
  readonly visualBaseline: JsonObject;
  readonly formalBoundary: JsonObject;
  readonly authority: JsonObject;
  readonly provenance: {
    readonly recordedArtifactSha256: typeof ST1105_ADMIN_VISUAL_ACCESSIBILITY_RECORDED_V2_SHA256;
    readonly payloadSha256: string;
  };
  readonly formalAcceptanceAchieved: false;
  readonly productionEligible: false;
}

function reject(code: AdminVisualAccessibilityV2ErrorCode): never {
  throw new AdminVisualAccessibilityV2Error(code);
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

function strictClone(value: unknown, code: AdminVisualAccessibilityV2ErrorCode): JsonValue {
  if (!isStrictPlainTree(value)) return reject(code);
  try {
    return createJsonValue(value);
  } catch {
    return reject(code);
  }
}

function isObject(value: JsonValue | undefined): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function validateInput(input: AdminVisualAccessibilityV2Input): string {
  const clone = strictClone(input, 'ADMIN_VISUAL_ACCESSIBILITY_V2_INPUT_INVALID');
  if (
    !isObject(clone) ||
    Object.keys(clone).length !== 1 ||
    typeof clone['screenId'] !== 'string'
  ) {
    return reject('ADMIN_VISUAL_ACCESSIBILITY_V2_INPUT_INVALID');
  }
  if (!ADMIN_VISUAL_ACCESSIBILITY_V2_SCREEN_IDS.includes(clone['screenId'])) {
    return reject('ADMIN_VISUAL_ACCESSIBILITY_V2_SCREEN_UNKNOWN');
  }
  return clone['screenId'];
}

function buildCandidate(screenId: string): AdminVisualAccessibilityV2Candidate {
  const screens = recorded['screens'];
  const browserContract = recorded['browser_contract'];
  const formalBoundary = recorded['formal_boundary'];
  const authority = recorded['authority'];
  const payloadSha256 = recorded['payload_sha256'];
  if (
    !Array.isArray(screens) ||
    !isObject(browserContract) ||
    !isObject(browserContract['baseline']) ||
    !isObject(browserContract['evidence']) ||
    !isObject(formalBoundary) ||
    !isObject(authority) ||
    typeof payloadSha256 !== 'string'
  ) {
    return reject('ADMIN_VISUAL_ACCESSIBILITY_V2_INVENTORY_INVALID');
  }
  const screen = screens.find(
    (value): value is JsonObject => isObject(value) && value['screen_id'] === screenId,
  );
  if (screen === undefined) {
    return reject('ADMIN_VISUAL_ACCESSIBILITY_V2_SCREEN_UNKNOWN');
  }
  const checklistAssessments = ADMIN_VISUAL_ACCESSIBILITY_V2_CHECKLIST.map((checklistItem) => ({
    checklistItem,
    applicability:
      checklistItem['local_automation_capability'] === 'SYNTHETIC_PATTERN_AUTOMATED'
        ? 'SYNTHETIC_FIXTURE_PATTERN_ONLY'
        : 'NOT_EVALUATED',
    localEvidence: 'SEPARATE_HASH_BOUND_ARTIFACT',
    formalExecutionStatus: 'NOT_EXECUTED',
    manualExecutionStatus: 'NOT_EXECUTED',
    conformanceResult: 'NOT_VERIFIED',
  }));
  return createJsonValue({
    classification: ADMIN_VISUAL_ACCESSIBILITY_V2_CLASSIFICATION,
    storyId: 'ST-1105',
    localStatus: 'LOCAL_IMPLEMENTATION_COMPLETE',
    sourceMode: 'RECORDED_SYNTHETIC_DEV_CI_ONLY',
    selectedScreen: screen,
    screenInventory: {
      count: 44,
      screenIds: ADMIN_VISUAL_ACCESSIBILITY_V2_SCREEN_IDS,
      completeness: 'COMPLETE_DEPENDENCY_EXPOSED_SCOPE',
      catalogRoutesRegistered: false,
    },
    componentInventory: ADMIN_VISUAL_ACCESSIBILITY_V2_COMPONENT_INVENTORY,
    componentInventoryCompleteness: 'COMPLETE_DEPENDENCY_EXPOSED_SCOPE',
    criticalWorkflows: ADMIN_VISUAL_ACCESSIBILITY_V2_CRITICAL_WORKFLOWS,
    criticalWorkflowCompleteness: 'COMPLETE_CANONICAL_CATALOG_SCOPE',
    checklistAssessments,
    formalSuites: ADMIN_VISUAL_ACCESSIBILITY_V2_FORMAL_SUITES,
    localBrowserEvidence: browserContract['evidence'],
    visualBaseline: browserContract['baseline'],
    formalBoundary,
    authority,
    provenance: {
      recordedArtifactSha256: ST1105_ADMIN_VISUAL_ACCESSIBILITY_RECORDED_V2_SHA256,
      payloadSha256,
    },
    formalAcceptanceAchieved: false,
    productionEligible: false,
  }) as unknown as AdminVisualAccessibilityV2Candidate;
}

export function createAdminVisualAccessibilityV2Candidate(
  input: AdminVisualAccessibilityV2Input,
): AdminVisualAccessibilityV2Candidate {
  return validateAdminVisualAccessibilityV2Candidate(buildCandidate(validateInput(input)));
}

export function validateAdminVisualAccessibilityV2Candidate(
  candidate: unknown,
): AdminVisualAccessibilityV2Candidate {
  const clone = strictClone(candidate, 'ADMIN_VISUAL_ACCESSIBILITY_V2_CANDIDATE_INVALID');
  if (!isObject(clone) || !isObject(clone['selectedScreen'])) {
    return reject('ADMIN_VISUAL_ACCESSIBILITY_V2_CANDIDATE_INVALID');
  }
  const screenId = clone['selectedScreen']['screen_id'];
  if (
    typeof screenId !== 'string' ||
    !ADMIN_VISUAL_ACCESSIBILITY_V2_SCREEN_IDS.includes(screenId)
  ) {
    return reject('ADMIN_VISUAL_ACCESSIBILITY_V2_SCREEN_UNKNOWN');
  }
  const expected = buildCandidate(screenId);
  if (JSON.stringify(clone) !== JSON.stringify(expected)) {
    if (
      JSON.stringify(clone['formalBoundary']) !== JSON.stringify(expected.formalBoundary) ||
      JSON.stringify(clone['formalSuites']) !== JSON.stringify(expected.formalSuites) ||
      JSON.stringify(clone['localBrowserEvidence']) !==
        JSON.stringify(expected.localBrowserEvidence) ||
      JSON.stringify(clone['visualBaseline']) !== JSON.stringify(expected.visualBaseline)
    ) {
      return reject('ADMIN_VISUAL_ACCESSIBILITY_V2_EVIDENCE_BOUNDARY_INVALID');
    }
    return reject('ADMIN_VISUAL_ACCESSIBILITY_V2_CANDIDATE_INVALID');
  }
  return clone as unknown as AdminVisualAccessibilityV2Candidate;
}
