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
        header('X-Content-Type-Options: nosniff', true);
        header('Referrer-Policy: no-referrer', true);
        header('X-Frame-Options: DENY', true);
        header(
            'Permissions-Policy: accelerometer=(), autoplay=(), camera=(), '
            . 'geolocation=(), gyroscope=(), magnetometer=(), microphone=(), '
            . 'payment=(), usb=()',
            true
        );
    }
}
add_action('send_headers', 'raos_local_preview_headers', PHP_INT_MAX);

/**
 * Keep the closed fourteen-page SEO contract observable while blog_public=0.
 *
 * Yoast intentionally omits canonical presenters when WordPress globally
 * discourages indexing. This local-only plugin restores the exact validated
 * URL for the home page, ten articles, and three policy pages without changing
 * the production theme's metadata ownership.
 */
function raos_local_preview_canonical(): void
{
    if (! function_exists('kurashinoshirube_public_head_context')) {
        return;
    }
    $context = kurashinoshirube_public_head_context();
    $canonical = is_array($context) ? ($context['canonical_url'] ?? null) : null;
    if (
        ! is_string($canonical)
        || ! preg_match('#^http://127\.0\.0\.1:[0-9]{4,5}/(?:[a-z0-9-]+/)?$#D', $canonical)
    ) {
        return;
    }
    echo '<link rel="canonical" href="' . esc_url($canonical) . '" />' . "\n";
}
add_action('wp_head', 'raos_local_preview_canonical', 20);

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


/** This extension has no authority outside the loopback, non-mixed preview. */
function raos_local_reader_guides_boundary(): bool
{
    if (! defined('RAOS_LOCAL_PREVIEW') || RAOS_LOCAL_PREVIEW !== true
        || ! defined('RAOS_WORDPRESS_PREVIEW_ORIGIN') || ! is_string(RAOS_WORDPRESS_PREVIEW_ORIGIN)
        || preg_match('#\Ahttp://127\.0\.0\.1:([0-9]{4,5})\z#D', RAOS_WORDPRESS_PREVIEW_ORIGIN, $port) !== 1
        || (int) $port[1] < 1024 || (int) $port[1] > 65535
        || wp_get_environment_type() !== 'local'
        || home_url('/') !== RAOS_WORDPRESS_PREVIEW_ORIGIN . '/'
        || site_url('/') !== RAOS_WORDPRESS_PREVIEW_ORIGIN . '/') {
        return false;
    }
    return getenv('RAOS_PREVIEW_PUBLICATION_PROFILE') !== 'verified-incremental'
        && get_option('raos_mixed_preview_policy_heads_v1', null) === null;
}

/** Validate the entire ready set before any writes; blocked entries never seed. */
function raos_local_reader_guides_validate($fixture): ?array
{
    if (! is_array($fixture) || ($fixture['schema'] ?? null) !== 'RAOS_LOCAL_READER_GUIDES_V1'
        || ($fixture['publication_authority'] ?? null) !== false
        || ! is_array($fixture['articles'] ?? null) || ! array_is_list($fixture['articles'])
        || count($fixture['articles']) > 5
        || ! is_array($fixture['blocked'] ?? null) || ! array_is_list($fixture['blocked'])) {
        return null;
    }
    $keys = array_keys($fixture);
    sort($keys);
    if ($keys !== array('articles', 'blocked', 'publication_authority', 'schema')) { return null; }
    $articles = array();
    $slugs = array();
    // Read the original navigation directly: article_bindings itself asks for hub labels.
    $fixed_rows = function_exists('kurashinoshirube_editorial_navigation')
        ? (kurashinoshirube_editorial_navigation()['articles'] ?? array()) : array();
    $fixed = array_column($fixed_rows, null, 'article_id');
    foreach ($fixture['articles'] as $article) {
        if (! is_array($article)) { return null; }
        $keys = array_keys($article);
        sort($keys);
        if ($keys !== array('article_id', 'article_type', 'category', 'checked_at', 'content_sha256',
            'dek', 'html', 'local_slug', 'purposes', 'title')) { return null; }
        foreach (array('article_id', 'local_slug', 'title', 'dek', 'html', 'content_sha256', 'checked_at') as $key) {
            if (! is_string($article[$key] ?? null) || trim($article[$key]) === '' || str_contains($article[$key], "\0")) {
                return null;
            }
        }
        $id = $article['article_id'];
        $slug = $article['local_slug'];
        $html = $article['html'];
        if (preg_match('/\A[A-Za-z0-9][A-Za-z0-9_-]*\z/D', $id) !== 1 || strlen($id) > 160
            || preg_match('/\Alocal-preview-[a-z0-9]+(?:-[a-z0-9]+)*\z/D', $slug) !== 1 || strlen($slug) > 190
            || isset($articles[$id]) || isset($slugs[$slug]) || isset($fixed[$id])
            || in_array($slug, array_column($fixed, 'local_slug'), true)
            || ($article['article_type'] ?? null) !== 'guide' || ($article['category'] ?? null) !== 'kitchen'
            || ! is_array($article['purposes'] ?? null) || ! array_is_list($article['purposes'])
            || count($article['purposes']) > 16
            || strlen($article['title']) > 2000 || strlen($article['dek']) > 10000
            || wp_strip_all_tags($article['title']) !== $article['title']
            || wp_strip_all_tags($article['dek']) !== $article['dek']
            || strlen($html) > 1048576 || wp_kses_post($html) !== $html
            || preg_match('/<\s*(?:h1|script|style|iframe|img|video|audio)\b/i', $html)
            || ! str_starts_with($html, '<div class="raos-editorial-v2">')
            || substr_count($html, '<div class="raos-editorial-v2">') !== 1
            || ! str_ends_with(rtrim($html), '</div>')
            || substr_count($html, 'data-raos-article-id=') !== 1
            || ! str_contains($html, 'data-raos-article-id="' . $id . '"')
            || preg_match('/\A[a-f0-9]{64}\z/D', $article['content_sha256']) !== 1
            || ! hash_equals($article['content_sha256'], hash('sha256', $html))
            || preg_match('/\A([0-9]{4})-([0-9]{2})-([0-9]{2})\z/D', $article['checked_at'], $date) !== 1
            || ! checkdate((int) $date[2], (int) $date[3], (int) $date[1])
            || $article['checked_at'] > gmdate('Y-m-d')) {
            return null;
        }
        $purposes = array();
        foreach ($article['purposes'] as $purpose) {
            if (! is_string($purpose) || preg_match('/\A[a-z]+(?:-[a-z]+)*\z/D', $purpose) !== 1
                || isset($purposes[$purpose])) { return null; }
            $purposes[$purpose] = true;
        }
        $articles[$id] = $article;
        $slugs[$slug] = true;
    }
    $blocked = array();
    foreach ($fixture['blocked'] as $row) {
        $id = is_array($row) ? ($row['article_id'] ?? null) : null;
        if (! is_string($id) || $id === '' || isset($articles[$id]) || isset($blocked[$id])) { return null; }
        $blocked[$id] = true;
    }
    return $articles;
}

/** One mounted fixture, with no path discovery or database content matching. */
function raos_local_reader_guides_fixture(): ?array
{
    $path = '/var/www/raos-local-preview/fixtures/reader-guides.v1.json';
    if (! raos_local_reader_guides_boundary() || ! is_file($path) || is_link($path) || ! is_readable($path)
        || filesize($path) > 6291456) { return null; }
    $bytes = file_get_contents($path);
    if (! is_string($bytes)) { return null; }
    // Revalidate only when mounted bytes change, including within the same CLI request.
    static $previous_bytes = null;
    static $validated = null;
    if ($bytes !== $previous_bytes) {
        $validated = raos_local_reader_guides_validate(json_decode($bytes, true, 32));
        $previous_bytes = $bytes;
    }
    return $validated;
}

function raos_local_reader_guide_metadata(array $article): array
{
    $metadata = array('schema' => 'RAOS_LOCAL_READER_GUIDE_POST_V1', 'publication_authority' => false);
    foreach (array('article_id', 'local_slug', 'article_type', 'title', 'dek', 'category', 'purposes', 'content_sha256', 'checked_at') as $key) {
        $metadata[$key] = $article[$key];
    }
    return $metadata;
}

/** Saved IDs are the only ownership authority; a slug alone never grants a write. */
function raos_local_reader_guides_bindings(): array
{
    $rows = get_option('raos_local_reader_guide_posts_v1', array());
    if (! is_array($rows)) { return array(); }
    $valid = array();
    foreach ($rows as $id => $row) {
        if (is_string($id) && is_array($row) && is_int($row['post_id'] ?? null) && $row['post_id'] > 0
            && is_array($row['metadata'] ?? null) && ($row['metadata']['article_id'] ?? null) === $id
            && ($row['metadata']['schema'] ?? null) === 'RAOS_LOCAL_READER_GUIDE_POST_V1'
            && ($row['metadata']['publication_authority'] ?? null) === false) {
            $valid[$id] = $row;
        }
    }
    return $valid;
}

function raos_local_reader_guide_post_matches(int $post_id, array $metadata): bool
{
    $post = get_post($post_id);
    return $post instanceof WP_Post && $post->post_type === 'post' && $post->post_status === 'publish'
        && $post->post_password === '' && $post->post_name === ($metadata['local_slug'] ?? null)
        && $post->post_title === ($metadata['title'] ?? null) && $post->post_excerpt === ($metadata['dek'] ?? null)
        && hash('sha256', $post->post_content) === ($metadata['content_sha256'] ?? null)
        && get_post_meta($post_id, '_raos_local_reader_guide_v1', true) === $metadata
        && get_permalink($post) === RAOS_WORDPRESS_PREVIEW_ORIGIN . '/' . $post->post_name . '/';
}

function raos_local_reader_guide_identity(int $post_id): ?array
{
    if (! raos_local_reader_guides_boundary() || get_option('raos_local_reader_guides_enabled_v1') !== '1') { return null; }
    $articles = raos_local_reader_guides_fixture();
    foreach (raos_local_reader_guides_bindings() as $id => $binding) {
        if ($binding['post_id'] !== $post_id || ! isset($articles[$id])) { continue; }
        $metadata = raos_local_reader_guide_metadata($articles[$id]);
        if ($binding['metadata'] !== $metadata || ! raos_local_reader_guide_post_matches($post_id, $metadata)) { return null; }
        return array('article_id' => $id, 'section' => 'キッチン・家事', 'slug' => $metadata['local_slug']);
    }
    return null;
}

function raos_local_reader_guide_posts(array $article_ids): array
{
    if (! raos_local_reader_guides_boundary()) { return array(); }
    $posts = array();
    foreach (raos_local_reader_guides_bindings() as $id => $binding) {
        if (in_array($id, $article_ids, true) && raos_local_reader_guide_identity($binding['post_id']) !== null) {
            $posts[] = get_post($binding['post_id']);
        }
    }
    return $posts;
}

/** Return null for unrelated posts so the prior public predicate still decides. */
function raos_local_reader_guide_listing_eligibility(int $post_id, string $slug): ?bool
{
    if (! raos_local_reader_guides_boundary()) { return null; }
    $known = false;
    foreach (raos_local_reader_guides_bindings() as $binding) {
        $known = $known || $binding['post_id'] === $post_id || ($binding['metadata']['local_slug'] ?? null) === $slug;
    }
    foreach (raos_local_reader_guides_fixture() ?? array() as $article) {
        $known = $known || $article['local_slug'] === $slug;
    }
    return $known ? (raos_local_reader_guide_identity($post_id)['slug'] ?? null) === $slug : null;
}

/** Exact IDs are checked separately from the unchanged twenty-row portfolio query. */
function raos_local_reader_guide_listing_ids(): array
{
    if (! raos_local_reader_guides_boundary()) { return array(); }
    return array_values(array_unique(array_column(raos_local_reader_guides_bindings(), 'post_id')));
}

function raos_local_reader_guide_hubs(array $hubs): array
{
    if (! raos_local_reader_guides_boundary()) { return $hubs; }
    $articles = raos_local_reader_guides_fixture() ?? array();
    $posts = raos_local_reader_guide_posts(array_keys($articles));
    $eligible = array_column($posts, 'ID');
    $bindings = raos_local_reader_guides_bindings();
    foreach ($hubs as &$hub) {
        foreach ($articles as $id => $article) {
            if (! in_array($bindings[$id]['post_id'] ?? null, $eligible, true)) { continue; }
            if (in_array($hub['kind'], array('categories', 'purposes', 'updates'), true)
                || ($hub['kind'] === 'collection' && $hub['slug'] === 'guides')
                || ($hub['kind'] === 'category' && $hub['slug'] === $article['category'])
                || ($hub['kind'] === 'purpose' && in_array($hub['slug'], $article['purposes'], true))) {
                $hub['article_ids'] = array_values(array_unique(array_merge($hub['article_ids'], array($id))));
            }
        }
    }
    unset($hub);
    return $hubs;
}

/** Seed only locally generated IDs after preflighting every foreign-slug conflict. */
function raos_local_reader_guides_seed(array $articles, int $author_id): int
{
    if (! defined('WP_CLI') || WP_CLI !== true || ! raos_local_reader_guides_boundary() || $author_id <= 0
        || raos_local_reader_guides_validate(array('schema' => 'RAOS_LOCAL_READER_GUIDES_V1',
            'publication_authority' => false, 'articles' => array_values($articles), 'blocked' => array())) !== $articles) {
        WP_CLI::error('RAOS_LOCAL_READER_GUIDES_SEED_BOUNDARY_INVALID');
    }
    $bindings = raos_local_reader_guides_bindings();
    foreach ($articles as $id => $article) {
        $binding = $bindings[$id] ?? null;
        $post_id = $binding['post_id'] ?? 0;
        $existing = get_page_by_path($article['local_slug'], OBJECT, array('post', 'page', 'attachment'));
        if (($existing instanceof WP_Post && (int) $existing->ID !== $post_id)
            || ($post_id > 0 && ! raos_local_reader_guide_post_matches($post_id, $binding['metadata']))
            || ($post_id > 0 && $binding['metadata']['local_slug'] !== $article['local_slug'])
            || wp_unique_post_slug($article['local_slug'], $post_id, 'publish', 'post', 0) !== $article['local_slug']) {
            WP_CLI::error('RAOS_LOCAL_READER_GUIDES_FOREIGN_OR_CHANGED_POST');
        }
    }
    if ($articles !== array()) {
        $term = term_exists('kitchen', 'category');
        if (! $term) { $term = wp_insert_term('キッチン・家事', 'category', array('slug' => 'kitchen')); }
        if (is_wp_error($term)) { WP_CLI::error('RAOS_LOCAL_READER_GUIDES_CATEGORY_FAILED'); }
        $category_id = is_array($term) ? (int) $term['term_id'] : (int) $term;
        if ($category_id <= 0) { WP_CLI::error('RAOS_LOCAL_READER_GUIDES_CATEGORY_FAILED'); }
    }
    foreach ($articles as $id => $article) {
        $data = array('post_type' => 'post', 'post_status' => 'publish', 'post_name' => $article['local_slug'],
            'post_title' => $article['title'], 'post_excerpt' => $article['dek'], 'post_content' => $article['html'],
            'post_author' => $author_id, 'post_category' => array($category_id), 'post_password' => '',
            'comment_status' => 'closed', 'ping_status' => 'closed');
        if (isset($bindings[$id])) { $data['ID'] = $bindings[$id]['post_id']; }
        $result = wp_insert_post(wp_slash($data), true);
        if (is_wp_error($result) || (int) $result <= 0) { WP_CLI::error('RAOS_LOCAL_READER_GUIDES_INSERT_FAILED'); }
        $post_id = (int) $result;
        $metadata = raos_local_reader_guide_metadata($article);
        update_post_meta($post_id, '_raos_local_reader_guide_v1', wp_slash($metadata));
        if (! raos_local_reader_guide_post_matches($post_id, $metadata)) { WP_CLI::error('RAOS_LOCAL_READER_GUIDES_READBACK_FAILED'); }
        $bindings[$id] = array('post_id' => $post_id, 'metadata' => $metadata);
        update_option('raos_local_reader_guide_posts_v1', $bindings, false);
        if (get_option('raos_local_reader_guide_posts_v1') !== $bindings) { WP_CLI::error('RAOS_LOCAL_READER_GUIDES_BINDING_FAILED'); }
    }
    update_option('raos_local_reader_guides_enabled_v1', '1', false);
    return count($articles);
}

/** Counts remain separate from the fixed ten publication fixtures. */
function raos_local_reader_guide_count(): int
{
    return count(raos_local_reader_guide_posts(array_keys(raos_local_reader_guides_fixture() ?? array())));
}


/** Add bounded next steps at authored decision/purchase headings, without changing stored HTML. */
function raos_local_reader_guide_contextual_links(string $content): string
{
    if (! raos_local_reader_guides_boundary() || ! is_singular('post') || ! in_the_loop() || ! is_main_query()
        || ! function_exists('kurashinoshirube_local_preview_article_identity')
        || str_contains($content, 'data-raos-local-reader-related=')) { return $content; }
    $post_id = (int) get_the_ID();
    if ($post_id !== (int) get_queried_object_id() || $content !== get_post_field('post_content', $post_id, 'raw')) {
        return $content;
    }
    $identity = kurashinoshirube_local_preview_article_identity($post_id);
    if ($identity === null || get_permalink($post_id) !== RAOS_WORDPRESS_PREVIEW_ORIGIN . '/' . $identity['slug'] . '/') {
        return $content;
    }
    $contexts = array(
        'st1704-countertop-dishwasher-for-small-households' => array(
            'headings' => array('reader-axes-title', 'reader-purchase-checklist-title', 'blk-dish-005-title'),
            'targets' => array('dishwasher-installation-measurement', 'dishwasher-water-supply-methods', 'dishwasher-running-cost'),
        ),
        'solota-vs-rakua-mini-plus' => array(
            'headings' => array('reader-purchase-checklist-title', 'dish-purchase-check-title'),
            'targets' => array('dishwasher-installation-measurement', 'dishwasher-detergent-guide', 'dishwasher-cleaning-guide'),
        ),
    );
    $context = $contexts[$identity['article_id']] ?? null;
    if ($context === null) { return $content; }
    $items = array();
    $articles = raos_local_reader_guides_fixture() ?? array();
    $bindings = raos_local_reader_guides_bindings();
    foreach ($context['targets'] as $id) {
        $target_id = $bindings[$id]['post_id'] ?? 0;
        if (! isset($articles[$id]) || raos_local_reader_guide_identity($target_id) === null) { continue; }
        $items[] = '<li><a href="' . esc_url(get_permalink($target_id)) . '">' . esc_html($articles[$id]['title']) . '</a></li>';
    }
    if (count($items) < 2) { return $content; }
    $links = '<aside class="raos-contextual-link" data-raos-local-reader-related="v1" aria-label="条件を詳しく確認する">'
        . '<p>気になる条件を、購入前にもう少し詳しく確認する</p><ul>' . implode('', $items) . '</ul></aside>';
    $pattern = '#(<h2\b[^>]*\bid="(?:' . implode('|', $context['headings']) . ')"[^>]*>.*?</h2>)#s';
    return preg_replace_callback($pattern, static fn (array $match): string => $match[0] . $links, $content, 1) ?? $content;
}
add_filter('the_content', 'raos_local_reader_guide_contextual_links', 9);
