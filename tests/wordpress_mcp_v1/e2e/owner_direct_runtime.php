<?php
/** Real WordPress and InnoDB integration; synthetic disposable data only. */
define('REST_REQUEST', true);
if ('setup' === ($argv[1] ?? '')) { define('WP_INSTALLING', true); }
require '/var/www/html/wp-load.php';
require_once ABSPATH . 'wp-admin/includes/upgrade.php';
require_once ABSPATH . 'wp-admin/includes/plugin.php';
function demand($value, $code) {
    if (is_wp_error($value)) { throw new RuntimeException($code . ':' . $value->get_error_code()); }
    if (true !== $value) { throw new RuntimeException($code . ':' . wp_json_encode($value)); }
}
if ('setup' === ($argv[1] ?? '')) {
    if (! is_blog_installed()) { wp_install('Synthetic owner-direct test', 'synthetic-admin', 'synthetic@example.invalid', false, '', wp_generate_password(32)); }
    update_option('active_plugins', array('raos-codex-mcp-abilities/raos-codex-mcp-abilities.php', 'wordpress-seo/wp-seo.php'));
    switch_theme('kurashinoshirube-child');
    echo "OWNER_DIRECT_SETUP_OK\n"; exit;
}
$plugin = RAOS_Codex_MCP_Abilities::instance();
RAOS_Codex_MCP_Store::install();
$role = RAOS_Codex_MCP_Owner_Direct::PUBLISHER_ROLE;
add_role($role, $role, RAOS_Codex_MCP_Owner_Direct::capabilities());
$publisher = wp_insert_user(array('user_login' => 'synthetic-publisher', 'user_pass' => wp_generate_password(32), 'role' => $role));
demand(is_int($publisher), 'PUBLISHER_CREATE');
wp_set_current_user($publisher);
$profile = array('profile' => 'owner-direct-v1', 'enabled' => true, 'publisher_user_id' => $publisher, 'configured_by' => 1,
    'allow_new_posts' => true, 'theme_slug' => 'kurashinoshirube-child', 'targets' => array());
update_option(RAOS_Codex_MCP_Owner_Direct::PROFILE_OPTION, $profile);
update_option(RAOS_Codex_MCP_Owner_Direct::BINDING_OPTION, (string) $publisher);
$auth = new WP_Error();
$plugin->constrain_application_password($auth, wp_get_current_user(), array('name' => RAOS_Codex_MCP_Owner_Direct::APP_NAME), 'synthetic-not-a-credential');
demand(! $auth->has_errors() && $plugin->owner_direct_permission(), 'PUBLISHER_BOUND');
$expected = new ReflectionMethod(RAOS_Codex_MCP_Content::class, 'expected_yoast_options');
foreach ($expected->invoke(null) as $name => $values) { update_option($name, array_replace(get_option($name, array()), $values)); }
demand(RAOS_Codex_MCP_Content::exact_yoast_gate(), 'YOAST_EXACT');
$direct = new RAOS_Codex_MCP_Owner_Direct($plugin);
$deploy = new RAOS_Codex_MCP_Deployment($plugin);
class OwnerDirectCommitAckLoss {
    public $inner; private $lost = false;
    public function __construct($inner) { $this->inner = $inner; }
    public function &__get($name) { return $this->inner->$name; }
    public function __set($name, $value) { $this->inner->$name = $value; }
    public function __call($name, $args) { return $this->inner->$name(...$args); }
    public function query($sql) {
        $result = $this->inner->query($sql);
        if (! $this->lost && 'COMMIT' === $sql) { $this->lost = true; return false; }
        return $result;
    }
}
function request($body, $params = array()) {
    $r = new WP_REST_Request('POST'); $r->set_header('Content-Type', 'application/json');
    $r->set_body(wp_json_encode($body)); $r->set_url_params($params); return $r;
}
function draft($key) {
    global $direct;
    $result = $direct->ensure_draft(request(array('profile' => 'owner-direct-v1', 'article_key' => $key, 'slug' => $key, 'idempotency_key' => hash('sha256', $key))));
    demand(! is_wp_error($result), 'DRAFT_CREATE_' . (is_wp_error($result) ? $result->get_error_code() : ''));
    $again = $direct->ensure_draft(request(array('profile' => 'owner-direct-v1', 'article_key' => $key, 'slug' => $key, 'idempotency_key' => hash('sha256', $key))));
    demand($again['id'] === $result['id'], 'DRAFT_REPLAY'); return $result;
}
// Lose a real successful InnoDB COMMIT acknowledgement; retry recovers actual ID.
$original_db = $wpdb; $wpdb = new OwnerDirectCommitAckLoss($original_db);
$ambiguous_input = array('profile' => 'owner-direct-v1', 'article_key' => 'synthetic-ambiguous', 'slug' => 'synthetic-ambiguous', 'idempotency_key' => hash('sha256', 'synthetic-ambiguous'));
try { $unknown = $direct->ensure_draft(request($ambiguous_input)); }
finally { $wpdb = $original_db; }
demand(is_wp_error($unknown) && 'raos_codex_owner_direct_draft_outcome_unknown' === $unknown->get_error_code(), 'AMBIGUOUS_COMMIT_REPORTED');
$reconciled = $direct->ensure_draft(request($ambiguous_input));
demand(! is_wp_error($reconciled), 'AMBIGUOUS_COMMIT_RECOVERED');
demand((int) $wpdb->get_var("SELECT COUNT(*) FROM {$wpdb->posts} WHERE post_name = 'synthetic-ambiguous'") === 1, 'AMBIGUOUS_COMMIT_NO_DUPLICATE');
echo "OWNER_DIRECT_SQL_DRAFT_COMMIT_ACK_LOSS_OK\n";
function proposal($draft, $title) {
    global $direct;
    $doc = RAOS_Codex_MCP_Content::document($draft['id']);
    $write = array_intersect_key($doc, array_flip(array('post_type', 'title', 'slug', 'excerpt', 'block_markup', 'taxonomies', 'media_ids')));
    $write['title'] = $title; $write['block_markup'] = '<!-- wp:paragraph --><p>Synthetic content ' . $title . '.</p><!-- /wp:paragraph -->';
    $pre = array_intersect_key($doc, array_flip(array('revision_id', 'modified_gmt', 'content_sha256')));
    $result = $direct->content_proposal(request(array('profile' => 'owner-direct-v1', 'article_key' => $draft['article_key'], 'id' => $draft['id'],
        'precondition' => $pre, 'document' => $write, 'idempotency_key' => hash('sha256', $title))));
    if (is_wp_error($result)) { throw new RuntimeException('CONTENT_PROPOSAL:' . $result->get_error_code()); }
    return $result;
}
function batch($proposals, $theme_after = null) {
    global $direct, $deploy;
    $body = array('profile' => 'owner-direct-v1', 'proposal_ids' => array_column($proposals, 'proposal_id'),
        'expected_theme_tree_sha256' => $theme_after ?? RAOS_Codex_MCP_Deployment::active_theme_tree_sha256());
    $result = $direct->authorize(request($body));
    if (is_wp_error($result)) throw new RuntimeException('AUTHORIZE:' . $result->get_error_code());
    $again = $direct->authorize(request($body));
    demand(! is_wp_error($again) && $again['batch_token'] === $result['batch_token'] && $again['expires_at_gmt'] === $result['expires_at_gmt'], 'AUTHORIZE_REPLAY_NO_RENEWAL');
    $claim = request(array('batch_manifest_sha256' => $result['batch_manifest_sha256'], 'proposal_ids' => $result['proposal_ids']), array('batch_token' => $result['batch_token']));
    $claim->set_header('If-Match', '"' . $result['batch_manifest_sha256'] . '"');
    $claim->set_header('Idempotency-Key', $result['batch_token']);
    $claimed = $deploy->claim_publication_batch($claim);
    if (is_wp_error($claimed)) throw new RuntimeException('CLAIM:' . $claimed->get_error_code());
    return $result;
}
function apply($proposal, $batch) {
    global $deploy;
    $r = request(array('batch_token' => $batch['batch_token'], 'batch_manifest_sha256' => $batch['batch_manifest_sha256']), array('proposal_id' => $proposal['proposal_id']));
    $r->set_header('If-Match', '"' . $proposal['proposal_id'] . '"'); $r->set_header('Idempotency-Key', $proposal['proposal_id']);
    $r->set_header('X-RAOS-Batch-Token', $batch['batch_token']);
    $r->set_header('X-RAOS-Batch-Manifest-SHA256', $batch['batch_manifest_sha256']);
    $result = $deploy->apply_proposal($r);
    if (is_wp_error($result)) { echo 'APPLY_RESULT:' . $result->get_error_code() . "\n"; }
    return $result;
}
function finish($batch, $action) {
    global $direct;
    $value = $direct->finish(request(array('profile' => 'owner-direct-v1', 'batch_manifest_sha256' => $batch['batch_manifest_sha256'], 'action' => $action), array('batch_token' => $batch['batch_token'])));
    if (is_wp_error($value)) throw new RuntimeException('FINISH:' . $value->get_error_code());
    if ('PARTIAL_CONFLICT' === $value['state']) { echo 'FINISH_RESULT:' . wp_json_encode($value['members']) . "\n"; }
    return $value;
}
$first = draft('synthetic-first'); $second = draft('synthetic-second');
$one = proposal($first, 'First'); $two = proposal($second, 'Second'); $b = batch(array($one, $two));
demand(! is_wp_error(apply($one, $b)), 'FIRST_APPLY');
demand(is_array(RAOS_Codex_MCP_Owner_Direct::public_article_snapshot($first['id'])), 'PUBLIC_PROJECTION');
wp_update_post(array('ID' => $second['id'], 'post_title' => 'Concurrent editor'));
demand(is_wp_error(apply($two, $b)), 'STALE_SECOND_REFUSED');
$rolled = finish($b, 'rollback'); demand($rolled['state'] === 'ROLLED_BACK', 'BATCH_COMPENSATED');
demand(get_post($first['id'])->post_status === 'draft', 'NEW_POST_RESTORED_DRAFT');
demand(get_post($second['id'])->post_title === 'Concurrent editor', 'OTHER_EDITOR_PRESERVED');
demand(finish($b, 'rollback') === $rolled, 'ROLLBACK_REPLAY');
$new = proposal($first, 'Publish baseline'); $b = batch(array($new)); demand(! is_wp_error(apply($new, $b)), 'BASELINE_APPLY');
demand(finish($b, 'finalize')['state'] === 'FINALIZED', 'FINALIZE');
$before = RAOS_Codex_MCP_Content::document($first['id']);
$update = proposal($first, 'Updated existing'); $b = batch(array($update)); demand(! is_wp_error(apply($update, $b)), 'EXISTING_UPDATE');
demand(finish($b, 'rollback')['state'] === 'ROLLED_BACK', 'EXISTING_COMPENSATED');
demand(RAOS_Codex_MCP_Content::document($first['id'])['content_sha256'] === $before['content_sha256'], 'EXISTING_RESTORED_EXACTLY');
$update = proposal($first, 'Concurrent guard'); $b = batch(array($update)); demand(! is_wp_error(apply($update, $b)), 'GUARD_APPLY');
wp_update_post(array('ID' => $first['id'], 'post_title' => 'Other later editor'));
demand(finish($b, 'rollback')['state'] === 'PARTIAL_CONFLICT', 'ROLLBACK_CONFLICT_REFUSED');
demand(get_post($first['id'])->post_title === 'Other later editor', 'LATER_EDITOR_NOT_OVERWRITTEN');
echo "OWNER_DIRECT_SQL_CONTENT_COMPENSATION_OK\n";

// Theme-only and theme+content use the same limited principal and retained backup.
function theme_proposal($version) {
    global $direct;
    $files = array('functions.php' => "<?php // Synthetic theme " . $version . ".\n",
        'style.css' => "/*\nTheme Name: RAOS disposable child\nTemplate: twentytwentyfive\nVersion: " . $version . "\n*/\n");
    $manifest = array(); $path = RAOS_CODEX_PRIVATE_DIR . '/synthetic-package.zip';
    $zip = new ZipArchive(); $zip->open($path, ZipArchive::CREATE | ZipArchive::OVERWRITE);
    foreach ($files as $name => $bytes) {
        $zip->addFromString('kurashinoshirube-child/' . $name, $bytes);
        $zip->setExternalAttributesName('kurashinoshirube-child/' . $name, ZipArchive::OPSYS_UNIX, 0100644 << 16);
        $manifest[] = array('path' => $name, 'size' => strlen($bytes), 'sha256' => hash('sha256', $bytes));
    }
    $zip->close(); $bytes = file_get_contents($path); unlink($path);
    $package = array('schema' => 'CodePackageV1', 'kind' => 'theme', 'source' => 'tracked_child_theme', 'artifact_id' => null,
        'git_commit' => str_repeat('a', 40), 'slug' => 'kurashinoshirube-child', 'old_version' => '1.0.0', 'new_version' => $version,
        'package_sha256' => hash('sha256', $bytes), 'file_manifest_sha256' => RAOS_Codex_MCP_Store::hash($manifest), 'file_manifest' => $manifest,
        'activation_intent' => 'preserve', 'migration_assessment' => 'NO_IRREVERSIBLE_MIGRATION_SIGNALS', 'automatic_apply_eligible' => true);
    $result = $direct->theme_proposal(request(array('profile' => 'owner-direct-v1', 'kind' => 'theme_release', 'code_package' => $package,
        'package_base64' => base64_encode($bytes), 'idempotency_key' => hash('sha256', $version))));
    if (is_wp_error($result)) throw new RuntimeException('THEME_PROPOSAL:' . $result->get_error_code());
    return $result['proposal'];
}
$theme_before = RAOS_Codex_MCP_Deployment::active_theme_tree_sha256();
$theme = theme_proposal('1.1.0');
$third = draft('synthetic-third'); $content = proposal($third, 'Third');
$b = batch(array($theme, $content), $theme['after_tree_sha256']);
demand(! is_wp_error(apply($theme, $b)), 'THEME_APPLY');
demand(is_dir(RAOS_CODEX_PRIVATE_DIR . '/operation-' . $theme['proposal_id'] . '/before'), 'THEME_BACKUP_RETAINED');
wp_update_post(array('ID' => $third['id'], 'post_title' => 'Another editor'));
demand(is_wp_error(apply($content, $b)), 'THEME_BATCH_SECOND_FAILED');
demand(finish($b, 'rollback')['state'] === 'ROLLED_BACK', 'THEME_COMPENSATED');
demand(RAOS_Codex_MCP_Deployment::active_theme_tree_sha256() === $theme_before, 'THEME_BEFORE_EXACT');
$theme = theme_proposal('1.2.0'); $b = batch(array($theme), $theme['after_tree_sha256']);
demand(! is_wp_error(apply($theme, $b)), 'THEME_ONLY_APPLY');
$final = finish($b, 'finalize'); demand($final['state'] === 'FINALIZED', 'THEME_ONLY_FINALIZE');
demand(finish($b, 'finalize') === $final, 'FINALIZE_REPLAY');
echo "OWNER_DIRECT_SQL_THEME_COMPENSATION_OK\n";

// Lose the terminal acknowledgement after member mutation/cleanup, then resume.
$fourth = draft('synthetic-fourth'); $content = proposal($fourth, 'Interrupted finalize'); $b = batch(array($content));
demand(! is_wp_error(apply($content, $b)), 'INTERRUPTED_FINALIZE_APPLY');
function interrupt_finish_once($batch, $action) {
    $hook = 'pre_update_option_raos_codex_owner_direct_finish_' . $batch['batch_token'];
    $terminal = 'finalize' === $action ? 'FINALIZED' : 'ROLLED_BACK';
    $interrupt = static function ($value) use ($terminal) {
        if (($value['state'] ?? null) === $terminal) { throw new RuntimeException('SYNTHETIC_FINISH_RESPONSE_LOSS'); }
        return $value;
    };
    add_filter($hook, $interrupt);
    try { finish($batch, $action); throw new RuntimeException('FINISH_NOT_INTERRUPTED'); }
    catch (RuntimeException $error) { demand($error->getMessage() === 'SYNTHETIC_FINISH_RESPONSE_LOSS', 'EXPECTED_INTERRUPT'); }
    finally { remove_filter($hook, $interrupt); }
    $result = finish($batch, $action);
    demand($result['state'] === $terminal, 'INTERRUPTED_FINISH_RESUMED');
    demand(finish($batch, $action) === $result, 'INTERRUPTED_FINISH_IDEMPOTENT');
}
interrupt_finish_once($b, 'finalize');
$before = RAOS_Codex_MCP_Content::document($fourth['id']);
$content = proposal($fourth, 'Interrupted rollback'); $b = batch(array($content));
demand(! is_wp_error(apply($content, $b)), 'INTERRUPTED_ROLLBACK_APPLY');
interrupt_finish_once($b, 'rollback');
demand(RAOS_Codex_MCP_Content::document($fourth['id'])['content_sha256'] === $before['content_sha256'], 'INTERRUPTED_ROLLBACK_RESTORED');
echo "OWNER_DIRECT_SQL_INTERRUPTED_FINISH_OK\n";
