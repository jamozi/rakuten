<?php
/** KS-020 purge publish: stored price-overlay bodies become hashes. No WordPress bootstrap or network. */
declare(strict_types=1);
define('ABSPATH', __DIR__ . '/');
define('ARRAY_A', 'ARRAY_A');
define('WP_CONTENT_DIR', __DIR__);
define('RAOS_OPERATOR_WRITES_ENABLED', true);
class WP_Error {
    public function __construct(public string $code, $message = '', $data = array()) {}
    public function get_error_code() { return $this->code; }
}
function is_wp_error($value) { return $value instanceof WP_Error; }
function wp_json_encode($value, $flags = 0) { return json_encode($value, $flags); }
function get_option($key, $default = false) { return $GLOBALS['options'][$key] ?? $default; }
function update_option($key, $value, $autoload = null) { $GLOBALS['options'][$key] = $value; return true; }
function get_current_user_id() { return 7; }
class RAOS_Codex_MCP_Abilities {
    public static function runtime_identity_gate() { return true; }
    public static function plugin_runtime_revision() { return RAOS_Codex_MCP_Store::RUNTIME_REVISION; }
}
final class OverlayRedactionDB {
    public $prefix = 'synthetic_';
    public $last_error = '';
    public $rows = array();
    public $fail_update = false;
    public function esc_like($text) { return addcslashes($text, '_%\\'); }
    public function prepare($sql, ...$values) { return array($sql, $values); }
    public function get_results($prepared, $output = null) {
        [$sql, $values] = $prepared;
        if ("SELECT proposal_id, state, payload_json FROM synthetic_raos_codex_operations_v1 WHERE kind = 'CONTENT_RELEASE' AND created_by = %d AND payload_json LIKE %s" !== $sql
            || '%data-ps-overlay-run=%' !== $values[1]) { throw new RuntimeException('UNEXPECTED_SELECT'); }
        $found = array();
        foreach ($this->rows as $row) {
            if ('CONTENT_RELEASE' === $row['kind'] && (int) $row['created_by'] === $values[0] && str_contains($row['payload_json'], 'data-ps-overlay-run=')) {
                $found[] = array('proposal_id' => $row['proposal_id'], 'state' => $row['state'], 'payload_json' => $row['payload_json']);
            }
        }
        return $found;
    }
    public function query($prepared) {
        [$sql, $values] = $prepared;
        if ('UPDATE synthetic_raos_codex_operations_v1 SET payload_json = %s WHERE proposal_id = %s AND state = %s AND payload_json = %s' !== $sql) { throw new RuntimeException('UNEXPECTED_UPDATE'); }
        [$json, $id, $state, $old] = $values;
        if ($this->fail_update || ! isset($this->rows[$id]) || $this->rows[$id]['state'] !== $state || $this->rows[$id]['payload_json'] !== $old) { return 0; }
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
$undo = static fn($char) => 'raos_codex_owner_direct_undo_' . str_repeat($char, 64);
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
demand($first === array('state' => 'INCOMPLETE', 'runs' => array($run), 'post_id' => 12, 'proposals' => 2, 'undo_options' => 2, 'skipped_active' => 1), 'FIRST_RESULT ' . json_encode($first));
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
demand($second === array('state' => 'COMPLETE', 'runs' => array($run), 'post_id' => 12, 'proposals' => 1, 'undo_options' => 0, 'skipped_active' => 0), 'SECOND_RESULT ' . json_encode($second));
demand(integrity($db->rows[str_repeat('3', 64)]) === true && ! str_contains($db->rows[str_repeat('3', 64)]['payload_json'], '98760'), 'EXPIRED_ROW_NOT_REDACTED');
$third = RAOS_Codex_MCP_Owner_Direct::redact_price_overlay_copies($purge);
demand($third['state'] === 'COMPLETE' && $third['proposals'] === 0 && $third['undo_options'] === 0, 'REDACTION_NOT_IDEMPOTENT');
demand(str_contains($db->rows[str_repeat('4', 64)]['payload_json'], '98760') && str_contains($db->rows[str_repeat('5', 64)]['payload_json'], '98760'), 'OTHER_RUN_OR_POST_REDACTED');
echo "OWNER_DIRECT_PRICE_OVERLAY_REDACTION_OK\n";
