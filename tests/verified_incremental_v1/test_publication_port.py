"""Synthetic MCP/approval transport only; never executes external publication."""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import importlib.util
from pathlib import Path
import sys
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import raos_wordpress_incremental_publication as port  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "synthetic_release_examples", Path(__file__).with_name("test_release.py")
)
assert spec is not None and spec.loader is not None
examples = importlib.util.module_from_spec(spec)
spec.loader.exec_module(examples)
NOW = examples.NOW
publication = port.publication


class SyntheticServer:
    def __init__(self, documents, desired):
        self.documents = deepcopy(documents)
        self.desired = desired
        self.proposals = {}
        self.operations = {}
        self.batch = None
        self.state = "REGISTERED"
        self.apply_count = 0
        self.proposal_count = 0
        self.lose_apply_response = False
        self.gets = 0
        self.theme_tree = "9" * 64
        self.gates = {"global": True, "content_apply": True, "theme_apply": True}
        self.theme_proposals = {}
        self.desired_theme_tree = "9" * 64
        self.theme_operation_gets = 0
        self.proposal_bindings = {}

    def initialize(self):
        pass

    def call(self, name, arguments):
        if name == "raos-codex-site-status":
            return {}
        if name == "raos-codex-content-get":
            self.gets += 1
            return deepcopy(
                next(
                    row
                    for row in self.documents.values()
                    if row["id"] == arguments["id"]
                )
            )
        if name == "raos-codex-content-propose-release":
            self.proposal_count += 1
            identifier = arguments["idempotency_key"]
            after = publication._content_after_sha256(
                arguments["document"], arguments["id"]
            )
            self.proposals[identifier] = (
                arguments["id"],
                deepcopy(arguments["document"]),
                after,
            )
            self.proposal_bindings[identifier] = {
                "kind": "CONTENT_RELEASE",
                "idempotency_key": arguments["idempotency_key"],
                "before_sha256": self.documents[arguments["document"]["slug"]][
                    "content_sha256"
                ],
                "after_sha256": after,
                "post_id": arguments["id"],
                "post_type": arguments["document"]["post_type"],
            }
            return {
                "proposal_id": identifier,
                "after_sha256": after,
                "expires_at_gmt": examples.stamp(NOW + timedelta(minutes=15)),
            }
        if name == "raos-codex-publication-batch-register":
            self.batch = {
                "schema": "RAOSWordPressPublicationBatchV1",
                "batch_token": "a" * 64,
                "batch_manifest_sha256": "b" * 64,
                "proposal_ids": arguments["proposal_ids"],
                "proposal_count": len(arguments["proposal_ids"]),
                "expected_theme_tree_sha256": arguments["expected_theme_tree_sha256"],
                "state": self.state,
                "expires_at_gmt": examples.stamp(NOW + timedelta(minutes=15)),
                "review_url": publication.REVIEW_URL,
            }
            return deepcopy(self.batch)
        if name == "raos-codex-operation-get":
            return deepcopy(self.operations[arguments["operation_id"]])
        raise AssertionError(name)

    def deploy(self, command, value):
        if command == "theme-propose-release":
            identifier = value["idempotency_key"]
            self.theme_proposals[identifier] = self.desired_theme_tree
            self.proposal_bindings[identifier] = {
                "kind": "THEME_RELEASE",
                "idempotency_key": value["idempotency_key"],
                "before_sha256": self.theme_tree,
                "after_sha256": self.desired_theme_tree,
                "post_id": None,
                "post_type": None,
            }
            return {
                "proposal": {
                    "proposal_id": identifier,
                    "after_tree_sha256": self.desired_theme_tree,
                    "expires_at_gmt": examples.stamp(NOW + timedelta(minutes=15)),
                }
            }
        if command == "operation-status":
            self.theme_operation_gets += 1
            return {
                "kind": "THEME_RELEASE",
                "operation": deepcopy(self.operations[value["operation_id"]]),
            }
        if command == "deployment-status":
            return {
                "schema": "RAOSWordPressDeploymentStatusV1",
                "origin": publication.ORIGIN,
                "plugin_runtime_revision": publication.EXPECTED_PLUGIN_RUNTIME_REVISION,
                "private_directory_ready": True,
                "gates": self.gates,
                "apply_authorization": {
                    "mode": "approval_scoped_lease",
                    "default": False,
                    "single_use": True,
                    "lease_ttl_seconds": publication.EXPECTED_APPLY_LEASE_TTL_SECONDS,
                },
                "theme": {
                    "slug": "kurashinoshirube-child",
                    "active": True,
                    "tree_sha256": self.theme_tree,
                },
            }
        if command == "publication-batch-status":
            assert self.batch is not None
            return {
                "schema": "RAOSWordPressPublicationBatchStatusV1",
                **value,
                "proposal_count": len(value["proposal_ids"]),
                "state": self.state,
                "expires_at_gmt": examples.stamp(NOW + timedelta(minutes=15)),
                "preconditions_ready": True,
                "proposal_bindings": deepcopy(self.proposal_bindings),
            }
        if command == "release-wait-and-apply":
            assert self.state == "APPROVED"
            assert value["evidence_expires_at_gmt"] == examples.stamp(
                NOW + timedelta(minutes=10)
            )
            self.apply_count += 1
            for identifier in value["proposal_ids"]:
                if identifier in self.theme_proposals:
                    self.operations[identifier] = {
                        "schema": "OperationReceiptV1",
                        "proposal_id": identifier,
                        "operation_id": identifier,
                        "state": "APPLIED",
                        "result_code": "THEME_APPLIED",
                        "before_sha256": self.theme_tree,
                        "after_sha256": self.theme_proposals[identifier],
                        "audit_id": "f" * 64,
                    }
                    self.theme_tree = self.theme_proposals[identifier]
                    continue
                post_id, target, after = self.proposals[identifier]
                previous = self.documents[target["slug"]]
                self.documents[target["slug"]] = {
                    **target,
                    "id": post_id,
                    "status": "publish",
                    "content_sha256": after,
                    "revision_id": previous["revision_id"] + 1,
                    "modified_gmt": examples.stamp(NOW + timedelta(seconds=1)),
                }
                self.operations[identifier] = {
                    "schema": "OperationReceiptV1",
                    "proposal_id": identifier,
                    "operation_id": identifier,
                    "state": "APPLIED",
                    "result_code": "CONTENT_APPLIED",
                    "before_sha256": previous["content_sha256"],
                    "after_sha256": after,
                    "audit_id": "f" * 64,
                }
            self.state = "APPLIED"
            if self.lose_apply_response:
                publication.fail("SYNTHETIC_RESPONSE_LOST")
            return {
                "schema": "ReleaseWaitApplyReceiptV1",
                "state": "APPLIED",
                "batch_token": value["batch_token"],
                "batch_manifest_sha256": value["batch_manifest_sha256"],
                "proposal_ids": value["proposal_ids"],
                "proposal_count": len(value["proposal_ids"]),
                "receipts": list(self.operations.values()),
            }
        raise AssertionError(command)


@pytest.fixture
def world(tmp_path, monkeypatch, request):
    monkeypatch.setattr(port, "OWNER", tmp_path)
    private = tmp_path / ".secrets/wordpress-mcp"
    monkeypatch.setattr(port, "PRIVATE", private)
    for directory in (
        tmp_path / ".secrets",
        private,
        private / "incremental-candidates",
        private / "incremental-snapshots",
    ):
        directory.mkdir(mode=0o700)
    manifest, inputs = examples.sample()
    documents = {}
    for slug, entry in inputs["inventory"].items():
        row = {
            "id": entry.post_id,
            "slug": slug,
            "post_type": entry.post_type,
            "status": "publish",
            "title": slug.title(),
            "excerpt": "Synthetic excerpt",
            "block_markup": f"<div><h2>{slug}</h2></div>",
            "taxonomies": {},
            "media_ids": [],
            "revision_id": 1,
            "modified_gmt": examples.stamp(NOW),
        }
        row["content_sha256"] = publication._content_after_sha256(row, row["id"])
        documents[slug] = row
        inputs["inventory"][slug] = replace(entry, content_sha256=row["content_sha256"])
    manifest["articles"][0]["baseline_sha256"] = documents["guide"]["content_sha256"]
    manifest["unchanged_documents"] = {
        slug: row["content_sha256"]
        for slug, row in documents.items()
        if slug != "guide"
    }
    include_theme = getattr(request, "param", False)
    if include_theme:
        theme_bytes = b'{"synthetic_theme":"new"}'
        theme_sha = port.digest(theme_bytes)
        inputs["artifact_bytes"]["theme-tree"] = theme_bytes
        manifest["shared_artifacts"] = {
            "theme": {
                "key": "theme-tree",
                "sha256": theme_sha,
                "baseline_sha256": "9" * 64,
                "post_id": None,
            }
        }
        manifest["rendered_document_slugs"] = sorted(documents)
        inputs["expected_shared_readback_sha256"] = {"theme": theme_sha}
    desired = {
        **publication.document_projection(documents["guide"]),
        "title": "Updated guide",
        "block_markup": inputs["artifact_bytes"]["production-guide"].decode(),
    }
    after = publication._content_after_sha256(desired, 19)
    inputs["expected_production_content_sha256"] = {"guide": after}
    examples.reseal(manifest, inputs)
    snapshot = {
        "documents": list(documents.values()),
        "all_document_baselines": {
            str(row["id"]): publication._baseline_record(row)
            for row in documents.values()
        },
        "deployment_status": {"theme": {"tree_sha256": "9" * 64}},
    }
    preparation = {
        "snapshot_name": "synthetic-snapshot.v1.json",
        "production_documents": {
            "guide": {
                "post_id": 19,
                "document": desired,
                "baseline_precondition": publication.precondition(documents["guide"]),
                "after_sha256": after,
            }
        },
    }
    inputs["audit_artifact_bytes"].update(
        {
            "live-snapshot": publication.canonical_json_bytes(snapshot),
            "candidate-preparation": port.canonical(preparation),
        }
    )
    inputs["audit_binding"] = replace(
        inputs["audit_binding"],
        artifact_bundle_sha256=examples.release._digest(
            {
                key: port.digest(raw)
                for key, raw in inputs["audit_artifact_bytes"].items()
            }
        ),
    )
    context = examples.build(manifest, inputs)
    path = (
        private
        / "incremental-candidates"
        / inputs["validated_manifest"].manifest_sha256
    )
    path.mkdir(mode=0o700)
    port.write_private_bytes(
        path, "candidate-preparation.v1.json", port.canonical(preparation)
    )
    port.write_private_bytes(
        private / "incremental-snapshots",
        preparation["snapshot_name"],
        publication.canonical_json_bytes(snapshot),
    )
    replayed = port.ReplayedCandidate(
        context, manifest, preparation, snapshot, {"synthetic": True}
    )
    loads = []

    def load(_path, **kwargs):
        loads.append(kwargs["now"])
        return replayed

    monkeypatch.setattr(port, "load_candidate", load)
    monkeypatch.setattr(publication, "validate_site_status", lambda status, **kw: None)
    monkeypatch.setattr(
        publication,
        "list_all_documents",
        lambda client, **kw: deepcopy(list(client.documents.values())),
    )
    server = SyntheticServer(documents, desired)
    if include_theme:
        server.desired_theme_tree = theme_sha
    data = {
        "path": path,
        "server": server,
        "loads": loads,
        "now": NOW,
        "context": context,
    }

    def public_result(**kwargs):
        result = {
            "schema": "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_PUBLIC_READBACK_V1",
            "status": "PUBLIC_READBACK_PASSED",
            "publication_profile": "verified-incremental",
            "link_mode": "standard-api",
            "publication_authority": False,
            "measurement_collection_enabled": False,
            "release_sha256": context.sha256,
            "manifest_sha256": context.to_document()["manifest_sha256"],
            "snapshot_sha256": port.digest(publication.canonical_json_bytes(snapshot)),
            "candidate_preparation_sha256": port.digest(port.canonical(preparation)),
            "theme_tree_sha256": server.theme_tree,
            "site_status_sha256": port.digest(
                publication.canonical_json_bytes(kwargs["site_status_readback"])
            ),
            "monetization_state": context.to_document()["monetization_state"],
        }
        return {
            **result,
            "binding_sha256": port.digest(publication.canonical_json_bytes(result)),
        }

    def execute(stage):
        return port.execute_incremental(
            path,
            stage=stage,
            implementation_execution_ids=("synthetic-implementer",),
            browser_validator=lambda **kw: {},
            public_readback_validator=data.get("public_validator", public_result),
            client_factory=lambda: server,
            deploy=server.deploy,
            clock=lambda: data["now"],
        )

    data["execute"] = execute
    return data


def test_proposal_is_not_apply_and_requires_separate_owner_approval(world):
    world["execute"]("propose")
    server = world["server"]
    assert server.proposal_count == 1 and server.apply_count == 0
    with pytest.raises(publication.PublicationFailure, match="OWNER_APPROVAL_REQUIRED"):
        world["execute"]("apply")
    assert server.apply_count == 0
    server.state = "APPROVED"
    result = world["execute"]("apply")
    receipt, _raw = port.read_json(result.parent, result.name)
    assert receipt["state"] == "PUBLISHED_AND_READBACK_VERIFIED"
    assert server.apply_count == 1


@pytest.mark.parametrize("state", ["REGISTERED", "APPROVED"])
def test_valid_existing_proposal_is_reused_without_new_mutation(world, state):
    result = world["execute"]("propose")
    world["server"].state = state
    assert world["execute"]("propose") == result
    assert world["server"].proposal_count == 1
    assert world["server"].apply_count == 0


@pytest.mark.parametrize("state", ["FAILED", "EXPIRED", "APPLIED"])
def test_terminal_existing_proposal_cannot_return_registration_success(world, state):
    world["execute"]("propose")
    world["server"].state = state
    with pytest.raises(
        publication.PublicationFailure,
        match="EXISTING_BATCH_TERMINAL_REQUIRES_RECONCILIATION",
    ):
        world["execute"]("propose")
    assert world["server"].proposal_count == 1
    assert world["server"].apply_count == 0


@pytest.mark.parametrize("state", ["REGISTERED", "APPROVED"])
@pytest.mark.parametrize("not_ready", ["precondition", "expired", "expiry_boundary"])
def test_existing_proposal_requires_live_preconditions_and_unexpired_batch(
    world, monkeypatch, state, not_ready
):
    world["execute"]("propose")
    world["server"].state = state
    original = world["server"].deploy

    def unready(command, value):
        response = original(command, value)
        if command == "publication-batch-status":
            if not_ready == "precondition":
                response["preconditions_ready"] = False
            else:
                response["expires_at_gmt"] = examples.stamp(
                    NOW - timedelta(seconds=int(not_ready == "expired"))
                )
        return response

    monkeypatch.setattr(world["server"], "deploy", unready)
    with pytest.raises(
        publication.PublicationFailure, match="EXISTING_BATCH_NOT_READY_OR_EXPIRED"
    ):
        world["execute"]("propose")
    assert world["server"].proposal_count == 1
    assert world["server"].apply_count == 0


def test_expired_already_applied_recovery_does_not_replay_sources_or_resend(world):
    world["execute"]("propose")
    world["server"].state = "APPROVED"
    world["execute"]("apply")
    count = len(world["loads"])
    world["now"] = NOW + timedelta(days=1)
    world["execute"]("apply")
    assert len(world["loads"]) == count
    assert world["server"].apply_count == 1


def test_lost_apply_response_queries_server_and_reads_back_without_resend(world):
    world["execute"]("propose")
    world["server"].state = "APPROVED"
    world["server"].lose_apply_response = True
    with pytest.raises(publication.PublicationFailure, match="SYNTHETIC_RESPONSE_LOST"):
        world["execute"]("apply")
    world["now"] = NOW + timedelta(hours=1)
    world["execute"]("apply")
    assert world["server"].apply_count == 1


def test_baseline_drift_prevents_proposal(world):
    world["server"].documents["older"]["revision_id"] += 1
    with pytest.raises(publication.PublicationFailure, match="LIVE_BASELINE_CHANGED"):
        world["execute"]("propose")
    assert world["server"].proposal_count == 0


def test_expired_new_apply_is_rejected_before_mutation(world):
    world["execute"]("propose")
    world["server"].state = "APPROVED"
    world["now"] = NOW + timedelta(hours=1)
    with pytest.raises(ValueError, match="EXPIRED"):
        world["execute"]("apply")
    assert world["server"].apply_count == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("idempotency_key", "e" * 64),
        ("after_sha256", "e" * 64),
        ("before_sha256", "e" * 64),
        ("post_id", 999),
        ("post_type", "page"),
        ("kind", "THEME_RELEASE"),
    ],
)
def test_server_proposal_identity_mismatch_blocks_before_apply(world, field, value):
    world["execute"]("propose")
    server = world["server"]
    server.state = "APPROVED"
    next(iter(server.proposal_bindings.values()))[field] = value
    with pytest.raises(publication.PublicationFailure, match="SERVER_PROPOSAL_BINDING"):
        world["execute"]("apply")
    assert server.apply_count == 0


def test_missing_server_identity_is_not_inferred_from_local_receipt(world):
    world["execute"]("propose")
    server = world["server"]
    server.state = "APPROVED"
    server.proposal_bindings.clear()
    with pytest.raises(
        publication.PublicationFailure, match="SERVER_PROPOSAL_BINDING_REQUIRED"
    ):
        world["execute"]("apply")
    assert server.apply_count == 0


def test_rehashed_expired_activation_cannot_replace_server_registered_identity(world):
    result = world["execute"]("propose")
    server = world["server"]
    server.state = "APPROVED"
    world["execute"]("apply")
    receipt, _raw = port.read_json(result.parent, result.name)
    world["now"] = NOW + timedelta(hours=4)
    envelope = receipt["release_envelope"]
    envelope["evaluated_at"] = examples.stamp(world["now"])
    envelope["expires_at"] = examples.stamp(world["now"] + timedelta(minutes=10))
    receipt["release_sha256"] = port.digest(port.canonical(envelope))
    for proposal in receipt["proposals"]:
        proposal["idempotency_key"] = publication.sha256_json(
            {"release_sha256": receipt["release_sha256"], "target": proposal["slug"]}
        )
    port.write_private_bytes(result.parent, result.name, port.canonical(receipt))
    with pytest.raises(
        publication.PublicationFailure, match="SERVER_PROPOSAL_BINDING_INVALID"
    ):
        world["execute"]("readback")
    assert server.apply_count == 1


def test_unknown_proposal_outcome_not_unconditionally_resent(world, monkeypatch):
    original = world["server"].call

    def uncertain(name, args):
        result = original(name, args)
        if name == "raos-codex-content-propose-release":
            publication.fail("SYNTHETIC_PROPOSAL_RESPONSE_LOST")
        return result

    monkeypatch.setattr(world["server"], "call", uncertain)
    with pytest.raises(publication.PublicationFailure, match="RESPONSE_LOST"):
        world["execute"]("propose")
    with pytest.raises(publication.PublicationFailure, match="REQUIRES_RECONCILIATION"):
        world["execute"]("propose")
    assert world["server"].proposal_count == 1


def test_mutated_unselected_document_blocks_readback_completion(world):
    world["execute"]("propose")
    world["server"].state = "APPROVED"
    world["execute"]("apply")
    world["server"].documents["older"]["revision_id"] += 1
    with pytest.raises(
        publication.PublicationFailure, match="UNCHANGED_COMPLEMENT_CHANGED"
    ):
        world["execute"]("readback")


def test_unchanged_theme_cannot_drift_during_readback(world):
    world["execute"]("propose")
    world["server"].state = "APPROVED"
    world["execute"]("apply")
    world["server"].theme_tree = "e" * 64
    with pytest.raises(publication.PublicationFailure, match="READBACK_THEME_CHANGED"):
        world["execute"]("readback")


def test_closed_apply_gate_blocks_mutation_but_not_applied_readback(world):
    server = world["server"]
    server.gates["content_apply"] = False
    with pytest.raises(
        publication.PublicationFailure, match="DEPLOYMENT_STATUS_INVALID"
    ):
        world["execute"]("propose")
    assert server.proposal_count == 0
    server.gates["content_apply"] = True
    world["execute"]("propose")
    server.state = "APPROVED"
    world["execute"]("apply")
    server.gates["content_apply"] = False
    world["now"] = NOW + timedelta(hours=1)
    world["execute"]("readback")


def test_generic_public_pass_does_not_mark_completion(world):
    world["execute"]("propose")
    world["server"].state = "APPROVED"
    world["public_validator"] = lambda **kwargs: {"status": "PASS"}
    with pytest.raises(
        publication.PublicationFailure, match="PUBLIC_READBACK_BINDING_INVALID"
    ):
        world["execute"]("apply")
    receipt, _ = port.read_json(world["path"], "publication-request.v1.json")
    assert receipt["state"] == "APPLIED_READBACK_PENDING"


@pytest.mark.parametrize(
    "mutation",
    ["mode", "selection", "proposal_hash", "idempotency", "unexpected_theme"],
)
def test_request_tamper_rejected_before_apply(world, mutation):
    world["execute"]("propose")
    path = world["path"]
    receipt, _ = port.read_json(path, "publication-request.v1.json")
    if mutation == "mode":
        receipt["release_envelope"]["link_mode"] = "measured-admin"
        receipt["release_sha256"] = port.digest(
            port.canonical(receipt["release_envelope"])
        )
    elif mutation == "selection":
        receipt["selected_slugs"].append("older")
    elif mutation == "proposal_hash":
        receipt["proposals"][0]["after_sha256"] = "a" * 64
    elif mutation == "idempotency":
        receipt["proposals"][0]["idempotency_key"] = "a" * 64
    elif mutation == "unexpected_theme":
        receipt["proposals"][0]["kind"] = "THEME_RELEASE"
    port.write_private_bytes(
        path, "publication-request.v1.json", port.canonical(receipt)
    )
    world["server"].state = "APPROVED"
    with pytest.raises((publication.PublicationFailure, ValueError)):
        world["execute"]("apply")
    assert world["server"].apply_count == 0


def test_cli_explicit_dispatch_preserves_legacy_default(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(
        publication,
        "execute",
        lambda *a, **kw: seen.append("legacy") or tmp_path / "receipt",
    )
    monkeypatch.setattr(
        port,
        "execute_cli",
        lambda args: seen.append(args.publication_profile) or tmp_path / "receipt",
    )
    assert publication.main([]) == 0
    assert seen == ["legacy"]
    assert publication.main(["--incremental-stage", "propose"]) == 69
    assert seen == ["legacy"]
    assert (
        publication.main(
            [
                "--publication-profile",
                "verified-incremental",
                "--incremental-stage",
                "propose",
            ]
        )
        == 0
    )
    assert seen == ["legacy", "verified-incremental"]


def test_direct_cli_profile_error_is_safe_without_import_identity_traceback():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/raos_wordpress_publication_request.py"),
            "--publication-profile",
            "verified-incremental",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 69
    assert result.stderr == "RAOS_INCREMENTAL_PORT_EXPLICIT_PROFILE_INPUTS_REQUIRED\n"
    assert result.stdout == ""


@pytest.mark.parametrize(
    "extra",
    [
        [],
        ["--link-mode", "measured-admin"],
        ["--standard-api-receipt", "/not/read"],
        ["--articles", "guide"],
    ],
)
def test_cli_rejects_incomplete_or_mixed_profile_without_execution(monkeypatch, extra):
    monkeypatch.setattr(
        port, "execute_incremental", lambda *a, **kw: pytest.fail("must not execute")
    )
    arguments = publication.parser().parse_args(
        [
            "--publication-profile",
            "verified-incremental",
            "--incremental-candidate",
            "/not/read",
            *extra,
        ]
    )
    with pytest.raises(
        publication.PublicationFailure, match="EXPLICIT_PROFILE_INPUTS_REQUIRED"
    ):
        port.execute_cli(arguments)


def test_candidate_failure_happens_before_mcp_client_or_mutation(world, monkeypatch):
    monkeypatch.setattr(
        port,
        "load_candidate",
        lambda *a, **kw: publication.fail("SYNTHETIC_AUDIT_NOT_EXECUTED"),
    )
    monkeypatch.setattr(
        world["server"], "initialize", lambda: pytest.fail("must not initialize")
    )
    with pytest.raises(publication.PublicationFailure, match="AUDIT_NOT_EXECUTED"):
        world["execute"]("propose")


@pytest.mark.parametrize("world", [True], indirect=True)
def test_shared_theme_is_one_approved_batch_and_recovered_by_read_only_get(world):
    world["execute"]("propose")
    server = world["server"]
    assert len(server.theme_proposals) == 1
    assert len(server.batch["proposal_ids"]) == 2
    assert server.theme_tree != server.desired_theme_tree
    server.state = "APPROVED"
    server.lose_apply_response = True
    with pytest.raises(publication.PublicationFailure, match="RESPONSE_LOST"):
        world["execute"]("apply")
    world["now"] = NOW + timedelta(hours=1)
    result = world["execute"]("apply")
    receipt, _ = port.read_json(result.parent, result.name)
    assert receipt["state"] == "PUBLISHED_AND_READBACK_VERIFIED"
    assert receipt["apply_receipt"] is None
    assert receipt["operation_readback"]["apply_response_received"] is False
    assert len(receipt["operation_readback"]["operations"]) == 2
    assert server.apply_count == 1 and server.theme_operation_gets == 1


@pytest.mark.parametrize("world", [True], indirect=True)
def test_theme_operation_receipt_must_be_applied_and_exact(world):
    world["execute"]("propose")
    world["server"].state = "APPROVED"
    world["execute"]("apply")
    key = next(iter(world["server"].theme_proposals))
    world["server"].operations[key]["after_sha256"] = "e" * 64
    with pytest.raises(publication.PublicationFailure, match="APPLY_RECEIPT_INVALID"):
        world["execute"]("readback")
