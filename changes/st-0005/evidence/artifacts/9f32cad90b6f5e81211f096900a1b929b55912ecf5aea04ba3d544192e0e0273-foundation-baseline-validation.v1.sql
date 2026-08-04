-- ST-0302 deterministic PostgreSQL 18.4 foundation validation.
-- Execute as the migration owner after upgrading to revision 202608030002.
DO $raos_st0302$
DECLARE
    observed_count bigint;
    sample_id uuid;
BEGIN
    IF current_setting('server_version_num')::integer <> 180004 THEN
        RAISE EXCEPTION 'ST0302_SERVER_VERSION_MISMATCH';
    END IF;

    IF current_setting('TimeZone') <> 'UTC' THEN
        RAISE EXCEPTION 'ST0302_TIMEZONE_MISMATCH';
    END IF;

    SELECT count(*) INTO observed_count
    FROM pg_catalog.pg_namespace AS n
    WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
      AND pg_catalog.pg_get_userbyid(n.nspowner) = current_user
      AND pg_catalog.obj_description(n.oid, 'pg_namespace') = CASE n.nspname
          WHEN 'ops' THEN 'ジョブ、原本レジストリ、監査、障害、Kill Switch、実行時設定'
          WHEN 'iam' THEN 'OIDC主体、アプリケーションRole、権限、緊急アクセス'
      END;
    IF observed_count <> 2 THEN
        RAISE EXCEPTION 'ST0302_SCHEMA_METADATA_MISMATCH';
    END IF;

    SELECT count(*) INTO observed_count
    FROM pg_catalog.pg_namespace AS n
    WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
      AND (
          SELECT COALESCE(
              array_agg(acl.privilege_type ORDER BY acl.privilege_type),
              ARRAY[]::text[]
          )
          FROM pg_catalog.aclexplode(
              COALESCE(n.nspacl, pg_catalog.acldefault('n', n.nspowner))
          ) AS acl
          WHERE acl.grantee = n.nspowner
      ) = ARRAY['CREATE', 'USAGE']::text[]
      AND NOT EXISTS (
          SELECT 1
          FROM pg_catalog.aclexplode(
              COALESCE(n.nspacl, pg_catalog.acldefault('n', n.nspowner))
          ) AS acl
          WHERE acl.grantee <> n.nspowner
      );
    IF observed_count <> 2 THEN
        RAISE EXCEPTION 'ST0302_SCHEMA_PRIVILEGE_MISMATCH';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_default_acl AS defaults
        LEFT JOIN pg_catalog.pg_namespace AS n
          ON n.oid = defaults.defaclnamespace
        WHERE defaults.defaclnamespace = 0
           OR n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) THEN
        RAISE EXCEPTION 'ST0302_FOUNDATION_DEFAULT_PRIVILEGE';
    END IF;

    SELECT count(*) INTO observed_count
    FROM pg_catalog.pg_namespace AS n
    WHERE n.nspname = ANY (ARRAY[
        'ai', 'analytics', 'catalog', 'editorial', 'evidence', 'finance',
        'freshness', 'policy', 'portfolio', 'publishing', 'readmodel'
    ]::text[]);
    IF observed_count <> 0 THEN
        RAISE EXCEPTION 'ST0302_LATER_SCHEMA_PRESENT';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc AS p
        JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_type AS t
        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.typnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_collation AS c
        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.collnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_conversion AS c
        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.connamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_operator AS o
        JOIN pg_catalog.pg_namespace AS n ON n.oid = o.oprnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_opclass AS o
        JOIN pg_catalog.pg_namespace AS n ON n.oid = o.opcnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_opfamily AS o
        JOIN pg_catalog.pg_namespace AS n ON n.oid = o.opfnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_ts_config AS t
        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.cfgnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_ts_dict AS t
        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.dictnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_ts_parser AS t
        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.prsnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_ts_template AS t
        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.tmplnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_statistic_ext AS s
        JOIN pg_catalog.pg_namespace AS n ON n.oid = s.stxnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) THEN
        RAISE EXCEPTION 'ST0302_FOUNDATION_NOT_EMPTY';
    END IF;

    SELECT count(*) INTO observed_count
    FROM pg_catalog.pg_extension
    WHERE extname <> 'plpgsql';
    IF observed_count <> 0 THEN
        RAISE EXCEPTION 'ST0302_EXTENSION_DEPENDENCY';
    END IF;

    SELECT count(*) INTO observed_count
    FROM (VALUES
        ('int8'), ('bool'), ('bpchar'), ('date'), ('int4'), ('interval'),
        ('jsonb'), ('numeric'), ('int2'), ('text'), ('timestamptz'), ('uuid')
    ) AS expected(typname)
    LEFT JOIN pg_catalog.pg_type AS t ON t.typname = expected.typname
    LEFT JOIN pg_catalog.pg_namespace AS n
      ON n.oid = t.typnamespace AND n.nspname = 'pg_catalog'
    WHERE n.oid IS NULL;
    IF observed_count <> 0 THEN
        RAISE EXCEPTION 'ST0302_BUILTIN_TYPE_MISSING';
    END IF;

    IF pg_catalog.to_regprocedure('pg_catalog.uuidv7()') IS NULL
       OR pg_catalog.to_regprocedure('pg_catalog.uuidv7(interval)') IS NULL
       OR pg_catalog.to_regprocedure(
           'pg_catalog.uuid_extract_version(uuid)'
       ) IS NULL
       OR pg_catalog.to_regprocedure(
           'pg_catalog.uuid_extract_timestamp(uuid)'
       ) IS NULL THEN
        RAISE EXCEPTION 'ST0302_UUID_FUNCTION_MISSING';
    END IF;
    sample_id := pg_catalog.uuidv7();
    IF pg_catalog.pg_typeof(sample_id) <> 'pg_catalog.uuid'::pg_catalog.regtype
       OR pg_catalog.uuid_extract_version(sample_id) <> 7
       OR pg_catalog.uuid_extract_timestamp(sample_id) IS NULL THEN
        RAISE EXCEPTION 'ST0302_UUIDV7_INVALID';
    END IF;

    IF (SELECT count(*) FROM public.raos_migration_version) <> 1
       OR NOT EXISTS (
           SELECT 1
           FROM public.raos_migration_version
           WHERE version_num = '202608030002'
       ) THEN
        RAISE EXCEPTION 'ST0302_MIGRATION_VERSION_MISMATCH';
    END IF;

    IF (SELECT count(*) FROM public.raos_migration_history) <> 3
       OR NOT EXISTS (
        SELECT 1
        FROM public.raos_migration_history AS anchor
        JOIN public.raos_migration_history AS started
          ON started.event_id > anchor.event_id
        JOIN public.raos_migration_history AS succeeded
          ON succeeded.event_id > started.event_id
        JOIN public.raos_migration_version AS version
          ON version.version_num = '202608030002'
        WHERE anchor.revision_id = '202608030001'
          AND anchor.story_id = 'ST-0301'
          AND anchor.direction = 'UPGRADE'
          AND anchor.status = 'SUCCEEDED'
          AND anchor.source_sha256 = 'edc9accc402947ff9d1fa9b93d5028fb762b2cfc10deb54e555985acde09e2d3'
          AND anchor.runner_version = '1.0.0'
          AND anchor.server_version_num = 180004
          AND anchor.error_code IS NULL
          AND started.revision_id = '202608030002'
          AND started.story_id = 'ST-0302'
          AND started.direction = 'UPGRADE'
          AND started.status = 'STARTED'
          AND started.source_sha256 = 'f91f6315779a045871d955cedb4b7a2606a562fbd8fdddae48810e54ef7dded4'
          AND started.runner_version = '1.1.0'
          AND started.server_version_num = 180004
          AND started.error_code IS NULL
          AND succeeded.revision_id = '202608030002'
          AND succeeded.story_id = 'ST-0302'
          AND succeeded.direction = 'UPGRADE'
          AND succeeded.status = 'SUCCEEDED'
          AND succeeded.source_sha256 = 'f91f6315779a045871d955cedb4b7a2606a562fbd8fdddae48810e54ef7dded4'
          AND succeeded.runner_version = '1.1.0'
          AND succeeded.server_version_num = 180004
          AND succeeded.error_code IS NULL
          AND anchor.attempt_id <> started.attempt_id
          AND started.attempt_id = succeeded.attempt_id
          AND started.transaction_id <> succeeded.transaction_id
          AND succeeded.transaction_id = version.xmin::text
          AND succeeded.xmin::text = version.xmin::text
    ) THEN
        RAISE EXCEPTION 'ST0302_MIGRATION_HISTORY_MISMATCH';
    END IF;
END
$raos_st0302$;

SELECT
    'PASS'::text AS status,
    current_setting('server_version_num')::integer AS server_version_num,
    2::integer AS foundation_schema_count,
    0::integer AS extension_dependency_count,
    pg_catalog.uuid_extract_version(pg_catalog.uuidv7()) AS uuid_version;
