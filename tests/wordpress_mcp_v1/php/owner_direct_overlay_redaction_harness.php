<?php
/** KS-020 purge publish: stored price-overlay bodies and injected-theme hashes become markers. No WordPress bootstrap or network. */
declare(strict_types=1);
// A guard that only emits a Warning or Notice must still fail the harness.
set_error_handler(static function ($severity, $message, $file, $line) { throw new ErrorException($message, 0, $severity, $file, $line); });
define('ABSPATH', __DIR__ . '/');
define('ARRAY_A', 'ARRAY_A');
define('WP_CONTENT_DIR', __DIR__);
define('RAOS_OPERATOR_WRITES_ENABLED', true);
class WP_Error {
    public function __construct(public string $code, $message = '', public $data = array()) {}
    public function get_error_code() { return $this->code; }
    public function get_error_message() { return 'synthetic'; }
    public function get_error_data() { return $this->data; }
}
function is_wp_error($value) { return $value instanceof WP_Error; }
function wp_json_encode($value, $flags = 0) { return json_encode($value, $flags); }
function get_option($key, $default = false) { return $GLOBALS['options'][$key] ?? $default; }
function update_option($key, $value, $autoload = null) { $GLOBALS['options'][$key] = $value; return true; }
function get_current_user_id() { return 7; }
function current_user_can($capability) { return 'raos_codex_owner_direct_publish' === $capability; }
function get_stylesheet() { return 'kurashinoshirube-child'; }
function get_theme_root($slug = null) { return $GLOBALS['theme_root']; }
final class WP_Post {
    public function __construct(public int $ID, public string $post_type, public string $post_status, public string $post_title,
        public string $post_name, public string $post_excerpt, public string $post_content, public string $post_modified_gmt,
        public string $post_modified) {}
}
function get_post($id) { return $GLOBALS['posts'][(int) $id] ?? null; }
function wp_get_post_revisions($id, $args = array()) { return array(); }
function get_object_taxonomies($type, $output = 'names') { return array(); }
function wp_get_object_terms($id, $taxonomy, $args = array()) { return array(); }
function get_post_thumbnail_id($id) { return 0; }
function get_post_type($id) { return 'post'; }
class RAOS_Codex_MCP_Abilities {
    public static function runtime_identity_gate() { return true; }
    public static function plugin_runtime_revision() { return RAOS_Codex_MCP_Store::RUNTIME_REVISION; }
}
final class OverlayRedactionDB {
    public $prefix = 'synthetic_';
    public $last_error = '';
    public $rows = array();
    public $batches = array();
    public $fail_update = false;
    public $fail_update_kinds = array();
    public function esc_like($text) { return addcslashes($text, '_%\\'); }
    public function prepare($sql, ...$values) { return array($sql, $values); }
    public function get_results($prepared, $output = null) {
        [$sql, $values] = $prepared;
        $found = array();
        if ("SELECT proposal_id, state, before_sha256, after_sha256, payload_json FROM synthetic_raos_codex_operations_v1 WHERE kind = 'THEME_RELEASE' AND created_by = %d AND (before_sha256 = %s OR after_sha256 = %s)" === $sql) {
            foreach ($this->rows as $row) {
                if ('THEME_RELEASE' === $row['kind'] && (int) $row['created_by'] === $values[0]
                    && ($row['before_sha256'] === $values[1] || $row['after_sha256'] === $values[2])) {
                    $found[] = array_intersect_key($row, array_flip(array('proposal_id', 'state', 'before_sha256', 'after_sha256', 'payload_json')));
                }
            }
            return $found;
        }
        if ("SELECT proposal_id, state, payload_json FROM synthetic_raos_codex_operations_v1 WHERE kind = 'CONTENT_RELEASE' AND created_by = %d AND payload_json LIKE %s" !== $sql
            || '%data-ps-overlay-run=%' !== $values[1]) { throw new RuntimeException('UNEXPECTED_SELECT'); }
        foreach ($this->rows as $row) {
            if ('CONTENT_RELEASE' === $row['kind'] && (int) $row['created_by'] === $values[0] && str_contains($row['payload_json'], 'data-ps-overlay-run=')) {
                $found[] = array('proposal_id' => $row['proposal_id'], 'state' => $row['state'], 'payload_json' => $row['payload_json']);
            }
        }
        return $found;
    }
    public function get_row($prepared, $output = null) {
        [$sql, $values] = $prepared;
        if ('SELECT * FROM synthetic_raos_codex_operations_v1 WHERE proposal_id = %s LIMIT 1' === $sql) { return $this->rows[$values[0]] ?? null; }
        if ('SELECT * FROM synthetic_raos_codex_publication_batches_v1 WHERE batch_token = %s LIMIT 1' === $sql) { return $this->batches[$values[0]] ?? null; }
        throw new RuntimeException('UNEXPECTED_ROW_SELECT');
    }
    public function query($prepared) {
        [$sql, $values] = $prepared;
        if ('UPDATE synthetic_raos_codex_operations_v1 SET payload_json = %s WHERE proposal_id = %s AND state = %s AND payload_json = %s' !== $sql) { throw new RuntimeException('UNEXPECTED_UPDATE'); }
        [$json, $id, $state, $old] = $values;
        if ($this->fail_update || ! isset($this->rows[$id]) || $this->rows[$id]['state'] !== $state || $this->rows[$id]['payload_json'] !== $old
            || in_array($this->rows[$id]['kind'], $this->fail_update_kinds, true)) { return 0; }
        $this->rows[$id]['payload_json'] = $json;
        return 1;
    }
}
function demand($condition, $code) { if ($condition !== true) { throw new RuntimeException($code); } }
$includes = dirname(__DIR__, 3) . '/changes/wordpress-mcp-v1/wordpress-plugin/raos-codex-mcp-abilities/includes/';
require $includes . 'class-raos-codex-mcp-store.php';
require $includes . 'class-raos-codex-mcp-content.php';
require $includes . 'class-raos-codex-mcp-deployment.php';
require $includes . 'class-raos-codex-mcp-owner-direct.php';
$GLOBALS['wpdb'] = $db = new OverlayRedactionDB();
$GLOBALS['options'][RAOS_Codex_MCP_Owner_Direct::PROFILE_OPTION] = array(
    'profile' => 'owner-direct-v1', 'enabled' => true, 'publisher_user_id' => 7, 'configured_by' => 1,
    'allow_new_posts' => false, 'theme_slug' => 'kurashinoshirube-child',
    'targets' => array(
        array('article_key' => 'existing', 'post_id' => 12, 'post_type' => 'post', 'slug' => 'existing'),
        array('article_key' => 'other', 'post_id' => 13, 'post_type' => 'post', 'slug' => 'other'),
    ),
);
$GLOBALS['direct'] = new RAOS_Codex_MCP_Owner_Direct(new RAOS_Codex_MCP_Abilities());
// Synthetic values only.
$run = 'ks020-synthetic-0001';
$free = '<div class="ps-seller" data-ps-offer="harness-offer"><p class="ps-price-date">販売条件確認</p></div>';
$injected = '<div class="ps-seller" data-ps-offer="harness-offer" data-ps-price-yen="98760" data-ps-overlay-run="' . $run . '"><p class="ps-price-date">販売条件確認</p></div>';
$injected_other_run = str_replace($run, 'ks020-synthetic-0002', $injected);

function doc($id, $slug, $markup, $revision) {
    return array('schema' => 'ContentDocumentV1', 'post_type' => 'post', 'id' => $id, 'status' => 'publish', 'title' => $slug,
        'slug' => $slug, 'excerpt' => '', 'block_markup' => $markup, 'taxonomies' => array(), 'media_ids' => array(),
        'revision_id' => $revision, 'modified_gmt' => '2026-09-15 00:00:0' . $revision,
        'content_sha256' => str_repeat((string) $revision, 64));
}
function proposal($char, $state, $before, $after) {
    $before_sha256 = RAOS_Codex_MCP_Content::document_hash($before);
    $after_sha256 = RAOS_Codex_MCP_Content::document_hash($after);
    $created = '2026-09-15 01:00:00';
    $approved = in_array($state, array('APPLIED', 'FAILED'), true) ? '2026-09-15 01:10:00' : null;
    $expires = null === $approved ? '2026-09-15 02:00:00' : '2026-09-15 01:25:00';
    $proposal_id = str_repeat($char, 64);
    $payload = array('schema' => 'ContentReleaseProposalV1',
        'authorization_profile' => $GLOBALS['direct']->binding($after['slug']),
        'before' => $before, 'after' => $after, 'before_sha256' => $before_sha256, 'after_sha256' => $after_sha256,
        'publication_manifest_sha256' => RAOS_Codex_MCP_Store::hash(array(
            'schema' => 'ContentPublicationManifestV1', 'target_status' => 'publish',
            'post_type' => $before['post_type'], 'post_id' => $before['id'],
            'before_sha256' => $before_sha256, 'after_sha256' => $after_sha256,
            'precondition' => array('revision_id' => $before['revision_id'], 'modified_gmt' => $before['modified_gmt'], 'content_sha256' => $before_sha256),
        )),
        'proposal_id' => $proposal_id, 'created_by' => 7,
        'created_at_gmt' => RAOS_Codex_MCP_Store::timestamp_iso($created),
        'expires_at_gmt' => RAOS_Codex_MCP_Store::timestamp_iso('2026-09-15 02:00:00'));
    return array('proposal_id' => $proposal_id, 'operation_id' => $proposal_id, 'kind' => 'CONTENT_RELEASE', 'state' => $state,
        'result_code' => 'SYNTHETIC', 'created_by' => 7, 'approved_by' => null === $approved ? null : 7,
        'created_at_gmt' => $created, 'expires_at_gmt' => $expires, 'approved_at_gmt' => $approved,
        'before_sha256' => $before_sha256, 'after_sha256' => $after_sha256, 'audit_id' => str_repeat('f', 64),
        'payload_json' => RAOS_Codex_MCP_Store::canonical_json($payload), 'receipt_json' => null, 'idempotency_key' => null);
}
function hydrated($row) {
    $row['payload'] = json_decode($row['payload_json'], true);
    $row['receipt'] = null;
    return $row;
}
function integrity($row) { return RAOS_Codex_MCP_Store::validate_proposal_integrity(hydrated($row)); }
function snapshot($document) {
    return array_intersect_key($document, array_flip(array('id', 'post_type', 'slug', 'title', 'excerpt', 'block_markup', 'content_sha256')));
}

$d = static fn($markup, $revision) => doc(12, 'existing', $markup, $revision);
$undo = static fn($char) => 'raos_codex_owner_direct_undo_' . str_repeat($char, 64);

// A content change while values are live (both bodies injected, by the same run or another
// run) is not a purge publish: the "after body carries no marker" guard keeps it untouched.
$db->rows = array();
$live_same = proposal('6', 'APPLIED', $d($injected, 5), $d(str_replace('98760', '98761', $injected), 6));
$live_other = proposal('7', 'APPLIED', $d($injected, 6), $d($injected_other_run, 7));
foreach (array($live_same, $live_other) as $row) { $db->rows[$row['proposal_id']] = $row; }
$GLOBALS['options'][$undo('6')] = array('applied_document' => $d(str_replace('98760', '98761', $injected), 6), 'public_before' => snapshot($d($injected, 5)));
$guard_rows = $db->rows;
$guard_options = $GLOBALS['options'];
foreach (array($live_same, $live_other) as $row) {
    demand(RAOS_Codex_MCP_Owner_Direct::redact_price_overlay_copies(hydrated($row), array()) === null, 'LIVE_CHANGE_TREATED_AS_PURGE_' . $row['proposal_id'][0]);
}
demand($db->rows === $guard_rows && $GLOBALS['options'] === $guard_options, 'LIVE_CHANGE_REDACTED');
unset($GLOBALS['options'][$undo('6')]);

$db->rows = array();
foreach (array(
    proposal('1', 'APPLIED', $d($free, 1), $d($injected, 2)),                               // publish with values
    proposal('2', 'APPLIED', $d($injected, 2), $d($free, 3)),                               // purge publish
    proposal('3', 'PENDING', $d($free, 3), $d($injected, 4)),                               // not applied
    proposal('4', 'APPLIED', $d($free, 4), $d($injected_other_run, 5)),                     // another run
    proposal('5', 'APPLIED', doc(13, 'other', $free, 1), doc(13, 'other', $injected, 2)),   // another post
) as $row) { $db->rows[$row['proposal_id']] = $row; }
$original = $db->rows;
foreach ($original as $row) { demand(integrity($row) === true, 'SYNTHETIC_ROW_INVALID_' . $row['proposal_id'][0]); }
$GLOBALS['options'][$undo('1')] = array('applied_document' => $d($injected, 2), 'public_before' => snapshot($d($free, 1)));
$GLOBALS['options'][$undo('2')] = array('applied_document' => $d($free, 3), 'public_before' => snapshot($d($injected, 2)));
$GLOBALS['options'][$undo('4')] = array('applied_document' => $d($injected_other_run, 5), 'public_before' => snapshot($d($free, 4)));
$GLOBALS['options'][$undo('5')] = array('applied_document' => doc(13, 'other', $injected, 2), 'public_before' => null);
$options_before = $GLOBALS['options'];

// Only a purge publish (injected before, marker-free after) redacts.
demand(RAOS_Codex_MCP_Owner_Direct::redact_price_overlay_copies(hydrated($db->rows[str_repeat('1', 64)])) === null, 'PUBLISH_TREATED_AS_PURGE');
$legacy = hydrated($db->rows[str_repeat('2', 64)]); unset($legacy['payload']['authorization_profile']);
demand(RAOS_Codex_MCP_Owner_Direct::redact_price_overlay_copies($legacy) === null, 'LEGACY_ROW_REDACTED');
$unapplied = hydrated($db->rows[str_repeat('2', 64)]); $unapplied['state'] = 'APPROVED';
demand(RAOS_Codex_MCP_Owner_Direct::redact_price_overlay_copies($unapplied) === null, 'UNAPPLIED_PURGE_REDACTED');
demand($db->rows === $original && $GLOBALS['options'] === $options_before, 'NON_PURGE_CHANGED_STORAGE');

$purge = hydrated($db->rows[str_repeat('2', 64)]);
$db->fail_update = true;
$failed = RAOS_Codex_MCP_Owner_Direct::redact_price_overlay_copies($purge);
demand($failed['state'] === 'INCOMPLETE' && $failed['proposals'] === 0, 'UPDATE_CONFLICT_NOT_REPORTED');
$db->fail_update = false;

$first = RAOS_Codex_MCP_Owner_Direct::redact_price_overlay_copies($purge);
demand($first === array('state' => 'INCOMPLETE', 'runs' => array($run), 'post_id' => 12, 'proposals' => 2, 'undo_options' => 2, 'skipped_active' => 1, 'theme_proposals' => 0), 'FIRST_RESULT ' . json_encode($first));
$published = json_decode($db->rows[str_repeat('1', 64)]['payload_json'], true);
$purged = json_decode($db->rows[str_repeat('2', 64)]['payload_json'], true);
demand($published['after']['block_markup'] === 'sha256:' . hash('sha256', $injected) && $published['before']['block_markup'] === $free, 'PUBLISH_PAYLOAD_NOT_REDACTED');
demand($purged['before']['block_markup'] === 'sha256:' . hash('sha256', $injected) && $purged['after']['block_markup'] === $free, 'PURGE_PAYLOAD_NOT_REDACTED');
demand($published['price_overlay_redaction'] === array('runs' => array($run), 'sides' => array('after' => array('block_markup_sha256' => hash('sha256', $injected)))), 'REDACTION_RECORD_INVALID');
foreach (array('1', '2') as $char) {
    // The redaction record keeps the run id; the price and the injected marker attribute are gone.
    demand(! str_contains($db->rows[str_repeat($char, 64)]['payload_json'], '98760')
        && ! str_contains($db->rows[str_repeat($char, 64)]['payload_json'], 'data-ps-overlay-run='), 'VALUE_LEFT_IN_ROW_' . $char);
    demand(integrity($db->rows[str_repeat($char, 64)]) === true, 'REDACTED_ROW_INTEGRITY_' . $char);
}
foreach (array('3', '4', '5') as $char) {
    demand($db->rows[str_repeat($char, 64)] === $original[str_repeat($char, 64)], 'UNRELATED_OR_ACTIVE_ROW_CHANGED_' . $char);
}
demand($GLOBALS['options'][$undo('1')]['applied_document']['block_markup'] === 'sha256:' . hash('sha256', $injected)
    && $GLOBALS['options'][$undo('1')]['applied_document']['content_sha256'] === $d($injected, 2)['content_sha256']
    && $GLOBALS['options'][$undo('1')]['public_before'] === snapshot($d($free, 1)), 'PUBLISH_UNDO_NOT_REDACTED');
demand($GLOBALS['options'][$undo('2')]['public_before']['block_markup'] === 'sha256:' . hash('sha256', $injected)
    && $GLOBALS['options'][$undo('2')]['applied_document'] === $d($free, 3), 'PURGE_UNDO_NOT_REDACTED');
demand($GLOBALS['options'][$undo('4')] === $options_before[$undo('4')] && $GLOBALS['options'][$undo('5')] === $options_before[$undo('5')], 'UNRELATED_UNDO_CHANGED');

// The integrity exception is bound to the redaction record and to terminal states.
$tampered = $db->rows[str_repeat('1', 64)];
$payload = json_decode($tampered['payload_json'], true);
$payload['price_overlay_redaction']['sides']['after']['block_markup_sha256'] = str_repeat('0', 64);
$tampered['payload_json'] = RAOS_Codex_MCP_Store::canonical_json($payload);
demand(is_wp_error(integrity($tampered)), 'TAMPERED_REDACTION_ACCEPTED');
$reopened = $db->rows[str_repeat('1', 64)]; $reopened['state'] = 'PENDING'; $reopened['approved_at_gmt'] = null; $reopened['expires_at_gmt'] = '2026-09-15 02:00:00';
demand(is_wp_error(integrity($reopened)), 'REDACTED_ACTIVE_ROW_ACCEPTED');
$unmarked = $db->rows[str_repeat('1', 64)];
$payload = json_decode($unmarked['payload_json'], true); unset($payload['price_overlay_redaction']);
$unmarked['payload_json'] = RAOS_Codex_MCP_Store::canonical_json($payload);
demand(is_wp_error(integrity($unmarked)), 'UNRECORDED_REDACTION_ACCEPTED');

// Once the pending proposal can no longer be applied, a repeated finalize completes it.
$db->rows[str_repeat('3', 64)]['state'] = 'EXPIRED';
$second = RAOS_Codex_MCP_Owner_Direct::redact_price_overlay_copies($purge);
demand($second === array('state' => 'COMPLETE', 'runs' => array($run), 'post_id' => 12, 'proposals' => 1, 'undo_options' => 0, 'skipped_active' => 0, 'theme_proposals' => 0), 'SECOND_RESULT ' . json_encode($second));
demand(integrity($db->rows[str_repeat('3', 64)]) === true && ! str_contains($db->rows[str_repeat('3', 64)]['payload_json'], '98760'), 'EXPIRED_ROW_NOT_REDACTED');
$third = RAOS_Codex_MCP_Owner_Direct::redact_price_overlay_copies($purge);
demand($third['state'] === 'COMPLETE' && $third['proposals'] === 0 && $third['undo_options'] === 0, 'REDACTION_NOT_IDEMPOTENT');
demand(str_contains($db->rows[str_repeat('4', 64)]['payload_json'], '98760') && str_contains($db->rows[str_repeat('5', 64)]['payload_json'], '98760'), 'OTHER_RUN_OR_POST_REDACTED');

// ---------------------------------------------------------------------------
// The production call site: finish_owner_direct_batch(finalize) over a purge batch redacts the
// content rows and the THEME_RELEASE rows around the injected theme tree.
// ---------------------------------------------------------------------------
define('RAOS_CODEX_MCP_RUNTIME_REVISION', RAOS_Codex_MCP_Store::RUNTIME_REVISION);
$work = sys_get_temp_dir() . '/raos-overlay-finish-' . getmypid() . '-' . bin2hex(random_bytes(6));
$theme_dir = $work . '/themes/kurashinoshirube-child';
demand(mkdir($work . '/private', 0700, true) && mkdir($theme_dir . '/assets', 0700, true) && chmod($work . '/private', 0700), 'WORK_DIRECTORY');
define('RAOS_CODEX_PRIVATE_DIR', $work . '/private');
$GLOBALS['theme_root'] = $work . '/themes';
file_put_contents($theme_dir . '/functions.php', "<?php\n// synthetic price-free theme\n");
file_put_contents($theme_dir . '/assets/purchase-support.v1.json', "{\"articles\":[]}\n");
$remove = static function ($path) use (&$remove) {
    if (is_dir($path) && ! is_link($path)) {
        foreach (array_diff(scandir($path), array('.', '..')) as $name) { $remove($path . '/' . $name); }
        rmdir($path);
    } elseif (file_exists($path) || is_link($path)) {
        unlink($path);
    }
};
register_shutdown_function(static function () use ($remove, $work) { $remove($work); });
$price_free_tree = RAOS_Codex_MCP_Deployment::tree_hash($theme_dir);
demand(RAOS_Codex_MCP_Store::is_sha256($price_free_tree), 'THEME_TREE_UNAVAILABLE');
$injected_tree = str_repeat('9', 64);
$older_tree = str_repeat('8', 64);
$marker = RAOS_Codex_MCP_Store::PRICE_OVERLAY_REDACTED;
function manifest_of($runtime, $functions) {
    return array(
        array('path' => 'assets/purchase-support.v1.json', 'size' => 16, 'sha256' => str_repeat($runtime, 64)),
        array('path' => 'assets/theme.css', 'size' => 16, 'sha256' => str_repeat('3', 64)),
        array('path' => 'functions.php', 'size' => 16, 'sha256' => str_repeat($functions, 64)),
    );
}
function theme_proposal($char, $state, $before_tree, $after_tree, $manifest) {
    $created = '2026-09-15 01:00:00';
    $approved = in_array($state, array('APPLIED', 'FAILED'), true) ? '2026-09-15 01:10:00' : null;
    $expires = null === $approved ? '2026-09-15 02:00:00' : '2026-09-15 01:25:00';
    $proposal_id = str_repeat($char, 64);
    $payload = array('schema' => 'CodeReleaseProposalV1', 'kind' => 'THEME_RELEASE',
        'code_package' => array('schema' => 'CodePackageV1', 'kind' => 'theme', 'source' => 'tracked_child_theme',
            'slug' => 'kurashinoshirube-child', 'file_manifest_sha256' => $after_tree, 'file_manifest' => $manifest),
        'before_tree_sha256' => $before_tree, 'after_tree_sha256' => $after_tree, 'target_active' => true,
        'authorization_profile' => $GLOBALS['direct']->binding(null),
        'proposal_id' => $proposal_id, 'created_by' => 7,
        'created_at_gmt' => RAOS_Codex_MCP_Store::timestamp_iso($created),
        'expires_at_gmt' => RAOS_Codex_MCP_Store::timestamp_iso('2026-09-15 02:00:00'));
    return array('proposal_id' => $proposal_id, 'operation_id' => $proposal_id, 'kind' => 'THEME_RELEASE', 'state' => $state,
        'result_code' => 'SYNTHETIC', 'created_by' => 7, 'approved_by' => null === $approved ? null : 7,
        'created_at_gmt' => $created, 'expires_at_gmt' => $expires, 'approved_at_gmt' => $approved,
        'before_sha256' => $before_tree, 'after_sha256' => $after_tree, 'audit_id' => str_repeat('f', 64),
        'payload_json' => RAOS_Codex_MCP_Store::canonical_json($payload), 'receipt_json' => '{}', 'idempotency_key' => null);
}
$GLOBALS['options'] = array(RAOS_Codex_MCP_Owner_Direct::PROFILE_OPTION => $GLOBALS['options'][RAOS_Codex_MCP_Owner_Direct::PROFILE_OPTION]);
$GLOBALS['posts'][12] = new WP_Post(12, 'post', 'publish', 'existing', 'existing', '', $free, '2026-09-15 00:00:03', '2026-09-15 09:00:03');
$db->rows = array();
$publish_row = proposal('1', 'APPLIED', $d($free, 1), $d($injected, 2));
$purge_row = proposal('2', 'APPLIED', $d($injected, 2), $d($free, 3));
$purge_row['receipt_json'] = '{}';
$publish_theme = theme_proposal('a', 'APPLIED', $older_tree, $injected_tree, manifest_of('5', '4'));
$purge_theme = theme_proposal('b', 'APPLIED', $injected_tree, $price_free_tree, manifest_of('c', 'e'));
$unrelated_theme = theme_proposal('d', 'APPLIED', str_repeat('7', 64), str_repeat('6', 64), manifest_of('5', '4'));
foreach (array($publish_row, $purge_row, $publish_theme, $purge_theme, $unrelated_theme) as $row) { $db->rows[$row['proposal_id']] = $row; }
foreach ($db->rows as $row) { demand(integrity($row) === true, 'FINISH_ROW_INVALID_' . $row['proposal_id'][0]); }
$live = RAOS_Codex_MCP_Content::document(12);
demand(! is_wp_error($live) && $live['content_sha256'] === $purge_row['after_sha256'], 'LIVE_DOCUMENT_MISMATCH');
$GLOBALS['options'][$undo('1')] = array('applied_document' => $d($injected, 2), 'public_before' => snapshot($d($free, 1)));
$GLOBALS['options'][$undo('2')] = array('applied_document' => $live, 'public_before' => snapshot($d($injected, 2)));
$token = str_repeat('f', 64);
$batch_manifest = array('schema' => 'RAOSWordPressPublicationBatchManifestV1', 'expected_theme_tree_sha256' => $price_free_tree,
    'proposal_count' => 2, 'proposals' => array_map(static fn($row) => array('proposal_id' => $row['proposal_id'], 'kind' => $row['kind'],
        'before_sha256' => $row['before_sha256'], 'after_sha256' => $row['after_sha256']), array($purge_row, $purge_theme)));
$db->batches[$token] = array('batch_token' => $token, 'state' => 'APPROVED', 'created_by' => 7,
    'created_at_gmt' => '2026-09-15 01:00:00', 'expires_at_gmt' => '2026-09-15 02:00:00', 'applying_at_gmt' => null,
    'batch_manifest_sha256' => RAOS_Codex_MCP_Store::hash($batch_manifest),
    'proposal_ids_json' => json_encode(array($purge_row['proposal_id'], $purge_theme['proposal_id'])),
    'manifest_json' => json_encode($batch_manifest));
$purge_before_finish = hydrated($purge_row);
$purge_theme_before_finish = hydrated($purge_theme);

// A THEME_RELEASE row that cannot be rewritten: nothing counted for it, the injected tree hash
// stays in both theme payloads, and the finish never reports the redaction COMPLETE.
$rows_before_finish = $db->rows;
$batches_before_finish = $db->batches;
$options_before_finish = $GLOBALS['options'];
$private_before_finish = scandir($work . '/private');
$db->fail_update_kinds = array('THEME_RELEASE');
$blocked = RAOS_Codex_MCP_Deployment::finish_owner_direct_batch($token, $db->batches[$token]['batch_manifest_sha256'], 'finalize');
demand(! is_wp_error($blocked) && 'FINALIZED' === $blocked['state'], 'THEME_UPDATE_FAILURE_FINISH ' . json_encode($blocked));
demand(($blocked['price_overlay_redaction'] ?? null) === array(array('state' => 'INCOMPLETE', 'runs' => array($run), 'post_id' => 12,
    'proposals' => 2, 'undo_options' => 2, 'skipped_active' => 0, 'theme_proposals' => 0)), 'THEME_UPDATE_FAILURE_REPORTED ' . json_encode($blocked));
demand(get_option('raos_codex_owner_direct_finish_' . $token, null) === $blocked, 'THEME_UPDATE_FAILURE_NOT_RECORDED');
demand($db->rows[str_repeat('a', 64)] === $publish_theme && $db->rows[str_repeat('b', 64)] === $purge_theme, 'THEME_ROWS_CHANGED_ON_UPDATE_FAILURE');
$db->fail_update_kinds = array();
$db->rows = $rows_before_finish;
$db->batches = $batches_before_finish;
$GLOBALS['options'] = $options_before_finish;
foreach (array_diff(scandir($work . '/private'), $private_before_finish) as $name) { $remove($work . '/private/' . $name); }

$finish = RAOS_Codex_MCP_Deployment::finish_owner_direct_batch($token, $db->batches[$token]['batch_manifest_sha256'], 'finalize');
demand(! is_wp_error($finish), 'FINISH_REFUSED ' . (is_wp_error($finish) ? $finish->code : ''));
demand('FINALIZED' === $finish['state'] && array_column($finish['members'], 'state') === array('FINALIZED', 'FINALIZED'), 'FINISH_NOT_FINALIZED ' . json_encode($finish));
demand(($finish['price_overlay_redaction'] ?? null) === array(array('state' => 'COMPLETE', 'runs' => array($run), 'post_id' => 12,
    'proposals' => 2, 'undo_options' => 2, 'skipped_active' => 0, 'theme_proposals' => 2)), 'FINISH_DID_NOT_REDACT ' . json_encode($finish));
demand(get_option('raos_codex_owner_direct_finish_' . $token, null) === $finish, 'FINISH_RESULT_NOT_RECORDED');
$stored = static fn($char) => json_decode($db->rows[str_repeat($char, 64)]['payload_json'], true);
demand($stored('1')['after']['block_markup'] === 'sha256:' . hash('sha256', $injected)
    && $stored('2')['before']['block_markup'] === 'sha256:' . hash('sha256', $injected), 'FINISH_CONTENT_NOT_REDACTED');
$published_theme = $stored('a');
demand($published_theme['after_tree_sha256'] === $marker && $published_theme['before_tree_sha256'] === $older_tree
    && $published_theme['code_package']['file_manifest_sha256'] === $marker
    && array_column($published_theme['code_package']['file_manifest'], 'sha256', 'path') === array(
        'assets/purchase-support.v1.json' => $marker, 'assets/theme.css' => str_repeat('3', 64), 'functions.php' => $marker)
    && $published_theme['price_overlay_redaction'] === array('manifest_paths' => array('assets/purchase-support.v1.json', 'functions.php'),
        'runs' => array($run), 'tree_sides' => array('after')), 'PUBLISH_THEME_NOT_REDACTED ' . json_encode($published_theme));
$purged_theme = $stored('b');
demand($purged_theme['before_tree_sha256'] === $marker && $purged_theme['after_tree_sha256'] === $price_free_tree
    && $purged_theme['code_package']['file_manifest_sha256'] === $price_free_tree
    && array_column($purged_theme['code_package']['file_manifest'], 'sha256', 'path') === array_column(manifest_of('c', 'e'), 'sha256', 'path')
    && $purged_theme['price_overlay_redaction'] === array('manifest_paths' => array(), 'runs' => array($run), 'tree_sides' => array('before')),
    'PURGE_THEME_NOT_REDACTED ' . json_encode($purged_theme));
demand($db->rows[str_repeat('d', 64)] === $unrelated_theme, 'UNRELATED_THEME_CHANGED');
foreach (array('1', '2', 'a', 'b', 'd') as $char) {
    $row = $db->rows[str_repeat($char, 64)];
    demand(integrity($row) === true, 'FINISHED_ROW_INTEGRITY_' . $char);
    foreach (array('98760', 'data-ps-overlay-run=', $injected_tree, str_repeat('5', 64), str_repeat('4', 64)) as $needle) {
        demand('d' === $char || ! str_contains($row['payload_json'], $needle), 'VALUE_LEFT_IN_FINISHED_ROW_' . $char);
    }
}
// The row columns keep the tree hashes (a documented residual, contract §10.1-3).
demand($db->rows[str_repeat('a', 64)]['after_sha256'] === $injected_tree && $db->rows[str_repeat('b', 64)]['before_sha256'] === $injected_tree, 'THEME_COLUMNS_CHANGED');

// An active theme row around the injected tree is never rewritten and keeps the result INCOMPLETE.
$pending_theme = theme_proposal('0', 'PENDING', $older_tree, $injected_tree, manifest_of('5', '4'));
$db->rows[$pending_theme['proposal_id']] = $pending_theme;
$again = RAOS_Codex_MCP_Owner_Direct::redact_price_overlay_copies($purge_before_finish, array($purge_theme_before_finish));
demand($again === array('state' => 'INCOMPLETE', 'runs' => array($run), 'post_id' => 12, 'proposals' => 0, 'undo_options' => 0,
    'skipped_active' => 1, 'theme_proposals' => 0), 'ACTIVE_THEME_RESULT ' . json_encode($again));
demand($db->rows[$pending_theme['proposal_id']] === $pending_theme, 'ACTIVE_THEME_ROW_REWRITTEN');
$db->rows[$pending_theme['proposal_id']]['state'] = 'EXPIRED';
$expired = RAOS_Codex_MCP_Owner_Direct::redact_price_overlay_copies($purge_before_finish, array($purge_theme_before_finish));
demand($expired === array('state' => 'COMPLETE', 'runs' => array($run), 'post_id' => 12, 'proposals' => 0, 'undo_options' => 0,
    'skipped_active' => 0, 'theme_proposals' => 1), 'EXPIRED_THEME_RESULT ' . json_encode($expired));
demand(integrity($db->rows[$pending_theme['proposal_id']]) === true && $stored('0')['after_tree_sha256'] === $marker, 'EXPIRED_THEME_NOT_REDACTED');
$repeated = RAOS_Codex_MCP_Owner_Direct::redact_price_overlay_copies($purge_before_finish, array($purge_theme_before_finish));
demand('COMPLETE' === $repeated['state'] && 0 === $repeated['theme_proposals'], 'THEME_REDACTION_NOT_IDEMPOTENT');

// A batch theme member created by another user is no clue to the rows around its tree.
$clue_row = theme_proposal('c', 'EXPIRED', $older_tree, $injected_tree, manifest_of('5', '4'));
$db->rows[$clue_row['proposal_id']] = $clue_row;
$foreign_member = $purge_theme_before_finish;
$foreign_member['created_by'] = 8;
$foreign = RAOS_Codex_MCP_Owner_Direct::redact_price_overlay_copies($purge_before_finish, array($foreign_member));
demand($foreign === array('state' => 'COMPLETE', 'runs' => array($run), 'post_id' => 12, 'proposals' => 0, 'undo_options' => 0,
    'skipped_active' => 0, 'theme_proposals' => 0), 'FOREIGN_MEMBER_RESULT ' . json_encode($foreign));
demand($db->rows[$clue_row['proposal_id']] === $clue_row, 'FOREIGN_MEMBER_USED_AS_CLUE');
unset($db->rows[$clue_row['proposal_id']]);

// The integrity exception for theme rows is bound to the record and to terminal states.
$tamper = static function ($row, $change) {
    $payload = json_decode($row['payload_json'], true);
    $change($payload);
    $row['payload_json'] = RAOS_Codex_MCP_Store::canonical_json($payload);
    return $row;
};
$redacted_theme = $db->rows[str_repeat('a', 64)];
foreach (array(
    'UNRECORDED_TREE_SIDE' => static function (array &$payload) { $payload['price_overlay_redaction']['tree_sides'] = array('before'); },
    'UNLISTED_MANIFEST_MARKER' => static function (array &$payload) { $payload['code_package']['file_manifest'][1]['sha256'] = RAOS_Codex_MCP_Store::PRICE_OVERLAY_REDACTED; },
    'UNLISTED_MANIFEST_PATH' => static function (array &$payload) { $payload['price_overlay_redaction']['manifest_paths'][] = 'assets/theme.css'; },
    'UNRECORDED_REDACTION' => static function (array &$payload) { unset($payload['price_overlay_redaction']); },
    'CONTENT_RECORD_SHAPE' => static function (array &$payload) { $payload['price_overlay_redaction'] = array('runs' => array('ks020-synthetic-0001'), 'sides' => array()); },
    'TREE_SIDE_WITHOUT_MARKER' => static function (array &$payload) { $payload['price_overlay_redaction']['tree_sides'] = array('after', 'before'); },
    'EMPTY_RUNS' => static function (array &$payload) { $payload['price_overlay_redaction']['runs'] = array(); },
    'INVALID_RUN_ID' => static function (array &$payload) { $payload['price_overlay_redaction']['runs'] = array('Invalid Run'); },
    'EXTRA_RECORD_KEY' => static function (array &$payload) { $payload['price_overlay_redaction']['extra'] = array(); },
) as $case => $change) {
    demand(is_wp_error(integrity($tamper($redacted_theme, $change))), 'TAMPERED_THEME_REDACTION_ACCEPTED_' . $case);
}
// The purge batch's row redacted only its before tree: a manifest marker there is drift.
$redacted_purge_theme = $db->rows[str_repeat('b', 64)];
foreach (array(
    'BEFORE_SIDE_MANIFEST_HASH_MARKER' => static function (array &$payload) { $payload['code_package']['file_manifest_sha256'] = RAOS_Codex_MCP_Store::PRICE_OVERLAY_REDACTED; },
    'BEFORE_SIDE_MANIFEST_ENTRY_MARKER' => static function (array &$payload) {
        $payload['code_package']['file_manifest'][2]['sha256'] = RAOS_Codex_MCP_Store::PRICE_OVERLAY_REDACTED;
        $payload['price_overlay_redaction']['manifest_paths'] = array('functions.php');
    },
) as $case => $change) {
    demand(is_wp_error(integrity($tamper($redacted_purge_theme, $change))), 'TAMPERED_THEME_REDACTION_ACCEPTED_' . $case);
}
// A theme-shaped record is accepted on a THEME_RELEASE row only.
$theme_record = array('manifest_paths' => array(), 'runs' => array($run), 'tree_sides' => array('after'));
demand(is_wp_error(integrity($tamper($db->rows[str_repeat('1', 64)], static function (array &$payload) use ($theme_record) {
    $payload['price_overlay_redaction'] = $theme_record;
}))), 'THEME_RECORD_ON_CONTENT_ROW_ACCEPTED');
$plugin_row = $tamper($redacted_theme, static function (array &$payload) { $payload['kind'] = 'PLUGIN_CHANGE'; });
$plugin_row['kind'] = 'PLUGIN_CHANGE';
demand(is_wp_error(integrity($plugin_row)), 'THEME_RECORD_ON_PLUGIN_ROW_ACCEPTED');
$reopened = $redacted_theme; $reopened['state'] = 'PENDING'; $reopened['approved_at_gmt'] = null; $reopened['expires_at_gmt'] = '2026-09-15 02:00:00';
demand(is_wp_error(integrity($reopened)), 'REDACTED_ACTIVE_THEME_ROW_ACCEPTED');
echo "OWNER_DIRECT_PRICE_OVERLAY_REDACTION_OK\n";
