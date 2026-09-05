"""The optional status identity map is exact, backwards compatible and read-only."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from jsonschema import Draft202012Validator
from scripts import raos_wordpress_deployment_operator as operator
from scripts import raos_wordpress_publication_request as publication

ROOT = Path(__file__).resolve().parents[2]
IDS = ["a" * 64, "b" * 64]
TOKEN = "c" * 64
MANIFEST = "d" * 64


def status(*, bindings: bool = True) -> dict:
    response = {
        "schema": "RAOSWordPressPublicationBatchStatusV1",
        "batch_token": TOKEN,
        "batch_manifest_sha256": MANIFEST,
        "proposal_count": len(IDS),
        "proposal_ids": IDS.copy(),
        "state": "REGISTERED",
        "expires_at_gmt": "2026-09-05T06:00:00Z",
        "preconditions_ready": False,
    }
    if bindings:
        response["proposal_bindings"] = {
            IDS[0]: {
                "kind": "CONTENT_RELEASE",
                "idempotency_key": "e" * 64,
                "before_sha256": "f" * 64,
                "after_sha256": "1" * 64,
                "post_id": 28,
                "post_type": "post",
            },
            IDS[1]: {
                "kind": "THEME_RELEASE",
                "idempotency_key": None,
                "before_sha256": None,
                "after_sha256": "2" * 64,
                "post_id": None,
                "post_type": None,
            },
        }
    return response


@pytest.mark.parametrize("bindings", (False, True))
def test_status_optional_bindings_match_published_json_schema(bindings: bool) -> None:
    schema = json.loads(
        (
            ROOT / "changes/wordpress-mcp-v1/contracts/wordpress-mcp.v1.schema.json"
        ).read_text()
    )
    validator = Draft202012Validator(schema)
    validator.validate(status(bindings=bindings))
    if bindings:
        for field, value in (
            ("post_id", "28"),
            ("post_type", None),
            ("kind", "PLUGIN_CHANGE"),
            ("idempotency_key", "invalid"),
        ):
            invalid = status()
            invalid["proposal_bindings"][IDS[0]][field] = value
            assert list(validator.iter_errors(invalid))


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch):
    calls = []
    box = [status()]

    def request(*args, **kwargs):
        calls.append((args, kwargs))
        return deepcopy(box[0])

    def forbidden(*_args, **_kwargs):
        pytest.fail("GET status may not claim, apply, finalize or obtain credentials")

    monkeypatch.setattr(operator, "request_json", request)
    for name in (
        "credentials",
        "release_wait_and_apply",
        "_release_batch_claim",
        "_finalize_applied_operation",
        "_finalize_failed_operation",
    ):
        monkeypatch.setattr(operator, name, forbidden)
    return box, calls


@pytest.mark.parametrize("bindings", (False, True))
def test_status_optional_identity_map_preserves_legacy_get_contract(
    transport, bindings: bool
) -> None:
    box, calls = transport
    box[0] = status(bindings=bindings)
    assert operator._release_batch_status_response(TOKEN, MANIFEST, IDS) == box[0]
    assert operator._release_batch_status(TOKEN, MANIFEST, IDS) == ("REGISTERED", False)
    assert calls == [(("GET", f"/publication-batches/{TOKEN}"), {"deadline": None})] * 2


@pytest.mark.parametrize("mapping", (None, [], {}, {IDS[0]: {}}, {"9" * 64: {}}))
def test_status_identity_map_requires_the_exact_member_set(transport, mapping) -> None:
    box, calls = transport
    box[0]["proposal_bindings"] = mapping
    with pytest.raises(operator.OperatorFailure):
        operator._release_batch_status_response(TOKEN, MANIFEST, IDS)
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("kind", "PLUGIN_CHANGE"),
        ("kind", "UNKNOWN"),
        ("kind", []),
        ("kind", None),
        ("idempotency_key", "bad"),
        ("idempotency_key", True),
        ("idempotency_key", {}),
        ("before_sha256", "F" * 64),
        ("after_sha256", "1" * 63),
        ("after_sha256", []),
        ("post_id", 0),
        ("post_id", True),
        ("post_id", "28"),
        ("post_id", None),
        ("post_id", []),
        ("post_type", "attachment"),
        ("post_type", None),
        ("post_type", []),
    ],
)
def test_status_binding_bad_types_and_unknown_values_are_bounded_failures(
    transport, key, value
) -> None:
    box, calls = transport
    box[0]["proposal_bindings"][IDS[0]][key] = value
    with pytest.raises(operator.OperatorFailure):
        operator._release_batch_status_response(TOKEN, MANIFEST, IDS)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "field",
    (
        "kind",
        "idempotency_key",
        "before_sha256",
        "after_sha256",
        "post_id",
        "post_type",
    ),
)
def test_status_binding_missing_or_private_fields_are_not_forwarded(
    transport, field
) -> None:
    box, calls = transport
    del box[0]["proposal_bindings"][IDS[0]][field]
    with pytest.raises(operator.OperatorFailure):
        operator._release_batch_status_response(TOKEN, MANIFEST, IDS)
    box[0] = status()
    box[0]["proposal_bindings"][IDS[0]]["payload"] = {"private": "synthetic"}
    with pytest.raises(operator.OperatorFailure):
        operator._release_batch_status_response(TOKEN, MANIFEST, IDS)
    assert len(calls) == 2


@pytest.mark.parametrize(("field", "value"), (("post_id", 28), ("post_type", "post")))
def test_theme_binding_cannot_claim_a_content_target(transport, field, value) -> None:
    box, _calls = transport
    box[0]["proposal_bindings"][IDS[1]][field] = value
    with pytest.raises(operator.OperatorFailure):
        operator._release_batch_status_response(TOKEN, MANIFEST, IDS)


def test_page_target_and_legacy_nullable_idempotency_are_accepted(transport) -> None:
    box, _calls = transport
    box[0]["proposal_bindings"][IDS[0]]["post_type"] = "page"
    box[0]["proposal_bindings"][IDS[0]]["idempotency_key"] = None
    assert operator._release_batch_status_response(TOKEN, MANIFEST, IDS) == box[0]


def test_php_batch_status_behavior() -> None:
    php = os.environ.get("RAOS_PHP_BIN") or shutil.which("php")
    if not php:
        pytest.skip(
            "PHP CLI unavailable; execute the pure harness in the local PHP runtime"
        )
    result = subprocess.run(
        [
            php,
            "-d",
            "display_errors=1",
            str(ROOT / "tests/wordpress_mcp_v1/php/batch_status_bindings_harness.php"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    assert result.stdout == "BATCH_STATUS_BINDINGS_READ_ONLY_OK\n"


def legacy_receipt() -> dict:
    return {
        "desired_theme_tree_sha256": "2" * 64,
        "selected_slugs": ["existing-post"],
        "selected_documents": {"existing-post": "post"},
        "proposals": [
            {
                "kind": kind,
                "slug": slug,
                "proposal_id": proposal_id,
                "after_sha256": after,
                "expires_at_gmt": "2026-09-05T06:00:00Z",
                "idempotency_key": "e" * 64,
            }
            for kind, slug, proposal_id, after in (
                ("CONTENT_RELEASE", "existing-post", IDS[0], "1" * 64),
                ("THEME_RELEASE", None, IDS[1], "2" * 64),
            )
        ],
        "batch_registration": {
            "schema": "RAOSWordPressPublicationBatchV1",
            "batch_token": TOKEN,
            "batch_manifest_sha256": MANIFEST,
            "expected_theme_tree_sha256": "2" * 64,
            "proposal_ids": IDS.copy(),
            "proposal_count": len(IDS),
            "state": "REGISTERED",
            "expires_at_gmt": "2026-09-05T06:00:00Z",
            "review_url": publication.REVIEW_URL,
        },
    }


@pytest.mark.parametrize("bindings", (False, True))
@pytest.mark.parametrize(
    "state", ("REGISTERED", "APPROVED", "APPLIED", "EXPIRED", "FAILED")
)
def test_legacy_status_accepts_both_versions_through_shared_pure_validation(
    monkeypatch, bindings, state
) -> None:
    response = status(bindings=bindings)
    response["state"] = state
    receipt = legacy_receipt()
    original = deepcopy(receipt)
    calls = []

    def remote(command, payload, **kwargs):
        calls.append((command, payload))
        assert kwargs["timeout"] == 120
        return response

    def forbidden(*_args, **_kwargs):
        pytest.fail("shared validation is pure: no second transport, clock or apply")

    monkeypatch.setattr(publication, "_deployment_mcp_call", remote)
    for name in (
        "request_json",
        "credentials",
        "_release_batch_claim",
        "_ensure_request_deadline",
    ):
        monkeypatch.setattr(publication.wordpress_deployment, name, forbidden)
    monkeypatch.setattr(publication, "wait_and_apply", forbidden)
    assert publication.publication_batch_status(receipt) is response
    assert receipt == original
    assert calls == [
        (
            "publication-batch-status",
            {
                "batch_token": TOKEN,
                "batch_manifest_sha256": MANIFEST,
                "proposal_ids": IDS,
            },
        )
    ]


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("proposal_bindings",), None),
        (("proposal_bindings",), {}),
        (("proposal_bindings", IDS[0], "kind"), "PLUGIN_CHANGE"),
        (("proposal_bindings", IDS[0], "kind"), []),
        (("proposal_bindings", IDS[0], "post_id"), True),
        (("proposal_bindings", IDS[0], "post_type"), "attachment"),
        (("proposal_bindings", IDS[0], "idempotency_key"), "invalid"),
        (("proposal_bindings", IDS[0], "after_sha256"), "0" * 63),
        (("proposal_bindings", IDS[0], "private_payload"), {}),
        (("proposal_bindings", IDS[1], "post_id"), 28),
        (("proposal_bindings", "9" * 64), {}),
        (("private_payload",), {}),
        (("batch_token",), "9" * 64),
        (("state",), []),
    ],
)
def test_legacy_status_keeps_strict_map_validation_and_legacy_error_code(
    monkeypatch, path, value
) -> None:
    response = status()
    target = response
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    monkeypatch.setattr(publication, "_deployment_mcp_call", lambda *_a, **_k: response)
    with pytest.raises(
        publication.PublicationFailure,
        match="^RAOS_WORDPRESS_REQUEST_BATCH_STATUS_INVALID$",
    ):
        publication.publication_batch_status(legacy_receipt())


def test_shared_validator_does_not_perform_a_network_request(monkeypatch) -> None:
    def forbidden(*_args, **_kwargs):
        pytest.fail("pure response validator cannot read credentials, network or clock")

    for name in ("request_json", "credentials", "_ensure_request_deadline"):
        monkeypatch.setattr(operator, name, forbidden)
    response = status()
    assert (
        operator.validate_release_batch_status_response(response, TOKEN, MANIFEST, IDS)
        is response
    )
