-- ST-0304 physical translation fragment 06 of 11.
-- Source: approved RAOS data catalog plus finalized ST-0003/ST-0004 semantics.
-- Capture: PostgreSQL 18.4 pg_dump --schema-only --no-owner --no-privileges
--          --no-security-labels --quote-all-identifiers for the six owned schemas.
-- Schema creation/comments are rendered once by the ST-0304 generator. The 22
-- role-bound CREATE POLICY objects remain ST-0306-owned. ENABLE/FORCE RLS remains.

--
-- Name: TABLE "article_block_product"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON TABLE "editorial"."article_block_product" IS 'BlockへProduct/Offerをroleとposition付きで結ぶ。';

--
-- Name: COLUMN "article_block_product"."article_block_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_block_product"."article_block_id" IS 'article block id';

--
-- Name: COLUMN "article_block_product"."product_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_block_product"."product_id" IS '正規化されたCanonical Product。';

--
-- Name: COLUMN "article_block_product"."offer_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_block_product"."offer_id" IS 'ショップ単位の販売Offer。';

--
-- Name: COLUMN "article_block_product"."placement_role"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_block_product"."placement_role" IS 'placement role';

--
-- Name: COLUMN "article_block_product"."position"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_block_product"."position" IS 'position';

--
-- Name: COLUMN "article_block_product"."placement_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_block_product"."placement_id" IS 'placement id';

--
-- Name: COLUMN "article_block_product"."created_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_block_product"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: article_disclosure_context; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."article_disclosure_context" (
    "article_version_id" "uuid" NOT NULL,
    "affiliate_relationship" boolean DEFAULT true NOT NULL,
    "material_benefit_relationship" boolean DEFAULT false CONSTRAINT "article_disclosure_context_material_benefit_relationsh_not_null" NOT NULL,
    "benefit_types" "text"[] DEFAULT '{}'::"text"[] NOT NULL,
    "disclosure_policy_version" "text" NOT NULL,
    "additional_disclosure_text" "text",
    "reviewed_by_principal_id" "uuid",
    "reviewed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_editorial_article_disclosure_benefit" CHECK (((NOT "material_benefit_relationship") OR (("cardinality"("benefit_types") > 0) AND ("length"("btrim"(COALESCE("additional_disclosure_text", ''::"text"))) > 0)))),
    CONSTRAINT "ck_editorial_article_disclosure_no_orphan_benefit" CHECK (("material_benefit_relationship" OR ("cardinality"("benefit_types") = 0))),
    CONSTRAINT "ck_editorial_article_disclosure_policy" CHECK (("length"("btrim"("disclosure_policy_version")) > 0)),
    CONSTRAINT "ck_editorial_article_disclosure_review_pair" CHECK ((("reviewed_by_principal_id" IS NULL) = ("reviewed_at" IS NULL)))
);

ALTER TABLE ONLY "editorial"."article_disclosure_context" FORCE ROW LEVEL SECURITY;

--
-- Name: article_link; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."article_link" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "from_article_id" "uuid" NOT NULL,
    "to_article_id" "uuid" NOT NULL,
    "link_type" "text" NOT NULL,
    "anchor_text" "text",
    "source_block_key" "text",
    "status" "text" DEFAULT 'ACTIVE'::"text" NOT NULL,
    "reason" "text",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    CONSTRAINT "ck_editorial_article_link_self" CHECK (("from_article_id" <> "to_article_id")),
    CONSTRAINT "ck_editorial_article_link_status" CHECK (("status" = ANY (ARRAY['ACTIVE'::"text", 'PAUSED'::"text", 'REMOVED'::"text"]))),
    CONSTRAINT "ck_editorial_article_link_type" CHECK (("link_type" = ANY (ARRAY['INTERNAL'::"text", 'RELATED'::"text", 'CANONICAL_REFERENCE'::"text"]))),
    CONSTRAINT "ck_editorial_article_link_version" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "article_link"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON TABLE "editorial"."article_link" IS '記事間のInternal/Related/Canonical link intentを管理し、公開時に安全なRouteへ解決する。';

--
-- Name: COLUMN "article_link"."id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_link"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "article_link"."from_article_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_link"."from_article_id" IS 'from article id';

--
-- Name: COLUMN "article_link"."to_article_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_link"."to_article_id" IS 'to article id';

--
-- Name: COLUMN "article_link"."link_type"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_link"."link_type" IS 'link type';

--
-- Name: COLUMN "article_link"."anchor_text"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_link"."anchor_text" IS 'anchor text';

--
-- Name: COLUMN "article_link"."source_block_key"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_link"."source_block_key" IS 'source block key';

--
-- Name: COLUMN "article_link"."status"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_link"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "article_link"."reason"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_link"."reason" IS 'reason';

--
-- Name: COLUMN "article_link"."created_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_link"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "article_link"."updated_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_link"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "article_link"."lock_version"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_link"."lock_version" IS '楽観的排他制御用の単調増加Version。';

--
-- Name: article_methodology_binding; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."article_methodology_binding" (
    "article_version_id" "uuid" NOT NULL,
    "methodology_version_id" "uuid" NOT NULL,
    "candidate_universe_artifact_id" "uuid" CONSTRAINT "article_methodology_binding_candidate_universe_artifac_not_null" NOT NULL,
    "candidate_universe_sha256" "text" NOT NULL,
    "bound_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "bound_by_principal_id" "uuid" NOT NULL,
    CONSTRAINT "ck_editorial_article_methodology_candidate_sha" CHECK (("candidate_universe_sha256" ~ '^[0-9a-f]{64}$'::"text"))
);

ALTER TABLE ONLY "editorial"."article_methodology_binding" FORCE ROW LEVEL SECURITY;

--
-- Name: article_plan; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."article_plan" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "site_id" "uuid" NOT NULL,
    "category_id" "uuid" NOT NULL,
    "intent_cluster_id" "uuid" NOT NULL,
    "primary_keyword_id" "uuid" NOT NULL,
    "article_type" "text" NOT NULL,
    "working_title" "text" NOT NULL,
    "objective" "text" NOT NULL,
    "status" "text" DEFAULT 'IDEA'::"text" NOT NULL,
    "priority" smallint DEFAULT 50 NOT NULL,
    "opportunity_assessment_id" "uuid",
    "created_by_principal_id" "uuid" NOT NULL,
    "approved_by_principal_id" "uuid",
    "approved_at" timestamp with time zone,
    "brief" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    CONSTRAINT "ck_editorial_plan_approval" CHECK ((("status" <> 'APPROVED'::"text") OR (("approved_by_principal_id" IS NOT NULL) AND ("approved_at" IS NOT NULL)))),
    CONSTRAINT "ck_editorial_plan_brief" CHECK (("jsonb_typeof"("brief") = 'object'::"text")),
    CONSTRAINT "ck_editorial_plan_priority" CHECK ((("priority" >= 0) AND ("priority" <= 100))),
    CONSTRAINT "ck_editorial_plan_status" CHECK (("status" = ANY (ARRAY['IDEA'::"text", 'PLANNED'::"text", 'SOURCES_PENDING'::"text", 'PACKET_READY'::"text", 'GENERATING'::"text", 'DRAFT'::"text", 'IN_REVIEW'::"text", 'APPROVED'::"text", 'CANCELLED'::"text", 'ARCHIVED'::"text"]))),
    CONSTRAINT "ck_editorial_plan_type" CHECK (("article_type" = ANY (ARRAY['SELECTION_GUIDE'::"text", 'USE_CASE_RECOMMENDATION'::"text", 'PRODUCT_COMPARISON'::"text", 'MODEL_DIFFERENCE'::"text", 'CONDITION_FILTER'::"text"]))),
    CONSTRAINT "ck_editorial_plan_version" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "article_plan"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON TABLE "editorial"."article_plan" IS 'Category・Intent・Primary Keyword・Opportunityを結ぶ記事企画。公開記事より前の意思決定正本。';

--
-- Name: COLUMN "article_plan"."id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "article_plan"."display_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."display_id" IS 'PLAN-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "article_plan"."site_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."site_id" IS '対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。';

--
-- Name: COLUMN "article_plan"."category_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."category_id" IS '対象カテゴリ。';

--
-- Name: COLUMN "article_plan"."intent_cluster_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."intent_cluster_id" IS 'intent cluster id';

--
-- Name: COLUMN "article_plan"."primary_keyword_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."primary_keyword_id" IS 'primary keyword id';

--
-- Name: COLUMN "article_plan"."article_type"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."article_type" IS 'article type';

--
-- Name: COLUMN "article_plan"."working_title"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."working_title" IS 'working title';

--
-- Name: COLUMN "article_plan"."objective"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."objective" IS 'objective';

--
-- Name: COLUMN "article_plan"."status"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "article_plan"."priority"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."priority" IS 'priority';

--
-- Name: COLUMN "article_plan"."opportunity_assessment_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."opportunity_assessment_id" IS 'opportunity assessment id';

--
-- Name: COLUMN "article_plan"."created_by_principal_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."created_by_principal_id" IS '作成操作を行ったIAM Principal。';

--
-- Name: COLUMN "article_plan"."approved_by_principal_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."approved_by_principal_id" IS 'approved by principal id';

--
-- Name: COLUMN "article_plan"."approved_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."approved_at" IS 'approved at';

--
-- Name: COLUMN "article_plan"."brief"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."brief" IS 'Target user、decision questions、required sections、unique value hypothesis。';

--
-- Name: COLUMN "article_plan"."created_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "article_plan"."updated_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "article_plan"."lock_version"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_plan"."lock_version" IS '楽観的排他制御用の単調増加Version。';

--
-- Name: article_slug; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."article_slug" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "site_id" "uuid" NOT NULL,
    "article_id" "uuid" NOT NULL,
    "slug" "text" NOT NULL,
    "normalized_path" "text" NOT NULL,
    "status" "text" NOT NULL,
    "valid_from" timestamp with time zone NOT NULL,
    "valid_to" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_editorial_slug_path" CHECK (("normalized_path" ~ '^/[a-z0-9/_-]*$'::"text")),
    CONSTRAINT "ck_editorial_slug_status" CHECK (("status" = ANY (ARRAY['ACTIVE'::"text", 'REDIRECTED'::"text", 'RETIRED'::"text"]))),
    CONSTRAINT "ck_editorial_slug_window" CHECK ((("valid_to" IS NULL) OR ("valid_to" > "valid_from")))
);

--
-- Name: TABLE "article_slug"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON TABLE "editorial"."article_slug" IS 'Site内Pathの履歴。Slug変更時は既存行を上書きせずvalid_toを閉じ、新行を作る。';

--
-- Name: COLUMN "article_slug"."id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_slug"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "article_slug"."site_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_slug"."site_id" IS '対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。';

--
-- Name: COLUMN "article_slug"."article_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_slug"."article_id" IS '論理記事ID。';

--
-- Name: COLUMN "article_slug"."slug"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_slug"."slug" IS 'slug';

--
-- Name: COLUMN "article_slug"."normalized_path"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_slug"."normalized_path" IS 'normalized path';

--
-- Name: COLUMN "article_slug"."status"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_slug"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "article_slug"."valid_from"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_slug"."valid_from" IS 'valid from';

--
-- Name: COLUMN "article_slug"."valid_to"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_slug"."valid_to" IS 'valid to';

--
-- Name: COLUMN "article_slug"."created_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_slug"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: article_template_version; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."article_template_version" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "article_type_version_id" "uuid" NOT NULL,
    "semantic_version" "text" NOT NULL,
    "template" "jsonb" NOT NULL,
    "template_sha256" "text" NOT NULL,
    "status" "text" DEFAULT 'DRAFT'::"text" NOT NULL,
    "approved_by_principal_id" "uuid",
    "approved_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_editorial_article_template_active_approval" CHECK ((("status" <> 'ACTIVE'::"text") OR (("approved_by_principal_id" IS NOT NULL) AND ("approved_at" IS NOT NULL)))),
    CONSTRAINT "ck_editorial_article_template_approval_pair" CHECK ((("approved_by_principal_id" IS NULL) = ("approved_at" IS NULL))),
    CONSTRAINT "ck_editorial_article_template_semver" CHECK (("semantic_version" ~ '^[0-9]+\.[0-9]+\.[0-9]+([+-][0-9A-Za-z.-]+)?$'::"text")),
    CONSTRAINT "ck_editorial_article_template_sha" CHECK (("template_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_editorial_article_template_shape" CHECK (("jsonb_typeof"("template") = 'object'::"text")),
    CONSTRAINT "ck_editorial_article_template_status" CHECK (("status" = ANY (ARRAY['DRAFT'::"text", 'ACTIVE'::"text", 'DEPRECATED'::"text", 'RETIRED'::"text"])))
);

ALTER TABLE ONLY "editorial"."article_template_version" FORCE ROW LEVEL SECURITY;

--
-- Name: article_type_version; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."article_type_version" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "article_type_code" "text" NOT NULL,
    "semantic_version" "text" NOT NULL,
    "contract" "jsonb" NOT NULL,
    "contract_sha256" "text" NOT NULL,
    "status" "text" DEFAULT 'DRAFT'::"text" NOT NULL,
    "approved_by_principal_id" "uuid",
    "approved_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_editorial_article_type_active_approval" CHECK ((("status" <> 'ACTIVE'::"text") OR (("approved_by_principal_id" IS NOT NULL) AND ("approved_at" IS NOT NULL)))),
    CONSTRAINT "ck_editorial_article_type_approval_pair" CHECK ((("approved_by_principal_id" IS NULL) = ("approved_at" IS NULL))),
    CONSTRAINT "ck_editorial_article_type_code" CHECK (("article_type_code" ~ '^[a-z][a-z0-9_]{2,127}$'::"text")),
    CONSTRAINT "ck_editorial_article_type_contract" CHECK (("jsonb_typeof"("contract") = 'object'::"text")),
    CONSTRAINT "ck_editorial_article_type_semver" CHECK (("semantic_version" ~ '^[0-9]+\.[0-9]+\.[0-9]+([+-][0-9A-Za-z.-]+)?$'::"text")),
    CONSTRAINT "ck_editorial_article_type_sha" CHECK (("contract_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_editorial_article_type_status" CHECK (("status" = ANY (ARRAY['DRAFT'::"text", 'ACTIVE'::"text", 'DEPRECATED'::"text", 'RETIRED'::"text"])))
);

ALTER TABLE ONLY "editorial"."article_type_version" FORCE ROW LEVEL SECURITY;

--
-- Name: article_version; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."article_version" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "article_id" "uuid" NOT NULL,
    "version_no" integer NOT NULL,
    "content_schema_version" integer NOT NULL,
    "title" "text" NOT NULL,
    "meta_title" "text",
    "meta_description" "text",
    "excerpt" "text",
    "body_sha256" "text" NOT NULL,
    "status" "text" DEFAULT 'DRAFT'::"text" NOT NULL,
    "source_packet_version_id" "uuid" NOT NULL,
    "based_on_version_id" "uuid",
    "ai_job_id" "uuid",
    "created_by_actor_type" "text" NOT NULL,
    "created_by_actor_id" "uuid",
    "submitted_at" timestamp with time zone,
    "reviewed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    "content_schema_version_id" "uuid" NOT NULL,
    "article_type_version_id" "uuid" NOT NULL,
    "article_template_version_id" "uuid" NOT NULL,
    "seo_metadata_version_id" "uuid" NOT NULL,
    CONSTRAINT "ck_editorial_article_version_actor" CHECK (("created_by_actor_type" = ANY (ARRAY['USER'::"text", 'SERVICE'::"text", 'SYSTEM'::"text"]))),
    CONSTRAINT "ck_editorial_article_version_hash" CHECK (("body_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_editorial_article_version_lock" CHECK (("lock_version" >= 0)),
    CONSTRAINT "ck_editorial_article_version_num" CHECK ((("version_no" >= 1) AND ("content_schema_version" >= 1))),
    CONSTRAINT "ck_editorial_article_version_review" CHECK ((("status" <> ALL (ARRAY['HUMAN_REVIEW'::"text", 'APPROVED'::"text", 'REJECTED'::"text"])) OR ("submitted_at" IS NOT NULL))),
    CONSTRAINT "ck_editorial_article_version_status" CHECK (("status" = ANY (ARRAY['DRAFT'::"text", 'AUTO_REVIEW'::"text", 'HUMAN_REVIEW'::"text", 'APPROVED'::"text", 'REJECTED'::"text", 'SUPERSEDED'::"text"])))
);

--
-- Name: TABLE "article_version"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON TABLE "editorial"."article_version" IS '構造化記事のVersion。AI Draft、人間Edit、Review、Approvalを上書きせずVersionで管理する。';

--
-- Name: COLUMN "article_version"."id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "article_version"."display_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."display_id" IS 'ARV-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "article_version"."article_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."article_id" IS '論理記事ID。';

--
-- Name: COLUMN "article_version"."version_no"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."version_no" IS 'Aggregate内で1から増加する不変Version番号。';

--
-- Name: COLUMN "article_version"."content_schema_version"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."content_schema_version" IS 'content schema version';

--
-- Name: COLUMN "article_version"."title"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."title" IS 'title';

--
-- Name: COLUMN "article_version"."meta_title"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."meta_title" IS 'meta title';

--
-- Name: COLUMN "article_version"."meta_description"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."meta_description" IS 'meta description';

--
-- Name: COLUMN "article_version"."excerpt"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."excerpt" IS 'excerpt';

--
-- Name: COLUMN "article_version"."body_sha256"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."body_sha256" IS 'body sha256';

--
-- Name: COLUMN "article_version"."status"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "article_version"."source_packet_version_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."source_packet_version_id" IS 'source packet version id';

--
-- Name: COLUMN "article_version"."based_on_version_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."based_on_version_id" IS 'based on version id';

--
-- Name: COLUMN "article_version"."ai_job_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."ai_job_id" IS 'ai job id';

--
-- Name: COLUMN "article_version"."created_by_actor_type"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."created_by_actor_type" IS 'created by actor type';

--
-- Name: COLUMN "article_version"."created_by_actor_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."created_by_actor_id" IS 'created by actor id';

--
-- Name: COLUMN "article_version"."submitted_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."submitted_at" IS 'submitted at';

--
-- Name: COLUMN "article_version"."reviewed_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."reviewed_at" IS 'reviewed at';

--
-- Name: COLUMN "article_version"."created_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "article_version"."updated_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "article_version"."lock_version"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_version"."lock_version" IS '楽観的排他制御用の単調増加Version。';

--
-- Name: comparison_axis; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."comparison_axis" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "article_version_id" "uuid" NOT NULL,
    "axis_code" "text" NOT NULL,
    "name" "text" NOT NULL,
    "description" "text" NOT NULL,
    "data_type" "text" NOT NULL,
    "unit_code" "text",
    "position" integer NOT NULL,
    "is_required" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_editorial_axis_position" CHECK (("position" >= 0)),
    CONSTRAINT "ck_editorial_axis_type" CHECK (("data_type" = ANY (ARRAY['TEXT'::"text", 'NUMERIC'::"text", 'BOOLEAN'::"text", 'DATE'::"text", 'CODE'::"text"])))
);

--
-- Name: TABLE "comparison_axis"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON TABLE "editorial"."comparison_axis" IS 'Article Versionごとの比較軸定義。Product比較表の意味と型・単位・根拠要件を固定する。';

--
-- Name: COLUMN "comparison_axis"."id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_axis"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "comparison_axis"."article_version_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_axis"."article_version_id" IS '記事の特定Version。';

--
-- Name: COLUMN "comparison_axis"."axis_code"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_axis"."axis_code" IS 'axis code';

--
-- Name: COLUMN "comparison_axis"."name"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_axis"."name" IS 'name';

--
-- Name: COLUMN "comparison_axis"."description"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_axis"."description" IS 'description';

--
-- Name: COLUMN "comparison_axis"."data_type"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_axis"."data_type" IS 'data type';

--
-- Name: COLUMN "comparison_axis"."unit_code"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_axis"."unit_code" IS 'unit code';

--
-- Name: COLUMN "comparison_axis"."position"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_axis"."position" IS 'position';

--
-- Name: COLUMN "comparison_axis"."is_required"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_axis"."is_required" IS 'is required';

--
-- Name: COLUMN "comparison_axis"."created_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_axis"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: comparison_value; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."comparison_value" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "comparison_axis_id" "uuid" NOT NULL,
    "product_id" "uuid" NOT NULL,
    "value_text" "text",
    "value_numeric" numeric(30,10),
    "value_boolean" boolean,
    "value_date" "date",
    "value_code" "text",
    "display_value" "text" NOT NULL,
    "source_fact_id" "uuid",
    "validation_status" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_editorial_comparison_evidence" CHECK ((("validation_status" <> 'VALID'::"text") OR ("source_fact_id" IS NOT NULL))),
    CONSTRAINT "ck_editorial_comparison_one_value" CHECK (("num_nonnulls"("value_text", "value_numeric", "value_boolean", "value_date", "value_code") = 1)),
    CONSTRAINT "ck_editorial_comparison_status" CHECK (("validation_status" = ANY (ARRAY['VALID'::"text", 'MISSING'::"text", 'CONFLICT'::"text", 'UNSUPPORTED'::"text"])))
);

--
-- Name: TABLE "comparison_value"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON TABLE "editorial"."comparison_value" IS '比較軸×Productの型付き値、表示値、根拠Fact、Validation状態。';

--
-- Name: COLUMN "comparison_value"."id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_value"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "comparison_value"."comparison_axis_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_value"."comparison_axis_id" IS 'comparison axis id';

--
-- Name: COLUMN "comparison_value"."product_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_value"."product_id" IS '正規化されたCanonical Product。';

--
-- Name: COLUMN "comparison_value"."value_text"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_value"."value_text" IS 'value text';

--
-- Name: COLUMN "comparison_value"."value_numeric"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_value"."value_numeric" IS 'value numeric';

--
-- Name: COLUMN "comparison_value"."value_boolean"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_value"."value_boolean" IS 'value boolean';

--
-- Name: COLUMN "comparison_value"."value_date"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_value"."value_date" IS 'value date';

--
-- Name: COLUMN "comparison_value"."value_code"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_value"."value_code" IS 'value code';

--
-- Name: COLUMN "comparison_value"."display_value"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_value"."display_value" IS 'display value';

--
-- Name: COLUMN "comparison_value"."source_fact_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_value"."source_fact_id" IS 'source fact id';

--
-- Name: COLUMN "comparison_value"."validation_status"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_value"."validation_status" IS 'validation status';

--
-- Name: COLUMN "comparison_value"."created_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."comparison_value"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: content_schema_version; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."content_schema_version" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "schema_code" "text" NOT NULL,
    "semantic_version" "text" NOT NULL,
    "artifact_id" "uuid" NOT NULL,
    "schema_sha256" "text" NOT NULL,
    "status" "text" DEFAULT 'DRAFT'::"text" NOT NULL,
    "effective_from" timestamp with time zone NOT NULL,
    "effective_to" timestamp with time zone,
    "approved_by_principal_id" "uuid",
    "approved_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_editorial_content_schema_active_approval" CHECK ((("status" <> 'ACTIVE'::"text") OR (("approved_by_principal_id" IS NOT NULL) AND ("approved_at" IS NOT NULL)))),
    CONSTRAINT "ck_editorial_content_schema_active_window" CHECK ((("status" <> 'ACTIVE'::"text") OR ("effective_to" IS NULL))),
    CONSTRAINT "ck_editorial_content_schema_approval_pair" CHECK ((("approved_by_principal_id" IS NULL) = ("approved_at" IS NULL))),
    CONSTRAINT "ck_editorial_content_schema_code" CHECK (("schema_code" ~ '^[a-z][a-z0-9._-]{2,127}$'::"text")),
    CONSTRAINT "ck_editorial_content_schema_semver" CHECK (("semantic_version" ~ '^[0-9]+\.[0-9]+\.[0-9]+([+-][0-9A-Za-z.-]+)?$'::"text")),
    CONSTRAINT "ck_editorial_content_schema_sha" CHECK (("schema_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_editorial_content_schema_status" CHECK (("status" = ANY (ARRAY['DRAFT'::"text", 'ACTIVE'::"text", 'DEPRECATED'::"text", 'RETIRED'::"text"]))),
    CONSTRAINT "ck_editorial_content_schema_window" CHECK ((("effective_to" IS NULL) OR ("effective_to" > "effective_from")))
);

ALTER TABLE ONLY "editorial"."content_schema_version" FORCE ROW LEVEL SECURITY;

--
-- Name: editorial_methodology_version; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."editorial_methodology_version" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "methodology_code" "text" NOT NULL,
    "semantic_version" "text" NOT NULL,
    "article_type_code" "text" NOT NULL,
    "article_type_version_id" "uuid" NOT NULL,
    "definition" "jsonb" NOT NULL,
    "definition_sha256" "text" NOT NULL,
    "excludes_finance_inputs" boolean DEFAULT true NOT NULL,
    "status" "text" DEFAULT 'DRAFT'::"text" NOT NULL,
    "approved_by_principal_id" "uuid",
    "approved_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_editorial_methodology_active_approval" CHECK ((("status" <> 'ACTIVE'::"text") OR (("approved_by_principal_id" IS NOT NULL) AND ("approved_at" IS NOT NULL)))),
    CONSTRAINT "ck_editorial_methodology_approval_pair" CHECK ((("approved_by_principal_id" IS NULL) = ("approved_at" IS NULL))),
    CONSTRAINT "ck_editorial_methodology_code" CHECK (("methodology_code" ~ '^[a-z][a-z0-9._-]{2,127}$'::"text")),
    CONSTRAINT "ck_editorial_methodology_definition" CHECK (("jsonb_typeof"("definition") = 'object'::"text")),
    CONSTRAINT "ck_editorial_methodology_no_finance" CHECK ("excludes_finance_inputs"),
    CONSTRAINT "ck_editorial_methodology_semver" CHECK (("semantic_version" ~ '^[0-9]+\.[0-9]+\.[0-9]+([+-][0-9A-Za-z.-]+)?$'::"text")),
    CONSTRAINT "ck_editorial_methodology_sha" CHECK (("definition_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_editorial_methodology_status" CHECK (("status" = ANY (ARRAY['DRAFT'::"text", 'ACTIVE'::"text", 'DEPRECATED'::"text", 'RETIRED'::"text"])))
);

ALTER TABLE ONLY "editorial"."editorial_methodology_version" FORCE ROW LEVEL SECURITY;

--
-- Name: media_asset; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."media_asset" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "asset_class" "text" NOT NULL,
    "source_id" "uuid" NOT NULL,
    "raw_artifact_id" "uuid" NOT NULL,
    "asset_sha256" "text" NOT NULL,
    "license_status" "text" NOT NULL,
    "modification_policy" "text" NOT NULL,
    "alt_text" "text" DEFAULT ''::"text" NOT NULL,
    "decorative" boolean DEFAULT false NOT NULL,
    "long_description_artifact_id" "uuid",
    "width" integer NOT NULL,
    "height" integer NOT NULL,
    "captured_or_observed_at" timestamp with time zone NOT NULL,
    "status" "text" DEFAULT 'DRAFT'::"text" NOT NULL,
    "approved_by_principal_id" "uuid",
    "approved_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_editorial_media_asset_alt" CHECK (("decorative" OR ("length"("btrim"("alt_text")) > 0))),
    CONSTRAINT "ck_editorial_media_asset_approval_pair" CHECK ((("approved_by_principal_id" IS NULL) = ("approved_at" IS NULL))),
    CONSTRAINT "ck_editorial_media_asset_approved_human" CHECK ((("status" <> 'APPROVED'::"text") OR (("approved_by_principal_id" IS NOT NULL) AND ("approved_at" IS NOT NULL)))),
    CONSTRAINT "ck_editorial_media_asset_class" CHECK (("asset_class" = ANY (ARRAY['IMAGE'::"text", 'CHART'::"text", 'VIDEO'::"text", 'DIAGRAM'::"text", 'OTHER'::"text"]))),
    CONSTRAINT "ck_editorial_media_asset_dimensions" CHECK ((("width" > 0) AND ("height" > 0))),
    CONSTRAINT "ck_editorial_media_asset_license" CHECK (("license_status" = ANY (ARRAY['PENDING'::"text", 'APPROVED'::"text", 'RESTRICTED'::"text", 'REJECTED'::"text"]))),
    CONSTRAINT "ck_editorial_media_asset_modification" CHECK (("length"("btrim"("modification_policy")) > 0)),
    CONSTRAINT "ck_editorial_media_asset_sha" CHECK (("asset_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_editorial_media_asset_status" CHECK (("status" = ANY (ARRAY['DRAFT'::"text", 'APPROVED'::"text", 'BLOCKED'::"text", 'RETIRED'::"text"])))
);

ALTER TABLE ONLY "editorial"."media_asset" FORCE ROW LEVEL SECURITY;

--
-- Name: recommendation; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."recommendation" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "recommendation_set_id" "uuid" NOT NULL,
    "product_id" "uuid" NOT NULL,
    "rank_position" integer NOT NULL,
    "suitability_score" numeric(5,2) NOT NULL,
    "status" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_editorial_rec_rank" CHECK (("rank_position" >= 1)),
    CONSTRAINT "ck_editorial_rec_score" CHECK ((("suitability_score" >= (0)::numeric) AND ("suitability_score" <= (100)::numeric))),
    CONSTRAINT "ck_editorial_rec_status" CHECK (("status" = ANY (ARRAY['RECOMMENDED'::"text", 'ALTERNATIVE'::"text", 'NOT_RECOMMENDED'::"text", 'EXCLUDED'::"text"])))
);

--
-- Name: TABLE "recommendation"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON TABLE "editorial"."recommendation" IS 'Recommendation Set内の商品順位とEditorial Suitability Score。収益・Affiliate rate Columnを持たない。';

--
-- Name: COLUMN "recommendation"."id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "recommendation"."recommendation_set_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation"."recommendation_set_id" IS 'recommendation set id';

--
-- Name: COLUMN "recommendation"."product_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation"."product_id" IS '正規化されたCanonical Product。';

--
-- Name: COLUMN "recommendation"."rank_position"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation"."rank_position" IS 'rank position';

--
-- Name: COLUMN "recommendation"."suitability_score"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation"."suitability_score" IS 'suitability score';

--
-- Name: COLUMN "recommendation"."status"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "recommendation"."created_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: recommendation_rationale; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."recommendation_rationale" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "recommendation_id" "uuid" NOT NULL,
    "rationale_type" "text" NOT NULL,
    "rationale_text" "text" NOT NULL,
    "claim_id" "uuid",
    "source_fact_id" "uuid",
    "position" integer NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_editorial_rationale_position" CHECK (("position" >= 0)),
    CONSTRAINT "ck_editorial_rationale_source" CHECK ((("claim_id" IS NOT NULL) OR ("source_fact_id" IS NOT NULL))),
    CONSTRAINT "ck_editorial_rationale_type" CHECK (("rationale_type" = ANY (ARRAY['FIT'::"text", 'NON_FIT'::"text", 'TRADE_OFF'::"text", 'QUALIFIER'::"text", 'EVIDENCE'::"text"])))
);

--
-- Name: TABLE "recommendation_rationale"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON TABLE "editorial"."recommendation_rationale" IS '推薦のfit/non-fit/trade-off/qualifierをClaimまたはFactへ結び、説明可能性を担保する。';

--
-- Name: COLUMN "recommendation_rationale"."id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation_rationale"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "recommendation_rationale"."recommendation_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation_rationale"."recommendation_id" IS 'recommendation id';

--
-- Name: COLUMN "recommendation_rationale"."rationale_type"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation_rationale"."rationale_type" IS 'rationale type';

--
-- Name: COLUMN "recommendation_rationale"."rationale_text"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation_rationale"."rationale_text" IS 'rationale text';

--
-- Name: COLUMN "recommendation_rationale"."claim_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation_rationale"."claim_id" IS 'claim id';

--
-- Name: COLUMN "recommendation_rationale"."source_fact_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation_rationale"."source_fact_id" IS 'source fact id';

--
-- Name: COLUMN "recommendation_rationale"."position"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation_rationale"."position" IS 'position';

--
-- Name: COLUMN "recommendation_rationale"."created_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation_rationale"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: recommendation_set; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."recommendation_set" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "article_version_id" "uuid" NOT NULL,
    "set_code" "text" NOT NULL,
    "name" "text" NOT NULL,
    "target_segment" "text" NOT NULL,
    "methodology" "text" NOT NULL,
    "editorial_policy_version" "text" NOT NULL,
    "position" integer NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_editorial_rec_set_position" CHECK (("position" >= 0))
);

--
-- Name: TABLE "recommendation_set"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON TABLE "editorial"."recommendation_set" IS '用途・条件別Recommendation groupとMethodologyをArticle Versionへ固定する。';

--
-- Name: COLUMN "recommendation_set"."id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation_set"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "recommendation_set"."article_version_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation_set"."article_version_id" IS '記事の特定Version。';

--
-- Name: COLUMN "recommendation_set"."set_code"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation_set"."set_code" IS 'set code';

--
-- Name: COLUMN "recommendation_set"."name"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation_set"."name" IS 'name';

--
-- Name: COLUMN "recommendation_set"."target_segment"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation_set"."target_segment" IS 'target segment';

--
-- Name: COLUMN "recommendation_set"."methodology"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation_set"."methodology" IS 'methodology';

--
-- Name: COLUMN "recommendation_set"."editorial_policy_version"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation_set"."editorial_policy_version" IS 'editorial policy version';

--
-- Name: COLUMN "recommendation_set"."position"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation_set"."position" IS 'position';

--
-- Name: COLUMN "recommendation_set"."created_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."recommendation_set"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: review_comment; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."review_comment" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "article_version_id" "uuid" NOT NULL,
    "article_block_id" "uuid",
    "claim_id" "uuid",
    "thread_id" "uuid" NOT NULL,
    "parent_comment_id" "uuid",
    "author_principal_id" "uuid" NOT NULL,
    "comment_text" "text" NOT NULL,
    "status" "text" DEFAULT 'OPEN'::"text" NOT NULL,
    "resolved_by_principal_id" "uuid",
    "resolved_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_editorial_review_comment_resolve_pair" CHECK ((("resolved_by_principal_id" IS NULL) = ("resolved_at" IS NULL))),
    CONSTRAINT "ck_editorial_review_comment_status" CHECK (("status" = ANY (ARRAY['OPEN'::"text", 'RESOLVED'::"text", 'WONT_FIX'::"text"]))),
    CONSTRAINT "ck_editorial_review_comment_target" CHECK ((("article_block_id" IS NOT NULL) OR ("claim_id" IS NOT NULL)))
);

--
-- Name: TABLE "review_comment"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON TABLE "editorial"."review_comment" IS 'Article Version、Block、Claimに対するReview thread。修正・解決履歴を上書きせずCommentとして残す。';

--
-- Name: COLUMN "review_comment"."id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."review_comment"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "review_comment"."article_version_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."review_comment"."article_version_id" IS '記事の特定Version。';

--
-- Name: COLUMN "review_comment"."article_block_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."review_comment"."article_block_id" IS 'article block id';

--
-- Name: COLUMN "review_comment"."claim_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."review_comment"."claim_id" IS 'claim id';

--
-- Name: COLUMN "review_comment"."thread_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."review_comment"."thread_id" IS 'thread id';

--
-- Name: COLUMN "review_comment"."parent_comment_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."review_comment"."parent_comment_id" IS 'parent comment id';

--
-- Name: COLUMN "review_comment"."author_principal_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."review_comment"."author_principal_id" IS 'author principal id';

--
-- Name: COLUMN "review_comment"."comment_text"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."review_comment"."comment_text" IS 'comment text';

--
-- Name: COLUMN "review_comment"."status"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."review_comment"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "review_comment"."resolved_by_principal_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."review_comment"."resolved_by_principal_id" IS 'resolved by principal id';

--
-- Name: COLUMN "review_comment"."resolved_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."review_comment"."resolved_at" IS 'resolved at';

--
-- Name: COLUMN "review_comment"."created_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."review_comment"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: seo_metadata_version; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."seo_metadata_version" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "article_version_id" "uuid" NOT NULL,
    "semantic_version" "text" NOT NULL,
    "metadata" "jsonb" NOT NULL,
    "metadata_sha256" "text" NOT NULL,
    "status" "text" DEFAULT 'DRAFT'::"text" NOT NULL,
    "validated_at" timestamp with time zone,
    "approved_by_principal_id" "uuid",
    "approved_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_editorial_seo_approval_pair" CHECK ((("approved_by_principal_id" IS NULL) = ("approved_at" IS NULL))),
    CONSTRAINT "ck_editorial_seo_approved_human" CHECK ((("status" <> 'APPROVED'::"text") OR (("approved_by_principal_id" IS NOT NULL) AND ("approved_at" IS NOT NULL)))),
    CONSTRAINT "ck_editorial_seo_metadata_sha" CHECK (("metadata_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_editorial_seo_metadata_shape" CHECK (("jsonb_typeof"("metadata") = 'object'::"text")),
    CONSTRAINT "ck_editorial_seo_semver" CHECK (("semantic_version" ~ '^[0-9]+\.[0-9]+\.[0-9]+([+-][0-9A-Za-z.-]+)?$'::"text")),
    CONSTRAINT "ck_editorial_seo_status" CHECK (("status" = ANY (ARRAY['DRAFT'::"text", 'VALIDATED'::"text", 'APPROVED'::"text", 'REJECTED'::"text"]))),
    CONSTRAINT "ck_editorial_seo_validation_time" CHECK ((("status" = 'DRAFT'::"text") OR ("validated_at" IS NOT NULL)))
);

ALTER TABLE ONLY "editorial"."seo_metadata_version" FORCE ROW LEVEL SECURITY;

--
-- Name: structured_data_manifest; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."structured_data_manifest" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "article_version_id" "uuid" NOT NULL,
    "seo_metadata_version_id" "uuid" NOT NULL,
    "generator_version" "text" NOT NULL,
    "visible_content_sha256" "text" NOT NULL,
    "jsonld_artifact_id" "uuid" NOT NULL,
    "jsonld_sha256" "text" NOT NULL,
    "enabled_types" "text"[] NOT NULL,
    "disabled_types" "text"[] NOT NULL,
    "validation_status" "text" NOT NULL,
    "validated_at" timestamp with time zone NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_editorial_structured_data_generator" CHECK (("length"("btrim"("generator_version")) > 0)),
    CONSTRAINT "ck_editorial_structured_data_jsonld_sha" CHECK (("jsonld_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_editorial_structured_data_status" CHECK (("validation_status" = ANY (ARRAY['PASS'::"text", 'FAIL'::"text"]))),
    CONSTRAINT "ck_editorial_structured_data_types" CHECK (((NOT ("enabled_types" && "disabled_types")) AND ("array_position"("enabled_types", NULL::"text") IS NULL) AND ("array_position"("disabled_types", NULL::"text") IS NULL))),
    CONSTRAINT "ck_editorial_structured_data_visible_sha" CHECK (("visible_content_sha256" ~ '^[0-9a-f]{64}$'::"text"))
);

ALTER TABLE ONLY "editorial"."structured_data_manifest" FORCE ROW LEVEL SECURITY;

--
-- Name: claim; Type: TABLE; Schema: evidence; Owner: -
--

CREATE TABLE "evidence"."claim" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "article_version_id" "uuid" NOT NULL,
    "block_id" "uuid",
    "claim_key" "text" NOT NULL,
    "claim_type" "text" NOT NULL,
    "claim_text" "text" NOT NULL,
    "criticality" "text" NOT NULL,
    "support_status" "text" DEFAULT 'PENDING'::"text" NOT NULL,
    "generated_by_ai_attempt_id" "uuid",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_evidence_claim_criticality" CHECK (("criticality" = ANY (ARRAY['LOW'::"text", 'MEDIUM'::"text", 'HIGH'::"text", 'CRITICAL'::"text"]))),
    CONSTRAINT "ck_evidence_claim_support" CHECK (("support_status" = ANY (ARRAY['PENDING'::"text", 'SUPPORTED'::"text", 'PARTIAL'::"text", 'UNSUPPORTED'::"text", 'CONFLICT'::"text", 'NOT_REQUIRED'::"text"]))),
    CONSTRAINT "ck_evidence_claim_type" CHECK (("claim_type" = ANY (ARRAY['FACTUAL'::"text", 'COMPARATIVE'::"text", 'RECOMMENDATION'::"text", 'DISCLOSURE'::"text", 'EXPERIENCE'::"text", 'OPINION'::"text"])))
);

--
-- Name: TABLE "claim"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON TABLE "evidence"."claim" IS '公開文中の主張単位。Article Version/Block、生成Attempt、Criticality、Support statusを追跡する。';

--
-- Name: COLUMN "claim"."id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."claim"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "claim"."display_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."claim"."display_id" IS 'CLM-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "claim"."article_version_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."claim"."article_version_id" IS '記事の特定Version。';

--
-- Name: COLUMN "claim"."block_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."claim"."block_id" IS 'block id';

--
-- Name: COLUMN "claim"."claim_key"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."claim"."claim_key" IS 'claim key';

--
-- Name: COLUMN "claim"."claim_type"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."claim"."claim_type" IS 'claim type';

--
-- Name: COLUMN "claim"."claim_text"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."claim"."claim_text" IS 'claim text';

--
-- Name: COLUMN "claim"."criticality"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."claim"."criticality" IS 'criticality';

--
-- Name: COLUMN "claim"."support_status"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."claim"."support_status" IS 'support status';

--
-- Name: COLUMN "claim"."generated_by_ai_attempt_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."claim"."generated_by_ai_attempt_id" IS 'generated by ai attempt id';

--
-- Name: COLUMN "claim"."created_at"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."claim"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: claim_evidence_link; Type: TABLE; Schema: evidence; Owner: -
--

CREATE TABLE "evidence"."claim_evidence_link" (
    "claim_id" "uuid" NOT NULL,
    "fact_id" "uuid" NOT NULL,
    "support_type" "text" NOT NULL,
    "support_strength" numeric(5,4) NOT NULL,
    "note" "text",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_evidence_claim_link_strength" CHECK ((("support_strength" >= (0)::numeric) AND ("support_strength" <= (1)::numeric))),
    CONSTRAINT "ck_evidence_claim_link_type" CHECK (("support_type" = ANY (ARRAY['SUPPORTS'::"text", 'QUALIFIES'::"text", 'CONTRADICTS'::"text"])))
);

--
-- Name: TABLE "claim_evidence_link"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON TABLE "evidence"."claim_evidence_link" IS 'ClaimとFactをsupports/qualifies/contradictsとして結び、Support strengthと注記を保持する。';

--
-- Name: COLUMN "claim_evidence_link"."claim_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."claim_evidence_link"."claim_id" IS 'claim id';

--
-- Name: COLUMN "claim_evidence_link"."fact_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."claim_evidence_link"."fact_id" IS 'fact id';

--
-- Name: COLUMN "claim_evidence_link"."support_type"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."claim_evidence_link"."support_type" IS 'support type';

--
-- Name: COLUMN "claim_evidence_link"."support_strength"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."claim_evidence_link"."support_strength" IS 'support strength';

--
-- Name: COLUMN "claim_evidence_link"."note"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."claim_evidence_link"."note" IS 'note';

--
-- Name: COLUMN "claim_evidence_link"."created_at"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."claim_evidence_link"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: fact; Type: TABLE; Schema: evidence; Owner: -
--

CREATE TABLE "evidence"."fact" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "source_snapshot_id" "uuid" NOT NULL,
    "subject_type" "text" NOT NULL,
    "subject_id" "uuid" NOT NULL,
    "predicate" "text" NOT NULL,
    "value_text" "text",
    "value_numeric" numeric(30,10),
    "value_boolean" boolean,
    "value_date" "date",
    "value_timestamp" timestamp with time zone,
    "value_json" "jsonb",
    "unit_code" "text",
    "locale" "text",
    "fact_kind" "text" DEFAULT 'ASSERTED'::"text" NOT NULL,
    "confidence" numeric(5,4) NOT NULL,
    "valid_from" timestamp with time zone,
    "valid_to" timestamp with time zone,
    "locator" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_evidence_fact_conf" CHECK ((("confidence" >= (0)::numeric) AND ("confidence" <= (1)::numeric))),
    CONSTRAINT "ck_evidence_fact_kind" CHECK (("fact_kind" = ANY (ARRAY['ASSERTED'::"text", 'DERIVED'::"text", 'MANUAL_VERIFIED'::"text"]))),
    CONSTRAINT "ck_evidence_fact_locator" CHECK (("jsonb_typeof"("locator") = 'object'::"text")),
    CONSTRAINT "ck_evidence_fact_one_value" CHECK (("num_nonnulls"("value_text", "value_numeric", "value_boolean", "value_date", "value_timestamp", "value_json") = 1)),
    CONSTRAINT "ck_evidence_fact_subject" CHECK (("subject_type" = ANY (ARRAY['SITE'::"text", 'CATEGORY'::"text", 'PRODUCT'::"text", 'OFFER'::"text", 'SHOP'::"text", 'ARTICLE'::"text", 'KEYWORD'::"text", 'OTHER'::"text"]))),
    CONSTRAINT "ck_evidence_fact_value_json" CHECK ((("value_json" IS NULL) OR ("jsonb_typeof"("value_json") = ANY (ARRAY['object'::"text", 'array'::"text", 'string'::"text", 'number'::"text", 'boolean'::"text", 'null'::"text"])))),
    CONSTRAINT "ck_evidence_fact_window" CHECK ((("valid_to" IS NULL) OR ("valid_from" IS NULL) OR ("valid_to" > "valid_from")))
);

--
-- Name: TABLE "fact"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON TABLE "evidence"."fact" IS 'Source Snapshotから抽出・正規化した型付き事実。subject_type/id、predicate、locator、信頼度、有効期間を持つ。';

--
-- Name: COLUMN "fact"."id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "fact"."display_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."display_id" IS 'FCT-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "fact"."source_snapshot_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."source_snapshot_id" IS 'source snapshot id';

--
-- Name: COLUMN "fact"."subject_type"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."subject_type" IS 'subject type';

--
-- Name: COLUMN "fact"."subject_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."subject_id" IS 'subject id';

--
-- Name: COLUMN "fact"."predicate"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."predicate" IS 'predicate';

--
-- Name: COLUMN "fact"."value_text"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."value_text" IS 'value text';

--
-- Name: COLUMN "fact"."value_numeric"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."value_numeric" IS 'value numeric';

--
-- Name: COLUMN "fact"."value_boolean"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."value_boolean" IS 'value boolean';

--
-- Name: COLUMN "fact"."value_date"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."value_date" IS 'value date';

--
-- Name: COLUMN "fact"."value_timestamp"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."value_timestamp" IS 'value timestamp';

--
-- Name: COLUMN "fact"."value_json"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."value_json" IS 'value json';

--
-- Name: COLUMN "fact"."unit_code"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."unit_code" IS 'unit code';

--
-- Name: COLUMN "fact"."locale"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."locale" IS 'locale';

--
-- Name: COLUMN "fact"."fact_kind"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."fact_kind" IS 'fact kind';

--
-- Name: COLUMN "fact"."confidence"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."confidence" IS 'confidence';

--
-- Name: COLUMN "fact"."valid_from"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."valid_from" IS 'valid from';

--
-- Name: COLUMN "fact"."valid_to"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."valid_to" IS 'valid to';

--
-- Name: COLUMN "fact"."locator"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."locator" IS 'JSON Pointer、page、section、table cell等の出典内位置。';

--
-- Name: COLUMN "fact"."created_at"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: fact_derivation; Type: TABLE; Schema: evidence; Owner: -
--

CREATE TABLE "evidence"."fact_derivation" (
    "derived_fact_id" "uuid" NOT NULL,
    "input_fact_id" "uuid" NOT NULL,
    "derivation_role" "text" NOT NULL,
    "algorithm_version" "text" NOT NULL,
    "formula_description" "text",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_evidence_derivation_role" CHECK (("derivation_role" = ANY (ARRAY['INPUT'::"text", 'BASELINE'::"text", 'QUALIFIER'::"text", 'EXCLUSION'::"text"]))),
    CONSTRAINT "ck_evidence_derivation_self" CHECK (("derived_fact_id" <> "input_fact_id"))
);

--
-- Name: TABLE "fact_derivation"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON TABLE "evidence"."fact_derivation" IS 'Derived Factと入力Factを多対多で結び、Algorithm/Formula versionを追跡する。';

--
-- Name: COLUMN "fact_derivation"."derived_fact_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact_derivation"."derived_fact_id" IS 'derived fact id';

--
-- Name: COLUMN "fact_derivation"."input_fact_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact_derivation"."input_fact_id" IS 'input fact id';

--
-- Name: COLUMN "fact_derivation"."derivation_role"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact_derivation"."derivation_role" IS 'derivation role';

--
-- Name: COLUMN "fact_derivation"."algorithm_version"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact_derivation"."algorithm_version" IS 'algorithm version';

--
-- Name: COLUMN "fact_derivation"."formula_description"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact_derivation"."formula_description" IS 'formula description';

--
-- Name: COLUMN "fact_derivation"."created_at"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."fact_derivation"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: first_hand_experience_asset; Type: TABLE; Schema: evidence; Owner: -
--

CREATE TABLE "evidence"."first_hand_experience_asset" (
    "experience_record_id" "uuid" NOT NULL,
    "artifact_id" "uuid" NOT NULL,
    "role" "text" NOT NULL,
    "artifact_sha256" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_evidence_first_hand_asset_role" CHECK (("role" = ANY (ARRAY['PHOTO'::"text", 'VIDEO'::"text", 'MEASUREMENT'::"text", 'LOG'::"text", 'PROCEDURE'::"text", 'OTHER'::"text"]))),
    CONSTRAINT "ck_evidence_first_hand_asset_sha" CHECK (("artifact_sha256" ~ '^[0-9a-f]{64}$'::"text"))
);

ALTER TABLE ONLY "evidence"."first_hand_experience_asset" FORCE ROW LEVEL SECURITY;

--
-- Name: first_hand_experience_record; Type: TABLE; Schema: evidence; Owner: -
--

CREATE TABLE "evidence"."first_hand_experience_record" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "product_id" "uuid" NOT NULL,
    "product_variant_identity" "jsonb" NOT NULL,
    "tester_principal_id" "uuid" NOT NULL,
    "procedure_version" "text" NOT NULL,
    "started_at" timestamp with time zone NOT NULL,
    "ended_at" timestamp with time zone NOT NULL,
    "environment" "jsonb" NOT NULL,
    "limitations" "text" NOT NULL,
    "review_status" "text" DEFAULT 'DRAFT'::"text" NOT NULL,
    "reviewed_by_principal_id" "uuid",
    "reviewed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_evidence_first_hand_environment" CHECK (("jsonb_typeof"("environment") = 'object'::"text")),
    CONSTRAINT "ck_evidence_first_hand_limitations" CHECK (("length"("btrim"("limitations")) > 0)),
    CONSTRAINT "ck_evidence_first_hand_procedure" CHECK (("length"("btrim"("procedure_version")) > 0)),
    CONSTRAINT "ck_evidence_first_hand_review_pair" CHECK ((("reviewed_by_principal_id" IS NULL) = ("reviewed_at" IS NULL))),
    CONSTRAINT "ck_evidence_first_hand_review_required" CHECK ((("review_status" = 'DRAFT'::"text") OR (("reviewed_by_principal_id" IS NOT NULL) AND ("reviewed_at" IS NOT NULL)))),
    CONSTRAINT "ck_evidence_first_hand_status" CHECK (("review_status" = ANY (ARRAY['DRAFT'::"text", 'REVIEWED'::"text", 'APPROVED'::"text", 'REJECTED'::"text"]))),
    CONSTRAINT "ck_evidence_first_hand_variant" CHECK (("jsonb_typeof"("product_variant_identity") = 'object'::"text")),
    CONSTRAINT "ck_evidence_first_hand_window" CHECK (("ended_at" >= "started_at"))
);

ALTER TABLE ONLY "evidence"."first_hand_experience_record" FORCE ROW LEVEL SECURITY;

--
-- Name: source; Type: TABLE; Schema: evidence; Owner: -
--

CREATE TABLE "evidence"."source" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "source_type" "text" NOT NULL,
    "provider_endpoint_id" "uuid",
    "name" "text" NOT NULL,
    "base_url" "text",
    "authority_level" "text" NOT NULL,
    "permitted_use" "text" NOT NULL,
    "terms_checked_at" timestamp with time zone,
    "terms_checked_by_principal_id" "uuid",
    "status" "text" DEFAULT 'ACTIVE'::"text" NOT NULL,
    "metadata" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    CONSTRAINT "ck_evidence_source_authority" CHECK (("authority_level" = ANY (ARRAY['PRIMARY'::"text", 'OFFICIAL'::"text", 'SECONDARY'::"text", 'INTERNAL_DERIVED'::"text", 'UNVERIFIED'::"text"]))),
    CONSTRAINT "ck_evidence_source_meta" CHECK (("jsonb_typeof"("metadata") = 'object'::"text")),
    CONSTRAINT "ck_evidence_source_status" CHECK (("status" = ANY (ARRAY['ACTIVE'::"text", 'PAUSED'::"text", 'BLOCKED'::"text", 'RETIRED'::"text"]))),
    CONSTRAINT "ck_evidence_source_type" CHECK (("source_type" = ANY (ARRAY['PROVIDER_API'::"text", 'MANUFACTURER'::"text", 'OFFICIAL_DOCUMENT'::"text", 'MANUAL_VERIFIED'::"text", 'INTERNAL_CALCULATION'::"text", 'ANALYTICS'::"text", 'OTHER'::"text"]))),
    CONSTRAINT "ck_evidence_source_url" CHECK ((("base_url" IS NULL) OR ("base_url" ~ '^https://'::"text"))),
    CONSTRAINT "ck_evidence_source_version" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "source"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON TABLE "evidence"."source" IS 'Provider API、Manufacturer、Manual entry等の根拠Sourceと利用条件・Authorityを管理する。';

--
-- Name: COLUMN "source"."id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "source"."display_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source"."display_id" IS 'SRC-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "source"."source_type"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source"."source_type" IS 'source type';

--
-- Name: COLUMN "source"."provider_endpoint_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source"."provider_endpoint_id" IS 'provider endpoint id';

--
-- Name: COLUMN "source"."name"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source"."name" IS 'name';

--
-- Name: COLUMN "source"."base_url"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source"."base_url" IS 'base url';

--
-- Name: COLUMN "source"."authority_level"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source"."authority_level" IS 'authority level';

--
-- Name: COLUMN "source"."permitted_use"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source"."permitted_use" IS 'permitted use';

--
-- Name: COLUMN "source"."terms_checked_at"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source"."terms_checked_at" IS 'terms checked at';

--
-- Name: COLUMN "source"."terms_checked_by_principal_id"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source"."terms_checked_by_principal_id" IS 'terms checked by principal id';

--
-- Name: COLUMN "source"."status"; Type: COMMENT; Schema: evidence; Owner: -
--

COMMENT ON COLUMN "evidence"."source"."status" IS '業務状態を示す安定Enum文字列。';
