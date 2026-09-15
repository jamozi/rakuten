"""Generated entry pages keep a heading outline without skipped levels (KS-028-d)."""

import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "site_builder_heading_order", ROOT / "scripts/build_site_editorial_pages.py"
)
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

HEADING = re.compile(r"<h([1-6])[\s>]")


def skipped_levels(body: str) -> list[tuple[int, int]]:
    levels = [int(level) for level in HEADING.findall(body)]
    # The WordPress page template prints the title as h1 unless the body owns it.
    if 1 not in levels:
        levels.insert(0, 1)
    return [
        (before, after)
        for before, after in zip(levels, levels[1:])
        if after > before + 1
    ]


class HeadingOrder(unittest.TestCase):
    def test_generated_pages_do_not_skip_heading_levels(self):
        pages = {
            path.name: body
            for path, body in builder.build().items()
            if path.suffix == ".html"
        }
        self.assertIn("categories.html", pages)
        for name, body in pages.items():
            with self.subTest(page=name):
                self.assertEqual(skipped_levels(body), [])

    def test_category_cards_are_second_level_without_new_heading_text(self):
        body = next(
            b for p, b in builder.build().items() if p.name == "categories.html"
        )
        names = re.findall(r'<article class="ks-editorial-card"><h2>([^<]+)</h2>', body)
        self.assertEqual(
            names, ["スーツケース", "食洗機", "ロボット掃除機", "ポータブル電源"]
        )
        self.assertNotIn('<article class="ks-editorial-card"><h3>', body)

    def test_skipped_levels_are_detected(self):
        self.assertEqual(skipped_levels("<h3>a</h3>"), [(1, 3)])
        self.assertEqual(skipped_levels("<h2>a</h2><h4>b</h4>"), [(2, 4)])
        self.assertEqual(skipped_levels("<h2>a</h2><h3>b</h3><h2>c</h2>"), [])


if __name__ == "__main__":
    unittest.main()
