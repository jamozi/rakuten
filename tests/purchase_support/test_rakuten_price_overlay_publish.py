"""KS-020 publisher integration: private overlay injection, readback, purge publish.

Offline only: WordPress is an in-memory fake, sockets are refused, and every Rakuten
value is synthetic (fixtures/rakuten_price_refresh). The owner checkout is a temporary
git repository holding a copy of the tracked child theme.
"""

from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import zipfile

import pytest

from raos.adapters.rakuten_price_refresh_client import (
    PrivateStore,
    scan_repository_for_overlay,
    scan_revision_for_overlay,
)
from raos.domain.editorial import rakuten_price_refresh as rpr
from scripts import build_st1704_self_hosted_theme as builder
from scripts import raos_rakuten_price_refresh as refresh_cli
from scripts import raos_wordpress_deployment_operator as operator
from scripts import raos_wordpress_direct_publish as direct
from scripts import raos_wordpress_price_overlay as price_overlay
from scripts.raos_wordpress_direct_preview import preview_plan

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures/rakuten_price_refresh"
CATALOG_BYTES = (FIXTURES / "catalog.synthetic.json").read_bytes()
RESPONSES = json.loads((FIXTURES / "responses.synthetic.json").read_text())
BODY = (FIXTURES / "body.price-free.synthetic.html").read_text()
GUIDE = "<p>合成ガイド（販売先なし）</p>\n"
RUN_ID = "ks020-synthetic-0001"
T0 = datetime(2026, 9, 15, 1, 2, 3, 456789, tzinfo=timezone.utc)
PRICE = 12340
THEME_PREFIX = price_overlay.THEME_PREFIX
KEYS = ["synthetic-comparison", "synthetic-guide"]
POST_IDS = {"synthetic-comparison": 101, "synthetic-guide": 102}
BODY_SOURCE = "changes/wordpress-direct-publish-v1/articles/{}.html"
PROFILE_SHA = "a" * 64
INITIAL_TREE = "b" * 64
WRITES = {"ensure-draft", "content-propose", "theme-propose", "authorize", "apply"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setenv("GIT_AUTHOR_DATE", "2026-09-15T00:00:00+00:00")
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-09-15T00:00:00+00:00")


def git(root, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=check
    )


# ---------------------------------------------------------------------------
# Owner checkout: tracked theme copy re-stamped by the generator's own primitives
# ---------------------------------------------------------------------------


def stamp_theme(theme_root):
    """Bind the synthetic runtime like build_st1704_self_hosted_theme --generate would."""
    payloads = {
        p.relative_to(theme_root).as_posix(): p.read_bytes()
        for p in theme_root.rglob("*")
        if p.is_file()
    }
    functions = payloads["functions.php"].decode()
    for constant, relative in builder.PHP_INTEGRITY_BINDINGS.items():
        functions = builder._replace_exact_hash_constant(
            functions, constant, hashlib.sha256(payloads[relative]).hexdigest()
        )
    payloads["functions.php"] = functions.encode()
    revision = builder._fingerprint_from_payloads(payloads)
    for constant in price_overlay.REVISION_CONSTANTS:
        functions = builder._replace_exact_hash_constant(functions, constant, revision)
    (theme_root / "functions.php").write_text(functions)
    for relative, name in builder.RUNTIME_STYLESHEET_SENTINELS.items():
        path = theme_root / relative
        path.write_text(
            builder._replace_stylesheet_revision(path.read_text(), name, revision)
        )
    assets = json.loads((theme_root / "raos-assets.v1.json").read_text())
    assets["theme_runtime_revision"] = assets["theme_source_fingerprint"] = revision
    (theme_root / "raos-assets.v1.json").write_bytes(builder._canonical_json(assets))
    contract = json.loads((theme_root / "theme-contract.v1.json").read_text())
    contract["runtime_evidence"]["revision"] = revision
    contract["runtime_evidence"]["source_fingerprint"] = revision
    (theme_root / "theme-contract.v1.json").write_bytes(
        builder._canonical_json(contract)
    )
    return revision


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    root = (tmp_path_factory.mktemp("template") / "owner").resolve()
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    (root / ".gitignore").write_text(".secrets/\n")
    # The checkpoint admits generated theme outputs (favicon.ico) through the build manifest.
    listed = git(
        ROOT, "ls-files", "-z", "--", THEME_PREFIX, "changes/build/manifest.v2.json"
    ).stdout.split(b"\0")
    for relative in (p.decode() for p in listed if p):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    theme_root = root / THEME_PREFIX
    runtime = {
        "schema": "RAOS_PURCHASE_ARTICLE_RUNTIME_V1",
        "articles": [
            {
                "slug": "synthetic-comparison",
                "post_type": "post",
                "body_sha256": rpr.body_sha256(BODY),
            },
            {
                "slug": "synthetic-guide",
                "post_type": "post",
                "body_sha256": rpr.body_sha256(GUIDE),
            },
        ],
    }
    (theme_root / price_overlay.RUNTIME_RELATIVE).write_bytes(
        rpr.serialize_runtime(runtime)
    )
    revision = stamp_theme(theme_root)
    rows = []
    for key, body in zip(KEYS, (BODY, GUIDE), strict=True):
        (root / BODY_SOURCE.format(key)).parent.mkdir(parents=True, exist_ok=True)
        (root / BODY_SOURCE.format(key)).write_text(body)
        rows.append(
            {
                "article_key": key,
                "mode": "existing",
                "post_id": POST_IDS[key],
                "post_type": "post",
                "title": key,
                "slug": key,
                "excerpt": "",
                "body_source": BODY_SOURCE.format(key),
                "taxonomies": {},
            }
        )
    registry = {
        "schema": "RAOSOwnerDirectArticlesV1",
        "profile": direct.PROFILE,
        "articles": rows,
    }
    (root / direct.REGISTRY).write_text(json.dumps(registry, indent=2) + "\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "synthetic owner checkout")
    return root, revision


@pytest.fixture
def owner(template, tmp_path):
    source, _revision = template
    root = (tmp_path / "owner").resolve()
    shutil.copytree(source, root, symlinks=True)
    (root / ".secrets").mkdir(mode=0o700)
    return root


def write_run(root, *, observed=T0, taxFlag=0, availability=1, approved=None):
    """Overlay and approval exactly as fetch/apply leave them (0600 under .secrets)."""
    plan = rpr.build_plan(json.loads(CATALOG_BYTES), rpr.sha256_hex(CATALOG_BYTES))
    entry = next(
        e for e in rpr.validate_plan(plan) if e.offer_id == "synthetic-single"
    )
    row = {**deepcopy(RESPONSES["row_single"]), "taxFlag": taxFlag}
    row["availability"] = availability
    body = json.dumps({"count": 1, "page": 1, "hits": 1, "items": [row]})
    result = rpr.classify_observation(entry, 200, body, observed)
    overlay = rpr.build_overlay(
        RUN_ID, "a" * 64, [result], observed + timedelta(minutes=5)
    )
    store = PrivateStore(root)
    directory = store.run_directory(RUN_ID)
    store.write_json(
        directory / "approval.v1.json",
        rpr.new_approval(RUN_ID, "a" * 64, approved or observed - timedelta(minutes=1)),
    )
    store.write_json(directory / "overlay.v1.json", overlay)
    return overlay


def approval_record(root):
    return json.loads(
        (root / ".secrets/rakuten-price-refresh" / RUN_ID / "approval.v1.json").read_text()
    )


class FakeWordPress:
    """In-memory owner-direct endpoint: proposals apply documents and the theme tree."""

    def __init__(self, root, *, store_body=None, store_tree=None, fail_apply_once=False):
        self.docs = {
            POST_IDS[key]: {
                "id": POST_IDS[key],
                "status": "publish",
                "post_type": "post",
                "title": key,
                "slug": key,
                "excerpt": "",
                "block_markup": (root / BODY_SOURCE.format(key)).read_text(),
                "taxonomies": {},
                "media_ids": [],
                "revision_id": 1,
                "modified_gmt": "2026-09-14T00:00:00Z",
                "content_sha256": "c" * 64,
            }
            for key in KEYS
        }
        self.tree = INITIAL_TREE
        self.proposals = {}
        self.applied = set()
        self.calls = []
        self.packages = []
        self.store_body = store_body
        self.store_tree = store_tree
        self.fail_apply_once = fail_apply_once

    def __call__(self, command, body):
        self.calls.append((command, deepcopy(body)))
        if command == "status":
            return {
                "schema": "RAOSOwnerDirectStatusV1",
                "profile": direct.PROFILE,
                "enabled": True,
                "allow_new_posts": False,
                "profile_sha256": PROFILE_SHA,
                "theme": {"tree_sha256": self.tree, "version": "1.5.0"},
                "targets": [
                    {"article_key": k, "post_id": POST_IDS[k], "post_type": "post", "slug": k}
                    for k in KEYS
                ],
            }
        if command == "document":
            return deepcopy(self.docs[body["id"]])
        if command == "content-propose":
            proposal_id = hashlib.sha256(direct.encoded(body)).hexdigest()
            self.proposals[proposal_id] = ("content", body["id"], body["document"])
            return {
                "proposal": {
                    "proposal_id": proposal_id,
                    "after_sha256": direct.content_after_sha256(
                        body["document"], body["id"]
                    ),
                }
            }
        if command == "theme-propose":
            proposal_id = hashlib.sha256(direct.encoded(body)).hexdigest()
            tree = body["code_package"]["file_manifest_sha256"]
            self.proposals[proposal_id] = ("theme", tree, None)
            self.packages.append(base64.b64decode(body["package_base64"]))
            return {"proposal": {"proposal_id": proposal_id, "after_tree_sha256": tree}}
        if command == "operation-status":
            state = "APPLIED" if body["operation_id"] in self.applied else "PENDING"
            return {"operation": {"state": state}}
        if command == "authorize":
            return {"batch_token": "e" * 64, "batch_manifest_sha256": "f" * 64}
        if command == "apply":
            if self.fail_apply_once:
                self.fail_apply_once = False
                raise operator.OperatorFailure("WORDPRESS_MCP_TRANSPORT_FAILED_BEFORE_APPLY")
            for proposal_id in body["proposal_ids"]:
                kind, target, document = self.proposals[proposal_id]
                if kind == "content":
                    stored = {**self.docs[target], **deepcopy(document)}
                    if self.store_body is not None:
                        stored["block_markup"] = self.store_body(target, document)
                    stored["revision_id"] += 1
                    stored["content_sha256"] = rpr.body_sha256(stored["block_markup"])
                    self.docs[target] = stored
                else:
                    self.tree = self.store_tree(target) if self.store_tree else target
                self.applied.add(proposal_id)
            return {"state": "APPLIED"}
        if command == "finish":
            return {
                "schema": "RAOSOwnerDirectBatchResultV1",
                "profile": direct.PROFILE,
                **{k: body[k] for k in ("batch_token", "batch_manifest_sha256")},
                "members": [],
                "state": "FINALIZED",
            }
        raise AssertionError(command)

    def writes(self):
        return [c for c, _ in self.calls if c in WRITES]


@pytest.fixture
def publisher(monkeypatch):
    synced = []
    previews = []

    def verify(candidate, directory, report):
        previews.append(preview_plan(candidate, directory))

    monkeypatch.setattr(direct, "verify_preview", verify)
    monkeypatch.setattr(
        direct, "sync_git", lambda root, checkpoint: synced.append(checkpoint) or {"status": "noop"}
    )
    monkeypatch.setattr(price_overlay, "clock", lambda: T0 + timedelta(hours=1))
    return {"synced": synced, "previews": previews}


def previewed(directory, candidate):
    direct.save(
        directory / "preview.json",
        {
            "status": "PASS",
            "candidate_id": candidate["candidate_id"],
            "source_sha256": candidate["source_sha256"],
        },
    )


def prepare_overlay(root, server, **flags):
    flags = flags or {"run": RUN_ID}
    candidate, directory = direct.prepare_price_overlay(
        root, KEYS, True, server, **flags
    )
    previewed(directory, candidate)
    return candidate, directory


def publish(root, directory, candidate, server, **flags):
    return direct.publish(
        root, directory, candidate["candidate_id"], server, **flags
    )


def tree_files(directory):
    return {
        p.relative_to(directory).as_posix(): p.read_bytes()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


# ---------------------------------------------------------------------------
# Without the flag nothing changes
# ---------------------------------------------------------------------------


def test_prepare_and_publish_without_the_flag_are_byte_identical(
    template, tmp_path, monkeypatch, publisher, capsys
):
    """Direct calls (the pre-G code path) and the CLI without price flags freeze and send the same bytes."""
    source, _revision = template
    roots = []
    for name in ("direct", "cli", "overlay"):
        root = (tmp_path / name).resolve()
        shutil.copytree(source, root, symlinks=True)
        (root / ".secrets").mkdir(mode=0o700)
        roots.append(root)
    direct_root, cli_root, overlay_root = roots

    server_a = FakeWordPress(direct_root)
    candidate_a, directory_a = direct.prepare(direct_root, KEYS, True, server_a)
    previewed(directory_a, candidate_a)
    direct.publish(direct_root, directory_a, candidate_a["candidate_id"], server_a)
    capsys.readouterr()

    server_b = FakeWordPress(cli_root)
    monkeypatch.setattr(direct, "ROOT", cli_root)
    # prepare/publish bind call=invoke at definition time; invoke routes to operator.run.
    monkeypatch.setattr(
        operator, "run", lambda name, body: server_b(name.removeprefix("owner-direct-"), body)
    )
    arguments = direct.parser().parse_args(
        ["prepare", "--articles", ",".join(KEYS), "--theme"]
    )
    assert arguments.price_overlay_run is None and arguments.price_overlay_purge is None
    assert direct.execute_cli(arguments) == 0
    printed = json.loads(capsys.readouterr().out)
    assert set(printed) == {"candidate_id", "candidate_directory", "publication_ready"}
    assert printed["publication_ready"] is True
    directory_b = Path(printed["candidate_directory"])
    candidate_b = direct.load_candidate(directory_b, printed["candidate_id"])
    previewed(directory_b, candidate_b)
    original_publish = direct.publish

    def publish_without_flags(root, directory, cid, **kw):
        assert kw == {"price_overlay_run": None, "price_overlay_purge": None}
        return original_publish(root, directory, cid, **kw)

    monkeypatch.setattr(direct, "publish", publish_without_flags)
    assert direct.execute_cli(
        direct.parser().parse_args(["publish", "--candidate", printed["candidate_id"]])
    ) == 0
    capsys.readouterr()

    assert candidate_a["candidate_id"] == candidate_b["candidate_id"]
    assert "price_overlay" not in candidate_a
    assert tree_files(directory_a) == tree_files(directory_b)
    assert server_a.calls == server_b.calls
    assert server_a.docs == server_b.docs and server_a.packages == server_b.packages
    assert not (direct_root / ".secrets/rakuten-price-refresh").exists()

    # The overlay path freezes the same price-free candidate before injecting.
    write_run(overlay_root)
    overlay_candidate, _ = direct.prepare_price_overlay(
        overlay_root, KEYS, True, FakeWordPress(overlay_root), run=RUN_ID
    )
    assert overlay_candidate["price_overlay"]["base_candidate_id"] == candidate_a[
        "candidate_id"
    ]
    base = direct.load_candidate(
        overlay_root / direct.PRIVATE / candidate_a["candidate_id"],
        candidate_a["candidate_id"],
    )
    assert direct.encoded(base) == direct.encoded(candidate_a)


# ---------------------------------------------------------------------------
# Injection stays private and hashes agree
# ---------------------------------------------------------------------------


def secret_needles(root, overlay, candidate):
    theme = candidate["theme"]["descriptor"]
    bodies = [a["body_sha256"] for a in candidate["articles"] if a.get("price_overlay_injected")]
    return sorted(
        {
            *rpr.leak_needles(overlay, approval_record(root)),
            f'{rpr.ATTR_PRICE_YEN}="{PRICE}"',
            f'"price_yen":{PRICE}',
            f'"amount_yen":{PRICE}',
            candidate["candidate_id"],
            candidate["price_overlay"]["runtime_sha256"],
            candidate["price_overlay"]["theme_revision"],
            theme["file_manifest_sha256"],
            theme["package_sha256"],
            *bodies,
        }
    )


def git_hits(root, needles):
    """Every commit on every ref, the index, tracked and untracked-not-ignored files, messages."""
    revisions = git(root, "rev-list", "--all").stdout.decode().split()
    patterns = [arg for n in needles for arg in ("-e", n)]
    hits = []
    for mode in (["--untracked"], ["--cached"], [*revisions, "--"]):
        found = git(root, "grep", "-l", "-F", *patterns, *mode, check=False)
        assert found.returncode in (0, 1)
        hits += found.stdout.decode().split()
    messages = git(root, "log", "--all", "--format=%B").stdout.decode()
    hits += [n for n in needles if n in messages]
    return hits


def test_overlay_values_reach_only_the_private_candidate_never_git(owner, publisher):
    overlay = write_run(owner)
    # An uncommitted editorial change makes prepare create a real checkpoint commit.
    guide = owner / BODY_SOURCE.format("synthetic-guide")
    guide.write_text(GUIDE + "<p>更新</p>\n")
    head = git(owner, "rev-parse", "HEAD").stdout.decode().strip()
    server = FakeWordPress(owner)
    candidate, directory = prepare_overlay(owner, server)
    checkpoint = candidate["checkpoint"]["commit"]
    assert candidate["checkpoint"]["status"] == "created" and checkpoint != head

    injected = candidate["articles"][0]
    assert injected["price_overlay_injected"] is True
    assert f'{rpr.ATTR_PRICE_YEN}="{PRICE}"' in injected["document"]["block_markup"]
    assert injected["body_file"] == "bodies/synthetic-comparison.html"
    for name, expected in candidate["sources"].items():
        shown = git(owner, "show", f"{checkpoint}:{name}").stdout
        assert hashlib.sha256(shown).hexdigest() == expected
        assert (directory / "sources" / name).read_bytes() == shown
    assert "price_overlay_injected" not in candidate["articles"][1]

    publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    assert server.docs[101]["block_markup"] == injected["document"]["block_markup"]
    assert publisher["synced"] == [candidate["checkpoint"]]
    assert publisher["previews"], "preview is verified through the injected-body view"

    needles = secret_needles(owner, overlay, candidate)
    assert git_hits(owner, needles) == []
    assert scan_repository_for_overlay(owner, overlay, approval_record(owner)) == []
    assert scan_revision_for_overlay(owner, checkpoint, overlay, approval_record(owner)) == []
    status = git(owner, "status", "--porcelain").stdout.decode().splitlines()
    assert status == [" M " + BODY_SOURCE.format("synthetic-guide")]
    for path in directory.rglob("*"):
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == (0o700 if path.is_dir() else 0o600), path


def test_injected_runtime_constant_stamps_and_package_are_consistent(owner, publisher, template):
    _source, git_revision = template
    write_run(owner)
    candidate, directory = prepare_overlay(owner, FakeWordPress(owner))
    theme_root = directory / "theme"
    payloads = tree_files(theme_root)
    injected = candidate["articles"][0]["document"]["block_markup"]
    runtime = json.loads(payloads[price_overlay.RUNTIME_RELATIVE])
    assert {a["slug"]: a["body_sha256"] for a in runtime["articles"]} == {
        "synthetic-comparison": rpr.body_sha256(injected),
        "synthetic-guide": rpr.body_sha256(GUIDE),
    }
    assert candidate["articles"][0]["body_sha256"] == rpr.body_sha256(injected)
    runtime_sha = hashlib.sha256(payloads[price_overlay.RUNTIME_RELATIVE]).hexdigest()
    assert candidate["price_overlay"]["runtime_sha256"] == runtime_sha
    functions = payloads["functions.php"].decode()
    for constant, relative in builder.PHP_INTEGRITY_BINDINGS.items():
        assert f"const {constant} = '{hashlib.sha256(payloads[relative]).hexdigest()}';" in functions
    revision = builder._fingerprint_from_payloads(payloads)
    assert revision == candidate["price_overlay"]["theme_revision"] != git_revision
    for constant in price_overlay.REVISION_CONSTANTS:
        assert f"const {constant} = '{revision}';" in functions
    for relative, name in builder.RUNTIME_STYLESHEET_SENTINELS.items():
        assert f"{name}: {revision};" in payloads[relative].decode()
    assets = json.loads(payloads["raos-assets.v1.json"])
    contract = json.loads(payloads["theme-contract.v1.json"])
    assert assets["theme_runtime_revision"] == assets["theme_source_fingerprint"] == revision
    assert contract["runtime_evidence"]["revision"] == revision
    assert not any(git_revision.encode() in payload for payload in payloads.values())
    package = (directory / "theme.zip").read_bytes()
    descriptor = candidate["theme"]["descriptor"]
    manifest, manifest_sha, _, safe = operator.validate_package(
        package, kind="theme", slug=operator.THEME_SLUG, expected_version=descriptor["new_version"]
    )
    assert safe and manifest_sha == descriptor["file_manifest_sha256"]
    assert hashlib.sha256(package).hexdigest() == descriptor["package_sha256"]
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        zipped = {
            i.filename.split("/", 1)[1]: archive.read(i) for i in archive.infolist()
        }
    assert zipped == payloads
    material = {k: v for k, v in candidate.items() if k != "candidate_id"}
    assert direct.digest(direct.encoded(material)) == candidate["candidate_id"]
    # Git bytes stay price-free in the candidate sources.
    git_runtime = (owner / THEME_PREFIX / price_overlay.RUNTIME_RELATIVE).read_bytes()
    assert (directory / "sources" / THEME_PREFIX / price_overlay.RUNTIME_RELATIVE).read_bytes() == git_runtime
    assert candidate["sources"][THEME_PREFIX + "/" + price_overlay.RUNTIME_RELATIVE] == hashlib.sha256(git_runtime).hexdigest()


def test_preview_accepts_injected_bodies_only_through_their_own_hash(owner, publisher):
    write_run(owner)
    candidate, directory = prepare_overlay(owner, FakeWordPress(owner))
    with pytest.raises(ValueError, match="DIRECT_PREVIEW_BODY_CHANGED"):
        preview_plan(candidate, directory)
    assert preview_plan(price_overlay.preview_view(candidate), directory)["surfaces"]
    (directory / "bodies/synthetic-comparison.html").chmod(0o600)
    (directory / "bodies/synthetic-comparison.html").write_text(BODY)
    with pytest.raises(ValueError, match="DIRECT_PREVIEW_BODY_CHANGED"):
        preview_plan(price_overlay.preview_view(candidate), directory)


# ---------------------------------------------------------------------------
# Readback, approval unit and expiry
# ---------------------------------------------------------------------------


def test_readback_compares_the_injected_body_and_theme_hashes(owner, publisher, template, tmp_path):
    write_run(owner)
    stale_body = FakeWordPress(
        owner, store_body=lambda post_id, document: (owner / BODY_SOURCE.format(document["slug"])).read_text()
    )
    candidate, directory = prepare_overlay(owner, stale_body)
    with pytest.raises(direct.DirectFailure, match="READBACK_MISMATCH"):
        publish(owner, directory, candidate, stale_body, price_overlay_run=RUN_ID)
    record = approval_record(owner)["publish"]
    assert record["candidate_id"] == candidate["candidate_id"]
    assert record["injected_body_sha256"] == {
        "synthetic-comparison": candidate["articles"][0]["body_sha256"]
    }
    assert record["readback_verified_at"] is None

    source, _revision = template
    other = (tmp_path / "other").resolve()
    shutil.copytree(source, other, symlinks=True)
    (other / ".secrets").mkdir(mode=0o700)
    write_run(other)
    base_tree = {}
    price_free_theme = FakeWordPress(other, store_tree=lambda tree: base_tree["tree"])
    candidate, directory = prepare_overlay(other, price_free_theme)
    base = direct.load_candidate(
        other / direct.PRIVATE / candidate["price_overlay"]["base_candidate_id"],
        candidate["price_overlay"]["base_candidate_id"],
    )
    base_tree["tree"] = base["theme"]["descriptor"]["file_manifest_sha256"]
    with pytest.raises(direct.DirectFailure, match="THEME_READBACK_MISMATCH"):
        publish(other, directory, candidate, price_free_theme, price_overlay_run=RUN_ID)


def test_injected_hash_check_runs_even_if_document_readback_passes(owner, publisher, monkeypatch):
    write_run(owner)
    server = FakeWordPress(owner)
    candidate, directory = prepare_overlay(owner, server)
    monkeypatch.setattr(direct, "readback", lambda *a: {"status": "PASS"})
    server.store_body = lambda post_id, document: document["block_markup"].replace(
        str(PRICE), str(PRICE + 1)
    )
    with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_READBACK_INJECTED_HASH_MISMATCH"):
        publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    assert approval_record(owner)["publish"]["readback_verified_at"] is None


def test_successful_publish_records_the_injected_hashes_once(owner, publisher):
    write_run(owner)
    server = FakeWordPress(owner, fail_apply_once=True)
    candidate, directory = prepare_overlay(owner, server)
    with pytest.raises(operator.OperatorFailure):
        publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    # Resuming the same candidate keeps the one reserved publish.
    journal = publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    assert journal["publication_status"] == "PUBLISHED_AND_READBACK_VERIFIED"
    record = approval_record(owner)["publish"]
    assert record["injected_body_sha256"]["synthetic-comparison"] == rpr.body_sha256(
        server.docs[101]["block_markup"]
    )
    assert record["runtime_sha256"] == candidate["price_overlay"]["runtime_sha256"]
    assert record["readback_verified_at"] is not None
    assert record["source_sha256"] == candidate["source_sha256"]
    assert record["purge_publish_due_by"] == rpr.iso(T0 + timedelta(hours=24))


def test_an_approval_covers_one_publish_only(owner, publisher):
    write_run(owner)
    server = FakeWordPress(owner)
    first, first_directory = prepare_overlay(owner, server)
    (owner / BODY_SOURCE.format("synthetic-guide")).write_text(GUIDE + "<p>別案</p>\n")
    second, second_directory = prepare_overlay(owner, server)
    assert first["candidate_id"] != second["candidate_id"]
    (owner / BODY_SOURCE.format("synthetic-guide")).write_text(GUIDE)
    publish(owner, first_directory, first, server, price_overlay_run=RUN_ID)
    writes = len(server.writes())
    (owner / BODY_SOURCE.format("synthetic-guide")).write_text(GUIDE + "<p>別案</p>\n")
    with pytest.raises(direct.DirectFailure, match="APPROVAL_PUBLISH_ALREADY_USED"):
        publish(owner, second_directory, second, server, price_overlay_run=RUN_ID)
    assert len(server.writes()) == writes, "refused before any WordPress write"
    with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_APPROVAL_PUBLISH_ALREADY_USED"):
        direct.prepare_price_overlay(owner, KEYS, True, server, run=RUN_ID)


@pytest.mark.parametrize(
    ("elapsed", "code"),
    [
        (timedelta(hours=22, seconds=1), "OVERLAY_VALUE_EXPIRING"),
        (timedelta(hours=25), "OVERLAY_VALUE_EXPIRING"),
    ],
)
def test_an_expiring_overlay_refuses_prepare_and_publish(owner, publisher, monkeypatch, elapsed, code):
    write_run(owner)
    server = FakeWordPress(owner)
    candidate, directory = prepare_overlay(owner, server)
    monkeypatch.setattr(price_overlay, "clock", lambda: T0 + elapsed)
    with pytest.raises(direct.DirectFailure, match=code):
        publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    assert server.writes() == []
    assert approval_record(owner)["publish"] is None
    before = sorted(p.name for p in (owner / direct.PRIVATE).iterdir())
    calls = len(server.calls)
    with pytest.raises(direct.DirectFailure, match=code):
        direct.prepare_price_overlay(owner, KEYS, True, server, run=RUN_ID)
    assert len(server.calls) == calls and sorted(
        p.name for p in (owner / direct.PRIVATE).iterdir()
    ) == before, "refused before the checkpoint and any WordPress read"


def test_the_gate_runs_after_the_checkpoint_and_before_injection(owner, publisher):
    write_run(owner, availability=0)
    server = FakeWordPress(owner)
    with pytest.raises(direct.DirectFailure, match="GATE_REFUSED:SOLD_OUT_WITH_CTA"):
        direct.prepare_price_overlay(owner, KEYS, True, server, run=RUN_ID)
    injected = [
        p for p in (owner / direct.PRIVATE).rglob("candidate.json")
        if "price_overlay" in json.loads(p.read_text())
    ]
    assert injected == []


def test_a_tax_excluded_price_needs_the_theme_that_labels_it(owner, publisher):
    write_run(owner, taxFlag=1)
    server = FakeWordPress(owner)
    candidate, _directory = prepare_overlay(owner, server)
    tag = re.search(r'<div class="ps-seller"[^>]*>', candidate["articles"][0]["document"]["block_markup"]).group(0)
    assert f'{rpr.ATTR_TAX_INCLUDED}="false"' in tag
    js = owner / THEME_PREFIX / price_overlay.JS_RELATIVE
    js.write_text(js.read_text().replace(rpr.TAX_EXCLUDED_LABEL, "本体"))
    with pytest.raises(direct.DirectFailure, match="GATE_REFUSED:TAX_EXCLUDED_PRICE_UNSUPPORTED"):
        direct.prepare_price_overlay(owner, KEYS, True, server, run=RUN_ID)


def test_price_flags_bind_explicitly_to_their_candidate(owner, publisher, monkeypatch):
    write_run(owner)
    server = FakeWordPress(owner)
    candidate, directory = prepare_overlay(owner, server)
    for flags, code in (
        ({}, "PRICE_OVERLAY_FLAG_REQUIRED"),
        ({"price_overlay_purge": RUN_ID}, "PRICE_OVERLAY_RUN_MISMATCH"),
        ({"price_overlay_run": "ks020-synthetic-0002"}, "PRICE_OVERLAY_RUN_MISMATCH"),
        ({"price_overlay_run": RUN_ID, "price_overlay_purge": RUN_ID}, "PRICE_OVERLAY_FLAGS_EXCLUSIVE"),
    ):
        with pytest.raises(direct.DirectFailure, match=code):
            publish(owner, directory, candidate, server, **flags)
    assert server.writes() == []
    plain, plain_directory = direct.prepare(owner, KEYS, True, server)
    previewed(plain_directory, plain)
    with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_CANDIDATE_UNBOUND"):
        publish(owner, plain_directory, plain, server, price_overlay_run=RUN_ID)
    with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_THEME_REQUIRED"):
        direct.prepare_price_overlay(owner, KEYS, False, server, run=RUN_ID)
    arguments = direct.parser().parse_args(
        ["publish", "--candidate", "0" * 64, "--price-overlay-run", RUN_ID]
    )
    assert arguments.price_overlay_run == RUN_ID


# ---------------------------------------------------------------------------
# Purge publish
# ---------------------------------------------------------------------------


def test_purge_publish_restores_price_free_bytes_and_removes_local_copies(owner, publisher, capsys):
    overlay = write_run(owner)
    server = FakeWordPress(owner)
    with pytest.raises(direct.DirectFailure, match="APPROVAL_PURGE_WITHOUT_PUBLISH"):
        direct.prepare_price_overlay(owner, KEYS, True, server, purge=RUN_ID)
    candidate, directory = prepare_overlay(owner, server)
    base_id = candidate["price_overlay"]["base_candidate_id"]
    base = direct.load_candidate(owner / direct.PRIVATE / base_id, base_id)
    publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    frozen = owner / price_overlay.PREVIEW_PRIVATE / "theme-placeholder"
    from scripts.raos_wordpress_direct_preview import _theme_tree

    frozen = frozen.with_name("theme-" + _theme_tree(directory / "theme"))
    frozen.mkdir(parents=True)
    (frozen / "functions.php").write_text("injected copy")
    injected_needles = secret_needles(owner, overlay, candidate)
    # A plain prepare while values are live freezes the injected page as its baseline.
    stray, stray_directory = direct.prepare(owner, ["synthetic-comparison"], True, server)
    assert f'{rpr.ATTR_PRICE_YEN}=\\"{PRICE}\\"'.encode() in (stray_directory / "candidate.json").read_bytes()

    (owner / BODY_SOURCE.format("synthetic-guide")).write_text(GUIDE + "<p>後から</p>\n")
    with pytest.raises(direct.DirectFailure, match="PURGE_SOURCE_DRIFT"):
        direct.prepare_price_overlay(owner, KEYS, True, server, purge=RUN_ID)
    (owner / BODY_SOURCE.format("synthetic-guide")).write_text(GUIDE)

    purge, purge_directory = prepare_overlay(owner, server, purge=RUN_ID)
    assert purge["price_overlay"]["mode"] == "PURGE"
    assert purge["source_sha256"] == candidate["source_sha256"]
    assert [a["document"]["block_markup"] for a in purge["articles"]] == [BODY, GUIDE]
    assert purge["theme"]["descriptor"]["file_manifest_sha256"] == base["theme"]["descriptor"]["file_manifest_sha256"]
    with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_FLAG_REQUIRED"):
        publish(owner, purge_directory, purge, server)
    publish(owner, purge_directory, purge, server, price_overlay_purge=RUN_ID)

    assert server.docs[101]["block_markup"] == BODY and server.docs[102]["block_markup"] == GUIDE
    assert server.tree == base["theme"]["descriptor"]["file_manifest_sha256"]
    assert rpr.price_free_violations(server.docs[101]["block_markup"], overlay) == []
    record = approval_record(owner)
    assert record["purge_publish"]["candidate_id"] == purge["candidate_id"]
    assert record["purge_publish"]["before_expiry"] is True
    assert not directory.exists() and not frozen.exists()
    assert not (owner / direct.PRIVATE / purge["price_overlay"]["base_candidate_id"]).exists()
    assert purge_directory.exists()
    with pytest.raises(direct.DirectFailure, match="APPROVAL_PURGE_ALREADY_USED"):
        direct.prepare_price_overlay(owner, KEYS, True, server, purge=RUN_ID)

    code = refresh_cli.main(
        ["purge-expired", "--owner-checkout", str(owner), "--run-id", RUN_ID, "--include-unexpired"],
        clock=lambda: T0 + timedelta(hours=3),
    )
    report = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert code == 0
    assert not purge_directory.exists()
    redacted = approval_record(owner)
    assert redacted["purge_publish"]["candidate_id"] == "PURGED"
    assert redacted["purge_publish"]["base_candidate_id"] == "PURGED"
    assert not stray_directory.exists()
    assert report["runs"][0]["candidate_directories_deleted"] == 2
    secrets_text = b"".join(
        p.read_bytes() for p in (owner / ".secrets").rglob("*") if p.is_file()
    )
    names = " ".join(str(p) for p in (owner / ".secrets").rglob("*"))
    # The redacted approval keeps its deadlines (cache_expires_at) by design; no price,
    # observation, marker or injected hash may remain.
    deadline = overlay["cache_expires_at"]
    kept = [n for n in injected_needles if n != deadline]
    kept += [purge["candidate_id"], purge["price_overlay"]["base_candidate_id"], stray["candidate_id"]]
    for needle in kept:
        for variant in (needle, json.dumps(needle)[1:-1]):
            assert variant.encode() not in secrets_text and variant not in names, variant
    assert git_hits(owner, injected_needles) == []


def test_a_concurrent_reservation_of_the_run_is_refused_before_writes(owner, publisher):
    write_run(owner)
    server = FakeWordPress(owner)
    candidate, directory = prepare_overlay(owner, server)
    with price_overlay._approval_lock(PrivateStore(owner), RUN_ID):
        with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_APPROVAL_BUSY"):
            publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    assert server.writes() == [] and approval_record(owner)["publish"] is None
    publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    assert approval_record(owner)["publish"]["readback_verified_at"] is not None


def test_a_rehashed_candidate_with_drifted_overlay_metadata_is_refused(owner, publisher):
    """Preview already binds bodies; the id check also binds the stamps nothing else compares."""
    write_run(owner)
    server = FakeWordPress(owner)
    candidate, directory = prepare_overlay(owner, server)
    tampered = deepcopy(candidate)
    tampered["price_overlay"]["theme_revision"] = "0" * 64
    tampered["candidate_id"] = direct.digest(
        direct.encoded({k: v for k, v in tampered.items() if k != "candidate_id"})
    )
    direct.save(directory / "candidate.json", tampered)
    previewed(directory, tampered)
    with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_INJECTION_MISMATCH"):
        publish(owner, directory, tampered, server, price_overlay_run=RUN_ID)
    assert server.writes() == [] and approval_record(owner)["publish"] is None


# ---------------------------------------------------------------------------
# Theme runtime: tax-excluded label
# ---------------------------------------------------------------------------


def test_theme_labels_tax_excluded_prices_and_keeps_them_out_of_totals():
    node = shutil.which("node")
    assert node
    script = r"""
const assert = require('node:assert/strict');
const context = {module:{exports:{}}};
require('node:vm').runInNewContext(require('node:fs').readFileSync(process.argv[1],'utf8'),context);
const {pricePresentation, offerCost, budgetState, readOffer} = context.module.exports;
const checked = Date.parse('2026-09-15T01:00:00Z');
const base = {checked_at:'2026-09-15T01:00:00Z', valid_until:'2026-09-16T01:00:00Z',
  identity_verified:true, state:'AVAILABLE', condition:'new', price_yen:12340,
  shipping_yen:0, required_items_yen:0, total_scope_complete:true};
const excluded = {...base, tax_included:false};
const text = pricePresentation(excluded, checked + 1).text;
assert.match(text, /本体税別：12,340円/);
assert.doesNotMatch(text, /税込/);
assert.doesNotMatch(text, /購入総額：/);
assert.equal(offerCost(excluded, checked + 1).state, 'INCOMPLETE');
assert.equal(offerCost(excluded, checked + 1).total, null);
assert.equal(offerCost(excluded, checked + 1).subtotal, 0);
assert.equal(budgetState([excluded], 20000, checked + 1), 'UNKNOWN');
for (const offer of [{...base, tax_included:true}, base]) {
  assert.match(pricePresentation(offer, checked + 1).text, /本体税込：12,340円/);
  assert.equal(offerCost(offer, checked + 1).state, 'CURRENT');
  assert.equal(offerCost(offer, checked + 1).total, 12340);
}
const node = attrs => ({dataset: attrs, hasAttribute: n => n === 'data-ps-price-yen', getAttribute: () => '12340'});
assert.equal(readOffer(node({psTaxIncluded:'false'})).tax_included, false);
assert.equal(readOffer(node({psTaxIncluded:'true'})).tax_included, true);
assert.equal(readOffer(node({})).tax_included, null);
"""
    js = ROOT / THEME_PREFIX / price_overlay.JS_RELATIVE
    result = subprocess.run(
        [node, "-e", script, str(js)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert rpr.theme_labels_tax_excluded(js.read_text())
    assert os.environ.get("GIT_COMMITTER_DATE")


# ---------------------------------------------------------------------------
# purge-expired before the purge publish keeps the run unfinished
# ---------------------------------------------------------------------------


def test_purge_expired_without_purge_publish_keeps_blocking_and_sweeps_a_late_purge(
    owner, publisher, capsys, monkeypatch
):
    from raos.adapters.rakuten_price_refresh_client import expired_unpurged_runs

    write_run(owner)
    server = FakeWordPress(owner)
    candidate, directory = prepare_overlay(owner, server)
    publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    store = PrivateStore(owner)
    expired = T0 + timedelta(hours=25)
    purge_expired = ["purge-expired", "--owner-checkout", str(owner), "--run-id", RUN_ID]
    capsys.readouterr()
    assert refresh_cli.main(purge_expired, clock=lambda: expired) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["runs"][0]["result"] == "PURGED"
    assert rpr.ATTR_PRICE_YEN in server.docs[101]["block_markup"], "WordPress still serves values"
    assert expired_unpurged_runs(store, expired) == [RUN_ID], "local purge alone must not unblock"
    assert refresh_cli.main(purge_expired, clock=lambda: expired) == 0
    report = json.loads(capsys.readouterr().out.splitlines()[-1])["runs"][0]
    assert report["result"] == "PURGE_PUBLISH_MISSING"

    # A late purge publish freezes the live injected page as the purge candidate's baseline.
    monkeypatch.setattr(price_overlay, "clock", lambda: expired + timedelta(hours=1))
    purge, purge_directory = prepare_overlay(owner, server, purge=RUN_ID)
    publish(owner, purge_directory, purge, server, price_overlay_purge=RUN_ID)
    assert server.docs[101]["block_markup"] == BODY
    assert approval_record(owner)["purge_publish"]["before_expiry"] is False
    assert f'{rpr.ATTR_PRICE_YEN}=\\"{PRICE}\\"'.encode() in (purge_directory / "candidate.json").read_bytes()
    assert expired_unpurged_runs(store, expired) == [RUN_ID], "price-recoverable ids remain"
    capsys.readouterr()
    assert refresh_cli.main(purge_expired, clock=lambda: expired + timedelta(hours=2)) == 0
    report = json.loads(capsys.readouterr().out.splitlines()[-1])["runs"][0]
    assert (report["result"], report["candidate_directories_deleted"]) == ("ALREADY_PURGED", 1)
    assert not purge_directory.exists()
    assert approval_record(owner)["purge_publish"]["candidate_id"] == "PURGED"
    assert expired_unpurged_runs(store, expired + timedelta(hours=2)) == []
    secrets_text = b"".join(p.read_bytes() for p in (owner / ".secrets").rglob("*") if p.is_file())
    assert f'{rpr.ATTR_PRICE_YEN}=\\"{PRICE}\\"'.encode() not in secrets_text
    assert purge["candidate_id"].encode() not in secrets_text
