import { createJsonValue } from './serializable.ts';

export type AiGovernanceRole = 'PRODUCT_OWNER' | 'MANAGING_EDITOR' | 'SECURITY_AUDITOR';

export interface AiGovernanceScreenMetadata {
  readonly id: 'GOV-001';
  readonly name: 'AI Governance';
  readonly route: '/admin/governance/ai';
  readonly area: 'governance';
  readonly roles: readonly AiGovernanceRole[];
  readonly purpose: 'Task/Prompt/Route/Evaluation/Releaseを表示';
  readonly storyObjective: 'Task/Prompt/Route/Eval/Costを表示';
  readonly mvp: true;
  readonly criticalAction: false;
  readonly apiDependencies: readonly [];
  readonly designStatus: 'APPROVED_FOR_IMPLEMENTATION';
  readonly implementationStatus: 'NOT_STARTED';
  readonly runtimeVerification: 'NOT_EXECUTED';
}

export const AI_GOVERNANCE_SCREEN = createJsonValue({
  id: 'GOV-001',
  name: 'AI Governance',
  route: '/admin/governance/ai',
  area: 'governance',
  roles: ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'SECURITY_AUDITOR'],
  purpose: 'Task/Prompt/Route/Evaluation/Releaseを表示',
  storyObjective: 'Task/Prompt/Route/Eval/Costを表示',
  mvp: true,
  criticalAction: false,
  apiDependencies: [],
  designStatus: 'APPROVED_FOR_IMPLEMENTATION',
  implementationStatus: 'NOT_STARTED',
  runtimeVerification: 'NOT_EXECUTED',
}) as unknown as AiGovernanceScreenMetadata;

export const AI_GOVERNANCE_SECTION_IDS = createJsonValue([
  'TASK',
  'PROMPT',
  'ROUTE',
  'EVALUATION',
  'RELEASE',
  'COST',
]) as unknown as readonly ['TASK', 'PROMPT', 'ROUTE', 'EVALUATION', 'RELEASE', 'COST'];

export type AiGovernanceSectionId = (typeof AI_GOVERNANCE_SECTION_IDS)[number];

export interface AiGovernanceSection {
  readonly id: AiGovernanceSectionId;
  readonly label: 'Task' | 'Prompt' | 'Route' | 'Evaluation' | 'Release' | 'Cost';
  readonly mode: 'READ_ONLY';
  readonly status: 'NOT_LOADED';
  readonly records: readonly [];
  readonly recordCount: null;
  readonly availableCount: null;
  readonly selectedRecordId: null;
  readonly actions: readonly [];
}

const sectionSource = [
  { id: 'TASK', label: 'Task' },
  { id: 'PROMPT', label: 'Prompt' },
  { id: 'ROUTE', label: 'Route' },
  { id: 'EVALUATION', label: 'Evaluation' },
  { id: 'RELEASE', label: 'Release' },
  { id: 'COST', label: 'Cost' },
].map(({ id, label }) => ({
  id,
  label,
  mode: 'READ_ONLY',
  status: 'NOT_LOADED',
  records: [],
  recordCount: null,
  availableCount: null,
  selectedRecordId: null,
  actions: [],
}));

export const AI_GOVERNANCE_SECTIONS = createJsonValue(
  sectionSource,
) as unknown as readonly AiGovernanceSection[];

export interface AiGovernanceSourceArtifact {
  readonly path: string;
  readonly sha256: string;
}

export interface AiGovernanceSourceBinding {
  readonly storyId: 'ST-0706' | 'ST-0707' | 'ST-1101';
  readonly commit: string;
  readonly artifacts: readonly AiGovernanceSourceArtifact[];
  readonly semantics: Readonly<Record<string, unknown>>;
}

const sourceBindingsSource = [
  {
    storyId: 'ST-0706',
    commit: 'fe867f85c68ea661b055f4edd32ef6fbc600fa68',
    artifacts: [
      {
        path: 'changes/st-0706/README.md',
        sha256: 'cce1c68a0ed60f9a8fdcf63f60b67c45df5a00c1826eb05cab278c35f7127687',
      },
      {
        path: 'python/raos/adapters/recorded_ai_job_orchestration.py',
        sha256: '089b8d3353e2adafe284c03839b2a36dc9a391ab0c060df28bf68dfc9bc38641',
      },
      {
        path: 'python/raos/application/ai/job_orchestration.py',
        sha256: '606744a4920ce1e2a5fe11f9d48a6d65756ebcde6b5f1dbe6cb982adc6005949',
      },
      {
        path: 'python/raos/domain/ai/job_orchestration.py',
        sha256: '5ef0e0d90f5bb07257d4a9d27829647dd07ced443310f9ba5bc6fed8fc7d97c2',
      },
      {
        path: 'python/raos/ports/ai_job_orchestration.py',
        sha256: '6a3a33345d17ca4072c468b0a018d95b9b5f33241bbfe6d97a4ae260b992ff9d',
      },
      {
        path: 'tests/st0706/conftest.py',
        sha256: '3121a41dc54fdc593d9599db864a6fff7efc897df3d4a7cfbafa02e775979b0b',
      },
      {
        path: 'tests/st0706/test_boundaries.py',
        sha256: '2b6916e5190a2d3a8019b21aeccdefb08f04f0f0d3b050b7d40d761fc0eacede',
      },
      {
        path: 'tests/st0706/test_failure_isolation.py',
        sha256: '15396dc093d69143456ecedfed749ab0ac20e73d6f4a6b9d3d8df9fd8e19712a',
      },
      {
        path: 'tests/st0706/test_orchestration.py',
        sha256: 'd15e19bdb2559043d9c74612bde81fba454b31c37acd8d5a00f54fa58718bf52',
      },
    ],
    semantics: {
      classification: 'RECORDED_DEVELOPMENT_METADATA_ONLY_AI_JOB_ORCHESTRATION',
      environment: 'ENV_DEV_ONLY',
      liveProviderIntegration: false,
      jobs: [],
      jobCount: null,
      costs: [],
      costCount: null,
      approvalAvailable: false,
      releaseAvailable: false,
      liveExecution: 'NOT_EXECUTED',
    },
  },
  {
    storyId: 'ST-0707',
    commit: '14f0813c443e22faab81dfce3507aff320831ac1',
    artifacts: [
      {
        path: 'changes/st-0707/README.md',
        sha256: '70feb638a72c33e78d23057a2fa1834d865aa92d07029908169892d34c7d67b7',
      },
      {
        path: 'python/raos/application/ai/evaluation.py',
        sha256: 'c8605b67d66af08940cc9ef416153e55e6ea71a571afe9244d7c4d362852b3c9',
      },
      {
        path: 'python/raos/domain/ai/evaluation.py',
        sha256: 'd17b962c14f278dc8673bf2213b65a71c3a0bb2b76275cbc60919788ecd85b3f',
      },
      {
        path: 'tests/st0707/conftest.py',
        sha256: '6bade20471f8724fe2d131e57d806d1467b54d6467d77b1853e99732b3d94b78',
      },
      {
        path: 'tests/st0707/test_boundaries.py',
        sha256: '5e5a3c2e07711f320ea9df9bcc36b950d1586e1b8a17366ababba3035528aec7',
      },
      {
        path: 'tests/st0707/test_evaluation.py',
        sha256: '3680ff67bf147721d04ab9f50c5d5c10503f7120af70c3a1c2b9ae4a80431340',
      },
      {
        path: 'tests/st0707/test_failure_isolation.py',
        sha256: 'c8444fd85609491bac33a151055a84c8be7cb2571c1a2db1b377100198537633',
      },
    ],
    semantics: {
      classification: 'BOOTSTRAP_SMOKE_ONLY',
      authority: 'NON_AUTHORITATIVE',
      canonicalBootstrapPayloadBound: false,
      lockedHoldout: 'NOT_LOADED',
      humanLabels: 'NOT_OBTAINED',
      judgeCalibration: 'NOT_OBTAINED',
      thresholdEvaluation: 'NOT_PERFORMED',
      formalTst018: 'NOT_EXECUTED',
      formalTst019: 'NOT_EXECUTED',
      reports: [],
      reportCount: null,
      storyAcceptance: false,
      releaseDecision: 'NOT_READY',
      releaseEligible: false,
      productionEligible: false,
      externalActionCount: 0,
      actionCount: 0,
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
      governanceScreenIdsRegistered: [],
      governanceRoutesRegistered: [],
      navigationExecution: 'NOT_EXECUTED',
      renderExecution: 'NOT_EXECUTED',
      backendReauthenticationRequired: true,
      backendReauthorizationRequired: true,
    },
  },
] as const;

export const AI_GOVERNANCE_SOURCE_BINDINGS = createJsonValue(
  sourceBindingsSource,
) as unknown as readonly [
  AiGovernanceSourceBinding,
  AiGovernanceSourceBinding,
  AiGovernanceSourceBinding,
];

export const AI_GOVERNANCE_MODEL_ERROR_CODES = createJsonValue([
  'AI_GOVERNANCE_INPUT_INVALID',
  'AI_GOVERNANCE_SCREEN_UNKNOWN',
]) as unknown as readonly ['AI_GOVERNANCE_INPUT_INVALID', 'AI_GOVERNANCE_SCREEN_UNKNOWN'];

export type AiGovernanceModelErrorCode = (typeof AI_GOVERNANCE_MODEL_ERROR_CODES)[number];

export class AiGovernanceModelError extends TypeError {
  readonly code: AiGovernanceModelErrorCode;

  constructor(code: AiGovernanceModelErrorCode) {
    super(code);
    this.name = 'AiGovernanceModelError';
    this.code = code;
    Object.freeze(this);
  }
}

export interface AiGovernanceWorkspaceInput {
  readonly screenId: 'GOV-001';
}

export interface AiGovernanceWorkspaceModel {
  readonly classification: 'SOURCE_DERIVED_DISABLED_HEADLESS_AI_GOVERNANCE_WORKSPACE_MODEL';
  readonly screen: AiGovernanceScreenMetadata;
  readonly canonicalSectionOrder: readonly AiGovernanceSectionId[];
  readonly sections: readonly AiGovernanceSection[];
  readonly sourceBindings: readonly AiGovernanceSourceBinding[];
  readonly availability: 'DISABLED';
  readonly routeRegistration: 'UNREGISTERED';
  readonly navigation: 'DISABLED';
  readonly rendering: 'DISABLED';
  readonly authentication: 'NOT_EXECUTED';
  readonly authorizationGranted: false;
  readonly dataAccess: 'NOT_EXECUTED';
  readonly dataStatus: 'NOT_LOADED';
  readonly actions: readonly [];
  readonly activation: 'FORBIDDEN';
  readonly approval: 'FORBIDDEN';
  readonly release: 'FORBIDDEN';
  readonly providerAction: 'FORBIDDEN';
  readonly externalAction: 'FORBIDDEN';
  readonly formalTst022: 'NOT_EXECUTED';
  readonly decision: 'NOT_READY';
  readonly productionEligible: false;
}

function reject(code: AiGovernanceModelErrorCode): never {
  throw new AiGovernanceModelError(code);
}

function validateInput(input: AiGovernanceWorkspaceInput): void {
  let value: ReturnType<typeof createJsonValue>;
  try {
    value = createJsonValue(input);
  } catch {
    return reject('AI_GOVERNANCE_INPUT_INVALID');
  }
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return reject('AI_GOVERNANCE_INPUT_INVALID');
  }
  const record = value as Readonly<Record<string, unknown>>;
  const keys = Object.keys(record);
  if (keys.length !== 1 || keys[0] !== 'screenId') {
    return reject('AI_GOVERNANCE_INPUT_INVALID');
  }
  const screenId = record['screenId'];
  if (typeof screenId !== 'string') {
    return reject('AI_GOVERNANCE_INPUT_INVALID');
  }
  if (screenId !== 'GOV-001') {
    return reject('AI_GOVERNANCE_SCREEN_UNKNOWN');
  }
}

export function createAiGovernanceWorkspaceModel(
  input: AiGovernanceWorkspaceInput,
): AiGovernanceWorkspaceModel {
  validateInput(input);
  return createJsonValue({
    classification: 'SOURCE_DERIVED_DISABLED_HEADLESS_AI_GOVERNANCE_WORKSPACE_MODEL',
    screen: AI_GOVERNANCE_SCREEN,
    canonicalSectionOrder: AI_GOVERNANCE_SECTION_IDS,
    sections: AI_GOVERNANCE_SECTIONS,
    sourceBindings: AI_GOVERNANCE_SOURCE_BINDINGS,
    availability: 'DISABLED',
    routeRegistration: 'UNREGISTERED',
    navigation: 'DISABLED',
    rendering: 'DISABLED',
    authentication: 'NOT_EXECUTED',
    authorizationGranted: false,
    dataAccess: 'NOT_EXECUTED',
    dataStatus: 'NOT_LOADED',
    actions: [],
    activation: 'FORBIDDEN',
    approval: 'FORBIDDEN',
    release: 'FORBIDDEN',
    providerAction: 'FORBIDDEN',
    externalAction: 'FORBIDDEN',
    formalTst022: 'NOT_EXECUTED',
    decision: 'NOT_READY',
    productionEligible: false,
  }) as unknown as AiGovernanceWorkspaceModel;
}
