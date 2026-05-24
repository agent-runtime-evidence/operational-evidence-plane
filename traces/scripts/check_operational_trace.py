"""Check the stitched trace bundle against manifest, event, permission, and eval files."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from oep_traces.paths import EXPECTED_SCHEMA_TITLE

from oep_verify.verify_support import (
    load_json_object,
    path_from_env,
    relative_path,
    require,
    require_datetime_not_after,
    require_json_list,
    require_json_object,
    require_resolved_layer_bindings,
    validate_json_schema,
)

ROOT = Path(__file__).resolve().parents[2]

TRACE_SCHEMA_PATH = ROOT / "traces" / "schema" / "operational_trace.v0.schema.json"
TRACE_EXAMPLE_PATH = ROOT / "traces" / "examples" / "code_review_agent_trace.v0.json"
EVAL_EXAMPLE_PATH = ROOT / "traces" / "examples" / "code_review_agent_eval.v0.json"
EVENT_EXAMPLE_PATH = ROOT / "events" / "examples" / "code_review_agent_step.v0.json"
PERMISSION_EXAMPLE_PATH = ROOT / "permissions" / "examples" / "code_review_tool_permission.v0.json"
MANIFEST_EXAMPLE_PATH = ROOT / "manifest" / "examples" / "code_review_agent_release.v0.json"
DEMO_STATE_PATH = path_from_env(
    ROOT,
    "OEP_DEMO_STATE_PATH",
    ROOT / "demo" / "state" / "code_review_agent.sqlite",
)


def rel(path: Path) -> str:
    return relative_path(ROOT, path)


def read_only_state_connection() -> sqlite3.Connection:
    state_uri = f"{DEMO_STATE_PATH.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(state_uri, uri=True)


def main() -> None:
    schema = load_json_object(TRACE_SCHEMA_PATH)
    trace = load_json_object(TRACE_EXAMPLE_PATH)
    validate_json_schema(schema, trace, instance_path=TRACE_EXAMPLE_PATH)
    eval_result = load_json_object(EVAL_EXAMPLE_PATH)
    event = load_json_object(EVENT_EXAMPLE_PATH)
    permission = load_json_object(PERMISSION_EXAMPLE_PATH)
    manifest = load_json_object(MANIFEST_EXAMPLE_PATH)

    require(schema.get("title") == EXPECTED_SCHEMA_TITLE, "bad schema")
    require(trace.get("schema_version") == "oep.operational_trace.v0", "bad trace schema_version")
    require(trace.get("release_manifest_id") == manifest.get("manifest_id"), "manifest join mismatch")
    if trace.get("status") == "replay_ready":
        require_resolved_layer_bindings(manifest, "replay-ready trace")
    require(trace.get("release_manifest_id") == event.get("release_manifest_id"), "event manifest mismatch")
    require(trace.get("release_manifest_id") == permission.get("release_manifest_id"), "permission manifest mismatch")
    require(trace.get("trace_id") == event.get("trace_id"), "event trace_id mismatch")
    require(trace.get("trace_id") == permission.get("trace_id"), "permission trace_id mismatch")
    require(trace.get("trace_id") == eval_result.get("trace_id"), "eval trace_id mismatch")
    require_datetime_not_after(trace.get("started_at"), trace.get("ended_at"), "trace.started_at", "trace.ended_at")
    require_datetime_not_after(trace.get("started_at"), event.get("event_time"), "trace.started_at", "event.event_time")
    require_datetime_not_after(event.get("event_time"), trace.get("ended_at"), "event.event_time", "trace.ended_at")
    require_datetime_not_after(
        trace.get("started_at"),
        permission.get("decision_time"),
        "trace.started_at",
        "permission.decision_time",
    )
    require_datetime_not_after(
        permission.get("decision_time"),
        trace.get("ended_at"),
        "permission.decision_time",
        "trace.ended_at",
    )

    joins = require_json_object(trace.get("joins"), "joins must be an object")
    require(joins.get("release_manifest_ref") == rel(MANIFEST_EXAMPLE_PATH), "manifest ref mismatch")
    require(joins.get("event_refs") == [rel(EVENT_EXAMPLE_PATH)], "event refs mismatch")
    require(joins.get("permission_packet_refs") == [rel(PERMISSION_EXAMPLE_PATH)], "permission refs mismatch")

    spans = require_json_list(trace.get("spans"), "spans must be a list")
    require(len(spans) == 1, "expected one span")
    span = spans[0]
    span = require_json_object(span, "span must be an object")
    require(span.get("span_id") == event.get("span_id"), "span_id mismatch")
    require(span.get("span_id") == permission.get("span_id"), "permission span_id mismatch")
    require(span.get("event_ref") == rel(EVENT_EXAMPLE_PATH), "span event_ref mismatch")
    require(span.get("permission_packet_ref") == rel(PERMISSION_EXAMPLE_PATH), "span permission ref mismatch")
    require(span.get("tool_call_id") == event.get("tool_call_id"), "tool_call_id mismatch")
    require(span.get("tool_call_id") == permission.get("tool_call_id"), "permission tool_call_id mismatch")
    require(span.get("checkpoint") == event.get("checkpoint"), "checkpoint mismatch")

    replay = require_json_object(trace.get("replay"), "trace replay must be an object")
    event_replay = require_json_object(event.get("replay_handle"), "event replay_handle must be an object")
    require(replay.get("handle") == event_replay.get("id"), "replay handle mismatch")
    require(replay.get("state_ref") == event_replay.get("state_ref"), "replay state_ref mismatch")
    require(replay.get("deterministic") == event_replay.get("deterministic"), "replay deterministic mismatch")
    require(replay.get("status") == "ready", "trace replay should be ready after demo state generation")
    require(DEMO_STATE_PATH.exists(), "generated demo SQLite state is required for ready replay")
    with closing(read_only_state_connection()) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_id = ? AND trace_id = ?",
            (event["event_id"], trace["trace_id"]),
        ).fetchone()
        require(row is not None and row[0] == 1, "ready replay state missing event row")

    eval_ref = require_json_object(trace.get("eval"), "trace eval must be an object")
    require(eval_ref.get("eval_id") == eval_result.get("eval_id"), "eval_id mismatch")
    require(eval_ref.get("eval_ref") == rel(EVAL_EXAMPLE_PATH), "eval_ref mismatch")
    require(eval_ref.get("status") == eval_result.get("status"), "eval status mismatch")
    require(eval_ref.get("status") == "passed", "trace eval should be passed")
    require(eval_result.get("release_manifest_id") == manifest.get("manifest_id"), "eval manifest mismatch")

    event_links = require_json_object(event.get("links"), "event links must be an object")
    permission_links = require_json_object(permission.get("links"), "permission links must be an object")
    require(event_links.get("trace_ref") == rel(TRACE_EXAMPLE_PATH), "event trace_ref mismatch")
    require(event_links.get("eval_ref") == rel(EVAL_EXAMPLE_PATH), "event eval_ref mismatch")
    require(permission_links.get("trace_ref") == rel(TRACE_EXAMPLE_PATH), "permission trace_ref mismatch")

    evidence_loss = require_json_list(trace.get("evidence_loss"), "trace evidence_loss must be a list")
    require(
        not any(isinstance(item, dict) and item.get("field") == "replay.state_ref" for item in evidence_loss),
        "ready replay must not carry replay evidence-loss note",
    )
    require(
        not any(isinstance(item, dict) and item.get("field") == "eval.status" for item in evidence_loss),
        "passed eval must not carry eval evidence-loss note",
    )

    print("Trace bundle checks passed")


if __name__ == "__main__":
    main()
