<?php
/** Local-only materialization of exactly the reviewed owner-direct documents. */
if (!defined('WP_CLI') || WP_CLI !== true || !defined('RAOS_LOCAL_PREVIEW') || RAOS_LOCAL_PREVIEW !== true
    || wp_get_environment_type() !== 'local'
    || !preg_match('~^http://127\.0\.0\.1:[0-9]{4,5}$~D', (string)get_option('home'))) {
    exit(69);
}
/** Adopt only WordPress's untouched install-time draft, never a custom local page.
 * This reuses local ID 3 and its privacy option; production IDs are not involved.
 */
function raos_direct_preview_is_initial_privacy_draft($post, array $document): bool
{
    if (!$post || (int)$post->ID !== 3 || (int)get_option('wp_page_for_privacy_policy') !== 3
        || ($document['post_type'] ?? null) !== 'page' || ($document['slug'] ?? null) !== 'privacy-policy'
        || $post->post_type !== 'page' || $post->post_status !== 'draft' || $post->post_name !== 'privacy-policy'
        || $post->post_title !== __('Privacy Policy') || $post->post_excerpt !== '' || (int)$post->post_parent !== 0
        || $post->post_date !== $post->post_modified || $post->post_date_gmt !== $post->post_modified_gmt
        || get_post_meta($post->ID) !== array('_wp_page_template' => array('default'))) {
        return false;
    }
    if (!class_exists('WP_Privacy_Policy_Content')) {
        require_once ABSPATH . 'wp-admin/includes/class-wp-privacy-policy-content.php';
    }
    return $post->post_content === WP_Privacy_Policy_Content::get_default_content();
}
/** Recognize only the untouched English install sample in this local database. */
function raos_direct_preview_is_initial_sample($post): bool
{
    return $post && (int)$post->ID === 1 && (int)$post->post_author === 1
        && $post->post_type === 'post' && $post->post_status === 'publish'
        && $post->post_name === 'hello-world' && $post->post_title === 'Hello world!'
        && $post->post_excerpt === '' && (int)$post->post_parent === 0
        && $post->post_date === $post->post_modified
        && $post->post_date_gmt === $post->post_modified_gmt
        && get_post_meta($post->ID) === array()
        && $post->post_content === "<!-- wp:paragraph -->\n<p>Welcome to WordPress. This is your first post. Edit or delete it, then start writing!</p>\n<!-- /wp:paragraph -->";
}
$input = json_decode(file_get_contents('/var/www/raos-direct-candidate/preview-input.json'), true, 64);
if (!is_array($input) || ($input['candidate']['profile'] ?? null) !== 'owner-direct-v1') {
    WP_CLI::error('DIRECT_PREVIEW_INPUT_INVALID');
}
$candidate = $input['candidate'];
$articles = $candidate['articles'];
$preview_admin = get_user_by('login', 'raos-local-admin');
if (!$preview_admin) { WP_CLI::error('DIRECT_PREVIEW_ADMIN_MISSING'); }
wp_set_current_user($preview_admin->ID);
kses_init();
if (!current_user_can('unfiltered_html')) { WP_CLI::error('DIRECT_PREVIEW_HTML_CAPABILITY_MISSING'); }
// Reversible local cleanup; edited or owner-bound posts are left untouched.
if (raos_direct_preview_is_initial_sample(get_post(1))) {
    $sample_result = wp_update_post(array('ID' => 1, 'post_status' => 'draft'), true);
    if (is_wp_error($sample_result) || get_post_status(1) !== 'draft') {
        WP_CLI::error('DIRECT_PREVIEW_SAMPLE_DRAFT_FAILED');
    }
}

if (!$articles && !empty($candidate['theme'])) {
    $articles = array(array('article_key' => 'direct-preview-example', 'document' => array(
        'post_type' => 'post', 'slug' => 'direct-preview-example', 'title' => 'ローカル表示確認用の記事',
        'excerpt' => 'テーマの表示だけを確認するローカル専用の記事です。本番には公開されません。',
        'block_markup' => '<!-- wp:paragraph --><p>これはローカル専用の表示確認です。</p><!-- /wp:paragraph -->'
            . '<!-- wp:heading --><h2 class="wp-block-heading">見出しと本文の確認</h2><!-- /wp:heading -->'
            . '<!-- wp:paragraph --><p>スマートフォンとパソコンで文字と余白を確認します。</p><!-- /wp:paragraph -->',
        'taxonomies' => array(), 'media_ids' => array(),
    )));
}
foreach ($articles as $article) {
    $document = $article['document'];
    if (!in_array($document['post_type'] ?? null, array('post', 'page'), true)
        || !preg_match('/^[a-z0-9]+(?:-[a-z0-9]+)*$/D', $document['slug'] ?? '')) {
        WP_CLI::error('DIRECT_PREVIEW_DOCUMENT_INVALID');
    }
    $existing = get_page_by_path($document['slug'], OBJECT, $document['post_type']);
    if ($existing && get_post_meta($existing->ID, '_raos_owner_direct_preview_key', true) !== $article['article_key']
        && !raos_direct_preview_is_initial_privacy_draft($existing, $document)) {
        WP_CLI::error('DIRECT_PREVIEW_LOCAL_SLUG_CONFLICT');
    }
    $fields = array('post_type' => $document['post_type'], 'post_name' => $document['slug'],
        'post_title' => $document['title'], 'post_excerpt' => $document['excerpt'],
        'post_content' => $document['block_markup'], 'post_status' => 'publish');
    $unchanged = $existing !== null;
    foreach ($fields as $key => $value) {
        if (!$existing || $existing->$key !== $value) {
            $unchanged = false;
        }
    }
    if ($existing) {
        $fields['ID'] = $existing->ID;
    }
    $id = $unchanged ? $existing->ID : wp_insert_post(wp_slash($fields), true);
    if (is_wp_error($id) || !$id) {
        WP_CLI::error('DIRECT_PREVIEW_INSERT_FAILED');
    }
    $saved = get_post($id);
    foreach ($fields as $key => $value) {
        if ($key !== 'ID' && $saved->$key !== $value) {
            WP_CLI::error('DIRECT_PREVIEW_SAVED_CONTENT_MISMATCH');
        }
    }
    if ($document['post_type'] === 'page' && $document['slug'] === 'home') {
        update_option('show_on_front', 'page');
        update_option('page_on_front', $id);
    }
    update_post_meta($id, '_raos_owner_direct_preview_key', $article['article_key']);
    update_post_meta($id, '_raos_owner_direct_preview_document', array(
        'id' => $id, 'post_type' => $document['post_type'], 'slug' => $document['slug'],
        'title' => $document['title'], 'excerpt' => $document['excerpt'],
        'block_markup' => $document['block_markup'], 'content_sha256' => hash('sha256', $document['block_markup']),
    ));
}
update_option('blog_public', '0');
update_option('blogname', '暮らしのしるべ');
update_option('timezone_string', 'Asia/Tokyo');
update_option('WPLANG', 'ja');
$wpseo = get_option('wpseo', array());
foreach ($input['yoast_configuration']['wpseo_option_values'] as $key => $value) {
    $wpseo[$key] = $value;
}
update_option('wpseo', $wpseo);
$social = get_option('wpseo_social', array());
foreach ($input['yoast_configuration']['wpseo_social_option_values'] as $key => $value) {
    $social[$key] = $value === 'VERIFIED_THEME_SOCIAL_IMAGE_URI'
        ? kurashinoshirube_verified_asset_uri(KURASHINOSHIRUBE_SOCIAL_IMAGE_PATH, KURASHINOSHIRUBE_SOCIAL_IMAGE_SHA256, true)
        : $value;
}
update_option('wpseo_social', $social);
WP_CLI::log('DIRECT_PREVIEW_SEEDED');
