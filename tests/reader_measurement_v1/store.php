<?php
require __DIR__.'/wp.php';
require __DIR__.'/store-double.php';
$root=dirname(__DIR__,2);
$plugin=$root.'/changes/reader-measurement-v1/wordpress-plugin/raos-reader-measurement';
require $plugin.'/includes/class-reader-contract.php';
require $plugin.'/includes/reader-measurement-maintenance.php';
require $plugin.'/includes/class-reader-store.php';
$contract=RAOS_Reader_Contract::load($plugin.'/config/reader-allowlist.v1.json');
$instant=new DateTimeImmutable('2026-09-06T14:59:59Z');
$GLOBALS['options'][RAOS_Reader_Maintenance::DB_OPTION]='1.0.0';
RAOS_Reader_Maintenance::schedule();
expect(RAOS_Reader_Maintenance::cleanup($instant),'cleanup initializes health');
$event=['event_name'=>'decision_check_open','article_id'=>'st1703-first-suitcase-comparison','panel_id'=>'reader-evidence'];
for($i=0;$i<1200;$i++)expect(RAOS_Reader_Store::record($event,$contract,$instant)===true,'burst capacity '.$i);
expect(RAOS_Reader_Store::record($event,$contract,$instant)->get_error_code()==='raos_reader_rate_limited','1201st refused');
expect(count($wpdb->raw)===1200 && array_sum($wpdb->daily)===1200 && $wpdb->rate['accepted_count']===1200,'atomic counts');
expect(array_keys($wpdb->raw[0])===['event_name','article_id','panel_id','event_date'],'raw stores only exact event fields and date');
$second=$instant->modify('+1 second');
RAOS_Reader_Maintenance::cleanup($second);
for($i=0;$i<20;$i++)expect(RAOS_Reader_Store::record($event,$contract,$second)===true,'refill/JST reset');
expect(RAOS_Reader_Store::record($event,$contract,$second)->get_error_code()==='raos_reader_rate_limited','only20refill');
expect($wpdb->rate['budget_date']==='2026-09-07' && $wpdb->rate['accepted_count']===20,'JST daily reset');
$wpdb->rate['accepted_count']=100000;
expect(RAOS_Reader_Store::record($event,$contract,$second->modify('+60 seconds'))->get_error_code()==='raos_reader_rate_limited','daily cap');
$wpdb->rate['accepted_count']=1;$wpdb->rate['tokens_milli']=1200000;
$before=[$wpdb->raw,$wpdb->daily,$wpdb->rate];
foreach(['raw','INSERT INTO wp_raos_reader_daily','UPDATE wp_raos_reader_rate','COMMIT','lock'] as $failure){
    $wpdb->failure=$failure;
    expect(is_wp_error(RAOS_Reader_Store::record($event,$contract,$second)),'storage failure refuses');
    expect([$wpdb->raw,$wpdb->daily,$wpdb->rate]===$before,'rollback prevents partial acceptance');
}
$wpdb->failure=null;
expect(is_wp_error(RAOS_Reader_Store::record($event,$contract,$second,fn()=>false)),'gate changed under lock');
expect([$wpdb->raw,$wpdb->daily,$wpdb->rate]===$before,'gate refusal no reservation');
$wpdb->engine='MyISAM';
expect(is_wp_error(RAOS_Reader_Store::record($event,$contract,$second)),'nontransactional refused');
$wpdb->engine='InnoDB';$wpdb->extra_column=true;
expect(is_wp_error(RAOS_Reader_Store::record($event,$contract,$second)),'unexpected identifying column refused');
$wpdb->extra_column=false;
$wpdb->failure='DELETE';
expect(!RAOS_Reader_Maintenance::cleanup($second),'cleanup failure observed');
expect(RAOS_Reader_Maintenance::status($second)['last_error_code']==='CLEANUP_FAILED','cleanup failure observable');
$wpdb->failure=null;
expect(is_wp_error(RAOS_Reader_Store::record($event,$contract,$second)),'failed cleanup blocks intake until succeeds');
expect(RAOS_Reader_Maintenance::cleanup($second),'cleanup recovers');
expect(RAOS_Reader_Store::record($event,$contract,$second)===true,'recovered cleanup permits');
expect(!RAOS_Reader_Maintenance::status($second->modify('+1 day'))['healthy'],'stale JST cleanup refused');
unset($GLOBALS['schedule'][RAOS_Reader_Maintenance::HOOK]);
expect(RAOS_Reader_Maintenance::status($second)['last_error_code']==='MAINTENANCE_UNAVAILABLE','absent runner never healthy');
RAOS_Reader_Maintenance::schedule();
$wpdb->raw=[
    $event+['event_date'=>'2026-08-08'],
    $event+['event_date'=>'2026-08-09'],
    $event+['event_date'=>'2026-08-10'],
];
$wpdb->daily=[];
foreach(['2026-06-09','2026-06-10','2026-06-11'] as $day)$wpdb->daily[json_encode([$day,'decision_check_open',$event['article_id'],'','','reader-evidence',''])]=5;
expect(RAOS_Reader_Maintenance::cleanup(new DateTimeImmutable('2026-09-06T16:00:00Z')),'retention with collection OFF');
expect(array_column($wpdb->raw,'event_date')===['2026-08-10'],'raw conservative max30days');
expect(count($wpdb->daily)===1 && json_decode(array_key_first($wpdb->daily),true)[0]==='2026-06-11','aggregate conservative max90days');
$GLOBALS['admin']=true;
RAOS_Reader_Maintenance::cleanup();
$report=RAOS_Reader_Store::report();
expect(is_array($report),'wp-admin aggregate report only');
$GLOBALS['admin']=false;
expect(is_wp_error(RAOS_Reader_Store::report()),'no public report');
$GLOBALS['option_failure']=true;
expect(!RAOS_Reader_Maintenance::cleanup(),'health write failure reported');
expect(!RAOS_Reader_Maintenance::status()['healthy'],'health write failure blocks intake');
$GLOBALS['option_failure']=false;
expect(RAOS_Reader_Maintenance::cleanup(),'health write failure can recover');
echo "store behavior OK\n";
