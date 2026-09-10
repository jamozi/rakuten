<?php
/** Synthetic in-memory WordPress double. Never a real restoration receipt. */
define('WP_CLI', true); define('RAOS_LOCAL_RESTORE_SCRATCH', true);
define('WP_HTTP_BLOCK_EXTERNAL', true); define('WP_POST_REVISIONS', false);
define('DB_NAME', 'scratch_wordpress'); define('DB_HOST', 'database');
define('ABSPATH', '/var/www/html/'); define('ARRAY_A', 'ARRAY_A');
class WP_CLI {
    public static function error($code) { throw new RuntimeException($code); }
    public static function success($text) {}
}
function wp_get_environment_type() { return 'local'; }
function home_url($path = '') { return 'http://scratch.wordpress.invalid' . $path; }
function site_url($path = '') { return home_url($path); }
$GLOBALS['synthetic_posts'] = array();
$GLOBALS['synthetic_options'] = array();
$GLOBALS['synthetic_terms'] = array(1 => array('name' => 'Uncategorized', 'slug' => 'uncategorized'));
$GLOBALS['synthetic_taxonomies'] = array(1 => 'category');
$GLOBALS['synthetic_relationships'] = array();
$GLOBALS['synthetic_filters'] = array();
function get_option($key, $fallback = false) { return $GLOBALS['synthetic_options'][$key] ?? $fallback; }
function update_option($key, $value) { $GLOBALS['synthetic_options'][$key] = $value; return true; }
function wp_json_encode($value, $flags = 0) { return json_encode($value, $flags); }
function wp_kses_post($value) {
    return preg_match('/<(?:script|form)\\b|data:image\\/|[\\s\\/]on[a-z0-9_-]+\\s*=|java(?:&#0*9;|&#x0*9;|\\s)*script:/i', $value) ? '' : $value;
}
function wp_kses_allowed_html($context) { return array(); }
function wp_allowed_protocols() { return array('http', 'https', 'mailto'); }
function wp_kses($value, $allowed, $protocols) {
    return preg_match('/<(?:script|iframe|object|embed)\\b|[\\s\\/]on[a-z0-9_-]+\\s*=|java(?:&#0*9;|&#x0*9;|\\s)*script:/i', $value) ? '' : $value;
}
function safecss_filter_attr($value) { return $value; }
function wp_parse_url($value) { return parse_url($value); }
class WP_HTML_Tag_Processor {
    private array $tags = array();
    private int $index = -1;
    private array $attributes = array();
    private string $html;
    public function __construct(string $html) {
        $this->html = $html;
        preg_match_all('/<\\s*([a-z][a-z0-9:-]*)\\b([^>]*)>/i', $html, $this->tags, PREG_SET_ORDER);
    }
    public function next_tag($query = null): bool {
        do { $this->index++; } while (isset($this->tags[$this->index]) && is_array($query) && isset($query['tag_name']) && strtoupper($this->tags[$this->index][1]) !== $query['tag_name']);
        if (! isset($this->tags[$this->index])) { return false; }
        $this->attributes = array();
        preg_match_all('/[\\s\\/]([a-z_:][a-z0-9_.:-]*)(?:\\s*=\\s*(?:"([^"]*)"|\'([^\']*)\'|([^\\s>]+)))?/i', $this->tags[$this->index][2], $found, PREG_SET_ORDER);
        foreach ($found as $attribute) {
            $this->attributes[strtolower($attribute[1])] = $attribute[2] ?? $attribute[3] ?? $attribute[4] ?? true;
        }
        return true;
    }
    public function get_tag(): string { return strtoupper($this->tags[$this->index][1]); }
    public function get_attribute(string $name) { return $this->attributes[strtolower($name)] ?? null; }
    public function set_attribute(string $name, $value): bool { return true; }
    public function get_updated_html(): string { return $this->html; }
}
function get_posts($args) {
    $found = array_filter($GLOBALS['synthetic_posts'], function ($post) use ($args) {
        return $args['post_type'] === 'any' || in_array($post->post_type, (array) $args['post_type'], true);
    });
    return ($args['fields'] ?? null) === 'ids' ? array_keys($found) : array_values($found);
}
function get_post($id) { return $GLOBALS['synthetic_posts'][$id] ?? null; }
function clean_post_cache($id) {}
function wp_delete_post($id, $force) { unset($GLOBALS['synthetic_posts'][$id]); return true; }
function is_wp_error($value) { return false; }
function clean_term_cache($id, $taxonomy) {}
function add_filter($name, $callback, $priority) { $GLOBALS['synthetic_filters'][$name] = $callback; }
function wp_slash($value) { return $value; }
function wp_insert_post($data, $errors) {
    $data['post_content'] = wp_kses_post($data['post_content']);
    if (isset($GLOBALS['synthetic_filters']['wp_insert_post_data'])) { $data = $GLOBALS['synthetic_filters']['wp_insert_post_data']($data); }
    if (($GLOBALS['synthetic_mutation'] ?? null) === 'promote' && $data['post_name'] === 'categories') { $data['post_status'] = 'publish'; }
    if (($GLOBALS['synthetic_mutation'] ?? null) === 'body' && $data['post_name'] === 'categories') { $data['post_content'] .= ' Changed'; }
    $id = $data['import_id'];
    $GLOBALS['synthetic_posts'][$id] = (object) array_merge(array(
        'ID' => $id, 'post_date' => '2000-01-01 00:00:00', 'post_date_gmt' => '2000-01-01 00:00:00',
        'post_modified' => '2000-01-01 00:00:00', 'post_modified_gmt' => '2000-01-01 00:00:00',
    ), $data);
    return $id;
}
function taxonomy_exists($taxonomy) { return in_array($taxonomy, array('category', 'post_tag'), true); }
function get_object_taxonomies($type, $output) { return $type === 'post' ? array('category', 'post_tag') : array(); }
function wp_set_object_terms($id, $ids, $taxonomy, $append) { $GLOBALS['synthetic_relationships'][$id][$taxonomy] = $ids; return $ids; }
function wp_get_object_terms($id, $taxonomy, $args = array()) {
    $ids = $GLOBALS['synthetic_relationships'][$id][$taxonomy] ?? array();
    if (($args['fields'] ?? null) === 'ids') { return $ids; }
    return array_map(function ($id) use ($taxonomy) {
        $term = $GLOBALS['synthetic_terms'][$id];
        return (object) array('term_id' => $id, 'name' => $term['name'], 'slug' => $term['slug'], 'parent' => 0);
    }, $ids);
}
function get_post_thumbnail_id($id) { return 0; }
class ScratchFakeDb {
    public $prefix = 'wp_';
    public $terms = 'wp_terms';
    public $term_taxonomy = 'wp_term_taxonomy';
    public $options = 'wp_options';
    public $posts = 'wp_posts';
    public function get_col($sql) { return array_keys($GLOBALS['synthetic_terms']); }
    public function delete($table, $where, $format) {
        unset($GLOBALS[$table === $this->terms ? 'synthetic_terms' : 'synthetic_taxonomies'][$where['term_id']]); return 1;
    }
    public function insert($table, $row, $formats) {
        if ($table === $this->terms) {
            if (isset($GLOBALS['synthetic_terms'][$row['term_id']])) { throw new RuntimeException('SYNTHETIC_DUPLICATE_TERM'); }
            $GLOBALS['synthetic_terms'][$row['term_id']] = $row;
        } else { $GLOBALS['synthetic_taxonomies'][$row['term_id']] = $row['taxonomy']; }
        return 1;
    }
    public function update($table, $row, $where, $formats, $where_formats) {
        if ($table !== $this->posts || ! isset($GLOBALS['synthetic_posts'][$where['ID']])) { return false; }
        foreach ($row as $key => $value) { $GLOBALS['synthetic_posts'][$where['ID']]->{$key} = $value; }
        return 1;
    }
    public function get_results($sql, $output) {
        ksort($GLOBALS['synthetic_options']);
        $rows = array();
        foreach ($GLOBALS['synthetic_options'] as $key => $value) { $rows[] = array('option_name' => $key, 'option_value' => $value, 'autoload' => 'off'); }
        return $rows;
    }
}
$wpdb = new ScratchFakeDb();
$input = json_decode(base64_decode($argv[1], true), true, 128, JSON_THROW_ON_ERROR);
$GLOBALS['synthetic_mutation'] = $input['mutation'] ?? '';
$workspace = dirname(__DIR__, 2);
$private = sys_get_temp_dir() . '/synthetic-reader-' . bin2hex(random_bytes(8));
mkdir($private, 0700); mkdir($private . '/content', 0700);
file_put_contents($private . '/scratch-seed.v1.json', $input['seed']);
file_put_contents($private . '/source-snapshot.v1.json', $input['snapshot']);
foreach ($input['bodies'] as $slug => $body) { file_put_contents($private . '/content/' . $slug . '.html', $body); }
$seed = json_decode($input['seed'], true);
putenv('RAOS_SCRATCH_RESTORE_ENVIRONMENT=' . $seed['environment_id']);
putenv('RAOS_SCRATCH_SEED_SHA256=' . hash('sha256', $input['seed']));
try {
    $code = file_get_contents($workspace . '/changes/wordpress-local-preview-v1/scratch-restore-seed.php');
    eval(substr(str_replace('/var/www/raos-scratch-backup', $private, $code), 5));
    $content = json_decode(file_get_contents($private . '/scratch-readback.v1.json'));
    $theme_result = null;
    if (isset($input['theme'])) {
        $theme = $input['theme'];
        mkdir($private . '/theme-restore', 0700);
        mkdir($private . '/wordpress/wp-content/themes', 0700, true);
        foreach (array('preparation', 'baseline-package', 'candidate-package') as $name) {
            file_put_contents($private . '/theme-restore/' . $name . '.v1.json', $theme[$name]);
        }
        file_put_contents($private . '/scratch-restoration-receipt.v1.json', $theme['content-receipt']);
        putenv('RAOS_SCRATCH_THEME_PREPARATION_SHA256=' . hash('sha256', $theme['preparation']));
        $code = file_get_contents($workspace . '/changes/wordpress-local-preview-v1/scratch-theme-restore.php');
        $code = str_replace(array('/var/www/raos-scratch-backup', '/var/www/html/wp-content'),
                            array($private, $private . '/wordpress/wp-content'), $code);
        eval(substr($code, 5));
        $theme_result = json_decode(file_get_contents($private . '/theme-restore/readback.v1.json'));
    }
    echo json_encode(array('synthetic_content' => $content, 'synthetic_theme' => $theme_result), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
} catch (Throwable $error) {
    echo json_encode(array('synthetic_error' => $error->getMessage(), 'synthetic_inserted_count' => count($GLOBALS['synthetic_posts'])));
}
