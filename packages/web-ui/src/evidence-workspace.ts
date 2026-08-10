import { createJsonValue } from './serializable.ts';

export const EVIDENCE_WORKSPACE_SCREEN_IDS = createJsonValue([
  'EVD-001',
  'EVD-002',
  'EVD-003',
  'EVD-004',
]) as unknown as readonly ['EVD-001', 'EVD-002', 'EVD-003', 'EVD-004'];

export type EvidenceWorkspaceScreenId = (typeof EVIDENCE_WORKSPACE_SCREEN_IDS)[number];

export type EvidenceWorkspaceRole = 'MANAGING_EDITOR' | 'EDITOR' | 'REVIEWER' | 'ANALYST';

export interface EvidenceWorkspaceScreenMetadata {
  readonly id: EvidenceWorkspaceScreenId;
  readonly name: string;
  readonly route: string;
  readonly area: 'evidence';
  readonly roles: readonly EvidenceWorkspaceRole[];
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
    id: 'EVD-001',
    name: 'Source Packet一覧',
    route: '/admin/evidence/source-packets',
    area: 'evidence',
    roles: ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
    purpose: '生成に使う承認済み情報束を管理',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'EVD-002',
    name: 'Source Packet詳細',
    route: '/admin/evidence/source-packets/{id}',
    area: 'evidence',
    roles: ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
    purpose: 'Fact、Conflict、Freshness、Coverageを確認',
    mvp: true,
    criticalAction: true,
    apiDependencies: ['SourcePacket', 'Fact'],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'EVD-003',
    name: 'Fact Explorer',
    route: '/admin/evidence/facts',
    area: 'evidence',
    roles: ['EDITOR', 'REVIEWER', 'ANALYST'],
    purpose: 'FactをSource/対象/日時で検索',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'EVD-004',
    name: 'Evidence Conflict Queue',
    route: '/admin/evidence/conflicts',
    area: 'evidence',
    roles: ['MANAGING_EDITOR', 'EDITOR', 'REVIEWER'],
    purpose: '矛盾Factを解決またはUnknown化',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
] as const;

export const EVIDENCE_WORKSPACE_SCREENS = createJsonValue(
  screenMetadataSource,
) as unknown as readonly [
  EvidenceWorkspaceScreenMetadata,
  EvidenceWorkspaceScreenMetadata,
  EvidenceWorkspaceScreenMetadata,
  EvidenceWorkspaceScreenMetadata,
];

export interface EvidenceWorkspaceSourceArtifact {
  readonly path: string;
  readonly sha256: string;
}

export interface EvidenceWorkspaceSourceBinding {
  readonly storyId: 'ST-1101' | 'ST-0604' | 'ST-0605';
  readonly commit: string;
  readonly artifacts: readonly EvidenceWorkspaceSourceArtifact[];
  readonly semantics: Readonly<Record<string, unknown>>;
}

const sourceBindingsSource = [
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
      evidenceScreenIdsRegistered: [],
      evidenceRoutesRegistered: [],
      navigationExecution: 'NOT_EXECUTED',
      renderExecution: 'NOT_EXECUTED',
      backendReauthenticationRequired: true,
      backendReauthorizationRequired: true,
    },
  },
  {
    storyId: 'ST-0604',
    commit: '24e9640f7fa2b681ea40bb539837e40403928ec8',
    artifacts: [
      {
        path: 'changes/st-0604/README.md',
        sha256: '5165b09e9049709005a4e2965ca2fb07e01172b4ef3e550892742fafc3e101c8',
      },
      {
        path: 'changes/st-0604/contracts/source-packet-lifecycle-reference-plan.v1.yaml',
        sha256: 'df184e56224586ccb399da2f782e7a6a4fa202f4d9934be240be61dc75f1fb74',
      },
      {
        path: 'changes/st-0604/generated/source-packet-lifecycle-reference-plan.v1.json',
        sha256: '92a65884534f2a9a1c9fe10473d6e85ecdf1308531518d97c768bc5ede7a4f0c',
      },
      {
        path: 'changes/st-0604/manifest.yaml',
        sha256: '07b399132fa15ce658931393dc56c7c11070152c1f7e1a1034783b230a0e170d',
      },
      {
        path: 'scripts/build_st0604_source_packet_lifecycle_reference_plan.py',
        sha256: 'f5e14432f9369e9ef82e4d2062480f11f6db3ba017bd38eeee988df622bf18c6',
      },
      {
        path: 'tests/st0604/conftest.py',
        sha256: 'd53440253de34f65e95f9668ac2c8bd3c55855797f99723d848613bd1d3fc04a',
      },
      {
        path: 'tests/st0604/test_contract.py',
        sha256: '68c3fad0196b6fc353dd354c172d32dcc64106474754a54665f362a51b415462',
      },
      {
        path: 'tests/st0604/test_generation.py',
        sha256: '5ed32f62c06924f3f6931fb827a6c68dc4ffcbd415ddc6b8ece54c66e93a9cca',
      },
      {
        path: 'tests/st0604/test_negative_cases.py',
        sha256: '143ea1cf8f9b5558f98c521909be7c1506e8ad6cbda5534edb01c11ef8afdb45',
      },
    ],
    semantics: {
      decision: 'NOT_READY',
      packets: [],
      versions: [],
      mappings: [],
      approvals: [],
      packetCount: null,
      versionCount: null,
      mappingCount: null,
      approvalCount: null,
      transitionStatus: 'UNAVAILABLE',
      mappingStatus: 'UNAVAILABLE',
      approval: false,
      generationPermitted: false,
    },
  },
  {
    storyId: 'ST-0605',
    commit: '72541b0e855954005231368e48a7811abe4b3ea4',
    artifacts: [
      {
        path: 'changes/st-0605/README.md',
        sha256: 'f5a59ab0542a95987720c5d9ec43ef4355d92cea2b7bafcf8851e510fb98cf4b',
      },
      {
        path: 'changes/st-0605/contracts/claim-evidence-coverage-reference-plan.v1.yaml',
        sha256: '5f0892277351b22ade4bd3f31a68b53239fd57212fc3e81eb1dec7dcddf2c487',
      },
      {
        path: 'changes/st-0605/generated/claim-evidence-coverage-reference-plan.v1.json',
        sha256: 'f573ec26baac6e9e0cb16520861d165f16b6b81d7f77fabd9de1e900afb76a1c',
      },
      {
        path: 'changes/st-0605/manifest.yaml',
        sha256: '7709c2e83db6ee683fe12eb1ebbe978e7bd95de23613131ea18ee4984504a840',
      },
      {
        path: 'scripts/build_st0605_claim_evidence_coverage_reference_plan.py',
        sha256: 'df81ec831d19aeb77a7f40b1cd17ccb594bc834dba43be180e0e4aa548eab7ae',
      },
      {
        path: 'tests/st0605/conftest.py',
        sha256: '089d70a4d95bda6c984646153129cd091126199806136a71e2b8621a01cd1219',
      },
      {
        path: 'tests/st0605/test_contract.py',
        sha256: '4dbfe43f08382899de0bd65901f91dda0831f64298ae3dafedb06fe6f20cff86',
      },
      {
        path: 'tests/st0605/test_generation.py',
        sha256: 'fd305593ae296ec6e763c5b88aa6ee89ff5aa25feb6b4296b3730d3b21f2e9e1',
      },
      {
        path: 'tests/st0605/test_negative_cases.py',
        sha256: '463e15c2ead5deab957cf755a7865e38d92a3fa4fb270a8886c4dc10fe42bd35',
      },
    ],
    semantics: {
      decision: 'NOT_READY',
      claims: [],
      facts: [],
      links: [],
      claimCount: null,
      factCount: null,
      linkCount: null,
      mappingAuthority: 'UNAVAILABLE',
      coverageStatus: 'UNEVALUABLE',
      coverageEvaluable: false,
      majorCoverageRatio: null,
      allVerifiableCoverageRatio: null,
      majorRequirementSatisfied: null,
      allVerifiableRequirementSatisfied: null,
      publicationPermitted: false,
    },
  },
] as const;

export const EVIDENCE_WORKSPACE_SOURCE_BINDINGS = createJsonValue(
  sourceBindingsSource,
) as unknown as readonly [
  EvidenceWorkspaceSourceBinding,
  EvidenceWorkspaceSourceBinding,
  EvidenceWorkspaceSourceBinding,
];

export const EVIDENCE_WORKSPACE_MODEL_ERROR_CODES = createJsonValue([
  'EVIDENCE_WORKSPACE_INPUT_INVALID',
  'EVIDENCE_WORKSPACE_SCREEN_UNKNOWN',
]) as unknown as readonly ['EVIDENCE_WORKSPACE_INPUT_INVALID', 'EVIDENCE_WORKSPACE_SCREEN_UNKNOWN'];

export type EvidenceWorkspaceModelErrorCode = (typeof EVIDENCE_WORKSPACE_MODEL_ERROR_CODES)[number];

export class EvidenceWorkspaceModelError extends TypeError {
  readonly code: EvidenceWorkspaceModelErrorCode;

  constructor(code: EvidenceWorkspaceModelErrorCode) {
    super(code);
    this.name = 'EvidenceWorkspaceModelError';
    this.code = code;
    Object.freeze(this);
  }
}

export interface EvidenceWorkspaceInput {
  readonly screenId: EvidenceWorkspaceScreenId;
}

export interface EvidenceWorkspaceModel {
  readonly classification: 'SOURCE_DERIVED_DISABLED_HEADLESS_EVIDENCE_WORKSPACE_MODEL';
  readonly screen: EvidenceWorkspaceScreenMetadata;
  readonly canonicalScreenOrder: readonly EvidenceWorkspaceScreenId[];
  readonly sourceBindings: readonly EvidenceWorkspaceSourceBinding[];
  readonly availability: 'DISABLED';
  readonly routeRegistration: 'UNREGISTERED';
  readonly navigationEligible: false;
  readonly renderEligible: false;
  readonly authorizationGranted: false;
  readonly backendReauthenticationRequired: true;
  readonly backendReauthorizationRequired: true;
  readonly authentication: 'NOT_EXECUTED';
  readonly dataAccess: 'NOT_EXECUTED';
  readonly commandExecution: 'NOT_EXECUTED';
  readonly effectExecution: 'NOT_EXECUTED';
  readonly dataState: {
    readonly status: 'NOT_LOADED';
    readonly items: readonly [];
    readonly itemCount: null;
  };
  readonly actions: readonly [];
  readonly accessibility: {
    readonly semanticStructureRequired: true;
    readonly keyboardOperabilityRequired: true;
    readonly visibleFocusRequired: true;
    readonly screenReaderLabelsRequired: true;
    readonly errorIdentificationRequired: true;
    readonly contrastComplianceRequired: true;
    readonly browserVerification: 'NOT_EXECUTED';
    readonly automatedAccessibilityVerification: 'NOT_EXECUTED';
    readonly manualKeyboardVerification: 'NOT_EXECUTED';
    readonly screenReaderVerification: 'NOT_EXECUTED';
  };
  readonly decision: 'NOT_READY';
  readonly productionEligible: false;
}

function reject(code: EvidenceWorkspaceModelErrorCode): never {
  throw new EvidenceWorkspaceModelError(code);
}

function validatedScreenId(input: EvidenceWorkspaceInput): EvidenceWorkspaceScreenId {
  let value: ReturnType<typeof createJsonValue>;
  try {
    value = createJsonValue(input);
  } catch {
    return reject('EVIDENCE_WORKSPACE_INPUT_INVALID');
  }
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return reject('EVIDENCE_WORKSPACE_INPUT_INVALID');
  }
  const record = value as Readonly<Record<string, unknown>>;
  const keys = Object.keys(record);
  if (keys.length !== 1 || keys[0] !== 'screenId') {
    return reject('EVIDENCE_WORKSPACE_INPUT_INVALID');
  }
  const screenId = record['screenId'];
  if (typeof screenId !== 'string') {
    return reject('EVIDENCE_WORKSPACE_INPUT_INVALID');
  }
  if (!(EVIDENCE_WORKSPACE_SCREEN_IDS as readonly string[]).includes(screenId)) {
    return reject('EVIDENCE_WORKSPACE_SCREEN_UNKNOWN');
  }
  return screenId as EvidenceWorkspaceScreenId;
}

export function createEvidenceWorkspaceModel(
  input: EvidenceWorkspaceInput,
): EvidenceWorkspaceModel {
  const screenId = validatedScreenId(input);
  const screen = EVIDENCE_WORKSPACE_SCREENS.find((item) => item.id === screenId);
  if (screen === undefined) {
    return reject('EVIDENCE_WORKSPACE_SCREEN_UNKNOWN');
  }
  return createJsonValue({
    classification: 'SOURCE_DERIVED_DISABLED_HEADLESS_EVIDENCE_WORKSPACE_MODEL',
    screen,
    canonicalScreenOrder: EVIDENCE_WORKSPACE_SCREEN_IDS,
    sourceBindings: EVIDENCE_WORKSPACE_SOURCE_BINDINGS,
    availability: 'DISABLED',
    routeRegistration: 'UNREGISTERED',
    navigationEligible: false,
    renderEligible: false,
    authorizationGranted: false,
    backendReauthenticationRequired: true,
    backendReauthorizationRequired: true,
    authentication: 'NOT_EXECUTED',
    dataAccess: 'NOT_EXECUTED',
    commandExecution: 'NOT_EXECUTED',
    effectExecution: 'NOT_EXECUTED',
    dataState: {
      status: 'NOT_LOADED',
      items: [],
      itemCount: null,
    },
    actions: [],
    accessibility: {
      semanticStructureRequired: true,
      keyboardOperabilityRequired: true,
      visibleFocusRequired: true,
      screenReaderLabelsRequired: true,
      errorIdentificationRequired: true,
      contrastComplianceRequired: true,
      browserVerification: 'NOT_EXECUTED',
      automatedAccessibilityVerification: 'NOT_EXECUTED',
      manualKeyboardVerification: 'NOT_EXECUTED',
      screenReaderVerification: 'NOT_EXECUTED',
    },
    decision: 'NOT_READY',
    productionEligible: false,
  }) as unknown as EvidenceWorkspaceModel;
}
