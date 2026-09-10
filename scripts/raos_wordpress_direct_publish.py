#!/usr/bin/env python3
"""Freeze, preview and explicitly publish an owner-direct-v1 candidate.

The publish command is an orchestration action to invoke only after the user
instructs publication of that exact reviewed candidate. Neither preview evidence
nor any local flag grants authority. The dedicated WordPress principal enforces
the configured scope. Legacy candidates are deliberately incompatible.
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import raos_wordpress_deployment_operator as operator  # noqa: E402

PROFILE = "owner-direct-v1"
SCHEMA = "RAOSOwnerDirectCandidateV1"
REGISTRY = "changes/wordpress-direct-publish-v1/articles.v1.json"
PRIVATE = ".secrets/wordpress-mcp/owner-direct-v1"
FIELDS = (
    "post_type",
    "title",
    "slug",
    "excerpt",
    "block_markup",
    "taxonomies",
    "media_ids",
)


class DirectFailure(RuntimeError):
    pass


def fail(code):
    raise DirectFailure("RAOS_WORDPRESS_DIRECT_" + code)


def encoded(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def save(path, value):
    safe_ancestors(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or path.parent.is_symlink():
        fail("PRIVATE_PATH_INVALID")
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded(value) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def read_json(path):
    safe_ancestors(path)
    if path.is_symlink() or path.stat().st_size > 32 * 1024 * 1024:
        fail("FILE_INVALID")
    return json.loads(path.read_text(encoding="utf-8"))


def tracked(root, paths):
    output = subprocess.run(
        ["git", "ls-files", "-z", "--", *paths],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    return sorted(p.decode() for p in output.split(b"\0") if p)


def source_bytes(root, relative):
    path = PurePosixPath(relative)
    if (
        path.as_posix() != relative
        or "\\" in relative
        or path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or path.parts[0] in {".secrets", ".git"}
    ):
        fail("SOURCE_PATH_INVALID")
    target = root / relative
    safe_ancestors(target)
    if (
        target.is_symlink()
        or not target.resolve().is_relative_to(root.resolve())
        or not target.is_file()
        or target.stat().st_nlink != 1
    ):
        fail("SOURCE_PATH_INVALID")
    return target.read_bytes()


def safe_ancestors(path):
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        fail("SOURCE_PATH_INVALID")


def validate_sources(root, candidate):
    for name, expected in candidate["sources"].items():
        if digest(source_bytes(root, name)) != expected:
            fail("SOURCE_DRIFT")
    for name in candidate.get("deleted_sources", []):
        if (root / name).exists() or (root / name).is_symlink():
            fail("SOURCE_DRIFT")


def load_candidate(directory, candidate_id):
    candidate = read_json(directory / "candidate.json")
    if candidate.get("schema") != SCHEMA or candidate.get("profile") != PROFILE:
        fail("PROFILE_REQUIRED")
    material = {k: v for k, v in candidate.items() if k != "candidate_id"}
    if (
        candidate.get("candidate_id") != candidate_id
        or digest(encoded(material)) != candidate_id
    ):
        fail("CANDIDATE_HASH_MISMATCH")
    for name, expected in candidate["sources"].items():
        if digest(source_bytes(directory / "sources", name)) != expected:
            fail("SNAPSHOT_DRIFT")
    for article in candidate["articles"]:
        if (directory / article["body_file"]).read_text() != article["document"][
            "block_markup"
        ]:
            fail("SNAPSHOT_DRIFT")
    if candidate.get("theme"):
        theme = candidate["theme"]
        if (
            digest((directory / theme["package_file"]).read_bytes())
            != theme["descriptor"]["package_sha256"]
        ):
            fail("SNAPSHOT_DRIFT")
        manifest = theme["descriptor"]["file_manifest"]
        theme_root = directory / theme["directory"]
        actual = []
        for path in sorted(theme_root.rglob("*")):
            if path.is_file():
                relative = path.relative_to(theme_root).as_posix()
                payload = source_bytes(theme_root, relative)
                actual.append(
                    {"path": relative, "size": len(payload), "sha256": digest(payload)}
                )
        if actual != manifest:
            fail("SNAPSHOT_DRIFT")
    return candidate


def invoke(command, body):
    return operator.run("owner-direct-" + command, body)


def checkpoint_git(root, paths, snapshot_id):
    from scripts.raos_wordpress_publish_git import checkpoint

    return checkpoint(root, paths, snapshot_id)


def sync_git(root, checkpoint):
    from scripts.raos_wordpress_publish_git import sync

    return sync(root, checkpoint)


def package_theme(root, paths, commit, payloads=None):
    prefix = operator.THEME_ROOT.relative_to(operator.ROOT).as_posix()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            if path.startswith(prefix + "/"):
                info = zipfile.ZipInfo(
                    operator.THEME_SLUG + "/" + path[len(prefix) + 1 :],
                    operator.ZIP_TIMESTAMP,
                )
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.create_system = 3
                archive.writestr(
                    info, payloads[path] if payloads else source_bytes(root, path)
                )
    payload = output.getvalue()
    style = (
        payloads[prefix + "/style.css"]
        if payloads
        else source_bytes(root, prefix + "/style.css")
    )
    match = re.search(rb"(?im)^\s*(?:\*\s*)?Version:\s*([^\r\n]+)", style[:8192])
    if match is None:
        fail("THEME_VERSION_MISSING")
    version = operator.require_version(match.group(1).decode().strip())
    manifest, manifest_hash, _, safe = operator.validate_package(
        payload, kind="theme", slug=operator.THEME_SLUG, expected_version=version
    )
    if not safe:
        fail("THEME_INVALID")
    return payload, {
        "schema": "CodePackageV1",
        "kind": "theme",
        "source": "tracked_child_theme",
        "artifact_id": None,
        "git_commit": commit,
        "slug": operator.THEME_SLUG,
        "old_version": None,
        "new_version": version,
        "package_sha256": digest(payload),
        "file_manifest_sha256": manifest_hash,
        "file_manifest": manifest,
        "activation_intent": "preserve",
        "migration_assessment": "NO_IRREVERSIBLE_MIGRATION_SIGNALS",
        "automatic_apply_eligible": True,
    }


def import_existing(root):
    """Import tracked baseline bytes once into separately owned editable sources."""
    base = root / "changes/wordpress-local-preview-v1"
    fixture = read_json(base / "fixtures/posts.json")
    mapping = read_json(base / "production-mapping.v1.json")
    posts = {p["slug"]: p for p in fixture["posts"]}
    registry = read_json(root / REGISTRY)
    known = {row["article_key"] for row in registry["articles"]}
    for row in mapping["articles"]:
        if row["production_slug"] in known:
            continue
        post = posts[row["local_slug"]]
        source = "changes/wordpress-local-preview-v1/fixtures/" + post["content_file"]
        body_source = (
            "changes/wordpress-direct-publish-v1/articles/"
            + row["production_slug"]
            + ".html"
        )
        target = root / body_source
        safe_ancestors(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = source_bytes(root, source)
        if target.exists() and source_bytes(root, body_source) != payload:
            fail("IMPORT_SOURCE_EXISTS")
        target.write_bytes(payload)
        registry["articles"].append(
            {
                "article_key": row["production_slug"],
                "mode": "existing",
                "post_id": None,
                "post_type": "post",
                "title": post["title"],
                "slug": row["production_slug"],
                "excerpt": post["excerpt"],
                "body_source": body_source,
                "import_provenance": {"path": source, "sha256": digest(payload)},
                "taxonomies": row["taxonomies"],
            }
        )
    (root / REGISTRY).write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n"
    )
    return {"status": "IMPORTED", "article_count": len(registry["articles"])}


def prepare(root, keys, theme=False, call=invoke):
    registry = read_json(root / REGISTRY)
    if (
        registry.get("schema") != "RAOSOwnerDirectArticlesV1"
        or registry.get("profile") != PROFILE
    ):
        fail("REGISTRY_INVALID")
    rows = [r for r in registry["articles"] if r["article_key"] in keys]
    if len(rows) != len(set(keys)) or not (rows or theme):
        fail("SELECTION_INVALID")
    # A patch is an edit recipe, never a replacement HTML body. Both source
    # types still enter the existing checkpoint and candidate integrity flow.
    for row in rows:
        if bool(row.get("body_source")) == bool(row.get("patch_source")):
            fail("BODY_SOURCE_AMBIGUOUS")
        if row.get("patch_source") and (
            row.get("mode") != "existing"
            or type(row.get("post_id")) is not int
            or row["post_id"] < 1
            or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", row["article_key"]) is None
            or row["patch_source"] != (
                "changes/wordpress-direct-publish-v1/articles/"
                + row["article_key"] + ".patch.json"
            )
        ):
            fail("PATCH_SOURCE_INVALID")
    paths = [REGISTRY] + [r.get("patch_source") or r["body_source"] for r in rows]
    if any(row.get("patch_source") for row in rows):
        paths.append("scripts/raos_reader_live_patch.py")
    theme_prefix = operator.THEME_ROOT.relative_to(operator.ROOT).as_posix()
    if theme:
        paths += tracked(root, [theme_prefix])
        extra = subprocess.run(
            [
                "git",
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
                theme_prefix,
            ],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        paths += [p.decode() for p in extra.split(b"\0") if p]
    paths = sorted(set(paths))
    untracked = set(paths) - set(tracked(root, paths))
    if any(
        p != REGISTRY
        and not p.startswith("changes/wordpress-direct-publish-v1/articles/")
        and not (theme and p.startswith(theme_prefix + "/"))
        for p in untracked
    ):
        fail("SOURCE_NOT_TRACKED")
    deleted = [
        p
        for p in paths
        if theme
        and p.startswith(theme_prefix + "/")
        and not (root / p).exists()
        and not (root / p).is_symlink()
    ]
    payloads = {p: source_bytes(root, p) for p in paths if p not in deleted}
    sources = {p: digest(b) for p, b in payloads.items()}
    source_hash = digest(encoded({"files": sources, "deleted": deleted}))
    checkpoint = checkpoint_git(root, paths, source_hash)
    if checkpoint.get("status") not in {"created", "noop"}:
        fail("CHECKPOINT_FAILED")
    checkpoint.pop("checkpoint_action", None)
    validate_sources(root, {"sources": sources, "deleted_sources": deleted})
    for name, expected in sources.items():
        pinned = subprocess.run(
            ["git", "show", checkpoint["commit"] + ":" + name],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        if digest(pinned) != expected:
            fail("CHECKPOINT_SOURCE_MISMATCH")
    for name in deleted:
        if (
            subprocess.run(
                ["git", "cat-file", "-e", checkpoint["commit"] + ":" + name],
                cwd=root,
                capture_output=True,
            ).returncode
            == 0
        ):
            fail("CHECKPOINT_SOURCE_MISMATCH")
    status_error = None
    try:
        status = call("status", {})
    except operator.OperatorFailure as error:
        if str(error) not in {
            "WORDPRESS_MCP_PRIVATE_FILE_UNAVAILABLE",
            "WORDPRESS_MCP_HTTP_404",
            "REST_NO_ROUTE",
            "WORDPRESS_MCP_TRANSPORT_FAILED",
        }:
            raise
        status_error = str(error)
        status = {}
    articles = []
    if status and (
        status.get("schema") != "RAOSOwnerDirectStatusV1"
        or status.get("profile") != PROFILE
        or type(status.get("targets")) is not list
    ):
        fail("STATUS_INVALID")
    targets = {t["article_key"]: t for t in status.get("targets", [])}
    ready = status.get("profile") == PROFILE and status.get("enabled") is True
    if ready:
        operator.require_sha256(status.get("profile_sha256"))
        operator.require_sha256(status.get("theme", {}).get("tree_sha256"))
    for row in rows:
        if row.get("mode") not in {"existing", "new"} or row.get("post_type") not in {
            "post",
            "page",
        }:
            fail("REGISTRY_INVALID")
        post_id = row.get("post_id") or targets.get(row["article_key"], {}).get(
            "post_id"
        )
        baseline = call("document", {"id": post_id}) if post_id and ready else None
        if row["mode"] == "existing" and baseline is None:
            ready = False
        if row["mode"] == "new" and not status.get("allow_new_posts"):
            ready = False
        document = {
            field: row.get(
                field,
                [] if field == "media_ids" else {} if field == "taxonomies" else "",
            )
            for field in FIELDS
        }
        if row.get("patch_source"):
            from scripts.raos_reader_live_patch import apply_patch

            if baseline is None:
                fail("PATCH_BASELINE_REQUIRED")
            if (
                baseline.get("id") != post_id
                or baseline.get("slug") != row["slug"]
                or baseline.get("post_type") != row["post_type"]
                or baseline.get("status") != "publish"
            ):
                fail("PATCH_BASELINE_MISMATCH")
            try:
                recipe = json.loads(payloads[row["patch_source"]].decode("utf-8"))
                document["block_markup"] = apply_patch(
                    baseline["block_markup"], recipe,
                    article_key=row["article_key"], post_id=post_id,
                )
            except (KeyError, TypeError, ValueError):
                fail("PATCH_REJECTED")
            if "title" not in row:
                document["title"] = baseline["title"]
            body_file = "bodies/" + row["article_key"] + ".html"
        else:
            document["block_markup"] = payloads[row["body_source"]].decode("utf-8")
            body_file = "sources/" + row["body_source"]
        if baseline:
            for field in ("excerpt", "taxonomies", "media_ids"):
                if field not in row:
                    document[field] = baseline[field]
        articles.append(
            {
                **row,
                "post_id": post_id,
                "body_file": body_file,
                **({"body_sha256": digest(document["block_markup"].encode("utf-8"))}
                   if row.get("patch_source") else {}),
                "document": document,
                "baseline": baseline,
            }
        )
    candidate = {
        "schema": SCHEMA,
        "profile": PROFILE,
        "source_sha256": source_hash,
        "sources": sources,
        "deleted_sources": deleted,
        "articles": articles,
        "theme": None,
        "baseline_theme_tree_sha256": status.get("theme", {}).get("tree_sha256"),
        "profile_sha256": status.get("profile_sha256"),
        "publication_ready": ready,
        "status_unavailable_reason": status_error,
        "checkpoint": checkpoint,
    }
    package = None
    if theme:
        package, descriptor = package_theme(
            root, list(payloads), checkpoint["commit"], payloads
        )
        descriptor["old_version"] = status.get("theme", {}).get("version")
        candidate["theme"] = {
            "directory": "theme",
            "package_file": "theme.zip",
            "descriptor": descriptor,
        }
    candidate["candidate_id"] = digest(encoded(candidate))
    directory = root / PRIVATE / candidate["candidate_id"]
    if directory.exists():
        return load_candidate(directory, candidate["candidate_id"]), directory
    directory.mkdir(parents=True, mode=0o700)
    for path, payload in payloads.items():
        target = directory / "sources" / path
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(payload)
        target.chmod(0o600)
        if theme and path.startswith(theme_prefix + "/"):
            destination = directory / "theme" / path[len(theme_prefix) + 1 :]
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            destination.write_bytes(payload)
            destination.chmod(0o600)
    for article in articles:
        if article.get("patch_source"):
            # The live body (including opaque CTA values) remains owner-private.
            target = directory / article["body_file"]
            safe_ancestors(target)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.write_text(article["document"]["block_markup"], encoding="utf-8")
            target.chmod(0o600)
    if package:
        (directory / "theme.zip").write_bytes(package)
        (directory / "theme.zip").chmod(0o600)
    save(directory / "candidate.json", candidate)
    return candidate, directory


def precondition(document):
    result = {k: document[k] for k in ("revision_id", "modified_gmt", "content_sha256")}
    if type(result["revision_id"]) is not int or result["revision_id"] < 1:
        fail("BASELINE_INVALID")
    operator.require_sha256(result["content_sha256"])
    return result


def readback(candidate, journal, call):
    for article in candidate["articles"]:
        current = call("document", {"id": journal["post_ids"][article["article_key"]]})
        if (
            current.get("status") != "publish"
            or {k: current.get(k) for k in FIELDS} != article["document"]
        ):
            fail("READBACK_MISMATCH")
    if candidate.get("theme"):
        current = call("status", {})
        if (
            current.get("theme", {}).get("tree_sha256")
            != candidate["theme"]["descriptor"]["file_manifest_sha256"]
        ):
            fail("THEME_READBACK_MISMATCH")
    return {"status": "PASS"}


def content_after_sha256(document, post_id):
    # The server hashes UTF-8 JSON with unescaped slashes, while local candidate
    # IDs intentionally keep the existing ASCII serialization contract.
    material = {"schema": "ContentDocumentV1", "id": post_id,
                "status": "publish", **document}
    serialized = json.dumps(material, sort_keys=True, ensure_ascii=False,
                            separators=(",", ":"), allow_nan=False)
    serialized = serialized.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return digest(serialized.encode("utf-8"))


def finish_batch(journal, action, call):
    result = call("finish", {"profile": PROFILE, **journal["batch"], "action": action})
    if (
        result.get("schema") != "RAOSOwnerDirectBatchResultV1"
        or result.get("profile") != PROFILE
        or any(result.get(key) != value for key, value in journal["batch"].items())
        or result.get("state")
        not in (
            {"FINALIZED", "PARTIAL_CONFLICT"}
            if action == "finalize"
            else {"ROLLED_BACK", "PARTIAL_CONFLICT"}
        )
        or type(result.get("members")) is not list
    ):
        fail("BATCH_RESULT_INVALID")
    return result


def finish_publication(root, directory, candidate, journal, call):
    journal["readback"] = readback(candidate, journal, call)
    if (
        journal.get("batch")
        and journal.get("batch_finish", {}).get("state") != "FINALIZED"
    ):
        result = finish_batch(journal, "finalize", call)
        journal["batch_finish"] = result
        save(directory / "journal.json", journal)
        if result.get("state") != "FINALIZED":
            fail("BATCH_FINALIZATION_CONFLICT")
    journal["publication_status"] = "PUBLISHED_AND_READBACK_VERIFIED"
    journal.pop("pending_operation", None)
    journal.pop("result_code", None)
    save(directory / "journal.json", journal)
    print(
        json.dumps(
            {
                "candidate_id": candidate["candidate_id"],
                "publication_status": journal["publication_status"],
                "git_sync": "PENDING",
            }
        ),
        flush=True,
    )
    try:
        journal["git_sync"] = sync_git(root, journal["checkpoint"])
    except Exception:
        journal["git_sync"] = {"status": "error", "error": "GIT_SYNC_FAILED"}
    save(directory / "journal.json", journal)
    return journal


def verify_preview(candidate, directory, report):
    from scripts.raos_wordpress_direct_preview import verify_preview as verify

    try:
        verify(candidate, directory, report)
    except ValueError, OSError:
        fail("PREVIEW_STALE")


def publish(root, directory, candidate_id, call=invoke):
    safe_ancestors(directory)
    descriptor = os.open(
        directory / "operation.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "ab") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("OPERATION_BUSY")
        try:
            return _publish(root, directory, candidate_id, call)
        except (
            DirectFailure,
            operator.OperatorFailure,
            OSError,
            ValueError,
            KeyError,
            KeyboardInterrupt,
        ) as error:
            record_failure(directory, candidate_id, error, call)
            raise


def record_failure(directory, candidate_id, error, call):
    """Keep uncertainty and partial application explicit; never compensate blindly."""
    path = directory / "journal.json"
    if not path.exists():
        return
    journal = read_json(path)
    if journal.get("candidate_id") != candidate_id:
        return
    if journal["publication_status"] in {"ROLLED_BACK", "PARTIAL_CONFLICT"}:
        return
    code = (
        str(error)
        if isinstance(error, (DirectFailure, operator.OperatorFailure))
        else "RAOS_WORDPRESS_DIRECT_INTERRUPTED"
        if isinstance(error, KeyboardInterrupt)
        else "RAOS_WORDPRESS_DIRECT_LOCAL_STATE_INVALID"
    )
    observed = {}
    for proposal_id in journal.get("proposals", {}).values():
        try:
            observed[proposal_id] = call(
                "operation-status", {"operation_id": proposal_id}
            )["operation"]["state"]
        except operator.OperatorFailure, OSError, KeyError, ValueError:
            observed[proposal_id] = "UNKNOWN"
    states = list(observed.values())
    definitive_failure = any(s == "FAILED" for s in states) or code in {
        "RAOS_WORDPRESS_DIRECT_READBACK_MISMATCH",
        "RAOS_WORDPRESS_DIRECT_THEME_READBACK_MISMATCH",
        "RAOS_WORDPRESS_DIRECT_BATCH_FINALIZATION_CONFLICT",
    }
    if (
        definitive_failure
        and journal.get("batch")
        and not any(s in {"UNKNOWN", "APPLYING"} for s in states)
    ):
        try:
            rollback = finish_batch(journal, "rollback", call)
            journal["batch_finish"] = rollback
            if rollback.get("state") in {"ROLLED_BACK", "PARTIAL_CONFLICT"}:
                journal["publication_status"] = rollback["state"]
                journal["result_code"] = code
                journal["observed_operation_states"] = observed
                save(path, journal)
                return
        except DirectFailure, operator.OperatorFailure, OSError, KeyError, ValueError:
            journal["rollback_status"] = "UNKNOWN"
    if journal["publication_status"] == "PUBLISHED_AND_READBACK_VERIFIED":
        pass
    elif (
        journal["publication_status"] == "APPLIED"
        or states
        and all(s == "APPLIED" for s in states)
    ):
        journal["publication_status"] = "APPLIED"
    elif "APPLIED" in states:
        journal["publication_status"] = "PARTIAL"
    elif "CONFLICT" in code:
        journal["publication_status"] = "CONFLICT"
    elif any(s in {"FAILED", "MANUAL_REQUIRED", "EXPIRED"} for s in states):
        journal["publication_status"] = "FAILED"
    else:
        journal["publication_status"] = (
            "UNKNOWN" if journal.get("pending_operation") else "BLOCKED"
        )
    journal["result_code"] = code
    journal["observed_operation_states"] = observed
    save(path, journal)


def _publish(root, directory, candidate_id, call):
    candidate = load_candidate(directory, candidate_id)
    path = directory / "journal.json"
    journal = (
        read_json(path)
        if path.exists()
        else {
            "candidate_id": candidate_id,
            "publication_status": "PREPARED",
            "post_ids": {},
            "proposals": {},
            "checkpoint": candidate["checkpoint"],
        }
    )
    if journal.get("candidate_id") != candidate_id:
        fail("JOURNAL_MISMATCH")
    if journal["publication_status"] in {"ROLLED_BACK", "PARTIAL_CONFLICT"}:
        fail("BATCH_CLOSED_REPREPARE")
    identities = {article["article_key"] for article in candidate["articles"]}
    if candidate["theme"]:
        identities.add("@theme")
    if not set(journal.get("proposals", {})).issubset(identities):
        fail("JOURNAL_MISMATCH")
    if journal["publication_status"] in {"APPLIED", "PUBLISHED_AND_READBACK_VERIFIED"}:
        return finish_publication(root, directory, candidate, journal, call)
    preview = read_json(directory / "preview.json")
    if (
        preview.get("status") != "PASS"
        or preview.get("candidate_id") != candidate_id
        or preview.get("source_sha256") != candidate["source_sha256"]
    ):
        fail("PREVIEW_REQUIRED")
    verify_preview(candidate, directory, preview)
    validate_sources(root, candidate)
    if not candidate["publication_ready"]:
        fail("BASELINE_UNAVAILABLE_REPREPARE")
    status = call("status", {})
    if (
        status.get("profile") != PROFILE
        or not status.get("enabled")
        or status.get("profile_sha256") != candidate["profile_sha256"]
    ):
        fail("PROFILE_CHANGED")
    if (
        not journal["proposals"]
        and status.get("theme", {}).get("tree_sha256")
        != candidate["baseline_theme_tree_sha256"]
    ):
        fail("THEME_CONFLICT")
    # Persist deterministic keys before any write, including first draft creation.
    save(path, journal)
    for article in candidate["articles"]:
        key = article["article_key"]
        if key in journal["proposals"]:
            continue
        post_id = journal["post_ids"].get(key) or article["post_id"]
        baseline = article["baseline"]
        if post_id is None:
            journal["pending_operation"] = "ensure-draft:" + key
            save(path, journal)
            draft = call(
                "ensure-draft",
                {
                    "profile": PROFILE,
                    "article_key": key,
                    "slug": article["slug"],
                    "idempotency_key": digest(encoded([candidate_id, key, "draft"])),
                },
            )
            post_id, baseline = draft["id"], draft["document"]
            journal.setdefault("draft_baselines", {})[key] = baseline
        elif baseline is None:
            baseline = journal.get("draft_baselines", {}).get(key)
        if baseline is None:
            fail("BASELINE_MISSING")
        journal["post_ids"][key] = post_id
        save(path, journal)
        current = call("document", {"id": post_id})
        if precondition(current) != precondition(baseline):
            fail("CONTENT_CONFLICT")
        journal["pending_operation"] = "content-propose:" + key
        save(path, journal)
        response = call(
            "content-propose",
            {
                "profile": PROFILE,
                "article_key": key,
                "id": post_id,
                "precondition": precondition(baseline),
                "document": article["document"],
                "idempotency_key": digest(encoded([candidate_id, key, "proposal"])),
            },
        )
        proposal = response.get("proposal", response)
        if proposal.get("after_sha256") != content_after_sha256(
            article["document"], post_id
        ):
            fail("PROPOSAL_CONTENT_MISMATCH")
        journal["proposals"][key] = operator.require_sha256(proposal.get("proposal_id"))
        save(path, journal)
    if candidate["theme"] and "@theme" not in journal["proposals"]:
        journal["pending_operation"] = "theme-propose"
        save(path, journal)
        response = call(
            "theme-propose",
            {
                "profile": PROFILE,
                "kind": "theme_release",
                "code_package": candidate["theme"]["descriptor"],
                "package_base64": base64.b64encode(
                    (directory / "theme.zip").read_bytes()
                ).decode(),
                "idempotency_key": digest(encoded([candidate_id, "theme"])),
            },
        )
        if (
            response["proposal"].get("after_tree_sha256")
            != candidate["theme"]["descriptor"]["file_manifest_sha256"]
        ):
            fail("PROPOSAL_THEME_MISMATCH")
        journal["proposals"]["@theme"] = operator.require_sha256(
            response["proposal"]["proposal_id"]
        )
        save(path, journal)
    ids = sorted(journal["proposals"].values())
    journal["proposal_ids"] = ids
    # Recovery reads state before retrying batch writes. The shared bounded
    # apply helper resolves APPLYING/APPLIED receipts before any re-application.
    states = [
        call("operation-status", {"operation_id": value})["operation"]["state"]
        for value in ids
    ]
    if all(state == "APPLIED" for state in states):
        journal["publication_status"] = "APPLIED"
    else:
        if any(state in {"FAILED", "MANUAL_REQUIRED", "EXPIRED"} for state in states):
            fail("OPERATION_REQUIRES_ATTENTION")
        if "batch" not in journal:
            journal["pending_operation"] = "authorize"
            save(path, journal)
            desired_theme = (
                candidate["theme"]["descriptor"]["file_manifest_sha256"]
                if candidate["theme"]
                else candidate["baseline_theme_tree_sha256"]
            )
            batch = call(
                "authorize",
                {
                    "profile": PROFILE,
                    "proposal_ids": ids,
                    "expected_theme_tree_sha256": desired_theme,
                },
            )
            journal["batch"] = {
                k: batch[k] for k in ("batch_token", "batch_manifest_sha256")
            }
            save(path, journal)
        journal["pending_operation"] = "apply"
        save(path, journal)
        receipt = call("apply", {**journal["batch"], "proposal_ids": ids})
        if receipt.get("state") != "APPLIED":
            fail("APPLY_UNCONFIRMED")
        journal["apply_receipt"] = receipt
        journal["publication_status"] = "APPLIED"
    save(path, journal)
    return finish_publication(root, directory, candidate, journal, call)


def parser():
    result = argparse.ArgumentParser(allow_abbrev=False)
    result.add_argument("--owner-checkout", type=Path)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("import-existing")
    create = commands.add_parser("prepare")
    create.add_argument("--articles", default="")
    create.add_argument("--theme", action="store_true")
    for name in ("preview", "publish", "status", "sync"):
        command = commands.add_parser(name)
        command.add_argument("--candidate", required=name != "status")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        owner = operator.validated_owner_checkout(args.owner_checkout)
    except operator.OperatorFailure as error:
        print(str(error), file=sys.stderr)
        return 69
    private_context_reset = operator._private_owner.set(owner)
    try:
        return execute_cli(args)
    finally:
        operator._private_owner.reset(private_context_reset)


def execute_cli(args):
    try:
        if args.command == "import-existing":
            result = import_existing(ROOT)
        elif args.command == "status" and args.candidate is None:
            result = invoke("status", {})
        elif args.command == "prepare":
            candidate, directory = prepare(
                ROOT, [x for x in args.articles.split(",") if x], args.theme
            )
            result = {
                "candidate_id": candidate["candidate_id"],
                "candidate_directory": str(directory),
                "publication_ready": candidate["publication_ready"],
            }
        else:
            operator.require_sha256(args.candidate)
            directory = ROOT / PRIVATE / args.candidate
            candidate = load_candidate(directory, args.candidate)
            if args.command == "preview":
                from scripts.raos_wordpress_direct_preview import (
                    prepare_candidate_preview,
                )

                result = prepare_candidate_preview(candidate, directory)
                save(directory / "preview.json", result)
            elif args.command == "publish":
                journal = publish(ROOT, directory, args.candidate)
                result = {
                    key: journal[key]
                    for key in ("candidate_id", "publication_status", "git_sync")
                }
            else:
                journal_path = directory / "journal.json"
                journal = (
                    read_json(journal_path)
                    if journal_path.exists()
                    else {
                        "candidate_id": args.candidate,
                        "publication_status": "PREPARED",
                        "publication_ready": candidate["publication_ready"],
                    }
                )
                if args.command == "sync":
                    if (
                        journal["publication_status"]
                        != "PUBLISHED_AND_READBACK_VERIFIED"
                    ):
                        fail("PUBLICATION_NOT_VERIFIED")
                    journal["git_sync"] = sync_git(ROOT, journal["checkpoint"])
                    save(directory / "journal.json", journal)
                elif journal.get("proposal_ids"):
                    journal = {
                        **journal,
                        "observed_operations": [
                            invoke("operation-status", {"operation_id": value})
                            for value in journal["proposal_ids"]
                        ],
                    }
                result = journal
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (DirectFailure, operator.OperatorFailure) as error:
        print(str(error), file=sys.stderr)
        return 69
    except KeyboardInterrupt:
        print("RAOS_WORDPRESS_DIRECT_INTERRUPTED_CHECK_STATUS", file=sys.stderr)
        return 130
    except OSError, ValueError, KeyError, subprocess.SubprocessError:
        print("RAOS_WORDPRESS_DIRECT_LOCAL_STATE_INVALID", file=sys.stderr)
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
