from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "infra/terraform/foundation/native/versions.tf"
WRAPPER = ROOT / "scripts/terraform_toolchain.sh"
CONTRACT = ROOT / "changes/st-1501/native-toolchain/contract.v1.yaml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_versions_tf_is_pin_only() -> None:
    text = _text(VERSIONS)
    assert 'required_version = "= 1.15.8"' in text
    assert 'source  = "hashicorp/aws"' in text
    assert 'version = "= 6.57.1"' in text

    forbidden_block = re.compile(
        r'^\s*(?:provider|backend|resource|data|module|output)\s+(?:"|\{)',
        re.MULTILINE,
    )
    assert forbidden_block.search(text) is None

    for forbidden in (
        "access_key",
        "secret_key",
        "account_id",
        "region =",
        "cidr",
        "kms",
    ):
        assert forbidden not in text.lower()


def test_wrapper_exposes_only_read_only_commands() -> None:
    text = _text(WRAPPER)
    assert "#!/bin/bash -p" in text
    assert "env -i" in text
    assert "[[ -L $terraform_executable" in text
    assert 'payload.get("terraform_version") != "1.15.8"' in text
    assert "Commands: version, fmt-check" in text

    for forbidden_dispatch in (
        "init)",
        "validate)",
        "plan)",
        "apply)",
        "destroy)",
        "import)",
        "refresh)",
    ):
        assert forbidden_dispatch not in text


def test_candidate_preserves_external_configuration_as_unset() -> None:
    text = _text(CONTRACT)
    assert "status: LOCAL_IMPLEMENTATION_CANDIDATE" in text
    assert "activation_enabled: false" in text
    assert "provider_calls: FORBIDDEN" in text
    assert "external_writes: FORBIDDEN" in text
    assert "cloud_provider: null" in text
    assert "production_region: null" in text
    assert "production_account_id: null" in text
    assert "state_backend: null" in text
    assert "credential_source: null" in text
    assert "resource_definitions: []" in text
    assert "apply: FORBIDDEN" in text
    assert "production: NOT_EXECUTED" in text
