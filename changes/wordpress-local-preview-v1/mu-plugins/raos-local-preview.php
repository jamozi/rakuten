<?php
/**
 * Plugin Name: RAOS Local Preview Guard
 * Description: Local-only safety rails and a visible non-production banner.
 * Version: 1.0.0
 */

if (
    ! defined('RAOS_LOCAL_PREVIEW')
    || RAOS_LOCAL_PREVIEW !== true
    || ! function_exists('wp_get_environment_type')
    || wp_get_environment_type() !== 'local'
) {
    return;
}

/** Always expose the local installation as non-indexable. */
function raos_local_preview_robots(array $robots): array
{
    $robots['noindex'] = true;
    $robots['nofollow'] = true;
    $robots['noarchive'] = true;
    $robots['nosnippet'] = true;
    unset($robots['index'], $robots['follow']);
    return $robots;
}
add_filter('wp_robots', 'raos_local_preview_robots', PHP_INT_MAX);
add_filter('pre_option_blog_public', static fn () => '0', PHP_INT_MAX);
add_filter('locale', static fn () => 'ja', PHP_INT_MAX);

/** Refuse every email attempt inside the preview. */
function raos_local_preview_block_mail($return)
{
    unset($return);
    return false;
}
add_filter('pre_wp_mail', 'raos_local_preview_block_mail', PHP_INT_MAX);

/** Refuse provider, update, tracking, and arbitrary HTTP requests. */
function raos_local_preview_block_http($preempt, array $arguments, string $url)
{
    unset($preempt, $arguments, $url);
    return new WP_Error(
        'raos_local_preview_external_http_blocked',
        'External HTTP is disabled in the RAOS local preview.'
    );
}
add_filter('pre_http_request', 'raos_local_preview_block_http', PHP_INT_MAX, 3);

/** Add defense-in-depth response headers. */
function raos_local_preview_headers(): void
{
    if (! headers_sent()) {
        header('X-Robots-Tag: noindex, nofollow, noarchive, nosnippet', true);
        header('Cache-Control: no-store, max-age=0', true);
    }
}
add_action('send_headers', 'raos_local_preview_headers', PHP_INT_MAX);

/** Render a persistent visual warning before the public theme. */
function raos_local_preview_banner(): void
{
    echo '<div class="raos-local-preview-banner" role="status">'
        . esc_html('LOCAL WORDPRESS PREVIEW — 本番表示ではありません')
        . '</div>';
}
add_action('wp_body_open', 'raos_local_preview_banner', 0);

/** Keep the preview banner and synthetic placeholders legible. */
function raos_local_preview_styles(): void
{
    echo '<style id="raos-local-preview-style">'
        . '.raos-local-preview-banner{background:#702b18;color:#fff;font:700 14px/1.5 system-ui,sans-serif;padding:.65rem 1rem;text-align:center;}'
        . '.raos-local-placeholder{align-items:center;aspect-ratio:1;background:#d6dfdc;border:1px dashed #4f5b57;color:#17243f;display:flex;justify-content:center;max-width:128px;padding:.5rem;text-align:center;}'
        . '.raos-local-disabled{background:#d6dfdc;border:2px solid #4f5b57;border-radius:.35rem;color:#17243f;display:inline-block;font-weight:700;padding:.8rem 1rem;}'
        . '</style>' . "\n";
}
add_action('wp_head', 'raos_local_preview_styles', 99);

/** Make the boundary equally visible to an authenticated editor. */
function raos_local_preview_admin_notice(): void
{
    echo '<div class="notice notice-warning"><p><strong>'
        . esc_html('LOCAL WORDPRESS PREVIEW — 変更は試行用で、本番へ反映されません。')
        . '</strong></p></div>';
}
add_action('admin_notices', 'raos_local_preview_admin_notice', 0);
