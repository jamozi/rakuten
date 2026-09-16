"""Measured phone scroll-frame widths for the tables that scroll sideways.

A table with a sticky first column is only usable on a phone if the frame shows
the sticky column *and* one whole data column at once. That is a statement about
rendered pixels, so the numbers below were measured, not derived.

How they were measured
----------------------
``node tests/purchase_support/phone_table_frames.mjs`` renders a published body
from ``changes/wordpress-direct-publish-v1/articles/`` in headless Chromium
(playwright, Chromium 152.0.7977.8) inside the real article shell::

    body{margin:0}                       # WordPress global styles for a block theme;
                                         # tests/st1704/test_header_text_resize.py does the same
    theme.css + editorial-v2.css + purchase-support.css
                                         # exactly what inc/purchase-support.php enqueues
                                         # (editorial-v2.css only for comparison/guide/
                                         #  curated_comparison bodies)
    <body class="raos-editorial-v2-page">
      <div class="wp-site-blocks">
        <main class="raos-article-shell">      # padding-inline:1rem at <=48rem
          <article class="raos-article">
            <div class="wp-block-post-content">BODY

and reports ``clientWidth`` of the nearest ancestor with ``overflow-x:auto``.

``.raos-article-shell`` takes 1rem off each side and the scroll container has a
1px border on each side, so an article body's frame is ``viewport - 34``. An
earlier round of this work used 302px for the 320px frame -- it counted the
container border but not the shell padding -- and a table sized to that number
frames no data column at all.

Measured 2026-09-16 on the committed theme:

====== ============ ============ =========================================
width  frame outer  frame inner  container
====== ============ ============ =========================================
320px  288          286          .sc-table-scroll / .ps-table-scroll
360px  328          326          .sc-table-scroll / .ps-table-scroll
375px  343          341          .sc-table-scroll / .ps-table-scroll
390px  358          356          .sc-table-scroll / .ps-table-scroll
====== ============ ============ =========================================

The purpose and hub pages put their tables in ``.ks-editorial-table``, which is
inset a further 1rem on each side; the same run measured 254/294/309/324 there.
Those tables are listed for completeness -- every one of them already frames a
whole data cell at 320px with room to spare.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTICLES = ROOT / "changes/wordpress-direct-publish-v1/articles"

#: Inner width of ``.sc-table-scroll`` / ``.ps-table-scroll`` in an article body.
ARTICLE_SCROLL_FRAME = {320: 286.0, 360: 326.0, 375: 341.0, 390: 356.0}

#: Inner width of ``.ks-editorial-table`` on a purpose or hub page.
PURPOSE_SCROLL_FRAME = {320: 254.0, 360: 294.0, 375: 309.0, 390: 324.0}

PHONE_QUERY = "@media (max-width:600px) {"


def phone_block(css: str) -> str:
    """Return every ``@media (max-width:600px)`` block, whitespace removed."""
    blocks = re.findall(r"@media \(max-width:600px\) \{(.*?)\n\}", css, re.S)
    assert blocks, "phone block"
    return "\n".join(blocks).replace(" ", "")


def _table(slug: str, table_class: str) -> str:
    body = (ARTICLES / f"{slug}.html").read_text(encoding="utf-8")
    match = re.search(
        r"<table[^>]*\bclass=\"[^\"]*" + re.escape(table_class) + r"[^\"]*\"[^>]*>.*?</table>",
        body,
        re.S,
    )
    assert match, (slug, table_class)
    return match.group(0)


def data_columns(slug: str, table_class: str) -> int:
    """Columns beside the sticky first column, counted from the published table."""
    head = re.search(r"<thead>\s*<tr[^>]*>(.*?)</tr>", _table(slug, table_class), re.S)
    assert head, (slug, table_class)
    # ``<th[ >]`` and not ``<th[^>]``: the latter also counts the ``<thead>`` tag.
    return len(re.findall(r"<th[ >]", head.group(1))) - 1
