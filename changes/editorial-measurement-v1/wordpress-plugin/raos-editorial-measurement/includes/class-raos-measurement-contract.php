<?php
/**
 * Closed public-event contract and generated editorial identity allowlist.
 *
 * This file deliberately has no WordPress dependency so the validation boundary
 * can be exercised without booting a site.
 *
 * @package RAOS_Editorial_Measurement
 */

defined('ABSPATH') || exit;

final class RAOS_Measurement_Contract
{
    const SCHEMA_VERSION = '1.0';
    const MAX_BODY_BYTES = 4096;

    private $articles;

    private function __construct(array $articles)
    {
        $this->articles = $articles;
    }

    /** Load only an owner-generated, closed allowlist. */
    public static function load($path)
    {
        if (! is_string($path)
            || is_link($path)
            || ! is_file($path)
            || ! is_readable($path)) {
            throw new RuntimeException('RAOS_MEASUREMENT_ALLOWLIST_UNAVAILABLE');
        }
        $raw = file_get_contents($path);
        if (! is_string($raw) || strlen($raw) < 2 || strlen($raw) > 1048576) {
            throw new RuntimeException('RAOS_MEASUREMENT_ALLOWLIST_INVALID');
        }
        $document = json_decode($raw, true, 64, JSON_BIGINT_AS_STRING);
        if (! is_array($document)
            || ! self::has_exact_keys(
                $document,
                array(
                    'schema',
                    'version',
                    'source',
                    'site_id',
                    'target_origin',
                    'events',
                    'articles',
                )
            )
            || 'RAOS_EDITORIAL_MEASUREMENT_ALLOWLIST_V1' !== $document['schema']
            || '1.0.0' !== $document['version']
            || ! self::safe_token($document['site_id'], 64)
            || 'https://kurashinoshirube.com' !== $document['target_origin']
            || ! is_array($document['source'])
            || ! self::has_exact_keys(
                $document['source'],
                array('path', 'schema', 'version', 'sha256')
            )
            || 'changes/editorial-portfolio-v3/editorial-portfolio.v3.json'
                !== $document['source']['path']
            || 'RAOS_EDITORIAL_PORTFOLIO_V3' !== $document['source']['schema']
            || '3.0.0' !== $document['source']['version']
            || ! is_string($document['source']['sha256'])
            || preg_match('/\A[0-9a-f]{64}\z/D', $document['source']['sha256']) !== 1
            || ! is_array($document['events'])
            || ! is_array($document['articles'])) {
            throw new RuntimeException('RAOS_MEASUREMENT_ALLOWLIST_INVALID');
        }
        $expected_events = array_keys(self::event_definitions());
        $events = array_values($document['events']);
        sort($expected_events, SORT_STRING);
        sort($events, SORT_STRING);
        if ($events !== $expected_events) {
            throw new RuntimeException('RAOS_MEASUREMENT_ALLOWLIST_INVALID');
        }
        $articles = array();
        $article_codes = array();
        $snapshot_ids = array();
        $cta_ids = array();
        foreach ($document['articles'] as $article) {
            if (! is_array($article)
                || ! self::has_exact_keys(
                    $article,
                    array(
                        'article_id',
                        'article_code',
                        'snapshot_id',
                        'category_id',
                        'related_article_ids',
                        'cta_bindings',
                    )
                )
                || ! self::safe_token($article['article_id'], 96)
                || ! self::safe_token($article['article_code'], 16)
                || ! self::safe_token($article['snapshot_id'], 96)
                || ! self::safe_token($article['category_id'], 32)
                || ! is_array($article['related_article_ids'])
                || ! is_array($article['cta_bindings'])) {
                throw new RuntimeException('RAOS_MEASUREMENT_ALLOWLIST_INVALID');
            }
            $article_id = $article['article_id'];
            if (isset($articles[$article_id])
                || isset($article_codes[$article['article_code']])
                || isset($snapshot_ids[$article['snapshot_id']])) {
                throw new RuntimeException('RAOS_MEASUREMENT_ALLOWLIST_INVALID');
            }
            $article_codes[$article['article_code']] = true;
            $snapshot_ids[$article['snapshot_id']] = true;
            $related = array();
            foreach ($article['related_article_ids'] as $related_id) {
                if (! self::safe_token($related_id, 96) || isset($related[$related_id])) {
                    throw new RuntimeException('RAOS_MEASUREMENT_ALLOWLIST_INVALID');
                }
                $related[$related_id] = true;
            }
            $bindings = array();
            foreach ($article['cta_bindings'] as $binding) {
                if (! is_array($binding)
                    || ! self::has_exact_keys(
                        $binding,
                        array('product_id', 'cta_id', 'offer_id', 'placement')
                    )
                    || ! self::safe_token($binding['product_id'], 96)
                    || ! self::safe_token($binding['cta_id'], 96)
                    || ! self::safe_token($binding['offer_id'], 96)
                    || ! in_array(
                        $binding['placement'],
                        array('product_card', 'final_summary'),
                        true
                    )) {
                    throw new RuntimeException('RAOS_MEASUREMENT_ALLOWLIST_INVALID');
                }
                $key = self::binding_key(
                    $binding['product_id'],
                    $binding['placement']
                );
                if (isset($bindings[$key]) || isset($cta_ids[$binding['cta_id']])) {
                    throw new RuntimeException('RAOS_MEASUREMENT_ALLOWLIST_INVALID');
                }
                $bindings[$key] = $binding;
                $cta_ids[$binding['cta_id']] = true;
            }
            $articles[$article_id] = array(
                'article_id' => $article_id,
                'article_code' => $article['article_code'],
                'snapshot_id' => $article['snapshot_id'],
                'category_id' => $article['category_id'],
                'related_article_ids' => $related,
                'cta_bindings' => $bindings,
            );
        }
        if (10 !== count($articles)) {
            throw new RuntimeException('RAOS_MEASUREMENT_ALLOWLIST_INVALID');
        }
        foreach ($articles as $article) {
            foreach (array_keys($article['related_article_ids']) as $related_id) {
                if (! isset($articles[$related_id]) || $related_id === $article['article_id']) {
                    throw new RuntimeException('RAOS_MEASUREMENT_ALLOWLIST_INVALID');
                }
            }
        }
        return new self($articles);
    }

    /** Return the secret-free client projection for one exact public article. */
    public function client_context($article_id)
    {
        if (! is_string($article_id) || ! isset($this->articles[$article_id])) {
            return null;
        }
        $article = $this->articles[$article_id];
        return array(
            'articleId' => $article['article_id'],
            'articleCode' => $article['article_code'],
            'snapshotId' => $article['snapshot_id'],
            'categoryId' => $article['category_id'],
            'relatedArticleIds' => array_keys($article['related_article_ids']),
            'ctaBindings' => array_values($article['cta_bindings']),
        );
    }

    /** Validate and normalize one event with exact per-event keys. */
    public function validate_event($event, $received_at)
    {
        if (! is_array($event)
            || ! self::has_exact_keys(
                $event,
                array(
                    'schema_version',
                    'event_id',
                    'event_name',
                    'occurred_at',
                    'anonymous_session_id',
                    'article_id',
                    'snapshot_id',
                    'dimensions',
                )
            )
            || self::SCHEMA_VERSION !== $event['schema_version']
            || ! self::uuid7($event['event_id'])
            || ! self::uuid7($event['anonymous_session_id'])
            || ! is_string($event['event_name'])
            || ! isset(self::event_definitions()[$event['event_name']])
            || ! self::rfc3339_milliseconds($event['occurred_at'])
            || ! self::rfc3339_milliseconds($received_at)
            || ! self::safe_token($event['article_id'], 96)
            || ! self::safe_token($event['snapshot_id'], 96)
            || ! is_array($event['dimensions'])) {
            throw new InvalidArgumentException('RAOS_MEASUREMENT_EVENT_SCHEMA_INVALID');
        }
        $occurred = strtotime($event['occurred_at']);
        $received = strtotime($received_at);
        if (false === $occurred
            || false === $received
            || $occurred > $received + 300
            || $occurred < $received - 86400) {
            throw new InvalidArgumentException('RAOS_MEASUREMENT_EVENT_TIME_INVALID');
        }
        $article = $this->articles[$event['article_id']] ?? null;
        if (! is_array($article)
            || ! hash_equals($article['snapshot_id'], $event['snapshot_id'])) {
            throw new InvalidArgumentException('RAOS_MEASUREMENT_EVENT_IDENTITY_INVALID');
        }
        $name = $event['event_name'];
        $definition = self::event_definitions()[$name];
        if (! self::has_exact_keys($event['dimensions'], $definition)) {
            throw new InvalidArgumentException('RAOS_MEASUREMENT_EVENT_DIMENSIONS_INVALID');
        }
        $dimensions = $this->validate_dimensions(
            $name,
            $event['dimensions'],
            $article
        );
        return array(
            'schema_version' => self::SCHEMA_VERSION,
            'event_id' => strtolower($event['event_id']),
            'event_name' => $name,
            'occurred_at' => $event['occurred_at'],
            'received_at' => $received_at,
            'anonymous_session_id' => strtolower($event['anonymous_session_id']),
            'article_id' => $article['article_id'],
            'snapshot_id' => $article['snapshot_id'],
            'dimensions' => $dimensions,
        );
    }

    private function validate_dimensions($name, array $dimensions, array $article)
    {
        foreach ($dimensions as $key => $value) {
            if ('visibility_threshold' === $key) {
                if (! is_float($value) && ! is_int($value)) {
                    throw new InvalidArgumentException('RAOS_MEASUREMENT_EVENT_VALUE_INVALID');
                }
                continue;
            }
            if (! is_string($value)
                || ! self::safe_token($value, 96)
                || self::looks_sensitive($value)) {
                throw new InvalidArgumentException('RAOS_MEASUREMENT_EVENT_VALUE_INVALID');
            }
        }
        if ('article_view' === $name) {
            if ($dimensions['category_id'] !== $article['category_id']
                || ! in_array(
                    $dimensions['referrer_class'],
                    array('direct', 'search', 'social', 'internal', 'other'),
                    true
                )
                || 'GRANTED' !== $dimensions['consent_state']) {
                throw new InvalidArgumentException('RAOS_MEASUREMENT_EVENT_VALUE_INVALID');
            }
        } elseif ('qualified_decision_engagement' === $name) {
            if (! in_array(
                $dimensions['component_type'],
                array('comparison_table', 'product_card'),
                true
            ) || ! in_array(
                $dimensions['engagement_kind'],
                array('view_50_percent', 'focus', 'horizontal_scroll'),
                true
            )) {
                throw new InvalidArgumentException('RAOS_MEASUREMENT_EVENT_VALUE_INVALID');
            }
        } elseif (in_array(
            $name,
            array('affiliate_cta_impression', 'affiliate_click'),
            true
        )) {
            $this->validate_cta_dimensions($dimensions, $article);
            if ('affiliate_cta_impression' === $name
                && 0.5 !== $dimensions['visibility_threshold']) {
                throw new InvalidArgumentException('RAOS_MEASUREMENT_EVENT_VALUE_INVALID');
            }
            if ('affiliate_click' === $name
                && (! in_array(
                    $dimensions['beacon_transport'],
                    array('sendBeacon', 'fetch_keepalive'),
                    true
                ) || 'GRANTED' !== $dimensions['consent_state'])) {
                throw new InvalidArgumentException('RAOS_MEASUREMENT_EVENT_VALUE_INVALID');
            }
        } elseif ('product_card_view' === $name) {
            $this->validate_cta_dimensions($dimensions, $article);
        } elseif ('comparison_interaction' === $name) {
            if (! in_array(
                $dimensions['interaction'],
                array('focus', 'horizontal_scroll'),
                true
            ) || 'comparison_table' !== $dimensions['axis_code']) {
                throw new InvalidArgumentException('RAOS_MEASUREMENT_EVENT_VALUE_INVALID');
            }
        } elseif ('internal_link_click' === $name) {
            if (! isset($article['related_article_ids'][$dimensions['to_article_id']])
                || ! in_array(
                    $dimensions['placement'],
                    array('article_body', 'related_navigation', 'home_cluster'),
                    true
                )) {
                throw new InvalidArgumentException('RAOS_MEASUREMENT_EVENT_VALUE_INVALID');
            }
        } elseif ('disclosure_view' === $name) {
            if ('privacy-2026-08-30' !== $dimensions['disclosure_version']) {
                throw new InvalidArgumentException('RAOS_MEASUREMENT_EVENT_VALUE_INVALID');
            }
        }
        return $dimensions;
    }

    private function validate_cta_dimensions(array $dimensions, array $article)
    {
        $key = self::binding_key(
            $dimensions['product_id'],
            $dimensions['placement']
        );
        $binding = $article['cta_bindings'][$key] ?? null;
        if (! is_array($binding)
            || ! hash_equals($binding['cta_id'], $dimensions['cta_id'])
            || ! hash_equals($binding['offer_id'], $dimensions['offer_id'])) {
            throw new InvalidArgumentException('RAOS_MEASUREMENT_EVENT_IDENTITY_INVALID');
        }
    }

    private static function event_definitions()
    {
        return array(
            'article_view' => array('category_id', 'referrer_class', 'consent_state'),
            'qualified_decision_engagement' => array('component_type', 'engagement_kind'),
            'affiliate_cta_impression' => array(
                'product_id',
                'cta_id',
                'offer_id',
                'placement',
                'visibility_threshold',
            ),
            'affiliate_click' => array(
                'product_id',
                'cta_id',
                'offer_id',
                'placement',
                'beacon_transport',
                'consent_state',
            ),
            'product_card_view' => array('product_id', 'cta_id', 'offer_id', 'placement'),
            'comparison_interaction' => array('interaction', 'axis_code'),
            'internal_link_click' => array('to_article_id', 'placement'),
            'disclosure_view' => array('disclosure_version'),
        );
    }

    private static function binding_key($product_id, $placement)
    {
        return (string) $product_id . "\n" . (string) $placement;
    }

    private static function has_exact_keys($value, array $expected)
    {
        if (! is_array($value)) {
            return false;
        }
        $actual = array_keys($value);
        sort($actual, SORT_STRING);
        sort($expected, SORT_STRING);
        return $actual === $expected;
    }

    private static function uuid7($value)
    {
        return is_string($value)
            && preg_match(
                '/\A[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/D',
                $value
            ) === 1;
    }

    private static function rfc3339_milliseconds($value)
    {
        if (! is_string($value)
            || preg_match(
                '/\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\z/D',
                $value
            ) !== 1) {
            return false;
        }
        $date = DateTimeImmutable::createFromFormat(
            '!Y-m-d\TH:i:s.v\Z',
            $value,
            new DateTimeZone('UTC')
        );
        return $date instanceof DateTimeImmutable
            && $date->format('Y-m-d\TH:i:s.v\Z') === $value;
    }

    private static function safe_token($value, $max_length)
    {
        return is_string($value)
            && strlen($value) >= 1
            && strlen($value) <= $max_length
            && preg_match('/\A[A-Za-z0-9][A-Za-z0-9._-]*\z/D', $value) === 1;
    }

    private static function looks_sensitive($value)
    {
        return preg_match(
            '/(?:@|\?|#|\/\/|(?:api[_-]?key|password|secret|token)=|mozilla\/|\A(?:https?|mailto|tel|javascript|data):)/i',
            $value
        ) === 1;
    }
}
