<?php
/** Executable fail-closed harness for the bounded Draft-writer read projection. */

declare(strict_types=1);

define('ABSPATH', __DIR__ . '/');
define('REST_REQUEST', true);

$_SERVER['REQUEST_METHOD'] = 'GET';
$_SERVER['REQUEST_URI'] = '/wp-json/wp/v2/posts';

final class WP_Error
{
    public array $errors = array();

    public function __construct($code = '', $message = '', $data = null)
    {
        if ($code !== '') {
            $this->add($code, $message, $data);
        }
    }

    public function add($code, $message, $data = null): void
    {
        $this->errors[(string) $code][] = array($message, $data);
    }
}

class WP_REST_Posts_Controller
{
    public function get_items(
        $operator = null,
        $user = null,
        $post_id = null,
        $caps = null,
        $mode = 'core'
    )
    {
        if ($operator !== null) {
            if ($mode === 'snapshot-auth') {
                return kurashinoshirube_authorize_snapshot_meta(
                    $operator,
                    $user,
                    $post_id,
                    $caps
                );
            }
            if ($mode === 'snapshot-hide') {
                return kurashinoshirube_hide_public_snapshot_meta(
                    $operator,
                    $user,
                    $post_id,
                    $caps
                );
            }
            return $this->check_update_permission(
                $operator,
                $user,
                $post_id,
                $caps
            );
        }
    }

    public function get_items_permissions_check(): void
    {
    }

    public function check_update_permission($operator, $user, $post_id, $caps)
    {
        return $operator->filter_draft_writer_read_projection_capabilities(
            $user->allcaps,
            $caps,
            array('edit_post', $user->ID, $post_id),
            $user
        );
    }

    public function create_item(): void
    {
    }

    public function create_item_permissions_check(): void
    {
    }

    public function update_item(): void
    {
    }

    public function update_item_permissions_check(): void
    {
    }
}

final class Other_REST_Posts_Controller extends WP_REST_Posts_Controller
{
}

final class WP_REST_Request
{
    private string $method;
    private string $route;
    private string $body;
    private array $query;
    private array $url;
    private array $body_params;
    private mixed $json;
    private array $files;

    public function __construct(
        string $method,
        string $route,
        array $query,
        string $body = '',
        array $url = array(),
        array $body_params = array(),
        mixed $json = null,
        array $files = array()
    ) {
        $this->method = $method;
        $this->route = $route;
        $this->query = $query;
        $this->body = $body;
        $this->url = $url;
        $this->body_params = $body_params;
        $this->json = $json;
        $this->files = $files;
    }

    public function get_method(): string
    {
        return $this->method;
    }

    public function get_route(): string
    {
        return $this->route;
    }

    public function get_body(): string
    {
        return $this->body;
    }

    public function get_query_params(): array
    {
        return $this->query;
    }

    public function get_url_params(): array
    {
        return $this->url;
    }

    public function get_body_params(): array
    {
        return $this->body_params;
    }

    public function get_json_params(): mixed
    {
        return $this->json;
    }

    public function get_file_params(): array
    {
        return $this->files;
    }
}

final class WP_Role
{
    public array $capabilities;

    public function __construct(array $capabilities)
    {
        $this->capabilities = $capabilities;
    }
}

final class WP_User
{
    public int $ID;
    public string $user_login;
    public array $roles;
    public array $caps;
    public array $allcaps;

    public function __construct(
        int $id,
        array $roles,
        array $caps,
        array $allcaps,
        string $user_login = 'raos-draft-writer'
    ) {
        $this->ID = $id;
        $this->user_login = $user_login;
        $this->roles = $roles;
        $this->caps = $caps;
        $this->allcaps = $allcaps;
    }

    public function exists(): bool
    {
        return $this->ID > 0;
    }
}

final class WP_Post
{
    public int $ID;
    public string $post_type;
    public string $post_name;
    public string $post_status;
    public string $post_author;

    public function __construct(
        int $id,
        string $slug,
        string $status,
        string $author = '1'
    ) {
        $this->ID = $id;
        $this->post_type = 'post';
        $this->post_name = $slug;
        $this->post_status = $status;
        $this->post_author = $author;
    }
}

final class RAOS_Bounded_Operator
{
}

$GLOBALS['raos_roles'] = array();
$GLOBALS['raos_current_user'] = null;
$GLOBALS['raos_posts'] = array();

function get_role($role)
{
    return $GLOBALS['raos_roles'][(string) $role] ?? null;
}

function wp_get_current_user()
{
    return $GLOBALS['raos_current_user'];
}

function get_post($post_id)
{
    return $GLOBALS['raos_posts'][(int) $post_id] ?? null;
}

function is_multisite(): bool
{
    return false;
}

function is_ssl(): bool
{
    return true;
}

function home_url($path = '/'): string
{
    unset($path);
    return 'https://kurashinoshirube.com/';
}

function site_url($path = '/'): string
{
    unset($path);
    return 'https://kurashinoshirube.com/';
}

function untrailingslashit($value): string
{
    return rtrim((string) $value, '/');
}

function raos_assert($condition, string $message): void
{
    if ($condition !== true) {
        throw new RuntimeException($message);
    }
}

function kurashinoshirube_authorize_snapshot_meta(
    $operator,
    $user,
    $post_id,
    $caps
) {
    return $operator->filter_draft_writer_read_projection_capabilities(
        $user->allcaps,
        $caps,
        array('edit_post', $user->ID, $post_id),
        $user
    );
}

function kurashinoshirube_hide_public_snapshot_meta(
    $operator,
    $user,
    $post_id,
    $caps
) {
    return $operator->filter_draft_writer_read_projection_capabilities(
        $user->allcaps,
        $caps,
        array('edit_post', $user->ID, $post_id),
        $user
    );
}

require dirname(__DIR__, 3)
    . '/changes/st-1704/publication-operator-v2/wordpress-plugin/'
    . 'raos-bounded-operator/includes/st1704-publication-bindings.v2.php';
require dirname(__DIR__, 3)
    . '/changes/st-1704/publication-operator-v2/wordpress-plugin/'
    . 'raos-bounded-operator/includes/st1704-publication-controller.v2.php';

const RAOS_TEST_FIELDS =
    'id,type,slug,status,categories,date_gmt,modified_gmt,title.raw,'
    . 'excerpt.raw,content.raw,meta._raos_publication_snapshot_v1';

$base_caps = array(
    'read' => true,
    'edit_posts' => true,
    'raos_draft_writer' => true,
);
$user = new WP_User(
    501,
    array('raos_draft_writer'),
    array('raos_draft_writer' => true),
    $base_caps
);
$GLOBALS['raos_current_user'] = $user;
$GLOBALS['raos_roles']['raos_draft_writer'] = new WP_Role(
    array('read' => true, 'edit_posts' => true)
);

$public = array(
    'carry-on-suitcase-comparison' => 19,
    'portable-power-station-guide' => 28,
    'anker-solix-c300-c800-c1000-differences' => 29,
    'countertop-dishwasher-for-small-households' => 41,
    'compact-robot-vacuum-shortlist' => 30,
);
foreach ($public as $slug => $post_id) {
    $GLOBALS['raos_posts'][$post_id] = new WP_Post($post_id, $slug, 'publish');
}
$review_slug = 'raos-review-carry-on-suitcase-comparison-'
    . 'f743a2944f1adca0a8fef2cdd850567767f2257836bb807c47901b25c04fc942';
$GLOBALS['raos_posts'][26] = new WP_Post(26, $review_slug, 'draft');
$GLOBALS['raos_posts'][999] = new WP_Post(999, 'arbitrary-post', 'publish');

$reflection = new ReflectionClass('RAOS_ST1704_Publication_Controller_V2');
$operator = $reflection->newInstanceWithoutConstructor();
$ready = $reflection->getProperty('combined_firewall_ready');
$ready->setAccessible(true);
$ready->setValue($operator, true);
$core = new WP_REST_Posts_Controller();
$GLOBALS['raos_core'] = $core;
$handler = array(
    'callback' => array($core, 'get_items'),
    'permission_callback' => array($core, 'get_items_permissions_check'),
);
$create_handler = array(
    'callback' => array($core, 'create_item'),
    'permission_callback' => array($core, 'create_item_permissions_check'),
);
$update_handler = array(
    'callback' => array($core, 'update_item'),
    'permission_callback' => array($core, 'update_item_permissions_check'),
);

function raos_request(array $query, string $method = 'GET', array $overrides = array())
{
    return new WP_REST_Request(
        $method,
        $overrides['route'] ?? '/wp/v2/posts',
        $query,
        $overrides['body'] ?? '',
        $overrides['url'] ?? array(),
        $overrides['body_params'] ?? array(),
        $overrides['json'] ?? null,
        $overrides['files'] ?? array()
    );
}

function raos_public_query(string $slug, int $per_page = 100): array
{
    return array(
        'context' => 'edit',
        'slug' => array($slug),
        'status' => array('publish'),
        '_fields' => RAOS_TEST_FIELDS,
        'per_page' => $per_page,
    );
}

function raos_authorize_and_prepare(
    $operator,
    WP_User $user,
    WP_REST_Request $request,
    array $handler
) {
    $GLOBALS['raos_current_user'] = $user;
    $operator->record_application_password_authentication($user, array());
    return $operator->prepare_draft_writer_read_projection(null, $handler, $request);
}

function raos_filter(
    $operator,
    WP_User $user,
    int $post_id,
    array $caps,
    string $meta_cap = 'edit_post'
): array {
    if ($meta_cap !== 'edit_post') {
        return $operator->filter_draft_writer_read_projection_capabilities(
            $user->allcaps,
            $caps,
            array($meta_cap, $user->ID, $post_id),
            $user
        );
    }
    return $GLOBALS['raos_core']->get_items(
        $operator,
        $user,
        $post_id,
        $caps
    );
}

function raos_reset_projection($operator): void
{
    $_SERVER['REQUEST_METHOD'] = 'GET';
    $_SERVER['REQUEST_URI'] = '/wp-json/wp/v2/posts';
    unset($_SERVER['HTTP_X_HTTP_METHOD_OVERRIDE']);
    $operator->clear_draft_writer_read_projection_on_shutdown();
}

function raos_assert_denied(
    $operator,
    WP_User $user,
    WP_REST_Request $request,
    array $handler,
    int $post_id = 28,
    array $caps = array('edit_others_posts', 'edit_published_posts')
): void {
    raos_reset_projection($operator);
    raos_authorize_and_prepare($operator, $user, $request, $handler);
    raos_assert(
        raos_filter($operator, $user, $post_id, $caps) === $user->allcaps,
        'denied request gained a capability'
    );
}

// Every exact single-target formal read projects only its fixed post ID.
foreach ($public as $slug => $post_id) {
    raos_reset_projection($operator);
    raos_authorize_and_prepare(
        $operator,
        $user,
        raos_request(raos_public_query($slug)),
        $handler
    );
    $granted = raos_filter(
        $operator,
        $user,
        $post_id,
        array('edit_others_posts', 'edit_published_posts')
    );
    raos_assert(
        ($granted['edit_others_posts'] ?? false) === true
            && ($granted['edit_published_posts'] ?? false) === true,
        'fixed public target was not projected'
    );
    raos_assert(
        raos_filter(
            $operator,
            $user,
            999,
            array('edit_others_posts', 'edit_published_posts')
        ) === $base_caps,
        'arbitrary post ID was projected'
    );
}

// WordPress's update-permission row filter is bounded to the exact controller
// while inside its exact get_items callback.
raos_reset_projection($operator);
raos_authorize_and_prepare(
    $operator,
    $user,
    raos_request(raos_public_query('portable-power-station-guide')),
    $handler
);
raos_assert(
    $core->check_update_permission(
        $operator,
        $user,
        28,
        array('edit_others_posts', 'edit_published_posts')
    ) === $base_caps,
    'out-of-get_items update-permission check gained projection'
);

// Related reads are the four fixed non-suitcase targets at per_page=2.
foreach (array_slice($public, 1, null, true) as $slug => $post_id) {
    raos_reset_projection($operator);
    raos_authorize_and_prepare(
        $operator,
        $user,
        raos_request(raos_public_query($slug, 2)),
        $handler
    );
    $granted = raos_filter(
        $operator,
        $user,
        $post_id,
        array('edit_others_posts', 'edit_published_posts')
    );
    raos_assert(isset($granted['edit_others_posts']), 'related target denied');
}
raos_assert_denied(
    $operator,
    $user,
    raos_request(raos_public_query('carry-on-suitcase-comparison', 2)),
    $handler,
    19
);

// The homepage query may project exactly the five fixed pilot post IDs.
$homepage_query = array(
    'context' => 'edit',
    'status' => array('publish'),
    'slug' => array_keys($public),
    'page' => 1,
    'per_page' => 5,
    '_fields' => RAOS_TEST_FIELDS,
);
raos_reset_projection($operator);
raos_authorize_and_prepare(
    $operator,
    $user,
    raos_request($homepage_query),
    $handler
);
foreach ($public as $post_id) {
    $granted = raos_filter(
        $operator,
        $user,
        $post_id,
        array('edit_others_posts', 'edit_published_posts')
    );
    raos_assert(isset($granted['edit_others_posts']), 'homepage target denied');
}

// The only Draft elevation is fixed post 26 at a digest-shaped carry-on slug.
$review_query = array(
    'context' => 'edit',
    'slug' => array($review_slug),
    'status' => array('draft'),
    '_fields' => RAOS_TEST_FIELDS,
    'page' => 1,
    'per_page' => 100,
);
raos_reset_projection($operator);
raos_authorize_and_prepare(
    $operator,
    $user,
    raos_request($review_query),
    $handler
);
$granted = raos_filter($operator, $user, 26, array('edit_others_posts'));
raos_assert(
    ($granted['edit_others_posts'] ?? false) === true,
    'fixed carry review Draft denied'
);

// Core's same-author mapped-cap shapes remain exact and add no broad primitive.
raos_reset_projection($operator);
$GLOBALS['raos_posts'][28]->post_author = '501';
raos_authorize_and_prepare(
    $operator,
    $user,
    raos_request(raos_public_query('portable-power-station-guide')),
    $handler
);
$granted = raos_filter($operator, $user, 28, array('edit_published_posts'));
raos_assert(
    ($granted['edit_published_posts'] ?? false) === true
        && ! isset($granted['edit_others_posts']),
    'same-author published mapped caps drifted'
);
$GLOBALS['raos_posts'][28]->post_author = '1';
raos_reset_projection($operator);
$GLOBALS['raos_posts'][26]->post_author = '501';
raos_authorize_and_prepare(
    $operator,
    $user,
    raos_request($review_query),
    $handler
);
raos_assert(
    raos_filter($operator, $user, 26, array('edit_posts')) === $base_caps,
    'same-author Draft mapped caps drifted'
);
$GLOBALS['raos_posts'][26]->post_author = '1';

// The two fixed theme snapshot readers are the only non-core allowed call sites.
raos_reset_projection($operator);
raos_authorize_and_prepare(
    $operator,
    $user,
    raos_request(raos_public_query('portable-power-station-guide')),
    $handler
);
foreach (array('snapshot-auth', 'snapshot-hide') as $snapshot_mode) {
    $granted = $core->get_items(
        $operator,
        $user,
        28,
        array('edit_others_posts', 'edit_published_posts'),
        $snapshot_mode
    );
    raos_assert(
        isset($granted['edit_others_posts']),
        'fixed theme snapshot read call site was denied'
    );
}

// Exact core collection POST keeps base own-Draft authority but never projects.
raos_reset_projection($operator);
$_SERVER['REQUEST_METHOD'] = 'POST';
$GLOBALS['raos_current_user'] = $user;
$operator->record_application_password_authentication($user, array());
$base_response = new stdClass();
$observed_response = $operator->prepare_draft_writer_read_projection(
    $base_response,
    $create_handler,
    raos_request(
        array(),
        'POST',
        array(
            'body' => '{"status":"draft","title":"owned"}',
            'json' => array('status' => 'draft', 'title' => 'owned'),
        )
    )
);
raos_assert(
    $observed_response === $base_response,
    'exact collection create base response changed'
);
raos_assert(
    raos_filter(
        $operator,
        $user,
        28,
        array('edit_others_posts', 'edit_published_posts')
    ) === $base_caps,
    'collection POST armed read projection'
);
raos_reset_projection($operator);

// An item-update handler under the same raw collection path is hard-refused.
$_SERVER['REQUEST_METHOD'] = 'POST';
$GLOBALS['raos_current_user'] = $user;
$operator->record_application_password_authentication($user, array());
$item_response = $operator->prepare_draft_writer_read_projection(
    null,
    $update_handler,
    raos_request(array(), 'POST', array('route' => '/wp/v2/posts/28'))
);
raos_assert($item_response instanceof WP_Error, 'item update was not refused');
raos_reset_projection($operator);

// Method, raw method, route, body buckets, handler and query drift all deny.
foreach (array('POST', 'PUT', 'DELETE') as $method) {
    $_SERVER['REQUEST_METHOD'] = $method;
    raos_assert_denied(
        $operator,
        $user,
        raos_request(raos_public_query('portable-power-station-guide'), $method),
        $handler
    );
}
$_SERVER['REQUEST_METHOD'] = 'POST';
raos_reset_projection($operator);
$_SERVER['REQUEST_METHOD'] = 'POST';
raos_authorize_and_prepare(
    $operator,
    $user,
    raos_request(raos_public_query('portable-power-station-guide')),
    $handler
);
raos_assert(
    raos_filter(
        $operator,
        $user,
        28,
        array('edit_others_posts', 'edit_published_posts')
    ) === $base_caps,
    'raw POST method gained projection'
);
raos_reset_projection($operator);
$_SERVER['HTTP_X_HTTP_METHOD_OVERRIDE'] = 'GET';
raos_authorize_and_prepare(
    $operator,
    $user,
    raos_request(raos_public_query('portable-power-station-guide')),
    $handler
);
raos_assert(
    raos_filter(
        $operator,
        $user,
        28,
        array('edit_others_posts', 'edit_published_posts')
    ) === $base_caps,
    'method override gained projection'
);
foreach (array(
    array('route' => '/wp/v2/posts/28'),
    array('body' => '{}'),
    array('url' => array('id' => '28')),
    array('body_params' => array('status' => 'publish')),
    array('json' => array('status' => 'publish')),
    array('files' => array('upload' => array())),
) as $override) {
    raos_assert_denied(
        $operator,
        $user,
        raos_request(
            raos_public_query('portable-power-station-guide'),
            'GET',
            $override
        ),
        $handler
    );
}
$other_core = new WP_REST_Posts_Controller();
$bad_handlers = array(
    array(
        'callback' => array($core, 'other'),
        'permission_callback' => array($core, 'get_items_permissions_check'),
    ),
    array(
        'callback' => array($core, 'get_items'),
        'permission_callback' => array($other_core, 'get_items_permissions_check'),
    ),
    array(
        'callback' => array($core, 'get_items'),
        'permission_callback' => array($core, 'other'),
    ),
    array(
        'callback' => array(new Other_REST_Posts_Controller(), 'get_items'),
        'permission_callback' => array(
            new Other_REST_Posts_Controller(),
            'get_items_permissions_check'
        ),
    ),
);
$subclass = new Other_REST_Posts_Controller();
$bad_handlers[] = array(
    'callback' => array($subclass, 'get_items'),
    'permission_callback' => array($subclass, 'get_items_permissions_check'),
);
foreach ($bad_handlers as $bad_handler) {
    raos_assert_denied(
        $operator,
        $user,
        raos_request(raos_public_query('portable-power-station-guide')),
        $bad_handler
    );
}

$query_drifts = array();
$extra = raos_public_query('portable-power-station-guide');
$extra['author'] = array(1);
$query_drifts[] = $extra;
$field = raos_public_query('portable-power-station-guide');
$field['_fields'] .= ',author';
$query_drifts[] = $field;
$arbitrary = raos_public_query('arbitrary-post');
$query_drifts[] = $arbitrary;
$status = raos_public_query('portable-power-station-guide');
$status['status'][] = 'draft';
$query_drifts[] = $status;
$slugs = raos_public_query('portable-power-station-guide');
$slugs['slug'][] = 'arbitrary-post';
$query_drifts[] = $slugs;
$string_page = raos_public_query('portable-power-station-guide');
$string_page['per_page'] = '100';
$query_drifts[] = $string_page;
$target_fields = raos_public_query('portable-power-station-guide');
$target_fields['_fields'] = 'id,type,slug,status';
$query_drifts[] = $target_fields;
$paged = raos_public_query('portable-power-station-guide');
$paged['page'] = 1;
$query_drifts[] = $paged;
$bad_digest = $review_query;
$bad_digest['slug'] = array(
    'raos-review-carry-on-suitcase-comparison-' . str_repeat('g', 64),
);
$query_drifts[] = $bad_digest;
foreach ($query_drifts as $drift) {
    raos_assert_denied(
        $operator,
        $user,
        raos_request($drift),
        $handler
    );
}

// Cookie-only/no-AP, identity drift, unexpected mapped caps and post drift deny.
raos_reset_projection($operator);
$operator->prepare_draft_writer_read_projection(
    null,
    $handler,
    raos_request(raos_public_query('portable-power-station-guide'))
);
raos_assert(
    raos_filter(
        $operator,
        $user,
        28,
        array('edit_others_posts', 'edit_published_posts')
    ) === $base_caps,
    'cookie-only request gained projection'
);
$drift_user = new WP_User(
    501,
    array('raos_draft_writer'),
    array('raos_draft_writer' => true),
    $base_caps + array('publish_posts' => true)
);
$drift_users = array(
    $drift_user,
    new WP_User(
        501,
        array('raos_draft_writer', 'subscriber'),
        array('raos_draft_writer' => true),
        $base_caps
    ),
    new WP_User(
        501,
        array('raos_draft_writer'),
        array('raos_draft_writer' => true, 'edit_others_posts' => true),
        $base_caps
    ),
    new WP_User(
        501,
        array('raos_draft_writer'),
        array('raos_draft_writer' => true),
        $base_caps,
        'different-login'
    ),
);

// The AP authentication hook rejects non-REST/non-GET transport and identity drift.
$transport_error = new WP_Error();
$operator->guard_draft_writer_application_password_transport(
    $transport_error,
    $user,
    array(),
    'not-inspected'
);
raos_assert($transport_error->errors === array(), 'exact GET transport was denied');
$_SERVER['REQUEST_METHOD'] = 'POST';
$transport_error = new WP_Error();
$operator->guard_draft_writer_application_password_transport(
    $transport_error,
    $user,
    array(),
    'not-inspected'
);
raos_assert($transport_error->errors === array(), 'exact POST transport was denied');
$_SERVER['REQUEST_METHOD'] = 'GET';
$_SERVER['REQUEST_URI'] = '/wp-json/wp/v2/posts?context=edit';
$transport_error = new WP_Error();
$operator->guard_draft_writer_application_password_transport(
    $transport_error,
    $user,
    array(),
    'not-inspected'
);
raos_assert(
    $transport_error->errors === array(),
    'exact path with query string was denied'
);
foreach (array(
    array('method' => 'PUT', 'uri' => '/wp-json/wp/v2/posts/28'),
    array('method' => 'PATCH', 'uri' => '/wp-json/wp/v2/posts'),
    array('method' => 'DELETE', 'uri' => '/wp-json/wp/v2/posts'),
    array('method' => 'get', 'uri' => '/wp-json/wp/v2/posts'),
    array('method' => 'POST', 'uri' => '/xmlrpc.php'),
    array('method' => 'GET', 'uri' => '/wp-json/wp/v2/plugins'),
    array(
        'method' => 'POST',
        'uri' => '/wp-json/wp/v2/posts?rest_route=%2Fwp%2Fv2%2Fposts%2F28',
    ),
    array(
        'method' => 'POST',
        'uri' => '/wp-json/wp/v2/posts?_method=PUT',
    ),
) as $transport) {
    $_SERVER['REQUEST_METHOD'] = $transport['method'];
    $_SERVER['REQUEST_URI'] = $transport['uri'];
    $transport_error = new WP_Error();
    $operator->guard_draft_writer_application_password_transport(
        $transport_error,
        $user,
        array(),
        'not-inspected'
    );
    raos_assert(
        isset(
            $transport_error->errors[
                'raos_st1704_draft_writer_transport_forbidden'
            ]
        ),
        'non-read AP transport was accepted'
    );
}
$_SERVER['REQUEST_METHOD'] = 'GET';
$_SERVER['REQUEST_URI'] = '/wp-json/wp/v2/posts';
$_SERVER['HTTP_X_HTTP_METHOD_OVERRIDE'] = 'GET';
$transport_error = new WP_Error();
$operator->guard_draft_writer_application_password_transport(
    $transport_error,
    $user,
    array(),
    'not-inspected'
);
raos_assert(
    isset(
        $transport_error->errors[
            'raos_st1704_draft_writer_transport_forbidden'
        ]
    ),
    'method-override transport was accepted'
);
unset($_SERVER['HTTP_X_HTTP_METHOD_OVERRIDE']);
$_SERVER['REQUEST_METHOD'] = 'GET';
$_SERVER['REQUEST_URI'] = '/wp-json/wp/v2/posts';
foreach ($drift_users as $identity_drift) {
    $transport_error = new WP_Error();
    $operator->guard_draft_writer_application_password_transport(
        $transport_error,
        $identity_drift,
        array(),
        'not-inspected'
    );
    raos_assert(
        isset(
            $transport_error->errors[
                'raos_st1704_draft_writer_transport_forbidden'
            ]
        ),
        'drifted Draft-writer AP identity was accepted'
    );
}
$GLOBALS['raos_roles']['raos_draft_writer']->capabilities['publish_posts'] = true;
$transport_error = new WP_Error();
$operator->guard_draft_writer_application_password_transport(
    $transport_error,
    $user,
    array(),
    'not-inspected'
);
raos_assert(
    isset(
        $transport_error->errors[
            'raos_st1704_draft_writer_transport_forbidden'
        ]
    ),
    'drifted role capabilities were accepted'
);
unset($GLOBALS['raos_roles']['raos_draft_writer']->capabilities['publish_posts']);

// The immutable login keeps a formerly assigned user transport-confined even
// if an administrator removes or replaces the role before revoking the AP.
$replaced_role_user = new WP_User(
    501,
    array('subscriber'),
    array('subscriber' => true),
    array('read' => true, 'subscriber' => true)
);
$transport_error = new WP_Error();
$operator->guard_draft_writer_application_password_transport(
    $transport_error,
    $replaced_role_user,
    array(),
    'not-inspected'
);
raos_assert(
    isset(
        $transport_error->errors[
            'raos_st1704_draft_writer_transport_forbidden'
        ]
    ),
    'fixed Draft-writer login escaped confinement after role replacement'
);
raos_reset_projection($operator);
$GLOBALS['raos_current_user'] = $replaced_role_user;
$operator->record_application_password_authentication(
    $replaced_role_user,
    array()
);
$operator->prepare_draft_writer_read_projection(
    null,
    $handler,
    raos_request(raos_public_query('portable-power-station-guide'))
);
raos_assert(
    raos_filter(
        $operator,
        $replaced_role_user,
        28,
        array('edit_others_posts', 'edit_published_posts')
    ) === $replaced_role_user->allcaps,
    'role-replaced fixed-login user gained read projection'
);

// An earlier REST error is preserved and never arms the projection.
raos_reset_projection($operator);
$GLOBALS['raos_current_user'] = $user;
$operator->record_application_password_authentication($user, array());
$existing_error = new WP_Error('existing_error', 'existing');
$observed_error = $operator->prepare_draft_writer_read_projection(
    $existing_error,
    $handler,
    raos_request(raos_public_query('portable-power-station-guide'))
);
raos_assert($observed_error === $existing_error, 'existing REST error was replaced');
raos_assert(
    raos_filter(
        $operator,
        $user,
        28,
        array('edit_others_posts', 'edit_published_posts')
    ) === $base_caps,
    'existing REST error armed projection'
);

raos_reset_projection($operator);
raos_authorize_and_prepare(
    $operator,
    $user,
    raos_request(raos_public_query('portable-power-station-guide')),
    $handler
);
raos_assert(
    raos_filter($operator, $user, 28, array('do_not_allow')) === $base_caps,
    'unexpected mapped cap was overridden'
);
raos_assert(
    raos_filter(
        $operator,
        $user,
        28,
        array('edit_others_posts', 'edit_published_posts'),
        'edit_post_meta'
    ) === $base_caps,
    'non-edit_post meta-cap was overridden'
);
raos_assert(
    $operator->filter_draft_writer_read_projection_capabilities(
        $base_caps,
        array('edit_others_posts', 'edit_published_posts'),
        array('edit_post', 501, '28'),
        $user
    ) === $base_caps,
    'string post ID was accepted'
);
raos_assert(
    $operator->filter_draft_writer_read_projection_capabilities(
        $base_caps,
        array('edit_others_posts', 'edit_published_posts'),
        array('edit_post', 501, 28, 'extra'),
        $user
    ) === $base_caps,
    'extra meta-cap argument was accepted'
);
raos_assert(
    $operator->filter_draft_writer_read_projection_capabilities(
        $base_caps,
        array('edit_others_posts', 'edit_published_posts'),
        array('edit_post', 502, 28),
        $user
    ) === $base_caps,
    'wrong user ID was accepted'
);
$GLOBALS['raos_posts'][28]->post_name = 'drifted-slug';
raos_assert(
    raos_filter(
        $operator,
        $user,
        28,
        array('edit_others_posts', 'edit_published_posts')
    ) === $base_caps,
    'post slug drift gained projection'
);
$GLOBALS['raos_posts'][28]->post_name = 'portable-power-station-guide';
$GLOBALS['raos_posts'][28]->post_status = 'draft';
raos_assert(
    raos_filter(
        $operator,
        $user,
        28,
        array('edit_others_posts', 'edit_published_posts')
    ) === $base_caps,
    'post status drift gained projection'
);
$GLOBALS['raos_posts'][28]->post_status = 'publish';
$GLOBALS['raos_posts'][28]->post_type = 'page';
raos_assert(
    raos_filter(
        $operator,
        $user,
        28,
        array('edit_others_posts', 'edit_published_posts')
    ) === $base_caps,
    'post type drift gained projection'
);
$GLOBALS['raos_posts'][28]->post_type = 'post';

// State remains through callbacks, then clears after-callback, shutdown, and next before.
raos_reset_projection($operator);
raos_authorize_and_prepare(
    $operator,
    $user,
    raos_request(raos_public_query('portable-power-station-guide')),
    $handler
);
try {
    $inside_callback = $core->get_items(
        $operator,
        $user,
        28,
        array('edit_others_posts', 'edit_published_posts')
    );
    raos_assert(
        isset($inside_callback['edit_others_posts']),
        'exact callback call site was not projected'
    );
    throw new RuntimeException('simulated callback exception');
} catch (RuntimeException $exception) {
    raos_assert(
        $exception->getMessage() === 'simulated callback exception',
        'unexpected exception was caught'
    );
}
raos_assert(
    $operator->filter_draft_writer_read_projection_capabilities(
        $base_caps,
        array('edit_others_posts', 'edit_published_posts'),
        array('edit_post', 501, 28),
        $user
    ) === $base_caps,
    'caught exception left a usable out-of-callback projection'
);
$operator->clear_draft_writer_read_projection_on_shutdown();
raos_assert(
    $core->get_items(
        $operator,
        $user,
        28,
        array('edit_others_posts', 'edit_published_posts')
    ) === $base_caps,
    'shutdown-only cleanup left projection state'
);

raos_reset_projection($operator);
raos_authorize_and_prepare(
    $operator,
    $user,
    raos_request(raos_public_query('portable-power-station-guide')),
    $handler
);
$operator->clear_draft_writer_read_projection_after_callbacks(
    null,
    $handler,
    raos_request(raos_public_query('portable-power-station-guide'))
);
raos_assert(
    raos_filter(
        $operator,
        $user,
        28,
        array('edit_others_posts', 'edit_published_posts')
    ) === $base_caps,
    'after-callback did not clear state'
);
raos_authorize_and_prepare(
    $operator,
    $user,
    raos_request(raos_public_query('portable-power-station-guide')),
    $handler
);
$operator->clear_draft_writer_read_projection_on_shutdown();
raos_assert(
    raos_filter(
        $operator,
        $user,
        28,
        array('edit_others_posts', 'edit_published_posts')
    ) === $base_caps,
    'shutdown did not clear state'
);
raos_authorize_and_prepare(
    $operator,
    $user,
    raos_request(raos_public_query('portable-power-station-guide')),
    $handler
);
$operator->prepare_draft_writer_read_projection(
    null,
    $handler,
    raos_request(raos_public_query('arbitrary-post'))
);
raos_assert(
    raos_filter(
        $operator,
        $user,
        28,
        array('edit_others_posts', 'edit_published_posts')
    ) === $base_caps,
    'next before-callback did not clear state'
);

fwrite(STDOUT, "DRAFT_WRITER_READ_PROJECTION_BEHAVIOR_OK\n");
