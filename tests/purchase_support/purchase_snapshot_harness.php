<?php
$theme = $argv[1]; $mode=$argv[2]; $body=$argv[3]; $slug=$argv[4];
$runtime=json_decode(file_get_contents($theme.'/assets/purchase-support.v1.json'),true);
$entry=array_values(array_filter($runtime['articles'],fn($a)=>$a['slug']===$slug))[0];
$record=array('id'=>17,'slug'=>$slug,'post_type'=>$entry['post_type'],'title'=>'Reviewed','excerpt'=>'Excerpt','block_markup'=>$body);
$fields=array('post_name'=>$slug,'post_type'=>$entry['post_type'],'post_title'=>'Reviewed','post_excerpt'=>'Excerpt','post_content'=>$body,'post_password'=>'');
const KURASHINOSHIRUBE_THEME_RUNTIME_REVISION='test';
const KURASHINOSHIRUBE_PURCHASE_UI_SHA256='ui';
const KURASHINOSHIRUBE_LOCAL_COST_ASSET_PATH='assets/local-running-cost.js';
const KURASHINOSHIRUBE_LOCAL_COST_ASSET_SHA256='cost';
define('KURASHINOSHIRUBE_PURCHASE_RUNTIME_SHA256',$mode==='runtime-tampered'?str_repeat('0',64):hash_file('sha256',$theme.'/assets/purchase-support.v1.json'));
function is_admin(){return false;} function is_singular($types){return true;} function get_queried_object_id(){return 17;}
function kurashinoshirube_is_local_preview(){return true;}
function get_post_status($id){global $mode;return $mode==='unpublished'?'draft':'publish';}
function get_post_field($field,$id,$raw){global $fields;return $fields[$field];}
function get_post_meta($id,$key,$single){global $record;return $record;}
function get_stylesheet_directory(){global $theme;return $theme;} function get_stylesheet_directory_uri(){return 'https://example.invalid/theme';}
$actions=[];$filters=[];$styles=[];$scripts=[];$analytics=[];
function add_action(...$a){global $actions;$actions[]=$a;} function add_filter(...$a){global $filters;$filters[]=$a;}
function wp_enqueue_style(...$a){global $styles;$styles[]=$a;}
function wp_enqueue_script(...$a){global $scripts;$scripts[]=$a;}
function kurashinoshirube_verified_asset_uri($path,$hash,$required){return 'https://example.invalid/theme/'.$path;}
function kurashinoshirube_purchase_ga4_enqueue($bindings){global $analytics;$analytics[]=$bindings;}
if($mode==='raw-tampered'){$fields['post_content'].='changed';}
if($mode==='unapproved'){$record=null;}
if($mode==='wrong-id'){$record['id']=18;}
if($mode==='password'){$fields['post_password']='password';}
require $theme.'/inc/purchase-support.php';
$result=kurashinoshirube_purchase_support_context();
if($mode==='valid'){
 if($result!==$entry){throw new RuntimeException('approved snapshot did not bind');}
 kurashinoshirube_enqueue_purchase_support();
 $handles=array_column($styles,0);
 if(!in_array('kurashinoshirube-editorial-v2',$handles,true)||!in_array('kurashinoshirube-purchase-support',$handles,true)){throw new RuntimeException('missing styles');}
 if(count($analytics)!==1){throw new RuntimeException('profile not closed/loaded');}
 if($slug==='dishwasher-running-cost'&&!in_array('kurashinoshirube-local-running-cost',array_column($scripts,0),true)){throw new RuntimeException('cost not loaded');}
}else{
 if($result!==null){throw new RuntimeException('unapproved content loaded runtime');}
 kurashinoshirube_enqueue_purchase_support();
 if($styles||$scripts||$analytics!==array(array())){throw new RuntimeException('failed snapshot must close collection without enabling assets');}
}
echo "PURCHASE_SNAPSHOT_OK\n";
