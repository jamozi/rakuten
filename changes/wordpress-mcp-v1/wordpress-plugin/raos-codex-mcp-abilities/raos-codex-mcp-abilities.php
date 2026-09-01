<?php
/**
 * Plugin Name: RAOS Codex MCP Abilities
 * Description: Browser-independent, approval-bound content and deployment abilities for kurashinoshirube.com.
 * Version: 1.3.1
 * Requires at least: 7.1
 * Requires PHP: 8.1
 * Author: RAOS
 * License: GPL-2.0-or-later
 * Update URI: false
 *
 * @package RAOS_Codex_MCP_Abilities
 */

defined('ABSPATH') || exit;

define('RAOS_CODEX_MCP_VERSION', '1.3.1');
define(
    'RAOS_CODEX_MCP_RUNTIME_REVISION',
    '82d3295080cb9723881773348e5366501af360b8b4301681ca9af82d22c7f368'
);
define('RAOS_CODEX_MCP_FILE', __FILE__);

require_once __DIR__ . '/includes/class-raos-codex-mcp-store.php';
require_once __DIR__ . '/includes/class-raos-codex-mcp-content.php';
require_once __DIR__ . '/includes/class-raos-codex-mcp-deployment.php';

final class RAOS_Codex_MCP_Abilities
{
    const RUNTIME_REVISION = '82d3295080cb9723881773348e5366501af360b8b4301681ca9af82d22c7f368';
    const ORIGIN = 'https://kurashinoshirube.com';
    const EDITOR_ROLE = 'raos_codex_mcp_editor';
    const OPERATOR_ROLE = 'raos_codex_deployment_operator';
    const EDITOR_BINDING = 'raos_codex_mcp_editor_bound_user_id_v1';
    const OPERATOR_BINDING = 'raos_codex_deployment_operator_bound_user_id_v1';
    const EDITOR_APP_NAME = 'RAOS Codex Editor MCP';
    const OPERATOR_APP_NAME = 'RAOS Codex Deployment Bridge';

    private static $instance = null;
    private static $application_password_user_id = 0;
    private static $application_password_role = null;

    private $content;
    private $deployment;

    public static function instance()
    {
        if (! self::$instance instanceof self) {
            self::$instance = new self();
        }
        return self::$instance;
    }

    private function __construct()
    {
        $this->content = new RAOS_Codex_MCP_Content($this);
        $this->deployment = new RAOS_Codex_MCP_Deployment($this);

        add_filter('mcp_adapter_create_default_server', '__return_false', PHP_INT_MAX);
        add_action('wp_abilities_api_categories_init', array($this, 'register_category'));
        add_action('wp_abilities_api_init', array($this, 'register_abilities'));
        add_action('mcp_adapter_init', array($this, 'register_mcp_server'));
        add_action('rest_api_init', array($this->deployment, 'register_routes'));
        add_action('init', array($this, 'maybe_upgrade'), 0);
        add_action(
            'wp_authenticate_application_password_errors',
            array($this, 'constrain_application_password'),
            10,
            4
        );
        add_filter(
            'rest_request_before_callbacks',
            array($this, 'guard_application_password_route'),
            10,
            3
        );
        add_action('admin_menu', array($this, 'register_admin_page'));
        add_action('admin_post_raos_codex_mcp_approve', array($this, 'handle_approval'));
        add_action('admin_post_raos_codex_mcp_approve_batch', array($this, 'handle_batch_approval'));
        add_action(
            'admin_post_raos_codex_mcp_attest_bootstrap',
            array($this, 'handle_bootstrap_attestation')
        );
        add_action('admin_notices', array($this, 'compatibility_notice'));
    }

    public static function activate()
    {
        global $wp_version;
        if (! self::runtime_identity_is_exact()
            || version_compare(PHP_VERSION, '8.1', '<')
            || ! is_string($wp_version)
            || preg_match('/\A7\.1(?:\.|\z)/', $wp_version) !== 1
            || (defined('WP_MCP_VERSION') && '0.6.1' !== WP_MCP_VERSION)) {
            deactivate_plugins(plugin_basename(__FILE__));
            wp_die(
                esc_html__('RAOS Codex MCP requires WordPress 7.1.x, PHP 8.1+, and MCP Adapter 0.6.1.', 'raos-codex-mcp'),
                esc_html__('RAOS Codex MCP activation refused', 'raos-codex-mcp'),
                array('back_link' => true)
            );
        }
        self::install_role(self::EDITOR_ROLE, self::editor_capabilities());
        self::install_role(self::OPERATOR_ROLE, self::operator_capabilities());
        RAOS_Codex_MCP_Store::install();
    }

    /**
     * Return the fixed plugin runtime identity only when every critical class
     * loaded in this PHP process belongs to this exact release.
     *
     * A tracked ZIP can replace files while OPcache still serves one older
     * class. Checking the disk package or entrypoint version alone therefore
     * cannot authorize a mutation.
     */
    public static function plugin_runtime_revision()
    {
        $expected = self::RUNTIME_REVISION;
        if (! defined('RAOS_CODEX_MCP_RUNTIME_REVISION')
            || ! is_string(RAOS_CODEX_MCP_RUNTIME_REVISION)
            || preg_match('/\A[0-9a-f]{64}\z/D', RAOS_CODEX_MCP_RUNTIME_REVISION) !== 1
            || ! hash_equals($expected, RAOS_CODEX_MCP_RUNTIME_REVISION)) {
            return null;
        }
        $critical_classes = array(
            __CLASS__,
            'RAOS_Codex_MCP_Store',
            'RAOS_Codex_MCP_Content',
            'RAOS_Codex_MCP_Deployment',
        );
        foreach ($critical_classes as $class_name) {
            $constant_name = $class_name . '::RUNTIME_REVISION';
            if (! class_exists($class_name, false)
                || ! defined($constant_name)) {
                return null;
            }
            $actual = constant($constant_name);
            if (! is_string($actual)
                || preg_match('/\A[0-9a-f]{64}\z/D', $actual) !== 1
                || ! hash_equals($expected, $actual)) {
                return null;
            }
        }
        return $expected;
    }

    public static function runtime_identity_is_exact()
    {
        return self::RUNTIME_REVISION === self::plugin_runtime_revision();
    }

    public static function runtime_identity_gate()
    {
        return self::runtime_identity_is_exact()
            ? true
            : new WP_Error(
                'raos_codex_plugin_runtime_mixed',
                'The loaded RAOS Codex plugin runtime is not one exact release.',
                array('status' => 503)
            );
    }

    /**
     * Guard the active-plugin overwrite upgrade path before Store code can run.
     */
    public function maybe_upgrade()
    {
        if (! self::runtime_identity_is_exact()) {
            return;
        }
        RAOS_Codex_MCP_Store::maybe_upgrade();
    }

    private static function install_role($name, $capabilities)
    {
        $role = get_role($name);
        if (! $role instanceof WP_Role) {
            add_role($name, $name, $capabilities);
            $role = get_role($name);
        }
        if (! $role instanceof WP_Role) {
            wp_die(esc_html__('RAOS Codex MCP role installation failed.', 'raos-codex-mcp'));
        }
        foreach (array_keys($role->capabilities) as $capability) {
            if (! array_key_exists($capability, $capabilities)) {
                $role->remove_cap($capability);
            }
        }
        foreach ($capabilities as $capability => $grant) {
            $role->add_cap($capability, true === $grant);
        }
    }

    private static function editor_capabilities()
    {
        return array(
            'read' => true,
            'raos_codex_mcp_access' => true,
            'raos_codex_content_read' => true,
            'raos_codex_content_write_draft' => true,
            'raos_codex_content_propose' => true,
        );
    }

    private static function operator_capabilities()
    {
        return array(
            'read' => true,
            'raos_codex_deploy_access' => true,
            'raos_codex_deploy_propose' => true,
            'raos_codex_deploy_apply' => true,
        );
    }

    public function register_category()
    {
        if (! self::runtime_compatible()) {
            return;
        }
        wp_register_ability_category(
            'raos-codex',
            array(
                'label' => __('RAOS Codex', 'raos-codex-mcp'),
                'description' => __('Approval-bound WordPress abilities for RAOS.', 'raos-codex-mcp'),
            )
        );
    }

    public function register_abilities()
    {
        if (self::runtime_compatible()) {
            $this->content->register_abilities();
        }
    }

    public function register_mcp_server($adapter)
    {
        if (! self::runtime_compatible()
            || ! is_object($adapter)
            || ! method_exists($adapter, 'create_server')) {
            return;
        }
        $adapter->create_server(
            'raos-codex-editor',
            'raos-codex-mcp/v1',
            'editor',
            'RAOS Codex WordPress Editor',
            'Draft editing, immutable release proposals, and aggregate-only measurement reads. No publish, delete, media-write, raw event, theme, plugin, PHP, SQL, or generic ability execution tool is exposed.',
            RAOS_CODEX_MCP_VERSION,
            array(\WP\MCP\Transport\HttpTransport::class),
            \WP\MCP\Infrastructure\ErrorHandling\NullMcpErrorHandler::class,
            \WP\MCP\Infrastructure\Observability\NullMcpObservabilityHandler::class,
            array(
                'raos-codex/site-status',
                'raos-codex/content-list',
                'raos-codex/content-get',
                'raos-codex/content-create-draft',
                'raos-codex/content-update-draft',
                'raos-codex/content-propose-release',
                'raos-codex/publication-batch-register',
                'raos-codex/operation-get',
                'raos-measurement/aggregate-report',
            ),
            array(),
            array(),
            array($this, 'transport_permission')
        );
    }

    public function constrain_application_password($error, $user, $item, $password)
    {
        unset($password);
        if (! $error instanceof WP_Error
            || ! $user instanceof WP_User
            || ! $user->exists()
            || ! is_array($item)) {
            return;
        }
        $role = null;
        $expected_name = null;
        $binding_name = null;
        if ($this->has_role_marker($user, self::EDITOR_ROLE)) {
            $role = self::EDITOR_ROLE;
            $expected_name = self::EDITOR_APP_NAME;
            $binding_name = self::EDITOR_BINDING;
        } elseif ($this->has_role_marker($user, self::OPERATOR_ROLE)) {
            $role = self::OPERATOR_ROLE;
            $expected_name = self::OPERATOR_APP_NAME;
            $binding_name = self::OPERATOR_BINDING;
        } else {
            return;
        }
        if (! self::runtime_identity_is_exact()
            || is_multisite()
            || ! self::runtime_origin_is_exact()
            || ! $this->has_exact_role_assignment($user, $role)
            || ! $this->role_is_exact($role)
            || ! $this->user_caps_are_exact($user, $role)
            || ! isset($item['name'])
            || ! is_string($item['name'])
            || ! hash_equals($expected_name, $item['name'])) {
            $error->add(
                'raos_codex_application_password_identity_invalid',
                'The RAOS Codex application-password identity is invalid.'
            );
            return;
        }
        $bound = get_option($binding_name, null);
        if (is_null($bound)) {
            add_option($binding_name, (string) $user->ID, '', false);
            $bound = get_option($binding_name, null);
        }
        if (! is_string($bound)
            || ! ctype_digit($bound)
            || (int) $bound !== (int) $user->ID) {
            $error->add(
                'raos_codex_application_password_binding_invalid',
                'The RAOS Codex application-password binding is invalid.'
            );
            return;
        }
        self::$application_password_user_id = (int) $user->ID;
        self::$application_password_role = $role;
        if ((defined('XMLRPC_REQUEST') && true === XMLRPC_REQUEST)
            || ! defined('REST_REQUEST')
            || true !== REST_REQUEST) {
            $error->add(
                'raos_codex_application_password_transport_forbidden',
                'The RAOS Codex credential is restricted to its REST transport.'
            );
        }
    }

    public function guard_application_password_route($response, $handler, $request)
    {
        if (0 === self::$application_password_user_id || ! is_string(self::$application_password_role)) {
            return $response;
        }
        $user = wp_get_current_user();
        if (! $user instanceof WP_User
            || (int) $user->ID !== self::$application_password_user_id
            || ! $request instanceof WP_REST_Request
            || ! is_array($handler)
            || ! isset($handler['callback'])
            || ! is_array($handler['callback'])
            || 2 !== count($handler['callback'])
            || ! self::runtime_origin_is_exact()) {
            return self::error('raos_codex_rest_scope_forbidden', 403);
        }
        $callback = $handler['callback'];
        if (self::EDITOR_ROLE === self::$application_password_role) {
            $allowed = '/raos-codex-mcp/v1/editor' === $request->get_route()
                && $callback[0] instanceof \WP\MCP\Transport\HttpTransport
                && 'handle_request' === $callback[1];
        } else {
            $allowed = $callback[0] === $this->deployment
                && $this->allowed_operator_handler($callback[1], $request);
        }
        return $allowed ? $response : self::error('raos_codex_rest_scope_forbidden', 403);
    }

    private function allowed_operator_handler($method, $request)
    {
        $route = $request->get_route();
        $http_method = strtoupper($request->get_method());
        if ('status' === $method) {
            return 'GET' === $http_method && '/raos-codex-deploy/v1/status' === $route;
        }
        if ('create_proposal' === $method) {
            return 'POST' === $http_method && '/raos-codex-deploy/v1/proposals' === $route;
        }
        if ('apply_proposal' === $method) {
            return 'POST' === $http_method
                && preg_match('#\A/raos-codex-deploy/v1/proposals/[0-9a-f]{64}/apply\z#D', $route) === 1;
        }
        if ('get_operation' === $method) {
            return 'GET' === $http_method
                && preg_match('#\A/raos-codex-deploy/v1/operations/[0-9a-f]{64}\z#D', $route) === 1;
        }
        if ('get_publication_batch' === $method) {
            return 'GET' === $http_method
                && preg_match('#\A/raos-codex-deploy/v1/publication-batches/[0-9a-f]{64}\z#D', $route) === 1;
        }
        if ('claim_publication_batch' === $method) {
            return 'POST' === $http_method
                && preg_match('#\A/raos-codex-deploy/v1/publication-batches/[0-9a-f]{64}/claim\z#D', $route) === 1;
        }
        if ('recover_operation' === $method) {
            return 'POST' === $http_method
                && preg_match('#\A/raos-codex-deploy/v1/operations/[0-9a-f]{64}/recover\z#D', $route) === 1;
        }
        return false;
    }

    public function transport_permission($request = null)
    {
        return $request instanceof WP_REST_Request
            && '/raos-codex-mcp/v1/editor' === $request->get_route()
            && self::runtime_identity_is_exact()
            && $this->authenticated_for_role(self::EDITOR_ROLE)
            && current_user_can('raos_codex_mcp_access');
    }

    public function ability_permission($input = null)
    {
        unset($input);
        return self::runtime_identity_is_exact()
            && $this->authenticated_for_role(self::EDITOR_ROLE)
            && current_user_can('raos_codex_content_read');
    }

    public function operator_rest_permission()
    {
        return self::runtime_identity_is_exact()
            && $this->authenticated_for_role(self::OPERATOR_ROLE)
            && current_user_can('raos_codex_deploy_access');
    }

    private function authenticated_for_role($role)
    {
        $user = wp_get_current_user();
        return self::$application_password_user_id > 0
            && self::runtime_identity_is_exact()
            && self::$application_password_role === $role
            && $user instanceof WP_User
            && (int) $user->ID === self::$application_password_user_id
            && $this->has_exact_role_assignment($user, $role)
            && $this->role_is_exact($role)
            && $this->user_caps_are_exact($user, $role)
            && self::runtime_origin_is_exact()
            && ! is_multisite();
    }

    private function has_role_marker($user, $role)
    {
        return $user instanceof WP_User
            && is_array($user->roles)
            && in_array($role, $user->roles, true);
    }

    private function has_exact_role_assignment($user, $role)
    {
        return $this->has_role_marker($user, $role)
            && 1 === count($user->roles)
            && $role === reset($user->roles)
            && ! in_array('administrator', $user->roles, true);
    }

    private function role_is_exact($role_name)
    {
        $role = get_role($role_name);
        if (! $role instanceof WP_Role) {
            return false;
        }
        $expected = self::EDITOR_ROLE === $role_name
            ? self::editor_capabilities()
            : self::operator_capabilities();
        ksort($expected, SORT_STRING);
        $actual = $role->capabilities;
        ksort($actual, SORT_STRING);
        return $actual === $expected;
    }

    private function user_caps_are_exact($user, $role)
    {
        return $user instanceof WP_User
            && is_array($user->caps)
            && array($role => true) === $user->caps;
    }

    public function register_admin_page()
    {
        add_management_page(
            __('RAOS Codex proposals', 'raos-codex-mcp'),
            __('RAOS Codex proposals', 'raos-codex-mcp'),
            'manage_options',
            'raos-codex-proposals',
            array($this, 'render_admin_page')
        );
    }

    private static function has_exact_keys($value, $expected)
    {
        if (! is_array($value) || ! is_array($expected)) {
            return false;
        }
        $actual = array_keys($value);
        sort($actual, SORT_STRING);
        sort($expected, SORT_STRING);
        return $actual === $expected;
    }

    private static function nullable_hash_matches($expected, $actual)
    {
        if (is_null($expected) || is_null($actual)) {
            return is_null($expected) && is_null($actual);
        }
        return RAOS_Codex_MCP_Store::is_sha256($expected)
            && RAOS_Codex_MCP_Store::is_sha256($actual)
            && hash_equals($expected, $actual);
    }

    private static function publication_batch_review_error($code)
    {
        return new WP_Error(
            $code,
            'The exact publication batch members could not be verified for human review.',
            array('status' => 409)
        );
    }

    /**
     * Load the exact rows named by a registered manifest. This deliberately does
     * not use the bounded recent-proposal list rendered elsewhere on the page.
     */
    private static function publication_batch_review($batch)
    {
        $manifest_keys = array(
            'schema',
            'expected_theme_tree_sha256',
            'proposal_count',
            'proposals',
        );
        $entry_keys = array(
            'proposal_id',
            'kind',
            'created_by',
            'created_at_gmt',
            'expires_at_gmt',
            'before_sha256',
            'after_sha256',
        );
        if (! is_array($batch)
            || ! isset(
                $batch['batch_token'],
                $batch['state'],
                $batch['created_by'],
                $batch['batch_manifest_sha256'],
                $batch['proposal_ids'],
                $batch['manifest']
            )
            || 'REGISTERED' !== $batch['state']
            || ! RAOS_Codex_MCP_Store::is_sha256($batch['batch_token'])
            || ! RAOS_Codex_MCP_Store::is_sha256($batch['batch_manifest_sha256'])
            || (int) $batch['created_by'] < 1
            || ! is_array($batch['proposal_ids'])
            || ! is_array($batch['manifest'])
            || ! self::has_exact_keys($batch['manifest'], $manifest_keys)) {
            return self::publication_batch_review_error('raos_codex_batch_review_manifest_invalid');
        }
        $manifest = $batch['manifest'];
        $proposal_ids = $batch['proposal_ids'];
        $manifest_hash = RAOS_Codex_MCP_Store::hash($manifest);
        if ('RAOSWordPressPublicationBatchManifestV1' !== $manifest['schema']
            || ! RAOS_Codex_MCP_Store::is_sha256($manifest['expected_theme_tree_sha256'])
            || ! is_int($manifest['proposal_count'])
            || ! is_array($manifest['proposals'])
            || empty($proposal_ids)
            || count($proposal_ids) > 20
            || $proposal_ids !== array_values($proposal_ids)
            || count(array_unique($proposal_ids)) !== count($proposal_ids)
            || count($proposal_ids) !== $manifest['proposal_count']
            || count($proposal_ids) !== count($manifest['proposals'])
            || $manifest['proposals'] !== array_values($manifest['proposals'])
            || ! RAOS_Codex_MCP_Store::is_sha256($manifest_hash)
            || ! hash_equals($batch['batch_manifest_sha256'], $manifest_hash)) {
            return self::publication_batch_review_error('raos_codex_batch_review_manifest_invalid');
        }
        $sorted_ids = $proposal_ids;
        sort($sorted_ids, SORT_STRING);
        if ($proposal_ids !== $sorted_ids) {
            return self::publication_batch_review_error('raos_codex_batch_review_manifest_invalid');
        }

        $rows = array();
        $seen_ids = array();
        $content_target_ids = array();
        $content_target_slugs = array();
        $content_count = 0;
        $theme_count = 0;
        foreach ($manifest['proposals'] as $index => $entry) {
            if (! self::has_exact_keys($entry, $entry_keys)
                || ! is_string($entry['proposal_id'])
                || ! isset($proposal_ids[$index])
                || ! is_string($proposal_ids[$index])
                || ! RAOS_Codex_MCP_Store::is_sha256($entry['proposal_id'])
                || ! hash_equals($proposal_ids[$index], $entry['proposal_id'])
                || isset($seen_ids[$entry['proposal_id']])
                || ! in_array($entry['kind'], array('CONTENT_RELEASE', 'THEME_RELEASE'), true)
                || ! is_int($entry['created_by'])
                || $entry['created_by'] < 1
                || ! is_string($entry['created_at_gmt'])
                || ! is_string($entry['expires_at_gmt'])
                || (! is_null($entry['before_sha256'])
                    && ! RAOS_Codex_MCP_Store::is_sha256($entry['before_sha256']))
                || (! is_null($entry['after_sha256'])
                    && ! RAOS_Codex_MCP_Store::is_sha256($entry['after_sha256']))) {
                return self::publication_batch_review_error('raos_codex_batch_review_manifest_invalid');
            }
            $proposal_id = $entry['proposal_id'];
            $seen_ids[$proposal_id] = true;
            $row = RAOS_Codex_MCP_Store::get($proposal_id);
            if (is_wp_error($row)) {
                return self::publication_batch_review_error('raos_codex_batch_review_member_unavailable');
            }
            $integrity = RAOS_Codex_MCP_Store::validate_proposal_integrity($row);
            $created_iso = isset($row['created_at_gmt']) && is_string($row['created_at_gmt'])
                ? RAOS_Codex_MCP_Store::timestamp_iso($row['created_at_gmt'])
                : null;
            $expires_iso = isset($row['expires_at_gmt']) && is_string($row['expires_at_gmt'])
                ? RAOS_Codex_MCP_Store::timestamp_iso($row['expires_at_gmt'])
                : null;
            if (true !== $integrity
                || ! is_array($row)
                || ! isset($row['proposal_id'], $row['kind'], $row['state'], $row['created_by'])
                || ! array_key_exists('before_sha256', $row)
                || ! array_key_exists('after_sha256', $row)
                || 'PENDING' !== $row['state']
                || ! is_string($row['proposal_id'])
                || ! hash_equals($proposal_id, $row['proposal_id'])
                || ! is_string($row['kind'])
                || ! hash_equals($entry['kind'], $row['kind'])
                || (int) $row['created_by'] !== $entry['created_by']
                || ! is_string($created_iso)
                || ! hash_equals($entry['created_at_gmt'], $created_iso)
                || ! is_string($expires_iso)
                || ! hash_equals($entry['expires_at_gmt'], $expires_iso)
                || ! self::nullable_hash_matches($entry['before_sha256'], $row['before_sha256'])
                || ! self::nullable_hash_matches($entry['after_sha256'], $row['after_sha256'])) {
                return self::publication_batch_review_error('raos_codex_batch_review_member_integrity_invalid');
            }

            if ('CONTENT_RELEASE' === $row['kind']) {
                $target = self::publication_batch_content_review_target(
                    $row,
                    $content_target_ids,
                    $content_target_slugs
                );
                ++$content_count;
                if ((int) $row['created_by'] !== (int) $batch['created_by']) {
                    return self::publication_batch_review_error('raos_codex_batch_review_owner_invalid');
                }
            } else {
                $target = self::publication_batch_theme_review_target(
                    $row,
                    $manifest['expected_theme_tree_sha256']
                );
                ++$theme_count;
                if ((int) $row['created_by'] === (int) $batch['created_by']) {
                    return self::publication_batch_review_error('raos_codex_batch_review_owner_invalid');
                }
            }
            if (true !== $target) {
                return $target instanceof WP_Error
                    ? $target
                    : self::publication_batch_review_error('raos_codex_batch_review_target_invalid');
            }
            $rows[] = $row;
        }
        if ($content_count < 1 || $theme_count > 1 || count($rows) !== count($proposal_ids)) {
            return self::publication_batch_review_error('raos_codex_batch_review_target_invalid');
        }
        return array('rows' => $rows);
    }

    private static function publication_batch_content_review_target(
        $row,
        &$content_target_ids,
        &$content_target_slugs
    ) {
        if (! isset($row['payload'])
            || ! is_array($row['payload'])
            || ! isset(
                $row['payload']['schema'],
                $row['payload']['target_status'],
                $row['payload']['before'],
                $row['payload']['after'],
                $row['payload']['before_sha256'],
                $row['payload']['after_sha256'],
                $row['payload']['publication_manifest_sha256']
            )
            || 'ContentReleaseProposalV1' !== $row['payload']['schema']
            || 'publish' !== $row['payload']['target_status']
            || ! is_array($row['payload']['before'])
            || ! is_array($row['payload']['after'])
            || ! RAOS_Codex_MCP_Store::is_sha256($row['before_sha256'])
            || ! RAOS_Codex_MCP_Store::is_sha256($row['after_sha256'])
            || ! RAOS_Codex_MCP_Store::is_sha256($row['payload']['before_sha256'])
            || ! RAOS_Codex_MCP_Store::is_sha256($row['payload']['after_sha256'])
            || ! RAOS_Codex_MCP_Store::is_sha256($row['payload']['publication_manifest_sha256'])
            || ! hash_equals($row['before_sha256'], $row['payload']['before_sha256'])
            || ! hash_equals($row['after_sha256'], $row['payload']['after_sha256'])) {
            return self::publication_batch_review_error('raos_codex_batch_review_content_target_invalid');
        }
        $before = $row['payload']['before'];
        $after = $row['payload']['after'];
        foreach (array('title', 'slug', 'excerpt', 'block_markup') as $field) {
            if (! isset($before[$field], $after[$field])
                || ! is_string($before[$field])
                || ! is_string($after[$field])) {
                return self::publication_batch_review_error('raos_codex_batch_review_content_target_invalid');
            }
        }
        if (! isset(
            $before['schema'],
            $before['post_type'],
            $before['id'],
            $before['status'],
            $before['content_sha256'],
            $after['schema'],
            $after['post_type'],
            $after['id'],
            $after['status'],
            $after['content_sha256']
        )
            || 'ContentDocumentV1' !== $before['schema']
            || 'ContentDocumentV1' !== $after['schema']
            || ! in_array($before['post_type'], array('post', 'page'), true)
            || ! is_string($after['post_type'])
            || ! hash_equals($before['post_type'], $after['post_type'])
            || ! is_int($before['id'])
            || ! is_int($after['id'])
            || $before['id'] < 1
            || $before['id'] !== $after['id']
            || ! in_array($before['status'], array('draft', 'publish'), true)
            || 'publish' !== $after['status']
            || ! RAOS_Codex_MCP_Store::is_sha256($before['content_sha256'])
            || ! RAOS_Codex_MCP_Store::is_sha256($after['content_sha256'])
            || ! hash_equals($row['before_sha256'], $before['content_sha256'])
            || ! hash_equals($row['after_sha256'], $after['content_sha256'])) {
            return self::publication_batch_review_error('raos_codex_batch_review_content_target_invalid');
        }
        $target_id = (string) $after['id'];
        $target_slug = strtolower(trim($after['slug']));
        if ('' === $target_slug
            || isset($content_target_ids[$target_id])
            || isset($content_target_slugs[$target_slug])) {
            return self::publication_batch_review_error('raos_codex_batch_review_content_target_conflict');
        }
        $content_target_ids[$target_id] = true;
        $content_target_slugs[$target_slug] = true;
        return true;
    }

    private static function publication_batch_theme_review_target($row, $expected_theme_tree_sha256)
    {
        $descriptor_keys = array(
            'schema',
            'kind',
            'source',
            'artifact_id',
            'git_commit',
            'slug',
            'old_version',
            'new_version',
            'package_sha256',
            'file_manifest_sha256',
            'file_manifest',
            'activation_intent',
            'migration_assessment',
            'automatic_apply_eligible',
        );
        if (! isset($row['payload'])
            || ! is_array($row['payload'])
            || ! isset(
                $row['payload']['schema'],
                $row['payload']['kind'],
                $row['payload']['code_package'],
                $row['payload']['before_tree_sha256'],
                $row['payload']['after_tree_sha256']
            )
            || 'CodeReleaseProposalV1' !== $row['payload']['schema']
            || 'THEME_RELEASE' !== $row['payload']['kind']
            || ! is_array($row['payload']['code_package'])
            || ! self::has_exact_keys($row['payload']['code_package'], $descriptor_keys)
            || ! RAOS_Codex_MCP_Store::is_sha256($row['before_sha256'])
            || ! RAOS_Codex_MCP_Store::is_sha256($row['after_sha256'])
            || ! RAOS_Codex_MCP_Store::is_sha256($row['payload']['before_tree_sha256'])
            || ! RAOS_Codex_MCP_Store::is_sha256($row['payload']['after_tree_sha256'])
            || ! hash_equals($row['before_sha256'], $row['payload']['before_tree_sha256'])
            || ! hash_equals($row['after_sha256'], $row['payload']['after_tree_sha256'])) {
            return self::publication_batch_review_error('raos_codex_batch_review_theme_target_invalid');
        }
        $descriptor = $row['payload']['code_package'];
        $file_manifest_json = RAOS_Codex_MCP_Store::canonical_json($descriptor['file_manifest']);
        if ('CodePackageV1' !== $descriptor['schema']
            || 'theme' !== $descriptor['kind']
            || 'tracked_child_theme' !== $descriptor['source']
            || RAOS_Codex_MCP_Deployment::THEME_SLUG !== $descriptor['slug']
            || ! is_null($descriptor['artifact_id'])
            || ! is_string($descriptor['git_commit'])
            || preg_match('/\A[0-9a-f]{40}\z/D', $descriptor['git_commit']) !== 1
            || (! is_null($descriptor['old_version']) && ! is_string($descriptor['old_version']))
            || ! is_string($descriptor['new_version'])
            || ! RAOS_Codex_MCP_Store::is_sha256($descriptor['package_sha256'])
            || ! RAOS_Codex_MCP_Store::is_sha256($descriptor['file_manifest_sha256'])
            || ! is_array($descriptor['file_manifest'])
            || empty($descriptor['file_manifest'])
            || 'preserve' !== $descriptor['activation_intent']
            || 'NO_IRREVERSIBLE_MIGRATION_SIGNALS' !== $descriptor['migration_assessment']
            || true !== $descriptor['automatic_apply_eligible']
            || ! is_string($file_manifest_json)
            || ! hash_equals($descriptor['file_manifest_sha256'], hash('sha256', $file_manifest_json))
            || ! hash_equals($row['after_sha256'], $descriptor['file_manifest_sha256'])
            || ! hash_equals($expected_theme_tree_sha256, $descriptor['file_manifest_sha256'])) {
            return self::publication_batch_review_error('raos_codex_batch_review_theme_target_invalid');
        }
        return true;
    }

    private static function render_publication_batch_member($row, $position, $count)
    {
        $heading_id = 'raos-batch-member-' . substr($row['proposal_id'], -12);
        echo '<article aria-labelledby="' . esc_attr($heading_id) . '" style="margin:1.5rem 0;padding:1rem;border:1px solid #c3c4c7">';
        echo '<h3 id="' . esc_attr($heading_id) . '">'
            . esc_html(sprintf(__('Batch member %1$d of %2$d: %3$s', 'raos-codex-mcp'), $position, $count, $row['kind']))
            . '</h3>';
        echo '<p><strong>' . esc_html__('Proposal ID:', 'raos-codex-mcp') . '</strong> <code>'
            . esc_html($row['proposal_id']) . '</code><br><strong>'
            . esc_html__('Before SHA-256:', 'raos-codex-mcp') . '</strong> <code>'
            . esc_html($row['before_sha256']) . '</code><br><strong>'
            . esc_html__('After SHA-256:', 'raos-codex-mcp') . '</strong> <code>'
            . esc_html($row['after_sha256']) . '</code></p>';
        if ('CONTENT_RELEASE' === $row['kind']) {
            self::render_publication_batch_content_member($row['payload']);
        } else {
            self::render_publication_batch_theme_member($row['payload']);
        }
        $payload = wp_json_encode(
            $row['payload'],
            JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE
        );
        echo '<details><summary>'
            . esc_html__('Complete immutable member payload (all fields)', 'raos-codex-mcp')
            . '</summary><pre style="white-space:pre-wrap;max-height:40rem;overflow:auto">'
            . esc_html((string) $payload) . '</pre></details>';
        echo '</article>';
    }

    private static function render_publication_batch_content_member($payload)
    {
        $before = $payload['before'];
        $after = $payload['after'];
        echo '<p><strong>' . esc_html__('Exact content target:', 'raos-codex-mcp') . '</strong> '
            . esc_html($after['post_type'] . ' #' . $after['id'] . ' / publish') . '</p>';
        echo '<table class="widefat striped" style="margin-bottom:1rem"><thead><tr><th>'
            . esc_html__('Field', 'raos-codex-mcp') . '</th><th>'
            . esc_html__('Before', 'raos-codex-mcp') . '</th><th>'
            . esc_html__('After', 'raos-codex-mcp') . '</th></tr></thead><tbody>';
        $fields = array(
            'title' => __('Title', 'raos-codex-mcp'),
            'slug' => __('Slug', 'raos-codex-mcp'),
            'excerpt' => __('Excerpt', 'raos-codex-mcp'),
        );
        foreach ($fields as $field => $label) {
            echo '<tr><th scope="row">' . esc_html($label) . '</th><td><pre style="white-space:pre-wrap">'
                . esc_html($before[$field]) . '</pre></td><td><pre style="white-space:pre-wrap">'
                . esc_html($after[$field]) . '</pre></td></tr>';
        }
        echo '</tbody></table>';
        echo '<h4>' . esc_html__('Before block markup', 'raos-codex-mcp') . '</h4><pre style="white-space:pre-wrap;max-height:40rem;overflow:auto">'
            . esc_html($before['block_markup']) . '</pre>';
        echo '<h4>' . esc_html__('After block markup', 'raos-codex-mcp') . '</h4><pre style="white-space:pre-wrap;max-height:40rem;overflow:auto">'
            . esc_html($after['block_markup']) . '</pre>';
    }

    private static function render_publication_batch_theme_member($payload)
    {
        $descriptor = $payload['code_package'];
        echo '<p><strong>' . esc_html__('Exact theme target:', 'raos-codex-mcp') . '</strong> <code>'
            . esc_html($descriptor['slug']) . '</code></p>';
        echo '<table class="widefat striped" style="margin-bottom:1rem"><tbody>';
        $metadata = array(
            'source' => __('Source', 'raos-codex-mcp'),
            'artifact_id' => __('Artifact ID', 'raos-codex-mcp'),
            'git_commit' => __('Git commit', 'raos-codex-mcp'),
            'slug' => __('Theme slug', 'raos-codex-mcp'),
            'old_version' => __('Old version', 'raos-codex-mcp'),
            'new_version' => __('New version', 'raos-codex-mcp'),
            'package_sha256' => __('Package SHA-256', 'raos-codex-mcp'),
            'file_manifest_sha256' => __('File manifest SHA-256', 'raos-codex-mcp'),
            'activation_intent' => __('Activation intent', 'raos-codex-mcp'),
            'migration_assessment' => __('Migration assessment', 'raos-codex-mcp'),
            'automatic_apply_eligible' => __('Automatic apply eligible', 'raos-codex-mcp'),
        );
        foreach ($metadata as $key => $label) {
            $value = wp_json_encode($descriptor[$key], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
            echo '<tr><th scope="row">' . esc_html($label) . '</th><td><code>'
                . esc_html((string) $value) . '</code></td></tr>';
        }
        echo '</tbody></table>';
        $file_manifest = wp_json_encode(
            $descriptor['file_manifest'],
            JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE
        );
        echo '<h4>' . esc_html__('Complete theme file manifest', 'raos-codex-mcp')
            . '</h4><pre style="white-space:pre-wrap;max-height:40rem;overflow:auto">'
            . esc_html((string) $file_manifest) . '</pre>';
    }

    public function render_admin_page()
    {
        if (! current_user_can('manage_options')) {
            wp_die(esc_html__('Permission denied.', 'raos-codex-mcp'));
        }
        if (! self::runtime_identity_is_exact()) {
            wp_die(
                esc_html__('Approval unavailable while the plugin runtime is mixed.', 'raos-codex-mcp'),
                '',
                array('response' => 503)
            );
        }
        $rows = RAOS_Codex_MCP_Store::pending_for_admin(50);
        $batches = RAOS_Codex_MCP_Store::pending_publication_batches_for_admin(20);
        echo '<div class="wrap"><h1>' . esc_html__('RAOS Codex proposals', 'raos-codex-mcp') . '</h1>';
        echo '<p>' . esc_html__('Review the complete before/after hashes and payload. Approval issues one proposal-bound, single-use authorization; it never applies the change. The bounded operator must still pass If-Match, idempotency, TTL, the global kill switch, drift, backup, and readback checks.', 'raos-codex-mcp') . '</p>';
        if (isset($_GET['approved']) && '1' === sanitize_text_field(wp_unslash($_GET['approved']))) {
            echo '<div class="notice notice-success inline"><p><strong>'
                . esc_html__('Approval completed.', 'raos-codex-mcp')
                . '</strong> '
                . esc_html__('State: APPROVED. The proposal is authorized for one bounded apply; it has not been applied by this form.', 'raos-codex-mcp')
                . '</p></div>';
        }
        if (isset($_GET['batch_approved'])) {
            $approved_count = absint(wp_unslash($_GET['batch_approved']));
            if ($approved_count > 0) {
                echo '<div class="notice notice-success inline"><p><strong>'
                    . esc_html(sprintf(__('Batch approval completed for %d proposals.', 'raos-codex-mcp'), $approved_count))
                    . '</strong> '
                    . esc_html__('State: APPROVED. Each proposal now has one proposal-bound lease; no change was applied by this form.', 'raos-codex-mcp')
                    . '</p></div>';
            }
        }
        if (isset($_GET['bootstrap_attested'])
            && '1' === sanitize_text_field(wp_unslash($_GET['bootstrap_attested']))) {
            echo '<div class="notice notice-success inline"><p><strong>'
                . esc_html__('Manual bootstrap attestation recorded.', 'raos-codex-mcp')
                . '</strong> '
                . esc_html__('The exact abilities 1.3.1 package was already installed manually by a human administrator. This form only recorded its proposal-bound readback receipt; it did not install or apply code.', 'raos-codex-mcp')
                . '</p></div>';
        }
        if (empty($rows) && empty($batches)) {
            echo '<p>' . esc_html__('No pending proposals.', 'raos-codex-mcp') . '</p></div>';
            return;
        }
        foreach ($batches as $batch) {
            $review = self::publication_batch_review($batch);
            $batch_hash = $batch['batch_manifest_sha256'];
            $batch_token = $batch['batch_token'];
            $batch_suffix = substr($batch_hash, -8);
            $batch_manifest = wp_json_encode(
                $batch['manifest'],
                JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE
            );
            $self_created = false;
            if (! is_wp_error($review)) {
                foreach ($review['rows'] as $review_row) {
                    if ((int) $review_row['created_by'] === get_current_user_id()) {
                        $self_created = true;
                        break;
                    }
                }
            }
            $heading_id = 'raos-batch-' . substr($batch_token, -12);
            echo '<hr><section aria-labelledby="' . esc_attr($heading_id) . '"><h2 id="' . esc_attr($heading_id) . '">'
                . esc_html__('Approve this requested publication batch', 'raos-codex-mcp')
                . '</h2>';
            echo '<p><strong>'
                . esc_html(sprintf(__('%d exact content/theme proposals / server state: REGISTERED', 'raos-codex-mcp'), count($batch['proposal_ids'])))
                . '</strong></p>';
            echo '<p>' . esc_html__('This server-side request is bound only to the complete proposal IDs and hashes shown below. Other pending proposals, including every plugin proposal, are not part of this approval.', 'raos-codex-mcp') . '</p>';
            echo '<p>' . esc_html__('Server batch token:', 'raos-codex-mcp') . ' <code>' . esc_html($batch_token) . '</code></p>';
            echo '<p>' . esc_html__('Batch manifest SHA-256:', 'raos-codex-mcp')
                . ' <code>' . esc_html($batch_hash) . '</code><br><strong>'
                . esc_html__('Enter this visible final 8-character batch suffix:', 'raos-codex-mcp')
                . ' <code style="font-size:1.15em">' . esc_html($batch_suffix) . '</code></strong></p>';
            echo '<details><summary>' . esc_html__('Complete canonical batch manifest (full IDs and hashes)', 'raos-codex-mcp')
                . '</summary><pre style="white-space:pre-wrap;max-height:40rem;overflow:auto">'
                . esc_html((string) $batch_manifest) . '</pre></details>';
            if (is_wp_error($review)) {
                echo '<div class="notice notice-error inline"><p><strong>'
                    . esc_html__('Approval disabled: the exact batch member review could not be verified.', 'raos-codex-mcp')
                    . '</strong> '
                    . esc_html__('At least one member is missing, duplicated, no longer pending, or inconsistent with the registered manifest. Do not approve this batch; create a new exact publication request after resolving the mismatch.', 'raos-codex-mcp')
                    . ' <code>' . esc_html($review->get_error_code()) . '</code></p></div>';
            } else {
                echo '<h3>' . esc_html__('Exact batch members for human review', 'raos-codex-mcp') . '</h3>';
                foreach ($review['rows'] as $index => $review_row) {
                    self::render_publication_batch_member(
                        $review_row,
                        $index + 1,
                        count($review['rows'])
                    );
                }
            }
            if (! is_wp_error($review)) {
                if ($self_created) {
                    echo '<p><strong>'
                        . esc_html__('This administrator created at least one proposal in the batch. A different administrator must approve the complete batch.', 'raos-codex-mcp')
                        . '</strong></p>';
                } else {
                    echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
                    echo '<input type="hidden" name="action" value="raos_codex_mcp_approve_batch">';
                    echo '<input type="hidden" name="batch_token" value="' . esc_attr($batch_token) . '">';
                    echo '<input type="hidden" name="batch_manifest_sha256" value="' . esc_attr($batch_hash) . '">';
                    wp_nonce_field('raos_codex_mcp_approve_batch_' . $batch_token . '_' . $batch_hash);
                    echo '<p><label>' . esc_html__('Current password (one reauthentication for the complete batch)', 'raos-codex-mcp') . '<br><input type="password" name="current_password" autocomplete="current-password" required></label></p>';
                    echo '<p><label>' . esc_html__('Approval reason for the complete batch (10+ characters)', 'raos-codex-mcp') . '<br><textarea name="reason" rows="3" cols="80" minlength="10" maxlength="2000" required></textarea></label></p>';
                    echo '<p><label>' . esc_html__('Type the visible final 8 characters of the batch manifest hash', 'raos-codex-mcp') . '<br><input type="text" name="hash_suffix" minlength="8" maxlength="8" pattern="[0-9a-f]{8}" required> <code>' . esc_html($batch_suffix) . '</code></label></p>';
                    submit_button(__('Approve complete batch', 'raos-codex-mcp'), 'primary', 'submit', false);
                    echo '</form>';
                }
            }
            echo '</section>';
        }
        foreach ($rows as $row) {
            $payload = wp_json_encode($row['payload'], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
            echo '<hr><h2><code>' . esc_html($row['proposal_id']) . '</code></h2>';
            echo '<p>' . esc_html($row['kind'] . ' / ' . $row['state'] . ' / expires ' . $row['expires_at_gmt'] . ' GMT') . '</p>';
            $after_suffix = is_string($row['after_sha256']) ? substr($row['after_sha256'], -8) : '';
            echo '<p>before: <code>' . esc_html((string) $row['before_sha256']) . '</code><br>after: <code>' . esc_html((string) $row['after_sha256']) . '</code>';
            if ('' !== $after_suffix) {
                echo '<br><strong>' . esc_html__('Visible after-hash suffix to enter:', 'raos-codex-mcp') . ' <code>' . esc_html($after_suffix) . '</code></strong>';
            }
            echo '</p>';
            echo '<details><summary>' . esc_html__('Complete immutable payload', 'raos-codex-mcp') . '</summary><pre style="white-space:pre-wrap;max-height:40rem;overflow:auto">' . esc_html((string) $payload) . '</pre></details>';
            if ('MANUAL_REQUIRED' === $row['state']) {
                $bootstrap = RAOS_Codex_MCP_Deployment::validate_manual_bootstrap_attestation($row);
                if (is_wp_error($bootstrap)) {
                    echo '<p><strong>' . esc_html__('Automatic approval/apply is unavailable because migration safety could not be established.', 'raos-codex-mcp') . '</strong> <code>'
                        . esc_html($bootstrap->get_error_code()) . '</code></p>';
                    continue;
                }
                if ((int) $row['created_by'] === get_current_user_id()) {
                    echo '<p><strong>'
                        . esc_html__('The proposal creator cannot attest the manual bootstrap. A different human administrator must perform the exact installation and attestation.', 'raos-codex-mcp')
                        . '</strong></p>';
                    continue;
                }
                $package_suffix = substr($bootstrap['package_sha256'], -8);
                $proposal_suffix = substr($bootstrap['proposal_id'], -8);
                echo '<div class="notice notice-warning inline"><p><strong>'
                    . esc_html__('Narrow manual-bootstrap receipt only.', 'raos-codex-mcp')
                    . '</strong> '
                    . esc_html__('The installed and active abilities 1.3.1 tree, staged package, complete file manifest, host artifact pin, and immutable proposal currently match exactly. Confirm only if you personally installed that exact package in wp-admin. This does not create a reusable migration exception.', 'raos-codex-mcp')
                    . '</p></div>';
                echo '<table class="widefat striped" style="margin-bottom:1rem"><tbody>';
                foreach (
                    array(
                        'proposal_id' => __('Proposal ID', 'raos-codex-mcp'),
                        'artifact_id' => __('Artifact ID', 'raos-codex-mcp'),
                        'slug' => __('Plugin slug', 'raos-codex-mcp'),
                        'version' => __('Installed version', 'raos-codex-mcp'),
                        'package_sha256' => __('Package SHA-256', 'raos-codex-mcp'),
                        'file_manifest_sha256' => __('File manifest SHA-256', 'raos-codex-mcp'),
                        'installed_tree_sha256' => __('Installed tree SHA-256', 'raos-codex-mcp'),
                    ) as $key => $label
                ) {
                    echo '<tr><th scope="row">' . esc_html($label) . '</th><td><code>'
                        . esc_html($bootstrap[$key]) . '</code></td></tr>';
                }
                echo '</tbody></table>';
                echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
                echo '<input type="hidden" name="action" value="raos_codex_mcp_attest_bootstrap">';
                echo '<input type="hidden" name="proposal_id" value="' . esc_attr($row['proposal_id']) . '">';
                wp_nonce_field('raos_codex_mcp_attest_bootstrap_' . $row['proposal_id']);
                echo '<p><label>' . esc_html__('Current password (human reauthentication)', 'raos-codex-mcp') . '<br><input type="password" name="current_password" autocomplete="current-password" required></label></p>';
                echo '<p><label>' . esc_html__('Manual installation attestation reason (10+ characters)', 'raos-codex-mcp') . '<br><textarea name="reason" rows="3" cols="80" minlength="10" maxlength="2000" required></textarea></label></p>';
                echo '<p><label>' . esc_html__('Type the final 8 characters of the proposal ID', 'raos-codex-mcp') . '<br><input type="text" name="proposal_suffix" minlength="8" maxlength="8" pattern="[0-9a-f]{8}" required> <code>' . esc_html($proposal_suffix) . '</code></label></p>';
                echo '<p><label>' . esc_html__('Type the final 8 characters of the package hash', 'raos-codex-mcp') . '<br><input type="text" name="package_suffix" minlength="8" maxlength="8" pattern="[0-9a-f]{8}" required> <code>' . esc_html($package_suffix) . '</code></label></p>';
                echo '<p><label>' . esc_html__('Type the final 8 characters of the installed tree/file-manifest hash', 'raos-codex-mcp') . '<br><input type="text" name="hash_suffix" minlength="8" maxlength="8" pattern="[0-9a-f]{8}" required> <code>' . esc_html($after_suffix) . '</code></label></p>';
                submit_button(__('Record exact manual bootstrap receipt', 'raos-codex-mcp'), 'primary', 'submit', false);
                echo '</form>';
                continue;
            }
            if ('PLUGIN_CHANGE' !== $row['kind']) {
                echo '<p><strong>'
                    . esc_html__('Content and theme proposals cannot be approved individually. Review and approve only the complete registered publication batch above.', 'raos-codex-mcp')
                    . '</strong></p>';
                continue;
            }
            if ((int) $row['created_by'] === get_current_user_id()) {
                echo '<p><strong>' . esc_html__('A different administrator must approve this proposal.', 'raos-codex-mcp') . '</strong></p>';
                continue;
            }
            echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
            echo '<input type="hidden" name="action" value="raos_codex_mcp_approve">';
            echo '<input type="hidden" name="proposal_id" value="' . esc_attr($row['proposal_id']) . '">';
            wp_nonce_field('raos_codex_mcp_approve_' . $row['proposal_id']);
            echo '<p><label>' . esc_html__('Current password (reauthentication)', 'raos-codex-mcp') . '<br><input type="password" name="current_password" autocomplete="current-password" required></label></p>';
            echo '<p><label>' . esc_html__('Approval reason (10+ characters)', 'raos-codex-mcp') . '<br><textarea name="reason" rows="3" cols="80" minlength="10" maxlength="2000" required></textarea></label></p>';
            echo '<p><label>' . esc_html__('Type the visible final 8 characters of the after hash', 'raos-codex-mcp') . '<br><input type="text" name="hash_suffix" minlength="8" maxlength="8" pattern="[0-9a-f]{8}" required> <code>' . esc_html($after_suffix) . '</code></label></p>';
            submit_button(__('Approve proposal only', 'raos-codex-mcp'), 'primary', 'submit', false);
            echo '</form>';
        }
        echo '</div>';
    }

    public function handle_approval()
    {
        if (! current_user_can('manage_options')
            || ! isset($_SERVER['REQUEST_METHOD'])
            || 'POST' !== $_SERVER['REQUEST_METHOD']) {
            wp_die(
                esc_html__('Approval refused.', 'raos-codex-mcp'),
                '',
                array('response' => 403)
            );
        }
        if (! self::runtime_identity_is_exact()) {
            wp_die(
                esc_html__('Approval refused while the plugin runtime is mixed.', 'raos-codex-mcp'),
                '',
                array('response' => 503)
            );
        }
        $proposal_id = isset($_POST['proposal_id']) ? sanitize_text_field(wp_unslash($_POST['proposal_id'])) : '';
        if (! RAOS_Codex_MCP_Store::is_sha256($proposal_id)) {
            wp_die(
                esc_html__('Approval refused.', 'raos-codex-mcp'),
                '',
                array('response' => 400)
            );
        }
        check_admin_referer('raos_codex_mcp_approve_' . $proposal_id);
        $row = RAOS_Codex_MCP_Store::get($proposal_id);
        $current_password = isset($_POST['current_password']) ? (string) wp_unslash($_POST['current_password']) : '';
        $reason = isset($_POST['reason']) ? sanitize_textarea_field(wp_unslash($_POST['reason'])) : '';
        $suffix = isset($_POST['hash_suffix']) ? sanitize_text_field(wp_unslash($_POST['hash_suffix'])) : '';
        $user = wp_get_current_user();
        if (is_wp_error($row)
            || ! $user instanceof WP_User
            || ! wp_check_password($current_password, $user->user_pass, $user->ID)
            || ! is_string($row['after_sha256'])
            || ! hash_equals(substr($row['after_sha256'], -8), $suffix)) {
            wp_die(
                esc_html__('Approval preconditions failed.', 'raos-codex-mcp'),
                '',
                array('response' => 403)
            );
        }
        $approved = RAOS_Codex_MCP_Store::approve($proposal_id, $user->ID, $reason);
        if (is_wp_error($approved)) {
            wp_die(
                esc_html($approved->get_error_code()),
                '',
                array('response' => 409)
            );
        }
        wp_safe_redirect(admin_url('tools.php?page=raos-codex-proposals&approved=1'));
        exit;
    }

    public function handle_batch_approval()
    {
        if (! current_user_can('manage_options')
            || ! isset($_SERVER['REQUEST_METHOD'])
            || 'POST' !== $_SERVER['REQUEST_METHOD']) {
            wp_die(
                esc_html__('Batch approval refused.', 'raos-codex-mcp'),
                '',
                array('response' => 403)
            );
        }
        if (! self::runtime_identity_is_exact()) {
            wp_die(
                esc_html__('Batch approval refused while the plugin runtime is mixed.', 'raos-codex-mcp'),
                '',
                array('response' => 503)
            );
        }
        $batch_hash = isset($_POST['batch_manifest_sha256'])
            ? sanitize_text_field(wp_unslash($_POST['batch_manifest_sha256']))
            : '';
        $batch_token = isset($_POST['batch_token'])
            ? sanitize_text_field(wp_unslash($_POST['batch_token']))
            : '';
        if (! RAOS_Codex_MCP_Store::is_sha256($batch_token)
            || ! RAOS_Codex_MCP_Store::is_sha256($batch_hash)) {
            wp_die(
                esc_html__('Batch approval refused.', 'raos-codex-mcp'),
                '',
                array('response' => 400)
            );
        }
        check_admin_referer('raos_codex_mcp_approve_batch_' . $batch_token . '_' . $batch_hash);
        $current_password = isset($_POST['current_password']) ? (string) wp_unslash($_POST['current_password']) : '';
        $reason = isset($_POST['reason']) ? sanitize_textarea_field(wp_unslash($_POST['reason'])) : '';
        $suffix = isset($_POST['hash_suffix']) ? sanitize_text_field(wp_unslash($_POST['hash_suffix'])) : '';
        $user = wp_get_current_user();
        if (! $user instanceof WP_User
            || ! wp_check_password($current_password, $user->user_pass, $user->ID)
            || ! hash_equals(substr($batch_hash, -8), $suffix)) {
            wp_die(
                esc_html__('Batch approval preconditions failed.', 'raos-codex-mcp'),
                '',
                array('response' => 403)
            );
        }
        $approved = RAOS_Codex_MCP_Store::approve_publication_batch(
            $batch_token,
            $batch_hash,
            $user->ID,
            $reason
        );
        if (is_wp_error($approved)) {
            $error_data = $approved->get_error_data();
            $status = is_array($error_data) && isset($error_data['status'])
                ? (int) $error_data['status']
                : 409;
            wp_die(
                esc_html($approved->get_error_code()),
                '',
                array('response' => $status)
            );
        }
        wp_safe_redirect(
            admin_url(
                'tools.php?page=raos-codex-proposals&batch_approved=' . absint($approved['proposal_count'])
            )
        );
        exit;
    }

    public function handle_bootstrap_attestation()
    {
        if (! current_user_can('manage_options')
            || ! isset($_SERVER['REQUEST_METHOD'])
            || 'POST' !== $_SERVER['REQUEST_METHOD']) {
            wp_die(
                esc_html__('Bootstrap attestation refused.', 'raos-codex-mcp'),
                '',
                array('response' => 403)
            );
        }
        if (! self::runtime_identity_is_exact()) {
            wp_die(
                esc_html__('Bootstrap attestation refused while the plugin runtime is mixed.', 'raos-codex-mcp'),
                '',
                array('response' => 503)
            );
        }
        $proposal_id = isset($_POST['proposal_id'])
            ? sanitize_text_field(wp_unslash($_POST['proposal_id']))
            : '';
        if (! RAOS_Codex_MCP_Store::is_sha256($proposal_id)) {
            wp_die(
                esc_html__('Bootstrap attestation refused.', 'raos-codex-mcp'),
                '',
                array('response' => 400)
            );
        }
        check_admin_referer('raos_codex_mcp_attest_bootstrap_' . $proposal_id);
        $row = RAOS_Codex_MCP_Store::get($proposal_id);
        $bootstrap = is_wp_error($row)
            ? $row
            : RAOS_Codex_MCP_Deployment::validate_manual_bootstrap_attestation($row);
        $current_password = isset($_POST['current_password'])
            ? (string) wp_unslash($_POST['current_password'])
            : '';
        $reason = isset($_POST['reason'])
            ? sanitize_textarea_field(wp_unslash($_POST['reason']))
            : '';
        $proposal_suffix = isset($_POST['proposal_suffix'])
            ? sanitize_text_field(wp_unslash($_POST['proposal_suffix']))
            : '';
        $package_suffix = isset($_POST['package_suffix'])
            ? sanitize_text_field(wp_unslash($_POST['package_suffix']))
            : '';
        $hash_suffix = isset($_POST['hash_suffix'])
            ? sanitize_text_field(wp_unslash($_POST['hash_suffix']))
            : '';
        $user = wp_get_current_user();
        if (is_wp_error($bootstrap)
            || ! $user instanceof WP_User
            || ! wp_check_password($current_password, $user->user_pass, $user->ID)
            || (int) $row['created_by'] === (int) $user->ID
            || ! hash_equals(substr($bootstrap['proposal_id'], -8), $proposal_suffix)
            || ! hash_equals(substr($bootstrap['package_sha256'], -8), $package_suffix)
            || ! hash_equals(substr($bootstrap['file_manifest_sha256'], -8), $hash_suffix)) {
            wp_die(
                esc_html__('Bootstrap attestation preconditions failed.', 'raos-codex-mcp'),
                '',
                array('response' => 403)
            );
        }
        $attested = RAOS_Codex_MCP_Deployment::attest_manual_bootstrap(
            $proposal_id,
            $user->ID,
            $reason
        );
        if (is_wp_error($attested)) {
            $error_data = $attested->get_error_data();
            $status = is_array($error_data) && isset($error_data['status'])
                ? (int) $error_data['status']
                : 409;
            wp_die(
                esc_html($attested->get_error_code()),
                '',
                array('response' => $status)
            );
        }
        wp_safe_redirect(
            admin_url('tools.php?page=raos-codex-proposals&bootstrap_attested=1')
        );
        exit;
    }

    public function compatibility_notice()
    {
        if (! current_user_can('activate_plugins') || self::runtime_compatible()) {
            return;
        }
        echo '<div class="notice notice-error"><p>'
            . esc_html__('RAOS Codex MCP is inactive until WordPress 7.1.x and MCP Adapter 0.6.1 are active.', 'raos-codex-mcp')
            . '</p></div>';
    }

    private static function runtime_compatible()
    {
        global $wp_version;
        return is_string($wp_version)
            && preg_match('/\A7\.1(?:\.|\z)/', $wp_version) === 1
            && self::runtime_identity_is_exact()
            && defined('WP_MCP_VERSION')
            && '0.6.1' === WP_MCP_VERSION
            && function_exists('wp_register_ability')
            && class_exists('\WP\MCP\Transport\HttpTransport');
    }

    private static function runtime_origin_is_exact()
    {
        return ! is_multisite()
            && untrailingslashit(home_url()) === self::ORIGIN
            && untrailingslashit(site_url()) === self::ORIGIN
            && is_ssl();
    }

    private static function error($code, $status)
    {
        return new WP_Error($code, 'The RAOS Codex credential is outside its permitted surface.', array('status' => $status));
    }
}

register_activation_hook(__FILE__, array('RAOS_Codex_MCP_Abilities', 'activate'));
RAOS_Codex_MCP_Abilities::instance();
