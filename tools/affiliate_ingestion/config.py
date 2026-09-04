from __future__ import annotations

import json
import math
import os
import stat
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from .providers import PROVIDERS, provider_skeleton

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "raos" / "affiliate-networks.json"
DEFAULT_OUTPUT_ROOT = Path("var") / "affiliate_ingestion"
_SECRET_FIELD_NAMES = frozenset(
    {
        "password",
        "token",
        "api_key",
        "client_secret",
        "secret",
        "secret_headers",
        "account_id",
        "client_id",
        "username",
        "endpoint",
        "token_url",
        "headers",
        "query",
        "path",
    }
)


class ConfigError(ValueError):
    pass


def initial_config() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "storage": {
            "root": str(DEFAULT_OUTPUT_ROOT),
            "max_response_bytes": 50 * 1024 * 1024,
            "max_uncompressed_bytes": 200 * 1024 * 1024,
        },
        "http": {
            "timeout_seconds": 30,
            "max_attempts": 4,
            "minimum_interval_seconds": 0.5,
            "user_agent": "RAOS-AffiliateIngestion/1.0",
            "allow_private_network": False,
        },
        "providers": {
            key: provider_skeleton(manifest) for key, manifest in PROVIDERS.items()
        },
    }


def _check_secret_file_permissions(path: Path) -> None:
    if os.name == "nt":
        # POSIX mode bits are not authoritative on Windows.  The file remains
        # outside the repository under the current user's profile by default.
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ConfigError(
            f"Refusing owner-secret config with permissions {oct(mode)}; "
            f"run: chmod 600 {path}"
        )


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise ConfigError(
            f"Configuration does not exist: {config_path}. "
            "Run `python -m tools.affiliate_ingestion init-config`."
        )
    if not config_path.is_file():
        raise ConfigError(f"Configuration path is not a file: {config_path}")
    _check_secret_file_permissions(config_path)
    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Unable to read configuration: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ConfigError("Top-level configuration must be a JSON object")
    merged = deep_merge(initial_config(), loaded)
    validate_config(merged)
    return merged


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = deep_merge(result[key], value)  # type: ignore[arg-type]
        else:
            result[key] = deepcopy(value)
    return result


def atomic_write_config(
    path: Path | str,
    data: Mapping[str, Any],
    *,
    overwrite: bool = True,
) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise ConfigError(f"Configuration already exists: {target}")
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temp = Path(temp_name)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
        if os.name != "nt":
            target.chmod(0o600)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return target


def resolve_indirections(value: Any) -> Any:
    """Resolve `env:NAME` values recursively without mutating input."""
    if isinstance(value, str) and value.startswith("env:"):
        name = value[4:].strip()
        if not name:
            raise ConfigError("Empty environment-variable indirection")
        try:
            return os.environ[name]
        except KeyError as exc:
            raise ConfigError(
                f"Required environment variable is not set: {name}"
            ) from exc
    if isinstance(value, list):
        return [resolve_indirections(item) for item in value]
    if isinstance(value, Mapping):
        return {key: resolve_indirections(item) for key, item in value.items()}
    return value


def redact(value: Any, *, key: str = "") -> Any:
    lowered = key.casefold()
    if any(secret in lowered for secret in _SECRET_FIELD_NAMES):
        return "***REDACTED***" if value not in (None, "", {}) else value
    if isinstance(value, Mapping):
        return {str(k): redact(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema_version") != 1:
        raise ConfigError("Unsupported configuration schema_version; expected 1")
    for section in ("storage", "http"):
        if not isinstance(config.get(section), Mapping):
            raise ConfigError(f"{section} must be an object")
    for section, field, minimum in (
        ("storage", "max_response_bytes", 1),
        ("storage", "max_uncompressed_bytes", 1),
        ("http", "timeout_seconds", 0.01),
        ("http", "max_attempts", 1),
        ("http", "minimum_interval_seconds", 0),
    ):
        value = config[section].get(field)
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or value < minimum
        ):
            raise ConfigError(f"{section}.{field} must be a finite number >= {minimum}")
    if type(config["http"].get("allow_private_network", False)) is not bool:
        raise ConfigError("http.allow_private_network must be a boolean")
    providers = config.get("providers")
    if not isinstance(providers, Mapping):
        raise ConfigError("providers must be an object")
    missing = set(PROVIDERS) - set(providers)
    if missing:
        raise ConfigError(f"Missing provider sections: {', '.join(sorted(missing))}")
    for key, raw in providers.items():
        if key not in PROVIDERS:
            continue
        if not isinstance(raw, Mapping):
            raise ConfigError(f"providers.{key} must be an object")
        if type(raw.get("enabled", False)) is not bool:
            raise ConfigError(f"providers.{key}.enabled must be a boolean")
        if not isinstance(raw.get("auth", {}), Mapping):
            raise ConfigError(f"providers.{key}.auth must be an object")
        for field in ("headers", "query", "pagination"):
            if not isinstance(raw.get(field, {}), Mapping):
                raise ConfigError(f"providers.{key}.{field} must be an object")
        resources = raw.get("resources", {})
        if not isinstance(resources, Mapping):
            raise ConfigError(f"providers.{key}.resources must be an object")
        for resource_name, resource in resources.items():
            if not isinstance(resource, Mapping):
                raise ConfigError(
                    f"providers.{key}.resources.{resource_name} must be an object"
                )
            if type(resource.get("enabled", False)) is not bool:
                raise ConfigError("Resource enabled must be a boolean")
            for field in ("auth", "headers", "query", "pagination"):
                if not isinstance(resource.get(field, raw.get(field, {})), Mapping):
                    raise ConfigError(f"Resource {field} must be an object")
            if resource.get("mode", raw.get("mode", "api")) not in {
                "api",
                "feed",
                "file",
            }:
                raise ConfigError("Unsupported resource mode")
            if str(resource.get("method", raw.get("method", "GET"))).upper() != "GET":
                raise ConfigError("Provider ingestion supports only GET requests")
            pagination = resource.get("pagination", raw.get("pagination", {}))
            if pagination.get("type", "none") not in {
                "none",
                "page",
                "offset",
                "cursor",
                "next_url",
            }:
                raise ConfigError("Unsupported pagination type")
            for field in ("max_pages", "page_size"):
                value = pagination.get(field, 1)
                if type(value) is not int or value < 1:
                    raise ConfigError(f"pagination.{field} must be a positive integer")


def _environment_errors(value: Any) -> list[str]:
    if isinstance(value, str) and value.startswith("env:"):
        name = value[4:].strip()
        if not name or not os.environ.get(name):
            return ["required environment variable is missing or empty"]
    if isinstance(value, Mapping):
        return [error for item in value.values() for error in _environment_errors(item)]
    if isinstance(value, list):
        return [error for item in value for error in _environment_errors(item)]
    return []


def provider_diagnostics(config: Mapping[str, Any], provider_key: str) -> list[str]:
    provider = config["providers"][provider_key]
    errors: list[str] = []
    if not provider.get("enabled"):
        errors.append("provider is disabled")
    if not str(provider.get("account_id", "")).strip():
        errors.append("account_id is empty")
    required_by_auth = {
        "bearer": ("token",),
        "api_key_header": ("api_key",),
        "api_key_query": ("api_key",),
        "basic": ("username", "password"),
        "oauth2_client_credentials": ("token_url", "client_id", "client_secret"),
        "custom_headers": ("secret_headers",),
        "none": (),
    }
    enabled_resources = 0
    for resource_name, resource in provider.get("resources", {}).items():
        if not isinstance(resource, Mapping) or not resource.get("enabled"):
            continue
        enabled_resources += 1
        mode = str(resource.get("mode", provider.get("mode", "api")))
        if mode in {"api", "feed"}:
            # Imported lazily because the client also consumes this configuration.
            from .client import EndpointValidator, FetchError

            auth = {**provider.get("auth", {}), **resource.get("auth", {})}
            auth_type = str(auth.get("type", "none"))
            if auth_type not in required_by_auth:
                errors.append("unsupported auth.type")
            else:
                for field in required_by_auth[auth_type]:
                    if auth.get(field) in (None, "", {}):
                        errors.append(
                            f"auth.{field} is empty for auth.type={auth_type}"
                        )
            errors.extend(_environment_errors(auth))
            for field in ("headers", "query"):
                effective = {**provider.get(field, {}), **resource.get(field, {})}
                errors.extend(_environment_errors(effective))
            for endpoint in (
                resource.get("endpoint", ""),
                auth.get("token_url", "")
                if auth_type == "oauth2_client_credentials"
                else "",
            ):
                if endpoint:
                    try:
                        EndpointValidator.validate_syntax(str(endpoint))
                    except FetchError as exc:
                        errors.append(str(exc))
        if mode in {"api", "feed"} and not str(resource.get("endpoint", "")).strip():
            errors.append(f"resources.{resource_name}.endpoint is empty")
        if mode == "file" and not str(resource.get("path", "")).strip():
            errors.append(f"resources.{resource_name}.path is empty")
    if enabled_resources == 0:
        errors.append("no resource is enabled")
    return errors
