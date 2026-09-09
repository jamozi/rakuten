<?php
/** Editorial photographs supplied in iRobot Japan's publication media kit.
 * See changes/wordpress-direct-publish-v1/official-media-sources.md.
 * No remote fetch, merchant-link change, or claim about availability.
 */
function kurashinoshirube_official_product_media(string $content, string $slug): string
{
    if (!in_array($slug, array('compact-robot-vacuum-shortlist', 'roomba-mini-vs-switchbot-k11-pro'), true)) {
        return $content;
    }
    $photos = array(
        'PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY' => array(
            'roomba-mini-official.jpg', 2048, 2048,
            'アイロボット Roomba® Mini 掃除機＆床拭きロボット + AutoEmpty™ 充電ステーション',
            'Roomba Mini（白）とAutoEmpty充電ステーション。公式提供写真。',
        ),
        'PRD-IROBOT-ROOMBA-MINI-SLIM-F115060' => array(
            'roomba-mini-slim-official.jpg', 2048, 1152,
            'アイロボット Roomba® Mini Slim 掃除機＆床拭きロボット + SlimCharge™ 充電スタンド',
            'Roomba Mini Slim（白）とSlimCharge充電スタンド。公式提供写真。',
        ),
    );
    return preg_replace_callback('/<article\b[^>]*>.*?<\/article>/s', static function ($match) use ($photos) {
        $article = $match[0];
        $opening = substr($article, 0, strpos($article, '>') + 1);
        if (!preg_match('/\bdata-raos-product-id="([A-Z0-9-]+)"/', $opening, $identity)
            || !isset($photos[$identity[1]]) || str_contains($article, 'raos-official-product-photo')) {
            return $article;
        }
        $photo = $photos[$identity[1]];
        if (!is_file(get_stylesheet_directory() . '/assets/images/' . $photo[0])) {
            return $article;
        }
        $figure = '<figure class="raos-product-card__media raos-official-product-photo">'
            . '<img src="' . esc_url(get_stylesheet_directory_uri() . '/assets/images/' . $photo[0])
            . '" width="' . $photo[1] . '" height="' . $photo[2] . '" loading="lazy" decoding="async"'
            . ' alt="' . esc_attr($photo[4]) . '">'
            . '<figcaption>' . esc_html($photo[3])
            . '<br>写真：<a href="https://irobotjp.mediaroom.com/media-kits?item=28">'
            . 'アイロボットジャパン 公式掲載用素材</a></figcaption></figure>';
        // Replace only the media preceding the existing product description.
        $pattern = '/\A(<article\b[^>]*>)\s*(?:<figure\b[^>]*>.*?<\/figure>|<div class="raos-product-card__media">.*?<\/div>|<!-- 商品写真は未掲載 -->)?\s*(?=<div class="[^"\n]*product-profile__body)/s';
        return preg_replace_callback($pattern, static fn($parts) => $parts[1] . $figure, $article, 1) ?? $article;
    }, $content) ?? $content;
}

function kurashinoshirube_filter_official_product_media($content)
{
    if (!is_string($content) || !is_singular('post') || is_admin() || is_feed()) {
        return $content;
    }
    $slug = get_post_field('post_name', get_queried_object_id());
    return is_string($slug) ? kurashinoshirube_official_product_media($content, $slug) : $content;
}
add_filter('the_content', 'kurashinoshirube_filter_official_product_media', 11);
