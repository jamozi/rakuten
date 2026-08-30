<?php
/**
 * Durable, bounded WordPress storage for consented public events.
 *
 * @package RAOS_Editorial_Measurement
 */

defined('ABSPATH') || exit;

final class RAOS_Measurement_Store
{
    const DB_VERSION = '1.1.0';
    const DB_VERSION_OPTION = 'raos_measurement_db_version_v1';
    const CLEANUP_HOOK = 'raos_measurement_cleanup_v1';
    const RAW_RETENTION_DAYS = 7;
    const AGGREGATE_RETENTION_MONTHS = 13;
    const SESSION_RATE_PER_MINUTE = 120;
    const SITE_SHORT_BUCKET_CAPACITY = 1200;
    const SITE_SHORT_REFILL_PER_SECOND = 20;
    const SITE_DAILY_CAP = 100000;
    const RATE_STATE_RETENTION_DAYS = 2;

    /** One token is stored as 1,000 integer units to retain sub-second refill. */
    const TOKEN_SCALE = 1000;

    public static function install()
    {
        global $wpdb;
        require_once ABSPATH . 'wp-admin/includes/upgrade.php';
        $charset = $wpdb->get_charset_collate();
        $raw = self::raw_table();
        $daily = self::daily_table();
        $rate = self::rate_table();
        dbDelta(
            "CREATE TABLE {$raw} (
                event_id char(36) NOT NULL,
                payload_sha256 char(64) NOT NULL,
                received_at_gmt datetime(3) NOT NULL,
                occurred_at_gmt datetime(3) NOT NULL,
                event_date date NOT NULL,
                session_sha256 char(64) NOT NULL,
                event_name varchar(48) NOT NULL,
                article_id varchar(96) NOT NULL,
                snapshot_id varchar(96) NOT NULL,
                dimensions_sha256 char(64) NOT NULL,
                dimensions_json varchar(1024) NOT NULL,
                PRIMARY KEY  (event_id),
                KEY received_at_gmt (received_at_gmt),
                KEY session_rate (session_sha256, received_at_gmt),
                KEY event_article_date (event_name, article_id, event_date)
            ) {$charset};"
        );
        dbDelta(
            "CREATE TABLE {$daily} (
                metric_date date NOT NULL,
                event_name varchar(48) NOT NULL,
                article_id varchar(96) NOT NULL,
                snapshot_id varchar(96) NOT NULL,
                dimensions_sha256 char(64) NOT NULL,
                dimensions_json varchar(1024) NOT NULL,
                event_count bigint unsigned NOT NULL DEFAULT 0,
                first_received_at_gmt datetime(3) NOT NULL,
                last_received_at_gmt datetime(3) NOT NULL,
                PRIMARY KEY  (metric_date, event_name, article_id, snapshot_id, dimensions_sha256),
                KEY article_period (article_id, metric_date),
                KEY event_period (event_name, metric_date)
            ) {$charset};"
        );
        dbDelta(
            "CREATE TABLE {$rate} (
                bucket_key varchar(48) NOT NULL,
                tokens_milli bigint unsigned NOT NULL DEFAULT 0,
                refilled_at_gmt datetime(3) NOT NULL,
                accepted_count bigint unsigned NOT NULL DEFAULT 0,
                expires_at_gmt datetime(3) NOT NULL,
                PRIMARY KEY  (bucket_key),
                KEY expires_at_gmt (expires_at_gmt)
            ) {$charset};"
        );
        update_option(self::DB_VERSION_OPTION, self::DB_VERSION, false);
        if (! wp_next_scheduled(self::CLEANUP_HOOK)) {
            wp_schedule_event(time() + HOUR_IN_SECONDS, 'daily', self::CLEANUP_HOOK);
        }
    }

    public static function maybe_upgrade()
    {
        if (get_option(self::DB_VERSION_OPTION, '') !== self::DB_VERSION) {
            self::install();
        }
    }

    public static function deactivate()
    {
        $timestamp = wp_next_scheduled(self::CLEANUP_HOOK);
        while (false !== $timestamp) {
            wp_unschedule_event($timestamp, self::CLEANUP_HOOK);
            $timestamp = wp_next_scheduled(self::CLEANUP_HOOK);
        }
    }

    public static function cleanup()
    {
        global $wpdb;
        $now = new DateTimeImmutable('now', new DateTimeZone('UTC'));
        $raw_cutoff = $now
            ->modify('-' . self::RAW_RETENTION_DAYS . ' days')
            ->format('Y-m-d H:i:s.v');
        $aggregate_cutoff = $now
            ->modify('-' . self::AGGREGATE_RETENTION_MONTHS . ' months')
            ->format('Y-m-d');
        $wpdb->query(
            $wpdb->prepare(
                'DELETE FROM ' . self::raw_table() . ' WHERE received_at_gmt < %s',
                $raw_cutoff
            )
        );
        $wpdb->query(
            $wpdb->prepare(
                'DELETE FROM ' . self::daily_table() . ' WHERE metric_date < %s',
                $aggregate_cutoff
            )
        );
        $wpdb->query(
            $wpdb->prepare(
                'DELETE FROM ' . self::rate_table() . ' WHERE expires_at_gmt < %s',
                $now->format('Y-m-d H:i:s.v')
            )
        );
    }

    /**
     * Store one validated event, returning ACCEPTED or DUPLICATE.
     * A repeated identity with different canonical bytes is a conflict.
     */
    public static function record(array $event)
    {
        global $wpdb;
        $identity_payload = $event;
        unset($identity_payload['received_at']);
        $canonical = self::canonical_json($identity_payload);
        $dimensions_json = self::canonical_json($event['dimensions']);
        if (! is_string($canonical)
            || ! is_string($dimensions_json)
            || strlen($dimensions_json) > 1024) {
            return new WP_Error(
                'raos_measurement_event_encoding_invalid',
                'The event could not be encoded.',
                array('status' => 400)
            );
        }
        $payload_sha256 = hash('sha256', $canonical);
        $dimensions_sha256 = hash('sha256', $dimensions_json);
        $session_sha256 = hash('sha256', $event['anonymous_session_id']);
        $received = self::sql_timestamp($event['received_at']);
        $occurred = self::sql_timestamp($event['occurred_at']);
        $event_date = substr($event['occurred_at'], 0, 10);
        if (! is_string($received) || ! is_string($occurred)) {
            return new WP_Error(
                'raos_measurement_event_time_invalid',
                'The event time is invalid.',
                array('status' => 400)
            );
        }
        if (false === $wpdb->query('START TRANSACTION')) {
            return self::storage_error();
        }
        $site_capacity = self::reserve_site_capacity($event['received_at']);
        if (is_wp_error($site_capacity)) {
            if ('raos_measurement_rate_limited' === $site_capacity->get_error_code()) {
                if (false === $wpdb->query('COMMIT')) {
                    $wpdb->query('ROLLBACK');
                    return self::storage_error();
                }
            } else {
                $wpdb->query('ROLLBACK');
            }
            return $site_capacity;
        }
        $rate_cutoff = (new DateTimeImmutable($event['received_at']))
            ->modify('-1 minute')
            ->format('Y-m-d H:i:s.v');
        $session_rate = $wpdb->get_var(
            $wpdb->prepare(
                'SELECT COUNT(*) FROM ' . self::raw_table()
                    . ' WHERE session_sha256 = %s AND received_at_gmt >= %s FOR UPDATE',
                $session_sha256,
                $rate_cutoff
            )
        );
        if (! is_numeric($session_rate)) {
            $wpdb->query('ROLLBACK');
            return self::storage_error();
        }
        if ((int) $session_rate >= self::SESSION_RATE_PER_MINUTE) {
            $wpdb->query('ROLLBACK');
            return self::rate_error();
        }
        $inserted = $wpdb->insert(
            self::raw_table(),
            array(
                'event_id' => $event['event_id'],
                'payload_sha256' => $payload_sha256,
                'received_at_gmt' => $received,
                'occurred_at_gmt' => $occurred,
                'event_date' => $event_date,
                'session_sha256' => $session_sha256,
                'event_name' => $event['event_name'],
                'article_id' => $event['article_id'],
                'snapshot_id' => $event['snapshot_id'],
                'dimensions_sha256' => $dimensions_sha256,
                'dimensions_json' => $dimensions_json,
            ),
            array('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s')
        );
        if (1 !== $inserted) {
            $existing = $wpdb->get_var(
                $wpdb->prepare(
                    'SELECT payload_sha256 FROM ' . self::raw_table()
                        . ' WHERE event_id = %s',
                    $event['event_id']
                )
            );
            $wpdb->query('ROLLBACK');
            if (is_string($existing) && hash_equals($existing, $payload_sha256)) {
                return array('disposition' => 'DUPLICATE');
            }
            if (! is_string($existing)) {
                return self::storage_error();
            }
            return new WP_Error(
                'raos_measurement_event_id_conflict',
                'The event identity conflicts with an existing event.',
                array('status' => 409)
            );
        }
        $aggregate = $wpdb->query(
            $wpdb->prepare(
                'INSERT INTO ' . self::daily_table()
                    . ' (metric_date, event_name, article_id, snapshot_id,'
                    . ' dimensions_sha256, dimensions_json, event_count,'
                    . ' first_received_at_gmt, last_received_at_gmt)'
                    . ' VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s)'
                    . ' ON DUPLICATE KEY UPDATE'
                    . ' event_count = event_count + 1,'
                    . ' first_received_at_gmt = LEAST(first_received_at_gmt, VALUES(first_received_at_gmt)),'
                    . ' last_received_at_gmt = GREATEST(last_received_at_gmt, VALUES(last_received_at_gmt))',
                $event_date,
                $event['event_name'],
                $event['article_id'],
                $event['snapshot_id'],
                $dimensions_sha256,
                $dimensions_json,
                $received,
                $received
            )
        );
        if (false === $aggregate) {
            $wpdb->query('ROLLBACK');
            return new WP_Error(
                'raos_measurement_aggregate_failed',
                'The event aggregate could not be updated.',
                array('status' => 503)
            );
        }
        if (false === $wpdb->query('COMMIT')) {
            $wpdb->query('ROLLBACK');
            return self::storage_error();
        }
        return array('disposition' => 'ACCEPTED');
    }

    /**
     * Atomically reserve one event from the site-wide short and daily budgets.
     *
     * The caller must hold a database transaction. The two rows are locked in
     * lexical order, so rotating anonymous session UUIDs cannot create fresh
     * site capacity. No network or browser identity is read or persisted.
     */
    private static function reserve_site_capacity($received_at)
    {
        global $wpdb;
        try {
            $instant = (new DateTimeImmutable($received_at))
                ->setTimezone(new DateTimeZone('UTC'));
        } catch (Exception $error) {
            return self::storage_error();
        }
        $now = $instant->format('Y-m-d H:i:s.v');
        $short_key = 'site-short-v1';
        $daily_key = 'site-day-v1:' . $instant->format('Ymd');
        $short_expiry = $instant
            ->modify('+' . self::RATE_STATE_RETENTION_DAYS . ' days')
            ->format('Y-m-d H:i:s.v');
        $daily_expiry = $instant
            ->setTime(0, 0)
            ->modify('+' . (self::RATE_STATE_RETENTION_DAYS + 1) . ' days')
            ->format('Y-m-d H:i:s.v');
        $short_capacity_milli = self::SITE_SHORT_BUCKET_CAPACITY * self::TOKEN_SCALE;
        $insert_daily = $wpdb->query(
            $wpdb->prepare(
                'INSERT INTO ' . self::rate_table()
                    . ' (bucket_key, tokens_milli, refilled_at_gmt, accepted_count, expires_at_gmt)'
                    . ' VALUES (%s, 0, %s, 0, %s)'
                    . ' ON DUPLICATE KEY UPDATE bucket_key = VALUES(bucket_key)',
                $daily_key,
                $now,
                $daily_expiry
            )
        );
        $insert_short = $wpdb->query(
            $wpdb->prepare(
                'INSERT INTO ' . self::rate_table()
                    . ' (bucket_key, tokens_milli, refilled_at_gmt, accepted_count, expires_at_gmt)'
                    . ' VALUES (%s, %d, %s, 0, %s)'
                    . ' ON DUPLICATE KEY UPDATE bucket_key = VALUES(bucket_key)',
                $short_key,
                $short_capacity_milli,
                $now,
                $short_expiry
            )
        );
        if (false === $insert_short || false === $insert_daily) {
            return self::storage_error();
        }
        $rows = $wpdb->get_results(
            $wpdb->prepare(
                'SELECT bucket_key, tokens_milli, refilled_at_gmt, accepted_count'
                    . ' FROM ' . self::rate_table()
                    . ' WHERE bucket_key IN (%s, %s)'
                    . ' ORDER BY bucket_key ASC FOR UPDATE',
                $daily_key,
                $short_key
            ),
            ARRAY_A
        );
        if (! is_array($rows) || 2 !== count($rows)) {
            return self::storage_error();
        }
        $by_key = array();
        foreach ($rows as $row) {
            if (! is_array($row)
                || ! isset(
                    $row['bucket_key'],
                    $row['tokens_milli'],
                    $row['refilled_at_gmt'],
                    $row['accepted_count']
                )
                || ! is_string($row['bucket_key'])
                || ! is_string($row['refilled_at_gmt'])
                || isset($by_key[$row['bucket_key']])) {
                return self::storage_error();
            }
            $by_key[$row['bucket_key']] = $row;
        }
        if (! isset($by_key[$short_key], $by_key[$daily_key])) {
            return self::storage_error();
        }
        $short = $by_key[$short_key];
        $daily = $by_key[$daily_key];
        $tokens_milli = self::bounded_database_integer(
            $short['tokens_milli'],
            $short_capacity_milli
        );
        $daily_count = self::bounded_database_integer(
            $daily['accepted_count'],
            self::SITE_DAILY_CAP
        );
        if (! is_int($tokens_milli) || ! is_int($daily_count)) {
            return self::storage_error();
        }
        $elapsed_milliseconds = self::elapsed_milliseconds(
            $short['refilled_at_gmt'],
            $instant
        );
        if (! is_int($elapsed_milliseconds)) {
            return self::storage_error();
        }
        $full_refill_milliseconds = (int) ceil(
            (self::SITE_SHORT_BUCKET_CAPACITY / self::SITE_SHORT_REFILL_PER_SECOND)
                * 1000
        );
        $bounded_elapsed = min($elapsed_milliseconds, $full_refill_milliseconds);
        $tokens_milli = min(
            $short_capacity_milli,
            $tokens_milli + ($bounded_elapsed * self::SITE_SHORT_REFILL_PER_SECOND)
        );
        if ($daily_count >= self::SITE_DAILY_CAP
            || $tokens_milli < self::TOKEN_SCALE) {
            $normalized = $wpdb->query(
                $wpdb->prepare(
                    'UPDATE ' . self::rate_table()
                        . ' SET tokens_milli = %d, refilled_at_gmt = %s, expires_at_gmt = %s'
                        . ' WHERE bucket_key = %s',
                    $tokens_milli,
                    $now,
                    $short_expiry,
                    $short_key
                )
            );
            if (false === $normalized) {
                return self::storage_error();
            }
            return self::rate_error();
        }
        $short_updated = $wpdb->query(
            $wpdb->prepare(
                'UPDATE ' . self::rate_table()
                    . ' SET tokens_milli = %d, refilled_at_gmt = %s, expires_at_gmt = %s'
                    . ' WHERE bucket_key = %s',
                $tokens_milli - self::TOKEN_SCALE,
                $now,
                $short_expiry,
                $short_key
            )
        );
        $daily_updated = $wpdb->query(
            $wpdb->prepare(
                'UPDATE ' . self::rate_table()
                    . ' SET accepted_count = accepted_count + 1,'
                    . ' refilled_at_gmt = %s, expires_at_gmt = %s'
                    . ' WHERE bucket_key = %s AND accepted_count < %d',
                $now,
                $daily_expiry,
                $daily_key,
                self::SITE_DAILY_CAP
            )
        );
        if (1 !== $short_updated || 1 !== $daily_updated) {
            return self::storage_error();
        }
        return true;
    }

    /** Return aggregates only; raw events and session hashes are never exposed. */
    public static function aggregate_report(array $input)
    {
        global $wpdb;
        $where = array('metric_date >= %s', 'metric_date <= %s');
        $arguments = array($input['start_date'], $input['end_date']);
        if (isset($input['article_id'])) {
            $where[] = 'article_id = %s';
            $arguments[] = $input['article_id'];
        }
        if (isset($input['event_names'])) {
            $placeholders = implode(', ', array_fill(0, count($input['event_names']), '%s'));
            $where[] = 'event_name IN (' . $placeholders . ')';
            foreach ($input['event_names'] as $name) {
                $arguments[] = $name;
            }
        }
        $offset = ($input['page'] - 1) * $input['per_page'];
        $arguments[] = $input['per_page'];
        $arguments[] = $offset;
        $sql = 'SELECT metric_date, event_name, article_id, snapshot_id,'
            . ' dimensions_json, event_count, first_received_at_gmt, last_received_at_gmt'
            . ' FROM ' . self::daily_table()
            . ' WHERE ' . implode(' AND ', $where)
            . ' ORDER BY metric_date ASC, article_id ASC, event_name ASC, dimensions_sha256 ASC'
            . ' LIMIT %d OFFSET %d';
        $rows = $wpdb->get_results($wpdb->prepare($sql, $arguments), ARRAY_A);
        if (! is_array($rows)) {
            return new WP_Error(
                'raos_measurement_aggregate_unavailable',
                'The aggregate report is unavailable.',
                array('status' => 503)
            );
        }
        $output = array();
        foreach ($rows as $row) {
            $dimensions = json_decode($row['dimensions_json'], true, 16);
            if (! is_array($dimensions)) {
                return new WP_Error(
                    'raos_measurement_aggregate_corrupt',
                    'The aggregate report is corrupt.',
                    array('status' => 500)
                );
            }
            $output[] = array(
                'metric_date' => $row['metric_date'],
                'event_name' => $row['event_name'],
                'article_id' => $row['article_id'],
                'snapshot_id' => $row['snapshot_id'],
                'dimensions' => $dimensions,
                'event_count' => (int) $row['event_count'],
                'first_received_at_gmt' => self::rfc3339($row['first_received_at_gmt']),
                'last_received_at_gmt' => self::rfc3339($row['last_received_at_gmt']),
            );
        }
        return $output;
    }

    private static function raw_table()
    {
        global $wpdb;
        return $wpdb->prefix . 'raos_measurement_event_v1';
    }

    private static function daily_table()
    {
        global $wpdb;
        return $wpdb->prefix . 'raos_measurement_daily_v1';
    }

    private static function rate_table()
    {
        global $wpdb;
        return $wpdb->prefix . 'raos_measurement_rate_v1';
    }

    private static function elapsed_milliseconds($stored, DateTimeImmutable $instant)
    {
        try {
            $before = (new DateTimeImmutable($stored, new DateTimeZone('UTC')))
                ->setTimezone(new DateTimeZone('UTC'));
        } catch (Exception $error) {
            return null;
        }
        $before_milliseconds = ((int) $before->format('U') * 1000)
            + (int) $before->format('v');
        $instant_milliseconds = ((int) $instant->format('U') * 1000)
            + (int) $instant->format('v');
        return max(0, $instant_milliseconds - $before_milliseconds);
    }

    private static function bounded_database_integer($value, $maximum)
    {
        if (is_int($value)) {
            return $value >= 0 && $value <= $maximum ? $value : null;
        }
        if (! is_string($value)
            || strlen($value) > 10
            || preg_match('/\A(?:0|[1-9]\d*)\z/D', $value) !== 1) {
            return null;
        }
        $normalized = (int) $value;
        return $normalized <= $maximum ? $normalized : null;
    }

    private static function rate_error()
    {
        return new WP_Error(
            'raos_measurement_rate_limited',
            'The event rate limit was reached.',
            array('status' => 429)
        );
    }

    private static function storage_error()
    {
        return new WP_Error(
            'raos_measurement_storage_unavailable',
            'The measurement store is unavailable.',
            array('status' => 503)
        );
    }

    private static function sql_timestamp($value)
    {
        try {
            return (new DateTimeImmutable($value))
                ->setTimezone(new DateTimeZone('UTC'))
                ->format('Y-m-d H:i:s.v');
        } catch (Exception $error) {
            return null;
        }
    }

    private static function rfc3339($value)
    {
        try {
            return (new DateTimeImmutable($value, new DateTimeZone('UTC')))
                ->format('Y-m-d\TH:i:s.v\Z');
        } catch (Exception $error) {
            return null;
        }
    }

    private static function canonical_json($value)
    {
        $normalized = self::sort_recursive($value);
        $encoded = wp_json_encode(
            $normalized,
            JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE
                | JSON_PRESERVE_ZERO_FRACTION
        );
        return is_string($encoded) ? $encoded : null;
    }

    private static function sort_recursive($value)
    {
        if (! is_array($value)) {
            return $value;
        }
        if (array_keys($value) !== range(0, count($value) - 1)) {
            ksort($value, SORT_STRING);
        }
        foreach ($value as $key => $child) {
            $value[$key] = self::sort_recursive($child);
        }
        return $value;
    }
}
