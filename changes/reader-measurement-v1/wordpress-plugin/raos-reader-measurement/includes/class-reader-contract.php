<?php
/** Pure closed validation; no WordPress state, visitor identity or network. */
final class RAOS_Reader_Contract
{
    const ORIGIN = 'https://kurashinoshirube.com';
    const MAX_BODY_BYTES = 1024;
    const EVENTS = array(
        'guide_navigation' => array('event_name', 'article_id', 'target_article_id', 'journey_stage'),
        'decision_check_open' => array('event_name', 'article_id', 'panel_id'),
        'official_reference_open' => array('event_name', 'article_id', 'source_ref'),
    );
    private $articles = array();

    public static function exact_keys($value, array $keys): bool
    {
        if (!is_array($value)) { return false; }
        $actual = array_keys($value);
        sort($actual, SORT_STRING); sort($keys, SORT_STRING);
        return $actual === $keys;
    }

    public static function digest($value): bool
    {
        return is_string($value) && preg_match('/\A[0-9a-f]{64}\z/D', $value) === 1;
    }

    private static function token($value): bool
    {
        return is_string($value) && preg_match('/\A[A-Za-z0-9][A-Za-z0-9._-]{0,95}\z/D', $value) === 1;
    }

    public static function load(string $path): self
    {
        if (is_link($path) || !is_file($path) || !is_readable($path) || filesize($path) > 1048576) {
            throw new RuntimeException('READER_CONTRACT_UNAVAILABLE');
        }
        $document = json_decode(file_get_contents($path), true, 32);
        return new self($document);
    }

    public function __construct($document)
    {
        if (!self::exact_keys($document, array('schema','version','target_origin','events','source_hashes','articles'))
            || $document['schema'] !== 'RAOS_READER_MEASUREMENT_ALLOWLIST_V1'
            || $document['version'] !== '1.0.0' || $document['target_origin'] !== self::ORIGIN
            || $document['events'] !== array_keys(self::EVENTS)
            || !is_array($document['source_hashes']) || count($document['source_hashes']) < 10
            || !is_array($document['articles']) || count($document['articles']) !== 10) {
            throw new RuntimeException('READER_CONTRACT_INVALID');
        }
        foreach ($document['source_hashes'] as $path => $hash) {
            if (!is_string($path) || preg_match('~\A(?:changes|python)/[A-Za-z0-9/_.-]+\z~D', $path) !== 1
                || strpos($path, '..') !== false || !self::digest($hash)) {
                throw new RuntimeException('READER_CONTRACT_INVALID');
            }
        }
        $slugs = array();
        foreach ($document['articles'] as $row) {
            if (!self::exact_keys($row, array('article_id','slug','navigation','panels','references'))
                || !self::token($row['article_id']) || !self::token($row['slug'])
                || strpos($row['slug'], 'local-') === 0 || isset($slugs[$row['slug']])
                || isset($this->articles[$row['article_id']])
                || !is_array($row['navigation']) || !is_array($row['panels']) || !is_array($row['references'])) {
                throw new RuntimeException('READER_CONTRACT_INVALID');
            }
            $slugs[$row['slug']] = true;
            $seen = array();
            foreach ($row['panels'] as $panel) {
                if (!self::exact_keys($panel, array('panel_id','kind'))
                    || !in_array($panel, array(
                        array('panel_id'=>'reader-axes','kind'=>'anchor'),
                        array('panel_id'=>'reader-purchase-checks','kind'=>'anchor'),
                        array('panel_id'=>'reader-evidence','kind'=>'details'),
                    ), true) || isset($seen[$panel['panel_id']])) {
                    // JSON key order is not part of object identity.
                    $expected = array('reader-axes'=>'anchor','reader-purchase-checks'=>'anchor','reader-evidence'=>'details');
                    if (!self::exact_keys($panel, array('panel_id','kind')) || ($expected[$panel['panel_id']] ?? null) !== $panel['kind'] || isset($seen[$panel['panel_id']])) {
                        throw new RuntimeException('READER_CONTRACT_INVALID');
                    }
                }
                $seen[$panel['panel_id']] = true;
            }
            $seen = array(); $urls = array();
            foreach ($row['references'] as $ref) {
                if (!self::exact_keys($ref, array('source_ref','url')) || !self::token($ref['source_ref'])
                    || strpos($ref['source_ref'],'SRC-') !== 0 || isset($seen[$ref['source_ref']])
                    || !is_string($ref['url']) || strlen($ref['url']) > 2048
                    || !filter_var($ref['url'], FILTER_VALIDATE_URL) || strpos($ref['url'],'https://') !== 0
                    || parse_url($ref['url'],PHP_URL_USER) !== null || parse_url($ref['url'],PHP_URL_PASS) !== null
                    || isset($urls[$ref['url']])) {
                    throw new RuntimeException('READER_CONTRACT_INVALID');
                }
                $seen[$ref['source_ref']] = true; $urls[$ref['url']] = true;
            }
            $this->articles[$row['article_id']] = $row;
        }
        foreach ($this->articles as $row) {
            $seen = array();
            foreach ($row['navigation'] as $nav) {
                if (!self::exact_keys($nav,array('target_article_id','journey_stage','path'))
                    || !self::token($nav['target_article_id']) || !isset($this->articles[$nav['target_article_id']])
                    || $nav['target_article_id'] === $row['article_id']
                    || !in_array($nav['journey_stage'],array('discover','learn','compare','verify','buy'),true)
                    || $nav['path'] !== '/' . $this->articles[$nav['target_article_id']]['slug'] . '/'
                    || isset($seen[$nav['target_article_id'].':'.$nav['journey_stage']])) {
                    throw new RuntimeException('READER_CONTRACT_INVALID');
                }
                $seen[$nav['target_article_id'].':'.$nav['journey_stage']] = true;
            }
        }
    }

    public function article($id): ?array
    {
        return is_string($id) ? ($this->articles[$id] ?? null) : null;
    }

    public function articles(): array { return array_values($this->articles); }

    public static function request_allowed($method, array $headers, $contract, $policy): bool
    {
        return $method === 'POST' && self::digest($contract) && self::digest($policy)
            && ($headers['origin'] ?? null) === self::ORIGIN
            && ($headers['sec-fetch-site'] ?? null) === 'same-origin'
            && is_string($headers['content-type'] ?? null)
            && preg_match('~\Aapplication/json(?:;\s*charset=utf-8)?\z~Di', $headers['content-type']) === 1
            && ($headers['x-raos-reader-consent'] ?? null) === 'granted'
            && ($headers['x-raos-reader-contract'] ?? null) === $contract
            && ($headers['x-raos-reader-policy'] ?? null) === $policy;
    }

    public function validate_body($body, DateTimeImmutable $instant): array
    {
        if (!is_string($body) || strlen($body) < 2 || strlen($body) > self::MAX_BODY_BYTES) {
            throw new InvalidArgumentException('READER_EVENT_INVALID');
        }
        $object = json_decode($body);
        if (!$object instanceof stdClass || json_last_error() !== JSON_ERROR_NONE) {
            throw new InvalidArgumentException('READER_EVENT_INVALID');
        }
        // Duplicate JSON member names must not be silently overwritten by json_decode.
        preg_match_all('/("(?:[^"\\\\]|\\\\.)*")\\s*:/s', $body, $matches);
        $keys = array_map(function ($key) { return json_decode($key); }, $matches[1]);
        if (count($keys) !== count(array_unique($keys))) {
            throw new InvalidArgumentException('READER_EVENT_INVALID');
        }
        return $this->validate_event((array)$object, $instant);
    }

    public function validate_event(array $event, DateTimeImmutable $instant): array
    {
        $name = $event['event_name'] ?? null;
        if (!is_string($name) || !isset(self::EVENTS[$name]) || !self::exact_keys($event,self::EVENTS[$name])) {
            throw new InvalidArgumentException('READER_EVENT_INVALID');
        }
        foreach ($event as $value) {
            if (!self::token($value)) { throw new InvalidArgumentException('READER_EVENT_INVALID'); }
        }
        $row = $this->article($event['article_id']);
        if ($row === null) { throw new InvalidArgumentException('READER_EVENT_IDENTITY_INVALID'); }
        $valid = false;
        if ($name === 'guide_navigation') {
            foreach ($row['navigation'] as $nav) {
                if ($nav['target_article_id'] === $event['target_article_id'] && $nav['journey_stage'] === $event['journey_stage']) { $valid = true; }
            }
        } elseif ($name === 'decision_check_open') {
            $valid = in_array($event['panel_id'], array_column($row['panels'], 'panel_id'), true);
        } else {
            $valid = in_array($event['source_ref'], array_column($row['references'], 'source_ref'), true);
        }
        if (!$valid) { throw new InvalidArgumentException('READER_EVENT_IDENTITY_INVALID'); }
        return $event + array('event_date'=>$instant->setTimezone(new DateTimeZone('Asia/Tokyo'))->format('Y-m-d'));
    }
}
