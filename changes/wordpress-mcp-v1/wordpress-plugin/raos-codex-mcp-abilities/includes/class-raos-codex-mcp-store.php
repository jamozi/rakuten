<?php
/**
 * Immutable proposal and operation receipt storage.
 *
 * @package RAOS_Codex_MCP_Abilities
 */

defined('ABSPATH') || exit;

final class RAOS_Codex_MCP_Store
{
    const SCHEMA_VERSION = '3';
    const SCHEMA_OPTION = 'raos_codex_mcp_store_schema_v1';
    const TTL_SECONDS = 900;
    const RECOVERY_GRACE_SECONDS = 120;

    public static function table_name()
    {
        global $wpdb;
        return $wpdb->prefix . 'raos_codex_operations_v1';
    }

    public static function batch_table_name()
    {
        global $wpdb;
        return $wpdb->prefix . 'raos_codex_publication_batches_v1';
    }

    public static function install()
    {
        global $wpdb;
        require_once ABSPATH . 'wp-admin/includes/upgrade.php';
        $table = self::table_name();
        $batch_table = self::batch_table_name();
        $charset = $wpdb->get_charset_collate();
        $sql = "CREATE TABLE {$table} (
            proposal_id char(64) NOT NULL,
            operation_id char(64) NOT NULL,
            kind varchar(32) NOT NULL,
            state varchar(32) NOT NULL,
            result_code varchar(96) NOT NULL,
            created_by bigint(20) unsigned NOT NULL,
            approved_by bigint(20) unsigned NULL,
            created_at_gmt datetime NOT NULL,
            expires_at_gmt datetime NOT NULL,
            approved_at_gmt datetime NULL,
            applying_at_gmt datetime NULL,
            completed_at_gmt datetime NULL,
            before_sha256 char(64) NULL,
            after_sha256 char(64) NULL,
            audit_id char(64) NOT NULL,
            approval_reason text NULL,
            payload_json longtext NOT NULL,
            receipt_json longtext NULL,
            package_path text NULL,
            idempotency_key char(64) NULL,
            PRIMARY KEY  (proposal_id),
            UNIQUE KEY operation_id (operation_id),
            UNIQUE KEY creator_kind_idempotency (created_by, kind, idempotency_key),
            KEY state_expires (state, expires_at_gmt),
            KEY creator_kind (created_by, kind)
        ) {$charset};";
        dbDelta($sql);
        $batch_sql = "CREATE TABLE {$batch_table} (
            batch_token char(64) NOT NULL,
            state varchar(32) NOT NULL,
            created_by bigint(20) unsigned NOT NULL,
            approved_by bigint(20) unsigned NULL,
            created_at_gmt datetime NOT NULL,
            expires_at_gmt datetime NOT NULL,
            approved_at_gmt datetime NULL,
            batch_manifest_sha256 char(64) NOT NULL,
            proposal_ids_json longtext NOT NULL,
            manifest_json longtext NOT NULL,
            approval_reason text NULL,
            PRIMARY KEY  (batch_token),
            UNIQUE KEY creator_manifest (created_by, batch_manifest_sha256),
            KEY state_expires (state, expires_at_gmt)
        ) {$charset};";
        dbDelta($batch_sql);
        $columns = $wpdb->get_col('DESCRIBE ' . self::table_name(), 0);
        $idempotency_index = $wpdb->get_results(
            'SHOW INDEX FROM ' . self::table_name()
            . " WHERE Key_name = 'creator_kind_idempotency'",
            ARRAY_A
        );
        $unique_index_ready = is_array($idempotency_index)
            && 3 === count($idempotency_index);
        foreach (is_array($idempotency_index) ? $idempotency_index : array() as $index_entry) {
            if (! isset($index_entry['Non_unique']) || 0 !== (int) $index_entry['Non_unique']) {
                $unique_index_ready = false;
                break;
            }
        }
        $batch_columns = $wpdb->get_col('DESCRIBE ' . self::batch_table_name(), 0);
        $batch_unique_index = $wpdb->get_results(
            'SHOW INDEX FROM ' . self::batch_table_name()
            . " WHERE Key_name = 'creator_manifest'",
            ARRAY_A
        );
        $batch_unique_ready = is_array($batch_unique_index)
            && 2 === count($batch_unique_index);
        foreach (is_array($batch_unique_index) ? $batch_unique_index : array() as $index_entry) {
            if (! isset($index_entry['Non_unique']) || 0 !== (int) $index_entry['Non_unique']) {
                $batch_unique_ready = false;
                break;
            }
        }
        $batch_table_ready = is_array($batch_columns)
            && empty(
                array_diff(
                    array(
                        'batch_token',
                        'state',
                        'created_by',
                        'approved_by',
                        'created_at_gmt',
                        'expires_at_gmt',
                        'approved_at_gmt',
                        'batch_manifest_sha256',
                        'proposal_ids_json',
                        'manifest_json',
                        'approval_reason',
                    ),
                    $batch_columns
                )
            )
            && $batch_unique_ready;
        if (is_array($columns)
            && in_array('idempotency_key', $columns, true)
            && in_array('applying_at_gmt', $columns, true)
            && $unique_index_ready
            && $batch_table_ready) {
            update_option(self::SCHEMA_OPTION, self::SCHEMA_VERSION, false);
        }
    }

    /**
     * Run the additive dbDelta upgrade after a tracked ZIP overwrites an
     * already-active plugin. WordPress does not run activation hooks then.
     */
    public static function maybe_upgrade()
    {
        $installed = get_option(self::SCHEMA_OPTION, '0');
        if (! is_string($installed) || ! hash_equals(self::SCHEMA_VERSION, $installed)) {
            self::install();
        }
    }

    public static function canonicalize($value)
    {
        if (! is_array($value)) {
            return $value;
        }
        $keys = array_keys($value);
        $is_list = $keys === range(0, count($keys) - 1);
        if (! $is_list) {
            ksort($value, SORT_STRING);
        }
        foreach ($value as $key => $entry) {
            $value[$key] = self::canonicalize($entry);
        }
        return $value;
    }

    public static function canonical_json($value)
    {
        $encoded = wp_json_encode(
            self::canonicalize($value),
            JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE
        );
        if (! is_string($encoded)) {
            return false;
        }
        return $encoded;
    }

    public static function hash($value)
    {
        $encoded = self::canonical_json($value);
        return is_string($encoded) ? hash('sha256', $encoded) : false;
    }

    public static function is_sha256($value)
    {
        return is_string($value) && preg_match('/\A[0-9a-f]{64}\z/D', $value) === 1;
    }

    public static function now_mysql()
    {
        return gmdate('Y-m-d H:i:s');
    }

    public static function timestamp_mysql($unix_timestamp)
    {
        return gmdate('Y-m-d H:i:s', (int) $unix_timestamp);
    }

    public static function timestamp_iso($mysql_timestamp)
    {
        $timestamp = strtotime($mysql_timestamp . ' UTC');
        return false === $timestamp ? null : gmdate('Y-m-d\TH:i:s\Z', $timestamp);
    }

    public static function create(
        $kind,
        $payload,
        $before_sha256,
        $after_sha256,
        $automatic_apply_eligible = true,
        $package_path = null,
        $idempotency_key = null
    ) {
        global $wpdb;
        if (! in_array($kind, array('CONTENT_RELEASE', 'THEME_RELEASE', 'PLUGIN_CHANGE'), true)
            || ! is_array($payload)
            || (! is_null($before_sha256) && ! self::is_sha256($before_sha256))
            || (! is_null($after_sha256) && ! self::is_sha256($after_sha256))
            || ! is_bool($automatic_apply_eligible)
            || (! is_null($package_path) && (! is_string($package_path) || '' === $package_path))
            || (! is_null($idempotency_key) && ! self::is_sha256($idempotency_key))
            || (array_key_exists('idempotency_key', $payload)
                && (! is_string($payload['idempotency_key'])
                    || ! self::is_sha256($payload['idempotency_key'])
                    || is_null($idempotency_key)
                    || ! hash_equals($idempotency_key, $payload['idempotency_key'])))) {
            return new WP_Error('raos_codex_proposal_invalid', 'Proposal input is invalid.', array('status' => 400));
        }
        $created_by = get_current_user_id();
        if ($created_by < 1) {
            return new WP_Error('raos_codex_identity_invalid', 'Authenticated identity is required.', array('status' => 403));
        }
        if (! is_null($idempotency_key)) {
            $payload['idempotency_key'] = $idempotency_key;
        }
        $payload_sha256 = self::hash($payload);
        if (! self::is_sha256($payload_sha256)) {
            return new WP_Error('raos_codex_proposal_invalid', 'Proposal creation failed.', array('status' => 500));
        }
        if (! is_null($idempotency_key)) {
            $existing = self::get_by_idempotency($created_by, $kind, $idempotency_key);
            if (! is_wp_error($existing)) {
                return self::idempotent_existing_or_conflict($existing, $payload_sha256);
            }
            if ('raos_codex_proposal_not_found' !== $existing->get_error_code()) {
                return $existing;
            }
        }
        $created_unix = time();
        $created = self::timestamp_mysql($created_unix);
        $expires = self::timestamp_mysql($created_unix + self::TTL_SECONDS);
        try {
            $nonce = bin2hex(random_bytes(32));
        } catch (Throwable $error) {
            unset($error);
            return new WP_Error('raos_codex_random_unavailable', 'Proposal creation failed.', array('status' => 500));
        }
        $id_material = array(
            'schema' => 'RAOS_WORDPRESS_PROPOSAL_ID_V1',
            'kind' => $kind,
            'created_by' => $created_by,
            'created_at_gmt' => self::timestamp_iso($created),
            'expires_at_gmt' => self::timestamp_iso($expires),
            'before_sha256' => $before_sha256,
            'after_sha256' => $after_sha256,
            'payload_sha256' => $payload_sha256,
            'nonce_sha256' => hash('sha256', $nonce),
        );
        $proposal_id = self::hash($id_material);
        if (! self::is_sha256($proposal_id)) {
            return new WP_Error('raos_codex_proposal_invalid', 'Proposal creation failed.', array('status' => 500));
        }
        $operation_id = $proposal_id;
        $audit_id = self::hash(
            array(
                'schema' => 'RAOS_WORDPRESS_AUDIT_ID_V1',
                'proposal_id' => $proposal_id,
                'created_by' => $created_by,
                'created_at_gmt' => self::timestamp_iso($created),
            )
        );
        $payload['proposal_id'] = $proposal_id;
        $payload['created_by'] = $created_by;
        $payload['created_at_gmt'] = self::timestamp_iso($created);
        $payload['expires_at_gmt'] = self::timestamp_iso($expires);
        $payload_json = self::canonical_json($payload);
        if (! is_string($payload_json) || ! self::is_sha256($audit_id)) {
            return new WP_Error('raos_codex_proposal_invalid', 'Proposal creation failed.', array('status' => 500));
        }
        $state = $automatic_apply_eligible ? 'PENDING' : 'MANUAL_REQUIRED';
        $result_code = $automatic_apply_eligible
            ? 'PROPOSAL_PENDING_APPROVAL'
            : 'MANUAL_REVIEW_REQUIRED';
        $inserted = $wpdb->insert(
            self::table_name(),
            array(
                'proposal_id' => $proposal_id,
                'operation_id' => $operation_id,
                'kind' => $kind,
                'state' => $state,
                'result_code' => $result_code,
                'created_by' => $created_by,
                'created_at_gmt' => $created,
                'expires_at_gmt' => $expires,
                'before_sha256' => $before_sha256,
                'after_sha256' => $after_sha256,
                'audit_id' => $audit_id,
                'payload_json' => $payload_json,
                'package_path' => $package_path,
                'idempotency_key' => $idempotency_key,
            ),
            array('%s', '%s', '%s', '%s', '%s', '%d', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s')
        );
        if (1 !== $inserted) {
            if (! is_null($idempotency_key)) {
                $existing = self::get_by_idempotency($created_by, $kind, $idempotency_key);
                if (! is_wp_error($existing)) {
                    return self::idempotent_existing_or_conflict($existing, $payload_sha256);
                }
            }
            return new WP_Error('raos_codex_proposal_store_failed', 'Proposal storage failed.', array('status' => 500));
        }
        return self::get($proposal_id);
    }

    private static function get_by_idempotency($created_by, $kind, $idempotency_key)
    {
        global $wpdb;
        if ((int) $created_by < 1
            || ! in_array($kind, array('CONTENT_RELEASE', 'THEME_RELEASE', 'PLUGIN_CHANGE'), true)
            || ! self::is_sha256($idempotency_key)) {
            return new WP_Error('raos_codex_proposal_invalid', 'Proposal input is invalid.', array('status' => 400));
        }
        $proposal_id = $wpdb->get_var(
            $wpdb->prepare(
                'SELECT proposal_id FROM ' . self::table_name()
                . ' WHERE created_by = %d AND kind = %s AND idempotency_key = %s LIMIT 1',
                (int) $created_by,
                $kind,
                $idempotency_key
            )
        );
        if (! is_string($proposal_id) || ! self::is_sha256($proposal_id)) {
            return new WP_Error('raos_codex_proposal_not_found', 'Proposal was not found.', array('status' => 404));
        }
        return self::get($proposal_id);
    }

    private static function idempotent_existing_or_conflict($row, $payload_sha256)
    {
        if (! is_array($row) || ! isset($row['payload']) || ! is_array($row['payload'])) {
            return new WP_Error('raos_codex_store_corrupt', 'Stored operation is invalid.', array('status' => 500));
        }
        $stored_payload = $row['payload'];
        foreach (array('proposal_id', 'created_by', 'created_at_gmt', 'expires_at_gmt') as $metadata_key) {
            unset($stored_payload[$metadata_key]);
        }
        $stored_sha256 = self::hash($stored_payload);
        if (! self::is_sha256($stored_sha256)
            || ! self::is_sha256($payload_sha256)
            || ! hash_equals($stored_sha256, $payload_sha256)) {
            return new WP_Error(
                'raos_codex_idempotency_conflict',
                'The idempotency key is already bound to a different proposal payload.',
                array('status' => 409)
            );
        }
        return $row;
    }

    public static function get($proposal_id)
    {
        global $wpdb;
        if (! self::is_sha256($proposal_id)) {
            return new WP_Error('raos_codex_proposal_id_invalid', 'Proposal ID is invalid.', array('status' => 400));
        }
        $row = $wpdb->get_row(
            $wpdb->prepare(
                'SELECT * FROM ' . self::table_name() . ' WHERE proposal_id = %s LIMIT 1',
                $proposal_id
            ),
            ARRAY_A
        );
        if (! is_array($row)) {
            return new WP_Error('raos_codex_proposal_not_found', 'Proposal was not found.', array('status' => 404));
        }
        if (in_array($row['state'], array('PENDING', 'MANUAL_REQUIRED', 'APPROVED'), true)
            && strtotime($row['expires_at_gmt'] . ' UTC') <= time()) {
            $expired = $wpdb->query(
                $wpdb->prepare(
                    'UPDATE ' . self::table_name()
                    . " SET state = 'EXPIRED', result_code = 'PROPOSAL_EXPIRED'"
                    . " WHERE proposal_id = %s AND state IN ('PENDING','MANUAL_REQUIRED','APPROVED')",
                    $proposal_id
                )
            );
            $row['state'] = 'EXPIRED';
            $row['result_code'] = 'PROPOSAL_EXPIRED';
            if (1 === $expired && class_exists('RAOS_Codex_MCP_Deployment')) {
                RAOS_Codex_MCP_Deployment::remove_approval_lease($proposal_id);
            }
        }
        return self::hydrate_row($row);
    }

    private static function hydrate_row($row)
    {
        if (! is_array($row)
            || ! isset($row['payload_json'])
            || ! is_string($row['payload_json'])) {
            return new WP_Error('raos_codex_store_corrupt', 'Stored operation is invalid.', array('status' => 500));
        }
        $payload = json_decode($row['payload_json'], true);
        $receipt = isset($row['receipt_json']) && is_string($row['receipt_json'])
            ? json_decode($row['receipt_json'], true)
            : null;
        if (! is_array($payload) || (! is_null($receipt) && ! is_array($receipt))) {
            return new WP_Error('raos_codex_store_corrupt', 'Stored operation is invalid.', array('status' => 500));
        }
        $row['payload'] = $payload;
        $row['receipt'] = $receipt;
        return $row;
    }

    /**
     * Verify the immutable hashes copied into the row and payload still agree.
     */
    public static function validate_proposal_integrity($row)
    {
        if (! is_array($row)
            || ! isset(
                $row['proposal_id'],
                $row['kind'],
                $row['created_by'],
                $row['created_at_gmt'],
                $row['expires_at_gmt'],
                $row['payload']
            )
            || ! array_key_exists('before_sha256', $row)
            || ! array_key_exists('after_sha256', $row)
            || ! self::is_sha256($row['proposal_id'])
            || ! is_string($row['kind'])
            || ! is_string($row['created_at_gmt'])
            || ! is_string($row['expires_at_gmt'])
            || ! is_array($row['payload'])
            || ! self::nullable_hash_is_valid($row['before_sha256'])
            || ! self::nullable_hash_is_valid($row['after_sha256'])) {
            return new WP_Error('raos_codex_proposal_hash_drift', 'Proposal hash integrity failed.', array('status' => 409));
        }
        $payload = $row['payload'];
        $created_iso = self::timestamp_iso($row['created_at_gmt']);
        $expires_iso = self::timestamp_iso($row['expires_at_gmt']);
        $stored_idempotency = isset($row['idempotency_key']) && is_string($row['idempotency_key'])
            ? $row['idempotency_key']
            : null;
        $payload_idempotency = isset($payload['idempotency_key']) && is_string($payload['idempotency_key'])
            ? $payload['idempotency_key']
            : null;
        if (! isset(
            $payload['proposal_id'],
            $payload['created_by'],
            $payload['created_at_gmt'],
            $payload['expires_at_gmt'],
            $payload['schema']
        )
            || ! is_string($created_iso)
            || ! is_string($expires_iso)
            || ! is_string($payload['proposal_id'])
            || ! is_string($payload['created_at_gmt'])
            || ! is_string($payload['expires_at_gmt'])
            || ! hash_equals($row['proposal_id'], (string) $payload['proposal_id'])
            || (int) $row['created_by'] !== (int) $payload['created_by']
            || ! hash_equals($created_iso, (string) $payload['created_at_gmt'])
            || ! hash_equals($expires_iso, (string) $payload['expires_at_gmt'])
            || ! self::nullable_hash_matches($stored_idempotency, $payload_idempotency)) {
            return new WP_Error('raos_codex_proposal_hash_drift', 'Proposal hash integrity failed.', array('status' => 409));
        }
        if ('CONTENT_RELEASE' === $row['kind']) {
            $valid = self::content_payload_integrity($row, $payload);
        } else {
            $valid = self::code_payload_integrity($row, $payload);
        }
        return $valid
            ? true
            : new WP_Error('raos_codex_proposal_hash_drift', 'Proposal hash integrity failed.', array('status' => 409));
    }

    private static function content_payload_integrity($row, $payload)
    {
        if ('ContentReleaseProposalV1' !== $payload['schema']
            || ! isset(
                $payload['before'],
                $payload['after'],
                $payload['before_sha256'],
                $payload['after_sha256'],
                $payload['publication_manifest_sha256']
            )
            || ! is_array($payload['before'])
            || ! is_array($payload['after'])
            || ! self::is_sha256($payload['before_sha256'])
            || ! self::is_sha256($payload['after_sha256'])
            || ! self::is_sha256($payload['publication_manifest_sha256'])) {
            return false;
        }
        $before_hash = class_exists('RAOS_Codex_MCP_Content')
            ? RAOS_Codex_MCP_Content::document_hash($payload['before'])
            : false;
        $after_hash = class_exists('RAOS_Codex_MCP_Content')
            ? RAOS_Codex_MCP_Content::document_hash($payload['after'])
            : false;
        if (! self::is_sha256($before_hash)
            || ! self::is_sha256($after_hash)
            || ! isset(
                $payload['before']['revision_id'],
                $payload['before']['modified_gmt'],
                $payload['before']['post_type'],
                $payload['before']['id']
            )) {
            return false;
        }
        $manifest_hash = self::hash(
            array(
                'schema' => 'ContentPublicationManifestV1',
                'target_status' => 'publish',
                'post_type' => $payload['before']['post_type'],
                'post_id' => $payload['before']['id'],
                'before_sha256' => $before_hash,
                'after_sha256' => $after_hash,
                'precondition' => array(
                    'revision_id' => $payload['before']['revision_id'],
                    'modified_gmt' => $payload['before']['modified_gmt'],
                    'content_sha256' => $before_hash,
                ),
            )
        );
        return self::is_sha256($manifest_hash)
            && hash_equals($before_hash, (string) $payload['before_sha256'])
            && hash_equals($after_hash, (string) $payload['after_sha256'])
            && self::nullable_hash_matches($row['before_sha256'], $before_hash)
            && self::nullable_hash_matches($row['after_sha256'], $after_hash)
            && hash_equals($manifest_hash, (string) $payload['publication_manifest_sha256']);
    }

    private static function code_payload_integrity($row, $payload)
    {
        return 'CodeReleaseProposalV1' === $payload['schema']
            && isset($payload['kind'], $payload['code_package'])
            && array_key_exists('before_tree_sha256', $payload)
            && array_key_exists('after_tree_sha256', $payload)
            && is_array($payload['code_package'])
            && isset($payload['code_package']['file_manifest_sha256'])
            && hash_equals($row['kind'], (string) $payload['kind'])
            && self::nullable_hash_matches($row['before_sha256'], $payload['before_tree_sha256'])
            && self::nullable_hash_matches($row['after_sha256'], $payload['after_tree_sha256'])
            && self::nullable_hash_matches(
                $row['after_sha256'],
                $payload['code_package']['file_manifest_sha256']
            );
    }

    private static function nullable_hash_is_valid($value)
    {
        return is_null($value) || self::is_sha256($value);
    }

    private static function nullable_hash_matches($expected, $actual)
    {
        if (is_null($expected) || is_null($actual)) {
            return is_null($expected) && is_null($actual);
        }
        return self::is_sha256($expected)
            && self::is_sha256($actual)
            && hash_equals($expected, $actual);
    }

    private static function build_publication_batch_snapshot($rows)
    {
        if (! is_array($rows) || empty($rows) || count($rows) > 20) {
            return new WP_Error('raos_codex_approval_batch_invalid', 'Approval batch is invalid.', array('status' => 409));
        }
        usort(
            $rows,
            static function ($left, $right) {
                return strcmp($left['proposal_id'], $right['proposal_id']);
            }
        );
        $entries = array();
        $content_count = 0;
        $theme_count = 0;
        foreach ($rows as $row) {
            if (! is_array($row)
                || ! isset(
                    $row['state'],
                    $row['proposal_id'],
                    $row['kind'],
                    $row['created_by'],
                    $row['created_at_gmt'],
                    $row['expires_at_gmt']
                )
                || ! array_key_exists('before_sha256', $row)
                || ! array_key_exists('after_sha256', $row)
                || 'PENDING' !== $row['state']
                || ! in_array($row['kind'], array('CONTENT_RELEASE', 'THEME_RELEASE'), true)
                || ! self::is_sha256($row['proposal_id'])
                || ! self::nullable_hash_is_valid($row['before_sha256'])
                || ! self::nullable_hash_is_valid($row['after_sha256'])) {
                return new WP_Error('raos_codex_approval_batch_invalid', 'Approval batch is invalid.', array('status' => 409));
            }
            if ('CONTENT_RELEASE' === $row['kind']) {
                ++$content_count;
            } else {
                ++$theme_count;
            }
            $created_iso = self::timestamp_iso($row['created_at_gmt']);
            $expires_iso = self::timestamp_iso($row['expires_at_gmt']);
            if (! is_string($created_iso) || ! is_string($expires_iso)) {
                return new WP_Error('raos_codex_approval_batch_invalid', 'Approval batch is invalid.', array('status' => 409));
            }
            $entries[] = array(
                'proposal_id' => $row['proposal_id'],
                'kind' => $row['kind'],
                'created_by' => (int) $row['created_by'],
                'created_at_gmt' => $created_iso,
                'expires_at_gmt' => $expires_iso,
                'before_sha256' => $row['before_sha256'],
                'after_sha256' => $row['after_sha256'],
            );
        }
        if ($content_count < 1 || $theme_count > 1) {
            return new WP_Error('raos_codex_approval_batch_invalid', 'Approval batch is invalid.', array('status' => 409));
        }
        $manifest = array(
            'schema' => 'RAOSWordPressPublicationBatchManifestV1',
            'proposal_count' => count($entries),
            'proposals' => $entries,
        );
        $batch_sha256 = self::hash($manifest);
        if (! self::is_sha256($batch_sha256)) {
            return new WP_Error('raos_codex_approval_batch_invalid', 'Approval batch is invalid.', array('status' => 409));
        }
        return array(
            'manifest' => $manifest,
            'batch_manifest_sha256' => $batch_sha256,
            'rows' => $rows,
        );
    }

    public static function register_publication_batch($proposal_ids)
    {
        global $wpdb;
        if (! is_array($proposal_ids)
            || empty($proposal_ids)
            || count($proposal_ids) > 20
            || count(array_unique($proposal_ids)) !== count($proposal_ids)) {
            return new WP_Error('raos_codex_publication_batch_input_invalid', 'Publication batch input is invalid.', array('status' => 400));
        }
        foreach ($proposal_ids as $proposal_id) {
            if (! self::is_sha256($proposal_id)) {
                return new WP_Error('raos_codex_publication_batch_input_invalid', 'Publication batch input is invalid.', array('status' => 400));
            }
        }
        sort($proposal_ids, SORT_STRING);
        $created_by = get_current_user_id();
        if ($created_by < 1) {
            return new WP_Error('raos_codex_identity_invalid', 'Authenticated identity is required.', array('status' => 403));
        }
        $canonical_proposal_ids = self::canonical_json($proposal_ids);
        if (! is_string($canonical_proposal_ids)) {
            return new WP_Error('raos_codex_publication_batch_input_invalid', 'Publication batch input is invalid.', array('status' => 400));
        }
        $existing_token = $wpdb->get_var(
            $wpdb->prepare(
                'SELECT batch_token FROM ' . self::batch_table_name()
                . ' WHERE created_by = %d AND proposal_ids_json = %s LIMIT 1',
                $created_by,
                $canonical_proposal_ids
            )
        );
        if (is_string($existing_token) && self::is_sha256($existing_token)) {
            $existing = self::get_publication_batch($existing_token);
            if (is_wp_error($existing) || 'EXPIRED' !== $existing['state']) {
                return $existing;
            }
            return new WP_Error('raos_codex_publication_batch_expired', 'Publication batch has expired.', array('status' => 409));
        }
        $rows = array();
        foreach ($proposal_ids as $proposal_id) {
            $row = self::get($proposal_id);
            if (is_wp_error($row)
                || 'PENDING' !== $row['state']
                || ! in_array($row['kind'], array('CONTENT_RELEASE', 'THEME_RELEASE'), true)) {
                return new WP_Error('raos_codex_publication_batch_proposal_invalid', 'Publication batch proposal is invalid.', array('status' => 409));
            }
            if (('CONTENT_RELEASE' === $row['kind'] && (int) $row['created_by'] !== $created_by)
                || ('THEME_RELEASE' === $row['kind'] && (int) $row['created_by'] === $created_by)) {
                return new WP_Error('raos_codex_publication_batch_owner_invalid', 'Publication batch ownership is invalid.', array('status' => 403));
            }
            $integrity = self::validate_proposal_integrity($row);
            if (is_wp_error($integrity)) {
                return $integrity;
            }
            $rows[] = $row;
        }
        $snapshot = self::build_publication_batch_snapshot($rows);
        if (is_wp_error($snapshot)) {
            return $snapshot;
        }
        $existing_token = $wpdb->get_var(
            $wpdb->prepare(
                'SELECT batch_token FROM ' . self::batch_table_name()
                . ' WHERE created_by = %d AND batch_manifest_sha256 = %s LIMIT 1',
                $created_by,
                $snapshot['batch_manifest_sha256']
            )
        );
        if (is_string($existing_token) && self::is_sha256($existing_token)) {
            $existing = self::get_publication_batch($existing_token);
            if (is_wp_error($existing) || 'EXPIRED' !== $existing['state']) {
                return $existing;
            }
            return new WP_Error('raos_codex_publication_batch_expired', 'Publication batch has expired.', array('status' => 409));
        }
        $created_unix = time();
        $created = self::timestamp_mysql($created_unix);
        $expires_unix = null;
        foreach ($rows as $row) {
            $row_expires = strtotime($row['expires_at_gmt'] . ' UTC');
            if (false === $row_expires) {
                return new WP_Error('raos_codex_publication_batch_proposal_invalid', 'Publication batch proposal is invalid.', array('status' => 409));
            }
            $expires_unix = is_null($expires_unix) ? $row_expires : min($expires_unix, $row_expires);
        }
        try {
            $nonce_sha256 = hash('sha256', random_bytes(32));
        } catch (Throwable $error) {
            unset($error);
            return new WP_Error('raos_codex_random_unavailable', 'Publication batch registration failed.', array('status' => 500));
        }
        $batch_token = self::hash(
            array(
                'schema' => 'RAOS_WORDPRESS_PUBLICATION_BATCH_TOKEN_V1',
                'created_by' => $created_by,
                'created_at_gmt' => self::timestamp_iso($created),
                'batch_manifest_sha256' => $snapshot['batch_manifest_sha256'],
                'nonce_sha256' => $nonce_sha256,
            )
        );
        $proposal_ids_json = $canonical_proposal_ids;
        $manifest_json = self::canonical_json($snapshot['manifest']);
        if (! self::is_sha256($batch_token)
            || ! is_string($proposal_ids_json)
            || ! is_string($manifest_json)
            || ! is_int($expires_unix)
            || $expires_unix <= $created_unix) {
            return new WP_Error('raos_codex_publication_batch_invalid', 'Publication batch registration failed.', array('status' => 500));
        }
        $inserted = $wpdb->insert(
            self::batch_table_name(),
            array(
                'batch_token' => $batch_token,
                'state' => 'REGISTERED',
                'created_by' => $created_by,
                'created_at_gmt' => $created,
                'expires_at_gmt' => self::timestamp_mysql($expires_unix),
                'batch_manifest_sha256' => $snapshot['batch_manifest_sha256'],
                'proposal_ids_json' => $proposal_ids_json,
                'manifest_json' => $manifest_json,
            ),
            array('%s', '%s', '%d', '%s', '%s', '%s', '%s', '%s')
        );
        if (1 !== $inserted) {
            $existing_token = $wpdb->get_var(
                $wpdb->prepare(
                    'SELECT batch_token FROM ' . self::batch_table_name()
                    . ' WHERE created_by = %d AND batch_manifest_sha256 = %s LIMIT 1',
                    $created_by,
                    $snapshot['batch_manifest_sha256']
                )
            );
            if (is_string($existing_token) && self::is_sha256($existing_token)) {
                $existing = self::get_publication_batch($existing_token);
                if (is_wp_error($existing) || 'EXPIRED' !== $existing['state']) {
                    return $existing;
                }
                return new WP_Error('raos_codex_publication_batch_expired', 'Publication batch has expired.', array('status' => 409));
            }
            return new WP_Error('raos_codex_publication_batch_store_failed', 'Publication batch storage failed.', array('status' => 500));
        }
        return self::get_publication_batch($batch_token);
    }

    public static function get_publication_batch($batch_token)
    {
        global $wpdb;
        if (! self::is_sha256($batch_token)) {
            return new WP_Error('raos_codex_publication_batch_token_invalid', 'Publication batch token is invalid.', array('status' => 400));
        }
        $row = $wpdb->get_row(
            $wpdb->prepare(
                'SELECT * FROM ' . self::batch_table_name() . ' WHERE batch_token = %s LIMIT 1',
                $batch_token
            ),
            ARRAY_A
        );
        if (! is_array($row)) {
            return new WP_Error('raos_codex_publication_batch_not_found', 'Publication batch was not found.', array('status' => 404));
        }
        if ('REGISTERED' === $row['state']
            && strtotime($row['expires_at_gmt'] . ' UTC') <= time()) {
            $wpdb->query(
                $wpdb->prepare(
                    'UPDATE ' . self::batch_table_name()
                    . " SET state = 'EXPIRED' WHERE batch_token = %s AND state = 'REGISTERED'",
                    $batch_token
                )
            );
            $row['state'] = 'EXPIRED';
        }
        return self::hydrate_publication_batch($row);
    }

    private static function hydrate_publication_batch($row)
    {
        if (! is_array($row)
            || ! isset(
                $row['batch_token'],
                $row['state'],
                $row['created_by'],
                $row['created_at_gmt'],
                $row['expires_at_gmt'],
                $row['batch_manifest_sha256'],
                $row['proposal_ids_json'],
                $row['manifest_json']
            )
            || ! self::is_sha256($row['batch_token'])
            || ! self::is_sha256($row['batch_manifest_sha256'])
            || ! in_array($row['state'], array('REGISTERED', 'APPROVED', 'EXPIRED'), true)) {
            return new WP_Error('raos_codex_publication_batch_corrupt', 'Stored publication batch is invalid.', array('status' => 500));
        }
        $proposal_ids = json_decode($row['proposal_ids_json'], true);
        $manifest = json_decode($row['manifest_json'], true);
        if (! is_array($proposal_ids)
            || ! is_array($manifest)
            || empty($proposal_ids)
            || count($proposal_ids) > 20
            || count(array_unique($proposal_ids)) !== count($proposal_ids)
            || $proposal_ids !== array_values($proposal_ids)
            || ! isset($manifest['schema'], $manifest['proposal_count'], $manifest['proposals'])
            || 'RAOSWordPressPublicationBatchManifestV1' !== $manifest['schema']
            || (int) $manifest['proposal_count'] !== count($proposal_ids)
            || ! is_array($manifest['proposals'])
            || ! hash_equals($row['batch_manifest_sha256'], (string) self::hash($manifest))) {
            return new WP_Error('raos_codex_publication_batch_corrupt', 'Stored publication batch is invalid.', array('status' => 500));
        }
        $manifest_ids = array();
        foreach ($manifest['proposals'] as $entry) {
            if (! is_array($entry)
                || ! isset($entry['proposal_id'], $entry['kind'])
                || ! self::is_sha256($entry['proposal_id'])
                || ! in_array($entry['kind'], array('CONTENT_RELEASE', 'THEME_RELEASE'), true)) {
                return new WP_Error('raos_codex_publication_batch_corrupt', 'Stored publication batch is invalid.', array('status' => 500));
            }
            $manifest_ids[] = $entry['proposal_id'];
        }
        sort($manifest_ids, SORT_STRING);
        if ($proposal_ids !== $manifest_ids) {
            return new WP_Error('raos_codex_publication_batch_corrupt', 'Stored publication batch is invalid.', array('status' => 500));
        }
        $row['proposal_ids'] = $proposal_ids;
        $row['manifest'] = $manifest;
        return $row;
    }

    public static function pending_publication_batches_for_admin($limit = 20)
    {
        global $wpdb;
        $limit = max(1, min(20, (int) $limit));
        $tokens = $wpdb->get_col(
            $wpdb->prepare(
                'SELECT batch_token FROM ' . self::batch_table_name()
                . " WHERE state = 'REGISTERED' ORDER BY created_at_gmt DESC LIMIT %d",
                $limit
            )
        );
        $batches = array();
        foreach (is_array($tokens) ? $tokens : array() as $batch_token) {
            $batch = self::get_publication_batch($batch_token);
            if (! is_wp_error($batch) && 'REGISTERED' === $batch['state']) {
                $batches[] = $batch;
            }
        }
        return $batches;
    }

    public static function public_publication_batch($row)
    {
        if (! is_array($row)) {
            return null;
        }
        return array(
            'schema' => 'RAOSWordPressPublicationBatchV1',
            'batch_token' => $row['batch_token'],
            'batch_manifest_sha256' => $row['batch_manifest_sha256'],
            'proposal_count' => count($row['proposal_ids']),
            'proposal_ids' => $row['proposal_ids'],
            'expires_at_gmt' => self::timestamp_iso($row['expires_at_gmt']),
            'review_url' => admin_url('tools.php?page=raos-codex-proposals'),
        );
    }

    public static function approve($proposal_id, $approver_id, $reason)
    {
        global $wpdb;
        $row = self::get($proposal_id);
        if (is_wp_error($row)) {
            return $row;
        }
        if ('PENDING' !== $row['state']) {
            return new WP_Error('raos_codex_proposal_not_pending', 'Proposal is not pending.', array('status' => 409));
        }
        $integrity = self::validate_proposal_integrity($row);
        if (is_wp_error($integrity)) {
            return $integrity;
        }
        if ((int) $row['created_by'] === (int) $approver_id || (int) $approver_id < 1) {
            return new WP_Error('raos_codex_self_approval_forbidden', 'A different administrator must approve.', array('status' => 403));
        }
        if (! is_string($reason) || strlen(trim($reason)) < 10 || strlen($reason) > 2000) {
            return new WP_Error('raos_codex_approval_reason_invalid', 'Approval reason is invalid.', array('status' => 400));
        }
        $approved_at = self::now_mysql();
        $lease = RAOS_Codex_MCP_Deployment::create_approval_lease(
            $row,
            (int) $approver_id,
            $approved_at
        );
        if (is_wp_error($lease)) {
            return $lease;
        }
        $updated = $wpdb->query(
            $wpdb->prepare(
                'UPDATE ' . self::table_name()
                . " SET state = 'APPROVED', result_code = 'PROPOSAL_APPROVED',"
                . ' approved_by = %d, approved_at_gmt = %s, approval_reason = %s'
                . " WHERE proposal_id = %s AND state = 'PENDING' AND expires_at_gmt > %s",
                (int) $approver_id,
                $approved_at,
                trim($reason),
                $proposal_id,
                self::now_mysql()
            )
        );
        if (1 !== $updated) {
            RAOS_Codex_MCP_Deployment::remove_approval_lease($proposal_id);
            return new WP_Error('raos_codex_approval_conflict', 'Proposal approval conflicted or expired.', array('status' => 409));
        }
        return self::get($proposal_id);
    }

    /**
     * Approve one server-registered, exact content/theme publication batch.
     */
    public static function approve_publication_batch(
        $batch_token,
        $expected_batch_sha256,
        $approver_id,
        $reason
    )
    {
        global $wpdb;
        if (! self::is_sha256($batch_token)
            || ! self::is_sha256($expected_batch_sha256)
            || (int) $approver_id < 1
            || ! is_string($reason)
            || strlen(trim($reason)) < 10
            || strlen($reason) > 2000) {
            return new WP_Error('raos_codex_approval_batch_invalid', 'Approval batch is invalid.', array('status' => 400));
        }
        if (false === $wpdb->query('START TRANSACTION')) {
            return new WP_Error('raos_codex_approval_batch_transaction_failed', 'Approval batch transaction failed.', array('status' => 500));
        }
        $lease_ids = array();
        try {
            $raw_batch = $wpdb->get_row(
                $wpdb->prepare(
                    'SELECT * FROM ' . self::batch_table_name()
                    . ' WHERE batch_token = %s FOR UPDATE',
                    $batch_token
                ),
                ARRAY_A
            );
            $batch = self::hydrate_publication_batch($raw_batch);
            if (is_wp_error($batch)
                || 'REGISTERED' !== $batch['state']
                || strtotime($batch['expires_at_gmt'] . ' UTC') <= time()
                || ! hash_equals($expected_batch_sha256, $batch['batch_manifest_sha256'])) {
                throw new RuntimeException('raos_codex_approval_batch_hash_drift');
            }
            $rows = array();
            foreach ($batch['proposal_ids'] as $proposal_id) {
                $raw_row = $wpdb->get_row(
                    $wpdb->prepare(
                        'SELECT * FROM ' . self::table_name()
                        . ' WHERE proposal_id = %s FOR UPDATE',
                        $proposal_id
                    ),
                    ARRAY_A
                );
                $row = self::hydrate_row($raw_row);
                if (is_wp_error($row)
                    || 'PENDING' !== $row['state']
                    || ! in_array($row['kind'], array('CONTENT_RELEASE', 'THEME_RELEASE'), true)
                    || strtotime($row['expires_at_gmt'] . ' UTC') <= time()) {
                    throw new RuntimeException('raos_codex_approval_batch_stale');
                }
                $integrity = self::validate_proposal_integrity($row);
                if (is_wp_error($integrity)) {
                    throw new RuntimeException($integrity->get_error_code());
                }
                if ((int) $row['created_by'] === (int) $approver_id) {
                    throw new RuntimeException('raos_codex_self_approval_forbidden');
                }
                $rows[] = $row;
            }
            $snapshot = self::build_publication_batch_snapshot($rows);
            if (is_wp_error($snapshot)
                || ! hash_equals($expected_batch_sha256, $snapshot['batch_manifest_sha256'])
                || ! hash_equals(
                    (string) self::canonical_json($batch['manifest']),
                    (string) self::canonical_json($snapshot['manifest'])
                )) {
                throw new RuntimeException('raos_codex_approval_batch_hash_drift');
            }
            $approved_at = self::now_mysql();
            foreach ($rows as $row) {
                $lease = RAOS_Codex_MCP_Deployment::create_approval_lease(
                    $row,
                    (int) $approver_id,
                    $approved_at
                );
                if (is_wp_error($lease)) {
                    throw new RuntimeException($lease->get_error_code());
                }
                $lease_ids[] = $row['proposal_id'];
            }
            foreach ($rows as $row) {
                $updated = $wpdb->query(
                    $wpdb->prepare(
                        'UPDATE ' . self::table_name()
                        . " SET state = 'APPROVED', result_code = 'PROPOSAL_APPROVED',"
                        . ' approved_by = %d, approved_at_gmt = %s, approval_reason = %s'
                        . " WHERE proposal_id = %s AND state = 'PENDING'"
                        . ' AND created_by = %d AND expires_at_gmt > %s',
                        (int) $approver_id,
                        $approved_at,
                        trim($reason),
                        $row['proposal_id'],
                        (int) $row['created_by'],
                        self::now_mysql()
                    )
                );
                if (1 !== $updated) {
                    throw new RuntimeException('raos_codex_approval_conflict');
                }
            }
            $batch_updated = $wpdb->query(
                $wpdb->prepare(
                    'UPDATE ' . self::batch_table_name()
                    . " SET state = 'APPROVED', approved_by = %d, approved_at_gmt = %s, approval_reason = %s"
                    . " WHERE batch_token = %s AND state = 'REGISTERED'"
                    . ' AND batch_manifest_sha256 = %s AND expires_at_gmt > %s',
                    (int) $approver_id,
                    $approved_at,
                    trim($reason),
                    $batch_token,
                    $expected_batch_sha256,
                    self::now_mysql()
                )
            );
            if (1 !== $batch_updated) {
                throw new RuntimeException('raos_codex_approval_batch_conflict');
            }
            if (false === $wpdb->query('COMMIT')) {
                throw new RuntimeException('raos_codex_approval_batch_commit_failed');
            }
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            foreach ($lease_ids as $proposal_id) {
                RAOS_Codex_MCP_Deployment::remove_approval_lease($proposal_id);
            }
            $code = $error->getMessage();
            if (! preg_match('/\Araos_codex_[a-z0-9_]{3,96}\z/D', $code)) {
                $code = 'raos_codex_approval_batch_failed';
            }
            $status = 'raos_codex_self_approval_forbidden' === $code ? 403 : 409;
            return new WP_Error($code, 'Approval batch failed closed.', array('status' => $status));
        }
        $approved_rows = array();
        foreach ($lease_ids as $proposal_id) {
            $row = self::get($proposal_id);
            if (is_wp_error($row)) {
                return $row;
            }
            $approved_rows[] = $row;
        }
        return array(
            'schema' => 'RAOSWordPressPublicationBatchApprovalResultV1',
            'batch_token' => $batch_token,
            'batch_manifest_sha256' => $expected_batch_sha256,
            'proposal_count' => count($approved_rows),
            'proposals' => $approved_rows,
        );
    }

    public static function claim_apply($proposal_id)
    {
        global $wpdb;
        $updated = $wpdb->query(
            $wpdb->prepare(
                'UPDATE ' . self::table_name()
                . " SET state = 'APPLYING', result_code = 'OPERATION_APPLYING', applying_at_gmt = %s"
                . " WHERE proposal_id = %s AND state = 'APPROVED'"
                . ' AND approved_by IS NOT NULL AND approved_by <> created_by'
                . ' AND expires_at_gmt > %s',
                self::now_mysql(),
                $proposal_id,
                self::now_mysql()
            )
        );
        if (1 !== $updated) {
            $row = self::get($proposal_id);
            if (! is_wp_error($row) && 'APPLIED' === $row['state'] && is_array($row['receipt'])) {
                return $row;
            }
            return new WP_Error('raos_codex_apply_precondition_failed', 'Approved proposal is unavailable.', array('status' => 409));
        }
        return self::get($proposal_id);
    }

    public static function recovery_grace_elapsed($row)
    {
        if (! is_array($row)
            || ! isset($row['state'])
            || 'APPLYING' !== $row['state']
            || ! array_key_exists('applying_at_gmt', $row)
            || ! is_string($row['applying_at_gmt'])) {
            return new WP_Error(
                'raos_codex_recovery_state_invalid',
                'Operation recovery state is invalid.',
                array('status' => 409)
            );
        }
        $claimed_at = strtotime($row['applying_at_gmt'] . ' UTC');
        if (false === $claimed_at) {
            return new WP_Error(
                'raos_codex_recovery_state_invalid',
                'Operation recovery state is invalid.',
                array('status' => 409)
            );
        }
        $remaining = ($claimed_at + self::RECOVERY_GRACE_SECONDS) - time();
        if ($remaining > 0) {
            return new WP_Error(
                'raos_codex_recovery_grace_active',
                'The applying operation is still inside its recovery grace period.',
                array('status' => 409, 'retry_after_seconds' => $remaining)
            );
        }
        return true;
    }

    public static function complete($proposal_id, $result_code, $before_sha256, $after_sha256)
    {
        global $wpdb;
        if (! preg_match('/\A[A-Z0-9_]{3,96}\z/D', $result_code)
            || (! is_null($before_sha256) && ! self::is_sha256($before_sha256))
            || (! is_null($after_sha256) && ! self::is_sha256($after_sha256))) {
            return new WP_Error('raos_codex_receipt_invalid', 'Receipt is invalid.', array('status' => 500));
        }
        $row = self::get($proposal_id);
        if (is_wp_error($row)) {
            return $row;
        }
        $receipt = array(
            'schema' => 'OperationReceiptV1',
            'proposal_id' => $proposal_id,
            'operation_id' => $row['operation_id'],
            'state' => 'APPLIED',
            'result_code' => $result_code,
            'before_sha256' => $before_sha256,
            'after_sha256' => $after_sha256,
            'audit_id' => $row['audit_id'],
        );
        $encoded = self::canonical_json($receipt);
        if (! is_string($encoded)) {
            return new WP_Error('raos_codex_receipt_invalid', 'Receipt is invalid.', array('status' => 500));
        }
        $updated = $wpdb->query(
            $wpdb->prepare(
                'UPDATE ' . self::table_name()
                . " SET state = 'APPLIED', result_code = %s, completed_at_gmt = %s,"
                . ' before_sha256 = %s, after_sha256 = %s, receipt_json = %s'
                . " WHERE proposal_id = %s AND state = 'APPLYING'",
                $result_code,
                self::now_mysql(),
                $before_sha256,
                $after_sha256,
                $encoded,
                $proposal_id
            )
        );
        if (1 !== $updated) {
            return new WP_Error('raos_codex_receipt_conflict', 'Receipt storage conflicted.', array('status' => 409));
        }
        RAOS_Codex_MCP_Deployment::remove_approval_lease($proposal_id);
        return $receipt;
    }

    public static function mark_failed($proposal_id, $result_code)
    {
        global $wpdb;
        if (! preg_match('/\A[A-Z0-9_]{3,96}\z/D', $result_code)) {
            $result_code = 'OPERATION_FAILED';
        }
        $updated = $wpdb->query(
            $wpdb->prepare(
                'UPDATE ' . self::table_name()
                . " SET state = 'FAILED', result_code = %s, completed_at_gmt = %s"
                . " WHERE proposal_id = %s AND state = 'APPLYING'",
                $result_code,
                self::now_mysql(),
                $proposal_id
            )
        );
        if (1 === $updated) {
            RAOS_Codex_MCP_Deployment::remove_approval_lease($proposal_id);
        }
        return self::get($proposal_id);
    }

    public static function pending_for_admin($limit = 50)
    {
        global $wpdb;
        $limit = max(1, min(50, (int) $limit));
        $rows = $wpdb->get_results(
            $wpdb->prepare(
                'SELECT proposal_id FROM ' . self::table_name()
                . " WHERE state IN ('PENDING','MANUAL_REQUIRED')"
                . ' ORDER BY created_at_gmt DESC LIMIT %d',
                $limit
            ),
            ARRAY_A
        );
        $result = array();
        foreach ($rows as $candidate) {
            $row = self::get($candidate['proposal_id']);
            if (! is_wp_error($row)
                && in_array($row['state'], array('PENDING', 'MANUAL_REQUIRED'), true)) {
                $result[] = $row;
            }
        }
        return $result;
    }

    public static function public_operation($row)
    {
        if (! is_array($row)) {
            return null;
        }
        if (is_array($row['receipt'])) {
            return $row['receipt'];
        }
        return array(
            'schema' => 'OperationReceiptV1',
            'proposal_id' => $row['proposal_id'],
            'operation_id' => $row['operation_id'],
            'state' => $row['state'],
            'result_code' => $row['result_code'],
            'before_sha256' => $row['before_sha256'],
            'after_sha256' => $row['after_sha256'],
            'audit_id' => $row['audit_id'],
        );
    }
}
