"""Source-layer, package-boundary and build-owner checks for RAOS V2."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo

import pytest

from scripts import build_raos_v2_successor as builder
from scripts import validate_raos_v2_successor as validator
from scripts.raos_build_core import discover_registry


ROOT = Path(__file__).resolve().parents[2]


def test_attached_package_is_bound_but_implementation_prompt_is_not_imported() -> None:
    source = json.loads(
        (ROOT / "changes/raos-v2/source-import.v1.json").read_text(encoding="utf-8")
    )
    assert len(source["imported_files"]) == 19
    assert source["excluded_files"] == [
        {
            "bytes": 22093,
            "path": "CODEX_MASTER_IMPLEMENTATION_PROMPT.md",
            "reason": "PROMPT_IS_DATA_NOT_EXECUTABLE_AUTHORITY",
            "sha256": builder.PROMPT_SHA256,
        }
    ]
    assert not (
        ROOT
        / "changes/raos-v2/source-package/2.0.0-design"
        / "CODEX_MASTER_IMPLEMENTATION_PROMPT.md"
    ).exists()


@pytest.mark.skipif(
    not validator.PACKAGE_PATH.is_file(),
    reason="attached ZIP is local-only; committed source-layer integrity remains mandatory",
)
def test_local_attached_zip_container_matches_fixed_hash() -> None:
    receipt = validator.validate_package()
    assert receipt["status"] == "PASSED_LOCAL"
    assert receipt["package_sha256"] == builder.PACKAGE_SHA256


def test_every_imported_source_file_matches_its_receipt() -> None:
    receipt = json.loads(
        (ROOT / "changes/raos-v2/source-import.v1.json").read_text(encoding="utf-8")
    )
    source_root = ROOT / "changes/raos-v2/source-package/2.0.0-design"
    for row in receipt["imported_files"]:
        payload = (source_root / row["path"]).read_bytes()
        assert len(payload) == row["bytes"]
        assert hashlib.sha256(payload).hexdigest() == row["sha256"]


def test_source_manifest_has_a_non_tautological_immutable_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = (
        ROOT
        / "changes/raos-v2/source-package/2.0.0-design/MANIFEST.sha256"
    ).read_bytes()
    assert hashlib.sha256(manifest).hexdigest() == builder.SOURCE_MANIFEST_SHA256
    target = tmp_path / builder.SOURCE_ROOT / "MANIFEST.sha256"
    target.parent.mkdir(parents=True)
    target.write_bytes(manifest + b"\n")
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    with pytest.raises(builder.BuildFailure, match="MANIFEST_ANCHOR"):
        builder._manifest_hashes()


def test_successor_has_one_generator_owner_and_explicit_test_path() -> None:
    spec = discover_registry()["build_raos_v2_successor"]
    assert spec.generator == Path("scripts/build_raos_v2_successor.py")
    assert spec.test_paths == (Path("tests/raos_v2"),)
    assert spec.supports_check is True
    assert set(spec.outputs) == set(builder.OUTPUT_PATHS)


def test_integration_pr_body_summarizes_fixed_decision_corrections() -> None:
    body = builder.integration_pr_body_document({})
    for marker in (
        "## Decision corrections",
        "`C-V2-002`",
        "seven templates",
        "`C-V2-003`",
        "T-V2-007 starts in Phase 1",
        "`C-V2-004`",
        "P0=16h, P1=40h and P2=80h",
        "`C-V2-005` + `C-V2-010`",
        "B-V2-009 closes over B-V2-001..008",
        "`C-V2-007` + `C-V2-008`",
        "real Phase 0-2 content remains unreviewed",
        "only synthetic fixtures may seal",
    ):
        assert marker in body


@pytest.mark.parametrize(
    "payload",
    [
        b'{"a": 1, "a": 2}',
        b"",
        b"NaN",
        b'{"nested": [Infinity]}',
        b'{"value": -Infinity}',
    ],
)
def test_strict_json_rejects_duplicate_or_empty_documents(payload: bytes) -> None:
    with pytest.raises(validator.ValidationFailure):
        validator.load_json_strict(payload)


@pytest.mark.parametrize(
    "payload",
    [
        b"a: 1\na: 2\n",
        b"a: &x 1\nb: *x\n",
        b"a: !!str 1\n",
    ],
)
def test_strict_yaml_rejects_duplicates_aliases_anchors_and_tags(
    payload: bytes,
) -> None:
    with pytest.raises(validator.ValidationFailure):
        validator.load_yaml_strict(payload)


def test_generator_consumes_machine_inputs_through_strict_loaders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "duplicate.json").write_text('{"a": 1, "a": 2}\n', encoding="utf-8")
    (tmp_path / "alias.yaml").write_text("a: &x 1\nb: *x\n", encoding="utf-8")
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    with pytest.raises(builder.BuildFailure):
        builder._read_json(Path("duplicate.json"))
    with pytest.raises(builder.BuildFailure):
        builder._read_yaml(Path("alias.yaml"))


def test_default_phase0_capture_path_does_not_use_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written: list[bytes] = []

    def deny_fetch(_url: str) -> object:
        raise AssertionError("network must remain disabled")

    monkeypatch.setattr(validator, "_fetch", deny_fetch)
    monkeypatch.setattr(
        validator, "_atomic_write", lambda _path, payload: written.append(payload)
    )
    document = validator.capture_phase0(public_read_only=False)
    assert document["public_observation_status"] == "NOT_EXECUTED"
    assert document["public_urls"] == []
    assert document["captured_at"].endswith("+09:00")
    assert document["visual_baseline"] == []
    assert "separate manual recorded-evidence" in document["visual_baseline_note"]
    assert written


def test_capture_transport_disables_environment_proxies_and_sensitive_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    class Response:
        status = 200
        headers = {"Content-Type": "text/html"}

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return b"<h1>safe</h1>"

    class Opener:
        def open(self, request: object, *, timeout: int) -> Response:
            observed["request"] = request
            observed["timeout"] = timeout
            return Response()

    def fake_build_opener(*handlers: object) -> Opener:
        observed["handlers"] = handlers
        return Opener()

    monkeypatch.setattr(validator, "build_opener", fake_build_opener)
    status, _payload, _headers, _redirects = validator._fetch(
        "https://kurashinoshirube.com/"
    )
    assert status == 200
    handlers = observed["handlers"]
    assert isinstance(handlers, tuple)
    proxy = next(item for item in handlers if isinstance(item, validator.ProxyHandler))
    assert proxy.proxies == {}
    assert any(isinstance(item, validator.HTTPSHandler) for item in handlers)
    request = observed["request"]
    assert isinstance(request, validator.Request)
    header_names = {name.lower() for name, _value in request.header_items()}
    assert not {"cookie", "authorization", "proxy-authorization"} & header_names


def test_capture_writer_rejects_target_and_ancestor_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    protected = root / "docs/canonical/anchor.txt"
    protected.parent.mkdir(parents=True)
    protected.write_text("immutable", encoding="utf-8")
    recorded = root / "changes/raos-v2/recorded-inputs/phase0-capture.v1.json"
    recorded.parent.mkdir(parents=True)
    recorded.symlink_to(protected)
    monkeypatch.setattr(validator, "ROOT", root)
    monkeypatch.setattr(validator, "RECORDED_INPUT", recorded)
    with pytest.raises(validator.ValidationFailure, match="CAPTURE_OUTPUT_UNSAFE"):
        validator._atomic_write(recorded, b"tamper")
    assert protected.read_text(encoding="utf-8") == "immutable"

    recorded.unlink()
    recorded.parent.rmdir()
    alternate = root / "alternate"
    alternate.mkdir()
    (root / "changes/raos-v2/recorded-inputs").symlink_to(alternate)
    with pytest.raises(validator.ValidationFailure, match="CAPTURE_OUTPUT_UNSAFE"):
        validator._atomic_write(recorded, b"tamper")


def test_generator_writer_rejects_target_and_ancestor_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    protected = root / "docs/canonical/anchor.txt"
    protected.parent.mkdir(parents=True)
    protected.write_text("immutable", encoding="utf-8")
    relative = Path("changes/raos-v2/generated/out.json")
    target = root / relative
    target.parent.mkdir(parents=True)
    target.symlink_to(protected)
    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "OUTPUT_PATHS", (relative,))
    with pytest.raises(builder.BuildFailure, match="OUTPUT_TARGET_INVALID"):
        builder.write_generated_output(relative, b"tamper")
    assert protected.read_text(encoding="utf-8") == "immutable"

    target.unlink()
    target.parent.rmdir()
    alternate = root / "alternate"
    alternate.mkdir()
    (root / "changes/raos-v2/generated").symlink_to(alternate)
    with pytest.raises(builder.BuildFailure, match="OUTPUT_ANCESTOR_INVALID"):
        builder.write_generated_output(relative, b"tamper")


def test_immutable_guard_detects_protected_changes_committed_after_baseline(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()

    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    git("init", "-q")
    git("config", "user.name", "RAOS Test")
    git("config", "user.email", "raos-test@example.invalid")
    protected = repository / "docs/canonical/anchor.txt"
    protected.parent.mkdir(parents=True)
    protected.write_text("baseline\n", encoding="utf-8")
    git("add", "docs/canonical/anchor.txt")
    git("commit", "-qm", "baseline")
    baseline = git("rev-parse", "HEAD")
    assert validator.protected_path_changes(baseline, root=repository) == []

    protected.write_text("tampered\n", encoding="utf-8")
    git("add", "docs/canonical/anchor.txt")
    git("commit", "-qm", "protected drift")
    assert validator.protected_path_changes(baseline, root=repository) == [
        "docs/canonical/anchor.txt"
    ]


def test_recorded_capture_cannot_move_the_immutable_base_forward(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture_path = tmp_path / builder.RECORDED_INPUT_PATH
    capture_path.parent.mkdir(parents=True)
    capture_path.write_text(
        json.dumps(
            {
                "schema": "RAOS_V2_PHASE0_CAPTURE_V1",
                "repository": {"head": "b" * 40},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    with pytest.raises(builder.BuildFailure, match="CAPTURE_INPUT_INVALID"):
        builder._capture_input()
    assert builder.IMMUTABLE_BASE_HEAD == validator.IMMUTABLE_BASE_HEAD


def test_local_suite_pass_requires_current_test_and_source_inventory_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bindings = {
        "test_inventory": {
            "schema": "RAOS_V2_FILE_INVENTORY_BINDING_V1",
            "file_count": 13,
            "total_bytes": 123,
            "path_set_sha256": "a" * 64,
            "content_inventory_sha256": "b" * 64,
        },
        "implementation_source_inventory": {
            "schema": "RAOS_V2_FILE_INVENTORY_BINDING_V1",
            "file_count": 64,
            "total_bytes": 456,
            "path_set_sha256": "c" * 64,
            "content_inventory_sha256": "d" * 64,
        },
        "machine_contract_inventory": {
            "schema": "RAOS_V2_FILE_INVENTORY_BINDING_V1",
            "file_count": 40,
            "total_bytes": 789,
            "path_set_sha256": "e" * 64,
            "content_inventory_sha256": "f" * 64,
        },
    }
    monkeypatch.setattr(
        validator, "local_test_evidence_bindings", lambda **_kwargs: bindings
    )
    monkeypatch.setattr(
        validator,
        "_git_head_and_ancestry",
        lambda _head, **_kwargs: ("a" * 40, True),
    )
    receipt = {
        "schema": "RAOS_V2_RECORDED_LOCAL_TEST_EVIDENCE_V1",
        "version": "2.0.0",
        "command": validator.LOCAL_TEST_COMMAND,
        "command_contract": validator.LOCAL_TEST_COMMAND_CONTRACT,
        "executed_at_jst": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(),
        "executed_head": "a" * 40,
        "status": "PASSED_LOCAL",
        "exit_code": 0,
        "passed": 289,
        "failed": 0,
        "skipped": 0,
        "classification": "LOCAL_ONLY",
        "formal_ci": "NOT_CLAIMED",
        "external_actions": "NOT_EXECUTED",
        **bindings,
        "raw_output": {
            "local_path": validator.LOCAL_TEST_RAW_OUTPUT_PATH.as_posix(),
            "sha256": "0" * 64,
            "bytes": 10,
        },
    }
    verified = validator.verify_local_test_evidence(receipt, root=tmp_path)
    assert verified["effective_status"] == "PASSED_LOCAL"
    assert verified["binding_verification"] == "CURRENT_TREE_BOUND"

    changed = json.loads(json.dumps(receipt))
    changed["test_inventory"]["file_count"] += 1
    stale = validator.verify_local_test_evidence(changed, root=tmp_path)
    assert stale["effective_status"] == "AWAITING_GATE_STALE_BINDING"
    assert stale["binding_verification"] == (
        "STALE_IMPLEMENTATION_OR_TEST_INVENTORY"
    )


def test_local_suite_tee_is_promoted_only_after_pytest_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.name", "RAOS Test"], cwd=repository, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "raos-test@example.invalid"],
        cwd=repository,
        check=True,
    )
    anchor = repository / "anchor.txt"
    anchor.write_text("anchor\n", encoding="utf-8")
    subprocess.run(["git", "add", "anchor.txt"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "anchor"], cwd=repository, check=True)
    binding = {
        "schema": "RAOS_V2_FILE_INVENTORY_BINDING_V1",
        "file_count": 1,
        "total_bytes": 1,
        "path_set_sha256": "a" * 64,
        "content_inventory_sha256": "b" * 64,
    }
    bindings = {
        "test_inventory": binding,
        "implementation_source_inventory": binding,
        "machine_contract_inventory": binding,
    }
    monkeypatch.setattr(
        validator, "local_test_evidence_bindings", lambda **_kwargs: bindings
    )
    monkeypatch.setattr(
        validator,
        "_git_head_and_ancestry",
        lambda _head, **_kwargs: ("a" * 40, True),
    )
    temporary = repository / validator.LOCAL_TEST_RAW_OUTPUT_TEMP_PATH
    temporary.parent.mkdir(parents=True)
    temporary.write_text("1 passed in 0.01s\n", encoding="utf-8")
    receipt = validator.record_local_test_evidence(root=repository)
    final = repository / validator.LOCAL_TEST_RAW_OUTPUT_PATH
    assert receipt["status"] == "PASSED_LOCAL"
    assert receipt["command_contract"] == (
        "BASH_PIPEFAIL_TEE_TEMP_PROMOTED_BY_RECORDER_V2"
    )
    assert final.read_text(encoding="utf-8") == "1 passed in 0.01s\n"
    assert not temporary.exists()


def test_normal_raos_v2_pytest_denies_network_and_dns() -> None:
    import socket

    with pytest.raises(RuntimeError, match="RAOS_V2_TEST_NETWORK_DENIED"):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(RuntimeError, match="RAOS_V2_TEST_NETWORK_DENIED"):
        socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    with pytest.raises(RuntimeError, match="RAOS_V2_TEST_NETWORK_DENIED"):
        socket.create_connection(("127.0.0.1", 9))
    with pytest.raises(RuntimeError, match="RAOS_V2_TEST_NETWORK_DENIED"):
        socket.getaddrinfo("example.invalid", 443)


def test_manual_visual_review_is_separate_and_binds_all_27_pngs() -> None:
    value = json.loads(
        (
            ROOT
            / "changes/raos-v2/recorded-inputs/phase2-visual-evidence.v1.json"
        ).read_text(encoding="utf-8")
    )
    pages = json.loads(
        (
            ROOT
            / "packages/web-ui/src/decision-support-v2/preview/pages.v2.json"
        ).read_text(encoding="utf-8")
    )["pages"]
    state_to_classification = {
        "LOCAL_PREVIEW": "PUBLIC_CANDIDATE",
        "PLANNED_LOCKED": "PLANNED_LOCKED",
        "FIXTURE_ONLY": "FIXTURE_ONLY",
    }
    digests: dict[str, str] = {}
    classifications: dict[str, str] = {}
    for page in pages:
        route = page["route"]
        preview_path = (
            ROOT / "changes/raos-v2/phase-2/preview/index.html"
            if route == "/"
            else ROOT
            / "changes/raos-v2/phase-2/preview"
            / route.lstrip("/")
            / "index.html"
        )
        digests[route] = hashlib.sha256(preview_path.read_bytes()).hexdigest()
        classifications[route] = state_to_classification[
            page["publication_state"]
        ]
    verification = validator.verify_visual_review_evidence(
        value,
        preview_digests=digests,
        route_classifications=classifications,
        root=ROOT,
        require_raw=True,
    )
    assert verification == {
        "effective_status": "PASSED_LOCAL_MANUAL_VISUAL_REVIEW",
        "review_binding": "CURRENT_PREVIEW_AND_CAPTURE_SET_BOUND",
        "raw_verification": "RAW_CAPTURE_AND_27_PNGS_VERIFIED_LOCAL",
        "captures": 27,
        "critical_findings": 0,
        "major_findings": 0,
    }
    modified_review = json.loads(json.dumps(value))
    modified_review["reviews"][0]["critical_findings"] = 1
    with pytest.raises(validator.ValidationFailure, match="VISUAL_REVIEW_ROW"):
        validator.verify_visual_review_evidence(
            modified_review,
            preview_digests=digests,
            route_classifications=classifications,
            root=ROOT,
        )
    modified_hash = json.loads(json.dumps(value))
    modified_hash["reviews"][0]["screenshot_sha256"] = "0" * 64
    with pytest.raises(validator.ValidationFailure):
        validator.verify_visual_review_evidence(
            modified_hash,
            preview_digests=digests,
            route_classifications=classifications,
            root=ROOT,
        )
