"""Replay reader over local SQLite replay state.

The v0.2 `oep replay <decision_id>` subcommand is a thin reader over the
existing demo SQLite replay store. It does not introduce new persistence,
live model calls, or service dependencies; it reconstructs the recorded
permission trace by joining rows already written by the deterministic
demo runner.
"""

from __future__ import annotations

import json
import math
import ntpath
import os
import re
import shlex
import shutil
import signal
import sqlite3
import subprocess
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Never

from oep_permissions.paths import COUNTERFACTUAL_REPLAY_SCHEMA_PATH, SCHEMA_PATH

COUNTERFACTUAL_CLAIM_BOUNDARY = (
    "This record is an inspectable counterfactual policy replay output for the reference implementation. "
    "It is not a production-grade replay engine, compliance certification, or legal/regulatory adequacy claim."
)
OPA_EVAL_TIMEOUT_SECONDS = 30
MIN_OPA_EVAL_TIMEOUT_SECONDS = 0.001
OPA_STDIN_INPUT_LIMIT_BYTES = 8 * 1024 * 1024
OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV = "OEP_OPA_EVAL_TIMEOUT_SECONDS"
OEP_OPA_COMMAND_WRAPPER_ENV = "OEP_OPA_COMMAND_WRAPPER"
SQLITE_REPLAY_BUSY_TIMEOUT_SECONDS = 10.0
OPA_DECISION_QUERY_PATH = "data.oep.permissions.decision"
OPA_BATCH_DECISION_QUERY = (
    '{sprintf("%08d", [i]): decision | '
    "some i; "
    "policy_input := input[i]; "
    "decision := data.oep.permissions.decision with input as policy_input"
    "}"
)
SQLITE_BATCH_VARIABLE_LIMIT = 900
SQLITE_BATCH_PLACEHOLDER_BUCKETS = (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, SQLITE_BATCH_VARIABLE_LIMIT)
SQLITE_BATCH_PLACEHOLDERS = {
    bucket_size: ",".join("?" for _ in range(bucket_size))
    for bucket_size in SQLITE_BATCH_PLACEHOLDER_BUCKETS
}
OPA_ERROR_OUTPUT_LIMIT = 1000
OPA_WRAPPER_NUMERIC_VALUE_RE = re.compile(r"^(?:[+-]?\d+(?:\.\d+)?|\d+:\d+|unlimited)$")
OPA_WRAPPER_USER_VALUE_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
OPA_DOCKER_IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*(?::[A-Za-z0-9._-]+)?$")
OPA_DOCKER_MEMORY_VALUE_RE = re.compile(r"^\d+[kKmMgG]?$")
TRUSTED_OPA_WRAPPER_DIRS = tuple(
    Path(path)
    for path in (
        "/bin",
        "/sbin",
        "/usr/bin",
        "/usr/sbin",
        "/usr/local/bin",
        "/opt/homebrew/bin",
    )
)
WINDOWS_SYSTEM_ROOT_ENV_NAMES = ("SystemRoot", "WINDIR")
WINDOWS_TRUSTED_OPA_WRAPPER_ROOT_ENV_NAMES = ("ProgramFiles", "ProgramFiles(x86)")
WINDOWS_SYSTEM_ROOT_FALLBACK = r"C:\Windows"
ALLOWED_OPA_COMMAND_WRAPPER_OPTIONS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "docker": frozenset(
            {
                "--cpus",
                "--init",
                "--memory",
                "--network",
                "--pids-limit",
                "--read-only",
                "--rm",
                "--user",
                "--volume",
                "-v",
                "run",
            }
        ),
        "nice": frozenset({"--adjustment", "-n"}),
        "prlimit": frozenset(
            {
                "--adjustment",
                "--as",
                "--cpu",
                "--data",
                "--fsize",
                "--memlock",
                "--nice",
                "--nofile",
                "--nproc",
                "--pid",
                "--priority",
                "--rss",
                "--stack",
                "-n",
            }
        ),
        "sudo": frozenset({"--user", "-n", "-u"}),
    }
)
ALLOWED_OPA_COMMAND_WRAPPERS = frozenset(ALLOWED_OPA_COMMAND_WRAPPER_OPTIONS)
OPA_WRAPPER_OPTIONS_WITH_VALUES: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "docker": frozenset({"--cpus", "--memory", "--network", "--pids-limit", "--user", "--volume", "-v"}),
        "nice": frozenset({"--adjustment", "-n"}),
        "prlimit": frozenset(
            {
                "--adjustment",
                "--as",
                "--cpu",
                "--data",
                "--fsize",
                "--memlock",
                "--nice",
                "--nofile",
                "--nproc",
                "--pid",
                "--priority",
                "--rss",
                "--stack",
                "-n",
            }
        ),
        "sudo": frozenset({"--user", "-u"}),
    }
)


@dataclass
class _ReplayPayloadCache:
    traces: dict[str, dict[str, Any]]
    manifest_summaries: dict[str, dict[str, Any] | None]


@dataclass(frozen=True)
class ReplayRecord:
    """Reconstructed view of a recorded permission decision and its joins."""

    decision_id: str
    tool_call_id: str
    release_manifest_id: str
    trace_id: str
    span_id: str
    permission_packet: dict[str, Any]
    agent_step_event: dict[str, Any]
    trace_bundle: dict[str, Any] | None
    release_manifest_summary: dict[str, Any] | None
    replay_handle: dict[str, Any] | None
    scoped_credential_lifetime: str | None
    approval_capture: dict[str, Any] | None
    policy_bundle_version: str | None
    release_manifest_version: str | None
    model_alias: str | None
    resolved_model_version: str | None
    model_provider: str | None
    nd_builtin_cache: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "tool_call_id": self.tool_call_id,
            "release_manifest_id": self.release_manifest_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "permission_packet": self.permission_packet,
            "agent_step_event": self.agent_step_event,
            "trace_bundle": self.trace_bundle,
            "release_manifest_summary": self.release_manifest_summary,
            "replay_handle": self.replay_handle,
            "scoped_credential_lifetime": self.scoped_credential_lifetime,
            "approval_capture": self.approval_capture,
            "policy_bundle_version": self.policy_bundle_version,
            "release_manifest_version": self.release_manifest_version,
            "model_alias": self.model_alias,
            "resolved_model_version": self.resolved_model_version,
            "model_provider": self.model_provider,
            "nd_builtin_cache": self.nd_builtin_cache,
        }


@dataclass(frozen=True)
class CounterfactualReplayRecord:
    """Original-vs-counterfactual policy replay result for one recorded decision."""

    decision_id: str
    original: Mapping[str, Any]
    counterfactual: Mapping[str, Any]
    diff: Mapping[str, Any]
    replay_metadata: Mapping[str, Any]
    claim_boundary: str = COUNTERFACTUAL_CLAIM_BOUNDARY

    def __post_init__(self) -> None:
        object.__setattr__(self, "original", _freeze_json_object(self.original))
        object.__setattr__(self, "counterfactual", _freeze_json_object(self.counterfactual))
        object.__setattr__(self, "diff", _freeze_json_object(self.diff))
        object.__setattr__(self, "replay_metadata", _freeze_json_object(self.replay_metadata))

    def with_diff_updates(self, updates: Mapping[str, Any]) -> CounterfactualReplayRecord:
        diff = _thaw_json_object(self.diff)
        diff.update({key: _thaw_json_value(value) for key, value in updates.items()})
        return CounterfactualReplayRecord(
            decision_id=self.decision_id,
            original=self.original,
            counterfactual=self.counterfactual,
            diff=diff,
            replay_metadata=self.replay_metadata,
            claim_boundary=self.claim_boundary,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "oep.counterfactual_replay.v0",
            "decision_id": self.decision_id,
            "replay_mode": "counterfactual",
            "original": _thaw_json_object(self.original),
            "counterfactual": _thaw_json_object(self.counterfactual),
            "diff": _thaw_json_object(self.diff),
            "replay_metadata": _thaw_json_object(self.replay_metadata),
            "claim_boundary": self.claim_boundary,
        }


class ReplayError(RuntimeError):
    """Raised when a decision cannot be reconstructed from local replay state."""


class StateNotFoundError(ReplayError):
    """Raised when the local replay state database is missing."""


class OpaEvaluationError(ReplayError):
    """Raised when counterfactual OPA evaluation cannot complete."""


class SchemaValidationError(ReplayError):
    """Raised when stored replay data or replay output fails schema validation."""


class JoinInconsistencyError(ReplayError):
    """Raised when replay rows cannot be joined consistently."""


def reconstruct_decision(
    state_path: Path | sqlite3.Connection,
    decision_id: str,
    *,
    validate_schema: bool = True,
) -> ReplayRecord:
    """Reconstruct the recorded permission trace for a decision id.

    `decision_id` matches the permission packet identifier (the `pder_*`
    value stored as `permissions.packet_id`). The function reads only;
    it does not write to the SQLite store.
    """

    return reconstruct_decisions(state_path, [decision_id], validate_schema=validate_schema)[0]


def reconstruct_decisions(
    state_path: Path | sqlite3.Connection,
    decision_ids: Sequence[str],
    *,
    validate_schema: bool = True,
) -> list[ReplayRecord]:
    """Reconstruct multiple recorded decisions with one SQLite connection."""

    if not decision_ids:
        return []

    if isinstance(state_path, sqlite3.Connection):
        try:
            return _reconstruct_decisions_from_connection(
                state_path,
                Path("<sqlite-connection>"),
                decision_ids,
                validate_schema=validate_schema,
            )
        except sqlite3.Error as exc:
            raise ReplayError(f"database operational error during replay reconstruction: {exc}") from exc

    replay_state_path = Path(state_path)
    if not replay_state_path.is_file():
        raise StateNotFoundError(
            f"replay state not found at {replay_state_path}. "
            "Run `oep-run-demo` or `make verify` to regenerate it."
        )

    try:
        with closing(_connect_read_only_state(replay_state_path)) as connection:
            return _reconstruct_decisions_from_connection(
                connection,
                replay_state_path,
                decision_ids,
                validate_schema=validate_schema,
            )
    except sqlite3.Error as exc:
        raise ReplayError(f"database operational error during replay reconstruction: {exc}") from exc


def _reconstruct_decisions_from_connection(
    connection: sqlite3.Connection,
    state_path: Path,
    decision_ids: Sequence[str],
    *,
    validate_schema: bool,
) -> list[ReplayRecord]:
    with closing(connection.cursor()) as cursor:
        cursor.row_factory = sqlite3.Row
        rows_by_decision_id = _select_decision_rows(cursor, decision_ids)
        payload_cache = _ReplayPayloadCache(traces={}, manifest_summaries={})
        return [
            _reconstruct_decision_from_row(
                cursor,
                state_path,
                decision_id,
                rows_by_decision_id.get(decision_id),
                payload_cache,
                validate_schema=validate_schema,
            )
            for decision_id in decision_ids
        ]


def _connect_read_only_state(state_path: Path) -> sqlite3.Connection:
    state_uri = _sqlite_read_only_uri(state_path)
    return sqlite3.connect(state_uri, uri=True, timeout=SQLITE_REPLAY_BUSY_TIMEOUT_SECONDS)


def _sqlite_read_only_uri(state_path: Path) -> str:
    return f"{state_path.resolve().as_uri()}?mode=ro"


def _select_decision_rows(
    cursor: sqlite3.Cursor,
    decision_ids: Sequence[str],
) -> dict[str, sqlite3.Row]:
    rows_by_decision_id: dict[str, sqlite3.Row] = {}
    unique_decision_ids = tuple(dict.fromkeys(decision_ids))
    for start in range(0, len(unique_decision_ids), SQLITE_BATCH_VARIABLE_LIMIT):
        batch = unique_decision_ids[start : start + SQLITE_BATCH_VARIABLE_LIMIT]
        # Bucketed placeholders trade small NULL padding for SQLite statement
        # plan reuse across replay batches.
        placeholders = _decision_id_placeholders(len(batch))
        parameters = _padded_decision_id_parameters(batch)
        rows = cursor.execute(
            f"""
            SELECT
                p.packet_id AS packet_id,
                p.event_id AS permission_event_id,
                p.tool_call_id AS permission_tool_call_id,
                p.trace_id AS permission_trace_id,
                p.span_id AS permission_span_id,
                p.payload_json AS permission_payload,
                e.event_id AS event_id,
                e.release_manifest_id AS event_release_manifest_id,
                e.tool_call_id AS event_tool_call_id,
                e.trace_id AS event_trace_id,
                e.span_id AS event_span_id,
                e.payload_json AS event_payload,
                t.payload_json AS trace_payload,
                a.payload_json AS manifest_payload
            FROM permissions p
            JOIN events e
                ON p.event_id = e.event_id
            LEFT JOIN traces t
                ON e.trace_id = t.trace_id
                AND e.release_manifest_id = t.release_manifest_id
            LEFT JOIN artifacts a
                ON a.kind = 'release_manifest'
                AND e.release_manifest_id = a.artifact_id
            WHERE p.packet_id IN ({placeholders})
            """,
            parameters,
        ).fetchall()
        rows_by_decision_id.update({row["packet_id"]: row for row in rows})
    return rows_by_decision_id


def _decision_id_placeholders(batch_size: int) -> str:
    return SQLITE_BATCH_PLACEHOLDERS[_decision_id_placeholder_bucket(batch_size)]


def _padded_decision_id_parameters(batch: Sequence[str]) -> tuple[str | None, ...]:
    bucket_size = _decision_id_placeholder_bucket(len(batch))
    return tuple(batch) + ((None,) * (bucket_size - len(batch)))


def _decision_id_placeholder_bucket(batch_size: int) -> int:
    if not 1 <= batch_size <= SQLITE_BATCH_VARIABLE_LIMIT:
        raise ReplayError(f"decision batch size must be between 1 and {SQLITE_BATCH_VARIABLE_LIMIT}")
    for bucket_size in SQLITE_BATCH_PLACEHOLDER_BUCKETS:
        if batch_size <= bucket_size:
            return bucket_size
    raise ReplayError(f"decision batch size must be between 1 and {SQLITE_BATCH_VARIABLE_LIMIT}")


def _reconstruct_decision_from_row(
    cursor: sqlite3.Cursor,
    state_path: Path,
    decision_id: str,
    row: sqlite3.Row | None,
    payload_cache: _ReplayPayloadCache,
    *,
    validate_schema: bool,
) -> ReplayRecord:
    if row is None:
        _raise_missing_decision(cursor, decision_id)

    permission = _loads_object(row["permission_payload"], "permission payload")
    if validate_schema:
        _validate_permission_packet(permission, state_path)
    event = _loads_object(row["event_payload"], "event payload")
    _require_join_consistency(row, permission, event, decision_id)
    trace = _cached_trace_payload(row, payload_cache)
    trace_id = _require_string(permission.get("trace_id"), "trace_id")
    manifest_id = _require_string(event.get("release_manifest_id"), "release_manifest_id")
    manifest_summary = _cached_manifest_summary(row["manifest_payload"], manifest_id, payload_cache)

    replay_handle = event.get("replay_handle")
    if replay_handle is not None and not isinstance(replay_handle, dict):
        raise ReplayError("event.replay_handle must be an object or null in replay state")

    approval_capture = permission.get("approval_capture")
    if approval_capture is not None and not isinstance(approval_capture, dict):
        raise ReplayError("permission.approval_capture must be an object or null in replay state")

    nd_builtin_cache = permission.get("nd_builtin_cache")
    if nd_builtin_cache is not None and not isinstance(nd_builtin_cache, dict):
        raise ReplayError("permission.nd_builtin_cache must be an object or null in replay state")

    return ReplayRecord(
        decision_id=decision_id,
        tool_call_id=_require_string(permission.get("tool_call_id"), "tool_call_id"),
        release_manifest_id=manifest_id,
        trace_id=trace_id,
        span_id=_require_string(permission.get("span_id"), "span_id"),
        permission_packet=permission,
        agent_step_event=event,
        trace_bundle=trace,
        release_manifest_summary=manifest_summary,
        replay_handle=replay_handle if isinstance(replay_handle, dict) else None,
        scoped_credential_lifetime=_optional_string(permission.get("scoped_credential_lifetime")),
        approval_capture=approval_capture if isinstance(approval_capture, dict) else None,
        policy_bundle_version=_optional_string(permission.get("policy_bundle_version")),
        release_manifest_version=_optional_string(permission.get("release_manifest_version")),
        model_alias=_optional_string(permission.get("model_alias")),
        resolved_model_version=_optional_string(permission.get("resolved_model_version")),
        model_provider=_optional_string(permission.get("model_provider")),
        nd_builtin_cache=nd_builtin_cache if isinstance(nd_builtin_cache, dict) else None,
    )


def _cached_trace_payload(
    row: sqlite3.Row,
    payload_cache: _ReplayPayloadCache,
) -> dict[str, Any] | None:
    payload = row["trace_payload"]
    if payload is None:
        return None
    trace_id = _require_string(row["event_trace_id"], "event.trace_id")
    trace = payload_cache.traces.get(trace_id)
    if trace is None:
        trace = _loads_object(payload, "trace payload")
        payload_cache.traces[trace_id] = trace
    return trace


def _cached_manifest_summary(
    manifest_payload: object,
    manifest_id: str,
    payload_cache: _ReplayPayloadCache,
) -> dict[str, Any] | None:
    if manifest_id not in payload_cache.manifest_summaries:
        payload_cache.manifest_summaries[manifest_id] = _manifest_summary(manifest_payload)
    return payload_cache.manifest_summaries[manifest_id]


def _raise_missing_decision(cursor: sqlite3.Cursor, decision_id: str) -> Never:
    event_row = cursor.execute(
        """
        SELECT payload_json FROM events
        WHERE permission_packet_ref = ?
        """,
        (decision_id,),
    ).fetchone()
    denied_hint = ""
    if event_row is not None:
        event = _loads_object(event_row["payload_json"], "event payload")
        outcome = event.get("outcome")
        if isinstance(outcome, dict) and outcome.get("status") == "denied":
            denied_hint = (
                " A matching agent-step event recorded outcome 'denied'; "
                "denied decisions do not generate SQLite replay state by "
                "design (see the v0.1 evidence chain). Inspect the "
                "denied permission packet artifact directly instead."
            )
    raise JoinInconsistencyError(f"no recorded decision found for decision_id={decision_id!r}.{denied_hint}")


def _require_join_consistency(
    row: sqlite3.Row,
    permission: dict[str, Any],
    event: dict[str, Any],
    decision_id: str,
) -> None:
    expected = {
        "packet_id": (row["packet_id"], decision_id),
        "permission.event_id": (permission.get("event_id"), row["permission_event_id"]),
        "permission.tool_call_id": (permission.get("tool_call_id"), row["permission_tool_call_id"]),
        "permission.trace_id": (permission.get("trace_id"), row["permission_trace_id"]),
        "permission.span_id": (permission.get("span_id"), row["permission_span_id"]),
        "event.event_id": (event.get("event_id"), row["event_id"]),
        "event.tool_call_id": (event.get("tool_call_id"), row["event_tool_call_id"]),
        "event.trace_id": (event.get("trace_id"), row["event_trace_id"]),
        "event.span_id": (event.get("span_id"), row["event_span_id"]),
        "event.release_manifest_id": (event.get("release_manifest_id"), row["event_release_manifest_id"]),
        "permission/event.tool_call_id": (row["permission_tool_call_id"], row["event_tool_call_id"]),
        "permission/event.trace_id": (row["permission_trace_id"], row["event_trace_id"]),
        "permission/event.span_id": (row["permission_span_id"], row["event_span_id"]),
    }
    for field, (actual, expected_value) in expected.items():
        if actual != expected_value:
            raise JoinInconsistencyError(f"recorded decision {decision_id!r} has inconsistent joined field {field!r}")


def _manifest_summary(manifest_payload: object) -> dict[str, Any] | None:
    if manifest_payload is None:
        return None
    manifest = _loads_object(manifest_payload, "manifest payload")
    release = manifest.get("release") if isinstance(manifest.get("release"), dict) else {}
    return {
        "manifest_id": manifest.get("manifest_id"),
        "scenario": release.get("scenario") if isinstance(release, dict) else None,
        "release_name": release.get("name") if isinstance(release, dict) else None,
        "release_version": release.get("version") if isinstance(release, dict) else None,
    }


def counterfactual_replay_decision(
    state_path: Path | sqlite3.Connection,
    decision_id: str,
    policy_bundle_path: Path,
    *,
    policy_bundle_version: str | None = None,
    replay_timestamp_utc: str | None = None,
    query: str = "data.oep.permissions.decision",
    timeout_seconds: float | None = None,
    validate_schema: bool = True,
) -> CounterfactualReplayRecord:
    """Re-derive a recorded decision under a substituted OPA policy bundle.

    The operation reads the existing v0.2 SQLite replay state, reconstructs
    the OPA input context from the stored permission packet, evaluates the
    supplied policy bundle with `opa eval`, and returns a schema-validated
    original-vs-counterfactual diff. It does not mutate the SQLite store.
    """

    return counterfactual_replay_decisions(
        state_path,
        [decision_id],
        policy_bundle_path,
        policy_bundle_version=policy_bundle_version,
        replay_timestamp_utc=replay_timestamp_utc,
        query=query,
        timeout_seconds=timeout_seconds,
        validate_schema=validate_schema,
    )[0]


def counterfactual_replay_decisions(
    state_path: Path | sqlite3.Connection,
    decision_ids: Sequence[str],
    policy_bundle_path: Path,
    *,
    policy_bundle_version: str | None = None,
    replay_timestamp_utc: str | None = None,
    query: str = "data.oep.permissions.decision",
    timeout_seconds: float | None = None,
    validate_schema: bool = True,
) -> list[CounterfactualReplayRecord]:
    """Batch re-derive recorded decisions under one substituted OPA policy bundle."""

    policy_path = Path(policy_bundle_path)
    if not policy_path.exists():
        raise OpaEvaluationError(f"counterfactual policy bundle not found: {policy_path}")
    if not decision_ids:
        return []
    replay_timestamp_utc = _validate_replay_timestamp_utc(replay_timestamp_utc)

    records = reconstruct_decisions(state_path, decision_ids, validate_schema=validate_schema)
    policy_inputs = [_policy_input_from_record(record) for record in records]
    counterfactual_decisions = _evaluate_opa_decisions(policy_path, policy_inputs, query, timeout_seconds)
    resolved_policy_version = policy_bundle_version or _counterfactual_policy_version(policy_path)
    return [
        _counterfactual_record_from_parts(
            record,
            counterfactual_decision,
            resolved_policy_version,
            replay_timestamp_utc,
        )
        for record, counterfactual_decision in zip(records, counterfactual_decisions, strict=True)
    ]


def _validate_replay_timestamp_utc(replay_timestamp_utc: str | None) -> str | None:
    if replay_timestamp_utc is None:
        return None
    from oep_verify.verify_support import parse_datetime

    try:
        parse_datetime(replay_timestamp_utc, "replay_timestamp_utc")
    except (TypeError, ValueError) as exc:
        raise ReplayError(str(exc)) from exc
    return replay_timestamp_utc


def _counterfactual_record_from_parts(
    record: ReplayRecord,
    counterfactual_decision: dict[str, Any],
    counterfactual_policy_version: str,
    replay_timestamp_utc: str | None,
) -> CounterfactualReplayRecord:
    original_snapshot = _snapshot_from_record(record)
    counterfactual_snapshot = _snapshot_from_opa_decision(
        counterfactual_decision,
        counterfactual_policy_version,
    )
    result = CounterfactualReplayRecord(
        decision_id=record.decision_id,
        original=original_snapshot,
        counterfactual=counterfactual_snapshot,
        diff=_decision_diff(original_snapshot, counterfactual_snapshot),
        replay_metadata={
            "oep_replay_mode": "counterfactual",
            "nd_builtin_cache_entries_used": _nd_builtin_cache_entry_count(record.nd_builtin_cache),
            "replay_timestamp_utc": replay_timestamp_utc or _utc_now(),
            "determinism_exclusions": ["replay_metadata.replay_timestamp_utc"],
        },
    )
    _validate_counterfactual_replay(result.to_dict())
    return result


def _loads_object(text: object, field: str) -> dict[str, Any]:
    if not isinstance(text, str):
        raise SchemaValidationError(f"{field} must be a JSON string in replay state")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(f"{field} is not valid JSON in replay state: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise SchemaValidationError(f"{field} must decode to a JSON object")
    return data


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReplayError(f"replay state row is missing required field {field!r}")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ReplayError("permission v0.2 fields must be strings or null in replay state")
    return value


def _validate_permission_packet(packet: dict[str, Any], state_path: Path) -> None:
    """Defense-in-depth schema check on permission packets read from SQLite."""

    from oep_verify.verify_support import validate_json_schema_from_path

    try:
        validate_json_schema_from_path(SCHEMA_PATH, packet, instance_path=state_path)
    except ValueError as exc:
        raise SchemaValidationError(
            f"permission packet stored in {state_path} failed schema validation: {exc}"
        ) from exc


def _policy_input_from_record(record: ReplayRecord) -> dict[str, Any]:
    permission = record.permission_packet
    event = record.agent_step_event
    requested_action = _require_object(permission.get("requested_action"), "requested_action")
    input_context = {
        "release_manifest_id": record.release_manifest_id,
        "event_id": _require_string(permission.get("event_id"), "event_id"),
        "tool_call_id": record.tool_call_id,
        "trace_id": record.trace_id,
        "span_id": record.span_id,
        "actor": _require_object(permission.get("actor"), "actor"),
        "action": requested_action,
        "tool": _require_object(permission.get("tool"), "tool"),
        "resource": _require_object(permission.get("resource"), "resource"),
        "scoped_credential_lifetime": record.scoped_credential_lifetime,
        "approval_capture": record.approval_capture,
        "policy_bundle_version": record.policy_bundle_version,
        "release_manifest_version": record.release_manifest_version,
        "model_alias": record.model_alias,
        "resolved_model_version": record.resolved_model_version,
        "model_provider": record.model_provider,
        "replay_handle": record.replay_handle,
        "nd_builtin_cache": record.nd_builtin_cache or {},
    }
    checkpoint = event.get("checkpoint")
    if isinstance(checkpoint, dict):
        input_context["checkpoint"] = checkpoint
    budget = event.get("budget")
    if isinstance(budget, dict):
        input_context["budget"] = budget
    return input_context


def _evaluate_opa_decisions(
    policy_bundle_path: Path,
    policy_inputs: Sequence[dict[str, Any]],
    query: str,
    timeout_seconds: float | None,
) -> list[dict[str, Any]]:
    from oep_verify.verify_support import require_executable

    try:
        opa = require_executable("opa", "counterfactual policy replay")
    except (FileNotFoundError, ValueError) as exc:
        raise OpaEvaluationError(str(exc)) from exc

    if query != OPA_DECISION_QUERY_PATH:
        raise OpaEvaluationError(
            f"unsupported OPA query path: {query!r}. "
            f"Counterfactual policy bundles must expose {OPA_DECISION_QUERY_PATH!r}."
        )

    result = _run_opa_eval(
        [
            opa,
            "eval",
            "--format",
            "json",
            "--data",
            _opa_policy_bundle_data_path(policy_bundle_path),
            "--stdin-input",
            OPA_BATCH_DECISION_QUERY,
        ],
        json.dumps(policy_inputs, sort_keys=True, separators=(",", ":")),
        timeout_seconds,
    )
    if result.returncode != 0:
        error_output = _bounded_opa_error_output(result)
        raise OpaEvaluationError(f"counterfactual OPA evaluation failed: {error_output}")

    try:
        payload = json.loads(result.stdout)
        batch_value = payload["result"][0]["expressions"][0]["value"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise OpaEvaluationError("counterfactual OPA evaluation did not return a decision object") from exc

    if not isinstance(batch_value, dict):
        raise OpaEvaluationError("counterfactual OPA evaluation must return an indexed decision object")
    decisions: list[dict[str, Any]] = []
    for index in range(len(policy_inputs)):
        value = batch_value.get(f"{index:08d}")
        if value is None:
            raise OpaEvaluationError(
                f"counterfactual OPA evaluation did not return a decision object for input {index + 1}. "
                f"The query rule {OPA_DECISION_QUERY_PATH!r} may be undefined or evaluated to empty under "
                "the substituted policy bundle."
            )
        if not isinstance(value, dict):
            raise OpaEvaluationError(
                f"counterfactual OPA evaluation returned invalid decision type for input {index + 1}: "
                "expected object"
            )
        decisions.append(value)
    return decisions


def _run_opa_eval(
    args: Sequence[str],
    stdin: str,
    timeout_seconds: float | None,
) -> subprocess.CompletedProcess[str]:
    timeout = _opa_eval_timeout_seconds(timeout_seconds)
    _require_opa_stdin_within_limit(stdin)
    command = _opa_command(args)
    popen_kwargs: dict[str, Any] = {}
    if os.name == "posix":
        # Wrappers must keep OPA in this process group or forward termination
        # signals; containerized adaptations should use an init/signal-forwarder.
        popen_kwargs["start_new_session"] = True
    elif os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if creation_flags:
            popen_kwargs["creationflags"] = creation_flags
    try:
        process: subprocess.Popen[str] = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            text=True,
            **popen_kwargs,
        )
        try:
            stdout, stderr = process.communicate(stdin, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _terminate_opa_process(process)
            _reap_opa_process(process)
            raise OpaEvaluationError(
                f"counterfactual OPA evaluation timed out after {_format_timeout_seconds(timeout)} seconds"
            ) from exc
        except BaseException:
            _terminate_opa_process(process)
            _reap_opa_process(process)
            raise
        return subprocess.CompletedProcess(
            command,
            process.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    except OSError as exc:
        raise OpaEvaluationError(f"counterfactual OPA evaluation failed to start: {exc}") from exc


def _require_opa_stdin_within_limit(stdin: str) -> None:
    payload_size = len(stdin.encode("utf-8"))
    if payload_size > OPA_STDIN_INPUT_LIMIT_BYTES:
        raise OpaEvaluationError(
            "counterfactual OPA evaluation input exceeds "
            f"{OPA_STDIN_INPUT_LIMIT_BYTES} bytes; split the replay into smaller batches"
        )


def _terminate_opa_process(process: subprocess.Popen[str]) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except ProcessLookupError:
            pass
        except OSError:
            pass
    if os.name == "nt":
        ctrl_break_event = getattr(signal, "CTRL_BREAK_EVENT", None)
        if ctrl_break_event is not None:
            try:
                os.kill(process.pid, ctrl_break_event)
                return
            except ProcessLookupError:
                pass
            except OSError:
                pass
    _kill_opa_process(process)


def _kill_opa_process(process: subprocess.Popen[str]) -> None:
    try:
        process.kill()
    except OSError:
        return


def _reap_opa_process(process: subprocess.Popen[str]) -> None:
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        _kill_opa_process(process)
        process.wait()
    except OSError:
        return


def _bounded_opa_error_output(result: subprocess.CompletedProcess[str]) -> str:
    error_output = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
    if len(error_output) <= OPA_ERROR_OUTPUT_LIMIT:
        return error_output
    return f"{error_output[:OPA_ERROR_OUTPUT_LIMIT]} ... [output truncated]"


def _opa_command(args: Sequence[str]) -> list[str]:
    wrapper = os.environ.get(OEP_OPA_COMMAND_WRAPPER_ENV)
    if wrapper is None or wrapper.strip() == "":
        return list(args)
    try:
        wrapper_args = shlex.split(wrapper)
    except ValueError as exc:
        raise OpaEvaluationError(f"{OEP_OPA_COMMAND_WRAPPER_ENV} could not be parsed: {exc}") from exc
    if not wrapper_args:
        return list(args)
    _validate_opa_command_wrapper(wrapper_args)
    wrapper_args[0] = _resolve_opa_command_wrapper_executable(wrapper_args[0])
    return wrapper_args + list(args)


def _resolve_opa_command_wrapper_executable(executable: str) -> str:
    resolved = shutil.which(executable, path=_opa_command_wrapper_search_path())
    if resolved is None:
        raise OpaEvaluationError(
            f"authorized {OEP_OPA_COMMAND_WRAPPER_ENV} executable not found on PATH: {executable!r}"
        )
    if os.name == "nt":
        return _resolve_windows_opa_command_wrapper_path(resolved)
    resolved_path = Path(resolved).resolve()
    trusted_dirs = {path.resolve() for path in TRUSTED_OPA_WRAPPER_DIRS if path.exists()}
    if resolved_path.parent not in trusted_dirs:
        allowed = ", ".join(str(path) for path in TRUSTED_OPA_WRAPPER_DIRS)
        raise OpaEvaluationError(
            f"authorized {OEP_OPA_COMMAND_WRAPPER_ENV} executable resolved to untrusted path: {resolved_path}. "
            f"Expected one of: {allowed}"
        )
    return str(resolved_path)


def _opa_command_wrapper_search_path() -> str:
    path = os.environ.get("PATH", os.defpath)
    entries = [
        entry
        for entry in path.split(os.pathsep)
        if _is_absolute_opa_wrapper_search_path_entry(entry)
    ]
    return os.pathsep.join(entries)


def _is_absolute_opa_wrapper_search_path_entry(entry: str) -> bool:
    if entry == "" or entry == os.curdir:
        return False
    expanded = os.path.expanduser(os.path.expandvars(entry))
    if os.name == "nt":
        return ntpath.isabs(expanded)
    return Path(expanded).is_absolute()


def _resolve_windows_opa_command_wrapper_path(resolved: str) -> str:
    normalized = ntpath.normpath(_resolve_windows_filesystem_path(resolved))
    normalized_for_compare = ntpath.normcase(normalized)
    trusted_roots = _trusted_windows_opa_wrapper_roots()
    if not ntpath.isabs(normalized) or not any(
        _windows_path_is_relative_to(normalized_for_compare, trusted_root) for trusted_root in trusted_roots
    ):
        allowed = ", ".join(trusted_roots)
        raise OpaEvaluationError(
            f"authorized {OEP_OPA_COMMAND_WRAPPER_ENV} executable resolved to untrusted path: {normalized}. "
            f"Expected one of: {allowed}"
        )
    return normalized


def _resolve_windows_filesystem_path(resolved: str) -> str:
    try:
        candidate = str(Path(resolved).resolve(strict=False))
    except (OSError, RuntimeError):
        return resolved
    # Non-Windows test runners cannot resolve Windows drive paths faithfully.
    # On real Windows this keeps junction/symlink resolution in the trust check.
    if ntpath.isabs(candidate) and ntpath.splitdrive(candidate)[0]:
        return candidate
    return resolved


def _trusted_windows_opa_wrapper_roots() -> tuple[str, ...]:
    system_root = next(
        (value for name in WINDOWS_SYSTEM_ROOT_ENV_NAMES if (value := os.environ.get(name))),
        WINDOWS_SYSTEM_ROOT_FALLBACK,
    )
    roots = [ntpath.join(system_root, "System32")]
    roots.extend(
        value
        for name in WINDOWS_TRUSTED_OPA_WRAPPER_ROOT_ENV_NAMES
        if (value := os.environ.get(name))
    )
    return tuple(ntpath.normcase(ntpath.normpath(root)) for root in roots)


def _windows_path_is_relative_to(path: str, root: str) -> bool:
    try:
        return ntpath.commonpath((path, root)) == root
    except ValueError:
        return False


def _validate_opa_command_wrapper(wrapper_args: Sequence[str]) -> None:
    executable = wrapper_args[0]
    if executable not in ALLOWED_OPA_COMMAND_WRAPPERS:
        allowed = ", ".join(sorted(ALLOWED_OPA_COMMAND_WRAPPERS))
        raise OpaEvaluationError(
            f"unauthorized {OEP_OPA_COMMAND_WRAPPER_ENV} executable: {executable!r}. "
            f"Allowed wrappers: {allowed}"
        )
    if executable == "docker":
        _validate_docker_opa_command_wrapper(wrapper_args)
        return
    _validate_option_only_opa_command_wrapper(executable, wrapper_args)


def _validate_option_only_opa_command_wrapper(executable: str, wrapper_args: Sequence[str]) -> None:
    allowed_options = ALLOWED_OPA_COMMAND_WRAPPER_OPTIONS[executable]
    value_options = OPA_WRAPPER_OPTIONS_WITH_VALUES[executable]
    index = 1
    while index < len(wrapper_args):
        argument = wrapper_args[index]
        option, inline_value = _split_wrapper_option(argument)
        if option not in allowed_options:
            _raise_unauthorized_opa_wrapper_argument(argument)
        if inline_value is not None:
            if option not in value_options:
                _raise_unauthorized_opa_wrapper_argument(argument)
            _validate_opa_wrapper_option_value(executable, option, inline_value, argument)
        elif option in value_options:
            index += 1
            if index >= len(wrapper_args):
                _raise_unauthorized_opa_wrapper_argument(argument)
            _validate_opa_wrapper_option_value(executable, option, wrapper_args[index], wrapper_args[index])
        index += 1


def _validate_docker_opa_command_wrapper(wrapper_args: Sequence[str]) -> None:
    if len(wrapper_args) < 2 or wrapper_args[1] != "run":
        argument = wrapper_args[1] if len(wrapper_args) > 1 else "<missing docker subcommand>"
        _raise_unauthorized_opa_wrapper_argument(argument)

    allowed_options = ALLOWED_OPA_COMMAND_WRAPPER_OPTIONS["docker"]
    value_options = OPA_WRAPPER_OPTIONS_WITH_VALUES["docker"]
    image_seen = False
    index = 2
    while index < len(wrapper_args):
        argument = wrapper_args[index]
        option, inline_value = _split_wrapper_option(argument)
        if not image_seen and option in allowed_options and option != "run":
            if inline_value is not None:
                if option not in value_options:
                    _raise_unauthorized_opa_wrapper_argument(argument)
                _validate_docker_wrapper_option_value(option, inline_value, argument)
            elif option in value_options:
                index += 1
                if index >= len(wrapper_args):
                    _raise_unauthorized_opa_wrapper_argument(argument)
                _validate_docker_wrapper_option_value(option, wrapper_args[index], wrapper_args[index])
            index += 1
            continue
        if not image_seen and OPA_DOCKER_IMAGE_RE.fullmatch(argument):
            image_seen = True
            index += 1
            continue
        _raise_unauthorized_opa_wrapper_argument(argument)

    if not image_seen:
        _raise_unauthorized_opa_wrapper_argument("<missing docker image>")


def _split_wrapper_option(argument: str) -> tuple[str, str | None]:
    if argument.startswith("--") and "=" in argument:
        option, value = argument.split("=", 1)
        return option, value
    return argument, None


def _validate_opa_wrapper_option_value(
    executable: str,
    option: str,
    value: str,
    argument: str,
) -> None:
    if executable == "sudo":
        if OPA_WRAPPER_USER_VALUE_RE.fullmatch(value):
            return
    elif OPA_WRAPPER_NUMERIC_VALUE_RE.fullmatch(value):
        return
    _raise_unauthorized_opa_wrapper_argument(f"{option} {argument}")


def _validate_docker_wrapper_option_value(option: str, value: str, argument: str) -> None:
    if option == "--network":
        if value == "none":
            return
    elif option == "--user":
        if OPA_WRAPPER_USER_VALUE_RE.fullmatch(value):
            return
    elif option == "--memory":
        if OPA_DOCKER_MEMORY_VALUE_RE.fullmatch(value):
            return
    elif option in {"--volume", "-v"}:
        _validate_docker_read_only_volume(value, argument)
        return
    elif OPA_WRAPPER_NUMERIC_VALUE_RE.fullmatch(value):
        return
    _raise_unauthorized_opa_wrapper_argument(f"{option} {argument}")


def _opa_policy_bundle_data_path(policy_bundle_path: Path) -> str:
    wrapper = os.environ.get(OEP_OPA_COMMAND_WRAPPER_ENV)
    if wrapper is None or wrapper.strip() == "":
        return str(policy_bundle_path)
    try:
        wrapper_args = shlex.split(wrapper)
    except ValueError:
        return str(policy_bundle_path)
    if len(wrapper_args) < 2 or wrapper_args[0] != "docker" or wrapper_args[1] != "run":
        return str(policy_bundle_path)

    policy_path = policy_bundle_path.resolve(strict=False)
    for source, target in _docker_read_only_volume_mappings(wrapper_args):
        source_path = Path(os.path.expanduser(os.path.expandvars(source))).resolve(strict=False)
        try:
            relative_policy_path = policy_path.relative_to(source_path)
        except ValueError:
            continue
        target_path = PurePosixPath(target)
        if relative_policy_path.parts:
            target_path = target_path.joinpath(*relative_policy_path.parts)
        return target_path.as_posix()
    return str(policy_bundle_path)


def _docker_read_only_volume_mappings(wrapper_args: Sequence[str]) -> list[tuple[str, str]]:
    mappings: list[tuple[str, str]] = []
    image_seen = False
    index = 2
    while index < len(wrapper_args):
        argument = wrapper_args[index]
        option, inline_value = _split_wrapper_option(argument)
        if not image_seen and option in {"--volume", "-v"}:
            if inline_value is not None:
                mappings.append(_docker_read_only_volume_mapping(inline_value, argument))
            else:
                index += 1
                if index >= len(wrapper_args):
                    _raise_unauthorized_opa_wrapper_argument(argument)
                mappings.append(_docker_read_only_volume_mapping(wrapper_args[index], wrapper_args[index]))
            index += 1
            continue
        if not image_seen and option in ALLOWED_OPA_COMMAND_WRAPPER_OPTIONS["docker"] and option != "run":
            if inline_value is None and option in OPA_WRAPPER_OPTIONS_WITH_VALUES["docker"]:
                index += 1
            index += 1
            continue
        if not image_seen and OPA_DOCKER_IMAGE_RE.fullmatch(argument):
            image_seen = True
        index += 1
    return mappings


def _validate_docker_read_only_volume(value: str, argument: str) -> None:
    _docker_read_only_volume_mapping(value, argument)


def _docker_read_only_volume_mapping(value: str, argument: str) -> tuple[str, str]:
    parts = value.rsplit(":", 2)
    if len(parts) != 3:
        _raise_unauthorized_opa_wrapper_argument(argument)
    source, target, mode = parts
    if mode != "ro":
        _raise_unauthorized_opa_wrapper_argument(argument)
    if not _is_absolute_host_volume_source(source):
        _raise_unauthorized_opa_wrapper_argument(argument)
    target_path = PurePosixPath(target)
    if not target or not target_path.is_absolute() or ".." in target_path.parts:
        _raise_unauthorized_opa_wrapper_argument(argument)
    return source, target


def _is_absolute_host_volume_source(source: str) -> bool:
    if not source or "\x00" in source or "\n" in source:
        return False
    expanded = os.path.expanduser(os.path.expandvars(source))
    return Path(expanded).is_absolute() or ntpath.isabs(expanded)


def _raise_unauthorized_opa_wrapper_argument(argument: str) -> Never:
    raise OpaEvaluationError(
        f"unauthorized {OEP_OPA_COMMAND_WRAPPER_ENV} argument: {argument!r}. "
        "Wrapper arguments must use the allow-listed options and strict value formats for the selected wrapper."
    )


def _opa_eval_timeout_seconds(timeout_seconds: float | None) -> float:
    if timeout_seconds is not None:
        return _require_positive_timeout_seconds(timeout_seconds, "timeout_seconds")

    raw_timeout = os.environ.get(OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV)
    if raw_timeout is None or raw_timeout == "":
        return float(OPA_EVAL_TIMEOUT_SECONDS)
    try:
        timeout = float(raw_timeout)
    except ValueError as exc:
        raise OpaEvaluationError(_timeout_validation_message(OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV)) from exc
    return _require_positive_timeout_seconds(timeout, OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV)


def _require_positive_timeout_seconds(timeout: float, field: str) -> float:
    if not math.isfinite(timeout) or timeout < MIN_OPA_EVAL_TIMEOUT_SECONDS:
        raise OpaEvaluationError(_timeout_validation_message(field))
    return timeout


def _timeout_validation_message(field: str) -> str:
    return f"{field} must be a number of seconds greater than or equal to {MIN_OPA_EVAL_TIMEOUT_SECONDS}"


def _format_timeout_seconds(timeout: float) -> str:
    return str(int(timeout)) if timeout.is_integer() else str(timeout)


def _snapshot_from_record(record: ReplayRecord) -> dict[str, Any]:
    decision = _require_object(record.permission_packet.get("decision"), "decision")
    policy = _require_object(record.permission_packet.get("policy"), "policy")
    return {
        "policy_bundle_version": record.policy_bundle_version or _require_string(
            policy.get("policy_version"),
            "policy.policy_version",
        ),
        "decision": _decision_label(decision.get("allow")),
        "rationale": _require_string(decision.get("reason"), "decision.reason"),
        "matched_rules": _matched_rules(decision),
    }


def _snapshot_from_opa_decision(decision: dict[str, Any], policy_bundle_version: str) -> dict[str, Any]:
    snapshot = {
        "policy_bundle_version": policy_bundle_version,
        "decision": _decision_label(decision.get("allow")),
        "rationale": _require_string(decision.get("reason"), "decision.reason"),
        "matched_rules": _matched_rules(decision),
    }
    decision_code = decision.get("decision_code")
    if decision_code is not None:
        snapshot["decision_code"] = _require_string(decision_code, "decision.decision_code")
    return snapshot


def _decision_diff(original: dict[str, Any], counterfactual: dict[str, Any]) -> dict[str, Any]:
    original_rules = set(_string_list(original.get("matched_rules"), "original.matched_rules"))
    counterfactual_rules = set(_string_list(counterfactual.get("matched_rules"), "counterfactual.matched_rules"))
    return {
        "decision_changed": original.get("decision") != counterfactual.get("decision"),
        "rationale_changed": original.get("rationale") != counterfactual.get("rationale"),
        "rule_set_delta": {
            "added": sorted(counterfactual_rules - original_rules),
            "removed": sorted(original_rules - counterfactual_rules),
            "unchanged": sorted(original_rules & counterfactual_rules),
        },
        "workflow_delta": None,
        "budget_delta": None,
        "approval_delta": None,
    }


def _counterfactual_policy_version(policy_bundle_path: Path) -> str:
    from oep_verify.verify_support import sha256_digest

    return sha256_digest(policy_bundle_path)


def _nd_builtin_cache_entry_count(cache: dict[str, Any] | None) -> int:
    if cache is None:
        return 0
    count = 0
    for builtin_cache in cache.values():
        if isinstance(builtin_cache, dict):
            count += len(builtin_cache)
    return count


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _matched_rules(decision: dict[str, Any]) -> list[str]:
    matched_rules = decision.get("matched_rules")
    if matched_rules is not None:
        return _string_list(matched_rules, "decision.matched_rules")
    return [_require_string(decision.get("matched_rule"), "decision.matched_rule")]


def _decision_label(allow: object) -> str:
    if not isinstance(allow, bool):
        raise ReplayError("decision.allow must be a boolean")
    return "allow" if allow else "deny"


def _require_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReplayError(f"replay state row is missing required object field {field!r}")
    return value


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ReplayError(f"{field} must be an array")
    strings = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ReplayError(f"{field} must contain non-empty strings")
        strings.append(item)
    return strings


def _validate_counterfactual_replay(record: dict[str, Any]) -> None:
    from oep_verify.verify_support import validate_json_schema_from_path

    try:
        validate_json_schema_from_path(
            COUNTERFACTUAL_REPLAY_SCHEMA_PATH,
            record,
            instance_path=COUNTERFACTUAL_REPLAY_SCHEMA_PATH,
        )
    except ValueError as exc:
        raise SchemaValidationError(f"counterfactual replay output failed schema validation: {exc}") from exc


def _freeze_json_object(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({key: _freeze_json_value(item) for key, item in value.items()})


def _freeze_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_json_object(value)
    if isinstance(value, list | tuple):
        return tuple(_freeze_json_value(item) for item in value)
    return value


def _thaw_json_object(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _thaw_json_value(item) for key, item in value.items()}


def _thaw_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _thaw_json_object(value)
    if isinstance(value, tuple):
        return [_thaw_json_value(item) for item in value]
    return value


__all__ = [
    "CounterfactualReplayRecord",
    "JoinInconsistencyError",
    "OEP_OPA_COMMAND_WRAPPER_ENV",
    "OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV",
    "OPA_STDIN_INPUT_LIMIT_BYTES",
    "OPA_EVAL_TIMEOUT_SECONDS",
    "OpaEvaluationError",
    "ReplayError",
    "ReplayRecord",
    "SchemaValidationError",
    "StateNotFoundError",
    "counterfactual_replay_decision",
    "counterfactual_replay_decisions",
    "reconstruct_decisions",
    "reconstruct_decision",
]
