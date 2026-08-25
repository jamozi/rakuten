#!/usr/bin/env python3
"""Generate the deterministic ST-1704 affiliate-learning V2 contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Final, NoReturn, cast


ROOT: Final = Path(__file__).resolve().parents[1]
SLICE: Final = ROOT / "changes/st-1704/affiliate-learning-v2"
CONTRACT_PATH: Final = SLICE / "measurement-contract.v2.json"
MANIFEST_PATH: Final = SLICE / "runtime-manifest.v2.json"
ARTICLE_EXAMPLE_PATH: Final = SLICE / "examples/article-observation.v2.json"
PROGRAM_EXAMPLE_PATH: Final = SLICE / "examples/program-observation.v2.json"
ARTICLE_COLLECTION: Final = ROOT / (
    "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json"
)
COMPATIBILITY_TEMPLATE: Final = ROOT / (
    "changes/st-1704/self-hosted-editorial-pilot-v1/operations/measurement-ledger.v1.json"
)
PROGRAM: Final = "WORDPRESS_BLOG_RAKUTEN_AFFILIATE"

INTENT_BY_ARTICLE_TYPE: Final = {
    "AT-001": "SELECTION_GUIDE",
    "AT-002": "HOUSEHOLD_FIT_COMPARISON",
    "AT-003": "CONDITION_COMPARISON",
    "AT-004": "MODEL_DIFFERENCES",
    "AT-005": "CONDITION_SHORTLIST",
}
EXPECTED_IDS: Final = (
    "st1703-first-suitcase-comparison",
    "st1704-portable-power-station-guide",
    "st1704-anker-solix-c300-c800-c1000-differences",
    "st1704-countertop-dishwasher-for-small-households",
    "st1704-compact-robot-vacuum-shortlist",
)
RUNTIME_SOURCES: Final = (
    "changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json",
    "python/raos/adapters/affiliate_learning_json.py",
    "python/raos/application/editorial/affiliate_learning.py",
    "python/raos/domain/editorial/affiliate_learning.py",
    "python/raos/domain/editorial/owner_local_pilot.py",
    "python/raos/ports/affiliate_learning.py",
    "scripts/build_st1704_affiliate_learning.py",
    "scripts/st1704_affiliate_learning.py",
)


class BuildFailure(RuntimeError):
    pass


def _fail() -> NoReturn:
    raise BuildFailure("ST1704_AFFILIATE_LEARNING_BUILD_FAILED") from None


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail()
        result[key] = value
    return result


def _reject_number(value: str) -> NoReturn:
    del value
    _fail()


def _decode(raw: bytes) -> object:
    if not raw or raw.startswith(b"\xef\xbb\xbf"):
        _fail()
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except BuildFailure, UnicodeError, json.JSONDecodeError, ValueError, RecursionError:
        _fail()


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeError:
        _fail()


def _render(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeError:
        _fail()


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read(path: Path, *, maximum: int = 16_777_216) -> bytes:
    try:
        observed = path.lstat()
        if (
            not path.is_file()
            or path.is_symlink()
            or observed.st_nlink != 1
            or not 0 < observed.st_size <= maximum
        ):
            _fail()
        raw = path.read_bytes()
    except OSError:
        _fail()
    if len(raw) != observed.st_size:
        _fail()
    return raw


def _mapping(value: object) -> dict[str, object]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        _fail()
    return cast(dict[str, object], value)


def _list(value: object) -> list[object]:
    if type(value) is not list:
        _fail()
    return cast(list[object], value)


def _contract() -> dict[str, object]:
    article_raw = _read(ARTICLE_COLLECTION)
    template_raw = _read(COMPATIBILITY_TEMPLATE)
    collection = _mapping(_decode(article_raw))
    raw_articles = _list(collection.get("articles"))
    if len(raw_articles) != 5:
        _fail()
    articles: list[dict[str, object]] = []
    for expected_slot, (expected_id, raw_article) in enumerate(
        zip(EXPECTED_IDS, raw_articles, strict=True), 1
    ):
        article = _mapping(raw_article)
        required = {
            "slot",
            "article_id",
            "slug",
            "article_type_code",
            "intent_cluster",
        }
        if (
            not required <= set(article)
            or article["slot"] != expected_slot
            or article["article_id"] != expected_id
            or type(article["slug"]) is not str
            or type(article["article_type_code"]) is not str
            or article["article_type_code"] not in INTENT_BY_ARTICLE_TYPE
            or type(article["intent_cluster"]) is not str
        ):
            _fail()
        articles.append(
            {
                "article_id": article["article_id"],
                "article_type_code": article["article_type_code"],
                "intent_classification": INTENT_BY_ARTICLE_TYPE[
                    article["article_type_code"]
                ],
                "intent_cluster": article["intent_cluster"],
                "packet_sha256": _sha256(_canonical(article)),
                "slot": expected_slot,
                "slug": article["slug"],
            }
        )
    return {
        "articles": articles,
        "derivation_contract": {
            "affiliate_click_rate": "sum(affiliate_clicks)/sum(article_views)",
            "confirmation_rate": "sum(confirmed_outcomes)/sum(confirmed_outcomes+rejected_outcomes)",
            "confirmed_reward_per_click_jpy": "sum(direct_confirmed_reward_jpy)/sum(affiliate_clicks)",
            "confirmed_reward_per_content_hour_jpy": "sum(direct_confirmed_reward_jpy)*60/sum(work_minutes)",
            "decimal_places": 6,
            "rounding": "ROUND_HALF_EVEN",
            "search_ctr": "sum(search_clicks)/sum(search_impressions)",
            "unavailability": [
                "MISSING_INPUT",
                "UNVERIFIED_INPUT",
                "ZERO_DENOMINATOR",
                "COHORT_IMMATURE",
                "PERIOD_MISMATCH",
                "PROGRAM_MISMATCH",
                "MISSING_ARTICLE_SLOTS",
            ],
        },
        "guardrails": {
            "article_html_mutation": False,
            "arbitrary_total_allocation": False,
            "automatic_publication": False,
            "cta_mutation": False,
            "live_provider_calls": False,
            "network_requests": False,
            "product_selection_mutation": False,
            "publication_snapshot_mutation": False,
            "recommendation_inputs_excluded": [
                "AFFILIATE_COMMISSION_RATE",
                "EPC",
                "RPM",
                "PROFIT",
            ],
            "recommendation_order_mutation": False,
            "tracking_activation": False,
            "unattributed_reward_article_allocation": False,
        },
        "metric_contract": {
            "article_metrics": [
                "search_impressions",
                "search_clicks",
                "article_views",
                "affiliate_clicks",
                "pending_outcomes",
                "confirmed_outcomes",
                "rejected_outcomes",
                "direct_confirmed_reward_jpy",
                "work_minutes",
                "incremental_cost_jpy",
                "broken_links",
            ],
            "program_metrics": ["unattributed_confirmed_reward_jpy"],
            "states": [
                "NOT_OBSERVED",
                "UNAVAILABLE",
                "UNVERIFIED",
                "OBSERVED_ZERO",
                "OBSERVED_VALUE",
            ],
            "zero_is_observed_only_when_explicit": True,
        },
        "owner_private_paths": {
            "directory": ".secrets/st1704-owner-local-pilot",
            "input": "affiliate-learning-observation-input.v2.json",
            "ledger": "affiliate-learning-ledger.v2.json",
            "lock": "affiliate-learning-ledger.v2.lock",
            "stage": "affiliate-learning-ledger.v2.json.preparing",
        },
        "packet_hash_basis": "TRACKED_ARTICLE_OBJECT_CANONICAL_JSON_SHA256",
        "period_duration_days": 14,
        "program": PROGRAM,
        "schema": "ST1704_AFFILIATE_LEARNING_MEASUREMENT_CONTRACT_V2",
        "slice_id": "AFFILIATE_LEARNING_MEASUREMENT_V2",
        "source_bindings": {
            "article_collection_path": ARTICLE_COLLECTION.relative_to(ROOT).as_posix(),
            "article_collection_sha256": _sha256(article_raw),
            "compatibility_template_path": COMPATIBILITY_TEMPLATE.relative_to(
                ROOT
            ).as_posix(),
            "compatibility_template_sha256": _sha256(template_raw),
        },
        "story_id": "ST-1704",
    }


def _unavailable_value() -> dict[str, object]:
    return {"input_sha256": None, "state": "UNAVAILABLE", "value": None}


def _article_example(contract: dict[str, object]) -> dict[str, object]:
    article = _mapping(_list(contract["articles"])[0])
    return {
        "article": article,
        "cohort": {
            "input_sha256": None,
            "state": "UNAVAILABLE",
            "verified_at_utc": None,
        },
        "metrics": {
            name: _unavailable_value()
            for name in cast(
                list[str], _mapping(contract["metric_contract"])["article_metrics"]
            )
        },
        "observation_id": "EXAMPLE.UNAVAILABLE.ARTICLE.001",
        "observed_at_utc": "2026-09-08T00:00:00Z",
        "period": {
            "duration_days": 14,
            "end_exclusive_date": "2026-09-08",
            "start_date": "2026-08-25",
        },
        "program": PROGRAM,
        "schema": "ST1704_AFFILIATE_LEARNING_ARTICLE_OBSERVATION_V2",
        "verification": {
            "attribution_basis": "UNAVAILABLE",
            "input_sha256": None,
            "state": "UNAVAILABLE",
        },
    }


def _program_example() -> dict[str, object]:
    return {
        "cohort": {
            "input_sha256": None,
            "state": "UNAVAILABLE",
            "verified_at_utc": None,
        },
        "metrics": {"unattributed_confirmed_reward_jpy": _unavailable_value()},
        "observation_id": "EXAMPLE.UNAVAILABLE.PROGRAM.001",
        "observed_at_utc": "2026-09-08T00:00:00Z",
        "period": {
            "duration_days": 14,
            "end_exclusive_date": "2026-09-08",
            "start_date": "2026-08-25",
        },
        "program": PROGRAM,
        "schema": "ST1704_AFFILIATE_LEARNING_PROGRAM_OBSERVATION_V2",
        "verification": {
            "attribution_basis": "UNAVAILABLE",
            "input_sha256": None,
            "state": "UNAVAILABLE",
        },
    }


def _manifest(
    *,
    contract_bytes: bytes,
    article_example_bytes: bytes,
    program_example_bytes: bytes,
) -> dict[str, object]:
    sources: list[dict[str, object]] = []
    for relative in RUNTIME_SOURCES:
        if relative == CONTRACT_PATH.relative_to(ROOT).as_posix():
            raw = contract_bytes
        else:
            raw = _read(ROOT / relative)
        sources.append({"path": relative, "sha256": _sha256(raw), "size": len(raw)})
    return {
        "authority": {
            "analytics_activation": False,
            "external_writes": False,
            "network_requests": False,
            "publication": False,
            "recommendation_mutation": False,
            "tracking": False,
        },
        "contract_sha256": _sha256(_canonical(_decode(contract_bytes))),
        "fixtures": [
            {
                "path": ARTICLE_EXAMPLE_PATH.relative_to(ROOT).as_posix(),
                "sha256": _sha256(article_example_bytes),
            },
            {
                "path": PROGRAM_EXAMPLE_PATH.relative_to(ROOT).as_posix(),
                "sha256": _sha256(program_example_bytes),
            },
        ],
        "generated_by": "scripts/build_st1704_affiliate_learning.py",
        "program": PROGRAM,
        "runtime_sources": sources,
        "schema": "ST1704_AFFILIATE_LEARNING_RUNTIME_MANIFEST_V2",
        "slice_id": "AFFILIATE_LEARNING_MEASUREMENT_V2",
        "story_id": "ST-1704",
    }


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".preparing", dir=path.parent
    )
    try:
        os.fchmod(descriptor, 0o644)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                _fail()
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def generate(*, check: bool) -> None:
    contract = _contract()
    contract_bytes = _render(contract)
    article_example_bytes = _render(_article_example(contract))
    program_example_bytes = _render(_program_example())
    manifest_bytes = _render(
        _manifest(
            contract_bytes=contract_bytes,
            article_example_bytes=article_example_bytes,
            program_example_bytes=program_example_bytes,
        )
    )
    outputs = {
        CONTRACT_PATH: contract_bytes,
        ARTICLE_EXAMPLE_PATH: article_example_bytes,
        PROGRAM_EXAMPLE_PATH: program_example_bytes,
        MANIFEST_PATH: manifest_bytes,
    }
    if check:
        if any(
            not path.exists() or _read(path) != payload
            for path, payload in outputs.items()
        ):
            _fail()
        return
    for path, payload in outputs.items():
        _write(path, payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        generate(check=cast(bool, args.check))
    except BuildFailure as error:
        print(str(error))
        return 1
    print("ST1704_AFFILIATE_LEARNING_GENERATION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
