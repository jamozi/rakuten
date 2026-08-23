<?php
/** Local-only presentation wiring. No remote requests or write capability. */

add_action('wp_enqueue_scripts', static function (): void {
    $theme = wp_get_theme();
    wp_enqueue_style(
        'kurashinoshirube-editorial',
        get_stylesheet_directory_uri() . '/assets/theme.css',
        array(),
        $theme->get('Version')
    );
    wp_enqueue_script(
        'kurashinoshirube-editorial',
        get_stylesheet_directory_uri() . '/assets/theme.js',
        array(),
        $theme->get('Version'),
        array('in_footer' => true, 'strategy' => 'defer')
    );
});

/** Render the one packet-bound lead image without granting media-upload authority. */
function kurashinoshirube_render_first_article_lead_image(
    $attributes,
    $content,
    $tag
): string {
    if (
        $attributes !== array()
        || ! in_array($content, array(null, ''), true)
        || $tag !== 'kurashinoshirube_first_article_lead_image'
        || ! is_singular('post')
        || get_post_field('post_title', get_the_ID(), 'raw')
            !== '機内持ち込み対応スーツケース3モデルを条件別比較｜軽さ・容量・開き方で選ぶ'
        || get_post_field('post_name', get_the_ID(), 'raw')
            !== 'carry-on-suitcase-comparison'
        || get_stylesheet() !== 'kurashinoshirube-child'
    ) {
        return '';
    }

    $stylesheet_uri = untrailingslashit(get_stylesheet_directory_uri());
    $uri = wp_parse_url($stylesheet_uri);
    if (
        ! is_array($uri)
        || ($uri['scheme'] ?? null) !== 'https'
        || ($uri['host'] ?? null) !== 'kurashinoshirube.com'
        || ! isset($uri['path'])
        || ! is_string($uri['path'])
        || preg_match(
            '#\A/(?:[A-Za-z0-9][A-Za-z0-9._-]*/)*kurashinoshirube-child\z#D',
            $uri['path']
        ) !== 1
        || array_intersect_key(
            $uri,
            array_flip(array('port', 'user', 'pass', 'query', 'fragment'))
        ) !== array()
    ) {
        return '';
    }

    $image_path = untrailingslashit(get_stylesheet_directory())
        . '/assets/images/article-suitcase-guide.webp';
    if (is_link($image_path) || ! is_file($image_path) || ! is_readable($image_path)) {
        return '';
    }

    $image_uri = $stylesheet_uri . '/assets/images/article-suitcase-guide.webp';
    $alt = '機内持ち込み手荷物の寸法を考えるための抽象的な旅支度の情景';
    return '<figure class="wp-block-image size-full raos-first-article-lead-image">'
        . '<img src="' . esc_url($image_uri) . '" alt="' . esc_attr($alt)
        . '" width="1600" height="900">'
        . '</figure>';
}

add_shortcode(
    'kurashinoshirube_first_article_lead_image',
    'kurashinoshirube_render_first_article_lead_image'
);
