"""Validate generated SQLite replay state for the deterministic demo."""

from __future__ import annotations

import sqlite3
from contextlib import closing

from oep_demo.paths import EVAL_PATH, EVENT_PATH, PERMISSION_PATH, STATE_PATH, TRACE_PATH

from oep_verify.verify_support import load_json_object, require, scalar


def read_only_state_connection() -> sqlite3.Connection:
    state_uri = f"{STATE_PATH.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(state_uri, uri=True)


def main() -> None:
    event = load_json_object(EVENT_PATH)
    permission = load_json_object(PERMISSION_PATH)
    trace = load_json_object(TRACE_PATH)
    eval_result = load_json_object(EVAL_PATH)

    require(STATE_PATH.exists(), f"missing generated demo state: {STATE_PATH}")

    with closing(read_only_state_connection()) as connection:
        event_count = scalar(
            connection,
            "SELECT COUNT(*) FROM events WHERE event_id = ? AND trace_id = ?",
            (event["event_id"], event["trace_id"]),
        )
        require(event_count == 1, "event row missing from replay state")

        packet_count = scalar(
            connection,
            "SELECT COUNT(*) FROM permissions WHERE packet_id = ? AND event_id = ? AND allow = 1",
            (permission["packet_id"], event["event_id"]),
        )
        require(packet_count == 1, "permission row missing from replay state")

        trace_count = scalar(
            connection,
            "SELECT COUNT(*) FROM traces WHERE trace_id = ? AND release_manifest_id = ?",
            (trace["trace_id"], trace["release_manifest_id"]),
        )
        require(trace_count == 1, "trace row missing from replay state")

        finding_count = scalar(
            connection,
            "SELECT COUNT(*) FROM findings WHERE trace_id = ? AND event_id = ?",
            (trace["trace_id"], event["event_id"]),
        )
        require(finding_count == 1, "expected exactly one deterministic finding")

        eval_count = scalar(
            connection,
            "SELECT COUNT(*) FROM evals WHERE eval_id = ? AND trace_id = ? AND status = 'passed'",
            (eval_result["eval_id"], trace["trace_id"]),
        )
        require(eval_count == 1, "passed eval row missing from replay state")

        permission_event_index_columns = [
            row[2] for row in connection.execute("PRAGMA index_info('idx_permissions_event_id')").fetchall()
        ]
        require(
            permission_event_index_columns == ["event_id"],
            "permissions event-id index missing or malformed",
        )

        event_permission_ref_index_columns = [
            row[2] for row in connection.execute("PRAGMA index_info('idx_events_permission_packet_ref')").fetchall()
        ]
        require(
            event_permission_ref_index_columns == ["permission_packet_ref"],
            "event permission-packet-ref index missing or malformed",
        )

        event_trace_manifest_index_columns = [
            row[2] for row in connection.execute("PRAGMA index_info('idx_events_trace_manifest')").fetchall()
        ]
        require(
            event_trace_manifest_index_columns == ["trace_id", "release_manifest_id"],
            "event trace-manifest index missing or malformed",
        )

    print("Demo replay state checks passed")


if __name__ == "__main__":
    main()
