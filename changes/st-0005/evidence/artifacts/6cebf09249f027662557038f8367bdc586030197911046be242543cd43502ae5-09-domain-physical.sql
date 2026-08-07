-- ST-0304 physical translation fragment 09 of 11.
-- Source: approved RAOS data catalog plus finalized ST-0003/ST-0004 semantics.
-- Capture: PostgreSQL 18.4 pg_dump --schema-only --no-owner --no-privileges
--          --no-security-labels --quote-all-identifiers for the six owned schemas.
-- Schema creation/comments are rendered once by the ST-0304 generator. The 22
-- role-bound CREATE POLICY objects remain ST-0306-owned. ENABLE/FORCE RLS remains.

--
-- Name: ix_catalog_candidate_genre; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_candidate_genre" ON "catalog"."product_candidate" USING "btree" ("rakuten_genre_id", "listing_status");

--
-- Name: ix_catalog_candidate_jan; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_candidate_jan" ON "catalog"."product_candidate" USING "btree" ("jan_code_candidate") WHERE ("jan_code_candidate" IS NOT NULL);

--
-- Name: ix_catalog_candidate_model; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_candidate_model" ON "catalog"."product_candidate" USING "btree" ("model_number_candidate") WHERE ("model_number_candidate" IS NOT NULL);

--
-- Name: ix_catalog_candidate_shop; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_candidate_shop" ON "catalog"."product_candidate" USING "btree" ("shop_id", "listing_status");

--
-- Name: ix_catalog_canonical_product_merged_into_product_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_canonical_product_merged_into_product_id" ON "catalog"."canonical_product" USING "btree" ("merged_into_product_id");

--
-- Name: ix_catalog_category_genre_mapping_decided_by_principal_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_category_genre_mapping_decided_by_principal_id" ON "catalog"."category_genre_mapping" USING "btree" ("decided_by_principal_id");

--
-- Name: ix_catalog_genre_categories; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_genre_categories" ON "catalog"."category_genre_mapping" USING "btree" ("rakuten_genre_id", "mapping_role");

--
-- Name: ix_catalog_group_candidate; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_group_candidate" ON "catalog"."grouping_decision" USING "btree" ("product_candidate_id", "decided_at");

--
-- Name: ix_catalog_group_product; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_group_product" ON "catalog"."grouping_decision" USING "btree" ("proposed_product_id", "decided_at");

--
-- Name: ix_catalog_grouping_decision_supersedes_decision_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_grouping_decision_supersedes_decision_id" ON "catalog"."grouping_decision" USING "btree" ("supersedes_decision_id");

--
-- Name: ix_catalog_ingestion_provider_time; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_ingestion_provider_time" ON "catalog"."ingestion_request" USING "btree" ("provider_endpoint_id", "requested_at");

--
-- Name: ix_catalog_ingestion_request_raw_response_artifact_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_ingestion_request_raw_response_artifact_id" ON "catalog"."ingestion_request" USING "btree" ("raw_response_artifact_id");

--
-- Name: ix_catalog_ingestion_status; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_ingestion_status" ON "catalog"."ingestion_request" USING "btree" ("status", "requested_at");

--
-- Name: ix_catalog_membership_product; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_membership_product" ON "catalog"."product_group_membership" USING "btree" ("product_id", "valid_from");

--
-- Name: ix_catalog_offer_candidate; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_offer_candidate" ON "catalog"."offer" USING "btree" ("product_candidate_id");

--
-- Name: ix_catalog_offer_current_available; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_offer_current_available" ON "catalog"."offer_current_projection" USING "btree" ("current_availability", "freshness_status");

--
-- Name: ix_catalog_offer_current_product; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_offer_current_product" ON "catalog"."offer_current_projection" USING "btree" ("product_id", "freshness_status");

--
-- Name: ix_catalog_offer_current_projection_affiliate_link_o_2ca582c972; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_offer_current_projection_affiliate_link_o_2ca582c972" ON "catalog"."offer_current_projection" USING "btree" ("affiliate_link_observation_id");

--
-- Name: ix_catalog_offer_current_projection_availability_observation_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_offer_current_projection_availability_observation_id" ON "catalog"."offer_current_projection" USING "btree" ("availability_observation_id");

--
-- Name: ix_catalog_offer_current_projection_price_observation_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_offer_current_projection_price_observation_id" ON "catalog"."offer_current_projection" USING "btree" ("price_observation_id");

--
-- Name: ix_catalog_offer_current_projection_review_observation_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_offer_current_projection_review_observation_id" ON "catalog"."offer_current_projection" USING "btree" ("review_observation_id");

--
-- Name: ix_catalog_offer_product; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_offer_product" ON "catalog"."offer" USING "btree" ("product_id", "status");

--
-- Name: ix_catalog_offer_shop; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_offer_shop" ON "catalog"."offer" USING "btree" ("shop_id", "status");

--
-- Name: ix_catalog_price_observation_source_snapshot_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_price_observation_source_snapshot_id" ON "catalog"."price_observation" USING "btree" ("source_snapshot_id");

--
-- Name: ix_catalog_price_observed_brin; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_price_observed_brin" ON "catalog"."price_observation" USING "brin" ("observed_at");

--
-- Name: ix_catalog_price_offer_time; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_price_offer_time" ON "catalog"."price_observation" USING "btree" ("offer_id", "observed_at");

--
-- Name: ix_catalog_product_attr_code; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_product_attr_code" ON "catalog"."product_attribute_value" USING "btree" ("attribute_definition_id", "value_code") WHERE ("value_code" IS NOT NULL);

--
-- Name: ix_catalog_product_attr_numeric; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_product_attr_numeric" ON "catalog"."product_attribute_value" USING "btree" ("attribute_definition_id", "value_numeric") WHERE ("value_numeric" IS NOT NULL);

--
-- Name: ix_catalog_product_attribute_value_source_fact_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_product_attribute_value_source_fact_id" ON "catalog"."product_attribute_value" USING "btree" ("source_fact_id");

--
-- Name: ix_catalog_product_candidate_source_snapshot_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_product_candidate_source_snapshot_id" ON "catalog"."product_candidate" USING "btree" ("source_snapshot_id");

--
-- Name: ix_catalog_product_category; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_product_category" ON "catalog"."canonical_product" USING "btree" ("category_id", "lifecycle_status");

--
-- Name: ix_catalog_product_group_membership_grouping_decision_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_product_group_membership_grouping_decision_id" ON "catalog"."product_group_membership" USING "btree" ("grouping_decision_id");

--
-- Name: ix_catalog_product_jan; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_product_jan" ON "catalog"."canonical_product" USING "btree" ("jan_code") WHERE ("jan_code" IS NOT NULL);

--
-- Name: ix_catalog_product_model; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_product_model" ON "catalog"."canonical_product" USING "btree" ("category_id", "model_number") WHERE ("model_number" IS NOT NULL);

--
-- Name: ix_catalog_product_relation_reverse; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_product_relation_reverse" ON "catalog"."product_relation" USING "btree" ("to_product_id", "relation_type");

--
-- Name: ix_catalog_product_relation_source_fact_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_product_relation_source_fact_id" ON "catalog"."product_relation" USING "btree" ("source_fact_id");

--
-- Name: ix_catalog_rakuten_genre_parent; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_rakuten_genre_parent" ON "catalog"."rakuten_genre" USING "btree" ("provider_endpoint_id", "parent_external_genre_id");

--
-- Name: ix_catalog_rakuten_genre_source_snapshot_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_rakuten_genre_source_snapshot_id" ON "catalog"."rakuten_genre" USING "btree" ("source_snapshot_id");

--
-- Name: ix_catalog_review_aggregate_observation_source_snapshot_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_review_aggregate_observation_source_snapshot_id" ON "catalog"."review_aggregate_observation" USING "btree" ("source_snapshot_id");

--
-- Name: ix_catalog_review_offer_time; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_review_offer_time" ON "catalog"."review_aggregate_observation" USING "btree" ("offer_id", "observed_at");

--
-- Name: ix_catalog_shop_source_snapshot_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_shop_source_snapshot_id" ON "catalog"."shop" USING "btree" ("source_snapshot_id");

--
-- Name: ix_catalog_shop_status; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX "ix_catalog_shop_status" ON "catalog"."shop" USING "btree" ("provider_endpoint_id", "status");

--
-- Name: uq_catalog_attribute_code; Type: INDEX; Schema: catalog; Owner: -
--

CREATE UNIQUE INDEX "uq_catalog_attribute_code" ON "catalog"."attribute_definition" USING "btree" ("category_id", "attribute_code") NULLS NOT DISTINCT;

--
-- Name: uq_catalog_category_genre_current; Type: INDEX; Schema: catalog; Owner: -
--

CREATE UNIQUE INDEX "uq_catalog_category_genre_current" ON "catalog"."category_genre_mapping" USING "btree" ("category_id", "rakuten_genre_id", "mapping_role") WHERE ("valid_to" IS NULL);

--
-- Name: uq_catalog_membership_current; Type: INDEX; Schema: catalog; Owner: -
--

CREATE UNIQUE INDEX "uq_catalog_membership_current" ON "catalog"."product_group_membership" USING "btree" ("product_candidate_id") WHERE ("valid_to" IS NULL);

--
-- Name: uq_catalog_product_attr_current; Type: INDEX; Schema: catalog; Owner: -
--

CREATE UNIQUE INDEX "uq_catalog_product_attr_current" ON "catalog"."product_attribute_value" USING "btree" ("product_id", "attribute_definition_id") WHERE ("valid_to" IS NULL);

--
-- Name: uq_catalog_product_relation_current; Type: INDEX; Schema: catalog; Owner: -
--

CREATE UNIQUE INDEX "uq_catalog_product_relation_current" ON "catalog"."product_relation" USING "btree" ("from_product_id", "to_product_id", "relation_type") WHERE ("valid_to" IS NULL);

--
-- Name: uq_catalog_provider_active; Type: INDEX; Schema: catalog; Owner: -
--

CREATE UNIQUE INDEX "uq_catalog_provider_active" ON "catalog"."provider_endpoint" USING "btree" ("provider_code", "api_name") WHERE ("status" = 'ACTIVE'::"text");

--
-- Name: ix_editorial_article_block_product_offer_id; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_block_product_offer_id" ON "editorial"."article_block_product" USING "btree" ("offer_id");

--
-- Name: ix_editorial_article_current; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_current" ON "editorial"."article" USING "btree" ("current_version_id");

--
-- Name: ix_editorial_article_disclosure_reviewer; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_disclosure_reviewer" ON "editorial"."article_disclosure_context" USING "btree" ("reviewed_by_principal_id");

--
-- Name: ix_editorial_article_link_to; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_link_to" ON "editorial"."article_link" USING "btree" ("to_article_id", "status");

--
-- Name: ix_editorial_article_methodology_binder; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_methodology_binder" ON "editorial"."article_methodology_binding" USING "btree" ("bound_by_principal_id");

--
-- Name: ix_editorial_article_methodology_candidate; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_methodology_candidate" ON "editorial"."article_methodology_binding" USING "btree" ("candidate_universe_artifact_id");

--
-- Name: ix_editorial_article_methodology_version; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_methodology_version" ON "editorial"."article_methodology_binding" USING "btree" ("methodology_version_id");

--
-- Name: ix_editorial_article_plan_approved_by_principal_id; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_plan_approved_by_principal_id" ON "editorial"."article_plan" USING "btree" ("approved_by_principal_id");

--
-- Name: ix_editorial_article_plan_category_id; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_plan_category_id" ON "editorial"."article_plan" USING "btree" ("category_id");

--
-- Name: ix_editorial_article_plan_created_by_principal_id; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_plan_created_by_principal_id" ON "editorial"."article_plan" USING "btree" ("created_by_principal_id");

--
-- Name: ix_editorial_article_plan_opportunity_assessment_id; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_plan_opportunity_assessment_id" ON "editorial"."article_plan" USING "btree" ("opportunity_assessment_id");

--
-- Name: ix_editorial_article_published; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_published" ON "editorial"."article" USING "btree" ("published_version_id");

--
-- Name: ix_editorial_article_status; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_status" ON "editorial"."article" USING "btree" ("site_id", "status", "updated_at");

--
-- Name: ix_editorial_article_template_approver; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_template_approver" ON "editorial"."article_template_version" USING "btree" ("approved_by_principal_id");

--
-- Name: ix_editorial_article_type_approver; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_type_approver" ON "editorial"."article_type_version" USING "btree" ("approved_by_principal_id");

--
-- Name: ix_editorial_article_version_ai_job_id; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_version_ai_job_id" ON "editorial"."article_version" USING "btree" ("ai_job_id");

--
-- Name: ix_editorial_article_version_article_template; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_version_article_template" ON "editorial"."article_version" USING "btree" ("article_template_version_id");

--
-- Name: ix_editorial_article_version_article_type; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_version_article_type" ON "editorial"."article_version" USING "btree" ("article_type_version_id");

--
-- Name: ix_editorial_article_version_based_on_version_id; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_version_based_on_version_id" ON "editorial"."article_version" USING "btree" ("based_on_version_id");

--
-- Name: ix_editorial_article_version_content_schema; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_version_content_schema" ON "editorial"."article_version" USING "btree" ("content_schema_version_id");

--
-- Name: ix_editorial_article_version_packet; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_version_packet" ON "editorial"."article_version" USING "btree" ("source_packet_version_id");

--
-- Name: ix_editorial_article_version_seo; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_version_seo" ON "editorial"."article_version" USING "btree" ("seo_metadata_version_id", "id");

--
-- Name: ix_editorial_article_version_status; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_article_version_status" ON "editorial"."article_version" USING "btree" ("article_id", "status", "version_no");

--
-- Name: ix_editorial_block_order; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_block_order" ON "editorial"."article_block" USING "btree" ("article_version_id", "position");

--
-- Name: ix_editorial_block_product_order; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_block_product_order" ON "editorial"."article_block_product" USING "btree" ("article_block_id", "position");

--
-- Name: ix_editorial_block_product_reverse; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_block_product_reverse" ON "editorial"."article_block_product" USING "btree" ("product_id");

--
-- Name: ix_editorial_comparison_product; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_comparison_product" ON "editorial"."comparison_value" USING "btree" ("product_id", "comparison_axis_id");

--
-- Name: ix_editorial_comparison_value_source_fact_id; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_comparison_value_source_fact_id" ON "editorial"."comparison_value" USING "btree" ("source_fact_id");

--
-- Name: ix_editorial_content_schema_approver; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_content_schema_approver" ON "editorial"."content_schema_version" USING "btree" ("approved_by_principal_id");

--
-- Name: ix_editorial_content_schema_artifact; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_content_schema_artifact" ON "editorial"."content_schema_version" USING "btree" ("artifact_id");

--
-- Name: ix_editorial_media_asset_approver; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_media_asset_approver" ON "editorial"."media_asset" USING "btree" ("approved_by_principal_id");

--
-- Name: ix_editorial_media_asset_long_description; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_media_asset_long_description" ON "editorial"."media_asset" USING "btree" ("long_description_artifact_id");

--
-- Name: ix_editorial_media_asset_raw; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_media_asset_raw" ON "editorial"."media_asset" USING "btree" ("raw_artifact_id");

--
-- Name: ix_editorial_media_asset_source; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_media_asset_source" ON "editorial"."media_asset" USING "btree" ("source_id");

--
-- Name: ix_editorial_media_asset_status; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_media_asset_status" ON "editorial"."media_asset" USING "btree" ("status", "created_at" DESC);

--
-- Name: ix_editorial_methodology_approver; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_methodology_approver" ON "editorial"."editorial_methodology_version" USING "btree" ("approved_by_principal_id");

--
-- Name: ix_editorial_methodology_article_type; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_methodology_article_type" ON "editorial"."editorial_methodology_version" USING "btree" ("article_type_version_id", "article_type_code");

--
-- Name: ix_editorial_plan_cluster; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_plan_cluster" ON "editorial"."article_plan" USING "btree" ("intent_cluster_id", "status");

--
-- Name: ix_editorial_plan_keyword; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_plan_keyword" ON "editorial"."article_plan" USING "btree" ("primary_keyword_id", "status");

--
-- Name: ix_editorial_plan_queue; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_plan_queue" ON "editorial"."article_plan" USING "btree" ("site_id", "status", "priority", "updated_at");

--
-- Name: ix_editorial_rationale_order; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_rationale_order" ON "editorial"."recommendation_rationale" USING "btree" ("recommendation_id", "position");

--
-- Name: ix_editorial_rec_product_reverse; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_rec_product_reverse" ON "editorial"."recommendation" USING "btree" ("product_id");

--
-- Name: ix_editorial_recommendation_rationale_claim_id; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_recommendation_rationale_claim_id" ON "editorial"."recommendation_rationale" USING "btree" ("claim_id");

--
-- Name: ix_editorial_recommendation_rationale_source_fact_id; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_recommendation_rationale_source_fact_id" ON "editorial"."recommendation_rationale" USING "btree" ("source_fact_id");

--
-- Name: ix_editorial_review_comment_article_block_id; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_review_comment_article_block_id" ON "editorial"."review_comment" USING "btree" ("article_block_id");

--
-- Name: ix_editorial_review_comment_author_principal_id; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_review_comment_author_principal_id" ON "editorial"."review_comment" USING "btree" ("author_principal_id");

--
-- Name: ix_editorial_review_comment_claim_id; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_review_comment_claim_id" ON "editorial"."review_comment" USING "btree" ("claim_id");

--
-- Name: ix_editorial_review_comment_parent_comment_id; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_review_comment_parent_comment_id" ON "editorial"."review_comment" USING "btree" ("parent_comment_id");

--
-- Name: ix_editorial_review_comment_resolved_by_principal_id; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_review_comment_resolved_by_principal_id" ON "editorial"."review_comment" USING "btree" ("resolved_by_principal_id");

--
-- Name: ix_editorial_review_open; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_review_open" ON "editorial"."review_comment" USING "btree" ("article_version_id", "status") WHERE ("status" = 'OPEN'::"text");

--
-- Name: ix_editorial_review_thread; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_review_thread" ON "editorial"."review_comment" USING "btree" ("thread_id", "created_at");

--
-- Name: ix_editorial_seo_approver; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_seo_approver" ON "editorial"."seo_metadata_version" USING "btree" ("approved_by_principal_id");

--
-- Name: ix_editorial_slug_article_history; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_slug_article_history" ON "editorial"."article_slug" USING "btree" ("article_id", "valid_from");

--
-- Name: ix_editorial_structured_data_jsonld; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_structured_data_jsonld" ON "editorial"."structured_data_manifest" USING "btree" ("jsonld_artifact_id");

--
-- Name: ix_editorial_structured_data_seo; Type: INDEX; Schema: editorial; Owner: -
--

CREATE INDEX "ix_editorial_structured_data_seo" ON "editorial"."structured_data_manifest" USING "btree" ("seo_metadata_version_id", "article_version_id");

--
-- Name: uq_editorial_article_type_active; Type: INDEX; Schema: editorial; Owner: -
--

CREATE UNIQUE INDEX "uq_editorial_article_type_active" ON "editorial"."article_type_version" USING "btree" ("article_type_code") WHERE ("status" = 'ACTIVE'::"text");

--
-- Name: uq_editorial_content_schema_active; Type: INDEX; Schema: editorial; Owner: -
--

CREATE UNIQUE INDEX "uq_editorial_content_schema_active" ON "editorial"."content_schema_version" USING "btree" ("schema_code") WHERE ("status" = 'ACTIVE'::"text");

--
-- Name: uq_editorial_methodology_active; Type: INDEX; Schema: editorial; Owner: -
--

CREATE UNIQUE INDEX "uq_editorial_methodology_active" ON "editorial"."editorial_methodology_version" USING "btree" ("methodology_code") WHERE ("status" = 'ACTIVE'::"text");

--
-- Name: uq_editorial_slug_active_article; Type: INDEX; Schema: editorial; Owner: -
--

CREATE UNIQUE INDEX "uq_editorial_slug_active_article" ON "editorial"."article_slug" USING "btree" ("article_id") WHERE (("valid_to" IS NULL) AND ("status" = 'ACTIVE'::"text"));

--
-- Name: uq_editorial_slug_active_path; Type: INDEX; Schema: editorial; Owner: -
--

CREATE UNIQUE INDEX "uq_editorial_slug_active_path" ON "editorial"."article_slug" USING "btree" ("site_id", "normalized_path") WHERE ("valid_to" IS NULL);

--
-- Name: ix_evidence_claim_block; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_claim_block" ON "evidence"."claim" USING "btree" ("block_id");

--
-- Name: ix_evidence_claim_block_id_article_version_id; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_claim_block_id_article_version_id" ON "evidence"."claim" USING "btree" ("block_id", "article_version_id");

--
-- Name: ix_evidence_claim_generated_by_ai_attempt_id; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_claim_generated_by_ai_attempt_id" ON "evidence"."claim" USING "btree" ("generated_by_ai_attempt_id");

--
-- Name: ix_evidence_claim_link_fact; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_claim_link_fact" ON "evidence"."claim_evidence_link" USING "btree" ("fact_id", "support_type");

--
-- Name: ix_evidence_claim_version_status; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_claim_version_status" ON "evidence"."claim" USING "btree" ("article_version_id", "support_status", "criticality");

--
-- Name: ix_evidence_derivation_input; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_derivation_input" ON "evidence"."fact_derivation" USING "btree" ("input_fact_id");

--
-- Name: ix_evidence_fact_predicate_numeric; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_fact_predicate_numeric" ON "evidence"."fact" USING "btree" ("predicate", "value_numeric") WHERE ("value_numeric" IS NOT NULL);

--
-- Name: ix_evidence_fact_snapshot; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_fact_snapshot" ON "evidence"."fact" USING "btree" ("source_snapshot_id");

--
-- Name: ix_evidence_fact_subject; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_fact_subject" ON "evidence"."fact" USING "btree" ("subject_type", "subject_id", "predicate", "created_at");

--
-- Name: ix_evidence_first_hand_asset_artifact; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_first_hand_asset_artifact" ON "evidence"."first_hand_experience_asset" USING "btree" ("artifact_id");

--
-- Name: ix_evidence_first_hand_product; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_first_hand_product" ON "evidence"."first_hand_experience_record" USING "btree" ("product_id", "ended_at" DESC);

--
-- Name: ix_evidence_first_hand_reviewer; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_first_hand_reviewer" ON "evidence"."first_hand_experience_record" USING "btree" ("reviewed_by_principal_id");

--
-- Name: ix_evidence_first_hand_tester; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_first_hand_tester" ON "evidence"."first_hand_experience_record" USING "btree" ("tester_principal_id");

--
-- Name: ix_evidence_packet_fact_order; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_packet_fact_order" ON "evidence"."source_packet_fact" USING "btree" ("source_packet_version_id", "display_order");

--
-- Name: ix_evidence_packet_fact_reverse; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_packet_fact_reverse" ON "evidence"."source_packet_fact" USING "btree" ("fact_id");

--
-- Name: ix_evidence_packet_product_order; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_packet_product_order" ON "evidence"."source_packet_product" USING "btree" ("source_packet_version_id", "display_order");

--
-- Name: ix_evidence_packet_product_reverse; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_packet_product_reverse" ON "evidence"."source_packet_product" USING "btree" ("product_id");

--
-- Name: ix_evidence_packet_status; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_packet_status" ON "evidence"."source_packet" USING "btree" ("status", "updated_at");

--
-- Name: ix_evidence_packet_version_status; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_packet_version_status" ON "evidence"."source_packet_version" USING "btree" ("source_packet_id", "status", "version_no");

--
-- Name: ix_evidence_snapshot_external; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_snapshot_external" ON "evidence"."source_snapshot" USING "btree" ("source_id", "external_reference") WHERE ("external_reference" IS NOT NULL);

--
-- Name: ix_evidence_snapshot_source_time; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_snapshot_source_time" ON "evidence"."source_snapshot" USING "btree" ("source_id", "acquired_at");

--
-- Name: ix_evidence_source_packet_product_offer_id; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_source_packet_product_offer_id" ON "evidence"."source_packet_product" USING "btree" ("offer_id");

--
-- Name: ix_evidence_source_packet_version_built_by_job_id; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_source_packet_version_built_by_job_id" ON "evidence"."source_packet_version" USING "btree" ("built_by_job_id");

--
-- Name: ix_evidence_source_packet_version_reviewed_by_principal_id; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_source_packet_version_reviewed_by_principal_id" ON "evidence"."source_packet_version" USING "btree" ("reviewed_by_principal_id");

--
-- Name: ix_evidence_source_provider_endpoint_id; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_source_provider_endpoint_id" ON "evidence"."source" USING "btree" ("provider_endpoint_id");

--
-- Name: ix_evidence_source_terms_checked_by_principal_id; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_source_terms_checked_by_principal_id" ON "evidence"."source" USING "btree" ("terms_checked_by_principal_id");

--
-- Name: ix_evidence_source_type_status; Type: INDEX; Schema: evidence; Owner: -
--

CREATE INDEX "ix_evidence_source_type_status" ON "evidence"."source" USING "btree" ("source_type", "status");

--
-- Name: ix_policy_bundle_rule_rule_version_id; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_bundle_rule_rule_version_id" ON "policy"."bundle_rule" USING "btree" ("rule_version_id");

--
-- Name: ix_policy_check_article; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_check_article" ON "policy"."quality_check_run" USING "btree" ("article_version_id", "started_at");

--
-- Name: ix_policy_check_status; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_check_status" ON "policy"."quality_check_run" USING "btree" ("status", "started_at");

--
-- Name: ix_policy_finding_article_block_id; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_finding_article_block_id" ON "policy"."finding" USING "btree" ("article_block_id");

--
-- Name: ix_policy_finding_claim_id; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_finding_claim_id" ON "policy"."finding" USING "btree" ("claim_id");

--
-- Name: ix_policy_finding_entity; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_finding_entity" ON "policy"."finding" USING "btree" ("entity_type", "entity_id");

--
-- Name: ix_policy_finding_open; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_finding_open" ON "policy"."finding" USING "btree" ("quality_check_run_id", "is_blocking", "severity") WHERE ("status" = 'OPEN'::"text");

--
-- Name: ix_policy_finding_resolved_by_principal_id; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_finding_resolved_by_principal_id" ON "policy"."finding" USING "btree" ("resolved_by_principal_id");

--
-- Name: ix_policy_finding_rule_version_id; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_finding_rule_version_id" ON "policy"."finding" USING "btree" ("rule_version_id");

--
-- Name: ix_policy_gate_decision_decided_by_principal_id; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_gate_decision_decided_by_principal_id" ON "policy"."gate_decision" USING "btree" ("decided_by_principal_id");

--
-- Name: ix_policy_gate_decision_evidence_artifact_id; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_gate_decision_evidence_artifact_id" ON "policy"."gate_decision" USING "btree" ("evidence_artifact_id");

--
-- Name: ix_policy_gate_decision_policy_bundle_id; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_gate_decision_policy_bundle_id" ON "policy"."gate_decision" USING "btree" ("policy_bundle_id");

--
-- Name: ix_policy_gate_scope; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_gate_scope" ON "policy"."gate_decision" USING "btree" ("gate_code", "scope_type", "scope_id", "decided_at");

--
-- Name: ix_policy_policy_bundle_approved_by_principal_id; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_policy_bundle_approved_by_principal_id" ON "policy"."policy_bundle" USING "btree" ("approved_by_principal_id");

--
-- Name: ix_policy_quality_check_run_policy_bundle_id; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_quality_check_run_policy_bundle_id" ON "policy"."quality_check_run" USING "btree" ("policy_bundle_id");

--
-- Name: ix_policy_quality_check_run_report_artifact_id; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_quality_check_run_report_artifact_id" ON "policy"."quality_check_run" USING "btree" ("report_artifact_id");

--
-- Name: ix_policy_quality_check_run_source_packet_version_id; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_quality_check_run_source_packet_version_id" ON "policy"."quality_check_run" USING "btree" ("source_packet_version_id");

--
-- Name: ix_policy_rule_version_approved_by_principal_id; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_rule_version_approved_by_principal_id" ON "policy"."rule_version" USING "btree" ("approved_by_principal_id");

--
-- Name: ix_policy_rule_version_created_by_principal_id; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_rule_version_created_by_principal_id" ON "policy"."rule_version" USING "btree" ("created_by_principal_id");

--
-- Name: ix_policy_waiver_active; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_waiver_active" ON "policy"."waiver" USING "btree" ("scope_type", "scope_id", "status", "expires_at");

--
-- Name: ix_policy_waiver_decided_by_principal_id; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_waiver_decided_by_principal_id" ON "policy"."waiver" USING "btree" ("decided_by_principal_id");

--
-- Name: ix_policy_waiver_finding_id; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_waiver_finding_id" ON "policy"."waiver" USING "btree" ("finding_id");

--
-- Name: ix_policy_waiver_requested_by_principal_id; Type: INDEX; Schema: policy; Owner: -
--

CREATE INDEX "ix_policy_waiver_requested_by_principal_id" ON "policy"."waiver" USING "btree" ("requested_by_principal_id");

--
-- Name: uq_policy_bundle_active; Type: INDEX; Schema: policy; Owner: -
--

CREATE UNIQUE INDEX "uq_policy_bundle_active" ON "policy"."policy_bundle" USING "btree" ("bundle_code") WHERE ("status" = 'ACTIVE'::"text");

--
-- Name: ix_portfolio_action_candidate_category_id; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_action_candidate_category_id" ON "portfolio"."action_candidate" USING "btree" ("category_id");

--
-- Name: ix_portfolio_action_candidate_decided_by_principal_id; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_action_candidate_decided_by_principal_id" ON "portfolio"."action_candidate" USING "btree" ("decided_by_principal_id");

--
-- Name: ix_portfolio_action_queue; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_action_queue" ON "portfolio"."action_candidate" USING "btree" ("site_id", "status", "priority_score", "generated_at");

--
-- Name: ix_portfolio_action_target; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_action_target" ON "portfolio"."action_candidate" USING "btree" ("target_entity_type", "target_entity_id");

--
-- Name: ix_portfolio_category_approved_by_principal_id; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_category_approved_by_principal_id" ON "portfolio"."category" USING "btree" ("approved_by_principal_id");

--
-- Name: ix_portfolio_category_parent_category_id; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_category_parent_category_id" ON "portfolio"."category" USING "btree" ("parent_category_id");

--
-- Name: ix_portfolio_category_stage; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_category_stage" ON "portfolio"."category" USING "btree" ("site_id", "stage");

--
-- Name: ix_portfolio_category_tree; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_category_tree" ON "portfolio"."category" USING "btree" ("site_id", "parent_category_id");

--
-- Name: ix_portfolio_cluster_keyword_role; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_cluster_keyword_role" ON "portfolio"."intent_cluster_keyword" USING "btree" ("intent_cluster_id", "keyword_role", "priority");

--
-- Name: ix_portfolio_intent_category; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_intent_category" ON "portfolio"."intent_cluster" USING "btree" ("category_id", "status");

--
-- Name: ix_portfolio_intent_cluster_keyword_keyword_id; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_intent_cluster_keyword_keyword_id" ON "portfolio"."intent_cluster_keyword" USING "btree" ("keyword_id");

--
-- Name: ix_portfolio_keyword_metric_observation_raw_artifact_id; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_keyword_metric_observation_raw_artifact_id" ON "portfolio"."keyword_metric_observation" USING "btree" ("raw_artifact_id");

--
-- Name: ix_portfolio_keyword_text; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_keyword_text" ON "portfolio"."keyword" USING "btree" ("lower"("display_text"));

--
-- Name: ix_portfolio_kw_metric_latest; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_kw_metric_latest" ON "portfolio"."keyword_metric_observation" USING "btree" ("keyword_id", "metric_type", "observed_date");

--
-- Name: ix_portfolio_opp_priority; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_opp_priority" ON "portfolio"."opportunity_assessment" USING "btree" ("decision", "overall_priority_score");

--
-- Name: ix_portfolio_opp_scope; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_opp_scope" ON "portfolio"."opportunity_assessment" USING "btree" ("category_id", "intent_cluster_id", "keyword_id", "assessed_at");

--
-- Name: ix_portfolio_opportunity_assessment_intent_cluster_id; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_opportunity_assessment_intent_cluster_id" ON "portfolio"."opportunity_assessment" USING "btree" ("intent_cluster_id");

--
-- Name: ix_portfolio_opportunity_assessment_keyword_id; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE INDEX "ix_portfolio_opportunity_assessment_keyword_id" ON "portfolio"."opportunity_assessment" USING "btree" ("keyword_id");

--
-- Name: uq_portfolio_kw_metric_observation; Type: INDEX; Schema: portfolio; Owner: -
--

CREATE UNIQUE INDEX "uq_portfolio_kw_metric_observation" ON "portfolio"."keyword_metric_observation" USING "btree" ("keyword_id", "provider_code", "metric_type", "country_code", "device", "observed_date");

--
-- Name: release_decision trg_ai_00_release_task_serialization; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_00_release_task_serialization" BEFORE UPDATE ON "ai"."release_decision" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_release_task_serialization"();

--
-- Name: evaluation_case trg_ai_eval_case_mutation; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_eval_case_mutation" BEFORE INSERT OR DELETE OR UPDATE ON "ai"."evaluation_case" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_evaluation_case_mutation"();

--
-- Name: evaluation_case_result trg_ai_eval_case_result_immutable; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_eval_case_result_immutable" BEFORE DELETE OR UPDATE ON "ai"."evaluation_case_result" FOR EACH ROW EXECUTE FUNCTION "ops"."reject_immutable_mutation"();

--
-- Name: evaluation_case_result trg_ai_eval_case_result_open_run; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_eval_case_result_open_run" BEFORE INSERT ON "ai"."evaluation_case_result" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_open_evaluation_run_result"();

--
-- Name: evaluation_dataset_version trg_ai_eval_dataset_locked; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_eval_dataset_locked" BEFORE INSERT OR DELETE OR UPDATE ON "ai"."evaluation_dataset_version" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_locked_evaluation_dataset"();

--
-- Name: evaluation_result trg_ai_eval_metric_mutation; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_eval_metric_mutation" BEFORE INSERT OR DELETE OR UPDATE ON "ai"."evaluation_result" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_evaluation_metric_mutation"();

--
-- Name: evaluation_run trg_ai_eval_run_completion_evidence; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_eval_run_completion_evidence" BEFORE UPDATE ON "ai"."evaluation_run" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_evaluation_run_completion_evidence"();

--
-- Name: evaluation_run trg_ai_eval_run_mutation; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_eval_run_mutation" BEFORE INSERT OR DELETE OR UPDATE ON "ai"."evaluation_run" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_evaluation_run_mutation"();

--
-- Name: evaluation_run trg_ai_eval_run_start_integrity; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_eval_run_start_integrity" BEFORE INSERT OR UPDATE ON "ai"."evaluation_run" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_evaluation_run_start_integrity"();

--
-- Name: evaluation_suite trg_ai_eval_suite_canonical_config; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_eval_suite_canonical_config" BEFORE INSERT OR UPDATE ON "ai"."evaluation_suite" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_canonical_suite_config"();

--
-- Name: evaluation_suite trg_ai_eval_suite_mutation; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_eval_suite_mutation" BEFORE INSERT OR DELETE OR UPDATE ON "ai"."evaluation_suite" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_evaluation_suite_mutation"();

--
-- Name: ai_attempt trg_ai_evaluated_attempt_immutable; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_evaluated_attempt_immutable" BEFORE DELETE OR UPDATE ON "ai"."ai_attempt" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_evaluated_attempt_immutability"();

--
-- Name: ai_job trg_ai_evaluated_job_binding; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_evaluated_job_binding" BEFORE DELETE OR UPDATE ON "ai"."ai_job" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_evaluated_job_binding"();

--
-- Name: human_evaluation trg_ai_human_eval_immutable; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_human_eval_immutable" BEFORE DELETE OR UPDATE ON "ai"."human_evaluation" FOR EACH ROW EXECUTE FUNCTION "ops"."reject_immutable_mutation"();

--
-- Name: human_evaluation trg_ai_human_eval_open_run; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_human_eval_open_run" BEFORE INSERT ON "ai"."human_evaluation" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_open_human_evaluation"();

--
-- Name: ai_job trg_ai_job_approved_packet; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_job_approved_packet" BEFORE INSERT OR UPDATE OF "source_packet_version_id" ON "ai"."ai_job" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_approved_source_packet"();

--
-- Name: judge_calibration trg_ai_judge_cal_mutation; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_judge_cal_mutation" BEFORE INSERT OR DELETE OR UPDATE ON "ai"."judge_calibration" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_judge_calibration_mutation"();

--
-- Name: judge_calibration trg_ai_judge_cal_scope; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_judge_cal_scope" BEFORE INSERT OR UPDATE ON "ai"."judge_calibration" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_judge_calibration_scope"();

--
-- Name: model_definition trg_ai_model_definition_lifecycle; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_model_definition_lifecycle" BEFORE INSERT OR DELETE OR UPDATE ON "ai"."model_definition" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_model_definition_lifecycle"();

--
-- Name: model_definition trg_ai_model_dependency_guard; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_model_dependency_guard" BEFORE DELETE OR UPDATE ON "ai"."model_definition" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_governance_component_dependency"();

--
-- Name: model_route_version trg_ai_model_route_lifecycle; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_model_route_lifecycle" BEFORE INSERT OR DELETE OR UPDATE ON "ai"."model_route_version" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_model_route_lifecycle"();

--
-- Name: output_schema_version trg_ai_output_schema_lifecycle; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_output_schema_lifecycle" BEFORE INSERT OR DELETE OR UPDATE ON "ai"."output_schema_version" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_output_schema_lifecycle"();

--
-- Name: prompt_version trg_ai_prompt_dependency_guard; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_prompt_dependency_guard" BEFORE DELETE OR UPDATE ON "ai"."prompt_version" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_governance_component_dependency"();

--
-- Name: prompt_version trg_ai_prompt_version_lifecycle; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_prompt_version_lifecycle" BEFORE INSERT OR DELETE OR UPDATE ON "ai"."prompt_version" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_prompt_version_lifecycle"();

--
-- Name: release_approval trg_ai_release_approval_immutable; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_release_approval_immutable" BEFORE INSERT OR DELETE OR UPDATE ON "ai"."release_approval" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_release_approval_mutation"();

--
-- Name: release_decision trg_ai_release_decision_evidence; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_release_decision_evidence" BEFORE UPDATE ON "ai"."release_decision" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_release_decision_evidence"();

--
-- Name: release_decision trg_ai_release_decision_mutation; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_release_decision_mutation" BEFORE INSERT OR DELETE OR UPDATE ON "ai"."release_decision" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_release_decision_mutation"();

--
-- Name: model_route_version trg_ai_route_dependency_guard; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_route_dependency_guard" BEFORE DELETE OR UPDATE ON "ai"."model_route_version" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_governance_component_dependency"();

--
-- Name: output_schema_version trg_ai_schema_dependency_guard; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_schema_dependency_guard" BEFORE DELETE OR UPDATE ON "ai"."output_schema_version" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_governance_component_dependency"();

--
-- Name: task_definition trg_ai_task_definition_lifecycle; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_task_definition_lifecycle" BEFORE INSERT OR DELETE OR UPDATE ON "ai"."task_definition" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_task_definition_lifecycle"();

--
-- Name: task_definition trg_ai_task_dependency_guard; Type: TRIGGER; Schema: ai; Owner: -
--

CREATE TRIGGER "trg_ai_task_dependency_guard" BEFORE DELETE OR UPDATE ON "ai"."task_definition" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_governance_component_dependency"();

--
-- Name: affiliate_link_observation trg_catalog_affiliate_link_observation_immutable; Type: TRIGGER; Schema: catalog; Owner: -
--

CREATE TRIGGER "trg_catalog_affiliate_link_observation_immutable" BEFORE DELETE OR UPDATE ON "catalog"."affiliate_link_observation" FOR EACH ROW EXECUTE FUNCTION "ops"."reject_immutable_mutation"();

--
-- Name: attribute_definition trg_catalog_attribute_definition_touch; Type: TRIGGER; Schema: catalog; Owner: -
--

CREATE TRIGGER "trg_catalog_attribute_definition_touch" BEFORE UPDATE ON "catalog"."attribute_definition" FOR EACH ROW EXECUTE FUNCTION "ops"."touch_mutable_row"();

--
-- Name: availability_observation trg_catalog_availability_observation_immutable; Type: TRIGGER; Schema: catalog; Owner: -
--

CREATE TRIGGER "trg_catalog_availability_observation_immutable" BEFORE DELETE OR UPDATE ON "catalog"."availability_observation" FOR EACH ROW EXECUTE FUNCTION "ops"."reject_immutable_mutation"();

--
-- Name: canonical_product trg_catalog_canonical_product_touch; Type: TRIGGER; Schema: catalog; Owner: -
--

CREATE TRIGGER "trg_catalog_canonical_product_touch" BEFORE UPDATE ON "catalog"."canonical_product" FOR EACH ROW EXECUTE FUNCTION "ops"."touch_mutable_row"();

--
-- Name: grouping_decision trg_catalog_grouping_decision_immutable; Type: TRIGGER; Schema: catalog; Owner: -
--

CREATE TRIGGER "trg_catalog_grouping_decision_immutable" BEFORE DELETE OR UPDATE ON "catalog"."grouping_decision" FOR EACH ROW EXECUTE FUNCTION "ops"."reject_immutable_mutation"();

--
-- Name: offer trg_catalog_offer_touch; Type: TRIGGER; Schema: catalog; Owner: -
--

CREATE TRIGGER "trg_catalog_offer_touch" BEFORE UPDATE ON "catalog"."offer" FOR EACH ROW EXECUTE FUNCTION "ops"."touch_mutable_row"();

--
-- Name: price_observation trg_catalog_price_observation_immutable; Type: TRIGGER; Schema: catalog; Owner: -
--

CREATE TRIGGER "trg_catalog_price_observation_immutable" BEFORE DELETE OR UPDATE ON "catalog"."price_observation" FOR EACH ROW EXECUTE FUNCTION "ops"."reject_immutable_mutation"();

--
-- Name: product_candidate trg_catalog_product_candidate_touch; Type: TRIGGER; Schema: catalog; Owner: -
--

CREATE TRIGGER "trg_catalog_product_candidate_touch" BEFORE UPDATE ON "catalog"."product_candidate" FOR EACH ROW EXECUTE FUNCTION "ops"."touch_mutable_row"();

--
-- Name: rakuten_genre trg_catalog_rakuten_genre_touch; Type: TRIGGER; Schema: catalog; Owner: -
--

CREATE TRIGGER "trg_catalog_rakuten_genre_touch" BEFORE UPDATE ON "catalog"."rakuten_genre" FOR EACH ROW EXECUTE FUNCTION "ops"."touch_mutable_row"();

--
-- Name: review_aggregate_observation trg_catalog_review_aggregate_observation_immutable; Type: TRIGGER; Schema: catalog; Owner: -
--

CREATE TRIGGER "trg_catalog_review_aggregate_observation_immutable" BEFORE DELETE OR UPDATE ON "catalog"."review_aggregate_observation" FOR EACH ROW EXECUTE FUNCTION "ops"."reject_immutable_mutation"();

--
-- Name: shop trg_catalog_shop_touch; Type: TRIGGER; Schema: catalog; Owner: -
--

CREATE TRIGGER "trg_catalog_shop_touch" BEFORE UPDATE ON "catalog"."shop" FOR EACH ROW EXECUTE FUNCTION "ops"."touch_mutable_row"();

--
-- Name: article_version trg_editorial_article_content_bindings; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_article_content_bindings" BEFORE INSERT OR UPDATE ON "editorial"."article_version" FOR EACH ROW EXECUTE FUNCTION "editorial"."guard_article_content_bindings"();

--
-- Name: article_link trg_editorial_article_link_touch; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_article_link_touch" BEFORE UPDATE ON "editorial"."article_link" FOR EACH ROW EXECUTE FUNCTION "ops"."touch_mutable_row"();

--
-- Name: article_methodology_binding trg_editorial_article_methodology_artifact; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_article_methodology_artifact" BEFORE INSERT OR UPDATE ON "editorial"."article_methodology_binding" FOR EACH ROW EXECUTE FUNCTION "editorial"."guard_content_artifact_binding"();

--
-- Name: article_methodology_binding trg_editorial_article_methodology_cross_binding; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_article_methodology_cross_binding" BEFORE INSERT OR UPDATE ON "editorial"."article_methodology_binding" FOR EACH ROW EXECUTE FUNCTION "editorial"."guard_article_methodology_binding"();

--
-- Name: article_methodology_binding trg_editorial_article_methodology_immutable; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_article_methodology_immutable" BEFORE DELETE OR UPDATE ON "editorial"."article_methodology_binding" FOR EACH ROW EXECUTE FUNCTION "ops"."reject_immutable_mutation"();

--
-- Name: article_plan trg_editorial_article_plan_touch; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_article_plan_touch" BEFORE UPDATE ON "editorial"."article_plan" FOR EACH ROW EXECUTE FUNCTION "ops"."touch_mutable_row"();

--
-- Name: article_template_version trg_editorial_article_template_lifecycle; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_article_template_lifecycle" BEFORE INSERT OR DELETE OR UPDATE ON "editorial"."article_template_version" FOR EACH ROW EXECUTE FUNCTION "editorial"."guard_versioned_content_mutation"();

--
-- Name: article trg_editorial_article_touch; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_article_touch" BEFORE UPDATE ON "editorial"."article" FOR EACH ROW EXECUTE FUNCTION "ops"."touch_mutable_row"();

--
-- Name: article_type_version trg_editorial_article_type_lifecycle; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_article_type_lifecycle" BEFORE INSERT OR DELETE OR UPDATE ON "editorial"."article_type_version" FOR EACH ROW EXECUTE FUNCTION "editorial"."guard_versioned_content_mutation"();

--
-- Name: article_version trg_editorial_article_version_touch; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_article_version_touch" BEFORE UPDATE ON "editorial"."article_version" FOR EACH ROW EXECUTE FUNCTION "ops"."touch_mutable_row"();

--
-- Name: content_schema_version trg_editorial_content_schema_artifact; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_content_schema_artifact" BEFORE INSERT OR UPDATE ON "editorial"."content_schema_version" FOR EACH ROW EXECUTE FUNCTION "editorial"."guard_content_artifact_binding"();

--
-- Name: content_schema_version trg_editorial_content_schema_lifecycle; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_content_schema_lifecycle" BEFORE INSERT OR DELETE OR UPDATE ON "editorial"."content_schema_version" FOR EACH ROW EXECUTE FUNCTION "editorial"."guard_versioned_content_mutation"();

--
-- Name: article_disclosure_context trg_editorial_disclosure_lifecycle; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_disclosure_lifecycle" BEFORE INSERT OR DELETE OR UPDATE ON "editorial"."article_disclosure_context" FOR EACH ROW EXECUTE FUNCTION "editorial"."guard_disclosure_context_mutation"();

--
-- Name: media_asset trg_editorial_media_asset_artifact; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_media_asset_artifact" BEFORE INSERT OR UPDATE ON "editorial"."media_asset" FOR EACH ROW EXECUTE FUNCTION "editorial"."guard_content_artifact_binding"();

--
-- Name: media_asset trg_editorial_media_asset_lifecycle; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_media_asset_lifecycle" BEFORE INSERT OR DELETE OR UPDATE ON "editorial"."media_asset" FOR EACH ROW EXECUTE FUNCTION "editorial"."guard_media_asset_mutation"();

--
-- Name: editorial_methodology_version trg_editorial_methodology_lifecycle; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_methodology_lifecycle" BEFORE INSERT OR DELETE OR UPDATE ON "editorial"."editorial_methodology_version" FOR EACH ROW EXECUTE FUNCTION "editorial"."guard_versioned_content_mutation"();

--
-- Name: seo_metadata_version trg_editorial_seo_metadata_lifecycle; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_seo_metadata_lifecycle" BEFORE INSERT OR DELETE OR UPDATE ON "editorial"."seo_metadata_version" FOR EACH ROW EXECUTE FUNCTION "editorial"."guard_seo_metadata_mutation"();

--
-- Name: structured_data_manifest trg_editorial_structured_data_artifact; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_structured_data_artifact" BEFORE INSERT OR UPDATE ON "editorial"."structured_data_manifest" FOR EACH ROW EXECUTE FUNCTION "editorial"."guard_content_artifact_binding"();

--
-- Name: structured_data_manifest trg_editorial_structured_data_immutable; Type: TRIGGER; Schema: editorial; Owner: -
--

CREATE TRIGGER "trg_editorial_structured_data_immutable" BEFORE DELETE OR UPDATE ON "editorial"."structured_data_manifest" FOR EACH ROW EXECUTE FUNCTION "ops"."reject_immutable_mutation"();

--
-- Name: claim_evidence_link trg_evidence_claim_evidence_link_immutable; Type: TRIGGER; Schema: evidence; Owner: -
--

CREATE TRIGGER "trg_evidence_claim_evidence_link_immutable" BEFORE DELETE OR UPDATE ON "evidence"."claim_evidence_link" FOR EACH ROW EXECUTE FUNCTION "ops"."reject_immutable_mutation"();

--
-- Name: fact_derivation trg_evidence_fact_derivation_immutable; Type: TRIGGER; Schema: evidence; Owner: -
--

CREATE TRIGGER "trg_evidence_fact_derivation_immutable" BEFORE DELETE OR UPDATE ON "evidence"."fact_derivation" FOR EACH ROW EXECUTE FUNCTION "ops"."reject_immutable_mutation"();

--
-- Name: fact trg_evidence_fact_immutable; Type: TRIGGER; Schema: evidence; Owner: -
--

CREATE TRIGGER "trg_evidence_fact_immutable" BEFORE DELETE OR UPDATE ON "evidence"."fact" FOR EACH ROW EXECUTE FUNCTION "ops"."reject_immutable_mutation"();

--
-- Name: first_hand_experience_asset trg_evidence_first_hand_asset_artifact; Type: TRIGGER; Schema: evidence; Owner: -
--

CREATE TRIGGER "trg_evidence_first_hand_asset_artifact" BEFORE INSERT OR UPDATE ON "evidence"."first_hand_experience_asset" FOR EACH ROW EXECUTE FUNCTION "editorial"."guard_content_artifact_binding"();

--
-- Name: first_hand_experience_asset trg_evidence_first_hand_asset_immutable; Type: TRIGGER; Schema: evidence; Owner: -
--

CREATE TRIGGER "trg_evidence_first_hand_asset_immutable" BEFORE DELETE OR UPDATE ON "evidence"."first_hand_experience_asset" FOR EACH ROW EXECUTE FUNCTION "ops"."reject_immutable_mutation"();

--
-- Name: first_hand_experience_record trg_evidence_first_hand_lifecycle; Type: TRIGGER; Schema: evidence; Owner: -
--

CREATE TRIGGER "trg_evidence_first_hand_lifecycle" BEFORE INSERT OR DELETE OR UPDATE ON "evidence"."first_hand_experience_record" FOR EACH ROW EXECUTE FUNCTION "evidence"."guard_first_hand_experience_mutation"();

--
-- Name: source_packet_fact trg_evidence_source_packet_fact_immutable; Type: TRIGGER; Schema: evidence; Owner: -
--

CREATE TRIGGER "trg_evidence_source_packet_fact_immutable" BEFORE DELETE OR UPDATE ON "evidence"."source_packet_fact" FOR EACH ROW EXECUTE FUNCTION "ops"."reject_immutable_mutation"();

--
-- Name: source_packet_product trg_evidence_source_packet_product_immutable; Type: TRIGGER; Schema: evidence; Owner: -
--

CREATE TRIGGER "trg_evidence_source_packet_product_immutable" BEFORE DELETE OR UPDATE ON "evidence"."source_packet_product" FOR EACH ROW EXECUTE FUNCTION "ops"."reject_immutable_mutation"();

--
-- Name: source_packet trg_evidence_source_packet_touch; Type: TRIGGER; Schema: evidence; Owner: -
--

CREATE TRIGGER "trg_evidence_source_packet_touch" BEFORE UPDATE ON "evidence"."source_packet" FOR EACH ROW EXECUTE FUNCTION "ops"."touch_mutable_row"();

--
-- Name: source_snapshot trg_evidence_source_snapshot_immutable; Type: TRIGGER; Schema: evidence; Owner: -
--

CREATE TRIGGER "trg_evidence_source_snapshot_immutable" BEFORE DELETE OR UPDATE ON "evidence"."source_snapshot" FOR EACH ROW EXECUTE FUNCTION "ops"."reject_immutable_mutation"();

--
-- Name: source trg_evidence_source_touch; Type: TRIGGER; Schema: evidence; Owner: -
--

CREATE TRIGGER "trg_evidence_source_touch" BEFORE UPDATE ON "evidence"."source" FOR EACH ROW EXECUTE FUNCTION "ops"."touch_mutable_row"();

--
-- Name: policy_bundle trg_policy_bundle_dependency_guard; Type: TRIGGER; Schema: policy; Owner: -
--

CREATE TRIGGER "trg_policy_bundle_dependency_guard" BEFORE DELETE OR UPDATE ON "policy"."policy_bundle" FOR EACH ROW EXECUTE FUNCTION "ai"."guard_governance_component_dependency"();

--
-- Name: policy_bundle trg_policy_bundle_lifecycle; Type: TRIGGER; Schema: policy; Owner: -
--

CREATE TRIGGER "trg_policy_bundle_lifecycle" BEFORE INSERT OR DELETE OR UPDATE ON "policy"."policy_bundle" FOR EACH ROW EXECUTE FUNCTION "policy"."guard_policy_bundle_lifecycle"();

--
-- Name: bundle_rule trg_policy_bundle_rule_append_only; Type: TRIGGER; Schema: policy; Owner: -
--

CREATE TRIGGER "trg_policy_bundle_rule_append_only" BEFORE INSERT OR DELETE OR UPDATE ON "policy"."bundle_rule" FOR EACH ROW EXECUTE FUNCTION "policy"."guard_bundle_rule_append_only"();

--
-- Name: rule_version trg_policy_rule_version_immutable; Type: TRIGGER; Schema: policy; Owner: -
--

CREATE TRIGGER "trg_policy_rule_version_immutable" BEFORE DELETE OR UPDATE ON "policy"."rule_version" FOR EACH ROW EXECUTE FUNCTION "policy"."guard_rule_version_immutability"();

--
-- Name: action_candidate trg_portfolio_action_candidate_touch; Type: TRIGGER; Schema: portfolio; Owner: -
--

CREATE TRIGGER "trg_portfolio_action_candidate_touch" BEFORE UPDATE ON "portfolio"."action_candidate" FOR EACH ROW EXECUTE FUNCTION "ops"."touch_mutable_row"();

--
-- Name: category trg_portfolio_category_touch; Type: TRIGGER; Schema: portfolio; Owner: -
--

CREATE TRIGGER "trg_portfolio_category_touch" BEFORE UPDATE ON "portfolio"."category" FOR EACH ROW EXECUTE FUNCTION "ops"."touch_mutable_row"();

--
-- Name: intent_cluster trg_portfolio_intent_cluster_touch; Type: TRIGGER; Schema: portfolio; Owner: -
--

CREATE TRIGGER "trg_portfolio_intent_cluster_touch" BEFORE UPDATE ON "portfolio"."intent_cluster" FOR EACH ROW EXECUTE FUNCTION "ops"."touch_mutable_row"();

--
-- Name: keyword trg_portfolio_keyword_touch; Type: TRIGGER; Schema: portfolio; Owner: -
--

CREATE TRIGGER "trg_portfolio_keyword_touch" BEFORE UPDATE ON "portfolio"."keyword" FOR EACH ROW EXECUTE FUNCTION "ops"."touch_mutable_row"();

--
-- Name: site trg_portfolio_site_touch; Type: TRIGGER; Schema: portfolio; Owner: -
--

CREATE TRIGGER "trg_portfolio_site_touch" BEFORE UPDATE ON "portfolio"."site" FOR EACH ROW EXECUTE FUNCTION "ops"."touch_mutable_row"();

--
-- Name: ai_attempt fk_ai_ai_attempt_ai_job_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_attempt"
    ADD CONSTRAINT "fk_ai_ai_attempt_ai_job_id" FOREIGN KEY ("ai_job_id") REFERENCES "ai"."ai_job"("id") ON DELETE RESTRICT;

--
-- Name: ai_attempt fk_ai_ai_attempt_input_artifact_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_attempt"
    ADD CONSTRAINT "fk_ai_ai_attempt_input_artifact_id" FOREIGN KEY ("input_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: ai_attempt fk_ai_ai_attempt_model_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_attempt"
    ADD CONSTRAINT "fk_ai_ai_attempt_model_id" FOREIGN KEY ("model_id") REFERENCES "ai"."model_definition"("id") ON DELETE RESTRICT;

--
-- Name: ai_attempt fk_ai_ai_attempt_output_artifact_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_attempt"
    ADD CONSTRAINT "fk_ai_ai_attempt_output_artifact_id" FOREIGN KEY ("output_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: ai_job fk_ai_ai_job_article_plan_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_job"
    ADD CONSTRAINT "fk_ai_ai_job_article_plan_id" FOREIGN KEY ("article_plan_id") REFERENCES "editorial"."article_plan"("id") ON DELETE RESTRICT;

--
-- Name: ai_job fk_ai_ai_job_article_version_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_job"
    ADD CONSTRAINT "fk_ai_ai_job_article_version_id" FOREIGN KEY ("article_version_id") REFERENCES "editorial"."article_version"("id") ON DELETE RESTRICT;

--
-- Name: ai_job fk_ai_ai_job_model_route_version_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_job"
    ADD CONSTRAINT "fk_ai_ai_job_model_route_version_id" FOREIGN KEY ("model_route_version_id") REFERENCES "ai"."model_route_version"("id") ON DELETE RESTRICT;

--
-- Name: ai_job fk_ai_ai_job_ops_job_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_job"
    ADD CONSTRAINT "fk_ai_ai_job_ops_job_id" FOREIGN KEY ("ops_job_id") REFERENCES "ops"."job"("id") ON DELETE RESTRICT;

--
-- Name: ai_job fk_ai_ai_job_output_schema_version_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_job"
    ADD CONSTRAINT "fk_ai_ai_job_output_schema_version_id" FOREIGN KEY ("output_schema_version_id") REFERENCES "ai"."output_schema_version"("id") ON DELETE RESTRICT;

--
-- Name: ai_job fk_ai_ai_job_prompt_version_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_job"
    ADD CONSTRAINT "fk_ai_ai_job_prompt_version_id" FOREIGN KEY ("prompt_version_id") REFERENCES "ai"."prompt_version"("id") ON DELETE RESTRICT;

--
-- Name: ai_job fk_ai_ai_job_source_packet_version_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_job"
    ADD CONSTRAINT "fk_ai_ai_job_source_packet_version_id" FOREIGN KEY ("source_packet_version_id") REFERENCES "evidence"."source_packet_version"("id") ON DELETE RESTRICT;

--
-- Name: ai_job fk_ai_ai_job_task_definition_id; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."ai_job"
    ADD CONSTRAINT "fk_ai_ai_job_task_definition_id" FOREIGN KEY ("task_definition_id") REFERENCES "ai"."task_definition"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_case fk_ai_eval_case_dataset; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_case"
    ADD CONSTRAINT "fk_ai_eval_case_dataset" FOREIGN KEY ("dataset_version_id") REFERENCES "ai"."evaluation_dataset_version"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_case fk_ai_eval_case_gold; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_case"
    ADD CONSTRAINT "fk_ai_eval_case_gold" FOREIGN KEY ("gold_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_case fk_ai_eval_case_input; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_case"
    ADD CONSTRAINT "fk_ai_eval_case_input" FOREIGN KEY ("input_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_case_result fk_ai_eval_case_result_attempt; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_case_result"
    ADD CONSTRAINT "fk_ai_eval_case_result_attempt" FOREIGN KEY ("ai_attempt_id") REFERENCES "ai"."ai_attempt"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_case_result fk_ai_eval_case_result_case; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_case_result"
    ADD CONSTRAINT "fk_ai_eval_case_result_case" FOREIGN KEY ("evaluation_case_id") REFERENCES "ai"."evaluation_case"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_case_result fk_ai_eval_case_result_output; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_case_result"
    ADD CONSTRAINT "fk_ai_eval_case_result_output" FOREIGN KEY ("output_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_case_result fk_ai_eval_case_result_run; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_case_result"
    ADD CONSTRAINT "fk_ai_eval_case_result_run" FOREIGN KEY ("evaluation_run_id") REFERENCES "ai"."evaluation_run"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_case_result fk_ai_eval_case_result_zero_tolerance_artifact; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_case_result"
    ADD CONSTRAINT "fk_ai_eval_case_result_zero_tolerance_artifact" FOREIGN KEY ("zero_tolerance_evidence_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_case fk_ai_eval_case_task; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_case"
    ADD CONSTRAINT "fk_ai_eval_case_task" FOREIGN KEY ("task_definition_id") REFERENCES "ai"."task_definition"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_dataset_version fk_ai_eval_dataset_artifact; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_dataset_version"
    ADD CONSTRAINT "fk_ai_eval_dataset_artifact" FOREIGN KEY ("dataset_artifact_id") REFERENCES "ops"."object_artifact"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_dataset_version fk_ai_eval_dataset_locker; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_dataset_version"
    ADD CONSTRAINT "fk_ai_eval_dataset_locker" FOREIGN KEY ("locked_by_principal_id") REFERENCES "iam"."principal"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_result fk_ai_eval_result_case; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_result"
    ADD CONSTRAINT "fk_ai_eval_result_case" FOREIGN KEY ("evaluation_case_id") REFERENCES "ai"."evaluation_case"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_result fk_ai_eval_result_judge_cal; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_result"
    ADD CONSTRAINT "fk_ai_eval_result_judge_cal" FOREIGN KEY ("judge_calibration_id") REFERENCES "ai"."judge_calibration"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_result fk_ai_eval_result_judge_model; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_result"
    ADD CONSTRAINT "fk_ai_eval_result_judge_model" FOREIGN KEY ("judge_resolved_model_id") REFERENCES "ai"."model_definition"("id") ON DELETE RESTRICT;

--
-- Name: evaluation_result fk_ai_eval_result_judge_prompt; Type: FK CONSTRAINT; Schema: ai; Owner: -
--

ALTER TABLE ONLY "ai"."evaluation_result"
    ADD CONSTRAINT "fk_ai_eval_result_judge_prompt" FOREIGN KEY ("judge_prompt_version_id") REFERENCES "ai"."prompt_version"("id") ON DELETE RESTRICT;
