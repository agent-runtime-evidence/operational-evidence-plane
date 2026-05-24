#!/usr/bin/env python3
"""Convert OEP example artefacts to a JSONL stream consumable by the
Decision Trace Reconstructor `generic-jsonl` adapter.

The Operational Evidence Plane ships its example artefacts as individual
JSON files (release manifest, agent-step event, OPA-backed tool permission
packet, operational trace bundle, deterministic eval result). The Decision
Trace Reconstructor `generic-jsonl` adapter consumes a single JSONL stream
where each line is one record carrying a `kind` field that the mapping
config (`mapping.v0.yaml`, shipped alongside this script) translates to a
DTR fragment kind.

Output JSONL records are sorted by timestamp, kind, and id so the
reconstructor's temporal-ordering stage receives deterministic input
even when records share the same timestamp.

Usage:
    python integrations/decision-trace-reconstructor/scripts/to_dtr_jsonl.py \\
        --scenario code_review_agent \\
        --out integrations/decision-trace-reconstructor/code_review_agent.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from oep_verify.scenarios import get_scenario, scenario_names

REPO_ROOT = Path(__file__).resolve().parents[3]
JsonRecord = dict[str, Any]


def iso_to_epoch(iso_str: str) -> float:
    """Convert an ISO 8601 timestamp string to Unix epoch seconds (UTC)."""
    parsed = datetime.fromisoformat(iso_str)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).timestamp()


def from_release_manifest(manifest: JsonRecord) -> JsonRecord:
    """Emit a config_snapshot record from an OEP release manifest."""
    return {
        "id": manifest["manifest_id"],
        "ts": iso_to_epoch(manifest["created_at"]),
        "kind": "manifest",
        "actor_id": manifest["release"].get("owner", "release-owner"),
        "tier": "within_stack",
        "release_name": manifest["release"]["name"],
        "release_version": manifest["release"]["version"],
        "layer_bindings": list(manifest["layer_bindings"].keys()),
        "scenario": manifest["release"].get("scenario", manifest["release"]["name"]),
        "schema_version": manifest["schema_version"],
    }


def from_agent_step_event(event: JsonRecord) -> tuple[JsonRecord, JsonRecord]:
    """Emit (prompt, tool_call) pair from an OEP agent-step event.

    The prompt record is synthesised at event_time minus a small offset so
    DTR's temporal ordering places it before the tool call. The tool call
    is the OEP step itself.
    """
    actor_id = event["actor"]["id"]
    step_ts = iso_to_epoch(event["event_time"])
    action = event.get("action", {})

    prompt = {
        "id": f"prompt_{event['event_id']}",
        "ts": step_ts - 0.5,
        "kind": "prompt",
        "actor_id": actor_id,
        "tier": "within_stack",
        "content": (
            f"OEP agent step: {action.get('name', action.get('action_type', 'agent_step'))}"
        ),
        "release_manifest_id": event.get("release_manifest_id"),
    }
    tool = {
        "id": event["event_id"],
        "ts": step_ts,
        "kind": "tool",
        "actor_id": actor_id,
        "tier": "within_stack",
        "tool": action.get("action_type"),
        "action_type": action.get("action_type"),
        "tool_call_id": event.get("tool_call_id"),
        "permission_packet_ref": event.get("permission_packet_ref"),
        "trace_id": event.get("trace_id"),
        "span_id": event.get("span_id"),
        "checkpoint_name": event.get("checkpoint", {}).get("name"),
        "checkpoint_sequence": event.get("checkpoint", {}).get("sequence"),
        "schema_version": event["schema_version"],
    }
    return prompt, tool


def from_permission_packet(packet: JsonRecord) -> JsonRecord:
    """Emit a policy_snapshot record from an OEP tool permission packet."""
    return {
        "id": packet["packet_id"],
        "ts": iso_to_epoch(packet["decision_time"]) - 0.1,
        "kind": "policy",
        "actor_id": packet["policy"]["engine"],
        "tier": "within_stack",
        "policy_engine": packet["policy"]["engine"],
        "policy_id": packet["policy"]["policy_id"],
        "policy_package": packet["policy"]["package"],
        "policy_uri": packet["policy"]["policy_uri"],
        "decision_allow": packet["decision"]["allow"],
        "matched_rule": packet["decision"]["matched_rule"],
        "tool_call_id": packet["tool_call_id"],
        "schema_version": packet["schema_version"],
    }


def from_replay_handle(event: JsonRecord) -> JsonRecord | None:
    """Emit a state_mutation record from the OEP event's replay_handle field."""
    handle = event["replay_handle"]
    if handle is None:
        return None
    if not isinstance(handle, dict):
        raise ValueError("event replay_handle must be an object or null")
    return {
        "id": handle["id"],
        "ts": iso_to_epoch(event["event_time"]) + 0.1,
        "kind": "state",
        "actor_id": "sqlite_replay_layer",
        "tier": "within_stack",
        "tool": "write_replay_handle",
        "replay_handle": handle["id"],
        "state_ref": handle.get("state_ref"),
        "deterministic": handle.get("deterministic", True),
        "event_id": event["event_id"],
    }


def from_eval_result(eval_result: JsonRecord, trace_bundle: JsonRecord) -> JsonRecord:
    """Emit a final agent_message record from the OEP eval result.

    Eval timestamp is derived from the trace bundle's ended_at, since the
    eval result schema does not carry a timestamp field directly.
    """
    trace_end = trace_bundle.get("ended_at") or trace_bundle.get("started_at")
    if not isinstance(trace_end, str):
        raise ValueError("trace bundle must contain ended_at or started_at timestamp")
    end_ts = iso_to_epoch(trace_end)
    return {
        "id": eval_result["eval_id"],
        "ts": end_ts + 0.5,
        "kind": "final",
        "actor_id": "eval_pipeline",
        "tier": "within_stack",
        "content": eval_result.get("summary", ""),
        "eval_status": eval_result.get("status"),
        "trace_id": eval_result.get("trace_id"),
        "schema_version": eval_result["schema_version"],
    }


def sort_jsonl_records(records: Sequence[JsonRecord]) -> list[JsonRecord]:
    """Return DTR JSONL records in deterministic temporal order."""

    return sorted(records, key=_jsonl_sort_key)


def _jsonl_sort_key(record: JsonRecord) -> tuple[float, str, str]:
    timestamp = record.get("ts")
    kind = record.get("kind")
    record_id = record.get("id")
    if not isinstance(timestamp, int | float):
        raise ValueError("DTR JSONL record must contain numeric ts")
    if not isinstance(kind, str):
        raise ValueError("DTR JSONL record must contain string kind")
    if not isinstance(record_id, str):
        raise ValueError("DTR JSONL record must contain string id")
    return (float(timestamp), kind, record_id)


def build_jsonl(scenario: str, repo_root: Path) -> list[JsonRecord]:
    """Read OEP scenario artefacts and return the sorted JSONL record list."""
    try:
        files = get_scenario(scenario).dtr_files
    except KeyError as exc:
        raise SystemExit(str(exc)) from exc

    def _load(rel: str) -> JsonRecord:
        data = json.loads((repo_root / rel).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{rel} must contain a JSON object")
        return data

    manifest = _load(files["release_manifest"])
    event = _load(files["agent_step"])
    permission = _load(files["permission"])
    trace_bundle = _load(files["trace_bundle"])
    eval_result = _load(files["eval_result"])

    prompt, tool = from_agent_step_event(event)
    records = [
        from_release_manifest(manifest),
        prompt,
        from_permission_packet(permission),
        tool,
        from_eval_result(eval_result, trace_bundle),
    ]
    replay_record = from_replay_handle(event)
    if replay_record is not None:
        records.append(replay_record)
    return sort_jsonl_records(records)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Convert OEP example artefacts to a JSONL stream consumable by "
            "the Decision Trace Reconstructor generic-jsonl adapter."
        )
    )
    parser.add_argument(
        "--scenario",
        default="code_review_agent",
        choices=scenario_names(),
        help="OEP scenario name (default: code_review_agent)",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output JSONL path (writes one record per line, sorted by timestamp)",
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="OEP repository root (default: detected from script location)",
    )
    args = parser.parse_args()

    records = build_jsonl(args.scenario, Path(args.repo_root))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True) + "\n")

    print(f"wrote {out_path} ({len(records)} records)")


if __name__ == "__main__":
    main()
