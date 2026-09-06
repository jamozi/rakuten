<?php
require __DIR__.'/wp.php';
require __DIR__.'/store-double.php';
require dirname(__DIR__,2).'/changes/reader-measurement-v1/wordpress-plugin/raos-reader-measurement/includes/reader-measurement-maintenance.php';
expect(!class_exists('RAOS_Reader_Measurement',false),'inactive plugin never bootstrapped');
expect(!class_exists('RAOS_Reader_Store',false),'no intake storage class loaded');
expect(!function_exists('raos_reader_measurement_enabled'),'no collection facade');
expect(empty($GLOBALS['routes']),'no endpoints');
$GLOBALS['options'][RAOS_Reader_Maintenance::DB_OPTION]='1.0.0';
RAOS_Reader_Maintenance::schedule();
expect(raos_reader_measurement_cleanup(),'theme-only cleanup works');
expect(raos_reader_measurement_cleanup_status()['healthy'],'theme-only cleanup observable');
echo "maintenance-only behavior OK\n";
