<?php
/** Explicit, public-only configuration for the purchase GA4 profile. */
function kurashinoshirube_purchase_ga4_configuration(array $bindings, ?array $article = null): ?array
{
    if (!defined('RAOS_PURCHASE_GA4_ENABLED') || RAOS_PURCHASE_GA4_ENABLED !== true
        || is_user_logged_in() || (!$bindings && $article === null)) {
        return null;
    }
    $keys = array('article_id', 'product_id', 'seller_id', 'offer_id', 'cta_id', 'placement', 'snapshot_id');
    $identity = null;
    if ($article !== null) {
        if (count($article) !== 2) { return null; }
        foreach (array('article_id', 'snapshot_id') as $key) {
            if (!isset($article[$key]) || !is_string($article[$key])
                || preg_match('/\A[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}\z/D', $article[$key]) !== 1) { return null; }
        }
        $identity = array($article['article_id'], $article['snapshot_id']);
    }
    foreach ($bindings as $binding) {
        if (!is_array($binding) || count($binding) !== 8) { return null; }
        foreach ($keys as $key) {
            if (!isset($binding[$key]) || !is_string($binding[$key])
                || preg_match('/\A[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}\z/D', $binding[$key]) !== 1) { return null; }
        }
        $current = array($binding['article_id'], $binding['snapshot_id']);
        if ($identity !== null && $identity !== $current) { return null; }
        $identity = $current;
        if (!in_array($binding['placement'], array('top_summary', 'comparison_table', 'product_card', 'final_summary'), true)
            || !isset($binding['href']) || !is_string($binding['href'])
            || !filter_var($binding['href'], FILTER_VALIDATE_URL)
            || parse_url($binding['href'], PHP_URL_SCHEME) !== 'https'
            || parse_url($binding['href'], PHP_URL_USER) !== null
            || parse_url($binding['href'], PHP_URL_PASS) !== null) { return null; }
    }
    return array('profile' => 'purchase-support-v1', 'enabled' => true,
        'debug_mode' => defined('RAOS_PURCHASE_GA4_DEBUG') && RAOS_PURCHASE_GA4_DEBUG === true,
        'article' => array('article_id' => $identity[0], 'snapshot_id' => $identity[1]),
        'bindings' => array_values($bindings));
}

/** Call on purchase pages even when disabled, so their Google loader stays closed. */
function kurashinoshirube_purchase_ga4_enqueue(array $bindings, ?array $article = null): void
{
    static $installed = false;
    if ($installed) { return; }
    $installed = true;
    $configuration = kurashinoshirube_purchase_ga4_configuration($bindings, $article);
    add_filter('script_loader_tag', static function ($tag, $handle) {
        if ($handle !== 'google_gtagjs' || !is_string($tag)) { return $tag; }
        return str_replace(' data-raos-consent-gate="statistics"',
            ' data-raos-consent-gate="statistics" data-raos-analytics-profile="purchase-support-v1"', $tag);
    }, 31, 2);
    if ($configuration === null) { return; }
    $asset_uri = kurashinoshirube_verified_asset_uri(
        'assets/purchase-analytics.js', KURASHINOSHIRUBE_PURCHASE_ANALYTICS_SHA256, true
    );
    if ($asset_uri === null) { return; }
    add_action('wp_head', static function () use ($configuration): void {
        echo '<script id="raos-purchase-ga4-config" type="application/json">'
            . wp_json_encode($configuration, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT)
            . '</script>';
    }, 2);
    wp_enqueue_script('kurashinoshirube-purchase-analytics',
        $asset_uri,
        array('kurashinoshirube-analytics-consent-gate'),
        KURASHINOSHIRUBE_THEME_RUNTIME_REVISION, array('in_footer' => true));
}
