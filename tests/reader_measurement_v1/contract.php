<?php
// No WordPress, provider, HTTP, or production data. Exact trusted fixture only.
$root = dirname(__DIR__, 2);
$contract_file = $root . '/changes/reader-measurement-v1/wordpress-plugin/raos-reader-measurement/includes/class-reader-contract.php';
if (!is_file($contract_file)) { fwrite(STDERR, "FAIL: pure contract missing\n"); exit(1); }
require $contract_file;
function expect($ok, $message) { if (!$ok) { throw new RuntimeException($message); } }
function refuses(callable $call) {
    try { $call(); } catch (InvalidArgumentException $e) { return; }
    throw new RuntimeException('invalid input was accepted');
}
$contract = RAOS_Reader_Contract::load($root . '/changes/reader-measurement-v1/wordpress-plugin/raos-reader-measurement/config/reader-allowlist.v1.json');
$utc = new DateTimeImmutable('2026-09-06T15:00:00Z');
$aid = 'st1703-first-suitcase-comparison';
$events = [
    ['event_name'=>'guide_navigation','article_id'=>$aid,'target_article_id'=>'lightweight-carry-on-suitcase-under-3kg','journey_stage'=>'compare'],
    ['event_name'=>'decision_check_open','article_id'=>$aid,'panel_id'=>'reader-evidence'],
    ['event_name'=>'official_reference_open','article_id'=>$aid,'source_ref'=>'SRC-PROTECA-TRI-AIR-01541'],
];
foreach ($events as $event) {
    $actual = $contract->validate_body(json_encode($event), $utc);
    expect($actual === $event + ['event_date'=>'2026-09-07'], 'exact allowed fields plus server JST date');
    foreach (['event_date','occurred_at','session_id','event_id','url','ip','extra'] as $extra) {
        refuses(fn() => $contract->validate_body(json_encode($event + [$extra=>'injected']), $utc));
    }
    refuses(fn() => $contract->validate_body(json_encode(array_merge($event, ['article_id'=>'local-dishwasher-installation-guide'])), $utc));
}
expect($contract->validate_body(json_encode($events[0]),new DateTimeImmutable('2026-09-06T14:59:59Z'))['event_date']==='2026-09-06','JST midnight boundary');
refuses(fn()=> $contract->validate_body('{"event_name":"decision_check_open","event_name":"official_reference_open","article_id":"'.$aid.'","source_ref":"SRC-PROTECA-TRI-AIR-01541"}',$utc));
refuses(fn()=> $contract->validate_body(str_repeat(' ',1024).json_encode($events[0]),$utc));
refuses(fn()=> $contract->validate_body('[]',$utc));
refuses(fn()=> $contract->validate_body(json_encode(array_merge($events[0],['journey_stage'=>'buy'])),$utc));
refuses(fn()=> $contract->validate_body(json_encode(array_merge($events[1],['panel_id'=>'password'])),$utc));
refuses(fn()=> $contract->validate_body(json_encode(array_merge($events[2],['source_ref'=>'SRC-UNKNOWN'])),$utc));
refuses(fn()=> $contract->validate_body(json_encode(array_merge($events[2],['source_ref'=>'https://example.invalid/private'])),$utc));
$headers = ['origin'=>'https://kurashinoshirube.com','sec-fetch-site'=>'same-origin','content-type'=>'application/json','x-raos-reader-consent'=>'granted','x-raos-reader-contract'=>str_repeat('a',64),'x-raos-reader-policy'=>str_repeat('b',64)];
expect(RAOS_Reader_Contract::request_allowed('POST',$headers,str_repeat('a',64),str_repeat('b',64)), 'strict headers valid');
foreach (['origin'=> 'https://kurashinoshirube.com.evil.invalid','sec-fetch-site'=>'same-site','content-type'=>'text/plain','x-raos-reader-consent'=>'denied','x-raos-reader-contract'=>str_repeat('c',64),'x-raos-reader-policy'=>str_repeat('d',64)] as $key=>$bad) {
    expect(!RAOS_Reader_Contract::request_allowed('POST',array_merge($headers,[$key=>$bad]),str_repeat('a',64),str_repeat('b',64)),'bad header refused');
    $missing=$headers; unset($missing[$key]); expect(!RAOS_Reader_Contract::request_allowed('POST',$missing,str_repeat('a',64),str_repeat('b',64)),'missing header refused');
}
expect(!RAOS_Reader_Contract::request_allowed('GET',$headers,str_repeat('a',64),str_repeat('b',64)),'no GET');
echo "contract behavior OK\n";
