"""Replay reader over local SQLite replay state.

The v0.2 `oep replay <decision_id>` subcommand is a thin reader over the
existing demo SQLite replay store. It does not introduce new persistence,
live model calls, or service dependencies; it reconstructs the recorded
permission trace by joining rows already written by the deterministic
demo runner.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from oep_permissions.paths import SCHEMA_PATH


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
        }


class ReplayError(RuntimeError):
    """Raised when a decision cannot be reconstructed from local replay state."""


def reconstruct_decision(state_path: Path, decision_id: str) -> ReplayRecord:
    """Reconstruct the recorded permission trace for a decision id.

    `decision_id` matches the permission packet identifier (the `pder_*`
    value stored as `permissions.packet_id`). The function reads only;
    it does not write to the SQLite store.
    """

    if not state_path.is_file():
        raise ReplayError(
            f"replay state not found at {state_path}. "
            "Run `oep-run-demo` or `make verify` to regenerate it."
        )

    connection = sqlite3.connect(state_path)
    try:
        connection.row_factory = sqlite3.Row
        permission_row = connection.execute(
            "SELECT payload_json FROM permissions WHERE packet_id = ?",
            (decision_id,),
        ).fetchone()
        if permission_row is None:
            event_row = connection.execute(
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
            raise ReplayError(
                f"no recorded decision found for decision_id={decision_id!r}.{denied_hint}"
            )
        permission = _loads_object(permission_row["payload_json"], "permission payload")
        _validate_permission_packet(permission, state_path)

        event_id = _require_string(permission.get("event_id"), "event_id")
        event_row = connection.execute(
            "SELECT payload_json FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if event_row is None:
            raise ReplayError(
                f"recorded decision {decision_id!r} has no joined event row (event_id={event_id!r})"
            )
        event = _loads_object(event_row["payload_json"], "event payload")

        trace_id = _require_string(permission.get("trace_id"), "trace_id")
        trace_row = connection.execute(
            "SELECT payload_json FROM traces WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()
        trace = _loads_object(trace_row["payload_json"], "trace payload") if trace_row else None

        manifest_id = _require_string(event.get("release_manifest_id"), "release_manifest_id")
        manifest_row = connection.execute(
            "SELECT payload_json FROM artifacts WHERE kind = ? AND artifact_id = ?",
            ("release_manifest", manifest_id),
        ).fetchone()
        manifest_summary: dict[str, Any] | None = None
        if manifest_row is not None:
            manifest = _loads_object(manifest_row["payload_json"], "manifest payload")
            release = manifest.get("release") if isinstance(manifest.get("release"), dict) else {}
            manifest_summary = {
                "manifest_id": manifest.get("manifest_id"),
                "scenario": release.get("scenario") if isinstance(release, dict) else None,
                "release_name": release.get("name") if isinstance(release, dict) else None,
                "release_version": release.get("version") if isinstance(release, dict) else None,
            }
    finally:
        connection.close()

    replay_handle = event.get("replay_handle")
    if replay_handle is not None and not isinstance(replay_handle, dict):
        raise ReplayError("event.replay_handle must be an object or null in replay state")

    approval_capture = permission.get("approval_capture")
    if approval_capture is not None and not isinstance(approval_capture, dict):
        raise ReplayError("permission.approval_capture must be an object or null in replay state")

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
    )


def _loads_object(text: object, field: str) -> dict[str, Any]:
    if not isinstance(text, str):
        raise ReplayError(f"{field} must be a JSON string in replay state")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ReplayError(f"{field} must decode to a JSON object")
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

    from oep_verify.verify_support import load_json_object, validate_json_schema

    schema = load_json_object(SCHEMA_PATH)
    try:
        validate_json_schema(schema, packet, instance_path=state_path)
    except AssertionError as exc:
        raise ReplayError(
            f"permission packet stored in {state_path} failed schema validation: {exc}"
        ) from exc


__all__ = ["ReplayError", "ReplayRecord", "reconstruct_decision"]
