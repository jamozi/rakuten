-- ST-0303 deterministic PostgreSQL 18.4 IAM/OPS validation.
-- Execute as the migration owner after upgrading to revision 202608030003.
DO $raos_st0303_validation$
DECLARE
    observed_count pg_catalog.int8;
BEGIN
    IF pg_catalog.current_setting('server_version_num')::pg_catalog.int4 <> 180004 THEN
        RAISE EXCEPTION 'ST0303_SERVER_VERSION_MISMATCH';
    END IF;
    IF pg_catalog.current_setting('TimeZone') <> 'UTC' THEN
        RAISE EXCEPTION 'ST0303_TIMEZONE_MISMATCH';
    END IF;
    IF pg_catalog.current_setting('search_path') <> 'pg_catalog' THEN
        RAISE EXCEPTION 'ST0303_SEARCH_PATH_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        ('ops', 'ジョブ、原本レジストリ、監査、障害、Kill Switch、実行時設定'),
        ('iam', 'OIDC主体、アプリケーションRole、権限、緊急アクセス')
    ) AS expected(schema_name, schema_comment)
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    WHERE pg_catalog.pg_get_userbyid(namespace.nspowner) = current_user
      AND pg_catalog.obj_description(namespace.oid, 'pg_namespace')
              = expected.schema_comment
      AND (
          SELECT pg_catalog.array_agg(
                     acl.privilege_type ORDER BY acl.privilege_type
                 )
          FROM pg_catalog.aclexplode(
              COALESCE(
                  namespace.nspacl,
                  pg_catalog.acldefault('n', namespace.nspowner)
              )
          ) AS acl
          WHERE acl.grantee = namespace.nspowner
      ) = ARRAY['CREATE', 'USAGE']::pg_catalog.text[]
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
    IF observed_count <> 2 THEN
        RAISE EXCEPTION 'ST0303_SCHEMA_OWNER_OR_ACL_MISMATCH';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_default_acl AS defaults
        LEFT JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = defaults.defaclnamespace
        WHERE defaults.defaclnamespace = 0
           OR namespace.nspname = ANY (
                  ARRAY['ops', 'iam', 'public']::pg_catalog.text[]
              )
    ) THEN
        RAISE EXCEPTION 'ST0303_DEFAULT_ACL_PRESENT';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM pg_catalog.pg_sequence AS sequence_record
    JOIN pg_catalog.pg_class AS sequence_relation
      ON sequence_relation.oid = sequence_record.seqrelid
    JOIN pg_catalog.pg_namespace AS sequence_namespace
      ON sequence_namespace.oid = sequence_relation.relnamespace
    JOIN pg_catalog.pg_depend AS dependency
      ON dependency.classid = 'pg_catalog.pg_class'::pg_catalog.regclass
     AND dependency.objid = sequence_relation.oid
     AND dependency.objsubid = 0
     AND dependency.refclassid = 'pg_catalog.pg_class'::pg_catalog.regclass
    JOIN pg_catalog.pg_class AS owned_relation
      ON owned_relation.oid = dependency.refobjid
    JOIN pg_catalog.pg_namespace AS owned_namespace
      ON owned_namespace.oid = owned_relation.relnamespace
    JOIN pg_catalog.pg_attribute AS owned_attribute
      ON owned_attribute.attrelid = owned_relation.oid
     AND owned_attribute.attnum = dependency.refobjsubid
    WHERE sequence_namespace.nspname = 'public'
      AND sequence_relation.relname = 'raos_migration_history_event_id_seq'
      AND pg_catalog.pg_get_userbyid(sequence_relation.relowner) = current_user
      AND sequence_relation.relkind = 'S'
      AND sequence_relation.relpersistence = 'p'
      AND pg_catalog.format_type(sequence_record.seqtypid, NULL) = 'bigint'
      AND sequence_record.seqstart = 1
      AND sequence_record.seqincrement = 1
      AND sequence_record.seqmin = 1
      AND sequence_record.seqmax = 9223372036854775807
      AND sequence_record.seqcache = 1
      AND sequence_record.seqcycle IS FALSE
      AND owned_namespace.nspname = 'public'
      AND owned_relation.relname = 'raos_migration_history'
      AND owned_attribute.attname = 'event_id'
      AND dependency.deptype = 'i';
    IF observed_count <> 1 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_sequence AS sequence_record
        JOIN pg_catalog.pg_class AS sequence_relation
          ON sequence_relation.oid = sequence_record.seqrelid
        JOIN pg_catalog.pg_namespace AS sequence_namespace
          ON sequence_namespace.oid = sequence_relation.relnamespace
        WHERE sequence_namespace.nspname = 'public'
    ) <> 1 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_depend AS dependency
        JOIN pg_catalog.pg_class AS sequence_relation
          ON sequence_relation.oid = dependency.objid
        JOIN pg_catalog.pg_namespace AS sequence_namespace
          ON sequence_namespace.oid = sequence_relation.relnamespace
        WHERE dependency.classid = 'pg_catalog.pg_class'::pg_catalog.regclass
          AND dependency.objsubid = 0
          AND dependency.refclassid = 'pg_catalog.pg_class'::pg_catalog.regclass
          AND sequence_namespace.nspname = 'public'
          AND sequence_relation.relname =
              'raos_migration_history_event_id_seq'
    ) <> 1 THEN
        RAISE EXCEPTION 'ST0303_PUBLIC_SEQUENCE_CATALOG_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        ('ops', 'object_artifact', 'S3互換Object Storage上の原本・入力・出力・公開Snapshotを登録する不変レジストリ。'),
        ('ops', 'job', '非同期作業の業務上の正本。Scheduler、API、Eventから作成され、Attemptとは分離する。'),
        ('ops', 'job_attempt', 'Jobの各実行Attemptを追記保存し、Retry、Provider call、入出力Artifact、失敗原因を再現可能にする。'),
        ('ops', 'outbox_event', '業務TransactionとEvent発行を原子的に接続するTransactional Outbox。'),
        ('ops', 'inbox_receipt', 'Consumer単位でEvent処理済みを記録し、at-least-once配送の重複を無害化する。'),
        ('ops', 'idempotency_record', 'HTTP Command等の二重送信を検出し、同じKey＋同じpayloadへ同じ結果を返す。'),
        ('ops', 'audit_event', '管理操作・自動化操作・権限変更・公開・Kill Switch等を追記記録する監査正本。'),
        ('iam', 'principal', '管理ユーザーとService Principalを共通IDで表すIAM Root。PasswordやSecretは保持しない。'),
        ('ops', 'runtime_setting_version', 'Feature Flag、閾値、Provider version、SLA等の非秘密設定をVersion管理する。'),
        ('iam', 'user_account', 'OIDC UserのIssuer/Subject、表示用Email、MFA claim等をPrincipalへ紐付ける。'),
        ('iam', 'service_principal', 'Worker、Dispatcher、CI等のWorkload IdentityをPrincipalへ紐付ける。Credential本体はSecrets Manager/OIDCに置く。'),
        ('iam', 'role', 'RAOSアプリケーション内Roleの定義。DB Roleとは分離する。'),
        ('iam', 'permission', 'API/Command単位の安定Permission code。'),
        ('iam', 'role_permission', 'RoleとPermissionの多対多対応。'),
        ('iam', 'principal_role_assignment', 'Principalへglobal/site/category/article scopeのRoleを期限付き付与する。'),
        ('iam', 'session_revocation', 'PrincipalまたはOIDC Subjectのrevoke-beforeを保持し、既存Sessionを無効化する。'),
        ('iam', 'break_glass_record', '緊急権限の理由、Incident、承認、権限集合、有効期間、終了を記録する。')
    ) AS expected(schema_name, table_name, table_comment)
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = namespace.oid
     AND relation.relname = expected.table_name
     AND relation.relkind = 'r'
    WHERE pg_catalog.pg_get_userbyid(relation.relowner) = current_user
      AND relation.relpersistence = 'p'
      AND relation.relreplident = 'd'
      AND relation.relispartition IS FALSE
      AND NOT EXISTS (
          SELECT 1
          FROM pg_catalog.pg_inherits AS inheritance
          WHERE inheritance.inhrelid = relation.oid
             OR inheritance.inhparent = relation.oid
      )
      AND relation.relrowsecurity IS FALSE
      AND relation.relforcerowsecurity IS FALSE
      AND pg_catalog.obj_description(relation.oid, 'pg_class') = expected.table_comment
      AND NOT EXISTS (
          SELECT 1
          FROM pg_catalog.aclexplode(
              COALESCE(
                  relation.relacl,
                  pg_catalog.acldefault('r', relation.relowner)
              )
          ) AS acl
          WHERE acl.grantee <> relation.relowner
      );
    IF observed_count <> 17 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
    ) <> 17 THEN
        RAISE EXCEPTION 'ST0303_TABLE_CATALOG_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        ('ops', 'object_artifact', 'object_artifact', '_object_artifact'),
        ('ops', 'job', 'job', '_job'),
        ('ops', 'job_attempt', 'job_attempt', '_job_attempt'),
        ('ops', 'outbox_event', 'outbox_event', '_outbox_event'),
        ('ops', 'inbox_receipt', 'inbox_receipt', '_inbox_receipt'),
        ('ops', 'idempotency_record', 'idempotency_record', '_idempotency_record'),
        ('ops', 'audit_event', 'audit_event', '_audit_event'),
        ('iam', 'principal', 'principal', '_principal'),
        ('ops', 'runtime_setting_version', 'runtime_setting_version', '_runtime_setting_version'),
        ('iam', 'user_account', 'user_account', '_user_account'),
        ('iam', 'service_principal', 'service_principal', '_service_principal'),
        ('iam', 'role', 'role', '_role'),
        ('iam', 'permission', 'permission', '_permission'),
        ('iam', 'role_permission', 'role_permission', '_role_permission'),
        ('iam', 'principal_role_assignment', 'principal_role_assignment', '_principal_role_assignment'),
        ('iam', 'session_revocation', 'session_revocation', '_session_revocation'),
        ('iam', 'break_glass_record', 'break_glass_record', '_break_glass_record')
    ) AS expected(schema_name, table_name, row_type_name, array_type_name)
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = namespace.oid
     AND relation.relname = expected.table_name
     AND relation.relkind = 'r'
    JOIN pg_catalog.pg_type AS row_type
      ON row_type.typnamespace = namespace.oid
     AND row_type.typname = expected.row_type_name
     AND row_type.oid = relation.reltype
    JOIN pg_catalog.pg_type AS array_type
      ON array_type.typnamespace = namespace.oid
     AND array_type.typname = expected.array_type_name
    WHERE pg_catalog.pg_get_userbyid(row_type.typowner) = current_user
      AND pg_catalog.pg_get_userbyid(array_type.typowner) = current_user
      AND row_type.typtype = 'c'
      AND row_type.typelem = 0
      AND row_type.typarray = array_type.oid
      AND row_type.typrelid = relation.oid
      AND row_type.typacl IS NULL
      AND pg_catalog.obj_description(row_type.oid, 'pg_type') IS NULL
      AND array_type.typtype = 'b'
      AND array_type.typelem = row_type.oid
      AND array_type.typarray = 0
      AND array_type.typrelid = 0
      AND array_type.typacl IS NULL
      AND pg_catalog.obj_description(array_type.oid, 'pg_type') IS NULL;
    IF observed_count <> 17 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_type AS object_type
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = object_type.typnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
    ) <> 34 THEN
        RAISE EXCEPTION 'ST0303_UNEXPECTED_OBJECT_CATALOG_MISMATCH';
    END IF;

    SELECT
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_class AS relation
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
           AND (
               relation.relkind NOT IN ('r', 'i')
               OR pg_catalog.pg_get_userbyid(relation.relowner) <> current_user
               OR relation.relpersistence <> 'p'
               OR relation.relispartition IS TRUE
           ))
        +
        (SELECT CASE WHEN pg_catalog.count(*) = 95 THEN 0 ELSE 1 END
         FROM pg_catalog.pg_class AS relation
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_cast AS cast_record
         WHERE EXISTS (
             SELECT 1
             FROM pg_catalog.pg_type AS object_type
             JOIN pg_catalog.pg_namespace AS namespace
               ON namespace.oid = object_type.typnamespace
             WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
               AND object_type.oid IN (
                   cast_record.castsource, cast_record.casttarget
               )
         ))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_transform AS transform_record
         JOIN pg_catalog.pg_type AS object_type
           ON object_type.oid = transform_record.trftype
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = object_type.typnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_rewrite AS rewrite_record
         JOIN pg_catalog.pg_class AS relation
           ON relation.oid = rewrite_record.ev_class
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_policy AS policy_record
         JOIN pg_catalog.pg_class AS relation
           ON relation.oid = policy_record.polrelid
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_collation AS collation_record
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = collation_record.collnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_conversion AS conversion_record
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = conversion_record.connamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_operator AS operator_record
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = operator_record.oprnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_opclass AS operator_class
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = operator_class.opcnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_opfamily AS operator_family
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = operator_family.opfnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_amop AS access_operator
         WHERE EXISTS (
             SELECT 1
             FROM pg_catalog.pg_type AS object_type
             JOIN pg_catalog.pg_namespace AS namespace
               ON namespace.oid = object_type.typnamespace
             WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
               AND object_type.oid IN (
                   access_operator.amoplefttype,
                   access_operator.amoprighttype
               )
         ))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_amproc AS access_procedure
         WHERE EXISTS (
             SELECT 1
             FROM pg_catalog.pg_type AS object_type
             JOIN pg_catalog.pg_namespace AS namespace
               ON namespace.oid = object_type.typnamespace
             WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
               AND object_type.oid IN (
                   access_procedure.amproclefttype,
                   access_procedure.amprocrighttype
               )
         ))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_ts_config AS search_configuration
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = search_configuration.cfgnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_ts_dict AS search_dictionary
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = search_dictionary.dictnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_ts_parser AS search_parser
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = search_parser.prsnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_ts_template AS search_template
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = search_template.tmplnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_statistic_ext AS statistics_record
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = statistics_record.stxnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_publication_rel AS publication_relation
         JOIN pg_catalog.pg_class AS relation
           ON relation.oid = publication_relation.prrelid
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_publication_namespace AS publication_namespace
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = publication_namespace.pnnspid
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_publication)
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_subscription AS subscription_record
         WHERE subscription_record.subdbid = (
             SELECT database_record.oid
             FROM pg_catalog.pg_database AS database_record
             WHERE database_record.datname = pg_catalog.current_database()
         ))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_largeobject_metadata)
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_foreign_data_wrapper)
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_foreign_server)
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_inherits AS inheritance
         JOIN pg_catalog.pg_class AS relation
           ON relation.oid IN (inheritance.inhrelid, inheritance.inhparent)
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_partitioned_table AS partitioned
         JOIN pg_catalog.pg_class AS relation
           ON relation.oid = partitioned.partrelid
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT CASE WHEN pg_catalog.count(*) = 80 THEN 0 ELSE 1 END
         FROM pg_catalog.pg_trigger AS trigger_record
         JOIN pg_catalog.pg_class AS relation
           ON relation.oid = trigger_record.tgrelid
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
           AND trigger_record.tgisinternal IS TRUE)
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_trigger AS trigger_record
         JOIN pg_catalog.pg_class AS relation
           ON relation.oid = trigger_record.tgrelid
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
           AND trigger_record.tgisinternal IS TRUE
           AND (
               trigger_record.tgenabled <> 'O'
               OR trigger_record.tgconstraint = 0
               OR trigger_record.tgparentid <> 0
               OR pg_catalog.obj_description(
                      trigger_record.oid, 'pg_trigger'
                  ) IS NOT NULL
           ))
    INTO observed_count;
    IF observed_count <> 0 THEN
        RAISE EXCEPTION 'ST0303_UNEXPECTED_OBJECT_CATALOG_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        ('ops', 'object_artifact', 1, 'id', 'uuid', TRUE, 'uuidv7()', '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。'),
        ('ops', 'object_artifact', 2, 'display_id', 'text', TRUE, '', 'OBJ-接頭辞を持つアプリケーション生成の不変表示ID。'),
        ('ops', 'object_artifact', 3, 'artifact_kind', 'text', TRUE, '', 'raw_provider_response、source_snapshot、source_packet、ai_input、ai_output、publication_snapshot、revenue_original、audit_export等。'),
        ('ops', 'object_artifact', 4, 'storage_provider', 'text', TRUE, '''s3''::text', 'storage provider'),
        ('ops', 'object_artifact', 5, 'bucket_name', 'text', TRUE, '', 'bucket name'),
        ('ops', 'object_artifact', 6, 'object_key', 'text', TRUE, '', 'object key'),
        ('ops', 'object_artifact', 7, 'object_version', 'text', FALSE, '', 'Object VersioningのVersion ID。ローカル環境ではNULL可。'),
        ('ops', 'object_artifact', 8, 'content_type', 'text', TRUE, '', 'content type'),
        ('ops', 'object_artifact', 9, 'byte_size', 'bigint', TRUE, '', 'byte size'),
        ('ops', 'object_artifact', 10, 'sha256', 'text', TRUE, '', 'sha256'),
        ('ops', 'object_artifact', 11, 'encryption_state', 'text', TRUE, '', 'encryption state'),
        ('ops', 'object_artifact', 12, 'retention_class', 'text', TRUE, '', 'retention class'),
        ('ops', 'object_artifact', 13, 'is_immutable', 'boolean', TRUE, 'true', 'is immutable'),
        ('ops', 'object_artifact', 14, 'source_system', 'text', TRUE, '', 'source system'),
        ('ops', 'object_artifact', 15, 'acquired_at', 'timestamp with time zone', FALSE, '', 'acquired at'),
        ('ops', 'object_artifact', 16, 'created_by_principal_id', 'uuid', FALSE, '', '作成操作を行ったIAM Principal。'),
        ('ops', 'object_artifact', 17, 'metadata', 'jsonb', TRUE, '''{}''::jsonb', 'Objectタグ、parser、provider request ID等。秘密・原本文は含めない。'),
        ('ops', 'object_artifact', 18, 'created_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'レコード作成時刻。UTCのtimestamptz。'),
        ('ops', 'job', 1, 'id', 'uuid', TRUE, 'uuidv7()', '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。'),
        ('ops', 'job', 2, 'display_id', 'text', TRUE, '', 'JOB-接頭辞を持つアプリケーション生成の不変表示ID。'),
        ('ops', 'job', 3, 'job_type', 'text', TRUE, '', 'job type'),
        ('ops', 'job', 4, 'queue_name', 'text', TRUE, '', 'queue name'),
        ('ops', 'job', 5, 'status', 'text', TRUE, '''REQUESTED''::text', '業務状態を示す安定Enum文字列。'),
        ('ops', 'job', 6, 'priority', 'smallint', TRUE, '50', 'priority'),
        ('ops', 'job', 7, 'idempotency_key', 'text', FALSE, '', 'idempotency key'),
        ('ops', 'job', 8, 'site_id', 'uuid', FALSE, '', '対象サイト。MVPは1サイトだが将来の複数サイトを識別可能にする。'),
        ('ops', 'job', 9, 'aggregate_type', 'text', FALSE, '', 'aggregate type'),
        ('ops', 'job', 10, 'aggregate_id', 'uuid', FALSE, '', 'aggregate id'),
        ('ops', 'job', 11, 'payload', 'jsonb', TRUE, '''{}''::jsonb', '小さなCommand payload。大容量入力はpayload_artifact_idへ分離する。'),
        ('ops', 'job', 12, 'payload_artifact_id', 'uuid', FALSE, '', 'payload artifact id'),
        ('ops', 'job', 13, 'scheduled_at', 'timestamp with time zone', FALSE, '', 'scheduled at'),
        ('ops', 'job', 14, 'available_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'available at'),
        ('ops', 'job', 15, 'started_at', 'timestamp with time zone', FALSE, '', 'started at'),
        ('ops', 'job', 16, 'completed_at', 'timestamp with time zone', FALSE, '', 'completed at'),
        ('ops', 'job', 17, 'max_attempts', 'smallint', TRUE, '5', 'max attempts'),
        ('ops', 'job', 18, 'attempt_count', 'smallint', TRUE, '0', 'attempt count'),
        ('ops', 'job', 19, 'lease_owner', 'text', FALSE, '', 'lease owner'),
        ('ops', 'job', 20, 'lease_expires_at', 'timestamp with time zone', FALSE, '', 'lease expires at'),
        ('ops', 'job', 21, 'correlation_id', 'uuid', TRUE, 'uuidv7()', '要求・Job・Eventを横断して追跡するCorrelation ID。'),
        ('ops', 'job', 22, 'causation_id', 'uuid', FALSE, '', 'この事実を直接発生させたCommand/Event/Job ID。'),
        ('ops', 'job', 23, 'parent_job_id', 'uuid', FALSE, '', 'parent job id'),
        ('ops', 'job', 24, 'budget_jpy', 'bigint', FALSE, '', 'budget jpy'),
        ('ops', 'job', 25, 'created_by_actor_type', 'text', TRUE, '', 'created by actor type'),
        ('ops', 'job', 26, 'created_by_actor_id', 'uuid', FALSE, '', 'created by actor id'),
        ('ops', 'job', 27, 'last_error_class', 'text', FALSE, '', 'last error class'),
        ('ops', 'job', 28, 'last_error_code', 'text', FALSE, '', 'last error code'),
        ('ops', 'job', 29, 'last_error_message', 'text', FALSE, '', 'last error message'),
        ('ops', 'job', 30, 'created_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'レコード作成時刻。UTCのtimestamptz。'),
        ('ops', 'job', 31, 'updated_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', '最終更新時刻。UTCのtimestamptz。'),
        ('ops', 'job', 32, 'lock_version', 'bigint', TRUE, '0', '楽観的排他制御用の単調増加Version。'),
        ('ops', 'job', 33, 'job_version', 'smallint', TRUE, '1', 'Version of the Job message/payload contract; distinct from lock_version.'),
        ('ops', 'job', 34, 'deadline_at', 'timestamp with time zone', FALSE, '', 'Deadline after which an eligible active Job may expire.'),
        ('ops', 'job', 35, 'cancel_requested_at', 'timestamp with time zone', FALSE, '', 'Timestamp of a cooperative cancellation request.'),
        ('ops', 'job_attempt', 1, 'id', 'uuid', TRUE, 'uuidv7()', '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。'),
        ('ops', 'job_attempt', 2, 'job_id', 'uuid', TRUE, '', '非同期Job。'),
        ('ops', 'job_attempt', 3, 'attempt_no', 'smallint', TRUE, '', 'attempt no'),
        ('ops', 'job_attempt', 4, 'status', 'text', TRUE, '', '業務状態を示す安定Enum文字列。'),
        ('ops', 'job_attempt', 5, 'worker_id', 'text', TRUE, '', 'worker id'),
        ('ops', 'job_attempt', 6, 'handler_version', 'text', TRUE, '', 'handler version'),
        ('ops', 'job_attempt', 7, 'started_at', 'timestamp with time zone', TRUE, '', 'started at'),
        ('ops', 'job_attempt', 8, 'completed_at', 'timestamp with time zone', FALSE, '', 'completed at'),
        ('ops', 'job_attempt', 9, 'provider_request_id', 'text', FALSE, '', 'provider request id'),
        ('ops', 'job_attempt', 10, 'input_artifact_id', 'uuid', FALSE, '', 'input artifact id'),
        ('ops', 'job_attempt', 11, 'output_artifact_id', 'uuid', FALSE, '', 'output artifact id'),
        ('ops', 'job_attempt', 12, 'error_class', 'text', FALSE, '', 'error class'),
        ('ops', 'job_attempt', 13, 'error_code', 'text', FALSE, '', 'error code'),
        ('ops', 'job_attempt', 14, 'error_message', 'text', FALSE, '', 'error message'),
        ('ops', 'job_attempt', 15, 'retry_after_at', 'timestamp with time zone', FALSE, '', 'retry after at'),
        ('ops', 'job_attempt', 16, 'metrics', 'jsonb', TRUE, '''{}''::jsonb', 'Duration、row count、provider quota等の低カーディナリティ指標。'),
        ('ops', 'job_attempt', 17, 'created_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'レコード作成時刻。UTCのtimestamptz。'),
        ('ops', 'outbox_event', 1, 'id', 'uuid', TRUE, 'uuidv7()', '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。'),
        ('ops', 'outbox_event', 2, 'event_type', 'text', TRUE, '', 'event type'),
        ('ops', 'outbox_event', 3, 'event_version', 'integer', TRUE, '1', 'event version'),
        ('ops', 'outbox_event', 4, 'producer', 'text', TRUE, '', 'producer'),
        ('ops', 'outbox_event', 5, 'aggregate_type', 'text', TRUE, '', 'aggregate type'),
        ('ops', 'outbox_event', 6, 'aggregate_id', 'uuid', TRUE, '', 'aggregate id'),
        ('ops', 'outbox_event', 7, 'aggregate_version', 'bigint', TRUE, '', 'aggregate version'),
        ('ops', 'outbox_event', 8, 'correlation_id', 'uuid', TRUE, '', '要求・Job・Eventを横断して追跡するCorrelation ID。'),
        ('ops', 'outbox_event', 9, 'causation_id', 'uuid', FALSE, '', 'この事実を直接発生させたCommand/Event/Job ID。'),
        ('ops', 'outbox_event', 10, 'actor_type', 'text', TRUE, '', 'actor type'),
        ('ops', 'outbox_event', 11, 'actor_id', 'uuid', FALSE, '', 'actor id'),
        ('ops', 'outbox_event', 12, 'payload', 'jsonb', TRUE, '''{}''::jsonb', 'Version付きEvent payload。秘密・大容量原本を含めない。'),
        ('ops', 'outbox_event', 13, 'payload_schema_hash', 'text', TRUE, '', 'payload schema hash'),
        ('ops', 'outbox_event', 14, 'status', 'text', TRUE, '''PENDING''::text', '業務状態を示す安定Enum文字列。'),
        ('ops', 'outbox_event', 15, 'available_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'available at'),
        ('ops', 'outbox_event', 16, 'published_at', 'timestamp with time zone', FALSE, '', 'published at'),
        ('ops', 'outbox_event', 17, 'publish_attempts', 'smallint', TRUE, '0', 'publish attempts'),
        ('ops', 'outbox_event', 18, 'last_error', 'text', FALSE, '', 'last error'),
        ('ops', 'outbox_event', 19, 'created_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'レコード作成時刻。UTCのtimestamptz。'),
        ('ops', 'inbox_receipt', 1, 'id', 'uuid', TRUE, 'uuidv7()', '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。'),
        ('ops', 'inbox_receipt', 2, 'consumer_name', 'text', TRUE, '', 'consumer name'),
        ('ops', 'inbox_receipt', 3, 'handler_version', 'text', TRUE, '', 'handler version'),
        ('ops', 'inbox_receipt', 4, 'event_id', 'uuid', TRUE, '', 'event id'),
        ('ops', 'inbox_receipt', 5, 'status', 'text', TRUE, '', '業務状態を示す安定Enum文字列。'),
        ('ops', 'inbox_receipt', 6, 'received_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'received at'),
        ('ops', 'inbox_receipt', 7, 'processed_at', 'timestamp with time zone', FALSE, '', 'processed at'),
        ('ops', 'inbox_receipt', 8, 'result_hash', 'text', FALSE, '', 'result hash'),
        ('ops', 'inbox_receipt', 9, 'error_code', 'text', FALSE, '', 'error code'),
        ('ops', 'inbox_receipt', 10, 'created_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'レコード作成時刻。UTCのtimestamptz。'),
        ('ops', 'idempotency_record', 1, 'id', 'uuid', TRUE, 'uuidv7()', '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。'),
        ('ops', 'idempotency_record', 2, 'actor_fingerprint', 'text', TRUE, '', 'actor fingerprint'),
        ('ops', 'idempotency_record', 3, 'route_key', 'text', TRUE, '', 'route key'),
        ('ops', 'idempotency_record', 4, 'idempotency_key', 'text', TRUE, '', 'idempotency key'),
        ('ops', 'idempotency_record', 5, 'request_hash', 'text', TRUE, '', 'request hash'),
        ('ops', 'idempotency_record', 6, 'status', 'text', TRUE, '''IN_PROGRESS''::text', '業務状態を示す安定Enum文字列。'),
        ('ops', 'idempotency_record', 7, 'response_status', 'integer', FALSE, '', 'response status'),
        ('ops', 'idempotency_record', 8, 'response_body', 'jsonb', FALSE, '', '小さな再送応答。大きい応答はArtifactへ保存。'),
        ('ops', 'idempotency_record', 9, 'response_artifact_id', 'uuid', FALSE, '', 'response artifact id'),
        ('ops', 'idempotency_record', 10, 'resource_type', 'text', FALSE, '', 'resource type'),
        ('ops', 'idempotency_record', 11, 'resource_id', 'uuid', FALSE, '', 'resource id'),
        ('ops', 'idempotency_record', 12, 'expires_at', 'timestamp with time zone', TRUE, '', 'expires at'),
        ('ops', 'idempotency_record', 13, 'completed_at', 'timestamp with time zone', FALSE, '', 'completed at'),
        ('ops', 'idempotency_record', 14, 'created_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'レコード作成時刻。UTCのtimestamptz。'),
        ('ops', 'audit_event', 1, 'id', 'uuid', TRUE, 'uuidv7()', '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。'),
        ('ops', 'audit_event', 2, 'occurred_at', 'timestamp with time zone', TRUE, '', 'occurred at'),
        ('ops', 'audit_event', 3, 'actor_type', 'text', TRUE, '', 'actor type'),
        ('ops', 'audit_event', 4, 'actor_id', 'uuid', FALSE, '', 'actor id'),
        ('ops', 'audit_event', 5, 'action', 'text', TRUE, '', 'action'),
        ('ops', 'audit_event', 6, 'target_type', 'text', TRUE, '', 'target type'),
        ('ops', 'audit_event', 7, 'target_id', 'uuid', FALSE, '', 'target id'),
        ('ops', 'audit_event', 8, 'outcome', 'text', TRUE, '', 'outcome'),
        ('ops', 'audit_event', 9, 'severity', 'text', TRUE, '''INFO''::text', 'severity'),
        ('ops', 'audit_event', 10, 'correlation_id', 'uuid', TRUE, '', '要求・Job・Eventを横断して追跡するCorrelation ID。'),
        ('ops', 'audit_event', 11, 'request_id', 'text', FALSE, '', 'request id'),
        ('ops', 'audit_event', 12, 'before_hash', 'text', FALSE, '', 'before hash'),
        ('ops', 'audit_event', 13, 'after_hash', 'text', FALSE, '', 'after hash'),
        ('ops', 'audit_event', 14, 'details', 'jsonb', TRUE, '''{}''::jsonb', '差分要約、理由、Policy/Prompt版。秘密、原文、raw IPは含めない。'),
        ('ops', 'audit_event', 15, 'created_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'レコード作成時刻。UTCのtimestamptz。'),
        ('iam', 'principal', 1, 'id', 'uuid', TRUE, 'uuidv7()', '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。'),
        ('iam', 'principal', 2, 'display_id', 'text', TRUE, '', 'PRN-接頭辞を持つアプリケーション生成の不変表示ID。'),
        ('iam', 'principal', 3, 'principal_type', 'text', TRUE, '', 'principal type'),
        ('iam', 'principal', 4, 'status', 'text', TRUE, '''ACTIVE''::text', '業務状態を示す安定Enum文字列。'),
        ('iam', 'principal', 5, 'display_name', 'text', TRUE, '', 'display name'),
        ('iam', 'principal', 6, 'deactivated_at', 'timestamp with time zone', FALSE, '', 'deactivated at'),
        ('iam', 'principal', 7, 'deactivation_reason', 'text', FALSE, '', 'deactivation reason'),
        ('iam', 'principal', 8, 'created_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'レコード作成時刻。UTCのtimestamptz。'),
        ('iam', 'principal', 9, 'updated_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', '最終更新時刻。UTCのtimestamptz。'),
        ('iam', 'principal', 10, 'lock_version', 'bigint', TRUE, '0', '楽観的排他制御用の単調増加Version。'),
        ('ops', 'runtime_setting_version', 1, 'id', 'uuid', TRUE, 'uuidv7()', '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。'),
        ('ops', 'runtime_setting_version', 2, 'setting_key', 'text', TRUE, '', 'setting key'),
        ('ops', 'runtime_setting_version', 3, 'scope_type', 'text', TRUE, '', 'scope type'),
        ('ops', 'runtime_setting_version', 4, 'scope_id', 'uuid', FALSE, '', 'scope id'),
        ('ops', 'runtime_setting_version', 5, 'version_no', 'integer', TRUE, '', 'Aggregate内で1から増加する不変Version番号。'),
        ('ops', 'runtime_setting_version', 6, 'setting_class', 'text', TRUE, '', 'setting class'),
        ('ops', 'runtime_setting_version', 7, 'value', 'jsonb', TRUE, '''{}''::jsonb', 'value'),
        ('ops', 'runtime_setting_version', 8, 'value_sha256', 'text', TRUE, '', 'value sha256'),
        ('ops', 'runtime_setting_version', 9, 'status', 'text', TRUE, '', '業務状態を示す安定Enum文字列。'),
        ('ops', 'runtime_setting_version', 10, 'effective_from', 'timestamp with time zone', FALSE, '', '設定・関係が有効になる時刻。'),
        ('ops', 'runtime_setting_version', 11, 'effective_to', 'timestamp with time zone', FALSE, '', '設定・関係の有効終了時刻。NULLは終了未定。'),
        ('ops', 'runtime_setting_version', 12, 'created_by_principal_id', 'uuid', TRUE, '', '作成操作を行ったIAM Principal。'),
        ('ops', 'runtime_setting_version', 13, 'approved_by_principal_id', 'uuid', FALSE, '', 'approved by principal id'),
        ('ops', 'runtime_setting_version', 14, 'approval_reason', 'text', FALSE, '', 'approval reason'),
        ('ops', 'runtime_setting_version', 15, 'created_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'レコード作成時刻。UTCのtimestamptz。'),
        ('iam', 'user_account', 1, 'principal_id', 'uuid', TRUE, '', 'principal id'),
        ('iam', 'user_account', 2, 'oidc_issuer', 'text', TRUE, '', 'oidc issuer'),
        ('iam', 'user_account', 3, 'oidc_subject', 'text', TRUE, '', 'oidc subject'),
        ('iam', 'user_account', 4, 'email', 'text', FALSE, '', 'email'),
        ('iam', 'user_account', 5, 'email_verified', 'boolean', TRUE, 'false', 'email verified'),
        ('iam', 'user_account', 6, 'mfa_required', 'boolean', TRUE, 'true', 'mfa required'),
        ('iam', 'user_account', 7, 'last_login_at', 'timestamp with time zone', FALSE, '', 'last login at'),
        ('iam', 'user_account', 8, 'last_mfa_at', 'timestamp with time zone', FALSE, '', 'last mfa at'),
        ('iam', 'user_account', 9, 'created_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'レコード作成時刻。UTCのtimestamptz。'),
        ('iam', 'service_principal', 1, 'principal_id', 'uuid', TRUE, '', 'principal id'),
        ('iam', 'service_principal', 2, 'service_code', 'text', TRUE, '', 'service code'),
        ('iam', 'service_principal', 3, 'workload_identity', 'text', TRUE, '', 'workload identity'),
        ('iam', 'service_principal', 4, 'allowed_environment', 'text', TRUE, '', 'allowed environment'),
        ('iam', 'service_principal', 5, 'credential_rotated_at', 'timestamp with time zone', FALSE, '', 'credential rotated at'),
        ('iam', 'service_principal', 6, 'last_used_at', 'timestamp with time zone', FALSE, '', 'last used at'),
        ('iam', 'service_principal', 7, 'created_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'レコード作成時刻。UTCのtimestamptz。'),
        ('iam', 'role', 1, 'id', 'uuid', TRUE, 'uuidv7()', '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。'),
        ('iam', 'role', 2, 'role_code', 'text', TRUE, '', 'role code'),
        ('iam', 'role', 3, 'name', 'text', TRUE, '', 'name'),
        ('iam', 'role', 4, 'description', 'text', TRUE, '', 'description'),
        ('iam', 'role', 5, 'is_system_role', 'boolean', TRUE, 'true', 'is system role'),
        ('iam', 'role', 6, 'status', 'text', TRUE, '''ACTIVE''::text', '業務状態を示す安定Enum文字列。'),
        ('iam', 'role', 7, 'created_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'レコード作成時刻。UTCのtimestamptz。'),
        ('iam', 'permission', 1, 'id', 'uuid', TRUE, 'uuidv7()', '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。'),
        ('iam', 'permission', 2, 'permission_code', 'text', TRUE, '', 'permission code'),
        ('iam', 'permission', 3, 'description', 'text', TRUE, '', 'description'),
        ('iam', 'permission', 4, 'risk_level', 'text', TRUE, '', 'risk level'),
        ('iam', 'permission', 5, 'status', 'text', TRUE, '''ACTIVE''::text', '業務状態を示す安定Enum文字列。'),
        ('iam', 'permission', 6, 'created_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'レコード作成時刻。UTCのtimestamptz。'),
        ('iam', 'role_permission', 1, 'role_id', 'uuid', TRUE, '', 'role id'),
        ('iam', 'role_permission', 2, 'permission_id', 'uuid', TRUE, '', 'permission id'),
        ('iam', 'role_permission', 3, 'created_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'レコード作成時刻。UTCのtimestamptz。'),
        ('iam', 'principal_role_assignment', 1, 'id', 'uuid', TRUE, 'uuidv7()', '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。'),
        ('iam', 'principal_role_assignment', 2, 'principal_id', 'uuid', TRUE, '', 'principal id'),
        ('iam', 'principal_role_assignment', 3, 'role_id', 'uuid', TRUE, '', 'role id'),
        ('iam', 'principal_role_assignment', 4, 'scope_type', 'text', TRUE, '', 'scope type'),
        ('iam', 'principal_role_assignment', 5, 'scope_id', 'uuid', FALSE, '', 'scope id'),
        ('iam', 'principal_role_assignment', 6, 'valid_from', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'valid from'),
        ('iam', 'principal_role_assignment', 7, 'valid_to', 'timestamp with time zone', FALSE, '', 'valid to'),
        ('iam', 'principal_role_assignment', 8, 'assigned_by_principal_id', 'uuid', TRUE, '', 'assigned by principal id'),
        ('iam', 'principal_role_assignment', 9, 'assignment_reason', 'text', TRUE, '', 'assignment reason'),
        ('iam', 'principal_role_assignment', 10, 'revoked_at', 'timestamp with time zone', FALSE, '', 'revoked at'),
        ('iam', 'principal_role_assignment', 11, 'revoked_by_principal_id', 'uuid', FALSE, '', 'revoked by principal id'),
        ('iam', 'principal_role_assignment', 12, 'revocation_reason', 'text', FALSE, '', 'revocation reason'),
        ('iam', 'principal_role_assignment', 13, 'created_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'レコード作成時刻。UTCのtimestamptz。'),
        ('iam', 'session_revocation', 1, 'id', 'uuid', TRUE, 'uuidv7()', '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。'),
        ('iam', 'session_revocation', 2, 'principal_id', 'uuid', TRUE, '', 'principal id'),
        ('iam', 'session_revocation', 3, 'oidc_issuer', 'text', TRUE, '', 'oidc issuer'),
        ('iam', 'session_revocation', 4, 'oidc_subject', 'text', TRUE, '', 'oidc subject'),
        ('iam', 'session_revocation', 5, 'revoke_before', 'timestamp with time zone', TRUE, '', 'revoke before'),
        ('iam', 'session_revocation', 6, 'reason', 'text', TRUE, '', 'reason'),
        ('iam', 'session_revocation', 7, 'created_by_principal_id', 'uuid', TRUE, '', '作成操作を行ったIAM Principal。'),
        ('iam', 'session_revocation', 8, 'expires_at', 'timestamp with time zone', FALSE, '', 'expires at'),
        ('iam', 'session_revocation', 9, 'created_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'レコード作成時刻。UTCのtimestamptz。'),
        ('iam', 'break_glass_record', 1, 'id', 'uuid', TRUE, 'uuidv7()', '内部主キー。PostgreSQL 18のuuidv7()で生成する時系列順UUID。'),
        ('iam', 'break_glass_record', 2, 'display_id', 'text', TRUE, '', 'BGA-接頭辞を持つアプリケーション生成の不変表示ID。'),
        ('iam', 'break_glass_record', 3, 'principal_id', 'uuid', TRUE, '', 'principal id'),
        ('iam', 'break_glass_record', 4, 'incident_id', 'uuid', TRUE, '', 'incident id'),
        ('iam', 'break_glass_record', 5, 'reason', 'text', TRUE, '', 'reason'),
        ('iam', 'break_glass_record', 6, 'approved_by_principal_id', 'uuid', TRUE, '', 'approved by principal id'),
        ('iam', 'break_glass_record', 7, 'permissions', 'jsonb', TRUE, '''{}''::jsonb', '緊急時に一時付与したPermission code集合。'),
        ('iam', 'break_glass_record', 8, 'started_at', 'timestamp with time zone', TRUE, '', 'started at'),
        ('iam', 'break_glass_record', 9, 'expires_at', 'timestamp with time zone', TRUE, '', 'expires at'),
        ('iam', 'break_glass_record', 10, 'ended_at', 'timestamp with time zone', FALSE, '', 'ended at'),
        ('iam', 'break_glass_record', 11, 'end_reason', 'text', FALSE, '', 'end reason'),
        ('iam', 'break_glass_record', 12, 'created_at', 'timestamp with time zone', TRUE, 'CURRENT_TIMESTAMP', 'レコード作成時刻。UTCのtimestamptz。')
    ) AS expected(
        schema_name, table_name, attribute_number, column_name, type_name,
        not_null, default_expression, column_comment
    )
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = namespace.oid
     AND relation.relname = expected.table_name
     AND relation.relkind = 'r'
    JOIN pg_catalog.pg_attribute AS attribute
      ON attribute.attrelid = relation.oid
     AND attribute.attnum = expected.attribute_number
     AND attribute.attname = expected.column_name
     AND attribute.attisdropped IS FALSE
    LEFT JOIN pg_catalog.pg_attrdef AS default_value
      ON default_value.adrelid = relation.oid
     AND default_value.adnum = attribute.attnum
    WHERE pg_catalog.format_type(attribute.atttypid, attribute.atttypmod)
              = expected.type_name
      AND attribute.attnotnull = expected.not_null
      AND attribute.attidentity = ''
      AND attribute.attgenerated = ''
      AND COALESCE(
              pg_catalog.pg_get_expr(
                  default_value.adbin, default_value.adrelid, false
              ),
              ''
          ) = expected.default_expression
      AND pg_catalog.col_description(relation.oid, attribute.attnum)
              = expected.column_comment
      AND attribute.attacl IS NULL;
    IF observed_count <> 219 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_attribute AS attribute
        JOIN pg_catalog.pg_class AS relation ON relation.oid = attribute.attrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
          AND attribute.attnum > 0
          AND attribute.attisdropped IS FALSE
    ) <> 219 OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_attribute AS attribute
        JOIN pg_catalog.pg_class AS relation ON relation.oid = attribute.attrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
          AND attribute.attnum > 0
          AND attribute.attisdropped IS TRUE
    ) THEN
        RAISE EXCEPTION 'ST0303_COLUMN_CATALOG_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        ('ops', 'object_artifact', 'object_artifact_id_not_null', 'n', 'id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL id', NULL),
        ('ops', 'object_artifact', 'object_artifact_display_id_not_null', 'n', 'display_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL display_id', NULL),
        ('ops', 'object_artifact', 'object_artifact_artifact_kind_not_null', 'n', 'artifact_kind', '', '', '', '', '', FALSE, FALSE, 'NOT NULL artifact_kind', NULL),
        ('ops', 'object_artifact', 'object_artifact_storage_provider_not_null', 'n', 'storage_provider', '', '', '', '', '', FALSE, FALSE, 'NOT NULL storage_provider', NULL),
        ('ops', 'object_artifact', 'object_artifact_bucket_name_not_null', 'n', 'bucket_name', '', '', '', '', '', FALSE, FALSE, 'NOT NULL bucket_name', NULL),
        ('ops', 'object_artifact', 'object_artifact_object_key_not_null', 'n', 'object_key', '', '', '', '', '', FALSE, FALSE, 'NOT NULL object_key', NULL),
        ('ops', 'object_artifact', 'object_artifact_content_type_not_null', 'n', 'content_type', '', '', '', '', '', FALSE, FALSE, 'NOT NULL content_type', NULL),
        ('ops', 'object_artifact', 'object_artifact_byte_size_not_null', 'n', 'byte_size', '', '', '', '', '', FALSE, FALSE, 'NOT NULL byte_size', NULL),
        ('ops', 'object_artifact', 'object_artifact_sha256_not_null', 'n', 'sha256', '', '', '', '', '', FALSE, FALSE, 'NOT NULL sha256', NULL),
        ('ops', 'object_artifact', 'object_artifact_encryption_state_not_null', 'n', 'encryption_state', '', '', '', '', '', FALSE, FALSE, 'NOT NULL encryption_state', NULL),
        ('ops', 'object_artifact', 'object_artifact_retention_class_not_null', 'n', 'retention_class', '', '', '', '', '', FALSE, FALSE, 'NOT NULL retention_class', NULL),
        ('ops', 'object_artifact', 'object_artifact_is_immutable_not_null', 'n', 'is_immutable', '', '', '', '', '', FALSE, FALSE, 'NOT NULL is_immutable', NULL),
        ('ops', 'object_artifact', 'object_artifact_source_system_not_null', 'n', 'source_system', '', '', '', '', '', FALSE, FALSE, 'NOT NULL source_system', NULL),
        ('ops', 'object_artifact', 'object_artifact_metadata_not_null', 'n', 'metadata', '', '', '', '', '', FALSE, FALSE, 'NOT NULL metadata', NULL),
        ('ops', 'object_artifact', 'object_artifact_created_at_not_null', 'n', 'created_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_at', NULL),
        ('ops', 'object_artifact', 'pk_ops_object_artifact', 'p', 'id', '', '', '', '', '', FALSE, FALSE, 'PRIMARY KEY (id)', NULL),
        ('ops', 'object_artifact', 'uq_ops_object_artifact_display_id', 'u', 'display_id', '', '', '', '', '', FALSE, FALSE, 'UNIQUE (display_id)', NULL),
        ('ops', 'object_artifact', 'ck_ops_object_artifact_kind', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((artifact_kind = ANY (ARRAY[''raw_provider_response''::text, ''raw_primary_source''::text, ''source_snapshot''::text, ''source_packet''::text, ''ai_input''::text, ''ai_output''::text, ''publication_snapshot''::text, ''revenue_original''::text, ''revenue_rejects''::text, ''audit_export''::text, ''quality_report''::text, ''diff''::text, ''import_report''::text, ''other''::text])))', '(artifact_kind = ANY (ARRAY[''raw_provider_response''::text, ''raw_primary_source''::text, ''source_snapshot''::text, ''source_packet''::text, ''ai_input''::text, ''ai_output''::text, ''publication_snapshot''::text, ''revenue_original''::text, ''revenue_rejects''::text, ''audit_export''::text, ''quality_report''::text, ''diff''::text, ''import_report''::text, ''other''::text]))'),
        ('ops', 'object_artifact', 'ck_ops_object_artifact_size', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((byte_size >= 0))', '(byte_size >= 0)'),
        ('ops', 'object_artifact', 'ck_ops_object_artifact_sha', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((sha256 ~ ''^[0-9a-f]{64}$''::text))', '(sha256 ~ ''^[0-9a-f]{64}$''::text)'),
        ('ops', 'object_artifact', 'ck_ops_object_artifact_enc', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((encryption_state = ANY (ARRAY[''SSE_KMS''::text, ''SSE_S3''::text, ''LOCAL_DEV''::text])))', '(encryption_state = ANY (ARRAY[''SSE_KMS''::text, ''SSE_S3''::text, ''LOCAL_DEV''::text]))'),
        ('ops', 'object_artifact', 'ck_ops_object_artifact_meta', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((jsonb_typeof(metadata) = ''object''::text))', '(jsonb_typeof(metadata) = ''object''::text)'),
        ('ops', 'job', 'job_id_not_null', 'n', 'id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL id', NULL),
        ('ops', 'job', 'job_display_id_not_null', 'n', 'display_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL display_id', NULL),
        ('ops', 'job', 'job_job_type_not_null', 'n', 'job_type', '', '', '', '', '', FALSE, FALSE, 'NOT NULL job_type', NULL),
        ('ops', 'job', 'job_queue_name_not_null', 'n', 'queue_name', '', '', '', '', '', FALSE, FALSE, 'NOT NULL queue_name', NULL),
        ('ops', 'job', 'job_status_not_null', 'n', 'status', '', '', '', '', '', FALSE, FALSE, 'NOT NULL status', NULL),
        ('ops', 'job', 'job_priority_not_null', 'n', 'priority', '', '', '', '', '', FALSE, FALSE, 'NOT NULL priority', NULL),
        ('ops', 'job', 'job_payload_not_null', 'n', 'payload', '', '', '', '', '', FALSE, FALSE, 'NOT NULL payload', NULL),
        ('ops', 'job', 'job_available_at_not_null', 'n', 'available_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL available_at', NULL),
        ('ops', 'job', 'job_max_attempts_not_null', 'n', 'max_attempts', '', '', '', '', '', FALSE, FALSE, 'NOT NULL max_attempts', NULL),
        ('ops', 'job', 'job_attempt_count_not_null', 'n', 'attempt_count', '', '', '', '', '', FALSE, FALSE, 'NOT NULL attempt_count', NULL),
        ('ops', 'job', 'job_correlation_id_not_null', 'n', 'correlation_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL correlation_id', NULL),
        ('ops', 'job', 'job_created_by_actor_type_not_null', 'n', 'created_by_actor_type', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_by_actor_type', NULL),
        ('ops', 'job', 'job_created_at_not_null', 'n', 'created_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_at', NULL),
        ('ops', 'job', 'job_updated_at_not_null', 'n', 'updated_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL updated_at', NULL),
        ('ops', 'job', 'job_lock_version_not_null', 'n', 'lock_version', '', '', '', '', '', FALSE, FALSE, 'NOT NULL lock_version', NULL),
        ('ops', 'job', 'job_job_version_not_null', 'n', 'job_version', '', '', '', '', '', FALSE, FALSE, 'NOT NULL job_version', NULL),
        ('ops', 'job', 'pk_ops_job', 'p', 'id', '', '', '', '', '', FALSE, FALSE, 'PRIMARY KEY (id)', NULL),
        ('ops', 'job', 'uq_ops_job_display_id', 'u', 'display_id', '', '', '', '', '', FALSE, FALSE, 'UNIQUE (display_id)', NULL),
        ('ops', 'job', 'ck_ops_job_status', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((status = ANY (ARRAY[''REQUESTED''::text, ''QUEUED''::text, ''RUNNING''::text, ''SUCCEEDED''::text, ''FAILED_RETRYABLE''::text, ''RETRY_SCHEDULED''::text, ''FAILED_TERMINAL''::text, ''QUARANTINED''::text, ''CANCELLED''::text, ''EXPIRED''::text])))', '(status = ANY (ARRAY[''REQUESTED''::text, ''QUEUED''::text, ''RUNNING''::text, ''SUCCEEDED''::text, ''FAILED_RETRYABLE''::text, ''RETRY_SCHEDULED''::text, ''FAILED_TERMINAL''::text, ''QUARANTINED''::text, ''CANCELLED''::text, ''EXPIRED''::text]))'),
        ('ops', 'job', 'ck_ops_job_priority', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((priority >= 0) AND (priority <= 100)))', '((priority >= 0) AND (priority <= 100))'),
        ('ops', 'job', 'ck_ops_job_attempts', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((((max_attempts >= 1) AND (max_attempts <= 50)) AND ((attempt_count >= 0) AND (attempt_count <= max_attempts))))', '(((max_attempts >= 1) AND (max_attempts <= 50)) AND ((attempt_count >= 0) AND (attempt_count <= max_attempts)))'),
        ('ops', 'job', 'ck_ops_job_budget', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((budget_jpy IS NULL) OR (budget_jpy >= 0)))', '((budget_jpy IS NULL) OR (budget_jpy >= 0))'),
        ('ops', 'job', 'ck_ops_job_payload', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((jsonb_typeof(payload) = ''object''::text))', '(jsonb_typeof(payload) = ''object''::text)'),
        ('ops', 'job', 'ck_ops_job_lease_pair', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((lease_owner IS NULL) = (lease_expires_at IS NULL)))', '((lease_owner IS NULL) = (lease_expires_at IS NULL))'),
        ('ops', 'job', 'ck_ops_job_completion', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((status <> ALL (ARRAY[''SUCCEEDED''::text, ''FAILED_TERMINAL''::text, ''QUARANTINED''::text, ''CANCELLED''::text, ''EXPIRED''::text])) OR (completed_at IS NOT NULL)))', '((status <> ALL (ARRAY[''SUCCEEDED''::text, ''FAILED_TERMINAL''::text, ''QUARANTINED''::text, ''CANCELLED''::text, ''EXPIRED''::text])) OR (completed_at IS NOT NULL))'),
        ('ops', 'job', 'ck_ops_job_version', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((lock_version >= 0))', '(lock_version >= 0)'),
        ('ops', 'job', 'ck_ops_job_version_positive', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((job_version >= 1))', '(job_version >= 1)'),
        ('ops', 'job', 'ck_ops_job_deadline_order', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((deadline_at IS NULL) OR (deadline_at > created_at)))', '((deadline_at IS NULL) OR (deadline_at > created_at))'),
        ('ops', 'job', 'ck_ops_job_cancel_request', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((cancel_requested_at IS NULL) OR (status <> ''SUCCEEDED''::text)))', '((cancel_requested_at IS NULL) OR (status <> ''SUCCEEDED''::text))'),
        ('ops', 'job', 'fk_ops_job_payload_artifact_id', 'f', 'payload_artifact_id', 'ops.object_artifact', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (payload_artifact_id) REFERENCES ops.object_artifact(id) ON DELETE RESTRICT', NULL),
        ('ops', 'job', 'fk_ops_job_parent_job_id', 'f', 'parent_job_id', 'ops.job', 'id', 'a', 'n', 's', FALSE, FALSE, 'FOREIGN KEY (parent_job_id) REFERENCES ops.job(id) ON DELETE SET NULL', NULL),
        ('ops', 'job_attempt', 'job_attempt_id_not_null', 'n', 'id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL id', NULL),
        ('ops', 'job_attempt', 'job_attempt_job_id_not_null', 'n', 'job_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL job_id', NULL),
        ('ops', 'job_attempt', 'job_attempt_attempt_no_not_null', 'n', 'attempt_no', '', '', '', '', '', FALSE, FALSE, 'NOT NULL attempt_no', NULL),
        ('ops', 'job_attempt', 'job_attempt_status_not_null', 'n', 'status', '', '', '', '', '', FALSE, FALSE, 'NOT NULL status', NULL),
        ('ops', 'job_attempt', 'job_attempt_worker_id_not_null', 'n', 'worker_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL worker_id', NULL),
        ('ops', 'job_attempt', 'job_attempt_handler_version_not_null', 'n', 'handler_version', '', '', '', '', '', FALSE, FALSE, 'NOT NULL handler_version', NULL),
        ('ops', 'job_attempt', 'job_attempt_started_at_not_null', 'n', 'started_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL started_at', NULL),
        ('ops', 'job_attempt', 'job_attempt_metrics_not_null', 'n', 'metrics', '', '', '', '', '', FALSE, FALSE, 'NOT NULL metrics', NULL),
        ('ops', 'job_attempt', 'job_attempt_created_at_not_null', 'n', 'created_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_at', NULL),
        ('ops', 'job_attempt', 'pk_ops_job_attempt', 'p', 'id', '', '', '', '', '', FALSE, FALSE, 'PRIMARY KEY (id)', NULL),
        ('ops', 'job_attempt', 'uq_ops_job_attempt_no', 'u', 'job_id,attempt_no', '', '', '', '', '', FALSE, FALSE, 'UNIQUE (job_id, attempt_no)', NULL),
        ('ops', 'job_attempt', 'ck_ops_job_attempt_status', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((status = ANY (ARRAY[''RUNNING''::text, ''SUCCEEDED''::text, ''FAILED''::text, ''CANCELLED''::text, ''TIMED_OUT''::text])))', '(status = ANY (ARRAY[''RUNNING''::text, ''SUCCEEDED''::text, ''FAILED''::text, ''CANCELLED''::text, ''TIMED_OUT''::text]))'),
        ('ops', 'job_attempt', 'ck_ops_job_attempt_no', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((attempt_no >= 1))', '(attempt_no >= 1)'),
        ('ops', 'job_attempt', 'ck_ops_job_attempt_metrics', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((jsonb_typeof(metrics) = ''object''::text))', '(jsonb_typeof(metrics) = ''object''::text)'),
        ('ops', 'job_attempt', 'ck_ops_job_attempt_end', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((status = ''RUNNING''::text) OR (completed_at IS NOT NULL)))', '((status = ''RUNNING''::text) OR (completed_at IS NOT NULL))'),
        ('ops', 'job_attempt', 'fk_ops_job_attempt_job_id', 'f', 'job_id', 'ops.job', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (job_id) REFERENCES ops.job(id) ON DELETE RESTRICT', NULL),
        ('ops', 'job_attempt', 'fk_ops_job_attempt_input_artifact_id', 'f', 'input_artifact_id', 'ops.object_artifact', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (input_artifact_id) REFERENCES ops.object_artifact(id) ON DELETE RESTRICT', NULL),
        ('ops', 'job_attempt', 'fk_ops_job_attempt_output_artifact_id', 'f', 'output_artifact_id', 'ops.object_artifact', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (output_artifact_id) REFERENCES ops.object_artifact(id) ON DELETE RESTRICT', NULL),
        ('ops', 'outbox_event', 'outbox_event_id_not_null', 'n', 'id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL id', NULL),
        ('ops', 'outbox_event', 'outbox_event_event_type_not_null', 'n', 'event_type', '', '', '', '', '', FALSE, FALSE, 'NOT NULL event_type', NULL),
        ('ops', 'outbox_event', 'outbox_event_event_version_not_null', 'n', 'event_version', '', '', '', '', '', FALSE, FALSE, 'NOT NULL event_version', NULL),
        ('ops', 'outbox_event', 'outbox_event_producer_not_null', 'n', 'producer', '', '', '', '', '', FALSE, FALSE, 'NOT NULL producer', NULL),
        ('ops', 'outbox_event', 'outbox_event_aggregate_type_not_null', 'n', 'aggregate_type', '', '', '', '', '', FALSE, FALSE, 'NOT NULL aggregate_type', NULL),
        ('ops', 'outbox_event', 'outbox_event_aggregate_id_not_null', 'n', 'aggregate_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL aggregate_id', NULL),
        ('ops', 'outbox_event', 'outbox_event_aggregate_version_not_null', 'n', 'aggregate_version', '', '', '', '', '', FALSE, FALSE, 'NOT NULL aggregate_version', NULL),
        ('ops', 'outbox_event', 'outbox_event_correlation_id_not_null', 'n', 'correlation_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL correlation_id', NULL),
        ('ops', 'outbox_event', 'outbox_event_actor_type_not_null', 'n', 'actor_type', '', '', '', '', '', FALSE, FALSE, 'NOT NULL actor_type', NULL),
        ('ops', 'outbox_event', 'outbox_event_payload_not_null', 'n', 'payload', '', '', '', '', '', FALSE, FALSE, 'NOT NULL payload', NULL),
        ('ops', 'outbox_event', 'outbox_event_payload_schema_hash_not_null', 'n', 'payload_schema_hash', '', '', '', '', '', FALSE, FALSE, 'NOT NULL payload_schema_hash', NULL),
        ('ops', 'outbox_event', 'outbox_event_status_not_null', 'n', 'status', '', '', '', '', '', FALSE, FALSE, 'NOT NULL status', NULL),
        ('ops', 'outbox_event', 'outbox_event_available_at_not_null', 'n', 'available_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL available_at', NULL),
        ('ops', 'outbox_event', 'outbox_event_publish_attempts_not_null', 'n', 'publish_attempts', '', '', '', '', '', FALSE, FALSE, 'NOT NULL publish_attempts', NULL),
        ('ops', 'outbox_event', 'outbox_event_created_at_not_null', 'n', 'created_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_at', NULL),
        ('ops', 'outbox_event', 'pk_ops_outbox_event', 'p', 'id', '', '', '', '', '', FALSE, FALSE, 'PRIMARY KEY (id)', NULL),
        ('ops', 'outbox_event', 'ck_ops_outbox_event_version', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((event_version >= 1) AND (aggregate_version >= 0)))', '((event_version >= 1) AND (aggregate_version >= 0))'),
        ('ops', 'outbox_event', 'ck_ops_outbox_payload', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((jsonb_typeof(payload) = ''object''::text))', '(jsonb_typeof(payload) = ''object''::text)'),
        ('ops', 'outbox_event', 'ck_ops_outbox_hash', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((payload_schema_hash ~ ''^[0-9a-f]{64}$''::text))', '(payload_schema_hash ~ ''^[0-9a-f]{64}$''::text)'),
        ('ops', 'outbox_event', 'ck_ops_outbox_status', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((status = ANY (ARRAY[''PENDING''::text, ''DISPATCHING''::text, ''PUBLISHED''::text, ''FAILED''::text, ''DEAD''::text])))', '(status = ANY (ARRAY[''PENDING''::text, ''DISPATCHING''::text, ''PUBLISHED''::text, ''FAILED''::text, ''DEAD''::text]))'),
        ('ops', 'outbox_event', 'ck_ops_outbox_attempts', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((publish_attempts >= 0))', '(publish_attempts >= 0)'),
        ('ops', 'outbox_event', 'ck_ops_outbox_published', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((status <> ''PUBLISHED''::text) OR (published_at IS NOT NULL)))', '((status <> ''PUBLISHED''::text) OR (published_at IS NOT NULL))'),
        ('ops', 'inbox_receipt', 'inbox_receipt_id_not_null', 'n', 'id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL id', NULL),
        ('ops', 'inbox_receipt', 'inbox_receipt_consumer_name_not_null', 'n', 'consumer_name', '', '', '', '', '', FALSE, FALSE, 'NOT NULL consumer_name', NULL),
        ('ops', 'inbox_receipt', 'inbox_receipt_handler_version_not_null', 'n', 'handler_version', '', '', '', '', '', FALSE, FALSE, 'NOT NULL handler_version', NULL),
        ('ops', 'inbox_receipt', 'inbox_receipt_event_id_not_null', 'n', 'event_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL event_id', NULL),
        ('ops', 'inbox_receipt', 'inbox_receipt_status_not_null', 'n', 'status', '', '', '', '', '', FALSE, FALSE, 'NOT NULL status', NULL),
        ('ops', 'inbox_receipt', 'inbox_receipt_received_at_not_null', 'n', 'received_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL received_at', NULL),
        ('ops', 'inbox_receipt', 'inbox_receipt_created_at_not_null', 'n', 'created_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_at', NULL),
        ('ops', 'inbox_receipt', 'pk_ops_inbox_receipt', 'p', 'id', '', '', '', '', '', FALSE, FALSE, 'PRIMARY KEY (id)', NULL),
        ('ops', 'inbox_receipt', 'uq_ops_inbox_receipt', 'u', 'consumer_name,handler_version,event_id', '', '', '', '', '', FALSE, FALSE, 'UNIQUE (consumer_name, handler_version, event_id)', NULL),
        ('ops', 'inbox_receipt', 'ck_ops_inbox_status', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((status = ANY (ARRAY[''PROCESSING''::text, ''PROCESSED''::text, ''FAILED''::text, ''IGNORED''::text])))', '(status = ANY (ARRAY[''PROCESSING''::text, ''PROCESSED''::text, ''FAILED''::text, ''IGNORED''::text]))'),
        ('ops', 'inbox_receipt', 'ck_ops_inbox_hash', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((result_hash IS NULL) OR (result_hash ~ ''^[0-9a-f]{64}$''::text)))', '((result_hash IS NULL) OR (result_hash ~ ''^[0-9a-f]{64}$''::text))'),
        ('ops', 'inbox_receipt', 'ck_ops_inbox_processed', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((status = ''PROCESSING''::text) OR (processed_at IS NOT NULL)))', '((status = ''PROCESSING''::text) OR (processed_at IS NOT NULL))'),
        ('ops', 'idempotency_record', 'idempotency_record_id_not_null', 'n', 'id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL id', NULL),
        ('ops', 'idempotency_record', 'idempotency_record_actor_fingerprint_not_null', 'n', 'actor_fingerprint', '', '', '', '', '', FALSE, FALSE, 'NOT NULL actor_fingerprint', NULL),
        ('ops', 'idempotency_record', 'idempotency_record_route_key_not_null', 'n', 'route_key', '', '', '', '', '', FALSE, FALSE, 'NOT NULL route_key', NULL),
        ('ops', 'idempotency_record', 'idempotency_record_idempotency_key_not_null', 'n', 'idempotency_key', '', '', '', '', '', FALSE, FALSE, 'NOT NULL idempotency_key', NULL),
        ('ops', 'idempotency_record', 'idempotency_record_request_hash_not_null', 'n', 'request_hash', '', '', '', '', '', FALSE, FALSE, 'NOT NULL request_hash', NULL),
        ('ops', 'idempotency_record', 'idempotency_record_status_not_null', 'n', 'status', '', '', '', '', '', FALSE, FALSE, 'NOT NULL status', NULL),
        ('ops', 'idempotency_record', 'idempotency_record_expires_at_not_null', 'n', 'expires_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL expires_at', NULL),
        ('ops', 'idempotency_record', 'idempotency_record_created_at_not_null', 'n', 'created_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_at', NULL),
        ('ops', 'idempotency_record', 'pk_ops_idempotency_record', 'p', 'id', '', '', '', '', '', FALSE, FALSE, 'PRIMARY KEY (id)', NULL),
        ('ops', 'idempotency_record', 'uq_ops_idempotency', 'u', 'actor_fingerprint,route_key,idempotency_key', '', '', '', '', '', FALSE, FALSE, 'UNIQUE (actor_fingerprint, route_key, idempotency_key)', NULL),
        ('ops', 'idempotency_record', 'ck_ops_idem_request_hash', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((request_hash ~ ''^[0-9a-f]{64}$''::text))', '(request_hash ~ ''^[0-9a-f]{64}$''::text)'),
        ('ops', 'idempotency_record', 'ck_ops_idem_status', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((status = ANY (ARRAY[''IN_PROGRESS''::text, ''COMPLETED''::text, ''FAILED''::text])))', '(status = ANY (ARRAY[''IN_PROGRESS''::text, ''COMPLETED''::text, ''FAILED''::text]))'),
        ('ops', 'idempotency_record', 'ck_ops_idem_response', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((status = ''IN_PROGRESS''::text) OR (response_status IS NOT NULL)))', '((status = ''IN_PROGRESS''::text) OR (response_status IS NOT NULL))'),
        ('ops', 'idempotency_record', 'ck_ops_idem_expiry', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((expires_at > created_at))', '(expires_at > created_at)'),
        ('ops', 'idempotency_record', 'ck_ops_idem_response_body', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((response_body IS NULL) OR (jsonb_typeof(response_body) = ''object''::text)))', '((response_body IS NULL) OR (jsonb_typeof(response_body) = ''object''::text))'),
        ('ops', 'idempotency_record', 'fk_ops_idempotency_record_response_artifact_id', 'f', 'response_artifact_id', 'ops.object_artifact', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (response_artifact_id) REFERENCES ops.object_artifact(id) ON DELETE RESTRICT', NULL),
        ('ops', 'audit_event', 'audit_event_id_not_null', 'n', 'id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL id', NULL),
        ('ops', 'audit_event', 'audit_event_occurred_at_not_null', 'n', 'occurred_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL occurred_at', NULL),
        ('ops', 'audit_event', 'audit_event_actor_type_not_null', 'n', 'actor_type', '', '', '', '', '', FALSE, FALSE, 'NOT NULL actor_type', NULL),
        ('ops', 'audit_event', 'audit_event_action_not_null', 'n', 'action', '', '', '', '', '', FALSE, FALSE, 'NOT NULL action', NULL),
        ('ops', 'audit_event', 'audit_event_target_type_not_null', 'n', 'target_type', '', '', '', '', '', FALSE, FALSE, 'NOT NULL target_type', NULL),
        ('ops', 'audit_event', 'audit_event_outcome_not_null', 'n', 'outcome', '', '', '', '', '', FALSE, FALSE, 'NOT NULL outcome', NULL),
        ('ops', 'audit_event', 'audit_event_severity_not_null', 'n', 'severity', '', '', '', '', '', FALSE, FALSE, 'NOT NULL severity', NULL),
        ('ops', 'audit_event', 'audit_event_correlation_id_not_null', 'n', 'correlation_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL correlation_id', NULL),
        ('ops', 'audit_event', 'audit_event_details_not_null', 'n', 'details', '', '', '', '', '', FALSE, FALSE, 'NOT NULL details', NULL),
        ('ops', 'audit_event', 'audit_event_created_at_not_null', 'n', 'created_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_at', NULL),
        ('ops', 'audit_event', 'pk_ops_audit_event', 'p', 'id', '', '', '', '', '', FALSE, FALSE, 'PRIMARY KEY (id)', NULL),
        ('ops', 'audit_event', 'ck_ops_audit_actor', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((actor_type = ANY (ARRAY[''USER''::text, ''SERVICE''::text, ''SCHEDULE''::text, ''SYSTEM''::text, ''ANONYMOUS''::text])))', '(actor_type = ANY (ARRAY[''USER''::text, ''SERVICE''::text, ''SCHEDULE''::text, ''SYSTEM''::text, ''ANONYMOUS''::text]))'),
        ('ops', 'audit_event', 'ck_ops_audit_outcome', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((outcome = ANY (ARRAY[''SUCCESS''::text, ''DENIED''::text, ''FAILED''::text, ''NOOP''::text])))', '(outcome = ANY (ARRAY[''SUCCESS''::text, ''DENIED''::text, ''FAILED''::text, ''NOOP''::text]))'),
        ('ops', 'audit_event', 'ck_ops_audit_severity', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((severity = ANY (ARRAY[''INFO''::text, ''NOTICE''::text, ''WARNING''::text, ''CRITICAL''::text])))', '(severity = ANY (ARRAY[''INFO''::text, ''NOTICE''::text, ''WARNING''::text, ''CRITICAL''::text]))'),
        ('ops', 'audit_event', 'ck_ops_audit_before_hash', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((before_hash IS NULL) OR (before_hash ~ ''^[0-9a-f]{64}$''::text)))', '((before_hash IS NULL) OR (before_hash ~ ''^[0-9a-f]{64}$''::text))'),
        ('ops', 'audit_event', 'ck_ops_audit_after_hash', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((after_hash IS NULL) OR (after_hash ~ ''^[0-9a-f]{64}$''::text)))', '((after_hash IS NULL) OR (after_hash ~ ''^[0-9a-f]{64}$''::text))'),
        ('ops', 'audit_event', 'ck_ops_audit_details', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((jsonb_typeof(details) = ''object''::text))', '(jsonb_typeof(details) = ''object''::text)'),
        ('ops', 'runtime_setting_version', 'runtime_setting_version_id_not_null', 'n', 'id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL id', NULL),
        ('ops', 'runtime_setting_version', 'runtime_setting_version_setting_key_not_null', 'n', 'setting_key', '', '', '', '', '', FALSE, FALSE, 'NOT NULL setting_key', NULL),
        ('ops', 'runtime_setting_version', 'runtime_setting_version_scope_type_not_null', 'n', 'scope_type', '', '', '', '', '', FALSE, FALSE, 'NOT NULL scope_type', NULL),
        ('ops', 'runtime_setting_version', 'runtime_setting_version_version_no_not_null', 'n', 'version_no', '', '', '', '', '', FALSE, FALSE, 'NOT NULL version_no', NULL),
        ('ops', 'runtime_setting_version', 'runtime_setting_version_setting_class_not_null', 'n', 'setting_class', '', '', '', '', '', FALSE, FALSE, 'NOT NULL setting_class', NULL),
        ('ops', 'runtime_setting_version', 'runtime_setting_version_value_not_null', 'n', 'value', '', '', '', '', '', FALSE, FALSE, 'NOT NULL value', NULL),
        ('ops', 'runtime_setting_version', 'runtime_setting_version_value_sha256_not_null', 'n', 'value_sha256', '', '', '', '', '', FALSE, FALSE, 'NOT NULL value_sha256', NULL),
        ('ops', 'runtime_setting_version', 'runtime_setting_version_status_not_null', 'n', 'status', '', '', '', '', '', FALSE, FALSE, 'NOT NULL status', NULL),
        ('ops', 'runtime_setting_version', 'runtime_setting_version_created_by_principal_id_not_null', 'n', 'created_by_principal_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_by_principal_id', NULL),
        ('ops', 'runtime_setting_version', 'runtime_setting_version_created_at_not_null', 'n', 'created_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_at', NULL),
        ('ops', 'runtime_setting_version', 'pk_ops_runtime_setting_version', 'p', 'id', '', '', '', '', '', FALSE, FALSE, 'PRIMARY KEY (id)', NULL),
        ('ops', 'runtime_setting_version', 'uq_ops_setting_version', 'u', 'setting_key,scope_type,scope_id,version_no', '', '', '', '', '', FALSE, FALSE, 'UNIQUE (setting_key, scope_type, scope_id, version_no)', NULL),
        ('ops', 'runtime_setting_version', 'ck_ops_setting_scope', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((scope_type = ANY (ARRAY[''GLOBAL''::text, ''SITE''::text, ''CATEGORY''::text, ''ARTICLE''::text, ''PROVIDER''::text, ''TASK''::text])))', '(scope_type = ANY (ARRAY[''GLOBAL''::text, ''SITE''::text, ''CATEGORY''::text, ''ARTICLE''::text, ''PROVIDER''::text, ''TASK''::text]))'),
        ('ops', 'runtime_setting_version', 'ck_ops_setting_scope_id', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((((scope_type = ''GLOBAL''::text) AND (scope_id IS NULL)) OR ((scope_type <> ''GLOBAL''::text) AND (scope_id IS NOT NULL))))', '(((scope_type = ''GLOBAL''::text) AND (scope_id IS NULL)) OR ((scope_type <> ''GLOBAL''::text) AND (scope_id IS NOT NULL)))'),
        ('ops', 'runtime_setting_version', 'ck_ops_setting_version', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((version_no >= 1))', '(version_no >= 1)'),
        ('ops', 'runtime_setting_version', 'ck_ops_setting_class', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((setting_class = ANY (ARRAY[''FEATURE_FLAG''::text, ''THRESHOLD''::text, ''PROVIDER''::text, ''FRESHNESS''::text, ''BUDGET''::text, ''UI''::text, ''OTHER''::text])))', '(setting_class = ANY (ARRAY[''FEATURE_FLAG''::text, ''THRESHOLD''::text, ''PROVIDER''::text, ''FRESHNESS''::text, ''BUDGET''::text, ''UI''::text, ''OTHER''::text]))'),
        ('ops', 'runtime_setting_version', 'ck_ops_setting_no_secret', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((setting_class <> ''SECRET''::text))', '(setting_class <> ''SECRET''::text)'),
        ('ops', 'runtime_setting_version', 'ck_ops_setting_value', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((jsonb_typeof(value) = ''object''::text))', '(jsonb_typeof(value) = ''object''::text)'),
        ('ops', 'runtime_setting_version', 'ck_ops_setting_hash', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((value_sha256 ~ ''^[0-9a-f]{64}$''::text))', '(value_sha256 ~ ''^[0-9a-f]{64}$''::text)'),
        ('ops', 'runtime_setting_version', 'ck_ops_setting_status', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((status = ANY (ARRAY[''DRAFT''::text, ''ACTIVE''::text, ''RETIRED''::text, ''REJECTED''::text])))', '(status = ANY (ARRAY[''DRAFT''::text, ''ACTIVE''::text, ''RETIRED''::text, ''REJECTED''::text]))'),
        ('ops', 'runtime_setting_version', 'ck_ops_setting_window', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((effective_to IS NULL) OR (effective_from IS NULL) OR (effective_to > effective_from)))', '((effective_to IS NULL) OR (effective_from IS NULL) OR (effective_to > effective_from))'),
        ('ops', 'runtime_setting_version', 'fk_ops_runtime_setting_version_created_by_principal_id', 'f', 'created_by_principal_id', 'iam.principal', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (created_by_principal_id) REFERENCES iam.principal(id) ON DELETE RESTRICT', NULL),
        ('ops', 'runtime_setting_version', 'fk_ops_runtime_setting_version_approved_by_principal_id', 'f', 'approved_by_principal_id', 'iam.principal', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (approved_by_principal_id) REFERENCES iam.principal(id) ON DELETE RESTRICT', NULL),
        ('iam', 'principal', 'principal_id_not_null', 'n', 'id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL id', NULL),
        ('iam', 'principal', 'principal_display_id_not_null', 'n', 'display_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL display_id', NULL),
        ('iam', 'principal', 'principal_principal_type_not_null', 'n', 'principal_type', '', '', '', '', '', FALSE, FALSE, 'NOT NULL principal_type', NULL),
        ('iam', 'principal', 'principal_status_not_null', 'n', 'status', '', '', '', '', '', FALSE, FALSE, 'NOT NULL status', NULL),
        ('iam', 'principal', 'principal_display_name_not_null', 'n', 'display_name', '', '', '', '', '', FALSE, FALSE, 'NOT NULL display_name', NULL),
        ('iam', 'principal', 'principal_created_at_not_null', 'n', 'created_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_at', NULL),
        ('iam', 'principal', 'principal_updated_at_not_null', 'n', 'updated_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL updated_at', NULL),
        ('iam', 'principal', 'principal_lock_version_not_null', 'n', 'lock_version', '', '', '', '', '', FALSE, FALSE, 'NOT NULL lock_version', NULL),
        ('iam', 'principal', 'pk_iam_principal', 'p', 'id', '', '', '', '', '', FALSE, FALSE, 'PRIMARY KEY (id)', NULL),
        ('iam', 'principal', 'uq_iam_principal_display', 'u', 'display_id', '', '', '', '', '', FALSE, FALSE, 'UNIQUE (display_id)', NULL),
        ('iam', 'principal', 'ck_iam_principal_type', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((principal_type = ANY (ARRAY[''USER''::text, ''SERVICE''::text])))', '(principal_type = ANY (ARRAY[''USER''::text, ''SERVICE''::text]))'),
        ('iam', 'principal', 'ck_iam_principal_status', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((status = ANY (ARRAY[''ACTIVE''::text, ''SUSPENDED''::text, ''DEACTIVATED''::text])))', '(status = ANY (ARRAY[''ACTIVE''::text, ''SUSPENDED''::text, ''DEACTIVATED''::text]))'),
        ('iam', 'principal', 'ck_iam_principal_deactivation', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((status <> ''DEACTIVATED''::text) OR (deactivated_at IS NOT NULL)))', '((status <> ''DEACTIVATED''::text) OR (deactivated_at IS NOT NULL))'),
        ('iam', 'principal', 'ck_iam_principal_version', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((lock_version >= 0))', '(lock_version >= 0)'),
        ('iam', 'user_account', 'user_account_principal_id_not_null', 'n', 'principal_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL principal_id', NULL),
        ('iam', 'user_account', 'user_account_oidc_issuer_not_null', 'n', 'oidc_issuer', '', '', '', '', '', FALSE, FALSE, 'NOT NULL oidc_issuer', NULL),
        ('iam', 'user_account', 'user_account_oidc_subject_not_null', 'n', 'oidc_subject', '', '', '', '', '', FALSE, FALSE, 'NOT NULL oidc_subject', NULL),
        ('iam', 'user_account', 'user_account_email_verified_not_null', 'n', 'email_verified', '', '', '', '', '', FALSE, FALSE, 'NOT NULL email_verified', NULL),
        ('iam', 'user_account', 'user_account_mfa_required_not_null', 'n', 'mfa_required', '', '', '', '', '', FALSE, FALSE, 'NOT NULL mfa_required', NULL),
        ('iam', 'user_account', 'user_account_created_at_not_null', 'n', 'created_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_at', NULL),
        ('iam', 'user_account', 'pk_iam_user_account', 'p', 'principal_id', '', '', '', '', '', FALSE, FALSE, 'PRIMARY KEY (principal_id)', NULL),
        ('iam', 'user_account', 'uq_iam_user_oidc', 'u', 'oidc_issuer,oidc_subject', '', '', '', '', '', FALSE, FALSE, 'UNIQUE (oidc_issuer, oidc_subject)', NULL),
        ('iam', 'user_account', 'ck_iam_user_https_issuer', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((oidc_issuer ~ ''^https://''::text))', '(oidc_issuer ~ ''^https://''::text)'),
        ('iam', 'user_account', 'fk_iam_user_account_principal_id', 'f', 'principal_id', 'iam.principal', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (principal_id) REFERENCES iam.principal(id) ON DELETE RESTRICT', NULL),
        ('iam', 'service_principal', 'service_principal_principal_id_not_null', 'n', 'principal_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL principal_id', NULL),
        ('iam', 'service_principal', 'service_principal_service_code_not_null', 'n', 'service_code', '', '', '', '', '', FALSE, FALSE, 'NOT NULL service_code', NULL),
        ('iam', 'service_principal', 'service_principal_workload_identity_not_null', 'n', 'workload_identity', '', '', '', '', '', FALSE, FALSE, 'NOT NULL workload_identity', NULL),
        ('iam', 'service_principal', 'service_principal_allowed_environment_not_null', 'n', 'allowed_environment', '', '', '', '', '', FALSE, FALSE, 'NOT NULL allowed_environment', NULL),
        ('iam', 'service_principal', 'service_principal_created_at_not_null', 'n', 'created_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_at', NULL),
        ('iam', 'service_principal', 'pk_iam_service_principal', 'p', 'principal_id', '', '', '', '', '', FALSE, FALSE, 'PRIMARY KEY (principal_id)', NULL),
        ('iam', 'service_principal', 'uq_iam_service_code', 'u', 'service_code', '', '', '', '', '', FALSE, FALSE, 'UNIQUE (service_code)', NULL),
        ('iam', 'service_principal', 'uq_iam_service_workload', 'u', 'workload_identity,allowed_environment', '', '', '', '', '', FALSE, FALSE, 'UNIQUE (workload_identity, allowed_environment)', NULL),
        ('iam', 'service_principal', 'ck_iam_service_env', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((allowed_environment = ANY (ARRAY[''LOCAL''::text, ''CI''::text, ''STAGING''::text, ''PRODUCTION''::text])))', '(allowed_environment = ANY (ARRAY[''LOCAL''::text, ''CI''::text, ''STAGING''::text, ''PRODUCTION''::text]))'),
        ('iam', 'service_principal', 'fk_iam_service_principal_principal_id', 'f', 'principal_id', 'iam.principal', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (principal_id) REFERENCES iam.principal(id) ON DELETE RESTRICT', NULL),
        ('iam', 'role', 'role_id_not_null', 'n', 'id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL id', NULL),
        ('iam', 'role', 'role_role_code_not_null', 'n', 'role_code', '', '', '', '', '', FALSE, FALSE, 'NOT NULL role_code', NULL),
        ('iam', 'role', 'role_name_not_null', 'n', 'name', '', '', '', '', '', FALSE, FALSE, 'NOT NULL name', NULL),
        ('iam', 'role', 'role_description_not_null', 'n', 'description', '', '', '', '', '', FALSE, FALSE, 'NOT NULL description', NULL),
        ('iam', 'role', 'role_is_system_role_not_null', 'n', 'is_system_role', '', '', '', '', '', FALSE, FALSE, 'NOT NULL is_system_role', NULL),
        ('iam', 'role', 'role_status_not_null', 'n', 'status', '', '', '', '', '', FALSE, FALSE, 'NOT NULL status', NULL),
        ('iam', 'role', 'role_created_at_not_null', 'n', 'created_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_at', NULL),
        ('iam', 'role', 'pk_iam_role', 'p', 'id', '', '', '', '', '', FALSE, FALSE, 'PRIMARY KEY (id)', NULL),
        ('iam', 'role', 'uq_iam_role_code', 'u', 'role_code', '', '', '', '', '', FALSE, FALSE, 'UNIQUE (role_code)', NULL),
        ('iam', 'role', 'ck_iam_role_status', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((status = ANY (ARRAY[''ACTIVE''::text, ''RETIRED''::text])))', '(status = ANY (ARRAY[''ACTIVE''::text, ''RETIRED''::text]))'),
        ('iam', 'permission', 'permission_id_not_null', 'n', 'id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL id', NULL),
        ('iam', 'permission', 'permission_permission_code_not_null', 'n', 'permission_code', '', '', '', '', '', FALSE, FALSE, 'NOT NULL permission_code', NULL),
        ('iam', 'permission', 'permission_description_not_null', 'n', 'description', '', '', '', '', '', FALSE, FALSE, 'NOT NULL description', NULL),
        ('iam', 'permission', 'permission_risk_level_not_null', 'n', 'risk_level', '', '', '', '', '', FALSE, FALSE, 'NOT NULL risk_level', NULL),
        ('iam', 'permission', 'permission_status_not_null', 'n', 'status', '', '', '', '', '', FALSE, FALSE, 'NOT NULL status', NULL),
        ('iam', 'permission', 'permission_created_at_not_null', 'n', 'created_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_at', NULL),
        ('iam', 'permission', 'pk_iam_permission', 'p', 'id', '', '', '', '', '', FALSE, FALSE, 'PRIMARY KEY (id)', NULL),
        ('iam', 'permission', 'uq_iam_permission_code', 'u', 'permission_code', '', '', '', '', '', FALSE, FALSE, 'UNIQUE (permission_code)', NULL),
        ('iam', 'permission', 'ck_iam_permission_risk', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((risk_level = ANY (ARRAY[''LOW''::text, ''MEDIUM''::text, ''HIGH''::text, ''CRITICAL''::text])))', '(risk_level = ANY (ARRAY[''LOW''::text, ''MEDIUM''::text, ''HIGH''::text, ''CRITICAL''::text]))'),
        ('iam', 'permission', 'ck_iam_permission_status', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((status = ANY (ARRAY[''ACTIVE''::text, ''RETIRED''::text])))', '(status = ANY (ARRAY[''ACTIVE''::text, ''RETIRED''::text]))'),
        ('iam', 'role_permission', 'role_permission_role_id_not_null', 'n', 'role_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL role_id', NULL),
        ('iam', 'role_permission', 'role_permission_permission_id_not_null', 'n', 'permission_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL permission_id', NULL),
        ('iam', 'role_permission', 'role_permission_created_at_not_null', 'n', 'created_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_at', NULL),
        ('iam', 'role_permission', 'pk_iam_role_permission', 'p', 'role_id,permission_id', '', '', '', '', '', FALSE, FALSE, 'PRIMARY KEY (role_id, permission_id)', NULL),
        ('iam', 'role_permission', 'fk_iam_role_permission_role_id', 'f', 'role_id', 'iam.role', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (role_id) REFERENCES iam.role(id) ON DELETE RESTRICT', NULL),
        ('iam', 'role_permission', 'fk_iam_role_permission_permission_id', 'f', 'permission_id', 'iam.permission', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (permission_id) REFERENCES iam.permission(id) ON DELETE RESTRICT', NULL),
        ('iam', 'principal_role_assignment', 'principal_role_assignment_id_not_null', 'n', 'id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL id', NULL),
        ('iam', 'principal_role_assignment', 'principal_role_assignment_principal_id_not_null', 'n', 'principal_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL principal_id', NULL),
        ('iam', 'principal_role_assignment', 'principal_role_assignment_role_id_not_null', 'n', 'role_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL role_id', NULL),
        ('iam', 'principal_role_assignment', 'principal_role_assignment_scope_type_not_null', 'n', 'scope_type', '', '', '', '', '', FALSE, FALSE, 'NOT NULL scope_type', NULL),
        ('iam', 'principal_role_assignment', 'principal_role_assignment_valid_from_not_null', 'n', 'valid_from', '', '', '', '', '', FALSE, FALSE, 'NOT NULL valid_from', NULL),
        ('iam', 'principal_role_assignment', 'principal_role_assignment_assigned_by_principal_id_not_null', 'n', 'assigned_by_principal_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL assigned_by_principal_id', NULL),
        ('iam', 'principal_role_assignment', 'principal_role_assignment_assignment_reason_not_null', 'n', 'assignment_reason', '', '', '', '', '', FALSE, FALSE, 'NOT NULL assignment_reason', NULL),
        ('iam', 'principal_role_assignment', 'principal_role_assignment_created_at_not_null', 'n', 'created_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_at', NULL),
        ('iam', 'principal_role_assignment', 'pk_iam_principal_role_assignment', 'p', 'id', '', '', '', '', '', FALSE, FALSE, 'PRIMARY KEY (id)', NULL),
        ('iam', 'principal_role_assignment', 'ck_iam_assignment_scope', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((scope_type = ANY (ARRAY[''GLOBAL''::text, ''SITE''::text, ''CATEGORY''::text, ''ARTICLE''::text])))', '(scope_type = ANY (ARRAY[''GLOBAL''::text, ''SITE''::text, ''CATEGORY''::text, ''ARTICLE''::text]))'),
        ('iam', 'principal_role_assignment', 'ck_iam_assignment_scope_id', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((((scope_type = ''GLOBAL''::text) AND (scope_id IS NULL)) OR ((scope_type <> ''GLOBAL''::text) AND (scope_id IS NOT NULL))))', '(((scope_type = ''GLOBAL''::text) AND (scope_id IS NULL)) OR ((scope_type <> ''GLOBAL''::text) AND (scope_id IS NOT NULL)))'),
        ('iam', 'principal_role_assignment', 'ck_iam_assignment_window', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((valid_to IS NULL) OR (valid_to > valid_from)))', '((valid_to IS NULL) OR (valid_to > valid_from))'),
        ('iam', 'principal_role_assignment', 'ck_iam_assignment_revoke_pair', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((revoked_at IS NULL) = (revoked_by_principal_id IS NULL)))', '((revoked_at IS NULL) = (revoked_by_principal_id IS NULL))'),
        ('iam', 'principal_role_assignment', 'fk_iam_principal_role_assignment_principal_id', 'f', 'principal_id', 'iam.principal', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (principal_id) REFERENCES iam.principal(id) ON DELETE RESTRICT', NULL),
        ('iam', 'principal_role_assignment', 'fk_iam_principal_role_assignment_role_id', 'f', 'role_id', 'iam.role', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (role_id) REFERENCES iam.role(id) ON DELETE RESTRICT', NULL),
        ('iam', 'principal_role_assignment', 'fk_iam_principal_role_assignment_assigned_by_principal_id', 'f', 'assigned_by_principal_id', 'iam.principal', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (assigned_by_principal_id) REFERENCES iam.principal(id) ON DELETE RESTRICT', NULL),
        ('iam', 'principal_role_assignment', 'fk_iam_principal_role_assignment_revoked_by_principal_id', 'f', 'revoked_by_principal_id', 'iam.principal', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (revoked_by_principal_id) REFERENCES iam.principal(id) ON DELETE RESTRICT', NULL),
        ('iam', 'session_revocation', 'session_revocation_id_not_null', 'n', 'id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL id', NULL),
        ('iam', 'session_revocation', 'session_revocation_principal_id_not_null', 'n', 'principal_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL principal_id', NULL),
        ('iam', 'session_revocation', 'session_revocation_oidc_issuer_not_null', 'n', 'oidc_issuer', '', '', '', '', '', FALSE, FALSE, 'NOT NULL oidc_issuer', NULL),
        ('iam', 'session_revocation', 'session_revocation_oidc_subject_not_null', 'n', 'oidc_subject', '', '', '', '', '', FALSE, FALSE, 'NOT NULL oidc_subject', NULL),
        ('iam', 'session_revocation', 'session_revocation_revoke_before_not_null', 'n', 'revoke_before', '', '', '', '', '', FALSE, FALSE, 'NOT NULL revoke_before', NULL),
        ('iam', 'session_revocation', 'session_revocation_reason_not_null', 'n', 'reason', '', '', '', '', '', FALSE, FALSE, 'NOT NULL reason', NULL),
        ('iam', 'session_revocation', 'session_revocation_created_by_principal_id_not_null', 'n', 'created_by_principal_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_by_principal_id', NULL),
        ('iam', 'session_revocation', 'session_revocation_created_at_not_null', 'n', 'created_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_at', NULL),
        ('iam', 'session_revocation', 'pk_iam_session_revocation', 'p', 'id', '', '', '', '', '', FALSE, FALSE, 'PRIMARY KEY (id)', NULL),
        ('iam', 'session_revocation', 'ck_iam_session_issuer', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((oidc_issuer ~ ''^https://''::text))', '(oidc_issuer ~ ''^https://''::text)'),
        ('iam', 'session_revocation', 'ck_iam_session_expiry', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((expires_at IS NULL) OR (expires_at > revoke_before)))', '((expires_at IS NULL) OR (expires_at > revoke_before))'),
        ('iam', 'session_revocation', 'fk_iam_session_revocation_principal_id', 'f', 'principal_id', 'iam.principal', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (principal_id) REFERENCES iam.principal(id) ON DELETE RESTRICT', NULL),
        ('iam', 'session_revocation', 'fk_iam_session_revocation_created_by_principal_id', 'f', 'created_by_principal_id', 'iam.principal', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (created_by_principal_id) REFERENCES iam.principal(id) ON DELETE RESTRICT', NULL),
        ('iam', 'break_glass_record', 'break_glass_record_id_not_null', 'n', 'id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL id', NULL),
        ('iam', 'break_glass_record', 'break_glass_record_display_id_not_null', 'n', 'display_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL display_id', NULL),
        ('iam', 'break_glass_record', 'break_glass_record_principal_id_not_null', 'n', 'principal_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL principal_id', NULL),
        ('iam', 'break_glass_record', 'break_glass_record_incident_id_not_null', 'n', 'incident_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL incident_id', NULL),
        ('iam', 'break_glass_record', 'break_glass_record_reason_not_null', 'n', 'reason', '', '', '', '', '', FALSE, FALSE, 'NOT NULL reason', NULL),
        ('iam', 'break_glass_record', 'break_glass_record_approved_by_principal_id_not_null', 'n', 'approved_by_principal_id', '', '', '', '', '', FALSE, FALSE, 'NOT NULL approved_by_principal_id', NULL),
        ('iam', 'break_glass_record', 'break_glass_record_permissions_not_null', 'n', 'permissions', '', '', '', '', '', FALSE, FALSE, 'NOT NULL permissions', NULL),
        ('iam', 'break_glass_record', 'break_glass_record_started_at_not_null', 'n', 'started_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL started_at', NULL),
        ('iam', 'break_glass_record', 'break_glass_record_expires_at_not_null', 'n', 'expires_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL expires_at', NULL),
        ('iam', 'break_glass_record', 'break_glass_record_created_at_not_null', 'n', 'created_at', '', '', '', '', '', FALSE, FALSE, 'NOT NULL created_at', NULL),
        ('iam', 'break_glass_record', 'pk_iam_break_glass_record', 'p', 'id', '', '', '', '', '', FALSE, FALSE, 'PRIMARY KEY (id)', NULL),
        ('iam', 'break_glass_record', 'uq_iam_break_glass_display', 'u', 'display_id', '', '', '', '', '', FALSE, FALSE, 'UNIQUE (display_id)', NULL),
        ('iam', 'break_glass_record', 'ck_iam_break_glass_window', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK (((expires_at > started_at) AND ((ended_at IS NULL) OR (ended_at >= started_at))))', '((expires_at > started_at) AND ((ended_at IS NULL) OR (ended_at >= started_at)))'),
        ('iam', 'break_glass_record', 'ck_iam_break_glass_permissions', 'c', '', '', '', '', '', '', FALSE, FALSE, 'CHECK ((jsonb_typeof(permissions) = ''object''::text))', '(jsonb_typeof(permissions) = ''object''::text)'),
        ('iam', 'break_glass_record', 'fk_iam_break_glass_record_principal_id', 'f', 'principal_id', 'iam.principal', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (principal_id) REFERENCES iam.principal(id) ON DELETE RESTRICT', NULL),
        ('iam', 'break_glass_record', 'fk_iam_break_glass_record_approved_by_principal_id', 'f', 'approved_by_principal_id', 'iam.principal', 'id', 'a', 'r', 's', FALSE, FALSE, 'FOREIGN KEY (approved_by_principal_id) REFERENCES iam.principal(id) ON DELETE RESTRICT', NULL)
    ) AS expected(
        schema_name, table_name, constraint_name, constraint_type,
        key_columns, target_table, target_columns, update_action, delete_action,
        match_type, is_deferrable, initially_deferred, constraint_definition,
        check_expression
    )
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = namespace.oid
     AND relation.relname = expected.table_name
    JOIN pg_catalog.pg_constraint AS constraint_record
      ON constraint_record.conrelid = relation.oid
     AND constraint_record.conname = expected.constraint_name
     AND constraint_record.contype = expected.constraint_type
    LEFT JOIN pg_catalog.pg_class AS target_relation
      ON target_relation.oid = constraint_record.confrelid
    LEFT JOIN pg_catalog.pg_namespace AS target_namespace
      ON target_namespace.oid = target_relation.relnamespace
    LEFT JOIN pg_catalog.pg_class AS constraint_index_relation
      ON constraint_index_relation.oid = constraint_record.conindid
    LEFT JOIN pg_catalog.pg_index AS constraint_index
      ON constraint_index.indexrelid = constraint_record.conindid
    WHERE constraint_record.convalidated IS TRUE
      AND constraint_record.conenforced IS TRUE
      AND constraint_record.conislocal IS TRUE
      AND constraint_record.coninhcount = 0
      AND constraint_record.connoinherit
              = (expected.constraint_type = ANY (
                    ARRAY['p', 'u', 'f']::pg_catalog.text[]
                ))
      AND constraint_record.conparentid = 0
      AND constraint_record.conperiod IS FALSE
      AND constraint_record.connamespace = namespace.oid
      AND (
          (
              expected.constraint_type = ANY (
                  ARRAY['p', 'u']::pg_catalog.text[]
              )
              AND constraint_record.conindid <> 0
              AND constraint_index_relation.relkind = 'i'
              AND constraint_index_relation.relnamespace
                      = constraint_record.connamespace
              AND constraint_index_relation.relname
                      = constraint_record.conname
              AND constraint_index.indrelid = constraint_record.conrelid
              AND constraint_index.indisunique IS TRUE
              AND constraint_index.indisvalid IS TRUE
              AND constraint_index.indisready IS TRUE
              AND constraint_index.indisprimary
                      = (expected.constraint_type = 'p')
          )
          OR (
              expected.constraint_type = 'f'
              AND constraint_record.conindid <> 0
              AND constraint_index_relation.relkind = 'i'
              AND constraint_index.indrelid = constraint_record.confrelid
              AND constraint_index.indisunique IS TRUE
              AND constraint_index.indisvalid IS TRUE
              AND constraint_index.indisready IS TRUE
          )
          OR (
              expected.constraint_type = ANY (
                  ARRAY['c', 'n']::pg_catalog.text[]
              )
              AND constraint_record.conindid = 0
          )
      )
      AND CASE WHEN expected.constraint_type = 'c' THEN '' ELSE COALESCE((
              SELECT pg_catalog.string_agg(
                  attribute.attname, ',' ORDER BY key_item.ordinality
              )
              FROM pg_catalog.unnest(constraint_record.conkey)
                   WITH ORDINALITY AS key_item(attribute_number, ordinality)
              JOIN pg_catalog.pg_attribute AS attribute
                ON attribute.attrelid = constraint_record.conrelid
               AND attribute.attnum = key_item.attribute_number
          ), '') END = expected.key_columns
      AND COALESCE(target_namespace.nspname || '.' || target_relation.relname, '')
              = expected.target_table
      AND COALESCE((
          SELECT pg_catalog.string_agg(attribute.attname, ',' ORDER BY key_item.ordinality)
          FROM pg_catalog.unnest(constraint_record.confkey)
               WITH ORDINALITY AS key_item(attribute_number, ordinality)
          JOIN pg_catalog.pg_attribute AS attribute
            ON attribute.attrelid = constraint_record.confrelid
           AND attribute.attnum = key_item.attribute_number
      ), '') = expected.target_columns
      AND CASE WHEN expected.constraint_type = 'f'
               THEN constraint_record.confupdtype::pg_catalog.text
               ELSE '' END = expected.update_action
      AND CASE WHEN expected.constraint_type = 'f'
               THEN constraint_record.confdeltype::pg_catalog.text
               ELSE '' END = expected.delete_action
      AND CASE WHEN expected.constraint_type = 'f'
               THEN constraint_record.confmatchtype::pg_catalog.text
               ELSE '' END = expected.match_type
      AND constraint_record.condeferrable = expected.is_deferrable
      AND constraint_record.condeferred = expected.initially_deferred
      AND pg_catalog.pg_get_constraintdef(constraint_record.oid, false)
              = expected.constraint_definition
      AND pg_catalog.pg_get_expr(
              constraint_record.conbin, constraint_record.conrelid, false
          ) IS NOT DISTINCT FROM expected.check_expression
      AND pg_catalog.obj_description(
              constraint_record.oid, 'pg_constraint'
          ) IS NULL
      AND pg_catalog.obj_description(
              constraint_record.conindid, 'pg_class'
          ) IS NULL;
    IF observed_count <> 267 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
    ) <> 267 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
          AND constraint_record.contype = 'n'
    ) <> 151 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
          AND constraint_record.contype = 'p'
    ) <> 17 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
          AND constraint_record.contype = 'u'
    ) <> 13 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
          AND constraint_record.contype = 'c'
    ) <> 66 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
          AND constraint_record.contype = 'f'
    ) <> 20 THEN
        RAISE EXCEPTION 'ST0303_CONSTRAINT_CATALOG_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        ('ops', 'object_artifact', 'uq_ops_object_artifact_location', 'btree', TRUE, TRUE, 'bucket_name,object_key,object_version', 'CREATE UNIQUE INDEX uq_ops_object_artifact_location ON ops.object_artifact USING btree (bucket_name, object_key, object_version) NULLS NOT DISTINCT', NULL, NULL, ''),
        ('ops', 'object_artifact', 'ix_ops_object_artifact_sha', 'btree', FALSE, FALSE, 'sha256', 'CREATE INDEX ix_ops_object_artifact_sha ON ops.object_artifact USING btree (sha256)', NULL, NULL, ''),
        ('ops', 'object_artifact', 'ix_ops_object_artifact_kind_created', 'btree', FALSE, FALSE, 'artifact_kind,created_at', 'CREATE INDEX ix_ops_object_artifact_kind_created ON ops.object_artifact USING btree (artifact_kind, created_at)', NULL, NULL, ''),
        ('ops', 'job', 'uq_ops_job_idempotency', 'btree', TRUE, FALSE, 'job_type,idempotency_key', 'CREATE UNIQUE INDEX uq_ops_job_idempotency ON ops.job USING btree (job_type, idempotency_key) WHERE (idempotency_key IS NOT NULL)', NULL, '(idempotency_key IS NOT NULL)', ''),
        ('ops', 'job', 'ix_ops_job_ready', 'btree', FALSE, FALSE, 'queue_name,priority,available_at', 'CREATE INDEX ix_ops_job_ready ON ops.job USING btree (queue_name, priority, available_at) WHERE (status = ANY (ARRAY[''REQUESTED''::text, ''QUEUED''::text, ''RETRY_SCHEDULED''::text]))', NULL, '(status = ANY (ARRAY[''REQUESTED''::text, ''QUEUED''::text, ''RETRY_SCHEDULED''::text]))', ''),
        ('ops', 'job', 'ix_ops_job_lease', 'btree', FALSE, FALSE, 'lease_expires_at', 'CREATE INDEX ix_ops_job_lease ON ops.job USING btree (lease_expires_at) WHERE (status = ''RUNNING''::text)', NULL, '(status = ''RUNNING''::text)', ''),
        ('ops', 'job', 'ix_ops_job_aggregate', 'btree', FALSE, FALSE, 'aggregate_type,aggregate_id', 'CREATE INDEX ix_ops_job_aggregate ON ops.job USING btree (aggregate_type, aggregate_id)', NULL, NULL, ''),
        ('ops', 'job', 'ix_ops_job_correlation', 'btree', FALSE, FALSE, 'correlation_id', 'CREATE INDEX ix_ops_job_correlation ON ops.job USING btree (correlation_id)', NULL, NULL, ''),
        ('ops', 'job', 'ix_ops_job_payload_artifact_id', 'btree', FALSE, FALSE, 'payload_artifact_id', 'CREATE INDEX ix_ops_job_payload_artifact_id ON ops.job USING btree (payload_artifact_id)', NULL, NULL, 'Foreign key lookup and parent delete/update check.'),
        ('ops', 'job', 'ix_ops_job_parent_job_id', 'btree', FALSE, FALSE, 'parent_job_id', 'CREATE INDEX ix_ops_job_parent_job_id ON ops.job USING btree (parent_job_id)', NULL, NULL, 'Foreign key lookup and parent delete/update check.'),
        ('ops', 'job', 'ix_ops_job_site_id', 'btree', FALSE, FALSE, 'site_id', 'CREATE INDEX ix_ops_job_site_id ON ops.job USING btree (site_id)', NULL, NULL, 'Foreign key lookup and parent delete/update check.'),
        ('ops', 'job', 'ix_ops_job_deadline_active', 'btree', FALSE, FALSE, 'deadline_at', 'CREATE INDEX ix_ops_job_deadline_active ON ops.job USING btree (deadline_at) WHERE ((deadline_at IS NOT NULL) AND (status = ANY (ARRAY[''REQUESTED''::text, ''QUEUED''::text, ''RUNNING''::text, ''FAILED_RETRYABLE''::text, ''RETRY_SCHEDULED''::text])))', NULL, '((deadline_at IS NOT NULL) AND (status = ANY (ARRAY[''REQUESTED''::text, ''QUEUED''::text, ''RUNNING''::text, ''FAILED_RETRYABLE''::text, ''RETRY_SCHEDULED''::text])))', ''),
        ('ops', 'job_attempt', 'ix_ops_job_attempt_started', 'btree', FALSE, FALSE, 'started_at', 'CREATE INDEX ix_ops_job_attempt_started ON ops.job_attempt USING btree (started_at)', NULL, NULL, ''),
        ('ops', 'job_attempt', 'ix_ops_job_attempt_status', 'btree', FALSE, FALSE, 'status,started_at', 'CREATE INDEX ix_ops_job_attempt_status ON ops.job_attempt USING btree (status, started_at)', NULL, NULL, ''),
        ('ops', 'job_attempt', 'ix_ops_job_attempt_input_artifact_id', 'btree', FALSE, FALSE, 'input_artifact_id', 'CREATE INDEX ix_ops_job_attempt_input_artifact_id ON ops.job_attempt USING btree (input_artifact_id)', NULL, NULL, 'Foreign key lookup and parent delete/update check.'),
        ('ops', 'job_attempt', 'ix_ops_job_attempt_output_artifact_id', 'btree', FALSE, FALSE, 'output_artifact_id', 'CREATE INDEX ix_ops_job_attempt_output_artifact_id ON ops.job_attempt USING btree (output_artifact_id)', NULL, NULL, 'Foreign key lookup and parent delete/update check.'),
        ('ops', 'outbox_event', 'ix_ops_outbox_ready', 'btree', FALSE, FALSE, 'status,available_at', 'CREATE INDEX ix_ops_outbox_ready ON ops.outbox_event USING btree (status, available_at) WHERE (status = ANY (ARRAY[''PENDING''::text, ''FAILED''::text]))', NULL, '(status = ANY (ARRAY[''PENDING''::text, ''FAILED''::text]))', ''),
        ('ops', 'outbox_event', 'ix_ops_outbox_aggregate', 'btree', FALSE, FALSE, 'aggregate_type,aggregate_id,aggregate_version', 'CREATE INDEX ix_ops_outbox_aggregate ON ops.outbox_event USING btree (aggregate_type, aggregate_id, aggregate_version)', NULL, NULL, ''),
        ('ops', 'outbox_event', 'ix_ops_outbox_correlation', 'btree', FALSE, FALSE, 'correlation_id', 'CREATE INDEX ix_ops_outbox_correlation ON ops.outbox_event USING btree (correlation_id)', NULL, NULL, ''),
        ('ops', 'outbox_event', 'ix_ops_outbox_created_brin', 'brin', FALSE, FALSE, 'created_at', 'CREATE INDEX ix_ops_outbox_created_brin ON ops.outbox_event USING brin (created_at)', NULL, NULL, ''),
        ('ops', 'inbox_receipt', 'ix_ops_inbox_event', 'btree', FALSE, FALSE, 'event_id', 'CREATE INDEX ix_ops_inbox_event ON ops.inbox_receipt USING btree (event_id)', NULL, NULL, ''),
        ('ops', 'inbox_receipt', 'ix_ops_inbox_received', 'btree', FALSE, FALSE, 'received_at', 'CREATE INDEX ix_ops_inbox_received ON ops.inbox_receipt USING btree (received_at)', NULL, NULL, ''),
        ('ops', 'idempotency_record', 'ix_ops_idempotency_expiry', 'btree', FALSE, FALSE, 'expires_at', 'CREATE INDEX ix_ops_idempotency_expiry ON ops.idempotency_record USING btree (expires_at)', NULL, NULL, ''),
        ('ops', 'idempotency_record', 'ix_ops_idempotency_record_response_artifact_id', 'btree', FALSE, FALSE, 'response_artifact_id', 'CREATE INDEX ix_ops_idempotency_record_response_artifact_id ON ops.idempotency_record USING btree (response_artifact_id)', NULL, NULL, 'Foreign key lookup and parent delete/update check.'),
        ('ops', 'audit_event', 'ix_ops_audit_occurred', 'btree', FALSE, FALSE, 'occurred_at', 'CREATE INDEX ix_ops_audit_occurred ON ops.audit_event USING btree (occurred_at)', NULL, NULL, ''),
        ('ops', 'audit_event', 'ix_ops_audit_actor', 'btree', FALSE, FALSE, 'actor_type,actor_id,occurred_at', 'CREATE INDEX ix_ops_audit_actor ON ops.audit_event USING btree (actor_type, actor_id, occurred_at)', NULL, NULL, ''),
        ('ops', 'audit_event', 'ix_ops_audit_target', 'btree', FALSE, FALSE, 'target_type,target_id,occurred_at', 'CREATE INDEX ix_ops_audit_target ON ops.audit_event USING btree (target_type, target_id, occurred_at)', NULL, NULL, ''),
        ('ops', 'audit_event', 'ix_ops_audit_corr', 'btree', FALSE, FALSE, 'correlation_id', 'CREATE INDEX ix_ops_audit_corr ON ops.audit_event USING btree (correlation_id)', NULL, NULL, ''),
        ('ops', 'audit_event', 'ix_ops_audit_occurred_brin', 'brin', FALSE, FALSE, 'occurred_at', 'CREATE INDEX ix_ops_audit_occurred_brin ON ops.audit_event USING brin (occurred_at)', NULL, NULL, ''),
        ('ops', 'runtime_setting_version', 'uq_ops_setting_active', 'btree', TRUE, TRUE, 'setting_key,scope_type,scope_id', 'CREATE UNIQUE INDEX uq_ops_setting_active ON ops.runtime_setting_version USING btree (setting_key, scope_type, scope_id) NULLS NOT DISTINCT WHERE (status = ''ACTIVE''::text)', NULL, '(status = ''ACTIVE''::text)', ''),
        ('ops', 'runtime_setting_version', 'ix_ops_setting_lookup', 'btree', FALSE, FALSE, 'setting_key,status,effective_from', 'CREATE INDEX ix_ops_setting_lookup ON ops.runtime_setting_version USING btree (setting_key, status, effective_from)', NULL, NULL, ''),
        ('ops', 'runtime_setting_version', 'ix_ops_runtime_setting_version_created_by_principal_id', 'btree', FALSE, FALSE, 'created_by_principal_id', 'CREATE INDEX ix_ops_runtime_setting_version_created_by_principal_id ON ops.runtime_setting_version USING btree (created_by_principal_id)', NULL, NULL, 'Foreign key lookup and parent delete/update check.'),
        ('ops', 'runtime_setting_version', 'ix_ops_runtime_setting_version_approved_by_principal_id', 'btree', FALSE, FALSE, 'approved_by_principal_id', 'CREATE INDEX ix_ops_runtime_setting_version_approved_by_principal_id ON ops.runtime_setting_version USING btree (approved_by_principal_id)', NULL, NULL, 'Foreign key lookup and parent delete/update check.'),
        ('iam', 'principal', 'ix_iam_principal_status', 'btree', FALSE, FALSE, 'status,principal_type', 'CREATE INDEX ix_iam_principal_status ON iam.principal USING btree (status, principal_type)', NULL, NULL, ''),
        ('iam', 'user_account', 'ix_iam_user_email_lower', 'btree', FALSE, FALSE, '', 'CREATE INDEX ix_iam_user_email_lower ON iam.user_account USING btree (lower(email)) WHERE (email IS NOT NULL)', 'lower(email)', '(email IS NOT NULL)', ''),
        ('iam', 'role_permission', 'ix_iam_role_permission_permission_id', 'btree', FALSE, FALSE, 'permission_id', 'CREATE INDEX ix_iam_role_permission_permission_id ON iam.role_permission USING btree (permission_id)', NULL, NULL, 'Foreign key lookup and parent delete/update check.'),
        ('iam', 'principal_role_assignment', 'uq_iam_assignment_active', 'btree', TRUE, TRUE, 'principal_id,role_id,scope_type,scope_id', 'CREATE UNIQUE INDEX uq_iam_assignment_active ON iam.principal_role_assignment USING btree (principal_id, role_id, scope_type, scope_id) NULLS NOT DISTINCT WHERE (revoked_at IS NULL)', NULL, '(revoked_at IS NULL)', ''),
        ('iam', 'principal_role_assignment', 'ix_iam_assignment_lookup', 'btree', FALSE, FALSE, 'principal_id,scope_type,scope_id,valid_from', 'CREATE INDEX ix_iam_assignment_lookup ON iam.principal_role_assignment USING btree (principal_id, scope_type, scope_id, valid_from)', NULL, NULL, ''),
        ('iam', 'principal_role_assignment', 'ix_iam_principal_role_assignment_role_id', 'btree', FALSE, FALSE, 'role_id', 'CREATE INDEX ix_iam_principal_role_assignment_role_id ON iam.principal_role_assignment USING btree (role_id)', NULL, NULL, 'Foreign key lookup and parent delete/update check.'),
        ('iam', 'principal_role_assignment', 'ix_iam_principal_role_assignment_assigned_by_principal_id', 'btree', FALSE, FALSE, 'assigned_by_principal_id', 'CREATE INDEX ix_iam_principal_role_assignment_assigned_by_principal_id ON iam.principal_role_assignment USING btree (assigned_by_principal_id)', NULL, NULL, 'Foreign key lookup and parent delete/update check.'),
        ('iam', 'principal_role_assignment', 'ix_iam_principal_role_assignment_revoked_by_principal_id', 'btree', FALSE, FALSE, 'revoked_by_principal_id', 'CREATE INDEX ix_iam_principal_role_assignment_revoked_by_principal_id ON iam.principal_role_assignment USING btree (revoked_by_principal_id)', NULL, NULL, 'Foreign key lookup and parent delete/update check.'),
        ('iam', 'session_revocation', 'ix_iam_session_revocation_lookup', 'btree', FALSE, FALSE, 'oidc_issuer,oidc_subject,revoke_before', 'CREATE INDEX ix_iam_session_revocation_lookup ON iam.session_revocation USING btree (oidc_issuer, oidc_subject, revoke_before)', NULL, NULL, ''),
        ('iam', 'session_revocation', 'ix_iam_session_revocation_principal_id', 'btree', FALSE, FALSE, 'principal_id', 'CREATE INDEX ix_iam_session_revocation_principal_id ON iam.session_revocation USING btree (principal_id)', NULL, NULL, 'Foreign key lookup and parent delete/update check.'),
        ('iam', 'session_revocation', 'ix_iam_session_revocation_created_by_principal_id', 'btree', FALSE, FALSE, 'created_by_principal_id', 'CREATE INDEX ix_iam_session_revocation_created_by_principal_id ON iam.session_revocation USING btree (created_by_principal_id)', NULL, NULL, 'Foreign key lookup and parent delete/update check.'),
        ('iam', 'break_glass_record', 'ix_iam_break_glass_active', 'btree', FALSE, FALSE, 'expires_at', 'CREATE INDEX ix_iam_break_glass_active ON iam.break_glass_record USING btree (expires_at) WHERE (ended_at IS NULL)', NULL, '(ended_at IS NULL)', ''),
        ('iam', 'break_glass_record', 'ix_iam_break_glass_record_principal_id', 'btree', FALSE, FALSE, 'principal_id', 'CREATE INDEX ix_iam_break_glass_record_principal_id ON iam.break_glass_record USING btree (principal_id)', NULL, NULL, 'Foreign key lookup and parent delete/update check.'),
        ('iam', 'break_glass_record', 'ix_iam_break_glass_record_incident_id', 'btree', FALSE, FALSE, 'incident_id', 'CREATE INDEX ix_iam_break_glass_record_incident_id ON iam.break_glass_record USING btree (incident_id)', NULL, NULL, 'Foreign key lookup and parent delete/update check.'),
        ('iam', 'break_glass_record', 'ix_iam_break_glass_record_approved_by_principal_id', 'btree', FALSE, FALSE, 'approved_by_principal_id', 'CREATE INDEX ix_iam_break_glass_record_approved_by_principal_id ON iam.break_glass_record USING btree (approved_by_principal_id)', NULL, NULL, 'Foreign key lookup and parent delete/update check.')
    ) AS expected(
        schema_name, table_name, index_name, method_name, is_unique,
        nulls_not_distinct, key_columns, index_definition, index_expression,
        index_predicate, index_comment
    )
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    JOIN pg_catalog.pg_class AS table_relation
      ON table_relation.relnamespace = namespace.oid
     AND table_relation.relname = expected.table_name
    JOIN pg_catalog.pg_index AS index_record
      ON index_record.indrelid = table_relation.oid
    JOIN pg_catalog.pg_class AS index_relation
      ON index_relation.oid = index_record.indexrelid
     AND index_relation.relname = expected.index_name
    JOIN pg_catalog.pg_am AS access_method
      ON access_method.oid = index_relation.relam
     AND access_method.amname = expected.method_name
    WHERE NOT EXISTS (
              SELECT 1
              FROM pg_catalog.pg_constraint AS constraint_record
              WHERE constraint_record.conindid = index_record.indexrelid
          )
      AND index_record.indisprimary IS FALSE
      AND index_record.indisunique = expected.is_unique
      AND index_record.indnullsnotdistinct = expected.nulls_not_distinct
      AND index_record.indisvalid IS TRUE
      AND index_record.indisready IS TRUE
      AND index_record.indislive IS TRUE
      AND index_record.indnkeyatts = index_record.indnatts
      AND pg_catalog.pg_get_userbyid(index_relation.relowner) = current_user
      AND COALESCE((
          SELECT pg_catalog.string_agg(attribute.attname, ',' ORDER BY key_item.ordinality)
          FROM pg_catalog.unnest(index_record.indkey)
               WITH ORDINALITY AS key_item(attribute_number, ordinality)
          JOIN pg_catalog.pg_attribute AS attribute
            ON attribute.attrelid = index_record.indrelid
           AND attribute.attnum = key_item.attribute_number
          WHERE key_item.ordinality <= index_record.indnkeyatts
      ), '') = expected.key_columns
      AND pg_catalog.pg_get_indexdef(index_record.indexrelid, 0, false)
              = expected.index_definition
      AND pg_catalog.pg_get_expr(
              index_record.indexprs, index_record.indrelid, false
          ) IS NOT DISTINCT FROM expected.index_expression
      AND pg_catalog.pg_get_expr(
              index_record.indpred, index_record.indrelid, false
          ) IS NOT DISTINCT FROM expected.index_predicate
      AND pg_catalog.obj_description(index_relation.oid, 'pg_class')
              IS NOT DISTINCT FROM NULLIF(expected.index_comment, '');
    IF observed_count <> 48 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_index AS index_record
        JOIN pg_catalog.pg_class AS table_relation
          ON table_relation.oid = index_record.indrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = table_relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND NOT EXISTS (
              SELECT 1 FROM pg_catalog.pg_constraint AS constraint_record
              WHERE constraint_record.conindid = index_record.indexrelid
          )
    ) <> 48 THEN
        RAISE EXCEPTION 'ST0303_INDEX_CATALOG_MISMATCH';
    END IF;
    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_class AS index_relation
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = index_relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND index_relation.relkind = 'i'
          AND pg_catalog.pg_get_userbyid(index_relation.relowner) = current_user
    ) <> 78 THEN
        RAISE EXCEPTION 'ST0303_INDEX_OWNER_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        ('ops', 'touch_mutable_row', 'BEGIN
    IF NEW IS DISTINCT FROM OLD THEN
        NEW.updated_at := pg_catalog.statement_timestamp();
        NEW.lock_version := OLD.lock_version + 1;
    END IF;
    RETURN NEW;
END;', 'Mutable rows receive a statement timestamp and monotonic lock version only when row values change.'),
        ('ops', 'reject_immutable_mutation', 'BEGIN
    IF pg_catalog.current_setting(''raos.allow_immutable_maintenance'', true) = ''on''
       AND pg_catalog.pg_has_role(current_user, ''raos_migrator'', ''MEMBER'') THEN
        IF TG_OP = ''DELETE'' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;
    RAISE EXCEPTION USING
        ERRCODE = ''55000'',
        MESSAGE = ''RAOS immutable table mutation is forbidden'';
END;', 'Reject normal UPDATE and DELETE on hard-immutable tables; permit only an explicit migrator maintenance session.')
    ) AS expected(schema_name, function_name, function_source, function_comment)
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    JOIN pg_catalog.pg_proc AS routine
      ON routine.pronamespace = namespace.oid
     AND routine.proname = expected.function_name
     AND routine.pronargs = 0
    JOIN pg_catalog.pg_language AS language
      ON language.oid = routine.prolang
     AND language.lanname = 'plpgsql'
    WHERE routine.prorettype = 'pg_catalog.trigger'::pg_catalog.regtype
      AND routine.prokind = 'f'
      AND routine.prosecdef IS FALSE
      AND routine.provolatile = 'v'
      AND routine.proconfig = ARRAY['search_path=pg_catalog']::pg_catalog.text[]
      AND routine.prosrc = expected.function_source
      AND pg_catalog.pg_get_userbyid(routine.proowner) = current_user
      AND pg_catalog.obj_description(routine.oid, 'pg_proc') = expected.function_comment
      AND NOT EXISTS (
          SELECT 1
          FROM pg_catalog.aclexplode(
              COALESCE(
                  routine.proacl,
                  pg_catalog.acldefault('f', routine.proowner)
              )
          ) AS acl
          WHERE acl.grantee <> routine.proowner
      );
    IF observed_count <> 2 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_proc AS routine
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = routine.pronamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
    ) <> 2 THEN
        RAISE EXCEPTION 'ST0303_FUNCTION_CATALOG_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        ('ops', 'job', 'trg_ops_job_touch', 'ops.touch_mutable_row()', 19, 'CREATE TRIGGER trg_ops_job_touch BEFORE UPDATE ON ops.job FOR EACH ROW EXECUTE FUNCTION ops.touch_mutable_row()', 'Maintain ops.job updated_at and lock_version for changed rows.'),
        ('iam', 'principal', 'trg_iam_principal_touch', 'ops.touch_mutable_row()', 19, 'CREATE TRIGGER trg_iam_principal_touch BEFORE UPDATE ON iam.principal FOR EACH ROW EXECUTE FUNCTION ops.touch_mutable_row()', 'Maintain iam.principal updated_at and lock_version for changed rows.'),
        ('ops', 'object_artifact', 'trg_ops_object_artifact_immutable', 'ops.reject_immutable_mutation()', 27, 'CREATE TRIGGER trg_ops_object_artifact_immutable BEFORE DELETE OR UPDATE ON ops.object_artifact FOR EACH ROW EXECUTE FUNCTION ops.reject_immutable_mutation()', 'Reject normal mutation of the object artifact registry.'),
        ('ops', 'audit_event', 'trg_ops_audit_event_immutable', 'ops.reject_immutable_mutation()', 27, 'CREATE TRIGGER trg_ops_audit_event_immutable BEFORE DELETE OR UPDATE ON ops.audit_event FOR EACH ROW EXECUTE FUNCTION ops.reject_immutable_mutation()', 'Reject normal mutation of the audit event ledger.')
    ) AS expected(
        schema_name, table_name, trigger_name, function_signature,
        trigger_type, trigger_definition, trigger_comment
    )
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = namespace.oid
     AND relation.relname = expected.table_name
    JOIN pg_catalog.pg_trigger AS trigger_record
      ON trigger_record.tgrelid = relation.oid
     AND trigger_record.tgname = expected.trigger_name
    WHERE trigger_record.tgisinternal IS FALSE
      AND trigger_record.tgenabled = 'O'
      AND trigger_record.tgtype = expected.trigger_type
      AND trigger_record.tgfoid = pg_catalog.to_regprocedure(expected.function_signature)
      AND trigger_record.tgqual IS NULL
      AND trigger_record.tgnargs = 0
      AND trigger_record.tgattr::pg_catalog.text = ''
      AND pg_catalog.octet_length(trigger_record.tgargs) = 0
      AND trigger_record.tgconstraint = 0
      AND trigger_record.tgdeferrable IS FALSE
      AND trigger_record.tginitdeferred IS FALSE
      AND trigger_record.tgparentid = 0
      AND trigger_record.tgoldtable IS NULL
      AND trigger_record.tgnewtable IS NULL
      AND pg_catalog.pg_get_triggerdef(trigger_record.oid, false)
              = expected.trigger_definition
      AND pg_catalog.obj_description(trigger_record.oid, 'pg_trigger')
              = expected.trigger_comment;
    IF observed_count <> 4 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_trigger AS trigger_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = trigger_record.tgrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND trigger_record.tgisinternal IS FALSE
    ) <> 4 THEN
        RAISE EXCEPTION 'ST0303_TRIGGER_CATALOG_MISMATCH';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conname = ANY (ARRAY[
            'fk_ops_job_site_id',
            'fk_iam_break_glass_record_incident_id'
        ]::pg_catalog.text[])
    ) OR pg_catalog.to_regclass('ops.ix_ops_job_site_id') IS NULL
       OR pg_catalog.to_regclass('iam.ix_iam_break_glass_record_incident_id') IS NULL THEN
        RAISE EXCEPTION 'ST0303_DEFERRED_FOREIGN_KEY_BOUNDARY_MISMATCH';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_constraint AS constraint_record
        WHERE constraint_record.conrelid = 'ops.job'::pg_catalog.regclass
          AND constraint_record.contype = 'c'
    ) <> 11 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_index AS index_record
        WHERE index_record.indrelid = 'ops.job'::pg_catalog.regclass
          AND NOT EXISTS (
              SELECT 1 FROM pg_catalog.pg_constraint AS constraint_record
              WHERE constraint_record.conindid = index_record.indexrelid
          )
    ) <> 9 OR NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint AS constraint_record
        WHERE constraint_record.conrelid = 'ops.job'::pg_catalog.regclass
          AND constraint_record.conname = 'ck_ops_job_status'
          AND pg_catalog.pg_get_constraintdef(constraint_record.oid, false)
              LIKE ALL (ARRAY[
                  '%''REQUESTED''%', '%''QUEUED''%', '%''RUNNING''%',
                  '%''SUCCEEDED''%', '%''FAILED_RETRYABLE''%',
                  '%''RETRY_SCHEDULED''%', '%''FAILED_TERMINAL''%',
                  '%''QUARANTINED''%', '%''CANCELLED''%', '%''EXPIRED''%'
              ]::pg_catalog.text[])
          AND pg_catalog.pg_get_constraintdef(constraint_record.oid, false)
              NOT LIKE ALL (ARRAY['%''PENDING''%', '%''READY''%', '%''FAILED''%']::pg_catalog.text[])
    ) THEN
        RAISE EXCEPTION 'ST0303_JOB_CONTRACT_MISMATCH';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        JOIN pg_catalog.pg_index AS index_record
          ON index_record.indexrelid = constraint_record.conindid
        WHERE namespace.nspname = 'ops'
          AND relation.relname = 'runtime_setting_version'
          AND constraint_record.conname = 'uq_ops_setting_version'
          AND constraint_record.contype = 'u'
          AND index_record.indnullsnotdistinct IS FALSE
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint AS constraint_record
        WHERE constraint_record.conrelid = 'iam.break_glass_record'::pg_catalog.regclass
          AND constraint_record.contype = 'c'
          AND pg_catalog.pg_get_constraintdef(constraint_record.oid, false)
              LIKE '%principal_id%approved_by_principal_id%'
    ) THEN
        RAISE EXCEPTION 'ST0303_CANONICAL_LIMITATION_DRIFT';
    END IF;

    IF (SELECT pg_catalog.count(*) FROM public.raos_migration_version) <> 1
       OR NOT EXISTS (
           SELECT 1 FROM public.raos_migration_version
           WHERE version_num = '202608030003'
       ) THEN
        RAISE EXCEPTION 'ST0303_MIGRATION_VERSION_MISMATCH';
    END IF;
    IF (SELECT pg_catalog.count(*) FROM public.raos_migration_history) <> 5
       OR NOT EXISTS (
        SELECT 1
        FROM public.raos_migration_history AS anchor
        JOIN public.raos_migration_history AS foundation_started
          ON foundation_started.event_id > anchor.event_id
        JOIN public.raos_migration_history AS foundation_succeeded
          ON foundation_succeeded.event_id > foundation_started.event_id
        JOIN public.raos_migration_history AS iam_ops_started
          ON iam_ops_started.event_id > foundation_succeeded.event_id
        JOIN public.raos_migration_history AS iam_ops_succeeded
          ON iam_ops_succeeded.event_id > iam_ops_started.event_id
        JOIN public.raos_migration_version AS version
          ON version.version_num = '202608030003'
        WHERE anchor.revision_id = '202608030001'
          AND anchor.story_id = 'ST-0301'
          AND anchor.direction = 'UPGRADE'
          AND anchor.status = 'SUCCEEDED'
          AND anchor.source_sha256 = 'edc9accc402947ff9d1fa9b93d5028fb762b2cfc10deb54e555985acde09e2d3'
          AND anchor.runner_version = '1.0.0'
          AND foundation_started.revision_id = '202608030002'
          AND foundation_started.story_id = 'ST-0302'
          AND foundation_started.direction = 'UPGRADE'
          AND foundation_started.status = 'STARTED'
          AND foundation_started.source_sha256 = 'f91f6315779a045871d955cedb4b7a2606a562fbd8fdddae48810e54ef7dded4'
          AND foundation_started.runner_version = '1.1.0'
          AND foundation_succeeded.revision_id = '202608030002'
          AND foundation_succeeded.story_id = 'ST-0302'
          AND foundation_succeeded.direction = 'UPGRADE'
          AND foundation_succeeded.status = 'SUCCEEDED'
          AND foundation_succeeded.source_sha256 = 'f91f6315779a045871d955cedb4b7a2606a562fbd8fdddae48810e54ef7dded4'
          AND foundation_succeeded.runner_version = '1.1.0'
          AND iam_ops_started.revision_id = '202608030003'
          AND iam_ops_started.story_id = 'ST-0303'
          AND iam_ops_started.direction = 'UPGRADE'
          AND iam_ops_started.status = 'STARTED'
          AND iam_ops_started.source_sha256 = 'a9e162915e7450e30a6c96bafd1a65485447f6163b88ef5771dedc3df14c2f4e'
          AND iam_ops_started.runner_version = '1.2.0'
          AND iam_ops_succeeded.revision_id = '202608030003'
          AND iam_ops_succeeded.story_id = 'ST-0303'
          AND iam_ops_succeeded.direction = 'UPGRADE'
          AND iam_ops_succeeded.status = 'SUCCEEDED'
          AND iam_ops_succeeded.source_sha256 = 'a9e162915e7450e30a6c96bafd1a65485447f6163b88ef5771dedc3df14c2f4e'
          AND iam_ops_succeeded.runner_version = '1.2.0'
          AND anchor.server_version_num = 180004
          AND foundation_started.server_version_num = 180004
          AND foundation_succeeded.server_version_num = 180004
          AND iam_ops_started.server_version_num = 180004
          AND iam_ops_succeeded.server_version_num = 180004
          AND anchor.error_code IS NULL
          AND foundation_started.error_code IS NULL
          AND foundation_succeeded.error_code IS NULL
          AND iam_ops_started.error_code IS NULL
          AND iam_ops_succeeded.error_code IS NULL
          AND anchor.attempt_id <> foundation_started.attempt_id
          AND foundation_started.attempt_id = foundation_succeeded.attempt_id
          AND foundation_succeeded.attempt_id <> iam_ops_started.attempt_id
          AND iam_ops_started.attempt_id = iam_ops_succeeded.attempt_id
          AND foundation_started.transaction_id <> foundation_succeeded.transaction_id
          AND iam_ops_started.transaction_id <> iam_ops_succeeded.transaction_id
          AND iam_ops_succeeded.transaction_id = version.xmin::pg_catalog.text
          AND iam_ops_succeeded.xmin::pg_catalog.text = version.xmin::pg_catalog.text
    ) THEN
        RAISE EXCEPTION 'ST0303_MIGRATION_HISTORY_MISMATCH';
    END IF;
END
$raos_st0303_validation$;

SELECT
    'PASS'::pg_catalog.text AS status,
    17::pg_catalog.int4 AS table_count,
    219::pg_catalog.int4 AS column_count,
    20::pg_catalog.int4 AS immediate_foreign_key_count,
    2::pg_catalog.int4 AS deferred_foreign_key_count;
