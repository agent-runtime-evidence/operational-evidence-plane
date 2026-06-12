"""SQLite reconstruction of recorded permission decisions and their joins."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from typing import Any, Never

from oep_permissions.replay.records import (
    JoinInconsistencyError,
    ReplayError,
    ReplayRecord,
    StateNotFoundError,
    _loads_object,
    _optional_string,
    _ReplayPayloadCache,
    _require_string,
    _validate_permission_packet,
)

SQLITE_REPLAY_BUSY_TIMEOUT_SECONDS = 10.0


DEFAULT_SQLITE_BATCH_VARIABLE_LIMIT = 900


MAX_SQLITE_BATCH_VARIABLE_LIMIT = 32766


SQLITE_BATCH_PLACEHOLDER_BASE_BUCKETS = (1, 2, 4, 8, 16, 32, 64, 128, 256, 512)


OEP_SQLITE_BATCH_VARIABLE_LIMIT_ENV = "OEP_SQLITE_BATCH_VARIABLE_LIMIT"


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
    batch_limit = _sqlite_batch_variable_limit()
    for start in range(0, len(unique_decision_ids), batch_limit):
        batch = unique_decision_ids[start : start + batch_limit]
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


def _sqlite_batch_variable_limit() -> int:
    raw_limit = os.environ.get(OEP_SQLITE_BATCH_VARIABLE_LIMIT_ENV)
    if raw_limit is None or raw_limit.strip() == "":
        return DEFAULT_SQLITE_BATCH_VARIABLE_LIMIT
    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise ReplayError(
            f"{OEP_SQLITE_BATCH_VARIABLE_LIMIT_ENV} must be an integer between 1 "
            f"and {MAX_SQLITE_BATCH_VARIABLE_LIMIT}"
        ) from exc
    if not 1 <= limit <= MAX_SQLITE_BATCH_VARIABLE_LIMIT:
        raise ReplayError(
            f"{OEP_SQLITE_BATCH_VARIABLE_LIMIT_ENV} must be an integer between 1 "
            f"and {MAX_SQLITE_BATCH_VARIABLE_LIMIT}"
        )
    return limit


def _sqlite_batch_placeholder_buckets(limit: int) -> tuple[int, ...]:
    return tuple(bucket for bucket in SQLITE_BATCH_PLACEHOLDER_BASE_BUCKETS if bucket < limit) + (limit,)


def _decision_id_placeholders(batch_size: int) -> str:
    return ",".join("?" for _ in range(_decision_id_placeholder_bucket(batch_size)))


def _padded_decision_id_parameters(batch: Sequence[str]) -> tuple[str | None, ...]:
    bucket_size = _decision_id_placeholder_bucket(len(batch))
    return tuple(batch) + ((None,) * (bucket_size - len(batch)))


def _decision_id_placeholder_bucket(batch_size: int) -> int:
    limit = _sqlite_batch_variable_limit()
    if not 1 <= batch_size <= limit:
        raise ReplayError(f"decision batch size must be between 1 and {limit}")
    for bucket_size in _sqlite_batch_placeholder_buckets(limit):
        if batch_size <= bucket_size:
            return bucket_size
    raise ReplayError(f"decision batch size must be between 1 and {limit}")


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

    decision_metadata = permission.get("decision_id")
    if decision_metadata is not None and not isinstance(decision_metadata, dict):
        raise ReplayError("permission.decision_id must be an object or null in replay state")

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
        decision_metadata=decision_metadata if isinstance(decision_metadata, dict) else None,
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
