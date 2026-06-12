"""Counterfactual replay, surface diffs, and substitution deltas."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any

from oep_permissions.replay.opa import (
    _evaluate_opa_decisions,
    _policy_input_from_record,
)
from oep_permissions.replay.records import (
    V03_COUNTERFACTUAL_CLAIM_BOUNDARY,
    CounterfactualReplayRecord,
    OpaEvaluationError,
    ReplayError,
    ReplayRecord,
    _decision_label,
    _matched_rules,
    _non_negative_number,
    _require_object,
    _require_string,
    _stable_number,
    _string_list,
    _utc_now,
    _validate_counterfactual_replay,
)
from oep_permissions.replay.storage import (
    reconstruct_decision,
    reconstruct_decisions,
)

SURFACE_NAMES = ("model", "policy", "prompt", "tool", "corpus")


SURFACE_FIELD_BY_NAME: Mapping[str, str] = MappingProxyType(
    {
        "model": "model_version",
        "policy": "policy_bundle",
        "prompt": "prompt_template",
        "tool": "tool_registry",
        "corpus": "retrieval_corpus",
    }
)


DETERMINISTIC_SURFACES = frozenset({"policy", "prompt", "tool", "corpus", "budget", "reserve", "cache_staleness"})


EVALUATIVE_SURFACES = frozenset({"model", "cache_fresh_call", "projection"})


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


def decision_surface_presence(
    state_path: Path | sqlite3.Connection,
    decision_id: str,
    *,
    validate_schema: bool = True,
) -> dict[str, Any]:
    """Report which optional v0.3 decision-id sub-objects are present.

    Older v0.1/v0.2 records do not carry the v0.3 composite metadata. The
    replay reader treats that as an absent surface report rather than a
    reconstruction error.
    """

    record = reconstruct_decision(state_path, decision_id, validate_schema=validate_schema)
    metadata = _decision_metadata(record)
    surface_names = ("permission", "cost", "drift", "cache", "identity")
    surfaces = {
        name: {"present": isinstance(metadata.get(name), dict)}
        for name in surface_names
    }
    absent = [name for name in surface_names if not surfaces[name]["present"]]
    return {
        "schema_version": "oep.decision_surface_presence.v0",
        "decision_id": decision_id,
        "decision_schema_version": metadata.get("schema_version", "not_recorded"),
        "surfaces": surfaces,
        "absent_surfaces": absent,
        "replayable": True,
    }


def diff_decision_surfaces(
    state_path: Path | sqlite3.Connection,
    decision_id_a: str,
    decision_id_b: str,
    *,
    surfaces: Sequence[str] | None = None,
    validate_schema: bool = True,
) -> dict[str, Any]:
    """Return the v0.3 five-surface config diff between two decisions."""

    requested_surfaces = _normalize_surface_names(surfaces)
    before, after = reconstruct_decisions(
        state_path,
        [decision_id_a, decision_id_b],
        validate_schema=validate_schema,
    )
    surface_rows = {
        surface: _surface_diff_row(before, after, surface)
        for surface in requested_surfaces
    }
    changed = [surface for surface in requested_surfaces if surface_rows[surface]["status"] == "changed"]
    absent = [surface for surface in requested_surfaces if surface_rows[surface]["status"] == "not_recorded"]
    return {
        "schema_version": "oep.surface_diff.v0",
        "replay_class": "deterministic",
        "decision_ids": {
            "before": decision_id_a,
            "after": decision_id_b,
        },
        "changed_surfaces": changed,
        "absent_surfaces": absent,
        "surfaces": surface_rows,
        "claim_boundary": (
            "This is a deterministic config-surface diff over recorded decision metadata. It does not "
            "re-execute an LLM or claim that a different model output would have occurred."
        ),
    }


def replay_decision_with_substitutions(
    state_path: Path | sqlite3.Connection,
    decision_id: str,
    *,
    substitutions: Mapping[str, str] | None = None,
    policy_bundle_path: Path | None = None,
    budget_policy: str | None = None,
    model_substitute: str | None = None,
    cache_policy: str | None = None,
    replay_timestamp_utc: str | None = None,
    validate_schema: bool = True,
) -> dict[str, Any]:
    """Compose v0.3 counterfactual substitutions over one recorded decision.

    Deterministic surfaces operate over stored fields and OPA policy inputs.
    Model-provider and cache-fresh-call substitutions are labelled
    evaluative because they require a new stochastic model execution outside
    this reference replay engine.
    """

    normalized = _normalize_substitutions(substitutions)
    if model_substitute is not None:
        normalized["model"] = model_substitute
    if policy_bundle_path is not None:
        normalized["policy"] = str(policy_bundle_path)
    if budget_policy is not None:
        normalized["budget"] = budget_policy
    if cache_policy is not None:
        normalized["cache"] = cache_policy

    record = reconstruct_decision(state_path, decision_id, validate_schema=validate_schema)
    replay_timestamp_utc = _validate_replay_timestamp_utc(replay_timestamp_utc)
    policy_path = _substituted_policy_path(normalized)
    if policy_path is None:
        output = _base_counterfactual_output(record, replay_timestamp_utc)
    else:
        output = counterfactual_replay_decision(
            state_path,
            decision_id,
            policy_path,
            replay_timestamp_utc=replay_timestamp_utc,
            validate_schema=validate_schema,
        ).to_dict()

    output["claim_boundary"] = V03_COUNTERFACTUAL_CLAIM_BOUNDARY
    diff = _require_object(output.get("diff"), "diff")
    replay_class = "deterministic"
    substituted_surfaces: dict[str, str] = {}
    for key, value in normalized.items():
        substituted_surfaces[key] = value

    surface_delta = _surface_delta_for_substitutions(record, normalized)
    if surface_delta is not None:
        diff["surface_delta"] = surface_delta

    if "budget" in normalized:
        budget_delta = _budget_delta_from_policy(record, normalized["budget"])
        diff["budget_delta"] = budget_delta
        if budget_delta.get("termination_step") is not None:
            _apply_budget_denial(output, budget_delta)

    if "model" in normalized:
        diff["model_delta"] = _model_delta_from_substitution(record, normalized["model"])
        replay_class = "evaluative"

    if "cache" in normalized:
        cache_delta, cache_replay_class = _cache_delta_from_policy(record, normalized["cache"])
        diff["cache_delta"] = cache_delta
        if cache_replay_class == "evaluative":
            replay_class = "evaluative"

    metadata = _require_object(output.get("replay_metadata"), "replay_metadata")
    metadata["replay_class"] = replay_class
    metadata["substituted_surfaces"] = substituted_surfaces
    _validate_counterfactual_replay(output)
    return output


def simulate_reserve_commit_release(
    reservations: Sequence[Mapping[str, Any]],
    *,
    budget_cap_usd: float,
    budget_cap_source: str = "per_session",
) -> dict[str, Any]:
    """Deterministically simulate reserve -> commit -> release accounting."""

    if budget_cap_usd < 0:
        raise ReplayError("budget_cap_usd must be non-negative")
    if budget_cap_source not in {"per_session", "per_tenant", "per_agent"}:
        raise ReplayError("budget_cap_source must be per_session, per_tenant, or per_agent")

    committed_total = 0.0
    released_total = 0.0
    rows: list[dict[str, Any]] = []
    first_denied: str | None = None
    for index, reservation in enumerate(reservations, start=1):
        reservation_id = _require_string(reservation.get("budget_reservation_id"), "budget_reservation_id")
        estimated = _non_negative_number(reservation.get("reservation_estimated_cost_usd"), "estimated cost")
        committed = _non_negative_number(reservation.get("reservation_committed_cost_usd"), "committed cost")
        would_exhaust = committed_total + estimated > budget_cap_usd
        if would_exhaust:
            outcome = "denied_budget_exhausted"
            released = 0.0
            effective_committed = 0.0
            if first_denied is None:
                first_denied = reservation_id
        else:
            outcome = "committed"
            effective_committed = committed
            released = max(estimated - committed, 0.0)
            committed_total += committed
            released_total += released
        rows.append(
            {
                "step": index,
                "budget_reservation_id": reservation_id,
                "reservation_estimated_cost_usd": _stable_number(estimated),
                "reservation_committed_cost_usd": _stable_number(effective_committed),
                "reservation_excess_released_usd": _stable_number(released),
                "budget_cap_active_at_reservation_time": True,
                "reservation_outcome": outcome,
                "committed_total_usd": _stable_number(committed_total),
                "remaining_budget_usd": _stable_number(max(budget_cap_usd - committed_total, 0.0)),
            }
        )

    return {
        "schema_version": "oep.reserve_commit_release.v0",
        "replay_class": "deterministic",
        "budget_cap_source": budget_cap_source,
        "budget_cap_usd": _stable_number(budget_cap_usd),
        "first_denied_reservation_id": first_denied,
        "reservation_outcomes": rows,
        "committed_total_usd": _stable_number(committed_total),
        "released_total_usd": _stable_number(released_total),
    }


def project_pre_session_cost(
    *,
    projected_min_usd: float,
    projected_max_usd: float,
    budget_cap_usd: float,
    approver_identity: Mapping[str, Any],
    approve: bool,
) -> dict[str, Any]:
    """Record a pre-session cost projection decision.

    Projection is labelled evaluative because the projected window is an
    estimate. The approval outcome is deterministic over the recorded
    estimate and explicit approval flag.
    """

    if projected_min_usd < 0 or projected_max_usd < 0 or budget_cap_usd < 0:
        raise ReplayError("projection and budget values must be non-negative")
    if projected_min_usd > projected_max_usd:
        raise ReplayError("projected_min_usd must not exceed projected_max_usd")
    approver = {
        "type": _require_string(approver_identity.get("type"), "approver type"),
        "id": _require_string(approver_identity.get("id"), "approver id"),
        "display_name": _require_string(approver_identity.get("display_name"), "approver display_name"),
    }
    outcome = "approved" if approve and projected_max_usd <= budget_cap_usd else "denied"
    return {
        "schema_version": "oep.pre_session_projection.v0",
        "replay_class": "evaluative",
        "projected_cost_window": {
            "estimated_min_usd": _stable_number(projected_min_usd),
            "estimated_max_usd": _stable_number(projected_max_usd),
        },
        "budget_cap_usd": _stable_number(budget_cap_usd),
        "approver_identity": approver,
        "approval_outcome": outcome,
        "claim_boundary": (
            "Pre-session projection records an estimate and an approval decision; it is not a deterministic "
            "prediction of actual run cost."
        ),
    }


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


def _normalize_surface_names(surfaces: Sequence[str] | None) -> tuple[str, ...]:
    if surfaces is None:
        return SURFACE_NAMES
    normalized: list[str] = []
    for raw_surface in surfaces:
        for surface in raw_surface.split(","):
            name = surface.strip()
            if not name:
                continue
            if name not in SURFACE_FIELD_BY_NAME:
                allowed = ", ".join(SURFACE_NAMES)
                raise ReplayError(f"unknown diff surface {name!r}; expected one of: {allowed}")
            if name not in normalized:
                normalized.append(name)
    return tuple(normalized) if normalized else SURFACE_NAMES


def _decision_metadata(record: ReplayRecord) -> dict[str, Any]:
    return record.decision_metadata if isinstance(record.decision_metadata, dict) else {}


def _surface_diff_row(before: ReplayRecord, after: ReplayRecord, surface: str) -> dict[str, Any]:
    before_change = _surface_change(before, surface)
    after_change = _surface_change(after, surface)
    before_version = _surface_effective_version(before_change, before, surface)
    after_version = _surface_effective_version(after_change, after, surface)
    if before_version is None and after_version is None:
        return {
            "status": "not_recorded",
            "before_version": None,
            "after_version": None,
            "change_class": None,
            "attribution_confidence": None,
        }

    changed = before_version != after_version
    return {
        "status": "changed" if changed else "unchanged",
        "before_version": before_version,
        "after_version": after_version,
        "change_class": _surface_change_class(after_change, surface) if changed else None,
        "attribution_confidence": _surface_attribution_confidence(after_change) if changed else None,
    }


def _surface_change(record: ReplayRecord, surface: str) -> dict[str, Any]:
    metadata = _decision_metadata(record)
    drift = metadata.get("drift")
    if not isinstance(drift, dict):
        return {}
    change = drift.get(SURFACE_FIELD_BY_NAME[surface])
    return change if isinstance(change, dict) else {}


def _surface_effective_version(change: Mapping[str, Any], record: ReplayRecord, surface: str) -> str | None:
    after_version = change.get("after_version")
    if isinstance(after_version, str) and after_version:
        return after_version
    before_version = change.get("before_version")
    if isinstance(before_version, str) and before_version:
        return before_version
    if surface == "model":
        return record.resolved_model_version
    if surface == "policy":
        return record.policy_bundle_version
    return None


def _surface_change_class(change: Mapping[str, Any], surface: str) -> str | None:
    value = change.get("change_class")
    if isinstance(value, str) and value:
        return value
    return {
        "model": "alias_resolution",
        "policy": "policy_update",
        "prompt": "prompt_edit",
        "tool": "tool_added_removed",
        "corpus": "corpus_indexed",
    }[surface]


def _surface_attribution_confidence(change: Mapping[str, Any]) -> float | None:
    value = change.get("attribution_confidence")
    if isinstance(value, int | float):
        return float(value)
    return None


def _normalize_substitutions(substitutions: Mapping[str, str] | None) -> dict[str, str]:
    if substitutions is None:
        return {}
    normalized: dict[str, str] = {}
    allowed = set(SURFACE_NAMES) | {"budget", "cache"}
    for raw_key, raw_value in substitutions.items():
        key = raw_key.strip()
        value = raw_value.strip()
        if key not in allowed:
            expected = ", ".join(sorted(allowed))
            raise ReplayError(f"unknown substitution surface {key!r}; expected one of: {expected}")
        if not value:
            raise ReplayError(f"substitution value for {key!r} must be non-empty")
        normalized[key] = value
    return normalized


def _substituted_policy_path(substitutions: Mapping[str, str]) -> Path | None:
    raw_policy = substitutions.get("policy")
    if raw_policy is None:
        return None
    policy_path = Path(raw_policy)
    if policy_path.exists():
        return policy_path
    return None


def _base_counterfactual_output(record: ReplayRecord, replay_timestamp_utc: str | None) -> dict[str, Any]:
    snapshot = _snapshot_from_record(record)
    result = CounterfactualReplayRecord(
        decision_id=record.decision_id,
        original=snapshot,
        counterfactual=snapshot,
        diff=_decision_diff(snapshot, snapshot),
        replay_metadata={
            "oep_replay_mode": "counterfactual",
            "nd_builtin_cache_entries_used": _nd_builtin_cache_entry_count(record.nd_builtin_cache),
            "replay_timestamp_utc": replay_timestamp_utc or _utc_now(),
            "determinism_exclusions": ["replay_metadata.replay_timestamp_utc"],
        },
    )
    return result.to_dict()


def _surface_delta_for_substitutions(record: ReplayRecord, substitutions: Mapping[str, str]) -> dict[str, Any] | None:
    requested_surfaces = tuple(surface for surface in SURFACE_NAMES if surface in substitutions)
    if not requested_surfaces:
        return None

    surface_rows: dict[str, dict[str, Any]] = {}
    changed: list[str] = []
    absent: list[str] = []
    for surface in requested_surfaces:
        change = _surface_change(record, surface)
        before_version = _surface_effective_version(change, record, surface)
        after_version = _substitution_effective_version(surface, substitutions[surface])
        if before_version is None:
            status = "not_recorded"
            absent.append(surface)
        elif before_version == after_version:
            status = "unchanged"
        else:
            status = "changed"
            changed.append(surface)
        surface_rows[surface] = {
            "status": status,
            "before_version": before_version,
            "after_version": after_version,
            "change_class": _surface_change_class(change, surface) if status == "changed" else None,
            "attribution_confidence": _surface_attribution_confidence(change) if status == "changed" else None,
        }

    return {
        "changed_surfaces": changed,
        "absent_surfaces": absent,
        "surfaces": surface_rows,
    }


def _substitution_effective_version(surface: str, value: str) -> str:
    if surface == "policy":
        path = Path(value)
        if path.exists():
            return _counterfactual_policy_version(path)
    return value


def _budget_delta_from_policy(record: ReplayRecord, policy: str) -> dict[str, Any]:
    cost = _recorded_step_cost_usd(record)
    cap = _budget_cap_from_policy(policy)
    if cost is None:
        return {
            "budget_cap_active": False,
            "cost_trace_changed": False,
            "original_total_usd": 0,
            "counterfactual_total_usd": 0,
            "termination_step": None,
            "termination_code": "BUDGET_SURFACE_NOT_RECORDED",
        }
    would_block = cost > cap
    return {
        "budget_cap_active": True,
        "cost_trace_changed": would_block,
        "original_total_usd": _stable_number(cost),
        "counterfactual_total_usd": _stable_number(0 if would_block else cost),
        "termination_step": 1 if would_block else None,
        "termination_code": "BUDGET_EXCEEDED" if would_block else None,
    }


def _recorded_step_cost_usd(record: ReplayRecord) -> float | None:
    metadata = _decision_metadata(record)
    cost = metadata.get("cost")
    if isinstance(cost, dict):
        value = cost.get("per_step_cost_usd")
        if isinstance(value, int | float):
            return float(value)
    event_budget = record.agent_step_event.get("budget")
    if isinstance(event_budget, dict):
        for key in ("per_step_cost_usd", "original_cumulative_usd"):
            value = event_budget.get(key)
            if isinstance(value, int | float):
                return float(value)
    return None


def _budget_cap_from_policy(policy: str) -> float:
    matches = re.findall(r"\d+(?:\.\d+)?", policy)
    if matches:
        return float(matches[-1])
    if policy in {"strict", "deny_all"}:
        return 0.0
    raise ReplayError("--substitute-budget must include a numeric cap, for example per_run_cap_usd=5000")


def _apply_budget_denial(output: dict[str, Any], budget_delta: Mapping[str, Any]) -> None:
    original = _require_object(output.get("original"), "original")
    counterfactual = _require_object(output.get("counterfactual"), "counterfactual")
    diff = _require_object(output.get("diff"), "diff")
    counterfactual["decision"] = "deny"
    counterfactual["rationale"] = "counterfactual budget policy would block the recorded step"
    counterfactual["matched_rules"] = ["deny_budget_substitution"]
    counterfactual["decision_code"] = _require_string(budget_delta.get("termination_code"), "termination_code")

    original_rules = set(_string_list(original.get("matched_rules"), "original.matched_rules"))
    counterfactual_rules = set(_string_list(counterfactual.get("matched_rules"), "counterfactual.matched_rules"))
    diff["decision_changed"] = original.get("decision") != counterfactual.get("decision")
    diff["rationale_changed"] = original.get("rationale") != counterfactual.get("rationale")
    diff["rule_set_delta"] = {
        "added": sorted(counterfactual_rules - original_rules),
        "removed": sorted(original_rules - counterfactual_rules),
        "unchanged": sorted(original_rules & counterfactual_rules),
    }


def _model_delta_from_substitution(record: ReplayRecord, substitution: str) -> dict[str, Any]:
    provider, model_version = _parse_model_substitution(substitution)
    return {
        "original_provider": record.model_provider,
        "original_model_version": record.resolved_model_version,
        "substituted_provider": provider,
        "substituted_model_version": model_version,
        "counterfactual_label": "counterfactual estimate",
    }


def _parse_model_substitution(substitution: str) -> tuple[str, str]:
    provider, separator, model_version = substitution.partition(":")
    if not separator or not provider or not model_version:
        raise ReplayError("--substitute-model must use provider:model_version")
    return provider, model_version


def _cache_delta_from_policy(record: ReplayRecord, policy: str) -> tuple[dict[str, Any], str]:
    metadata = _decision_metadata(record)
    cache = metadata.get("cache")
    if not isinstance(cache, dict):
        return (
            {
                "cache_policy": policy,
                "would_reject_cached_hit": False,
                "fresh_call_required": False,
                "rejection_reason": "cache surface not recorded",
            },
            "deterministic",
        )

    if policy.startswith("embedding_version"):
        _, _, requested_version = policy.partition("=")
        requested_version = requested_version.strip()
        if not requested_version:
            raise ReplayError("embedding_version cache policy must use embedding_version=<version>")
        current_version = cache.get("embedding_model_version")
        rejects = isinstance(current_version, str) and current_version != requested_version
        return (
            {
                "cache_policy": policy,
                "would_reject_cached_hit": rejects,
                "fresh_call_required": rejects,
                "rejection_reason": "embedding model version differs" if rejects else None,
            },
            "evaluative" if rejects else "deterministic",
        )

    if policy not in {"staleness", "strict_staleness"}:
        raise ReplayError("--substitute-cache-policy must be staleness, strict_staleness, or embedding_version=<v>")
    stale = bool(cache.get("staleness_flag"))
    return (
        {
            "cache_policy": policy,
            "would_reject_cached_hit": stale,
            "fresh_call_required": stale,
            "rejection_reason": "cached response marked stale" if stale else None,
        },
        "deterministic",
    )


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
