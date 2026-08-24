from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from scripts import build_st0807_seo_render_runtime as generator


def _walk_keys(value: object) -> tuple[str, ...]:
    keys: list[str] = []
    if type(value) is dict:
        for key, child in cast(dict[object, object], value).items():
            keys.append(str(key).casefold())
            keys.extend(_walk_keys(child))
    elif type(value) is list:
        for child in cast(list[object], value):
            keys.extend(_walk_keys(child))
    return tuple(keys)


def test_v1_renderer_and_readme_are_byte_preserved() -> None:
    expected = {
        "python/raos/domain/editorial/seo_renderer.py": generator.V1_RENDERER_SHA256,
        "changes/st-0807/README.md": (
            "841f8bc9a6cd15310d19f3be25121ef8875d51bbb0861745735b8a3b5d5caf2a"
        ),
    }
    for relative, digest in expected.items():
        assert (
            hashlib.sha256((generator.REPO_ROOT / relative).read_bytes()).hexdigest()
            == digest
        )


def test_runtime_has_no_network_provider_or_operational_write_surface() -> None:
    paths = (
        generator.GENERATOR_PATH,
        Path("python/raos/domain/editorial/seo_renderer.py"),
    )
    forbidden = (
        "import requests",
        "import httpx",
        "import socket",
        "import subprocess",
        "urllib.request",
        "def publish_article",
        "def activate",
        "def approve",
        "def update_article",
        "def delete_article",
        "wordpress",
        "wp-json",
    )
    for relative in paths:
        source = (generator.REPO_ROOT / relative).read_text(encoding="utf-8").casefold()
        assert not any(token in source for token in forbidden), relative


def test_result_carries_no_secret_body_prompt_or_finance_ranking_input(
    generated_document: dict[str, Any],
) -> None:
    keys = _walk_keys(generated_document)
    forbidden_keys = {
        "password",
        "credential",
        "secret",
        "token",
        "api_key",
        "authorization_header",
        "cookie",
        "raw_prompt",
        "article_body",
        "review_body",
        "affiliate_rate",
        "commission",
        "epc",
        "rpm",
        "revenue",
        "reward",
        "profit",
    }
    assert forbidden_keys.isdisjoint(keys)
    encoded = json.dumps(generated_document, ensure_ascii=False).casefold()
    assert "bearer " not in encoded
    assert "-----begin" not in encoded


def test_contract_and_outputs_preserve_all_external_execution_gates(
    contract: dict[str, Any],
    generated_document: dict[str, Any],
    runtime_manifest: dict[str, Any],
) -> None:
    assert set(contract["authority"].values()) == {False}
    execution = contract["execution_boundary"]
    assert execution["activation"] == "DISABLED"
    assert execution["provider_mode"] == "RECORDED_SYNTHETIC_ONLY"
    assert set(
        value
        for key, value in execution.items()
        if key not in {"activation", "provider_mode"}
    ) == {False}
    assert set(contract["verification_boundary"].values()) == {"NOT_EXECUTED"}
    assert set(generated_document["authority"].values()) == {False}
    assert set(generated_document["verification"].values()) == {"NOT_EXECUTED"}
    assert runtime_manifest["bounds"] == {
        "activation": "DISABLED",
        "provider_mode": "RECORDED_SYNTHETIC_ONLY",
        "origin_mode": "ROUTE_ONLY",
        "render_mode": "PREVIEW",
        "network": False,
        "credentials": False,
        "database": False,
        "browser": False,
        "publication": False,
        "release": False,
        "production": False,
    }
