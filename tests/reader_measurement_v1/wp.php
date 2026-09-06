<?php
/** Minimal boundary doubles; no CMS connection or network is available. */
define('ABSPATH', __DIR__.'/wp-runtime/');
define('ARRAY_A', 'ARRAY_A');
define('RAOS_OPERATOR_WRITES_ENABLED', true);
define('HOUR_IN_SECONDS', 3600);
$GLOBALS['options'] = [];
$GLOBALS['hooks'] = [];
$GLOBALS['schedule'] = [];
$GLOBALS['admin'] = false;
$GLOBALS['caps'] = ['manage_options'=>true, 'activate_plugins'=>true];
$GLOBALS['profile'] = 'reader-minimal-v1';
$GLOBALS['origin'] = 'https://kurashinoshirube.com';
$GLOBALS['posts'] = [];
$GLOBALS['query_id'] = 0;
$GLOBALS['styles'] = $GLOBALS['scripts'] = [];
class WP_Error {
    public function __construct(public $code, public $message='', public $data=[]) {}
    public function get_error_code(){return $this->code;}
    public function get_error_data(){return $this->data;}
}
class WP_REST_Request {
    public $headers = []; public $body = ''; public $method = 'POST';
    public function get_header($key){return $this->headers[$key] ?? '';}
    public function get_body(){return $this->body;}
    public function get_method(){return $this->method;}
}
class WP_REST_Response {
    public $headers=[]; public function __construct(public $data,public $status=200){}
    public function header($k,$v){$this->headers[$k]=$v;}
}
class WP_REST_Server { const CREATABLE = 'POST'; }
class WP_User {
    public $ID = 99; public $user_pass = 'simulation-only'; public $roles = ['administrator'];
}
function expect($value,$message){if(!$value){throw new RuntimeException($message);}}
function is_wp_error($value){return $value instanceof WP_Error;}
function add_action($hook,$callback,$priority=10,$args=1){$GLOBALS['hooks'][$hook][]=$callback;}
function has_action($hook,$callback=false){return isset($GLOBALS['hooks'][$hook]) ? 10 : false;}
function add_filter($hook,$callback,$priority=10,$args=1){add_action($hook,$callback);}
function get_option($name,$default=false){return $GLOBALS['options'][$name]??$default;}
function update_option($name,$value,$autoload=false){if(($GLOBALS['option_failure']??false)){return false;} $GLOBALS['options'][$name]=$value;return true;}
function add_option($name,$value,$deprecated='',$autoload=false){if(isset($GLOBALS['options'][$name]))return false;return update_option($name,$value);}
function wp_next_scheduled($hook){return $GLOBALS['schedule'][$hook]??false;}
function wp_schedule_event($when,$recurrence,$hook){$GLOBALS['schedule'][$hook]=$when;return true;}
function wp_doing_ajax(){return false;}
function wp_doing_cron(){return false;}
function is_admin(){return $GLOBALS['admin'];}
function is_multisite(){return false;}
function is_feed(){return $GLOBALS['feed']??false;}
function is_preview(){return $GLOBALS['preview']??false;}
function is_404(){return false;}
function is_singular($type=''){return $GLOBALS['query_id']>0;}
function get_queried_object_id(){return $GLOBALS['query_id'];}
function current_user_can($cap){return $GLOBALS['caps'][$cap]??false;}
function get_current_user_id(){return 99;}
function wp_get_current_user(){return $GLOBALS['user']??new WP_User();}
function get_userdata($id){return $id === 99 ? wp_get_current_user() : false;}
function user_can($user,$cap){return current_user_can($cap);}
function wp_check_password($pass,$hash,$id){return $pass==='simulation-only' && $id===99;}
function wp_verify_nonce($nonce,$action){return $nonce==='simulation-nonce';}
function wp_unslash($value){return $value;}
function wp_is_serving_rest_request(){return false;}
function home_url($path=''){return $GLOBALS['origin'].$path;}
function site_url($path=''){return $GLOBALS['origin'].$path;}
function untrailingslashit($text){return rtrim($text,'/');}
function admin_url($path=''){return home_url('/wp-admin/'.$path);}
function plugins_url($path='',$file=''){return ($GLOBALS['plugin_origin']??$GLOBALS['origin']).'/wp-content/plugins/raos-reader-measurement/'.$path;}
function plugin_basename($file){return 'raos-reader-measurement/raos-reader-measurement.php';}
function register_activation_hook($file,$callback){$GLOBALS['activate']=$callback;}
function register_deactivation_hook($file,$callback){$GLOBALS['deactivate']=$callback;}
function register_rest_route($namespace,$route,$args){$GLOBALS['routes'][$namespace.$route]=$args;}
function wp_json_encode($value,$flags=0){return json_encode($value,$flags);}
function esc_html($value){return htmlspecialchars((string)$value,ENT_QUOTES,'UTF-8');}
function esc_attr($value){return esc_html($value);}
function esc_url($value){return esc_html($value);}
function wp_enqueue_script($handle,$src,$deps=[],$ver=false,$footer=false){$GLOBALS['scripts'][$handle]=[$src,$ver,$footer];}
function wp_enqueue_style($handle,$src,$deps=[],$ver=false){$GLOBALS['styles'][$handle]=[$src,$ver];}
function wp_nonce_field($action){echo '<input type="hidden" name="_wpnonce" value="simulation-nonce">';}
function add_management_page(...$args){}
function wp_safe_redirect($url){$GLOBALS['redirect']=$url;}
function wp_die($message,$title='',$args=[]){throw new RuntimeException('WP_DIE:'.$message);}
function get_post_type($id){return $GLOBALS['posts'][$id]->post_type??false;}
function get_post_status($id){return $GLOBALS['posts'][$id]->post_status??false;}
function get_post_field($name,$id,$context='raw'){return $GLOBALS['posts'][$id]->$name??'';}
function get_post($id){return $GLOBALS['posts'][$id]??null;}
function get_page_by_path($path,$output=OBJECT,$type='page'){
    foreach($GLOBALS['posts'] as $post){if($post->post_name===$path && $post->post_type===$type)return $post;}
    return null;
}
define('OBJECT','OBJECT');
function kurashinoshirube_reader_runtime_profile(){return $GLOBALS['profile'];}
function kurashinoshirube_public_article_identity($id){
    // Real theme contract: article_id + section + slug, may return a local identity.
    return $GLOBALS['identities'][$id]??null;
}
function wp_password_change_notification(...$args){throw new RuntimeException('credential changes forbidden');}
