<?php
/** Functional harness for the DB-backed site-wide measurement rate budget. */

define('ABSPATH', __DIR__ . '/');
define('ARRAY_A', 'ARRAY_A');

final class WP_Error
{
    private $code;
    private $data;

    public function __construct($code, $message = '', $data = array())
    {
        unset($message);
        $this->code = $code;
        $this->data = $data;
    }

    public function get_error_code()
    {
        return $this->code;
    }

    public function get_error_data()
    {
        return $this->data;
    }
}

function is_wp_error($value)
{
    return $value instanceof WP_Error;
}

final class RAOS_Fake_Prepared_Query
{
    public $sql;
    public $arguments;

    public function __construct($sql, array $arguments)
    {
        $this->sql = $sql;
        $this->arguments = $arguments;
    }
}

final class RAOS_Fake_Wpdb
{
    public $prefix = 'wp_';
    private $rate_rows = array();
    private $transaction_snapshot = null;
    private $fail_kind = null;

    public function prepare($sql, ...$arguments)
    {
        if (1 === count($arguments) && is_array($arguments[0])) {
            $arguments = $arguments[0];
        }
        return new RAOS_Fake_Prepared_Query($sql, $arguments);
    }

    public function query($query)
    {
        if (is_string($query)) {
            if ('START TRANSACTION' === $query) {
                if (null !== $this->transaction_snapshot) {
                    return false;
                }
                $this->transaction_snapshot = $this->rate_rows;
                return 0;
            }
            if ('COMMIT' === $query) {
                if (null === $this->transaction_snapshot) {
                    return false;
                }
                $this->transaction_snapshot = null;
                return 0;
            }
            if ('ROLLBACK' === $query) {
                if (null === $this->transaction_snapshot) {
                    return false;
                }
                $this->rate_rows = $this->transaction_snapshot;
                $this->transaction_snapshot = null;
                return 0;
            }
            return false;
        }
        if (! $query instanceof RAOS_Fake_Prepared_Query) {
            return false;
        }
        if (str_starts_with($query->sql, 'INSERT INTO')) {
            if ($this->consume_failure('insert')) {
                return false;
            }
            return $this->insert_rate_row($query->arguments);
        }
        if (str_starts_with($query->sql, 'UPDATE ')) {
            if ($this->consume_failure('update')) {
                return false;
            }
            return $this->update_rate_row($query);
        }
        return false;
    }

    public function get_results($query, $format)
    {
        if ($format !== ARRAY_A
            || ! $query instanceof RAOS_Fake_Prepared_Query
            || ! str_contains($query->sql, 'FOR UPDATE')) {
            return null;
        }
        if ($this->consume_failure('select')) {
            return null;
        }
        $rows = array();
        foreach ($query->arguments as $key) {
            if (isset($this->rate_rows[$key])) {
                $rows[] = $this->rate_rows[$key];
            }
        }
        usort(
            $rows,
            static fn($left, $right) => strcmp($left['bucket_key'], $right['bucket_key'])
        );
        return $rows;
    }

    public function fail_once($kind)
    {
        $this->fail_kind = $kind;
    }

    public function bucket($key)
    {
        return $this->rate_rows[$key] ?? null;
    }

    public function seed_short($tokens_milli, $refilled_at)
    {
        $this->rate_rows['site-short-v1'] = array(
            'bucket_key' => 'site-short-v1',
            'tokens_milli' => $tokens_milli,
            'refilled_at_gmt' => $refilled_at,
            'accepted_count' => 0,
            'expires_at_gmt' => '2026-09-03 00:00:00.000',
        );
    }

    public function seed_daily($date, $accepted_count)
    {
        $key = 'site-day-v1:' . str_replace('-', '', $date);
        $this->rate_rows[$key] = array(
            'bucket_key' => $key,
            'tokens_milli' => 0,
            'refilled_at_gmt' => $date . ' 00:00:00.000',
            'accepted_count' => $accepted_count,
            'expires_at_gmt' => '2026-09-03 00:00:00.000',
        );
    }

    private function consume_failure($kind)
    {
        if ($this->fail_kind !== $kind) {
            return false;
        }
        $this->fail_kind = null;
        return true;
    }

    private function insert_rate_row(array $arguments)
    {
        $key = $arguments[0];
        if (isset($this->rate_rows[$key])) {
            return 0;
        }
        if ('site-short-v1' === $key) {
            $this->rate_rows[$key] = array(
                'bucket_key' => $key,
                'tokens_milli' => (int) $arguments[1],
                'refilled_at_gmt' => $arguments[2],
                'accepted_count' => 0,
                'expires_at_gmt' => $arguments[3],
            );
        } else {
            $this->rate_rows[$key] = array(
                'bucket_key' => $key,
                'tokens_milli' => 0,
                'refilled_at_gmt' => $arguments[1],
                'accepted_count' => 0,
                'expires_at_gmt' => $arguments[2],
            );
        }
        return 1;
    }

    private function update_rate_row(RAOS_Fake_Prepared_Query $query)
    {
        if (str_contains($query->sql, 'accepted_count = accepted_count + 1')) {
            [$now, $expiry, $key, $limit] = $query->arguments;
            if (! isset($this->rate_rows[$key])
                || $this->rate_rows[$key]['accepted_count'] >= (int) $limit) {
                return 0;
            }
            $this->rate_rows[$key]['accepted_count'] += 1;
            $this->rate_rows[$key]['refilled_at_gmt'] = $now;
            $this->rate_rows[$key]['expires_at_gmt'] = $expiry;
            return 1;
        }
        [$tokens, $now, $expiry, $key] = $query->arguments;
        if (! isset($this->rate_rows[$key])) {
            return 0;
        }
        $this->rate_rows[$key]['tokens_milli'] = (int) $tokens;
        $this->rate_rows[$key]['refilled_at_gmt'] = $now;
        $this->rate_rows[$key]['expires_at_gmt'] = $expiry;
        return 1;
    }
}

function raos_expect($condition, $message)
{
    if (! $condition) {
        fwrite(STDERR, $message . PHP_EOL);
        exit(1);
    }
}

require dirname(__DIR__, 2)
    . '/changes/editorial-measurement-v1/wordpress-plugin/'
    . 'raos-editorial-measurement/includes/class-raos-measurement-store.php';

$reserve = new ReflectionMethod(RAOS_Measurement_Store::class, 'reserve_site_capacity');
$reserve->setAccessible(true);

function raos_reserve(RAOS_Fake_Wpdb $database, ReflectionMethod $reserve, $time)
{
    $GLOBALS['wpdb'] = $database;
    raos_expect(false !== $database->query('START TRANSACTION'), 'transaction did not start');
    $result = $reserve->invoke(null, $time);
    if (is_wp_error($result)) {
        if ('raos_measurement_rate_limited' === $result->get_error_code()) {
            raos_expect(false !== $database->query('COMMIT'), 'rate state did not commit');
        } else {
            raos_expect(false !== $database->query('ROLLBACK'), 'failed reservation did not roll back');
        }
    } else {
        raos_expect(false !== $database->query('COMMIT'), 'reservation did not commit');
    }
    return $result;
}

// A new anonymous session for every event still consumes one shared bucket.
$database = new RAOS_Fake_Wpdb();
$rotating_sessions = array();
$instant = '2026-08-30T00:00:00.000Z';
for ($index = 0; $index < RAOS_Measurement_Store::SITE_SHORT_BUCKET_CAPACITY; $index += 1) {
    $rotating_sessions[] = hash('sha256', 'anonymous-session-' . $index);
    raos_expect(
        true === raos_reserve($database, $reserve, $instant),
        'shared capacity refused an in-budget event'
    );
}
raos_expect(
    count(array_unique($rotating_sessions)) === RAOS_Measurement_Store::SITE_SHORT_BUCKET_CAPACITY,
    'the rotating-session fixture did not rotate identities'
);
$flooded = raos_reserve($database, $reserve, $instant);
raos_expect(
    $flooded instanceof WP_Error
        && 'raos_measurement_rate_limited' === $flooded->get_error_code()
        && 429 === $flooded->get_error_data()['status'],
    'session rotation bypassed the site-wide bucket'
);
raos_expect(
    0 === $database->bucket('site-short-v1')['tokens_milli'],
    'exhausted short bucket retained capacity'
);

// Twenty tokens/second means 50 ms restores exactly one token, then stops again.
raos_expect(
    true === raos_reserve($database, $reserve, '2026-08-30T00:00:00.050Z'),
    'short bucket did not refill after its bounded interval'
);
$same_moment = raos_reserve($database, $reserve, '2026-08-30T00:00:00.050Z');
raos_expect(
    $same_moment instanceof WP_Error
        && 'raos_measurement_rate_limited' === $same_moment->get_error_code(),
    'refill minted more tokens than the elapsed interval permits'
);

// The daily key rotates only at a UTC day boundary; UUID rotation cannot reset it.
$database = new RAOS_Fake_Wpdb();
$database->seed_short(
    RAOS_Measurement_Store::SITE_SHORT_BUCKET_CAPACITY
        * RAOS_Measurement_Store::TOKEN_SCALE,
    '2026-08-30 23:59:59.000'
);
$database->seed_daily('2026-08-30', RAOS_Measurement_Store::SITE_DAILY_CAP);
$daily_full = raos_reserve($database, $reserve, '2026-08-30T23:59:59.000Z');
raos_expect(
    $daily_full instanceof WP_Error
        && 'raos_measurement_rate_limited' === $daily_full->get_error_code(),
    'daily cap was bypassed before the UTC boundary'
);
raos_expect(
    true === raos_reserve($database, $reserve, '2026-08-31T00:00:00.000Z'),
    'daily cap did not reset at the UTC day boundary'
);
raos_expect(
    1 === $database->bucket('site-day-v1:20260831')['accepted_count'],
    'new UTC daily bucket did not record the first reservation'
);

// Every storage failure fails closed and rolls back partially created state.
foreach (array('insert', 'select', 'update') as $failure) {
    $database = new RAOS_Fake_Wpdb();
    $database->fail_once($failure);
    $failed = raos_reserve($database, $reserve, $instant);
    raos_expect(
        $failed instanceof WP_Error
            && 'raos_measurement_storage_unavailable' === $failed->get_error_code()
            && 503 === $failed->get_error_data()['status'],
        'storage failure did not fail closed: ' . $failure
    );
    raos_expect(
        null === $database->bucket('site-short-v1'),
        'storage failure retained a partial bucket: ' . $failure
    );
}

fwrite(STDOUT, "RAOS_MEASUREMENT_STORE_RATE_OK\n");
