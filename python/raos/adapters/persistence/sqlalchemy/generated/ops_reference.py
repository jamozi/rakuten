"""Generated ST-0308 OPS reference SQLAlchemy metadata.

Do not edit; run scripts/build_st0308_persistence.py.
"""

# fmt: off
from __future__ import annotations

from types import MappingProxyType
from typing import Final

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    bindparam,
    insert,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.elements import TextClause

OWNER_GENERATOR_SHA256: Final = 'a52c4a0ac971ef1239e7301d84f8f09dc8cda718872e1d2d09e01aebcbbec979'
SOURCE_SHA256: Final = MappingProxyType({'changes/st-0105/README.md': '15adf4e461592453f78a363ccba411c861f476aeaf58444039c6eaff12ade8de', 'changes/st-0105/manifest.json': '7f1ead0b00d7264f40b29c79a06f35cdad06610231a5c7f7a3e5e1d18054ceb7', 'changes/st-0303/generated/iam-ops-catalog.v1.json': '0cab8decf1a9a874248ef16a5b1bfd01c19d1babbf45bb0f73eb42b89913720a', 'changes/st-0304/contracts/domain-schema.v1.yaml': '8030f28f59124686c2fb975b507f66e70640b529ff5769666f88202628e19122', 'changes/st-0304/contracts/physical/01-domain-physical.sql': 'b2f937ae00d526a886e5e875e095e247702f4bd7831a3164e2eda93423d7fdb8', 'changes/st-0304/contracts/physical/02-domain-physical.sql': 'b685751e4e2743ea6c7202e8ce726486ac152e46987bb832e6777e61b987aafc', 'changes/st-0304/contracts/physical/03-domain-physical.sql': 'f95ad5a2fd349177b01f97237d0d9a3fb598b2781828e9531a04c3c42b811b45', 'changes/st-0304/contracts/physical/04-domain-physical.sql': '4a3c029980e8c27957fac2291e7b0a8efb81eaf1faa74dee4e757b0836e7ba30', 'changes/st-0304/contracts/physical/05-domain-physical.sql': 'c78e946f9be015d461350f347f125a2cf8f01b267647a8685158af207cefc0ec', 'changes/st-0304/contracts/physical/06-domain-physical.sql': 'cc520254390d68fdc68d54c01ed6b95e031ea422814e5be924849ec61636904d', 'changes/st-0304/contracts/physical/07-domain-physical.sql': '739cc2ecae7e49702da5e36be6e37eaebaa7a535be4a623c79dee86926212870', 'changes/st-0304/contracts/physical/08-domain-physical.sql': 'eafb7b89c6fa08bd74a8c13d89aa19aea3a946e739720a8cff9e6faa3ca2bfc4', 'changes/st-0304/contracts/physical/09-domain-physical.sql': '6cebf09249f027662557038f8367bdc586030197911046be242543cd43502ae5', 'changes/st-0304/contracts/physical/10-domain-physical.sql': '3d806436b7ed91f25e0396e15b914dda7258b743589ec4dc6c3f4272c9fcb38d', 'changes/st-0304/contracts/physical/11-domain-physical.sql': '947e480157a52b0d926461a4d40a7409e92e6e50482c216d394953a462d8cd09', 'changes/st-0304/generated/domain-catalog.v1.json': '41d0c9c4ba94aaf65587687a31bbab1caa05a8fed1d323d99991363013258208', 'changes/st-0306/contracts/database-roles-grants.v1.yaml': '93f03ff2a762ff0d0b950b06a5b7416687ce20e44f7e7b7f6ea2a7ed2b873206', 'changes/st-0308/CANONICAL-RECONCILIATION-v3.md': '91748530eafc018823b5a6a74cc2ca052569cb3c46f6e90dd1224d720d3fdc08', 'changes/st-0308/DESIGN_HANDOFF_V1_ST0308_LOCAL_PERSISTENCE_RUNTIME_V2.yaml': '7ce27915b7d848dfd4ad1a38a8df094fa3955847a2d9a28159ea61cbd428e882', 'changes/st-0308/IMPLEMENTATION-READINESS-v3.md': '29e90628cc8ed4259b54486ab12abddb606ae414e3a2391c5055dbbf521577f7', 'changes/st-0308/PRO-CORRECTION-REQUEST-v3.md': '0906d9bf46920bfd1d018590490857a6665ab9fc8eecc92411e3fcdb9d206270', 'changes/st-0308/contracts/persistence-runtime.v2.yaml': '0dc1de1069988807c59130df42a39837640d006c4f28ab23cf5334895abe51e4', 'changes/st-0308/contracts/persistence/ops-reference-slice.v1.yaml': '77b47ea2d3ef5a238e65132fd5c13053772eaf0c7bb6f53935aa9e7572753866', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-ai-evaluation-completed-v2.schema.json': '49d495fd47a2638cd6c008fa04823617af784b7991dad65d27f2c724c0725f39', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-ai-job-failed-v1.schema.json': '5cb07491fe735a9e1724b7539f50763928a32befb96627d642c1ad30e39fa2c7', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-ai-job-requested-v1.schema.json': '9937ac30df245d120ccf06aaaf406a8b29cdc9773307e9c9c61d9fc025abd42c', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-ai-job-succeeded-v1.schema.json': '670dbd4036129bb41284eafa6fb8809b260593f9aab4bc270384509d41d2057a', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-ai-policy-assist-completed-v1.schema.json': '689bd2b267e83d0b9b46acc884526ea87a051bf7bde57221d14893ea13d27033', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-ai-release-decision-approved-v1.schema.json': '947685c9cf295997629fe0acd27df88e0f78a581ca146dea445948d9f3632fa4', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-ai-release-decision-revoked-v1.schema.json': 'c1a671dd2849a92c4078f726aa82f720be6349e67f123df1dd35d5455f77b7a3', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-catalog-affiliate-link-invalid-v1.schema.json': '0787d7d44ef70f0a002be9c8ed4768ee19f6f833e5dd81e3399436593f72940a', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-catalog-offer-observed-v1.schema.json': 'c3e38d1c0cf17c475ca5d70a922b4ddcdfcdc8b2e381750a2b32c21fe1622f04', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-catalog-offer-unavailable-v1.schema.json': 'd8a2df0bfcdb0056a3056d95350a77697a6f8659daea5e264ca9ad13487175b7', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-editorial-article-created-v1.schema.json': 'b257eed50005023f07ad252b6676e41f8b1deb41090014a405285947a8e1fbde', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-editorial-article-plan-approved-v1.schema.json': '831be3d8bc7713a9fada02b9d06792dbdf4b1def00f360aebe7d8a0307260d2b', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-editorial-article-version-submitted-v1.schema.json': 'c1cd3bcc629575880f98091c721416c98cf24062858f3750ed426058b324808d', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-editorial-draft-generated-v1.schema.json': '6128ccaac3fabca2bfc4cfa4c1047c424124e353f5115495431b087b9e9a7012', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-evidence-source-snapshot-captured-v1.schema.json': 'f00bb94cea83ca3aede34fb6fe4531121ad356896414f3dddaa435dc8b104e93', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-ops-job-requested-v1.schema.json': 'c10f9773b621000705684bec152bdc8f037c46b688f390216effa2872ab8e671', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-policy-policy-bundle-activated-v1.schema.json': 'cb6c7233454a08ab0eea46e12fd4ff353205763393853f16d812bfe0cadbd461', 'contracts/raos-v0.4/contracts/schemas/events/jp-raos-portfolio-action-candidate-decided-v1.schema.json': '3ae2f73207c27bd019d9fd55e0d24c794e4a0d711265af902c4d38ec63bf2528', 'docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md': '540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a', 'docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml': 'c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8', 'docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml': '7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b', 'docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml': '4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d', 'docs/upstream/key_documents/RAOS_02_system_architecture_v0.1.md': '00da457014aaf6dd1b726c1a9972a4b371720cb8604d517bccc180ba7a9a93f3', 'docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md': 'dce0b457ddacef791b1e134fb5988dee6a4c1f51fa905a3bc7e7d33fb3a0269c'})
MATRIX_SHA256: Final = MappingProxyType({'concurrency': '66cb474d428703e83b7b84744c4f843463b0a040714b907e00137438f5ba08ab', 'domain_mapper': '8b2499f99faa223fbc5b6329bd0f0e441441e89b45d507b6bbb0ffbce470e872', 'event_emission': '3c4f8e429824849b9219faefb2867dd8444828562d0d0a1d9c79bfa2cc511ad0', 'idempotency': '1645b6b67d8ab6ae01520094cbc7f14405f2545c41d019ecb98ea48412c39e1b', 'identity': 'aa009ab2423069f782621d6f7e4cb4c4fa57185d03ad3195ad5df29c75360d0b', 'repository_surface': '0dcd8edabe662bb94dc38960b372dfabf1afc8e83f74e3acc4757049fda6f1f0', 'state_cas': 'f865a30c2c000dfd9ca6f2f43d0be7c5cc3883077cfd41f3dcc4c340d03c94d1', 'uow_surface': '2e298605a9679b593244d78b49a6e4f331d8927363d3513d8f7aa6527c10bdc0'})
METADATA: Final[MetaData] = MetaData()

OBJECT_ARTIFACT: Final[Table] = Table(
    'object_artifact',
    METADATA,
    Column('id', Uuid(as_uuid=True), nullable=False, server_default=text('pg_catalog.uuidv7()')),
    Column('display_id', Text(), nullable=False),
    Column('artifact_kind', Text(), nullable=False),
    Column('storage_provider', Text(), nullable=False, server_default=text("'s3'")),
    Column('bucket_name', Text(), nullable=False),
    Column('object_key', Text(), nullable=False),
    Column('object_version', Text(), nullable=True),
    Column('content_type', Text(), nullable=False),
    Column('byte_size', BigInteger(), nullable=False),
    Column('sha256', Text(), nullable=False),
    Column('encryption_state', Text(), nullable=False),
    Column('retention_class', Text(), nullable=False),
    Column('is_immutable', Boolean(), nullable=False, server_default=text('true')),
    Column('source_system', Text(), nullable=False),
    Column('acquired_at', DateTime(timezone=True), nullable=True),
    Column('created_by_principal_id', Uuid(as_uuid=True), nullable=True),
    Column('metadata', JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=text('CURRENT_TIMESTAMP')),
    PrimaryKeyConstraint('id', name='pk_ops_object_artifact'),
    CheckConstraint("artifact_kind IN ('raw_provider_response', 'raw_primary_source', 'source_snapshot', 'source_packet', 'ai_input', 'ai_output', 'publication_snapshot', 'revenue_original', 'revenue_rejects', 'audit_export', 'quality_report', 'diff', 'import_report', 'other')", name='ck_ops_object_artifact_kind'),
    CheckConstraint('byte_size >= 0', name='ck_ops_object_artifact_size'),
    CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name='ck_ops_object_artifact_sha'),
    CheckConstraint("encryption_state IN ('SSE_KMS', 'SSE_S3', 'LOCAL_DEV')", name='ck_ops_object_artifact_enc'),
    CheckConstraint("pg_catalog.jsonb_typeof(metadata) = 'object'", name='ck_ops_object_artifact_meta'),
    UniqueConstraint('display_id', name='uq_ops_object_artifact_display_id'),
    Index('uq_ops_object_artifact_location', 'bucket_name', 'object_key', 'object_version', unique=True, postgresql_using='btree', postgresql_nulls_not_distinct=True),
    Index('ix_ops_object_artifact_sha', 'sha256', unique=False, postgresql_using='btree'),
    Index('ix_ops_object_artifact_kind_created', 'artifact_kind', 'created_at', unique=False, postgresql_using='btree'),
    schema='ops',
)

RUNTIME_SETTING_VERSION: Final[Table] = Table(
    'runtime_setting_version',
    METADATA,
    Column('id', Uuid(as_uuid=True), nullable=False, server_default=text('pg_catalog.uuidv7()')),
    Column('setting_key', Text(), nullable=False),
    Column('scope_type', Text(), nullable=False),
    Column('scope_id', Uuid(as_uuid=True), nullable=True),
    Column('version_no', Integer(), nullable=False),
    Column('setting_class', Text(), nullable=False),
    Column('value', JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column('value_sha256', Text(), nullable=False),
    Column('status', Text(), nullable=False),
    Column('effective_from', DateTime(timezone=True), nullable=True),
    Column('effective_to', DateTime(timezone=True), nullable=True),
    Column('created_by_principal_id', Uuid(as_uuid=True), ForeignKey('iam.principal.id', name='fk_ops_runtime_setting_version_created_by_principal_id', ondelete='RESTRICT', deferrable=False), nullable=False),
    Column('approved_by_principal_id', Uuid(as_uuid=True), ForeignKey('iam.principal.id', name='fk_ops_runtime_setting_version_approved_by_principal_id', ondelete='RESTRICT', deferrable=False), nullable=True),
    Column('approval_reason', Text(), nullable=True),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=text('CURRENT_TIMESTAMP')),
    PrimaryKeyConstraint('id', name='pk_ops_runtime_setting_version'),
    CheckConstraint("scope_type IN ('GLOBAL', 'SITE', 'CATEGORY', 'ARTICLE', 'PROVIDER', 'TASK')", name='ck_ops_setting_scope'),
    CheckConstraint("(scope_type = 'GLOBAL' AND scope_id IS NULL) OR (scope_type <> 'GLOBAL' AND scope_id IS NOT NULL)", name='ck_ops_setting_scope_id'),
    CheckConstraint('version_no >= 1', name='ck_ops_setting_version'),
    CheckConstraint("setting_class IN ('FEATURE_FLAG', 'THRESHOLD', 'PROVIDER', 'FRESHNESS', 'BUDGET', 'UI', 'OTHER')", name='ck_ops_setting_class'),
    CheckConstraint("setting_class <> 'SECRET'", name='ck_ops_setting_no_secret'),
    CheckConstraint("pg_catalog.jsonb_typeof(value) = 'object'", name='ck_ops_setting_value'),
    CheckConstraint("value_sha256 ~ '^[0-9a-f]{64}$'", name='ck_ops_setting_hash'),
    CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'RETIRED', 'REJECTED')", name='ck_ops_setting_status'),
    CheckConstraint('effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from', name='ck_ops_setting_window'),
    UniqueConstraint('setting_key', 'scope_type', 'scope_id', 'version_no', name='uq_ops_setting_version'),
    Index('uq_ops_setting_active', 'setting_key', 'scope_type', 'scope_id', unique=True, postgresql_using='btree', postgresql_where=text("status = 'ACTIVE'"), postgresql_nulls_not_distinct=True),
    Index('ix_ops_setting_lookup', 'setting_key', 'status', 'effective_from', unique=False, postgresql_using='btree'),
    Index('ix_ops_runtime_setting_version_created_by_principal_id', 'created_by_principal_id', unique=False, postgresql_using='btree'),
    Index('ix_ops_runtime_setting_version_approved_by_principal_id', 'approved_by_principal_id', unique=False, postgresql_using='btree'),
    schema='ops',
)

AUDIT_EVENT: Final[Table] = Table(
    'audit_event',
    METADATA,
    Column('id', Uuid(as_uuid=True), nullable=False, server_default=text('pg_catalog.uuidv7()')),
    Column('occurred_at', DateTime(timezone=True), nullable=False),
    Column('actor_type', Text(), nullable=False),
    Column('actor_id', Uuid(as_uuid=True), nullable=True),
    Column('action', Text(), nullable=False),
    Column('target_type', Text(), nullable=False),
    Column('target_id', Uuid(as_uuid=True), nullable=True),
    Column('outcome', Text(), nullable=False),
    Column('severity', Text(), nullable=False, server_default=text("'INFO'")),
    Column('correlation_id', Uuid(as_uuid=True), nullable=False),
    Column('request_id', Text(), nullable=True),
    Column('before_hash', Text(), nullable=True),
    Column('after_hash', Text(), nullable=True),
    Column('details', JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=text('CURRENT_TIMESTAMP')),
    PrimaryKeyConstraint('id', name='pk_ops_audit_event'),
    CheckConstraint("actor_type IN ('USER', 'SERVICE', 'SCHEDULE', 'SYSTEM', 'ANONYMOUS')", name='ck_ops_audit_actor'),
    CheckConstraint("outcome IN ('SUCCESS', 'DENIED', 'FAILED', 'NOOP')", name='ck_ops_audit_outcome'),
    CheckConstraint("severity IN ('INFO', 'NOTICE', 'WARNING', 'CRITICAL')", name='ck_ops_audit_severity'),
    CheckConstraint("before_hash IS NULL OR before_hash ~ '^[0-9a-f]{64}$'", name='ck_ops_audit_before_hash'),
    CheckConstraint("after_hash IS NULL OR after_hash ~ '^[0-9a-f]{64}$'", name='ck_ops_audit_after_hash'),
    CheckConstraint("pg_catalog.jsonb_typeof(details) = 'object'", name='ck_ops_audit_details'),
    Index('ix_ops_audit_occurred', 'occurred_at', unique=False, postgresql_using='btree'),
    Index('ix_ops_audit_actor', 'actor_type', 'actor_id', 'occurred_at', unique=False, postgresql_using='btree'),
    Index('ix_ops_audit_target', 'target_type', 'target_id', 'occurred_at', unique=False, postgresql_using='btree'),
    Index('ix_ops_audit_corr', 'correlation_id', unique=False, postgresql_using='btree'),
    Index('ix_ops_audit_occurred_brin', 'occurred_at', unique=False, postgresql_using='brin'),
    schema='ops',
)

OUTBOX_EVENT: Final[Table] = Table(
    'outbox_event',
    METADATA,
    Column('id', Uuid(as_uuid=True), nullable=False, server_default=text('pg_catalog.uuidv7()')),
    Column('event_type', Text(), nullable=False),
    Column('event_version', Integer(), nullable=False, server_default=text('1')),
    Column('producer', Text(), nullable=False),
    Column('aggregate_type', Text(), nullable=False),
    Column('aggregate_id', Uuid(as_uuid=True), nullable=False),
    Column('aggregate_version', BigInteger(), nullable=False),
    Column('correlation_id', Uuid(as_uuid=True), nullable=False),
    Column('causation_id', Uuid(as_uuid=True), nullable=True),
    Column('actor_type', Text(), nullable=False),
    Column('actor_id', Uuid(as_uuid=True), nullable=True),
    Column('payload', JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column('payload_schema_hash', Text(), nullable=False),
    Column('status', Text(), nullable=False, server_default=text("'PENDING'")),
    Column('available_at', DateTime(timezone=True), nullable=False, server_default=text('CURRENT_TIMESTAMP')),
    Column('published_at', DateTime(timezone=True), nullable=True),
    Column('publish_attempts', SmallInteger(), nullable=False, server_default=text('0')),
    Column('last_error', Text(), nullable=True),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=text('CURRENT_TIMESTAMP')),
    PrimaryKeyConstraint('id', name='pk_ops_outbox_event'),
    CheckConstraint('event_version >= 1 AND aggregate_version >= 0', name='ck_ops_outbox_event_version'),
    CheckConstraint("pg_catalog.jsonb_typeof(payload) = 'object'", name='ck_ops_outbox_payload'),
    CheckConstraint("payload_schema_hash ~ '^[0-9a-f]{64}$'", name='ck_ops_outbox_hash'),
    CheckConstraint("status IN ('PENDING', 'DISPATCHING', 'PUBLISHED', 'FAILED', 'DEAD')", name='ck_ops_outbox_status'),
    CheckConstraint('publish_attempts >= 0', name='ck_ops_outbox_attempts'),
    CheckConstraint("status <> 'PUBLISHED' OR published_at IS NOT NULL", name='ck_ops_outbox_published'),
    Index('ix_ops_outbox_ready', 'status', 'available_at', unique=False, postgresql_using='btree', postgresql_where=text("status IN ('PENDING','FAILED')")),
    Index('ix_ops_outbox_aggregate', 'aggregate_type', 'aggregate_id', 'aggregate_version', unique=False, postgresql_using='btree'),
    Index('ix_ops_outbox_correlation', 'correlation_id', unique=False, postgresql_using='btree'),
    Index('ix_ops_outbox_created_brin', 'created_at', unique=False, postgresql_using='brin'),
    schema='ops',
)

IDEMPOTENCY_RECORD: Final[Table] = Table(
    'idempotency_record',
    METADATA,
    Column('id', Uuid(as_uuid=True), nullable=False, server_default=text('pg_catalog.uuidv7()')),
    Column('actor_fingerprint', Text(), nullable=False),
    Column('route_key', Text(), nullable=False),
    Column('idempotency_key', Text(), nullable=False),
    Column('request_hash', Text(), nullable=False),
    Column('status', Text(), nullable=False, server_default=text("'IN_PROGRESS'")),
    Column('response_status', Integer(), nullable=True),
    Column('response_body', JSONB(), nullable=True),
    Column('response_artifact_id', Uuid(as_uuid=True), ForeignKey('ops.object_artifact.id', name='fk_ops_idempotency_record_response_artifact_id', ondelete='RESTRICT', deferrable=False), nullable=True),
    Column('resource_type', Text(), nullable=True),
    Column('resource_id', Uuid(as_uuid=True), nullable=True),
    Column('expires_at', DateTime(timezone=True), nullable=False),
    Column('completed_at', DateTime(timezone=True), nullable=True),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=text('CURRENT_TIMESTAMP')),
    PrimaryKeyConstraint('id', name='pk_ops_idempotency_record'),
    CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name='ck_ops_idem_request_hash'),
    CheckConstraint("status IN ('IN_PROGRESS', 'COMPLETED', 'FAILED')", name='ck_ops_idem_status'),
    CheckConstraint("status = 'IN_PROGRESS' OR response_status IS NOT NULL", name='ck_ops_idem_response'),
    CheckConstraint('expires_at > created_at', name='ck_ops_idem_expiry'),
    CheckConstraint("response_body IS NULL OR pg_catalog.jsonb_typeof(response_body) = 'object'", name='ck_ops_idem_response_body'),
    UniqueConstraint('actor_fingerprint', 'route_key', 'idempotency_key', name='uq_ops_idempotency'),
    Index('ix_ops_idempotency_expiry', 'expires_at', unique=False, postgresql_using='btree'),
    Index('ix_ops_idempotency_record_response_artifact_id', 'response_artifact_id', unique=False, postgresql_using='btree'),
    schema='ops',
)

IMMUTABILITY_TRIGGER_NAMES: Final = (('ops.object_artifact', 'trg_ops_object_artifact_immutable'), ('ops.audit_event', 'trg_ops_audit_event_immutable'))

OBJECT_ARTIFACT_BY_ID: Final[object] = select(OBJECT_ARTIFACT).where(
    OBJECT_ARTIFACT.c.id == bindparam('artifact_id')
)
OBJECT_ARTIFACT_INSERT: Final[object] = insert(OBJECT_ARTIFACT)
RUNTIME_SETTING_CURRENT: Final[object] = (
    select(RUNTIME_SETTING_VERSION)
    .where(
        RUNTIME_SETTING_VERSION.c.setting_key == bindparam('setting_key'),
        RUNTIME_SETTING_VERSION.c.scope_type == bindparam('scope_type'),
        RUNTIME_SETTING_VERSION.c.scope_id.is_not_distinct_from(
            bindparam('scope_id')
        ),
    )
    .order_by(
        RUNTIME_SETTING_VERSION.c.version_no.desc(),
        RUNTIME_SETTING_VERSION.c.id.desc(),
    )
    .limit(1)
)
RUNTIME_SETTING_INSERT: Final[object] = insert(RUNTIME_SETTING_VERSION)

RUNTIME_SETTING_TRANSITIONS: Final[MappingProxyType[tuple[str, str], TextClause]] = MappingProxyType(
    {
        ('DRAFT', 'ACTIVE'): text("UPDATE ops.runtime_setting_version SET status='ACTIVE', approved_by_principal_id=:context_actor_id, approval_reason=:nonempty_reason, effective_from=:activation_at, effective_to=NULL WHERE id=:version_id AND status=:expected_status AND :expected_status='DRAFT' AND approved_by_principal_id IS NULL AND approval_reason IS NULL AND effective_to IS NULL RETURNING *"),
        ('DRAFT', 'REJECTED'): text("UPDATE ops.runtime_setting_version SET status='REJECTED' WHERE id=:version_id AND status=:expected_status AND :expected_status='DRAFT' AND approved_by_principal_id IS NULL AND approval_reason IS NULL RETURNING *"),
        ('DRAFT', 'RETIRED'): text("UPDATE ops.runtime_setting_version SET status='RETIRED' WHERE id=:version_id AND status=:expected_status AND :expected_status='DRAFT' AND approved_by_principal_id IS NULL AND approval_reason IS NULL RETURNING *"),
        ('ACTIVE', 'RETIRED'): text("UPDATE ops.runtime_setting_version SET status='RETIRED', effective_to=:retired_at WHERE id=:version_id AND status=:expected_status AND :expected_status='ACTIVE' AND approved_by_principal_id IS NOT NULL AND length(btrim(approval_reason))>0 AND effective_from IS NOT NULL AND effective_to IS NULL RETURNING *"),
    }
)

IDEMPOTENCY_SQL: Final[MappingProxyType[str, TextClause]] = MappingProxyType(
    {
        'initial_claim': text("INSERT INTO ops.idempotency_record (\n  actor_fingerprint, route_key, idempotency_key, request_hash, status,\n  response_status, response_body, response_artifact_id, resource_type,\n  resource_id, expires_at, completed_at, created_at\n) VALUES (\n  :actor_fingerprint, :route_key, :idempotency_key, :request_hash, 'IN_PROGRESS',\n  NULL, NULL, NULL, NULL, NULL, :expires_at, NULL, transaction_timestamp()\n)\nON CONFLICT (actor_fingerprint, route_key, idempotency_key)\nDO NOTHING\nRETURNING id, actor_fingerprint, route_key, idempotency_key, request_hash,\n          status, expires_at, created_at"),
        'loser_read': text('SELECT id, actor_fingerprint, route_key, idempotency_key, request_hash,\n       status, response_status, response_body, response_artifact_id,\n       resource_type, resource_id, expires_at, completed_at, created_at\nFROM ops.idempotency_record\nWHERE actor_fingerprint=:actor_fingerprint\n  AND route_key=:route_key\n  AND idempotency_key=:idempotency_key'),
        'expired_lock': text('SELECT id, actor_fingerprint, route_key, idempotency_key, request_hash,\n       status, response_status, response_body, response_artifact_id,\n       resource_type, resource_id, expires_at, completed_at, created_at\nFROM ops.idempotency_record\nWHERE actor_fingerprint=:actor_fingerprint\n  AND route_key=:route_key\n  AND idempotency_key=:idempotency_key\nFOR UPDATE'),
        'expired_in_place_replacement': text("UPDATE ops.idempotency_record\nSET request_hash=:new_request_hash,\n    status='IN_PROGRESS',\n    response_status=NULL,\n    response_body=NULL,\n    response_artifact_id=NULL,\n    resource_type=NULL,\n    resource_id=NULL,\n    expires_at=:new_expires_at,\n    completed_at=NULL,\n    created_at=transaction_timestamp()\nWHERE id=:record_id\n  AND actor_fingerprint=:actor_fingerprint\n  AND route_key=:route_key\n  AND idempotency_key=:idempotency_key\n  AND request_hash=:observed_request_hash\n  AND status=:observed_status\n  AND expires_at=:observed_expires_at\n  AND expires_at<=transaction_timestamp()\nRETURNING id, actor_fingerprint, route_key, idempotency_key, request_hash,\n          status, expires_at, created_at"),
        'complete_success': text("UPDATE ops.idempotency_record\nSET status='COMPLETED',\n    response_status=:response_status,\n    response_body=:response_body,\n    response_artifact_id=:response_artifact_id,\n    resource_type=:resource_type,\n    resource_id=:resource_id,\n    completed_at=transaction_timestamp()\nWHERE id=:handle_record_id\n  AND actor_fingerprint=:handle_actor_fingerprint\n  AND route_key=:handle_route_key\n  AND idempotency_key=:handle_idempotency_key\n  AND request_hash=:handle_request_hash\n  AND status='IN_PROGRESS'\n  AND completed_at IS NULL\n  AND expires_at>transaction_timestamp()\nRETURNING id, status, response_status, response_body, response_artifact_id,\n          resource_type, resource_id, completed_at"),
        'complete_failure': text("UPDATE ops.idempotency_record\nSET status='FAILED',\n    response_status=:response_status,\n    response_body=:response_body,\n    response_artifact_id=:response_artifact_id,\n    resource_type=:resource_type,\n    resource_id=:resource_id,\n    completed_at=transaction_timestamp()\nWHERE id=:handle_record_id\n  AND actor_fingerprint=:handle_actor_fingerprint\n  AND route_key=:handle_route_key\n  AND idempotency_key=:handle_idempotency_key\n  AND request_hash=:handle_request_hash\n  AND status='IN_PROGRESS'\n  AND completed_at IS NULL\n  AND expires_at>transaction_timestamp()\nRETURNING id, status, response_status, response_body, response_artifact_id,\n          resource_type, resource_id, completed_at"),
    }
)

__all__ = [
    'AUDIT_EVENT',
    'IDEMPOTENCY_RECORD',
    'IDEMPOTENCY_SQL',
    'IMMUTABILITY_TRIGGER_NAMES',
    'MATRIX_SHA256',
    'METADATA',
    'OBJECT_ARTIFACT',
    'OBJECT_ARTIFACT_BY_ID',
    'OBJECT_ARTIFACT_INSERT',
    'OUTBOX_EVENT',
    'RUNTIME_SETTING_CURRENT',
    'RUNTIME_SETTING_INSERT',
    'RUNTIME_SETTING_TRANSITIONS',
    'RUNTIME_SETTING_VERSION',
    'OWNER_GENERATOR_SHA256',
    'SOURCE_SHA256',
]
# fmt: on
