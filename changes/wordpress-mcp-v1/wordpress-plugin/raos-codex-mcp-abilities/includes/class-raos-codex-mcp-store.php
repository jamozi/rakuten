<?php
/**
 * Immutable proposal and operation receipt storage.
 *
 * @package RAOS_Codex_MCP_Abilities
 */

defined('ABSPATH') || exit;

final class RAOS_Codex_MCP_Store
{
    const SCHEMA_VERSION = '1';
    const TTL_SECONDS = 900;

    public static function table_name()
    {
        global $wpdb;
        return $wpdb->prefix . 'raos_codex_operations_v1';
    }

    public static function install()
    {
        global $wpdb;
        require_once ABSPATH . 'wp-admin/includes/upgrade.php';
        $table = self::table_name();
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
            completed_at_gmt datetime NULL,
            before_sha256 char(64) NULL,
            after_sha256 char(64) NULL,
            audit_id char(64) NOT NULL,
            approval_reason text NULL,
            payload_json longtext NOT NULL,
            receipt_json longtext NULL,
            package_path text NULL,
            PRIMARY KEY  (proposal_id),
            UNIQUE KEY operation_id (operation_id),
            KEY state_expires (state, expires_at_gmt),
            KEY creator_kind (created_by, kind)
        ) {$charset};";
        dbDelta($sql);
        update_option('raos_codex_mcp_store_schema_v1', self::SCHEMA_VERSION, false);
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
        $package_path = null
    ) {
        global $wpdb;
        if (! in_array($kind, array('CONTENT_RELEASE', 'THEME_RELEASE', 'PLUGIN_CHANGE'), true)
            || ! is_array($payload)
            || (! is_null($before_sha256) && ! self::is_sha256($before_sha256))
            || (! is_null($after_sha256) && ! self::is_sha256($after_sha256))
            || ! is_bool($automatic_apply_eligible)
            || (! is_null($package_path) && (! is_string($package_path) || '' === $package_path))) {
            return new WP_Error('raos_codex_proposal_invalid', 'Proposal input is invalid.', array('status' => 400));
        }
        $created_by = get_current_user_id();
        if ($created_by < 1) {
            return new WP_Error('raos_codex_identity_invalid', 'Authenticated identity is required.', array('status' => 403));
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
            'payload_sha256' => self::hash($payload),
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
            ),
            array('%s', '%s', '%s', '%s', '%s', '%d', '%s', '%s', '%s', '%s', '%s', '%s', '%s')
        );
        if (1 !== $inserted) {
            return new WP_Error('raos_codex_proposal_store_failed', 'Proposal storage failed.', array('status' => 500));
        }
        return self::get($proposal_id);
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
            $wpdb->query(
                $wpdb->prepare(
                    'UPDATE ' . self::table_name()
                    . " SET state = 'EXPIRED', result_code = 'PROPOSAL_EXPIRED'"
                    . " WHERE proposal_id = %s AND state IN ('PENDING','MANUAL_REQUIRED','APPROVED')",
                    $proposal_id
                )
            );
            $row['state'] = 'EXPIRED';
            $row['result_code'] = 'PROPOSAL_EXPIRED';
        }
        $payload = json_decode($row['payload_json'], true);
        $receipt = is_string($row['receipt_json'])
            ? json_decode($row['receipt_json'], true)
            : null;
        if (! is_array($payload) || (! is_null($receipt) && ! is_array($receipt))) {
            return new WP_Error('raos_codex_store_corrupt', 'Stored operation is invalid.', array('status' => 500));
        }
        $row['payload'] = $payload;
        $row['receipt'] = $receipt;
        return $row;
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
        if ((int) $row['created_by'] === (int) $approver_id || (int) $approver_id < 1) {
            return new WP_Error('raos_codex_self_approval_forbidden', 'A different administrator must approve.', array('status' => 403));
        }
        if (! is_string($reason) || strlen(trim($reason)) < 10 || strlen($reason) > 2000) {
            return new WP_Error('raos_codex_approval_reason_invalid', 'Approval reason is invalid.', array('status' => 400));
        }
        $updated = $wpdb->query(
            $wpdb->prepare(
                'UPDATE ' . self::table_name()
                . " SET state = 'APPROVED', result_code = 'PROPOSAL_APPROVED',"
                . ' approved_by = %d, approved_at_gmt = %s, approval_reason = %s'
                . " WHERE proposal_id = %s AND state = 'PENDING' AND expires_at_gmt > %s",
                (int) $approver_id,
                self::now_mysql(),
                trim($reason),
                $proposal_id,
                self::now_mysql()
            )
        );
        if (1 !== $updated) {
            return new WP_Error('raos_codex_approval_conflict', 'Proposal approval conflicted or expired.', array('status' => 409));
        }
        return self::get($proposal_id);
    }

    public static function claim_apply($proposal_id)
    {
        global $wpdb;
        $updated = $wpdb->query(
            $wpdb->prepare(
                'UPDATE ' . self::table_name()
                . " SET state = 'APPLYING', result_code = 'OPERATION_APPLYING'"
                . " WHERE proposal_id = %s AND state = 'APPROVED'"
                . ' AND approved_by IS NOT NULL AND approved_by <> created_by'
                . ' AND expires_at_gmt > %s',
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
        return $receipt;
    }

    public static function mark_failed($proposal_id, $result_code)
    {
        global $wpdb;
        if (! preg_match('/\A[A-Z0-9_]{3,96}\z/D', $result_code)) {
            $result_code = 'OPERATION_FAILED';
        }
        $wpdb->query(
            $wpdb->prepare(
                'UPDATE ' . self::table_name()
                . " SET state = 'FAILED', result_code = %s, completed_at_gmt = %s"
                . " WHERE proposal_id = %s AND state = 'APPLYING'",
                $result_code,
                self::now_mysql(),
                $proposal_id
            )
        );
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
