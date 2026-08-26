"""Owner-generator checks for the ST-1202 V2 local runtime."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_st1202_public_event_instrumentation as builder


ROOT = Path(__file__).resolve().parents[2]


def test_expected_artifacts_are_current_and_owner_check_is_read_only() -> None:
    artifacts = builder.expected_artifacts(ROOT)
    assert tuple(path.as_posix() for path, _payload in artifacts) == (
        "changes/st-1202/generated/public-event-instrumentation-recorded.v2.json",
        "changes/st-1202/runtime-manifest.v2.yaml",
    )
    for relative, expected in artifacts:
        assert (ROOT / relative).read_bytes() == expected
    before = tuple((ROOT / path).read_bytes() for path in builder.GENERATED_PATHS)
    builder.build(ROOT, check=True)
    after = tuple((ROOT / path).read_bytes() for path in builder.GENERATED_PATHS)
    assert after == before


def test_recorded_output_keeps_actual_route_disabled_and_fixture_synthetic() -> None:
    recorded = json.loads((ROOT / builder.GENERATED_PATH).read_bytes())
    route = recorded["actualRouteBoundary"]
    assert route["mode"] == "DISABLED_OD_012"
    assert route["eligibleEventIds"] == []
    assert route["events"] == []
    assert route["effects"] == []
    assert route["networkUsed"] is False
    assert route["trackingEnabled"] is False
    fixture = recorded["recordedFixture"]
    assert fixture["mode"] == "RECORDED_TEST_ONLY"
    assert fixture["consent"]["authority"] == "UNRESOLVED_OD_012"
    assert fixture["consent"]["trackingActivation"] == "DISABLED"
    assert [event["catalogId"] for event in fixture["events"]] == list(
        builder.EXPECTED_EVENT_IDS
    )
    assert "http://" not in json.dumps(recorded)
    assert "https://" not in json.dumps(recorded)


def test_duplicate_documents_and_bound_dependency_drift_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(builder.St1202BuildError, match="^DUPLICATE_YAML_KEY$"):
        builder._parse_yaml(b"safe: 1\nsafe: 2\n")
    with pytest.raises(builder.St1202BuildError, match="^DUPLICATE_JSON_KEY$"):
        builder._parse_json(b'{"safe":1,"safe":2}')

    original = builder._read_regular

    def changed(root: Path, relative: Path, *, maximum: int = 4_000_000) -> bytes:
        payload = original(root, relative, maximum=maximum)
        if relative != Path(
            "changes/st-1004/generated/disclosure-affiliate-recorded.v2.json"
        ):
            return payload
        return payload.replace(b'"rendered": false', b'"rendered": true ', 1)

    monkeypatch.setattr(builder, "_read_regular", changed)
    with pytest.raises(builder.St1202BuildError, match="^ST1004_DEPENDENCY_DRIFT$"):
        builder.expected_artifacts(ROOT)


def test_reader_rejects_symlink_leaf_and_parent(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    regular = root / "regular.yaml"
    regular.write_bytes(b"safe: true\n")
    (root / "leaf.yaml").symlink_to(regular.name)
    with pytest.raises(builder.St1202BuildError, match="^SOURCE_LEAF_INVALID$"):
        builder._read_regular(root, Path("leaf.yaml"))

    real_parent = root / "real-parent"
    real_parent.mkdir()
    (real_parent / "source.yaml").write_bytes(b"safe: true\n")
    (root / "linked-parent").symlink_to(real_parent.name, target_is_directory=True)
    with pytest.raises(builder.St1202BuildError, match="^SOURCE_PARENT_INVALID$"):
        builder._read_regular(root, Path("linked-parent/source.yaml"))


def test_unknown_cli_does_not_write_generated_artifacts() -> None:
    before = tuple((ROOT / path).read_bytes() for path in builder.GENERATED_PATHS)
    assert builder.main(["--unknown"]) == 2
    after = tuple((ROOT / path).read_bytes() for path in builder.GENERATED_PATHS)
    assert after == before
