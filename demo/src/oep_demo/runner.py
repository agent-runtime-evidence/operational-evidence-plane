"""Deterministic code-review demo that materializes replay state in SQLite."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from oep_demo.paths import (
    EVAL_PATH,
    EVENT_PATH,
    FIXTURE_PATH,
    MANIFEST_PATH,
    PERMISSION_PATH,
    STATE_PATH,
    TRACE_PATH,
)


@dataclass(frozen=True)
class DemoResult:
    """Summary of generated local demo state."""

    state_path: Path
    event_id: str
    trace_id: str
    finding_count: int


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def stable_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def deterministic_review(diff_text: str) -> list[dict[str, Any]]:
    """Return deterministic findings for the synthetic code-review fixture."""

    findings: list[dict[str, Any]] = []
    for index, line in enumerate(diff_text.splitlines(), start=1):
        if line.startswith("+") and "return None" in line:
            findings.append(
                {
                    "finding_id": f"finding_return_none_line_{index:04d}",
                    "severity": "warning",
                    "path": "review_target.py",
                    "line": index,
                    "message": (
                        "Return an explicit error object instead of None so callers can distinguish "
                        "denial from missing data."
                    ),
                }
            )
    return findings


def connect_state(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE artifacts (
            kind TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            path TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (kind, artifact_id)
        );

        CREATE TABLE traces (
            trace_id TEXT PRIMARY KEY,
            release_manifest_id TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            UNIQUE (trace_id, release_manifest_id)
        );

        CREATE TABLE events (
            event_id TEXT PRIMARY KEY,
            trace_id TEXT NOT NULL,
            span_id TEXT NOT NULL,
            release_manifest_id TEXT NOT NULL,
            tool_call_id TEXT NOT NULL,
            permission_packet_ref TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            UNIQUE (trace_id, event_id),
            UNIQUE (event_id, tool_call_id, trace_id, span_id),
            FOREIGN KEY (trace_id, release_manifest_id)
                REFERENCES traces (trace_id, release_manifest_id)
                ON DELETE CASCADE
        );

        CREATE TABLE permissions (
            packet_id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            tool_call_id TEXT NOT NULL,
            trace_id TEXT NOT NULL,
            span_id TEXT NOT NULL,
            allow INTEGER NOT NULL,
            reason TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            FOREIGN KEY (event_id, tool_call_id, trace_id, span_id)
                REFERENCES events (event_id, tool_call_id, trace_id, span_id)
                ON DELETE CASCADE
        );

        CREATE TABLE evals (
            eval_id TEXT PRIMARY KEY,
            trace_id TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            FOREIGN KEY (trace_id)
                REFERENCES traces (trace_id)
                ON DELETE CASCADE
        );

        CREATE TABLE findings (
            finding_id TEXT PRIMARY KEY,
            trace_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            severity TEXT NOT NULL,
            path TEXT NOT NULL,
            line INTEGER NOT NULL,
            message TEXT NOT NULL,
            FOREIGN KEY (trace_id, event_id)
                REFERENCES events (trace_id, event_id)
                ON DELETE CASCADE
        );

        CREATE INDEX idx_events_trace_id ON events (trace_id);
        CREATE INDEX idx_permissions_event_id ON permissions (event_id);
        CREATE INDEX idx_permissions_trace_id ON permissions (trace_id);
        CREATE INDEX idx_evals_trace_id ON evals (trace_id);
        CREATE INDEX idx_findings_trace_event ON findings (trace_id, event_id);
        """
    )


def insert_artifact(
    connection: sqlite3.Connection,
    *,
    kind: str,
    artifact_id: str,
    path: Path,
    payload: dict[str, Any],
) -> None:
    connection.execute(
        "INSERT INTO artifacts (kind, artifact_id, path, payload_json) VALUES (?, ?, ?, ?)",
        (kind, artifact_id, path.as_posix(), stable_json(payload)),
    )


def run_demo(state_path: Path = STATE_PATH) -> DemoResult:
    manifest = load_json(MANIFEST_PATH)
    event = load_json(EVENT_PATH)
    permission = load_json(PERMISSION_PATH)
    trace = load_json(TRACE_PATH)
    eval_result = load_json(EVAL_PATH)
    diff_text = FIXTURE_PATH.read_text(encoding="utf-8")

    if not permission["decision"]["allow"]:
        raise RuntimeError("deterministic demo expects the local read_diff permission to be allowed")

    findings = deterministic_review(diff_text)
    connection = connect_state(state_path)
    try:
        create_schema(connection)

        insert_artifact(
            connection,
            kind="release_manifest",
            artifact_id=manifest["manifest_id"],
            path=MANIFEST_PATH,
            payload=manifest,
        )
        insert_artifact(
            connection,
            kind="agent_step_event",
            artifact_id=event["event_id"],
            path=EVENT_PATH,
            payload=event,
        )
        insert_artifact(
            connection,
            kind="tool_permission_packet",
            artifact_id=permission["packet_id"],
            path=PERMISSION_PATH,
            payload=permission,
        )
        insert_artifact(
            connection,
            kind="operational_trace",
            artifact_id=trace["trace_id"],
            path=TRACE_PATH,
            payload=trace,
        )
        insert_artifact(
            connection,
            kind="eval_result",
            artifact_id=eval_result["eval_id"],
            path=EVAL_PATH,
            payload=eval_result,
        )

        connection.execute(
            "INSERT INTO traces (trace_id, release_manifest_id, status, payload_json) VALUES (?, ?, ?, ?)",
            (
                trace["trace_id"],
                trace["release_manifest_id"],
                trace["status"],
                stable_json(trace),
            ),
        )
        connection.execute(
            """
            INSERT INTO events (
                event_id,
                trace_id,
                span_id,
                release_manifest_id,
                tool_call_id,
                permission_packet_ref,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                event["trace_id"],
                event["span_id"],
                event["release_manifest_id"],
                event["tool_call_id"],
                event["permission_packet_ref"],
                stable_json(event),
            ),
        )
        connection.execute(
            """
            INSERT INTO permissions (
                packet_id,
                event_id,
                tool_call_id,
                trace_id,
                span_id,
                allow,
                reason,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                permission["packet_id"],
                permission["event_id"],
                permission["tool_call_id"],
                permission["trace_id"],
                permission["span_id"],
                int(permission["decision"]["allow"]),
                permission["decision"]["reason"],
                stable_json(permission),
            ),
        )
        connection.execute(
            "INSERT INTO evals (eval_id, trace_id, status, payload_json) VALUES (?, ?, ?, ?)",
            (
                eval_result["eval_id"],
                eval_result["trace_id"],
                eval_result["status"],
                stable_json(eval_result),
            ),
        )
        connection.executemany(
            """
            INSERT INTO findings (
                finding_id,
                trace_id,
                event_id,
                severity,
                path,
                line,
                message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    finding["finding_id"],
                    event["trace_id"],
                    event["event_id"],
                    finding["severity"],
                    finding["path"],
                    finding["line"],
                    finding["message"],
                )
                for finding in findings
            ],
        )
        connection.commit()
    finally:
        connection.close()

    return DemoResult(
        state_path=state_path,
        event_id=event["event_id"],
        trace_id=event["trace_id"],
        finding_count=len(findings),
    )


__all__ = ["DemoResult", "deterministic_review", "run_demo"]
