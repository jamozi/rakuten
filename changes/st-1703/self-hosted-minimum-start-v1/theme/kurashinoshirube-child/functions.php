<?php
/** Local-only presentation wiring. No remote requests or write capability. */

add_action('wp_enqueue_scripts', static function (): void {
    $theme = wp_get_theme();
    wp_enqueue_style(
        'kurashinoshirube-editorial',
        get_stylesheet_directory_uri() . '/assets/theme.css',
        array(),
        $theme->get('Version')
    );
    wp_enqueue_script(
        'kurashinoshirube-editorial',
        get_stylesheet_directory_uri() . '/assets/theme.js',
        array(),
        $theme->get('Version'),
        array('in_footer' => true, 'strategy' => 'defer')
    );
});
