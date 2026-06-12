"""Shared helpers for local verification scripts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
from collections.abc import Iterable
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from jsonschema.exceptions import SchemaError, ValidationError
except ModuleNotFoundError as exc:  # pragma: no cover - exercised only in unprepared envs
    raise RuntimeError(
        "jsonschema is required for verification; install project dependencies in a virtualenv "
        "with `python -m pip install -e .`"
    ) from exc


JsonObject = dict[str, Any]
OEP_OPA_BIN_PATH_ENV = "OEP_OPA_BIN_PATH"
OPA_PATH_ENV = "OPA_PATH"
_EXECUTABLE_ENV_OVERRIDES = {"opa": (OEP_OPA_BIN_PATH_ENV, OPA_PATH_ENV)}
_SCHEMA_VALIDATOR_CACHE_MAX_ENTRIES = 64
OPA_SUPPORTED_MAJOR_VERSION = 1
OPA_VERSION_RE = re.compile(r"^Version:\s*(\d+)\.(\d+)(?:\.(\d+))?(?:[-+][^\s]+)?", re.MULTILINE)
JSON_SCHEMA_VALIDATION_ERROR_LIMIT = 5
JSON_SCHEMA_REQUIRED_FORMATS = ("date-time",)
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
    ".db-shm",
    ".db-wal",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite-shm",
    ".sqlite-wal",
    ".sqlite3",
    ".sqlite3-shm",
    ".sqlite3-wal",
)
TREE_DIGEST_EXECUTABLE_SUFFIXES = frozenset({".py", ".sh"})
TREE_DIGEST_EXECUTABLE_MODE = 0o755
TREE_DIGEST_REGULAR_MODE = 0o644


def load_json_object(path: Path) -> JsonObject:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def load_json_object_or_exit(path: Path) -> JsonObject:
    """Load a JSON object for CLI scripts, exiting cleanly on a non-object payload."""
    try:
        return load_json_object(path)
    except TypeError as exc:
        raise SystemExit(f"expected JSON object at {path}") from exc


def stable_json(data: JsonObject) -> str:
    """Serialize *data* as deterministic pretty JSON with a trailing newline."""
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def required_field(value: Any, field: str, context: str) -> Any:
    """Return *value*, exiting cleanly when a required projection field is absent."""
    if value is None:
        raise SystemExit(f"{context} missing required field: {field}")
    return value


def read_only_sqlite_connection(db_path: Path) -> sqlite3.Connection:
    """Open *db_path* as a read-only SQLite connection via a file URI."""
    state_uri = f"{db_path.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(state_uri, uri=True)


def eval_opa_decision(policy_path: Path, input_path: Path, purpose: str) -> JsonObject:
    """Evaluate ``data.oep.permissions.decision`` for *input_path* against *policy_path*."""
    opa = require_executable("opa", purpose)
    result = subprocess.run(
        [
            opa,
            "eval",
            "--format",
            "json",
            "--data",
            str(policy_path),
            "--input",
            str(input_path),
            "data.oep.permissions.decision",
        ],
        check=True,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )
    payload = json.loads(result.stdout)
    value = payload["result"][0]["expressions"][0]["value"]
    return require_json_object(value, "OPA decision must be an object")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def require_json_object(value: object, message: str) -> JsonObject:
    if not isinstance(value, dict):
        raise TypeError(message)
    return cast(JsonObject, value)


def require_json_list(value: object, message: str) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(message)
    return value


def require_string(value: object, message: str) -> str:
    if not isinstance(value, str):
        raise TypeError(message)
    return value


def require_executable(name: str, purpose: str) -> str:
    env_executable = _executable_from_env(name, purpose)
    if env_executable is not None:
        _validate_executable_version(name, env_executable, purpose)
        return env_executable

    executable = shutil.which(name)
    if executable is None:
        raise FileNotFoundError(f"{name} executable is required for {purpose}")
    _validate_executable_version(name, executable, purpose)
    return executable


def _validate_executable_version(name: str, executable: str, purpose: str) -> None:
    if name == "opa":
        _opa_version(executable, purpose)


@lru_cache(maxsize=16)
def _opa_version(executable: str, purpose: str) -> tuple[int, int, int]:
    try:
        completed = subprocess.run(
            [executable, "version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"opa version check failed for {purpose}: {exc}") from exc

    if completed.returncode != 0:
        output = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
        raise ValueError(f"opa version check failed for {purpose}: {output}")

    match = OPA_VERSION_RE.search(completed.stdout)
    if match is None:
        raise ValueError(f"opa version output could not be parsed for {purpose}: {completed.stdout.strip()}")

    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3) or 0)
    version = (major, minor, patch)
    if major != OPA_SUPPORTED_MAJOR_VERSION:
        found_version = match.group(0).split(":", 1)[1].strip()
        raise ValueError(f"opa {OPA_SUPPORTED_MAJOR_VERSION}.x is required for {purpose}; found {found_version}")
    return version


def _executable_from_env(name: str, purpose: str) -> str | None:
    for env_name in _EXECUTABLE_ENV_OVERRIDES.get(name, ()):
        raw_path = os.environ.get(env_name)
        if not raw_path:
            continue

        path = Path(raw_path).expanduser()
        if path.parent == Path("."):
            executable = shutil.which(raw_path)
            if executable is not None:
                return executable
        elif path.is_file() and os.access(path, os.X_OK):
            return str(path)

        raise ValueError(f"{env_name} must point to an executable file for {purpose}: {raw_path}")
    return None


def parse_datetime(value: object, field: str) -> datetime:
    text = require_string(value, f"{field} must be a date-time string")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid date-time") from exc

    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
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


def scalar(connection: sqlite3.Connection, query: str, parameters: tuple[object, ...]) -> object:
    row = connection.execute(query, parameters).fetchone()
    require(row is not None, f"query returned no rows: {query}")
    return row[0]


def sha256_digest(path: Path) -> str:
    if path.is_dir():
        return _sha256_tree_digest(path)
    if not path.is_file():
        raise ValueError(f"digest path must point to a file or directory: {path}")
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
        mode = _normalized_tree_digest_mode(file_path)
        digest.update(b"path\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0mode\0")
        digest.update(f"{mode:o}".encode("ascii"))
        digest.update(b"\0content\0")
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _normalized_tree_digest_mode(file_path: Path) -> int:
    raw_mode = file_path.stat().st_mode
    executable = (raw_mode & 0o111) != 0 or file_path.suffix in TREE_DIGEST_EXECUTABLE_SUFFIXES
    return TREE_DIGEST_EXECUTABLE_MODE if executable else TREE_DIGEST_REGULAR_MODE


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


def validate_json_schema(schema: JsonObject, instance: Any, *, instance_path: Path) -> None:
    schema_key = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    validator = _json_schema_validator_from_content(schema_key)
    _validate_with_compiled_schema(validator, instance, instance_path)


def validate_json_schema_from_path(schema_path: Path, instance: Any, *, instance_path: Path) -> None:
    validator = json_schema_validator(schema_path)
    _validate_with_compiled_schema(validator, instance, instance_path)


def json_schema_validator(schema_path: Path) -> Draft202012Validator:
    resolved_path = schema_path.resolve()
    stat = resolved_path.stat()
    return _json_schema_validator_from_path(resolved_path, stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=_SCHEMA_VALIDATOR_CACHE_MAX_ENTRIES)
def _json_schema_validator_from_path(
    resolved_path: Path,
    mtime_ns: int,
    size: int,
) -> Draft202012Validator:
    del mtime_ns, size
    return _compile_json_schema_validator(load_json_object(resolved_path), resolved_path)


@lru_cache(maxsize=_SCHEMA_VALIDATOR_CACHE_MAX_ENTRIES)
def _json_schema_validator_from_content(schema_key: str) -> Draft202012Validator:
    schema = json.loads(schema_key)
    return _compile_json_schema_validator(cast(JsonObject, schema), Path("<schema>"))


def _compile_json_schema_validator(schema: JsonObject, schema_path: Path) -> Draft202012Validator:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(f"invalid JSON Schema for {schema_path}: {exc.message}") from exc
    return Draft202012Validator(schema, format_checker=_json_schema_format_checker())


def _json_schema_format_checker() -> FormatChecker:
    checker = FormatChecker()
    missing_formats = sorted(
        format_name for format_name in JSON_SCHEMA_REQUIRED_FORMATS if format_name not in checker.checkers
    )
    if missing_formats:
        formatted = ", ".join(missing_formats)
        raise RuntimeError(f"jsonschema format dependencies are missing or inactive: {formatted}")
    if checker.conforms("not-a-date-time", "date-time"):
        raise RuntimeError("jsonschema date-time format validation is inactive; install jsonschema[format]")
    return checker


def _validate_with_compiled_schema(
    validator: Draft202012Validator,
    instance: Any,
    instance_path: Path,
) -> None:
    errors = sorted(validator.iter_errors(instance), key=_validation_error_key)
    if errors:
        formatted_errors = [
            _format_validation_error(error)
            for error in errors[:JSON_SCHEMA_VALIDATION_ERROR_LIMIT]
        ]
        if len(errors) > JSON_SCHEMA_VALIDATION_ERROR_LIMIT:
            formatted_errors.append(
                f"... {len(errors) - JSON_SCHEMA_VALIDATION_ERROR_LIMIT} more validation error(s)"
            )
        raise ValueError(
            f"{instance_path} failed JSON Schema validation: {'; '.join(formatted_errors)}"
        )


def _validation_error_key(error: ValidationError) -> tuple[str, str]:
    return (_json_pointer_path(error.absolute_path), error.message)


def _format_validation_error(error: ValidationError) -> str:
    path = _json_pointer_path(error.absolute_path)
    location = path if path else "<root>"
    return f"{location}: {error.message}"


def _json_pointer_path(parts: Iterable[object]) -> str:
    tokens = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return f"/{'/'.join(tokens)}" if tokens else ""


__all__ = [
    "JsonObject",
    "JSON_SCHEMA_VALIDATION_ERROR_LIMIT",
    "OEP_OPA_BIN_PATH_ENV",
    "OPA_PATH_ENV",
    "TREE_DIGEST_EXCLUDED_DIRS",
    "TREE_DIGEST_EXCLUDED_NAMES",
    "TREE_DIGEST_EXCLUDED_SUFFIXES",
    "eval_opa_decision",
    "json_schema_validator",
    "load_json_object",
    "load_json_object_or_exit",
    "parse_datetime",
    "path_from_env",
    "read_only_sqlite_connection",
    "relative_path",
    "require",
    "require_datetime_not_after",
    "require_executable",
    "require_json_list",
    "require_json_object",
    "require_string",
    "required_field",
    "scalar",
    "sha256_digest",
    "stable_json",
    "require_resolved_layer_bindings",
    "unresolved_layer_bindings",
    "validate_json_schema",
    "validate_json_schema_from_path",
]
