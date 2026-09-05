"""Explain local/production parity from existing observations, without live writes."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import subprocess
from typing import Any


def _field(value: Mapping[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        current = current.get(key) if isinstance(current, Mapping) else None
    if type(current) is bool or current is None:
        return current
    if isinstance(current, str) and re.fullmatch(r"[a-zA-Z0-9._-]{1,128}", current):
        return current
    return None


def compare(
    snapshot: Mapping[str, Any],
    manifest: Mapping[str, Any],
    local: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """A difference report, not an extra approval or a claim of full host parity."""
    local = local or {}
    site = snapshot.get("site_status", {})
    deployment = snapshot.get("deployment_status", {})
    components = []
    for name, path, production in (
        ("wordpress", ("wordpress_version",), _field(site, "wordpress_version")),
        ("php", ("php_version",), _field(deployment, "runtime", "php_version")),
        ("theme", ("theme", "tree_sha256"), _field(deployment, "theme", "tree_sha256")),
        ("yoast", ("yoast", "version"), _field(site, "yoast", "version")),
        (
            "yoast_settings",
            ("yoast", "settings_exact"),
            _field(site, "yoast", "settings_exact"),
        ),
        (
            "measurement",
            ("measurement", "plugin_active"),
            _field(site, "measurement", "plugin_active"),
        ),
    ):
        observed = _field(local, *path)
        status = "NOT_OBSERVED"
        if observed is not None and production is not None:
            status = "MATCH" if observed == production else "DIFFERENT"
            if (
                name == "theme"
                and status == "DIFFERENT"
                and observed == _field(manifest, "shared_artifacts", "theme", "sha256")
            ):
                status = "SELECTED_CHANGE"
        components.append(
            {
                "component": name,
                "local": observed,
                "production": production,
                "status": status,
            }
        )
    return {
        "schema": "RAOS_WORDPRESS_ENVIRONMENT_COMPARISON_V1",
        "publication_authority": False,
        "production_observed_at": snapshot.get("captured_at"),
        "components": components,
        "local_defaults": {
            "link_mode": "standard-api",
            "measurement": "OFF",
            "script_debug": False,
        },
        "local_configuration": {
            "script_debug": _field(local, "script_debug"),
            "status": "NOT_OBSERVED"
            if _field(local, "script_debug") is None
            else "MATCH"
            if local["script_debug"] is False
            else "DIFFERENT",
            "refresh_command": "make wordpress-preview-up",
        },
        "intentional_local_differences": [
            "loopback origin and local-preview URL aliases",
            "noindex, visible local banner, disabled email and external HTTP",
            "local-only accounts, secrets, database and recorded media",
        ],
        "not_observed": [
            "production parent-theme version and complete plugin inventory",
            "production database, web server, cache/CDN and general display options",
        ],
        "content_workflow": "edit local tracked sources; review frozen candidate; apply its exact approved payload and read back",
    }


def capture_local(root: Path, environment: dict[str, str]) -> dict[str, Any]:
    result = subprocess.run(
        [
            str(root / "changes/wordpress-local-preview-v1/bin/wordpress_preview.sh"),
            "environment",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    if len(result.stdout) > 16384:
        raise ValueError("RAOS_WORDPRESS_LOCAL_ENVIRONMENT_INVALID")
    value = json.loads(result.stdout)
    if (
        not isinstance(value, dict)
        or value.get("schema") != "RAOS_WORDPRESS_LOCAL_ENVIRONMENT_V1"
    ):
        raise ValueError("RAOS_WORDPRESS_LOCAL_ENVIRONMENT_INVALID")
    return {"captured_at": datetime.now(UTC).isoformat(), "local": value}
