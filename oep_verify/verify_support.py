"""Shared helpers for local verification scripts."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from jsonschema.exceptions import SchemaError, ValidationError
except ModuleNotFoundError as exc:  # pragma: no cover - exercised only in unprepared envs
    raise RuntimeError(
        "jsonschema is required for verification; install project dependencies in a virtualenv "
        "with `python -m pip install -e '.[dev]'`"
    ) from exc


JsonObject = dict[str, Any]
TREE_DIGEST_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
    }
)
TREE_DIGEST_EXCLUDED_NAMES = frozenset(
    {
        ".coverage",
        ".DS_Store",
    }
)
TREE_DIGEST_EXCLUDED_SUFFIXES = (
    ".db",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
)


def load_json_object(path: Path) -> JsonObject:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_json_object(value: object, message: str) -> JsonObject:
    if not isinstance(value, dict):
        raise AssertionError(message)
    return cast(JsonObject, value)


def require_json_list(value: object, message: str) -> list[Any]:
    if not isinstance(value, list):
        raise AssertionError(message)
    return value


def require_string(value: object, message: str) -> str:
    if not isinstance(value, str):
        raise AssertionError(message)
    return value


def parse_datetime(value: object, field: str) -> datetime:
    text = require_string(value, f"{field} must be a date-time string")
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AssertionError(f"{field} must be a valid date-time") from exc

    if parsed.tzinfo is None:
        raise AssertionError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def require_datetime_not_after(
    earlier_value: object,
    later_value: object,
    earlier_field: str,
    later_field: str,
) -> None:
    earlier = parse_datetime(earlier_value, earlier_field)
    later = parse_datetime(later_value, later_field)
    require(earlier <= later, f"{earlier_field} must not be after {later_field}")


def relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def path_from_env(root: Path, env_name: str, default: Path) -> Path:
    raw_path = os.environ.get(env_name)
    if not raw_path:
        return default

    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return root / path


def scalar(connection: Any, query: str, parameters: tuple[object, ...]) -> object:
    row = connection.execute(query, parameters).fetchone()
    require(row is not None, f"query returned no rows: {query}")
    return row[0]


def sha256_digest(path: Path) -> str:
    if path.is_dir():
        return _sha256_tree_digest(path)
    if not path.is_file():
        raise AssertionError(f"digest path must point to a file or directory: {path}")
    return _sha256_file_digest(path)


def _sha256_file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _sha256_tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    digest.update(b"oep-tree-sha256-v1\0")
    for file_path in _iter_tree_digest_files(root):
        relative = file_path.relative_to(root).as_posix()
        digest.update(b"path\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0content\0")
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _iter_tree_digest_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if any(part in TREE_DIGEST_EXCLUDED_DIRS for part in file_path.relative_to(root).parts[:-1]):
            continue
        if file_path.name in TREE_DIGEST_EXCLUDED_NAMES or file_path.name.endswith(TREE_DIGEST_EXCLUDED_SUFFIXES):
            continue
        files.append(file_path)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def unresolved_layer_bindings(manifest: JsonObject) -> list[str]:
    layer_bindings = require_json_object(manifest.get("layer_bindings"), "layer_bindings must be an object")
    unresolved = []
    for layer, raw_binding in layer_bindings.items():
        binding = require_json_object(raw_binding, f"{layer} binding must be an object")
        if binding.get("binding_status") != "resolved":
            unresolved.append(str(layer))
    return sorted(unresolved)


def require_resolved_layer_bindings(manifest: JsonObject, context: str) -> None:
    unresolved = unresolved_layer_bindings(manifest)
    require(not unresolved, f"{context} requires resolved release layer bindings: {', '.join(unresolved)}")


def validate_json_schema(schema: JsonObject, instance: JsonObject, *, instance_path: Path) -> None:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise AssertionError(f"invalid JSON Schema for {instance_path}: {exc.message}") from exc

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=_validation_error_key)
    if errors:
        raise AssertionError(
            f"{instance_path} failed JSON Schema validation: {_format_validation_error(errors[0])}"
        )


def _validation_error_key(error: ValidationError) -> tuple[str, str]:
    return (".".join(str(part) for part in error.absolute_path), error.message)


def _format_validation_error(error: ValidationError) -> str:
    path = ".".join(str(part) for part in error.absolute_path)
    location = path if path else "<root>"
    return f"{location}: {error.message}"


__all__ = [
    "JsonObject",
    "TREE_DIGEST_EXCLUDED_DIRS",
    "TREE_DIGEST_EXCLUDED_NAMES",
    "TREE_DIGEST_EXCLUDED_SUFFIXES",
    "load_json_object",
    "parse_datetime",
    "path_from_env",
    "relative_path",
    "require",
    "require_datetime_not_after",
    "require_json_list",
    "require_json_object",
    "require_string",
    "scalar",
    "sha256_digest",
    "require_resolved_layer_bindings",
    "unresolved_layer_bindings",
    "validate_json_schema",
]
