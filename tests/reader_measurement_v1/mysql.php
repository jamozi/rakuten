<?php
/** Ephemeral MariaDB container only; no host DB or network endpoint accepted. */
require __DIR__.'/wp.php';
final class ReaderMysqlDB {
    public $prefix='wp_'; public $failure=null; public $last_error=''; private $db; private $suppressed=false;
    public function __construct(){
        mysqli_report(MYSQLI_REPORT_ERROR|MYSQLI_REPORT_STRICT);
        $this->db=new mysqli('127.0.0.1','root','','raos_reader_test');
        $this->db->set_charset('utf8mb4');
    }
    public function suppress_errors($s=true){$p=$this->suppressed;$this->suppressed=$s;return $p;}
    public function get_charset_collate(){return 'DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin';}
    public function prepare($sql,...$args){
        if(count($args)===1 && is_array($args[0]))$args=$args[0];
        $index=0;
        $sql=preg_replace_callback('/%[sd]/',function($m)use(&$index,$args){$v=$args[$index++];return $m[0]==='%d'?(string)(int)$v:"'".$this->db->real_escape_string($v)."'";},$sql);
        expect($index===count($args),'SQL parameter mismatch');
        return $sql;
    }
    public function query($sql){
        if($this->failure!==null && str_contains($sql,$this->failure))return false;
        try{$result=$this->db->query($sql);return $result===true?$this->db->affected_rows:$result;}
        catch(mysqli_sql_exception $e){$this->last_error='fixture sql failure';return false;}
    }
    public function insert($table,$row,$formats){
        return $this->query($this->prepare('INSERT INTO '.$table.' ('.implode(',',array_keys($row)).') VALUES ('.implode(',',array_fill(0,count($row),'%s')).')',array_values($row)));
    }
    public function get_results($sql,$format){
        $result=$this->query($sql);
        return $result instanceof mysqli_result ? $result->fetch_all(MYSQLI_ASSOC) : null;
    }
    public function get_row($sql,$format){$rows=$this->get_results($sql,$format);return $rows[0]??null;}
    public function totals(){
        return [
            (int)$this->get_row('SELECT COUNT(*) n FROM wp_raos_reader_raw_v1',ARRAY_A)['n'],
            (int)$this->get_row('SELECT COALESCE(SUM(event_count),0) n FROM wp_raos_reader_daily_v1',ARRAY_A)['n'],
            (int)($this->get_row("SELECT accepted_count n FROM wp_raos_reader_rate_v1 WHERE bucket_key='site'",ARRAY_A)['n']??0),
        ];
    }
}
$wpdb=new ReaderMysqlDB();
$plugin=dirname(__DIR__,2).'/changes/reader-measurement-v1/wordpress-plugin/raos-reader-measurement';
require $plugin.'/includes/class-reader-contract.php';
require $plugin.'/includes/reader-measurement-maintenance.php';
require $plugin.'/includes/class-reader-store.php';
$contract=RAOS_Reader_Contract::load($plugin.'/config/reader-allowlist.v1.json');
$instant=new DateTimeImmutable('2026-09-06T12:00:00Z');
$GLOBALS['options'][RAOS_Reader_Maintenance::DB_OPTION]='1.0.0';
RAOS_Reader_Maintenance::schedule();
$GLOBALS['options'][RAOS_Reader_Maintenance::HEALTH_OPTION]=['healthy'=>true,'last_success_date'=>'2026-09-06','last_error_code'=>null];
$event=['event_name'=>'official_reference_open','article_id'=>'st1703-first-suitcase-comparison','source_ref'=>'SRC-PROTECA-TRI-AIR-01541'];
$mode=$argv[1]??'';
if($mode==='setup'){
    expect(RAOS_Reader_Store::install(),'production DDL installation on ephemeral db');
    expect(RAOS_Reader_Maintenance::storage_ready(),'real InnoDB and column validation');
    echo "mysql setup OK\n";
} elseif($mode==='record'){
    $accepted=0;$limited=0;
    for($i=0;$i<200;$i++){
        $result=RAOS_Reader_Store::record($event,$contract,$instant);
        if($result===true)$accepted++;
        elseif(is_wp_error($result) && $result->get_error_code()==='raos_reader_rate_limited')$limited++;
        else throw new RuntimeException('unexpected store failure');
    }
    echo json_encode(['accepted'=>$accepted,'limited'=>$limited])."\n";
} elseif($mode==='verify'){
    expect($wpdb->totals()===[1200,1200,1200],'concurrent site-wide cap and atomic counts');
    $wpdb->query("UPDATE wp_raos_reader_rate_v1 SET tokens_milli=1200000");
    $before=$wpdb->totals();$wpdb->failure='INSERT INTO wp_raos_reader_daily';
    expect(is_wp_error(RAOS_Reader_Store::record($event,$contract,$instant)),'aggregate storage failure refused');
    $wpdb->failure=null;
    expect($wpdb->totals()===$before,'real transaction raw+rate rollback');
    expect(RAOS_Reader_Store::record($event,$contract,$instant)===true,'successful transaction');
    expect($wpdb->totals()===[1201,1201,1201],'one raw and daily increment');
    $columns=$wpdb->get_results('SHOW COLUMNS FROM wp_raos_reader_raw_v1',ARRAY_A);
    expect(array_column($columns,'Field')===['event_date','event_name','article_id','target_article_id','journey_stage','panel_id','source_ref'],'no IDs, timestamps or visitor dimensions in actual schema');
    expect(RAOS_Reader_Maintenance::cleanup($instant->modify('+90 days')),'real cleanup executes');
    expect($wpdb->totals()[0]===0 && $wpdb->totals()[1]===0,'raw and daily retention on real database');
    echo "mysql transaction behavior OK\n";
} else throw new RuntimeException('simulation mode required');
