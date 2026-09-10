"""One explicit release workflow. Planning is read-only; preparation is local only."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import UTC, datetime
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "scripts", ROOT / "python"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from scripts.raos_build_core import (  # noqa: E402
    OWNER_PRIVATE_OWNER_IDS,
    affected_generation_owners,
    changed_paths,
    discover_registry,
    write_active_manifest,
)
from scripts.raos_test_plan import create_plan  # noqa: E402
from scripts.raos_wordpress_browser_plan import browser_plan  # noqa: E402
from scripts import raos_wordpress_verification as verification  # noqa: E402
from scripts import raos_wordpress_environment as environment_owner  # noqa: E402

REPORT = ROOT / "output/publication/release-preparation.v2.json"
STAGES = ("plan", "prepare", "propose", "apply", "readback")


class WorkflowFailure(ValueError):
    """Bounded, operator-facing diagnostic without private adapter values."""


def request_scope(arguments: argparse.Namespace) -> dict[str, Any]:
    result = {
        key: getattr(arguments, key)
        for key in (
            "articles",
            "snapshot_name",
            "include_theme",
            "update_policies",
            "runtime_transition",
        )
    }
    for key in ("include_home", "reader_pages", "reader_privacy"):
        if getattr(arguments, key, None):
            result[key] = getattr(arguments, key)
    return result


def restore_selection(arguments: argparse.Namespace, state: dict[str, Any]) -> None:
    # Only restore an exact user selection, never silently expand the target set.
    if (
        arguments.candidate is None
        and (
            arguments.articles
            or arguments.include_theme
            or getattr(arguments, "reader_pages", None)
            or getattr(arguments, "reader_privacy", False)
        )
        and arguments.snapshot_name
        and state.get("request_scope") == request_scope(arguments)
        and state.get("candidate")
    ):
        candidate = Path(state["candidate"])
        port = importlib.import_module("raos_wordpress_incremental_publication")
        try:
            port.prepare_candidate(candidate, now=datetime.now(UTC))
        except ValueError, RuntimeError, OSError, KeyError, TypeError:
            # An edited/expired subject needs a new candidate. Preserve the old
            # bytes and reviews; an explicitly selected candidate still fails.
            return
        arguments.candidate = candidate
    if arguments.candidate is not None and state.get("candidate") == str(
        arguments.candidate
    ):
        if arguments.preview_fixture is None and state.get("preview_fixture"):
            arguments.preview_fixture = Path(state["preview_fixture"])


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    result.add_argument("stage", nargs="?", choices=STAGES, default="plan")
    result.add_argument("--candidate", "--incremental-candidate", type=Path)
    result.add_argument("--preview-fixture", "--incremental-preview-fixture", type=Path)
    result.add_argument("--articles", help="explicit existing slugs, or all")
    result.add_argument("--snapshot-name")
    result.add_argument("--include-theme", action="store_true")
    result.add_argument("--include-home", action="store_true")
    result.add_argument("--reader-pages", help="explicit registered hub slugs, comma separated")
    result.add_argument("--reader-privacy", action="store_true")
    result.add_argument("--reader-measurement-readback", action="store_true", help="read-only inspection of the separately approved enabled reader revision")
    result.add_argument("--update-policies", choices=("none", "all"), default="none")
    result.add_argument(
        "--runtime-transition",
        default="strict",
        choices=("strict", "sitekit-dns-prefetch-removal-v1"),
    )
    result.add_argument("--implementation-execution-id", action="append", default=[])
    result.add_argument("--base", default="origin/main")
    result.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    result.add_argument("--json", action="store_true")
    return result


def previous_report() -> dict[str, Any]:
    try:
        value = json.loads(verification.read_regular(REPORT))
        return value if isinstance(value, dict) else {}
    except OSError, ValueError:
        return {}


def save_report(value: dict[str, Any]) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if REPORT.is_symlink():
        raise WorkflowFailure("preparation report is a symlink")
    descriptor, name = tempfile.mkstemp(prefix=".preparation-", dir=REPORT.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(verification.canonical(value))
        temporary.replace(REPORT)
    finally:
        temporary.unlink(missing_ok=True)


def check_inputs(selected: Any) -> dict[str, str]:
    selection = selected.as_json()
    for key in ("changed_files", "reasons", "full_reasons"):
        selection.pop(key)
    return {
        "source_tree_sha256": verification.source_fingerprint(ROOT),
        "selection_sha256": verification.digest(verification.canonical(selection)),
    }


def verification_inputs(base: str = "origin/main") -> dict[str, str]:
    head = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    selected = create_plan(
        ROOT, discover_registry(), changed_paths(base=base), critical=True
    )
    return {**check_inputs(selected), "head_sha": head}


def validate_explicit_selection(arguments: argparse.Namespace, manifest: Mapping[str, Any]) -> None:
    from raos_reader_release_pages import selected_page_slugs
    from raos_wordpress_publication_request import load_articles
    articles = getattr(arguments, "articles", None)
    if articles and {row.production_slug for row in load_articles(articles)} != {row["slug"] for row in manifest["articles"]}:
        raise WorkflowFailure("article selection differs from the frozen candidate")
    explicit_pages = any(getattr(arguments, key, None) for key in ("include_home", "reader_pages", "reader_privacy")) or getattr(arguments, "update_policies", "none") == "all"
    if explicit_pages:
        selected = set(selected_page_slugs(ROOT, arguments))
        if getattr(arguments, "update_policies", "none") == "all":
            selected.update({"privacy-policy", "about-ad-policy", "comparison-policy"})
        frozen = set(manifest["shared_artifacts"]) - {"theme", "seo", "plugins"}
        if selected != frozen:
            raise WorkflowFailure("page selection differs from the frozen candidate")
    if getattr(arguments, "include_theme", False) and "theme" not in manifest["shared_artifacts"]:
        raise WorkflowFailure("theme selection differs from the frozen candidate")


def validate_frozen_selection(arguments: argparse.Namespace) -> None:
    if not (arguments.articles or arguments.include_home or arguments.reader_pages
            or arguments.reader_privacy or arguments.include_theme
            or arguments.update_policies == "all"):
        return
    port = importlib.import_module("raos_wordpress_incremental_publication")
    port._candidate_directory(arguments.candidate)
    manifest, raw = port.read_json(arguments.candidate, "manifest.v1.json")
    if raw != port.canonical(manifest) or port.digest(raw) != arguments.candidate.name:
        raise WorkflowFailure("frozen candidate hash differs from its directory")
    validate_explicit_selection(arguments, manifest)


def plan(arguments: argparse.Namespace) -> tuple[dict[str, Any], Any, Any]:
    registry = discover_registry()
    changes = changed_paths(base=arguments.base)
    selected = create_plan(ROOT, registry, changes, critical=True)
    state = previous_report()
    restore_selection(arguments, state)
    inputs = check_inputs(selected)
    fast = state.get("checks", {}).get("fast", {})
    reuse = verification.reusable(
        fast, check_id="fast", inputs=inputs, root=ROOT, now=datetime.now(UTC)
    )
    missing: list[str] = []
    targets: list[str] = []
    browser = None
    browser_reuse = False
    environment_plan = environment_owner.compare({}, {})
    if arguments.candidate is not None:
        port = importlib.import_module("raos_wordpress_incremental_publication")
        prepared = port.prepare_candidate(arguments.candidate, now=datetime.now(UTC))
        environment_plan = environment_owner.compare(
            prepared.snapshot, prepared.manifest
        )
        targets = [row["slug"] for row in prepared.manifest["articles"]]
        validate_explicit_selection(arguments, prepared.manifest)
        targets += sorted(set(prepared.preparation["production_documents"]) - set(targets))
        inventory = json.loads(
            (
                ROOT
                / "changes/editorial-portfolio-v3/generated/wordpress-audit-inventory.v3.json"
            ).read_text()
        )
        markup = None
        if arguments.preview_fixture:
            from raos.application.finance.editorial_economics_v3 import (
                read_private_bytes,
            )

            markup = {
                row["article_id"]: read_private_bytes(
                    arguments.preview_fixture / "articles",
                    f"{row['production_path'].strip('/')}.html",
                ).decode()
                for row in inventory["surfaces"]
                if row["kind"] == "article"
            }
        browser = browser_plan(
            inventory,
            prepared.manifest,
            article_markup=markup,
            changed_files=[p.as_posix() for p in changes],
        )
        if arguments.preview_fixture:
            browser_dir = str(ROOT / "changes/wordpress-local-preview-v1/browser")
            if browser_dir not in sys.path:
                sys.path.insert(0, browser_dir)
            report_owner = importlib.import_module("mixed_audit_report")
            origin = preview_origin(dict(os.environ))
            # Compare the actual candidate to the fixture before any generation.
            report_owner.current_inputs(
                arguments.preview_fixture,
                origin,
                candidate_path=arguments.candidate,
                include_runtime=False,
            )
            try:
                report_owner.validate_report(
                    report_owner.REPORT,
                    fixture_root=arguments.preview_fixture,
                    origin=origin,
                    candidate_path=arguments.candidate,
                )
                browser_reuse = True
            except (
                ValueError,
                RuntimeError,
                OSError,
                KeyError,
                TypeError,
                subprocess.SubprocessError,
            ):
                pass
    else:
        if arguments.articles:
            from raos_wordpress_publication_request import load_articles

            targets = [row.production_slug for row in load_articles(arguments.articles)]
        from raos_reader_release_pages import selected_page_slugs
        page_targets = selected_page_slugs(ROOT, arguments)
        targets += page_targets
        if (
            not arguments.articles
            and not arguments.include_theme
            and not (
                getattr(arguments, "reader_pages", None)
                or getattr(arguments, "reader_privacy", False)
            )
        ):
            missing.append("explicit articles, registered reader pages or a frozen candidate")
        if not arguments.snapshot_name:
            missing.append("an existing bounded MCP snapshot")
    return (
        {
            "schema": "RAOS_WORDPRESS_RELEASE_PLAN_V2",
            "publication_authority": False,
            "publication_profile": "verified-incremental",
            "link_mode": "standard-api",
            "quality_audit_mode": "codex-owner",
            "targets": targets,
            "verification": selected.as_json(),
            "browser": browser,
            "environment": environment_plan,
            "reuse": {
                "fast": reuse,
                "browser": browser_reuse,
                "browser_reason": "matching original results within two hours"
                if browser_reuse
                else "missing, changed, failed, incomplete or expired browser inputs/results",
                "reason": "matching original result"
                if reuse
                else "missing, changed, failed or expired result",
            },
            "missing_inputs": missing,
            "next_action": "supply missing inputs" if missing else "prepare",
        },
        selected,
        registry,
    )


def _run(command: list[str], environment: dict[str, str]) -> None:
    # Match the shared build runner so every selected owner can import raos.
    environment = {
        **environment,
        "PYTHONPATH": os.pathsep.join(
            str(path)
            for path in (ROOT, ROOT / "python", environment.get("PYTHONPATH", ""))
            if path
        ),
    }
    subprocess.run(command, cwd=ROOT, env=environment, check=True)


def generate_once(
    arguments: argparse.Namespace, registry: Any, environment: dict[str, str]
) -> None:
    """Stamp the tracked theme at its dependency boundary, without creating a ZIP."""
    owners = affected_generation_owners(registry, changed_paths(base=arguments.base))
    theme_owner = "build_st1704_self_hosted_theme"
    stamped = False
    for owner in owners:
        # The source stamp is pure; packaging remains excluded from this workflow.
        if owner in OWNER_PRIVATE_OWNER_IDS:
            continue
        if (
            owner
            in {"build_st1704_self_hosted_editorial_manifest", "build_wordpress_mcp_v1"}
            and not stamped
        ):
            _run(
                [
                    sys.executable,
                    "scripts/build_st1704_self_hosted_theme.py",
                    "--generate",
                ],
                environment,
            )
            stamped = True
        _run(list(registry[owner].command()), environment)
    if theme_owner in owners and not stamped:
        _run(
            [sys.executable, "scripts/build_st1704_self_hosted_theme.py", "--generate"],
            environment,
        )
    if owners:
        write_active_manifest(registry)


def prepare(arguments: argparse.Namespace) -> dict[str, Any]:
    # All pure candidate checks precede generation, tests, browsers and reviews.
    planned, selected, registry = plan(arguments)
    if planned["missing_inputs"]:
        raise WorkflowFailure("missing inputs: " + "; ".join(planned["missing_inputs"]))
    if (
        arguments.candidate is not None
        and (arguments.candidate / "publication-request.v1.json").exists()
    ):
        raise WorkflowFailure(
            "registered candidate is immutable; use its apply/readback path"
        )
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": "/tmp",
        "RAOS_WORDPRESS_PUBLICATION_PROFILE": "verified-incremental",
        "RAOS_WORDPRESS_LINK_MODE": "standard-api",
        "RAOS_WORDPRESS_BROWSER_WORKERS": str(arguments.workers),
    }
    state = previous_report()
    port = importlib.import_module("raos_wordpress_incremental_publication")
    if arguments.candidate is None:
        # Snapshot, post identities, scope, public markup, supporting sources and
        # shared inputs use the same reconstruction as proposal, before any work.
        port.candidate_owner.inspect_candidate(arguments)
    if state.get("generation_source_sha256") != verification.source_fingerprint(ROOT):
        generate_once(arguments, registry, environment)
    if arguments.candidate is None:
        arguments.candidate = port.candidate_owner.create_candidate(arguments)
    prepared = port.prepare_candidate(arguments.candidate, now=datetime.now(UTC))
    if arguments.preview_fixture is None:
        preview_owner = importlib.import_module("raos_wordpress_incremental_preview")
        arguments.preview_fixture = preview_owner.create_preview(
            argparse.Namespace(
                candidate=arguments.candidate,
                snapshot_name=prepared.preparation["snapshot_name"],
                articles=",".join(row["slug"] for row in prepared.manifest["articles"]),
                update_policies=",".join(
                    sorted(
                        set(prepared.manifest["shared_artifacts"])
                        & {"about-ad-policy", "comparison-policy", "privacy-policy"}
                        - set(prepared.manifest.get("reader_pages", {}))
                    )
                )
                or "none",
                include_home="home" in prepared.manifest["shared_artifacts"],
                reader_pages=",".join(sorted(slug for slug, row in prepared.manifest.get("reader_pages", {}).items() if row["kind"] == "hub")) or None,
                reader_privacy="privacy-policy" in prepared.manifest.get("reader_pages", {}),
                home_mode="shared-theme-candidate"
                if "theme" in prepared.manifest["shared_artifacts"]
                else "preserve-live-baseline",
                materialize_baseline_images=True,
            )
        )
    environment.update(
        RAOS_WORDPRESS_RELEASE_CANDIDATE=str(arguments.candidate),
        RAOS_WORDPRESS_PREVIEW_FIXTURE_ROOT=str(arguments.preview_fixture),
    )
    browser_dir = str(ROOT / "changes/wordpress-local-preview-v1/browser")
    if browser_dir not in sys.path:
        sys.path.insert(0, browser_dir)
    report_owner = importlib.import_module("mixed_audit_report")
    origin = preview_origin(environment)
    report_owner.current_inputs(
        arguments.preview_fixture,
        origin,
        candidate_path=arguments.candidate,
        include_runtime=False,
    )
    # Generation may change the selection; use the final source tree once.
    planned, selected, registry = plan(arguments)
    state["generation_source_sha256"] = verification.source_fingerprint(ROOT)
    state.update(
        schema="RAOS_WORDPRESS_RELEASE_PREPARATION_V2",
        plan=planned,
        candidate=str(arguments.candidate),
        request_scope=request_scope(arguments),
        publication_authority=False,
    )
    checks = state.setdefault("checks", {})
    inputs = check_inputs(selected)
    if not verification.reusable(
        checks.get("fast", {}),
        check_id="fast",
        inputs=inputs,
        root=ROOT,
        now=datetime.now(UTC),
    ):
        checks["fast"] = verification.run_check(
            ROOT,
            [
                sys.executable,
                "scripts/raos_build.py",
                "--base",
                arguments.base,
                "fast",
                "--critical",
            ],
            check_id="fast",
            inputs=inputs,
            directory=ROOT / "output/publication/checks",
            environment=environment,
        )
        save_report(state)
        if (
            checks["fast"]["exit_code"]
            or verification.source_fingerprint(ROOT) != inputs["source_tree_sha256"]
        ):
            raise WorkflowFailure(
                "focused checks failed or inputs changed; inspect the original check output"
            )
    preview = ROOT / "changes/wordpress-local-preview-v1/bin/wordpress_preview.sh"
    status = subprocess.run(
        [str(preview), "status"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        check=False,
    )
    if status.returncode or b"RAOS_WORDPRESS_PREVIEW_READY" not in status.stdout:
        _run(["make", "wordpress-preview-up"], environment)
    observed_environment = environment_owner.capture_local(ROOT, environment)
    if observed_environment["local"].get("script_debug") is not False:
        # Existing containers can still use the previous Compose configuration.
        _run(["make", "wordpress-preview-up"], environment)
        observed_environment = environment_owner.capture_local(ROOT, environment)
        if observed_environment["local"].get("script_debug") is not False:
            raise WorkflowFailure("local serving configuration was not refreshed")
    state["environment"] = {
        **environment_owner.compare(
            prepared.snapshot, prepared.manifest, observed_environment["local"]
        ),
        "local_observed_at": observed_environment["captured_at"],
    }
    browser_dir = str(ROOT / "changes/wordpress-local-preview-v1/browser")
    if browser_dir not in sys.path:
        sys.path.insert(0, browser_dir)
    report_owner = importlib.import_module("mixed_audit_report")
    # The actual per-worktree origin is determined by the preview owner.
    origin = preview_origin(environment)
    try:
        report_owner.validate_report(
            report_owner.REPORT,
            fixture_root=arguments.preview_fixture,
            origin=origin,
            candidate_path=arguments.candidate,
        )
    except (
        ValueError,
        RuntimeError,
        OSError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ):
        _run(["make", "wordpress-preview-sync"], environment)
        _run(["make", "wordpress-preview-check"], environment)
    browser_report = report_owner.validate_report(
        report_owner.REPORT,
        fixture_root=arguments.preview_fixture,
        origin=origin,
        candidate_path=arguments.candidate,
    )
    state["browser"] = {
        "report": str(report_owner.REPORT),
        "captured_at": browser_report["captured_at"],
        "screenshots": len(browser_report["screenshots"]),
    }
    try:
        state["required_ci"] = verification.required_ci(ROOT)
    except ValueError, subprocess.SubprocessError:
        state["required_ci"] = {"conclusion": "NOT_VERIFIED"}
    state["next_action"] = "independent reviews and required CI, then owner proposal"
    state["preview_fixture"] = str(arguments.preview_fixture)
    state["preview_origin"] = origin
    state["verification_base"] = arguments.base
    save_report(state)
    return state


def preview_origin(environment: dict[str, str]) -> str:
    # Match the established preview owner's worktree-derived, loopback-only port.
    import hashlib

    identity = hashlib.sha256(str(ROOT.resolve()).encode()).hexdigest()
    port = int(
        environment.get(
            "RAOS_WORDPRESS_PREVIEW_PORT", str(20000 + int(identity[:4], 16) % 20000)
        )
    )
    if not 1024 <= port <= 65535:
        raise WorkflowFailure("invalid local preview port")
    return f"http://127.0.0.1:{port}"


def main(argv: list[str] | None = None) -> int:
    supplied = list(sys.argv[1:] if argv is None else argv)
    if supplied and (supplied[0] == "direct" or supplied[:2] == ["--publication-profile", "owner-direct-v1"]):
        from raos_wordpress_direct_publish import main as direct_main

        return direct_main(supplied[1:] if supplied[0] == "direct" else supplied[2:])
    arguments = parser().parse_args(argv)
    try:
        if arguments.reader_measurement_readback and arguments.stage != "readback":
            raise WorkflowFailure("reader measurement ON inspection is readback-only")
        restore_selection(arguments, previous_report())
        if not 1 <= arguments.workers <= 32:
            raise WorkflowFailure("workers must be within 1..32")
        if arguments.stage == "plan":
            result = plan(arguments)[0]
        elif arguments.stage == "prepare":
            result = prepare(arguments)
        else:
            if arguments.candidate is None:
                raise WorkflowFailure("an explicit candidate is required")
            validate_frozen_selection(arguments)
            if arguments.stage == "propose" and not (
                (arguments.candidate / "audit/report.v2.json").exists()
                or (arguments.candidate / "publication-request.v1.json").exists()
            ):
                raise WorkflowFailure(
                    "new proposals require the two independent V2 review reports"
                )
            from raos_wordpress_publication_request import parser as legacy_parser
            from raos_wordpress_incremental_publication import execute_cli

            legacy = legacy_parser().parse_args(
                [
                    "--publication-profile",
                    "verified-incremental",
                    "--link-mode",
                    "standard-api",
                    "--quality-audit-mode",
                    "codex-owner",
                    "--incremental-stage",
                    arguments.stage,
                    "--incremental-candidate",
                    str(arguments.candidate),
                ]
            )
            legacy.incremental_preview_fixture = arguments.preview_fixture
            legacy.incremental_base = arguments.base
            legacy.incremental_reader_measurement_readback = arguments.reader_measurement_readback
            legacy.incremental_implementation_execution_id = (
                arguments.implementation_execution_id
            )
            receipt = execute_cli(legacy)
            result = {"stage": arguments.stage, "receipt": str(receipt)}
        if arguments.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif arguments.stage == "plan":
            selected = result["verification"]
            print(f"Targets: {', '.join(result['targets']) or 'not selected'}")
            print(
                f"Checks: {len(selected['python_tests'])} Python files; {len(selected['generators'])} generators; full={selected['full']}"
            )
            print(f"Reuse: fast={result['reuse']['fast']}; {result['reuse']['reason']}")
            for missing in result["missing_inputs"]:
                print(f"Missing: {missing}")
            print(
                "Use plan --json for selection reasons; prepare performs local work only."
            )
        else:
            print(
                json.dumps(
                    result
                    if arguments.stage != "prepare"
                    else {
                        "candidate": result["candidate"],
                        "preview_origin": result["preview_origin"],
                        "browser": result["browser"],
                        "next_action": result["next_action"],
                        "report": str(REPORT),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return 0
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as error:
        # Do not print provider bodies or private input values from adapter exceptions.
        reason = str(error)
        if not isinstance(error, WorkflowFailure) and not re.fullmatch(
            r"[A-Z][A-Z0-9_]{2,120}", reason
        ):
            reason = f"{type(error).__name__}; inspect the preparation report and original check output"
        if arguments.stage == "plan" and arguments.json:
            print(
                json.dumps(
                    {
                        "schema": "RAOS_WORDPRESS_RELEASE_PLAN_V2",
                        "publication_authority": False,
                        "missing_inputs": [reason],
                        "next_action": "repair inputs and repeat plan",
                    },
                    ensure_ascii=False,
                )
            )
            return 69
        print(f"RAOS_WORDPRESS_RELEASE_FAILED: {reason}", file=sys.stderr)
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
