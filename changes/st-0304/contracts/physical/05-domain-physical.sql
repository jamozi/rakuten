-- ST-0304 physical translation fragment 05 of 11.
-- Source: approved RAOS data catalog plus finalized ST-0003/ST-0004 semantics.
-- Capture: PostgreSQL 18.4 pg_dump --schema-only --no-owner --no-privileges
--          --no-security-labels --quote-all-identifiers for the six owned schemas.
-- Schema creation/comments are rendered once by the ST-0304 generator. The 22
-- role-bound CREATE POLICY objects remain ST-0306-owned. ENABLE/FORCE RLS remains.

--
-- Name: COLUMN "availability_observation"."valid_until"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."availability_observation"."valid_until" IS 'valid until';

--
-- Name: COLUMN "availability_observation"."source_snapshot_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."availability_observation"."source_snapshot_id" IS 'source snapshot id';

--
-- Name: COLUMN "availability_observation"."validation_status"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."availability_observation"."validation_status" IS 'validation status';

--
-- Name: COLUMN "availability_observation"."confidence"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."availability_observation"."confidence" IS 'confidence';

--
-- Name: COLUMN "availability_observation"."created_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."availability_observation"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: canonical_product; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."canonical_product" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "category_id" "uuid" NOT NULL,
    "canonical_name" "text" NOT NULL,
    "brand_name" "text",
    "manufacturer_name" "text",
    "model_number" "text",
    "jan_code" "text",
    "product_type" "text" NOT NULL,
    "lifecycle_status" "text" DEFAULT 'ACTIVE'::"text" NOT NULL,
    "identity_confidence" numeric(5,4) NOT NULL,
    "identity_attributes" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "merged_into_product_id" "uuid",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    CONSTRAINT "ck_catalog_product_conf" CHECK ((("identity_confidence" >= (0)::numeric) AND ("identity_confidence" <= (1)::numeric))),
    CONSTRAINT "ck_catalog_product_identity" CHECK (("jsonb_typeof"("identity_attributes") = 'object'::"text")),
    CONSTRAINT "ck_catalog_product_jan" CHECK ((("jan_code" IS NULL) OR ("jan_code" ~ '^[0-9]{8,14}$'::"text"))),
    CONSTRAINT "ck_catalog_product_lifecycle" CHECK (("lifecycle_status" = ANY (ARRAY['ACTIVE'::"text", 'DISCONTINUED'::"text", 'MERGED'::"text", 'SPLIT'::"text", 'UNKNOWN'::"text"]))),
    CONSTRAINT "ck_catalog_product_merge" CHECK ((("merged_into_product_id" IS NULL) OR ("merged_into_product_id" <> "id"))),
    CONSTRAINT "ck_catalog_product_version" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "canonical_product"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."canonical_product" IS '複数Shop Listingを束ねる商品概念。JAN、型番、Brand等は確信度付きIdentityとして扱う。';

--
-- Name: COLUMN "canonical_product"."id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."canonical_product"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "canonical_product"."display_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."canonical_product"."display_id" IS 'PRD-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "canonical_product"."category_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."canonical_product"."category_id" IS '対象カテゴリ。';

--
-- Name: COLUMN "canonical_product"."canonical_name"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."canonical_product"."canonical_name" IS 'canonical name';

--
-- Name: COLUMN "canonical_product"."brand_name"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."canonical_product"."brand_name" IS 'brand name';

--
-- Name: COLUMN "canonical_product"."manufacturer_name"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."canonical_product"."manufacturer_name" IS 'manufacturer name';

--
-- Name: COLUMN "canonical_product"."model_number"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."canonical_product"."model_number" IS 'model number';

--
-- Name: COLUMN "canonical_product"."jan_code"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."canonical_product"."jan_code" IS 'jan code';

--
-- Name: COLUMN "canonical_product"."product_type"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."canonical_product"."product_type" IS 'product type';

--
-- Name: COLUMN "canonical_product"."lifecycle_status"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."canonical_product"."lifecycle_status" IS 'lifecycle status';

--
-- Name: COLUMN "canonical_product"."identity_confidence"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."canonical_product"."identity_confidence" IS 'identity confidence';

--
-- Name: COLUMN "canonical_product"."identity_attributes"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."canonical_product"."identity_attributes" IS '同定に使用した正規化Attribute。';

--
-- Name: COLUMN "canonical_product"."merged_into_product_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."canonical_product"."merged_into_product_id" IS 'merged into product id';

--
-- Name: COLUMN "canonical_product"."created_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."canonical_product"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "canonical_product"."updated_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."canonical_product"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "canonical_product"."lock_version"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."canonical_product"."lock_version" IS '楽観的排他制御用の単調増加Version。';

--
-- Name: category_genre_mapping; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."category_genre_mapping" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "category_id" "uuid" NOT NULL,
    "rakuten_genre_id" "uuid" NOT NULL,
    "mapping_role" "text" NOT NULL,
    "valid_from" timestamp with time zone NOT NULL,
    "valid_to" timestamp with time zone,
    "decision_reason" "text" NOT NULL,
    "decided_by_principal_id" "uuid" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_catalog_category_genre_role" CHECK (("mapping_role" = ANY (ARRAY['PRIMARY'::"text", 'INCLUDE'::"text", 'EXCLUDE'::"text"]))),
    CONSTRAINT "ck_catalog_category_genre_window" CHECK ((("valid_to" IS NULL) OR ("valid_to" > "valid_from")))
);

--
-- Name: TABLE "category_genre_mapping"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."category_genre_mapping" IS 'RAOS Categoryと楽天Genreのinclude/exclude/primary関係を有効期間付きで管理する。';

--
-- Name: COLUMN "category_genre_mapping"."id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."category_genre_mapping"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "category_genre_mapping"."category_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."category_genre_mapping"."category_id" IS '対象カテゴリ。';

--
-- Name: COLUMN "category_genre_mapping"."rakuten_genre_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."category_genre_mapping"."rakuten_genre_id" IS 'rakuten genre id';

--
-- Name: COLUMN "category_genre_mapping"."mapping_role"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."category_genre_mapping"."mapping_role" IS 'mapping role';

--
-- Name: COLUMN "category_genre_mapping"."valid_from"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."category_genre_mapping"."valid_from" IS 'valid from';

--
-- Name: COLUMN "category_genre_mapping"."valid_to"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."category_genre_mapping"."valid_to" IS 'valid to';

--
-- Name: COLUMN "category_genre_mapping"."decision_reason"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."category_genre_mapping"."decision_reason" IS 'decision reason';

--
-- Name: COLUMN "category_genre_mapping"."decided_by_principal_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."category_genre_mapping"."decided_by_principal_id" IS 'decided by principal id';

--
-- Name: COLUMN "category_genre_mapping"."created_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."category_genre_mapping"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: grouping_decision; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."grouping_decision" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "product_candidate_id" "uuid" NOT NULL,
    "proposed_product_id" "uuid",
    "decision_type" "text" NOT NULL,
    "decision_score" numeric(5,4),
    "rule_version" "text" NOT NULL,
    "reasons" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "decided_by_actor_type" "text" NOT NULL,
    "decided_by_actor_id" "uuid",
    "decided_at" timestamp with time zone NOT NULL,
    "supersedes_decision_id" "uuid",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_catalog_group_decision_type" CHECK (("decision_type" = ANY (ARRAY['AUTO_ACCEPT'::"text", 'HUMAN_ACCEPT'::"text", 'REJECT'::"text", 'SPLIT'::"text", 'UNDECIDED'::"text"]))),
    CONSTRAINT "ck_catalog_group_reasons" CHECK (("jsonb_typeof"("reasons") = 'object'::"text")),
    CONSTRAINT "ck_catalog_group_score" CHECK ((("decision_score" IS NULL) OR (("decision_score" >= (0)::numeric) AND ("decision_score" <= (1)::numeric)))),
    CONSTRAINT "ck_catalog_group_target" CHECK ((("decision_type" = ANY (ARRAY['REJECT'::"text", 'UNDECIDED'::"text"])) OR ("proposed_product_id" IS NOT NULL)))
);

--
-- Name: TABLE "grouping_decision"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."grouping_decision" IS 'Product CandidateをCanonical Productへ統合・分離・却下した判断とRule版・Score・理由を追記保存する。';

--
-- Name: COLUMN "grouping_decision"."id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."grouping_decision"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "grouping_decision"."product_candidate_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."grouping_decision"."product_candidate_id" IS 'product candidate id';

--
-- Name: COLUMN "grouping_decision"."proposed_product_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."grouping_decision"."proposed_product_id" IS 'proposed product id';

--
-- Name: COLUMN "grouping_decision"."decision_type"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."grouping_decision"."decision_type" IS 'decision type';

--
-- Name: COLUMN "grouping_decision"."decision_score"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."grouping_decision"."decision_score" IS 'decision score';

--
-- Name: COLUMN "grouping_decision"."rule_version"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."grouping_decision"."rule_version" IS 'rule version';

--
-- Name: COLUMN "grouping_decision"."reasons"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."grouping_decision"."reasons" IS '一致・不一致Attribute、閾値、Manual note。';

--
-- Name: COLUMN "grouping_decision"."decided_by_actor_type"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."grouping_decision"."decided_by_actor_type" IS 'decided by actor type';

--
-- Name: COLUMN "grouping_decision"."decided_by_actor_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."grouping_decision"."decided_by_actor_id" IS 'decided by actor id';

--
-- Name: COLUMN "grouping_decision"."decided_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."grouping_decision"."decided_at" IS 'decided at';

--
-- Name: COLUMN "grouping_decision"."supersedes_decision_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."grouping_decision"."supersedes_decision_id" IS 'supersedes decision id';

--
-- Name: COLUMN "grouping_decision"."created_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."grouping_decision"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: ingestion_request; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."ingestion_request" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "provider_endpoint_id" "uuid" NOT NULL,
    "job_id" "uuid" NOT NULL,
    "request_fingerprint" "text" NOT NULL,
    "request_parameters" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "requested_at" timestamp with time zone NOT NULL,
    "responded_at" timestamp with time zone,
    "http_status" integer,
    "status" "text" NOT NULL,
    "raw_response_artifact_id" "uuid",
    "item_count" integer,
    "rate_limit_observation" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "error_class" "text",
    "error_code" "text",
    "error_message" "text",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_catalog_ingestion_count" CHECK ((("item_count" IS NULL) OR ("item_count" >= 0))),
    CONSTRAINT "ck_catalog_ingestion_fingerprint" CHECK (("request_fingerprint" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_catalog_ingestion_http" CHECK ((("http_status" IS NULL) OR (("http_status" >= 100) AND ("http_status" <= 599)))),
    CONSTRAINT "ck_catalog_ingestion_params" CHECK (("jsonb_typeof"("request_parameters") = 'object'::"text")),
    CONSTRAINT "ck_catalog_ingestion_rate" CHECK (("jsonb_typeof"("rate_limit_observation") = 'object'::"text")),
    CONSTRAINT "ck_catalog_ingestion_response" CHECK ((("status" <> 'SUCCEEDED'::"text") OR (("responded_at" IS NOT NULL) AND ("raw_response_artifact_id" IS NOT NULL)))),
    CONSTRAINT "ck_catalog_ingestion_status" CHECK (("status" = ANY (ARRAY['REQUESTED'::"text", 'SUCCEEDED'::"text", 'FAILED'::"text", 'QUARANTINED'::"text"])))
);

--
-- Name: TABLE "ingestion_request"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."ingestion_request" IS '外部API Request/Responseの契約、raw Artifact、件数、Rate Limit、失敗分類を記録する。';

--
-- Name: COLUMN "ingestion_request"."id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."ingestion_request"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "ingestion_request"."display_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."ingestion_request"."display_id" IS 'ING-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "ingestion_request"."provider_endpoint_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."ingestion_request"."provider_endpoint_id" IS 'provider endpoint id';

--
-- Name: COLUMN "ingestion_request"."job_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."ingestion_request"."job_id" IS '非同期Job。';

--
-- Name: COLUMN "ingestion_request"."request_fingerprint"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."ingestion_request"."request_fingerprint" IS 'request fingerprint';

--
-- Name: COLUMN "ingestion_request"."request_parameters"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."ingestion_request"."request_parameters" IS 'Secretを除外したCanonical request parameters。';

--
-- Name: COLUMN "ingestion_request"."requested_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."ingestion_request"."requested_at" IS 'requested at';

--
-- Name: COLUMN "ingestion_request"."responded_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."ingestion_request"."responded_at" IS 'responded at';

--
-- Name: COLUMN "ingestion_request"."http_status"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."ingestion_request"."http_status" IS 'http status';

--
-- Name: COLUMN "ingestion_request"."status"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."ingestion_request"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "ingestion_request"."raw_response_artifact_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."ingestion_request"."raw_response_artifact_id" IS 'raw response artifact id';

--
-- Name: COLUMN "ingestion_request"."item_count"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."ingestion_request"."item_count" IS 'item count';

--
-- Name: COLUMN "ingestion_request"."rate_limit_observation"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."ingestion_request"."rate_limit_observation" IS 'Remaining、reset時刻等。';

--
-- Name: COLUMN "ingestion_request"."error_class"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."ingestion_request"."error_class" IS 'error class';

--
-- Name: COLUMN "ingestion_request"."error_code"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."ingestion_request"."error_code" IS 'error code';

--
-- Name: COLUMN "ingestion_request"."error_message"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."ingestion_request"."error_message" IS 'error message';

--
-- Name: COLUMN "ingestion_request"."created_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."ingestion_request"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: offer; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."offer" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "provider_endpoint_id" "uuid" NOT NULL,
    "external_offer_id" "text" NOT NULL,
    "product_candidate_id" "uuid" NOT NULL,
    "product_id" "uuid",
    "shop_id" "uuid" NOT NULL,
    "item_url" "text" NOT NULL,
    "status" "text" NOT NULL,
    "first_observed_at" timestamp with time zone NOT NULL,
    "last_observed_at" timestamp with time zone NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    CONSTRAINT "ck_catalog_offer_observed" CHECK (("last_observed_at" >= "first_observed_at")),
    CONSTRAINT "ck_catalog_offer_status" CHECK (("status" = ANY (ARRAY['ACTIVE'::"text", 'OUT_OF_STOCK'::"text", 'ENDED'::"text", 'SUSPENDED'::"text", 'BLOCKED'::"text", 'UNKNOWN'::"text"]))),
    CONSTRAINT "ck_catalog_offer_url" CHECK (("item_url" ~ '^https://'::"text")),
    CONSTRAINT "ck_catalog_offer_version" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "offer"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."offer" IS 'Shop単位の販売OfferをStable ID化し、Product Candidate・Shop・Canonical Productへ結び付ける。';

--
-- Name: COLUMN "offer"."id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "offer"."display_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer"."display_id" IS 'OFF-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "offer"."provider_endpoint_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer"."provider_endpoint_id" IS 'provider endpoint id';

--
-- Name: COLUMN "offer"."external_offer_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer"."external_offer_id" IS 'external offer id';

--
-- Name: COLUMN "offer"."product_candidate_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer"."product_candidate_id" IS 'product candidate id';

--
-- Name: COLUMN "offer"."product_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer"."product_id" IS '正規化されたCanonical Product。';

--
-- Name: COLUMN "offer"."shop_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer"."shop_id" IS 'shop id';

--
-- Name: COLUMN "offer"."item_url"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer"."item_url" IS 'item url';

--
-- Name: COLUMN "offer"."status"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "offer"."first_observed_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer"."first_observed_at" IS 'first observed at';

--
-- Name: COLUMN "offer"."last_observed_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer"."last_observed_at" IS 'last observed at';

--
-- Name: COLUMN "offer"."created_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "offer"."updated_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "offer"."lock_version"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer"."lock_version" IS '楽観的排他制御用の単調増加Version。';

--
-- Name: offer_current_projection; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."offer_current_projection" (
    "offer_id" "uuid" NOT NULL,
    "product_id" "uuid",
    "price_observation_id" "uuid",
    "availability_observation_id" "uuid",
    "review_observation_id" "uuid",
    "affiliate_link_observation_id" "uuid",
    "current_price_jpy" bigint,
    "current_shipping_fee_jpy" bigint,
    "current_availability" "text" DEFAULT 'UNKNOWN'::"text" NOT NULL,
    "review_count" integer,
    "review_average" numeric(3,2),
    "affiliate_url" "text",
    "destination_host" "text",
    "price_observed_at" timestamp with time zone,
    "availability_observed_at" timestamp with time zone,
    "link_observed_at" timestamp with time zone,
    "freshness_status" "text" NOT NULL,
    "projection_version" bigint NOT NULL,
    "updated_at" timestamp with time zone NOT NULL,
    CONSTRAINT "ck_catalog_offer_current_avail" CHECK (("current_availability" = ANY (ARRAY['IN_STOCK'::"text", 'OUT_OF_STOCK'::"text", 'BACKORDER'::"text", 'PREORDER'::"text", 'DISCONTINUED'::"text", 'UNKNOWN'::"text"]))),
    CONSTRAINT "ck_catalog_offer_current_fresh" CHECK (("freshness_status" = ANY (ARRAY['FRESH'::"text", 'WARNING'::"text", 'STALE'::"text", 'UNKNOWN'::"text", 'CONFLICT'::"text"]))),
    CONSTRAINT "ck_catalog_offer_current_price" CHECK ((("current_price_jpy" IS NULL) OR ("current_price_jpy" >= 0))),
    CONSTRAINT "ck_catalog_offer_current_review" CHECK (((("review_count" IS NULL) OR ("review_count" >= 0)) AND (("review_average" IS NULL) OR (("review_average" >= (0)::numeric) AND ("review_average" <= (5)::numeric))))),
    CONSTRAINT "ck_catalog_offer_current_ship" CHECK ((("current_shipping_fee_jpy" IS NULL) OR ("current_shipping_fee_jpy" >= 0))),
    CONSTRAINT "ck_catalog_offer_current_url" CHECK ((("affiliate_url" IS NULL) OR ("affiliate_url" ~ '^https://'::"text"))),
    CONSTRAINT "ck_catalog_offer_current_version" CHECK (("projection_version" >= 1))
);

--
-- Name: TABLE "offer_current_projection"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."offer_current_projection" IS '最新かつValidなObservationを選択した再生成可能Projection。公開候補はさらにFreshness/Policyを通す。';

--
-- Name: COLUMN "offer_current_projection"."offer_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."offer_id" IS 'ショップ単位の販売Offer。';

--
-- Name: COLUMN "offer_current_projection"."product_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."product_id" IS '正規化されたCanonical Product。';

--
-- Name: COLUMN "offer_current_projection"."price_observation_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."price_observation_id" IS 'price observation id';

--
-- Name: COLUMN "offer_current_projection"."availability_observation_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."availability_observation_id" IS 'availability observation id';

--
-- Name: COLUMN "offer_current_projection"."review_observation_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."review_observation_id" IS 'review observation id';

--
-- Name: COLUMN "offer_current_projection"."affiliate_link_observation_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."affiliate_link_observation_id" IS 'affiliate link observation id';

--
-- Name: COLUMN "offer_current_projection"."current_price_jpy"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."current_price_jpy" IS 'current price jpy';

--
-- Name: COLUMN "offer_current_projection"."current_shipping_fee_jpy"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."current_shipping_fee_jpy" IS 'current shipping fee jpy';

--
-- Name: COLUMN "offer_current_projection"."current_availability"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."current_availability" IS 'current availability';

--
-- Name: COLUMN "offer_current_projection"."review_count"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."review_count" IS 'review count';

--
-- Name: COLUMN "offer_current_projection"."review_average"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."review_average" IS 'review average';

--
-- Name: COLUMN "offer_current_projection"."affiliate_url"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."affiliate_url" IS 'affiliate url';

--
-- Name: COLUMN "offer_current_projection"."destination_host"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."destination_host" IS 'destination host';

--
-- Name: COLUMN "offer_current_projection"."price_observed_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."price_observed_at" IS 'price observed at';

--
-- Name: COLUMN "offer_current_projection"."availability_observed_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."availability_observed_at" IS 'availability observed at';

--
-- Name: COLUMN "offer_current_projection"."link_observed_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."link_observed_at" IS 'link observed at';

--
-- Name: COLUMN "offer_current_projection"."freshness_status"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."freshness_status" IS 'freshness status';

--
-- Name: COLUMN "offer_current_projection"."projection_version"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."projection_version" IS 'projection version';

--
-- Name: COLUMN "offer_current_projection"."updated_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."offer_current_projection"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: price_observation; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."price_observation" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "offer_id" "uuid" NOT NULL,
    "price_jpy" bigint NOT NULL,
    "tax_included" boolean DEFAULT true NOT NULL,
    "shipping_fee_jpy" bigint,
    "shipping_condition" "text" NOT NULL,
    "points_rate" numeric(9,6),
    "observed_at" timestamp with time zone NOT NULL,
    "ingested_at" timestamp with time zone NOT NULL,
    "valid_until" timestamp with time zone,
    "source_snapshot_id" "uuid" NOT NULL,
    "validation_status" "text" NOT NULL,
    "confidence" numeric(5,4) NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_catalog_price_conf" CHECK ((("confidence" >= (0)::numeric) AND ("confidence" <= (1)::numeric))),
    CONSTRAINT "ck_catalog_price_nonnegative" CHECK ((("price_jpy" >= 0) AND (("shipping_fee_jpy" IS NULL) OR ("shipping_fee_jpy" >= 0)))),
    CONSTRAINT "ck_catalog_price_points" CHECK ((("points_rate" IS NULL) OR (("points_rate" >= (0)::numeric) AND ("points_rate" <= (100)::numeric)))),
    CONSTRAINT "ck_catalog_price_shipping" CHECK (("shipping_condition" = ANY (ARRAY['FREE'::"text", 'PAID'::"text", 'CONDITIONAL'::"text", 'INCLUDED'::"text", 'UNKNOWN'::"text"]))),
    CONSTRAINT "ck_catalog_price_valid" CHECK ((("valid_until" IS NULL) OR ("valid_until" > "observed_at"))),
    CONSTRAINT "ck_catalog_price_validation" CHECK (("validation_status" = ANY (ARRAY['VALID'::"text", 'SUSPECT'::"text", 'INVALID'::"text", 'CONFLICT'::"text"])))
);

--
-- Name: TABLE "price_observation"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."price_observation" IS '価格・送料・Point等の時点事実を上書きせず追記する。';

--
-- Name: COLUMN "price_observation"."id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."price_observation"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "price_observation"."offer_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."price_observation"."offer_id" IS 'ショップ単位の販売Offer。';

--
-- Name: COLUMN "price_observation"."price_jpy"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."price_observation"."price_jpy" IS 'price jpy';

--
-- Name: COLUMN "price_observation"."tax_included"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."price_observation"."tax_included" IS 'tax included';

--
-- Name: COLUMN "price_observation"."shipping_fee_jpy"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."price_observation"."shipping_fee_jpy" IS 'shipping fee jpy';

--
-- Name: COLUMN "price_observation"."shipping_condition"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."price_observation"."shipping_condition" IS 'shipping condition';

--
-- Name: COLUMN "price_observation"."points_rate"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."price_observation"."points_rate" IS 'points rate';

--
-- Name: COLUMN "price_observation"."observed_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."price_observation"."observed_at" IS 'observed at';

--
-- Name: COLUMN "price_observation"."ingested_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."price_observation"."ingested_at" IS 'ingested at';

--
-- Name: COLUMN "price_observation"."valid_until"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."price_observation"."valid_until" IS 'valid until';

--
-- Name: COLUMN "price_observation"."source_snapshot_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."price_observation"."source_snapshot_id" IS 'source snapshot id';

--
-- Name: COLUMN "price_observation"."validation_status"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."price_observation"."validation_status" IS 'validation status';

--
-- Name: COLUMN "price_observation"."confidence"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."price_observation"."confidence" IS 'confidence';

--
-- Name: COLUMN "price_observation"."created_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."price_observation"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: product_attribute_value; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."product_attribute_value" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "product_id" "uuid" NOT NULL,
    "attribute_definition_id" "uuid" NOT NULL,
    "value_text" "text",
    "value_numeric" numeric(30,10),
    "value_boolean" boolean,
    "value_date" "date",
    "value_code" "text",
    "unit_code" "text",
    "source_fact_id" "uuid",
    "confidence" numeric(5,4) NOT NULL,
    "valid_from" timestamp with time zone NOT NULL,
    "valid_to" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_catalog_product_attr_conf" CHECK ((("confidence" >= (0)::numeric) AND ("confidence" <= (1)::numeric))),
    CONSTRAINT "ck_catalog_product_attr_one_value" CHECK (("num_nonnulls"("value_text", "value_numeric", "value_boolean", "value_date", "value_code") = 1)),
    CONSTRAINT "ck_catalog_product_attr_window" CHECK ((("valid_to" IS NULL) OR ("valid_to" > "valid_from")))
);

--
-- Name: TABLE "product_attribute_value"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."product_attribute_value" IS 'Canonical Productの型付きAttribute値と根拠Fact、有効期間、信頼度を保持する。';

--
-- Name: COLUMN "product_attribute_value"."id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_attribute_value"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "product_attribute_value"."product_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_attribute_value"."product_id" IS '正規化されたCanonical Product。';

--
-- Name: COLUMN "product_attribute_value"."attribute_definition_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_attribute_value"."attribute_definition_id" IS 'attribute definition id';

--
-- Name: COLUMN "product_attribute_value"."value_text"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_attribute_value"."value_text" IS 'value text';

--
-- Name: COLUMN "product_attribute_value"."value_numeric"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_attribute_value"."value_numeric" IS 'value numeric';

--
-- Name: COLUMN "product_attribute_value"."value_boolean"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_attribute_value"."value_boolean" IS 'value boolean';

--
-- Name: COLUMN "product_attribute_value"."value_date"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_attribute_value"."value_date" IS 'value date';

--
-- Name: COLUMN "product_attribute_value"."value_code"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_attribute_value"."value_code" IS 'value code';

--
-- Name: COLUMN "product_attribute_value"."unit_code"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_attribute_value"."unit_code" IS 'unit code';

--
-- Name: COLUMN "product_attribute_value"."source_fact_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_attribute_value"."source_fact_id" IS 'source fact id';

--
-- Name: COLUMN "product_attribute_value"."confidence"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_attribute_value"."confidence" IS 'confidence';

--
-- Name: COLUMN "product_attribute_value"."valid_from"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_attribute_value"."valid_from" IS 'valid from';

--
-- Name: COLUMN "product_attribute_value"."valid_to"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_attribute_value"."valid_to" IS 'valid to';

--
-- Name: COLUMN "product_attribute_value"."created_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_attribute_value"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: product_candidate; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."product_candidate" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "provider_endpoint_id" "uuid" NOT NULL,
    "external_item_code" "text" NOT NULL,
    "shop_id" "uuid" NOT NULL,
    "rakuten_genre_id" "uuid",
    "item_name" "text" NOT NULL,
    "normalized_item_name" "text" NOT NULL,
    "model_number_candidate" "text",
    "jan_code_candidate" "text",
    "image_set" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "listing_status" "text" NOT NULL,
    "first_observed_at" timestamp with time zone NOT NULL,
    "last_observed_at" timestamp with time zone NOT NULL,
    "source_snapshot_id" "uuid" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    CONSTRAINT "ck_catalog_candidate_images" CHECK (("jsonb_typeof"("image_set") = 'object'::"text")),
    CONSTRAINT "ck_catalog_candidate_jan" CHECK ((("jan_code_candidate" IS NULL) OR ("jan_code_candidate" ~ '^[0-9]{8,14}$'::"text"))),
    CONSTRAINT "ck_catalog_candidate_observed" CHECK (("last_observed_at" >= "first_observed_at")),
    CONSTRAINT "ck_catalog_candidate_status" CHECK (("listing_status" = ANY (ARRAY['ACTIVE'::"text", 'MISSING'::"text", 'ENDED'::"text", 'BLOCKED'::"text", 'UNKNOWN'::"text"]))),
    CONSTRAINT "ck_catalog_candidate_version" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "product_candidate"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."product_candidate" IS 'Provider Listingから抽出した商品候補。raw本文はArtifactへ置き、比較に必要な正規化項目と許可画像URLのみ保持する。';

--
-- Name: COLUMN "product_candidate"."id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "product_candidate"."display_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."display_id" IS 'PCD-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "product_candidate"."provider_endpoint_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."provider_endpoint_id" IS 'provider endpoint id';

--
-- Name: COLUMN "product_candidate"."external_item_code"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."external_item_code" IS 'external item code';

--
-- Name: COLUMN "product_candidate"."shop_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."shop_id" IS 'shop id';

--
-- Name: COLUMN "product_candidate"."rakuten_genre_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."rakuten_genre_id" IS 'rakuten genre id';

--
-- Name: COLUMN "product_candidate"."item_name"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."item_name" IS 'item name';

--
-- Name: COLUMN "product_candidate"."normalized_item_name"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."normalized_item_name" IS 'normalized item name';

--
-- Name: COLUMN "product_candidate"."model_number_candidate"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."model_number_candidate" IS 'model number candidate';

--
-- Name: COLUMN "product_candidate"."jan_code_candidate"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."jan_code_candidate" IS 'jan code candidate';

--
-- Name: COLUMN "product_candidate"."image_set"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."image_set" IS 'APIが返した許可画像URL、order、size。Overlay/Crop後画像は登録しない。';

--
-- Name: COLUMN "product_candidate"."listing_status"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."listing_status" IS 'listing status';

--
-- Name: COLUMN "product_candidate"."first_observed_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."first_observed_at" IS 'first observed at';

--
-- Name: COLUMN "product_candidate"."last_observed_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."last_observed_at" IS 'last observed at';

--
-- Name: COLUMN "product_candidate"."source_snapshot_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."source_snapshot_id" IS 'source snapshot id';

--
-- Name: COLUMN "product_candidate"."created_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "product_candidate"."updated_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "product_candidate"."lock_version"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_candidate"."lock_version" IS '楽観的排他制御用の単調増加Version。';

--
-- Name: product_group_membership; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."product_group_membership" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "product_id" "uuid" NOT NULL,
    "product_candidate_id" "uuid" NOT NULL,
    "grouping_decision_id" "uuid" NOT NULL,
    "valid_from" timestamp with time zone NOT NULL,
    "valid_to" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_catalog_membership_window" CHECK ((("valid_to" IS NULL) OR ("valid_to" > "valid_from")))
);

--
-- Name: TABLE "product_group_membership"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."product_group_membership" IS 'Product CandidateがどのCanonical Productへ属したかを有効期間付きで記録する。';

--
-- Name: COLUMN "product_group_membership"."id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_group_membership"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "product_group_membership"."product_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_group_membership"."product_id" IS '正規化されたCanonical Product。';

--
-- Name: COLUMN "product_group_membership"."product_candidate_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_group_membership"."product_candidate_id" IS 'product candidate id';

--
-- Name: COLUMN "product_group_membership"."grouping_decision_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_group_membership"."grouping_decision_id" IS 'grouping decision id';

--
-- Name: COLUMN "product_group_membership"."valid_from"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_group_membership"."valid_from" IS 'valid from';

--
-- Name: COLUMN "product_group_membership"."valid_to"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_group_membership"."valid_to" IS 'valid to';

--
-- Name: COLUMN "product_group_membership"."created_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_group_membership"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: product_relation; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."product_relation" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "from_product_id" "uuid" NOT NULL,
    "to_product_id" "uuid" NOT NULL,
    "relation_type" "text" NOT NULL,
    "confidence" numeric(5,4) NOT NULL,
    "source_fact_id" "uuid",
    "valid_from" timestamp with time zone NOT NULL,
    "valid_to" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_catalog_product_relation_conf" CHECK ((("confidence" >= (0)::numeric) AND ("confidence" <= (1)::numeric))),
    CONSTRAINT "ck_catalog_product_relation_self" CHECK (("from_product_id" <> "to_product_id")),
    CONSTRAINT "ck_catalog_product_relation_type" CHECK (("relation_type" = ANY (ARRAY['VARIANT'::"text", 'SUCCESSOR'::"text", 'PREDECESSOR'::"text", 'BUNDLE'::"text", 'COMPATIBLE'::"text", 'EQUIVALENT'::"text", 'ACCESSORY'::"text"]))),
    CONSTRAINT "ck_catalog_product_relation_window" CHECK ((("valid_to" IS NULL) OR ("valid_to" > "valid_from")))
);

--
-- Name: TABLE "product_relation"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."product_relation" IS '後継、前世代、Variant、Bundle、Equivalent等の商品関係を根拠付きで管理する。';

--
-- Name: COLUMN "product_relation"."id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_relation"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "product_relation"."from_product_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_relation"."from_product_id" IS 'from product id';

--
-- Name: COLUMN "product_relation"."to_product_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_relation"."to_product_id" IS 'to product id';

--
-- Name: COLUMN "product_relation"."relation_type"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_relation"."relation_type" IS 'relation type';

--
-- Name: COLUMN "product_relation"."confidence"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_relation"."confidence" IS 'confidence';

--
-- Name: COLUMN "product_relation"."source_fact_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_relation"."source_fact_id" IS 'source fact id';

--
-- Name: COLUMN "product_relation"."valid_from"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_relation"."valid_from" IS 'valid from';

--
-- Name: COLUMN "product_relation"."valid_to"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_relation"."valid_to" IS 'valid to';

--
-- Name: COLUMN "product_relation"."created_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."product_relation"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: provider_endpoint; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."provider_endpoint" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "provider_code" "text" NOT NULL,
    "provider_name" "text" NOT NULL,
    "api_name" "text" NOT NULL,
    "api_version" "text" NOT NULL,
    "base_host" "text" NOT NULL,
    "status" "text" NOT NULL,
    "contract_sha256" "text" NOT NULL,
    "documentation_url" "text",
    "non_secret_config" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "effective_from" timestamp with time zone NOT NULL,
    "effective_to" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_catalog_provider_config" CHECK (("jsonb_typeof"("non_secret_config") = 'object'::"text")),
    CONSTRAINT "ck_catalog_provider_contract_hash" CHECK (("contract_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_catalog_provider_host" CHECK (("base_host" ~ '^[a-z0-9.-]+$'::"text")),
    CONSTRAINT "ck_catalog_provider_status" CHECK (("status" = ANY (ARRAY['DRAFT'::"text", 'ACTIVE'::"text", 'DEPRECATED'::"text", 'RETIRED'::"text", 'BLOCKED'::"text"]))),
    CONSTRAINT "ck_catalog_provider_window" CHECK ((("effective_to" IS NULL) OR ("effective_to" > "effective_from")))
);

--
-- Name: TABLE "provider_endpoint"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."provider_endpoint" IS '楽天等のCommerce ProviderとAPI Contract versionを一つのVersion行として管理する。Secretは含めない。';

--
-- Name: COLUMN "provider_endpoint"."id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."provider_endpoint"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "provider_endpoint"."provider_code"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."provider_endpoint"."provider_code" IS 'provider code';

--
-- Name: COLUMN "provider_endpoint"."provider_name"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."provider_endpoint"."provider_name" IS 'provider name';

--
-- Name: COLUMN "provider_endpoint"."api_name"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."provider_endpoint"."api_name" IS 'api name';

--
-- Name: COLUMN "provider_endpoint"."api_version"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."provider_endpoint"."api_version" IS 'api version';

--
-- Name: COLUMN "provider_endpoint"."base_host"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."provider_endpoint"."base_host" IS 'base host';

--
-- Name: COLUMN "provider_endpoint"."status"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."provider_endpoint"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "provider_endpoint"."contract_sha256"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."provider_endpoint"."contract_sha256" IS 'contract sha256';

--
-- Name: COLUMN "provider_endpoint"."documentation_url"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."provider_endpoint"."documentation_url" IS 'documentation url';

--
-- Name: COLUMN "provider_endpoint"."non_secret_config"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."provider_endpoint"."non_secret_config" IS 'Timeout、page size、field mapping等。Application ID、Access Key、Affiliate IDは含めない。';

--
-- Name: COLUMN "provider_endpoint"."effective_from"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."provider_endpoint"."effective_from" IS '設定・関係が有効になる時刻。';

--
-- Name: COLUMN "provider_endpoint"."effective_to"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."provider_endpoint"."effective_to" IS '設定・関係の有効終了時刻。NULLは終了未定。';

--
-- Name: COLUMN "provider_endpoint"."created_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."provider_endpoint"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: rakuten_genre; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."rakuten_genre" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "provider_endpoint_id" "uuid" NOT NULL,
    "external_genre_id" bigint NOT NULL,
    "parent_external_genre_id" bigint,
    "genre_name" "text" NOT NULL,
    "genre_level" smallint NOT NULL,
    "is_leaf" boolean NOT NULL,
    "is_active" boolean DEFAULT true NOT NULL,
    "source_snapshot_id" "uuid" NOT NULL,
    "observed_at" timestamp with time zone NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    CONSTRAINT "ck_catalog_rakuten_genre_id" CHECK (("external_genre_id" > 0)),
    CONSTRAINT "ck_catalog_rakuten_genre_level" CHECK (("genre_level" >= 0)),
    CONSTRAINT "ck_catalog_rakuten_genre_parent" CHECK ((("parent_external_genre_id" IS NULL) OR ("parent_external_genre_id" <> "external_genre_id"))),
    CONSTRAINT "ck_catalog_rakuten_genre_version" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "rakuten_genre"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."rakuten_genre" IS '楽天ジャンルID階層のVersioned current registry。';

--
-- Name: COLUMN "rakuten_genre"."id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."rakuten_genre"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "rakuten_genre"."provider_endpoint_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."rakuten_genre"."provider_endpoint_id" IS 'provider endpoint id';

--
-- Name: COLUMN "rakuten_genre"."external_genre_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."rakuten_genre"."external_genre_id" IS 'external genre id';

--
-- Name: COLUMN "rakuten_genre"."parent_external_genre_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."rakuten_genre"."parent_external_genre_id" IS 'parent external genre id';

--
-- Name: COLUMN "rakuten_genre"."genre_name"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."rakuten_genre"."genre_name" IS 'genre name';

--
-- Name: COLUMN "rakuten_genre"."genre_level"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."rakuten_genre"."genre_level" IS 'genre level';

--
-- Name: COLUMN "rakuten_genre"."is_leaf"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."rakuten_genre"."is_leaf" IS 'is leaf';

--
-- Name: COLUMN "rakuten_genre"."is_active"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."rakuten_genre"."is_active" IS 'is active';

--
-- Name: COLUMN "rakuten_genre"."source_snapshot_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."rakuten_genre"."source_snapshot_id" IS 'source snapshot id';

--
-- Name: COLUMN "rakuten_genre"."observed_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."rakuten_genre"."observed_at" IS 'observed at';

--
-- Name: COLUMN "rakuten_genre"."created_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."rakuten_genre"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "rakuten_genre"."updated_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."rakuten_genre"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "rakuten_genre"."lock_version"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."rakuten_genre"."lock_version" IS '楽観的排他制御用の単調増加Version。';

--
-- Name: review_aggregate_observation; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."review_aggregate_observation" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "offer_id" "uuid" NOT NULL,
    "review_count" integer NOT NULL,
    "review_average" numeric(3,2),
    "observed_at" timestamp with time zone NOT NULL,
    "ingested_at" timestamp with time zone NOT NULL,
    "source_snapshot_id" "uuid" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_catalog_review_average" CHECK ((("review_average" IS NULL) OR (("review_average" >= (0)::numeric) AND ("review_average" <= (5)::numeric)))),
    CONSTRAINT "ck_catalog_review_count" CHECK (("review_count" >= 0))
);

--
-- Name: TABLE "review_aggregate_observation"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."review_aggregate_observation" IS '楽天APIが返すReview件数・平均評価のみを保存する。Review本文を保存するColumnは設けない。';

--
-- Name: COLUMN "review_aggregate_observation"."id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."review_aggregate_observation"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "review_aggregate_observation"."offer_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."review_aggregate_observation"."offer_id" IS 'ショップ単位の販売Offer。';

--
-- Name: COLUMN "review_aggregate_observation"."review_count"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."review_aggregate_observation"."review_count" IS 'review count';

--
-- Name: COLUMN "review_aggregate_observation"."review_average"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."review_aggregate_observation"."review_average" IS 'review average';

--
-- Name: COLUMN "review_aggregate_observation"."observed_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."review_aggregate_observation"."observed_at" IS 'observed at';

--
-- Name: COLUMN "review_aggregate_observation"."ingested_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."review_aggregate_observation"."ingested_at" IS 'ingested at';

--
-- Name: COLUMN "review_aggregate_observation"."source_snapshot_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."review_aggregate_observation"."source_snapshot_id" IS 'source snapshot id';

--
-- Name: COLUMN "review_aggregate_observation"."created_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."review_aggregate_observation"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: shop; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."shop" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "provider_endpoint_id" "uuid" NOT NULL,
    "external_shop_code" "text" NOT NULL,
    "shop_name" "text" NOT NULL,
    "shop_url" "text",
    "affiliate_capable" boolean DEFAULT true NOT NULL,
    "status" "text" NOT NULL,
    "first_observed_at" timestamp with time zone NOT NULL,
    "last_observed_at" timestamp with time zone NOT NULL,
    "source_snapshot_id" "uuid" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    CONSTRAINT "ck_catalog_shop_observed" CHECK (("last_observed_at" >= "first_observed_at")),
    CONSTRAINT "ck_catalog_shop_status" CHECK (("status" = ANY (ARRAY['ACTIVE'::"text", 'INACTIVE'::"text", 'BLOCKED'::"text", 'UNKNOWN'::"text"]))),
    CONSTRAINT "ck_catalog_shop_url" CHECK ((("shop_url" IS NULL) OR ("shop_url" ~ '^https://'::"text"))),
    CONSTRAINT "ck_catalog_shop_version" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "shop"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."shop" IS 'Provider内ShopをStable IDへ正規化する。';

--
-- Name: COLUMN "shop"."id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."shop"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "shop"."display_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."shop"."display_id" IS 'SHP-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "shop"."provider_endpoint_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."shop"."provider_endpoint_id" IS 'provider endpoint id';

--
-- Name: COLUMN "shop"."external_shop_code"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."shop"."external_shop_code" IS 'external shop code';

--
-- Name: COLUMN "shop"."shop_name"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."shop"."shop_name" IS 'shop name';

--
-- Name: COLUMN "shop"."shop_url"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."shop"."shop_url" IS 'shop url';

--
-- Name: COLUMN "shop"."affiliate_capable"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."shop"."affiliate_capable" IS 'affiliate capable';

--
-- Name: COLUMN "shop"."status"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."shop"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "shop"."first_observed_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."shop"."first_observed_at" IS 'first observed at';

--
-- Name: COLUMN "shop"."last_observed_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."shop"."last_observed_at" IS 'last observed at';

--
-- Name: COLUMN "shop"."source_snapshot_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."shop"."source_snapshot_id" IS 'source snapshot id';

--
-- Name: COLUMN "shop"."created_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."shop"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "shop"."updated_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."shop"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "shop"."lock_version"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."shop"."lock_version" IS '楽観的排他制御用の単調増加Version。';

--
-- Name: v_safe_offer_current; Type: VIEW; Schema: catalog; Owner: -
--

CREATE VIEW "catalog"."v_safe_offer_current" AS
 SELECT "p"."offer_id",
    "p"."product_id",
    "o"."shop_id",
    "p"."current_price_jpy",
    "p"."current_shipping_fee_jpy",
    "p"."current_availability",
    "p"."review_count",
    "p"."review_average",
    "p"."affiliate_url",
    "p"."destination_host",
    "p"."price_observed_at",
    "p"."availability_observed_at",
    "p"."link_observed_at",
    "p"."freshness_status",
    "p"."projection_version",
    "p"."updated_at"
   FROM ("catalog"."offer_current_projection" "p"
     JOIN "catalog"."offer" "o" ON (("o"."id" = "p"."offer_id")));

--
-- Name: article; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."article" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "site_id" "uuid" NOT NULL,
    "article_plan_id" "uuid" NOT NULL,
    "article_type" "text" NOT NULL,
    "status" "text" DEFAULT 'IDEA'::"text" NOT NULL,
    "current_version_id" "uuid",
    "published_version_id" "uuid",
    "archived_at" timestamp with time zone,
    "archive_reason" "text",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    CONSTRAINT "ck_editorial_article_archive" CHECK ((("status" <> 'ARCHIVED'::"text") OR ("archived_at" IS NOT NULL))),
    CONSTRAINT "ck_editorial_article_status" CHECK (("status" = ANY (ARRAY['IDEA'::"text", 'PLANNED'::"text", 'SOURCES_PENDING'::"text", 'PACKET_READY'::"text", 'GENERATING'::"text", 'DRAFT'::"text", 'AUTO_REVIEW'::"text", 'HUMAN_REVIEW'::"text", 'APPROVED'::"text", 'SCHEDULED'::"text", 'PUBLISHED'::"text", 'UPDATE_PENDING'::"text", 'PAUSED'::"text", 'ARCHIVED'::"text"]))),
    CONSTRAINT "ck_editorial_article_type" CHECK (("article_type" = ANY (ARRAY['SELECTION_GUIDE'::"text", 'USE_CASE_RECOMMENDATION'::"text", 'PRODUCT_COMPARISON'::"text", 'MODEL_DIFFERENCE'::"text", 'CONDITION_FILTER'::"text"]))),
    CONSTRAINT "ck_editorial_article_version" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "article"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON TABLE "editorial"."article" IS '論理記事Aggregate。SlugやVersionを分離し、current/published Versionはdeferrable FKで指す。';

--
-- Name: COLUMN "article"."id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "article"."display_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article"."display_id" IS 'ART-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "article"."site_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article"."site_id" IS '対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。';

--
-- Name: COLUMN "article"."article_plan_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article"."article_plan_id" IS 'article plan id';

--
-- Name: COLUMN "article"."article_type"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article"."article_type" IS 'article type';

--
-- Name: COLUMN "article"."status"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "article"."current_version_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article"."current_version_id" IS 'current version id';

--
-- Name: COLUMN "article"."published_version_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article"."published_version_id" IS 'published version id';

--
-- Name: COLUMN "article"."archived_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article"."archived_at" IS 'archived at';

--
-- Name: COLUMN "article"."archive_reason"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article"."archive_reason" IS 'archive reason';

--
-- Name: COLUMN "article"."created_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "article"."updated_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "article"."lock_version"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article"."lock_version" IS '楽観的排他制御用の単調増加Version。';

--
-- Name: article_block; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."article_block" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "article_version_id" "uuid" NOT NULL,
    "block_key" "text" NOT NULL,
    "block_type" "text" NOT NULL,
    "position" integer NOT NULL,
    "heading_level" smallint,
    "content" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "plain_text" "text" NOT NULL,
    "content_sha256" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_editorial_block_content" CHECK (("jsonb_typeof"("content") = 'object'::"text")),
    CONSTRAINT "ck_editorial_block_hash" CHECK (("content_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_editorial_block_heading" CHECK ((("heading_level" IS NULL) OR (("heading_level" >= 2) AND ("heading_level" <= 4)))),
    CONSTRAINT "ck_editorial_block_position" CHECK (("position" >= 0)),
    CONSTRAINT "ck_editorial_block_type" CHECK (("block_type" = ANY (ARRAY['INTRO'::"text", 'HEADING'::"text", 'PARAGRAPH'::"text", 'SELECTION_CRITERIA'::"text", 'COMPARISON_TABLE'::"text", 'PRODUCT_CARD'::"text", 'RECOMMENDATION'::"text", 'FIT_NONFIT'::"text", 'FAQ'::"text", 'DISCLOSURE'::"text", 'SUMMARY'::"text", 'CALLOUT'::"text", 'INTERNAL_LINKS'::"text"])))
);

--
-- Name: TABLE "article_block"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON TABLE "editorial"."article_block" IS 'Article Version内の順序付き構造化Block。任意HTMLではなくBlock type＋Schema-valid JSONを保存する。';

--
-- Name: COLUMN "article_block"."id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_block"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "article_block"."article_version_id"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_block"."article_version_id" IS '記事の特定Version。';

--
-- Name: COLUMN "article_block"."block_key"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_block"."block_key" IS 'block key';

--
-- Name: COLUMN "article_block"."block_type"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_block"."block_type" IS 'block type';

--
-- Name: COLUMN "article_block"."position"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_block"."position" IS 'position';

--
-- Name: COLUMN "article_block"."heading_level"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_block"."heading_level" IS 'heading level';

--
-- Name: COLUMN "article_block"."content"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_block"."content" IS 'Block type別JSON Schemaに適合した構造化本文。';

--
-- Name: COLUMN "article_block"."plain_text"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_block"."plain_text" IS 'plain text';

--
-- Name: COLUMN "article_block"."content_sha256"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_block"."content_sha256" IS 'content sha256';

--
-- Name: COLUMN "article_block"."created_at"; Type: COMMENT; Schema: editorial; Owner: -
--

COMMENT ON COLUMN "editorial"."article_block"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: article_block_product; Type: TABLE; Schema: editorial; Owner: -
--

CREATE TABLE "editorial"."article_block_product" (
    "article_block_id" "uuid" NOT NULL,
    "product_id" "uuid" NOT NULL,
    "offer_id" "uuid",
    "placement_role" "text" NOT NULL,
    "position" integer NOT NULL,
    "placement_id" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_editorial_block_product_position" CHECK (("position" >= 0)),
    CONSTRAINT "ck_editorial_block_product_role" CHECK (("placement_role" = ANY (ARRAY['PRIMARY'::"text", 'ALTERNATIVE'::"text", 'COMPARED'::"text", 'MENTIONED'::"text", 'EXCLUDED'::"text"])))
);
