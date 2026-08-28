<?php
/**
 * Plugin Name: RAOS AT-003 Recovery Operator
 * Description: One fixed snapshot repair and Draft-to-Publish recovery for ST-1704 AT-003.
 * Version: 1.1.0
 * Requires at least: 7.1
 * Tested up to: 7.1
 * Requires PHP: 8.1
 * Author: RAOS
 * License: Proprietary
 */

if (! defined('ABSPATH')) {
    exit;
}

final class RAOS_AT003_Recovery_Operator_V1
{
    const VERSION = '1.1.0';
    const PAGE = 'raos-at003-recovery-v1';
    const ACTION = 'raos_apply_at003_recovery_v1';
    const LOCK_KEY = '_raos_at003_recovery_lock_v1_f743a2944f1adca0a8fef2cdd850567767f2257836bb807c47901b25c04fc942';
    const SOURCE_POST_ID = 26;
    const TARGET_POST_ID = 19;
    const ARTICLE_ID = 'st1703-first-suitcase-comparison';
    const PUBLIC_SLUG = 'carry-on-suitcase-comparison';
    const CATEGORY_NAME = '暮らしの道具';
    const PACKET_SHA256 = '570708758b22b2af06e663d1e89dbb39bcd2bb4536e039a6c486e6d47405687c';
    const REQUEST_SHA256 = '9ead64fcc0bedb35718d9e62c8f073cf89482d97a182243e5852feb4b272b516';
    const PAYLOAD_SHA256 = 'f743a2944f1adca0a8fef2cdd850567767f2257836bb807c47901b25c04fc942';
    const SNAPSHOT_RAW_SHA256 = 'bd71097b68c3c4386459195e7e41a08ebb3e60f2912594b25ed66763bb25ba9a';
    const REQUIRED_THEME_VERSION = '1.3.1';
    const SNAPSHOT_META_KEY = '_raos_publication_snapshot_v1';

    private static $instance = null;
    private static $context_failure = 'NOT_EVALUATED';

    public static function instance()
    {
        if (! (self::$instance instanceof self)) {
            self::$instance = new self();
        }
        return self::$instance;
    }

    private function __construct()
    {
        add_action('admin_menu', array($this, 'register_page'));
        add_action('admin_post_' . self::ACTION, array($this, 'handle'));
    }

    private static function writes_enabled()
    {
        return defined('RAOS_AT003_RECOVERY_WRITES_ENABLED')
            && RAOS_AT003_RECOVERY_WRITES_ENABLED === true;
    }

    public function register_page()
    {
        add_management_page(
            'AT-003 Draft recovery',
            'AT-003 Draft recovery',
            'manage_options',
            self::PAGE,
            array($this, 'render')
        );
    }

    private static function exact_keys($value, $keys)
    {
        if (! is_array($value)) {
            return false;
        }
        $actual = array_keys($value);
        sort($actual, SORT_STRING);
        sort($keys, SORT_STRING);
        return $actual === $keys;
    }

    private static function canonical_json($value)
    {
        if (! function_exists('kurashinoshirube_canonical_json')) {
            return null;
        }
        return kurashinoshirube_canonical_json($value);
    }

    private static function clean_reason($value)
    {
        return function_exists('kurashinoshirube_is_clean_text')
            && kurashinoshirube_is_clean_text($value, 10, 300);
    }

    private static function expected_snapshot_raw()
    {
        $path = __DIR__ . '/at003-snapshot.v1.json';
        $raw = is_file($path) && ! is_link($path) ? file_get_contents($path) : false;
        if (! is_string($raw)) {
            return null;
        }
        $raw = rtrim($raw, "\r\n");
        return hash_equals(self::SNAPSHOT_RAW_SHA256, hash('sha256', $raw))
            ? $raw
            : null;
    }

    private static function category_id()
    {
        $terms = get_terms(
            array(
                'taxonomy' => 'category',
                'hide_empty' => false,
                'name' => self::CATEGORY_NAME,
            )
        );
        if (is_wp_error($terms) || ! is_array($terms) || count($terms) !== 1) {
            return null;
        }
        $term = $terms[0];
        return $term instanceof WP_Term
            && $term->name === self::CATEGORY_NAME
            && (int) $term->term_id > 0
            ? (int) $term->term_id
            : null;
    }

    private static function taxonomy_state($post_id)
    {
        $taxonomies = get_object_taxonomies('post', 'names');
        if (! is_array($taxonomies)) {
            return null;
        }
        sort($taxonomies, SORT_STRING);
        $state = array();
        foreach ($taxonomies as $taxonomy) {
            if (! is_string($taxonomy) || $taxonomy === '') {
                return null;
            }
            $ids = wp_get_object_terms($post_id, $taxonomy, array('fields' => 'ids'));
            if (is_wp_error($ids) || ! is_array($ids)) {
                return null;
            }
            $ids = array_map('intval', $ids);
            sort($ids, SORT_NUMERIC);
            $state[$taxonomy] = $ids;
        }
        return $state;
    }

    private static function protected_state($post, $taxonomy_state)
    {
        if (! ($post instanceof WP_Post) || ! is_array($taxonomy_state)) {
            return null;
        }
        return array(
            'comment_status' => $post->comment_status,
            'guid' => $post->guid,
            'menu_order' => (int) $post->menu_order,
            'ping_status' => $post->ping_status,
            'post_author' => (int) $post->post_author,
            'post_name' => $post->post_name,
            'post_parent' => (int) $post->post_parent,
            'post_password' => $post->post_password,
            'post_type' => $post->post_type,
            'taxonomies' => $taxonomy_state,
        );
    }

    private static function pre_state($post_id)
    {
        $post = get_post($post_id);
        $taxonomies = self::taxonomy_state($post_id);
        $protected = self::protected_state($post, $taxonomies);
        $snapshot = get_post_meta($post_id, self::SNAPSHOT_META_KEY, true);
        if (! ($post instanceof WP_Post) || $protected === null || ! is_string($snapshot)) {
            return null;
        }
        return array(
            'post_content' => $post->post_content,
            'post_date' => $post->post_date,
            'post_date_gmt' => $post->post_date_gmt,
            'post_excerpt' => $post->post_excerpt,
            'post_status' => $post->post_status,
            'post_title' => $post->post_title,
            'protected' => $protected,
            'snapshot_raw' => $snapshot,
        );
    }

    private static function source_content_matches($context)
    {
        $source = get_post(self::SOURCE_POST_ID);
        return $source instanceof WP_Post
            && $source->post_status === 'draft'
            && $source->post_name === $context['review_slug']
            && $source->post_title === $context['source_title']
            && $source->post_excerpt === $context['source_excerpt']
            && $source->post_content === $context['source_content'];
    }

    private static function source_matches($context)
    {
        $snapshot_raw = get_post_meta(
            self::SOURCE_POST_ID,
            self::SNAPSHOT_META_KEY,
            true
        );
        $bound = function_exists('kurashinoshirube_bound_post_snapshot')
            ? kurashinoshirube_bound_post_snapshot(self::SOURCE_POST_ID, true)
            : null;
        return self::source_content_matches($context)
            && is_string($snapshot_raw)
            && $snapshot_raw === $context['snapshot_raw']
            && is_array($bound)
            && ($bound['article_id'] ?? null) === self::ARTICLE_ID
            && ($bound['packet_sha256'] ?? null) === self::PACKET_SHA256;
    }

    private static function runtime_ready()
    {
        $required_functions = array(
            'kurashinoshirube_bound_post_snapshot',
            'kurashinoshirube_canonical_json',
            'kurashinoshirube_is_clean_text',
            'kurashinoshirube_parse_snapshot',
            'kurashinoshirube_yoast_configuration_is_exact',
        );
        foreach ($required_functions as $function) {
            if (! function_exists($function)) {
                return false;
            }
        }
        $theme = wp_get_theme();
        return get_stylesheet() === 'kurashinoshirube-child'
            && is_object($theme)
            && $theme->get('Version') === self::REQUIRED_THEME_VERSION
            && kurashinoshirube_yoast_configuration_is_exact();
    }

    private static function context()
    {
        self::$context_failure = 'UNKNOWN';
        if (! self::runtime_ready()) {
            self::$context_failure = 'RUNTIME_PROFILE';
            return null;
        }
        $category_id = self::category_id();
        $source = get_post(self::SOURCE_POST_ID);
        $target = get_post(self::TARGET_POST_ID);
        $target_pre = self::pre_state(self::TARGET_POST_ID);
        $source_snapshot_pre_raw = get_post_meta(
            self::SOURCE_POST_ID,
            self::SNAPSHOT_META_KEY,
            true
        );
        $snapshot_raw = self::expected_snapshot_raw();
        $snapshot = kurashinoshirube_parse_snapshot($snapshot_raw);
        $payload_json = self::canonical_json($snapshot);
        $review_slug = 'raos-review-' . self::PUBLIC_SLUG . '-' . self::PAYLOAD_SHA256;
        if ($category_id === null) {
            self::$context_failure = 'CATEGORY';
            return null;
        }
        if (! ($source instanceof WP_Post) || ! ($target instanceof WP_Post)) {
            self::$context_failure = 'POST_OBJECTS';
            return null;
        }
        if ($target_pre === null) {
            self::$context_failure = 'TARGET_PRE_STATE';
            return null;
        }
        if (! is_string($source_snapshot_pre_raw) || ! is_string($snapshot_raw)) {
            self::$context_failure = 'SNAPSHOT_RAW';
            return null;
        }
        if (! is_array($snapshot)) {
            self::$context_failure = 'SNAPSHOT_PARSE';
            return null;
        }
        if (! is_string($payload_json)) {
            self::$context_failure = 'SNAPSHOT_CANONICAL';
            return null;
        }
        if (
            ! hash_equals(self::PAYLOAD_SHA256, hash('sha256', $payload_json))
            || ($snapshot['article_id'] ?? null) !== self::ARTICLE_ID
            || ($snapshot['slug'] ?? null) !== self::PUBLIC_SLUG
            || ($snapshot['packet_sha256'] ?? null) !== self::PACKET_SHA256
        ) {
            self::$context_failure = 'SNAPSHOT_BINDING';
            return null;
        }
        if (
            $source->post_status !== 'draft'
            || $source->post_name !== $review_slug
            || $source->post_type !== 'post'
            || $source->post_excerpt !== ($snapshot['description'] ?? null)
        ) {
            self::$context_failure = 'SOURCE_POST';
            return null;
        }
        if (
            $target->post_status !== 'draft'
            || $target->post_name !== self::PUBLIC_SLUG
            || $target->post_type !== 'post'
            || ($target_pre['protected']['taxonomies']['category'] ?? null)
                !== array($category_id)
        ) {
            self::$context_failure = 'TARGET_POST';
            return null;
        }
        $request_material = self::canonical_json(
            array(
                'body' => array(
                    'content' => $source->post_content,
                    'excerpt' => $source->post_excerpt,
                    'meta' => array(self::SNAPSHOT_META_KEY => $snapshot_raw),
                    'slug' => $review_slug,
                    'status' => 'draft',
                    'title' => $source->post_title,
                ),
                'origin' => 'https://kurashinoshirube.com',
                'path' => KURASHINOSHIRUBE_REVIEW_REQUEST_PATH,
            )
        );
        $pre_json = self::canonical_json($target_pre);
        if (
            ! is_string($request_material)
            || ! hash_equals(self::REQUEST_SHA256, hash('sha256', $request_material))
            || ! is_string($pre_json)
        ) {
            self::$context_failure = 'REQUEST_BINDING';
            return null;
        }
        $pre_sha256 = hash('sha256', $pre_json);
        $operation = array(
            'action' => 'AT003_DRAFT_TO_PUBLISH_RECOVERY_V1',
            'category_id' => $category_id,
            'packet_sha256' => self::PACKET_SHA256,
            'payload_sha256' => self::PAYLOAD_SHA256,
            'pre_state_sha256' => $pre_sha256,
            'request_sha256' => self::REQUEST_SHA256,
            'source_snapshot_pre_sha256' => hash('sha256', $source_snapshot_pre_raw),
            'source_snapshot_repair_sha256' => self::SNAPSHOT_RAW_SHA256,
            'source_post_id' => self::SOURCE_POST_ID,
            'target_post_id' => self::TARGET_POST_ID,
        );
        $operation_json = self::canonical_json($operation);
        if (! is_string($operation_json)) {
            self::$context_failure = 'OPERATION_BINDING';
            return null;
        }
        self::$context_failure = 'PASS';
        return array(
            'category_id' => $category_id,
            'operation_sha256' => hash('sha256', $operation_json),
            'pre_state' => $target_pre,
            'pre_state_sha256' => $pre_sha256,
            'review_slug' => $review_slug,
            'snapshot_raw' => $snapshot_raw,
            'source_snapshot_pre_raw' => $source_snapshot_pre_raw,
            'source_content' => $source->post_content,
            'source_excerpt' => $source->post_excerpt,
            'source_title' => $source->post_title,
        );
    }

    private static function locked_context($lock_raw)
    {
        if (! self::runtime_ready() || ! is_string($lock_raw) || $lock_raw === '') {
            return null;
        }
        $record = json_decode($lock_raw, true);
        $keys = array(
            'approved_at',
            'approved_by_user_id',
            'decision',
            'operation_sha256',
            'pre_state',
            'pre_state_sha256',
            'reason',
            'schema',
            'source_snapshot_pre_raw',
            'source_snapshot_pre_sha256',
        );
        if (
            ! self::exact_keys($record, $keys)
            || ($record['schema'] ?? null) !== 'RAOS_AT003_RECOVERY_LOCK_V1'
            || ($record['decision'] ?? null) !== 'APPROVE_AT003_DRAFT_TO_PUBLISH_RECOVERY_V1'
            || ! is_int($record['approved_by_user_id'] ?? null)
            || ($record['approved_by_user_id'] ?? 0) <= 0
            || ! is_string($record['operation_sha256'] ?? null)
            || preg_match('/\A[0-9a-f]{64}\z/D', $record['operation_sha256']) !== 1
            || ! is_string($record['pre_state_sha256'] ?? null)
            || preg_match('/\A[0-9a-f]{64}\z/D', $record['pre_state_sha256']) !== 1
            || ! is_array($record['pre_state'] ?? null)
            || ! is_string($record['source_snapshot_pre_raw'] ?? null)
            || ! is_string($record['source_snapshot_pre_sha256'] ?? null)
            || ! hash_equals(
                $record['source_snapshot_pre_sha256'],
                hash('sha256', $record['source_snapshot_pre_raw'])
            )
        ) {
            return null;
        }
        $pre_json = self::canonical_json($record['pre_state']);
        $category_id = self::category_id();
        $source = get_post(self::SOURCE_POST_ID);
        $snapshot_raw = self::expected_snapshot_raw();
        $review_slug = 'raos-review-' . self::PUBLIC_SLUG . '-' . self::PAYLOAD_SHA256;
        if (
            ! is_string($pre_json)
            || ! hash_equals($record['pre_state_sha256'], hash('sha256', $pre_json))
            || $category_id === null
            || ! ($source instanceof WP_Post)
            || ! is_string($snapshot_raw)
        ) {
            return null;
        }
        $context = array(
            'category_id' => $category_id,
            'operation_sha256' => $record['operation_sha256'],
            'pre_state' => $record['pre_state'],
            'pre_state_sha256' => $record['pre_state_sha256'],
            'review_slug' => $review_slug,
            'snapshot_raw' => $snapshot_raw,
            'source_content' => $source->post_content,
            'source_excerpt' => $source->post_excerpt,
            'source_title' => $source->post_title,
        );
        return self::source_matches($context) ? $context : null;
    }

    private static function lock_record($context, $user_id, $reason)
    {
        $record = array(
            'approved_at' => gmdate('Y-m-d\TH:i:s\Z'),
            'approved_by_user_id' => $user_id,
            'decision' => 'APPROVE_AT003_DRAFT_TO_PUBLISH_RECOVERY_V1',
            'operation_sha256' => $context['operation_sha256'],
            'pre_state' => $context['pre_state'],
            'pre_state_sha256' => $context['pre_state_sha256'],
            'reason' => $reason,
            'schema' => 'RAOS_AT003_RECOVERY_LOCK_V1',
            'source_snapshot_pre_raw' => $context['source_snapshot_pre_raw'],
            'source_snapshot_pre_sha256' => hash(
                'sha256',
                $context['source_snapshot_pre_raw']
            ),
        );
        return self::canonical_json($record);
    }

    private static function target_matches($context)
    {
        $target = get_post(self::TARGET_POST_ID);
        $snapshot_raw = get_post_meta(
            self::TARGET_POST_ID,
            self::SNAPSHOT_META_KEY,
            true
        );
        $taxonomy = self::taxonomy_state(self::TARGET_POST_ID);
        $protected = self::protected_state($target, $taxonomy);
        $bound = function_exists('kurashinoshirube_bound_post_snapshot')
            ? kurashinoshirube_bound_post_snapshot(self::TARGET_POST_ID, false)
            : null;
        return $target instanceof WP_Post
            && $target->post_status === 'publish'
            && $target->post_name === self::PUBLIC_SLUG
            && $target->post_title === $context['source_title']
            && $target->post_excerpt === $context['source_excerpt']
            && $target->post_content === $context['source_content']
            && is_string($snapshot_raw)
            && $snapshot_raw === $context['snapshot_raw']
            && is_array($protected)
            && $protected === $context['pre_state']['protected']
            && ($taxonomy['category'] ?? null) === array($context['category_id'])
            && is_array($bound)
            && ($bound['article_id'] ?? null) === self::ARTICLE_ID;
    }

    private static function restore_taxonomies($state)
    {
        if (! is_array($state)) {
            return false;
        }
        foreach ($state as $taxonomy => $ids) {
            if (! is_string($taxonomy) || ! is_array($ids)) {
                return false;
            }
            $result = wp_set_object_terms(self::TARGET_POST_ID, $ids, $taxonomy, false);
            if (is_wp_error($result)) {
                return false;
            }
        }
        return true;
    }

    private static function rollback($context)
    {
        $pre = $context['pre_state'];
        $updated = wp_update_post(
            array(
                'ID' => self::TARGET_POST_ID,
                'post_content' => $pre['post_content'],
                'post_date' => $pre['post_date'],
                'post_date_gmt' => $pre['post_date_gmt'],
                'post_excerpt' => $pre['post_excerpt'],
                'post_status' => $pre['post_status'],
                'post_title' => $pre['post_title'],
            ),
            true
        );
        update_post_meta(
            self::TARGET_POST_ID,
            self::SNAPSHOT_META_KEY,
            $pre['snapshot_raw']
        );
        update_post_meta(
            self::SOURCE_POST_ID,
            self::SNAPSHOT_META_KEY,
            $context['source_snapshot_pre_raw']
        );
        $taxonomies_ok = self::restore_taxonomies(
            $pre['protected']['taxonomies'] ?? null
        );
        clean_post_cache(self::TARGET_POST_ID);
        return ! is_wp_error($updated)
            && (int) $updated === self::TARGET_POST_ID
            && $taxonomies_ok
            && get_post_meta(
                self::SOURCE_POST_ID,
                self::SNAPSHOT_META_KEY,
                true
            ) === $context['source_snapshot_pre_raw']
            && self::pre_state(self::TARGET_POST_ID) === $pre;
    }

    private static function admin_url()
    {
        return add_query_arg(array('page' => self::PAGE), admin_url('tools.php'));
    }

    public function render()
    {
        if (! current_user_can('manage_options') || ! current_user_can('publish_posts')) {
            wp_die(esc_html('This recovery action is not available.'), '', array('response' => 403));
        }
        echo '<div class="wrap"><h1>AT-003 Draft recovery</h1>';
        if (! self::writes_enabled()) {
            echo '<div class="notice notice-warning"><p>Host write gate is disabled.</p></div></div>';
            return;
        }
        $lock = get_option(self::LOCK_KEY, null);
        if (is_string($lock) && $lock !== '') {
            $locked_context = self::locked_context($lock);
            echo $locked_context !== null && self::target_matches($locked_context)
                ? '<div class="notice notice-success"><p>Recovery is applied and verified.</p></div></div>'
                : '<div class="notice notice-error"><p>A durable recovery lock exists. Do not retry; audit the target and rollback artifact.</p></div></div>';
            return;
        }
        $context = self::context();
        if (
            $context === null
            || ! current_user_can('edit_post', self::SOURCE_POST_ID)
            || ! current_user_can('edit_post', self::TARGET_POST_ID)
        ) {
            echo '<div class="notice notice-error"><p>Fixed recovery conditions are not satisfied. Diagnostic: <code>'
                . esc_html(self::$context_failure) . '</code></p></div></div>';
            return;
        }
        echo '<p>This action atomically applies the fixed Review Draft to post 19 and publishes it.</p>';
        echo '<table class="widefat striped"><tbody>';
        $rows = array(
            'Article' => self::ARTICLE_ID,
            'Review Draft post' => (string) self::SOURCE_POST_ID,
            'Target Draft post' => (string) self::TARGET_POST_ID,
            'Category' => self::CATEGORY_NAME,
            'Packet SHA-256' => self::PACKET_SHA256,
            'Request SHA-256' => self::REQUEST_SHA256,
            'Payload SHA-256' => self::PAYLOAD_SHA256,
            'Pre-state SHA-256' => $context['pre_state_sha256'],
            'Operation SHA-256' => $context['operation_sha256'],
        );
        foreach ($rows as $label => $value) {
            echo '<tr><th scope="row">' . esc_html($label) . '</th><td><code>'
                . esc_html($value) . '</code></td></tr>';
        }
        echo '</tbody></table><form method="post" action="'
            . esc_url(admin_url('admin-post.php')) . '">';
        echo '<input type="hidden" name="action" value="' . esc_attr(self::ACTION) . '">';
        echo '<input type="hidden" name="pre_state_sha256" value="'
            . esc_attr($context['pre_state_sha256']) . '">';
        echo '<input type="hidden" name="operation_sha256" value="'
            . esc_attr($context['operation_sha256']) . '">';
        echo '<p><label for="raos-at003-recovery-reason"><strong>Reason</strong></label><br>'
            . '<textarea id="raos-at003-recovery-reason" name="approval_reason" required minlength="10" maxlength="300" rows="3" cols="70"></textarea></p>';
        echo '<p><label for="raos-at003-recovery-confirmation"><strong>Final 12 operation-hash characters</strong></label><br>'
            . '<input id="raos-at003-recovery-confirmation" name="hash_confirmation" required pattern="[0-9a-f]{12}" maxlength="12"></p>';
        echo '<p><label for="raos-at003-recovery-password"><strong>Current WordPress password</strong></label><br>'
            . '<input id="raos-at003-recovery-password" type="password" name="current_password" required autocomplete="current-password"></p>';
        wp_nonce_field(self::ACTION . '|' . $context['operation_sha256']);
        submit_button('Apply fixed AT-003 recovery and publish');
        echo '</form></div>';
    }

    public function handle()
    {
        if (! self::writes_enabled()) {
            wp_die(esc_html('Host write gate is disabled.'), '', array('response' => 503));
        }
        if (
            ($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST'
            || ! is_user_logged_in()
            || ! current_user_can('manage_options')
            || ! current_user_can('publish_posts')
        ) {
            wp_die(esc_html('Recovery authentication failed.'), '', array('response' => 403));
        }
        $context = self::context();
        if (
            $context === null
            || ! current_user_can('edit_post', self::SOURCE_POST_ID)
            || ! current_user_can('edit_post', self::TARGET_POST_ID)
        ) {
            wp_die(esc_html('Fixed recovery conditions are not satisfied.'), '', array('response' => 409));
        }
        $reason_input = isset($_POST['approval_reason'])
            ? wp_unslash($_POST['approval_reason'])
            : '';
        $confirmation = isset($_POST['hash_confirmation'])
            ? sanitize_text_field(wp_unslash($_POST['hash_confirmation']))
            : '';
        $reauth_input = isset($_POST['current_password'])
            ? (string) wp_unslash($_POST['current_password'])
            : '';
        $pre_state_sha256 = isset($_POST['pre_state_sha256'])
            ? sanitize_text_field(wp_unslash($_POST['pre_state_sha256']))
            : '';
        $operation_sha256 = isset($_POST['operation_sha256'])
            ? sanitize_text_field(wp_unslash($_POST['operation_sha256']))
            : '';
        if (
            ! self::clean_reason($reason_input)
            || ! hash_equals(substr($context['operation_sha256'], -12), $confirmation)
            || ! hash_equals($context['pre_state_sha256'], $pre_state_sha256)
            || ! hash_equals($context['operation_sha256'], $operation_sha256)
            || $reauth_input === ''
            || strlen($reauth_input) > 4096
        ) {
            $reauth_input = '';
            wp_die(esc_html('Recovery approval evidence is invalid.'), '', array('response' => 400));
        }
        check_admin_referer(self::ACTION . '|' . $context['operation_sha256']);
        $current_user = wp_get_current_user();
        $password_ok = $current_user instanceof WP_User
            && wp_check_password($reauth_input, $current_user->user_pass, $current_user->ID);
        $reauth_input = '';
        if (! $password_ok) {
            wp_die(esc_html('Password reauthentication failed.'), '', array('response' => 403));
        }
        if (
            get_option(self::LOCK_KEY, null) !== null
            || ! function_exists('wp_check_post_lock')
            || wp_check_post_lock(self::TARGET_POST_ID) !== false
            || ! self::source_content_matches($context)
            || get_post_meta(
                self::SOURCE_POST_ID,
                self::SNAPSHOT_META_KEY,
                true
            ) !== $context['source_snapshot_pre_raw']
            || self::pre_state(self::TARGET_POST_ID) !== $context['pre_state']
        ) {
            wp_die(esc_html('Recovery pre-state changed or is locked.'), '', array('response' => 409));
        }
        $lock_record = self::lock_record(
            $context,
            (int) $current_user->ID,
            sanitize_textarea_field($reason_input)
        );
        if (
            ! is_string($lock_record)
            || ! add_option(self::LOCK_KEY, $lock_record, '', false)
        ) {
            wp_die(esc_html('Durable recovery lock could not be acquired.'), '', array('response' => 409));
        }
        update_post_meta(
            self::SOURCE_POST_ID,
            self::SNAPSHOT_META_KEY,
            $context['snapshot_raw']
        );
        if (! self::source_matches($context)) {
            $rolled_back = self::rollback($context);
            wp_die(
                esc_html($rolled_back
                    ? 'Review Draft snapshot repair failed and the original Drafts were restored.'
                    : 'Review Draft snapshot repair and rollback failed; inspect the site immediately.'),
                '',
                array('response' => 500)
            );
        }
        update_post_meta(
            self::TARGET_POST_ID,
            self::SNAPSHOT_META_KEY,
            $context['snapshot_raw']
        );
        $stored_snapshot = get_post_meta(
            self::TARGET_POST_ID,
            self::SNAPSHOT_META_KEY,
            true
        );
        if ($stored_snapshot !== $context['snapshot_raw']) {
            $rolled_back = self::rollback($context);
            wp_die(
                esc_html($rolled_back
                    ? 'Snapshot write failed and the Draft was restored.'
                    : 'Snapshot write and rollback failed; inspect the site immediately.'),
                '',
                array('response' => 500)
            );
        }
        $updated = wp_update_post(
            array(
                'ID' => self::TARGET_POST_ID,
                'post_content' => $context['source_content'],
                'post_excerpt' => $context['source_excerpt'],
                'post_status' => 'publish',
                'post_title' => $context['source_title'],
            ),
            true
        );
        clean_post_cache(self::TARGET_POST_ID);
        if (
            is_wp_error($updated)
            || (int) $updated !== self::TARGET_POST_ID
            || ! self::target_matches($context)
        ) {
            $rolled_back = self::rollback($context);
            wp_die(
                esc_html($rolled_back
                    ? 'Recovery verification failed and the Draft was restored. Audit the durable lock.'
                    : 'Recovery verification and rollback failed; inspect the public site immediately.'),
                '',
                array('response' => 500)
            );
        }
        wp_safe_redirect(self::admin_url());
        exit;
    }
}

RAOS_AT003_Recovery_Operator_V1::instance();
