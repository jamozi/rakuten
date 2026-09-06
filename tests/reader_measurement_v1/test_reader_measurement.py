"""Offline behavior checks; the PHP wrapper runs with --network none."""
from pathlib import Path
import importlib.util
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "changes/reader-measurement-v1/wordpress-plugin/raos-reader-measurement"


def owner():
    path = ROOT / "scripts/build_reader_measurement_v1.py"
    assert path.is_file(), "reader owner generator must exist"
    spec = importlib.util.spec_from_file_location("reader_owner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_closed_generation_uses_real_rendered_targets_and_refuses_unknowns():
    build = owner()
    doc = build.generated_allowlist()
    assert len(doc["articles"]) == 10
    article = next(a for a in doc["articles"] if a["article_id"] == "st1703-first-suitcase-comparison")
    assert {"target_article_id": "lightweight-carry-on-suitcase-under-3kg", "journey_stage": "compare",
            "path": "/lightweight-carry-on-suitcase-under-3kg/"} in article["navigation"]
    assert {"source_ref": "SRC-PROTECA-TRI-AIR-01541", "url": "https://store.ace.jp/shop/g/g01541-10/"} in article["references"]
    assert {"panel_id": "reader-evidence", "kind": "details"} in article["panels"]
    assert all(not a["slug"].startswith("local-") for a in doc["articles"])
    with pytest.raises(build.BuildFailure):
        build.reference_bindings(["https://unreviewed.invalid/manual"], {}, {"SRC-UNKNOWN"})
    with pytest.raises(build.BuildFailure):
        build.reference_bindings(["https://maker.invalid/p"], {"SRC-KNOWN": {"url": "https://maker.invalid/p", "authority": "MANUFACTURER_OFFICIAL"}}, {"SRC-UNKNOWN"})


def test_private_package_is_exact_deterministic_and_rejects_changed_owned_files(tmp_path):
    build = owner()
    manifest, outputs, package = build.build_artifact()
    assert manifest["default_enabled"] is False
    assert package == build.build_artifact()[2]
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        assert sorted(archive.namelist()) == sorted("raos-reader-measurement/" + p["path"] for p in manifest["plugin_files"])
        assert not any("tests/" in p or p.endswith(".zip") for p in archive.namelist())
    bad = tmp_path / "link"
    bad.symlink_to(PLUGIN / "raos-reader-measurement.php")
    with pytest.raises(build.BuildFailure):
        build.read_regular(bad)
    result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/build_reader_measurement_v1.py"), "--check"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("harness", ["contract", "runtime", "store", "maintenance-only"])
def test_php_behavior(harness):
    php = shutil.which("php")
    assert php, "explicit local PHP runner required"
    path = ROOT / "tests/reader_measurement_v1" / (harness + ".php")
    assert path.is_file(), "behavior harness must exist"
    result = subprocess.run([php, str(path)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "behavior OK" in result.stdout


def test_browser_behavior():
    node = shutil.which("node")
    assert node, "explicit local Node runner required"
    path = ROOT / "tests/reader_measurement_v1/browser.mjs"
    assert path.is_file(), "browser behavior harness must exist"
    result = subprocess.run([node, str(path)], cwd=ROOT, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "behavior OK" in result.stdout
