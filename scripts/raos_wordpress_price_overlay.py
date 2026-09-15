"""Owner-direct publisher integration of the KS-020 Rakuten price overlay.

Opt-in only (``--price-overlay-run`` / ``--price-overlay-purge`` on prepare and
publish). The price-free git checkpoint is created first by the unchanged
``prepare``; API values are then injected into a separate private candidate under
``.secrets/wordpress-mcp/owner-direct-v1/<candidate_id>/`` together with the rebound
runtime JSON, ``KURASHINOSHIRUBE_PURCHASE_RUNTIME_SHA256``, theme revision stamps and
package manifest. The purge path re-sends the price-free checkpoint bytes. Nothing
here writes a git-tracked path. Contract:
changes/reader-purchase-support-v1/price-refresh-contract.md §6-§8.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
from datetime import UTC, datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

from raos.adapters.rakuten_price_refresh_client import (  # noqa: E402
    PrivateStore,
    expired_unpurged_runs,
    scan_repository_for_overlay,
    scan_revision_for_overlay,
)
from raos.domain.editorial import rakuten_price_refresh as rpr  # noqa: E402
from scripts import raos_wordpress_deployment_operator as operator  # noqa: E402

BINDING_SCHEMA = "RAOS_OWNER_DIRECT_PRICE_OVERLAY_V1"
MODE_PUBLISH = "PUBLISH"
MODE_PURGE = "PURGE"
THEME_PREFIX = operator.THEME_ROOT.relative_to(operator.ROOT).as_posix()
RUNTIME_RELATIVE = "assets/purchase-support.v1.json"
FUNCTIONS_RELATIVE = "functions.php"
JS_RELATIVE = "assets/purchase-support.js"
PREVIEW_PRIVATE = ".secrets/wordpress-direct-preview"
REVISION_CONSTANTS = (
    "KURASHINOSHIRUBE_THEME_RUNTIME_REVISION",
    "KURASHINOSHIRUBE_THEME_SOURCE_FINGERPRINT",
)
# Theme files outside functions.php and the stylesheets that repeat the revision
# (build_st1704_self_hosted_theme.render_theme_stamp_payloads).
JSON_REVISION_FIELDS = {
    "raos-assets.v1.json": ((), ("theme_runtime_revision", "theme_source_fingerprint")),
    "theme-contract.v1.json": (("runtime_evidence",), ("revision", "source_fingerprint")),
}
ARTICLE_KEY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def clock():
    return datetime.now(UTC)


@contextmanager
def refusals(direct):
    """Domain refusals keep their stable code under the publisher prefix."""
    try:
        yield
    except rpr.RefreshError as error:
        direct.fail("PRICE_OVERLAY_" + error.code)


def _store(root):
    return PrivateStore(Path(root))


def _approval(store, run_id):
    path = store.run_directory(run_id) / "approval.v1.json"
    if not path.is_file():
        rpr.fail("APPROVAL_MISSING")
    return path, rpr.validate_approval(store.read_json(path), run_id)


@contextmanager
def _approval_lock(store, run_id):
    """Serialize read-check-write of one run's approval record across candidates.

    The publisher lock covers one candidate directory only; without this, two candidates
    of the same run could both reserve and the later record would overwrite the earlier
    one (its article keys would then carry no purge obligation).
    """
    directory = store.run_directory(run_id)
    if directory.is_symlink() or not directory.is_dir():
        rpr.fail("PRIVATE_PATH_UNSAFE")
    descriptor = os.open(
        directory / "approval.lock",
        os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    with os.fdopen(descriptor, "ab") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            rpr.fail("APPROVAL_BUSY")
        yield


def _overlay(store, run_id):
    path = store.run_directory(run_id) / "overlay.v1.json"
    if not path.is_file():
        rpr.fail("OVERLAY_MISSING")
    overlay = store.read_json(path)
    rpr.validate_overlay(overlay)
    return overlay


def _overlay_for_check(store, run_id):
    """The overlay when still readable; otherwise only its run marker (after purge-expired)."""
    try:
        return _overlay(store, run_id)
    except (rpr.RefreshError, OSError, ValueError):
        return {"run_id": run_id, "entries": []}


def _write_private(path, payload, top):
    """mkdir(parents=True) ignores mode for parents, so each level is created 0700 here."""
    current = top
    for part in path.parent.relative_to(top).parts:
        current = current / part
        if current.is_symlink():
            rpr.fail("PRIVATE_PATH_UNSAFE")
        if not current.exists():
            current.mkdir(mode=0o700)
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def _price_free_payloads(direct, candidate, directory):
    """Checkpoint bytes frozen by prepare (load_candidate verified their hashes)."""
    return {
        name: direct.source_bytes(directory / "sources", name)
        for name in sorted(candidate["sources"])
    }


def _theme_payloads(payloads):
    prefix = THEME_PREFIX + "/"
    return {p[len(prefix) :]: b for p, b in payloads.items() if p.startswith(prefix)}


def _constant(functions, name):
    found = re.findall(
        rf"(?m)^const {re.escape(name)} = '([0-9a-f]{{64}})';$", functions
    )
    return found[0] if len(found) == 1 else None


def _require_php_bindings(builder, payloads):
    functions = payloads[FUNCTIONS_RELATIVE].decode("utf-8")
    for constant, relative in builder.PHP_INTEGRITY_BINDINGS.items():
        if relative in payloads and _constant(functions, constant) != rpr.sha256_hex(
            payloads[relative]
        ):
            rpr.fail("THEME_BINDING_STALE")


def injected_theme_payloads(theme_payloads, price_free_bodies, injected_bodies):
    """Rebind the runtime, its PHP constant and every theme revision stamp (§7-2〜4)."""
    from scripts import build_st1704_self_hosted_theme as builder

    if RUNTIME_RELATIVE not in theme_payloads or FUNCTIONS_RELATIVE not in theme_payloads:
        rpr.fail("THEME_RUNTIME_MISSING")
    runtime = theme_payloads[RUNTIME_RELATIVE]
    document = json.loads(runtime.decode("utf-8"))
    bound = {
        a.get("slug"): a.get("body_sha256")
        for a in document.get("articles", [])
        if isinstance(a, dict)
    }
    for slug in injected_bodies:
        # The git runtime must bind the price-free body that the value is injected into.
        if bound.get(slug) != rpr.body_sha256(price_free_bodies[slug]):
            rpr.fail("RUNTIME_BODY_UNBOUND")
    try:
        _require_php_bindings(builder, theme_payloads)
        old_revision = builder._fingerprint_from_payloads(theme_payloads)
        functions = theme_payloads[FUNCTIONS_RELATIVE].decode("utf-8")
        if any(_constant(functions, c) != old_revision for c in REVISION_CONSTANTS):
            rpr.fail("THEME_STAMP_STALE")
        runtime_bytes, runtime_sha256 = rpr.inject_runtime(runtime, injected_bodies)
        result = dict(theme_payloads)
        result[RUNTIME_RELATIVE] = runtime_bytes
        functions = rpr.rebind_runtime_constant(functions, runtime_sha256)
        result[FUNCTIONS_RELATIVE] = functions.encode("utf-8")
        revision = builder._fingerprint_from_payloads(result)
        for constant in REVISION_CONSTANTS:
            functions = builder._replace_exact_hash_constant(
                functions, constant, revision
            )
        result[FUNCTIONS_RELATIVE] = functions.encode("utf-8")
        for relative, name in builder.RUNTIME_STYLESHEET_SENTINELS.items():
            result[relative] = builder._replace_stylesheet_revision(
                result[relative].decode("utf-8"), name, revision
            ).encode("utf-8")
        for relative, (parents, fields) in JSON_REVISION_FIELDS.items():
            stamped = json.loads(result[relative].decode("utf-8"))
            if builder._canonical_json(stamped) != result[relative]:
                rpr.fail("THEME_STAMP_NOT_CANONICAL")
            holder = stamped
            for key in parents:
                holder = holder[key]
            for field in fields:
                if holder.get(field) != old_revision:
                    rpr.fail("THEME_STAMP_STALE")
                holder[field] = revision
            result[relative] = builder._canonical_json(stamped)
        if builder._fingerprint_from_payloads(result) != revision:
            rpr.fail("THEME_STAMP_INVALID")
        _require_php_bindings(builder, result)
    except builder.ThemeBuildFailure:
        rpr.fail("THEME_STAMP_INVALID")
    if revision == old_revision or any(
        old_revision.encode() in payload for payload in result.values()
    ):
        rpr.fail("THEME_STAMP_INCOMPLETE")
    return result, {"runtime_sha256": runtime_sha256, "theme_revision": revision}


def _checkpoint_bodies(candidate, payloads):
    bodies = {}
    for article in candidate["articles"]:
        if article.get("patch_source") or not article.get("body_source"):
            rpr.fail("PATCH_SOURCE_UNSUPPORTED")
        body = payloads[article["body_source"]].decode("utf-8")
        bodies[article["article_key"]] = body
    return bodies


def _gate(root, store, run_id, candidate, payloads, overlay, approval, now):
    leaks = [
        "owner_checkout:" + leak
        for leak in scan_repository_for_overlay(Path(root), overlay, approval)
    ]
    leaks += [
        "checkpoint:" + leak
        for leak in scan_revision_for_overlay(
            Path(root), candidate["checkpoint"]["commit"], overlay, approval
        )
    ]
    theme_js = payloads.get(THEME_PREFIX + "/" + JS_RELATIVE)
    findings = rpr.gate(
        overlay,
        now=now,
        bodies=_checkpoint_bodies(candidate, payloads),
        tracked_leaks=leaks,
        approval=approval,
        theme_js=theme_js.decode("utf-8") if theme_js is not None else None,
    )
    findings += [
        rpr.GateFinding("EXPIRED_RUN_NOT_PURGED", other)
        for other in expired_unpurged_runs(store, now, exclude=run_id)
    ]
    if findings:
        rpr.fail("GATE_REFUSED:" + ",".join(sorted({f.code for f in findings})))


def _derive_injected(direct, root, candidate, payloads, overlay, run_id):
    """Price-free candidate + overlay -> (injected candidate, bodies, theme payloads, package)."""
    checkpoint_bodies = _checkpoint_bodies(candidate, payloads)
    derived = copy.deepcopy({k: v for k, v in candidate.items() if k != "candidate_id"})
    price_free, injected, bodies = {}, {}, {}
    sellers, references = set(), set()
    for article in derived["articles"]:
        key, slug = article["article_key"], article["document"]["slug"]
        body = checkpoint_bodies[key]
        if article["document"]["block_markup"] != body:
            rpr.fail("BODY_NOT_CHECKPOINT")
        result = rpr.inject_body(body, overlay)
        if result.body == body:
            continue
        if ARTICLE_KEY.fullmatch(key) is None or slug in injected:
            rpr.fail("ARTICLE_KEY_INVALID")
        price_free[slug], injected[slug] = body, result.body
        sellers.update(result.seller_offer_ids)
        references.update(result.reference_offer_ids)
        article["document"]["block_markup"] = result.body
        article["body_file"] = "bodies/" + key + ".html"
        article["body_sha256"] = rpr.body_sha256(result.body)
        article["price_overlay_injected"] = True
        bodies[article["body_file"]] = result.body.encode("utf-8")
    if not injected:
        rpr.fail("NOTHING_INJECTED")
    theme, stamps = injected_theme_payloads(
        _theme_payloads(payloads), price_free, injected
    )
    full = {**payloads, **{THEME_PREFIX + "/" + p: b for p, b in theme.items()}}
    package, descriptor = direct.package_theme(
        Path(root), sorted(full), candidate["checkpoint"]["commit"], full
    )
    descriptor["old_version"] = candidate["theme"]["descriptor"]["old_version"]
    derived["theme"] = {**derived["theme"], "descriptor": descriptor}
    derived["price_overlay"] = {
        "schema": BINDING_SCHEMA,
        "mode": MODE_PUBLISH,
        "run_id": run_id,
        "base_candidate_id": candidate["candidate_id"],
        "injected_article_keys": sorted(
            a["article_key"] for a in derived["articles"] if a.get("price_overlay_injected")
        ),
        "seller_offer_ids": sorted(sellers),
        "reference_offer_ids": sorted(references),
        **stamps,
    }
    derived["candidate_id"] = direct.digest(direct.encoded(derived))
    return derived, bodies, theme, package


def _materialize(direct, root, candidate, payloads, bodies, theme, package):
    """Write a derived candidate atomically next to the price-free one (0700/0600)."""
    private = Path(root) / direct.PRIVATE
    directory = private / candidate["candidate_id"]
    direct.safe_ancestors(directory)
    if directory.exists():
        return direct.load_candidate(directory, candidate["candidate_id"]), directory
    staging = private / (".staging-" + candidate["candidate_id"])
    if staging.is_symlink():
        direct.fail("PRIVATE_PATH_INVALID")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(mode=0o700)
    for name, payload in payloads.items():
        _write_private(staging / "sources" / name, payload, staging)
    for relative, payload in theme.items():
        _write_private(
            staging / candidate["theme"]["directory"] / relative, payload, staging
        )
    for relative, payload in bodies.items():
        _write_private(staging / relative, payload, staging)
    _write_private(staging / candidate["theme"]["package_file"], package, staging)
    direct.save(staging / "candidate.json", candidate)
    staging.rename(directory)
    return direct.load_candidate(directory, candidate["candidate_id"]), directory


def prepare_publish(direct, root, keys, run_id, call):
    """prepare --theme --price-overlay-run: checkpoint (price-free) -> gate -> inject."""
    with refusals(direct):
        rpr.require_run_id(run_id)
        store = _store(root)
        overlay = _overlay(store, run_id)
        _path, approval = _approval(store, run_id)
        if approval["publish"] is not None:
            rpr.fail("APPROVAL_PUBLISH_ALREADY_USED")
        if rpr.parse_time(overlay["cache_expires_at"]) - clock() < rpr.GATE_MIN_REMAINING:
            rpr.fail("OVERLAY_VALUE_EXPIRING")
    base, base_directory = direct.prepare(root, keys, True, call)
    with refusals(direct):
        payloads = _price_free_payloads(direct, base, base_directory)
        _gate(root, store, run_id, base, payloads, overlay, approval, clock())
        derived, bodies, theme, package = _derive_injected(
            direct, root, base, payloads, overlay, run_id
        )
        return _materialize(direct, root, derived, payloads, bodies, theme, package)


def prepare_purge(direct, root, keys, run_id, call):
    """prepare --theme --price-overlay-purge: the price-free checkpoint bytes, bound to the run."""
    with refusals(direct):
        rpr.require_run_id(run_id)
        store = _store(root)
        _path, approval = _approval(store, run_id)
        publish = approval["publish"]
        if publish is None:
            rpr.fail("APPROVAL_PURGE_WITHOUT_PUBLISH")
        if approval["purge_publish"] is not None:
            rpr.fail("APPROVAL_PURGE_ALREADY_USED")
        if sorted(set(keys)) != publish.get("article_keys"):
            rpr.fail("PURGE_ARTICLE_KEYS_MISMATCH")
    base, base_directory = direct.prepare(root, keys, True, call)
    try:
        return _derive_purge(direct, root, store, run_id, publish, base, base_directory)
    except (direct.DirectFailure, OSError, ValueError):
        # The base froze the live (injected) documents as its baseline.
        store.delete_owner_direct_candidate(base["candidate_id"])
        raise


def _derive_purge(direct, root, store, run_id, publish, base, base_directory):
    with refusals(direct):
        if base["source_sha256"] != publish.get("source_sha256"):
            rpr.fail("PURGE_SOURCE_DRIFT")
        payloads = _price_free_payloads(direct, base, base_directory)
        check = _overlay_for_check(store, run_id)
        for body in _checkpoint_bodies(base, payloads).values():
            if rpr.price_free_violations(body, check):
                rpr.fail("PURGE_BODY_NOT_PRICE_FREE")
        derived = copy.deepcopy({k: v for k, v in base.items() if k != "candidate_id"})
        derived["price_overlay"] = {
            "schema": BINDING_SCHEMA,
            "mode": MODE_PURGE,
            "run_id": run_id,
            # The live (injected) documents are this base's baseline: purged with the run.
            "base_candidate_id": base["candidate_id"],
        }
        derived["candidate_id"] = direct.digest(direct.encoded(derived))
        package = (base_directory / base["theme"]["package_file"]).read_bytes()
        return _materialize(
            direct, root, derived, payloads, {}, _theme_payloads(payloads), package
        )


def preview_view(candidate):
    """Preview checks injected bodies by their own hash, as it does for patch bodies."""
    if not candidate.get("price_overlay"):
        return candidate
    view = copy.deepcopy(candidate)
    for article in view["articles"]:
        if article.get("price_overlay_injected"):
            article["patch_source"] = "price-overlay-injected-body"
    return view


def resolve_binding(direct, candidate, run_flag, purge_flag):
    if run_flag and purge_flag:
        direct.fail("PRICE_OVERLAY_FLAGS_EXCLUSIVE")
    requested = (
        (MODE_PUBLISH, run_flag)
        if run_flag
        else (MODE_PURGE, purge_flag)
        if purge_flag
        else None
    )
    bound = candidate.get("price_overlay")
    if bound is None:
        if requested is not None:
            direct.fail("PRICE_OVERLAY_CANDIDATE_UNBOUND")
        return None
    if not isinstance(bound, dict) or bound.get("schema") != BINDING_SCHEMA:
        direct.fail("PRICE_OVERLAY_BINDING_INVALID")
    if requested is None:
        direct.fail("PRICE_OVERLAY_FLAG_REQUIRED")
    if (bound.get("mode"), bound.get("run_id")) != requested:
        direct.fail("PRICE_OVERLAY_RUN_MISMATCH")
    return Binding(direct, bound)


class Binding:
    """Hooks called by the publisher before its first WordPress write and after readback."""

    def __init__(self, direct, bound):
        self.direct = direct
        self.bound = bound
        self.mode = bound["mode"]
        self.run_id = bound["run_id"]

    def precheck(self, root, candidate):
        """Read-only: refuse a used approval before any WordPress call."""
        with refusals(self.direct):
            _path, approval = _approval(_store(root), self.run_id)
            publish, purge = approval["publish"], approval["purge_publish"]
            if self.mode == MODE_PUBLISH:
                if publish is not None and publish.get("candidate_id") != candidate[
                    "candidate_id"
                ]:
                    rpr.fail("APPROVAL_PUBLISH_ALREADY_USED")
            elif publish is None:
                rpr.fail("APPROVAL_PURGE_WITHOUT_PUBLISH")
            elif purge is not None and purge.get("candidate_id") != candidate[
                "candidate_id"
            ]:
                rpr.fail("APPROVAL_PURGE_ALREADY_USED")

    def before_writes(self, root, directory, candidate, journal):
        with refusals(self.direct):
            if self.mode == MODE_PUBLISH:
                with _approval_lock(_store(root), self.run_id):
                    self._reserve_publish(root, directory, candidate)
            else:
                self._check_purge(root, directory, candidate)

    def after_readback(self, root, directory, candidate, journal, call):
        with refusals(self.direct):
            with _approval_lock(_store(root), self.run_id):
                if self.mode == MODE_PUBLISH:
                    self._verify_publish(root, candidate, journal, call)
                else:
                    self._record_purge(root, candidate, journal, call)

    # -- publish -----------------------------------------------------------

    def _reserve_publish(self, root, directory, candidate):
        direct = self.direct
        store = _store(root)
        overlay = _overlay(store, self.run_id)
        approval_path, approval = _approval(store, self.run_id)
        now = clock()
        publish = approval["publish"]
        if publish is not None:
            if publish.get("candidate_id") != candidate["candidate_id"]:
                rpr.fail("APPROVAL_PUBLISH_ALREADY_USED")
            # Resuming this candidate: values still need two hours before expiry.
            if rpr.parse_time(overlay["cache_expires_at"]) - now < rpr.GATE_MIN_REMAINING:
                rpr.fail("OVERLAY_VALUE_EXPIRING")
            return
        payloads = _price_free_payloads(direct, candidate, directory)
        _gate(root, store, self.run_id, candidate, payloads, overlay, approval, now)
        # The frozen candidate must be exactly checkpoint bytes + this overlay.
        base = copy.deepcopy(candidate)
        for article in base["articles"]:
            article["document"]["block_markup"] = payloads[article["body_source"]].decode(
                "utf-8"
            )
        base["candidate_id"] = self.bound["base_candidate_id"]
        expected, _bodies, theme, _package = _derive_injected(
            direct, root, base, payloads, overlay, self.run_id
        )
        theme_root = directory / candidate["theme"]["directory"]
        if (
            # The id covers every field (body_sha256, injected flags, stamps, descriptor).
            expected["candidate_id"] != candidate["candidate_id"]
            or [a["document"] for a in expected["articles"]]
            != [a["document"] for a in candidate["articles"]]
            or expected["theme"]["descriptor"] != candidate["theme"]["descriptor"]
            or expected["price_overlay"]["runtime_sha256"] != self.bound["runtime_sha256"]
            or any(
                direct.source_bytes(theme_root, relative) != payload
                for relative, payload in theme.items()
            )
        ):
            rpr.fail("INJECTION_MISMATCH")
        record = rpr.record_publish(
            approval,
            overlay,
            candidate_id=candidate["candidate_id"],
            article_keys=[a["article_key"] for a in candidate["articles"]],
            injected_body_sha256={
                a["article_key"]: a["body_sha256"]
                for a in candidate["articles"]
                if a.get("price_overlay_injected")
            },
            runtime_sha256=self.bound["runtime_sha256"],
            now=now,
        )
        record["publish"]["source_sha256"] = candidate["source_sha256"]
        record["publish"]["readback_verified_at"] = None
        store.write_json(approval_path, record, replace=True)

    def _verify_publish(self, root, candidate, journal, call):
        store = _store(root)
        approval_path, approval = _approval(store, self.run_id)
        publish = approval["publish"]
        if publish is None or publish.get("candidate_id") != candidate["candidate_id"]:
            rpr.fail("APPROVAL_PUBLISH_RECORD_MISSING")
        expected = publish.get("injected_body_sha256") or {}
        for article in candidate["articles"]:
            if not article.get("price_overlay_injected"):
                continue
            key = article["article_key"]
            current = call("document", {"id": journal["post_ids"][key]})
            body = current.get("block_markup")
            if not isinstance(body, str) or rpr.body_sha256(body) != expected.get(key):
                rpr.fail("READBACK_INJECTED_HASH_MISMATCH")
        if publish.get("readback_verified_at") is None:
            publish["readback_verified_at"] = rpr.iso(clock())
            store.write_json(approval_path, approval, replace=True)

    # -- purge -------------------------------------------------------------

    def _check_purge(self, root, directory, candidate):
        store = _store(root)
        _path, approval = _approval(store, self.run_id)
        publish, purge = approval["publish"], approval["purge_publish"]
        if publish is None:
            rpr.fail("APPROVAL_PURGE_WITHOUT_PUBLISH")
        if purge is not None and purge.get("candidate_id") != candidate["candidate_id"]:
            rpr.fail("APPROVAL_PURGE_ALREADY_USED")
        if sorted(a["article_key"] for a in candidate["articles"]) != publish.get(
            "article_keys"
        ) or candidate["source_sha256"] != publish.get("source_sha256"):
            rpr.fail("PURGE_SOURCE_DRIFT")
        payloads = _price_free_payloads(self.direct, candidate, directory)
        check = _overlay_for_check(store, self.run_id)
        bodies = _checkpoint_bodies(candidate, payloads)
        theme_root = directory / candidate["theme"]["directory"]
        if any(
            a["document"]["block_markup"] != bodies[a["article_key"]]
            or rpr.price_free_violations(a["document"]["block_markup"], check)
            for a in candidate["articles"]
        ) or any(
            self.direct.source_bytes(theme_root, relative) != payload
            for relative, payload in _theme_payloads(payloads).items()
        ):
            rpr.fail("PURGE_BODY_NOT_PRICE_FREE")

    def _record_purge(self, root, candidate, journal, call):
        store = _store(root)
        check = _overlay_for_check(store, self.run_id)
        for article in candidate["articles"]:
            current = call(
                "document", {"id": journal["post_ids"][article["article_key"]]}
            )
            body = current.get("block_markup")
            if (
                body != article["document"]["block_markup"]
                or rpr.price_free_violations(body, check)
            ):
                rpr.fail("PURGE_READBACK_NOT_PRICE_FREE")
        approval_path, approval = _approval(store, self.run_id)
        purge = approval["purge_publish"]
        if purge is None:
            approval = rpr.record_purge_publish(
                approval, candidate_id=candidate["candidate_id"], now=clock()
            )
            approval["purge_publish"]["base_candidate_id"] = self.bound[
                "base_candidate_id"
            ]
            store.write_json(approval_path, approval, replace=True)
        elif purge.get("candidate_id") != candidate["candidate_id"]:
            rpr.fail("APPROVAL_PURGE_ALREADY_USED")
        delete_local_injected_copies(
            self.direct, root, store, approval["publish"].get("candidate_id")
        )
        store.delete_owner_direct_candidate(self.bound["base_candidate_id"])


def delete_local_injected_copies(direct, root, store, candidate_id):
    """Remove the injected candidate directory and the preview's frozen copy of its theme."""
    if not isinstance(candidate_id, str) or len(candidate_id) != 64:
        return
    directory = Path(root) / direct.PRIVATE / candidate_id
    theme = directory / "theme"
    if theme.is_dir() and not theme.is_symlink():
        from scripts.raos_wordpress_direct_preview import _theme_tree

        frozen = Path(root) / PREVIEW_PRIVATE / ("theme-" + _theme_tree(theme))
        direct.safe_ancestors(frozen)
        if frozen.is_dir():
            shutil.rmtree(frozen)
    store.delete_owner_direct_candidate(candidate_id)
