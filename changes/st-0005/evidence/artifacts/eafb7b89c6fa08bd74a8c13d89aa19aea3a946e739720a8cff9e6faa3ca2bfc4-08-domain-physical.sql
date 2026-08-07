-- ST-0304 physical translation fragment 08 of 11.
-- Source: approved RAOS data catalog plus finalized ST-0003/ST-0004 semantics.
-- Capture: PostgreSQL 18.4 pg_dump --schema-only --no-owner --no-privileges
--          --no-security-labels --quote-all-identifiers for the six owned schemas.
-- Schema creation/comments are rendered once by the ST-0304 generator. The 22
-- role-bound CREATE POLICY objects remain ST-0306-owned. ENABLE/FORCE RLS remains.

--
-- Name: COLUMN "keyword_metric_observation"."observed_date"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword_metric_observation"."observed_date" IS 'observed date';

--
-- Name: COLUMN "keyword_metric_observation"."confidence"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword_metric_observation"."confidence" IS 'confidence';

--
-- Name: COLUMN "keyword_metric_observation"."raw_artifact_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword_metric_observation"."raw_artifact_id" IS 'raw artifact id';

--
-- Name: COLUMN "keyword_metric_observation"."ingested_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword_metric_observation"."ingested_at" IS 'ingested at';

--
-- Name: COLUMN "keyword_metric_observation"."created_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."keyword_metric_observation"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: opportunity_assessment; Type: TABLE; Schema: portfolio; Owner: -
--

CREATE TABLE "portfolio"."opportunity_assessment" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "category_id" "uuid" NOT NULL,
    "intent_cluster_id" "uuid",
    "keyword_id" "uuid",
    "assessment_type" "text" NOT NULL,
    "formula_version" "text" NOT NULL,
    "editorial_feasibility_score" numeric(5,2) NOT NULL,
    "business_opportunity_score" numeric(5,2) NOT NULL,
    "compliance_risk_score" numeric(5,2) NOT NULL,
    "overall_priority_score" numeric(5,2) NOT NULL,
    "decision" "text" NOT NULL,
    "editorial_components" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "business_components" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "compliance_components" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "assessed_at" timestamp with time zone NOT NULL,
    "assessed_by_actor_type" "text" NOT NULL,
    "assessed_by_actor_id" "uuid",
    "expires_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_portfolio_opp_business" CHECK ((("business_opportunity_score" >= (0)::numeric) AND ("business_opportunity_score" <= (100)::numeric))),
    CONSTRAINT "ck_portfolio_opp_business_json" CHECK (("jsonb_typeof"("business_components") = 'object'::"text")),
    CONSTRAINT "ck_portfolio_opp_compliance" CHECK ((("compliance_risk_score" >= (0)::numeric) AND ("compliance_risk_score" <= (100)::numeric))),
    CONSTRAINT "ck_portfolio_opp_compliance_json" CHECK (("jsonb_typeof"("compliance_components") = 'object'::"text")),
    CONSTRAINT "ck_portfolio_opp_decision" CHECK (("decision" = ANY (ARRAY['PURSUE'::"text", 'RESEARCH'::"text", 'HOLD'::"text", 'REJECT'::"text", 'EXIT'::"text"]))),
    CONSTRAINT "ck_portfolio_opp_editorial" CHECK ((("editorial_feasibility_score" >= (0)::numeric) AND ("editorial_feasibility_score" <= (100)::numeric))),
    CONSTRAINT "ck_portfolio_opp_editorial_json" CHECK (("jsonb_typeof"("editorial_components") = 'object'::"text")),
    CONSTRAINT "ck_portfolio_opp_expiry" CHECK ((("expires_at" IS NULL) OR ("expires_at" > "assessed_at"))),
    CONSTRAINT "ck_portfolio_opp_priority" CHECK ((("overall_priority_score" >= (0)::numeric) AND ("overall_priority_score" <= (100)::numeric))),
    CONSTRAINT "ck_portfolio_opp_type" CHECK (("assessment_type" = ANY (ARRAY['CATEGORY'::"text", 'CLUSTER'::"text", 'KEYWORD'::"text", 'ARTICLE_PLAN'::"text"])))
);

--
-- Name: TABLE "opportunity_assessment"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON TABLE "portfolio"."opportunity_assessment" IS 'Editorial feasibility、Business opportunity、Compliance riskを混合せず別Column・別根拠で評価する版付き判断。';

--
-- Name: COLUMN "opportunity_assessment"."id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "opportunity_assessment"."display_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."display_id" IS 'OPA-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "opportunity_assessment"."category_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."category_id" IS '対象カテゴリ。';

--
-- Name: COLUMN "opportunity_assessment"."intent_cluster_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."intent_cluster_id" IS 'intent cluster id';

--
-- Name: COLUMN "opportunity_assessment"."keyword_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."keyword_id" IS 'keyword id';

--
-- Name: COLUMN "opportunity_assessment"."assessment_type"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."assessment_type" IS 'assessment type';

--
-- Name: COLUMN "opportunity_assessment"."formula_version"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."formula_version" IS 'formula version';

--
-- Name: COLUMN "opportunity_assessment"."editorial_feasibility_score"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."editorial_feasibility_score" IS 'editorial feasibility score';

--
-- Name: COLUMN "opportunity_assessment"."business_opportunity_score"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."business_opportunity_score" IS 'business opportunity score';

--
-- Name: COLUMN "opportunity_assessment"."compliance_risk_score"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."compliance_risk_score" IS 'compliance risk score';

--
-- Name: COLUMN "opportunity_assessment"."overall_priority_score"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."overall_priority_score" IS 'overall priority score';

--
-- Name: COLUMN "opportunity_assessment"."decision"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."decision" IS 'decision';

--
-- Name: COLUMN "opportunity_assessment"."editorial_components"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."editorial_components" IS 'Editorialに必要な一次情報、独自価値、比較可能性等。';

--
-- Name: COLUMN "opportunity_assessment"."business_components"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."business_components" IS '需要、競争、商品数、想定EPC等。推薦順位には渡さない。';

--
-- Name: COLUMN "opportunity_assessment"."compliance_components"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."compliance_components" IS 'Category、表示、著作権、規約、YMYL等のRisk。';

--
-- Name: COLUMN "opportunity_assessment"."assessed_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."assessed_at" IS 'assessed at';

--
-- Name: COLUMN "opportunity_assessment"."assessed_by_actor_type"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."assessed_by_actor_type" IS 'assessed by actor type';

--
-- Name: COLUMN "opportunity_assessment"."assessed_by_actor_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."assessed_by_actor_id" IS 'assessed by actor id';

--
-- Name: COLUMN "opportunity_assessment"."expires_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."expires_at" IS 'expires at';

--
-- Name: COLUMN "opportunity_assessment"."created_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."opportunity_assessment"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: site; Type: TABLE; Schema: portfolio; Owner: -
--

CREATE TABLE "portfolio"."site" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "site_code" "text" NOT NULL,
    "name" "text" NOT NULL,
    "primary_domain" "text" NOT NULL,
    "brand_name" "text" NOT NULL,
    "locale" "text" DEFAULT 'ja-JP'::"text" NOT NULL,
    "timezone" "text" DEFAULT 'Asia/Tokyo'::"text" NOT NULL,
    "currency" "text" DEFAULT 'JPY'::"text" NOT NULL,
    "status" "text" DEFAULT 'PLANNING'::"text" NOT NULL,
    "public_settings" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    CONSTRAINT "ck_portfolio_site_currency" CHECK (("currency" ~ '^[A-Z]{3}$'::"text")),
    CONSTRAINT "ck_portfolio_site_domain" CHECK (("primary_domain" ~ '^[a-z0-9.-]+$'::"text")),
    CONSTRAINT "ck_portfolio_site_settings" CHECK (("jsonb_typeof"("public_settings") = 'object'::"text")),
    CONSTRAINT "ck_portfolio_site_status" CHECK (("status" = ANY (ARRAY['PLANNING'::"text", 'ACTIVE'::"text", 'PAUSED'::"text", 'RETIRED'::"text"]))),
    CONSTRAINT "ck_portfolio_site_version" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "site"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON TABLE "portfolio"."site" IS 'RAOSが運営するMedia SiteのRoot。MVPは1件だがCategory、Article、Analytics、Financeのscope基準となる。';

--
-- Name: COLUMN "site"."id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."site"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "site"."display_id"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."site"."display_id" IS 'SITE-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "site"."site_code"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."site"."site_code" IS 'site code';

--
-- Name: COLUMN "site"."name"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."site"."name" IS 'name';

--
-- Name: COLUMN "site"."primary_domain"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."site"."primary_domain" IS 'primary domain';

--
-- Name: COLUMN "site"."brand_name"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."site"."brand_name" IS 'brand name';

--
-- Name: COLUMN "site"."locale"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."site"."locale" IS 'locale';

--
-- Name: COLUMN "site"."timezone"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."site"."timezone" IS 'timezone';

--
-- Name: COLUMN "site"."currency"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."site"."currency" IS 'currency';

--
-- Name: COLUMN "site"."status"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."site"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "site"."public_settings"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."site"."public_settings" IS '公開表示に安全なSite設定。秘密や内部KPIを含めない。';

--
-- Name: COLUMN "site"."created_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."site"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "site"."updated_at"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."site"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "site"."lock_version"; Type: COMMENT; Schema: portfolio; Owner: -
--

COMMENT ON COLUMN "portfolio"."site"."lock_version" IS '楽観的排他制御用の単調増加Version。';

--
-- Name: evaluation_case evaluation_case_pkey; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_case"
    ADD CONSTRAINT "evaluation_case_pkey" PRIMARY KEY ("id");

--
-- Name: evaluation_case_result evaluation_case_result_pkey; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_case_result"
    ADD CONSTRAINT "evaluation_case_result_pkey" PRIMARY KEY ("id");

--
-- Name: evaluation_dataset_version evaluation_dataset_version_display_id_key; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_dataset_version"
    ADD CONSTRAINT "evaluation_dataset_version_display_id_key" UNIQUE ("display_id");

--
-- Name: evaluation_dataset_version evaluation_dataset_version_pkey; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_dataset_version"
    ADD CONSTRAINT "evaluation_dataset_version_pkey" PRIMARY KEY ("id");

--
-- Name: evaluation_run evaluation_run_display_id_key; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_run"
    ADD CONSTRAINT "evaluation_run_display_id_key" UNIQUE ("display_id");

--
-- Name: evaluation_run evaluation_run_pkey; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_run"
    ADD CONSTRAINT "evaluation_run_pkey" PRIMARY KEY ("id");

--
-- Name: evaluation_suite evaluation_suite_pkey; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_suite"
    ADD CONSTRAINT "evaluation_suite_pkey" PRIMARY KEY ("id");

--
-- Name: human_evaluation human_evaluation_pkey; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."human_evaluation"
    ADD CONSTRAINT "human_evaluation_pkey" PRIMARY KEY ("id");

--
-- Name: judge_calibration judge_calibration_display_id_key; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."judge_calibration"
    ADD CONSTRAINT "judge_calibration_display_id_key" UNIQUE ("display_id");

--
-- Name: judge_calibration judge_calibration_pkey; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."judge_calibration"
    ADD CONSTRAINT "judge_calibration_pkey" PRIMARY KEY ("id");

--
-- Name: ai_attempt pk_ai_ai_attempt; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_attempt"
    ADD CONSTRAINT "pk_ai_ai_attempt" PRIMARY KEY ("id");

--
-- Name: ai_job pk_ai_ai_job; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_job"
    ADD CONSTRAINT "pk_ai_ai_job" PRIMARY KEY ("id");

--
-- Name: evaluation_result pk_ai_evaluation_result; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_result"
    ADD CONSTRAINT "pk_ai_evaluation_result" PRIMARY KEY ("id");

--
-- Name: model_definition pk_ai_model_definition; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."model_definition"
    ADD CONSTRAINT "pk_ai_model_definition" PRIMARY KEY ("id");

--
-- Name: model_route_version pk_ai_model_route_version; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."model_route_version"
    ADD CONSTRAINT "pk_ai_model_route_version" PRIMARY KEY ("id");

--
-- Name: output_schema_version pk_ai_output_schema_version; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."output_schema_version"
    ADD CONSTRAINT "pk_ai_output_schema_version" PRIMARY KEY ("id");

--
-- Name: prompt_version pk_ai_prompt_version; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."prompt_version"
    ADD CONSTRAINT "pk_ai_prompt_version" PRIMARY KEY ("id");

--
-- Name: task_definition pk_ai_task_definition; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."task_definition"
    ADD CONSTRAINT "pk_ai_task_definition" PRIMARY KEY ("id");

--
-- Name: usage_cost pk_ai_usage_cost; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."usage_cost"
    ADD CONSTRAINT "pk_ai_usage_cost" PRIMARY KEY ("id");

--
-- Name: release_approval release_approval_display_id_key; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_approval"
    ADD CONSTRAINT "release_approval_display_id_key" UNIQUE ("display_id");

--
-- Name: release_approval release_approval_pkey; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_approval"
    ADD CONSTRAINT "release_approval_pkey" PRIMARY KEY ("id");

--
-- Name: release_decision release_decision_display_id_key; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "release_decision_display_id_key" UNIQUE ("display_id");

--
-- Name: release_decision release_decision_pkey; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "release_decision_pkey" PRIMARY KEY ("id");

--
-- Name: ai_attempt uq_ai_attempt_no; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_attempt"
    ADD CONSTRAINT "uq_ai_attempt_no" UNIQUE ("ai_job_id", "attempt_no");

--
-- Name: evaluation_case uq_ai_eval_case; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_case"
    ADD CONSTRAINT "uq_ai_eval_case" UNIQUE ("dataset_version_id", "case_key");

--
-- Name: evaluation_case uq_ai_eval_case_input; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_case"
    ADD CONSTRAINT "uq_ai_eval_case_input" UNIQUE ("dataset_version_id", "input_artifact_id");

--
-- Name: evaluation_result uq_ai_eval_case_metric; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_result"
    ADD CONSTRAINT "uq_ai_eval_case_metric" UNIQUE ("run_id", "case_key", "metric_code");

--
-- Name: evaluation_case_result uq_ai_eval_case_result; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_case_result"
    ADD CONSTRAINT "uq_ai_eval_case_result" UNIQUE ("evaluation_run_id", "evaluation_case_id");

--
-- Name: evaluation_case_result uq_ai_eval_case_result_attempt; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_case_result"
    ADD CONSTRAINT "uq_ai_eval_case_result_attempt" UNIQUE ("ai_attempt_id");

--
-- Name: evaluation_case_result uq_ai_eval_case_result_output; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_case_result"
    ADD CONSTRAINT "uq_ai_eval_case_result_output" UNIQUE ("output_artifact_id");

--
-- Name: evaluation_dataset_version uq_ai_eval_dataset; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_dataset_version"
    ADD CONSTRAINT "uq_ai_eval_dataset" UNIQUE ("dataset_code", "version_no");

--
-- Name: evaluation_suite uq_ai_eval_suite; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_suite"
    ADD CONSTRAINT "uq_ai_eval_suite" UNIQUE ("suite_code", "version_no");

--
-- Name: human_evaluation uq_ai_human_eval; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."human_evaluation"
    ADD CONSTRAINT "uq_ai_human_eval" UNIQUE ("evaluation_case_result_id", "reviewer_principal_id", "is_adjudication");

--
-- Name: ai_job uq_ai_job_display; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_job"
    ADD CONSTRAINT "uq_ai_job_display" UNIQUE ("display_id");

--
-- Name: ai_job uq_ai_job_ops; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_job"
    ADD CONSTRAINT "uq_ai_job_ops" UNIQUE ("ops_job_id");

--
-- Name: model_definition uq_ai_model_provider_id; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."model_definition"
    ADD CONSTRAINT "uq_ai_model_provider_id" UNIQUE ("provider_code", "provider_model_id");

--
-- Name: output_schema_version uq_ai_output_schema_version; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."output_schema_version"
    ADD CONSTRAINT "uq_ai_output_schema_version" UNIQUE ("schema_code", "version_no");

--
-- Name: prompt_version uq_ai_prompt_display; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."prompt_version"
    ADD CONSTRAINT "uq_ai_prompt_display" UNIQUE ("display_id");

--
-- Name: prompt_version uq_ai_prompt_version; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."prompt_version"
    ADD CONSTRAINT "uq_ai_prompt_version" UNIQUE ("prompt_code", "version_no");

--
-- Name: release_approval uq_ai_release_approval_phase; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_approval"
    ADD CONSTRAINT "uq_ai_release_approval_phase" UNIQUE ("release_decision_id", "phase");

--
-- Name: model_route_version uq_ai_route_version; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."model_route_version"
    ADD CONSTRAINT "uq_ai_route_version" UNIQUE ("route_code", "version_no");

--
-- Name: task_definition uq_ai_task_code; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."task_definition"
    ADD CONSTRAINT "uq_ai_task_code" UNIQUE ("task_code");

--
-- Name: usage_cost uq_ai_usage_attempt; Type: CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."usage_cost"
    ADD CONSTRAINT "uq_ai_usage_attempt" UNIQUE ("ai_attempt_id");

--
-- Name: affiliate_link_observation pk_catalog_affiliate_link_observation; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."affiliate_link_observation"
    ADD CONSTRAINT "pk_catalog_affiliate_link_observation" PRIMARY KEY ("id");

--
-- Name: attribute_definition pk_catalog_attribute_definition; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."attribute_definition"
    ADD CONSTRAINT "pk_catalog_attribute_definition" PRIMARY KEY ("id");

--
-- Name: availability_observation pk_catalog_availability_observation; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."availability_observation"
    ADD CONSTRAINT "pk_catalog_availability_observation" PRIMARY KEY ("id");

--
-- Name: canonical_product pk_catalog_canonical_product; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."canonical_product"
    ADD CONSTRAINT "pk_catalog_canonical_product" PRIMARY KEY ("id");

--
-- Name: category_genre_mapping pk_catalog_category_genre_mapping; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."category_genre_mapping"
    ADD CONSTRAINT "pk_catalog_category_genre_mapping" PRIMARY KEY ("id");

--
-- Name: grouping_decision pk_catalog_grouping_decision; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."grouping_decision"
    ADD CONSTRAINT "pk_catalog_grouping_decision" PRIMARY KEY ("id");

--
-- Name: ingestion_request pk_catalog_ingestion_request; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."ingestion_request"
    ADD CONSTRAINT "pk_catalog_ingestion_request" PRIMARY KEY ("id");

--
-- Name: offer pk_catalog_offer; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."offer"
    ADD CONSTRAINT "pk_catalog_offer" PRIMARY KEY ("id");

--
-- Name: offer_current_projection pk_catalog_offer_current_projection; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."offer_current_projection"
    ADD CONSTRAINT "pk_catalog_offer_current_projection" PRIMARY KEY ("offer_id");

--
-- Name: price_observation pk_catalog_price_observation; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."price_observation"
    ADD CONSTRAINT "pk_catalog_price_observation" PRIMARY KEY ("id");

--
-- Name: product_attribute_value pk_catalog_product_attribute_value; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_attribute_value"
    ADD CONSTRAINT "pk_catalog_product_attribute_value" PRIMARY KEY ("id");

--
-- Name: product_candidate pk_catalog_product_candidate; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_candidate"
    ADD CONSTRAINT "pk_catalog_product_candidate" PRIMARY KEY ("id");

--
-- Name: product_group_membership pk_catalog_product_group_membership; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_group_membership"
    ADD CONSTRAINT "pk_catalog_product_group_membership" PRIMARY KEY ("id");

--
-- Name: product_relation pk_catalog_product_relation; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_relation"
    ADD CONSTRAINT "pk_catalog_product_relation" PRIMARY KEY ("id");

--
-- Name: provider_endpoint pk_catalog_provider_endpoint; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."provider_endpoint"
    ADD CONSTRAINT "pk_catalog_provider_endpoint" PRIMARY KEY ("id");

--
-- Name: rakuten_genre pk_catalog_rakuten_genre; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."rakuten_genre"
    ADD CONSTRAINT "pk_catalog_rakuten_genre" PRIMARY KEY ("id");

--
-- Name: review_aggregate_observation pk_catalog_review_aggregate_observation; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."review_aggregate_observation"
    ADD CONSTRAINT "pk_catalog_review_aggregate_observation" PRIMARY KEY ("id");

--
-- Name: shop pk_catalog_shop; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."shop"
    ADD CONSTRAINT "pk_catalog_shop" PRIMARY KEY ("id");

--
-- Name: product_candidate uq_catalog_candidate_display; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_candidate"
    ADD CONSTRAINT "uq_catalog_candidate_display" UNIQUE ("display_id");

--
-- Name: product_candidate uq_catalog_candidate_external; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_candidate"
    ADD CONSTRAINT "uq_catalog_candidate_external" UNIQUE ("provider_endpoint_id", "external_item_code");

--
-- Name: ingestion_request uq_catalog_ingestion_display; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."ingestion_request"
    ADD CONSTRAINT "uq_catalog_ingestion_display" UNIQUE ("display_id");

--
-- Name: ingestion_request uq_catalog_ingestion_job; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."ingestion_request"
    ADD CONSTRAINT "uq_catalog_ingestion_job" UNIQUE ("job_id");

--
-- Name: offer uq_catalog_offer_display; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."offer"
    ADD CONSTRAINT "uq_catalog_offer_display" UNIQUE ("display_id");

--
-- Name: offer uq_catalog_offer_external; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."offer"
    ADD CONSTRAINT "uq_catalog_offer_external" UNIQUE ("provider_endpoint_id", "external_offer_id");

--
-- Name: canonical_product uq_catalog_product_display; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."canonical_product"
    ADD CONSTRAINT "uq_catalog_product_display" UNIQUE ("display_id");

--
-- Name: provider_endpoint uq_catalog_provider_api_version; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."provider_endpoint"
    ADD CONSTRAINT "uq_catalog_provider_api_version" UNIQUE ("provider_code", "api_name", "api_version");

--
-- Name: rakuten_genre uq_catalog_rakuten_genre; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."rakuten_genre"
    ADD CONSTRAINT "uq_catalog_rakuten_genre" UNIQUE ("provider_endpoint_id", "external_genre_id");

--
-- Name: shop uq_catalog_shop_display; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."shop"
    ADD CONSTRAINT "uq_catalog_shop_display" UNIQUE ("display_id");

--
-- Name: shop uq_catalog_shop_external; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."shop"
    ADD CONSTRAINT "uq_catalog_shop_external" UNIQUE ("provider_endpoint_id", "external_shop_code");

--
-- Name: article pk_editorial_article; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article"
    ADD CONSTRAINT "pk_editorial_article" PRIMARY KEY ("id");

--
-- Name: article_block pk_editorial_article_block; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_block"
    ADD CONSTRAINT "pk_editorial_article_block" PRIMARY KEY ("id");

--
-- Name: article_block_product pk_editorial_article_block_product; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_block_product"
    ADD CONSTRAINT "pk_editorial_article_block_product" PRIMARY KEY ("article_block_id", "product_id", "placement_role");

--
-- Name: article_disclosure_context pk_editorial_article_disclosure_context; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_disclosure_context"
    ADD CONSTRAINT "pk_editorial_article_disclosure_context" PRIMARY KEY ("article_version_id");

--
-- Name: article_link pk_editorial_article_link; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_link"
    ADD CONSTRAINT "pk_editorial_article_link" PRIMARY KEY ("id");

--
-- Name: article_methodology_binding pk_editorial_article_methodology_binding; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_methodology_binding"
    ADD CONSTRAINT "pk_editorial_article_methodology_binding" PRIMARY KEY ("article_version_id");

--
-- Name: article_plan pk_editorial_article_plan; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_plan"
    ADD CONSTRAINT "pk_editorial_article_plan" PRIMARY KEY ("id");

--
-- Name: article_slug pk_editorial_article_slug; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_slug"
    ADD CONSTRAINT "pk_editorial_article_slug" PRIMARY KEY ("id");

--
-- Name: article_template_version pk_editorial_article_template_version; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_template_version"
    ADD CONSTRAINT "pk_editorial_article_template_version" PRIMARY KEY ("id");

--
-- Name: article_type_version pk_editorial_article_type_version; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_type_version"
    ADD CONSTRAINT "pk_editorial_article_type_version" PRIMARY KEY ("id");

--
-- Name: article_version pk_editorial_article_version; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_version"
    ADD CONSTRAINT "pk_editorial_article_version" PRIMARY KEY ("id");

--
-- Name: comparison_axis pk_editorial_comparison_axis; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."comparison_axis"
    ADD CONSTRAINT "pk_editorial_comparison_axis" PRIMARY KEY ("id");

--
-- Name: comparison_value pk_editorial_comparison_value; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."comparison_value"
    ADD CONSTRAINT "pk_editorial_comparison_value" PRIMARY KEY ("id");

--
-- Name: content_schema_version pk_editorial_content_schema_version; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."content_schema_version"
    ADD CONSTRAINT "pk_editorial_content_schema_version" PRIMARY KEY ("id");

--
-- Name: media_asset pk_editorial_media_asset; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."media_asset"
    ADD CONSTRAINT "pk_editorial_media_asset" PRIMARY KEY ("id");

--
-- Name: editorial_methodology_version pk_editorial_methodology_version; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."editorial_methodology_version"
    ADD CONSTRAINT "pk_editorial_methodology_version" PRIMARY KEY ("id");

--
-- Name: recommendation pk_editorial_recommendation; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."recommendation"
    ADD CONSTRAINT "pk_editorial_recommendation" PRIMARY KEY ("id");

--
-- Name: recommendation_rationale pk_editorial_recommendation_rationale; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."recommendation_rationale"
    ADD CONSTRAINT "pk_editorial_recommendation_rationale" PRIMARY KEY ("id");

--
-- Name: recommendation_set pk_editorial_recommendation_set; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."recommendation_set"
    ADD CONSTRAINT "pk_editorial_recommendation_set" PRIMARY KEY ("id");

--
-- Name: review_comment pk_editorial_review_comment; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."review_comment"
    ADD CONSTRAINT "pk_editorial_review_comment" PRIMARY KEY ("id");

--
-- Name: seo_metadata_version pk_editorial_seo_metadata_version; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."seo_metadata_version"
    ADD CONSTRAINT "pk_editorial_seo_metadata_version" PRIMARY KEY ("id");

--
-- Name: structured_data_manifest pk_editorial_structured_data_manifest; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."structured_data_manifest"
    ADD CONSTRAINT "pk_editorial_structured_data_manifest" PRIMARY KEY ("id");

--
-- Name: article uq_editorial_article_display; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article"
    ADD CONSTRAINT "uq_editorial_article_display" UNIQUE ("display_id");

--
-- Name: article_link uq_editorial_article_link; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_link"
    ADD CONSTRAINT "uq_editorial_article_link" UNIQUE ("from_article_id", "to_article_id", "link_type");

--
-- Name: article uq_editorial_article_plan; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article"
    ADD CONSTRAINT "uq_editorial_article_plan" UNIQUE ("article_plan_id");

--
-- Name: article_template_version uq_editorial_article_template_type_version; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_template_version"
    ADD CONSTRAINT "uq_editorial_article_template_type_version" UNIQUE ("article_type_version_id", "semantic_version");

--
-- Name: article_type_version uq_editorial_article_type_code_version; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_type_version"
    ADD CONSTRAINT "uq_editorial_article_type_code_version" UNIQUE ("article_type_code", "semantic_version");

--
-- Name: article_type_version uq_editorial_article_type_id_code; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_type_version"
    ADD CONSTRAINT "uq_editorial_article_type_id_code" UNIQUE ("id", "article_type_code");

--
-- Name: article_version uq_editorial_article_version_display; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_version"
    ADD CONSTRAINT "uq_editorial_article_version_display" UNIQUE ("display_id");

--
-- Name: article_version uq_editorial_article_version_no; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_version"
    ADD CONSTRAINT "uq_editorial_article_version_no" UNIQUE ("article_id", "version_no");

--
-- Name: comparison_axis uq_editorial_axis_code; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."comparison_axis"
    ADD CONSTRAINT "uq_editorial_axis_code" UNIQUE ("article_version_id", "axis_code");

--
-- Name: comparison_axis uq_editorial_axis_position; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."comparison_axis"
    ADD CONSTRAINT "uq_editorial_axis_position" UNIQUE ("article_version_id", "position");

--
-- Name: article_block uq_editorial_block_id_version; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_block"
    ADD CONSTRAINT "uq_editorial_block_id_version" UNIQUE ("id", "article_version_id");

--
-- Name: article_block uq_editorial_block_key; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_block"
    ADD CONSTRAINT "uq_editorial_block_key" UNIQUE ("article_version_id", "block_key");

--
-- Name: article_block_product uq_editorial_block_placement; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_block_product"
    ADD CONSTRAINT "uq_editorial_block_placement" UNIQUE ("placement_id");

--
-- Name: article_block uq_editorial_block_position; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_block"
    ADD CONSTRAINT "uq_editorial_block_position" UNIQUE ("article_version_id", "position");

--
-- Name: comparison_value uq_editorial_comparison_value; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."comparison_value"
    ADD CONSTRAINT "uq_editorial_comparison_value" UNIQUE ("comparison_axis_id", "product_id");

--
-- Name: content_schema_version uq_editorial_content_schema_code_version; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."content_schema_version"
    ADD CONSTRAINT "uq_editorial_content_schema_code_version" UNIQUE ("schema_code", "semantic_version");

--
-- Name: media_asset uq_editorial_media_asset_display; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."media_asset"
    ADD CONSTRAINT "uq_editorial_media_asset_display" UNIQUE ("display_id");

--
-- Name: editorial_methodology_version uq_editorial_methodology_code_version; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."editorial_methodology_version"
    ADD CONSTRAINT "uq_editorial_methodology_code_version" UNIQUE ("methodology_code", "semantic_version");

--
-- Name: article_plan uq_editorial_plan_display; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_plan"
    ADD CONSTRAINT "uq_editorial_plan_display" UNIQUE ("display_id");

--
-- Name: recommendation uq_editorial_rec_product; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."recommendation"
    ADD CONSTRAINT "uq_editorial_rec_product" UNIQUE ("recommendation_set_id", "product_id");

--
-- Name: recommendation uq_editorial_rec_rank; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."recommendation"
    ADD CONSTRAINT "uq_editorial_rec_rank" UNIQUE ("recommendation_set_id", "rank_position");

--
-- Name: recommendation_set uq_editorial_rec_set_code; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."recommendation_set"
    ADD CONSTRAINT "uq_editorial_rec_set_code" UNIQUE ("article_version_id", "set_code");

--
-- Name: recommendation_set uq_editorial_rec_set_position; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."recommendation_set"
    ADD CONSTRAINT "uq_editorial_rec_set_position" UNIQUE ("article_version_id", "position");

--
-- Name: seo_metadata_version uq_editorial_seo_article_version; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."seo_metadata_version"
    ADD CONSTRAINT "uq_editorial_seo_article_version" UNIQUE ("article_version_id", "semantic_version");

--
-- Name: seo_metadata_version uq_editorial_seo_id_article; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."seo_metadata_version"
    ADD CONSTRAINT "uq_editorial_seo_id_article" UNIQUE ("id", "article_version_id");

--
-- Name: structured_data_manifest uq_editorial_structured_data_render; Type: CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."structured_data_manifest"
    ADD CONSTRAINT "uq_editorial_structured_data_render" UNIQUE ("article_version_id", "generator_version", "visible_content_sha256");

--
-- Name: claim pk_evidence_claim; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."claim"
    ADD CONSTRAINT "pk_evidence_claim" PRIMARY KEY ("id");

--
-- Name: claim_evidence_link pk_evidence_claim_evidence_link; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."claim_evidence_link"
    ADD CONSTRAINT "pk_evidence_claim_evidence_link" PRIMARY KEY ("claim_id", "fact_id", "support_type");

--
-- Name: fact pk_evidence_fact; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."fact"
    ADD CONSTRAINT "pk_evidence_fact" PRIMARY KEY ("id");

--
-- Name: fact_derivation pk_evidence_fact_derivation; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."fact_derivation"
    ADD CONSTRAINT "pk_evidence_fact_derivation" PRIMARY KEY ("derived_fact_id", "input_fact_id", "derivation_role");

--
-- Name: first_hand_experience_record pk_evidence_first_hand_experience; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."first_hand_experience_record"
    ADD CONSTRAINT "pk_evidence_first_hand_experience" PRIMARY KEY ("id");

--
-- Name: first_hand_experience_asset pk_evidence_first_hand_experience_asset; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."first_hand_experience_asset"
    ADD CONSTRAINT "pk_evidence_first_hand_experience_asset" PRIMARY KEY ("experience_record_id", "artifact_id", "role");

--
-- Name: source pk_evidence_source; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source"
    ADD CONSTRAINT "pk_evidence_source" PRIMARY KEY ("id");

--
-- Name: source_packet pk_evidence_source_packet; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet"
    ADD CONSTRAINT "pk_evidence_source_packet" PRIMARY KEY ("id");

--
-- Name: source_packet_fact pk_evidence_source_packet_fact; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet_fact"
    ADD CONSTRAINT "pk_evidence_source_packet_fact" PRIMARY KEY ("source_packet_version_id", "fact_id");

--
-- Name: source_packet_product pk_evidence_source_packet_product; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet_product"
    ADD CONSTRAINT "pk_evidence_source_packet_product" PRIMARY KEY ("source_packet_version_id", "product_id", "product_role");

--
-- Name: source_packet_version pk_evidence_source_packet_version; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet_version"
    ADD CONSTRAINT "pk_evidence_source_packet_version" PRIMARY KEY ("id");

--
-- Name: source_snapshot pk_evidence_source_snapshot; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_snapshot"
    ADD CONSTRAINT "pk_evidence_source_snapshot" PRIMARY KEY ("id");

--
-- Name: claim uq_evidence_claim_display; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."claim"
    ADD CONSTRAINT "uq_evidence_claim_display" UNIQUE ("display_id");

--
-- Name: claim uq_evidence_claim_key; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."claim"
    ADD CONSTRAINT "uq_evidence_claim_key" UNIQUE ("article_version_id", "claim_key");

--
-- Name: fact uq_evidence_fact_display; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."fact"
    ADD CONSTRAINT "uq_evidence_fact_display" UNIQUE ("display_id");

--
-- Name: first_hand_experience_record uq_evidence_first_hand_experience_display; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."first_hand_experience_record"
    ADD CONSTRAINT "uq_evidence_first_hand_experience_display" UNIQUE ("display_id");

--
-- Name: source_packet uq_evidence_packet_display; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet"
    ADD CONSTRAINT "uq_evidence_packet_display" UNIQUE ("display_id");

--
-- Name: source_packet uq_evidence_packet_plan_type; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet"
    ADD CONSTRAINT "uq_evidence_packet_plan_type" UNIQUE ("article_plan_id", "packet_type");

--
-- Name: source_packet_version uq_evidence_packet_version_artifact; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet_version"
    ADD CONSTRAINT "uq_evidence_packet_version_artifact" UNIQUE ("artifact_id");

--
-- Name: source_packet_version uq_evidence_packet_version_display; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet_version"
    ADD CONSTRAINT "uq_evidence_packet_version_display" UNIQUE ("display_id");

--
-- Name: source_packet_version uq_evidence_packet_version_no; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet_version"
    ADD CONSTRAINT "uq_evidence_packet_version_no" UNIQUE ("source_packet_id", "version_no");

--
-- Name: source_snapshot uq_evidence_snapshot_artifact; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_snapshot"
    ADD CONSTRAINT "uq_evidence_snapshot_artifact" UNIQUE ("artifact_id");

--
-- Name: source_snapshot uq_evidence_snapshot_display; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_snapshot"
    ADD CONSTRAINT "uq_evidence_snapshot_display" UNIQUE ("display_id");

--
-- Name: source uq_evidence_source_display; Type: CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source"
    ADD CONSTRAINT "uq_evidence_source_display" UNIQUE ("display_id");

--
-- Name: bundle_rule pk_policy_bundle_rule; Type: CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."bundle_rule"
    ADD CONSTRAINT "pk_policy_bundle_rule" PRIMARY KEY ("policy_bundle_id", "rule_version_id");

--
-- Name: finding pk_policy_finding; Type: CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."finding"
    ADD CONSTRAINT "pk_policy_finding" PRIMARY KEY ("id");

--
-- Name: gate_decision pk_policy_gate_decision; Type: CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."gate_decision"
    ADD CONSTRAINT "pk_policy_gate_decision" PRIMARY KEY ("id");

--
-- Name: policy_bundle pk_policy_policy_bundle; Type: CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."policy_bundle"
    ADD CONSTRAINT "pk_policy_policy_bundle" PRIMARY KEY ("id");

--
-- Name: quality_check_run pk_policy_quality_check_run; Type: CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."quality_check_run"
    ADD CONSTRAINT "pk_policy_quality_check_run" PRIMARY KEY ("id");

--
-- Name: quality_score pk_policy_quality_score; Type: CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."quality_score"
    ADD CONSTRAINT "pk_policy_quality_score" PRIMARY KEY ("id");

--
-- Name: rule_version pk_policy_rule_version; Type: CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."rule_version"
    ADD CONSTRAINT "pk_policy_rule_version" PRIMARY KEY ("id");

--
-- Name: waiver pk_policy_waiver; Type: CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."waiver"
    ADD CONSTRAINT "pk_policy_waiver" PRIMARY KEY ("id");

--
-- Name: policy_bundle uq_policy_bundle_display; Type: CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."policy_bundle"
    ADD CONSTRAINT "uq_policy_bundle_display" UNIQUE ("display_id");

--
-- Name: bundle_rule uq_policy_bundle_rule_order; Type: CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."bundle_rule"
    ADD CONSTRAINT "uq_policy_bundle_rule_order" UNIQUE ("policy_bundle_id", "execution_order");

--
-- Name: policy_bundle uq_policy_bundle_version; Type: CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."policy_bundle"
    ADD CONSTRAINT "uq_policy_bundle_version" UNIQUE ("bundle_code", "version_no");

--
-- Name: quality_check_run uq_policy_check_display; Type: CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."quality_check_run"
    ADD CONSTRAINT "uq_policy_check_display" UNIQUE ("display_id");

--
-- Name: gate_decision uq_policy_gate_display; Type: CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."gate_decision"
    ADD CONSTRAINT "uq_policy_gate_display" UNIQUE ("display_id");

--
-- Name: quality_score uq_policy_quality_score_run; Type: CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."quality_score"
    ADD CONSTRAINT "uq_policy_quality_score_run" UNIQUE ("quality_check_run_id");

--
-- Name: rule_version uq_policy_rule_version; Type: CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."rule_version"
    ADD CONSTRAINT "uq_policy_rule_version" UNIQUE ("rule_code", "version_no");

--
-- Name: waiver uq_policy_waiver_display; Type: CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."waiver"
    ADD CONSTRAINT "uq_policy_waiver_display" UNIQUE ("display_id");

--
-- Name: action_candidate pk_portfolio_action_candidate; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."action_candidate"
    ADD CONSTRAINT "pk_portfolio_action_candidate" PRIMARY KEY ("id");

--
-- Name: category pk_portfolio_category; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."category"
    ADD CONSTRAINT "pk_portfolio_category" PRIMARY KEY ("id");

--
-- Name: intent_cluster pk_portfolio_intent_cluster; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."intent_cluster"
    ADD CONSTRAINT "pk_portfolio_intent_cluster" PRIMARY KEY ("id");

--
-- Name: intent_cluster_keyword pk_portfolio_intent_cluster_keyword; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."intent_cluster_keyword"
    ADD CONSTRAINT "pk_portfolio_intent_cluster_keyword" PRIMARY KEY ("intent_cluster_id", "keyword_id");

--
-- Name: keyword pk_portfolio_keyword; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."keyword"
    ADD CONSTRAINT "pk_portfolio_keyword" PRIMARY KEY ("id");

--
-- Name: keyword_metric_observation pk_portfolio_keyword_metric_observation; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."keyword_metric_observation"
    ADD CONSTRAINT "pk_portfolio_keyword_metric_observation" PRIMARY KEY ("id");

--
-- Name: opportunity_assessment pk_portfolio_opportunity_assessment; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."opportunity_assessment"
    ADD CONSTRAINT "pk_portfolio_opportunity_assessment" PRIMARY KEY ("id");

--
-- Name: site pk_portfolio_site; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."site"
    ADD CONSTRAINT "pk_portfolio_site" PRIMARY KEY ("id");

--
-- Name: action_candidate uq_portfolio_action_display; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."action_candidate"
    ADD CONSTRAINT "uq_portfolio_action_display" UNIQUE ("display_id");

--
-- Name: category uq_portfolio_category_code; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."category"
    ADD CONSTRAINT "uq_portfolio_category_code" UNIQUE ("site_id", "category_code");

--
-- Name: category uq_portfolio_category_display; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."category"
    ADD CONSTRAINT "uq_portfolio_category_display" UNIQUE ("display_id");

--
-- Name: intent_cluster uq_portfolio_intent_code; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."intent_cluster"
    ADD CONSTRAINT "uq_portfolio_intent_code" UNIQUE ("category_id", "cluster_code");

--
-- Name: intent_cluster uq_portfolio_intent_display; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."intent_cluster"
    ADD CONSTRAINT "uq_portfolio_intent_display" UNIQUE ("display_id");

--
-- Name: keyword uq_portfolio_keyword_display; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."keyword"
    ADD CONSTRAINT "uq_portfolio_keyword_display" UNIQUE ("display_id");

--
-- Name: keyword uq_portfolio_keyword_normalized; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."keyword"
    ADD CONSTRAINT "uq_portfolio_keyword_normalized" UNIQUE ("site_id", "locale", "normalized_text");

--
-- Name: opportunity_assessment uq_portfolio_opp_display; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."opportunity_assessment"
    ADD CONSTRAINT "uq_portfolio_opp_display" UNIQUE ("display_id");

--
-- Name: site uq_portfolio_site_code; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."site"
    ADD CONSTRAINT "uq_portfolio_site_code" UNIQUE ("site_code");

--
-- Name: site uq_portfolio_site_display; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."site"
    ADD CONSTRAINT "uq_portfolio_site_display" UNIQUE ("display_id");

--
-- Name: site uq_portfolio_site_domain; Type: CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."site"
    ADD CONSTRAINT "uq_portfolio_site_domain" UNIQUE ("primary_domain");

--
-- Name: ix_ai_ai_attempt_input_artifact_id; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_ai_attempt_input_artifact_id" ON "ai"."ai_attempt" USING "btree" ("input_artifact_id");

--
-- Name: ix_ai_ai_attempt_output_artifact_id; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_ai_attempt_output_artifact_id" ON "ai"."ai_attempt" USING "btree" ("output_artifact_id");

--
-- Name: ix_ai_ai_job_article_version_id; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_ai_job_article_version_id" ON "ai"."ai_job" USING "btree" ("article_version_id");

--
-- Name: ix_ai_ai_job_model_route_version_id; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_ai_job_model_route_version_id" ON "ai"."ai_job" USING "btree" ("model_route_version_id");

--
-- Name: ix_ai_ai_job_output_schema_version_id; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_ai_job_output_schema_version_id" ON "ai"."ai_job" USING "btree" ("output_schema_version_id");

--
-- Name: ix_ai_ai_job_prompt_version_id; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_ai_job_prompt_version_id" ON "ai"."ai_job" USING "btree" ("prompt_version_id");

--
-- Name: ix_ai_ai_job_source_packet_version_id; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_ai_job_source_packet_version_id" ON "ai"."ai_job" USING "btree" ("source_packet_version_id");

--
-- Name: ix_ai_ai_job_task_definition_id; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_ai_job_task_definition_id" ON "ai"."ai_job" USING "btree" ("task_definition_id");

--
-- Name: ix_ai_attempt_model_time; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_attempt_model_time" ON "ai"."ai_attempt" USING "btree" ("model_id", "started_at");

--
-- Name: ix_ai_attempt_status; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_attempt_status" ON "ai"."ai_attempt" USING "btree" ("status", "started_at");

--
-- Name: ix_ai_eval_case_gold; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_case_gold" ON "ai"."evaluation_case" USING "btree" ("gold_artifact_id");

--
-- Name: ix_ai_eval_case_input; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_case_input" ON "ai"."evaluation_case" USING "btree" ("input_artifact_id");

--
-- Name: ix_ai_eval_case_result_attempt; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_case_result_attempt" ON "ai"."evaluation_case_result" USING "btree" ("ai_attempt_id");

--
-- Name: ix_ai_eval_case_result_case; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_case_result_case" ON "ai"."evaluation_case_result" USING "btree" ("evaluation_case_id");

--
-- Name: ix_ai_eval_case_result_output; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_case_result_output" ON "ai"."evaluation_case_result" USING "btree" ("output_artifact_id");

--
-- Name: ix_ai_eval_case_result_run_status; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_case_result_run_status" ON "ai"."evaluation_case_result" USING "btree" ("evaluation_run_id", "status");

--
-- Name: ix_ai_eval_case_result_zero_tolerance_artifact; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_case_result_zero_tolerance_artifact" ON "ai"."evaluation_case_result" USING "btree" ("zero_tolerance_evidence_artifact_id");

--
-- Name: ix_ai_eval_case_task_split; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_case_task_split" ON "ai"."evaluation_case" USING "btree" ("task_definition_id", "split", "risk_level");

--
-- Name: ix_ai_eval_dataset_artifact; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_dataset_artifact" ON "ai"."evaluation_dataset_version" USING "btree" ("dataset_artifact_id");

--
-- Name: ix_ai_eval_dataset_locker; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_dataset_locker" ON "ai"."evaluation_dataset_version" USING "btree" ("locked_by_principal_id");

--
-- Name: ix_ai_eval_result_case_id; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_result_case_id" ON "ai"."evaluation_result" USING "btree" ("evaluation_case_id");

--
-- Name: ix_ai_eval_result_judge_cal; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_result_judge_cal" ON "ai"."evaluation_result" USING "btree" ("judge_calibration_id");

--
-- Name: ix_ai_eval_result_run_id; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_result_run_id" ON "ai"."evaluation_result" USING "btree" ("evaluation_run_id");

--
-- Name: ix_ai_eval_route; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_route" ON "ai"."evaluation_result" USING "btree" ("model_route_version_id", "created_at");

--
-- Name: ix_ai_eval_run; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_run" ON "ai"."evaluation_result" USING "btree" ("run_id", "case_key");

--
-- Name: ix_ai_eval_run_baseline; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_run_baseline" ON "ai"."evaluation_run" USING "btree" ("baseline_evaluation_run_id");

--
-- Name: ix_ai_eval_run_creator; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_run_creator" ON "ai"."evaluation_run" USING "btree" ("created_by_principal_id");

--
-- Name: ix_ai_eval_run_dataset; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_run_dataset" ON "ai"."evaluation_run" USING "btree" ("dataset_version_id");

--
-- Name: ix_ai_eval_run_manifest; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_run_manifest" ON "ai"."evaluation_run" USING "btree" ("run_manifest_artifact_id");

--
-- Name: ix_ai_eval_run_policy; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_run_policy" ON "ai"."evaluation_run" USING "btree" ("policy_bundle_version_id");

--
-- Name: ix_ai_eval_run_prompt; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_run_prompt" ON "ai"."evaluation_run" USING "btree" ("prompt_version_id");

--
-- Name: ix_ai_eval_run_resolved_model; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_run_resolved_model" ON "ai"."evaluation_run" USING "btree" ("resolved_model_id");

--
-- Name: ix_ai_eval_run_route; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_run_route" ON "ai"."evaluation_run" USING "btree" ("model_route_version_id");

--
-- Name: ix_ai_eval_run_schema; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_run_schema" ON "ai"."evaluation_run" USING "btree" ("output_schema_version_id");

--
-- Name: ix_ai_eval_run_suite_status; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_run_suite_status" ON "ai"."evaluation_run" USING "btree" ("suite_id", "status", "created_at" DESC);

--
-- Name: ix_ai_eval_suite_approver; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_suite_approver" ON "ai"."evaluation_suite" USING "btree" ("approved_by_principal_id");

--
-- Name: ix_ai_eval_suite_rubric; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_suite_rubric" ON "ai"."evaluation_suite" USING "btree" ("rubric_artifact_id");

--
-- Name: ix_ai_eval_suite_task; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_eval_suite_task" ON "ai"."evaluation_suite" USING "btree" ("task_definition_id");

--
-- Name: ix_ai_evaluation_result_prompt_version_id; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_evaluation_result_prompt_version_id" ON "ai"."evaluation_result" USING "btree" ("prompt_version_id");

--
-- Name: ix_ai_evaluation_result_result_artifact_id; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_evaluation_result_result_artifact_id" ON "ai"."evaluation_result" USING "btree" ("result_artifact_id");

--
-- Name: ix_ai_evaluation_result_task_definition_id; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_evaluation_result_task_definition_id" ON "ai"."evaluation_result" USING "btree" ("task_definition_id");

--
-- Name: ix_ai_human_eval_notes; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_human_eval_notes" ON "ai"."human_evaluation" USING "btree" ("notes_artifact_id");

--
-- Name: ix_ai_human_eval_result; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_human_eval_result" ON "ai"."human_evaluation" USING "btree" ("evaluation_case_result_id", "created_at");

--
-- Name: ix_ai_human_eval_reviewer; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_human_eval_reviewer" ON "ai"."human_evaluation" USING "btree" ("reviewer_principal_id");

--
-- Name: ix_ai_job_article; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_job_article" ON "ai"."ai_job" USING "btree" ("article_plan_id", "article_version_id");

--
-- Name: ix_ai_job_policy_bundle; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_job_policy_bundle" ON "ai"."ai_job" USING "btree" ("policy_bundle_version_id");

--
-- Name: ix_ai_job_release_decision; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_job_release_decision" ON "ai"."ai_job" USING "btree" ("release_decision_id");

--
-- Name: ix_ai_job_status; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_job_status" ON "ai"."ai_job" USING "btree" ("status", "created_at");

--
-- Name: ix_ai_judge_cal_approver; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_judge_cal_approver" ON "ai"."judge_calibration" USING "btree" ("approved_by_principal_id");

--
-- Name: ix_ai_judge_cal_dataset; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_judge_cal_dataset" ON "ai"."judge_calibration" USING "btree" ("dataset_version_id");

--
-- Name: ix_ai_judge_cal_model; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_judge_cal_model" ON "ai"."judge_calibration" USING "btree" ("resolved_judge_model_id");

--
-- Name: ix_ai_judge_cal_prompt; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_judge_cal_prompt" ON "ai"."judge_calibration" USING "btree" ("judge_prompt_version_id");

--
-- Name: ix_ai_judge_cal_report; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_judge_cal_report" ON "ai"."judge_calibration" USING "btree" ("report_artifact_id");

--
-- Name: ix_ai_judge_cal_route; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_judge_cal_route" ON "ai"."judge_calibration" USING "btree" ("judge_route_version_id");

--
-- Name: ix_ai_judge_cal_rubric; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_judge_cal_rubric" ON "ai"."judge_calibration" USING "btree" ("rubric_artifact_id");

--
-- Name: ix_ai_judge_cal_task; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_judge_cal_task" ON "ai"."judge_calibration" USING "btree" ("evaluated_task_definition_id");

--
-- Name: ix_ai_model_route_version_approved_by_principal_id; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_model_route_version_approved_by_principal_id" ON "ai"."model_route_version" USING "btree" ("approved_by_principal_id");

--
-- Name: ix_ai_model_route_version_fallback_model_id; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_model_route_version_fallback_model_id" ON "ai"."model_route_version" USING "btree" ("fallback_model_id");

--
-- Name: ix_ai_model_route_version_primary_model_id; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_model_route_version_primary_model_id" ON "ai"."model_route_version" USING "btree" ("primary_model_id");

--
-- Name: ix_ai_model_status; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_model_status" ON "ai"."model_definition" USING "btree" ("provider_code", "status");

--
-- Name: ix_ai_prompt_author; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_prompt_author" ON "ai"."prompt_version" USING "btree" ("author_principal_id");

--
-- Name: ix_ai_prompt_task; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_prompt_task" ON "ai"."prompt_version" USING "btree" ("task_definition_id", "status");

--
-- Name: ix_ai_prompt_version_approved_by_principal_id; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_prompt_version_approved_by_principal_id" ON "ai"."prompt_version" USING "btree" ("approved_by_principal_id");

--
-- Name: ix_ai_release_active_approval; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_active_approval" ON "ai"."release_decision" USING "btree" ("active_approval_id");

--
-- Name: ix_ai_release_approval_artifact; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_approval_artifact" ON "ai"."release_approval" USING "btree" ("approval_artifact_id");

--
-- Name: ix_ai_release_approval_primary; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_approval_primary" ON "ai"."release_approval" USING "btree" ("primary_approver_principal_id");

--
-- Name: ix_ai_release_approval_second; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_approval_second" ON "ai"."release_approval" USING "btree" ("second_approver_principal_id");

--
-- Name: ix_ai_release_approver; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_approver" ON "ai"."release_decision" USING "btree" ("approved_by_principal_id");

--
-- Name: ix_ai_release_canary_approval; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_canary_approval" ON "ai"."release_decision" USING "btree" ("canary_approval_id");

--
-- Name: ix_ai_release_dataset; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_dataset" ON "ai"."release_decision" USING "btree" ("dataset_version_id");

--
-- Name: ix_ai_release_evidence; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_evidence" ON "ai"."release_decision" USING "btree" ("canary_evidence_artifact_id");

--
-- Name: ix_ai_release_judge_cal; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_judge_cal" ON "ai"."release_decision" USING "btree" ("judge_calibration_id");

--
-- Name: ix_ai_release_model; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_model" ON "ai"."release_decision" USING "btree" ("resolved_model_id");

--
-- Name: ix_ai_release_monitor; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_monitor" ON "ai"."release_decision" USING "btree" ("canary_monitoring_artifact_id");

--
-- Name: ix_ai_release_policy; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_policy" ON "ai"."release_decision" USING "btree" ("policy_bundle_version_id");

--
-- Name: ix_ai_release_prompt; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_prompt" ON "ai"."release_decision" USING "btree" ("prompt_version_id");

--
-- Name: ix_ai_release_revoker; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_revoker" ON "ai"."release_decision" USING "btree" ("revoked_by_principal_id");

--
-- Name: ix_ai_release_rollback; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_rollback" ON "ai"."release_decision" USING "btree" ("rollback_release_decision_id");

--
-- Name: ix_ai_release_route; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_route" ON "ai"."release_decision" USING "btree" ("model_route_version_id");

--
-- Name: ix_ai_release_run; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_run" ON "ai"."release_decision" USING "btree" ("evaluation_run_id");

--
-- Name: ix_ai_release_runbook; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_runbook" ON "ai"."release_decision" USING "btree" ("rollback_runbook_artifact_id");

--
-- Name: ix_ai_release_schema; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_schema" ON "ai"."release_decision" USING "btree" ("output_schema_version_id");

--
-- Name: ix_ai_release_second_approver; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_second_approver" ON "ai"."release_decision" USING "btree" ("second_approver_principal_id");

--
-- Name: ix_ai_release_task_status; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_release_task_status" ON "ai"."release_decision" USING "btree" ("task_definition_id", "status", "approved_at" DESC);

--
-- Name: ix_ai_route_task; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_route_task" ON "ai"."model_route_version" USING "btree" ("task_definition_id", "status");

--
-- Name: ix_ai_usage_observed; Type: INDEX; Schema: ai; Owner: -
--

CREATE INDEX "ix_ai_usage_observed" ON "ai"."usage_cost" USING "btree" ("observed_at");

--
-- Name: uq_ai_eval_result_run_case_metric; Type: INDEX; Schema: ai; Owner: -
--

CREATE UNIQUE INDEX "uq_ai_eval_result_run_case_metric" ON "ai"."evaluation_result" USING "btree" ("evaluation_run_id", "evaluation_case_id", "metric_code");

--
-- Name: uq_ai_output_schema_active; Type: INDEX; Schema: ai; Owner: -
--

CREATE UNIQUE INDEX "uq_ai_output_schema_active" ON "ai"."output_schema_version" USING "btree" ("schema_code") WHERE ("status" = 'ACTIVE'::"text");

--
-- Name: uq_ai_prompt_task_locale_active; Type: INDEX; Schema: ai; Owner: -
--

CREATE UNIQUE INDEX "uq_ai_prompt_task_locale_active" ON "ai"."prompt_version" USING "btree" ("task_definition_id", "locale") WHERE ("status" = 'ACTIVE'::"text");

--
-- Name: uq_ai_route_active; Type: INDEX; Schema: ai; Owner: -
--

CREATE UNIQUE INDEX "uq_ai_route_active" ON "ai"."model_route_version" USING "btree" ("route_code") WHERE ("status" = 'ACTIVE'::"text");

--
-- Name: ix_catalog_affiliate_hash; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_affiliate_hash" ON "catalog"."affiliate_link_observation" USING "btree" ("url_sha256");

--
-- Name: ix_catalog_affiliate_link_observation_source_snapshot_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_affiliate_link_observation_source_snapshot_id" ON "catalog"."affiliate_link_observation" USING "btree" ("source_snapshot_id");

--
-- Name: ix_catalog_affiliate_offer_time; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_affiliate_offer_time" ON "catalog"."affiliate_link_observation" USING "btree" ("offer_id", "observed_at");

--
-- Name: ix_catalog_avail_observed_brin; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_avail_observed_brin" ON "catalog"."availability_observation" USING "brin" ("observed_at");

--
-- Name: ix_catalog_avail_offer_time; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_avail_offer_time" ON "catalog"."availability_observation" USING "btree" ("offer_id", "observed_at");

--
-- Name: ix_catalog_availability_observation_source_snapshot_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_availability_observation_source_snapshot_id" ON "catalog"."availability_observation" USING "btree" ("source_snapshot_id");
