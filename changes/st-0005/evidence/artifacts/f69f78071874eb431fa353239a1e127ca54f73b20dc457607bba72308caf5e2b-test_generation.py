from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
import yaml

from scripts import build_st0205_synthetic_data as generator


def test_rendered_outputs_are_byte_deterministic_and_match_committed_bytes() -> None:
    first = generator.render_outputs()
    second = generator.render_outputs()
    assert first == second
    assert tuple(first) == generator.GENERATED_PATHS
    for path, expected in first.items():
        assert (generator.REPO_ROOT / path).read_bytes() == expected


def test_bundle_round_trip_and_catalog_generation() -> None:
    bundle_bytes = generator.render_fixture_bundle()
    loaded = json.loads(bundle_bytes)
    assert loaded == generator.build_seed_bundle()
    catalog = json.loads(generator.render_catalog(bundle_bytes))
    assert catalog["bundle"]["sha256"] == hashlib.sha256(bundle_bytes).hexdigest()
    assert catalog["bundle"]["fixture_count"] == len(generator.FIXTURE_SCENARIOS)


def test_catalog_hash_license_and_origin_are_bound_per_fixture() -> None:
    bundle = json.loads(generator.render_fixture_bundle())
    catalog = json.loads(generator.render_catalog())
    rows = {row["fixture_id"]: row for row in catalog["fixtures"]}
    assert set(rows) == {fixture["fixture_id"] for fixture in bundle["fixtures"]}
    for fixture in bundle["fixtures"]:
        content = generator._json_bytes(fixture, compact=True)
        row = rows[fixture["fixture_id"]]
        assert row["bytes"] == len(content)
        assert row["sha256"] == hashlib.sha256(content).hexdigest()
        assert row["origin"] == generator.ORIGIN
        assert row["license"] == "UNLICENSED"


def test_manifest_inventories_all_sources_and_generated_payloads() -> None:
    outputs = generator.render_outputs()
    manifest = yaml.safe_load(outputs[generator.MANIFEST_PATH])
    sources = manifest["source_artifacts"]
    generated = manifest["generated_artifacts"]
    assert manifest["source_artifact_count"] == len(generator.SOURCE_ARTIFACT_PATHS)
    assert [row["uri"] for row in sources] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_ARTIFACT_PATHS
    ]
    assert len({row["uri"] for row in sources}) == len(sources)
    assert manifest["generated_artifact_count"] == 2
    assert [row["uri"] for row in generated] == [
        f"repo://{generator.FIXTURE_BUNDLE_PATH.as_posix()}",
        f"repo://{generator.CATALOG_PATH.as_posix()}",
    ]
    for row in generated:
        path = Path(row["uri"].removeprefix("repo://"))
        content = outputs[path]
        assert row["bytes"] == len(content)
        assert row["sha256"] == hashlib.sha256(content).hexdigest()


def test_manifest_binds_both_dependency_manifests() -> None:
    manifest = yaml.safe_load(generator.render_outputs()[generator.MANIFEST_PATH])
    assert manifest["provenance"]["predecessor_manifests"] == [
        {
            "story_id": story,
            "uri": f"repo://{path.as_posix()}",
            "sha256": digest,
        }
        for story, path, digest in generator.PREDECESSOR_MANIFESTS
    ]


def test_check_mode_is_read_only_and_matches_generated_bytes() -> None:
    before = {
        path: (generator.REPO_ROOT / path).stat().st_mtime_ns
        for path in generator.GENERATED_PATHS
    }
    generator.check_generated()
    after = {
        path: (generator.REPO_ROOT / path).stat().st_mtime_ns
        for path in generator.GENERATED_PATHS
    }
    assert after == before


def test_cli_check_reports_sanitized_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert generator.main(["--check"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "domains": 13,
        "fixtures": 18,
        "generated_artifacts": 3,
        "mode": "check",
        "status": "PASS",
        "story_id": "ST-0205",
    }


def test_atomic_writer_rejects_symlink_ancestor(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, tmp_path / "changes")
    with pytest.raises((OSError, RuntimeError)):
        generator._write_artifact_atomic(
            tmp_path,
            generator.FIXTURE_BUNDLE_PATH,
            b"unsafe\n",
        )
    assert list(outside.iterdir()) == []


def test_root_make_and_readme_route_the_story_surface() -> None:
    makefile = (generator.REPO_ROOT / "Makefile").read_text()
    readme = (generator.REPO_ROOT / "README.md").read_text()
    assert (
        "synthetic-data-generate synthetic-data-check synthetic-data-test" in makefile
    )
    assert "scripts/build_st0205_synthetic_data.py --check" in makefile
    assert "tests/st0205" in makefile
    assert (
        "synthetic-data-check"
        in makefile.split("ci-repository-policy:", 1)[1].split("ci-static:", 1)[0]
    )
    assert (
        "tests/st0205" in makefile.split("ci-unit:", 1)[1].split("ci-contracts:", 1)[0]
    )
    assert "make synthetic-data-generate" in readme
    assert "make synthetic-data-check" in readme
    assert "make synthetic-data-test" in readme
