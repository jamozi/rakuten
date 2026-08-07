-- ST-0304 physical translation fragment 11 of 11.
-- Source: approved RAOS data catalog plus finalized ST-0003/ST-0004 semantics.
-- Capture: PostgreSQL 18.4 pg_dump --schema-only --no-owner --no-privileges
--          --no-security-labels --quote-all-identifiers for the six owned schemas.
-- Schema creation/comments are rendered once by the ST-0304 generator. The 22
-- role-bound CREATE POLICY objects remain ST-0306-owned. ENABLE/FORCE RLS remains.

--
-- Name: waiver fk_policy_waiver_requested_by_principal_id; Type: FK CONSTRAINT; Schema: policy; Owner: -
--

ALTER TABLE ONLY "policy"."waiver"
    ADD CONSTRAINT "fk_policy_waiver_requested_by_principal_id" FOREIGN KEY ("requested_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: action_candidate fk_portfolio_action_candidate_category_id; Type: FK CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."action_candidate"
    ADD CONSTRAINT "fk_portfolio_action_candidate_category_id" FOREIGN KEY ("category_id") REFERENCES "portfolio"."category"("id") ON DELETE RESTRICT;

--
-- Name: action_candidate fk_portfolio_action_candidate_decided_by_principal_id; Type: FK CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."action_candidate"
    ADD CONSTRAINT "fk_portfolio_action_candidate_decided_by_principal_id" FOREIGN KEY ("decided_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: action_candidate fk_portfolio_action_candidate_site_id; Type: FK CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."action_candidate"
    ADD CONSTRAINT "fk_portfolio_action_candidate_site_id" FOREIGN KEY ("site_id") REFERENCES "portfolio"."site"("id") ON DELETE RESTRICT;

--
-- Name: category fk_portfolio_category_approved_by_principal_id; Type: FK CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."category"
    ADD CONSTRAINT "fk_portfolio_category_approved_by_principal_id" FOREIGN KEY ("approved_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: category fk_portfolio_category_parent_category_id; Type: FK CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."category"
    ADD CONSTRAINT "fk_portfolio_category_parent_category_id" FOREIGN KEY ("parent_category_id") REFERENCES "portfolio"."category"("id") ON DELETE RESTRICT;

--
-- Name: category fk_portfolio_category_site_id; Type: FK CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."category"
    ADD CONSTRAINT "fk_portfolio_category_site_id" FOREIGN KEY ("site_id") REFERENCES "portfolio"."site"("id") ON DELETE RESTRICT;

--
-- Name: intent_cluster fk_portfolio_intent_cluster_category_id; Type: FK CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."intent_cluster"
    ADD CONSTRAINT "fk_portfolio_intent_cluster_category_id" FOREIGN KEY ("category_id") REFERENCES "portfolio"."category"("id") ON DELETE RESTRICT;

--
-- Name: intent_cluster_keyword fk_portfolio_intent_cluster_keyword_intent_cluster_id; Type: FK CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."intent_cluster_keyword"
    ADD CONSTRAINT "fk_portfolio_intent_cluster_keyword_intent_cluster_id" FOREIGN KEY ("intent_cluster_id") REFERENCES "portfolio"."intent_cluster"("id") ON DELETE RESTRICT;

--
-- Name: intent_cluster_keyword fk_portfolio_intent_cluster_keyword_keyword_id; Type: FK CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."intent_cluster_keyword"
    ADD CONSTRAINT "fk_portfolio_intent_cluster_keyword_keyword_id" FOREIGN KEY ("keyword_id") REFERENCES "portfolio"."keyword"("id") ON DELETE RESTRICT;

--
-- Name: keyword_metric_observation fk_portfolio_keyword_metric_observation_keyword_id; Type: FK CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."keyword_metric_observation"
    ADD CONSTRAINT "fk_portfolio_keyword_metric_observation_keyword_id" FOREIGN KEY ("keyword_id") REFERENCES "portfolio"."keyword"("id") ON DELETE RESTRICT;

--
-- Name: keyword_metric_observation fk_portfolio_keyword_metric_observation_raw_artifact_id; Type: FK CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."keyword_metric_observation"
    ADD CONSTRAINT "fk_portfolio_keyword_metric_observation_raw_artifact_id" FOREIGN KEY ("raw_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: keyword fk_portfolio_keyword_site_id; Type: FK CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."keyword"
    ADD CONSTRAINT "fk_portfolio_keyword_site_id" FOREIGN KEY ("site_id") REFERENCES "portfolio"."site"("id") ON DELETE RESTRICT;

--
-- Name: opportunity_assessment fk_portfolio_opportunity_assessment_category_id; Type: FK CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."opportunity_assessment"
    ADD CONSTRAINT "fk_portfolio_opportunity_assessment_category_id" FOREIGN KEY ("category_id") REFERENCES "portfolio"."category"("id") ON DELETE RESTRICT;

--
-- Name: opportunity_assessment fk_portfolio_opportunity_assessment_intent_cluster_id; Type: FK CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."opportunity_assessment"
    ADD CONSTRAINT "fk_portfolio_opportunity_assessment_intent_cluster_id" FOREIGN KEY ("intent_cluster_id") REFERENCES "portfolio"."intent_cluster"("id") ON DELETE RESTRICT;

--
-- Name: opportunity_assessment fk_portfolio_opportunity_assessment_keyword_id; Type: FK CONSTRAINT; Schema: portfolio; Owner: -
--

ALTER TABLE ONLY "portfolio"."opportunity_assessment"
    ADD CONSTRAINT "fk_portfolio_opportunity_assessment_keyword_id" FOREIGN KEY ("keyword_id") REFERENCES "portfolio"."keyword"("id") ON DELETE RESTRICT;

--
-- Name: article_disclosure_context; Type: ROW SECURITY; Schema: editorial; Owner: -
--

ALTER TABLE "editorial"."article_disclosure_context" ENABLE ROW LEVEL SECURITY;

--
-- Name: article_methodology_binding; Type: ROW SECURITY; Schema: editorial; Owner: -
--

ALTER TABLE "editorial"."article_methodology_binding" ENABLE ROW LEVEL SECURITY;

--
-- Name: article_template_version; Type: ROW SECURITY; Schema: editorial; Owner: -
--

ALTER TABLE "editorial"."article_template_version" ENABLE ROW LEVEL SECURITY;

--
-- Name: article_type_version; Type: ROW SECURITY; Schema: editorial; Owner: -
--

ALTER TABLE "editorial"."article_type_version" ENABLE ROW LEVEL SECURITY;

--
-- Name: content_schema_version; Type: ROW SECURITY; Schema: editorial; Owner: -
--

ALTER TABLE "editorial"."content_schema_version" ENABLE ROW LEVEL SECURITY;

--
-- Name: editorial_methodology_version; Type: ROW SECURITY; Schema: editorial; Owner: -
--

ALTER TABLE "editorial"."editorial_methodology_version" ENABLE ROW LEVEL SECURITY;

--
-- Name: media_asset; Type: ROW SECURITY; Schema: editorial; Owner: -
--

ALTER TABLE "editorial"."media_asset" ENABLE ROW LEVEL SECURITY;

--
-- Name: seo_metadata_version; Type: ROW SECURITY; Schema: editorial; Owner: -
--

ALTER TABLE "editorial"."seo_metadata_version" ENABLE ROW LEVEL SECURITY;

--
-- Name: structured_data_manifest; Type: ROW SECURITY; Schema: editorial; Owner: -
--

ALTER TABLE "editorial"."structured_data_manifest" ENABLE ROW LEVEL SECURITY;

--
-- Name: first_hand_experience_asset; Type: ROW SECURITY; Schema: evidence; Owner: -
--

ALTER TABLE "evidence"."first_hand_experience_asset" ENABLE ROW LEVEL SECURITY;

--
-- Name: first_hand_experience_record; Type: ROW SECURITY; Schema: evidence; Owner: -
--

ALTER TABLE "evidence"."first_hand_experience_record" ENABLE ROW LEVEL SECURITY;
