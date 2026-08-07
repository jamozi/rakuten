-- ST-0304 physical translation fragment 07 of 11.
-- Source: approved RAOS data catalog plus finalized ST-0003/ST-0004 semantics.
-- Capture: PostgreSQL 18.4 pg_dump --schema-only --no-owner --no-privileges
--          --no-security-labels --quote-all-identifiers for the six owned schemas.
-- Schema creation/comments are rendered once by the ST-0304 generator. The 22
-- role-bound CREATE POLICY objects remain ST-0306-owned. ENABLE/FORCE RLS remains.

--
-- Name: COLUMN "source"."metadata"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source"."metadata" IS 'Contact、acquisition method、robots/terms note等。';

--
-- Name: COLUMN "source"."created_at"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "source"."updated_at"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "source"."lock_version"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source"."lock_version" IS '楽観的排他制御用の単調増加Version。';

--
-- Name: source_packet; Type: TABLE; Schema: evidence; Owner: -
--

CREATE TABLE "evidence"."source_packet" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "article_plan_id" "uuid" NOT NULL,
    "packet_type" "text" NOT NULL,
    "status" "text" DEFAULT 'BUILDING'::"text" NOT NULL,
    "current_version_no" integer DEFAULT 0 NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    CONSTRAINT "ck_evidence_packet_lock" CHECK (("lock_version" >= 0)),
    CONSTRAINT "ck_evidence_packet_status" CHECK (("status" = ANY (ARRAY['BUILDING'::"text", 'READY'::"text", 'IN_REVIEW'::"text", 'APPROVED'::"text", 'INVALID'::"text", 'SUPERSEDED'::"text"]))),
    CONSTRAINT "ck_evidence_packet_type" CHECK (("packet_type" = ANY (ARRAY['ARTICLE_DRAFT'::"text", 'ARTICLE_UPDATE'::"text", 'COMPARISON'::"text", 'QUALITY_REVIEW'::"text"]))),
    CONSTRAINT "ck_evidence_packet_version_no" CHECK (("current_version_no" >= 0))
);

--
-- Name: TABLE "source_packet"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON TABLE "evidence"."source_packet" IS 'Article Plan向けSource PacketのStable Aggregate。Version本文はsource_packet_versionへ置く。';

--
-- Name: COLUMN "source_packet"."id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "source_packet"."display_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet"."display_id" IS 'SP-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "source_packet"."article_plan_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet"."article_plan_id" IS 'article plan id';

--
-- Name: COLUMN "source_packet"."packet_type"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet"."packet_type" IS 'packet type';

--
-- Name: COLUMN "source_packet"."status"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "source_packet"."current_version_no"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet"."current_version_no" IS 'current version no';

--
-- Name: COLUMN "source_packet"."created_at"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "source_packet"."updated_at"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "source_packet"."lock_version"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet"."lock_version" IS '楽観的排他制御用の単調増加Version。';

--
-- Name: source_packet_fact; Type: TABLE; Schema: evidence; Owner: -
--

CREATE TABLE "evidence"."source_packet_fact" (
    "source_packet_version_id" "uuid" NOT NULL,
    "fact_id" "uuid" NOT NULL,
    "usage_role" "text" NOT NULL,
    "display_order" integer NOT NULL,
    "is_required" boolean DEFAULT false NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_evidence_packet_fact_order" CHECK (("display_order" >= 0)),
    CONSTRAINT "ck_evidence_packet_fact_role" CHECK (("usage_role" = ANY (ARRAY['REQUIRED'::"text", 'SUPPORTING'::"text", 'QUALIFIER'::"text", 'EXCLUSION'::"text", 'CONTRADICTING'::"text"])))
);

--
-- Name: TABLE "source_packet_fact"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON TABLE "evidence"."source_packet_fact" IS 'Source Packet VersionへFactをrequired/supporting/exclusionとして収録する。';

--
-- Name: COLUMN "source_packet_fact"."source_packet_version_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_fact"."source_packet_version_id" IS 'source packet version id';

--
-- Name: COLUMN "source_packet_fact"."fact_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_fact"."fact_id" IS 'fact id';

--
-- Name: COLUMN "source_packet_fact"."usage_role"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_fact"."usage_role" IS 'usage role';

--
-- Name: COLUMN "source_packet_fact"."display_order"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_fact"."display_order" IS 'display order';

--
-- Name: COLUMN "source_packet_fact"."is_required"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_fact"."is_required" IS 'is required';

--
-- Name: COLUMN "source_packet_fact"."created_at"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_fact"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: source_packet_product; Type: TABLE; Schema: evidence; Owner: -
--

CREATE TABLE "evidence"."source_packet_product" (
    "source_packet_version_id" "uuid" NOT NULL,
    "product_id" "uuid" NOT NULL,
    "offer_id" "uuid",
    "product_role" "text" NOT NULL,
    "display_order" integer NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_evidence_packet_product_order" CHECK (("display_order" >= 0)),
    CONSTRAINT "ck_evidence_packet_product_role" CHECK (("product_role" = ANY (ARRAY['CANDIDATE'::"text", 'RECOMMENDED'::"text", 'COMPARED'::"text", 'EXCLUDED'::"text", 'REFERENCE'::"text"])))
);

--
-- Name: TABLE "source_packet_product"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON TABLE "evidence"."source_packet_product" IS 'Source Packet Versionに含めるProduct/Offerとcandidate/recommended/compared/excluded roleを固定する。';

--
-- Name: COLUMN "source_packet_product"."source_packet_version_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_product"."source_packet_version_id" IS 'source packet version id';

--
-- Name: COLUMN "source_packet_product"."product_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_product"."product_id" IS '正規化されたCanonical Product。';

--
-- Name: COLUMN "source_packet_product"."offer_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_product"."offer_id" IS 'ショップ単位の販売Offer。';

--
-- Name: COLUMN "source_packet_product"."product_role"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_product"."product_role" IS 'product role';

--
-- Name: COLUMN "source_packet_product"."display_order"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_product"."display_order" IS 'display order';

--
-- Name: COLUMN "source_packet_product"."created_at"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_product"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: source_packet_version; Type: TABLE; Schema: evidence; Owner: -
--

CREATE TABLE "evidence"."source_packet_version" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "source_packet_id" "uuid" NOT NULL,
    "version_no" integer NOT NULL,
    "artifact_id" "uuid" NOT NULL,
    "content_sha256" "text" NOT NULL,
    "schema_version" integer NOT NULL,
    "status" "text" NOT NULL,
    "built_by_job_id" "uuid",
    "reviewed_by_principal_id" "uuid",
    "reviewed_at" timestamp with time zone,
    "review_note" "text",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_evidence_packet_version_hash" CHECK (("content_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_evidence_packet_version_num" CHECK ((("version_no" >= 1) AND ("schema_version" >= 1))),
    CONSTRAINT "ck_evidence_packet_version_review" CHECK ((("status" <> ALL (ARRAY['APPROVED'::"text", 'REJECTED'::"text"])) OR (("reviewed_by_principal_id" IS NOT NULL) AND ("reviewed_at" IS NOT NULL)))),
    CONSTRAINT "ck_evidence_packet_version_status" CHECK (("status" = ANY (ARRAY['BUILDING'::"text", 'READY'::"text", 'IN_REVIEW'::"text", 'APPROVED'::"text", 'REJECTED'::"text", 'SUPERSEDED'::"text", 'INVALID'::"text"])))
);

--
-- Name: TABLE "source_packet_version"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON TABLE "evidence"."source_packet_version" IS 'AI/Editorへ渡す許可済み根拠集合の不変Version。Artifact hash、Schema、Review決定を保持する。';

--
-- Name: COLUMN "source_packet_version"."id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_version"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "source_packet_version"."display_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_version"."display_id" IS 'SPV-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "source_packet_version"."source_packet_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_version"."source_packet_id" IS 'source packet id';

--
-- Name: COLUMN "source_packet_version"."version_no"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_version"."version_no" IS 'Aggregate内で1から増加する不変Version番号。';

--
-- Name: COLUMN "source_packet_version"."artifact_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_version"."artifact_id" IS 'S3互換Object Storage上の不変Artifactレジストリ。';

--
-- Name: COLUMN "source_packet_version"."content_sha256"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_version"."content_sha256" IS 'content sha256';

--
-- Name: COLUMN "source_packet_version"."schema_version"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_version"."schema_version" IS 'schema version';

--
-- Name: COLUMN "source_packet_version"."status"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_version"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "source_packet_version"."built_by_job_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_version"."built_by_job_id" IS 'built by job id';

--
-- Name: COLUMN "source_packet_version"."reviewed_by_principal_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_version"."reviewed_by_principal_id" IS 'reviewed by principal id';

--
-- Name: COLUMN "source_packet_version"."reviewed_at"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_version"."reviewed_at" IS 'reviewed at';

--
-- Name: COLUMN "source_packet_version"."review_note"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_version"."review_note" IS 'review note';

--
-- Name: COLUMN "source_packet_version"."created_at"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_packet_version"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: source_snapshot; Type: TABLE; Schema: evidence; Owner: -
--

CREATE TABLE "evidence"."source_snapshot" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "source_id" "uuid" NOT NULL,
    "artifact_id" "uuid" NOT NULL,
    "external_reference" "text",
    "acquired_at" timestamp with time zone NOT NULL,
    "effective_at" timestamp with time zone,
    "expires_at" timestamp with time zone,
    "content_sha256" "text" NOT NULL,
    "parser_version" "text" NOT NULL,
    "validation_status" "text" NOT NULL,
    "validation_message" "text",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_evidence_snapshot_expiry" CHECK ((("expires_at" IS NULL) OR ("expires_at" > COALESCE("effective_at", "acquired_at")))),
    CONSTRAINT "ck_evidence_snapshot_hash" CHECK (("content_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_evidence_snapshot_status" CHECK (("validation_status" = ANY (ARRAY['VALID'::"text", 'SUSPECT'::"text", 'INVALID'::"text", 'QUARANTINED'::"text"])))
);

--
-- Name: TABLE "source_snapshot"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON TABLE "evidence"."source_snapshot" IS 'Sourceの特定時点原本をObject Artifactと結び、取得・有効・失効・Parser・Validationを不変保存する。';

--
-- Name: COLUMN "source_snapshot"."id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_snapshot"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "source_snapshot"."display_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_snapshot"."display_id" IS 'SSN-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "source_snapshot"."source_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_snapshot"."source_id" IS 'source id';

--
-- Name: COLUMN "source_snapshot"."artifact_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_snapshot"."artifact_id" IS 'S3互換Object Storage上の不変Artifactレジストリ。';

--
-- Name: COLUMN "source_snapshot"."external_reference"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_snapshot"."external_reference" IS 'external reference';

--
-- Name: COLUMN "source_snapshot"."acquired_at"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_snapshot"."acquired_at" IS 'acquired at';

--
-- Name: COLUMN "source_snapshot"."effective_at"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_snapshot"."effective_at" IS 'effective at';

--
-- Name: COLUMN "source_snapshot"."expires_at"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_snapshot"."expires_at" IS 'expires at';

--
-- Name: COLUMN "source_snapshot"."content_sha256"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_snapshot"."content_sha256" IS 'content sha256';

--
-- Name: COLUMN "source_snapshot"."parser_version"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_snapshot"."parser_version" IS 'parser version';

--
-- Name: COLUMN "source_snapshot"."validation_status"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_snapshot"."validation_status" IS 'validation status';

--
-- Name: COLUMN "source_snapshot"."validation_message"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_snapshot"."validation_message" IS 'validation message';

--
-- Name: COLUMN "source_snapshot"."created_at"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source_snapshot"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: bundle_rule; Type: TABLE; Schema: policy; Owner: -
--

CREATE TABLE "policy"."bundle_rule" (
    "policy_bundle_id" "uuid" NOT NULL,
    "rule_version_id" "uuid" NOT NULL,
    "execution_order" integer NOT NULL,
    "mode" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_policy_bundle_rule_mode" CHECK (("mode" = ANY (ARRAY['ENFORCE'::"text", 'SHADOW'::"text", 'DISABLED'::"text"]))),
    CONSTRAINT "ck_policy_bundle_rule_order" CHECK (("execution_order" >= 0))
);

--
-- Name: TABLE "bundle_rule"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON TABLE "policy"."bundle_rule" IS 'Policy Bundle内のRule version、実行順、enforce/shadow/disabled modeを固定する。';

--
-- Name: COLUMN "bundle_rule"."policy_bundle_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."bundle_rule"."policy_bundle_id" IS 'policy bundle id';

--
-- Name: COLUMN "bundle_rule"."rule_version_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."bundle_rule"."rule_version_id" IS 'rule version id';

--
-- Name: COLUMN "bundle_rule"."execution_order"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."bundle_rule"."execution_order" IS 'execution order';

--
-- Name: COLUMN "bundle_rule"."mode"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."bundle_rule"."mode" IS 'mode';

--
-- Name: COLUMN "bundle_rule"."created_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."bundle_rule"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: finding; Type: TABLE; Schema: policy; Owner: -
--

CREATE TABLE "policy"."finding" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "quality_check_run_id" "uuid" NOT NULL,
    "rule_version_id" "uuid" NOT NULL,
    "finding_code" "text" NOT NULL,
    "severity" "text" NOT NULL,
    "is_blocking" boolean NOT NULL,
    "entity_type" "text" NOT NULL,
    "entity_id" "uuid",
    "article_block_id" "uuid",
    "claim_id" "uuid",
    "message" "text" NOT NULL,
    "evidence" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "status" "text" DEFAULT 'OPEN'::"text" NOT NULL,
    "resolved_at" timestamp with time zone,
    "resolved_by_principal_id" "uuid",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_policy_finding_entity" CHECK (("entity_type" = ANY (ARRAY['ARTICLE_VERSION'::"text", 'BLOCK'::"text", 'CLAIM'::"text", 'PRODUCT'::"text", 'OFFER'::"text", 'LINK'::"text", 'SOURCE_PACKET'::"text"]))),
    CONSTRAINT "ck_policy_finding_evidence" CHECK (("jsonb_typeof"("evidence") = 'object'::"text")),
    CONSTRAINT "ck_policy_finding_resolve_pair" CHECK ((("resolved_at" IS NULL) = ("resolved_by_principal_id" IS NULL))),
    CONSTRAINT "ck_policy_finding_severity" CHECK (("severity" = ANY (ARRAY['INFO'::"text", 'LOW'::"text", 'MEDIUM'::"text", 'HIGH'::"text", 'CRITICAL'::"text"]))),
    CONSTRAINT "ck_policy_finding_status" CHECK (("status" = ANY (ARRAY['OPEN'::"text", 'FIXED'::"text", 'WAIVED'::"text", 'FALSE_POSITIVE'::"text", 'ACCEPTED_RISK'::"text"])))
);

--
-- Name: TABLE "finding"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON TABLE "policy"."finding" IS 'Quality Checkで検出したRule違反・不足・Conflictを対象Entityへ紐付け、解決・Waiver状態を管理する。';

--
-- Name: COLUMN "finding"."id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."finding"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "finding"."quality_check_run_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."finding"."quality_check_run_id" IS 'quality check run id';

--
-- Name: COLUMN "finding"."rule_version_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."finding"."rule_version_id" IS 'rule version id';

--
-- Name: COLUMN "finding"."finding_code"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."finding"."finding_code" IS 'finding code';

--
-- Name: COLUMN "finding"."severity"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."finding"."severity" IS 'severity';

--
-- Name: COLUMN "finding"."is_blocking"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."finding"."is_blocking" IS 'is blocking';

--
-- Name: COLUMN "finding"."entity_type"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."finding"."entity_type" IS 'entity type';

--
-- Name: COLUMN "finding"."entity_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."finding"."entity_id" IS 'entity id';

--
-- Name: COLUMN "finding"."article_block_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."finding"."article_block_id" IS 'article block id';

--
-- Name: COLUMN "finding"."claim_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."finding"."claim_id" IS 'claim id';

--
-- Name: COLUMN "finding"."message"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."finding"."message" IS 'message';

--
-- Name: COLUMN "finding"."evidence"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."finding"."evidence" IS '検出値、expected、locator、comparison等。';

--
-- Name: COLUMN "finding"."status"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."finding"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "finding"."resolved_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."finding"."resolved_at" IS 'resolved at';

--
-- Name: COLUMN "finding"."resolved_by_principal_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."finding"."resolved_by_principal_id" IS 'resolved by principal id';

--
-- Name: COLUMN "finding"."created_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."finding"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: gate_decision; Type: TABLE; Schema: policy; Owner: -
--

CREATE TABLE "policy"."gate_decision" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "gate_code" "text" NOT NULL,
    "scope_type" "text" NOT NULL,
    "scope_id" "uuid" NOT NULL,
    "policy_bundle_id" "uuid" NOT NULL,
    "result" "text" NOT NULL,
    "conditions" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "evidence_artifact_id" "uuid" NOT NULL,
    "decided_by_principal_id" "uuid" NOT NULL,
    "decided_at" timestamp with time zone NOT NULL,
    "expires_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_policy_gate_code" CHECK (("gate_code" = ANY (ARRAY['GATE-0'::"text", 'GATE-1'::"text", 'GATE-2'::"text", 'GATE-3'::"text", 'GATE-4'::"text"]))),
    CONSTRAINT "ck_policy_gate_conditions" CHECK (("jsonb_typeof"("conditions") = 'object'::"text")),
    CONSTRAINT "ck_policy_gate_expiry" CHECK ((("expires_at" IS NULL) OR ("expires_at" > "decided_at"))),
    CONSTRAINT "ck_policy_gate_result" CHECK (("result" = ANY (ARRAY['PASS'::"text", 'FAIL'::"text", 'CONDITIONAL'::"text"]))),
    CONSTRAINT "ck_policy_gate_scope" CHECK (("scope_type" = ANY (ARRAY['SITE'::"text", 'CATEGORY'::"text", 'ARTICLE_TYPE'::"text", 'RELEASE'::"text"])))
);

--
-- Name: TABLE "gate_decision"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON TABLE "policy"."gate_decision" IS 'GATE-0～4のscope別Pass/Fail/Conditional判定、根拠Artifact、条件、有効期限を追記する。';

--
-- Name: COLUMN "gate_decision"."id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."gate_decision"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "gate_decision"."display_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."gate_decision"."display_id" IS 'GTD-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "gate_decision"."gate_code"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."gate_decision"."gate_code" IS 'gate code';

--
-- Name: COLUMN "gate_decision"."scope_type"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."gate_decision"."scope_type" IS 'scope type';

--
-- Name: COLUMN "gate_decision"."scope_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."gate_decision"."scope_id" IS 'scope id';

--
-- Name: COLUMN "gate_decision"."policy_bundle_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."gate_decision"."policy_bundle_id" IS 'policy bundle id';

--
-- Name: COLUMN "gate_decision"."result"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."gate_decision"."result" IS 'result';

--
-- Name: COLUMN "gate_decision"."conditions"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."gate_decision"."conditions" IS 'Conditional passの未達・期限・scale limit。';

--
-- Name: COLUMN "gate_decision"."evidence_artifact_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."gate_decision"."evidence_artifact_id" IS 'evidence artifact id';

--
-- Name: COLUMN "gate_decision"."decided_by_principal_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."gate_decision"."decided_by_principal_id" IS 'decided by principal id';

--
-- Name: COLUMN "gate_decision"."decided_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."gate_decision"."decided_at" IS 'decided at';

--
-- Name: COLUMN "gate_decision"."expires_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."gate_decision"."expires_at" IS 'expires at';

--
-- Name: COLUMN "gate_decision"."created_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."gate_decision"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: policy_bundle; Type: TABLE; Schema: policy; Owner: -
--

CREATE TABLE "policy"."policy_bundle" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "bundle_code" "text" NOT NULL,
    "version_no" integer NOT NULL,
    "status" "text" NOT NULL,
    "git_commit_sha" "text" NOT NULL,
    "bundle_sha256" "text" NOT NULL,
    "effective_from" timestamp with time zone,
    "effective_to" timestamp with time zone,
    "approved_by_principal_id" "uuid",
    "approved_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_policy_bundle_approval" CHECK ((("status" <> 'ACTIVE'::"text") OR (("approved_by_principal_id" IS NOT NULL) AND ("approved_at" IS NOT NULL)))),
    CONSTRAINT "ck_policy_bundle_git" CHECK (("git_commit_sha" ~ '^[0-9a-f]{40,64}$'::"text")),
    CONSTRAINT "ck_policy_bundle_hash" CHECK (("bundle_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_policy_bundle_status" CHECK (("status" = ANY (ARRAY['DRAFT'::"text", 'ACTIVE'::"text", 'RETIRED'::"text", 'REJECTED'::"text"]))),
    CONSTRAINT "ck_policy_bundle_version" CHECK (("version_no" >= 1)),
    CONSTRAINT "ck_policy_bundle_window" CHECK ((("effective_to" IS NULL) OR ("effective_from" IS NULL) OR ("effective_to" > "effective_from")))
);

--
-- Name: TABLE "policy_bundle"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON TABLE "policy"."policy_bundle" IS '規約・品質・鮮度・Security Rule集合をVersion、Git commit、hash、承認、有効期間で固定する。';

--
-- Name: COLUMN "policy_bundle"."id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."policy_bundle"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "policy_bundle"."display_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."policy_bundle"."display_id" IS 'POL-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "policy_bundle"."bundle_code"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."policy_bundle"."bundle_code" IS 'bundle code';

--
-- Name: COLUMN "policy_bundle"."version_no"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."policy_bundle"."version_no" IS 'Aggregate内で1から増加する不変Version番号。';

--
-- Name: COLUMN "policy_bundle"."status"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."policy_bundle"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "policy_bundle"."git_commit_sha"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."policy_bundle"."git_commit_sha" IS 'git commit sha';

--
-- Name: COLUMN "policy_bundle"."bundle_sha256"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."policy_bundle"."bundle_sha256" IS 'bundle sha256';

--
-- Name: COLUMN "policy_bundle"."effective_from"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."policy_bundle"."effective_from" IS '設定・関係が有効になる時刻。';

--
-- Name: COLUMN "policy_bundle"."effective_to"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."policy_bundle"."effective_to" IS '設定・関係の有効終了時刻。NULLは終了未定。';

--
-- Name: COLUMN "policy_bundle"."approved_by_principal_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."policy_bundle"."approved_by_principal_id" IS 'approved by principal id';

--
-- Name: COLUMN "policy_bundle"."approved_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."policy_bundle"."approved_at" IS 'approved at';

--
-- Name: COLUMN "policy_bundle"."created_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."policy_bundle"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: quality_check_run; Type: TABLE; Schema: policy; Owner: -
--

CREATE TABLE "policy"."quality_check_run" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "article_version_id" "uuid" NOT NULL,
    "source_packet_version_id" "uuid" NOT NULL,
    "policy_bundle_id" "uuid" NOT NULL,
    "status" "text" NOT NULL,
    "triggered_by_actor_type" "text" NOT NULL,
    "triggered_by_actor_id" "uuid",
    "started_at" timestamp with time zone NOT NULL,
    "completed_at" timestamp with time zone,
    "total_score" numeric(5,2),
    "blocking_finding_count" integer DEFAULT 0 NOT NULL,
    "report_artifact_id" "uuid",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_policy_check_actor" CHECK (("triggered_by_actor_type" = ANY (ARRAY['USER'::"text", 'SERVICE'::"text", 'SYSTEM'::"text"]))),
    CONSTRAINT "ck_policy_check_blocking" CHECK (("blocking_finding_count" >= 0)),
    CONSTRAINT "ck_policy_check_complete" CHECK ((("status" = 'RUNNING'::"text") OR ("completed_at" IS NOT NULL))),
    CONSTRAINT "ck_policy_check_score" CHECK ((("total_score" IS NULL) OR (("total_score" >= (0)::numeric) AND ("total_score" <= (100)::numeric)))),
    CONSTRAINT "ck_policy_check_status" CHECK (("status" = ANY (ARRAY['RUNNING'::"text", 'PASSED'::"text", 'FAILED'::"text", 'ERROR'::"text", 'CANCELLED'::"text"])))
);

--
-- Name: TABLE "quality_check_run"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON TABLE "policy"."quality_check_run" IS 'Article Versionを特定Source Packet/Policy Bundleで検査したRunとReport Artifact。';

--
-- Name: COLUMN "quality_check_run"."id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_check_run"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "quality_check_run"."display_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_check_run"."display_id" IS 'QCR-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "quality_check_run"."article_version_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_check_run"."article_version_id" IS '記事の特定Version。';

--
-- Name: COLUMN "quality_check_run"."source_packet_version_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_check_run"."source_packet_version_id" IS 'source packet version id';

--
-- Name: COLUMN "quality_check_run"."policy_bundle_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_check_run"."policy_bundle_id" IS 'policy bundle id';

--
-- Name: COLUMN "quality_check_run"."status"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_check_run"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "quality_check_run"."triggered_by_actor_type"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_check_run"."triggered_by_actor_type" IS 'triggered by actor type';

--
-- Name: COLUMN "quality_check_run"."triggered_by_actor_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_check_run"."triggered_by_actor_id" IS 'triggered by actor id';

--
-- Name: COLUMN "quality_check_run"."started_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_check_run"."started_at" IS 'started at';

--
-- Name: COLUMN "quality_check_run"."completed_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_check_run"."completed_at" IS 'completed at';

--
-- Name: COLUMN "quality_check_run"."total_score"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_check_run"."total_score" IS 'total score';

--
-- Name: COLUMN "quality_check_run"."blocking_finding_count"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_check_run"."blocking_finding_count" IS 'blocking finding count';

--
-- Name: COLUMN "quality_check_run"."report_artifact_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_check_run"."report_artifact_id" IS 'report artifact id';

--
-- Name: COLUMN "quality_check_run"."created_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_check_run"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: quality_score; Type: TABLE; Schema: policy; Owner: -
--

CREATE TABLE "policy"."quality_score" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "quality_check_run_id" "uuid" NOT NULL,
    "score_version" "text" NOT NULL,
    "total_score" numeric(5,2) NOT NULL,
    "pass_score" numeric(5,2) NOT NULL,
    "factual_accuracy_score" numeric(5,2) NOT NULL,
    "disclosure_policy_score" numeric(5,2) NOT NULL,
    "passed" boolean NOT NULL,
    "components" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_policy_score_components" CHECK (("jsonb_typeof"("components") = 'object'::"text")),
    CONSTRAINT "ck_policy_score_disclosure" CHECK ((("disclosure_policy_score" >= (0)::numeric) AND ("disclosure_policy_score" <= (5)::numeric))),
    CONSTRAINT "ck_policy_score_factual" CHECK ((("factual_accuracy_score" >= (0)::numeric) AND ("factual_accuracy_score" <= (20)::numeric))),
    CONSTRAINT "ck_policy_score_pass" CHECK ((("pass_score" >= (0)::numeric) AND ("pass_score" <= (100)::numeric))),
    CONSTRAINT "ck_policy_score_pass_logic" CHECK (("passed" = (("total_score" >= "pass_score") AND ("factual_accuracy_score" >= (18)::numeric) AND ("disclosure_policy_score" = (5)::numeric)))),
    CONSTRAINT "ck_policy_score_total" CHECK ((("total_score" >= (0)::numeric) AND ("total_score" <= (100)::numeric)))
);

--
-- Name: TABLE "quality_score"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON TABLE "policy"."quality_score" IS 'Quality Runの100点評価、必須Subscore、Pass threshold、判定、内訳JSON。';

--
-- Name: COLUMN "quality_score"."id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_score"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "quality_score"."quality_check_run_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_score"."quality_check_run_id" IS 'quality check run id';

--
-- Name: COLUMN "quality_score"."score_version"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_score"."score_version" IS 'score version';

--
-- Name: COLUMN "quality_score"."total_score"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_score"."total_score" IS 'total score';

--
-- Name: COLUMN "quality_score"."pass_score"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_score"."pass_score" IS 'pass score';

--
-- Name: COLUMN "quality_score"."factual_accuracy_score"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_score"."factual_accuracy_score" IS 'factual accuracy score';

--
-- Name: COLUMN "quality_score"."disclosure_policy_score"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_score"."disclosure_policy_score" IS 'disclosure policy score';

--
-- Name: COLUMN "quality_score"."passed"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_score"."passed" IS 'passed';

--
-- Name: COLUMN "quality_score"."components"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_score"."components" IS '8評価軸のearned/max/reason。';

--
-- Name: COLUMN "quality_score"."created_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."quality_score"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: rule_version; Type: TABLE; Schema: policy; Owner: -
--

CREATE TABLE "policy"."rule_version" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "rule_code" "text" NOT NULL,
    "version_no" integer NOT NULL,
    "rule_category" "text" NOT NULL,
    "severity" "text" NOT NULL,
    "is_blocking" boolean NOT NULL,
    "implementation_type" "text" NOT NULL,
    "definition" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "definition_sha256" "text" NOT NULL,
    "status" "text" NOT NULL,
    "created_by_principal_id" "uuid" NOT NULL,
    "approved_by_principal_id" "uuid",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_policy_rule_category" CHECK (("rule_category" = ANY (ARRAY['COMPLIANCE'::"text", 'FACTUAL'::"text", 'QUALITY'::"text", 'FRESHNESS'::"text", 'LINK'::"text", 'SECURITY'::"text", 'ACCESSIBILITY'::"text", 'SEO'::"text"]))),
    CONSTRAINT "ck_policy_rule_definition" CHECK (("jsonb_typeof"("definition") = 'object'::"text")),
    CONSTRAINT "ck_policy_rule_hash" CHECK (("definition_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_policy_rule_impl" CHECK (("implementation_type" = ANY (ARRAY['PYTHON'::"text", 'SQL'::"text", 'REGEX'::"text", 'JSON_SCHEMA'::"text", 'MANUAL'::"text"]))),
    CONSTRAINT "ck_policy_rule_severity" CHECK (("severity" = ANY (ARRAY['INFO'::"text", 'LOW'::"text", 'MEDIUM'::"text", 'HIGH'::"text", 'CRITICAL'::"text"]))),
    CONSTRAINT "ck_policy_rule_status" CHECK (("status" = ANY (ARRAY['DRAFT'::"text", 'ACTIVE'::"text", 'RETIRED'::"text", 'REJECTED'::"text"]))),
    CONSTRAINT "ck_policy_rule_version" CHECK (("version_no" >= 1))
);

--
-- Name: TABLE "rule_version"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON TABLE "policy"."rule_version" IS '個別RuleのCategory、Severity、Blocking、Implementation、定義、hashをVersion管理する。';

--
-- Name: COLUMN "rule_version"."id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."rule_version"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "rule_version"."rule_code"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."rule_version"."rule_code" IS 'rule code';

--
-- Name: COLUMN "rule_version"."version_no"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."rule_version"."version_no" IS 'Aggregate内で1から増加する不変Version番号。';

--
-- Name: COLUMN "rule_version"."rule_category"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."rule_version"."rule_category" IS 'rule category';

--
-- Name: COLUMN "rule_version"."severity"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."rule_version"."severity" IS 'severity';

--
-- Name: COLUMN "rule_version"."is_blocking"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."rule_version"."is_blocking" IS 'is blocking';

--
-- Name: COLUMN "rule_version"."implementation_type"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."rule_version"."implementation_type" IS 'implementation type';

--
-- Name: COLUMN "rule_version"."definition"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."rule_version"."definition" IS 'Regex、threshold、field、manual checklist等のRule定義。';

--
-- Name: COLUMN "rule_version"."definition_sha256"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."rule_version"."definition_sha256" IS 'definition sha256';

--
-- Name: COLUMN "rule_version"."status"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."rule_version"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "rule_version"."created_by_principal_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."rule_version"."created_by_principal_id" IS '作成操作を行ったIAM Principal。';

--
-- Name: COLUMN "rule_version"."approved_by_principal_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."rule_version"."approved_by_principal_id" IS 'approved by principal id';

--
-- Name: COLUMN "rule_version"."created_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."rule_version"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: waiver; Type: TABLE; Schema: policy; Owner: -
--

CREATE TABLE "policy"."waiver" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "finding_id" "uuid" NOT NULL,
    "scope_type" "text" NOT NULL,
    "scope_id" "uuid" NOT NULL,
    "justification" "text" NOT NULL,
    "status" "text" DEFAULT 'REQUESTED'::"text" NOT NULL,
    "requested_by_principal_id" "uuid" NOT NULL,
    "requested_at" timestamp with time zone NOT NULL,
    "decided_by_principal_id" "uuid",
    "decided_at" timestamp with time zone,
    "decision_reason" "text",
    "expires_at" timestamp with time zone,
    "revoked_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_policy_waiver_decision_pair" CHECK ((("status" = 'REQUESTED'::"text") OR (("decided_by_principal_id" IS NOT NULL) AND ("decided_at" IS NOT NULL)))),
    CONSTRAINT "ck_policy_waiver_expiry" CHECK ((("expires_at" IS NULL) OR ("expires_at" > "requested_at"))),
    CONSTRAINT "ck_policy_waiver_scope" CHECK (("scope_type" = ANY (ARRAY['FINDING'::"text", 'ARTICLE_VERSION'::"text", 'ARTICLE'::"text", 'CATEGORY'::"text"]))),
    CONSTRAINT "ck_policy_waiver_status" CHECK (("status" = ANY (ARRAY['REQUESTED'::"text", 'APPROVED'::"text", 'REJECTED'::"text", 'EXPIRED'::"text", 'REVOKED'::"text"])))
);

--
-- Name: TABLE "waiver"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON TABLE "policy"."waiver" IS 'Findingの例外申請・承認・期限・Scopeを管理する。Critical zero-tolerance RuleはDB/Serviceで申請不可にする。';

--
-- Name: COLUMN "waiver"."id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."waiver"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "waiver"."display_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."waiver"."display_id" IS 'WVR-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "waiver"."finding_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."waiver"."finding_id" IS 'finding id';

--
-- Name: COLUMN "waiver"."scope_type"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."waiver"."scope_type" IS 'scope type';

--
-- Name: COLUMN "waiver"."scope_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."waiver"."scope_id" IS 'scope id';

--
-- Name: COLUMN "waiver"."justification"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."waiver"."justification" IS 'justification';

--
-- Name: COLUMN "waiver"."status"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."waiver"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "waiver"."requested_by_principal_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."waiver"."requested_by_principal_id" IS 'requested by principal id';

--
-- Name: COLUMN "waiver"."requested_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."waiver"."requested_at" IS 'requested at';

--
-- Name: COLUMN "waiver"."decided_by_principal_id"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."waiver"."decided_by_principal_id" IS 'decided by principal id';

--
-- Name: COLUMN "waiver"."decided_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."waiver"."decided_at" IS 'decided at';

--
-- Name: COLUMN "waiver"."decision_reason"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."waiver"."decision_reason" IS 'decision reason';

--
-- Name: COLUMN "waiver"."expires_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."waiver"."expires_at" IS 'expires at';

--
-- Name: COLUMN "waiver"."revoked_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."waiver"."revoked_at" IS 'revoked at';

--
-- Name: COLUMN "waiver"."created_at"; Type: COMMENT; Schema: policy; Owner: -
--

COMMENT ON COLUMN "policy"."waiver"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: action_candidate; Type: TABLE; Schema: portfolio; Owner: -
--

CREATE TABLE "portfolio"."action_candidate" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "site_id" "uuid" NOT NULL,
    "category_id" "uuid",
    "action_type" "text" NOT NULL,
    "target_entity_type" "text" NOT NULL,
    "target_entity_id" "uuid",
    "secondary_entity_id" "uuid",
    "source_signal" "text" NOT NULL,
    "expected_incremental_profit_jpy" bigint,
    "urgency_score" numeric(5,2) NOT NULL,
    "confidence" numeric(5,4) NOT NULL,
    "priority_score" numeric(8,3) NOT NULL,
    "status" "text" DEFAULT 'PROPOSED'::"text" NOT NULL,
    "rationale" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "generated_at" timestamp with time zone NOT NULL,
    "expires_at" timestamp with time zone,
    "decided_by_principal_id" "uuid",
    "decided_at" timestamp with time zone,
    "decision_note" "text",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    CONSTRAINT "ck_portfolio_action_conf" CHECK ((("confidence" >= (0)::numeric) AND ("confidence" <= (1)::numeric))),
    CONSTRAINT "ck_portfolio_action_decision_pair" CHECK ((("decided_by_principal_id" IS NULL) = ("decided_at" IS NULL))),
    CONSTRAINT "ck_portfolio_action_expiry" CHECK ((("expires_at" IS NULL) OR ("expires_at" > "generated_at"))),
    CONSTRAINT "ck_portfolio_action_rationale" CHECK (("jsonb_typeof"("rationale") = 'object'::"text")),
    CONSTRAINT "ck_portfolio_action_status" CHECK (("status" = ANY (ARRAY['PROPOSED'::"text", 'ACCEPTED'::"text", 'REJECTED'::"text", 'IN_PROGRESS'::"text", 'COMPLETED'::"text", 'EXPIRED'::"text"]))),
    CONSTRAINT "ck_portfolio_action_target" CHECK (("target_entity_type" = ANY (ARRAY['CATEGORY'::"text", 'CLUSTER'::"text", 'KEYWORD'::"text", 'ARTICLE_PLAN'::"text", 'ARTICLE'::"text", 'PRODUCT'::"text", 'OFFER'::"text"]))),
    CONSTRAINT "ck_portfolio_action_type" CHECK (("action_type" = ANY (ARRAY['CREATE'::"text", 'UPDATE'::"text", 'MERGE'::"text", 'DELETE'::"text", 'ARCHIVE'::"text", 'PAUSE'::"text", 'HOLD'::"text", 'INVESTIGATE'::"text"]))),
    CONSTRAINT "ck_portfolio_action_urgency" CHECK ((("urgency_score" >= (0)::numeric) AND ("urgency_score" <= (100)::numeric))),
    CONSTRAINT "ck_portfolio_action_version" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "action_candidate"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON TABLE "portfolio"."action_candidate" IS '新規作成・更新・統合・削除・保留の候補を、期待増分利益・緊急度・信頼度とともに管理する。';

--
-- Name: COLUMN "action_candidate"."id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "action_candidate"."display_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."display_id" IS 'ACT-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "action_candidate"."site_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."site_id" IS '対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。';

--
-- Name: COLUMN "action_candidate"."category_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."category_id" IS '対象カテゴリ。';

--
-- Name: COLUMN "action_candidate"."action_type"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."action_type" IS 'action type';

--
-- Name: COLUMN "action_candidate"."target_entity_type"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."target_entity_type" IS 'target entity type';

--
-- Name: COLUMN "action_candidate"."target_entity_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."target_entity_id" IS 'target entity id';

--
-- Name: COLUMN "action_candidate"."secondary_entity_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."secondary_entity_id" IS 'secondary entity id';

--
-- Name: COLUMN "action_candidate"."source_signal"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."source_signal" IS 'source signal';

--
-- Name: COLUMN "action_candidate"."expected_incremental_profit_jpy"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."expected_incremental_profit_jpy" IS 'expected incremental profit jpy';

--
-- Name: COLUMN "action_candidate"."urgency_score"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."urgency_score" IS 'urgency score';

--
-- Name: COLUMN "action_candidate"."confidence"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."confidence" IS 'confidence';

--
-- Name: COLUMN "action_candidate"."priority_score"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."priority_score" IS 'priority score';

--
-- Name: COLUMN "action_candidate"."status"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "action_candidate"."rationale"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."rationale" IS 'rationale';

--
-- Name: COLUMN "action_candidate"."generated_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."generated_at" IS 'generated at';

--
-- Name: COLUMN "action_candidate"."expires_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."expires_at" IS 'expires at';

--
-- Name: COLUMN "action_candidate"."decided_by_principal_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."decided_by_principal_id" IS 'decided by principal id';

--
-- Name: COLUMN "action_candidate"."decided_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."decided_at" IS 'decided at';

--
-- Name: COLUMN "action_candidate"."decision_note"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."decision_note" IS 'decision note';

--
-- Name: COLUMN "action_candidate"."created_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "action_candidate"."updated_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "action_candidate"."lock_version"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."action_candidate"."lock_version" IS '楽観的排他制御用の単調増加Version。';

--
-- Name: category; Type: TABLE; Schema: portfolio; Owner: -
--

CREATE TABLE "portfolio"."category" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "site_id" "uuid" NOT NULL,
    "parent_category_id" "uuid",
    "category_code" "text" NOT NULL,
    "name" "text" NOT NULL,
    "description" "text",
    "risk_class" "text" NOT NULL,
    "stage" "text" DEFAULT 'CANDIDATE'::"text" NOT NULL,
    "article_limit" integer,
    "approved_at" timestamp with time zone,
    "approved_by_principal_id" "uuid",
    "entry_criteria" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    CONSTRAINT "ck_portfolio_category_approval" CHECK ((("stage" <> ALL (ARRAY['APPROVED'::"text", 'ACTIVE'::"text"])) OR (("approved_at" IS NOT NULL) AND ("approved_by_principal_id" IS NOT NULL)))),
    CONSTRAINT "ck_portfolio_category_entry" CHECK (("jsonb_typeof"("entry_criteria") = 'object'::"text")),
    CONSTRAINT "ck_portfolio_category_limit" CHECK ((("article_limit" IS NULL) OR ("article_limit" >= 0))),
    CONSTRAINT "ck_portfolio_category_parent" CHECK ((("parent_category_id" IS NULL) OR ("parent_category_id" <> "id"))),
    CONSTRAINT "ck_portfolio_category_risk" CHECK (("risk_class" = ANY (ARRAY['LOW'::"text", 'MEDIUM'::"text", 'HIGH'::"text", 'PROHIBITED'::"text"]))),
    CONSTRAINT "ck_portfolio_category_stage" CHECK (("stage" = ANY (ARRAY['CANDIDATE'::"text", 'RESEARCH'::"text", 'APPROVED'::"text", 'ACTIVE'::"text", 'PAUSED'::"text", 'RETIRED'::"text", 'REJECTED'::"text"]))),
    CONSTRAINT "ck_portfolio_category_version" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "category"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON TABLE "portfolio"."category" IS '運営上のCategory階層、Risk、Gate stage、公開上限、承認を管理する。';

--
-- Name: COLUMN "category"."id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."category"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "category"."display_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."category"."display_id" IS 'CAT-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "category"."site_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."category"."site_id" IS '対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。';

--
-- Name: COLUMN "category"."parent_category_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."category"."parent_category_id" IS 'parent category id';

--
-- Name: COLUMN "category"."category_code"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."category"."category_code" IS 'category code';

--
-- Name: COLUMN "category"."name"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."category"."name" IS 'name';

--
-- Name: COLUMN "category"."description"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."category"."description" IS 'description';

--
-- Name: COLUMN "category"."risk_class"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."category"."risk_class" IS 'risk class';

--
-- Name: COLUMN "category"."stage"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."category"."stage" IS 'stage';

--
-- Name: COLUMN "category"."article_limit"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."category"."article_limit" IS 'article limit';

--
-- Name: COLUMN "category"."approved_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."category"."approved_at" IS 'approved at';

--
-- Name: COLUMN "category"."approved_by_principal_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."category"."approved_by_principal_id" IS 'approved by principal id';

--
-- Name: COLUMN "category"."entry_criteria"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."category"."entry_criteria" IS '当該Categoryへ参入するための定量・定性基準。';

--
-- Name: COLUMN "category"."created_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."category"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "category"."updated_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."category"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "category"."lock_version"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."category"."lock_version" IS '楽観的排他制御用の単調増加Version。';

--
-- Name: intent_cluster; Type: TABLE; Schema: portfolio; Owner: -
--

CREATE TABLE "portfolio"."intent_cluster" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "category_id" "uuid" NOT NULL,
    "cluster_code" "text" NOT NULL,
    "name" "text" NOT NULL,
    "description" "text" NOT NULL,
    "intent_type" "text" NOT NULL,
    "status" "text" DEFAULT 'ACTIVE'::"text" NOT NULL,
    "decision_requirements" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    CONSTRAINT "ck_portfolio_intent_requirements" CHECK (("jsonb_typeof"("decision_requirements") = 'object'::"text")),
    CONSTRAINT "ck_portfolio_intent_status" CHECK (("status" = ANY (ARRAY['ACTIVE'::"text", 'PAUSED'::"text", 'RETIRED'::"text"]))),
    CONSTRAINT "ck_portfolio_intent_type" CHECK (("intent_type" = ANY (ARRAY['SELECTION_GUIDE'::"text", 'USE_CASE'::"text", 'COMPARISON'::"text", 'MODEL_DIFFERENCE'::"text", 'CONDITION_FILTER'::"text", 'INFORMATIONAL_SUPPORT'::"text"]))),
    CONSTRAINT "ck_portfolio_intent_version" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "intent_cluster"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON TABLE "portfolio"."intent_cluster" IS 'Category内の検索意図Cluster。Article PlanとKeywordを結び、同一意図の重複記事を防ぐ。';

--
-- Name: COLUMN "intent_cluster"."id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."intent_cluster"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "intent_cluster"."display_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."intent_cluster"."display_id" IS 'INT-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "intent_cluster"."category_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."intent_cluster"."category_id" IS '対象カテゴリ。';

--
-- Name: COLUMN "intent_cluster"."cluster_code"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."intent_cluster"."cluster_code" IS 'cluster code';

--
-- Name: COLUMN "intent_cluster"."name"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."intent_cluster"."name" IS 'name';

--
-- Name: COLUMN "intent_cluster"."description"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."intent_cluster"."description" IS 'description';

--
-- Name: COLUMN "intent_cluster"."intent_type"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."intent_cluster"."intent_type" IS 'intent type';

--
-- Name: COLUMN "intent_cluster"."status"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."intent_cluster"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "intent_cluster"."decision_requirements"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."intent_cluster"."decision_requirements" IS 'ユーザーが当該意図で判断するために必要な比較軸・疑問・不安。';

--
-- Name: COLUMN "intent_cluster"."created_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."intent_cluster"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "intent_cluster"."updated_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."intent_cluster"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "intent_cluster"."lock_version"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."intent_cluster"."lock_version" IS '楽観的排他制御用の単調増加Version。';

--
-- Name: intent_cluster_keyword; Type: TABLE; Schema: portfolio; Owner: -
--

CREATE TABLE "portfolio"."intent_cluster_keyword" (
    "intent_cluster_id" "uuid" NOT NULL,
    "keyword_id" "uuid" NOT NULL,
    "keyword_role" "text" NOT NULL,
    "priority" smallint DEFAULT 50 NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_portfolio_cluster_keyword_priority" CHECK ((("priority" >= 0) AND ("priority" <= 100))),
    CONSTRAINT "ck_portfolio_cluster_keyword_role" CHECK (("keyword_role" = ANY (ARRAY['PRIMARY'::"text", 'SECONDARY'::"text", 'QUESTION'::"text", 'EXCLUSION'::"text"])))
);

--
-- Name: TABLE "intent_cluster_keyword"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON TABLE "portfolio"."intent_cluster_keyword" IS 'Intent Cluster内でKeywordをprimary、secondary、question、exclusionに分類する。';

--
-- Name: COLUMN "intent_cluster_keyword"."intent_cluster_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."intent_cluster_keyword"."intent_cluster_id" IS 'intent cluster id';

--
-- Name: COLUMN "intent_cluster_keyword"."keyword_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."intent_cluster_keyword"."keyword_id" IS 'keyword id';

--
-- Name: COLUMN "intent_cluster_keyword"."keyword_role"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."intent_cluster_keyword"."keyword_role" IS 'keyword role';

--
-- Name: COLUMN "intent_cluster_keyword"."priority"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."intent_cluster_keyword"."priority" IS 'priority';

--
-- Name: COLUMN "intent_cluster_keyword"."created_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."intent_cluster_keyword"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: keyword; Type: TABLE; Schema: portfolio; Owner: -
--

CREATE TABLE "portfolio"."keyword" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "site_id" "uuid" NOT NULL,
    "display_text" "text" NOT NULL,
    "normalized_text" "text" NOT NULL,
    "locale" "text" DEFAULT 'ja-JP'::"text" NOT NULL,
    "status" "text" DEFAULT 'ACTIVE'::"text" NOT NULL,
    "sensitive_query" boolean DEFAULT false NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    CONSTRAINT "ck_portfolio_keyword_status" CHECK (("status" = ANY (ARRAY['ACTIVE'::"text", 'PAUSED'::"text", 'RETIRED'::"text", 'BLOCKED'::"text"]))),
    CONSTRAINT "ck_portfolio_keyword_version" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "keyword"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON TABLE "portfolio"."keyword" IS '検索Queryを表示形と正規化形に分け、文字列変更に依存しないStable IDを付与する。';

--
-- Name: COLUMN "keyword"."id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "keyword"."display_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword"."display_id" IS 'KW-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "keyword"."site_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword"."site_id" IS '対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。';

--
-- Name: COLUMN "keyword"."display_text"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword"."display_text" IS 'display text';

--
-- Name: COLUMN "keyword"."normalized_text"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword"."normalized_text" IS 'normalized text';

--
-- Name: COLUMN "keyword"."locale"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword"."locale" IS 'locale';

--
-- Name: COLUMN "keyword"."status"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "keyword"."sensitive_query"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword"."sensitive_query" IS 'sensitive query';

--
-- Name: COLUMN "keyword"."created_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "keyword"."updated_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "keyword"."lock_version"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword"."lock_version" IS '楽観的排他制御用の単調増加Version。';

--
-- Name: keyword_metric_observation; Type: TABLE; Schema: portfolio; Owner: -
--

CREATE TABLE "portfolio"."keyword_metric_observation" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "keyword_id" "uuid" NOT NULL,
    "provider_code" "text" NOT NULL,
    "metric_type" "text" NOT NULL,
    "metric_value" numeric(24,8) NOT NULL,
    "unit" "text" NOT NULL,
    "country_code" "text" DEFAULT 'JP'::"text" NOT NULL,
    "device" "text" DEFAULT 'ALL'::"text" NOT NULL,
    "observed_date" "date" NOT NULL,
    "confidence" numeric(5,4),
    "raw_artifact_id" "uuid",
    "ingested_at" timestamp with time zone NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_portfolio_kw_metric_conf" CHECK ((("confidence" IS NULL) OR (("confidence" >= (0)::numeric) AND ("confidence" <= (1)::numeric)))),
    CONSTRAINT "ck_portfolio_kw_metric_device" CHECK (("device" = ANY (ARRAY['ALL'::"text", 'DESKTOP'::"text", 'MOBILE'::"text", 'TABLET'::"text"]))),
    CONSTRAINT "ck_portfolio_kw_metric_type" CHECK (("metric_type" = ANY (ARRAY['SEARCH_VOLUME'::"text", 'COMPETITION'::"text", 'RANK'::"text", 'CPC'::"text", 'TREND_INDEX'::"text", 'RESULT_COUNT_ESTIMATE'::"text"])))
);

--
-- Name: TABLE "keyword_metric_observation"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON TABLE "portfolio"."keyword_metric_observation" IS '許諾済みProviderまたはCSVから得た検索需要、競争、順位、Trend等の時点Observation。';

--
-- Name: COLUMN "keyword_metric_observation"."id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword_metric_observation"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "keyword_metric_observation"."keyword_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword_metric_observation"."keyword_id" IS 'keyword id';

--
-- Name: COLUMN "keyword_metric_observation"."provider_code"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword_metric_observation"."provider_code" IS 'provider code';

--
-- Name: COLUMN "keyword_metric_observation"."metric_type"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword_metric_observation"."metric_type" IS 'metric type';

--
-- Name: COLUMN "keyword_metric_observation"."metric_value"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword_metric_observation"."metric_value" IS 'metric value';

--
-- Name: COLUMN "keyword_metric_observation"."unit"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword_metric_observation"."unit" IS 'unit';

--
-- Name: COLUMN "keyword_metric_observation"."country_code"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword_metric_observation"."country_code" IS 'country code';

--
-- Name: COLUMN "keyword_metric_observation"."device"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword_metric_observation"."device" IS 'device';
