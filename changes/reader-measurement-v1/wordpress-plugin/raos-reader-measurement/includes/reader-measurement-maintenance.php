<?php
/**
 * Maintenance ONLY. The reviewed theme may require this exact digest when the
 * plugin is inactive. No plugin bootstrap, endpoint, consent, activation or read
 * surface. Keep this file and its scheduled callback through approved rollback.
 */
defined('ABSPATH') || exit;
if (!class_exists('RAOS_Reader_Maintenance', false)) {
final class RAOS_Reader_Maintenance
{
    const DB_OPTION = 'raos_reader_measurement_db_v1';
    const HEALTH_OPTION = 'raos_reader_measurement_cleanup_v1';
    const HOOK = 'raos_reader_measurement_cleanup_v1';
    const RAW_DAYS = 30;
    const DAILY_DAYS = 90;
    private static $failed_in_process = false;

    public static function tables(): array
    {
        global $wpdb;
        return array('raw'=>$wpdb->prefix.'raos_reader_raw_v1',
                     'daily'=>$wpdb->prefix.'raos_reader_daily_v1',
                     'rate'=>$wpdb->prefix.'raos_reader_rate_v1');
    }

    public static function columns(): array
    {
        $event = array('event_date','event_name','article_id','target_article_id','journey_stage','panel_id','source_ref');
        return array('raw'=>$event, 'daily'=>array_merge($event,array('event_count')),
            'rate'=>array('bucket_key','tokens_milli','refilled_millis','budget_date','accepted_count'));
    }

    /** Refuse nontransactional, absent or unexpected storage; never auto-install. */
    public static function storage_ready(): bool
    {
        global $wpdb;
        if (get_option(self::DB_OPTION,'') !== '1.0.0') { return false; }
        $before = $wpdb->suppress_errors(true);
        try {
            $tables = self::tables();
            $rows = $wpdb->get_results($wpdb->prepare(
                'SHOW TABLE STATUS WHERE Name IN (%s, %s, %s)',
                $tables['raw'],$tables['daily'],$tables['rate']
            ), ARRAY_A);
            if (!is_array($rows) || count($rows)!==3) { return false; }
            $engines = array();
            foreach ($rows as $row) { $engines[$row['Name'] ?? ''] = $row['Engine'] ?? ''; }
            foreach ($tables as $kind=>$table) {
                if (($engines[$table] ?? null)!=='InnoDB') { return false; }
                $columns = $wpdb->get_results('SHOW COLUMNS FROM '.$table, ARRAY_A);
                if (!is_array($columns)) { return false; }
                $actual = array_column($columns,'Field'); $expected = self::columns()[$kind];
                sort($actual); sort($expected);
                if ($actual !== $expected) { return false; }
            }
            return true;
        } catch (Throwable $error) {
            return false;
        } finally {
            $wpdb->suppress_errors($before);
        }
    }

    public static function schedule(): void
    {
        if (get_option(self::DB_OPTION,'') === '1.0.0' && !wp_next_scheduled(self::HOOK)) {
            wp_schedule_event(time() + 60, 'hourly', self::HOOK);
        }
    }

    private static function today(?DateTimeImmutable $instant = null): DateTimeImmutable
    {
        return ($instant ?? new DateTimeImmutable('now'))->setTimezone(new DateTimeZone('Asia/Tokyo'))->setTime(0,0);
    }

    public static function status(?DateTimeImmutable $instant = null): array
    {
        $state = get_option(self::HEALTH_OPTION, null);
        $date = is_array($state) && is_string($state['last_success_date'] ?? null)
            && preg_match('/\A[0-9]{4}-[0-9]{2}-[0-9]{2}\z/D',$state['last_success_date']) === 1
            ? $state['last_success_date'] : null;
        $code = 'CLEANUP_STATUS_UNAVAILABLE';
        if (self::$failed_in_process) {
            $code = 'CLEANUP_FAILED';
        } elseif (!has_action(self::HOOK,'raos_reader_measurement_cleanup') || !wp_next_scheduled(self::HOOK)) {
            $code = 'MAINTENANCE_UNAVAILABLE';
        } elseif (!self::storage_ready()) {
            $code = 'STORAGE_UNAVAILABLE';
        } elseif (is_array($state) && ($state['last_error_code'] ?? null) === 'CLEANUP_FAILED') {
            $code = 'CLEANUP_FAILED';
        } elseif ($date !== self::today($instant)->format('Y-m-d')) {
            $code = 'CLEANUP_STALE';
        } elseif (($state['healthy'] ?? false) === true && ($state['last_error_code'] ?? null) === null) {
            $code = null;
        }
        return array('healthy'=>$code===null,'last_success_date'=>$date,'last_error_code'=>$code);
    }

    public static function cleanup(?DateTimeImmutable $instant = null): bool
    {
        global $wpdb;
        $prior = get_option(self::HEALTH_OPTION,array());
        $last = is_array($prior) ? ($prior['last_success_date'] ?? null) : null;
        // Persist a failure marker BEFORE deleting. A crash, rollback or failed
        // final health write must leave subsequent requests fail-closed.
        $pending = array('healthy'=>false,'last_success_date'=>$last,'last_error_code'=>'CLEANUP_FAILED');
        update_option(self::HEALTH_OPTION,$pending,false);
        if (get_option(self::HEALTH_OPTION,null) !== $pending) {
            self::$failed_in_process = true;
            return false;
        }
        $success = false;
        $before = $wpdb->suppress_errors(true);
        try {
            if (!self::storage_ready() || false === $wpdb->query('START TRANSACTION')) {
                throw new RuntimeException('unavailable');
            }
            $today = self::today($instant);
            // Calendar dates carry no event time. Delete a calendar date early
            // so regular daily maintenance stays within the advertised maxima.
            foreach (array('raw'=>self::RAW_DAYS-1, 'daily'=>self::DAILY_DAYS-1) as $kind=>$days) {
                $cutoff = $today->modify('-'.$days.' days')->format('Y-m-d');
                if (false === $wpdb->query($wpdb->prepare(
                    'DELETE FROM '.self::tables()[$kind].' WHERE event_date <= %s', $cutoff))) {
                    throw new RuntimeException('cleanup');
                }
            }
            if (false === $wpdb->query('COMMIT')) { throw new RuntimeException('commit'); }
            $last = $today->format('Y-m-d');
            $success = true;
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
        } finally {
            $wpdb->suppress_errors($before);
        }
        $state = array('healthy'=>$success,'last_success_date'=>$last,
            'last_error_code'=>$success ? null : 'CLEANUP_FAILED');
        update_option(self::HEALTH_OPTION,$state,false);
        // Failed health writes must not make intake appear healthy.
        self::$failed_in_process = !$success || get_option(self::HEALTH_OPTION,null) !== $state;
        return !self::$failed_in_process;
    }
}
function raos_reader_measurement_cleanup(): bool
{
    return RAOS_Reader_Maintenance::cleanup();
}
function raos_reader_measurement_cleanup_status(): array
{
    return RAOS_Reader_Maintenance::status();
}
add_action(RAOS_Reader_Maintenance::HOOK,'raos_reader_measurement_cleanup');
add_action('init',array('RAOS_Reader_Maintenance','schedule'),0);
}
