<?php
/** Strict wpdb boundary with transaction snapshots and fault injection.
 * SQL semantics/concurrent transaction verification also run against MariaDB.
 */
class ReaderDB {
    public $prefix='wp_'; public $raw=[]; public $daily=[]; public $rate=null;
    public $failure=null; public $engine='InnoDB'; public $extra_column=false;
    public $queries=[]; public $transaction=null; public $last_error='';
    private $suppressed=false;
    public function suppress_errors($value=true){$old=$this->suppressed;$this->suppressed=$value;return $old;}
    public function get_charset_collate(){return 'DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin';}
    public function prepare($sql,...$args){
        if(count($args)===1 && is_array($args[0]))$args=$args[0];
        expect(preg_match_all('/%[sd]/',$sql)===count($args),'placeholder mismatch: '.$sql);
        return ['sql'=>$sql,'args'=>$args];
    }
    private function unpack($q){return is_array($q)?[$q['sql'],$q['args']]:[$q,[]];}
    public function query($q){
        [$sql,$args]=$this->unpack($q);$this->queries[]=$sql;
        if($this->failure && str_contains($sql,$this->failure))return false;
        if(str_starts_with($sql,'CREATE TABLE wp_raos_reader_'))return 0;
        if($sql==='START TRANSACTION'){
            expect($this->transaction===null,'nested transaction');
            $this->transaction=[$this->raw,$this->daily,$this->rate];return 0;
        }
        if($sql==='ROLLBACK'){
            if($this->transaction!==null){[$this->raw,$this->daily,$this->rate]=$this->transaction;$this->transaction=null;}
            return 0;
        }
        if($sql==='COMMIT'){expect($this->transaction!==null,'commit without transaction');$this->transaction=null;return 0;}
        if(str_starts_with($sql,'INSERT INTO wp_raos_reader_rate_v1')){
            expect($this->transaction!==null,'rate initialization must be in transaction');
            if($this->rate===null)$this->rate=['bucket_key'=>$args[0],'tokens_milli'=>$args[1],'refilled_millis'=>$args[2],'budget_date'=>$args[3],'accepted_count'=>0];
            return 1;
        }
        if(str_starts_with($sql,'UPDATE wp_raos_reader_rate_v1')){
            expect($this->transaction!==null,'rate write must be in transaction');
            expect($args[4]==='site','one site bucket only');
            $this->rate=['bucket_key'=>'site','tokens_milli'=>$args[0],'refilled_millis'=>$args[1],'budget_date'=>$args[2],'accepted_count'=>$args[3]];return 1;
        }
        if(str_starts_with($sql,'INSERT INTO wp_raos_reader_daily_v1')){
            expect(str_ends_with($sql,'ON DUPLICATE KEY UPDATE event_count=event_count+1'),'counts must increment');
            expect($this->transaction!==null,'aggregate must be in transaction');
            $key=json_encode($args);
            $this->daily[$key]=($this->daily[$key]??0)+1;return 1;
        }
        if(preg_match('/^DELETE FROM wp_raos_reader_(raw|daily)_v1 WHERE event_date <= %s$/',$sql,$m)){
            if($m[1]==='raw')$this->raw=array_values(array_filter($this->raw,fn($e)=>$e['event_date']>$args[0]));
            else foreach($this->daily as $key=>$count){if(json_decode($key,true)[0]<=$args[0])unset($this->daily[$key]);}
            return 1;
        }
        throw new RuntimeException('unhandled query '.$sql);
    }
    public function insert($table,$data,$formats){
        if($this->failure==='raw')return false;
        expect($table==='wp_raos_reader_raw_v1','only owned raw table inserted');
        expect($this->transaction!==null,'raw must be in transaction');
        expect(count($formats)===count($data),'format mismatch');
        $this->raw[]=$data;return 1;
    }
    public function get_results($q,$format){
        [$sql,$args]=$this->unpack($q);
        if($this->failure==='schema')return null;
        if(str_starts_with($sql,'SHOW TABLE STATUS WHERE Name IN ')){
            return array_map(fn($name)=>['Name'=>$name,'Engine'=>$this->engine],$args);
        }
        if(preg_match('/^SHOW COLUMNS FROM wp_raos_reader_(raw|daily|rate)_v1$/',$sql,$m)){
            $fields=RAOS_Reader_Maintenance::columns()[$m[1]];
            if($this->extra_column)$fields[]='session_id';
            return array_map(fn($field)=>['Field'=>$field],$fields);
        }
        if(str_starts_with($sql,'SELECT event_date,event_name,article_id,target_article_id,journey_stage,panel_id,source_ref,event_count FROM wp_raos_reader_daily_v1')){
            $result=[];
            foreach($this->daily as $key=>$count){$result[]=array_combine(RAOS_Reader_Maintenance::columns()['raw'],json_decode($key,true))+['event_count'=>$count];}
            return array_slice($result,$args[0],100);
        }
        throw new RuntimeException('unhandled results '.$sql);
    }
    public function get_row($q,$format){
        [$sql,$args]=$this->unpack($q);
        expect(str_ends_with($sql,'WHERE bucket_key=%s FOR UPDATE'),'rate locking required');
        expect($this->transaction!==null,'lock outside transaction');
        return $this->failure==='lock'?null:$this->rate;
    }
}
$GLOBALS['wpdb']=new ReaderDB();
