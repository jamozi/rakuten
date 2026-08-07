-- ST-0304 physical translation fragment 04 of 11.
-- Source: approved RAOS data catalog plus finalized ST-0003/ST-0004 semantics.
-- Capture: PostgreSQL 18.4 pg_dump --schema-only --no-owner --no-privileges
--          --no-security-labels --quote-all-identifiers for the six owned schemas.
-- Schema creation/comments are rendered once by the ST-0304 generator. The 22
-- role-bound CREATE POLICY objects remain ST-0306-owned. ENABLE/FORCE RLS remains.

--
-- Name: COLUMN "ai_job"."article_version_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_job"."article_version_id" IS '記事の特定Version。';

--
-- Name: COLUMN "ai_job"."source_packet_version_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_job"."source_packet_version_id" IS 'source packet version id';

--
-- Name: COLUMN "ai_job"."prompt_version_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_job"."prompt_version_id" IS 'prompt version id';

--
-- Name: COLUMN "ai_job"."output_schema_version_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_job"."output_schema_version_id" IS 'output schema version id';

--
-- Name: COLUMN "ai_job"."model_route_version_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_job"."model_route_version_id" IS 'model route version id';

--
-- Name: COLUMN "ai_job"."status"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_job"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "ai_job"."max_cost_jpy"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_job"."max_cost_jpy" IS 'max cost jpy';

--
-- Name: COLUMN "ai_job"."completed_at"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_job"."completed_at" IS 'completed at';

--
-- Name: COLUMN "ai_job"."created_at"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."ai_job"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: evaluation_case; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."evaluation_case" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "dataset_version_id" "uuid" NOT NULL,
    "case_key" "text" NOT NULL,
    "task_definition_id" "uuid" NOT NULL,
    "split" "text" NOT NULL,
    "category" "text" NOT NULL,
    "risk_level" "text" NOT NULL,
    "input_artifact_id" "uuid" NOT NULL,
    "gold_artifact_id" "uuid",
    "expected_disposition" "text" NOT NULL,
    "tags" "text"[] DEFAULT ARRAY[]::"text"[] NOT NULL,
    "metadata" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_ai_eval_case_category" CHECK (("btrim"("category") <> ''::"text")),
    CONSTRAINT "ck_ai_eval_case_disposition" CHECK (("expected_disposition" = ANY (ARRAY['CALL_PROVIDER_AND_PASS'::"text", 'CALL_PROVIDER_AND_FLAG'::"text", 'BLOCK_BEFORE_PROVIDER'::"text", 'EXPECTED_REFUSAL'::"text", 'EXPECTED_TERMINAL_FAILURE'::"text"]))),
    CONSTRAINT "ck_ai_eval_case_key" CHECK (("btrim"("case_key") <> ''::"text")),
    CONSTRAINT "ck_ai_eval_case_meta" CHECK (("jsonb_typeof"("metadata") = 'object'::"text")),
    CONSTRAINT "ck_ai_eval_case_risk" CHECK (("risk_level" = ANY (ARRAY['LOW'::"text", 'MEDIUM'::"text", 'HIGH'::"text", 'CRITICAL'::"text"]))),
    CONSTRAINT "ck_ai_eval_case_split" CHECK (("split" = ANY (ARRAY['BOOTSTRAP'::"text", 'DEV'::"text", 'CALIBRATION'::"text", 'HOLDOUT'::"text", 'REGRESSION'::"text", 'ADVERSARIAL'::"text", 'PRODUCTION_SAMPLE'::"text"])))
);

--
-- Name: TABLE "evaluation_case"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."evaluation_case" IS 'Immutable case metadata within a versioned evaluation dataset.';

--
-- Name: evaluation_case_result; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."evaluation_case_result" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "evaluation_run_id" "uuid" NOT NULL,
    "evaluation_case_id" "uuid" NOT NULL,
    "ai_attempt_id" "uuid",
    "output_artifact_id" "uuid",
    "status" "text" NOT NULL,
    "disposition" "text" NOT NULL,
    "zero_tolerance_evidence" "jsonb" NOT NULL,
    "zero_tolerance_evidence_artifact_id" "uuid" CONSTRAINT "evaluation_case_result_zero_tolerance_evidence_artifac_not_null" NOT NULL,
    "zero_tolerance_evidence_sha256" "text" NOT NULL,
    "zero_tolerance_failure_count" integer GENERATED ALWAYS AS (((((((((("zero_tolerance_evidence" ->> 'AI-FCT-001'::"text"))::integer + (("zero_tolerance_evidence" ->> 'AI-FCT-004'::"text"))::integer) + (("zero_tolerance_evidence" ->> 'AI-POL-001'::"text"))::integer) + (("zero_tolerance_evidence" ->> 'AI-POL-002'::"text"))::integer) + (("zero_tolerance_evidence" ->> 'AI-FCT-003'::"text"))::integer) + (("zero_tolerance_evidence" ->> 'AI-POL-003'::"text"))::integer) + (("zero_tolerance_evidence" ->> 'AI-POL-005'::"text"))::integer) + (("zero_tolerance_evidence" ->> 'AI-POL-004'::"text"))::integer)) STORED NOT NULL,
    "grader_summary" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_ai_eval_case_result_disposition" CHECK (("disposition" = ANY (ARRAY['CALL_PROVIDER_AND_PASS'::"text", 'CALL_PROVIDER_AND_FLAG'::"text", 'BLOCK_BEFORE_PROVIDER'::"text", 'EXPECTED_REFUSAL'::"text", 'EXPECTED_TERMINAL_FAILURE'::"text"]))),
    CONSTRAINT "ck_ai_eval_case_result_failures" CHECK ((("zero_tolerance_failure_count" >= 0) AND ("zero_tolerance_failure_count" <= 50))),
    CONSTRAINT "ck_ai_eval_case_result_passed_zero_tolerance" CHECK ((("status" <> 'PASSED'::"text") OR ("zero_tolerance_failure_count" = 0))),
    CONSTRAINT "ck_ai_eval_case_result_status" CHECK (("status" = ANY (ARRAY['PASSED'::"text", 'FAILED'::"text", 'QUARANTINED'::"text", 'INVALID'::"text"]))),
    CONSTRAINT "ck_ai_eval_case_result_summary" CHECK (("jsonb_typeof"("grader_summary") = 'object'::"text")),
    CONSTRAINT "ck_ai_eval_case_result_zero_tolerance_evidence" CHECK ((("jsonb_typeof"("zero_tolerance_evidence") = 'object'::"text") AND ("zero_tolerance_evidence" ?& ARRAY['AI-FCT-001'::"text", 'AI-FCT-004'::"text", 'AI-POL-001'::"text", 'AI-POL-002'::"text", 'AI-FCT-003'::"text", 'AI-POL-003'::"text", 'AI-POL-005'::"text", 'AI-POL-004'::"text"]) AND (("zero_tolerance_evidence" - ARRAY['AI-FCT-001'::"text", 'AI-FCT-004'::"text", 'AI-POL-001'::"text", 'AI-POL-002'::"text", 'AI-FCT-003'::"text", 'AI-POL-003'::"text", 'AI-POL-005'::"text", 'AI-POL-004'::"text"]) = '{}'::"jsonb") AND ("jsonb_typeof"(("zero_tolerance_evidence" -> 'AI-FCT-001'::"text")) = 'number'::"text") AND ("jsonb_typeof"(("zero_tolerance_evidence" -> 'AI-FCT-004'::"text")) = 'number'::"text") AND ("jsonb_typeof"(("zero_tolerance_evidence" -> 'AI-POL-001'::"text")) = 'number'::"text") AND ("jsonb_typeof"(("zero_tolerance_evidence" -> 'AI-POL-002'::"text")) = 'number'::"text") AND ("jsonb_typeof"(("zero_tolerance_evidence" -> 'AI-FCT-003'::"text")) = 'number'::"text") AND ("jsonb_typeof"(("zero_tolerance_evidence" -> 'AI-POL-003'::"text")) = 'number'::"text") AND ("jsonb_typeof"(("zero_tolerance_evidence" -> 'AI-POL-005'::"text")) = 'number'::"text") AND ("jsonb_typeof"(("zero_tolerance_evidence" -> 'AI-POL-004'::"text")) = 'number'::"text") AND (("zero_tolerance_evidence" ->> 'AI-FCT-001'::"text") ~ '^(0|[1-9]|[1-4][0-9]|50)$'::"text") AND (("zero_tolerance_evidence" ->> 'AI-FCT-004'::"text") ~ '^(0|[1-9]|[1-4][0-9]|50)$'::"text") AND (("zero_tolerance_evidence" ->> 'AI-POL-001'::"text") ~ '^(0|[1-9]|[1-4][0-9]|50)$'::"text") AND (("zero_tolerance_evidence" ->> 'AI-POL-002'::"text") ~ '^(0|[1-9]|[1-4][0-9]|50)$'::"text") AND (("zero_tolerance_evidence" ->> 'AI-FCT-003'::"text") ~ '^(0|[1-9]|[1-4][0-9]|50)$'::"text") AND (("zero_tolerance_evidence" ->> 'AI-POL-003'::"text") ~ '^(0|[1-9]|[1-4][0-9]|50)$'::"text") AND (("zero_tolerance_evidence" ->> 'AI-POL-005'::"text") ~ '^(0|[1-9]|[1-4][0-9]|50)$'::"text") AND (("zero_tolerance_evidence" ->> 'AI-POL-004'::"text") ~ '^(0|[1-9]|[1-4][0-9]|50)$'::"text"))),
    CONSTRAINT "ck_ai_eval_case_result_zero_tolerance_sha" CHECK (("zero_tolerance_evidence_sha256" ~ '^[0-9a-f]{64}$'::"text"))
);

--
-- Name: TABLE "evaluation_case_result"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."evaluation_case_result" IS 'Append-only output and grader disposition for one evaluation case.';

--
-- Name: evaluation_dataset_version; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."evaluation_dataset_version" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "dataset_code" "text" NOT NULL,
    "version_no" integer NOT NULL,
    "purpose" "text" NOT NULL,
    "split_policy" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "dataset_artifact_id" "uuid" NOT NULL,
    "dataset_sha256" "text" NOT NULL,
    "case_count" integer NOT NULL,
    "status" "text" DEFAULT 'DRAFT'::"text" NOT NULL,
    "locked_by_principal_id" "uuid",
    "locked_at" timestamp with time zone,
    "compromised_at" timestamp with time zone,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_ai_eval_dataset_code" CHECK (("btrim"("dataset_code") <> ''::"text")),
    CONSTRAINT "ck_ai_eval_dataset_compromised" CHECK ((("status" <> 'COMPROMISED'::"text") OR ("compromised_at" IS NOT NULL))),
    CONSTRAINT "ck_ai_eval_dataset_count" CHECK (("case_count" >= 0)),
    CONSTRAINT "ck_ai_eval_dataset_display" CHECK (("btrim"("display_id") <> ''::"text")),
    CONSTRAINT "ck_ai_eval_dataset_lock" CHECK ((("status" <> ALL (ARRAY['LOCKED'::"text", 'ACTIVE'::"text", 'COMPROMISED'::"text", 'RETIRED'::"text"])) OR (("locked_by_principal_id" IS NOT NULL) AND ("locked_at" IS NOT NULL)))),
    CONSTRAINT "ck_ai_eval_dataset_purpose" CHECK (("btrim"("purpose") <> ''::"text")),
    CONSTRAINT "ck_ai_eval_dataset_sha" CHECK (("dataset_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_ai_eval_dataset_split" CHECK (("jsonb_typeof"("split_policy") = 'object'::"text")),
    CONSTRAINT "ck_ai_eval_dataset_status" CHECK (("status" = ANY (ARRAY['DRAFT'::"text", 'CURATING'::"text", 'LOCKED'::"text", 'ACTIVE'::"text", 'COMPROMISED'::"text", 'RETIRED'::"text"]))),
    CONSTRAINT "ck_ai_eval_dataset_version" CHECK (("version_no" >= 1)),
    CONSTRAINT "ck_ai_eval_dataset_version_lock" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "evaluation_dataset_version"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."evaluation_dataset_version" IS 'Hash-bound evaluation dataset version; LOCKED versions are immutable by contract.';

--
-- Name: evaluation_result; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."evaluation_result" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "suite_code" "text" NOT NULL,
    "suite_version" integer NOT NULL,
    "run_id" "uuid" NOT NULL,
    "task_definition_id" "uuid" NOT NULL,
    "model_route_version_id" "uuid" NOT NULL,
    "prompt_version_id" "uuid" NOT NULL,
    "case_key" "text" NOT NULL,
    "metric_code" "text" NOT NULL,
    "metric_value" numeric(20,8) NOT NULL,
    "passed" boolean,
    "details" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "result_artifact_id" "uuid",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "evaluation_run_id" "uuid",
    "evaluation_case_id" "uuid",
    "grader_code" "text",
    "slice_key" "text",
    "threshold_operator" "text",
    "threshold_value" numeric,
    "judge_calibration_id" "uuid",
    "judge_route_version_id" "uuid",
    "judge_prompt_version_id" "uuid",
    "judge_rubric_artifact_id" "uuid",
    "judge_resolved_model_id" "uuid",
    "judge_grader_version" "text",
    "proportion_numerator_count" bigint,
    "proportion_denominator_count" bigint,
    CONSTRAINT "ck_ai_eval_details" CHECK (("jsonb_typeof"("details") = 'object'::"text")),
    CONSTRAINT "ck_ai_eval_result_grader" CHECK ((("grader_code" IS NULL) OR ("btrim"("grader_code") <> ''::"text"))),
    CONSTRAINT "ck_ai_eval_result_judge_provenance" CHECK (((("grader_code" = 'grader.model_judge.v1'::"text") AND ("judge_calibration_id" IS NOT NULL) AND ("judge_route_version_id" IS NOT NULL) AND ("judge_prompt_version_id" IS NOT NULL) AND ("judge_rubric_artifact_id" IS NOT NULL) AND ("judge_resolved_model_id" IS NOT NULL) AND ("judge_grader_version" IS NOT NULL) AND ("btrim"("judge_grader_version") <> ''::"text")) OR (("grader_code" IS DISTINCT FROM 'grader.model_judge.v1'::"text") AND ("judge_calibration_id" IS NULL) AND ("judge_route_version_id" IS NULL) AND ("judge_prompt_version_id" IS NULL) AND ("judge_rubric_artifact_id" IS NULL) AND ("judge_resolved_model_id" IS NULL) AND ("judge_grader_version" IS NULL)))),
    CONSTRAINT "ck_ai_eval_result_proportion_counts" CHECK (((("evaluation_run_id" IS NULL) AND ("proportion_numerator_count" IS NULL) AND ("proportion_denominator_count" IS NULL)) OR (("evaluation_run_id" IS NOT NULL) AND ((("ai"."canonical_metric_unit"("metric_code") = 'ratio'::"text") AND ("proportion_numerator_count" IS NOT NULL) AND ("proportion_denominator_count" IS NOT NULL) AND (("proportion_numerator_count" >= 0) AND ("proportion_numerator_count" <= "proportion_denominator_count")) AND ("proportion_denominator_count" > 0) AND ("metric_value" = (("proportion_numerator_count")::numeric / ("proportion_denominator_count")::numeric))) OR (("ai"."canonical_metric_unit"("metric_code") <> 'ratio'::"text") AND ("proportion_numerator_count" IS NULL) AND ("proportion_denominator_count" IS NULL)))))),
    CONSTRAINT "ck_ai_eval_result_run_binding" CHECK ((("evaluation_run_id" IS NULL) OR ("evaluation_run_id" = "run_id"))),
    CONSTRAINT "ck_ai_eval_result_slice" CHECK ((("slice_key" IS NULL) OR ("btrim"("slice_key") <> ''::"text"))),
    CONSTRAINT "ck_ai_eval_result_threshold" CHECK (((("threshold_operator" IS NULL) OR ("threshold_operator" = ANY (ARRAY['>='::"text", '>'::"text", '<='::"text", '<'::"text", '=='::"text", '!='::"text"]))) AND ((("evaluation_run_id" IS NULL) AND ("passed" IS NOT NULL)) OR (("evaluation_run_id" IS NOT NULL) AND ("metric_code" = ANY (ARRAY['latency_p95_ms'::"text", 'cost_jpy_p95'::"text"])) AND ((("threshold_operator" IS NULL) AND ("threshold_value" IS NULL) AND ("passed" IS NULL)) OR (("threshold_operator" IS NOT NULL) AND ("threshold_value" IS NOT NULL) AND ("passed" IS NOT NULL)))) OR (("evaluation_run_id" IS NOT NULL) AND ("metric_code" <> ALL (ARRAY['latency_p95_ms'::"text", 'cost_jpy_p95'::"text"])) AND ("threshold_operator" IS NOT NULL) AND ("threshold_value" IS NOT NULL) AND ("passed" IS NOT NULL))))),
    CONSTRAINT "ck_ai_eval_suite_version" CHECK (("suite_version" >= 1))
);

--
-- Name: TABLE "evaluation_result"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."evaluation_result" IS 'Model RouteまたはPrompt候補を固定Evaluation suiteで比較したCase/Metric結果。詳細DatasetはArtifactへ置く。';

--
-- Name: COLUMN "evaluation_result"."id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."evaluation_result"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "evaluation_result"."suite_code"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."evaluation_result"."suite_code" IS 'suite code';

--
-- Name: COLUMN "evaluation_result"."suite_version"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."evaluation_result"."suite_version" IS 'suite version';

--
-- Name: COLUMN "evaluation_result"."run_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."evaluation_result"."run_id" IS 'run id';

--
-- Name: COLUMN "evaluation_result"."task_definition_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."evaluation_result"."task_definition_id" IS 'task definition id';

--
-- Name: COLUMN "evaluation_result"."model_route_version_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."evaluation_result"."model_route_version_id" IS 'model route version id';

--
-- Name: COLUMN "evaluation_result"."prompt_version_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."evaluation_result"."prompt_version_id" IS 'prompt version id';

--
-- Name: COLUMN "evaluation_result"."case_key"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."evaluation_result"."case_key" IS 'case key';

--
-- Name: COLUMN "evaluation_result"."metric_code"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."evaluation_result"."metric_code" IS 'metric code';

--
-- Name: COLUMN "evaluation_result"."metric_value"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."evaluation_result"."metric_value" IS 'metric value';

--
-- Name: COLUMN "evaluation_result"."passed"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."evaluation_result"."passed" IS 'passed';

--
-- Name: COLUMN "evaluation_result"."details"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."evaluation_result"."details" IS 'details';

--
-- Name: COLUMN "evaluation_result"."result_artifact_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."evaluation_result"."result_artifact_id" IS 'result artifact id';

--
-- Name: COLUMN "evaluation_result"."created_at"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."evaluation_result"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: evaluation_run; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."evaluation_run" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "suite_id" "uuid" NOT NULL,
    "dataset_version_id" "uuid" NOT NULL,
    "baseline_evaluation_run_id" "uuid",
    "prompt_version_id" "uuid" NOT NULL,
    "model_route_version_id" "uuid" NOT NULL,
    "output_schema_version_id" "uuid" NOT NULL,
    "policy_bundle_version_id" "uuid" NOT NULL,
    "code_git_sha" "text" NOT NULL,
    "status" "text" DEFAULT 'PLANNED'::"text" NOT NULL,
    "run_manifest_artifact_id" "uuid",
    "started_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "created_by_principal_id" "uuid" NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "resolved_model_id" "uuid" NOT NULL,
    CONSTRAINT "ck_ai_eval_run_completion" CHECK ((("status" <> ALL (ARRAY['COMPLETED'::"text", 'FAILED'::"text", 'INVALIDATED'::"text"])) OR ("completed_at" IS NOT NULL))),
    CONSTRAINT "ck_ai_eval_run_display" CHECK (("btrim"("display_id") <> ''::"text")),
    CONSTRAINT "ck_ai_eval_run_git" CHECK (("code_git_sha" ~ '^[0-9a-f]{40,64}$'::"text")),
    CONSTRAINT "ck_ai_eval_run_status" CHECK (("status" = ANY (ARRAY['PLANNED'::"text", 'RUNNING'::"text", 'GRADING'::"text", 'HUMAN_REVIEW'::"text", 'COMPLETED'::"text", 'FAILED'::"text", 'INVALIDATED'::"text"]))),
    CONSTRAINT "ck_ai_eval_run_timing" CHECK ((("completed_at" IS NULL) OR (("started_at" IS NOT NULL) AND ("completed_at" >= "started_at")))),
    CONSTRAINT "ck_ai_eval_run_version_lock" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "evaluation_run"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."evaluation_run" IS 'Prompt/route/schema/policy/code/dataset-bound evaluation execution.';

--
-- Name: COLUMN "evaluation_run"."resolved_model_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."evaluation_run"."resolved_model_id" IS 'Exact provider model measured by this immutable evaluation run.';

--
-- Name: evaluation_suite; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."evaluation_suite" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "suite_code" "text" NOT NULL,
    "version_no" integer NOT NULL,
    "task_definition_id" "uuid" NOT NULL,
    "risk_level" "text" NOT NULL,
    "rubric_artifact_id" "uuid",
    "suite_config" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "status" "text" DEFAULT 'DRAFT'::"text" NOT NULL,
    "approved_by_principal_id" "uuid",
    "approved_at" timestamp with time zone,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_ai_eval_suite_approval" CHECK ((("status" <> 'ACTIVE'::"text") OR (("approved_by_principal_id" IS NOT NULL) AND ("approved_at" IS NOT NULL)))),
    CONSTRAINT "ck_ai_eval_suite_approval_time" CHECK ((("approved_at" IS NULL) OR ("approved_at" >= "created_at"))),
    CONSTRAINT "ck_ai_eval_suite_code" CHECK (("btrim"("suite_code") <> ''::"text")),
    CONSTRAINT "ck_ai_eval_suite_config" CHECK (("jsonb_typeof"("suite_config") = 'object'::"text")),
    CONSTRAINT "ck_ai_eval_suite_risk" CHECK (("risk_level" = ANY (ARRAY['LOW'::"text", 'MEDIUM'::"text", 'HIGH'::"text", 'CRITICAL'::"text"]))),
    CONSTRAINT "ck_ai_eval_suite_status" CHECK (("status" = ANY (ARRAY['DRAFT'::"text", 'LOCKED'::"text", 'ACTIVE'::"text", 'RETIRED'::"text"]))),
    CONSTRAINT "ck_ai_eval_suite_version" CHECK (("version_no" >= 1)),
    CONSTRAINT "ck_ai_eval_suite_version_lock" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "evaluation_suite"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."evaluation_suite" IS 'Versioned task rubric, thresholds, and required evaluation splits.';

--
-- Name: human_evaluation; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."human_evaluation" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "evaluation_case_result_id" "uuid" NOT NULL,
    "reviewer_principal_id" "uuid" NOT NULL,
    "rubric_version" "text" NOT NULL,
    "blind_assignment_key" "text" NOT NULL,
    "scores" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "decision" "text" NOT NULL,
    "notes_artifact_id" "uuid",
    "is_adjudication" boolean DEFAULT false NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_ai_human_eval_blind_key" CHECK (("btrim"("blind_assignment_key") <> ''::"text")),
    CONSTRAINT "ck_ai_human_eval_decision" CHECK (("decision" = ANY (ARRAY['PASS'::"text", 'FAIL'::"text", 'NEEDS_ADJUDICATION'::"text", 'INVALID'::"text"]))),
    CONSTRAINT "ck_ai_human_eval_rubric" CHECK (("btrim"("rubric_version") <> ''::"text")),
    CONSTRAINT "ck_ai_human_eval_scores" CHECK (("jsonb_typeof"("scores") = 'object'::"text"))
);

--
-- Name: TABLE "human_evaluation"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."human_evaluation" IS 'Blind human label or distinct adjudication record.';

--
-- Name: judge_calibration; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."judge_calibration" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "judge_route_version_id" "uuid" NOT NULL,
    "judge_prompt_version_id" "uuid" NOT NULL,
    "dataset_version_id" "uuid" NOT NULL,
    "weighted_kappa" numeric(8,6),
    "zero_tolerance_false_pass_rate" numeric(8,6),
    "zero_tolerance_false_fail_rate" numeric(8,6),
    "case_count" integer NOT NULL,
    "status" "text" DEFAULT 'DRAFT'::"text" NOT NULL,
    "report_artifact_id" "uuid",
    "approved_by_principal_id" "uuid",
    "approved_at" timestamp with time zone,
    "expires_at" timestamp with time zone,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "evaluated_task_definition_id" "uuid" NOT NULL,
    "resolved_judge_model_id" "uuid" NOT NULL,
    "rubric_artifact_id" "uuid" NOT NULL,
    "rubric_sha256" "text" NOT NULL,
    "grader_version" "text" NOT NULL,
    CONSTRAINT "ck_ai_judge_cal_approval" CHECK ((("status" <> 'PASSED'::"text") OR (("weighted_kappa" IS NOT NULL) AND ("weighted_kappa" >= 0.70) AND ("zero_tolerance_false_pass_rate" IS NOT NULL) AND ("zero_tolerance_false_pass_rate" <= 0.01) AND ("zero_tolerance_false_fail_rate" IS NOT NULL) AND ("zero_tolerance_false_fail_rate" <= 0.05) AND ("case_count" >= 200) AND ("report_artifact_id" IS NOT NULL) AND ("approved_by_principal_id" IS NOT NULL) AND ("approved_at" IS NOT NULL) AND ("expires_at" IS NOT NULL)))),
    CONSTRAINT "ck_ai_judge_cal_approval_time" CHECK ((("approved_at" IS NULL) OR ("approved_at" >= "created_at"))),
    CONSTRAINT "ck_ai_judge_cal_count" CHECK (("case_count" >= 0)),
    CONSTRAINT "ck_ai_judge_cal_display" CHECK (("btrim"("display_id") <> ''::"text")),
    CONSTRAINT "ck_ai_judge_cal_expiry" CHECK ((("status" <> 'EXPIRED'::"text") OR ("expires_at" IS NOT NULL))),
    CONSTRAINT "ck_ai_judge_cal_expiry_time" CHECK ((("expires_at" IS NULL) OR (("approved_at" IS NOT NULL) AND ("expires_at" > "approved_at")))),
    CONSTRAINT "ck_ai_judge_cal_grader_version" CHECK (("btrim"("grader_version") <> ''::"text")),
    CONSTRAINT "ck_ai_judge_cal_rates" CHECK (((("weighted_kappa" IS NULL) OR (("weighted_kappa" >= ('-1'::integer)::numeric) AND ("weighted_kappa" <= (1)::numeric))) AND (("zero_tolerance_false_pass_rate" IS NULL) OR (("zero_tolerance_false_pass_rate" >= (0)::numeric) AND ("zero_tolerance_false_pass_rate" <= (1)::numeric))) AND (("zero_tolerance_false_fail_rate" IS NULL) OR (("zero_tolerance_false_fail_rate" >= (0)::numeric) AND ("zero_tolerance_false_fail_rate" <= (1)::numeric))))),
    CONSTRAINT "ck_ai_judge_cal_rubric_sha" CHECK (("rubric_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_ai_judge_cal_status" CHECK (("status" = ANY (ARRAY['DRAFT'::"text", 'PASSED'::"text", 'FAILED'::"text", 'EXPIRED'::"text", 'RETIRED'::"text"]))),
    CONSTRAINT "ck_ai_judge_cal_version_lock" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "judge_calibration"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."judge_calibration" IS 'Human-agreement evidence required before model-judge release use.';

--
-- Name: model_definition; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."model_definition" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "provider_code" "text" NOT NULL,
    "provider_model_id" "text" NOT NULL,
    "display_name" "text" NOT NULL,
    "capabilities" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "input_price_per_million" numeric(20,8),
    "cached_input_price_per_million" numeric(20,8),
    "output_price_per_million" numeric(20,8),
    "pricing_currency" "text",
    "pricing_observed_at" timestamp with time zone,
    "status" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "context_window_tokens" integer,
    "max_output_tokens" integer,
    "knowledge_cutoff" "date",
    "metadata_observed_at" timestamp with time zone,
    "provider_metadata" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    CONSTRAINT "ck_ai_model_capabilities" CHECK (("jsonb_typeof"("capabilities") = 'object'::"text")),
    CONSTRAINT "ck_ai_model_context" CHECK ((("context_window_tokens" IS NULL) OR ("context_window_tokens" > 0))),
    CONSTRAINT "ck_ai_model_currency" CHECK ((("pricing_currency" IS NULL) OR ("pricing_currency" ~ '^[A-Z]{3}$'::"text"))),
    CONSTRAINT "ck_ai_model_metadata" CHECK ((("provider_metadata" IS NULL) OR ("jsonb_typeof"("provider_metadata") = 'object'::"text"))),
    CONSTRAINT "ck_ai_model_output" CHECK ((("max_output_tokens" IS NULL) OR ("max_output_tokens" > 0))),
    CONSTRAINT "ck_ai_model_prices" CHECK (((("input_price_per_million" IS NULL) OR ("input_price_per_million" >= (0)::numeric)) AND (("cached_input_price_per_million" IS NULL) OR ("cached_input_price_per_million" >= (0)::numeric)) AND (("output_price_per_million" IS NULL) OR ("output_price_per_million" >= (0)::numeric)))),
    CONSTRAINT "ck_ai_model_status" CHECK (("status" = ANY (ARRAY['ACTIVE'::"text", 'EVALUATION'::"text", 'PAUSED'::"text", 'RETIRED'::"text", 'BLOCKED'::"text"])))
);

--
-- Name: TABLE "model_definition"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."model_definition" IS 'Provider model ID、Capability、Pricing observation、稼働状態を管理する。API Keyは保持しない。';

--
-- Name: COLUMN "model_definition"."id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_definition"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "model_definition"."provider_code"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_definition"."provider_code" IS 'provider code';

--
-- Name: COLUMN "model_definition"."provider_model_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_definition"."provider_model_id" IS 'provider model id';

--
-- Name: COLUMN "model_definition"."display_name"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_definition"."display_name" IS 'display name';

--
-- Name: COLUMN "model_definition"."capabilities"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_definition"."capabilities" IS 'Structured output、context、batch等のCapability snapshot。';

--
-- Name: COLUMN "model_definition"."input_price_per_million"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_definition"."input_price_per_million" IS 'input price per million';

--
-- Name: COLUMN "model_definition"."cached_input_price_per_million"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_definition"."cached_input_price_per_million" IS 'cached input price per million';

--
-- Name: COLUMN "model_definition"."output_price_per_million"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_definition"."output_price_per_million" IS 'output price per million';

--
-- Name: COLUMN "model_definition"."pricing_currency"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_definition"."pricing_currency" IS 'pricing currency';

--
-- Name: COLUMN "model_definition"."pricing_observed_at"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_definition"."pricing_observed_at" IS 'pricing observed at';

--
-- Name: COLUMN "model_definition"."status"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_definition"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "model_definition"."created_at"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_definition"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: model_route_version; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."model_route_version" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "route_code" "text" NOT NULL,
    "version_no" integer NOT NULL,
    "task_definition_id" "uuid" NOT NULL,
    "primary_model_id" "uuid" NOT NULL,
    "fallback_model_id" "uuid",
    "route_config" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "monthly_budget_jpy" bigint,
    "per_job_budget_jpy" bigint NOT NULL,
    "status" "text" NOT NULL,
    "effective_from" timestamp with time zone,
    "effective_to" timestamp with time zone,
    "approved_by_principal_id" "uuid",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_ai_route_budget" CHECK (((("monthly_budget_jpy" IS NULL) OR ("monthly_budget_jpy" >= 0)) AND ("per_job_budget_jpy" >= 0))),
    CONSTRAINT "ck_ai_route_config" CHECK (("jsonb_typeof"("route_config") = 'object'::"text")),
    CONSTRAINT "ck_ai_route_lock_version" CHECK ((("lock_version" IS NULL) OR ("lock_version" >= 0))),
    CONSTRAINT "ck_ai_route_models" CHECK ((("fallback_model_id" IS NULL) OR ("fallback_model_id" <> "primary_model_id"))),
    CONSTRAINT "ck_ai_route_status" CHECK (("status" = ANY (ARRAY['DRAFT'::"text", 'EVALUATING'::"text", 'CERTIFIED'::"text", 'CANARY'::"text", 'ACTIVE'::"text", 'PAUSED'::"text", 'ROLLED_BACK'::"text", 'RETIRED'::"text"]))),
    CONSTRAINT "ck_ai_route_version" CHECK (("version_no" >= 1)),
    CONSTRAINT "ck_ai_route_window" CHECK ((("effective_to" IS NULL) OR ("effective_from" IS NULL) OR ("effective_to" > "effective_from")))
);

--
-- Name: TABLE "model_route_version"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."model_route_version" IS 'TaskごとのPrimary/Fallback model、Timeout、Budget、Retry等の稼働Route version。';

--
-- Name: COLUMN "model_route_version"."id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_route_version"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "model_route_version"."route_code"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_route_version"."route_code" IS 'route code';

--
-- Name: COLUMN "model_route_version"."version_no"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_route_version"."version_no" IS 'Aggregate内で1から増加する不変Version番号。';

--
-- Name: COLUMN "model_route_version"."task_definition_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_route_version"."task_definition_id" IS 'task definition id';

--
-- Name: COLUMN "model_route_version"."primary_model_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_route_version"."primary_model_id" IS 'primary model id';

--
-- Name: COLUMN "model_route_version"."fallback_model_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_route_version"."fallback_model_id" IS 'fallback model id';

--
-- Name: COLUMN "model_route_version"."route_config"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_route_version"."route_config" IS 'Timeout、retry、temperature、max tokens等。';

--
-- Name: COLUMN "model_route_version"."monthly_budget_jpy"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_route_version"."monthly_budget_jpy" IS 'monthly budget jpy';

--
-- Name: COLUMN "model_route_version"."per_job_budget_jpy"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_route_version"."per_job_budget_jpy" IS 'per job budget jpy';

--
-- Name: COLUMN "model_route_version"."status"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_route_version"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "model_route_version"."effective_from"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_route_version"."effective_from" IS '設定・関係が有効になる時刻。';

--
-- Name: COLUMN "model_route_version"."effective_to"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_route_version"."effective_to" IS '設定・関係の有効終了時刻。NULLは終了未定。';

--
-- Name: COLUMN "model_route_version"."approved_by_principal_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_route_version"."approved_by_principal_id" IS 'approved by principal id';

--
-- Name: COLUMN "model_route_version"."created_at"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."model_route_version"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: output_schema_version; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."output_schema_version" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "schema_code" "text" NOT NULL,
    "version_no" integer NOT NULL,
    "git_path" "text" NOT NULL,
    "git_commit_sha" "text" NOT NULL,
    "schema_sha256" "text" NOT NULL,
    "status" "text" NOT NULL,
    "effective_from" timestamp with time zone,
    "effective_to" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_ai_output_schema_git" CHECK (("git_commit_sha" ~ '^[0-9a-f]{40,64}$'::"text")),
    CONSTRAINT "ck_ai_output_schema_hash" CHECK (("schema_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_ai_output_schema_status" CHECK (("status" = ANY (ARRAY['DRAFT'::"text", 'ACTIVE'::"text", 'RETIRED'::"text"]))),
    CONSTRAINT "ck_ai_output_schema_version" CHECK (("version_no" >= 1)),
    CONSTRAINT "ck_ai_output_schema_window" CHECK ((("effective_to" IS NULL) OR ("effective_from" IS NULL) OR ("effective_to" > "effective_from")))
);

--
-- Name: TABLE "output_schema_version"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."output_schema_version" IS 'Structured OutputのJSON Schema version、Git commit、hash、稼働状態を登録する。';

--
-- Name: COLUMN "output_schema_version"."id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."output_schema_version"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "output_schema_version"."schema_code"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."output_schema_version"."schema_code" IS 'schema code';

--
-- Name: COLUMN "output_schema_version"."version_no"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."output_schema_version"."version_no" IS 'Aggregate内で1から増加する不変Version番号。';

--
-- Name: COLUMN "output_schema_version"."git_path"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."output_schema_version"."git_path" IS 'git path';

--
-- Name: COLUMN "output_schema_version"."git_commit_sha"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."output_schema_version"."git_commit_sha" IS 'git commit sha';

--
-- Name: COLUMN "output_schema_version"."schema_sha256"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."output_schema_version"."schema_sha256" IS 'schema sha256';

--
-- Name: COLUMN "output_schema_version"."status"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."output_schema_version"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "output_schema_version"."effective_from"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."output_schema_version"."effective_from" IS '設定・関係が有効になる時刻。';

--
-- Name: COLUMN "output_schema_version"."effective_to"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."output_schema_version"."effective_to" IS '設定・関係の有効終了時刻。NULLは終了未定。';

--
-- Name: COLUMN "output_schema_version"."created_at"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."output_schema_version"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: prompt_version; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."prompt_version" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "task_definition_id" "uuid" NOT NULL,
    "prompt_code" "text" NOT NULL,
    "version_no" integer NOT NULL,
    "git_path" "text" NOT NULL,
    "git_commit_sha" "text" NOT NULL,
    "template_sha256" "text" NOT NULL,
    "status" "text" NOT NULL,
    "effective_from" timestamp with time zone,
    "effective_to" timestamp with time zone,
    "approved_by_principal_id" "uuid",
    "approved_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "locale" "text" DEFAULT 'ja-JP'::"text" NOT NULL,
    "compiler_version" "text",
    "input_contract_sha256" "text",
    "policy_test_status" "text" DEFAULT 'NOT_EXECUTED'::"text" NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "author_principal_id" "uuid" NOT NULL,
    CONSTRAINT "ck_ai_prompt_approval" CHECK ((("status" <> 'ACTIVE'::"text") OR (("approved_by_principal_id" IS NOT NULL) AND ("approved_at" IS NOT NULL)))),
    CONSTRAINT "ck_ai_prompt_compiler" CHECK ((("compiler_version" IS NULL) OR ("btrim"("compiler_version") <> ''::"text"))),
    CONSTRAINT "ck_ai_prompt_git" CHECK (("git_commit_sha" ~ '^[0-9a-f]{40,64}$'::"text")),
    CONSTRAINT "ck_ai_prompt_hash" CHECK (("template_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_ai_prompt_input_hash" CHECK ((("input_contract_sha256" IS NULL) OR ("input_contract_sha256" ~ '^[0-9a-f]{64}$'::"text"))),
    CONSTRAINT "ck_ai_prompt_locale" CHECK ((("locale" IS NULL) OR ("locale" ~ '^[a-z]{2,3}(-[A-Z]{2})?$'::"text"))),
    CONSTRAINT "ck_ai_prompt_lock_version" CHECK ((("lock_version" IS NULL) OR ("lock_version" >= 0))),
    CONSTRAINT "ck_ai_prompt_policy_test" CHECK ((("policy_test_status" IS NULL) OR ("policy_test_status" = ANY (ARRAY['NOT_EXECUTED'::"text", 'PASSED'::"text", 'FAILED'::"text"])))),
    CONSTRAINT "ck_ai_prompt_status" CHECK (("status" = ANY (ARRAY['DRAFT'::"text", 'IN_REVIEW'::"text", 'EVALUATING'::"text", 'CERTIFIED'::"text", 'ACTIVE'::"text", 'SUSPENDED'::"text", 'RETIRED'::"text"]))),
    CONSTRAINT "ck_ai_prompt_version" CHECK (("version_no" >= 1)),
    CONSTRAINT "ck_ai_prompt_window" CHECK ((("effective_to" IS NULL) OR ("effective_from" IS NULL) OR ("effective_to" > "effective_from")))
);

--
-- Name: TABLE "prompt_version"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."prompt_version" IS 'Git管理Prompt templateの稼働Version、hash、承認、適用期間を登録する。Prompt本文はDBへ重複保存しない。';

--
-- Name: COLUMN "prompt_version"."id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."prompt_version"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "prompt_version"."display_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."prompt_version"."display_id" IS 'PRM-接頭辞を持つアプリケーション生成の不変表示ID。';

--
-- Name: COLUMN "prompt_version"."task_definition_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."prompt_version"."task_definition_id" IS 'task definition id';

--
-- Name: COLUMN "prompt_version"."prompt_code"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."prompt_version"."prompt_code" IS 'prompt code';

--
-- Name: COLUMN "prompt_version"."version_no"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."prompt_version"."version_no" IS 'Aggregate内で1から増加する不変Version番号。';

--
-- Name: COLUMN "prompt_version"."git_path"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."prompt_version"."git_path" IS 'git path';

--
-- Name: COLUMN "prompt_version"."git_commit_sha"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."prompt_version"."git_commit_sha" IS 'git commit sha';

--
-- Name: COLUMN "prompt_version"."template_sha256"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."prompt_version"."template_sha256" IS 'template sha256';

--
-- Name: COLUMN "prompt_version"."status"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."prompt_version"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "prompt_version"."effective_from"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."prompt_version"."effective_from" IS '設定・関係が有効になる時刻。';

--
-- Name: COLUMN "prompt_version"."effective_to"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."prompt_version"."effective_to" IS '設定・関係の有効終了時刻。NULLは終了未定。';

--
-- Name: COLUMN "prompt_version"."approved_by_principal_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."prompt_version"."approved_by_principal_id" IS 'approved by principal id';

--
-- Name: COLUMN "prompt_version"."approved_at"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."prompt_version"."approved_at" IS 'approved at';

--
-- Name: COLUMN "prompt_version"."created_at"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."prompt_version"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "prompt_version"."author_principal_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."prompt_version"."author_principal_id" IS 'Human author provenance used to enforce release separation of duties.';

--
-- Name: release_approval; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."release_approval" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "release_decision_id" "uuid" NOT NULL,
    "phase" "text" NOT NULL,
    "decision_manifest_sha256" "text" NOT NULL,
    "primary_approver_principal_id" "uuid" NOT NULL,
    "primary_approver_role" "text" NOT NULL,
    "second_approver_principal_id" "uuid" NOT NULL,
    "second_approver_role" "text" NOT NULL,
    "approval_artifact_id" "uuid" NOT NULL,
    "approval_sha256" "text" NOT NULL,
    "signed_at" timestamp with time zone NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_ai_release_approval_display" CHECK (("btrim"("display_id") <> ''::"text")),
    CONSTRAINT "ck_ai_release_approval_manifest" CHECK (("decision_manifest_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_ai_release_approval_phase" CHECK (("phase" = ANY (ARRAY['CANARY'::"text", 'ACTIVE'::"text"]))),
    CONSTRAINT "ck_ai_release_approval_principals" CHECK (("second_approver_principal_id" <> "primary_approver_principal_id")),
    CONSTRAINT "ck_ai_release_approval_roles" CHECK ((("primary_approver_role" = 'APPROVER'::"text") AND ("second_approver_role" = 'OWNER'::"text"))),
    CONSTRAINT "ck_ai_release_approval_sha" CHECK (("approval_sha256" ~ '^[0-9a-f]{64}$'::"text"))
);

--
-- Name: TABLE "release_approval"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."release_approval" IS 'Append-only human signature bundle bound to one release phase and exact manifest.';

--
-- Name: release_decision; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."release_decision" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "display_id" "text" NOT NULL,
    "task_definition_id" "uuid" NOT NULL,
    "prompt_version_id" "uuid" NOT NULL,
    "model_route_version_id" "uuid" NOT NULL,
    "output_schema_version_id" "uuid" NOT NULL,
    "resolved_model_id" "uuid" NOT NULL,
    "policy_bundle_version_id" "uuid" NOT NULL,
    "dataset_version_id" "uuid" NOT NULL,
    "evaluation_run_id" "uuid" NOT NULL,
    "code_git_sha" "text" NOT NULL,
    "release_scope" "text" NOT NULL,
    "status" "text" DEFAULT 'DRAFT'::"text" NOT NULL,
    "maximum_canary_percent" smallint DEFAULT 0 NOT NULL,
    "decision_manifest_sha256" "text" NOT NULL,
    "rollback_release_decision_id" "uuid",
    "approved_by_principal_id" "uuid",
    "second_approver_principal_id" "uuid",
    "approved_at" timestamp with time zone,
    "revoked_by_principal_id" "uuid",
    "revoked_at" timestamp with time zone,
    "revocation_reason" "text",
    "lock_version" bigint DEFAULT 0 NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "judge_calibration_id" "uuid",
    "rollback_strategy" "text" NOT NULL,
    "rollback_runbook_artifact_id" "uuid",
    "rollback_runbook_sha256" "text",
    "canary_monitoring_artifact_id" "uuid",
    "canary_monitoring_sha256" "text",
    "canary_evidence_artifact_id" "uuid",
    "canary_evidence_sha256" "text",
    "canary_started_at" timestamp with time zone,
    "canary_completed_at" timestamp with time zone,
    "canary_started_txid" bigint,
    "canary_completed_txid" bigint,
    "canary_approval_id" "uuid",
    "active_approval_id" "uuid",
    CONSTRAINT "ck_ai_release_approval" CHECK ((("status" <> ALL (ARRAY['APPROVED_CANARY'::"text", 'APPROVED_ACTIVE'::"text", 'REVOKED'::"text"])) OR (("approved_by_principal_id" IS NOT NULL) AND ("approved_at" IS NOT NULL)))),
    CONSTRAINT "ck_ai_release_approval_time" CHECK ((("approved_at" IS NULL) OR ("approved_at" >= "created_at"))),
    CONSTRAINT "ck_ai_release_approvers" CHECK ((("second_approver_principal_id" IS NULL) OR ("second_approver_principal_id" <> "approved_by_principal_id"))),
    CONSTRAINT "ck_ai_release_canary" CHECK (((("maximum_canary_percent" >= 0) AND ("maximum_canary_percent" <= 100)) AND (("release_scope" = 'CANARY'::"text") OR ("maximum_canary_percent" = 0)))),
    CONSTRAINT "ck_ai_release_canary_time" CHECK (((("canary_started_at" IS NULL) AND ("canary_started_txid" IS NULL) AND ("canary_completed_at" IS NULL) AND ("canary_completed_txid" IS NULL) AND ("canary_evidence_artifact_id" IS NULL)) OR (("canary_started_at" IS NOT NULL) AND ("canary_started_txid" IS NOT NULL) AND ((("canary_completed_at" IS NULL) AND ("canary_completed_txid" IS NULL) AND ("canary_evidence_artifact_id" IS NULL)) OR (("canary_completed_at" > "canary_started_at") AND ("canary_completed_txid" IS NOT NULL) AND ("canary_evidence_artifact_id" IS NOT NULL)))))),
    CONSTRAINT "ck_ai_release_display" CHECK (("btrim"("display_id") <> ''::"text")),
    CONSTRAINT "ck_ai_release_evidence_sha" CHECK (((("canary_evidence_artifact_id" IS NULL) AND ("canary_evidence_sha256" IS NULL)) OR (("canary_evidence_artifact_id" IS NOT NULL) AND ("canary_evidence_sha256" IS NOT NULL) AND ("canary_evidence_sha256" ~ '^[0-9a-f]{64}$'::"text")))),
    CONSTRAINT "ck_ai_release_git" CHECK (("code_git_sha" ~ '^[0-9a-f]{40,64}$'::"text")),
    CONSTRAINT "ck_ai_release_monitoring_sha" CHECK (((("canary_monitoring_artifact_id" IS NULL) AND ("canary_monitoring_sha256" IS NULL)) OR (("canary_monitoring_artifact_id" IS NOT NULL) AND ("canary_monitoring_sha256" IS NOT NULL) AND ("canary_monitoring_sha256" ~ '^[0-9a-f]{64}$'::"text")))),
    CONSTRAINT "ck_ai_release_no_self_rollback" CHECK ((("rollback_release_decision_id" IS NULL) OR ("rollback_release_decision_id" <> "id"))),
    CONSTRAINT "ck_ai_release_phase_state" CHECK (((("status" = ANY (ARRAY['DRAFT'::"text", 'READY_FOR_REVIEW'::"text", 'REJECTED'::"text"])) AND ("canary_approval_id" IS NULL) AND ("active_approval_id" IS NULL) AND ("approved_by_principal_id" IS NULL) AND ("second_approver_principal_id" IS NULL) AND ("approved_at" IS NULL) AND ("canary_started_at" IS NULL) AND ("canary_started_txid" IS NULL) AND ("canary_completed_at" IS NULL) AND ("canary_completed_txid" IS NULL) AND ("canary_evidence_artifact_id" IS NULL) AND ("canary_evidence_sha256" IS NULL)) OR (("status" = 'APPROVED_CANARY'::"text") AND ("canary_approval_id" IS NOT NULL) AND ("active_approval_id" IS NULL) AND ("approved_by_principal_id" IS NOT NULL) AND ("second_approver_principal_id" IS NOT NULL) AND ("approved_at" IS NOT NULL) AND ("canary_started_at" IS NOT NULL) AND ("canary_started_txid" IS NOT NULL)) OR (("status" = 'APPROVED_ACTIVE'::"text") AND ("canary_approval_id" IS NOT NULL) AND ("active_approval_id" IS NOT NULL) AND ("approved_by_principal_id" IS NOT NULL) AND ("second_approver_principal_id" IS NOT NULL) AND ("approved_at" IS NOT NULL) AND ("canary_started_at" IS NOT NULL) AND ("canary_started_txid" IS NOT NULL) AND ("canary_completed_at" IS NOT NULL) AND ("canary_completed_txid" IS NOT NULL) AND ("canary_evidence_artifact_id" IS NOT NULL) AND ("canary_evidence_sha256" IS NOT NULL)) OR (("status" = 'REVOKED'::"text") AND ("canary_approval_id" IS NOT NULL) AND ("approved_by_principal_id" IS NOT NULL) AND ("second_approver_principal_id" IS NOT NULL) AND ("approved_at" IS NOT NULL) AND ("canary_started_at" IS NOT NULL) AND ("canary_started_txid" IS NOT NULL) AND (("active_approval_id" IS NULL) OR (("canary_completed_at" IS NOT NULL) AND ("canary_completed_txid" IS NOT NULL) AND ("canary_evidence_artifact_id" IS NOT NULL) AND ("canary_evidence_sha256" IS NOT NULL)))))),
    CONSTRAINT "ck_ai_release_revocation" CHECK (((("status" = 'REVOKED'::"text") AND ("revoked_by_principal_id" IS NOT NULL) AND ("revoked_at" IS NOT NULL) AND ("revocation_reason" IS NOT NULL) AND ("btrim"("revocation_reason") <> ''::"text")) OR (("status" <> 'REVOKED'::"text") AND ("revoked_by_principal_id" IS NULL) AND ("revoked_at" IS NULL) AND ("revocation_reason" IS NULL)))),
    CONSTRAINT "ck_ai_release_revocation_time" CHECK ((("revoked_at" IS NULL) OR (("approved_at" IS NOT NULL) AND ("revoked_at" >= "approved_at")))),
    CONSTRAINT "ck_ai_release_rollback_binding" CHECK (((("rollback_strategy" = 'PREVIOUS_RELEASE'::"text") AND ("rollback_release_decision_id" IS NOT NULL) AND ("rollback_runbook_artifact_id" IS NULL) AND ("rollback_runbook_sha256" IS NULL)) OR (("rollback_strategy" = 'DISABLE_ROUTE'::"text") AND ("rollback_release_decision_id" IS NULL) AND ("rollback_runbook_artifact_id" IS NOT NULL) AND ("rollback_runbook_sha256" IS NOT NULL) AND ("rollback_runbook_sha256" ~ '^[0-9a-f]{64}$'::"text")))),
    CONSTRAINT "ck_ai_release_rollback_strategy" CHECK (("rollback_strategy" = ANY (ARRAY['PREVIOUS_RELEASE'::"text", 'DISABLE_ROUTE'::"text"]))),
    CONSTRAINT "ck_ai_release_scope" CHECK (("release_scope" = ANY (ARRAY['SHADOW'::"text", 'CANARY'::"text", 'ACTIVE'::"text"]))),
    CONSTRAINT "ck_ai_release_scope_status" CHECK (((("status" <> 'APPROVED_CANARY'::"text") OR ("release_scope" = 'CANARY'::"text")) AND (("status" <> 'APPROVED_ACTIVE'::"text") OR ("release_scope" = 'ACTIVE'::"text")))),
    CONSTRAINT "ck_ai_release_sha" CHECK (("decision_manifest_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_ai_release_status" CHECK (("status" = ANY (ARRAY['DRAFT'::"text", 'READY_FOR_REVIEW'::"text", 'APPROVED_CANARY'::"text", 'APPROVED_ACTIVE'::"text", 'REJECTED'::"text", 'REVOKED'::"text"]))),
    CONSTRAINT "ck_ai_release_version_lock" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "release_decision"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."release_decision" IS 'Human-approved, hash-bound Shadow/Canary/Active AI release authority.';

--
-- Name: task_definition; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."task_definition" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "task_code" "text" NOT NULL,
    "name" "text" NOT NULL,
    "description" "text" NOT NULL,
    "risk_level" "text" NOT NULL,
    "output_schema_code" "text" NOT NULL,
    "default_max_tokens" integer NOT NULL,
    "default_max_cost_jpy" bigint NOT NULL,
    "human_review_required" boolean DEFAULT true NOT NULL,
    "status" "text" DEFAULT 'ACTIVE'::"text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_ai_task_cost" CHECK (("default_max_cost_jpy" >= 0)),
    CONSTRAINT "ck_ai_task_risk" CHECK (("risk_level" = ANY (ARRAY['LOW'::"text", 'MEDIUM'::"text", 'HIGH'::"text", 'CRITICAL'::"text"]))),
    CONSTRAINT "ck_ai_task_status" CHECK (("status" = ANY (ARRAY['ACTIVE'::"text", 'PAUSED'::"text", 'RETIRED'::"text"]))),
    CONSTRAINT "ck_ai_task_tokens" CHECK ((("default_max_tokens" >= 1) AND ("default_max_tokens" <= 1000000)))
);

--
-- Name: TABLE "task_definition"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."task_definition" IS 'AI処理のTask type、Risk、Output Schema、予算、人間Review要否を定義する。';

--
-- Name: COLUMN "task_definition"."id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."task_definition"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "task_definition"."task_code"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."task_definition"."task_code" IS 'task code';

--
-- Name: COLUMN "task_definition"."name"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."task_definition"."name" IS 'name';

--
-- Name: COLUMN "task_definition"."description"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."task_definition"."description" IS 'description';

--
-- Name: COLUMN "task_definition"."risk_level"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."task_definition"."risk_level" IS 'risk level';

--
-- Name: COLUMN "task_definition"."output_schema_code"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."task_definition"."output_schema_code" IS 'output schema code';

--
-- Name: COLUMN "task_definition"."default_max_tokens"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."task_definition"."default_max_tokens" IS 'default max tokens';

--
-- Name: COLUMN "task_definition"."default_max_cost_jpy"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."task_definition"."default_max_cost_jpy" IS 'default max cost jpy';

--
-- Name: COLUMN "task_definition"."human_review_required"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."task_definition"."human_review_required" IS 'human review required';

--
-- Name: COLUMN "task_definition"."status"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."task_definition"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "task_definition"."created_at"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."task_definition"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: usage_cost; Type: TABLE; Schema: ai; Owner: -
--

CREATE TABLE "ai"."usage_cost" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "ai_attempt_id" "uuid" NOT NULL,
    "input_tokens" bigint NOT NULL,
    "cached_input_tokens" bigint DEFAULT 0 NOT NULL,
    "output_tokens" bigint NOT NULL,
    "total_tokens" bigint NOT NULL,
    "provider_cost_amount" numeric(20,8) NOT NULL,
    "provider_currency" "text" NOT NULL,
    "fx_rate_to_jpy" numeric(20,8) NOT NULL,
    "cost_jpy" bigint NOT NULL,
    "pricing_version" "text" NOT NULL,
    "observed_at" timestamp with time zone NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_ai_usage_cost" CHECK ((("provider_cost_amount" >= (0)::numeric) AND ("fx_rate_to_jpy" > (0)::numeric) AND ("cost_jpy" >= 0))),
    CONSTRAINT "ck_ai_usage_currency" CHECK (("provider_currency" ~ '^[A-Z]{3}$'::"text")),
    CONSTRAINT "ck_ai_usage_tokens" CHECK ((("input_tokens" >= 0) AND ("cached_input_tokens" >= 0) AND ("output_tokens" >= 0) AND ("total_tokens" = ("input_tokens" + "output_tokens"))))
);

--
-- Name: TABLE "usage_cost"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON TABLE "ai"."usage_cost" IS 'AI AttemptのToken usage、Provider原通貨費用、換算Rate、JPY費用を不変記録する。';

--
-- Name: COLUMN "usage_cost"."id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."usage_cost"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "usage_cost"."ai_attempt_id"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."usage_cost"."ai_attempt_id" IS 'ai attempt id';

--
-- Name: COLUMN "usage_cost"."input_tokens"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."usage_cost"."input_tokens" IS 'input tokens';

--
-- Name: COLUMN "usage_cost"."cached_input_tokens"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."usage_cost"."cached_input_tokens" IS 'cached input tokens';

--
-- Name: COLUMN "usage_cost"."output_tokens"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."usage_cost"."output_tokens" IS 'output tokens';

--
-- Name: COLUMN "usage_cost"."total_tokens"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."usage_cost"."total_tokens" IS 'total tokens';

--
-- Name: COLUMN "usage_cost"."provider_cost_amount"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."usage_cost"."provider_cost_amount" IS 'provider cost amount';

--
-- Name: COLUMN "usage_cost"."provider_currency"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."usage_cost"."provider_currency" IS 'provider currency';

--
-- Name: COLUMN "usage_cost"."fx_rate_to_jpy"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."usage_cost"."fx_rate_to_jpy" IS 'fx rate to jpy';

--
-- Name: COLUMN "usage_cost"."cost_jpy"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."usage_cost"."cost_jpy" IS 'cost jpy';

--
-- Name: COLUMN "usage_cost"."pricing_version"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."usage_cost"."pricing_version" IS 'pricing version';

--
-- Name: COLUMN "usage_cost"."observed_at"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."usage_cost"."observed_at" IS 'observed at';

--
-- Name: COLUMN "usage_cost"."created_at"; Type: COMMENT; Schema: ai; Owner: -
--

COMMENT ON COLUMN "ai"."usage_cost"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: affiliate_link_observation; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."affiliate_link_observation" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "offer_id" "uuid" NOT NULL,
    "affiliate_url" "text" NOT NULL,
    "url_sha256" "text" NOT NULL,
    "destination_host" "text" NOT NULL,
    "is_api_returned" boolean NOT NULL,
    "affiliate_rate" numeric(9,6),
    "observed_at" timestamp with time zone NOT NULL,
    "valid_until" timestamp with time zone,
    "source_snapshot_id" "uuid" NOT NULL,
    "validation_status" "text" NOT NULL,
    "link_contract_version" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_catalog_affiliate_api" CHECK (("is_api_returned" = true)),
    CONSTRAINT "ck_catalog_affiliate_hash" CHECK (("url_sha256" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_catalog_affiliate_host" CHECK (("destination_host" ~ '^[a-z0-9.-]+$'::"text")),
    CONSTRAINT "ck_catalog_affiliate_rate" CHECK ((("affiliate_rate" IS NULL) OR (("affiliate_rate" >= (0)::numeric) AND ("affiliate_rate" <= (100)::numeric)))),
    CONSTRAINT "ck_catalog_affiliate_url" CHECK (("affiliate_url" ~ '^https://'::"text")),
    CONSTRAINT "ck_catalog_affiliate_valid" CHECK ((("valid_until" IS NULL) OR ("valid_until" > "observed_at"))),
    CONSTRAINT "ck_catalog_affiliate_validation" CHECK (("validation_status" = ANY (ARRAY['VALID'::"text", 'UNVERIFIED'::"text", 'INVALID'::"text", 'EXPIRED'::"text", 'BLOCKED'::"text"])))
);

--
-- Name: TABLE "affiliate_link_observation"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."affiliate_link_observation" IS '公式/API返却Affiliate URL、Destination host、URL hash、料率Observationを追記し、URLを改変しない。';

--
-- Name: COLUMN "affiliate_link_observation"."id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."affiliate_link_observation"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "affiliate_link_observation"."offer_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."affiliate_link_observation"."offer_id" IS 'ショップ単位の販売Offer。';

--
-- Name: COLUMN "affiliate_link_observation"."affiliate_url"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."affiliate_link_observation"."affiliate_url" IS 'affiliate url';

--
-- Name: COLUMN "affiliate_link_observation"."url_sha256"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."affiliate_link_observation"."url_sha256" IS 'url sha256';

--
-- Name: COLUMN "affiliate_link_observation"."destination_host"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."affiliate_link_observation"."destination_host" IS 'destination host';

--
-- Name: COLUMN "affiliate_link_observation"."is_api_returned"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."affiliate_link_observation"."is_api_returned" IS 'is api returned';

--
-- Name: COLUMN "affiliate_link_observation"."affiliate_rate"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."affiliate_link_observation"."affiliate_rate" IS 'affiliate rate';

--
-- Name: COLUMN "affiliate_link_observation"."observed_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."affiliate_link_observation"."observed_at" IS 'observed at';

--
-- Name: COLUMN "affiliate_link_observation"."valid_until"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."affiliate_link_observation"."valid_until" IS 'valid until';

--
-- Name: COLUMN "affiliate_link_observation"."source_snapshot_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."affiliate_link_observation"."source_snapshot_id" IS 'source snapshot id';

--
-- Name: COLUMN "affiliate_link_observation"."validation_status"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."affiliate_link_observation"."validation_status" IS 'validation status';

--
-- Name: COLUMN "affiliate_link_observation"."link_contract_version"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."affiliate_link_observation"."link_contract_version" IS 'link contract version';

--
-- Name: COLUMN "affiliate_link_observation"."created_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."affiliate_link_observation"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: attribute_definition; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."attribute_definition" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "category_id" "uuid",
    "attribute_code" "text" NOT NULL,
    "name" "text" NOT NULL,
    "data_type" "text" NOT NULL,
    "unit_family" "text",
    "is_comparable" boolean DEFAULT true NOT NULL,
    "is_required" boolean DEFAULT false NOT NULL,
    "normalization_rule_version" "text" NOT NULL,
    "status" "text" DEFAULT 'ACTIVE'::"text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "lock_version" bigint DEFAULT 0 NOT NULL,
    CONSTRAINT "ck_catalog_attribute_status" CHECK (("status" = ANY (ARRAY['ACTIVE'::"text", 'RETIRED'::"text"]))),
    CONSTRAINT "ck_catalog_attribute_type" CHECK (("data_type" = ANY (ARRAY['TEXT'::"text", 'NUMERIC'::"text", 'BOOLEAN'::"text", 'DATE'::"text", 'CODE'::"text"]))),
    CONSTRAINT "ck_catalog_attribute_version" CHECK (("lock_version" >= 0))
);

--
-- Name: TABLE "attribute_definition"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."attribute_definition" IS 'カテゴリ別の比較可能Attribute定義、型、単位、正規化Ruleを管理する。';

--
-- Name: COLUMN "attribute_definition"."id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."attribute_definition"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "attribute_definition"."category_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."attribute_definition"."category_id" IS '対象カテゴリ。';

--
-- Name: COLUMN "attribute_definition"."attribute_code"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."attribute_definition"."attribute_code" IS 'attribute code';

--
-- Name: COLUMN "attribute_definition"."name"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."attribute_definition"."name" IS 'name';

--
-- Name: COLUMN "attribute_definition"."data_type"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."attribute_definition"."data_type" IS 'data type';

--
-- Name: COLUMN "attribute_definition"."unit_family"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."attribute_definition"."unit_family" IS 'unit family';

--
-- Name: COLUMN "attribute_definition"."is_comparable"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."attribute_definition"."is_comparable" IS 'is comparable';

--
-- Name: COLUMN "attribute_definition"."is_required"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."attribute_definition"."is_required" IS 'is required';

--
-- Name: COLUMN "attribute_definition"."normalization_rule_version"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."attribute_definition"."normalization_rule_version" IS 'normalization rule version';

--
-- Name: COLUMN "attribute_definition"."status"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."attribute_definition"."status" IS '業務状態を示す安定Enum文字列。';

--
-- Name: COLUMN "attribute_definition"."created_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."attribute_definition"."created_at" IS 'レコード作成時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "attribute_definition"."updated_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."attribute_definition"."updated_at" IS '最終更新時刻。UTCのtimestamptz。';

--
-- Name: COLUMN "attribute_definition"."lock_version"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."attribute_definition"."lock_version" IS '楽観的排他制御用の単調増加Version。';

--
-- Name: availability_observation; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE "catalog"."availability_observation" (
    "id" "uuid" DEFAULT "uuidv7"() NOT NULL,
    "offer_id" "uuid" NOT NULL,
    "availability" "text" NOT NULL,
    "quantity" integer,
    "lead_time_text" "text",
    "observed_at" timestamp with time zone NOT NULL,
    "ingested_at" timestamp with time zone NOT NULL,
    "valid_until" timestamp with time zone,
    "source_snapshot_id" "uuid" NOT NULL,
    "validation_status" "text" NOT NULL,
    "confidence" numeric(5,4) NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT "ck_catalog_avail_conf" CHECK ((("confidence" >= (0)::numeric) AND ("confidence" <= (1)::numeric))),
    CONSTRAINT "ck_catalog_avail_qty" CHECK ((("quantity" IS NULL) OR ("quantity" >= 0))),
    CONSTRAINT "ck_catalog_avail_type" CHECK (("availability" = ANY (ARRAY['IN_STOCK'::"text", 'OUT_OF_STOCK'::"text", 'BACKORDER'::"text", 'PREORDER'::"text", 'DISCONTINUED'::"text", 'UNKNOWN'::"text"]))),
    CONSTRAINT "ck_catalog_avail_valid" CHECK ((("valid_until" IS NULL) OR ("valid_until" > "observed_at"))),
    CONSTRAINT "ck_catalog_avail_validation" CHECK (("validation_status" = ANY (ARRAY['VALID'::"text", 'SUSPECT'::"text", 'INVALID'::"text", 'CONFLICT'::"text"])))
);

--
-- Name: TABLE "availability_observation"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE "catalog"."availability_observation" IS '在庫・販売終了・Backorder等の時点事実を追記する。';

--
-- Name: COLUMN "availability_observation"."id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."availability_observation"."id" IS '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。';

--
-- Name: COLUMN "availability_observation"."offer_id"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."availability_observation"."offer_id" IS 'ショップ単位の販売Offer。';

--
-- Name: COLUMN "availability_observation"."availability"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."availability_observation"."availability" IS 'availability';

--
-- Name: COLUMN "availability_observation"."quantity"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."availability_observation"."quantity" IS 'quantity';

--
-- Name: COLUMN "availability_observation"."lead_time_text"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."availability_observation"."lead_time_text" IS 'lead time text';

--
-- Name: COLUMN "availability_observation"."observed_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."availability_observation"."observed_at" IS 'observed at';

--
-- Name: COLUMN "availability_observation"."ingested_at"; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN "catalog"."availability_observation"."ingested_at" IS 'ingested at';
