<?php
/**
 * Bounded post and page abilities exposed by the custom MCP server.
 *
 * @package RAOS_Codex_MCP_Abilities
 */

defined('ABSPATH') || exit;

final class RAOS_Codex_MCP_Content
{
    const MAX_CONTENT_BYTES = 1048576;

    private $plugin;

    public function __construct($plugin)
    {
        $this->plugin = $plugin;
    }

    public function register_abilities()
    {
        $this->register(
            'raos-codex/site-status',
            'RAOS WordPress site status',
            'Return version pins, safety gates, and the tracked child-theme status.',
            array('type' => 'object', 'additionalProperties' => false),
            array($this, 'site_status'),
            true,
            true
        );
        $this->register(
            'raos-codex/content-list',
            'List posts and pages',
            'List bounded post/page document projections without media bytes or secrets.',
            array(
                'type' => 'object',
                'additionalProperties' => false,
                'properties' => array(
                    'post_type' => array('type' => 'string', 'enum' => array('post', 'page')),
                    'status' => array('type' => 'string', 'enum' => array('draft', 'publish', 'any')),
                    'page' => array('type' => 'integer', 'minimum' => 1, 'maximum' => 100000),
                    'per_page' => array('type' => 'integer', 'minimum' => 1, 'maximum' => 50),
                ),
            ),
            array($this, 'content_list'),
            true,
            false
        );
        $this->register(
            'raos-codex/content-get',
            'Get one post or page',
            'Return ContentDocumentV1 with revision, timestamp, and hash preconditions.',
            array(
                'type' => 'object',
                'additionalProperties' => false,
                'required' => array('id'),
                'properties' => array('id' => array('type' => 'integer', 'minimum' => 1)),
            ),
            array($this, 'content_get'),
            true,
            false
        );
        $this->register(
            'raos-codex/content-create-draft',
            'Create a draft post or page',
            'Create only draft content. Publishing, deletion, media upload, and unpublishing are unavailable.',
            self::document_write_schema(false),
            array($this, 'content_create_draft'),
            false,
            false
        );
        $this->register(
            'raos-codex/content-update-draft',
            'Update a draft post or page',
            'Partially update or fully replace a draft after all three preconditions match.',
            array(
                'type' => 'object',
                'additionalProperties' => false,
                'required' => array('id', 'mode', 'precondition', 'changes'),
                'properties' => array(
                    'id' => array('type' => 'integer', 'minimum' => 1),
                    'mode' => array('type' => 'string', 'enum' => array('partial', 'replace')),
                    'precondition' => self::precondition_schema(),
                    'changes' => self::document_write_schema(true),
                ),
            ),
            array($this, 'content_update_draft'),
            false,
            false
        );
        $this->register(
            'raos-codex/content-propose-release',
            'Propose a content release',
            'Create an immutable 15-minute proposal. This never publishes or changes the target post/page.',
            array(
                'type' => 'object',
                'additionalProperties' => false,
                'required' => array('id', 'precondition', 'document'),
                'properties' => array(
                    'id' => array('type' => 'integer', 'minimum' => 1),
                    'precondition' => self::precondition_schema(),
                    'document' => self::document_write_schema(false),
                ),
            ),
            array($this, 'content_propose_release'),
            false,
            false
        );
        $this->register(
            'raos-codex/operation-get',
            'Get an operation receipt',
            'Read one proposal/operation state by its existing ID.',
            array(
                'type' => 'object',
                'additionalProperties' => false,
                'required' => array('operation_id'),
                'properties' => array(
                    'operation_id' => array('type' => 'string', 'pattern' => '^[0-9a-f]{64}$'),
                ),
            ),
            array($this, 'operation_get'),
            true,
            false
        );
    }

    private function register($name, $label, $description, $input_schema, $callback, $read_only, $idempotent)
    {
        wp_register_ability(
            $name,
            array(
                'label' => $label,
                'description' => $description,
                'category' => 'raos-codex',
                'input_schema' => $input_schema,
                'output_schema' => array('type' => 'object'),
                'execute_callback' => $callback,
                'permission_callback' => array($this->plugin, 'ability_permission'),
                'meta' => array(
                    'public' => false,
                    'annotations' => array(
                        'readOnlyHint' => $read_only,
                        'destructiveHint' => false,
                        'idempotentHint' => $idempotent,
                        'openWorldHint' => false,
                    ),
                    'mcp' => array('type' => 'tool'),
                ),
            )
        );
    }

    private static function precondition_schema()
    {
        return array(
            'type' => 'object',
            'additionalProperties' => false,
            'required' => array('revision_id', 'modified_gmt', 'content_sha256'),
            'properties' => array(
                'revision_id' => array('type' => 'integer', 'minimum' => 1),
                'modified_gmt' => array(
                    'type' => 'string',
                    'pattern' => '^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$',
                ),
                'content_sha256' => array('type' => 'string', 'pattern' => '^[0-9a-f]{64}$'),
            ),
        );
    }

    private static function document_write_schema($partial)
    {
        $properties = array(
            'post_type' => array('type' => 'string', 'enum' => array('post', 'page')),
            'title' => array('type' => 'string', 'minLength' => 1, 'maxLength' => 500),
            'slug' => array(
                'type' => 'string',
                'minLength' => 1,
                'maxLength' => 200,
                'pattern' => '^[a-z0-9]+(?:-[a-z0-9]+)*$',
            ),
            'excerpt' => array('type' => 'string', 'maxLength' => 10000),
            'block_markup' => array('type' => 'string', 'maxLength' => self::MAX_CONTENT_BYTES),
            'taxonomies' => array(
                'type' => 'object',
                'maxProperties' => 32,
                'additionalProperties' => array(
                    'type' => 'array',
                    'maxItems' => 128,
                    'uniqueItems' => true,
                    'items' => array('type' => 'integer', 'minimum' => 1),
                ),
            ),
            'media_ids' => array(
                'type' => 'array',
                'maxItems' => 256,
                'uniqueItems' => true,
                'items' => array('type' => 'integer', 'minimum' => 1),
            ),
        );
        $schema = array(
            'type' => 'object',
            'additionalProperties' => false,
            'properties' => $properties,
        );
        if (! $partial) {
            $schema['required'] = array_keys($properties);
        } else {
            $schema['minProperties'] = 1;
        }
        return $schema;
    }

    public function site_status($input = array())
    {
        unset($input);
        global $wp_version;
        $theme = wp_get_theme('kurashinoshirube-child');
        $global_writes = defined('RAOS_OPERATOR_WRITES_ENABLED')
            && true === RAOS_OPERATOR_WRITES_ENABLED;
        $private_ready = ! is_wp_error(RAOS_Codex_MCP_Deployment::private_directory());
        $apply_ready = $global_writes && $private_ready;
        return array(
            'schema' => 'RAOSWordPressSiteStatusV1',
            'origin' => home_url(),
            'wordpress_version' => $wp_version,
            'wordpress_version_compatible' => preg_match('/\A7\.1(?:\.|\z)/', $wp_version) === 1,
            'mcp_adapter_version' => defined('WP_MCP_VERSION') ? WP_MCP_VERSION : null,
            'mcp_adapter_version_compatible' => defined('WP_MCP_VERSION') && '0.6.1' === WP_MCP_VERSION,
            'plugin_version' => RAOS_CODEX_MCP_VERSION,
            'writes_enabled' => array(
                'global' => $global_writes,
                'draft' => defined('RAOS_CODEX_DRAFT_WRITES_ENABLED') && true === RAOS_CODEX_DRAFT_WRITES_ENABLED,
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
            'theme' => array(
                'slug' => 'kurashinoshirube-child',
                'exists' => $theme->exists(),
                'version' => $theme->exists() ? (string) $theme->get('Version') : null,
                'active' => get_stylesheet() === 'kurashinoshirube-child',
            ),
            'server' => array(
                'endpoint' => home_url('/wp-json/raos-codex-mcp/v1/editor'),
                'proposal_ttl_seconds' => RAOS_Codex_MCP_Store::TTL_SECONDS,
                'publish_tool_exposed' => false,
                'delete_tool_exposed' => false,
                'media_write_tool_exposed' => false,
            ),
        );
    }

    public function content_list($input)
    {
        $input = is_array($input) ? $input : array();
        $post_type = isset($input['post_type']) ? $input['post_type'] : 'post';
        $status = isset($input['status']) ? $input['status'] : 'any';
        $page = isset($input['page']) ? (int) $input['page'] : 1;
        $per_page = isset($input['per_page']) ? (int) $input['per_page'] : 20;
        if (! in_array($post_type, array('post', 'page'), true)
            || ! in_array($status, array('draft', 'publish', 'any'), true)
            || $page < 1
            || $per_page < 1
            || $per_page > 50) {
            return self::error('raos_codex_content_query_invalid', 400);
        }
        $query = new WP_Query(
            array(
                'post_type' => $post_type,
                'post_status' => 'any' === $status ? array('draft', 'publish') : $status,
                'paged' => $page,
                'posts_per_page' => $per_page,
                'orderby' => array('modified' => 'DESC', 'ID' => 'ASC'),
                'no_found_rows' => false,
            )
        );
        $documents = array();
        foreach ($query->posts as $post) {
            $document = self::document($post);
            if (! is_wp_error($document)) {
                $documents[] = $document;
            }
        }
        return array(
            'schema' => 'ContentDocumentListV1',
            'page' => $page,
            'per_page' => $per_page,
            'total' => (int) $query->found_posts,
            'documents' => $documents,
        );
    }

    public function content_get($input)
    {
        if (! is_array($input) || ! isset($input['id'])) {
            return self::error('raos_codex_content_id_invalid', 400);
        }
        return self::document((int) $input['id']);
    }

    public function content_create_draft($input)
    {
        $gate = $this->draft_write_gate();
        if (is_wp_error($gate)) {
            return $gate;
        }
        $validated = self::validate_write_document($input, false, null);
        if (is_wp_error($validated)) {
            return $validated;
        }
        $post_id = wp_insert_post(
            array(
                'post_type' => $validated['post_type'],
                'post_status' => 'draft',
                'post_author' => get_current_user_id(),
                'post_title' => $validated['title'],
                'post_name' => $validated['slug'],
                'post_excerpt' => $validated['excerpt'],
                'post_content' => $validated['block_markup'],
            ),
            true
        );
        if (is_wp_error($post_id)) {
            return self::error('raos_codex_draft_create_failed', 500);
        }
        $term_result = self::apply_taxonomies((int) $post_id, $validated['post_type'], $validated['taxonomies']);
        if (is_wp_error($term_result)) {
            wp_delete_post((int) $post_id, true);
            return $term_result;
        }
        return self::document((int) $post_id);
    }

    public function content_update_draft($input)
    {
        $gate = $this->draft_write_gate();
        if (is_wp_error($gate)) {
            return $gate;
        }
        if (! is_array($input)
            || ! isset($input['id'], $input['mode'], $input['precondition'], $input['changes'])
            || ! in_array($input['mode'], array('partial', 'replace'), true)) {
            return self::error('raos_codex_draft_update_invalid', 400);
        }
        $post = get_post((int) $input['id']);
        if (! $post instanceof WP_Post
            || ! in_array($post->post_type, array('post', 'page'), true)
            || 'draft' !== $post->post_status) {
            return self::error('raos_codex_draft_target_invalid', 409);
        }
        $before = self::document($post);
        if (is_wp_error($before)) {
            return $before;
        }
        if (! self::precondition_matches($before, $input['precondition'])) {
            return self::error('raos_codex_content_precondition_failed', 412);
        }
        $partial = 'partial' === $input['mode'];
        $changes = self::validate_write_document($input['changes'], $partial, $post->post_type);
        if (is_wp_error($changes)) {
            return $changes;
        }
        $merged = array(
            'post_type' => $post->post_type,
            'title' => $before['title'],
            'slug' => $before['slug'],
            'excerpt' => $before['excerpt'],
            'block_markup' => $before['block_markup'],
            'taxonomies' => $before['taxonomies'],
            'media_ids' => $before['media_ids'],
        );
        foreach ($changes as $key => $value) {
            $merged[$key] = $value;
        }
        $validated = self::validate_write_document($merged, false, $post->post_type);
        if (is_wp_error($validated)) {
            return $validated;
        }
        $updated = wp_update_post(
            array(
                'ID' => (int) $post->ID,
                'post_status' => 'draft',
                'post_title' => $validated['title'],
                'post_name' => $validated['slug'],
                'post_excerpt' => $validated['excerpt'],
                'post_content' => $validated['block_markup'],
            ),
            true
        );
        if (is_wp_error($updated)) {
            return self::error('raos_codex_draft_update_failed', 500);
        }
        $term_result = self::apply_taxonomies((int) $post->ID, $post->post_type, $validated['taxonomies']);
        if (is_wp_error($term_result)) {
            wp_update_post(
                array(
                    'ID' => (int) $post->ID,
                    'post_status' => 'draft',
                    'post_title' => $before['title'],
                    'post_name' => $before['slug'],
                    'post_excerpt' => $before['excerpt'],
                    'post_content' => $before['block_markup'],
                )
            );
            self::apply_taxonomies(
                (int) $post->ID,
                $post->post_type,
                $before['taxonomies']
            );
            return $term_result;
        }
        return self::document((int) $post->ID);
    }

    public function content_propose_release($input)
    {
        if (! is_array($input)
            || ! isset($input['id'], $input['precondition'], $input['document'])) {
            return self::error('raos_codex_release_input_invalid', 400);
        }
        $before = self::document((int) $input['id']);
        if (is_wp_error($before)) {
            return $before;
        }
        if (! self::precondition_matches($before, $input['precondition'])) {
            return self::error('raos_codex_content_precondition_failed', 412);
        }
        $validated = self::validate_write_document($input['document'], false, $before['post_type']);
        if (is_wp_error($validated)) {
            return $validated;
        }
        $after = array(
            'schema' => 'ContentDocumentV1',
            'post_type' => $before['post_type'],
            'id' => $before['id'],
            'status' => 'publish',
            'title' => $validated['title'],
            'slug' => $validated['slug'],
            'excerpt' => $validated['excerpt'],
            'block_markup' => $validated['block_markup'],
            'taxonomies' => $validated['taxonomies'],
            'media_ids' => $validated['media_ids'],
            'revision_id' => $before['revision_id'],
            'modified_gmt' => $before['modified_gmt'],
        );
        $after['content_sha256'] = self::document_hash($after);
        $manifest_hash = RAOS_Codex_MCP_Store::hash(
            array(
                'schema' => 'ContentPublicationManifestV1',
                'target_status' => 'publish',
                'post_type' => $after['post_type'],
                'post_id' => $after['id'],
                'before_sha256' => $before['content_sha256'],
                'after_sha256' => $after['content_sha256'],
                'precondition' => $input['precondition'],
            )
        );
        if (! RAOS_Codex_MCP_Store::is_sha256($after['content_sha256'])
            || ! RAOS_Codex_MCP_Store::is_sha256($manifest_hash)) {
            return self::error('raos_codex_release_manifest_invalid', 500);
        }
        $proposal = array(
            'schema' => 'ContentReleaseProposalV1',
            'target_status' => 'publish',
            'before' => $before,
            'after' => $after,
            'before_sha256' => $before['content_sha256'],
            'after_sha256' => $after['content_sha256'],
            'publication_manifest_sha256' => $manifest_hash,
        );
        $row = RAOS_Codex_MCP_Store::create(
            'CONTENT_RELEASE',
            $proposal,
            $before['content_sha256'],
            $after['content_sha256']
        );
        return is_wp_error($row) ? $row : $row['payload'];
    }

    public function operation_get($input)
    {
        if (! is_array($input) || ! isset($input['operation_id'])) {
            return self::error('raos_codex_operation_id_invalid', 400);
        }
        $row = RAOS_Codex_MCP_Store::get($input['operation_id']);
        if (is_wp_error($row)) {
            return $row;
        }
        if ((int) $row['created_by'] !== get_current_user_id()
            || 'CONTENT_RELEASE' !== $row['kind']) {
            return self::error('raos_codex_operation_forbidden', 403);
        }
        return RAOS_Codex_MCP_Store::public_operation($row);
    }

    private function draft_write_gate()
    {
        if (! defined('RAOS_OPERATOR_WRITES_ENABLED') || true !== RAOS_OPERATOR_WRITES_ENABLED
            || ! defined('RAOS_CODEX_DRAFT_WRITES_ENABLED') || true !== RAOS_CODEX_DRAFT_WRITES_ENABLED) {
            return self::error('raos_codex_draft_writes_disabled', 503);
        }
        return true;
    }

    public static function document($post_or_id)
    {
        $post = $post_or_id instanceof WP_Post ? $post_or_id : get_post((int) $post_or_id);
        if (! $post instanceof WP_Post
            || ! in_array($post->post_type, array('post', 'page'), true)
            || ! in_array($post->post_status, array('draft', 'publish'), true)) {
            return self::error('raos_codex_content_not_found', 404);
        }
        $revisions = wp_get_post_revisions(
            $post->ID,
            array('posts_per_page' => 1, 'orderby' => 'ID', 'order' => 'DESC')
        );
        $revision_id = empty($revisions) ? (int) $post->ID : (int) array_key_first($revisions);
        $modified_gmt = self::normalized_modified_gmt($post);
        if (! is_string($modified_gmt)) {
            return self::error('raos_codex_content_timestamp_invalid', 500);
        }
        $taxonomies = array();
        foreach (get_object_taxonomies($post->post_type, 'names') as $taxonomy) {
            $term_ids = wp_get_object_terms($post->ID, $taxonomy, array('fields' => 'ids'));
            if (is_wp_error($term_ids)) {
                return self::error('raos_codex_taxonomy_read_failed', 500);
            }
            $term_ids = array_values(array_unique(array_map('intval', $term_ids)));
            sort($term_ids, SORT_NUMERIC);
            $taxonomies[$taxonomy] = $term_ids;
        }
        ksort($taxonomies, SORT_STRING);
        $media_ids = self::referenced_media_ids($post);
        $document = array(
            'schema' => 'ContentDocumentV1',
            'post_type' => $post->post_type,
            'id' => (int) $post->ID,
            'status' => $post->post_status,
            'title' => $post->post_title,
            'slug' => $post->post_name,
            'excerpt' => $post->post_excerpt,
            'block_markup' => $post->post_content,
            'taxonomies' => $taxonomies,
            'media_ids' => $media_ids,
            'revision_id' => max(1, $revision_id),
            'modified_gmt' => $modified_gmt,
        );
        $document['content_sha256'] = self::document_hash($document);
        return $document;
    }

    private static function normalized_modified_gmt($post)
    {
        if (! $post instanceof WP_Post) {
            return false;
        }
        $mysql_pattern = '/\A[1-9][0-9]{3}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\z/';
        $modified_gmt = is_string($post->post_modified_gmt)
            ? $post->post_modified_gmt
            : '';
        if ('0000-00-00 00:00:00' === $modified_gmt
            || preg_match($mysql_pattern, $modified_gmt) !== 1) {
            if (! is_string($post->post_modified)
                || '0000-00-00 00:00:00' === $post->post_modified
                || preg_match($mysql_pattern, $post->post_modified) !== 1) {
                return false;
            }
            $modified_gmt = get_gmt_from_date($post->post_modified, 'Y-m-d H:i:s');
        }
        if (! is_string($modified_gmt)
            || preg_match($mysql_pattern, $modified_gmt) !== 1) {
            return false;
        }
        $modified_timestamp = strtotime($modified_gmt . ' UTC');
        if (false === $modified_timestamp || $modified_timestamp < 0) {
            return false;
        }
        return gmdate('Y-m-d\TH:i:s\Z', $modified_timestamp);
    }

    public static function document_hash($document)
    {
        if (! is_array($document)) {
            return false;
        }
        $keys = array(
            'schema',
            'post_type',
            'id',
            'status',
            'title',
            'slug',
            'excerpt',
            'block_markup',
            'taxonomies',
            'media_ids',
        );
        $material = array();
        foreach ($keys as $key) {
            if (! array_key_exists($key, $document)) {
                return false;
            }
            $material[$key] = $document[$key];
        }
        return RAOS_Codex_MCP_Store::hash($material);
    }

    public static function precondition_matches($document, $precondition)
    {
        return is_array($document)
            && is_array($precondition)
            && isset($precondition['revision_id'], $precondition['modified_gmt'], $precondition['content_sha256'])
            && count($precondition) === 3
            && (int) $precondition['revision_id'] === (int) $document['revision_id']
            && is_string($precondition['modified_gmt'])
            && hash_equals($document['modified_gmt'], $precondition['modified_gmt'])
            && RAOS_Codex_MCP_Store::is_sha256($precondition['content_sha256'])
            && hash_equals($document['content_sha256'], $precondition['content_sha256']);
    }

    private static function validate_write_document($input, $partial, $expected_post_type)
    {
        if (! is_array($input)) {
            return self::error('raos_codex_document_invalid', 400);
        }
        $allowed = array('post_type', 'title', 'slug', 'excerpt', 'block_markup', 'taxonomies', 'media_ids');
        if (array_diff(array_keys($input), $allowed)) {
            return self::error('raos_codex_document_invalid', 400);
        }
        if (! $partial && array_diff($allowed, array_keys($input))) {
            return self::error('raos_codex_document_invalid', 400);
        }
        if ($partial && empty($input)) {
            return self::error('raos_codex_document_invalid', 400);
        }
        if (isset($input['post_type'])) {
            if (! in_array($input['post_type'], array('post', 'page'), true)
                || (! is_null($expected_post_type) && $input['post_type'] !== $expected_post_type)) {
                return self::error('raos_codex_post_type_invalid', 400);
            }
        } elseif (! $partial) {
            return self::error('raos_codex_post_type_invalid', 400);
        }
        if (isset($input['title'])
            && (! is_string($input['title'])
                || '' === trim($input['title'])
                || strlen($input['title']) > 2000
                || wp_strip_all_tags($input['title']) !== $input['title'])) {
            return self::error('raos_codex_title_invalid', 400);
        }
        if (isset($input['slug'])
            && (! is_string($input['slug'])
                || strlen($input['slug']) > 200
                || sanitize_title($input['slug']) !== $input['slug']
                || preg_match('/\A[a-z0-9]+(?:-[a-z0-9]+)*\z/D', $input['slug']) !== 1)) {
            return self::error('raos_codex_slug_invalid', 400);
        }
        if (isset($input['excerpt'])
            && (! is_string($input['excerpt'])
                || strlen($input['excerpt']) > 10000
                || wp_kses_post($input['excerpt']) !== $input['excerpt'])) {
            return self::error('raos_codex_excerpt_invalid', 400);
        }
        if (isset($input['block_markup'])
            && (! is_string($input['block_markup'])
                || strlen($input['block_markup']) > self::MAX_CONTENT_BYTES
                || wp_kses_post($input['block_markup']) !== $input['block_markup'])) {
            return self::error('raos_codex_block_markup_invalid', 400);
        }
        $post_type = isset($input['post_type']) ? $input['post_type'] : $expected_post_type;
        if (isset($input['taxonomies'])) {
            $valid_taxonomies = self::validate_taxonomies($post_type, $input['taxonomies']);
            if (is_wp_error($valid_taxonomies)) {
                return $valid_taxonomies;
            }
            $input['taxonomies'] = $valid_taxonomies;
        }
        if (isset($input['media_ids'])) {
            $valid_media = self::validate_media($input['media_ids']);
            if (is_wp_error($valid_media)) {
                return $valid_media;
            }
            $input['media_ids'] = $valid_media;
            if (isset($input['block_markup'])) {
                $actual_ids = self::referenced_media_ids_from_markup($input['block_markup']);
                if (array_diff($actual_ids, $valid_media)) {
                    return self::error('raos_codex_media_manifest_incomplete', 400);
                }
            }
        }
        return $input;
    }

    private static function validate_taxonomies($post_type, $taxonomies)
    {
        if (! in_array($post_type, array('post', 'page'), true)
            || ! is_array($taxonomies)
            || count($taxonomies) > 32) {
            return self::error('raos_codex_taxonomies_invalid', 400);
        }
        $allowed = get_object_taxonomies($post_type, 'names');
        $result = array();
        foreach ($taxonomies as $taxonomy => $term_ids) {
            if (! is_string($taxonomy)
                || ! in_array($taxonomy, $allowed, true)
                || ! is_array($term_ids)
                || count($term_ids) > 128) {
                return self::error('raos_codex_taxonomies_invalid', 400);
            }
            $validated = array();
            foreach ($term_ids as $term_id) {
                if (! is_int($term_id) || $term_id < 1 || ! term_exists($term_id, $taxonomy)) {
                    return self::error('raos_codex_taxonomy_reference_invalid', 400);
                }
                $validated[] = $term_id;
            }
            $validated = array_values(array_unique($validated));
            sort($validated, SORT_NUMERIC);
            $result[$taxonomy] = $validated;
        }
        ksort($result, SORT_STRING);
        return $result;
    }

    private static function validate_media($media_ids)
    {
        if (! is_array($media_ids) || count($media_ids) > 256) {
            return self::error('raos_codex_media_invalid', 400);
        }
        $result = array();
        foreach ($media_ids as $media_id) {
            if (! is_int($media_id) || $media_id < 1 || 'attachment' !== get_post_type($media_id)) {
                return self::error('raos_codex_media_reference_invalid', 400);
            }
            $result[] = $media_id;
        }
        $result = array_values(array_unique($result));
        sort($result, SORT_NUMERIC);
        return $result;
    }

    public static function apply_taxonomies($post_id, $post_type, $taxonomies)
    {
        $validated = self::validate_taxonomies($post_type, $taxonomies);
        if (is_wp_error($validated)) {
            return $validated;
        }
        foreach ($validated as $taxonomy => $term_ids) {
            $result = wp_set_object_terms($post_id, $term_ids, $taxonomy, false);
            if (is_wp_error($result)) {
                return self::error('raos_codex_taxonomy_write_failed', 500);
            }
        }
        return true;
    }

    public static function validate_release_references($document)
    {
        if (! is_array($document)
            || ! isset(
                $document['post_type'],
                $document['taxonomies'],
                $document['media_ids'],
                $document['block_markup']
            )) {
            return self::error('raos_codex_content_document_invalid', 400);
        }
        $taxonomies = self::validate_taxonomies(
            $document['post_type'],
            $document['taxonomies']
        );
        if (is_wp_error($taxonomies)) {
            return $taxonomies;
        }
        $media = self::validate_media($document['media_ids']);
        if (is_wp_error($media)) {
            return $media;
        }
        $actual = self::referenced_media_ids_from_markup($document['block_markup']);
        if (array_diff($actual, $media)) {
            return self::error('raos_codex_media_manifest_incomplete', 400);
        }
        return true;
    }

    private static function referenced_media_ids($post)
    {
        $ids = self::referenced_media_ids_from_markup($post->post_content);
        $thumbnail = get_post_thumbnail_id($post->ID);
        if ($thumbnail > 0 && 'attachment' === get_post_type($thumbnail)) {
            $ids[] = (int) $thumbnail;
        }
        $ids = array_values(array_unique($ids));
        sort($ids, SORT_NUMERIC);
        return $ids;
    }

    private static function referenced_media_ids_from_markup($markup)
    {
        $ids = array();
        if (! is_string($markup)) {
            return $ids;
        }
        if (preg_match_all('/(?:wp-image-|"id"\s*:\s*)([1-9][0-9]*)/', $markup, $matches)) {
            foreach ($matches[1] as $candidate) {
                $id = (int) $candidate;
                if ('attachment' === get_post_type($id)) {
                    $ids[] = $id;
                }
            }
        }
        return array_values(array_unique($ids));
    }

    public static function error($code, $status)
    {
        return new WP_Error($code, 'The bounded WordPress operation was refused.', array('status' => $status));
    }
}
