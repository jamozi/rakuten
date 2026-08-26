"""ST-0105 integration checks against the shared generator runner."""

from __future__ import annotations

import json

from .support import REPOSITORY_ROOT


def test_codegen_owner_is_registered_once_in_manifest_v2() -> None:
    manifest = json.loads(
        (REPOSITORY_ROOT / "changes/build/manifest.v2.json").read_text(
            encoding="utf-8"
        )
    )
    owners = [
        owner
        for owner in manifest["owners"]
        if owner["owner_id"] == "build_st0105_generated_contracts"
    ]
    assert len(owners) == 1
    owner = owners[0]
    assert owner["owner_version"] == 2
    assert owner["story_ids"] == ["ST-0105"]
    assert any(
        item["uri"] == "repo://scripts/build_st0105_generated_contracts.py"
        for item in owner["semantic_inputs"]
    )


def test_codegen_is_reached_through_unified_commands_only() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    for target in ("generate", "check", "fast", "final"):
        assert f"{target}:" in makefile
    for obsolete in (
        "contract-codegen-hydrate",
        "contract-codegen-install",
        "contract-codegen-check",
        "contract-codegen-test",
        "contract-codegen-typecheck",
        "contract-codegen-gate",
    ):
        assert f"{obsolete}:" not in makefile


def test_manifest_v2_has_no_absolute_command_or_approval_authority() -> None:
    manifest_text = (
        REPOSITORY_ROOT / "changes/build/manifest.v2.json"
    ).read_text(encoding="utf-8")
    lowered = manifest_text.lower()
    assert '"command"' not in lowered
    assert '"approval_authority"' not in lowered
    assert '"approval_token"' not in lowered
    assert "approved_base" not in lowered
    assert "/home/" not in manifest_text


def test_every_tracked_owner_has_outputs_and_output_ownership_is_unique() -> None:
    manifest = json.loads(
        (REPOSITORY_ROOT / "changes/build/manifest.v2.json").read_text(
            encoding="utf-8"
        )
    )
    # The baseline inventory may grow as new product owners are added. The
    # ownership and graph invariants below are the stable contract.
    assert len(manifest["owners"]) >= 134
    tracked = [
        owner for owner in manifest["owners"] if owner["output_scope"] == "tracked"
    ]
    assert all(owner["outputs"] for owner in tracked)
    output_uris = [row["uri"] for owner in tracked for row in owner["outputs"]]
    assert len(output_uris) == len(set(output_uris))
    private = [
        owner
        for owner in manifest["owners"]
        if owner["output_scope"] == "owner_private"
    ]
    assert {owner["owner_id"] for owner in private} == {
        "build_st1703_self_hosted_runtime_manifest",
        "build_st1703_self_hosted_theme",
        "build_st1704_self_hosted_theme",
    }
