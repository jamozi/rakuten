import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const ANALYTICS_FINANCE_WORKSPACE_CLASSIFICATION =
  'SOURCE_DERIVED_DISABLED_HEADLESS_ANALYTICS_FINANCE_WORKSPACE_CANDIDATE' as const;

export const ANALYTICS_FINANCE_SCREEN_IDS = createJsonValue([
  'ANA-001',
  'ANA-002',
  'ANA-003',
  'FIN-001',
  'FIN-002',
  'FIN-003',
]) as unknown as readonly ['ANA-001', 'ANA-002', 'ANA-003', 'FIN-001', 'FIN-002', 'FIN-003'];

export type AnalyticsFinanceScreenId = (typeof ANALYTICS_FINANCE_SCREEN_IDS)[number];

export type AnalyticsFinanceRole = 'PRODUCT_OWNER' | 'MANAGING_EDITOR' | 'ANALYST' | 'OPERATOR';

export interface AnalyticsFinanceScreenMetadata {
  readonly id: AnalyticsFinanceScreenId;
  readonly name:
    | 'Content Performance'
    | 'Search Performance'
    | 'Affiliate Clicks'
    | '成果Import'
    | 'Reconciliation'
    | 'Unit Economics';
  readonly route:
    | '/admin/analytics/content'
    | '/admin/analytics/search'
    | '/admin/analytics/clicks'
    | '/admin/finance/imports'
    | '/admin/finance/reconciliation/{id}'
    | '/admin/finance/unit-economics';
  readonly area: 'analytics' | 'finance';
  readonly roles: readonly AnalyticsFinanceRole[];
  readonly purpose: string;
  readonly mvp: true;
  readonly criticalAction: false;
  readonly apiDependencies: readonly [];
  readonly designStatus: 'APPROVED_FOR_IMPLEMENTATION';
  readonly implementationStatus: 'NOT_STARTED';
  readonly runtimeVerification: 'NOT_EXECUTED';
  readonly routeRegistered: false;
}

const screenMetadataSource = [
  {
    id: 'ANA-001',
    name: 'Content Performance',
    route: '/admin/analytics/content',
    area: 'analytics',
    roles: ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'ANALYST'],
    purpose: '検索、行動、クリック、品質を記事別に表示',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
    routeRegistered: false,
  },
  {
    id: 'ANA-002',
    name: 'Search Performance',
    route: '/admin/analytics/search',
    area: 'analytics',
    roles: ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'ANALYST'],
    purpose: 'Search Console指標とIntentを表示',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
    routeRegistered: false,
  },
  {
    id: 'ANA-003',
    name: 'Affiliate Clicks',
    route: '/admin/analytics/clicks',
    area: 'analytics',
    roles: ['PRODUCT_OWNER', 'ANALYST'],
    purpose: 'CTA別クリックと計測品質を表示',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
    routeRegistered: false,
  },
  {
    id: 'FIN-001',
    name: '成果Import',
    route: '/admin/finance/imports',
    area: 'finance',
    roles: ['PRODUCT_OWNER', 'ANALYST', 'OPERATOR'],
    purpose: 'CSV Upload、検査、Dry Run、Commit',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
    routeRegistered: false,
  },
  {
    id: 'FIN-002',
    name: 'Reconciliation',
    route: '/admin/finance/reconciliation/{id}',
    area: 'finance',
    roles: ['PRODUCT_OWNER', 'ANALYST'],
    purpose: 'Provider合計とCanonical取込を照合',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
    routeRegistered: false,
  },
  {
    id: 'FIN-003',
    name: 'Unit Economics',
    route: '/admin/finance/unit-economics',
    area: 'finance',
    roles: ['PRODUCT_OWNER', 'ANALYST'],
    purpose: '確定EPC/RPM/貢献利益と帰属Basisを表示',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
    routeRegistered: false,
  },
] as const;

export const ANALYTICS_FINANCE_SCREENS = createJsonValue(
  screenMetadataSource,
) as unknown as readonly AnalyticsFinanceScreenMetadata[];

export const ANALYTICS_FINANCE_WORKSPACE_ERROR_CODES = createJsonValue([
  'ANALYTICS_FINANCE_INPUT_INVALID',
  'ANALYTICS_FINANCE_SCREEN_UNKNOWN',
  'ANALYTICS_FINANCE_CANDIDATE_INVALID',
  'ANALYTICS_FINANCE_DUPLICATE_ID',
  'ANALYTICS_FINANCE_DUPLICATE_ROUTE',
  'ANALYTICS_FINANCE_METADATA_INVALID',
  'ANALYTICS_FINANCE_STATE_INVALID',
  'ANALYTICS_FINANCE_VISIBILITY_INVALID',
  'ANALYTICS_FINANCE_ACCESSIBILITY_INVALID',
  'ANALYTICS_FINANCE_ISOLATION_INVALID',
  'ANALYTICS_FINANCE_AUTHORITY_INVALID',
  'ANALYTICS_FINANCE_PROHIBITED_SURFACE',
]) as unknown as readonly [
  'ANALYTICS_FINANCE_INPUT_INVALID',
  'ANALYTICS_FINANCE_SCREEN_UNKNOWN',
  'ANALYTICS_FINANCE_CANDIDATE_INVALID',
  'ANALYTICS_FINANCE_DUPLICATE_ID',
  'ANALYTICS_FINANCE_DUPLICATE_ROUTE',
  'ANALYTICS_FINANCE_METADATA_INVALID',
  'ANALYTICS_FINANCE_STATE_INVALID',
  'ANALYTICS_FINANCE_VISIBILITY_INVALID',
  'ANALYTICS_FINANCE_ACCESSIBILITY_INVALID',
  'ANALYTICS_FINANCE_ISOLATION_INVALID',
  'ANALYTICS_FINANCE_AUTHORITY_INVALID',
  'ANALYTICS_FINANCE_PROHIBITED_SURFACE',
];

export type AnalyticsFinanceWorkspaceErrorCode =
  (typeof ANALYTICS_FINANCE_WORKSPACE_ERROR_CODES)[number];

export class AnalyticsFinanceWorkspaceError extends TypeError {
  readonly code: AnalyticsFinanceWorkspaceErrorCode;

  constructor(code: AnalyticsFinanceWorkspaceErrorCode) {
    const closedCode = (ANALYTICS_FINANCE_WORKSPACE_ERROR_CODES as readonly unknown[]).includes(
      code,
    )
      ? code
      : 'ANALYTICS_FINANCE_CANDIDATE_INVALID';
    super(closedCode);
    this.name = 'AnalyticsFinanceWorkspaceError';
    this.code = closedCode;
    Object.freeze(this);
  }
}

export interface AnalyticsFinanceWorkspaceInput {
  readonly screenId: AnalyticsFinanceScreenId;
}

export interface AnalyticsFinanceDataSlot {
  readonly status: 'NOT_LOADED' | 'NOT_EVALUATED';
  readonly payload: null | readonly [];
}

export interface AnalyticsFinanceWorkspaceCandidate {
  readonly classification: typeof ANALYTICS_FINANCE_WORKSPACE_CLASSIFICATION;
  readonly storyId: 'ST-1104';
  readonly screen: AnalyticsFinanceScreenMetadata;
  readonly catalogScreens: readonly AnalyticsFinanceScreenMetadata[];
  readonly canonicalScreenOrder: typeof ANALYTICS_FINANCE_SCREEN_IDS;
  readonly availability: 'DISABLED';
  readonly roleInputAccepted: false;
  readonly roleMetadataAuthority: 'DISPLAY_ONLY_NOT_AUTHENTICATION_OR_AUTHORIZATION';
  readonly components: readonly [];
  readonly componentOwnership: 'NOT_INFERRED';
  readonly dashboards: readonly [];
  readonly dashboardOwnership: 'NOT_INFERRED';
  readonly routeRegistered: false;
  readonly renderEnabled: false;
  readonly dataSlots: {
    readonly kpiValues: AnalyticsFinanceDataSlot;
    readonly attributionBasis: AnalyticsFinanceDataSlot;
    readonly freshness: AnalyticsFinanceDataSlot;
    readonly dataQuality: AnalyticsFinanceDataSlot;
    readonly imports: AnalyticsFinanceDataSlot;
    readonly reconciliation: AnalyticsFinanceDataSlot;
    readonly unitEconomics: AnalyticsFinanceDataSlot;
  };
  readonly visibilityRequirements: {
    readonly requirementsOnly: true;
    readonly rendered: false;
    readonly verified: false;
    readonly dataSourceRequired: true;
    readonly periodRequired: true;
    readonly freshnessRequired: true;
    readonly basisRequired: true;
    readonly qualityRequired: true;
    readonly unknownRequired: true;
    readonly unknownAsZeroAllowed: false;
    readonly unknownAsEmptyAllowed: false;
    readonly unknownAsGuessAllowed: false;
  };
  readonly dependencies: {
    readonly adminFoundation: {
      readonly storyId: 'ST-1101';
      readonly status: 'DISABLED_HEADLESS';
      readonly routeAuthority: false;
      readonly payload: null;
    };
    readonly kpiReadModels: {
      readonly storyId: 'ST-1205';
      readonly status: 'REFERENCE_PLAN_ONLY';
      readonly decision: 'NOT_READY';
      readonly definitionCount: 30;
      readonly calculationCount: 0;
      readonly verifiedCount: 0;
      readonly valuesAvailable: false;
      readonly payload: null;
    };
    readonly unitEconomics: {
      readonly storyId: 'ST-1304';
      readonly status: 'UNAVAILABLE';
      readonly openDecisions: readonly ['OD-005', 'OD-009'];
      readonly laborCostState: 'UNKNOWN';
      readonly laborCostValue: null;
      readonly unknownLaborAsZeroAllowed: false;
      readonly payload: null;
    };
    readonly revenueReport: {
      readonly openDecision: 'OD-003';
      readonly status: 'SYNTHETIC_ONLY_REAL_ATTRIBUTION_UNVERIFIED';
      readonly payload: null;
    };
    readonly analyticsConsent: {
      readonly openDecision: 'OD-012';
      readonly status: 'NONESSENTIAL_TRACKING_DISABLED';
      readonly payload: null;
    };
    readonly retention: {
      readonly openDecision: 'OD-014';
      readonly status: 'MINIMAL_COLLECTION_AUTO_DELETION_DISABLED';
      readonly payload: null;
    };
    readonly liveProviders: {
      readonly openDecision: 'OD-015';
      readonly status: 'RECORDED_FIXTURES_ONLY';
      readonly payload: null;
    };
  };
  readonly importBoundary: {
    readonly workflowId: 'UI-WF-008';
    readonly referenceOnly: true;
    readonly implementationStatus: 'NOT_STARTED';
    readonly runtimeVerification: 'NOT_EXECUTED';
    readonly fileAccepted: false;
    readonly securityScanExecuted: false;
    readonly schemaDetectionExecuted: false;
    readonly dryRunExecuted: false;
    readonly reconciliationExecuted: false;
    readonly humanConfirmationEstablished: false;
    readonly commitExecuted: false;
    readonly formulaDefenseVerified: false;
    readonly duplicatePreventionVerified: false;
    readonly estimatedAttributionOfficialized: false;
  };
  readonly financeIsolation: {
    readonly dataClass: 'CONFIDENTIAL';
    readonly publicExposure: false;
    readonly publicProjectionEnabled: false;
    readonly editorialRecommendationInput: false;
    readonly financialValuesPresent: false;
    readonly providerRowsPresent: false;
    readonly personalDataPresent: false;
    readonly secretsPresent: false;
  };
  readonly actions: readonly [];
  readonly actionAvailability: 'UNAVAILABLE';
  readonly effectAvailability: 'UNAVAILABLE';
  readonly intentAvailability: 'UNAVAILABLE';
  readonly csvCommitPolicy: {
    readonly criticalActionRequirement: true;
    readonly available: false;
    readonly authenticationEstablished: false;
    readonly authorizationGranted: false;
    readonly mfaEstablished: false;
    readonly stepUpEstablished: false;
    readonly reasonRecorded: false;
    readonly idempotencyEstablished: false;
    readonly auditRecorded: false;
  };
  readonly accessibility: {
    readonly requirementsOnly: true;
    readonly rendered: false;
    readonly verified: false;
    readonly statusPresentation: {
      readonly textRequired: true;
      readonly iconRequired: true;
      readonly colorOnly: false;
      readonly rendered: false;
      readonly verified: false;
    };
    readonly tableSemantics: {
      readonly captionRequired: true;
      readonly headersRequired: true;
      readonly scopeRequired: true;
      readonly rendered: false;
      readonly verified: false;
    };
    readonly chartAlternative: {
      readonly tableOrTextSummaryRequired: true;
      readonly rendered: false;
      readonly verified: false;
    };
    readonly financialActionCorrection: {
      readonly confirmationOrCorrectionRequired: true;
      readonly rendered: false;
      readonly verified: false;
    };
    readonly loadingSuccessFailureAnnouncement: {
      readonly required: true;
      readonly rendered: false;
      readonly verified: false;
    };
  };
  readonly authority: {
    readonly authenticationEstablished: false;
    readonly authorizationGranted: false;
    readonly mfaEstablished: false;
    readonly stepUpEstablished: false;
    readonly mutationEnabled: false;
    readonly fileIntakeEnabled: false;
    readonly networkEnabled: false;
    readonly persistenceEnabled: false;
    readonly runtimeEnabled: false;
    readonly externalActionEnabled: false;
    readonly telemetryEnabled: false;
    readonly publicationAuthorized: false;
    readonly releaseAuthorized: false;
    readonly productionAuthorized: false;
  };
  readonly verification: {
    readonly runtime: 'NOT_VERIFIED';
    readonly accessibility: 'NOT_VERIFIED';
    readonly formal: 'NOT_EXECUTED';
    readonly live: 'NOT_EXECUTED';
    readonly browser: 'NOT_EXECUTED';
    readonly staging: 'NOT_EXECUTED';
    readonly release: 'NOT_EXECUTED';
    readonly publication: 'NOT_EXECUTED';
    readonly production: 'NOT_EXECUTED';
    readonly TST_022: 'NOT_EXECUTED';
    readonly TST_024: 'NOT_EXECUTED';
    readonly TST_030: 'NOT_EXECUTED';
  };
  readonly acceptanceAchieved: false;
  readonly storyComplete: false;
  readonly productionEligible: false;
}

function reject(code: AnalyticsFinanceWorkspaceErrorCode): never {
  throw new AnalyticsFinanceWorkspaceError(code);
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

function cloneStrict(value: unknown, code: AnalyticsFinanceWorkspaceErrorCode): JsonValue {
  if (!isStrictPlainTree(value)) {
    return reject(code);
  }
  try {
    return createJsonValue(value);
  } catch {
    return reject(code);
  }
}

function validatedScreenId(input: AnalyticsFinanceWorkspaceInput): AnalyticsFinanceScreenId {
  const value = cloneStrict(input, 'ANALYTICS_FINANCE_INPUT_INVALID');
  if (!isJsonObject(value)) {
    return reject('ANALYTICS_FINANCE_INPUT_INVALID');
  }
  const keys = Object.keys(value);
  if (keys.length !== 1 || keys[0] !== 'screenId') {
    return reject('ANALYTICS_FINANCE_INPUT_INVALID');
  }
  const screenId = value['screenId'];
  if (typeof screenId !== 'string') {
    return reject('ANALYTICS_FINANCE_INPUT_INVALID');
  }
  if (!(ANALYTICS_FINANCE_SCREEN_IDS as readonly string[]).includes(screenId)) {
    return reject('ANALYTICS_FINANCE_SCREEN_UNKNOWN');
  }
  return screenId as AnalyticsFinanceScreenId;
}

function buildCandidate(screenId: AnalyticsFinanceScreenId): AnalyticsFinanceWorkspaceCandidate {
  const screen = ANALYTICS_FINANCE_SCREENS.find((item) => item.id === screenId);
  if (screen === undefined) {
    return reject('ANALYTICS_FINANCE_SCREEN_UNKNOWN');
  }
  return createJsonValue({
    classification: ANALYTICS_FINANCE_WORKSPACE_CLASSIFICATION,
    storyId: 'ST-1104',
    screen,
    catalogScreens: ANALYTICS_FINANCE_SCREENS,
    canonicalScreenOrder: ANALYTICS_FINANCE_SCREEN_IDS,
    availability: 'DISABLED',
    roleInputAccepted: false,
    roleMetadataAuthority: 'DISPLAY_ONLY_NOT_AUTHENTICATION_OR_AUTHORIZATION',
    components: [],
    componentOwnership: 'NOT_INFERRED',
    dashboards: [],
    dashboardOwnership: 'NOT_INFERRED',
    routeRegistered: false,
    renderEnabled: false,
    dataSlots: {
      kpiValues: { status: 'NOT_LOADED', payload: [] },
      attributionBasis: { status: 'NOT_EVALUATED', payload: null },
      freshness: { status: 'NOT_EVALUATED', payload: null },
      dataQuality: { status: 'NOT_EVALUATED', payload: null },
      imports: { status: 'NOT_LOADED', payload: [] },
      reconciliation: { status: 'NOT_EVALUATED', payload: null },
      unitEconomics: { status: 'NOT_EVALUATED', payload: null },
    },
    visibilityRequirements: {
      requirementsOnly: true,
      rendered: false,
      verified: false,
      dataSourceRequired: true,
      periodRequired: true,
      freshnessRequired: true,
      basisRequired: true,
      qualityRequired: true,
      unknownRequired: true,
      unknownAsZeroAllowed: false,
      unknownAsEmptyAllowed: false,
      unknownAsGuessAllowed: false,
    },
    dependencies: {
      adminFoundation: {
        storyId: 'ST-1101',
        status: 'DISABLED_HEADLESS',
        routeAuthority: false,
        payload: null,
      },
      kpiReadModels: {
        storyId: 'ST-1205',
        status: 'REFERENCE_PLAN_ONLY',
        decision: 'NOT_READY',
        definitionCount: 30,
        calculationCount: 0,
        verifiedCount: 0,
        valuesAvailable: false,
        payload: null,
      },
      unitEconomics: {
        storyId: 'ST-1304',
        status: 'UNAVAILABLE',
        openDecisions: ['OD-005', 'OD-009'],
        laborCostState: 'UNKNOWN',
        laborCostValue: null,
        unknownLaborAsZeroAllowed: false,
        payload: null,
      },
      revenueReport: {
        openDecision: 'OD-003',
        status: 'SYNTHETIC_ONLY_REAL_ATTRIBUTION_UNVERIFIED',
        payload: null,
      },
      analyticsConsent: {
        openDecision: 'OD-012',
        status: 'NONESSENTIAL_TRACKING_DISABLED',
        payload: null,
      },
      retention: {
        openDecision: 'OD-014',
        status: 'MINIMAL_COLLECTION_AUTO_DELETION_DISABLED',
        payload: null,
      },
      liveProviders: {
        openDecision: 'OD-015',
        status: 'RECORDED_FIXTURES_ONLY',
        payload: null,
      },
    },
    importBoundary: {
      workflowId: 'UI-WF-008',
      referenceOnly: true,
      implementationStatus: 'NOT_STARTED',
      runtimeVerification: 'NOT_EXECUTED',
      fileAccepted: false,
      securityScanExecuted: false,
      schemaDetectionExecuted: false,
      dryRunExecuted: false,
      reconciliationExecuted: false,
      humanConfirmationEstablished: false,
      commitExecuted: false,
      formulaDefenseVerified: false,
      duplicatePreventionVerified: false,
      estimatedAttributionOfficialized: false,
    },
    financeIsolation: {
      dataClass: 'CONFIDENTIAL',
      publicExposure: false,
      publicProjectionEnabled: false,
      editorialRecommendationInput: false,
      financialValuesPresent: false,
      providerRowsPresent: false,
      personalDataPresent: false,
      secretsPresent: false,
    },
    actions: [],
    actionAvailability: 'UNAVAILABLE',
    effectAvailability: 'UNAVAILABLE',
    intentAvailability: 'UNAVAILABLE',
    csvCommitPolicy: {
      criticalActionRequirement: true,
      available: false,
      authenticationEstablished: false,
      authorizationGranted: false,
      mfaEstablished: false,
      stepUpEstablished: false,
      reasonRecorded: false,
      idempotencyEstablished: false,
      auditRecorded: false,
    },
    accessibility: {
      requirementsOnly: true,
      rendered: false,
      verified: false,
      statusPresentation: {
        textRequired: true,
        iconRequired: true,
        colorOnly: false,
        rendered: false,
        verified: false,
      },
      tableSemantics: {
        captionRequired: true,
        headersRequired: true,
        scopeRequired: true,
        rendered: false,
        verified: false,
      },
      chartAlternative: {
        tableOrTextSummaryRequired: true,
        rendered: false,
        verified: false,
      },
      financialActionCorrection: {
        confirmationOrCorrectionRequired: true,
        rendered: false,
        verified: false,
      },
      loadingSuccessFailureAnnouncement: {
        required: true,
        rendered: false,
        verified: false,
      },
    },
    authority: {
      authenticationEstablished: false,
      authorizationGranted: false,
      mfaEstablished: false,
      stepUpEstablished: false,
      mutationEnabled: false,
      fileIntakeEnabled: false,
      networkEnabled: false,
      persistenceEnabled: false,
      runtimeEnabled: false,
      externalActionEnabled: false,
      telemetryEnabled: false,
      publicationAuthorized: false,
      releaseAuthorized: false,
      productionAuthorized: false,
    },
    verification: {
      runtime: 'NOT_VERIFIED',
      accessibility: 'NOT_VERIFIED',
      formal: 'NOT_EXECUTED',
      live: 'NOT_EXECUTED',
      browser: 'NOT_EXECUTED',
      staging: 'NOT_EXECUTED',
      release: 'NOT_EXECUTED',
      publication: 'NOT_EXECUTED',
      production: 'NOT_EXECUTED',
      TST_022: 'NOT_EXECUTED',
      TST_024: 'NOT_EXECUTED',
      TST_030: 'NOT_EXECUTED',
    },
    acceptanceAchieved: false,
    storyComplete: false,
    productionEligible: false,
  }) as unknown as AnalyticsFinanceWorkspaceCandidate;
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
  'dashboardid',
  'dashboardids',
  'dashboardowner',
  'dashboardownershipmap',
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
  'filebytes',
  'csvrows',
  'financialamount',
  'kpivalue',
  'formula',
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
  expected: AnalyticsFinanceWorkspaceCandidate,
): AnalyticsFinanceWorkspaceErrorCode {
  if (hasProhibitedSurface(value)) {
    return 'ANALYTICS_FINANCE_PROHIBITED_SURFACE';
  }
  const screens = recordArray(value['catalogScreens']);
  if (hasDuplicate(valuesFor(screens, 'id'))) {
    return 'ANALYTICS_FINANCE_DUPLICATE_ID';
  }
  if (hasDuplicate(valuesFor(screens, 'route'))) {
    return 'ANALYTICS_FINANCE_DUPLICATE_ROUTE';
  }
  if (
    !jsonEqual(value['screen'], expected.screen) ||
    !jsonEqual(value['catalogScreens'], expected.catalogScreens) ||
    !jsonEqual(value['canonicalScreenOrder'], expected.canonicalScreenOrder) ||
    !jsonEqual(value['components'], expected.components) ||
    !jsonEqual(value['componentOwnership'], expected.componentOwnership) ||
    !jsonEqual(value['dashboards'], expected.dashboards) ||
    !jsonEqual(value['dashboardOwnership'], expected.dashboardOwnership)
  ) {
    return 'ANALYTICS_FINANCE_METADATA_INVALID';
  }
  if (
    !jsonEqual(value['dataSlots'], expected.dataSlots) ||
    !jsonEqual(value['dependencies'], expected.dependencies) ||
    !jsonEqual(value['importBoundary'], expected.importBoundary)
  ) {
    return 'ANALYTICS_FINANCE_STATE_INVALID';
  }
  if (!jsonEqual(value['visibilityRequirements'], expected.visibilityRequirements)) {
    return 'ANALYTICS_FINANCE_VISIBILITY_INVALID';
  }
  if (!jsonEqual(value['accessibility'], expected.accessibility)) {
    return 'ANALYTICS_FINANCE_ACCESSIBILITY_INVALID';
  }
  if (!jsonEqual(value['financeIsolation'], expected.financeIsolation)) {
    return 'ANALYTICS_FINANCE_ISOLATION_INVALID';
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
    'csvCommitPolicy',
    'authority',
    'verification',
    'acceptanceAchieved',
    'storyComplete',
    'productionEligible',
  ] as const;
  if (authorityKeys.some((key) => !jsonEqual(value[key], expected[key]))) {
    return 'ANALYTICS_FINANCE_AUTHORITY_INVALID';
  }
  return 'ANALYTICS_FINANCE_CANDIDATE_INVALID';
}

export function validateAnalyticsFinanceWorkspaceCandidate(
  value: unknown,
): AnalyticsFinanceWorkspaceCandidate {
  const clone = cloneStrict(value, 'ANALYTICS_FINANCE_CANDIDATE_INVALID');
  if (!isJsonObject(clone)) {
    return reject('ANALYTICS_FINANCE_CANDIDATE_INVALID');
  }
  const screen = clone['screen'];
  if (!isJsonObject(screen)) {
    return reject('ANALYTICS_FINANCE_CANDIDATE_INVALID');
  }
  const screenId = screen['id'];
  if (
    typeof screenId !== 'string' ||
    !(ANALYTICS_FINANCE_SCREEN_IDS as readonly string[]).includes(screenId)
  ) {
    return reject('ANALYTICS_FINANCE_SCREEN_UNKNOWN');
  }
  const expected = buildCandidate(screenId as AnalyticsFinanceScreenId);
  if (!jsonEqual(clone, expected)) {
    return reject(classifyCandidateFailure(clone, expected));
  }
  return clone as unknown as AnalyticsFinanceWorkspaceCandidate;
}

export function createAnalyticsFinanceWorkspaceCandidate(
  input: AnalyticsFinanceWorkspaceInput,
): AnalyticsFinanceWorkspaceCandidate {
  return validateAnalyticsFinanceWorkspaceCandidate(buildCandidate(validatedScreenId(input)));
}

export const createAnalyticsFinanceWorkspaceModel = createAnalyticsFinanceWorkspaceCandidate;
export type AnalyticsFinanceWorkspaceModel = AnalyticsFinanceWorkspaceCandidate;
