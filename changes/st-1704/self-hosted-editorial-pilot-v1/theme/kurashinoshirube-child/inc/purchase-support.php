<?php
/** Resolve only an applied immutable public document, then its bounded display metadata. */
function kurashinoshirube_purchase_support_context(): ?array
{
    if (is_admin() || !is_singular(array('post', 'page'))) { return null; }
    $post_id = (int) get_queried_object_id();
    // The applied snapshot and the hashed runtime file do not change within one request.
    static $resolved = array();
    if (array_key_exists($post_id, $resolved)) { return $resolved[$post_id]; }
    $resolved[$post_id] = kurashinoshirube_resolve_purchase_support_context($post_id);
    return $resolved[$post_id];
}

function kurashinoshirube_resolve_purchase_support_context(int $post_id): ?array
{
    $snapshot = null;
    if (class_exists('RAOS_Codex_MCP_Owner_Direct')) {
        $snapshot = RAOS_Codex_MCP_Owner_Direct::public_article_snapshot($post_id);
    } elseif (kurashinoshirube_is_local_preview()) {
        $snapshot = get_post_meta($post_id, '_raos_owner_direct_preview_document', true);
    }
    if (!is_array($snapshot) || ($snapshot['id'] ?? null) !== $post_id
        || get_post_status($post_id) !== 'publish'
        || !in_array($snapshot['post_type'] ?? null, array('post', 'page'), true)
        || get_post_field('post_password', $post_id, 'raw') !== '') { return null; }
    foreach (array('slug' => 'post_name', 'title' => 'post_title', 'excerpt' => 'post_excerpt',
                   'block_markup' => 'post_content', 'post_type' => 'post_type') as $key => $field) {
        if (!is_string($snapshot[$key] ?? null)
            || $snapshot[$key] !== get_post_field($field, $post_id, 'raw')) { return null; }
    }
    $path = get_stylesheet_directory() . '/assets/purchase-support.v1.json';
    if (is_link($path) || !is_file($path) || filesize($path) > 262144) { return null; }
    $bytes = file_get_contents($path);
    if (!is_string($bytes) || !hash_equals(KURASHINOSHIRUBE_PURCHASE_RUNTIME_SHA256, hash('sha256', $bytes))) { return null; }
    $runtime = json_decode($bytes, true);
    if (!is_array($runtime) || ($runtime['schema'] ?? null) !== 'RAOS_PURCHASE_ARTICLE_RUNTIME_V1'
        || !is_array($runtime['articles'] ?? null)) { return null; }
    $matches = array_values(array_filter($runtime['articles'], static function ($a) use ($snapshot): bool {
        return is_array($a) && ($a['slug'] ?? null) === $snapshot['slug'];
    }));
    if (count($matches) !== 1) { return null; }
    $entry = $matches[0];
    if (($entry['post_type'] ?? null) !== $snapshot['post_type']
        || !is_string($entry['body_sha256'] ?? null)
        || !hash_equals($entry['body_sha256'], hash('sha256', $snapshot['block_markup']))) { return null; }
    return $entry;
}

function kurashinoshirube_enqueue_purchase_support(): void
{
    $context = kurashinoshirube_purchase_support_context();
    if ($context === null) {
        // A failed snapshot check must not fall back to the legacy Google loader.
        // This list can only disable collection; it never authorizes a binding.
        $slugs = array('countertop-dishwasher-for-small-households', 'lightweight-carry-on-suitcase-under-3kg',
            'compact-robot-vacuum-shortlist', 'portable-power-station-guide',
            'dishwasher-installation-measurement', 'dishwasher-water-supply-methods',
            'dishwasher-detergent-guide', 'dishwasher-cleaning-guide', 'dishwasher-running-cost',
            'kitchen', 'about-ad-policy', 'comparison-policy', 'privacy-policy');
        if (!is_admin() && is_singular(array('post', 'page'))
            && in_array(get_post_field('post_name', get_queried_object_id(), 'raw'), $slugs, true)) {
            kurashinoshirube_purchase_ga4_enqueue(array());
        }
        return;
    }
    // Only article bodies use the Editorial V2 markup; hubs and policies keep the base sheet.
    $article_kind = in_array($context['kind'] ?? null, array('comparison', 'guide'), true);
    if ($article_kind) {
        wp_enqueue_style('kurashinoshirube-editorial-v2',
            get_stylesheet_directory_uri() . '/assets/editorial-v2.css',
            array('kurashinoshirube-editorial'), KURASHINOSHIRUBE_THEME_RUNTIME_REVISION);
    }
    wp_enqueue_style('kurashinoshirube-purchase-support',
        get_stylesheet_directory_uri() . '/assets/purchase-support.css',
        array($article_kind ? 'kurashinoshirube-editorial-v2' : 'kurashinoshirube-editorial'),
        KURASHINOSHIRUBE_THEME_RUNTIME_REVISION);
    $asset = kurashinoshirube_verified_asset_uri('assets/purchase-support.js', KURASHINOSHIRUBE_PURCHASE_UI_SHA256, true);
    if ($asset !== null) {
        wp_enqueue_script('kurashinoshirube-purchase-support', $asset, array(),
            KURASHINOSHIRUBE_THEME_RUNTIME_REVISION, array('in_footer' => true, 'strategy' => 'defer'));
    }
    // A separate profile closes the existing Google loader even while measurement is OFF.
    kurashinoshirube_purchase_ga4_enqueue($context['bindings'] ?? array(),
        array('article_id' => $context['article_id'], 'snapshot_id' => $context['snapshot_id']));
    if (($context['slug'] ?? null) === 'dishwasher-running-cost') {
        $cost = kurashinoshirube_verified_asset_uri(KURASHINOSHIRUBE_LOCAL_COST_ASSET_PATH, KURASHINOSHIRUBE_LOCAL_COST_ASSET_SHA256, true);
        if ($cost !== null) {
            wp_enqueue_script('kurashinoshirube-local-running-cost', $cost, array(),
                KURASHINOSHIRUBE_THEME_RUNTIME_REVISION, array('in_footer' => true, 'strategy' => 'defer'));
        }
    }
}
add_action('wp_enqueue_scripts', 'kurashinoshirube_enqueue_purchase_support', 27);

add_filter('body_class', static function (array $classes): array {
    $context = kurashinoshirube_purchase_support_context();
    if ($context !== null && in_array($context['kind'] ?? null, array('comparison', 'guide'), true)) {
        $classes[] = 'raos-editorial-v2-page';
    }
    return array_values(array_unique($classes));
});

/** Project only the theme-hash-bound media for the exact applied public body. */
function kurashinoshirube_purchase_support_media($content)
{
    if (!is_string($content) || is_feed()) { return $content; }
    $context = kurashinoshirube_purchase_support_context();
    if ($context === null || ($context['kind'] ?? null) !== 'comparison') { return $content; }
    $media = $context['media'] ?? null;
    if (!is_array($media) || count($media) > 4) { return $content; }
    $replacements = array();
    foreach ($media as $product_id => $html) {
        if (!is_string($product_id) || preg_match('/\APRD-[A-Z0-9-]{1,100}\z/D', $product_id) !== 1
            || !is_string($html) || strlen($html) > 32768
            || !str_starts_with($html, '<figure class="ps-product-image ')
            || !str_ends_with($html, '</figure>')) { return $content; }
        $placeholder = '<div class="ps-product-media" data-ps-media-product="' . $product_id . '"></div>';
        if (substr_count($content, $placeholder) > 1) { return $content; }
        if (substr_count($content, $placeholder) === 1) {
            $replacements[$placeholder] = $html;
        }
    }
    // strtr replaces exact known placeholders once; it never re-parses source snippets.
    return strtr($content, $replacements);
}
add_filter('the_content', 'kurashinoshirube_purchase_support_media', 13);
