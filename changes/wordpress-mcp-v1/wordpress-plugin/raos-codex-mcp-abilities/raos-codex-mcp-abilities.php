<?php
/**
 * Plugin Name: RAOS Codex MCP Abilities
 * Description: Browser-independent, approval-bound content and deployment abilities for kurashinoshirube.com.
 * Version: 1.1.0
 * Requires at least: 7.1
 * Requires PHP: 8.1
 * Author: RAOS
 * License: GPL-2.0-or-later
 * Update URI: false
 *
 * @package RAOS_Codex_MCP_Abilities
 */

defined('ABSPATH') || exit;

define('RAOS_CODEX_MCP_VERSION', '1.1.0');
define('RAOS_CODEX_MCP_FILE', __FILE__);

require_once __DIR__ . '/includes/class-raos-codex-mcp-store.php';
require_once __DIR__ . '/includes/class-raos-codex-mcp-content.php';
require_once __DIR__ . '/includes/class-raos-codex-mcp-deployment.php';

final class RAOS_Codex_MCP_Abilities
{
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
        add_action('admin_notices', array($this, 'compatibility_notice'));
    }

    public static function activate()
    {
        global $wp_version;
        if (version_compare(PHP_VERSION, '8.1', '<')
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
            'Draft editing and immutable release proposals only. No publish, delete, media-write, theme, plugin, PHP, SQL, or generic ability execution tool is exposed.',
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
                'raos-codex/operation-get',
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
        if (is_multisite()
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
            && $this->authenticated_for_role(self::EDITOR_ROLE)
            && current_user_can('raos_codex_mcp_access');
    }

    public function ability_permission($input = null)
    {
        unset($input);
        return $this->authenticated_for_role(self::EDITOR_ROLE)
            && current_user_can('raos_codex_content_read');
    }

    public function operator_rest_permission()
    {
        return $this->authenticated_for_role(self::OPERATOR_ROLE)
            && current_user_can('raos_codex_deploy_access');
    }

    private function authenticated_for_role($role)
    {
        $user = wp_get_current_user();
        return self::$application_password_user_id > 0
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

    public function render_admin_page()
    {
        if (! current_user_can('manage_options')) {
            wp_die(esc_html__('Permission denied.', 'raos-codex-mcp'));
        }
        $rows = RAOS_Codex_MCP_Store::pending_for_admin(50);
        echo '<div class="wrap"><h1>' . esc_html__('RAOS Codex proposals', 'raos-codex-mcp') . '</h1>';
        echo '<p>' . esc_html__('Review the complete before/after hashes and payload. Approval issues one proposal-bound, single-use authorization; it never applies the change. The bounded operator must still pass If-Match, idempotency, TTL, the global kill switch, drift, backup, and readback checks.', 'raos-codex-mcp') . '</p>';
        if (empty($rows)) {
            echo '<p>' . esc_html__('No pending proposals.', 'raos-codex-mcp') . '</p></div>';
            return;
        }
        foreach ($rows as $row) {
            $payload = wp_json_encode($row['payload'], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
            echo '<hr><h2><code>' . esc_html($row['proposal_id']) . '</code></h2>';
            echo '<p>' . esc_html($row['kind'] . ' / ' . $row['state'] . ' / expires ' . $row['expires_at_gmt'] . ' GMT') . '</p>';
            echo '<p>before: <code>' . esc_html((string) $row['before_sha256']) . '</code><br>after: <code>' . esc_html((string) $row['after_sha256']) . '</code></p>';
            echo '<details><summary>' . esc_html__('Complete immutable payload', 'raos-codex-mcp') . '</summary><pre style="white-space:pre-wrap;max-height:40rem;overflow:auto">' . esc_html((string) $payload) . '</pre></details>';
            if ('MANUAL_REQUIRED' === $row['state']) {
                echo '<p><strong>' . esc_html__('Automatic approval/apply is unavailable because migration safety could not be established.', 'raos-codex-mcp') . '</strong></p>';
                continue;
            }
            echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
            echo '<input type="hidden" name="action" value="raos_codex_mcp_approve">';
            echo '<input type="hidden" name="proposal_id" value="' . esc_attr($row['proposal_id']) . '">';
            wp_nonce_field('raos_codex_mcp_approve_' . $row['proposal_id']);
            echo '<p><label>' . esc_html__('Current password (reauthentication)', 'raos-codex-mcp') . '<br><input type="password" name="current_password" autocomplete="current-password" required></label></p>';
            echo '<p><label>' . esc_html__('Approval reason (10+ characters)', 'raos-codex-mcp') . '<br><textarea name="reason" rows="3" cols="80" minlength="10" maxlength="2000" required></textarea></label></p>';
            echo '<p><label>' . esc_html__('Type the final 8 characters of the after hash', 'raos-codex-mcp') . '<br><input type="text" name="hash_suffix" minlength="8" maxlength="8" pattern="[0-9a-f]{8}" required></label></p>';
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
