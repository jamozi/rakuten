<?php
/**
 * ST-1704 presentation and metadata bridge.
 *
 * This theme performs no remote requests and grants no autonomous publication,
 * plugin, theme, taxonomy, or media capability. One fixed AT-003 admin POST may
 * apply a hash-confirmed update after an explicit human action. Metadata is read
 * from one closed post-meta value and ignored unless it matches the rendered post.
 */

const KURASHINOSHIRUBE_SNAPSHOT_META_KEY = '_raos_publication_snapshot_v1';
const KURASHINOSHIRUBE_SNAPSHOT_SCHEMA = 'RAOS_PUBLICATION_SNAPSHOT_V1';
const KURASHINOSHIRUBE_SNAPSHOT_MAX_BYTES = 16384;
const KURASHINOSHIRUBE_SITE_ORIGIN = 'https://kurashinoshirube.com';
const KURASHINOSHIRUBE_THEME_VERSION = '1.3.10';
const KURASHINOSHIRUBE_THEME_RUNTIME_REVISION = '30a84ec5dffb12c048181198ecc8745fa22be70f1854507237c19306589b341f';
const KURASHINOSHIRUBE_EDITORIAL_V2_ROOT = '<div class="raos-editorial-v2">';
const KURASHINOSHIRUBE_SOCIAL_IMAGE_PATH = 'assets/images/home-hero.webp';
const KURASHINOSHIRUBE_SOCIAL_IMAGE_SHA256 = 'df9fc09115e93708e858335e50e88534cc91114fb064642f9d904b5e52b83cea';
const KURASHINOSHIRUBE_ARTICLE_IMAGE_PATH = 'assets/images/article-suitcase-guide.webp';
const KURASHINOSHIRUBE_ARTICLE_IMAGE_SHA256 = '23c585a03598a8521fd797c036d2caad4350139ad709ca9b0cfc3ab18ad993ad';
const KURASHINOSHIRUBE_POWER_ARTICLE_IMAGE_PATH = 'assets/images/article-portable-power-guide.png';
const KURASHINOSHIRUBE_POWER_ARTICLE_IMAGE_SHA256 = '703444cdf29740bb72de42d09c7c7222a3ee46a09bcaf4f78875df9131cc56d6';
const KURASHINOSHIRUBE_BRAND_MARK_PATH = 'assets/images/brand-mark.svg';
const KURASHINOSHIRUBE_BRAND_MARK_SHA256 = 'bd9f84f40eca90fb88b7e8a3967f6d7ceb5d337c6023d1f2ff748936a0f3acf3';
const KURASHINOSHIRUBE_HOMEPAGE_FEATURED_ARTICLE_ID = 'st1704-portable-power-station-guide';
const KURASHINOSHIRUBE_EXISTING_UPDATE_ARTICLE_ID = 'st1703-first-suitcase-comparison';
const KURASHINOSHIRUBE_EXISTING_UPDATE_ACTION = 'kurashinoshirube_apply_at003_review_v1';
const KURASHINOSHIRUBE_EXISTING_UPDATE_PAGE = 'kurashinoshirube-at003-update-v1';
const KURASHINOSHIRUBE_EXISTING_UPDATE_LOCK_PREFIX = '_raos_at003_update_lock_v1_';
const KURASHINOSHIRUBE_REVIEW_REQUEST_PATH = '/wp-json/wp/v2/posts?_fields=id%2Ctype%2Cslug%2Cstatus%2Ctitle.raw%2Cexcerpt.raw%2Ccontent.raw%2Cmeta._raos_publication_snapshot_v1';
const KURASHINOSHIRUBE_RELATED_ARTICLE_MAP_SHA256 = '5db17f3cff259d4abe35cf616b2e953d25f33b5187ac637d6c1c6f3a86174028';
const KURASHINOSHIRUBE_RELATED_ARTICLE_MAP_JSON = '{"st1703-first-suitcase-comparison":{"home_anchor":"cluster-mobility","home_label":"暮らしの道具「移動」の一覧へ","targets":{}},"st1704-anker-solix-c300-c800-c1000-differences":{"home_anchor":"cluster-ready","home_label":"暮らしの道具「備え」の一覧へ","targets":{"st1704-portable-power-station-guide":"停電対策用ポータブル電源の選び方｜容量・定格出力・持ち運びで決める"}},"st1704-compact-robot-vacuum-shortlist":{"home_anchor":"cluster-home","home_label":"暮らしの道具「家事」の一覧へ","targets":{"st1704-countertop-dishwasher-for-small-households":"工事不要の食洗機を1〜2人暮らし向けに比較"}},"st1704-countertop-dishwasher-for-small-households":{"home_anchor":"cluster-home","home_label":"暮らしの道具「家事」の一覧へ","targets":{"st1704-compact-robot-vacuum-shortlist":"省スペースのロボット掃除機を条件で絞る"}},"st1704-portable-power-station-guide":{"home_anchor":"cluster-ready","home_label":"暮らしの道具「備え」の一覧へ","targets":{"st1704-anker-solix-c300-c800-c1000-differences":"Anker Solix C300・C800 Plus・C1000・C1000 Gen 2の違い"}}}';
const KURASHINOSHIRUBE_HOMEPAGE_CLUSTERS_SHA256 = 'd9e2e40d369723e2e8dc2f6d5bfc0e74e2873c7748936a287f04a4acbc7dc7da';
const KURASHINOSHIRUBE_HOMEPAGE_CLUSTERS_JSON = '{"clusters":{"cluster-home":{"description":"置き場所と手間から、無理のない一台を選ぶ。","heading":"置き場所と日々の手間を整える","label":"家事","post_order":["st1704-countertop-dishwasher-for-small-households","st1704-compact-robot-vacuum-shortlist"],"posts":{"st1704-compact-robot-vacuum-shortlist":"省スペースのロボット掃除機を条件で絞る","st1704-countertop-dishwasher-for-small-households":"工事不要の食洗機を1〜2人暮らし向けに比較"}},"cluster-mobility":{"description":"軽さ、容量、持ち運び方の違いをほどく。","heading":"持ち運ぶ負担を小さくする","label":"移動","post_order":["st1703-first-suitcase-comparison"],"posts":{"st1703-first-suitcase-comparison":"エースの機内持ち込みスーツケース3モデル比較"}},"cluster-ready":{"description":"必要な容量と出力を、使う場面から逆算する。","heading":"必要な電力を過不足なく備える","label":"備え","post_order":["st1704-portable-power-station-guide","st1704-anker-solix-c300-c800-c1000-differences"],"posts":{"st1704-anker-solix-c300-c800-c1000-differences":"Anker Solix 4モデルの違い","st1704-portable-power-station-guide":"停電対策用ポータブル電源の選び方"}}},"display_order":["cluster-mobility","cluster-home","cluster-ready"]}';

/** Return the only article identities accepted by the v1 bridge. */
function kurashinoshirube_article_bindings(): array
{
    return array(
        'st1703-first-suitcase-comparison' => array(
            'slug' => 'carry-on-suitcase-comparison',
            'section' => '移動',
        ),
        'st1704-portable-power-station-guide' => array(
            'slug' => 'portable-power-station-guide',
            'section' => '備え',
        ),
        'st1704-countertop-dishwasher-for-small-households' => array(
            'slug' => 'countertop-dishwasher-for-small-households',
            'section' => '家事',
        ),
        'st1704-anker-solix-c300-c800-c1000-differences' => array(
            'slug' => 'anker-solix-c300-c800-c1000-differences',
            'section' => '備え',
        ),
        'st1704-compact-robot-vacuum-shortlist' => array(
            'slug' => 'compact-robot-vacuum-shortlist',
            'section' => '家事',
        ),
    );
}

/** Closed identities allowed to use the Editorial V2 publication fallback. */
function kurashinoshirube_editorial_v2_publication_bindings(): array
{
    return array(
        'st1703-first-suitcase-comparison' => array(
            'slug' => 'carry-on-suitcase-comparison',
            'section' => '移動',
        ),
        'st1704-portable-power-station-guide' => array(
            'slug' => 'portable-power-station-guide',
            'section' => '備え',
        ),
        'st1704-countertop-dishwasher-for-small-households' => array(
            'slug' => 'countertop-dishwasher-for-small-households',
            'section' => '家事',
        ),
        'st1704-anker-solix-c300-c800-c1000-differences' => array(
            'slug' => 'anker-solix-c300-c800-c1000-differences',
            'section' => '備え',
        ),
        'st1704-compact-robot-vacuum-shortlist' => array(
            'slug' => 'compact-robot-vacuum-shortlist',
            'section' => '家事',
        ),
        'carry-on-suitcase-under-100-seats' => array(
            'slug' => 'carry-on-suitcase-under-100-seats',
            'section' => '移動',
        ),
        'front-open-carry-on-suitcase-with-stopper' => array(
            'slug' => 'front-open-carry-on-suitcase-with-stopper',
            'section' => '移動',
        ),
        'lightweight-carry-on-suitcase-under-3kg' => array(
            'slug' => 'lightweight-carry-on-suitcase-under-3kg',
            'section' => '移動',
        ),
        'roomba-mini-vs-switchbot-k11-pro' => array(
            'slug' => 'roomba-mini-vs-switchbot-k11-pro',
            'section' => '家事',
        ),
        'solota-vs-rakua-mini-plus' => array(
            'slug' => 'solota-vs-rakua-mini-plus',
            'section' => '家事',
        ),
    );
}

/** Fixed theme-chrome relations; no score, revenue, or mutable option is read. */
function kurashinoshirube_related_article_map(): array
{
    if (
        ! hash_equals(
            KURASHINOSHIRUBE_RELATED_ARTICLE_MAP_SHA256,
            hash('sha256', KURASHINOSHIRUBE_RELATED_ARTICLE_MAP_JSON)
        )
    ) {
        return array();
    }
    $map = json_decode(
        KURASHINOSHIRUBE_RELATED_ARTICLE_MAP_JSON,
        true,
        8,
        JSON_BIGINT_AS_STRING
    );
    return json_last_error() === JSON_ERROR_NONE && is_array($map)
        ? $map
        : array();
}

/** Return the hash-bound homepage clusters and their explicit visual order. */
function kurashinoshirube_homepage_clusters(): array
{
    if (
        ! hash_equals(
            KURASHINOSHIRUBE_HOMEPAGE_CLUSTERS_SHA256,
            hash('sha256', KURASHINOSHIRUBE_HOMEPAGE_CLUSTERS_JSON)
        )
    ) {
        return array();
    }
    $configuration = json_decode(
        KURASHINOSHIRUBE_HOMEPAGE_CLUSTERS_JSON,
        true,
        12,
        JSON_BIGINT_AS_STRING
    );
    if (
        json_last_error() !== JSON_ERROR_NONE
        || ! is_array($configuration)
        || ! kurashinoshirube_has_exact_keys(
            $configuration,
            array('clusters', 'display_order')
        )
        || ! is_array($configuration['clusters'])
        || ! is_array($configuration['display_order'])
        || count($configuration['display_order']) !== 3
        || count(array_unique($configuration['display_order'])) !== 3
    ) {
        return array();
    }
    $cluster_ids = array_keys($configuration['clusters']);
    sort($cluster_ids, SORT_STRING);
    $ordered_ids = $configuration['display_order'];
    sort($ordered_ids, SORT_STRING);
    return $cluster_ids === $ordered_ids ? $configuration : array();
}

/** Exact-key helper for decoded JSON objects. */
function kurashinoshirube_has_exact_keys($value, array $expected): bool
{
    if (! is_array($value)) {
        return false;
    }
    $actual = array_keys($value);
    sort($actual, SORT_STRING);
    sort($expected, SORT_STRING);
    return $actual === $expected;
}

/** Recursively sort object keys for the cross-runtime canonical JSON profile. */
function kurashinoshirube_is_json_list(array $value): bool
{
    $expected = 0;
    foreach ($value as $key => $unused) {
        if ($key !== $expected) {
            return false;
        }
        ++$expected;
    }
    return true;
}

/** Recursively sort object keys for the cross-runtime canonical JSON profile. */
function kurashinoshirube_canonicalize_json_value($value)
{
    if (! is_array($value)) {
        return $value;
    }
    if (kurashinoshirube_is_json_list($value)) {
        return array_map('kurashinoshirube_canonicalize_json_value', $value);
    }
    ksort($value, SORT_STRING);
    foreach ($value as $key => $item) {
        if (! is_string($key)) {
            return null;
        }
        $value[$key] = kurashinoshirube_canonicalize_json_value($item);
    }
    return $value;
}

/** Encode one stable UTF-8 JSON byte sequence or fail closed. */
function kurashinoshirube_canonical_json($value): ?string
{
    $canonical = kurashinoshirube_canonicalize_json_value($value);
    if ($canonical === null) {
        return null;
    }
    $encoded = wp_json_encode(
        $canonical,
        JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION
    );
    return is_string($encoded) ? $encoded : null;
}

/** Require clean, single-line, markup-free text with Unicode character bounds. */
function kurashinoshirube_is_clean_text($value, int $minimum, int $maximum): bool
{
    if (
        ! is_string($value)
        || $value === ''
        || $value !== trim($value)
        || strlen($value) > $maximum * 4
        || preg_match('/[\x00-\x1F\x7F]/u', $value) === 1
        || wp_strip_all_tags($value) !== $value
    ) {
        return false;
    }
    $characters = preg_match_all('/./us', $value, $unused);
    return is_int($characters) && $characters >= $minimum && $characters <= $maximum;
}

/** Accept null for a pre-publication snapshot or one canonical UTC timestamp. */
function kurashinoshirube_is_nullable_timestamp($value): bool
{
    if ($value === null) {
        return true;
    }
    if (
        ! is_string($value)
        || preg_match('/\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\z/D', $value) !== 1
    ) {
        return false;
    }
    $parsed = DateTimeImmutable::createFromFormat(
        '!Y-m-d\TH:i:s\Z',
        $value,
        new DateTimeZone('UTC')
    );
    return $parsed instanceof DateTimeImmutable
        && $parsed->format('Y-m-d\TH:i:s\Z') === $value;
}

/** Parse the strict snapshot wrapper without consulting mutable post state. */
function kurashinoshirube_parse_snapshot($raw): ?array
{
    if (
        ! is_string($raw)
        || $raw === ''
        || strlen($raw) > KURASHINOSHIRUBE_SNAPSHOT_MAX_BYTES
        || strpos($raw, "\0") !== false
    ) {
        return null;
    }
    $decoded = json_decode($raw, true, 16, JSON_BIGINT_AS_STRING);
    if (
        json_last_error() !== JSON_ERROR_NONE
        || ! kurashinoshirube_has_exact_keys(
            $decoded,
            array('schema', 'payload', 'payload_sha256')
        )
        || ($decoded['schema'] ?? null) !== KURASHINOSHIRUBE_SNAPSHOT_SCHEMA
        || ! is_string($decoded['payload_sha256'] ?? null)
        || preg_match('/\A[0-9a-f]{64}\z/D', $decoded['payload_sha256']) !== 1
        || kurashinoshirube_canonical_json($decoded) !== $raw
    ) {
        return null;
    }

    $payload = $decoded['payload'];
    $payload_keys = array(
        'article_id',
        'author_name',
        'canonical_url',
        'description',
        'modified_at',
        'og_description',
        'og_title',
        'packet_sha256',
        'published_at',
        'section',
        'seo_title',
        'slug',
        'title',
        'visible_content_sha256',
    );
    if (! kurashinoshirube_has_exact_keys($payload, $payload_keys)) {
        return null;
    }
    $payload_json = kurashinoshirube_canonical_json($payload);
    if (
        $payload_json === null
        || ! hash_equals($decoded['payload_sha256'], hash('sha256', $payload_json))
        || ! is_string($payload['article_id'])
        || ! is_string($payload['slug'])
        || ! is_string($payload['section'])
    ) {
        return null;
    }

    $bindings = kurashinoshirube_article_bindings();
    $binding = $bindings[$payload['article_id']] ?? null;
    $canonical = KURASHINOSHIRUBE_SITE_ORIGIN . '/' . $payload['slug'] . '/';
    if (
        ! is_array($binding)
        || $payload['slug'] !== $binding['slug']
        || $payload['section'] !== $binding['section']
        || ($payload['canonical_url'] ?? null) !== $canonical
        || ($payload['author_name'] ?? null) !== '暮らしのしるべ編集部'
        || ! kurashinoshirube_is_clean_text($payload['title'] ?? null, 8, 100)
        || ! kurashinoshirube_is_clean_text($payload['seo_title'] ?? null, 8, 100)
        || ! kurashinoshirube_is_clean_text($payload['description'] ?? null, 30, 180)
        || ($payload['og_title'] ?? null) !== $payload['title']
        || ($payload['og_description'] ?? null) !== $payload['description']
        || ! is_string($payload['packet_sha256'] ?? null)
        || preg_match('/\A[0-9a-f]{64}\z/D', $payload['packet_sha256']) !== 1
        || ! kurashinoshirube_is_nullable_timestamp($payload['published_at'] ?? null)
        || ! kurashinoshirube_is_nullable_timestamp($payload['modified_at'] ?? null)
        || ! is_string($payload['visible_content_sha256'] ?? null)
        || preg_match('/\A[0-9a-f]{64}\z/D', $payload['visible_content_sha256']) !== 1
        || (
            $payload['published_at'] !== null
            && $payload['modified_at'] !== null
            && strcmp($payload['modified_at'], $payload['published_at']) < 0
        )
    ) {
        return null;
    }
    return $payload;
}

/** Store only canonical, fully valid wrappers; invalid input clears the bridge. */
function kurashinoshirube_sanitize_snapshot($value): string
{
    return kurashinoshirube_parse_snapshot($value) === null ? '' : $value;
}

/** Derive the only temporary slug accepted for a hash-bound Review Draft. */
function kurashinoshirube_review_slug(array $payload): ?string
{
    $payload_json = kurashinoshirube_canonical_json($payload);
    if (
        $payload_json === null
        || ! is_string($payload['slug'] ?? null)
    ) {
        return null;
    }
    return 'raos-review-' . $payload['slug'] . '-'
        . hash('sha256', $payload_json);
}

/** Accept a public slug, or a closed draft-only review-slug shape. */
function kurashinoshirube_is_authorized_post_slug(
    string $slug,
    string $status
): bool {
    foreach (kurashinoshirube_article_bindings() as $binding) {
        $public_slug = $binding['slug'];
        if ($slug === $public_slug) {
            return $status === 'publish';
        }
        if (
            $status === 'draft'
            && preg_match(
                '/\Araos-review-' . preg_quote($public_slug, '/')
                . '-[0-9a-f]{64}\z/D',
                $slug
            ) === 1
        ) {
            return true;
        }
    }
    return false;
}

/** Limit writes to users who can edit the exact allowlisted post. */
function kurashinoshirube_authorize_snapshot_meta(
    $allowed,
    $meta_key,
    $object_id,
    $user_id,
    $cap,
    $caps
): bool {
    if (
        ! is_int($object_id)
        && ! (is_string($object_id) && ctype_digit($object_id))
    ) {
        return false;
    }
    $post_id = (int) $object_id;
    $slug = get_post_field('post_name', $post_id, 'raw');
    $status = get_post_status($post_id);
    return $post_id > 0
        && get_post_type($post_id) === 'post'
        && is_string($slug)
        && is_string($status)
        && kurashinoshirube_is_authorized_post_slug($slug, $status)
        && current_user_can('edit_post', $post_id);
}

add_action('init', static function (): void {
    register_post_meta(
        'post',
        KURASHINOSHIRUBE_SNAPSHOT_META_KEY,
        array(
            'auth_callback' => 'kurashinoshirube_authorize_snapshot_meta',
            'default' => '',
            'description' => 'Hash-bound RAOS publication snapshot. Never publication authority.',
            'revisions_enabled' => true,
            'sanitize_callback' => 'kurashinoshirube_sanitize_snapshot',
            'show_in_rest' => array(
                'schema' => array(
                    'maxLength' => KURASHINOSHIRUBE_SNAPSHOT_MAX_BYTES,
                    'type' => 'string',
                ),
            ),
            'single' => true,
            'type' => 'string',
        )
    );
});

/** Never expose the internal snapshot through an anonymous REST response. */
function kurashinoshirube_hide_public_snapshot_meta($response, $post, $request)
{
    $post_id = is_object($post) && isset($post->ID) ? (int) $post->ID : 0;
    $context = is_object($request) && method_exists($request, 'get_param')
        ? $request->get_param('context')
        : null;
    if (is_object($response) && method_exists($response, 'get_data')) {
        $data = $response->get_data();
        if (is_array($data)) {
            unset($data['yoast_head'], $data['yoast_head_json']);
            if (
                ! ($context === 'edit'
                    && $post_id > 0
                    && current_user_can('edit_post', $post_id))
                && is_array($data['meta'] ?? null)
            ) {
                unset($data['meta'][KURASHINOSHIRUBE_SNAPSHOT_META_KEY]);
            }
            $response->set_data($data);
        }
    }
    return $response;
}
add_filter('rest_prepare_post', 'kurashinoshirube_hide_public_snapshot_meta', 99, 3);
add_filter('rest_prepare_page', 'kurashinoshirube_hide_public_snapshot_meta', 99, 3);

/**
 * Read back the persisted, human-configured Yoast profile. The theme loads
 * after normal plugins, so it deliberately does not claim to rewrite options
 * that Yoast may already have cached during plugins_loaded.
 */
function kurashinoshirube_yoast_configuration_is_exact(): bool
{
    static $verified = null;
    if (is_bool($verified)) {
        return $verified;
    }
    $verified = false;
    if (! defined('WPSEO_VERSION') || WPSEO_VERSION !== '28.3') {
        return false;
    }
    $options = get_option('wpseo', null);
    $social = get_option('wpseo_social', null);
    if (! is_array($options) || ! is_array($social)) {
        return false;
    }
    $expected = array(
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
    foreach ($expected as $key => $value) {
        if (! array_key_exists($key, $options) || $options[$key] !== $value) {
            return false;
        }
    }
    $social_image = kurashinoshirube_verified_asset_uri(
        KURASHINOSHIRUBE_SOCIAL_IMAGE_PATH,
        KURASHINOSHIRUBE_SOCIAL_IMAGE_SHA256
    );
    if ($social_image === null) {
        return false;
    }
    $expected_social = array(
        'og_default_image' => $social_image,
        'og_default_image_id' => '',
        'opengraph' => true,
        'twitter' => true,
        'twitter_card_type' => 'summary_large_image',
    );
    foreach ($expected_social as $key => $value) {
        if (! array_key_exists($key, $social) || $social[$key] !== $value) {
            return false;
        }
    }
    $verified = true;
    return true;
}

/** Make the read-only configuration gate visible in WordPress Site Health. */
function kurashinoshirube_yoast_site_health_test(): array
{
    $verified = kurashinoshirube_yoast_configuration_is_exact();
    return array(
        'badge' => array('color' => 'blue', 'label' => 'RAOS'),
        'description' => '<p>' . esc_html(
            $verified
                ? 'Yoast SEO 28.3の保存設定がRAOS契約と一致しています。'
                : 'Yoast SEO 28.3の版または保存設定がRAOS契約と一致していません。'
        ) . '</p>',
        'label' => 'RAOS Yoast 28.3設定',
        'status' => $verified ? 'good' : 'critical',
        'test' => 'kurashinoshirube_yoast_configuration',
    );
}

function kurashinoshirube_register_site_health_tests($tests): array
{
    if (! is_array($tests)) {
        return array();
    }
    if (! is_array($tests['direct'] ?? null)) {
        $tests['direct'] = array();
    }
    $tests['direct']['kurashinoshirube_yoast_configuration'] = array(
        'label' => 'RAOS Yoast 28.3設定',
        'test' => 'kurashinoshirube_yoast_site_health_test',
    );
    return $tests;
}
add_filter(
    'site_status_tests',
    'kurashinoshirube_register_site_health_tests',
    20,
    1
);

/** Remove Yoast's public head route even if stale plugin state registered it. */
function kurashinoshirube_remove_yoast_head_route($endpoints)
{
    if (! is_array($endpoints)) {
        return $endpoints;
    }
    foreach (array_keys($endpoints) as $route) {
        if (
            is_string($route)
            && ($route === '/yoast/v1/get_head'
                || strpos($route, '/yoast/v1/get_head/') === 0)
        ) {
            unset($endpoints[$route]);
        }
    }
    return $endpoints;
}
add_filter('rest_endpoints', 'kurashinoshirube_remove_yoast_head_route', PHP_INT_MAX);

/** Resolve a self-owned theme asset and verify its exact immutable bytes. */
function kurashinoshirube_verified_asset_uri(string $relative, string $sha256): ?string
{
    if (
        preg_match('#\Aassets/images/[a-z0-9-]+\.(?:svg|webp)\z#D', $relative) !== 1
        || preg_match('/\A[0-9a-f]{64}\z/D', $sha256) !== 1
    ) {
        return null;
    }
    $path = untrailingslashit(get_stylesheet_directory()) . '/' . $relative;
    if (
        is_link($path)
        || ! is_file($path)
        || ! is_readable($path)
        || ! hash_equals($sha256, (string) hash_file('sha256', $path))
    ) {
        return null;
    }
    $base = untrailingslashit(get_stylesheet_directory_uri());
    $parts = wp_parse_url($base);
    if (
        ! is_array($parts)
        || ($parts['scheme'] ?? null) !== 'https'
        || ($parts['host'] ?? null) !== 'kurashinoshirube.com'
        || ! isset($parts['path'])
        || ! is_string($parts['path'])
        || preg_match(
            '#\A/(?:[A-Za-z0-9][A-Za-z0-9._-]*/)*kurashinoshirube-child\z#D',
            $parts['path']
        ) !== 1
        || array_intersect_key(
            $parts,
            array_flip(array('port', 'user', 'pass', 'query', 'fragment'))
        ) !== array()
    ) {
        return null;
    }
    return $base . '/' . $relative;
}

/** Bind one parsed snapshot to exact stored post bytes and identity. */
function kurashinoshirube_bound_post_snapshot(
    int $post_id,
    bool $allow_review_draft
): ?array
{
    if ($post_id <= 0) {
        return null;
    }
    $raw = get_post_meta($post_id, KURASHINOSHIRUBE_SNAPSHOT_META_KEY, true);
    $payload = kurashinoshirube_parse_snapshot($raw);
    $content = get_post_field('post_content', $post_id, 'raw');
    $excerpt = get_post_field('post_excerpt', $post_id, 'raw');
    $title = get_post_field('post_title', $post_id, 'raw');
    $slug = get_post_field('post_name', $post_id, 'raw');
    $status = get_post_status($post_id);
    $review_slug = is_array($payload)
        ? kurashinoshirube_review_slug($payload)
        : null;
    if (
        $payload === null
        || get_post_type($post_id) !== 'post'
        || ! is_string($content)
        || ! is_string($excerpt)
        || ! is_string($title)
        || ! is_string($slug)
        || ! is_string($status)
        || $payload['description'] !== $excerpt
        || $payload['title'] !== $title
        || ! (
            ($status === 'publish' && $payload['slug'] === $slug)
            || (
                $allow_review_draft
                && $status === 'draft'
                && $review_slug !== null
                && $review_slug === $slug
            )
        )
        || ! hash_equals($payload['visible_content_sha256'], hash('sha256', $content))
        || kurashinoshirube_verified_asset_uri(
            KURASHINOSHIRUBE_SOCIAL_IMAGE_PATH,
            KURASHINOSHIRUBE_SOCIAL_IMAGE_SHA256
        ) === null
    ) {
        return null;
    }

    if ($status === 'publish') {
        $published = get_post_time('Y-m-d\TH:i:s\Z', true, $post_id);
        $modified = get_post_modified_time('Y-m-d\TH:i:s\Z', true, $post_id);
        if (
            ! is_string($published)
            || ! is_string($modified)
            || ($payload['published_at'] !== null && $payload['published_at'] !== $published)
            || ($payload['modified_at'] !== null && $payload['modified_at'] !== $modified)
        ) {
            return null;
        }
    }
    return $payload;
}

/** Detect the exact authored Editorial V2 raw-content prefix on one post. */
function kurashinoshirube_post_has_editorial_v2_root(int $post_id): bool
{
    if ($post_id <= 0 || get_post_type($post_id) !== 'post') {
        return false;
    }
    $content = get_post_field('post_content', $post_id, 'raw');
    return is_string($content)
        && str_starts_with($content, KURASHINOSHIRUBE_EDITORIAL_V2_ROOT);
}

/**
 * Resolve one exact published Editorial V2 identity without snapshot metadata.
 *
 * The fallback is deliberately unavailable to drafts, unknown routes, and
 * content whose single authored root or article identity does not match the
 * closed ten-article portfolio.
 */
function kurashinoshirube_published_editorial_v2_identity(
    int $post_id
): ?array {
    if (
        $post_id <= 0
        || get_post_type($post_id) !== 'post'
        || get_post_status($post_id) !== 'publish'
    ) {
        return null;
    }
    $slug = get_post_field('post_name', $post_id, 'raw');
    $content = get_post_field('post_content', $post_id, 'raw');
    if (! is_string($slug) || ! is_string($content)) {
        return null;
    }
    $article_id = null;
    $binding = null;
    foreach (
        kurashinoshirube_editorial_v2_publication_bindings()
        as $candidate_article_id => $candidate_binding
    ) {
        if (
            is_array($candidate_binding)
            && ($candidate_binding['slug'] ?? null) === $slug
        ) {
            $article_id = $candidate_article_id;
            $binding = $candidate_binding;
            break;
        }
    }
    if (
        ! is_string($article_id)
        || ! is_array($binding)
        || ! kurashinoshirube_post_has_editorial_v2_root($post_id)
        || substr_count($content, KURASHINOSHIRUBE_EDITORIAL_V2_ROOT) !== 1
        || ! str_ends_with($content, "</div>\n")
    ) {
        return null;
    }
    $matched = preg_match_all(
        '/\bdata-raos-article-id="([a-z0-9]+(?:-[a-z0-9]+)*)"/',
        $content,
        $matches
    );
    if (
        ! is_int($matched)
        || $matched < 1
        || ! isset($matches[1])
        || ! is_array($matches[1])
        || array_values(array_unique($matches[1])) !== array($article_id)
    ) {
        return null;
    }
    return array(
        'article_id' => $article_id,
        'section' => $binding['section'],
        'slug' => $slug,
    );
}

/** One predicate for every public presentation and discovery consumer. */
function kurashinoshirube_public_article_identity(int $post_id): ?array
{
    $snapshot = kurashinoshirube_bound_post_snapshot($post_id, false);
    if ($snapshot !== null) {
        return array(
            'article_id' => $snapshot['article_id'],
            'section' => $snapshot['section'],
            'slug' => $snapshot['slug'],
        );
    }
    return kurashinoshirube_published_editorial_v2_identity($post_id);
}

/** Bind the singular presentation to one exact public post or Review Draft. */
function kurashinoshirube_current_snapshot(): ?array
{
    static $cache = array();
    if (
        ! is_singular('post')
        || ! kurashinoshirube_yoast_configuration_is_exact()
    ) {
        return null;
    }
    $post_id = (int) get_queried_object_id();
    if ($post_id <= 0) {
        return null;
    }
    if (! array_key_exists($post_id, $cache)) {
        $cache[$post_id] = kurashinoshirube_bound_post_snapshot($post_id, true);
    }
    return $cache[$post_id];
}

/** Preserve authored RAOS HTML only for an exact public article identity. */
function kurashinoshirube_disable_wpautop_for_bound_public_article(): void
{
    if (! is_singular('post')) {
        return;
    }
    $post_id = (int) get_queried_object_id();
    if (
        $post_id <= 0
        || get_post_status($post_id) !== 'publish'
        || kurashinoshirube_public_article_identity($post_id) === null
    ) {
        return;
    }
    remove_filter('the_content', 'wpautop', 10);
}
add_action(
    'wp',
    'kurashinoshirube_disable_wpautop_for_bound_public_article',
    0
);

/** Read one exact lower-case SHA-256 assertion from a request boundary. */
function kurashinoshirube_read_sha256_input(int $input_type, string $name): ?string
{
    $value = filter_input(
        $input_type,
        $name,
        FILTER_UNSAFE_RAW,
        FILTER_REQUIRE_SCALAR
    );
    return is_string($value)
        && preg_match('/\A[0-9a-f]{64}\z/D', $value) === 1
        ? $value
        : null;
}

/** Read one exact positive decimal post-ID assertion. */
function kurashinoshirube_read_post_id_input(int $input_type, string $name): ?int
{
    $value = filter_input(
        $input_type,
        $name,
        FILTER_UNSAFE_RAW,
        FILTER_REQUIRE_SCALAR
    );
    if (
        ! is_string($value)
        || preg_match('/\A[1-9][0-9]{0,18}\z/D', $value) !== 1
    ) {
        return null;
    }
    $integer = filter_var($value, FILTER_VALIDATE_INT);
    return is_int($integer) && $integer > 0 ? $integer : null;
}

/** Resolve exactly one post from a server-owned slug and status. */
function kurashinoshirube_resolve_one_post_id(
    string $slug,
    string $status
): ?int {
    $ids = get_posts(
        array(
            'fields' => 'ids',
            'name' => $slug,
            'no_found_rows' => true,
            'order' => 'ASC',
            'orderby' => 'ID',
            'post_status' => $status,
            'post_type' => 'post',
            'posts_per_page' => 2,
            'suppress_filters' => true,
        )
    );
    if (! is_array($ids) || count($ids) !== 1 || ! is_int($ids[0])) {
        return null;
    }
    return $ids[0] > 0 ? $ids[0] : null;
}

/** Capture every post taxonomy as a stable server-side invariant. */
function kurashinoshirube_post_taxonomy_state(int $post_id): ?array
{
    $taxonomies = get_object_taxonomies('post', 'names');
    if (! is_array($taxonomies)) {
        return null;
    }
    sort($taxonomies, SORT_STRING);
    $state = array();
    foreach ($taxonomies as $taxonomy) {
        if (! is_string($taxonomy)) {
            return null;
        }
        $ids = wp_get_object_terms(
            $post_id,
            $taxonomy,
            array('fields' => 'ids')
        );
        if (is_wp_error($ids) || ! is_array($ids)) {
            return null;
        }
        $ids = array_map('intval', $ids);
        sort($ids, SORT_NUMERIC);
        $state[$taxonomy] = $ids;
    }
    return $state;
}

/** Capture public identity fields that the bounded update may never change. */
function kurashinoshirube_existing_update_invariants(int $post_id): ?array
{
    $post = get_post($post_id);
    $taxonomies = kurashinoshirube_post_taxonomy_state($post_id);
    if (! ($post instanceof WP_Post) || $taxonomies === null) {
        return null;
    }
    return array(
        'comment_status' => $post->comment_status,
        'guid' => $post->guid,
        'menu_order' => (int) $post->menu_order,
        'ping_status' => $post->ping_status,
        'post_author' => (int) $post->post_author,
        'post_date' => $post->post_date,
        'post_date_gmt' => $post->post_date_gmt,
        'post_name' => $post->post_name,
        'post_parent' => (int) $post->post_parent,
        'post_password' => $post->post_password,
        'post_status' => $post->post_status,
        'post_type' => $post->post_type,
        'taxonomies' => $taxonomies,
    );
}

/** Capture the exact existing-post state shown on the human confirmation page. */
function kurashinoshirube_existing_update_pre_state(int $post_id): ?array
{
    $post = get_post($post_id);
    $invariants = kurashinoshirube_existing_update_invariants($post_id);
    $snapshot = get_post_meta(
        $post_id,
        KURASHINOSHIRUBE_SNAPSHOT_META_KEY,
        true
    );
    if (
        ! ($post instanceof WP_Post)
        || $invariants === null
        || ! is_string($snapshot)
    ) {
        return null;
    }
    return array(
        'content_sha256' => hash('sha256', $post->post_content),
        'excerpt_sha256' => hash('sha256', $post->post_excerpt),
        'invariants' => $invariants,
        'snapshot_sha256' => hash('sha256', $snapshot),
        'title_sha256' => hash('sha256', $post->post_title),
    );
}

/** Build the only permitted existing-post update context (AT-003). */
function kurashinoshirube_existing_update_context(
    string $payload_sha256,
    string $packet_sha256,
    string $request_sha256,
    int $expected_source_post_id,
    int $expected_target_post_id
): ?array {
    $theme = wp_get_theme();
    if (
        get_stylesheet() !== 'kurashinoshirube-child'
        || ! is_object($theme)
        || $theme->get('Version') !== KURASHINOSHIRUBE_THEME_VERSION
        || ! kurashinoshirube_yoast_configuration_is_exact()
    ) {
        return null;
    }
    $binding = kurashinoshirube_article_bindings()[
        KURASHINOSHIRUBE_EXISTING_UPDATE_ARTICLE_ID
    ] ?? null;
    if (! is_array($binding)) {
        return null;
    }
    $public_slug = $binding['slug'];
    $review_slug = 'raos-review-' . $public_slug . '-' . $payload_sha256;
    $source_id = kurashinoshirube_resolve_one_post_id($review_slug, 'draft');
    $target_id = kurashinoshirube_resolve_one_post_id($public_slug, 'publish');
    if ($source_id === null || $target_id === null || $source_id === $target_id) {
        return null;
    }
    $source = get_post($source_id);
    $target = get_post($target_id);
    $snapshot_raw = get_post_meta(
        $source_id,
        KURASHINOSHIRUBE_SNAPSHOT_META_KEY,
        true
    );
    $snapshot = kurashinoshirube_parse_snapshot($snapshot_raw);
    $bound = kurashinoshirube_bound_post_snapshot($source_id, true);
    if (
        ! ($source instanceof WP_Post)
        || ! ($target instanceof WP_Post)
        || ! is_string($snapshot_raw)
        || $snapshot === null
        || $bound === null
        || $snapshot['article_id'] !== KURASHINOSHIRUBE_EXISTING_UPDATE_ARTICLE_ID
        || $bound['article_id'] !== KURASHINOSHIRUBE_EXISTING_UPDATE_ARTICLE_ID
        || $snapshot['slug'] !== $public_slug
        || $snapshot['packet_sha256'] !== $packet_sha256
        || preg_match('/\A[0-9a-f]{64}\z/D', $request_sha256) !== 1
        || kurashinoshirube_review_slug($snapshot) !== $review_slug
        || hash('sha256', (string) kurashinoshirube_canonical_json($snapshot))
            !== $payload_sha256
        || $source->post_excerpt !== $snapshot['description']
        || $target->post_name !== $public_slug
        || $target->post_status !== 'publish'
        || $target->post_type !== 'post'
        || $source_id !== $expected_source_post_id
        || $target_id !== $expected_target_post_id
    ) {
        return null;
    }
    $request_material = kurashinoshirube_canonical_json(
        array(
            'body' => array(
                'content' => $source->post_content,
                'excerpt' => $source->post_excerpt,
                'meta' => array(
                    KURASHINOSHIRUBE_SNAPSHOT_META_KEY => $snapshot_raw,
                ),
                'slug' => $review_slug,
                'status' => 'draft',
                'title' => $source->post_title,
            ),
            'origin' => KURASHINOSHIRUBE_SITE_ORIGIN,
            'path' => KURASHINOSHIRUBE_REVIEW_REQUEST_PATH,
        )
    );
    if (
        $request_material === null
        || ! hash_equals($request_sha256, hash('sha256', $request_material))
    ) {
        return null;
    }
    $pre_state = kurashinoshirube_existing_update_pre_state($target_id);
    $pre_state_json = kurashinoshirube_canonical_json($pre_state);
    if ($pre_state === null || $pre_state_json === null) {
        return null;
    }
    $target = get_post($target_id);
    $target_snapshot_raw = get_post_meta(
        $target_id,
        KURASHINOSHIRUBE_SNAPSHOT_META_KEY,
        true
    );
    if (
        ! ($target instanceof WP_Post)
        || ! is_string($target_snapshot_raw)
        || hash('sha256', $target->post_title) !== $pre_state['title_sha256']
        || hash('sha256', $target->post_excerpt) !== $pre_state['excerpt_sha256']
        || hash('sha256', $target->post_content) !== $pre_state['content_sha256']
        || hash('sha256', $target_snapshot_raw) !== $pre_state['snapshot_sha256']
        || kurashinoshirube_existing_update_invariants($target_id)
            !== $pre_state['invariants']
    ) {
        return null;
    }
    $pre_state_sha256 = hash('sha256', $pre_state_json);
    $operation = array(
        'packet_sha256' => $packet_sha256,
        'payload_sha256' => $payload_sha256,
        'pre_state_sha256' => $pre_state_sha256,
        'request_sha256' => $request_sha256,
        'source_post_id' => $source_id,
        'target_post_id' => $target_id,
    );
    $operation_json = kurashinoshirube_canonical_json($operation);
    if ($operation_json === null) {
        return null;
    }
    return array(
        'operation_sha256' => hash('sha256', $operation_json),
        'packet_sha256' => $packet_sha256,
        'payload_sha256' => $payload_sha256,
        'pre_state' => $pre_state,
        'pre_state_sha256' => $pre_state_sha256,
        'public_slug' => $public_slug,
        'request_sha256' => $request_sha256,
        'snapshot' => $snapshot,
        'snapshot_raw' => $snapshot_raw,
        'source_content' => $source->post_content,
        'source_excerpt' => $source->post_excerpt,
        'source_post_id' => $source_id,
        'source_title' => $source->post_title,
        'target_content' => $target->post_content,
        'target_excerpt' => $target->post_excerpt,
        'target_post_id' => $target_id,
        'target_snapshot_raw' => $target_snapshot_raw,
        'target_title' => $target->post_title,
    );
}

/** Return the immutable per-snapshot database lock key. */
function kurashinoshirube_existing_update_lock_key(array $context): string
{
    return KURASHINOSHIRUBE_EXISTING_UPDATE_LOCK_PREFIX
        . $context['payload_sha256'];
}

/** Build the closed approval receipt/lock written only by the human POST action. */
function kurashinoshirube_existing_update_lock_record(
    array $context,
    int $approved_by_user_id,
    string $approved_at,
    string $approval_reason
): ?string
{
    if (
        $approved_by_user_id <= 0
        || ! kurashinoshirube_is_nullable_timestamp($approved_at)
        || ! kurashinoshirube_is_clean_text($approval_reason, 10, 300)
    ) {
        return null;
    }
    return kurashinoshirube_canonical_json(
        array(
            'approved_at' => $approved_at,
            'approved_by_user_id' => $approved_by_user_id,
            'approval_reason' => $approval_reason,
            'decision' => 'APPROVE_AT003_EXISTING_UPDATE',
            'operation_sha256' => $context['operation_sha256'],
            'packet_sha256' => $context['packet_sha256'],
            'payload_sha256' => $context['payload_sha256'],
            'pre_state' => $context['pre_state'],
            'pre_state_sha256' => $context['pre_state_sha256'],
            'request_sha256' => $context['request_sha256'],
            'rollback_artifact' => array(
                'invariants' => $context['pre_state']['invariants'],
                'post_content' => $context['target_content'],
                'post_excerpt' => $context['target_excerpt'],
                'post_title' => $context['target_title'],
                'snapshot_raw' => $context['target_snapshot_raw'],
            ),
            'schema' => 'RAOS_AT003_HUMAN_UPDATE_LOCK_V1',
            'source_post_id' => $context['source_post_id'],
            'target_post_id' => $context['target_post_id'],
        )
    );
}

/** Parse only a lock that is internally bound to the current source and target. */
function kurashinoshirube_existing_update_read_lock(array $context): ?array
{
    $raw = get_option(kurashinoshirube_existing_update_lock_key($context), null);
    if (! is_string($raw) || $raw === '') {
        return null;
    }
    $record = json_decode($raw, true, 12, JSON_BIGINT_AS_STRING);
    if (
        json_last_error() !== JSON_ERROR_NONE
        || ! kurashinoshirube_has_exact_keys(
            $record,
            array(
                'approved_at',
                'approved_by_user_id',
                'approval_reason',
                'decision',
                'operation_sha256',
                'packet_sha256',
                'payload_sha256',
                'pre_state',
                'pre_state_sha256',
                'request_sha256',
                'rollback_artifact',
                'schema',
                'source_post_id',
                'target_post_id',
            )
        )
        || kurashinoshirube_canonical_json($record) !== $raw
        || ($record['schema'] ?? null) !== 'RAOS_AT003_HUMAN_UPDATE_LOCK_V1'
        || ($record['decision'] ?? null) !== 'APPROVE_AT003_EXISTING_UPDATE'
        || ! is_int($record['approved_by_user_id'] ?? null)
        || $record['approved_by_user_id'] <= 0
        || ! is_string($record['approved_at'] ?? null)
        || ! kurashinoshirube_is_nullable_timestamp($record['approved_at'] ?? null)
        || ! kurashinoshirube_is_clean_text(
            $record['approval_reason'] ?? null,
            10,
            300
        )
        || ($record['packet_sha256'] ?? null) !== $context['packet_sha256']
        || ($record['payload_sha256'] ?? null) !== $context['payload_sha256']
        || ($record['request_sha256'] ?? null) !== $context['request_sha256']
        || ($record['source_post_id'] ?? null) !== $context['source_post_id']
        || ($record['target_post_id'] ?? null) !== $context['target_post_id']
        || ! is_array($record['pre_state'] ?? null)
        || ! is_array($record['rollback_artifact'] ?? null)
    ) {
        return null;
    }
    $rollback = $record['rollback_artifact'];
    if (
        ! kurashinoshirube_has_exact_keys(
            $rollback,
            array(
                'invariants',
                'post_content',
                'post_excerpt',
                'post_title',
                'snapshot_raw',
            )
        )
        || ! is_string($rollback['post_content'] ?? null)
        || ! is_string($rollback['post_excerpt'] ?? null)
        || ! is_string($rollback['post_title'] ?? null)
        || ! is_string($rollback['snapshot_raw'] ?? null)
        || ! is_array($rollback['invariants'] ?? null)
        || ($record['pre_state']['invariants'] ?? null) !== $rollback['invariants']
        || hash('sha256', $rollback['post_content'])
            !== ($record['pre_state']['content_sha256'] ?? null)
        || hash('sha256', $rollback['post_excerpt'])
            !== ($record['pre_state']['excerpt_sha256'] ?? null)
        || hash('sha256', $rollback['post_title'])
            !== ($record['pre_state']['title_sha256'] ?? null)
        || hash('sha256', $rollback['snapshot_raw'])
            !== ($record['pre_state']['snapshot_sha256'] ?? null)
    ) {
        return null;
    }
    $pre_state_json = kurashinoshirube_canonical_json($record['pre_state']);
    $operation_json = kurashinoshirube_canonical_json(
        array(
            'packet_sha256' => $record['packet_sha256'],
            'payload_sha256' => $record['payload_sha256'],
            'pre_state_sha256' => is_string($pre_state_json)
                ? hash('sha256', $pre_state_json)
                : null,
            'request_sha256' => $record['request_sha256'],
            'source_post_id' => $record['source_post_id'],
            'target_post_id' => $record['target_post_id'],
        )
    );
    if (
        $pre_state_json === null
        || $operation_json === null
        || ($record['pre_state_sha256'] ?? null)
            !== hash('sha256', $pre_state_json)
        || ! is_string($record['operation_sha256'] ?? null)
        || ! hash_equals(
            $record['operation_sha256'],
            hash('sha256', $operation_json)
        )
    ) {
        return null;
    }
    return $record;
}

/** Re-read the Review Draft immediately before any public-post write. */
function kurashinoshirube_existing_update_source_matches(array $context): bool
{
    $source = get_post($context['source_post_id']);
    $snapshot_raw = get_post_meta(
        $context['source_post_id'],
        KURASHINOSHIRUBE_SNAPSHOT_META_KEY,
        true
    );
    $bound = kurashinoshirube_bound_post_snapshot(
        $context['source_post_id'],
        true
    );
    return $source instanceof WP_Post
        && $source->post_status === 'draft'
        && $source->post_name === 'raos-review-' . $context['public_slug'] . '-'
            . $context['payload_sha256']
        && $source->post_title === $context['source_title']
        && $source->post_excerpt === $context['source_excerpt']
        && $source->post_content === $context['source_content']
        && is_string($snapshot_raw)
        && $snapshot_raw === $context['snapshot_raw']
        && $bound !== null
        && $bound['packet_sha256'] === $context['packet_sha256'];
}

/** Confirm that the public target exactly reflects the reviewed draft. */
function kurashinoshirube_existing_update_target_matches(
    array $context,
    array $locked_pre_state
): bool {
    $target = get_post($context['target_post_id']);
    $snapshot_raw = get_post_meta(
        $context['target_post_id'],
        KURASHINOSHIRUBE_SNAPSHOT_META_KEY,
        true
    );
    $invariants = kurashinoshirube_existing_update_invariants(
        $context['target_post_id']
    );
    $bound = kurashinoshirube_bound_post_snapshot(
        $context['target_post_id'],
        false
    );
    return $target instanceof WP_Post
        && is_string($snapshot_raw)
        && $snapshot_raw === $context['snapshot_raw']
        && $target->post_title === $context['source_title']
        && $target->post_excerpt === $context['source_excerpt']
        && $target->post_content === $context['source_content']
        && is_array($locked_pre_state['invariants'] ?? null)
        && $invariants === $locked_pre_state['invariants']
        && $bound !== null
        && $bound['article_id'] === KURASHINOSHIRUBE_EXISTING_UPDATE_ARTICLE_ID;
}

/** Restore the exact pre-action copy and snapshot; the durable lock remains. */
function kurashinoshirube_rollback_existing_update(array $context): bool
{
    $restored = wp_update_post(
        array(
            'ID' => $context['target_post_id'],
            'post_content' => $context['target_content'],
            'post_excerpt' => $context['target_excerpt'],
            'post_title' => $context['target_title'],
        ),
        true
    );
    update_post_meta(
        $context['target_post_id'],
        KURASHINOSHIRUBE_SNAPSHOT_META_KEY,
        $context['target_snapshot_raw']
    );
    clean_post_cache($context['target_post_id']);
    $target = get_post($context['target_post_id']);
    $snapshot = get_post_meta(
        $context['target_post_id'],
        KURASHINOSHIRUBE_SNAPSHOT_META_KEY,
        true
    );
    return ! is_wp_error($restored)
        && (int) $restored === $context['target_post_id']
        && $target instanceof WP_Post
        && $target->post_title === $context['target_title']
        && $target->post_excerpt === $context['target_excerpt']
        && $target->post_content === $context['target_content']
        && $snapshot === $context['target_snapshot_raw']
        && kurashinoshirube_existing_update_invariants(
            $context['target_post_id']
        ) === $context['pre_state']['invariants'];
}

/** Register one human-only Tools page; it grants no background authority. */
function kurashinoshirube_register_existing_update_page(): void
{
    add_management_page(
        'AT-003の承認済み更新',
        'AT-003の承認済み更新',
        'manage_options',
        KURASHINOSHIRUBE_EXISTING_UPDATE_PAGE,
        'kurashinoshirube_render_existing_update_page'
    );
}
add_action('admin_menu', 'kurashinoshirube_register_existing_update_page');

/** Build the fixed Tools URL carrying only journal assertions, never authority. */
function kurashinoshirube_existing_update_admin_url(array $context): string
{
    return add_query_arg(
        array(
            'packet_sha256' => $context['packet_sha256'],
            'page' => KURASHINOSHIRUBE_EXISTING_UPDATE_PAGE,
            'payload_sha256' => $context['payload_sha256'],
            'request_sha256' => $context['request_sha256'],
            'review_draft_id' => $context['source_post_id'],
            'target_public_post_id' => $context['target_post_id'],
        ),
        admin_url('tools.php')
    );
}

/** Render the exact hashes and IDs that the human must confirm before POST. */
function kurashinoshirube_render_existing_update_page(): void
{
    if (! current_user_can('manage_options') || ! current_user_can('publish_posts')) {
        wp_die(esc_html('この操作を実行する権限がありません。'), '', array('response' => 403));
    }
    $payload_sha256 = kurashinoshirube_read_sha256_input(
        INPUT_GET,
        'payload_sha256'
    );
    $packet_sha256 = kurashinoshirube_read_sha256_input(
        INPUT_GET,
        'packet_sha256'
    );
    $request_sha256 = kurashinoshirube_read_sha256_input(
        INPUT_GET,
        'request_sha256'
    );
    $source_post_id = kurashinoshirube_read_post_id_input(
        INPUT_GET,
        'review_draft_id'
    );
    $target_post_id = kurashinoshirube_read_post_id_input(
        INPUT_GET,
        'target_public_post_id'
    );
    echo '<div class="wrap"><h1>AT-003の承認済み更新</h1>';
    if (
        $payload_sha256 === null
        || $packet_sha256 === null
        || $request_sha256 === null
        || $source_post_id === null
        || $target_post_id === null
    ) {
        echo '<p>CLI receiptが出力した5つのjournal assertionをURLに指定してください。</p></div>';
        return;
    }
    $context = kurashinoshirube_existing_update_context(
        $payload_sha256,
        $packet_sha256,
        $request_sha256,
        $source_post_id,
        $target_post_id
    );
    if (
        $context === null
        || ! current_user_can('edit_post', $context['source_post_id'])
        || ! current_user_can('edit_post', $context['target_post_id'])
    ) {
        echo '<div class="notice notice-error"><p>固定された更新条件を確認できません。</p></div></div>';
        return;
    }
    $lock = kurashinoshirube_existing_update_read_lock($context);
    if ($lock !== null) {
        if (
            kurashinoshirube_existing_update_target_matches(
                $context,
                $lock['pre_state']
            )
        ) {
            echo '<div class="notice notice-success"><p>この承認済み更新は適用済みです。</p></div></div>';
            return;
        }
        echo '<div class="notice notice-error"><p>同じsnapshotの操作ロックがあります。自動再試行せず監査してください。</p></div></div>';
        return;
    }
    echo '<p>次の不変値を公開確認記録と照合してください。このボタンは既存公開投稿を直ちに更新します。</p>';
    echo '<table class="widefat striped"><tbody>';
    foreach (
        array(
            'Review Draft投稿ID' => (string) $context['source_post_id'],
            '既存公開投稿ID' => (string) $context['target_post_id'],
            'packet SHA-256' => $context['packet_sha256'],
            'payload SHA-256' => $context['payload_sha256'],
            'request SHA-256' => $context['request_sha256'],
            '更新前状態 SHA-256' => $context['pre_state_sha256'],
            '操作 SHA-256' => $context['operation_sha256'],
        ) as $label => $value
    ) {
        echo '<tr><th scope="row">' . esc_html($label) . '</th><td><code>'
            . esc_html($value) . '</code></td></tr>';
    }
    echo '</tbody></table><form method="post" action="'
        . esc_url(admin_url('admin-post.php')) . '">';
    echo '<input type="hidden" name="action" value="'
        . esc_attr(KURASHINOSHIRUBE_EXISTING_UPDATE_ACTION) . '">';
    echo '<input type="hidden" name="payload_sha256" value="'
        . esc_attr($context['payload_sha256']) . '">';
    echo '<input type="hidden" name="packet_sha256" value="'
        . esc_attr($context['packet_sha256']) . '">';
    echo '<input type="hidden" name="request_sha256" value="'
        . esc_attr($context['request_sha256']) . '">';
    echo '<input type="hidden" name="review_draft_id" value="'
        . esc_attr((string) $context['source_post_id']) . '">';
    echo '<input type="hidden" name="target_public_post_id" value="'
        . esc_attr((string) $context['target_post_id']) . '">';
    echo '<input type="hidden" name="pre_state_sha256" value="'
        . esc_attr($context['pre_state_sha256']) . '">';
    echo '<input type="hidden" name="operation_sha256" value="'
        . esc_attr($context['operation_sha256']) . '">';
    echo '<p><label for="raos-approval-reason"><strong>公開更新の理由</strong></label><br>'
        . '<textarea id="raos-approval-reason" name="approval_reason" '
        . 'required minlength="10" maxlength="300" rows="3" cols="70"></textarea></p>';
    echo '<p><label for="raos-reauthentication-password"><strong>再認証</strong></label><br>'
        . '<input id="raos-reauthentication-password" type="password" '
        . 'name="reauthentication_password" required autocomplete="current-password">'
        . '<br><span class="description">現在のWordPress認証情報は照合だけに使い、保存しません。</span></p>';
    wp_nonce_field(
        KURASHINOSHIRUBE_EXISTING_UPDATE_ACTION
        . '|' . $context['operation_sha256']
    );
    submit_button('確認したAT-003 snapshotを既存投稿へ適用');
    echo '</form></div>';
}

/** Execute only the explicit, nonce-bound human update of existing AT-003. */
function kurashinoshirube_handle_existing_update(): void
{
    $method = filter_input(INPUT_SERVER, 'REQUEST_METHOD', FILTER_UNSAFE_RAW);
    if (
        $method !== 'POST'
        || ! current_user_can('manage_options')
        || ! current_user_can('publish_posts')
    ) {
        wp_die(esc_html('この操作を実行できません。'), '', array('response' => 403));
    }
    $payload_sha256 = kurashinoshirube_read_sha256_input(
        INPUT_POST,
        'payload_sha256'
    );
    $packet_sha256 = kurashinoshirube_read_sha256_input(
        INPUT_POST,
        'packet_sha256'
    );
    $request_sha256 = kurashinoshirube_read_sha256_input(
        INPUT_POST,
        'request_sha256'
    );
    $source_post_id = kurashinoshirube_read_post_id_input(
        INPUT_POST,
        'review_draft_id'
    );
    $target_post_id = kurashinoshirube_read_post_id_input(
        INPUT_POST,
        'target_public_post_id'
    );
    $pre_state_sha256 = kurashinoshirube_read_sha256_input(
        INPUT_POST,
        'pre_state_sha256'
    );
    $operation_sha256 = kurashinoshirube_read_sha256_input(
        INPUT_POST,
        'operation_sha256'
    );
    $approval_reason = filter_input(
        INPUT_POST,
        'approval_reason',
        FILTER_UNSAFE_RAW,
        FILTER_REQUIRE_SCALAR
    );
    $reauthentication_password = filter_input(
        INPUT_POST,
        'reauthentication_password',
        FILTER_UNSAFE_RAW,
        FILTER_REQUIRE_SCALAR
    );
    if (
        $payload_sha256 === null
        || $packet_sha256 === null
        || $request_sha256 === null
        || $source_post_id === null
        || $target_post_id === null
        || $pre_state_sha256 === null
        || $operation_sha256 === null
        || ! kurashinoshirube_is_clean_text($approval_reason, 10, 300)
        || ! is_string($reauthentication_password)
        || $reauthentication_password === ''
        || strlen($reauthentication_password) > 4096
    ) {
        wp_die(esc_html('更新assertionが不正です。'), '', array('response' => 400));
    }
    $context = kurashinoshirube_existing_update_context(
        $payload_sha256,
        $packet_sha256,
        $request_sha256,
        $source_post_id,
        $target_post_id
    );
    if (
        $context === null
        || ! current_user_can('edit_post', $context['source_post_id'])
        || ! current_user_can('edit_post', $context['target_post_id'])
    ) {
        wp_die(esc_html('固定された更新条件を確認できません。'), '', array('response' => 409));
    }
    $existing_lock = kurashinoshirube_existing_update_read_lock($context);
    if ($existing_lock !== null) {
        if (
            kurashinoshirube_existing_update_target_matches(
                $context,
                $existing_lock['pre_state']
            )
        ) {
            wp_safe_redirect(
                kurashinoshirube_existing_update_admin_url($context)
            );
            exit;
        }
        wp_die(esc_html('操作ロックと公開状態が一致しません。'), '', array('response' => 409));
    }
    if (
        ! hash_equals($context['pre_state_sha256'], $pre_state_sha256)
        || ! hash_equals($context['operation_sha256'], $operation_sha256)
    ) {
        wp_die(esc_html('更新前状態が変化しました。'), '', array('response' => 409));
    }
    check_admin_referer(
        KURASHINOSHIRUBE_EXISTING_UPDATE_ACTION . '|' . $operation_sha256
    );
    $current_user = wp_get_current_user();
    $authenticated_user = $current_user instanceof WP_User
        ? wp_authenticate(
            $current_user->user_login,
            $reauthentication_password
        )
        : new WP_Error('raos_step_up_failed');
    $reauthentication_password = '';
    if (
        is_wp_error($authenticated_user)
        || ! ($authenticated_user instanceof WP_User)
        || ! ($current_user instanceof WP_User)
        || (int) $authenticated_user->ID !== (int) $current_user->ID
    ) {
        wp_die(esc_html('再認証に失敗しました。'), '', array('response' => 403));
    }
    $lock_record = kurashinoshirube_existing_update_lock_record(
        $context,
        (int) $current_user->ID,
        gmdate('Y-m-d\TH:i:s\Z'),
        $approval_reason
    );
    if (
        $lock_record === null
        || ! add_option(
            kurashinoshirube_existing_update_lock_key($context),
            $lock_record,
            '',
            false
        )
    ) {
        wp_die(esc_html('操作ロックを取得できません。'), '', array('response' => 409));
    }
    if (
        ! function_exists('wp_check_post_lock')
        || wp_check_post_lock($context['target_post_id']) !== false
        || ! kurashinoshirube_existing_update_source_matches($context)
        || kurashinoshirube_existing_update_pre_state(
            $context['target_post_id']
        ) !== $context['pre_state']
    ) {
        wp_die(esc_html('投稿の編集状態が変化しました。操作ロックを監査してください。'), '', array('response' => 409));
    }

    update_post_meta(
        $context['target_post_id'],
        KURASHINOSHIRUBE_SNAPSHOT_META_KEY,
        $context['snapshot_raw']
    );
    $stored_snapshot = get_post_meta(
        $context['target_post_id'],
        KURASHINOSHIRUBE_SNAPSHOT_META_KEY,
        true
    );
    if ($stored_snapshot !== $context['snapshot_raw']) {
        kurashinoshirube_rollback_existing_update($context);
        wp_die(esc_html('snapshot更新を検証できません。旧状態を確認してください。'), '', array('response' => 500));
    }
    $updated = wp_update_post(
        array(
            'ID' => $context['target_post_id'],
            'post_content' => $context['source_content'],
            'post_excerpt' => $context['source_excerpt'],
            'post_title' => $context['source_title'],
        ),
        true
    );
    clean_post_cache($context['target_post_id']);
    if (
        is_wp_error($updated)
        || (int) $updated !== $context['target_post_id']
        || ! kurashinoshirube_existing_update_target_matches(
            $context,
            $context['pre_state']
        )
    ) {
        $rolled_back = kurashinoshirube_rollback_existing_update($context);
        wp_die(
            esc_html(
                $rolled_back
                    ? '更新検証に失敗し、旧状態へ戻しました。操作ロックを監査してください。'
                    : '更新検証と復元に失敗しました。公開面を直ちに確認してください。'
            ),
            '',
            array('response' => 500)
        );
    }
    wp_safe_redirect(
        kurashinoshirube_existing_update_admin_url($context)
    );
    exit;
}
add_action(
    'admin_post_' . KURASHINOSHIRUBE_EXISTING_UPDATE_ACTION,
    'kurashinoshirube_handle_existing_update'
);

add_action('after_setup_theme', static function (): void {
    add_theme_support('title-tag');
    add_theme_support('responsive-embeds');
    add_theme_support('html5', array('caption', 'comment-form', 'comment-list', 'gallery', 'search-form', 'style', 'script'));
});

/** Let Yoast own the title when active, preserving the platform fallback. */
function kurashinoshirube_select_document_title_owner(): void
{
    if (! defined('WPSEO_VERSION')) {
        return;
    }
    foreach (
        array(
            '_wp_render_title_tag',
            '_block_template_render_title_tag',
            'gutenberg_render_title_tag',
        ) as $callback
    ) {
        remove_action('wp_head', $callback, 1);
    }
}
add_action(
    'wp_head',
    'kurashinoshirube_select_document_title_owner',
    0
);

add_action('wp_enqueue_scripts', static function (): void {
    $theme = wp_get_theme();
    wp_enqueue_style(
        'kurashinoshirube-editorial',
        get_stylesheet_directory_uri() . '/assets/theme.css',
        array(),
        $theme->get('Version')
    );
});

/** Identify ordinary posts that opt into the bounded Editorial V2 presentation. */
function kurashinoshirube_is_editorial_v2_post(): bool
{
    if (! is_singular('post')) {
        return false;
    }
    $post_id = get_queried_object_id();
    if ($post_id <= 0 || get_post_type($post_id) !== 'post') {
        return false;
    }
    return kurashinoshirube_post_has_editorial_v2_root($post_id);
}

/** Keep all ten production Editorial V2 section labels slug-bound and closed. */
function kurashinoshirube_editorial_v2_section_map(): array
{
    $sections = array();
    foreach (kurashinoshirube_editorial_v2_publication_bindings() as $binding) {
        if (
            is_array($binding)
            && is_string($binding['slug'] ?? null)
            && is_string($binding['section'] ?? null)
        ) {
            $sections[$binding['slug']] = $binding['section'];
        }
    }
    return count($sections) === 10 ? $sections : array();
}

/** Add the page-level style hook only for exact Editorial V2 post markup. */
function kurashinoshirube_editorial_v2_body_class(array $classes): array
{
    if (is_front_page()) {
        $classes[] = 'raos-home-v2-page';
    }
    if (kurashinoshirube_is_editorial_v2_post()) {
        $classes[] = 'raos-editorial-v2-page';
    }
    return array_values(array_unique($classes));
}
add_filter('body_class', 'kurashinoshirube_editorial_v2_body_class');

/** Keep the reference-matched stylesheet off unrelated public pages. */
function kurashinoshirube_enqueue_editorial_v2_stylesheet(): void
{
    if (! kurashinoshirube_is_editorial_v2_post()) {
        return;
    }
    $theme = wp_get_theme();
    wp_enqueue_style(
        'kurashinoshirube-editorial-v2',
        get_stylesheet_directory_uri() . '/assets/editorial-v2.css',
        array('kurashinoshirube-editorial'),
        $theme->get('Version')
    );
}
add_action(
    'wp_enqueue_scripts',
    'kurashinoshirube_enqueue_editorial_v2_stylesheet',
    20
);

/** Render the predecessor-bound lead illustration without media authority. */
function kurashinoshirube_render_first_article_lead_image($attributes, $content, $tag): string
{
    if (
        $attributes !== array()
        || ! in_array($content, array(null, ''), true)
        || $tag !== 'kurashinoshirube_first_article_lead_image'
        || ! is_singular('post')
        || get_post_field('post_title', get_the_ID(), 'raw')
            !== 'エースの機内持ち込みスーツケース3モデル比較｜軽さ・容量・開き方で選ぶ'
        || get_post_field('post_name', get_the_ID(), 'raw')
            !== 'carry-on-suitcase-comparison'
        || get_stylesheet() !== 'kurashinoshirube-child'
    ) {
        return '';
    }
    $image_uri = kurashinoshirube_verified_asset_uri(
        KURASHINOSHIRUBE_ARTICLE_IMAGE_PATH,
        KURASHINOSHIRUBE_ARTICLE_IMAGE_SHA256
    );
    if ($image_uri === null) {
        return '';
    }
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

/** Render a theme-owned, non-product hero for the two portable-power guides. */
function kurashinoshirube_render_article_hero($attributes, $content, $tag): string
{
    if (
        $attributes !== array()
        || ! in_array($content, array(null, ''), true)
        || $tag !== 'kurashinoshirube_article_hero'
        || ! is_singular('post')
        || ! in_array(
            get_post_field('post_name', get_the_ID(), 'raw'),
            array(
                'portable-power-station-guide',
                'anker-solix-c300-c800-c1000-differences',
            ),
            true
        )
        || get_stylesheet() !== 'kurashinoshirube-child'
    ) {
        return '';
    }
    $image_uri = kurashinoshirube_verified_asset_uri(
        KURASHINOSHIRUBE_POWER_ARTICLE_IMAGE_PATH,
        KURASHINOSHIRUBE_POWER_ARTICLE_IMAGE_SHA256
    );
    if ($image_uri === null) {
        return '';
    }
    return '<figure class="wp-block-image size-full raos-article-hero-image">'
        . '<img src="' . esc_url($image_uri) . '" alt="" width="1536" height="1024">'
        . '<figcaption>停電への備えを、置き場所と持ち運び方から考えるためのイメージ</figcaption>'
        . '</figure>';
}
add_shortcode(
    'kurashinoshirube_article_hero',
    'kurashinoshirube_render_article_hero'
);

/** Render a visible breadcrumb whose current label cannot inject markup. */
function kurashinoshirube_render_breadcrumb($attributes, $content, $tag): string
{
    if (
        $attributes !== array()
        || ! in_array($content, array(null, ''), true)
        || $tag !== 'kurashinoshirube_breadcrumb'
        || ! is_singular('post')
    ) {
        return '';
    }
    $title = get_post_field('post_title', get_the_ID(), 'raw');
    if (! kurashinoshirube_is_clean_text($title, 1, 100)) {
        return '';
    }
    return '<nav class="raos-breadcrumb" aria-label="パンくずリスト"><ol>'
        . '<li><a href="' . esc_url(home_url('/')) . '">ホーム</a></li>'
        . '<li aria-current="page">' . esc_html($title) . '</li>'
        . '</ol></nav>';
}
add_shortcode('kurashinoshirube_breadcrumb', 'kurashinoshirube_render_breadcrumb');

/** Render a bounded article category label from the pilot or Editorial V2 identity. */
function kurashinoshirube_render_article_category($attributes, $content, $tag): string
{
    if (
        $attributes !== array()
        || ! in_array($content, array(null, ''), true)
        || $tag !== 'kurashinoshirube_article_category'
        || ! is_singular('post')
    ) {
        return '';
    }
    $section = null;
    $snapshot = kurashinoshirube_current_snapshot();
    if ($snapshot !== null) {
        $binding = kurashinoshirube_article_bindings()[$snapshot['article_id']] ?? null;
        if (is_array($binding) && is_string($binding['section'] ?? null)) {
            $section = $binding['section'];
        }
    } elseif (kurashinoshirube_is_editorial_v2_post()) {
        $post_id = get_queried_object_id();
        $slug = get_post_field('post_name', $post_id, 'raw');
        if (is_string($slug)) {
            $section = kurashinoshirube_editorial_v2_section_map()[$slug] ?? null;
        }
        if ($section === null) {
            $terms = wp_get_post_terms(
                $post_id,
                'category',
                array('fields' => 'names')
            );
            if (! is_wp_error($terms) && is_array($terms)) {
                foreach (array('移動', '家事') as $allowed_section) {
                    if (in_array($allowed_section, $terms, true)) {
                        $section = $allowed_section;
                        break;
                    }
                }
            }
        }
    }
    if ($section === null) {
        return '';
    }
    return '<p class="raos-article-category">' . esc_html($section)
        . '／比較ガイド</p>';
}
add_shortcode(
    'kurashinoshirube_article_category',
    'kurashinoshirube_render_article_category'
);

/**
 * Render theme-owned related navigation after the hash-bound article copy.
 * A target is linked only after its exact allowlisted route is public.
 */
function kurashinoshirube_render_related_guides($attributes, $content, $tag): string
{
    if (
        $attributes !== array()
        || ! in_array($content, array(null, ''), true)
        || $tag !== 'kurashinoshirube_related_guides'
    ) {
        return '';
    }
    $post_id = (int) get_the_ID();
    $identity = kurashinoshirube_public_article_identity($post_id);
    if (
        $identity === null
        || get_post_status($post_id) !== 'publish'
    ) {
        return '';
    }
    $relation = kurashinoshirube_related_article_map()[$identity['article_id']] ?? null;
    if (! is_array($relation)) {
        return '';
    }
    $items = array();
    foreach ($relation['targets'] as $target_id => $label) {
        $binding = kurashinoshirube_article_bindings()[$target_id] ?? null;
        if (! is_array($binding)) {
            return '';
        }
        $target_slug = $binding['slug'];
        $target = get_page_by_path($target_slug, OBJECT, 'post');
        $expected_url = KURASHINOSHIRUBE_SITE_ORIGIN . '/' . $target_slug . '/';
        if (
            ! ($target instanceof WP_Post)
            || get_post_status($target) !== 'publish'
            || get_post_field('post_name', $target->ID, 'raw') !== $target_slug
            || get_permalink($target) !== $expected_url
        ) {
            continue;
        }
        $target_identity = kurashinoshirube_public_article_identity(
            (int) $target->ID
        );
        if (
            $target_identity === null
            || $target_identity['article_id'] !== $target_id
        ) {
            continue;
        }
        $items[] = '<li><a href="' . esc_url($expected_url) . '">'
            . esc_html($label) . '</a></li>';
    }
    $home_url = KURASHINOSHIRUBE_SITE_ORIGIN . '/#' . $relation['home_anchor'];
    $items[] = '<li><a href="' . esc_url($home_url) . '">'
        . esc_html($relation['home_label']) . '</a></li>';
    return '<aside class="raos-related-guides" aria-labelledby="raos-related-title">'
        . '<h2 id="raos-related-title">関連記事</h2><ul>'
        . implode('', $items) . '</ul></aside>';
}
add_shortcode(
    'kurashinoshirube_related_guides',
    'kurashinoshirube_render_related_guides'
);

/** Return true only inside the repository-owned, network-isolated preview. */
function kurashinoshirube_is_local_preview(): bool
{
    return defined('RAOS_LOCAL_PREVIEW')
        && RAOS_LOCAL_PREVIEW === true
        && function_exists('wp_get_environment_type')
        && wp_get_environment_type() === 'local'
        && home_url('/') === 'http://127.0.0.1:8888/'
        && site_url('/') === 'http://127.0.0.1:8888/';
}

/**
 * Resolve the fixed featured article without widening production eligibility.
 * The isolated local preview may substitute one synthetic post for layout checks.
 */
function kurashinoshirube_homepage_featured_post(): ?WP_Post
{
    static $resolved = false;
    static $cached = null;
    if ($resolved) {
        return $cached instanceof WP_Post ? $cached : null;
    }
    $resolved = true;
    $article_id = KURASHINOSHIRUBE_HOMEPAGE_FEATURED_ARTICLE_ID;
    $binding = kurashinoshirube_article_bindings()[$article_id] ?? null;
    if (is_array($binding)) {
        $slug = $binding['slug'];
        $post = get_page_by_path($slug, OBJECT, 'post');
        $identity = $post instanceof WP_Post
            ? kurashinoshirube_public_article_identity((int) $post->ID)
            : null;
        $expected_permalink = KURASHINOSHIRUBE_SITE_ORIGIN . '/' . $slug . '/';
        if (
            $post instanceof WP_Post
            && get_post_status($post) === 'publish'
            && $identity !== null
            && $identity['article_id'] === $article_id
            && get_permalink($post) === $expected_permalink
        ) {
            $cached = $post;
            return $post;
        }
    }
    if (! kurashinoshirube_is_local_preview()) {
        return null;
    }
    $ids = get_posts(
        array(
            'fields' => 'ids',
            'numberposts' => 1,
            'order' => 'DESC',
            'orderby' => 'modified',
            'post_status' => 'publish',
            'post_type' => 'post',
            'suppress_filters' => false,
        )
    );
    if (! is_array($ids) || count($ids) !== 1 || (int) $ids[0] <= 0) {
        return null;
    }
    $post = get_post((int) $ids[0]);
    $slug = $post instanceof WP_Post
        ? get_post_field('post_name', $post->ID, 'raw')
        : null;
    if (
        ! ($post instanceof WP_Post)
        || ! is_string($slug)
        || preg_match('/\Alocal-preview-[a-z0-9-]+\z/D', $slug) !== 1
    ) {
        return null;
    }
    $cached = $post;
    return $post;
}

/** Resolve a bounded reader-facing section label for a homepage post. */
function kurashinoshirube_homepage_post_section(WP_Post $post): ?string
{
    foreach (kurashinoshirube_article_bindings() as $binding) {
        if (($binding['slug'] ?? null) === $post->post_name) {
            return $binding['section'];
        }
    }
    if (! kurashinoshirube_is_local_preview()) {
        return null;
    }
    $terms = wp_get_post_terms($post->ID, 'category', array('fields' => 'names'));
    if (is_wp_error($terms) || ! is_array($terms)) {
        return null;
    }
    foreach (array('移動', '家事') as $allowed) {
        if (in_array($allowed, $terms, true)) {
            return $allowed;
        }
    }
    return null;
}

/** Render the fixed, public portable-power guide without implying popularity. */
function kurashinoshirube_render_featured_guide($attributes, $content, $tag): string
{
    if (
        $attributes !== array()
        || ! in_array($content, array(null, ''), true)
        || $tag !== 'kurashinoshirube_featured_guide'
        || ! is_front_page()
    ) {
        return '';
    }
    $post = kurashinoshirube_homepage_featured_post();
    if (! ($post instanceof WP_Post)) {
        return '';
    }
    $title = get_post_field('post_title', $post->ID, 'raw');
    $excerpt = get_post_field('post_excerpt', $post->ID, 'raw');
    $modified = get_post_modified_time('Y.m.d', false, $post->ID);
    $permalink = get_permalink($post);
    $section = kurashinoshirube_homepage_post_section($post);
    if (
        ! kurashinoshirube_is_clean_text($title, 1, 140)
        || ! kurashinoshirube_is_clean_text($excerpt, 1, 300)
        || ! is_string($modified)
        || $modified === ''
        || ! is_string($permalink)
        || $permalink === ''
        || $section === null
    ) {
        return '';
    }
    $criteria = $post->post_name === 'portable-power-station-guide'
        ? '容量・出力・重量'
        : '表示確認用fixture';
    $read_label = $title . 'を読む';
    return '<section id="featured" class="raos-featured raos-home-section alignwide" '
        . 'aria-labelledby="raos-featured-title"><div class="raos-home-heading '
        . 'raos-home-heading--split"><div><p class="raos-home-eyebrow">FEATURED GUIDE</p>'
        . '<h2 id="raos-featured-title">今、読んでほしい選び方</h2></div>'
        . '<p>人気順ではなく、いまの比較テーマを編集部が案内します。</p></div>'
        . '<article class="raos-featured-guide"><figure class="raos-featured-guide__visual '
        . 'raos-featured-guide__visual--power"><a href="' . esc_url($permalink)
        . '"><span class="screen-reader-text">' . esc_html($read_label)
        . '</span></a></figure>'
        . '<div class="raos-featured-guide__body"><p class="raos-article-category">'
        . esc_html($section) . 'テーマ／選び方ガイド</p><h3><a href="'
        . esc_url($permalink) . '">' . esc_html($title) . '</a></h3><p>'
        . esc_html($excerpt) . '</p><dl class="raos-featured-guide__facts"><div><dt>基準</dt><dd>'
        . esc_html($criteria) . '</dd></div><div><dt>更新</dt><dd>'
        . esc_html($modified) . '</dd></div></dl><p class="raos-featured-guide__action">'
        . '<a class="raos-home-button raos-home-button--outline" href="'
        . esc_url($permalink) . '">この記事を読む</a></p></div></article></section>';
}
add_shortcode(
    'kurashinoshirube_featured_guide',
    'kurashinoshirube_render_featured_guide'
);

/** Render only synthetic local posts from one allowed preview category. */
function kurashinoshirube_local_preview_cluster_items(string $label): string
{
    if (
        ! kurashinoshirube_is_local_preview()
        || ! in_array($label, array('移動', '家事'), true)
    ) {
        return '';
    }
    $term = get_term_by('name', $label, 'category');
    if (! ($term instanceof WP_Term) || (int) $term->term_id <= 0) {
        return '';
    }
    $posts = get_posts(
        array(
            'category' => (int) $term->term_id,
            'numberposts' => 5,
            'order' => 'DESC',
            'orderby' => 'modified',
            'post_status' => 'publish',
            'post_type' => 'post',
            'suppress_filters' => false,
        )
    );
    if (! is_array($posts)) {
        return '';
    }
    $items = '';
    foreach ($posts as $post) {
        $title = $post instanceof WP_Post
            ? get_post_field('post_title', $post->ID, 'raw')
            : null;
        $slug = $post instanceof WP_Post
            ? get_post_field('post_name', $post->ID, 'raw')
            : null;
        $permalink = $post instanceof WP_Post ? get_permalink($post) : null;
        if (
            ! ($post instanceof WP_Post)
            || ! kurashinoshirube_is_clean_text($title, 1, 140)
            || ! is_string($slug)
            || preg_match('/\Alocal-preview-[a-z0-9-]+\z/D', $slug) !== 1
            || ! is_string($permalink)
            || $permalink === ''
        ) {
            continue;
        }
        $items .= '<li><a href="' . esc_url($permalink) . '">'
            . esc_html($title) . '<span aria-hidden="true">→</span></a></li>';
    }
    return $items;
}

/** Render clusters with links only for posts that are already public. */
function kurashinoshirube_render_published_clusters($attributes, $content, $tag): string
{
    if (
        $attributes !== array()
        || ! in_array($content, array(null, ''), true)
        || $tag !== 'kurashinoshirube_published_clusters'
        || ! is_front_page()
    ) {
        return '';
    }
    $configuration = kurashinoshirube_homepage_clusters();
    if ($configuration === array()) {
        return '';
    }
    $clusters = $configuration['clusters'];

    $sections = '';
    foreach ($configuration['display_order'] as $id) {
        $cluster = $clusters[$id] ?? null;
        if (
            ! is_array($cluster)
            || ! kurashinoshirube_has_exact_keys(
                $cluster,
                array('description', 'heading', 'label', 'post_order', 'posts')
            )
            || ! is_array($cluster['posts'])
            || ! is_array($cluster['post_order'])
            || count($cluster['post_order']) !== count($cluster['posts'])
            || count(array_unique($cluster['post_order']))
                !== count($cluster['post_order'])
        ) {
            return '';
        }
        $post_ids = array_keys($cluster['posts']);
        sort($post_ids, SORT_STRING);
        $ordered_post_ids = $cluster['post_order'];
        sort($ordered_post_ids, SORT_STRING);
        if ($post_ids !== $ordered_post_ids) {
            return '';
        }
        $items = '';
        foreach ($cluster['post_order'] as $article_id) {
            $title = $cluster['posts'][$article_id] ?? null;
            $binding = kurashinoshirube_article_bindings()[$article_id] ?? null;
            if (! is_array($binding) || ! is_string($title)) {
                return '';
            }
            $slug = $binding['slug'];
            $post = get_page_by_path($slug, OBJECT, 'post');
            $identity = $post instanceof WP_Post
                ? kurashinoshirube_public_article_identity((int) $post->ID)
                : null;
            $expected_permalink = KURASHINOSHIRUBE_SITE_ORIGIN . '/' . $slug . '/';
            if (
                ! $post instanceof WP_Post
                || get_post_status($post) !== 'publish'
                || $identity === null
                || $identity['article_id'] !== $article_id
                || get_permalink($post) !== $expected_permalink
            ) {
                continue;
            }
            $items .= '<li><a href="' . esc_url($expected_permalink) . '">'
                . esc_html($title) . '<span aria-hidden="true">→</span></a></li>';
        }
        if ($items === '') {
            $items = kurashinoshirube_local_preview_cluster_items(
                $cluster['label']
            );
        }
        $cluster_body = $items === ''
            ? '<p class="raos-empty-state">このテーマの記事は、根拠と公開条件の確認後に掲載します。</p>'
            : '<ul>' . $items . '</ul>';
        $sections .= '<section id="' . esc_attr($id) . '" class="raos-cluster" '
            . 'aria-labelledby="' . esc_attr($id) . '-title">'
            . '<p class="raos-condition-label">' . esc_html($cluster['label'])
            . '</p><h3 id="' . esc_attr($id) . '-title">'
            . esc_html($cluster['heading']) . '</h3>' . $cluster_body
            . '</section>';
    }
    if ($sections === '') {
        $sections = '<p class="raos-empty-state">カテゴリ別ガイドは、'
            . '根拠と公開条件の確認が完了したものから掲載します。</p>';
    }

    return '<section class="raos-cluster-nav raos-home-section alignwide" '
        . 'aria-labelledby="raos-cluster-nav-title"><div class="raos-home-heading '
        . 'raos-home-heading--split"><div><p class="raos-home-eyebrow">PURPOSE GUIDES</p>'
        . '<h2 id="raos-cluster-nav-title">目的別の記事</h2></div>'
        . '<p>総合1位ではなく、暮らしの条件に近いテーマから記事を選べます。</p>'
        . '</div><div class="raos-clusters">' . $sections . '</div></section>';
}
add_shortcode(
    'kurashinoshirube_published_clusters',
    'kurashinoshirube_render_published_clusters'
);

/** Apply one validated snapshot value through Yoast's single metadata owner. */
function kurashinoshirube_filter_snapshot_value($original, string $field)
{
    $snapshot = kurashinoshirube_current_snapshot();
    return $snapshot === null ? $original : $snapshot[$field];
}

function kurashinoshirube_filter_title($value)
{
    return kurashinoshirube_filter_snapshot_value($value, 'seo_title');
}
function kurashinoshirube_filter_description($value)
{
    return kurashinoshirube_filter_snapshot_value($value, 'description');
}
function kurashinoshirube_filter_canonical($value)
{
    $snapshot = kurashinoshirube_current_snapshot();
    if ($snapshot !== null) {
        return $snapshot['canonical_url'];
    }
    if (! is_singular('post')) {
        return $value;
    }
    $post_id = (int) get_queried_object_id();
    $identity = $post_id > 0
        ? kurashinoshirube_public_article_identity($post_id)
        : null;
    if (
        $identity === null
        || get_post_status($post_id) !== 'publish'
    ) {
        return $value;
    }
    return KURASHINOSHIRUBE_SITE_ORIGIN . '/' . $identity['slug'] . '/';
}
function kurashinoshirube_filter_og_title($value)
{
    return kurashinoshirube_filter_snapshot_value($value, 'og_title');
}
function kurashinoshirube_filter_og_description($value)
{
    return kurashinoshirube_filter_snapshot_value($value, 'og_description');
}
function kurashinoshirube_filter_social_image($value)
{
    if (kurashinoshirube_current_snapshot() === null) {
        return $value;
    }
    $uri = kurashinoshirube_verified_asset_uri(
        KURASHINOSHIRUBE_SOCIAL_IMAGE_PATH,
        KURASHINOSHIRUBE_SOCIAL_IMAGE_SHA256
    );
    return $uri === null ? $value : $uri;
}
function kurashinoshirube_filter_social_image_width($value)
{
    return kurashinoshirube_current_snapshot() === null ? $value : 1600;
}
function kurashinoshirube_filter_social_image_height($value)
{
    return kurashinoshirube_current_snapshot() === null ? $value : 900;
}
function kurashinoshirube_filter_social_image_type($value)
{
    return kurashinoshirube_current_snapshot() === null ? $value : 'image/webp';
}
function kurashinoshirube_filter_twitter_card($value)
{
    return kurashinoshirube_current_snapshot() === null
        ? $value
        : 'summary_large_image';
}

add_filter('wpseo_title', 'kurashinoshirube_filter_title');
add_filter('wpseo_metadesc', 'kurashinoshirube_filter_description');
add_filter('wpseo_canonical', 'kurashinoshirube_filter_canonical');
add_filter('wpseo_opengraph_title', 'kurashinoshirube_filter_og_title');
add_filter('wpseo_opengraph_desc', 'kurashinoshirube_filter_og_description');
add_filter('wpseo_opengraph_url', 'kurashinoshirube_filter_canonical');
add_filter('wpseo_opengraph_image', 'kurashinoshirube_filter_social_image');
add_filter(
    'wpseo_opengraph_image_width',
    'kurashinoshirube_filter_social_image_width'
);
add_filter(
    'wpseo_opengraph_image_height',
    'kurashinoshirube_filter_social_image_height'
);
add_filter('wpseo_opengraph_image_type', 'kurashinoshirube_filter_social_image_type');
add_filter('wpseo_twitter_title', 'kurashinoshirube_filter_og_title');
add_filter('wpseo_twitter_description', 'kurashinoshirube_filter_og_description');
add_filter('wpseo_twitter_image', 'kurashinoshirube_filter_social_image');
add_filter('wpseo_twitter_card_type', 'kurashinoshirube_filter_twitter_card');

/** Index only a review-safe route or one exact public article identity. */
function kurashinoshirube_filter_robots($robots, $presentation)
{
    if (is_singular('post')) {
        $post_id = (int) get_queried_object_id();
        $slug = get_post_field('post_name', $post_id, 'raw');
        $status = get_post_status($post_id);
        $snapshot = kurashinoshirube_current_snapshot();
        if (
            is_string($slug)
            && is_string($status)
            && $status === 'draft'
            && $snapshot !== null
            && kurashinoshirube_review_slug($snapshot) === $slug
        ) {
            return 'noindex, nofollow';
        }
        $identity = kurashinoshirube_public_article_identity($post_id);
        if (
            is_string($slug)
            && $status === 'publish'
            && $identity !== null
            && $identity['slug'] === $slug
        ) {
            return 'index, follow, max-image-preview:large, max-snippet:-1, '
                . 'max-video-preview:-1';
        }
        if (is_string($slug)) {
            if (str_starts_with($slug, 'raos-review-')) {
                return 'noindex, nofollow';
            }
            if (kurashinoshirube_post_has_editorial_v2_root($post_id)) {
                return 'noindex, nofollow';
            }
            foreach (
                kurashinoshirube_editorial_v2_publication_bindings()
                as $binding
            ) {
                $public_slug = $binding['slug'];
                if ($slug === $public_slug) {
                    return 'noindex, nofollow';
                }
            }
        }
    }
    if (
        is_author()
        || is_category()
        || is_tag()
        || is_date()
        || is_search()
        || is_post_type_archive()
        || is_attachment()
    ) {
        return 'noindex, follow';
    }
    return $robots;
}
add_filter('wpseo_robots', 'kurashinoshirube_filter_robots', 20, 2);

/**
 * Apply the one public-listing policy to a candidate post.
 *
 * Review routes are never public-listing eligible. A portfolio final route is
 * eligible only through the shared exact public-identity predicate. All
 * unrelated posts remain eligible.
 */
function kurashinoshirube_public_listing_post_is_eligible(
    int $post_id,
    string $slug
): bool {
    if ($post_id <= 0 || strpos($slug, 'raos-review-') === 0) {
        return false;
    }
    foreach (
        kurashinoshirube_editorial_v2_publication_bindings()
        as $article_id => $binding
    ) {
        if (! is_array($binding) || $slug !== ($binding['slug'] ?? null)) {
            continue;
        }
        $identity = kurashinoshirube_public_article_identity($post_id);
        return $identity !== null
            && ($identity['article_id'] ?? null) === $article_id;
    }
    return ! kurashinoshirube_post_has_editorial_v2_root($post_id);
}

/**
 * Resolve only review routes and allowlisted final routes once per request.
 * The direct database read is bounded to post IDs and slugs; it performs no
 * write and does not create a persistent cache or a generic query surface.
 * Null is a distinct lookup failure which every consumer must suppress.
 */
function kurashinoshirube_public_listing_excluded_post_ids(): ?array
{
    static $resolved = false;
    static $cached = null;
    if ($resolved) {
        return $cached;
    }
    $resolved = true;

    global $wpdb;
    if (
        ! is_object($wpdb)
        || ! isset($wpdb->posts)
        || ! is_string($wpdb->posts)
        || preg_match('/\A[A-Za-z0-9_]+\z/D', $wpdb->posts) !== 1
        || ! method_exists($wpdb, 'esc_like')
        || ! method_exists($wpdb, 'prepare')
        || ! method_exists($wpdb, 'get_results')
    ) {
        return null;
    }

    $final_slugs = array();
    foreach (kurashinoshirube_editorial_v2_publication_bindings() as $binding) {
        if (is_array($binding) && is_string($binding['slug'] ?? null)) {
            $final_slugs[] = $binding['slug'];
        }
    }
    sort($final_slugs, SORT_STRING);
    if (count($final_slugs) !== 10 || count(array_unique($final_slugs)) !== 10) {
        return null;
    }

    // The ten-slot portfolio permits at most two candidate rows per slot. Fetch
    // one sentinel row beyond that closed bound so overflow fails closed.
    $max_candidates_per_slot = 2;
    $max_candidate_rows = count($final_slugs) * $max_candidates_per_slot;
    $query_row_limit = $max_candidate_rows + 1;

    $placeholders = implode(', ', array_fill(0, count($final_slugs), '%s'));
    $editorial_root_like = $wpdb->esc_like(
        KURASHINOSHIRUBE_EDITORIAL_V2_ROOT
    ) . '%';
    $query = $wpdb->prepare(
        "SELECT ID, post_name FROM {$wpdb->posts} "
            . "WHERE post_type = %s AND (post_name LIKE %s "
            . "OR post_name IN ({$placeholders}) OR post_content LIKE %s) "
            . "ORDER BY ID ASC LIMIT %d",
        array_merge(
            array('post', $wpdb->esc_like('raos-review-') . '%'),
            $final_slugs,
            array($editorial_root_like, $query_row_limit)
        )
    );
    if (! is_string($query)) {
        return null;
    }
    $rows = $wpdb->get_results($query);
    if (
        ! isset($wpdb->last_error)
        || ! is_string($wpdb->last_error)
        || $wpdb->last_error !== ''
        || ! is_array($rows)
        || count($rows) > $max_candidate_rows
    ) {
        return null;
    }

    $excluded = array();
    foreach ($rows as $row) {
        $raw_id = is_object($row) && isset($row->ID) ? $row->ID : null;
        $slug = is_object($row) && isset($row->post_name)
            ? $row->post_name
            : null;
        if (
            ! (is_int($raw_id)
                || (is_string($raw_id) && ctype_digit($raw_id)))
            || ! is_string($slug)
        ) {
            return null;
        }
        $post_id = (int) $raw_id;
        if (
            ! kurashinoshirube_public_listing_post_is_eligible(
                $post_id,
                $slug
            )
        ) {
            $excluded[$post_id] = $post_id;
        }
    }
    ksort($excluded, SORT_NUMERIC);
    $cached = array_values($excluded);
    return $cached;
}

/** Normalize a caller-owned exclusion set without widening it. */
function kurashinoshirube_normalize_positive_post_ids($post_ids): array
{
    $normalized = array();
    foreach (is_array($post_ids) ? $post_ids : array() as $post_id) {
        if (
            ! (is_int($post_id)
                || (is_string($post_id) && ctype_digit($post_id)))
            || (int) $post_id <= 0
        ) {
            continue;
        }
        $normalized[(int) $post_id] = (int) $post_id;
    }
    ksort($normalized, SORT_NUMERIC);
    return array_values($normalized);
}

/** Preserve and deduplicate an existing positive post-ID exclusion set. */
function kurashinoshirube_merge_public_listing_exclusions($post_ids): ?array
{
    $excluded = kurashinoshirube_public_listing_excluded_post_ids();
    if ($excluded === null) {
        return null;
    }
    $merged = is_array($post_ids) ? $post_ids : array();
    foreach ($excluded as $post_id) {
        $merged[] = $post_id;
    }
    return kurashinoshirube_normalize_positive_post_ids($merged);
}

/** Exclude non-eligible pilot posts through Yoast's official post-ID filter. */
function kurashinoshirube_sitemap_exclude_post_ids($post_ids): array
{
    $merged = kurashinoshirube_merge_public_listing_exclusions($post_ids);
    return $merged === null
        ? kurashinoshirube_normalize_positive_post_ids($post_ids)
        : $merged;
}
add_filter(
    'wpseo_exclude_from_sitemap_by_post_ids',
    'kurashinoshirube_sitemap_exclude_post_ids',
    20,
    1
);

/** Exclude the same post IDs from the front-page latest-post Query block. */
function kurashinoshirube_filter_front_page_latest_query(
    array $query,
    $block,
    $page
): array {
    if (! is_front_page()) {
        return $query;
    }
    if (
        isset($query['post_type'])
        && $query['post_type'] !== 'post'
        && $query['post_type'] !== array('post')
    ) {
        return $query;
    }
    $requested_exclusions = $query['post__not_in'] ?? array();
    $featured = kurashinoshirube_homepage_featured_post();
    if ($featured instanceof WP_Post) {
        $requested_exclusions[] = (int) $featured->ID;
    }
    $excluded = kurashinoshirube_merge_public_listing_exclusions(
        $requested_exclusions
    );
    if ($excluded === null) {
        $query['post__in'] = array(0);
        return $query;
    }
    $query['post__not_in'] = $excluded;
    return $query;
}
add_filter(
    'query_loop_block_query_vars',
    'kurashinoshirube_filter_front_page_latest_query',
    20,
    3
);

/** Keep the sitemap to post and page URLs only. */
function kurashinoshirube_sitemap_exclude_post_type($excluded, $post_type): bool
{
    if ((bool) $excluded || ! in_array($post_type, array('post', 'page'), true)) {
        return true;
    }
    return $post_type === 'post'
        && kurashinoshirube_public_listing_excluded_post_ids() === null;
}
function kurashinoshirube_sitemap_exclude_taxonomy($excluded, $taxonomy): bool
{
    return true;
}
function kurashinoshirube_sitemap_exclude_authors($users): array
{
    return array();
}
add_filter(
    'wpseo_sitemap_exclude_post_type',
    'kurashinoshirube_sitemap_exclude_post_type',
    20,
    2
);
add_filter(
    'wpseo_sitemap_exclude_taxonomy',
    'kurashinoshirube_sitemap_exclude_taxonomy',
    20,
    2
);
add_filter(
    'wpseo_sitemap_exclude_author',
    'kurashinoshirube_sitemap_exclude_authors',
    20,
    1
);

/** Yoast remains the head owner, but RAOS exclusively owns frontend JSON-LD. */
add_filter('wpseo_json_ld_output', '__return_false', PHP_INT_MAX);

/**
 * Resolve bounded Article values from a legacy snapshot or closed Editorial V2.
 */
function kurashinoshirube_structured_data_article_values(
    int $post_id
): ?array {
    if (
        ! is_singular('post')
        || $post_id <= 0
        || get_post_status($post_id) !== 'publish'
    ) {
        return null;
    }
    $snapshot = kurashinoshirube_current_snapshot();
    if ($snapshot !== null) {
        return array(
            'canonical_url' => $snapshot['canonical_url'],
            'description' => $snapshot['description'],
            'section' => $snapshot['section'],
            'title' => $snapshot['title'],
        );
    }
    $identity = kurashinoshirube_published_editorial_v2_identity($post_id);
    $title = get_post_field('post_title', $post_id, 'raw');
    $description = get_post_field('post_excerpt', $post_id, 'raw');
    $slug = get_post_field('post_name', $post_id, 'raw');
    if (
        $identity === null
        || ! is_string($slug)
        || ($identity['slug'] ?? null) !== $slug
        || ! kurashinoshirube_is_clean_text($title, 8, 100)
        || ! kurashinoshirube_is_clean_text($description, 30, 180)
        || ! is_string($identity['section'] ?? null)
    ) {
        return null;
    }
    return array(
        'canonical_url' => KURASHINOSHIRUBE_SITE_ORIGIN . '/' . $slug . '/',
        'description' => $description,
        'section' => $identity['section'],
        'title' => $title,
    );
}

/** Emit exactly Article, BreadcrumbList, Organization, and WebSite. */
function kurashinoshirube_emit_json_ld(): void
{
    $post_id = (int) get_queried_object_id();
    $article = kurashinoshirube_structured_data_article_values($post_id);
    if ($article === null) {
        return;
    }
    $published = get_post_time('Y-m-d\TH:i:s\Z', true, $post_id);
    $modified = get_post_modified_time('Y-m-d\TH:i:s\Z', true, $post_id);
    $image = kurashinoshirube_verified_asset_uri(
        KURASHINOSHIRUBE_SOCIAL_IMAGE_PATH,
        KURASHINOSHIRUBE_SOCIAL_IMAGE_SHA256
    );
    if (
        ! is_string($published)
        || ! is_string($modified)
        || ! kurashinoshirube_is_nullable_timestamp($published)
        || ! kurashinoshirube_is_nullable_timestamp($modified)
        || strcmp($modified, $published) < 0
        || $image === null
    ) {
        return;
    }
    $canonical = $article['canonical_url'];
    $organization_id = KURASHINOSHIRUBE_SITE_ORIGIN . '/#organization';
    $website_id = KURASHINOSHIRUBE_SITE_ORIGIN . '/#website';
    $graph = array(
        '@context' => 'https://schema.org',
        '@graph' => array(
            array(
                '@id' => $canonical . '#article',
                '@type' => 'Article',
                'articleSection' => $article['section'],
                'author' => array('@id' => $organization_id),
                'dateModified' => $modified,
                'datePublished' => $published,
                'description' => $article['description'],
                'headline' => $article['title'],
                'image' => array($image),
                'inLanguage' => 'ja-JP',
                'mainEntityOfPage' => $canonical,
                'publisher' => array('@id' => $organization_id),
            ),
            array(
                '@id' => $canonical . '#breadcrumb',
                '@type' => 'BreadcrumbList',
                'itemListElement' => array(
                    array(
                        '@type' => 'ListItem',
                        'item' => KURASHINOSHIRUBE_SITE_ORIGIN . '/',
                        'name' => 'ホーム',
                        'position' => 1,
                    ),
                    array(
                        '@type' => 'ListItem',
                        'item' => $canonical,
                        'name' => $article['title'],
                        'position' => 2,
                    ),
                ),
            ),
            array(
                '@id' => $organization_id,
                '@type' => 'Organization',
                'name' => '暮らしのしるべ編集部',
                'url' => KURASHINOSHIRUBE_SITE_ORIGIN . '/',
            ),
            array(
                '@id' => $website_id,
                '@type' => 'WebSite',
                'inLanguage' => 'ja-JP',
                'name' => '暮らしのしるべ',
                'publisher' => array('@id' => $organization_id),
                'url' => KURASHINOSHIRUBE_SITE_ORIGIN . '/',
            ),
        ),
    );
    $json = wp_json_encode(
        $graph,
        JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT
            | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE
    );
    if (is_string($json)) {
        echo '<script id="raos-structured-data" type="application/ld+json">'
            . $json . '</script>' . "\n";
    }
}
add_action('wp_head', 'kurashinoshirube_emit_json_ld', 30);

/** Use the self-owned mark only when WordPress has no human-configured site icon. */
function kurashinoshirube_emit_fallback_icon(): void
{
    if (has_site_icon()) {
        return;
    }
    $uri = kurashinoshirube_verified_asset_uri(
        KURASHINOSHIRUBE_BRAND_MARK_PATH,
        KURASHINOSHIRUBE_BRAND_MARK_SHA256
    );
    if ($uri !== null) {
        echo '<link rel="icon" href="' . esc_url($uri) . '" type="image/svg+xml">' . "\n";
    }
}
add_action('wp_head', 'kurashinoshirube_emit_fallback_icon', 2);

/** Keep the reviewed Yoast release fixed until a separate human-gated update. */
function kurashinoshirube_disable_yoast_auto_update($update, $item)
{
    $slug = is_object($item) && isset($item->slug) ? $item->slug : null;
    $plugin = is_object($item) && isset($item->plugin) ? $item->plugin : null;
    if ($slug === 'wordpress-seo' || $plugin === 'wordpress-seo/wp-seo.php') {
        return false;
    }
    return $update;
}
add_filter('auto_update_plugin', 'kurashinoshirube_disable_yoast_auto_update', 10, 2);

/** Require an explicit visitor choice before optional categories are enabled. */
function kurashinoshirube_wp_consent_type(): string
{
    return 'optin';
}
add_filter('wp_get_consent_type', 'kurashinoshirube_wp_consent_type');

/** Keep WP Consent API choices aligned with CookieYes's reviewed 365-day term. */
function kurashinoshirube_wp_consent_cookie_expiration(): int
{
    return 365;
}
add_filter(
    'wp_cookie_expiration',
    'kurashinoshirube_wp_consent_cookie_expiration'
);

/** Apply Site Kit's denied consent defaults globally, not only in EEA regions. */
function kurashinoshirube_site_kit_global_consent_defaults($defaults)
{
    if (!is_array($defaults)) {
        return $defaults;
    }
    unset($defaults['region']);
    if (array_key_exists('wait_for_update', $defaults)) {
        $defaults['wait_for_update'] = 2000;
    }
    return $defaults;
}
add_filter(
    'googlesitekit_consent_defaults',
    'kurashinoshirube_site_kit_global_consent_defaults'
);

/** Load Site Kit Analytics only after WP Consent API reports statistics consent. */
function kurashinoshirube_gate_site_kit_analytics_loader($tag, $handle)
{
    if (
        !is_string($tag)
        || !is_string($handle)
        || $handle !== 'google_gtagjs'
    ) {
        return $tag;
    }
    if (!preg_match(
        '/<script\b(?=[^>]*\bid=(["\'])google_gtagjs-js\1)'
            . '[^>]*\ssrc=(["\'])([^"\']+)\2[^>]*>/u',
        $tag,
        $source_match
    ) || !isset($source_match[3])) {
        return '';
    }
    $source = html_entity_decode(
        $source_match[3],
        ENT_QUOTES | ENT_HTML5,
        'UTF-8'
    );
    $source_parts = wp_parse_url($source);
    if (
        !is_array($source_parts)
        || ($source_parts['scheme'] ?? '') !== 'https'
        || ($source_parts['host'] ?? '') !== 'www.googletagmanager.com'
        || ($source_parts['path'] ?? '') !== '/gtag/js'
    ) {
        return '';
    }
    $source_json = wp_json_encode(
        $source,
        JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT
    );
    if (!is_string($source_json)) {
        return '';
    }
    $gate = '<script id="google_gtagjs-js" data-raos-consent-gate="statistics">'
        . '(function(){'
        . 'var source=' . $source_json . ';'
        . 'var initialCookieYes=typeof window.getCkyConsent==="function"'
        . '?window.getCkyConsent():null;'
        . 'var eligibleAtParse=!!(initialCookieYes'
        . '&&initialCookieYes.isUserActionCompleted===true'
        . '&&initialCookieYes.categories'
        . '&&initialCookieYes.categories.analytics===true);'
        . 'var activated=false;'
        . 'function consentIsGranted(){'
        . 'if(!eligibleAtParse'
        . '||typeof window.getCkyConsent!=="function"'
        . '||typeof window.wp_has_consent!=="function"){return false;}'
        . 'var cookieYes=window.getCkyConsent();'
        . 'return !!(cookieYes'
        . '&&cookieYes.isUserActionCompleted===true'
        . '&&cookieYes.categories'
        . '&&cookieYes.categories.analytics===true'
        . '&&window.wp_has_consent("statistics")===true'
        . '&&window._googlesitekitConsents'
        . '&&window._googlesitekitConsents.analytics_storage==="granted");'
        . '}'
        . 'function activate(){'
        . 'if(activated||!consentIsGranted()){return;}'
        . 'var loader=document.getElementById("google_gtagjs-js");'
        . 'var config=document.getElementById("google_gtagjs-js-after");'
        . 'if(!loader'
        . '||loader.getAttribute("data-raos-consent-gate")!=="statistics"'
        . '||!config'
        . '||config.getAttribute("data-raos-consent-config")!=="statistics")'
        . '{return;}'
        . 'var parsed;'
        . 'try{parsed=new URL(source);}catch(error){return;}'
        . 'if(parsed.protocol!=="https:"'
        . '||parsed.hostname!=="www.googletagmanager.com"'
        . '||parsed.pathname!=="/gtag/js"){return;}'
        . 'activated=true;'
        . 'var configScript=document.createElement("script");'
        . 'configScript.id="google_gtagjs-js-after";'
        . 'configScript.setAttribute("data-cookieyes","cookieyes-analytics");'
        . 'configScript.type="text/javascript";'
        . 'configScript.text=config.textContent||"";'
        . 'config.replaceWith(configScript);'
        . 'var analytics=document.createElement("script");'
        . 'analytics.id="google_gtagjs-js";'
        . 'analytics.async=true;'
        . 'analytics.setAttribute("data-cookieyes","cookieyes-analytics");'
        . 'analytics.type="text/javascript";'
        . 'analytics.src=source;'
        . 'loader.replaceWith(analytics);'
        . '}'
        . 'document.addEventListener("wp_consent_type_defined",activate);'
        . 'document.addEventListener("wp_listen_for_consent_change",activate);'
        . 'document.addEventListener("cookieyes_consent_update",activate);'
        . 'if(document.readyState==="complete"){activate();}'
        . 'else{window.addEventListener("load",activate,{once:true});}'
        . '})();'
        . '</script>';
    $gated_tag = preg_replace(
        '/<script\b(?=[^>]*\bid=(["\'])google_gtagjs-js\1)'
            . '[^>]*>\s*<\/script>/u',
        $gate,
        $tag,
        1,
        $loader_replacement_count
    );
    if ($loader_replacement_count !== 1 || !is_string($gated_tag)) {
        return '';
    }
    $gated_tag = preg_replace_callback(
        '/<script\b(?=[^>]*\bid=(["\'])google_gtagjs-js-after\1)'
            . '([^>]*)>/u',
        static function (array $match): string {
            return '<script type="text/plain" '
                . 'data-raos-consent-config="statistics"'
                . ($match[2] ?? '')
                . '>';
        },
        $gated_tag,
        1,
        $config_replacement_count
    );
    return $config_replacement_count === 1 && is_string($gated_tag)
        ? $gated_tag
        : '';
}
add_filter(
    'script_loader_tag',
    'kurashinoshirube_gate_site_kit_analytics_loader',
    30,
    2
);
