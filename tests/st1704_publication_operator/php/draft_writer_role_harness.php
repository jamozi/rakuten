<?php
/** Executable WordPress-role harness for the ST-1704 activation primitive. */

declare(strict_types=1);

define('ABSPATH', __DIR__ . '/');
define('ARRAY_A', 'ARRAY_A');

$GLOBALS['raos_roles'] = array();
$GLOBALS['raos_stored_roles'] = array();
$GLOBALS['raos_add_role_fails'] = false;
$GLOBALS['raos_persist_role_writes'] = true;
$GLOBALS['raos_get_role_throws'] = false;

final class WP_Role
{
    public string $name;
    public array $capabilities;

    public function __construct(string $name, array $capabilities)
    {
        $this->name = $name;
        $this->capabilities = $capabilities;
    }

    public function remove_cap($capability): void
    {
        unset($this->capabilities[(string) $capability]);
        raos_persist_role_capabilities($this->name, $this->capabilities);
    }

    public function add_cap($capability, $grant = true): void
    {
        $this->capabilities[(string) $capability] = $grant;
        raos_persist_role_capabilities($this->name, $this->capabilities);
    }
}

final class RAOS_Bounded_Operator
{
}

final class FakeWpdb
{
    public string $prefix = 'wp_';
    public string $options = 'wp_options';
    public string $last_error = '';
    public int $role_option_row_count = 1;

    public function prepare($query, ...$arguments): array
    {
        return array((string) $query, $arguments);
    }

    public function get_results($statement, $format): array
    {
        if (! is_array($statement)
            || count($statement) !== 2
            || $format !== ARRAY_A
            || strpos($statement[0], 'SELECT option_value') === false
            || $statement[1] !== array('wp_user_roles')) {
            throw new RuntimeException('unexpected role persistence query');
        }
        if ($this->role_option_row_count < 1) {
            return array();
        }
        $row = array(
            'option_value' => serialize($GLOBALS['raos_stored_roles']),
        );
        return array_fill(0, $this->role_option_row_count, $row);
    }
}

function raos_persist_role_capabilities(string $role, array $capabilities): void
{
    if ($GLOBALS['raos_persist_role_writes'] !== true
        || ! isset($GLOBALS['raos_stored_roles'][$role])) {
        return;
    }
    $GLOBALS['raos_stored_roles'][$role]['capabilities'] = $capabilities;
}

function raos_seed_role(string $role, string $display, array $capabilities): void
{
    $GLOBALS['raos_roles'][$role] = new WP_Role($role, $capabilities);
    $GLOBALS['raos_stored_roles'][$role] = array(
        'name' => $display,
        'capabilities' => $capabilities,
    );
}

function raos_reset_roles(): void
{
    global $wpdb;
    $GLOBALS['raos_roles'] = array();
    $GLOBALS['raos_stored_roles'] = array();
    $GLOBALS['raos_add_role_fails'] = false;
    $GLOBALS['raos_persist_role_writes'] = true;
    $GLOBALS['raos_get_role_throws'] = false;
    $wpdb = new FakeWpdb();
}

function get_role($role)
{
    if ($GLOBALS['raos_get_role_throws'] === true) {
        throw new RuntimeException('simulated role lookup failure');
    }
    $key = (string) $role;
    return $GLOBALS['raos_roles'][$key] ?? null;
}

function add_role($role, $display_name, $capabilities)
{
    if ($GLOBALS['raos_add_role_fails'] === true) {
        return null;
    }
    $key = (string) $role;
    if (isset($GLOBALS['raos_roles'][$key]) || ! is_array($capabilities)) {
        return null;
    }
    $created = new WP_Role($key, $capabilities);
    $GLOBALS['raos_roles'][$key] = $created;
    if ($GLOBALS['raos_persist_role_writes'] === true) {
        $GLOBALS['raos_stored_roles'][$key] = array(
            'name' => (string) $display_name,
            'capabilities' => $capabilities,
        );
    }
    return $created;
}

function is_serialized($value, $strict = true): bool
{
    unset($strict);
    if (! is_string($value)) {
        return false;
    }
    if ($value === 'b:0;') {
        return true;
    }
    return @unserialize(
        $value,
        array('allowed_classes' => false)
    ) !== false;
}

function raos_assert($condition, string $message): void
{
    if ($condition !== true) {
        throw new RuntimeException($message);
    }
}

require dirname(__DIR__, 3)
    . '/changes/st-1704/publication-operator-v2/wordpress-plugin/'
    . 'raos-bounded-operator/includes/st1704-publication-controller.v2.php';

$controller = new ReflectionClass('RAOS_ST1704_Publication_Controller_V2');
$exact = $controller->getMethod('exact_draft_writer_capabilities');
$exact->setAccessible(true);
$install = $controller->getMethod('install_draft_writer_role');
$install->setAccessible(true);
$expected = array('read' => true, 'edit_posts' => true);

raos_assert($exact->invoke(null) === $expected, 'exact capabilities drifted');

raos_reset_roles();
raos_assert($install->invoke(null) === true, 'new role was not installed');
raos_assert(
    $GLOBALS['raos_roles']['raos_draft_writer']->capabilities === $expected,
    'new in-memory capabilities differ'
);
raos_assert(
    $GLOBALS['raos_stored_roles']['raos_draft_writer'] === array(
        'name' => 'RAOS Draft Writer',
        'capabilities' => $expected,
    ),
    'new persisted role differs'
);

raos_reset_roles();
$operator = array(
    'read' => true,
    'raos_operator_read' => true,
    'raos_operator_propose' => true,
    'raos_operator_apply' => true,
);
raos_seed_role('raos_operator_executor', 'RAOS Operator Executor', $operator);
raos_seed_role(
    'raos_draft_writer',
    'RAOS Draft Writer',
    array('read' => true, 'publish_posts' => true, 'upload_files' => true)
);
raos_assert($install->invoke(null) === true, 'polluted role was not normalized');
raos_assert(
    $GLOBALS['raos_roles']['raos_draft_writer']->capabilities === $expected,
    'polluted capabilities survived'
);
raos_assert(
    $GLOBALS['raos_roles']['raos_operator_executor']->capabilities === $operator,
    'operator role changed'
);

raos_reset_roles();
raos_seed_role('raos_draft_writer', 'Wrong Display', $expected);
raos_assert(
    $install->invoke(null) === false,
    'wrong persisted display was accepted'
);

raos_reset_roles();
$GLOBALS['raos_add_role_fails'] = true;
raos_assert($install->invoke(null) === false, 'creation failure was accepted');

raos_reset_roles();
$GLOBALS['raos_persist_role_writes'] = false;
raos_assert($install->invoke(null) === false, 'persistence failure was accepted');

raos_reset_roles();
raos_seed_role('raos_draft_writer', 'RAOS Draft Writer', $expected);
$wpdb->role_option_row_count = 2;
raos_assert($install->invoke(null) === false, 'duplicate option rows were accepted');

raos_reset_roles();
$GLOBALS['raos_get_role_throws'] = true;
raos_assert($install->invoke(null) === false, 'role exception was accepted');

fwrite(STDOUT, "DRAFT_WRITER_ROLE_BEHAVIOR_OK\n");
