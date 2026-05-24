"""Check deterministic eval result against trace, event, permission, and generated state."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from oep_traces.paths import EXPECTED_EVAL_SCHEMA_TITLE

from oep_verify.verify_support import (
    load_json_object,
    path_from_env,
    relative_path,
    require,
    require_json_list,
    require_json_object,
    scalar,
    validate_json_schema,
)

ROOT = Path(__file__).resolve().parents[2]

EVAL_SCHEMA_PATH = ROOT / "traces" / "schema" / "eval_result.v0.schema.json"
EVAL_EXAMPLE_PATH = ROOT / "traces" / "examples" / "code_review_agent_eval.v0.json"
TRACE_EXAMPLE_PATH = ROOT / "traces" / "examples" / "code_review_agent_trace.v0.json"
EVENT_EXAMPLE_PATH = ROOT / "events" / "examples" / "code_review_agent_step.v0.json"
PERMISSION_EXAMPLE_PATH = ROOT / "permissions" / "examples" / "code_review_tool_permission.v0.json"
FIXTURE_PATH = ROOT / "demo" / "fixtures" / "diff_synthetic_001.patch"
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
    schema = load_json_object(EVAL_SCHEMA_PATH)
    eval_result = load_json_object(EVAL_EXAMPLE_PATH)
    validate_json_schema(schema, eval_result, instance_path=EVAL_EXAMPLE_PATH)
    trace = load_json_object(TRACE_EXAMPLE_PATH)
    event = load_json_object(EVENT_EXAMPLE_PATH)
    permission = load_json_object(PERMISSION_EXAMPLE_PATH)

    require(schema.get("title") == EXPECTED_EVAL_SCHEMA_TITLE, "bad schema")
    require(eval_result.get("schema_version") == "oep.eval_result.v0", "bad eval schema_version")
    require(eval_result.get("status") == "passed", "eval should be passed")
    require(eval_result.get("release_manifest_id") == trace.get("release_manifest_id"), "manifest mismatch")
    require(eval_result.get("trace_id") == trace.get("trace_id"), "trace_id mismatch")

    input_refs = require_json_object(eval_result.get("input_refs"), "input_refs must be an object")
    require(input_refs.get("trace_ref") == rel(TRACE_EXAMPLE_PATH), "trace_ref mismatch")
    require(input_refs.get("event_ref") == rel(EVENT_EXAMPLE_PATH), "event_ref mismatch")
    require(input_refs.get("permission_packet_ref") == rel(PERMISSION_EXAMPLE_PATH), "permission ref mismatch")
    require(input_refs.get("fixture_ref") == rel(FIXTURE_PATH), "fixture ref mismatch")

    metrics = require_json_object(eval_result.get("metrics"), "metrics must be an object")
    require(metrics.get("expected_findings") == 1, "expected_findings mismatch")
    require(metrics.get("actual_findings") == 1, "actual_findings mismatch")
    require(metrics.get("allowed_permission_packets") == 1, "allowed permission count mismatch")
    require(metrics.get("blocking_evidence_loss_count") == 0, "blocking evidence loss mismatch")

    checks = require_json_list(eval_result.get("checks"), "checks must be a list")
    require(len(checks) > 0, "checks must be a non-empty list")
    require(
        all(isinstance(check, dict) and check.get("status") == "passed" for check in checks),
        "all checks must pass",
    )

    require(permission["decision"]["allow"] is True, "permission decision must allow")
    blocking_loss = [
        item
        for item in require_json_list(event.get("evidence_loss"), "event evidence_loss must be a list")
        + require_json_list(trace.get("evidence_loss"), "trace evidence_loss must be a list")
        if isinstance(item, dict) and item.get("severity") == "blocking"
    ]
    require(len(blocking_loss) == 0, "blocking evidence loss remains")
    require(DEMO_STATE_PATH.exists(), "generated demo SQLite state is required for eval validation")

    with closing(read_only_state_connection()) as connection:
        finding_count = scalar(
            connection,
            "SELECT COUNT(*) FROM findings WHERE trace_id = ? AND event_id = ?",
            (trace["trace_id"], event["event_id"]),
        )
        require(finding_count == metrics["actual_findings"], "SQLite finding count mismatch")

        allowed_packets = scalar(
            connection,
            "SELECT COUNT(*) FROM permissions WHERE event_id = ? AND allow = 1",
            (event["event_id"],),
        )
        require(allowed_packets == metrics["allowed_permission_packets"], "SQLite permission count mismatch")

        eval_count = scalar(
            connection,
            "SELECT COUNT(*) FROM evals WHERE eval_id = ? AND status = ?",
            (eval_result["eval_id"], eval_result["status"]),
        )
        require(eval_count == 1, "SQLite eval row mismatch")

    print("Eval result checks passed")


if __name__ == "__main__":
    main()
