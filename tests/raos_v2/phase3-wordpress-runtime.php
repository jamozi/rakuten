<?php
declare(strict_types=1);

/**
 * Minimal fail-closed WordPress runtime harness for the Phase 3 presentation
 * plugin. This is a local CI stub, not production or full WordPress evidence.
 *
 * Usage:
 *   php phase3-wordpress-runtime.php <source|generated> <plugin.php> <candidate.json>
 */

$GLOBALS['raos_v2_runtime_assertions'] = 0;
$GLOBALS['raos_v2_runtime_actions'] = array();
$GLOBALS['raos_v2_runtime_filters'] = array();
$GLOBALS['raos_v2_runtime_styles'] = array();
$GLOBALS['raos_v2_runtime_forbidden_calls'] = array();
$GLOBALS['raos_v2_runtime_is_singular'] = false;
$GLOBALS['raos_v2_runtime_is_main_query'] = false;
$GLOBALS['raos_v2_runtime_in_the_loop'] = false;
$GLOBALS['raos_v2_runtime_post'] = null;
$GLOBALS['post'] = null;
$GLOBALS['raos_v2_runtime_permalink'] = '';
$GLOBALS['wp_filter'] = array();
$GLOBALS['raos_v2_runtime_late_mutator_calls'] = 0;

const RAOS_V2_RUNTIME_EXPECTED_PLUGIN_SHA256 = 'b7ebed3ffabd6a5067707ec898e15901382e1782459f5087a3798b27fdc970b1';

function raos_v2_runtime_assert(bool $condition, string $failure_code): void
{
    $GLOBALS['raos_v2_runtime_assertions']++;
    if (! $condition) {
        throw new RuntimeException($failure_code);
    }
}

function raos_v2_runtime_forbidden_call(string $function_name): void
{
    $GLOBALS['raos_v2_runtime_forbidden_calls'][] = $function_name;
}

function raos_v2_runtime_failure_receipt(Throwable $error): void
{
    $message = $error->getMessage();
    $failure_code = preg_match('/\A[A-Z0-9_]+\z/', $message) === 1
        ? $message
        : 'UNEXPECTED_RUNTIME_FAILURE';
    $receipt = array(
        'schema' => 'RAOS_V2_PHASE3_WORDPRESS_RUNTIME_RECEIPT_V1',
        'status' => 'FAILED_LOCAL_CI_STUB',
        'evidence_scope' => 'LOCAL_CI_NOT_WORDPRESS_PRODUCTION',
        'failure_code' => $failure_code,
        'failure_type' => get_class($error),
        'assertion_count' => $GLOBALS['raos_v2_runtime_assertions'],
        'php_version' => PHP_VERSION,
    );
    fwrite(
        STDERR,
        json_encode($receipt, JSON_UNESCAPED_SLASHES) . PHP_EOL
    );
}

class WP_Post
{
    /** @var int */
    public $ID;

    /** @var string */
    public $post_name;

    /** @var string */
    public $post_content;

    public function __construct(int $post_id, string $post_name, string $post_content)
    {
        $this->ID = $post_id;
        $this->post_name = $post_name;
        $this->post_content = $post_content;
    }
}

class WP_Hook
{
    /** @var array<int, array<string, array{function: callable|string, accepted_args: int}>> */
    public $callbacks = array();
}

class RaosV2RuntimeTermination extends RuntimeException
{
    /** @var string */
    public $page_title;

    /** @var array<string, mixed> */
    public $arguments;

    /** @param array<string, mixed> $arguments */
    public function __construct(string $message, string $page_title, array $arguments)
    {
        parent::__construct($message);
        $this->page_title = $page_title;
        $this->arguments = $arguments;
    }
}

function is_singular(string $post_type): bool
{
    return $post_type === 'post' && $GLOBALS['raos_v2_runtime_is_singular'];
}

function is_main_query(): bool
{
    return $GLOBALS['raos_v2_runtime_is_main_query'];
}

function in_the_loop(): bool
{
    return $GLOBALS['raos_v2_runtime_in_the_loop'];
}

/** @return int|false */
function get_the_ID()
{
    $post = $GLOBALS['post'];
    return $post instanceof WP_Post ? $post->ID : false;
}

/** @return mixed */
function get_queried_object()
{
    return $GLOBALS['raos_v2_runtime_post'];
}

/** @return mixed */
function get_permalink(WP_Post $post)
{
    unset($post);
    return $GLOBALS['raos_v2_runtime_permalink'];
}

/** @return mixed */
function wp_parse_url(string $url, int $component = -1)
{
    return parse_url($url, $component);
}

function esc_attr(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function plugins_url(string $path, string $plugin_file): string
{
    unset($plugin_file);
    return 'https://example.invalid/wp-content/plugins/raos-v2-decision-support/'
        . ltrim($path, '/');
}

/** @param string|WP_Error $message @param string $title @param array<string, mixed> $args */
function wp_die($message, $title = '', $args = array()): void
{
    if (! is_string($message) || ! is_string($title) || ! is_array($args)) {
        throw new RuntimeException('WP_DIE_ARGUMENTS_INVALID');
    }
    throw new RaosV2RuntimeTermination($message, $title, $args);
}

/** @param array<int, string> $dependencies */
function wp_enqueue_style(
    string $handle,
    string $source,
    array $dependencies = array(),
    $version = false,
    string $media = 'all'
): void {
    $GLOBALS['raos_v2_runtime_styles'][] = array(
        'handle' => $handle,
        'source' => $source,
        'dependencies' => $dependencies,
        'version' => $version,
        'media' => $media,
    );
}

/** @param callable|string $callback */
function add_action(
    string $hook,
    $callback,
    int $priority = 10,
    int $accepted_args = 1
): void {
    $GLOBALS['raos_v2_runtime_actions'][] = array(
        'hook' => $hook,
        'callback' => $callback,
        'priority' => $priority,
        'accepted_args' => $accepted_args,
    );
}

/** @param callable|string $callback */
function add_filter(
    string $hook,
    $callback,
    int $priority = 10,
    int $accepted_args = 1
): void {
    if (! isset($GLOBALS['wp_filter'][$hook])) {
        $GLOBALS['wp_filter'][$hook] = new WP_Hook();
    }
    $hook_object = $GLOBALS['wp_filter'][$hook];
    if (! ($hook_object instanceof WP_Hook)) {
        throw new RuntimeException('FILTER_HOOK_OBJECT_INVALID');
    }
    $callback_id = is_string($callback)
        ? $callback
        : 'callback-' . count($hook_object->callbacks[$priority] ?? array());
    $hook_object->callbacks[$priority][$callback_id] = array(
        'function' => $callback,
        'accepted_args' => $accepted_args,
    );
    $GLOBALS['raos_v2_runtime_filters'][] = array(
        'hook' => $hook,
        'callback' => $callback,
        'priority' => $priority,
        'accepted_args' => $accepted_args,
    );
}

/** @param mixed $value @return mixed */
function apply_filters(string $hook, $value)
{
    $hook_object = $GLOBALS['wp_filter'][$hook] ?? null;
    if (! ($hook_object instanceof WP_Hook)) {
        return $value;
    }
    ksort($hook_object->callbacks, SORT_NUMERIC);
    foreach (array_keys($hook_object->callbacks) as $priority) {
        foreach ($hook_object->callbacks[$priority] as $row) {
            if (! is_array($row) || ! is_callable($row['function'] ?? null)) {
                continue;
            }
            $value = call_user_func($row['function'], $value);
        }
    }
    return $value;
}

/** Record forbidden WordPress capabilities if a plugin attempts to call them. */
function wp_remote_get(...$arguments) { unset($arguments); raos_v2_runtime_forbidden_call(__FUNCTION__); }
function wp_remote_post(...$arguments) { unset($arguments); raos_v2_runtime_forbidden_call(__FUNCTION__); }
function wp_remote_request(...$arguments) { unset($arguments); raos_v2_runtime_forbidden_call(__FUNCTION__); }
function wp_insert_post(...$arguments) { unset($arguments); raos_v2_runtime_forbidden_call(__FUNCTION__); }
function wp_update_post(...$arguments) { unset($arguments); raos_v2_runtime_forbidden_call(__FUNCTION__); }
function update_option(...$arguments) { unset($arguments); raos_v2_runtime_forbidden_call(__FUNCTION__); }
function add_option(...$arguments) { unset($arguments); raos_v2_runtime_forbidden_call(__FUNCTION__); }
function delete_option(...$arguments) { unset($arguments); raos_v2_runtime_forbidden_call(__FUNCTION__); }
function update_post_meta(...$arguments) { unset($arguments); raos_v2_runtime_forbidden_call(__FUNCTION__); }
function register_rest_route(...$arguments) { unset($arguments); raos_v2_runtime_forbidden_call(__FUNCTION__); }
function wp_schedule_event(...$arguments) { unset($arguments); raos_v2_runtime_forbidden_call(__FUNCTION__); }
function set_transient(...$arguments) { unset($arguments); raos_v2_runtime_forbidden_call(__FUNCTION__); }

/** @return array{0: int, 1: mixed}|null */
function raos_v2_runtime_next_source_token(array $tokens, int $offset): ?array
{
    $count = count($tokens);
    for ($index = $offset; $index < $count; $index++) {
        $token = $tokens[$index];
        if (
            is_array($token)
            && in_array($token[0], array(T_WHITESPACE, T_COMMENT, T_DOC_COMMENT), true)
        ) {
            continue;
        }
        return array($index, $token);
    }
    return null;
}

/** @return array{0: int, 1: mixed}|null */
function raos_v2_runtime_previous_source_token(array $tokens, int $offset): ?array
{
    for ($index = $offset; $index >= 0; $index--) {
        $token = $tokens[$index];
        if (
            is_array($token)
            && in_array($token[0], array(T_WHITESPACE, T_COMMENT, T_DOC_COMMENT), true)
        ) {
            continue;
        }
        return array($index, $token);
    }
    return null;
}

/**
 * Return every plugin source capability outside the read-only presentation set.
 *
 * This is intentionally a strict function-call allowlist. Unknown calls,
 * methods, static calls, dynamic calls, includes, evaluation, process syntax,
 * and object construction all fail the CI runtime before the plugin is loaded.
 * The sole direct file read is separately pinned to the adjacent binding path.
 *
 * @return array<int, string>
 */
function raos_v2_runtime_plugin_source_violations(string $source): array
{
    $allowed_calls = array_fill_keys(
        array(
            'add_action',
            'add_filter',
            'array_key_exists',
            'array_keys',
            'clearstatcache',
            'count',
            'defined',
            'esc_attr',
            'file_get_contents',
            'filesize',
            'get_permalink',
            'get_queried_object',
            'get_the_id',
            'hash',
            'hash_equals',
            'in_the_loop',
            'is_array',
            'is_file',
            'is_int',
            'is_link',
            'is_main_query',
            'is_readable',
            'is_singular',
            'is_string',
            'json_decode',
            'json_last_error',
            'plugins_url',
            'preg_match',
            'sort',
            'strlen',
            'substr_count',
            'wp_die',
            'wp_enqueue_style',
            'wp_parse_url',
        ),
        true
    );
    $special_tokens = array(
        T_EVAL => 'eval',
        T_INCLUDE => 'include',
        T_INCLUDE_ONCE => 'include_once',
        T_REQUIRE => 'require',
        T_REQUIRE_ONCE => 'require_once',
    );
    $tokens = token_get_all($source);
    $violations = array();
    foreach ($tokens as $index => $token) {
        if (is_string($token)) {
            if ($token === '`') {
                $violations[] = 'shell_backtick';
            }
            continue;
        }
        if (isset($special_tokens[$token[0]])) {
            $violations[] = $special_tokens[$token[0]];
            continue;
        }
        $next = raos_v2_runtime_next_source_token($tokens, $index + 1);
        if ($next === null || $next[1] !== '(') {
            continue;
        }
        $previous = raos_v2_runtime_previous_source_token($tokens, $index - 1);
        if ($token[0] === T_VARIABLE) {
            $violations[] = 'dynamic_call';
            continue;
        }
        if ($token[0] !== T_STRING) {
            continue;
        }
        if (
            $previous !== null
            && is_array($previous[1])
            && $previous[1][0] === T_FUNCTION
        ) {
            continue;
        }
        $name = strtolower($token[1]);
        if ($previous !== null && is_array($previous[1])) {
            if ($previous[1][0] === T_OBJECT_OPERATOR) {
                $violations[] = 'method:' . $name;
                continue;
            }
            if ($previous[1][0] === T_DOUBLE_COLON) {
                $violations[] = 'static:' . $name;
                continue;
            }
            if ($previous[1][0] === T_NEW) {
                $violations[] = 'new:' . $name;
                continue;
            }
        }
        if (
            strpos($name, 'raos_v2_decision_support_') !== 0
            && ! isset($allowed_calls[$name])
        ) {
            $violations[] = 'function:' . $name;
        }
    }
    if (
        substr_count(
            $source,
            '$path = __DIR__ . \'/cutover-binding.v1.json\';'
        ) !== 1
        || substr_count($source, '@file_get_contents($path)') !== 1
        || substr_count($source, 'file_get_contents') !== 1
    ) {
        $violations[] = 'local_binding_read_contract';
    }
    $violations = array_values(array_unique($violations));
    sort($violations, SORT_STRING);
    return $violations;
}

function raos_v2_runtime_context(
    WP_Post $queried_post,
    string $permalink,
    ?WP_Post $current_post = null,
    bool $is_main_query = true,
    bool $in_the_loop = true
): void {
    $GLOBALS['raos_v2_runtime_is_singular'] = true;
    $GLOBALS['raos_v2_runtime_is_main_query'] = $is_main_query;
    $GLOBALS['raos_v2_runtime_in_the_loop'] = $in_the_loop;
    $GLOBALS['raos_v2_runtime_post'] = $queried_post;
    $GLOBALS['post'] = $current_post ?? $queried_post;
    $GLOBALS['raos_v2_runtime_permalink'] = $permalink;
    $GLOBALS['raos_v2_runtime_styles'] = array();
}

function raos_v2_runtime_late_mutator(string $content): string
{
    $GLOBALS['raos_v2_runtime_late_mutator_calls']++;
    return $content . '<p>late-filter-drift</p>';
}

function raos_v2_runtime_default_content_filter(string $content): string
{
    return '<div data-runtime-default-content-filter="APPLIED">'
        . $content
        . '</div>';
}

/** @param array<string, mixed> $binding */
function raos_v2_runtime_write_binding(string $path, array $binding): void
{
    $encoded = json_encode(
        $binding,
        JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT
    );
    raos_v2_runtime_assert(is_string($encoded), 'BINDING_ENCODE_FAILED');
    raos_v2_runtime_assert(
        file_put_contents($path, $encoded . PHP_EOL) !== false,
        'BINDING_WRITE_FAILED'
    );
    clearstatcache(true, $path);
}

try {
    raos_v2_runtime_assert($argc === 4, 'CLI_ARGUMENT_COUNT_INVALID');
    $artifact_kind = $argv[1];
    raos_v2_runtime_assert(
        in_array($artifact_kind, array('source', 'generated'), true),
        'ARTIFACT_KIND_INVALID'
    );

    $plugin_file = realpath($argv[2]);
    $candidate_file = realpath($argv[3]);
    raos_v2_runtime_assert($plugin_file !== false, 'PLUGIN_FILE_MISSING');
    raos_v2_runtime_assert($candidate_file !== false, 'CANDIDATE_FILE_MISSING');
    raos_v2_runtime_assert(is_file($plugin_file), 'PLUGIN_PATH_NOT_FILE');
    raos_v2_runtime_assert(is_file($candidate_file), 'CANDIDATE_PATH_NOT_FILE');

    $plugin_source = file_get_contents($plugin_file);
    raos_v2_runtime_assert($plugin_source !== false, 'PLUGIN_SOURCE_READ_FAILED');
    raos_v2_runtime_assert(
        hash('sha256', $plugin_source) === RAOS_V2_RUNTIME_EXPECTED_PLUGIN_SHA256,
        'PLUGIN_SOURCE_BYTE_PIN_INVALID'
    );
    $unsafe_mutation = <<<'PHP'
<?php
$path = __DIR__ . '/cutover-binding.v1.json';
@file_get_contents($path);
file_put_contents('/tmp/forbidden', 'x');
fsockopen('example.invalid', 443);
mysqli_connect('example.invalid');
exec('false');
unlink('/tmp/forbidden');
new PDO('sqlite::memory:');
$callable();
$wpdb->query('DELETE');
UnsafeRuntime::write();
require '/tmp/forbidden.php';
`false`;
PHP;
    $mutation_violations = raos_v2_runtime_plugin_source_violations(
        $unsafe_mutation
    );
    foreach (
        array(
            'dynamic_call',
            'function:exec',
            'function:file_put_contents',
            'function:fsockopen',
            'function:mysqli_connect',
            'function:unlink',
            'method:query',
            'new:pdo',
            'require',
            'shell_backtick',
            'static:write',
        ) as $required_violation
    ) {
        raos_v2_runtime_assert(
            in_array($required_violation, $mutation_violations, true),
            'SOURCE_CAPABILITY_MUTATION_NOT_REJECTED'
        );
    }
    raos_v2_runtime_assert(
        raos_v2_runtime_plugin_source_violations($plugin_source) === array(),
        'PLUGIN_SOURCE_CAPABILITY_SURFACE_INVALID'
    );
    $source_mutations = array(
        str_replace(
            '@file_get_contents($path);',
            '$path = \'https://example.invalid/write-probe\';'
                . "\n    "
                . '@file_get_contents($path);',
            $plugin_source
        ),
        str_replace(
            "add_action('wp_enqueue_scripts', 'raos_v2_decision_support_enqueue_style');",
            "add_action('wp_enqueue_scripts', 'session_start');",
            $plugin_source
        ),
        str_replace(
            'defined(\'ABSPATH\') || exit;',
            "defined('ABSPATH') || exit;\n\$GLOBALS['raos_callable']();",
            $plugin_source
        ),
    );
    foreach ($source_mutations as $mutated_source) {
        raos_v2_runtime_assert(
            $mutated_source !== $plugin_source
                && hash('sha256', $mutated_source)
                    !== RAOS_V2_RUNTIME_EXPECTED_PLUGIN_SHA256,
            'PLUGIN_SOURCE_BYTE_PIN_MUTATION_NOT_REJECTED'
        );
    }

    $candidate_json = file_get_contents($candidate_file);
    raos_v2_runtime_assert($candidate_json !== false, 'CANDIDATE_READ_FAILED');
    $candidate = json_decode($candidate_json, true);
    raos_v2_runtime_assert(is_array($candidate), 'CANDIDATE_JSON_INVALID');
    raos_v2_runtime_assert(
        isset($candidate['fields']) && is_array($candidate['fields']),
        'CANDIDATE_FIELDS_INVALID'
    );
    $sealed_content = $candidate['fields']['post_content'] ?? null;
    raos_v2_runtime_assert(is_string($sealed_content), 'SEALED_CONTENT_INVALID');

    $tracked_binding_file = realpath(
        dirname($plugin_file) . DIRECTORY_SEPARATOR . 'cutover-binding.v1.json'
    );
    raos_v2_runtime_assert(
        $tracked_binding_file !== false && is_file($tracked_binding_file),
        'TRACKED_BINDING_MISSING'
    );
    $tracked_binding_json = file_get_contents($tracked_binding_file);
    $disabled_binding = is_string($tracked_binding_json)
        ? json_decode($tracked_binding_json, true)
        : null;
    raos_v2_runtime_assert(
        is_array($disabled_binding)
            && ($disabled_binding['state'] ?? null) === 'DEPLOYMENT_DISABLED',
        'TRACKED_BINDING_NOT_DEPLOYMENT_DISABLED'
    );

    $legacy_content = "  <p>existing-legacy-public-content</p>\n";
    $inactive_sealed = apply_filters('the_content', $sealed_content);
    raos_v2_runtime_assert(
        $inactive_sealed === $sealed_content
            && $GLOBALS['raos_v2_runtime_actions'] === array()
            && $GLOBALS['raos_v2_runtime_filters'] === array()
            && $GLOBALS['raos_v2_runtime_styles'] === array(),
        'INACTIVE_PLUGIN_RUNTIME_EFFECT'
    );

    $runtime_directory = sys_get_temp_dir()
        . DIRECTORY_SEPARATOR
        . 'raos-v2-phase3-wordpress-runtime-'
        . getmypid()
        . '-'
        . bin2hex(random_bytes(8));
    raos_v2_runtime_assert(
        mkdir($runtime_directory, 0700),
        'RUNTIME_DIRECTORY_CREATE_FAILED'
    );
    $runtime_plugin_file = $runtime_directory
        . DIRECTORY_SEPARATOR
        . 'raos-v2-decision-support.php';
    $runtime_binding_file = $runtime_directory
        . DIRECTORY_SEPARATOR
        . 'cutover-binding.v1.json';
    raos_v2_runtime_assert(
        copy($plugin_file, $runtime_plugin_file),
        'RUNTIME_PLUGIN_COPY_FAILED'
    );
    raos_v2_runtime_write_binding($runtime_binding_file, $disabled_binding);

    define('ABSPATH', $runtime_directory . DIRECTORY_SEPARATOR);
    require $runtime_plugin_file;

    raos_v2_runtime_assert(
        defined('RAOS_V2_DECISION_SUPPORT_VERSION'),
        'PLUGIN_VERSION_MISSING'
    );
    raos_v2_runtime_assert(
        hash('sha256', $sealed_content)
            === RAOS_V2_DECISION_SUPPORT_POST_CONTENT_SHA256,
        'SEALED_CONTENT_HASH_MISMATCH'
    );
    raos_v2_runtime_assert(
        substr_count(
            $sealed_content,
            'data-raos-v2-package-marker="RAOS_V2_A05_POST_CONTENT_V1"'
        ) === 1,
        'SEALED_CONTENT_MARKER_INVALID'
    );

    raos_v2_runtime_assert(
        $GLOBALS['raos_v2_runtime_actions'] === array(
            array(
                'hook' => 'template_redirect',
                'callback' => 'raos_v2_decision_support_register_content_filter',
                'priority' => PHP_INT_MAX,
                'accepted_args' => 1,
            ),
            array(
                'hook' => 'wp_enqueue_scripts',
                'callback' => 'raos_v2_decision_support_enqueue_style',
                'priority' => 10,
                'accepted_args' => 1,
            ),
        ),
        'ACTION_HOOK_SURFACE_INVALID'
    );
    raos_v2_runtime_assert(
        $GLOBALS['raos_v2_runtime_filters'] === array(),
        'CONTENT_FILTER_REGISTERED_TOO_EARLY'
    );
    add_filter('the_content', 'raos_v2_runtime_default_content_filter', 10, 1);
    raos_v2_decision_support_register_content_filter();
    raos_v2_runtime_assert(
        $GLOBALS['raos_v2_runtime_filters'] === array(
            array(
                'hook' => 'the_content',
                'callback' => 'raos_v2_runtime_default_content_filter',
                'priority' => 10,
                'accepted_args' => 1,
            ),
            array(
                'hook' => 'the_content',
                'callback' => 'raos_v2_decision_support_wrap_content',
                'priority' => PHP_INT_MAX,
                'accepted_args' => 1,
            ),
        ),
        'FILTER_HOOK_SURFACE_INVALID'
    );

    $non_target_content = '<p>non-target-public-content</p>';
    raos_v2_runtime_context(
        new WP_Post(9901, 'another-article', $non_target_content),
        'https://kurashinoshirube.com/another-article/'
    );
    $expected_non_target = raos_v2_runtime_default_content_filter(
        $non_target_content
    );
    raos_v2_runtime_assert(
        apply_filters('the_content', $non_target_content)
            === $expected_non_target,
        'NON_TARGET_CONTENT_CHANGED'
    );
    raos_v2_decision_support_enqueue_style();
    raos_v2_runtime_assert(
        $GLOBALS['raos_v2_runtime_styles'] === array(),
        'NON_TARGET_STYLE_ENQUEUED'
    );

    raos_v2_runtime_context(
        new WP_Post(4242, RAOS_V2_DECISION_SUPPORT_SLUG, $legacy_content),
        'https://kurashinoshirube.com/carry-on-suitcase-comparison/'
    );
    $disabled_blocked = apply_filters('the_content', $legacy_content);
    raos_v2_runtime_assert(
        substr_count(
            $disabled_blocked,
            'data-raos-v2-post-content-envelope-status="BLOCKED"'
        ) === 1,
        'DISABLED_BINDING_TARGET_NOT_BLOCKED'
    );
    raos_v2_runtime_assert(
        strpos($disabled_blocked, 'existing-legacy-public-content') === false,
        'DISABLED_BINDING_TARGET_CONTENT_LEAKED'
    );
    raos_v2_decision_support_enqueue_style();
    raos_v2_runtime_assert(
        $GLOBALS['raos_v2_runtime_styles'] === array(),
        'DISABLED_BINDING_TARGET_STYLE_ENQUEUED'
    );

    raos_v2_runtime_assert(
        unlink($runtime_binding_file),
        'RUNTIME_BINDING_REMOVE_FAILED'
    );
    $missing_binding_blocked = apply_filters('the_content', $legacy_content);
    raos_v2_runtime_assert(
        substr_count(
            $missing_binding_blocked,
            'data-raos-v2-post-content-envelope-status="BLOCKED"'
        ) === 1,
        'MISSING_BINDING_TARGET_NOT_BLOCKED'
    );

    $invalid_binding = $disabled_binding;
    $invalid_binding['state'] = 'ARMED_EXACT_LEGACY_OR_SEALED';
    raos_v2_runtime_write_binding($runtime_binding_file, $invalid_binding);
    $invalid_binding_blocked = apply_filters('the_content', $legacy_content);
    raos_v2_runtime_assert(
        substr_count(
            $invalid_binding_blocked,
            'data-raos-v2-post-content-envelope-status="BLOCKED"'
        ) === 1,
        'INVALID_BINDING_TARGET_NOT_BLOCKED'
    );

    $armed_binding = $disabled_binding;
    $armed_binding['state'] = 'ARMED_EXACT_LEGACY_OR_SEALED';
    $armed_binding['target']['post_id'] = 4242;
    $armed_binding['hashes'] = array(
        'legacy_post_content_sha256' => hash('sha256', $legacy_content),
        'preaction_binding_sha256' => str_repeat('1', 64),
        'sealed_package_sha256' => str_repeat('2', 64),
        'sealed_post_content_sha256' => hash('sha256', $sealed_content),
        'source_owner_export_sha256' => str_repeat('3', 64),
    );
    raos_v2_runtime_write_binding($runtime_binding_file, $armed_binding);

    raos_v2_runtime_context(
        new WP_Post(4243, RAOS_V2_DECISION_SUPPORT_SLUG, $legacy_content),
        'https://kurashinoshirube.com/carry-on-suitcase-comparison/'
    );
    $wrong_post_id_blocked = apply_filters('the_content', $legacy_content);
    raos_v2_runtime_assert(
        substr_count(
            $wrong_post_id_blocked,
            'data-raos-v2-post-content-envelope-status="BLOCKED"'
        ) === 1,
        'WRONG_POST_ID_NOT_BLOCKED'
    );

    raos_v2_runtime_context(
        new WP_Post(4242, RAOS_V2_DECISION_SUPPORT_SLUG, $legacy_content),
        'https://kurashinoshirube.com/carry-on-suitcase-comparison/'
    );
    $legacy_filtered = apply_filters('the_content', $legacy_content);
    raos_v2_runtime_assert(
        $legacy_filtered === raos_v2_runtime_default_content_filter($legacy_content),
        'LEGACY_FILTER_TRANSFORM_NOT_PRESERVED'
    );
    raos_v2_runtime_assert(
        strpos($legacy_filtered, 'data-raos-v2-post-content-envelope=') === false,
        'LEGACY_TARGET_ENVELOPED'
    );
    raos_v2_runtime_assert(
        ! raos_v2_decision_support_should_enqueue(),
        'LEGACY_TARGET_STYLE_ALLOWED'
    );
    raos_v2_decision_support_enqueue_style();
    raos_v2_runtime_assert(
        $GLOBALS['raos_v2_runtime_styles'] === array(),
        'LEGACY_TARGET_STYLE_ENQUEUED'
    );

    $intermediate_content = $legacy_content . '<p>intermediate-write</p>';
    raos_v2_runtime_context(
        new WP_Post(
            4242,
            RAOS_V2_DECISION_SUPPORT_SLUG,
            $intermediate_content
        ),
        'https://kurashinoshirube.com/carry-on-suitcase-comparison/'
    );
    $intermediate_blocked = apply_filters(
        'the_content',
        $intermediate_content
    );
    raos_v2_runtime_assert(
        substr_count(
            $intermediate_blocked,
            'data-raos-v2-post-content-envelope-status="BLOCKED"'
        ) === 1,
        'INTERMEDIATE_CONTENT_NOT_BLOCKED'
    );
    raos_v2_runtime_assert(
        strpos($intermediate_blocked, 'intermediate-write') === false,
        'INTERMEDIATE_CONTENT_LEAKED'
    );

    $boundary_drift = "\n" . $sealed_content;
    raos_v2_runtime_context(
        new WP_Post(4242, RAOS_V2_DECISION_SUPPORT_SLUG, $boundary_drift),
        'https://kurashinoshirube.com/carry-on-suitcase-comparison/'
    );
    $boundary_blocked = apply_filters('the_content', $boundary_drift);
    raos_v2_runtime_assert(
        substr_count(
            $boundary_blocked,
            'data-raos-v2-post-content-envelope-status="BLOCKED"'
        ) === 1,
        'BOUNDARY_BYTE_DRIFT_NOT_BLOCKED'
    );
    raos_v2_runtime_assert(
        strpos($boundary_blocked, RAOS_V2_DECISION_SUPPORT_MARKER) === false,
        'BOUNDARY_BYTE_DRIFT_LEAKED'
    );

    $sealed_target_post = new WP_Post(
        4242,
        RAOS_V2_DECISION_SUPPORT_SLUG,
        $sealed_content
    );
    raos_v2_runtime_context(
        $sealed_target_post,
        'https://kurashinoshirube.com/carry-on-suitcase-comparison/'
    );
    raos_v2_runtime_assert(
        raos_v2_decision_support_should_enqueue(),
        'SEALED_TARGET_NOT_ACTIVATED'
    );
    raos_v2_decision_support_enqueue_style();
    raos_v2_runtime_assert(
        $GLOBALS['raos_v2_runtime_styles'] === array(
            array(
                'handle' => 'raos-v2-decision-support',
                'source' => 'https://example.invalid/wp-content/plugins/'
                    . 'raos-v2-decision-support/assets/decision-support.css',
                'dependencies' => array(),
                'version' => null,
                'media' => 'all',
            ),
        ),
        'SEALED_TARGET_STYLE_INVALID'
    );

    $wrapped = apply_filters('the_content', $sealed_content);
    $expected_wrapped = '<div data-raos-v2-post-content-envelope="'
        . RAOS_V2_DECISION_SUPPORT_ENVELOPE
        . '">'
        . $sealed_content
        . '</div>';
    raos_v2_runtime_assert(
        $wrapped === $expected_wrapped,
        'SEALED_TARGET_RAW_ENVELOPE_INVALID'
    );
    raos_v2_runtime_assert(
        strpos($wrapped, 'data-raos-v2-post-content-envelope-status="BLOCKED"')
            === false,
        'SEALED_TARGET_BLOCKED'
    );
    raos_v2_runtime_assert(
        apply_filters('the_content', $wrapped) === $wrapped,
        'SEALED_TARGET_NOT_IDEMPOTENT'
    );

    $secondary_content = '<p>secondary-query-public-content</p>';
    $secondary_post = new WP_Post(5151, 'secondary-article', $secondary_content);
    $secondary_expected = raos_v2_runtime_default_content_filter(
        $secondary_content
    );
    raos_v2_runtime_context(
        $sealed_target_post,
        'https://kurashinoshirube.com/carry-on-suitcase-comparison/',
        $secondary_post,
        false,
        true
    );
    $secondary_rendered = apply_filters('the_content', $secondary_content);
    raos_v2_runtime_assert(
        $secondary_rendered === $secondary_expected,
        'SECONDARY_QUERY_CONTENT_CHANGED'
    );
    raos_v2_runtime_assert(
        strpos($secondary_rendered, 'data-raos-v2-post-content-envelope=')
            === false
            && strpos($secondary_rendered, RAOS_V2_DECISION_SUPPORT_MARKER)
                === false
            && strpos(
                $secondary_rendered,
                'data-raos-v2-post-content-envelope-status="BLOCKED"'
            ) === false,
        'SECONDARY_QUERY_V2_PROJECTION_LEAKED'
    );

    raos_v2_runtime_context(
        $sealed_target_post,
        'https://kurashinoshirube.com/carry-on-suitcase-comparison/',
        $secondary_post,
        true,
        true
    );
    $mismatched_current_rendered = apply_filters(
        'the_content',
        $secondary_content
    );
    raos_v2_runtime_assert(
        $mismatched_current_rendered === $secondary_expected,
        'MISMATCHED_CURRENT_POST_CONTENT_CHANGED'
    );

    $outside_loop_content = '<p>outside-main-loop-content</p>';
    raos_v2_runtime_context(
        $sealed_target_post,
        'https://kurashinoshirube.com/carry-on-suitcase-comparison/',
        $sealed_target_post,
        true,
        false
    );
    $outside_loop_rendered = apply_filters(
        'the_content',
        $outside_loop_content
    );
    raos_v2_runtime_assert(
        substr_count(
            $outside_loop_rendered,
            'data-raos-v2-post-content-envelope-status="BLOCKED"'
        ) === 1,
        'OUTSIDE_MAIN_LOOP_TARGET_NOT_BLOCKED'
    );
    raos_v2_runtime_assert(
        strpos($outside_loop_rendered, 'outside-main-loop-content') === false
            && strpos($outside_loop_rendered, RAOS_V2_DECISION_SUPPORT_MARKER)
                === false,
        'OUTSIDE_MAIN_LOOP_TARGET_CONTENT_LEAKED'
    );

    $non_main_target_content = '<p>non-main-query-target-content</p>';
    raos_v2_runtime_context(
        $sealed_target_post,
        'https://kurashinoshirube.com/carry-on-suitcase-comparison/',
        $sealed_target_post,
        false,
        true
    );
    $non_main_target_blocked = apply_filters(
        'the_content',
        $non_main_target_content
    );
    raos_v2_runtime_assert(
        substr_count(
            $non_main_target_blocked,
            'data-raos-v2-post-content-envelope-status="BLOCKED"'
        ) === 1,
        'NON_MAIN_QUERY_TARGET_NOT_BLOCKED'
    );
    raos_v2_runtime_assert(
        strpos($non_main_target_blocked, 'non-main-query-target-content')
            === false,
        'NON_MAIN_QUERY_TARGET_CONTENT_LEAKED'
    );
    raos_v2_runtime_assert(
        substr_count($wrapped, 'data-raos-v2-post-content-envelope=') === 1
            && substr_count(
                $secondary_rendered
                    . $mismatched_current_rendered
                    . $outside_loop_rendered
                    . $non_main_target_blocked,
                'data-raos-v2-post-content-envelope='
            ) === 0
            && strpos(
                $secondary_rendered
                    . $mismatched_current_rendered
                    . $outside_loop_rendered
                    . $non_main_target_blocked,
                RAOS_V2_DECISION_SUPPORT_MARKER
            ) === false,
        'MAIN_CONTENT_PROJECTION_COUNT_INVALID'
    );

    raos_v2_runtime_context(
        $sealed_target_post,
        'https://kurashinoshirube.com/carry-on-suitcase-comparison/'
    );

    $earlier_filter_drift = apply_filters(
        'the_content',
        $sealed_content . '<p>earlier-filter-drift</p>'
    );
    raos_v2_runtime_assert(
        $earlier_filter_drift === $expected_wrapped,
        'SEALED_EARLIER_FILTER_OUTPUT_NOT_DISCARDED'
    );
    raos_v2_runtime_assert(
        strpos($earlier_filter_drift, 'earlier-filter-drift') === false
            && strpos($earlier_filter_drift, 'runtime-default-content-filter')
                === false,
        'SEALED_EARLIER_FILTER_OUTPUT_LEAKED'
    );

    add_filter('the_content', 'raos_v2_runtime_late_mutator', PHP_INT_MAX, 1);
    $termination = null;
    try {
        apply_filters('the_content', $sealed_content);
    } catch (RaosV2RuntimeTermination $caught) {
        $termination = $caught;
    }
    raos_v2_runtime_assert(
        $termination instanceof RaosV2RuntimeTermination,
        'LATER_MAX_PRIORITY_FILTER_DID_NOT_TERMINATE'
    );
    raos_v2_runtime_assert(
        $termination->getMessage()
            === '公開内容の最終整合性を確認できないため、このページを停止しました。',
        'LATER_MAX_PRIORITY_FILTER_TERMINATION_MESSAGE_INVALID'
    );
    raos_v2_runtime_assert(
        $termination->page_title === '公開内容の整合性エラー'
            && $termination->arguments === array('response' => 503, 'exit' => true),
        'LATER_MAX_PRIORITY_FILTER_TERMINATION_RESPONSE_INVALID'
    );
    raos_v2_runtime_assert(
        $GLOBALS['raos_v2_runtime_late_mutator_calls'] === 0,
        'LATER_MAX_PRIORITY_FILTER_EXECUTED'
    );
    raos_v2_runtime_assert(
        $GLOBALS['raos_v2_runtime_forbidden_calls'] === array(),
        'FORBIDDEN_CAPABILITY_CALLED'
    );

    $plugin_sha256 = hash_file('sha256', $plugin_file);
    raos_v2_runtime_assert(
        $plugin_sha256 === RAOS_V2_RUNTIME_EXPECTED_PLUGIN_SHA256,
        'PLUGIN_HASH_FAILED'
    );
    raos_v2_runtime_assert(
        unlink($runtime_binding_file),
        'RUNTIME_BINDING_CLEANUP_FAILED'
    );
    raos_v2_runtime_assert(
        unlink($runtime_plugin_file),
        'RUNTIME_PLUGIN_CLEANUP_FAILED'
    );
    raos_v2_runtime_assert(
        rmdir($runtime_directory),
        'RUNTIME_DIRECTORY_CLEANUP_FAILED'
    );
    $receipt = array(
        'schema' => 'RAOS_V2_PHASE3_WORDPRESS_RUNTIME_RECEIPT_V1',
        'status' => 'PASSED_LOCAL_CI_STUB',
        'evidence_scope' => 'LOCAL_CI_NOT_WORDPRESS_PRODUCTION',
        'artifact_kind' => $artifact_kind,
        'plugin_version' => RAOS_V2_DECISION_SUPPORT_VERSION,
        'plugin_sha256' => $plugin_sha256,
        'cutover_binding_schema' => RAOS_V2_DECISION_SUPPORT_BINDING_SCHEMA,
        'cutover_binding_state' => 'ARMED_EXACT_LEGACY_OR_SEALED',
        'legacy_post_content_sha256' => hash('sha256', $legacy_content),
        'sealed_post_content_sha256' => hash('sha256', $sealed_content),
        'php_version' => PHP_VERSION,
        'php_sapi' => PHP_SAPI,
        'assertion_count' => $GLOBALS['raos_v2_runtime_assertions'],
        'source_capability_scan' => 'STRICT_CALL_ALLOWLIST_PASSED',
        'source_byte_pin' => 'EXPECTED_SHA256_MATCHED',
        'capabilities_observed' => array(
            'wordpress_write' => false,
            'network' => false,
            'admin_hook' => false,
            'rest_hook' => false,
        ),
    );
    echo json_encode($receipt, JSON_UNESCAPED_SLASHES) . PHP_EOL;
} catch (Throwable $error) {
    raos_v2_runtime_failure_receipt($error);
    exit(1);
}
