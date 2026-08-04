-- ST-0004 / INT-DEC-005 / INT-DEC-006
-- Phase: EXPAND
--
-- Formal migration derived from RAOS_06_001_data_alignment_patch_v0.1.sql.
-- The proposal is design input only and is intentionally never executed.

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '15min';

DO $$
DECLARE
    required_name text;
    required_role text;
BEGIN
    IF current_setting('server_version_num')::integer < 180000 THEN
        RAISE EXCEPTION 'ST-0004 requires PostgreSQL 18 or later';
    END IF;

    FOREACH required_name IN ARRAY ARRAY[
        'ai.evaluation_suite',
        'ai.evaluation_dataset_version',
        'ai.evaluation_case',
        'ai.evaluation_run',
        'ai.evaluation_case_result',
        'ai.human_evaluation',
        'ai.judge_calibration',
        'ai.release_decision',
        'ai.release_approval'
    ]
    LOOP
        IF to_regclass(required_name) IS NULL THEN
            RAISE EXCEPTION
                'ST-0004 requires finalized ST-0003 relation %',
                required_name;
        END IF;
    END LOOP;

    IF (
        SELECT count(*)
          FROM pg_constraint
         WHERE (conrelid, conname) IN (
            ('ai.ai_job'::regclass, 'ck_ai_job_status'),
            ('ai.ai_job'::regclass, 'ck_ai_job_complete'),
            ('ai.prompt_version'::regclass, 'ck_ai_prompt_status'),
            ('ai.model_route_version'::regclass, 'ck_ai_route_status')
         )
           AND convalidated
    ) <> 4
       OR to_regprocedure('ai.artifact_matches_immutable_hash(uuid,text)') IS NULL
       OR to_regprocedure('ops.reject_immutable_mutation()') IS NULL
       OR to_regclass('ai.ix_ai_eval_case_result_zero_tolerance_artifact') IS NULL
    THEN
        RAISE EXCEPTION
            'ST-0004 requires the exact finalized ST-0003 Contract';
    END IF;

    IF to_regclass('editorial.article_version') IS NULL
       OR to_regclass('ops.object_artifact') IS NULL
       OR to_regclass('iam.principal') IS NULL
       OR to_regclass('catalog.canonical_product') IS NULL
    THEN
        RAISE EXCEPTION 'ST-0004 requires the RAOS-DATA-001 content baseline';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'editorial'
           AND table_name = 'article_version'
           AND column_name = 'content_schema_version'
           AND data_type = 'integer'
           AND is_nullable = 'NO'
    ) OR (
        SELECT count(*)
          FROM pg_constraint
         WHERE (conrelid, conname) IN (
            ('editorial.article_version'::regclass,
             'pk_editorial_article_version'),
            ('editorial.article_version'::regclass,
             'uq_editorial_article_version_no'),
            ('editorial.article_version'::regclass,
             'ck_editorial_article_version_status')
         )
    ) <> 3 THEN
        RAISE EXCEPTION
            'ST-0004 predecessor article_version shape is missing or drifted';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_trigger AS trigger
         WHERE trigger.tgrelid = 'ops.object_artifact'::regclass
           AND trigger.tgname = 'trg_ops_object_artifact_immutable'
           AND trigger.tgfoid =
                'ops.reject_immutable_mutation()'::regprocedure
           AND trigger.tgtype = 27
           AND trigger.tgenabled = 'O'
           AND NOT trigger.tgisinternal
    ) THEN
        RAISE EXCEPTION
            'ST-0004 requires the immutable object-artifact registry';
    END IF;

    FOREACH required_role IN ARRAY ARRAY[
        'raos_api_rw',
        'raos_worker_rw',
        'raos_projection_rw',
        'raos_public_ro',
        'raos_reporting_ro',
        'raos_auditor_ro'
    ]
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_roles WHERE rolname = required_role
        ) THEN
            RAISE EXCEPTION 'ST-0004 requires predecessor role %', required_role;
        END IF;
    END LOOP;

    FOREACH required_name IN ARRAY ARRAY[
        'editorial.content_schema_version',
        'editorial.article_type_version',
        'editorial.article_template_version',
        'editorial.editorial_methodology_version',
        'editorial.article_methodology_binding',
        'editorial.seo_metadata_version',
        'editorial.structured_data_manifest',
        'editorial.media_asset',
        'evidence.first_hand_experience_record',
        'evidence.first_hand_experience_asset',
        'editorial.article_disclosure_context'
    ]
    LOOP
        IF to_regclass(required_name) IS NOT NULL THEN
            RAISE EXCEPTION
                'ST-0004 Expand appears already/partially applied at %; inspect migration history',
                required_name;
        END IF;
    END LOOP;

    IF EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'editorial'
           AND table_name = 'article_version'
           AND column_name IN (
                'content_schema_version_id',
                'article_type_version_id',
                'article_template_version_id',
                'seo_metadata_version_id'
           )
    ) THEN
        RAISE EXCEPTION
            'ST-0004 article_version bindings already/partially exist';
    END IF;
END
$$;

CREATE TABLE editorial.content_schema_version (
    id uuid DEFAULT uuidv7() NOT NULL,
    schema_code text NOT NULL,
    semantic_version text NOT NULL,
    artifact_id uuid NOT NULL,
    schema_sha256 text NOT NULL,
    status text DEFAULT 'DRAFT' NOT NULL,
    effective_from timestamptz NOT NULL,
    effective_to timestamptz,
    approved_by_principal_id uuid,
    approved_at timestamptz,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pk_editorial_content_schema_version PRIMARY KEY (id),
    CONSTRAINT uq_editorial_content_schema_code_version
        UNIQUE (schema_code, semantic_version),
    CONSTRAINT ck_editorial_content_schema_code CHECK (
        schema_code ~ '^[a-z][a-z0-9._-]{2,127}$'
    ),
    CONSTRAINT ck_editorial_content_schema_semver CHECK (
        semantic_version ~ '^[0-9]+\.[0-9]+\.[0-9]+([+-][0-9A-Za-z.-]+)?$'
    ),
    CONSTRAINT ck_editorial_content_schema_sha CHECK (
        schema_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_editorial_content_schema_status CHECK (
        status IN ('DRAFT', 'ACTIVE', 'DEPRECATED', 'RETIRED')
    ),
    CONSTRAINT ck_editorial_content_schema_window CHECK (
        effective_to IS NULL OR effective_to > effective_from
    ),
    CONSTRAINT ck_editorial_content_schema_active_window CHECK (
        status <> 'ACTIVE' OR effective_to IS NULL
    ),
    CONSTRAINT ck_editorial_content_schema_approval_pair CHECK (
        (approved_by_principal_id IS NULL) = (approved_at IS NULL)
    ),
    CONSTRAINT ck_editorial_content_schema_active_approval CHECK (
        status <> 'ACTIVE'
        OR (approved_by_principal_id IS NOT NULL AND approved_at IS NOT NULL)
    ),
    CONSTRAINT fk_editorial_content_schema_artifact FOREIGN KEY (artifact_id)
        REFERENCES ops.object_artifact(id) ON DELETE RESTRICT,
    CONSTRAINT fk_editorial_content_schema_approver
        FOREIGN KEY (approved_by_principal_id)
        REFERENCES iam.principal(id) ON DELETE RESTRICT
);

CREATE TABLE editorial.article_type_version (
    id uuid DEFAULT uuidv7() NOT NULL,
    article_type_code text NOT NULL,
    semantic_version text NOT NULL,
    contract jsonb NOT NULL,
    contract_sha256 text NOT NULL,
    status text DEFAULT 'DRAFT' NOT NULL,
    approved_by_principal_id uuid,
    approved_at timestamptz,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pk_editorial_article_type_version PRIMARY KEY (id),
    CONSTRAINT uq_editorial_article_type_code_version
        UNIQUE (article_type_code, semantic_version),
    CONSTRAINT uq_editorial_article_type_id_code
        UNIQUE (id, article_type_code),
    CONSTRAINT ck_editorial_article_type_code CHECK (
        article_type_code ~ '^[a-z][a-z0-9_]{2,127}$'
    ),
    CONSTRAINT ck_editorial_article_type_semver CHECK (
        semantic_version ~ '^[0-9]+\.[0-9]+\.[0-9]+([+-][0-9A-Za-z.-]+)?$'
    ),
    CONSTRAINT ck_editorial_article_type_contract CHECK (
        jsonb_typeof(contract) = 'object'
    ),
    CONSTRAINT ck_editorial_article_type_sha CHECK (
        contract_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_editorial_article_type_status CHECK (
        status IN ('DRAFT', 'ACTIVE', 'DEPRECATED', 'RETIRED')
    ),
    CONSTRAINT ck_editorial_article_type_approval_pair CHECK (
        (approved_by_principal_id IS NULL) = (approved_at IS NULL)
    ),
    CONSTRAINT ck_editorial_article_type_active_approval CHECK (
        status <> 'ACTIVE'
        OR (approved_by_principal_id IS NOT NULL AND approved_at IS NOT NULL)
    ),
    CONSTRAINT fk_editorial_article_type_approver
        FOREIGN KEY (approved_by_principal_id)
        REFERENCES iam.principal(id) ON DELETE RESTRICT
);

CREATE TABLE editorial.article_template_version (
    id uuid DEFAULT uuidv7() NOT NULL,
    article_type_version_id uuid NOT NULL,
    semantic_version text NOT NULL,
    template jsonb NOT NULL,
    template_sha256 text NOT NULL,
    status text DEFAULT 'DRAFT' NOT NULL,
    approved_by_principal_id uuid,
    approved_at timestamptz,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pk_editorial_article_template_version PRIMARY KEY (id),
    CONSTRAINT uq_editorial_article_template_type_version
        UNIQUE (article_type_version_id, semantic_version),
    CONSTRAINT ck_editorial_article_template_semver CHECK (
        semantic_version ~ '^[0-9]+\.[0-9]+\.[0-9]+([+-][0-9A-Za-z.-]+)?$'
    ),
    CONSTRAINT ck_editorial_article_template_shape CHECK (
        jsonb_typeof(template) = 'object'
    ),
    CONSTRAINT ck_editorial_article_template_sha CHECK (
        template_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_editorial_article_template_status CHECK (
        status IN ('DRAFT', 'ACTIVE', 'DEPRECATED', 'RETIRED')
    ),
    CONSTRAINT ck_editorial_article_template_approval_pair CHECK (
        (approved_by_principal_id IS NULL) = (approved_at IS NULL)
    ),
    CONSTRAINT ck_editorial_article_template_active_approval CHECK (
        status <> 'ACTIVE'
        OR (approved_by_principal_id IS NOT NULL AND approved_at IS NOT NULL)
    ),
    CONSTRAINT fk_editorial_article_template_type
        FOREIGN KEY (article_type_version_id)
        REFERENCES editorial.article_type_version(id) ON DELETE RESTRICT,
    CONSTRAINT fk_editorial_article_template_approver
        FOREIGN KEY (approved_by_principal_id)
        REFERENCES iam.principal(id) ON DELETE RESTRICT
);

CREATE TABLE editorial.editorial_methodology_version (
    id uuid DEFAULT uuidv7() NOT NULL,
    methodology_code text NOT NULL,
    semantic_version text NOT NULL,
    article_type_code text NOT NULL,
    article_type_version_id uuid NOT NULL,
    definition jsonb NOT NULL,
    definition_sha256 text NOT NULL,
    excludes_finance_inputs boolean DEFAULT true NOT NULL,
    status text DEFAULT 'DRAFT' NOT NULL,
    approved_by_principal_id uuid,
    approved_at timestamptz,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pk_editorial_methodology_version PRIMARY KEY (id),
    CONSTRAINT uq_editorial_methodology_code_version
        UNIQUE (methodology_code, semantic_version),
    CONSTRAINT ck_editorial_methodology_code CHECK (
        methodology_code ~ '^[a-z][a-z0-9._-]{2,127}$'
    ),
    CONSTRAINT ck_editorial_methodology_semver CHECK (
        semantic_version ~ '^[0-9]+\.[0-9]+\.[0-9]+([+-][0-9A-Za-z.-]+)?$'
    ),
    CONSTRAINT ck_editorial_methodology_definition CHECK (
        jsonb_typeof(definition) = 'object'
    ),
    CONSTRAINT ck_editorial_methodology_sha CHECK (
        definition_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_editorial_methodology_no_finance CHECK (
        excludes_finance_inputs
    ),
    CONSTRAINT ck_editorial_methodology_status CHECK (
        status IN ('DRAFT', 'ACTIVE', 'DEPRECATED', 'RETIRED')
    ),
    CONSTRAINT ck_editorial_methodology_approval_pair CHECK (
        (approved_by_principal_id IS NULL) = (approved_at IS NULL)
    ),
    CONSTRAINT ck_editorial_methodology_active_approval CHECK (
        status <> 'ACTIVE'
        OR (approved_by_principal_id IS NOT NULL AND approved_at IS NOT NULL)
    ),
    CONSTRAINT fk_editorial_methodology_article_type
        FOREIGN KEY (article_type_version_id, article_type_code)
        REFERENCES editorial.article_type_version(id, article_type_code)
        ON DELETE RESTRICT,
    CONSTRAINT fk_editorial_methodology_approver
        FOREIGN KEY (approved_by_principal_id)
        REFERENCES iam.principal(id) ON DELETE RESTRICT
);

CREATE TABLE editorial.article_methodology_binding (
    article_version_id uuid NOT NULL,
    methodology_version_id uuid NOT NULL,
    candidate_universe_artifact_id uuid NOT NULL,
    candidate_universe_sha256 text NOT NULL,
    bound_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
    bound_by_principal_id uuid NOT NULL,
    CONSTRAINT pk_editorial_article_methodology_binding
        PRIMARY KEY (article_version_id),
    CONSTRAINT ck_editorial_article_methodology_candidate_sha CHECK (
        candidate_universe_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT fk_editorial_article_methodology_article
        FOREIGN KEY (article_version_id)
        REFERENCES editorial.article_version(id) ON DELETE RESTRICT,
    CONSTRAINT fk_editorial_article_methodology_version
        FOREIGN KEY (methodology_version_id)
        REFERENCES editorial.editorial_methodology_version(id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_editorial_article_methodology_candidate
        FOREIGN KEY (candidate_universe_artifact_id)
        REFERENCES ops.object_artifact(id) ON DELETE RESTRICT,
    CONSTRAINT fk_editorial_article_methodology_binder
        FOREIGN KEY (bound_by_principal_id)
        REFERENCES iam.principal(id) ON DELETE RESTRICT
);

CREATE TABLE editorial.seo_metadata_version (
    id uuid DEFAULT uuidv7() NOT NULL,
    article_version_id uuid NOT NULL,
    semantic_version text NOT NULL,
    metadata jsonb NOT NULL,
    metadata_sha256 text NOT NULL,
    status text DEFAULT 'DRAFT' NOT NULL,
    validated_at timestamptz,
    approved_by_principal_id uuid,
    approved_at timestamptz,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pk_editorial_seo_metadata_version PRIMARY KEY (id),
    CONSTRAINT uq_editorial_seo_article_version
        UNIQUE (article_version_id, semantic_version),
    CONSTRAINT uq_editorial_seo_id_article UNIQUE (id, article_version_id),
    CONSTRAINT ck_editorial_seo_semver CHECK (
        semantic_version ~ '^[0-9]+\.[0-9]+\.[0-9]+([+-][0-9A-Za-z.-]+)?$'
    ),
    CONSTRAINT ck_editorial_seo_metadata_shape CHECK (
        jsonb_typeof(metadata) = 'object'
    ),
    CONSTRAINT ck_editorial_seo_metadata_sha CHECK (
        metadata_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_editorial_seo_status CHECK (
        status IN ('DRAFT', 'VALIDATED', 'APPROVED', 'REJECTED')
    ),
    CONSTRAINT ck_editorial_seo_validation_time CHECK (
        status = 'DRAFT' OR validated_at IS NOT NULL
    ),
    CONSTRAINT ck_editorial_seo_approval_pair CHECK (
        (approved_by_principal_id IS NULL) = (approved_at IS NULL)
    ),
    CONSTRAINT ck_editorial_seo_approved_human CHECK (
        status <> 'APPROVED'
        OR (approved_by_principal_id IS NOT NULL AND approved_at IS NOT NULL)
    ),
    CONSTRAINT fk_editorial_seo_article FOREIGN KEY (article_version_id)
        REFERENCES editorial.article_version(id) ON DELETE RESTRICT
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT fk_editorial_seo_approver
        FOREIGN KEY (approved_by_principal_id)
        REFERENCES iam.principal(id) ON DELETE RESTRICT
);

CREATE TABLE editorial.structured_data_manifest (
    id uuid DEFAULT uuidv7() NOT NULL,
    article_version_id uuid NOT NULL,
    seo_metadata_version_id uuid NOT NULL,
    generator_version text NOT NULL,
    visible_content_sha256 text NOT NULL,
    jsonld_artifact_id uuid NOT NULL,
    jsonld_sha256 text NOT NULL,
    enabled_types text[] NOT NULL,
    disabled_types text[] NOT NULL,
    validation_status text NOT NULL,
    validated_at timestamptz NOT NULL,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pk_editorial_structured_data_manifest PRIMARY KEY (id),
    CONSTRAINT uq_editorial_structured_data_render
        UNIQUE (article_version_id, generator_version, visible_content_sha256),
    CONSTRAINT ck_editorial_structured_data_generator CHECK (
        length(btrim(generator_version)) > 0
    ),
    CONSTRAINT ck_editorial_structured_data_visible_sha CHECK (
        visible_content_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_editorial_structured_data_jsonld_sha CHECK (
        jsonld_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_editorial_structured_data_types CHECK (
        NOT (enabled_types && disabled_types)
        AND array_position(enabled_types, NULL) IS NULL
        AND array_position(disabled_types, NULL) IS NULL
    ),
    CONSTRAINT ck_editorial_structured_data_status CHECK (
        validation_status IN ('PASS', 'FAIL')
    ),
    CONSTRAINT fk_editorial_structured_data_seo_article
        FOREIGN KEY (seo_metadata_version_id, article_version_id)
        REFERENCES editorial.seo_metadata_version(id, article_version_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_editorial_structured_data_jsonld_artifact
        FOREIGN KEY (jsonld_artifact_id)
        REFERENCES ops.object_artifact(id) ON DELETE RESTRICT
);

CREATE TABLE editorial.media_asset (
    id uuid DEFAULT uuidv7() NOT NULL,
    display_id text NOT NULL,
    asset_class text NOT NULL,
    source_id uuid NOT NULL,
    raw_artifact_id uuid NOT NULL,
    asset_sha256 text NOT NULL,
    license_status text NOT NULL,
    modification_policy text NOT NULL,
    alt_text text DEFAULT '' NOT NULL,
    decorative boolean DEFAULT false NOT NULL,
    long_description_artifact_id uuid,
    width integer NOT NULL,
    height integer NOT NULL,
    captured_or_observed_at timestamptz NOT NULL,
    status text DEFAULT 'DRAFT' NOT NULL,
    approved_by_principal_id uuid,
    approved_at timestamptz,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pk_editorial_media_asset PRIMARY KEY (id),
    CONSTRAINT uq_editorial_media_asset_display UNIQUE (display_id),
    CONSTRAINT ck_editorial_media_asset_class CHECK (
        asset_class IN ('IMAGE', 'CHART', 'VIDEO', 'DIAGRAM', 'OTHER')
    ),
    CONSTRAINT ck_editorial_media_asset_sha CHECK (
        asset_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_editorial_media_asset_license CHECK (
        license_status IN ('PENDING', 'APPROVED', 'RESTRICTED', 'REJECTED')
    ),
    CONSTRAINT ck_editorial_media_asset_modification CHECK (
        length(btrim(modification_policy)) > 0
    ),
    CONSTRAINT ck_editorial_media_asset_dimensions CHECK (
        width > 0 AND height > 0
    ),
    CONSTRAINT ck_editorial_media_asset_status CHECK (
        status IN ('DRAFT', 'APPROVED', 'BLOCKED', 'RETIRED')
    ),
    CONSTRAINT ck_editorial_media_asset_alt CHECK (
        decorative OR length(btrim(alt_text)) > 0
    ),
    CONSTRAINT ck_editorial_media_asset_approval_pair CHECK (
        (approved_by_principal_id IS NULL) = (approved_at IS NULL)
    ),
    CONSTRAINT ck_editorial_media_asset_approved_human CHECK (
        status <> 'APPROVED'
        OR (approved_by_principal_id IS NOT NULL AND approved_at IS NOT NULL)
    ),
    CONSTRAINT fk_editorial_media_asset_source FOREIGN KEY (source_id)
        REFERENCES evidence.source(id) ON DELETE RESTRICT,
    CONSTRAINT fk_editorial_media_asset_raw FOREIGN KEY (raw_artifact_id)
        REFERENCES ops.object_artifact(id) ON DELETE RESTRICT,
    CONSTRAINT fk_editorial_media_asset_long_description
        FOREIGN KEY (long_description_artifact_id)
        REFERENCES ops.object_artifact(id) ON DELETE RESTRICT,
    CONSTRAINT fk_editorial_media_asset_approver
        FOREIGN KEY (approved_by_principal_id)
        REFERENCES iam.principal(id) ON DELETE RESTRICT
);

CREATE TABLE evidence.first_hand_experience_record (
    id uuid DEFAULT uuidv7() NOT NULL,
    display_id text NOT NULL,
    product_id uuid NOT NULL,
    product_variant_identity jsonb NOT NULL,
    tester_principal_id uuid NOT NULL,
    procedure_version text NOT NULL,
    started_at timestamptz NOT NULL,
    ended_at timestamptz NOT NULL,
    environment jsonb NOT NULL,
    limitations text NOT NULL,
    review_status text DEFAULT 'DRAFT' NOT NULL,
    reviewed_by_principal_id uuid,
    reviewed_at timestamptz,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pk_evidence_first_hand_experience PRIMARY KEY (id),
    CONSTRAINT uq_evidence_first_hand_experience_display UNIQUE (display_id),
    CONSTRAINT ck_evidence_first_hand_variant CHECK (
        jsonb_typeof(product_variant_identity) = 'object'
    ),
    CONSTRAINT ck_evidence_first_hand_environment CHECK (
        jsonb_typeof(environment) = 'object'
    ),
    CONSTRAINT ck_evidence_first_hand_procedure CHECK (
        length(btrim(procedure_version)) > 0
    ),
    CONSTRAINT ck_evidence_first_hand_window CHECK (ended_at >= started_at),
    CONSTRAINT ck_evidence_first_hand_limitations CHECK (
        length(btrim(limitations)) > 0
    ),
    CONSTRAINT ck_evidence_first_hand_status CHECK (
        review_status IN ('DRAFT', 'REVIEWED', 'APPROVED', 'REJECTED')
    ),
    CONSTRAINT ck_evidence_first_hand_review_pair CHECK (
        (reviewed_by_principal_id IS NULL) = (reviewed_at IS NULL)
    ),
    CONSTRAINT ck_evidence_first_hand_review_required CHECK (
        review_status = 'DRAFT'
        OR (reviewed_by_principal_id IS NOT NULL AND reviewed_at IS NOT NULL)
    ),
    CONSTRAINT fk_evidence_first_hand_product FOREIGN KEY (product_id)
        REFERENCES catalog.canonical_product(id) ON DELETE RESTRICT,
    CONSTRAINT fk_evidence_first_hand_tester
        FOREIGN KEY (tester_principal_id)
        REFERENCES iam.principal(id) ON DELETE RESTRICT,
    CONSTRAINT fk_evidence_first_hand_reviewer
        FOREIGN KEY (reviewed_by_principal_id)
        REFERENCES iam.principal(id) ON DELETE RESTRICT
);

CREATE TABLE evidence.first_hand_experience_asset (
    experience_record_id uuid NOT NULL,
    artifact_id uuid NOT NULL,
    role text NOT NULL,
    artifact_sha256 text NOT NULL,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pk_evidence_first_hand_experience_asset
        PRIMARY KEY (experience_record_id, artifact_id, role),
    CONSTRAINT ck_evidence_first_hand_asset_role CHECK (
        role IN ('PHOTO', 'VIDEO', 'MEASUREMENT', 'LOG', 'PROCEDURE', 'OTHER')
    ),
    CONSTRAINT ck_evidence_first_hand_asset_sha CHECK (
        artifact_sha256 ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT fk_evidence_first_hand_asset_record
        FOREIGN KEY (experience_record_id)
        REFERENCES evidence.first_hand_experience_record(id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_evidence_first_hand_asset_artifact
        FOREIGN KEY (artifact_id)
        REFERENCES ops.object_artifact(id) ON DELETE RESTRICT
);

CREATE TABLE editorial.article_disclosure_context (
    article_version_id uuid NOT NULL,
    affiliate_relationship boolean DEFAULT true NOT NULL,
    material_benefit_relationship boolean DEFAULT false NOT NULL,
    benefit_types text[] DEFAULT '{}'::text[] NOT NULL,
    disclosure_policy_version text NOT NULL,
    additional_disclosure_text text,
    reviewed_by_principal_id uuid,
    reviewed_at timestamptz,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pk_editorial_article_disclosure_context
        PRIMARY KEY (article_version_id),
    CONSTRAINT ck_editorial_article_disclosure_policy CHECK (
        length(btrim(disclosure_policy_version)) > 0
    ),
    CONSTRAINT ck_editorial_article_disclosure_benefit CHECK (
        NOT material_benefit_relationship
        OR (
            cardinality(benefit_types) > 0
            AND length(btrim(coalesce(additional_disclosure_text, ''))) > 0
        )
    ),
    CONSTRAINT ck_editorial_article_disclosure_no_orphan_benefit CHECK (
        material_benefit_relationship OR cardinality(benefit_types) = 0
    ),
    CONSTRAINT ck_editorial_article_disclosure_review_pair CHECK (
        (reviewed_by_principal_id IS NULL) = (reviewed_at IS NULL)
    ),
    CONSTRAINT fk_editorial_article_disclosure_article
        FOREIGN KEY (article_version_id)
        REFERENCES editorial.article_version(id) ON DELETE RESTRICT,
    CONSTRAINT fk_editorial_article_disclosure_reviewer
        FOREIGN KEY (reviewed_by_principal_id)
        REFERENCES iam.principal(id) ON DELETE RESTRICT
);

ALTER TABLE editorial.article_version
    ADD COLUMN content_schema_version_id uuid,
    ADD COLUMN article_type_version_id uuid,
    ADD COLUMN article_template_version_id uuid,
    ADD COLUMN seo_metadata_version_id uuid,
    ADD CONSTRAINT fk_editorial_article_version_content_schema_st0004_expand
        FOREIGN KEY (content_schema_version_id)
        REFERENCES editorial.content_schema_version(id)
        ON DELETE RESTRICT NOT VALID,
    ADD CONSTRAINT fk_editorial_article_version_article_type_st0004_expand
        FOREIGN KEY (article_type_version_id)
        REFERENCES editorial.article_type_version(id)
        ON DELETE RESTRICT NOT VALID,
    ADD CONSTRAINT fk_editorial_article_version_article_template_st0004_expand
        FOREIGN KEY (article_template_version_id)
        REFERENCES editorial.article_template_version(id)
        ON DELETE RESTRICT NOT VALID,
    ADD CONSTRAINT fk_editorial_article_version_seo_st0004_expand
        FOREIGN KEY (seo_metadata_version_id, id)
        REFERENCES editorial.seo_metadata_version(id, article_version_id)
        ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED NOT VALID;

CREATE FUNCTION editorial.is_active_human_principal(p_principal_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
STRICT
SECURITY INVOKER
SET search_path = pg_catalog, iam
AS $$
    SELECT EXISTS (
        SELECT 1
          FROM iam.principal
         WHERE id = p_principal_id
           AND principal_type = 'USER'
           AND status = 'ACTIVE'
    )
$$;

CREATE FUNCTION editorial.content_artifact_matches_immutable_hash(
    p_artifact_id uuid,
    p_sha256 text
) RETURNS boolean
LANGUAGE sql
STABLE
STRICT
SECURITY INVOKER
SET search_path = pg_catalog, ops
AS $$
    SELECT EXISTS (
        SELECT 1
          FROM ops.object_artifact
         WHERE id = p_artifact_id
           AND is_immutable
           AND sha256 = p_sha256
    )
$$;

CREATE FUNCTION editorial.guard_versioned_content_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, editorial
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT'
           OR NEW.approved_by_principal_id IS NOT NULL
           OR NEW.approved_at IS NOT NULL THEN
            RAISE EXCEPTION '% must be created in unapproved DRAFT', TG_TABLE_NAME
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'DRAFT' THEN
            RAISE EXCEPTION '% non-DRAFT versions are immutable', TG_TABLE_NAME
                USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
    END IF;

    IF NOT (
        NEW.status = OLD.status
        OR (OLD.status = 'DRAFT' AND NEW.status IN ('ACTIVE', 'RETIRED'))
        OR (OLD.status = 'ACTIVE' AND NEW.status IN ('DEPRECATED', 'RETIRED'))
        OR (OLD.status = 'DEPRECATED' AND NEW.status = 'RETIRED')
    ) THEN
        RAISE EXCEPTION 'invalid % lifecycle transition % -> %',
            TG_TABLE_NAME, OLD.status, NEW.status
            USING ERRCODE = '23514';
    END IF;

    IF OLD.status <> 'DRAFT'
       AND (to_jsonb(OLD) - ARRAY['status', 'effective_to'])
           IS DISTINCT FROM
           (to_jsonb(NEW) - ARRAY['status', 'effective_to']) THEN
        RAISE EXCEPTION '% activated payload and approval history are immutable',
            TG_TABLE_NAME USING ERRCODE = '55000';
    END IF;

    IF NEW.status = 'DRAFT'
       AND (NEW.approved_by_principal_id IS NOT NULL
            OR NEW.approved_at IS NOT NULL) THEN
        RAISE EXCEPTION 'DRAFT % cannot carry approval evidence', TG_TABLE_NAME
            USING ERRCODE = '23514';
    END IF;

    IF NEW.status = 'ACTIVE'
       AND NOT editorial.is_active_human_principal(
            NEW.approved_by_principal_id
       ) THEN
        RAISE EXCEPTION '% activation requires an ACTIVE USER principal',
            TG_TABLE_NAME USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION editorial.guard_seo_metadata_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, editorial
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT'
           OR NEW.validated_at IS NOT NULL
           OR NEW.approved_by_principal_id IS NOT NULL
           OR NEW.approved_at IS NOT NULL THEN
            RAISE EXCEPTION 'SEO metadata must be created in unvalidated DRAFT'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'validated SEO metadata is immutable'
                USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
    END IF;
    IF NOT (
        NEW.status = OLD.status
        OR (OLD.status = 'DRAFT'
            AND NEW.status IN ('VALIDATED', 'REJECTED'))
        OR (OLD.status = 'VALIDATED'
            AND NEW.status IN ('APPROVED', 'REJECTED'))
    ) THEN
        RAISE EXCEPTION 'invalid SEO lifecycle transition % -> %',
            OLD.status, NEW.status USING ERRCODE = '23514';
    END IF;
    IF OLD.status = 'VALIDATED' AND NEW.status = 'APPROVED' THEN
        IF to_jsonb(OLD)
               - ARRAY['status', 'approved_by_principal_id', 'approved_at']
           IS DISTINCT FROM
           to_jsonb(NEW)
               - ARRAY['status', 'approved_by_principal_id', 'approved_at'] THEN
            RAISE EXCEPTION 'validated SEO metadata payload is immutable'
                USING ERRCODE = '55000';
        END IF;
    ELSIF OLD.status <> 'DRAFT'
       AND to_jsonb(OLD) - 'status'
           IS DISTINCT FROM to_jsonb(NEW) - 'status' THEN
        RAISE EXCEPTION 'validated SEO metadata payload is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.status <> 'DRAFT' AND NEW.validated_at IS NULL THEN
        RAISE EXCEPTION 'validated SEO metadata requires validated_at'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.status <> 'APPROVED'
       AND (NEW.approved_by_principal_id IS NOT NULL
            OR NEW.approved_at IS NOT NULL) THEN
        RAISE EXCEPTION 'only APPROVED SEO metadata may carry approval evidence'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.status = 'APPROVED'
       AND NOT editorial.is_active_human_principal(
            NEW.approved_by_principal_id
       ) THEN
        RAISE EXCEPTION 'SEO approval requires an ACTIVE USER principal'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION editorial.guard_media_asset_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, editorial
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT'
           OR NEW.approved_by_principal_id IS NOT NULL
           OR NEW.approved_at IS NOT NULL THEN
            RAISE EXCEPTION 'media asset must be created in unapproved DRAFT'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'reviewed media asset is immutable'
                USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
    END IF;
    IF NOT (
        NEW.status = OLD.status
        OR (OLD.status = 'DRAFT'
            AND NEW.status IN ('APPROVED', 'BLOCKED', 'RETIRED'))
        OR (OLD.status = 'APPROVED'
            AND NEW.status IN ('BLOCKED', 'RETIRED'))
        OR (OLD.status = 'BLOCKED' AND NEW.status = 'RETIRED')
    ) THEN
        RAISE EXCEPTION 'invalid media lifecycle transition % -> %',
            OLD.status, NEW.status USING ERRCODE = '23514';
    END IF;
    IF OLD.status <> 'DRAFT'
       AND to_jsonb(OLD) - 'status'
           IS DISTINCT FROM to_jsonb(NEW) - 'status' THEN
        RAISE EXCEPTION 'reviewed media asset payload is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.status = 'APPROVED'
       AND NOT editorial.is_active_human_principal(
            NEW.approved_by_principal_id
       ) THEN
        RAISE EXCEPTION 'media approval requires an ACTIVE USER principal'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION evidence.guard_first_hand_experience_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, evidence, editorial
AS $$
BEGIN
    IF TG_OP IN ('INSERT', 'UPDATE')
       AND NOT editorial.is_active_human_principal(
            NEW.tester_principal_id
       ) THEN
        RAISE EXCEPTION 'first-hand experience tester must be an ACTIVE USER'
            USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.review_status <> 'DRAFT'
           OR NEW.reviewed_by_principal_id IS NOT NULL
           OR NEW.reviewed_at IS NOT NULL THEN
            RAISE EXCEPTION 'experience record must be created in DRAFT'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        IF OLD.review_status <> 'DRAFT' THEN
            RAISE EXCEPTION 'reviewed experience record is immutable'
                USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
    END IF;
    IF NOT (
        NEW.review_status = OLD.review_status
        OR (OLD.review_status = 'DRAFT'
            AND NEW.review_status IN ('REVIEWED', 'REJECTED'))
        OR (OLD.review_status = 'REVIEWED'
            AND NEW.review_status IN ('APPROVED', 'REJECTED'))
    ) THEN
        RAISE EXCEPTION 'invalid experience lifecycle transition % -> %',
            OLD.review_status, NEW.review_status USING ERRCODE = '23514';
    END IF;
    IF OLD.review_status <> 'DRAFT'
       AND to_jsonb(OLD) - 'review_status'
           IS DISTINCT FROM to_jsonb(NEW) - 'review_status' THEN
        RAISE EXCEPTION 'reviewed experience payload is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.review_status <> 'DRAFT'
       AND NOT editorial.is_active_human_principal(
            NEW.reviewed_by_principal_id
       ) THEN
        RAISE EXCEPTION 'experience review requires an ACTIVE USER principal'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.review_status IN ('REVIEWED', 'APPROVED')
       AND NEW.reviewed_by_principal_id = NEW.tester_principal_id THEN
        RAISE EXCEPTION 'experience reviewer must differ from tester'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION editorial.guard_disclosure_context_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, editorial
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.reviewed_at IS NOT NULL THEN
            RAISE EXCEPTION 'reviewed disclosure context is immutable'
                USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
    END IF;
    IF TG_OP = 'UPDATE'
       AND OLD.reviewed_at IS NOT NULL
       AND to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
        RAISE EXCEPTION 'reviewed disclosure context is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.reviewed_by_principal_id IS NOT NULL
       AND NOT editorial.is_active_human_principal(
            NEW.reviewed_by_principal_id
       ) THEN
        RAISE EXCEPTION 'disclosure review requires an ACTIVE USER principal'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION editorial.guard_content_artifact_binding()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, editorial
AS $$
DECLARE
    artifact_id_value uuid;
    hash_value text;
BEGIN
    CASE TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
        WHEN 'editorial.content_schema_version' THEN
            artifact_id_value := NEW.artifact_id;
            hash_value := NEW.schema_sha256;
        WHEN 'editorial.article_methodology_binding' THEN
            artifact_id_value := NEW.candidate_universe_artifact_id;
            hash_value := NEW.candidate_universe_sha256;
        WHEN 'editorial.structured_data_manifest' THEN
            artifact_id_value := NEW.jsonld_artifact_id;
            hash_value := NEW.jsonld_sha256;
        WHEN 'editorial.media_asset' THEN
            artifact_id_value := NEW.raw_artifact_id;
            hash_value := NEW.asset_sha256;
            IF NEW.long_description_artifact_id IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1
                      FROM ops.object_artifact
                     WHERE id = NEW.long_description_artifact_id
                       AND is_immutable
               ) THEN
                RAISE EXCEPTION
                    'media long description requires an immutable artifact'
                    USING ERRCODE = '23514';
            END IF;
        WHEN 'evidence.first_hand_experience_asset' THEN
            artifact_id_value := NEW.artifact_id;
            hash_value := NEW.artifact_sha256;
        ELSE
            RAISE EXCEPTION 'unsupported content artifact trigger target %',
                TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME;
    END CASE;

    IF artifact_id_value IS NOT NULL
       AND NOT editorial.content_artifact_matches_immutable_hash(
            artifact_id_value,
            hash_value
       ) THEN
        RAISE EXCEPTION
            '% requires an immutable exact-hash artifact',
            TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION editorial.guard_article_methodology_binding()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, editorial
AS $$
DECLARE
    article_type_id uuid;
    methodology_type_id uuid;
    methodology_status text;
BEGIN
    IF NOT editorial.is_active_human_principal(
            NEW.bound_by_principal_id
       ) THEN
        RAISE EXCEPTION 'methodology binding actor must be an ACTIVE USER'
            USING ERRCODE = '23514';
    END IF;
    SELECT article_type_version_id
      INTO article_type_id
      FROM editorial.article_version
     WHERE id = NEW.article_version_id;
    SELECT article_type_version_id, status
      INTO methodology_type_id, methodology_status
      FROM editorial.editorial_methodology_version
     WHERE id = NEW.methodology_version_id;
    IF article_type_id IS NULL
       OR methodology_type_id IS DISTINCT FROM article_type_id
       OR methodology_status <> 'ACTIVE' THEN
        RAISE EXCEPTION
            'article methodology must bind the article ACTIVE Article Type Version'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION editorial.guard_article_content_bindings()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, editorial
AS $$
DECLARE
    schema_status text;
    type_status text;
    template_status text;
    template_type_id uuid;
    seo_status text;
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.status IN ('APPROVED', 'SUPERSEDED')
       AND (
            NEW.content_schema_version_id IS DISTINCT FROM
                OLD.content_schema_version_id
            OR NEW.article_type_version_id IS DISTINCT FROM
                OLD.article_type_version_id
            OR NEW.article_template_version_id IS DISTINCT FROM
                OLD.article_template_version_id
            OR NEW.seo_metadata_version_id IS DISTINCT FROM
                OLD.seo_metadata_version_id
       ) THEN
        RAISE EXCEPTION 'approved article content bindings are immutable'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.content_schema_version_id IS NOT NULL THEN
        SELECT status INTO schema_status
          FROM editorial.content_schema_version
         WHERE id = NEW.content_schema_version_id;
    END IF;
    IF NEW.article_type_version_id IS NOT NULL THEN
        SELECT status INTO type_status
          FROM editorial.article_type_version
         WHERE id = NEW.article_type_version_id;
    END IF;
    IF NEW.article_template_version_id IS NOT NULL THEN
        SELECT status, article_type_version_id
          INTO template_status, template_type_id
          FROM editorial.article_template_version
         WHERE id = NEW.article_template_version_id;
    END IF;
    IF NEW.article_type_version_id IS NOT NULL
       AND NEW.article_template_version_id IS NOT NULL
       AND template_type_id IS DISTINCT FROM NEW.article_type_version_id THEN
        RAISE EXCEPTION
            'Article Template Version must belong to the bound Article Type Version'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.seo_metadata_version_id IS NOT NULL THEN
        SELECT status INTO seo_status
          FROM editorial.seo_metadata_version
         WHERE id = NEW.seo_metadata_version_id
           AND article_version_id = NEW.id;
    END IF;

    IF NEW.status = 'APPROVED'
       AND (
            NEW.content_schema_version_id IS NULL
            OR NEW.article_type_version_id IS NULL
            OR NEW.article_template_version_id IS NULL
            OR NEW.seo_metadata_version_id IS NULL
            OR schema_status IS DISTINCT FROM 'ACTIVE'
            OR type_status IS DISTINCT FROM 'ACTIVE'
            OR template_status IS DISTINCT FROM 'ACTIVE'
            OR seo_status IS DISTINCT FROM 'APPROVED'
            OR NOT EXISTS (
                SELECT 1
                  FROM editorial.article_methodology_binding AS binding
                  JOIN editorial.editorial_methodology_version AS methodology
                    ON methodology.id = binding.methodology_version_id
                 WHERE binding.article_version_id = NEW.id
                   AND methodology.status = 'ACTIVE'
                   AND methodology.article_type_version_id =
                        NEW.article_type_version_id
            )
       ) THEN
        RAISE EXCEPTION
            'article approval requires ACTIVE schema/type/template/methodology and APPROVED SEO bindings'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

REVOKE ALL ON FUNCTION editorial.is_active_human_principal(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION
    editorial.content_artifact_matches_immutable_hash(uuid, text)
FROM PUBLIC;
REVOKE ALL ON FUNCTION editorial.guard_versioned_content_mutation()
    FROM PUBLIC;
REVOKE ALL ON FUNCTION editorial.guard_seo_metadata_mutation() FROM PUBLIC;
REVOKE ALL ON FUNCTION editorial.guard_media_asset_mutation() FROM PUBLIC;
REVOKE ALL ON FUNCTION evidence.guard_first_hand_experience_mutation()
    FROM PUBLIC;
REVOKE ALL ON FUNCTION editorial.guard_disclosure_context_mutation()
    FROM PUBLIC;
REVOKE ALL ON FUNCTION editorial.guard_content_artifact_binding()
    FROM PUBLIC;
REVOKE ALL ON FUNCTION editorial.guard_article_methodology_binding()
    FROM PUBLIC;
REVOKE ALL ON FUNCTION editorial.guard_article_content_bindings()
    FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    editorial.is_active_human_principal(uuid),
    editorial.content_artifact_matches_immutable_hash(uuid, text)
TO raos_api_rw;

CREATE TRIGGER trg_editorial_content_schema_lifecycle
BEFORE INSERT OR UPDATE OR DELETE ON editorial.content_schema_version
FOR EACH ROW EXECUTE FUNCTION editorial.guard_versioned_content_mutation();
CREATE TRIGGER trg_editorial_article_type_lifecycle
BEFORE INSERT OR UPDATE OR DELETE ON editorial.article_type_version
FOR EACH ROW EXECUTE FUNCTION editorial.guard_versioned_content_mutation();
CREATE TRIGGER trg_editorial_article_template_lifecycle
BEFORE INSERT OR UPDATE OR DELETE ON editorial.article_template_version
FOR EACH ROW EXECUTE FUNCTION editorial.guard_versioned_content_mutation();
CREATE TRIGGER trg_editorial_methodology_lifecycle
BEFORE INSERT OR UPDATE OR DELETE ON editorial.editorial_methodology_version
FOR EACH ROW EXECUTE FUNCTION editorial.guard_versioned_content_mutation();
CREATE TRIGGER trg_editorial_seo_metadata_lifecycle
BEFORE INSERT OR UPDATE OR DELETE ON editorial.seo_metadata_version
FOR EACH ROW EXECUTE FUNCTION editorial.guard_seo_metadata_mutation();
CREATE TRIGGER trg_editorial_media_asset_lifecycle
BEFORE INSERT OR UPDATE OR DELETE ON editorial.media_asset
FOR EACH ROW EXECUTE FUNCTION editorial.guard_media_asset_mutation();
CREATE TRIGGER trg_evidence_first_hand_lifecycle
BEFORE INSERT OR UPDATE OR DELETE ON evidence.first_hand_experience_record
FOR EACH ROW EXECUTE FUNCTION evidence.guard_first_hand_experience_mutation();
CREATE TRIGGER trg_editorial_disclosure_lifecycle
BEFORE INSERT OR UPDATE OR DELETE ON editorial.article_disclosure_context
FOR EACH ROW EXECUTE FUNCTION editorial.guard_disclosure_context_mutation();

CREATE TRIGGER trg_editorial_content_schema_artifact
BEFORE INSERT OR UPDATE ON editorial.content_schema_version
FOR EACH ROW EXECUTE FUNCTION editorial.guard_content_artifact_binding();
CREATE TRIGGER trg_editorial_article_methodology_artifact
BEFORE INSERT OR UPDATE ON editorial.article_methodology_binding
FOR EACH ROW EXECUTE FUNCTION editorial.guard_content_artifact_binding();
CREATE TRIGGER trg_editorial_structured_data_artifact
BEFORE INSERT OR UPDATE ON editorial.structured_data_manifest
FOR EACH ROW EXECUTE FUNCTION editorial.guard_content_artifact_binding();
CREATE TRIGGER trg_editorial_media_asset_artifact
BEFORE INSERT OR UPDATE ON editorial.media_asset
FOR EACH ROW EXECUTE FUNCTION editorial.guard_content_artifact_binding();
CREATE TRIGGER trg_evidence_first_hand_asset_artifact
BEFORE INSERT OR UPDATE ON evidence.first_hand_experience_asset
FOR EACH ROW EXECUTE FUNCTION editorial.guard_content_artifact_binding();

CREATE TRIGGER trg_editorial_article_methodology_cross_binding
BEFORE INSERT OR UPDATE ON editorial.article_methodology_binding
FOR EACH ROW EXECUTE FUNCTION editorial.guard_article_methodology_binding();
CREATE TRIGGER trg_editorial_article_content_bindings
BEFORE INSERT OR UPDATE ON editorial.article_version
FOR EACH ROW EXECUTE FUNCTION editorial.guard_article_content_bindings();

CREATE TRIGGER trg_editorial_article_methodology_immutable
BEFORE UPDATE OR DELETE ON editorial.article_methodology_binding
FOR EACH ROW EXECUTE FUNCTION ops.reject_immutable_mutation();
CREATE TRIGGER trg_editorial_structured_data_immutable
BEFORE UPDATE OR DELETE ON editorial.structured_data_manifest
FOR EACH ROW EXECUTE FUNCTION ops.reject_immutable_mutation();
CREATE TRIGGER trg_evidence_first_hand_asset_immutable
BEFORE UPDATE OR DELETE ON evidence.first_hand_experience_asset
FOR EACH ROW EXECUTE FUNCTION ops.reject_immutable_mutation();

ALTER TABLE editorial.content_schema_version ENABLE ROW LEVEL SECURITY;
ALTER TABLE editorial.content_schema_version FORCE ROW LEVEL SECURITY;
ALTER TABLE editorial.article_type_version ENABLE ROW LEVEL SECURITY;
ALTER TABLE editorial.article_type_version FORCE ROW LEVEL SECURITY;
ALTER TABLE editorial.article_template_version ENABLE ROW LEVEL SECURITY;
ALTER TABLE editorial.article_template_version FORCE ROW LEVEL SECURITY;
ALTER TABLE editorial.editorial_methodology_version ENABLE ROW LEVEL SECURITY;
ALTER TABLE editorial.editorial_methodology_version FORCE ROW LEVEL SECURITY;
ALTER TABLE editorial.article_methodology_binding ENABLE ROW LEVEL SECURITY;
ALTER TABLE editorial.article_methodology_binding FORCE ROW LEVEL SECURITY;
ALTER TABLE editorial.seo_metadata_version ENABLE ROW LEVEL SECURITY;
ALTER TABLE editorial.seo_metadata_version FORCE ROW LEVEL SECURITY;
ALTER TABLE editorial.structured_data_manifest ENABLE ROW LEVEL SECURITY;
ALTER TABLE editorial.structured_data_manifest FORCE ROW LEVEL SECURITY;
ALTER TABLE editorial.media_asset ENABLE ROW LEVEL SECURITY;
ALTER TABLE editorial.media_asset FORCE ROW LEVEL SECURITY;
ALTER TABLE evidence.first_hand_experience_record ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence.first_hand_experience_record FORCE ROW LEVEL SECURITY;
ALTER TABLE evidence.first_hand_experience_asset ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence.first_hand_experience_asset FORCE ROW LEVEL SECURITY;
ALTER TABLE editorial.article_disclosure_context ENABLE ROW LEVEL SECURITY;
ALTER TABLE editorial.article_disclosure_context FORCE ROW LEVEL SECURITY;

CREATE POLICY pl_content_schema_api ON editorial.content_schema_version
FOR ALL TO raos_api_rw USING (true) WITH CHECK (true);
CREATE POLICY pl_content_schema_read ON editorial.content_schema_version
FOR SELECT TO raos_worker_rw, raos_projection_rw, raos_reporting_ro,
    raos_auditor_ro USING (true);
CREATE POLICY pl_article_type_api ON editorial.article_type_version
FOR ALL TO raos_api_rw USING (true) WITH CHECK (true);
CREATE POLICY pl_article_type_read ON editorial.article_type_version
FOR SELECT TO raos_worker_rw, raos_projection_rw, raos_reporting_ro,
    raos_auditor_ro USING (true);
CREATE POLICY pl_article_template_api ON editorial.article_template_version
FOR ALL TO raos_api_rw USING (true) WITH CHECK (true);
CREATE POLICY pl_article_template_read ON editorial.article_template_version
FOR SELECT TO raos_worker_rw, raos_projection_rw, raos_reporting_ro,
    raos_auditor_ro USING (true);
CREATE POLICY pl_methodology_api ON editorial.editorial_methodology_version
FOR ALL TO raos_api_rw USING (true) WITH CHECK (true);
CREATE POLICY pl_methodology_read ON editorial.editorial_methodology_version
FOR SELECT TO raos_worker_rw, raos_projection_rw, raos_reporting_ro,
    raos_auditor_ro USING (true);
CREATE POLICY pl_article_methodology_api
ON editorial.article_methodology_binding
FOR ALL TO raos_api_rw USING (true) WITH CHECK (true);
CREATE POLICY pl_article_methodology_read
ON editorial.article_methodology_binding
FOR SELECT TO raos_worker_rw, raos_projection_rw, raos_reporting_ro,
    raos_auditor_ro USING (true);
CREATE POLICY pl_seo_metadata_api ON editorial.seo_metadata_version
FOR ALL TO raos_api_rw USING (true) WITH CHECK (true);
CREATE POLICY pl_seo_metadata_read ON editorial.seo_metadata_version
FOR SELECT TO raos_worker_rw, raos_projection_rw, raos_reporting_ro,
    raos_auditor_ro USING (true);
CREATE POLICY pl_structured_data_api ON editorial.structured_data_manifest
FOR ALL TO raos_api_rw USING (true) WITH CHECK (true);
CREATE POLICY pl_structured_data_read ON editorial.structured_data_manifest
FOR SELECT TO raos_worker_rw, raos_projection_rw, raos_reporting_ro,
    raos_auditor_ro USING (true);
CREATE POLICY pl_media_asset_api ON editorial.media_asset
FOR ALL TO raos_api_rw USING (true) WITH CHECK (true);
CREATE POLICY pl_media_asset_read ON editorial.media_asset
FOR SELECT TO raos_worker_rw, raos_projection_rw, raos_reporting_ro,
    raos_auditor_ro USING (true);
CREATE POLICY pl_first_hand_record_api
ON evidence.first_hand_experience_record
FOR ALL TO raos_api_rw USING (true) WITH CHECK (true);
CREATE POLICY pl_first_hand_record_read
ON evidence.first_hand_experience_record
FOR SELECT TO raos_worker_rw, raos_projection_rw, raos_reporting_ro,
    raos_auditor_ro USING (true);
CREATE POLICY pl_first_hand_asset_api
ON evidence.first_hand_experience_asset
FOR ALL TO raos_api_rw USING (true) WITH CHECK (true);
CREATE POLICY pl_first_hand_asset_read
ON evidence.first_hand_experience_asset
FOR SELECT TO raos_worker_rw, raos_projection_rw, raos_reporting_ro,
    raos_auditor_ro USING (true);
CREATE POLICY pl_disclosure_context_api
ON editorial.article_disclosure_context
FOR ALL TO raos_api_rw USING (true) WITH CHECK (true);
CREATE POLICY pl_disclosure_context_read
ON editorial.article_disclosure_context
FOR SELECT TO raos_worker_rw, raos_projection_rw, raos_reporting_ro,
    raos_auditor_ro USING (true);

REVOKE ALL ON TABLE
    editorial.content_schema_version,
    editorial.article_type_version,
    editorial.article_template_version,
    editorial.editorial_methodology_version,
    editorial.article_methodology_binding,
    editorial.seo_metadata_version,
    editorial.structured_data_manifest,
    editorial.media_asset,
    editorial.article_disclosure_context,
    evidence.first_hand_experience_record,
    evidence.first_hand_experience_asset
FROM PUBLIC, raos_public_ro, raos_worker_rw;

GRANT SELECT, INSERT, UPDATE ON TABLE
    editorial.content_schema_version,
    editorial.article_type_version,
    editorial.article_template_version,
    editorial.editorial_methodology_version,
    editorial.article_methodology_binding,
    editorial.seo_metadata_version,
    editorial.structured_data_manifest,
    editorial.media_asset,
    editorial.article_disclosure_context,
    evidence.first_hand_experience_record,
    evidence.first_hand_experience_asset
TO raos_api_rw;

GRANT SELECT ON TABLE
    editorial.content_schema_version,
    editorial.article_type_version,
    editorial.article_template_version,
    editorial.editorial_methodology_version,
    editorial.article_methodology_binding,
    editorial.seo_metadata_version,
    editorial.structured_data_manifest,
    editorial.media_asset,
    editorial.article_disclosure_context,
    evidence.first_hand_experience_record,
    evidence.first_hand_experience_asset
TO raos_worker_rw, raos_projection_rw, raos_auditor_ro;

GRANT USAGE ON SCHEMA editorial TO raos_auditor_ro;
GRANT SELECT ON TABLE
    editorial.content_schema_version,
    editorial.article_type_version,
    editorial.article_template_version,
    editorial.editorial_methodology_version,
    editorial.article_methodology_binding,
    editorial.seo_metadata_version,
    editorial.structured_data_manifest,
    editorial.media_asset,
    editorial.article_disclosure_context
TO raos_reporting_ro;

COMMIT;
