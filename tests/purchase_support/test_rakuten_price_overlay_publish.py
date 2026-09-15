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
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
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
# What an owner-direct plugin with the price-overlay redaction reports when nothing is left.
PLUGIN_RUNTIME_REVISION = "7" * 64
RUNTIME_REVISION = re.compile(
    r"(?m)^const KURASHINOSHIRUBE_THEME_RUNTIME_REVISION = '([0-9a-f]{64})';$"
)
COMPLETE_REDACTION = [
    {"state": "COMPLETE", "runs": [RUN_ID], "post_id": 101, "proposals": 2,
     "undo_options": 2, "skipped_active": 0, "theme_proposals": 2}
]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setenv("GIT_AUTHOR_DATE", "2026-09-15T00:00:00+00:00")
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-09-15T00:00:00+00:00")


@pytest.fixture(autouse=True)
def isolated_owner_checkout(monkeypatch, tmp_path):
    """Flag-free commands check the fixed owner checkout for live runs (contract §8): point it
    at an empty location so no test reads the real one."""
    monkeypatch.setattr(operator, "OWNER_CHECKOUT", tmp_path / "fixed-owner-checkout")
    # The refresh CLI accepts only the fixed owner checkout: the temporary owner here.
    monkeypatch.setattr(refresh_cli, "OWNER_CHECKOUT", (tmp_path / "owner").resolve())


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
        functions = (root / THEME_PREFIX / "functions.php").read_text()
        self.runtime_revision = RUNTIME_REVISION.search(functions)[1]
        self.revisions = {}
        self.proposals = {}
        self.applied = set()
        self.calls = []
        self.packages = []
        self.store_body = store_body
        self.store_tree = store_tree
        self.fail_apply_once = fail_apply_once
        # What an owner-direct plugin with the price-overlay redaction reports on finalize.
        self.finish_redaction = None

    def __call__(self, command, body):
        self.calls.append((command, deepcopy(body)))
        if command == "status":
            # The shape of RAOS_Codex_MCP_Owner_Direct::status(): the theme of
            # RAOS_Codex_MCP_Deployment::status() and the plugin runtime revision.
            return {
                "schema": "RAOSOwnerDirectStatusV1",
                "profile": direct.PROFILE,
                "enabled": True,
                "allow_new_posts": False,
                "profile_sha256": PROFILE_SHA,
                "plugin_runtime_revision": PLUGIN_RUNTIME_REVISION,
                "theme": {
                    "slug": operator.THEME_SLUG,
                    "version": "1.5.0",
                    "runtime_version": "1.5.0",
                    "runtime_revision": self.runtime_revision,
                    "active": True,
                    "tree_sha256": self.tree,
                },
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
            with zipfile.ZipFile(io.BytesIO(self.packages[-1])) as archive:
                functions = archive.read(operator.THEME_SLUG + "/functions.php").decode()
            self.revisions[tree] = RUNTIME_REVISION.search(functions)[1]
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
                    self.runtime_revision = self.revisions[target]
                self.applied.add(proposal_id)
            return {"state": "APPLIED"}
        if command == "finish":
            return {
                "schema": "RAOSOwnerDirectBatchResultV1",
                "profile": direct.PROFILE,
                **{k: body[k] for k in ("batch_token", "batch_manifest_sha256")},
                "members": [],
                "state": "FINALIZED",
                **(
                    {"price_overlay_redaction": deepcopy(self.finish_redaction)}
                    if self.finish_redaction is not None
                    else {}
                ),
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
    calls = len(server.calls)
    (owner / BODY_SOURCE.format("synthetic-guide")).write_text(GUIDE + "<p>別案</p>\n")
    with pytest.raises(direct.DirectFailure, match="APPROVAL_PUBLISH_ALREADY_USED"):
        publish(owner, second_directory, second, server, price_overlay_run=RUN_ID)
    assert len(server.calls) == calls, "refused before any WordPress call, reads included"
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


def test_purge_publish_restores_price_free_bytes_and_removes_local_copies(
    owner, publisher, capsys, monkeypatch
):
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
    # A plain prepare while values are live is refused before any WordPress call: its
    # baseline would freeze the injected page or the injected theme tree.
    calls = len(server.calls)
    for keys, theme in ((["synthetic-comparison"], False), (["synthetic-guide"], True), ([], True)):
        with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_LIVE"):
            direct.prepare(owner, keys, theme, server)
    assert len(server.calls) == calls
    # One made by a publisher without that refusal still freezes the injected page.
    with monkeypatch.context() as older:
        older.setattr(direct, "refuse_while_price_overlay_live", lambda *a: None)
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
    # Without the flag it is a flag-free publish, refused while the run's values are live.
    with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_LIVE"):
        publish(owner, purge_directory, purge, server)
    publish(owner, purge_directory, purge, server, price_overlay_purge=RUN_ID)

    assert server.docs[101]["block_markup"] == BODY and server.docs[102]["block_markup"] == GUIDE
    assert server.tree == base["theme"]["descriptor"]["file_manifest_sha256"]
    assert rpr.price_free_violations(server.docs[101]["block_markup"], overlay) == []
    record = approval_record(owner)
    assert record["purge_publish"]["before_expiry"] is True
    # The purge publish sweeps every local copy that carries the run: the stray included.
    assert not directory.exists() and not frozen.exists() and not stray_directory.exists()
    assert not (owner / direct.PRIVATE / purge["price_overlay"]["base_candidate_id"]).exists()
    # The purge candidate froze the live injected pages as its baseline: the finished purge
    # publish deletes it and forgets its ids (the publish ids wait for purge-expired).
    assert not purge_directory.exists()
    assert record["purge_publish"]["candidate_id"] == "PURGED"
    assert record["purge_publish"]["base_candidate_id"] == "PURGED"
    assert record["prepared_candidates"] == {
        "PUBLISH": candidate["candidate_id"],
        "PURGE": "PURGED",
    }
    assert record["publish"]["candidate_id"] == candidate["candidate_id"]
    assert record["purge_publish"]["wordpress_redaction"] == "NOT_REPORTED"
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
    assert report["runs"][0]["candidate_directories_deleted"] == 0
    # The plugin did not report its redaction: the run stays blocked until the owner confirms.
    assert report["runs"][0]["result"] == "WORDPRESS_REDACTION_UNCONFIRMED"
    assert redacted["prepared_candidates"] == {"PUBLISH": "PURGED", "PURGE": "PURGED"}
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


def test_purge_expired_without_purge_publish_keeps_blocking_until_a_late_purge_publish(
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
    report = json.loads(capsys.readouterr().out.splitlines()[-1])["runs"][0]
    # Local values are deleted, but the run is not reported (or treated) as purged.
    assert (report["result"], report["published"], report["purge_publish_recorded"]) == (
        "PURGE_PUBLISH_MISSING",
        True,
        False,
    )
    assert rpr.ATTR_PRICE_YEN in server.docs[101]["block_markup"], "WordPress still serves values"
    assert expired_unpurged_runs(store, expired) == [RUN_ID], "local purge alone must not unblock"
    assert refresh_cli.main(purge_expired, clock=lambda: expired) == 0
    report = json.loads(capsys.readouterr().out.splitlines()[-1])["runs"][0]
    assert report["result"] == "PURGE_PUBLISH_MISSING"
    assert expired_unpurged_runs(store, expired) == [RUN_ID]

    # A late purge publish freezes the live injected page as the purge candidate's baseline;
    # finishing it deletes that candidate and its ids, which ends the obligation.
    monkeypatch.setattr(price_overlay, "clock", lambda: expired + timedelta(hours=1))
    purge, purge_directory = prepare_overlay(owner, server, purge=RUN_ID)
    assert f'{rpr.ATTR_PRICE_YEN}=\\"{PRICE}\\"'.encode() in (purge_directory / "candidate.json").read_bytes()
    server.finish_redaction = deepcopy(COMPLETE_REDACTION)
    publish(owner, purge_directory, purge, server, price_overlay_purge=RUN_ID)
    assert server.docs[101]["block_markup"] == BODY
    record = approval_record(owner)
    assert record["purge_publish"]["before_expiry"] is False
    assert record["purge_publish"]["candidate_id"] == "PURGED"
    assert record["purge_publish"]["base_candidate_id"] == "PURGED"
    assert not purge_directory.exists()
    assert expired_unpurged_runs(store, expired + timedelta(hours=1)) == []
    capsys.readouterr()
    assert refresh_cli.main(purge_expired, clock=lambda: expired + timedelta(hours=2)) == 0
    report = json.loads(capsys.readouterr().out.splitlines()[-1])["runs"][0]
    assert report == {"run_id": RUN_ID, "result": "ALREADY_PURGED"}
    secrets_text = b"".join(p.read_bytes() for p in (owner / ".secrets").rglob("*") if p.is_file())
    assert f'{rpr.ATTR_PRICE_YEN}=\\"{PRICE}\\"'.encode() not in secrets_text
    assert purge["candidate_id"].encode() not in secrets_text


def test_an_interrupted_purge_cleanup_keeps_the_run_blocked_until_purge_expired(
    owner, publisher, capsys, monkeypatch
):
    from raos.adapters.rakuten_price_refresh_client import expired_unpurged_runs, run_status

    write_run(owner)
    server = FakeWordPress(owner)
    candidate, directory = prepare_overlay(owner, server)
    publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    store = PrivateStore(owner)
    later = T0 + timedelta(hours=25)
    purge_expired = ["purge-expired", "--owner-checkout", str(owner), "--run-id", RUN_ID]
    assert refresh_cli.main(purge_expired, clock=lambda: later) == 0
    monkeypatch.setattr(price_overlay, "clock", lambda: later)
    purge, purge_directory = prepare_overlay(owner, server, purge=RUN_ID)
    server.finish_redaction = deepcopy(COMPLETE_REDACTION)

    def interrupted(_approval):
        raise OSError("interrupted after the candidate directory was deleted")

    with monkeypatch.context() as patched:
        patched.setattr(price_overlay.rpr, "redact_purge_candidates", interrupted)
        with pytest.raises(OSError):
            publish(owner, purge_directory, purge, server, price_overlay_purge=RUN_ID)
    assert server.docs[101]["block_markup"] == BODY and not purge_directory.exists()
    assert approval_record(owner)["purge_publish"]["candidate_id"] == purge["candidate_id"]
    assert run_status(store, RUN_ID)[0] == "REDACTION_PENDING"
    assert expired_unpurged_runs(store, later) == [RUN_ID]
    capsys.readouterr()
    assert refresh_cli.main(purge_expired, clock=lambda: later) == 0
    report = json.loads(capsys.readouterr().out.splitlines()[-1])["runs"][0]
    assert (report["result"], report["record_state"]) == ("ALREADY_PURGED", "REDACTION_PENDING")
    assert approval_record(owner)["purge_publish"]["candidate_id"] == "PURGED"
    assert approval_record(owner)["prepared_candidates"]["PURGE"] == "PURGED"
    assert expired_unpurged_runs(store, later) == []


# ---------------------------------------------------------------------------
# Checks right before the first WordPress write
# ---------------------------------------------------------------------------


def test_publish_refuses_a_candidate_that_no_longer_matches_the_overlay(owner, publisher):
    """The frozen candidate must equal checkpoint bytes + the overlay read right before writes."""
    write_run(owner)
    server = FakeWordPress(owner)
    candidate, directory = prepare_overlay(owner, server)
    plan = rpr.build_plan(json.loads(CATALOG_BYTES), rpr.sha256_hex(CATALOG_BYTES))
    entry = next(e for e in rpr.validate_plan(plan) if e.offer_id == "synthetic-single")
    row = deepcopy(RESPONSES["row_single"])
    for field in ("itemPrice", "itemPriceMin1", "itemPriceMax1", "itemPriceMin3", "itemPriceMax3"):
        row[field] = PRICE + 1
    body = json.dumps({"count": 1, "page": 1, "hits": 1, "items": [row]})
    result = rpr.classify_observation(entry, 200, body, T0)
    replaced = rpr.build_overlay(RUN_ID, "a" * 64, [result], T0 + timedelta(minutes=5))
    assert replaced["entries"][0]["price_yen"] == PRICE + 1
    store = PrivateStore(owner)
    store.write_json(store.run_directory(RUN_ID) / "overlay.v1.json", replaced, replace=True)
    with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_INJECTION_MISMATCH"):
        publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    assert server.writes() == []
    assert approval_record(owner)["publish"] is None


def test_purge_publish_rechecks_the_publish_record_and_price_free_bytes_before_writes(
    owner, publisher, monkeypatch
):
    write_run(owner)
    server = FakeWordPress(owner)
    candidate, directory = prepare_overlay(owner, server)
    publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    purge, purge_directory = prepare_overlay(owner, server, purge=RUN_ID)
    store = PrivateStore(owner)
    path = store.run_directory(RUN_ID) / "approval.v1.json"
    original = approval_record(owner)
    writes = len(server.writes())

    drifted = deepcopy(original)
    drifted["publish"]["source_sha256"] = "0" * 64
    store.write_json(path, drifted, replace=True)
    with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_PURGE_SOURCE_DRIFT"):
        publish(owner, purge_directory, purge, server, price_overlay_purge=RUN_ID)
    assert len(server.writes()) == writes, "refused before any WordPress write"
    store.write_json(path, original, replace=True)

    # A consistently re-hashed purge candidate that would send the injected runtime.
    theme_root = purge_directory / "theme"
    runtime = theme_root / price_overlay.RUNTIME_RELATIVE
    price_free_runtime = runtime.read_bytes()
    runtime.write_bytes((directory / "theme" / price_overlay.RUNTIME_RELATIVE).read_bytes())
    tampered = deepcopy(purge)
    tampered["theme"]["descriptor"]["file_manifest"] = [
        {
            "path": f.relative_to(theme_root).as_posix(),
            "size": f.stat().st_size,
            "sha256": direct.digest(f.read_bytes()),
        }
        for f in sorted(theme_root.rglob("*"))
        if f.is_file()
    ]
    tampered["candidate_id"] = direct.digest(
        direct.encoded({k: v for k, v in tampered.items() if k != "candidate_id"})
    )
    direct.save(purge_directory / "candidate.json", tampered)
    previewed(purge_directory, tampered)
    with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_PURGE_BODY_NOT_PRICE_FREE"):
        publish(owner, purge_directory, tampered, server, price_overlay_purge=RUN_ID)
    assert len(server.writes()) == writes, "refused before any WordPress write"
    assert approval_record(owner)["purge_publish"] is None
    runtime.write_bytes(price_free_runtime)
    direct.save(purge_directory / "candidate.json", purge)
    previewed(purge_directory, purge)

    # A site that keeps the injected body is refused even when document readback passes.
    monkeypatch.setattr(direct, "readback", lambda *a: {"status": "PASS"})
    injected = candidate["articles"][0]["document"]["block_markup"]
    server.store_body = lambda post_id, document: (
        injected if post_id == POST_IDS["synthetic-comparison"] else document["block_markup"]
    )
    with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_PURGE_READBACK_NOT_PRICE_FREE"):
        publish(owner, purge_directory, purge, server, price_overlay_purge=RUN_ID)
    assert approval_record(owner)["purge_publish"] is None
    assert purge_directory.exists(), "an unverified purge keeps its candidate for the retry"


def test_the_checkpoint_scan_refuses_a_value_committed_by_prepare(owner, publisher, monkeypatch):
    overlay = write_run(owner)
    observed = next(e for e in overlay["entries"] if rpr.carries_values(e))["observed_at"]
    (owner / BODY_SOURCE.format("synthetic-guide")).write_text(GUIDE + f"<p>{observed}</p>\n")
    scanned = []
    scan_revision = price_overlay.scan_revision_for_overlay
    # Only the checkpoint commit scan may catch it: the working tree scan is disabled here.
    monkeypatch.setattr(price_overlay, "scan_repository_for_overlay", lambda *a, **k: [])
    monkeypatch.setattr(
        price_overlay,
        "scan_revision_for_overlay",
        lambda *a, **k: scanned.append(scan_revision(*a, **k)) or scanned[-1],
    )
    server = FakeWordPress(owner)
    # The observation time in a body also reads as an injected body (BODY_ALREADY_INJECTED).
    with pytest.raises(direct.DirectFailure, match=r"GATE_REFUSED:[A-Z_,]*GIT_TRACKED_OVERLAY_VALUE"):
        direct.prepare_price_overlay(owner, KEYS, True, server, run=RUN_ID)
    frozen = [json.loads(p.read_text()) for p in (owner / direct.PRIVATE).rglob("candidate.json")]
    # Only the price-free base exists; the gate refused before any injection.
    assert [("price_overlay" in c, c["checkpoint"]["status"]) for c in frozen] == [(False, "created")]
    assert scanned and scanned[0] == [
        "OVERLAY_EXACT_VALUE:revision:"
        + frozen[0]["checkpoint"]["commit"][:12]
        + ":"
        + BODY_SOURCE.format("synthetic-guide")
    ]
    assert "prepared_candidates" not in approval_record(owner)


def test_publish_re_gates_findings_that_appear_after_prepare(owner, publisher):
    overlay = write_run(owner)
    server = FakeWordPress(owner)
    candidate, directory = prepare_overlay(owner, server)
    observed = next(e for e in overlay["entries"] if rpr.carries_values(e))["observed_at"]
    note = owner / "notes" / "price-check.txt"
    note.parent.mkdir()
    note.write_text(observed + "\n")
    with pytest.raises(direct.DirectFailure, match="GATE_REFUSED:GIT_TRACKED_OVERLAY_VALUE"):
        publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    assert server.writes() == [] and approval_record(owner)["publish"] is None
    note.unlink()
    note.parent.rmdir()

    other = "ks020-synthetic-0002"
    store = PrivateStore(owner)
    store.write_json(
        store.run_directory(other) / "approval.v1.json",
        rpr.new_approval(other, "a" * 64, T0 - timedelta(hours=30)),
    )
    with pytest.raises(direct.DirectFailure, match="GATE_REFUSED:EXPIRED_RUN_NOT_PURGED"):
        publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    assert server.writes() == [] and approval_record(owner)["publish"] is None
    with pytest.raises(direct.DirectFailure, match="GATE_REFUSED:EXPIRED_RUN_NOT_PURGED"):
        direct.prepare_price_overlay(owner, KEYS, True, server, run=RUN_ID)


def test_resuming_a_reserved_publish_near_expiry_is_refused_without_writes(
    owner, publisher, monkeypatch
):
    write_run(owner)
    server = FakeWordPress(owner, fail_apply_once=True)
    candidate, directory = prepare_overlay(owner, server)
    with pytest.raises(operator.OperatorFailure):
        publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    assert approval_record(owner)["publish"]["candidate_id"] == candidate["candidate_id"]
    writes = len(server.writes())
    monkeypatch.setattr(price_overlay, "clock", lambda: T0 + timedelta(hours=22, seconds=1))
    with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_OVERLAY_VALUE_EXPIRING"):
        publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    assert len(server.writes()) == writes
    assert approval_record(owner)["publish"]["readback_verified_at"] is None


# ---------------------------------------------------------------------------
# Flag-free publisher equals the publisher before batch G
# ---------------------------------------------------------------------------

# The main commit right before batch G (#289). Pinned instead of origin/main: once batch G is
# merged, origin/main itself carries the price-overlay flags, so a comparison with it would
# compare the code with itself (and its pre-batch-G assertion would fail on main).
PRE_BATCH_G_COMMIT = "2fac0278b3b64b46545389c083f3fcedaf5e0199"


def pre_batch_g_publisher(tmp_path, monkeypatch):
    present = git(ROOT, "cat-file", "-e", PRE_BATCH_G_COMMIT + "^{commit}", check=False)
    if present.returncode != 0:
        shallow = git(ROOT, "rev-parse", "--is-shallow-repository", check=False)
        if shallow.stdout.strip() == b"true":
            pytest.skip("shallow clone without the pinned pre-batch-G commit")
        pytest.fail("the pinned pre-batch-G commit " + PRE_BATCH_G_COMMIT + " is missing")
    archive = git(ROOT, "archive", PRE_BATCH_G_COMMIT, "scripts/raos_wordpress_direct_publish.py")
    target = tmp_path / "pre-batch-g-archive"
    target.mkdir()
    subprocess.run(["tar", "-x", "-C", str(target)], input=archive.stdout, check=True)
    # The archived module prepends its own root to sys.path; keep the test's path intact.
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec = importlib.util.spec_from_file_location(
        "pre_batch_g_raos_wordpress_direct_publish",
        target / "scripts/raos_wordpress_direct_publish.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert not hasattr(module, "prepare_price_overlay"), "the pinned commit predates batch G"
    return module


def test_flag_free_prepare_and_publish_match_the_pre_batch_g_publisher(
    template, tmp_path, monkeypatch, capsys
):
    main_publisher = pre_batch_g_publisher(tmp_path, monkeypatch)
    source, _revision = template
    runs = []
    for name, module in (("pre-batch-g", main_publisher), ("branch", direct)):
        root = (tmp_path / name).resolve()
        shutil.copytree(source, root, symlinks=True)
        (root / ".secrets").mkdir(mode=0o700)
        server = FakeWordPress(root)
        synced = []
        monkeypatch.setattr(module, "verify_preview", lambda *a: None)
        monkeypatch.setattr(
            module,
            "sync_git",
            lambda root, checkpoint, synced=synced: synced.append(checkpoint) or {"status": "noop"},
        )
        capsys.readouterr()
        candidate, directory = module.prepare(root, KEYS, True, server)
        previewed(directory, candidate)
        journal = module.publish(root, directory, candidate["candidate_id"], server)
        runs.append(
            {
                "candidate": candidate,
                "files": tree_files(directory),
                "calls": server.calls,
                "docs": server.docs,
                "packages": server.packages,
                "journal": journal,
                "synced": synced,
                "stdout": capsys.readouterr().out,
                "secrets": sorted(p.relative_to(root).as_posix() for p in (root / ".secrets").rglob("*")),
            }
        )
    main_run, branch_run = runs
    assert main_run["stdout"] and main_run["calls"]
    for key in main_run:
        assert main_run[key] == branch_run[key], key


# ---------------------------------------------------------------------------
# Output names price-overlay candidates by handle only
# ---------------------------------------------------------------------------


def test_cli_names_price_overlay_candidates_by_handle_only(owner, publisher, monkeypatch, capsys):
    write_run(owner)
    server = FakeWordPress(owner)
    monkeypatch.setattr(direct, "ROOT", owner)
    monkeypatch.setattr(
        operator, "run", lambda name, body: server(name.removeprefix("owner-direct-"), body)
    )
    from scripts import raos_wordpress_direct_preview as preview_module

    monkeypatch.setattr(
        preview_module,
        "prepare_candidate_preview",
        lambda candidate, directory: {
            "schema": "RAOSOwnerDirectPreviewV1",
            "status": "PASS",
            "candidate_id": candidate["candidate_id"],
            "source_sha256": candidate["source_sha256"],
            "runtime_sha256": "9" * 64,
        },
    )
    # A realistic sync result: only its status may be printed for a price-overlay candidate.
    sync_result = {
        "status": "pushed",
        "phase": "PUSHED",
        "branch": "synthetic-branch",
        "commit": "1" * 40,
        "checkpoint": {"commit": "2" * 40, "source_sha256": "3" * 64},
    }
    monkeypatch.setattr(direct, "sync_git", lambda root, checkpoint: deepcopy(sync_result))

    def cli(*arguments):
        assert direct.execute_cli(direct.parser().parse_args(list(arguments))) == 0
        return capsys.readouterr().out

    capsys.readouterr()
    publish_handle = f"price-overlay:{RUN_ID}:publish"
    purge_handle = f"price-overlay:{RUN_ID}:purge"
    printed = cli("prepare", "--articles", ",".join(KEYS), "--theme", "--price-overlay-run", RUN_ID)
    assert json.loads(printed) == {
        "candidate": publish_handle,
        "candidate_id": "REDACTED_PRICE_OVERLAY",
        "price_overlay": {"mode": "PUBLISH", "run_id": RUN_ID},
        "publication_ready": True,
    }
    publish_id = approval_record(owner)["prepared_candidates"]["PUBLISH"]
    assert (owner / direct.PRIVATE / publish_id / "candidate.json").is_file()
    outputs = [printed]
    outputs.append(cli("preview", "--candidate", publish_handle))
    assert json.loads((owner / direct.PRIVATE / publish_id / "preview.json").read_text())["candidate_id"] == publish_id
    outputs.append(cli("status", "--candidate", publish_handle))
    outputs.append(cli("publish", "--candidate", publish_handle, "--price-overlay-run", RUN_ID))
    assert f'{rpr.ATTR_PRICE_YEN}="{PRICE}"' in server.docs[101]["block_markup"]
    outputs.append(cli("prepare", "--articles", ",".join(KEYS), "--theme", "--price-overlay-purge", RUN_ID))
    purge_id = approval_record(owner)["prepared_candidates"]["PURGE"]
    outputs.append(cli("preview", "--candidate", purge_handle))
    server.finish_redaction = [
        {"state": "COMPLETE", "runs": [RUN_ID], "post_id": 101, "proposals": 2, "undo_options": 2, "skipped_active": 0}
    ]
    outputs.append(cli("publish", "--candidate", purge_handle, "--price-overlay-purge", RUN_ID))
    assert server.docs[101]["block_markup"] == BODY
    text = "".join(outputs)
    assert re.findall(r"[0-9a-f]{64}", text) == [], text
    printed_syncs = [
        json.loads(line)["git_sync"]
        for line in text.splitlines()
        if isinstance(json.loads(line).get("git_sync"), dict)
    ]
    assert printed_syncs == [{"status": "pushed"}, {"status": "pushed"}], text
    assert "1" * 40 not in text and "synthetic-branch" not in text and "PUSHED" not in text
    assert publish_id not in text and purge_id not in text
    assert all(json.loads(line)["candidate_id"] == "REDACTED_PRICE_OVERLAY" for line in text.splitlines())
    record = approval_record(owner)
    assert record["prepared_candidates"] == {"PUBLISH": publish_id, "PURGE": "PURGED"}
    assert record["purge_publish"]["wordpress_redaction"] == "COMPLETE"
    assert not (owner / direct.PRIVATE / purge_id).exists()

    calls = len(server.calls)
    for value, code in (
        (purge_handle, "PRICE_OVERLAY_CANDIDATE_HANDLE_UNKNOWN"),
        ("price-overlay:BAD:publish", "PRICE_OVERLAY_CANDIDATE_HANDLE_INVALID"),
    ):
        assert direct.execute_cli(direct.parser().parse_args(["status", "--candidate", value])) == 69
        assert code in capsys.readouterr().err
    assert len(server.calls) == calls


def test_an_incomplete_plugin_redaction_is_recorded_with_the_purge_publish(owner, publisher):
    write_run(owner)
    server = FakeWordPress(owner)
    candidate, directory = prepare_overlay(owner, server)
    publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    purge, purge_directory = prepare_overlay(owner, server, purge=RUN_ID)
    server.finish_redaction = [
        {"state": "COMPLETE", "runs": [RUN_ID], "post_id": 101, "proposals": 2, "undo_options": 2, "skipped_active": 0},
        {"state": "INCOMPLETE", "runs": [RUN_ID], "post_id": 102, "proposals": 0, "undo_options": 0, "skipped_active": 1},
    ]
    publish(owner, purge_directory, purge, server, price_overlay_purge=RUN_ID)
    assert approval_record(owner)["purge_publish"]["wordpress_redaction"] == "INCOMPLETE"


# ---------------------------------------------------------------------------
# While values may be live: no flag-free command, no live hash on stdout, from any checkout
# ---------------------------------------------------------------------------


def test_while_values_may_be_live_flag_free_commands_are_refused_from_a_worktree_too(
    owner, publisher, template, tmp_path, monkeypatch, capsys
):
    """Runs live in the owner checkout; the publisher and the operator often run from a
    worktree (its own .secrets, no runs), with or without --owner-checkout."""
    write_run(owner)
    server = FakeWordPress(owner)
    monkeypatch.setattr(operator, "OWNER_CHECKOUT", owner)
    monkeypatch.setattr(
        operator, "run", lambda name, body: server(name.removeprefix("owner-direct-"), body)
    )
    source, _revision = template
    worktree = (tmp_path / "worktree").resolve()
    shutil.copytree(source, worktree, symlinks=True)
    (worktree / ".secrets").mkdir(mode=0o700)
    monkeypatch.setattr(direct, "ROOT", worktree)
    # A flag-free candidate prepared in the worktree before the values went live.
    earlier, earlier_directory = direct.prepare(worktree, KEYS, True, server)
    previewed(earlier_directory, earlier)
    candidate, directory = prepare_overlay(owner, server)
    publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    injected_revision = candidate["price_overlay"]["theme_revision"]
    live_status = server("status", {})
    assert (live_status["theme"]["tree_sha256"], live_status["theme"]["runtime_revision"]) == (
        candidate["theme"]["descriptor"]["file_manifest_sha256"],
        injected_revision,
    )

    def cli(*arguments):
        code = direct.main(list(arguments))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    def listings():
        return [
            (git(r, "rev-parse", "HEAD").stdout, sorted(p.name for p in (r / direct.PRIVATE).iterdir()))
            for r in (owner, worktree)
        ]

    capsys.readouterr()
    before = listings()
    calls = len(server.calls)
    for option in ([], ["--owner-checkout", str(owner)]):
        for arguments in (
            ["prepare", "--articles", "synthetic-comparison"],
            ["prepare", "--articles", "synthetic-guide"],
            ["prepare", "--articles", "synthetic-guide", "--theme"],
            ["prepare", "--articles", "", "--theme"],
            ["publish", "--candidate", earlier["candidate_id"]],
        ):
            assert cli(*option, *arguments) == (
                69, "", "RAOS_WORDPRESS_DIRECT_PRICE_OVERLAY_LIVE\n"
            ), (option, arguments)
        code, out, _err = cli(*option, "status")
        assert code == 0 and json.loads(out) == {
            "price_overlay_live": [RUN_ID],
            "status": "REDACTED_PRICE_OVERLAY_LIVE",
        }
        # A flag-free candidate's status: no hash of any kind on stdout.
        code, out, _err = cli(*option, "status", "--candidate", earlier["candidate_id"])
        assert code == 0 and re.findall(r"[0-9a-f]{64}", out) == [], out
    assert len(server.calls) == calls, "refused before any WordPress call"
    assert listings() == before, "and before any checkpoint commit or candidate directory"
    assert not (earlier_directory / "journal.json").exists()

    # Any status output scrubbed while live: the theme subtree (tree hash and the rebound
    # runtime revision) and the plugin runtime revision become the marker.
    marker = price_overlay.LIVE_HASH_MARKER
    scrubbed = price_overlay.scrub_live_hashes(live_status)
    assert scrubbed["theme"] == {
        "slug": operator.THEME_SLUG,
        "version": "1.5.0",
        "runtime_version": "1.5.0",
        "runtime_revision": marker,
        "active": True,
        "tree_sha256": marker,
    }
    assert (scrubbed["plugin_runtime_revision"], scrubbed["profile_sha256"]) == (marker, marker)
    assert injected_revision not in json.dumps(scrubbed)
    # A runtime revision is a marker whatever its format.
    assert price_overlay.scrub_live_hashes(
        {"plugin_runtime_revision": "1.3.2-synthetic", "theme": {"runtime_revision": "r1", "slug": "s"}}
    ) == {"plugin_runtime_revision": marker, "theme": {"runtime_revision": marker, "slug": "s"}}

    # The deployment operator's read commands are refused the same way, before any request.
    with monkeypatch.context() as local:
        local.setattr(operator, "ROOT", worktree)
        local.setattr(operator, "run", lambda *a: pytest.fail("WordPress was called"))
        for command in OPERATOR_COMMANDS:
            for option in ([], ["--owner-checkout", str(owner)]):
                assert operator.main([*option, command]) == 69, command
                assert capsys.readouterr().err == "WORDPRESS_MCP_PRICE_OVERLAY_LIVE\n"

    purge, purge_directory = prepare_overlay(owner, server, purge=RUN_ID)
    server.finish_redaction = deepcopy(COMPLETE_REDACTION)
    publish(owner, purge_directory, purge, server, price_overlay_purge=RUN_ID)
    capsys.readouterr()
    code, out, _err = cli("status")
    assert code == 0 and json.loads(out) == server("status", {})
    after, _after_directory = direct.prepare(worktree, ["synthetic-comparison"], True, server)
    assert after["publication_ready"] is True
    operator.refuse_while_price_overlay_live(owner)

    # An approval record that cannot be read counts as live.
    store = PrivateStore(owner)
    store.write_json(
        store.run_directory("ks020-synthetic-0002") / "approval.v1.json", {"schema": "tampered"}
    )
    with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_LIVE"):
        direct.prepare(worktree, ["synthetic-guide"], False, server)
    # A run directory in the fixed owner checkout that is a symlink is refused too.
    linked = (tmp_path / "linked-owner").resolve()
    (linked / ".secrets").mkdir(parents=True, mode=0o700)
    (linked / ".secrets/rakuten-price-refresh").symlink_to(owner / ".secrets/rakuten-price-refresh")
    monkeypatch.setattr(operator, "OWNER_CHECKOUT", linked)
    with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_PRIVATE_PATH_UNSAFE"):
        direct.prepare(worktree, ["synthetic-guide"], False, server)
    with pytest.raises(operator.OperatorFailure, match="WORDPRESS_MCP_PRICE_OVERLAY_STATE_INVALID"):
        operator.refuse_while_price_overlay_live(None)

# ---------------------------------------------------------------------------
# While values may be live: every operator command and every bridge tool is refused
# ---------------------------------------------------------------------------

OPERATOR_COMMANDS = tuple(
    next(action for action in operator.parser()._actions if action.dest == "command").choices
)
# Every operator command except the allowlisted local ones reaches WordPress. A new command
# must be classified here; the operator refuses it while live unless it is allowlisted.
WORDPRESS_COMMANDS = frozenset(
    {
        "deployment-status",
        "operation-status",
        "publication-batch-status",
        "release-wait-and-apply",
        "theme-propose-release",
        "plugin-propose-change",
        "plugin-apply-change",
        "operation-recover",
        "owner-direct-status",
        "owner-direct-document",
        "owner-direct-ensure-draft",
        "owner-direct-content-propose",
        "owner-direct-theme-propose",
        "owner-direct-theme-propose-candidate",
        "owner-direct-authorize",
        "owner-direct-apply",
        "owner-direct-operation-status",
        "owner-direct-finish",
    }
)
SYNTHETIC = {name: char * 64 for name, char in (("a", "a"), ("b", "b"), ("c", "c"))}
BRIDGE_TOOL_INPUTS = {
    "deployment-status": {},
    "operation-status": {"operation_id": SYNTHETIC["a"]},
    "publication-batch-status": {
        "batch_token": SYNTHETIC["a"],
        "batch_manifest_sha256": SYNTHETIC["b"],
        "proposal_ids": [SYNTHETIC["c"]],
    },
    "release-wait-and-apply": {
        "batch_token": SYNTHETIC["a"],
        "batch_manifest_sha256": SYNTHETIC["b"],
        "proposal_ids": [SYNTHETIC["c"]],
    },
    "theme-propose-release": {},
    "plugin-propose-change": {
        "source": "wordpress_org",
        "slug": "synthetic-plugin",
        "version": "1.0.0",
        "activation_intent": "preserve",
    },
    "plugin-apply-change": {"proposal_id": SYNTHETIC["a"]},
    "operation-recover": {"operation_id": SYNTHETIC["a"]},
    "owner-direct-status": {},
    "owner-direct-document": {"id": 101},
    "owner-direct-ensure-draft": {
        "profile": "owner-direct-v1",
        "article_key": "synthetic-guide",
        "slug": "synthetic-guide",
        "idempotency_key": SYNTHETIC["a"],
    },
    "owner-direct-content-propose": {
        "profile": "owner-direct-v1",
        "article_key": "synthetic-guide",
        "id": 102,
        "precondition": {
            "revision_id": 1,
            "modified_gmt": "2026-09-14T00:00:00Z",
            "content_sha256": SYNTHETIC["b"],
        },
        "document": {
            "post_type": "post",
            "title": "synthetic-guide",
            "slug": "synthetic-guide",
            "excerpt": "",
            "block_markup": GUIDE,
            "taxonomies": {},
            "media_ids": [],
        },
        "idempotency_key": SYNTHETIC["a"],
    },
    "owner-direct-theme-propose-candidate": {"candidate_id": SYNTHETIC["a"]},
    "owner-direct-authorize": {
        "profile": "owner-direct-v1",
        "proposal_ids": [SYNTHETIC["a"]],
        "expected_theme_tree_sha256": INITIAL_TREE,
    },
    "owner-direct-operation-status": {"operation_id": SYNTHETIC["a"]},
    "owner-direct-apply": {
        "batch_token": SYNTHETIC["a"],
        "batch_manifest_sha256": SYNTHETIC["b"],
        "proposal_ids": [SYNTHETIC["c"]],
    },
    "owner-direct-finish": {
        "profile": "owner-direct-v1",
        "batch_token": SYNTHETIC["a"],
        "batch_manifest_sha256": SYNTHETIC["b"],
        "action": "finalize",
    },
}


def plain_owner_checkout(tmp_path):
    """A minimal owner checkout: git-ignored 0700 .secrets with the operator's private dir."""
    root = (tmp_path / "plain-owner").resolve()
    root.mkdir()
    git(root, "init", "-q")
    (root / ".gitignore").write_text(".secrets/\n")
    (root / ".secrets/wordpress-mcp").mkdir(parents=True, mode=0o700)
    (root / ".secrets").chmod(0o700)
    return root


def record_live_publish(root):
    """A run whose publish is recorded and whose purge publish is not: its values are live."""
    from raos.adapters.rakuten_price_refresh_client import live_run_ids

    overlay = write_run(root)
    store = PrivateStore(root)
    path = store.run_directory(RUN_ID) / "approval.v1.json"
    recorded = rpr.record_publish(
        store.read_json(path),
        overlay,
        candidate_id=SYNTHETIC["a"],
        article_keys=KEYS,
        injected_body_sha256={key: SYNTHETIC["b"] for key in KEYS},
        runtime_sha256=SYNTHETIC["c"],
        now=T0 + timedelta(minutes=10),
    )
    store.write_json(path, recorded, replace=True)
    assert live_run_ids([root]) == [RUN_ID]


def test_every_operator_command_is_classified_as_reaching_wordpress_or_local():
    assert operator.PRICE_OVERLAY_LOCAL_COMMANDS == {"price-overlay-live-check"}
    assert len(OPERATOR_COMMANDS) == len(set(OPERATOR_COMMANDS))
    assert not WORDPRESS_COMMANDS & operator.PRICE_OVERLAY_LOCAL_COMMANDS
    assert set(OPERATOR_COMMANDS) == WORDPRESS_COMMANDS | operator.PRICE_OVERLAY_LOCAL_COMMANDS


@pytest.mark.parametrize("state", ["live", "unreadable", "not-live"])
@pytest.mark.parametrize("owner_option", [False, True], ids=["worktree-root", "owner-checkout"])
@pytest.mark.parametrize("command", OPERATOR_COMMANDS)
def test_while_live_every_operator_command_is_refused_before_wordpress(
    tmp_path, monkeypatch, capsys, command, owner_option, state
):
    """Run from a separate worktree ROOT (its own .secrets, no runs); the run lives in the
    fixed owner checkout. Every command, read or write, is refused before any WordPress call."""
    owner = plain_owner_checkout(tmp_path)
    worktree = (tmp_path / "worktree").resolve()
    (worktree / ".secrets").mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(operator, "OWNER_CHECKOUT", owner)
    monkeypatch.setattr(operator, "ROOT", worktree)
    if state == "live":
        record_live_publish(owner)
    elif state == "unreadable":
        (owner / ".secrets/rakuten-price-refresh").write_text("")
    calls = []

    def wordpress(*arguments, **_keywords):
        calls.append(arguments)
        return {"synthetic": True}

    for name in ("run", "owner_direct_run", "request_json", "release_wait_and_apply"):
        monkeypatch.setattr(operator, name, wordpress)
    monkeypatch.setattr(operator, "read_stdin", lambda *_a: {})
    option = ["--owner-checkout", str(owner)] if owner_option else []
    capsys.readouterr()
    code = operator.main([*option, command])
    captured = capsys.readouterr()
    if state == "not-live":
        # Control: the same harness sees a WordPress call once nothing is live.
        if command in operator.PRICE_OVERLAY_LOCAL_COMMANDS:
            assert (code, calls, captured.err) == (0, [], "")
            assert json.loads(captured.out) == {"price_overlay_live": False}
        else:
            assert (code, len(calls), captured.err) == (0, 1, "")
        return
    expected = {
        "live": "WORDPRESS_MCP_PRICE_OVERLAY_LIVE",
        "unreadable": "WORDPRESS_MCP_PRICE_OVERLAY_STATE_INVALID",
    }[state]
    assert (code, captured.out, captured.err, calls) == (69, "", expected + "\n", [])


def bridge_root(tmp_path, python_source):
    """A separate checkout holding the bridge; its .venv/bin/python is the given script."""
    root = (tmp_path / "bridge-root").resolve()
    bridge = root / "packages/wordpress-mcp-bridge/src/index.ts"
    bridge.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "packages/wordpress-mcp-bridge/src/index.ts", bridge)
    (root / "node_modules").symlink_to(ROOT / "node_modules", target_is_directory=True)
    python = root / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text(python_source, encoding="utf-8")
    python.chmod(0o700)
    return root


def call_every_bridge_tool(root):
    node = shutil.which("node")
    assert node is not None
    names = sorted(BRIDGE_TOOL_INPUTS)
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1.0.0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        *(
            {
                "jsonrpc": "2.0",
                "id": index + 3,
                "method": "tools/call",
                "params": {"name": name, "arguments": BRIDGE_TOOL_INPUTS[name]},
            }
            for index, name in enumerate(names)
        ),
    ]
    completed = subprocess.run(
        [node, "--experimental-strip-types", "packages/wordpress-mcp-bridge/src/index.ts"],
        cwd=root,
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        text=True,
        capture_output=True,
        check=True,
        timeout=300,
    )
    responses = {
        response["id"]: response
        for response in map(json.loads, completed.stdout.splitlines())
        if "id" in response
    }
    # Every tool the bridge exposes is called (a new tool needs an input here).
    assert {tool["name"] for tool in responses[2]["result"]["tools"]} == set(names)
    return {name: responses[index + 3]["result"] for index, name in enumerate(names)}


FAKE_OPERATOR = """#!/usr/bin/python3
import json, pathlib, sys
here = pathlib.Path(__file__).parent
json.load(sys.stdin)
if sys.argv[-1] == "price-overlay-live-check":
    code, out, err = json.loads((here / "check.json").read_text())
    sys.stdout.write(out)
    sys.stderr.write(err)
    raise SystemExit(code)
with (here / "dispatched.jsonl").open("a") as handle:
    handle.write(json.dumps(sys.argv[3:]) + "\\n")
print("{}")
"""


@pytest.mark.parametrize(
    ("check", "expected"),
    [
        ((69, "", "WORDPRESS_MCP_PRICE_OVERLAY_LIVE\n"), "WORDPRESS_MCP_PRICE_OVERLAY_LIVE"),
        (
            (69, "", "WORDPRESS_MCP_PRICE_OVERLAY_STATE_INVALID\n"),
            "WORDPRESS_MCP_PRICE_OVERLAY_STATE_INVALID",
        ),
        ((0, '{"price_overlay_live": true}\n', ""), "WORDPRESS_MCP_PRICE_OVERLAY_STATE_INVALID"),
        ((0, '{"price_overlay_live": 0}\n', ""), "WORDPRESS_MCP_PRICE_OVERLAY_STATE_INVALID"),
        ((0, "{}\n", ""), "WORDPRESS_MCP_PRICE_OVERLAY_STATE_INVALID"),
        (
            (0, '{"price_overlay_live": false, "run_ids": []}\n', ""),
            "WORDPRESS_MCP_PRICE_OVERLAY_STATE_INVALID",
        ),
        ((0, '{"price_overlay_live": false}\n', ""), None),
    ],
    ids=["live", "state-invalid", "true", "falsy", "empty", "extra-key", "not-live"],
)
def test_the_bridge_checks_before_dispatching_any_tool(tmp_path, check, expected):
    """The bridge entry itself refuses: the operator command is never spawned unless the
    live check answers exactly {"price_overlay_live": false}."""
    root = bridge_root(tmp_path, FAKE_OPERATOR)
    (root / ".venv/bin/check.json").write_text(json.dumps(check))
    results = call_every_bridge_tool(root)
    dispatched = root / ".venv/bin/dispatched.jsonl"
    if expected is None:
        assert all(result.get("isError") is not True for result in results.values())
        commands = sorted(json.loads(line)[0] for line in dispatched.read_text().splitlines())
        assert commands == sorted(BRIDGE_TOOL_INPUTS)
        return
    assert {name: result["structuredContent"] for name, result in results.items()} == {
        name: {"code": expected} for name in BRIDGE_TOOL_INPUTS
    }
    assert all(result["isError"] is True for result in results.values())
    assert not dispatched.exists()


def test_the_bridge_with_the_real_operator_refuses_every_tool_while_live(tmp_path):
    """End to end from a separate checkout: bridge -> real operator CLI (its OWNER_CHECKOUT
    pointed at the temporary owner) with every WordPress primitive and socket recorded."""
    owner = plain_owner_checkout(tmp_path)
    record_live_publish(owner)
    guard = f"""#!{sys.executable}
import importlib.util, json, pathlib, sys
sys.dont_write_bytecode = True
here = pathlib.Path(__file__).parent
flag, operator_path, *arguments = sys.argv[1:]
assert flag == "-B"
sys.path.insert(0, str(pathlib.Path(operator_path).parent))
spec = importlib.util.spec_from_file_location("raos_wordpress_deployment_operator", operator_path)
operator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = operator
spec.loader.exec_module(operator)
operator.OWNER_CHECKOUT = pathlib.Path({str(owner)!r})

def wordpress(*_args, **_kwargs):
    with (here / "wordpress-calls.jsonl").open("a") as handle:
        handle.write(json.dumps(arguments) + "\\n")
    operator.fail("SYNTHETIC_WORDPRESS_CALLED")

operator.run = wordpress
operator.request_json = wordpress

def audit(event, _args):
    if event in ("socket.connect", "socket.getaddrinfo"):
        wordpress()

sys.addaudithook(audit)
raise SystemExit(operator.main(arguments))
"""
    root = bridge_root(tmp_path, guard)
    (root / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts/raos_wordpress_deployment_operator.py", root / "scripts")
    (root / "python").symlink_to(ROOT / "python", target_is_directory=True)
    calls = root / ".venv/bin/wordpress-calls.jsonl"

    results = call_every_bridge_tool(root)
    assert {name: result["structuredContent"] for name, result in results.items()} == {
        name: {"code": "WORDPRESS_MCP_PRICE_OVERLAY_LIVE"} for name in BRIDGE_TOOL_INPUTS
    }
    assert not calls.exists()

    # Control: once nothing is live, the same harness records every tool reaching WordPress.
    shutil.rmtree(owner / ".secrets/rakuten-price-refresh")
    results = call_every_bridge_tool(root)
    assert {name: result["structuredContent"] for name, result in results.items()} == {
        name: {"code": "SYNTHETIC_WORDPRESS_CALLED"} for name in BRIDGE_TOOL_INPUTS
    }
    assert sorted(json.loads(line)[0] for line in calls.read_text().splitlines()) == sorted(
        BRIDGE_TOOL_INPUTS
    )


# ---------------------------------------------------------------------------
# A run is finished only when no local copy of its values remains
# ---------------------------------------------------------------------------


def test_a_run_is_unblocked_only_when_no_local_copy_of_its_values_remains(
    owner, publisher, monkeypatch, capsys
):
    from raos.adapters.rakuten_price_refresh_client import expired_unpurged_runs, run_status
    from scripts.raos_wordpress_direct_preview import _theme_tree

    write_run(owner)
    server = FakeWordPress(owner)
    candidate, directory = prepare_overlay(owner, server)
    injected = candidate["articles"][0]["document"]["block_markup"]
    preview = owner / price_overlay.PREVIEW_PRIVATE
    # What a preview of the injected candidate leaves behind: the frozen injected theme (no run
    # marker, only injected hashes) and the article fixture. A price-free frozen theme stays.
    frozen = preview / ("theme-" + _theme_tree(directory / "theme"))
    shutil.copytree(directory / "theme", frozen)
    fixture = preview / "fixtures/articles/synthetic-comparison.html"
    fixture.parent.mkdir(parents=True)
    fixture.write_text(injected)
    price_free_theme = preview / ("theme-" + "0" * 64)
    shutil.copytree(owner / THEME_PREFIX, price_free_theme)
    publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    store = PrivateStore(owner)
    expired = T0 + timedelta(hours=25)
    purge_expired = ["purge-expired", "--owner-checkout", str(owner), "--run-id", RUN_ID]
    capsys.readouterr()
    assert refresh_cli.main(purge_expired, clock=lambda: expired) == 0
    report = json.loads(capsys.readouterr().out.splitlines()[-1])["runs"][0]
    assert (report["result"], report["preview_copies_deleted"]) == ("PURGE_PUBLISH_MISSING", 2)
    assert not frozen.exists() and not fixture.exists() and price_free_theme.exists()

    # While the values are live: a candidate from a publisher without the live refusal and a
    # preview fixture of the live page. The late purge publish sweeps both.
    with monkeypatch.context() as older:
        older.setattr(direct, "refuse_while_price_overlay_live", lambda *a: None)
        _stray, stray_directory = direct.prepare(owner, ["synthetic-comparison"], True, server)
    fixture.write_text(server.docs[101]["block_markup"])
    assert run_status(store, RUN_ID)[0] == "PUBLISHED_NOT_PURGED"
    monkeypatch.setattr(price_overlay, "clock", lambda: expired + timedelta(hours=1))
    purge, purge_directory = prepare_overlay(owner, server, purge=RUN_ID)
    server.finish_redaction = deepcopy(COMPLETE_REDACTION)
    publish(owner, purge_directory, purge, server, price_overlay_purge=RUN_ID)
    assert not stray_directory.exists() and not fixture.exists() and not purge_directory.exists()
    assert run_status(store, RUN_ID)[0] == "PURGED"
    assert expired_unpurged_runs(store, expired + timedelta(hours=1)) == []

    # A copy that shows up later blocks fetch and gate again until purge-expired removes it.
    fixture.write_text(injected)
    assert run_status(store, RUN_ID)[0] == "REDACTION_PENDING"
    assert expired_unpurged_runs(store, expired + timedelta(hours=1)) == [RUN_ID]
    capsys.readouterr()
    assert refresh_cli.main(purge_expired, clock=lambda: expired + timedelta(hours=2)) == 0
    report = json.loads(capsys.readouterr().out.splitlines()[-1])["runs"][0]
    assert (report["result"], report["record_state"], report["preview_copies_deleted"]) == (
        "ALREADY_PURGED",
        "REDACTION_PENDING",
        1,
    )
    assert not fixture.exists() and run_status(store, RUN_ID)[0] == "PURGED"


@pytest.mark.parametrize(
    ("reported", "reason"),
    [
        (None, "WORDPRESS_REDACTION_NOT_REPORTED"),
        (
            [{**COMPLETE_REDACTION[0], "state": "INCOMPLETE", "skipped_active": 1}],
            "WORDPRESS_REDACTION_INCOMPLETE",
        ),
    ],
)
def test_an_unconfirmed_plugin_redaction_blocks_until_the_owner_confirms_the_cleanup(
    owner, publisher, capsys, reported, reason
):
    from raos.adapters.rakuten_price_refresh_client import expired_unpurged_runs, run_status

    write_run(owner)
    server = FakeWordPress(owner)
    candidate, directory = prepare_overlay(owner, server)
    publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    purge, purge_directory = prepare_overlay(owner, server, purge=RUN_ID)
    server.finish_redaction = deepcopy(reported)
    publish(owner, purge_directory, purge, server, price_overlay_purge=RUN_ID)
    later = T0 + timedelta(hours=3)
    store = PrivateStore(owner)
    confirm = ["confirm-plugin-cleanup", "--owner-checkout", str(owner), "--run-id", RUN_ID]
    text = ["--owner-confirmed-plugin-cleanup", "PLUGIN_COPIES_REMOVED:" + RUN_ID]

    def refused(arguments):
        assert refresh_cli.main(arguments, clock=lambda: later) == 2
        return json.loads(capsys.readouterr().out)["code"]

    capsys.readouterr()
    # Local values are not purged yet: nothing to confirm.
    assert refused([*confirm, *text]) == "PLUGIN_CLEANUP_CONFIRMATION_NOT_APPLICABLE"
    purge_expired = ["purge-expired", "--owner-checkout", str(owner), "--run-id", RUN_ID]
    assert refresh_cli.main([*purge_expired, "--include-unexpired"], clock=lambda: later) == 0
    report = json.loads(capsys.readouterr().out.splitlines()[-1])["runs"][0]
    assert report["result"] == "WORDPRESS_REDACTION_UNCONFIRMED"
    assert run_status(store, RUN_ID)[0] == "WORDPRESS_REDACTION_UNCONFIRMED"
    assert expired_unpurged_runs(store, later) == [RUN_ID]
    for wrong in (
        [],
        ["--owner-confirmed-plugin-cleanup", "PLUGIN_COPIES_REMOVED:ks020-synthetic-0002"],
        ["--owner-confirmed-plugin-cleanup", RUN_ID],
    ):
        assert refused([*confirm, *wrong]) == "PLUGIN_CLEANUP_CONFIRMATION_REQUIRED"
    assert expired_unpurged_runs(store, later) == [RUN_ID]
    assert refresh_cli.main([*confirm, *text], clock=lambda: later) == 0
    assert json.loads(capsys.readouterr().out) == {
        "result": "PLUGIN_CLEANUP_RECORDED",
        "run_id": RUN_ID,
        "reason": reason,
        "record_state": "PURGED",
    }
    record = store.run_directory(RUN_ID) / "plugin-cleanup.v1.json"
    assert stat.S_IMODE(record.stat().st_mode) == 0o600
    assert expired_unpurged_runs(store, later) == []
    assert refused([*confirm, *text]) == "PLUGIN_CLEANUP_CONFIRMATION_NOT_APPLICABLE"


def test_purge_publish_refuses_an_injected_article_body_before_writes(owner, publisher, monkeypatch):
    write_run(owner)
    server = FakeWordPress(owner)
    candidate, directory = prepare_overlay(owner, server)
    publish(owner, directory, candidate, server, price_overlay_run=RUN_ID)
    purge, purge_directory = prepare_overlay(owner, server, purge=RUN_ID)
    injected = candidate["articles"][0]["document"]["block_markup"]
    key = "synthetic-comparison"
    source = BODY_SOURCE.format(key)
    writes = len(server.writes())

    def tampered_purge(*, rehash_sources):
        tampered = deepcopy(purge)
        article = next(a for a in tampered["articles"] if a["article_key"] == key)
        article["document"]["block_markup"] = injected
        (purge_directory / article["body_file"]).write_text(injected)
        if rehash_sources:
            # Checkpoint copy, its recorded hash and the working tree all carry the injected body.
            (purge_directory / "sources" / source).write_text(injected)
            (owner / source).write_text(injected)
            tampered["sources"][source] = direct.digest(injected.encode())
        tampered["candidate_id"] = direct.digest(
            direct.encoded({k: v for k, v in tampered.items() if k != "candidate_id"})
        )
        direct.save(purge_directory / "candidate.json", tampered)
        previewed(purge_directory, tampered)
        return tampered

    # A consistently re-hashed candidate: only price_free_violations can refuse the body.
    tampered = tampered_purge(rehash_sources=True)
    with pytest.raises(direct.DirectFailure, match="PRICE_OVERLAY_PURGE_BODY_NOT_PRICE_FREE"):
        publish(owner, purge_directory, tampered, server, price_overlay_purge=RUN_ID)
    assert len(server.writes()) == writes, "refused before any WordPress write"
    assert approval_record(owner)["purge_publish"] is None

    # A document that differs from its checkpoint bytes never reaches that check: a price-free
    # article's body_file is its checkpoint copy (sources/...), so load_candidate refuses first.
    (owner / source).write_text(BODY)
    monkeypatch.setattr(direct, "verify_preview", lambda *a: None)
    tampered = tampered_purge(rehash_sources=False)
    article = next(a for a in tampered["articles"] if a["article_key"] == key)
    assert article["body_file"] == "sources/" + source
    with pytest.raises(direct.DirectFailure, match="RAOS_WORDPRESS_DIRECT_SNAPSHOT_DRIFT"):
        publish(owner, purge_directory, tampered, server, price_overlay_purge=RUN_ID)
    assert len(server.writes()) == writes, "refused before any WordPress write"
    assert approval_record(owner)["purge_publish"] is None
