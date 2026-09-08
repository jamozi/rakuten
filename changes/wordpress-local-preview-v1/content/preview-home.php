<?php
/** Restore authored home content only in this checkout's isolated local preview. */
require '/var/www/html/wp-load.php';
if (! defined('RAOS_LOCAL_PREVIEW') || RAOS_LOCAL_PREVIEW !== true
    || wp_get_environment_type() !== 'local'
    || get_option('home') !== RAOS_WORDPRESS_PREVIEW_ORIGIN
    || ! preg_match('~^http://127\.0\.0\.1:[0-9]{4,5}$~D', RAOS_WORDPRESS_PREVIEW_ORIGIN)) {
    exit(69);
}
$author = get_user_by('login', 'raos-local-admin');
if (! $author) { exit(69); }
wp_set_current_user($author->ID);
kses_init();
if (! current_user_can('unfiltered_html')) { exit(69); }
$body = file_get_contents('/var/www/raos-local-preview/content/home.html');
if (! is_string($body) || substr_count($body, 'id="ks-magazine"') !== 1 || substr_count($body, '<h1 ') !== 1) { exit(69); }
foreach (kurashinoshirube_article_bindings() as $binding) {
    $body = str_replace('href="/' . $binding['slug'] . '/"', 'href="/' . $binding['local_slug'] . '/"', $body);
}
$slug = 'local-preview-magazine-home';
$existing = get_page_by_path($slug, OBJECT, 'page');
if ($existing && get_post_meta($existing->ID, '_raos_journey_home', true) !== '1') { exit(69); }
$front = (int) get_option('page_on_front');
if ($front > 0 && (! $existing || $front !== (int) $existing->ID)) { exit(69); }
$fields = array('post_type' => 'page', 'post_status' => 'publish', 'post_name' => $slug,
    'post_title' => '暮らしのしるべ', 'post_content' => $body, 'post_password' => '',
    'comment_status' => 'closed', 'ping_status' => 'closed');
if ($existing) { $fields['ID'] = $existing->ID; }
$id = $existing && $existing->post_content === $body ? $existing->ID : wp_insert_post(wp_slash($fields), true);
if (is_wp_error($id) || ! $id) { exit(69); }
update_post_meta($id, '_raos_journey_home', '1');
if (get_post_field('post_content', $id, 'raw') !== $body) { exit(69); }
update_option('page_on_front', (int) $id);
update_option('show_on_front', 'page');
update_option('blog_public', '0');
echo "LOCAL_SAVED_HOME_RESTORED\n";
