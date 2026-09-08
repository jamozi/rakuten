<?php
/** Versioned administrator-delegated publishing; the legacy approval protocol is unchanged. */
defined('ABSPATH') || exit;

final class RAOS_Codex_MCP_Owner_Direct
{
    const RUNTIME_REVISION = '3959d130244e13994c252522bbbc4ae245d70c517817c7e6e64835c621659a19';
    const PROFILE = 'owner-direct-v1';
    const PROFILE_OPTION = 'raos_codex_owner_direct_profile_v1';
    const TARGETS_OPTION = 'raos_codex_owner_direct_created_targets_v1';
    const PUBLISHER_ROLE = 'raos_codex_owner_direct_publisher';
    const APP_NAME = 'RAOS Codex Owner Direct Publisher';
    const BINDING_OPTION = 'raos_codex_owner_direct_bound_user_id_v1';
    private $plugin;

    public function __construct($plugin) { $this->plugin = $plugin; }

    public function register_routes()
    {
        foreach (array(
            array('/status', 'GET', 'status'),
            array('/documents/(?P<id>[1-9][0-9]*)', 'GET', 'document'),
            array('/ensure-draft', 'POST', 'ensure_draft'),
            array('/content-proposals', 'POST', 'content_proposal'),
            array('/theme-proposals', 'POST', 'theme_proposal'),
            array('/authorize', 'POST', 'authorize'),
            array('/batches/(?P<batch_token>[0-9a-f]{64})/finish', 'POST', 'finish'),
        ) as $route) {
            register_rest_route('raos-codex-owner-direct/v1', $route[0], array(
                'methods' => $route[1], 'callback' => array($this, $route[2]),
                'permission_callback' => array($this->plugin, 'owner_direct_permission'),
            ));
        }
    }

    public static function capabilities()
    {
        return array('read' => true, 'raos_codex_owner_direct_publish' => true);
    }

    private static function error($code, $status = 409)
    {
        return new WP_Error('raos_codex_owner_direct_' . $code, 'Owner-direct publication refused.', array('status' => $status));
    }

    public static function profile()
    {
        $profile = get_option(self::PROFILE_OPTION, null);
        return is_array($profile) ? $profile : null;
    }

    public static function gate()
    {
        $runtime = RAOS_Codex_MCP_Abilities::runtime_identity_gate();
        if (is_wp_error($runtime)) { return $runtime; }
        $profile = self::profile();
        if (! is_array($profile) || empty($profile['enabled'])
            || ! isset($profile['profile'], $profile['publisher_user_id'], $profile['configured_by'], $profile['allow_new_posts'], $profile['targets'], $profile['theme_slug'])
            || self::PROFILE !== $profile['profile'] || true !== $profile['enabled']
            || ! is_int($profile['publisher_user_id']) || $profile['publisher_user_id'] < 1
            || ! is_int($profile['configured_by']) || $profile['configured_by'] < 1
            || $profile['configured_by'] === $profile['publisher_user_id']
            || ! is_bool($profile['allow_new_posts']) || ! is_array($profile['targets'])
            || 'kurashinoshirube-child' !== $profile['theme_slug']) {
            return self::error('disabled', 403);
        }
        if (! defined('RAOS_OPERATOR_WRITES_ENABLED') || true !== RAOS_OPERATOR_WRITES_ENABLED) {
            return self::error('kill_switch_disabled', 503);
        }
        return $profile;
    }

    private function request_gate($request, $required)
    {
        $profile = self::gate();
        if (is_wp_error($profile)) { return $profile; }
        if (! $this->plugin->owner_direct_permission()
            || get_current_user_id() !== $profile['publisher_user_id']) {
            return self::error('identity_forbidden', 403);
        }
        $input = $request->get_json_params();
        $keys = is_array($input) ? array_keys($input) : array();
        sort($keys); sort($required);
        if ($keys !== $required || ! isset($input['profile']) || self::PROFILE !== $input['profile']) {
            return self::error('input_invalid', 400);
        }
        return $input;
    }

    private static function created_targets()
    {
        // Read authoritative DB values, avoiding persistent option-cache ambiguity
        // after a COMMIT whose acknowledgement was lost.
        global $wpdb;
        $json = $wpdb->get_var($wpdb->prepare('SELECT option_value FROM ' . $wpdb->options . ' WHERE option_name = %s', self::TARGETS_OPTION));
        if (null === $json && empty($wpdb->last_error)) { return array(); }
        $targets = is_string($json) ? json_decode($json, true) : null;
        return is_array($targets) && empty($wpdb->last_error) ? $targets : self::error('registry_unavailable', 503);
    }

    private static function target($article_key)
    {
        $profile = self::profile();
        if (! is_array($profile)) { return self::error('disabled', 403); }
        foreach ($profile['targets'] as $target) {
            if ($target['article_key'] === $article_key) { return $target; }
        }
        $targets = self::created_targets();
        if (is_wp_error($targets)) { return $targets; }
        $target = $targets[$article_key] ?? null;
        if (! is_array($target) || ($target['publisher_user_id'] ?? null) !== $profile['publisher_user_id']) {
            return self::error('target_forbidden', 403);
        }
        return $target;
    }

    public function status()
    {
        $profile = self::profile();
        $gate = self::gate();
        $deployment = new RAOS_Codex_MCP_Deployment($this->plugin);
        $deployment_status = $deployment->status();
        $targets = is_array($profile) ? $profile['targets'] : array();
        $created = self::created_targets();
        if (is_array($created) && is_array($profile)) {
            foreach ($created as $target) {
                if (($target['publisher_user_id'] ?? null) === $profile['publisher_user_id']) {
                    $targets[] = array_intersect_key($target, array_flip(array('article_key', 'post_id', 'post_type', 'slug')));
                }
            }
        }
        return array(
            'schema' => 'RAOSOwnerDirectStatusV1', 'profile' => self::PROFILE,
            'enabled' => ! is_wp_error($gate) && ! is_wp_error($created),
            'profile_sha256' => is_array($profile) ? RAOS_Codex_MCP_Store::hash($profile) : null,
            'publisher_user_id' => $profile['publisher_user_id'] ?? null,
            'allow_new_posts' => $profile['allow_new_posts'] ?? false,
            'targets' => $targets, 'theme' => $deployment_status['theme'],
            'plugin_version' => RAOS_CODEX_MCP_VERSION,
            'plugin_runtime_revision' => RAOS_Codex_MCP_Abilities::plugin_runtime_revision(),
        );
    }

    public function binding($article_key = null)
    {
        $profile = self::gate();
        if (is_wp_error($profile)) { return $profile; }
        return array('profile' => self::PROFILE, 'profile_sha256' => RAOS_Codex_MCP_Store::hash($profile),
            'publisher_user_id' => $profile['publisher_user_id'], 'article_key' => $article_key);
    }

    public static function is_direct($row)
    {
        return isset($row['payload']['authorization_profile']);
    }

    public static function validate_binding($row)
    {
        if (! self::is_direct($row)) { return self::error('legacy_forbidden', 403); }
        $profile = self::gate();
        if (is_wp_error($profile)) { return $profile; }
        $binding = $row['payload']['authorization_profile'];
        if (! is_array($binding) || count($binding) !== 4
            || ($binding['profile'] ?? null) !== self::PROFILE
            || ($binding['publisher_user_id'] ?? null) !== $profile['publisher_user_id']
            || (int) ($row['created_by'] ?? 0) !== $profile['publisher_user_id']
            || ! isset($binding['profile_sha256']) || ! is_string($binding['profile_sha256'])
            || ! hash_equals(RAOS_Codex_MCP_Store::hash($profile), $binding['profile_sha256'])) {
            return self::error('identity_forbidden', 403);
        }
        if ('CONTENT_RELEASE' === ($row['kind'] ?? null)) {
            $target = self::target($binding['article_key'] ?? null);
            if (is_wp_error($target)) { return $target; }
            foreach (array('before', 'after') as $side) {
                $document = $row['payload'][$side] ?? array();
                if (($document['id'] ?? null) !== $target['post_id']
                    || ($document['post_type'] ?? null) !== $target['post_type']
                    || ($document['slug'] ?? null) !== $target['slug']) {
                    return self::error('target_forbidden', 403);
                }
            }
            return true;
        }
        if ('THEME_RELEASE' === ($row['kind'] ?? null)
            && array_key_exists('article_key', $binding) && null === $binding['article_key']
            && 'kurashinoshirube-child' === ($row['payload']['code_package']['slug'] ?? null)) {
            return true;
        }
        return self::error('target_forbidden', 403);
    }

    public function document($request)
    {
        $status = $this->status();
        foreach ($status['targets'] as $target) {
            if ($target['post_id'] === (int) $request['id']) {
                return RAOS_Codex_MCP_Content::document($target['post_id']);
            }
        }
        return self::error('target_forbidden', 403);
    }

    public function ensure_draft($request)
    {
        $input = $this->request_gate($request, array('profile', 'article_key', 'slug', 'idempotency_key'));
        if (is_wp_error($input)) { return $input; }
        if (! self::safe_key($input['article_key']) || ! self::safe_key($input['slug'])
            || ! RAOS_Codex_MCP_Store::is_sha256($input['idempotency_key'])) {
            return self::error('input_invalid', 400);
        }
        global $wpdb;
        $transactional = RAOS_Codex_MCP_Store::require_transactional_tables(array(
            $wpdb->options, $wpdb->posts, $wpdb->postmeta, $wpdb->terms, $wpdb->term_taxonomy, $wpdb->term_relationships,
        ));
        if (is_wp_error($transactional)) { return $transactional; }
        $private = RAOS_Codex_MCP_Deployment::private_directory();
        if (is_wp_error($private)) { return $private; }
        $path = $private . '/owner-direct-drafts.lock';
        if (is_link($path)) { return self::error('lock_unavailable', 503); }
        $lock = @fopen($path, 'c');
        if (false === $lock || ! @chmod($path, 0600) || ! flock($lock, LOCK_EX | LOCK_NB)) {
            if (is_resource($lock)) { fclose($lock); }
            return self::error('lock_unavailable', 409);
        }
        $transaction = false;
        try {
            $target = self::target($input['article_key']);
            if (! is_wp_error($target)) {
                if (($target['idempotency_key'] ?? null) !== $input['idempotency_key'] || $target['slug'] !== $input['slug']) {
                    return self::error('draft_conflict');
                }
                return self::draft_result($target);
            }
            if ('raos_codex_owner_direct_target_forbidden' !== $target->get_error_code()) { return $target; }
            $profile = self::gate();
            if (is_wp_error($profile)) { return $profile; }
            if (true !== $profile['allow_new_posts']) { return self::error('target_forbidden', 403); }
            // One global registry row also serializes independent PHP processes.
            add_option(self::TARGETS_OPTION, '{}', '', false);
            if (false === $wpdb->query('START TRANSACTION')) { return self::error('registry_unavailable', 503); }
            $transaction = true;
            $raw = $wpdb->get_var($wpdb->prepare('SELECT option_value FROM ' . $wpdb->options . ' WHERE option_name = %s FOR UPDATE', self::TARGETS_OPTION));
            $targets = is_string($raw) ? json_decode($raw, true) : null;
            if (! is_array($targets) || ! empty($wpdb->last_error)) { return self::error('registry_unavailable', 503); }
            if (isset($targets[$input['article_key']])) { return self::error('draft_conflict'); }
            foreach ($targets as $existing) {
                if (($existing['idempotency_key'] ?? null) === $input['idempotency_key']) { return self::error('draft_conflict'); }
            }
            $collision = $wpdb->get_var($wpdb->prepare('SELECT ID FROM ' . $wpdb->posts . ' WHERE post_name = %s LIMIT 1 FOR UPDATE', $input['slug']));
            if (! empty($wpdb->last_error)) { return self::error('registry_unavailable', 503); }
            if (null !== $collision) { return self::error('slug_conflict'); }
            $post_id = wp_insert_post(wp_slash(array('post_type' => 'post', 'post_status' => 'draft',
                'post_title' => $input['slug'], 'post_name' => $input['slug'], 'post_content' => '', 'post_author' => $profile['publisher_user_id'])), true);
            if (is_wp_error($post_id) || ! is_int($post_id) || $post_id < 1) { return self::error('draft_create_failed', 500); }
            $post = get_post($post_id);
            if (! $post || $post->post_name !== $input['slug'] || $post->post_type !== 'post' || $post->post_status !== 'draft') {
                return self::error('draft_create_failed', 500);
            }
            $target = array('article_key' => $input['article_key'], 'post_id' => $post_id, 'post_type' => 'post',
                'slug' => $input['slug'], 'idempotency_key' => $input['idempotency_key'], 'publisher_user_id' => $profile['publisher_user_id']);
            $targets[$input['article_key']] = $target;
            $updated = $wpdb->update($wpdb->options, array('option_value' => RAOS_Codex_MCP_Store::canonical_json($targets)), array('option_name' => self::TARGETS_OPTION));
            if (1 !== $updated) { return self::error('registry_unavailable', 503); }
            if (false === $wpdb->query('COMMIT')) {
                // Do not retry INSERT or infer rollback. The next identical request
                // reads the committed registry, binding the same actual post ID.
                return self::error('draft_outcome_unknown', 503);
            }
            $transaction = false;
            return self::draft_result($target);
        } finally {
            if ($transaction) { $wpdb->query('ROLLBACK'); }
            if (isset($post_id) && is_int($post_id)) { clean_post_cache($post_id); }
            wp_cache_delete(self::TARGETS_OPTION, 'options');
            flock($lock, LOCK_UN); fclose($lock);
        }
    }

    private static function draft_result($target)
    {
        $document = RAOS_Codex_MCP_Content::document($target['post_id']);
        if (is_wp_error($document)) { return $document; }
        if ($document['slug'] !== $target['slug'] || $document['post_type'] !== $target['post_type']) { return self::error('draft_conflict'); }
        return array('schema' => 'RAOSOwnerDirectDraftV1', 'profile' => self::PROFILE,
            'article_key' => $target['article_key'], 'id' => $target['post_id'], 'document' => $document);
    }

    private static function safe_key($value)
    {
        return is_string($value) && strlen($value) <= 120
            && preg_match('/\A[a-z0-9]+(?:-[a-z0-9]+)*\z/D', $value) === 1;
    }

    public function content_proposal($request)
    {
        $input = $this->request_gate($request, array('profile', 'article_key', 'id', 'precondition', 'document', 'idempotency_key'));
        if (is_wp_error($input)) { return $input; }
        $binding = $this->binding($input['article_key']);
        $target = self::target($input['article_key']);
        if (is_wp_error($target)) { return $target; }
        if ($target['post_id'] !== $input['id'] || ! is_array($input['document'])
            || ($input['document']['slug'] ?? null) !== $target['slug']) { return self::error('target_forbidden', 403); }
        unset($input['profile'], $input['article_key']);
        $content = new RAOS_Codex_MCP_Content($this->plugin);
        return $content->content_propose_release($input, $binding);
    }

    public function theme_proposal($request)
    {
        $input = $this->request_gate($request, array('profile', 'kind', 'code_package', 'package_base64', 'idempotency_key'));
        if (is_wp_error($input)) { return $input; }
        if ('theme_release' !== $input['kind'] || ! is_array($input['code_package'])
            || 'kurashinoshirube-child' !== ($input['code_package']['slug'] ?? null)) { return self::error('target_forbidden', 403); }
        unset($input['profile']);
        $inner = new WP_REST_Request('POST');
        $inner->set_header('Content-Type', 'application/json');
        $inner->set_body(RAOS_Codex_MCP_Store::canonical_json($input));
        $deployment = new RAOS_Codex_MCP_Deployment($this->plugin);
        return $deployment->create_proposal($inner, $this->binding());
    }

    public function authorize($request)
    {
        $input = $this->request_gate($request, array('profile', 'proposal_ids', 'expected_theme_tree_sha256'));
        if (is_wp_error($input)) { return $input; }
        if (! is_array($input['proposal_ids']) || empty($input['proposal_ids']) || count($input['proposal_ids']) > 20
            || ! RAOS_Codex_MCP_Store::is_sha256($input['expected_theme_tree_sha256'])) { return self::error('input_invalid', 400); }
        foreach ($input['proposal_ids'] as $id) {
            $row = RAOS_Codex_MCP_Store::get($id);
            if (is_wp_error($row)) { return $row; }
            $valid = self::validate_binding($row);
            if (is_wp_error($valid)) { return $valid; }
        }
        $batch = RAOS_Codex_MCP_Store::register_publication_batch($input['proposal_ids'], $input['expected_theme_tree_sha256']);
        if (is_wp_error($batch)) { return $batch; }
        $result = RAOS_Codex_MCP_Store::approve_publication_batch($batch['batch_token'], $batch['batch_manifest_sha256'],
            get_current_user_id(), 'Owner-direct-v1 delegated publication lease.', true);
        if (is_wp_error($result)) { return $result; }
        $batch = RAOS_Codex_MCP_Store::get_publication_batch($batch['batch_token']);
        return is_wp_error($batch) ? $batch : RAOS_Codex_MCP_Store::public_publication_batch($batch);
    }

    public function finish($request)
    {
        $input = $this->request_gate($request, array('profile', 'batch_manifest_sha256', 'action'));
        if (is_wp_error($input)) { return $input; }
        if (! RAOS_Codex_MCP_Store::is_sha256($input['batch_manifest_sha256'])
            || ! in_array($input['action'], array('finalize', 'rollback'), true)) { return self::error('input_invalid', 400); }
        return RAOS_Codex_MCP_Deployment::finish_owner_direct_batch($request['batch_token'], $input['batch_manifest_sha256'], $input['action']);
    }

    public static function remember_applied_content($row, $document)
    {
        $name = 'raos_codex_owner_direct_undo_' . $row['proposal_id'];
        $undo = array('applied_document' => $document,
            'public_before' => get_option('raos_codex_owner_direct_public_' . $document['id'], null));
        update_option($name, $undo, false);
        return get_option($name, null) === $undo ? true : self::error('undo_unavailable', 503);
    }

    /** A public projection is materialized only after the existing apply engine commits. */
    public static function materialize_public_snapshot($row)
    {
        if (! self::is_direct($row) || 'CONTENT_RELEASE' !== $row['kind'] || 'APPLIED' !== $row['state']) { return true; }
        $after = $row['payload']['after'];
        $current = RAOS_Codex_MCP_Content::document($after['id']);
        if (is_wp_error($current) || ! hash_equals($row['after_sha256'], $current['content_sha256'])) {
            return self::error('public_snapshot_drift');
        }
        $snapshot = array_intersect_key($after, array_flip(array('id', 'post_type', 'slug', 'title', 'excerpt', 'block_markup', 'content_sha256')));
        $name = 'raos_codex_owner_direct_public_' . $after['id'];
        update_option($name, $snapshot, false);
        return get_option($name, null) === $snapshot ? true : self::error('public_snapshot_write_failed', 503);
    }

    public static function public_article_snapshot($post_id)
    {
        $snapshot = get_option('raos_codex_owner_direct_public_' . (int) $post_id, null);
        if (! is_array($snapshot) || ! isset($snapshot['content_sha256'])) { return null; }
        $current = RAOS_Codex_MCP_Content::document((int) $post_id);
        if (is_wp_error($current) || 'publish' !== $current['status']
            || ! hash_equals($snapshot['content_sha256'], $current['content_sha256'])) { return null; }
        return $snapshot;
    }

    public static function is_direct_article($post_id)
    {
        $snapshot = get_option('raos_codex_owner_direct_public_' . (int) $post_id, null);
        return is_array($snapshot) && ($snapshot['id'] ?? null) === (int) $post_id;
    }

    public function render_setup()
    {
        if (! current_user_can('manage_options')) { return; }
        $profile = self::profile();
        echo '<h2>Owner-direct-v1 publishing</h2><p>One-time delegation for bounded articles and kurashinoshirube-child. Disabled until saved by a human administrator. Existing editor/operator accounts are not promoted.</p>';
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
        echo '<input type="hidden" name="action" value="raos_codex_owner_direct_setup">';
        wp_nonce_field('raos_codex_owner_direct_setup');
        echo '<p><label><input type="checkbox" name="enabled" value="1" ' . checked(true, $profile['enabled'] ?? false, false) . '> Enable owner-direct-v1</label></p>';
        echo '<p><label>Dedicated publisher user ID <input type="number" min="1" name="publisher_user_id" value="' . esc_attr($profile['publisher_user_id'] ?? '') . '" required></label></p>';
        echo '<p><label><input type="checkbox" name="allow_new_posts" value="1" ' . checked(true, $profile['allow_new_posts'] ?? false, false) . '> Allow new posts created and owned by this publisher</label></p>';
        echo '<p><label>Existing targets (JSON array: article_key, post_id, post_type, slug)<br><textarea name="targets" rows="6" cols="90">' . esc_textarea(wp_json_encode($profile['targets'] ?? array())) . '</textarea></label></p>';
        echo '<button type="submit" class="button button-primary">Save delegation</button></form>';
    }

    public function handle_setup()
    {
        if (! current_user_can('manage_options') || is_multisite()
            || ! RAOS_Codex_MCP_Abilities::human_admin_session()) { wp_die('Human administrator session required.'); }
        check_admin_referer('raos_codex_owner_direct_setup');
        $publisher_id = isset($_POST['publisher_user_id']) ? (int) $_POST['publisher_user_id'] : 0;
        $user = get_user_by('id', $publisher_id);
        if (! $user || $publisher_id === get_current_user_id()
            || array(self::PUBLISHER_ROLE) !== array_values($user->roles)
            || array(self::PUBLISHER_ROLE => true) !== $user->caps) { wp_die('A separate dedicated publisher role account is required.'); }
        $targets = isset($_POST['targets']) ? json_decode(wp_unslash($_POST['targets']), true) : null;
        if (! is_array($targets) || count($targets) > 200 || array_values($targets) !== $targets) { wp_die('Target list invalid.'); }
        $seen = array();
        foreach ($targets as $target) {
            if (! is_array($target) || count($target) !== 4 || ! isset($target['article_key'], $target['post_id'], $target['post_type'], $target['slug'])
                || ! self::safe_key($target['article_key']) || ! is_int($target['post_id']) || $target['post_id'] < 1
                || ! in_array($target['post_type'], array('post', 'page'), true) || ! is_string($target['slug'])
                || isset($seen[$target['article_key']]) || isset($seen['id:' . $target['post_id']])) { wp_die('Target identity invalid.'); }
            $document = RAOS_Codex_MCP_Content::document($target['post_id']);
            if (is_wp_error($document) || $document['slug'] !== $target['slug'] || $document['post_type'] !== $target['post_type']) { wp_die('Target identity does not match WordPress.'); }
            $seen[$target['article_key']] = true; $seen['id:' . $target['post_id']] = true;
        }
        $profile = array('profile' => self::PROFILE, 'enabled' => isset($_POST['enabled']) && '1' === $_POST['enabled'],
            'publisher_user_id' => $publisher_id, 'configured_by' => get_current_user_id(),
            'delegation_id' => bin2hex(random_bytes(32)),
            'allow_new_posts' => isset($_POST['allow_new_posts']) && '1' === $_POST['allow_new_posts'],
            'theme_slug' => 'kurashinoshirube-child', 'targets' => $targets);
        update_option(self::BINDING_OPTION, (string) $publisher_id, false);
        update_option(self::PROFILE_OPTION, $profile, false);
        if ($profile !== get_option(self::PROFILE_OPTION, null)) { wp_die('Delegation save failed.'); }
        wp_safe_redirect(admin_url('tools.php?page=raos-codex-proposals')); exit;
    }
}
