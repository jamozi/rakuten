<?php
/**
 * Plugin Name: RAOS Reader Measurement
 * Description: Optional three-event reader measurement; separate manual operator approval, default OFF.
 * Version: 1.0.0
 * Requires at least: 7.1
 * Requires PHP: 8.1
 * Author: RAOS
 * License: GPL-2.0-or-later
 * Update URI: false
 */
defined('ABSPATH') || exit;
require_once __DIR__.'/includes/class-reader-contract.php';
require_once __DIR__.'/includes/reader-measurement-maintenance.php';
require_once __DIR__.'/includes/class-reader-store.php';

final class RAOS_Reader_Measurement
{
    const VERSION = '1.0.0';
    const STATE_OPTION = 'raos_reader_measurement_state_v1';
    const FILES = array(
        'README.md','assets/reader-measurement.css','assets/reader-measurement.js',
        'config/reader-allowlist.v1.json','includes/class-reader-contract.php',
        'includes/class-reader-store.php','includes/reader-measurement-maintenance.php',
        'raos-reader-measurement.php',
    );
    private static $instance;
    private $enqueued = false;

    public static function instance(): self
    {
        if (!self::$instance) { self::$instance=new self(); }
        return self::$instance;
    }
    private function __construct()
    {
        add_action('rest_api_init',array($this,'register_route'));
        add_action('wp_enqueue_scripts',array($this,'enqueue'));
        add_action('wp_footer',array($this,'footer'),10);
        add_filter('script_loader_tag',array($this,'asset_tag'),10,3);
        add_filter('style_loader_tag',array($this,'asset_tag'),10,4);
        add_action('admin_menu',array($this,'admin_menu'));
        add_action('admin_post_raos_reader_measurement',array($this,'handle_admin'));
    }
    private static function error(string $code, int $status=403): WP_Error
    {
        return new WP_Error('raos_reader_'.$code,'読者計測の操作を完了できません。設定と稼働状態を確認してください。',array('status'=>$status));
    }
    private static function origin(): bool
    {
        return !is_multisite() && untrailingslashit(home_url())===RAOS_Reader_Contract::ORIGIN
            && untrailingslashit(site_url())===RAOS_Reader_Contract::ORIGIN;
    }
    private static function asset_urls_exact(): bool
    {
        foreach (array('js','css') as $extension) {
            $file='assets/reader-measurement.'.$extension;
            if (plugins_url($file,__FILE__)!==RAOS_Reader_Contract::ORIGIN.'/wp-content/plugins/raos-reader-measurement/'.$file) { return false; }
        }
        return true;
    }
    private static function profile(): bool
    {
        return function_exists('kurashinoshirube_reader_runtime_profile')
            && kurashinoshirube_reader_runtime_profile()==='reader-minimal-v1';
    }

    /** Revision includes every packaged code/asset/allowlist byte and policy. */
    public function runtime(): ?array
    {
        $path=__DIR__.'/config/reader-runtime.v1.json';
        if (is_link($path) || !is_file($path) || filesize($path)>32768) { return null; }
        $meta=json_decode(file_get_contents($path),true,16);
        if (!RAOS_Reader_Contract::exact_keys($meta,array('schema','plugin_version','contract_sha256','policy_sha256','policy_slug','revision','files'))
            || $meta['schema']!=='RAOS_READER_MEASUREMENT_RUNTIME_V1' || $meta['plugin_version']!==self::VERSION
            || $meta['policy_slug']!=='privacy-policy' || !RAOS_Reader_Contract::digest($meta['contract_sha256'])
            || !RAOS_Reader_Contract::digest($meta['policy_sha256']) || !RAOS_Reader_Contract::digest($meta['revision'])
            || !RAOS_Reader_Contract::exact_keys($meta['files'],self::FILES)) { return null; }
        $hashes=$meta['files']; ksort($hashes,SORT_STRING); $revision='';
        foreach ($hashes as $file=>$hash) {
            $real=__DIR__.'/'.$file;
            if (!RAOS_Reader_Contract::digest($hash) || is_link($real) || !is_file($real)
                || realpath($real)!==$real || !hash_equals($hash,hash_file('sha256',$real))) { return null; }
            $revision.=$file.':'.$hash."\n";
        }
        if ($meta['contract_sha256']!==$hashes['config/reader-allowlist.v1.json']
            || !hash_equals($meta['revision'],hash('sha256',$revision.'policy:'.$meta['policy_sha256']."\nversion:".self::VERSION."\n"))) { return null; }
        try { RAOS_Reader_Contract::load(__DIR__.'/config/reader-allowlist.v1.json'); }
        catch (Throwable $error) { return null; }
        return $meta;
    }

    public function contract(): RAOS_Reader_Contract
    {
        return RAOS_Reader_Contract::load(__DIR__.'/config/reader-allowlist.v1.json');
    }

    private static function public_post($post, string $type, string $slug): bool
    {
        return is_object($post) && (int)$post->ID>0 && get_post_type($post->ID)===$type
            && get_post_status($post->ID)==='publish' && get_post_field('post_name',$post->ID,'raw')===$slug
            && get_post_field('post_password',$post->ID,'raw')==='';
    }

    public function verified_article(array $article): bool
    {
        if (!function_exists('kurashinoshirube_public_article_identity')) { return false; }
        $post=get_page_by_path($article['slug'],OBJECT,'post');
        if (!self::public_post($post,'post',$article['slug'])) { return false; }
        $identity=kurashinoshirube_public_article_identity((int)$post->ID);
        return is_array($identity) && ($identity['article_id']??null)===$article['article_id']
            && ($identity['slug']??null)===$article['slug'];
    }

    private function ready(array $meta): bool
    {
        if (!self::origin() || !self::profile() || !self::asset_urls_exact()
            || !defined('RAOS_OPERATOR_WRITES_ENABLED') || RAOS_OPERATOR_WRITES_ENABLED!==true
            || (defined('RAOS_READER_MEASUREMENT_DISABLED') && RAOS_READER_MEASUREMENT_DISABLED===true)
            || !RAOS_Reader_Maintenance::status()['healthy']) { return false; }
        $policy=get_page_by_path('privacy-policy',OBJECT,'page');
        if (!self::public_post($policy,'page','privacy-policy')
            || (int)get_option('wp_page_for_privacy_policy',0)!==(int)$policy->ID
            || !hash_equals($meta['policy_sha256'],hash('sha256',get_post_field('post_content',$policy->ID,'raw')))) { return false; }
        foreach ($this->contract()->articles() as $article) {
            if (!$this->verified_article($article)) { return false; }
        }
        return true;
    }

    private static function separate_operator($user): bool
    {
        if (!$user instanceof WP_User || (int)$user->ID<1 || !user_can($user,'manage_options')
            || !in_array('administrator',(array)$user->roles,true)) { return false; }
        foreach (array('raos_codex_mcp_access','raos_codex_content_write_draft','raos_codex_content_propose','raos_codex_deploy_access','raos_codex_deploy_apply') as $cap) {
            if (user_can($user,$cap)) { return false; }
        }
        foreach (array('raos_codex_mcp_editor_bound_user_id_v1','raos_codex_deployment_operator_bound_user_id_v1') as $binding) {
            if ((int)get_option($binding,0)===(int)$user->ID) { return false; }
        }
        return true;
    }

    private function approval_valid(array $meta): bool
    {
        $state=get_option(self::STATE_OPTION,null);
        if (!RAOS_Reader_Contract::exact_keys($state,array('enabled','approval')) || $state['enabled']!==true) { return false; }
        $approval=$state['approval'];
        if (!RAOS_Reader_Contract::exact_keys($approval,array('revision','contract_sha256','policy_sha256','operator_user_id','approved_date','method'))
            || $approval['revision']!==$meta['revision'] || $approval['contract_sha256']!==$meta['contract_sha256']
            || $approval['policy_sha256']!==$meta['policy_sha256'] || $approval['method']!=='wp_admin_password'
            || !is_int($approval['operator_user_id']) || !is_string($approval['approved_date'])
            || preg_match('/\A[0-9]{4}-[0-9]{2}-[0-9]{2}\z/D',$approval['approved_date'])!==1) { return false; }
        return self::separate_operator(get_userdata($approval['operator_user_id']));
    }

    public function enabled(): bool
    {
        try {
            $meta=$this->runtime();
            return $meta!==null && $this->ready($meta) && $this->approval_valid($meta);
        } catch (Throwable $error) { return false; }
    }

    public function status(): array
    {
        $meta=$this->runtime();
        return array('schema'=>'RAOSReaderMeasurementStatusV1','plugin_active'=>true,
            'plugin_version'=>self::VERSION,'collection_enabled'=>$this->enabled(),
            'contract_sha256'=>$meta['contract_sha256']??null,'policy_sha256'=>$meta['policy_sha256']??null,
            'approved_revision'=>$meta!==null && $this->approval_valid($meta) ? $meta['revision'] : null,
            'cleanup'=>RAOS_Reader_Maintenance::status());
    }

    public function register_route(): void
    {
        register_rest_route('raos-reader/v1','/events',array(
            'methods'=>'POST','permission_callback'=>array($this,'permission'),'callback'=>array($this,'collect')));
    }
    public function permission($request)
    {
        $meta=$this->runtime();
        if (!$request instanceof WP_REST_Request || $meta===null || !$this->enabled()) { return self::error('disabled',404); }
        $headers=array();
        foreach (array('origin','sec-fetch-site','content-type','x-raos-reader-consent','x-raos-reader-contract','x-raos-reader-policy') as $key) {
            $headers[$key]=$request->get_header($key);
        }
        return RAOS_Reader_Contract::request_allowed($request->get_method(),$headers,$meta['contract_sha256'],$meta['policy_sha256'])
            ? true : self::error('request_forbidden');
    }
    public function collect($request)
    {
        // Also guard direct callback invocation and state changes since permission.
        $allowed=$this->permission($request);
        if (is_wp_error($allowed)) { return $allowed; }
        try {
            $contract=$this->contract();
            $instant=new DateTimeImmutable('now');
            $event=$contract->validate_body($request->get_body(),$instant);
        } catch (InvalidArgumentException $error) { return self::error('event_invalid',400); }
        catch (Throwable $error) { return self::error('contract_unavailable',503); }
        $stored=RAOS_Reader_Store::record($event,$contract,$instant,array($this,'enabled'));
        if (is_wp_error($stored)) { return $stored; }
        $response=new WP_REST_Response(array('accepted'=>true),202);
        $response->header('Cache-Control','no-store, max-age=0');
        $response->header('Vary','Origin');
        return $response;
    }

    private static function admin_request(): bool
    {
        return is_admin() && !wp_doing_ajax() && !wp_doing_cron()
            && !(defined('REST_REQUEST') && REST_REQUEST) && !(defined('WP_CLI') && WP_CLI)
            && ($_SERVER['REQUEST_METHOD']??'')==='POST' && current_user_can('manage_options');
    }

    public function approve(array $input)
    {
        $meta=$this->runtime(); $user=wp_get_current_user();
        if (!self::admin_request() || !self::separate_operator($user) || $meta===null) { return self::error('approval_refused'); }
        foreach (array('_wpnonce','current_password','contract_suffix','policy_suffix','revision_suffix','revision','operator_ack') as $key) {
            if (!is_string($input[$key]??null)) { return self::error('approval_refused'); }
        }
        if ($input['revision']!==$meta['revision'] || $input['operator_ack']!=='yes'
            || !wp_verify_nonce($input['_wpnonce'],'raos_reader_enable_'.$meta['revision'])
            || !hash_equals(substr($meta['contract_sha256'],-8),$input['contract_suffix'])
            || !hash_equals(substr($meta['policy_sha256'],-8),$input['policy_suffix'])
            || !hash_equals(substr($meta['revision'],-8),$input['revision_suffix'])
            || strlen($input['current_password'])>4096 || $input['current_password']===''
            || !wp_check_password($input['current_password'],$user->user_pass,$user->ID)
            || !$this->ready($meta)) { return self::error('approval_refused'); }
        // Password is never persisted, logged or echoed. No AI validation claim.
        $state=array('enabled'=>true,'approval'=>array(
            'revision'=>$meta['revision'],'contract_sha256'=>$meta['contract_sha256'],'policy_sha256'=>$meta['policy_sha256'],
            'operator_user_id'=>(int)$user->ID,'approved_date'=>(new DateTimeImmutable('now',new DateTimeZone('Asia/Tokyo')))->format('Y-m-d'),
            'method'=>'wp_admin_password'));
        update_option(self::STATE_OPTION,$state,false);
        return get_option(self::STATE_OPTION,null)===$state ? true : self::error('approval_storage_unavailable',503);
    }

    public function disable(): bool
    {
        $state=array('enabled'=>false,'approval'=>null);
        update_option(self::STATE_OPTION,$state,false);
        return get_option(self::STATE_OPTION,null)===$state;
    }

    public static function activate(): void
    {
        $nonce=$_REQUEST['_wpnonce']??null;
        $nonce_ok=is_string($nonce) && (wp_verify_nonce($nonce,'activate-plugin_'.plugin_basename(__FILE__))
            || wp_verify_nonce($nonce,'bulk-plugins'));
        if (!is_admin() || wp_doing_ajax() || wp_doing_cron()
            || (defined('REST_REQUEST') && REST_REQUEST) || (defined('WP_CLI') && WP_CLI)
            || !in_array($_SERVER['REQUEST_METHOD']??'',array('GET','POST'),true)
            || !$nonce_ok || !current_user_can('activate_plugins')
            || !self::separate_operator(wp_get_current_user()) || !self::origin()
            || self::instance()->runtime()===null) {
            wp_die('読者計測の初期化には、別管理者による手動レビューと正しいパッケージが必要です。','',array('response'=>403));
        }
        // Migration stays on the existing manual-review route; no init upgrade.
        if (!self::instance()->disable() || !RAOS_Reader_Store::install()) {
            wp_die('専用保存領域の初期化を確認できません。計測は停止状態です。','',array('response'=>503));
        }
    }
    public static function deactivate(): void
    {
        self::instance()->disable();
        // Retain tables AND scheduling. The reviewed theme loads maintenance only.
        RAOS_Reader_Maintenance::schedule();
    }

    private static function public_page(): bool
    {
        return !is_admin() && !is_feed() && !is_preview()
            && !(defined('REST_REQUEST') && REST_REQUEST)
            && !in_array($GLOBALS['pagenow']??'',array('wp-login.php','wp-register.php'),true);
    }

    public function enqueue(): void
    {
        $meta=$this->runtime();
        if (!self::public_page() || !self::origin() || !self::profile() || !self::asset_urls_exact() || $meta===null) { return; }
        wp_enqueue_script('raos-reader-measurement',plugins_url('assets/reader-measurement.js',__FILE__),array(),$meta['files']['assets/reader-measurement.js'],true);
        wp_enqueue_style('raos-reader-measurement-style',plugins_url('assets/reader-measurement.css',__FILE__),array(),$meta['files']['assets/reader-measurement.css']);
        $this->enqueued=true;
    }

    public function asset_tag($tag,$handle,$src=null,$media=null): string
    {
        if (!in_array($handle,array('raos-reader-measurement','raos-reader-measurement-style'),true)) { return $tag; }
        $meta=$this->runtime();
        if ($meta===null || !self::origin() || !self::profile() || !self::asset_urls_exact()) { return ''; }
        $js=$handle==='raos-reader-measurement'; $file='assets/reader-measurement.'.($js?'js':'css');
        $hash=$meta['files'][$file];
        $url=plugins_url($file,__FILE__).'?ver='.$hash;
        $integrity='sha256-'.base64_encode(hex2bin($hash));
        return $js
            ? '<script id="raos-reader-measurement-js" src="'.esc_url($url).'" integrity="'.esc_attr($integrity).'" crossorigin="anonymous"></script>'."\n"
            : '<link rel="stylesheet" id="raos-reader-measurement-style-css" href="'.esc_url($url).'" media="all" integrity="'.esc_attr($integrity).'" crossorigin="anonymous">'."\n";
    }

    public function footer(): void
    {
        if (!self::public_page()) { return; }
        $meta=$this->runtime(); $configured=$this->enqueued && $meta!==null && self::profile() && self::origin() && self::asset_urls_exact();
        $enabled=$configured && $this->enabled();
        echo '<section id="raos-reader-consent-settings" aria-labelledby="raos-reader-consent-title">';
        echo '<h2 id="raos-reader-consent-title">任意の読者計測</h2>';
        echo '<p id="raos-reader-site-status" role="status">'.esc_html($enabled ? 'サイトの計測は有効です。許可した場合だけ対象の操作を送ります。' : 'サイトの計測は停止中です。現在、操作は送信されません。').'</p>';
        echo '<p>記事の移動・確認パネル・公式出典の操作件数を、記事改善の参考にします。許可は任意です。<a href="/privacy-policy/">プライバシーポリシー</a></p>';
        echo '<p id="raos-reader-user-status" aria-live="polite">あなたの選択：未選択</p>';
        if ($configured) {
            echo '<button type="button" id="raos-reader-consent-reopen" aria-expanded="true" aria-controls="raos-reader-consent-choices">計測設定を開く</button>';
            echo '<div id="raos-reader-consent-choices"><button type="button" id="raos-reader-consent-allow">許可する</button> <button type="button" id="raos-reader-consent-deny">許可しない</button></div>';
            echo '<button type="button" id="raos-reader-consent-revoke" hidden>許可を撤回する</button>';
            echo '<p id="raos-reader-consent-error" role="alert" hidden></p>';
            echo '<noscript><p>JavaScriptが無効なため、この計測は行いません。</p></noscript>';
        } else {
            echo '<p>計測設定を利用できません。計測の受付は停止しています。</p>';
        }
        echo '</section>';
        if (!$configured) { return; }
        $article=null;
        if (is_singular('post')) {
            $id=(int)get_queried_object_id();
            $identity=function_exists('kurashinoshirube_public_article_identity') ? kurashinoshirube_public_article_identity($id) : null;
            $row=is_array($identity) ? $this->contract()->article($identity['article_id']??null) : null;
            if ($row!==null && get_post_field('post_name',$id,'raw')===$row['slug'] && $this->verified_article($row)) { $article=$row; }
        }
        $config=array('schema'=>'RAOSReaderMeasurementClientV1','origin'=>RAOS_Reader_Contract::ORIGIN,
            'endpoint'=>'/wp-json/raos-reader/v1/events','collection_enabled'=>$enabled,
            'contract_sha256'=>$meta['contract_sha256'],'policy_sha256'=>$meta['policy_sha256'],
            'policy_version'=>$meta['policy_sha256'],'article'=>$article);
        echo '<script id="raos-reader-measurement-config" type="application/json">'
            .wp_json_encode($config,JSON_HEX_TAG|JSON_HEX_AMP|JSON_HEX_APOS|JSON_HEX_QUOT|JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES).'</script>';
    }

    public function admin_menu(): void
    {
        add_management_page('読者計測','読者計測','manage_options','raos-reader-measurement',array($this,'admin_page'));
    }
    public function handle_admin(): void
    {
        if (!self::admin_request()) { wp_die('操作を確認できません。','',array('response'=>403)); }
        $input=wp_unslash($_POST);
        if (($input['operation']??null)==='disable') {
            $ok=is_string($input['_wpnonce']??null) && wp_verify_nonce($input['_wpnonce'],'raos_reader_disable') && $this->disable();
        } elseif (($input['operation']??null)==='cleanup') {
            $ok=is_string($input['_wpnonce']??null) && wp_verify_nonce($input['_wpnonce'],'raos_reader_cleanup') && raos_reader_measurement_cleanup();
        } else { $ok=$this->approve(is_array($input)?$input:array()); }
        if ($ok!==true) { wp_die('操作を完了できません。稼働状態・公開ポリシー・確認値を見直してください。','',array('response'=>403,'back_link'=>true)); }
        wp_safe_redirect(admin_url('tools.php?page=raos-reader-measurement'));
        exit;
    }

    public function admin_page(): void
    {
        if (!is_admin() || !current_user_can('manage_options')) { wp_die('権限がありません。','',array('response'=>403)); }
        $status=$this->status(); $meta=$this->runtime();
        echo '<div class="wrap"><h1>任意の読者計測</h1><p>収集状態：<strong>'.($status['collection_enabled']?'ON':'OFF').'</strong></p>';
        echo '<p>運営者が計測の管理・削除に責任を持ちます。記録はJST日付のみで、イベントは最大30日、日別集計は最大90日です。個人を識別しないため、個人別の記録検索・削除はできません。件数は利用人数や理解度を表しません。</p>';
        echo '<p>清掃状態：'.esc_html($status['cleanup']['healthy']?'正常':($status['cleanup']['last_error_code']??'未確認')).'／最終成功日：'.esc_html($status['cleanup']['last_success_date']??'未確認').'</p>';
        foreach (array('disable'=>'緊急停止（承認を無効化）','cleanup'=>'保持期限の清掃を再実行') as $operation=>$label) {
            echo '<form method="post" action="'.esc_url(admin_url('admin-post.php')).'"><input type="hidden" name="action" value="raos_reader_measurement"><input type="hidden" name="operation" value="'.esc_attr($operation).'">';
            wp_nonce_field('raos_reader_'.$operation);
            echo '<p><button type="submit">'.esc_html($label).'</button></p></form>';
        }
        if ($meta!==null) {
            echo '<h2>この版の計測を承認して有効化</h2><p>MCP編集者・デプロイ担当と別の管理者が、公開ポリシー、契約、保存・削除条件を確認して操作します。AIによる確認はこの承認の代わりになりません。</p>';
            echo '<form method="post" action="'.esc_url(admin_url('admin-post.php')).'"><input type="hidden" name="action" value="raos_reader_measurement"><input type="hidden" name="operation" value="enable"><input type="hidden" name="revision" value="'.esc_attr($meta['revision']).'">';
            wp_nonce_field('raos_reader_enable_'.$meta['revision']);
            foreach (array('contract'=>'契約','policy'=>'公開ポリシー','revision'=>'プラグインと許可リストの版') as $key=>$label) {
                $hash=$key==='revision'?$meta['revision']:$meta[$key.'_sha256'];
                echo '<p>'.esc_html($label).'：<code>'.esc_html($hash).'</code></p><p><label for="reader-'.$key.'">'.esc_html($label).'の末尾8文字（'.esc_html(substr($hash,-8)).'）</label> <input id="reader-'.$key.'" name="'.$key.'_suffix" required pattern="[a-f0-9]{8}" autocomplete="off"></p>';
            }
            echo '<p><label for="reader-password">現在のパスワードで再認証</label> <input id="reader-password" type="password" name="current_password" autocomplete="current-password" required></p>';
            echo '<p><label><input type="checkbox" name="operator_ack" value="yes" required>この版の公開説明・3項目・保存期限・清掃を確認し、運営者として承認します。</label></p><button type="submit">この版を承認して有効化する</button></form>';
        }
        echo '<h2>日別集計（1ページ100行）</h2>';
        $page=isset($_GET['report_page']) && is_scalar($_GET['report_page']) ? max(1,min(10000,(int)$_GET['report_page'])) : 1;
        $rows=RAOS_Reader_Store::report($page);
        if (is_wp_error($rows)) { echo '<p role="alert">集計を表示できません。清掃と保存領域の状態を確認してください。</p>'; }
        else {
            echo '<table class="widefat"><caption>保存期間内の操作件数</caption><thead><tr>';
            foreach (array('JST日付','項目','記事','移動先','検討段階','パネル','出典','件数') as $label) { echo '<th scope="col">'.esc_html($label).'</th>'; }
            echo '</tr></thead><tbody>';
            foreach ($rows as $row) {
                echo '<tr>';
                foreach (array('event_date','event_name','article_id','target_article_id','journey_stage','panel_id','source_ref','event_count') as $key) { echo '<td>'.esc_html($row[$key]??'').'</td>'; }
                echo '</tr>';
            }
            echo '</tbody></table><p><a href="'.esc_url(admin_url('tools.php?page=raos-reader-measurement&report_page='.max(1,$page-1))).'">前のページ</a> ';
            if(count($rows)===100) { echo '<a href="'.esc_url(admin_url('tools.php?page=raos-reader-measurement&report_page='.min(10000,$page+1))).'">次のページ</a>'; }
            echo '</p>';
        }
        echo '</div>';
    }
}
function raos_reader_measurement_status(): array { return RAOS_Reader_Measurement::instance()->status(); }
function raos_reader_measurement_enabled(): bool { return RAOS_Reader_Measurement::instance()->enabled(); }
RAOS_Reader_Measurement::instance();
register_activation_hook(__FILE__,array('RAOS_Reader_Measurement','activate'));
register_deactivation_hook(__FILE__,array('RAOS_Reader_Measurement','deactivate'));
