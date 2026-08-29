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
            '/publication-batches/(?P<batch_token>[0-9a-f]{64})',
            array(
                'methods' => WP_REST_Server::READABLE,
                'callback' => array($this, 'get_publication_batch'),
                'permission_callback' => array($this->plugin, 'operator_rest_permission'),
            )
        );
        register_rest_route(
            'raos-codex-deploy/v1',
            '/publication-batches/(?P<batch_token>[0-9a-f]{64})/claim',
            array(
                'methods' => WP_REST_Server::CREATABLE,
                'callback' => array($this, 'claim_publication_batch'),
                'permission_callback' => array($this->plugin, 'operator_rest_permission'),
            )
        );
        register_rest_route(
            'raos-codex-deploy/v1',
            '/operations/(?P<operation_id>[0-9a-f]{64})',
            array(
                'methods' => WP_REST_Server::READABLE,
                'callback' => array($this, 'get_operation'),
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
        $theme_hash = $theme->exists() ? self::active_theme_tree_sha256() : null;
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

    public static function active_theme_tree_sha256()
    {
        if (get_stylesheet() !== self::THEME_SLUG) {
            return self::error('raos_codex_active_theme_invalid', 409);
        }
        $target = get_theme_root(self::THEME_SLUG) . '/' . self::THEME_SLUG;
        if (! is_dir($target)) {
            return self::error('raos_codex_active_theme_unavailable', 503);
        }
        $hash = self::tree_hash($target);
        return is_wp_error($hash) || ! RAOS_Codex_MCP_Store::is_sha256($hash)
            ? self::error('raos_codex_active_theme_readback_failed', 503)
            : $hash;
    }

    public function create_proposal(WP_REST_Request $request)
    {
        $input = $request->get_json_params();
        if (! is_array($input)
            || ! self::has_only_keys(
                $input,
                array('kind', 'code_package', 'package_base64'),
                array('idempotency_key')
            )
            || ! in_array($input['kind'], array('theme_release', 'plugin_change'), true)
            || ! is_array($input['code_package'])
            || ! is_string($input['package_base64'])
            || (array_key_exists('idempotency_key', $input)
                && ! RAOS_Codex_MCP_Store::is_sha256($input['idempotency_key']))
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
            $package_path,
            array_key_exists('idempotency_key', $input) ? $input['idempotency_key'] : null
        );
        if (is_wp_error($row)) {
            @unlink($package_path);
            return $row;
        }
        if (! isset($row['package_path'])
            || ! is_string($row['package_path'])
            || ! hash_equals($package_path, $row['package_path'])) {
            @unlink($package_path);
        }
        return array(
            'proposal' => $row['payload'],
            'operation' => RAOS_Codex_MCP_Store::public_operation($row),
        );
    }

    public function get_operation(WP_REST_Request $request)
    {
        $operation_id = $request['operation_id'];
        if (! RAOS_Codex_MCP_Store::is_sha256($operation_id)) {
            return self::error('raos_codex_operation_id_invalid', 400);
        }
        $row = RAOS_Codex_MCP_Store::get($operation_id);
        if (is_wp_error($row)) {
            return $row;
        }
        return array(
            'kind' => $row['kind'],
            'operation' => RAOS_Codex_MCP_Store::public_operation($row),
        );
    }

    public function get_publication_batch(WP_REST_Request $request)
    {
        $batch_token = $request['batch_token'];
        if (! RAOS_Codex_MCP_Store::is_sha256($batch_token)) {
            return self::error('raos_codex_publication_batch_token_invalid', 400);
        }
        $batch = RAOS_Codex_MCP_Store::get_publication_batch($batch_token);
        if (is_wp_error($batch)) {
            return $batch;
        }
        return self::publication_batch_status($batch);
    }

    public function claim_publication_batch(WP_REST_Request $request)
    {
        $batch_token = $request['batch_token'];
        $input = $request->get_json_params();
        if (! RAOS_Codex_MCP_Store::is_sha256($batch_token)
            || ! self::has_exact_keys($input, array('batch_manifest_sha256', 'proposal_ids'))
            || ! RAOS_Codex_MCP_Store::is_sha256($input['batch_manifest_sha256'])
            || ! is_array($input['proposal_ids'])
            || empty($input['proposal_ids'])
            || count($input['proposal_ids']) > 20
            || $input['proposal_ids'] !== array_values($input['proposal_ids'])
            || count(array_unique($input['proposal_ids'])) !== count($input['proposal_ids'])) {
            return self::error('raos_codex_publication_batch_claim_invalid', 400);
        }
        foreach ($input['proposal_ids'] as $proposal_id) {
            if (! RAOS_Codex_MCP_Store::is_sha256($proposal_id)) {
                return self::error('raos_codex_publication_batch_claim_invalid', 400);
            }
        }
        $sorted_ids = $input['proposal_ids'];
        sort($sorted_ids, SORT_STRING);
        if ($sorted_ids !== $input['proposal_ids']) {
            return self::error('raos_codex_publication_batch_claim_invalid', 400);
        }
        $batch = RAOS_Codex_MCP_Store::get_publication_batch($batch_token);
        if (is_wp_error($batch)
            || ! hash_equals($input['batch_manifest_sha256'], (string) $batch['batch_manifest_sha256'])
            || $input['proposal_ids'] !== $batch['proposal_ids']) {
            return self::error('raos_codex_publication_batch_binding_invalid', 412);
        }
        $status = self::publication_batch_status($batch);
        if (is_wp_error($status)
            || 'APPROVED' !== $status['state']
            || true !== $status['preconditions_ready']) {
            return self::error('raos_codex_publication_batch_not_ready', 409);
        }
        return RAOS_Codex_MCP_Store::claim_publication_batch_apply(
            $batch_token,
            $input['batch_manifest_sha256'],
            $input['proposal_ids']
        );
    }

    private static function publication_batch_status($batch)
    {
        if (! is_array($batch)
            || ! isset(
                $batch['batch_token'],
                $batch['batch_manifest_sha256'],
                $batch['proposal_ids'],
                $batch['state'],
                $batch['expires_at_gmt']
            )
            || ! is_array($batch['proposal_ids'])) {
            return self::error('raos_codex_publication_batch_corrupt', 500);
        }
        $proposal_ids = $batch['proposal_ids'];
        sort($proposal_ids, SORT_STRING);
        $approved_batch = 'APPROVED' === $batch['state'];
        $expires_at = strtotime($batch['expires_at_gmt'] . ' UTC');
        $batch_expired = false === $expires_at || $expires_at <= time();
        $ready = $approved_batch;
        $member_started = false;
        $all_members_expired = $approved_batch;
        $all_members_terminal_expired = $approved_batch;
        $all_members_applied = $approved_batch;
        $recovery_only = $approved_batch;
        $expiry_reset_safe = $approved_batch;
        if ($approved_batch) {
            foreach ($proposal_ids as $proposal_id) {
                $row = RAOS_Codex_MCP_Store::get($proposal_id);
                if (is_wp_error($row)) {
                    // Unknown member history cannot be reset automatically.
                    $member_started = true;
                    $all_members_expired = false;
                    $all_members_terminal_expired = false;
                    $all_members_applied = false;
                    $recovery_only = false;
                    $expiry_reset_safe = false;
                    $ready = false;
                    continue;
                }
                $member_expires_at = isset($row['expires_at_gmt'])
                    ? strtotime($row['expires_at_gmt'] . ' UTC')
                    : false;
                $member_expired = false !== $member_expires_at
                    && $member_expires_at <= time();
                $started = in_array($row['state'], array('APPLYING', 'APPLIED', 'FAILED'), true);
                if ($started) {
                    $member_started = true;
                } elseif (! $member_expired) {
                    $all_members_expired = false;
                }
                if ('EXPIRED' !== $row['state'] || ! $member_expired) {
                    $all_members_terminal_expired = false;
                }
                if ('APPLIED' !== $row['state'] || ! is_array($row['receipt'])) {
                    $all_members_applied = false;
                }
                if (false === $member_expires_at
                    || (! $started && ! in_array($row['state'], array('APPROVED', 'EXPIRED'), true))) {
                    $expiry_reset_safe = false;
                }
                if (! in_array($row['state'], array('APPLYING', 'APPLIED'), true)) {
                    $recovery_only = false;
                }
                $target_match = self::proposal_target_matches_immutable_state($row);
                if (is_wp_error($target_match)) {
                    $expiry_reset_safe = false;
                    $ready = false;
                    continue;
                }
                if (! in_array($row['state'], array('APPROVED', 'APPLYING', 'APPLIED'), true)
                    || ('APPROVED' === $row['state'] && $member_expired)
                    || true !== $target_match) {
                    $ready = false;
                    if (true !== $target_match) {
                        // Confirmed drift is not equivalent to expired authority.
                        $expiry_reset_safe = false;
                    }
                }
            }
            $theme_binding = self::publication_batch_theme_precondition_matches($batch);
            if (true !== $theme_binding) {
                $ready = false;
                $expiry_reset_safe = false;
            }
            // Once the batch TTL elapses, no new APPROVED member may be claimed.
            // Exact APPLYING/APPLIED-only sets can still recover response loss.
            if ($batch_expired && ! $recovery_only) {
                $ready = false;
            }
        }
        $derived_state = $batch['state'];
        if ($approved_batch && $all_members_applied) {
            // Persisted exact member receipts are terminal. A later external
            // edit is drift for the next proposal, not retroactive failure of
            // the already completed publication batch.
            $derived_state = 'APPLIED';
        } elseif ($approved_batch && ! $member_started && $all_members_terminal_expired) {
            // Store::get() has atomically revoked every never-started member
            // lease. With no authority left, later target drift cannot keep the
            // obsolete batch in a non-resettable FAILED state.
            $derived_state = 'EXPIRED';
            $ready = false;
        } elseif ($approved_batch && ! $ready) {
            // Only persisted member EXPIRED states above prove every lease was
            // revoked. A stale APPROVED snapshot must never be treated as safe
            // expiry after a failed or lost compare-and-swap.
            $derived_state = 'FAILED';
        }
        return array(
            'schema' => 'RAOSWordPressPublicationBatchStatusV1',
            'batch_token' => $batch['batch_token'],
            'batch_manifest_sha256' => $batch['batch_manifest_sha256'],
            'proposal_count' => count($proposal_ids),
            'proposal_ids' => $proposal_ids,
            'state' => $derived_state,
            'expires_at_gmt' => RAOS_Codex_MCP_Store::timestamp_iso($batch['expires_at_gmt']),
            'preconditions_ready' => $ready,
        );
    }

    private static function validate_publication_batch_apply($request, $row)
    {
        $batch_token = $request->get_header('X-RAOS-Batch-Token');
        $batch_manifest = $request->get_header('X-RAOS-Batch-Manifest-SHA256');
        if ('PLUGIN_CHANGE' === $row['kind']) {
            return (empty($batch_token) && empty($batch_manifest))
                ? true
                : self::error('raos_codex_plugin_batch_headers_refused', 400);
        }
        if (! in_array($row['kind'], array('CONTENT_RELEASE', 'THEME_RELEASE'), true)
            || ! RAOS_Codex_MCP_Store::is_sha256($batch_token)
            || ! RAOS_Codex_MCP_Store::is_sha256($batch_manifest)) {
            return self::error('raos_codex_publication_batch_headers_invalid', 412);
        }
        $batch = RAOS_Codex_MCP_Store::get_publication_batch($batch_token);
        if (is_wp_error($batch)
            || ! hash_equals($batch_manifest, (string) $batch['batch_manifest_sha256'])
            || ! in_array($row['proposal_id'], $batch['proposal_ids'], true)) {
            return self::error('raos_codex_publication_batch_binding_invalid', 412);
        }
        $status = self::publication_batch_status($batch);
        $batch_ready = is_array($status)
            && true === $status['preconditions_ready']
            && ('APPROVED' === $status['state']
                || ('APPLIED' === $status['state'] && 'APPLIED' === $row['state']));
        if (! $batch_ready) {
            return self::error('raos_codex_publication_batch_not_ready', 409);
        }
        if ('CONTENT_RELEASE' === $row['kind']) {
            $theme_ready = self::publication_batch_theme_ready($batch);
            if (true !== $theme_ready) {
                return is_wp_error($theme_ready)
                    ? $theme_ready
                    : self::error('raos_codex_publication_batch_theme_not_applied', 409);
            }
        }
        return $batch;
    }

    private static function publication_batch_theme_ready($batch)
    {
        $binding = self::publication_batch_theme_precondition_matches($batch);
        if (true !== $binding) {
            return $binding;
        }
        if (! is_array($batch)
            || ! isset($batch['proposal_ids'])
            || ! is_array($batch['proposal_ids'])) {
            return self::error('raos_codex_publication_batch_corrupt', 500);
        }
        foreach ($batch['proposal_ids'] as $proposal_id) {
            $member = RAOS_Codex_MCP_Store::get($proposal_id);
            if (is_wp_error($member) || ! isset($member['kind'], $member['state'])) {
                return self::error('raos_codex_publication_batch_precondition_indeterminate', 500);
            }
            if ('THEME_RELEASE' !== $member['kind']) {
                continue;
            }
            $target_match = self::proposal_target_matches_immutable_state($member);
            if (is_wp_error($target_match)) {
                return $target_match;
            }
            if ('APPLIED' !== $member['state'] || true !== $target_match) {
                return false;
            }
        }
        return true;
    }

    private static function publication_batch_theme_precondition_matches($batch)
    {
        if (! is_array($batch)
            || ! isset($batch['proposal_ids'], $batch['manifest'])
            || ! is_array($batch['proposal_ids'])
            || ! is_array($batch['manifest'])
            || ! isset($batch['manifest']['expected_theme_tree_sha256'])
            || ! RAOS_Codex_MCP_Store::is_sha256(
                $batch['manifest']['expected_theme_tree_sha256']
            )) {
            return self::error('raos_codex_publication_batch_corrupt', 500);
        }
        $expected = $batch['manifest']['expected_theme_tree_sha256'];
        $theme_member = null;
        foreach ($batch['proposal_ids'] as $proposal_id) {
            $member = RAOS_Codex_MCP_Store::get($proposal_id);
            if (is_wp_error($member)
                || ! isset($member['kind'], $member['state'], $member['result_code'])
                || ! array_key_exists('after_sha256', $member)) {
                return self::error('raos_codex_publication_batch_precondition_indeterminate', 500);
            }
            if ('THEME_RELEASE' !== $member['kind']) {
                continue;
            }
            if (is_array($theme_member)
                || ! is_string($member['after_sha256'])
                || ! hash_equals($expected, $member['after_sha256'])) {
                return self::error('raos_codex_publication_batch_corrupt', 500);
            }
            $theme_member = $member;
        }
        $current = self::active_theme_tree_sha256();
        if (is_wp_error($current)) {
            return $current;
        }
        if (! is_array($theme_member)) {
            return hash_equals($expected, $current);
        }
        $at_before = is_string($theme_member['before_sha256'])
            && hash_equals($theme_member['before_sha256'], $current);
        $at_after = hash_equals($theme_member['after_sha256'], $current);
        if ('APPROVED' === $theme_member['state']) {
            return 'PROPOSAL_APPROVED' === $theme_member['result_code'] && $at_before;
        }
        if ('APPLYING' === $theme_member['state']) {
            if ('BATCH_CLAIMED' === $theme_member['result_code']) {
                return $at_before;
            }
            return 'OPERATION_APPLYING' === $theme_member['result_code']
                && ($at_before || $at_after);
        }
        return 'APPLIED' === $theme_member['state'] && $at_after;
    }

    private static function proposal_target_matches_immutable_state($row)
    {
        if (! is_array($row)
            || ! isset($row['kind'], $row['payload'], $row['state'])
            || ! array_key_exists('before_sha256', $row)
            || ! array_key_exists('after_sha256', $row)) {
            return self::error('raos_codex_batch_precondition_indeterminate', 500);
        }
        $target_absent = false;
        if ('CONTENT_RELEASE' === $row['kind']) {
            $after = isset($row['payload']['after']) && is_array($row['payload']['after'])
                ? $row['payload']['after']
                : null;
            $current = is_array($after) && isset($after['id'])
                ? RAOS_Codex_MCP_Content::document((int) $after['id'])
                : null;
            if (! is_array($current) || ! isset($current['content_sha256'])) {
                return self::error('raos_codex_batch_precondition_indeterminate', 500);
            }
            $current_hash = is_array($current) && isset($current['content_sha256'])
                ? $current['content_sha256']
                : null;
        } else {
            $descriptor = isset($row['payload']['code_package'])
                ? $row['payload']['code_package']
                : null;
            $target = is_array($descriptor) ? self::target_path($descriptor) : null;
            if (! is_string($target)) {
                return self::error('raos_codex_batch_precondition_indeterminate', 500);
            }
            $target_absent = is_string($target) && ! file_exists($target);
            $current_hash = is_string($target) && is_dir($target)
                ? self::tree_hash($target)
                : null;
            if (is_wp_error($current_hash)) {
                return self::error('raos_codex_batch_precondition_indeterminate', 500);
            }
        }
        $at_before = (is_null($row['before_sha256']) && $target_absent)
            || (is_string($current_hash)
                && is_string($row['before_sha256'])
                && hash_equals($row['before_sha256'], $current_hash));
        $at_after = is_string($current_hash)
            && is_string($row['after_sha256'])
            && hash_equals($row['after_sha256'], $current_hash);
        if ('APPROVED' === $row['state']) {
            return $at_before;
        }
        if ('EXPIRED' === $row['state']) {
            return $at_before;
        }
        if ('APPLIED' === $row['state']) {
            return $at_after;
        }
        return 'APPLYING' === $row['state'] && ($at_before || $at_after);
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
        $operation_lock = self::acquire_operation_lock($proposal_id);
        if (is_wp_error($operation_lock)) {
            return $operation_lock;
        }
        $publication_lock = null;
        try {
            $row = RAOS_Codex_MCP_Store::get($proposal_id);
            if (is_wp_error($row)) {
                return $row;
            }
            if (in_array($row['kind'], array('CONTENT_RELEASE', 'THEME_RELEASE'), true)) {
                $publication_lock = self::acquire_publication_mutation_lock();
                if (is_wp_error($publication_lock)) {
                    return $publication_lock;
                }
            }
            $batch_authorization = self::validate_publication_batch_apply($request, $row);
            if (is_wp_error($batch_authorization)) {
                return $batch_authorization;
            }
            if ('APPLIED' === $row['state'] && is_array($row['receipt'])) {
                self::cleanup_completed_code_operation($row);
                return $row['receipt'];
            }
            $gate = self::apply_gate($row['kind']);
            if (is_wp_error($gate)) {
                return $gate;
            }
            if (in_array($row['kind'], array('CONTENT_RELEASE', 'THEME_RELEASE'), true)) {
                if ('APPLYING' === $row['state']
                    && isset($row['result_code'])
                    && 'OPERATION_APPLYING' === $row['result_code']) {
                    return self::recoverable_error(
                        'raos_codex_operation_recovery_required',
                        409
                    );
                }
                if ('APPLYING' !== $row['state']
                    || ! isset($row['result_code'])
                    || 'BATCH_CLAIMED' !== $row['result_code']) {
                    return self::error('raos_codex_publication_batch_not_claimed', 409);
                }
            }
            $claimed = RAOS_Codex_MCP_Store::claim_apply($proposal_id);
            if (is_wp_error($claimed)) {
                return $claimed;
            }
            if ('APPLIED' === $claimed['state'] && is_array($claimed['receipt'])) {
                self::cleanup_completed_code_operation($claimed);
                return $claimed['receipt'];
            }
            $authorization = self::validate_approval_lease($claimed);
            if (is_wp_error($authorization)) {
                $failed = RAOS_Codex_MCP_Store::mark_failed(
                    $proposal_id,
                    'RAOS_CODEX_APPROVAL_LEASE_INVALID'
                );
                if (! is_wp_error($failed) && 'FAILED' === $failed['state']) {
                    self::cleanup_completed_code_operation($failed);
                }
                return $authorization;
            }
            try {
                if ('CONTENT_RELEASE' === $claimed['kind']) {
                    $receipt = $this->apply_content(
                        $claimed,
                        $batch_authorization['manifest']['expected_theme_tree_sha256']
                    );
                } elseif (in_array($claimed['kind'], array('THEME_RELEASE', 'PLUGIN_CHANGE'), true)) {
                    $receipt = $this->apply_code($claimed);
                } else {
                    $receipt = self::error('raos_codex_operation_kind_invalid', 409);
                }
            } catch (Throwable $error) {
                unset($error);
                // A throwable can occur after the live mutation.  Keep the lease and
                // APPLYING state so recovery can compare the authoritative readback.
                $receipt = self::recoverable_error(
                    'raos_codex_operation_recovery_required',
                    500
                );
            }
            if (is_wp_error($receipt) && ! self::error_requires_recovery($receipt)) {
                $code = strtoupper(str_replace('-', '_', $receipt->get_error_code()));
                if (preg_match('/\A[A-Z0-9_]{3,96}\z/D', $code) !== 1) {
                    $code = 'OPERATION_FAILED';
                }
                $failed = RAOS_Codex_MCP_Store::mark_failed($proposal_id, $code);
                if (! is_wp_error($failed) && 'FAILED' === $failed['state']) {
                    self::cleanup_completed_code_operation($failed);
                }
            }
            return $receipt;
        } finally {
            self::release_operation_lock($publication_lock);
            self::release_operation_lock($operation_lock);
        }
    }

    public function recover_operation(WP_REST_Request $request)
    {
        $operation_id = $request['operation_id'];
        if (! RAOS_Codex_MCP_Store::is_sha256($operation_id)) {
            return self::error('raos_codex_operation_id_invalid', 400);
        }
        $operation_lock = self::acquire_operation_lock($operation_id);
        if (is_wp_error($operation_lock)) {
            return $operation_lock;
        }
        $publication_lock = null;
        try {
            $row = RAOS_Codex_MCP_Store::get($operation_id);
            if (is_wp_error($row)) {
                return $row;
            }
            if (in_array($row['kind'], array('CONTENT_RELEASE', 'THEME_RELEASE'), true)) {
                $publication_lock = self::acquire_publication_mutation_lock();
                if (is_wp_error($publication_lock)) {
                    return $publication_lock;
                }
            }
            if ('APPLIED' === $row['state'] && is_array($row['receipt'])) {
                self::cleanup_completed_code_operation($row);
                return $row['receipt'];
            }
            if ('APPLYING' !== $row['state']) {
                return RAOS_Codex_MCP_Store::public_operation($row);
            }
            if (isset($row['result_code']) && 'BATCH_CLAIMED' === $row['result_code']) {
                // The exact batch reserved this member, but its live mutation has
                // not begun.  A retry must POST apply, not roll it back as an
                // interrupted operation at its immutable before state.
                return RAOS_Codex_MCP_Store::public_operation($row);
            }
            $grace = RAOS_Codex_MCP_Store::recovery_grace_elapsed($row);
            if (is_wp_error($grace)) {
                return $grace;
            }
            $current_read_error = false;
            $target_exists = false;
            if ('CONTENT_RELEASE' === $row['kind']) {
                $after = isset($row['payload']['after']) && is_array($row['payload']['after'])
                    ? $row['payload']['after']
                    : null;
                $current = is_array($after) && isset($after['id'])
                    ? RAOS_Codex_MCP_Content::document((int) $after['id'])
                    : null;
                $current_read_error = ! is_array($current);
                $current_hash = is_array($current) && isset($current['content_sha256'])
                    ? $current['content_sha256']
                    : null;
                $target = null;
            } else {
                $code_package = isset($row['payload']['code_package'])
                    ? $row['payload']['code_package']
                    : null;
                $target = is_array($code_package) ? self::target_path($code_package) : null;
                $target_exists = is_string($target) && file_exists($target);
                $current_hash = is_string($target) && is_dir($target)
                    ? self::tree_hash($target)
                    : null;
                if (is_wp_error($current_hash)) {
                    $current_read_error = true;
                    $current_hash = null;
                }
            }
            if (is_string($current_hash)
                && is_string($row['after_sha256'])
                && hash_equals($row['after_sha256'], $current_hash)) {
                if ('PLUGIN_CHANGE' === $row['kind']) {
                    $plugin_recovery = self::recover_plugin_activation($row, true);
                    if (true !== $plugin_recovery) {
                        return $plugin_recovery;
                    }
                }
                $receipt = RAOS_Codex_MCP_Store::complete(
                    $row['proposal_id'],
                    'OPERATION_RECOVERED_AFTER_READBACK',
                    $row['before_sha256'],
                    $current_hash
                );
                if (! is_wp_error($receipt)) {
                    $completed = RAOS_Codex_MCP_Store::get($row['proposal_id']);
                    if (! is_wp_error($completed) && 'APPLIED' === $completed['state']) {
                        self::cleanup_completed_code_operation($completed);
                    }
                }
                return $receipt;
            }
            if (! $current_read_error
                && ((is_null($row['before_sha256']) && is_null($current_hash) && ! $target_exists)
                    || (is_string($current_hash)
                        && is_string($row['before_sha256'])
                        && hash_equals($row['before_sha256'], $current_hash)))) {
                if ('PLUGIN_CHANGE' === $row['kind']) {
                    $plugin_recovery = self::recover_plugin_activation($row, false);
                    if (true !== $plugin_recovery) {
                        return $plugin_recovery;
                    }
                }
                RAOS_Codex_MCP_Store::mark_failed(
                    $row['proposal_id'],
                    'OPERATION_RECOVERED_AT_BEFORE_STATE'
                );
                $updated = RAOS_Codex_MCP_Store::get($row['proposal_id']);
                if (! is_wp_error($updated) && 'FAILED' === $updated['state']) {
                    self::cleanup_completed_code_operation($updated);
                }
                return is_wp_error($updated)
                    ? $updated
                    : RAOS_Codex_MCP_Store::public_operation($updated);
            }

            // An unknown content hash may be a later human/third-party edit.  It
            // must never be overwritten with the proposal's before document.
            if ('CONTENT_RELEASE' === $row['kind']) {
                return self::error(
                    $current_read_error
                        ? 'raos_codex_recovery_readback_failed'
                        : 'raos_codex_recovery_content_drift',
                    409
                );
            }

            // Code recovery is automatically safe only when the target is absent
            // and the exact before tree is still held in the private backup.
            if (is_string($target)
                && ! $target_exists
                && ! $current_read_error
                && is_string($row['before_sha256'])) {
                $gate = self::apply_gate($row['kind']);
                if (is_wp_error($gate)) {
                    return $gate;
                }
                $authorization = self::validate_approval_lease($row);
                if (is_wp_error($authorization)) {
                    return $authorization;
                }
                $private = self::private_directory();
                $backup = is_wp_error($private)
                    ? null
                    : $private . '/operation-' . $row['proposal_id'] . '/before';
                $restored = is_string($backup)
                    ? self::restore_code_before(
                        $target,
                        $backup,
                        $row['before_sha256'],
                        $row['after_sha256']
                    )
                    : self::recoverable_error('raos_codex_code_rollback_indeterminate', 409);
                if (true === $restored) {
                    RAOS_Codex_MCP_Store::mark_failed(
                        $row['proposal_id'],
                        'OPERATION_RECOVERED_BY_CODE_ROLLBACK'
                    );
                    $updated = RAOS_Codex_MCP_Store::get($row['proposal_id']);
                    if (! is_wp_error($updated) && 'FAILED' === $updated['state']) {
                        self::cleanup_completed_code_operation($updated);
                    }
                    return is_wp_error($updated)
                        ? $updated
                        : RAOS_Codex_MCP_Store::public_operation($updated);
                }
                return $restored;
            }

            // A present tree with neither immutable hash is drift.  Do not delete
            // or replace it, and retain the backup and approval lease for review.
            return self::error(
                $current_read_error
                    ? 'raos_codex_recovery_readback_failed'
                    : 'raos_codex_recovery_code_drift',
                409
            );
        } finally {
            self::release_operation_lock($publication_lock);
            self::release_operation_lock($operation_lock);
        }
    }

    private function apply_content($row, $expected_theme_tree_sha256)
    {
        $payload = $row['payload'];
        if (! RAOS_Codex_MCP_Store::is_sha256($expected_theme_tree_sha256)
            || ! isset($payload['before'], $payload['after'])
            || ! is_array($payload['before'])
            || ! is_array($payload['after'])) {
            return self::error('raos_codex_content_proposal_corrupt', 500);
        }
        $before = $payload['before'];
        $after = $payload['after'];
        if (! isset($before['id'], $after['id']) || (int) $before['id'] !== (int) $after['id']) {
            return self::error('raos_codex_content_proposal_corrupt', 500);
        }
        $references = RAOS_Codex_MCP_Content::validate_release_references($after);
        if (is_wp_error($references)) {
            return $references;
        }
        $current = self::begin_content_transaction($before, $row['before_sha256']);
        if (is_wp_error($current)) {
            return $current;
        }
        $write = self::write_content_document($after);
        if (is_wp_error($write)) {
            $rollback = self::rollback_content_transaction($before, $row['before_sha256']);
            return true === $rollback ? $write : $rollback;
        }
        $readback = RAOS_Codex_MCP_Content::document((int) $after['id']);
        if (is_wp_error($readback)
            || ! hash_equals($row['after_sha256'], $readback['content_sha256'])) {
            $rollback = self::rollback_content_transaction($before, $row['before_sha256']);
            return true === $rollback
                ? self::error('raos_codex_content_readback_failed', 500)
                : $rollback;
        }
        $theme_readback = self::active_theme_tree_sha256();
        if (is_wp_error($theme_readback)
            || ! hash_equals($expected_theme_tree_sha256, $theme_readback)) {
            $rollback = self::rollback_content_transaction($before, $row['before_sha256']);
            if (true !== $rollback) {
                return $rollback;
            }
            return is_wp_error($theme_readback)
                ? self::error('raos_codex_content_theme_readback_failed', 503)
                : self::error('raos_codex_content_theme_drift', 409);
        }
        global $wpdb;
        if (false === $wpdb->query('COMMIT')) {
            // COMMIT can fail with an ambiguous network/database outcome.  A
            // readback decides only a confirmed before state is terminal-safe.
            $wpdb->query('ROLLBACK');
            self::clean_content_read_cache((int) $before['id'], $before['post_type']);
            $committed = RAOS_Codex_MCP_Content::document((int) $before['id']);
            if (is_array($committed)
                && isset($committed['content_sha256'])
                && hash_equals($row['before_sha256'], $committed['content_sha256'])) {
                return self::error('raos_codex_content_commit_failed', 500);
            }
            return self::recoverable_error('raos_codex_content_commit_indeterminate', 500);
        }
        $receipt = RAOS_Codex_MCP_Store::complete(
            $row['proposal_id'],
            'CONTENT_RELEASE_APPLIED',
            $current['content_sha256'],
            $readback['content_sha256']
        );
        if (is_wp_error($receipt)) {
            return self::recoverable_from_error($receipt);
        }
        return $receipt;
    }

    private static function cleanup_completed_code_operation($row)
    {
        if (! is_array($row)
            || ! isset($row['proposal_id'], $row['kind'], $row['state'])
            || ! in_array($row['kind'], array('THEME_RELEASE', 'PLUGIN_CHANGE'), true)
            || ! in_array($row['state'], array('APPLIED', 'FAILED', 'EXPIRED'), true)
            || ! RAOS_Codex_MCP_Store::is_sha256($row['proposal_id'])) {
            return;
        }
        $private = self::private_directory();
        if (! is_wp_error($private)) {
            self::remove_tree($private . '/operation-' . $row['proposal_id']);
            $package_path = isset($row['package_path']) ? $row['package_path'] : null;
            $package_real = is_string($package_path) ? realpath($package_path) : false;
            if (is_string($package_real)
                && hash_equals(dirname($package_real), $private)
                && preg_match('/\Apackage-[0-9a-f]{48}\.zip\z/D', basename($package_real)) === 1
                && self::secure_staged_file($package_real)) {
                @unlink($package_real);
            }
        }
    }

    /**
     * Lock the post and taxonomy relationship range, then re-evaluate the full
     * immutable precondition.  Standard wp-admin writes cannot pass between the
     * authoritative comparison and this transaction's content mutation.
     */
    private static function begin_content_transaction($before, $before_sha256)
    {
        global $wpdb;
        if (! is_array($before)
            || ! isset($before['id'], $before['post_type'], $before['revision_id'], $before['modified_gmt'])
            || ! is_string($before_sha256)) {
            return self::error('raos_codex_content_transaction_failed', 500);
        }
        $transactional = RAOS_Codex_MCP_Store::require_transactional_tables(
            array($wpdb->posts, $wpdb->term_relationships, $wpdb->term_taxonomy)
        );
        if (is_wp_error($transactional)) {
            return $transactional;
        }
        if (false === $wpdb->query('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')) {
            return self::error('raos_codex_content_transaction_isolation_failed', 503);
        }
        if (false === $wpdb->query('START TRANSACTION')) {
            return self::error('raos_codex_content_transaction_failed', 500);
        }
        $post_id = (int) $before['id'];
        $locked_post = $wpdb->get_var(
            $wpdb->prepare(
                "SELECT ID FROM {$wpdb->posts} WHERE ID = %d FOR UPDATE",
                $post_id
            )
        );
        $locked_terms = $wpdb->get_results(
            $wpdb->prepare(
                "SELECT object_id, term_taxonomy_id FROM {$wpdb->term_relationships}"
                . ' WHERE object_id = %d FOR UPDATE',
                $post_id
            ),
            ARRAY_A
        );
        if ((int) $locked_post !== $post_id || ! is_array($locked_terms)) {
            $wpdb->query('ROLLBACK');
            return self::error('raos_codex_content_transaction_failed', 500);
        }
        self::clean_content_read_cache($post_id, $before['post_type']);
        $current = RAOS_Codex_MCP_Content::document($post_id);
        if (is_wp_error($current)
            || ! isset($current['content_sha256'], $current['revision_id'], $current['modified_gmt'])
            || ! hash_equals($before_sha256, $current['content_sha256'])
            || (int) $current['revision_id'] !== (int) $before['revision_id']
            || ! hash_equals($current['modified_gmt'], $before['modified_gmt'])) {
            $observed_hash = is_array($current) && isset($current['content_sha256'])
                ? $current['content_sha256']
                : null;
            $rolled_back = false !== $wpdb->query('ROLLBACK');
            self::clean_content_read_cache($post_id, $before['post_type']);
            $confirmed = RAOS_Codex_MCP_Content::document($post_id);
            if ($rolled_back
                && is_string($observed_hash)
                && is_array($confirmed)
                && isset($confirmed['content_sha256'])
                && hash_equals($observed_hash, $confirmed['content_sha256'])) {
                return self::error('raos_codex_content_hash_drift', 412);
            }
            return self::recoverable_error('raos_codex_content_precondition_indeterminate', 500);
        }
        return $current;
    }

    private static function rollback_content_transaction($before, $before_sha256)
    {
        global $wpdb;
        if (! is_array($before)
            || ! isset($before['id'], $before['post_type'])
            || ! is_string($before_sha256)) {
            return self::recoverable_error('raos_codex_content_rollback_indeterminate', 500);
        }
        $rollback = false !== $wpdb->query('ROLLBACK');
        self::clean_content_read_cache((int) $before['id'], $before['post_type']);
        $readback = RAOS_Codex_MCP_Content::document((int) $before['id']);
        if (! $rollback
            || ! is_array($readback)
            || ! isset($readback['content_sha256'])
            || ! is_string($readback['content_sha256'])
            || ! hash_equals($before_sha256, $readback['content_sha256'])) {
            return self::recoverable_error('raos_codex_content_rollback_indeterminate', 500);
        }
        return true;
    }

    private static function clean_content_read_cache($post_id, $post_type)
    {
        clean_post_cache((int) $post_id);
        clean_object_term_cache((int) $post_id, (string) $post_type);
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
            return self::error('raos_codex_package_extract_failed', 500);
        }
        $zip->close();
        $new_root = $extract_root . '/' . $descriptor['slug'];
        $new_hash = self::tree_hash($new_root);
        if (is_wp_error($new_hash) || ! hash_equals($descriptor['file_manifest_sha256'], $new_hash)) {
            return self::error('raos_codex_extracted_digest_mismatch', 412);
        }
        $plugin_state = null;
        if ('plugin' === $descriptor['kind']) {
            $plugin_state = self::plugin_state($descriptor['slug'], $new_root);
            if (is_wp_error($plugin_state)) {
                return $plugin_state;
            }
            $plugin_recovery = self::write_plugin_recovery_state(
                $row['proposal_id'],
                $plugin_state
            );
            if (is_wp_error($plugin_recovery)) {
                return $plugin_recovery;
            }
        }
        $installed = self::install_code_tree(
            $new_root,
            $target,
            $backup_root,
            $row['before_sha256'],
            $row['after_sha256']
        );
        if (is_wp_error($installed)) {
            // Once the old target has moved to the backup, never recursively
            // clean the operation directory until an exact restoration is read
            // back.  It may contain the only recoverable copy.
            return $installed;
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
            $rollback = self::restore_code_before(
                $target,
                $backup_root,
                $row['before_sha256'],
                $row['after_sha256']
            );
            $plugin_restored = true;
            if (true === $rollback
                && 'plugin' === $descriptor['kind']
                && is_array($plugin_state)) {
                $plugin_restored = self::restore_plugin_state($plugin_state);
            }
            if (true !== $rollback || ! $plugin_restored) {
                return self::recoverable_error('raos_codex_code_rollback_indeterminate', 500);
            }
            return self::error('raos_codex_code_readback_failed', 500);
        }
        self::remove_tree($extract_root);
        $receipt = RAOS_Codex_MCP_Store::complete(
            $row['proposal_id'],
            'theme' === $descriptor['kind'] ? 'THEME_RELEASE_APPLIED' : 'PLUGIN_CHANGE_APPLIED',
            $current_hash,
            $readback
        );
        if (is_wp_error($receipt)) {
            return self::recoverable_from_error($receipt);
        }
        $completed = RAOS_Codex_MCP_Store::get($row['proposal_id']);
        if (! is_wp_error($completed) && 'APPLIED' === $completed['state']) {
            self::cleanup_completed_code_operation($completed);
        }
        return $receipt;
    }

    /**
     * Atomically install an extracted tree and verify rollback if installation
     * fails after the old target has moved.  The optional mover is private test
     * injection; production always uses rename(2).
     */
    private static function install_code_tree(
        $new_root,
        $target,
        $backup_root,
        $before_sha256,
        $after_sha256,
        $mover = null
    ) {
        $move = is_callable($mover)
            ? $mover
            : static function ($source, $destination) {
                return @rename($source, $destination);
            };
        if ((is_string($before_sha256) && ! is_dir($target))
            || (is_null($before_sha256) && file_exists($target))) {
            return self::error('raos_codex_code_hash_drift', 412);
        }
        if (is_dir($target)) {
            if (! $move($target, $backup_root)) {
                return self::error('raos_codex_backup_failed', 500);
            }
            // Rehash the tree after rename.  The earlier status check is not a
            // CAS: wp-admin or another updater can edit between it and rename.
            $moved_hash = self::tree_hash($backup_root);
            if (! is_string($moved_hash)
                || ! is_string($before_sha256)
                || ! hash_equals($before_sha256, $moved_hash)) {
                $restored = is_string($moved_hash)
                    ? self::restore_code_before(
                        $target,
                        $backup_root,
                        $moved_hash,
                        $after_sha256,
                        $move
                    )
                    : self::recoverable_error('raos_codex_backup_cas_indeterminate', 500);
                return true === $restored
                    ? self::error('raos_codex_code_hash_drift', 412)
                    : self::recoverable_error('raos_codex_backup_cas_indeterminate', 500);
            }
        }
        if ($move($new_root, $target)) {
            return true;
        }
        $restored = self::restore_code_before(
            $target,
            $backup_root,
            $before_sha256,
            $after_sha256,
            $move
        );
        return true === $restored
            ? self::error('raos_codex_code_install_failed', 500)
            : self::recoverable_error('raos_codex_code_install_rollback_indeterminate', 500);
    }

    /**
     * Restore the immutable before tree without overwriting an unknown target.
     * A non-null after hash authorizes removal only of the exact installed tree.
     */
    private static function restore_code_before(
        $target,
        $backup_root,
        $before_sha256,
        $after_sha256,
        $mover = null
    ) {
        $move = is_callable($mover)
            ? $mover
            : static function ($source, $destination) {
                return @rename($source, $destination);
            };
        if (! is_string($target)
            || ! is_string($backup_root)
            || (! is_null($before_sha256)
                && ! RAOS_Codex_MCP_Store::is_sha256($before_sha256))
            || (! is_null($after_sha256)
                && ! RAOS_Codex_MCP_Store::is_sha256($after_sha256))) {
            return self::recoverable_error('raos_codex_code_rollback_indeterminate', 500);
        }

        if (file_exists($target)) {
            $current_hash = is_dir($target) ? self::tree_hash($target) : null;
            // Never delete a third state.  It can be a human or another system's
            // later edit, even while this proposal remains APPLYING.
            if (! is_string($current_hash)
                || ! is_string($after_sha256)
                || ! hash_equals($after_sha256, $current_hash)
                || ! self::remove_tree($target)
                || file_exists($target)) {
                return self::recoverable_error('raos_codex_code_rollback_indeterminate', 500);
            }
        }

        if (is_null($before_sha256)) {
            return file_exists($target) || file_exists($backup_root)
                ? self::recoverable_error('raos_codex_code_rollback_indeterminate', 500)
                : true;
        }
        $backup_hash = is_dir($backup_root) ? self::tree_hash($backup_root) : null;
        if (! is_string($backup_hash)
            || ! hash_equals($before_sha256, $backup_hash)
            || file_exists($target)
            || ! $move($backup_root, $target)) {
            return self::recoverable_error('raos_codex_code_rollback_indeterminate', 500);
        }
        $restored_hash = is_dir($target) ? self::tree_hash($target) : null;
        return is_string($restored_hash) && hash_equals($before_sha256, $restored_hash)
            ? true
            : self::recoverable_error('raos_codex_code_rollback_indeterminate', 500);
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
        if ('preserve' === $descriptor['activation_intent'] && ! $state['old_active']) {
            deactivate_plugins($state['new_file'], true, false);
            return is_plugin_active($state['new_file'])
                ? self::error('raos_codex_plugin_deactivation_failed', 500)
                : true;
        }
        return true;
    }

    private static function restore_plugin_state($state)
    {
        require_once ABSPATH . 'wp-admin/includes/plugin.php';
        if (! is_array($state)) {
            return false;
        }
        if (! empty($state['new_file'])) {
            deactivate_plugins($state['new_file'], true, false);
        }
        if (! empty($state['old_active']) && is_string($state['old_file'])) {
            $activation = activate_plugin($state['old_file'], '', false, true);
            if (is_wp_error($activation)) {
                return false;
            }
        }
        $new_active = ! empty($state['new_file']) && is_plugin_active($state['new_file']);
        $old_active = is_string($state['old_file']) && is_plugin_active($state['old_file']);
        if (! empty($state['old_active'])) {
            return $old_active;
        }
        return ! $new_active && ! $old_active;
    }

    private static function write_plugin_recovery_state($proposal_id, $state)
    {
        if (! RAOS_Codex_MCP_Store::is_sha256($proposal_id)
            || ! self::valid_plugin_recovery_state($state)) {
            return self::error('raos_codex_plugin_recovery_state_invalid', 500);
        }
        $private = self::private_directory();
        if (is_wp_error($private)) {
            return $private;
        }
        $path = $private . '/operation-' . $proposal_id . '/plugin-before-state.json';
        $payload = RAOS_Codex_MCP_Store::canonical_json($state);
        if (! is_string($payload)
            || ! self::write_exclusive_file($path, $payload)
            || ! self::secure_staged_file($path)) {
            @unlink($path);
            return self::error('raos_codex_plugin_recovery_state_failed', 500);
        }
        return true;
    }

    private static function read_plugin_recovery_state($proposal_id)
    {
        if (! RAOS_Codex_MCP_Store::is_sha256($proposal_id)) {
            return self::recoverable_error('raos_codex_plugin_recovery_indeterminate', 409);
        }
        $private = self::private_directory();
        $path = is_wp_error($private)
            ? null
            : $private . '/operation-' . $proposal_id . '/plugin-before-state.json';
        $payload = is_string($path) && self::secure_staged_file($path)
            ? @file_get_contents($path)
            : null;
        $state = is_string($payload) ? json_decode($payload, true, 8) : null;
        return self::valid_plugin_recovery_state($state)
            ? $state
            : self::recoverable_error('raos_codex_plugin_recovery_indeterminate', 409);
    }

    private static function valid_plugin_recovery_state($state)
    {
        return is_array($state)
            && self::has_exact_keys($state, array('old_file', 'old_active', 'new_file'))
            && (is_null($state['old_file'])
                || (is_string($state['old_file'])
                    && preg_match('/\A[a-z0-9-]+\/[A-Za-z0-9._-]+\.php\z/D', $state['old_file']) === 1))
            && is_bool($state['old_active'])
            && is_string($state['new_file'])
            && preg_match('/\A[a-z0-9-]+\/[A-Za-z0-9._-]+\.php\z/D', $state['new_file']) === 1;
    }

    private static function plugin_state_matches_before($state)
    {
        require_once ABSPATH . 'wp-admin/includes/plugin.php';
        if (! self::valid_plugin_recovery_state($state)) {
            return false;
        }
        $old_active = is_string($state['old_file']) && is_plugin_active($state['old_file']);
        $new_active = is_plugin_active($state['new_file']);
        if ($state['old_file'] === $state['new_file']) {
            return $old_active === $state['old_active'];
        }
        return $old_active === $state['old_active'] && ! $new_active;
    }

    private static function plugin_state_matches_after($descriptor, $state)
    {
        require_once ABSPATH . 'wp-admin/includes/plugin.php';
        if (! is_array($descriptor)
            || ! isset($descriptor['activation_intent'])
            || ! self::valid_plugin_recovery_state($state)) {
            return false;
        }
        $expected_active = 'activate' === $descriptor['activation_intent']
            || ('preserve' === $descriptor['activation_intent'] && $state['old_active']);
        $new_active = is_plugin_active($state['new_file']);
        $old_active = is_string($state['old_file']) && is_plugin_active($state['old_file']);
        return $new_active === $expected_active
            && ($state['old_file'] === $state['new_file'] || ! $old_active);
    }

    private static function recover_plugin_activation($row, $at_after)
    {
        $state = isset($row['proposal_id'])
            ? self::read_plugin_recovery_state($row['proposal_id'])
            : null;
        if (is_wp_error($state)) {
            return $state;
        }
        $descriptor = isset($row['payload']['code_package'])
            ? $row['payload']['code_package']
            : null;
        $matches = $at_after
            ? self::plugin_state_matches_after($descriptor, $state)
            : self::plugin_state_matches_before($state);
        if ($matches) {
            return true;
        }
        $gate = self::apply_gate($row['kind']);
        if (is_wp_error($gate)) {
            return $gate;
        }
        $authorization = self::validate_approval_lease($row);
        if (is_wp_error($authorization)) {
            return $authorization;
        }
        try {
            $restored = $at_after
                ? self::apply_plugin_intent($descriptor, $state)
                : self::restore_plugin_state($state);
        } catch (Throwable $error) {
            unset($error);
            $restored = false;
        }
        $matches = true === $restored
            && ($at_after
                ? self::plugin_state_matches_after($descriptor, $state)
                : self::plugin_state_matches_before($state));
        return $matches
            ? true
            : self::recoverable_error('raos_codex_plugin_recovery_indeterminate', 409);
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

    private static function acquire_operation_lock($proposal_id)
    {
        if (! RAOS_Codex_MCP_Store::is_sha256($proposal_id)) {
            return self::error('raos_codex_operation_id_invalid', 400);
        }
        return self::acquire_private_lock(
            'operation-lock-' . $proposal_id . '.lock',
            'raos_codex_operation_lock_insecure',
            'raos_codex_operation_lock_unavailable',
            'raos_codex_operation_in_flight'
        );
    }

    private static function acquire_publication_mutation_lock()
    {
        return self::acquire_private_lock(
            'publication-mutation.lock',
            'raos_codex_publication_lock_insecure',
            'raos_codex_publication_lock_unavailable',
            'raos_codex_publication_mutation_in_flight'
        );
    }

    private static function acquire_private_lock(
        $filename,
        $insecure_code,
        $unavailable_code,
        $in_flight_code
    ) {
        if (! is_string($filename)
            || preg_match('/\A[a-z0-9-]+\.lock\z/D', $filename) !== 1) {
            return self::error($insecure_code, 503);
        }
        $private = self::private_directory();
        if (is_wp_error($private)) {
            return $private;
        }
        $path = $private . '/' . $filename;
        $previous_umask = umask(0077);
        $handle = @fopen($path, 'x+b');
        umask($previous_umask);
        if (false !== $handle) {
            @chmod($path, 0600);
        } else {
            if (is_link($path) || ! is_file($path)) {
                return self::error($insecure_code, 503);
            }
            $handle = @fopen($path, 'r+b');
        }
        if (false === $handle) {
            return self::error($unavailable_code, 503);
        }
        $path_metadata = @lstat($path);
        $handle_metadata = @fstat($handle);
        $private_metadata = @stat($private);
        $real = realpath($path);
        if (! is_array($path_metadata)
            || ! is_array($handle_metadata)
            || ! is_array($private_metadata)
            || ! is_string($real)
            || ! hash_equals($path, $real)
            || 0100000 !== ((int) $handle_metadata['mode'] & 0170000)
            || 0600 !== ((int) $handle_metadata['mode'] & 0777)
            || 1 !== (int) $handle_metadata['nlink']
            || (int) $handle_metadata['uid'] !== (int) $private_metadata['uid']
            || (int) $path_metadata['dev'] !== (int) $handle_metadata['dev']
            || (int) $path_metadata['ino'] !== (int) $handle_metadata['ino']) {
            fclose($handle);
            return self::error($insecure_code, 503);
        }
        if (! @flock($handle, LOCK_EX | LOCK_NB)) {
            fclose($handle);
            return self::error($in_flight_code, 409);
        }
        return $handle;
    }

    private static function release_operation_lock($handle)
    {
        if (! is_resource($handle)) {
            return;
        }
        @flock($handle, LOCK_UN);
        fclose($handle);
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

    private static function has_only_keys($value, $required, $optional)
    {
        if (! is_array($value) || ! is_array($required) || ! is_array($optional)) {
            return false;
        }
        $actual = array_keys($value);
        $allowed = array_merge($required, $optional);
        return empty(array_diff($required, $actual))
            && empty(array_diff($actual, $allowed));
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

    private static function recoverable_error($code, $status)
    {
        return new WP_Error(
            $code,
            'The bounded deployment operation requires recovery.',
            array('status' => $status, 'recovery_required' => true)
        );
    }

    private static function recoverable_from_error($error)
    {
        if (! is_wp_error($error)) {
            return self::recoverable_error('raos_codex_operation_recovery_required', 500);
        }
        $data = $error->get_error_data();
        if (! is_array($data)) {
            $data = array('status' => 500);
        }
        if (! isset($data['status']) || ! is_int($data['status'])) {
            $data['status'] = 500;
        }
        $data['recovery_required'] = true;
        return new WP_Error($error->get_error_code(), $error->get_error_message(), $data);
    }

    private static function error_requires_recovery($error)
    {
        if (! is_wp_error($error)) {
            return false;
        }
        $data = $error->get_error_data();
        return is_array($data) && true === ($data['recovery_required'] ?? false);
    }
}
