<?php

if (! defined('WP_CLI') || ! WP_CLI) {
    exit(1);
}

$action = isset($args[0]) && is_string($args[0]) ? $args[0] : '';
$wpseo = array(
    'enable_ai_generator' => false,
    'enable_headless_rest_endpoints' => false,
    'enable_index_now' => false,
    'enable_schema' => false,
    'enable_schema_aggregation_endpoint' => false,
    'enable_xml_sitemap' => true,
    'google_site_kit_feature_enabled' => false,
    'googleverify' => '',
    'semrush_integration_active' => false,
    'tracking' => false,
    'wincher_integration_active' => false,
);
$wpseo_social = array(
    'og_default_image' => home_url(
        '/wp-content/themes/kurashinoshirube-child/assets/images/home-hero.webp'
    ),
    'og_default_image_id' => '',
    'opengraph' => true,
    'twitter' => true,
    'twitter_card_type' => 'summary_large_image',
);

if ('seed' === $action) {
    $current_wpseo = get_option('wpseo', array());
    $current_social = get_option('wpseo_social', array());
    update_option(
        'wpseo',
        array_replace(is_array($current_wpseo) ? $current_wpseo : array(), $wpseo),
        false
    );
    update_option(
        'wpseo_social',
        array_replace(is_array($current_social) ? $current_social : array(), $wpseo_social),
        false
    );
} elseif ('check-gates' === $action) {
    $status = RAOS_Codex_MCP_Content::yoast_status();
    if ($status !== array(
        'plugin_slug' => 'wordpress-seo',
        'installed' => true,
        'active' => true,
        'version' => '28.3',
        'version_exact' => true,
        'options' => array(
            'wpseo' => $wpseo,
            'wpseo_social' => $wpseo_social,
        ),
        'settings_fingerprint' => '907f32107299b0fb8154cdedc87ed20d18ab0b92c2aa3704516c8f44085ca5b9',
        'settings_exact' => true,
    )) {
        WP_CLI::error('RAOS_WORDPRESS_E2E_YOAST_STATUS_INVALID');
    }
    $apply_gate = new ReflectionMethod(RAOS_Codex_MCP_Deployment::class, 'apply_gate');
    $before = get_option('wpseo', null);
    $drifted = is_array($before) ? $before : array();
    $drifted['tracking'] = true;
    update_option('wpseo', $drifted, false);
    try {
        $exact_gate = RAOS_Codex_MCP_Content::exact_yoast_gate();
        if (! is_wp_error($exact_gate)
            || 'raos_codex_yoast_configuration_drift' !== $exact_gate->get_error_code()) {
            WP_CLI::error('RAOS_WORDPRESS_E2E_YOAST_EXACT_GATE_NOT_CLOSED');
        }
        foreach (array('CONTENT_RELEASE', 'THEME_RELEASE') as $kind) {
            $result = $apply_gate->invoke(null, $kind);
            if (! is_wp_error($result)
                || 'raos_codex_yoast_configuration_drift' !== $result->get_error_code()) {
                WP_CLI::error('RAOS_WORDPRESS_E2E_YOAST_APPLY_GATE_NOT_CLOSED');
            }
        }
        if (true !== $apply_gate->invoke(null, 'PLUGIN_CHANGE')) {
            WP_CLI::error('RAOS_WORDPRESS_E2E_PLUGIN_BOOTSTRAP_GATE_BLOCKED');
        }
    } finally {
        update_option('wpseo', $before, false);
    }
    if (true !== RAOS_Codex_MCP_Content::exact_yoast_gate()) {
        WP_CLI::error('RAOS_WORDPRESS_E2E_YOAST_GATE_RESTORE_FAILED');
    }
} else {
    WP_CLI::error('RAOS_WORDPRESS_E2E_YOAST_ACTION_INVALID');
}

WP_CLI::success('RAOS_WORDPRESS_E2E_YOAST_' . strtoupper(str_replace('-', '_', $action)));
