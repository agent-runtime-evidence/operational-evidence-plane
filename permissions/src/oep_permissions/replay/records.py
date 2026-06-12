"""Records, errors, and shared value helpers for permission decision replay."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from oep_permissions.paths import COUNTERFACTUAL_REPLAY_SCHEMA_PATH, SCHEMA_PATH

COUNTERFACTUAL_CLAIM_BOUNDARY = (
    "This record is an inspectable counterfactual policy replay output for the reference implementation. "
    "It is not a production-grade replay engine, compliance certification, or legal/regulatory adequacy claim."
)


V03_COUNTERFACTUAL_CLAIM_BOUNDARY = (
    "This record is an inspectable v0.3 counterfactual replay output for the reference implementation. "
    "Deterministic surfaces are rule replays over recorded fields; evaluative surfaces are counterfactual "
    "estimates and are not what-would-have-happened claims."
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
    decision_metadata: dict[str, Any] | None

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
            "decision_metadata": self.decision_metadata,
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


def _non_negative_number(value: object, field: str) -> float:
    if not isinstance(value, int | float) or value < 0:
        raise ReplayError(f"{field} must be a non-negative number")
    return float(value)


def _stable_number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


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
