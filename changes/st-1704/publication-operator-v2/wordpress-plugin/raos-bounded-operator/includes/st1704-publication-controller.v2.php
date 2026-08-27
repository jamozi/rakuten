<?php
/**
 * ST-1704 publication and fixed Draft-revision extension for the bounded operator.
 *
 * This file deliberately owns a separate namespace, proposal ledger, audit
 * chain, write gate, and approval action. It never grants a WordPress publish,
 * taxonomy, HTML, URL, or metadata capability to the executor role.
 */

if (! defined('ABSPATH')) {
    exit;
}

final class RAOS_ST1704_Publication_Controller_V2
{
    const VERSION = '2.0.0';
    const REVISION_VERSION = '2.1.0';
    const REST_NAMESPACE = 'raos-operator/v2';
    const SITE_ORIGIN = 'https://kurashinoshirube.com';
    const OPERATOR_CONTRACT_VERSION = 2;
    const PROFILE_VERSION = 2;
    const OPERATION = 'PUBLISH_ST1704_ARTICLE';
    const REVISION_OPERATION = 'REVISE_ST1704_DRAFT';
    const RESULT_CODE = 'ST1704_ARTICLE_PUBLISHED';
    const REVISION_RESULT_CODE = 'ST1704_DRAFT_REVISED';
    const REVISION_VERIFY_RESULT_CODE = 'ST1704_DRAFT_REVISION_VERIFIED';
    const REVISION_RECOVERY_RESULT_CODE = 'ST1704_DRAFT_REVISION_STATE_OBSERVED';
    const HOOK_REPLAY_COMPLETED = 'HOOK_REPLAY_COMPLETED';
    const REDIRECT_META_PHASE_INACTIVE = 'INACTIVE';
    const REDIRECT_META_PHASE_POST_UPDATED = 'POST_UPDATED';
    const DEFAULT_TTL = 900;
    const ROLE = 'raos_operator_executor';
    const CAP_READ = 'raos_operator_read';
    const CAP_PROPOSE = 'raos_operator_propose';
    const CAP_APPLY = 'raos_operator_apply';
    const BOUND_OPERATOR_OPTION = 'raos_operator_bound_user_id_v1';
    const NETWORK_IDENTITY_META = 'raos_operator_network_identity_v1';
    const SNAPSHOT_META_KEY = '_raos_publication_snapshot_v1';
    const SNAPSHOT_SCHEMA = 'RAOS_PUBLICATION_SNAPSHOT_V1';
    const SNAPSHOT_MAX_BYTES = 16384;
    const REVISION_CONTENT_MAX_BYTES = 2097152;
    const REVIEW_REQUEST_PATH = '/wp-json/wp/v2/posts?_fields=id%2Ctype%2Cslug%2Cstatus%2Ctitle.raw%2Cexcerpt.raw%2Ccontent.raw%2Cmeta._raos_publication_snapshot_v1';
    const ADMIN_PAGE = 'raos-st1704-publication-operator-v2';
    const APPROVAL_ACTION = 'raos_st1704_publication_approve_v2';
    const RECONCILIATION_CLEANUP_ACTION =
        'raos_st1704_redirect_meta_reconcile_v1';
    const RECONCILIATION_CONFIRM_ACTION =
        'raos_st1704_reconciled_public_confirm_v1';
    const RECONCILIATION_FAILURE_CODE =
        'POST_COMMIT_HOOK_REPLAY_UNCERTAIN';
    const RECONCILIATION_EXCEPTION_FAILURE_CODE =
        'POST_COMMIT_HOOK_REPLAY_EXCEPTION';
    const RECONCILIATION_CLEANUP_EVENT = 'REDIRECT_META_RECONCILED';
    const RECONCILIATION_PUBLIC_EVENT = 'RECONCILED_PUBLIC';
    const MUTEX_PURPOSE = 'PUBLICATION_V2';
    const MAX_REASON_BYTES = 1200;
    const MAX_PASSWORD_BYTES = 4096;
    const MAX_PROPOSAL_ROWS = 1000;
    const MAX_META_ROWS = 2048;
    const MAX_TERM_RELATIONSHIPS = 256;
    const MAX_REPLAY_HOOK_CALLBACKS = 256;
    const MAX_RECONCILIATION_AUDIT_ROWS = 4096;
    const WORDPRESS_CORE_RELEASE_PATTERN = '/\A7\.1(?:\.[0-9]+)*\z/';

    private static $instance = null;
    private static $application_password_authenticated = false;
    private static $application_password_user_id = 0;

    private $legacy_operator;
    private $combined_firewall_ready = false;

    public static function instance($legacy_operator = null)
    {
        if (! self::wordpress_core_is_supported()) {
            return null;
        }
        if (self::$instance !== null) {
            return self::$instance;
        }
        if (! $legacy_operator instanceof RAOS_Bounded_Operator
            || $legacy_operator !== RAOS_Bounded_Operator::instance()) {
            return null;
        }
        self::$instance = new self($legacy_operator);
        return self::$instance;
    }

    private static function wordpress_core_is_supported()
    {
        global $wp_version;
        return is_string($wp_version)
            && preg_match(
                self::WORDPRESS_CORE_RELEASE_PATTERN,
                $wp_version
            ) === 1;
    }

    private function __construct($legacy_operator)
    {
        $this->legacy_operator = $legacy_operator;
        $legacy_callback = array(
            $legacy_operator,
            'guard_operator_rest_route',
        );
        if (has_filter('rest_request_before_callbacks', $legacy_callback) === 10
            && remove_filter(
                'rest_request_before_callbacks',
                $legacy_callback,
                10
            )) {
            add_filter(
                'rest_request_before_callbacks',
                array($this, 'guard_combined_operator_rest_route'),
                10,
                3
            );
            $this->combined_firewall_ready = has_filter(
                'rest_request_before_callbacks',
                array($this, 'guard_combined_operator_rest_route')
            ) === 10;
        }

        add_action(
            'application_password_did_authenticate',
            array($this, 'record_application_password_authentication'),
            20,
            2
        );
        add_action('rest_api_init', array($this, 'register_rest_routes'));
        add_action('admin_menu', array($this, 'register_admin_page'));
        add_action(
            'admin_post_' . self::APPROVAL_ACTION,
            array($this, 'handle_approval')
        );
        add_action(
            'admin_post_' . self::RECONCILIATION_CLEANUP_ACTION,
            array($this, 'handle_reconciliation_cleanup')
        );
        add_action(
            'admin_post_' . self::RECONCILIATION_CONFIRM_ACTION,
            array($this, 'handle_reconciliation_public_confirmation')
        );
    }

    public function record_application_password_authentication($user, $item)
    {
        unset($item);
        self::$application_password_authenticated = false;
        self::$application_password_user_id = 0;
        if ($this->combined_firewall_ready
            && $user instanceof WP_User
            && $user->exists()
            && $this->executor_identity_is_exact($user, false)) {
            self::$application_password_authenticated = true;
            self::$application_password_user_id = (int) $user->ID;
        }
    }

    public function guard_combined_operator_rest_route(
        $response,
        $handler,
        $request
    ) {
        if ($request instanceof WP_REST_Request
            && is_array($handler)
            && $this->is_exact_v2_handler($handler, $request)) {
            return $this->authenticated_executor_is_exact()
                ? $response
                : self::error('raos_st1704_operator_authentication_required', 403);
        }
        return $this->legacy_operator->guard_operator_rest_route(
            $response,
            $handler,
            $request
        );
    }

    private function is_exact_v2_handler(array $handler, $request)
    {
        if (! isset($handler['callback'])
            || ! is_array($handler['callback'])
            || count($handler['callback']) !== 2
            || $handler['callback'][0] !== $this
            || ! is_string($handler['callback'][1])) {
            return false;
        }
        $method = strtoupper((string) $request->get_method());
        $route = (string) $request->get_route();
        $callback = $handler['callback'][1];
        if ($method === 'GET'
            && $route === '/' . self::REST_NAMESPACE . '/status') {
            return $callback === 'rest_status';
        }
        if ($method === 'GET'
            && $route === '/' . self::REST_NAMESPACE . '/revision-status') {
            return $callback === 'rest_revision_status';
        }
        if ($method === 'POST'
            && $route === '/' . self::REST_NAMESPACE . '/proposals') {
            return $callback === 'rest_create_proposal';
        }
        if ($method === 'GET'
            && preg_match(
                '#\A/' . preg_quote(self::REST_NAMESPACE, '#')
                . '/proposals/[a-f0-9]{64}\z#',
                $route
            ) === 1) {
            return $callback === 'rest_read_proposal';
        }
        if ($method === 'POST'
            && preg_match(
                '#\A/' . preg_quote(self::REST_NAMESPACE, '#')
                . '/proposals/[a-f0-9]{64}/apply\z#',
                $route
            ) === 1) {
            return $callback === 'rest_apply';
        }
        if ($method === 'GET'
            && preg_match(
                '#\A/' . preg_quote(self::REST_NAMESPACE, '#')
                . '/proposals/[a-f0-9]{64}/verify\z#',
                $route
            ) === 1) {
            return $callback === 'rest_verify_revision';
        }
        if ($method === 'GET'
            && preg_match(
                '#\A/' . preg_quote(self::REST_NAMESPACE, '#')
                . '/proposals/[a-f0-9]{64}/revision-state\z#',
                $route
            ) === 1) {
            return $callback === 'rest_recover_revision_state';
        }
        return false;
    }

    public function register_rest_routes()
    {
        register_rest_route(
            self::REST_NAMESPACE,
            '/status',
            array(
                'methods' => WP_REST_Server::READABLE,
                'callback' => array($this, 'rest_status'),
                'permission_callback' => array($this, 'can_read'),
            )
        );
        register_rest_route(
            self::REST_NAMESPACE,
            '/revision-status',
            array(
                'methods' => WP_REST_Server::READABLE,
                'callback' => array($this, 'rest_revision_status'),
                'permission_callback' => array($this, 'can_read'),
            )
        );
        register_rest_route(
            self::REST_NAMESPACE,
            '/proposals/(?P<proposal_id>[a-f0-9]{64})/verify',
            array(
                'methods' => WP_REST_Server::READABLE,
                'callback' => array($this, 'rest_verify_revision'),
                'permission_callback' => array($this, 'can_read'),
            )
        );
        register_rest_route(
            self::REST_NAMESPACE,
            '/proposals/(?P<proposal_id>[a-f0-9]{64})/revision-state',
            array(
                'methods' => WP_REST_Server::READABLE,
                'callback' => array($this, 'rest_recover_revision_state'),
                'permission_callback' => array($this, 'can_read'),
            )
        );
        register_rest_route(
            self::REST_NAMESPACE,
            '/proposals',
            array(
                'methods' => WP_REST_Server::CREATABLE,
                'callback' => array($this, 'rest_create_proposal'),
                'permission_callback' => array($this, 'can_propose'),
            )
        );
        register_rest_route(
            self::REST_NAMESPACE,
            '/proposals/(?P<proposal_id>[a-f0-9]{64})',
            array(
                'methods' => WP_REST_Server::READABLE,
                'callback' => array($this, 'rest_read_proposal'),
                'permission_callback' => array($this, 'can_read'),
            )
        );
        register_rest_route(
            self::REST_NAMESPACE,
            '/proposals/(?P<proposal_id>[a-f0-9]{64})/apply',
            array(
                'methods' => WP_REST_Server::CREATABLE,
                'callback' => array($this, 'rest_apply'),
                'permission_callback' => array($this, 'can_apply'),
            )
        );
    }

    public function can_read()
    {
        return $this->authenticated_executor_is_exact()
            && current_user_can(self::CAP_READ);
    }

    public function can_propose()
    {
        return $this->authenticated_executor_is_exact()
            && current_user_can(self::CAP_PROPOSE);
    }

    public function can_apply()
    {
        return $this->authenticated_executor_is_exact()
            && current_user_can(self::CAP_APPLY);
    }

    private function authenticated_executor_is_exact()
    {
        $user = wp_get_current_user();
        return $this->combined_firewall_ready
            && self::$application_password_authenticated
            && $user instanceof WP_User
            && $user->exists()
            && self::$application_password_user_id === (int) $user->ID
            && $this->executor_identity_is_exact($user, true);
    }

    private function executor_identity_is_exact($user, $require_marker)
    {
        if (! $user instanceof WP_User
            || ! $user->exists()
            || ! self::runtime_origin_is_exact()
            || count($user->roles) !== 1
            || reset($user->roles) !== self::ROLE
            || ($require_marker
                && (! self::$application_password_authenticated
                    || self::$application_password_user_id !== (int) $user->ID))) {
            return false;
        }
        $binding = $this->operator_user_binding();
        if ($binding['state'] !== 'VALID'
            || $binding['user_id'] !== (int) $user->ID
            || ! $this->operator_network_marker_is_exact((int) $user->ID)) {
            return false;
        }
        $role = get_role(self::ROLE);
        if (! $role instanceof WP_Role
            || ! is_array($role->capabilities)
            || ! is_array($user->caps)
            || ! is_array($user->allcaps)) {
            return false;
        }
        $expected = self::exact_executor_capabilities();
        $expected_all = $expected;
        $expected_all[self::ROLE] = true;
        $role_caps = $role->capabilities;
        $user_caps = $user->caps;
        $all_caps = $user->allcaps;
        ksort($expected, SORT_STRING);
        ksort($expected_all, SORT_STRING);
        ksort($role_caps, SORT_STRING);
        ksort($user_caps, SORT_STRING);
        ksort($all_caps, SORT_STRING);
        return $role_caps === $expected
            && $user_caps === array(self::ROLE => true)
            && $all_caps === $expected_all;
    }

    private static function exact_executor_capabilities()
    {
        return array(
            'read' => true,
            self::CAP_READ => true,
            self::CAP_PROPOSE => true,
            self::CAP_APPLY => true,
        );
    }

    private function operator_user_binding()
    {
        global $wpdb;
        $rows = $wpdb->get_col(
            $wpdb->prepare(
                "SELECT option_value FROM {$wpdb->options} "
                . 'WHERE BINARY option_name = BINARY %s',
                self::BOUND_OPERATOR_OPTION
            )
        );
        if ($wpdb->last_error !== ''
            || ! is_array($rows)
            || count($rows) !== 1
            || ! is_string($rows[0])
            || preg_match('/\A[1-9][0-9]{0,18}\z/', $rows[0]) !== 1) {
            return array('state' => 'INVALID', 'user_id' => 0);
        }
        $user_id = (int) $rows[0];
        return $user_id > 0 && (string) $user_id === $rows[0]
            ? array('state' => 'VALID', 'user_id' => $user_id)
            : array('state' => 'INVALID', 'user_id' => 0);
    }

    private function operator_network_marker_is_exact($user_id)
    {
        global $wpdb;
        $rows = $wpdb->get_col(
            $wpdb->prepare(
                "SELECT meta_value FROM {$wpdb->usermeta} "
                . 'WHERE user_id = %d AND BINARY meta_key = BINARY %s '
                . 'ORDER BY umeta_id ASC',
                $user_id,
                self::NETWORK_IDENTITY_META
            )
        );
        $expected = 'RAOS_OPERATOR_IDENTITY_V1' . "\n"
            . self::SITE_ORIGIN . "\n" . (string) $user_id;
        return $wpdb->last_error === ''
            && is_array($rows)
            && count($rows) === 1
            && is_string($rows[0])
            && hash_equals($expected, $rows[0]);
    }

    private static function master_writes_enabled()
    {
        return defined('RAOS_OPERATOR_WRITES_ENABLED')
            && RAOS_OPERATOR_WRITES_ENABLED === true;
    }

    private static function publication_writes_enabled()
    {
        return defined('RAOS_ST1704_PUBLICATION_WRITES_ENABLED')
            && RAOS_ST1704_PUBLICATION_WRITES_ENABLED === true;
    }

    private static function reconciliation_gate_enabled()
    {
        return defined('RAOS_ST1704_PUBLICATION_RECONCILIATION_WRITES_ENABLED')
            && RAOS_ST1704_PUBLICATION_RECONCILIATION_WRITES_ENABLED === true;
    }

    private static function writes_enabled()
    {
        return self::master_writes_enabled()
            && self::publication_writes_enabled()
            && ! self::reconciliation_gate_enabled();
    }

    private static function reconciliation_writes_enabled()
    {
        return self::master_writes_enabled()
            && ! self::publication_writes_enabled()
            && self::reconciliation_gate_enabled();
    }

    private static function runtime_origin_is_exact()
    {
        return ! is_multisite()
            && is_ssl()
            && untrailingslashit(home_url('/')) === self::SITE_ORIGIN
            && untrailingslashit(site_url('/')) === self::SITE_ORIGIN;
    }

    private static function error($code, $status)
    {
        return new WP_Error(
            $code,
            'The ST-1704 publication operator rejected the request.',
            array('status' => $status)
        );
    }

    public static function activate()
    {
        if (! self::wordpress_core_is_supported()) {
            wp_die(esc_html('RAOS ST-1704 publication requires WordPress 7.1.x.'));
        }
        if (is_multisite()) {
            wp_die(esc_html('RAOS ST-1704 publication does not support multisite.'));
        }
        if (! self::bindings_are_exact()) {
            wp_die(esc_html('RAOS ST-1704 publication bindings are invalid.'));
        }
        self::install_tables();
        if (! self::tables_are_innodb()
            || ! self::append_activation_audit()) {
            wp_die(esc_html('RAOS ST-1704 publication audit initialization failed.'));
        }
    }

    private static function install_tables()
    {
        global $wpdb;
        require_once ABSPATH . 'wp-admin/includes/upgrade.php';
        $charset = $wpdb->get_charset_collate();
        $proposal_table = self::proposal_table();
        $audit_table = self::audit_table();
        $proposal_sql = "CREATE TABLE {$proposal_table} (
            internal_id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
            proposal_id char(64) NOT NULL,
            operation varchar(32) NOT NULL,
            request_json longtext NOT NULL,
            state varchar(24) NOT NULL,
            created_at datetime NOT NULL,
            expires_at datetime NOT NULL,
            proposer_user_id bigint(20) unsigned NOT NULL,
            before_state_json longtext NOT NULL,
            before_state_hash char(64) NOT NULL,
            approved_by_user_id bigint(20) unsigned DEFAULT NULL,
            approved_at datetime DEFAULT NULL,
            approval_expires_at datetime DEFAULT NULL,
            approval_reason varchar(300) DEFAULT NULL,
            approval_evidence_hash char(64) DEFAULT NULL,
            apply_started_at datetime DEFAULT NULL,
            completed_at datetime DEFAULT NULL,
            idempotency_key char(64) DEFAULT NULL,
            result_code varchar(64) DEFAULT NULL,
            rollback_json longtext DEFAULT NULL,
            state_version bigint(20) unsigned NOT NULL DEFAULT 1,
            PRIMARY KEY  (internal_id),
            UNIQUE KEY proposal_id (proposal_id),
            UNIQUE KEY idempotency_key (idempotency_key),
            KEY state_expiry (state,expires_at)
        ) ENGINE=InnoDB {$charset};";
        $audit_sql = "CREATE TABLE {$audit_table} (
            audit_id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
            occurred_at datetime NOT NULL,
            actor_user_id bigint(20) unsigned NOT NULL,
            event_code varchar(64) NOT NULL,
            proposal_id char(64) DEFAULT NULL,
            detail_code varchar(64) NOT NULL,
            previous_hash char(64) NOT NULL,
            event_hash char(64) NOT NULL,
            PRIMARY KEY  (audit_id),
            UNIQUE KEY event_hash (event_hash),
            KEY proposal_events (proposal_id,audit_id)
        ) ENGINE=InnoDB {$charset};";
        dbDelta($proposal_sql);
        dbDelta($audit_sql);
    }

    private static function append_activation_audit()
    {
        global $wpdb;
        if ($wpdb->query('START TRANSACTION') === false) {
            return false;
        }
        $audit = self::append_audit(
            'PUBLICATION_CONTROLLER_ACTIVATED',
            str_repeat('0', 64),
            'PUBLICATION_TABLES_READY',
            get_current_user_id()
        );
        if (! is_string($audit) || $wpdb->query('COMMIT') === false) {
            $wpdb->query('ROLLBACK');
            return false;
        }
        return true;
    }

    private static function tables_are_innodb()
    {
        global $wpdb;
        return self::table_is_innodb(self::proposal_table())
            && self::table_is_innodb(self::audit_table())
            && self::table_is_innodb($wpdb->posts)
            && self::table_is_innodb($wpdb->postmeta)
            && self::table_is_innodb($wpdb->term_relationships)
            && self::table_is_innodb($wpdb->term_taxonomy)
            && self::table_is_innodb($wpdb->terms);
    }

    private static function table_is_innodb($table)
    {
        global $wpdb;
        $rows = $wpdb->get_results(
            $wpdb->prepare(
                'SELECT ENGINE FROM information_schema.TABLES '
                . 'WHERE BINARY TABLE_SCHEMA = BINARY DATABASE() '
                . 'AND BINARY TABLE_NAME = BINARY %s',
                $table
            ),
            ARRAY_A
        );
        return $wpdb->last_error === ''
            && is_array($rows)
            && count($rows) === 1
            && isset($rows[0]['ENGINE'])
            && $rows[0]['ENGINE'] === 'InnoDB';
    }

    private static function proposal_table()
    {
        global $wpdb;
        return $wpdb->prefix . 'raos_st1704_publication_proposals_v2';
    }

    private static function audit_table()
    {
        global $wpdb;
        return $wpdb->prefix . 'raos_st1704_publication_audit_v2';
    }

    public function rest_status(WP_REST_Request $request)
    {
        if (! self::runtime_origin_is_exact()) {
            return self::error('raos_st1704_runtime_origin_invalid', 409);
        }
        if ($request->get_body() !== ''
            || $request->get_query_params() !== array()) {
            return self::error('raos_st1704_status_request_invalid', 400);
        }
        global $wpdb;
        $counts = array_fill_keys(self::states(), 0);
        $rows = $wpdb->get_results(
            'SELECT state, COUNT(*) AS aggregate_count FROM '
            . self::proposal_table() . ' GROUP BY state',
            ARRAY_A
        );
        if ($wpdb->last_error !== '' || ! is_array($rows)) {
            return self::error('raos_st1704_status_unavailable', 500);
        }
        foreach ($rows as $row) {
            if (! is_array($row)
                || ! isset($row['state'], $row['aggregate_count'])
                || ! array_key_exists($row['state'], $counts)
                || ! preg_match('/\A(?:0|[1-9][0-9]*)\z/', (string) $row['aggregate_count'])) {
                return self::error('raos_st1704_status_unavailable', 500);
            }
            $counts[$row['state']] = (int) $row['aggregate_count'];
        }
        return rest_ensure_response(
            array(
                'schema' => 'RAOS_ST1704_PUBLICATION_OPERATOR_STATUS_V2',
                'operator_version' => self::VERSION,
                'master_writes_enabled' => self::master_writes_enabled(),
                'publication_writes_enabled' => self::publication_writes_enabled(),
                'writes_enabled' => self::writes_enabled(),
                'supported_operations' => array(self::OPERATION),
                'proposal_counts' => $counts,
            )
        );
    }

    public function rest_revision_status(WP_REST_Request $request)
    {
        if (! self::runtime_origin_is_exact()) {
            return self::error('raos_st1704_runtime_origin_invalid', 409);
        }
        if ($request->get_body() !== ''
            || $request->get_query_params() !== array()) {
            return self::error('raos_st1704_revision_status_request_invalid', 400);
        }
        return rest_ensure_response(
            array(
                'schema' => 'RAOS_ST1704_DRAFT_REVISION_STATUS_V2',
                'operator_version' => self::REVISION_VERSION,
                'master_writes_enabled' => self::master_writes_enabled(),
                'publication_writes_enabled' => self::publication_writes_enabled(),
                'writes_enabled' => self::writes_enabled(),
                'supported_operations' => array(self::REVISION_OPERATION),
            )
        );
    }

    public function rest_create_proposal(WP_REST_Request $request)
    {
        if (! self::runtime_origin_is_exact()) {
            return self::error('raos_st1704_runtime_origin_invalid', 409);
        }
        if (! self::writes_enabled()) {
            return self::error('raos_st1704_writes_disabled', 503);
        }
        if ($request->get_header('content-type') !== 'application/json') {
            return self::error('raos_st1704_content_type_invalid', 400);
        }
        $input = $request->get_json_params();
        if (! is_array($input)) {
            return self::error('raos_st1704_proposal_invalid', 400);
        }
        $normalized = $this->normalize_proposal_request($input);
        if (is_wp_error($normalized)) {
            return $normalized;
        }
        $canonical = self::canonical_json($normalized);
        if (! is_string($canonical)
            || ! hash_equals($canonical, (string) $request->get_body())) {
            return self::error('raos_st1704_proposal_invalid', 400);
        }
        $proposal_id = hash('sha256', $canonical);
        $mutex_name = $this->publication_mutex_name();
        if (! $this->acquire_publication_mutex($mutex_name)) {
            return self::error('raos_st1704_publication_busy', 409);
        }
        $released = false;
        try {
            $response = $this->create_proposal_under_mutex(
                $normalized,
                $canonical,
                $proposal_id,
                $mutex_name
            );
        } catch (Throwable $exception) {
            global $wpdb;
            $wpdb->query('ROLLBACK');
            $response = self::error('raos_st1704_proposal_store_failed', 500);
        } finally {
            $released = $this->release_publication_mutex($mutex_name);
        }
        return $released
            ? $response
            : self::error('raos_st1704_mutex_release_uncertain', 500);
    }

    public function rest_read_proposal(WP_REST_Request $request)
    {
        if (! self::runtime_origin_is_exact()) {
            return self::error('raos_st1704_runtime_origin_invalid', 409);
        }
        if ($request->get_body() !== ''
            || $request->get_query_params() !== array()) {
            return self::error('raos_st1704_proposal_read_invalid', 400);
        }
        $proposal_id = (string) $request['proposal_id'];
        if (preg_match('/\A[a-f0-9]{64}\z/', $proposal_id) !== 1) {
            return self::error('raos_st1704_proposal_not_found', 404);
        }
        $row = $this->proposal_row($proposal_id);
        if (! is_array($row)) {
            return is_wp_error($row)
                ? $row
                : self::error('raos_st1704_proposal_not_found', 404);
        }
        return $this->validated_proposal_response(
            $row,
            $proposal_id,
            null,
            true,
            200
        );
    }

    private function normalize_proposal_request(array $input)
    {
        if (isset($input['operation'])
            && $input['operation'] === self::REVISION_OPERATION) {
            return $this->normalize_revision_proposal_request($input);
        }
        $keys = array(
            'article_id',
            'category_contract',
            'draft_post_id',
            'operation',
            'operator_contract_version',
            'packet_sha256',
            'profile_version',
            'public_slug',
            'request_sha256',
            'request_token',
            'site_origin',
            'snapshot_payload_sha256',
            'ttl_seconds',
            'visible_content_sha256',
        );
        if (! self::has_exact_keys($input, $keys)
            || $input['operation'] !== self::OPERATION
            || $input['operator_contract_version'] !== self::OPERATOR_CONTRACT_VERSION
            || $input['profile_version'] !== self::PROFILE_VERSION
            || $input['site_origin'] !== self::SITE_ORIGIN
            || $input['ttl_seconds'] !== self::DEFAULT_TTL
            || $input['category_contract']
                !== RAOS_ST1704_Publication_Bindings_V2::CATEGORY_CONTRACT
            || ! is_string($input['article_id'])
            || ! is_string($input['public_slug'])
            || ! is_int($input['draft_post_id'])
            || $input['draft_post_id'] < 1) {
            return self::error('raos_st1704_proposal_invalid', 400);
        }
        foreach (
            array(
                'packet_sha256',
                'request_sha256',
                'request_token',
                'snapshot_payload_sha256',
                'visible_content_sha256',
            ) as $hash_key
        ) {
            if (! is_string($input[$hash_key])
                || preg_match('/\A[a-f0-9]{64}\z/', $input[$hash_key]) !== 1) {
                return self::error('raos_st1704_proposal_invalid', 400);
            }
        }
        $articles = self::fixed_articles();
        if (! isset($articles[$input['article_id']])
            || $articles[$input['article_id']] !== $input['public_slug']) {
            return self::error('raos_st1704_article_not_bound', 409);
        }
        return array(
            'article_id' => $input['article_id'],
            'category_contract' => RAOS_ST1704_Publication_Bindings_V2::CATEGORY_CONTRACT,
            'draft_post_id' => $input['draft_post_id'],
            'operation' => self::OPERATION,
            'operator_contract_version' => self::OPERATOR_CONTRACT_VERSION,
            'packet_sha256' => $input['packet_sha256'],
            'profile_version' => self::PROFILE_VERSION,
            'public_slug' => $input['public_slug'],
            'request_sha256' => $input['request_sha256'],
            'request_token' => $input['request_token'],
            'site_origin' => self::SITE_ORIGIN,
            'snapshot_payload_sha256' => $input['snapshot_payload_sha256'],
            'ttl_seconds' => self::DEFAULT_TTL,
            'visible_content_sha256' => $input['visible_content_sha256'],
        );
    }

    private static function decode_canonical_base64($value, $maximum)
    {
        if (! is_string($value)
            || $value === ''
            || ! is_int($maximum)
            || $maximum < 1
            || strlen($value) > 4 * $maximum + 4) {
            return null;
        }
        $decoded = base64_decode($value, true);
        return is_string($decoded)
            && strlen($decoded) <= $maximum
            && hash_equals($value, base64_encode($decoded))
            ? $decoded
            : null;
    }

    private function normalize_revision_proposal_request(array $input)
    {
        $keys = array(
            'article_id',
            'draft_post_id',
            'generation',
            'operation',
            'operation_sha256',
            'operator_contract_version',
            'predecessor',
            'profile_version',
            'public_slug',
            'request_token',
            'site_origin',
            'successor',
            'ttl_seconds',
        );
        $binding_keys = array(
            'content_sha256',
            'packet_sha256',
            'payload_sha256',
            'request_sha256',
            'review_slug',
        );
        $successor_keys = array_merge(
            $binding_keys,
            array(
                'content_base64',
                'excerpt_base64',
                'snapshot_base64',
                'title_base64',
            )
        );
        if (! self::has_exact_keys($input, $keys)
            || $input['operation'] !== self::REVISION_OPERATION
            || $input['operator_contract_version'] !== self::OPERATOR_CONTRACT_VERSION
            || $input['profile_version'] !== self::PROFILE_VERSION
            || $input['site_origin'] !== self::SITE_ORIGIN
            || $input['ttl_seconds'] !== self::DEFAULT_TTL
            || ! is_string($input['article_id'])
            || ! is_string($input['public_slug'])
            || ! is_int($input['draft_post_id'])
            || $input['draft_post_id'] < 1
            || ! is_int($input['generation'])
            || $input['generation'] < 2
            || $input['generation'] > 32
            || ! self::has_exact_keys($input['predecessor'], $binding_keys)
            || ! self::has_exact_keys($input['successor'], $successor_keys)) {
            return self::error('raos_st1704_revision_proposal_invalid', 400);
        }
        $articles = self::fixed_articles();
        $revision_post_ids = self::fixed_revision_post_ids();
        if (! isset($articles[$input['article_id']])
            || $articles[$input['article_id']] !== $input['public_slug']
            || ! isset($revision_post_ids[$input['article_id']])
            || $revision_post_ids[$input['article_id']]
                !== $input['draft_post_id']) {
            return self::error('raos_st1704_article_not_bound', 409);
        }
        foreach (array('operation_sha256', 'request_token') as $hash_key) {
            if (! is_string($input[$hash_key])
                || preg_match('/\A[a-f0-9]{64}\z/', $input[$hash_key]) !== 1) {
                return self::error('raos_st1704_revision_proposal_invalid', 400);
            }
        }
        foreach (array('predecessor', 'successor') as $side) {
            foreach (
                array(
                    'content_sha256',
                    'packet_sha256',
                    'payload_sha256',
                    'request_sha256',
                ) as $hash_key
            ) {
                if (! is_string($input[$side][$hash_key])
                    || preg_match(
                        '/\A[a-f0-9]{64}\z/',
                        $input[$side][$hash_key]
                    ) !== 1) {
                    return self::error(
                        'raos_st1704_revision_proposal_invalid',
                        400
                    );
                }
            }
            $expected_review_slug = 'raos-review-' . $input['public_slug'] . '-'
                . $input[$side]['payload_sha256'];
            if (! is_string($input[$side]['review_slug'])
                || ! hash_equals(
                    $expected_review_slug,
                    $input[$side]['review_slug']
                )) {
                return self::error(
                    'raos_st1704_revision_proposal_invalid',
                    400
                );
            }
        }
        if (hash_equals(
            $input['predecessor']['request_sha256'],
            $input['successor']['request_sha256']
        ) || hash_equals(
            $input['predecessor']['packet_sha256'],
            $input['successor']['packet_sha256']
        )) {
            return self::error('raos_st1704_revision_not_fresh', 409);
        }
        $title = self::decode_canonical_base64(
            $input['successor']['title_base64'],
            1200
        );
        $excerpt = self::decode_canonical_base64(
            $input['successor']['excerpt_base64'],
            2400
        );
        $content = self::decode_canonical_base64(
            $input['successor']['content_base64'],
            self::REVISION_CONTENT_MAX_BYTES
        );
        $snapshot_raw = self::decode_canonical_base64(
            $input['successor']['snapshot_base64'],
            self::SNAPSHOT_MAX_BYTES
        );
        $snapshot = is_string($snapshot_raw)
            ? self::parse_snapshot($snapshot_raw)
            : null;
        if (! is_string($title)
            || ! is_string($excerpt)
            || ! is_string($content)
            || $content === ''
            || strpos($content, "\0") !== false
            || ! is_array($snapshot)
            || $snapshot['payload']['article_id'] !== $input['article_id']
            || $snapshot['payload']['slug'] !== $input['public_slug']
            || $snapshot['payload']['packet_sha256']
                !== $input['successor']['packet_sha256']
            || $snapshot['payload']['visible_content_sha256']
                !== $input['successor']['content_sha256']
            || $snapshot['payload_sha256']
                !== $input['successor']['payload_sha256']
            || $snapshot['payload']['title'] !== $title
            || $snapshot['payload']['description'] !== $excerpt
            || ! hash_equals(
                $input['successor']['content_sha256'],
                hash('sha256', $content)
            )) {
            return self::error('raos_st1704_revision_successor_invalid', 409);
        }
        $successor_body = array(
            'content' => $content,
            'excerpt' => $excerpt,
            'meta' => array(self::SNAPSHOT_META_KEY => $snapshot_raw),
            'slug' => $input['successor']['review_slug'],
            'status' => 'draft',
            'title' => $title,
        );
        $request_material = self::canonical_json(
            array(
                'body' => $successor_body,
                'origin' => self::SITE_ORIGIN,
                'path' => self::REVIEW_REQUEST_PATH,
            )
        );
        if (! is_string($request_material)
            || ! hash_equals(
                $input['successor']['request_sha256'],
                hash('sha256', $request_material)
            )) {
            return self::error('raos_st1704_revision_request_not_bound', 409);
        }
        $operation_material = array(
            'article_id' => $input['article_id'],
            'draft_id' => $input['draft_post_id'],
            'generation' => $input['generation'],
            'predecessor' => $input['predecessor'],
            'schema' => 'RAOS_ST1704_REVIEW_DRAFT_REVISION_OPERATION_V1',
            'successor' => array_intersect_key(
                $input['successor'],
                array_fill_keys($binding_keys, true)
            ),
        );
        $operation_json = self::canonical_ascii_json($operation_material);
        if (! is_string($operation_json)
            || ! hash_equals(
                $input['operation_sha256'],
                hash('sha256', $operation_json)
            )) {
            return self::error('raos_st1704_revision_operation_not_bound', 409);
        }
        return array(
            'article_id' => $input['article_id'],
            'draft_post_id' => $input['draft_post_id'],
            'generation' => $input['generation'],
            'operation' => self::REVISION_OPERATION,
            'operation_sha256' => $input['operation_sha256'],
            'operator_contract_version' => self::OPERATOR_CONTRACT_VERSION,
            'predecessor' => $input['predecessor'],
            'profile_version' => self::PROFILE_VERSION,
            'public_slug' => $input['public_slug'],
            'request_token' => $input['request_token'],
            'site_origin' => self::SITE_ORIGIN,
            'successor' => $input['successor'],
            'ttl_seconds' => self::DEFAULT_TTL,
        );
    }

    private static function fixed_articles()
    {
        return self::bindings_are_exact()
            ? RAOS_ST1704_Publication_Bindings_V2::articles()
            : array();
    }

    private static function fixed_revision_post_ids()
    {
        return self::bindings_are_exact()
            ? RAOS_ST1704_Publication_Bindings_V2::revision_post_ids()
            : array();
    }

    private static function terminal_reconciliation_targets()
    {
        if (! self::bindings_are_exact()) {
            return array();
        }
        $articles = self::fixed_articles();
        $post_ids = self::fixed_revision_post_ids();
        $target_ids = array(
            'st1704-portable-power-station-guide',
            'st1704-anker-solix-c300-c800-c1000-differences',
        );
        $targets = array();
        foreach ($target_ids as $article_id) {
            if (! isset($articles[$article_id], $post_ids[$article_id])
                || ! is_string($articles[$article_id])
                || ! is_int($post_ids[$article_id])) {
                return array();
            }
            $targets[$article_id] = array(
                'article_id' => $article_id,
                'post_id' => $post_ids[$article_id],
                'public_slug' => $articles[$article_id],
            );
        }
        return $targets;
    }

    private static function bindings_are_exact()
    {
        if (! class_exists('RAOS_ST1704_Publication_Bindings_V2', false)
            || RAOS_ST1704_Publication_Bindings_V2::CATEGORY_NAME !== '暮らしの道具'
            || RAOS_ST1704_Publication_Bindings_V2::CATEGORY_CONTRACT
                !== 'KURASHINO_DOGU_SINGLE_V1') {
            return false;
        }
        $articles = RAOS_ST1704_Publication_Bindings_V2::articles();
        $revision_post_ids = RAOS_ST1704_Publication_Bindings_V2::revision_post_ids();
        if (! is_array($articles)
            || count($articles) !== 4
            || ! is_array($revision_post_ids)
            || count($revision_post_ids) !== 4
            || array_keys($revision_post_ids) !== array_keys($articles)
            || count(array_unique(array_values($revision_post_ids))) !== 4
            || isset($articles['st1703-first-suitcase-comparison'])) {
            return false;
        }
        foreach ($articles as $article_id => $slug) {
            if (! is_string($article_id)
                || strpos($article_id, 'st1704-') !== 0
                || ! is_string($slug)
                || ! isset($revision_post_ids[$article_id])
                || ! is_int($revision_post_ids[$article_id])
                || $revision_post_ids[$article_id] < 1
                || preg_match('/\A[a-z0-9]+(?:-[a-z0-9]+)*\z/', $slug) !== 1) {
                return false;
            }
        }
        return true;
    }

    private static function states()
    {
        return array(
            'PROPOSED',
            'APPROVED',
            'APPLYING',
            'APPLIED',
            'FAILED',
            'NEEDS_RECOVERY',
            'EXPIRED',
        );
    }

    private static function unresolved_states()
    {
        // NEEDS_RECOVERY is a terminal, fail-closed receipt. It must remain
        // visible for operator recovery without permanently consuming the
        // single active publication slot.
        return array('PROPOSED', 'APPROVED', 'APPLYING');
    }

    private static function canonical_json($value)
    {
        $normalized = self::sort_for_json($value);
        if ($normalized === null && $value !== null) {
            return null;
        }
        $json = wp_json_encode(
            $normalized,
            JSON_UNESCAPED_SLASHES
                | JSON_UNESCAPED_UNICODE
                | JSON_PRESERVE_ZERO_FRACTION
        );
        return is_string($json) ? $json : null;
    }

    private static function canonical_ascii_json($value)
    {
        $normalized = self::sort_for_json($value);
        if ($normalized === null && $value !== null) {
            return null;
        }
        $json = wp_json_encode(
            $normalized,
            JSON_UNESCAPED_SLASHES | JSON_PRESERVE_ZERO_FRACTION
        );
        return is_string($json) ? $json : null;
    }

    private static function sort_for_json($value)
    {
        if (! is_array($value)) {
            return $value;
        }
        if (self::is_json_list($value)) {
            $result = array();
            foreach ($value as $item) {
                $result[] = self::sort_for_json($item);
            }
            return $result;
        }
        foreach (array_keys($value) as $key) {
            if (! is_string($key)) {
                return null;
            }
        }
        ksort($value, SORT_STRING);
        foreach ($value as $key => $item) {
            $value[$key] = self::sort_for_json($item);
        }
        return $value;
    }

    private static function is_json_list(array $value)
    {
        $expected = 0;
        foreach ($value as $key => $unused) {
            if ($key !== $expected) {
                return false;
            }
            ++$expected;
        }
        return true;
    }

    private static function has_exact_keys($value, array $expected)
    {
        if (! is_array($value)) {
            return false;
        }
        $actual = array_keys($value);
        sort($actual, SORT_STRING);
        sort($expected, SORT_STRING);
        return $actual === $expected;
    }

    private static function iso8601($mysql_utc)
    {
        $epoch = strtotime((string) $mysql_utc . ' UTC');
        return $epoch === false ? '' : gmdate('Y-m-d\TH:i:s\Z', $epoch);
    }

    private static function strict_mysql_utc_epoch($value)
    {
        if (! is_string($value)
            || preg_match(
                '/\A[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01]) '
                . '(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\z/',
                $value
            ) !== 1) {
            return null;
        }
        $epoch = strtotime($value . ' UTC');
        return $epoch !== false && gmdate('Y-m-d H:i:s', $epoch) === $value
            ? $epoch
            : null;
    }

    private function proposal_row($proposal_id)
    {
        global $wpdb;
        $table = self::proposal_table();
        $row = $wpdb->get_row(
            $wpdb->prepare(
                "SELECT proposal_id, operation, request_json, state, created_at,
                        expires_at, proposer_user_id, before_state_json,
                        before_state_hash, approved_by_user_id, approved_at,
                        approval_expires_at, approval_reason,
                        approval_evidence_hash, apply_started_at, completed_at,
                        idempotency_key, result_code, rollback_json,
                        state_version
                 FROM {$table} WHERE proposal_id = %s LIMIT 1",
                $proposal_id
            ),
            ARRAY_A
        );
        if ($wpdb->last_error !== '') {
            return self::error('raos_st1704_proposal_lookup_failed', 500);
        }
        return is_array($row) ? $row : null;
    }

    private function validated_stored_proposal(array $row, $proposal_id)
    {
        if (! isset(
            $row['proposal_id'],
            $row['operation'],
            $row['request_json'],
            $row['state'],
            $row['created_at'],
            $row['expires_at'],
            $row['proposer_user_id'],
            $row['before_state_json'],
            $row['before_state_hash']
        )
            || ! is_string($row['proposal_id'])
            || ! hash_equals($proposal_id, $row['proposal_id'])
            || ! is_string($row['request_json'])
            || ! hash_equals($proposal_id, hash('sha256', $row['request_json']))
            || ! is_string($row['operation'])
            || ! in_array(
                $row['operation'],
                array(self::OPERATION, self::REVISION_OPERATION),
                true
            )
            || ! is_string($row['state'])
            || ! in_array($row['state'], self::states(), true)
            || ! is_string($row['before_state_json'])
            || ! is_string($row['before_state_hash'])
            || preg_match('/\A[a-f0-9]{64}\z/', $row['before_state_hash']) !== 1
            || ! hash_equals(
                $row['before_state_hash'],
                hash('sha256', $row['before_state_json'])
            )) {
            return self::error('raos_st1704_proposal_record_invalid', 409);
        }
        $created_epoch = self::strict_mysql_utc_epoch($row['created_at']);
        $expires_epoch = self::strict_mysql_utc_epoch($row['expires_at']);
        if (! is_int($created_epoch)
            || ! is_int($expires_epoch)
            || $expires_epoch - $created_epoch !== self::DEFAULT_TTL
            || (! is_int($row['proposer_user_id'])
                && (! is_string($row['proposer_user_id'])
                    || preg_match('/\A[1-9][0-9]*\z/', $row['proposer_user_id']) !== 1))) {
            return self::error('raos_st1704_proposal_record_invalid', 409);
        }
        $decoded = json_decode($row['request_json'], true, 16, JSON_BIGINT_AS_STRING);
        $normalized = is_array($decoded)
            ? $this->normalize_proposal_request($decoded)
            : self::error('raos_st1704_proposal_record_invalid', 409);
        if (is_wp_error($normalized)
            || self::canonical_json($normalized) !== $row['request_json']) {
            return self::error('raos_st1704_proposal_record_invalid', 409);
        }
        $before_state = json_decode(
            $row['before_state_json'],
            true,
            32,
            JSON_BIGINT_AS_STRING
        );
        if (! is_array($before_state)
            || self::canonical_json($before_state) !== $row['before_state_json']) {
            return self::error('raos_st1704_proposal_record_invalid', 409);
        }
        return array('request' => $normalized, 'before_state' => $before_state);
    }

    private function validated_proposal_response(
        array $row,
        $proposal_id,
        $canonical,
        $replayed,
        $status
    ) {
        $stored = $this->validated_stored_proposal($row, $proposal_id);
        if (is_wp_error($stored)
            || ($canonical !== null
                && (! is_string($canonical)
                    || ! hash_equals($canonical, $row['request_json'])))
            || (int) $row['proposer_user_id'] !== get_current_user_id()) {
            return self::error('raos_st1704_proposal_record_invalid', 409);
        }
        return new WP_REST_Response(
            array(
                'schema' => 'RAOS_ST1704_PUBLICATION_OPERATOR_PROPOSAL_V2',
                'proposal_id' => $row['proposal_id'],
                'operation' => $row['operation'],
                'state' => $row['state'],
                'created_at' => self::iso8601($row['created_at']),
                'expires_at' => self::iso8601($row['expires_at']),
                'replayed' => (bool) $replayed,
            ),
            (int) $status,
            array('ETag' => '"' . $row['proposal_id'] . '"')
        );
    }

    private function publication_mutex_name()
    {
        global $wpdb;
        if (! defined('DB_NAME')
            || ! is_string(DB_NAME)
            || DB_NAME === ''
            || ! is_string($wpdb->prefix)
            || $wpdb->prefix === '') {
            return null;
        }
        $scope = DB_NAME . "\n" . $wpdb->prefix . "\n"
            . self::SITE_ORIGIN . "\n" . self::MUTEX_PURPOSE;
        return 'raos_pub_v2_' . substr(hash('sha256', $scope), 0, 48);
    }

    private function acquire_publication_mutex($mutex_name)
    {
        global $wpdb;
        if (! is_string($mutex_name)
            || preg_match('/\Araos_pub_v2_[a-f0-9]{48}\z/', $mutex_name) !== 1) {
            return false;
        }
        $owner = $wpdb->get_var(
            $wpdb->prepare('SELECT IS_USED_LOCK(%s)', $mutex_name)
        );
        if ($wpdb->last_error !== '' || $owner !== null) {
            return false;
        }
        $acquired = $wpdb->get_var(
            $wpdb->prepare('SELECT GET_LOCK(%s, 0)', $mutex_name)
        );
        return $wpdb->last_error === '' && (string) $acquired === '1';
    }

    private function publication_mutex_is_owned($mutex_name)
    {
        global $wpdb;
        if (! is_string($mutex_name)) {
            return false;
        }
        $owned = $wpdb->get_var(
            $wpdb->prepare(
                'SELECT (IS_USED_LOCK(%s) = CONNECTION_ID())',
                $mutex_name
            )
        );
        return $wpdb->last_error === '' && (string) $owned === '1';
    }

    private function release_publication_mutex($mutex_name)
    {
        global $wpdb;
        if (! $this->publication_mutex_is_owned($mutex_name)) {
            return false;
        }
        $released = $wpdb->get_var(
            $wpdb->prepare('SELECT RELEASE_LOCK(%s)', $mutex_name)
        );
        return $wpdb->last_error === '' && (string) $released === '1';
    }

    private function strict_count($value)
    {
        global $wpdb;
        if ($wpdb->last_error !== ''
            || (! is_int($value)
                && (! is_string($value)
                    || preg_match('/\A(?:0|[1-9][0-9]*)\z/', $value) !== 1))) {
            return null;
        }
        $count = (int) $value;
        return $count >= 0 ? $count : null;
    }

    private function expire_due_proposals_under_mutex($mutex_name)
    {
        global $wpdb;
        if (! $this->publication_mutex_is_owned($mutex_name)
            || $wpdb->query('START TRANSACTION') === false) {
            return false;
        }
        $table = self::proposal_table();
        $now = gmdate('Y-m-d H:i:s');
        $rows = $wpdb->get_col(
            $wpdb->prepare(
                "SELECT proposal_id FROM {$table}
                 WHERE state IN (%s,%s) AND expires_at <= %s
                 ORDER BY internal_id ASC FOR UPDATE",
                'PROPOSED',
                'APPROVED',
                $now
            )
        );
        if ($wpdb->last_error !== '' || ! is_array($rows)) {
            $wpdb->query('ROLLBACK');
            return false;
        }
        foreach ($rows as $expired_id) {
            if (! is_string($expired_id)
                || preg_match('/\A[a-f0-9]{64}\z/', $expired_id) !== 1) {
                $wpdb->query('ROLLBACK');
                return false;
            }
            $updated = $wpdb->query(
                $wpdb->prepare(
                    "UPDATE {$table} SET state = %s, result_code = %s,
                     completed_at = %s, state_version = state_version + 1
                     WHERE proposal_id = %s AND state IN (%s,%s)
                       AND expires_at <= %s",
                    'EXPIRED',
                    'PROPOSAL_EXPIRED',
                    $now,
                    $expired_id,
                    'PROPOSED',
                    'APPROVED',
                    $now
                )
            );
            if ($updated !== 1
                || ! is_string(self::append_audit(
                    'PROPOSAL_EXPIRED',
                    $expired_id,
                    'EXPIRED',
                    get_current_user_id()
                ))) {
                $wpdb->query('ROLLBACK');
                return false;
            }
        }
        if (! $this->publication_mutex_is_owned($mutex_name)
            || $wpdb->query('COMMIT') === false) {
            $wpdb->query('ROLLBACK');
            return false;
        }
        return true;
    }

    private function create_proposal_under_mutex(
        array $normalized,
        $canonical,
        $proposal_id,
        $mutex_name
    ) {
        global $wpdb;
        if (! $this->publication_mutex_is_owned($mutex_name)
            || ! $this->expire_due_proposals_under_mutex($mutex_name)) {
            return self::error('raos_st1704_publication_lock_lost', 500);
        }
        $existing = $this->proposal_row($proposal_id);
        if (is_wp_error($existing)) {
            return $existing;
        }
        if (is_array($existing)) {
            return $this->validated_proposal_response(
                $existing,
                $proposal_id,
                $canonical,
                true,
                201
            );
        }
        $table = self::proposal_table();
        $total = $this->strict_count(
            $wpdb->get_var("SELECT COUNT(*) FROM {$table}")
        );
        $unresolved = $this->strict_count(
            $wpdb->get_var(
                $wpdb->prepare(
                    "SELECT COUNT(*) FROM {$table}
                     WHERE state IN (%s,%s,%s)",
                    'PROPOSED',
                    'APPROVED',
                    'APPLYING'
                )
            )
        );
        if (! is_int($total) || ! is_int($unresolved)) {
            return self::error('raos_st1704_capacity_check_failed', 500);
        }
        if ($total >= self::MAX_PROPOSAL_ROWS) {
            return self::error('raos_st1704_proposal_capacity_reached', 429);
        }
        if ($unresolved !== 0) {
            return self::error('raos_st1704_unresolved_proposal_exists', 409);
        }
        $before_state = $this->capture_operation_state($normalized);
        if (is_wp_error($before_state)) {
            return $before_state;
        }
        $before_json = self::canonical_json($before_state);
        if (! is_string($before_json)
            || ! $this->publication_mutex_is_owned($mutex_name)) {
            return self::error('raos_st1704_before_state_invalid', 409);
        }
        $created_epoch = time();
        $created_at = gmdate('Y-m-d H:i:s', $created_epoch);
        $expires_at = gmdate(
            'Y-m-d H:i:s',
            $created_epoch + self::DEFAULT_TTL
        );
        if ($wpdb->query('START TRANSACTION') === false
            || ! $this->publication_mutex_is_owned($mutex_name)) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_st1704_transaction_unavailable', 500);
        }
        $inserted = $wpdb->insert(
            $table,
            array(
                'proposal_id' => $proposal_id,
                'operation' => $normalized['operation'],
                'request_json' => $canonical,
                'state' => 'PROPOSED',
                'created_at' => $created_at,
                'expires_at' => $expires_at,
                'proposer_user_id' => get_current_user_id(),
                'before_state_json' => $before_json,
                'before_state_hash' => hash('sha256', $before_json),
                'state_version' => 1,
            ),
            array('%s', '%s', '%s', '%s', '%s', '%s', '%d', '%s', '%s', '%d')
        );
        $audit_hash = $inserted === 1
            ? self::append_audit(
                'PROPOSAL_CREATED',
                $proposal_id,
                'PROPOSED',
                get_current_user_id()
            )
            : false;
        if ($inserted !== 1
            || ! is_string($audit_hash)
            || ! $this->publication_mutex_is_owned($mutex_name)
            || $wpdb->query('COMMIT') === false) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_st1704_proposal_store_failed', 500);
        }
        return $this->validated_proposal_response(
            array(
                'proposal_id' => $proposal_id,
                'operation' => $normalized['operation'],
                'request_json' => $canonical,
                'state' => 'PROPOSED',
                'created_at' => $created_at,
                'expires_at' => $expires_at,
                'proposer_user_id' => get_current_user_id(),
                'before_state_json' => $before_json,
                'before_state_hash' => hash('sha256', $before_json),
            ),
            $proposal_id,
            $canonical,
            false,
            201
        );
    }

    private static function expected_article_section($article_id)
    {
        $sections = array(
            'st1704-anker-solix-c300-c800-c1000-differences' => '備え',
            'st1704-compact-robot-vacuum-shortlist' => '家事',
            'st1704-countertop-dishwasher-for-small-households' => '家事',
            'st1704-portable-power-station-guide' => '備え',
        );
        return isset($sections[$article_id]) ? $sections[$article_id] : null;
    }

    private static function clean_snapshot_text($value, $minimum, $maximum)
    {
        if (! is_string($value)
            || $value === ''
            || $value !== trim($value)
            || strlen($value) > $maximum * 4
            || preg_match('/[\x00-\x1F\x7F]/u', $value) === 1
            || wp_strip_all_tags($value) !== $value) {
            return false;
        }
        $characters = preg_match_all('/./us', $value, $unused);
        return is_int($characters)
            && $characters >= $minimum
            && $characters <= $maximum;
    }

    private static function parse_snapshot($raw)
    {
        if (! is_string($raw)
            || $raw === ''
            || strlen($raw) > self::SNAPSHOT_MAX_BYTES
            || strpos($raw, "\0") !== false) {
            return null;
        }
        $wrapper = json_decode($raw, true, 16, JSON_BIGINT_AS_STRING);
        if (json_last_error() !== JSON_ERROR_NONE
            || ! self::has_exact_keys(
                $wrapper,
                array('schema', 'payload', 'payload_sha256')
            )
            || $wrapper['schema'] !== self::SNAPSHOT_SCHEMA
            || ! is_string($wrapper['payload_sha256'])
            || preg_match('/\A[a-f0-9]{64}\z/', $wrapper['payload_sha256']) !== 1
            || self::canonical_json($wrapper) !== $raw) {
            return null;
        }
        $payload = $wrapper['payload'];
        $keys = array(
            'article_id',
            'author_name',
            'canonical_url',
            'description',
            'modified_at',
            'og_description',
            'og_title',
            'packet_sha256',
            'published_at',
            'section',
            'seo_title',
            'slug',
            'title',
            'visible_content_sha256',
        );
        if (! self::has_exact_keys($payload, $keys)) {
            return null;
        }
        $payload_json = self::canonical_json($payload);
        if (! is_string($payload_json)
            || ! hash_equals(
                $wrapper['payload_sha256'],
                hash('sha256', $payload_json)
            )
            || ! is_string($payload['article_id'])
            || ! is_string($payload['slug'])
            || ! is_string($payload['section'])
            || self::expected_article_section($payload['article_id'])
                !== $payload['section']
            || $payload['canonical_url']
                !== self::SITE_ORIGIN . '/' . $payload['slug'] . '/'
            || $payload['author_name'] !== '暮らしのしるべ編集部'
            || ! self::clean_snapshot_text($payload['title'], 8, 100)
            || ! self::clean_snapshot_text($payload['seo_title'], 8, 100)
            || ! self::clean_snapshot_text($payload['description'], 30, 180)
            || $payload['og_title'] !== $payload['title']
            || $payload['og_description'] !== $payload['description']
            || ! is_string($payload['packet_sha256'])
            || preg_match('/\A[a-f0-9]{64}\z/', $payload['packet_sha256']) !== 1
            || ! is_string($payload['visible_content_sha256'])
            || preg_match('/\A[a-f0-9]{64}\z/', $payload['visible_content_sha256']) !== 1
            || $payload['published_at'] !== null
            || $payload['modified_at'] !== null) {
            return null;
        }
        return array(
            'payload' => $payload,
            'payload_json' => $payload_json,
            'payload_sha256' => $wrapper['payload_sha256'],
            'raw' => $raw,
        );
    }

    private function resolve_exact_category()
    {
        global $wpdb;
        $rows = $wpdb->get_results(
            $wpdb->prepare(
                "SELECT t.term_id, tt.term_taxonomy_id
                 FROM {$wpdb->terms} AS t
                 INNER JOIN {$wpdb->term_taxonomy} AS tt
                    ON tt.term_id = t.term_id
                 WHERE BINARY t.name = BINARY %s
                   AND BINARY tt.taxonomy = BINARY %s
                 ORDER BY tt.term_taxonomy_id ASC",
                RAOS_ST1704_Publication_Bindings_V2::CATEGORY_NAME,
                'category'
            ),
            ARRAY_A
        );
        if ($wpdb->last_error !== ''
            || ! is_array($rows)
            || count($rows) !== 1
            || ! isset($rows[0]['term_id'], $rows[0]['term_taxonomy_id'])
            || preg_match('/\A[1-9][0-9]*\z/', (string) $rows[0]['term_id']) !== 1
            || preg_match('/\A[1-9][0-9]*\z/', (string) $rows[0]['term_taxonomy_id']) !== 1) {
            return self::error('raos_st1704_category_not_exact', 409);
        }
        return array(
            'term_id' => (int) $rows[0]['term_id'],
            'term_taxonomy_id' => (int) $rows[0]['term_taxonomy_id'],
        );
    }

    private static function encoded_pair($key, $value)
    {
        return array(
            'key_base64' => base64_encode((string) $key),
            'value_base64' => base64_encode((string) $value),
        );
    }

    private static function canonical_hash($value)
    {
        $json = self::canonical_json($value);
        return is_string($json) ? hash('sha256', $json) : null;
    }

    private static function post_field_names()
    {
        return array(
            'post_author',
            'post_date',
            'post_date_gmt',
            'post_content',
            'post_title',
            'post_excerpt',
            'post_status',
            'comment_status',
            'ping_status',
            'post_password',
            'post_name',
            'to_ping',
            'pinged',
            'post_modified',
            'post_modified_gmt',
            'post_content_filtered',
            'post_parent',
            'guid',
            'menu_order',
            'post_type',
            'post_mime_type',
            'comment_count',
        );
    }

    private function capture_post_storage(
        $post_id,
        array $category,
        $for_update = false,
        $revision_mutable_fields = false
    )
    {
        global $wpdb;
        if (! is_bool($for_update) || ! is_bool($revision_mutable_fields)) {
            return self::error('raos_st1704_draft_not_exact', 409);
        }
        $lock_clause = $for_update ? ' FOR UPDATE' : '';
        $post_columns = self::post_field_names();
        $post = $wpdb->get_row(
            $wpdb->prepare(
                'SELECT ID, ' . implode(', ', $post_columns)
                . " FROM {$wpdb->posts} WHERE ID = %d LIMIT 1{$lock_clause}",
                $post_id
            ),
            ARRAY_A
        );
        if ($wpdb->last_error !== ''
            || ! is_array($post)
            || ! isset($post['ID'])
            || (int) $post['ID'] !== $post_id
            || count($post) !== count($post_columns) + 1) {
            return self::error('raos_st1704_draft_not_exact', 409);
        }
        $restore_fields = array();
        foreach ($post_columns as $column) {
            if (! array_key_exists($column, $post)
                || ! is_string($post[$column])) {
                return self::error('raos_st1704_draft_not_exact', 409);
            }
            $restore_fields[$column] = base64_encode($post[$column]);
        }
        $protected_fields = $restore_fields;
        $mutable_columns = array(
            'post_date',
            'post_date_gmt',
            'post_modified',
            'post_modified_gmt',
            'post_status',
            'post_name',
        );
        if ($revision_mutable_fields) {
            $mutable_columns = array_merge(
                $mutable_columns,
                array('post_content', 'post_excerpt', 'post_title')
            );
        }
        foreach ($mutable_columns as $mutable_column) {
            unset($protected_fields[$mutable_column]);
        }

        $meta_query = $wpdb->get_results(
            $wpdb->prepare(
                "SELECT meta_key, meta_value FROM {$wpdb->postmeta}
                 WHERE post_id = %d ORDER BY meta_id ASC{$lock_clause}",
                $post_id
            ),
            ARRAY_A
        );
        if ($wpdb->last_error !== ''
            || ! is_array($meta_query)
            || count($meta_query) > self::MAX_META_ROWS) {
            return self::error('raos_st1704_meta_state_unreadable', 409);
        }
        $meta_rows = array();
        $snapshot_values = array();
        $thumbnail_values = array();
        $other_meta = array();
        foreach ($meta_query as $meta_row) {
            if (! is_array($meta_row)
                || ! isset($meta_row['meta_key'], $meta_row['meta_value'])
                || ! is_string($meta_row['meta_key'])
                || ! is_string($meta_row['meta_value'])) {
                return self::error('raos_st1704_meta_state_unreadable', 409);
            }
            $pair = self::encoded_pair(
                $meta_row['meta_key'],
                $meta_row['meta_value']
            );
            $meta_rows[] = $pair;
            if ($meta_row['meta_key'] === self::SNAPSHOT_META_KEY) {
                $snapshot_values[] = $meta_row['meta_value'];
            } elseif ($meta_row['meta_key'] === '_thumbnail_id') {
                $thumbnail_values[] = $meta_row['meta_value'];
            } else {
                $other_meta[] = $pair;
            }
        }
        $sort_pairs = function ($left, $right) {
            $key_order = strcmp($left['key_base64'], $right['key_base64']);
            return $key_order !== 0
                ? $key_order
                : strcmp($left['value_base64'], $right['value_base64']);
        };
        usort($meta_rows, $sort_pairs);
        usort($other_meta, $sort_pairs);
        if (count($snapshot_values) !== 1
            || count($thumbnail_values) > 1
            || (count($thumbnail_values) === 1
                && preg_match('/\A[1-9][0-9]*\z/', $thumbnail_values[0]) !== 1)) {
            return self::error('raos_st1704_meta_state_invalid', 409);
        }

        $relationship_query = $wpdb->get_results(
            $wpdb->prepare(
                "SELECT tr.term_taxonomy_id, tr.term_order, tt.taxonomy
                 FROM {$wpdb->term_relationships} AS tr
                 INNER JOIN {$wpdb->term_taxonomy} AS tt
                    ON tt.term_taxonomy_id = tr.term_taxonomy_id
                 WHERE tr.object_id = %d
                 ORDER BY tr.term_taxonomy_id ASC, tr.term_order ASC
                 {$lock_clause}",
                $post_id
            ),
            ARRAY_A
        );
        if ($wpdb->last_error !== ''
            || ! is_array($relationship_query)
            || count($relationship_query) > self::MAX_TERM_RELATIONSHIPS) {
            return self::error('raos_st1704_taxonomy_state_unreadable', 409);
        }
        $relationships = array();
        $category_relationships = array();
        $other_taxonomy = array();
        foreach ($relationship_query as $relationship) {
            if (! is_array($relationship)
                || ! isset(
                    $relationship['term_taxonomy_id'],
                    $relationship['term_order'],
                    $relationship['taxonomy']
                )
                || preg_match(
                    '/\A[1-9][0-9]*\z/',
                    (string) $relationship['term_taxonomy_id']
                ) !== 1
                || preg_match(
                    '/\A(?:0|[1-9][0-9]*)\z/',
                    (string) $relationship['term_order']
                ) !== 1
                || ! is_string($relationship['taxonomy'])
                || $relationship['taxonomy'] === '') {
                return self::error('raos_st1704_taxonomy_state_invalid', 409);
            }
            $entry = array(
                'term_order' => (int) $relationship['term_order'],
                'term_taxonomy_id' => (int) $relationship['term_taxonomy_id'],
            );
            $relationships[] = $entry;
            if ($relationship['taxonomy'] === 'category') {
                $category_relationships[] = $entry;
            } else {
                $other_taxonomy[] = array(
                    'taxonomy_base64' => base64_encode($relationship['taxonomy']),
                    'term_order' => $entry['term_order'],
                    'term_taxonomy_id' => $entry['term_taxonomy_id'],
                );
            }
        }
        $category_ids = array();
        foreach ($category_relationships as $entry) {
            $category_ids[] = $entry['term_taxonomy_id'];
        }
        sort($category_ids, SORT_NUMERIC);
        $summary = array(
            'all_meta_sha256' => self::canonical_hash($meta_rows),
            'all_taxonomy_sha256' => self::canonical_hash($relationships),
            'category_relationship_sha256' => self::canonical_hash(
                $category_relationships
            ),
            'category_term_taxonomy_ids' => $category_ids,
            'content_sha256' => hash('sha256', $post['post_content']),
            'excerpt_sha256' => hash('sha256', $post['post_excerpt']),
            'featured_media_id' => count($thumbnail_values) === 1
                ? (int) $thumbnail_values[0]
                : 0,
            'other_meta_sha256' => self::canonical_hash($other_meta),
            'other_taxonomy_sha256' => self::canonical_hash($other_taxonomy),
            'post_id' => $post_id,
            'protected_post_fields_sha256' => self::canonical_hash(
                $protected_fields
            ),
            'slug' => $post['post_name'],
            'snapshot_meta_sha256' => hash('sha256', $snapshot_values[0]),
            'status' => $post['post_status'],
            'thumbnail_meta_sha256' => self::canonical_hash(
                array_map(
                    function ($value) {
                        return base64_encode($value);
                    },
                    $thumbnail_values
                )
            ),
            'title_sha256' => hash('sha256', $post['post_title']),
        );
        foreach ($summary as $key => $value) {
            if (substr($key, -7) === '_sha256' && ! is_string($value)) {
                return self::error('raos_st1704_state_hash_failed', 500);
            }
        }
        return array(
            'category_target_term_id' => $category['term_id'],
            'category_target_term_taxonomy_id' => $category['term_taxonomy_id'],
            'restore' => array(
                'meta_rows' => $meta_rows,
                'post_fields' => $restore_fields,
                'term_relationships' => $relationships,
            ),
            'snapshot_raw' => $snapshot_values[0],
            'summary' => $summary,
        );
    }

    private function capture_publication_state(array $proposal)
    {
        global $wpdb;
        $category = $this->resolve_exact_category();
        if (is_wp_error($category)) {
            return $category;
        }
        $storage = $this->capture_post_storage(
            $proposal['draft_post_id'],
            $category
        );
        if (is_wp_error($storage)) {
            return $storage;
        }
        $summary = $storage['summary'];
        $snapshot = self::parse_snapshot($storage['snapshot_raw']);
        $review_slug = 'raos-review-' . $proposal['public_slug'] . '-'
            . $proposal['snapshot_payload_sha256'];
        if (! is_array($snapshot)
            || $summary['status'] !== 'draft'
            || $summary['slug'] !== $review_slug
            || $snapshot['payload']['article_id'] !== $proposal['article_id']
            || $snapshot['payload']['slug'] !== $proposal['public_slug']
            || $snapshot['payload']['packet_sha256'] !== $proposal['packet_sha256']
            || $snapshot['payload']['visible_content_sha256']
                !== $proposal['visible_content_sha256']
            || $snapshot['payload_sha256']
                !== $proposal['snapshot_payload_sha256']
            || $summary['title_sha256']
                !== hash('sha256', $snapshot['payload']['title'])
            || $summary['excerpt_sha256']
                !== hash('sha256', $snapshot['payload']['description'])
            || $summary['content_sha256']
                !== $snapshot['payload']['visible_content_sha256']) {
            return self::error('raos_st1704_snapshot_not_bound', 409);
        }
        $request_material = self::canonical_json(
            array(
                'body' => array(
                    'content' => base64_decode(
                        $storage['restore']['post_fields']['post_content'],
                        true
                    ),
                    'excerpt' => base64_decode(
                        $storage['restore']['post_fields']['post_excerpt'],
                        true
                    ),
                    'meta' => array(self::SNAPSHOT_META_KEY => $storage['snapshot_raw']),
                    'slug' => $review_slug,
                    'status' => 'draft',
                    'title' => base64_decode(
                        $storage['restore']['post_fields']['post_title'],
                        true
                    ),
                ),
                'origin' => self::SITE_ORIGIN,
                'path' => self::REVIEW_REQUEST_PATH,
            )
        );
        if (! is_string($request_material)
            || ! hash_equals(
                $proposal['request_sha256'],
                hash('sha256', $request_material)
            )) {
            return self::error('raos_st1704_request_not_bound', 409);
        }
        $conflicts = $this->strict_count(
            $wpdb->get_var(
                $wpdb->prepare(
                    "SELECT COUNT(*) FROM {$wpdb->posts}
                     WHERE ID <> %d AND BINARY post_name = BINARY %s",
                    $proposal['draft_post_id'],
                    $proposal['public_slug']
                )
            )
        );
        if (! is_int($conflicts) || $conflicts !== 0) {
            return self::error('raos_st1704_public_slug_not_unique', 409);
        }
        return array(
            'article_id' => $proposal['article_id'],
            'category_contract' => RAOS_ST1704_Publication_Bindings_V2::CATEGORY_CONTRACT,
            'category_name' => RAOS_ST1704_Publication_Bindings_V2::CATEGORY_NAME,
            'category_term_id' => $category['term_id'],
            'category_term_taxonomy_id' => $category['term_taxonomy_id'],
            'draft_post_id' => $proposal['draft_post_id'],
            'packet_sha256' => $proposal['packet_sha256'],
            'public_slug' => $proposal['public_slug'],
            'request_sha256' => $proposal['request_sha256'],
            'review_slug' => $review_slug,
            'snapshot_payload_sha256' => $proposal['snapshot_payload_sha256'],
            'storage' => $storage,
            'visible_content_sha256' => $proposal['visible_content_sha256'],
        );
    }

    private function capture_operation_state(array $proposal, $for_update = false)
    {
        return isset($proposal['operation'])
            && $proposal['operation'] === self::REVISION_OPERATION
            ? $this->capture_revision_state($proposal, $for_update)
            : $this->capture_publication_state($proposal);
    }

    private function capture_revision_state(
        array $proposal,
        $for_update = false,
        $require_successor_unique = true
    )
    {
        global $wpdb;
        $category = $this->resolve_exact_category();
        if (is_wp_error($category)) {
            return $category;
        }
        $fixed_ids = self::fixed_revision_post_ids();
        if (! isset($fixed_ids[$proposal['article_id']])
            || $fixed_ids[$proposal['article_id']] !== $proposal['draft_post_id']) {
            return self::error('raos_st1704_revision_post_not_bound', 409);
        }
        $storage = $this->capture_post_storage(
            $proposal['draft_post_id'],
            $category,
            $for_update,
            true
        );
        if (is_wp_error($storage)) {
            return $storage;
        }
        $summary = $storage['summary'];
        $snapshot = self::parse_snapshot($storage['snapshot_raw']);
        $predecessor = $proposal['predecessor'];
        if (! is_array($snapshot)
            || $summary['status'] !== 'draft'
            || $summary['slug'] !== $predecessor['review_slug']
            || $snapshot['payload']['article_id'] !== $proposal['article_id']
            || $snapshot['payload']['slug'] !== $proposal['public_slug']
            || $snapshot['payload']['packet_sha256']
                !== $predecessor['packet_sha256']
            || $snapshot['payload']['visible_content_sha256']
                !== $predecessor['content_sha256']
            || $snapshot['payload_sha256'] !== $predecessor['payload_sha256']
            || $summary['title_sha256']
                !== hash('sha256', $snapshot['payload']['title'])
            || $summary['excerpt_sha256']
                !== hash('sha256', $snapshot['payload']['description'])
            || $summary['content_sha256'] !== $predecessor['content_sha256']) {
            return self::error('raos_st1704_revision_predecessor_changed', 409);
        }
        $request_material = self::canonical_json(
            array(
                'body' => array(
                    'content' => base64_decode(
                        $storage['restore']['post_fields']['post_content'],
                        true
                    ),
                    'excerpt' => base64_decode(
                        $storage['restore']['post_fields']['post_excerpt'],
                        true
                    ),
                    'meta' => array(
                        self::SNAPSHOT_META_KEY => $storage['snapshot_raw'],
                    ),
                    'slug' => $predecessor['review_slug'],
                    'status' => 'draft',
                    'title' => base64_decode(
                        $storage['restore']['post_fields']['post_title'],
                        true
                    ),
                ),
                'origin' => self::SITE_ORIGIN,
                'path' => self::REVIEW_REQUEST_PATH,
            )
        );
        if (! is_string($request_material)
            || ! hash_equals(
                $predecessor['request_sha256'],
                hash('sha256', $request_material)
            )) {
            return self::error('raos_st1704_revision_predecessor_changed', 409);
        }
        if ($require_successor_unique) {
            $slug_lock_clause = $for_update ? ' FOR UPDATE' : '';
            $successor_slug_conflict = $wpdb->get_var(
                $wpdb->prepare(
                    "SELECT ID FROM {$wpdb->posts}
                     WHERE ID <> %d AND BINARY post_name = BINARY %s
                     ORDER BY ID ASC LIMIT 1{$slug_lock_clause}",
                    $proposal['draft_post_id'],
                    $proposal['successor']['review_slug']
                )
            );
            if ($wpdb->last_error !== '' || $successor_slug_conflict !== null) {
                return self::error('raos_st1704_revision_slug_not_unique', 409);
            }
        }
        return array(
            'article_id' => $proposal['article_id'],
            'draft_post_id' => $proposal['draft_post_id'],
            'generation' => $proposal['generation'],
            'operation_sha256' => $proposal['operation_sha256'],
            'predecessor' => $predecessor,
            'public_slug' => $proposal['public_slug'],
            'storage' => $storage,
        );
    }

    private function revision_before_state_matches(
        array $proposal,
        array $before,
        $for_update = false,
        $require_successor_unique = true
    ) {
        $current = $this->capture_revision_state(
            $proposal,
            $for_update,
            $require_successor_unique
        );
        if (is_wp_error($current)) {
            return false;
        }
        $current_json = self::canonical_json($current);
        $before_json = self::canonical_json($before);
        return is_string($current_json)
            && is_string($before_json)
            && hash_equals($before_json, $current_json);
    }

    private function revision_state_matches_successor(
        array $proposal,
        array $before,
        array $expected_modified_times = array(),
        $for_update = false
    ) {
        global $wpdb;
        $category = $this->resolve_exact_category();
        if (is_wp_error($category)) {
            return false;
        }
        $current = $this->capture_post_storage(
            $proposal['draft_post_id'],
            $category,
            $for_update,
            true
        );
        if (is_wp_error($current)) {
            return false;
        }
        $successor = $proposal['successor'];
        $content = self::decode_canonical_base64(
            $successor['content_base64'],
            self::REVISION_CONTENT_MAX_BYTES
        );
        $excerpt = self::decode_canonical_base64(
            $successor['excerpt_base64'],
            2400
        );
        $title = self::decode_canonical_base64(
            $successor['title_base64'],
            1200
        );
        $snapshot_raw = self::decode_canonical_base64(
            $successor['snapshot_base64'],
            self::SNAPSHOT_MAX_BYTES
        );
        $snapshot = is_string($snapshot_raw)
            ? self::parse_snapshot($snapshot_raw)
            : null;
        if (! is_string($content)
            || ! is_string($excerpt)
            || ! is_string($title)
            || ! is_string($snapshot_raw)
            || ! is_array($snapshot)) {
            return false;
        }
        $old = $before['storage']['summary'];
        $new = $current['summary'];
        foreach (
            array(
                'all_taxonomy_sha256',
                'category_relationship_sha256',
                'category_term_taxonomy_ids',
                'featured_media_id',
                'other_meta_sha256',
                'other_taxonomy_sha256',
                'post_id',
                'protected_post_fields_sha256',
                'thumbnail_meta_sha256',
            ) as $preserved
        ) {
            if (! array_key_exists($preserved, $old)
                || ! array_key_exists($preserved, $new)
                || $old[$preserved] !== $new[$preserved]) {
                return false;
            }
        }
        foreach (array('post_date', 'post_date_gmt') as $date_field) {
            $old_value = self::decode_exact_base64(
                $before['storage']['restore']['post_fields'][$date_field]
            );
            $new_value = self::decode_exact_base64(
                $current['restore']['post_fields'][$date_field]
            );
            if (! is_string($old_value)
                || ! is_string($new_value)
                || ! hash_equals($old_value, $new_value)) {
                return false;
            }
        }
        if ($expected_modified_times !== array()) {
            foreach (array('post_modified', 'post_modified_gmt') as $field) {
                $observed = self::decode_exact_base64(
                    $current['restore']['post_fields'][$field]
                );
                if (! isset($expected_modified_times[$field])
                    || ! is_string($observed)
                    || ! hash_equals($expected_modified_times[$field], $observed)) {
                    return false;
                }
            }
        }
        $slug_conflicts = $this->strict_count(
            $wpdb->get_var(
                $wpdb->prepare(
                    "SELECT COUNT(*) FROM {$wpdb->posts}
                     WHERE ID <> %d AND BINARY post_name = BINARY %s",
                    $proposal['draft_post_id'],
                    $successor['review_slug']
                )
            )
        );
        $request_material = self::canonical_json(
            array(
                'body' => array(
                    'content' => $content,
                    'excerpt' => $excerpt,
                    'meta' => array(self::SNAPSHOT_META_KEY => $snapshot_raw),
                    'slug' => $successor['review_slug'],
                    'status' => 'draft',
                    'title' => $title,
                ),
                'origin' => self::SITE_ORIGIN,
                'path' => self::REVIEW_REQUEST_PATH,
            )
        );
        return is_int($slug_conflicts)
            && $slug_conflicts === 0
            && $new['status'] === 'draft'
            && $new['slug'] === $successor['review_slug']
            && $new['content_sha256'] === $successor['content_sha256']
            && $new['title_sha256'] === hash('sha256', $title)
            && $new['excerpt_sha256'] === hash('sha256', $excerpt)
            && $new['snapshot_meta_sha256'] === hash('sha256', $snapshot_raw)
            && $snapshot['payload']['article_id'] === $proposal['article_id']
            && $snapshot['payload']['slug'] === $proposal['public_slug']
            && $snapshot['payload']['packet_sha256']
                === $successor['packet_sha256']
            && $snapshot['payload_sha256'] === $successor['payload_sha256']
            && $snapshot['payload']['visible_content_sha256']
                === $successor['content_sha256']
            && is_string($request_material)
            && hash_equals(
                $successor['request_sha256'],
                hash('sha256', $request_material)
            );
    }

    public function register_admin_page()
    {
        add_management_page(
            'RAOS ST-1704 Publication Approvals',
            'RAOS ST-1704 Publication',
            'manage_options',
            self::ADMIN_PAGE,
            array($this, 'render_admin_page')
        );
    }

    public function render_admin_page()
    {
        if (! is_user_logged_in() || ! current_user_can('manage_options')) {
            wp_die(
                esc_html('You do not have permission to access this page.'),
                '',
                array('response' => 403)
            );
        }
        global $wpdb;
        $table = self::proposal_table();
        $rows = $wpdb->get_results(
            $wpdb->prepare(
                "SELECT proposal_id, operation, request_json, state, created_at,
                        expires_at, proposer_user_id, before_state_json,
                        before_state_hash
                 FROM {$table}
                 WHERE state = %s AND expires_at > %s
                 ORDER BY internal_id ASC LIMIT 2",
                'PROPOSED',
                gmdate('Y-m-d H:i:s')
            ),
            ARRAY_A
        );
        $row = $wpdb->last_error === ''
            && is_array($rows)
            && count($rows) === 1
            ? $rows[0]
            : null;
        ?>
        <div class="wrap">
            <h1><?php echo esc_html('RAOS ST-1704 Bounded Operation Approval'); ?></h1>
            <p><?php echo esc_html('Approval binds one exact Review Draft and one exact operation.'); ?></p>
            <?php if (! self::writes_enabled()) : ?>
                <div class="notice notice-warning"><p><?php
                    echo esc_html('Both the master and ST-1704 publication write gates must be strict true.');
                ?></p></div>
            <?php endif; ?>
            <?php if (! is_array($row)) : ?>
                <p><?php echo esc_html('No single unexpired proposal is available for approval.'); ?></p>
            <?php else : ?>
                <?php
                $proposal_id = (string) $row['proposal_id'];
                $stored = preg_match('/\A[a-f0-9]{64}\z/', $proposal_id) === 1
                    ? $this->validated_stored_proposal($row, $proposal_id)
                    : self::error('raos_st1704_proposal_record_invalid', 409);
                ?>
                <?php if (is_wp_error($stored)) : ?>
                    <p><?php echo esc_html('The proposal record is invalid; do not approve it.'); ?></p>
                <?php else : ?>
                    <?php $spec = $stored['request']; ?>
                    <dl>
                        <dt><?php echo esc_html('Operation'); ?></dt>
                        <dd><code><?php echo esc_html($spec['operation']); ?></code></dd>
                        <dt><?php echo esc_html('Article ID'); ?></dt>
                        <dd><code><?php echo esc_html($spec['article_id']); ?></code></dd>
                        <dt><?php echo esc_html('Draft post ID'); ?></dt>
                        <dd><code><?php echo esc_html((string) $spec['draft_post_id']); ?></code></dd>
                        <dt><?php echo esc_html('Final public slug'); ?></dt>
                        <dd><code><?php echo esc_html($spec['public_slug']); ?></code></dd>
                        <dt><?php echo esc_html('Proposal ID'); ?></dt>
                        <dd><code><?php echo esc_html($proposal_id); ?></code></dd>
                        <?php if ($spec['operation'] === self::REVISION_OPERATION) : ?>
                            <dt><?php echo esc_html('Generation'); ?></dt>
                            <dd><code><?php echo esc_html((string) $spec['generation']); ?></code></dd>
                            <dt><?php echo esc_html('Revision operation SHA-256'); ?></dt>
                            <dd><code><?php echo esc_html($spec['operation_sha256']); ?></code></dd>
                            <dt><?php echo esc_html('Predecessor request SHA-256'); ?></dt>
                            <dd><code><?php echo esc_html($spec['predecessor']['request_sha256']); ?></code></dd>
                            <dt><?php echo esc_html('Successor request SHA-256'); ?></dt>
                            <dd><code><?php echo esc_html($spec['successor']['request_sha256']); ?></code></dd>
                            <dt><?php echo esc_html('Successor packet SHA-256'); ?></dt>
                            <dd><code><?php echo esc_html($spec['successor']['packet_sha256']); ?></code></dd>
                            <dt><?php echo esc_html('Successor snapshot SHA-256'); ?></dt>
                            <dd><code><?php echo esc_html($spec['successor']['payload_sha256']); ?></code></dd>
                            <dt><?php echo esc_html('Successor content SHA-256'); ?></dt>
                            <dd><code><?php echo esc_html($spec['successor']['content_sha256']); ?></code></dd>
                        <?php else : ?>
                            <dt><?php echo esc_html('Existing single category'); ?></dt>
                            <dd><code><?php echo esc_html(RAOS_ST1704_Publication_Bindings_V2::CATEGORY_NAME); ?></code></dd>
                            <dt><?php echo esc_html('Packet SHA-256'); ?></dt>
                            <dd><code><?php echo esc_html($spec['packet_sha256']); ?></code></dd>
                            <dt><?php echo esc_html('Review request SHA-256'); ?></dt>
                            <dd><code><?php echo esc_html($spec['request_sha256']); ?></code></dd>
                            <dt><?php echo esc_html('Snapshot payload SHA-256'); ?></dt>
                            <dd><code><?php echo esc_html($spec['snapshot_payload_sha256']); ?></code></dd>
                            <dt><?php echo esc_html('Visible content SHA-256'); ?></dt>
                            <dd><code><?php echo esc_html($spec['visible_content_sha256']); ?></code></dd>
                        <?php endif; ?>
                        <dt><?php echo esc_html('Complete pre-state SHA-256'); ?></dt>
                        <dd><code><?php echo esc_html($row['before_state_hash']); ?></code></dd>
                        <dt><?php echo esc_html('Expires (UTC)'); ?></dt>
                        <dd><code><?php echo esc_html($row['expires_at']); ?></code></dd>
                    </dl>
                    <p><?php echo esc_html(
                        $spec['operation'] === self::REVISION_OPERATION
                            ? 'Only the fixed Draft title, excerpt, content, review slug, snapshot, and modified timestamps may change; post ID and Draft status remain fixed.'
                            : 'Only draft→publish, review slug→final slug, one existing category assignment, and unavoidable WordPress publication timestamps are permitted.'
                    ); ?></p>
                    <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                        <input type="hidden" name="action" value="<?php echo esc_attr(self::APPROVAL_ACTION); ?>">
                        <input type="hidden" name="proposal_id" value="<?php echo esc_attr($proposal_id); ?>">
                        <?php wp_nonce_field(self::APPROVAL_ACTION . '|' . $proposal_id); ?>
                        <p><label><?php echo esc_html('Reason (10–300 characters)'); ?><br>
                            <textarea name="approval_reason" rows="3" cols="72" minlength="10" maxlength="300" required></textarea>
                        </label></p>
                        <p><label><?php echo esc_html('Final 12 characters of proposal ID'); ?><br>
                            <input name="hash_confirmation" type="text" minlength="12" maxlength="12" autocomplete="off" required>
                        </label></p>
                        <p><label><?php echo esc_html('Current WordPress password'); ?><br>
                            <input name="current_password" type="password" autocomplete="current-password" required>
                        </label></p>
                        <?php submit_button('Approve exact bounded proposal', 'primary', 'submit', false); ?>
                    </form>
                <?php endif; ?>
            <?php endif; ?>
            <?php $this->render_terminal_reconciliation_tools(); ?>
        </div>
        <?php
    }

    public function handle_approval()
    {
        if (! isset($_SERVER['REQUEST_METHOD'])
            || $_SERVER['REQUEST_METHOD'] !== 'POST') {
            wp_die(esc_html('Approval method rejected.'), '', array('response' => 405));
        }
        if (! self::runtime_origin_is_exact() || ! self::writes_enabled()) {
            wp_die(esc_html('Publication writes are disabled.'), '', array('response' => 503));
        }
        if (! is_user_logged_in()
            || ! current_user_can('manage_options')
            || ! function_exists('wp_get_session_token')
            || wp_get_session_token() === '') {
            wp_die(esc_html('Approval authentication failed.'), '', array('response' => 403));
        }
        $proposal_id = isset($_POST['proposal_id'])
            ? sanitize_text_field(wp_unslash($_POST['proposal_id']))
            : '';
        if (! is_string($proposal_id)
            || preg_match('/\A[a-f0-9]{64}\z/', $proposal_id) !== 1) {
            wp_die(esc_html('The proposal is invalid.'), '', array('response' => 400));
        }
        check_admin_referer(self::APPROVAL_ACTION . '|' . $proposal_id);

        $reason_input = isset($_POST['approval_reason'])
            ? wp_unslash($_POST['approval_reason'])
            : '';
        if (! is_string($reason_input)
            || strlen($reason_input) > self::MAX_REASON_BYTES
            || wp_check_invalid_utf8($reason_input) !== $reason_input
            || preg_match('//u', $reason_input) !== 1) {
            wp_die(esc_html('The approval evidence is invalid.'), '', array('response' => 400));
        }
        $reason = sanitize_textarea_field($reason_input);
        if (wp_check_invalid_utf8($reason) !== $reason
            || preg_match('/\A.{10,300}\z/us', $reason) !== 1) {
            wp_die(esc_html('The approval evidence is invalid.'), '', array('response' => 400));
        }
        $confirmation = isset($_POST['hash_confirmation'])
            ? sanitize_text_field(wp_unslash($_POST['hash_confirmation']))
            : '';
        $reauthentication_input = isset($_POST['current_password'])
            ? wp_unslash($_POST['current_password'])
            : '';
        if (! is_string($confirmation)
            || ! hash_equals(substr($proposal_id, -12), $confirmation)
            || ! is_string($reauthentication_input)
            || strlen($reauthentication_input) > self::MAX_PASSWORD_BYTES) {
            wp_die(esc_html('The approval evidence is invalid.'), '', array('response' => 400));
        }
        $approver = wp_get_current_user();
        $password_valid = $approver instanceof WP_User
            && $approver->exists()
            && wp_check_password(
                $reauthentication_input,
                $approver->user_pass,
                $approver->ID
            );
        unset($reauthentication_input);
        if (! $password_valid) {
            wp_die(esc_html('Password reauthentication failed.'), '', array('response' => 403));
        }

        $row = $this->proposal_row($proposal_id);
        $stored = is_array($row)
            ? $this->validated_stored_proposal($row, $proposal_id)
            : self::error('raos_st1704_proposal_not_found', 404);
        if (is_wp_error($stored)
            || $row['state'] !== 'PROPOSED'
            || self::strict_mysql_utc_epoch($row['expires_at']) <= time()
            || (int) $row['proposer_user_id'] === (int) $approver->ID) {
            wp_die(esc_html('The proposal cannot be approved.'), '', array('response' => 409));
        }
        $current_state = $this->capture_operation_state($stored['request']);
        $current_json = is_wp_error($current_state)
            ? null
            : self::canonical_json($current_state);
        if (! is_string($current_json)
            || ! hash_equals($row['before_state_json'], $current_json)
            || ! hash_equals($row['before_state_hash'], hash('sha256', $current_json))) {
            wp_die(esc_html('The Review Draft changed before approval.'), '', array('response' => 409));
        }

        $approved_at = gmdate('Y-m-d H:i:s');
        $approval_material = self::canonical_json(
            array(
                'approval_expires_at' => $row['expires_at'],
                'approved_at' => $approved_at,
                'approved_by_user_id' => (int) $approver->ID,
                'normalized_reason' => $reason,
                'proposal_id' => $proposal_id,
            )
        );
        if (! is_string($approval_material)) {
            wp_die(esc_html('Approval evidence could not be bound.'), '', array('response' => 500));
        }
        global $wpdb;
        $table = self::proposal_table();
        if ($wpdb->query('START TRANSACTION') === false) {
            wp_die(esc_html('Approval transaction unavailable.'), '', array('response' => 500));
        }
        $updated = $wpdb->query(
            $wpdb->prepare(
                "UPDATE {$table}
                 SET state = %s, approved_by_user_id = %d, approved_at = %s,
                     approval_expires_at = %s, approval_reason = %s,
                     approval_evidence_hash = %s,
                     state_version = state_version + 1
                 WHERE proposal_id = %s AND state = %s
                   AND proposer_user_id <> %d AND before_state_hash = %s
                   AND expires_at > %s",
                'APPROVED',
                $approver->ID,
                $approved_at,
                $row['expires_at'],
                $reason,
                hash('sha256', $approval_material),
                $proposal_id,
                'PROPOSED',
                $approver->ID,
                $row['before_state_hash'],
                gmdate('Y-m-d H:i:s')
            )
        );
        $audit_hash = $updated === 1
            ? self::append_audit(
                'HUMAN_APPROVED',
                $proposal_id,
                'APPROVED',
                $approver->ID
            )
            : false;
        if ($updated !== 1
            || ! is_string($audit_hash)
            || $wpdb->query('COMMIT') === false) {
            $wpdb->query('ROLLBACK');
            wp_die(esc_html('Approval persistence failed.'), '', array('response' => 500));
        }
        wp_safe_redirect(
            add_query_arg(
                array('page' => self::ADMIN_PAGE, 'raos_st1704_notice' => 'approved'),
                admin_url('tools.php')
            )
        );
        exit;
    }

    private function approval_evidence_is_valid(
        array $row,
        $proposal_id,
        $require_unexpired
    ) {
        if (! isset(
            $row['proposer_user_id'],
            $row['approved_by_user_id'],
            $row['approved_at'],
            $row['approval_expires_at'],
            $row['approval_reason'],
            $row['approval_evidence_hash']
        )
            || (int) $row['approved_by_user_id'] < 1
            || (int) $row['approved_by_user_id'] === (int) $row['proposer_user_id']
            || ! is_string($row['approved_at'])
            || ! is_string($row['approval_expires_at'])
            || ! is_string($row['approval_reason'])
            || strlen($row['approval_reason']) > self::MAX_REASON_BYTES
            || preg_match('/\A.{10,300}\z/us', $row['approval_reason']) !== 1
            || ! is_string($row['approval_evidence_hash'])
            || preg_match('/\A[a-f0-9]{64}\z/', $row['approval_evidence_hash']) !== 1) {
            return false;
        }
        $approved_epoch = self::strict_mysql_utc_epoch($row['approved_at']);
        $approval_expiry = self::strict_mysql_utc_epoch(
            $row['approval_expires_at']
        );
        $proposal_expiry = self::strict_mysql_utc_epoch($row['expires_at']);
        if (! is_int($approved_epoch)
            || ! is_int($approval_expiry)
            || ! is_int($proposal_expiry)
            || $approved_epoch > $approval_expiry
            || $approval_expiry !== $proposal_expiry
            || ($require_unexpired && $approval_expiry <= time())) {
            return false;
        }
        $material = self::canonical_json(
            array(
                'approval_expires_at' => $row['approval_expires_at'],
                'approved_at' => $row['approved_at'],
                'approved_by_user_id' => (int) $row['approved_by_user_id'],
                'normalized_reason' => $row['approval_reason'],
                'proposal_id' => $proposal_id,
            )
        );
        return is_string($material)
            && hash_equals(
                $row['approval_evidence_hash'],
                hash('sha256', $material)
            );
    }

    private function render_terminal_reconciliation_tools()
    {
        ?>
        <hr>
        <h2><?php echo esc_html('Incident-bound redirect metadata reconciliation'); ?></h2>
        <p><?php echo esc_html(
            'This admin-only workflow is limited to the two fixed terminal publication incidents. It never changes a proposal receipt or adds a REST authority.'
        ); ?></p>
        <?php
        $notice = isset($_GET['raos_st1704_reconciliation_notice'])
            ? sanitize_key(wp_unslash($_GET['raos_st1704_reconciliation_notice']))
            : '';
        if (in_array($notice, array('cleanup_complete', 'public_confirmed'), true)) :
            ?>
            <div class="notice notice-success"><p><?php echo esc_html(
                $notice === 'cleanup_complete'
                    ? 'The exact redirect metadata cleanup is recorded.'
                    : 'The owner-private public verification evidence is recorded.'
            ); ?></p></div>
            <?php
        endif;
        if (! self::reconciliation_writes_enabled()) :
            ?>
            <div class="notice notice-warning"><p><?php echo esc_html(
                'Reconciliation requires the master gate strict true, the publication gate strict false, and the dedicated reconciliation gate strict true.'
            ); ?></p></div>
            <?php
            return;
        endif;
        $targets = self::terminal_reconciliation_targets();
        if (count($targets) !== 2) :
            ?>
            <p><?php echo esc_html('The fixed reconciliation allowlist is invalid.'); ?></p>
            <?php
            return;
        endif;
        foreach ($targets as $target) :
            $plan = $this->preview_terminal_reconciliation(
                $target['article_id']
            );
            ?>
            <h3><code><?php echo esc_html($target['article_id']); ?></code></h3>
            <?php if (is_wp_error($plan)) : ?>
                <p><?php echo esc_html(
                    'No single exact terminal candidate with an unambiguous locked state is available.'
                ); ?></p>
                <?php
                $diagnostic_code = self::terminal_reconciliation_diagnostic_code(
                    $plan
                );
                ?>
                <p><?php echo esc_html('Administrator diagnostic code:'); ?>
                    <code><?php echo esc_html($diagnostic_code); ?></code>
                </p>
                <?php continue; ?>
            <?php endif; ?>
            <dl>
                <dt><?php echo esc_html('Post ID'); ?></dt>
                <dd><code><?php echo esc_html((string) $target['post_id']); ?></code></dd>
                <dt><?php echo esc_html('Terminal proposal assertion'); ?></dt>
                <dd><code><?php echo esc_html($plan['proposal_id']); ?></code></dd>
                <dt><?php echo esc_html('Cleanup operation SHA-256'); ?></dt>
                <dd><code><?php echo esc_html($plan['operation_sha256']); ?></code></dd>
                <dt><?php echo esc_html('Reconciliation stage'); ?></dt>
                <dd><code><?php echo esc_html($plan['stage']); ?></code></dd>
            </dl>
            <?php if ($plan['stage'] === 'CLEANUP_REQUIRED') : ?>
                <p><?php echo esc_html(
                    'The transaction will delete only the exact locked WordPress redirect metadata rows bound by this operation hash. The terminal proposal receipt remains unchanged.'
                ); ?></p>
                <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                    <input type="hidden" name="action" value="<?php echo esc_attr(self::RECONCILIATION_CLEANUP_ACTION); ?>">
                    <input type="hidden" name="proposal_id" value="<?php echo esc_attr($plan['proposal_id']); ?>">
                    <input type="hidden" name="operation_sha256" value="<?php echo esc_attr($plan['operation_sha256']); ?>">
                    <?php wp_nonce_field(
                        self::RECONCILIATION_CLEANUP_ACTION . '|'
                            . $plan['proposal_id'] . '|'
                            . $plan['operation_sha256']
                    ); ?>
                    <p><label><?php echo esc_html('Reason (10–300 characters)'); ?><br>
                        <textarea name="reconciliation_reason" rows="3" cols="72" minlength="10" maxlength="300" required></textarea>
                    </label></p>
                    <p><label><?php echo esc_html('Final 12 characters of cleanup operation SHA-256'); ?><br>
                        <input name="hash_confirmation" type="text" minlength="12" maxlength="12" autocomplete="off" required>
                    </label></p>
                    <p><label><?php echo esc_html('Current WordPress password'); ?><br>
                        <input name="current_password" type="password" autocomplete="current-password" required>
                    </label></p>
                    <?php submit_button(
                        'Reconcile exact redirect metadata rows',
                        'primary',
                        'submit',
                        false
                    ); ?>
                </form>
            <?php elseif ($plan['stage'] === 'CLEANED') : ?>
                <p><?php echo esc_html(
                    'After producing and retaining the owner-private external verification artifact, the administrator may attest its SHA-256 here. This form does not inspect or validate arbitrary HTTP content.'
                ); ?></p>
                <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                    <input type="hidden" name="action" value="<?php echo esc_attr(self::RECONCILIATION_CONFIRM_ACTION); ?>">
                    <input type="hidden" name="proposal_id" value="<?php echo esc_attr($plan['proposal_id']); ?>">
                    <input type="hidden" name="operation_sha256" value="<?php echo esc_attr($plan['operation_sha256']); ?>">
                    <?php wp_nonce_field(
                        self::RECONCILIATION_CONFIRM_ACTION . '|'
                            . $plan['proposal_id'] . '|'
                            . $plan['operation_sha256']
                    ); ?>
                    <p><label><?php echo esc_html('Owner-private verification evidence SHA-256'); ?><br>
                        <input name="verification_evidence_sha256" type="text" minlength="64" maxlength="64" autocomplete="off" required>
                    </label></p>
                    <p><label><?php echo esc_html('Reason (10–300 characters)'); ?><br>
                        <textarea name="reconciliation_reason" rows="3" cols="72" minlength="10" maxlength="300" required></textarea>
                    </label></p>
                    <p><label><?php echo esc_html('Final 12 characters of cleanup operation SHA-256'); ?><br>
                        <input name="hash_confirmation" type="text" minlength="12" maxlength="12" autocomplete="off" required>
                    </label></p>
                    <p><label><?php echo esc_html('Current WordPress password'); ?><br>
                        <input name="current_password" type="password" autocomplete="current-password" required>
                    </label></p>
                    <?php submit_button(
                        'Record owner-private public verification evidence',
                        'primary',
                        'submit',
                        false
                    ); ?>
                </form>
            <?php else : ?>
                <p><?php echo esc_html(
                    'The redirect metadata cleanup and one owner-private verification evidence hash are already recorded.'
                ); ?></p>
            <?php endif; ?>
            <?php
        endforeach;
    }

    private static function terminal_reconciliation_diagnostic_code($error)
    {
        $fallback = 'raos_st1704_reconciliation_preview_unavailable';
        if (! is_wp_error($error)) {
            return $fallback;
        }
        $code = $error->get_error_code();
        $allowed = array(
            'raos_st1704_reconciliation_allowlist_invalid',
            'raos_st1704_reconciliation_assertion_invalid',
            'raos_st1704_reconciliation_audit_invalid',
            'raos_st1704_reconciliation_candidate_ambiguous',
            'raos_st1704_reconciliation_candidate_failure_code_mismatch',
            'raos_st1704_reconciliation_candidate_invalid',
            'raos_st1704_reconciliation_candidate_missing',
            'raos_st1704_reconciliation_core_delete_prestate',
            'raos_st1704_reconciliation_dates_invalid',
            'raos_st1704_reconciliation_disabled',
            'raos_st1704_reconciliation_hash_invalid',
            'raos_st1704_reconciliation_lock_lost',
            'raos_st1704_reconciliation_lock_unavailable',
            'raos_st1704_reconciliation_meta_ambiguous',
            'raos_st1704_reconciliation_meta_duplicate',
            'raos_st1704_reconciliation_meta_extra',
            'raos_st1704_reconciliation_meta_invalid',
            'raos_st1704_reconciliation_meta_missing',
            'raos_st1704_reconciliation_operation_invalid',
            'raos_st1704_reconciliation_post_invalid',
            'raos_st1704_reconciliation_post_locked',
            'raos_st1704_reconciliation_receipt_invalid',
            'raos_st1704_reconciliation_runtime_invalid',
            'raos_st1704_reconciliation_slug_conflict',
            'raos_st1704_reconciliation_state_ambiguous',
            'raos_st1704_reconciliation_state_invalid',
            'raos_st1704_reconciliation_target_invalid',
        );
        return is_string($code) && in_array($code, $allowed, true)
            ? $code
            : $fallback;
    }

    private function preview_terminal_reconciliation($article_id)
    {
        $targets = self::terminal_reconciliation_targets();
        if (! self::reconciliation_writes_enabled()
            || ! current_user_can('publish_posts')
            || ! isset($targets[$article_id])
            || ! current_user_can('edit_post', $targets[$article_id]['post_id'])) {
            return self::error('raos_st1704_reconciliation_disabled', 503);
        }
        $mutex_name = $this->publication_mutex_name();
        if (! $this->acquire_publication_mutex($mutex_name)) {
            return self::error('raos_st1704_reconciliation_lock_unavailable', 409);
        }
        global $wpdb;
        $plan = self::error('raos_st1704_reconciliation_state_invalid', 409);
        try {
            if ($wpdb->query(
                'SET TRANSACTION ISOLATION LEVEL SERIALIZABLE'
            ) !== false
                && $wpdb->query('START TRANSACTION') !== false
                && $this->publication_mutex_is_owned($mutex_name)) {
                $plan = $this->terminal_reconciliation_plan_for_target(
                    $article_id,
                    $mutex_name
                );
            }
            $wpdb->query('ROLLBACK');
        } catch (Throwable $exception) {
            $wpdb->query('ROLLBACK');
            $plan = self::error(
                'raos_st1704_reconciliation_state_invalid',
                409
            );
        }
        if (! $this->release_publication_mutex($mutex_name)) {
            return self::error('raos_st1704_reconciliation_lock_lost', 500);
        }
        if (is_wp_error($plan)) {
            return $plan;
        }
        return array(
            'operation_sha256' => $plan['operation_sha256'],
            'proposal_id' => $plan['proposal_id'],
            'stage' => $plan['stage'],
        );
    }

    private function reconciliation_submission_authentication(
        $action,
        $proposal_id,
        $operation_sha256
    ) {
        if (! isset($_SERVER['REQUEST_METHOD'])
            || $_SERVER['REQUEST_METHOD'] !== 'POST'
            || ! self::runtime_origin_is_exact()
            || ! self::reconciliation_writes_enabled()) {
            return self::error('raos_st1704_reconciliation_disabled', 503);
        }
        if (! is_string($action)
            || ! in_array(
                $action,
                array(
                    self::RECONCILIATION_CLEANUP_ACTION,
                    self::RECONCILIATION_CONFIRM_ACTION,
                ),
                true
            )
            || ! is_string($proposal_id)
            || preg_match('/\A[a-f0-9]{64}\z/', $proposal_id) !== 1
            || ! is_string($operation_sha256)
            || preg_match('/\A[a-f0-9]{64}\z/', $operation_sha256) !== 1
            || ! is_user_logged_in()
            || ! current_user_can('manage_options')
            || ! current_user_can('publish_posts')
            || ! function_exists('wp_get_session_token')
            || wp_get_session_token() === '') {
            return self::error('raos_st1704_reconciliation_auth_failed', 403);
        }
        check_admin_referer(
            $action . '|' . $proposal_id . '|' . $operation_sha256
        );
        $reason_input = isset($_POST['reconciliation_reason'])
            ? wp_unslash($_POST['reconciliation_reason'])
            : '';
        unset($_POST['reconciliation_reason']);
        $confirmation = isset($_POST['hash_confirmation'])
            ? sanitize_text_field(wp_unslash($_POST['hash_confirmation']))
            : '';
        if (! is_string($reason_input)
            || strlen($reason_input) > self::MAX_REASON_BYTES
            || wp_check_invalid_utf8($reason_input) !== $reason_input
            || preg_match('//u', $reason_input) !== 1
            || ! is_string($confirmation)
            || ! hash_equals(substr($operation_sha256, -12), $confirmation)) {
            return self::error('raos_st1704_reconciliation_evidence_invalid', 400);
        }
        $reason = sanitize_textarea_field($reason_input);
        unset($reason_input);
        if (wp_check_invalid_utf8($reason) !== $reason
            || preg_match('/\A.{10,300}\z/us', $reason) !== 1) {
            unset($reason);
            return self::error('raos_st1704_reconciliation_evidence_invalid', 400);
        }
        $password = isset($_POST['current_password'])
            ? wp_unslash($_POST['current_password'])
            : '';
        unset($_POST['current_password']);
        $approver = wp_get_current_user();
        $password_valid = is_string($password)
            && strlen($password) <= self::MAX_PASSWORD_BYTES
            && $approver instanceof WP_User
            && $approver->exists()
            && wp_check_password(
                $password,
                $approver->user_pass,
                $approver->ID
            );
        unset($password);
        unset($reason);
        if (! $password_valid) {
            return self::error('raos_st1704_reconciliation_reauth_failed', 403);
        }
        return $approver;
    }

    private static function reconciliation_submission_diagnostic_code($failure)
    {
        if (! is_user_logged_in()
            || ! current_user_can('manage_options')
            || ! current_user_can('publish_posts')
            || ! function_exists('wp_get_session_token')
            || wp_get_session_token() === '') {
            return '';
        }
        if ($failure === false) {
            return 'raos_st1704_reconciliation_execution_refused';
        }
        if (! is_wp_error($failure)) {
            return '';
        }
        $code = $failure->get_error_code();
        $allowed = array(
            'raos_st1704_reconciliation_auth_failed',
            'raos_st1704_reconciliation_disabled',
            'raos_st1704_reconciliation_evidence_invalid',
            'raos_st1704_reconciliation_reauth_failed',
        );
        return is_string($code) && in_array($code, $allowed, true)
            ? $code
            : 'raos_st1704_reconciliation_authentication_refused';
    }

    private static function reconciliation_cleanup_refusal_message($failure)
    {
        $message = 'The exact redirect metadata reconciliation was refused.';
        $diagnostic_code = self::reconciliation_submission_diagnostic_code(
            $failure
        );
        if ($diagnostic_code !== '') {
            $message .= ' Administrator diagnostic code: ' . $diagnostic_code;
        }
        return $message;
    }

    public function handle_reconciliation_cleanup()
    {
        $proposal_id = isset($_POST['proposal_id'])
            ? sanitize_text_field(wp_unslash($_POST['proposal_id']))
            : '';
        $operation_sha256 = isset($_POST['operation_sha256'])
            ? sanitize_text_field(wp_unslash($_POST['operation_sha256']))
            : '';
        $approver = $this->reconciliation_submission_authentication(
            self::RECONCILIATION_CLEANUP_ACTION,
            $proposal_id,
            $operation_sha256
        );
        if (is_wp_error($approver)) {
            wp_die(
                esc_html(
                    self::reconciliation_cleanup_refusal_message($approver)
                ),
                '',
                array('response' => 409)
            );
        }
        if (! $this->execute_terminal_reconciliation_cleanup(
            $proposal_id,
            $operation_sha256,
            $approver
        )) {
            wp_die(
                esc_html(
                    self::reconciliation_cleanup_refusal_message(false)
                ),
                '',
                array('response' => 409)
            );
        }
        wp_safe_redirect(
            add_query_arg(
                array(
                    'page' => self::ADMIN_PAGE,
                    'raos_st1704_reconciliation_notice' => 'cleanup_complete',
                ),
                admin_url('tools.php')
            )
        );
        exit;
    }

    public function handle_reconciliation_public_confirmation()
    {
        $proposal_id = isset($_POST['proposal_id'])
            ? sanitize_text_field(wp_unslash($_POST['proposal_id']))
            : '';
        $operation_sha256 = isset($_POST['operation_sha256'])
            ? sanitize_text_field(wp_unslash($_POST['operation_sha256']))
            : '';
        $evidence_sha256 = isset($_POST['verification_evidence_sha256'])
            ? sanitize_text_field(
                wp_unslash($_POST['verification_evidence_sha256'])
            )
            : '';
        $approver = $this->reconciliation_submission_authentication(
            self::RECONCILIATION_CONFIRM_ACTION,
            $proposal_id,
            $operation_sha256
        );
        if (is_wp_error($approver)
            || ! is_string($evidence_sha256)
            || preg_match('/\A[a-f0-9]{64}\z/', $evidence_sha256) !== 1
            || ! $this->execute_reconciled_public_confirmation(
                $proposal_id,
                $operation_sha256,
                $evidence_sha256,
                $approver
            )) {
            wp_die(
                esc_html('The public verification evidence was refused.'),
                '',
                array('response' => 409)
            );
        }
        wp_safe_redirect(
            add_query_arg(
                array(
                    'page' => self::ADMIN_PAGE,
                    'raos_st1704_reconciliation_notice' => 'public_confirmed',
                ),
                admin_url('tools.php')
            )
        );
        exit;
    }

    private function execute_terminal_reconciliation_cleanup(
        $proposal_id,
        $operation_sha256,
        WP_User $approver
    ) {
        $mutex_name = $this->publication_mutex_name();
        if (! $this->acquire_publication_mutex($mutex_name)) {
            return false;
        }
        global $wpdb;
        $committed = false;
        $post_id = 0;
        try {
            if ($wpdb->query(
                'SET TRANSACTION ISOLATION LEVEL SERIALIZABLE'
            ) === false
                || $wpdb->query('START TRANSACTION') === false
                || ! $this->publication_mutex_is_owned($mutex_name)) {
                throw new RuntimeException('reconciliation transaction unavailable');
            }
            $plan = $this->terminal_reconciliation_plan_for_assertion(
                $proposal_id,
                $mutex_name
            );
            if (is_wp_error($plan)
                || ! hash_equals(
                    $plan['operation_sha256'],
                    $operation_sha256
                )
                || (int) $plan['proposer_user_id'] === (int) $approver->ID
                || ! current_user_can('edit_post', $plan['post_id'])) {
                throw new RuntimeException('reconciliation assertion changed');
            }
            $post_id = $plan['post_id'];
            if (in_array(
                $plan['stage'],
                array('CLEANED', 'PUBLIC_CONFIRMED'),
                true
            )) {
                $wpdb->query('ROLLBACK');
                $committed = true;
            } elseif ($plan['stage'] === 'CLEANUP_REQUIRED') {
                if (! $this->delete_exact_reconciliation_meta_rows(
                    $plan['delete_rows'],
                    $plan['post_id']
                )) {
                    throw new RuntimeException('reconciliation metadata CAS failed');
                }
                if (! $this->published_state_matches(
                    $plan['proposal'],
                    $plan['before'],
                    $plan['modified_times'],
                    true
                )
                    || ! $this->publication_mutex_is_owned($mutex_name)) {
                    throw new RuntimeException('reconciliation readback changed');
                }
                $audit_hash = self::append_audit(
                    self::RECONCILIATION_CLEANUP_EVENT,
                    $proposal_id,
                    strtoupper($operation_sha256),
                    $approver->ID
                );
                if (! is_string($audit_hash)
                    || ! $this->publication_mutex_is_owned($mutex_name)
                    || $wpdb->query('COMMIT') === false) {
                    throw new RuntimeException('reconciliation receipt failed');
                }
                $committed = true;
            } else {
                throw new RuntimeException('reconciliation stage invalid');
            }
        } catch (Throwable $exception) {
            if (! $committed) {
                $wpdb->query('ROLLBACK');
            }
        }
        $released = $this->release_publication_mutex($mutex_name);
        if ($committed && $post_id > 0) {
            clean_post_cache($post_id);
        }
        return $committed && $released;
    }

    private function delete_exact_reconciliation_meta_rows(
        array $delete_rows,
        $post_id
    ) {
        if (! is_int($post_id)
            || $post_id < 1
            || count($delete_rows) < 1
            || count($delete_rows) > 2) {
            return false;
        }
        global $wpdb;
        foreach ($delete_rows as $meta_row) {
            if (! is_array($meta_row)
                || ! self::has_exact_keys(
                    $meta_row,
                    array('meta_id', 'meta_key', 'meta_value')
                )
                || ! is_int($meta_row['meta_id'])
                || $meta_row['meta_id'] < 1
                || ! is_string($meta_row['meta_key'])
                || ! in_array(
                    $meta_row['meta_key'],
                    array('_wp_old_slug', '_wp_old_date'),
                    true
                )
                || ! is_string($meta_row['meta_value'])) {
                return false;
            }
            $deleted = $wpdb->query(
                $wpdb->prepare(
                    "DELETE FROM {$wpdb->postmeta}
                     WHERE meta_id = %d AND post_id = %d
                       AND BINARY meta_key = BINARY %s
                       AND BINARY meta_value = BINARY %s",
                    $meta_row['meta_id'],
                    $post_id,
                    $meta_row['meta_key'],
                    $meta_row['meta_value']
                )
            );
            if ($deleted !== 1) {
                return false;
            }
        }
        return true;
    }

    private function execute_reconciled_public_confirmation(
        $proposal_id,
        $operation_sha256,
        $evidence_sha256,
        WP_User $approver
    ) {
        $mutex_name = $this->publication_mutex_name();
        if (! $this->acquire_publication_mutex($mutex_name)) {
            return false;
        }
        global $wpdb;
        $committed = false;
        try {
            if ($wpdb->query(
                'SET TRANSACTION ISOLATION LEVEL SERIALIZABLE'
            ) === false
                || $wpdb->query('START TRANSACTION') === false
                || ! $this->publication_mutex_is_owned($mutex_name)) {
                throw new RuntimeException('confirmation transaction unavailable');
            }
            $plan = $this->terminal_reconciliation_plan_for_assertion(
                $proposal_id,
                $mutex_name
            );
            if (is_wp_error($plan)
                || ! hash_equals(
                    $plan['operation_sha256'],
                    $operation_sha256
                )
                || (int) $plan['proposer_user_id'] === (int) $approver->ID
                || ! current_user_can('edit_post', $plan['post_id'])) {
                throw new RuntimeException('confirmation assertion changed');
            }
            if ($plan['stage'] === 'PUBLIC_CONFIRMED') {
                if (! hash_equals(
                    $plan['verification_evidence_sha256'],
                    $evidence_sha256
                )) {
                    throw new RuntimeException('conflicting confirmation refused');
                }
                $wpdb->query('ROLLBACK');
                $committed = true;
            } elseif ($plan['stage'] === 'CLEANED') {
                $audit_hash = self::append_audit(
                    self::RECONCILIATION_PUBLIC_EVENT,
                    $proposal_id,
                    strtoupper($evidence_sha256),
                    $approver->ID
                );
                if (! is_string($audit_hash)
                    || ! $this->publication_mutex_is_owned($mutex_name)
                    || $wpdb->query('COMMIT') === false) {
                    throw new RuntimeException('confirmation receipt failed');
                }
                $committed = true;
            } else {
                throw new RuntimeException('cleanup evidence missing');
            }
        } catch (Throwable $exception) {
            if (! $committed) {
                $wpdb->query('ROLLBACK');
            }
        }
        $released = $this->release_publication_mutex($mutex_name);
        return $committed && $released;
    }

    private function terminal_reconciliation_plan_for_target(
        $article_id,
        $mutex_name
    ) {
        $targets = self::terminal_reconciliation_targets();
        if (! is_string($article_id)
            || ! isset($targets[$article_id])
            || ! $this->publication_mutex_is_owned($mutex_name)) {
            return self::error('raos_st1704_reconciliation_target_invalid', 409);
        }
        $candidates = $this->terminal_reconciliation_candidates_for_update();
        if (is_wp_error($candidates)) {
            return $candidates;
        }
        if (! isset($candidates[$article_id])) {
            return self::error('raos_st1704_reconciliation_candidate_missing', 409);
        }
        $candidate = $candidates[$article_id];
        $result_error = self::terminal_reconciliation_candidate_result_error(
            $candidate
        );
        if (is_wp_error($result_error)) {
            return $result_error;
        }
        return $this->build_terminal_reconciliation_plan(
            $candidate,
            $targets[$article_id],
            $mutex_name
        );
    }

    private static function terminal_reconciliation_candidate_result_error(
        array $candidate
    ) {
        if (! isset($candidate['result_code'])
            || ! is_string($candidate['result_code'])
            || preg_match('/\A[A-Z0-9_]{1,64}\z/', $candidate['result_code']) !== 1) {
            return self::error('raos_st1704_reconciliation_candidate_invalid', 409);
        }
        if (in_array(
            $candidate['result_code'],
            self::terminal_reconciliation_failure_codes(),
            true
        )) {
            return null;
        }
        return self::error(
            'raos_st1704_reconciliation_candidate_failure_code_mismatch',
            409
        );
    }

    private static function terminal_reconciliation_failure_codes()
    {
        return array(
            self::RECONCILIATION_FAILURE_CODE,
            self::RECONCILIATION_EXCEPTION_FAILURE_CODE,
        );
    }

    private function terminal_reconciliation_plan_for_assertion(
        $proposal_id,
        $mutex_name
    ) {
        if (! is_string($proposal_id)
            || preg_match('/\A[a-f0-9]{64}\z/', $proposal_id) !== 1
            || ! $this->publication_mutex_is_owned($mutex_name)) {
            return self::error('raos_st1704_reconciliation_assertion_invalid', 409);
        }
        $targets = self::terminal_reconciliation_targets();
        $candidates = $this->terminal_reconciliation_candidates_for_update();
        if (count($targets) !== 2) {
            return self::error('raos_st1704_reconciliation_allowlist_invalid', 409);
        }
        if (is_wp_error($candidates)) {
            return $candidates;
        }
        $match = null;
        $target = null;
        foreach ($candidates as $article_id => $candidate) {
            if (hash_equals((string) $candidate['proposal_id'], $proposal_id)) {
                if ($match !== null || ! isset($targets[$article_id])) {
                    return self::error(
                        'raos_st1704_reconciliation_candidate_ambiguous',
                        409
                    );
                }
                $match = $candidate;
                $target = $targets[$article_id];
            }
        }
        if (! is_array($match) || ! is_array($target)) {
            return self::error('raos_st1704_reconciliation_candidate_missing', 409);
        }
        $result_error = self::terminal_reconciliation_candidate_result_error(
            $match
        );
        if (is_wp_error($result_error)) {
            return $result_error;
        }
        return $this->build_terminal_reconciliation_plan(
            $match,
            $target,
            $mutex_name
        );
    }

    private function terminal_reconciliation_candidates_for_update()
    {
        global $wpdb;
        $table = self::proposal_table();
        $rows = $wpdb->get_results(
            $wpdb->prepare(
                "SELECT proposal_id, operation, request_json, state, created_at,
                        expires_at, proposer_user_id, before_state_json,
                        before_state_hash, approved_by_user_id, approved_at,
                        approval_expires_at, approval_reason,
                        approval_evidence_hash, apply_started_at, completed_at,
                        idempotency_key, result_code, rollback_json,
                        state_version
                 FROM {$table}
                 WHERE BINARY operation = BINARY %s
                   AND BINARY state = BINARY %s
                 ORDER BY internal_id ASC
                 LIMIT " . (self::MAX_PROPOSAL_ROWS + 1) . ' FOR UPDATE',
                self::OPERATION,
                'NEEDS_RECOVERY'
            ),
            ARRAY_A
        );
        if ($wpdb->last_error !== ''
            || ! is_array($rows)
            || count($rows) > self::MAX_PROPOSAL_ROWS) {
            return self::error('raos_st1704_reconciliation_candidate_invalid', 409);
        }
        $targets = self::terminal_reconciliation_targets();
        if (count($targets) !== 2) {
            return self::error('raos_st1704_reconciliation_allowlist_invalid', 409);
        }
        $result = array();
        foreach ($rows as $row) {
            if (! is_array($row)
                || ! isset($row['proposal_id'])
                || ! is_string($row['proposal_id'])
                || preg_match('/\A[a-f0-9]{64}\z/', $row['proposal_id']) !== 1) {
                return self::error('raos_st1704_reconciliation_candidate_invalid', 409);
            }
            $stored = $this->validated_stored_proposal(
                $row,
                $row['proposal_id']
            );
            if (is_wp_error($stored)) {
                return self::error('raos_st1704_reconciliation_candidate_invalid', 409);
            }
            $article_id = $stored['request']['article_id'];
            if (! isset($targets[$article_id])) {
                continue;
            }
            $target = $targets[$article_id];
            if (isset($result[$article_id])
                || $stored['request']['operation'] !== self::OPERATION
                || $stored['request']['draft_post_id'] !== $target['post_id']
                || $stored['request']['public_slug'] !== $target['public_slug']) {
                return self::error(
                    'raos_st1704_reconciliation_candidate_ambiguous',
                    409
                );
            }
            $row['stored'] = $stored;
            $result[$article_id] = $row;
        }
        return $result;
    }

    private function validate_terminal_reconciliation_receipt(
        array $candidate,
        array $target
    ) {
        if (! isset($candidate['stored'])
            || ! is_array($candidate['stored'])
            || ! isset(
                $candidate['proposal_id'],
                $candidate['operation'],
                $candidate['state'],
                $candidate['result_code'],
                $candidate['idempotency_key'],
                $candidate['rollback_json'],
                $candidate['before_state_json'],
                $candidate['before_state_hash'],
                $candidate['created_at'],
                $candidate['expires_at'],
                $candidate['approved_at'],
                $candidate['approval_expires_at'],
                $candidate['apply_started_at'],
                $candidate['completed_at'],
                $candidate['proposer_user_id'],
                $candidate['approved_by_user_id'],
                $candidate['state_version']
            )) {
            return self::error('raos_st1704_reconciliation_receipt_invalid', 409);
        }
        $proposal_id = $candidate['proposal_id'];
        $stored = $candidate['stored'];
        $proposal = $stored['request'];
        $before = $stored['before_state'];
        $review_slug = 'raos-review-' . $target['public_slug'] . '-'
            . $proposal['snapshot_payload_sha256'];
        $created_epoch = self::strict_mysql_utc_epoch($candidate['created_at']);
        $expires_epoch = self::strict_mysql_utc_epoch($candidate['expires_at']);
        $approved_epoch = self::strict_mysql_utc_epoch($candidate['approved_at']);
        $approval_expiry_epoch = self::strict_mysql_utc_epoch(
            $candidate['approval_expires_at']
        );
        $apply_epoch = self::strict_mysql_utc_epoch(
            $candidate['apply_started_at']
        );
        $completed_epoch = self::strict_mysql_utc_epoch(
            $candidate['completed_at']
        );
        if ($candidate['operation'] !== self::OPERATION
            || $candidate['state'] !== 'NEEDS_RECOVERY'
            || ! in_array(
                $candidate['result_code'],
                self::terminal_reconciliation_failure_codes(),
                true
            )
            || ! is_string($candidate['idempotency_key'])
            || ! hash_equals($proposal_id, $candidate['idempotency_key'])
            || ! is_string($candidate['rollback_json'])
            || ! hash_equals(
                $candidate['before_state_json'],
                $candidate['rollback_json']
            )
            || ! hash_equals(
                $candidate['before_state_hash'],
                hash('sha256', $candidate['rollback_json'])
            )
            || (int) $candidate['state_version'] !== 4
            || ! $this->approval_evidence_is_valid(
                $candidate,
                $proposal_id,
                false
            )
            || ! is_int($created_epoch)
            || ! is_int($expires_epoch)
            || ! is_int($approved_epoch)
            || ! is_int($approval_expiry_epoch)
            || ! is_int($apply_epoch)
            || ! is_int($completed_epoch)
            || $expires_epoch - $created_epoch !== self::DEFAULT_TTL
            || $approval_expiry_epoch !== $expires_epoch
            || $approval_expiry_epoch > time()
            || ! ($created_epoch <= $approved_epoch
                && $approved_epoch <= $apply_epoch
                && $apply_epoch < $approval_expiry_epoch
                && $apply_epoch <= $completed_epoch)
            || (int) $candidate['proposer_user_id'] < 1
            || (int) $candidate['approved_by_user_id'] < 1
            || (int) $candidate['proposer_user_id']
                === (int) $candidate['approved_by_user_id']
            || $proposal['article_id'] !== $target['article_id']
            || $proposal['draft_post_id'] !== $target['post_id']
            || $proposal['public_slug'] !== $target['public_slug']
            || ! isset(
                $before['article_id'],
                $before['draft_post_id'],
                $before['public_slug'],
                $before['review_slug'],
                $before['request_sha256'],
                $before['storage']['summary']['status'],
                $before['storage']['summary']['slug']
            )
            || $before['article_id'] !== $target['article_id']
            || (int) $before['draft_post_id'] !== $target['post_id']
            || $before['public_slug'] !== $target['public_slug']
            || $before['review_slug'] !== $review_slug
            || $before['storage']['summary']['status'] !== 'draft'
            || $before['storage']['summary']['slug'] !== $review_slug
            || ! hash_equals(
                $proposal['request_sha256'],
                $before['request_sha256']
            )) {
            return self::error('raos_st1704_reconciliation_receipt_invalid', 409);
        }
        $modified_times = self::publication_modified_times_from_gmt(
            $candidate['apply_started_at']
        );
        $publication_dates = is_array($modified_times)
            ? self::publication_date_fields($before, $modified_times)
            : false;
        if (! is_array($modified_times) || ! is_array($publication_dates)) {
            return self::error('raos_st1704_reconciliation_dates_invalid', 409);
        }
        $audit = $this->validate_reconciliation_audit_chain(
            $candidate,
            $proposal_id
        );
        if (is_wp_error($audit)) {
            return $audit;
        }
        return array(
            'audit' => $audit,
            'before' => $before,
            'failure_code' => $candidate['result_code'],
            'modified_times' => $modified_times,
            'proposal' => $proposal,
            'publication_dates' => $publication_dates,
        );
    }

    private function validate_reconciliation_audit_chain(
        array $candidate,
        $proposal_id
    ) {
        global $wpdb;
        $table = self::audit_table();
        $rows = $wpdb->get_results(
            "SELECT audit_id, occurred_at, actor_user_id, event_code,
                    proposal_id, detail_code, previous_hash, event_hash
             FROM {$table} ORDER BY audit_id ASC FOR UPDATE",
            ARRAY_A
        );
        if ($wpdb->last_error !== ''
            || ! is_array($rows)
            || count($rows) < 1
            || count($rows) > self::MAX_RECONCILIATION_AUDIT_ROWS) {
            return self::error('raos_st1704_reconciliation_audit_invalid', 409);
        }
        $previous = str_repeat('0', 64);
        $previous_audit_id = 0;
        $proposal_events = array();
        foreach ($rows as $audit_row) {
            $occurred_epoch = is_array($audit_row)
                && isset($audit_row['occurred_at'])
                ? self::strict_mysql_utc_epoch($audit_row['occurred_at'])
                : null;
            if (! is_array($audit_row)
                || ! self::has_exact_keys(
                    $audit_row,
                    array(
                        'actor_user_id',
                        'audit_id',
                        'detail_code',
                        'event_code',
                        'event_hash',
                        'occurred_at',
                        'previous_hash',
                        'proposal_id',
                    )
                )
                || ! is_string($audit_row['audit_id'])
                || preg_match('/\A[1-9][0-9]*\z/', $audit_row['audit_id']) !== 1
                || (int) $audit_row['audit_id'] <= $previous_audit_id
                || ! is_string($audit_row['actor_user_id'])
                || preg_match('/\A(?:0|[1-9][0-9]*)\z/', $audit_row['actor_user_id']) !== 1
                || ! is_string($audit_row['occurred_at'])
                || ! is_int($occurred_epoch)
                || $occurred_epoch > time()
                || ! is_string($audit_row['event_code'])
                || preg_match('/\A[A-Z0-9_]{1,64}\z/', $audit_row['event_code']) !== 1
                || ! is_string($audit_row['proposal_id'])
                || preg_match('/\A[a-f0-9]{64}\z/', $audit_row['proposal_id']) !== 1
                || ! is_string($audit_row['detail_code'])
                || preg_match('/\A[A-Z0-9_]{1,64}\z/', $audit_row['detail_code']) !== 1
                || ! is_string($audit_row['previous_hash'])
                || ! hash_equals($previous, $audit_row['previous_hash'])
                || ! is_string($audit_row['event_hash'])
                || preg_match('/\A[a-f0-9]{64}\z/', $audit_row['event_hash']) !== 1) {
                return self::error('raos_st1704_reconciliation_audit_invalid', 409);
            }
            $material = implode(
                "\n",
                array(
                    $previous,
                    $audit_row['occurred_at'],
                    (string) (int) $audit_row['actor_user_id'],
                    $audit_row['event_code'],
                    $audit_row['proposal_id'],
                    $audit_row['detail_code'],
                )
            );
            if (! hash_equals(
                $audit_row['event_hash'],
                hash('sha256', $material)
            )) {
                return self::error('raos_st1704_reconciliation_audit_invalid', 409);
            }
            $previous = $audit_row['event_hash'];
            $previous_audit_id = (int) $audit_row['audit_id'];
            if (hash_equals($proposal_id, $audit_row['proposal_id'])) {
                $proposal_events[] = $audit_row;
            }
        }
        if (count($proposal_events) < 4 || count($proposal_events) > 6) {
            return self::error('raos_st1704_reconciliation_audit_invalid', 409);
        }
        $expected = array(
            array(
                'actor' => (int) $candidate['proposer_user_id'],
                'detail' => 'PROPOSED',
                'event' => 'PROPOSAL_CREATED',
                'time' => $candidate['created_at'],
            ),
            array(
                'actor' => (int) $candidate['approved_by_user_id'],
                'detail' => 'APPROVED',
                'event' => 'HUMAN_APPROVED',
                'time' => $candidate['approved_at'],
            ),
            array(
                'actor' => (int) $candidate['proposer_user_id'],
                'detail' => 'APPLYING',
                'event' => 'APPLY_STARTED',
                'time' => $candidate['apply_started_at'],
            ),
            array(
                'actor' => (int) $candidate['proposer_user_id'],
                'detail' => $candidate['result_code'],
                'event' => 'APPLY_FAILED',
                'time' => $candidate['completed_at'],
            ),
        );
        foreach ($expected as $index => $shape) {
            $event = $proposal_events[$index];
            $event_epoch = self::strict_mysql_utc_epoch(
                $event['occurred_at']
            );
            $row_epoch = self::strict_mysql_utc_epoch($shape['time']);
            if ($event['event_code'] !== $shape['event']
                || $event['detail_code'] !== $shape['detail']
                || (int) $event['actor_user_id'] !== $shape['actor']
                || ! is_int($event_epoch)
                || ! is_int($row_epoch)
                || $event_epoch < $row_epoch
                || $event_epoch - $row_epoch > 2) {
                return self::error('raos_st1704_reconciliation_audit_invalid', 409);
            }
        }
        $stage = 'CLEANUP_REQUIRED';
        $cleanup_operation_sha256 = null;
        $cleanup_previous_hash = null;
        $verification_evidence_sha256 = null;
        if (isset($proposal_events[4])) {
            $cleanup = $proposal_events[4];
            if ($cleanup['event_code'] !== self::RECONCILIATION_CLEANUP_EVENT
                || preg_match('/\A[A-F0-9]{64}\z/', $cleanup['detail_code']) !== 1
                || (int) $cleanup['actor_user_id'] < 1
                || (int) $cleanup['actor_user_id']
                    === (int) $candidate['proposer_user_id']
                || self::strict_mysql_utc_epoch($cleanup['occurred_at'])
                    < self::strict_mysql_utc_epoch($candidate['completed_at'])) {
                return self::error('raos_st1704_reconciliation_audit_invalid', 409);
            }
            $stage = 'CLEANED';
            $cleanup_operation_sha256 = strtolower($cleanup['detail_code']);
            $cleanup_previous_hash = $cleanup['previous_hash'];
        }
        if (isset($proposal_events[5])) {
            $public = $proposal_events[5];
            if ($stage !== 'CLEANED'
                || $public['event_code'] !== self::RECONCILIATION_PUBLIC_EVENT
                || preg_match('/\A[A-F0-9]{64}\z/', $public['detail_code']) !== 1
                || (int) $public['actor_user_id'] < 1
                || (int) $public['actor_user_id']
                    === (int) $candidate['proposer_user_id']
                || self::strict_mysql_utc_epoch($public['occurred_at'])
                    < self::strict_mysql_utc_epoch(
                        $proposal_events[4]['occurred_at']
                    )) {
                return self::error('raos_st1704_reconciliation_audit_invalid', 409);
            }
            $stage = 'PUBLIC_CONFIRMED';
            $verification_evidence_sha256 = strtolower($public['detail_code']);
        }
        return array(
            'audit_head_sha256' => $previous,
            'cleanup_operation_sha256' => $cleanup_operation_sha256,
            'cleanup_previous_hash' => $cleanup_previous_hash,
            'event_hashes' => array_map(
                function ($event) {
                    return $event['event_hash'];
                },
                $proposal_events
            ),
            'stage' => $stage,
            'verification_evidence_sha256' => $verification_evidence_sha256,
        );
    }

    private function build_terminal_reconciliation_plan(
        array $candidate,
        array $target,
        $mutex_name
    ) {
        if (! self::reconciliation_writes_enabled()
            || ! $this->publication_mutex_is_owned($mutex_name)
            || ! self::publication_core_redirect_callbacks_are_exact()) {
            return self::error('raos_st1704_reconciliation_runtime_invalid', 409);
        }
        $receipt = $this->validate_terminal_reconciliation_receipt(
            $candidate,
            $target
        );
        if (is_wp_error($receipt)) {
            return $receipt;
        }
        require_once ABSPATH . 'wp-admin/includes/post.php';
        if (! function_exists('wp_check_post_lock')
            || wp_check_post_lock($target['post_id']) !== false) {
            return self::error('raos_st1704_reconciliation_post_locked', 409);
        }
        global $wpdb;
        $conflicts = $wpdb->get_col(
            $wpdb->prepare(
                "SELECT ID FROM {$wpdb->posts}
                 WHERE ID <> %d
                   AND (BINARY post_name = BINARY %s
                        OR BINARY post_name = BINARY %s)
                 ORDER BY ID ASC FOR UPDATE",
                $target['post_id'],
                $target['public_slug'],
                $receipt['before']['review_slug']
            )
        );
        if ($wpdb->last_error !== ''
            || ! is_array($conflicts)
            || $conflicts !== array()) {
            return self::error('raos_st1704_reconciliation_slug_conflict', 409);
        }
        $storage = $this->capture_reconciliation_published_storage(
            $receipt['proposal'],
            $receipt['before'],
            $receipt['modified_times']
        );
        if (! is_array($storage)) {
            return self::error('raos_st1704_reconciliation_post_invalid', 409);
        }
        $meta_plan = $this->reconciliation_meta_cleanup_plan(
            $target['post_id'],
            $receipt['proposal'],
            $receipt['before'],
            $receipt['publication_dates'],
            $storage
        );
        if (is_wp_error($meta_plan)) {
            return $meta_plan;
        }
        $audit = $receipt['audit'];
        if ($audit['stage'] === 'CLEANUP_REQUIRED') {
            if ($meta_plan['state'] !== 'EXACT_REDIRECT_EXTRAS') {
                return self::error(
                    'raos_st1704_reconciliation_state_ambiguous',
                    409
                );
            }
            $operation_material = self::canonical_json(
                array(
                    'article_id' => $target['article_id'],
                    'apply_started_at' => $candidate['apply_started_at'],
                    'approval_evidence_sha256' =>
                        $candidate['approval_evidence_hash'],
                    'approved_at' => $candidate['approved_at'],
                    'approved_by_user_id' =>
                        (int) $candidate['approved_by_user_id'],
                    'audit_event_hashes' => $audit['event_hashes'],
                    'audit_head_sha256' => $audit['audit_head_sha256'],
                    'before_meta_multiset_sha256' =>
                        $meta_plan['before_meta_multiset_sha256'],
                    'before_state_sha256' => $candidate['before_state_hash'],
                    'cleanup_rows' => $meta_plan['cleanup_row_digests'],
                    'current_meta_rows_sha256' =>
                        $meta_plan['current_meta_rows_sha256'],
                    'current_published_storage_sha256' =>
                        $meta_plan['current_published_storage_sha256'],
                    'completed_at' => $candidate['completed_at'],
                    'created_at' => $candidate['created_at'],
                    'expected_after_meta_rows_sha256' =>
                        $meta_plan['expected_after_meta_rows_sha256'],
                    'expected_after_meta_multiset_sha256' =>
                        $meta_plan['expected_after_meta_multiset_sha256'],
                    'expected_post_date' =>
                        $receipt['publication_dates']['post_date'],
                    'expected_post_date_gmt' =>
                        $receipt['publication_dates']['post_date_gmt'],
                    'expected_post_modified' =>
                        $receipt['modified_times']['post_modified'],
                    'expected_post_modified_gmt' =>
                        $receipt['modified_times']['post_modified_gmt'],
                    'failure_code' => $receipt['failure_code'],
                    'expires_at' => $candidate['expires_at'],
                    'idempotency_key_sha256' => hash(
                        'sha256',
                        $candidate['idempotency_key']
                    ),
                    'operation' => 'RECONCILE_INCIDENT_REDIRECT_META',
                    'post_id' => $target['post_id'],
                    'proposal_id' => $candidate['proposal_id'],
                    'proposal_state_version' =>
                        (int) $candidate['state_version'],
                    'proposal_state' => $candidate['state'],
                    'proposer_user_id' =>
                        (int) $candidate['proposer_user_id'],
                    'public_slug_sha256' => hash(
                        'sha256',
                        $target['public_slug']
                    ),
                    'request_json_sha256' => hash(
                        'sha256',
                        $candidate['request_json']
                    ),
                    'review_slug_sha256' => hash(
                        'sha256',
                        $receipt['before']['review_slug']
                    ),
                    'rollback_json_sha256' => hash(
                        'sha256',
                        $candidate['rollback_json']
                    ),
                    'schema' => 'RAOS_ST1704_REDIRECT_META_RECONCILIATION_V1',
                    'site_origin' => self::SITE_ORIGIN,
                    'wordpress_release_line' => '7.1.x',
                )
            );
            if (! is_string($operation_material)) {
                return self::error(
                    'raos_st1704_reconciliation_operation_invalid',
                    409
                );
            }
            $operation_sha256 = hash('sha256', $operation_material);
            $stage = 'CLEANUP_REQUIRED';
            $delete_rows = $meta_plan['delete_rows'];
        } else {
            // The cleanup audit row's `previous_hash` is the exact global head
            // used by the pre-cleanup operation material. Deleted meta IDs and
            // values are intentionally not copied into audit storage, so an
            // idempotent replay uses the chain-validated stored operation hash
            // rather than a new hash based on a later global audit head.
            if ($meta_plan['state'] !== 'CLEAN'
                || ! $this->published_state_matches(
                    $receipt['proposal'],
                    $receipt['before'],
                    $receipt['modified_times'],
                    true
                )
                || ! is_string($audit['cleanup_operation_sha256'])
                || preg_match(
                    '/\A[a-f0-9]{64}\z/',
                    $audit['cleanup_operation_sha256']
                ) !== 1
                || ! is_string($audit['cleanup_previous_hash'])
                || preg_match(
                    '/\A[a-f0-9]{64}\z/',
                    $audit['cleanup_previous_hash']
                ) !== 1) {
                return self::error(
                    'raos_st1704_reconciliation_state_ambiguous',
                    409
                );
            }
            $operation_sha256 = $audit['cleanup_operation_sha256'];
            $stage = $audit['stage'];
            $delete_rows = array();
        }
        return array(
            'before' => $receipt['before'],
            'delete_rows' => $delete_rows,
            'modified_times' => $receipt['modified_times'],
            'operation_sha256' => $operation_sha256,
            'post_id' => $target['post_id'],
            'proposal' => $receipt['proposal'],
            'proposal_id' => $candidate['proposal_id'],
            'proposer_user_id' => (int) $candidate['proposer_user_id'],
            'stage' => $stage,
            'verification_evidence_sha256' =>
                $audit['verification_evidence_sha256'],
        );
    }

    private function capture_reconciliation_published_storage(
        array $proposal,
        array $before,
        array $modified_times
    ) {
        if (! isset(
            $before['category_term_id'],
            $before['category_term_taxonomy_id'],
            $before['storage']['summary']
        )) {
            return false;
        }
        $category = $this->resolve_exact_category();
        if (is_wp_error($category)
            || $category['term_id'] !== (int) $before['category_term_id']
            || $category['term_taxonomy_id']
                !== (int) $before['category_term_taxonomy_id']) {
            return false;
        }
        $current = $this->capture_post_storage(
            $proposal['draft_post_id'],
            $category,
            true
        );
        $publication_dates = self::publication_date_fields(
            $before,
            $modified_times
        );
        if (is_wp_error($current) || ! is_array($publication_dates)) {
            return false;
        }
        $fields = $current['restore']['post_fields'];
        $expected_fields = array(
            'post_date' => $publication_dates['post_date'],
            'post_date_gmt' => $publication_dates['post_date_gmt'],
            'post_modified' => $modified_times['post_modified'],
            'post_modified_gmt' => $modified_times['post_modified_gmt'],
        );
        foreach ($expected_fields as $field => $expected) {
            $actual = isset($fields[$field])
                ? self::decode_exact_base64($fields[$field])
                : null;
            if (! is_string($actual) || ! hash_equals($expected, $actual)) {
                return false;
            }
        }
        $old = $before['storage']['summary'];
        $new = $current['summary'];
        foreach (
            array(
                'content_sha256',
                'excerpt_sha256',
                'featured_media_id',
                'other_taxonomy_sha256',
                'post_id',
                'protected_post_fields_sha256',
                'snapshot_meta_sha256',
                'thumbnail_meta_sha256',
                'title_sha256',
            ) as $key
        ) {
            if (! array_key_exists($key, $old)
                || ! array_key_exists($key, $new)
                || $old[$key] !== $new[$key]) {
                return false;
            }
        }
        $category_hash = self::canonical_hash(
            array(
                array(
                    'term_order' => 0,
                    'term_taxonomy_id' =>
                        (int) $before['category_term_taxonomy_id'],
                ),
            )
        );
        if (! is_string($category_hash)
            || $new['status'] !== 'publish'
            || $new['slug'] !== $proposal['public_slug']
            || $new['category_term_taxonomy_ids']
                !== array($category['term_taxonomy_id'])
            || ! hash_equals(
                $category_hash,
                $new['category_relationship_sha256']
            )) {
            return false;
        }
        return $current;
    }

    private function reconciliation_meta_cleanup_plan(
        $post_id,
        array $proposal,
        array $before,
        array $publication_dates,
        array $current_storage
    ) {
        if (! isset(
            $before['review_slug'],
            $before['storage']['restore']['meta_rows'],
            $before['storage']['restore']['post_fields']['post_date']
        )
            || $before['review_slug'] !== 'raos-review-'
                . $proposal['public_slug'] . '-'
                . $proposal['snapshot_payload_sha256']) {
            return self::error('raos_st1704_reconciliation_meta_invalid', 409);
        }
        global $wpdb;
        $rows = $wpdb->get_results(
            $wpdb->prepare(
                "SELECT meta_id, meta_key, meta_value
                 FROM {$wpdb->postmeta}
                 WHERE post_id = %d ORDER BY meta_id ASC FOR UPDATE",
                $post_id
            ),
            ARRAY_A
        );
        if ($wpdb->last_error !== ''
            || ! is_array($rows)
            || count($rows) > self::MAX_META_ROWS) {
            return self::error('raos_st1704_reconciliation_meta_invalid', 409);
        }
        $current_rows = array();
        $buckets = array();
        $last_meta_id = 0;
        foreach ($rows as $index => $row) {
            if (! is_array($row)
                || ! self::has_exact_keys(
                    $row,
                    array('meta_id', 'meta_key', 'meta_value')
                )
                || ! is_string($row['meta_id'])
                || preg_match('/\A[1-9][0-9]*\z/', $row['meta_id']) !== 1
                || (int) $row['meta_id'] <= $last_meta_id
                || ! is_string($row['meta_key'])
                || ! is_string($row['meta_value'])) {
                return self::error('raos_st1704_reconciliation_meta_invalid', 409);
            }
            $last_meta_id = (int) $row['meta_id'];
            $pair = self::encoded_pair($row['meta_key'], $row['meta_value']);
            $pair_key = self::canonical_json($pair);
            if (! is_string($pair_key)) {
                return self::error('raos_st1704_reconciliation_meta_invalid', 409);
            }
            $current_rows[$index] = array(
                'meta_id' => (int) $row['meta_id'],
                'meta_key' => $row['meta_key'],
                'meta_value' => $row['meta_value'],
                'pair' => $pair,
            );
            if (! isset($buckets[$pair_key])) {
                $buckets[$pair_key] = array();
            }
            $buckets[$pair_key][] = $index;
        }
        $before_rows = $before['storage']['restore']['meta_rows'];
        if (! is_array($before_rows) || count($before_rows) > self::MAX_META_ROWS) {
            return self::error('raos_st1704_reconciliation_meta_invalid', 409);
        }
        $matched = array();
        foreach ($before_rows as $before_row) {
            if (! is_array($before_row)
                || ! self::has_exact_keys(
                    $before_row,
                    array('key_base64', 'value_base64')
                )) {
                return self::error('raos_st1704_reconciliation_meta_invalid', 409);
            }
            $pair_key = self::canonical_json($before_row);
            if (! is_string($pair_key)
                || ! isset($buckets[$pair_key])
                || $buckets[$pair_key] === array()) {
                return self::error('raos_st1704_reconciliation_meta_missing', 409);
            }
            $matched[array_shift($buckets[$pair_key])] = true;
        }
        $extras = array();
        foreach ($current_rows as $index => $row) {
            if (! isset($matched[$index])) {
                $extras[] = $row;
            }
        }
        $previous_date_value = self::decode_exact_base64(
            $before['storage']['restore']['post_fields']['post_date']
        );
        if (! is_string($previous_date_value)
            || self::strict_mysql_utc_epoch($previous_date_value) === null
            || ! isset($publication_dates['post_date'])
            || ! is_string($publication_dates['post_date'])) {
            return self::error('raos_st1704_reconciliation_dates_invalid', 409);
        }
        $previous_epoch = strtotime($previous_date_value);
        $published_epoch = strtotime($publication_dates['post_date']);
        if ($previous_epoch === false || $published_epoch === false) {
            return self::error('raos_st1704_reconciliation_dates_invalid', 409);
        }
        $previous_date = gmdate('Y-m-d', $previous_epoch);
        $published_date = gmdate('Y-m-d', $published_epoch);
        $redirect_values = self::publication_redirect_metadata_values($before);
        if (! is_array($redirect_values)
            || in_array(
                $proposal['public_slug'],
                $redirect_values['_wp_old_slug'],
                true
            )
            || ($previous_date !== $published_date
                && in_array(
                    $published_date,
                    $redirect_values['_wp_old_date'],
                    true
                ))
            || in_array(
                $before['review_slug'],
                $redirect_values['_wp_old_slug'],
                true
            )) {
            return self::error(
                'raos_st1704_reconciliation_core_delete_prestate',
                409
            );
        }
        $expected_extras = array(
            array(
                'meta_key' => '_wp_old_slug',
                'meta_value' => $before['review_slug'],
            ),
        );
        if ($previous_date !== $published_date
            && ! in_array(
                $previous_date,
                $redirect_values['_wp_old_date'],
                true
            )) {
            $expected_extras[] = array(
                'meta_key' => '_wp_old_date',
                'meta_value' => $previous_date,
            );
        }
        $delete_rows = array();
        if ($extras !== array()) {
            if (count($extras) !== count($expected_extras)) {
                return self::error('raos_st1704_reconciliation_meta_extra', 409);
            }
            foreach ($expected_extras as $expected) {
                $match_index = null;
                foreach ($extras as $index => $extra) {
                    if ($extra['meta_key'] === $expected['meta_key']
                        && hash_equals(
                            $expected['meta_value'],
                            $extra['meta_value']
                        )) {
                        if ($match_index !== null) {
                            return self::error(
                                'raos_st1704_reconciliation_meta_duplicate',
                                409
                            );
                        }
                        $match_index = $index;
                    }
                }
                if ($match_index === null) {
                    return self::error('raos_st1704_reconciliation_meta_extra', 409);
                }
                $delete_rows[] = $extras[$match_index];
                unset($extras[$match_index]);
            }
            if ($extras !== array()) {
                return self::error('raos_st1704_reconciliation_meta_extra', 409);
            }
        }
        usort(
            $delete_rows,
            function ($left, $right) {
                return $left['meta_id'] - $right['meta_id'];
            }
        );
        $delete_ids = array();
        $cleanup_row_digests = array();
        foreach ($delete_rows as $row) {
            $delete_ids[$row['meta_id']] = true;
            $cleanup_row_digests[] = array(
                'key_sha256' => hash('sha256', $row['meta_key']),
                'meta_id' => $row['meta_id'],
                'value_sha256' => hash('sha256', $row['meta_value']),
            );
        }
        $current_digest_rows = array();
        $after_digest_rows = array();
        $after_pairs = array();
        foreach ($current_rows as $row) {
            $digest = array(
                'key_sha256' => hash('sha256', $row['meta_key']),
                'meta_id' => $row['meta_id'],
                'value_sha256' => hash('sha256', $row['meta_value']),
            );
            $current_digest_rows[] = $digest;
            if (! isset($delete_ids[$row['meta_id']])) {
                $after_digest_rows[] = $digest;
                $after_pairs[] = $row['pair'];
            }
        }
        $sort_pairs = function ($left, $right) {
            $key_order = strcmp($left['key_base64'], $right['key_base64']);
            return $key_order !== 0
                ? $key_order
                : strcmp($left['value_base64'], $right['value_base64']);
        };
        usort($after_pairs, $sort_pairs);
        $before_pairs = $before_rows;
        usort($before_pairs, $sort_pairs);
        if (self::canonical_json($after_pairs)
            !== self::canonical_json($before_pairs)) {
            return self::error('raos_st1704_reconciliation_meta_ambiguous', 409);
        }
        if ($delete_rows === array() && $expected_extras !== array()) {
            $state = 'CLEAN';
        } elseif (count($delete_rows) === count($expected_extras)) {
            $state = 'EXACT_REDIRECT_EXTRAS';
        } else {
            return self::error('raos_st1704_reconciliation_meta_ambiguous', 409);
        }
        $hashes = array(
            'before_meta_multiset_sha256' => self::canonical_hash($before_pairs),
            'cleanup_row_digests' => $cleanup_row_digests,
            'current_meta_rows_sha256' => self::canonical_hash(
                $current_digest_rows
            ),
            'current_published_storage_sha256' => self::canonical_hash(
                $current_storage
            ),
            'expected_after_meta_rows_sha256' => self::canonical_hash(
                $after_digest_rows
            ),
            'expected_after_meta_multiset_sha256' => self::canonical_hash(
                $after_pairs
            ),
        );
        foreach ($hashes as $key => $value) {
            if ($key !== 'cleanup_row_digests' && ! is_string($value)) {
                return self::error('raos_st1704_reconciliation_hash_invalid', 409);
            }
        }
        return array_merge(
            $hashes,
            array(
                'delete_rows' => array_map(
                    function ($row) {
                        return array(
                            'meta_id' => $row['meta_id'],
                            'meta_key' => $row['meta_key'],
                            'meta_value' => $row['meta_value'],
                        );
                    },
                    $delete_rows
                ),
                'state' => $state,
            )
        );
    }

    public function rest_verify_revision(WP_REST_Request $request)
    {
        if (! self::runtime_origin_is_exact()) {
            return self::error('raos_st1704_runtime_origin_invalid', 409);
        }
        $proposal_id = (string) $request['proposal_id'];
        if (preg_match('/\A[a-f0-9]{64}\z/', $proposal_id) !== 1
            || $request->get_body() !== ''
            || $request->get_query_params() !== array()) {
            return self::error('raos_st1704_revision_verify_invalid', 400);
        }
        $row = $this->proposal_row($proposal_id);
        $stored = is_array($row)
            ? $this->validated_stored_proposal($row, $proposal_id)
            : self::error('raos_st1704_proposal_not_found', 404);
        $modified_times = is_array($row)
            ? self::publication_modified_times_from_gmt($row['apply_started_at'])
            : false;
        if (is_wp_error($stored)
            || $stored['request']['operation'] !== self::REVISION_OPERATION
            || $row['state'] !== 'APPLIED'
            || $row['result_code'] !== self::REVISION_RESULT_CODE
            || (int) $row['proposer_user_id'] !== get_current_user_id()
            || ! is_array($modified_times)
            || ! $this->approval_evidence_is_valid($row, $proposal_id, false)
            || ! $this->revision_state_matches_successor(
                $stored['request'],
                $stored['before_state'],
                $modified_times
            )) {
            return self::error('raos_st1704_revision_verify_mismatch', 409);
        }
        return new WP_REST_Response(
            array(
                'schema' => 'RAOS_ST1704_DRAFT_REVISION_VERIFY_V2',
                'proposal_id' => $proposal_id,
                'operation' => self::REVISION_OPERATION,
                'operation_sha256' => $stored['request']['operation_sha256'],
                'draft_post_id' => $stored['request']['draft_post_id'],
                'state' => 'APPLIED',
                'result_code' => self::REVISION_VERIFY_RESULT_CODE,
            ),
            200,
            array('ETag' => '"' . $proposal_id . '"')
        );
    }

    public function rest_recover_revision_state(WP_REST_Request $request)
    {
        if (! self::runtime_origin_is_exact()) {
            return self::error('raos_st1704_runtime_origin_invalid', 409);
        }
        $proposal_id = (string) $request['proposal_id'];
        if (preg_match('/\A[a-f0-9]{64}\z/', $proposal_id) !== 1
            || $request->get_body() !== ''
            || $request->get_query_params() !== array()) {
            return self::error('raos_st1704_revision_recovery_invalid', 400);
        }
        $mutex_name = $this->publication_mutex_name();
        if (! $this->acquire_publication_mutex($mutex_name)) {
            return self::error('raos_st1704_publication_busy', 409);
        }
        $released = false;
        try {
            $response = $this->recover_revision_state_under_mutex($proposal_id);
        } catch (Throwable $exception) {
            $response = self::error(
                'raos_st1704_revision_recovery_unavailable',
                500
            );
        } finally {
            $released = $this->release_publication_mutex($mutex_name);
        }
        return $released
            ? $response
            : self::error('raos_st1704_mutex_release_uncertain', 500);
    }

    private function recover_revision_state_under_mutex($proposal_id)
    {
        $mutex_name = $this->publication_mutex_name();
        if (! $this->publication_mutex_is_owned($mutex_name)) {
            return self::error('raos_st1704_publication_lock_lost', 500);
        }
        $row = $this->proposal_row($proposal_id);
        $stored = is_array($row)
            ? $this->validated_stored_proposal($row, $proposal_id)
            : self::error('raos_st1704_proposal_not_found', 404);
        if (is_wp_error($stored)
            || $stored['request']['operation'] !== self::REVISION_OPERATION
            || (int) $row['proposer_user_id'] !== get_current_user_id()) {
            return self::error('raos_st1704_revision_recovery_mismatch', 409);
        }

        $proposal = $stored['request'];
        $before = $stored['before_state'];
        $state = $row['state'];
        $disposition = null;
        $modified_times = self::publication_modified_times_from_gmt(
            $row['apply_started_at']
        );
        if ($state === 'APPLIED') {
            if ($row['result_code'] !== self::REVISION_RESULT_CODE
                || ! is_array($modified_times)
                || ! $this->approval_evidence_is_valid(
                    $row,
                    $proposal_id,
                    false
                )
                || ! $this->revision_state_matches_successor(
                    $proposal,
                    $before,
                    $modified_times
                )) {
                return self::error(
                    'raos_st1704_revision_recovery_mismatch',
                    409
                );
            }
            $disposition = 'SUCCESSOR';
        } elseif ($state === 'NEEDS_RECOVERY') {
            if (is_array($modified_times)
                && $this->approval_evidence_is_valid(
                    $row,
                    $proposal_id,
                    false
                )
                && $this->revision_state_matches_successor(
                    $proposal,
                    $before,
                    $modified_times
                )) {
                $disposition = 'SUCCESSOR';
            } elseif ($this->revision_before_state_matches(
                $proposal,
                $before,
                false,
                false
            )) {
                $disposition = 'PREDECESSOR';
            }
        } elseif (in_array($state, array('FAILED', 'EXPIRED'), true)) {
            if ($this->revision_before_state_matches(
                $proposal,
                $before,
                false,
                false
            )) {
                $disposition = 'PREDECESSOR';
            }
        } elseif (in_array($state, array('PROPOSED', 'APPROVED'), true)) {
            $expires_epoch = self::strict_mysql_utc_epoch($row['expires_at']);
            if (is_int($expires_epoch)
                && $expires_epoch <= time()
                && $this->revision_before_state_matches(
                    $proposal,
                    $before,
                    false,
                    false
                )) {
                $disposition = 'PREDECESSOR';
            }
        }
        // APPLYING remains recoverable only through the exact idempotent apply
        // request. Classifying it here could race an in-flight transaction.
        if (! is_string($disposition)) {
            return self::error('raos_st1704_revision_recovery_mismatch', 409);
        }
        if (! $this->publication_mutex_is_owned($mutex_name)) {
            return self::error('raos_st1704_publication_lock_lost', 500);
        }
        return new WP_REST_Response(
            array(
                'schema' => 'RAOS_ST1704_DRAFT_REVISION_RECOVERY_V2',
                'proposal_id' => $proposal_id,
                'operation' => self::REVISION_OPERATION,
                'operation_sha256' => $proposal['operation_sha256'],
                'draft_post_id' => $proposal['draft_post_id'],
                'proposal_state' => $state,
                'disposition' => $disposition,
                'result_code' => self::REVISION_RECOVERY_RESULT_CODE,
            ),
            200,
            array('ETag' => '"' . $proposal_id . '"')
        );
    }

    public function rest_apply(WP_REST_Request $request)
    {
        if (! self::runtime_origin_is_exact()) {
            return self::error('raos_st1704_runtime_origin_invalid', 409);
        }
        if (! self::writes_enabled()) {
            return self::error('raos_st1704_writes_disabled', 503);
        }
        $proposal_id = (string) $request['proposal_id'];
        if (preg_match('/\A[a-f0-9]{64}\z/', $proposal_id) !== 1
            || $request->get_query_params() !== array()
            || $request->get_header('content-type') !== 'application/json'
            || $request->get_body() !== '{}') {
            return self::error('raos_st1704_apply_request_invalid', 400);
        }
        if (! hash_equals(
            '"' . $proposal_id . '"',
            (string) $request->get_header('if-match')
        )) {
            return self::error('raos_st1704_precondition_failed', 412);
        }
        $idempotency_key = (string) $request->get_header('idempotency-key');
        if (! hash_equals($proposal_id, $idempotency_key)) {
            return self::error('raos_st1704_idempotency_key_invalid', 400);
        }
        $mutex_name = $this->publication_mutex_name();
        if (! $this->acquire_publication_mutex($mutex_name)) {
            return self::error('raos_st1704_publication_busy', 409);
        }
        $released = false;
        try {
            $response = $this->execute_apply_under_mutex(
                $proposal_id,
                $idempotency_key,
                $mutex_name
            );
        } catch (Throwable $exception) {
            global $wpdb;
            $wpdb->query('ROLLBACK');
            $response = $this->finish_unhandled_apply_exception(
                $proposal_id,
                $mutex_name
            );
        } finally {
            $released = $this->release_publication_mutex($mutex_name);
        }
        return $released
            ? $response
            : self::error('raos_st1704_mutex_release_uncertain', 500);
    }

    private function execute_apply_under_mutex(
        $proposal_id,
        $idempotency_key,
        $mutex_name
    ) {
        global $wpdb;
        if (! $this->publication_mutex_is_owned($mutex_name)
            || ! $this->expire_due_proposals_under_mutex($mutex_name)) {
            return self::error('raos_st1704_publication_lock_lost', 500);
        }
        $row = $this->proposal_row($proposal_id);
        if (! is_array($row)) {
            return is_wp_error($row)
                ? $row
                : self::error('raos_st1704_proposal_not_found', 404);
        }
        $stored = $this->validated_stored_proposal($row, $proposal_id);
        if (is_wp_error($stored)
            || (int) $row['proposer_user_id'] !== get_current_user_id()) {
            return self::error('raos_st1704_proposal_record_invalid', 409);
        }
        if ($stored['request']['operation'] === self::REVISION_OPERATION) {
            return $this->execute_revision_apply_under_mutex(
                $row,
                $stored,
                $proposal_id,
                $idempotency_key,
                $mutex_name
            );
        }
        if ($row['state'] === 'APPLIED') {
            $modified_times = self::publication_modified_times_from_gmt(
                $row['apply_started_at']
            );
            if (! is_array($modified_times)
                || ! is_string($row['idempotency_key'])
                || ! hash_equals($idempotency_key, $row['idempotency_key'])
                || $row['result_code'] !== self::RESULT_CODE
                || ! $this->approval_evidence_is_valid($row, $proposal_id, false)
                || ! $this->published_state_matches(
                    $stored['request'],
                    $stored['before_state'],
                    $modified_times
                )) {
                return self::error('raos_st1704_terminal_replay_invalid', 409);
            }
            return $this->apply_response($row, true);
        }
        if ($row['state'] === 'APPLYING') {
            if (! $this->publication_mutex_is_owned($mutex_name)) {
                return self::error('raos_st1704_publication_lock_lost', 500);
            }
            $orphan_evidence_is_bound = is_string($row['idempotency_key'])
                && hash_equals($idempotency_key, $row['idempotency_key'])
                && is_string($row['rollback_json'])
                && hash_equals($row['before_state_json'], $row['rollback_json'])
                && hash_equals(
                    $row['before_state_hash'],
                    hash('sha256', $row['rollback_json'])
                )
                && $this->approval_evidence_is_valid(
                    $row,
                    $proposal_id,
                    false
                );
            $hook_replay_is_durable = $orphan_evidence_is_bound
                && is_string($row['result_code'])
                && hash_equals(
                    self::HOOK_REPLAY_COMPLETED,
                    $row['result_code']
                );
            $modified_times = $hook_replay_is_durable
                ? self::publication_modified_times_from_gmt(
                    $row['apply_started_at']
                )
                : false;
            if ($hook_replay_is_durable
                && is_array($modified_times)
                && $this->published_state_matches(
                    $stored['request'],
                    $stored['before_state'],
                    $modified_times
                )) {
                return $this->finish_success(
                    $proposal_id,
                    $stored['request'],
                    $stored['before_state'],
                    $mutex_name,
                    $modified_times
                );
            }
            if (! $hook_replay_is_durable
                && $orphan_evidence_is_bound
                && $this->published_state_matches(
                    $stored['request'],
                    $stored['before_state']
                )) {
                return $this->finish_failure(
                    $proposal_id,
                    'NEEDS_RECOVERY',
                    'ORPHANED_APPLYING_REPLAY_UNPROVEN',
                    $mutex_name
                );
            }
            if (! $hook_replay_is_durable
                && $orphan_evidence_is_bound
                && $this->before_state_matches(
                    $stored['request'],
                    $stored['before_state']
                )) {
                return $this->finish_failure(
                    $proposal_id,
                    'FAILED',
                    'ORPHANED_APPLYING_BEFORE_STATE',
                    $mutex_name
                );
            }
            return $this->finish_failure(
                $proposal_id,
                'NEEDS_RECOVERY',
                'ORPHANED_APPLYING_STATE_AMBIGUOUS',
                $mutex_name
            );
        }
        if ($row['state'] !== 'APPROVED'
            || ! $this->approval_evidence_is_valid($row, $proposal_id, true)) {
            return self::error('raos_st1704_proposal_not_approved', 409);
        }
        $current_state = $this->capture_publication_state($stored['request']);
        $current_json = is_wp_error($current_state)
            ? null
            : self::canonical_json($current_state);
        if (! is_string($current_json)
            || ! hash_equals($row['before_state_json'], $current_json)
            || ! hash_equals($row['before_state_hash'], hash('sha256', $current_json))) {
            return self::error('raos_st1704_before_state_changed', 409);
        }
        require_once ABSPATH . 'wp-admin/includes/post.php';
        if (! function_exists('wp_check_post_lock')
            || wp_check_post_lock($stored['request']['draft_post_id']) !== false
            || ! $this->publication_mutex_is_owned($mutex_name)) {
            return self::error('raos_st1704_post_locked', 409);
        }

        $modified_times = self::capture_publication_modified_times();
        if (! is_array($modified_times)) {
            return self::error(
                'raos_st1704_publication_modified_time_invalid',
                500
            );
        }
        $table = self::proposal_table();
        $now = $modified_times['post_modified_gmt'];
        if ($wpdb->query('START TRANSACTION') === false
            || ! $this->publication_mutex_is_owned($mutex_name)) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_st1704_transaction_unavailable', 500);
        }
        $cas = $wpdb->query(
            $wpdb->prepare(
                "UPDATE {$table}
                 SET state = %s, apply_started_at = %s,
                     idempotency_key = %s, rollback_json = %s,
                     state_version = state_version + 1
                 WHERE proposal_id = %s AND state = %s
                   AND approved_by_user_id IS NOT NULL
                   AND approved_by_user_id <> proposer_user_id
                   AND before_state_hash = %s
                   AND approval_evidence_hash = %s
                   AND expires_at > %s AND approval_expires_at > %s",
                'APPLYING',
                $now,
                $idempotency_key,
                $current_json,
                $proposal_id,
                'APPROVED',
                $row['before_state_hash'],
                $row['approval_evidence_hash'],
                $now,
                $now
            )
        );
        $audit_hash = $cas === 1
            ? self::append_audit(
                'APPLY_STARTED',
                $proposal_id,
                'APPLYING',
                get_current_user_id()
            )
            : false;
        if ($cas !== 1
            || ! is_string($audit_hash)
            || ! $this->publication_mutex_is_owned($mutex_name)
            || $wpdb->query('COMMIT') === false) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_st1704_apply_cas_failed', 409);
        }

        $result = $this->apply_one_publication(
            $stored['request'],
            $current_state,
            $mutex_name,
            $modified_times
        );
        $result_modified_times = isset($result['modified_times'])
            && is_array($result['modified_times'])
            ? $result['modified_times']
            : null;
        if ($result['ok']
            && is_array($result_modified_times)
            && $this->persist_hook_replay_completion(
                $proposal_id,
                $stored['request'],
                $current_state,
                $mutex_name,
                $result_modified_times
            )) {
            return $this->finish_success(
                $proposal_id,
                $stored['request'],
                $current_state,
                $mutex_name,
                $result_modified_times
            );
        }
        if ($result['ok']) {
            return $this->finish_failure(
                $proposal_id,
                'NEEDS_RECOVERY',
                'HOOK_REPLAY_RECEIPT_PERSISTENCE_FAILED',
                $mutex_name
            );
        }
        return $this->finish_failure(
            $proposal_id,
            $result['state'],
            $result['code'],
            $mutex_name
        );
    }

    private function execute_revision_apply_under_mutex(
        array $row,
        array $stored,
        $proposal_id,
        $idempotency_key,
        $mutex_name
    ) {
        global $wpdb;
        $proposal = $stored['request'];
        $before = $stored['before_state'];
        if ($row['state'] === 'APPLIED') {
            $modified_times = self::publication_modified_times_from_gmt(
                $row['apply_started_at']
            );
            if (! is_array($modified_times)
                || ! is_string($row['idempotency_key'])
                || ! hash_equals($idempotency_key, $row['idempotency_key'])
                || $row['result_code'] !== self::REVISION_RESULT_CODE
                || ! $this->approval_evidence_is_valid($row, $proposal_id, false)
                || ! $this->revision_state_matches_successor(
                    $proposal,
                    $before,
                    $modified_times
                )) {
                return self::error('raos_st1704_revision_terminal_replay_invalid', 409);
            }
            return $this->apply_response($row, true);
        }
        if ($row['state'] !== 'APPROVED' && $row['state'] !== 'APPLYING') {
            return self::error('raos_st1704_proposal_not_approved', 409);
        }
        if (! $this->approval_evidence_is_valid(
            $row,
            $proposal_id,
            $row['state'] === 'APPROVED'
        )) {
            return self::error('raos_st1704_proposal_not_approved', 409);
        }
        require_once ABSPATH . 'wp-admin/includes/post.php';
        if (! function_exists('wp_check_post_lock')
            || wp_check_post_lock($proposal['draft_post_id']) !== false
            || ! $this->publication_mutex_is_owned($mutex_name)) {
            return self::error('raos_st1704_post_locked', 409);
        }
        if ($row['state'] === 'APPROVED') {
            $current = $this->capture_revision_state($proposal);
            $current_json = is_wp_error($current)
                ? null
                : self::canonical_json($current);
            $modified_times = self::capture_publication_modified_times();
            if (! is_string($current_json)
                || ! is_array($modified_times)
                || ! hash_equals($row['before_state_json'], $current_json)
                || ! hash_equals(
                    $row['before_state_hash'],
                    hash('sha256', $current_json)
                )) {
                return self::error('raos_st1704_before_state_changed', 409);
            }
            $now = $modified_times['post_modified_gmt'];
            $table = self::proposal_table();
            if ($wpdb->query('START TRANSACTION') === false
                || ! $this->publication_mutex_is_owned($mutex_name)) {
                $wpdb->query('ROLLBACK');
                return self::error('raos_st1704_transaction_unavailable', 500);
            }
            $cas = $wpdb->query(
                $wpdb->prepare(
                    "UPDATE {$table}
                     SET state = %s, apply_started_at = %s,
                         idempotency_key = %s, rollback_json = %s,
                         state_version = state_version + 1
                     WHERE proposal_id = %s AND state = %s
                       AND approved_by_user_id IS NOT NULL
                       AND approved_by_user_id <> proposer_user_id
                       AND before_state_hash = %s
                       AND approval_evidence_hash = %s
                       AND expires_at > %s AND approval_expires_at > %s",
                    'APPLYING',
                    $now,
                    $idempotency_key,
                    $current_json,
                    $proposal_id,
                    'APPROVED',
                    $row['before_state_hash'],
                    $row['approval_evidence_hash'],
                    $now,
                    $now
                )
            );
            $audit_hash = $cas === 1
                ? self::append_audit(
                    'DRAFT_REVISION_STARTED',
                    $proposal_id,
                    'APPLYING',
                    get_current_user_id()
                )
                : false;
            if ($cas !== 1
                || ! is_string($audit_hash)
                || ! $this->publication_mutex_is_owned($mutex_name)
                || $wpdb->query('COMMIT') === false) {
                $wpdb->query('ROLLBACK');
                return self::error('raos_st1704_revision_apply_cas_failed', 409);
            }
        } else {
            if (! is_string($row['idempotency_key'])
                || ! hash_equals($idempotency_key, $row['idempotency_key'])
                || ! is_string($row['rollback_json'])
                || ! hash_equals($row['before_state_json'], $row['rollback_json'])
                || ! hash_equals(
                    $row['before_state_hash'],
                    hash('sha256', $row['rollback_json'])
                )) {
                return self::error('raos_st1704_revision_recovery_not_bound', 409);
            }
            $modified_times = self::publication_modified_times_from_gmt(
                $row['apply_started_at']
            );
            if (! is_array($modified_times)) {
                return self::error('raos_st1704_revision_recovery_not_bound', 409);
            }
            if ($this->revision_state_matches_successor(
                $proposal,
                $before,
                $modified_times
            )) {
                return $this->finish_revision_success(
                    $proposal_id,
                    $proposal,
                    $before,
                    $mutex_name,
                    $modified_times
                );
            }
            if (! $this->revision_before_state_matches($proposal, $before)) {
                return $this->finish_failure(
                    $proposal_id,
                    'NEEDS_RECOVERY',
                    'DRAFT_REVISION_STATE_AMBIGUOUS',
                    $mutex_name
                );
            }
        }
        return $this->apply_one_revision(
            $proposal_id,
            $proposal,
            $before,
            $mutex_name,
            $modified_times
        );
    }

    private function apply_one_revision(
        $proposal_id,
        array $proposal,
        array $before,
        $mutex_name,
        array $modified_times
    ) {
        global $wpdb;
        $post_id = $proposal['draft_post_id'];
        $successor = $proposal['successor'];
        $content = self::decode_canonical_base64(
            $successor['content_base64'],
            self::REVISION_CONTENT_MAX_BYTES
        );
        $excerpt = self::decode_canonical_base64(
            $successor['excerpt_base64'],
            2400
        );
        $title = self::decode_canonical_base64(
            $successor['title_base64'],
            1200
        );
        $snapshot_raw = self::decode_canonical_base64(
            $successor['snapshot_base64'],
            self::SNAPSHOT_MAX_BYTES
        );
        if (! is_string($content)
            || ! is_string($excerpt)
            || ! is_string($title)
            || ! is_string($snapshot_raw)
            || ! $this->publication_mutex_is_owned($mutex_name)) {
            return $this->finish_failure(
                $proposal_id,
                'FAILED',
                'DRAFT_REVISION_SUCCESSOR_INVALID',
                $mutex_name
            );
        }
        if ($wpdb->query('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE') === false
            || $wpdb->query('START TRANSACTION') === false
            || ! $this->publication_mutex_is_owned($mutex_name)) {
            $wpdb->query('ROLLBACK');
            return $this->finish_failure(
                $proposal_id,
                'NEEDS_RECOVERY',
                'DRAFT_REVISION_TRANSACTION_UNAVAILABLE',
                $mutex_name
            );
        }
        $locked = $this->capture_revision_state($proposal, true);
        $locked_json = is_wp_error($locked) ? null : self::canonical_json($locked);
        $before_json = self::canonical_json($before);
        if (! is_string($locked_json)
            || ! is_string($before_json)
            || ! hash_equals($before_json, $locked_json)
            || ! $this->publication_mutex_is_owned($mutex_name)) {
            $wpdb->query('ROLLBACK');
            return $this->finish_failure(
                $proposal_id,
                'NEEDS_RECOVERY',
                'DRAFT_REVISION_LOCKED_PRESTATE_CHANGED',
                $mutex_name
            );
        }
        $old_fields = $before['storage']['restore']['post_fields'];
        $old_content = self::decode_exact_base64($old_fields['post_content']);
        $old_excerpt = self::decode_exact_base64($old_fields['post_excerpt']);
        $old_title = self::decode_exact_base64($old_fields['post_title']);
        $old_slug = self::decode_exact_base64($old_fields['post_name']);
        $post_updated = $wpdb->query(
            $wpdb->prepare(
                "UPDATE {$wpdb->posts}
                 SET post_content = %s, post_excerpt = %s, post_title = %s,
                     post_name = %s, post_modified = %s,
                     post_modified_gmt = %s
                 WHERE ID = %d
                   AND BINARY post_content = BINARY %s
                   AND BINARY post_excerpt = BINARY %s
                   AND BINARY post_title = BINARY %s
                   AND BINARY post_name = BINARY %s
                   AND BINARY post_status = BINARY %s
                   AND BINARY post_type = BINARY %s
                   AND (IS_USED_LOCK(%s) = CONNECTION_ID())",
                $content,
                $excerpt,
                $title,
                $successor['review_slug'],
                $modified_times['post_modified'],
                $modified_times['post_modified_gmt'],
                $post_id,
                $old_content,
                $old_excerpt,
                $old_title,
                $old_slug,
                'draft',
                'post',
                $mutex_name
            )
        );
        $snapshot_updated = $post_updated === 1
            ? $wpdb->query(
                $wpdb->prepare(
                    "UPDATE {$wpdb->postmeta}
                     SET meta_value = %s
                     WHERE post_id = %d
                       AND BINARY meta_key = BINARY %s
                       AND BINARY meta_value = BINARY %s
                       AND (IS_USED_LOCK(%s) = CONNECTION_ID())",
                    $snapshot_raw,
                    $post_id,
                    self::SNAPSHOT_META_KEY,
                    $before['storage']['snapshot_raw'],
                    $mutex_name
                )
            )
            : false;
        if ($post_updated !== 1
            || $snapshot_updated !== 1
            || ! $this->revision_state_matches_successor(
                $proposal,
                $before,
                $modified_times,
                true
            )) {
            $wpdb->query('ROLLBACK');
            return $this->finish_failure(
                $proposal_id,
                'FAILED',
                'DRAFT_REVISION_BOUNDED_WRITE_FAILED',
                $mutex_name
            );
        }
        $table = self::proposal_table();
        $completed_at = gmdate('Y-m-d H:i:s');
        $receipt_updated = $wpdb->query(
            $wpdb->prepare(
                "UPDATE {$table}
                 SET state = %s, result_code = %s, completed_at = %s,
                     state_version = state_version + 1
                 WHERE proposal_id = %s AND state = %s
                   AND BINARY apply_started_at = BINARY %s",
                'APPLIED',
                self::REVISION_RESULT_CODE,
                $completed_at,
                $proposal_id,
                'APPLYING',
                $modified_times['post_modified_gmt']
            )
        );
        $audit_hash = $receipt_updated === 1
            ? self::append_audit(
                'DRAFT_REVISED',
                $proposal_id,
                self::REVISION_RESULT_CODE,
                get_current_user_id()
            )
            : false;
        if ($receipt_updated !== 1
            || ! is_string($audit_hash)
            || ! $this->publication_mutex_is_owned($mutex_name)
            || $wpdb->query('COMMIT') === false) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_st1704_revision_outcome_ambiguous', 500);
        }
        clean_post_cache($post_id);
        return $this->apply_response(
            array(
                'proposal_id' => $proposal_id,
                'operation' => self::REVISION_OPERATION,
                'state' => 'APPLIED',
                'result_code' => self::REVISION_RESULT_CODE,
            ),
            false
        );
    }

    private function finish_revision_success(
        $proposal_id,
        array $proposal,
        array $before,
        $mutex_name,
        array $modified_times
    ) {
        global $wpdb;
        if ($wpdb->query('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE') === false
            || $wpdb->query('START TRANSACTION') === false
            || ! $this->revision_state_matches_successor(
                $proposal,
                $before,
                $modified_times,
                true
            )) {
            $wpdb->query('ROLLBACK');
            return $this->finish_failure(
                $proposal_id,
                'NEEDS_RECOVERY',
                'DRAFT_REVISION_TERMINAL_READBACK_CHANGED',
                $mutex_name
            );
        }
        $table = self::proposal_table();
        $updated = $wpdb->query(
            $wpdb->prepare(
                "UPDATE {$table}
                 SET state = %s, result_code = %s, completed_at = %s,
                     state_version = state_version + 1
                 WHERE proposal_id = %s AND state = %s",
                'APPLIED',
                self::REVISION_RESULT_CODE,
                gmdate('Y-m-d H:i:s'),
                $proposal_id,
                'APPLYING'
            )
        );
        $audit_hash = $updated === 1
            ? self::append_audit(
                'DRAFT_REVISION_RECOVERED',
                $proposal_id,
                self::REVISION_RESULT_CODE,
                get_current_user_id()
            )
            : false;
        if ($updated !== 1
            || ! is_string($audit_hash)
            || ! $this->publication_mutex_is_owned($mutex_name)
            || $wpdb->query('COMMIT') === false) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_st1704_revision_outcome_ambiguous', 500);
        }
        clean_post_cache($proposal['draft_post_id']);
        return $this->apply_response(
            array(
                'proposal_id' => $proposal_id,
                'operation' => self::REVISION_OPERATION,
                'state' => 'APPLIED',
                'result_code' => self::REVISION_RESULT_CODE,
            ),
            true
        );
    }

    private function published_state_matches(
        array $proposal,
        array $before,
        array $expected_modified_times = array(),
        $lock_storage = false
    ) {
        if (! is_bool($lock_storage)
            || ! isset(
                $before['category_term_id'],
                $before['category_term_taxonomy_id'],
                $before['draft_post_id'],
                $before['storage']['summary']
            )
            || ($expected_modified_times !== array()
                && (! self::has_exact_keys(
                    $expected_modified_times,
                    array('post_modified', 'post_modified_gmt')
                )
                    || ! is_string($expected_modified_times['post_modified'])
                    || ! is_string(
                        $expected_modified_times['post_modified_gmt']
                    )))) {
            return false;
        }
        $category = $this->resolve_exact_category();
        if (is_wp_error($category)
            || $category['term_id'] !== (int) $before['category_term_id']
            || $category['term_taxonomy_id']
                !== (int) $before['category_term_taxonomy_id']) {
            return false;
        }
        $current = $this->capture_post_storage(
            $proposal['draft_post_id'],
            $category,
            $lock_storage
        );
        if (is_wp_error($current)) {
            return false;
        }
        if ($expected_modified_times !== array()) {
            $expected_publication_dates = self::publication_date_fields(
                $before,
                $expected_modified_times
            );
            $current_post_date = self::decode_exact_base64(
                $current['restore']['post_fields']['post_date']
            );
            $current_post_date_gmt = self::decode_exact_base64(
                $current['restore']['post_fields']['post_date_gmt']
            );
            $current_post_modified = self::decode_exact_base64(
                $current['restore']['post_fields']['post_modified']
            );
            $current_post_modified_gmt = self::decode_exact_base64(
                $current['restore']['post_fields']['post_modified_gmt']
            );
            if (! is_array($expected_publication_dates)
                || ! is_string($current_post_date)
                || ! is_string($current_post_date_gmt)
                || ! is_string($current_post_modified)
                || ! is_string($current_post_modified_gmt)
                || ! hash_equals(
                    $expected_publication_dates['post_date'],
                    $current_post_date
                )
                || ! hash_equals(
                    $expected_publication_dates['post_date_gmt'],
                    $current_post_date_gmt
                )
                || ! hash_equals(
                    $expected_modified_times['post_modified'],
                    $current_post_modified
                )
                || ! hash_equals(
                    $expected_modified_times['post_modified_gmt'],
                    $current_post_modified_gmt
                )) {
                return false;
            }
        }
        $old = $before['storage']['summary'];
        $new = $current['summary'];
        $preserved = array(
            'all_meta_sha256',
            'content_sha256',
            'excerpt_sha256',
            'featured_media_id',
            'other_meta_sha256',
            'other_taxonomy_sha256',
            'post_id',
            'protected_post_fields_sha256',
            'snapshot_meta_sha256',
            'thumbnail_meta_sha256',
            'title_sha256',
        );
        foreach ($preserved as $key) {
            if (! array_key_exists($key, $old)
                || ! array_key_exists($key, $new)
                || $old[$key] !== $new[$key]) {
                return false;
            }
        }
        $expected_category_relationship_hash = self::canonical_hash(
            array(
                array(
                    'term_order' => 0,
                    'term_taxonomy_id' => (int) $before[
                        'category_term_taxonomy_id'
                    ],
                ),
            )
        );
        return $new['status'] === 'publish'
            && $new['slug'] === $proposal['public_slug']
            && is_string($expected_category_relationship_hash)
            && isset($new['category_relationship_sha256'])
            && is_string($new['category_relationship_sha256'])
            && hash_equals(
                $expected_category_relationship_hash,
                $new['category_relationship_sha256']
            )
            && $new['category_term_taxonomy_ids']
                === array($category['term_taxonomy_id']);
    }

    private function before_state_matches(array $proposal, array $before)
    {
        $current = $this->capture_publication_state($proposal);
        if (is_wp_error($current)) {
            return false;
        }
        $current_json = self::canonical_json($current);
        $before_json = self::canonical_json($before);
        return is_string($current_json)
            && is_string($before_json)
            && hash_equals($before_json, $current_json);
    }

    private static function publication_replay_hook_names()
    {
        return array(
            'added_term_relationship',
            'deleted_term_relationships',
            'set_object_terms',
            'pre_post_insert',
            'transition_post_status',
            'new_to_inherit',
            'inherit_revision',
            'draft_to_publish',
            'publish_post',
            'edit_post_post',
            'edit_post',
            'post_updated',
            'save_post_post',
            'save_post_revision',
            'save_post',
            'wp_insert_post',
            'wp_after_insert_post',
            '_wp_put_post_revision',
        );
    }

    private static function publication_pre_mutation_hook_names()
    {
        return array(
            'add_term_relationship',
            'delete_term_relationships',
            'pre_post_update',
        );
    }

    private function publication_pre_mutation_hooks_are_unobserved()
    {
        global $wp_filter;
        if (! is_array($wp_filter)) {
            return false;
        }
        $hook_names = array_merge(
            self::publication_pre_mutation_hook_names(),
            array('all')
        );
        foreach ($hook_names as $hook_name) {
            if (! array_key_exists($hook_name, $wp_filter)) {
                continue;
            }
            $hook = $wp_filter[$hook_name];
            if (! $hook instanceof WP_Hook
                || ! is_array($hook->callbacks)
                || $hook->callbacks !== array()) {
                return false;
            }
        }
        return true;
    }

    private static function publication_core_redirect_callbacks_are_exact()
    {
        global $wp_filter;
        if (! is_array($wp_filter)
            || ! isset($wp_filter['post_updated'])
            || ! $wp_filter['post_updated'] instanceof WP_Hook
            || ! is_array($wp_filter['post_updated']->callbacks)
            || ! isset($wp_filter['post_updated']->callbacks[12])
            || ! is_array($wp_filter['post_updated']->callbacks[12])) {
            return false;
        }
        $priority_callbacks = $wp_filter['post_updated']->callbacks[12];
        foreach (
            array(
                'wp_check_for_changed_slugs',
                'wp_check_for_changed_dates',
            ) as $callback_name
        ) {
            if (! function_exists($callback_name)
                || ! array_key_exists($callback_name, $priority_callbacks)) {
                return false;
            }
            $callback = $priority_callbacks[$callback_name];
            if (! is_array($callback)
                || ! self::has_exact_keys(
                    $callback,
                    array('accepted_args', 'function')
                )
                || $callback['accepted_args'] !== 3
                || $callback['function'] !== $callback_name) {
                return false;
            }
        }
        return true;
    }

    private static function publication_redirect_metadata_values(array $before)
    {
        if (! function_exists('maybe_unserialize')
            || ! isset($before['storage']['restore']['meta_rows'])
            || ! is_array($before['storage']['restore']['meta_rows'])
            || count($before['storage']['restore']['meta_rows'])
                > self::MAX_META_ROWS) {
            return false;
        }
        $values = array(
            '_wp_old_slug' => array(),
            '_wp_old_date' => array(),
        );
        foreach ($before['storage']['restore']['meta_rows'] as $row) {
            if (! is_array($row)
                || ! self::has_exact_keys(
                    $row,
                    array('key_base64', 'value_base64')
                )
                || ! is_string($row['key_base64'])
                || ! is_string($row['value_base64'])) {
                return false;
            }
            $key = self::decode_exact_base64($row['key_base64']);
            $value = self::decode_exact_base64($row['value_base64']);
            if (! is_string($key) || ! is_string($value)) {
                return false;
            }
            if (array_key_exists($key, $values)) {
                $values[$key][] = maybe_unserialize($value);
            }
        }
        return $values;
    }

    private static function publication_redirect_meta_plan(
        array $before,
        WP_Post $post_before,
        array $publication_dates,
        $public_slug
    ) {
        $values = self::publication_redirect_metadata_values($before);
        if (! is_array($values)
            || ! self::has_exact_keys(
                $publication_dates,
                array('post_date', 'post_date_gmt')
            )
            || ! is_string($post_before->post_name)
            || ! is_string($post_before->post_date)
            || ! is_string($publication_dates['post_date'])
            || ! is_string($public_slug)
            || $public_slug === '') {
            return false;
        }
        $previous_slug = $post_before->post_name;
        $previous_date = gmdate(
            'Y-m-d',
            strtotime($post_before->post_date)
        );
        $published_date = gmdate(
            'Y-m-d',
            strtotime($publication_dates['post_date'])
        );
        return array(
            '_wp_old_slug' => array(
                'add_expected' => $previous_slug !== $public_slug
                    && ! empty($previous_slug)
                    && ! in_array(
                        $previous_slug,
                        $values['_wp_old_slug'],
                        true
                    ),
                'add_value' => $previous_slug,
                'delete_expected' => $previous_slug !== $public_slug
                    && in_array(
                        $public_slug,
                        $values['_wp_old_slug'],
                        true
                    ),
                'delete_value' => $public_slug,
            ),
            '_wp_old_date' => array(
                'add_expected' => $previous_date !== $published_date
                    && ! empty($previous_date)
                    && ! in_array(
                        $previous_date,
                        $values['_wp_old_date'],
                        true
                    ),
                'add_value' => $previous_date,
                'delete_expected' => $previous_date !== $published_date
                    && in_array(
                        $published_date,
                        $values['_wp_old_date'],
                        true
                    ),
                'delete_value' => $published_date,
            ),
        );
    }

    private static function redirect_metadata_filter_stack_is_exact(
        $metadata_hook
    ) {
        global $wp_current_filter;
        if (! is_string($metadata_hook)
            || ! in_array(
                $metadata_hook,
                array('add_post_metadata', 'delete_post_metadata'),
                true
            )
            || ! is_array($wp_current_filter)
            || count($wp_current_filter) < 2) {
            return false;
        }
        $active_index = count($wp_current_filter) - 1;
        return $wp_current_filter[$active_index] === $metadata_hook
            && $wp_current_filter[$active_index - 1] === 'post_updated'
            && count(
                array_keys($wp_current_filter, 'post_updated', true)
            ) === 1
            && count(
                array_keys($wp_current_filter, $metadata_hook, true)
            ) === 1;
    }

    private function capture_publication_hook_snapshot()
    {
        global $wp_actions, $wp_filter;
        if (! is_array($wp_actions) || ! is_array($wp_filter)) {
            return false;
        }
        $snapshot = array();
        $callback_count = 0;
        $hook_names = array_merge(
            self::publication_replay_hook_names(),
            array('all')
        );
        foreach ($hook_names as $hook_name) {
            $hook_present = array_key_exists($hook_name, $wp_filter);
            $hook = $hook_present ? $wp_filter[$hook_name] : null;
            if ($hook_present && ! $hook instanceof WP_Hook) {
                return false;
            }
            $callbacks = array();
            if ($hook instanceof WP_Hook) {
                $callbacks = $hook->callbacks;
                if (! is_array($callbacks)
                    || ($hook_name !== 'all'
                        && array_key_exists(PHP_INT_MIN, $callbacks))) {
                    return false;
                }
                foreach ($callbacks as $priority_callbacks) {
                    if (! is_array($priority_callbacks)) {
                        return false;
                    }
                    $callback_count += count($priority_callbacks);
                    if ($callback_count > self::MAX_REPLAY_HOOK_CALLBACKS) {
                        return false;
                    }
                }
            }
            $action_present = array_key_exists($hook_name, $wp_actions);
            $action_count = $action_present ? $wp_actions[$hook_name] : 0;
            if (! is_int($action_count) || $action_count < 0) {
                return false;
            }
            $snapshot[$hook_name] = array(
                'action_count' => $action_count,
                'action_present' => $action_present,
                'callbacks' => $callbacks,
                'hook' => $hook,
                'hook_present' => $hook_present,
            );
        }
        return $snapshot;
    }

    private function publication_hook_snapshot_is_current(
        array $snapshot,
        array $action_increments
    ) {
        global $wp_actions, $wp_filter;
        $replay_hook_names = self::publication_replay_hook_names();
        $hook_names = array_merge($replay_hook_names, array('all'));
        if (! is_array($wp_actions)
            || ! is_array($wp_filter)
            || ! self::has_exact_keys($snapshot, $hook_names)
            || ! self::has_exact_keys($action_increments, $replay_hook_names)) {
            return false;
        }
        foreach ($hook_names as $hook_name) {
            $state = $snapshot[$hook_name];
            $increment = $hook_name === 'all'
                ? 0
                : $action_increments[$hook_name];
            if (! is_array($state)
                || ! self::has_exact_keys(
                    $state,
                    array(
                        'action_count',
                        'action_present',
                        'callbacks',
                        'hook',
                        'hook_present',
                    )
                )
                || ! is_bool($state['action_present'])
                || ! is_int($state['action_count'])
                || ! is_array($state['callbacks'])
                || ! is_bool($state['hook_present'])
                || ! is_int($increment)
                || $increment < 0
                || $increment > 2) {
                return false;
            }
            $hook_present = array_key_exists($hook_name, $wp_filter);
            if ($hook_present !== $state['hook_present']
                || ($hook_present
                    && (! $wp_filter[$hook_name] instanceof WP_Hook
                        || $wp_filter[$hook_name] !== $state['hook']
                        || $wp_filter[$hook_name]->callbacks
                            !== $state['callbacks']))) {
                return false;
            }
            $expected_count = $state['action_count'] + $increment;
            $action_present = array_key_exists($hook_name, $wp_actions);
            if ($action_present !== ($state['action_present'] || $increment > 0)
                || ($action_present
                    && (! is_int($wp_actions[$hook_name])
                        || $wp_actions[$hook_name] !== $expected_count))) {
                return false;
            }
        }
        return true;
    }

    private static function capture_publication_modified_times()
    {
        return self::publication_modified_times_from_gmt(
            gmdate('Y-m-d H:i:s')
        );
    }

    private static function publication_modified_times_from_gmt(
        $post_modified_gmt
    ) {
        $epoch = self::strict_mysql_utc_epoch($post_modified_gmt);
        if (! is_int($epoch)) {
            return false;
        }
        try {
            $site_timezone = wp_timezone();
            if (! $site_timezone instanceof DateTimeZone) {
                return false;
            }
            $utc_instant = (new DateTimeImmutable('@' . $epoch))->setTimezone(
                new DateTimeZone('UTC')
            );
            $instant = $utc_instant->setTimezone($site_timezone);
        } catch (Throwable $exception) {
            return false;
        }
        $post_modified = $instant->format('Y-m-d H:i:s');
        if ($utc_instant->format('Y-m-d H:i:s') !== $post_modified_gmt
            || $instant->getTimestamp() !== $utc_instant->getTimestamp()) {
            return false;
        }
        return array(
            'post_modified' => $post_modified,
            'post_modified_gmt' => $post_modified_gmt,
        );
    }

    private static function publication_date_fields(
        array $before,
        array $modified_times
    ) {
        if (! isset($before['storage']['restore']['post_fields'])
            || ! self::has_exact_keys(
                $modified_times,
                array('post_modified', 'post_modified_gmt')
            )
            || ! is_string($modified_times['post_modified'])
            || ! is_string($modified_times['post_modified_gmt'])) {
            return false;
        }
        $fields = $before['storage']['restore']['post_fields'];
        if (! is_array($fields)
            || ! isset($fields['post_date'], $fields['post_date_gmt'])) {
            return false;
        }
        $post_date = self::decode_exact_base64($fields['post_date']);
        $post_date_gmt = self::decode_exact_base64($fields['post_date_gmt']);
        if (! is_string($post_date) || ! is_string($post_date_gmt)) {
            return false;
        }
        if ($post_date_gmt === '0000-00-00 00:00:00') {
            $post_date = $modified_times['post_modified'];
            if (! function_exists('get_gmt_from_date')) {
                return false;
            }
            $post_date_gmt = get_gmt_from_date($post_date);
        }
        if (self::strict_mysql_utc_epoch($post_date) === null
            || self::strict_mysql_utc_epoch($post_date_gmt) === null) {
            return false;
        }
        return array(
            'post_date' => $post_date,
            'post_date_gmt' => $post_date_gmt,
        );
    }

    private function write_bounded_publication_rows(
        array $proposal,
        array $before,
        $mutex_name,
        array $modified_times
    ) {
        global $wpdb;
        if (! isset(
            $before['category_term_id'],
            $before['category_term_taxonomy_id'],
            $before['storage']['restore']['post_fields'],
            $before['storage']['restore']['term_relationships'],
            $before['storage']['summary']['category_term_taxonomy_ids']
        )
            || ! self::has_exact_keys(
                $modified_times,
                array('post_modified', 'post_modified_gmt')
            )
            || ! is_string($modified_times['post_modified'])
            || ! is_string($modified_times['post_modified_gmt'])) {
            return false;
        }
        $encoded_fields = $before['storage']['restore']['post_fields'];
        if (! is_array($encoded_fields)
            || ! self::has_exact_keys($encoded_fields, self::post_field_names())) {
            return false;
        }
        $post_fields = array();
        foreach (self::post_field_names() as $field_name) {
            $decoded = self::decode_exact_base64($encoded_fields[$field_name]);
            if (! is_string($decoded)) {
                return false;
            }
            $post_fields[$field_name] = $decoded;
        }
        $post_id = $proposal['draft_post_id'];
        $review_slug = 'raos-review-' . $proposal['public_slug'] . '-'
            . $proposal['snapshot_payload_sha256'];
        if ($post_fields['post_status'] !== 'draft'
            || $post_fields['post_name'] !== $review_slug
            || $post_fields['post_type'] !== 'post') {
            return false;
        }
        $publication_dates = self::publication_date_fields(
            $before,
            $modified_times
        );
        if (! is_array($publication_dates)) {
            return false;
        }

        $relationships = $before['storage']['restore']['term_relationships'];
        if (! is_array($relationships)
            || count($relationships) > self::MAX_TERM_RELATIONSHIPS) {
            return false;
        }
        $locked_relationships = $wpdb->get_results(
            $wpdb->prepare(
                "SELECT tr.term_taxonomy_id, tr.term_order
                 FROM {$wpdb->term_relationships} AS tr
                 WHERE tr.object_id = %d
                 ORDER BY tr.term_taxonomy_id ASC, tr.term_order ASC
                 FOR UPDATE",
                $post_id
            ),
            ARRAY_A
        );
        if ($wpdb->last_error !== ''
            || ! is_array($locked_relationships)
            || count($locked_relationships) !== count($relationships)) {
            return false;
        }
        foreach ($locked_relationships as $index => $locked_relationship) {
            if (! isset(
                $locked_relationship['term_taxonomy_id'],
                $locked_relationship['term_order'],
                $relationships[$index]['term_taxonomy_id'],
                $relationships[$index]['term_order']
            )
                || (int) $locked_relationship['term_taxonomy_id']
                    !== (int) $relationships[$index]['term_taxonomy_id']
                || (int) $locked_relationship['term_order']
                    !== (int) $relationships[$index]['term_order']) {
                return false;
            }
        }

        $target_term_id = (int) $before['category_term_id'];
        $target_tt_id = (int) $before['category_term_taxonomy_id'];
        $locked_category = $wpdb->get_row(
            $wpdb->prepare(
                "SELECT t.term_id, tt.term_taxonomy_id
                 FROM {$wpdb->terms} AS t
                 INNER JOIN {$wpdb->term_taxonomy} AS tt
                    ON tt.term_id = t.term_id
                 WHERE t.term_id = %d AND tt.term_taxonomy_id = %d
                   AND BINARY t.name = BINARY %s
                   AND BINARY tt.taxonomy = BINARY %s
                 FOR UPDATE",
                $target_term_id,
                $target_tt_id,
                RAOS_ST1704_Publication_Bindings_V2::CATEGORY_NAME,
                'category'
            ),
            ARRAY_A
        );
        if ($wpdb->last_error !== ''
            || ! is_array($locked_category)
            || ! isset(
                $locked_category['term_id'],
                $locked_category['term_taxonomy_id']
            )
            || (int) $locked_category['term_id'] !== $target_term_id
            || (int) $locked_category['term_taxonomy_id'] !== $target_tt_id) {
            return false;
        }
        $slug_conflicts = $wpdb->get_col(
            $wpdb->prepare(
                "SELECT ID FROM {$wpdb->posts}
                 WHERE ID <> %d AND BINARY post_name = BINARY %s
                 ORDER BY ID ASC LIMIT 2 FOR UPDATE",
                $post_id,
                $proposal['public_slug']
            )
        );
        if ($wpdb->last_error !== ''
            || ! is_array($slug_conflicts)
            || count($slug_conflicts) !== 0) {
            return false;
        }

        $old_category_tt_ids = $before['storage']['summary']
            ['category_term_taxonomy_ids'];
        if (! is_array($old_category_tt_ids)
            || count($old_category_tt_ids) > self::MAX_TERM_RELATIONSHIPS) {
            return false;
        }
        foreach ($old_category_tt_ids as $old_tt_id) {
            if (! is_int($old_tt_id) || $old_tt_id < 1) {
                return false;
            }
        }
        $normalized_old_tt_ids = array_values(
            array_unique($old_category_tt_ids)
        );
        sort($normalized_old_tt_ids, SORT_NUMERIC);
        if ($normalized_old_tt_ids !== $old_category_tt_ids) {
            return false;
        }

        $deleted_categories = $wpdb->query(
            $wpdb->prepare(
                "DELETE tr FROM {$wpdb->term_relationships} AS tr
                 INNER JOIN {$wpdb->term_taxonomy} AS tt
                    ON tt.term_taxonomy_id = tr.term_taxonomy_id
                 WHERE tr.object_id = %d
                   AND BINARY tt.taxonomy = BINARY %s
                   AND (IS_USED_LOCK(%s) = CONNECTION_ID())",
                $post_id,
                'category',
                $mutex_name
            )
        );
        if ($deleted_categories === false
            || $deleted_categories !== count($old_category_tt_ids)
            || $wpdb->query(
                $wpdb->prepare(
                    "INSERT INTO {$wpdb->term_relationships}
                        (object_id, term_taxonomy_id, term_order)
                     SELECT %d, %d, %d
                     WHERE (IS_USED_LOCK(%s) = CONNECTION_ID())",
                    $post_id,
                    $target_tt_id,
                    0,
                    $mutex_name
                )
            ) !== 1) {
            return false;
        }
        $post_updated = $wpdb->query(
            $wpdb->prepare(
                "UPDATE {$wpdb->posts}
                 SET post_name = %s, post_status = %s,
                     post_date = %s, post_date_gmt = %s,
                     post_modified = %s, post_modified_gmt = %s
                 WHERE ID = %d
                   AND BINARY post_name = BINARY %s
                   AND BINARY post_status = BINARY %s
                   AND BINARY post_date = BINARY %s
                   AND BINARY post_date_gmt = BINARY %s
                   AND BINARY post_type = BINARY %s
                   AND (IS_USED_LOCK(%s) = CONNECTION_ID())",
                $proposal['public_slug'],
                'publish',
                $publication_dates['post_date'],
                $publication_dates['post_date_gmt'],
                $modified_times['post_modified'],
                $modified_times['post_modified_gmt'],
                $post_id,
                $review_slug,
                'draft',
                $post_fields['post_date'],
                $post_fields['post_date_gmt'],
                'post',
                $mutex_name
            )
        );
        if ($post_updated !== 1) {
            return false;
        }

        $post_before_fields = array_merge(array('ID' => $post_id), $post_fields);
        $post_before = new WP_Post((object) $post_before_fields);
        return array(
            'added_category_tt_ids' => in_array(
                $target_tt_id,
                $old_category_tt_ids,
                true
            ) ? array() : array($target_tt_id),
            'deleted_category_tt_ids' => array_values(
                array_diff($old_category_tt_ids, array($target_tt_id))
            ),
            'old_category_tt_ids' => $old_category_tt_ids,
            'post_before' => $post_before,
            'target_term_id' => $target_term_id,
            'target_tt_id' => $target_tt_id,
        );
    }

    private function apply_one_publication(
        array $proposal,
        array $before,
        $mutex_name,
        array $modified_times
    ) {
        global $wpdb;
        $post_id = $proposal['draft_post_id'];
        $external_effects_possible = false;
        $expected_modified_times = isset($modified_times['post_modified_gmt'])
            ? self::publication_modified_times_from_gmt(
                $modified_times['post_modified_gmt']
            )
            : false;
        if (! is_array($expected_modified_times)
            || $expected_modified_times !== $modified_times) {
            return array(
                'ok' => false,
                'state' => 'FAILED',
                'code' => 'PUBLICATION_MODIFIED_TIME_INVALID',
            );
        }
        $publication_dates = self::publication_date_fields(
            $before,
            $modified_times
        );
        if (! is_array($publication_dates)) {
            return array(
                'ok' => false,
                'state' => 'FAILED',
                'code' => 'PUBLICATION_DATE_INVALID',
            );
        }
        if (! function_exists('wp_after_insert_post')) {
            return array(
                'ok' => false,
                'state' => 'FAILED',
                'code' => 'WORDPRESS_POST_INSERT_PHASE_UNAVAILABLE',
            );
        }
        if (! $this->publication_mutex_is_owned($mutex_name)
            || wp_check_post_lock($post_id) !== false) {
            return array(
                'ok' => false,
                'state' => 'FAILED',
                'code' => 'POST_LOCKED_BEFORE_MUTATION',
            );
        }
        try {
            if ($wpdb->query('START TRANSACTION') === false) {
                return array(
                    'ok' => false,
                    'state' => 'NEEDS_RECOVERY',
                    'code' => 'MUTATION_TRANSACTION_UNAVAILABLE',
                );
            }
            $locked_id = $wpdb->get_var(
                $wpdb->prepare(
                    "SELECT ID FROM {$wpdb->posts} WHERE ID = %d FOR UPDATE",
                    $post_id
                )
            );
            if ($wpdb->last_error !== ''
                || (int) $locked_id !== $post_id
                || ! $this->publication_mutex_is_owned($mutex_name)
                || wp_check_post_lock($post_id) !== false
                || ! $this->before_state_matches($proposal, $before)) {
                $wpdb->query('ROLLBACK');
                return array(
                    'ok' => false,
                    'state' => $this->before_state_matches($proposal, $before)
                        ? 'FAILED'
                        : 'NEEDS_RECOVERY',
                    'code' => 'LOCKED_PRESTATE_CHANGED',
                );
            }

            $hook_snapshot = $this->capture_publication_hook_snapshot();
            if (! self::publication_core_redirect_callbacks_are_exact()
                || ! is_array($hook_snapshot)) {
                $wpdb->query('ROLLBACK');
                return $this->mutation_failure_result(
                    $proposal,
                    $before,
                    'HOOK_REGISTRY_CAPTURE_FAILED',
                    false,
                    $mutex_name
                );
            }
            if (! $this->publication_pre_mutation_hooks_are_unobserved()) {
                $wpdb->query('ROLLBACK');
                return $this->mutation_failure_result(
                    $proposal,
                    $before,
                    'PRE_MUTATION_HOOK_OBSERVER_UNSUPPORTED',
                    false,
                    $mutex_name
                );
            }
            $mutation = $this->write_bounded_publication_rows(
                $proposal,
                $before,
                $mutex_name,
                $modified_times
            );
            if (! is_array($mutation)
                || ! $mutation['post_before'] instanceof WP_Post
                || ! $this->publication_mutex_is_owned($mutex_name)) {
                $wpdb->query('ROLLBACK');
                return $this->mutation_failure_result(
                    $proposal,
                    $before,
                    'BOUNDED_PUBLICATION_WRITE_FAILED',
                    false,
                    $mutex_name
                );
            }
            $redirect_meta_plan = self::publication_redirect_meta_plan(
                $before,
                $mutation['post_before'],
                $publication_dates,
                $proposal['public_slug']
            );
            if (! is_array($redirect_meta_plan)) {
                $wpdb->query('ROLLBACK');
                return $this->mutation_failure_result(
                    $proposal,
                    $before,
                    'CORE_REDIRECT_META_PLAN_INVALID',
                    true,
                    $mutex_name,
                    $modified_times
                );
            }
            if (! $this->published_state_matches(
                $proposal,
                $before,
                $modified_times
            )) {
                $wpdb->query('ROLLBACK');
                return $this->mutation_failure_result(
                    $proposal,
                    $before,
                    'POST_WRITE_DRIFT_DETECTED',
                    true,
                    $mutex_name,
                    $modified_times
                );
            }
            $zero_action_increments = array_fill_keys(
                self::publication_replay_hook_names(),
                0
            );
            if (! $this->publication_hook_snapshot_is_current(
                $hook_snapshot,
                $zero_action_increments
            )) {
                $wpdb->query('ROLLBACK');
                return $this->mutation_failure_result(
                    $proposal,
                    $before,
                    'PRE_COMMIT_HOOK_REGISTRY_CHANGED',
                    true,
                    $mutex_name,
                    $modified_times
                );
            }
            if ($wpdb->query('COMMIT') === false) {
                $wpdb->query('ROLLBACK');
                return $this->mutation_failure_result(
                    $proposal,
                    $before,
                    'POST_COMMIT_UNCERTAIN',
                    true,
                    $mutex_name,
                    $modified_times
                );
            }

            // The content/category mutation is now durable. From this point on,
            // any cache, taxonomy, or publication callback may have an external
            // effect, so no failure path is allowed to restore the draft.
            $external_effects_possible = true;

            // WordPress 7.1 core `_publish_post_hook()` passes unique=true for
            // `_pingme` and `_encloseme`; only `_trackbackme` uses the default
            // unique=false shape. Its priority-12 `post_updated` callbacks also
            // maintain redirect metadata. Suppress only their exact add/delete
            // API shapes while that one hook is active, so the private Review
            // URL cannot become a redirect and all stored metadata stays bound
            // to the immutable pre-state.
            $redirect_meta_phase = self::REDIRECT_META_PHASE_INACTIVE;
            $redirect_meta_suppression_counts = array(
                'add' => array(
                    '_wp_old_slug' => 0,
                    '_wp_old_date' => 0,
                ),
                'delete' => array(
                    '_wp_old_slug' => 0,
                    '_wp_old_date' => 0,
                ),
            );
            $core_queue_meta_suppressor = function (
                $check,
                $object_id,
                $meta_key,
                $meta_value,
                $unique
            ) use (
                $post_id,
                $redirect_meta_plan,
                &$redirect_meta_phase,
                &$redirect_meta_suppression_counts
            ) {
                if (! is_string($redirect_meta_phase)
                    || ! in_array(
                        $redirect_meta_phase,
                        array(
                            self::REDIRECT_META_PHASE_INACTIVE,
                            self::REDIRECT_META_PHASE_POST_UPDATED,
                        ),
                        true
                    )) {
                    throw new RuntimeException('redirect metadata phase invalid');
                }
                if ($redirect_meta_phase
                        === self::REDIRECT_META_PHASE_POST_UPDATED
                    && array_key_exists($meta_key, $redirect_meta_plan)) {
                    $shape = $redirect_meta_plan[$meta_key];
                    if ($check !== null
                        || ! is_int($object_id)
                        || $object_id !== $post_id
                        || ! is_string($meta_value)
                        || $meta_value !== $shape['add_value']
                        || $unique !== false
                        || $shape['add_expected'] !== true
                        || $redirect_meta_suppression_counts['add'][$meta_key]
                            !== 0
                        || ! self::redirect_metadata_filter_stack_is_exact(
                            'add_post_metadata'
                        )) {
                        throw new RuntimeException(
                            'redirect metadata add shape refused'
                        );
                    }
                    $redirect_meta_suppression_counts['add'][$meta_key] = 1;
                    return false;
                }
                $unique_queue_marker = ($meta_key === '_encloseme'
                        || $meta_key === '_pingme')
                    && $unique === true;
                $trackback_queue_marker = $meta_key === '_trackbackme'
                    && $unique === false;
                if ((int) $object_id === $post_id
                    && $meta_value === '1'
                    && ($unique_queue_marker || $trackback_queue_marker)) {
                    return false;
                }
                return $check;
            };
            $core_redirect_meta_delete_suppressor = function (
                $check,
                $object_id,
                $meta_key,
                $meta_value,
                $delete_all
            ) use (
                $post_id,
                $redirect_meta_plan,
                &$redirect_meta_phase,
                &$redirect_meta_suppression_counts
            ) {
                if (! is_string($redirect_meta_phase)
                    || ! in_array(
                        $redirect_meta_phase,
                        array(
                            self::REDIRECT_META_PHASE_INACTIVE,
                            self::REDIRECT_META_PHASE_POST_UPDATED,
                        ),
                        true
                    )) {
                    throw new RuntimeException('redirect metadata phase invalid');
                }
                if ($redirect_meta_phase
                        !== self::REDIRECT_META_PHASE_POST_UPDATED
                    || ! array_key_exists($meta_key, $redirect_meta_plan)) {
                    return $check;
                }
                $shape = $redirect_meta_plan[$meta_key];
                if ($check !== null
                    || ! is_int($object_id)
                    || $object_id !== $post_id
                    || ! is_string($meta_value)
                    || $meta_value !== $shape['delete_value']
                    || $delete_all !== false
                    || $shape['delete_expected'] !== true
                    || $redirect_meta_suppression_counts['delete'][$meta_key]
                        !== 0
                    || ! self::redirect_metadata_filter_stack_is_exact(
                        'delete_post_metadata'
                    )) {
                    throw new RuntimeException(
                        'redirect metadata delete shape refused'
                    );
                }
                $redirect_meta_suppression_counts['delete'][$meta_key] = 1;
                return false;
            };
            $replay_hook_names = self::publication_replay_hook_names();
            $nested_revision_increments = $zero_action_increments;
            $nested_revision_hook_sequence = array(
                'pre_post_insert',
                'transition_post_status',
                'new_to_inherit',
                'inherit_revision',
                'save_post_revision',
                'save_post',
                'wp_insert_post',
                'wp_after_insert_post',
                '_wp_put_post_revision',
            );
            $nested_revision_phase = 0;
            $nested_revision_id = null;
            $revision_expected_fields = array(
                'post_content' => $mutation['post_before']->post_content,
                'post_excerpt' => $mutation['post_before']->post_excerpt,
                'post_title' => $mutation['post_before']->post_title,
            );
            $replay_hook_reentry_guard = function (...$arguments) use (
                $post_id,
                $replay_hook_names,
                $nested_revision_hook_sequence,
                $revision_expected_fields,
                &$nested_revision_increments,
                &$nested_revision_phase,
                &$nested_revision_id
            ) {
                global $wp_current_filter;
                if (! is_array($wp_current_filter)
                    || count($wp_current_filter) === 0) {
                    throw new RuntimeException('replay hook stack unavailable');
                }
                $replay_depth = 0;
                foreach ($wp_current_filter as $stack_hook) {
                    if (in_array($stack_hook, $replay_hook_names, true)) {
                        ++$replay_depth;
                    }
                }
                if ($replay_depth === 1) {
                    return;
                }
                $active_hook = $wp_current_filter[
                    count($wp_current_filter) - 1
                ];
                $parent_hook = count($wp_current_filter) >= 2
                    ? $wp_current_filter[count($wp_current_filter) - 2]
                    : null;
                $revision_post = null;
                $revision_data_valid = false;
                $revision_shape_valid = false;
                if ($active_hook === 'pre_post_insert'
                    && count($arguments) === 1
                    && is_array($arguments[0])
                    && isset(
                        $arguments[0]['post_content'],
                        $arguments[0]['post_excerpt'],
                        $arguments[0]['post_parent'],
                        $arguments[0]['post_status'],
                        $arguments[0]['post_title'],
                        $arguments[0]['post_type']
                    )
                    && $arguments[0]['post_type'] === 'revision'
                    && $arguments[0]['post_status'] === 'inherit'
                    && (int) $arguments[0]['post_parent'] === $post_id
                    && $arguments[0]['post_content']
                        === $revision_expected_fields['post_content']
                    && $arguments[0]['post_excerpt']
                        === $revision_expected_fields['post_excerpt']
                    && $arguments[0]['post_title']
                        === $revision_expected_fields['post_title']) {
                    $revision_data_valid = true;
                } elseif ($active_hook === 'transition_post_status'
                    && count($arguments) === 3
                    && $arguments[0] === 'inherit'
                    && $arguments[1] === 'new'
                    && $arguments[2] instanceof WP_Post) {
                    $revision_post = $arguments[2];
                    $revision_shape_valid = true;
                } elseif ($active_hook === 'new_to_inherit'
                    && count($arguments) === 1
                    && $arguments[0] instanceof WP_Post) {
                    $revision_post = $arguments[0];
                    $revision_shape_valid = true;
                } elseif ($active_hook === 'inherit_revision'
                    && count($arguments) === 3
                    && $arguments[1] instanceof WP_Post
                    && $arguments[2] === 'new'
                    && (int) $arguments[0] === (int) $arguments[1]->ID) {
                    $revision_post = $arguments[1];
                    $revision_shape_valid = true;
                } elseif (in_array(
                    $active_hook,
                    array(
                        'save_post_revision',
                        'save_post',
                        'wp_insert_post',
                    ),
                    true
                )
                    && count($arguments) === 3
                    && $arguments[1] instanceof WP_Post
                    && $arguments[2] === false
                    && (int) $arguments[0] === (int) $arguments[1]->ID) {
                    $revision_post = $arguments[1];
                    $revision_shape_valid = true;
                } elseif ($active_hook === 'wp_after_insert_post'
                    && count($arguments) === 4
                    && $arguments[1] instanceof WP_Post
                    && $arguments[2] === false
                    && $arguments[3] === null
                    && (int) $arguments[0] === (int) $arguments[1]->ID) {
                    $revision_post = $arguments[1];
                    $revision_shape_valid = true;
                } elseif ($active_hook === '_wp_put_post_revision'
                    && count($arguments) === 2
                    && is_int($arguments[0])
                    && $arguments[0] > 0
                    && (int) $arguments[1] === $post_id) {
                    $revision_post = get_post($arguments[0]);
                    $revision_shape_valid = $revision_post instanceof WP_Post;
                }
                if ($replay_depth === 2
                    && $parent_hook === 'wp_after_insert_post'
                    && isset(
                        $nested_revision_hook_sequence[$nested_revision_phase]
                    )
                    && $nested_revision_hook_sequence[$nested_revision_phase]
                        === $active_hook
                    && array_key_exists(
                        $active_hook,
                        $nested_revision_increments
                    )) {
                    if ($active_hook === 'pre_post_insert') {
                        if (! $revision_data_valid
                            || $nested_revision_id !== null) {
                            throw new RuntimeException(
                                'revision insert payload refused'
                            );
                        }
                    } elseif (! $revision_shape_valid
                        || ! $revision_post instanceof WP_Post
                        || $revision_post->post_type !== 'revision'
                        || (int) $revision_post->post_parent !== $post_id
                        || ($nested_revision_id !== null
                            && $nested_revision_id
                                !== (int) $revision_post->ID)) {
                        throw new RuntimeException(
                            'revision lifecycle shape refused'
                        );
                    } elseif ($nested_revision_id === null) {
                        $nested_revision_id = (int) $revision_post->ID;
                    }
                    ++$nested_revision_increments[$active_hook];
                    if ($nested_revision_increments[$active_hook] <= 1) {
                        ++$nested_revision_phase;
                        return;
                    }
                }
                throw new RuntimeException('nested publication replay refused');
            };
            $guarded_hooks = array();
            $guards_added = add_filter(
                'add_post_metadata',
                $core_queue_meta_suppressor,
                PHP_INT_MAX,
                5
            );
            $guards_added = add_filter(
                'delete_post_metadata',
                $core_redirect_meta_delete_suppressor,
                PHP_INT_MAX,
                5
            ) && $guards_added;
            foreach ($replay_hook_names as $hook_name) {
                if (! add_action(
                    $hook_name,
                    $replay_hook_reentry_guard,
                    PHP_INT_MIN,
                    4
                )) {
                    $guards_added = false;
                    break;
                }
                $guarded_hooks[] = $hook_name;
            }
            if (! $guards_added) {
                foreach ($guarded_hooks as $hook_name) {
                    remove_action(
                        $hook_name,
                        $replay_hook_reentry_guard,
                        PHP_INT_MIN
                    );
                }
                remove_filter(
                    'add_post_metadata',
                    $core_queue_meta_suppressor,
                    PHP_INT_MAX
                );
                remove_filter(
                    'delete_post_metadata',
                    $core_redirect_meta_delete_suppressor,
                    PHP_INT_MAX
                );
                return array(
                    'ok' => false,
                    'state' => 'NEEDS_RECOVERY',
                    'code' => 'POST_COMMIT_HOOK_GUARD_FAILED',
                );
            }
            $assert_guards_current = function () use (
                $core_queue_meta_suppressor,
                $core_redirect_meta_delete_suppressor,
                &$redirect_meta_phase,
                $replay_hook_names,
                $replay_hook_reentry_guard
            ) {
                if (! is_string($redirect_meta_phase)
                    || ! in_array(
                        $redirect_meta_phase,
                        array(
                            self::REDIRECT_META_PHASE_INACTIVE,
                            self::REDIRECT_META_PHASE_POST_UPDATED,
                        ),
                        true
                    )
                    || ! self::publication_core_redirect_callbacks_are_exact()
                    || has_filter(
                        'add_post_metadata',
                        $core_queue_meta_suppressor
                    ) !== PHP_INT_MAX
                    || has_filter(
                        'delete_post_metadata',
                        $core_redirect_meta_delete_suppressor
                    ) !== PHP_INT_MAX) {
                    throw new RuntimeException('metadata guard changed');
                }
                foreach ($replay_hook_names as $hook_name) {
                    if (has_filter(
                        $hook_name,
                        $replay_hook_reentry_guard
                    ) !== PHP_INT_MIN) {
                        throw new RuntimeException('replay guard changed');
                    }
                }
            };
            $action_increments = $zero_action_increments;
                $replay_completed = false;
                $replay_guards_removed = true;
                try {
                    $assert_guards_current();
                    if (count($mutation['added_category_tt_ids']) === 1) {
                        do_action(
                            'added_term_relationship',
                            $post_id,
                        $mutation['target_tt_id'],
                        'category'
                    );
                    $action_increments['added_term_relationship'] = 1;
                    if (wp_update_term_count_now(
                        $mutation['added_category_tt_ids'],
                        'category'
                    ) !== true) {
                        throw new RuntimeException('added term recount failed');
                    }
                }
                if (count($mutation['deleted_category_tt_ids']) > 0) {
                    wp_cache_delete($post_id, 'category_relationships');
                    wp_cache_set_terms_last_changed();
                    $assert_guards_current();
                    do_action(
                        'deleted_term_relationships',
                        $post_id,
                        $mutation['deleted_category_tt_ids'],
                        'category'
                    );
                    $action_increments['deleted_term_relationships'] = 1;
                    if (wp_update_term_count_now(
                        $mutation['deleted_category_tt_ids'],
                        'category'
                    ) !== true) {
                        throw new RuntimeException('deleted term recount failed');
                    }
                }
                wp_cache_delete($post_id, 'category_relationships');
                wp_cache_set_terms_last_changed();
                $assert_guards_current();
                do_action(
                    'set_object_terms',
                    $post_id,
                    array($mutation['target_term_id']),
                    array($mutation['target_tt_id']),
                    'category',
                    false,
                    $mutation['old_category_tt_ids']
                );
                $action_increments['set_object_terms'] = 1;
                clean_post_cache($post_id);
                clean_object_term_cache($post_id, 'post');
                if (! $this->publication_mutex_is_owned($mutex_name)
                    || ! $this->published_state_matches(
                        $proposal,
                        $before,
                        $modified_times
                    )) {
                    throw new RuntimeException('post-commit readback drift');
                }
                $published_post = get_post($post_id);
                if (! $published_post instanceof WP_Post
                    || (int) $published_post->ID !== $post_id
                    || $published_post->post_status !== 'publish'
                    || $published_post->post_type !== 'post'
                    || ! hash_equals(
                        $publication_dates['post_date'],
                        $published_post->post_date
                    )
                    || ! hash_equals(
                        $publication_dates['post_date_gmt'],
                        $published_post->post_date_gmt
                    )
                    || ! hash_equals(
                        $modified_times['post_modified'],
                        $published_post->post_modified
                    )
                    || ! hash_equals(
                        $modified_times['post_modified_gmt'],
                        $published_post->post_modified_gmt
                    )) {
                    throw new RuntimeException('published post unavailable');
                }

                $assert_guards_current();
                do_action(
                    'transition_post_status',
                    'publish',
                    'draft',
                    $published_post
                );
                $action_increments['transition_post_status'] = 1;
                $assert_guards_current();
                do_action('draft_to_publish', $published_post);
                $action_increments['draft_to_publish'] = 1;
                $assert_guards_current();
                do_action(
                    'publish_post',
                    $post_id,
                    $published_post,
                    'draft'
                );
                $action_increments['publish_post'] = 1;
                $assert_guards_current();
                do_action('edit_post_post', $post_id, $published_post);
                $action_increments['edit_post_post'] = 1;
                $assert_guards_current();
                do_action('edit_post', $post_id, $published_post);
                $action_increments['edit_post'] = 1;
                $post_after = get_post($post_id);
                if (! $post_after instanceof WP_Post
                    || (int) $post_after->ID !== $post_id
                    || ! hash_equals(
                        $publication_dates['post_date'],
                        $post_after->post_date
                    )
                    || ! hash_equals(
                        $publication_dates['post_date_gmt'],
                        $post_after->post_date_gmt
                    )
                    || ! hash_equals(
                        $modified_times['post_modified'],
                        $post_after->post_modified
                    )
                    || ! hash_equals(
                        $modified_times['post_modified_gmt'],
                        $post_after->post_modified_gmt
                    )) {
                    throw new RuntimeException('updated post unavailable');
                }
                $assert_guards_current();
                if ($redirect_meta_phase
                    !== self::REDIRECT_META_PHASE_INACTIVE) {
                    throw new RuntimeException(
                        'redirect metadata phase transition refused'
                    );
                }
                $redirect_meta_phase = self::REDIRECT_META_PHASE_POST_UPDATED;
                try {
                    do_action(
                        'post_updated',
                        $post_id,
                        $post_after,
                        $mutation['post_before']
                    );
                } finally {
                    $redirect_meta_phase = self::REDIRECT_META_PHASE_INACTIVE;
                }
                $action_increments['post_updated'] = 1;
                foreach ($redirect_meta_plan as $meta_key => $shape) {
                    $expected_add_count = $shape['add_expected'] ? 1 : 0;
                    $expected_delete_count = $shape['delete_expected'] ? 1 : 0;
                    if ($redirect_meta_suppression_counts['add'][$meta_key]
                            !== $expected_add_count
                        || $redirect_meta_suppression_counts['delete'][$meta_key]
                            !== $expected_delete_count) {
                        throw new RuntimeException(
                            'redirect metadata suppression incomplete'
                        );
                    }
                }
                $assert_guards_current();
                do_action(
                    'save_post_post',
                    $post_id,
                    $published_post,
                    true
                );
                $action_increments['save_post_post'] = 1;
                $assert_guards_current();
                do_action('save_post', $post_id, $published_post, true);
                $action_increments['save_post'] = 1;
                $assert_guards_current();
                do_action('wp_insert_post', $post_id, $published_post, true);
                $action_increments['wp_insert_post'] = 1;
                $assert_guards_current();
                wp_after_insert_post(
                    $published_post,
                    true,
                    $mutation['post_before']
                );
                $action_increments['wp_after_insert_post'] = 1;
                if ($nested_revision_phase !== 0
                    && $nested_revision_phase
                        !== count($nested_revision_hook_sequence)) {
                    throw new RuntimeException(
                        'revision lifecycle replay incomplete'
                    );
                }
                if ($nested_revision_phase > 0) {
                    $saved_revision = get_post($nested_revision_id);
                    if (! $saved_revision instanceof WP_Post
                        || $saved_revision->post_type !== 'revision'
                        || (int) $saved_revision->post_parent !== $post_id
                        || $saved_revision->post_content
                            !== $revision_expected_fields['post_content']
                        || $saved_revision->post_excerpt
                            !== $revision_expected_fields['post_excerpt']
                        || $saved_revision->post_title
                            !== $revision_expected_fields['post_title']) {
                        throw new RuntimeException(
                            'revision lifecycle result unavailable'
                        );
                    }
                }
                foreach (
                    $nested_revision_increments as $hook_name => $increment
                ) {
                    $action_increments[$hook_name] += $increment;
                }
                $replay_completed = true;
            } finally {
                $redirect_meta_phase_was_inactive = $redirect_meta_phase
                    === self::REDIRECT_META_PHASE_INACTIVE;
                $redirect_meta_phase = self::REDIRECT_META_PHASE_INACTIVE;
                foreach ($guarded_hooks as $hook_name) {
                    $replay_guards_removed = remove_action(
                        $hook_name,
                        $replay_hook_reentry_guard,
                        PHP_INT_MIN
                    ) && $replay_guards_removed;
                }
                $add_meta_guard_removed = remove_filter(
                    'add_post_metadata',
                    $core_queue_meta_suppressor,
                    PHP_INT_MAX
                );
                $delete_meta_guard_removed = remove_filter(
                    'delete_post_metadata',
                    $core_redirect_meta_delete_suppressor,
                    PHP_INT_MAX
                );
                $replay_guards_removed = $redirect_meta_phase_was_inactive
                    && $add_meta_guard_removed
                    && $delete_meta_guard_removed
                    && has_filter(
                        'add_post_metadata',
                        $core_queue_meta_suppressor
                    ) === false
                    && has_filter(
                        'delete_post_metadata',
                        $core_redirect_meta_delete_suppressor
                    ) === false
                    && $replay_guards_removed;
            }
            if (! $replay_completed
                || ! $replay_guards_removed
                || ! $this->publication_mutex_is_owned($mutex_name)
                || ! $this->publication_hook_snapshot_is_current(
                    $hook_snapshot,
                    $action_increments
                )
                || ! $this->published_state_matches(
                    $proposal,
                    $before,
                    $modified_times
                )) {
                return array(
                    'ok' => false,
                    'state' => 'NEEDS_RECOVERY',
                    'code' => 'POST_COMMIT_HOOK_REPLAY_UNCERTAIN',
                );
            }
            return array(
                'ok' => true,
                'state' => 'APPLIED',
                'code' => self::RESULT_CODE,
                'modified_times' => $modified_times,
            );
        } catch (Throwable $exception) {
            if ($external_effects_possible) {
                return array(
                    'ok' => false,
                    'state' => 'NEEDS_RECOVERY',
                    'code' => 'POST_COMMIT_HOOK_REPLAY_EXCEPTION',
                );
            }
            $wpdb->query('ROLLBACK');
            return $this->mutation_failure_result(
                $proposal,
                $before,
                'PUBLICATION_EXCEPTION',
                true,
                $mutex_name,
                $modified_times
            );
        }
    }

    private function mutation_failure_result(
        array $proposal,
        array $before,
        $code,
        $restore_if_needed,
        $mutex_name,
        $modified_times = null
    ) {
        $post_id = $proposal['draft_post_id'];
        clean_post_cache($post_id);
        clean_object_term_cache($post_id, 'post');
        if ($this->before_state_matches($proposal, $before)) {
            return array('ok' => false, 'state' => 'FAILED', 'code' => $code);
        }
        if ($restore_if_needed
            && is_array($modified_times)
            && $this->publication_mutex_is_owned($mutex_name)
            && $this->rollback_post_state(
                $proposal,
                $before,
                $modified_times,
                $mutex_name
            )
            && $this->before_state_matches($proposal, $before)) {
            return array(
                'ok' => false,
                'state' => 'FAILED',
                'code' => $code . '_ROLLED_BACK',
            );
        }
        return array(
            'ok' => false,
            'state' => 'NEEDS_RECOVERY',
            'code' => $code . '_RECOVERY_UNCERTAIN',
        );
    }

    private static function decode_exact_base64($encoded)
    {
        if (! is_string($encoded)) {
            return null;
        }
        $decoded = base64_decode($encoded, true);
        return is_string($decoded) && base64_encode($decoded) === $encoded
            ? $decoded
            : null;
    }

    private function rollback_post_state(
        array $proposal,
        array $before,
        array $modified_times,
        $mutex_name
    ) {
        global $wpdb;
        if (! isset(
            $before['draft_post_id'],
            $before['category_term_taxonomy_id'],
            $before['storage']['restore']['post_fields'],
            $before['storage']['restore']['term_relationships'],
            $before['storage']['summary']['category_term_taxonomy_ids']
        )
            || (int) $before['draft_post_id'] !== $proposal['draft_post_id']
            || ! self::has_exact_keys(
                $modified_times,
                array('post_modified', 'post_modified_gmt')
            )
            || ! is_string($modified_times['post_modified'])
            || ! is_string($modified_times['post_modified_gmt'])
            || ! $this->publication_mutex_is_owned($mutex_name)) {
            return false;
        }
        $restore = $before['storage']['restore'];
        if (! is_array($restore['post_fields'])
            || ! self::has_exact_keys(
                $restore['post_fields'],
                self::post_field_names()
            )
            || ! is_array($restore['term_relationships'])
            || count($restore['term_relationships'])
                > self::MAX_TERM_RELATIONSHIPS) {
            return false;
        }
        $post_fields = array();
        foreach (
            array(
                'post_date',
                'post_date_gmt',
                'post_modified',
                'post_modified_gmt',
                'post_name',
                'post_status',
                'post_type',
            ) as $field
        ) {
            $decoded = self::decode_exact_base64(
                $restore['post_fields'][$field]
            );
            if (! is_string($decoded)) {
                return false;
            }
            $post_fields[$field] = $decoded;
        }
        $review_slug = 'raos-review-' . $proposal['public_slug'] . '-'
            . $proposal['snapshot_payload_sha256'];
        if ($post_fields['post_name'] !== $review_slug
            || $post_fields['post_status'] !== 'draft'
            || $post_fields['post_type'] !== 'post') {
            return false;
        }
        $publication_dates = self::publication_date_fields(
            $before,
            $modified_times
        );
        if (! is_array($publication_dates)) {
            return false;
        }

        $old_category_tt_ids = $before['storage']['summary']
            ['category_term_taxonomy_ids'];
        if (! is_array($old_category_tt_ids)
            || count($old_category_tt_ids) > self::MAX_TERM_RELATIONSHIPS) {
            return false;
        }
        foreach ($old_category_tt_ids as $old_tt_id) {
            if (! is_int($old_tt_id) || $old_tt_id < 1) {
                return false;
            }
        }
        $normalized_old_tt_ids = array_values(
            array_unique($old_category_tt_ids)
        );
        sort($normalized_old_tt_ids, SORT_NUMERIC);
        if ($normalized_old_tt_ids !== $old_category_tt_ids) {
            return false;
        }
        $old_category_relationships = array();
        foreach ($restore['term_relationships'] as $relationship) {
            if (! self::has_exact_keys(
                $relationship,
                array('term_order', 'term_taxonomy_id')
            )
                || ! is_int($relationship['term_order'])
                || $relationship['term_order'] < 0
                || ! is_int($relationship['term_taxonomy_id'])
                || $relationship['term_taxonomy_id'] < 1) {
                return false;
            }
            if (in_array(
                $relationship['term_taxonomy_id'],
                $old_category_tt_ids,
                true
            )) {
                $old_category_relationships[] = $relationship;
            }
        }
        $relationship_tt_ids = array_map(
            function ($relationship) {
                return $relationship['term_taxonomy_id'];
            },
            $old_category_relationships
        );
        sort($relationship_tt_ids, SORT_NUMERIC);
        if ($relationship_tt_ids !== $old_category_tt_ids) {
            return false;
        }

        $post_id = $proposal['draft_post_id'];
        $target_tt_id = (int) $before['category_term_taxonomy_id'];
        $affected_category_tt_ids = array_values(
            array_unique(array_merge($old_category_tt_ids, array($target_tt_id)))
        );
        sort($affected_category_tt_ids, SORT_NUMERIC);
        if ($target_tt_id < 1
            || count($affected_category_tt_ids)
                > self::MAX_TERM_RELATIONSHIPS + 1
            || ! function_exists('wp_update_term_count_now')
            || ! function_exists('taxonomy_exists')
            || ! taxonomy_exists('category')
            || $wpdb->query('START TRANSACTION') === false
            || ! $this->publication_mutex_is_owned($mutex_name)) {
            $wpdb->query('ROLLBACK');
            return false;
        }
        $current_post = $wpdb->get_row(
            $wpdb->prepare(
                "SELECT post_name, post_status, post_date, post_date_gmt,
                        post_modified, post_modified_gmt, post_type
                 FROM {$wpdb->posts} WHERE ID = %d FOR UPDATE",
                $post_id
            ),
            ARRAY_A
        );
        if ($wpdb->last_error !== ''
            || ! is_array($current_post)
            || ! self::has_exact_keys(
                $current_post,
                array(
                    'post_date',
                    'post_date_gmt',
                    'post_modified',
                    'post_modified_gmt',
                    'post_name',
                    'post_status',
                    'post_type',
                )
            )
            || $current_post['post_name'] !== $proposal['public_slug']
            || $current_post['post_status'] !== 'publish'
            || $current_post['post_date']
                !== $publication_dates['post_date']
            || $current_post['post_date_gmt']
                !== $publication_dates['post_date_gmt']
            || $current_post['post_modified']
                !== $modified_times['post_modified']
            || $current_post['post_modified_gmt']
                !== $modified_times['post_modified_gmt']
            || $current_post['post_type'] !== 'post') {
            $wpdb->query('ROLLBACK');
            return false;
        }
        $current_relationships = $wpdb->get_results(
            $wpdb->prepare(
                "SELECT tr.term_taxonomy_id, tr.term_order, tt.taxonomy
                 FROM {$wpdb->term_relationships} AS tr
                 INNER JOIN {$wpdb->term_taxonomy} AS tt
                    ON tt.term_taxonomy_id = tr.term_taxonomy_id
                 WHERE tr.object_id = %d
                 ORDER BY tr.term_taxonomy_id ASC, tr.term_order ASC
                 FOR UPDATE",
                $post_id
            ),
            ARRAY_A
        );
        if ($wpdb->last_error !== ''
            || ! is_array($current_relationships)
            || count($current_relationships) > self::MAX_TERM_RELATIONSHIPS) {
            $wpdb->query('ROLLBACK');
            return false;
        }
        $current_categories = array();
        foreach ($current_relationships as $relationship) {
            if (! isset(
                $relationship['term_taxonomy_id'],
                $relationship['term_order'],
                $relationship['taxonomy']
            )
                || preg_match(
                    '/\A[1-9][0-9]*\z/',
                    (string) $relationship['term_taxonomy_id']
                ) !== 1
                || preg_match(
                    '/\A(?:0|[1-9][0-9]*)\z/',
                    (string) $relationship['term_order']
                ) !== 1
                || ! is_string($relationship['taxonomy'])
                || $relationship['taxonomy'] === '') {
                $wpdb->query('ROLLBACK');
                return false;
            }
            if ($relationship['taxonomy'] === 'category') {
                $current_categories[] = $relationship;
            }
        }
        if (count($current_categories) !== 1
            || ! isset(
                $current_categories[0]['term_taxonomy_id'],
                $current_categories[0]['term_order']
            )
            || (int) $current_categories[0]['term_taxonomy_id']
                !== $target_tt_id
            || (int) $current_categories[0]['term_order'] !== 0) {
            $wpdb->query('ROLLBACK');
            return false;
        }
        $placeholders = implode(
            ',',
            array_fill(0, count($affected_category_tt_ids), '%d')
        );
        $taxonomy_rows = $wpdb->get_results(
            $wpdb->prepare(
                "SELECT term_taxonomy_id, taxonomy
                 FROM {$wpdb->term_taxonomy}
                 WHERE term_taxonomy_id IN ({$placeholders})
                 ORDER BY term_taxonomy_id ASC FOR UPDATE",
                $affected_category_tt_ids
            ),
            ARRAY_A
        );
        if ($wpdb->last_error !== ''
            || ! is_array($taxonomy_rows)
            || count($taxonomy_rows) !== count($affected_category_tt_ids)) {
            $wpdb->query('ROLLBACK');
            return false;
        }
        foreach ($taxonomy_rows as $index => $taxonomy_row) {
            if (! isset(
                $taxonomy_row['term_taxonomy_id'],
                $taxonomy_row['taxonomy']
            )
                || (int) $taxonomy_row['term_taxonomy_id']
                    !== $affected_category_tt_ids[$index]
                || $taxonomy_row['taxonomy'] !== 'category') {
                $wpdb->query('ROLLBACK');
                return false;
            }
        }

        $post_updated = $wpdb->query(
            $wpdb->prepare(
                "UPDATE {$wpdb->posts}
                 SET post_name = %s, post_status = %s,
                     post_date = %s, post_date_gmt = %s,
                     post_modified = %s, post_modified_gmt = %s
                 WHERE ID = %d
                   AND BINARY post_name = BINARY %s
                   AND BINARY post_status = BINARY %s
                   AND BINARY post_date = BINARY %s
                   AND BINARY post_date_gmt = BINARY %s
                   AND BINARY post_modified = BINARY %s
                   AND BINARY post_modified_gmt = BINARY %s
                   AND BINARY post_type = BINARY %s
                   AND (IS_USED_LOCK(%s) = CONNECTION_ID())",
                $post_fields['post_name'],
                $post_fields['post_status'],
                $post_fields['post_date'],
                $post_fields['post_date_gmt'],
                $post_fields['post_modified'],
                $post_fields['post_modified_gmt'],
                $post_id,
                $proposal['public_slug'],
                'publish',
                $publication_dates['post_date'],
                $publication_dates['post_date_gmt'],
                $modified_times['post_modified'],
                $modified_times['post_modified_gmt'],
                'post',
                $mutex_name
            )
        );
        $deleted_category = $post_updated === 1
            ? $wpdb->query(
                $wpdb->prepare(
                    "DELETE tr FROM {$wpdb->term_relationships} AS tr
                     INNER JOIN {$wpdb->term_taxonomy} AS tt
                        ON tt.term_taxonomy_id = tr.term_taxonomy_id
                     WHERE tr.object_id = %d
                       AND tr.term_taxonomy_id = %d
                       AND tr.term_order = %d
                       AND BINARY tt.taxonomy = BINARY %s
                       AND (IS_USED_LOCK(%s) = CONNECTION_ID())",
                    $post_id,
                    $target_tt_id,
                    0,
                    'category',
                    $mutex_name
                )
            )
            : false;
        if ($post_updated !== 1 || $deleted_category !== 1) {
            $wpdb->query('ROLLBACK');
            return false;
        }
        foreach ($old_category_relationships as $relationship) {
            if ($wpdb->query(
                $wpdb->prepare(
                    "INSERT INTO {$wpdb->term_relationships}
                        (object_id, term_taxonomy_id, term_order)
                     SELECT %d, tt.term_taxonomy_id, %d
                     FROM {$wpdb->term_taxonomy} AS tt
                     WHERE tt.term_taxonomy_id = %d
                       AND BINARY tt.taxonomy = BINARY %s
                       AND (IS_USED_LOCK(%s) = CONNECTION_ID())",
                    $post_id,
                    $relationship['term_order'],
                    $relationship['term_taxonomy_id'],
                    'category',
                    $mutex_name
                )
            ) !== 1) {
                $wpdb->query('ROLLBACK');
                return false;
            }
        }
        if (! $this->publication_mutex_is_owned($mutex_name)
            || $wpdb->query('COMMIT') === false) {
            $wpdb->query('ROLLBACK');
            return false;
        }
        try {
            if (wp_update_term_count_now(
                $affected_category_tt_ids,
                'category'
            ) !== true) {
                return false;
            }
        } catch (Throwable $exception) {
            return false;
        }
        clean_post_cache($post_id);
        clean_object_term_cache($post_id, 'post');
        return $this->before_state_matches($proposal, $before);
    }

    private function persist_hook_replay_completion(
        $proposal_id,
        array $proposal,
        array $before,
        $mutex_name,
        array $modified_times
    ) {
        global $wpdb;
        if (! $this->publication_mutex_is_owned($mutex_name)
            || $wpdb->query('START TRANSACTION') === false
            || ! $this->publication_mutex_is_owned($mutex_name)) {
            $wpdb->query('ROLLBACK');
            return false;
        }
        $locked_id = $wpdb->get_var(
            $wpdb->prepare(
                "SELECT ID FROM {$wpdb->posts} WHERE ID = %d FOR UPDATE",
                $proposal['draft_post_id']
            )
        );
        if ($wpdb->last_error !== ''
            || (int) $locked_id !== $proposal['draft_post_id']
            || ! $this->publication_mutex_is_owned($mutex_name)
            || ! $this->published_state_matches(
                $proposal,
                $before,
                $modified_times
            )) {
            $wpdb->query('ROLLBACK');
            return false;
        }
        $table = self::proposal_table();
        $updated = $wpdb->query(
            $wpdb->prepare(
                "UPDATE {$table}
                 SET result_code = %s, state_version = state_version + 1
                 WHERE proposal_id = %s AND state = %s
                   AND result_code IS NULL
                   AND BINARY apply_started_at = BINARY %s",
                self::HOOK_REPLAY_COMPLETED,
                $proposal_id,
                'APPLYING',
                $modified_times['post_modified_gmt']
            )
        );
        $audit_hash = $updated === 1
            ? self::append_audit(
                'HOOK_REPLAY_COMPLETED',
                $proposal_id,
                self::HOOK_REPLAY_COMPLETED,
                get_current_user_id()
            )
            : false;
        if ($updated !== 1
            || ! is_string($audit_hash)
            || ! $this->publication_mutex_is_owned($mutex_name)
            || $wpdb->query('COMMIT') === false) {
            $wpdb->query('ROLLBACK');
            return false;
        }
        return true;
    }

    private function finish_success(
        $proposal_id,
        array $proposal,
        array $before,
        $mutex_name,
        array $modified_times
    ) {
        global $wpdb;
        if (! $this->publication_mutex_is_owned($mutex_name)
            || $wpdb->query(
                'SET TRANSACTION ISOLATION LEVEL SERIALIZABLE'
            ) === false
            || $wpdb->query('START TRANSACTION') === false
            || ! $this->publication_mutex_is_owned($mutex_name)) {
            $wpdb->query('ROLLBACK');
            return $this->finish_failure(
                $proposal_id,
                'NEEDS_RECOVERY',
                'SUCCESS_TRANSACTION_UNAVAILABLE',
                $mutex_name
            );
        }
        $table = self::proposal_table();
        $locked_id = $wpdb->get_var(
            $wpdb->prepare(
                "SELECT ID FROM {$wpdb->posts} WHERE ID = %d FOR UPDATE",
                $proposal['draft_post_id']
            )
        );
        if ($wpdb->last_error !== ''
            || (int) $locked_id !== $proposal['draft_post_id']
            || ! $this->publication_mutex_is_owned($mutex_name)
            || ! $this->published_state_matches(
                $proposal,
                $before,
                $modified_times,
                true
            )) {
            $wpdb->query('ROLLBACK');
            return $this->finish_failure(
                $proposal_id,
                'NEEDS_RECOVERY',
                'TERMINAL_READBACK_CHANGED',
                $mutex_name
            );
        }
        $updated = $wpdb->query(
            $wpdb->prepare(
                "UPDATE {$table}
                 SET state = %s, result_code = %s, completed_at = %s,
                     state_version = state_version + 1
                 WHERE proposal_id = %s AND state = %s
                   AND result_code = %s",
                'APPLIED',
                self::RESULT_CODE,
                gmdate('Y-m-d H:i:s'),
                $proposal_id,
                'APPLYING',
                self::HOOK_REPLAY_COMPLETED
            )
        );
        $audit_hash = $updated === 1
            ? self::append_audit(
                'ARTICLE_PUBLISHED',
                $proposal_id,
                self::RESULT_CODE,
                get_current_user_id()
            )
            : false;
        if ($updated !== 1
            || ! is_string($audit_hash)
            || ! $this->publication_mutex_is_owned($mutex_name)
            || $wpdb->query('COMMIT') === false) {
            $wpdb->query('ROLLBACK');
            return $this->finish_failure(
                $proposal_id,
                'NEEDS_RECOVERY',
                'SUCCESS_RECEIPT_PERSISTENCE_FAILED',
                $mutex_name
            );
        }
        return $this->apply_response(
            array(
                'proposal_id' => $proposal_id,
                'operation' => self::OPERATION,
                'state' => 'APPLIED',
                'result_code' => self::RESULT_CODE,
            ),
            false
        );
    }

    private function finish_failure($proposal_id, $state, $code, $mutex_name)
    {
        if (! in_array($state, array('FAILED', 'NEEDS_RECOVERY'), true)
            || ! is_string($code)
            || preg_match('/\A[A-Z0-9_]{1,64}\z/', $code) !== 1) {
            $state = 'NEEDS_RECOVERY';
            $code = 'INVALID_FAILURE_CLASSIFICATION';
        }
        global $wpdb;
        $table = self::proposal_table();
        if (! $this->publication_mutex_is_owned($mutex_name)
            || $wpdb->query('START TRANSACTION') === false
            || ! $this->publication_mutex_is_owned($mutex_name)) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_st1704_apply_state_unknown', 500);
        }
        $updated = $wpdb->query(
            $wpdb->prepare(
                "UPDATE {$table}
                 SET state = %s,
                     result_code = CASE
                         WHEN BINARY result_code = BINARY %s THEN result_code
                         ELSE %s
                     END,
                     completed_at = %s,
                     state_version = state_version + 1
                 WHERE proposal_id = %s AND state = %s
                   AND (result_code IS NULL
                        OR BINARY result_code = BINARY %s)",
                $state,
                self::HOOK_REPLAY_COMPLETED,
                $code,
                gmdate('Y-m-d H:i:s'),
                $proposal_id,
                'APPLYING',
                self::HOOK_REPLAY_COMPLETED
            )
        );
        $audit_hash = $updated === 1
            ? self::append_audit(
                'APPLY_FAILED',
                $proposal_id,
                $code,
                get_current_user_id()
            )
            : false;
        if ($updated !== 1
            || ! is_string($audit_hash)
            || ! $this->publication_mutex_is_owned($mutex_name)
            || $wpdb->query('COMMIT') === false) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_st1704_apply_state_unknown', 500);
        }
        return self::error(
            $state === 'NEEDS_RECOVERY'
                ? 'raos_st1704_apply_needs_recovery'
                : 'raos_st1704_apply_failed',
            409
        );
    }

    private function finish_unhandled_apply_exception($proposal_id, $mutex_name)
    {
        if (! $this->publication_mutex_is_owned($mutex_name)) {
            return self::error('raos_st1704_publication_lock_lost', 500);
        }
        $row = $this->proposal_row($proposal_id);
        if (is_array($row) && $row['state'] === 'APPLYING') {
            return $this->finish_failure(
                $proposal_id,
                'NEEDS_RECOVERY',
                'UNHANDLED_APPLY_EXCEPTION',
                $mutex_name
            );
        }
        return self::error('raos_st1704_apply_execution_failed', 500);
    }

    private function apply_response(array $row, $replayed)
    {
        return new WP_REST_Response(
            array(
                'schema' => 'RAOS_ST1704_PUBLICATION_OPERATOR_APPLY_V2',
                'proposal_id' => $row['proposal_id'],
                'operation' => $row['operation'],
                'state' => $row['state'],
                'result_code' => $row['result_code'],
                'replayed' => (bool) $replayed,
            ),
            200,
            array('ETag' => '"' . $row['proposal_id'] . '"')
        );
    }

    private static function append_audit(
        $event_code,
        $proposal_id,
        $detail_code,
        $actor_user_id
    ) {
        global $wpdb;
        $table = self::audit_table();
        $previous = $wpdb->get_var(
            "SELECT event_hash FROM {$table}
             ORDER BY audit_id DESC LIMIT 1 FOR UPDATE"
        );
        if ($wpdb->last_error !== '') {
            return false;
        }
        if ($previous === null) {
            $audit_count = $wpdb->get_var("SELECT COUNT(*) FROM {$table}");
            if ($wpdb->last_error !== '' || (string) $audit_count !== '0') {
                return false;
            }
            $previous = str_repeat('0', 64);
        } elseif (! is_string($previous)
            || preg_match('/\A[a-f0-9]{64}\z/', $previous) !== 1) {
            return false;
        }
        if (! is_string($event_code)
            || preg_match('/\A[A-Z0-9_]{1,64}\z/', $event_code) !== 1
            || ! is_string($proposal_id)
            || preg_match('/\A[a-f0-9]{64}\z/', $proposal_id) !== 1
            || ! is_string($detail_code)
            || preg_match('/\A[A-Z0-9_]{1,64}\z/', $detail_code) !== 1
            || (int) $actor_user_id < 0) {
            return false;
        }
        $occurred_at = gmdate('Y-m-d H:i:s');
        $material = implode(
            "\n",
            array(
                $previous,
                $occurred_at,
                (string) (int) $actor_user_id,
                $event_code,
                $proposal_id,
                $detail_code,
            )
        );
        $event_hash = hash('sha256', $material);
        $inserted = $wpdb->insert(
            $table,
            array(
                'occurred_at' => $occurred_at,
                'actor_user_id' => (int) $actor_user_id,
                'event_code' => $event_code,
                'proposal_id' => $proposal_id,
                'detail_code' => $detail_code,
                'previous_hash' => $previous,
                'event_hash' => $event_hash,
            ),
            array('%s', '%d', '%s', '%s', '%s', '%s', '%s')
        );
        return $inserted === 1 ? $event_hash : false;
    }
}
