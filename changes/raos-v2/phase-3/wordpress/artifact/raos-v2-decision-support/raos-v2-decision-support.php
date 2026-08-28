<?php
/**
 * Plugin Name: RAOS V2 Decision Support Presentation
 * Description: Route-scoped presentation styles for the sealed A05 WordPress payload.
 * Version: 0.6.0
 * Requires PHP: 7.4
 * License: Proprietary
 *
 * This plugin performs no remote request, write, publication, telemetry, option,
 * cron, REST, or admin action. Before activation an external owner must replace
 * the deployment-disabled cutover binding with one derived from the preaction
 * owner export. The binding pins the target post ID and the exact legacy and
 * sealed database byte hashes.
 *
 * On the exact target, valid legacy database bytes preserve the existing
 * WordPress-filtered response without CSS or an envelope. Exact sealed database
 * bytes discard earlier filter output and render only the generator-owned raw
 * reviewed fragment in the verification envelope. A disabled, missing, invalid,
 * or intermediate binding/content state returns a fixed blocked response. The
 * content callback projects only the exact current post in the singular main
 * query's main loop. Only a verified different current post is treated as a
 * secondary the_content call and retains its already-filtered input. Missing or
 * ambiguous context and target-post rendering outside the main loop are blocked.
 * The main content callback must be final at PHP_INT_MAX; a later callback
 * terminates the target request with a fixed 503 before it can run. The safe
 * cutover order is binding replacement, activation, then the sealed database
 * write. Public capture still verifies the rendered response.
 */

defined('ABSPATH') || exit;

const RAOS_V2_DECISION_SUPPORT_SLUG = 'carry-on-suitcase-comparison';
const RAOS_V2_DECISION_SUPPORT_ROUTE = '/carry-on-suitcase-comparison/';
const RAOS_V2_DECISION_SUPPORT_MARKER = 'RAOS_V2_A05_POST_CONTENT_V1';
const RAOS_V2_DECISION_SUPPORT_ENVELOPE = 'RAOS_V2_A05_ENVELOPE_V1';
const RAOS_V2_DECISION_SUPPORT_VERSION = '0.6.0';
const RAOS_V2_DECISION_SUPPORT_POST_CONTENT_SHA256 = '270dfec22f4c659f30e498e321d96bf230f4f5d4504ab7f97c48f533f70f4ff5';
const RAOS_V2_DECISION_SUPPORT_BINDING_SCHEMA = 'RAOS_V2_WORDPRESS_CUTOVER_BINDING_V1';
const RAOS_V2_DECISION_SUPPORT_STATE_BLOCKED = 'BLOCKED';
const RAOS_V2_DECISION_SUPPORT_STATE_LEGACY = 'LEGACY';
const RAOS_V2_DECISION_SUPPORT_STATE_SEALED = 'SEALED';

/** Return the one exact route-bound post, otherwise null. */
function raos_v2_decision_support_target_post(): ?WP_Post
{
    if (! is_singular('post')) {
        return null;
    }
    $post = get_queried_object();
    if (! ($post instanceof WP_Post)) {
        return null;
    }
    if ($post->post_name !== RAOS_V2_DECISION_SUPPORT_SLUG) {
        return null;
    }
    $permalink = get_permalink($post);
    if (
        ! is_string($permalink)
        || wp_parse_url($permalink, PHP_URL_PATH) !== RAOS_V2_DECISION_SUPPORT_ROUTE
    ) {
        return null;
    }
    return $post;
}

/** Return a current post only when global post and get_the_ID agree exactly. */
function raos_v2_decision_support_current_content_post(): ?WP_Post
{
    global $post;
    $current_post_id = get_the_ID();
    if (
        ! ($post instanceof WP_Post)
        || ! isset($post->ID)
        || ! is_int($post->ID)
        || ! is_int($current_post_id)
        || $current_post_id !== $post->ID
    ) {
        return null;
    }
    return $post;
}

/**
 * Return the exact current target only for the singular main query's main loop.
 *
 * get_queried_object() remains request-scoped while the_content may run for a
 * secondary query or manually supplied post. Requiring all WordPress context
 * signals and exact integer IDs prevents those calls from receiving the target
 * fragment. Missing or ambiguous target context is blocked by the caller.
 */
function raos_v2_decision_support_main_content_post(): ?WP_Post
{
    $queried_post = raos_v2_decision_support_target_post();
    $current_post = raos_v2_decision_support_current_content_post();
    if (
        ! ($queried_post instanceof WP_Post)
        || ! ($current_post instanceof WP_Post)
        || ! is_main_query()
        || ! in_the_loop()
        || ! isset($queried_post->ID)
        || ! is_int($queried_post->ID)
        || $current_post->ID !== $queried_post->ID
        || $current_post->post_name !== RAOS_V2_DECISION_SUPPORT_SLUG
    ) {
        return null;
    }
    return $current_post;
}

/**
 * Read the adjacent, externally replaced cutover binding without side effects.
 *
 * DEPLOYMENT_DISABLED and every malformed or partial state fail closed. The file
 * is intentionally read for each decision so an atomic deployment replacement
 * becomes visible without an option/cache write; a partial replacement blocks.
 *
 * @return array<string, mixed>|null
 */
function raos_v2_decision_support_cutover_binding(): ?array
{
    $path = __DIR__ . '/cutover-binding.v1.json';
    clearstatcache(true, $path);
    if (! is_file($path) || is_link($path) || ! is_readable($path)) {
        return null;
    }
    $size = @filesize($path);
    if (! is_int($size) || $size < 2 || $size > 8192) {
        return null;
    }
    $raw = @file_get_contents($path);
    if (! is_string($raw) || strlen($raw) !== $size) {
        return null;
    }
    $binding = json_decode($raw, true);
    if (! is_array($binding) || json_last_error() !== JSON_ERROR_NONE) {
        return null;
    }

    $top_keys = array_keys($binding);
    sort($top_keys, SORT_STRING);
    if ($top_keys !== array('hashes', 'schema', 'state', 'target', 'version')) {
        return null;
    }
    if (! is_array($binding['target']) || ! is_array($binding['hashes'])) {
        return null;
    }
    $target_keys = array_keys($binding['target']);
    $hash_keys = array_keys($binding['hashes']);
    sort($target_keys, SORT_STRING);
    sort($hash_keys, SORT_STRING);
    if (
        $target_keys !== array('article_id', 'post_id', 'post_slug', 'route')
        || $hash_keys !== array(
            'legacy_post_content_sha256',
            'preaction_binding_sha256',
            'sealed_package_sha256',
            'sealed_post_content_sha256',
            'source_owner_export_sha256'
        )
    ) {
        return null;
    }

    $target = $binding['target'];
    $hashes = $binding['hashes'];
    if (
        $binding['schema'] !== RAOS_V2_DECISION_SUPPORT_BINDING_SCHEMA
        || $binding['version'] !== '1.0.0'
        || $binding['state'] !== 'ARMED_EXACT_LEGACY_OR_SEALED'
        || $target['article_id'] !== 'A05'
        || $target['route'] !== RAOS_V2_DECISION_SUPPORT_ROUTE
        || $target['post_slug'] !== RAOS_V2_DECISION_SUPPORT_SLUG
        || ! is_int($target['post_id'])
        || $target['post_id'] < 1
        || ! is_string($hashes['legacy_post_content_sha256'])
        || preg_match(
            '/\A[a-f0-9]{64}\z/',
            $hashes['legacy_post_content_sha256']
        ) !== 1
        || ! is_string($hashes['sealed_post_content_sha256'])
        || ! hash_equals(
            RAOS_V2_DECISION_SUPPORT_POST_CONTENT_SHA256,
            $hashes['sealed_post_content_sha256']
        )
        || hash_equals(
            $hashes['legacy_post_content_sha256'],
            $hashes['sealed_post_content_sha256']
        )
        || ! is_string($hashes['preaction_binding_sha256'])
        || preg_match(
            '/\A[a-f0-9]{64}\z/',
            $hashes['preaction_binding_sha256']
        ) !== 1
        || ! is_string($hashes['sealed_package_sha256'])
        || preg_match(
            '/\A[a-f0-9]{64}\z/',
            $hashes['sealed_package_sha256']
        ) !== 1
        || ! is_string($hashes['source_owner_export_sha256'])
        || preg_match(
            '/\A[a-f0-9]{64}\z/',
            $hashes['source_owner_export_sha256']
        ) !== 1
    ) {
        return null;
    }
    return $binding;
}

/** Classify only exact legacy or sealed raw database bytes for the bound post. */
function raos_v2_decision_support_content_state(WP_Post $post): string
{
    $binding = raos_v2_decision_support_cutover_binding();
    if (
        $binding === null
        || ! isset($post->ID)
        || ! is_int($post->ID)
        || $post->ID !== $binding['target']['post_id']
    ) {
        return RAOS_V2_DECISION_SUPPORT_STATE_BLOCKED;
    }

    $reviewed = $post->post_content;
    $database_sha256 = hash('sha256', $reviewed);
    if (
        hash_equals(
            $binding['hashes']['legacy_post_content_sha256'],
            $database_sha256
        )
    ) {
        return RAOS_V2_DECISION_SUPPORT_STATE_LEGACY;
    }

    $exact_marker = 'data-raos-v2-package-marker="'
        . RAOS_V2_DECISION_SUPPORT_MARKER
        . '"';
    if (
        hash_equals(
            $binding['hashes']['sealed_post_content_sha256'],
            $database_sha256
        )
        && substr_count($reviewed, $exact_marker) === 1
    ) {
        return RAOS_V2_DECISION_SUPPORT_STATE_SEALED;
    }
    return RAOS_V2_DECISION_SUPPORT_STATE_BLOCKED;
}

/** Bind live database content to the generator-owned, human-reviewed bytes. */
function raos_v2_decision_support_content_is_sealed(WP_Post $post): bool
{
    return raos_v2_decision_support_content_state($post)
        === RAOS_V2_DECISION_SUPPORT_STATE_SEALED;
}

/** Return one fixed response which never includes an unknown target state. */
function raos_v2_decision_support_blocked_response(): string
{
    return '<div class="raos-v2-decision-support raos-v2-decision-support--blocked" '
        . 'data-raos-v2-post-content-envelope-status="BLOCKED">'
        . '公開内容の整合性を確認できないため、この記事は表示を停止しています。'
        . '</div>';
}

/** Terminate before a later max-priority callback can mutate this response. */
function raos_v2_decision_support_enforce_final_content_filter(): bool
{
    global $wp_filter;
    if (
        ! isset($wp_filter['the_content'])
        || ! ($wp_filter['the_content'] instanceof WP_Hook)
    ) {
        return false;
    }
    $callbacks = $wp_filter['the_content']->callbacks[PHP_INT_MAX] ?? null;
    if (! is_array($callbacks) || count($callbacks) < 1) {
        return false;
    }
    $found = false;
    foreach ($callbacks as $callback) {
        if (! is_array($callback) || ! array_key_exists('function', $callback)) {
            return false;
        }
        if ($callback['function'] === 'raos_v2_decision_support_wrap_content') {
            $found = true;
            continue;
        }
        if ($found) {
            wp_die(
                '公開内容の最終整合性を確認できないため、このページを停止しました。',
                '公開内容の整合性エラー',
                array('response' => 503, 'exit' => true)
            );
            return false;
        }
    }
    if (! $found) {
        return false;
    }
    return true;
}

/** Register after normal plugin/theme setup; any later registration blocks. */
function raos_v2_decision_support_register_content_filter(): void
{
    add_filter(
        'the_content',
        'raos_v2_decision_support_wrap_content',
        PHP_INT_MAX,
        1
    );
}

/** Return true only for the exact bound and sealed A05 post. */
function raos_v2_decision_support_should_enqueue(): bool
{
    $post = raos_v2_decision_support_target_post();
    return $post instanceof WP_Post
        && raos_v2_decision_support_content_is_sealed($post);
}

/**
 * Preserve legacy filtered output or render the exact sealed raw fragment.
 *
 * WordPress default filters legitimately transform legacy content, so that
 * result is passed through only while the raw database hash is exactly bound.
 * For sealed content all earlier filter output is discarded: the exact raw
 * reviewed fragment is enclosed once and returned deterministically.
 */
function raos_v2_decision_support_wrap_content(string $content): string
{
    $queried_post = raos_v2_decision_support_target_post();
    if (! ($queried_post instanceof WP_Post)) {
        return $content;
    }

    $current_post = raos_v2_decision_support_current_content_post();
    if (
        $current_post instanceof WP_Post
        && isset($queried_post->ID)
        && is_int($queried_post->ID)
        && $current_post->ID !== $queried_post->ID
    ) {
        return $content;
    }

    if (! raos_v2_decision_support_enforce_final_content_filter()) {
        return raos_v2_decision_support_blocked_response();
    }

    $post = raos_v2_decision_support_main_content_post();
    if (! ($post instanceof WP_Post)) {
        return raos_v2_decision_support_blocked_response();
    }

    $state = raos_v2_decision_support_content_state($post);
    if ($state === RAOS_V2_DECISION_SUPPORT_STATE_LEGACY) {
        return $content;
    }
    if ($state !== RAOS_V2_DECISION_SUPPORT_STATE_SEALED) {
        return raos_v2_decision_support_blocked_response();
    }

    $envelope_open = '<div data-raos-v2-post-content-envelope="'
        . esc_attr(RAOS_V2_DECISION_SUPPORT_ENVELOPE)
        . '">';
    return $envelope_open . $post->post_content . '</div>';
}

/** Enqueue one local immutable stylesheet; make no other runtime change. */
function raos_v2_decision_support_enqueue_style(): void
{
    if (! raos_v2_decision_support_should_enqueue()) {
        return;
    }
    wp_enqueue_style(
        'raos-v2-decision-support',
        plugins_url('assets/decision-support.css', __FILE__),
        array(),
        null
    );
}

add_action(
    'template_redirect',
    'raos_v2_decision_support_register_content_filter',
    PHP_INT_MAX,
    1
);
add_action('wp_enqueue_scripts', 'raos_v2_decision_support_enqueue_style');
