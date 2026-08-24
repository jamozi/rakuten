import {
  ST0606_RECORDED_PROJECTION_V2_JSON,
  ST0606_RECORDED_PROJECTION_V2_SHA256,
} from './evidence-workspace-recorded.v2.ts';
import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const EVIDENCE_WORKSPACE_V2_CLASSIFICATION =
  'LOCAL_EXECUTABLE_RECORDED_SYNTHETIC_EVIDENCE_WORKSPACE_V2' as const;

export const EVIDENCE_WORKSPACE_V2_SCREEN_IDS = createJsonValue([
  'EVD-001',
  'EVD-002',
  'EVD-003',
  'EVD-004',
]) as unknown as readonly ['EVD-001', 'EVD-002', 'EVD-003', 'EVD-004'];

export type EvidenceWorkspaceScreenIdV2 = (typeof EVIDENCE_WORKSPACE_V2_SCREEN_IDS)[number];

export const EVIDENCE_WORKSPACE_V2_ERROR_CODES = createJsonValue([
  'EVIDENCE_WORKSPACE_V2_INPUT_INVALID',
  'EVIDENCE_WORKSPACE_V2_SCREEN_UNKNOWN',
  'EVIDENCE_WORKSPACE_V2_PROJECTION_INVALID',
  'EVIDENCE_WORKSPACE_V2_BINDING_INVALID',
  'EVIDENCE_WORKSPACE_V2_AUTHORITY_INVALID',
  'EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE',
  'EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID',
  'EVIDENCE_WORKSPACE_V2_UNAVAILABLE_INVALID',
  'EVIDENCE_WORKSPACE_V2_PROHIBITED_INPUT',
]) as unknown as readonly [
  'EVIDENCE_WORKSPACE_V2_INPUT_INVALID',
  'EVIDENCE_WORKSPACE_V2_SCREEN_UNKNOWN',
  'EVIDENCE_WORKSPACE_V2_PROJECTION_INVALID',
  'EVIDENCE_WORKSPACE_V2_BINDING_INVALID',
  'EVIDENCE_WORKSPACE_V2_AUTHORITY_INVALID',
  'EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE',
  'EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID',
  'EVIDENCE_WORKSPACE_V2_UNAVAILABLE_INVALID',
  'EVIDENCE_WORKSPACE_V2_PROHIBITED_INPUT',
];

export type EvidenceWorkspaceV2ErrorCode = (typeof EVIDENCE_WORKSPACE_V2_ERROR_CODES)[number];

export class EvidenceWorkspaceV2Error extends TypeError {
  readonly code: EvidenceWorkspaceV2ErrorCode;

  constructor(code: EvidenceWorkspaceV2ErrorCode) {
    const closed = (EVIDENCE_WORKSPACE_V2_ERROR_CODES as readonly unknown[]).includes(code)
      ? code
      : 'EVIDENCE_WORKSPACE_V2_PROJECTION_INVALID';
    super(closed);
    this.name = 'EvidenceWorkspaceV2Error';
    this.code = closed;
    Object.freeze(this);
  }
}

export interface EvidenceWorkspaceV2Input {
  readonly screenId: EvidenceWorkspaceScreenIdV2;
}

export interface EvidenceStatusCueV2 {
  readonly code: string;
  readonly text: string;
  readonly icon: string;
  readonly color_only: false;
}

export interface EvidenceTableColumnV2 {
  readonly id: string;
  readonly label: string;
  readonly scope: 'col';
}

export interface EvidenceTableV2 {
  readonly table_id: string;
  readonly caption: string;
  readonly columns: readonly EvidenceTableColumnV2[];
  readonly row_header_column: string;
  readonly row_header_scope: 'row';
  readonly availability:
    | 'AVAILABLE_RECORDED_SYNTHETIC'
    | 'AVAILABLE_RECORDED_SYNTHETIC_EMPTY'
    | 'UNAVAILABLE_DEPENDENCY';
  readonly row_count: number | null;
  readonly rows: readonly JsonObject[];
  readonly empty_state: EvidenceStatusCueV2 | null;
}

export interface EvidenceSemanticViewV2 {
  readonly document_title: string;
  readonly skip_link: {
    readonly href: string;
    readonly text: string;
  };
  readonly main_landmark: {
    readonly id: string;
    readonly role: 'main';
    readonly labelled_by: string;
  };
  readonly h1: {
    readonly id: string;
    readonly text: string;
    readonly count: 1;
  };
  readonly sections: readonly {
    readonly id: string;
    readonly heading_level: 2;
    readonly labelled: true;
  }[];
  readonly focus_order: readonly string[];
  readonly keyboard_contract: readonly ['Tab', 'Shift+Tab', 'ArrowUp', 'ArrowDown'];
  readonly status_cue: EvidenceStatusCueV2;
  readonly rendered: false;
  readonly browser_verified: false;
}

export interface EvidenceWorkspaceScreenV2 {
  readonly screen_id: EvidenceWorkspaceScreenIdV2;
  readonly name:
    'Source Packet一覧' | 'Source Packet詳細' | 'Fact Explorer' | 'Evidence Conflict Queue';
  readonly route_pattern:
    | '/admin/evidence/source-packets'
    | '/admin/evidence/source-packets/{id}'
    | '/admin/evidence/facts'
    | '/admin/evidence/conflicts';
  readonly roles: readonly string[];
  readonly role_metadata_authority: 'DISPLAY_ONLY_NOT_AUTHENTICATION_OR_AUTHORIZATION';
  readonly components: readonly string[];
  readonly route: {
    readonly registered: false;
    readonly render_enabled: false;
    readonly status: 'UNREGISTERED_AUTH_TRANSPORT_UNRESOLVED';
  };
  readonly semantic_view: EvidenceSemanticViewV2;
  readonly table: EvidenceTableV2;
}

export interface EvidenceAttestationV2 {
  readonly attestation_id: string;
  readonly kind: string;
  readonly owner_story_id: string;
  readonly contract_version: string;
  readonly contract_sha256: string;
  readonly origin: 'RECORDED_SYNTHETIC_ONLY';
  readonly subject_sha256: string;
  readonly input_sha256: string;
  readonly decision_sha256: string;
  readonly validated_at: string;
  readonly valid: true;
}

export interface EvidenceSourceSnapshotV2 {
  readonly source_snapshot_id: string;
  readonly content_sha256: string;
  readonly validation_status: 'VALID';
  readonly acquired_at: string;
  readonly expires_at: string | null;
}

export interface EvidenceSourceV2 {
  readonly source_id: string;
  readonly label: string;
  readonly tier: string;
  readonly origin: string;
  readonly active: boolean;
  readonly snapshot_count: number;
  readonly snapshots: readonly EvidenceSourceSnapshotV2[];
  readonly recorded_freshness: 'CURRENT_AT_RECORDED_EVALUATION' | 'EXPLICIT_CONFLICT';
  readonly live_freshness: 'UNKNOWN';
  readonly live_checked_at: null;
  readonly live_label: string;
  readonly raw_source_body: null;
  readonly source_url: null;
}

export interface EvidenceFactV2 {
  readonly fact_id: string;
  readonly label: string;
  readonly fact_sha256: string;
  readonly subject_identity_sha256: string;
  readonly source_snapshot_id: string;
  readonly source_id: string;
  readonly claim_ids: readonly string[];
  readonly support_types: readonly string[];
  readonly source_access_path_id: string;
  readonly live_freshness: 'UNKNOWN';
  readonly live_freshness_value: null;
}

export interface EvidenceMatrixRowV2 {
  readonly matrix_row_id: string;
  readonly claim_id: string;
  readonly claim_type: string;
  readonly criticality: number;
  readonly fact_id: string;
  readonly support_type: string;
  readonly citation_id: string;
  readonly source_id: string;
  readonly source_snapshot_id: string;
  readonly coverage_state: 'SUPPORTED_RECORDED_SYNTHETIC';
  readonly conflict_state: 'KNOWN_RECORDED_NONE';
  readonly live_freshness: 'UNKNOWN';
  readonly source_access_path_id: string;
}

export interface EvidenceSourceAccessStepV2 {
  readonly position: number;
  readonly code:
    'FOCUS_SOURCE_REFERENCE' | 'FOCUS_SUPPORTING_FACT' | 'INSPECT_RECORDED_SOURCE_METADATA';
  readonly target_ref: string;
}

export interface EvidenceSourceAccessPathV2 {
  readonly path_id: string;
  readonly origin_type: 'FACT' | 'MATRIX_ROW';
  readonly origin_id: string;
  readonly source_id: string;
  readonly maximum_steps: 2;
  readonly step_count: 2;
  readonly steps: readonly EvidenceSourceAccessStepV2[];
  readonly effect: 'NONE';
  readonly dispatch: 'NOT_EXECUTED';
}

export interface EvidenceCoverageFractionV2 {
  readonly evidenced: number;
  readonly total: number;
  readonly [key: string]: JsonValue;
}

export interface EvidenceCoverageReportV2 {
  readonly profile: 'ST0605_COVERAGE_REPORT_V1';
  readonly status: 'PASS';
  readonly report_sha256: string;
  readonly evaluation_input_sha256: string;
  readonly evaluator_version: 'ST0605_CLAIM_EVIDENCE_COVERAGE_V1';
  readonly findings: readonly [];
  readonly major_coverage: EvidenceCoverageFractionV2;
  readonly all_verifiable_coverage: EvidenceCoverageFractionV2;
  readonly major_requirement_satisfied: true;
  readonly all_verifiable_requirement_satisfied: true;
  readonly publication_authorized: false;
  readonly production_eligible: false;
  readonly formal_test_status: 'NOT_EXECUTED';
  readonly live_validation_status: 'NOT_EXECUTED';
  readonly staging_status: 'NOT_EXECUTED';
  readonly release_status: 'NOT_EXECUTED';
  readonly production_status: 'NOT_EXECUTED';
  readonly [key: string]: JsonValue;
}

export interface EvidenceWorkspaceProjectionV2 {
  readonly schema_version: 2;
  readonly story_id: 'ST-0606';
  readonly classification: typeof EVIDENCE_WORKSPACE_V2_CLASSIFICATION;
  readonly local_status: 'LOCAL_IMPLEMENTATION_COMPLETE';
  readonly canonical_status: {
    readonly implementation: 'NOT_STARTED';
    readonly verification: 'NOT_EXECUTED';
  };
  readonly source_mode: 'RECORDED_SYNTHETIC_DEV_CI_ONLY';
  readonly contract_sha256: string;
  readonly fixture_sha256: string;
  readonly source_bindings: readonly {
    readonly uri: string;
    readonly sha256: string;
  }[];
  readonly lifecycle: {
    readonly story_id: 'ST-0604';
    readonly authority: 'CURRENT_LIFECYCLE_SOURCE';
    readonly decision: 'NOT_READY';
    readonly availability: 'UNAVAILABLE';
    readonly packet_count: null;
    readonly version_count: null;
    readonly transition_status: 'UNAVAILABLE';
    readonly mapping_status: 'UNAVAILABLE';
    readonly approval: false;
    readonly generation_permitted: false;
    readonly blockers: readonly string[];
  };
  readonly coverage: {
    readonly authority: 'RECORDED_SYNTHETIC_COVERAGE_ONLY';
    readonly report: EvidenceCoverageReportV2;
    readonly publication_authorized: false;
    readonly production_eligible: false;
    readonly live_state: 'UNKNOWN';
  };
  readonly attestations: readonly EvidenceAttestationV2[];
  readonly sources: readonly EvidenceSourceV2[];
  readonly facts: readonly EvidenceFactV2[];
  readonly conflicts: {
    readonly availability: 'AVAILABLE_RECORDED_SYNTHETIC_EMPTY';
    readonly known_recorded_count: 0;
    readonly live_count: null;
    readonly live_state: 'UNKNOWN';
    readonly rows: readonly [];
  };
  readonly matrix: {
    readonly availability: 'AVAILABLE_RECORDED_SYNTHETIC';
    readonly rows: readonly EvidenceMatrixRowV2[];
  };
  readonly source_access: {
    readonly maximum_deterministic_steps: 2;
    readonly semantics: 'READ_ONLY_FOCUS_PATH_CONTRACT';
    readonly paths: readonly EvidenceSourceAccessPathV2[];
    readonly dispatch: 'NOT_EXECUTED';
  };
  readonly screens: readonly EvidenceWorkspaceScreenV2[];
  readonly unknown_policy: {
    readonly missing: 'UNAVAILABLE';
    readonly unevaluated: 'UNKNOWN';
    readonly conflict: 'EXPLICIT_CONFLICT';
    readonly live_freshness: 'UNKNOWN';
    readonly nullable_value: null;
    readonly unknown_as_zero_allowed: false;
    readonly unknown_as_pass_allowed: false;
    readonly known_recorded_empty_collection_may_be_zero: true;
  };
  readonly editorial_independence: {
    readonly prohibited_input_categories: readonly [
      'AFFILIATE_COMPENSATION',
      'COMMERCIAL_PERFORMANCE',
      'RECOMMENDATION_ORDERING',
    ];
    readonly inputs_present: false;
  };
  readonly authority: {
    readonly route_registration: false;
    readonly rendering: false;
    readonly authentication: false;
    readonly authorization: false;
    readonly backend_data: false;
    readonly network: false;
    readonly user_actions: false;
    readonly mutation: false;
    readonly persistence: false;
    readonly publication: false;
    readonly activation: false;
    readonly staging: false;
    readonly release: false;
    readonly production: false;
    readonly role_metadata_is_authority: false;
  };
  readonly verification: {
    readonly local_owner_check: 'EXECUTED';
    readonly local_model_tests: 'EXECUTED';
    readonly 'TST-022': 'NOT_EXECUTED';
    readonly 'TST-024': 'NOT_EXECUTED';
    readonly browser: 'NOT_EXECUTED';
    readonly live: 'NOT_EXECUTED';
    readonly staging: 'NOT_EXECUTED';
    readonly release: 'NOT_EXECUTED';
    readonly production: 'NOT_EXECUTED';
  };
  readonly formal_acceptance_achieved: false;
  readonly production_eligible: false;
}

export interface EvidenceWorkspaceModelV2 {
  readonly classification: typeof EVIDENCE_WORKSPACE_V2_CLASSIFICATION;
  readonly storyId: 'ST-0606';
  readonly localStatus: 'LOCAL_IMPLEMENTATION_COMPLETE';
  readonly canonicalStatus: EvidenceWorkspaceProjectionV2['canonical_status'];
  readonly projectionSha256: string;
  readonly contractSha256: string;
  readonly fixtureSha256: string;
  readonly sourceMode: 'RECORDED_SYNTHETIC_DEV_CI_ONLY';
  readonly screenOrder: typeof EVIDENCE_WORKSPACE_V2_SCREEN_IDS;
  readonly screen: EvidenceWorkspaceScreenV2;
  readonly lifecycle: EvidenceWorkspaceProjectionV2['lifecycle'];
  readonly coverage: EvidenceWorkspaceProjectionV2['coverage'];
  readonly attestations: readonly EvidenceAttestationV2[];
  readonly sources: readonly EvidenceSourceV2[];
  readonly facts: readonly EvidenceFactV2[];
  readonly conflicts: EvidenceWorkspaceProjectionV2['conflicts'];
  readonly matrix: EvidenceWorkspaceProjectionV2['matrix'];
  readonly sourceAccess: EvidenceWorkspaceProjectionV2['source_access'];
  readonly unknownPolicy: EvidenceWorkspaceProjectionV2['unknown_policy'];
  readonly editorialIndependence: EvidenceWorkspaceProjectionV2['editorial_independence'];
  readonly authority: EvidenceWorkspaceProjectionV2['authority'];
  readonly verification: EvidenceWorkspaceProjectionV2['verification'];
  readonly localImplementationComplete: true;
  readonly formalAcceptanceAchieved: false;
  readonly productionEligible: false;
}

const SHA256 = /^[0-9a-f]{64}$/u;
const expectedScreenIds = ['EVD-001', 'EVD-002', 'EVD-003', 'EVD-004'] as const;
const expectedTopKeys = [
  'schema_version',
  'story_id',
  'classification',
  'local_status',
  'canonical_status',
  'source_mode',
  'contract_sha256',
  'fixture_sha256',
  'source_bindings',
  'lifecycle',
  'coverage',
  'attestations',
  'sources',
  'facts',
  'conflicts',
  'matrix',
  'source_access',
  'screens',
  'unknown_policy',
  'editorial_independence',
  'authority',
  'verification',
  'formal_acceptance_achieved',
  'production_eligible',
] as const;
const expectedAuthorityKeys = [
  'route_registration',
  'rendering',
  'authentication',
  'authorization',
  'backend_data',
  'network',
  'user_actions',
  'mutation',
  'persistence',
  'publication',
  'activation',
  'staging',
  'release',
  'production',
  'role_metadata_is_authority',
] as const;
const expectedAttestationProvenance = [
  'CLAIM_INVENTORY|ST-0605|RAOS-CONTENT-EVIDENCE-001@1.0.0|fbf2d0ad6e7821a0059f9ceeb53d57268031e2e42b4aad988af9a42378aec5ba|3c943f8500bfc18bda0ef93614ca426789fadc9bd361cd1ad64a35b7ccd8b723|eed2c880b83ca8092e1704efc7a718ac1ba88969df249e4c7f03fad1e1d0891d|1c2fbcd02c8eb2624c2f8402f5bbd4df7673b029e4f79fe9ff5074e487dfa1ea',
  'ARTICLE_PACKET_BINDING|ST-0802|RESOURCE-CONTRACTS@0.4|aa53bf68b125821a46c093e653464e7f80e5710e31f6f860251aa8ebc30480c0|dcef9107ebf5a77435bdf63659bd036e7ae4929e4931f8c98ebfa39b131eeb16|0eeac9ea5a6c8e552d6dbd41b655aa31f432b7d74a7f462738066acc12c6121c|1c1c882e2a44e82c0cc6ed5655e9be17eea5929e4cbff639399fd0efc9deee8d',
  'PACKET_APPROVAL_MEMBERSHIP|ST-0604|SOURCE-PACKET-LIFECYCLE-RUNTIME@2.0.0|719f5366eced10c19a16dc11355d92680fb66dfe08bebce5be5251618e79cfbe|5113c184044507308f41d4d80036ca3b352345767aa7297d00d809e50515fef5|d4d0010908959e4f5c26c60db299dccb4ba93f81eaf36f525f61b80c6901c8b2|89dcbf8d4dcf05c6dd9d7dafc259c59bfca7685eef1058a63482811ac90ebfd0',
  'FACT_VALIDATION|ST-0602|FACT-EXTRACTION-VALIDATION-REFERENCE-PLAN@1|c7d7c16ee41a3d3ba5203c9cb091cc6f09fd1556400abb0d42438434d8bea073|e01f09009e0c7fe19d739bb88c935e2c0b3420145cc7a899b7b4acdc39e38431|7a0fe30ffff752e5fc310847d4204d3a0217c3a1f75613adff6439f637f3485e|0de8dd90721173899272d2da2a7a3db3fc4c61d9cc567ff38e0e42341fe960f8',
  'FACT_VALIDATION|ST-0602|FACT-EXTRACTION-VALIDATION-REFERENCE-PLAN@1|c7d7c16ee41a3d3ba5203c9cb091cc6f09fd1556400abb0d42438434d8bea073|b4848396d48d75f702d574a6afdfa1d9a2a4272b4a543e2519ebbc7c1343dd4a|7109d90c64699f4cb749ca784e6d225930742bcaa8bf31bd8b3090defc54f70f|63ffdb62e89c393e33d7395c69fcb1d92625822d8c4d1c5b75e9fc99bafb3b61',
  'IDENTITY_DECISION|ST-0504|PRODUCT-IDENTITY-HUMAN-REVIEW-REFERENCE-PLAN@1|9e73f7e436ab14df75394b2337e853f1dcbf553c16e0f950a8bdb604da685304|3fabe1af282ff9ef5159eb671a0f8f8b3cde53527663bf3ae20ffac5c154bd5c|673dc0b4ce458b85d2cdf058938c23b3f4a511e141501c8d2375c7ba6eb975a2|a6cd1e01ac72ea3408a65fd50c414ab427a4a85a675d52ce4bd136c3e7d3dece',
  'IDENTITY_DECISION|ST-0504|PRODUCT-IDENTITY-HUMAN-REVIEW-REFERENCE-PLAN@1|9e73f7e436ab14df75394b2337e853f1dcbf553c16e0f950a8bdb604da685304|52d959ad30001c3f52d4095114d94360c31613b21d3ecaf6a9ba27929bbe6325|a956e3b2b9c7c55da2e87b69867b55ecce6db8ae174f042145398200502c2c05|20755725c9ba6af26dd2a0a158901a38f95d3e084ec90210b6f232d67e72d296',
  'CONFLICT_CLOSURE|ST-0603|FACT-CONFLICT-REVIEW-REFERENCE-PLAN@1|bca7c63e49be113d7e2b7d15017d22ad6a9b27c59509325b2bbca407081246ef|3eae35b6d938eba8d185c1c37666fcddf58e6532cac3dfec95e7378d94e24f93|55fbbf8f5dc3a9fdb3d6e20d7dd5bb43c82a323775e819509c50208295f8e59f|f74e5ad354197636a6ac2ab2f61838d41c161fc36b67b1cdbbe9922a39958477',
] as const;
const prohibitedKey = /(?:reward|commission|payout|revenue|profit|epc|rpm|ranking|score)/iu;

function reject(code: EvidenceWorkspaceV2ErrorCode): never {
  throw new EvidenceWorkspaceV2Error(code);
}

function record(value: JsonValue, code: EvidenceWorkspaceV2ErrorCode): JsonObject {
  if (value === null || Array.isArray(value) || typeof value !== 'object') {
    return reject(code);
  }
  return value as JsonObject;
}

function array(value: JsonValue, code: EvidenceWorkspaceV2ErrorCode): readonly JsonValue[] {
  if (!Array.isArray(value)) {
    return reject(code);
  }
  return value;
}

function exactKeys(value: JsonObject, expected: readonly string[]): boolean {
  const observed = Object.keys(value);
  return observed.length === expected.length && expected.every((key) => observed.includes(key));
}

function stringField(value: JsonObject, key: string): string {
  const field = value[key];
  if (typeof field !== 'string' || field.length === 0 || field !== field.trim()) {
    return reject('EVIDENCE_WORKSPACE_V2_PROJECTION_INVALID');
  }
  return field;
}

function requireSha(value: JsonObject, key: string): string {
  const field = stringField(value, key);
  if (!SHA256.test(field)) {
    return reject('EVIDENCE_WORKSPACE_V2_BINDING_INVALID');
  }
  return field;
}

function scanProhibitedKeys(value: JsonValue): void {
  if (Array.isArray(value)) {
    for (const item of value) {
      scanProhibitedKeys(item);
    }
    return;
  }
  if (value === null || typeof value !== 'object') {
    return;
  }
  for (const [key, item] of Object.entries(value)) {
    if (prohibitedKey.test(key)) {
      return reject('EVIDENCE_WORKSPACE_V2_PROHIBITED_INPUT');
    }
    scanProhibitedKeys(item);
  }
}

function validateAuthority(value: JsonValue): void {
  const authority = record(value, 'EVIDENCE_WORKSPACE_V2_AUTHORITY_INVALID');
  if (
    !exactKeys(authority, expectedAuthorityKeys) ||
    Object.values(authority).some((entry) => entry !== false)
  ) {
    return reject('EVIDENCE_WORKSPACE_V2_AUTHORITY_INVALID');
  }
}

function validateAttestations(value: JsonValue): void {
  const rows = array(value, 'EVIDENCE_WORKSPACE_V2_BINDING_INVALID');
  if (rows.length !== 8) {
    return reject('EVIDENCE_WORKSPACE_V2_BINDING_INVALID');
  }
  const identities = new Set<string>();
  const provenance: string[] = [];
  for (const valueRow of rows) {
    const row = record(valueRow, 'EVIDENCE_WORKSPACE_V2_BINDING_INVALID');
    const identity = stringField(row, 'attestation_id');
    if (identities.has(identity)) {
      return reject('EVIDENCE_WORKSPACE_V2_BINDING_INVALID');
    }
    identities.add(identity);
    if (
      row['origin'] !== 'RECORDED_SYNTHETIC_ONLY' ||
      row['valid'] !== true ||
      !SHA256.test(stringField(row, 'contract_sha256')) ||
      !SHA256.test(stringField(row, 'subject_sha256')) ||
      !SHA256.test(stringField(row, 'input_sha256')) ||
      !SHA256.test(stringField(row, 'decision_sha256'))
    ) {
      return reject('EVIDENCE_WORKSPACE_V2_BINDING_INVALID');
    }
    stringField(row, 'kind');
    stringField(row, 'owner_story_id');
    stringField(row, 'contract_version');
    provenance.push(
      [
        row['kind'],
        row['owner_story_id'],
        row['contract_version'],
        row['contract_sha256'],
        row['subject_sha256'],
        row['input_sha256'],
        row['decision_sha256'],
      ].join('|'),
    );
  }
  if (provenance.join('\n') !== expectedAttestationProvenance.join('\n')) {
    return reject('EVIDENCE_WORKSPACE_V2_BINDING_INVALID');
  }
}

function validateUnknownPolicy(
  value: JsonValue,
  lifecycleValue: JsonValue,
  conflictsValue: JsonValue,
): void {
  const policy = record(value, 'EVIDENCE_WORKSPACE_V2_UNAVAILABLE_INVALID');
  const lifecycle = record(lifecycleValue, 'EVIDENCE_WORKSPACE_V2_UNAVAILABLE_INVALID');
  const conflicts = record(conflictsValue, 'EVIDENCE_WORKSPACE_V2_UNAVAILABLE_INVALID');
  if (
    policy['missing'] !== 'UNAVAILABLE' ||
    policy['unevaluated'] !== 'UNKNOWN' ||
    policy['conflict'] !== 'EXPLICIT_CONFLICT' ||
    policy['live_freshness'] !== 'UNKNOWN' ||
    policy['nullable_value'] !== null ||
    policy['unknown_as_zero_allowed'] !== false ||
    policy['unknown_as_pass_allowed'] !== false ||
    policy['known_recorded_empty_collection_may_be_zero'] !== true ||
    lifecycle['availability'] !== 'UNAVAILABLE' ||
    lifecycle['packet_count'] !== null ||
    lifecycle['version_count'] !== null ||
    lifecycle['approval'] !== false ||
    lifecycle['generation_permitted'] !== false ||
    conflicts['availability'] !== 'AVAILABLE_RECORDED_SYNTHETIC_EMPTY' ||
    conflicts['known_recorded_count'] !== 0 ||
    conflicts['live_count'] !== null ||
    conflicts['live_state'] !== 'UNKNOWN'
  ) {
    return reject('EVIDENCE_WORKSPACE_V2_UNAVAILABLE_INVALID');
  }
}

function validateSourceAccess(
  accessValue: JsonValue,
  sourcesValue: JsonValue,
  factsValue: JsonValue,
  matrixValue: JsonValue,
): void {
  const access = record(accessValue, 'EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE');
  if (
    access['maximum_deterministic_steps'] !== 2 ||
    access['semantics'] !== 'READ_ONLY_FOCUS_PATH_CONTRACT' ||
    access['dispatch'] !== 'NOT_EXECUTED'
  ) {
    return reject('EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE');
  }
  const sources = array(sourcesValue, 'EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE');
  const sourceIds = new Set(
    sources.map((source) =>
      stringField(record(source, 'EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE'), 'source_id'),
    ),
  );
  const paths = array(access['paths'] ?? null, 'EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE');
  const pathIds = new Set<string>();
  for (const pathValue of paths) {
    const path = record(pathValue, 'EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE');
    const pathId = stringField(path, 'path_id');
    const steps = array(path['steps'] ?? null, 'EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE');
    if (
      pathIds.has(pathId) ||
      path['maximum_steps'] !== 2 ||
      path['step_count'] !== 2 ||
      steps.length !== 2 ||
      path['effect'] !== 'NONE' ||
      path['dispatch'] !== 'NOT_EXECUTED' ||
      !sourceIds.has(stringField(path, 'source_id'))
    ) {
      return reject('EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE');
    }
    pathIds.add(pathId);
    for (const [index, stepValue] of steps.entries()) {
      const step = record(stepValue, 'EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE');
      if (step['position'] !== index + 1) {
        return reject('EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE');
      }
      stringField(step, 'code');
      stringField(step, 'target_ref');
    }
  }
  const facts = array(factsValue, 'EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE');
  const matrix = record(matrixValue, 'EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE');
  const matrixRows = array(matrix['rows'] ?? null, 'EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE');
  for (const rowValue of [...facts, ...matrixRows]) {
    const row = record(rowValue, 'EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE');
    if (!pathIds.has(stringField(row, 'source_access_path_id'))) {
      return reject('EVIDENCE_WORKSPACE_V2_SOURCE_UNREACHABLE');
    }
  }
}

function validateScreens(value: JsonValue): void {
  const screens = array(value, 'EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID');
  if (screens.length !== expectedScreenIds.length) {
    return reject('EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID');
  }
  for (const [index, screenValue] of screens.entries()) {
    const screen = record(screenValue, 'EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID');
    if (screen['screen_id'] !== expectedScreenIds[index]) {
      return reject('EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID');
    }
    const route = record(screen['route'] ?? null, 'EVIDENCE_WORKSPACE_V2_AUTHORITY_INVALID');
    if (
      route['registered'] !== false ||
      route['render_enabled'] !== false ||
      route['status'] !== 'UNREGISTERED_AUTH_TRANSPORT_UNRESOLVED' ||
      screen['role_metadata_authority'] !== 'DISPLAY_ONLY_NOT_AUTHENTICATION_OR_AUTHORIZATION'
    ) {
      return reject('EVIDENCE_WORKSPACE_V2_AUTHORITY_INVALID');
    }
    const semantic = record(
      screen['semantic_view'] ?? null,
      'EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID',
    );
    const main = record(
      semantic['main_landmark'] ?? null,
      'EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID',
    );
    const h1 = record(semantic['h1'] ?? null, 'EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID');
    const skip = record(
      semantic['skip_link'] ?? null,
      'EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID',
    );
    const cue = record(
      semantic['status_cue'] ?? null,
      'EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID',
    );
    if (
      main['role'] !== 'main' ||
      main['labelled_by'] !== h1['id'] ||
      h1['count'] !== 1 ||
      skip['href'] !== `#${String(main['id'])}` ||
      cue['color_only'] !== false ||
      semantic['rendered'] !== false ||
      semantic['browser_verified'] !== false ||
      array(semantic['focus_order'] ?? null, 'EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID').length <
        4 ||
      array(
        semantic['keyboard_contract'] ?? null,
        'EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID',
      ).join('|') !== 'Tab|Shift+Tab|ArrowUp|ArrowDown'
    ) {
      return reject('EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID');
    }
    stringField(cue, 'code');
    stringField(cue, 'text');
    stringField(cue, 'icon');
    const table = record(screen['table'] ?? null, 'EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID');
    stringField(table, 'caption');
    if (table['row_header_scope'] !== 'row') {
      return reject('EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID');
    }
    const columns = array(table['columns'] ?? null, 'EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID');
    if (
      columns.length === 0 ||
      columns.some(
        (column) =>
          record(column, 'EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID')['scope'] !== 'col',
      )
    ) {
      return reject('EVIDENCE_WORKSPACE_V2_ACCESSIBILITY_INVALID');
    }
  }
}

export function validateEvidenceWorkspaceProjectionV2(
  candidate: unknown,
): EvidenceWorkspaceProjectionV2 {
  let frozen: JsonValue;
  try {
    frozen = createJsonValue(candidate);
  } catch {
    return reject('EVIDENCE_WORKSPACE_V2_PROJECTION_INVALID');
  }
  const projection = record(frozen, 'EVIDENCE_WORKSPACE_V2_PROJECTION_INVALID');
  if (
    !exactKeys(projection, expectedTopKeys) ||
    projection['schema_version'] !== 2 ||
    projection['story_id'] !== 'ST-0606' ||
    projection['classification'] !== EVIDENCE_WORKSPACE_V2_CLASSIFICATION ||
    projection['local_status'] !== 'LOCAL_IMPLEMENTATION_COMPLETE' ||
    projection['source_mode'] !== 'RECORDED_SYNTHETIC_DEV_CI_ONLY' ||
    projection['formal_acceptance_achieved'] !== false ||
    projection['production_eligible'] !== false
  ) {
    return reject('EVIDENCE_WORKSPACE_V2_PROJECTION_INVALID');
  }
  requireSha(projection, 'contract_sha256');
  requireSha(projection, 'fixture_sha256');
  scanProhibitedKeys(frozen);
  validateAuthority(projection['authority'] ?? null);
  validateAttestations(projection['attestations'] ?? null);
  validateUnknownPolicy(
    projection['unknown_policy'] ?? null,
    projection['lifecycle'] ?? null,
    projection['conflicts'] ?? null,
  );
  validateSourceAccess(
    projection['source_access'] ?? null,
    projection['sources'] ?? null,
    projection['facts'] ?? null,
    projection['matrix'] ?? null,
  );
  validateScreens(projection['screens'] ?? null);
  const coverage = record(projection['coverage'] ?? null, 'EVIDENCE_WORKSPACE_V2_BINDING_INVALID');
  const report = record(coverage['report'] ?? null, 'EVIDENCE_WORKSPACE_V2_BINDING_INVALID');
  if (
    coverage['authority'] !== 'RECORDED_SYNTHETIC_COVERAGE_ONLY' ||
    coverage['publication_authorized'] !== false ||
    coverage['production_eligible'] !== false ||
    coverage['live_state'] !== 'UNKNOWN' ||
    report['status'] !== 'PASS' ||
    report['report_sha256'] !==
      'dbbd1b02fdc84d17bc058be669c434dc5a5a93cc0274496bdab7bc23a52d5a0d' ||
    report['evaluation_input_sha256'] !==
      '1ee43fc1aecd8d8afd382b2d340f86014809f05d479a74e65a11184813bc5094' ||
    report['publication_authorized'] !== false ||
    report['production_eligible'] !== false ||
    report['live_validation_status'] !== 'NOT_EXECUTED'
  ) {
    return reject('EVIDENCE_WORKSPACE_V2_BINDING_INVALID');
  }
  const independence = record(
    projection['editorial_independence'] ?? null,
    'EVIDENCE_WORKSPACE_V2_PROHIBITED_INPUT',
  );
  if (
    independence['inputs_present'] !== false ||
    array(
      independence['prohibited_input_categories'] ?? null,
      'EVIDENCE_WORKSPACE_V2_PROHIBITED_INPUT',
    ).join('|') !== 'AFFILIATE_COMPENSATION|COMMERCIAL_PERFORMANCE|RECOMMENDATION_ORDERING'
  ) {
    return reject('EVIDENCE_WORKSPACE_V2_PROHIBITED_INPUT');
  }
  return frozen as unknown as EvidenceWorkspaceProjectionV2;
}

function parseRecordedProjection(): EvidenceWorkspaceProjectionV2 {
  if (!SHA256.test(ST0606_RECORDED_PROJECTION_V2_SHA256)) {
    return reject('EVIDENCE_WORKSPACE_V2_BINDING_INVALID');
  }
  let candidate: unknown;
  try {
    candidate = JSON.parse(ST0606_RECORDED_PROJECTION_V2_JSON);
  } catch {
    return reject('EVIDENCE_WORKSPACE_V2_PROJECTION_INVALID');
  }
  return validateEvidenceWorkspaceProjectionV2(candidate);
}

export const ST0606_EVIDENCE_WORKSPACE_RECORDED_V2 = parseRecordedProjection();

function validateInput(input: unknown): EvidenceWorkspaceV2Input {
  let frozen: JsonValue;
  try {
    frozen = createJsonValue(input);
  } catch {
    return reject('EVIDENCE_WORKSPACE_V2_INPUT_INVALID');
  }
  const value = record(frozen, 'EVIDENCE_WORKSPACE_V2_INPUT_INVALID');
  if (!exactKeys(value, ['screenId']) || typeof value['screenId'] !== 'string') {
    return reject('EVIDENCE_WORKSPACE_V2_INPUT_INVALID');
  }
  if (!(expectedScreenIds as readonly string[]).includes(value['screenId'])) {
    return reject('EVIDENCE_WORKSPACE_V2_SCREEN_UNKNOWN');
  }
  return value as unknown as EvidenceWorkspaceV2Input;
}

export function createEvidenceWorkspaceModelV2(input: unknown): EvidenceWorkspaceModelV2 {
  const validated = validateInput(input);
  const projection = ST0606_EVIDENCE_WORKSPACE_RECORDED_V2;
  const screen = projection.screens.find((candidate) => candidate.screen_id === validated.screenId);
  if (screen === undefined) {
    return reject('EVIDENCE_WORKSPACE_V2_SCREEN_UNKNOWN');
  }
  return createJsonValue({
    classification: EVIDENCE_WORKSPACE_V2_CLASSIFICATION,
    storyId: 'ST-0606',
    localStatus: 'LOCAL_IMPLEMENTATION_COMPLETE',
    canonicalStatus: projection.canonical_status,
    projectionSha256: ST0606_RECORDED_PROJECTION_V2_SHA256,
    contractSha256: projection.contract_sha256,
    fixtureSha256: projection.fixture_sha256,
    sourceMode: projection.source_mode,
    screenOrder: EVIDENCE_WORKSPACE_V2_SCREEN_IDS,
    screen,
    lifecycle: projection.lifecycle,
    coverage: projection.coverage,
    attestations: projection.attestations,
    sources: projection.sources,
    facts: projection.facts,
    conflicts: projection.conflicts,
    matrix: projection.matrix,
    sourceAccess: projection.source_access,
    unknownPolicy: projection.unknown_policy,
    editorialIndependence: projection.editorial_independence,
    authority: projection.authority,
    verification: projection.verification,
    localImplementationComplete: true,
    formalAcceptanceAchieved: false,
    productionEligible: false,
  }) as unknown as EvidenceWorkspaceModelV2;
}
