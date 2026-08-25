<?php
/**
 * Plugin Name: RAOS Bounded Operator
 * Description: A closed, human-approved WordPress operator bridge for RAOS.
 * Version: 1.0.0
 * Requires at least: 6.9
 * Requires PHP: 7.4
 * Author: RAOS
 * License: Proprietary
 */

if (! defined('ABSPATH')) {
    exit;
}

final class RAOS_Bounded_Operator
{
    const VERSION = '1.0.0';
    const REST_NAMESPACE = 'raos-operator/v1';
    const SITE_ORIGIN = 'https://kurashinoshirube.com';
    const OPERATOR_CONTRACT_VERSION = 1;
    const PROFILE_VERSION = 1;
    const ROLE = 'raos_operator_executor';
    const BOUND_OPERATOR_OPTION = 'raos_operator_bound_user_id_v1';
    const NETWORK_IDENTITY_META = 'raos_operator_network_identity_v1';
    const CAP_READ = 'raos_operator_read';
    const CAP_PROPOSE = 'raos_operator_propose';
    const CAP_APPLY = 'raos_operator_apply';
    const THEME_SLUG = 'kurashinoshirube-child';
    const YOAST_VERSION = '28.3';
    const YOAST_CHECKSUM_URL = 'https://downloads.wordpress.org/plugin-checksums/wordpress-seo/28.3.json';
    const YOAST_CHECKSUM_MANIFEST_SHA256 = '1773aaadf88827311b488877c069aefcb6422e8dc6d5a7f50c1bd492d34bf85f';
    const YOAST_CHECKSUM_MANIFEST_BYTES = 343370;
    const YOAST_CHECKSUM_FILE_COUNT = 1952;
    const CHECKSUM_CACHE_TTL = 300;
    const CHECKSUM_MUTEX_PURPOSE = 'YOAST_CHECKSUM';
    const PROPOSAL_CREATE_MUTEX_PURPOSE = 'PROPOSAL_CREATE';
    const YOAST_ARCHIVE_SHA256 = '381edc1603147bd76af81341f21c9155ff3e9f6ce29ed20886d889fb9d6744fb';
    const YOAST_ARCHIVE_BYTES = 5151735;
    const SOCIAL_IMAGE_PATH = 'assets/images/home-hero.webp';
    const SOCIAL_IMAGE_SHA256 = 'df9fc09115e93708e858335e50e88534cc91114fb064642f9d904b5e52b83cea';
    const THEME_FROM_VERSION = '1.1.1';
    const DEFAULT_TTL = 900;
    const MAX_PACKAGE_BYTES = 16777216;
    const MAX_UNCOMPRESSED_BYTES = 67108864;
    const MAX_FILE_BYTES = 4194304;
    const MAX_FILE_COUNT = 64;
    const MAX_ACTIVE_PROPOSALS_PER_PROPOSER = 20;
    const MAX_PROPOSALS_PER_WINDOW = 5;
    const PROPOSAL_RATE_WINDOW_SECONDS = 600;
    const MAX_PROPOSAL_ROWS = 1000;
    const CANONICAL_VECTOR_BYTES = 870;
    const CANONICAL_VECTOR_SHA256 = '699a1c5a40786449e3f0241958a594f436e03504472a592d2abc1e3eae2b7d90';
    const REVIEWED_THEME_RELEASE_STATE = 'NO_REVIEWED_UPGRADE';
    const REVIEWED_THEME_RUNTIME_MANIFEST_SHA256 = '5a1e2965fb976b687cbc72c0841d0192ccf54de7e78e34c5bbdc59a360799fed';
    const REVIEWED_THEME_RELEASE_JSON_SHA256 = '47326724a60c84102c3a38b548fab152c2044457f2c7b8b0b6712a80f0a04272';
    const REVIEWED_THEME_RELEASE_JSON = '{"file_manifest":[{"path":"assets/images/article-suitcase-guide.webp","sha256":"23c585a03598a8521fd797c036d2caad4350139ad709ca9b0cfc3ab18ad993ad","size":70148},{"path":"assets/images/brand-mark.svg","sha256":"bd9f84f40eca90fb88b7e8a3967f6d7ceb5d337c6023d1f2ff748936a0f3acf3","size":331},{"path":"assets/images/home-hero.webp","sha256":"df9fc09115e93708e858335e50e88534cc91114fb064642f9d904b5e52b83cea","size":133648},{"path":"assets/theme.css","sha256":"63b55476a03f822b6723d3df141b9f3e4215c09e99e7dd366999fa12f29db8f2","size":10345},{"path":"functions.php","sha256":"aa38573d0b050a87a8dd48f5c8d71d78a0605b16fe04798d39c46bbcc81479ae","size":83520},{"path":"parts/footer.html","sha256":"ed8d2c2242575b08ad442752786b15b2184e649e4e7839fe22ae5a4609425aa0","size":581},{"path":"parts/header.html","sha256":"e3a125c165aa3f59e719ea9f78989fbc8a1ccb125db7f7ab69a0df28f1303e46","size":403},{"path":"raos-assets.v1.json","sha256":"df12cf49489faf0f9bb74b6fdda25d6a414b05a51a90142e799f0816f8317b95","size":1694},{"path":"style.css","sha256":"4d81df712a9895b1579e99bd19510f9c7c9977b815b0dba360f7bea3d29f8492","size":265},{"path":"templates/front-page.html","sha256":"86972888a39444adfb2882755850693d07e6bed5738b76119741f8fe669e7ae0","size":3625},{"path":"templates/single.html","sha256":"5dd6acd3d1aed444322d85f72bfcc9de1dd1aaf266334febe8d13c36e35f14bb","size":944},{"path":"theme-contract.v1.json","sha256":"173b7832dd96ef0dbdb695ce35ca0261a8a92575fcc676b9eb2a4a32c1ccdfc8","size":12410},{"path":"theme.json","sha256":"af7ed75442b05192c4185a7bbe8ba8a95ee8e757d0f006aacf804e5801c03d7c","size":1933}],"from_version":"1.1.1","package_sha256":"072ba1f5864af0b7f5b5b3c9deaf04ce6c162a13132762b7ffda0b0823de35a7","package_size":321987,"slug":"kurashinoshirube-child","to_version":"1.1.1"}';

    private static $instance = null;
    private static $application_password_user_id = 0;
    private static $operator_application_password_authenticated = false;

    public static function instance()
    {
        if (self::$instance === null) {
            self::$instance = new self();
        }
        return self::$instance;
    }

    private function __construct()
    {
        add_action(
            'wp_authenticate_application_password_errors',
            array($this, 'constrain_operator_application_password'),
            10,
            4
        );
        add_action(
            'application_password_did_authenticate',
            array($this, 'record_application_password_authentication'),
            10,
            2
        );
        add_filter(
            'rest_request_before_callbacks',
            array($this, 'guard_operator_rest_route'),
            10,
            3
        );
        add_action(
            'plugins_loaded',
            array($this, 'quarantine_existing_operator_binding'),
            1
        );
        add_action('rest_api_init', array($this, 'register_rest_routes'));
        add_action('admin_menu', array($this, 'register_admin_page'));
        add_action('admin_post_raos_operator_approve', array($this, 'handle_approval'));
    }

    public function quarantine_existing_operator_binding()
    {
        $binding = $this->operator_user_binding();
        if ($binding['state'] !== 'VALID') {
            return;
        }
        $marker = $this->operator_network_marker($binding['user_id']);
        if ($marker['state'] === 'ABSENT') {
            $this->bind_operator_identity(
                $binding['user_id'],
                ! is_multisite() && self::runtime_origin_is_exact()
            );
        }
    }

    public function constrain_operator_application_password($error, $user, $item, $password)
    {
        unset($item, $password);
        if (! $error instanceof WP_Error
            || ! $user instanceof WP_User
            || ! $user->exists()) {
            return;
        }
        $binding = $this->operator_user_binding();
        $role_marker = $this->has_operator_role_marker($user);
        $network_marker = $this->operator_network_marker((int) $user->ID);
        $local_match = $binding['state'] === 'VALID'
            && $binding['user_id'] === (int) $user->ID;
        $network_match = in_array(
            $network_marker['state'],
            array('VALID', 'INVALID'),
            true
        );
        if (! $role_marker && ! $local_match && ! $network_match) {
            return;
        }
        if ($network_marker['state'] === 'INVALID'
            || $network_marker['state'] === 'UNAVAILABLE'
            || ($role_marker
                && $binding['state'] === 'VALID'
                && $binding['user_id'] !== (int) $user->ID)
            || ($role_marker && $binding['state'] === 'INVALID')) {
            $error->add(
                'raos_operator_application_password_binding_invalid',
                'The bounded operator credential binding is invalid.'
            );
            return;
        }
        $write_local_binding = ! is_multisite() && self::runtime_origin_is_exact();
        if ($network_marker['state'] === 'ABSENT'
            || ($write_local_binding && $binding['state'] === 'ABSENT')) {
            if (! $local_match && ! $this->has_exact_operator_role_assignment($user)) {
                $error->add(
                    'raos_operator_application_password_binding_invalid',
                    'The bounded operator credential binding is invalid.'
                );
                return;
            }
            if (! $this->bind_operator_identity(
                (int) $user->ID,
                $write_local_binding
            )) {
                $error->add(
                    'raos_operator_application_password_binding_invalid',
                    'The bounded operator credential binding is invalid.'
                );
                return;
            }
            $binding = $this->operator_user_binding();
            $network_marker = $this->operator_network_marker((int) $user->ID);
        }
        if ($network_marker['state'] !== 'VALID') {
            $error->add(
                'raos_operator_application_password_binding_invalid',
                'The bounded operator credential binding is invalid.'
            );
            return;
        }
        if (is_multisite()) {
            $error->add(
                'raos_operator_application_password_multisite_unsupported',
                'The bounded operator does not support multisite.'
            );
            return;
        }
        if (! self::runtime_origin_is_exact()) {
            $error->add(
                'raos_operator_application_password_surface_forbidden',
                'The bounded operator credential is restricted to its exact site.'
            );
            return;
        }
        if ($binding['state'] !== 'VALID'
            || $binding['user_id'] !== (int) $user->ID) {
            $error->add(
                'raos_operator_application_password_binding_invalid',
                'The bounded operator credential binding is invalid.'
            );
            return;
        }
        self::$operator_application_password_authenticated = true;
        self::$application_password_user_id = (int) $user->ID;
        if ((defined('XMLRPC_REQUEST') && XMLRPC_REQUEST === true)
            || ! defined('REST_REQUEST')
            || REST_REQUEST !== true) {
            $error->add(
                'raos_operator_application_password_transport_forbidden',
                'The bounded operator credential is restricted to its REST surface.'
            );
        }
    }

    public function record_application_password_authentication($user, $item)
    {
        unset($item);
        if ($user instanceof WP_User
            && $user->exists()
            && self::$operator_application_password_authenticated
            && self::$application_password_user_id === (int) $user->ID) {
            self::$application_password_user_id = (int) $user->ID;
        }
    }

    public function guard_operator_rest_route($response, $handler, $request)
    {
        if (! self::$operator_application_password_authenticated) {
            return $response;
        }
        $user = wp_get_current_user();
        if (! $user instanceof WP_User
            || ! $user->exists()
            || (int) $user->ID !== self::$application_password_user_id
            || is_multisite()
            || ! self::runtime_origin_is_exact()
            || ! $request instanceof WP_REST_Request
            || ! is_array($handler)
            || ! $this->is_allowed_operator_rest_handler($handler, $request)) {
            return self::error('raos_operator_rest_scope_forbidden', 403);
        }
        return $response;
    }

    private function has_operator_role_marker($user)
    {
        return $user instanceof WP_User
            && is_array($user->roles)
            && in_array(self::ROLE, $user->roles, true);
    }

    private function has_exact_operator_role_assignment($user)
    {
        return $this->has_operator_role_marker($user)
            && count($user->roles) === 1
            && reset($user->roles) === self::ROLE;
    }

    private function operator_user_binding()
    {
        global $wpdb;
        $rows = $wpdb->get_col(
            $wpdb->prepare(
                "SELECT option_value FROM {$wpdb->options}
                 WHERE BINARY option_name = BINARY %s",
                self::BOUND_OPERATOR_OPTION
            )
        );
        if ($wpdb->last_error !== '' || ! is_array($rows) || count($rows) > 1) {
            return array('state' => 'INVALID', 'user_id' => 0);
        }
        if (count($rows) === 0) {
            return array('state' => 'ABSENT', 'user_id' => 0);
        }
        $raw = $rows[0];
        if (is_int($raw)) {
            $user_id = $raw;
        } elseif (is_string($raw)
            && preg_match('/\A[1-9][0-9]{0,18}\z/', $raw)) {
            $user_id = (int) $raw;
        } else {
            return array('state' => 'INVALID', 'user_id' => 0);
        }
        if ($user_id < 1 || (string) $user_id !== (string) $raw) {
            return array('state' => 'INVALID', 'user_id' => 0);
        }
        return array('state' => 'VALID', 'user_id' => $user_id);
    }

    private function operator_network_marker($user_id)
    {
        if (! is_int($user_id) || $user_id < 1) {
            return array('state' => 'INVALID');
        }
        global $wpdb;
        $rows = $wpdb->get_col(
            $wpdb->prepare(
                "SELECT meta_value FROM {$wpdb->usermeta}
                 WHERE user_id = %d AND BINARY meta_key = BINARY %s
                 ORDER BY umeta_id ASC",
                $user_id,
                self::NETWORK_IDENTITY_META
            )
        );
        if ($wpdb->last_error !== '' || ! is_array($rows)) {
            return array('state' => 'UNAVAILABLE');
        }
        if (count($rows) === 0) {
            return array('state' => 'ABSENT');
        }
        if (count($rows) !== 1
            || ! is_string($rows[0])
            || ! hash_equals($this->network_identity_value($user_id), $rows[0])) {
            return array('state' => 'INVALID');
        }
        return array('state' => 'VALID');
    }

    private function network_identity_value($user_id)
    {
        return 'RAOS_OPERATOR_IDENTITY_V1' . "\n"
            . self::SITE_ORIGIN . "\n" . (string) (int) $user_id;
    }

    private function bind_operator_identity($user_id, $write_local_binding)
    {
        $mutex_name = $this->identity_mutex_name($user_id);
        if (! is_string($mutex_name)) {
            return false;
        }
        global $wpdb;
        $acquired = $wpdb->get_var(
            $wpdb->prepare('SELECT GET_LOCK(%s, 0)', $mutex_name)
        );
        if ($wpdb->last_error !== '' || (string) $acquired !== '1') {
            return false;
        }
        $valid = false;
        $released = false;
        try {
            $marker = $this->operator_network_marker($user_id);
            if ($marker['state'] === 'ABSENT') {
                add_user_meta(
                    $user_id,
                    self::NETWORK_IDENTITY_META,
                    $this->network_identity_value($user_id),
                    true
                );
                $marker = $this->operator_network_marker($user_id);
            }
            if ($marker['state'] !== 'VALID') {
                return false;
            }
            if ($write_local_binding) {
                $binding = $this->operator_user_binding();
                if ($binding['state'] === 'ABSENT') {
                    add_option(
                        self::BOUND_OPERATOR_OPTION,
                        (string) $user_id,
                        '',
                        false
                    );
                    $binding = $this->operator_user_binding();
                }
                if ($binding['state'] !== 'VALID'
                    || $binding['user_id'] !== $user_id) {
                    return false;
                }
            }
            $valid = true;
        } finally {
            $released_value = $wpdb->get_var(
                $wpdb->prepare('SELECT RELEASE_LOCK(%s)', $mutex_name)
            );
            $released = $wpdb->last_error === ''
                && (string) $released_value === '1';
        }
        return $valid && $released;
    }

    private function identity_mutex_name($user_id)
    {
        global $wpdb;
        if (! is_int($user_id)
            || $user_id < 1
            || ! defined('DB_NAME')
            || ! is_string(DB_NAME)
            || DB_NAME === ''
            || ! is_string($wpdb->base_prefix)
            || $wpdb->base_prefix === '') {
            return null;
        }
        $scope = DB_NAME . "\n" . $wpdb->base_prefix . "\n"
            . self::NETWORK_IDENTITY_META . "\n" . self::SITE_ORIGIN . "\n"
            . (string) $user_id;
        return 'raos_identity_v1_' . substr(hash('sha256', $scope), 0, 44);
    }

    private function is_allowed_operator_rest_handler(array $handler, $request)
    {
        $method = strtoupper((string) $request->get_method());
        $route = (string) $request->get_route();
        $expected_callback = null;
        if ($method === 'GET' && $route === '/' . self::REST_NAMESPACE . '/status') {
            $expected_callback = 'rest_status';
        } elseif ($method === 'POST'
            && $route === '/' . self::REST_NAMESPACE . '/yoast-checksum') {
            $expected_callback = 'rest_yoast_checksum';
        } elseif ($method === 'POST'
            && $route === '/' . self::REST_NAMESPACE . '/proposals') {
            $expected_callback = 'rest_create_proposal';
        } elseif ($method === 'POST'
            && preg_match(
                '#\A/' . preg_quote(self::REST_NAMESPACE, '#')
                . '/proposals/[a-f0-9]{64}/apply\z#',
                $route
            )) {
            $expected_callback = 'rest_apply';
        }
        if ($expected_callback === null
            || ! isset($handler['callback'])
            || ! is_array($handler['callback'])
            || count($handler['callback']) !== 2) {
            return false;
        }
        return $handler['callback'][0] === $this
            && $handler['callback'][1] === $expected_callback;
    }

    public static function activate()
    {
        if (is_multisite()) {
            wp_die(esc_html('RAOS Bounded Operator does not support multisite.'));
        }
        if (! self::install_role()) {
            wp_die(esc_html('RAOS operator role initialization failed.'));
        }
        self::install_tables();
        if (! self::append_activation_audit()) {
            wp_die(esc_html('RAOS operator audit initialization failed.'));
        }
    }

    private static function append_activation_audit()
    {
        global $wpdb;
        if (! self::operator_tables_are_innodb()
            || $wpdb->query('START TRANSACTION') === false) {
            return false;
        }
        try {
            if (self::append_audit(
                'PLUGIN_ACTIVATED',
                str_repeat('0', 64),
                'ROLE_AND_TABLES_READY',
                get_current_user_id()
            ) === false) {
                $wpdb->query('ROLLBACK');
                return false;
            }
            if ($wpdb->query('COMMIT') === false) {
                $wpdb->query('ROLLBACK');
                return false;
            }
        } catch (Throwable $exception) {
            $wpdb->query('ROLLBACK');
            return false;
        }
        return true;
    }

    private static function operator_tables_are_innodb()
    {
        return self::operator_table_is_innodb(self::proposal_table())
            && self::operator_table_is_innodb(self::audit_table());
    }

    private static function operator_table_is_innodb($table)
    {
        global $wpdb;
        if (! is_string($table)
            || ! in_array(
                $table,
                array(self::proposal_table(), self::audit_table()),
                true
            )) {
            return false;
        }
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

    private static function install_role()
    {
        $exact = self::exact_executor_capabilities();
        try {
            $role = get_role(self::ROLE);
            if (! $role instanceof WP_Role) {
                $created = add_role(
                    self::ROLE,
                    'RAOS Operator Executor',
                    $exact
                );
                if (! $created instanceof WP_Role) {
                    return false;
                }
                $role = get_role(self::ROLE);
            }
            if (! $role instanceof WP_Role
                || ! is_array($role->capabilities)) {
                return false;
            }
            foreach (array_keys($role->capabilities) as $capability) {
                $role->remove_cap($capability);
            }
            foreach ($exact as $capability => $grant) {
                $role->add_cap($capability, $grant);
            }
            $verified = get_role(self::ROLE);
            return $verified instanceof WP_Role
                && is_array($verified->capabilities)
                && $verified->capabilities === $exact
                && self::persisted_executor_role_is_exact();
        } catch (Throwable $exception) {
            return false;
        }
    }

    private static function persisted_executor_role_is_exact()
    {
        global $wpdb;
        $option_name = $wpdb->prefix . 'user_roles';
        $rows = $wpdb->get_results(
            $wpdb->prepare(
                "SELECT option_value FROM {$wpdb->options} "
                . 'WHERE BINARY option_name = BINARY %s',
                $option_name
            ),
            ARRAY_A
        );
        if ($wpdb->last_error !== ''
            || ! is_array($rows)
            || count($rows) !== 1
            || ! is_array($rows[0])
            || count($rows[0]) !== 1
            || ! isset($rows[0]['option_value'])
            || ! is_string($rows[0]['option_value'])
            || ! is_serialized($rows[0]['option_value'], true)) {
            return false;
        }
        $stored_roles = @unserialize(
            $rows[0]['option_value'],
            array('allowed_classes' => false)
        );
        if (! is_array($stored_roles)
            || ! isset($stored_roles[self::ROLE])
            || ! is_array($stored_roles[self::ROLE])) {
            return false;
        }
        $record = $stored_roles[self::ROLE];
        return count($record) === 2
            && isset($record['name'], $record['capabilities'])
            && $record['name'] === 'RAOS Operator Executor'
            && is_array($record['capabilities'])
            && $record['capabilities'] === self::exact_executor_capabilities();
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

    private static function proposal_table()
    {
        global $wpdb;
        return $wpdb->prefix . 'raos_operator_proposals';
    }

    private static function audit_table()
    {
        global $wpdb;
        return $wpdb->prefix . 'raos_operator_audit';
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
            '/yoast-checksum',
            array(
                'methods' => WP_REST_Server::CREATABLE,
                'callback' => array($this, 'rest_yoast_checksum'),
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
            '/proposals/(?P<proposal_id>[a-f0-9]{64})/apply',
            array(
                'methods' => WP_REST_Server::CREATABLE,
                'callback' => array($this, 'rest_apply'),
                'permission_callback' => array($this, 'can_apply'),
            )
        );
    }

    private function is_exact_executor()
    {
        $user = wp_get_current_user();
        $binding = $this->operator_user_binding();
        $network_marker = $user instanceof WP_User && $user->exists()
            ? $this->operator_network_marker((int) $user->ID)
            : array('state' => 'INVALID');
        if (! $user instanceof WP_User
            || ! $user->exists()
            || is_multisite()
            || self::$application_password_user_id !== (int) $user->ID
            || ! self::$operator_application_password_authenticated
            || $network_marker['state'] !== 'VALID'
            || $binding['state'] !== 'VALID'
            || $binding['user_id'] !== (int) $user->ID
            || (is_multisite() && is_super_admin($user->ID))
            || count($user->roles) !== 1
            || reset($user->roles) !== self::ROLE) {
            return false;
        }
        $role = get_role(self::ROLE);
        if (! $role instanceof WP_Role) {
            return false;
        }
        $expected = self::exact_executor_capabilities();
        $expected_all = $expected;
        $expected_all[self::ROLE] = true;
        $role_caps = $role->capabilities;
        $all_caps = $user->allcaps;
        $user_caps = $user->caps;
        ksort($expected, SORT_STRING);
        ksort($expected_all, SORT_STRING);
        ksort($role_caps, SORT_STRING);
        ksort($all_caps, SORT_STRING);
        ksort($user_caps, SORT_STRING);
        return $role_caps === $expected
            && $all_caps === $expected_all
            && $user_caps === array(self::ROLE => true);
    }

    public function can_read()
    {
        return $this->is_exact_executor() && current_user_can(self::CAP_READ);
    }

    public function can_propose()
    {
        return $this->is_exact_executor() && current_user_can(self::CAP_PROPOSE);
    }

    public function can_apply()
    {
        return $this->is_exact_executor() && current_user_can(self::CAP_APPLY);
    }

    private static function writes_enabled()
    {
        return defined('RAOS_OPERATOR_WRITES_ENABLED')
            && RAOS_OPERATOR_WRITES_ENABLED === true;
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
            'The bounded operator rejected the request.',
            array('status' => $status)
        );
    }

    public function rest_status()
    {
        if (! self::runtime_origin_is_exact()) {
            return self::error('raos_runtime_origin_invalid', 409);
        }
        global $wpdb;
        $states = array(
            'PROPOSED',
            'APPROVED',
            'APPLYING',
            'APPLIED',
            'FAILED',
            'NEEDS_RECOVERY',
            'EXPIRED',
        );
        $counts = array_fill_keys($states, 0);
        $rows = $wpdb->get_results(
            'SELECT state, COUNT(*) AS aggregate_count FROM '
            . self::proposal_table()
            . ' GROUP BY state',
            ARRAY_A
        );
        if (! is_array($rows) || $wpdb->last_error !== '') {
            return self::error('raos_status_unavailable', 500);
        }
        foreach ($rows as $row) {
            if (! isset($row['state'], $row['aggregate_count'])
                || ! array_key_exists($row['state'], $counts)) {
                return self::error('raos_status_unavailable', 500);
            }
            $count = $this->strict_count($row['aggregate_count']);
            if (is_wp_error($count)) {
                return self::error('raos_status_unavailable', 500);
            }
            $counts[$row['state']] = $count;
        }
        $yoast_code = $this->yoast_status_code();
        $theme_status = $this->theme_status();
        return rest_ensure_response(
            array(
                'schema' => 'RAOS_OPERATOR_STATUS_V1',
                'operator_version' => self::VERSION,
                'writes_enabled' => self::writes_enabled(),
                'supported_operations' => array(
                    'APPLY_YOAST_PROFILE',
                    'UPDATE_CHILD_THEME',
                ),
                'yoast_profile_code' => $yoast_code,
                'theme' => $theme_status,
                'proposal_counts' => $counts,
            )
        );
    }

    private function yoast_status_code()
    {
        if (! defined('WPSEO_VERSION')) {
            return 'YOAST_VERSION_ABSENT';
        }
        if (WPSEO_VERSION !== self::YOAST_VERSION) {
            return 'YOAST_VERSION_MISMATCH';
        }
        $profile = $this->derived_yoast_profile();
        if (is_wp_error($profile)) {
            return 'YOAST_PROFILE_PREREQUISITE_FAILED';
        }
        return $this->yoast_readback_matches($profile, null, null)
            ? 'YOAST_PROFILE_MATCH'
            : 'YOAST_PROFILE_MISMATCH';
    }

    private function theme_status()
    {
        $theme = wp_get_theme(self::THEME_SLUG);
        if (! $theme->exists()) {
            return array(
                'slug' => self::THEME_SLUG,
                'installed_version' => null,
                'active' => false,
                'state_code' => 'THEME_ABSENT',
                'file_count' => 0,
                'tree_sha256' => null,
            );
        }
        $state = $this->capture_theme_state();
        if (is_wp_error($state)) {
            return array(
                'slug' => self::THEME_SLUG,
                'installed_version' => null,
                'active' => get_stylesheet() === self::THEME_SLUG,
                'state_code' => 'THEME_TREE_UNREADABLE',
                'file_count' => 0,
                'tree_sha256' => null,
            );
        }
        return array(
            'slug' => self::THEME_SLUG,
            'installed_version' => $state['installed_version'],
            'active' => $state['active'],
            'state_code' => 'THEME_TREE_READABLE',
            'file_count' => count($state['file_manifest']),
            'tree_sha256' => $state['tree_sha256'],
        );
    }

    public function rest_yoast_checksum(WP_REST_Request $request)
    {
        if (! self::runtime_origin_is_exact()) {
            return self::error('raos_runtime_origin_invalid', 409);
        }
        if ($request->get_header('content-type') !== 'application/json'
            || $request->get_body() !== '{}') {
            return self::error('raos_checksum_body_forbidden', 400);
        }
        $cached = get_transient('raos_operator_yoast_checksum_v1');
        if ($cached !== false) {
            $cached_result = $this->validated_checksum_cache($cached);
            if (is_wp_error($cached_result)) {
                return rest_ensure_response($this->checksum_unavailable('YOAST_CHECKSUM_CACHE_INVALID'));
            }
            return rest_ensure_response($this->checksum_response($cached_result));
        }
        $mutex_name = $this->auxiliary_mutex_name(self::CHECKSUM_MUTEX_PURPOSE);
        $mutex_state = $this->acquire_auxiliary_mutex($mutex_name);
        if ($mutex_state === 'BUSY') {
            return rest_ensure_response($this->checksum_unavailable('YOAST_CHECKSUM_BUSY'));
        }
        if ($mutex_state !== 'ACQUIRED') {
            return rest_ensure_response(
                $this->checksum_unavailable('YOAST_CHECKSUM_LOCK_UNAVAILABLE')
            );
        }
        $released = false;
        $from_cache = false;
        try {
            $locked_cached = get_transient('raos_operator_yoast_checksum_v1');
            if ($locked_cached !== false) {
                $locked_result = $this->validated_checksum_cache($locked_cached);
                $result = is_wp_error($locked_result)
                    ? $this->checksum_unavailable_result(
                        'YOAST_CHECKSUM_CACHE_INVALID'
                    )
                    : $locked_result;
                $from_cache = true;
            } else {
                $result = $this->auxiliary_mutex_is_owned($mutex_name)
                    ? $this->compute_yoast_checksum()
                    : $this->checksum_unavailable_result(
                        'YOAST_CHECKSUM_LOCK_LOST'
                    );
            }
            if (! $this->auxiliary_mutex_is_owned($mutex_name)) {
                $result = $this->checksum_unavailable_result(
                    'YOAST_CHECKSUM_LOCK_LOST'
                );
            } elseif (! $this->valid_checksum_result($result)) {
                $result = $this->checksum_unavailable_result(
                    'YOAST_CHECKSUM_INTERNAL_INVALID'
                );
            } elseif (! $from_cache) {
                if (! set_transient(
                    'raos_operator_yoast_checksum_v1',
                    $this->checksum_cache_record($result),
                    self::CHECKSUM_CACHE_TTL
                )) {
                    $result = $this->checksum_unavailable_result(
                        'YOAST_CHECKSUM_CACHE_WRITE_FAILED'
                    );
                }
                if (! $this->auxiliary_mutex_is_owned($mutex_name)) {
                    $result = $this->checksum_unavailable_result(
                        'YOAST_CHECKSUM_LOCK_LOST'
                    );
                }
            }
        } catch (Throwable $exception) {
            $result = $this->checksum_unavailable_result(
                'YOAST_CHECKSUM_INTERNAL_INVALID'
            );
        } finally {
            $released = $this->release_auxiliary_mutex($mutex_name);
        }
        if (! $released) {
            return rest_ensure_response(
                $this->checksum_unavailable('YOAST_CHECKSUM_LOCK_RELEASE_UNCERTAIN')
            );
        }
        return rest_ensure_response($this->checksum_response($result));
    }

    private function auxiliary_mutex_name($purpose)
    {
        global $wpdb;
        $prefixes = array(
            self::CHECKSUM_MUTEX_PURPOSE => 'raos_ck_v1_',
            self::PROPOSAL_CREATE_MUTEX_PURPOSE => 'raos_pc_v1_',
        );
        if (! is_string($purpose)
            || ! isset($prefixes[$purpose])
            || ! defined('DB_NAME')
            || ! is_string(DB_NAME)
            || DB_NAME === ''
            || ! is_string($wpdb->prefix)
            || $wpdb->prefix === '') {
            return null;
        }
        $scope = DB_NAME . "\n" . $wpdb->prefix . "\n"
            . self::SITE_ORIGIN . "\n" . $purpose;
        return $prefixes[$purpose] . substr(hash('sha256', $scope), 0, 48);
    }

    private function acquire_auxiliary_mutex($mutex_name)
    {
        global $wpdb;
        if (! is_string($mutex_name)
            || strlen($mutex_name) > 64
            || ! preg_match('/\A[A-Za-z0-9_]+\z/', $mutex_name)) {
            return 'UNAVAILABLE';
        }
        $existing_owner = $wpdb->get_var(
            $wpdb->prepare('SELECT IS_USED_LOCK(%s)', $mutex_name)
        );
        if ($wpdb->last_error !== '') {
            return 'UNAVAILABLE';
        }
        if ($existing_owner !== null) {
            return 'BUSY';
        }
        $acquired = $wpdb->get_var(
            $wpdb->prepare('SELECT GET_LOCK(%s, 0)', $mutex_name)
        );
        if ($wpdb->last_error !== '') {
            return 'UNAVAILABLE';
        }
        if ((string) $acquired === '1') {
            return 'ACQUIRED';
        }
        return (string) $acquired === '0' ? 'BUSY' : 'UNAVAILABLE';
    }

    private function auxiliary_mutex_is_owned($mutex_name)
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

    private function release_auxiliary_mutex($mutex_name)
    {
        global $wpdb;
        if (! $this->auxiliary_mutex_is_owned($mutex_name)) {
            return false;
        }
        $released = $wpdb->get_var(
            $wpdb->prepare('SELECT RELEASE_LOCK(%s)', $mutex_name)
        );
        return $wpdb->last_error === '' && (string) $released === '1';
    }

    private function compute_yoast_checksum()
    {
        $status = 'UNAVAILABLE';
        $code = 'YOAST_OFFICIAL_CHECKSUM_UNAVAILABLE';
        $checked = 0;
        $mismatches = 0;

        $response = wp_safe_remote_get(
            self::YOAST_CHECKSUM_URL,
            array(
                'timeout' => 15,
                'redirection' => 0,
                'reject_unsafe_urls' => true,
                'user-agent' => 'RAOS-Bounded-Operator/' . self::VERSION,
                'limit_response_size' => self::YOAST_CHECKSUM_MANIFEST_BYTES + 1,
                'headers' => array(
                    'Accept' => 'application/json',
                    'Accept-Encoding' => 'identity',
                ),
            )
        );
        if (! is_wp_error($response)
            && (int) wp_remote_retrieve_response_code($response) === 200) {
            $body = wp_remote_retrieve_body($response);
            $payload = json_decode($body, true);
            if (is_string($body)
                && strlen($body) === self::YOAST_CHECKSUM_MANIFEST_BYTES
                && hash_equals(self::YOAST_CHECKSUM_MANIFEST_SHA256, hash('sha256', $body))
                && is_array($payload)
                && isset($payload['plugin'], $payload['version'], $payload['files'])
                && $payload['plugin'] === 'wordpress-seo'
                && $payload['version'] === self::YOAST_VERSION
                && is_array($payload['files'])
                && count($payload['files']) === self::YOAST_CHECKSUM_FILE_COUNT) {
                $result = $this->verify_installed_yoast($payload['files']);
                $status = $result['status'];
                $code = $result['code'];
                $checked = $result['checked_file_count'];
                $mismatches = $result['mismatch_count'];
            } else {
                $code = 'YOAST_OFFICIAL_CHECKSUM_INVALID';
            }
        }

        return array(
            'status' => $status,
            'code' => $code,
            'checked_file_count' => $checked,
            'mismatch_count' => $mismatches,
        );
    }

    private function valid_checksum_result($result)
    {
        if (! is_array($result)
            || ! $this->has_exact_keys(
                $result,
                array('status', 'code', 'checked_file_count', 'mismatch_count')
            )
            || ! is_string($result['status'])
            || ! is_string($result['code'])
            || ! is_int($result['checked_file_count'])
            || ! is_int($result['mismatch_count'])) {
            return false;
        }
        if ($result['status'] === 'PASS') {
            return $result['code'] === 'YOAST_CHECKSUM_MATCH'
                && $result['checked_file_count'] === self::YOAST_CHECKSUM_FILE_COUNT
                && $result['mismatch_count'] === 0;
        }
        if ($result['status'] === 'FAIL') {
            return in_array(
                $result['code'],
                array(
                    'YOAST_CHECKSUM_MISMATCH',
                    'YOAST_INSTALLATION_ABSENT',
                    'YOAST_INSTALLATION_UNREADABLE',
                ),
                true
            )
                && $result['checked_file_count'] === self::YOAST_CHECKSUM_FILE_COUNT
                && $result['mismatch_count'] >= 1
                && $result['mismatch_count'] <= self::YOAST_CHECKSUM_FILE_COUNT;
        }
        return $result['status'] === 'UNAVAILABLE'
            && in_array(
                $result['code'],
                array(
                    'YOAST_CHECKSUM_BUSY',
                    'YOAST_CHECKSUM_CACHE_INVALID',
                    'YOAST_CHECKSUM_CACHE_WRITE_FAILED',
                    'YOAST_CHECKSUM_INTERNAL_INVALID',
                    'YOAST_CHECKSUM_LOCK_LOST',
                    'YOAST_CHECKSUM_LOCK_RELEASE_UNCERTAIN',
                    'YOAST_CHECKSUM_LOCK_UNAVAILABLE',
                    'YOAST_OFFICIAL_CHECKSUM_INVALID',
                    'YOAST_OFFICIAL_CHECKSUM_UNAVAILABLE',
                ),
                true
            )
            && $result['checked_file_count'] === 0
            && $result['mismatch_count'] === 0;
    }

    private function checksum_cache_record(array $result)
    {
        $material = self::canonical_json($result);
        return array(
            'result' => $result,
            'integrity' => hash_hmac('sha256', $material, wp_salt('auth')),
        );
    }

    private function validated_checksum_cache($cached)
    {
        if (! is_array($cached)
            || ! $this->has_exact_keys($cached, array('result', 'integrity'))
            || ! $this->valid_checksum_result($cached['result'])
            || ! is_string($cached['integrity'])
            || ! preg_match('/\A[a-f0-9]{64}\z/', $cached['integrity'])) {
            return self::error('raos_checksum_cache_invalid', 500);
        }
        $material = self::canonical_json($cached['result']);
        if (! is_string($material)
            || ! hash_equals(
                $cached['integrity'],
                hash_hmac('sha256', $material, wp_salt('auth'))
            )) {
            return self::error('raos_checksum_cache_invalid', 500);
        }
        return $cached['result'];
    }

    private function checksum_response(array $result)
    {
        return array(
            'schema' => 'RAOS_OPERATOR_CHECKSUM_V1',
            'status' => $result['status'],
            'code' => $result['code'],
            'checked_file_count' => $result['checked_file_count'],
            'mismatch_count' => $result['mismatch_count'],
            'expected_archive' => array(
                'version' => self::YOAST_VERSION,
                'byte_length' => self::YOAST_ARCHIVE_BYTES,
                'sha256' => self::YOAST_ARCHIVE_SHA256,
            ),
        );
    }

    private function checksum_unavailable($code)
    {
        return $this->checksum_response($this->checksum_unavailable_result($code));
    }

    private function checksum_unavailable_result($code)
    {
        return array(
            'status' => 'UNAVAILABLE',
            'code' => $code,
            'checked_file_count' => 0,
            'mismatch_count' => 0,
        );
    }

    private function verify_installed_yoast(array $checksums)
    {
        $plugin_root = WP_PLUGIN_DIR . '/wordpress-seo';
        if (! is_dir($plugin_root) || is_link($plugin_root)) {
            return array(
                'status' => 'FAIL',
                'code' => 'YOAST_INSTALLATION_ABSENT',
                'checked_file_count' => self::YOAST_CHECKSUM_FILE_COUNT,
                'mismatch_count' => self::YOAST_CHECKSUM_FILE_COUNT,
            );
        }
        $expected = array();
        $mismatches = 0;
        foreach ($checksums as $path => $record) {
            $digest = is_array($record) && isset($record['sha256'])
                ? $record['sha256']
                : null;
            if (! is_string($path)
                || ! is_string($digest)
                || ! $this->safe_relative_path($path)
                || ! preg_match('/\A[a-f0-9]{64}\z/', $digest)) {
                return array(
                    'status' => 'UNAVAILABLE',
                    'code' => 'YOAST_OFFICIAL_CHECKSUM_INVALID',
                    'checked_file_count' => 0,
                    'mismatch_count' => 0,
                );
            }
            $folded = strtolower($path);
            if (isset($expected[$folded])) {
                return array(
                    'status' => 'UNAVAILABLE',
                    'code' => 'YOAST_OFFICIAL_CHECKSUM_INVALID',
                    'checked_file_count' => 0,
                    'mismatch_count' => 0,
                );
            }
            $expected[$folded] = $path;
            $file = $plugin_root . '/' . $path;
            if (! is_file($file) || is_link($file)) {
                $mismatches++;
                continue;
            }
            $actual = hash_file('sha256', $file);
            if (! is_string($actual) || ! hash_equals($digest, strtolower($actual))) {
                $mismatches++;
            }
        }

        try {
            $iterator = new RecursiveIteratorIterator(
                new RecursiveDirectoryIterator(
                    $plugin_root,
                    FilesystemIterator::SKIP_DOTS
                ),
                RecursiveIteratorIterator::LEAVES_ONLY
            );
            foreach ($iterator as $file_info) {
                if ($file_info->isLink()) {
                    $mismatches++;
                    continue;
                }
                if (! $file_info->isFile()) {
                    continue;
                }
                $absolute = $file_info->getPathname();
                $relative = substr($absolute, strlen($plugin_root) + 1);
                $relative = str_replace(DIRECTORY_SEPARATOR, '/', $relative);
                if (! isset($expected[strtolower($relative)])) {
                    $mismatches++;
                }
            }
        } catch (UnexpectedValueException $exception) {
            return array(
                'status' => 'FAIL',
                'code' => 'YOAST_INSTALLATION_UNREADABLE',
                'checked_file_count' => self::YOAST_CHECKSUM_FILE_COUNT,
                'mismatch_count' => min(
                    self::YOAST_CHECKSUM_FILE_COUNT,
                    $mismatches + 1
                ),
            );
        }

        $mismatches = min($mismatches, count($expected));
        return array(
            'status' => $mismatches === 0 ? 'PASS' : 'FAIL',
            'code' => $mismatches === 0
                ? 'YOAST_CHECKSUM_MATCH'
                : 'YOAST_CHECKSUM_MISMATCH',
            'checked_file_count' => count($expected),
            'mismatch_count' => $mismatches,
        );
    }

    public function rest_create_proposal(WP_REST_Request $request)
    {
        if (! self::runtime_origin_is_exact()) {
            return self::error('raos_runtime_origin_invalid', 409);
        }
        if (! self::writes_enabled()) {
            return self::error('raos_writes_disabled', 503);
        }
        if (! $this->canonicalization_self_check()) {
            return self::error('raos_canonicalization_unavailable', 500);
        }
        if ($request->get_header('content-type') !== 'application/json') {
            return self::error('raos_content_type_invalid', 400);
        }
        $input = $request->get_json_params();
        if (! is_array($input)) {
            return self::error('raos_proposal_invalid', 400);
        }
        $normalized = $this->normalize_proposal_request($input);
        if (is_wp_error($normalized)) {
            return $normalized;
        }
        $canonical = self::canonical_json($normalized);
        if (! is_string($canonical) || $request->get_body() !== $canonical) {
            return self::error('raos_proposal_invalid', 400);
        }
        $proposal_id = hash('sha256', $canonical);
        $existing = $this->proposal_replay_row($proposal_id);
        if (is_wp_error($existing)) {
            return $existing;
        }
        if (is_array($existing)) {
            return $this->validated_proposal_replay_response(
                $existing,
                $proposal_id,
                $canonical
            );
        }

        $mutex_name = $this->auxiliary_mutex_name(
            self::PROPOSAL_CREATE_MUTEX_PURPOSE
        );
        $mutex_state = $this->acquire_auxiliary_mutex($mutex_name);
        if ($mutex_state === 'BUSY') {
            return self::error('raos_proposal_creation_busy', 429);
        }
        if ($mutex_state !== 'ACQUIRED') {
            return self::error('raos_proposal_creation_lock_unavailable', 500);
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
            $response = self::error('raos_proposal_store_failed', 500);
        } finally {
            $released = $this->release_auxiliary_mutex($mutex_name);
        }
        if (! $released) {
            return self::error(
                'raos_proposal_creation_lock_release_uncertain',
                500
            );
        }
        return $response;
    }

    private function create_proposal_under_mutex(
        array $normalized,
        $canonical,
        $proposal_id,
        $mutex_name
    ) {
        global $wpdb;
        if (! $this->auxiliary_mutex_is_owned($mutex_name)) {
            return self::error('raos_proposal_creation_lock_lost', 500);
        }
        $locked_existing = $this->proposal_replay_row($proposal_id);
        if (is_wp_error($locked_existing)) {
            return $locked_existing;
        }
        if (is_array($locked_existing)) {
            return $this->validated_proposal_replay_response(
                $locked_existing,
                $proposal_id,
                $canonical
            );
        }
        $capacity = $this->proposal_capacity_available(get_current_user_id());
        if (is_wp_error($capacity)) {
            return $capacity;
        }
        $before_state_hash = $this->capture_before_state_hash($normalized);
        if (is_wp_error($before_state_hash)) {
            return $before_state_hash;
        }
        if (! $this->auxiliary_mutex_is_owned($mutex_name)) {
            return self::error('raos_proposal_creation_lock_lost', 500);
        }

        $created_epoch = time();
        $created_at = gmdate('Y-m-d H:i:s', $created_epoch);
        $expires_at = gmdate(
            'Y-m-d H:i:s',
            $created_epoch + $normalized['ttl_seconds']
        );
        if ($wpdb->query('START TRANSACTION') === false) {
            return self::error('raos_transaction_unavailable', 500);
        }
        $table = self::proposal_table();
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
                'before_state_hash' => $before_state_hash,
                'state_version' => 1,
            ),
            array('%s', '%s', '%s', '%s', '%s', '%s', '%d', '%s', '%d')
        );
        if ($inserted !== 1) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_proposal_store_failed', 500);
        }
        $audit_hash = self::append_audit(
            'PROPOSAL_CREATED',
            $proposal_id,
            'PROPOSED',
            get_current_user_id()
        );
        if (! is_string($audit_hash)
            || ! $this->auxiliary_mutex_is_owned($mutex_name)) {
            $wpdb->query('ROLLBACK');
            return self::error(
                is_string($audit_hash)
                    ? 'raos_proposal_creation_lock_lost'
                    : 'raos_audit_write_failed',
                500
            );
        }
        if ($wpdb->query('COMMIT') === false) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_transaction_commit_failed', 500);
        }
        return $this->proposal_response(
            array(
                'proposal_id' => $proposal_id,
                'operation' => $normalized['operation'],
                'state' => 'PROPOSED',
                'created_at' => $created_at,
                'expires_at' => $expires_at,
            ),
            false
        );
    }

    private function proposal_replay_row($proposal_id)
    {
        global $wpdb;
        $table = self::proposal_table();
        $row = $wpdb->get_row(
            $wpdb->prepare(
                "SELECT proposal_id, operation, request_json, state, created_at,
                        expires_at, proposer_user_id
                 FROM {$table} WHERE proposal_id = %s LIMIT 1",
                $proposal_id
            ),
            ARRAY_A
        );
        if ($wpdb->last_error !== '') {
            return self::error('raos_proposal_lookup_failed', 500);
        }
        return is_array($row) ? $row : null;
    }

    private function validated_proposal_replay_response(
        array $row,
        $proposal_id,
        $canonical
    ) {
        $states = array(
            'PROPOSED',
            'APPROVED',
            'APPLYING',
            'APPLIED',
            'FAILED',
            'NEEDS_RECOVERY',
            'EXPIRED',
        );
        if (! $this->has_exact_keys(
            $row,
            array(
                'proposal_id',
                'operation',
                'request_json',
                'state',
                'created_at',
                'expires_at',
                'proposer_user_id',
            )
        )
            || ! is_string($row['proposal_id'])
            || ! hash_equals($proposal_id, $row['proposal_id'])
            || ! is_string($row['request_json'])
            || ! hash_equals($canonical, $row['request_json'])
            || ! hash_equals($proposal_id, hash('sha256', $row['request_json']))
            || ! is_string($row['operation'])
            || ! is_string($row['state'])
            || ! in_array($row['state'], $states, true)
            || ! is_string($row['created_at'])
            || ! is_string($row['expires_at'])
            || (! is_int($row['proposer_user_id'])
                && (! is_string($row['proposer_user_id'])
                    || ! preg_match('/\A[1-9][0-9]*\z/', $row['proposer_user_id'])))
            || (int) $row['proposer_user_id'] !== get_current_user_id()) {
            return self::error('raos_proposal_record_invalid', 409);
        }
        $created_epoch = self::strict_mysql_utc_epoch($row['created_at']);
        $expires_epoch = self::strict_mysql_utc_epoch($row['expires_at']);
        if (! is_int($created_epoch)
            || ! is_int($expires_epoch)
            || $expires_epoch - $created_epoch !== self::DEFAULT_TTL) {
            return self::error('raos_proposal_record_invalid', 409);
        }
        $decoded = json_decode($row['request_json'], true);
        $normalized = is_array($decoded)
            ? $this->normalize_proposal_request($decoded)
            : self::error('raos_proposal_record_invalid', 409);
        if (is_wp_error($normalized)
            || $normalized['operation'] !== $row['operation']
            || self::canonical_json($normalized) !== $row['request_json']) {
            return self::error('raos_proposal_record_invalid', 409);
        }
        return $this->proposal_response($row, true);
    }

    private static function strict_mysql_utc_epoch($value)
    {
        if (! is_string($value)
            || ! preg_match(
                '/\A[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01]) '
                . '(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\z/',
                $value
            )) {
            return null;
        }
        $epoch = strtotime($value . ' UTC');
        if ($epoch === false || gmdate('Y-m-d H:i:s', $epoch) !== $value) {
            return null;
        }
        return $epoch;
    }

    private function proposal_capacity_available($user_id)
    {
        global $wpdb;
        $table = self::proposal_table();
        $total = $this->strict_count($wpdb->get_var("SELECT COUNT(*) FROM {$table}"));
        if (is_wp_error($total)) {
            return $total;
        }
        if ($total >= self::MAX_PROPOSAL_ROWS) {
            return self::error('raos_proposal_capacity_reached', 429);
        }
        $now = gmdate('Y-m-d H:i:s');
        $active = $this->strict_count($wpdb->get_var(
            $wpdb->prepare(
                "SELECT COUNT(*) FROM {$table}
                 WHERE proposer_user_id = %d
                   AND state IN (%s,%s,%s) AND expires_at > %s",
                $user_id,
                'PROPOSED',
                'APPROVED',
                'APPLYING',
                $now
            )
        ));
        if (is_wp_error($active)) {
            return $active;
        }
        if ($active >= self::MAX_ACTIVE_PROPOSALS_PER_PROPOSER) {
            return self::error('raos_active_proposal_limit_reached', 429);
        }
        $window = gmdate('Y-m-d H:i:s', time() - self::PROPOSAL_RATE_WINDOW_SECONDS);
        $recent = $this->strict_count($wpdb->get_var(
            $wpdb->prepare(
                "SELECT COUNT(*) FROM {$table}
                 WHERE proposer_user_id = %d AND created_at >= %s",
                $user_id,
                $window
            )
        ));
        if (is_wp_error($recent)) {
            return $recent;
        }
        if ($recent >= self::MAX_PROPOSALS_PER_WINDOW) {
            return self::error('raos_proposal_rate_limited', 429);
        }
        return true;
    }

    private function strict_count($value)
    {
        global $wpdb;
        if ($wpdb->last_error !== ''
            || (! is_int($value)
                && (! is_string($value)
                    || strlen($value) > 18
                    || ! preg_match('/\A(?:0|[1-9][0-9]*)\z/', $value)))) {
            return self::error('raos_capacity_check_failed', 500);
        }
        $count = (int) $value;
        if ($count < 0 || $count > PHP_INT_MAX) {
            return self::error('raos_capacity_check_failed', 500);
        }
        return $count;
    }

    private function capture_before_state_hash(array $proposal)
    {
        if ($proposal['operation'] === 'APPLY_YOAST_PROFILE') {
            if (! defined('WPSEO_VERSION') || WPSEO_VERSION !== self::YOAST_VERSION) {
                return self::error('raos_yoast_version_mismatch', 409);
            }
            $derived = $this->derived_yoast_profile();
            if (is_wp_error($derived)
                || self::canonical_json($derived['wpseo'])
                    !== self::canonical_json($proposal['yoast_profile']['wpseo'])
                || self::canonical_json($derived['wpseo_social'])
                    !== self::canonical_json($proposal['yoast_profile']['wpseo_social'])) {
                return self::error('raos_yoast_profile_prerequisite_failed', 409);
            }
            return $this->capture_yoast_before_state_hash();
        }
        $state = $this->capture_theme_state();
        if (is_wp_error($state)
            || $state['active'] !== true
            || $state['installed_version'] !== $proposal['theme']['from_version']) {
            return self::error('raos_theme_before_state_invalid', 409);
        }
        return $state['before_state_hash'];
    }

    private function proposal_response(array $row, $replayed)
    {
        return new WP_REST_Response(
            array(
                'schema' => 'RAOS_OPERATOR_PROPOSAL_V1',
                'proposal_id' => $row['proposal_id'],
                'operation' => $row['operation'],
                'state' => $row['state'],
                'created_at' => self::iso8601($row['created_at']),
                'expires_at' => self::iso8601($row['expires_at']),
                'replayed' => (bool) $replayed,
            ),
            201,
            array('ETag' => '"' . $row['proposal_id'] . '"')
        );
    }

    private function normalize_proposal_request(array $input)
    {
        $common = array(
            'operator_contract_version',
            'operation',
            'profile_version',
            'request_token',
            'site_origin',
            'ttl_seconds',
        );
        if (! isset($input['operation'])
            || ! is_string($input['operation'])
            || ! isset($input['operator_contract_version'])
            || $input['operator_contract_version'] !== self::OPERATOR_CONTRACT_VERSION
            || ! isset($input['profile_version'])
            || $input['profile_version'] !== self::PROFILE_VERSION
            || ! isset($input['site_origin'])
            || $input['site_origin'] !== self::SITE_ORIGIN
            || ! isset($input['request_token'])
            || ! is_string($input['request_token'])
            || ! preg_match('/\A[a-f0-9]{64}\z/', $input['request_token'])) {
            return self::error('raos_proposal_invalid', 400);
        }
        $ttl = isset($input['ttl_seconds']) ? $input['ttl_seconds'] : null;
        if (! is_int($ttl) || $ttl !== self::DEFAULT_TTL) {
            return self::error('raos_proposal_ttl_invalid', 400);
        }
        if ($input['operation'] === 'APPLY_YOAST_PROFILE') {
            $keys = array_merge($common, array('yoast_profile'));
            if (! $this->has_exact_keys($input, $keys)
                || ! is_array($input['yoast_profile'])
                || self::canonical_json($input['yoast_profile'])
                    !== self::canonical_json($this->fixed_yoast_profile_payload())) {
                return self::error('raos_proposal_invalid', 400);
            }
            return array(
                'operator_contract_version' => self::OPERATOR_CONTRACT_VERSION,
                'operation' => 'APPLY_YOAST_PROFILE',
                'profile_version' => self::PROFILE_VERSION,
                'request_token' => $input['request_token'],
                'site_origin' => self::SITE_ORIGIN,
                'ttl_seconds' => $ttl,
                'yoast_profile' => $this->fixed_yoast_profile_payload(),
            );
        }
        if ($input['operation'] !== 'UPDATE_CHILD_THEME'
            || ! $this->has_exact_keys($input, array_merge($common, array('theme')))
            || ! isset($input['theme'])
            || ! is_array($input['theme'])) {
            return self::error('raos_operation_unsupported', 400);
        }
        $theme = $this->normalize_theme_spec($input['theme']);
        if (is_wp_error($theme)) {
            return $theme;
        }
        return array(
            'operator_contract_version' => self::OPERATOR_CONTRACT_VERSION,
            'operation' => 'UPDATE_CHILD_THEME',
            'profile_version' => self::PROFILE_VERSION,
            'request_token' => $input['request_token'],
            'site_origin' => self::SITE_ORIGIN,
            'theme' => $theme,
            'ttl_seconds' => $ttl,
        );
    }

    private function canonicalization_self_check()
    {
        $vector = array(
            'operator_contract_version' => self::OPERATOR_CONTRACT_VERSION,
            'operation' => 'APPLY_YOAST_PROFILE',
            'profile_version' => self::PROFILE_VERSION,
            'request_token' => str_repeat('0123456789abcdef', 4),
            'site_origin' => self::SITE_ORIGIN,
            'ttl_seconds' => self::DEFAULT_TTL,
            'yoast_profile' => $this->fixed_yoast_profile_payload(),
        );
        $canonical = self::canonical_json($vector);
        return is_string($canonical)
            && strlen($canonical) === self::CANONICAL_VECTOR_BYTES
            && hash_equals(
                self::CANONICAL_VECTOR_SHA256,
                hash('sha256', $canonical)
            );
    }

    private function fixed_yoast_profile_payload()
    {
        return array(
            'plugin_slug' => 'wordpress-seo',
            'version' => self::YOAST_VERSION,
            'wpseo' => array(
                'enable_ai_generator' => false,
                'enable_headless_rest_endpoints' => false,
                'enable_index_now' => false,
                'enable_schema' => false,
                'enable_schema_aggregation_endpoint' => false,
                'enable_xml_sitemap' => true,
                'google_site_kit_feature_enabled' => false,
                'googleverify' => '',
                'semrush_integration_active' => false,
                'tracking' => false,
                'wincher_integration_active' => false,
            ),
            'wpseo_social' => array(
                'og_default_image' => self::SITE_ORIGIN
                    . '/wp-content/themes/' . self::THEME_SLUG . '/'
                    . self::SOCIAL_IMAGE_PATH,
                'og_default_image_id' => '',
                'opengraph' => true,
                'twitter' => true,
                'twitter_card_type' => 'summary_large_image',
            ),
        );
    }

    private function normalize_theme_spec(array $theme)
    {
        $keys = array(
            'slug',
            'from_version',
            'to_version',
            'package_size',
            'package_sha256',
            'file_manifest',
        );
        if (! $this->has_exact_keys($theme, $keys)
            || $theme['slug'] !== self::THEME_SLUG
            || ! is_string($theme['from_version'])
            || ! is_string($theme['to_version'])
            || $theme['from_version'] !== self::THEME_FROM_VERSION
            || ! preg_match('/\A(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\z/', $theme['from_version'])
            || ! preg_match('/\A(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\z/', $theme['to_version'])
            || ! is_int($theme['package_size'])
            || $theme['package_size'] < 1
            || $theme['package_size'] > self::MAX_PACKAGE_BYTES
            || ! is_string($theme['package_sha256'])
            || ! preg_match('/\A[a-f0-9]{64}\z/', $theme['package_sha256'])
            || ! is_array($theme['file_manifest'])
            || count($theme['file_manifest']) < 1
            || count($theme['file_manifest']) > self::MAX_FILE_COUNT) {
            return self::error('raos_theme_spec_invalid', 400);
        }
        $manifest = array();
        $seen = array();
        $total = 0;
        foreach ($theme['file_manifest'] as $entry) {
            if (! is_array($entry)
                || ! $this->has_exact_keys($entry, array('path', 'size', 'sha256'))
                || ! is_string($entry['path'])
                || strlen($entry['path']) > 240
                || ! preg_match('/\A[A-Za-z0-9._\/-]+\z/', $entry['path'])
                || ! $this->safe_relative_path($entry['path'])
                || substr($entry['path'], -1) === '/'
                || ! is_int($entry['size'])
                || $entry['size'] < 1
                || $entry['size'] > self::MAX_FILE_BYTES
                || ! is_string($entry['sha256'])
                || ! preg_match('/\A[a-f0-9]{64}\z/', $entry['sha256'])) {
                return self::error('raos_theme_manifest_invalid', 400);
            }
            $folded = strtolower($entry['path']);
            if (isset($seen[$folded])) {
                return self::error('raos_theme_manifest_duplicate', 400);
            }
            $seen[$folded] = true;
            $total += $entry['size'];
            if ($total > self::MAX_UNCOMPRESSED_BYTES) {
                return self::error('raos_theme_manifest_oversized', 400);
            }
            $manifest[] = array(
                'path' => $entry['path'],
                'size' => $entry['size'],
                'sha256' => $entry['sha256'],
            );
        }
        if (! isset($seen['style.css'])) {
            return self::error('raos_theme_manifest_invalid', 400);
        }
        usort(
            $manifest,
            function ($left, $right) {
                return strcmp($left['path'], $right['path']);
            }
        );
        $normalized = array(
            'slug' => self::THEME_SLUG,
            'from_version' => $theme['from_version'],
            'to_version' => $theme['to_version'],
            'package_size' => $theme['package_size'],
            'package_sha256' => $theme['package_sha256'],
            'file_manifest' => $manifest,
        );
        $reviewed = $this->reviewed_theme_release_binding();
        if (is_wp_error($reviewed)) {
            return $reviewed;
        }
        if (self::canonical_json($normalized) !== self::REVIEWED_THEME_RELEASE_JSON) {
            return self::error('raos_theme_release_not_reviewed', 409);
        }
        if (self::REVIEWED_THEME_RELEASE_STATE !== 'AVAILABLE'
            || version_compare(
                $reviewed['to_version'],
                $reviewed['from_version'],
                '<='
            )) {
            return self::error('raos_theme_release_not_available', 409);
        }
        return $reviewed;
    }

    private function reviewed_theme_release_binding()
    {
        if (! hash_equals(
            self::REVIEWED_THEME_RELEASE_JSON_SHA256,
            hash('sha256', self::REVIEWED_THEME_RELEASE_JSON)
        )) {
            return self::error('raos_theme_release_binding_invalid', 500);
        }
        $reviewed = json_decode(self::REVIEWED_THEME_RELEASE_JSON, true);
        if (! is_array($reviewed)
            || ! $this->has_exact_keys(
                $reviewed,
                array(
                    'slug',
                    'from_version',
                    'to_version',
                    'package_size',
                    'package_sha256',
                    'file_manifest',
                )
            )
            || self::canonical_json($reviewed) !== self::REVIEWED_THEME_RELEASE_JSON) {
            return self::error('raos_theme_release_binding_invalid', 500);
        }
        return $reviewed;
    }

    private function has_only_keys(array $value, array $allowed)
    {
        return count(array_diff(array_keys($value), $allowed)) === 0;
    }

    private function has_exact_keys(array $value, array $expected)
    {
        $actual = array_keys($value);
        sort($actual, SORT_STRING);
        sort($expected, SORT_STRING);
        return $actual === $expected;
    }

    private function safe_relative_path($path)
    {
        if (! is_string($path)
            || $path === ''
            || strpos($path, "\0") !== false
            || strpos($path, '\\') !== false
            || substr($path, 0, 1) === '/'
            || preg_match('/\A[A-Za-z]:/', $path)
            || strpos($path, '//') !== false) {
            return false;
        }
        foreach (explode('/', $path) as $part) {
            if ($part === '' || $part === '.' || $part === '..') {
                return false;
            }
        }
        return true;
    }

    private function capture_theme_state()
    {
        $theme = wp_get_theme(self::THEME_SLUG);
        $version = $theme->exists() ? $theme->get('Version') : null;
        if (! is_string($version)
            || ! preg_match('/\A(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\z/', $version)) {
            return self::error('raos_theme_state_unreadable', 409);
        }
        $root = get_theme_root(self::THEME_SLUG) . '/' . self::THEME_SLUG;
        $real_root = realpath($root);
        if (! is_string($real_root) || ! is_dir($real_root) || is_link($root)) {
            return self::error('raos_theme_state_unreadable', 409);
        }
        $manifest = array();
        try {
            $iterator = new RecursiveIteratorIterator(
                new RecursiveDirectoryIterator($root, FilesystemIterator::SKIP_DOTS),
                RecursiveIteratorIterator::LEAVES_ONLY
            );
            foreach ($iterator as $file_info) {
                if ($file_info->isLink() || ! $file_info->isFile()) {
                    return self::error('raos_theme_state_unreadable', 409);
                }
                if (count($manifest) >= self::MAX_FILE_COUNT) {
                    return self::error('raos_theme_state_unreadable', 409);
                }
                $absolute = $file_info->getPathname();
                $relative = substr($absolute, strlen($root) + 1);
                $relative = str_replace(DIRECTORY_SEPARATOR, '/', $relative);
                $size = $file_info->getSize();
                if (! is_string($relative)
                    || ! preg_match('/\A[A-Za-z0-9._\/-]+\z/', $relative)
                    || ! $this->safe_relative_path($relative)
                    || ! is_int($size)
                    || $size < 1
                    || $size > self::MAX_FILE_BYTES) {
                    return self::error('raos_theme_state_unreadable', 409);
                }
                $digest = hash_file('sha256', $absolute);
                if (! is_string($digest)) {
                    return self::error('raos_theme_state_unreadable', 409);
                }
                $manifest[] = array(
                    'path' => $relative,
                    'size' => $size,
                    'sha256' => $digest,
                );
            }
        } catch (UnexpectedValueException $exception) {
            return self::error('raos_theme_state_unreadable', 409);
        }
        if (count($manifest) < 1) {
            return self::error('raos_theme_state_unreadable', 409);
        }
        usort(
            $manifest,
            function ($left, $right) {
                return strcmp($left['path'], $right['path']);
            }
        );
        $tree_json = self::canonical_json($manifest);
        if (! is_string($tree_json)) {
            return self::error('raos_theme_state_unreadable', 409);
        }
        $tree_hash = hash('sha256', $tree_json);
        $active = get_stylesheet() === self::THEME_SLUG;
        $before_json = self::canonical_json(
            array(
                'active' => $active,
                'installed_version' => $version,
                'slug' => self::THEME_SLUG,
                'tree_sha256' => $tree_hash,
            )
        );
        if (! is_string($before_json)) {
            return self::error('raos_theme_state_unreadable', 409);
        }
        return array(
            'active' => $active,
            'installed_version' => $version,
            'file_manifest' => $manifest,
            'tree_sha256' => $tree_hash,
            'before_state_hash' => hash('sha256', $before_json),
        );
    }

    private static function canonical_json($value)
    {
        $normalized = self::sort_for_json($value);
        $flags = JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE;
        $json = wp_json_encode($normalized, $flags);
        return is_string($json) ? $json : null;
    }

    private static function sort_for_json($value)
    {
        if (! is_array($value)) {
            return $value;
        }
        $keys = array_keys($value);
        $is_list = $keys === range(0, count($value) - 1);
        if ($is_list) {
            $result = array();
            foreach ($value as $item) {
                $result[] = self::sort_for_json($item);
            }
            return $result;
        }
        ksort($value, SORT_STRING);
        foreach ($value as $key => $item) {
            $value[$key] = self::sort_for_json($item);
        }
        return $value;
    }

    public function register_admin_page()
    {
        add_management_page(
            'RAOS Operator Approvals',
            'RAOS Operator',
            'manage_options',
            'raos-bounded-operator',
            array($this, 'render_admin_page')
        );
    }

    public function render_admin_page()
    {
        if (! current_user_can('manage_options')) {
            wp_die(esc_html__('You do not have permission to access this page.'));
        }
        global $wpdb;
        $table = self::proposal_table();
        $rows = $wpdb->get_results(
            $wpdb->prepare(
                "SELECT proposal_id, operation, request_json, expires_at,
                        proposer_user_id, before_state_hash
                 FROM {$table}
                 WHERE state = %s AND expires_at > %s
                 ORDER BY internal_id ASC LIMIT 50",
                'PROPOSED',
                gmdate('Y-m-d H:i:s')
            ),
            ARRAY_A
        );
        ?>
        <div class="wrap">
            <h1><?php echo esc_html('RAOS Operator Approvals'); ?></h1>
            <p><?php echo esc_html('Approval does not execute a change. It only authorizes the exact proposal until its displayed expiry.'); ?></p>
            <?php if (! self::writes_enabled()) : ?>
                <div class="notice notice-warning"><p><?php echo esc_html('The host write gate is disabled.'); ?></p></div>
            <?php endif; ?>
            <?php if (empty($rows)) : ?>
                <p><?php echo esc_html('No unexpired proposals await approval.'); ?></p>
            <?php else : ?>
                <?php foreach ($rows as $row) : ?>
                    <hr>
                    <h2><?php echo esc_html($row['operation']); ?></h2>
                    <dl>
                        <dt><?php echo esc_html('Proposal ID'); ?></dt>
                        <dd><code><?php echo esc_html($row['proposal_id']); ?></code></dd>
                        <dt><?php echo esc_html('Expires (UTC)'); ?></dt>
                        <dd><?php echo esc_html($row['expires_at']); ?></dd>
                        <dt><?php echo esc_html('Before-state hash'); ?></dt>
                        <dd><code><?php echo esc_html($row['before_state_hash']); ?></code></dd>
                    </dl>
                    <?php $this->render_proposal_impact($row); ?>
                    <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                        <input type="hidden" name="action" value="raos_operator_approve">
                        <input type="hidden" name="proposal_id" value="<?php echo esc_attr($row['proposal_id']); ?>">
                        <?php wp_nonce_field('raos_operator_approve_' . $row['proposal_id']); ?>
                        <p>
                            <label>
                                <?php echo esc_html('Reason (10–300 characters)'); ?><br>
                                <textarea name="approval_reason" rows="3" cols="70" minlength="10" maxlength="300" required></textarea>
                            </label>
                        </p>
                        <p>
                            <label>
                                <?php echo esc_html('Type the final 12 characters of the proposal ID'); ?><br>
                                <input name="hash_confirmation" type="text" minlength="12" maxlength="12" autocomplete="off" required>
                            </label>
                        </p>
                        <p>
                            <label>
                                <?php echo esc_html('Re-enter your WordPress password'); ?><br>
                                <input name="current_password" type="password" autocomplete="current-password" required>
                            </label>
                        </p>
                        <?php submit_button('Approve exact proposal', 'primary', 'submit', false); ?>
                    </form>
                <?php endforeach; ?>
            <?php endif; ?>
        </div>
        <?php
    }

    private function render_proposal_impact(array $row)
    {
        $request = json_decode($row['request_json'], true);
        if (! is_array($request)) {
            echo '<p>' . esc_html('Impact details are unavailable; do not approve this proposal.') . '</p>';
            return;
        }
        $normalized = $this->normalize_proposal_request($request);
        if (is_wp_error($normalized)
            || self::canonical_json($normalized) !== $row['request_json']) {
            echo '<p>' . esc_html('Impact details are invalid; do not approve this proposal.') . '</p>';
            return;
        }
        $request = $normalized;
        echo '<h3>' . esc_html('Impact') . '</h3>';
        if ($request['operation'] === 'APPLY_YOAST_PROFILE'
            && isset($request['yoast_profile']['wpseo'], $request['yoast_profile']['wpseo_social'])
            && is_array($request['yoast_profile']['wpseo'])
            && is_array($request['yoast_profile']['wpseo_social'])) {
            echo '<p>' . esc_html('Exact target: Yoast wpseo and wpseo_social allowlisted keys') . '</p><ul>';
            foreach (array('wpseo', 'wpseo_social') as $option_name) {
                foreach ($request['yoast_profile'][$option_name] as $key => $value) {
                    echo '<li><code>' . esc_html($option_name . '.' . $key) . '</code>: '
                        . '<code>' . esc_html($this->impact_value($value)) . '</code></li>';
                }
            }
            echo '</ul>';
            return;
        }
        if ($request['operation'] === 'UPDATE_CHILD_THEME'
            && isset($request['theme'])
            && is_array($request['theme'])) {
            $theme = $request['theme'];
            echo '<p>' . esc_html('Exact target: kurashinoshirube-child') . '</p><ul>';
            echo '<li>' . esc_html('Version: ' . $theme['from_version'] . ' → ' . $theme['to_version']) . '</li>';
            echo '<li>' . esc_html('Package bytes: ' . (string) $theme['package_size']) . '</li>';
            echo '<li>' . esc_html('File count: ' . (string) count($theme['file_manifest'])) . '</li>';
            echo '<li>' . esc_html('Package SHA-256: ') . '<code>'
                . esc_html($theme['package_sha256']) . '</code></li>';
            echo '</ul>';
            return;
        }
        echo '<p>' . esc_html('Impact details are invalid; do not approve this proposal.') . '</p>';
    }

    private function impact_value($value)
    {
        if ($value === true) {
            return 'true';
        }
        if ($value === false) {
            return 'false';
        }
        if ($value === '') {
            return '""';
        }
        return is_string($value) ? $value : '[invalid]';
    }

    public function handle_approval()
    {
        if (! self::writes_enabled()) {
            wp_die(esc_html('The host write gate is disabled.'), '', array('response' => 503));
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
        if (! preg_match('/\A[a-f0-9]{64}\z/', $proposal_id)) {
            wp_die(esc_html('The proposal is invalid.'), '', array('response' => 400));
        }
        check_admin_referer('raos_operator_approve_' . $proposal_id);
        $reason_input = isset($_POST['approval_reason'])
            ? wp_unslash($_POST['approval_reason'])
            : '';
        if (! is_string($reason_input)
            || strlen($reason_input) > 1200
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
            ? (string) wp_unslash($_POST['current_password'])
            : '';
        if (! hash_equals(substr($proposal_id, -12), $confirmation)) {
            wp_die(esc_html('The approval evidence is invalid.'), '', array('response' => 400));
        }
        $current_user = wp_get_current_user();
        if (! $current_user->exists()
            || ! wp_check_password($reauthentication_input, $current_user->user_pass, $current_user->ID)) {
            wp_die(esc_html('Password reauthentication failed.'), '', array('response' => 403));
        }

        global $wpdb;
        $table = self::proposal_table();
        $row = $wpdb->get_row(
            $wpdb->prepare(
                "SELECT proposer_user_id, expires_at, request_json FROM {$table}
                 WHERE proposal_id = %s AND state = %s AND expires_at > %s LIMIT 1",
                $proposal_id,
                'PROPOSED',
                gmdate('Y-m-d H:i:s')
            ),
            ARRAY_A
        );
        if (! is_array($row) || (int) $row['proposer_user_id'] === (int) $current_user->ID) {
            wp_die(esc_html('The proposal cannot be approved.'), '', array('response' => 409));
        }
        $stored_request = json_decode($row['request_json'], true);
        $normalized_request = is_array($stored_request)
            ? $this->normalize_proposal_request($stored_request)
            : self::error('raos_proposal_record_invalid', 409);
        if (is_wp_error($normalized_request)
            || self::canonical_json($normalized_request) !== $row['request_json']
            || ! hash_equals($proposal_id, hash('sha256', $row['request_json']))) {
            wp_die(esc_html('The proposal record is invalid.'), '', array('response' => 409));
        }
        $approved_at = gmdate('Y-m-d H:i:s');
        $approval_expires_at = $row['expires_at'];
        $approval_material = self::canonical_json(
            array(
                'approval_expires_at' => $approval_expires_at,
                'approved_at' => $approved_at,
                'approved_by_user_id' => (int) $current_user->ID,
                'normalized_reason' => $reason,
                'proposal_id' => $proposal_id,
            )
        );
        if (! is_string($approval_material)) {
            wp_die(esc_html('The approval evidence is invalid.'), '', array('response' => 409));
        }
        $approval_evidence_hash = hash('sha256', $approval_material);
        if ($wpdb->query('START TRANSACTION') === false) {
            wp_die(esc_html('Approval transaction unavailable.'), '', array('response' => 500));
        }
        $updated = $wpdb->query(
            $wpdb->prepare(
                "UPDATE {$table}
                 SET state = %s, approved_by_user_id = %d, approved_at = %s,
                     approval_expires_at = %s, approval_reason = %s,
                     approval_evidence_hash = %s, state_version = state_version + 1
                 WHERE proposal_id = %s AND state = %s AND expires_at > %s",
                'APPROVED',
                $current_user->ID,
                $approved_at,
                $approval_expires_at,
                $reason,
                $approval_evidence_hash,
                $proposal_id,
                'PROPOSED',
                gmdate('Y-m-d H:i:s')
            )
        );
        if ($updated !== 1) {
            $wpdb->query('ROLLBACK');
            wp_die(esc_html('The proposal state changed before approval.'), '', array('response' => 409));
        }
        if (self::append_audit(
            'HUMAN_APPROVED',
            $proposal_id,
            'APPROVED',
            $current_user->ID
        ) === false) {
            $wpdb->query('ROLLBACK');
            wp_die(esc_html('Approval audit persistence failed.'), '', array('response' => 500));
        }
        if ($wpdb->query('COMMIT') === false) {
            $wpdb->query('ROLLBACK');
            wp_die(esc_html('Approval transaction commit failed.'), '', array('response' => 500));
        }
        wp_safe_redirect(
            add_query_arg(
                array('page' => 'raos-bounded-operator', 'raos_operator_notice' => 'approved'),
                admin_url('tools.php')
            )
        );
        exit;
    }

    public function rest_apply(WP_REST_Request $request)
    {
        if (! self::runtime_origin_is_exact()) {
            return self::error('raos_runtime_origin_invalid', 409);
        }
        if (! self::writes_enabled()) {
            return self::error('raos_writes_disabled', 503);
        }
        $proposal_id = (string) $request['proposal_id'];
        $if_match = (string) $request->get_header('if-match');
        if (! hash_equals('"' . $proposal_id . '"', $if_match)) {
            return self::error('raos_precondition_failed', 412);
        }
        $idempotency_key = (string) $request->get_header('idempotency-key');
        if (! hash_equals($proposal_id, $idempotency_key)) {
            return self::error('raos_idempotency_key_invalid', 400);
        }

        global $wpdb;
        $table = self::proposal_table();
        $row = $wpdb->get_row(
            $wpdb->prepare(
                "SELECT proposal_id, operation, request_json, state, expires_at,
                        proposer_user_id, before_state_hash, approved_by_user_id,
                        approved_at, approval_expires_at, approval_reason,
                        approval_evidence_hash, idempotency_key, result_code
                 FROM {$table} WHERE proposal_id = %s LIMIT 1",
                $proposal_id
            ),
            ARRAY_A
        );
        if (! is_array($row)) {
            return self::error('raos_proposal_not_found', 404);
        }
        $spec = $this->validated_stored_proposal($row, $proposal_id);
        if (is_wp_error($spec)) {
            return $spec;
        }
        if ($row['state'] === 'APPLIED'
            && is_string($row['idempotency_key'])
            && hash_equals($row['idempotency_key'], $idempotency_key)) {
            if (! $this->approval_evidence_is_valid($row, $proposal_id, false)) {
                return self::error('raos_approval_evidence_invalid', 409);
            }
            return $this->apply_response($row, true);
        }
        if ($row['state'] !== 'APPLYING'
            && strtotime($row['expires_at'] . ' UTC') <= time()) {
            if ($wpdb->query('START TRANSACTION') === false) {
                return self::error('raos_transaction_unavailable', 500);
            }
            $expired = $wpdb->query(
                $wpdb->prepare(
                    "UPDATE {$table} SET state = %s, result_code = %s,
                     completed_at = %s, state_version = state_version + 1
                     WHERE proposal_id = %s AND state IN (%s,%s)",
                    'EXPIRED',
                    'PROPOSAL_EXPIRED',
                    gmdate('Y-m-d H:i:s'),
                    $proposal_id,
                    'PROPOSED',
                    'APPROVED'
                )
            );
            if ($expired === false) {
                $wpdb->query('ROLLBACK');
                return self::error('raos_expiry_transition_failed', 500);
            }
            if ($expired === 1
                && self::append_audit(
                    'PROPOSAL_EXPIRED',
                    $proposal_id,
                    'EXPIRED',
                    get_current_user_id()
                ) === false) {
                $wpdb->query('ROLLBACK');
                return self::error('raos_audit_write_failed', 500);
            }
            if ($wpdb->query('COMMIT') === false) {
                $wpdb->query('ROLLBACK');
                return self::error('raos_transaction_commit_failed', 500);
            }
            return self::error('raos_proposal_expired', 409);
        }
        if ($row['state'] !== 'APPLYING'
            && ($row['state'] !== 'APPROVED'
                || ! $this->approval_evidence_is_valid($row, $proposal_id, true))) {
            return self::error('raos_proposal_not_approved', 409);
        }
        $body = $request->get_body();
        if ($spec['operation'] === 'APPLY_YOAST_PROFILE') {
            if ($request->get_header('content-type') !== 'application/json'
                || $body !== '{}') {
                return self::error('raos_yoast_apply_payload_invalid', 400);
            }
        } elseif ($spec['operation'] === 'UPDATE_CHILD_THEME') {
            if ($request->get_header('content-type') !== 'application/zip'
                || ! is_string($body)
                || strlen($body) !== $spec['theme']['package_size']
                || ! hash_equals($spec['theme']['package_sha256'], hash('sha256', $body))) {
                return self::error('raos_theme_apply_payload_invalid', 400);
            }
        } else {
            return self::error('raos_operation_unsupported', 400);
        }
        $mutex_name = $this->apply_mutex_name();
        $mutex = $this->acquire_apply_mutex($mutex_name);
        if (is_wp_error($mutex)) {
            return $mutex;
        }
        $mutex_released = false;
        try {
            $response = $this->execute_apply_under_mutex(
                $request,
                $proposal_id,
                $idempotency_key,
                $body,
                $mutex_name
            );
        } catch (Throwable $exception) {
            $response = $this->finish_unhandled_apply_exception($proposal_id);
        } finally {
            $mutex_released = $this->release_apply_mutex($mutex_name);
        }
        if (! $mutex_released) {
            return self::error('raos_apply_mutex_release_uncertain', 500);
        }
        return $response;
    }

    private function execute_apply_under_mutex(
        $request,
        $proposal_id,
        $idempotency_key,
        $body,
        $mutex_name
    ) {
        global $wpdb;
        $table = self::proposal_table();
        $row = $wpdb->get_row(
            $wpdb->prepare(
                "SELECT proposal_id, operation, request_json, state, expires_at,
                        proposer_user_id, before_state_hash, approved_by_user_id,
                        approved_at, approval_expires_at, approval_reason,
                        approval_evidence_hash, idempotency_key, result_code
                 FROM {$table} WHERE proposal_id = %s LIMIT 1",
                $proposal_id
            ),
            ARRAY_A
        );
        if (! is_array($row)) {
            return self::error('raos_proposal_not_found', 404);
        }
        $spec = $this->validated_stored_proposal($row, $proposal_id);
        if (is_wp_error($spec)) {
            return $spec;
        }
        if ($row['state'] === 'APPLIED'
            && is_string($row['idempotency_key'])
            && hash_equals($row['idempotency_key'], $idempotency_key)
            && $this->approval_evidence_is_valid($row, $proposal_id, false)) {
            return $this->apply_response($row, true);
        }
        if ($row['state'] === 'APPLYING') {
            if (! $this->apply_mutex_is_owned($mutex_name)) {
                return self::error('raos_apply_mutex_ownership_lost', 500);
            }
            return $this->finish_failure(
                $proposal_id,
                'NEEDS_RECOVERY',
                'ORPHANED_APPLYING_RECOVERED'
            );
        }
        if ($row['state'] !== 'APPROVED'
            || strtotime($row['expires_at'] . ' UTC') <= time()
            || ! $this->approval_evidence_is_valid($row, $proposal_id, true)) {
            return self::error('raos_proposal_not_approved', 409);
        }
        if ($spec['operation'] === 'APPLY_YOAST_PROFILE') {
            if ($request->get_header('content-type') !== 'application/json'
                || $body !== '{}') {
                return self::error('raos_yoast_apply_payload_invalid', 400);
            }
        } elseif ($spec['operation'] === 'UPDATE_CHILD_THEME') {
            if ($request->get_header('content-type') !== 'application/zip'
                || ! is_string($body)
                || strlen($body) !== $spec['theme']['package_size']
                || ! hash_equals($spec['theme']['package_sha256'], hash('sha256', $body))) {
                return self::error('raos_theme_apply_payload_invalid', 400);
            }
        } else {
            return self::error('raos_operation_unsupported', 400);
        }
        if (! $this->apply_mutex_is_owned($mutex_name)) {
            return self::error('raos_apply_mutex_ownership_lost', 500);
        }
        $current_before = $this->capture_before_state_hash($spec);
        if (is_wp_error($current_before)
            || ! hash_equals($row['before_state_hash'], $current_before)) {
            return self::error('raos_before_state_changed', 409);
        }
        if ($wpdb->query('START TRANSACTION') === false) {
            return self::error('raos_transaction_unavailable', 500);
        }
        $cas = $wpdb->query(
            $wpdb->prepare(
                "UPDATE {$table}
                 SET state = %s, idempotency_key = %s, apply_started_at = %s,
                     state_version = state_version + 1
                 WHERE proposal_id = %s AND state = %s
                   AND approved_by_user_id IS NOT NULL
                   AND approved_by_user_id <> proposer_user_id
                   AND before_state_hash = %s
                   AND approval_evidence_hash = %s
                   AND expires_at > %s AND approval_expires_at > %s",
                'APPLYING',
                $idempotency_key,
                gmdate('Y-m-d H:i:s'),
                $proposal_id,
                'APPROVED',
                $row['before_state_hash'],
                $row['approval_evidence_hash'],
                gmdate('Y-m-d H:i:s'),
                gmdate('Y-m-d H:i:s')
            )
        );
        if ($cas !== 1) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_apply_cas_failed', 409);
        }
        $audit_hash = self::append_audit(
            'APPLY_STARTED',
            $proposal_id,
            'APPLYING',
            get_current_user_id()
        );
        if (! is_string($audit_hash)) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_audit_write_failed', 500);
        }
        if ($wpdb->query('COMMIT') === false) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_transaction_commit_failed', 500);
        }
        if (! $this->apply_mutex_is_owned($mutex_name)) {
            return $this->finish_failure(
                $proposal_id,
                'NEEDS_RECOVERY',
                'APPLY_MUTEX_LOST_BEFORE_MUTATION'
            );
        }
        if ($spec['operation'] === 'APPLY_YOAST_PROFILE') {
            $result = $this->apply_yoast_profile(
                $spec['yoast_profile'],
                $row['before_state_hash']
            );
        } elseif ($spec['operation'] === 'UPDATE_CHILD_THEME') {
            $result = $this->apply_theme_package(
                $spec['theme'],
                $body,
                $row['before_state_hash']
            );
        } else {
            return $this->finish_failure($proposal_id, 'NEEDS_RECOVERY', 'OPERATION_RECORD_INVALID');
        }
        if (! $this->apply_mutex_is_owned($mutex_name)) {
            return $this->finish_failure(
                $proposal_id,
                'NEEDS_RECOVERY',
                'APPLY_MUTEX_OWNERSHIP_LOST'
            );
        }
        if ($result['ok']) {
            return $this->finish_success($proposal_id, $result['code']);
        }
        return $this->finish_failure($proposal_id, $result['state'], $result['code']);
    }

    private function apply_mutex_name()
    {
        global $wpdb;
        if (! defined('DB_NAME')
            || ! is_string(DB_NAME)
            || DB_NAME === ''
            || ! is_string($wpdb->prefix)
            || $wpdb->prefix === '') {
            return null;
        }
        $scope = DB_NAME . "\n" . $wpdb->prefix . "\n" . self::SITE_ORIGIN;
        return 'raos_apply_v1_' . substr(hash('sha256', $scope), 0, 48);
    }

    private function acquire_apply_mutex($mutex_name)
    {
        global $wpdb;
        if (! is_string($mutex_name)
            || ! preg_match('/\Araos_apply_v1_[a-f0-9]{48}\z/', $mutex_name)) {
            return self::error('raos_apply_mutex_scope_invalid', 500);
        }
        $acquired = $wpdb->get_var(
            $wpdb->prepare('SELECT GET_LOCK(%s, 0)', $mutex_name)
        );
        if ($wpdb->last_error !== '' || (string) $acquired !== '1') {
            return self::error('raos_apply_mutex_unavailable', 409);
        }
        return true;
    }

    private function release_apply_mutex($mutex_name)
    {
        global $wpdb;
        $released = $wpdb->get_var(
            $wpdb->prepare('SELECT RELEASE_LOCK(%s)', $mutex_name)
        );
        return $wpdb->last_error === '' && (string) $released === '1';
    }

    private function apply_mutex_is_owned($mutex_name)
    {
        global $wpdb;
        $owned = $wpdb->get_var(
            $wpdb->prepare(
                'SELECT (IS_USED_LOCK(%s) = CONNECTION_ID())',
                $mutex_name
            )
        );
        return $wpdb->last_error === '' && (string) $owned === '1';
    }

    private function finish_unhandled_apply_exception($proposal_id)
    {
        global $wpdb;
        $state = $wpdb->get_var(
            $wpdb->prepare(
                'SELECT state FROM ' . self::proposal_table()
                . ' WHERE proposal_id = %s LIMIT 1',
                $proposal_id
            )
        );
        if ($state === 'APPLYING') {
            return $this->finish_failure(
                $proposal_id,
                'NEEDS_RECOVERY',
                'APPLY_UNHANDLED_EXCEPTION'
            );
        }
        return self::error('raos_apply_execution_failed', 500);
    }

    private function validated_stored_proposal(array $row, $proposal_id)
    {
        $decoded = json_decode($row['request_json'], true);
        $normalized = is_array($decoded)
            ? $this->normalize_proposal_request($decoded)
            : self::error('raos_proposal_record_invalid', 409);
        if (is_wp_error($normalized)
            || self::canonical_json($normalized) !== $row['request_json']
            || ! hash_equals($proposal_id, hash('sha256', $row['request_json']))
            || $normalized['operation'] !== $row['operation']) {
            return self::error('raos_proposal_record_invalid', 409);
        }
        return $normalized;
    }

    private function approval_evidence_is_valid(array $row, $proposal_id, $require_unexpired)
    {
        if (empty($row['approved_by_user_id'])
            || (int) $row['approved_by_user_id'] === (int) $row['proposer_user_id']
            || ! is_string($row['approved_at'])
            || ! is_string($row['approval_expires_at'])
            || ($require_unexpired && strtotime($row['approval_expires_at'] . ' UTC') <= time())
            || ! is_string($row['approval_reason'])
            || ! is_string($row['approval_evidence_hash'])) {
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
            && hash_equals($row['approval_evidence_hash'], hash('sha256', $material));
    }

    private function apply_yoast_profile(array $approved_profile, $before_state_hash)
    {
        if (! defined('WPSEO_VERSION') || WPSEO_VERSION !== self::YOAST_VERSION) {
            return array('ok' => false, 'state' => 'FAILED', 'code' => 'YOAST_VERSION_MISMATCH');
        }
        $profile = $this->derived_yoast_profile();
        if (is_wp_error($profile)) {
            return array('ok' => false, 'state' => 'FAILED', 'code' => 'YOAST_PROFILE_PREREQUISITE_FAILED');
        }
        $fixed = $this->fixed_yoast_profile_payload();
        if (self::canonical_json($approved_profile) !== self::canonical_json($fixed)
            || self::canonical_json($profile['wpseo'])
                !== self::canonical_json($approved_profile['wpseo'])
            || self::canonical_json($profile['wpseo_social'])
                !== self::canonical_json($approved_profile['wpseo_social'])) {
            return array('ok' => false, 'state' => 'FAILED', 'code' => 'YOAST_APPROVED_PROFILE_MISMATCH');
        }
        $profile = array(
            'wpseo' => $approved_profile['wpseo'],
            'wpseo_social' => $approved_profile['wpseo_social'],
        );
        global $wpdb;
        if (! $this->yoast_option_table_is_innodb()) {
            return array(
                'ok' => false,
                'state' => 'FAILED',
                'code' => 'YOAST_OPTION_TABLE_ENGINE_UNSUPPORTED',
            );
        }
        if ($wpdb->query('START TRANSACTION') === false) {
            return array('ok' => false, 'state' => 'FAILED', 'code' => 'YOAST_TRANSACTION_UNAVAILABLE');
        }
        try {
            $old_rows = $this->read_yoast_option_rows(true);
            if (is_wp_error($old_rows)) {
                return $this->rollback_yoast_transaction(
                    null,
                    'YOAST_OPTION_ROWS_INVALID'
                );
            }
            if (! hash_equals($before_state_hash, $this->yoast_rows_state_hash($old_rows))) {
                return $this->rollback_yoast_transaction(
                    $old_rows,
                    'YOAST_BEFORE_STATE_CHANGED'
                );
            }
            $new_values = array(
                'wpseo' => array_replace($old_rows['wpseo']['value'], $profile['wpseo']),
                'wpseo_social' => array_replace(
                    $old_rows['wpseo_social']['value'],
                    $profile['wpseo_social']
                ),
            );
            $expected_rows = $old_rows;
            foreach (array('wpseo', 'wpseo_social') as $option_name) {
                $new_raw = maybe_serialize($new_values[$option_name]);
                if (! is_string($new_raw)) {
                    return $this->rollback_yoast_transaction(
                        $old_rows,
                        'YOAST_SERIALIZATION_FAILED'
                    );
                }
                if ($new_raw !== $old_rows[$option_name]['raw']) {
                    $updated = $wpdb->query(
                        $wpdb->prepare(
                            "UPDATE {$wpdb->options} SET option_value = %s
                             WHERE BINARY option_name = BINARY %s
                               AND BINARY option_value = BINARY %s
                               AND BINARY autoload = BINARY %s",
                            $new_raw,
                            $option_name,
                            $old_rows[$option_name]['raw'],
                            $old_rows[$option_name]['autoload']
                        )
                    );
                    if ($updated !== 1) {
                        return $this->rollback_yoast_transaction(
                            $old_rows,
                            'YOAST_OPTION_CAS_FAILED'
                        );
                    }
                }
                $expected_rows[$option_name]['raw'] = $new_raw;
                $expected_rows[$option_name]['value'] = $new_values[$option_name];
            }
            $locked_readback = $this->read_yoast_option_rows(true);
            if (is_wp_error($locked_readback)
                || ! $this->yoast_rows_are_exact($locked_readback, $expected_rows)) {
                return $this->rollback_yoast_transaction(
                    $old_rows,
                    'YOAST_LOCKED_READBACK_FAILED'
                );
            }
            if ($wpdb->query('COMMIT') === false) {
                $wpdb->query('ROLLBACK');
                $this->flush_yoast_option_caches();
                return array(
                    'ok' => false,
                    'state' => 'NEEDS_RECOVERY',
                    'code' => 'YOAST_COMMIT_UNCERTAIN',
                );
            }
        } catch (Throwable $exception) {
            return $this->rollback_yoast_transaction(
                isset($old_rows) && is_array($old_rows) ? $old_rows : null,
                'YOAST_TRANSACTION_EXCEPTION'
            );
        }
        $this->flush_yoast_option_caches();
        $post_commit_rows = $this->read_yoast_option_rows(false);
        if (is_wp_error($post_commit_rows)
            || ! $this->yoast_rows_are_exact($post_commit_rows, $expected_rows)
            || ! $this->yoast_readback_matches(
                $profile,
                $old_rows['wpseo']['value'],
                $old_rows['wpseo_social']['value']
            )) {
            return array(
                'ok' => false,
                'state' => 'NEEDS_RECOVERY',
                'code' => 'YOAST_POST_COMMIT_DRIFT',
            );
        }
        return array('ok' => true, 'state' => 'APPLIED', 'code' => 'YOAST_PROFILE_APPLIED');
    }

    private function capture_yoast_before_state_hash()
    {
        global $wpdb;
        if (! $this->yoast_option_table_is_innodb()) {
            return self::error('raos_yoast_option_table_engine_unsupported', 409);
        }
        if ($wpdb->query('START TRANSACTION') === false) {
            return self::error('raos_yoast_transaction_unavailable', 500);
        }
        $rows = $this->read_yoast_option_rows(true);
        if (is_wp_error($rows)) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_yoast_options_invalid', 409);
        }
        $state_hash = $this->yoast_rows_state_hash($rows);
        if ($wpdb->query('COMMIT') === false) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_yoast_transaction_commit_failed', 500);
        }
        return $state_hash;
    }

    private function yoast_option_table_is_innodb()
    {
        global $wpdb;
        $rows = $wpdb->get_results(
            $wpdb->prepare(
                'SELECT ENGINE FROM information_schema.TABLES '
                . 'WHERE BINARY TABLE_SCHEMA = BINARY DATABASE() '
                . 'AND BINARY TABLE_NAME = BINARY %s',
                $wpdb->options
            ),
            ARRAY_A
        );
        return $wpdb->last_error === ''
            && is_array($rows)
            && count($rows) === 1
            && isset($rows[0]['ENGINE'])
            && $rows[0]['ENGINE'] === 'InnoDB';
    }

    private function read_yoast_option_rows($for_update)
    {
        global $wpdb;
        $sql = $wpdb->prepare(
            "SELECT option_name, option_value, autoload FROM {$wpdb->options}
             WHERE BINARY option_name = BINARY %s
                OR BINARY option_name = BINARY %s
             ORDER BY BINARY option_name ASC",
            'wpseo',
            'wpseo_social'
        );
        if ($for_update) {
            $sql .= ' FOR UPDATE';
        }
        $raw_rows = $wpdb->get_results($sql, ARRAY_A);
        if ($wpdb->last_error !== '' || ! is_array($raw_rows) || count($raw_rows) !== 2) {
            return self::error('raos_yoast_option_rows_invalid', 500);
        }
        $rows = array();
        foreach ($raw_rows as $row) {
            if (! isset($row['option_name'], $row['option_value'], $row['autoload'])
                || ! in_array($row['option_name'], array('wpseo', 'wpseo_social'), true)
                || isset($rows[$row['option_name']])
                || ! is_string($row['option_value'])
                || ! is_string($row['autoload'])) {
                return self::error('raos_yoast_option_rows_invalid', 500);
            }
            $value = maybe_unserialize($row['option_value']);
            if (! is_array($value)) {
                return self::error('raos_yoast_option_rows_invalid', 500);
            }
            $rows[$row['option_name']] = array(
                'raw' => $row['option_value'],
                'autoload' => $row['autoload'],
                'value' => $value,
            );
        }
        if (! isset($rows['wpseo'], $rows['wpseo_social'])) {
            return self::error('raos_yoast_option_rows_invalid', 500);
        }
        return $rows;
    }

    private function yoast_rows_state_hash(array $rows)
    {
        $material = '';
        foreach (array('wpseo', 'wpseo_social') as $option_name) {
            $material .= $option_name . "\n"
                . strlen($rows[$option_name]['raw']) . "\n"
                . $rows[$option_name]['raw'] . "\n"
                . strlen($rows[$option_name]['autoload']) . "\n"
                . $rows[$option_name]['autoload'] . "\n";
        }
        return hash('sha256', $material);
    }

    private function yoast_rows_are_exact(array $actual, array $expected)
    {
        foreach (array('wpseo', 'wpseo_social') as $option_name) {
            if (! isset($actual[$option_name], $expected[$option_name])
                || $actual[$option_name]['raw'] !== $expected[$option_name]['raw']
                || $actual[$option_name]['autoload'] !== $expected[$option_name]['autoload']
                || $actual[$option_name]['value'] !== $expected[$option_name]['value']) {
                return false;
            }
        }
        return true;
    }

    private function rollback_yoast_transaction($old_rows, $code)
    {
        global $wpdb;
        $rolled_back = $wpdb->query('ROLLBACK') !== false;
        $this->flush_yoast_option_caches();
        $actual = $this->read_yoast_option_rows(false);
        if ($rolled_back
            && is_array($old_rows)
            && ! is_wp_error($actual)
            && $this->yoast_rows_are_exact($actual, $old_rows)) {
            return array('ok' => false, 'state' => 'FAILED', 'code' => $code . '_ROLLED_BACK');
        }
        return array(
            'ok' => false,
            'state' => 'NEEDS_RECOVERY',
            'code' => 'YOAST_TRANSACTION_ROLLBACK_UNCERTAIN',
        );
    }

    private function flush_yoast_option_caches()
    {
        wp_cache_delete('alloptions', 'options');
        wp_cache_delete('notoptions', 'options');
        wp_cache_delete('wpseo', 'options');
        wp_cache_delete('wpseo_social', 'options');
    }

    private function derived_yoast_profile()
    {
        if (get_stylesheet() !== self::THEME_SLUG) {
            return self::error('raos_theme_not_active', 409);
        }
        $image_file = get_stylesheet_directory() . '/' . self::SOCIAL_IMAGE_PATH;
        if (! is_file($image_file)
            || is_link($image_file)
            || ! hash_equals(self::SOCIAL_IMAGE_SHA256, (string) hash_file('sha256', $image_file))) {
            return self::error('raos_social_image_invalid', 409);
        }
        $fixed = $this->fixed_yoast_profile_payload();
        $runtime_image_uri = trailingslashit(get_stylesheet_directory_uri())
            . self::SOCIAL_IMAGE_PATH;
        if (! hash_equals($fixed['wpseo_social']['og_default_image'], $runtime_image_uri)) {
            return self::error('raos_social_image_uri_invalid', 409);
        }
        return array(
            'wpseo' => $fixed['wpseo'],
            'wpseo_social' => $fixed['wpseo_social'],
        );
    }

    private function yoast_readback_matches(array $profile, $before_wpseo, $before_social)
    {
        $actual_wpseo = get_option('wpseo', null);
        $actual_social = get_option('wpseo_social', null);
        if (! is_array($actual_wpseo) || ! is_array($actual_social)) {
            return false;
        }
        foreach ($profile['wpseo'] as $key => $value) {
            if (! array_key_exists($key, $actual_wpseo) || $actual_wpseo[$key] !== $value) {
                return false;
            }
        }
        foreach ($profile['wpseo_social'] as $key => $value) {
            if (! array_key_exists($key, $actual_social) || $actual_social[$key] !== $value) {
                return false;
            }
        }
        if (is_array($before_wpseo) && is_array($before_social)) {
            $wpseo_profile_keys = array_fill_keys(array_keys($profile['wpseo']), true);
            $social_profile_keys = array_fill_keys(array_keys($profile['wpseo_social']), true);
            $before_wpseo_non_profile = array_diff_key($before_wpseo, $wpseo_profile_keys);
            $after_wpseo_non_profile = array_diff_key($actual_wpseo, $wpseo_profile_keys);
            $before_social_non_profile = array_diff_key($before_social, $social_profile_keys);
            $after_social_non_profile = array_diff_key($actual_social, $social_profile_keys);
            if ($before_wpseo_non_profile !== $after_wpseo_non_profile
                || $before_social_non_profile !== $after_social_non_profile) {
                return false;
            }
        }
        return true;
    }

    private function write_private_theme_stage($bytes, array $spec)
    {
        if (! is_string($bytes)
            || strlen($bytes) !== $spec['package_size']
            || ! hash_equals($spec['package_sha256'], hash('sha256', $bytes))) {
            return null;
        }
        $base = realpath(get_temp_dir());
        if (! is_string($base) || ! is_dir($base)) {
            return null;
        }
        try {
            $stage_suffix = bin2hex(random_bytes(24));
        } catch (Throwable $exception) {
            return null;
        }
        $directory = $base . DIRECTORY_SEPARATOR . 'raos-theme-stage-' . $stage_suffix;
        if (file_exists($directory) || ! @mkdir($directory, 0700)) {
            return null;
        }
        if (! @chmod($directory, 0700)) {
            @rmdir($directory);
            return null;
        }
        clearstatcache(true, $directory);
        $directory_stat = lstat($directory);
        if (! is_array($directory_stat)
            || (($directory_stat['mode'] & 0170000) !== 0040000)
            || (($directory_stat['mode'] & 0777) !== 0700)
            || realpath($directory) !== $directory) {
            @rmdir($directory);
            return null;
        }
        $path = $directory . DIRECTORY_SEPARATOR . 'package.zip';
        $handle = @fopen($path, 'x+b');
        if ($handle === false || ! flock($handle, LOCK_EX)) {
            if (is_resource($handle)) {
                fclose($handle);
            }
            $this->delete_private_theme_stage($directory, $path);
            return null;
        }
        $offset = 0;
        $length = strlen($bytes);
        $written = true;
        while ($offset < $length) {
            $chunk = fwrite($handle, substr($bytes, $offset));
            if (! is_int($chunk) || $chunk < 1) {
                $written = false;
                break;
            }
            $offset += $chunk;
        }
        $flushed = fflush($handle);
        $permissioned = chmod($path, 0600);
        $unlocked = flock($handle, LOCK_UN);
        $closed = fclose($handle);
        if (! $written
            || $offset !== $length
            || ! $flushed
            || ! $permissioned
            || ! $unlocked
            || ! $closed) {
            $this->delete_private_theme_stage($directory, $path);
            return null;
        }
        return array('directory' => $directory, 'path' => $path);
    }

    private function capture_staged_theme_package($directory, $path, array $spec)
    {
        if (! is_string($directory)
            || ! is_string($path)
            || dirname($path) !== $directory
            || basename($path) !== 'package.zip') {
            return null;
        }
        clearstatcache(true, $directory);
        clearstatcache(true, $path);
        $directory_stat = lstat($directory);
        $before = lstat($path);
        if (! is_array($directory_stat)
            || ! is_array($before)
            || (($directory_stat['mode'] & 0170000) !== 0040000)
            || (($directory_stat['mode'] & 0777) !== 0700)
            || (($before['mode'] & 0170000) !== 0100000)
            || (($before['mode'] & 0777) !== 0600)
            || (int) $before['nlink'] !== 1
            || (int) $before['size'] !== $spec['package_size']
            || is_link($directory)
            || is_link($path)
            || realpath($directory) !== $directory
            || realpath($path) !== $path) {
            return null;
        }
        $digest = hash_file('sha256', $path);
        clearstatcache(true, $path);
        $after = lstat($path);
        if (! is_string($digest)
            || ! hash_equals($spec['package_sha256'], $digest)
            || ! is_array($after)
            || (int) $after['dev'] !== (int) $before['dev']
            || (int) $after['ino'] !== (int) $before['ino']
            || (int) $after['mode'] !== (int) $before['mode']
            || (int) $after['nlink'] !== 1
            || (int) $after['size'] !== (int) $before['size']) {
            return null;
        }
        return array(
            'directory_dev' => (int) $directory_stat['dev'],
            'directory_ino' => (int) $directory_stat['ino'],
            'file_dev' => (int) $after['dev'],
            'file_ino' => (int) $after['ino'],
            'package_sha256' => $digest,
            'package_size' => (int) $after['size'],
        );
    }

    private function staged_theme_package_matches_capture(
        array $expected,
        $directory,
        $path,
        array $spec
    ) {
        $actual = $this->capture_staged_theme_package($directory, $path, $spec);
        return is_array($actual) && $actual === $expected;
    }

    private function theme_upgrader_hook_extra_is_exact(
        $hook_extra,
        $marker,
        array $backup
    ) {
        return is_array($hook_extra)
            && $this->has_exact_keys(
                $hook_extra,
                array(
                    'action',
                    'raos_operator_theme_apply_marker',
                    'temp_backup',
                    'type',
                )
            )
            && isset(
                $hook_extra['action'],
                $hook_extra['raos_operator_theme_apply_marker'],
                $hook_extra['temp_backup'],
                $hook_extra['type']
            )
            && $hook_extra['action'] === 'install'
            && $hook_extra['type'] === 'theme'
            && is_string($hook_extra['raos_operator_theme_apply_marker'])
            && hash_equals(
                $marker,
                $hook_extra['raos_operator_theme_apply_marker']
            )
            && is_array($hook_extra['temp_backup'])
            && $hook_extra['temp_backup'] === $backup;
    }

    private function capture_extracted_theme_source(
        $source,
        $remote_source,
        array $spec
    ) {
        if (! is_string($source)
            || ! is_string($remote_source)
            || $source === ''
            || $remote_source === ''
            || strpos($source, "\0") !== false
            || strpos($remote_source, "\0") !== false) {
            return null;
        }
        $source_path = rtrim($source, '/\\');
        $remote_path = rtrim($remote_source, '/\\');
        $source_real = realpath($source_path);
        $remote_real = realpath($remote_path);
        clearstatcache(true, $source_path);
        clearstatcache(true, $remote_path);
        $root_before = @lstat($source_path);
        $remote_before = @lstat($remote_path);
        if (! is_string($source_real)
            || ! is_string($remote_real)
            || $source_real !== $source_path
            || $remote_real !== $remote_path
            || dirname($source_real) !== $remote_real
            || basename($source_real) !== self::THEME_SLUG
            || ! is_array($root_before)
            || ! is_array($remote_before)
            || (($root_before['mode'] & 0170000) !== 0040000)
            || (($remote_before['mode'] & 0170000) !== 0040000)
            || is_link($source_path)
            || is_link($remote_path)) {
            return null;
        }

        $expected_files = array();
        $expected_directories = array();
        foreach ($spec['file_manifest'] as $entry) {
            $expected_files[$entry['path']] = $entry;
            $segments = explode('/', $entry['path']);
            array_pop($segments);
            $relative_directory = '';
            foreach ($segments as $segment) {
                $relative_directory = $relative_directory === ''
                    ? $segment
                    : $relative_directory . '/' . $segment;
                $expected_directories[$relative_directory] = true;
            }
        }

        $files = array();
        $directories = array();
        $identities = array();
        try {
            $iterator = new RecursiveIteratorIterator(
                new RecursiveDirectoryIterator(
                    $source_real,
                    FilesystemIterator::SKIP_DOTS
                ),
                RecursiveIteratorIterator::SELF_FIRST
            );
            foreach ($iterator as $file_info) {
                $absolute = $file_info->getPathname();
                $relative = substr($absolute, strlen($source_real) + 1);
                $relative = str_replace(DIRECTORY_SEPARATOR, '/', $relative);
                if (! is_string($relative)
                    || ! preg_match('/\A[A-Za-z0-9._\/-]+\z/', $relative)
                    || ! $this->safe_relative_path($relative)
                    || $file_info->isLink()) {
                    return null;
                }
                clearstatcache(true, $absolute);
                $before = @lstat($absolute);
                $real = realpath($absolute);
                if (! is_array($before)
                    || ! is_string($real)
                    || $real !== $absolute
                    || strpos($real, $source_real . DIRECTORY_SEPARATOR) !== 0) {
                    return null;
                }
                if ($file_info->isDir()) {
                    if (! isset($expected_directories[$relative])
                        || (($before['mode'] & 0170000) !== 0040000)) {
                        return null;
                    }
                    clearstatcache(true, $absolute);
                    $after = @lstat($absolute);
                    if (! is_array($after)
                        || (int) $after['dev'] !== (int) $before['dev']
                        || (int) $after['ino'] !== (int) $before['ino']
                        || (int) $after['mode'] !== (int) $before['mode']
                        || (int) $after['nlink'] !== (int) $before['nlink']) {
                        return null;
                    }
                    $directories[$relative] = true;
                    $identities['directory:' . $relative] = array(
                        'dev' => (int) $after['dev'],
                        'ino' => (int) $after['ino'],
                        'mode' => (int) $after['mode'],
                        'nlink' => (int) $after['nlink'],
                    );
                    continue;
                }
                if (! $file_info->isFile()
                    || ! isset($expected_files[$relative])
                    || (($before['mode'] & 0170000) !== 0100000)
                    || (int) $before['nlink'] !== 1
                    || (int) $before['size'] !== $expected_files[$relative]['size']) {
                    return null;
                }
                $digest = @hash_file('sha256', $absolute);
                clearstatcache(true, $absolute);
                $after = @lstat($absolute);
                if (! is_string($digest)
                    || ! hash_equals($expected_files[$relative]['sha256'], $digest)
                    || ! is_array($after)
                    || (int) $after['dev'] !== (int) $before['dev']
                    || (int) $after['ino'] !== (int) $before['ino']
                    || (int) $after['mode'] !== (int) $before['mode']
                    || (int) $after['nlink'] !== 1
                    || (int) $after['size'] !== (int) $before['size']) {
                    return null;
                }
                $files[] = array(
                    'path' => $relative,
                    'size' => (int) $after['size'],
                    'sha256' => $digest,
                );
                $identities['file:' . $relative] = array(
                    'dev' => (int) $after['dev'],
                    'ino' => (int) $after['ino'],
                    'mode' => (int) $after['mode'],
                    'nlink' => (int) $after['nlink'],
                    'size' => (int) $after['size'],
                );
            }
        } catch (Throwable $exception) {
            return null;
        }
        usort(
            $files,
            function ($left, $right) {
                return strcmp($left['path'], $right['path']);
            }
        );
        ksort($directories, SORT_STRING);
        ksort($expected_directories, SORT_STRING);
        ksort($identities, SORT_STRING);
        clearstatcache(true, $source_path);
        clearstatcache(true, $remote_path);
        $root_after = @lstat($source_path);
        $remote_after = @lstat($remote_path);
        if ($files !== $spec['file_manifest']
            || $directories !== $expected_directories
            || ! is_array($root_after)
            || ! is_array($remote_after)
            || (int) $root_after['dev'] !== (int) $root_before['dev']
            || (int) $root_after['ino'] !== (int) $root_before['ino']
            || (int) $root_after['mode'] !== (int) $root_before['mode']
            || (int) $root_after['nlink'] !== (int) $root_before['nlink']
            || (int) $remote_after['dev'] !== (int) $remote_before['dev']
            || (int) $remote_after['ino'] !== (int) $remote_before['ino']
            || (int) $remote_after['mode'] !== (int) $remote_before['mode']
            || (int) $remote_after['nlink'] !== (int) $remote_before['nlink']
            || realpath($source_path) !== $source_real
            || realpath($remote_path) !== $remote_real) {
            return null;
        }
        return array(
            'file_manifest' => $files,
            'identities' => $identities,
            'remote_dev' => (int) $remote_after['dev'],
            'remote_ino' => (int) $remote_after['ino'],
            'remote_mode' => (int) $remote_after['mode'],
            'remote_nlink' => (int) $remote_after['nlink'],
            'root_dev' => (int) $root_after['dev'],
            'root_ino' => (int) $root_after['ino'],
            'root_mode' => (int) $root_after['mode'],
            'root_nlink' => (int) $root_after['nlink'],
        );
    }

    private function theme_clear_destination_is_exact(
        $local_destination,
        $remote_destination,
        array $theme_root
    ) {
        if (! is_string($local_destination)
            || ! is_string($remote_destination)
            || ! $this->has_exact_keys(
                $theme_root,
                array('dev', 'ino', 'mode', 'path')
            )) {
            return false;
        }
        $local = rtrim($local_destination, '/\\');
        $remote = rtrim($remote_destination, '/\\');
        clearstatcache(true, $local);
        clearstatcache(true, $remote);
        $local_stat = @lstat($local);
        // Core moved the theme child to backup, so the parent nlink may change.
        return is_array($local_stat)
            && realpath($local) === $theme_root['path']
            && ! is_link($local)
            && (int) $local_stat['dev'] === $theme_root['dev']
            && (int) $local_stat['ino'] === $theme_root['ino']
            && (int) $local_stat['mode'] === $theme_root['mode']
            && $remote === $theme_root['path'] . DIRECTORY_SEPARATOR . self::THEME_SLUG
            && ! file_exists($remote)
            && ! is_link($remote);
    }

    private function delete_private_theme_stage($directory, $path)
    {
        if (! is_string($directory)
            || ! is_string($path)
            || dirname($path) !== $directory
            || basename($path) !== 'package.zip') {
            return false;
        }
        clearstatcache(true, $directory);
        clearstatcache(true, $path);
        $directory_stat = lstat($directory);
        if (! is_array($directory_stat)
            || (($directory_stat['mode'] & 0170000) !== 0040000)
            || is_link($directory)
            || realpath($directory) !== $directory) {
            return false;
        }
        if (file_exists($path) || is_link($path)) {
            $file_stat = lstat($path);
            if (! is_array($file_stat)
                || (($file_stat['mode'] & 0170000) !== 0100000)
                || (int) $file_stat['nlink'] !== 1
                || is_link($path)
                || realpath($path) !== $path
                || ! @unlink($path)) {
                return false;
            }
        }
        clearstatcache(true, $path);
        return ! file_exists($path)
            && ! is_link($path)
            && @rmdir($directory)
            && ! file_exists($directory);
    }

    private function apply_theme_package(array $spec, $bytes, $before_state_hash)
    {
        if (! is_string($bytes)
            || strlen($bytes) !== $spec['package_size']
            || strlen($bytes) > self::MAX_PACKAGE_BYTES
            || ! hash_equals($spec['package_sha256'], hash('sha256', $bytes))) {
            return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_PACKAGE_BINDING_MISMATCH');
        }
        $installed = wp_get_theme(self::THEME_SLUG);
        $immediate_state = $this->capture_theme_state();
        if (! $installed->exists()
            || $installed->get_stylesheet() !== self::THEME_SLUG
            || $installed->get('Version') !== $spec['from_version']
            || is_wp_error($immediate_state)
            || ! hash_equals($before_state_hash, $immediate_state['before_state_hash'])) {
            return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_SOURCE_VERSION_MISMATCH');
        }
        $old_state = $immediate_state;
        if (! class_exists('ZipArchive')) {
            return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_ZIP_UNAVAILABLE');
        }
        $stage = $this->write_private_theme_stage($bytes, $spec);
        unset($bytes);
        if (! is_array($stage)) {
            return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_TEMPORARY_UNAVAILABLE');
        }
        $staging_directory = $stage['directory'];
        $temporary = $stage['path'];
        $validation = $this->validate_theme_zip($temporary, $spec);
        if (! $validation['ok']) {
            $this->delete_private_theme_stage($staging_directory, $temporary);
            return $validation;
        }
        $stage_capture = $this->capture_staged_theme_package(
            $staging_directory,
            $temporary,
            $spec
        );
        if (! is_array($stage_capture)) {
            $this->delete_private_theme_stage($staging_directory, $temporary);
            return array(
                'ok' => false,
                'state' => 'FAILED',
                'code' => 'THEME_STAGED_PACKAGE_INVALID',
            );
        }

        require_once ABSPATH . 'wp-admin/includes/file.php';
        require_once ABSPATH . 'wp-admin/includes/class-wp-upgrader.php';
        global $wp_filesystem;
        if (get_filesystem_method() !== 'direct'
            || ! WP_Filesystem()
            || ! $wp_filesystem instanceof WP_Filesystem_Direct) {
            $this->delete_private_theme_stage($staging_directory, $temporary);
            return array(
                'ok' => false,
                'state' => 'FAILED',
                'code' => 'THEME_FILESYSTEM_METHOD_UNSUPPORTED',
            );
        }
        $theme_root_input = get_theme_root(self::THEME_SLUG);
        if (! is_string($theme_root_input) || $theme_root_input === '') {
            $this->delete_private_theme_stage($staging_directory, $temporary);
            return array(
                'ok' => false,
                'state' => 'FAILED',
                'code' => 'THEME_ROOT_INVALID',
            );
        }
        $theme_root_path = rtrim($theme_root_input, '/\\');
        $theme_root_real = realpath($theme_root_path);
        clearstatcache(true, $theme_root_path);
        $theme_root_stat = @lstat($theme_root_path);
        if (! is_string($theme_root_real)
            || $theme_root_real !== $theme_root_path
            || ! is_array($theme_root_stat)
            || (($theme_root_stat['mode'] & 0170000) !== 0040000)
            || is_link($theme_root_path)) {
            $this->delete_private_theme_stage($staging_directory, $temporary);
            return array(
                'ok' => false,
                'state' => 'FAILED',
                'code' => 'THEME_ROOT_INVALID',
            );
        }
        $theme_root_capture = array(
            'dev' => (int) $theme_root_stat['dev'],
            'ino' => (int) $theme_root_stat['ino'],
            'mode' => (int) $theme_root_stat['mode'],
            'path' => $theme_root_real,
        );
        if (! $this->theme_backup_is_absent()) {
            $this->delete_private_theme_stage($staging_directory, $temporary);
            return array(
                'ok' => false,
                'state' => 'NEEDS_RECOVERY',
                'code' => 'THEME_PREEXISTING_BACKUP_FORBIDDEN',
            );
        }
        $skin = new Automatic_Upgrader_Skin();
        $upgrader = new Theme_Upgrader($skin);
        $backup = array(
            'slug' => self::THEME_SLUG,
            'src' => $theme_root_real,
            'dir' => 'themes',
        );
        try {
            $apply_marker = bin2hex(random_bytes(32));
        } catch (Throwable $exception) {
            $this->delete_private_theme_stage($staging_directory, $temporary);
            return array(
                'ok' => false,
                'state' => 'FAILED',
                'code' => 'THEME_UPGRADER_GUARD_UNAVAILABLE',
            );
        }
        $backup_filter = function ($options) use ($backup, $apply_marker) {
            if (! is_array($options)
                || ! isset($options['hook_extra'])
                || ! is_array($options['hook_extra'])
                || ! $this->has_exact_keys(
                    $options['hook_extra'],
                    array('action', 'type')
                )
                || ! isset(
                    $options['hook_extra']['action'],
                    $options['hook_extra']['type']
                )
                || $options['hook_extra']['action'] !== 'install'
                || $options['hook_extra']['type'] !== 'theme') {
                return $options;
            }
            $options['hook_extra']['temp_backup'] = $backup;
            $options['hook_extra']['raos_operator_theme_apply_marker'] = $apply_marker;
            return $options;
        };
        if (! $this->staged_theme_package_matches_capture(
            $stage_capture,
            $staging_directory,
            $temporary,
            $spec
        )) {
            $this->delete_private_theme_stage($staging_directory, $temporary);
            return array(
                'ok' => false,
                'state' => 'FAILED',
                'code' => 'THEME_STAGED_PACKAGE_CHANGED',
            );
        }

        $source_selection_count = 0;
        $source_selection_rejected = false;
        $source_selection_verified = false;
        $selected_source = null;
        $selected_remote_source = null;
        $extracted_source_capture = null;
        $source_filter = function (
            $source,
            $remote_source,
            $filter_upgrader,
            $hook_extra
        ) use (
            &$source_selection_count,
            &$source_selection_rejected,
            &$source_selection_verified,
            &$selected_source,
            &$selected_remote_source,
            &$extracted_source_capture,
            $upgrader,
            $backup,
            $apply_marker,
            $stage_capture,
            $staging_directory,
            $temporary,
            $spec
        ) {
            ++$source_selection_count;
            if (is_wp_error($source)) {
                return $source;
            }
            if ($source_selection_count !== 1
                || $filter_upgrader !== $upgrader
                || ! $this->theme_upgrader_hook_extra_is_exact(
                    $hook_extra,
                    $apply_marker,
                    $backup
                )
                || ! $this->staged_theme_package_matches_capture(
                    $stage_capture,
                    $staging_directory,
                    $temporary,
                    $spec
                )) {
                $source_selection_rejected = true;
                return self::error('raos_theme_upgrader_source_context_invalid', 409);
            }
            $capture = $this->capture_extracted_theme_source(
                $source,
                $remote_source,
                $spec
            );
            if (! is_array($capture)) {
                $source_selection_rejected = true;
                return self::error('raos_theme_extracted_source_invalid', 409);
            }
            $selected_source = $source;
            $selected_remote_source = $remote_source;
            $extracted_source_capture = $capture;
            $source_selection_verified = true;
            return $source;
        };

        $clear_destination_count = 0;
        $clear_destination_rejected = false;
        $clear_destination_verified = false;
        $clear_filter = function (
            $removed,
            $local_destination,
            $remote_destination,
            $hook_extra
        ) use (
            &$clear_destination_count,
            &$clear_destination_rejected,
            &$clear_destination_verified,
            &$source_selection_verified,
            &$selected_source,
            &$selected_remote_source,
            &$extracted_source_capture,
            $backup,
            $apply_marker,
            $theme_root_capture,
            $spec
        ) {
            if (is_wp_error($removed)) {
                return $removed;
            }
            ++$clear_destination_count;
            if ($clear_destination_count !== 1
                || $removed !== true
                || ! $source_selection_verified
                || ! is_string($selected_source)
                || ! is_string($selected_remote_source)
                || ! is_array($extracted_source_capture)
                || ! $this->theme_upgrader_hook_extra_is_exact(
                    $hook_extra,
                    $apply_marker,
                    $backup
                )
                || ! $this->theme_clear_destination_is_exact(
                    $local_destination,
                    $remote_destination,
                    $theme_root_capture
                )) {
                $clear_destination_rejected = true;
                return self::error('raos_theme_upgrader_destination_context_invalid', 409);
            }
            $recaptured = $this->capture_extracted_theme_source(
                $selected_source,
                $selected_remote_source,
                $spec
            );
            if (! is_array($recaptured)
                || $recaptured !== $extracted_source_capture) {
                $clear_destination_rejected = true;
                return self::error('raos_theme_extracted_source_changed', 409);
            }
            $clear_destination_verified = true;
            return true;
        };

        add_filter('upgrader_package_options', $backup_filter, 999, 1);
        add_filter('upgrader_source_selection', $source_filter, PHP_INT_MAX, 4);
        add_filter('upgrader_clear_destination', $clear_filter, PHP_INT_MAX, 4);
        try {
            $upgrade_result = $upgrader->install(
                $temporary,
                array('overwrite_package' => true)
            );
        } catch (Throwable $exception) {
            $upgrade_result = false;
        } finally {
            remove_filter('upgrader_package_options', $backup_filter, 999);
            remove_filter('upgrader_source_selection', $source_filter, PHP_INT_MAX);
            remove_filter('upgrader_clear_destination', $clear_filter, PHP_INT_MAX);
        }
        $temporary_deleted = $this->delete_private_theme_stage(
            $staging_directory,
            $temporary
        );
        remove_action('shutdown', array($upgrader, 'restore_temp_backup'), 10);
        remove_action('shutdown', array($upgrader, 'delete_temp_backup'), 100);
        if ($source_selection_rejected) {
            return $this->theme_restore_result(
                $upgrader,
                $backup,
                $old_state,
                'THEME_EXTRACTED_SOURCE_REJECTED'
            );
        }
        if ($clear_destination_rejected) {
            return $this->theme_restore_result(
                $upgrader,
                $backup,
                $old_state,
                'THEME_EXTRACTED_SOURCE_CHANGED_ROLLED_BACK'
            );
        }
        if (is_wp_error($upgrade_result) || $upgrade_result !== true) {
            return $this->theme_restore_result(
                $upgrader,
                $backup,
                $old_state,
                'THEME_UPDATE_FAILED_ROLLED_BACK'
            );
        }
        if ($source_selection_count !== 1
            || ! $source_selection_verified
            || $clear_destination_count !== 1
            || ! $clear_destination_verified) {
            return $this->theme_restore_result(
                $upgrader,
                $backup,
                $old_state,
                'THEME_UPGRADER_GUARD_BYPASSED_ROLLED_BACK'
            );
        }
        if (! $temporary_deleted) {
            return $this->theme_restore_result(
                $upgrader,
                $backup,
                $old_state,
                'THEME_TEMPORARY_CLEANUP_FAILED_ROLLED_BACK'
            );
        }
        wp_clean_themes_cache(true);
        $readback = $this->verify_installed_theme($spec);
        if (! $readback) {
            return $this->theme_restore_result(
                $upgrader,
                $backup,
                $old_state,
                'THEME_READBACK_FAILED_ROLLED_BACK'
            );
        }
        if (! $this->theme_backup_matches($old_state)) {
            return array(
                'ok' => false,
                'state' => 'NEEDS_RECOVERY',
                'code' => 'THEME_BACKUP_NOT_VERIFIED_NEW_THEME_KEPT',
            );
        }
        $cleanup = $upgrader->delete_temp_backup(array($backup));
        if ($cleanup !== true) {
            wp_clean_themes_cache(true);
            return array(
                'ok' => false,
                'state' => 'NEEDS_RECOVERY',
                'code' => $this->verify_installed_theme($spec)
                    ? 'THEME_BACKUP_CLEANUP_FAILED_NEW_THEME_VERIFIED'
                    : 'THEME_BACKUP_CLEANUP_FAILED_STATE_UNCERTAIN',
            );
        }
        wp_clean_themes_cache(true);
        if (! $this->theme_backup_is_absent()
            || ! $this->verify_installed_theme($spec)) {
            return array(
                'ok' => false,
                'state' => 'NEEDS_RECOVERY',
                'code' => 'THEME_POST_CLEANUP_DRIFT',
            );
        }
        return array('ok' => true, 'state' => 'APPLIED', 'code' => 'THEME_UPDATE_APPLIED');
    }

    private function theme_restore_result($upgrader, array $backup, array $old_state, $restored_code)
    {
        if ($this->theme_state_matches($old_state)) {
            if ($this->theme_backup_is_absent()) {
                return array('ok' => false, 'state' => 'FAILED', 'code' => $restored_code);
            }
            if (! $this->theme_backup_matches($old_state)) {
                return array(
                    'ok' => false,
                    'state' => 'NEEDS_RECOVERY',
                    'code' => 'THEME_REDUNDANT_BACKUP_NOT_VERIFIED',
                );
            }
            $cleanup = $upgrader->delete_temp_backup(array($backup));
            wp_clean_themes_cache(true);
            if ($cleanup === true
                && $this->theme_backup_is_absent()
                && $this->theme_state_matches($old_state)) {
                return array('ok' => false, 'state' => 'FAILED', 'code' => $restored_code);
            }
            return array(
                'ok' => false,
                'state' => 'NEEDS_RECOVERY',
                'code' => 'THEME_REDUNDANT_BACKUP_CLEANUP_FAILED',
            );
        }
        if (! $this->theme_backup_matches($old_state)) {
            return array(
                'ok' => false,
                'state' => 'NEEDS_RECOVERY',
                'code' => 'THEME_BACKUP_NOT_VERIFIED',
            );
        }
        $restored = $upgrader->restore_temp_backup(array($backup));
        wp_clean_themes_cache(true);
        if ($restored === true && $this->theme_state_matches($old_state)) {
            return array('ok' => false, 'state' => 'FAILED', 'code' => $restored_code);
        }
        return array(
            'ok' => false,
            'state' => 'NEEDS_RECOVERY',
            'code' => 'THEME_RESTORE_FAILED',
        );
    }

    private function theme_state_matches(array $expected)
    {
        $actual = $this->capture_theme_state();
        return ! is_wp_error($actual)
            && $actual['active'] === $expected['active']
            && $actual['installed_version'] === $expected['installed_version']
            && $actual['tree_sha256'] === $expected['tree_sha256']
            && $actual['before_state_hash'] === $expected['before_state_hash']
            && $actual['file_manifest'] === $expected['file_manifest'];
    }

    private function theme_backup_root()
    {
        global $wp_filesystem;
        if (! $wp_filesystem instanceof WP_Filesystem_Direct) {
            return null;
        }
        $content_root = $wp_filesystem->wp_content_dir();
        if (! is_string($content_root) || $content_root === '') {
            return null;
        }
        return trailingslashit($content_root)
            . 'upgrade-temp-backup/themes/' . self::THEME_SLUG;
    }

    private function theme_backup_is_absent()
    {
        $root = $this->theme_backup_root();
        return is_string($root)
            && $this->theme_backup_path_has_no_symlinks($root)
            && ! file_exists($root)
            && ! is_link($root);
    }

    private function theme_backup_matches(array $old_state)
    {
        $root = $this->theme_backup_root();
        if (! is_string($root)) {
            return false;
        }
        if (! $this->theme_backup_path_has_no_symlinks($root)) {
            return false;
        }
        $state = $this->capture_theme_tree_at_root($root);
        return ! is_wp_error($state)
            && $state['installed_version'] === $old_state['installed_version']
            && $state['tree_sha256'] === $old_state['tree_sha256']
            && $state['file_manifest'] === $old_state['file_manifest'];
    }

    private function theme_backup_path_has_no_symlinks($root)
    {
        $content_root = dirname(dirname(dirname($root)));
        $paths = array(
            $content_root . '/upgrade-temp-backup',
            $content_root . '/upgrade-temp-backup/themes',
            $root,
        );
        foreach ($paths as $path) {
            if (is_link($path)) {
                return false;
            }
        }
        return true;
    }

    private function capture_theme_tree_at_root($root)
    {
        $real_root = realpath($root);
        if (! is_string($root)
            || ! is_string($real_root)
            || ! is_dir($real_root)
            || is_link($root)) {
            return self::error('raos_theme_backup_unreadable', 500);
        }
        $manifest = array();
        try {
            $iterator = new RecursiveIteratorIterator(
                new RecursiveDirectoryIterator($real_root, FilesystemIterator::SKIP_DOTS),
                RecursiveIteratorIterator::LEAVES_ONLY
            );
            foreach ($iterator as $file_info) {
                if ($file_info->isLink()
                    || ! $file_info->isFile()
                    || count($manifest) >= self::MAX_FILE_COUNT) {
                    return self::error('raos_theme_backup_unreadable', 500);
                }
                $absolute = $file_info->getPathname();
                $relative = substr($absolute, strlen($real_root) + 1);
                $relative = str_replace(DIRECTORY_SEPARATOR, '/', $relative);
                $size = $file_info->getSize();
                if (! is_string($relative)
                    || ! preg_match('/\A[A-Za-z0-9._\/-]+\z/', $relative)
                    || ! $this->safe_relative_path($relative)
                    || ! is_int($size)
                    || $size < 1
                    || $size > self::MAX_FILE_BYTES) {
                    return self::error('raos_theme_backup_unreadable', 500);
                }
                $digest = hash_file('sha256', $absolute);
                if (! is_string($digest)) {
                    return self::error('raos_theme_backup_unreadable', 500);
                }
                $manifest[] = array(
                    'path' => $relative,
                    'size' => $size,
                    'sha256' => $digest,
                );
            }
        } catch (UnexpectedValueException $exception) {
            return self::error('raos_theme_backup_unreadable', 500);
        }
        if (count($manifest) < 1) {
            return self::error('raos_theme_backup_unreadable', 500);
        }
        usort(
            $manifest,
            function ($left, $right) {
                return strcmp($left['path'], $right['path']);
            }
        );
        $tree_json = self::canonical_json($manifest);
        $style_path = $real_root . '/style.css';
        $style = is_file($style_path) && ! is_link($style_path)
            ? file_get_contents($style_path)
            : false;
        if (! is_string($tree_json)
            || ! is_string($style)
            || strlen($style) > 262144
            || ! preg_match(
                '/^[ \t*#@]*Version:\s*((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))\s*$/mi',
                $style,
                $version_match
            )) {
            return self::error('raos_theme_backup_unreadable', 500);
        }
        return array(
            'installed_version' => $version_match[1],
            'file_manifest' => $manifest,
            'tree_sha256' => hash('sha256', $tree_json),
        );
    }

    private function validate_theme_zip($zip_path, array $spec)
    {
        $zip = new ZipArchive();
        $opened = $zip->open($zip_path, ZipArchive::CHECKCONS);
        if ($opened !== true) {
            return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_ZIP_INVALID');
        }
        if ($zip->numFiles < 1 || $zip->numFiles > self::MAX_FILE_COUNT + 64) {
            $zip->close();
            return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_ZIP_ENTRY_COUNT_INVALID');
        }
        $files = array();
        $seen = array();
        $total = 0;
        $prefix = self::THEME_SLUG . '/';
        for ($index = 0; $index < $zip->numFiles; $index++) {
            $stat = $zip->statIndex($index, ZipArchive::FL_UNCHANGED);
            if (! is_array($stat)
                || ! isset($stat['name'], $stat['size'], $stat['comp_size'], $stat['comp_method'])) {
                $zip->close();
                return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_ZIP_ENTRY_INVALID');
            }
            $name = $stat['name'];
            if (! is_string($name)
                || strpos($name, $prefix) !== 0
                || ! preg_match('/\A[A-Za-z0-9._\/-]+\z/', $name)
                || ! $this->safe_relative_path(rtrim($name, '/'))
                || strlen($name) > 300) {
                $zip->close();
                return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_ZIP_PATH_INVALID');
            }
            $folded = strtolower($name);
            if (isset($seen[$folded])) {
                $zip->close();
                return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_ZIP_DUPLICATE_ENTRY');
            }
            $seen[$folded] = true;
            $attributes = 0;
            $operations = 0;
            if ($zip->getExternalAttributesIndex($index, $operations, $attributes)
                && (($attributes >> 16) & 0170000) === 0120000) {
                $zip->close();
                return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_ZIP_SYMLINK_FORBIDDEN');
            }
            $is_directory = substr($name, -1) === '/';
            if ($is_directory) {
                if ((int) $stat['size'] !== 0) {
                    $zip->close();
                    return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_ZIP_ENTRY_INVALID');
                }
                continue;
            }
            $size = (int) $stat['size'];
            $compressed = (int) $stat['comp_size'];
            if ($size < 0
                || $compressed < 0
                || (int) $stat['comp_method'] !== 0
                || $size > self::MAX_FILE_BYTES
                || ($compressed === 0 && $size > 0)
                || ($size > 1048576 && $size > ($compressed * 100))) {
                $zip->close();
                return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_ZIP_BOMB_REJECTED');
            }
            $total += $size;
            if ($total > self::MAX_UNCOMPRESSED_BYTES) {
                $zip->close();
                return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_ZIP_BOMB_REJECTED');
            }
            $relative = substr($name, strlen($prefix));
            if ($relative === '' || ! $this->safe_relative_path($relative)) {
                $zip->close();
                return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_ZIP_PATH_INVALID');
            }
            $content = $zip->getFromIndex($index);
            if (! is_string($content) || strlen($content) !== $size) {
                $zip->close();
                return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_ZIP_ENTRY_UNREADABLE');
            }
            $files[] = array(
                'path' => $relative,
                'size' => $size,
                'sha256' => hash('sha256', $content),
            );
        }
        if (count($files) < 1 || count($files) > self::MAX_FILE_COUNT) {
            $zip->close();
            return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_ZIP_ENTRY_COUNT_INVALID');
        }
        usort(
            $files,
            function ($left, $right) {
                return strcmp($left['path'], $right['path']);
            }
        );
        if ($files !== $spec['file_manifest']) {
            $zip->close();
            return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_MANIFEST_MISMATCH');
        }
        $style = $zip->getFromName($prefix . 'style.css');
        $zip->close();
        if (! is_string($style)
            || strlen($style) > 262144
            || ! preg_match('/^[ \t*#@]*Theme Name:\s*(\S.*)$/mi', $style, $name_match)
            || ! preg_match('/^[ \t*#@]*Template:\s*twentytwentyfive\s*$/mi', $style)
            || ! preg_match('/^[ \t*#@]*Version:\s*([^\s]+)\s*$/mi', $style, $version_match)
            || trim($name_match[1]) !== '暮らしのしるべ Child'
            || trim($version_match[1]) !== $spec['to_version']) {
            return array('ok' => false, 'state' => 'FAILED', 'code' => 'THEME_HEADERS_INVALID');
        }
        return array('ok' => true, 'state' => 'VALIDATED', 'code' => 'THEME_ZIP_VALIDATED');
    }

    private function verify_installed_theme(array $spec)
    {
        $theme = wp_get_theme(self::THEME_SLUG);
        if (! $theme->exists()
            || $theme->get_stylesheet() !== self::THEME_SLUG
            || get_stylesheet() !== self::THEME_SLUG
            || $theme->get('Version') !== $spec['to_version']) {
            return false;
        }
        $root = get_theme_root(self::THEME_SLUG) . '/' . self::THEME_SLUG;
        $real_root = realpath($root);
        if (! is_string($real_root) || is_link($root)) {
            return false;
        }
        foreach ($spec['file_manifest'] as $entry) {
            $candidate = $root . '/' . $entry['path'];
            $real = realpath($candidate);
            if (! is_string($real)
                || strpos($real, $real_root . DIRECTORY_SEPARATOR) !== 0
                || ! is_file($real)
                || is_link($candidate)
                || filesize($real) !== $entry['size']
                || ! hash_equals($entry['sha256'], (string) hash_file('sha256', $real))) {
                return false;
            }
        }
        $actual = array();
        try {
            $iterator = new RecursiveIteratorIterator(
                new RecursiveDirectoryIterator($root, FilesystemIterator::SKIP_DOTS),
                RecursiveIteratorIterator::LEAVES_ONLY
            );
            foreach ($iterator as $file_info) {
                if ($file_info->isLink() || ! $file_info->isFile()) {
                    return false;
                }
                $relative = substr($file_info->getPathname(), strlen($root) + 1);
                $actual[] = str_replace(DIRECTORY_SEPARATOR, '/', $relative);
            }
        } catch (UnexpectedValueException $exception) {
            return false;
        }
        sort($actual, SORT_STRING);
        $expected = wp_list_pluck($spec['file_manifest'], 'path');
        sort($expected, SORT_STRING);
        return $actual === $expected;
    }

    private function finish_success($proposal_id, $code)
    {
        global $wpdb;
        $table = self::proposal_table();
        if ($wpdb->query('START TRANSACTION') === false) {
            return self::error('raos_transaction_unavailable', 500);
        }
        $updated = $wpdb->query(
            $wpdb->prepare(
                "UPDATE {$table} SET state = %s, result_code = %s,
                 completed_at = %s, state_version = state_version + 1
                 WHERE proposal_id = %s AND state = %s",
                'APPLIED',
                $code,
                gmdate('Y-m-d H:i:s'),
                $proposal_id,
                'APPLYING'
            )
        );
        if ($updated !== 1) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_apply_state_unknown', 500);
        }
        $audit_hash = self::append_audit(
            'APPLY_SUCCEEDED',
            $proposal_id,
            $code,
            get_current_user_id()
        );
        if (! is_string($audit_hash)) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_audit_write_failed', 500);
        }
        if ($wpdb->query('COMMIT') === false) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_transaction_commit_failed', 500);
        }
        $row = $wpdb->get_row(
            $wpdb->prepare(
                "SELECT proposal_id, operation, state, idempotency_key, result_code
                 FROM {$table} WHERE proposal_id = %s LIMIT 1",
                $proposal_id
            ),
            ARRAY_A
        );
        return $this->apply_response($row, false);
    }

    private function finish_failure($proposal_id, $state, $code)
    {
        if (! in_array($state, array('FAILED', 'NEEDS_RECOVERY'), true)) {
            $state = 'NEEDS_RECOVERY';
            $code = 'APPLY_RESULT_INVALID';
        }
        global $wpdb;
        $table = self::proposal_table();
        if ($wpdb->query('START TRANSACTION') === false) {
            return self::error('raos_transaction_unavailable', 500);
        }
        $updated = $wpdb->query(
            $wpdb->prepare(
                "UPDATE {$table} SET state = %s, result_code = %s,
                 completed_at = %s, state_version = state_version + 1
                 WHERE proposal_id = %s AND state = %s",
                $state,
                $code,
                gmdate('Y-m-d H:i:s'),
                $proposal_id,
                'APPLYING'
            )
        );
        if ($updated !== 1) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_apply_state_unknown', 500);
        }
        $audit_hash = self::append_audit(
            'APPLY_FAILED',
            $proposal_id,
            $code,
            get_current_user_id()
        );
        if (! is_string($audit_hash)) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_audit_write_failed', 500);
        }
        if ($wpdb->query('COMMIT') === false) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_transaction_commit_failed', 500);
        }
        return self::error(
            $state === 'NEEDS_RECOVERY'
                ? 'raos_apply_needs_recovery'
                : 'raos_apply_failed',
            409
        );
    }

    private function apply_response(array $row, $replayed)
    {
        return new WP_REST_Response(
            array(
                'schema' => 'RAOS_OPERATOR_APPLY_V1',
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

    private static function append_audit($event_code, $proposal_id, $detail_code, $actor_user_id)
    {
        global $wpdb;
        $table = self::audit_table();
        $previous = $wpdb->get_var(
            "SELECT event_hash FROM {$table} ORDER BY audit_id DESC LIMIT 1 FOR UPDATE"
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
            || ! preg_match('/\A[a-f0-9]{64}\z/', $previous)) {
            return false;
        }
        $occurred = gmdate('Y-m-d H:i:s');
        $material = implode(
            "\n",
            array(
                $previous,
                $occurred,
                (string) (int) $actor_user_id,
                (string) $event_code,
                (string) $proposal_id,
                (string) $detail_code,
            )
        );
        $event_hash = hash('sha256', $material);
        $inserted = $wpdb->insert(
            $table,
            array(
                'occurred_at' => $occurred,
                'actor_user_id' => (int) $actor_user_id,
                'event_code' => substr((string) $event_code, 0, 64),
                'proposal_id' => $proposal_id,
                'detail_code' => substr((string) $detail_code, 0, 64),
                'previous_hash' => $previous,
                'event_hash' => $event_hash,
            ),
            array('%s', '%d', '%s', '%s', '%s', '%s', '%s')
        );
        return $inserted === 1 ? $event_hash : false;
    }

    private static function iso8601($mysql_utc)
    {
        $timestamp = strtotime($mysql_utc . ' UTC');
        return $timestamp === false ? '' : gmdate('Y-m-d\TH:i:s\Z', $timestamp);
    }
}

register_activation_hook(__FILE__, array('RAOS_Bounded_Operator', 'activate'));
RAOS_Bounded_Operator::instance();
