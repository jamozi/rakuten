from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import cast

import pytest

from scripts import build_st0709_ai_governance_workspace as builder


ROOT = Path(__file__).resolve().parents[2]


def _json(path: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads((ROOT / path).read_bytes()))


def test_owner_generator_is_deterministic_and_no_write_check_passes() -> None:
    first = builder.build(ROOT)
    second = builder.build(ROOT)
    assert first == second
    subprocess.run(
        [sys.executable, "scripts/build_st0709_ai_governance_workspace.py", "--check"],
        cwd=ROOT,
        check=True,
        env=os.environ
        | {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": "python:.",
        },
    )


def test_fixture_and_manifest_hashes_bind_every_output_and_runtime_source() -> None:
    fixture = (ROOT / builder.FIXTURE_PATH).read_bytes()
    assert fixture.endswith(b"\n")
    assert fixture == builder._canonical(json.loads(fixture)) + b"\n"
    manifest = _json(builder.MANIFEST_PATH.as_posix())
    manifest_hash = cast(str, manifest.pop("manifestSha256"))
    assert hashlib.sha256(builder._canonical(manifest)).hexdigest() == manifest_hash
    for raw in cast(list[dict[str, object]], manifest["runtimeSources"]):
        payload = (ROOT / cast(str, raw["path"])).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == raw["sha256"]
    outputs = cast(list[dict[str, object]], manifest["outputs"])
    assert outputs[0]["sha256"] == hashlib.sha256(fixture).hexdigest()
    assert (
        outputs[1]["sha256"]
        == hashlib.sha256((ROOT / builder.TYPESCRIPT_PATH).read_bytes()).hexdigest()
    )


def test_projection_uses_exact_recorded_reports_and_preserves_unknown_cost() -> None:
    fixture = _json(builder.FIXTURE_PATH.as_posix())
    sections = {
        cast(str, item["id"]): item
        for item in cast(list[dict[str, object]], fixture["sections"])
    }
    evaluation = cast(
        list[dict[str, object]],
        cast(dict[str, object], sections["EVALUATION"]["table"])["rows"],
    )[0]
    release = cast(
        list[dict[str, object]],
        cast(dict[str, object], sections["RELEASE"]["table"])["rows"],
    )[0]
    costs = cast(
        list[dict[str, object]],
        cast(dict[str, object], sections["COST"]["table"])["rows"],
    )
    assert evaluation["reportSha256"] == (
        "e583af1ef694facb6441fa9d9bbd06be4e4238b8aaa3636c6e642bc379b13566"
    )
    assert evaluation["outcome"] == "REFUSED_INCOMPLETE_EVIDENCE"
    assert release["reportSha256"] == (
        "c9d40408ce6e83ae04b2c5793d80bd3d556cbb6ed7ebac5876e749d9e435203e"
    )
    assert release["outcome"] == "REFUSED_INCOMPLETE_EVIDENCE"
    assert release["authority"] == "NONE"
    assert all(
        value is False
        for value in cast(dict[str, object], release["operationalAuthority"]).values()
    )
    assert len(costs) == 12
    assert all(item["observedActualCostJpy"] is None for item in costs)
    assert all(item["unknownTreatedAsZero"] is False for item in costs)


def test_v1_bytes_and_restricted_projection_fields_are_unchanged_or_absent() -> None:
    assert (
        hashlib.sha256(
            (ROOT / "packages/web-ui/src/ai-governance-workspace.ts").read_bytes()
        ).hexdigest()
        == "07b240c8f127ec3676b7d111778f27a9eca0e288ed866e177be077e733b84875"
    )
    fixture = _json(builder.FIXTURE_PATH.as_posix())
    restricted = {
        "credential",
        "jobArtifact",
        "personalData",
        "promptBody",
        "providerResponse",
        "rawPrompt",
        "rawSource",
        "reviewBody",
        "secret",
    }

    def visit(value: object) -> None:
        if type(value) is dict:
            candidate = cast(dict[str, object], value)
            assert restricted.isdisjoint(candidate)
            for item in candidate.values():
                visit(item)
        elif type(value) is list:
            for item in cast(list[object], value):
                visit(item)

    visit(fixture)


def test_duplicate_json_and_source_hash_drift_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(
        builder.St0709BuildError, match="^ST0709_AI_GOVERNANCE_BUILD_FAILED$"
    ):
        builder._parse_json(b'{"duplicate":1,"duplicate":2}')

    original = builder._read_regular

    def changed(root: Path, relative: Path) -> bytes:
        payload = original(root, relative)
        if relative == Path("changes/st-0701/generated/ai-task-registry.v1.json"):
            return payload + b" "
        return payload

    monkeypatch.setattr(builder, "_read_regular", changed)
    with pytest.raises(
        builder.St0709BuildError, match="^ST0709_AI_GOVERNANCE_BUILD_FAILED$"
    ):
        builder.build(ROOT)


def test_owner_check_refuses_symlink_and_multiple_link_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    output = root / "output.json"
    expected = b'{"safe":true}\n'
    output.write_bytes(expected)
    monkeypatch.setattr(builder, "REPO_ROOT", root)
    builder._check(((output, expected),))

    foreign = tmp_path / "foreign.json"
    foreign.write_bytes(expected)
    output.unlink()
    output.symlink_to(foreign)
    with pytest.raises(
        builder.St0709BuildError, match="^ST0709_AI_GOVERNANCE_BUILD_FAILED$"
    ):
        builder._check(((output, expected),))

    output.unlink()
    os.link(foreign, output)
    with pytest.raises(
        builder.St0709BuildError, match="^ST0709_AI_GOVERNANCE_BUILD_FAILED$"
    ):
        builder._check(((output, expected),))
