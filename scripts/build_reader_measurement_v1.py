#!/usr/bin/env python3
"""Own the closed reader contract, integrity manifest and private review package.

No network, publication, installation, approval or other owner's regeneration.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "python")]
from raos.application.editorial.reader_experience_projection import project_registered_article  # noqa: E402
from raos.application.editorial.reader_html import fragment  # noqa: E402

SLICE = Path("changes/reader-measurement-v1")
PLUGIN_SLUG = "raos-reader-measurement"
PLUGIN_VERSION = "1.0.0"
PLUGIN_ROOT = ROOT / SLICE / "wordpress-plugin" / PLUGIN_SLUG
ALLOWLIST_PATH = SLICE / "wordpress-plugin" / PLUGIN_SLUG / "config/reader-allowlist.v1.json"
RUNTIME_PATH = SLICE / "wordpress-plugin" / PLUGIN_SLUG / "config/reader-runtime.v1.json"
MANIFEST_PATH = SLICE / "runtime-manifest.v1.json"
PRIVACY_SOURCE = Path("changes/editorial-portfolio-v3/reader-measurement-privacy.html")
BINDING_PATH = SLICE / "theme-runtime-binding.v1.json"
OUTPUT_PATHS = (ALLOWLIST_PATH, RUNTIME_PATH, MANIFEST_PATH, BINDING_PATH)
TEST_PATHS = (Path("tests/reader_measurement_v1"),)
SOURCE_PATHS = (
    Path("changes/editorial-portfolio-v3/editorial-portfolio.v3.json"),
    Path("changes/editorial-portfolio-v3/editorial-identities.v1.json"),
    Path("changes/editorial-portfolio-v3/reader-experience.v1.json"),
    Path("changes/editorial-portfolio-v2/editorial-portfolio.v2.json"),
    Path("changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json"),
    Path("changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json"),
    Path("python/raos/application/editorial/reader_experience_projection.py"),
    Path("python/raos/application/editorial/reader_experience_v1.py"),
    Path("python/raos/application/editorial/reader_components.py"),
    Path("python/raos/application/editorial/reader_html.py"),
)
RUNTIME_INPUT_PATHS = SOURCE_PATHS + (PRIVACY_SOURCE, Path("scripts/build_reader_measurement_v1.py"))
PLUGIN_FILES = (
    "README.md",
    "assets/reader-measurement.css",
    "assets/reader-measurement.js",
    "config/reader-allowlist.v1.json",
    "includes/class-reader-contract.php",
    "includes/class-reader-store.php",
    "includes/reader-measurement-maintenance.php",
    "raos-reader-measurement.php",
)
EVENTS = ("guide_navigation", "decision_check_open", "official_reference_open")
ORIGIN = "https://kurashinoshirube.com"
PACKAGE = ROOT.joinpath(".secrets/wordpress-mcp/repo-plugin-artifacts/raos-reader-measurement-v1.zip")


class BuildFailure(RuntimeError):
    pass


def fail(code):
    raise BuildFailure(code) from None


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def read_regular(path, maximum=8 * 1024 * 1024):
    path = Path(path)
    try:
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or not 0 < metadata.st_size <= maximum:
            fail("READER_SOURCE_INVALID")
        data = path.read_bytes()
    except OSError:
        fail("READER_SOURCE_UNAVAILABLE")
    if len(data) != metadata.st_size:
        fail("READER_SOURCE_CHANGED")
    return data


def local_source(path):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    try:
        relative = path.relative_to(ROOT)
        if any(p in ("", ".", "..") for p in relative.parts) or path.resolve() != path:
            fail("READER_SOURCE_PATH_INVALID")
    except ValueError:
        fail("READER_SOURCE_PATH_INVALID")
    return path


def load_json(path):
    try:
        return json.loads(read_regular(ROOT / path))
    except (ValueError, UnicodeError):
        fail("READER_SOURCE_JSON_INVALID")


def token(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", value):
        fail("READER_IDENTITY_INVALID")
    return value


def reference_bindings(hrefs, sources, bound_refs):
    """Only article-bound, dated official identities whose exact URLs render."""
    if any(ref not in sources for ref in bound_refs):
        fail("READER_UNKNOWN_SOURCE_REF")
    result = []
    for ref in sorted(bound_refs):
        row = sources[ref]
        if row.get("authority") not in {"MANUFACTURER_OFFICIAL", "CARRIER_OFFICIAL", "GOVERNMENT_OFFICIAL"}:
            continue
        url = row.get("url")
        if not isinstance(url, str) or not url.startswith("https://") or not row.get("retrieved_on"):
            continue
        if url in hrefs:
            result.append({"source_ref": token(ref), "url": url})
    if len({r["url"] for r in result}) != len(result):
        fail("READER_SOURCE_URL_AMBIGUOUS")
    return result


def generated_allowlist():
    portfolio = load_json(SOURCE_PATHS[0])
    identities = load_json(SOURCE_PATHS[1])
    experience = load_json(SOURCE_PATHS[2])
    registry = load_json(SOURCE_PATHS[4])
    rows = portfolio.get("articles", [])
    if portfolio.get("schema") != "RAOS_EDITORIAL_PORTFOLIO_V3" or portfolio.get("target_origin") != ORIGIN or len(rows) != 10:
        fail("READER_PORTFOLIO_INVALID")
    ids = {token(row["article_id"]) for row in rows}
    if len(ids) != 10 or ids != {row["article_id"] for row in identities["articles"]} or ids != set(experience["articles"]):
        fail("READER_ARTICLE_SET_INVALID")
    products = {p["product_id"] for p in portfolio["products"]}
    routes = {r["article_id"]: "/" + token(r["production_slug"]) + "/" for r in rows}
    if len(set(routes.values())) != 10 or any(path.startswith("/local-") for path in routes.values()):
        fail("READER_ROUTES_INVALID")
    sources = {s["source_ref"]: s for s in registry["sources"]}
    if len(sources) != len(registry["sources"]):
        fail("READER_SOURCE_DUPLICATE")
    packets = {p["article_id"]: p for p in registry["source_packets"]}
    articles = []
    inputs = set(SOURCE_PATHS)
    for row in rows:
        aid = row["article_id"]
        if not set(row["product_ids"]) <= products or aid not in packets:
            fail("READER_PRODUCT_IDENTITY_INVALID")
        content_path = local_source(row["content_ref"])
        inputs.add(content_path.relative_to(ROOT))
        markup = read_regular(content_path).decode("utf-8")
        rendered = fragment(project_registered_article(ROOT, markup, article_id=aid))
        markers = {n.attrs["data-raos-article-id"] for n in rendered.walk() if "data-raos-article-id" in n.attrs}
        if markers != {aid}:
            fail("READER_RENDERED_IDENTITY_INVALID")
        hrefs = {n.attrs.get("href") for n in rendered.find(tag="a")}
        navigation = []
        for link in experience["articles"][aid].get("contextual_links", []):
            target = link["target_ref"]
            if target not in ids or target == aid:
                fail("READER_NAVIGATION_IDENTITY_INVALID")
            stage = link["journey_stage"]
            if stage not in {"discover", "learn", "compare", "verify", "buy"}:
                fail("READER_NAVIGATION_STAGE_INVALID")
            actual = [n for n in rendered.find(cls="raos-contextual-related")
                      if n.attrs.get("data-journey-stage") == stage
                      and any(a.attrs.get("href") == routes[target] for a in n.find(tag="a"))]
            if actual:
                binding = {"target_article_id": target, "journey_stage": stage, "path": routes[target]}
                if binding not in navigation:
                    navigation.append(binding)
        panels = []
        for panel_id, kind, tag in (("reader-axes", "anchor", "section"), ("reader-purchase-checks", "anchor", "section"), ("reader-evidence", "details", "details")):
            matches = [n for n in rendered.walk() if n.attrs.get("id") == panel_id and n.tag == tag]
            if len(matches) > 1:
                fail("READER_PANEL_AMBIGUOUS")
            if len(matches) == 1:
                panels.append({"panel_id": panel_id, "kind": kind})
        packet = packets[aid]
        bound_refs = set(packet["source_refs"])
        bound_refs.update(ref for claim in packet["claims"] for ref in claim.get("evidence_refs", []))
        references = reference_bindings(hrefs, sources, bound_refs)
        if not references:
            fail("READER_REFERENCES_MISSING")
        articles.append({"article_id": aid, "slug": row["production_slug"],
                         "navigation": sorted(navigation, key=lambda n:(n["target_article_id"], n["journey_stage"])),
                         "panels": panels, "references": references})
    return {"schema": "RAOS_READER_MEASUREMENT_ALLOWLIST_V1", "version": PLUGIN_VERSION,
            "target_origin": ORIGIN, "events": list(EVENTS),
            "source_hashes": {str(p): sha256(read_regular(ROOT / p)) for p in sorted(inputs)},
            "articles": sorted(articles, key=lambda a:a["article_id"])}


def package_bytes(payloads):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, data in sorted(payloads.items()):
            item = zipfile.ZipInfo(PLUGIN_SLUG + "/" + path, (2026, 9, 6, 0, 0, 0))
            item.create_system = 3
            item.external_attr = (stat.S_IFREG | 0o644) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def build_artifact(privacy_source=PRIVACY_SOURCE):
    policy_path = local_source(privacy_source)
    relative_policy = policy_path.relative_to(ROOT).as_posix()
    if not relative_policy.startswith(("changes/", "tests/reader_measurement_v1/")):
        fail("READER_POLICY_SOURCE_PATH_INVALID")
    policy = read_regular(policy_path, maximum=128 * 1024)
    try:
        policy.decode("utf-8", errors="strict")
    except UnicodeError:
        fail("READER_POLICY_ENCODING_INVALID")
    if b"\r" in policy or policy.startswith(b"\xef\xbb\xbf") or b"<!-- wp:html -->" not in policy:
        fail("READER_POLICY_BLOCK_MARKUP_INVALID")
    allowlist = canonical_json(generated_allowlist())
    actual_files = {p.relative_to(PLUGIN_ROOT).as_posix() for p in PLUGIN_ROOT.rglob("*") if p.is_file() or p.is_symlink()}
    if actual_files - set(PLUGIN_FILES) - {"config/reader-runtime.v1.json"}:
        fail("READER_PLUGIN_EXTRA_FILE")
    payloads = {p: allowlist if p == "config/reader-allowlist.v1.json" else read_regular(PLUGIN_ROOT / p) for p in PLUGIN_FILES}
    hashes = {p:sha256(data) for p,data in sorted(payloads.items())}
    policy_hash = sha256(policy)
    revision = sha256(("".join(p+":"+h+"\n" for p,h in hashes.items()) + "policy:"+policy_hash+"\nversion:"+PLUGIN_VERSION+"\n").encode("utf-8"))
    runtime = {"schema":"RAOS_READER_MEASUREMENT_RUNTIME_V1", "plugin_version":PLUGIN_VERSION,
               "contract_sha256":sha256(allowlist), "policy_sha256":policy_hash,
               "policy_slug":"privacy-policy", "revision":revision, "files":hashes}
    payloads["config/reader-runtime.v1.json"] = canonical_json(runtime)
    package = package_bytes(payloads)
    source_paths = sorted(set(RUNTIME_INPUT_PATHS) - {PRIVACY_SOURCE} | {policy_path.relative_to(ROOT)})
    manifest = {
        "schema":"RAOS_READER_MEASUREMENT_RUNTIME_MANIFEST_V1", "version":"1.0.0",
        "artifact_id":"raos-reader-measurement-v1", "plugin_slug":PLUGIN_SLUG,
        "plugin_version":PLUGIN_VERSION, "default_enabled":False,
        "approval_required":True, "migration_assessment":"MANUAL_REVIEW_REQUIRED",
        "contract_sha256":sha256(allowlist), "policy_sha256":policy_hash, "revision":revision,
        "privacy_source":policy_path.relative_to(ROOT).as_posix(),
        "plugin_root":PLUGIN_ROOT.relative_to(ROOT).as_posix(),
        "maintenance_file":"includes/reader-measurement-maintenance.php",
        "package_sha256":sha256(package), "package_size":len(package),
        "plugin_files":[{"path":p,"size":len(b),"sha256":sha256(b)} for p,b in sorted(payloads.items())],
        "runtime_files":[{"path":str(p),"size":len(read_regular(ROOT/p)),"sha256":sha256(read_regular(ROOT/p))} for p in source_paths],
    }
    manifest_bytes = canonical_json(manifest)
    return manifest, {ALLOWLIST_PATH:allowlist, RUNTIME_PATH:canonical_json(runtime), MANIFEST_PATH:manifest_bytes, BINDING_PATH:theme_runtime_binding(manifest_bytes)}, package


def theme_runtime_binding(manifest_bytes):
    manifest = json.loads(manifest_bytes)
    maintenance = manifest["maintenance_file"]
    maintenance_hash = next(row["sha256"] for row in manifest["plugin_files"] if row["path"] == maintenance)
    return canonical_json({
        "schema":"RAOS_READER_MEASUREMENT_THEME_BINDING_V1",
        "plugin_slug":PLUGIN_SLUG, "plugin_version":PLUGIN_VERSION,
        "manifest_sha256":sha256(manifest_bytes),
        "contract_sha256":manifest["contract_sha256"], "policy_sha256":manifest["policy_sha256"],
        "revision":manifest["revision"], "plugin_files":manifest["plugin_files"],
        "maintenance_file":maintenance, "maintenance_sha256":maintenance_hash,
    })


def write_private_package(data):
    # This directory is provisioned by the existing manual-review tooling.
    # Refuse unsafe permissions instead of changing existing permissions.
    parent = PACKAGE.parent
    for directory in (ROOT / ".secrets", ROOT / ".secrets/wordpress-mcp", parent):
        if directory.is_symlink() or directory.resolve() != directory:
            fail("READER_PRIVATE_PACKAGE_DIRECTORY_UNAVAILABLE")
        if not directory.exists():
            directory.mkdir(mode=0o700)
    if parent.resolve() != parent or not parent.is_dir() or (parent.stat().st_mode & 0o077):
        fail("READER_PRIVATE_PACKAGE_DIRECTORY_UNAVAILABLE")
    if PACKAGE.exists():
        if PACKAGE.is_symlink() or PACKAGE.stat().st_nlink != 1 or PACKAGE.stat().st_mode & 0o077:
            fail("READER_PRIVATE_PACKAGE_INVALID")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
    descriptor = os.open(PACKAGE, flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def main(argv=None):
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true")
    group.add_argument("--check", action="store_true")
    group.add_argument("--package", action="store_true")
    parser.add_argument("--privacy-source", type=Path, default=PRIVACY_SOURCE,
                        help="Repository-local generation input only; never a runtime URL/path")
    args = parser.parse_args(argv)
    try:
        if not args.generate and args.privacy_source != PRIVACY_SOURCE:
            fail("READER_PRIVACY_OVERRIDE_GENERATION_ONLY")
        _, outputs, package = build_artifact(args.privacy_source)
        if args.check or args.package:
            for path, expected in outputs.items():
                if read_regular(ROOT/path) != expected:
                    fail("READER_GENERATED_OUTPUT_DRIFT")
        else:
            for path, data in outputs.items():
                (ROOT/path).parent.mkdir(parents=True, exist_ok=True)
                (ROOT/path).write_bytes(data)
        if args.package:
            write_private_package(package)
        print("READER_MEASUREMENT_" + ("CHECK_OK" if args.check else "PACKAGE_READY" if args.package else "GENERATED"))
        return 0
    except (BuildFailure, KeyError, ValueError, OSError) as error:
        print(str(error) if isinstance(error, BuildFailure) else "READER_BUILD_REFUSED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
