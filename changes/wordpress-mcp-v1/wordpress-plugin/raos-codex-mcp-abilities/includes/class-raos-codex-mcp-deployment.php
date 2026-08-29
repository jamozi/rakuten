<?php
/**
 * Bounded deployment REST surface used by the local stdio MCP bridge.
 *
 * @package RAOS_Codex_MCP_Abilities
 */

defined('ABSPATH') || exit;

final class RAOS_Codex_MCP_Deployment
{
    const MAX_PACKAGE_BYTES = 33554432;
    const MAX_FILE_BYTES = 8388608;
    const MAX_FILE_COUNT = 2048;
    const THEME_SLUG = 'kurashinoshirube-child';

    private $plugin;

    public function __construct($plugin)
    {
        $this->plugin = $plugin;
    }

    public function register_routes()
    {
        register_rest_route(
            'raos-codex-deploy/v1',
            '/status',
            array(
                'methods' => WP_REST_Server::READABLE,
                'callback' => array($this, 'status'),
                'permission_callback' => array($this->plugin, 'operator_rest_permission'),
            )
        );
        register_rest_route(
            'raos-codex-deploy/v1',
            '/proposals',
            array(
                'methods' => WP_REST_Server::CREATABLE,
                'callback' => array($this, 'create_proposal'),
                'permission_callback' => array($this->plugin, 'operator_rest_permission'),
            )
        );
        register_rest_route(
            'raos-codex-deploy/v1',
            '/proposals/(?P<proposal_id>[0-9a-f]{64})/apply',
            array(
                'methods' => WP_REST_Server::CREATABLE,
                'callback' => array($this, 'apply_proposal'),
                'permission_callback' => array($this->plugin, 'operator_rest_permission'),
            )
        );
        register_rest_route(
            'raos-codex-deploy/v1',
            '/operations/(?P<operation_id>[0-9a-f]{64})/recover',
            array(
                'methods' => WP_REST_Server::CREATABLE,
                'callback' => array($this, 'recover_operation'),
                'permission_callback' => array($this->plugin, 'operator_rest_permission'),
            )
        );
    }

    public function status()
    {
        $theme = wp_get_theme(self::THEME_SLUG);
        $private_ready = ! is_wp_error(self::private_directory());
        $apply_ready = self::gate('RAOS_OPERATOR_WRITES_ENABLED') && $private_ready;
        $theme_hash = $theme->exists()
            ? self::tree_hash(get_theme_root(self::THEME_SLUG) . '/' . self::THEME_SLUG)
            : null;
        if (is_wp_error($theme_hash)) {
            $theme_hash = null;
        }
        return array(
            'schema' => 'RAOSWordPressDeploymentStatusV1',
            'origin' => home_url(),
            'php_version' => PHP_VERSION,
            'wordpress_version' => get_bloginfo('version'),
            'theme' => array(
                'slug' => self::THEME_SLUG,
                'version' => $theme->exists() ? (string) $theme->get('Version') : null,
                'active' => get_stylesheet() === self::THEME_SLUG,
                'tree_sha256' => $theme_hash,
            ),
            'gates' => array(
                'global' => self::gate('RAOS_OPERATOR_WRITES_ENABLED'),
                'content_apply' => $apply_ready,
                'theme_apply' => $apply_ready,
                'plugin_apply' => $apply_ready,
            ),
            'apply_authorization' => array(
                'mode' => 'approval_scoped_lease',
                'default' => false,
                'single_use' => true,
                'ttl_seconds' => RAOS_Codex_MCP_Store::TTL_SECONDS,
            ),
            'private_directory_ready' => $private_ready,
        );
    }

    public function create_proposal(WP_REST_Request $request)
    {
        $input = $request->get_json_params();
        if (! is_array($input)
            || ! self::has_exact_keys($input, array('kind', 'code_package', 'package_base64'))
            || ! in_array($input['kind'], array('theme_release', 'plugin_change'), true)
            || ! is_array($input['code_package'])
            || ! is_string($input['package_base64'])
            || strlen($input['package_base64']) > (int) ceil(self::MAX_PACKAGE_BYTES * 4 / 3) + 8) {
            return self::error('raos_codex_package_proposal_invalid', 400);
        }
        $package = base64_decode($input['package_base64'], true);
        if (! is_string($package) || ! strlen($package) || strlen($package) > self::MAX_PACKAGE_BYTES) {
            return self::error('raos_codex_package_payload_invalid', 400);
        }
        $expected_kind = 'theme_release' === $input['kind'] ? 'theme' : 'plugin';
        $validated = self::validate_code_package($input['code_package'], $package, $expected_kind);
        if (is_wp_error($validated)) {
            return $validated;
        }
        $provenance = self::verify_package_provenance($validated, $package);
        if (is_wp_error($provenance)) {
            return $provenance;
        }
        $target = self::target_status($validated);
        if (is_wp_error($target)) {
            return $target;
        }
        $validated['old_version'] = $target['version'];
        $private = self::private_directory();
        if (is_wp_error($private)) {
            return $private;
        }
        try {
            $filename = 'package-' . bin2hex(random_bytes(24)) . '.zip';
        } catch (Throwable $error) {
            unset($error);
            return self::error('raos_codex_random_unavailable', 500);
        }
        $package_path = $private . '/' . $filename;
        if (! self::write_exclusive_file($package_path, $package)
            || ! self::secure_staged_file($package_path)) {
            @unlink($package_path);
            return self::error('raos_codex_package_stage_failed', 500);
        }
        $kind = 'theme' === $expected_kind ? 'THEME_RELEASE' : 'PLUGIN_CHANGE';
        $payload = array(
            'schema' => 'CodeReleaseProposalV1',
            'kind' => $kind,
            'code_package' => $validated,
            'before_tree_sha256' => $target['tree_sha256'],
            'after_tree_sha256' => $validated['file_manifest_sha256'],
            'target_active' => $target['active'],
        );
        $row = RAOS_Codex_MCP_Store::create(
            $kind,
            $payload,
            $target['tree_sha256'],
            $validated['file_manifest_sha256'],
            (bool) $validated['automatic_apply_eligible'],
            $package_path
        );
        if (is_wp_error($row)) {
            @unlink($package_path);
            return $row;
        }
        return array(
            'proposal' => $row['payload'],
            'operation' => RAOS_Codex_MCP_Store::public_operation($row),
        );
    }

    public function apply_proposal(WP_REST_Request $request)
    {
        $proposal_id = $request['proposal_id'];
        if (! RAOS_Codex_MCP_Store::is_sha256($proposal_id)) {
            return self::error('raos_codex_proposal_id_invalid', 400);
        }
        $header_result = self::verify_apply_headers($request, $proposal_id);
        if (is_wp_error($header_result)) {
            return $header_result;
        }
        $row = RAOS_Codex_MCP_Store::get($proposal_id);
        if (is_wp_error($row)) {
            return $row;
        }
        if ('APPLIED' === $row['state'] && is_array($row['receipt'])) {
            return $row['receipt'];
        }
        $gate = self::apply_gate($row['kind']);
        if (is_wp_error($gate)) {
            return $gate;
        }
        $claimed = RAOS_Codex_MCP_Store::claim_apply($proposal_id);
        if (is_wp_error($claimed)) {
            return $claimed;
        }
        if ('APPLIED' === $claimed['state'] && is_array($claimed['receipt'])) {
            return $claimed['receipt'];
        }
        $authorization = self::validate_approval_lease($claimed);
        if (is_wp_error($authorization)) {
            RAOS_Codex_MCP_Store::mark_failed(
                $proposal_id,
                'RAOS_CODEX_APPROVAL_LEASE_INVALID'
            );
            return $authorization;
        }
        try {
            if ('CONTENT_RELEASE' === $claimed['kind']) {
                $receipt = $this->apply_content($claimed);
            } elseif (in_array($claimed['kind'], array('THEME_RELEASE', 'PLUGIN_CHANGE'), true)) {
                $receipt = $this->apply_code($claimed);
            } else {
                $receipt = self::error('raos_codex_operation_kind_invalid', 409);
            }
        } catch (Throwable $error) {
            unset($error);
            $receipt = self::error('raos_codex_operation_failed', 500);
        }
        if (is_wp_error($receipt)) {
            $code = strtoupper(str_replace('-', '_', $receipt->get_error_code()));
            if (preg_match('/\A[A-Z0-9_]{3,96}\z/D', $code) !== 1) {
                $code = 'OPERATION_FAILED';
            }
            RAOS_Codex_MCP_Store::mark_failed($proposal_id, $code);
        }
        return $receipt;
    }

    public function recover_operation(WP_REST_Request $request)
    {
        $operation_id = $request['operation_id'];
        $row = RAOS_Codex_MCP_Store::get($operation_id);
        if (is_wp_error($row)) {
            return $row;
        }
        if ('APPLIED' === $row['state'] && is_array($row['receipt'])) {
            return $row['receipt'];
        }
        if ('APPLYING' !== $row['state']) {
            return RAOS_Codex_MCP_Store::public_operation($row);
        }
        if ('CONTENT_RELEASE' === $row['kind']) {
            $after = $row['payload']['after'];
            $current = isset($after['id']) ? RAOS_Codex_MCP_Content::document((int) $after['id']) : null;
            $current_hash = is_array($current) ? $current['content_sha256'] : null;
            $target = null;
        } else {
            $code_package = isset($row['payload']['code_package'])
                ? $row['payload']['code_package']
                : null;
            $target = is_array($code_package) ? self::target_path($code_package) : null;
            $current_hash = is_string($target) && is_dir($target) ? self::tree_hash($target) : null;
            if (is_wp_error($current_hash)) {
                $current_hash = null;
            }
        }
        if (is_string($current_hash) && hash_equals($row['after_sha256'], $current_hash)) {
            return RAOS_Codex_MCP_Store::complete(
                $row['proposal_id'],
                'OPERATION_RECOVERED_AFTER_READBACK',
                $row['before_sha256'],
                $current_hash
            );
        }
        if ((is_null($row['before_sha256']) && is_null($current_hash))
            || (is_string($current_hash)
                && is_string($row['before_sha256'])
                && hash_equals($row['before_sha256'], $current_hash))) {
            RAOS_Codex_MCP_Store::mark_failed(
                $row['proposal_id'],
                'OPERATION_RECOVERED_AT_BEFORE_STATE'
            );
            $updated = RAOS_Codex_MCP_Store::get($row['proposal_id']);
            return is_wp_error($updated)
                ? $updated
                : RAOS_Codex_MCP_Store::public_operation($updated);
        }
        $gate = self::apply_gate($row['kind']);
        if (is_wp_error($gate)) {
            return $gate;
        }
        $authorization = self::validate_approval_lease($row);
        if (is_wp_error($authorization)) {
            return $authorization;
        }
        if ('CONTENT_RELEASE' === $row['kind']
            && isset($row['payload']['before'])
            && is_array($row['payload']['before'])) {
            $rollback = self::write_content_document($row['payload']['before']);
            $readback = RAOS_Codex_MCP_Content::document(
                (int) $row['payload']['before']['id']
            );
            if (! is_wp_error($rollback)
                && is_array($readback)
                && is_string($row['before_sha256'])
                && hash_equals($row['before_sha256'], $readback['content_sha256'])) {
                RAOS_Codex_MCP_Store::mark_failed(
                    $row['proposal_id'],
                    'OPERATION_RECOVERED_BY_CONTENT_ROLLBACK'
                );
                $updated = RAOS_Codex_MCP_Store::get($row['proposal_id']);
                return is_wp_error($updated)
                    ? $updated
                    : RAOS_Codex_MCP_Store::public_operation($updated);
            }
        }
        if (is_string($target)
            && ! file_exists($target)
            && is_string($row['before_sha256'])) {
            $private = self::private_directory();
            $backup = is_wp_error($private)
                ? null
                : $private . '/operation-' . $row['proposal_id'] . '/before';
            $backup_hash = is_string($backup) && is_dir($backup)
                ? self::tree_hash($backup)
                : null;
            if (is_string($backup_hash)
                && hash_equals($row['before_sha256'], $backup_hash)
                && @rename($backup, $target)) {
                $restored = self::tree_hash($target);
                if (is_string($restored)
                    && hash_equals($row['before_sha256'], $restored)) {
                    RAOS_Codex_MCP_Store::mark_failed(
                        $row['proposal_id'],
                        'OPERATION_RECOVERED_BY_CODE_ROLLBACK'
                    );
                    $updated = RAOS_Codex_MCP_Store::get($row['proposal_id']);
                    return is_wp_error($updated)
                        ? $updated
                        : RAOS_Codex_MCP_Store::public_operation($updated);
                }
            }
        }
        return self::error('raos_codex_recovery_indeterminate', 409);
    }

    private function apply_content($row)
    {
        $payload = $row['payload'];
        if (! isset($payload['before'], $payload['after'])
            || ! is_array($payload['before'])
            || ! is_array($payload['after'])) {
            return self::error('raos_codex_content_proposal_corrupt', 500);
        }
        $before = $payload['before'];
        $after = $payload['after'];
        if (! isset($before['id'], $after['id']) || (int) $before['id'] !== (int) $after['id']) {
            return self::error('raos_codex_content_proposal_corrupt', 500);
        }
        $current = RAOS_Codex_MCP_Content::document((int) $before['id']);
        if (is_wp_error($current)
            || ! hash_equals($row['before_sha256'], $current['content_sha256'])
            || (int) $current['revision_id'] !== (int) $before['revision_id']
            || ! hash_equals($current['modified_gmt'], $before['modified_gmt'])) {
            return self::error('raos_codex_content_hash_drift', 412);
        }
        $references = RAOS_Codex_MCP_Content::validate_release_references($after);
        if (is_wp_error($references)) {
            return $references;
        }
        $write = self::write_content_document($after);
        if (is_wp_error($write)) {
            self::write_content_document($before);
            return $write;
        }
        $readback = RAOS_Codex_MCP_Content::document((int) $after['id']);
        if (is_wp_error($readback)
            || ! hash_equals($row['after_sha256'], $readback['content_sha256'])) {
            self::write_content_document($before);
            return self::error('raos_codex_content_readback_failed', 500);
        }
        return RAOS_Codex_MCP_Store::complete(
            $row['proposal_id'],
            'CONTENT_RELEASE_APPLIED',
            $current['content_sha256'],
            $readback['content_sha256']
        );
    }

    private static function write_content_document($document)
    {
        $required = array(
            'post_type',
            'id',
            'status',
            'title',
            'slug',
            'excerpt',
            'block_markup',
            'taxonomies',
            'media_ids',
            'content_sha256',
        );
        if (! is_array($document)
            || array_diff($required, array_keys($document))
            || ! in_array($document['post_type'], array('post', 'page'), true)
            || ! in_array($document['status'], array('draft', 'publish'), true)
            || RAOS_Codex_MCP_Content::document_hash($document) !== $document['content_sha256']) {
            return self::error('raos_codex_content_document_invalid', 500);
        }
        $updated = wp_update_post(
            array(
                'ID' => (int) $document['id'],
                'post_type' => $document['post_type'],
                'post_status' => $document['status'],
                'post_title' => $document['title'],
                'post_name' => $document['slug'],
                'post_excerpt' => $document['excerpt'],
                'post_content' => $document['block_markup'],
            ),
            true
        );
        if (is_wp_error($updated)) {
            return self::error('raos_codex_content_write_failed', 500);
        }
        return RAOS_Codex_MCP_Content::apply_taxonomies(
            (int) $document['id'],
            $document['post_type'],
            $document['taxonomies']
        );
    }

    private function apply_code($row)
    {
        $payload = $row['payload'];
        if (! isset($payload['code_package']) || ! is_array($payload['code_package'])) {
            return self::error('raos_codex_code_proposal_corrupt', 500);
        }
        $descriptor = $payload['code_package'];
        if (empty($descriptor['automatic_apply_eligible'])
            || 'NO_IRREVERSIBLE_MIGRATION_SIGNALS' !== $descriptor['migration_assessment']) {
            return self::error('raos_codex_migration_manual_required', 409);
        }
        $package_path = $row['package_path'];
        if (! is_string($package_path) || ! self::secure_staged_file($package_path)) {
            return self::error('raos_codex_package_stage_invalid', 500);
        }
        $package = @file_get_contents($package_path);
        if (! is_string($package) || ! hash_equals($descriptor['package_sha256'], hash('sha256', $package))) {
            return self::error('raos_codex_package_digest_mismatch', 412);
        }
        $validated = self::validate_code_package($descriptor, $package, $descriptor['kind']);
        if (is_wp_error($validated)) {
            return $validated;
        }
        $target = self::target_path($descriptor);
        if (! is_string($target)) {
            return self::error('raos_codex_code_target_invalid', 500);
        }
        $current_hash = is_dir($target) ? self::tree_hash($target) : null;
        if (is_wp_error($current_hash)
            || (is_null($row['before_sha256']) && ! is_null($current_hash))
            || (is_string($row['before_sha256'])
                && (! is_string($current_hash) || ! hash_equals($row['before_sha256'], $current_hash)))) {
            return self::error('raos_codex_code_hash_drift', 412);
        }
        $private = self::private_directory();
        if (is_wp_error($private)) {
            return $private;
        }
        $target_parent = dirname($target);
        $private_stat = @stat($private);
        $target_parent_stat = @stat($target_parent);
        if (! is_array($private_stat)
            || ! is_array($target_parent_stat)
            || $private_stat['dev'] !== $target_parent_stat['dev']) {
            return self::error('raos_codex_atomic_filesystem_required', 503);
        }
        $operation_root = $private . '/operation-' . $row['proposal_id'];
        $extract_root = $operation_root . '/new';
        $backup_root = $operation_root . '/before';
        if (file_exists($operation_root) || ! @mkdir($operation_root, 0700, false)) {
            return self::error('raos_codex_operation_directory_failed', 500);
        }
        @chmod($operation_root, 0700);
        $zip = new ZipArchive();
        if (true !== $zip->open($package_path, ZipArchive::RDONLY)
            || ! @mkdir($extract_root, 0700, false)
            || ! $zip->extractTo($extract_root)) {
            if ($zip->status === ZipArchive::ER_OK) {
                $zip->close();
            }
            self::remove_tree($operation_root);
            return self::error('raos_codex_package_extract_failed', 500);
        }
        $zip->close();
        $new_root = $extract_root . '/' . $descriptor['slug'];
        $new_hash = self::tree_hash($new_root);
        if (is_wp_error($new_hash) || ! hash_equals($descriptor['file_manifest_sha256'], $new_hash)) {
            self::remove_tree($operation_root);
            return self::error('raos_codex_extracted_digest_mismatch', 412);
        }
        $plugin_state = null;
        if ('plugin' === $descriptor['kind']) {
            $plugin_state = self::plugin_state($descriptor['slug'], $new_root);
            if (is_wp_error($plugin_state)) {
                self::remove_tree($operation_root);
                return $plugin_state;
            }
        }
        if (is_dir($target) && ! @rename($target, $backup_root)) {
            self::remove_tree($operation_root);
            return self::error('raos_codex_backup_failed', 500);
        }
        if (! @rename($new_root, $target)) {
            if (is_dir($backup_root)) {
                @rename($backup_root, $target);
            }
            self::remove_tree($operation_root);
            return self::error('raos_codex_code_install_failed', 500);
        }
        $activation = true;
        if ('plugin' === $descriptor['kind']) {
            try {
                $activation = self::apply_plugin_intent($descriptor, $plugin_state);
            } catch (Throwable $error) {
                unset($error);
                $activation = self::error('raos_codex_plugin_activation_failed', 500);
            }
        }
        $readback = self::tree_hash($target);
        if (is_wp_error($activation)
            || is_wp_error($readback)
            || ! hash_equals($descriptor['file_manifest_sha256'], $readback)) {
            self::remove_tree($target);
            if (is_dir($backup_root)) {
                @rename($backup_root, $target);
            }
            if ('plugin' === $descriptor['kind'] && is_array($plugin_state)) {
                self::restore_plugin_state($plugin_state);
            }
            return self::error('raos_codex_code_readback_failed', 500);
        }
        self::remove_tree($extract_root);
        return RAOS_Codex_MCP_Store::complete(
            $row['proposal_id'],
            'theme' === $descriptor['kind'] ? 'THEME_RELEASE_APPLIED' : 'PLUGIN_CHANGE_APPLIED',
            $current_hash,
            $readback
        );
    }

    private static function validate_code_package($descriptor, $package, $expected_kind)
    {
        $required = array(
            'schema',
            'kind',
            'source',
            'artifact_id',
            'git_commit',
            'slug',
            'old_version',
            'new_version',
            'package_sha256',
            'file_manifest_sha256',
            'file_manifest',
            'activation_intent',
            'migration_assessment',
            'automatic_apply_eligible',
        );
        if (! is_array($descriptor)
            || ! self::has_exact_keys($descriptor, $required)
            || 'CodePackageV1' !== $descriptor['schema']
            || $descriptor['kind'] !== $expected_kind
            || ! in_array($expected_kind, array('theme', 'plugin'), true)
            || ! is_string($package)
            || strlen($package) < 1
            || strlen($package) > self::MAX_PACKAGE_BYTES
            || ! RAOS_Codex_MCP_Store::is_sha256($descriptor['package_sha256'])
            || ! hash_equals($descriptor['package_sha256'], hash('sha256', $package))
            || ! RAOS_Codex_MCP_Store::is_sha256($descriptor['file_manifest_sha256'])
            || ! is_array($descriptor['file_manifest'])
            || ! is_bool($descriptor['automatic_apply_eligible'])
            || ! in_array($descriptor['activation_intent'], array('preserve', 'activate', 'deactivate'), true)
            || ! is_string($descriptor['slug'])
            || preg_match('/\A[a-z0-9]+(?:-[a-z0-9]+)*\z/D', $descriptor['slug']) !== 1
            || ! is_string($descriptor['new_version'])
            || preg_match('/\A[0-9]+(?:\.[0-9]+){1,3}(?:[-+][0-9A-Za-z.-]+)?\z/D', $descriptor['new_version']) !== 1) {
            return self::error('raos_codex_code_package_invalid', 400);
        }
        if ('theme' === $expected_kind) {
            if ('tracked_child_theme' !== $descriptor['source']
                || self::THEME_SLUG !== $descriptor['slug']
                || ! is_null($descriptor['artifact_id'])
                || ! is_string($descriptor['git_commit'])
                || preg_match('/\A[0-9a-f]{40}\z/D', $descriptor['git_commit']) !== 1
                || 'preserve' !== $descriptor['activation_intent']) {
                return self::error('raos_codex_theme_source_refused', 400);
            }
        } elseif (! in_array($descriptor['source'], array('wordpress_org', 'repo_artifact'), true)
            || ! is_null($descriptor['git_commit'])
            || ('wordpress_org' === $descriptor['source'] && ! is_null($descriptor['artifact_id']))
            || ('repo_artifact' === $descriptor['source']
                && (! is_string($descriptor['artifact_id'])
                    || preg_match('/\A[a-z0-9][a-z0-9._-]{0,127}\z/D', $descriptor['artifact_id']) !== 1))) {
            return self::error('raos_codex_plugin_source_refused', 400);
        }
        if (! class_exists('ZipArchive')) {
            return self::error('raos_codex_zip_unavailable', 503);
        }
        $zip = new ZipArchive();
        $private = self::private_directory();
        if (is_wp_error($private)) {
            return $private;
        }
        try {
            $temporary = $private . '/validate-' . bin2hex(random_bytes(24)) . '.zip';
        } catch (Throwable $error) {
            unset($error);
            return self::error('raos_codex_random_unavailable', 500);
        }
        if (! self::write_exclusive_file($temporary, $package)) {
            return self::error('raos_codex_zip_validation_failed', 500);
        }
        $opened = $zip->open($temporary, ZipArchive::RDONLY);
        if (true !== $opened || $zip->numFiles < 1 || $zip->numFiles > self::MAX_FILE_COUNT) {
            @unlink($temporary);
            return self::error('raos_codex_zip_invalid', 400);
        }
        $manifest = array();
        $seen = array();
        $total = 0;
        $header = null;
        $header_count = 0;
        $migration_signal = false;
        for ($index = 0; $index < $zip->numFiles; $index++) {
            $stat = $zip->statIndex($index, ZipArchive::FL_UNCHANGED);
            if (! is_array($stat) || ! isset($stat['name'], $stat['size']) || ! is_string($stat['name'])) {
                $zip->close();
                @unlink($temporary);
                return self::error('raos_codex_zip_invalid', 400);
            }
            $name = $stat['name'];
            $parts = explode('/', rtrim($name, '/'));
            if ('' === $name
                || str_contains($name, '\\')
                || str_starts_with($name, '/')
                || str_contains($name, "\0")
                || strlen($name) > 300
                || preg_match('/\A[A-Za-z0-9._\/-]+\/?\z/D', $name) !== 1
                || in_array('', $parts, true)
                || in_array('.', $parts, true)
                || in_array('..', $parts, true)
                || $parts[0] !== $descriptor['slug']) {
                $zip->close();
                @unlink($temporary);
                return self::error('raos_codex_zip_path_invalid', 400);
            }
            $folded = strtolower(rtrim($name, '/'));
            if (isset($seen[$folded])) {
                $zip->close();
                @unlink($temporary);
                return self::error('raos_codex_zip_case_collision', 400);
            }
            $seen[$folded] = true;
            $opsys = 0;
            $attributes = 0;
            if ($zip->getExternalAttributesIndex($index, $opsys, $attributes)) {
                $file_type = ($attributes >> 16) & 0170000;
                if (0120000 === $file_type) {
                    $zip->close();
                    @unlink($temporary);
                    return self::error('raos_codex_zip_symlink_refused', 400);
                }
                if (! in_array($file_type, array(0, 0100000, 0040000), true)) {
                    $zip->close();
                    @unlink($temporary);
                    return self::error('raos_codex_zip_special_file_refused', 400);
                }
            }
            if (str_ends_with($name, '/')) {
                continue;
            }
            if ((int) $stat['size'] < 0 || (int) $stat['size'] > self::MAX_FILE_BYTES) {
                $zip->close();
                @unlink($temporary);
                return self::error('raos_codex_zip_file_size_invalid', 400);
            }
            $total += (int) $stat['size'];
            if ($total > self::MAX_PACKAGE_BYTES) {
                $zip->close();
                @unlink($temporary);
                return self::error('raos_codex_zip_expanded_size_invalid', 400);
            }
            $contents = $zip->getFromIndex($index, self::MAX_FILE_BYTES + 1, ZipArchive::FL_UNCHANGED);
            if (! is_string($contents) || strlen($contents) !== (int) $stat['size']) {
                $zip->close();
                @unlink($temporary);
                return self::error('raos_codex_zip_read_invalid', 400);
            }
            $relative = implode('/', array_slice($parts, 1));
            $manifest[] = array(
                'path' => $relative,
                'size' => strlen($contents),
                'sha256' => hash('sha256', $contents),
            );
            if ('theme' === $expected_kind && 'style.css' === $relative) {
                $header = substr($contents, 0, 8192);
                $header_count++;
            }
            if ('plugin' === $expected_kind
                && 2 === count($parts)
                && str_ends_with($relative, '.php')
                && false !== stripos(substr($contents, 0, 8192), 'Plugin Name:')) {
                $header = substr($contents, 0, 8192);
                $header_count++;
            }
            if ('plugin' === $expected_kind && str_ends_with($relative, '.php')) {
                foreach (self::migration_patterns() as $pattern) {
                    if (preg_match($pattern, $contents)) {
                        $migration_signal = true;
                        break;
                    }
                }
            }
        }
        $zip->close();
        @unlink($temporary);
        usort(
            $manifest,
            static function ($left, $right) {
                return strcmp($left['path'], $right['path']);
            }
        );
        $manifest_json = RAOS_Codex_MCP_Store::canonical_json($manifest);
        $declared_json = RAOS_Codex_MCP_Store::canonical_json($descriptor['file_manifest']);
        if (! is_string($manifest_json)
            || ! is_string($declared_json)
            || ! hash_equals($manifest_json, $declared_json)
            || ! hash_equals($descriptor['file_manifest_sha256'], hash('sha256', $manifest_json))
            || ! is_string($header)
            || 1 !== $header_count
            || ! preg_match('/^\s*(?:\*\s*)?Version:\s*([^\r\n]+)/mi', $header, $version_match)
            || trim($version_match[1]) !== $descriptor['new_version']) {
            return self::error('raos_codex_package_manifest_mismatch', 412);
        }
        if (preg_match('/^\s*(?:\*\s*)?Requires at least:\s*([^\r\n]+)/mi', $header, $wp_match)
            && version_compare(get_bloginfo('version'), trim($wp_match[1]), '<')) {
            return self::error('raos_codex_wordpress_compatibility_failed', 409);
        }
        if (preg_match('/^\s*(?:\*\s*)?Requires PHP:\s*([^\r\n]+)/mi', $header, $php_match)
            && version_compare(PHP_VERSION, trim($php_match[1]), '<')) {
            return self::error('raos_codex_php_compatibility_failed', 409);
        }
        if ('theme' === $expected_kind
            && (! preg_match('/^\s*(?:\*\s*)?Template:\s*([^\r\n]+)/mi', $header, $template_match)
                || 'twentytwentyfive' !== trim($template_match[1]))) {
            return self::error('raos_codex_theme_parent_invalid', 409);
        }
        $descriptor['migration_assessment'] = $migration_signal
            ? 'MANUAL_REVIEW_REQUIRED'
            : 'NO_IRREVERSIBLE_MIGRATION_SIGNALS';
        $descriptor['automatic_apply_eligible'] = ! $migration_signal;
        return $descriptor;
    }

    private static function migration_patterns()
    {
        return array(
            '/register_activation_hook\s*\(/i',
            '/\bdbDelta\s*\(/i',
            '/\$wpdb\b/i',
            '/\b(?:ALTER|CREATE|DROP|TRUNCATE)\s+TABLE\b/i',
            '/\b(?:update|add|delete)_site_option\s*\(/i',
            '/\b(?:update|add|delete)_option\s*\(/i',
            '/migrat(?:e|ion|ing)/i',
        );
    }

    private static function verify_package_provenance($descriptor, $package)
    {
        if ('theme' === $descriptor['kind']) {
            return 'tracked_child_theme' === $descriptor['source'];
        }
        if ('repo_artifact' === $descriptor['source']) {
            if (! defined('RAOS_CODEX_REPO_ARTIFACT_HASHES')
                || ! is_array(RAOS_CODEX_REPO_ARTIFACT_HASHES)
                || ! is_string($descriptor['artifact_id'])
                || ! isset(RAOS_CODEX_REPO_ARTIFACT_HASHES[$descriptor['artifact_id']])
                || ! is_string(RAOS_CODEX_REPO_ARTIFACT_HASHES[$descriptor['artifact_id']])
                || ! RAOS_Codex_MCP_Store::is_sha256(
                    RAOS_CODEX_REPO_ARTIFACT_HASHES[$descriptor['artifact_id']]
                )
                || ! hash_equals(
                    RAOS_CODEX_REPO_ARTIFACT_HASHES[$descriptor['artifact_id']],
                    hash('sha256', $package)
                )) {
                return self::error('raos_codex_repo_artifact_not_host_pinned', 409);
            }
            return true;
        }
        if ('wordpress_org' !== $descriptor['source']) {
            return self::error('raos_codex_plugin_source_refused', 400);
        }
        require_once ABSPATH . 'wp-admin/includes/plugin-install.php';
        $metadata = plugins_api(
            'plugin_information',
            array(
                'slug' => $descriptor['slug'],
                'fields' => array('versions' => true),
            )
        );
        if (is_wp_error($metadata)
            || ! is_object($metadata)
            || ! isset($metadata->versions)
            || ! is_array($metadata->versions)
            || ! isset($metadata->versions[$descriptor['new_version']])
            || ! is_string($metadata->versions[$descriptor['new_version']])) {
            return self::error('raos_codex_wordpress_org_version_unavailable', 409);
        }
        $download_url = $metadata->versions[$descriptor['new_version']];
        $parts = wp_parse_url($download_url);
        if (! is_array($parts)
            || ! isset($parts['scheme'], $parts['host'])
            || 'https' !== strtolower($parts['scheme'])
            || 'downloads.wordpress.org' !== strtolower($parts['host'])
            || isset($parts['user'])
            || isset($parts['pass'])
            || isset($parts['fragment'])) {
            return self::error('raos_codex_wordpress_org_url_refused', 409);
        }
        $response = wp_safe_remote_get(
            $download_url,
            array(
                'timeout' => 60,
                'redirection' => 0,
                'limit_response_size' => self::MAX_PACKAGE_BYTES + 1,
                'headers' => array('Accept' => 'application/zip'),
            )
        );
        if (is_wp_error($response)
            || 200 !== wp_remote_retrieve_response_code($response)) {
            return self::error('raos_codex_wordpress_org_download_failed', 503);
        }
        $official = wp_remote_retrieve_body($response);
        if (! is_string($official)
            || strlen($official) < 1
            || strlen($official) > self::MAX_PACKAGE_BYTES
            || ! hash_equals(hash('sha256', $official), hash('sha256', $package))) {
            return self::error('raos_codex_wordpress_org_digest_mismatch', 412);
        }
        return true;
    }

    private static function target_status($descriptor)
    {
        $path = self::target_path($descriptor);
        if (! is_string($path)) {
            return self::error('raos_codex_code_target_invalid', 400);
        }
        $tree = is_dir($path) ? self::tree_hash($path) : null;
        if (is_wp_error($tree)) {
            return $tree;
        }
        if ('theme' === $descriptor['kind']) {
            $theme = wp_get_theme(self::THEME_SLUG);
            if (! $theme->exists() || get_stylesheet() !== self::THEME_SLUG) {
                return self::error('raos_codex_tracked_theme_not_active', 409);
            }
            $version = (string) $theme->get('Version');
            $active = true;
        } else {
            require_once ABSPATH . 'wp-admin/includes/plugin.php';
            $plugins = get_plugins('/' . $descriptor['slug']);
            $version = null;
            $active = false;
            foreach ($plugins as $relative => $metadata) {
                if (is_array($metadata) && ! empty($metadata['Name'])) {
                    $version = isset($metadata['Version']) ? (string) $metadata['Version'] : null;
                    $active = is_plugin_active($descriptor['slug'] . '/' . $relative);
                    break;
                }
            }
        }
        return array('tree_sha256' => $tree, 'version' => $version, 'active' => $active);
    }

    private static function target_path($descriptor)
    {
        if (! is_array($descriptor) || ! isset($descriptor['kind'], $descriptor['slug'])) {
            return null;
        }
        if ('theme' === $descriptor['kind'] && self::THEME_SLUG === $descriptor['slug']) {
            return get_theme_root(self::THEME_SLUG) . '/' . self::THEME_SLUG;
        }
        if ('plugin' === $descriptor['kind']
            && is_string($descriptor['slug'])
            && preg_match('/\A[a-z0-9]+(?:-[a-z0-9]+)*\z/D', $descriptor['slug']) === 1) {
            return WP_PLUGIN_DIR . '/' . $descriptor['slug'];
        }
        return null;
    }

    public static function tree_hash($root)
    {
        if (! is_string($root) || ! is_dir($root) || is_link($root)) {
            return self::error('raos_codex_tree_invalid', 409);
        }
        $root_real = realpath($root);
        if (! is_string($root_real)) {
            return self::error('raos_codex_tree_invalid', 409);
        }
        $manifest = array();
        $seen = array();
        $total = 0;
        try {
            $iterator = new RecursiveIteratorIterator(
                new RecursiveDirectoryIterator($root_real, FilesystemIterator::SKIP_DOTS),
                RecursiveIteratorIterator::LEAVES_ONLY
            );
            foreach ($iterator as $file) {
                if ($file->isLink() || ! $file->isFile()) {
                    return self::error('raos_codex_tree_entry_invalid', 409);
                }
                $path = $file->getPathname();
                $relative = substr($path, strlen($root_real) + 1);
                if (! is_string($relative)
                    || preg_match('/\A[A-Za-z0-9._\/-]+\z/D', $relative) !== 1
                    || strlen($relative) > 300
                    || isset($seen[strtolower($relative)])) {
                    return self::error('raos_codex_tree_path_invalid', 409);
                }
                $seen[strtolower($relative)] = true;
                $size = $file->getSize();
                if ($size < 0 || $size > self::MAX_FILE_BYTES || count($manifest) >= self::MAX_FILE_COUNT) {
                    return self::error('raos_codex_tree_limit_exceeded', 409);
                }
                $total += $size;
                if ($total > self::MAX_PACKAGE_BYTES) {
                    return self::error('raos_codex_tree_limit_exceeded', 409);
                }
                $digest = hash_file('sha256', $path);
                if (! is_string($digest)) {
                    return self::error('raos_codex_tree_read_failed', 500);
                }
                $manifest[] = array('path' => $relative, 'size' => $size, 'sha256' => $digest);
            }
        } catch (UnexpectedValueException $error) {
            unset($error);
            return self::error('raos_codex_tree_read_failed', 500);
        }
        if (empty($manifest)) {
            return self::error('raos_codex_tree_empty', 409);
        }
        usort(
            $manifest,
            static function ($left, $right) {
                return strcmp($left['path'], $right['path']);
            }
        );
        return RAOS_Codex_MCP_Store::hash($manifest);
    }

    private static function plugin_state($slug, $new_root)
    {
        require_once ABSPATH . 'wp-admin/includes/plugin.php';
        $plugins = get_plugins('/' . $slug);
        $old_file = null;
        $old_active = false;
        foreach ($plugins as $relative => $metadata) {
            if (is_array($metadata) && ! empty($metadata['Name'])) {
                $old_file = $slug . '/' . $relative;
                $old_active = is_plugin_active($old_file);
                break;
            }
        }
        $new_main = null;
        foreach (glob($new_root . '/*.php') ?: array() as $candidate) {
            $head = @file_get_contents($candidate, false, null, 0, 8192);
            if (is_string($head) && false !== stripos($head, 'Plugin Name:')) {
                $new_main = $slug . '/' . basename($candidate);
                break;
            }
        }
        if (! is_string($new_main)) {
            return self::error('raos_codex_plugin_main_file_missing', 409);
        }
        return array(
            'old_file' => $old_file,
            'old_active' => $old_active,
            'new_file' => $new_main,
        );
    }

    private static function apply_plugin_intent($descriptor, $state)
    {
        require_once ABSPATH . 'wp-admin/includes/plugin.php';
        if (! is_array($state)) {
            return self::error('raos_codex_plugin_state_invalid', 500);
        }
        if ('deactivate' === $descriptor['activation_intent']) {
            if (is_string($state['old_file'])) {
                deactivate_plugins($state['old_file'], true, false);
            }
            deactivate_plugins($state['new_file'], true, false);
            return is_plugin_active($state['new_file'])
                || (is_string($state['old_file']) && is_plugin_active($state['old_file']))
                ? self::error('raos_codex_plugin_deactivation_failed', 500)
                : true;
        }
        if ('activate' === $descriptor['activation_intent']
            || ('preserve' === $descriptor['activation_intent'] && $state['old_active'])) {
            if (is_string($state['old_file']) && $state['old_file'] !== $state['new_file']) {
                deactivate_plugins($state['old_file'], true, false);
            }
            $result = activate_plugin($state['new_file'], '', false, true);
            return is_wp_error($result) ? self::error('raos_codex_plugin_activation_failed', 500) : true;
        }
        return true;
    }

    private static function restore_plugin_state($state)
    {
        require_once ABSPATH . 'wp-admin/includes/plugin.php';
        if (! is_array($state)) {
            return;
        }
        if (! empty($state['new_file'])) {
            deactivate_plugins($state['new_file'], true, false);
        }
        if (! empty($state['old_active']) && is_string($state['old_file'])) {
            activate_plugin($state['old_file'], '', false, true);
        }
    }

    public static function private_directory()
    {
        if (! defined('RAOS_CODEX_PRIVATE_DIR')
            || ! is_string(RAOS_CODEX_PRIVATE_DIR)
            || '' === RAOS_CODEX_PRIVATE_DIR
            || ! str_starts_with(RAOS_CODEX_PRIVATE_DIR, '/')
            || is_link(RAOS_CODEX_PRIVATE_DIR)
            || ! is_dir(RAOS_CODEX_PRIVATE_DIR)) {
            return self::error('raos_codex_private_directory_unavailable', 503);
        }
        $real = realpath(RAOS_CODEX_PRIVATE_DIR);
        $abspath = realpath(ABSPATH);
        $content = realpath(WP_CONTENT_DIR);
        if (! is_string($real)
            || ! is_string($abspath)
            || ! is_string($content)) {
            return self::error('raos_codex_private_directory_insecure', 503);
        }
        $mode = @fileperms($real);
        if (str_starts_with($real . '/', rtrim($abspath, '/') . '/')
            || str_starts_with($real . '/', rtrim($content, '/') . '/')
            || false === $mode
            || (0700 !== ($mode & 0777))
            || ! is_writable($real)) {
            return self::error('raos_codex_private_directory_insecure', 503);
        }
        return $real;
    }

    public static function create_approval_lease($row, $approver_id, $approved_at_gmt)
    {
        if (! is_array($row)
            || ! isset(
                $row['proposal_id'],
                $row['kind'],
                $row['created_by'],
                $row['expires_at_gmt']
            )
            || ! RAOS_Codex_MCP_Store::is_sha256($row['proposal_id'])
            || ! in_array($row['kind'], array('CONTENT_RELEASE', 'THEME_RELEASE', 'PLUGIN_CHANGE'), true)
            || (int) $approver_id < 1
            || (int) $approver_id === (int) $row['created_by']
            || ! is_string($approved_at_gmt)
            || false === strtotime($approved_at_gmt . ' UTC')) {
            return self::error('raos_codex_approval_lease_input_invalid', 500);
        }
        $private = self::private_directory();
        if (is_wp_error($private)) {
            return $private;
        }
        try {
            $nonce_sha256 = hash('sha256', random_bytes(32));
        } catch (Throwable $error) {
            unset($error);
            return self::error('raos_codex_random_unavailable', 500);
        }
        $material = array(
            'schema' => 'RAOS_CODEX_APPROVAL_LEASE_V1',
            'proposal_id' => $row['proposal_id'],
            'kind' => $row['kind'],
            'created_by' => (int) $row['created_by'],
            'approved_by' => (int) $approver_id,
            'approved_at_gmt' => RAOS_Codex_MCP_Store::timestamp_iso($approved_at_gmt),
            'expires_at_gmt' => RAOS_Codex_MCP_Store::timestamp_iso($row['expires_at_gmt']),
            'before_sha256' => $row['before_sha256'],
            'after_sha256' => $row['after_sha256'],
            'nonce_sha256' => $nonce_sha256,
        );
        $lease_id = RAOS_Codex_MCP_Store::hash($material);
        if (! RAOS_Codex_MCP_Store::is_sha256($lease_id)
            || ! is_string($material['approved_at_gmt'])
            || ! is_string($material['expires_at_gmt'])) {
            return self::error('raos_codex_approval_lease_input_invalid', 500);
        }
        $lease = $material;
        $lease['lease_id'] = $lease_id;
        $payload = RAOS_Codex_MCP_Store::canonical_json($lease);
        $path = self::approval_lease_path($row['proposal_id']);
        if (! is_string($payload)
            || ! is_string($path)
            || ! self::write_exclusive_file($path, $payload)
            || ! self::secure_approval_lease_file($path)) {
            if (is_string($path)) {
                @unlink($path);
            }
            return self::error('raos_codex_approval_lease_create_failed', 500);
        }
        return $lease;
    }

    public static function validate_approval_lease($row)
    {
        if (! is_array($row)
            || ! isset($row['proposal_id'], $row['kind'], $row['created_by'], $row['approved_by'])
            || ! in_array($row['state'], array('APPROVED', 'APPLYING'), true)
            || ! RAOS_Codex_MCP_Store::is_sha256($row['proposal_id'])) {
            return self::error('raos_codex_approval_lease_invalid', 409);
        }
        $path = self::approval_lease_path($row['proposal_id']);
        if (! is_string($path) || ! self::secure_approval_lease_file($path)) {
            return self::error('raos_codex_approval_lease_invalid', 409);
        }
        $payload = @file_get_contents($path);
        $lease = is_string($payload) ? json_decode($payload, true, 8) : null;
        $expected_keys = array(
            'schema',
            'proposal_id',
            'kind',
            'created_by',
            'approved_by',
            'approved_at_gmt',
            'expires_at_gmt',
            'before_sha256',
            'after_sha256',
            'nonce_sha256',
            'lease_id',
        );
        if (! self::has_exact_keys($lease, $expected_keys)) {
            return self::error('raos_codex_approval_lease_invalid', 409);
        }
        $material = $lease;
        $lease_id = $material['lease_id'];
        unset($material['lease_id']);
        $expected_approved_at = RAOS_Codex_MCP_Store::timestamp_iso($row['approved_at_gmt']);
        $expected_expires_at = RAOS_Codex_MCP_Store::timestamp_iso($row['expires_at_gmt']);
        $lease_expires = strtotime($lease['expires_at_gmt']);
        if ('RAOS_CODEX_APPROVAL_LEASE_V1' !== $lease['schema']
            || ! is_string($lease_id)
            || ! RAOS_Codex_MCP_Store::is_sha256($lease_id)
            || ! hash_equals($lease_id, (string) RAOS_Codex_MCP_Store::hash($material))
            || ! hash_equals($row['proposal_id'], (string) $lease['proposal_id'])
            || ! hash_equals($row['kind'], (string) $lease['kind'])
            || (int) $row['created_by'] !== (int) $lease['created_by']
            || (int) $row['approved_by'] !== (int) $lease['approved_by']
            || (int) $row['created_by'] === (int) $row['approved_by']
            || ! is_string($expected_approved_at)
            || ! hash_equals($expected_approved_at, (string) $lease['approved_at_gmt'])
            || ! is_string($expected_expires_at)
            || ! hash_equals($expected_expires_at, (string) $lease['expires_at_gmt'])
            || ! self::nullable_hash_matches($row['before_sha256'], $lease['before_sha256'])
            || ! self::nullable_hash_matches($row['after_sha256'], $lease['after_sha256'])
            || ! RAOS_Codex_MCP_Store::is_sha256($lease['nonce_sha256'])
            || false === $lease_expires
            || ('APPROVED' === $row['state'] && $lease_expires <= time())) {
            return self::error('raos_codex_approval_lease_invalid', 409);
        }
        return true;
    }

    public static function remove_approval_lease($proposal_id)
    {
        $path = self::approval_lease_path($proposal_id);
        if (! is_string($path) || ! file_exists($path)) {
            return true;
        }
        return ! is_link($path) && is_file($path) && @unlink($path);
    }

    private static function approval_lease_path($proposal_id)
    {
        if (! RAOS_Codex_MCP_Store::is_sha256($proposal_id)) {
            return null;
        }
        $private = self::private_directory();
        return is_wp_error($private)
            ? null
            : $private . '/approval-lease-' . $proposal_id . '.json';
    }

    private static function secure_approval_lease_file($path)
    {
        $private = self::private_directory();
        if (is_wp_error($private)
            || ! is_string($path)
            || is_link($path)
            || ! is_file($path)) {
            return false;
        }
        $real = realpath($path);
        $mode = @fileperms($path);
        $metadata = @stat($path);
        $size = @filesize($path);
        return is_string($real)
            && str_starts_with($real, $private . '/approval-lease-')
            && str_ends_with($real, '.json')
            && false !== $mode
            && 0600 === ($mode & 0777)
            && is_array($metadata)
            && 1 === (int) $metadata['nlink']
            && is_int($size)
            && $size > 0
            && $size <= 8192;
    }

    private static function nullable_hash_matches($expected, $actual)
    {
        if (is_null($expected) || is_null($actual)) {
            return is_null($expected) && is_null($actual);
        }
        return RAOS_Codex_MCP_Store::is_sha256($expected)
            && RAOS_Codex_MCP_Store::is_sha256($actual)
            && hash_equals($expected, $actual);
    }

    private static function has_exact_keys($value, $expected)
    {
        if (! is_array($value) || ! is_array($expected)) {
            return false;
        }
        $actual = array_keys($value);
        sort($actual, SORT_STRING);
        sort($expected, SORT_STRING);
        return $actual === $expected;
    }

    private static function write_exclusive_file($path, $payload)
    {
        if (! is_string($path)
            || ! is_string($payload)
            || '' === $payload
            || strlen($payload) > self::MAX_PACKAGE_BYTES) {
            return false;
        }
        $handle = @fopen($path, 'xb');
        if (false === $handle) {
            return false;
        }
        $offset = 0;
        $length = strlen($payload);
        while ($offset < $length) {
            $written = @fwrite($handle, substr($payload, $offset));
            if (! is_int($written) || $written < 1) {
                fclose($handle);
                @unlink($path);
                return false;
            }
            $offset += $written;
        }
        $flushed = @fflush($handle);
        fclose($handle);
        @chmod($path, 0600);
        if (! $flushed) {
            @unlink($path);
            return false;
        }
        return true;
    }

    private static function secure_staged_file($path)
    {
        $private = self::private_directory();
        if (is_wp_error($private) || ! is_string($path) || is_link($path) || ! is_file($path)) {
            return false;
        }
        $real = realpath($path);
        $mode = @fileperms($path);
        $links = @stat($path);
        return is_string($real)
            && str_starts_with($real, $private . '/')
            && false !== $mode
            && 0600 === ($mode & 0777)
            && is_array($links)
            && 1 === (int) $links['nlink']
            && filesize($path) > 0
            && filesize($path) <= self::MAX_PACKAGE_BYTES;
    }

    private static function remove_tree($path)
    {
        if (! is_string($path) || '' === $path || '/' === $path || ! file_exists($path)) {
            return false;
        }
        if (is_link($path) || is_file($path)) {
            return @unlink($path);
        }
        try {
            $iterator = new RecursiveIteratorIterator(
                new RecursiveDirectoryIterator($path, FilesystemIterator::SKIP_DOTS),
                RecursiveIteratorIterator::CHILD_FIRST
            );
            foreach ($iterator as $entry) {
                if ($entry->isLink() || $entry->isFile()) {
                    @unlink($entry->getPathname());
                } else {
                    @rmdir($entry->getPathname());
                }
            }
        } catch (UnexpectedValueException $error) {
            unset($error);
            return false;
        }
        return @rmdir($path);
    }

    private static function apply_gate($kind)
    {
        if (! self::gate('RAOS_OPERATOR_WRITES_ENABLED')) {
            return self::error('raos_codex_global_kill_switch_disabled', 503);
        }
        if (! in_array($kind, array('CONTENT_RELEASE', 'THEME_RELEASE', 'PLUGIN_CHANGE'), true)) {
            return self::error('raos_codex_operation_kind_invalid', 409);
        }
        return true;
    }

    private static function gate($constant)
    {
        return defined($constant) && true === constant($constant);
    }

    private static function verify_apply_headers(WP_REST_Request $request, $proposal_id)
    {
        $if_match = $request->get_header('If-Match');
        $idempotency = $request->get_header('Idempotency-Key');
        if (! is_string($if_match)
            || ! hash_equals('"' . $proposal_id . '"', $if_match)
            || ! is_string($idempotency)
            || ! hash_equals($proposal_id, $idempotency)) {
            return self::error('raos_codex_apply_headers_invalid', 412);
        }
        return true;
    }

    private static function error($code, $status)
    {
        return new WP_Error($code, 'The bounded deployment operation was refused.', array('status' => $status));
    }
}
