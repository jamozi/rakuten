"""Reader roles for every ledger row (KS-014 data and checks, batch F).

Every test here failed before batch F added reader_role and its validator.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "site_builder_roles", ROOT / "scripts/build_site_editorial_pages.py"
)
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

from raos.application.editorial.site_editorial_pages import (  # noqa: E402
    PLANNED_BATCHES,
    READER_PAGE_KINDS,
    validate_reader_roles,
)

ROLE_KEYS = {
    "page_kind",
    "primary_intent",
    "reader",
    "decision_after_reading",
    "main_cta",
    "next_question",
}


def role(kind, cta, question, intent, scope=None):
    value = {
        "page_kind": kind,
        "primary_intent": intent,
        "reader": "試験用の読者",
        "decision_after_reading": "試験用の判断",
        "main_cta": dict(zip(("kind", "target", "anchor", "label"), cta)),
        "next_question": dict(
            zip(("question", "target", "anchor", "status"), question)
        ),
    }
    if scope is not None:
        value["scope"] = scope
    return value


def fixture():
    registry = {
        "articles": [
            {
                "article_key": "home",
                "mode": "existing",
                "post_id": 1,
                "post_type": "page",
                "slug": "home",
                "reader_role": role(
                    "home",
                    ("internal", None, "", "カテゴリから選ぶ"),
                    ("比べる記事は？", "alpha", "", "live"),
                    "ホームの意図",
                ),
            },
            {
                "article_key": "alpha",
                "mode": "existing",
                "post_id": 2,
                "post_type": "post",
                "slug": "alpha",
                "listing": {"state": "published"},
                "reader_role": role(
                    "condition_comparison",
                    ("offer", None, "specs", "販売条件へ"),
                    ("ガイドは？", "beta", "", "live"),
                    "比較の意図",
                ),
            },
            {
                "article_key": "beta",
                "mode": "existing",
                "post_id": 3,
                "post_type": "post",
                "slug": "beta",
                "listing": {"state": "published"},
                "reader_role": role(
                    "task_guide",
                    ("none", None, "", ""),
                    ("比較表は？", "alpha", "specs", "live"),
                    "ガイドの意図",
                    {"primary_product_ids": ["P1"], "reference_product_ids": []},
                ),
            },
            {
                "article_key": "gamma",
                "mode": "existing",
                "post_id": 4,
                "post_type": "post",
                "slug": "gamma",
                "listing": {"state": "draft"},
                "reader_role": role(
                    "condition_comparison",
                    ("none", None, "", ""),
                    ("比較は？", "alpha", "", "live"),
                    "下書きの意図",
                ),
            },
        ]
    }
    documents = {
        "home": '<a href="/alpha/">比較</a>',
        "alpha": '<section id="specs"></section><a rel="sponsored" href="https://example.com/x">販売先</a><a href="/beta/">ガイド</a>',
        "beta": '<p>MODEL-X</p><a href="/alpha/#specs">比較表</a>',
        "gamma": "",
    }
    catalog = {"products": [{"product_id": "P1", "exact_model": "MODEL-X"}]}
    return registry, documents, catalog


def rows(registry):
    return {r["article_key"]: r for r in registry["articles"]}


class RoleValidatorFixtures(unittest.TestCase):
    def assertIssue(self, issues, prefix):
        self.assertTrue(any(i.startswith(prefix) for i in issues), issues)

    def test_fixture_is_valid(self):
        self.assertEqual(validate_reader_roles(*fixture()), [])

    def test_live_next_question_needs_a_generated_link(self):
        registry, documents, catalog = fixture()
        documents["alpha"] = documents["alpha"].replace(
            '<a href="/beta/">ガイド</a>', ""
        )
        self.assertIssue(
            validate_reader_roles(registry, documents, catalog),
            "READER_NEXT_QUESTION_UNLINKED: alpha",
        )

    def test_planned_next_question_must_name_its_batch_and_stay_unlinked(self):
        registry, documents, catalog = fixture()
        question = rows(registry)["alpha"]["reader_role"]["next_question"]
        for status in ("planned", "planned:Q", "planned:", "later"):
            question["status"] = status
            self.assertIssue(
                validate_reader_roles(registry, documents, catalog),
                "READER_NEXT_QUESTION_STATUS_INVALID: alpha",
            )
        question["status"] = "planned:J2"
        self.assertIssue(
            validate_reader_roles(registry, documents, catalog),
            "READER_NEXT_QUESTION_ALREADY_LIVE: alpha",
        )
        documents["alpha"] = documents["alpha"].replace(
            '<a href="/beta/">ガイド</a>', ""
        )
        self.assertEqual(validate_reader_roles(registry, documents, catalog), [])

    def test_next_question_target_must_be_another_published_row(self):
        registry, documents, catalog = fixture()
        question = rows(registry)["alpha"]["reader_role"]["next_question"]
        for target in ("alpha", "gamma", "missing"):
            question["target"] = target
            self.assertIssue(
                validate_reader_roles(registry, documents, catalog),
                "READER_NEXT_QUESTION_TARGET_INVALID: alpha",
            )

    def test_internal_main_cta_needs_its_link_and_a_target(self):
        registry, documents, catalog = fixture()
        cta = rows(registry)["beta"]["reader_role"]["main_cta"]
        cta.update(kind="internal", target="alpha", anchor="missing", label="比較へ")
        self.assertIssue(
            validate_reader_roles(registry, documents, catalog),
            "READER_MAIN_CTA_UNLINKED: beta",
        )
        cta.update(target=None, anchor="")
        self.assertIssue(
            validate_reader_roles(registry, documents, catalog),
            "READER_MAIN_CTA_TARGET_INVALID: beta",
        )

    def test_offer_cta_needs_comparison_kind_anchor_and_sponsored_link(self):
        registry, documents, catalog = fixture()
        cta = rows(registry)["beta"]["reader_role"]["main_cta"]
        cta.update(kind="offer", anchor="specs", label="販売条件へ")
        self.assertIssue(
            validate_reader_roles(registry, documents, catalog),
            "READER_MAIN_CTA_OFFER_INVALID: beta",
        )
        registry, documents, catalog = fixture()
        rows(registry)["alpha"]["reader_role"]["main_cta"]["anchor"] = "offers"
        self.assertIssue(
            validate_reader_roles(registry, documents, catalog),
            "READER_MAIN_CTA_OFFER_INVALID: alpha",
        )
        registry, documents, catalog = fixture()
        documents["alpha"] = documents["alpha"].replace(' rel="sponsored"', "")
        self.assertIssue(
            validate_reader_roles(registry, documents, catalog),
            "READER_MAIN_CTA_OFFER_INVALID: alpha",
        )

    def test_incomplete_or_unknown_roles_are_rejected(self):
        registry, documents, catalog = fixture()
        del rows(registry)["alpha"]["reader_role"]["reader"]
        self.assertIssue(
            validate_reader_roles(registry, documents, catalog),
            "READER_ROLE_INCOMPLETE: alpha",
        )
        registry, documents, catalog = fixture()
        rows(registry)["alpha"]["reader_role"]["page_kind"] = "listicle"
        self.assertIssue(
            validate_reader_roles(registry, documents, catalog),
            "READER_ROLE_INVALID: alpha",
        )
        registry, documents, catalog = fixture()
        rows(registry)["alpha"]["reader_role"]["scope"] = {
            "primary_product_ids": [],
            "reference_product_ids": [],
        }
        self.assertIssue(
            validate_reader_roles(registry, documents, catalog),
            "READER_ROLE_INVALID: alpha",
        )

    def test_guide_scope_models_must_appear_in_the_guide(self):
        registry, documents, catalog = fixture()
        documents["beta"] = documents["beta"].replace("MODEL-X", "MODEL-Y")
        self.assertIssue(
            validate_reader_roles(registry, documents, catalog),
            "READER_SCOPE_MODEL_MISSING: beta",
        )

    def test_primary_intents_are_unique(self):
        registry, documents, catalog = fixture()
        rows(registry)["beta"]["reader_role"]["primary_intent"] = "比較の意図"
        self.assertIssue(
            validate_reader_roles(registry, documents, catalog),
            "READER_PRIMARY_INTENT_DUPLICATE: beta",
        )


class LedgerRoles(unittest.TestCase):
    def setUp(self):
        self.data, self.registry, self.catalog = [
            json.loads((ROOT / p).read_text()) for p in builder.INPUT_PATHS[:3]
        ]

    def test_every_ledger_row_has_a_reader_role(self):
        rows = self.registry["articles"]
        posts = [r for r in rows if r["post_type"] == "post"]
        # 19 pages, the 23 published posts, and the three next30 Wave 2 rows
        # (A04 / A05 / A07) whose body exists while their post id does not.
        # Wave 1's three were given their post ids on 2026-09-20.
        self.assertEqual(
            (
                len(rows),
                len(rows) - len(posts),
                sum(r["mode"] == "existing" for r in posts),
                sum(r["mode"] == "new" for r in posts),
            ),
            (45, 19, 23, 3),
        )
        for row in self.registry["articles"]:
            with self.subTest(key=row["article_key"]):
                value = row["reader_role"]
                self.assertTrue(ROLE_KEYS <= set(value))
                self.assertIn(value["page_kind"], READER_PAGE_KINDS)
                self.assertEqual("scope" in value, value["page_kind"] == "task_guide")
                self.assertNotEqual(
                    value["next_question"]["target"], row["article_key"]
                )

    def test_ledger_roles_are_satisfied_by_generated_documents(self):
        documents = builder.reader_documents()
        self.assertEqual(
            set(documents), {r["article_key"] for r in self.registry["articles"]}
        )
        self.assertEqual(
            validate_reader_roles(self.registry, documents, self.catalog), []
        )

    def test_planned_questions_belong_to_batches_ending_at_j2(self):
        self.assertEqual(PLANNED_BATCHES, ("H", "I", "J1", "J2"))
        for row in self.registry["articles"]:
            status = row["reader_role"]["next_question"]["status"]
            self.assertIn(status, {"live"} | {"planned:" + b for b in PLANNED_BATCHES})

    def test_home_cta_has_no_target_and_category_hubs_point_at_representatives(self):
        roles = {r["article_key"]: r for r in self.registry["articles"]}
        self.assertIsNone(roles["home"]["reader_role"]["main_cta"]["target"])
        for slug, category in self.data["categories"].items():
            with self.subTest(slug=slug):
                representative = roles[category["representative"]]
                self.assertEqual(representative["listing"]["role"], "comparison")
                self.assertEqual(representative["listing"]["category"], slug)
                self.assertEqual(
                    roles[slug]["reader_role"]["main_cta"]["target"],
                    category["representative"],
                )

    def test_validation_runs_inside_the_build(self):
        registry = copy.deepcopy(self.registry)
        row = next(r for r in registry["articles"] if r["article_key"] == "updates")
        row["reader_role"]["next_question"]["status"] = "planned:H"
        with self.assertRaisesRegex(
            ValueError, "READER_NEXT_QUESTION_ALREADY_LIVE: updates"
        ):
            builder.validate_build(registry=registry)


if __name__ == "__main__":
    unittest.main()
