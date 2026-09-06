<?php
require __DIR__.'/wp.php';
$root=dirname(__DIR__,2);
$plugin=$root.'/changes/reader-measurement-v1/wordpress-plugin/raos-reader-measurement';
if(!is_file($plugin.'/raos-reader-measurement.php')){fwrite(STDERR,"FAIL runtime missing\n");exit(1);}
require __DIR__.'/store-double.php';
require $plugin.'/raos-reader-measurement.php';
$runtime=RAOS_Reader_Measurement::instance();
$meta=json_decode(file_get_contents($plugin.'/config/reader-runtime.v1.json'),true);
$contract=RAOS_Reader_Contract::load($plugin.'/config/reader-allowlist.v1.json');
$id=10;
foreach($contract->articles() as $a){
    $GLOBALS['posts'][$id]=(object)['ID'=>$id,'post_type'=>'post','post_status'=>'publish','post_password'=>'','post_name'=>$a['slug'],'post_content'=>'reviewed fixture'];
    $GLOBALS['identities'][$id]=['article_id'=>$a['article_id'],'section'=>'mobility','slug'=>$a['slug']];$id++;
}
$GLOBALS['posts'][100]=(object)['ID'=>100,'post_type'=>'page','post_status'=>'publish','post_password'=>'','post_name'=>'privacy-policy','post_content'=>file_get_contents($root.'/changes/editorial-portfolio-v3/reader-measurement-privacy.html')];
$GLOBALS['options']['wp_page_for_privacy_policy']=100;
$GLOBALS['options'][RAOS_Reader_Maintenance::DB_OPTION]='1.0.0';
RAOS_Reader_Maintenance::schedule();
RAOS_Reader_Maintenance::cleanup();
expect(!raos_reader_measurement_enabled(),'fresh plugin OFF');
$input=['_wpnonce'=>'simulation-nonce','current_password'=>'simulation-only','contract_suffix'=>substr($meta['contract_sha256'],-8),'policy_suffix'=>substr($meta['policy_sha256'],-8),'revision_suffix'=>substr($meta['revision'],-8),'revision'=>$meta['revision'],'operator_ack'=>'yes'];
$_SERVER['REQUEST_METHOD']='POST';
$GLOBALS['admin']=true;
expect(!is_wp_error($runtime->approve($input)),'verified administrator approves immutable revision');
$GLOBALS['admin']=false;
expect(raos_reader_measurement_enabled(),'valid approval ON');
$aid='st1703-first-suitcase-comparison';
$row=$contract->article($aid);
foreach($GLOBALS['identities'] as $pid=>$identity){if($identity['article_id']===$aid)$GLOBALS['query_id']=$pid;}
if(in_array('--footer',$argv,true)){
    if(in_array('--off',$argv,true)){$runtime->disable();}
    $runtime->enqueue();$runtime->footer();exit(0);
}
$request=new WP_REST_Request();
$request->headers=['origin'=>'https://kurashinoshirube.com','sec-fetch-site'=>'same-origin','content-type'=>'application/json','x-raos-reader-consent'=>'granted','x-raos-reader-contract'=>$meta['contract_sha256'],'x-raos-reader-policy'=>$meta['policy_sha256']];
$request->body=json_encode(['event_name'=>'official_reference_open','article_id'=>$aid,'source_ref'=>'SRC-PROTECA-TRI-AIR-01541']);
expect($runtime->collect($request)->status===202,'real endpoint accepts and increments');
$pid=$GLOBALS['query_id'];
$GLOBALS['posts'][$pid]->post_status='draft';
expect(is_wp_error($runtime->collect($request)),'unpublished identity refused');
$GLOBALS['posts'][$pid]->post_status='publish';
$GLOBALS['identities'][$pid]['slug']='local-preview-carry-on-suitcase-comparison';
expect(is_wp_error($runtime->collect($request)),'theme local fallback refused');
$GLOBALS['identities'][$pid]['slug']=$row['slug'];
$GLOBALS['posts'][$pid]->post_password='private';
expect(is_wp_error($runtime->collect($request)),'password-protected refused');
$GLOBALS['posts'][$pid]->post_password='';
$GLOBALS['posts'][100]->post_content.="\n";
expect(!raos_reader_measurement_enabled(),'published policy content drift refuses intake');
$GLOBALS['posts'][100]->post_content=substr($GLOBALS['posts'][100]->post_content,0,-1);
$state=$GLOBALS['options'][RAOS_Reader_Measurement::STATE_OPTION];
$GLOBALS['options'][RAOS_Reader_Measurement::STATE_OPTION]['approval']['revision']=str_repeat('f',64);
expect(!raos_reader_measurement_enabled(),'stale approval refuses');
$GLOBALS['options'][RAOS_Reader_Measurement::STATE_OPTION]=$state;
$GLOBALS['origin']='http://localhost';
expect(!raos_reader_measurement_enabled(),'no local runtime bypass');
$GLOBALS['origin']='https://kurashinoshirube.com';
$GLOBALS['plugin_origin']='https://unapproved.invalid';
expect(!raos_reader_measurement_enabled(),'unapproved asset origin refuses');
unset($GLOBALS['plugin_origin']);
$GLOBALS['profile']='default';
expect(!raos_reader_measurement_enabled(),'explicit profile required');
$GLOBALS['profile']='reader-minimal-v1';
$GLOBALS['admin']=true;
foreach(['current_password'=>'wrong','contract_suffix'=>'wrong','policy_suffix'=>'wrong','revision_suffix'=>'wrong','_wpnonce'=>'wrong','operator_ack'=>'no'] as $key=>$value){
    expect(is_wp_error($runtime->approve(array_merge($input,[$key=>$value]))),'admin proof rejected');
}
$GLOBALS['options']['raos_codex_mcp_editor_bound_user_id_v1']=99;
expect(is_wp_error($runtime->approve($input)),'bound MCP editor cannot approve');
unset($GLOBALS['options']['raos_codex_mcp_editor_bound_user_id_v1']);
$GLOBALS['caps']['raos_codex_deploy_access']=true;
expect(is_wp_error($runtime->approve($input)),'MCP deployer cannot approve');
unset($GLOBALS['caps']['raos_codex_deploy_access']);
$GLOBALS['caps']['manage_options']=false;
expect(is_wp_error(RAOS_Reader_Store::report()),'no report without manage_options');
$GLOBALS['caps']['manage_options']=true;
$runtime->disable();
expect(!raos_reader_measurement_enabled(),'emergency disable');
$scheduled=$GLOBALS['schedule'];
call_user_func($GLOBALS['deactivate']);
expect($scheduled===$GLOBALS['schedule'],'deactivation retains schedule');
$GLOBALS['admin']=false;
expect(is_wp_error($runtime->collect($request)),'offgate refuses direct callback too');
$runtime->enqueue();
ob_start();$runtime->footer();$html=ob_get_clean();
expect(strpos($html,'raos-reader-consent-settings')!==false,'accessible footer anchor');
expect(strpos($html,'"collection_enabled":false')!==false,'OFF config accurately rendered');
$GLOBALS['admin']=true;
ob_start();$runtime->footer();expect(ob_get_clean()==='','admin no consent UI');
$GLOBALS['admin']=false;$GLOBALS['feed']=true;
ob_start();$runtime->footer();expect(ob_get_clean()==='','feed no consent UI');
$GLOBALS['feed']=false;
$runtime->register_route();
expect(array_keys($GLOBALS['routes'])===['raos-reader/v1/events'],'one public POST route; no read or enable API');
// Ordinary WordPress plugin activation is a nonce-protected GET.
$GLOBALS['admin']=true;
$_SERVER['REQUEST_METHOD']='GET';
$_REQUEST['_wpnonce']='simulation-nonce';
call_user_func($GLOBALS['activate']);
expect(!raos_reader_measurement_enabled(),'activation initializes tables but stays OFF');
echo "runtime behavior OK\n";
