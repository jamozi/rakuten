-- ST-0304 physical translation fragment 10 of 11.
-- Source: approved RAOS data catalog plus finalized ST-0003/ST-0004 semantics.
-- Capture: PostgreSQL 18.4 pg_dump --schema-only --no-owner --no-privileges
--          --no-security-labels --quote-all-identifiers for the six owned schemas.
-- Schema creation/comments are rendered once by the ST-0304 generator. The 22
-- role-bound CREATE POLICY objects remain ST-0306-owned. ENABLE/FORCE RLS remains.

--
-- Name: evaluation_result fk_ai_eval_result_judge_route; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_result"
    ADD CONSTRAINT "fk_ai_eval_result_judge_route" FOREIGN KEY ("judge_route_version_id") REFERENCES "ai"."model_route_version"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_result fk_ai_eval_result_judge_rubric; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_result"
    ADD CONSTRAINT "fk_ai_eval_result_judge_rubric" FOREIGN KEY ("judge_rubric_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_result fk_ai_eval_result_run; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_result"
    ADD CONSTRAINT "fk_ai_eval_result_run" FOREIGN KEY ("evaluation_run_id") REFERENCES "ai"."evaluation_run"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_run fk_ai_eval_run_baseline; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_run"
    ADD CONSTRAINT "fk_ai_eval_run_baseline" FOREIGN KEY ("baseline_evaluation_run_id") REFERENCES "ai"."evaluation_run"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_run fk_ai_eval_run_creator; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_run"
    ADD CONSTRAINT "fk_ai_eval_run_creator" FOREIGN KEY ("created_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_run fk_ai_eval_run_dataset; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_run"
    ADD CONSTRAINT "fk_ai_eval_run_dataset" FOREIGN KEY ("dataset_version_id") REFERENCES "ai"."evaluation_dataset_version"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_run fk_ai_eval_run_manifest; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_run"
    ADD CONSTRAINT "fk_ai_eval_run_manifest" FOREIGN KEY ("run_manifest_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_run fk_ai_eval_run_policy; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_run"
    ADD CONSTRAINT "fk_ai_eval_run_policy" FOREIGN KEY ("policy_bundle_version_id") REFERENCES "policy"."policy_bundle"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_run fk_ai_eval_run_prompt; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_run"
    ADD CONSTRAINT "fk_ai_eval_run_prompt" FOREIGN KEY ("prompt_version_id") REFERENCES "ai"."prompt_version"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_run fk_ai_eval_run_resolved_model; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_run"
    ADD CONSTRAINT "fk_ai_eval_run_resolved_model" FOREIGN KEY ("resolved_model_id") REFERENCES "ai"."model_definition"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_run fk_ai_eval_run_route; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_run"
    ADD CONSTRAINT "fk_ai_eval_run_route" FOREIGN KEY ("model_route_version_id") REFERENCES "ai"."model_route_version"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_run fk_ai_eval_run_schema; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_run"
    ADD CONSTRAINT "fk_ai_eval_run_schema" FOREIGN KEY ("output_schema_version_id") REFERENCES "ai"."output_schema_version"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_run fk_ai_eval_run_suite; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_run"
    ADD CONSTRAINT "fk_ai_eval_run_suite" FOREIGN KEY ("suite_id") REFERENCES "ai"."evaluation_suite"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_suite fk_ai_eval_suite_approver; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_suite"
    ADD CONSTRAINT "fk_ai_eval_suite_approver" FOREIGN KEY ("approved_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_suite fk_ai_eval_suite_rubric; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_suite"
    ADD CONSTRAINT "fk_ai_eval_suite_rubric" FOREIGN KEY ("rubric_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_suite fk_ai_eval_suite_task; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_suite"
    ADD CONSTRAINT "fk_ai_eval_suite_task" FOREIGN KEY ("task_definition_id") REFERENCES "ai"."task_definition"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_result fk_ai_evaluation_result_model_route_version_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_result"
    ADD CONSTRAINT "fk_ai_evaluation_result_model_route_version_id" FOREIGN KEY ("model_route_version_id") REFERENCES "ai"."model_route_version"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_result fk_ai_evaluation_result_prompt_version_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_result"
    ADD CONSTRAINT "fk_ai_evaluation_result_prompt_version_id" FOREIGN KEY ("prompt_version_id") REFERENCES "ai"."prompt_version"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_result fk_ai_evaluation_result_result_artifact_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_result"
    ADD CONSTRAINT "fk_ai_evaluation_result_result_artifact_id" FOREIGN KEY ("result_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_result fk_ai_evaluation_result_task_definition_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_result"
    ADD CONSTRAINT "fk_ai_evaluation_result_task_definition_id" FOREIGN KEY ("task_definition_id") REFERENCES "ai"."task_definition"("id") ON DELETE RESTRICT;

--
-- Name: human_evaluation fk_ai_human_eval_notes; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."human_evaluation"
    ADD CONSTRAINT "fk_ai_human_eval_notes" FOREIGN KEY ("notes_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: human_evaluation fk_ai_human_eval_result; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."human_evaluation"
    ADD CONSTRAINT "fk_ai_human_eval_result" FOREIGN KEY ("evaluation_case_result_id") REFERENCES "ai"."evaluation_case_result"("id") ON DELETE RESTRICT;

--
-- Name: human_evaluation fk_ai_human_eval_reviewer; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."human_evaluation"
    ADD CONSTRAINT "fk_ai_human_eval_reviewer" FOREIGN KEY ("reviewer_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: ai_job fk_ai_job_policy_bundle; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_job"
    ADD CONSTRAINT "fk_ai_job_policy_bundle" FOREIGN KEY ("policy_bundle_version_id") REFERENCES "policy"."policy_bundle"("id") ON DELETE RESTRICT;

--
-- Name: ai_job fk_ai_job_release_decision; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_job"
    ADD CONSTRAINT "fk_ai_job_release_decision" FOREIGN KEY ("release_decision_id") REFERENCES "ai"."release_decision"("id") ON DELETE RESTRICT;

--
-- Name: judge_calibration fk_ai_judge_cal_approver; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."judge_calibration"
    ADD CONSTRAINT "fk_ai_judge_cal_approver" FOREIGN KEY ("approved_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: judge_calibration fk_ai_judge_cal_dataset; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."judge_calibration"
    ADD CONSTRAINT "fk_ai_judge_cal_dataset" FOREIGN KEY ("dataset_version_id") REFERENCES "ai"."evaluation_dataset_version"("id") ON DELETE RESTRICT;

--
-- Name: judge_calibration fk_ai_judge_cal_model; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."judge_calibration"
    ADD CONSTRAINT "fk_ai_judge_cal_model" FOREIGN KEY ("resolved_judge_model_id") REFERENCES "ai"."model_definition"("id") ON DELETE RESTRICT;

--
-- Name: judge_calibration fk_ai_judge_cal_prompt; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."judge_calibration"
    ADD CONSTRAINT "fk_ai_judge_cal_prompt" FOREIGN KEY ("judge_prompt_version_id") REFERENCES "ai"."prompt_version"("id") ON DELETE RESTRICT;

--
-- Name: judge_calibration fk_ai_judge_cal_report; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."judge_calibration"
    ADD CONSTRAINT "fk_ai_judge_cal_report" FOREIGN KEY ("report_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: judge_calibration fk_ai_judge_cal_route; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."judge_calibration"
    ADD CONSTRAINT "fk_ai_judge_cal_route" FOREIGN KEY ("judge_route_version_id") REFERENCES "ai"."model_route_version"("id") ON DELETE RESTRICT;

--
-- Name: judge_calibration fk_ai_judge_cal_rubric; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."judge_calibration"
    ADD CONSTRAINT "fk_ai_judge_cal_rubric" FOREIGN KEY ("rubric_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: judge_calibration fk_ai_judge_cal_task; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."judge_calibration"
    ADD CONSTRAINT "fk_ai_judge_cal_task" FOREIGN KEY ("evaluated_task_definition_id") REFERENCES "ai"."task_definition"("id") ON DELETE RESTRICT;

--
-- Name: model_route_version fk_ai_model_route_version_approved_by_principal_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."model_route_version"
    ADD CONSTRAINT "fk_ai_model_route_version_approved_by_principal_id" FOREIGN KEY ("approved_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: model_route_version fk_ai_model_route_version_fallback_model_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."model_route_version"
    ADD CONSTRAINT "fk_ai_model_route_version_fallback_model_id" FOREIGN KEY ("fallback_model_id") REFERENCES "ai"."model_definition"("id") ON DELETE RESTRICT;

--
-- Name: model_route_version fk_ai_model_route_version_primary_model_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."model_route_version"
    ADD CONSTRAINT "fk_ai_model_route_version_primary_model_id" FOREIGN KEY ("primary_model_id") REFERENCES "ai"."model_definition"("id") ON DELETE RESTRICT;

--
-- Name: model_route_version fk_ai_model_route_version_task_definition_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."model_route_version"
    ADD CONSTRAINT "fk_ai_model_route_version_task_definition_id" FOREIGN KEY ("task_definition_id") REFERENCES "ai"."task_definition"("id") ON DELETE RESTRICT;

--
-- Name: prompt_version fk_ai_prompt_author; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."prompt_version"
    ADD CONSTRAINT "fk_ai_prompt_author" FOREIGN KEY ("author_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: prompt_version fk_ai_prompt_version_approved_by_principal_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."prompt_version"
    ADD CONSTRAINT "fk_ai_prompt_version_approved_by_principal_id" FOREIGN KEY ("approved_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: prompt_version fk_ai_prompt_version_task_definition_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."prompt_version"
    ADD CONSTRAINT "fk_ai_prompt_version_task_definition_id" FOREIGN KEY ("task_definition_id") REFERENCES "ai"."task_definition"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_active_approval; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_active_approval" FOREIGN KEY ("active_approval_id") REFERENCES "ai"."release_approval"("id") ON DELETE RESTRICT;

--
-- Name: release_approval fk_ai_release_approval_artifact; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_approval"
    ADD CONSTRAINT "fk_ai_release_approval_artifact" FOREIGN KEY ("approval_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: release_approval fk_ai_release_approval_primary; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_approval"
    ADD CONSTRAINT "fk_ai_release_approval_primary" FOREIGN KEY ("primary_approver_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: release_approval fk_ai_release_approval_release; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_approval"
    ADD CONSTRAINT "fk_ai_release_approval_release" FOREIGN KEY ("release_decision_id") REFERENCES "ai"."release_decision"("id") ON DELETE RESTRICT;

--
-- Name: release_approval fk_ai_release_approval_second; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_approval"
    ADD CONSTRAINT "fk_ai_release_approval_second" FOREIGN KEY ("second_approver_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_approver; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_approver" FOREIGN KEY ("approved_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_canary_approval; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_canary_approval" FOREIGN KEY ("canary_approval_id") REFERENCES "ai"."release_approval"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_canary_evidence; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_canary_evidence" FOREIGN KEY ("canary_evidence_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_canary_monitor; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_canary_monitor" FOREIGN KEY ("canary_monitoring_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_dataset; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_dataset" FOREIGN KEY ("dataset_version_id") REFERENCES "ai"."evaluation_dataset_version"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_judge_cal; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_judge_cal" FOREIGN KEY ("judge_calibration_id") REFERENCES "ai"."judge_calibration"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_model; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_model" FOREIGN KEY ("resolved_model_id") REFERENCES "ai"."model_definition"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_policy; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_policy" FOREIGN KEY ("policy_bundle_version_id") REFERENCES "policy"."policy_bundle"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_prompt; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_prompt" FOREIGN KEY ("prompt_version_id") REFERENCES "ai"."prompt_version"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_revoker; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_revoker" FOREIGN KEY ("revoked_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_rollback; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_rollback" FOREIGN KEY ("rollback_release_decision_id") REFERENCES "ai"."release_decision"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_rollback_runbook; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_rollback_runbook" FOREIGN KEY ("rollback_runbook_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_route; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_route" FOREIGN KEY ("model_route_version_id") REFERENCES "ai"."model_route_version"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_run; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_run" FOREIGN KEY ("evaluation_run_id") REFERENCES "ai"."evaluation_run"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_schema; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_schema" FOREIGN KEY ("output_schema_version_id") REFERENCES "ai"."output_schema_version"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_second_approver; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_second_approver" FOREIGN KEY ("second_approver_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: release_decision fk_ai_release_task; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."release_decision"
    ADD CONSTRAINT "fk_ai_release_task" FOREIGN KEY ("task_definition_id") REFERENCES "ai"."task_definition"("id") ON DELETE RESTRICT;

--
-- Name: usage_cost fk_ai_usage_cost_ai_attempt_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."usage_cost"
    ADD CONSTRAINT "fk_ai_usage_cost_ai_attempt_id" FOREIGN KEY ("ai_attempt_id") REFERENCES "ai"."ai_attempt"("id") ON DELETE RESTRICT;

--
-- Name: affiliate_link_observation fk_catalog_affiliate_link_observation_offer_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."affiliate_link_observation"
    ADD CONSTRAINT "fk_catalog_affiliate_link_observation_offer_id" FOREIGN KEY ("offer_id") REFERENCES "catalog"."offer"("id") ON DELETE RESTRICT;

--
-- Name: affiliate_link_observation fk_catalog_affiliate_link_observation_source_snapshot_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."affiliate_link_observation"
    ADD CONSTRAINT "fk_catalog_affiliate_link_observation_source_snapshot_id" FOREIGN KEY ("source_snapshot_id") REFERENCES "evidence"."source_snapshot"("id") ON DELETE RESTRICT;

--
-- Name: attribute_definition fk_catalog_attribute_definition_category_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."attribute_definition"
    ADD CONSTRAINT "fk_catalog_attribute_definition_category_id" FOREIGN KEY ("category_id") REFERENCES "portfolio"."category"("id") ON DELETE RESTRICT;

--
-- Name: availability_observation fk_catalog_availability_observation_offer_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."availability_observation"
    ADD CONSTRAINT "fk_catalog_availability_observation_offer_id" FOREIGN KEY ("offer_id") REFERENCES "catalog"."offer"("id") ON DELETE RESTRICT;

--
-- Name: availability_observation fk_catalog_availability_observation_source_snapshot_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."availability_observation"
    ADD CONSTRAINT "fk_catalog_availability_observation_source_snapshot_id" FOREIGN KEY ("source_snapshot_id") REFERENCES "evidence"."source_snapshot"("id") ON DELETE RESTRICT;

--
-- Name: canonical_product fk_catalog_canonical_product_category_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."canonical_product"
    ADD CONSTRAINT "fk_catalog_canonical_product_category_id" FOREIGN KEY ("category_id") REFERENCES "portfolio"."category"("id") ON DELETE RESTRICT;

--
-- Name: canonical_product fk_catalog_canonical_product_merged_into_product_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."canonical_product"
    ADD CONSTRAINT "fk_catalog_canonical_product_merged_into_product_id" FOREIGN KEY ("merged_into_product_id") REFERENCES "catalog"."canonical_product"("id") ON DELETE RESTRICT;

--
-- Name: category_genre_mapping fk_catalog_category_genre_mapping_category_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."category_genre_mapping"
    ADD CONSTRAINT "fk_catalog_category_genre_mapping_category_id" FOREIGN KEY ("category_id") REFERENCES "portfolio"."category"("id") ON DELETE RESTRICT;

--
-- Name: category_genre_mapping fk_catalog_category_genre_mapping_decided_by_principal_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."category_genre_mapping"
    ADD CONSTRAINT "fk_catalog_category_genre_mapping_decided_by_principal_id" FOREIGN KEY ("decided_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: category_genre_mapping fk_catalog_category_genre_mapping_rakuten_genre_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."category_genre_mapping"
    ADD CONSTRAINT "fk_catalog_category_genre_mapping_rakuten_genre_id" FOREIGN KEY ("rakuten_genre_id") REFERENCES "catalog"."rakuten_genre"("id") ON DELETE RESTRICT;

--
-- Name: grouping_decision fk_catalog_grouping_decision_product_candidate_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."grouping_decision"
    ADD CONSTRAINT "fk_catalog_grouping_decision_product_candidate_id" FOREIGN KEY ("product_candidate_id") REFERENCES "catalog"."product_candidate"("id") ON DELETE RESTRICT;

--
-- Name: grouping_decision fk_catalog_grouping_decision_proposed_product_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."grouping_decision"
    ADD CONSTRAINT "fk_catalog_grouping_decision_proposed_product_id" FOREIGN KEY ("proposed_product_id") REFERENCES "catalog"."canonical_product"("id") ON DELETE RESTRICT;

--
-- Name: grouping_decision fk_catalog_grouping_decision_supersedes_decision_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."grouping_decision"
    ADD CONSTRAINT "fk_catalog_grouping_decision_supersedes_decision_id" FOREIGN KEY ("supersedes_decision_id") REFERENCES "catalog"."grouping_decision"("id") ON DELETE SET NULL;

--
-- Name: ingestion_request fk_catalog_ingestion_request_job_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."ingestion_request"
    ADD CONSTRAINT "fk_catalog_ingestion_request_job_id" FOREIGN KEY ("job_id") REFERENCES "ops"."job"("id") ON DELETE RESTRICT;

--
-- Name: ingestion_request fk_catalog_ingestion_request_provider_endpoint_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."ingestion_request"
    ADD CONSTRAINT "fk_catalog_ingestion_request_provider_endpoint_id" FOREIGN KEY ("provider_endpoint_id") REFERENCES "catalog"."provider_endpoint"("id") ON DELETE RESTRICT;

--
-- Name: ingestion_request fk_catalog_ingestion_request_raw_response_artifact_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."ingestion_request"
    ADD CONSTRAINT "fk_catalog_ingestion_request_raw_response_artifact_id" FOREIGN KEY ("raw_response_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: offer_current_projection fk_catalog_offer_current_projection_affiliate_link_o_c2329b301d; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."offer_current_projection"
    ADD CONSTRAINT "fk_catalog_offer_current_projection_affiliate_link_o_c2329b301d" FOREIGN KEY ("affiliate_link_observation_id") REFERENCES "catalog"."affiliate_link_observation"("id") ON DELETE RESTRICT;

--
-- Name: offer_current_projection fk_catalog_offer_current_projection_availability_observation_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."offer_current_projection"
    ADD CONSTRAINT "fk_catalog_offer_current_projection_availability_observation_id" FOREIGN KEY ("availability_observation_id") REFERENCES "catalog"."availability_observation"("id") ON DELETE RESTRICT;

--
-- Name: offer_current_projection fk_catalog_offer_current_projection_offer_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."offer_current_projection"
    ADD CONSTRAINT "fk_catalog_offer_current_projection_offer_id" FOREIGN KEY ("offer_id") REFERENCES "catalog"."offer"("id") ON DELETE RESTRICT;

--
-- Name: offer_current_projection fk_catalog_offer_current_projection_price_observation_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."offer_current_projection"
    ADD CONSTRAINT "fk_catalog_offer_current_projection_price_observation_id" FOREIGN KEY ("price_observation_id") REFERENCES "catalog"."price_observation"("id") ON DELETE RESTRICT;

--
-- Name: offer_current_projection fk_catalog_offer_current_projection_product_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."offer_current_projection"
    ADD CONSTRAINT "fk_catalog_offer_current_projection_product_id" FOREIGN KEY ("product_id") REFERENCES "catalog"."canonical_product"("id") ON DELETE RESTRICT;

--
-- Name: offer_current_projection fk_catalog_offer_current_projection_review_observation_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."offer_current_projection"
    ADD CONSTRAINT "fk_catalog_offer_current_projection_review_observation_id" FOREIGN KEY ("review_observation_id") REFERENCES "catalog"."review_aggregate_observation"("id") ON DELETE RESTRICT;

--
-- Name: offer fk_catalog_offer_product_candidate_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."offer"
    ADD CONSTRAINT "fk_catalog_offer_product_candidate_id" FOREIGN KEY ("product_candidate_id") REFERENCES "catalog"."product_candidate"("id") ON DELETE RESTRICT;

--
-- Name: offer fk_catalog_offer_product_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."offer"
    ADD CONSTRAINT "fk_catalog_offer_product_id" FOREIGN KEY ("product_id") REFERENCES "catalog"."canonical_product"("id") ON DELETE RESTRICT;

--
-- Name: offer fk_catalog_offer_provider_endpoint_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."offer"
    ADD CONSTRAINT "fk_catalog_offer_provider_endpoint_id" FOREIGN KEY ("provider_endpoint_id") REFERENCES "catalog"."provider_endpoint"("id") ON DELETE RESTRICT;

--
-- Name: offer fk_catalog_offer_shop_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."offer"
    ADD CONSTRAINT "fk_catalog_offer_shop_id" FOREIGN KEY ("shop_id") REFERENCES "catalog"."shop"("id") ON DELETE RESTRICT;

--
-- Name: price_observation fk_catalog_price_observation_offer_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."price_observation"
    ADD CONSTRAINT "fk_catalog_price_observation_offer_id" FOREIGN KEY ("offer_id") REFERENCES "catalog"."offer"("id") ON DELETE RESTRICT;

--
-- Name: price_observation fk_catalog_price_observation_source_snapshot_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."price_observation"
    ADD CONSTRAINT "fk_catalog_price_observation_source_snapshot_id" FOREIGN KEY ("source_snapshot_id") REFERENCES "evidence"."source_snapshot"("id") ON DELETE RESTRICT;

--
-- Name: product_attribute_value fk_catalog_product_attribute_value_attribute_definition_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_attribute_value"
    ADD CONSTRAINT "fk_catalog_product_attribute_value_attribute_definition_id" FOREIGN KEY ("attribute_definition_id") REFERENCES "catalog"."attribute_definition"("id") ON DELETE RESTRICT;

--
-- Name: product_attribute_value fk_catalog_product_attribute_value_product_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_attribute_value"
    ADD CONSTRAINT "fk_catalog_product_attribute_value_product_id" FOREIGN KEY ("product_id") REFERENCES "catalog"."canonical_product"("id") ON DELETE RESTRICT;

--
-- Name: product_attribute_value fk_catalog_product_attribute_value_source_fact_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_attribute_value"
    ADD CONSTRAINT "fk_catalog_product_attribute_value_source_fact_id" FOREIGN KEY ("source_fact_id") REFERENCES "evidence"."fact"("id") ON DELETE RESTRICT;

--
-- Name: product_candidate fk_catalog_product_candidate_provider_endpoint_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_candidate"
    ADD CONSTRAINT "fk_catalog_product_candidate_provider_endpoint_id" FOREIGN KEY ("provider_endpoint_id") REFERENCES "catalog"."provider_endpoint"("id") ON DELETE RESTRICT;

--
-- Name: product_candidate fk_catalog_product_candidate_rakuten_genre_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_candidate"
    ADD CONSTRAINT "fk_catalog_product_candidate_rakuten_genre_id" FOREIGN KEY ("rakuten_genre_id") REFERENCES "catalog"."rakuten_genre"("id") ON DELETE RESTRICT;

--
-- Name: product_candidate fk_catalog_product_candidate_shop_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_candidate"
    ADD CONSTRAINT "fk_catalog_product_candidate_shop_id" FOREIGN KEY ("shop_id") REFERENCES "catalog"."shop"("id") ON DELETE RESTRICT;

--
-- Name: product_candidate fk_catalog_product_candidate_source_snapshot_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_candidate"
    ADD CONSTRAINT "fk_catalog_product_candidate_source_snapshot_id" FOREIGN KEY ("source_snapshot_id") REFERENCES "evidence"."source_snapshot"("id") ON DELETE RESTRICT;

--
-- Name: product_group_membership fk_catalog_product_group_membership_grouping_decision_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_group_membership"
    ADD CONSTRAINT "fk_catalog_product_group_membership_grouping_decision_id" FOREIGN KEY ("grouping_decision_id") REFERENCES "catalog"."grouping_decision"("id") ON DELETE RESTRICT;

--
-- Name: product_group_membership fk_catalog_product_group_membership_product_candidate_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_group_membership"
    ADD CONSTRAINT "fk_catalog_product_group_membership_product_candidate_id" FOREIGN KEY ("product_candidate_id") REFERENCES "catalog"."product_candidate"("id") ON DELETE RESTRICT;

--
-- Name: product_group_membership fk_catalog_product_group_membership_product_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_group_membership"
    ADD CONSTRAINT "fk_catalog_product_group_membership_product_id" FOREIGN KEY ("product_id") REFERENCES "catalog"."canonical_product"("id") ON DELETE RESTRICT;

--
-- Name: product_relation fk_catalog_product_relation_from_product_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_relation"
    ADD CONSTRAINT "fk_catalog_product_relation_from_product_id" FOREIGN KEY ("from_product_id") REFERENCES "catalog"."canonical_product"("id") ON DELETE RESTRICT;

--
-- Name: product_relation fk_catalog_product_relation_source_fact_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_relation"
    ADD CONSTRAINT "fk_catalog_product_relation_source_fact_id" FOREIGN KEY ("source_fact_id") REFERENCES "evidence"."fact"("id") ON DELETE RESTRICT;

--
-- Name: product_relation fk_catalog_product_relation_to_product_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."product_relation"
    ADD CONSTRAINT "fk_catalog_product_relation_to_product_id" FOREIGN KEY ("to_product_id") REFERENCES "catalog"."canonical_product"("id") ON DELETE RESTRICT;

--
-- Name: rakuten_genre fk_catalog_rakuten_genre_provider_endpoint_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."rakuten_genre"
    ADD CONSTRAINT "fk_catalog_rakuten_genre_provider_endpoint_id" FOREIGN KEY ("provider_endpoint_id") REFERENCES "catalog"."provider_endpoint"("id") ON DELETE RESTRICT;

--
-- Name: rakuten_genre fk_catalog_rakuten_genre_source_snapshot_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."rakuten_genre"
    ADD CONSTRAINT "fk_catalog_rakuten_genre_source_snapshot_id" FOREIGN KEY ("source_snapshot_id") REFERENCES "evidence"."source_snapshot"("id") ON DELETE RESTRICT;

--
-- Name: review_aggregate_observation fk_catalog_review_aggregate_observation_offer_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."review_aggregate_observation"
    ADD CONSTRAINT "fk_catalog_review_aggregate_observation_offer_id" FOREIGN KEY ("offer_id") REFERENCES "catalog"."offer"("id") ON DELETE RESTRICT;

--
-- Name: review_aggregate_observation fk_catalog_review_aggregate_observation_source_snapshot_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."review_aggregate_observation"
    ADD CONSTRAINT "fk_catalog_review_aggregate_observation_source_snapshot_id" FOREIGN KEY ("source_snapshot_id") REFERENCES "evidence"."source_snapshot"("id") ON DELETE RESTRICT;

--
-- Name: shop fk_catalog_shop_provider_endpoint_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."shop"
    ADD CONSTRAINT "fk_catalog_shop_provider_endpoint_id" FOREIGN KEY ("provider_endpoint_id") REFERENCES "catalog"."provider_endpoint"("id") ON DELETE RESTRICT;

--
-- Name: shop fk_catalog_shop_source_snapshot_id; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY "catalog"."shop"
    ADD CONSTRAINT "fk_catalog_shop_source_snapshot_id" FOREIGN KEY ("source_snapshot_id") REFERENCES "evidence"."source_snapshot"("id") ON DELETE RESTRICT;

--
-- Name: article fk_editorial_article_article_plan_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article"
    ADD CONSTRAINT "fk_editorial_article_article_plan_id" FOREIGN KEY ("article_plan_id") REFERENCES "editorial"."article_plan"("id") ON DELETE RESTRICT;

--
-- Name: article_block fk_editorial_article_block_article_version_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_block"
    ADD CONSTRAINT "fk_editorial_article_block_article_version_id" FOREIGN KEY ("article_version_id") REFERENCES "editorial"."article_version"("id") ON DELETE RESTRICT;

--
-- Name: article_block_product fk_editorial_article_block_product_article_block_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_block_product"
    ADD CONSTRAINT "fk_editorial_article_block_product_article_block_id" FOREIGN KEY ("article_block_id") REFERENCES "editorial"."article_block"("id") ON DELETE RESTRICT;

--
-- Name: article_block_product fk_editorial_article_block_product_offer_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_block_product"
    ADD CONSTRAINT "fk_editorial_article_block_product_offer_id" FOREIGN KEY ("offer_id") REFERENCES "catalog"."offer"("id") ON DELETE RESTRICT;

--
-- Name: article_block_product fk_editorial_article_block_product_product_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_block_product"
    ADD CONSTRAINT "fk_editorial_article_block_product_product_id" FOREIGN KEY ("product_id") REFERENCES "catalog"."canonical_product"("id") ON DELETE RESTRICT;

--
-- Name: article fk_editorial_article_current_version_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article"
    ADD CONSTRAINT "fk_editorial_article_current_version_id" FOREIGN KEY ("current_version_id") REFERENCES "editorial"."article_version"("id") DEFERRABLE INITIALLY DEFERRED;

--
-- Name: article_disclosure_context fk_editorial_article_disclosure_article; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_disclosure_context"
    ADD CONSTRAINT "fk_editorial_article_disclosure_article" FOREIGN KEY ("article_version_id") REFERENCES "editorial"."article_version"("id") ON DELETE RESTRICT;

--
-- Name: article_disclosure_context fk_editorial_article_disclosure_reviewer; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_disclosure_context"
    ADD CONSTRAINT "fk_editorial_article_disclosure_reviewer" FOREIGN KEY ("reviewed_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: article_link fk_editorial_article_link_from_article_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_link"
    ADD CONSTRAINT "fk_editorial_article_link_from_article_id" FOREIGN KEY ("from_article_id") REFERENCES "editorial"."article"("id") ON DELETE RESTRICT;

--
-- Name: article_link fk_editorial_article_link_to_article_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_link"
    ADD CONSTRAINT "fk_editorial_article_link_to_article_id" FOREIGN KEY ("to_article_id") REFERENCES "editorial"."article"("id") ON DELETE RESTRICT;

--
-- Name: article_methodology_binding fk_editorial_article_methodology_article; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_methodology_binding"
    ADD CONSTRAINT "fk_editorial_article_methodology_article" FOREIGN KEY ("article_version_id") REFERENCES "editorial"."article_version"("id") ON DELETE RESTRICT;

--
-- Name: article_methodology_binding fk_editorial_article_methodology_binder; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_methodology_binding"
    ADD CONSTRAINT "fk_editorial_article_methodology_binder" FOREIGN KEY ("bound_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: article_methodology_binding fk_editorial_article_methodology_candidate; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_methodology_binding"
    ADD CONSTRAINT "fk_editorial_article_methodology_candidate" FOREIGN KEY ("candidate_universe_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: article_methodology_binding fk_editorial_article_methodology_version; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_methodology_binding"
    ADD CONSTRAINT "fk_editorial_article_methodology_version" FOREIGN KEY ("methodology_version_id") REFERENCES "editorial"."editorial_methodology_version"("id") ON DELETE RESTRICT;

--
-- Name: article_plan fk_editorial_article_plan_approved_by_principal_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_plan"
    ADD CONSTRAINT "fk_editorial_article_plan_approved_by_principal_id" FOREIGN KEY ("approved_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: article_plan fk_editorial_article_plan_category_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_plan"
    ADD CONSTRAINT "fk_editorial_article_plan_category_id" FOREIGN KEY ("category_id") REFERENCES "portfolio"."category"("id") ON DELETE RESTRICT;

--
-- Name: article_plan fk_editorial_article_plan_created_by_principal_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_plan"
    ADD CONSTRAINT "fk_editorial_article_plan_created_by_principal_id" FOREIGN KEY ("created_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: article_plan fk_editorial_article_plan_intent_cluster_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_plan"
    ADD CONSTRAINT "fk_editorial_article_plan_intent_cluster_id" FOREIGN KEY ("intent_cluster_id") REFERENCES "portfolio"."intent_cluster"("id") ON DELETE RESTRICT;

--
-- Name: article_plan fk_editorial_article_plan_opportunity_assessment_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_plan"
    ADD CONSTRAINT "fk_editorial_article_plan_opportunity_assessment_id" FOREIGN KEY ("opportunity_assessment_id") REFERENCES "portfolio"."opportunity_assessment"("id") ON DELETE RESTRICT;

--
-- Name: article_plan fk_editorial_article_plan_primary_keyword_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_plan"
    ADD CONSTRAINT "fk_editorial_article_plan_primary_keyword_id" FOREIGN KEY ("primary_keyword_id") REFERENCES "portfolio"."keyword"("id") ON DELETE RESTRICT;

--
-- Name: article_plan fk_editorial_article_plan_site_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_plan"
    ADD CONSTRAINT "fk_editorial_article_plan_site_id" FOREIGN KEY ("site_id") REFERENCES "portfolio"."site"("id") ON DELETE RESTRICT;

--
-- Name: article fk_editorial_article_published_version_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article"
    ADD CONSTRAINT "fk_editorial_article_published_version_id" FOREIGN KEY ("published_version_id") REFERENCES "editorial"."article_version"("id") DEFERRABLE INITIALLY DEFERRED;

--
-- Name: article fk_editorial_article_site_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article"
    ADD CONSTRAINT "fk_editorial_article_site_id" FOREIGN KEY ("site_id") REFERENCES "portfolio"."site"("id") ON DELETE RESTRICT;

--
-- Name: article_slug fk_editorial_article_slug_article_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_slug"
    ADD CONSTRAINT "fk_editorial_article_slug_article_id" FOREIGN KEY ("article_id") REFERENCES "editorial"."article"("id") ON DELETE RESTRICT;

--
-- Name: article_slug fk_editorial_article_slug_site_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_slug"
    ADD CONSTRAINT "fk_editorial_article_slug_site_id" FOREIGN KEY ("site_id") REFERENCES "portfolio"."site"("id") ON DELETE RESTRICT;

--
-- Name: article_template_version fk_editorial_article_template_approver; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_template_version"
    ADD CONSTRAINT "fk_editorial_article_template_approver" FOREIGN KEY ("approved_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: article_template_version fk_editorial_article_template_type; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_template_version"
    ADD CONSTRAINT "fk_editorial_article_template_type" FOREIGN KEY ("article_type_version_id") REFERENCES "editorial"."article_type_version"("id") ON DELETE RESTRICT;

--
-- Name: article_type_version fk_editorial_article_type_approver; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_type_version"
    ADD CONSTRAINT "fk_editorial_article_type_approver" FOREIGN KEY ("approved_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: article_version fk_editorial_article_version_ai_job_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_version"
    ADD CONSTRAINT "fk_editorial_article_version_ai_job_id" FOREIGN KEY ("ai_job_id") REFERENCES "ai"."ai_job"("id") ON DELETE RESTRICT;

--
-- Name: article_version fk_editorial_article_version_article_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_version"
    ADD CONSTRAINT "fk_editorial_article_version_article_id" FOREIGN KEY ("article_id") REFERENCES "editorial"."article"("id") DEFERRABLE INITIALLY DEFERRED;

--
-- Name: article_version fk_editorial_article_version_article_template; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_version"
    ADD CONSTRAINT "fk_editorial_article_version_article_template" FOREIGN KEY ("article_template_version_id") REFERENCES "editorial"."article_template_version"("id") ON DELETE RESTRICT;

--
-- Name: article_version fk_editorial_article_version_article_type; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_version"
    ADD CONSTRAINT "fk_editorial_article_version_article_type" FOREIGN KEY ("article_type_version_id") REFERENCES "editorial"."article_type_version"("id") ON DELETE RESTRICT;

--
-- Name: article_version fk_editorial_article_version_based_on_version_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_version"
    ADD CONSTRAINT "fk_editorial_article_version_based_on_version_id" FOREIGN KEY ("based_on_version_id") REFERENCES "editorial"."article_version"("id") ON DELETE RESTRICT;

--
-- Name: article_version fk_editorial_article_version_content_schema; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_version"
    ADD CONSTRAINT "fk_editorial_article_version_content_schema" FOREIGN KEY ("content_schema_version_id") REFERENCES "editorial"."content_schema_version"("id") ON DELETE RESTRICT;

--
-- Name: article_version fk_editorial_article_version_seo; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_version"
    ADD CONSTRAINT "fk_editorial_article_version_seo" FOREIGN KEY ("seo_metadata_version_id", "id") REFERENCES "editorial"."seo_metadata_version"("id", "article_version_id") ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

--
-- Name: article_version fk_editorial_article_version_source_packet_version_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."article_version"
    ADD CONSTRAINT "fk_editorial_article_version_source_packet_version_id" FOREIGN KEY ("source_packet_version_id") REFERENCES "evidence"."source_packet_version"("id") ON DELETE RESTRICT;

--
-- Name: comparison_axis fk_editorial_comparison_axis_article_version_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."comparison_axis"
    ADD CONSTRAINT "fk_editorial_comparison_axis_article_version_id" FOREIGN KEY ("article_version_id") REFERENCES "editorial"."article_version"("id") ON DELETE RESTRICT;

--
-- Name: comparison_value fk_editorial_comparison_value_comparison_axis_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."comparison_value"
    ADD CONSTRAINT "fk_editorial_comparison_value_comparison_axis_id" FOREIGN KEY ("comparison_axis_id") REFERENCES "editorial"."comparison_axis"("id") ON DELETE RESTRICT;

--
-- Name: comparison_value fk_editorial_comparison_value_product_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."comparison_value"
    ADD CONSTRAINT "fk_editorial_comparison_value_product_id" FOREIGN KEY ("product_id") REFERENCES "catalog"."canonical_product"("id") ON DELETE RESTRICT;

--
-- Name: comparison_value fk_editorial_comparison_value_source_fact_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."comparison_value"
    ADD CONSTRAINT "fk_editorial_comparison_value_source_fact_id" FOREIGN KEY ("source_fact_id") REFERENCES "evidence"."fact"("id") ON DELETE RESTRICT;

--
-- Name: content_schema_version fk_editorial_content_schema_approver; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."content_schema_version"
    ADD CONSTRAINT "fk_editorial_content_schema_approver" FOREIGN KEY ("approved_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: content_schema_version fk_editorial_content_schema_artifact; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."content_schema_version"
    ADD CONSTRAINT "fk_editorial_content_schema_artifact" FOREIGN KEY ("artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: media_asset fk_editorial_media_asset_approver; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."media_asset"
    ADD CONSTRAINT "fk_editorial_media_asset_approver" FOREIGN KEY ("approved_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: media_asset fk_editorial_media_asset_long_description; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."media_asset"
    ADD CONSTRAINT "fk_editorial_media_asset_long_description" FOREIGN KEY ("long_description_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: media_asset fk_editorial_media_asset_raw; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."media_asset"
    ADD CONSTRAINT "fk_editorial_media_asset_raw" FOREIGN KEY ("raw_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: media_asset fk_editorial_media_asset_source; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."media_asset"
    ADD CONSTRAINT "fk_editorial_media_asset_source" FOREIGN KEY ("source_id") REFERENCES "evidence"."source"("id") ON DELETE RESTRICT;

--
-- Name: editorial_methodology_version fk_editorial_methodology_approver; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."editorial_methodology_version"
    ADD CONSTRAINT "fk_editorial_methodology_approver" FOREIGN KEY ("approved_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: editorial_methodology_version fk_editorial_methodology_article_type; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."editorial_methodology_version"
    ADD CONSTRAINT "fk_editorial_methodology_article_type" FOREIGN KEY ("article_type_version_id", "article_type_code") REFERENCES "editorial"."article_type_version"("id", "article_type_code") ON DELETE RESTRICT;

--
-- Name: recommendation fk_editorial_recommendation_product_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."recommendation"
    ADD CONSTRAINT "fk_editorial_recommendation_product_id" FOREIGN KEY ("product_id") REFERENCES "catalog"."canonical_product"("id") ON DELETE RESTRICT;

--
-- Name: recommendation_rationale fk_editorial_recommendation_rationale_claim_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."recommendation_rationale"
    ADD CONSTRAINT "fk_editorial_recommendation_rationale_claim_id" FOREIGN KEY ("claim_id") REFERENCES "evidence"."claim"("id") ON DELETE RESTRICT;

--
-- Name: recommendation_rationale fk_editorial_recommendation_rationale_recommendation_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."recommendation_rationale"
    ADD CONSTRAINT "fk_editorial_recommendation_rationale_recommendation_id" FOREIGN KEY ("recommendation_id") REFERENCES "editorial"."recommendation"("id") ON DELETE RESTRICT;

--
-- Name: recommendation_rationale fk_editorial_recommendation_rationale_source_fact_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."recommendation_rationale"
    ADD CONSTRAINT "fk_editorial_recommendation_rationale_source_fact_id" FOREIGN KEY ("source_fact_id") REFERENCES "evidence"."fact"("id") ON DELETE RESTRICT;

--
-- Name: recommendation fk_editorial_recommendation_recommendation_set_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."recommendation"
    ADD CONSTRAINT "fk_editorial_recommendation_recommendation_set_id" FOREIGN KEY ("recommendation_set_id") REFERENCES "editorial"."recommendation_set"("id") ON DELETE RESTRICT;

--
-- Name: recommendation_set fk_editorial_recommendation_set_article_version_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."recommendation_set"
    ADD CONSTRAINT "fk_editorial_recommendation_set_article_version_id" FOREIGN KEY ("article_version_id") REFERENCES "editorial"."article_version"("id") ON DELETE RESTRICT;

--
-- Name: review_comment fk_editorial_review_comment_article_block_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."review_comment"
    ADD CONSTRAINT "fk_editorial_review_comment_article_block_id" FOREIGN KEY ("article_block_id") REFERENCES "editorial"."article_block"("id") ON DELETE RESTRICT;

--
-- Name: review_comment fk_editorial_review_comment_article_version_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."review_comment"
    ADD CONSTRAINT "fk_editorial_review_comment_article_version_id" FOREIGN KEY ("article_version_id") REFERENCES "editorial"."article_version"("id") ON DELETE RESTRICT;

--
-- Name: review_comment fk_editorial_review_comment_author_principal_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."review_comment"
    ADD CONSTRAINT "fk_editorial_review_comment_author_principal_id" FOREIGN KEY ("author_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: review_comment fk_editorial_review_comment_claim_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."review_comment"
    ADD CONSTRAINT "fk_editorial_review_comment_claim_id" FOREIGN KEY ("claim_id") REFERENCES "evidence"."claim"("id") ON DELETE RESTRICT;

--
-- Name: review_comment fk_editorial_review_comment_parent_comment_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."review_comment"
    ADD CONSTRAINT "fk_editorial_review_comment_parent_comment_id" FOREIGN KEY ("parent_comment_id") REFERENCES "editorial"."review_comment"("id") ON DELETE RESTRICT;

--
-- Name: review_comment fk_editorial_review_comment_resolved_by_principal_id; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."review_comment"
    ADD CONSTRAINT "fk_editorial_review_comment_resolved_by_principal_id" FOREIGN KEY ("resolved_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: seo_metadata_version fk_editorial_seo_approver; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."seo_metadata_version"
    ADD CONSTRAINT "fk_editorial_seo_approver" FOREIGN KEY ("approved_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: seo_metadata_version fk_editorial_seo_article; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."seo_metadata_version"
    ADD CONSTRAINT "fk_editorial_seo_article" FOREIGN KEY ("article_version_id") REFERENCES "editorial"."article_version"("id") ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

--
-- Name: structured_data_manifest fk_editorial_structured_data_jsonld_artifact; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."structured_data_manifest"
    ADD CONSTRAINT "fk_editorial_structured_data_jsonld_artifact" FOREIGN KEY ("jsonld_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: structured_data_manifest fk_editorial_structured_data_seo_article; Type: FK CONSTRAINT; Schema: editorial; Owner: -
--

ALTER TABLE ONLY "editorial"."structured_data_manifest"
    ADD CONSTRAINT "fk_editorial_structured_data_seo_article" FOREIGN KEY ("seo_metadata_version_id", "article_version_id") REFERENCES "editorial"."seo_metadata_version"("id", "article_version_id") ON DELETE RESTRICT;

--
-- Name: claim fk_evidence_claim_article_version_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."claim"
    ADD CONSTRAINT "fk_evidence_claim_article_version_id" FOREIGN KEY ("article_version_id") REFERENCES "editorial"."article_version"("id") ON DELETE RESTRICT;

--
-- Name: claim fk_evidence_claim_block_id_article_version_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."claim"
    ADD CONSTRAINT "fk_evidence_claim_block_id_article_version_id" FOREIGN KEY ("block_id", "article_version_id") REFERENCES "editorial"."article_block"("id", "article_version_id") ON DELETE RESTRICT;

--
-- Name: claim_evidence_link fk_evidence_claim_evidence_link_claim_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."claim_evidence_link"
    ADD CONSTRAINT "fk_evidence_claim_evidence_link_claim_id" FOREIGN KEY ("claim_id") REFERENCES "evidence"."claim"("id") ON DELETE RESTRICT;

--
-- Name: claim_evidence_link fk_evidence_claim_evidence_link_fact_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."claim_evidence_link"
    ADD CONSTRAINT "fk_evidence_claim_evidence_link_fact_id" FOREIGN KEY ("fact_id") REFERENCES "evidence"."fact"("id") ON DELETE RESTRICT;

--
-- Name: claim fk_evidence_claim_generated_by_ai_attempt_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."claim"
    ADD CONSTRAINT "fk_evidence_claim_generated_by_ai_attempt_id" FOREIGN KEY ("generated_by_ai_attempt_id") REFERENCES "ai"."ai_attempt"("id") ON DELETE RESTRICT;

--
-- Name: fact_derivation fk_evidence_fact_derivation_derived_fact_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."fact_derivation"
    ADD CONSTRAINT "fk_evidence_fact_derivation_derived_fact_id" FOREIGN KEY ("derived_fact_id") REFERENCES "evidence"."fact"("id") ON DELETE RESTRICT;

--
-- Name: fact_derivation fk_evidence_fact_derivation_input_fact_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."fact_derivation"
    ADD CONSTRAINT "fk_evidence_fact_derivation_input_fact_id" FOREIGN KEY ("input_fact_id") REFERENCES "evidence"."fact"("id") ON DELETE RESTRICT;

--
-- Name: fact fk_evidence_fact_source_snapshot_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."fact"
    ADD CONSTRAINT "fk_evidence_fact_source_snapshot_id" FOREIGN KEY ("source_snapshot_id") REFERENCES "evidence"."source_snapshot"("id") ON DELETE RESTRICT;

--
-- Name: first_hand_experience_asset fk_evidence_first_hand_asset_artifact; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."first_hand_experience_asset"
    ADD CONSTRAINT "fk_evidence_first_hand_asset_artifact" FOREIGN KEY ("artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: first_hand_experience_asset fk_evidence_first_hand_asset_record; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."first_hand_experience_asset"
    ADD CONSTRAINT "fk_evidence_first_hand_asset_record" FOREIGN KEY ("experience_record_id") REFERENCES "evidence"."first_hand_experience_record"("id") ON DELETE RESTRICT;

--
-- Name: first_hand_experience_record fk_evidence_first_hand_product; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."first_hand_experience_record"
    ADD CONSTRAINT "fk_evidence_first_hand_product" FOREIGN KEY ("product_id") REFERENCES "catalog"."canonical_product"("id") ON DELETE RESTRICT;

--
-- Name: first_hand_experience_record fk_evidence_first_hand_reviewer; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."first_hand_experience_record"
    ADD CONSTRAINT "fk_evidence_first_hand_reviewer" FOREIGN KEY ("reviewed_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: first_hand_experience_record fk_evidence_first_hand_tester; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."first_hand_experience_record"
    ADD CONSTRAINT "fk_evidence_first_hand_tester" FOREIGN KEY ("tester_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: source_packet fk_evidence_source_packet_article_plan_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet"
    ADD CONSTRAINT "fk_evidence_source_packet_article_plan_id" FOREIGN KEY ("article_plan_id") REFERENCES "editorial"."article_plan"("id") ON DELETE RESTRICT;

--
-- Name: source_packet_fact fk_evidence_source_packet_fact_fact_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet_fact"
    ADD CONSTRAINT "fk_evidence_source_packet_fact_fact_id" FOREIGN KEY ("fact_id") REFERENCES "evidence"."fact"("id") ON DELETE RESTRICT;

--
-- Name: source_packet_fact fk_evidence_source_packet_fact_source_packet_version_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet_fact"
    ADD CONSTRAINT "fk_evidence_source_packet_fact_source_packet_version_id" FOREIGN KEY ("source_packet_version_id") REFERENCES "evidence"."source_packet_version"("id") ON DELETE RESTRICT;

--
-- Name: source_packet_product fk_evidence_source_packet_product_offer_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet_product"
    ADD CONSTRAINT "fk_evidence_source_packet_product_offer_id" FOREIGN KEY ("offer_id") REFERENCES "catalog"."offer"("id") ON DELETE RESTRICT;

--
-- Name: source_packet_product fk_evidence_source_packet_product_product_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet_product"
    ADD CONSTRAINT "fk_evidence_source_packet_product_product_id" FOREIGN KEY ("product_id") REFERENCES "catalog"."canonical_product"("id") ON DELETE RESTRICT;

--
-- Name: source_packet_product fk_evidence_source_packet_product_source_packet_version_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet_product"
    ADD CONSTRAINT "fk_evidence_source_packet_product_source_packet_version_id" FOREIGN KEY ("source_packet_version_id") REFERENCES "evidence"."source_packet_version"("id") ON DELETE RESTRICT;

--
-- Name: source_packet_version fk_evidence_source_packet_version_artifact_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet_version"
    ADD CONSTRAINT "fk_evidence_source_packet_version_artifact_id" FOREIGN KEY ("artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: source_packet_version fk_evidence_source_packet_version_built_by_job_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet_version"
    ADD CONSTRAINT "fk_evidence_source_packet_version_built_by_job_id" FOREIGN KEY ("built_by_job_id") REFERENCES "ops"."job"("id") ON DELETE RESTRICT;

--
-- Name: source_packet_version fk_evidence_source_packet_version_reviewed_by_principal_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet_version"
    ADD CONSTRAINT "fk_evidence_source_packet_version_reviewed_by_principal_id" FOREIGN KEY ("reviewed_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: source_packet_version fk_evidence_source_packet_version_source_packet_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_packet_version"
    ADD CONSTRAINT "fk_evidence_source_packet_version_source_packet_id" FOREIGN KEY ("source_packet_id") REFERENCES "evidence"."source_packet"("id") ON DELETE RESTRICT;

--
-- Name: source fk_evidence_source_provider_endpoint_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source"
    ADD CONSTRAINT "fk_evidence_source_provider_endpoint_id" FOREIGN KEY ("provider_endpoint_id") REFERENCES "catalog"."provider_endpoint"("id") ON DELETE RESTRICT;

--
-- Name: source_snapshot fk_evidence_source_snapshot_artifact_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_snapshot"
    ADD CONSTRAINT "fk_evidence_source_snapshot_artifact_id" FOREIGN KEY ("artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: source_snapshot fk_evidence_source_snapshot_source_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source_snapshot"
    ADD CONSTRAINT "fk_evidence_source_snapshot_source_id" FOREIGN KEY ("source_id") REFERENCES "evidence"."source"("id") ON DELETE RESTRICT;

--
-- Name: source fk_evidence_source_terms_checked_by_principal_id; Type: FK CONSTRAINT; Schema: evidence; Owner: -
--

ALTER TABLE ONLY "evidence"."source"
    ADD CONSTRAINT "fk_evidence_source_terms_checked_by_principal_id" FOREIGN KEY ("terms_checked_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: bundle_rule fk_policy_bundle_rule_policy_bundle_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."bundle_rule"
    ADD CONSTRAINT "fk_policy_bundle_rule_policy_bundle_id" FOREIGN KEY ("policy_bundle_id") REFERENCES "policy"."policy_bundle"("id") ON DELETE RESTRICT;

--
-- Name: bundle_rule fk_policy_bundle_rule_rule_version_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."bundle_rule"
    ADD CONSTRAINT "fk_policy_bundle_rule_rule_version_id" FOREIGN KEY ("rule_version_id") REFERENCES "policy"."rule_version"("id") ON DELETE RESTRICT;

--
-- Name: finding fk_policy_finding_article_block_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."finding"
    ADD CONSTRAINT "fk_policy_finding_article_block_id" FOREIGN KEY ("article_block_id") REFERENCES "editorial"."article_block"("id") ON DELETE RESTRICT;

--
-- Name: finding fk_policy_finding_claim_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."finding"
    ADD CONSTRAINT "fk_policy_finding_claim_id" FOREIGN KEY ("claim_id") REFERENCES "evidence"."claim"("id") ON DELETE RESTRICT;

--
-- Name: finding fk_policy_finding_quality_check_run_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."finding"
    ADD CONSTRAINT "fk_policy_finding_quality_check_run_id" FOREIGN KEY ("quality_check_run_id") REFERENCES "policy"."quality_check_run"("id") ON DELETE RESTRICT;

--
-- Name: finding fk_policy_finding_resolved_by_principal_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."finding"
    ADD CONSTRAINT "fk_policy_finding_resolved_by_principal_id" FOREIGN KEY ("resolved_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: finding fk_policy_finding_rule_version_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."finding"
    ADD CONSTRAINT "fk_policy_finding_rule_version_id" FOREIGN KEY ("rule_version_id") REFERENCES "policy"."rule_version"("id") ON DELETE RESTRICT;

--
-- Name: gate_decision fk_policy_gate_decision_decided_by_principal_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."gate_decision"
    ADD CONSTRAINT "fk_policy_gate_decision_decided_by_principal_id" FOREIGN KEY ("decided_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: gate_decision fk_policy_gate_decision_evidence_artifact_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."gate_decision"
    ADD CONSTRAINT "fk_policy_gate_decision_evidence_artifact_id" FOREIGN KEY ("evidence_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: gate_decision fk_policy_gate_decision_policy_bundle_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."gate_decision"
    ADD CONSTRAINT "fk_policy_gate_decision_policy_bundle_id" FOREIGN KEY ("policy_bundle_id") REFERENCES "policy"."policy_bundle"("id") ON DELETE RESTRICT;

--
-- Name: policy_bundle fk_policy_policy_bundle_approved_by_principal_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."policy_bundle"
    ADD CONSTRAINT "fk_policy_policy_bundle_approved_by_principal_id" FOREIGN KEY ("approved_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: quality_check_run fk_policy_quality_check_run_article_version_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."quality_check_run"
    ADD CONSTRAINT "fk_policy_quality_check_run_article_version_id" FOREIGN KEY ("article_version_id") REFERENCES "editorial"."article_version"("id") ON DELETE RESTRICT;

--
-- Name: quality_check_run fk_policy_quality_check_run_policy_bundle_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."quality_check_run"
    ADD CONSTRAINT "fk_policy_quality_check_run_policy_bundle_id" FOREIGN KEY ("policy_bundle_id") REFERENCES "policy"."policy_bundle"("id") ON DELETE RESTRICT;

--
-- Name: quality_check_run fk_policy_quality_check_run_report_artifact_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."quality_check_run"
    ADD CONSTRAINT "fk_policy_quality_check_run_report_artifact_id" FOREIGN KEY ("report_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: quality_check_run fk_policy_quality_check_run_source_packet_version_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."quality_check_run"
    ADD CONSTRAINT "fk_policy_quality_check_run_source_packet_version_id" FOREIGN KEY ("source_packet_version_id") REFERENCES "evidence"."source_packet_version"("id") ON DELETE RESTRICT;

--
-- Name: quality_score fk_policy_quality_score_quality_check_run_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."quality_score"
    ADD CONSTRAINT "fk_policy_quality_score_quality_check_run_id" FOREIGN KEY ("quality_check_run_id") REFERENCES "policy"."quality_check_run"("id") ON DELETE RESTRICT;

--
-- Name: rule_version fk_policy_rule_version_approved_by_principal_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."rule_version"
    ADD CONSTRAINT "fk_policy_rule_version_approved_by_principal_id" FOREIGN KEY ("approved_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: rule_version fk_policy_rule_version_created_by_principal_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."rule_version"
    ADD CONSTRAINT "fk_policy_rule_version_created_by_principal_id" FOREIGN KEY ("created_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: waiver fk_policy_waiver_decided_by_principal_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."waiver"
    ADD CONSTRAINT "fk_policy_waiver_decided_by_principal_id" FOREIGN KEY ("decided_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: waiver fk_policy_waiver_finding_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."waiver"
    ADD CONSTRAINT "fk_policy_waiver_finding_id" FOREIGN KEY ("finding_id") REFERENCES "policy"."finding"("id") ON DELETE RESTRICT;
