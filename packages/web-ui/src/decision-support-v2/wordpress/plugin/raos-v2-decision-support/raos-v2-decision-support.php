<?php
/**
 * Plugin Name: RAOS V2 Decision Support Presentation
 * Description: Route-scoped presentation styles for the sealed A05 WordPress payload.
 * Version: 0.1.0
 * Requires PHP: 7.4
 * License: Proprietary
 *
 * This plugin performs no remote request, write, publication, telemetry, option,
 * cron, REST, or admin action. For one exact route and package marker it enqueues
 * bundled CSS and wraps the unchanged reviewed fragment in a verification
 * envelope. Any content-filter drift renders a fixed blocked message.
 */

defined('ABSPATH') || exit;

const RAOS_V2_DECISION_SUPPORT_SLUG = 'carry-on-suitcase-comparison';
const RAOS_V2_DECISION_SUPPORT_ROUTE = '/carry-on-suitcase-comparison/';
const RAOS_V2_DECISION_SUPPORT_MARKER = 'RAOS_V2_A05_POST_CONTENT_V1';
const RAOS_V2_DECISION_SUPPORT_ENVELOPE = 'RAOS_V2_A05_ENVELOPE_V1';
const RAOS_V2_DECISION_SUPPORT_VERSION = '0.1.0';
const RAOS_V2_DECISION_SUPPORT_POST_CONTENT_SHA256 = '270dfec22f4c659f30e498e321d96bf230f4f5d4504ab7f97c48f533f70f4ff5';

/** Return the one exact route-bound, marker-bound post, otherwise null. */
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

/** Bind live database content to the generator-owned, human-reviewed bytes. */
function raos_v2_decision_support_content_is_sealed(WP_Post $post): bool
{
    $reviewed = trim($post->post_content);
    $exact_marker = 'data-raos-v2-package-marker="'
        . RAOS_V2_DECISION_SUPPORT_MARKER
        . '"';
    return substr_count($reviewed, $exact_marker) === 1
        && hash_equals(
            RAOS_V2_DECISION_SUPPORT_POST_CONTENT_SHA256,
            hash('sha256', $reviewed)
        );
}

/** Return true only for the one route-bound, marker-bound A05 post. */
function raos_v2_decision_support_should_enqueue(): bool
{
    return raos_v2_decision_support_target_post() instanceof WP_Post;
}

/**
 * Wrap only the byte-equivalent reviewed fragment after normal content filters.
 *
 * A second application returns the exact same envelope. A target-route filter
 * mutation never renders the mutated candidate and never gains a valid envelope.
 */
function raos_v2_decision_support_wrap_content(string $content): string
{
    $post = raos_v2_decision_support_target_post();
    if (! ($post instanceof WP_Post)) {
        return $content;
    }

    if (! raos_v2_decision_support_content_is_sealed($post)) {
        return '<div class="raos-v2-decision-support raos-v2-decision-support--blocked" '
            . 'data-raos-v2-post-content-envelope-status="BLOCKED">'
            . '公開内容の整合性を確認できないため、この記事は表示を停止しています。'
            . '</div>';
    }

    $envelope_open = '<div data-raos-v2-post-content-envelope="'
        . esc_attr(RAOS_V2_DECISION_SUPPORT_ENVELOPE)
        . '">';
    $envelope_close = '</div>';
    // Core may add boundary whitespace; substantive or markup drift still blocks.
    $reviewed = trim($post->post_content);
    $candidate = trim($content);
    $already_wrapped = $envelope_open . $reviewed . $envelope_close;
    if ($candidate === $already_wrapped) {
        return $already_wrapped;
    }

    $expected_root = '<div class="raos-v2-decision-support"';
    $envelope_attribute = 'data-raos-v2-post-content-envelope=';
    if (
        $candidate !== $reviewed
        || strpos($reviewed, $expected_root) !== 0
        || substr($reviewed, -strlen($envelope_close)) !== $envelope_close
        || strpos($reviewed, $envelope_attribute) !== false
    ) {
        return '<div class="raos-v2-decision-support raos-v2-decision-support--blocked" '
            . 'data-raos-v2-post-content-envelope-status="BLOCKED">'
            . '公開内容の整合性を確認できないため、この記事は表示を停止しています。'
            . '</div>';
    }

    return $envelope_open . $reviewed . $envelope_close;
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

add_action('wp_enqueue_scripts', 'raos_v2_decision_support_enqueue_style');
add_filter(
    'the_content',
    'raos_v2_decision_support_wrap_content',
    PHP_INT_MAX,
    1
);
