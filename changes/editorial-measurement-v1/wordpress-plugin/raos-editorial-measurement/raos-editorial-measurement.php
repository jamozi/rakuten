<?php
/**
 * Plugin Name: RAOS Editorial Measurement
 * Description: Consent-gated first-party editorial event collection and aggregate-only reporting.
 * Version: 1.0.0
 * Requires at least: 7.1
 * Requires PHP: 8.1
 * Author: RAOS
 * License: GPL-2.0-or-later
 * Update URI: false
 *
 * @package RAOS_Editorial_Measurement
 */

defined('ABSPATH') || exit;

define('RAOS_EDITORIAL_MEASUREMENT_VERSION', '1.0.0');
define('RAOS_EDITORIAL_MEASUREMENT_FILE', __FILE__);
define(
    'RAOS_EDITORIAL_MEASUREMENT_ALLOWLIST',
    __DIR__ . '/config/measurement-allowlist.v1.json'
);

require_once __DIR__ . '/includes/class-raos-measurement-contract.php';
require_once __DIR__ . '/includes/class-raos-measurement-store.php';

final class RAOS_Editorial_Measurement
{
    const TARGET_ORIGIN = 'https://kurashinoshirube.com';
    const REST_NAMESPACE = 'raos/v1';
    const REST_ROUTE = '/events';

    private static $instance = null;
    private $contract = null;

    public static function instance()
    {
        if (! self::$instance instanceof self) {
            self::$instance = new self();
        }
        return self::$instance;
    }

    private function __construct()
    {
        add_action('init', array('RAOS_Measurement_Store', 'maybe_upgrade'), 0);
        add_action('rest_api_init', array($this, 'register_rest_route'));
        add_action('wp_abilities_api_init', array($this, 'register_ability'));
        add_action(
            RAOS_Measurement_Store::CLEANUP_HOOK,
            array('RAOS_Measurement_Store', 'cleanup')
        );
    }

    public static function activate()
    {
        global $wp_version;
        if (version_compare(PHP_VERSION, '8.1', '<')
            || ! is_string($wp_version)
            || preg_match('/\A7\.1(?:\.|\z)/', $wp_version) !== 1) {
            deactivate_plugins(plugin_basename(__FILE__));
            wp_die(
                esc_html__('RAOS Editorial Measurement requires WordPress 7.1.x and PHP 8.1+.', 'raos-measurement'),
                esc_html__('RAOS measurement activation refused', 'raos-measurement'),
                array('back_link' => true)
            );
        }
        try {
            RAOS_Measurement_Contract::load(
                RAOS_EDITORIAL_MEASUREMENT_ALLOWLIST
            );
        } catch (RuntimeException $error) {
            deactivate_plugins(plugin_basename(__FILE__));
            wp_die(
                esc_html__('The fixed RAOS measurement identity contract is invalid.', 'raos-measurement'),
                esc_html__('RAOS measurement activation refused', 'raos-measurement'),
                array('back_link' => true)
            );
        }
        RAOS_Measurement_Store::install();
    }

    public function register_rest_route()
    {
        register_rest_route(
            self::REST_NAMESPACE,
            self::REST_ROUTE,
            array(
                'methods' => WP_REST_Server::CREATABLE,
                'callback' => array($this, 'collect'),
                'permission_callback' => array($this, 'public_permission'),
            )
        );
    }

    public function public_permission($request)
    {
        if (! $request instanceof WP_REST_Request
            || 'POST' !== strtoupper($request->get_method())
            || ! self::enabled()
            || ! self::runtime_origin_is_exact()) {
            return self::error('raos_measurement_disabled', 404);
        }
        $origin = $request->get_header('origin');
        $fetch_site = $request->get_header('sec-fetch-site');
        $content_type = strtolower((string) $request->get_header('content-type'));
        if (! is_string($origin)
            || ! hash_equals(self::TARGET_ORIGIN, $origin)
            || 'same-origin' !== strtolower((string) $fetch_site)
            || preg_match(
                '/\Aapplication\/json(?:\s*;\s*charset=utf-8)?\z/D',
                $content_type
            ) !== 1) {
            return self::error('raos_measurement_origin_forbidden', 403);
        }
        return true;
    }

    public function collect($request)
    {
        if (! $request instanceof WP_REST_Request) {
            return self::error('raos_measurement_request_invalid', 400);
        }
        $body = $request->get_body();
        if (! is_string($body)
            || strlen($body) < 2
            || strlen($body) > RAOS_Measurement_Contract::MAX_BODY_BYTES) {
            return self::error('raos_measurement_request_invalid', 400);
        }
        $input = json_decode($body, true, 16, JSON_BIGINT_AS_STRING);
        if (! is_array($input)) {
            return self::error('raos_measurement_json_invalid', 400);
        }
        try {
            $event = $this->contract()->validate_event(
                $input,
                self::now_milliseconds()
            );
        } catch (InvalidArgumentException $error) {
            return self::error(strtolower($error->getMessage()), 400);
        } catch (RuntimeException $error) {
            return self::error('raos_measurement_contract_unavailable', 503);
        }
        $result = RAOS_Measurement_Store::record($event);
        if (is_wp_error($result)) {
            return $result;
        }
        $response = new WP_REST_Response(
            array(
                'schema' => 'RAOSMeasurementAcceptanceV1',
                'event_id' => $event['event_id'],
                'disposition' => $result['disposition'],
            ),
            'ACCEPTED' === $result['disposition'] ? 202 : 200
        );
        $response->header('Cache-Control', 'no-store, max-age=0');
        $response->header('Vary', 'Origin');
        return $response;
    }

    public function register_ability()
    {
        if (! function_exists('wp_register_ability')) {
            return;
        }
        wp_register_ability(
            'raos-measurement/aggregate-report',
            array(
                'label' => 'RAOS measurement aggregate report',
                'description' => 'Read aggregate event counts only. Raw events, sessions, IP addresses, user agents, and secrets are never returned.',
                'category' => 'raos-codex',
                'input_schema' => array(
                    'type' => 'object',
                    'additionalProperties' => false,
                    'required' => array('start_date', 'end_date'),
                    'properties' => array(
                        'start_date' => array(
                            'type' => 'string',
                            'pattern' => '^\\d{4}-\\d{2}-\\d{2}$',
                        ),
                        'end_date' => array(
                            'type' => 'string',
                            'pattern' => '^\\d{4}-\\d{2}-\\d{2}$',
                        ),
                        'article_id' => array(
                            'type' => 'string',
                            'pattern' => '^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$',
                        ),
                        'event_names' => array(
                            'type' => 'array',
                            'minItems' => 1,
                            'maxItems' => 8,
                            'uniqueItems' => true,
                            'items' => array(
                                'type' => 'string',
                                'enum' => array(
                                    'article_view',
                                    'qualified_decision_engagement',
                                    'affiliate_cta_impression',
                                    'affiliate_click',
                                    'product_card_view',
                                    'comparison_interaction',
                                    'internal_link_click',
                                    'disclosure_view',
                                ),
                            ),
                        ),
                        'page' => array(
                            'type' => 'integer',
                            'minimum' => 1,
                            'maximum' => 100000,
                        ),
                        'per_page' => array(
                            'type' => 'integer',
                            'minimum' => 1,
                            'maximum' => 100,
                        ),
                    ),
                ),
                'output_schema' => array('type' => 'object'),
                'execute_callback' => array($this, 'aggregate_report'),
                'permission_callback' => array($this, 'aggregate_permission'),
                'meta' => array(
                    'public' => false,
                    'annotations' => array(
                        'readOnlyHint' => true,
                        'destructiveHint' => false,
                        'idempotentHint' => true,
                        'openWorldHint' => false,
                    ),
                    'mcp' => array('type' => 'tool'),
                ),
            )
        );
    }

    public function aggregate_permission($input = null)
    {
        unset($input);
        return self::runtime_origin_is_exact()
            && current_user_can('raos_codex_content_read');
    }

    public function aggregate_report($input)
    {
        $input = is_array($input) ? $input : array();
        $normalized = $this->normalize_report_input($input);
        if (is_wp_error($normalized)) {
            return $normalized;
        }
        $rows = RAOS_Measurement_Store::aggregate_report($normalized);
        if (is_wp_error($rows)) {
            return $rows;
        }
        return array(
            'schema' => 'RAOSMeasurementAggregateReportV1',
            'measurement_enabled' => self::enabled(),
            'raw_events_exposed' => false,
            'retention' => array(
                'raw_days' => RAOS_Measurement_Store::RAW_RETENTION_DAYS,
                'daily_aggregate_months' => RAOS_Measurement_Store::AGGREGATE_RETENTION_MONTHS,
            ),
            'generated_at_gmt' => self::now_milliseconds(),
            'period' => array(
                'start_date' => $normalized['start_date'],
                'end_date' => $normalized['end_date'],
            ),
            'page' => $normalized['page'],
            'per_page' => $normalized['per_page'],
            'rows' => $rows,
        );
    }

    public function client_context($article_id)
    {
        try {
            return $this->contract()->client_context($article_id);
        } catch (RuntimeException $error) {
            return null;
        }
    }

    private function normalize_report_input(array $input)
    {
        $allowed = array('start_date', 'end_date', 'article_id', 'event_names', 'page', 'per_page');
        if (array_diff(array_keys($input), $allowed) !== array()
            || ! isset($input['start_date'], $input['end_date'])
            || ! self::date($input['start_date'])
            || ! self::date($input['end_date'])
            || $input['start_date'] > $input['end_date']) {
            return self::error('raos_measurement_report_input_invalid', 400);
        }
        $start = new DateTimeImmutable($input['start_date'], new DateTimeZone('UTC'));
        $end = new DateTimeImmutable($input['end_date'], new DateTimeZone('UTC'));
        if ($start->modify('+400 days') < $end) {
            return self::error('raos_measurement_report_period_too_large', 400);
        }
        $normalized = array(
            'start_date' => $input['start_date'],
            'end_date' => $input['end_date'],
            'page' => isset($input['page']) ? (int) $input['page'] : 1,
            'per_page' => isset($input['per_page']) ? (int) $input['per_page'] : 100,
        );
        if ($normalized['page'] < 1
            || $normalized['page'] > 100000
            || $normalized['per_page'] < 1
            || $normalized['per_page'] > 100) {
            return self::error('raos_measurement_report_input_invalid', 400);
        }
        if (isset($input['article_id'])) {
            $context = $this->client_context($input['article_id']);
            if (! is_array($context)) {
                return self::error('raos_measurement_report_article_invalid', 400);
            }
            $normalized['article_id'] = $input['article_id'];
        }
        if (isset($input['event_names'])) {
            $known = array(
                'article_view',
                'qualified_decision_engagement',
                'affiliate_cta_impression',
                'affiliate_click',
                'product_card_view',
                'comparison_interaction',
                'internal_link_click',
                'disclosure_view',
            );
            if (! is_array($input['event_names'])
                || count($input['event_names']) < 1
                || count($input['event_names']) > 8
                || count(array_unique($input['event_names'])) !== count($input['event_names'])
                || array_diff($input['event_names'], $known) !== array()) {
                return self::error('raos_measurement_report_event_invalid', 400);
            }
            $normalized['event_names'] = array_values($input['event_names']);
        }
        return $normalized;
    }

    private function contract()
    {
        if (! $this->contract instanceof RAOS_Measurement_Contract) {
            $this->contract = RAOS_Measurement_Contract::load(
                RAOS_EDITORIAL_MEASUREMENT_ALLOWLIST
            );
        }
        return $this->contract;
    }

    public static function enabled()
    {
        return defined('RAOS_MEASUREMENT_ENABLED')
            && true === RAOS_MEASUREMENT_ENABLED;
    }

    private static function runtime_origin_is_exact()
    {
        return ! is_multisite()
            && untrailingslashit(home_url()) === self::TARGET_ORIGIN
            && untrailingslashit(site_url()) === self::TARGET_ORIGIN;
    }

    private static function date($value)
    {
        if (! is_string($value)
            || preg_match('/\A\d{4}-\d{2}-\d{2}\z/D', $value) !== 1) {
            return false;
        }
        $date = DateTimeImmutable::createFromFormat(
            '!Y-m-d',
            $value,
            new DateTimeZone('UTC')
        );
        return $date instanceof DateTimeImmutable && $date->format('Y-m-d') === $value;
    }

    private static function now_milliseconds()
    {
        return (new DateTimeImmutable('now', new DateTimeZone('UTC')))
            ->format('Y-m-d\TH:i:s.v\Z');
    }

    private static function error($code, $status)
    {
        return new WP_Error(
            $code,
            'RAOS measurement request refused.',
            array('status' => $status)
        );
    }
}

/** Theme bridge: no credential, destination URL, or visitor identity is returned. */
function raos_editorial_measurement_client_context($article_id)
{
    return RAOS_Editorial_Measurement::instance()->client_context($article_id);
}

/** Theme bridge for the default-off transmission gate. */
function raos_editorial_measurement_enabled()
{
    return RAOS_Editorial_Measurement::enabled();
}

RAOS_Editorial_Measurement::instance();
register_activation_hook(
    __FILE__,
    array('RAOS_Editorial_Measurement', 'activate')
);
register_deactivation_hook(
    __FILE__,
    array('RAOS_Measurement_Store', 'deactivate')
);
