<?php
/** Executable fake-wpdb harness for the private reconciliation primitives. */

declare(strict_types=1);

define('ABSPATH', __DIR__ . '/');
define('ARRAY_A', 'ARRAY_A');
date_default_timezone_set('UTC');

final class WP_Error
{
    public string $code;
    private string $message;
    private $data;

    public function __construct($code, $message = '', $data = array())
    {
        $this->code = (string) $code;
        $this->message = (string) $message;
        $this->data = $data;
    }

    public function get_error_code(): string
    {
        return $this->code;
    }

    public function get_error_message(): string
    {
        throw new RuntimeException('error message accessor must not be used');
    }

    public function get_error_data()
    {
        throw new RuntimeException('error data accessor must not be used');
    }
}

final class WP_User
{
    public int $ID = 0;
}

final class WP_Post
{
}

final class WP_Hook
{
    public array $callbacks = array();
}

final class RAOS_Bounded_Operator
{
}

final class RAOS_ST1704_Publication_Bindings_V2
{
    const CATEGORY_NAME = '暮らしの道具';
    const CATEGORY_CONTRACT = 'KURASHINO_DOGU_SINGLE_V1';

    public static function articles(): array
    {
        return array(
            'st1704-anker-solix-c300-c800-c1000-differences' =>
                'anker-solix-c300-c800-c1000-differences',
            'st1704-compact-robot-vacuum-shortlist' =>
                'compact-robot-vacuum-shortlist',
            'st1704-countertop-dishwasher-for-small-households' =>
                'countertop-dishwasher-for-small-households',
            'st1704-portable-power-station-guide' =>
                'portable-power-station-guide',
        );
    }

    public static function revision_post_ids(): array
    {
        return array(
            'st1704-anker-solix-c300-c800-c1000-differences' => 29,
            'st1704-compact-robot-vacuum-shortlist' => 30,
            'st1704-countertop-dishwasher-for-small-households' => 41,
            'st1704-portable-power-station-guide' => 28,
        );
    }
}

function is_wp_error($value): bool
{
    return $value instanceof WP_Error;
}

$GLOBALS['raos_test_logged_in'] = false;
$GLOBALS['raos_test_capabilities'] = array();
$GLOBALS['raos_test_session_token'] = '';

function is_user_logged_in(): bool
{
    return $GLOBALS['raos_test_logged_in'] === true;
}

function current_user_can($capability, ...$arguments): bool
{
    unset($arguments);
    return isset($GLOBALS['raos_test_capabilities'][(string) $capability])
        && $GLOBALS['raos_test_capabilities'][(string) $capability] === true;
}

function wp_get_session_token(): string
{
    return (string) $GLOBALS['raos_test_session_token'];
}

function wp_json_encode($value, $flags = 0)
{
    return json_encode($value, (int) $flags);
}

function maybe_unserialize($value)
{
    if (! is_string($value)) {
        return $value;
    }
    $decoded = @unserialize($value);
    return $decoded === false && $value !== 'b:0;' ? $value : $decoded;
}

final class FakePrepared
{
    public string $query;
    public array $arguments;

    public function __construct(string $query, array $arguments)
    {
        $this->query = $query;
        $this->arguments = $arguments;
    }
}

final class FakeWpdb
{
    public string $prefix = 'wp_';
    public string $postmeta = 'wp_postmeta';
    public string $posts = 'wp_posts';
    public string $terms = 'wp_terms';
    public string $term_taxonomy = 'wp_term_taxonomy';
    public string $term_relationships = 'wp_term_relationships';
    public string $last_error = '';
    public array $meta_rows = array();
    public array $audit_rows = array();
    public ?array $transaction_snapshot = null;
    public int $delete_calls = 0;
    public ?int $fail_delete_at = null;
    public bool $fail_audit_insert = false;
    public bool $fail_commit = false;
    public bool $commit_response_loss = false;

    public function prepare($query, ...$arguments): FakePrepared
    {
        return new FakePrepared((string) $query, $arguments);
    }

    public function get_results($statement, $format): array
    {
        unset($format);
        $this->last_error = '';
        if ($statement instanceof FakePrepared
            && strpos($statement->query, 'SELECT meta_id, meta_key, meta_value')
                !== false) {
            $post_id = (int) $statement->arguments[0];
            $rows = array_values(array_filter(
                $this->meta_rows,
                static function (array $row) use ($post_id): bool {
                    return (int) $row['post_id'] === $post_id;
                }
            ));
            usort(
                $rows,
                static function (array $left, array $right): int {
                    return (int) $left['meta_id'] <=> (int) $right['meta_id'];
                }
            );
            return array_map(
                static function (array $row): array {
                    return array(
                        'meta_id' => (string) $row['meta_id'],
                        'meta_key' => (string) $row['meta_key'],
                        'meta_value' => (string) $row['meta_value'],
                    );
                },
                $rows
            );
        }
        if (is_string($statement)
            && strpos($statement, 'publication_audit_v2') !== false) {
            return $this->audit_rows;
        }
        throw new RuntimeException('unexpected get_results query');
    }

    public function get_var($statement)
    {
        $query = $statement instanceof FakePrepared
            ? $statement->query
            : (string) $statement;
        $this->last_error = '';
        if (strpos($query, 'SELECT event_hash') !== false) {
            if ($this->audit_rows === array()) {
                return null;
            }
            return $this->audit_rows[count($this->audit_rows) - 1]['event_hash'];
        }
        if (strpos($query, 'SELECT COUNT(*)') !== false) {
            return (string) count($this->audit_rows);
        }
        throw new RuntimeException('unexpected get_var query');
    }

    public function query($statement)
    {
        if ($statement instanceof FakePrepared
            && strpos($statement->query, 'DELETE FROM') !== false) {
            ++$this->delete_calls;
            if ($this->fail_delete_at === $this->delete_calls) {
                return 0;
            }
            [$meta_id, $post_id, $meta_key, $meta_value] =
                $statement->arguments;
            $matches = array();
            foreach ($this->meta_rows as $index => $row) {
                if ((int) $row['meta_id'] === (int) $meta_id
                    && (int) $row['post_id'] === (int) $post_id
                    && $row['meta_key'] === $meta_key
                    && $row['meta_value'] === $meta_value) {
                    $matches[] = $index;
                }
            }
            if (count($matches) !== 1) {
                return 0;
            }
            unset($this->meta_rows[$matches[0]]);
            $this->meta_rows = array_values($this->meta_rows);
            return 1;
        }
        $query = (string) $statement;
        if ($query === 'START TRANSACTION') {
            if ($this->transaction_snapshot !== null) {
                return false;
            }
            $this->transaction_snapshot = array(
                'audit_rows' => $this->audit_rows,
                'meta_rows' => $this->meta_rows,
            );
            $this->delete_calls = 0;
            return true;
        }
        if ($query === 'ROLLBACK') {
            if ($this->transaction_snapshot !== null) {
                $this->audit_rows = $this->transaction_snapshot['audit_rows'];
                $this->meta_rows = $this->transaction_snapshot['meta_rows'];
                $this->transaction_snapshot = null;
            }
            return true;
        }
        if ($query === 'COMMIT') {
            if ($this->transaction_snapshot === null) {
                return false;
            }
            if ($this->fail_commit) {
                return false;
            }
            $this->transaction_snapshot = null;
            return $this->commit_response_loss ? false : true;
        }
        throw new RuntimeException('unexpected query');
    }

    public function insert($table, $data, $formats)
    {
        unset($formats);
        if ($table !== $this->prefix . 'raos_st1704_publication_audit_v2'
            || $this->fail_audit_insert) {
            return false;
        }
        $this->audit_rows[] = array(
            'audit_id' => (string) (count($this->audit_rows) + 1),
            'occurred_at' => (string) $data['occurred_at'],
            'actor_user_id' => (string) $data['actor_user_id'],
            'event_code' => (string) $data['event_code'],
            'proposal_id' => (string) $data['proposal_id'],
            'detail_code' => (string) $data['detail_code'],
            'previous_hash' => (string) $data['previous_hash'],
            'event_hash' => (string) $data['event_hash'],
        );
        return 1;
    }
}

function expect_true($condition, string $message): void
{
    if ($condition !== true) {
        throw new RuntimeException($message);
    }
}

function encoded_pair(string $key, string $value): array
{
    return array(
        'key_base64' => base64_encode($key),
        'value_base64' => base64_encode($value),
    );
}

function meta_row(int $id, string $key, string $value): array
{
    return array(
        'meta_id' => $id,
        'post_id' => 28,
        'meta_key' => $key,
        'meta_value' => $value,
    );
}

function append_fixture_audit(
    FakeWpdb $database,
    string $occurred_at,
    int $actor,
    string $event,
    string $proposal_id,
    string $detail
): array {
    $previous = $database->audit_rows === array()
        ? str_repeat('0', 64)
        : $database->audit_rows[count($database->audit_rows) - 1]['event_hash'];
    $material = implode("\n", array(
        $previous,
        $occurred_at,
        (string) $actor,
        $event,
        $proposal_id,
        $detail,
    ));
    $row = array(
        'audit_id' => (string) (count($database->audit_rows) + 1),
        'occurred_at' => $occurred_at,
        'actor_user_id' => (string) $actor,
        'event_code' => $event,
        'proposal_id' => $proposal_id,
        'detail_code' => $detail,
        'previous_hash' => $previous,
        'event_hash' => hash('sha256', $material),
    );
    $database->audit_rows[] = $row;
    return $row;
}

require_once dirname(__DIR__, 3)
    . '/changes/st-1704/publication-operator-v2/wordpress-plugin/'
    . 'raos-bounded-operator/includes/st1704-publication-controller.v2.php';

$reflection = new ReflectionClass('RAOS_ST1704_Publication_Controller_V2');
$controller = $reflection->newInstanceWithoutConstructor();
$meta_plan_method = $reflection->getMethod('reconciliation_meta_cleanup_plan');
$meta_plan_method->setAccessible(true);
$cas_method = $reflection->getMethod('delete_exact_reconciliation_meta_rows');
$cas_method->setAccessible(true);
$audit_method = $reflection->getMethod('validate_reconciliation_audit_chain');
$audit_method->setAccessible(true);
$append_method = $reflection->getMethod('append_audit');
$append_method->setAccessible(true);
$result_error_method = $reflection->getMethod(
    'terminal_reconciliation_candidate_result_error'
);
$result_error_method->setAccessible(true);
$submission_diagnostic_method = $reflection->getMethod(
    'reconciliation_submission_diagnostic_code'
);
$submission_diagnostic_method->setAccessible(true);
$cleanup_refusal_message_method = $reflection->getMethod(
    'reconciliation_cleanup_refusal_message'
);
$cleanup_refusal_message_method->setAccessible(true);

$generic_refusal = 'The exact redirect metadata reconciliation was refused.';
$sensitive_error = new WP_Error(
    'raos_st1704_reconciliation_reauth_failed',
    'PASSWORD_MUST_NOT_LEAK',
    array('credential' => 'TOKEN_MUST_NOT_LEAK')
);
$GLOBALS['raos_test_capabilities'] = array(
    'manage_options' => true,
    'publish_posts' => true,
);
$GLOBALS['raos_test_session_token'] = 'cookie-session';
expect_true(
    $submission_diagnostic_method->invoke(null, $sensitive_error) === '',
    'logged-out requests must not receive a diagnostic'
);
expect_true(
    $cleanup_refusal_message_method->invoke(null, $sensitive_error)
        === $generic_refusal,
    'logged-out refusal must remain generic'
);

$GLOBALS['raos_test_logged_in'] = true;
$GLOBALS['raos_test_capabilities']['manage_options'] = false;
expect_true(
    $cleanup_refusal_message_method->invoke(null, $sensitive_error)
        === $generic_refusal,
    'non-administrators must receive the generic refusal'
);
$GLOBALS['raos_test_capabilities']['manage_options'] = true;
$GLOBALS['raos_test_capabilities']['publish_posts'] = false;
expect_true(
    $cleanup_refusal_message_method->invoke(null, $sensitive_error)
        === $generic_refusal,
    'users without publication capability must receive the generic refusal'
);
$GLOBALS['raos_test_capabilities']['publish_posts'] = true;
$GLOBALS['raos_test_session_token'] = '';
expect_true(
    $cleanup_refusal_message_method->invoke(null, $sensitive_error)
        === $generic_refusal,
    'non-cookie authentication must receive the generic refusal'
);

$GLOBALS['raos_test_session_token'] = 'cookie-session';
expect_true(
    $submission_diagnostic_method->invoke(null, $sensitive_error)
        === 'raos_st1704_reconciliation_reauth_failed',
    'authorized administrators must receive the allowlisted auth class'
);
$authorized_auth_message = $cleanup_refusal_message_method->invoke(
    null,
    $sensitive_error
);
expect_true(
    $authorized_auth_message === $generic_refusal
        . ' Administrator diagnostic code: '
        . 'raos_st1704_reconciliation_reauth_failed',
    'authorized auth refusal must contain only the fixed diagnostic'
);
expect_true(
    strpos($authorized_auth_message, 'PASSWORD_MUST_NOT_LEAK') === false
        && strpos($authorized_auth_message, 'TOKEN_MUST_NOT_LEAK') === false,
    'error message and data must not leak'
);
$unknown_error = new WP_Error(
    'SECRET_DERIVED_ERROR_CODE',
    'SECRET_ERROR_MESSAGE',
    array('secret' => 'SECRET_ERROR_DATA')
);
expect_true(
    $submission_diagnostic_method->invoke(null, $unknown_error)
        === 'raos_st1704_reconciliation_authentication_refused',
    'unknown errors must collapse to one fixed authentication diagnostic'
);
$unknown_message = $cleanup_refusal_message_method->invoke(
    null,
    $unknown_error
);
expect_true(
    strpos($unknown_message, 'SECRET_DERIVED_ERROR_CODE') === false
        && strpos($unknown_message, 'SECRET_ERROR_MESSAGE') === false
        && strpos($unknown_message, 'SECRET_ERROR_DATA') === false,
    'unknown error fields must not reach the response'
);
expect_true(
    $submission_diagnostic_method->invoke(null, false)
        === 'raos_st1704_reconciliation_execution_refused',
    'boolean execution refusal must map to one fixed diagnostic'
);
expect_true(
    $cleanup_refusal_message_method->invoke(null, false) === $generic_refusal
        . ' Administrator diagnostic code: '
        . 'raos_st1704_reconciliation_execution_refused',
    'authorized execution refusal must expose only its fixed class'
);

expect_true(
    $result_error_method->invoke(
        null,
        array('result_code' => 'POST_COMMIT_HOOK_REPLAY_UNCERTAIN')
    ) === null,
    'pinned uncertain result must remain eligible'
);
$replay_exception = $result_error_method->invoke(
    null,
    array('result_code' => 'POST_COMMIT_HOOK_REPLAY_EXCEPTION')
);
expect_true(
    $replay_exception === null,
    'fixed replay exception must be eligible for exact-state reconciliation'
);
$other_result = $result_error_method->invoke(
    null,
    array('result_code' => 'POST_WRITE_DRIFT_DETECTED')
);
expect_true(
    $other_result instanceof WP_Error
        && $other_result->get_error_code()
            === 'raos_st1704_reconciliation_candidate_failure_code_mismatch',
    'other bounded result must not be rendered or become eligible'
);
foreach (
    array(
        array(),
        array('result_code' => null),
        array('result_code' => 'lowercase'),
        array('result_code' => str_repeat('A', 65)),
    ) as $invalid_candidate
) {
    $invalid_result = $result_error_method->invoke(null, $invalid_candidate);
    expect_true(
        $invalid_result instanceof WP_Error
            && $invalid_result->get_error_code()
                === 'raos_st1704_reconciliation_candidate_invalid',
        'invalid result shape must fail closed'
    );
}

$snapshot_sha = str_repeat('1', 64);
$public_slug = 'portable-power-station-guide';
$review_slug = 'raos-review-' . $public_slug . '-' . $snapshot_sha;
$proposal = array(
    'public_slug' => $public_slug,
    'snapshot_payload_sha256' => $snapshot_sha,
);
$baseline_pairs = array(
    encoded_pair('_raos_publication_snapshot_v1', '{"fixture":true}'),
    encoded_pair('_thumbnail_id', '9'),
);
$before = array(
    'review_slug' => $review_slug,
    'storage' => array(
        'restore' => array(
            'meta_rows' => $baseline_pairs,
            'post_fields' => array(
                'post_date' => base64_encode('2026-08-27 08:00:00'),
            ),
        ),
    ),
);
$storage = array('summary' => array('fixture' => 'published'));

$GLOBALS['wpdb'] = new FakeWpdb();
$GLOBALS['wpdb']->meta_rows = array(
    meta_row(10, '_raos_publication_snapshot_v1', '{"fixture":true}'),
    meta_row(11, '_thumbnail_id', '9'),
    meta_row(12, '_wp_old_slug', $review_slug),
);
$same_day = $meta_plan_method->invoke(
    $controller,
    28,
    $proposal,
    $before,
    array('post_date' => '2026-08-27 12:00:00'),
    $storage
);
expect_true(
    is_array($same_day),
    'same-day slug plan must succeed: '
        . ($same_day instanceof WP_Error ? $same_day->code : gettype($same_day))
);
expect_true(
    $same_day['state'] === 'EXACT_REDIRECT_EXTRAS'
        && count($same_day['delete_rows']) === 1
        && $same_day['delete_rows'][0]['meta_key'] === '_wp_old_slug',
    'same-day plan must delete slug only'
);

$GLOBALS['wpdb']->meta_rows[] = meta_row(13, '_wp_old_date', '2026-08-27');
$next_day = $meta_plan_method->invoke(
    $controller,
    28,
    $proposal,
    $before,
    array('post_date' => '2026-08-28 12:00:00'),
    $storage
);
expect_true(is_array($next_day), 'slug plus date plan must succeed');
expect_true(
    $next_day['state'] === 'EXACT_REDIRECT_EXTRAS'
        && count($next_day['delete_rows']) === 2
        && $next_day['delete_rows'][1]['meta_key'] === '_wp_old_date',
    'next-day plan must delete slug and date'
);

$slug_only_before = $before;
$slug_only_before['storage']['restore']['meta_rows'][] =
    encoded_pair('_wp_old_date', '2026-08-27');
$GLOBALS['wpdb']->meta_rows = array(
    meta_row(10, '_raos_publication_snapshot_v1', '{"fixture":true}'),
    meta_row(11, '_thumbnail_id', '9'),
    meta_row(12, '_wp_old_date', '2026-08-27'),
    meta_row(13, '_wp_old_slug', $review_slug),
);
$slug_only = $meta_plan_method->invoke(
    $controller,
    28,
    $proposal,
    $slug_only_before,
    array('post_date' => '2026-08-28 12:00:00'),
    $storage
);
expect_true(
    is_array($slug_only)
        && $slug_only['state'] === 'EXACT_REDIRECT_EXTRAS'
        && count($slug_only['delete_rows']) === 1
        && $slug_only['delete_rows'][0]['meta_key'] === '_wp_old_slug',
    'pre-existing old date must produce slug-only cleanup'
);

$GLOBALS['wpdb']->meta_rows = array(
    meta_row(10, '_raos_publication_snapshot_v1', '{"fixture":true}'),
    meta_row(11, '_thumbnail_id', '9'),
);
$clean = $meta_plan_method->invoke(
    $controller,
    28,
    $proposal,
    $before,
    array('post_date' => '2026-08-28 12:00:00'),
    $storage
);
expect_true(is_array($clean) && $clean['state'] === 'CLEAN', 'clean replay state');

$GLOBALS['wpdb']->meta_rows = array(
    meta_row(10, '_raos_publication_snapshot_v1', '{"fixture":true}'),
    meta_row(11, '_thumbnail_id', '9'),
    meta_row(12, '_wp_old_slug', $review_slug),
    meta_row(13, '_wp_old_slug', $review_slug),
);
$duplicate = $meta_plan_method->invoke(
    $controller,
    28,
    $proposal,
    $before,
    array('post_date' => '2026-08-28 12:00:00'),
    $storage
);
expect_true(
    $duplicate instanceof WP_Error
        && $duplicate->code === 'raos_st1704_reconciliation_meta_duplicate',
    'duplicate redirect row must fail'
);

$GLOBALS['wpdb']->meta_rows = array(
    meta_row(10, '_raos_publication_snapshot_v1', '{"fixture":true}'),
    meta_row(11, '_thumbnail_id', '9'),
    meta_row(12, '_unrelated', 'unexpected'),
);
$unrelated = $meta_plan_method->invoke(
    $controller,
    28,
    $proposal,
    $before,
    array('post_date' => '2026-08-27 12:00:00'),
    $storage
);
expect_true($unrelated instanceof WP_Error, 'unrelated extra meta must fail');

$GLOBALS['wpdb']->meta_rows = array(
    meta_row(10, '_raos_publication_snapshot_v1', '{"fixture":true}'),
    meta_row(12, '_wp_old_slug', $review_slug),
);
$missing = $meta_plan_method->invoke(
    $controller,
    28,
    $proposal,
    $before,
    array('post_date' => '2026-08-27 12:00:00'),
    $storage
);
expect_true(
    $missing instanceof WP_Error
        && $missing->code === 'raos_st1704_reconciliation_meta_missing',
    'missing before row must fail'
);

$core_delete_before = $before;
$core_delete_before['storage']['restore']['meta_rows'][] =
    encoded_pair('_wp_old_slug', $public_slug);
$GLOBALS['wpdb']->meta_rows = array(
    meta_row(10, '_raos_publication_snapshot_v1', '{"fixture":true}'),
    meta_row(11, '_thumbnail_id', '9'),
    meta_row(12, '_wp_old_slug', $public_slug),
    meta_row(13, '_wp_old_slug', $review_slug),
);
$core_delete = $meta_plan_method->invoke(
    $controller,
    28,
    $proposal,
    $core_delete_before,
    array('post_date' => '2026-08-27 12:00:00'),
    $storage
);
expect_true(
    $core_delete instanceof WP_Error
        && $core_delete->code
            === 'raos_st1704_reconciliation_core_delete_prestate',
    'core-delete prestate must fail'
);

$base_meta = array(
    meta_row(10, '_raos_publication_snapshot_v1', '{"fixture":true}'),
    meta_row(11, '_thumbnail_id', '9'),
);
$cleanup_meta = array(
    array(
        'meta_id' => 12,
        'meta_key' => '_wp_old_slug',
        'meta_value' => $review_slug,
    ),
    array(
        'meta_id' => 13,
        'meta_key' => '_wp_old_date',
        'meta_value' => '2026-08-27',
    ),
);
$GLOBALS['wpdb'] = new FakeWpdb();
$GLOBALS['wpdb']->meta_rows = array_merge(
    $base_meta,
    array(
        meta_row(12, '_wp_old_slug', $review_slug),
        meta_row(13, '_wp_old_date', '2026-08-27'),
    )
);
$original_meta = $GLOBALS['wpdb']->meta_rows;
$GLOBALS['wpdb']->query('START TRANSACTION');
$GLOBALS['wpdb']->fail_delete_at = 2;
$delete_failed = $cas_method->invoke($controller, $cleanup_meta, 28);
expect_true($delete_failed === false, 'second CAS delete fault must fail');
$GLOBALS['wpdb']->query('ROLLBACK');
expect_true($GLOBALS['wpdb']->meta_rows === $original_meta, 'delete rollback exact');

$proposal_id = str_repeat('a', 64);
$zero_proposal = str_repeat('0', 64);
$created_at = gmdate('Y-m-d H:i:s', time() - 4000);
$approved_at = gmdate('Y-m-d H:i:s', time() - 3900);
$apply_at = gmdate('Y-m-d H:i:s', time() - 3800);
$completed_at = gmdate('Y-m-d H:i:s', time() - 3700);
$GLOBALS['wpdb']->audit_rows = array();
append_fixture_audit(
    $GLOBALS['wpdb'],
    gmdate('Y-m-d H:i:s', time() - 5000),
    0,
    'PUBLICATION_CONTROLLER_ACTIVATED',
    $zero_proposal,
    'PUBLICATION_TABLES_READY'
);
append_fixture_audit(
    $GLOBALS['wpdb'],
    $created_at,
    7,
    'PROPOSAL_CREATED',
    $proposal_id,
    'PROPOSED'
);
append_fixture_audit(
    $GLOBALS['wpdb'],
    $approved_at,
    8,
    'HUMAN_APPROVED',
    $proposal_id,
    'APPROVED'
);
append_fixture_audit(
    $GLOBALS['wpdb'],
    $apply_at,
    7,
    'APPLY_STARTED',
    $proposal_id,
    'APPLYING'
);
append_fixture_audit(
    $GLOBALS['wpdb'],
    $completed_at,
    7,
    'APPLY_FAILED',
    $proposal_id,
    'POST_COMMIT_HOOK_REPLAY_UNCERTAIN'
);
$base_audit = $GLOBALS['wpdb']->audit_rows;
$candidate = array(
    'proposer_user_id' => '7',
    'approved_by_user_id' => '8',
    'created_at' => $created_at,
    'approved_at' => $approved_at,
    'apply_started_at' => $apply_at,
    'completed_at' => $completed_at,
    'result_code' => 'POST_COMMIT_HOOK_REPLAY_UNCERTAIN',
);
$audit_base_result = $audit_method->invoke(
    $controller,
    $candidate,
    $proposal_id
);
expect_true(
    is_array($audit_base_result)
        && $audit_base_result['stage'] === 'CLEANUP_REQUIRED',
    'base audit must require cleanup'
);
$exception_candidate = $candidate;
$exception_candidate['result_code'] = 'POST_COMMIT_HOOK_REPLAY_EXCEPTION';
$GLOBALS['wpdb']->audit_rows[4]['detail_code'] =
    'POST_COMMIT_HOOK_REPLAY_EXCEPTION';
$exception_material = implode("\n", array(
    $GLOBALS['wpdb']->audit_rows[4]['previous_hash'],
    $GLOBALS['wpdb']->audit_rows[4]['occurred_at'],
    $GLOBALS['wpdb']->audit_rows[4]['actor_user_id'],
    $GLOBALS['wpdb']->audit_rows[4]['event_code'],
    $GLOBALS['wpdb']->audit_rows[4]['proposal_id'],
    $GLOBALS['wpdb']->audit_rows[4]['detail_code'],
));
$GLOBALS['wpdb']->audit_rows[4]['event_hash'] = hash(
    'sha256',
    $exception_material
);
$exception_audit_result = $audit_method->invoke(
    $controller,
    $exception_candidate,
    $proposal_id
);
expect_true(
    is_array($exception_audit_result)
        && $exception_audit_result['stage'] === 'CLEANUP_REQUIRED',
    'exception receipt must bind its exact audit failure detail'
);
$cross_swapped_audit = $audit_method->invoke(
    $controller,
    $candidate,
    $proposal_id
);
expect_true(
    $cross_swapped_audit instanceof WP_Error,
    'receipt and audit failure codes must not cross-swap'
);
$GLOBALS['wpdb']->audit_rows = $base_audit;
$GLOBALS['wpdb']->audit_rows[2]['actor_user_id'] = '99';
$tampered_audit = $audit_method->invoke($controller, $candidate, $proposal_id);
expect_true($tampered_audit instanceof WP_Error, 'audit tamper must fail');
$GLOBALS['wpdb']->audit_rows = $base_audit;

$GLOBALS['wpdb']->meta_rows = $original_meta;
$GLOBALS['wpdb']->audit_rows = $base_audit;
$GLOBALS['wpdb']->fail_delete_at = null;
$GLOBALS['wpdb']->fail_audit_insert = true;
$GLOBALS['wpdb']->query('START TRANSACTION');
expect_true(
    $cas_method->invoke($controller, $cleanup_meta, 28) === true,
    'CAS before audit fault'
);
$audit_insert = $append_method->invoke(
    null,
    'REDIRECT_META_RECONCILED',
    $proposal_id,
    str_repeat('B', 64),
    9
);
expect_true($audit_insert === false, 'audit insert fault');
$GLOBALS['wpdb']->query('ROLLBACK');
expect_true($GLOBALS['wpdb']->meta_rows === $original_meta, 'audit fault meta rollback');
expect_true($GLOBALS['wpdb']->audit_rows === $base_audit, 'audit fault chain rollback');

$GLOBALS['wpdb']->fail_audit_insert = false;
$GLOBALS['wpdb']->fail_commit = true;
$GLOBALS['wpdb']->query('START TRANSACTION');
expect_true($cas_method->invoke($controller, $cleanup_meta, 28) === true, 'commit CAS');
expect_true(
    is_string($append_method->invoke(
        null,
        'REDIRECT_META_RECONCILED',
        $proposal_id,
        str_repeat('B', 64),
        9
    )),
    'commit audit append'
);
expect_true($GLOBALS['wpdb']->query('COMMIT') === false, 'commit fault');
$GLOBALS['wpdb']->query('ROLLBACK');
expect_true($GLOBALS['wpdb']->meta_rows === $original_meta, 'commit fault meta rollback');
expect_true($GLOBALS['wpdb']->audit_rows === $base_audit, 'commit fault audit rollback');

$GLOBALS['wpdb']->fail_commit = false;
$GLOBALS['wpdb']->commit_response_loss = true;
$GLOBALS['wpdb']->query('START TRANSACTION');
expect_true($cas_method->invoke($controller, $cleanup_meta, 28) === true, 'loss CAS');
expect_true(
    is_string($append_method->invoke(
        null,
        'REDIRECT_META_RECONCILED',
        $proposal_id,
        str_repeat('B', 64),
        9
    )),
    'loss audit append'
);
expect_true($GLOBALS['wpdb']->query('COMMIT') === false, 'simulated response loss');
$GLOBALS['wpdb']->query('ROLLBACK');
expect_true($GLOBALS['wpdb']->meta_rows === $base_meta, 'response-loss commit persisted');
$loss_audit = $audit_method->invoke($controller, $candidate, $proposal_id);
expect_true(
    is_array($loss_audit)
        && $loss_audit['stage'] === 'CLEANED'
        && $loss_audit['cleanup_operation_sha256'] === str_repeat('b', 64),
    'response-loss audit classifies idempotently'
);
$loss_clean = $meta_plan_method->invoke(
    $controller,
    28,
    $proposal,
    $before,
    array('post_date' => '2026-08-28 12:00:00'),
    $storage
);
expect_true(
    is_array($loss_clean) && $loss_clean['state'] === 'CLEAN',
    'response-loss meta classifies clean'
);

$cleanup_operation = $loss_audit['cleanup_operation_sha256'];
$unrelated_proposal = str_repeat('c', 64);
append_fixture_audit(
    $GLOBALS['wpdb'],
    gmdate('Y-m-d H:i:s'),
    11,
    'PROPOSAL_CREATED',
    $unrelated_proposal,
    'PROPOSED'
);
$after_unrelated = $audit_method->invoke($controller, $candidate, $proposal_id);
expect_true(
    is_array($after_unrelated)
        && $after_unrelated['cleanup_operation_sha256'] === $cleanup_operation,
    'later global audit must not stale cleanup operation'
);

append_fixture_audit(
    $GLOBALS['wpdb'],
    gmdate('Y-m-d H:i:s'),
    10,
    'RECONCILED_PUBLIC',
    $proposal_id,
    str_repeat('D', 64)
);
$public_result = $audit_method->invoke($controller, $candidate, $proposal_id);
expect_true(
    is_array($public_result)
        && $public_result['stage'] === 'PUBLIC_CONFIRMED'
        && $public_result['verification_evidence_sha256'] === str_repeat('d', 64),
    'public evidence must classify once'
);
expect_true(
    ! hash_equals(
        $public_result['verification_evidence_sha256'],
        str_repeat('e', 64)
    ),
    'different evidence must conflict'
);
append_fixture_audit(
    $GLOBALS['wpdb'],
    gmdate('Y-m-d H:i:s'),
    10,
    'RECONCILED_PUBLIC',
    $proposal_id,
    str_repeat('D', 64)
);
$duplicate_public = $audit_method->invoke($controller, $candidate, $proposal_id);
expect_true($duplicate_public instanceof WP_Error, 'multiple final audits fail');

echo "TERMINAL_RECONCILIATION_BEHAVIOR_OK\n";
