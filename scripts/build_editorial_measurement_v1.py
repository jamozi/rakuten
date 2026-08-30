#!/usr/bin/env python3
"""Generate and verify the fixed Editorial V3 measurement WordPress artifact."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Final, NoReturn
import zipfile


ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_editorial_portfolio_v3 as editorial_v3_owner  # noqa: E402


SOURCE: Final = ROOT / editorial_v3_owner.OUTPUT_PATHS[0]
SLICE: Final = ROOT / "changes/editorial-measurement-v1"
PLUGIN_SLUG: Final = "raos-editorial-measurement"
PLUGIN_VERSION: Final = "1.0.0"
ARTIFACT_ID: Final = "raos-editorial-measurement-v1"
PLUGIN_ROOT: Final = SLICE / "wordpress-plugin" / PLUGIN_SLUG
ALLOWLIST: Final = PLUGIN_ROOT / "config/measurement-allowlist.v1.json"
MANIFEST: Final = SLICE / "runtime-manifest.v1.json"
REGISTRY: Final = (
    ROOT / "changes/wordpress-mcp-v1/contracts/repo-plugin-artifacts.v1.json"
)
PACKAGE: Final = (
    ROOT
    / ".secrets/wordpress-mcp/repo-plugin-artifacts"
    / f"{ARTIFACT_ID}.zip"
)
ZIP_TIMESTAMP: Final = (2026, 8, 30, 0, 0, 0)
EVENTS: Final = (
    "affiliate_click",
    "affiliate_cta_impression",
    "article_view",
    "comparison_interaction",
    "disclosure_view",
    "internal_link_click",
    "product_card_view",
    "qualified_decision_engagement",
)
PLUGIN_FILES: Final = (
    "README.md",
    "config/measurement-allowlist.v1.json",
    "includes/class-raos-measurement-contract.php",
    "includes/class-raos-measurement-store.php",
    "raos-editorial-measurement.php",
)
RUNTIME_INPUT_PATHS: Final = (
    Path("changes/editorial-portfolio-v3/editorial-portfolio.v3.json"),
    Path("changes/editorial-measurement-v1/measurement-runtime.v1.json"),
    Path(
        "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
        "kurashinoshirube-child/assets/measurement.js"
    ),
    Path(
        "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
        "kurashinoshirube-child/functions.php"
    ),
    Path("scripts/build_editorial_measurement_v1.py"),
    Path("tests/editorial_measurement_v1/test_contract.py"),
    Path("tests/editorial_measurement_v1/measurement_client_harness.mjs"),
)
RUNTIME_FILES: Final = tuple(path.as_posix() for path in RUNTIME_INPUT_PATHS)
TEST_PATHS: Final = (Path("tests/editorial_measurement_v1"),)


class BuildFailure(RuntimeError):
    pass


def fail(code: str) -> NoReturn:
    raise BuildFailure(code) from None


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value: object) -> bytes:
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
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        fail("EDITORIAL_MEASUREMENT_JSON_INVALID")


def read_regular(path: Path, *, maximum: int = 8 * 1024 * 1024) -> bytes:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        fail("EDITORIAL_MEASUREMENT_SOURCE_MISSING")
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size < 1
        or metadata.st_size > maximum
        or len(payload) != metadata.st_size
    ):
        fail("EDITORIAL_MEASUREMENT_SOURCE_INVALID")
    return payload


def load_source() -> tuple[dict[str, object], bytes]:
    if RUNTIME_INPUT_PATHS[0] != editorial_v3_owner.OUTPUT_PATHS[0]:
        fail("EDITORIAL_MEASUREMENT_OWNER_BINDING_INVALID")
    raw = read_regular(SOURCE)
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError):
        fail("EDITORIAL_MEASUREMENT_PORTFOLIO_INVALID")
    if (
        type(value) is not dict
        or value.get("schema") != "RAOS_EDITORIAL_PORTFOLIO_V3"
        or value.get("version") != "3.0.0"
        or value.get("target_origin") != "https://kurashinoshirube.com"
        or type(value.get("articles")) is not list
        or type(value.get("products")) is not list
        or len(value["articles"]) != 10
    ):
        fail("EDITORIAL_MEASUREMENT_PORTFOLIO_INVALID")
    return value, raw


def token(value: object, code: str, maximum: int = 96) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value.encode("ascii", errors="ignore")) <= maximum
        or not value[0].isalnum()
        or any(not (character.isalnum() or character in "._-") for character in value)
        or not value.isascii()
    ):
        fail(code)
    return value


def generated_allowlist() -> dict[str, object]:
    source, raw = load_source()
    products: dict[str, str] = {}
    product_codes: set[str] = set()
    for row in source["products"]:
        if type(row) is not dict:
            fail("EDITORIAL_MEASUREMENT_PRODUCT_INVALID")
        product_id = token(
            row.get("product_id"), "EDITORIAL_MEASUREMENT_PRODUCT_INVALID"
        )
        product_code = token(
            row.get("product_code"), "EDITORIAL_MEASUREMENT_PRODUCT_INVALID", 16
        )
        if product_id in products or product_code in product_codes:
            fail("EDITORIAL_MEASUREMENT_PRODUCT_DUPLICATE")
        products[product_id] = product_code
        product_codes.add(product_code)
    articles: list[dict[str, object]] = []
    seen_articles: set[str] = set()
    seen_codes: set[str] = set()
    seen_snapshots: set[str] = set()
    seen_ctas: set[str] = set()
    seen_measurement_ids: set[str] = set()
    offer_owners: dict[str, tuple[str, str]] = {}
    for row in source["articles"]:
        if type(row) is not dict:
            fail("EDITORIAL_MEASUREMENT_ARTICLE_INVALID")
        article_id = token(row.get("article_id"), "EDITORIAL_MEASUREMENT_ARTICLE_INVALID")
        article_code = token(
            row.get("article_code"), "EDITORIAL_MEASUREMENT_ARTICLE_INVALID", 16
        )
        snapshot_id = token(
            row.get("snapshot_id"), "EDITORIAL_MEASUREMENT_ARTICLE_INVALID"
        )
        category_id = token(
            row.get("category"), "EDITORIAL_MEASUREMENT_ARTICLE_INVALID", 32
        )
        if (
            article_id in seen_articles
            or article_code in seen_codes
            or snapshot_id in seen_snapshots
        ):
            fail("EDITORIAL_MEASUREMENT_ARTICLE_DUPLICATE")
        seen_articles.add(article_id)
        seen_codes.add(article_code)
        seen_snapshots.add(snapshot_id)
        related_raw = row.get("related_article_ids")
        bindings_raw = row.get("cta_bindings")
        if type(related_raw) is not list or type(bindings_raw) is not list:
            fail("EDITORIAL_MEASUREMENT_ARTICLE_INVALID")
        related = [
            token(value, "EDITORIAL_MEASUREMENT_RELATED_INVALID")
            for value in related_raw
        ]
        if len(set(related)) != len(related):
            fail("EDITORIAL_MEASUREMENT_RELATED_INVALID")
        bindings: list[dict[str, str]] = []
        binding_keys: set[tuple[str, str]] = set()
        for binding in bindings_raw:
            if type(binding) is not dict:
                fail("EDITORIAL_MEASUREMENT_CTA_INVALID")
            # CTA/offer identity is safe to measure before Rakuten confirms the
            # separate measurement-ID profile. Direct revenue attribution stays
            # disabled in V3 until that provider profile is verified; this
            # client projection never contains the Rakuten measurement ID.
            if binding.get("provider_profile_state") not in {
                "UNVERIFIED_DISABLED",
                "VERIFIED",
            }:
                fail("EDITORIAL_MEASUREMENT_CTA_INVALID")
            product_id = token(
                binding.get("product_id"), "EDITORIAL_MEASUREMENT_CTA_INVALID"
            )
            product_code = token(
                binding.get("product_code"),
                "EDITORIAL_MEASUREMENT_CTA_INVALID",
                16,
            )
            cta_id = token(binding.get("cta_id"), "EDITORIAL_MEASUREMENT_CTA_INVALID")
            offer_id = token(
                binding.get("offer_id"), "EDITORIAL_MEASUREMENT_CTA_INVALID"
            )
            placement = binding.get("placement")
            if placement not in {"product_card", "final_summary"}:
                fail("EDITORIAL_MEASUREMENT_CTA_INVALID")
            placement_code = "card" if placement == "product_card" else "final"
            measurement_id = token(
                binding.get("rakuten_measurement_id"),
                "EDITORIAL_MEASUREMENT_CTA_INVALID",
            )
            expected_measurement_id = (
                f"{article_code}-{product_code}-{placement_code}"
            )
            if (
                binding.get("article_id") != article_id
                or binding.get("article_code") != article_code
                or binding.get("snapshot_id") != snapshot_id
                or binding.get("placement_code") != placement_code
                or products.get(product_id) != product_code
                or measurement_id != expected_measurement_id
                or cta_id != f"cta-{expected_measurement_id}"
                or offer_id != f"off-{article_code}-{product_code}"
                or cta_id in seen_ctas
                or measurement_id in seen_measurement_ids
                or offer_owners.get(offer_id, (article_id, product_id))
                != (article_id, product_id)
            ):
                fail("EDITORIAL_MEASUREMENT_CTA_INVALID")
            seen_ctas.add(cta_id)
            seen_measurement_ids.add(measurement_id)
            offer_owners[offer_id] = (article_id, product_id)
            key = (product_id, placement)
            if key in binding_keys:
                fail("EDITORIAL_MEASUREMENT_CTA_DUPLICATE")
            binding_keys.add(key)
            bindings.append(
                {
                    "product_id": product_id,
                    "cta_id": cta_id,
                    "offer_id": offer_id,
                    "placement": placement,
                }
            )
        articles.append(
            {
                "article_id": article_id,
                "article_code": article_code,
                "snapshot_id": snapshot_id,
                "category_id": category_id,
                "related_article_ids": related,
                "cta_bindings": sorted(
                    bindings, key=lambda item: (item["product_id"], item["placement"])
                ),
            }
        )
    for row in articles:
        if row["article_id"] in row["related_article_ids"] or not set(
            row["related_article_ids"]
        ).issubset(seen_articles):
            fail("EDITORIAL_MEASUREMENT_RELATED_INVALID")
    return {
        "schema": "RAOS_EDITORIAL_MEASUREMENT_ALLOWLIST_V1",
        "version": "1.0.0",
        "source": {
            "path": SOURCE.relative_to(ROOT).as_posix(),
            "schema": source["schema"],
            "version": source["version"],
            "sha256": sha256(raw),
        },
        "site_id": "kurashinoshirube",
        "target_origin": "https://kurashinoshirube.com",
        "events": list(EVENTS),
        "articles": sorted(articles, key=lambda item: item["article_code"]),
    }


def plugin_payloads(allowlist_payload: bytes) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    seen: set[str] = set()
    for relative in PLUGIN_FILES:
        safe = PurePosixPath(relative)
        if (
            safe.as_posix() != relative
            or relative.startswith("/")
            or "\\" in relative
            or any(part in {"", ".", ".."} for part in safe.parts)
            or relative.casefold() in seen
        ):
            fail("EDITORIAL_MEASUREMENT_PLUGIN_PATH_INVALID")
        seen.add(relative.casefold())
        result[relative] = (
            allowlist_payload
            if relative == "config/measurement-allowlist.v1.json"
            else read_regular(PLUGIN_ROOT.joinpath(*safe.parts))
        )
    return result


def package_bytes(payloads: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for relative in sorted(payloads):
            info = zipfile.ZipInfo(f"{PLUGIN_SLUG}/{relative}", ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(
                info,
                payloads[relative],
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
    return output.getvalue()


def generated_manifest() -> tuple[dict[str, object], bytes, bytes]:
    allowlist_payload = canonical_json(generated_allowlist())
    payloads = plugin_payloads(allowlist_payload)
    package = package_bytes(payloads)
    runtime = []
    for relative in RUNTIME_FILES:
        payload = read_regular(ROOT / relative)
        runtime.append(
            {"path": relative, "size": len(payload), "sha256": sha256(payload)}
        )
    return (
        {
            "schema": "RAOS_EDITORIAL_MEASUREMENT_RUNTIME_MANIFEST_V1",
            "version": "1.0.0",
            "artifact_id": ARTIFACT_ID,
            "plugin_slug": PLUGIN_SLUG,
            "plugin_version": PLUGIN_VERSION,
            "default_enabled": False,
            "host_gate": "RAOS_MEASUREMENT_ENABLED",
            "package_sha256": sha256(package),
            "package_size": len(package),
            "plugin_files": [
                {"path": path, "size": len(payload), "sha256": sha256(payload)}
                for path, payload in sorted(payloads.items())
            ],
            "runtime_files": runtime,
        },
        allowlist_payload,
        package,
    )


def registry_payload(package_sha256: str) -> bytes:
    try:
        current = json.loads(read_regular(REGISTRY).decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError):
        fail("EDITORIAL_MEASUREMENT_REGISTRY_INVALID")
    if (
        type(current) is not dict
        or current.get("schema") != "RAOS_WORDPRESS_REPO_PLUGIN_ARTIFACTS_V1"
        or type(current.get("artifacts")) is not list
    ):
        fail("EDITORIAL_MEASUREMENT_REGISTRY_INVALID")
    artifact = {
        "artifact_id": ARTIFACT_ID,
        "slug": PLUGIN_SLUG,
        "version": PLUGIN_VERSION,
        "package_sha256": package_sha256,
    }
    artifacts = [
        row
        for row in current["artifacts"]
        if type(row) is not dict or row.get("artifact_id") != ARTIFACT_ID
    ]
    artifacts.append(artifact)
    artifacts.sort(key=lambda row: str(row.get("artifact_id", "")))
    return canonical_json({"schema": current["schema"], "artifacts": artifacts})


def write_outputs(*, package: bool) -> None:
    manifest, allowlist, package_payload = generated_manifest()
    ALLOWLIST.parent.mkdir(parents=True, exist_ok=True)
    ALLOWLIST.write_bytes(allowlist)
    MANIFEST.write_bytes(canonical_json(manifest))
    REGISTRY.write_bytes(registry_payload(manifest["package_sha256"]))
    if package:
        PACKAGE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        PACKAGE.write_bytes(package_payload)
        PACKAGE.chmod(0o600)


def check_outputs() -> None:
    manifest, allowlist, _package = generated_manifest()
    if read_regular(ALLOWLIST) != allowlist:
        fail("EDITORIAL_MEASUREMENT_ALLOWLIST_DRIFT")
    if read_regular(MANIFEST) != canonical_json(manifest):
        fail("EDITORIAL_MEASUREMENT_MANIFEST_DRIFT")
    if read_regular(REGISTRY) != registry_payload(manifest["package_sha256"]):
        fail("EDITORIAL_MEASUREMENT_REGISTRY_DRIFT")


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--generate", action="store_true")
    group.add_argument("--check", action="store_true")
    group.add_argument("--package", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.check:
            check_outputs()
        else:
            write_outputs(package=arguments.package)
    except BuildFailure as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
