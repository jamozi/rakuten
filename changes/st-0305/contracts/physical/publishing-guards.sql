-- ST-0305 reviewed publication guard surface. Core table DDL is rendered
-- directly from the hash-pinned RAOS machine catalog by the Story generator.

CREATE FUNCTION publishing.guard_final_approval() RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path TO pg_catalog
AS $raos_st0305$
BEGIN
    IF NEW.approval_type <> 'FINAL' OR NEW.decision <> 'APPROVED' THEN
        RETURN NEW;
    END IF;

    IF NEW.revoked_at IS NOT NULL
       OR (NEW.valid_until IS NOT NULL
           AND NEW.valid_until <= pg_catalog.statement_timestamp()) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'ST0305_FINAL_APPROVAL_INACTIVE';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM iam.principal AS principal
        WHERE principal.id = NEW.approved_by_principal_id
          AND principal.principal_type = 'USER'
          AND principal.status = 'ACTIVE'
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'ST0305_FINAL_APPROVAL_REQUIRES_ACTIVE_USER';
    END IF;

    IF NEW.quality_check_run_id IS NULL OR NEW.policy_bundle_id IS NULL
       OR NOT EXISTS (
           SELECT 1
           FROM policy.quality_check_run AS quality_run
           JOIN editorial.article_version AS article_version
             ON article_version.id = quality_run.article_version_id
           JOIN evidence.source_packet_version AS source_packet_version
             ON source_packet_version.id = quality_run.source_packet_version_id
           WHERE quality_run.id = NEW.quality_check_run_id
             AND quality_run.article_version_id = NEW.article_version_id
             AND quality_run.policy_bundle_id = NEW.policy_bundle_id
             AND quality_run.status = 'PASSED'
             AND quality_run.blocking_finding_count = 0
             AND article_version.source_packet_version_id =
                 quality_run.source_packet_version_id
             AND source_packet_version.status = 'APPROVED'
             AND EXISTS (
                 SELECT 1
                 FROM policy.quality_score AS quality_score
                 WHERE quality_score.quality_check_run_id = quality_run.id
                   AND quality_score.passed IS TRUE
             )
       ) OR EXISTS (
           SELECT 1
           FROM policy.finding AS finding
           WHERE finding.quality_check_run_id = NEW.quality_check_run_id
             AND finding.is_blocking IS TRUE
             AND finding.status = 'OPEN'
       ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'ST0305_FINAL_APPROVAL_EVIDENCE_INVALID';
    END IF;

    RETURN NEW;
END
$raos_st0305$;

CREATE FUNCTION publishing.guard_publication_candidate() RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path TO pg_catalog
AS $raos_st0305$
BEGIN
    IF NEW.status IN ('BLOCKED', 'FAILED', 'CANCELLED') THEN
        RETURN NEW;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM publishing.approval AS approval
        JOIN iam.principal AS principal
          ON principal.id = approval.approved_by_principal_id
        JOIN policy.quality_check_run AS quality_run
          ON quality_run.id = NEW.quality_check_run_id
        JOIN editorial.article_version AS article_version
          ON article_version.id = NEW.article_version_id
        JOIN evidence.source_packet_version AS source_packet_version
          ON source_packet_version.id = quality_run.source_packet_version_id
        WHERE approval.id = NEW.final_approval_id
          AND approval.article_version_id = NEW.article_version_id
          AND approval.approval_type = 'FINAL'
          AND approval.decision = 'APPROVED'
          AND approval.revoked_at IS NULL
          AND (approval.valid_until IS NULL
               OR approval.valid_until > pg_catalog.statement_timestamp())
          AND approval.quality_check_run_id = quality_run.id
          AND approval.policy_bundle_id = quality_run.policy_bundle_id
          AND principal.principal_type = 'USER'
          AND principal.status = 'ACTIVE'
          AND quality_run.article_version_id = NEW.article_version_id
          AND quality_run.status = 'PASSED'
          AND quality_run.blocking_finding_count = 0
          AND article_version.source_packet_version_id =
              quality_run.source_packet_version_id
          AND source_packet_version.status = 'APPROVED'
          AND EXISTS (
              SELECT 1
              FROM policy.quality_score AS quality_score
              WHERE quality_score.quality_check_run_id = quality_run.id
                AND quality_score.passed IS TRUE
          )
          AND NOT EXISTS (
              SELECT 1
              FROM publishing.approval AS revocation
              WHERE revocation.supersedes_approval_id = approval.id
                AND revocation.decision = 'REVOKED'
          )
          AND NOT EXISTS (
              SELECT 1
              FROM policy.finding AS finding
              WHERE finding.quality_check_run_id = quality_run.id
                AND finding.is_blocking IS TRUE
                AND finding.status = 'OPEN'
          )
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'ST0305_PUBLICATION_CANDIDATE_NOT_APPROVED';
    END IF;

    RETURN NEW;
END
$raos_st0305$;

CREATE FUNCTION publishing.guard_publication_transition() RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path TO pg_catalog
AS $raos_st0305$
DECLARE
    category_id uuid;
    engaged boolean;
BEGIN
    IF NEW.state <> 'PUBLISHED' THEN
        RETURN NEW;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM publishing.publication_snapshot AS snapshot
        JOIN publishing.publication_candidate AS candidate
          ON candidate.id = snapshot.publication_candidate_id
        JOIN editorial.article_version AS article_version
          ON article_version.id = snapshot.article_version_id
        JOIN editorial.article AS article
          ON article.id = snapshot.article_id
        JOIN publishing.approval AS approval
          ON approval.id = snapshot.final_approval_id
        JOIN iam.principal AS principal
          ON principal.id = approval.approved_by_principal_id
        JOIN policy.quality_check_run AS quality_run
          ON quality_run.id = snapshot.quality_check_run_id
        JOIN policy.quality_score AS quality_score
          ON quality_score.quality_check_run_id = quality_run.id
        JOIN evidence.source_packet_version AS source_packet_version
          ON source_packet_version.id = snapshot.source_packet_version_id
        WHERE snapshot.id = NEW.current_snapshot_id
          AND snapshot.site_id = NEW.site_id
          AND snapshot.article_id = NEW.article_id
          AND article.id = NEW.article_id
          AND article.site_id = NEW.site_id
          AND article_version.article_id = NEW.article_id
          AND article_version.source_packet_version_id =
              snapshot.source_packet_version_id
          AND candidate.site_id = snapshot.site_id
          AND candidate.article_version_id = snapshot.article_version_id
          AND candidate.final_approval_id = snapshot.final_approval_id
          AND candidate.quality_check_run_id = snapshot.quality_check_run_id
          AND candidate.publication_snapshot_id = snapshot.id
          AND candidate.status IN ('SNAPSHOT_READY', 'PUBLISHED')
          AND approval.article_version_id = snapshot.article_version_id
          AND approval.quality_check_run_id = quality_run.id
          AND approval.policy_bundle_id = quality_run.policy_bundle_id
          AND approval.approval_type = 'FINAL'
          AND approval.decision = 'APPROVED'
          AND approval.revoked_at IS NULL
          AND (approval.valid_until IS NULL
               OR approval.valid_until > pg_catalog.statement_timestamp())
          AND principal.principal_type = 'USER'
          AND principal.status = 'ACTIVE'
          AND quality_run.article_version_id = snapshot.article_version_id
          AND quality_run.source_packet_version_id =
              snapshot.source_packet_version_id
          AND quality_run.policy_bundle_id = snapshot.policy_bundle_id
          AND quality_run.status = 'PASSED'
          AND quality_run.blocking_finding_count = 0
          AND quality_score.passed IS TRUE
          AND source_packet_version.status = 'APPROVED'
          AND NOT EXISTS (
              SELECT 1
              FROM publishing.approval AS revocation
              WHERE revocation.supersedes_approval_id = approval.id
                AND revocation.decision = 'REVOKED'
          )
          AND NOT EXISTS (
              SELECT 1
              FROM policy.finding AS finding
              WHERE finding.quality_check_run_id = quality_run.id
                AND finding.is_blocking IS TRUE
                AND finding.status = 'OPEN'
          )
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'ST0305_PUBLICATION_SNAPSHOT_NOT_APPROVED';
    END IF;

    SELECT article_plan.category_id
      INTO category_id
      FROM editorial.article AS article
      JOIN editorial.article_plan AS article_plan
        ON article_plan.id = article.article_plan_id
     WHERE article.id = NEW.article_id;

    BEGIN
        SELECT COALESCE(pg_catalog.bool_or(kill_switch.is_engaged), false)
          INTO engaged
          FROM ops.kill_switch AS kill_switch
         WHERE kill_switch.switch_type = 'PUBLICATION'
           AND (kill_switch.expires_at IS NULL
                OR kill_switch.expires_at > pg_catalog.statement_timestamp())
           AND (
               kill_switch.scope_type = 'GLOBAL'
               OR (kill_switch.scope_type = 'SITE'
                   AND kill_switch.scope_id = NEW.site_id)
               OR (kill_switch.scope_type = 'CATEGORY'
                   AND kill_switch.scope_id = category_id)
               OR (kill_switch.scope_type = 'ARTICLE'
                   AND kill_switch.scope_id = NEW.article_id)
           );
    EXCEPTION
        WHEN undefined_table THEN
            RAISE EXCEPTION USING ERRCODE = '55000',
                MESSAGE = 'ST0305_KILL_SWITCH_UNAVAILABLE';
    END;

    IF engaged THEN
        RAISE EXCEPTION USING ERRCODE = '55000',
            MESSAGE = 'ST0305_PUBLICATION_KILL_SWITCH_ENGAGED';
    END IF;

    RETURN NEW;
END
$raos_st0305$;

REVOKE ALL ON FUNCTION publishing.guard_final_approval() FROM PUBLIC;
REVOKE ALL ON FUNCTION publishing.guard_publication_candidate() FROM PUBLIC;
REVOKE ALL ON FUNCTION publishing.guard_publication_transition() FROM PUBLIC;

COMMENT ON FUNCTION publishing.guard_final_approval() IS
    'Require an active human user, matching passed quality evidence, an approved source packet, and zero unresolved blocking findings for FINAL approval.';
COMMENT ON FUNCTION publishing.guard_publication_candidate() IS
    'Reject an active publication candidate unless its final approval and matching quality evidence remain valid.';
COMMENT ON FUNCTION publishing.guard_publication_transition() IS
    'Fail closed on publication when approved snapshot lineage is absent or the publication kill-switch surface is unavailable or engaged.';

CREATE TRIGGER trg_publishing_approval_guard
BEFORE INSERT OR UPDATE ON publishing.approval
FOR EACH ROW EXECUTE FUNCTION publishing.guard_final_approval();
CREATE TRIGGER trg_publishing_candidate_guard
BEFORE INSERT OR UPDATE ON publishing.publication_candidate
FOR EACH ROW EXECUTE FUNCTION publishing.guard_publication_candidate();
CREATE TRIGGER trg_publishing_publication_guard
BEFORE INSERT OR UPDATE ON publishing.publication
FOR EACH ROW EXECUTE FUNCTION publishing.guard_publication_transition();

CREATE TRIGGER trg_publishing_review_assignment_touch BEFORE UPDATE ON publishing.review_assignment FOR EACH ROW EXECUTE FUNCTION ops.touch_mutable_row();
CREATE TRIGGER trg_publishing_publication_candidate_touch BEFORE UPDATE ON publishing.publication_candidate FOR EACH ROW EXECUTE FUNCTION ops.touch_mutable_row();
CREATE TRIGGER trg_publishing_publication_touch BEFORE UPDATE ON publishing.publication FOR EACH ROW EXECUTE FUNCTION ops.touch_mutable_row();
CREATE TRIGGER trg_publishing_public_route_touch BEFORE UPDATE ON publishing.public_route FOR EACH ROW EXECUTE FUNCTION ops.touch_mutable_row();
CREATE TRIGGER trg_freshness_refresh_schedule_touch BEFORE UPDATE ON freshness.refresh_schedule FOR EACH ROW EXECUTE FUNCTION ops.touch_mutable_row();
CREATE TRIGGER trg_finance_revenue_import_touch BEFORE UPDATE ON finance.revenue_import FOR EACH ROW EXECUTE FUNCTION ops.touch_mutable_row();
CREATE TRIGGER trg_finance_commission_touch BEFORE UPDATE ON finance.commission FOR EACH ROW EXECUTE FUNCTION ops.touch_mutable_row();

CREATE TRIGGER trg_publishing_review_decision_immutable BEFORE DELETE OR UPDATE ON publishing.review_decision FOR EACH ROW EXECUTE FUNCTION ops.reject_immutable_mutation();
CREATE TRIGGER trg_publishing_publication_snapshot_immutable BEFORE DELETE OR UPDATE ON publishing.publication_snapshot FOR EACH ROW EXECUTE FUNCTION ops.reject_immutable_mutation();
CREATE TRIGGER trg_publishing_publication_event_immutable BEFORE DELETE OR UPDATE ON publishing.publication_event FOR EACH ROW EXECUTE FUNCTION ops.reject_immutable_mutation();
CREATE TRIGGER trg_analytics_anonymous_event_immutable BEFORE DELETE OR UPDATE ON analytics.anonymous_event FOR EACH ROW EXECUTE FUNCTION ops.reject_immutable_mutation();
CREATE TRIGGER trg_analytics_affiliate_click_event_immutable BEFORE DELETE OR UPDATE ON analytics.affiliate_click_event FOR EACH ROW EXECUTE FUNCTION ops.reject_immutable_mutation();
CREATE TRIGGER trg_finance_commission_event_immutable BEFORE DELETE OR UPDATE ON finance.commission_event FOR EACH ROW EXECUTE FUNCTION ops.reject_immutable_mutation();
CREATE TRIGGER trg_finance_cost_allocation_immutable BEFORE DELETE OR UPDATE ON finance.cost_allocation FOR EACH ROW EXECUTE FUNCTION ops.reject_immutable_mutation();
