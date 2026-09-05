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
const KURASHINOSHIRUBE_THEME_VERSION = '1.5.1';
const KURASHINOSHIRUBE_THEME_RUNTIME_REVISION = '78af0ca39c752410c56c8480c275d5807e6821b06aae266501e2eb74ee78099e';
const KURASHINOSHIRUBE_THEME_SOURCE_FINGERPRINT = '78af0ca39c752410c56c8480c275d5807e6821b06aae266501e2eb74ee78099e';
const KURASHINOSHIRUBE_EDITORIAL_V2_ROOT = '<div class="raos-editorial-v2">';
const KURASHINOSHIRUBE_SOCIAL_IMAGE_PATH = 'assets/images/home-hero.webp';
const KURASHINOSHIRUBE_SOCIAL_IMAGE_SHA256 = '9a2d6d390ffd4ef0642d4c0a7a12da9daf7e904934ffd3f9e95e29907aedc493';
const KURASHINOSHIRUBE_ARTICLE_IMAGE_PATH = 'assets/images/article-suitcase-guide.webp';
const KURASHINOSHIRUBE_ARTICLE_IMAGE_SHA256 = 'dc8133377f21355ac0c187273d70904c305dd5687bf0e5e8ce3af76fab668046';
const KURASHINOSHIRUBE_POWER_ARTICLE_IMAGE_PATH = 'assets/images/article-portable-power-guide.webp';
const KURASHINOSHIRUBE_POWER_ARTICLE_IMAGE_SHA256 = '54b84689cff952f6a384982b89d2f56adfbdeff9ff03fe628fcaf5a949ab0f5a';
const KURASHINOSHIRUBE_DISHWASHER_ARTICLE_IMAGE_PATH = 'assets/images/article-countertop-dishwasher-guide.webp';
const KURASHINOSHIRUBE_DISHWASHER_ARTICLE_IMAGE_SHA256 = 'c36e87682ce9be33f70bc5b1a55e20a63b19ab6155172d670d5c019a984bcf9f';
const KURASHINOSHIRUBE_ROBOT_ARTICLE_IMAGE_PATH = 'assets/images/article-robot-vacuum-guide.webp';
const KURASHINOSHIRUBE_ROBOT_ARTICLE_IMAGE_SHA256 = 'f589471aeed1064f2499ec5d32a8e9c4b6b14db8613d3b1743b37d245ecc2384';
const KURASHINOSHIRUBE_SUITCASE_UNDER_100_IMAGE_PATH = 'assets/images/article-suitcase-under-100-seats.webp';
const KURASHINOSHIRUBE_SUITCASE_UNDER_100_IMAGE_SHA256 = '0a2682459af1562593ccae37a877bbae26585f269c86d79775e98c015fd40f10';
const KURASHINOSHIRUBE_SUITCASE_UNDER_3KG_IMAGE_PATH = 'assets/images/article-suitcase-under-3kg.webp';
const KURASHINOSHIRUBE_SUITCASE_UNDER_3KG_IMAGE_SHA256 = '43db66a0e12a20cc8f31f44293691811734a41b0d0afa0374c73cf95d6cfd394';
const KURASHINOSHIRUBE_SUITCASE_FRONT_OPEN_IMAGE_PATH = 'assets/images/article-suitcase-front-open-stopper.webp';
const KURASHINOSHIRUBE_SUITCASE_FRONT_OPEN_IMAGE_SHA256 = '6cffe92e50ce644ae60c72d4acaece34609acaa25a943a41811833063afb9d1e';
const KURASHINOSHIRUBE_ANKER_GENERATIONS_IMAGE_PATH = 'assets/images/article-anker-solix-generations.webp';
const KURASHINOSHIRUBE_ANKER_GENERATIONS_IMAGE_SHA256 = 'b8db0de1e65653539d327c3645f8c0722a71be1b2a8291c338ce7b37bd5545a0';
const KURASHINOSHIRUBE_SOLOTA_RAKUA_IMAGE_PATH = 'assets/images/article-solota-rakua-replacement.webp';
const KURASHINOSHIRUBE_SOLOTA_RAKUA_IMAGE_SHA256 = 'a413f3c1a70282eb0d1362959f746421bec4c1fc640f072eb045d9c4009d3374';
const KURASHINOSHIRUBE_ROOMBA_K11_IMAGE_PATH = 'assets/images/article-roomba-mini-k11-comparison.webp';
const KURASHINOSHIRUBE_ROOMBA_K11_IMAGE_SHA256 = 'a601dd1913fe0c54551e9e894666dd5dd793b36e193d47bb292e85ed22a2b1d2';
const KURASHINOSHIRUBE_BRAND_MARK_PATH = 'assets/images/brand-mark.svg';
const KURASHINOSHIRUBE_BRAND_MARK_SHA256 = 'bd9f84f40eca90fb88b7e8a3967f6d7ceb5d337c6023d1f2ff748936a0f3acf3';
const KURASHINOSHIRUBE_MEASUREMENT_ASSET_PATH = 'assets/measurement.js';
const KURASHINOSHIRUBE_MEASUREMENT_ASSET_SHA256 = '181dff17451e52bb5bc548964e6c951573a4ddde42072ee0f1165bfc6faa1772';
const KURASHINOSHIRUBE_ANALYTICS_CONSENT_GATE_ASSET_PATH = 'assets/analytics-consent-gate.js';
const KURASHINOSHIRUBE_ANALYTICS_CONSENT_GATE_ASSET_SHA256 = '09b2bff8deba45af068ad8566a8d4e237da7da21fd310aaa62fedc10aa24a38a';
const KURASHINOSHIRUBE_NAVIGATION_ASSET_PATH = 'assets/editorial-navigation.js';
const KURASHINOSHIRUBE_NAVIGATION_ASSET_SHA256 = '29fc68a8929aadfb49ef39740b4c7cbc5be66d6a8bd94f1fc5a8dcdc4345eac7';
const KURASHINOSHIRUBE_HOMEPAGE_FEATURED_ARTICLE_ID = 'st1704-portable-power-station-guide';
const KURASHINOSHIRUBE_EXISTING_UPDATE_ARTICLE_ID = 'st1703-first-suitcase-comparison';
const KURASHINOSHIRUBE_EXISTING_UPDATE_ACTION = 'kurashinoshirube_apply_at003_review_v1';
const KURASHINOSHIRUBE_EXISTING_UPDATE_PAGE = 'kurashinoshirube-at003-update-v1';
const KURASHINOSHIRUBE_EXISTING_UPDATE_LOCK_PREFIX = '_raos_at003_update_lock_v1_';
const KURASHINOSHIRUBE_REVIEW_REQUEST_PATH = '/wp-json/wp/v2/posts?_fields=id%2Ctype%2Cslug%2Cstatus%2Ctitle.raw%2Cexcerpt.raw%2Ccontent.raw%2Cmeta._raos_publication_snapshot_v1';
const KURASHINOSHIRUBE_EDITORIAL_NAVIGATION_PATH = 'assets/editorial-navigation.v3.json';
const KURASHINOSHIRUBE_EDITORIAL_NAVIGATION_SHA256 = 'f7a2d9af7fc9405d49847eb5999d66496bf59e3b0a92f9f621bb13222c57e564';
const KURASHINOSHIRUBE_EDITORIAL_NAVIGATION_MAX_BYTES = 262144;
const KURASHINOSHIRUBE_HOME_TITLE = '生活用品を公式仕様で比較｜暮らしのしるべ';
const KURASHINOSHIRUBE_HOME_DESCRIPTION = '暮らしのしるべは、移動・家事・備えの生活用品を、公式情報と確認条件に基づいて比較し、選び方を分かりやすく案内します。';
const KURASHINOSHIRUBE_LEGACY_MEDIA_PROJECTION_SHA256 = '9512b5cde2fe11857e662a745a372bdd5e2281a4b7c73671979c1ea8c56b0ac9';

/** Hash/range-only contract: no copied article prose or remote image fetch. */
function kurashinoshirube_legacy_media_projection_contract(): array
{
    $root = realpath(get_stylesheet_directory());
    $path = get_stylesheet_directory() . '/assets/legacy-media-display-projection.v1.json';
    $resolved = realpath($path);
    if (! is_string($root) || ! is_string($resolved)
        || dirname($resolved) !== $root . '/assets' || is_link($path)
        || ! is_file($path) || ! is_readable($path)
        || filesize($path) < 1 || filesize($path) > 65536) {
        return array();
    }
    $bytes = file_get_contents($path);
    if (! is_string($bytes) || ! hash_equals(
        KURASHINOSHIRUBE_LEGACY_MEDIA_PROJECTION_SHA256, hash('sha256', $bytes)
    )) {
        return array();
    }
    $value = json_decode($bytes, true, 16, JSON_BIGINT_AS_STRING);
    return json_last_error() === JSON_ERROR_NONE && is_array($value) ? $value : array();
}

/** Pure, byte-exact display projection. BLOCKED always retains the input. */
function kurashinoshirube_project_legacy_media(
    string $content,
    string $article_id,
    string $profile,
    array $contract
): array {
    $input_hash = hash('sha256', $content);
    $proof = array(
        'state' => 'NOT_APPLICABLE',
        'contract_sha256' => KURASHINOSHIRUBE_LEGACY_MEDIA_PROJECTION_SHA256,
        'input_sha256' => $input_hash,
        'output_sha256' => $input_hash,
        'profile' => null,
        'removed_decoration_count' => 0,
        'removed_neutral_media_count' => 0,
    );
    $unchanged = static function (string $state) use ($content, $proof): array {
        $proof['state'] = $state;
        return array('markup' => $content, 'proof' => $proof);
    };
    $targets = array(
        'st1704-portable-power-station-guide' => array('portable-power-station-guide', 28, 8, 2),
        'st1704-anker-solix-c300-c800-c1000-differences' => array('anker-solix-c300-c800-c1000-differences', 29, 8, 4),
    );
    $broken = '/wp-content/themes/kurashinoshirube-child/assets/images/article-portable-power-guide.png';
    if (! isset($targets[$article_id])) {
        return $unchanged('NOT_APPLICABLE');
    }
    if (! str_contains($content, $broken)
        && preg_match('/data-raos-product-image-state\s*=\s*["\']neutral["\']/', $content) !== 1) {
        return $unchanged('NOT_APPLICABLE');
    }
    if (! in_array($profile, array('production', 'local-fixture', 'local-stored'), true)
        || ! kurashinoshirube_has_exact_keys($contract, array('schema', 'version', 'broken_image_path', 'articles'))
        || $contract['schema'] !== 'RAOS_LEGACY_MEDIA_DISPLAY_PROJECTION_V1'
        || $contract['version'] !== '1.0.0' || $contract['broken_image_path'] !== $broken
        || ! is_array($contract['articles'])
        || ! kurashinoshirube_has_exact_keys($contract['articles'], array_keys($targets))) {
        return $unchanged('BLOCKED_CONTRACT_INVALID');
    }
    $row = $contract['articles'][$article_id];
    $target = $targets[$article_id];
    if (! is_array($row)
        || ! kurashinoshirube_has_exact_keys($row, array('slug', 'post_id', 'baseline_document_sha256', 'profiles'))
        || $row['slug'] !== $target[0] || $row['post_id'] !== $target[1]
        || ! is_string($row['baseline_document_sha256'])
        || preg_match('/\A[a-f0-9]{64}\z/D', $row['baseline_document_sha256']) !== 1
        || ! is_array($row['profiles'])
        || ! kurashinoshirube_has_exact_keys($row['profiles'], array('production', 'local-fixture', 'local-stored'))) {
        return $unchanged('BLOCKED_CONTRACT_INVALID');
    }
    $rule = $row['profiles'][$profile];
    if (! is_array($rule)
        || ! kurashinoshirube_has_exact_keys($rule, array('input_sha256', 'output_sha256', 'removals'))
        || ! is_string($rule['input_sha256']) || ! is_string($rule['output_sha256'])
        || preg_match('/\A[a-f0-9]{64}\z/D', $rule['output_sha256']) !== 1
        || ! hash_equals($rule['input_sha256'], $input_hash)) {
        return $unchanged('BLOCKED_INPUT_MISMATCH');
    }
    if (! is_array($rule['removals']) || count($rule['removals']) !== $target[2] + $target[3]) {
        return $unchanged('BLOCKED_CONTRACT_INVALID');
    }
    $previous_end = 0;
    $counts = array('decorative-image' => 0, 'neutral-media' => 0);
    foreach ($rule['removals'] as $removal) {
        if (! is_array($removal)
            || ! kurashinoshirube_has_exact_keys($removal, array('offset', 'length', 'sha256', 'kind'))
            || ! is_int($removal['offset']) || ! is_int($removal['length'])
            || $removal['offset'] < $previous_end || $removal['length'] < 1 || $removal['length'] > 4096
            || $removal['offset'] + $removal['length'] > strlen($content)
            || ! is_string($removal['sha256']) || ! is_string($removal['kind'])
            || ! isset($counts[$removal['kind']])) {
            return $unchanged('BLOCKED_CONTRACT_INVALID');
        }
        $fragment = substr($content, $removal['offset'], $removal['length']);
        if (! hash_equals($removal['sha256'], hash('sha256', $fragment))) {
            return $unchanged('BLOCKED_FRAGMENT_MISMATCH');
        }
        $image = $fragment;
        if ($removal['kind'] === 'neutral-media') {
            $prefix = '<div class="raos-product-card__media">';
            if (! str_starts_with($fragment, $prefix) || ! str_ends_with($fragment, '</div>')) {
                return $unchanged('BLOCKED_FRAGMENT_INVALID');
            }
            $image = substr($fragment, strlen($prefix), -6);
        }
        if (preg_match('/\A<img\s+([^<>]+)>\z/D', $image, $match) !== 1
            || preg_match_all('/([a-z][a-z0-9-]*)="([^"<>]*)"/', $match[1], $attributes, PREG_SET_ORDER) < 1) {
            return $unchanged('BLOCKED_FRAGMENT_INVALID');
        }
        $attrs = array();
        foreach ($attributes as $attribute) {
            if (isset($attrs[$attribute[1]])) {
                return $unchanged('BLOCKED_FRAGMENT_INVALID');
            }
            $attrs[$attribute[1]] = html_entity_decode($attribute[2], ENT_QUOTES | ENT_HTML5, 'UTF-8');
        }
        $rest = preg_replace('/[a-z][a-z0-9-]*="[^"<>]*"/', '', $match[1]);
        if (! is_string($rest) || trim($rest) !== '' || ($attrs['src'] ?? null) !== $broken) {
            return $unchanged('BLOCKED_FRAGMENT_INVALID');
        }
        if ($removal['kind'] === 'decorative-image') {
            $expected = array('class' => 'raos-comparison__product-image', 'src' => $broken,
                'alt' => '', 'width' => '64', 'height' => '64', 'loading' => 'lazy');
            ksort($expected); ksort($attrs);
            if ($attrs !== $expected) {
                return $unchanged('BLOCKED_FRAGMENT_INVALID');
            }
        } elseif (! kurashinoshirube_has_exact_keys($attrs, array('src', 'alt', 'width', 'height', 'loading',
            'data-raos-product-image-id', 'data-raos-product-image-state'))
            || $attrs['width'] !== '128' || $attrs['height'] !== '128' || $attrs['loading'] !== 'lazy'
            || $attrs['data-raos-product-image-state'] !== 'neutral'
            || preg_match('/\APRD-[A-Z0-9-]+\z/D', $attrs['data-raos-product-image-id']) !== 1
            || ! str_ends_with($attrs['alt'], 'を比較検討するための中立イメージ。商品写真ではありません')) {
            return $unchanged('BLOCKED_FRAGMENT_INVALID');
        }
        ++$counts[$removal['kind']];
        $previous_end = $removal['offset'] + $removal['length'];
    }
    if ($counts !== array('decorative-image' => $target[2], 'neutral-media' => $target[3])) {
        return $unchanged('BLOCKED_CONTRACT_INVALID');
    }
    $output = $content;
    foreach (array_reverse($rule['removals']) as $removal) {
        $output = substr($output, 0, $removal['offset'])
            . substr($output, $removal['offset'] + $removal['length']);
    }
    if (! hash_equals($rule['output_sha256'], hash('sha256', $output))) {
        return $unchanged('BLOCKED_OUTPUT_MISMATCH');
    }
    $proof['state'] = 'APPLIED';
    $proof['profile'] = $profile;
    $proof['output_sha256'] = hash('sha256', $output);
    $proof['removed_decoration_count'] = $target[2];
    $proof['removed_neutral_media_count'] = $target[3];
    return array('markup' => $output, 'proof' => $proof);
}

/** Render only; never wp_update_post, database writes, CSS hiding or image substitution. */
function kurashinoshirube_filter_legacy_media_display($content)
{
    if (! is_string($content) || ! is_singular('post') || ! in_the_loop() || ! is_main_query()
        || get_stylesheet() !== 'kurashinoshirube-child') {
        return $content;
    }
    $identity = kurashinoshirube_public_article_identity((int) get_the_ID());
    if (! is_array($identity) || get_post_field('post_content', get_the_ID(), 'raw') !== $content) {
        return $content;
    }
    $profile = is_string(kurashinoshirube_local_preview_origin()) ? 'local-stored' : 'production';
    $result = kurashinoshirube_project_legacy_media(
        $content, $identity['article_id'], $profile, kurashinoshirube_legacy_media_projection_contract()
    );
    return $result['markup'];
}
add_filter('the_content', 'kurashinoshirube_filter_legacy_media_display', 1);

/** Load the generated public-safe Editorial V3 navigation or fail closed. */
function kurashinoshirube_editorial_navigation(): array
{
    static $loaded = false;
    static $navigation = array();
    if ($loaded) {
        return $navigation;
    }
    $loaded = true;
    $theme_root = realpath(get_stylesheet_directory());
    $path = get_stylesheet_directory() . '/'
        . KURASHINOSHIRUBE_EDITORIAL_NAVIGATION_PATH;
    $resolved = realpath($path);
    if (
        ! is_string($theme_root)
        || ! is_string($resolved)
        || dirname($resolved) !== $theme_root . '/assets'
        || is_link($path)
        || ! is_file($path)
        || ! is_readable($path)
        || filesize($path) <= 0
        || filesize($path) > KURASHINOSHIRUBE_EDITORIAL_NAVIGATION_MAX_BYTES
    ) {
        return array();
    }
    $bytes = file_get_contents($path);
    if (
        ! is_string($bytes)
        || ! hash_equals(
            KURASHINOSHIRUBE_EDITORIAL_NAVIGATION_SHA256,
            hash('sha256', $bytes)
        )
    ) {
        return array();
    }
    $decoded = json_decode($bytes, true, 16, JSON_BIGINT_AS_STRING);
    if (
        json_last_error() !== JSON_ERROR_NONE
        || ! is_array($decoded)
        || ! kurashinoshirube_has_exact_keys(
            $decoded,
            array(
                'articles',
                'clusters',
                'schema',
                'source_navigation_sha256',
                'source_portfolio_sha256',
                'target_origin',
                'version',
            )
        )
        || $decoded['schema'] !== 'RAOS_EDITORIAL_THEME_NAVIGATION_V3'
        || $decoded['target_origin'] !== KURASHINOSHIRUBE_SITE_ORIGIN
        || $decoded['version'] !== '3.0.0'
        || ! is_array($decoded['articles'])
        || count($decoded['articles']) !== 10
        || ! is_array($decoded['clusters'])
        || count($decoded['clusters']) !== 3
        || ! is_string($decoded['source_navigation_sha256'])
        || preg_match('/\A[0-9a-f]{64}\z/D', $decoded['source_navigation_sha256']) !== 1
        || ! is_string($decoded['source_portfolio_sha256'])
        || preg_match('/\A[0-9a-f]{64}\z/D', $decoded['source_portfolio_sha256']) !== 1
    ) {
        return array();
    }
    $navigation = $decoded;
    return $navigation;
}

/** Return all ten article identities generated from Editorial V3. */
function kurashinoshirube_article_bindings(): array
{
    static $bindings = null;
    if (is_array($bindings)) {
        return $bindings;
    }
    $bindings = array();
    $navigation = kurashinoshirube_editorial_navigation();
    foreach ($navigation['articles'] ?? array() as $article) {
        if (
            ! is_array($article)
            || ! kurashinoshirube_has_exact_keys(
                $article,
                array(
                    'article_code',
                    'article_id',
                    'category_label',
                    'cluster_id',
                    'comparison_scope',
                    'content_role',
                    'content_role_label',
                    'primary_query_intent',
                    'broader_article_id',
                    'home_order',
                    'intent_group_id',
                    'local_slug',
                    'production_slug',
                    'related_articles',
                    'snapshot_id',
                    'title',
                )
            )
            || ! is_string($article['article_id'])
            || preg_match('/\A[a-z0-9]+(?:-[a-z0-9]+)*\z/D', $article['article_id']) !== 1
            || isset($bindings[$article['article_id']])
            || ! is_string($article['production_slug'])
            || preg_match('/\A[a-z0-9]+(?:-[a-z0-9]+)*\z/D', $article['production_slug']) !== 1
            || ! is_string($article['local_slug'])
            || $article['local_slug'] !== 'local-preview-' . $article['production_slug']
            || ! in_array($article['category_label'], array('移動', '家事', '備え'), true)
            || ! is_string($article['intent_group_id'])
            || preg_match('/\A[a-z0-9]+(?:-[a-z0-9]+)*\z/D', $article['intent_group_id']) !== 1
            || ! is_string($article['content_role'])
            || ! isset(
                array(
                    'brand_family_comparison' => 'ブランド内比較',
                    'category_guide' => '選び方',
                    'constraint_shortlist' => '条件別比較',
                    'feature_shortlist' => '機能別比較',
                    'head_to_head_comparison' => '2製品比較',
                    'head_to_head_with_reference' => '2製品比較＋参考機種',
                    'lifecycle_status_route' => '型番・販売表示の確認案内',
                    'model_family_comparison' => 'ブランド内比較',
                )[$article['content_role']]
            )
            || array(
                'brand_family_comparison' => 'ブランド内比較',
                'category_guide' => '選び方',
                'constraint_shortlist' => '条件別比較',
                'feature_shortlist' => '機能別比較',
                'head_to_head_comparison' => '2製品比較',
                'head_to_head_with_reference' => '2製品比較＋参考機種',
                'lifecycle_status_route' => '型番・販売表示の確認案内',
                'model_family_comparison' => 'ブランド内比較',
            )[$article['content_role']] !== $article['content_role_label']
            || ! kurashinoshirube_is_clean_text($article['primary_query_intent'], 1, 180)
            || ! kurashinoshirube_is_clean_text($article['comparison_scope'], 1, 120)
            || (
                $article['broader_article_id'] !== null
                && (
                    ! is_string($article['broader_article_id'])
                    || preg_match(
                        '/\A[a-z0-9]+(?:-[a-z0-9]+)*\z/D',
                        $article['broader_article_id']
                    ) !== 1
                )
            )
            || ! is_string($article['article_code'])
            || preg_match('/\Aa[0-9]{2}\z/D', $article['article_code']) !== 1
            || ! is_string($article['snapshot_id'])
            || preg_match('/\Asnp-a[0-9]{2}-[0-9a-f]{12}\z/D', $article['snapshot_id']) !== 1
        ) {
            $bindings = array();
            return array();
        }
        $bindings[$article['article_id']] = array(
            'article_code' => $article['article_code'],
            'broader_article_id' => $article['broader_article_id'],
            'cluster_id' => $article['cluster_id'],
            'comparison_scope' => $article['comparison_scope'],
            'content_role' => $article['content_role'],
            'content_role_label' => $article['content_role_label'],
            'primary_query_intent' => $article['primary_query_intent'],
            'intent_group_id' => $article['intent_group_id'],
            'local_slug' => $article['local_slug'],
            'section' => $article['category_label'],
            'slug' => $article['production_slug'],
            'snapshot_id' => $article['snapshot_id'],
            'title' => $article['title'],
        );
    }
    if (count($bindings) !== 10) {
        $bindings = array();
        return $bindings;
    }
    $query_intents_by_group = array();
    foreach ($bindings as $binding) {
        $query_intents_by_group[$binding['intent_group_id']][] = $binding['primary_query_intent'];
    }
    foreach ($query_intents_by_group as $query_intents) {
        if (count($query_intents) !== count(array_unique($query_intents))) {
            $bindings = array();
            return $bindings;
        }
    }
    foreach ($bindings as $article_id => $binding) {
        $broader_id = $binding['broader_article_id'];
        if ($broader_id === null) {
            continue;
        }
        $broader = $bindings[$broader_id] ?? null;
        if (
            $broader_id === $article_id
            || ! is_array($broader)
            || $broader['intent_group_id'] !== $binding['intent_group_id']
            || ! in_array(
                $broader['content_role'],
                array('category_guide', 'constraint_shortlist'),
                true
            )
        ) {
            $bindings = array();
            return $bindings;
        }
    }
    return $bindings;
}

/** Legacy-named fallback now delegates to the single V3 portfolio binding. */
function kurashinoshirube_editorial_v2_publication_bindings(): array
{
    return kurashinoshirube_article_bindings();
}

/** Generate related navigation from the same ten-article portfolio. */
function kurashinoshirube_related_article_map(): array
{
    $navigation = kurashinoshirube_editorial_navigation();
    $bindings = kurashinoshirube_article_bindings();
    if ($navigation === array() || count($bindings) !== 10) {
        return array();
    }
    $clusters = array();
    foreach ($navigation['clusters'] as $cluster) {
        if (
            ! is_array($cluster)
            || ! is_string($cluster['cluster_id'] ?? null)
            || ! is_string($cluster['anchor'] ?? null)
            || ! is_string($cluster['label'] ?? null)
        ) {
            return array();
        }
        $clusters[$cluster['cluster_id']] = $cluster;
    }
    $map = array();
    foreach ($navigation['articles'] as $article) {
        $article_id = $article['article_id'] ?? null;
        $cluster = $clusters[$article['cluster_id'] ?? ''] ?? null;
        $related = $article['related_articles'] ?? null;
        if (
            ! is_string($article_id)
            || ! is_array($cluster)
            || ! is_array($related)
            || count($related) < 1
            || count($related) > 2
        ) {
            return array();
        }
        $targets = array();
        $relationships = array();
        foreach ($related as $relation) {
            $target_id = is_array($relation) ? ($relation['article_id'] ?? null) : null;
            $relationship = is_array($relation) ? ($relation['relationship'] ?? null) : null;
            $target = is_string($target_id) ? ($bindings[$target_id] ?? null) : null;
            $expected_relationship = is_array($target) && $article['broader_article_id'] === $target_id
                ? 'broader_guide'
                : (
                    is_array($target) && $target['broader_article_id'] === $article_id
                        ? (
                            $target['content_role'] === 'lifecycle_status_route'
                                ? 'lifecycle_reference'
                                : 'narrower_comparison'
                        )
                        : 'adjacent_condition'
                );
            if (
                ! is_array($target)
                || $relationship !== $expected_relationship
                || isset($targets[$target_id])
                || $target['intent_group_id'] !== $article['intent_group_id']
            ) {
                return array();
            }
            $targets[$target_id] = $target['title'];
            $relationships[$target_id] = $relationship;
        }
        $map[$article_id] = array(
            'home_anchor' => $cluster['anchor'],
            'home_label' => '暮らしの道具「' . $cluster['label'] . '」の一覧へ',
            'target_relationships' => $relationships,
            'targets' => $targets,
        );
    }
    foreach ($bindings as $article_id => $binding) {
        $broader_id = $binding['broader_article_id'];
        if ($broader_id === null) {
            continue;
        }
        if (
            ! isset($map[$article_id]['targets'][$broader_id])
            || ! isset($map[$broader_id]['targets'][$article_id])
            || ($map[$article_id]['target_relationships'][$broader_id] ?? null)
                !== 'broader_guide'
            || ($map[$broader_id]['target_relationships'][$article_id] ?? null)
                !== (
                    $binding['content_role'] === 'lifecycle_status_route'
                        ? 'lifecycle_reference'
                        : 'narrower_comparison'
                )
        ) {
            return array();
        }
    }
    return count($map) === 10 ? $map : array();
}

/** Generate homepage cluster membership and article order from Editorial V3. */
function kurashinoshirube_homepage_clusters(): array
{
    $navigation = kurashinoshirube_editorial_navigation();
    $bindings = kurashinoshirube_article_bindings();
    if ($navigation === array() || count($bindings) !== 10) {
        return array();
    }
    $configuration = array('clusters' => array(), 'display_order' => array());
    $seen = array();
    foreach ($navigation['clusters'] as $cluster) {
        if (
            ! is_array($cluster)
            || ! is_string($cluster['anchor'] ?? null)
            || ! is_string($cluster['description'] ?? null)
            || ! is_string($cluster['heading'] ?? null)
            || ! is_string($cluster['label'] ?? null)
            || ! is_array($cluster['article_ids'] ?? null)
            || isset($configuration['clusters'][$cluster['anchor']])
        ) {
            return array();
        }
        $posts = array();
        foreach ($cluster['article_ids'] as $article_id) {
            $binding = is_string($article_id) ? ($bindings[$article_id] ?? null) : null;
            if (! is_array($binding) || isset($seen[$article_id])) {
                return array();
            }
            $seen[$article_id] = true;
            $posts[$article_id] = $binding['title'];
        }
        $configuration['clusters'][$cluster['anchor']] = array(
            'description' => $cluster['description'],
            'heading' => $cluster['heading'],
            'label' => $cluster['label'],
            'post_order' => array_values($cluster['article_ids']),
            'posts' => $posts,
        );
        $configuration['display_order'][] = $cluster['anchor'];
    }
    return count($seen) === 10 ? $configuration : array();
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
        || ($payload['author_name'] ?? null) !== '暮らしのしるべ編集者'
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
        KURASHINOSHIRUBE_SOCIAL_IMAGE_SHA256,
        kurashinoshirube_is_local_preview()
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
function kurashinoshirube_verified_asset_uri(
    string $relative,
    string $sha256,
    bool $allow_local_preview = false
): ?string
{
    if (
        preg_match(
            '#\A(?:assets/images/[a-z0-9-]+\.(?:svg|webp)|assets/(?:analytics-consent-gate|measurement|editorial-navigation)\.js)\z#D',
            $relative
        ) !== 1
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
    $local_origin = $allow_local_preview
        ? kurashinoshirube_local_preview_origin()
        : null;
    if (
        is_string($local_origin)
        && $base === $local_origin
            . '/wp-content/themes/kurashinoshirube-child'
    ) {
        return $base . '/' . $relative;
    }
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

/** Resolve one reviewed, article-specific comparison visual. */
function kurashinoshirube_article_visual_asset(int $post_id): ?array
{
    if ($post_id <= 0 || get_post_type($post_id) !== 'post') {
        return null;
    }
    $article_id = null;
    if (is_singular('post') && (int) get_queried_object_id() === $post_id) {
        $snapshot = kurashinoshirube_current_snapshot();
        if (is_array($snapshot) && is_string($snapshot['article_id'] ?? null)) {
            $article_id = $snapshot['article_id'];
        }
    }
    if (! is_string($article_id)) {
        $identity = kurashinoshirube_public_article_identity($post_id);
        $article_id = is_array($identity)
            && is_string($identity['article_id'] ?? null)
            ? $identity['article_id']
            : null;
    }
    $article_visuals = array(
        'st1703-first-suitcase-comparison' => array(
            'asset_key' => 'suitcase',
            'caption' => 'エース3モデルの軽さ・容量・開き方を整理した暮らしのしるべ編集者の比較イメージ（商品写真ではありません）',
            'points' => array('軽さ', '容量', '開き方'),
        ),
        'st1704-portable-power-station-guide' => array(
            'asset_key' => 'power',
            'caption' => '停電時に使う機器から容量・出力・重量を整理した暮らしのしるべ編集者の比較イメージ（商品写真ではありません）',
            'points' => array('容量', '出力', '重量'),
        ),
        'st1704-anker-solix-c300-c800-c1000-differences' => array(
            'asset_key' => 'anker-generations',
            'caption' => 'Anker Solix 4型番の世代・出力・持ち運び条件を整理した暮らしのしるべ編集者の比較イメージ（商品写真ではありません）',
            'points' => array('型番・世代', '出力', '持ち運び'),
        ),
        'st1704-countertop-dishwasher-for-small-households' => array(
            'asset_key' => 'dishwasher',
            'caption' => '少人数向け卓上食洗機の設置・容量・給水方式を整理した暮らしのしるべ編集者の比較イメージ（商品写真ではありません）',
            'points' => array('設置寸法', '食器点数', '給水方式'),
        ),
        'st1704-compact-robot-vacuum-shortlist' => array(
            'asset_key' => 'robot',
            'caption' => 'ロボット掃除機4モデルの本体・ステーション寸法と自動手入れ範囲を整理した暮らしのしるべ編集者の比較イメージ（商品写真ではありません）',
            'points' => array('本体寸法', 'ステーション', '高さ'),
        ),
        'carry-on-suitcase-under-100-seats' => array(
            'asset_key' => 'suitcase-under-100',
            'caption' => '100席未満便の機内持ち込み条件を各辺と3辺合計で整理した暮らしのしるべ編集者の比較イメージ（商品写真ではありません）',
            'points' => array('45×35×20cm', '3辺合計100cm', '便・機材'),
        ),
        'lightweight-carry-on-suitcase-under-3kg' => array(
            'asset_key' => 'suitcase-under-3kg',
            'caption' => '軽量スーツケースの容量・重量・外寸を整理した暮らしのしるべ編集者の比較イメージ（商品写真ではありません）',
            'points' => array('30L以上', '3kg以下', '外寸'),
        ),
        'front-open-carry-on-suitcase-with-stopper' => array(
            'asset_key' => 'suitcase-front-open',
            'caption' => '機内持ち込みスーツケースの前開き・ストッパー・拡張時寸法を整理した暮らしのしるべ編集者の比較イメージ（商品写真ではありません）',
            'points' => array('前開き', 'ストッパー', '拡張時寸法'),
        ),
        'roomba-mini-vs-switchbot-k11-pro' => array(
            'asset_key' => 'roomba-k11',
            'caption' => '小型ロボット掃除機の本体幅・ステーション・販売状態を整理した暮らしのしるべ編集者の比較イメージ（商品写真ではありません）',
            'points' => array('本体幅', 'ステーション', '販売状態'),
        ),
        'solota-vs-rakua-mini-plus' => array(
            'asset_key' => 'solota-rakua',
            'caption' => '食洗機の型番・販売元・在庫と納期を順に確認する暮らしのしるべ編集者の比較イメージ（商品写真ではありません）',
            'points' => array('対象の型番', '公式の販売表示', '在庫・納期'),
        ),
    );
    $assets = array(
        'anker-generations' => array(
            'height' => 1024,
            'path' => KURASHINOSHIRUBE_ANKER_GENERATIONS_IMAGE_PATH,
            'sha256' => KURASHINOSHIRUBE_ANKER_GENERATIONS_IMAGE_SHA256,
            'width' => 1536,
        ),
        'dishwasher' => array(
            'height' => 1024,
            'path' => KURASHINOSHIRUBE_DISHWASHER_ARTICLE_IMAGE_PATH,
            'sha256' => KURASHINOSHIRUBE_DISHWASHER_ARTICLE_IMAGE_SHA256,
            'width' => 1536,
        ),
        'power' => array(
            'height' => 1024,
            'path' => KURASHINOSHIRUBE_POWER_ARTICLE_IMAGE_PATH,
            'sha256' => KURASHINOSHIRUBE_POWER_ARTICLE_IMAGE_SHA256,
            'width' => 1536,
        ),
        'robot' => array(
            'height' => 1024,
            'path' => KURASHINOSHIRUBE_ROBOT_ARTICLE_IMAGE_PATH,
            'sha256' => KURASHINOSHIRUBE_ROBOT_ARTICLE_IMAGE_SHA256,
            'width' => 1536,
        ),
        'roomba-k11' => array(
            'height' => 1024,
            'path' => KURASHINOSHIRUBE_ROOMBA_K11_IMAGE_PATH,
            'sha256' => KURASHINOSHIRUBE_ROOMBA_K11_IMAGE_SHA256,
            'width' => 1536,
        ),
        'solota-rakua' => array(
            'height' => 1024,
            'path' => KURASHINOSHIRUBE_SOLOTA_RAKUA_IMAGE_PATH,
            'sha256' => KURASHINOSHIRUBE_SOLOTA_RAKUA_IMAGE_SHA256,
            'width' => 1536,
        ),
        'suitcase' => array(
            'height' => 900,
            'path' => KURASHINOSHIRUBE_ARTICLE_IMAGE_PATH,
            'sha256' => KURASHINOSHIRUBE_ARTICLE_IMAGE_SHA256,
            'width' => 1600,
        ),
        'suitcase-front-open' => array(
            'height' => 1024,
            'path' => KURASHINOSHIRUBE_SUITCASE_FRONT_OPEN_IMAGE_PATH,
            'sha256' => KURASHINOSHIRUBE_SUITCASE_FRONT_OPEN_IMAGE_SHA256,
            'width' => 1536,
        ),
        'suitcase-under-100' => array(
            'height' => 1024,
            'path' => KURASHINOSHIRUBE_SUITCASE_UNDER_100_IMAGE_PATH,
            'sha256' => KURASHINOSHIRUBE_SUITCASE_UNDER_100_IMAGE_SHA256,
            'width' => 1536,
        ),
        'suitcase-under-3kg' => array(
            'height' => 1024,
            'path' => KURASHINOSHIRUBE_SUITCASE_UNDER_3KG_IMAGE_PATH,
            'sha256' => KURASHINOSHIRUBE_SUITCASE_UNDER_3KG_IMAGE_SHA256,
            'width' => 1536,
        ),
    );
    $definition = is_string($article_id)
        ? ($article_visuals[$article_id] ?? null)
        : null;
    if (
        ! is_array($definition)
        || ! is_string($definition['asset_key'] ?? null)
        || ! is_string($definition['caption'] ?? null)
        || ! is_array($definition['points'] ?? null)
        || count($definition['points']) !== 3
        || ! is_array($assets[$definition['asset_key']] ?? null)
    ) {
        return null;
    }
    foreach ($definition['points'] as $point) {
        if (! is_string($point) || $point === '') {
            return null;
        }
    }
    return array_merge(
        array(
            'height' => 900,
            'path' => KURASHINOSHIRUBE_SOCIAL_IMAGE_PATH,
            'sha256' => KURASHINOSHIRUBE_SOCIAL_IMAGE_SHA256,
            'width' => 1600,
        ),
        array(
            'caption' => '鍋、マグカップ、照明とチェックリストを描いた暮らしの道具のイラスト',
            'diagram_caption' => $definition['caption'],
            'points' => $definition['points'],
        )
    );
}

/** Resolve the current head image without widening any article identity. */
function kurashinoshirube_current_social_visual_asset(): ?array
{
    $context = kurashinoshirube_public_head_context();
    if ($context === null) {
        return null;
    }
    $visual = null;
    if ($context['kind'] === 'article') {
        $visual = kurashinoshirube_article_visual_asset(
            (int) get_queried_object_id()
        );
    }
    if ($visual === null) {
        $visual = array(
            'caption' => '',
            'height' => 900,
            'path' => KURASHINOSHIRUBE_SOCIAL_IMAGE_PATH,
            'sha256' => KURASHINOSHIRUBE_SOCIAL_IMAGE_SHA256,
            'width' => 1600,
        );
    }
    $uri = kurashinoshirube_verified_asset_uri(
        $visual['path'],
        $visual['sha256'],
        true
    );
    if ($uri === null) {
        return null;
    }
    $visual['uri'] = $uri;
    return $visual;
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

/** Resolve one synthetic local route back to its generated production identity. */
function kurashinoshirube_local_preview_article_identity(
    int $post_id
): ?array {
    if (
        ! kurashinoshirube_is_local_preview()
        || $post_id <= 0
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
    foreach (kurashinoshirube_article_bindings() as $article_id => $binding) {
        if (($binding['local_slug'] ?? null) !== $slug) {
            continue;
        }
        $matched = preg_match_all(
            '/\bdata-raos-article-id="([a-z0-9]+(?:-[a-z0-9]+)*)"/',
            $content,
            $matches
        );
        if (
            ! kurashinoshirube_post_has_editorial_v2_root($post_id)
            || substr_count($content, KURASHINOSHIRUBE_EDITORIAL_V2_ROOT) !== 1
            || ! is_int($matched)
            || $matched < 1
            || ! isset($matches[1])
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
    return null;
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
    $published = kurashinoshirube_published_editorial_v2_identity($post_id);
    return $published === null
        ? kurashinoshirube_local_preview_article_identity($post_id)
        : $published;
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

/**
 * Keep the public site free of WordPress's browser-storage emoji probe.
 *
 * Modern system fonts cover the editorial UI. The core compatibility probe
 * writes wpEmojiSettingsSupports to sessionStorage even when analytics and
 * consent storage are disabled, which would make the published privacy state
 * disagree with the actual browser state.
 */
function kurashinoshirube_disable_core_emoji_assets(): void
{
    remove_action('wp_head', 'print_emoji_detection_script', 7);
    remove_action('wp_enqueue_scripts', 'wp_enqueue_emoji_styles');
    remove_action('wp_print_styles', 'print_emoji_styles');
    remove_action('embed_head', 'print_emoji_detection_script');
    remove_action('enqueue_embed_scripts', 'wp_enqueue_emoji_styles');
    remove_filter('the_content_feed', 'wp_staticize_emoji');
    remove_filter('comment_text_rss', 'wp_staticize_emoji');
    remove_filter('wp_mail', 'wp_staticize_emoji_for_email');
}
add_action(
    'after_setup_theme',
    'kurashinoshirube_disable_core_emoji_assets',
    0
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
    wp_enqueue_style(
        'kurashinoshirube-editorial',
        get_stylesheet_directory_uri() . '/assets/theme.css',
        array(),
        KURASHINOSHIRUBE_THEME_RUNTIME_REVISION
    );
});

/** Load the closed consent state machine before any eligible Google tag. */
function kurashinoshirube_enqueue_analytics_consent_gate(): void
{
    if (is_admin()) {
        return;
    }
    $asset_uri = kurashinoshirube_verified_asset_uri(
        KURASHINOSHIRUBE_ANALYTICS_CONSENT_GATE_ASSET_PATH,
        KURASHINOSHIRUBE_ANALYTICS_CONSENT_GATE_ASSET_SHA256,
        true
    );
    if ($asset_uri === null) {
        return;
    }
    wp_enqueue_script(
        'kurashinoshirube-analytics-consent-gate',
        $asset_uri,
        array(),
        KURASHINOSHIRUBE_THEME_RUNTIME_REVISION,
        array('in_footer' => false, 'strategy' => 'defer')
    );
}
add_action(
    'wp_enqueue_scripts',
    'kurashinoshirube_enqueue_analytics_consent_gate',
    1
);

/** Discover the always-required base stylesheet before later inline block CSS. */
function kurashinoshirube_preload_base_stylesheet(array $preloads): array
{
    if (is_admin()) {
        return $preloads;
    }
    $preloads[] = array(
        'href' => add_query_arg(
            'ver',
            rawurlencode(KURASHINOSHIRUBE_THEME_RUNTIME_REVISION),
            get_stylesheet_directory_uri() . '/assets/theme.css'
        ),
        'as' => 'style',
    );
    return $preloads;
}
add_filter(
    'wp_preload_resources',
    'kurashinoshirube_preload_base_stylesheet'
);

/**
 * Let WordPress inline its small, version-matched navigation block stylesheet.
 *
 * The core stylesheet is already required by the header and footer navigation
 * blocks. Supplying its local path opts it into WordPress's bounded
 * wp_maybe_inline_styles() pass, removing one render-blocking request without
 * copying or replacing core CSS.
 */
function kurashinoshirube_inline_core_navigation_style(): void
{
    if (is_admin()) {
        return;
    }
    $navigation_style_path = ABSPATH . WPINC . '/blocks/navigation/style.css';
    if (
        ! is_readable($navigation_style_path)
        || is_link($navigation_style_path)
        || ! wp_style_is('wp-block-navigation', 'registered')
    ) {
        return;
    }
    wp_style_add_data(
        'wp-block-navigation',
        'path',
        $navigation_style_path
    );
}
add_action(
    'wp_head',
    'kurashinoshirube_inline_core_navigation_style',
    0
);

/** Reserve only the verified core navigation bytes in the inline-style budget. */
function kurashinoshirube_navigation_inline_style_limit(int $limit): int
{
    $navigation_style_path = ABSPATH . WPINC . '/blocks/navigation/style.css';
    if (
        $limit < 0
        || ! is_readable($navigation_style_path)
        || is_link($navigation_style_path)
    ) {
        return $limit;
    }
    $navigation_style_bytes = wp_filesize($navigation_style_path);
    if (
        ! is_int($navigation_style_bytes)
        || $navigation_style_bytes <= 0
        || $navigation_style_bytes > 32768
        || $limit > PHP_INT_MAX - $navigation_style_bytes
    ) {
        return $limit;
    }
    return $limit + $navigation_style_bytes;
}
add_filter(
    'styles_inline_size_limit',
    'kurashinoshirube_navigation_inline_style_limit'
);

/** Make the core skip-link target programmatically focusable on every template. */
function kurashinoshirube_make_main_focusable(
    string $block_content,
    array $block
): string {
    if (
        ($block['attrs']['tagName'] ?? null) !== 'main'
        || ! class_exists('WP_HTML_Tag_Processor')
    ) {
        return $block_content;
    }
    $processor = new WP_HTML_Tag_Processor($block_content);
    if (! $processor->next_tag(array('tag_name' => 'MAIN'))) {
        return $block_content;
    }
    $processor->set_attribute('tabindex', '-1');
    return $processor->get_updated_html();
}
add_filter(
    'render_block_core/group',
    'kurashinoshirube_make_main_focusable',
    10,
    2
);

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

/** Identify only a reviewed, published policy page from the closed fixture set. */
function kurashinoshirube_is_policy_v3_page(): bool
{
    if (! is_singular('page')) {
        return false;
    }
    $post_id = (int) get_queried_object_id();
    if (
        $post_id <= 0
        || get_post_type($post_id) !== 'page'
        || get_post_status($post_id) !== 'publish'
    ) {
        return false;
    }
    $slug = get_post_field('post_name', $post_id, 'raw');
    $head = is_string($slug)
        ? (kurashinoshirube_policy_page_head_map()[$slug] ?? null)
        : null;
    return is_array($head)
        && get_post_field('post_title', $post_id, 'raw') === $head['title']
        && get_post_field('post_excerpt', $post_id, 'raw') === $head['description'];
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
            $sections[$binding['local_slug']] = $binding['section'];
        }
    }
    return count($sections) === 20 ? $sections : array();
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
    if (kurashinoshirube_is_policy_v3_page()) {
        $classes[] = 'raos-policy-v3-page';
    }
    if (is_search() || is_archive()) {
        $classes[] = 'raos-listing-page';
    }
    if (is_404()) {
        $classes[] = 'raos-not-found-page';
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
    wp_enqueue_style(
        'kurashinoshirube-editorial-v2',
        get_stylesheet_directory_uri() . '/assets/editorial-v2.css',
        array('kurashinoshirube-editorial'),
        KURASHINOSHIRUBE_THEME_RUNTIME_REVISION
    );
}
add_action(
    'wp_enqueue_scripts',
    'kurashinoshirube_enqueue_editorial_v2_stylesheet',
    20
);

/** Add focus handoff only on article routes that render the generated TOC. */
function kurashinoshirube_enqueue_editorial_navigation(): void
{
    if (! kurashinoshirube_is_editorial_v2_post()) {
        return;
    }
    $asset_uri = kurashinoshirube_verified_asset_uri(
        KURASHINOSHIRUBE_NAVIGATION_ASSET_PATH,
        KURASHINOSHIRUBE_NAVIGATION_ASSET_SHA256,
        true
    );
    if ($asset_uri === null) {
        return;
    }
    wp_enqueue_script(
        'kurashinoshirube-editorial-navigation',
        $asset_uri,
        array(),
        KURASHINOSHIRUBE_THEME_RUNTIME_REVISION,
        array('in_footer' => true, 'strategy' => 'defer')
    );
}
add_action(
    'wp_enqueue_scripts',
    'kurashinoshirube_enqueue_editorial_navigation',
    25
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
    $alt = '機内持ち込みスーツケースの比較軸を整理した編集部のイメージ（商品写真ではありません）';
    return '<figure class="wp-block-image size-full raos-first-article-lead-image">'
        . '<img src="' . esc_url($image_uri) . '" alt="' . esc_attr($alt)
        . '" width="1600" height="900">'
        . '</figure>';
}
add_shortcode(
    'kurashinoshirube_first_article_lead_image',
    'kurashinoshirube_render_first_article_lead_image'
);

/** Render a theme-owned, non-product comparison hero for all ten guides. */
function kurashinoshirube_render_article_hero($attributes, $content, $tag): string
{
    $post_id = (int) get_the_ID();
    $identity = kurashinoshirube_public_article_identity($post_id);
    $article_id = is_array($identity)
        ? ($identity['article_id'] ?? null)
        : null;
    $generated_article_ids = array(
        'st1703-first-suitcase-comparison',
        'st1704-portable-power-station-guide',
        'st1704-anker-solix-c300-c800-c1000-differences',
        'st1704-countertop-dishwasher-for-small-households',
        'st1704-compact-robot-vacuum-shortlist',
        'carry-on-suitcase-under-100-seats',
        'lightweight-carry-on-suitcase-under-3kg',
        'front-open-carry-on-suitcase-with-stopper',
        'roomba-mini-vs-switchbot-k11-pro',
        'solota-vs-rakua-mini-plus',
    );
    if (
        $attributes !== array()
        || ! in_array($content, array(null, ''), true)
        || $tag !== 'kurashinoshirube_article_hero'
        || ! is_singular('post')
        || ! is_string($article_id)
        || ! in_array($article_id, $generated_article_ids, true)
        || get_stylesheet() !== 'kurashinoshirube-child'
    ) {
        return '';
    }
    $visual = kurashinoshirube_article_visual_asset($post_id);
    if ($visual === null) {
        return '';
    }
    $point_items = '';
    foreach ($visual['points'] as $index => $point) {
        $point_items .= '<li><span aria-hidden="true">0'
            . (string) ($index + 1) . '</span>' . esc_html($point) . '</li>';
    }
    return '<figure class="raos-article-hero-image raos-article-hero-image--criteria">'
        . '<div class="raos-article-hero-image__canvas">'
        . '<p class="raos-article-hero-image__notice">'
        . '比較イメージ／商品写真ではありません</p>'
        . '<div class="raos-article-hero-image__overlay">'
        . '<p>この記事で確認すること</p>'
        . '<ol aria-label="この記事で確認する3つの項目">' . $point_items . '</ol></div></div>'
        . '<figcaption>' . esc_html($visual['diagram_caption']) . '</figcaption>'
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
                foreach (array('移動', '家事', '備え') as $allowed_section) {
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
    $role_label = null;
    $identity = kurashinoshirube_public_article_identity(
        (int) get_queried_object_id()
    );
    if (is_array($identity)) {
        $binding = kurashinoshirube_article_bindings()[$identity['article_id']] ?? null;
        if (is_array($binding) && is_string($binding['content_role_label'] ?? null)) {
            $role_label = $binding['content_role_label'];
        }
    }
    return '<p class="raos-article-category">' . esc_html($section)
        . '／' . esc_html($role_label ?? '比較ガイド') . '</p>';
}
add_shortcode(
    'kurashinoshirube_article_category',
    'kurashinoshirube_render_article_category'
);

/** Resolve one generated related target on production or the isolated preview. */
function kurashinoshirube_resolve_related_target(string $target_id): ?array
{
    $binding = kurashinoshirube_article_bindings()[$target_id] ?? null;
    if (! is_array($binding)) {
        return null;
    }
    $local_origin = kurashinoshirube_local_preview_origin();
    $local = is_string($local_origin);
    $target_slug = $local ? $binding['local_slug'] : $binding['slug'];
    $target = get_page_by_path($target_slug, OBJECT, 'post');
    $expected_url = $local
        ? $local_origin . '/' . $target_slug . '/'
        : KURASHINOSHIRUBE_SITE_ORIGIN . '/' . $target_slug . '/';
    if (
        ! ($target instanceof WP_Post)
        || get_post_status($target) !== 'publish'
        || get_post_field('post_name', $target->ID, 'raw') !== $target_slug
        || get_permalink($target) !== $expected_url
    ) {
        return null;
    }
    $target_identity = kurashinoshirube_public_article_identity((int) $target->ID);
    if (
        $target_identity === null
        || $target_identity['article_id'] !== $target_id
    ) {
        return null;
    }
    return array('title' => $binding['title'], 'url' => $expected_url);
}

/** Pick the most useful same-intent guide for the in-article decision handoff. */
function kurashinoshirube_contextual_target_id(array $relation): ?string
{
    $relationships = $relation['target_relationships'] ?? array();
    foreach (
        array(
            'broader_guide',
            'narrower_comparison',
            'lifecycle_reference',
            'adjacent_condition',
        ) as $priority
    ) {
        foreach ($relationships as $candidate => $relationship) {
            if (is_string($candidate) && $relationship === $priority) {
                return $candidate;
            }
        }
    }
    return null;
}

/** Add a compact table of contents without changing the authored evidence copy. */
function kurashinoshirube_inject_article_toc($content)
{
    if (
        ! is_string($content)
        || $content === ''
        || ! is_singular('post')
        || ! in_the_loop()
        || ! is_main_query()
        || str_contains($content, 'class="raos-article-toc"')
        || kurashinoshirube_public_article_identity((int) get_the_ID()) === null
    ) {
        return $content;
    }
    $items = array();
    $seen = array();
    $generated_index = 0;
    $transformed = preg_replace_callback(
        '#<h2(?P<attributes>[^>]*)>(?P<label>.*?)</h2>#isu',
        static function (array $matches) use (&$items, &$seen, &$generated_index): string {
            $attributes = $matches['attributes'];
            $focus_attribute = preg_match('/\btabindex\s*=/iu', $attributes) === 1
                ? ''
                : ' tabindex="-1"';
            $opening = '<h2' . $attributes . $focus_attribute . '>';
            $label = html_entity_decode(
                wp_strip_all_tags($matches['label']),
                ENT_QUOTES | ENT_HTML5,
                'UTF-8'
            );
            $label = trim((string) preg_replace('/\s+/u', ' ', $label));
            if (! kurashinoshirube_is_clean_text($label, 2, 120)) {
                return $matches[0];
            }
            $matched_id = preg_match(
                '/\bid="([a-z][a-z0-9-]{1,80})"/D',
                $matches['attributes'],
                $id_match
            );
            if ($matched_id === 1) {
                $section_id = $id_match[1];
            } else {
                do {
                    ++$generated_index;
                    $section_id = 'raos-section-' . $generated_index;
                } while (isset($seen[$section_id]));
                $opening = '<h2 id="' . esc_attr($section_id) . '"'
                    . $attributes . $focus_attribute . '>';
            }
            if (isset($seen[$section_id])) {
                return $matches[0];
            }
            $seen[$section_id] = true;
            $items[] = array('id' => $section_id, 'label' => $label);
            return $opening . $matches['label'] . '</h2>';
        },
        $content
    );
    if (! is_string($transformed) || count($items) < 3 || count($items) > 24) {
        return $content;
    }
    $links = '';
    foreach ($items as $item) {
        $links .= '<li><a href="#' . esc_attr($item['id']) . '">'
            . esc_html($item['label']) . '</a></li>';
    }
    $back_link = '<p class="raos-back-to-toc-wrap"><a class="raos-back-to-toc" '
        . 'href="#raos-article-toc">記事内の目次へ戻る <span aria-hidden="true">↑</span></a></p>';
    $with_back_links = preg_replace_callback(
        '#<section(?P<attributes>[^>]*)>(?P<body>.*?)</section>#isu',
        static function (array $matches) use ($back_link): string {
            if (
                stripos($matches['body'], '<h2') === false
                || strpos($matches['body'], 'class="raos-back-to-toc"') !== false
            ) {
                return $matches[0];
            }
            return '<section' . $matches['attributes'] . '>'
                . $matches['body'] . $back_link . '</section>';
        },
        $transformed
    );
    if (! is_string($with_back_links)) {
        return $content;
    }
    $transformed = $with_back_links;
    $toc = '<nav id="raos-article-toc" class="raos-article-toc" '
        . 'aria-label="記事内の目次" tabindex="-1">'
        . '<p class="raos-article-toc__title">この記事の目次</p>'
        . '<details open><summary>この記事の目次</summary><ol>' . $links
        . '</ol></details></nav>';
    $root_end = strpos($transformed, '>');
    $root_close = strrpos($transformed, '</div>');
    if ($root_end === false || $root_close === false || $root_close <= $root_end) {
        return $content;
    }
    $position = $root_end + 1;
    return substr($transformed, 0, $position) . $toc
        . '<div class="raos-editorial-v2__main">'
        . substr($transformed, $position, $root_close - $position)
        . '</div>' . substr($transformed, $root_close);
}
add_filter('the_content', 'kurashinoshirube_inject_article_toc', 12);

/** Insert one decision-context link inside the authored article flow. */
function kurashinoshirube_inject_contextual_guide($content)
{
    if (
        ! is_string($content)
        || $content === ''
        || ! is_singular('post')
        || ! in_the_loop()
        || ! is_main_query()
        || str_contains($content, 'class="raos-contextual-guide"')
    ) {
        return $content;
    }
    $identity = kurashinoshirube_public_article_identity((int) get_the_ID());
    $relation = is_array($identity)
        ? (kurashinoshirube_related_article_map()[$identity['article_id']] ?? null)
        : null;
    if (! is_array($relation)) {
        return $content;
    }
    $target_id = kurashinoshirube_contextual_target_id($relation);
    $target = is_string($target_id)
        ? kurashinoshirube_resolve_related_target($target_id)
        : null;
    if (! is_array($target)) {
        return $content;
    }
    $relationship = $relation['target_relationships'][$target_id] ?? null;
    $handoff_label = array(
        'broader_guide' => '候補を広げて選び直す：',
        'narrower_comparison' => '条件を絞って比較する：',
        'lifecycle_reference' => '以前の比較対象の販売状況を確認する：',
        'adjacent_condition' => '別の条件も確認する：',
    )[$relationship] ?? null;
    if (! is_string($handoff_label)) {
        return $content;
    }
    $markup = '<p class="raos-contextual-guide"><strong>'
        . esc_html($handoff_label) . '</strong>'
        . '<a href="' . esc_url($target['url']) . '" data-raos-internal-link="contextual"'
        . ' data-raos-to-article-id="' . esc_attr($target_id) . '"'
        . ' data-raos-link-placement="article_body">'
        . esc_html($target['title']) . '</a></p>';
    $markers = array(
        '<section class="comparison-section"',
        '<section class="products-section"',
        '<aside class="raos-caution purchase-caution"',
        '<aside id="purchase-notes" class="purchase-caution"',
    );
    foreach ($markers as $marker) {
        $position = strpos($content, $marker);
        if ($position !== false) {
            return substr($content, 0, $position) . $markup
                . substr($content, $position);
        }
    }
    $position = strrpos($content, '</div>');
    return $position === false
        ? $content
        : substr($content, 0, $position) . $markup . substr($content, $position);
}
add_filter('the_content', 'kurashinoshirube_inject_contextual_guide', 15);

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
    $contextual_target_id = kurashinoshirube_contextual_target_id($relation);
    if ($contextual_target_id === null) {
        return '';
    }
    $items = array();
    foreach ($relation['targets'] as $target_id => $label) {
        if ($target_id === $contextual_target_id) {
            continue;
        }
        $target = kurashinoshirube_resolve_related_target($target_id);
        if (! is_array($target)) {
            continue;
        }
        $items[] = '<li><a href="' . esc_url($target['url'])
            . '" data-raos-internal-link="related"'
            . ' data-raos-to-article-id="' . esc_attr($target_id) . '"'
            . ' data-raos-link-placement="related_navigation">'
            . esc_html($label) . '</a></li>';
    }
    if (count($items) > 1) {
        return '';
    }
    $local_origin = kurashinoshirube_local_preview_origin();
    $home_url = (is_string($local_origin)
        ? $local_origin
        : KURASHINOSHIRUBE_SITE_ORIGIN) . '/#' . $relation['home_anchor'];
    $items[] = '<li><a href="' . esc_url($home_url) . '"'
        . ' data-raos-internal-link="cluster-home"'
        . ' data-raos-cluster-anchor="' . esc_attr($relation['home_anchor']) . '"'
        . ' data-raos-link-placement="cluster_home">'
        . esc_html($relation['home_label']) . '</a></li>';
    return '<aside class="raos-related-guides" aria-labelledby="raos-related-title">'
        . '<h2 id="raos-related-title">次に確認したいガイド</h2><ul>'
        . implode('', $items) . '</ul></aside>';
}
add_shortcode(
    'kurashinoshirube_related_guides',
    'kurashinoshirube_render_related_guides'
);

/** Return the validated loopback origin only in the isolated preview. */
function kurashinoshirube_local_preview_origin(): ?string
{
    if (
        ! defined('RAOS_LOCAL_PREVIEW')
        || RAOS_LOCAL_PREVIEW !== true
        || ! defined('RAOS_WORDPRESS_PREVIEW_ORIGIN')
        || ! is_string(RAOS_WORDPRESS_PREVIEW_ORIGIN)
        || preg_match(
            '#\Ahttp://127\.0\.0\.1:([0-9]{4,5})\z#D',
            RAOS_WORDPRESS_PREVIEW_ORIGIN,
            $matches
        ) !== 1
        || (int) $matches[1] < 1024
        || (int) $matches[1] > 65535
        || ! function_exists('wp_get_environment_type')
        || wp_get_environment_type() !== 'local'
        || home_url('/') !== RAOS_WORDPRESS_PREVIEW_ORIGIN . '/'
        || site_url('/') !== RAOS_WORDPRESS_PREVIEW_ORIGIN . '/'
    ) {
        return null;
    }
    return RAOS_WORDPRESS_PREVIEW_ORIGIN;
}

/** Return true only inside the repository-owned, network-isolated preview. */
function kurashinoshirube_is_local_preview(): bool
{
    return kurashinoshirube_local_preview_origin() !== null;
}

/**
 * Resolve the fixed featured article without widening production eligibility.
 * The isolated local preview uses the same article through its exact local slug.
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
        $local_origin = kurashinoshirube_local_preview_origin();
        $slug = is_string($local_origin)
            ? ($binding['local_slug'] ?? null)
            : ($binding['slug'] ?? null);
        if (! is_string($slug)) {
            return null;
        }
        $post = get_page_by_path($slug, OBJECT, 'post');
        $identity = $post instanceof WP_Post
            ? kurashinoshirube_public_article_identity((int) $post->ID)
            : null;
        $expected_permalink = (is_string($local_origin)
            ? $local_origin
            : KURASHINOSHIRUBE_SITE_ORIGIN) . '/' . $slug . '/';
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
    return null;
}

/** Resolve a bounded reader-facing section label for a homepage post. */
function kurashinoshirube_homepage_post_section(WP_Post $post): ?string
{
    foreach (kurashinoshirube_article_bindings() as $binding) {
        if (
            ($binding['slug'] ?? null) === $post->post_name
            || (
                kurashinoshirube_is_local_preview()
                && ($binding['local_slug'] ?? null) === $post->post_name
            )
        ) {
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
    foreach (array('移動', '家事', '備え') as $allowed) {
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
    $criteria = '容量・定格出力・重量・持ち運び';
    $read_label = $title . 'を読む';
    return '<section id="featured" class="raos-featured raos-home-section alignwide" '
        . 'aria-labelledby="raos-featured-title"><div class="raos-home-heading '
        . 'raos-home-heading--split"><div><p class="raos-home-eyebrow">注目ガイド</p>'
        . '<h2 id="raos-featured-title">条件を整理する比較ガイド</h2></div>'
        . '<p>停電時に使う機器と持ち運び方から、必要な容量と出力を整理します。</p></div>'
        . '<article class="raos-featured-guide"><figure class="raos-featured-guide__visual '
        . 'raos-featured-guide__visual--power"><a href="' . esc_url($permalink)
        . '"><span class="raos-featured-guide__diagram" aria-hidden="true">'
        . '<span>01　使いたい機器を決める</span><span>02　必要な出力を確かめる</span>'
        . '<span>03　使う時間から容量を考える</span></span>'
        . '<span class="screen-reader-text">' . esc_html($read_label)
        . '</span></a><figcaption>選ぶ順番を示す比較図。商品写真ではありません。</figcaption></figure>'
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

/** Label the content actually stored, including a mixed old/new publication. */
function kurashinoshirube_stored_guide_role(int $post_id): string
{
    $identity = kurashinoshirube_public_article_identity($post_id);
    $body = get_post_field('post_content', $post_id, 'raw');
    if (
        is_array($identity)
        && $identity['article_id'] === 'solota-vs-rakua-mini-plus'
        && is_string($body)
        && substr_count(
            $body,
            '<dt>記事分類</dt><dd>型番・販売表示の確認案内</dd>'
        ) === 1
    ) {
        return '型番・販売表示の確認案内';
    }
    return '比較・選び方ガイド';
}

/** Render synthetic local posts in the exact generated cluster order. */
function kurashinoshirube_local_preview_cluster_items(
    string $label,
    array $article_ids
): string
{
    if (
        ! kurashinoshirube_is_local_preview()
        || ! in_array($label, array('移動', '家事', '備え'), true)
        || $article_ids === array()
        || count(array_unique($article_ids)) !== count($article_ids)
    ) {
        return '';
    }
    $items = '';
    foreach ($article_ids as $article_id) {
        $binding = is_string($article_id)
            ? (kurashinoshirube_article_bindings()[$article_id] ?? null)
            : null;
        $post = is_array($binding)
            ? get_page_by_path($binding['local_slug'], OBJECT, 'post')
            : null;
        $identity = $post instanceof WP_Post
            ? kurashinoshirube_public_article_identity((int) $post->ID)
            : null;
        $permalink = $post instanceof WP_Post ? get_permalink($post) : null;
        if (
            ! ($post instanceof WP_Post)
            || ! is_array($binding)
            || $identity === null
            || $identity['article_id'] !== $article_id
            || ! is_string($permalink)
            || $permalink !== kurashinoshirube_local_preview_origin() . '/'
                . $binding['local_slug'] . '/'
        ) {
            return '';
        }
        $items .= '<li><a href="' . esc_url($permalink) . '">'
            . esc_html(get_post_field('post_title', (int) $post->ID, 'raw'))
            . '<small class="raos-guide-role">'
            . esc_html(kurashinoshirube_stored_guide_role((int) $post->ID)) . '</small>'
            . '<span aria-hidden="true">→</span></a></li>';
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
                . esc_html(get_post_field('post_title', (int) $post->ID, 'raw'))
                . '<small class="raos-guide-role">'
                . esc_html(kurashinoshirube_stored_guide_role((int) $post->ID))
                . '</small><span aria-hidden="true">→</span></a></li>';
        }
        if ($items === '') {
            $items = kurashinoshirube_local_preview_cluster_items(
                $cluster['label'],
                $cluster['post_order']
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

    return '<section id="all-guides" class="raos-cluster-nav raos-home-section alignwide" '
        . 'aria-labelledby="raos-cluster-nav-title"><div class="raos-home-heading '
        . 'raos-home-heading--split"><div><p class="raos-home-eyebrow">目的別ガイド</p>'
        . '<h2 id="raos-cluster-nav-title">目的別の記事</h2></div>'
        . '<p>総合1位ではなく、暮らしの条件に近いテーマから記事を選べます。</p>'
        . '</div><div class="raos-clusters">' . $sections . '</div></section>';
}
add_shortcode(
    'kurashinoshirube_published_clusters',
    'kurashinoshirube_render_published_clusters'
);

/** Search public guides only; an empty query never means "show all". */
function kurashinoshirube_constrain_public_search($query): void
{
    if (
        is_admin()
        || ! ($query instanceof WP_Query)
        || ! $query->is_main_query()
        || ! $query->is_search()
    ) {
        return;
    }
    $query->set('post_type', 'post');
    $excluded = kurashinoshirube_merge_public_listing_exclusions(
        $query->get('post__not_in')
    );
    if ($excluded === null) {
        $query->set('post__in', array(0));
        return;
    }
    $query->set('post__not_in', $excluded);
    $search = $query->get('s');
    if (is_string($search) && trim($search) === '') {
        $query->set('post__in', array(0));
    }
}
add_action(
    'pre_get_posts',
    'kurashinoshirube_constrain_public_search',
    20
);

/** Render one bounded Japanese summary for the native search result route. */
function kurashinoshirube_render_search_summary($attributes, $content, $tag): string
{
    if (
        $attributes !== array()
        || ! in_array($content, array(null, ''), true)
        || $tag !== 'kurashinoshirube_search_summary'
        || ! is_search()
    ) {
        return '';
    }
    $query = trim((string) get_search_query(false));
    if ($query === '') {
        return '<p class="raos-listing-summary">商品名や条件を入力して、比較ガイドを検索できます。</p>';
    }
    $count = isset($GLOBALS['wp_query']) && $GLOBALS['wp_query'] instanceof WP_Query
        ? (int) $GLOBALS['wp_query']->found_posts
        : 0;
    return '<p class="raos-listing-summary">「' . esc_html($query)
        . '」に一致する記事：' . esc_html((string) $count) . '件</p>';
}
add_shortcode(
    'kurashinoshirube_search_summary',
    'kurashinoshirube_render_search_summary'
);

/** Render wording that distinguishes an empty query from a zero-result query. */
function kurashinoshirube_render_search_empty_state($attributes, $content, $tag): string
{
    if (
        $attributes !== array()
        || ! in_array($content, array(null, ''), true)
        || $tag !== 'kurashinoshirube_search_empty_state'
        || ! is_search()
    ) {
        return '';
    }
    $query = trim((string) get_search_query(false));
    if ($query === '') {
        return '<h2>検索語を入力してください</h2>'
            . '<p>商品名や選びたい条件を、検索欄へ入力してください。</p>';
    }
    return '<h2>一致する記事はありません</h2>'
        . '<p>検索語を短くするか、別の言葉でお試しください。</p>';
}
add_shortcode(
    'kurashinoshirube_search_empty_state',
    'kurashinoshirube_render_search_empty_state'
);

/** Render one Japanese H1 for supported archive contexts. */
function kurashinoshirube_render_archive_heading($attributes, $content, $tag): string
{
    if (
        $attributes !== array()
        || ! in_array($content, array(null, ''), true)
        || $tag !== 'kurashinoshirube_archive_heading'
        || ! is_archive()
    ) {
        return '';
    }
    if (is_category()) {
        $label = single_cat_title('', false) . 'の記事';
    } elseif (is_tag()) {
        $label = single_tag_title('', false) . 'の記事';
    } elseif (is_author()) {
        $label = '執筆者別の記事';
    } elseif (is_date()) {
        $year = (int) get_query_var('year');
        $month = (int) get_query_var('monthnum');
        $day = (int) get_query_var('day');
        if ($year >= 1970 && $year <= 9999 && $month >= 1 && $month <= 12) {
            $label = $day >= 1 && $day <= 31
                ? sprintf('%d年%d月%d日の記事', $year, $month, $day)
                : sprintf('%d年%d月の記事', $year, $month);
        } elseif ($year >= 1970 && $year <= 9999) {
            $label = sprintf('%d年の記事', $year);
        } else {
            $label = '更新日別の記事';
        }
    } else {
        $label = '記事一覧';
    }
    $label = trim(wp_strip_all_tags((string) $label));
    if (! kurashinoshirube_is_clean_text($label, 2, 100)) {
        $label = '記事一覧';
    }
    return '<h1 class="raos-listing-title">' . esc_html($label) . '</h1>';
}
add_shortcode(
    'kurashinoshirube_archive_heading',
    'kurashinoshirube_render_archive_heading'
);

/** Return environment-specific policy-page head records from closed baselines. */
function kurashinoshirube_policy_page_head_map(): array
{
    $local = array(
        'about-ad-policy' => array(
            'description' => '暮らしのしるべの情報源、型番照合、広告との分離、更新・訂正と現在の問い合わせ窓口の扱いを説明します。',
            'title' => '運営・広告方針',
        ),
        'comparison-policy' => array(
            'description' => '暮らしのしるべの比較対象・除外、根拠の扱い、掲載順、販売条件、利益相反、更新・訂正の方針を説明します。',
            'title' => '比較・編集方針',
        ),
        'privacy-policy' => array(
            'description' => 'ローカルプレビューにおける計測送信、Cookie、第三者送信、権利請求、安全管理、変更履歴の扱いを説明します。',
            'title' => 'プライバシーポリシー',
        ),
    );
    $production = array(
        'about-ad-policy' => array(
            'description' => '暮らしのしるべの運営者、情報源と型番の照合、AI支援、広告との分離、更新・訂正の責任を説明します。',
            'title' => '運営・広告方針',
        ),
        'comparison-policy' => array(
            'description' => '公式情報の確かめ方、実機未使用の明示、Codexによる調査支援と運営者の公開承認、訂正手順を説明します。',
            'title' => '比較・編集方針',
        ),
        'privacy-policy' => array(
            'description' => '追加のアクセス・クリック計測を行わない方針と、問い合わせ情報や外部アフィリエイトリンクの取扱いを説明します。',
            'title' => 'プライバシーポリシー',
        ),
    );
    if (! kurashinoshirube_is_local_preview()) {
        return $production;
    }
    // The isolated mixed preview contains real baseline or proposed production
    // policy copy. It must not silently substitute local-only privacy wording.
    // This option has no effect at all outside the strict loopback environment.
    $mixed = get_option('raos_mixed_preview_policy_heads_v1', null);
    if ($mixed === null) {
        return $local;
    }
    if (
        ! is_array($mixed)
        || ($mixed['schema'] ?? null) !== 'RAOS_WORDPRESS_MIXED_PREVIEW_POLICY_HEADS_V1'
        || ($mixed['publication_profile'] ?? null) !== 'verified-incremental'
        || ($mixed['publication_authority'] ?? null) !== false
        || ! is_string($mixed['preparation_binding_sha256'] ?? null)
        || preg_match('/\A[a-f0-9]{64}\z/D', $mixed['preparation_binding_sha256']) !== 1
        || ! is_array($mixed['pages'] ?? null)
        || array_keys($mixed['pages']) !== array('about-ad-policy', 'comparison-policy', 'privacy-policy')
    ) {
        return array();
    }
    $heads = array();
    foreach ($mixed['pages'] as $slug => $record) {
        $post = get_page_by_path($slug, OBJECT, 'page');
        if (
            ! is_array($record)
            || ! is_string($record['title'] ?? null)
            || ! kurashinoshirube_is_clean_text($record['title'], 2, 100)
            || ! is_string($record['description'] ?? null)
            || ! kurashinoshirube_is_clean_text($record['description'], 30, 180)
            || ! is_string($record['content_sha256'] ?? null)
            || preg_match('/\A[a-f0-9]{64}\z/D', $record['content_sha256']) !== 1
            || ! ($post instanceof WP_Post)
            || get_post_status($post) !== 'publish'
            || get_post_field('post_title', $post->ID, 'raw') !== $record['title']
            || get_post_field('post_excerpt', $post->ID, 'raw') !== $record['description']
            || hash('sha256', (string) get_post_field('post_content', $post->ID, 'raw')) !== $record['content_sha256']
        ) {
            return array();
        }
        $heads[$slug] = array('title' => $record['title'], 'description' => $record['description']);
    }
    return $heads;
}

/**
 * Resolve one closed, public head context for home, Editorial V3, or policy.
 *
 * This is presentation data only. It never widens publication eligibility and
 * refuses a page whose persisted title or excerpt differs from the reviewed
 * fixture. Local preview URLs stay local; production URLs stay exact-origin.
 */
function kurashinoshirube_public_head_context(): ?array
{
    $local = kurashinoshirube_is_local_preview();
    $origin = $local
        ? kurashinoshirube_local_preview_origin()
        : KURASHINOSHIRUBE_SITE_ORIGIN;
    if (is_front_page()) {
        return array(
            'canonical_url' => $origin . '/',
            'description' => KURASHINOSHIRUBE_HOME_DESCRIPTION,
            'kind' => 'home',
            'title' => KURASHINOSHIRUBE_HOME_TITLE,
        );
    }
    if (is_singular('post')) {
        $post_id = (int) get_queried_object_id();
        $identity = $post_id > 0
            ? kurashinoshirube_public_article_identity($post_id)
            : null;
        $binding = is_array($identity)
            ? (kurashinoshirube_article_bindings()[$identity['article_id']] ?? null)
            : null;
        $title = $post_id > 0
            ? get_post_field('post_title', $post_id, 'raw')
            : null;
        $description = $post_id > 0
            ? get_post_field('post_excerpt', $post_id, 'raw')
            : null;
        $expected_slug = is_array($binding)
            ? ($local ? $binding['local_slug'] : $binding['slug'])
            : null;
        if (
            ! is_array($identity)
            || ! is_array($binding)
            || get_post_status($post_id) !== 'publish'
            || ($identity['slug'] ?? null) !== $expected_slug
            || ! is_string($title)
            || ! kurashinoshirube_is_clean_text($title, 8, 100)
            || ! is_string($description)
            || ! kurashinoshirube_is_clean_text($description, 30, 180)
        ) {
            return null;
        }
        return array(
            'canonical_url' => $origin . '/' . $expected_slug . '/',
            'description' => $description,
            'kind' => 'article',
            'section' => $identity['section'],
            'title' => $title,
        );
    }
    if (is_singular('page')) {
        $post_id = (int) get_queried_object_id();
        $slug = $post_id > 0
            ? get_post_field('post_name', $post_id, 'raw')
            : null;
        $head = is_string($slug)
            ? (kurashinoshirube_policy_page_head_map()[$slug] ?? null)
            : null;
        if (
            ! is_array($head)
            || get_post_status($post_id) !== 'publish'
            || get_post_field('post_title', $post_id, 'raw') !== $head['title']
            || get_post_field('post_excerpt', $post_id, 'raw')
                !== $head['description']
        ) {
            return null;
        }
        return array(
            'canonical_url' => $origin . '/' . $slug . '/',
            'description' => $head['description'],
            'kind' => 'fixed_page',
            'title' => $head['title'],
        );
    }
    return null;
}

/** Apply one validated snapshot value through Yoast's single metadata owner. */
function kurashinoshirube_filter_snapshot_value($original, string $field)
{
    $snapshot = kurashinoshirube_current_snapshot();
    return $snapshot === null ? $original : $snapshot[$field];
}

/** Keep the public shell's WordPress-generated control names in Japanese. */
function kurashinoshirube_translate_public_control_label(
    $translation,
    $text,
    $domain
) {
    unset($domain);
    if (is_admin() || ! is_string($text)) {
        return $translation;
    }
    $labels = array(
        'Close menu' => 'メニューを閉じる',
        'Expand search field' => '検索欄を開く',
        'Menu' => 'メニュー',
        'Open menu' => 'メニューを開く',
        'Pagination' => 'ページ送り',
        'Skip to content' => '本文へ移動',
        'Submit Search' => '検索する',
    );
    return $labels[$text] ?? $translation;
}
add_filter(
    'gettext',
    'kurashinoshirube_translate_public_control_label',
    20,
    3
);

/** Return one bounded Japanese title for every intentionally noindex route. */
function kurashinoshirube_non_index_title(): ?string
{
    if (is_search()) {
        $query = trim(wp_strip_all_tags((string) get_search_query(false)));
        if (! kurashinoshirube_is_clean_text($query, 1, 60)) {
            return '記事の検索結果｜暮らしのしるべ';
        }
        return '「' . $query . '」の検索結果｜暮らしのしるべ';
    }
    if (is_404()) {
        return 'ページが見つかりません｜暮らしのしるべ';
    }
    if (is_category()) {
        $label = trim(wp_strip_all_tags((string) single_cat_title('', false)));
        return kurashinoshirube_is_clean_text($label, 1, 60)
            ? '「' . $label . '」の記事一覧｜暮らしのしるべ'
            : 'カテゴリ別の記事一覧｜暮らしのしるべ';
    }
    if (is_tag()) {
        $label = trim(wp_strip_all_tags((string) single_tag_title('', false)));
        return kurashinoshirube_is_clean_text($label, 1, 60)
            ? '「' . $label . '」の記事一覧｜暮らしのしるべ'
            : 'タグ別の記事一覧｜暮らしのしるべ';
    }
    if (is_author()) {
        return '執筆者別の記事一覧｜暮らしのしるべ';
    }
    if (is_date()) {
        return '更新日別の記事一覧｜暮らしのしるべ';
    }
    if (is_post_type_archive()) {
        return '記事一覧｜暮らしのしるべ';
    }
    return null;
}

function kurashinoshirube_filter_title($value)
{
    $snapshot_value = kurashinoshirube_filter_snapshot_value($value, 'seo_title');
    if ($snapshot_value !== $value) {
        return $snapshot_value;
    }
    $non_index_title = kurashinoshirube_non_index_title();
    if ($non_index_title !== null) {
        return $non_index_title;
    }
    $context = kurashinoshirube_public_head_context();
    return $context === null ? $value : $context['title'];
}
function kurashinoshirube_filter_description($value)
{
    $snapshot_value = kurashinoshirube_filter_snapshot_value($value, 'description');
    if ($snapshot_value !== $value) {
        return $snapshot_value;
    }
    $context = kurashinoshirube_public_head_context();
    return $context === null ? $value : $context['description'];
}
function kurashinoshirube_filter_canonical($value)
{
    $snapshot = kurashinoshirube_current_snapshot();
    if ($snapshot !== null) {
        return $snapshot['canonical_url'];
    }
    $context = kurashinoshirube_public_head_context();
    return $context === null ? $value : $context['canonical_url'];
}
function kurashinoshirube_filter_og_title($value)
{
    $snapshot_value = kurashinoshirube_filter_snapshot_value($value, 'og_title');
    if ($snapshot_value !== $value) {
        return $snapshot_value;
    }
    $non_index_title = kurashinoshirube_non_index_title();
    if ($non_index_title !== null) {
        return $non_index_title;
    }
    $context = kurashinoshirube_public_head_context();
    return $context === null ? $value : $context['title'];
}
function kurashinoshirube_filter_og_description($value)
{
    $snapshot_value = kurashinoshirube_filter_snapshot_value($value, 'og_description');
    if ($snapshot_value !== $value) {
        return $snapshot_value;
    }
    $context = kurashinoshirube_public_head_context();
    return $context === null ? $value : $context['description'];
}
function kurashinoshirube_filter_social_image($value)
{
    $visual = kurashinoshirube_current_social_visual_asset();
    return $visual === null ? $value : $visual['uri'];
}
function kurashinoshirube_filter_social_image_width($value)
{
    $visual = kurashinoshirube_current_social_visual_asset();
    return $visual === null ? $value : $visual['width'];
}
function kurashinoshirube_filter_social_image_height($value)
{
    $visual = kurashinoshirube_current_social_visual_asset();
    return $visual === null ? $value : $visual['height'];
}
function kurashinoshirube_filter_social_image_type($value)
{
    return kurashinoshirube_current_social_visual_asset() === null
        ? $value
        : 'image/webp';
}
function kurashinoshirube_filter_twitter_card($value)
{
    return kurashinoshirube_current_snapshot() === null
        && kurashinoshirube_public_head_context() === null
        ? $value
        : 'summary_large_image';
}

/** Keep Yoast's author and reading-time labels consistent with the visible copy. */
function kurashinoshirube_filter_meta_author($value, $presentation)
{
    unset($presentation);
    $context = kurashinoshirube_public_head_context();
    return is_array($context) && ($context['kind'] ?? null) === 'article'
        ? '暮らしのしるべ編集者'
        : $value;
}

function kurashinoshirube_filter_enhanced_slack_data($data, $presentation): array
{
    $context = kurashinoshirube_public_head_context();
    if (! is_array($context) || ($context['kind'] ?? null) !== 'article') {
        return is_array($data) ? $data : array();
    }
    $localized = array('執筆' => '暮らしのしるべ編集者');
    $minutes = is_object($presentation)
        ? ($presentation->estimated_reading_time_minutes ?? null)
        : null;
    if (is_int($minutes) && $minutes > 0 && $minutes <= 999) {
        $localized['読了時間の目安'] = (string) $minutes . '分';
    }
    return $localized;
}

function kurashinoshirube_filter_og_type($value)
{
    $context = kurashinoshirube_public_head_context();
    if ($context === null) {
        return $value;
    }
    return $context['kind'] === 'article' ? 'article' : 'website';
}

function kurashinoshirube_filter_og_site_name($value)
{
    return kurashinoshirube_public_head_context() === null
        ? $value
        : '暮らしのしるべ';
}

function kurashinoshirube_filter_og_locale($value)
{
    return kurashinoshirube_public_head_context() === null
        ? $value
        : 'ja_JP';
}

/** Keep the WordPress title owner exact on the isolated no-Yoast preview. */
function kurashinoshirube_filter_local_document_title($title)
{
    if (defined('WPSEO_VERSION') || ! kurashinoshirube_is_local_preview()) {
        return $title;
    }
    $context = kurashinoshirube_public_head_context();
    return $context === null ? $title : $context['title'];
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
add_filter('wpseo_meta_author', 'kurashinoshirube_filter_meta_author', 10, 2);
add_filter(
    'wpseo_enhanced_slack_data',
    'kurashinoshirube_filter_enhanced_slack_data',
    10,
    2
);
add_filter('wpseo_opengraph_type', 'kurashinoshirube_filter_og_type');
add_filter('wpseo_opengraph_site_name', 'kurashinoshirube_filter_og_site_name');
add_filter('wpseo_og_locale', 'kurashinoshirube_filter_og_locale');
add_filter(
    'pre_get_document_title',
    'kurashinoshirube_filter_local_document_title',
    PHP_INT_MAX
);

/**
 * Supply the bounded SEO head only when the isolated preview has no Yoast.
 *
 * WordPress remains the document-title owner. The verified image is resolved
 * before core's singular canonical is removed, so an invalid asset fails closed
 * without suppressing upstream metadata. Production and unrelated routes never
 * enter this fallback.
 */
function kurashinoshirube_emit_local_fallback_head(): void
{
    if (defined('WPSEO_VERSION') || ! kurashinoshirube_is_local_preview()) {
        return;
    }
    $context = kurashinoshirube_public_head_context();
    $image = kurashinoshirube_verified_asset_uri(
        KURASHINOSHIRUBE_SOCIAL_IMAGE_PATH,
        KURASHINOSHIRUBE_SOCIAL_IMAGE_SHA256
    );
    if ($context === null || $image === null) {
        return;
    }
    remove_action('wp_head', 'rel_canonical');
    echo '<meta name="description" content="'
        . esc_attr($context['description']) . '">' . "\n";
    echo '<link rel="canonical" href="'
        . esc_url($context['canonical_url']) . '">' . "\n";
    echo '<meta property="og:title" content="'
        . esc_attr($context['title']) . '">' . "\n";
    echo '<meta property="og:description" content="'
        . esc_attr($context['description']) . '">' . "\n";
    echo '<meta property="og:url" content="'
        . esc_url($context['canonical_url']) . '">' . "\n";
    echo '<meta property="og:image" content="'
        . esc_url($image) . '">' . "\n";
}
add_action('wp_head', 'kurashinoshirube_emit_local_fallback_head', 5);

/** Index only a review-safe route or one exact public article identity. */
function kurashinoshirube_filter_robots($robots, $presentation)
{
    if (kurashinoshirube_is_local_preview()) {
        return 'noindex, nofollow, noarchive, nosnippet';
    }
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
    if (is_404()) {
        return 'noindex, nofollow';
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
        if (! is_array($binding)) {
            continue;
        }
        $is_production_slug = $slug === ($binding['slug'] ?? null);
        $is_local_slug = kurashinoshirube_is_local_preview()
            && $slug === ($binding['local_slug'] ?? null);
        if (! $is_production_slug && ! $is_local_slug) {
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

/** Emit only the required graph for home, one article, or one policy page. */
function kurashinoshirube_emit_json_ld(): void
{
    $context = kurashinoshirube_public_head_context();
    if ($context === null) {
        return;
    }
    $canonical = $context['canonical_url'];
    $schema_origin = kurashinoshirube_is_local_preview()
        ? kurashinoshirube_local_preview_origin()
        : KURASHINOSHIRUBE_SITE_ORIGIN;
    $organization_id = $schema_origin . '/#organization';
    $website_id = $schema_origin . '/#website';
    $nodes = array();
    if ($context['kind'] === 'article') {
        $post_id = (int) get_queried_object_id();
        $published = get_post_time('Y-m-d\TH:i:s\Z', true, $post_id);
        $modified = get_post_modified_time('Y-m-d\TH:i:s\Z', true, $post_id);
        $visual = kurashinoshirube_article_visual_asset($post_id);
        $image = is_array($visual)
            ? kurashinoshirube_verified_asset_uri(
                $visual['path'],
                $visual['sha256'],
                true
            )
            : null;
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
        $nodes[] = array(
            '@id' => $canonical . '#article',
            '@type' => 'Article',
            'articleSection' => $context['section'],
            'author' => array('@id' => $organization_id),
            'breadcrumb' => array('@id' => $canonical . '#breadcrumb'),
            'dateModified' => $modified,
            'datePublished' => $published,
            'description' => $context['description'],
            'headline' => $context['title'],
            'image' => array($image),
            'inLanguage' => 'ja-JP',
            'mainEntityOfPage' => $canonical,
            'publisher' => array('@id' => $organization_id),
            'url' => $canonical,
        );
    }
    if ($context['kind'] === 'fixed_page') {
        $page_id = (int) get_queried_object_id();
        $page_slug = get_post_field('post_name', $page_id, 'raw');
        if (! is_string($page_slug)) {
            return;
        }
        $nodes[] = array(
            '@id' => $canonical . '#webpage',
            '@type' => $page_slug === 'about-ad-policy'
                ? 'AboutPage'
                : 'WebPage',
            'breadcrumb' => array('@id' => $canonical . '#breadcrumb'),
            'description' => $context['description'],
            'inLanguage' => 'ja-JP',
            'isPartOf' => array('@id' => $website_id),
            'name' => $context['title'],
            'url' => $canonical,
        );
    }
    if (in_array($context['kind'], array('article', 'fixed_page'), true)) {
        $nodes[] = array(
            '@id' => $canonical . '#breadcrumb',
            '@type' => 'BreadcrumbList',
            'itemListElement' => array(
                array(
                    '@type' => 'ListItem',
                    'item' => $schema_origin . '/',
                    'name' => 'ホーム',
                    'position' => 1,
                ),
                array(
                    '@type' => 'ListItem',
                    'item' => $canonical,
                    'name' => $context['title'],
                    'position' => 2,
                ),
            ),
        );
    }
    $nodes[] = array(
        '@id' => $organization_id,
        '@type' => 'Organization',
        'name' => '暮らしのしるべ編集者',
        'url' => $schema_origin . '/',
    );
    $nodes[] = array(
        '@id' => $website_id,
        '@type' => 'WebSite',
        'inLanguage' => 'ja-JP',
        'name' => '暮らしのしるべ',
        'publisher' => array('@id' => $organization_id),
        'url' => $schema_origin . '/',
    );
    $graph = array(
        '@context' => 'https://schema.org',
        '@graph' => $nodes,
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

/** Replace Site Kit's executable payload with one closed inert configuration. */
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
        || isset($source_parts['port'])
        || isset($source_parts['user'])
        || isset($source_parts['pass'])
        || isset($source_parts['fragment'])
        || !is_string($source_parts['query'] ?? null)
        || preg_match(
            '/\Aid=(G-[A-Z0-9]{6,20})\z/D',
            $source_parts['query'],
            $measurement_match
        ) !== 1
        || !isset($measurement_match[1])
    ) {
        return '';
    }
    $measurement_id = $measurement_match[1];
    $canonical_source = 'https://www.googletagmanager.com/gtag/js?id='
        . rawurlencode($measurement_id);
    return '<script id="google_gtagjs-js" type="application/json"'
        . ' data-raos-consent-gate="statistics"'
        . ' data-raos-source="' . esc_attr($canonical_source) . '"'
        . ' data-raos-measurement-id="' . esc_attr($measurement_id) . '"'
        . '></script>';
}
add_filter(
    'script_loader_tag',
    'kurashinoshirube_gate_site_kit_analytics_loader',
    30,
    2
);

/**
 * Enqueue the fixed first-party measurement client only behind the host gate.
 * The plugin supplies a secret-free projection of the generated Editorial V3
 * identity allowlist. No destination URL or provider credential enters JS.
 */
function kurashinoshirube_enqueue_measurement_client(): void
{
    if (! kurashinoshirube_is_editorial_v2_post()
        || ! function_exists('raos_editorial_measurement_enabled')
        || ! raos_editorial_measurement_enabled()
        || ! function_exists('raos_editorial_measurement_client_context')) {
        return;
    }
    $post_id = get_queried_object_id();
    $identity = $post_id > 0
        ? kurashinoshirube_public_article_identity($post_id)
        : null;
    if (! is_array($identity)
        || ! is_string($identity['article_id'] ?? null)) {
        return;
    }
    $article = raos_editorial_measurement_client_context(
        $identity['article_id']
    );
    if (! is_array($article)) {
        return;
    }
    $endpoint = rest_url('raos/v1/events');
    $endpoint_parts = is_string($endpoint) ? wp_parse_url($endpoint) : false;
    if (! is_array($endpoint_parts)
        || ($endpoint_parts['scheme'] ?? null) !== 'https'
        || ($endpoint_parts['host'] ?? null) !== 'kurashinoshirube.com'
        || ($endpoint_parts['path'] ?? null) !== '/wp-json/raos/v1/events'
        || array_intersect_key(
            $endpoint_parts,
            array_flip(array('port', 'user', 'pass', 'query', 'fragment'))
        ) !== array()) {
        return;
    }
    $asset_uri = kurashinoshirube_verified_asset_uri(
        KURASHINOSHIRUBE_MEASUREMENT_ASSET_PATH,
        KURASHINOSHIRUBE_MEASUREMENT_ASSET_SHA256
    );
    if ($asset_uri === null) {
        return;
    }
    wp_enqueue_script(
        'kurashinoshirube-measurement-v1',
        $asset_uri,
        array(),
        KURASHINOSHIRUBE_THEME_VERSION . '-measurement-v1',
        array('in_footer' => true, 'strategy' => 'defer')
    );
    $configuration = wp_json_encode(
        array(
            'schema' => 'RAOSMeasurementClientConfigV1',
            'enabled' => true,
            'endpoint' => $endpoint,
            'disclosureVersion' => 'privacy-2026-08-30',
            'article' => $article,
        ),
        JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT
            | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE
    );
    if (! is_string($configuration)
        || false === wp_add_inline_script(
            'kurashinoshirube-measurement-v1',
            'window.RAOS_MEASUREMENT_CONFIG_V1=' . $configuration . ';',
            'before'
        )) {
        wp_dequeue_script('kurashinoshirube-measurement-v1');
    }
}
add_action(
    'wp_enqueue_scripts',
    'kurashinoshirube_enqueue_measurement_client',
    30
);
