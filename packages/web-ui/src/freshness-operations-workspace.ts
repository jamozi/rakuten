import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const FRESHNESS_OPERATIONS_WORKSPACE_CLASSIFICATION =
  'SOURCE_DERIVED_DISABLED_HEADLESS_FRESHNESS_OPERATIONS_WORKSPACE_CANDIDATE' as const;

export const FRESHNESS_OPERATIONS_SCREEN_IDS = createJsonValue([
  'FRESH-001',
  'FRESH-002',
  'FRESH-003',
  'OPS-001',
  'OPS-002',
  'OPS-003',
  'OPS-004',
  'OPS-005',
]) as unknown as readonly [
  'FRESH-001',
  'FRESH-002',
  'FRESH-003',
  'OPS-001',
  'OPS-002',
  'OPS-003',
  'OPS-004',
  'OPS-005',
];

export type FreshnessOperationsScreenId = (typeof FRESHNESS_OPERATIONS_SCREEN_IDS)[number];

export type FreshnessOperationsRole =
  | 'PRODUCT_OWNER'
  | 'MANAGING_EDITOR'
  | 'EDITOR'
  | 'REVIEWER'
  | 'OPERATOR'
  | 'SECURITY_AUDITOR'
  | 'READ_ONLY_AUDITOR';

export interface FreshnessOperationsScreenMetadata {
  readonly id: FreshnessOperationsScreenId;
  readonly name:
    | 'Freshness Queue'
    | 'Link Health'
    | 'Refresh Proposal'
    | 'Job Monitor'
    | 'DLQ / Quarantine'
    | 'Incident'
    | 'Kill Switches'
    | 'Audit Log';
  readonly route:
    | '/admin/freshness'
    | '/admin/freshness/link-health'
    | '/admin/freshness/proposals/{id}'
    | '/admin/ops/jobs'
    | '/admin/ops/dlq'
    | '/admin/ops/incidents/{id}'
    | '/admin/ops/kill-switches'
    | '/admin/ops/audit';
  readonly area: 'freshness' | 'operations';
  readonly roles: readonly FreshnessOperationsRole[];
  readonly purpose: string;
  readonly mvp: true;
  readonly criticalAction: boolean;
  readonly apiDependencies: readonly [];
  readonly designStatus: 'APPROVED_FOR_IMPLEMENTATION';
  readonly implementationStatus: 'NOT_STARTED';
  readonly runtimeVerification: 'NOT_EXECUTED';
  readonly routeRegistered: false;
}

const screenMetadataSource = [
  {
    id: 'FRESH-001',
    name: 'Freshness Queue',
    route: '/admin/freshness',
    area: 'freshness',
    roles: ['MANAGING_EDITOR', 'EDITOR', 'OPERATOR'],
    purpose: 'Stale/Expired Factと影響記事を管理',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
    routeRegistered: false,
  },
  {
    id: 'FRESH-002',
    name: 'Link Health',
    route: '/admin/freshness/link-health',
    area: 'freshness',
    roles: ['EDITOR', 'OPERATOR'],
    purpose: 'Affiliate LinkとDestination異常を確認',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
    routeRegistered: false,
  },
  {
    id: 'FRESH-003',
    name: 'Refresh Proposal',
    route: '/admin/freshness/proposals/{id}',
    area: 'freshness',
    roles: ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
    purpose: '更新差分と再承認範囲を確認',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
    routeRegistered: false,
  },
  {
    id: 'OPS-001',
    name: 'Job Monitor',
    route: '/admin/ops/jobs',
    area: 'operations',
    roles: ['OPERATOR', 'SECURITY_AUDITOR'],
    purpose: 'Job、Attempt、Lease、Retryを監視',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
    routeRegistered: false,
  },
  {
    id: 'OPS-002',
    name: 'DLQ / Quarantine',
    route: '/admin/ops/dlq',
    area: 'operations',
    roles: ['OPERATOR', 'SECURITY_AUDITOR'],
    purpose: '隔離Payloadを安全に調査・再実行',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
    routeRegistered: false,
  },
  {
    id: 'OPS-003',
    name: 'Incident',
    route: '/admin/ops/incidents/{id}',
    area: 'operations',
    roles: ['PRODUCT_OWNER', 'OPERATOR', 'SECURITY_AUDITOR'],
    purpose: 'Incident、Timeline、Action、Evidenceを管理',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
    routeRegistered: false,
  },
  {
    id: 'OPS-004',
    name: 'Kill Switches',
    route: '/admin/ops/kill-switches',
    area: 'operations',
    roles: ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'OPERATOR'],
    purpose: 'Publication/Affiliate停止をstep-upで操作',
    mvp: true,
    criticalAction: true,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
    routeRegistered: false,
  },
  {
    id: 'OPS-005',
    name: 'Audit Log',
    route: '/admin/ops/audit',
    area: 'operations',
    roles: ['SECURITY_AUDITOR', 'READ_ONLY_AUDITOR'],
    purpose: '不変Audit Eventを検索',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
    routeRegistered: false,
  },
] as const;

export const FRESHNESS_OPERATIONS_SCREENS = createJsonValue(
  screenMetadataSource,
) as unknown as readonly FreshnessOperationsScreenMetadata[];

export const FRESHNESS_OPERATIONS_WORKSPACE_ERROR_CODES = createJsonValue([
  'FRESHNESS_OPERATIONS_INPUT_INVALID',
  'FRESHNESS_OPERATIONS_SCREEN_UNKNOWN',
  'FRESHNESS_OPERATIONS_CANDIDATE_INVALID',
  'FRESHNESS_OPERATIONS_DUPLICATE_ID',
  'FRESHNESS_OPERATIONS_DUPLICATE_ROUTE',
  'FRESHNESS_OPERATIONS_METADATA_INVALID',
  'FRESHNESS_OPERATIONS_STATE_INVALID',
  'FRESHNESS_OPERATIONS_ACCESSIBILITY_INVALID',
  'FRESHNESS_OPERATIONS_AUTHORITY_INVALID',
  'FRESHNESS_OPERATIONS_PROHIBITED_SURFACE',
]) as unknown as readonly [
  'FRESHNESS_OPERATIONS_INPUT_INVALID',
  'FRESHNESS_OPERATIONS_SCREEN_UNKNOWN',
  'FRESHNESS_OPERATIONS_CANDIDATE_INVALID',
  'FRESHNESS_OPERATIONS_DUPLICATE_ID',
  'FRESHNESS_OPERATIONS_DUPLICATE_ROUTE',
  'FRESHNESS_OPERATIONS_METADATA_INVALID',
  'FRESHNESS_OPERATIONS_STATE_INVALID',
  'FRESHNESS_OPERATIONS_ACCESSIBILITY_INVALID',
  'FRESHNESS_OPERATIONS_AUTHORITY_INVALID',
  'FRESHNESS_OPERATIONS_PROHIBITED_SURFACE',
];

export type FreshnessOperationsWorkspaceErrorCode =
  (typeof FRESHNESS_OPERATIONS_WORKSPACE_ERROR_CODES)[number];

export class FreshnessOperationsWorkspaceError extends TypeError {
  readonly code: FreshnessOperationsWorkspaceErrorCode;

  constructor(code: FreshnessOperationsWorkspaceErrorCode) {
    const closedCode = (FRESHNESS_OPERATIONS_WORKSPACE_ERROR_CODES as readonly unknown[]).includes(
      code,
    )
      ? code
      : 'FRESHNESS_OPERATIONS_CANDIDATE_INVALID';
    super(closedCode);
    this.name = 'FreshnessOperationsWorkspaceError';
    this.code = closedCode;
    Object.freeze(this);
  }
}

export interface FreshnessOperationsWorkspaceInput {
  readonly screenId: FreshnessOperationsScreenId;
}

export interface FreshnessOperationsDataSlot {
  readonly status: 'NOT_LOADED' | 'NOT_EVALUATED';
  readonly payload: null | readonly [];
}

export interface FreshnessOperationsWorkspaceCandidate {
  readonly classification: typeof FRESHNESS_OPERATIONS_WORKSPACE_CLASSIFICATION;
  readonly storyId: 'ST-1103';
  readonly screen: FreshnessOperationsScreenMetadata;
  readonly catalogScreens: readonly FreshnessOperationsScreenMetadata[];
  readonly canonicalScreenOrder: typeof FRESHNESS_OPERATIONS_SCREEN_IDS;
  readonly availability: 'DISABLED';
  readonly roleInputAccepted: false;
  readonly roleMetadataAuthority: 'DISPLAY_ONLY_NOT_AUTHENTICATION_OR_AUTHORIZATION';
  readonly components: readonly [];
  readonly componentOwnership: 'NOT_INFERRED';
  readonly routeRegistered: false;
  readonly renderEnabled: false;
  readonly dataSlots: {
    readonly primary: FreshnessOperationsDataSlot;
    readonly status: FreshnessOperationsDataSlot;
    readonly items: FreshnessOperationsDataSlot;
    readonly evidence: FreshnessOperationsDataSlot;
  };
  readonly dependencies: {
    readonly freshnessPolicy: {
      readonly storyId: 'ST-1401';
      readonly openDecision: 'OD-007';
      readonly status: 'UNAVAILABLE';
      readonly payload: null;
    };
    readonly jobRuntime: {
      readonly storyId: 'ST-1404';
      readonly status: 'RECORDED_ONLY';
      readonly runtimeAuthority: false;
      readonly payload: null;
    };
    readonly killSwitch: {
      readonly screenId: 'OPS-004';
      readonly storyId: 'ST-1405';
      readonly status: 'UNAVAILABLE';
      readonly authority: 'UNDECLARED';
      readonly payload: null;
    };
    readonly auditLog: {
      readonly screenId: 'OPS-005';
      readonly status: 'UNAVAILABLE';
      readonly authority: 'UNDECLARED';
      readonly payload: null;
    };
  };
  readonly actions: readonly [];
  readonly actionAvailability: 'UNAVAILABLE';
  readonly effectAvailability: 'UNAVAILABLE';
  readonly intentAvailability: 'UNAVAILABLE';
  readonly accessibility: {
    readonly requirementsOnly: true;
    readonly rendered: false;
    readonly verified: false;
    readonly statusPresentation: {
      readonly textRequired: true;
      readonly codeRequired: true;
      readonly iconRequired: true;
      readonly colorOnly: false;
      readonly rendered: false;
      readonly verified: false;
    };
  };
  readonly authority: {
    readonly authenticationEstablished: false;
    readonly authorizationGranted: false;
    readonly stepUpEstablished: false;
    readonly mutationEnabled: false;
    readonly networkEnabled: false;
    readonly persistenceEnabled: false;
    readonly runtimeEnabled: false;
    readonly externalActionEnabled: false;
    readonly criticalActionExecutionEnabled: false;
    readonly publicationAuthorized: false;
    readonly releaseAuthorized: false;
    readonly productionAuthorized: false;
  };
  readonly verification: {
    readonly runtime: 'NOT_VERIFIED';
    readonly accessibility: 'NOT_VERIFIED';
    readonly formal: 'NOT_EXECUTED';
    readonly live: 'NOT_EXECUTED';
    readonly staging: 'NOT_EXECUTED';
    readonly release: 'NOT_EXECUTED';
    readonly publication: 'NOT_EXECUTED';
    readonly production: 'NOT_EXECUTED';
  };
  readonly acceptanceAchieved: false;
  readonly storyComplete: false;
  readonly productionEligible: false;
}

function reject(code: FreshnessOperationsWorkspaceErrorCode): never {
  throw new FreshnessOperationsWorkspaceError(code);
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
    const array = Array.isArray(value);
    if (Object.getPrototypeOf(value) !== (array ? Array.prototype : Object.prototype)) {
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

function cloneStrict(value: unknown, code: FreshnessOperationsWorkspaceErrorCode): JsonValue {
  if (!isStrictPlainTree(value)) {
    return reject(code);
  }
  try {
    return createJsonValue(value);
  } catch {
    return reject(code);
  }
}

function validatedScreenId(input: FreshnessOperationsWorkspaceInput): FreshnessOperationsScreenId {
  const value = cloneStrict(input, 'FRESHNESS_OPERATIONS_INPUT_INVALID');
  if (!isJsonObject(value)) {
    return reject('FRESHNESS_OPERATIONS_INPUT_INVALID');
  }
  const keys = Object.keys(value);
  if (keys.length !== 1 || keys[0] !== 'screenId') {
    return reject('FRESHNESS_OPERATIONS_INPUT_INVALID');
  }
  const screenId = value['screenId'];
  if (typeof screenId !== 'string') {
    return reject('FRESHNESS_OPERATIONS_INPUT_INVALID');
  }
  if (!(FRESHNESS_OPERATIONS_SCREEN_IDS as readonly string[]).includes(screenId)) {
    return reject('FRESHNESS_OPERATIONS_SCREEN_UNKNOWN');
  }
  return screenId as FreshnessOperationsScreenId;
}

function buildCandidate(
  screenId: FreshnessOperationsScreenId,
): FreshnessOperationsWorkspaceCandidate {
  const screen = FRESHNESS_OPERATIONS_SCREENS.find((item) => item.id === screenId);
  if (screen === undefined) {
    return reject('FRESHNESS_OPERATIONS_SCREEN_UNKNOWN');
  }
  return createJsonValue({
    classification: FRESHNESS_OPERATIONS_WORKSPACE_CLASSIFICATION,
    storyId: 'ST-1103',
    screen,
    catalogScreens: FRESHNESS_OPERATIONS_SCREENS,
    canonicalScreenOrder: FRESHNESS_OPERATIONS_SCREEN_IDS,
    availability: 'DISABLED',
    roleInputAccepted: false,
    roleMetadataAuthority: 'DISPLAY_ONLY_NOT_AUTHENTICATION_OR_AUTHORIZATION',
    components: [],
    componentOwnership: 'NOT_INFERRED',
    routeRegistered: false,
    renderEnabled: false,
    dataSlots: {
      primary: { status: 'NOT_LOADED', payload: null },
      status: { status: 'NOT_EVALUATED', payload: null },
      items: { status: 'NOT_LOADED', payload: [] },
      evidence: { status: 'NOT_EVALUATED', payload: [] },
    },
    dependencies: {
      freshnessPolicy: {
        storyId: 'ST-1401',
        openDecision: 'OD-007',
        status: 'UNAVAILABLE',
        payload: null,
      },
      jobRuntime: {
        storyId: 'ST-1404',
        status: 'RECORDED_ONLY',
        runtimeAuthority: false,
        payload: null,
      },
      killSwitch: {
        screenId: 'OPS-004',
        storyId: 'ST-1405',
        status: 'UNAVAILABLE',
        authority: 'UNDECLARED',
        payload: null,
      },
      auditLog: {
        screenId: 'OPS-005',
        status: 'UNAVAILABLE',
        authority: 'UNDECLARED',
        payload: null,
      },
    },
    actions: [],
    actionAvailability: 'UNAVAILABLE',
    effectAvailability: 'UNAVAILABLE',
    intentAvailability: 'UNAVAILABLE',
    accessibility: {
      requirementsOnly: true,
      rendered: false,
      verified: false,
      statusPresentation: {
        textRequired: true,
        codeRequired: true,
        iconRequired: true,
        colorOnly: false,
        rendered: false,
        verified: false,
      },
    },
    authority: {
      authenticationEstablished: false,
      authorizationGranted: false,
      stepUpEstablished: false,
      mutationEnabled: false,
      networkEnabled: false,
      persistenceEnabled: false,
      runtimeEnabled: false,
      externalActionEnabled: false,
      criticalActionExecutionEnabled: false,
      publicationAuthorized: false,
      releaseAuthorized: false,
      productionAuthorized: false,
    },
    verification: {
      runtime: 'NOT_VERIFIED',
      accessibility: 'NOT_VERIFIED',
      formal: 'NOT_EXECUTED',
      live: 'NOT_EXECUTED',
      staging: 'NOT_EXECUTED',
      release: 'NOT_EXECUTED',
      publication: 'NOT_EXECUTED',
      production: 'NOT_EXECUTED',
    },
    acceptanceAchieved: false,
    storyComplete: false,
    productionEligible: false,
  }) as unknown as FreshnessOperationsWorkspaceCandidate;
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
  'componentid',
  'componentids',
  'componentowner',
  'componentownershipmap',
  'callback',
  'callbacks',
  'handler',
  'intent',
  'intents',
  'effect',
  'effects',
  'token',
  'credential',
  'secret',
  'rawpayload',
  'payloadbody',
  'html',
  'script',
  'iframe',
  'url',
  'origin',
  'database',
  'queue',
  'environment',
  'authoritytoken',
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

function classifyCandidateFailure(
  value: Readonly<Record<string, JsonValue>>,
  expected: FreshnessOperationsWorkspaceCandidate,
): FreshnessOperationsWorkspaceErrorCode {
  if (hasProhibitedSurface(value)) {
    return 'FRESHNESS_OPERATIONS_PROHIBITED_SURFACE';
  }
  const screens = recordArray(value['catalogScreens']);
  if (hasDuplicate(valuesFor(screens, 'id'))) {
    return 'FRESHNESS_OPERATIONS_DUPLICATE_ID';
  }
  if (hasDuplicate(valuesFor(screens, 'route'))) {
    return 'FRESHNESS_OPERATIONS_DUPLICATE_ROUTE';
  }
  if (
    !jsonEqual(value['screen'], expected.screen) ||
    !jsonEqual(value['catalogScreens'], expected.catalogScreens) ||
    !jsonEqual(value['canonicalScreenOrder'], expected.canonicalScreenOrder) ||
    !jsonEqual(value['components'], expected.components) ||
    !jsonEqual(value['componentOwnership'], expected.componentOwnership)
  ) {
    return 'FRESHNESS_OPERATIONS_METADATA_INVALID';
  }
  if (
    !jsonEqual(value['dataSlots'], expected.dataSlots) ||
    !jsonEqual(value['dependencies'], expected.dependencies)
  ) {
    return 'FRESHNESS_OPERATIONS_STATE_INVALID';
  }
  if (!jsonEqual(value['accessibility'], expected.accessibility)) {
    return 'FRESHNESS_OPERATIONS_ACCESSIBILITY_INVALID';
  }
  const authorityKeys = [
    'availability',
    'roleInputAccepted',
    'roleMetadataAuthority',
    'routeRegistered',
    'renderEnabled',
    'actions',
    'actionAvailability',
    'effectAvailability',
    'intentAvailability',
    'authority',
    'verification',
    'acceptanceAchieved',
    'storyComplete',
    'productionEligible',
  ] as const;
  if (authorityKeys.some((key) => !jsonEqual(value[key], expected[key]))) {
    return 'FRESHNESS_OPERATIONS_AUTHORITY_INVALID';
  }
  return 'FRESHNESS_OPERATIONS_CANDIDATE_INVALID';
}

export function validateFreshnessOperationsWorkspaceCandidate(
  value: unknown,
): FreshnessOperationsWorkspaceCandidate {
  const clone = cloneStrict(value, 'FRESHNESS_OPERATIONS_CANDIDATE_INVALID');
  if (!isJsonObject(clone)) {
    return reject('FRESHNESS_OPERATIONS_CANDIDATE_INVALID');
  }
  const screen = clone['screen'];
  if (!isJsonObject(screen)) {
    return reject('FRESHNESS_OPERATIONS_CANDIDATE_INVALID');
  }
  const screenId = screen['id'];
  if (
    typeof screenId !== 'string' ||
    !(FRESHNESS_OPERATIONS_SCREEN_IDS as readonly string[]).includes(screenId)
  ) {
    return reject('FRESHNESS_OPERATIONS_SCREEN_UNKNOWN');
  }
  const expected = buildCandidate(screenId as FreshnessOperationsScreenId);
  if (!jsonEqual(clone, expected)) {
    return reject(classifyCandidateFailure(clone, expected));
  }
  return clone as unknown as FreshnessOperationsWorkspaceCandidate;
}

export function createFreshnessOperationsWorkspaceCandidate(
  input: FreshnessOperationsWorkspaceInput,
): FreshnessOperationsWorkspaceCandidate {
  return validateFreshnessOperationsWorkspaceCandidate(buildCandidate(validatedScreenId(input)));
}

export const createFreshnessOperationsWorkspaceModel = createFreshnessOperationsWorkspaceCandidate;
export type FreshnessOperationsWorkspaceModel = FreshnessOperationsWorkspaceCandidate;
