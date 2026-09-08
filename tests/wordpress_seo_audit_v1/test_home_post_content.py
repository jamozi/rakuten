"""Saved home markup is compared as DOM content, never CSS/script substrings."""

import pytest
import base64

from scripts import raos_wordpress_incremental_seo_audit as audit


HOME = '''<div id="ks-magazine" data-release="test-release" style="--km-hero-image:url('data:image/webp;base64,AAAA')">
<header class="km-header"><a href="/">Home</a><form class="km-popover" action="/" method="get" role="search"><label for="km-search-input">Search</label><input id="km-search-input" name="s" type="search" placeholder="Search words" required><button type="submit">Search</button></form></header>
<div class="km-spine" aria-hidden="true"><span>EDITOR'S PICK</span></div>
<section class="km-hero"><h1>Saved home heading</h1><p>Saved body</p><a href="/guides/">Guides</a></section></div>'''


def page(body: str) -> str:
    return '<html><head></head><body><header>Shared header</header><main id="main-content"><div class="entry-content wp-block-post-content">' + body + '</div></main><footer>Shared footer</footer></body></html>'


def test_home_verifies_all_saved_attributes_and_only_closed_spine_typography() -> None:
    rendered = HOME.replace("EDITOR'S PICK", "EDITOR&#8217;S PICK")
    assert len(audit.verify_rendered_home_body(HOME, page(rendered))) == 64


@pytest.mark.parametrize("replacement", [
    HOME.replace('test-release', 'changed-release'),
    HOME.replace('AAAA', 'BBBB'),
    HOME.replace('Saved body', 'Changed body'),
    HOME.replace('/guides/', '/other/'),
    HOME.replace('km-hero', 'hidden-hero'),
    HOME.replace('Saved body', "Editor's body"),
    HOME + HOME,
])
def test_home_rejects_body_identity_style_image_text_link_or_duplicate_changes(replacement: str) -> None:
    with pytest.raises((audit.seo.AuditError, ValueError)):
        audit.verify_rendered_home_body(HOME, page(replacement))


@pytest.mark.parametrize("actual", [
    '<html><head><style>/*' + HOME + '*/</style></head><body><main id="main-content"><h1>Old home</h1></main></body></html>',
    page(HOME).replace('<main id="main-content">', '<main id="main-content"><h1 id="home-hero-title">Old home</h1>'),
    page(HOME).replace('<main id="main-content">', '<main id="wrong-main">'),
    page(HOME).replace('entry-content wp-block-post-content', 'entry-content'),
    page(HOME).replace('</main>', '<hr/></main>'),
    page(HOME + '&nbsp;'),
    page(HOME).replace('<main ', '<main hidden '),
    page(HOME).replace('class="entry-content', 'hidden class="entry-content'),
    page(HOME).replace('class="entry-content', 'style="display:none" class="entry-content'),
])
def test_home_requires_single_normal_post_content_inside_main_without_old_body(actual: str) -> None:
    with pytest.raises((audit.seo.AuditError, ValueError)):
        audit.verify_rendered_home_body(HOME, actual)


def test_home_typography_exception_cannot_change_editorial_text_or_attributes() -> None:
    expected = HOME.replace('Saved body', "Editor's body")
    with pytest.raises((audit.seo.AuditError, ValueError)):
        audit.verify_rendered_home_body(expected, page(expected.replace("Editor's body", 'Editor’s body')))
    with pytest.raises((audit.seo.AuditError, ValueError)):
        audit.verify_rendered_home_body(HOME, page(HOME.replace('aria-hidden="true"', 'aria-hidden="false"')))


@pytest.mark.parametrize("injection", ['<script>alert(1)</script>', '<img src="x" onerror="alert(1)">', '<iframe src="https://example.com"></iframe>'])
def test_home_exact_equality_does_not_accept_active_content(injection: str) -> None:
    body = HOME.replace('Saved body', injection)
    with pytest.raises((audit.seo.AuditError, ValueError)):
        audit.verify_rendered_home_body(body, page(body))


@pytest.mark.parametrize("before,after", [
    ('A <strong>B</strong> C', 'A<strong>B</strong>C'),
    ('<pre>A  B\n C</pre>', '<pre>A B C</pre>'),
])
def test_home_preserves_meaningful_inline_and_preformatted_whitespace(before: str, after: str) -> None:
    expected = HOME.replace('<p>Saved body</p>', before)
    assert len(audit.verify_rendered_home_body(expected, page(expected))) == 64
    with pytest.raises((audit.seo.AuditError, ValueError)):
        audit.verify_rendered_home_body(expected, page(expected.replace(before, after)))


@pytest.mark.parametrize("replacement", ['AA&#11;AA', 'AA&#xB;AA', 'AA&#x0B;AA'])
def test_home_rejects_attribute_references_that_python_drops_but_browser_keeps(replacement: str) -> None:
    with pytest.raises((audit.seo.AuditError, ValueError)):
        audit.verify_rendered_home_body(HOME, page(HOME.replace('AAAA', replacement)))


def frozen_style() -> str:
    # Synthetic RIFF container for parser tests; browser image loading has its
    # own evidence and this fixture never claims to be a decodable photograph.
    encoded = base64.b64encode(b'RIFF\x04\x00\x00\x00WEBP').decode()
    return "--km-hero-image:url('data:image/webp;base64," + encoded + "')"


def test_runtime_accepts_only_the_exact_retained_home_webp_style() -> None:
    style = frozen_style()
    markup = '<div id="ks-magazine" style="' + style + '"><h1>Home</h1></div>'
    parser = audit.runtime.RuntimeMarkup({}, page_url=audit.publication.ORIGIN + '/', preserved_home_style=style)
    parser.feed(markup)
    parser.close()
    with pytest.raises(audit.seo.AuditError):
        audit.runtime.RuntimeMarkup({}).feed(markup)
    with pytest.raises(audit.seo.AuditError):
        audit.runtime.RuntimeMarkup({}, page_url=audit.publication.ORIGIN + '/guides/', preserved_home_style=style)


@pytest.mark.parametrize("change", ['changed', 'missing', 'outside', 'duplicate'])
def test_runtime_retained_home_style_does_not_authorize_other_inline_css(change: str) -> None:
    style = frozen_style()
    markup = '<div id="ks-magazine" style="' + style + '"><h1>Home</h1></div>'
    if change == 'changed':
        markup = markup.replace('--km-hero-image:', '--other:')
    elif change == 'missing':
        markup = '<h1>Home</h1>'
    elif change == 'outside':
        markup = markup.replace('ks-magazine', 'unrelated')
    else:
        markup += markup
    parser = audit.runtime.RuntimeMarkup({}, page_url=audit.publication.ORIGIN + '/', preserved_home_style=style)
    with pytest.raises(audit.seo.AuditError):
        parser.feed(markup)
        parser.close()


@pytest.mark.parametrize("suffix", [
    ';background:url(https://example.com/tracker)',
    ';background:image-set(url(https://example.com/tracker) 1x)',
    ';behavior:track',
    ';background:u\\72l(https://example.com/tracker)',
    ';@import "https://example.com/tracker"',
])
def test_retained_webps_never_enable_external_or_executable_css(suffix: str) -> None:
    with pytest.raises(audit.seo.AuditError):
        audit.runtime.preserved_webp_style(frozen_style() + suffix)


@pytest.mark.parametrize("data", ['AAAA', '%%%%', 'PHN2Zz48L3N2Zz4=', 'UklGRv////9XRUJQ'])
def test_retained_webp_requires_strict_base64_and_matching_riff_size(data: str) -> None:
    with pytest.raises(audit.seo.AuditError):
        audit.runtime.preserved_webp_style("--km-hero-image:url('data:image/webp;base64," + data + "')")
