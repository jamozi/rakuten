-- RAOS-CONTENT-001 v0.1
-- PROPOSAL_ONLY: Do not apply directly to production.
-- Purpose: align RAOS-DATA-001 with versioned content contracts.
-- Required before use: repository migration framework, PostgreSQL 18.x integration tests,
-- role/grant review, expand-migrate-contract plan, rollback and backup/restore rehearsal.

BEGIN;

CREATE TABLE IF NOT EXISTS editorial.content_schema_version (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    schema_code text NOT NULL,
    semantic_version text NOT NULL,
    artifact_id uuid NOT NULL REFERENCES ops.object_artifact(id),
    schema_sha256 text NOT NULL CHECK (schema_sha256 ~ '^[0-9a-f]{64}$'),
    status text NOT NULL CHECK (status IN ('DRAFT','ACTIVE','DEPRECATED','RETIRED')),
    effective_from timestamptz NOT NULL,
    effective_to timestamptz,
    approved_by_principal_id uuid REFERENCES iam.principal(id),
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (schema_code, semantic_version),
    CHECK (effective_to IS NULL OR effective_to > effective_from),
    CHECK ((status = 'ACTIVE') = (approved_by_principal_id IS NOT NULL AND approved_at IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS editorial.article_type_version (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    article_type_code text NOT NULL,
    semantic_version text NOT NULL,
    contract jsonb NOT NULL,
    contract_sha256 text NOT NULL CHECK (contract_sha256 ~ '^[0-9a-f]{64}$'),
    status text NOT NULL CHECK (status IN ('DRAFT','ACTIVE','DEPRECATED','RETIRED')),
    approved_by_principal_id uuid REFERENCES iam.principal(id),
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (article_type_code, semantic_version)
);

CREATE TABLE IF NOT EXISTS editorial.article_template_version (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    article_type_version_id uuid NOT NULL REFERENCES editorial.article_type_version(id),
    semantic_version text NOT NULL,
    template jsonb NOT NULL,
    template_sha256 text NOT NULL CHECK (template_sha256 ~ '^[0-9a-f]{64}$'),
    status text NOT NULL CHECK (status IN ('DRAFT','ACTIVE','DEPRECATED','RETIRED')),
    approved_by_principal_id uuid REFERENCES iam.principal(id),
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (article_type_version_id, semantic_version)
);

CREATE TABLE IF NOT EXISTS editorial.editorial_methodology_version (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    methodology_code text NOT NULL,
    semantic_version text NOT NULL,
    article_type_code text NOT NULL,
    definition jsonb NOT NULL,
    definition_sha256 text NOT NULL CHECK (definition_sha256 ~ '^[0-9a-f]{64}$'),
    excludes_finance_inputs boolean NOT NULL DEFAULT true CHECK (excludes_finance_inputs),
    status text NOT NULL CHECK (status IN ('DRAFT','ACTIVE','DEPRECATED','RETIRED')),
    approved_by_principal_id uuid REFERENCES iam.principal(id),
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (methodology_code, semantic_version)
);

CREATE TABLE IF NOT EXISTS editorial.article_methodology_binding (
    article_version_id uuid PRIMARY KEY REFERENCES editorial.article_version(id),
    methodology_version_id uuid NOT NULL REFERENCES editorial.editorial_methodology_version(id),
    candidate_universe_artifact_id uuid NOT NULL REFERENCES ops.object_artifact(id),
    candidate_universe_sha256 text NOT NULL CHECK (candidate_universe_sha256 ~ '^[0-9a-f]{64}$'),
    bound_at timestamptz NOT NULL DEFAULT now(),
    bound_by_principal_id uuid REFERENCES iam.principal(id)
);

CREATE TABLE IF NOT EXISTS editorial.seo_metadata_version (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    article_version_id uuid NOT NULL REFERENCES editorial.article_version(id),
    semantic_version text NOT NULL,
    metadata jsonb NOT NULL,
    metadata_sha256 text NOT NULL CHECK (metadata_sha256 ~ '^[0-9a-f]{64}$'),
    status text NOT NULL CHECK (status IN ('DRAFT','VALIDATED','APPROVED','REJECTED')),
    validated_at timestamptz,
    approved_by_principal_id uuid REFERENCES iam.principal(id),
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (article_version_id, semantic_version)
);

CREATE TABLE IF NOT EXISTS editorial.structured_data_manifest (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    article_version_id uuid NOT NULL REFERENCES editorial.article_version(id),
    seo_metadata_version_id uuid NOT NULL REFERENCES editorial.seo_metadata_version(id),
    generator_version text NOT NULL,
    visible_content_sha256 text NOT NULL CHECK (visible_content_sha256 ~ '^[0-9a-f]{64}$'),
    jsonld_artifact_id uuid NOT NULL REFERENCES ops.object_artifact(id),
    jsonld_sha256 text NOT NULL CHECK (jsonld_sha256 ~ '^[0-9a-f]{64}$'),
    enabled_types text[] NOT NULL,
    disabled_types text[] NOT NULL,
    validation_status text NOT NULL CHECK (validation_status IN ('PASS','FAIL')),
    validated_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (article_version_id, generator_version, visible_content_sha256)
);

CREATE TABLE IF NOT EXISTS editorial.media_asset (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    display_id text NOT NULL UNIQUE,
    asset_class text NOT NULL,
    source_id uuid REFERENCES evidence.source(id),
    raw_artifact_id uuid REFERENCES ops.object_artifact(id),
    asset_sha256 text NOT NULL CHECK (asset_sha256 ~ '^[0-9a-f]{64}$'),
    license_status text NOT NULL,
    modification_policy text NOT NULL,
    alt_text text NOT NULL DEFAULT '',
    decorative boolean NOT NULL DEFAULT false,
    long_description_artifact_id uuid REFERENCES ops.object_artifact(id),
    width integer NOT NULL CHECK (width > 0),
    height integer NOT NULL CHECK (height > 0),
    captured_or_observed_at timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN ('DRAFT','APPROVED','BLOCKED','RETIRED')),
    approved_by_principal_id uuid REFERENCES iam.principal(id),
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (decorative OR length(btrim(alt_text)) > 0)
);

CREATE TABLE IF NOT EXISTS evidence.first_hand_experience_record (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    display_id text NOT NULL UNIQUE,
    product_id uuid NOT NULL REFERENCES catalog.product(id),
    product_variant_identity jsonb NOT NULL,
    tester_principal_id uuid NOT NULL REFERENCES iam.principal(id),
    procedure_version text NOT NULL,
    started_at timestamptz NOT NULL,
    ended_at timestamptz NOT NULL,
    environment jsonb NOT NULL,
    limitations text NOT NULL,
    review_status text NOT NULL CHECK (review_status IN ('DRAFT','REVIEWED','APPROVED','REJECTED')),
    reviewed_by_principal_id uuid REFERENCES iam.principal(id),
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (ended_at >= started_at)
);

CREATE TABLE IF NOT EXISTS evidence.first_hand_experience_asset (
    experience_record_id uuid NOT NULL REFERENCES evidence.first_hand_experience_record(id),
    artifact_id uuid NOT NULL REFERENCES ops.object_artifact(id),
    role text NOT NULL CHECK (role IN ('PHOTO','VIDEO','MEASUREMENT','LOG','PROCEDURE','OTHER')),
    artifact_sha256 text NOT NULL CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (experience_record_id, artifact_id, role)
);

CREATE TABLE IF NOT EXISTS editorial.article_disclosure_context (
    article_version_id uuid PRIMARY KEY REFERENCES editorial.article_version(id),
    affiliate_relationship boolean NOT NULL DEFAULT true,
    material_benefit_relationship boolean NOT NULL DEFAULT false,
    benefit_types text[] NOT NULL DEFAULT '{}',
    disclosure_policy_version text NOT NULL,
    additional_disclosure_text text,
    reviewed_by_principal_id uuid REFERENCES iam.principal(id),
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (NOT material_benefit_relationship OR length(btrim(coalesce(additional_disclosure_text,''))) > 0)
);

-- Proposed additive bindings. Codex must inspect actual baseline columns before applying.
ALTER TABLE editorial.article_version
    ADD COLUMN IF NOT EXISTS content_schema_version_id uuid REFERENCES editorial.content_schema_version(id),
    ADD COLUMN IF NOT EXISTS article_type_version_id uuid REFERENCES editorial.article_type_version(id),
    ADD COLUMN IF NOT EXISTS seo_metadata_version_id uuid REFERENCES editorial.seo_metadata_version(id);

CREATE INDEX IF NOT EXISTS ix_content_schema_active ON editorial.content_schema_version(schema_code, effective_from DESC) WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS ix_article_type_active ON editorial.article_type_version(article_type_code, created_at DESC) WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS ix_methodology_active ON editorial.editorial_methodology_version(methodology_code, created_at DESC) WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS ix_media_asset_status ON editorial.media_asset(status, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_experience_product ON evidence.first_hand_experience_record(product_id, ended_at DESC);

COMMIT;
