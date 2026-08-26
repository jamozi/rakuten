#!/usr/bin/env python3
"""Build content-addressed, disabled ST-0806 V2 recorded artifacts."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import stat
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Callable, Final, NoReturn, Protocol, cast

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, Node
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.adapters.recorded_ai_draft_integration_v2 import (  # noqa: E402
    load_recorded_ai_draft_fixture_v2,
)
from raos.adapters.recorded_claim_evidence import (  # noqa: E402
    load_recorded_claim_evidence_fixture,
)
from raos.domain.editorial.ai_draft_integration_v2 import (  # noqa: E402
    FIXTURE_DOCUMENT_ID,
    FIXTURE_SCHEMA_VERSION,
    POLICY_SHA256,
)
from raos.domain.editorial.content_ast import (  # noqa: E402
    dump_content_ast_json,
    load_content_ast,
)
from raos.domain.evidence.claim_evidence import (  # noqa: E402
    CoverageStatus,
    complete_claim_set_sha256,
    evaluate_claim_evidence,
    recorded_synthetic_attestation_decision_sha256,
    required_validation_attestation_inputs,
    validation_attestation_owner_binding,
)


CONTRACT_PATH: Final = Path("changes/st-0806/contracts/ai-draft-integration.v2.yaml")
PLAN_PATH: Final = Path("changes/st-0806/generated/ai-draft-integration.v2.json")
FIXTURE_PATH: Final = Path(
    "changes/st-0806/generated/ai-draft-integration-fixture.v2.json"
)
MANIFEST_PATH: Final = Path("changes/st-0806/manifest.v2.yaml")
GENERATED_PATHS: Final = (PLAN_PATH, FIXTURE_PATH, MANIFEST_PATH)
EXPECTED_CONTRACT_SHA256: Final = (
    "42715fc526bcb4eddccbd836084769f7ef8886b7767ad806f33accdff4843bdd"
)
EXPECTED_POLICY_SHA256: Final = (
    "443b5ea91544ea1e8d5f9c7c2e71ebe331fda6f81397f0b51e25aa70da5c77f2"
)
HARDENED_WRITER_PATH: Final = Path("scripts/secure_generated_publication.py")
HARDENED_WRITER_SHA256: Final = (
    "38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e"
)
CONTENT_FIXTURE_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/content/fixtures/valid/selection_guide.json"
)
EVIDENCE_FIXTURE_PATH: Final = Path(
    "changes/st-0605/generated/claim-evidence-runtime-pass.v1.json"
)
GENERATION_COMMAND: Final = "python scripts/build_st0806_ai_draft_integration_v2.py"
CHECK_COMMAND: Final = f"{GENERATION_COMMAND} --check"
ARTICLE_ID: Final = "018f3e90-7b00-7000-8000-000000000806"
ARTICLE_VERSION_ID: Final = "018f3e90-7b00-7000-8000-000000000807"
SOURCE_PACKET_VERSION_ID: Final = "018f3e90-7b00-7000-8000-000000000808"
TITLE: Final = "Synthetic AI draft integration article V2"
CLAIM_IDS: Final = (
    "44444444-4444-4444-8444-444444444444",
    "55555555-5555-4555-8555-555555555555",
)
SHA256_PATTERN: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
MAXIMUM_CONTRACT_BYTES: Final = 262_144

SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    Path("changes/st-0806/README.md"),
    Path("changes/st-0806/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v2.yaml"),
    Path("docs/execplans/ST-0806.md"),
    Path("docs/worklogs/ST-0806.md"),
    Path("scripts/build_st0806_ai_draft_integration_v2.py"),
    HARDENED_WRITER_PATH,
    CONTENT_FIXTURE_PATH,
    EVIDENCE_FIXTURE_PATH,
    Path("python/raos/domain/editorial/ai_draft_integration.py"),
    Path("python/raos/ports/ai_draft_integration.py"),
    Path("python/raos/application/editorial/ai_draft_integration.py"),
    Path("python/raos/adapters/recorded_ai_draft_integration.py"),
    Path("python/raos/domain/editorial/ai_draft_integration_v2.py"),
    Path("python/raos/ports/ai_draft_integration_v2.py"),
    Path("python/raos/application/editorial/ai_draft_integration_v2.py"),
    Path("python/raos/adapters/recorded_ai_draft_integration_v2.py"),
    Path("tests/st0806/v2_support.py"),
    Path("tests/st0806/test_ai_draft_integration_v2.py"),
    Path("tests/st0806/test_ai_draft_integration_v2_negative.py"),
    Path("tests/st0806/test_ai_draft_integration_v2_boundaries.py"),
    Path("tests/st0806/test_ai_draft_integration_v2_generation.py"),
)


class AiDraftBuildError(RuntimeError):
    __slots__ = ("code", "field")

    def __init__(self, code: str, field: str) -> None:
        super().__init__(code)
        self.code = code
        self.field = field


def _fail(code: str, field: str) -> NoReturn:
    raise AiDraftBuildError(code, field) from None


class _UniqueLoader(yaml.SafeLoader):
    pass


class _YamlConstructor(Protocol):
    def construct_object(self, node: Node, deep: bool = False) -> object: ...


def _construct_mapping(
    loader: _UniqueLoader, node: MappingNode, deep: bool = False
) -> dict[object, object]:
    result: dict[object, object] = {}
    pairs = cast(list[tuple[Node, Node]], node.value)
    constructor = cast(_YamlConstructor, loader)
    for key_node, value_node in pairs:
        key = constructor.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "unhashable key",
                key_node.start_mark,
            ) from None
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "duplicate key",
                key_node.start_mark,
            ) from None
        result[key] = constructor.construct_object(value_node, deep=deep)
    return result


_UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read(root: Path, relative: Path, field: str) -> bytes:
    if relative.is_absolute() or ".." in relative.parts:
        _fail("UNSAFE_PATH", field)
    path = root / relative
    try:
        metadata = path.lstat()
        value = path.read_bytes()
    except OSError:
        _fail("SOURCE_UNAVAILABLE", field)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _fail("SOURCE_NOT_REGULAR", field)
    return value


def _mapping(value: object, code: str, field: str) -> dict[str, object]:
    if type(value) is not dict:
        _fail(code, field)
    return cast(dict[str, object], value)


def _list(value: object, code: str, field: str) -> list[object]:
    if type(value) is not list:
        _fail(code, field)
    return cast(list[object], value)


def _load_contract(root: Path) -> dict[str, object]:
    raw = _read(root, CONTRACT_PATH, "contract")
    if (
        not raw
        or len(raw) > MAXIMUM_CONTRACT_BYTES
    ):
        _fail("CONTRACT_PARSE_FAILED", "contract")
    try:
        text = raw.decode("utf-8", errors="strict")
        scan_value = cast(object, getattr(yaml, "scan"))
        if not callable(scan_value):
            _fail("CONTRACT_PARSE_FAILED", "contract")
        scan = cast(Callable[[str], Iterable[object]], scan_value)
        if any(
            isinstance(token, (AliasToken, AnchorToken, TagToken))
            for token in scan(text)
        ):
            _fail("CONTRACT_YAML_FEATURE_FORBIDDEN", "contract")
        loaded: object = yaml.load(text, Loader=_UniqueLoader)
    except AiDraftBuildError:
        raise
    except Exception:
        _fail("CONTRACT_PARSE_FAILED", "contract")
    expected_keys = {
        "document",
        "authority",
        "source_bindings",
        "recorded_policy",
        "durable_receipt_consumer",
        "draft_proposal",
        "prohibited_inputs",
        "security_controls",
        "safe_defaults",
        "verification_boundary",
    }
    if type(loaded) is not dict:
        _fail("CONTRACT_SHAPE_INVALID", "contract")
    contract = cast(dict[str, object], loaded)
    if set(contract) != expected_keys:
        _fail("CONTRACT_SHAPE_INVALID", "contract")
    document_value = contract["document"]
    if type(document_value) is not dict:
        _fail("CONTRACT_DOCUMENT_INVALID", "document")
    document = cast(dict[str, object], document_value)
    if (
        document.get("id") != "RAOS-ST0806-AI-DRAFT-INTEGRATION-002"
        or document.get("story_id") != "ST-0806"
        or document.get("status") != "LOCAL_IMPLEMENTATION_COMPLETE"
        or document.get("enabled_by_default") is not False
        or document.get("authority") != "NONE"
        or document.get("production_eligible") is not False
        or document.get("publication_authorized") is not False
    ):
        _fail("CONTRACT_DOCUMENT_INVALID", "document")
    policy_value = contract["recorded_policy"]
    if type(policy_value) is not dict:
        _fail("CONTRACT_POLICY_INVALID", "recorded_policy")
    policy = cast(dict[str, object], policy_value)
    policy_material = dict(policy)
    observed_policy_sha = policy_material.pop("policy_sha256", None)
    canonical_policy = json.dumps(
        policy_material,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8", errors="strict")
    if (
        observed_policy_sha != EXPECTED_POLICY_SHA256
        or _sha256(canonical_policy) != EXPECTED_POLICY_SHA256
        or POLICY_SHA256 != EXPECTED_POLICY_SHA256
    ):
        _fail("CONTRACT_POLICY_INVALID", "recorded_policy")
    consumer_value = contract["durable_receipt_consumer"]
    if type(consumer_value) is not dict:
        _fail("DURABLE_BOUNDARY_INVALID", "durable_receipt_consumer")
    consumer = cast(dict[str, object], consumer_value)
    if (
        consumer.get("owns_queue_state_or_cas") is not False
        or consumer.get("owns_worker_dispatch_or_redrive") is not False
    ):
        _fail("DURABLE_BOUNDARY_INVALID", "durable_receipt_consumer")
    defaults_value = contract["safe_defaults"]
    if type(defaults_value) is not dict:
        _fail("SAFE_DEFAULT_INVALID", "safe_defaults")
    defaults = cast(dict[str, object], defaults_value)
    if defaults.get("activation") != "DISABLED":
        _fail("SAFE_DEFAULT_INVALID", "safe_defaults")
    bindings_value = contract["source_bindings"]
    if type(bindings_value) is not list:
        _fail("SOURCE_BINDING_INVALID", "source_bindings")
    bindings = cast(list[object], bindings_value)
    if not bindings:
        _fail("SOURCE_BINDING_INVALID", "source_bindings")
    seen: set[str] = set()
    for index, row_value in enumerate(bindings):
        if type(row_value) is not dict:
            _fail("SOURCE_BINDING_INVALID", f"source_bindings[{index}]")
        row = cast(dict[str, object], row_value)
        if set(row) != {"path", "sha256", "owner", "role"}:
            _fail("SOURCE_BINDING_INVALID", f"source_bindings[{index}]")
        path = row["path"]
        digest = row["sha256"]
        if (
            type(path) is not str
            or path in seen
            or type(digest) is not str
            or SHA256_PATTERN.fullmatch(digest) is None
            or (
                path.startswith(("docs/canonical/", "docs/upstream/", "contracts/"))
                and _sha256(_read(root, Path(path), "source_binding")) != digest
            )
        ):
            _fail("SOURCE_BINDING_DRIFT", f"source_bindings[{index}]")
        seen.add(path)
    return contract


def _after_ast_bytes(root: Path) -> bytes:
    try:
        loaded: object = json.loads(
            _read(root, CONTENT_FIXTURE_PATH, "content_fixture")
        )
        payload = _mapping(loaded, "CONTENT_FIXTURE_INVALID", "content_fixture")
        payload["article_id"] = ARTICLE_ID
        payload["article_version_id"] = ARTICLE_VERSION_ID
        payload["source_packet_version_ref"] = SOURCE_PACKET_VERSION_ID
        payload["title"] = TITLE
        blocks = _list(payload["blocks"], "CONTENT_FIXTURE_INVALID", "content_fixture")
        lead = _mapping(blocks[1], "CONTENT_FIXTURE_INVALID", "content_fixture")
        content = _list(
            lead.get("content"), "CONTENT_FIXTURE_INVALID", "content_fixture"
        )
        first_text = _mapping(content[0], "CONTENT_FIXTURE_INVALID", "content_fixture")
        first_text["text"] = (
            "この合成V2候補は、人間が編集する提案であり自動適用されません。"
        )
        claim_index = 0
        stack: list[object] = [payload]
        while stack:
            current = stack.pop()
            if type(current) is dict:
                mapping = cast(dict[str, object], current)
                for key, child in mapping.items():
                    if key in {"claim_ids", "rationale_claim_ids"}:
                        if type(child) is not list:
                            _fail("CONTENT_FIXTURE_INVALID", "claim_ids")
                        claim_values = cast(list[object], child)
                        if not claim_values:
                            _fail("CONTENT_FIXTURE_INVALID", "claim_ids")
                        replacement: list[str] = []
                        for _value in claim_values:
                            replacement.append(CLAIM_IDS[claim_index % len(CLAIM_IDS)])
                            claim_index += 1
                        mapping[key] = replacement
                    else:
                        stack.append(child)
            elif type(current) is list:
                stack.extend(cast(list[object], current))
        if claim_index == 0:
            _fail("CONTENT_FIXTURE_INVALID", "claim_ids")
        ast = load_content_ast(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )
        return dump_content_ast_json(ast).encode("utf-8", errors="strict")
    except AiDraftBuildError:
        raise
    except Exception:
        _fail("CONTENT_FIXTURE_INVALID", "content_fixture")


def _evidence_snapshot_bytes(root: Path, *, after_sha256: str) -> bytes:
    try:
        loaded: object = json.loads(
            _read(root, EVIDENCE_FIXTURE_PATH, "evidence_fixture")
        )
        fixture = _mapping(loaded, "EVIDENCE_FIXTURE_INVALID", "evidence_fixture")
        article = _mapping(
            fixture["article"], "EVIDENCE_FIXTURE_INVALID", "evidence_fixture"
        )
        packet = _mapping(
            fixture["approved_packet"],
            "EVIDENCE_FIXTURE_INVALID",
            "evidence_fixture",
        )
        claims = _list(
            fixture["claims"], "EVIDENCE_FIXTURE_INVALID", "evidence_fixture"
        )
        article["article_version_id"] = ARTICLE_VERSION_ID
        article["article_body_sha256"] = after_sha256
        article["source_packet_version_id"] = SOURCE_PACKET_VERSION_ID
        packet["source_packet_version_id"] = SOURCE_PACKET_VERSION_ID
        for claim_value in claims:
            claim = _mapping(claim_value, "EVIDENCE_FIXTURE_INVALID", "claims")
            claim["article_version_id"] = ARTICLE_VERSION_ID
        article["complete_claim_set_sha256"] = "0" * 64
        provisional = json.dumps(
            fixture, ensure_ascii=True, separators=(",", ":")
        ).encode("ascii")
        snapshot = load_recorded_claim_evidence_fixture(provisional)
        article["complete_claim_set_sha256"] = complete_claim_set_sha256(
            snapshot.claims
        ).value
        fixture["attestations"] = []
        no_attestations = load_recorded_claim_evidence_fixture(
            json.dumps(fixture, ensure_ascii=True, separators=(",", ":")).encode(
                "ascii"
            )
        )
        attestations: list[dict[str, object]] = []
        for kind, subject, input_digest in required_validation_attestation_inputs(
            no_attestations
        ):
            owner, version, contract_digest = validation_attestation_owner_binding(kind)
            attestations.append(
                {
                    "kind": kind.value,
                    "owner_story_id": owner,
                    "contract_version": version,
                    "contract_sha256": contract_digest.value,
                    "origin": "RECORDED_SYNTHETIC_ONLY",
                    "subject_sha256": subject.value,
                    "input_sha256": input_digest.value,
                    "decision_sha256": recorded_synthetic_attestation_decision_sha256(
                        kind, subject, input_digest
                    ).value,
                    "validated_at": "2026-08-23T23:00:00Z",
                    "valid": True,
                }
            )
        fixture["attestations"] = attestations
        payload = (
            json.dumps(
                fixture,
                ensure_ascii=True,
                indent=2,
                separators=(",", ": "),
            )
            + "\n"
        ).encode("ascii")
        verified = load_recorded_claim_evidence_fixture(payload)
        report = evaluate_claim_evidence(verified)
        if report.status is not CoverageStatus.PASS or report.findings:
            _fail("EVIDENCE_FIXTURE_NOT_PASSING", "evidence_fixture")
        return payload
    except AiDraftBuildError:
        raise
    except Exception:
        _fail("EVIDENCE_FIXTURE_INVALID", "evidence_fixture")


def _fixture_bytes(root: Path) -> bytes:
    after = _after_ast_bytes(root)
    snapshot_bytes = _evidence_snapshot_bytes(root, after_sha256=_sha256(after))
    snapshot = load_recorded_claim_evidence_fixture(snapshot_bytes)
    report = evaluate_claim_evidence(snapshot)
    report.require_valid()
    report_bytes = report.canonical_bytes()
    value = {
        "after_content_ast_sha256": _sha256(after),
        "after_content_ast_utf8": after.decode("utf-8", errors="strict"),
        "claim_evidence_snapshot_sha256": _sha256(snapshot_bytes),
        "claim_evidence_snapshot_utf8": snapshot_bytes.decode("utf-8", errors="strict"),
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
        "coverage_receipt": {
            "publication_authorized": False,
            "report_sha256": report.report_sha256.value,
            "sequence": 1,
        },
        "coverage_report_sha256": _sha256(report_bytes),
        "coverage_report_utf8": report_bytes.decode("utf-8", errors="strict"),
        "document_id": FIXTURE_DOCUMENT_ID,
        "policy_sha256": EXPECTED_POLICY_SHA256,
        "schema_version": FIXTURE_SCHEMA_VERSION,
    }
    payload = (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8", errors="strict")
    load_recorded_ai_draft_fixture_v2(payload)
    return payload


def _source_hashes(root: Path) -> dict[str, str]:
    if len(SOURCE_ARTIFACT_PATHS) != len(set(SOURCE_ARTIFACT_PATHS)):
        _fail("SOURCE_INVENTORY_DUPLICATE", "source_artifacts")
    return {
        path.as_posix(): _sha256(_read(root, path, "source_artifacts"))
        for path in SOURCE_ARTIFACT_PATHS
    }


def _plan_bytes(
    contract: Mapping[str, object], source_hashes: Mapping[str, str], fixture: bytes
) -> bytes:
    value = {
        "authority": "NONE",
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
        "document_id": "RAOS-ST0806-AI-DRAFT-INTEGRATION-PLAN-002",
        "enabled": False,
        "formal_and_external": contract["verification_boundary"],
        "generated_fixture_sha256": _sha256(fixture),
        "owner_source_sha256": dict(source_hashes),
        "policy_sha256": EXPECTED_POLICY_SHA256,
        "proposal_boundary": contract["draft_proposal"],
        "safe_defaults": contract["safe_defaults"],
        "source_bindings": contract["source_bindings"],
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "story_id": "ST-0806",
        "version": "2.0.0",
    }
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8", errors="strict")


def _manifest_bytes(
    source_hashes: Mapping[str, str], plan: bytes, fixture: bytes
) -> bytes:
    value = {
        "document": {
            "id": "RAOS-ST0806-AI-DRAFT-INTEGRATION-MANIFEST-002",
            "version": "2.0.0",
            "story_id": "ST-0806",
            "status": "LOCAL_IMPLEMENTATION_COMPLETE",
            "authority": "NONE",
            "production_eligible": False,
        },
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
        "policy_sha256": EXPECTED_POLICY_SHA256,
        "hardened_writer_sha256": HARDENED_WRITER_SHA256,
        "source_sha256": dict(source_hashes),
        "generated_sha256": {
            PLAN_PATH.as_posix(): _sha256(plan),
            FIXTURE_PATH.as_posix(): _sha256(fixture),
        },
        "generation": {"command": GENERATION_COMMAND, "check_command": CHECK_COMMAND},
        "bounds": {
            "activation": "DISABLED",
            "adapter": "RECORDED_SYNTHETIC_CALLER_BYTES_ONLY",
            "durable_state_owner": "ST-0706",
            "generic_runtime_owner": "ST-1404",
            "provider": False,
            "network": False,
            "credentials": False,
            "persistence": False,
            "publication": False,
            "release": False,
            "production": False,
        },
        "formal_TST_018": "NOT_EXECUTED",
        "formal_TST_020": "NOT_EXECUTED",
    }
    return yaml.safe_dump(
        value, allow_unicode=True, default_flow_style=False, sort_keys=False
    ).encode("utf-8", errors="strict")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = _load_contract(root)
    fixture = _fixture_bytes(root)
    sources = _source_hashes(root)
    plan = _plan_bytes(contract, sources, fixture)
    return {
        PLAN_PATH: plan,
        FIXTURE_PATH: fixture,
        MANIFEST_PATH: _manifest_bytes(sources, plan, fixture),
    }


def _output(root: Path, relative: Path, *, create_parent: bool) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        _fail("UNSAFE_OUTPUT_PATH", "output")
    parent = root / relative.parent
    try:
        if create_parent and not parent.exists():
            parent.mkdir(mode=0o755)
        metadata = parent.lstat()
    except OSError:
        _fail("OUTPUT_PARENT_INVALID", "output")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("OUTPUT_PARENT_INVALID", "output")
    destination = parent / relative.name
    if not destination.is_absolute():
        _fail("UNSAFE_OUTPUT_PATH", "output")
    return destination


def _writer(root: Path) -> Any:
    raw = _read(root, HARDENED_WRITER_PATH, "hardened_writer")
    if not raw:
        _fail("HARDENED_WRITER_UNAVAILABLE", "hardened_writer")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        module = importlib.import_module("scripts.secure_generated_publication")
        origin = Path(cast(str, module.__file__)).resolve(strict=True)
    except Exception:
        _fail("HARDENED_WRITER_UNAVAILABLE", "hardened_writer")
    if origin != (root / HARDENED_WRITER_PATH).resolve(strict=True):
        _fail("HARDENED_WRITER_ORIGIN_MISMATCH", "hardened_writer")
    return module


def _replace_generated(root: Path, artifacts: tuple[tuple[Path, bytes], ...]) -> None:
    writer = _writer(root)
    try:
        writer.publish_generated(
            artifacts,
            namespace="st0806-v2",
            maximum_payload_bytes=4 * 1024 * 1024,
        )
    except BaseException as failure:
        if isinstance(failure, writer.SecurePublicationError):
            _fail("OUTPUT_TRANSACTION_FAILED", "output")
        raise


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if set(outputs) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    if check:
        for relative in GENERATED_PATHS:
            path = _output(root, relative, create_parent=False)
            try:
                metadata = path.lstat()
                actual = path.read_bytes()
            except OSError:
                _fail("GENERATED_OUTPUT_MISSING", "output")
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o644
                or actual != outputs[relative]
            ):
                _fail("GENERATED_OUTPUT_DRIFT", "output")
        return
    artifacts = tuple(
        (_output(root, relative, create_parent=True), outputs[relative])
        for relative in GENERATED_PATHS
    )
    _replace_generated(root, artifacts)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build ST-0806 V2 artifacts")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(REPO_ROOT, check=bool(args.check))
    except AiDraftBuildError as exc:
        print(f"ERROR code={exc.code} field={exc.field}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE field=builder", file=sys.stderr)
        return 1
    print("ST-0806 V2 check passed" if args.check else "ST-0806 V2 artifacts generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
