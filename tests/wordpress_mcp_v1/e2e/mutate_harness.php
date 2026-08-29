<?php
/** Force a content precondition drift in the disposable E2E site. */

defined('ABSPATH') || exit;

if (! isset($args) || ! is_array($args) || 1 !== count($args) || ! ctype_digit((string) $args[0])) {
    fwrite(STDERR, "RAOS_E2E_MUTATION_ARGUMENT_INVALID\n");
    exit(64);
}

$updated = wp_update_post(
    array(
        'ID' => (int) $args[0],
        'post_title' => 'Concurrent E2E mutation',
    ),
    true
);
if (is_wp_error($updated)) {
    fwrite(STDERR, "RAOS_E2E_MUTATION_FAILED\n");
    exit(65);
}
