#!/usr/bin/env python3
"""Build the deterministic RAOS V2 successor specification and contracts.

The imported design package is an immutable, design-only source layer.  This
owner never executes the package's prompt and never performs network I/O.  Live
observations, when explicitly captured by the validator, are sanitized into a
tracked recorded input before this owner consumes them.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
from html import escape
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import stat
import sys
from typing import Any, Final, NoReturn

import yaml

try:
    from scripts.raos_build_core import atomic_write, canonical_json_bytes
    from scripts.validate_raos_v2_successor import (
        _read_local_evidence_file,
        _phase3_capture_observation,
        ValidationFailure,
        load_json_strict,
        load_yaml_strict,
        protected_path_changes,
        simulate_route_round_trip,
        verify_local_test_evidence,
        verify_phase3_external_state,
        verify_phase3_local_browser_evidence,
        verify_visual_review_evidence,
    )
except ModuleNotFoundError:  # direct ``python scripts/...`` execution
    from raos_build_core import atomic_write, canonical_json_bytes
    from validate_raos_v2_successor import (
        _read_local_evidence_file,
        _phase3_capture_observation,
        ValidationFailure,
        load_json_strict,
        load_yaml_strict,
        protected_path_changes,
        simulate_route_round_trip,
        verify_local_test_evidence,
        verify_phase3_external_state,
        verify_phase3_local_browser_evidence,
        verify_visual_review_evidence,
    )


ROOT: Final = Path(__file__).resolve().parents[1]
SOURCE_ROOT: Final = Path("changes/raos-v2/source-package/2.0.0-design")
RECORDED_INPUT_PATH: Final = Path(
    "changes/raos-v2/recorded-inputs/phase0-capture.v1.json"
)
PHASE0_VISUAL_EVIDENCE_PATH: Final = Path(
    "changes/raos-v2/recorded-inputs/phase0-visual-evidence.v1.json"
)
PHASE2_DATA_PATHS: Final = (
    Path("changes/raos-v2/phase-2/content/article-definitions.v2.yaml"),
    Path("changes/raos-v2/phase-2/content/carry-on-comparison.v2.yaml"),
    Path("changes/raos-v2/phase-2/content/carry-on-rules-guide.v2.yaml"),
    Path("changes/raos-v2/phase-2/content/comparison-policy.v2.yaml"),
    Path("changes/raos-v2/phase-2/content/difference-template-fixture.v2.yaml"),
    Path("changes/raos-v2/phase-2/data/ace-carry-on-models.v2.json"),
    Path("changes/raos-v2/phase-2/editorial/editorial-decisions.v2.yaml"),
    Path("changes/raos-v2/phase-2/events/event-catalog.v2.yaml"),
    Path("changes/raos-v2/phase-2/fixtures/negative-product-identity.v2.json"),
    Path("changes/raos-v2/phase-2/fixtures/recorded-airline-rules.v2.json"),
    Path(
        "changes/raos-v2/phase-2/fixtures/recorded-rakuten-item-search-2026-07-01.json"
    ),
    Path("changes/raos-v2/phase-2/media/media-policy.v2.yaml"),
    Path("changes/raos-v2/phase-2/reviews/review-packet.v2.yaml"),
    Path("changes/raos-v2/phase-2/rules/airline-rule-sets.v2.yaml"),
    Path("changes/raos-v2/phase-2/sources/source-registry.v2.yaml"),
)
PHASE2_PREVIEW_INPUT_PATHS: Final = (
    Path(
        "packages/web-ui/src/decision-support-v2/preview/checker-parity-cases.v2.json"
    ),
    Path("packages/web-ui/src/decision-support-v2/preview/pages.v2.json"),
    Path("packages/web-ui/src/decision-support-v2/preview/styles.css"),
    Path("packages/web-ui/src/decision-support-v2/preview/checker.js"),
    Path("packages/web-ui/src/decision-support-v2/preview/render_preview.py"),
)
PHASE3_WORDPRESS_SOURCE_PATHS: Final = (
    Path("packages/web-ui/src/decision-support-v2/wordpress/projection.py"),
    Path(
        "packages/web-ui/src/decision-support-v2/wordpress/plugin/"
        "raos-v2-decision-support/cutover-binding.v1.json"
    ),
    Path(
        "packages/web-ui/src/decision-support-v2/wordpress/plugin/"
        "raos-v2-decision-support/plugin-manifest.v1.json"
    ),
    Path(
        "packages/web-ui/src/decision-support-v2/wordpress/plugin/"
        "raos-v2-decision-support/raos-v2-decision-support.php"
    ),
    Path(
        "packages/web-ui/src/decision-support-v2/wordpress/plugin/"
        "raos-v2-decision-support/assets/decision-support.css"
    ),
)
PHASE2_RECORDED_EVIDENCE_PATHS: Final = (
    Path("changes/raos-v2/recorded-inputs/phase2-browser-evidence.v1.json"),
    Path("changes/raos-v2/recorded-inputs/phase2-local-test-evidence.v1.json"),
    Path("changes/raos-v2/recorded-inputs/phase2-visual-evidence.v1.json"),
)
PHASE3_EXTERNAL_STATE_PATH: Final = Path(
    "changes/raos-v2/phase-3/inputs/external-action-state.v1.yaml"
)
PHASE3_LOCAL_BROWSER_EVIDENCE_PATH: Final = Path(
    "changes/raos-v2/recorded-inputs/phase3-local-browser-evidence.v1.json"
)
PHASE3_PUBLIC_OBSERVATION_PATH: Final = Path(
    "changes/raos-v2/recorded-inputs/phase3/preaction-public-20260828-v1.json"
)
PHASE2_IMPLEMENTATION_PATHS: Final = (
    Path("packages/web-ui/src/decision-support-v2/checker.ts"),
    Path("packages/web-ui/src/decision-support-v2/contracts.ts"),
    Path("packages/web-ui/src/decision-support-v2/renderer.ts"),
    Path("python/raos/adapters/decision_support_v2/__init__.py"),
    Path("python/raos/adapters/decision_support_v2/errors.py"),
    Path("python/raos/adapters/decision_support_v2/local_events.py"),
    Path("python/raos/adapters/decision_support_v2/recorded_airline.py"),
    Path("python/raos/adapters/decision_support_v2/recorded_catalog.py"),
    Path("python/raos/adapters/decision_support_v2/recorded_rakuten.py"),
    Path("python/raos/adapters/decision_support_v2/strict_json.py"),
    Path("python/raos/adapters/decision_support_v2/wordpress_disabled.py"),
    Path("python/raos/adapters/decision_support_v2/wordpress_phase3_disabled.py"),
    Path("python/raos/application/decision_support_v2/__init__.py"),
    Path("python/raos/application/decision_support_v2/checker.py"),
    Path("python/raos/application/decision_support_v2/offer_lookup.py"),
    Path("python/raos/application/decision_support_v2/publication.py"),
    Path("python/raos/application/decision_support_v2/phase3_publication.py"),
    Path("python/raos/application/decision_support_v2/selection.py"),
    Path("python/raos/domain/decision_support_v2/__init__.py"),
    Path("python/raos/domain/decision_support_v2/business.py"),
    Path("python/raos/domain/decision_support_v2/content_quality.py"),
    Path("python/raos/domain/decision_support_v2/decision.py"),
    Path("python/raos/domain/decision_support_v2/events.py"),
    Path("python/raos/domain/decision_support_v2/freshness.py"),
    Path("python/raos/domain/decision_support_v2/media.py"),
    Path("python/raos/domain/decision_support_v2/models.py"),
    Path("python/raos/domain/decision_support_v2/publication.py"),
    Path("python/raos/domain/decision_support_v2/phase3_publication.py"),
    Path("python/raos/domain/decision_support_v2/selection.py"),
    Path("python/raos/ports/decision_support_v2/__init__.py"),
    Path("python/raos/ports/decision_support_v2/protocols.py"),
)
PHASE2_TEST_SOURCE_PATHS: Final = (
    Path("tests/raos_v2/browser-validation.mjs"),
    Path("tests/raos_v2/conftest.py"),
    Path("tests/raos_v2/phase3-local-validation.mjs"),
    Path("tests/raos_v2/phase3-public-adversarial.mjs"),
    Path("tests/raos_v2/phase3-public-validation.mjs"),
    Path("tests/raos_v2/phase3-wordpress-runtime.php"),
    Path("tests/raos_v2/test_adapters_recorded.py"),
    Path("tests/raos_v2/test_browser_contract.py"),
    Path("tests/raos_v2/test_content_quality.py"),
    Path("tests/raos_v2/test_contracts_phase1.py"),
    Path("tests/raos_v2/test_decision_engine.py"),
    Path("tests/raos_v2/test_events_privacy.py"),
    Path("tests/raos_v2/test_phase0_contracts.py"),
    Path("tests/raos_v2/test_phase3_artifacts.py"),
    Path("tests/raos_v2/test_phase3_browser_evidence.py"),
    Path("tests/raos_v2/test_phase3_execution_operator.py"),
    Path("tests/raos_v2/test_phase3_local_validation_contract.py"),
    Path("tests/raos_v2/test_phase3_php_runtime_contract.py"),
    Path("tests/raos_v2/test_phase3_public_browser_contract.py"),
    Path("tests/raos_v2/test_phase3_public_capture.py"),
    Path("tests/raos_v2/test_phase3_publication.py"),
    Path("tests/raos_v2/test_phase3_wordpress_projection.py"),
    Path("tests/raos_v2/test_publication_contract.py"),
    Path("tests/raos_v2/test_selection_contract.py"),
    Path("tests/raos_v2/test_source_import.py"),
    Path("tests/raos_v2/test_traceability_phase0_phase2.py"),
    Path("tests/raos_v2/test_ui_contracts.py"),
    Path("tests/raos_v2/test_ui_parity.py"),
    Path("tests/raos_v2/test_visual_contract.py"),
    Path("tests/raos_v2/ui-parity.mjs"),
    Path("tests/raos_v2/visual-validation.mjs"),
)
PHASE2_SOURCE_PATHS: Final = (
    *PHASE2_DATA_PATHS,
    *PHASE2_PREVIEW_INPUT_PATHS,
    *PHASE2_RECORDED_EVIDENCE_PATHS,
    *PHASE2_IMPLEMENTATION_PATHS,
    *PHASE2_TEST_SOURCE_PATHS,
)
PHASE3_SOURCE_PATHS: Final = (
    PHASE3_EXTERNAL_STATE_PATH,
    PHASE3_LOCAL_BROWSER_EVIDENCE_PATH,
    PHASE3_PUBLIC_OBSERVATION_PATH,
    *PHASE3_WORDPRESS_SOURCE_PATHS,
)
PHASE3_BROWSER_BOOTSTRAP_SOURCE_PATHS: Final = (
    PHASE3_EXTERNAL_STATE_PATH,
    *PHASE3_WORDPRESS_SOURCE_PATHS,
)
PHASE3_ARTIFACT_ROOT: Final = Path(
    "changes/raos-v2/phase-3/wordpress/artifact/raos-v2-decision-support"
)
PHASE3_OUTPUT_PATHS: Final = (
    Path("changes/raos-v2/phase-3/production-backup-export-runbook.md"),
    PHASE3_ARTIFACT_ROOT / "raos-v2-decision-support.php",
    PHASE3_ARTIFACT_ROOT / "assets/decision-support.css",
    PHASE3_ARTIFACT_ROOT / "cutover-binding.v1.json",
    PHASE3_ARTIFACT_ROOT / "plugin-manifest.v1.json",
    Path("changes/raos-v2/phase-3/preview/carry-on-suitcase-comparison/index.html"),
    Path("changes/raos-v2/phase-3/generated/post-content.html"),
    Path("changes/raos-v2/phase-3/generated/wordpress-update-candidate.v1.json"),
    Path("changes/raos-v2/phase-3/generated/review-candidate.v1.json"),
    Path("changes/raos-v2/phase-3/generated/human-review-request.v1.json"),
    Path("changes/raos-v2/phase-3/generated/wordpress-dry-run-status.v1.json"),
    Path("changes/raos-v2/phase-3/generated/seo-url-change-plan.v1.yaml"),
    Path("changes/raos-v2/phase-3/generated/privacy-legal-review-packet.v1.yaml"),
    Path("changes/raos-v2/phase-3/generated/rollback-rehearsal.v1.json"),
    Path("changes/raos-v2/phase-3/generated/external-action-evidence-template.v1.yaml"),
    Path("changes/raos-v2/phase-3/generated/phase-3-validation.v1.json"),
    Path("changes/raos-v2/phase-3/phase-3-preparation-report.md"),
    Path("changes/raos-v2/phase-3/integration-pr-body.md"),
    Path("contracts/raos-v2/v2/human-review-receipt.schema.json"),
    Path("contracts/raos-v2/v2/publication-package.schema.json"),
    Path("contracts/raos-v2/v2/wordpress-update-payload.schema.json"),
    Path("contracts/raos-v2/v2/wordpress-dry-run-receipt.schema.json"),
    Path("contracts/raos-v2/v2/wordpress-export-binding.schema.json"),
    Path("contracts/raos-v2/v2/preaction-binding.schema.json"),
    Path("contracts/raos-v2/v2/public-verification-receipt.schema.json"),
    Path("contracts/raos-v2/v2/public-browser-verification-receipt.schema.json"),
    Path("contracts/raos-v2/v2/reissued-review-bundle.schema.json"),
    Path("contracts/raos-v2/v2/wordpress-cutover-binding.schema.json"),
)
PHASE3_BROWSER_BOOTSTRAP_OUTPUT_PATHS: Final = (
    PHASE3_ARTIFACT_ROOT / "raos-v2-decision-support.php",
    PHASE3_ARTIFACT_ROOT / "assets/decision-support.css",
    PHASE3_ARTIFACT_ROOT / "cutover-binding.v1.json",
    PHASE3_ARTIFACT_ROOT / "plugin-manifest.v1.json",
    Path("changes/raos-v2/phase-3/generated/post-content.html"),
    Path("changes/raos-v2/phase-3/preview/carry-on-suitcase-comparison/index.html"),
)
SOURCE_PATHS: Final = (
    Path("changes/raos-v2/source-package/2.0.0-design/00_EXECUTIVE_DECISIONS.md"),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/01_CURRENT_STATE_AND_RESEARCH.md"
    ),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/02_PRODUCT_BRAND_CATEGORY_STRATEGY.md"
    ),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/03_CONTENT_SEO_EDITORIAL_SYSTEM.md"
    ),
    Path("changes/raos-v2/source-package/2.0.0-design/04_UX_DESIGN_SYSTEM.md"),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/05_TECHNICAL_DATA_ANALYTICS_ARCHITECTURE.md"
    ),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/06_MIGRATION_ROADMAP_AND_BACKLOG.md"
    ),
    Path("changes/raos-v2/source-package/2.0.0-design/07_DECISION_TRACEABILITY.yaml"),
    Path("changes/raos-v2/source-package/2.0.0-design/08_TEST_AND_ACCEPTANCE_PLAN.md"),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/09_EVIDENCE_AND_SOURCE_REGISTER.yaml"
    ),
    Path("changes/raos-v2/source-package/2.0.0-design/10_INTERFACE_CONTRACTS.yaml"),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/11_EXTERNAL_ACTIONS_REGISTER.yaml"
    ),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/12_INDEPENDENT_QUALITY_REVIEW.md"
    ),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/CONTROL/implementation_contract.yaml"
    ),
    Path("changes/raos-v2/source-package/2.0.0-design/CONTROL/package_validation.json"),
    Path("changes/raos-v2/source-package/2.0.0-design/CONTROL/source_integrity.json"),
    Path("changes/raos-v2/source-package/2.0.0-design/MANIFEST.sha256"),
    Path("changes/raos-v2/source-package/2.0.0-design/README.md"),
    Path("changes/raos-v2/source-package/2.0.0-design/package_manifest.json"),
    RECORDED_INPUT_PATH,
    PHASE0_VISUAL_EVIDENCE_PATH,
    *PHASE2_SOURCE_PATHS,
    *PHASE3_SOURCE_PATHS,
    Path("scripts/build_raos_v2_successor.py"),
    Path("scripts/raos_v2_phase3_execution.py"),
    Path("scripts/raos_build_core.py"),
    Path("scripts/validate_raos_v2_successor.py"),
)
OUTPUT_PATHS: Final = (
    Path("changes/raos-v2/source-import.v1.json"),
    Path("changes/raos-v2/clarifications.v1.yaml"),
    Path("changes/raos-v2/phase-0/preflight-report.json"),
    Path("changes/raos-v2/phase-0/source-audit-report.json"),
    Path("changes/raos-v2/phase-0/public-url-inventory.yaml"),
    Path("changes/raos-v2/phase-0/production-observation-plan.md"),
    Path("changes/raos-v2/phase-0/metric-dictionary.yaml"),
    Path("changes/raos-v2/phase-0/deprecation-ledger.yaml"),
    Path("changes/raos-v2/phase-0/pilot-reconciliation.yaml"),
    Path("changes/raos-v2/phase-0/rollback-contract.yaml"),
    Path("changes/raos-v2/phase-0/phase-0-report.md"),
    Path("changes/raos-v2/product-spec.v2.yaml"),
    Path("changes/raos-v2/route-registry.v2.yaml"),
    Path("changes/raos-v2/design/design-tokens.v2.json"),
    Path("changes/raos-v2/design/component-states.yaml"),
    Path("changes/raos-v2/generated/decision-traceability.effective.v1.yaml"),
    Path("changes/raos-v2/generated/phase-1-validation.v1.json"),
    Path("changes/raos-v2/phase-1-report.md"),
    Path("contracts/raos-v2/v1/source-record.schema.json"),
    Path("contracts/raos-v2/v1/claim.schema.json"),
    Path("contracts/raos-v2/v1/product-model.schema.json"),
    Path("contracts/raos-v2/v1/product-variant.schema.json"),
    Path("contracts/raos-v2/v1/offer-observation.schema.json"),
    Path("contracts/raos-v2/v1/airline-rule-set.schema.json"),
    Path("contracts/raos-v2/v1/article-definition.schema.json"),
    Path("contracts/raos-v2/v1/editorial-decision.schema.json"),
    Path("contracts/raos-v2/v1/publication-package.schema.json"),
    Path("contracts/raos-v2/v1/analytics-event.schema.json"),
    Path("contracts/raos-v2/v1/ports.v1.yaml"),
    Path("changes/raos-v2/phase-2/claims/claim-ledger.v2.yaml"),
    Path("changes/raos-v2/phase-2/generated/migration-manifest.v2.yaml"),
    Path("changes/raos-v2/phase-2/generated/publication-candidate.v2.json"),
    Path("changes/raos-v2/phase-2/generated/synthetic-seal-receipt.v2.json"),
    Path("changes/raos-v2/phase-2/generated/sitemap-candidates.v2.yaml"),
    Path("changes/raos-v2/phase-2/generated/phase-2-validation.v2.json"),
    Path("changes/raos-v2/phase-2/generated/local-evidence-bundle.v2.json"),
    Path("changes/raos-v2/phase-2/phase-2-report.md"),
    Path("changes/raos-v2/phase-2/integration-pr-body.md"),
    Path("changes/raos-v2/phase-2/preview/index.html"),
    Path("changes/raos-v2/phase-2/preview/carry-on/index.html"),
    Path("changes/raos-v2/phase-2/preview/tools/carry-on-size-checker/index.html"),
    Path("changes/raos-v2/phase-2/preview/guides/carry-on-baggage-rules/index.html"),
    Path(
        "changes/raos-v2/phase-2/preview/guides/low-cost-carrier-7kg-packing/index.html"
    ),
    Path("changes/raos-v2/phase-2/preview/carry-on-suitcase-comparison/index.html"),
    Path("changes/raos-v2/phase-2/preview/guides/carry-on-bag-measurement/index.html"),
    Path(
        "changes/raos-v2/phase-2/preview/policy/how-we-compare-carry-on-products/index.html"
    ),
    Path(
        "changes/raos-v2/phase-2/preview/differences/ace-cresta-vs-difference-vs-maxpass4/index.html"
    ),
    *PHASE3_OUTPUT_PATHS,
)
TEST_PATHS: Final = (Path("tests/raos_v2"),)

PACKAGE_SHA256: Final = (
    "7ea856e74d73589ae37d1248e08e685e5d022b90bfc45c9bf1d6cb414b5fc42a"
)
IMMUTABLE_BASE_HEAD: Final = "ae92eb8f50e9d439c1c292cc6c76d5a9c50f85c7"
SOURCE_MANIFEST_SHA256: Final = (
    "db9dc42bebd84090b18103cc9a48a6098f9d890af3f52b93cc33a6d52f821a44"
)
PROMPT_PATH: Final = "CODEX_MASTER_IMPLEMENTATION_PROMPT.md"
PROMPT_SHA256: Final = (
    "a122782725efb57b9fbaa7c916e821252736c0556c993b15604872f2a424f54f"
)
PROMPT_BYTES: Final = 22093
SOURCE_PACKAGE_GENERATED_AT: Final = "2026-08-28T22:30:00+09:00"
SCHEMA_URI_ROOT: Final = "https://kurashinoshirube.com/contracts/raos-v2/v1"
BROWSER_EVIDENCE_INPUT_PATH: Final = PHASE2_RECORDED_EVIDENCE_PATHS[0]
LOCAL_TEST_EVIDENCE_INPUT_PATH: Final = PHASE2_RECORDED_EVIDENCE_PATHS[1]
VISUAL_EVIDENCE_INPUT_PATH: Final = PHASE2_RECORDED_EVIDENCE_PATHS[2]


class BuildFailure(RuntimeError):
    """A sanitized, deterministic successor build failure."""


def fail(code: str) -> NoReturn:
    raise BuildFailure(code) from None


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def semantic_json_sha256(value: Mapping[str, object]) -> str:
    """Match the domain semantic-digest contract for closed mappings."""

    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(payload)


def exact_file_set_sha256(paths: Sequence[Path]) -> str:
    """Bind every byte and filename in a small semantic input set."""

    rows: list[dict[str, object]] = []
    for path in paths:
        try:
            payload = (ROOT / path).read_bytes()
        except OSError:
            fail("RAOS_V2_PUBLICATION_INPUT_MISSING")
        rows.append(
            {
                "path": path.as_posix(),
                "bytes": len(payload),
                "sha256": sha256(payload),
            }
        )
    return sha256(canonical_json_bytes({"files": rows}))


class _NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: object) -> bool:
        return True


def yaml_bytes(value: object) -> bytes:
    return yaml.dump(
        value,
        Dumper=_NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=100,
    ).encode("utf-8")


def _read_json(path: Path) -> Any:
    try:
        return load_json_strict((ROOT / path).read_bytes())
    except OSError, ValidationFailure:
        fail("RAOS_V2_SOURCE_JSON_INVALID")


def _read_yaml(path: Path) -> Any:
    try:
        return load_yaml_strict((ROOT / path).read_bytes())
    except OSError, ValidationFailure:
        fail("RAOS_V2_SOURCE_YAML_INVALID")


def _manifest_hashes() -> dict[str, str]:
    path = ROOT / SOURCE_ROOT / "MANIFEST.sha256"
    result: dict[str, str] = {}
    try:
        payload = path.read_bytes()
        if sha256(payload) != SOURCE_MANIFEST_SHA256:
            fail("RAOS_V2_SOURCE_MANIFEST_ANCHOR_MISMATCH")
        lines = payload.decode("utf-8").splitlines()
    except OSError, UnicodeError:
        fail("RAOS_V2_SOURCE_MANIFEST_INVALID")
    for line in lines:
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64 or parts[1] in result:
            fail("RAOS_V2_SOURCE_MANIFEST_INVALID")
        result[parts[1]] = parts[0]
    return result


def source_import_document(capture: Mapping[str, object]) -> dict[str, object]:
    manifest = _manifest_hashes()
    imported: list[dict[str, object]] = []
    expected_paths = {
        path.relative_to(SOURCE_ROOT).as_posix()
        for path in SOURCE_PATHS
        if path.is_relative_to(SOURCE_ROOT)
    }
    if PROMPT_PATH in expected_paths or PROMPT_PATH not in manifest:
        fail("RAOS_V2_PROMPT_BOUNDARY_INVALID")
    for relative in sorted(expected_paths):
        path = ROOT / SOURCE_ROOT / relative
        try:
            payload = path.read_bytes()
        except OSError:
            fail("RAOS_V2_SOURCE_FILE_MISSING")
        expected_hash = manifest.get(relative)
        if relative == "MANIFEST.sha256":
            expected_hash = sha256(payload)
        if expected_hash is None or sha256(payload) != expected_hash:
            fail("RAOS_V2_SOURCE_FILE_HASH_MISMATCH")
        imported.append(
            {"path": relative, "bytes": len(payload), "sha256": sha256(payload)}
        )
    package_manifest = _read_json(SOURCE_ROOT / "package_manifest.json")
    if not isinstance(package_manifest, dict):
        fail("RAOS_V2_PACKAGE_MANIFEST_INVALID")
    prompt_row = next(
        (
            row
            for row in package_manifest.get("files", [])
            if isinstance(row, dict) and row.get("path") == PROMPT_PATH
        ),
        None,
    )
    if prompt_row != {
        "path": PROMPT_PATH,
        "sha256": PROMPT_SHA256,
        "size_bytes": PROMPT_BYTES,
    }:
        fail("RAOS_V2_PROMPT_RECEIPT_INVALID")
    return {
        "schema": "RAOS_V2_SOURCE_IMPORT_V1",
        "source_layer": "IMMUTABLE_SUCCESSOR_DESIGN_SOURCE",
        "package_sha256": PACKAGE_SHA256,
        "package_version": "2.0.0-design",
        "source_package_generated_at": SOURCE_PACKAGE_GENERATED_AT,
        "import_observed_at": capture.get("captured_at"),
        "imported_files": imported,
        "excluded_files": [
            {
                "path": PROMPT_PATH,
                "bytes": PROMPT_BYTES,
                "sha256": PROMPT_SHA256,
                "reason": "PROMPT_IS_DATA_NOT_EXECUTABLE_AUTHORITY",
            }
        ],
        "rules": {
            "source_files_mutable": False,
            "clarifications_are_separate_overlay": True,
            "external_actions_authorized": False,
        },
    }


def clarifications_document() -> dict[str, object]:
    return {
        "schema": "RAOS_V2_CLARIFICATIONS_V1",
        "version": "1.0.0",
        "authority": "USER_PLAN_AND_REPOSITORY_POLICY_OVER_DESIGN_SOURCE",
        "source_package_sha256": PACKAGE_SHA256,
        "clarifications": [
            {
                "id": "C-V2-001",
                "decision": "successor source layer lives below changes/raos-v2",
                "supersedes": "any source suggestion to mutate canonical/upstream/zip",
            },
            {
                "id": "C-V2-002",
                "decision": "the machine contract has seven templates",
                "value": [
                    "HOME",
                    "HUB",
                    "GUIDE",
                    "COMPARISON",
                    "DIFFERENCE",
                    "TOOL",
                    "POLICY",
                ],
                "supersedes": "prose references to six templates",
            },
            {
                "id": "C-V2-003",
                "decision": "Phase 0 owns T-V2-001..006, T-V2-040 and T-V2-051; T-V2-007 starts Phase 1",
            },
            {
                "id": "C-V2-004",
                "decision": "effective phase planning ceilings are P0=16h, P1=40h and P2=80h",
                "note": "backlog row sums are reconciliation information, not additive gates",
            },
            {
                "id": "C-V2-005",
                "decision": "B-V2-009 depends on every B-V2-001..008 artifact",
            },
            {
                "id": "C-V2-006",
                "decision": "ArticleDefinition requires ordered blocks and temporal source fields are mandatory",
            },
            {
                "id": "C-V2-007",
                "decision": "Phase 0-2 real content cannot be human-reviewed or sealed; only synthetic fixtures may reach PACKAGE_SEALED",
            },
            {
                "id": "C-V2-008",
                "decision": "B-V2-017 defines the WordPress port; its disabled adapter is Phase 2",
            },
            {
                "id": "C-V2-009",
                "decision": "T-V2-027 route collisions fail closed",
            },
            {
                "id": "C-V2-010",
                "decision": "B-V2-031 also waits B-V2-030; B-V2-033 waits B-V2-027/B-V2-029/B-V2-030; B-V2-034 waits B-V2-019..033",
            },
            {
                "id": "C-V2-011",
                "decision": "airline rules without a published effective date use a null effective_from plus observed_applicable_from and OBSERVED_CURRENT_AT_CAPTURE_NO_PUBLISHED_EFFECTIVE_DATE; only an official date may use OFFICIAL_EFFECTIVE_DATE",
            },
            {
                "id": "C-V2-012",
                "decision": "airline effective intervals are machine-defined as FROM_INCLUSIVE_TO_EXCLUSIVE",
            },
            {
                "id": "C-V2-013",
                "decision": "packages/web-ui/src/decision-support-v2 is the authoritative UI source; its preview subtree is the sole deterministic preview input and changes/raos-v2/phase-2/preview contains generated output only",
                "supersedes": "the former duplicated changes/raos-v2/phase-2/ui-source input location",
            },
            {
                "id": "C-V2-014",
                "decision": "the effective Phase 3 planning ceiling is 20 hours and external spend remains JPY 0",
                "note": "Phase 3 backlog row estimates are reconciliation information, not an additive budget gate",
            },
            {
                "id": "C-V2-015",
                "decision": "Phase 3 adds a v2 real-content local simulation-seal contract for an exact non-synthetic but unauthenticated owner assertion; the Phase 2 v1 synthetic-only seal remains unchanged and neither contract grants production approval authority",
            },
            {
                "id": "C-V2-016",
                "decision": "the one-URL WordPress projection suppresses every unpublished future route and keeps every product CTA blocked until a current exact offer binding exists",
            },
            {
                "id": "C-V2-017",
                "decision": "B-V2-040 remains BLOCKED_EXTERNAL until human backup, review, deployment, WordPress write, publication, public verification, rollback evidence and seven stable days exist",
            },
            {
                "id": "C-V2-018",
                "decision": "the safe Phase 3 default preserves /carry-on-suitcase-comparison/, its self-canonical and sitemap membership with an empty redirect change set",
            },
            {
                "id": "C-V2-019",
                "decision": "B-V2-036 uses a marker-bound one-route WordPress block-presentation plugin instead of switching the active theme",
                "rationale": "the one-URL migration must not restyle or risk unrelated public pages and remains reversible by removing one local artifact",
            },
            {
                "id": "C-V2-020",
                "decision": "the existing published A05 route uses an approved-cutover update contract whose precondition and postcondition both require post_status=publish; no Phase 3 review payload may demote it to draft",
                "supersedes": "draft wording that could be interpreted as applying post_status=draft to the existing public post",
            },
            {
                "id": "C-V2-021",
                "decision": "each Phase 3 claim type, risk class, freshness and authoritative source status is closed by the Phase 2 candidate phase3_claim_authority digest before human review or seal",
            },
            {
                "id": "C-V2-022",
                "decision": "Phase 3 local test execution and external acceptance are reported separately; local evidence never marks an external-dependent Phase 3 acceptance complete",
            },
            {
                "id": "C-V2-023",
                "decision": "Phase 3 external-state input is a closed sanitized object at every nesting level and rejects unknown or secret-like fields",
            },
            {
                "id": "C-V2-024",
                "decision": "the Phase 3 post-action WordPress owner export uses overlay action ID V2-P3-EXT-POSTACTION-EXPORT; source EXT-014 remains reserved for destructive repository deletion",
                "supersedes": "the conflicting Phase 3 use of EXT-014",
            },
            {
                "id": "C-V2-025",
                "decision": "the route-scoped presentation plugin may be activated only with an owner-armed cutover binding; it passes through only the exact bound legacy post bytes, projects only the exact bound sealed post bytes, and fails closed for disabled, missing, malformed, intermediate or drifted target content",
                "rationale": "the two-step cutover keeps the existing article byte-exact before the approved content write while preventing an unbound activation or partial content update from rendering an ambiguous public state",
                "supersedes": "the v0.4 complete-pass-through wording that allowed activation without an armed owner binding",
            },
            {
                "id": "C-V2-026",
                "decision": "the 2026-08-28 bounded public read is a sanitized unpaired observation only and has no pre-action, review, seal or publication acceptance authority",
                "rationale": "no owner-held WordPress export was captured within the required five-minute pairing window",
            },
            {
                "id": "C-V2-027",
                "decision": "the fixed-target public browser recorder emits owner-held raw evidence with acceptance_authority=false; only a separately implemented independent recalculation may create an acceptance receipt",
            },
            {
                "id": "C-V2-028",
                "decision": "source and generated Phase 3 plugins require PHP lint and a fail-closed WordPress stub in required CI; those results remain local CI evidence and do not prove production WordPress compatibility",
            },
            {
                "id": "C-V2-029",
                "decision": "an unsigned Phase 3 review receipt is an unauthenticated owner assertion and may create only a local simulation package; it has no human-approval acceptance authority and cannot satisfy B-V2-040 or the Phase 3 exit gate",
                "rationale": "reviewer_id plus caller-authored digests do not authenticate a human principal or an immutable artifact-specific decision",
            },
            {
                "id": "C-V2-030",
                "decision": "an ARMED WordPress cutover binding remains unavailable until a trusted artifact-specific approval verifier and fresh PRE_WRITE_EXPORT plus disabled dry-run verifier are implemented and bound; the repository-owned binding remains DEPLOYMENT_DISABLED",
                "rationale": "preaction evidence and a simulation seal alone cannot enforce the final pre-write gate or authorize a production cutover",
            },
            {
                "id": "C-V2-031",
                "decision": "the unauthenticated simulation receipt persists only fixed non-personal reviewer_id=OWNER_ASSERTION_LOCAL and review_version=P3-OWNER-ASSERTION-V1; arbitrary external identity strings are rejected",
                "rationale": "the local assertion has no approval authority, so retaining a person-identifying or caller-selected identity creates privacy risk without evidentiary value",
            },
        ],
    }


def _capture_input() -> dict[str, object]:
    value = _read_json(RECORDED_INPUT_PATH)
    repository = value.get("repository") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or value.get("schema") != "RAOS_V2_PHASE0_CAPTURE_V1"
        or not isinstance(repository, dict)
        or repository.get("head") != IMMUTABLE_BASE_HEAD
        or protected_path_changes(IMMUTABLE_BASE_HEAD, root=ROOT)
    ):
        fail("RAOS_V2_CAPTURE_INPUT_INVALID")
    return value


def phase3_external_state() -> dict[str, object]:
    """Load the sanitized, deny-by-default Phase 3 human/external state."""

    value = _read_yaml(PHASE3_EXTERNAL_STATE_PATH)
    if not isinstance(value, dict):
        fail("RAOS_V2_PHASE3_EXTERNAL_STATE_INVALID")
    try:
        verify_phase3_external_state(value)
    except ValidationFailure:
        fail("RAOS_V2_PHASE3_EXTERNAL_STATE_INVALID")
    return deepcopy(value)


def phase3_external_status(state: Mapping[str, object], name: str) -> str:
    section = state.get(name)
    status = section.get("status") if isinstance(section, Mapping) else None
    if not isinstance(status, str):
        fail("RAOS_V2_PHASE3_EXTERNAL_STATE_INVALID")
    return status


def preflight_document(capture: Mapping[str, object]) -> dict[str, object]:
    repository = capture.get("repository")
    if not isinstance(repository, dict):
        fail("RAOS_V2_CAPTURE_REPOSITORY_INVALID")
    if repository.get("head") != IMMUTABLE_BASE_HEAD:
        fail("RAOS_V2_CAPTURE_REPOSITORY_INVALID")
    return {
        "schema": "RAOS_V2_PREFLIGHT_REPORT_V1",
        "captured_at": capture.get("captured_at"),
        "repository": repository,
        "immutable_base_head": IMMUTABLE_BASE_HEAD,
        "package": {
            "sha256": PACKAGE_SHA256,
            "source_import": "changes/raos-v2/source-import.v1.json",
            "prompt_executed": False,
        },
        "boundaries": {
            "immutable_paths": ["docs/canonical/**", "docs/upstream/**", "zip/**"],
            "external_actions": "NOT_EXECUTED",
            "public_observation": capture.get("public_observation_status"),
            "local_evidence_label": "PASSED_LOCAL",
            "generator_owner": "scripts/build_raos_v2_successor.py",
        },
        "backlog_id": "B-V2-001",
        "test_ids": ["T-V2-001", "T-V2-002", "T-V2-003", "T-V2-051"],
    }


def source_audit_document() -> dict[str, object]:
    trace = _read_yaml(SOURCE_ROOT / "07_DECISION_TRACEABILITY.yaml")
    interfaces = _read_yaml(SOURCE_ROOT / "10_INTERFACE_CONTRACTS.yaml")
    if not isinstance(trace, dict) or not isinstance(interfaces, dict):
        fail("RAOS_V2_SOURCE_MACHINE_DOCUMENT_INVALID")
    counts = {
        key: len(trace.get(key, []))
        for key in ("decisions", "requirements", "backlog", "tests")
    }
    if counts != {"decisions": 34, "requirements": 36, "backlog": 49, "tests": 51}:
        fail("RAOS_V2_SOURCE_TRACEABILITY_COUNT_MISMATCH")
    return {
        "schema": "RAOS_V2_SOURCE_AUDIT_REPORT_V1",
        "status": "PASSED_LOCAL",
        "source_package_sha256": PACKAGE_SHA256,
        "source_layer_file_count": 19,
        "excluded_prompt_count": 1,
        "traceability_counts": counts,
        "interface_entities": sorted(interfaces.get("entities", {})),
        "interface_ports": sorted(interfaces.get("ports", {})),
        "interpretation": "DESIGN_INPUT_NOT_EXECUTABLE_INSTRUCTIONS",
        "freshness": "REVALIDATE_EXTERNAL_FACTS_BEFORE_PUBLICATION",
        "backlog_id": "B-V2-002",
        "test_ids": ["T-V2-002", "T-V2-003"],
    }


def _phase0_visual_evidence() -> dict[str, object]:
    value = _read_json(PHASE0_VISUAL_EVIDENCE_PATH)
    if (
        not isinstance(value, dict)
        or value.get("schema") != "RAOS_V2_RECORDED_PHASE0_VISUAL_EVIDENCE_V1"
        or value.get("evidence_class") != "PUBLIC_READ_ONLY_MANUAL_RECORDED"
        or value.get("raw_images") != "LOCAL_ONLY_NOT_TRACKED_NOT_REVERIFIED"
        or value.get("external_actions") != "NOT_EXECUTED"
    ):
        fail("RAOS_V2_PHASE0_VISUAL_EVIDENCE_INVALID")
    rows = value.get("screenshots")
    if not isinstance(rows, list) or len(rows) != 12:
        fail("RAOS_V2_PHASE0_VISUAL_EVIDENCE_INVALID")
    expected_paths = {
        "/",
        "/carry-on-suitcase-comparison/",
        "/portable-power-station-guide/",
        "/anker-solix-c300-c800-c1000-differences/",
    }
    expected_viewports = {"390x844", "768x1024", "1440x900"}
    observed_pairs: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "bytes",
            "path",
            "sha256",
            "viewport",
        }:
            fail("RAOS_V2_PHASE0_VISUAL_EVIDENCE_INVALID")
        path = row.get("path")
        viewport = row.get("viewport")
        byte_count = row.get("bytes")
        digest = row.get("sha256")
        if (
            path not in expected_paths
            or viewport not in expected_viewports
            or not isinstance(byte_count, int)
            or isinstance(byte_count, bool)
            or byte_count <= 0
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            fail("RAOS_V2_PHASE0_VISUAL_EVIDENCE_INVALID")
        observed_pairs.add((str(path), str(viewport)))
    if observed_pairs != {
        (path, viewport) for path in expected_paths for viewport in expected_viewports
    }:
        fail("RAOS_V2_PHASE0_VISUAL_EVIDENCE_INVALID")
    return value


def public_url_inventory(capture: Mapping[str, object]) -> dict[str, object]:
    observations = capture.get("public_urls")
    by_path: dict[str, object] = {}
    if isinstance(observations, list):
        by_path = {
            str(row.get("path")): row
            for row in observations
            if isinstance(row, dict) and isinstance(row.get("path"), str)
        }
    initial = [
        ("/", "KEEP_CURRENT", "home"),
        ("/carry-on-suitcase-comparison/", "MIGRATE_AFTER_VERTICAL_SLICE", "pilot"),
        ("/portable-power-station-guide/", "KEEP_CURRENT_DEFER_V2", "pilot"),
        (
            "/anker-solix-c300-c800-c1000-differences/",
            "KEEP_CURRENT_DEFER_V2",
            "pilot",
        ),
        (
            "/countertop-dishwasher-for-small-households/",
            "NO_ROUTE_OR_REDIRECT",
            "pilot",
        ),
        ("/compact-robot-vacuum-shortlist/", "NO_ROUTE_OR_REDIRECT", "pilot"),
        ("/about-ad-policy/", "KEEP_CURRENT", "policy"),
        ("/advertising-policy/", "NO_ROUTE_OR_REDIRECT", "observed_candidate"),
        ("/privacy-policy/", "KEEP_CURRENT", "policy"),
    ]
    rows: list[dict[str, object]] = []
    for path, disposition, role in initial:
        observation = by_path.get(path)
        if isinstance(observation, dict):
            observed = deepcopy(observation)
        else:
            observed = {
                "status": "UNAVAILABLE",
                "redirect_chain": [],
                "canonical": "UNAVAILABLE",
                "robots": "UNAVAILABLE",
                "h1": "UNAVAILABLE",
                "sitemap_membership": "UNAVAILABLE",
                "body_sha256": "UNAVAILABLE",
                "observed_at": "UNAVAILABLE",
            }
        rows.append(
            {
                "url": f"https://kurashinoshirube.com{path}",
                "path": path,
                "role": role,
                "safe_initial_disposition": disposition,
                "observation": observed,
            }
        )
    supporting = capture.get("supporting_resources")
    visual_evidence = _phase0_visual_evidence()
    return {
        "schema": "RAOS_V2_PUBLIC_URL_INVENTORY_V1",
        "evidence_class": capture.get("public_observation_status"),
        "capture_contract": {
            "scope": (
                supporting.get("capture_scope")
                if isinstance(supporting, dict)
                else "UNAVAILABLE"
            ),
            "maximum_urls": (
                supporting.get("maximum_capture_urls")
                if isinstance(supporting, dict)
                else "UNAVAILABLE"
            ),
            "unlisted_sitemap_urls_are_silently_dropped": False,
        },
        "automatic_public_mutation": False,
        "visual_baseline_evidence": {
            "source": PHASE0_VISUAL_EVIDENCE_PATH.as_posix(),
            "classification": visual_evidence.get("evidence_class"),
            "raw_images": visual_evidence.get("raw_images"),
            "capture_contract": visual_evidence.get("capture_contract"),
        },
        "visual_baseline": deepcopy(visual_evidence["screenshots"]),
        "urls": rows,
        "backlog_id": "B-V2-003",
        "test_ids": ["T-V2-004", "T-V2-005"],
    }


def metric_dictionary() -> dict[str, object]:
    rows = [
        (
            "QDS",
            "distinct eligible 30-minute sessions with tool result OR comparison/evidence followed by official-source or affiliate activation",
            "LOCAL_FIRST_PARTY_EVENTS",
            "EVENT_OBSERVED",
        ),
        (
            "NON_BRAND_ORGANIC_SESSIONS",
            "Search Console organic sessions excluding approved brand query set",
            "SEARCH_CONSOLE_EXPORT",
            "GSC_FINAL",
        ),
        (
            "NON_BRAND_IMPRESSIONS",
            "Search Console impressions excluding approved brand query set",
            "SEARCH_CONSOLE_EXPORT",
            "GSC_FINAL",
        ),
        (
            "NON_BRAND_QUERY_WIDTH",
            "count(distinct eligible non-brand queries)",
            "SEARCH_CONSOLE_EXPORT",
            "GSC_FINAL",
        ),
        (
            "AFFILIATE_OUTBOUND_CTR",
            "verified affiliate outbound activations / eligible decision sessions",
            "LOCAL_FIRST_PARTY_EVENTS",
            "EVENT_OBSERVED",
        ),
        (
            "CONFIRMED_EPC",
            "mature confirmed reward JPY / attributable verified outbound clicks",
            "SANITIZED_RAKUTEN_EXPORT",
            "CONFIRMED",
        ),
        (
            "CONFIRMED_RPM",
            "mature confirmed reward JPY / eligible sessions * 1000",
            "SANITIZED_RAKUTEN_EXPORT_AND_EVENTS",
            "CONFIRMED",
        ),
        (
            "CASH_CONTRIBUTION_PROFIT",
            "confirmed reward JPY - paid variable cash cost JPY",
            "FINANCE_LEDGER",
            "CONFIRMED",
        ),
        (
            "ECONOMIC_CONTRIBUTION_PROFIT",
            "confirmed reward JPY - variable cash cost JPY - human hours * internal hourly cost JPY",
            "FINANCE_AND_TIME_LEDGER",
            "CONFIRMED",
        ),
        (
            "MONTHLY_CONFIRMED_CONTRIBUTION_PROFIT",
            "monthly confirmed reward JPY - monthly variable cash cost JPY - monthly human hours * internal hourly cost JPY",
            "FINANCE_AND_TIME_LEDGER",
            "CONFIRMED",
        ),
        (
            "ARTICLE_PAYBACK_MONTHS",
            "article production economic cost / mature monthly article contribution",
            "ATTRIBUTION_AND_COST_LEDGER",
            "CONFIRMED",
        ),
        (
            "CATEGORY_PAYBACK_MONTHS",
            "category production and maintenance economic cost / mature monthly confirmed category contribution",
            "CATEGORY_ATTRIBUTION_AND_COST_LEDGER",
            "CONFIRMED",
        ),
        (
            "DIRECT_AND_RETURN_RATE",
            "eligible direct or returning sessions / eligible sessions",
            "LOCAL_FIRST_PARTY_EVENTS",
            "EVENT_OBSERVED",
        ),
        (
            "CORRECTION_RATE",
            "published corrections / reviewed published assets",
            "EDITORIAL_LEDGER",
            "HUMAN_REVIEWED",
        ),
        (
            "MAJOR_FACT_DEFECTS",
            "count of confirmed high-severity factual defects",
            "EDITORIAL_INCIDENT_LEDGER",
            "HUMAN_CONFIRMED",
        ),
        (
            "COMPLAINT_FIRST_RESPONSE_WITHIN_72H_RATE",
            "eligible complaints receiving a recorded first response within 72 hours / eligible complaints",
            "EDITORIAL_COMPLAINT_LEDGER",
            "HUMAN_CONFIRMED",
        ),
        (
            "STALE_EXPOSURE_RATE",
            "sessions exposed to overdue claims / eligible sessions",
            "FRESHNESS_AND_EVENT_LEDGER",
            "EVENT_OBSERVED",
        ),
        (
            "HUMAN_HOURS_PER_ARTICLE",
            "human logged production hours / completed articles",
            "TIME_LEDGER",
            "HUMAN_RECORDED",
        ),
        (
            "UPDATE_COST_PER_PAGE",
            "human update hours * internal hourly cost / updated pages",
            "TIME_LEDGER",
            "HUMAN_RECORDED",
        ),
    ]
    return {
        "schema": "RAOS_V2_METRIC_DICTIONARY_V1",
        "currency": "JPY",
        "timezone": "Asia/Tokyo",
        "rules": {
            "missing_value": "UNAVAILABLE",
            "missing_never_equals_zero": True,
            "pending_never_equals_confirmed": True,
            "unattributed_program_total_never_populates_article_reward": True,
        },
        "metrics": [
            {
                "id": identifier,
                "formula": formula,
                "source": source,
                "required_maturity": maturity,
                "current_value": "UNAVAILABLE",
                "unavailable_rule": "return UNAVAILABLE when any required numerator, denominator, maturity or attribution input is absent",
            }
            for identifier, formula, source, maturity in rows
        ],
        "backlog_id": "B-V2-005",
        "test_ids": ["T-V2-006"],
    }


def deprecation_ledger() -> dict[str, object]:
    keep_gate = "NO_DELETION_SUCCESSOR_REVIEW_REQUIRED"
    removal_gate = "MINIMUM_2_RELEASES_AND_30_DAYS_UNUSED_PLUS_HUMAN_APPROVAL"
    assets = [
        {
            "asset": "root development policy/build/generator ownership",
            "decision": "KEEP",
            "reason": "dirty protection, standard commands and one generated owner are implementation safety",
            "migration": "register V2 owner in the existing graph and retain root workflow",
            "deletion_gate": keep_gate,
        },
        {
            "asset": "docs/canonical docs/upstream and zip baselines",
            "decision": "KEEP",
            "reason": "immutable V1 evidence and authority cannot be rewritten by the successor",
            "migration": "read-only reference from changes/raos-v2 overlay",
            "deletion_gate": "NEVER_FROM_V2",
        },
        {
            "asset": "secret scan denied-network authz and public/internal isolation",
            "decision": "KEEP",
            "reason": "validated security boundaries remain necessary",
            "migration": "inherit as local tests and deny-default adapter policy",
            "deletion_gate": keep_gate,
        },
        {
            "asset": "publication operator journal and rollback concepts",
            "decision": "REWORK",
            "reason": "human gate, hash binding and rollback are valuable but the old breadth is excessive",
            "migration": "reduce to local package states, synthetic seal test and disabled dry-run port",
            "deletion_gate": removal_gate,
        },
        {
            "asset": "claim evidence and editorial domain",
            "decision": "REWORK",
            "reason": "purpose is retained while the generic type surface is too broad",
            "migration": "narrow to A_OFFICIAL_FACT D_EDITORIAL_JUDGEMENT and UNKNOWN",
            "deletion_gate": removal_gate,
        },
        {
            "asset": "Rakuten adapter",
            "decision": "REWORK",
            "reason": "exact identity and current provider constraints require a smaller boundary",
            "migration": "RECORDED_ONLY fixture first; live mode absent through Phase 2",
            "deletion_gate": removal_gate,
        },
        {
            "asset": "public WordPress theme and Yoast integration",
            "decision": "MIGRATE",
            "reason": "public URLs must survive while UX and IA change",
            "migration": "disabled adapter then one-URL-at-a-time human-gated migration",
            "deletion_gate": removal_gate,
        },
        {
            "asset": "published carry-on comparison article",
            "decision": "MIGRATE",
            "reason": "current search and reader-learning asset in the selected wedge",
            "migration": "preserve slug/canonical until a verified V2 replacement is approved",
            "deletion_gate": "NO_DELETE_SLUG_PRESERVING_REPLACEMENT_ONLY",
        },
        {
            "asset": "portable power Anker dishwasher and robot-vacuum assets",
            "decision": "DEFER",
            "reason": "outside the wedge with unresolved evidence/media/safety cost",
            "migration": "preserve current public state; re-score only after Phase 6 gate",
            "deletion_gate": removal_gate,
        },
        {
            "asset": "empty 家事 and 備え category UI",
            "decision": "RETIRE",
            "reason": "empty navigation harms trust and crawl quality",
            "migration": "remove only from successor navigation after URL inventory decision",
            "deletion_gate": removal_gate,
        },
        {
            "asset": "Next.js or headless public application",
            "decision": "DEFER",
            "reason": "would duplicate the retained WordPress renderer",
            "migration": "reconsider only after measured WordPress limits",
            "deletion_gate": keep_gate,
        },
        {
            "asset": "custom admin and review UI",
            "decision": "DEFER",
            "reason": "maintenance exceeds value at 25-page scale",
            "migration": "reconsider at 50 pages or measured admin friction over 4h/week",
            "deletion_gate": removal_gate,
        },
        {
            "asset": "advanced causal attribution rank provider and paid dashboard",
            "decision": "DEFER",
            "reason": "provider evidence and zero-spend constraints do not support it",
            "migration": "begin with GSC, first-party events and monthly sanitized reports",
            "deletion_gate": removal_gate,
        },
        {
            "asset": "automatic or partial publication",
            "decision": "RETIRE",
            "reason": "initial reader and production risk exceeds value",
            "migration": "remove capability; retain only explicit human-gated contracts",
            "deletion_gate": removal_gate,
        },
        {
            "asset": "general Postgres and object-storage persistence",
            "decision": "DEFER",
            "reason": "versioned JSON/YAML is sufficient at current scale",
            "migration": "reconsider after >10k records, measured latency or merge conflicts",
            "deletion_gate": keep_gate,
        },
    ]
    for row in assets:
        decision = str(row["decision"])
        row["usage_evidence"] = {
            "status": (
                "CURRENT_OR_REFERENCED"
                if decision in {"KEEP", "REWORK", "MIGRATE"}
                else "NOT_ADOPTED_IN_V2_CURRENT_USAGE_UNAVAILABLE"
            ),
            "source": "REPOSITORY_AND_PUBLIC_URL_INVENTORY",
            "verified_unused": False,
        }
        row["replacement"] = {
            "status": (
                "NOT_APPLICABLE_RETAINED"
                if decision == "KEEP"
                else (
                    "SAFE_DEFAULT_PRESERVE_OR_DO_NOT_INTRODUCE"
                    if decision == "DEFER"
                    else "SUCCESSOR_DEFINED"
                )
            ),
            "plan": row["migration"],
        }
        row["rollback"] = {
            "status": (
                "NOT_APPLICABLE_RETAINED" if decision == "KEEP" else "LOCAL_PLAN_ONLY"
            ),
            "plan": (
                "asset remains retained; no retirement rollback is applicable"
                if decision == "KEEP"
                else "restore the prior owner/configuration from version control and rerun focused contracts before any external action"
            ),
            "production_execution": "NOT_EXECUTED",
        }
        row["removal_readiness"] = (
            "BLOCKED_USAGE_NOT_VERIFIED_UNUSED"
            if decision == "RETIRE"
            else "NOT_REQUESTED"
        )
    document = {
        "schema": "RAOS_V2_DEPRECATION_LEDGER_V1",
        "automatic_deletion": False,
        "default_removal_gate": removal_gate,
        "retire_requires_verified_unused": True,
        "assets": assets,
        "backlog_id": "B-V2-006",
        "test_ids": ["T-V2-051"],
    }
    validate_deprecation_ledger_document(document)
    return document


def validate_deprecation_ledger_document(document: Mapping[str, object]) -> None:
    rows = document.get("assets")
    if (
        document.get("automatic_deletion") is not False
        or document.get("retire_requires_verified_unused") is not True
        or not isinstance(rows, list)
        or len(rows) != 15
    ):
        fail("RAOS_V2_DEPRECATION_LEDGER_INVALID")
    observed_assets: set[str] = set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("asset"), str)
            or not row["asset"]
            or row["asset"] in observed_assets
            or row.get("decision")
            not in {"KEEP", "REWORK", "MIGRATE", "RETIRE", "DEFER"}
            or not all(
                isinstance(row.get(key), dict)
                for key in ("usage_evidence", "replacement", "rollback")
            )
        ):
            fail("RAOS_V2_DEPRECATION_LEDGER_INVALID")
        observed_assets.add(str(row["asset"]))
        usage = row["usage_evidence"]
        replacement = row["replacement"]
        rollback = row["rollback"]
        assert isinstance(usage, dict)
        assert isinstance(replacement, dict)
        assert isinstance(rollback, dict)
        if (
            not isinstance(usage.get("status"), str)
            or not usage["status"]
            or not isinstance(usage.get("source"), str)
            or not usage["source"]
            or not isinstance(usage.get("verified_unused"), bool)
            or not isinstance(replacement.get("status"), str)
            or not replacement["status"]
            or not isinstance(replacement.get("plan"), str)
            or not replacement["plan"]
            or not isinstance(rollback.get("status"), str)
            or not rollback["status"]
            or not isinstance(rollback.get("plan"), str)
            or not rollback["plan"]
            or rollback.get("production_execution") != "NOT_EXECUTED"
            or not isinstance(row.get("deletion_gate"), str)
            or not row["deletion_gate"]
        ):
            fail("RAOS_V2_DEPRECATION_LEDGER_INVALID")
        if row.get("decision") == "RETIRE" and (
            usage.get("verified_unused") is not False
            or row.get("removal_readiness") != "BLOCKED_USAGE_NOT_VERIFIED_UNUSED"
        ):
            fail("RAOS_V2_DEPRECATION_LEDGER_INVALID")


def pilot_reconciliation(capture: Mapping[str, object]) -> dict[str, object]:
    observations = capture.get("public_urls")
    by_path = (
        {
            str(row.get("path")): row
            for row in observations
            if isinstance(row, dict) and isinstance(row.get("path"), str)
        }
        if isinstance(observations, list)
        else {}
    )

    def observed(path: str) -> dict[str, object]:
        value = by_path.get(path)
        if not isinstance(value, dict):
            fail("RAOS_V2_PILOT_OBSERVATION_MISSING")
        return {
            "status": value.get("status"),
            "canonical": value.get("canonical"),
            "sitemap_membership": value.get("sitemap_membership"),
            "body_sha256": value.get("body_sha256"),
            "observed_at": value.get("observed_at"),
            "evidence_class": capture.get("public_observation_status"),
        }

    return {
        "schema": "RAOS_V2_PILOT_RECONCILIATION_V1",
        "automatic_public_action": False,
        "articles": [
            {
                "article_id": "st1703-first-suitcase-comparison",
                "route": "/carry-on-suitcase-comparison/",
                "safe_action": "KEEP_PUBLIC_AND_MIGRATE",
                "observation": observed("/carry-on-suitcase-comparison/"),
            },
            {
                "article_id": "st1704-portable-power-station-guide",
                "route": "/portable-power-station-guide/",
                "safe_action": "KEEP_PUBLIC_DEFER_V2",
                "observation": observed("/portable-power-station-guide/"),
            },
            {
                "article_id": "st1704-anker-solix-c300-c800-c1000-differences",
                "route": "/anker-solix-c300-c800-c1000-differences/",
                "safe_action": "KEEP_PUBLIC_DEFER_V2",
                "observation": observed("/anker-solix-c300-c800-c1000-differences/"),
            },
            {
                "article_id": "st1704-countertop-dishwasher-for-small-households",
                "route": "/countertop-dishwasher-for-small-households/",
                "safe_action": "NO_NEW_ROUTE_NO_REDIRECT",
                "observation": observed("/countertop-dishwasher-for-small-households/"),
            },
            {
                "article_id": "st1704-compact-robot-vacuum-shortlist",
                "route": "/compact-robot-vacuum-shortlist/",
                "safe_action": "NO_NEW_ROUTE_NO_REDIRECT",
                "observation": observed("/compact-robot-vacuum-shortlist/"),
            },
        ],
        "backlog_id": "B-V2-007",
        "test_ids": ["T-V2-004", "T-V2-005", "T-V2-051"],
    }


def rollback_contract() -> dict[str, object]:
    round_trip = simulate_route_round_trip(
        (
            "/carry-on-suitcase-comparison/",
            200,
            "https://kurashinoshirube.com/carry-on-suitcase-comparison/",
            "index,follow",
        ),
        (
            "/carry-on-suitcase-comparison/",
            200,
            "https://kurashinoshirube.com/carry-on-suitcase-comparison/",
            "noindex,nofollow",
        ),
    )
    return {
        "schema": "RAOS_V2_ROLLBACK_CONTRACT_V1",
        "scope": "LOCAL_SIMULATION_ONLY",
        "production_backup": "NOT_EXECUTED",
        "production_restore": "NOT_EXECUTED",
        "public_mutation": "NOT_EXECUTED",
        "invariants": [
            "existing public URL remains unchanged through Phase 2",
            "redirect chain length is at most one hop",
            "redirect loops are rejected",
            "many unrelated sources cannot redirect to home",
            "rollback restores the exact prior route/canonical/robots tuple",
            "sealed-package round trip preserves every input hash",
        ],
        "simulation": {
            "states": [
                "BASELINE_CAPTURED",
                "CANDIDATE_RENDERED",
                "DIFF_VERIFIED",
                "ROLLBACK_SIMULATED",
            ],
            "result": "PASSED_LOCAL",
            "route_tuple_round_trip": round_trip,
            "redirect_rules": [],
        },
        "backlog_id": "B-V2-008",
        "test_ids": ["T-V2-005", "T-V2-040"],
    }


OBSERVATION_PLAN: Final = """# RAOS V2 production observation plan

Status: **NOT_EXECUTED**. This is a read-only plan, not permission to access an
admin surface or change production.

## Allowed public observation

- Credential- and cookie-free HTTPS GET/HEAD against `kurashinoshirube.com` only.
- Known public URLs and same-origin sitemap URLs, with a hard item/byte/time cap.
- Record status, one-hop redirect evidence, canonical, robots, one H1, sitemap
  membership, body SHA-256 and JST observation time. Never store the response body.
- Capture home and confirmed-public pilot reader surfaces at 390, 768 and 1440px.
  Policy pages receive metadata-only observation.

## Denied surfaces and actions

Admin/login/preview/private/query-bearing URLs, credentials, cookies, WordPress or
Yoast writes, plugin/theme changes, publication, deployment and provider writes are
denied. A changed live state never triggers delete, unpublish, noindex or redirect.

## Human/external boundary

WordPress inventory, backup/restore, deployment, credentials and production
analytics configuration remain `NOT_EXECUTED` until separately authorized. Local
fixtures and rollback simulation may be executed and labelled `PASSED_LOCAL`.

Backlog: B-V2-004. Tests: T-V2-004, T-V2-005, T-V2-039.
"""


PHASE0_REPORT: Final = """# RAOS V2 Phase 0 report

Phase 0's nine artifacts are generated from the checksum-bound successor source
layer and a sanitized recorded capture. B-V2-001 through B-V2-008 are terminal
before this B-V2-009 report is emitted.

| Boundary | Result |
|---|---|
| Source package/import integrity | PASSED_LOCAL |
| Attached ZIP container | PASSED_LOCAL when local attachment is present; CI may skip only this container check while committed 19-file manifest/hash checks remain mandatory |
| Strict JSON/YAML/schema/traceability checks | PASSED_LOCAL |
| Local rollback simulation | PASSED_LOCAL |
| Public read-only observation | See `public-url-inventory.yaml`; unavailable fields remain `UNAVAILABLE` |
| Production backup/restore/write | NOT_EXECUTED |
| Deployment/publication/credentials/spend | NOT_EXECUTED |

Safe defaults keep current public surfaces unchanged, migrate only the existing
carry-on comparison after a verified vertical slice, defer the power articles,
and create no routes or redirects for the expected dishwasher/robot-vacuum 404s.

Effective planning ceiling: 16 hours. Backlog row estimates are reconciliation
information and are not additive stop gates. External spend ceiling: JPY 0.

Backlog: B-V2-009. Tests: T-V2-001..006, T-V2-040, T-V2-051.
"""


PORTFOLIO: Final = (
    ("A01", "/carry-on/", "機内持ち込み荷物の条件から選ぶ", "HUB", "RULE", 1),
    (
        "A02",
        "/tools/carry-on-size-checker/",
        "機内持ち込みサイズ・重量チェッカー",
        "TOOL",
        "DECISION",
        1,
    ),
    (
        "A03",
        "/guides/carry-on-baggage-rules/",
        "機内持ち込み手荷物の基本ルール",
        "GUIDE",
        "RULE",
        1,
    ),
    (
        "A04",
        "/guides/low-cost-carrier-7kg-packing/",
        "LCC 7kg以内に収める考え方",
        "GUIDE",
        "TASK",
        1,
    ),
    (
        "A05",
        "/carry-on-suitcase-comparison/",
        "機内持ち込みスーツケース3モデル条件別比較",
        "COMPARISON",
        "PRODUCT",
        1,
    ),
    (
        "A06",
        "/guides/carry-on-bag-measurement/",
        "キャスター・持ち手込みで測る方法",
        "GUIDE",
        "HOW_TO",
        1,
    ),
    (
        "A07",
        "/guides/domestic-airline-carry-on-size/",
        "国内線100席以上・未満のサイズ差",
        "GUIDE",
        "RULE",
        2,
    ),
    (
        "A08",
        "/guides/ana-carry-on-baggage/",
        "ANAの機内持ち込み条件",
        "GUIDE",
        "RULE",
        2,
    ),
    (
        "A09",
        "/guides/jal-carry-on-baggage/",
        "JALの機内持ち込み条件",
        "GUIDE",
        "RULE",
        2,
    ),
    (
        "A10",
        "/guides/peach-carry-on-baggage/",
        "Peachの機内持ち込み条件",
        "GUIDE",
        "RULE",
        2,
    ),
    (
        "A11",
        "/guides/jetstar-carry-on-baggage/",
        "Jetstarの機内持ち込み条件",
        "GUIDE",
        "RULE",
        2,
    ),
    (
        "A12",
        "/guides/carry-on-expanded-suitcase/",
        "拡張機能を使うと持ち込めない場合",
        "GUIDE",
        "RISK",
        2,
    ),
    (
        "A13",
        "/guides/carry-on-personal-item/",
        "身の回り品と手荷物の違い",
        "GUIDE",
        "RULE",
        2,
    ),
    (
        "A14",
        "/guides/carry-on-weight-calculator/",
        "荷物の合計重量を見積もる方法",
        "TOOL",
        "DECISION",
        2,
    ),
    (
        "A15",
        "/comparisons/lightweight-carry-on-suitcases/",
        "公称重量で比べる軽量機内持ち込み候補",
        "COMPARISON",
        "PRODUCT",
        3,
    ),
    (
        "A16",
        "/comparisons/front-open-carry-on-suitcases/",
        "フロントオープン候補の条件比較",
        "COMPARISON",
        "PRODUCT",
        3,
    ),
    (
        "A17",
        "/comparisons/carry-on-suitcases-with-stopper/",
        "ストッパー付き候補の条件比較",
        "COMPARISON",
        "PRODUCT",
        3,
    ),
    (
        "A18",
        "/comparisons/soft-vs-hard-carry-on/",
        "ソフトとハードの仕様差から選ぶ",
        "DIFFERENCE",
        "DECISION",
        3,
    ),
    (
        "A19",
        "/differences/ace-cresta-vs-difference-vs-maxpass4/",
        "ACE 3モデルの違い",
        "DIFFERENCE",
        "PRODUCT",
        3,
    ),
    (
        "A20",
        "/guides/business-trip-carry-on/",
        "1〜2泊出張で先に決める条件",
        "GUIDE",
        "TASK",
        3,
    ),
    (
        "A21",
        "/guides/weekend-trip-carry-on/",
        "週末旅行の荷物から容量を決める",
        "GUIDE",
        "TASK",
        3,
    ),
    (
        "A22",
        "/guides/carry-on-laptop-size/",
        "PC収納と外寸を同時に確認する",
        "GUIDE",
        "TASK",
        4,
    ),
    (
        "A23",
        "/guides/carry-on-liquid-rules/",
        "液体物ルールの公式確認手順",
        "GUIDE",
        "RULE",
        4,
    ),
    (
        "A24",
        "/guides/carry-on-battery-rules/",
        "モバイルバッテリー持ち込み確認手順",
        "GUIDE",
        "RISK",
        4,
    ),
    (
        "A25",
        "/policy/how-we-compare-carry-on-products/",
        "機内持ち込み用品の比較方法",
        "POLICY",
        "TRUST",
        1,
    ),
)


def product_specification() -> dict[str, object]:
    portfolio = [
        {
            "article_id": article_id,
            "route": route,
            "working_title": title,
            "template": template,
            "intent_class": intent,
            "wave": wave,
            "phase_1_state": (
                "LOCAL_VERTICAL_SLICE_CANDIDATE" if wave == 1 else "PLANNED_LOCKED"
            ),
        }
        for article_id, route, title, template, intent, wave in PORTFOLIO
    ]
    return {
        "schema": "RAOS_V2_PRODUCT_SPEC_V2",
        "version": "2.0.0",
        "brand": {
            "public_name": "暮らしのしるべ",
            "internal_name": "RAOS V2",
            "positioning": "公式ルールと製品仕様を照合し、条件に合う候補だけを残す購買支援",
            "public_no_1_claim_allowed": False,
            "voice": ["具体的", "静か", "非誇張", "不明を不明と表示"],
        },
        "wedge": {
            "id": "WEDGE-CARRY-ON-JP-V1",
            "name": "旅の機内持ち込み条件と荷物選び",
            "market": "JP",
            "currency": "JPY",
            "timezone": "Asia/Tokyo",
            "single_wedge": True,
            "value_mechanisms": [
                "condition_input_decision_flow",
                "official_rule_and_product_spec_normalization",
                "fit_non_fit_and_unknown_visibility",
                "source_level_checked_at_and_change_tracking",
            ],
        },
        "templates": [
            "HOME",
            "HUB",
            "GUIDE",
            "COMPARISON",
            "DIFFERENCE",
            "TOOL",
            "POLICY",
        ],
        "portfolio": portfolio,
        "wave_1_contract": {
            "six_primary_assets": [f"A0{value}" for value in range(1, 7)],
            "support_policy": "A25",
            "public_action": "PHASE_3_HUMAN_GATED",
        },
        "gates": {
            "day_30": {
                "continue": [
                    "critical_defects=0",
                    "source_sla=100%",
                    "index_canonical_issues=0",
                    "QDS instrumentation AVAILABLE or approved UNAVAILABLE explanation",
                    "at least 2 non-brand query families observed",
                ],
                "otherwise": ["REPAIR", "EXTEND", "RETREAT"],
            },
            "day_90": {
                "continue": [
                    "at least 3 query families",
                    "500 monthly non-brand sessions or improving valid sample",
                    "QDS rate >=20%",
                    "affiliate outbound CTR >=3% planning signal",
                    "major defects=0",
                    "broken affiliate links=0",
                ],
                "threshold_origin": "PLANNING_HYPOTHESIS_NOT_MARKET_BENCHMARK",
                "otherwise": ["REPAIR", "CONSOLIDATE", "RETREAT", "EXTEND"],
            },
            "month_12": {
                "expand_only_if": [
                    "all quality guardrails pass",
                    "mature economic contribution profit positive for 3 months",
                    "update labor remains within ceiling",
                ],
                "if_not": "STOP_NEW_ARTICLES_AND_IMPROVE_CONSOLIDATE_OR_RETREAT",
            },
        },
        "north_star_hypotheses": {
            "rebaseline": "after Day 90 cohort and again at P5",
            "12_month": {
                "assets": "24-25",
                "qds_monthly": 1500,
                "qds_rate_min": "0.30",
                "outbound_ctr_min": "0.06",
                "confirmed_epc_jpy_min": 30,
                "confirmed_rpm_jpy_min": 1800,
                "economic_contribution_jpy_min": 60000,
            },
            "24_month": {
                "assets": "45-50",
                "qds_monthly": 8000,
                "qds_rate_min": "0.32",
                "outbound_ctr_min": "0.07",
                "confirmed_epc_jpy_min": 40,
                "confirmed_rpm_jpy_min": 2800,
                "economic_contribution_jpy_min": 250000,
            },
            "36_month": {
                "assets": "75-85",
                "qds_monthly": 25000,
                "qds_rate_min": "0.33",
                "outbound_ctr_min": "0.08",
                "confirmed_epc_jpy_min": 50,
                "confirmed_rpm_jpy_min": 4000,
                "economic_contribution_jpy_min": 700000,
            },
            "classification": "INTERNAL_PLANNING_HYPOTHESES_NOT_PUBLIC_NO_1_EVIDENCE",
        },
        "guardrails": {
            "external_spend_jpy": 0,
            "hands_on_claims_without_use": "FORBIDDEN",
            "product_facts": "ALLOWED_PRIMARY_SOURCES_ONLY",
            "competitor_content": "UX_RESEARCH_ONLY",
            "recommendation_business_score_coupling": "FORBIDDEN",
            "automatic_publication": False,
        },
        "phase_planning_ceiling_hours": {"P0": 16, "P1": 40, "P2": 80},
        "backlog_id": "B-V2-010",
        "test_ids": ["T-V2-007"],
    }


def route_registry() -> dict[str, object]:
    policy_route = "/policy/how-we-compare-carry-on-products/"
    routes: list[dict[str, object]] = [
        {
            "route": "/",
            "article_id": "HOME",
            "primary_intent_id": "INT-HOME",
            "template": "HOME",
            "parent_hub": None,
            "taxonomy": [],
            "breadcrumbs": [{"label": "ホーム", "route": "/"}],
            "internal_links": ["/carry-on/", policy_route],
            "index_state": "PRESERVE_CURRENT",
            "phase": "CURRENT_PUBLIC_UNCHANGED",
        }
    ]
    all_asset_routes = [row[1] for row in PORTFOLIO]
    for article_id, route, title, template, _intent, wave in PORTFOLIO:
        is_hub = article_id == "A01"
        links = (
            [value for value in all_asset_routes if value != route]
            if is_hub
            else ["/carry-on/", policy_route]
        )
        if route == policy_route:
            links = ["/carry-on/", "/tools/carry-on-size-checker/"]
        routes.append(
            {
                "route": route,
                "article_id": article_id,
                "primary_intent_id": f"INT-{article_id}",
                "template": template,
                "parent_hub": "/" if is_hub else "/carry-on/",
                "taxonomy": ["carry-on"],
                "breadcrumbs": [
                    {"label": "ホーム", "route": "/"},
                    *(
                        []
                        if is_hub
                        else [{"label": "機内持ち込み", "route": "/carry-on/"}]
                    ),
                    {"label": title, "route": route},
                ],
                "internal_links": list(dict.fromkeys(links)),
                "index_state": (
                    "PRESERVE_CURRENT"
                    if article_id == "A05"
                    else (
                        "LOCAL_CANDIDATE_NOINDEX"
                        if wave == 1
                        else "PLANNED_LOCKED_NOINDEX"
                    )
                ),
                "phase": "PHASE_2_LOCAL" if wave == 1 else "POST_GATE",
            }
        )
    return {
        "schema": "RAOS_V2_ROUTE_REGISTRY_V2",
        "origin": "https://kurashinoshirube.com",
        "public_mutation_authorized": False,
        "collision_policy": "FAIL_CLOSED",
        "empty_indexable_taxonomy_allowed": False,
        "routes": routes,
        "backlog_id": "B-V2-011",
        "test_ids": ["T-V2-009", "T-V2-010", "T-V2-027"],
    }


def validate_cross_ledger_identity(
    product: Mapping[str, object],
    routes: Mapping[str, object],
    *,
    article_definitions: Mapping[str, object] | None = None,
    pages: Mapping[str, object] | None = None,
) -> None:
    """Fail closed when route/article/intent IDs drift across V2 ledgers."""

    if article_definitions is None:
        value = _read_yaml(
            Path("changes/raos-v2/phase-2/content/article-definitions.v2.yaml")
        )
        article_definitions = value if isinstance(value, dict) else None
    if pages is None:
        value = _read_json(
            Path("packages/web-ui/src/decision-support-v2/preview/pages.v2.json")
        )
        pages = value if isinstance(value, dict) else None
    if not isinstance(article_definitions, Mapping) or not isinstance(pages, Mapping):
        fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")
    portfolio = product.get("portfolio")
    route_rows = routes.get("routes")
    article_rows = article_definitions.get("articles")
    page_rows = pages.get("pages")
    if not all(
        isinstance(value, list)
        for value in (portfolio, route_rows, article_rows, page_rows)
    ):
        fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")

    def index(rows: object, key: str) -> dict[str, Mapping[str, object]]:
        assert isinstance(rows, list)
        result: dict[str, Mapping[str, object]] = {}
        for row in rows:
            if not isinstance(row, Mapping) or not isinstance(row.get(key), str):
                fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")
            identifier = str(row[key])
            if identifier in result:
                fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")
            result[identifier] = row
        return result

    portfolio_by_route = index(portfolio, "route")
    routes_by_route = index(route_rows, "route")
    articles_by_route = index(article_rows, "route")
    pages_by_route = index(page_rows, "route")
    if set(portfolio_by_route) != set(routes_by_route) - {"/"}:
        fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")
    for route, portfolio_row in portfolio_by_route.items():
        route_row = routes_by_route[route]
        if any(
            route_row.get(field) != portfolio_row.get(field)
            for field in ("article_id", "template")
        ):
            fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")
    for route, article_row in articles_by_route.items():
        route_row = routes_by_route.get(route)
        if not isinstance(route_row, Mapping) or any(
            route_row.get(field) != article_row.get(field)
            for field in (
                "article_id",
                "primary_intent_id",
                "template",
                "parent_hub",
            )
        ):
            fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")
    for route, page_row in pages_by_route.items():
        route_row = routes_by_route.get(route)
        if not isinstance(route_row, Mapping) or any(
            route_row.get(field) != page_row.get(field)
            for field in ("article_id", "template")
        ):
            fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")


def validate_authoritative_ui_parity(
    pages: Mapping[str, object],
    *,
    route_contract: str | None = None,
    typescript_checker: str | None = None,
    preview_checker: str | None = None,
) -> None:
    """Keep package-owned preview inputs aligned with the TypeScript contract."""

    package_root = ROOT / "packages/web-ui/src/decision-support-v2"
    try:
        route_contract = (
            route_contract
            if route_contract is not None
            else (package_root / "contracts.ts").read_text(encoding="utf-8")
        )
        typescript_checker = (
            typescript_checker
            if typescript_checker is not None
            else (package_root / "checker.ts").read_text(encoding="utf-8")
        )
        preview_checker = (
            preview_checker
            if preview_checker is not None
            else (package_root / "preview/checker.js").read_text(encoding="utf-8")
        )
    except OSError, UnicodeError:
        fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")
    rows = pages.get("pages")
    if not isinstance(rows, list) or pages.get("preview_robots") != "noindex,nofollow":
        fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")
    route_pattern = re.compile(
        r"\{\s*route: '([^']+)',\s*template: '([^']+)',\s*"
        r"articleId: '([^']+)',\s*publicationState: '([^']+)',\s*"
        r"publicCandidate: (true|false),\s*"
        r"intendedIndexCandidate: (true|false),\s*"
        r"previewRobots: '([^']+)',\s*\}",
        re.DOTALL,
    )
    contract_rows = [
        {
            "route": route,
            "template": template,
            "article_id": article_id,
            "publication_state": publication_state,
            "public_candidate": public_candidate == "true",
            "intended_index_candidate": intended == "true",
            "preview_robots": robots,
        }
        for (
            route,
            template,
            article_id,
            publication_state,
            public_candidate,
            intended,
            robots,
        ) in route_pattern.findall(route_contract)
    ]
    page_contract_rows: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")
        page_contract_rows.append(
            {
                "route": row.get("route"),
                "template": row.get("template"),
                "article_id": row.get("article_id"),
                "publication_state": row.get("publication_state"),
                "public_candidate": row.get("public_candidate"),
                "intended_index_candidate": row.get("intended_index_candidate"),
                "preview_robots": pages.get("preview_robots"),
            }
        )
    if contract_rows != page_contract_rows:
        fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")

    state_pattern = re.compile(r"'(PASS|FAIL|UNKNOWN|STALE|BLOCKED|NO_MATCH)'")
    contract_state_region = route_contract.split(
        "DECISION_SUPPORT_V2_RESULT_STATES", 1
    )[-1].split("] as const", 1)[0]
    preview_state_region = preview_checker.split("const RESULT_STATES", 1)[-1].split(
        ");", 1
    )[0]
    if state_pattern.findall(contract_state_region) != state_pattern.findall(
        preview_state_region
    ):
        fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")

    def priorities(source: str) -> dict[str, int]:
        match = re.search(
            r"const STATE_PRIORITY[^=]*= Object\.freeze\(\{(.*?)\}\);",
            source,
            re.DOTALL,
        )
        if match is None:
            fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")
        return {
            state: int(value)
            for state, value in re.findall(
                r"\b(PASS|FAIL|UNKNOWN|STALE|BLOCKED|NO_MATCH):\s*(\d+)",
                match.group(1),
            )
        }

    typescript_priority = priorities(typescript_checker)
    preview_priority = priorities(preview_checker)
    if (
        typescript_priority != preview_priority
        or set(typescript_priority)
        != {"PASS", "FAIL", "UNKNOWN", "STALE", "BLOCKED", "NO_MATCH"}
        or typescript_priority["PASS"] != 0
        or typescript_priority["UNKNOWN"] <= typescript_priority["NO_MATCH"]
    ):
        fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")
    semantic_tokens = {
        "BigInt": "BigInt",
        "permutations": "permutations",
        "journeyScope": "journeyScope",
        "effectiveUntil": "effectiveUntil",
        "sourceNextReviewAt": "nextReviewAt",
        "personalItemUnderseatConfirmed": "personalItemUnderseatConfirmed",
        "appendagesIncluded": "appendagesIncluded",
    }
    if any(
        typescript_token not in typescript_checker
        or preview_token not in preview_checker
        for typescript_token, preview_token in semantic_tokens.items()
    ):
        fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")


def sitemap_candidates_document(
    pages: Mapping[str, object], preview: Mapping[Path, bytes]
) -> dict[str, object]:
    """Describe future sitemap eligibility without creating a public sitemap."""

    page_rows = pages.get("pages")
    if not isinstance(page_rows, list):
        fail("RAOS_V2_SITEMAP_CANDIDATE_INVALID")
    entries: list[dict[str, object]] = []
    for row in page_rows:
        if not isinstance(row, dict):
            fail("RAOS_V2_SITEMAP_CANDIDATE_INVALID")
        route = row.get("route")
        if not isinstance(route, str):
            fail("RAOS_V2_SITEMAP_CANDIDATE_INVALID")
        relative = (
            Path("changes/raos-v2/phase-2/preview/index.html")
            if route == "/"
            else Path("changes/raos-v2/phase-2/preview")
            / route.strip("/")
            / "index.html"
        )
        payload = preview.get(relative)
        if not isinstance(payload, bytes):
            fail("RAOS_V2_SITEMAP_CANDIDATE_INVALID")
        intended = row.get("intended_index_candidate") is True
        entries.append(
            {
                "route": route,
                "article_id": row.get("article_id"),
                "title": row.get("title"),
                "description": row.get("description"),
                "canonical_candidate": f"https://kurashinoshirube.com{route}",
                "preview_robots": "noindex,nofollow",
                "phase2_sitemap_included": False,
                "phase3_intended_candidate": intended,
                "lastmod": "UNAVAILABLE",
                "render_sha256": sha256(payload),
            }
        )
    return {
        "schema": "RAOS_V2_SITEMAP_CANDIDATES_V1",
        "mode": "LOCAL_CONTRACT_ONLY",
        "target_origin": "https://kurashinoshirube.com",
        "production_sitemap_write": "NOT_EXECUTED",
        "candidate_count": sum(
            entry["phase3_intended_candidate"] is True for entry in entries
        ),
        "entries": entries,
        "backlog_id": "B-V2-031",
        "requirement_ids": ["R-V2-022"],
        "test_ids": ["T-V2-035"],
    }


def design_tokens() -> dict[str, object]:
    return {
        "schema": "RAOS_V2_DESIGN_TOKENS_V2",
        "version": "2.0.0",
        "color": {
            "ink": "#17213A",
            "paper": "#FBF8F1",
            "surface": "#FFFFFF",
            "muted": "#F1F5F4",
            "indigo": "#243B6B",
            "indigo_dark": "#172A52",
            "accent": "#A4492C",
            "success": "#216E5A",
            "warning": "#8A5A00",
            "danger": "#A23434",
            "focus": "#005FCC",
            "border": "#D9D5CB",
        },
        "contrast_pairs": [
            {"foreground": "ink", "background": "paper", "minimum": "4.5"},
            {"foreground": "indigo", "background": "surface", "minimum": "4.5"},
            {"foreground": "accent", "background": "surface", "minimum": "4.5"},
            {"foreground": "focus", "background": "surface", "minimum": "4.5"},
        ],
        "typography": {
            "font_family": "system-ui, -apple-system, BlinkMacSystemFont, 'Noto Sans JP', sans-serif",
            "body": {"size_px": 16, "line_height": "1.8"},
            "meta": {"size_px": 14, "line_height": "1.6"},
            "external_font_requests": 0,
        },
        "layout": {
            "reading_max_px": 720,
            "wide_max_px": 1120,
            "shell_max_px": 1280,
            "gutter_px": {"mobile": 16, "tablet": 24, "desktop": 32},
            "viewports_px": [390, 768, 1440],
        },
        "spacing_px": [4, 8, 12, 16, 24, 32, 48, 64, 96],
        "radius_px": [6, 12, 20],
        "minimum_target_px": 44,
        "motion": {"reduced_motion_respected": True, "essential_motion_only": True},
        "accessibility_target": "WCAG_2_2_AA",
        "backlog_id": "B-V2-012",
        "test_ids": ["T-V2-008"],
    }


def component_states() -> dict[str, object]:
    states = ["DEFAULT", "LOADING", "EMPTY", "ERROR", "STALE", "BLOCKED", "DISABLED"]
    components = [
        "SemanticShell",
        "DisclosureBar",
        "DecisionHero",
        "ConditionForm",
        "ResultPanel",
        "GuideCard",
        "TrustStrip",
        "SourceChip",
        "ComparisonMatrix",
        "ProductCard",
        "AffiliateCTA",
        "ChangeLog",
        "CorrectionLink",
        "ConsentSurface",
    ]
    return {
        "schema": "RAOS_V2_COMPONENT_STATES_V1",
        "components": [
            {
                "id": component,
                "states": states,
                "keyboard_operable": True,
                "minimum_target_px": 44,
                "status_never_color_only": True,
            }
            for component in components
        ],
        "decision_states": ["PASS", "FAIL", "UNKNOWN", "STALE", "BLOCKED", "NO_MATCH"],
        "affiliate_cta": {
            "requires": [
                "exact_product_identity",
                "current_offer_or_nonvolatile_link",
                "advertising_disclosure",
            ],
            "blocked_fallback": "show reason and official/product evidence; do not fabricate CTA",
        },
        "responsive_checks": [
            "390x844",
            "768x1024",
            "1440x900",
            "360px regression",
            "200% text",
            "forced colors",
            "reduced motion",
            "no horizontal overflow",
        ],
        "backlog_id": "B-V2-012",
        "test_ids": ["T-V2-008"],
    }


DECIMAL_PATTERN: Final = r"^(0|[1-9][0-9]*)(\.[0-9]+)?$"
POSITIVE_DECIMAL_PATTERN: Final = r"^(?:[1-9][0-9]*(?:\.[0-9]+)?|0\.(?:0*[1-9][0-9]*))$"
HEX64_PATTERN: Final = r"^[0-9a-f]{64}$"
DATE_PATTERN: Final = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
DATETIME_PATTERN: Final = (
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)
JST_DATETIME_PATTERN: Final = (
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}" r"(?:\.[0-9]+)?\+09:00$"
)


def _object_schema(
    name: str,
    required: Sequence[str],
    properties: Mapping[str, object],
    *,
    all_of: Sequence[object] = (),
) -> dict[str, object]:
    document: dict[str, object] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_URI_ROOT}/{name}.schema.json",
        "title": name,
        "type": "object",
        "required": list(required),
        "properties": dict(properties),
        "additionalProperties": False,
    }
    if all_of:
        document["allOf"] = list(all_of)
    return document


def _v2_object_schema(
    name: str,
    required: Sequence[str],
    properties: Mapping[str, object],
    *,
    all_of: Sequence[object] = (),
    definitions: Mapping[str, object] | None = None,
) -> dict[str, object]:
    document: dict[str, object] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://kurashinoshirube.com/contracts/raos-v2/v2/{name}.schema.json",
        "title": name,
        "type": "object",
        "required": list(required),
        "properties": dict(properties),
        "additionalProperties": False,
    }
    if all_of:
        document["allOf"] = list(all_of)
    if definitions:
        document["$defs"] = dict(definitions)
    return document


def source_record_schema() -> dict[str, object]:
    nullable_time = {
        "type": ["string", "null"],
        "pattern": DATETIME_PATTERN,
        "format": "date-time",
    }
    return _object_schema(
        "source-record",
        (
            "schema_version",
            "source_id",
            "source_class",
            "publisher",
            "title",
            "canonical_url",
            "published_at",
            "effective_from",
            "effective_to",
            "checked_at",
            "next_review_at",
            "content_sha256",
            "capture_provenance",
            "status",
        ),
        {
            "schema_version": {"const": "1.0.0"},
            "source_id": {"type": "string", "pattern": r"^SRC-[A-Z0-9-]+$"},
            "source_class": {
                "enum": [
                    "MANUFACTURER_PRIMARY",
                    "AIRLINE_PRIMARY",
                    "GOVERNMENT_PRIMARY",
                    "RAKUTEN_PERMITTED_DATA",
                    "COMPETITOR_UX_ONLY",
                ]
            },
            "publisher": {"type": "string", "minLength": 1},
            "title": {"type": "string", "minLength": 1},
            "canonical_url": {
                "type": "string",
                "pattern": (
                    r"^https://(?![^/?#]*@)"
                    r"(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:.]+\])"
                    r"(?::443)?(?:/[^?#]*)?$"
                ),
            },
            "published_at": nullable_time,
            "effective_from": nullable_time,
            "effective_to": nullable_time,
            "checked_at": {
                "type": "string",
                "pattern": DATETIME_PATTERN,
                "format": "date-time",
            },
            "next_review_at": {
                "type": "string",
                "pattern": DATETIME_PATTERN,
                "format": "date-time",
            },
            "content_sha256": {"type": "string", "pattern": HEX64_PATTERN},
            "capture_provenance": {
                "type": "object",
                "required": ["mode", "captured_at"],
                "properties": {
                    "mode": {
                        "enum": [
                            "PUBLIC_READ_ONLY",
                            "RECORDED_FIXTURE",
                            "OWNER_SUPPLIED",
                        ]
                    },
                    "captured_at": {
                        "type": "string",
                        "pattern": DATETIME_PATTERN,
                        "format": "date-time",
                    },
                },
                "additionalProperties": False,
            },
            "status": {
                "enum": [
                    "FRESH",
                    "DUE",
                    "SOFT_STALE",
                    "HARD_STALE",
                    "UNAVAILABLE",
                    "REJECTED",
                ]
            },
        },
    )


def claim_schema() -> dict[str, object]:
    properties: dict[str, object] = {
        "schema_version": {"const": "1.0.0"},
        "claim_id": {"type": "string", "pattern": r"^CLM-[A-Z0-9-]+$"},
        "claim_type": {"enum": ["A_OFFICIAL_FACT", "D_EDITORIAL_JUDGEMENT", "UNKNOWN"]},
        "subject_id": {
            "type": "string",
            "pattern": r"^[A-Z0-9][A-Z0-9._:-]{0,127}$",
        },
        "predicate": {"type": "string", "pattern": r"^[a-z][a-z0-9_.-]{0,63}$"},
        "value": {
            "type": [
                "string",
                "number",
                "integer",
                "boolean",
                "object",
                "array",
                "null",
            ]
        },
        "unit": {"type": ["string", "null"]},
        "source_ids": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": r"^SRC-[A-Z0-9][A-Z0-9-]{0,127}$",
            },
            "maxItems": 32,
            "uniqueItems": True,
        },
        "logic_inputs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["input_id", "value_ref"],
                "properties": {
                    "input_id": {
                        "type": "string",
                        "pattern": r"^[A-Z][A-Z0-9_-]{0,63}$",
                    },
                    "value_ref": {
                        "type": "string",
                        "pattern": r"^[A-Z0-9][A-Z0-9._:-]{0,127}$",
                    },
                },
                "additionalProperties": False,
            },
            "maxItems": 32,
        },
        "checked_at": {
            "type": "string",
            "pattern": DATETIME_PATTERN,
            "format": "date-time",
        },
        "next_review_at": {
            "type": "string",
            "pattern": DATETIME_PATTERN,
            "format": "date-time",
        },
        "risk_class": {"enum": ["LOW", "MEDIUM", "HIGH"]},
        "status": {"enum": ["DRAFT", "VERIFIED", "STALE", "BLOCKED"]},
    }
    all_of = [
        {
            "if": {"properties": {"claim_type": {"const": "A_OFFICIAL_FACT"}}},
            "then": {
                "properties": {
                    "source_ids": {"minItems": 1},
                    "value": {"not": {"type": "null"}},
                }
            },
        },
        {
            "if": {"properties": {"claim_type": {"const": "D_EDITORIAL_JUDGEMENT"}}},
            "then": {"properties": {"logic_inputs": {"minItems": 1}}},
        },
        {
            "if": {"properties": {"claim_type": {"const": "UNKNOWN"}}},
            "then": {
                "properties": {
                    "value": {"type": "null"},
                    "unit": {"type": "null"},
                    "status": {"enum": ["DRAFT", "BLOCKED"]},
                }
            },
        },
    ]
    return _object_schema(
        "claim",
        tuple(properties),
        properties,
        all_of=all_of,
    )


def product_variant_schema() -> dict[str, object]:
    dimensions = {
        "type": "object",
        "required": [
            "edges_cm",
            "orientation",
            "includes_wheels_and_handles",
        ],
        "properties": {
            "edges_cm": {
                "type": "array",
                "prefixItems": [
                    {"type": "string", "pattern": POSITIVE_DECIMAL_PATTERN},
                    {"type": "string", "pattern": POSITIVE_DECIMAL_PATTERN},
                    {"type": "string", "pattern": POSITIVE_DECIMAL_PATTERN},
                ],
                "minItems": 3,
                "maxItems": 3,
            },
            "orientation": {"const": "ORDERED"},
            "includes_wheels_and_handles": {"const": True},
        },
        "additionalProperties": False,
    }
    nullable_decimal = {
        "type": ["string", "null"],
        "pattern": POSITIVE_DECIMAL_PATTERN,
    }
    return _object_schema(
        "product-variant",
        (
            "schema_version",
            "variant_id",
            "external_dimensions_cm",
            "expanded_dimensions_cm",
            "mass_kg",
            "capacity_l",
            "declared_features",
            "unknown_fields",
        ),
        {
            "schema_version": {"const": "1.0.0"},
            "variant_id": {
                "type": "string",
                "pattern": r"^[A-Z0-9][A-Z0-9-]{0,127}$",
            },
            "external_dimensions_cm": dimensions,
            "expanded_dimensions_cm": {"anyOf": [dimensions, {"type": "null"}]},
            "mass_kg": {"type": "string", "pattern": POSITIVE_DECIMAL_PATTERN},
            "capacity_l": {
                "type": "string",
                "pattern": POSITIVE_DECIMAL_PATTERN,
            },
            "expanded_capacity_l": nullable_decimal,
            "declared_features": {
                "type": "array",
                "items": {
                    "type": "string",
                    "pattern": r"^[A-Z][A-Z0-9_-]{0,63}$",
                },
                "maxItems": 64,
                "uniqueItems": True,
            },
            "unknown_fields": {
                "type": "array",
                "items": {
                    "type": "string",
                    "pattern": r"^[A-Z][A-Z0-9_-]{0,63}$",
                },
                "maxItems": 64,
                "uniqueItems": True,
            },
        },
    )


def product_model_schema() -> dict[str, object]:
    properties: dict[str, object] = {
        "schema_version": {"const": "1.0.0"},
        "product_id": {"type": "string", "pattern": r"^PRD-[A-Z0-9-]+$"},
        "manufacturer": {"type": "string", "minLength": 1},
        "brand": {"type": "string", "minLength": 1},
        "model_name": {"type": "string", "minLength": 1},
        "model_number": {"type": "string", "minLength": 1},
        "generation": {"type": "string", "minLength": 1},
        "variants": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "product-variant.schema.json"},
        },
        "official_source_ids": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": r"^SRC-[A-Z0-9][A-Z0-9-]{0,127}$",
            },
            "maxItems": 32,
            "uniqueItems": True,
        },
        "identity_status": {"enum": ["EXACT", "AMBIGUOUS", "REJECTED", "UNRESOLVED"]},
    }
    return _object_schema(
        "product-model",
        tuple(properties),
        properties,
        all_of=[
            {
                "if": {"properties": {"identity_status": {"const": "EXACT"}}},
                "then": {
                    "properties": {
                        "model_number": {"type": "string", "minLength": 1},
                        "official_source_ids": {"minItems": 1},
                    }
                },
            }
        ],
    )


def offer_observation_schema() -> dict[str, object]:
    properties: dict[str, object] = {
        "schema_version": {"const": "1.0.0"},
        "offer_id": {
            "type": "string",
            "pattern": r"^[A-Z0-9][A-Z0-9-]{0,127}$",
        },
        "product_id": {"type": "string", "pattern": r"^PRD-[A-Z0-9-]+$"},
        "provider": {"const": "RAKUTEN"},
        "mode": {"enum": ["RECORDED_ONLY", "LIVE_APPROVED"]},
        "item_code": {
            "type": ["string", "null"],
            "pattern": r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$",
        },
        "shop_code": {
            "type": ["string", "null"],
            "pattern": r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$",
        },
        "observed_at": {
            "type": "string",
            "pattern": DATETIME_PATTERN,
            "format": "date-time",
        },
        "price_jpy": {
            "type": ["string", "null"],
            "pattern": POSITIVE_DECIMAL_PATTERN,
        },
        "availability": {
            "type": ["string", "null"],
            "pattern": r"^[A-Z][A-Z0-9_-]{0,63}$",
        },
        "affiliate_url_ref": {
            "type": ["string", "null"],
            "pattern": r"^OPAQUE-[A-Z0-9][A-Z0-9._:-]{0,127}$",
        },
        "image_ref": {
            "type": ["string", "null"],
            "pattern": r"^OPAQUE-[A-Z0-9][A-Z0-9._:-]{0,127}$",
        },
        "identity_evidence": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": r"^[A-Z][A-Z0-9_-]{0,63}$",
            },
            "maxItems": 32,
            "uniqueItems": True,
        },
        "status": {
            "enum": [
                "CURRENT",
                "STALE",
                "OUT_OF_STOCK",
                "IDENTITY_BLOCKED",
                "UNAVAILABLE",
            ]
        },
    }
    return _object_schema("offer-observation", tuple(properties), properties)


def airline_rule_set_schema() -> dict[str, object]:
    decimal_or_null = {
        "type": ["string", "null"],
        "pattern": POSITIVE_DECIMAL_PATTERN,
    }
    variant = {
        "type": "object",
        "required": [
            "variant_id",
            "applicability",
            "bag_count",
            "personal_item_count",
            "dimension_edges_cm",
            "orientation",
            "sum_edges_cm",
            "total_weight_kg",
            "includes_wheels_and_handles",
            "notes",
            "resolution_requirements",
        ],
        "properties": {
            "variant_id": {"type": "string", "minLength": 1},
            "applicability": {
                "type": "object",
                "required": ["operator"],
                "properties": {
                    "operator": {
                        "type": ["string", "null"],
                        "pattern": r"^[A-Z0-9][A-Z0-9_-]{0,63}$",
                    },
                    "min_seat_count": {"type": ["integer", "null"], "minimum": 1},
                    "max_seat_count": {"type": ["integer", "null"], "minimum": 1},
                    "fare_classes": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "pattern": r"^[A-Z0-9][A-Z0-9_-]{0,63}$",
                        },
                        "uniqueItems": True,
                    },
                    "required_options": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "pattern": r"^[A-Z0-9][A-Z0-9_-]{0,63}$",
                        },
                        "uniqueItems": True,
                    },
                    "forbidden_options": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "pattern": r"^[A-Z0-9][A-Z0-9_-]{0,63}$",
                        },
                        "uniqueItems": True,
                    },
                },
                "additionalProperties": False,
            },
            "bag_count": {"type": "integer", "minimum": 0},
            "personal_item_count": {"type": "integer", "minimum": 0},
            "dimension_edges_cm": {
                "type": "array",
                "items": {
                    "type": "string",
                    "pattern": POSITIVE_DECIMAL_PATTERN,
                },
                "minItems": 3,
                "maxItems": 3,
            },
            "orientation": {"enum": ["ORDERED", "PERMUTABLE"]},
            "sum_edges_cm": decimal_or_null,
            "total_weight_kg": decimal_or_null,
            "max_per_item_weight_kg": decimal_or_null,
            "item_allowances": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "slot_id",
                        "placement",
                        "dimension_edges_cm",
                        "orientation",
                        "includes_wheels_and_handles",
                        "max_weight_kg",
                        "fit_requirement",
                    ],
                    "properties": {
                        "slot_id": {
                            "type": "string",
                            "pattern": r"^[A-Z][A-Z0-9_-]{0,63}$",
                        },
                        "placement": {"enum": ["MAIN", "UNDERSEAT", "OVERHEAD"]},
                        "dimension_edges_cm": {
                            "type": ["array", "null"],
                            "items": {
                                "type": "string",
                                "pattern": POSITIVE_DECIMAL_PATTERN,
                            },
                            "minItems": 3,
                            "maxItems": 3,
                        },
                        "orientation": {"enum": ["ORDERED", "PERMUTABLE"]},
                        "includes_wheels_and_handles": {"type": ["boolean", "null"]},
                        "max_weight_kg": decimal_or_null,
                        "fit_requirement": {"enum": ["UNDERSEAT", None]},
                    },
                    "additionalProperties": False,
                },
                "maxItems": 4,
            },
            "includes_wheels_and_handles": {"type": "boolean"},
            "notes": {"type": "array", "items": {"type": "string"}},
            "resolution_requirements": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    }
    properties: dict[str, object] = {
        "schema_version": {"const": "1.0.0"},
        "rule_set_id": {"type": "string", "minLength": 1},
        "carrier": {"type": "string", "minLength": 1},
        "journey_scope": {"enum": ["DOMESTIC", "INTERNATIONAL", "ALL"]},
        "effective_interval_semantics": {"const": "FROM_INCLUSIVE_TO_EXCLUSIVE"},
        "effective_from": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "string",
                    "pattern": DATETIME_PATTERN,
                    "format": "date-time",
                },
            ],
        },
        "observed_applicable_from": {
            "type": "string",
            "pattern": DATETIME_PATTERN,
            "format": "date-time",
        },
        "applicability_basis": {
            "enum": [
                "OBSERVED_CURRENT_AT_CAPTURE_NO_PUBLISHED_EFFECTIVE_DATE",
                "OFFICIAL_EFFECTIVE_DATE",
            ]
        },
        "effective_to": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "string",
                    "pattern": DATETIME_PATTERN,
                    "format": "date-time",
                },
            ]
        },
        "variants": {"type": "array", "items": variant, "minItems": 1},
        "source_id": {
            "type": "string",
            "pattern": r"^SRC-[A-Z0-9][A-Z0-9-]{0,127}$",
        },
        "source_content_sha256": {
            "type": "string",
            "pattern": HEX64_PATTERN,
        },
        "source_next_review_at": {
            "type": "string",
            "pattern": DATETIME_PATTERN,
            "format": "date-time",
        },
        "recheck_required_before_use": {"type": "boolean"},
        "checked_at": {
            "type": "string",
            "pattern": DATETIME_PATTERN,
            "format": "date-time",
        },
    }
    return _object_schema(
        "airline-rule-set",
        tuple(properties),
        properties,
        all_of=[
            {
                "if": {
                    "properties": {
                        "applicability_basis": {"const": "OFFICIAL_EFFECTIVE_DATE"}
                    }
                },
                "then": {"properties": {"effective_from": {"not": {"type": "null"}}}},
            },
            {
                "if": {
                    "properties": {
                        "applicability_basis": {
                            "const": "OBSERVED_CURRENT_AT_CAPTURE_NO_PUBLISHED_EFFECTIVE_DATE"
                        }
                    }
                },
                "then": {"properties": {"effective_from": {"type": "null"}}},
            },
        ],
    )


ARTICLE_BLOCK_ORDERS: Final = {
    "HOME": (
        "MASTHEAD_DISCLOSURE",
        "HERO",
        "QUICK_CHECK",
        "VERIFIED_GUIDES",
        "DECISION_PATHS",
        "TRUST_STRIP",
        "EDITORIAL_METHOD",
        "FOOTER_POLICIES",
    ),
    "HUB": (
        "SCOPE",
        "DECISION_MAP",
        "TOOL_ENTRY",
        "AIRLINE_RULE_CARDS",
        "TASK_GUIDES",
        "PRODUCT_COMPARISONS",
        "UNKNOWN_EDGE_CASES",
        "METHOD_FRESHNESS_CORRECTION",
        "PUBLISHED_RELATED_LINKS",
    ),
    "GUIDE": (
        "DISCLOSURE",
        "PROBLEM_SCOPE",
        "THIRTY_SECOND_CONCLUSION",
        "DECISION_INPUTS",
        "OFFICIAL_FACTS",
        "HYPOTHETICAL_EXAMPLES",
        "EXCEPTIONS_UNKNOWN",
        "ALTERNATIVE_PATH",
        "CONDITIONAL_NEXT_STEP",
        "SOURCES_CHANGELOG_CORRECTION",
    ),
    "COMPARISON": (
        "DISCLOSURE_SCOPE",
        "THIRTY_SECOND_CONCLUSION",
        "FIT_NON_FIT",
        "METHOD",
        "COMPARISON_TABLE",
        "PRODUCT_CARDS",
        "DECISION_CRITERIA",
        "BUY_NONE_CONDITIONS",
        "SOURCES_CHANGELOG_CORRECTION",
        "RELATED_LINKS",
    ),
    "DIFFERENCE": (
        "SCOPE_NON_DUPLICATION",
        "DECISIVE_DIFFERENCES",
        "FACT_TABLE",
        "CONDITIONAL_BRANCH",
        "COMMON_NON_FIT",
        "SOURCES_CHECKED_DATE",
        "COMPARISON_OR_TOOL_LINK",
    ),
    "TOOL": (
        "PURPOSE_LIMITATION_PRIVACY",
        "INPUTS",
        "VALIDATION",
        "RESULT",
        "RESOLVED_RULE",
        "NON_GUARANTEE",
        "NEXT_ACTION",
        "LOCAL_RESET_COPY",
        "CTA_GUARD",
    ),
    "POLICY": (
        "SCOPE",
        "SOURCE_AND_CLAIM_LABELS",
        "NO_HANDS_ON_POLICY",
        "AI_AND_HUMAN_RESPONSIBILITY",
        "RECOMMENDATION_BUSINESS_SEPARATION",
        "AFFILIATE_AND_CTA_RULES",
        "FRESHNESS_CORRECTIONS_HISTORY",
        "PRIVACY_MEASUREMENT_LINK",
    ),
}


def article_definition_schema() -> dict[str, object]:
    block_types = sorted(
        {block_type for order in ARTICLE_BLOCK_ORDERS.values() for block_type in order}
    )
    properties: dict[str, object] = {
        "schema_version": {"const": "1.0.0"},
        "article_id": {"type": "string", "minLength": 1},
        "route": {"type": "string", "pattern": r"^/(?:[a-z0-9-]+/)*$"},
        "template": {
            "enum": [
                "HOME",
                "HUB",
                "GUIDE",
                "COMPARISON",
                "DIFFERENCE",
                "TOOL",
                "POLICY",
            ]
        },
        "primary_intent_id": {
            "type": "string",
            "pattern": r"^INT-[A-Z0-9-]+$",
        },
        "parent_hub": {
            "type": ["string", "null"],
            "pattern": r"^/(?:[a-z0-9-]+/)*$",
        },
        "claim_ids": {
            "type": "array",
            "items": {"type": "string", "pattern": r"^CLM-[A-Z0-9-]+$"},
            "minItems": 1,
            "uniqueItems": True,
        },
        "editorial_decisions": {
            "type": "array",
            "items": {"type": "string", "pattern": r"^ED-[A-Z0-9-]+$"},
            "minItems": 1,
            "uniqueItems": True,
        },
        "blocks": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["block_id", "block_type"],
                "properties": {
                    "block_id": {
                        "type": "string",
                        "pattern": r"^BLK-[A-Z0-9-]+$",
                    },
                    "block_type": {"enum": block_types},
                },
                "additionalProperties": False,
            },
        },
        "disclosure": {"type": "string", "minLength": 1},
        "source_checked_at": {
            "type": "string",
            "pattern": DATETIME_PATTERN,
            "format": "date-time",
        },
        "review_state": {
            "enum": ["DRAFT", "EVIDENCE_COMPLETE", "REVIEW_REQUIRED", "HUMAN_REVIEWED"]
        },
    }
    all_of = [
        {
            "if": {"properties": {"template": {"const": template}}},
            "then": {
                "properties": {
                    "blocks": {
                        "minItems": len(order),
                        "prefixItems": [
                            {"properties": {"block_type": {"const": block_type}}}
                            for block_type in order
                        ],
                    }
                }
            },
        }
        for template, order in ARTICLE_BLOCK_ORDERS.items()
    ]
    return _object_schema(
        "article-definition", tuple(properties), properties, all_of=all_of
    )


def editorial_decision_schema() -> dict[str, object]:
    decision_input = {
        "type": "object",
        "required": ["input_id", "value_ref"],
        "properties": {
            "input_id": {
                "type": "string",
                "pattern": r"^IN-[A-Z0-9-]+$",
                "not": {
                    "enum": [
                        "IN-COMMISSION",
                        "IN-EPC",
                        "IN-BUSINESS-SCORE",
                        "IN-PRICE",
                        "IN-REWARD-RATE",
                    ]
                },
            },
            "value_ref": {
                "type": "string",
                "pattern": r"^CLM-[A-Z0-9-]+$",
            },
        },
        "additionalProperties": False,
    }
    properties: dict[str, object] = {
        "schema_version": {"const": "1.0.0"},
        "decision_id": {"type": "string", "pattern": r"^ED-[A-Z0-9-]+$"},
        "decision_type": {
            "enum": [
                "ELIGIBILITY",
                "FIT",
                "ARTICLE_SCOPE",
                "TRADE_OFF",
                "UNKNOWN_HANDLING",
            ]
        },
        "inputs": {"type": "array", "items": decision_input, "minItems": 1},
        "logic_version": {
            "type": "string",
            "pattern": r"^LOGIC-[A-Z0-9.-]+$",
        },
        "outcome": {"type": "string", "minLength": 1},
        "rationale": {"type": "string", "minLength": 1},
        "non_fit": {"type": "array", "items": {"type": "string"}},
        "reviewer": {
            "type": ["string", "null"],
            "pattern": r"^REVIEWER-[A-Z0-9-]+$",
        },
    }
    return _object_schema("editorial-decision", tuple(properties), properties)


def publication_package_schema() -> dict[str, object]:
    base_hashes = ("article", "claims", "sources", "render", "migration")
    real_required_hashes = (
        *base_hashes,
        "editorial",
        "products",
        "review",
        "render_model",
    )
    real_hash_properties = (*real_required_hashes, "phase3_claim_authority")
    review_binding = {
        "anyOf": [
            {"type": "null"},
            {
                "type": "object",
                "required": [
                    "reviewer_id",
                    "reviewed_at",
                    "review_version",
                    "synthetic",
                ],
                "properties": {
                    "reviewer_id": {
                        "type": "string",
                        "pattern": r"^[A-Z0-9][A-Z0-9._:-]{0,127}$",
                    },
                    "reviewed_at": {
                        "type": "string",
                        "pattern": DATETIME_PATTERN,
                        "format": "date-time",
                    },
                    "review_version": {
                        "type": "string",
                        "pattern": r"^[A-Z0-9][A-Z0-9._:-]{0,127}$",
                    },
                    "synthetic": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        ]
    }
    migration_binding = {
        "anyOf": [
            {
                "type": "object",
                "required": ["schema", "mode", "target_route", "sha256"],
                "properties": {
                    "schema": {"const": "RAOS_V2_MIGRATION_MANIFEST_V1"},
                    "mode": {"const": "LOCAL_SIMULATION_ONLY"},
                    "target_route": {
                        "type": "string",
                        "pattern": r"^/(?:[a-z0-9-]+/)*$",
                    },
                    "sha256": {"type": "string", "pattern": HEX64_PATTERN},
                },
                "additionalProperties": False,
            },
            {
                "type": "object",
                "required": ["previous", "next", "wordpress_intent", "sha256"],
                "properties": {
                    "previous": {"type": "null"},
                    "next": {"const": "synthetic"},
                    "wordpress_intent": {"const": "CREATE_OR_UPDATE"},
                    "sha256": {"type": "string", "pattern": HEX64_PATTERN},
                },
                "additionalProperties": False,
            },
        ]
    }
    claim_evidence = {
        "type": "array",
        "minItems": 1,
        "items": {
            "type": "object",
            "required": ["claim_id", "risk_class", "freshness"],
            "properties": {
                "claim_id": {
                    "type": "string",
                    "pattern": r"^CLM-[A-Z0-9-]+$",
                },
                "risk_class": {"enum": ["LOW", "MEDIUM", "HIGH"]},
                "freshness": {
                    "enum": [
                        "FRESH",
                        "DUE",
                        "SOFT_STALE",
                        "HARD_STALE",
                        "UNKNOWN",
                        "UNAVAILABLE",
                        "REJECTED",
                    ]
                },
            },
            "additionalProperties": False,
        },
    }
    properties: dict[str, object] = {
        "schema_version": {"const": "1.0.0"},
        "package_id": {
            "type": "string",
            "pattern": r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        },
        "target_origin": {"const": "https://kurashinoshirube.com"},
        "target_route": {"type": "string", "pattern": r"^/(?:[a-z0-9-]+/)*$"},
        "article_id": {
            "type": "string",
            "pattern": r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        },
        "input_hashes": {
            "type": "object",
            "required": list(base_hashes),
            "properties": {
                name: {"type": "string", "pattern": HEX64_PATTERN}
                for name in real_hash_properties
            },
            "additionalProperties": False,
        },
        "render_hash": {"type": "string", "pattern": HEX64_PATTERN},
        "source_snapshot_hash": {"type": "string", "pattern": HEX64_PATTERN},
        "review_binding": review_binding,
        "migration_manifest": migration_binding,
        "claim_evidence": claim_evidence,
        "created_at": {
            "type": "string",
            "pattern": DATETIME_PATTERN,
            "format": "date-time",
        },
        "content_class": {"enum": ["REAL_CONTENT", "SYNTHETIC_FIXTURE"]},
        "package_digest": {
            "type": ["string", "null"],
            "pattern": HEX64_PATTERN,
        },
        "state": {
            "enum": [
                "DRAFT",
                "EVIDENCE_COMPLETE",
                "HUMAN_REVIEWED",
                "PACKAGE_SEALED",
                "BLOCKED",
                "REVIEW_REQUIRED",
            ]
        },
    }
    return _object_schema(
        "publication-package",
        tuple(properties),
        properties,
        all_of=[
            {
                "if": {"properties": {"content_class": {"const": "REAL_CONTENT"}}},
                "then": {
                    "properties": {
                        "state": {
                            "enum": [
                                "DRAFT",
                                "EVIDENCE_COMPLETE",
                                "BLOCKED",
                                "REVIEW_REQUIRED",
                            ]
                        },
                        "review_binding": {"type": "null"},
                        "input_hashes": {"required": list(real_required_hashes)},
                        "package_digest": {"type": "null"},
                    }
                },
            },
            {
                "if": {"properties": {"state": {"const": "PACKAGE_SEALED"}}},
                "then": {
                    "properties": {
                        "content_class": {"const": "SYNTHETIC_FIXTURE"},
                        "review_binding": {
                            "type": "object",
                            "required": ["synthetic"],
                            "properties": {"synthetic": {"const": True}},
                        },
                        "package_digest": {
                            "type": "string",
                            "pattern": HEX64_PATTERN,
                        },
                        "claim_evidence": {
                            "items": {
                                "properties": {"freshness": {"enum": ["FRESH", "DUE"]}}
                            }
                        },
                    }
                },
            },
        ],
    )


def phase3_preaction_binding_schema() -> dict[str, object]:
    """Contract for the create-once public capture and owner export binding."""

    return _v2_object_schema(
        "preaction-binding",
        (
            "schema",
            "version",
            "status",
            "provenance",
            "captured_at",
            "target",
            "current_public_body_sha256",
            "public_capture_sha256",
            "wordpress_export_sha256",
            "wordpress_export_bytes",
            "owner_evidence_sha256",
            "legacy_post_content_sha256",
        ),
        {
            "schema": {"const": "RAOS_V2_PHASE3_PREACTION_BINDING_V1"},
            "version": {"const": "1.0.0"},
            "status": {"const": "VERIFIED_PREACTION"},
            "provenance": {
                "const": "PUBLIC_READ_ONLY_CAPTURE_AND_OWNER_WORDPRESS_EXPORT"
            },
            "captured_at": {
                "type": "string",
                "pattern": DATETIME_PATTERN,
                "format": "date-time",
            },
            "target": {
                "type": "object",
                "required": [
                    "origin",
                    "route",
                    "kind",
                    "post_id",
                    "exact_match_count",
                ],
                "properties": {
                    "origin": {"const": "https://kurashinoshirube.com"},
                    "route": {"const": "/carry-on-suitcase-comparison/"},
                    "kind": {"const": "EXISTING_POST"},
                    "post_id": {"type": "integer", "minimum": 1},
                    "exact_match_count": {"const": 1},
                },
                "additionalProperties": False,
            },
            "current_public_body_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "public_capture_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "wordpress_export_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "wordpress_export_bytes": {"type": "integer", "minimum": 1},
            "owner_evidence_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "legacy_post_content_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
        },
    )


def phase3_structured_data_expectation_contract_schema() -> dict[str, object]:
    """Closed derived JSON-LD envelope embedded in the reviewed payload."""

    canonical = "https://kurashinoshirube.com/carry-on-suitcase-comparison/"
    origin = "https://kurashinoshirube.com/"
    plain_text = {"type": "string", "minLength": 1}
    article = {
        "type": "object",
        "required": [
            "@type",
            "headline",
            "description",
            "mainEntityOfPage",
            "url",
        ],
        "properties": {
            "@type": {"const": "Article"},
            "headline": plain_text,
            "description": plain_text,
            "mainEntityOfPage": {
                "type": "object",
                "required": ["@id"],
                "properties": {"@id": {"const": canonical}},
                "additionalProperties": False,
            },
            "url": {"const": canonical},
        },
        "additionalProperties": False,
    }
    breadcrumb = {
        "type": "object",
        "required": ["@type", "itemListElement"],
        "properties": {
            "@type": {"const": "BreadcrumbList"},
            "itemListElement": {
                "type": "array",
                "minItems": 1,
                "maxItems": 1,
                "prefixItems": [
                    {
                        "type": "object",
                        "required": ["@type", "position", "name", "item"],
                        "properties": {
                            "@type": {"const": "ListItem"},
                            "position": {"const": 1},
                            "name": plain_text,
                            "item": {"const": canonical},
                        },
                        "additionalProperties": False,
                    }
                ],
                "items": False,
            },
        },
        "additionalProperties": False,
    }

    def owner_graph(node_type: str) -> dict[str, object]:
        return {
            "type": "object",
            "required": ["@type", "url"],
            "properties": {
                "@type": {"const": node_type},
                "url": {"const": origin},
            },
            "additionalProperties": False,
        }

    document = {
        "type": "object",
        "required": ["@context", "@graph"],
        "properties": {
            "@context": {"const": "https://schema.org"},
            "@graph": {
                "type": "array",
                "minItems": 4,
                "maxItems": 4,
                "prefixItems": [
                    article,
                    breadcrumb,
                    owner_graph("Organization"),
                    owner_graph("WebSite"),
                ],
                "items": False,
            },
        },
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "required": [
            "schema",
            "version",
            "derivation",
            "json_ld_script_count",
            "json_ld_document_count",
            "json_ld_types",
            "emission",
            "documents",
            "json_ld_sha256",
        ],
        "properties": {
            "schema": {"const": "RAOS_V2_PHASE3_STRUCTURED_DATA_EXPECTATION_V1"},
            "version": {"const": "1.0.0"},
            "derivation": {"const": "EXACT_WORDPRESS_FIELDS_V1"},
            "json_ld_script_count": {"const": 1},
            "json_ld_document_count": {"const": 1},
            "json_ld_types": {
                "const": [
                    "Article",
                    "BreadcrumbList",
                    "Organization",
                    "WebSite",
                ]
            },
            "emission": {
                "type": "object",
                "required": [
                    "owner",
                    "local_json_ld_emission",
                    "external_configuration_status",
                ],
                "properties": {
                    "owner": {"const": "EXTERNAL_WORDPRESS_SEO_CONFIGURATION"},
                    "local_json_ld_emission": {"const": False},
                    "external_configuration_status": {"const": "UNVERIFIED_EXTERNAL"},
                },
                "additionalProperties": False,
            },
            "documents": {
                "type": "array",
                "minItems": 1,
                "maxItems": 1,
                "prefixItems": [document],
                "items": False,
            },
            "json_ld_sha256": {"type": "string", "pattern": HEX64_PATTERN},
        },
        "additionalProperties": False,
    }


def phase3_wordpress_update_payload_schema() -> dict[str, object]:
    field_properties: dict[str, object] = {
        "canonical_url": {
            "const": "https://kurashinoshirube.com/carry-on-suitcase-comparison/"
        },
        "comment_status": {"const": "closed"},
        "meta_description": {"type": "string", "minLength": 1},
        "ping_status": {"const": "closed"},
        "post_content": {"type": "string", "minLength": 1},
        "post_excerpt": {"type": "string"},
        "post_name": {"const": "carry-on-suitcase-comparison"},
        "post_status": {"const": "publish"},
        "post_title": {"type": "string", "minLength": 1},
    }
    return _v2_object_schema(
        "wordpress-update-payload",
        (
            "schema",
            "version",
            "intent",
            "target",
            "preconditions",
            "postconditions",
            "structured_data_expectation",
            "preaction",
            "fields",
        ),
        {
            "schema": {"const": "RAOS_V2_PHASE3_WORDPRESS_UPDATE_PAYLOAD_V1"},
            "version": {"const": "1.0.0"},
            "intent": {"const": "UPDATE_EXISTING_PUBLISHED_POST_AT_APPROVED_CUTOVER"},
            "target": {
                "type": "object",
                "required": [
                    "origin",
                    "route",
                    "kind",
                    "expected_match_count",
                    "expected_public_body_sha256",
                ],
                "properties": {
                    "origin": {"const": "https://kurashinoshirube.com"},
                    "route": {"const": "/carry-on-suitcase-comparison/"},
                    "kind": {"const": "EXISTING_POST"},
                    "expected_match_count": {"const": 1},
                    "expected_public_body_sha256": {
                        "type": "string",
                        "pattern": HEX64_PATTERN,
                    },
                },
                "additionalProperties": False,
            },
            "preconditions": {
                "type": "object",
                "required": ["expected_current_post_status"],
                "properties": {
                    "expected_current_post_status": {"const": "publish"},
                },
                "additionalProperties": False,
            },
            "postconditions": {
                "type": "object",
                "required": ["required_after_post_status"],
                "properties": {
                    "required_after_post_status": {"const": "publish"},
                },
                "additionalProperties": False,
            },
            "structured_data_expectation": (
                phase3_structured_data_expectation_contract_schema()
            ),
            "preaction": {
                "type": "object",
                "required": ["status", "binding_digest", "binding"],
                "properties": {
                    "status": {
                        "enum": [
                            "HISTORICAL_BASELINE_ONLY",
                            "VERIFIED_PREACTION",
                        ]
                    },
                    "binding_digest": {
                        "type": ["string", "null"],
                        "pattern": HEX64_PATTERN,
                    },
                    "binding": {
                        "type": ["object", "null"],
                    },
                },
                "additionalProperties": False,
                "allOf": [
                    {
                        "if": {
                            "properties": {
                                "status": {"const": "HISTORICAL_BASELINE_ONLY"}
                            }
                        },
                        "then": {
                            "properties": {
                                "binding_digest": {"type": "null"},
                                "binding": {"type": "null"},
                            }
                        },
                    },
                    {
                        "if": {
                            "properties": {"status": {"const": "VERIFIED_PREACTION"}}
                        },
                        "then": {
                            "properties": {
                                "binding_digest": {
                                    "type": "string",
                                    "pattern": HEX64_PATTERN,
                                },
                                "binding": {
                                    "$ref": (
                                        "https://kurashinoshirube.com/contracts/"
                                        "raos-v2/v2/preaction-binding.schema.json"
                                    )
                                },
                            }
                        },
                    },
                ],
            },
            "fields": {
                "type": "object",
                "required": list(field_properties),
                "properties": field_properties,
                "additionalProperties": False,
            },
        },
    )


def phase3_human_review_receipt_schema() -> dict[str, object]:
    return _v2_object_schema(
        "human-review-receipt",
        (
            "schema",
            "version",
            "reviewer_id",
            "reviewed_at",
            "review_version",
            "correction_count",
            "accepted",
            "synthetic",
            "candidate_digest",
            "payload_digest",
            "target_route",
            "assertion_status",
            "acceptance_authority",
        ),
        {
            "schema": {"const": "RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_V1"},
            "version": {"const": "1.0.0"},
            "reviewer_id": {"const": "OWNER_ASSERTION_LOCAL"},
            "reviewed_at": {
                "type": "string",
                "pattern": DATETIME_PATTERN,
                "format": "date-time",
            },
            "review_version": {"const": "P3-OWNER-ASSERTION-V1"},
            "correction_count": {"type": "integer", "minimum": 0},
            "accepted": {"const": True},
            "synthetic": {"const": False},
            "candidate_digest": {"type": "string", "pattern": HEX64_PATTERN},
            "payload_digest": {"type": "string", "pattern": HEX64_PATTERN},
            "target_route": {"const": "/carry-on-suitcase-comparison/"},
            "assertion_status": {"const": "UNAUTHENTICATED_OWNER_ASSERTION"},
            "acceptance_authority": {"const": False},
        },
    )


def phase3_publication_package_schema() -> dict[str, object]:
    claim_binding = {
        "type": "object",
        "required": [
            "claim_id",
            "claim_type",
            "risk_class",
            "freshness",
            "authoritative_source_status",
            "checked_at",
            "next_review_at",
            "resolved",
            "blocking",
            "intentionally_disclosed",
        ],
        "properties": {
            "claim_id": {"type": "string", "pattern": r"^CLM-[A-Z0-9-]+$"},
            "claim_type": {
                "enum": [
                    "A_OFFICIAL_FACT",
                    "D_EDITORIAL_JUDGEMENT",
                    "UNKNOWN",
                ]
            },
            "risk_class": {"enum": ["LOW", "MEDIUM", "HIGH"]},
            "freshness": {
                "enum": [
                    "FRESH",
                    "DUE",
                    "SOFT_STALE",
                    "HARD_STALE",
                    "UNKNOWN",
                    "UNAVAILABLE",
                    "REJECTED",
                ]
            },
            "authoritative_source_status": {
                "enum": ["DRAFT", "VERIFIED", "STALE", "BLOCKED"]
            },
            "checked_at": {
                "type": "string",
                "pattern": DATETIME_PATTERN,
                "format": "date-time",
            },
            "next_review_at": {
                "type": "string",
                "pattern": DATETIME_PATTERN,
                "format": "date-time",
            },
            "resolved": {"type": "boolean"},
            "blocking": {"type": "boolean"},
            "intentionally_disclosed": {"type": "boolean"},
        },
        "additionalProperties": False,
    }
    review_candidate = {
        "type": "object",
        "required": [
            "schema",
            "version",
            "phase2_candidate",
            "candidate_digest",
            "claim_bindings",
            "update_payload",
            "preaction_status",
            "preaction_binding_digest",
            "structured_data_expectation_sha256",
            "payload_digest",
        ],
        "properties": {
            "schema": {"const": "RAOS_V2_PHASE3_REVIEW_CANDIDATE_V1"},
            "version": {"const": "1.0.0"},
            "phase2_candidate": {
                "$ref": "https://kurashinoshirube.com/contracts/raos-v2/v1/publication-package.schema.json"
            },
            "candidate_digest": {"type": "string", "pattern": HEX64_PATTERN},
            "claim_bindings": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": claim_binding,
            },
            "update_payload": {
                "$ref": "https://kurashinoshirube.com/contracts/raos-v2/v2/wordpress-update-payload.schema.json"
            },
            "preaction_status": {
                "enum": ["HISTORICAL_BASELINE_ONLY", "VERIFIED_PREACTION"]
            },
            "preaction_binding_digest": {
                "type": ["string", "null"],
                "pattern": HEX64_PATTERN,
            },
            "structured_data_expectation_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "payload_digest": {"type": "string", "pattern": HEX64_PATTERN},
        },
        "additionalProperties": False,
        "allOf": [
            {
                "if": {
                    "properties": {
                        "preaction_status": {"const": "HISTORICAL_BASELINE_ONLY"}
                    }
                },
                "then": {"properties": {"preaction_binding_digest": {"type": "null"}}},
            },
            {
                "if": {
                    "properties": {"preaction_status": {"const": "VERIFIED_PREACTION"}}
                },
                "then": {
                    "properties": {
                        "preaction_binding_digest": {
                            "type": "string",
                            "pattern": HEX64_PATTERN,
                        }
                    }
                },
            },
        ],
    }
    return _v2_object_schema(
        "publication-package",
        (
            "schema",
            "version",
            "state",
            "review_candidate",
            "human_review_receipt",
            "simulation_only",
            "approval_acceptance_authority",
            "structured_data_expectation_sha256",
            "capabilities",
            "package_digest",
        ),
        {
            "schema": {"const": "RAOS_V2_PHASE3_PUBLICATION_PACKAGE_V1"},
            "version": {"const": "1.0.0"},
            "state": {"enum": ["HUMAN_REVIEWED", "PACKAGE_SEALED"]},
            "review_candidate": review_candidate,
            "human_review_receipt": {
                "$ref": "https://kurashinoshirube.com/contracts/raos-v2/v2/human-review-receipt.schema.json"
            },
            "simulation_only": {"const": True},
            "approval_acceptance_authority": {"const": False},
            "structured_data_expectation_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "capabilities": {
                "type": "object",
                "required": ["network", "wordpress_write", "publish"],
                "properties": {
                    "network": {"const": False},
                    "wordpress_write": {"const": False},
                    "publish": {"const": False},
                },
                "additionalProperties": False,
            },
            "package_digest": {
                "type": ["string", "null"],
                "pattern": HEX64_PATTERN,
            },
        },
        all_of=[
            {
                "if": {"properties": {"state": {"const": "PACKAGE_SEALED"}}},
                "then": {
                    "properties": {
                        "package_digest": {
                            "type": "string",
                            "pattern": HEX64_PATTERN,
                        }
                    }
                },
            },
            {
                "if": {"properties": {"state": {"const": "HUMAN_REVIEWED"}}},
                "then": {"properties": {"package_digest": {"type": "null"}}},
            },
        ],
    )


def phase3_reissued_review_bundle_schema() -> dict[str, object]:
    publication_schema = phase3_publication_package_schema()
    publication_properties = publication_schema.get("properties")
    if not isinstance(publication_properties, dict):
        fail("RAOS_V2_PHASE3_REISSUED_REVIEW_SCHEMA_INVALID")
    review_candidate = publication_properties.get("review_candidate")
    if not isinstance(review_candidate, dict):
        fail("RAOS_V2_PHASE3_REISSUED_REVIEW_SCHEMA_INVALID")
    source = {
        "type": "object",
        "required": [
            "historical_review_candidate",
            "historical_review_candidate_sha256",
            "preaction_input",
            "preaction_input_sha256",
            "preaction_binding_sha256",
        ],
        "properties": {
            "historical_review_candidate": {
                "const": "changes/raos-v2/phase-3/generated/review-candidate.v1.json"
            },
            "historical_review_candidate_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "preaction_input": {
                "type": "string",
                "pattern": (
                    r"^changes/raos-v2/recorded-inputs/phase3/"
                    r"[A-Za-z0-9][A-Za-z0-9._-]*\.json$"
                ),
            },
            "preaction_input_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "preaction_binding_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
        },
        "additionalProperties": False,
    }
    review_request = {
        "type": "object",
        "required": [
            "required_receipt_schema",
            "candidate_digest",
            "payload_digest",
            "target_route",
            "generic_approval_accepted",
            "artifact_specific_review_required",
        ],
        "properties": {
            "required_receipt_schema": {
                "const": "RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_V1"
            },
            "candidate_digest": {"type": "string", "pattern": HEX64_PATTERN},
            "payload_digest": {"type": "string", "pattern": HEX64_PATTERN},
            "target_route": {"const": "/carry-on-suitcase-comparison/"},
            "generic_approval_accepted": {"const": False},
            "artifact_specific_review_required": {"const": True},
        },
        "additionalProperties": False,
    }
    return _v2_object_schema(
        "reissued-review-bundle",
        (
            "schema",
            "version",
            "classification",
            "state",
            "reissued_at",
            "reissue_age_milliseconds",
            "public_capture_age_milliseconds",
            "owner_export_age_milliseconds",
            "maximum_reissue_age_seconds",
            "source",
            "review_candidate",
            "candidate_digest",
            "payload_digest",
            "review_request",
            "capabilities",
            "external_actions",
            "review_bundle_sha256",
        ),
        {
            "schema": {"const": "RAOS_V2_PHASE3_REISSUED_REVIEW_BUNDLE_V1"},
            "version": {"const": "1.0.0"},
            "classification": {
                "const": "LOCAL_REISSUE_FOR_ARTIFACT_SPECIFIC_HUMAN_REVIEW"
            },
            "state": {"const": "READY_FOR_ARTIFACT_SPECIFIC_HUMAN_REVIEW"},
            "reissued_at": {
                "type": "string",
                "pattern": DATETIME_PATTERN,
                "format": "date-time",
            },
            "reissue_age_milliseconds": {
                "type": "integer",
                "minimum": 0,
                "maximum": 300000,
            },
            "public_capture_age_milliseconds": {
                "type": "integer",
                "minimum": 0,
                "maximum": 300000,
            },
            "owner_export_age_milliseconds": {
                "type": "integer",
                "minimum": 0,
                "maximum": 300000,
            },
            "maximum_reissue_age_seconds": {"const": 300},
            "source": source,
            "review_candidate": deepcopy(review_candidate),
            "candidate_digest": {"type": "string", "pattern": HEX64_PATTERN},
            "payload_digest": {"type": "string", "pattern": HEX64_PATTERN},
            "review_request": review_request,
            "capabilities": {
                "type": "object",
                "required": ["network", "wordpress_read", "wordpress_write", "publish"],
                "properties": {
                    "network": {"const": False},
                    "wordpress_read": {"const": False},
                    "wordpress_write": {"const": False},
                    "publish": {"const": False},
                },
                "additionalProperties": False,
            },
            "external_actions": {"const": "NOT_EXECUTED"},
            "review_bundle_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
        },
    )


def phase3_wordpress_cutover_binding_schema() -> dict[str, object]:
    """Closed deployment guard binding for the one Phase 3 WordPress route."""

    digest_or_unavailable = {
        "oneOf": [
            {"type": "string", "pattern": HEX64_PATTERN},
            {"const": "UNAVAILABLE"},
        ]
    }
    return _v2_object_schema(
        "wordpress-cutover-binding",
        ("schema", "version", "state", "target", "hashes"),
        {
            "schema": {"const": "RAOS_V2_WORDPRESS_CUTOVER_BINDING_V1"},
            "version": {"const": "1.0.0"},
            "state": {
                "enum": [
                    "DEPLOYMENT_DISABLED",
                    "ARMED_EXACT_LEGACY_OR_SEALED",
                ]
            },
            "target": {
                "type": "object",
                "required": ["article_id", "post_id", "post_slug", "route"],
                "properties": {
                    "article_id": {"const": "A05"},
                    "post_id": {"type": "integer", "minimum": 0},
                    "post_slug": {"const": "carry-on-suitcase-comparison"},
                    "route": {"const": "/carry-on-suitcase-comparison/"},
                },
                "additionalProperties": False,
            },
            "hashes": {
                "type": "object",
                "required": [
                    "legacy_post_content_sha256",
                    "sealed_post_content_sha256",
                    "source_owner_export_sha256",
                    "preaction_binding_sha256",
                    "sealed_package_sha256",
                ],
                "properties": {
                    "legacy_post_content_sha256": deepcopy(digest_or_unavailable),
                    "sealed_post_content_sha256": {
                        "type": "string",
                        "pattern": HEX64_PATTERN,
                    },
                    "source_owner_export_sha256": deepcopy(digest_or_unavailable),
                    "preaction_binding_sha256": deepcopy(digest_or_unavailable),
                    "sealed_package_sha256": deepcopy(digest_or_unavailable),
                },
                "additionalProperties": False,
            },
        },
        all_of=[
            {
                "if": {
                    "properties": {"state": {"const": "DEPLOYMENT_DISABLED"}},
                    "required": ["state"],
                },
                "then": {
                    "properties": {
                        "target": {"properties": {"post_id": {"const": 0}}},
                        "hashes": {
                            "properties": {
                                name: {"const": "UNAVAILABLE"}
                                for name in (
                                    "legacy_post_content_sha256",
                                    "source_owner_export_sha256",
                                    "preaction_binding_sha256",
                                    "sealed_package_sha256",
                                )
                            }
                        },
                    }
                },
                "else": {
                    "properties": {
                        "target": {
                            "properties": {"post_id": {"type": "integer", "minimum": 1}}
                        },
                        "hashes": {
                            "properties": {
                                name: {"type": "string", "pattern": HEX64_PATTERN}
                                for name in (
                                    "legacy_post_content_sha256",
                                    "source_owner_export_sha256",
                                    "preaction_binding_sha256",
                                    "sealed_package_sha256",
                                )
                            }
                        },
                    }
                },
            }
        ],
    )


def phase3_wordpress_dry_run_receipt_schema() -> dict[str, object]:
    field_diff = {
        "type": "object",
        "required": ["field", "before_sha256", "after_sha256", "changed"],
        "properties": {
            "field": {
                "enum": [
                    "canonical_url",
                    "comment_status",
                    "meta_description",
                    "ping_status",
                    "post_content",
                    "post_excerpt",
                    "post_name",
                    "post_status",
                    "post_title",
                ]
            },
            "before_sha256": {"type": "string", "pattern": HEX64_PATTERN},
            "after_sha256": {"type": "string", "pattern": HEX64_PATTERN},
            "changed": {"type": "boolean"},
        },
        "additionalProperties": False,
    }
    return _v2_object_schema(
        "wordpress-dry-run-receipt",
        (
            "schema",
            "version",
            "mode",
            "request_count",
            "external_action_count",
            "external_status",
            "status",
            "intent",
            "target",
            "package_digest",
            "payload_digest",
            "export_binding_sha256",
            "preconditions",
            "postconditions",
            "field_diff",
            "idempotency_key",
        ),
        {
            "schema": {"const": "RAOS_V2_PHASE3_WORDPRESS_DRY_RUN_RECEIPT_V1"},
            "version": {"const": "1.0.0"},
            "mode": {"const": "DISABLED_DRY_RUN"},
            "request_count": {"const": 0},
            "external_action_count": {"const": 0},
            "external_status": {"const": "NOT_EXECUTED"},
            "status": {"const": "DRY_RUN"},
            "intent": {"const": "UPDATE_EXISTING_PUBLISHED_POST_AT_APPROVED_CUTOVER"},
            "target": {
                "type": "object",
                "required": [
                    "origin",
                    "route",
                    "kind",
                    "post_id",
                    "expected_match_count",
                ],
                "properties": {
                    "origin": {"const": "https://kurashinoshirube.com"},
                    "route": {"const": "/carry-on-suitcase-comparison/"},
                    "kind": {"const": "EXISTING_POST"},
                    "post_id": {"type": "integer", "minimum": 1},
                    "expected_match_count": {"const": 1},
                },
                "additionalProperties": False,
            },
            "package_digest": {"type": "string", "pattern": HEX64_PATTERN},
            "payload_digest": {"type": "string", "pattern": HEX64_PATTERN},
            "export_binding_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "preconditions": {
                "type": "object",
                "required": [
                    "export_role",
                    "expected_current_post_status",
                    "before_post_status_sha256",
                    "expected_public_body_sha256",
                    "observed_public_body_sha256",
                    "export_captured_at",
                    "human_reviewed_at",
                    "preaction_status",
                    "preaction_binding_sha256",
                    "observed_preaction_binding_sha256",
                    "preaction_captured_at",
                    "evaluated_at",
                    "max_export_age_seconds",
                    "satisfied",
                ],
                "properties": {
                    "export_role": {"const": "PRE_WRITE_EXPORT"},
                    "expected_current_post_status": {"const": "publish"},
                    "before_post_status_sha256": {
                        "const": (
                            "f25fde75eb12c3cb5c9f8108e6d53c165d19d8bd2aac192e"
                            "37fa68f7d6312aa7"
                        )
                    },
                    "expected_public_body_sha256": {
                        "type": "string",
                        "pattern": HEX64_PATTERN,
                    },
                    "observed_public_body_sha256": {
                        "type": "string",
                        "pattern": HEX64_PATTERN,
                    },
                    "export_captured_at": {
                        "type": "string",
                        "pattern": DATETIME_PATTERN,
                        "format": "date-time",
                    },
                    "human_reviewed_at": {
                        "type": "string",
                        "pattern": DATETIME_PATTERN,
                        "format": "date-time",
                    },
                    "preaction_status": {"const": "VERIFIED_PREACTION"},
                    "preaction_binding_sha256": {
                        "type": "string",
                        "pattern": HEX64_PATTERN,
                    },
                    "observed_preaction_binding_sha256": {
                        "type": "string",
                        "pattern": HEX64_PATTERN,
                    },
                    "preaction_captured_at": {
                        "type": "string",
                        "pattern": DATETIME_PATTERN,
                        "format": "date-time",
                    },
                    "evaluated_at": {
                        "type": "string",
                        "pattern": DATETIME_PATTERN,
                        "format": "date-time",
                    },
                    "max_export_age_seconds": {"const": 300},
                    "satisfied": {"const": True},
                },
                "additionalProperties": False,
            },
            "postconditions": {
                "type": "object",
                "required": [
                    "required_after_post_status",
                    "after_post_status_sha256",
                    "satisfied",
                ],
                "properties": {
                    "required_after_post_status": {"const": "publish"},
                    "after_post_status_sha256": {
                        "const": (
                            "f25fde75eb12c3cb5c9f8108e6d53c165d19d8bd2aac192e"
                            "37fa68f7d6312aa7"
                        )
                    },
                    "satisfied": {"const": True},
                },
                "additionalProperties": False,
            },
            "field_diff": {
                "type": "array",
                "minItems": 9,
                "maxItems": 9,
                "uniqueItems": True,
                "items": field_diff,
                "allOf": [
                    {
                        "contains": {
                            "type": "object",
                            "properties": {"field": {"const": field_name}},
                            "required": ["field"],
                        },
                        "minContains": 1,
                        "maxContains": 1,
                    }
                    for field_name in (
                        "canonical_url",
                        "comment_status",
                        "meta_description",
                        "ping_status",
                        "post_content",
                        "post_excerpt",
                        "post_name",
                        "post_status",
                        "post_title",
                    )
                ],
            },
            "idempotency_key": {"type": "string", "pattern": HEX64_PATTERN},
        },
    )


def phase3_wordpress_export_binding_schema() -> dict[str, object]:
    field_names = [
        "canonical_url",
        "comment_status",
        "meta_description",
        "ping_status",
        "post_content",
        "post_excerpt",
        "post_name",
        "post_status",
        "post_title",
    ]
    return _v2_object_schema(
        "wordpress-export-binding",
        (
            "schema",
            "version",
            "target",
            "captured_at",
            "field_hashes",
            "public_body_sha256",
            "preaction_binding_sha256",
            "export_sha256",
            "export_bytes",
            "restore_artifact_sha256",
            "theme_artifact_sha256",
            "seo_state_sha256",
            "redirect_map_sha256",
            "sitemap_state_sha256",
            "raw_export_location",
            "status",
            "export_role",
        ),
        {
            "schema": {"const": "RAOS_V2_WORDPRESS_EXPORT_BINDING_V2"},
            "version": {"const": "2.0.0"},
            "target": {
                "type": "object",
                "required": [
                    "origin",
                    "route",
                    "kind",
                    "post_id",
                    "exact_match_count",
                ],
                "properties": {
                    "origin": {"const": "https://kurashinoshirube.com"},
                    "route": {"const": "/carry-on-suitcase-comparison/"},
                    "kind": {"const": "EXISTING_POST"},
                    "post_id": {"type": "integer", "minimum": 1},
                    "exact_match_count": {"const": 1},
                },
                "additionalProperties": False,
            },
            "public_body_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "preaction_binding_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "export_sha256": {"type": "string", "pattern": HEX64_PATTERN},
            "export_bytes": {"type": "integer", "minimum": 1},
            "captured_at": {
                "type": "string",
                "pattern": DATETIME_PATTERN,
                "format": "date-time",
            },
            "field_hashes": {
                "type": "object",
                "required": field_names,
                "properties": {
                    **{
                        name: {"type": "string", "pattern": HEX64_PATTERN}
                        for name in field_names
                    },
                    "post_status": {
                        "const": (
                            "f25fde75eb12c3cb5c9f8108e6d53c165d19d8bd2aac192e"
                            "37fa68f7d6312aa7"
                        )
                    },
                },
                "additionalProperties": False,
            },
            "restore_artifact_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "theme_artifact_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "seo_state_sha256": {"type": "string", "pattern": HEX64_PATTERN},
            "redirect_map_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "sitemap_state_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "raw_export_location": {"const": "OWNER_STORAGE_ONLY_NOT_GIT"},
            "status": {"const": "VERIFIED_HUMAN_EXPORT"},
            "export_role": {"enum": ["PRE_WRITE_EXPORT", "POST_ACTION_OWNER_EXPORT"]},
        },
    )


def phase3_public_verification_receipt_schema() -> dict[str, object]:
    return _v2_object_schema(
        "public-verification-receipt",
        (
            "schema",
            "version",
            "derivation",
            "evidence_class",
            "completion_scope",
            "capture_sha256",
            "preaction_capture_sha256",
            "post_action_export_binding_sha256",
            "target",
            "observed_at",
            "evaluated_at",
            "max_capture_age_seconds",
            "status",
            "redirect_chain",
            "canonical",
            "canonical_tag_count",
            "head_tag_count",
            "metadata_location_violation_count",
            "robots",
            "robots_meta",
            "robots_http",
            "robots_http_indexability_safe",
            "content_type_media_type",
            "refresh_http_present",
            "link_http_sha256",
            "robots_txt_status",
            "robots_txt_sha256",
            "robots_txt_target_allowed_for_googlebot",
            "indexability_evidence_scope",
            "robots_tag_count",
            "crawler_robots_tag_count",
            "crawler_robots_indexability_safe",
            "sitemap_membership",
            "title",
            "title_tag_count",
            "meta_description",
            "meta_description_tag_count",
            "h1",
            "h1_count",
            "body_sha256",
            "package_digest",
            "structured_data_expectation_sha256",
            "post_content_semantic_sha256",
            "sealed_post_content_sha256",
            "package_marker",
            "package_marker_count",
            "package_marker_attribute_count",
            "post_content_envelope",
            "post_content_envelope_count",
            "post_content_envelope_attribute_count",
            "blocked_post_content_envelope_count",
            "post_content_envelope_marker_child_count",
            "post_content_envelope_valid",
            "post_content_marker_subtree_count",
            "disclosure_marker_present",
            "disclosure_marker_count",
            "cta_state_count",
            "blocked_cta_count",
            "affiliate_url_count",
            "ambiguous_attribute_count",
            "image_count",
            "inline_executable_script_count",
            "external_script_count",
            "resource_inventory_sha256",
            "resource_change_status",
            "plugin_stylesheet_url",
            "plugin_stylesheet_resource_sha256",
            "plugin_stylesheet_content_sha256",
            "plugin_stylesheet_bytes",
            "plugin_php_sha256",
            "plugin_manifest_sha256",
            "plugin_artifact_status",
            "json_ld_script_count",
            "json_ld_sha256",
            "json_ld_types",
            "json_ld_visible_content_match",
            "critical_issue_count",
            "public_browser_verification_status",
            "phase_exit_eligible",
            "rollback_invoked",
        ),
        {
            "schema": {"const": "RAOS_V2_PUBLIC_VERIFICATION_RECEIPT_V2"},
            "version": {"const": "2.0.0"},
            "derivation": {
                "const": "STRICT_PREACTION_CAPTURE_SEALED_PACKAGE_POST_ACTION_EXPORT_V2"
            },
            "evidence_class": {"const": "PUBLIC_READ_ONLY_HTTP_AND_OWNER_EXPORT"},
            "completion_scope": {"const": "HTTP_AND_OWNER_EXPORT_ONLY"},
            "capture_sha256": {"type": "string", "pattern": HEX64_PATTERN},
            "preaction_capture_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "post_action_export_binding_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "target": {
                "type": "object",
                "required": ["origin", "route"],
                "properties": {
                    "origin": {"const": "https://kurashinoshirube.com"},
                    "route": {"const": "/carry-on-suitcase-comparison/"},
                },
                "additionalProperties": False,
            },
            "observed_at": {
                "type": "string",
                "pattern": DATETIME_PATTERN,
                "format": "date-time",
            },
            "evaluated_at": {
                "type": "string",
                "pattern": DATETIME_PATTERN,
                "format": "date-time",
            },
            "max_capture_age_seconds": {"const": 300},
            "status": {"const": 200},
            "redirect_chain": {"const": []},
            "canonical": {
                "const": "https://kurashinoshirube.com/carry-on-suitcase-comparison/"
            },
            "canonical_tag_count": {"const": 1},
            "head_tag_count": {"const": 1},
            "metadata_location_violation_count": {"const": 0},
            "robots": {"const": "index,follow"},
            "robots_meta": {"const": "index,follow"},
            "robots_http": {
                "type": "string",
                "pattern": (
                    r"^(?:UNAVAILABLE|(?!.*(?:^|,)(?:noindex|nofollow|none)"
                    r"(?:,|$))[a-z][a-z0-9:-]*(?:,[a-z][a-z0-9:-]*)*)$"
                ),
            },
            "robots_http_indexability_safe": {"const": True},
            "content_type_media_type": {"const": "text/html"},
            "refresh_http_present": {"const": False},
            "link_http_sha256": {
                "type": "string",
                "pattern": r"^(?:UNAVAILABLE|[0-9a-f]{64})$",
            },
            "robots_txt_status": {
                "type": "integer",
                "enum": [200, 404, 410],
            },
            "robots_txt_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "robots_txt_target_allowed_for_googlebot": {"const": True},
            "indexability_evidence_scope": {
                "const": "HEAD_META_HTTP_SITEMAP_AND_ROBOTS_TXT"
            },
            "robots_tag_count": {"const": 1},
            "crawler_robots_tag_count": {"type": "integer", "minimum": 0},
            "crawler_robots_indexability_safe": {"const": True},
            "sitemap_membership": {"const": True},
            "title": {"type": "string", "minLength": 1},
            "title_tag_count": {"const": 1},
            "meta_description": {"type": "string", "minLength": 1},
            "meta_description_tag_count": {"const": 1},
            "h1": {"type": "string", "minLength": 1},
            "h1_count": {"const": 1},
            "body_sha256": {"type": "string", "pattern": HEX64_PATTERN},
            "package_digest": {"type": "string", "pattern": HEX64_PATTERN},
            "structured_data_expectation_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "post_content_semantic_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "sealed_post_content_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "package_marker": {"const": "RAOS_V2_A05_POST_CONTENT_V1"},
            "package_marker_count": {"const": 1},
            "package_marker_attribute_count": {"const": 1},
            "post_content_envelope": {"const": "RAOS_V2_A05_ENVELOPE_V1"},
            "post_content_envelope_count": {"const": 1},
            "post_content_envelope_attribute_count": {"const": 1},
            "blocked_post_content_envelope_count": {"const": 0},
            "post_content_envelope_marker_child_count": {"const": 1},
            "post_content_envelope_valid": {"const": True},
            "post_content_marker_subtree_count": {"const": 1},
            "disclosure_marker_present": {"const": True},
            "disclosure_marker_count": {"const": 1},
            "cta_state_count": {"const": 3},
            "blocked_cta_count": {"const": 3},
            "affiliate_url_count": {"const": 0},
            "ambiguous_attribute_count": {"const": 0},
            "image_count": {"type": "integer", "minimum": 0},
            "inline_executable_script_count": {
                "type": "integer",
                "minimum": 0,
            },
            "external_script_count": {"type": "integer", "minimum": 0},
            "resource_inventory_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "resource_change_status": {"const": "NO_UNAPPROVED_NEW_TRACKED_RESOURCE"},
            "plugin_stylesheet_url": {
                "const": (
                    "https://kurashinoshirube.com/wp-content/plugins/"
                    "raos-v2-decision-support/assets/decision-support.css"
                )
            },
            "plugin_stylesheet_resource_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "plugin_stylesheet_content_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "plugin_stylesheet_bytes": {"type": "integer", "minimum": 1},
            "plugin_php_sha256": {"type": "string", "pattern": HEX64_PATTERN},
            "plugin_manifest_sha256": {
                "type": "string",
                "pattern": HEX64_PATTERN,
            },
            "plugin_artifact_status": {
                "const": "LOCAL_SOURCE_BOUND_AND_PUBLIC_CSS_MATCHED"
            },
            "json_ld_script_count": {"const": 1},
            "json_ld_sha256": {"type": "string", "pattern": HEX64_PATTERN},
            "json_ld_types": {
                "const": ["Article", "BreadcrumbList", "Organization", "WebSite"]
            },
            "json_ld_visible_content_match": {"const": True},
            "critical_issue_count": {"const": 0},
            "public_browser_verification_status": {
                "const": "SEPARATE_RECEIPT_REQUIRED"
            },
            "phase_exit_eligible": {"const": False},
            "rollback_invoked": {"const": False},
        },
    )


def phase3_public_browser_verification_receipt_schema() -> dict[str, object]:
    """Strict future receipt for the separately approved public browser gate."""

    viewport = {
        "type": "object",
        "required": [
            "width",
            "height",
            "screenshot_sha256",
            "screenshot_bytes",
            "disclosure_computed_visible",
            "cta_state_count",
            "blocked_cta_count",
            "visible_blocked_cta_count",
            "keyboard_only_passed",
            "zoom_200_percent_passed",
            "horizontal_overflow",
            "axe_critical_count",
            "axe_serious_count",
        ],
        "properties": {
            "width": {"enum": [390, 768, 1440]},
            "height": {"type": "integer", "minimum": 1},
            "screenshot_sha256": {"type": "string", "pattern": HEX64_PATTERN},
            "screenshot_bytes": {"type": "integer", "minimum": 1},
            "disclosure_computed_visible": {"const": True},
            "cta_state_count": {"const": 3},
            "blocked_cta_count": {"const": 3},
            "visible_blocked_cta_count": {"const": 3},
            "keyboard_only_passed": {"const": True},
            "zoom_200_percent_passed": {"const": True},
            "horizontal_overflow": {"const": False},
            "axe_critical_count": {"const": 0},
            "axe_serious_count": {"const": 0},
        },
        "additionalProperties": False,
    }
    return _v2_object_schema(
        "public-browser-verification-receipt",
        (
            "schema",
            "version",
            "classification",
            "verification_status",
            "acceptance_authority",
            "phase_exit_eligible",
            "derivation",
            "evidence_class",
            "target",
            "observed_at",
            "raw_capture_location",
            "independent_recalculation_status",
            "browser",
            "bindings",
            "viewports",
            "network",
            "summary",
            "critical_issue_count",
        ),
        {
            "schema": {
                "const": "RAOS_V2_PHASE3_PUBLIC_BROWSER_VERIFICATION_RECEIPT_V1"
            },
            "version": {"const": "1.0.0"},
            "classification": {
                "const": "UNVERIFIED_EXTERNAL_TEMPLATE_NO_ACCEPTANCE_AUTHORITY"
            },
            "verification_status": {"const": "REQUIRED_VALIDATOR_NOT_IMPLEMENTED"},
            "acceptance_authority": {"const": False},
            "phase_exit_eligible": {"const": False},
            "derivation": {"const": "PROPOSED_PUBLIC_READ_ONLY_BROWSER_CAPTURE_V1"},
            "evidence_class": {"const": "UNVERIFIED_EXTERNAL_TEMPLATE"},
            "target": {
                "type": "object",
                "required": ["origin", "route"],
                "properties": {
                    "origin": {"const": "https://kurashinoshirube.com"},
                    "route": {"const": "/carry-on-suitcase-comparison/"},
                },
                "additionalProperties": False,
            },
            "observed_at": {
                "type": "string",
                "pattern": DATETIME_PATTERN,
                "format": "date-time",
            },
            "raw_capture_location": {"const": "OWNER_CONTROLLED_NOT_GIT"},
            "independent_recalculation_status": {"const": "NOT_IMPLEMENTED"},
            "browser": {
                "type": "object",
                "required": [
                    "engine",
                    "version",
                    "axe_version",
                    "executable_sha256",
                    "harness_sha256",
                    "command_sha256",
                ],
                "properties": {
                    "engine": {"const": "CHROMIUM"},
                    "version": {"type": "string", "minLength": 1},
                    "axe_version": {"const": "4.12.1"},
                    "executable_sha256": {
                        "type": "string",
                        "pattern": HEX64_PATTERN,
                    },
                    "harness_sha256": {
                        "type": "string",
                        "pattern": HEX64_PATTERN,
                    },
                    "command_sha256": {
                        "type": "string",
                        "pattern": HEX64_PATTERN,
                    },
                },
                "additionalProperties": False,
            },
            "bindings": {
                "type": "object",
                "required": [
                    "public_verification_receipt_sha256",
                    "body_sha256",
                    "package_digest",
                    "post_content_semantic_sha256",
                    "plugin_artifact_sha256",
                    "plugin_css_sha256",
                ],
                "properties": {
                    name: {"type": "string", "pattern": HEX64_PATTERN}
                    for name in (
                        "public_verification_receipt_sha256",
                        "body_sha256",
                        "package_digest",
                        "post_content_semantic_sha256",
                        "plugin_artifact_sha256",
                        "plugin_css_sha256",
                    )
                },
                "additionalProperties": False,
            },
            "viewports": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "uniqueItems": True,
                "items": viewport,
                "allOf": [
                    {
                        "contains": {
                            "type": "object",
                            "properties": {"width": {"const": width}},
                            "required": ["width"],
                        },
                        "minContains": 1,
                        "maxContains": 1,
                    }
                    for width in (390, 768, 1440)
                ],
            },
            "network": {
                "type": "object",
                "required": [
                    "navigation_request_count",
                    "write_request_count",
                    "form_submission_count",
                    "storage_mutation_count",
                    "service_worker_registration_count",
                    "affiliate_request_count",
                    "unexpected_cross_origin_request_count",
                    "resource_manifest_sha256",
                ],
                "properties": {
                    "navigation_request_count": {"const": 1},
                    "write_request_count": {"const": 0},
                    "form_submission_count": {"const": 0},
                    "storage_mutation_count": {"const": 0},
                    "service_worker_registration_count": {"const": 0},
                    "affiliate_request_count": {"const": 0},
                    "unexpected_cross_origin_request_count": {"const": 0},
                    "resource_manifest_sha256": {
                        "type": "string",
                        "pattern": HEX64_PATTERN,
                    },
                },
                "additionalProperties": False,
            },
            "summary": {
                "type": "object",
                "required": [
                    "computed_visibility_passed",
                    "keyboard_passed",
                    "zoom_200_percent_passed",
                    "axe_wcag22aa_passed",
                    "resource_and_network_gate_passed",
                    "binding_gate_passed",
                ],
                "properties": {
                    "computed_visibility_passed": {"const": True},
                    "keyboard_passed": {"const": True},
                    "zoom_200_percent_passed": {"const": True},
                    "axe_wcag22aa_passed": {"const": True},
                    "resource_and_network_gate_passed": {"const": True},
                    "binding_gate_passed": {"const": True},
                },
                "additionalProperties": False,
            },
            "critical_issue_count": {"const": 0},
        },
    )


def analytics_event_schema() -> dict[str, object]:
    properties: dict[str, object] = {
        "schema_version": {"const": "1.0.0"},
        "event_name": {
            "enum": [
                "tool_result_view",
                "comparison_view",
                "evidence_link_open",
                "official_source_open",
                "affiliate_outbound_activate",
                "article_complete",
                "error_state_view",
            ]
        },
        "event_version": {"const": 1},
        "event_time_jst": {
            "type": "string",
            "pattern": JST_DATETIME_PATTERN,
            "format": "date-time",
        },
        "session_token_hmac": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
        "article_id": {
            "type": "string",
            "pattern": r"^[A-Z0-9][A-Z0-9._:-]{0,127}$",
        },
        "placement": {"type": "string", "pattern": r"^[a-z0-9_-]{1,64}$"},
        "consent_state": {"enum": ["UNKNOWN", "DENIED", "GRANTED"]},
        "result_state": {
            "enum": ["PASS", "FAIL", "UNKNOWN", "STALE", "BLOCKED", "NO_MATCH", None]
        },
        "product_id": {
            "type": ["string", "null"],
            "pattern": r"^PRD-[A-Z0-9-]+$",
        },
        "source_id": {
            "type": ["string", "null"],
            "pattern": r"^SRC-[A-Z0-9][A-Z0-9-]{0,127}$",
        },
    }
    null_optional = {
        name: {"type": "null"} for name in ("result_state", "source_id", "product_id")
    }
    result_required = {
        "required": ["result_state"],
        "properties": {
            "result_state": {
                "enum": ["PASS", "FAIL", "UNKNOWN", "STALE", "BLOCKED", "NO_MATCH"]
            },
            "source_id": {"type": "null"},
            "product_id": {"type": "null"},
        },
    }
    source_required = {
        "required": ["source_id"],
        "properties": {
            "result_state": {"type": "null"},
            "source_id": {
                "type": "string",
                "pattern": r"^SRC-[A-Z0-9][A-Z0-9-]{0,127}$",
            },
            "product_id": {"type": "null"},
        },
    }
    product_required = {
        "required": ["product_id"],
        "properties": {
            "result_state": {"type": "null"},
            "source_id": {"type": "null"},
            "product_id": {"type": "string", "pattern": r"^PRD-[A-Z0-9-]+$"},
        },
    }
    return _object_schema(
        "analytics-event",
        (
            "schema_version",
            "event_name",
            "event_version",
            "event_time_jst",
            "session_token_hmac",
            "article_id",
            "placement",
            "consent_state",
        ),
        properties,
        all_of=[
            {
                "if": {"properties": {"event_name": {"const": "tool_result_view"}}},
                "then": result_required,
            },
            {
                "if": {
                    "properties": {
                        "event_name": {
                            "enum": ["evidence_link_open", "official_source_open"]
                        }
                    }
                },
                "then": source_required,
            },
            {
                "if": {
                    "properties": {
                        "event_name": {"const": "affiliate_outbound_activate"}
                    }
                },
                "then": product_required,
            },
            {
                "if": {"properties": {"event_name": {"const": "error_state_view"}}},
                "then": result_required,
            },
            {
                "if": {
                    "properties": {
                        "event_name": {"enum": ["comparison_view", "article_complete"]}
                    }
                },
                "then": {"properties": null_optional},
            },
        ],
    )


def ports_contract() -> dict[str, object]:
    return {
        "schema": "RAOS_V2_PORTS_V1",
        "version": "1.0.0",
        "network_default": "DENY",
        "ports": {
            "RuleRegistryPort": {
                "input": "JourneyConditions@v1 + effective timestamp",
                "output": "ResolvedRuleVariant@v1 | UNKNOWN",
                "failure": "typed closed error; carrier is never inferred",
            },
            "ProductCatalogPort": {
                "input": "product/model id",
                "output": "ProductModel@v1",
                "failure": "UNRESOLVED; offer title is not product truth",
            },
            "RakutenSearchPort": {
                "input": "RakutenSearchRequest@v1",
                "output": "recorded envelope",
                "default_mode": "RECORDED_ONLY",
                "failure": [
                    "TIMEOUT",
                    "RATE_LIMIT",
                    "INVALID_RESPONSE",
                    "DISABLED",
                    "STALE",
                ],
            },
            "DecisionSupportPort": {
                "input": "user conditions + rules + product",
                "output": "PASS|FAIL|UNKNOWN|STALE|BLOCKED|NO_MATCH with segment reasons and sources",
                "failure": "UNKNOWN; no optimistic fallback",
            },
            "ArticleRendererPort": {
                "input": "ArticleDefinition@v1 + resolved data",
                "output": "deterministic local render",
                "failure": "BLOCKED; no partial affiliate CTA",
            },
            "PublicationPackagePort": {
                "input": "review-bound render bundle",
                "output": "local package state",
                "failure": "BLOCKED; no live write capability",
            },
            "WordPressDraftPort": {
                "input": "package",
                "output": "disabled dry-run diff receipt",
                "default_mode": "DISABLED_DRY_RUN",
                "live_write_capability": False,
                "receipt_contract": {
                    "schema_version": "1.0.0",
                    "required_fields": [
                        "schema_version",
                        "mode",
                        "external_action_count",
                        "request_count",
                        "target",
                        "intent",
                        "before",
                        "after",
                        "idempotency_key",
                        "package_digest",
                        "status",
                        "external_status",
                    ],
                    "constants": {
                        "mode": "DISABLED_DRY_RUN",
                        "external_action_count": 0,
                        "request_count": 0,
                        "intent": "CREATE_OR_UPDATE",
                        "status": "DRY_RUN",
                        "external_status": "NOT_EXECUTED",
                    },
                    "target_shape": ["origin", "route"],
                    "before_shape": ["state", "reason"],
                    "after_shape": [
                        "post_status",
                        "comment_status",
                        "ping_status",
                        "render_hash",
                    ],
                    "opaque_hex64_fields": ["idempotency_key", "package_digest"],
                },
            },
            "EventCollectorPort": {
                "input": "AnalyticsEvent@v1",
                "output": "local receipt",
                "default_mode": "LOCAL_SINK_ONLY",
                "failure": "reject forbidden event/field without PII enrichment",
            },
            "FreshnessMonitorPort": {
                "input": "source/claim/product clocks",
                "output": "FRESH|DUE|SOFT_STALE|HARD_STALE|UNKNOWN",
                "failure": "UNKNOWN or HARD_STALE safe state",
            },
        },
        "publication_transitions": [
            "DRAFT -> EVIDENCE_COMPLETE",
            "EVIDENCE_COMPLETE -> HUMAN_REVIEWED [human only; not executed Phase 0-2]",
            "HUMAN_REVIEWED -> PACKAGE_SEALED [synthetic fixture only Phase 0-2]",
            "PACKAGE_SEALED -> DRY_RUN_RECEIPT [disabled WordPress port]",
        ],
        "forbidden_capabilities": [
            "PUBLISHED transition",
            "live WordPress write",
            "live provider write",
            "credential input",
        ],
        "backlog_id": "B-V2-017",
        "test_ids": [
            "T-V2-014",
            "T-V2-034",
            "T-V2-037",
            "T-V2-038",
            "T-V2-045",
            "T-V2-046",
        ],
    }


def recorded_local_test_evidence() -> dict[str, object]:
    value = _read_json(LOCAL_TEST_EVIDENCE_INPUT_PATH)
    if (
        not isinstance(value, dict)
        or value.get("schema") != "RAOS_V2_RECORDED_LOCAL_TEST_EVIDENCE_V1"
        or value.get("status") not in {"NOT_EXECUTED", "PASSED_LOCAL"}
        or value.get("external_actions") != "NOT_EXECUTED"
        or value.get("formal_ci") != "NOT_CLAIMED"
    ):
        fail("RAOS_V2_LOCAL_TEST_EVIDENCE_INVALID")
    try:
        verification = verify_local_test_evidence(value, root=ROOT)
    except ValidationFailure:
        fail("RAOS_V2_LOCAL_TEST_EVIDENCE_INVALID")
    result = deepcopy(value)
    result["claimed_status"] = value.get("status")
    result["status"] = verification["effective_status"]
    result["binding_verification"] = verification["binding_verification"]
    result["raw_verification"] = verification["raw_verification"]
    return result


def effective_traceability(
    *, evidence_gate_passed: bool | None = None
) -> dict[str, object]:
    source = _read_yaml(SOURCE_ROOT / "07_DECISION_TRACEABILITY.yaml")
    if not isinstance(source, dict):
        fail("RAOS_V2_TRACEABILITY_INVALID")
    source_decisions = source.get("decisions")
    source_requirements = source.get("requirements")
    source_backlog = source.get("backlog")
    source_tests = source.get("tests")
    if not all(
        isinstance(rows, list)
        for rows in (
            source_decisions,
            source_requirements,
            source_backlog,
            source_tests,
        )
    ):
        fail("RAOS_V2_TRACEABILITY_INVALID")

    def indexed(rows: object) -> dict[str, dict[str, object]]:
        assert isinstance(rows, list)
        result: dict[str, dict[str, object]] = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                fail("RAOS_V2_TRACEABILITY_INVALID")
            identifier = row["id"]
            if identifier in result:
                fail("RAOS_V2_TRACEABILITY_DUPLICATE_ID")
            result[identifier] = deepcopy(row)
        return result

    decisions = indexed(source_decisions)
    requirements = indexed(source_requirements)
    backlog = indexed(source_backlog)
    tests = indexed(source_tests)
    selected_backlog_ids = {f"B-V2-{value:03d}" for value in range(1, 41)}
    selected_test_ids = {
        *(f"T-V2-{value:03d}" for value in range(1, 47)),
        "T-V2-051",
    }
    if (
        not selected_backlog_ids <= backlog.keys()
        or not selected_test_ids <= tests.keys()
    ):
        fail("RAOS_V2_TRACEABILITY_SCOPE_MISSING")

    # Build relationship unions from both sides before restricting the P0-P3
    # scope.  This repairs stale one-way lists without changing the imported
    # source layer and makes every effective edge explicitly bidirectional.
    b_to_r: dict[str, set[str]] = {
        identifier: {str(value) for value in row.get("requirement_ids", [])}
        for identifier, row in backlog.items()
    }
    b_to_t: dict[str, set[str]] = {
        identifier: {str(value) for value in row.get("test_ids", [])}
        for identifier, row in backlog.items()
    }
    r_to_d: dict[str, set[str]] = {
        identifier: {str(value) for value in row.get("decision_ids", [])}
        for identifier, row in requirements.items()
    }
    d_to_r: dict[str, set[str]] = {
        identifier: {str(value) for value in row.get("requirement_ids", [])}
        for identifier, row in decisions.items()
    }
    r_to_b: dict[str, set[str]] = {
        identifier: {str(value) for value in row.get("backlog_ids", [])}
        for identifier, row in requirements.items()
    }
    r_to_t: dict[str, set[str]] = {
        identifier: {str(value) for value in row.get("test_ids", [])}
        for identifier, row in requirements.items()
    }
    t_to_r: dict[str, set[str]] = {
        identifier: {str(value) for value in row.get("requirement_ids", [])}
        for identifier, row in tests.items()
    }
    for requirement_id, values in r_to_b.items():
        for backlog_id in values:
            b_to_r.setdefault(backlog_id, set()).add(requirement_id)
    for requirement_id, values in r_to_t.items():
        for test_id in values:
            t_to_r.setdefault(test_id, set()).add(requirement_id)
    for test_id, values in t_to_r.items():
        for requirement_id in values:
            r_to_t.setdefault(requirement_id, set()).add(test_id)
    for decision_id, values in d_to_r.items():
        for requirement_id in values:
            r_to_d.setdefault(requirement_id, set()).add(decision_id)
    for requirement_id, values in r_to_d.items():
        for decision_id in values:
            d_to_r.setdefault(decision_id, set()).add(requirement_id)

    selected_requirement_ids = {
        requirement_id
        for backlog_id in selected_backlog_ids
        for requirement_id in b_to_r.get(backlog_id, set())
    } | {
        requirement_id
        for test_id in selected_test_ids
        for requirement_id in t_to_r.get(test_id, set())
    }
    selected_decision_ids = {
        decision_id
        for requirement_id in selected_requirement_ids
        for decision_id in r_to_d.get(requirement_id, set())
    }
    # Close D<->R once in case a selected decision binds another requirement.
    selected_requirement_ids |= {
        requirement_id
        for decision_id in selected_decision_ids
        for requirement_id in d_to_r.get(decision_id, set())
    }
    selected_decision_ids |= {
        decision_id
        for requirement_id in selected_requirement_ids
        for decision_id in r_to_d.get(requirement_id, set())
    }
    if (
        not selected_requirement_ids <= requirements.keys()
        or not selected_decision_ids <= decisions.keys()
    ):
        fail("RAOS_V2_TRACEABILITY_CROSS_REFERENCE_INVALID")

    local_test = recorded_local_test_evidence()
    local_gate_passed = local_test.get("status") == "PASSED_LOCAL"
    if evidence_gate_passed is not None:
        local_gate_passed = local_gate_passed and evidence_gate_passed
    backlog_rows: list[dict[str, object]] = []
    for identifier in sorted(selected_backlog_ids):
        row = backlog[identifier]
        try:
            number = int(identifier.rsplit("-", 1)[1])
        except ValueError, IndexError:
            fail("RAOS_V2_TRACEABILITY_INVALID")
        effective = deepcopy(row)
        dependencies = {str(value) for value in effective.get("depends_on", [])}
        if identifier == "B-V2-009":
            dependencies = {f"B-V2-{value:03d}" for value in range(1, 9)}
        elif identifier == "B-V2-031":
            dependencies.add("B-V2-030")
        elif identifier == "B-V2-033":
            dependencies.update({"B-V2-027", "B-V2-029", "B-V2-030"})
        elif identifier == "B-V2-034":
            dependencies = {f"B-V2-{value:03d}" for value in range(19, 34)}
        effective["depends_on"] = sorted(dependencies)
        effective["requirement_ids"] = sorted(
            b_to_r.get(identifier, set()) & selected_requirement_ids
        )
        effective["test_ids"] = sorted(
            b_to_t.get(identifier, set()) & selected_test_ids
        )
        if number <= 18:
            implementation_status = "GENERATED_LOCAL"
        elif number <= 34:
            implementation_status = (
                "VERIFIED_LOCAL_RECORDED"
                if local_gate_passed
                else (
                    "AWAITING_LOCAL_TEST_GATE"
                    if number == 34
                    else "IMPLEMENTED_LOCAL_PENDING_GATE"
                )
            )
        elif number in {35, 36, 38, 39}:
            implementation_status = (
                "COMPLETE_LOCAL_RECORDED"
                if local_gate_passed
                else "IMPLEMENTED_LOCAL_PENDING_GATE"
            )
        elif number == 37:
            implementation_status = "REVIEW_READY_BLOCKED_EXTERNAL"
        else:
            implementation_status = "BLOCKED_EXTERNAL"
        effective["implementation_status"] = implementation_status
        effective["external_action_status"] = "NOT_EXECUTED"
        backlog_rows.append(effective)

    test_rows: list[dict[str, object]] = []
    for identifier in sorted(selected_test_ids):
        effective = deepcopy(tests[identifier])
        number = int(identifier.rsplit("-", 1)[1])
        effective["requirement_ids"] = sorted(
            t_to_r.get(identifier, set()) & selected_requirement_ids
        )
        effective["backlog_ids"] = sorted(
            backlog_id
            for backlog_id in selected_backlog_ids
            if identifier in b_to_t.get(backlog_id, set())
        )
        base_phases = (
            ["P0", "P1", "P2"]
            if number == 51
            else (
                ["P0"]
                if number in {*range(1, 7), 40}
                else ["P1"] if 7 <= number <= 19 else ["P2"]
            )
        )
        phase3_test_numbers = {4, 5, 8, 10, 23, *range(35, 47), 51}
        effective["effective_phases"] = [
            *base_phases,
            *(["P3"] if number in phase3_test_numbers else []),
        ]
        if number in phase3_test_numbers:
            effective["execution_status"] = (
                "PASSED_LOCAL_COMPONENT_RECORDED"
                if local_gate_passed
                else "LOCAL_COMPONENT_NOT_EXECUTED_RECORDED"
            )
            effective["phase3_acceptance_status"] = "BLOCKED_EXTERNAL"
        else:
            effective["execution_status"] = (
                "PASSED_LOCAL_RECORDED"
                if local_gate_passed
                else "NOT_EXECUTED_RECORDED"
            )
            effective["phase3_acceptance_status"] = "NOT_APPLICABLE"
        effective["phase3_external_execution_status"] = (
            "NOT_EXECUTED" if number in phase3_test_numbers else "NOT_APPLICABLE"
        )
        test_rows.append(effective)

    requirement_rows: list[dict[str, object]] = []
    for identifier in sorted(selected_requirement_ids):
        effective = deepcopy(requirements[identifier])
        effective["decision_ids"] = sorted(
            r_to_d.get(identifier, set()) & selected_decision_ids
        )
        effective["backlog_ids"] = sorted(
            backlog_id
            for backlog_id in selected_backlog_ids
            if identifier in b_to_r.get(backlog_id, set())
        )
        effective["test_ids"] = sorted(
            test_id
            for test_id in selected_test_ids
            if identifier in t_to_r.get(test_id, set())
        )
        requirement_rows.append(effective)

    decision_rows: list[dict[str, object]] = []
    for identifier in sorted(selected_decision_ids):
        effective = deepcopy(decisions[identifier])
        effective["requirement_ids"] = sorted(
            d_to_r.get(identifier, set()) & selected_requirement_ids
        )
        decision_rows.append(effective)

    # Validate the corrected P0-P3 backlog graph before emitting it.
    graph = {
        str(row["id"]): {str(value) for value in row.get("depends_on", [])}
        for row in backlog_rows
    }
    pending = dict(graph)
    while pending:
        ready = {
            identifier
            for identifier, dependencies in pending.items()
            if not (dependencies & pending.keys())
        }
        if not ready:
            fail("RAOS_V2_EFFECTIVE_BACKLOG_CYCLE")
        for identifier in ready:
            pending.pop(identifier)

    d_r_complete = all(
        requirement_id in r_to_d and identifier in r_to_d[requirement_id]
        for identifier in selected_decision_ids
        for requirement_id in d_to_r.get(identifier, set()) & selected_requirement_ids
    )
    r_b_complete = all(
        identifier in b_to_r.get(backlog_id, set())
        for identifier in selected_requirement_ids
        for backlog_id in selected_backlog_ids
        if backlog_id in r_to_b.get(identifier, set())
        or identifier in b_to_r.get(backlog_id, set())
    )
    r_t_complete = all(
        identifier in t_to_r.get(test_id, set())
        for identifier in selected_requirement_ids
        for test_id in selected_test_ids
        if test_id in r_to_t.get(identifier, set())
        or identifier in t_to_r.get(test_id, set())
    )
    b_t_complete = all(
        any(
            str(test_row["id"]) == test_id
            and str(backlog_row["id"]) in test_row.get("backlog_ids", [])
            for test_row in test_rows
        )
        for backlog_row in backlog_rows
        for test_id in backlog_row.get("test_ids", [])
    )
    return {
        "schema": "RAOS_V2_EFFECTIVE_TRACEABILITY_V1",
        "source": "source-package/2.0.0-design/07_DECISION_TRACEABILITY.yaml",
        "source_package_sha256": PACKAGE_SHA256,
        "clarification_overlay": "changes/raos-v2/clarifications.v1.yaml",
        "scope": ["P0", "P1", "P2", "P3"],
        "source_counts": {
            "decisions": len(decisions),
            "requirements": len(requirements),
            "backlog": len(backlog),
            "tests": len(tests),
        },
        "decisions": decision_rows,
        "requirements": requirement_rows,
        "backlog": backlog_rows,
        "tests": test_rows,
        "invariants": {
            "D_to_R_and_R_to_D_complete": d_r_complete,
            "R_to_B_and_B_to_R_complete": r_b_complete,
            "R_to_T_and_T_to_R_complete": r_t_complete,
            "B_to_T_and_T_to_B_complete": b_t_complete,
            "backlog_acyclic": not pending,
            "each_backlog_has_requirement": all(
                row.get("requirement_ids") for row in backlog_rows
            ),
            "each_backlog_has_test": all(row.get("test_ids") for row in backlog_rows),
            "B_V2_009_waits_all_phase0": backlog_rows[8].get("depends_on")
            == [f"B-V2-{value:03d}" for value in range(1, 9)],
            "B_V2_034_waits_all_phase2_builders": next(
                row for row in backlog_rows if row["id"] == "B-V2-034"
            ).get("depends_on")
            == [f"B-V2-{value:03d}" for value in range(19, 34)],
            "B_V2_040_waits_all_phase3_local_inputs": next(
                row for row in backlog_rows if row["id"] == "B-V2-040"
            ).get("depends_on")
            == ["B-V2-036", "B-V2-037", "B-V2-038", "B-V2-039"],
            "B_V2_040_is_blocked_external": next(
                row for row in backlog_rows if row["id"] == "B-V2-040"
            ).get("implementation_status")
            == "BLOCKED_EXTERNAL",
        },
    }


def phase1_validation_document(
    product: Mapping[str, object],
    routes: Mapping[str, object],
    schemas: Mapping[Path, object],
) -> dict[str, object]:
    portfolio = product.get("portfolio")
    route_rows = routes.get("routes")
    return {
        "schema": "RAOS_V2_PHASE1_VALIDATION_V1",
        "status": "GENERATED_CONTRACTS_VALIDATED",
        "checks": {
            "one_wedge": (
                product.get("wedge", {}).get("single_wedge") is True
                if isinstance(product.get("wedge"), dict)
                else False
            ),
            "portfolio_count": len(portfolio) if isinstance(portfolio, list) else -1,
            "template_count": (
                len(product.get("templates", []))
                if isinstance(product.get("templates"), list)
                else -1
            ),
            "route_count_including_home": (
                len(route_rows) if isinstance(route_rows, list) else -1
            ),
            "schema_count": len(schemas),
            "public_mutation_authorized": False,
            "network_used_by_generator": False,
            "external_actions": "NOT_EXECUTED",
        },
        "expected": {
            "portfolio_count": 25,
            "template_count": 7,
            "route_count_including_home": 26,
            "schema_count": 10,
        },
        "test_ids": [f"T-V2-{value:03d}" for value in range(7, 20)] + ["T-V2-051"],
    }


def preview_documents() -> dict[Path, bytes]:
    source_root = ROOT / "packages/web-ui/src/decision-support-v2/preview"
    renderer_path = source_root / "render_preview.py"
    try:
        specification = importlib.util.spec_from_file_location(
            "raos_v2_preview_renderer", renderer_path
        )
        if specification is None or specification.loader is None:
            fail("RAOS_V2_PREVIEW_RENDERER_IMPORT_INVALID")
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        render_pages = getattr(module, "render_pages")
        pages = _read_json(
            Path("packages/web-ui/src/decision-support-v2/preview/pages.v2.json")
        )
        css = (source_root / "styles.css").read_text(encoding="utf-8")
        javascript = (source_root / "checker.js").read_text(encoding="utf-8")
        rendered = render_pages(
            pages=pages,
            css=css,
            javascript=javascript,
        )
    except BuildFailure:
        raise
    except AttributeError, OSError, TypeError, UnicodeError, ValueError:
        fail("RAOS_V2_PREVIEW_RENDER_FAILED")
    if not isinstance(rendered, dict):
        fail("RAOS_V2_PREVIEW_RENDER_INVALID")
    paths = {
        "/": Path("changes/raos-v2/phase-2/preview/index.html"),
        "/carry-on/": Path("changes/raos-v2/phase-2/preview/carry-on/index.html"),
        "/tools/carry-on-size-checker/": Path(
            "changes/raos-v2/phase-2/preview/tools/carry-on-size-checker/index.html"
        ),
        "/guides/carry-on-baggage-rules/": Path(
            "changes/raos-v2/phase-2/preview/guides/carry-on-baggage-rules/index.html"
        ),
        "/guides/low-cost-carrier-7kg-packing/": Path(
            "changes/raos-v2/phase-2/preview/guides/low-cost-carrier-7kg-packing/index.html"
        ),
        "/carry-on-suitcase-comparison/": Path(
            "changes/raos-v2/phase-2/preview/carry-on-suitcase-comparison/index.html"
        ),
        "/guides/carry-on-bag-measurement/": Path(
            "changes/raos-v2/phase-2/preview/guides/carry-on-bag-measurement/index.html"
        ),
        "/policy/how-we-compare-carry-on-products/": Path(
            "changes/raos-v2/phase-2/preview/policy/how-we-compare-carry-on-products/index.html"
        ),
        "/differences/ace-cresta-vs-difference-vs-maxpass4/": Path(
            "changes/raos-v2/phase-2/preview/differences/ace-cresta-vs-difference-vs-maxpass4/index.html"
        ),
    }
    if set(rendered) != set(paths):
        fail("RAOS_V2_PREVIEW_ROUTE_SET_INVALID")
    result: dict[Path, bytes] = {}
    for route, path in paths.items():
        payload = rendered[route]
        if (
            not isinstance(payload, bytes)
            or not payload.startswith(b"<!doctype html>")
            or len(payload) > 1200 * 1024
        ):
            fail("RAOS_V2_PREVIEW_OUTPUT_INVALID")
        result[path] = payload
    return result


def phase3_wordpress_projection_document(
    pages: Mapping[str, object], publication: Mapping[str, object]
) -> dict[str, object]:
    renderer_path = (
        ROOT / "packages/web-ui/src/decision-support-v2/wordpress/projection.py"
    )
    try:
        specification = importlib.util.spec_from_file_location(
            "raos_v2_wordpress_projection", renderer_path
        )
        if specification is None or specification.loader is None:
            fail("RAOS_V2_PHASE3_PROJECTION_IMPORT_INVALID")
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        project = getattr(module, "project_a05_wordpress_post_content_v1")
        projection_input = deepcopy(dict(pages))
        projection_input["checked_at"] = publication.get("created_at")
        projected = project(projection_input)
    except BuildFailure:
        raise
    except AttributeError, OSError, TypeError, UnicodeError, ValueError:
        fail("RAOS_V2_PHASE3_PROJECTION_FAILED")
    if (
        not isinstance(projected, dict)
        or projected.get("schema") != "RAOS_V2_WORDPRESS_POST_CONTENT_PROJECTION_V1"
        or projected.get("article_id") != "A05"
        or projected.get("route") != "/carry-on-suitcase-comparison/"
        or projected.get("post_status") != "publish"
        or projected.get("image_count") != 0
        or projected.get("affiliate_url_count") != 0
        or projected.get("blocked_cta_count") != 3
        or projected.get("linked_internal_routes")
        != ["/about-ad-policy/", "/privacy-policy/"]
    ):
        fail("RAOS_V2_PHASE3_PROJECTION_INVALID")
    heading = projected.get("heading_contract")
    post_content = projected.get("post_content")
    if (
        not isinstance(heading, dict)
        or heading.get("document_heading_owner") != "WORDPRESS_POST_TITLE"
        or heading.get("expected_document_h1_count") != 1
        or heading.get("post_content_h1_count") != 0
        or not isinstance(post_content, str)
        or not post_content.startswith('<div class="raos-v2-decision-support"')
        or "<h1" in post_content.casefold()
        or "ローカルプレビュー" in post_content
    ):
        fail("RAOS_V2_PHASE3_PROJECTION_INVALID")
    return projected


def phase3_review_candidate_document(
    *,
    publication: Mapping[str, object],
    claim_ledger: Mapping[str, object],
    projection: Mapping[str, object],
    migration: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object], str, str]:
    python_root = str(ROOT / "python")
    if python_root not in sys.path:
        sys.path.insert(0, python_root)
    try:
        from raos.application.decision_support_v2.phase3_publication import (
            build_phase3_review_candidate,
        )
        from raos.domain.decision_support_v2.models import (
            ClaimStatus,
            ClaimType,
            FreshnessState,
            RiskClass,
        )
        from raos.domain.decision_support_v2.phase3_publication import (
            Phase3ClaimBinding,
            Phase3WordPressUpdateFields,
            Phase3WordPressUpdatePayload,
        )
        from raos.domain.decision_support_v2.publication import PublicationPackage
    except ImportError:
        fail("RAOS_V2_PHASE3_PUBLICATION_RUNTIME_IMPORT_INVALID")
    try:
        phase2_candidate = PublicationPackage.from_contract_record(publication)
    except TypeError, ValueError:
        fail("RAOS_V2_PHASE3_PUBLICATION_CANDIDATE_INVALID")
    claim_rows = claim_ledger.get("claims")
    publication_claims = publication.get("claim_evidence")
    if not isinstance(claim_rows, list) or not isinstance(publication_claims, list):
        fail("RAOS_V2_PHASE3_CLAIM_BINDING_INVALID")
    claims_by_id = {
        str(row["claim_id"]): row
        for row in claim_rows
        if isinstance(row, dict) and isinstance(row.get("claim_id"), str)
    }
    claim_bindings = []
    try:
        for evidence in publication_claims:
            if not isinstance(evidence, dict):
                fail("RAOS_V2_PHASE3_CLAIM_BINDING_INVALID")
            claim_id = evidence.get("claim_id")
            claim = claims_by_id.get(str(claim_id))
            if not isinstance(claim, dict):
                fail("RAOS_V2_PHASE3_CLAIM_BINDING_INVALID")
            claim_bindings.append(
                Phase3ClaimBinding(
                    claim_id=str(claim_id),
                    claim_type=ClaimType(str(claim.get("claim_type"))),
                    risk_class=RiskClass(str(claim.get("risk_class"))),
                    freshness=FreshnessState(str(evidence.get("freshness"))),
                    authoritative_source_status=ClaimStatus(str(claim.get("status"))),
                    checked_at=datetime.fromisoformat(str(claim.get("checked_at"))),
                    next_review_at=datetime.fromisoformat(
                        str(claim.get("next_review_at"))
                    ),
                )
            )
    except TypeError, ValueError:
        fail("RAOS_V2_PHASE3_CLAIM_BINDING_INVALID")
    public_before = migration.get("public_before")
    body_sha256 = (
        public_before.get("body_sha256") if isinstance(public_before, dict) else None
    )
    field_names = (
        "post_title",
        "post_content",
        "post_excerpt",
        "post_status",
        "comment_status",
        "ping_status",
    )
    if not isinstance(body_sha256, str) or any(
        not isinstance(projection.get(name), str) for name in field_names
    ):
        fail("RAOS_V2_PHASE3_WORDPRESS_PAYLOAD_INVALID")
    try:
        fields = Phase3WordPressUpdateFields(
            post_title=str(projection["post_title"]),
            post_content=str(projection["post_content"]),
            post_excerpt=str(projection["post_excerpt"]),
            meta_description=str(projection["post_excerpt"]),
            post_status=str(projection["post_status"]),
            comment_status=str(projection["comment_status"]),
            ping_status=str(projection["ping_status"]),
        )
        payload = Phase3WordPressUpdatePayload(
            fields=fields,
            expected_public_body_sha256=body_sha256,
        )
        candidate = build_phase3_review_candidate(
            phase2_candidate=phase2_candidate,
            claim_bindings=tuple(claim_bindings),
            update_payload=payload,
        )
    except TypeError, ValueError:
        fail("RAOS_V2_PHASE3_REVIEW_CANDIDATE_INVALID")
    blockers = candidate.seal_blockers()
    if blockers != ("PREACTION_BINDING_MISSING_OR_HISTORICAL_BASELINE_ONLY",):
        fail("RAOS_V2_PHASE3_REVIEW_CANDIDATE_BLOCKED")
    return (
        dict(payload.to_contract_record()),
        dict(candidate.to_contract_record()),
        candidate.candidate_digest,
        candidate.payload_digest,
    )


def validate_phase3_publication_closure(
    *,
    publication: Mapping[str, object],
    claim_ledger: Mapping[str, object],
    migration: Mapping[str, object],
    wordpress_payload: Mapping[str, object],
    review_candidate: Mapping[str, object],
) -> None:
    """Recompute the complete Phase 2 -> Phase 3 authority and payload closure."""

    ledger_rows = claim_ledger.get("claims")
    evidence_rows = publication.get("claim_evidence")
    binding_rows = review_candidate.get("claim_bindings")
    phase2_record = review_candidate.get("phase2_candidate")
    input_hashes = publication.get("input_hashes")
    public_before = migration.get("public_before")
    payload_target = wordpress_payload.get("target")
    payload_preconditions = wordpress_payload.get("preconditions")
    payload_postconditions = wordpress_payload.get("postconditions")
    payload_preaction = wordpress_payload.get("preaction")
    payload_structured_data = wordpress_payload.get("structured_data_expectation")
    payload_fields = wordpress_payload.get("fields")
    if not all(
        isinstance(value, dict)
        for value in (
            input_hashes,
            public_before,
            payload_target,
            payload_preconditions,
            payload_postconditions,
            payload_preaction,
            payload_structured_data,
            payload_fields,
        )
    ) or not all(
        isinstance(value, list) for value in (ledger_rows, evidence_rows, binding_rows)
    ):
        fail("RAOS_V2_PHASE3_PUBLICATION_CLOSURE_INVALID")
    assert isinstance(input_hashes, dict)
    assert isinstance(public_before, dict)
    assert isinstance(payload_target, dict)
    assert isinstance(payload_preconditions, dict)
    assert isinstance(payload_postconditions, dict)
    assert isinstance(payload_preaction, dict)
    assert isinstance(payload_structured_data, dict)
    assert isinstance(payload_fields, dict)
    assert isinstance(ledger_rows, list)
    assert isinstance(evidence_rows, list)
    assert isinstance(binding_rows, list)
    ledger_by_id = {
        str(row.get("claim_id")): row
        for row in ledger_rows
        if isinstance(row, dict) and isinstance(row.get("claim_id"), str)
    }
    evidence_by_id = {
        str(row.get("claim_id")): row
        for row in evidence_rows
        if isinstance(row, dict) and isinstance(row.get("claim_id"), str)
    }
    bindings_by_id = {
        str(row.get("claim_id")): row
        for row in binding_rows
        if isinstance(row, dict) and isinstance(row.get("claim_id"), str)
    }
    if (
        len(bindings_by_id) != len(binding_rows)
        or set(bindings_by_id) != set(evidence_by_id)
        or not set(bindings_by_id).issubset(ledger_by_id)
    ):
        fail("RAOS_V2_PHASE3_PUBLICATION_CLOSURE_INVALID")
    authority_rows: list[dict[str, object]] = []
    for claim_id in sorted(bindings_by_id):
        binding = bindings_by_id[claim_id]
        ledger = ledger_by_id[claim_id]
        evidence = evidence_by_id[claim_id]
        authority = {
            "claim_id": claim_id,
            "claim_type": binding.get("claim_type"),
            "risk_class": binding.get("risk_class"),
            "freshness": binding.get("freshness"),
            "authoritative_source_status": binding.get("authoritative_source_status"),
            "checked_at": binding.get("checked_at"),
            "next_review_at": binding.get("next_review_at"),
        }
        claim_type = authority["claim_type"]
        source_status = authority["authoritative_source_status"]
        expected_resolved = claim_type != "UNKNOWN" and source_status == "VERIFIED"
        expected_blocking = (
            source_status != "BLOCKED"
            if claim_type == "UNKNOWN"
            else source_status != "VERIFIED"
        )
        expected_disclosed = claim_type == "UNKNOWN" and source_status == "BLOCKED"
        try:
            checked_at = datetime.fromisoformat(str(authority["checked_at"]))
            next_review_at = datetime.fromisoformat(str(authority["next_review_at"]))
        except ValueError:
            fail("RAOS_V2_PHASE3_PUBLICATION_CLOSURE_INVALID")
        if (
            claim_type != ledger.get("claim_type")
            or authority["risk_class"] != ledger.get("risk_class")
            or authority["risk_class"] != evidence.get("risk_class")
            or authority["freshness"] != evidence.get("freshness")
            or source_status != ledger.get("status")
            or authority["checked_at"] != ledger.get("checked_at")
            or authority["next_review_at"] != ledger.get("next_review_at")
            or binding.get("resolved") is not expected_resolved
            or binding.get("blocking") is not expected_blocking
            or binding.get("intentionally_disclosed") is not expected_disclosed
            or checked_at.tzinfo is None
            or checked_at.utcoffset() is None
            or next_review_at.tzinfo is None
            or next_review_at.utcoffset() is None
            or next_review_at <= checked_at
        ):
            fail("RAOS_V2_PHASE3_PUBLICATION_CLOSURE_INVALID")
        authority_rows.append(authority)
    authority_document = {
        "schema": "RAOS_V2_PHASE3_CLAIM_AUTHORITY_V1",
        "version": "1.0.0",
        "claims": authority_rows,
    }
    canonical = "https://kurashinoshirube.com/carry-on-suitcase-comparison/"
    structured_document = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "headline": payload_fields.get("post_title"),
                "description": payload_fields.get("meta_description"),
                "mainEntityOfPage": {"@id": canonical},
                "url": canonical,
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": payload_fields.get("post_title"),
                        "item": canonical,
                    }
                ],
            },
            {"@type": "Organization", "url": "https://kurashinoshirube.com/"},
            {"@type": "WebSite", "url": "https://kurashinoshirube.com/"},
        ],
    }
    structured_digest = semantic_json_sha256({"documents": [structured_document]})
    expected_structured_data = {
        "schema": "RAOS_V2_PHASE3_STRUCTURED_DATA_EXPECTATION_V1",
        "version": "1.0.0",
        "derivation": "EXACT_WORDPRESS_FIELDS_V1",
        "json_ld_script_count": 1,
        "json_ld_document_count": 1,
        "json_ld_types": [
            "Article",
            "BreadcrumbList",
            "Organization",
            "WebSite",
        ],
        "emission": {
            "owner": "EXTERNAL_WORDPRESS_SEO_CONFIGURATION",
            "local_json_ld_emission": False,
            "external_configuration_status": "UNVERIFIED_EXTERNAL",
        },
        "documents": [structured_document],
        "json_ld_sha256": structured_digest,
    }
    expected_public_body = public_before.get("body_sha256")
    expected_payload_digest = semantic_json_sha256(wordpress_payload)
    if (
        phase2_record != publication
        or review_candidate.get("candidate_digest") != semantic_json_sha256(publication)
        or review_candidate.get("update_payload") != wordpress_payload
        or review_candidate.get("preaction_status") != "HISTORICAL_BASELINE_ONLY"
        or review_candidate.get("preaction_binding_digest") is not None
        or review_candidate.get("structured_data_expectation_sha256")
        != structured_digest
        or review_candidate.get("payload_digest") != expected_payload_digest
        or input_hashes.get("phase3_claim_authority")
        != semantic_json_sha256(authority_document)
        or wordpress_payload.get("schema")
        != "RAOS_V2_PHASE3_WORDPRESS_UPDATE_PAYLOAD_V1"
        or wordpress_payload.get("intent")
        != "UPDATE_EXISTING_PUBLISHED_POST_AT_APPROVED_CUTOVER"
        or payload_target
        != {
            "origin": "https://kurashinoshirube.com",
            "route": "/carry-on-suitcase-comparison/",
            "kind": "EXISTING_POST",
            "expected_match_count": 1,
            "expected_public_body_sha256": expected_public_body,
        }
        or payload_preconditions != {"expected_current_post_status": "publish"}
        or payload_postconditions != {"required_after_post_status": "publish"}
        or payload_preaction
        != {
            "status": "HISTORICAL_BASELINE_ONLY",
            "binding_digest": None,
            "binding": None,
        }
        or payload_structured_data != expected_structured_data
        or payload_fields.get("post_status") != "publish"
        or payload_fields.get("canonical_url")
        != "https://kurashinoshirube.com/carry-on-suitcase-comparison/"
    ):
        fail("RAOS_V2_PHASE3_PUBLICATION_CLOSURE_INVALID")


def phase3_plugin_artifact_documents(
    phase3_sources: Mapping[Path, object],
    *,
    post_content: str,
) -> dict[Path, bytes]:
    source_root = Path(
        "packages/web-ui/src/decision-support-v2/wordpress/plugin/"
        "raos-v2-decision-support"
    )
    source_manifest_path = source_root / "plugin-manifest.v1.json"
    source_binding_path = source_root / "cutover-binding.v1.json"
    source_php_path = source_root / "raos-v2-decision-support.php"
    source_css_path = source_root / "assets/decision-support.css"
    source_manifest = phase3_sources.get(source_manifest_path)
    source_binding = phase3_sources.get(source_binding_path)
    if not isinstance(source_manifest, dict) or not isinstance(source_binding, dict):
        fail("RAOS_V2_PHASE3_WORDPRESS_MANIFEST_INVALID")
    try:
        php = (ROOT / source_php_path).read_bytes()
        css = (ROOT / source_css_path).read_bytes()
    except OSError:
        fail("RAOS_V2_PHASE3_WORDPRESS_SOURCE_MISSING")
    post_content_sha256 = sha256(post_content.encode("utf-8"))
    expected_target = {
        "article_id": "A05",
        "exact_route": "/carry-on-suitcase-comparison/",
        "exact_post_slug": "carry-on-suitcase-comparison",
        "expected_post_id": "CUTOVER_BINDING_REQUIRED",
        "required_package_marker": "RAOS_V2_A05_POST_CONTENT_V1",
        "required_post_content_sha256": post_content_sha256,
        "rendered_content_envelope": "RAOS_V2_A05_ENVELOPE_V1",
    }
    expected_php_binding = (
        f"const RAOS_V2_DECISION_SUPPORT_POST_CONTENT_SHA256 = '{post_content_sha256}';"
    ).encode("ascii")
    expected_cutover_binding = {
        "schema": "RAOS_V2_WORDPRESS_CUTOVER_BINDING_V1",
        "version": "1.0.0",
        "state": "DEPLOYMENT_DISABLED",
        "target": {
            "article_id": "A05",
            "post_id": 0,
            "post_slug": "carry-on-suitcase-comparison",
            "route": "/carry-on-suitcase-comparison/",
        },
        "hashes": {
            "legacy_post_content_sha256": "UNAVAILABLE",
            "sealed_post_content_sha256": post_content_sha256,
            "source_owner_export_sha256": "UNAVAILABLE",
            "preaction_binding_sha256": "UNAVAILABLE",
            "sealed_package_sha256": "UNAVAILABLE",
        },
    }
    expected_cutover_contract = {
        "adjacent_file": "cutover-binding.v1.json",
        "required_schema": "RAOS_V2_WORDPRESS_CUTOVER_BINDING_V1",
        "required_version": "1.0.0",
        "tracked_state": "DEPLOYMENT_DISABLED",
        "activation_state": "ARMED_EXACT_LEGACY_OR_SEALED",
        "source": "PREACTION_OWNER_EXPORT",
        "required_hashes": [
            "legacy_post_content_sha256",
            "preaction_binding_sha256",
            "sealed_package_sha256",
            "sealed_post_content_sha256",
            "source_owner_export_sha256",
        ],
    }
    expected_runtime = {
        "allowed_effect": (
            "LEGACY_FILTERED_PASSTHROUGH_OR_SEALED_RAW_ENQUEUE_AND_ENVELOPE_"
            "OTHERWISE_BLOCK_TARGET"
        ),
        "activation_gate": "REPLACE_BINDING_THEN_ACTIVATE_BEFORE_SEALED_WRITE",
        "admin_ui": False,
        "content_filter": (
            "EXACT_RAW_DATABASE_STATE_FAIL_CLOSED_EARLIER_SEALED_FILTER_OUTPUT_"
            "DISCARDED"
        ),
        "content_context_gate": (
            "SINGULAR_TARGET_REQUEST_VERIFIED_CURRENT_POST_MAIN_QUERY_MAIN_LOOP"
        ),
        "content_filter_position": "TERMINATE_503_IF_NOT_LAST_AT_PHP_INT_MAX",
        "cron": False,
        "database_write": False,
        "disabled_binding_behavior": "BLOCK_TARGET_ROUTE",
        "exact_legacy_behavior": (
            "PRESERVE_EXISTING_FILTERED_CONTENT_WITHOUT_CSS_OR_ENVELOPE"
        ),
        "exact_sealed_behavior": (
            "DISCARD_FILTERED_CANDIDATE_AND_ENVELOPE_EXACT_RAW_REVIEWED_"
            "FRAGMENT_WITH_CSS"
        ),
        "inactive_behavior": (
            "NO_RUNTIME_EFFECT_WRITE_BEFORE_ACTIVATION_IS_UNPROTECTED_AND_" "PROHIBITED"
        ),
        "ambiguous_content_behavior": "BLOCK_TARGET_ROUTE",
        "intermediate_content_behavior": "BLOCK_TARGET_ROUTE",
        "network_request": False,
        "option_write": False,
        "post_render_verification": "PUBLIC_CAPTURE_AND_BROWSER_RECEIPT_REQUIRED",
        "publication_capability": False,
        "rest_route": False,
        "secondary_content_behavior": (
            "PRESERVE_FILTERED_INPUT_ONLY_FOR_VERIFIED_DIFFERENT_CURRENT_POST"
        ),
        "safe_cutover_order": [
            "REPLACE_DISABLED_BINDING_WITH_OWNER_EXPORT_BOUND_ARTIFACT",
            "ACTIVATE_PLUGIN_WHILE_EXACT_LEGACY_BYTES_REMAIN",
            "WRITE_EXACT_SEALED_DATABASE_BYTES",
        ],
        "telemetry": False,
    }
    if (
        source_manifest.get("schema")
        != "RAOS_V2_WORDPRESS_PRESENTATION_PLUGIN_INPUT_V1"
        or source_manifest.get("plugin_slug") != "raos-v2-decision-support"
        or source_manifest.get("version") != "0.6.0"
        or source_manifest.get("target") != expected_target
        or source_manifest.get("cutover_binding") != expected_cutover_contract
        or source_manifest.get("runtime") != expected_runtime
        or source_binding != expected_cutover_binding
        or php.count(expected_php_binding) != 1
        or php.count(b"const RAOS_V2_DECISION_SUPPORT_VERSION = '0.6.0';") != 1
        or b"trim($post->post_content)" in php
        or b"return $content;" not in php
        or b"return $envelope_open . $post->post_content . '</div>';" not in php
        or b"raos_v2_decision_support_cutover_binding()" not in php
        or b"raos_v2_decision_support_main_content_post()" not in php
        or b"raos_v2_decision_support_current_content_post()" not in php
        or b"is_main_query()" not in php
        or b"in_the_loop()" not in php
        or b"get_the_ID()" not in php
        or b"raos_v2_decision_support_enforce_final_content_filter()" not in php
        or php.count(b"wp_die(") != 1
        or b"array('response' => 503, 'exit' => true)" not in php
    ):
        fail("RAOS_V2_PHASE3_WORDPRESS_CONTENT_BINDING_INVALID")
    rows = [
        {
            "path": "raos-v2-decision-support.php",
            "bytes": len(php),
            "sha256": sha256(php),
        },
        {
            "path": "cutover-binding.v1.json",
            "bytes": len(canonical_json_bytes(source_binding)),
            "sha256": sha256(canonical_json_bytes(source_binding)),
        },
        {
            "path": "assets/decision-support.css",
            "bytes": len(css),
            "sha256": sha256(css),
        },
    ]
    manifest = {
        **deepcopy(source_manifest),
        "classification": "LOCAL_ARTIFACT_TEMPLATE_REQUIRES_OWNER_CUTOVER_BINDING",
        "files": rows,
        "artifact_sha256": sha256(canonical_json_bytes({"files": rows})),
        "source_root": source_root.as_posix(),
        "external_action_id": "EXT-004",
        "deployment_status": "NOT_EXECUTED",
        "backlog_id": "B-V2-036",
        "requirement_ids": ["R-V2-006", "R-V2-024", "R-V2-033"],
        "test_ids": ["T-V2-008", "T-V2-039", "T-V2-051"],
    }
    return {
        PHASE3_ARTIFACT_ROOT / "raos-v2-decision-support.php": php,
        PHASE3_ARTIFACT_ROOT / "assets/decision-support.css": css,
        PHASE3_ARTIFACT_ROOT
        / "cutover-binding.v1.json": canonical_json_bytes(source_binding),
        PHASE3_ARTIFACT_ROOT
        / "plugin-manifest.v1.json": canonical_json_bytes(manifest),
    }


def media_binding_state(binding: object, expected: Mapping[str, object]) -> str:
    """Return the closed media gate state for a recorded offer image binding."""

    if binding is None:
        return "NO_IMAGE_INTENTIONAL"
    required = {"source_id", "item_code", "content_sha256", "alt", "checked_at"}
    if not isinstance(binding, dict) or set(binding) != required:
        return "BLOCKED"
    if set(expected) != {"source_id", "item_code", "content_sha256"}:
        return "BLOCKED"
    source_id = binding.get("source_id")
    item_code = binding.get("item_code")
    digest = binding.get("content_sha256")
    alt = binding.get("alt")
    checked_at = binding.get("checked_at")
    if (
        not isinstance(source_id, str)
        or not source_id.startswith("SRC-")
        or not isinstance(item_code, str)
        or not item_code
        or len(item_code) > 160
        or any(character.isspace() for character in item_code)
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or not isinstance(alt, str)
        or not alt.strip()
        or len(alt) > 300
        or "<" in alt
        or not isinstance(checked_at, str)
    ):
        return "BLOCKED"
    try:
        checked = datetime.fromisoformat(checked_at)
    except ValueError:
        return "BLOCKED"
    if checked.tzinfo is None or checked.utcoffset() is None:
        return "BLOCKED"
    if any(binding.get(key) != expected.get(key) for key in expected):
        return "BLOCKED"
    return "BOUND_OFFICIAL_IMAGE"


def validate_media_policy_document(
    media: Mapping[str, object], offers: Mapping[str, object]
) -> None:
    """Validate the no-image safe default and fail-closed image binding gate."""

    binding = media.get("image_binding_contract")
    registry = media.get("product_registry")
    negatives = media.get("negative_fixtures")
    required_fields = {
        "source_id",
        "item_code",
        "content_sha256",
        "alt",
        "checked_at",
    }
    expected_products = {
        "PRD-ACE-CRESTA-06316",
        "PRD-ACE-DIFFERENCE-05721",
        "PRD-ACE-MAXPASS4-01471",
    }
    if (
        not isinstance(binding, dict)
        or set(binding.get("required_when_offer_image_ref_present", []))
        != required_fields
        or binding.get("missing_or_modified_state") != "BLOCKED"
        or binding.get("no_image_state") != "NO_IMAGE_INTENTIONAL"
        or not isinstance(registry, list)
        or not isinstance(negatives, list)
    ):
        fail("RAOS_V2_MEDIA_POLICY_INVALID")
    registry_products: set[str] = set()
    for row in registry:
        if (
            not isinstance(row, dict)
            or set(row) != {"product_id", "state", "image_binding", "render"}
            or row.get("state") != "NO_IMAGE_INTENTIONAL"
            or row.get("image_binding") is not None
            or row.get("render") != "NEUTRAL_PLACEHOLDER"
            or not isinstance(row.get("product_id"), str)
        ):
            fail("RAOS_V2_MEDIA_POLICY_INVALID")
        registry_products.add(str(row["product_id"]))
    if registry_products != expected_products:
        fail("RAOS_V2_MEDIA_POLICY_INVALID")
    negative_ids: set[str] = set()
    for row in negatives:
        if not isinstance(row, dict) or set(row) != {
            "fixture_id",
            "binding",
            "expected",
            "expected_state",
        }:
            fail("RAOS_V2_MEDIA_POLICY_INVALID")
        fixture_id = row.get("fixture_id")
        expected = row.get("expected")
        if (
            fixture_id not in {"MEDIA-MISSING-SOURCE", "MEDIA-MODIFIED-HASH"}
            or not isinstance(expected, dict)
            or media_binding_state(row.get("binding"), expected)
            != row.get("expected_state")
            or row.get("expected_state") != "BLOCKED"
        ):
            fail("RAOS_V2_MEDIA_POLICY_INVALID")
        negative_ids.add(str(fixture_id))
    if negative_ids != {"MEDIA-MISSING-SOURCE", "MEDIA-MODIFIED-HASH"}:
        fail("RAOS_V2_MEDIA_POLICY_INVALID")
    offer_rows = offers.get("offers")
    registry_by_product = {
        str(row["product_id"]): row for row in registry if isinstance(row, dict)
    }
    if not isinstance(offer_rows, list):
        fail("RAOS_V2_MEDIA_BINDING_UNRESOLVED")
    for row in offer_rows:
        observation = row.get("offer_observation") if isinstance(row, dict) else None
        if not isinstance(observation, dict):
            fail("RAOS_V2_MEDIA_BINDING_UNRESOLVED")
        registry_row = registry_by_product.get(str(observation.get("product_id")))
        if not isinstance(registry_row, dict):
            fail("RAOS_V2_MEDIA_BINDING_UNRESOLVED")
        if observation.get("image_ref") is None:
            if media_binding_state(registry_row.get("image_binding"), {}) != (
                "NO_IMAGE_INTENTIONAL"
            ):
                fail("RAOS_V2_MEDIA_BINDING_UNRESOLVED")
        else:
            # Phase 2 deliberately has no recorded image body/hash. An image
            # reference can only be introduced together with a complete exact
            # expected binding in a successor contract.
            fail("RAOS_V2_MEDIA_BINDING_UNRESOLVED")


def validate_event_catalog_document(catalog: Mapping[str, object]) -> None:
    expected = {
        "tool_result_view": ({"result_state"}, {"source_id", "product_id"}),
        "comparison_view": (set(), {"result_state", "source_id", "product_id"}),
        "evidence_link_open": ({"source_id"}, {"result_state", "product_id"}),
        "official_source_open": ({"source_id"}, {"result_state", "product_id"}),
        "affiliate_outbound_activate": (
            {"product_id"},
            {"result_state", "source_id"},
        ),
        "article_complete": (set(), {"result_state", "source_id", "product_id"}),
        "error_state_view": ({"result_state"}, {"source_id", "product_id"}),
    }
    events = catalog.get("events")
    matrix = catalog.get("event_field_matrix")
    if (
        not isinstance(events, list)
        or set(events) != set(expected)
        or not isinstance(matrix, dict)
        or set(matrix) != set(expected)
    ):
        fail("RAOS_V2_EVENT_FIELD_MATRIX_INVALID")
    for event_name, (required, forbidden) in expected.items():
        row = matrix.get(event_name)
        if (
            not isinstance(row, dict)
            or set(row) != {"required_non_null", "must_be_null"}
            or set(row.get("required_non_null", [])) != required
            or set(row.get("must_be_null", [])) != forbidden
            or required & forbidden
        ):
            fail("RAOS_V2_EVENT_FIELD_MATRIX_INVALID")


def validate_phase2_source_inputs() -> dict[Path, object]:
    """Parse every machine input strictly and bound every source file.

    This intentionally runs before any Phase 2 output is composed. JSON/YAML
    duplicate keys, YAML aliases/tags, symlinks, invalid UTF-8 and oversized
    inputs therefore fail closed at the single generator-owner boundary.
    """

    discovered_implementation = {
        path.relative_to(ROOT)
        for base, suffix in (
            (ROOT / "packages/web-ui/src/decision-support-v2", "*.ts"),
            (ROOT / "python/raos/adapters/decision_support_v2", "*.py"),
            (ROOT / "python/raos/application/decision_support_v2", "*.py"),
            (ROOT / "python/raos/domain/decision_support_v2", "*.py"),
            (ROOT / "python/raos/ports/decision_support_v2", "*.py"),
        )
        for path in base.glob(suffix)
        if path.is_file() and not path.is_symlink()
    }
    discovered_tests = {
        path.relative_to(ROOT)
        for pattern in ("*.py", "*.mjs", "*.php")
        for path in (ROOT / "tests/raos_v2").glob(pattern)
        if path.is_file() and not path.is_symlink()
    }
    discovered_preview_inputs = {
        path.relative_to(ROOT)
        for path in (ROOT / "packages/web-ui/src/decision-support-v2/preview").glob("*")
        if path.is_file() and not path.is_symlink()
    }
    if discovered_implementation != set(PHASE2_IMPLEMENTATION_PATHS):
        fail("RAOS_V2_PHASE2_IMPLEMENTATION_INVENTORY_DRIFT")
    if discovered_preview_inputs != set(PHASE2_PREVIEW_INPUT_PATHS):
        fail("RAOS_V2_PHASE2_PREVIEW_INPUT_INVENTORY_DRIFT")
    if discovered_tests != set(PHASE2_TEST_SOURCE_PATHS):
        fail("RAOS_V2_PHASE2_TEST_INVENTORY_DRIFT")
    if len(PHASE2_SOURCE_PATHS) != len(set(PHASE2_SOURCE_PATHS)):
        fail("RAOS_V2_PHASE2_SOURCE_DUPLICATE")
    parsed: dict[Path, object] = {}
    for relative in PHASE2_SOURCE_PATHS:
        path = ROOT / relative
        try:
            path.lstat()
            payload = path.read_bytes()
        except OSError:
            fail("RAOS_V2_PHASE2_SOURCE_MISSING")
        if path.is_symlink() or not path.is_file() or len(payload) > 2 * 1024 * 1024:
            fail("RAOS_V2_PHASE2_SOURCE_BOUNDARY_INVALID")
        if relative.suffix == ".json":
            parsed[relative] = _read_json(relative)
        elif relative.suffix in {".yaml", ".yml"}:
            parsed[relative] = _read_yaml(relative)
        else:
            try:
                text = payload.decode("utf-8")
            except UnicodeError:
                fail("RAOS_V2_PHASE2_SOURCE_UTF8_INVALID")
            if "\x00" in text:
                fail("RAOS_V2_PHASE2_SOURCE_UTF8_INVALID")
            parsed[relative] = text
    media = parsed.get(Path("changes/raos-v2/phase-2/media/media-policy.v2.yaml"))
    offers = parsed.get(
        Path(
            "changes/raos-v2/phase-2/fixtures/recorded-rakuten-item-search-2026-07-01.json"
        )
    )
    if not isinstance(media, dict) or not isinstance(offers, dict):
        fail("RAOS_V2_MEDIA_POLICY_INVALID")
    validate_media_policy_document(media, offers)
    event_catalog = parsed.get(
        Path("changes/raos-v2/phase-2/events/event-catalog.v2.yaml")
    )
    if not isinstance(event_catalog, dict):
        fail("RAOS_V2_EVENT_FIELD_MATRIX_INVALID")
    validate_event_catalog_document(event_catalog)
    return parsed


def _validate_phase3_wordpress_source_inventory() -> None:
    wordpress_root = ROOT / "packages/web-ui/src/decision-support-v2/wordpress"
    discovered = {
        path.relative_to(ROOT)
        for path in wordpress_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    if discovered != set(PHASE3_WORDPRESS_SOURCE_PATHS) or any(
        path.is_symlink() for path in wordpress_root.rglob("*")
    ):
        fail("RAOS_V2_PHASE3_WORDPRESS_SOURCE_INVENTORY_DRIFT")


def _read_phase3_source_paths(paths: Sequence[Path]) -> dict[Path, object]:
    parsed: dict[Path, object] = {}
    for relative in paths:
        path = ROOT / relative
        try:
            metadata = path.lstat()
            payload = path.read_bytes()
        except OSError:
            fail("RAOS_V2_PHASE3_SOURCE_MISSING")
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or len(payload) > 2 * 1024 * 1024
        ):
            fail("RAOS_V2_PHASE3_SOURCE_BOUNDARY_INVALID")
        if relative.suffix == ".json":
            parsed[relative] = _read_json(relative)
        elif relative.suffix in {".yaml", ".yml"}:
            parsed[relative] = _read_yaml(relative)
        else:
            try:
                text = payload.decode("utf-8")
            except UnicodeError:
                fail("RAOS_V2_PHASE3_SOURCE_UTF8_INVALID")
            if "\x00" in text:
                fail("RAOS_V2_PHASE3_SOURCE_UTF8_INVALID")
            parsed[relative] = text
    return parsed


def _validate_phase3_wordpress_manifest(parsed: Mapping[Path, object]) -> None:
    phase3_external_state()
    manifest_path = Path(
        "packages/web-ui/src/decision-support-v2/wordpress/plugin/"
        "raos-v2-decision-support/plugin-manifest.v1.json"
    )
    manifest = parsed.get(manifest_path)
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != "RAOS_V2_WORDPRESS_PRESENTATION_PLUGIN_INPUT_V1"
        or manifest.get("installation")
        != (
            "INSTALL_INACTIVE_REPLACE_BINDING_ACTIVATE_THEN_WRITE_"
            "EXTERNAL_HUMAN_ACTIONS_NOT_EXECUTED"
        )
    ):
        fail("RAOS_V2_PHASE3_WORDPRESS_MANIFEST_INVALID")
    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict) or any(
        runtime.get(capability) is not False
        for capability in (
            "admin_ui",
            "cron",
            "database_write",
            "network_request",
            "option_write",
            "publication_capability",
            "rest_route",
            "telemetry",
        )
    ):
        fail("RAOS_V2_PHASE3_WORDPRESS_MANIFEST_INVALID")


def validate_phase3_browser_bootstrap_inputs() -> dict[Path, object]:
    """Bind browser inputs without requiring an earlier browser receipt."""

    _validate_phase3_wordpress_source_inventory()
    parsed = _read_phase3_source_paths(PHASE3_BROWSER_BOOTSTRAP_SOURCE_PATHS)
    _validate_phase3_wordpress_manifest(parsed)
    if PHASE3_LOCAL_BROWSER_EVIDENCE_PATH in parsed:
        fail("RAOS_V2_PHASE3_BOOTSTRAP_EVIDENCE_BOUNDARY_INVALID")
    return parsed


def validate_phase3_source_inputs() -> dict[Path, object]:
    """Strictly bind all Phase 3 sources after browser evidence exists."""

    parsed = validate_phase3_browser_bootstrap_inputs()
    parsed.update(
        _read_phase3_source_paths(
            (PHASE3_LOCAL_BROWSER_EVIDENCE_PATH, PHASE3_PUBLIC_OBSERVATION_PATH)
        )
    )
    return parsed


def _phase2_input_inventory() -> list[dict[str, object]]:
    roles: dict[Path, str] = {
        **{path: "DATA_OR_CONTENT_INPUT" for path in PHASE2_DATA_PATHS},
        **{path: "AUTHORITATIVE_PREVIEW_INPUT" for path in PHASE2_PREVIEW_INPUT_PATHS},
        **{
            path: "RECORDED_LOCAL_EVIDENCE_INPUT"
            for path in PHASE2_RECORDED_EVIDENCE_PATHS
        },
        **{path: "IMPLEMENTATION_SOURCE" for path in PHASE2_IMPLEMENTATION_PATHS},
        **{path: "TEST_SOURCE" for path in PHASE2_TEST_SOURCE_PATHS},
    }
    # Normal tracked code/tests/content are deliberately not digest-pinned.
    # Hashes below are reserved for runtime data integrity, generated output,
    # package/container provenance and recorded evidence receipts.
    return [
        {"path": path.as_posix(), "role": roles[path]}
        for path in sorted(PHASE2_SOURCE_PATHS)
    ]


def migration_manifest_document(
    capture: Mapping[str, object], preview: Mapping[Path, bytes]
) -> dict[str, object]:
    rows = capture.get("public_urls")
    if not isinstance(rows, list):
        fail("RAOS_V2_MIGRATION_BASELINE_INVALID")
    baseline = next(
        (
            row
            for row in rows
            if isinstance(row, dict)
            and row.get("path") == "/carry-on-suitcase-comparison/"
        ),
        None,
    )
    if not isinstance(baseline, dict):
        fail("RAOS_V2_MIGRATION_BASELINE_INVALID")
    route = str(baseline.get("path"))
    status = baseline.get("status")
    canonical = baseline.get("canonical")
    robots = baseline.get("robots")
    if (
        not isinstance(status, int)
        or not isinstance(canonical, str)
        or not isinstance(robots, str)
    ):
        fail("RAOS_V2_MIGRATION_BASELINE_INVALID")
    round_trip = simulate_route_round_trip(
        (route, status, canonical, robots),
        (route, 200, canonical, "noindex,nofollow"),
    )
    preview_path = Path(
        "changes/raos-v2/phase-2/preview/carry-on-suitcase-comparison/index.html"
    )
    preview_payload = preview.get(preview_path)
    if not isinstance(preview_payload, bytes):
        fail("RAOS_V2_MIGRATION_PREVIEW_MISSING")
    document: dict[str, object] = {
        "schema": "RAOS_V2_MIGRATION_MANIFEST_V1",
        "version": "2.0.0",
        "mode": "LOCAL_SIMULATION_ONLY",
        "target_origin": "https://kurashinoshirube.com",
        "target_route": route,
        "legacy_article_aliases": [
            {
                "legacy_article_id": "st1703-first-suitcase-comparison",
                "stable_article_id": "A05",
                "route": route,
                "purpose": "MIGRATION_REFERENCE_ONLY",
            }
        ],
        "public_before": {
            "evidence_class": "PUBLIC_READ_ONLY",
            "observed_at": baseline.get("observed_at"),
            "status": status,
            "canonical": canonical,
            "robots": robots,
            "body_sha256": baseline.get("body_sha256"),
        },
        "local_candidate": {
            "preview_path": preview_path.as_posix(),
            "render_sha256": sha256(preview_payload),
            "preview_robots": "noindex,nofollow",
            "public_write": "NOT_EXECUTED",
        },
        "future_public_intent": {
            "route_preserved": True,
            "canonical": canonical,
            "indexing_change": "REQUIRES_PHASE3_HUMAN_APPROVAL_AND_PUBLIC_VERIFY",
        },
        "rollback": {
            "simulation": round_trip,
            "restore_tuple": [route, status, canonical, robots],
            "plan_scope": "P2_LOCAL_CONTRACT_FOR_P3_HUMAN_GATED_EXECUTION",
            "ordered_restore_steps": [
                {
                    "sequence": 1,
                    "phase_boundary": "P2_LOCAL_PREPARATION",
                    "action": "VERIFY_PRECONDITIONS_AND_EXPORT_RECEIPT",
                    "requires": [
                        "human approval for Phase 3",
                        "recoverable content metadata theme and URL export receipt",
                    ],
                    "production_status": "NOT_EXECUTED",
                },
                {
                    "sequence": 2,
                    "phase_boundary": "P3_HUMAN_GATED",
                    "action": "RESTORE_PRIOR_CONTENT_METADATA_THEME_AND_URL",
                    "requires": ["step 1 verified", "exact restore tuple binding"],
                    "production_status": "NOT_EXECUTED",
                },
                {
                    "sequence": 3,
                    "phase_boundary": "P3_HUMAN_GATED",
                    "action": "PUBLIC_READ_ONLY_VERIFY_STATUS_CANONICAL_ROBOTS_AND_BODY",
                    "requires": [
                        "step 2 completed",
                        "same-origin credential-free capture",
                    ],
                    "production_status": "NOT_EXECUTED",
                },
            ],
            "production_backup": "NOT_EXECUTED",
            "production_restore": "NOT_EXECUTED",
        },
        "failure_conditions": [
            "route or canonical differs from captured baseline",
            "critical claim, disclosure, CTA, accessibility or SEO defect",
            "rollback tuple binding or render digest mismatch",
        ],
        "external_actions": "NOT_EXECUTED",
        "backlog_id": "B-V2-031",
        "requirement_ids": ["R-V2-023", "R-V2-025"],
        "test_ids": ["T-V2-025", "T-V2-035", "T-V2-040"],
    }
    validate_migration_restore_plan(document)
    return document


def validate_migration_restore_plan(document: Mapping[str, object]) -> None:
    """Validate the ordered, local-only recovery contract for Phase 3."""

    public_before = document.get("public_before")
    rollback = document.get("rollback")
    if not isinstance(public_before, Mapping) or not isinstance(rollback, Mapping):
        fail("RAOS_V2_MIGRATION_RESTORE_PLAN_INVALID")
    restore_tuple = rollback.get("restore_tuple")
    steps = rollback.get("ordered_restore_steps")
    simulation = rollback.get("simulation")
    expected_tuple = [
        document.get("target_route"),
        public_before.get("status"),
        public_before.get("canonical"),
        public_before.get("robots"),
    ]
    expected_actions = [
        "VERIFY_PRECONDITIONS_AND_EXPORT_RECEIPT",
        "RESTORE_PRIOR_CONTENT_METADATA_THEME_AND_URL",
        "PUBLIC_READ_ONLY_VERIFY_STATUS_CANONICAL_ROBOTS_AND_BODY",
    ]
    expected_boundaries = [
        "P2_LOCAL_PREPARATION",
        "P3_HUMAN_GATED",
        "P3_HUMAN_GATED",
    ]
    if (
        document.get("mode") != "LOCAL_SIMULATION_ONLY"
        or document.get("external_actions") != "NOT_EXECUTED"
        or rollback.get("plan_scope")
        != "P2_LOCAL_CONTRACT_FOR_P3_HUMAN_GATED_EXECUTION"
        or rollback.get("production_backup") != "NOT_EXECUTED"
        or rollback.get("production_restore") != "NOT_EXECUTED"
        or restore_tuple != expected_tuple
        or not isinstance(steps, list)
        or len(steps) != 3
        or not isinstance(simulation, Mapping)
        or simulation.get("status") != "PASSED_LOCAL"
        or simulation.get("exact_tuple_restored") is not True
        or simulation.get("baseline_sha256") != simulation.get("restored_sha256")
        or simulation.get("external_action") != "NOT_EXECUTED"
    ):
        fail("RAOS_V2_MIGRATION_RESTORE_PLAN_INVALID")
    for index, step in enumerate(steps, start=1):
        if (
            not isinstance(step, Mapping)
            or step.get("sequence") != index
            or step.get("action") != expected_actions[index - 1]
            or step.get("phase_boundary") != expected_boundaries[index - 1]
            or step.get("production_status") != "NOT_EXECUTED"
            or not isinstance(step.get("requires"), list)
            or not step["requires"]
            or not all(isinstance(value, str) and value for value in step["requires"])
        ):
            fail("RAOS_V2_MIGRATION_RESTORE_PLAN_INVALID")


def claim_ledger_document() -> dict[str, object]:
    products = _read_json(
        Path("changes/raos-v2/phase-2/data/ace-carry-on-models.v2.json")
    )
    airlines = _read_json(
        Path("changes/raos-v2/phase-2/fixtures/recorded-airline-rules.v2.json")
    )
    source_registry = _read_yaml(
        Path("changes/raos-v2/phase-2/sources/source-registry.v2.yaml")
    )
    if not all(
        isinstance(value, dict) for value in (products, airlines, source_registry)
    ):
        fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
    assert isinstance(products, dict)
    assert isinstance(airlines, dict)
    assert isinstance(source_registry, dict)
    source_rows = source_registry.get("sources")
    if not isinstance(source_rows, list):
        fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
    sources = {
        row["source_id"]: row
        for row in source_rows
        if isinstance(row, dict) and isinstance(row.get("source_id"), str)
    }

    def record(
        *,
        claim_id: str,
        claim_type: str,
        subject_id: str,
        predicate: str,
        value: object,
        unit: str | None,
        source_ids: list[str],
        logic_inputs: list[dict[str, str]],
        checked_at: str,
        next_review_at: str,
        risk_class: str,
        status: str,
    ) -> dict[str, object]:
        return {
            "schema_version": "1.0.0",
            "claim_id": claim_id,
            "claim_type": claim_type,
            "subject_id": subject_id,
            "predicate": predicate,
            "value": value,
            "unit": unit,
            "source_ids": source_ids,
            "logic_inputs": logic_inputs,
            "checked_at": checked_at,
            "next_review_at": next_review_at,
            "risk_class": risk_class,
            "status": status,
        }

    rows: list[dict[str, object]] = []
    product_claim_ids: dict[str, dict[str, str]] = {}
    prefixes = {
        "PRD-ACE-CRESTA-06316": "CRESTA",
        "PRD-ACE-DIFFERENCE-05721": "DIFFERENCE",
        "PRD-ACE-MAXPASS4-01471": "MAXPASS4",
    }
    product_rows = products.get("products")
    if not isinstance(product_rows, list):
        fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
    for product in product_rows:
        if not isinstance(product, dict):
            fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
        product_id = product.get("product_id")
        source_ids = product.get("official_source_ids")
        variants = product.get("variants")
        if (
            not isinstance(product_id, str)
            or product_id not in prefixes
            or not isinstance(source_ids, list)
            or len(source_ids) != 1
            or not isinstance(source_ids[0], str)
            or not isinstance(variants, list)
            or len(variants) != 1
            or not isinstance(variants[0], dict)
        ):
            fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
        source = sources.get(source_ids[0])
        if not isinstance(source, dict):
            fail("RAOS_V2_CLAIM_LEDGER_SOURCE_MISSING")
        checked_at = source.get("checked_at")
        next_review_at = source.get("next_review_at")
        if not isinstance(checked_at, str) or not isinstance(next_review_at, str):
            fail("RAOS_V2_CLAIM_LEDGER_SOURCE_MISSING")
        variant = variants[0]
        prefix = prefixes[product_id]
        identifiers = {
            "identity": f"CLM-A05-{prefix}-IDENTITY",
            "dimensions": f"CLM-A05-{prefix}-DIMENSIONS",
            "capacity": f"CLM-A05-{prefix}-CAPACITY",
            "mass": f"CLM-A05-{prefix}-MASS",
            "features": f"CLM-A05-{prefix}-FEATURES",
            "unknown": f"CLM-A05-{prefix}-USAGE-UNKNOWN",
            "fit": f"CLM-A05-{prefix}-CONDITIONAL-FIT",
        }
        product_claim_ids[product_id] = identifiers
        facts = (
            (
                identifiers["identity"],
                "product_identity",
                {
                    "brand": product.get("brand"),
                    "model_name": product.get("model_name"),
                    "model_number": product.get("model_number"),
                },
                None,
            ),
            (
                identifiers["dimensions"],
                "external_dimensions_cm",
                variant.get("external_dimensions_cm"),
                "cm",
            ),
            (
                identifiers["capacity"],
                "capacity_l",
                variant.get("capacity_l"),
                "L",
            ),
            (identifiers["mass"], "mass_kg", variant.get("mass_kg"), "kg"),
            (
                identifiers["features"],
                "declared_features",
                variant.get("declared_features"),
                None,
            ),
        )
        for claim_id, predicate, fact_value, unit in facts:
            rows.append(
                record(
                    claim_id=claim_id,
                    claim_type="A_OFFICIAL_FACT",
                    subject_id=product_id,
                    predicate=predicate,
                    value=fact_value,
                    unit=unit,
                    source_ids=[source_ids[0]],
                    logic_inputs=[],
                    checked_at=checked_at,
                    next_review_at=next_review_at,
                    risk_class=(
                        "HIGH"
                        if predicate in {"product_identity", "external_dimensions_cm"}
                        else "MEDIUM"
                    ),
                    status="VERIFIED",
                )
            )
        for field, predicate, unit in (
            ("expanded_dimensions_cm", "expanded_dimensions_cm", "cm"),
            ("expanded_capacity_l", "expanded_capacity_l", "L"),
        ):
            if variant.get(field) is not None:
                claim_id = f"CLM-A05-{prefix}-{'EXPANDED-DIMENSIONS' if 'dimensions' in field else 'EXPANDED-CAPACITY'}"
                identifiers[field] = claim_id
                rows.append(
                    record(
                        claim_id=claim_id,
                        claim_type="A_OFFICIAL_FACT",
                        subject_id=product_id,
                        predicate=predicate,
                        value=variant.get(field),
                        unit=unit,
                        source_ids=[source_ids[0]],
                        logic_inputs=[],
                        checked_at=checked_at,
                        next_review_at=next_review_at,
                        risk_class="HIGH",
                        status="VERIFIED",
                    )
                )
        rows.append(
            record(
                claim_id=identifiers["unknown"],
                claim_type="UNKNOWN",
                subject_id=product_id,
                predicate="hands_on_usage",
                value=None,
                unit=None,
                source_ids=[],
                logic_inputs=[],
                checked_at=checked_at,
                next_review_at=next_review_at,
                risk_class="MEDIUM",
                status="BLOCKED",
            )
        )
        decision_inputs = [
            {
                "input_id": f"IN-{prefix}-DIMENSIONS",
                "value_ref": identifiers["dimensions"],
            },
            {"input_id": f"IN-{prefix}-CAPACITY", "value_ref": identifiers["capacity"]},
            {"input_id": f"IN-{prefix}-MASS", "value_ref": identifiers["mass"]},
            {"input_id": f"IN-{prefix}-FEATURES", "value_ref": identifiers["features"]},
        ]
        rows.append(
            record(
                claim_id=identifiers["fit"],
                claim_type="D_EDITORIAL_JUDGEMENT",
                subject_id="A05",
                predicate="conditional_fit",
                value=product_id,
                unit=None,
                source_ids=[source_ids[0]],
                logic_inputs=decision_inputs,
                checked_at=checked_at,
                next_review_at=next_review_at,
                risk_class="MEDIUM",
                status="VERIFIED",
            )
        )

    mass_inputs = [
        {
            "input_id": f"IN-{prefixes[product_id]}-MASS",
            "value_ref": product_claim_ids[product_id]["mass"],
        }
        for product_id in prefixes
    ]
    mass_sources = [
        sources[source_id]
        for source_id in (
            "SRC-ACE-CRESTA-06316",
            "SRC-ACE-DIFFERENCE-05721",
            "SRC-ACE-MAXPASS4-01471",
        )
    ]
    if not all(isinstance(row, dict) for row in mass_sources):
        fail("RAOS_V2_CLAIM_LEDGER_SOURCE_MISSING")
    mass_checked_at = max(str(row["checked_at"]) for row in mass_sources)
    mass_next_review_at = min(str(row["next_review_at"]) for row in mass_sources)
    rows.append(
        record(
            claim_id="CLM-A05-CRESTA-LIGHTEST-IN-SCOPE",
            claim_type="D_EDITORIAL_JUDGEMENT",
            subject_id="A05",
            predicate="conditional_lightest_product",
            value="PRD-ACE-CRESTA-06316",
            unit=None,
            source_ids=[
                "SRC-ACE-CRESTA-06316",
                "SRC-ACE-DIFFERENCE-05721",
                "SRC-ACE-MAXPASS4-01471",
            ],
            logic_inputs=mass_inputs,
            checked_at=mass_checked_at,
            next_review_at=mass_next_review_at,
            risk_class="MEDIUM",
            status="VERIFIED",
        )
    )

    displayed_rules = {
        ("AIR-ANA-DOMESTIC-2026", "ANA-100-SEATS-OR-MORE"): "CLM-A02-ANA-LARGE-RULE",
        ("AIR-ANA-DOMESTIC-2026", "ANA-UNDER-100-SEATS"): "CLM-A02-ANA-SMALL-RULE",
        ("AIR-JAL-DOMESTIC-2026", "JAL-100-SEATS-OR-MORE"): "CLM-A02-JAL-LARGE-RULE",
        ("AIR-JAL-DOMESTIC-2026", "JAL-UNDER-100-SEATS"): "CLM-A02-JAL-SMALL-RULE",
        ("AIR-PEACH-2026", "PEACH-STANDARD"): "CLM-A02-PEACH-STANDARD-RULE",
        (
            "AIR-JETSTAR-JAPAN-2026",
            "JETSTAR-JAPAN-STANDARD-7KG",
        ): "CLM-A02-JETSTAR-STANDARD-RULE",
    }
    rule_sets = airlines.get("rule_sets")
    if not isinstance(rule_sets, list):
        fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
    for rule_set in rule_sets:
        if not isinstance(rule_set, dict) or not isinstance(
            rule_set.get("variants"), list
        ):
            fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
        for variant in rule_set["variants"]:
            if not isinstance(variant, dict):
                fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
            key = (rule_set.get("rule_set_id"), variant.get("variant_id"))
            claim_id = displayed_rules.get(key)
            if claim_id is None:
                continue
            source_id = rule_set.get("source_id")
            next_review_at = rule_set.get("source_next_review_at")
            checked_at = rule_set.get("checked_at")
            if not all(
                isinstance(value, str)
                for value in (source_id, next_review_at, checked_at)
            ):
                fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
            rows.append(
                record(
                    claim_id=claim_id,
                    claim_type="A_OFFICIAL_FACT",
                    subject_id=str(rule_set["rule_set_id"]),
                    predicate="carry_on_rule_variant",
                    value={
                        "carrier": rule_set.get("carrier"),
                        "effective_from": rule_set.get("effective_from"),
                        "observed_applicable_from": rule_set.get(
                            "observed_applicable_from"
                        ),
                        "effective_to": rule_set.get("effective_to"),
                        "variant": variant,
                    },
                    unit=None,
                    source_ids=[str(source_id)],
                    logic_inputs=[],
                    checked_at=str(checked_at),
                    next_review_at=str(next_review_at),
                    risk_class="HIGH",
                    status="VERIFIED",
                )
            )
    if len(rows) != len({str(row["claim_id"]) for row in rows}):
        fail("RAOS_V2_CLAIM_LEDGER_DUPLICATE")
    return {
        "schema": "RAOS_V2_CLAIM_LEDGER_V1",
        "version": "2.0.0",
        "generation": "NORMALIZED_FROM_RECORDED_PRODUCT_AND_AIRLINE_FACTS",
        "claims": rows,
    }


def publication_claim_evidence(
    *,
    bound_claims: Sequence[Mapping[str, object]],
    all_claims: Mapping[str, Mapping[str, object]],
    source_registry: Mapping[str, object],
    candidate_at: datetime,
) -> list[dict[str, str]]:
    """Resolve evidence freshness instead of trusting a VERIFIED label."""

    if candidate_at.tzinfo is None or candidate_at.utcoffset() is None:
        fail("RAOS_V2_PUBLICATION_TIME_INVALID")
    source_rows = source_registry.get("sources")
    if not isinstance(source_rows, list):
        fail("RAOS_V2_PUBLICATION_SOURCE_REGISTRY_INVALID")
    sources = {
        str(row["source_id"]): row
        for row in source_rows
        if isinstance(row, dict) and isinstance(row.get("source_id"), str)
    }
    allowed_source_classes = {
        "MANUFACTURER_PRIMARY",
        "AIRLINE_PRIMARY",
        "GOVERNMENT_PRIMARY",
        "RAKUTEN_PERMITTED_DATA",
    }
    evidence: list[dict[str, str]] = []
    for claim in sorted(bound_claims, key=lambda row: str(row.get("claim_id"))):
        claim_id = claim.get("claim_id")
        claim_type = claim.get("claim_type")
        risk_class = claim.get("risk_class")
        if not all(
            isinstance(value, str) for value in (claim_id, claim_type, risk_class)
        ):
            fail("RAOS_V2_PUBLICATION_CLAIM_INVALID")
        assert isinstance(claim_id, str)
        assert isinstance(claim_type, str)
        assert isinstance(risk_class, str)
        if claim_type == "UNKNOWN":
            if (
                claim.get("status") != "BLOCKED"
                or claim.get("value") is not None
                or claim.get("unit") is not None
                or claim.get("source_ids") != []
            ):
                fail("RAOS_V2_PUBLICATION_UNKNOWN_CLAIM_INVALID")
            evidence.append(
                {
                    "claim_id": claim_id,
                    "risk_class": risk_class,
                    "freshness": "UNKNOWN",
                }
            )
            continue
        if claim.get("status") != "VERIFIED":
            fail("RAOS_V2_PUBLICATION_CLAIM_NOT_VERIFIED")
        source_ids = claim.get("source_ids")
        if not isinstance(source_ids, list) or not source_ids:
            fail("RAOS_V2_PUBLICATION_SOURCE_CLOSURE_INVALID")
        resolved_sources: list[Mapping[str, object]] = []
        for source_id in source_ids:
            source = sources.get(str(source_id))
            if (
                not isinstance(source, dict)
                or source.get("source_class") not in allowed_source_classes
                or source.get("status") not in {"FRESH", "DUE"}
                or not isinstance(source.get("content_sha256"), str)
                or len(str(source.get("content_sha256"))) != 64
            ):
                fail("RAOS_V2_PUBLICATION_SOURCE_INELIGIBLE")
            resolved_sources.append(source)
        try:
            source_checked = max(
                datetime.fromisoformat(str(source["checked_at"]).replace("Z", "+00:00"))
                for source in resolved_sources
            )
            source_next_review = min(
                datetime.fromisoformat(
                    str(source["next_review_at"]).replace("Z", "+00:00")
                )
                for source in resolved_sources
            )
            claim_checked = datetime.fromisoformat(
                str(claim["checked_at"]).replace("Z", "+00:00")
            )
            claim_next_review = datetime.fromisoformat(
                str(claim["next_review_at"]).replace("Z", "+00:00")
            )
        except KeyError, ValueError:
            fail("RAOS_V2_PUBLICATION_SOURCE_TIME_INVALID")
        if (
            claim_checked != source_checked
            or claim_next_review != source_next_review
            or candidate_at > claim_next_review
        ):
            fail("RAOS_V2_PUBLICATION_CLAIM_FRESHNESS_INVALID")
        if claim_type == "D_EDITORIAL_JUDGEMENT":
            logic_inputs = claim.get("logic_inputs")
            if not isinstance(logic_inputs, list) or not logic_inputs:
                fail("RAOS_V2_PUBLICATION_LOGIC_CLOSURE_INVALID")
            for logic_input in logic_inputs:
                value_ref = (
                    logic_input.get("value_ref")
                    if isinstance(logic_input, dict)
                    else None
                )
                if not isinstance(value_ref, str) or value_ref not in all_claims:
                    fail("RAOS_V2_PUBLICATION_LOGIC_CLOSURE_INVALID")
        freshness = (
            "DUE"
            if candidate_at == claim_next_review
            or any(source.get("status") == "DUE" for source in resolved_sources)
            else "FRESH"
        )
        evidence.append(
            {
                "claim_id": claim_id,
                "risk_class": risk_class,
                "freshness": freshness,
            }
        )
    return evidence


def phase3_claim_authority_document(
    *,
    bound_claims: Sequence[Mapping[str, object]],
    claim_evidence: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Close Phase 3 claim type/risk/status over Phase 2 evidence."""

    claims_by_id = {
        str(claim.get("claim_id")): claim
        for claim in bound_claims
        if isinstance(claim.get("claim_id"), str)
    }
    evidence_by_id = {
        str(evidence.get("claim_id")): evidence
        for evidence in claim_evidence
        if isinstance(evidence.get("claim_id"), str)
    }
    if (
        not claims_by_id
        or len(claims_by_id) != len(bound_claims)
        or len(evidence_by_id) != len(claim_evidence)
        or set(claims_by_id) != set(evidence_by_id)
    ):
        fail("RAOS_V2_PHASE3_CLAIM_AUTHORITY_INVALID")
    rows: list[dict[str, object]] = []
    for claim_id in sorted(claims_by_id):
        claim = claims_by_id[claim_id]
        evidence = evidence_by_id[claim_id]
        row = {
            "claim_id": claim_id,
            "claim_type": claim.get("claim_type"),
            "risk_class": claim.get("risk_class"),
            "freshness": evidence.get("freshness"),
            "authoritative_source_status": claim.get("status"),
            "checked_at": claim.get("checked_at"),
            "next_review_at": claim.get("next_review_at"),
        }
        try:
            checked_at = datetime.fromisoformat(str(row["checked_at"]))
            next_review_at = datetime.fromisoformat(str(row["next_review_at"]))
        except ValueError:
            fail("RAOS_V2_PHASE3_CLAIM_AUTHORITY_INVALID")
        if (
            row["claim_type"]
            not in {"A_OFFICIAL_FACT", "D_EDITORIAL_JUDGEMENT", "UNKNOWN"}
            or row["risk_class"] not in {"LOW", "MEDIUM", "HIGH"}
            or row["freshness"]
            not in {
                "FRESH",
                "DUE",
                "SOFT_STALE",
                "HARD_STALE",
                "UNKNOWN",
                "UNAVAILABLE",
                "REJECTED",
            }
            or row["authoritative_source_status"] not in {"VERIFIED", "BLOCKED"}
            or checked_at.tzinfo is None
            or checked_at.utcoffset() is None
            or next_review_at.tzinfo is None
            or next_review_at.utcoffset() is None
            or next_review_at <= checked_at
            or evidence.get("risk_class") != row["risk_class"]
        ):
            fail("RAOS_V2_PHASE3_CLAIM_AUTHORITY_INVALID")
        rows.append(row)
    return {
        "schema": "RAOS_V2_PHASE3_CLAIM_AUTHORITY_V1",
        "version": "1.0.0",
        "claims": rows,
    }


def validate_publication_hash_closure(document: Mapping[str, object]) -> None:
    hashes = document.get("input_hashes")
    migration = document.get("migration_manifest")
    if (
        not isinstance(hashes, dict)
        or not isinstance(migration, dict)
        or document.get("render_hash") != hashes.get("render")
        or document.get("source_snapshot_hash") != hashes.get("sources")
        or migration.get("sha256") != hashes.get("migration")
    ):
        fail("RAOS_V2_PUBLICATION_HASH_CLOSURE_INVALID")


def publication_candidate_document(
    migration: Mapping[str, object],
    preview: Mapping[Path, bytes],
    claim_ledger: Mapping[str, object],
) -> dict[str, object]:
    content_path = Path("changes/raos-v2/phase-2/content/carry-on-comparison.v2.yaml")
    article_path = Path("changes/raos-v2/phase-2/content/article-definitions.v2.yaml")
    editorial_path = Path(
        "changes/raos-v2/phase-2/editorial/editorial-decisions.v2.yaml"
    )
    product_path = Path("changes/raos-v2/phase-2/data/ace-carry-on-models.v2.json")
    render_model_path = Path(
        "packages/web-ui/src/decision-support-v2/preview/pages.v2.json"
    )
    source_path = Path("changes/raos-v2/phase-2/sources/source-registry.v2.yaml")
    review_path = Path("changes/raos-v2/phase-2/reviews/review-packet.v2.yaml")
    preview_path = Path(
        "changes/raos-v2/phase-2/preview/carry-on-suitcase-comparison/index.html"
    )
    content = _read_yaml(content_path)
    article_definitions = _read_yaml(article_path)
    source_registry = _read_yaml(source_path)
    review = _read_yaml(review_path)
    if not all(
        isinstance(value, dict)
        for value in (content, article_definitions, source_registry, review)
    ):
        fail("RAOS_V2_PUBLICATION_INPUT_INVALID")
    assert isinstance(content, dict)
    assert isinstance(article_definitions, dict)
    assert isinstance(source_registry, dict)
    assert isinstance(review, dict)
    real_review = review.get("real_content")
    article_rows = article_definitions.get("articles")
    claim_rows = claim_ledger.get("claims")
    if not isinstance(article_rows, list) or not isinstance(claim_rows, list):
        fail("RAOS_V2_PUBLICATION_INPUT_INVALID")
    article = next(
        (
            row
            for row in article_rows
            if isinstance(row, dict)
            and row.get("article_id") == content.get("article_id")
        ),
        None,
    )
    if not isinstance(article, dict) or article.get("route") != content.get("route"):
        fail("RAOS_V2_PUBLICATION_ARTICLE_BINDING_INVALID")
    claims_by_id = {
        row["claim_id"]: row
        for row in claim_rows
        if isinstance(row, dict) and isinstance(row.get("claim_id"), str)
    }
    article_claim_ids = article.get("claim_ids")
    if (
        not isinstance(article_claim_ids, list)
        or not article_claim_ids
        or any(claim_id not in claims_by_id for claim_id in article_claim_ids)
    ):
        fail("RAOS_V2_PUBLICATION_CLAIM_CLOSURE_INVALID")
    bound_claims = [claims_by_id[str(claim_id)] for claim_id in article_claim_ids]
    if any(
        claim.get("status")
        != ("BLOCKED" if claim.get("claim_type") == "UNKNOWN" else "VERIFIED")
        for claim in bound_claims
    ):
        fail("RAOS_V2_PUBLICATION_CLAIM_STATE_INVALID")
    if (
        content.get("review_state") != "EVIDENCE_COMPLETE"
        or not isinstance(real_review, dict)
        or real_review.get("human_review") != "NOT_EXECUTED"
    ):
        fail("RAOS_V2_REAL_CONTENT_REVIEW_BOUNDARY_INVALID")
    preview_payload = preview.get(preview_path)
    if not isinstance(preview_payload, bytes):
        fail("RAOS_V2_PUBLICATION_RENDER_MISSING")
    migration_payload = yaml_bytes(migration)
    input_hashes = {
        "article": exact_file_set_sha256((article_path, content_path)),
        "claims": sha256(yaml_bytes(claim_ledger)),
        "sources": sha256((ROOT / source_path).read_bytes()),
        "render": sha256(preview_payload),
        "migration": sha256(migration_payload),
        "editorial": sha256((ROOT / editorial_path).read_bytes()),
        "products": sha256((ROOT / product_path).read_bytes()),
        "review": sha256((ROOT / review_path).read_bytes()),
        "render_model": sha256((ROOT / render_model_path).read_bytes()),
    }
    route = content.get("route")
    article_id = content.get("article_id")
    source_rows = source_registry.get("sources")
    checked_times = (
        [
            row.get("checked_at")
            for row in source_rows
            if isinstance(row, dict) and isinstance(row.get("checked_at"), str)
        ]
        if isinstance(source_rows, list)
        else []
    )
    try:
        created_at_value = max(
            (
                datetime.fromisoformat(value.replace("Z", "+00:00"))
                for value in checked_times
            ),
            default=None,
        )
    except ValueError:
        fail("RAOS_V2_PUBLICATION_SOURCE_TIME_INVALID")
    created_at = created_at_value.isoformat() if created_at_value is not None else None
    if not all(isinstance(value, str) for value in (route, article_id, created_at)):
        fail("RAOS_V2_PUBLICATION_INPUT_INVALID")
    assert created_at_value is not None
    claim_evidence = publication_claim_evidence(
        bound_claims=bound_claims,
        all_claims=claims_by_id,
        source_registry=source_registry,
        candidate_at=created_at_value,
    )
    phase3_claim_authority = phase3_claim_authority_document(
        bound_claims=bound_claims,
        claim_evidence=claim_evidence,
    )
    input_hashes["phase3_claim_authority"] = semantic_json_sha256(
        phase3_claim_authority
    )
    document = {
        "schema_version": "1.0.0",
        "package_id": "PKG-V2-CARRY-ON-COMPARISON-CANDIDATE",
        "target_origin": "https://kurashinoshirube.com",
        "target_route": route,
        "article_id": article_id,
        "input_hashes": input_hashes,
        "render_hash": input_hashes["render"],
        "source_snapshot_hash": input_hashes["sources"],
        "claim_evidence": claim_evidence,
        "review_binding": None,
        "migration_manifest": {
            "schema": migration.get("schema"),
            "mode": migration.get("mode"),
            "target_route": migration.get("target_route"),
            "sha256": input_hashes["migration"],
        },
        "created_at": created_at,
        "content_class": "REAL_CONTENT",
        "state": "EVIDENCE_COMPLETE",
        "package_digest": None,
    }
    validate_publication_hash_closure(document)
    return document


def synthetic_seal_receipt_document() -> dict[str, object]:
    python_root = str(ROOT / "python")
    if python_root not in sys.path:
        sys.path.insert(0, python_root)
    try:
        from raos.adapters.decision_support_v2.wordpress_disabled import (
            DisabledWordPressDraft,
        )
        from raos.domain.decision_support_v2.publication import (
            ClaimEvidenceBinding,
            PublicationPackage,
            PublicationState,
            ReviewBinding,
        )
        from raos.domain.decision_support_v2.models import FreshnessState, RiskClass
    except ImportError:
        fail("RAOS_V2_PUBLICATION_RUNTIME_IMPORT_INVALID")
    input_hashes = {
        key: sha256(f"RAOS-V2-SYNTHETIC-{key.upper()}".encode())
        for key in ("article", "claims", "sources", "render", "migration")
    }
    synthetic_migration = {
        "previous": None,
        "next": "synthetic",
        "wordpress_intent": "CREATE_OR_UPDATE",
    }
    input_hashes["migration"] = sha256(canonical_json_bytes(synthetic_migration))
    synthetic_migration["sha256"] = input_hashes["migration"]
    package = PublicationPackage(
        package_id="SYNTHETIC-PACKAGE-V2",
        target_origin="https://kurashinoshirube.com",
        target_route="/synthetic-contract-fixture/",
        article_id="SYNTHETIC-ARTICLE-V2",
        input_hashes=input_hashes,
        render_hash=input_hashes["render"],
        source_snapshot_hash=input_hashes["sources"],
        claim_evidence=(
            ClaimEvidenceBinding(
                claim_id="CLM-SYNTHETIC-FRESH",
                risk_class=RiskClass.LOW,
                freshness=FreshnessState.FRESH,
            ),
        ),
        review_binding=ReviewBinding(
            reviewer_id="SYNTHETIC-REVIEWER-NOT-A-PERSON",
            reviewed_at=datetime.fromisoformat("2026-08-28T12:00:00+09:00"),
            review_version="SYNTHETIC-V1",
            synthetic=True,
        ),
        migration_manifest=synthetic_migration,
        created_at=datetime.fromisoformat("2026-08-28T12:00:00+09:00"),
        state=PublicationState.DRAFT,
        synthetic=True,
    )
    sealed = (
        package.transition(PublicationState.EVIDENCE_COMPLETE)
        .transition(PublicationState.HUMAN_REVIEWED)
        .transition(PublicationState.PACKAGE_SEALED)
    )
    if not sealed.verify_seal() or sealed.package_digest is None:
        fail("RAOS_V2_SYNTHETIC_SEAL_INVALID")
    sealed_record = dict(sealed.to_contract_record())
    validate_publication_hash_closure(sealed_record)
    wordpress_receipt = dict(DisabledWordPressDraft().dry_run(sealed))
    return {
        "schema": "RAOS_V2_SYNTHETIC_SEAL_RECEIPT_V1",
        "purpose": "STATE_MACHINE_AND_DIGEST_TEST_ONLY",
        "state_path": [
            "DRAFT",
            "EVIDENCE_COMPLETE",
            "HUMAN_REVIEWED",
            "PACKAGE_SEALED",
        ],
        "package": sealed_record,
        "package_digest": sealed.package_digest,
        "digest_verified": True,
        "wordpress_dry_run": wordpress_receipt,
        "external_authority": "NONE",
        "publication": "NOT_EXECUTED",
        "test_ids": ["T-V2-031", "T-V2-037", "T-V2-038"],
    }


def validated_browser_evidence(
    parsed: Mapping[Path, object], preview: Mapping[Path, bytes]
) -> dict[str, object]:
    value = parsed.get(BROWSER_EVIDENCE_INPUT_PATH)
    if not isinstance(value, dict) or value.get("schema") != (
        "RAOS_V2_RECORDED_BROWSER_EVIDENCE_V1"
    ):
        fail("RAOS_V2_BROWSER_EVIDENCE_INPUT_INVALID")
    raw_receipt = value.get("raw_receipt")
    assertions = value.get("assertions")
    recorded_digests = value.get("preview_digests")
    browser_data = value.get("browser")
    if not all(
        isinstance(item, dict)
        for item in (raw_receipt, assertions, recorded_digests, browser_data)
    ):
        fail("RAOS_V2_BROWSER_EVIDENCE_INPUT_INVALID")
    assert isinstance(raw_receipt, dict)
    assert isinstance(assertions, dict)
    assert isinstance(recorded_digests, dict)
    assert isinstance(browser_data, dict)
    checker_states = assertions.get("checker_states")
    if not isinstance(checker_states, dict):
        fail("RAOS_V2_BROWSER_EVIDENCE_ASSERTION_FAILED")
    pages = _read_json(
        Path("packages/web-ui/src/decision-support-v2/preview/pages.v2.json")
    )
    page_rows = pages.get("pages") if isinstance(pages, dict) else None
    routes = (
        [row.get("route") for row in page_rows if isinstance(row, dict)]
        if isinstance(page_rows, list)
        else []
    )
    if not routes or not all(isinstance(route, str) for route in routes):
        fail("RAOS_V2_BROWSER_EVIDENCE_ROUTE_INVALID")
    generated_digests: dict[str, str] = {}
    for route in routes:
        assert isinstance(route, str)
        relative = (
            Path("changes/raos-v2/phase-2/preview/index.html")
            if route == "/"
            else Path("changes/raos-v2/phase-2/preview")
            / route.lstrip("/")
            / "index.html"
        )
        payload = preview.get(relative)
        if not isinstance(payload, bytes):
            fail("RAOS_V2_BROWSER_EVIDENCE_ROUTE_INVALID")
        generated_digests[route] = sha256(payload)
    if generated_digests != recorded_digests:
        fail("RAOS_V2_BROWSER_EVIDENCE_PREVIEW_DRIFT")
    required_assertions = {
        "routes": 9,
        "viewports": [320, 360, 390, 768, 1440],
        "axe_runs": 45,
        "axe_violations": 0,
        "axe_incomplete": 0,
        "horizontal_overflow": 0,
        "outbound_requests": 0,
        "persistent_records": 0,
        "keyboard_only": True,
        "zoom_200_percent": True,
        "forced_colors": True,
        "reduced_motion": True,
        "accessibility_tree_routes": 9,
        "screen_reader_smoke": True,
        "unnamed_interactive_count": 0,
        "keyboard_routes": 9,
        "reflow_400_percent": True,
        "javascript_disabled_routes": 2,
        "javascript_disabled_fallback": True,
        "transfer_budget_routes": 9,
        "transfer_budgets": True,
    }
    if any(
        assertions.get(key) != expected for key, expected in required_assertions.items()
    ):
        fail("RAOS_V2_BROWSER_EVIDENCE_ASSERTION_FAILED")
    raw_path_value = raw_receipt.get("local_path")
    harness_path_value = raw_receipt.get("harness_path")
    if (
        raw_path_value != "output/playwright/raos-v2-local-browser-evidence.json"
        or harness_path_value != "tests/raos_v2/browser-validation.mjs"
        or raw_receipt.get("command_contract")
        != "NODE24_LOCAL_CDP_AXE_WITH_ABSOLUTE_BROWSER_AND_OUTPUT_PLAYWRIGHT_RECEIPT_V1"
        or raw_receipt.get("exit_status") != 0
    ):
        fail("RAOS_V2_BROWSER_EVIDENCE_INPUT_INVALID")
    harness_path = ROOT / str(harness_path_value)
    try:
        harness_payload = _read_local_evidence_file(harness_path, root=ROOT)
    except ValidationFailure:
        fail("RAOS_V2_BROWSER_HARNESS_MISSING")
    if (
        harness_path.is_symlink()
        or not harness_path.is_file()
        or len(harness_payload) != raw_receipt.get("harness_bytes")
        or sha256(harness_payload) != raw_receipt.get("harness_sha256")
    ):
        fail("RAOS_V2_BROWSER_HARNESS_DRIFT")
    raw_path = ROOT / raw_path_value
    raw_verification = "RECORDED_NOT_REVERIFIED"
    if raw_path.exists() or raw_path.is_symlink():
        try:
            payload = _read_local_evidence_file(raw_path, root=ROOT)
        except ValidationFailure:
            fail("RAOS_V2_BROWSER_RAW_RECEIPT_INVALID")
        if len(payload) != raw_receipt.get("bytes") or sha256(
            payload
        ) != raw_receipt.get("sha256"):
            fail("RAOS_V2_BROWSER_RAW_RECEIPT_DRIFT")
        raw = load_json_strict(payload)
        if (
            not isinstance(raw, dict)
            or raw.get("classification") != "PASSED_LOCAL"
            or raw.get("externalActions") != "NOT_EXECUTED"
            or raw.get("previewDigests") != generated_digests
            or raw.get("harnessPath") != harness_path_value
            or raw.get("harnessSha256") != raw_receipt.get("harness_sha256")
            or raw.get("harnessBytes") != raw_receipt.get("harness_bytes")
            or raw.get("commandContract") != raw_receipt.get("command_contract")
            or raw.get("exitStatus") != raw_receipt.get("exit_status")
        ):
            fail("RAOS_V2_BROWSER_RAW_RECEIPT_INVALID")
        raw_routes = raw.get("routes")
        raw_viewports = raw.get("viewports")
        raw_keyboard = raw.get("keyboard")
        raw_media = raw.get("media")
        raw_accessibility = raw.get("accessibility")
        raw_javascript_disabled = raw.get("javascriptDisabled")
        raw_reflow = raw.get("reflow")
        raw_transfer = raw.get("transfer")
        raw_network = raw.get("network")
        raw_persistence = raw.get("persistence")
        raw_runtime = raw.get("runtime")
        raw_browser = raw.get("browser")
        raw_checker = raw.get("checker")
        viewport_names = {
            "reflow-320-equivalent-400pct",
            "mobile-360",
            "mobile-390",
            "tablet-768",
            "desktop-1440",
        }
        checker_field_map = {
            "pass": "pass",
            "fail": "fail",
            "count_fail": "countFail",
            "unknown": "unknown",
            "underseat_unknown": "underseatUnknown",
            "before_observed_boundary_unknown": "beforeObservedBoundaryUnknown",
            "review_deadline_stale": "reviewDeadlineStale",
            "ana_international_no_match": "anaInternationalNoMatch",
            "ana_unknown_scope": "anaUnknownScope",
            "peach_international_pass": "peachInternationalPass",
            "unknown_dominates_no_match": "unknownDominatesNoMatch",
            "all_segment_intersection": "allSegmentIntersection",
        }
        if (
            not isinstance(raw_routes, dict)
            or len(raw_routes) != 9
            or any(
                not isinstance(row, dict)
                or row.get("axeViolations") != 0
                or row.get("axeIncomplete") != []
                or row.get("mobileOverflow") is not False
                or not isinstance(row.get("viewportAudits"), dict)
                or set(row["viewportAudits"]) != viewport_names
                or any(
                    not isinstance(audit, dict)
                    or audit.get("axeViolations") != 0
                    or audit.get("axeIncomplete") != []
                    or audit.get("horizontalOverflow") is not False
                    for audit in row["viewportAudits"].values()
                )
                for row in raw_routes.values()
            )
            or not isinstance(raw_viewports, dict)
            or set(raw_viewports) != viewport_names
            or any(
                not isinstance(row, dict)
                or row.get("axeRuns") != 9
                or row.get("routes") != 9
                or row.get("horizontalOverflow") is not False
                for row in raw_viewports.values()
            )
            or not isinstance(raw_keyboard, dict)
            or raw_keyboard.get("skipLink") is not True
            or raw_keyboard.get("routes") != 9
            or raw_keyboard.get("focusTraversalAllRoutes") is not True
            or raw_keyboard.get("skipLinkAllRoutes") is not True
            or not isinstance(raw_keyboard.get("focusRingPx"), (int, float))
            or raw_keyboard.get("focusRingPx", 0) < 3
            or not isinstance(raw_keyboard.get("routeResults"), dict)
            or set(raw_keyboard["routeResults"]) != set(generated_digests)
            or any(
                not isinstance(row, dict)
                or row.get("focusTraversal") is not True
                or row.get("skipLink") is not True
                or row.get("mainFocused") is not True
                or not isinstance(row.get("focusRingPx"), (int, float))
                or row.get("focusRingPx", 0) < 3
                for row in raw_keyboard["routeResults"].values()
            )
            or not isinstance(raw_media, dict)
            or not isinstance(raw_media.get("zoom"), dict)
            or raw_media["zoom"].get("horizontalOverflow") is not False
            or raw_media["zoom"].get("routes") != 9
            or not isinstance(raw_media.get("media"), dict)
            or raw_media["media"].get("forcedColors") is not True
            or raw_media["media"].get("reducedMotion") is not True
            or raw_media["media"].get("routes") != 9
            or not isinstance(raw_accessibility, dict)
            or raw_accessibility.get("routes") != 9
            or raw_accessibility.get("fullAxTreeAllRoutes") is not True
            or raw_accessibility.get("screenReaderSmokeAllRoutes") is not True
            or raw_accessibility.get("unnamedInteractiveCount") != 0
            or not isinstance(raw_accessibility.get("routeResults"), dict)
            or set(raw_accessibility["routeResults"]) != set(generated_digests)
            or any(
                not isinstance(row, dict)
                or row.get("fullTreeQueried") is not True
                or row.get("screenReaderSmoke") is not True
                or row.get("unnamedInteractiveCount") != 0
                or row.get("levelOneHeadingCount") != 1
                for row in raw_accessibility["routeResults"].values()
            )
            or not isinstance(raw_javascript_disabled, dict)
            or raw_javascript_disabled.get("testedRoutes") != 2
            or not isinstance(raw_javascript_disabled.get("routes"), dict)
            or set(raw_javascript_disabled.get("routes", {}))
            != {"/", "/tools/carry-on-size-checker/"}
            or any(
                not isinstance(row, dict)
                or row.get("fallbackVisible") is not True
                or row.get("formVisible") is not True
                or row.get("initialState") != "UNKNOWN"
                for row in raw_javascript_disabled["routes"].values()
            )
            or not isinstance(raw_reflow, dict)
            or raw_reflow.get("cssViewportWidthPx") != 320
            or raw_reflow.get("equivalentSourceWidthPx") != 1280
            or raw_reflow.get("equivalentZoomPercent") != 400
            or raw_reflow.get("horizontalOverflow") is not False
            or raw_reflow.get("routes") != 9
            or not isinstance(raw_transfer, dict)
            or not isinstance(raw_transfer.get("routes"), dict)
            or set(raw_transfer["routes"]) != set(generated_digests)
            or any(
                not isinstance(row, dict)
                or row.get("withinCeiling") is not True
                or row.get("inlineSingleDocument") is not True
                or row.get("additionalResourceBytes") != 0
                or not isinstance(row.get("bytes"), int)
                or not isinstance(row.get("ceilingBytes"), int)
                or row["bytes"] > row["ceilingBytes"]
                for row in raw_transfer["routes"].values()
            )
            or not isinstance(raw_network, dict)
            or raw_network.get("outboundRequests") != 0
            or not isinstance(raw_persistence, dict)
            or any(value != 0 for value in raw_persistence.values())
            or not isinstance(raw_runtime, dict)
            or raw_runtime.get("nodeMajor") != 24
            or not isinstance(raw_runtime.get("nodeVersion"), str)
            or not isinstance(raw_browser, dict)
            or raw_browser.get("version") != browser_data.get("version")
            or raw_browser.get("executableSha256")
            != browser_data.get("executable_sha256")
            or not isinstance(raw_checker, dict)
            or any(
                raw_checker.get(raw_key) != checker_states.get(recorded_key)
                for recorded_key, raw_key in checker_field_map.items()
            )
        ):
            fail("RAOS_V2_BROWSER_RAW_RECEIPT_ASSERTION_FAILED")
        raw_verification = "RAW_RECEIPT_VERIFIED_LOCAL"
    result = deepcopy(value)
    result["raw_verification"] = raw_verification
    return result


def _preview_evidence_context(
    parsed: Mapping[Path, object], preview: Mapping[Path, bytes]
) -> tuple[dict[str, str], dict[str, str]]:
    pages = parsed.get(
        Path("packages/web-ui/src/decision-support-v2/preview/pages.v2.json")
    )
    page_rows = pages.get("pages") if isinstance(pages, dict) else None
    if not isinstance(page_rows, list) or len(page_rows) != 9:
        fail("RAOS_V2_VISUAL_EVIDENCE_ROUTE_INVALID")
    digests: dict[str, str] = {}
    classifications: dict[str, str] = {}
    state_to_classification = {
        "LOCAL_PREVIEW": "PUBLIC_CANDIDATE",
        "PLANNED_LOCKED": "PLANNED_LOCKED",
        "FIXTURE_ONLY": "FIXTURE_ONLY",
    }
    for row in page_rows:
        if not isinstance(row, dict):
            fail("RAOS_V2_VISUAL_EVIDENCE_ROUTE_INVALID")
        route = row.get("route")
        state = row.get("publication_state")
        if (
            not isinstance(route, str)
            or route in digests
            or state not in state_to_classification
        ):
            fail("RAOS_V2_VISUAL_EVIDENCE_ROUTE_INVALID")
        relative = (
            Path("changes/raos-v2/phase-2/preview/index.html")
            if route == "/"
            else Path("changes/raos-v2/phase-2/preview")
            / route.lstrip("/")
            / "index.html"
        )
        payload = preview.get(relative)
        if not isinstance(payload, bytes):
            fail("RAOS_V2_VISUAL_EVIDENCE_ROUTE_INVALID")
        digests[route] = sha256(payload)
        classifications[route] = state_to_classification[str(state)]
    return digests, classifications


def validated_visual_evidence(
    parsed: Mapping[Path, object], preview: Mapping[Path, bytes]
) -> dict[str, object]:
    value = parsed.get(VISUAL_EVIDENCE_INPUT_PATH)
    if not isinstance(value, dict):
        fail("RAOS_V2_VISUAL_REVIEW_EVIDENCE_INPUT_INVALID")
    digests, classifications = _preview_evidence_context(parsed, preview)
    try:
        verification = verify_visual_review_evidence(
            value,
            preview_digests=digests,
            route_classifications=classifications,
            root=ROOT,
        )
    except ValidationFailure:
        fail("RAOS_V2_VISUAL_REVIEW_EVIDENCE_INPUT_INVALID")
    result = deepcopy(value)
    result["verification"] = verification
    return result


def phase2_validation_document(
    parsed: Mapping[Path, object],
    preview: Mapping[Path, bytes],
    publication: Mapping[str, object],
    migration: Mapping[str, object],
) -> dict[str, object]:
    airline = parsed.get(
        Path("changes/raos-v2/phase-2/fixtures/recorded-airline-rules.v2.json")
    )
    products = parsed.get(
        Path("changes/raos-v2/phase-2/data/ace-carry-on-models.v2.json")
    )
    sources = parsed.get(
        Path("changes/raos-v2/phase-2/sources/source-registry.v2.yaml")
    )
    if not all(isinstance(value, dict) for value in (airline, products, sources)):
        fail("RAOS_V2_PHASE2_VALIDATION_INPUT_INVALID")
    assert isinstance(airline, dict)
    assert isinstance(products, dict)
    assert isinstance(sources, dict)
    browser = validated_browser_evidence(parsed, preview)
    visual = validated_visual_evidence(parsed, preview)
    local_test = recorded_local_test_evidence()
    browser_assertions = browser.get("assertions")
    raw_receipt = browser.get("raw_receipt")
    browser_data = browser.get("browser")
    assert isinstance(browser_assertions, dict)
    assert isinstance(raw_receipt, dict)
    assert isinstance(browser_data, dict)
    visual_verification = visual.get("verification")
    if not isinstance(visual_verification, dict):
        fail("RAOS_V2_VISUAL_REVIEW_EVIDENCE_INPUT_INVALID")
    recorded_local_test = deepcopy(local_test)
    recorded_local_test["raw_verification"] = "RECORDED_NOT_REVERIFIED"
    recorded_visual_verification = deepcopy(visual_verification)
    recorded_visual_verification["raw_verification"] = "RECORDED_NOT_REVERIFIED"
    tests = [f"T-V2-{value:03d}" for value in range(20, 47)] + ["T-V2-051"]
    gate_passed = (
        local_test.get("status") == "PASSED_LOCAL"
        and browser.get("classification") == "PASSED_LOCAL"
        and browser.get("raw_verification")
        in {"RAW_RECEIPT_VERIFIED_LOCAL", "RECORDED_NOT_REVERIFIED"}
        and visual_verification.get("effective_status")
        == "PASSED_LOCAL_MANUAL_VISUAL_REVIEW"
        and visual_verification.get("raw_verification")
        in {
            "RAW_CAPTURE_AND_27_PNGS_VERIFIED_LOCAL",
            "RECORDED_NOT_REVERIFIED",
        }
    )
    return {
        "schema": "RAOS_V2_PHASE2_VALIDATION_V1",
        "status": (
            "PASSED_LOCAL_RECORDED" if gate_passed else "READY_FOR_LOCAL_TEST_GATE"
        ),
        "evidence_scope": "LOCAL_ONLY",
        "checks": {
            "strict_source_inputs": len(parsed),
            "recorded_airline_rule_sets": len(airline.get("rule_sets", [])),
            "recorded_official_sources": len(sources.get("sources", [])),
            "product_models": len(products.get("products", [])),
            "preview_routes": len(preview),
            "real_publication_state": publication.get("state"),
            "real_publication_sealed": False,
            "migration_mode": migration.get("mode"),
            "rakuten_adapter": "RECORDED_ONLY",
            "wordpress_adapter": "DISABLED_DRY_RUN",
            "event_collector": "LOCAL_SINK_ONLY",
            "network_default": "DENY",
            "live_write_capability": False,
        },
        "implemented_backlog_ids": [f"B-V2-{value:03d}" for value in range(19, 34)],
        "completed_backlog_ids": (
            [f"B-V2-{value:03d}" for value in range(19, 35)] if gate_passed else []
        ),
        "pending_exit_backlog_ids": ([] if gate_passed else ["B-V2-034"]),
        "local_test_contracts": {
            "ids": tests,
            "status": local_test.get("status"),
            "required_owner": "tests/raos_v2",
            "receipt": recorded_local_test,
            "generator_execution": "NOT_EXECUTED_BY_GENERATOR",
        },
        "browser_evidence": {
            "classification": browser.get("classification"),
            "evidence_basis": "COMMITTED_SANITIZED_RECORDED_RECEIPT",
            "browser": browser_data.get("version"),
            **browser_assertions,
            "receipt_path": raw_receipt.get("local_path"),
            "receipt_sha256": raw_receipt.get("sha256"),
            "receipt_bytes": raw_receipt.get("bytes"),
            "tracked": False,
            "raw_verification": "RECORDED_NOT_REVERIFIED",
            "ci_without_raw": "RECORDED_NOT_REVERIFIED",
        },
        "visual_review_evidence": {
            "classification": visual.get("classification"),
            "reviewer_class": visual.get("reviewer_class"),
            "reviewed_at_jst": visual.get("reviewed_at_jst"),
            "capture_receipt": visual.get("capture_receipt"),
            "aggregate_findings": visual.get("aggregate_findings"),
            "capture_hash_review": visual.get("capture_hash_review"),
            "verification": recorded_visual_verification,
            "evidence_basis": "SEPARATE_MANUAL_REVIEW_BOUND_TO_CAPTURE_AND_27_PNG_HASHES",
            "tracked": True,
            "ci_without_raw": "RECORDED_NOT_REVERIFIED",
        },
        "external_actions": "NOT_EXECUTED",
        "formal_ci": "NOT_CLAIMED_BY_LOCAL_ARTIFACT",
    }


def local_evidence_bundle_document(
    capture: Mapping[str, object],
    generated: Mapping[Path, bytes],
    validation: Mapping[str, object],
) -> dict[str, object]:
    artifact_rows = [
        {
            "path": path.as_posix(),
            "bytes": len(payload),
            "sha256": sha256(payload),
        }
        for path, payload in sorted(generated.items())
    ]
    test_contracts = validation.get("local_test_contracts")
    if not isinstance(test_contracts, dict):
        fail("RAOS_V2_PHASE2_TEST_CONTRACT_INVALID")
    gate_status = validation.get("status")
    gate_passed = gate_status == "PASSED_LOCAL_RECORDED"
    return {
        "schema": "RAOS_V2_LOCAL_EVIDENCE_BUNDLE_V1",
        "phase": "P2",
        "classification": (
            "PASSED_LOCAL_RECORDED_WITH_BROWSER_AND_MANUAL_VISUAL_EVIDENCE"
            if gate_passed
            else "GENERATED_LOCAL_PENDING_COMBINED_EVIDENCE_GATE"
        ),
        "gate_status": gate_status,
        "source_head": (
            capture.get("repository", {}).get("head")
            if isinstance(capture.get("repository"), dict)
            else None
        ),
        "source_inputs": _phase2_input_inventory(),
        "generated_artifacts": artifact_rows,
        "tests": {
            "status": test_contracts.get("status"),
            "ids": test_contracts.get("ids"),
            "owner": "tests/raos_v2",
            "required_command": "uv run --offline pytest -s -q tests/raos_v2",
            "generator_execution": "NOT_EXECUTED_BY_GENERATOR",
            "receipt": test_contracts.get("receipt"),
        },
        "visual_a11y_evidence": [
            validation.get("browser_evidence"),
            validation.get("visual_review_evidence"),
        ],
        "analytics_evidence": {
            "status": "UNAVAILABLE",
            "local_semantic_evidence": "TEST_OWNER_REQUIRED",
            "collector": "LOCAL_SINK_ONLY",
            "production_sender": "DISABLED",
            "note": "production KPI values remain UNAVAILABLE; synthetic QDS semantics are tested locally",
        },
        "security": {
            "credential_required": False,
            "default_network": "DENY",
            "public_internal_isolation": "PRESERVED",
            "publication_capability": False,
        },
        "external_actions": {
            "executed": [],
            "not_executed": [
                "publication",
                "deployment",
                "credential entry",
                "spend",
                "live provider write",
                "WordPress write",
                "production migration",
                "irreversible deletion",
            ],
        },
        "backlog_id": "B-V2-033",
        "test_ids": ["T-V2-023", "T-V2-039", "T-V2-051"],
    }


def phase2_report_document(
    capture: Mapping[str, object], evidence: Mapping[str, object]
) -> str:
    repository = capture.get("repository")
    head = repository.get("head") if isinstance(repository, dict) else "UNAVAILABLE"
    evidence_sha = sha256(canonical_json_bytes(evidence))
    test_receipt = evidence.get("tests")
    test_status = (
        test_receipt.get("status") if isinstance(test_receipt, dict) else "UNAVAILABLE"
    )
    local_gate_passed = evidence.get("gate_status") == "PASSED_LOCAL_RECORDED"
    backlog_label = (
        ", ".join(f"B-V2-{value:03d}" for value in range(19, 35))
        if local_gate_passed
        else (
            ", ".join(f"B-V2-{value:03d}" for value in range(19, 34))
            + "; B-V2-034 pending local test gate"
        )
    )
    browser_rows = evidence.get("visual_a11y_evidence")
    browser = (
        browser_rows[0]
        if isinstance(browser_rows, list)
        and browser_rows
        and isinstance(browser_rows[0], dict)
        else {}
    )
    browser_status = browser.get("classification", "UNAVAILABLE")
    browser_raw = browser.get("raw_verification", "UNAVAILABLE")
    visual = (
        browser_rows[1]
        if isinstance(browser_rows, list)
        and len(browser_rows) == 2
        and isinstance(browser_rows[1], dict)
        else {}
    )
    visual_verification = visual.get("verification")
    visual_status = visual.get("classification", "UNAVAILABLE")
    visual_raw = (
        visual_verification.get("raw_verification", "UNAVAILABLE")
        if isinstance(visual_verification, dict)
        else "UNAVAILABLE"
    )
    return f"""# RAOS V2 Phase 2 report

## Outcome

The offline carry-on vertical slice is implemented and measurable locally. It
contains recorded official-airline and Rakuten adapters, an exact-decimal
multi-segment checker, three-product identity/selection logic, seven future-route
reader surfaces plus home and one non-public DIFFERENCE fixture, local-only events,
and a disabled WordPress dry-run boundary.

## Exit evidence

- Phase: P2
- Source head: `{head}`
- Worktree before: `CLEAN` at the recorded dedicated-worktree baseline
- Worktree after: `LOCAL_IMPLEMENTATION_CHANGES_PRESENT` (not production state)
- Backlog status: {backlog_label}
- Local test receipt: `{test_status}` for T-V2-020..046 and T-V2-051; generator does not execute tests
- Browser/a11y recorded evidence: `{browser_status}`; raw verification: `{browser_raw}`; required CI must run its own gate
- Manual visual review: `{visual_status}` across 27 route/viewport captures; raw verification: `{visual_raw}`
- Evidence bundle SHA-256: `{evidence_sha}`
- Analytics: production values `UNAVAILABLE`; semantic QDS/local sink evidence only
- Planning ceiling: 80 hours; actual human time `UNAVAILABLE`; external spend: JPY 0
- Rollback: route/canonical/robots exact-tuple simulation `PASSED_LOCAL`; production backup/restore `NOT_EXECUTED`
- Exit gate: `{"PASS_LOCAL_RECORDED" if local_gate_passed else "PENDING_LOCAL_TEST_GATE"}`

## Publication and migration boundary

The real comparison candidate stops at `EVIDENCE_COMPLETE`: human review is
`NOT_EXECUTED`, it has no seal, and no `PUBLISHED` transition exists. Only the
explicit synthetic contract fixture reaches `PACKAGE_SEALED`. The migration
manifest preserves `/carry-on-suitcase-comparison/` and is
`LOCAL_SIMULATION_ONLY`; public indexing, WordPress write and URL migration await
the separately approved Phase 3 boundary.

## Gaps and external actions

Formal/required CI is not relabelled by this local report. Publication,
deployment, credential entry, spend, provider/WordPress writes, production
migration, policy activation and irreversible deletion are all `NOT_EXECUTED`.
The raw browser receipt remains untracked under `output/playwright`; only its
digest metadata is recorded. Product price, stock, confirmed reward and every
production KPI remain `UNAVAILABLE` rather than zero.
"""


def integration_pr_body_document(evidence: Mapping[str, object]) -> str:
    evidence_sha = sha256(canonical_json_bytes(evidence))
    test_receipt = evidence.get("tests")
    test_status = (
        test_receipt.get("status") if isinstance(test_receipt, dict) else "UNAVAILABLE"
    )
    browser_rows = evidence.get("visual_a11y_evidence")
    browser_status = (
        browser_rows[0].get("classification", "UNAVAILABLE")
        if isinstance(browser_rows, list)
        and browser_rows
        and isinstance(browser_rows[0], dict)
        else "UNAVAILABLE"
    )
    visual_status = (
        browser_rows[1].get("classification", "UNAVAILABLE")
        if isinstance(browser_rows, list)
        and len(browser_rows) == 2
        and isinstance(browser_rows[1], dict)
        else "UNAVAILABLE"
    )
    return f"""# RAOS V2 Phase 0-2 offline vertical slice

## Design authority

- Successor package SHA-256: `{PACKAGE_SHA256}`
- Immutable source layer: `changes/raos-v2/source-package/2.0.0-design/**`
- The package prompt was excluded and never executed.
- Clarifications are recorded only in `changes/raos-v2/clarifications.v1.yaml`.

## Decision corrections

- `C-V2-002`: the machine contract has seven templates: HOME, HUB, GUIDE,
  COMPARISON, DIFFERENCE, TOOL and POLICY; source prose referring to six is
  superseded.
- `C-V2-003`: Phase 0 owns T-V2-001..006, T-V2-040 and T-V2-051;
  T-V2-007 starts in Phase 1.
- `C-V2-004`: the effective planning ceilings are P0=16h, P1=40h and P2=80h;
  backlog row estimates are reconciliation data, not additive gates.
- `C-V2-005` + `C-V2-010`: B-V2-009 closes over B-V2-001..008, and the
  corrected Phase 2 exit dependencies are closed before B-V2-034.
- `C-V2-007` + `C-V2-008`: real Phase 0-2 content remains unreviewed and
  unsealed; only synthetic fixtures may seal, and the disabled WordPress
  adapter belongs to Phase 2.

## Delivered

- Phase 0: clean dedicated-worktree baseline, public read-only URL inventory,
  metric/deprecation/rollback contracts and nine required artifacts.
- Phase 1: one carry-on wedge, 25-asset portfolio, seven templates, route/design
  contracts, ten entity schemas and disabled-by-default ports.
- Phase 2: recorded official sources/adapters, deterministic checker and product
  selection, local preview, content/review/media/event contracts, publication
  candidate, migration simulation and evidence bundle.

Evidence bundle SHA-256: `{evidence_sha}`. Recorded local test status is
`{test_status}`, browser/a11y evidence is `{browser_status}`, and independent
manual visual review is `{visual_status}`. The generator
does not execute either gate; required repository CI remains the merge gate and
is not claimed by this generated body.

## Safety and rollback

The public site and existing URL are unchanged. The real content package is
`EVIDENCE_COMPLETE`, not sealed or published. WordPress is
`DISABLED_DRY_RUN`, Rakuten is `RECORDED_ONLY`, analytics is `LOCAL_SINK_ONLY`,
and normal runtime/test network is denied. Route/canonical/robots rollback was
round-tripped locally against its captured hash binding.

## External/live actions

Publication, deployment, credentials, spending, live provider/WordPress writes,
production migration, policy activation and irreversible deletion:
`NOT_EXECUTED`.
"""


def phase3_backup_runbook_document() -> str:
    return """# RAOS V2 Phase 3 production backup/export runbook

## Boundary

This is a human runbook for `B-V2-035`; no backup, credential access, WordPress
read/write, deployment or production mutation was executed while generating it.
Stop before any action unless the owner has separately approved the exact
production task and has a recoverable storage location outside this repository.

## Exact target

- Origin: `https://kurashinoshirube.com`
- Existing route: `/carry-on-suitcase-comparison/`
- Migration mode: update the existing public route in place; do not create a
  redirect, alternate public slug or second indexable page.

## Create-once pre-action binding before final review

The Phase 0 body hash is historical evidence only. Never overwrite or relabel it
as current. First create a new `RAOS_V2_PHASE3_PREACTION_BINDING_V1` from one
bounded public read-only capture and one owner-held WordPress export of the same
existing post. If the public body, post ID or export identity cannot be bound
exactly, keep the historical candidate unsealable and stop.

1. Record the WordPress site, core version, active theme/version, relevant
   plugin versions and the exact target post ID. Do not put credentials or raw
   database exports in Git, logs or the review packet.
2. Export recoverable bytes for the target post: title, slug, excerpt, content,
   status, author, publish/modified dates, taxonomy, comment/ping state, featured
   media references and every SEO/Yoast field that affects title, description,
   canonical, robots or schema.
3. Export the active theme/plugin artifact needed to restore the previous
   presentation, and record its version plus SHA-256 outside the repository.
4. Record public status, redirect chain, canonical, HTML/meta and HTTP robots,
   sitemap membership, H1 and body hash using the bounded
   `capture-phase3-public --public-read-only` command immediately before the
   external action. The same capture must fetch the fixed same-origin
   `/robots.txt`, accept only status 200, 404 or 410, retain only its SHA-256
   and metadata, discard its body, and prove that the target route is allowed
   for Googlebot. Enumerate crawler-specific robots meta such as `googlebot`
   and `googlebot-news` and require every directive to remain indexability
   safe; metadata nested in `template` or `noscript` is not accepted as head
   metadata evidence. Phase 0 evidence is a historical baseline and must not
   be overwritten.
5. Store raw exports in recoverable owner-controlled storage. Create only a
   sanitized receipt containing opaque hashes, version identifiers, field names
   and the exact target binding for review by the local generator. The local,
   network-free derivation command is:

   ```text
   python scripts/raos_v2_phase3_execution.py derive-preaction \
     --public-capture changes/raos-v2/recorded-inputs/phase3/<capture>.json \
     --owner-export /absolute/owner/storage/wordpress-owner-export.json \
     --restore-artifact /absolute/owner/storage/restore-artifact \
     --theme-plugin-artifact /absolute/owner/storage/theme-plugin-artifact \
     --seo-state /absolute/owner/storage/seo-state \
     --redirect-map /absolute/owner/storage/redirect-map \
     --sitemap-state /absolute/owner/storage/sitemap-state \
     --output changes/raos-v2/recorded-inputs/phase3/<preaction-input>.json
   ```

   Every owner-held path must resolve to a nonsymlink regular file outside the
   repository. The command is create-once, rejects a capture/export pair more
   than five minutes apart and persists no raw WordPress field value or external
   path. The currently recorded public observation is deliberately unpaired and
   cannot be substituted for this receipt.

6. Reissue the local update/review candidate from the verified pre-action
   binding. Only that reissued digest may be given to the human reviewer. Run:

   ```text
   python scripts/raos_v2_phase3_execution.py reissue-candidate \
     --preaction-input changes/raos-v2/recorded-inputs/phase3/<preaction-input>.json \
     --output changes/raos-v2/recorded-inputs/phase3/<reissued-review-bundle>.json
   ```

   The reissue is local and create-once, rejects pre-action evidence older than
   five minutes, reconstructs the historical candidate through the versioned
   domain contract and leaves all network/WordPress/publication capabilities
   false. The bundle is independently verified against
   `contracts/raos-v2/v2/reissued-review-bundle.schema.json`, the current
   generator-owned candidate and the exact pre-action input. A generic
   conversation approval is not an artifact-specific receipt. The current JSON
   receipt has no trusted signature or approval source: even with
   `accepted=true` it is classified `UNAUTHENTICATED_OWNER_ASSERTION` with
   `acceptance_authority=false`. The identity-bearing fields are fixed to
   `reviewer_id=OWNER_ASSERTION_LOCAL` and
   `review_version=P3-OWNER-ASSERTION-V1`; a name, email or caller-selected ID is
   rejected rather than persisted. It may create only a simulation seal. After
   the owner creates that schema-valid assertion, seal locally with:

   ```text
   python scripts/raos_v2_phase3_execution.py seal-candidate \
     --review-bundle changes/raos-v2/recorded-inputs/phase3/<reissued-review-bundle>.json \
     --human-review-receipt /absolute/owner/storage/human-review-receipt.json \
     --output changes/raos-v2/recorded-inputs/phase3/<sealed-simulation-package>.json
   ```

   The seal command has no network or WordPress capability and rejects a
   synthetic, stale, schema-mismatched or digest-mismatched assertion. Its
   package is explicitly `simulation_only=true` and
   `approval_acceptance_authority=false`; it never satisfies human approval,
   public-write authority or the Phase 3 exit. The tracked plugin binding stays
   `DEPLOYMENT_DISABLED`; never hand-edit or deploy it as armed.

   `derive-cutover-binding` is deliberately fail-closed. It independently
   reconstructs any caller-supplied sealed package through the same domain seal
   blockers, then returns
   `RAOS_V2_PHASE3_CUTOVER_PREWRITE_EVIDENCE_REQUIRED`. It cannot emit or certify
   `ARMED_EXACT_LEGACY_OR_SEALED` until a separately designed trusted
   artifact-specific approval source plus fresh post-approval `PRE_WRITE_EXPORT`
   and disabled-plugin dry-run verifiers are all implemented. A caller-authored
   digest or JSON receipt cannot substitute for any of them.
7. After the local simulation seal, create `PRE_WRITE_EXPORT` and its
   disabled dry-run receipt. This pre-write export must bind the existing
   field hashes, sealed pre-action digest and same current body, be no older than
   five minutes at evaluation and be captured after the owner assertion. Any
   intervening change requires a new pre-action binding, candidate reissue and
   assertion. It is not post-publication evidence and the current operator does
   not consume it to arm the plugin. Keep the binding disabled and stop.

If any field, restore byte sequence, target identity or checksum is unavailable,
record `UNAVAILABLE` and stop. Missing data is never equivalent to an empty field.

## Deploy, preview and metadata gate

The route-scoped plugin renders CSS and the exact content-verification envelope;
it does not generate JSON-LD. Plugin version 0.6.0 models one future safe cutover
order, but the trusted approval/pre-write verifier needed to create its armed
artifact is not implemented. Do not activate or write. If that verifier is
implemented in a later approved phase, the order is: install inactive,
atomically replace the disabled adjacent binding with the independently verified
owner-export-bound artifact, activate while the exact legacy database bytes
still remain, and only then write the exact sealed bytes.
The exact legacy state preserves the existing filtered response without V2 CSS;
the exact sealed state discards earlier filter output and envelopes only the
reviewed raw fragment. Disabled, missing, partial, intermediate or drifted
states block the target. Writing sealed bytes before activation is prohibited
because an inactive plugin cannot protect the route. A content filter registered after RAOS at `PHP_INT_MAX`
terminates only the target request with a fixed 503 before the later callback
can mutate it. V2 projection is limited to the exact current target post inside
the singular main query's main loop. Only a verified different current post is
treated as a secondary `the_content` call and preserves its filtered input;
missing, ambiguous or out-of-main-loop target context is blocked. The candidate depends on the existing
Yoast or single metadata-owner configuration. Before publication, a nonpublic
WordPress preview must prove the
exact `Article`, `BreadcrumbList`, `Organization` and `WebSite` graph required by
T-V2-036, with visible-title/canonical parity and no forbidden rich-result type.
It must also emit exactly one HTML title equal to the sealed `post_title` (no
unreviewed site-name suffix) and exactly one meta description equal to the
sealed `meta_description`.
This is an unexecuted external blocker. A mismatch must not be accepted as a
completed publication: correct the metadata configuration before cutover, or
restore the exported state if the mismatch is discovered after a write.

After an approved publication, the HTTP verification receipt must be derived
from three independent inputs: the fresh bounded public capture, the sealed
package and a separate `POST_ACTION_OWNER_EXPORT` of every sealed WordPress
field after the write. This after-state export must bind the same post ID,
sealed AFTER field hashes, final public body and pre-action digest. It is not the
pre-write dry-run export. The post-action HTTP capture and export form one
atomic paired-capture contract: both must be independently derived and evaluated
within the same five-minute window. A capture alone or a self-asserted receipt
cannot satisfy this gate. The HTTP receipt's indexability evidence scope is
`HEAD_META_HTTP_SITEMAP_AND_ROBOTS_TXT`: it must include the safe HTML/meta and
HTTP robots state, sitemap membership, plus the hashed-and-discarded
same-origin `/robots.txt` response and a positive Googlebot allowance for the
target route. Crawler-specific meta must also be counted and free of `noindex`,
`nofollow` and `none` directives.

After any separately approved publication, B-V2-040 also requires a separate
public read-only browser receipt at 390, 768 and 1440px. It must bind the public
body, sealed package and deployed plugin hashes while checking computed
disclosure/blocked-CTA visibility, keyboard use, 200% zoom, axe WCAG 2.2 AA and
resource/network behavior. Raw capture and screenshot bytes must remain in
owner-controlled storage outside Git. The local public-read-only recorder is
implemented in `tests/raos_v2/phase3-public-validation.mjs`; its raw receipt is
explicitly non-authoritative and cannot complete Phase 3. An independent
acceptance verifier must still recalculate the public HTTP receipt digest,
resource manifest, screenshot bytes/hashes and the harness, browser binary and
exact command hashes. Until that independent receipt exists, the generated
acceptance schema remains an unverified template and Phase 3 stays
`BLOCKED_EXTERNAL`.

## Restore rehearsal and triggers

Before publishing, the owner must be able to restore the exact post fields,
SEO fields, theme/plugin version and public route tuple from the export. Trigger
rollback for a wrong fact/model/CTA, hidden advertising disclosure, canonical or
indexability error, broken package binding, critical accessibility defect or
publication-state mismatch. Operational targets are to start rollback within 30
minutes of detection and verify the previous public state within two hours,
subject to host availability; these are targets, not guarantees.

## Evidence labels

- This runbook: `GENERATED_LOCAL`
- Production backup/export: `NOT_EXECUTED`
- Production restore: `NOT_EXECUTED`
- Public verification: `NOT_EXECUTED`
"""


def phase3_seo_change_plan_document(
    *, structured_data_expectation_sha256: str
) -> dict[str, object]:
    route = "/carry-on-suitcase-comparison/"
    canonical = f"https://kurashinoshirube.com{route}"
    return {
        "schema": "RAOS_V2_PHASE3_SEO_URL_CHANGE_PLAN_V1",
        "version": "1.0.0",
        "mode": "HUMAN_ACTION_PLAN_ONLY",
        "target_origin": "https://kurashinoshirube.com",
        "target_route": route,
        "safe_default": "PRESERVE_EXISTING_ROUTE_AND_INDEX_STATE",
        "route": {
            "before": route,
            "after": route,
            "change": "NONE",
        },
        "redirects": {
            "create": [],
            "update": [],
            "delete": [],
            "maximum_hops": 1,
            "loop_count": 0,
            "broad_home_redirect": False,
        },
        "canonical": {
            "before": canonical,
            "after": canonical,
            "change": "NONE",
            "owner": "YOAST_OR_CURRENT_SINGLE_METADATA_OWNER",
        },
        "robots": {
            "before": "index,follow",
            "after": "index,follow",
            "change": "NONE",
        },
        "sitemap": {
            "before_membership": True,
            "after_membership": True,
            "change": "NONE",
            "lastmod_rule": "MATERIAL_CONTENT_CHANGE_ONLY",
        },
        "structured_data": {
            "single_owner": "YOAST_OR_CURRENT_WORDPRESS_METADATA_OWNER",
            "plugin_generates_json_ld": False,
            "verification_status": "NOT_EXECUTED_EXTERNAL_BLOCKER",
            "test_gate": "T-V2-036",
            "expected_graph_sha256": structured_data_expectation_sha256,
            "allowed_types": [
                "Article",
                "BreadcrumbList",
                "Organization",
                "WebSite",
            ],
            "forbidden_types": [
                "Product",
                "Offer",
                "Review",
                "AggregateRating",
                "ItemList",
                "FAQPage",
                "HowTo",
            ],
            "custom_duplicate_graph": False,
            "failure": (
                "DO_NOT_COMPLETE_PUBLICATION; CORRECT_METADATA_BEFORE_CUTOVER_OR_"
                "ROLL_BACK_AFTER_WRITE"
            ),
        },
        "publication_aware_links": {
            "allowed_internal_routes": [
                "/",
                route,
                "/about-ad-policy/",
                "/privacy-policy/",
            ],
            "suppressed_until_published": [
                "/carry-on/",
                "/tools/carry-on-size-checker/",
                "/policy/how-we-compare-carry-on-products/",
            ],
        },
        "preconditions": [
            "fresh bounded public read-only capture",
            "recoverable exact WordPress export binding",
            "authenticated artifact-specific approval and semantically valid package seal",
            "fresh PRE_WRITE_EXPORT plus disabled-plugin dry-run bound by an independent verifier",
            "one-H1 and visible/structured-data parity check",
            (
                "exact Yoast/metadata-owner Article, BreadcrumbList, "
                "Organization and WebSite output verified"
            ),
        ],
        "failure": "BLOCK_AND_KEEP_CURRENT_PUBLIC_STATE",
        "production_change": "NOT_EXECUTED",
        "external_action_ids": ["EXT-013"],
        "backlog_id": "B-V2-038",
        "requirement_ids": ["R-V2-003", "R-V2-022", "R-V2-025"],
        "test_ids": [
            "T-V2-004",
            "T-V2-005",
            "T-V2-010",
            "T-V2-035",
            "T-V2-036",
            "T-V2-040",
        ],
    }


def phase3_privacy_review_packet_document() -> dict[str, object]:
    catalog = _read_yaml(Path("changes/raos-v2/phase-2/events/event-catalog.v2.yaml"))
    if not isinstance(catalog, dict):
        fail("RAOS_V2_PHASE3_PRIVACY_PACKET_INVALID")
    events = catalog.get("events")
    required = catalog.get("required_fields")
    optional = catalog.get("optional_fields")
    forbidden = catalog.get("forbidden_fields")
    if not all(
        isinstance(value, list) for value in (events, required, optional, forbidden)
    ):
        fail("RAOS_V2_PHASE3_PRIVACY_PACKET_INVALID")
    return {
        "schema": "RAOS_V2_PHASE3_PRIVACY_LEGAL_REVIEW_PACKET_V1",
        "version": "1.0.0",
        "classification": "OWNER_OR_COUNSEL_REVIEW_INPUT_NOT_LEGAL_ADVICE",
        "target_route": "/carry-on-suitcase-comparison/",
        "safe_default": {
            "production_sender": "DISABLED",
            "event_transmission": "OFF",
            "metric_state": "UNAVAILABLE",
            "site_and_links_remain_usable": True,
        },
        "proposed_catalog": {
            "source": "changes/raos-v2/phase-2/events/event-catalog.v2.yaml",
            "events": deepcopy(events),
            "required_fields": deepcopy(required),
            "optional_fields": deepcopy(optional),
            "forbidden_fields": deepcopy(forbidden),
            "session_rotation_minutes": catalog.get("session_rotation_minutes"),
            "cross_device_identity": False,
            "free_text": False,
            "full_url_or_query": False,
        },
        "review_questions": [
            "Is each proposed event necessary for the stated decision-support metric?",
            "What consent state and disclosure are required before each transmission?",
            "Are retention, access, deletion and processor responsibilities documented?",
            "Does the current privacy/external-transmission notice match the approved implementation?",
            "Can denied or unknown consent use the site and outbound links without nonessential transmission?",
        ],
        "activation_preconditions": [
            "owner or counsel approval recorded outside this generated packet",
            "approved policy wording and consent behavior implemented and tested",
            "first-party endpoint security and retention separately approved",
            "public mobile consent surface passes focus and accessibility review",
        ],
        "approval": "NOT_EXECUTED",
        "activation": "NOT_EXECUTED",
        "external_action_ids": ["EXT-010", "EXT-011"],
        "backlog_id": "B-V2-039",
        "requirement_ids": ["R-V2-029", "R-V2-036"],
        "test_ids": ["T-V2-045", "T-V2-046", "T-V2-051"],
    }


def phase3_rollback_rehearsal_document(
    migration: Mapping[str, object], external_state: Mapping[str, object]
) -> dict[str, object]:
    rollback = migration.get("rollback")
    simulation = rollback.get("simulation") if isinstance(rollback, dict) else None
    if (
        not isinstance(simulation, dict)
        or simulation.get("status") != "PASSED_LOCAL"
        or simulation.get("exact_tuple_restored") is not True
    ):
        fail("RAOS_V2_PHASE3_ROLLBACK_REHEARSAL_INVALID")
    return {
        "schema": "RAOS_V2_PHASE3_ROLLBACK_REHEARSAL_V1",
        "version": "1.0.0",
        "target_route": "/carry-on-suitcase-comparison/",
        "classification": "LOCAL_CONTRACT_SIMULATION_ONLY",
        "route_tuple_simulation": deepcopy(simulation),
        "required_restore_fields": [
            "post_id",
            "post_title",
            "post_name",
            "post_excerpt",
            "post_content",
            "post_status",
            "post_author",
            "published_at",
            "modified_at",
            "taxonomies",
            "comment_status",
            "ping_status",
            "featured_media",
            "yoast_title",
            "yoast_description",
            "yoast_canonical",
            "yoast_robots",
            "theme_version",
            "plugin_versions",
            "redirect_map",
            "sitemap_membership",
        ],
        "complete_export_binding": False,
        "pre_write_export_status": phase3_external_status(
            external_state, "wordpress_export"
        ),
        "post_action_export_status": phase3_external_status(
            external_state, "post_action_wordpress_export"
        ),
        "production_backup": "NOT_EXECUTED",
        "production_restore": "NOT_EXECUTED",
        "public_restore_verification": "NOT_EXECUTED",
        "local_status": "PASSED_LOCAL_CONTRACT_ONLY",
        "phase_exit_evidence": False,
        "failure": "BLOCK_EXTERNAL_MIGRATION_UNTIL_EXACT_EXPORT_EXISTS",
        "backlog_ids": ["B-V2-035", "B-V2-040"],
        "requirement_ids": ["R-V2-025", "R-V2-034", "R-V2-036"],
        "test_ids": ["T-V2-005", "T-V2-040", "T-V2-051"],
    }


def phase3_external_action_template_document(
    external_state: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema": "RAOS_V2_PHASE3_EXTERNAL_ACTION_EVIDENCE_TEMPLATE_V1",
        "version": "1.0.0",
        "classification": "SANITIZED_RECEIPT_TEMPLATE_NO_AUTHORITY",
        "target_origin": external_state.get("target_origin"),
        "target_route": external_state.get("target_route"),
        "current_state_source": PHASE3_EXTERNAL_STATE_PATH.as_posix(),
        "steps": [
            {
                "sequence": 1,
                "action": "PREACTION_PUBLIC_CAPTURE_AND_OWNER_EXPORT",
                "status": "NOT_EXECUTED",
                "required_receipt_schema": "RAOS_V2_PHASE3_PREACTION_BINDING_V1",
                "phase0_baseline_rule": "IMMUTABLE_HISTORICAL_DO_NOT_OVERWRITE",
            },
            {
                "sequence": 2,
                "action": "LOCAL_REISSUE_FROM_VERIFIED_PREACTION",
                "status": "BLOCKED_PENDING_VERIFIED_PREACTION_BINDING",
                "network": False,
                "external_write": False,
            },
            {
                "sequence": 3,
                "action": "OWNER_CONTENT_REVIEW",
                "status": phase3_external_status(external_state, "human_review"),
                "required_receipt_schema": ("RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_V1"),
            },
            {
                "sequence": 4,
                "action": "PRE_WRITE_EXPORT_AND_DISABLED_DRY_RUN",
                "external_action_id": "EXT-001",
                "status": phase3_external_status(external_state, "wordpress_export"),
                "required_receipt_schemas": [
                    "RAOS_V2_WORDPRESS_EXPORT_BINDING_V2",
                    "RAOS_V2_PHASE3_WORDPRESS_DRY_RUN_RECEIPT_V1",
                ],
                "maximum_export_age_seconds": 300,
                "ordering": "AFTER_HUMAN_REVIEW_BEFORE_WORDPRESS_WRITE",
            },
            {
                "sequence": 5,
                "action": "DEPLOY_AND_WORDPRESS_NONPUBLIC_REVIEW_PREVIEW",
                "external_action_ids": ["EXT-004", "EXT-002"],
                "component_statuses": {
                    "theme_or_plugin_deploy": phase3_external_status(
                        external_state, "theme_or_plugin_deploy"
                    ),
                    "wordpress_nonpublic_preview": phase3_external_status(
                        external_state, "wordpress_nonpublic_preview"
                    ),
                },
                "production_plugin_installation": (
                    "INACTIVE_WITH_DEPLOYMENT_DISABLED_BINDING"
                ),
                "production_cutover_order": [
                    "ATOMICALLY_REPLACE_WITH_OWNER_EXPORT_BOUND_BINDING",
                    "ACTIVATE_WHILE_EXACT_LEGACY_DATABASE_BYTES_REMAIN",
                    "WRITE_EXACT_SEALED_DATABASE_BYTES",
                ],
                "production_plugin_activation_gate": (
                    "EXACT_LEGACY_DATABASE_BYTES_AND_VERIFIED_ARMED_BINDING"
                ),
                "intermediate_state_behavior": "BLOCK_TARGET_ROUTE_AND_ROLLBACK",
                "structured_data_gate": {
                    "test_id": "T-V2-036",
                    "status": "NOT_EXECUTED_EXTERNAL_BLOCKER",
                    "expected_types": [
                        "Article",
                        "BreadcrumbList",
                        "Organization",
                        "WebSite",
                    ],
                    "owner": "YOAST_OR_CURRENT_WORDPRESS_METADATA_OWNER",
                    "plugin_generates_json_ld": False,
                },
            },
            {
                "sequence": 6,
                "action": "HUMAN_PUBLICATION",
                "external_action_id": "EXT-003",
                "status": phase3_external_status(external_state, "publication"),
            },
            {
                "sequence": 7,
                "action": "POST_ACTION_OWNER_EXPORT",
                "external_action_id": "V2-P3-EXT-POSTACTION-EXPORT",
                "status": phase3_external_status(
                    external_state, "post_action_wordpress_export"
                ),
                "required_receipt_schema": "RAOS_V2_WORDPRESS_EXPORT_BINDING_V2",
                "ordering": "AFTER_WORDPRESS_WRITE_BEFORE_HTTP_VERIFICATION",
                "required_binding": "SEALED_AFTER_FIELD_HASHES_AND_FINAL_PUBLIC_BODY",
            },
            {
                "sequence": 8,
                "action": "ATOMIC_POST_ACTION_HTTP_AND_EXPORT_VERIFICATION",
                "component_statuses": {
                    "public_capture": phase3_external_status(
                        external_state, "public_verification"
                    ),
                    "post_action_owner_export": phase3_external_status(
                        external_state, "post_action_wordpress_export"
                    ),
                },
                "required_receipt_schema": "RAOS_V2_PUBLIC_VERIFICATION_RECEIPT_V2",
                "required_inputs": [
                    "FRESH_PUBLIC_READ_ONLY_CAPTURE",
                    "SEALED_PHASE3_PACKAGE",
                    "FRESH_POST_ACTION_OWNER_EXPORT_BINDING",
                ],
                "completion_scope": "HTTP_AND_OWNER_EXPORT_ONLY",
                "indexability_evidence": {
                    "scope": "HEAD_META_HTTP_SITEMAP_AND_ROBOTS_TXT",
                    "robots_txt_url": "https://kurashinoshirube.com/robots.txt",
                    "robots_txt_allowed_statuses": [200, 404, 410],
                    "robots_txt_body_storage": "DISCARDED_AFTER_HASH",
                    "target_agent": "Googlebot",
                    "target_path": "/carry-on-suitcase-comparison/",
                    "target_allowed_required": True,
                    "crawler_specific_meta_indexability_safe_required": True,
                    "template_or_noscript_metadata_accepted": False,
                },
                "maximum_age_seconds": 300,
                "pairing": "ATOMIC_PAIRED_CAPTURE_CONTRACT",
            },
            {
                "sequence": 9,
                "action": "PUBLIC_BROWSER_VERIFICATION",
                "status": "RAW_RECORDER_IMPLEMENTED_ACCEPTANCE_VERIFIER_REQUIRED",
                "required_receipt_schema": (
                    "RAOS_V2_PHASE3_PUBLIC_BROWSER_VERIFICATION_RECEIPT_V1"
                ),
                "raw_receipt_schema": ("RAOS_V2_PHASE3_PUBLIC_BROWSER_RAW_RECEIPT_V1"),
                "recorder": "tests/raos_v2/phase3-public-validation.mjs",
                "required_viewport_widths": [390, 768, 1440],
                "boundary": "SEPARATELY_APPROVED_PUBLIC_READ_ONLY_BROWSER",
                "acceptance_authority": False,
                "phase_exit": "BLOCKED_EXTERNAL",
            },
            {
                "sequence": 10,
                "action": "SEVEN_DAY_STABILITY_WINDOW",
                "status": phase3_external_status(external_state, "stability_window"),
                "required_days": 7,
            },
        ],
        "credentials": "MUST_NOT_ENTER_REPOSITORY_OR_RECEIPT",
        "raw_exports": "OWNER_STORAGE_ONLY_NOT_GIT",
        "all_external_actions": "NOT_EXECUTED",
        "phase_exit": "BLOCKED_EXTERNAL",
        "backlog_id": "B-V2-040",
        "test_ids": ["T-V2-005", "T-V2-023", "T-V2-039", "T-V2-040", "T-V2-051"],
    }


def phase3_human_review_request_document(
    *,
    candidate_digest: str,
    payload_digest: str,
    structured_data_expectation_sha256: str,
) -> dict[str, object]:
    return {
        "schema": "RAOS_V2_PHASE3_HUMAN_REVIEW_REQUEST_V1",
        "version": "1.0.0",
        "target_route": "/carry-on-suitcase-comparison/",
        "candidate_digest": candidate_digest,
        "payload_digest": payload_digest,
        "structured_data_expectation_sha256": structured_data_expectation_sha256,
        "state": "AWAITING_VERIFIED_PREACTION_BINDING",
        "preaction_status": "HISTORICAL_BASELINE_ONLY",
        "preaction_binding_digest": None,
        "receipt": None,
        "required_preaction_schema": (
            "contracts/raos-v2/v2/preaction-binding.schema.json"
        ),
        "required_receipt_schema": (
            "contracts/raos-v2/v2/human-review-receipt.schema.json"
        ),
        "checklist": [
            "Create one verified Phase 3 pre-action binding from a bounded public capture and owner-held WordPress export; never overwrite the Phase 0 historical baseline.",
            "Reissue the candidate from that verified binding and review only the reissued candidate and payload digests.",
            "The exact title, excerpt and post-content fragment answer one comparison intent without an unsupported universal winner.",
            "Every A_OFFICIAL_FACT is traceable to a current eligible primary source and every D_EDITORIAL_JUDGEMENT is visibly framed as editorial reasoning.",
            "Every UNKNOWN is visible and nonblocking; no experience, durability, noise or usability claim is implied.",
            "All three product CTA states are BLOCKED and there is no affiliate URL, image, price, stock, point, rate, EPC or business score.",
            "Links are limited to verified public internal policy routes and the three closed ACE official product-source URLs; future carry-on hub, checker and policy routes are absent.",
            "Replacing the current public article without an active affiliate CTA is an intentional owner decision, not an unnoticed regression.",
            "Advertising disclosure, correction path, accessibility and one-H1 ownership are acceptable in the exact WordPress projection.",
            "The exact derived JSON-LD expectation matches the title, description and canonical fields; Yoast or the current metadata owner must be externally verified because the local plugin emits no JSON-LD.",
        ],
        "reviewer_identity_rule": (
            "Use exactly reviewer_id=OWNER_ASSERTION_LOCAL and "
            "review_version=P3-OWNER-ASSERTION-V1; arbitrary identities, names, "
            "emails and credentials are rejected and must never be committed."
        ),
        "failure": "KEEP_EVIDENCE_COMPLETE_AND_DO_NOT_SEAL",
        "candidate_reissue": "BLOCKED_PENDING_VERIFIED_PREACTION_BINDING",
        "human_review": "NOT_EXECUTED",
        "package_seal": "NOT_EXECUTED",
        "external_write": "NOT_EXECUTED",
        "backlog_id": "B-V2-037",
        "requirement_ids": ["R-V2-023", "R-V2-024"],
        "test_ids": ["T-V2-037", "T-V2-038", "T-V2-039"],
    }


def phase3_wordpress_dry_run_status_document(
    *,
    candidate_digest: str,
    payload_digest: str,
    structured_data_expectation_sha256: str,
) -> dict[str, object]:
    return {
        "schema": "RAOS_V2_PHASE3_WORDPRESS_DRY_RUN_STATUS_V1",
        "version": "1.0.0",
        "mode": "DISABLED_DRY_RUN",
        "target": {
            "origin": "https://kurashinoshirube.com",
            "route": "/carry-on-suitcase-comparison/",
            "kind": "EXISTING_POST",
            "expected_match_count": 1,
        },
        "intent": "UPDATE_EXISTING_PUBLISHED_POST_AT_APPROVED_CUTOVER",
        "candidate_digest": candidate_digest,
        "payload_digest": payload_digest,
        "structured_data_expectation_sha256": structured_data_expectation_sha256,
        "preaction_status": "HISTORICAL_BASELINE_ONLY",
        "preaction_binding_digest": None,
        "status": "BLOCKED_EXTERNAL",
        "blockers": [
            "VERIFIED_PREACTION_BINDING_MISSING",
            "CANDIDATE_REISSUE_REQUIRED",
            "NON_SYNTHETIC_HUMAN_REVIEW_RECEIPT_MISSING",
            "FRESH_WORDPRESS_EXPORT_BINDING_MISSING",
        ],
        "future_receipt_schema": (
            "contracts/raos-v2/v2/wordpress-dry-run-receipt.schema.json"
        ),
        "request_count": 0,
        "external_action_count": 0,
        "credential_fields": [],
        "endpoint": None,
        "human_review": "NOT_EXECUTED",
        "wordpress_export_role": "PRE_WRITE_EXPORT",
        "wordpress_export": "NOT_EXECUTED",
        "post_action_wordpress_export": "NOT_APPLICABLE_BEFORE_WRITE",
        "wordpress_write": "NOT_EXECUTED",
        "publication": "NOT_EXECUTED",
        "failure": "CURRENT_PUBLIC_ARTICLE_REMAINS_UNCHANGED",
        "backlog_id": "B-V2-037",
        "test_ids": ["T-V2-037", "T-V2-038", "T-V2-039"],
    }


def phase3_local_wordpress_assembly_document(
    *,
    projection: Mapping[str, object],
    plugin_documents: Mapping[Path, bytes],
) -> bytes:
    """Assemble the exact fragment and plugin CSS in a noindex local WP shell."""

    title = projection.get("post_title")
    post_content = projection.get("post_content")
    css_path = PHASE3_ARTIFACT_ROOT / "assets/decision-support.css"
    css_payload = plugin_documents.get(css_path)
    if (
        not isinstance(title, str)
        or not title.strip()
        or not isinstance(post_content, str)
        or not post_content.strip()
        or not isinstance(css_payload, bytes)
    ):
        fail("RAOS_V2_PHASE3_LOCAL_ASSEMBLY_INPUT_INVALID")
    try:
        plugin_css = css_payload.decode("utf-8")
    except UnicodeError:
        fail("RAOS_V2_PHASE3_LOCAL_ASSEMBLY_INPUT_INVALID")
    shell_css = """
:root { color-scheme: light; font-size: 100%; }
* { box-sizing: border-box; }
html { overflow-x: hidden; }
body { background: #fff; color: #17213a; margin: 0; min-width: 0; }
.raos-v2-phase3-skip { background: #fff; color: #17213a; left: .75rem; padding: .75rem 1rem; position: fixed; top: -10rem; z-index: 10; }
.raos-v2-phase3-skip:focus { outline: 3px solid #005fcc; outline-offset: 3px; top: .75rem; }
.raos-v2-phase3-site-header, .raos-v2-phase3-site-footer { background: #243b6b; color: #fff; padding: 1rem max(1rem, calc((100vw - 74rem) / 2)); }
.raos-v2-phase3-site-header p, .raos-v2-phase3-site-footer p { background-color: #243b6b; color: #fff; margin: 0; }
.raos-v2-phase3-shell { margin-inline: auto; max-width: 74rem; padding: clamp(1rem, 3vw, 2rem); }
.raos-v2-phase3-entry-title { font-size: clamp(1.8rem, 1.45rem + 1.4vw, 3rem); line-height: 1.35; margin-block: 1.5rem 2rem; overflow-wrap: anywhere; }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition-duration: 0.01ms !important; } }
@media (forced-colors: active) { .raos-v2-phase3-site-header, .raos-v2-phase3-site-footer { border-block: 2px solid CanvasText; } }
""".strip()
    document = (
        '<!doctype html><html lang="ja" '
        'data-raos-v2-classification="LOCAL_WORDPRESS_ASSEMBLY_SIMULATION">'
        '<head><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex,nofollow">'
        f"<title>{escape(title)}｜ローカルWordPress組立検証</title>"
        f"<style>{shell_css}\n{plugin_css}</style></head><body>"
        '<a class="raos-v2-phase3-skip" href="#raos-v2-phase3-main">本文へ移動</a>'
        '<header class="raos-v2-phase3-site-header"><p>暮らしのしるべ</p></header>'
        '<main id="raos-v2-phase3-main" class="raos-v2-phase3-shell" tabindex="-1">'
        '<article data-raos-v2-wordpress-route="/carry-on-suitcase-comparison/">'
        f'<h1 class="raos-v2-phase3-entry-title">{escape(title)}</h1>'
        '<div data-raos-v2-post-content-envelope="RAOS_V2_A05_ENVELOPE_V1">'
        f"{post_content}</div></article></main>"
        '<footer class="raos-v2-phase3-site-footer" '
        'aria-label="ローカルWordPress組立検証"></footer></body></html>'
    )
    lowered = document.casefold()
    absolute_hrefs = sorted(
        href
        for href in re.findall(r'href="([^"]+)"', document)
        if href.startswith(("http://", "https://"))
    )
    expected_official_hrefs = sorted(
        [
            "https://store.ace.jp/shop/g/g06316-01/",
            "https://store.ace.jp/shop/g/g05721-04",
            "https://store.ace.jp/shop/g/g01471-02",
        ]
    )
    if (
        document.count("<h1") != 1
        or "noindex,nofollow" not in lowered
        or document.count(
            'data-raos-v2-post-content-envelope="RAOS_V2_A05_ENVELOPE_V1"'
        )
        != 1
        or "<script" in lowered
        or 'src="http' in lowered
        or absolute_hrefs != expected_official_hrefs
        or "affiliate.rakuten" in lowered
        or "hb.afl.rakuten" in lowered
    ):
        fail("RAOS_V2_PHASE3_LOCAL_ASSEMBLY_INVALID")
    return document.encode("utf-8")


def validated_phase3_local_browser_evidence(
    parsed: Mapping[Path, object], local_assembly: bytes
) -> dict[str, object]:
    value = parsed.get(PHASE3_LOCAL_BROWSER_EVIDENCE_PATH)
    if not isinstance(value, dict):
        fail("RAOS_V2_PHASE3_BROWSER_EVIDENCE_INPUT_INVALID")
    try:
        verification = verify_phase3_local_browser_evidence(
            value,
            expected_preview=local_assembly,
            root=ROOT,
        )
    except ValidationFailure:
        fail("RAOS_V2_PHASE3_BROWSER_EVIDENCE_INPUT_INVALID")
    result = deepcopy(value)
    result["verification"] = verification
    return result


def validated_phase3_public_observation(
    parsed: Mapping[Path, object],
) -> dict[str, object]:
    """Bind one sanitized public read without promoting it to preaction evidence."""

    value = parsed.get(PHASE3_PUBLIC_OBSERVATION_PATH)
    if not isinstance(value, dict):
        fail("RAOS_V2_PHASE3_PUBLIC_OBSERVATION_INPUT_INVALID")
    try:
        observation, _captured_at, observed_at = _phase3_capture_observation(
            value, code="RAOS_V2_PHASE3_PUBLIC_OBSERVATION_INPUT_INVALID"
        )
    except ValidationFailure:
        fail("RAOS_V2_PHASE3_PUBLIC_OBSERVATION_INPUT_INVALID")
    if (
        observation.get("status") != 200
        or observation.get("redirect_chain") != []
        or observation.get("canonical")
        != "https://kurashinoshirube.com/carry-on-suitcase-comparison/"
        or observation.get("canonical_tag_count") != 1
        or observation.get("sitemap_membership") is not True
        or observation.get("body_storage") != "DISCARDED_AFTER_HASH"
        or value.get("public_observation_status") != "PUBLIC_READ_ONLY"
        or value.get("external_write_actions") != "NOT_EXECUTED"
    ):
        fail("RAOS_V2_PHASE3_PUBLIC_OBSERVATION_INPUT_INVALID")
    return {
        "classification": "SANITIZED_PUBLIC_READ_ONLY_UNPAIRED",
        "status": "PUBLIC_READ_ONLY",
        "observed_at": observed_at.isoformat(),
        "semantic_sha256": semantic_json_sha256(value),
        "body_sha256": observation.get("body_sha256"),
        "owner_export_pairing": "NOT_EXECUTED",
        "preaction_acceptance_authority": False,
        "external_write": "NOT_EXECUTED",
    }


def phase3_validation_document(
    *,
    projection: Mapping[str, object],
    plugin_documents: Mapping[Path, bytes],
    local_assembly: bytes,
    wordpress_payload: Mapping[str, object],
    review_candidate: Mapping[str, object],
    external_state: Mapping[str, object],
    schemas: Mapping[Path, object],
    browser_evidence: Mapping[str, object],
    public_observation: Mapping[str, object],
    publication_closure_verified: bool,
) -> dict[str, object]:
    post_content = projection.get("post_content")
    target = wordpress_payload.get("target")
    fields = wordpress_payload.get("fields")
    structured_data = wordpress_payload.get("structured_data_expectation")
    expected_schema_names = {
        "human-review-receipt.schema.json",
        "publication-package.schema.json",
        "wordpress-update-payload.schema.json",
        "wordpress-dry-run-receipt.schema.json",
        "wordpress-export-binding.schema.json",
        "preaction-binding.schema.json",
        "public-verification-receipt.schema.json",
        "public-browser-verification-receipt.schema.json",
        "reissued-review-bundle.schema.json",
        "wordpress-cutover-binding.schema.json",
    }
    assembly_text = local_assembly.decode("utf-8")
    browser_verification = browser_evidence.get("verification")
    try:
        plugin_php = plugin_documents[
            PHASE3_ARTIFACT_ROOT / "raos-v2-decision-support.php"
        ].decode("utf-8")
        execution_operator = (ROOT / "scripts/raos_v2_phase3_execution.py").read_text(
            encoding="utf-8"
        )
        public_browser_recorder = (
            ROOT / "tests/raos_v2/phase3-public-validation.mjs"
        ).read_text(encoding="utf-8")
        php_runtime_harness = (
            ROOT / "tests/raos_v2/phase3-wordpress-runtime.php"
        ).read_text(encoding="utf-8")
        required_ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    except KeyError, OSError, UnicodeError:
        fail("RAOS_V2_PHASE3_EXECUTION_TOOLING_MISSING")
    checks = {
        "publication_authority_and_payload_closed": publication_closure_verified,
        "one_existing_route": (
            isinstance(target, dict)
            and target.get("route") == "/carry-on-suitcase-comparison/"
            and target.get("expected_match_count") == 1
        ),
        "wordpress_fragment_not_document": (
            isinstance(post_content, str)
            and re.search(r"<html(?:\s|>)", post_content, re.IGNORECASE) is None
            and re.search(r"<head(?:\s|>)", post_content, re.IGNORECASE) is None
            and re.search(r"<script(?:\s|>)", post_content, re.IGNORECASE) is None
        ),
        "wordpress_owns_single_h1": (
            isinstance(post_content, str) and "<h1" not in post_content.casefold()
        ),
        "future_routes_suppressed": projection.get("linked_internal_routes")
        == ["/about-ad-policy/", "/privacy-policy/"],
        "cta_and_media_fail_closed": (
            projection.get("blocked_cta_count") == 3
            and projection.get("affiliate_url_count") == 0
            and projection.get("image_count") == 0
        ),
        "exact_payload_fields": isinstance(fields, dict) and len(fields) == 9,
        "structured_data_expectation_bound_external_unverified": (
            isinstance(structured_data, dict)
            and review_candidate.get("structured_data_expectation_sha256")
            == structured_data.get("json_ld_sha256")
            and structured_data.get("json_ld_types")
            == ["Article", "BreadcrumbList", "Organization", "WebSite"]
            and structured_data.get("emission")
            == {
                "owner": "EXTERNAL_WORDPRESS_SEO_CONFIGURATION",
                "local_json_ld_emission": False,
                "external_configuration_status": "UNVERIFIED_EXTERNAL",
            }
        ),
        "review_candidate_unsealed": (
            review_candidate.get("schema") == "RAOS_V2_PHASE3_REVIEW_CANDIDATE_V1"
            and review_candidate.get("preaction_status") == "HISTORICAL_BASELINE_ONLY"
            and review_candidate.get("preaction_binding_digest") is None
            and phase3_external_status(external_state, "human_review") == "NOT_EXECUTED"
        ),
        "plugin_artifact_closed": set(plugin_documents)
        == {
            PHASE3_ARTIFACT_ROOT / "raos-v2-decision-support.php",
            PHASE3_ARTIFACT_ROOT / "assets/decision-support.css",
            PHASE3_ARTIFACT_ROOT / "cutover-binding.v1.json",
            PHASE3_ARTIFACT_ROOT / "plugin-manifest.v1.json",
        },
        "plugin_activation_is_fail_closed": (
            "cutover order is binding replacement, activation" in plugin_php
            and 'data-raos-v2-post-content-envelope-status="BLOCKED"' in plugin_php
            and "RAOS_V2_DECISION_SUPPORT_STATE_LEGACY" in plugin_php
            and "return $envelope_open . $post->post_content . '</div>';" in plugin_php
            and "RAOS_V2_DECISION_SUPPORT_VERSION = '0.6.0'" in plugin_php
            and "raos_v2_decision_support_main_content_post" in plugin_php
            and "raos_v2_decision_support_current_content_post" in plugin_php
            and "is_main_query()" in plugin_php
            and "in_the_loop()" in plugin_php
            and "get_the_ID()" in plugin_php
        ),
        "preaction_execution_operator_derives_and_reissues_locally": (
            '"derive-preaction"' in execution_operator
            and '"reissue-candidate"' in execution_operator
            and '"seal-candidate"' in execution_operator
            and '"derive-cutover-binding"' in execution_operator
            and '"--cutover-binding-output"' in execution_operator
            and "build_wordpress_cutover_binding" in execution_operator
            and "UNAUTHENTICATED_OWNER_ASSERTION" in execution_operator
            and '"acceptance_authority": False' in execution_operator
            and '"simulation_only": True' in execution_operator
            and "RAOS_V2_PHASE3_CUTOVER_PREWRITE_EVIDENCE_REQUIRED"
            in execution_operator
            and "verify_phase3_sealed_package_semantics" in execution_operator
            and "READY_FOR_ARTIFACT_SPECIFIC_HUMAN_REVIEW" in execution_operator
            and "_write_new_phase3_capture" in execution_operator
            and '"raw_values_persisted": False' in execution_operator
            and '"network": False' in execution_operator
            and "OWNER_STORAGE_ONLY_NOT_GIT" in execution_operator
        ),
        "php_runtime_stub_is_required_ci": (
            "RAOS_V2_PHASE3_WORDPRESS_RUNTIME_RECEIPT_V1" in php_runtime_harness
            and "PASSED_LOCAL_CI_STUB" in php_runtime_harness
            and 'php -l "$raos_source_plugin"' in required_ci
            and 'php "$raos_harness" source ' in required_ci
            and 'php "$raos_harness" generated ' in required_ci
        ),
        "public_browser_raw_recorder_is_non_authoritative": (
            "RAOS_V2_PHASE3_PUBLIC_BROWSER_RAW_RECEIPT_V1" in public_browser_recorder
            and "OWNER_HELD_RAW_PUBLIC_BROWSER_EVIDENCE" in public_browser_recorder
            and "acceptanceAuthority: false" in public_browser_recorder
            and "phaseExitEligible: false" in public_browser_recorder
            and "const TARGET_ROUTE = '/carry-on-suitcase-comparison/'"
            in public_browser_recorder
            and "BlockedWebSocketStream" in public_browser_recorder
            and "MAX_NETWORK_REQUESTS = 80" in public_browser_recorder
        ),
        "contract_set_complete": {path.name for path in schemas}
        == expected_schema_names,
        "production_sender_off": phase3_external_status(
            external_state, "analytics_activation"
        )
        == "NOT_EXECUTED",
        "external_actions_not_executed": all(
            phase3_external_status(external_state, name) == "NOT_EXECUTED"
            for name in (
                "human_review",
                "wordpress_export",
                "post_action_wordpress_export",
                "wordpress_nonpublic_preview",
                "theme_or_plugin_deploy",
                "publication",
                "privacy_legal_review",
                "analytics_activation",
                "redirect_canonical_sitemap_change",
                "public_verification",
            )
        ),
        "local_wordpress_assembly_fail_closed": (
            "LOCAL_WORDPRESS_ASSEMBLY_SIMULATION" in assembly_text
            and "noindex,nofollow" in assembly_text.casefold()
            and assembly_text.count("<h1") == 1
            and assembly_text.count(
                'data-raos-v2-post-content-envelope="RAOS_V2_A05_ENVELOPE_V1"'
            )
            == 1
            and str(post_content) in assembly_text
            and "<script" not in assembly_text.casefold()
        ),
        "local_browser_a11y_and_visual_evidence": (
            isinstance(browser_verification, dict)
            and browser_verification.get("effective_status")
            == "PASSED_LOCAL_ASSEMBLY_SIMULATION"
            and browser_verification.get("current_tree_binding")
            == "CURRENT_PREVIEW_AND_HARNESS_BOUND"
            and browser_verification.get("manual_visual_review")
            == "PASSED_LOCAL_MANUAL_VISUAL_REVIEW"
            and browser_verification.get("critical_findings") == 0
            and browser_verification.get("major_findings") == 0
            and browser_verification.get("external_actions") == "NOT_EXECUTED"
            and browser_verification.get("public_evidence") == "NOT_CLAIMED"
        ),
        "public_read_only_observation_is_sanitized_and_unpaired": (
            public_observation.get("classification")
            == "SANITIZED_PUBLIC_READ_ONLY_UNPAIRED"
            and public_observation.get("status") == "PUBLIC_READ_ONLY"
            and public_observation.get("owner_export_pairing") == "NOT_EXECUTED"
            and public_observation.get("preaction_acceptance_authority") is False
            and public_observation.get("external_write") == "NOT_EXECUTED"
        ),
    }
    return {
        "schema": "RAOS_V2_PHASE3_VALIDATION_V1",
        "version": "1.0.0",
        "classification": "LOCAL_PREPARATION_ONLY",
        "status": (
            "PASSED_LOCAL_PREPARATION"
            if all(checks.values())
            else "FAILED_LOCAL_PREPARATION"
        ),
        "checks": checks,
        "artifact_sha256": {
            path.as_posix(): sha256(payload)
            for path, payload in sorted(
                plugin_documents.items(), key=lambda item: item[0].as_posix()
            )
        },
        "local_wordpress_assembly": {
            "path": (
                "changes/raos-v2/phase-3/preview/"
                "carry-on-suitcase-comparison/index.html"
            ),
            "classification": "LOCAL_WORDPRESS_ASSEMBLY_SIMULATION",
            "bytes": len(local_assembly),
            "sha256": sha256(local_assembly),
            "plugin_css_sha256": sha256(
                plugin_documents[PHASE3_ARTIFACT_ROOT / "assets/decision-support.css"]
            ),
            "browser_a11y_evidence": {
                "classification": browser_evidence.get("classification"),
                "evidence_basis": "COMMITTED_SANITIZED_LOCAL_RECEIPT",
                "raw_verification": "RECORDED_NOT_REVERIFIED",
                "current_tree_binding": (
                    browser_verification.get("current_tree_binding")
                    if isinstance(browser_verification, dict)
                    else None
                ),
                "manual_visual_review": (
                    browser_verification.get("manual_visual_review")
                    if isinstance(browser_verification, dict)
                    else None
                ),
                "critical_findings": 0,
                "major_findings": 0,
                "formal_ci": "NOT_CLAIMED",
                "public_evidence": "NOT_CLAIMED",
            },
            "production_equivalence": "NOT_CLAIMED",
        },
        "public_observation": dict(public_observation),
        "wordpress_payload_sha256": sha256(canonical_json_bytes(wordpress_payload)),
        "review_candidate_sha256": sha256(canonical_json_bytes(review_candidate)),
        "backlog_status": {
            "B-V2-035": "COMPLETE_LOCAL",
            "B-V2-036": "COMPLETE_LOCAL",
            "B-V2-037": "AWAITING_VERIFIED_PREACTION_BINDING",
            "B-V2-038": "COMPLETE_LOCAL",
            "B-V2-039": "COMPLETE_LOCAL",
            "B-V2-040": "BLOCKED_EXTERNAL",
        },
        "phase_exit": "BLOCKED_EXTERNAL",
        "phase_exit_reasons": [
            "verified create-once pre-action capture/export binding not executed",
            "candidate reissue from current public state not executed",
            "human review and semantic seal not executed",
            "production export/backup not executed",
            "post-action owner export not executed",
            "plugin deploy and WordPress write not executed",
            "PHP lint/runtime harness implemented but required CI and real WordPress integration are not yet evidenced",
            "human publication and public verification not executed",
            "public browser raw recorder implemented but independent acceptance verifier not implemented",
            "exact Yoast/metadata-owner JSON-LD output not externally verified",
            "seven-day stability window not started",
        ],
        "cost_ceiling_hours": 20,
        "external_spend_jpy": 0,
        "external_actions": "NOT_EXECUTED",
        "test_ids": [
            "T-V2-004",
            "T-V2-005",
            "T-V2-008",
            "T-V2-010",
            "T-V2-023",
            *[f"T-V2-{number:03d}" for number in range(35, 47)],
            "T-V2-051",
        ],
    }


def phase3_report_document(validation: Mapping[str, object]) -> str:
    local_test = recorded_local_test_evidence()
    return f"""# RAOS V2 Phase 3 local preparation report

## Outcome

The reversible one-URL WordPress migration package is prepared locally for
`/carry-on-suitcase-comparison/`. The production projection is a post-content
fragment, suppresses unpublished routes, contains no affiliate URL or image and
keeps all three product CTA states blocked. A marker-bound presentation plugin
is packaged without switching the active theme or affecting unrelated pages.
The exact fragment and plugin CSS are also combined in a generator-owned,
`noindex,nofollow` local WordPress assembly simulation; it is not a public page
or proof of production theme/KSES compatibility.

## Earned status

- Local preparation validation: `{validation.get("status")}`
- Recorded local test evidence: `{local_test.get("status")}`; the generator does
  not execute tests or claim required CI
- B-V2-035 backup/export runbook: `COMPLETE_LOCAL`; production export `NOT_EXECUTED`
- B-V2-036 block-presentation plugin: `COMPLETE_LOCAL`; deploy `NOT_EXECUTED`
- Local WordPress assembly: `LOCAL_WORDPRESS_ASSEMBLY_SIMULATION`; browser/a11y
  evidence is recorded separately from generator execution and never promoted
  to production evidence
- PHP lint and minimum WordPress runtime harness: `IMPLEMENTED_REQUIRED_CI`;
  source/generated lint and the fail-closed stub are mandatory in required CI.
  No PHP runtime is available in this local toolchain, so neither has been
  promoted to real WordPress or production evidence
- B-V2-037 exact payload and seal path:
  `AWAITING_VERIFIED_PREACTION_BINDING`; the generated candidate is explicitly
  `HISTORICAL_BASELINE_ONLY` and cannot seal. The create-once, network-free
  `derive-preaction` operator is implemented, but no owner export was supplied.
  One bounded public read was recorded as sanitized, unpaired observation only;
  it has no pre-action acceptance authority. A newly paired capture plus owner
  export must create a Phase 3 binding, then the candidate must be reissued.
  The current unsigned owner assertion can create only a simulation seal with
  no approval authority. A trusted artifact-specific approval source, fresh
  post-approval pre-write export, disabled dry-run and exact field diff are
  `NOT_EXECUTED`; post-action export is a separate later gate
- B-V2-038 route/canonical/sitemap plan: `COMPLETE_LOCAL`; change set empty and
  production mutation `NOT_EXECUTED`
- B-V2-039 privacy/legal packet: `COMPLETE_LOCAL`; sender remains `OFF`, approval
  and activation `NOT_EXECUTED`, metrics `UNAVAILABLE`
- B-V2-040 one-URL migration/public verification: `BLOCKED_EXTERNAL`

## Exit gate

Phase 3 is **not complete**. The public site was observed read-only and remains
the pre-V2 article; no write was made. Backup, owner content review, deployment, WordPress
nonpublic review preview, approved-cutover write, publication, public read-only
verification, rollback evidence and
seven stable days have not occurred. The public site is not changed by this
package. Planning ceiling: 20 hours; actual human time `UNAVAILABLE`; external
spend: JPY 0.

The route-scoped plugin is packaged with a disabled binding. No local command can
create or certify an armed binding: trusted approval and pre-write/dry-run
verifiers are not implemented. A future separately approved cutover would order
  independently verified binding replacement, activation while exact legacy bytes remain,
then the exact sealed write. Legacy bytes retain the existing
filtered output; sealed bytes receive CSS and an envelope around only the raw
reviewed fragment; every intermediate or drifted state is blocked. It does not
generate JSON-LD. Exact
T-V2-036 output from the current Yoast or metadata owner—`Article`,
`BreadcrumbList`, `Organization` and `WebSite` with visible-content parity—is
an unexecuted external blocker. The exact sealed HTML title (without an
unreviewed suffix) and meta description must also each appear once. A public
verifier mismatch is not success; fix
configuration before cutover or roll back an already written change.

The future HTTP verification receipt also requires a fresh post-action owner
export binding every sealed WordPress field and the public body; public capture
alone has no completion authority. Its indexability evidence must cover the
HTML head/meta and HTTP robots state, sitemap membership, and a fixed
same-origin `/robots.txt` response whose body is discarded after hashing. Only
status 200, 404 or 410 is accepted, and the target route must evaluate as
allowed for Googlebot. Crawler-specific robots meta, including `googlebot` and
`googlebot-news`, must be counted and indexability-safe; metadata hidden inside
`template` or `noscript` does not satisfy the head-metadata gate.

The fixed-target public browser raw recorder is implemented, but
`PUBLIC_BROWSER_VERIFICATION` still has no acceptance authority. The current
public page was probed and failed closed because the V2 marker is absent; no raw
receipt or screenshot set was committed. A future post-cutover run plus an
independent acceptance verifier must recompute owner-held raw capture,
screenshots, browser/harness/command, public HTTP and resource-manifest hash
bindings before any receipt can be considered.
"""


def phase3_integration_pr_body_document(
    validation: Mapping[str, object],
) -> str:
    return f"""# RAOS V2 Phase 3 one-URL migration preparation

## Delivered locally

- Package authority: `{PACKAGE_SHA256}`; immutable source package untouched
- Target: existing `/carry-on-suitcase-comparison/` only
- Deterministic WordPress post-content projection and route-scoped presentation plugin
- Noindex local WordPress assembly simulation for the exact fragment and plugin CSS
- Unauthenticated owner-assertion simulation-seal v2 contract and disabled
  hash-only WordPress diff adapter; no approval or cutover authority
- Backup/export runbook, no-change SEO plan, privacy/legal review packet,
  rollback rehearsal and bounded Phase 3 public-capture command
- Local preparation status: `{validation.get("status")}`

## Safety boundary

The real candidate is `HISTORICAL_BASELINE_ONLY`, unreviewed and unsealed. A
create-once local derivation operator now accepts a fresh bounded capture and
owner-held export without persisting raw WordPress values, but those paired
inputs do not yet exist. The candidate must be reissued from their verified
Phase 3 pre-action binding before review. The current unsigned owner assertion
has no approval authority and can produce only a simulation seal. All CTA states are blocked;
no affiliate URL, image, price, stock, rate or business metric was invented.
Unpublished hub/checker/policy routes are not linked. The existing URL,
self-canonical, robots and sitemap membership are planned to remain unchanged;
the redirect change set is empty.

## External/live actions

Production backup/pre-write export, human content approval, plugin deployment, WordPress
nonpublic review preview, approved-cutover write, publication,
post-action owner export,
redirect/canonical/sitemap mutation, analytics/legal
activation, public verification and rollback: `NOT_EXECUTED`. B-V2-040 and the
Phase 3 exit gate remain `BLOCKED_EXTERNAL`; seven stable days are required after
any separately approved publication. A bounded public read-only observation was
recorded but is unpaired and non-authoritative; it changed nothing. The plugin
must remain inactive with its disabled binding: the trusted approval plus fresh
pre-write export/dry-run verifier required to create an armed artifact is not
implemented. It does not generate JSON-LD. PHP lint
and a minimum WordPress runtime stub are now required CI gates, while real
WordPress integration remains an unexecuted deployment prerequisite;
exact T-V2-036 Yoast/metadata-owner output remains an external blocker and a
public verification mismatch requires configuration correction or rollback.
The fixed-target 390/768/1440 public browser raw recorder is implemented, but
its output is non-authoritative and the independent acceptance verifier is still
required before B-V2-040 or Phase 3 can complete.
"""


def phase1_report_document(*, evidence_gate_passed: bool) -> str:
    local_test = recorded_local_test_evidence()
    test_status = local_test.get("status")
    gate = (
        "PASSED_LOCAL_RECORDED"
        if test_status == "PASSED_LOCAL" and evidence_gate_passed
        else "PENDING_LOCAL_TEST_GATE"
    )
    return f"""# RAOS V2 Phase 1 report

The successor product specification fixes one wedge—旅の機内持ち込み条件と荷物選び—
and a locked 25-asset portfolio. The effective machine contract contains seven
templates: HOME, HUB, GUIDE, COMPARISON, DIFFERENCE, TOOL and POLICY.

The route graph, design tokens, component states, ten versioned entity schemas
and disabled-by-default port contracts are deterministic generated outputs. The
existing public comparison route is preserved; every new route remains a local
candidate or `PLANNED_LOCKED`, so Phase 1 changes no public URL.

Source facts, editorial judgement and UNKNOWN are separate. Product/variant facts
are separate from volatile offers. Recommendation inputs cannot include finance.
Real content cannot become human-reviewed or sealed in Phase 0-2; a disabled
WordPress dry-run receipt is not publication evidence.

Validation: T-V2-007..019 and T-V2-051 are `{gate}` (recorded test status:
`{test_status}`); the generator does not execute tests. Publication,
deployment, credentials, spend, live provider writes and production changes are
`NOT_EXECUTED`. Effective planning ceiling: 40 hours; spend ceiling: JPY 0.
"""


def current_phase3_historical_review_candidate_document() -> dict[str, object]:
    """Derive the current historical candidate without browser-evidence input."""

    validate_phase2_source_inputs()
    validate_phase3_browser_bootstrap_inputs()
    capture = _capture_input()
    pages_value = _read_json(
        Path("packages/web-ui/src/decision-support-v2/preview/pages.v2.json")
    )
    if not isinstance(pages_value, dict):
        fail("RAOS_V2_UI_PAGE_SOURCE_INVALID")
    validate_authoritative_ui_parity(pages_value)
    preview = preview_documents()
    migration = migration_manifest_document(capture, preview)
    claim_ledger = claim_ledger_document()
    publication = publication_candidate_document(migration, preview, claim_ledger)
    projection = phase3_wordpress_projection_document(pages_value, publication)
    wordpress_payload, review_candidate, _candidate_digest, _payload_digest = (
        phase3_review_candidate_document(
            publication=publication,
            claim_ledger=claim_ledger,
            projection=projection,
            migration=migration,
        )
    )
    validate_phase3_publication_closure(
        publication=publication,
        claim_ledger=claim_ledger,
        migration=migration,
        wordpress_payload=wordpress_payload,
        review_candidate=review_candidate,
    )
    return review_candidate


def documents() -> dict[Path, bytes]:
    capture = _capture_input()
    phase2_sources = validate_phase2_source_inputs()
    phase3_sources = validate_phase3_source_inputs()
    phase3_state = phase3_external_state()
    product = product_specification()
    routes = route_registry()
    pages_value = _read_json(
        Path("packages/web-ui/src/decision-support-v2/preview/pages.v2.json")
    )
    if not isinstance(pages_value, dict):
        fail("RAOS_V2_UI_PAGE_SOURCE_INVALID")
    validate_authoritative_ui_parity(pages_value)
    validate_cross_ledger_identity(product, routes, pages=pages_value)
    preview = preview_documents()
    sitemap_candidates = sitemap_candidates_document(pages_value, preview)
    migration = migration_manifest_document(capture, preview)
    claim_ledger = claim_ledger_document()
    publication = publication_candidate_document(migration, preview, claim_ledger)
    phase3_projection = phase3_wordpress_projection_document(pages_value, publication)
    (
        phase3_wordpress_payload,
        phase3_review_candidate,
        phase3_candidate_digest,
        phase3_payload_digest,
    ) = phase3_review_candidate_document(
        publication=publication,
        claim_ledger=claim_ledger,
        projection=phase3_projection,
        migration=migration,
    )
    validate_phase3_publication_closure(
        publication=publication,
        claim_ledger=claim_ledger,
        migration=migration,
        wordpress_payload=phase3_wordpress_payload,
        review_candidate=phase3_review_candidate,
    )
    phase3_plugin_documents = phase3_plugin_artifact_documents(
        phase3_sources,
        post_content=str(phase3_projection["post_content"]),
    )
    phase3_local_assembly = phase3_local_wordpress_assembly_document(
        projection=phase3_projection,
        plugin_documents=phase3_plugin_documents,
    )
    phase3_browser_evidence = validated_phase3_local_browser_evidence(
        phase3_sources, phase3_local_assembly
    )
    phase3_public_observation = validated_phase3_public_observation(phase3_sources)
    synthetic_seal = synthetic_seal_receipt_document()
    phase2_validation = phase2_validation_document(
        phase2_sources, preview, publication, migration
    )
    evidence_gate_passed = phase2_validation.get("status") == "PASSED_LOCAL_RECORDED"
    phase2_generated: dict[Path, bytes] = {
        **preview,
        Path("changes/raos-v2/phase-2/claims/claim-ledger.v2.yaml"): yaml_bytes(
            claim_ledger
        ),
        Path(
            "changes/raos-v2/phase-2/generated/migration-manifest.v2.yaml"
        ): yaml_bytes(migration),
        Path(
            "changes/raos-v2/phase-2/generated/publication-candidate.v2.json"
        ): canonical_json_bytes(publication),
        Path(
            "changes/raos-v2/phase-2/generated/synthetic-seal-receipt.v2.json"
        ): canonical_json_bytes(synthetic_seal),
        Path(
            "changes/raos-v2/phase-2/generated/sitemap-candidates.v2.yaml"
        ): yaml_bytes(sitemap_candidates),
        Path(
            "changes/raos-v2/phase-2/generated/phase-2-validation.v2.json"
        ): canonical_json_bytes(phase2_validation),
    }
    local_evidence = local_evidence_bundle_document(
        capture, phase2_generated, phase2_validation
    )
    schema_documents: dict[Path, object] = {
        Path("contracts/raos-v2/v1/source-record.schema.json"): source_record_schema(),
        Path("contracts/raos-v2/v1/claim.schema.json"): claim_schema(),
        Path("contracts/raos-v2/v1/product-model.schema.json"): product_model_schema(),
        Path(
            "contracts/raos-v2/v1/product-variant.schema.json"
        ): product_variant_schema(),
        Path(
            "contracts/raos-v2/v1/offer-observation.schema.json"
        ): offer_observation_schema(),
        Path(
            "contracts/raos-v2/v1/airline-rule-set.schema.json"
        ): airline_rule_set_schema(),
        Path(
            "contracts/raos-v2/v1/article-definition.schema.json"
        ): article_definition_schema(),
        Path(
            "contracts/raos-v2/v1/editorial-decision.schema.json"
        ): editorial_decision_schema(),
        Path(
            "contracts/raos-v2/v1/publication-package.schema.json"
        ): publication_package_schema(),
        Path(
            "contracts/raos-v2/v1/analytics-event.schema.json"
        ): analytics_event_schema(),
    }
    phase3_schema_documents: dict[Path, object] = {
        Path(
            "contracts/raos-v2/v2/human-review-receipt.schema.json"
        ): phase3_human_review_receipt_schema(),
        Path(
            "contracts/raos-v2/v2/publication-package.schema.json"
        ): phase3_publication_package_schema(),
        Path(
            "contracts/raos-v2/v2/wordpress-update-payload.schema.json"
        ): phase3_wordpress_update_payload_schema(),
        Path(
            "contracts/raos-v2/v2/wordpress-dry-run-receipt.schema.json"
        ): phase3_wordpress_dry_run_receipt_schema(),
        Path(
            "contracts/raos-v2/v2/wordpress-export-binding.schema.json"
        ): phase3_wordpress_export_binding_schema(),
        Path(
            "contracts/raos-v2/v2/preaction-binding.schema.json"
        ): phase3_preaction_binding_schema(),
        Path(
            "contracts/raos-v2/v2/public-verification-receipt.schema.json"
        ): phase3_public_verification_receipt_schema(),
        Path(
            "contracts/raos-v2/v2/public-browser-verification-receipt.schema.json"
        ): phase3_public_browser_verification_receipt_schema(),
        Path(
            "contracts/raos-v2/v2/reissued-review-bundle.schema.json"
        ): phase3_reissued_review_bundle_schema(),
        Path(
            "contracts/raos-v2/v2/wordpress-cutover-binding.schema.json"
        ): phase3_wordpress_cutover_binding_schema(),
    }
    phase3_validation = phase3_validation_document(
        projection=phase3_projection,
        plugin_documents=phase3_plugin_documents,
        local_assembly=phase3_local_assembly,
        wordpress_payload=phase3_wordpress_payload,
        review_candidate=phase3_review_candidate,
        external_state=phase3_state,
        schemas=phase3_schema_documents,
        browser_evidence=phase3_browser_evidence,
        public_observation=phase3_public_observation,
        publication_closure_verified=True,
    )
    phase3_generated: dict[Path, bytes] = {
        **phase3_plugin_documents,
        Path(
            "changes/raos-v2/phase-3/production-backup-export-runbook.md"
        ): phase3_backup_runbook_document().encode("utf-8"),
        Path(
            "changes/raos-v2/phase-3/preview/carry-on-suitcase-comparison/index.html"
        ): phase3_local_assembly,
        Path("changes/raos-v2/phase-3/generated/post-content.html"): str(
            phase3_projection["post_content"]
        ).encode("utf-8"),
        Path(
            "changes/raos-v2/phase-3/generated/wordpress-update-candidate.v1.json"
        ): canonical_json_bytes(phase3_wordpress_payload),
        Path(
            "changes/raos-v2/phase-3/generated/review-candidate.v1.json"
        ): canonical_json_bytes(phase3_review_candidate),
        Path(
            "changes/raos-v2/phase-3/generated/human-review-request.v1.json"
        ): canonical_json_bytes(
            phase3_human_review_request_document(
                candidate_digest=phase3_candidate_digest,
                payload_digest=phase3_payload_digest,
                structured_data_expectation_sha256=str(
                    phase3_review_candidate["structured_data_expectation_sha256"]
                ),
            )
        ),
        Path(
            "changes/raos-v2/phase-3/generated/wordpress-dry-run-status.v1.json"
        ): canonical_json_bytes(
            phase3_wordpress_dry_run_status_document(
                candidate_digest=phase3_candidate_digest,
                payload_digest=phase3_payload_digest,
                structured_data_expectation_sha256=str(
                    phase3_review_candidate["structured_data_expectation_sha256"]
                ),
            )
        ),
        Path(
            "changes/raos-v2/phase-3/generated/seo-url-change-plan.v1.yaml"
        ): yaml_bytes(
            phase3_seo_change_plan_document(
                structured_data_expectation_sha256=str(
                    phase3_review_candidate["structured_data_expectation_sha256"]
                )
            )
        ),
        Path(
            "changes/raos-v2/phase-3/generated/privacy-legal-review-packet.v1.yaml"
        ): yaml_bytes(phase3_privacy_review_packet_document()),
        Path(
            "changes/raos-v2/phase-3/generated/rollback-rehearsal.v1.json"
        ): canonical_json_bytes(
            phase3_rollback_rehearsal_document(migration, phase3_state)
        ),
        Path(
            "changes/raos-v2/phase-3/generated/"
            "external-action-evidence-template.v1.yaml"
        ): yaml_bytes(phase3_external_action_template_document(phase3_state)),
        Path(
            "changes/raos-v2/phase-3/generated/phase-3-validation.v1.json"
        ): canonical_json_bytes(phase3_validation),
        Path(
            "changes/raos-v2/phase-3/phase-3-preparation-report.md"
        ): phase3_report_document(phase3_validation).encode("utf-8"),
        Path(
            "changes/raos-v2/phase-3/integration-pr-body.md"
        ): phase3_integration_pr_body_document(phase3_validation).encode("utf-8"),
    }
    result: dict[Path, bytes] = {
        Path("changes/raos-v2/source-import.v1.json"): canonical_json_bytes(
            source_import_document(capture)
        ),
        Path("changes/raos-v2/clarifications.v1.yaml"): yaml_bytes(
            clarifications_document()
        ),
        Path("changes/raos-v2/phase-0/preflight-report.json"): canonical_json_bytes(
            preflight_document(capture)
        ),
        Path("changes/raos-v2/phase-0/source-audit-report.json"): canonical_json_bytes(
            source_audit_document()
        ),
        Path("changes/raos-v2/phase-0/public-url-inventory.yaml"): yaml_bytes(
            public_url_inventory(capture)
        ),
        Path(
            "changes/raos-v2/phase-0/production-observation-plan.md"
        ): OBSERVATION_PLAN.encode("utf-8"),
        Path("changes/raos-v2/phase-0/metric-dictionary.yaml"): yaml_bytes(
            metric_dictionary()
        ),
        Path("changes/raos-v2/phase-0/deprecation-ledger.yaml"): yaml_bytes(
            deprecation_ledger()
        ),
        Path("changes/raos-v2/phase-0/pilot-reconciliation.yaml"): yaml_bytes(
            pilot_reconciliation(capture)
        ),
        Path("changes/raos-v2/phase-0/rollback-contract.yaml"): yaml_bytes(
            rollback_contract()
        ),
        # B-V2-009 intentionally follows every B-V2-001..008 output above.
        Path("changes/raos-v2/phase-0/phase-0-report.md"): PHASE0_REPORT.encode(
            "utf-8"
        ),
        Path("changes/raos-v2/product-spec.v2.yaml"): yaml_bytes(product),
        Path("changes/raos-v2/route-registry.v2.yaml"): yaml_bytes(routes),
        Path("changes/raos-v2/design/design-tokens.v2.json"): canonical_json_bytes(
            design_tokens()
        ),
        Path("changes/raos-v2/design/component-states.yaml"): yaml_bytes(
            component_states()
        ),
        Path(
            "changes/raos-v2/generated/decision-traceability.effective.v1.yaml"
        ): yaml_bytes(
            effective_traceability(evidence_gate_passed=evidence_gate_passed)
        ),
        Path(
            "changes/raos-v2/generated/phase-1-validation.v1.json"
        ): canonical_json_bytes(
            phase1_validation_document(product, routes, schema_documents)
        ),
        Path("changes/raos-v2/phase-1-report.md"): phase1_report_document(
            evidence_gate_passed=evidence_gate_passed
        ).encode("utf-8"),
        Path("contracts/raos-v2/v1/ports.v1.yaml"): yaml_bytes(ports_contract()),
        Path(
            "changes/raos-v2/phase-2/generated/local-evidence-bundle.v2.json"
        ): canonical_json_bytes(local_evidence),
        Path("changes/raos-v2/phase-2/phase-2-report.md"): phase2_report_document(
            capture, local_evidence
        ).encode("utf-8"),
        Path(
            "changes/raos-v2/phase-2/integration-pr-body.md"
        ): integration_pr_body_document(local_evidence).encode("utf-8"),
    }
    result.update(
        {
            path: canonical_json_bytes(document)
            for path, document in schema_documents.items()
        }
    )
    result.update(
        {
            path: canonical_json_bytes(document)
            for path, document in phase3_schema_documents.items()
        }
    )
    result.update(phase2_generated)
    result.update(phase3_generated)
    if set(result) != set(OUTPUT_PATHS):
        fail("RAOS_V2_OUTPUT_INVENTORY_MISMATCH")
    return result


def write_generated_output(relative: Path, payload: bytes) -> None:
    """Write an allowlisted output without following target or ancestor links."""

    if (
        relative not in OUTPUT_PATHS
        or relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        fail("RAOS_V2_OUTPUT_PATH_NOT_ALLOWLISTED")
    repository = ROOT.resolve()
    current = ROOT
    for part in relative.parts[:-1]:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            fail("RAOS_V2_OUTPUT_ANCESTOR_INVALID")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            fail("RAOS_V2_OUTPUT_ANCESTOR_INVALID")
    target = ROOT / relative
    try:
        metadata = target.lstat()
    except FileNotFoundError:
        metadata = None
    except OSError:
        fail("RAOS_V2_OUTPUT_TARGET_INVALID")
    if metadata is not None and (
        stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode)
    ):
        fail("RAOS_V2_OUTPUT_TARGET_INVALID")
    resolved_parent = target.parent.resolve()
    if resolved_parent != repository and repository not in resolved_parent.parents:
        fail("RAOS_V2_OUTPUT_PATH_ESCAPE")
    atomic_write(relative, payload, root=ROOT)


def generate(*, check: bool) -> None:
    expected = documents()
    drift: list[str] = []
    for path in OUTPUT_PATHS:
        payload = expected[path]
        target = ROOT / path
        if check:
            try:
                actual = target.read_bytes()
            except OSError:
                drift.append(path.as_posix())
                continue
            if actual != payload:
                drift.append(path.as_posix())
        else:
            write_generated_output(path, payload)
    if drift:
        print("RAOS_V2_SUCCESSOR_DRIFT " + " ".join(drift), file=sys.stderr)
        raise SystemExit(1)


def generate_preview_only() -> None:
    """Refresh unverified local preview bytes before browser evidence capture."""

    validate_phase2_source_inputs()
    preview = preview_documents()
    expected_preview_paths = {
        path for path in OUTPUT_PATHS if "phase-2/preview" in path.as_posix()
    }
    if set(preview) != expected_preview_paths:
        fail("RAOS_V2_PREVIEW_OUTPUT_INVENTORY_MISMATCH")
    for path, payload in preview.items():
        write_generated_output(path, payload)


def phase3_browser_bootstrap_documents() -> dict[Path, bytes]:
    """Build only unverified Phase 3 browser inputs before evidence capture.

    This deliberately does not read or validate the existing Phase 3 browser
    receipt. It remains offline and cannot construct a reviewed/sealed package
    or a WordPress request.
    """

    capture = _capture_input()
    validate_phase2_source_inputs()
    phase3_sources = validate_phase3_browser_bootstrap_inputs()
    pages_value = _read_json(
        Path("packages/web-ui/src/decision-support-v2/preview/pages.v2.json")
    )
    if not isinstance(pages_value, dict):
        fail("RAOS_V2_UI_PAGE_SOURCE_INVALID")
    phase2_preview = preview_documents()
    migration = migration_manifest_document(capture, phase2_preview)
    claim_ledger = claim_ledger_document()
    publication = publication_candidate_document(
        migration, phase2_preview, claim_ledger
    )
    projection = phase3_wordpress_projection_document(pages_value, publication)
    plugin_documents = phase3_plugin_artifact_documents(
        phase3_sources,
        post_content=str(projection["post_content"]),
    )
    local_assembly = phase3_local_wordpress_assembly_document(
        projection=projection,
        plugin_documents=plugin_documents,
    )
    result = {
        **plugin_documents,
        Path("changes/raos-v2/phase-3/generated/post-content.html"): str(
            projection["post_content"]
        ).encode("utf-8"),
        Path(
            "changes/raos-v2/phase-3/preview/carry-on-suitcase-comparison/index.html"
        ): local_assembly,
    }
    if set(result) != set(PHASE3_BROWSER_BOOTSTRAP_OUTPUT_PATHS):
        fail("RAOS_V2_PHASE3_BOOTSTRAP_OUTPUT_INVENTORY_MISMATCH")
    return result


def generate_phase3_browser_bootstrap() -> None:
    """Refresh local Phase 3 preview bytes without claiming test evidence."""

    for path, payload in phase3_browser_bootstrap_documents().items():
        write_generated_output(path, payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="refresh deterministic unverified preview before a browser evidence run",
    )
    parser.add_argument(
        "--phase3-preview-only",
        action="store_true",
        help=(
            "refresh the unverified Phase 3 WordPress assembly before a browser "
            "evidence run"
        ),
    )
    arguments = parser.parse_args(argv)
    selected_modes = sum(
        bool(value)
        for value in (
            arguments.check,
            arguments.preview_only,
            arguments.phase3_preview_only,
        )
    )
    if selected_modes > 1:
        parser.error(
            "--check, --preview-only and --phase3-preview-only are mutually exclusive"
        )
    try:
        if arguments.phase3_preview_only:
            generate_phase3_browser_bootstrap()
        elif arguments.preview_only:
            generate_preview_only()
        else:
            generate(check=arguments.check)
    except BuildFailure as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        (
            "RAOS_V2_SUCCESSOR_CHECK_OK"
            if arguments.check
            else (
                "RAOS_V2_PHASE3_PREVIEW_REFRESHED_UNVERIFIED"
                if arguments.phase3_preview_only
                else (
                    "RAOS_V2_PREVIEW_REFRESHED_UNVERIFIED"
                    if arguments.preview_only
                    else "RAOS_V2_SUCCESSOR_GENERATED"
                )
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
