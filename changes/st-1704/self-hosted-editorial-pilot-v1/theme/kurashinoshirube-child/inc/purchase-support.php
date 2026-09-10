<?php
/** Resolve only an applied immutable public document, then its bounded display metadata. */
function kurashinoshirube_purchase_support_context(): ?array
{
    if (is_admin() || !is_singular(array('post', 'page'))) { return null; }
    $post_id = (int) get_queried_object_id();
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
    wp_enqueue_style('kurashinoshirube-editorial-v2',
        get_stylesheet_directory_uri() . '/assets/editorial-v2.css',
        array('kurashinoshirube-editorial'), KURASHINOSHIRUBE_THEME_RUNTIME_REVISION);
    wp_enqueue_style('kurashinoshirube-purchase-support',
        get_stylesheet_directory_uri() . '/assets/purchase-support.css',
        array('kurashinoshirube-editorial-v2'), KURASHINOSHIRUBE_THEME_RUNTIME_REVISION);
    $asset = kurashinoshirube_verified_asset_uri('assets/purchase-support.js', KURASHINOSHIRUBE_PURCHASE_UI_SHA256, true);
    if ($asset !== null) {
        wp_enqueue_script('kurashinoshirube-purchase-support', $asset, array(),
            KURASHINOSHIRUBE_THEME_RUNTIME_REVISION, array('in_footer' => true, 'strategy' => 'defer'));
    }
    // A separate profile closes the existing Google loader even while measurement is OFF.
    kurashinoshirube_purchase_ga4_enqueue($context['bindings'] ?? array());
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
