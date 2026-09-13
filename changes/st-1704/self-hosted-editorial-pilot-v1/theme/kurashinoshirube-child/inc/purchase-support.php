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
    // Explicitly registered comparison rows can include up to 32 products.
    // Keep a bounded payload while retaining the exact asset/snapshot hashes.
    if (is_link($path) || !is_file($path) || filesize($path) > 1048576) { return null; }
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
            'kitchen', 'about-ad-policy', 'comparison-policy', 'privacy-policy',
            'carry-on-suitcase-comparison', 'carry-on-suitcase-under-100-seats',
            'front-open-carry-on-suitcase-with-stopper', 'solota-vs-rakua-mini-plus',
            'roomba-mini-vs-switchbot-k11-pro', 'anker-solix-c300-c800-c1000-differences',
            'compact-dishwasher-comparison');
        if (!is_admin() && is_singular(array('post', 'page'))
            && in_array(get_post_field('post_name', get_queried_object_id(), 'raw'), $slugs, true)) {
            kurashinoshirube_purchase_ga4_enqueue(array());
        }
        return;
    }
    // Only article bodies use the Editorial V2 markup; hubs and policies keep the base sheet.
    $article_kind = in_array($context['kind'] ?? null, array('comparison', 'guide', 'curated_comparison'), true);
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
    if ($context !== null && in_array($context['kind'] ?? null, array('comparison', 'guide', 'curated_comparison'), true)) {
        $classes[] = 'raos-editorial-v2-page';
    }
    return array_values(array_unique($classes));
});

/** Project only the theme-hash-bound media for the exact applied public body. */
function kurashinoshirube_purchase_support_media($content)
{
    if (!is_string($content) || is_feed()) { return $content; }
    $context = kurashinoshirube_purchase_support_context();
    if ($context === null || !in_array($context['kind'] ?? null, array('comparison', 'guide', 'curated_comparison'), true)) { return $content; }
    $media = $context['media'] ?? null;
    $maximum = ($context['kind'] ?? null) === 'curated_comparison' ? 32 : 4;
    if (!is_array($media) || count($media) > $maximum) { return $content; }
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
    $conditions = $context['condition_media'] ?? array();
    if (!is_array($conditions) || count($conditions) > 32) { return $content; }
    foreach ($conditions as $identity => $entry) {
        if (!is_array($entry)) { return $content; }
        $product_id = $entry['product_id'] ?? null;
        $condition_id = $entry['condition_id'] ?? null;
        $html = $entry['html'] ?? null;
        if (!is_string($product_id) || !array_key_exists($product_id, $media)
            || !is_string($condition_id) || preg_match('/\A[a-z0-9-]{1,32}\z/D', $condition_id) !== 1
            || $identity !== $condition_id . '--' . $product_id
            || !is_string($html) || strlen($html) > 32768
            || !str_starts_with($html, '<figure class="ps-product-image ')
            || !str_ends_with($html, '</figure>')) { return $content; }
        $placeholder = '<div class="ps-condition-product-media" data-ps-media-product="' . $product_id . '" data-ps-condition="' . $condition_id . '"></div>';
        if (substr_count($content, $placeholder) > 1) { return $content; }
        if (substr_count($content, $placeholder) === 1) { $replacements[$placeholder] = $html; }
    }
    // strtr replaces exact known placeholders once; it never re-parses source snippets.
    return strtr($content, $replacements);
}
add_filter('the_content', 'kurashinoshirube_purchase_support_media', 13);

/** Home-only media uses the same applied-document boundary as article media. */
function kurashinoshirube_home_product_media($content)
{
    if (!is_string($content) || is_admin() || is_feed() || !is_front_page()
        ) { return $content; }
    $post_id = 15;
    $local_preview = kurashinoshirube_is_local_preview() && !class_exists('RAOS_Codex_MCP_Owner_Direct');
    if ($local_preview) { $post_id = (int) get_option('page_on_front'); }
    if ($post_id <= 0 || (int) get_queried_object_id() !== $post_id
        || (int) get_the_ID() !== $post_id) { return $content; }
    $snapshot = null;
    if (class_exists('RAOS_Codex_MCP_Owner_Direct')) {
        $snapshot = RAOS_Codex_MCP_Owner_Direct::public_article_snapshot(15);
    } elseif ($local_preview) {
        $snapshot = get_post_meta($post_id, '_raos_owner_direct_preview_document', true);
    }
    if (!is_array($snapshot) || ($snapshot['id'] ?? null) !== $post_id
        || ($snapshot['post_type'] ?? null) !== 'page' || ($snapshot['slug'] ?? null) !== 'home'
        || get_post_status($post_id) !== 'publish' || get_post_field('post_password', $post_id, 'raw') !== '') {
        return $content;
    }
    foreach (array('slug' => 'post_name', 'title' => 'post_title', 'excerpt' => 'post_excerpt',
                   'block_markup' => 'post_content', 'post_type' => 'post_type') as $key => $field) {
        if (!is_string($snapshot[$key] ?? null)
            || $snapshot[$key] !== get_post_field($field, $post_id, 'raw')) { return $content; }
    }
    $path = get_stylesheet_directory() . '/assets/site-editorial-metadata.v1.json';
    if (is_link($path) || !is_file($path) || !is_readable($path) || filesize($path) > 262144) {
        return $content;
    }
    $bytes = file_get_contents($path);
    if (!is_string($bytes) || !hash_equals(KURASHINOSHIRUBE_SITE_EDITORIAL_METADATA_SHA256, hash('sha256', $bytes))) {
        return $content;
    }
    $document = json_decode($bytes, true);
    $media = is_array($document) ? ($document['home_product_media'] ?? null) : null;
    if (($document['schema'] ?? null) !== 'RAOS_SITE_EDITORIAL_METADATA_V1'
        || !is_array($media) || ($media['schema'] ?? null) !== 'RAOS_HOME_PRODUCT_MEDIA_V1'
        || ($media['post_id'] ?? null) !== 15 || ($media['post_type'] ?? null) !== 'page'
        || ($media['slug'] ?? null) !== 'home' || !is_string($media['body_sha256'] ?? null)
        || !hash_equals($media['body_sha256'], hash('sha256', $snapshot['block_markup']))
        || !is_array($media['products'] ?? null)) { return $content; }
    $expected = array(
        'PRD-PANASONIC-NP-TMLK1' => 'NP-TMLK1-K',
        'PRD-SIROCA-SS-MA251' => 'SS-MA251',
        'PRD-PROTECA-AEROFLEX-DX2-01521' => '01521-09',
        'PRD-SAMSONITE-C-LITE-CS2-09007' => 'CS2*09007 / 134679-1041',
        'PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY' => 'F155260',
        'PRD-SWITCHBOT-K11-PRO' => 'K11+ Pro',
    );
    if (count($media['products']) !== count($expected)
        || array_diff_key($expected, $media['products']) !== array()
        || array_diff_key($media['products'], $expected) !== array()) { return $content; }
    if (substr_count($content, 'class="ks-home-product-slot"') !== count($expected)) { return $content; }
    $replacements = array();
    foreach ($expected as $pid => $model) {
        $product = $media['products'][$pid];
        if (!is_array($product) || ($product['exact_model'] ?? null) !== $model
            || !is_string($product['html'] ?? null) || strlen($product['html']) > 16384
            || !is_string($product['sha256'] ?? null)
            || !hash_equals($product['sha256'], hash('sha256', $product['html']))
            || !str_starts_with($product['html'], '<figure class="ks-home-product-image" data-ks-home-product="' . $pid . '">')
            || !str_ends_with($product['html'], '</figure>')
            || !is_array($product['source_sha256'] ?? null)) { return $content; }
        $source_key = $pid === 'PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY' ? 'official' : '240';
        if (count($product['source_sha256']) !== 1 || !array_key_exists($source_key, $product['source_sha256'])
            || !is_string($product['source_sha256'][$source_key])
            || preg_match('/\A[0-9a-f]{64}\z/D', $product['source_sha256'][$source_key]) !== 1) { return $content; }
        $placeholder = '<div class="ks-home-product-slot" data-ks-home-product="' . $pid . '"></div>';
        if (substr_count($content, $placeholder) !== 1) { return $content; }
        $replacements[$placeholder] = $product['html'];
    }
    return strtr($content, $replacements);
}
add_filter('the_content', 'kurashinoshirube_home_product_media', 14);
