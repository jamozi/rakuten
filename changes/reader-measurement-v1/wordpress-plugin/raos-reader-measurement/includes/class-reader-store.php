<?php
defined('ABSPATH') || exit;

/** Dedicated storage, all three writes in one site-wide serialized transaction. */
final class RAOS_Reader_Store
{
    const BURST = 1200;
    const REFILL = 20;
    const DAILY_CAP = 100000;

    public static function install(): bool
    {
        global $wpdb;
        require_once ABSPATH.'wp-admin/includes/upgrade.php';
        $tables = RAOS_Reader_Maintenance::tables();
        $charset = $wpdb->get_charset_collate();
        $before = $wpdb->suppress_errors(true);
        try {
            dbDelta("CREATE TABLE {$tables['raw']} (
                event_date date NOT NULL,
                event_name varchar(24) NOT NULL,
                article_id varchar(96) NOT NULL,
                target_article_id varchar(96) DEFAULT NULL,
                journey_stage varchar(8) DEFAULT NULL,
                panel_id varchar(96) DEFAULT NULL,
                source_ref varchar(96) DEFAULT NULL,
                KEY event_date (event_date)
            ) ENGINE=InnoDB {$charset};");
            dbDelta("CREATE TABLE {$tables['daily']} (
                event_date date NOT NULL,
                event_name varchar(24) NOT NULL,
                article_id varchar(96) NOT NULL,
                target_article_id varchar(96) NOT NULL DEFAULT '',
                journey_stage varchar(8) NOT NULL DEFAULT '',
                panel_id varchar(96) NOT NULL DEFAULT '',
                source_ref varchar(96) NOT NULL DEFAULT '',
                event_count bigint unsigned NOT NULL DEFAULT 0,
                PRIMARY KEY  (event_date,event_name,article_id,target_article_id,journey_stage,panel_id,source_ref)
            ) ENGINE=InnoDB {$charset};");
            dbDelta("CREATE TABLE {$tables['rate']} (
                bucket_key varchar(8) NOT NULL,
                tokens_milli bigint unsigned NOT NULL,
                refilled_millis bigint unsigned NOT NULL,
                budget_date date NOT NULL,
                accepted_count bigint unsigned NOT NULL,
                PRIMARY KEY  (bucket_key)
            ) ENGINE=InnoDB {$charset};");
            update_option(RAOS_Reader_Maintenance::DB_OPTION,'1.0.0',false);
            if (!RAOS_Reader_Maintenance::storage_ready()) { return false; }
            RAOS_Reader_Maintenance::schedule();
            return RAOS_Reader_Maintenance::cleanup();
        } finally { $wpdb->suppress_errors($before); }
    }

    private static function error(string $code, int $status=503): WP_Error
    {
        return new WP_Error('raos_reader_'.$code,'Reader measurement unavailable.',array('status'=>$status));
    }

    private static function integer($value, int $max): ?int
    {
        if (!is_int($value) && (!is_string($value) || preg_match('/\A(?:0|[1-9][0-9]{0,15})\z/D',$value)!==1)) { return null; }
        $number=(int)$value;
        return $number>=0 && $number<=$max ? $number : null;
    }

    public static function record(array $event, RAOS_Reader_Contract $contract, ?DateTimeImmutable $instant=null, ?callable $guard=null)
    {
        global $wpdb;
        $instant=$instant ?? new DateTimeImmutable('now');
        // Revalidate at storage boundary: no caller-supplied event date survives.
        unset($event['event_date']);
        try { $event=$contract->validate_event($event,$instant); }
        catch (InvalidArgumentException $error) { return self::error('event_invalid',400); }
        if (!RAOS_Reader_Maintenance::status($instant)['healthy']) { return self::error('cleanup_unavailable'); }
        $tables=RAOS_Reader_Maintenance::tables();
        $now=(int)$instant->format('U')*1000+(int)$instant->format('v');
        $before=$wpdb->suppress_errors(true);
        $active=false;
        try {
            if (false===$wpdb->query('START TRANSACTION')) { throw new RuntimeException('storage'); }
            $active=true;
            if (false===$wpdb->query($wpdb->prepare(
                'INSERT INTO '.$tables['rate'].' (bucket_key,tokens_milli,refilled_millis,budget_date,accepted_count)'
                .' VALUES (%s,%d,%d,%s,0) ON DUPLICATE KEY UPDATE bucket_key=VALUES(bucket_key)',
                'site',self::BURST*1000,$now,$event['event_date']))) { throw new RuntimeException('storage'); }
            $rate=$wpdb->get_row($wpdb->prepare(
                'SELECT bucket_key,tokens_milli,refilled_millis,budget_date,accepted_count FROM '.$tables['rate']
                .' WHERE bucket_key=%s FOR UPDATE','site'),ARRAY_A);
            if (!is_array($rate) || ($rate['bucket_key']??null)!=='site') { throw new RuntimeException('storage'); }
            $tokens=self::integer($rate['tokens_milli']??null,self::BURST*1000);
            $refilled=self::integer($rate['refilled_millis']??null,PHP_INT_MAX);
            $count=self::integer($rate['accepted_count']??null,self::DAILY_CAP);
            if ($tokens===null || $refilled===null || $count===null || $refilled>$now
                || !is_string($rate['budget_date']??null) || $rate['budget_date']>$event['event_date']
                || preg_match('/\A[0-9]{4}-[0-9]{2}-[0-9]{2}\z/D',$rate['budget_date'])!==1) {
                throw new RuntimeException('storage');
            }
            $tokens=min(self::BURST*1000,$tokens+min(60000,$now-$refilled)*self::REFILL);
            if ($rate['budget_date']!==$event['event_date']) { $count=0; }
            if ($tokens<1000 || $count>=self::DAILY_CAP) {
                $wpdb->query('ROLLBACK');$active=false;
                return self::error('rate_limited',429);
            }
            if ($guard!==null && $guard()!==true) {
                $wpdb->query('ROLLBACK');$active=false;
                return self::error('disabled',404);
            }
            if (1!==$wpdb->query($wpdb->prepare(
                'UPDATE '.$tables['rate'].' SET tokens_milli=%d,refilled_millis=%d,budget_date=%s,accepted_count=%d WHERE bucket_key=%s',
                $tokens-1000,$now,$event['event_date'],$count+1,'site'))) { throw new RuntimeException('storage'); }
            if (1!==$wpdb->insert($tables['raw'],$event,array_fill(0,count($event),'%s'))) { throw new RuntimeException('storage'); }
            $dimensions=array();
            foreach (RAOS_Reader_Maintenance::columns()['raw'] as $key) { $dimensions[]=$event[$key]??''; }
            if (false===$wpdb->query($wpdb->prepare(
                'INSERT INTO '.$tables['daily'].' (event_date,event_name,article_id,target_article_id,journey_stage,panel_id,source_ref,event_count)'
                .' VALUES (%s,%s,%s,%s,%s,%s,%s,1) ON DUPLICATE KEY UPDATE event_count=event_count+1',
                $dimensions))) { throw new RuntimeException('storage'); }
            if (false===$wpdb->query('COMMIT')) { throw new RuntimeException('storage'); }
            $active=false;
            return true;
        } catch (Throwable $error) {
            if($active){$wpdb->query('ROLLBACK');}
            return self::error('storage_unavailable');
        } finally { $wpdb->suppress_errors($before); }
    }

    /** Only wp-admin manage_options; no REST/MCP/raw-data reporting surface. */
    public static function report(int $page=1)
    {
        global $wpdb;
        if (!is_admin() || !current_user_can('manage_options') || wp_doing_ajax()
            || wp_doing_cron() || (defined('REST_REQUEST') && REST_REQUEST)) {
            return self::error('report_forbidden',403);
        }
        if (!RAOS_Reader_Maintenance::status()['healthy']) { return self::error('cleanup_unavailable'); }
        $page=max(1,min(10000,$page));
        $before=$wpdb->suppress_errors(true);
        try {
            $rows=$wpdb->get_results($wpdb->prepare(
                'SELECT event_date,event_name,article_id,target_article_id,journey_stage,panel_id,source_ref,event_count FROM '
                .RAOS_Reader_Maintenance::tables()['daily']
                .' ORDER BY event_date DESC,event_name,article_id,target_article_id,journey_stage,panel_id,source_ref LIMIT 100 OFFSET %d',
                ($page-1)*100),ARRAY_A);
            return is_array($rows) ? $rows : self::error('storage_unavailable');
        } finally { $wpdb->suppress_errors($before); }
    }
}
