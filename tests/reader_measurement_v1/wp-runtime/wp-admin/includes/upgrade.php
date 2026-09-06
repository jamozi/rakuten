<?php
// Offline fixture only: execute production DDL against the test wpdb boundary.
function dbDelta($sql) {
    global $wpdb;
    return $wpdb->query($sql);
}
