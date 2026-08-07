-- ST-0304 deterministic no-write PostgreSQL 18.4 domain-schema validation.
-- Execute as the migration owner with TimeZone=UTC and search_path=pg_catalog.
DO $raos_st0304_validation$
DECLARE
    mismatch_count pg_catalog.int8;
    observed_count pg_catalog.int8;
BEGIN
    IF pg_catalog.current_setting('server_version_num')::pg_catalog.int4 <> 180004 THEN
        RAISE EXCEPTION 'ST0304_SERVER_VERSION_MISMATCH';
    END IF;
    IF pg_catalog.current_setting('TimeZone') <> 'UTC' THEN
        RAISE EXCEPTION 'ST0304_TIMEZONE_MISMATCH';
    END IF;
    IF pg_catalog.current_setting('search_path') <> 'pg_catalog' THEN
        RAISE EXCEPTION 'ST0304_SEARCH_PATH_MISMATCH';
    END IF;
    IF (SELECT version_num FROM public.raos_migration_version) <> '202608030004' THEN
        RAISE EXCEPTION 'ST0304_HEAD_MISMATCH';
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM public.raos_migration_history
        WHERE revision_id = '202608030004'
          AND story_id = 'ST-0304'
          AND direction = 'UPGRADE'
          AND status = 'SUCCEEDED'
          AND source_sha256 = '632fc5146a57e2c7768745e3ed665aba0f91f229afc174c17fca8e9e2d88c407'
          AND runner_version = '1.3.0'
          AND server_version_num = 180004
    ) THEN
        RAISE EXCEPTION 'ST0304_HISTORY_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        ('portfolio', 'サイト、カテゴリ、検索意図、キーワード、機会評価、優先アクション'),
        ('catalog', '楽天取得、商品同定、ショップ、Offer、外部事実Observation、Current Projection'),
        ('evidence', 'Source、Snapshot、Fact、Source Packet、Claim、根拠対応'),
        ('editorial', '記事企画、構造化記事版、比較、推薦、レビューコメント、内部リンク'),
        ('ai', 'AI Task、Prompt、Schema、Model Route、Job、Attempt、Token・費用、評価'),
        ('policy', 'Policy Bundle、Rule、品質検査、Finding、Score、Waiver、Gate')
    ) AS expected(schema_name, schema_comment)
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    WHERE pg_catalog.pg_get_userbyid(namespace.nspowner) = current_user
      AND pg_catalog.obj_description(namespace.oid, 'pg_namespace') =
          expected.schema_comment
      AND NOT EXISTS (
          SELECT 1
          FROM pg_catalog.aclexplode(
              COALESCE(
                  namespace.nspacl,
                  pg_catalog.acldefault('n', namespace.nspowner)
              )
          ) AS acl
          WHERE acl.grantee <> namespace.nspowner
      );
    IF observed_count <> 6 THEN
        RAISE EXCEPTION 'ST0304_SCHEMA_CATALOG_MISMATCH';
    END IF;

    WITH selected(schema_name) AS (
        VALUES ('portfolio'), ('catalog'), ('evidence'),
               ('editorial'), ('ai'), ('policy')
    ),
    relation_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\x1f', namespace.nspname, relation.relname,
                   relation.relkind, relation.relpersistence,
                   relation.relreplident, relation.relrowsecurity,
                   relation.relforcerowsecurity,
                   COALESCE(
                       pg_catalog.array_to_string(relation.reloptions, E'\x1d'),
                       '<NULL>'
                   ),
                   COALESCE(
                       pg_catalog.obj_description(relation.oid, 'pg_class'),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        JOIN selected ON selected.schema_name = namespace.nspname
        WHERE relation.relkind IN ('r', 'v')
    ),
    column_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\x1f', namespace.nspname, relation.relname,
                   attribute.attnum, attribute.attname,
                   pg_catalog.format_type(
                       attribute.atttypid, attribute.atttypmod
                   ),
                   attribute.attnotnull, attribute.attidentity,
                   attribute.attgenerated, attribute.attisdropped,
                   COALESCE(
                       pg_catalog.pg_get_expr(
                           attribute_default.adbin,
                           attribute_default.adrelid,
                           false
                       ),
                       '<NULL>'
                   ),
                   COALESCE(
                       collation_namespace.nspname || '.'
                       || collation_record.collname,
                       '<NULL>'
                   ),
                   attribute.attstorage, attribute.attcompression,
                   attribute.attstattarget,
                   COALESCE(
                       pg_catalog.col_description(
                           relation.oid, attribute.attnum
                       ),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        JOIN selected ON selected.schema_name = namespace.nspname
        JOIN pg_catalog.pg_attribute AS attribute
          ON attribute.attrelid = relation.oid
         AND attribute.attnum > 0
        LEFT JOIN pg_catalog.pg_attrdef AS attribute_default
          ON attribute_default.adrelid = relation.oid
         AND attribute_default.adnum = attribute.attnum
        LEFT JOIN pg_catalog.pg_collation AS collation_record
          ON collation_record.oid = attribute.attcollation
        LEFT JOIN pg_catalog.pg_namespace AS collation_namespace
          ON collation_namespace.oid = collation_record.collnamespace
        WHERE relation.relkind = 'r'
    ),
    constraint_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\x1f', namespace.nspname, relation.relname,
                   constraint_record.conname, constraint_record.contype,
                   constraint_record.condeferrable,
                   constraint_record.condeferred,
                   constraint_record.convalidated,
                   constraint_record.connoinherit,
                   constraint_record.confmatchtype,
                   constraint_record.confupdtype,
                   constraint_record.confdeltype,
                   COALESCE(
                       pg_catalog.pg_get_constraintdef(
                           constraint_record.oid, false
                       ),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        JOIN selected ON selected.schema_name = namespace.nspname
        WHERE constraint_record.contype IN ('c', 'f', 'n', 'p', 'u')
    ),
    index_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\x1f', namespace.nspname, table_record.relname,
                   index_record.relname, index_catalog.indisunique,
                   index_catalog.indisprimary,
                   index_catalog.indisexclusion,
                   index_catalog.indimmediate,
                   index_catalog.indisclustered,
                   index_catalog.indisvalid, index_catalog.indisready,
                   index_catalog.indislive, index_catalog.indisreplident,
                   index_catalog.indnullsnotdistinct,
                   index_catalog.indnkeyatts, index_catalog.indnatts,
                   index_catalog.indkey::pg_catalog.text,
                   index_catalog.indcollation::pg_catalog.text,
                   index_catalog.indclass::pg_catalog.text,
                   index_catalog.indoption::pg_catalog.text,
                   pg_catalog.pg_get_indexdef(index_record.oid, 0, false),
                   COALESCE(
                       pg_catalog.pg_get_expr(
                           index_catalog.indpred,
                           index_catalog.indrelid,
                           false
                       ),
                       '<NULL>'
                   ),
                   COALESCE(
                       pg_catalog.pg_get_expr(
                           index_catalog.indexprs,
                           index_catalog.indrelid,
                           false
                       ),
                       '<NULL>'
                   ),
                   COALESCE(
                       pg_catalog.obj_description(
                           index_record.oid, 'pg_class'
                       ),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_index AS index_catalog
        JOIN pg_catalog.pg_class AS index_record
          ON index_record.oid = index_catalog.indexrelid
        JOIN pg_catalog.pg_class AS table_record
          ON table_record.oid = index_catalog.indrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = table_record.relnamespace
        JOIN selected ON selected.schema_name = namespace.nspname
    ),
    function_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\x1f', namespace.nspname, routine.proname,
                   pg_catalog.pg_get_function_identity_arguments(routine.oid),
                   pg_catalog.pg_get_function_result(routine.oid),
                   language_record.lanname, routine.provolatile,
                   routine.proisstrict, routine.prosecdef,
                   routine.proleakproof, routine.proparallel,
                   COALESCE(
                       pg_catalog.array_to_string(routine.proconfig, E'\x1d'),
                       '<NULL>'
                   ),
                   pg_catalog.pg_get_functiondef(routine.oid),
                   COALESCE(
                       pg_catalog.obj_description(routine.oid, 'pg_proc'),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_proc AS routine
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = routine.pronamespace
        JOIN selected ON selected.schema_name = namespace.nspname
        JOIN pg_catalog.pg_language AS language_record
          ON language_record.oid = routine.prolang
        WHERE routine.prokind = 'f'
    ),
    trigger_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\x1f', namespace.nspname, relation.relname,
                   trigger_record.tgname, trigger_record.tgtype,
                   trigger_record.tgenabled, trigger_record.tgisinternal,
                   routine_namespace.nspname, routine.proname,
                   pg_catalog.pg_get_function_identity_arguments(routine.oid),
                   pg_catalog.pg_get_triggerdef(trigger_record.oid, false),
                   COALESCE(
                       pg_catalog.pg_get_expr(
                           trigger_record.tgqual,
                           trigger_record.tgrelid,
                           false
                       ),
                       '<NULL>'
                   ),
                   COALESCE(
                       pg_catalog.obj_description(
                           trigger_record.oid, 'pg_trigger'
                       ),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_trigger AS trigger_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = trigger_record.tgrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        JOIN selected ON selected.schema_name = namespace.nspname
        JOIN pg_catalog.pg_proc AS routine
          ON routine.oid = trigger_record.tgfoid
        JOIN pg_catalog.pg_namespace AS routine_namespace
          ON routine_namespace.oid = routine.pronamespace
        WHERE trigger_record.tgisinternal IS FALSE
    ),
    observed(kind, object_count, digest) AS (
        SELECT 'relations', pg_catalog.count(*),
               pg_catalog.md5(
                   pg_catalog.string_agg(row_value, E'\x1e' ORDER BY row_value)
               )
        FROM relation_rows
        UNION ALL
        SELECT 'columns', pg_catalog.count(*),
               pg_catalog.md5(
                   pg_catalog.string_agg(row_value, E'\x1e' ORDER BY row_value)
               )
        FROM column_rows
        UNION ALL
        SELECT 'constraints', pg_catalog.count(*),
               pg_catalog.md5(
                   pg_catalog.string_agg(row_value, E'\x1e' ORDER BY row_value)
               )
        FROM constraint_rows
        UNION ALL
        SELECT 'indexes', pg_catalog.count(*),
               pg_catalog.md5(
                   pg_catalog.string_agg(row_value, E'\x1e' ORDER BY row_value)
               )
        FROM index_rows
        UNION ALL
        SELECT 'functions', pg_catalog.count(*),
               pg_catalog.md5(
                   pg_catalog.string_agg(row_value, E'\x1e' ORDER BY row_value)
               )
        FROM function_rows
        UNION ALL
        SELECT 'triggers', pg_catalog.count(*),
               pg_catalog.md5(
                   pg_catalog.string_agg(row_value, E'\x1e' ORDER BY row_value)
               )
        FROM trigger_rows
    ),
    expected(kind, object_count, digest) AS (
        VALUES
        ('relations', 87, '692fe9230d7c72823ceb716758d16b9d'),
        ('columns', 1141, 'ed47ed9dad9060fcf55573143653de09'),
        ('constraints', 1757, 'cf4c5ac88bf3476e433de1f35c48af6e'),
        ('indexes', 453, 'b5049f3b168dad1bb7dfe6296f0d60e6'),
        ('functions', 48, '5e994dea08bd1b7f9fe80cf0e23b0951'),
        ('triggers', 81, '7ec669ff04f1c99c5d144b3e234983bf')
    )
    SELECT pg_catalog.count(*) INTO mismatch_count
    FROM expected
    FULL JOIN observed USING (kind)
    WHERE expected.object_count IS DISTINCT FROM observed.object_count
       OR expected.digest IS DISTINCT FROM observed.digest;
    IF mismatch_count <> 0 THEN
        RAISE EXCEPTION 'ST0304_PHYSICAL_CATALOG_DIGEST_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        ('editorial', 'article_disclosure_context'),
        ('editorial', 'article_methodology_binding'),
        ('editorial', 'article_template_version'),
        ('editorial', 'article_type_version'),
        ('editorial', 'content_schema_version'),
        ('editorial', 'editorial_methodology_version'),
        ('editorial', 'media_asset'),
        ('editorial', 'seo_metadata_version'),
        ('editorial', 'structured_data_manifest'),
        ('evidence', 'first_hand_experience_asset'),
        ('evidence', 'first_hand_experience_record')
    ) AS expected(schema_name, table_name)
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = namespace.oid
     AND relation.relname = expected.table_name
     AND relation.relkind = 'r'
    WHERE relation.relrowsecurity IS TRUE
      AND relation.relforcerowsecurity IS TRUE;
    IF observed_count <> 11 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_policy AS policy_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = policy_record.polrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY(
            ARRAY['portfolio','catalog','evidence','editorial','ai','policy']
        )
    ) <> 0 THEN
        RAISE EXCEPTION 'ST0304_RLS_BOUNDARY_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM pg_catalog.pg_constraint AS constraint_record
    WHERE constraint_record.conname = 'fk_ops_job_site_id'
      AND constraint_record.conrelid = 'ops.job'::pg_catalog.regclass
      AND constraint_record.confrelid = 'portfolio.site'::pg_catalog.regclass
      AND constraint_record.contype = 'f'
      AND constraint_record.convalidated IS TRUE
      AND constraint_record.condeferrable IS FALSE
      AND constraint_record.condeferred IS FALSE
      AND constraint_record.confupdtype = 'a'
      AND constraint_record.confdeltype = 'r'
      AND constraint_record.confmatchtype = 's'
      AND pg_catalog.pg_get_constraintdef(constraint_record.oid, false) =
          'FOREIGN KEY (site_id) REFERENCES portfolio.site(id) ON DELETE RESTRICT';
    IF observed_count <> 1 OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conname = 'fk_iam_break_glass_record_incident_id'
    ) THEN
        RAISE EXCEPTION 'ST0304_DEFERRED_FOREIGN_KEY_MISMATCH';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(
                relation.relacl,
                pg_catalog.acldefault('r', relation.relowner)
            )
        ) AS acl
        WHERE namespace.nspname = ANY(
            ARRAY['portfolio','catalog','evidence','editorial','ai','policy']
        )
          AND relation.relkind IN ('r', 'v')
          AND acl.grantee <> relation.relowner
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc AS routine
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = routine.pronamespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(
                routine.proacl,
                pg_catalog.acldefault('f', routine.proowner)
            )
        ) AS acl
        WHERE namespace.nspname = ANY(
            ARRAY['portfolio','catalog','evidence','editorial','ai','policy']
        )
          AND acl.grantee <> routine.proowner
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_default_acl AS default_acl
        LEFT JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = default_acl.defaclnamespace
        WHERE default_acl.defaclnamespace = 0
           OR namespace.nspname = ANY(
                  ARRAY['portfolio','catalog','evidence','editorial','ai','policy']
              )
    ) THEN
        RAISE EXCEPTION 'ST0304_PUBLIC_OR_DEFAULT_ACL_MISMATCH';
    END IF;
END
$raos_st0304_validation$;

SELECT 'PASS'::pg_catalog.text AS status,
       86::pg_catalog.int4 AS tables,
       1141::pg_catalog.int4 AS columns,
       265::pg_catalog.int4 AS scope_foreign_keys,
       11::pg_catalog.int4 AS rls_forced_tables,
       0::pg_catalog.int4 AS rls_policies;
