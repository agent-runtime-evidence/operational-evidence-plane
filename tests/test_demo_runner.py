"""Deterministic demo runner: schema, state backup, and replace semantics."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

import oep_demo.runner as demo_runner
import pytest
from oep_demo import deterministic_review, run_demo
from oep_demo.runner import create_schema

from oep_verify.verify_support import (
    require_datetime_not_after,
)


def test_deterministic_review_generates_unique_finding_ids() -> None:
    findings = deterministic_review("+ return None\n+ return None\n")
    assert [finding["finding_id"] for finding in findings] == [
        "finding_return_none_line_0001",
        "finding_return_none_line_0002",
    ]


def test_temporal_order_rejects_inversion() -> None:
    with pytest.raises(ValueError, match="created_at must not be after event_time"):
        require_datetime_not_after(
            "2026-05-04T00:00:02Z",
            "2026-05-04T00:00:01Z",
            "created_at",
            "event_time",
        )


def test_run_demo_replaces_existing_state_with_backup_api(tmp_path: Path) -> None:
    state_path = tmp_path / "state.sqlite"
    stale = sqlite3.connect(state_path)
    try:
        stale.execute("PRAGMA journal_mode = WAL")
        stale.execute("CREATE TABLE stale_rows (id INTEGER PRIMARY KEY)")
        stale.execute("INSERT INTO stale_rows (id) VALUES (1)")
        stale.commit()
    finally:
        stale.close()

    reader = sqlite3.connect(state_path)
    event_id = ""
    try:
        reader.execute("BEGIN")
        assert reader.execute("SELECT COUNT(*) FROM stale_rows").fetchone() == (1,)

        result = run_demo(state_path)
        assert result.state_path == state_path
        event_id = result.event_id
        assert reader.execute("SELECT COUNT(*) FROM stale_rows").fetchone() == (1,)
    finally:
        reader.close()

    with sqlite3.connect(state_path) as connection:
        stale_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("stale_rows",),
        ).fetchone()
        assert stale_table is None
        event_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        assert event_count == (1,)


def test_run_demo_retries_transient_backup_lock_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "state.sqlite"
    real_backup = demo_runner._backup_sqlite_state
    backup_calls = 0
    sleep_calls: list[float] = []

    def flaky_backup(src: Path, dst: Path) -> None:
        nonlocal backup_calls
        backup_calls += 1
        if backup_calls < 3:
            raise sqlite3.OperationalError("database is locked")
        real_backup(src, dst)

    monkeypatch.setattr("oep_demo.runner._backup_sqlite_state", flaky_backup)
    monkeypatch.setattr("oep_demo.runner.time.sleep", sleep_calls.append)

    result = run_demo(state_path)

    assert result.state_path == state_path
    assert backup_calls == 3
    assert sleep_calls == [0.05, 0.1]
    assert state_path.exists()


def test_run_demo_publishes_backup_with_atomic_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "state.sqlite"
    publish_path = tmp_path / ".state.sqlite.publish_tmp"
    real_replace = os.replace
    replace_calls: list[tuple[Path, Path]] = []

    def capture_replace(src: Path, dst: Path) -> None:
        replace_calls.append((src, dst))
        real_replace(src, dst)

    monkeypatch.setattr("oep_demo.runner.os.replace", capture_replace)

    result = run_demo(state_path)

    assert result.state_path == state_path
    assert replace_calls == [(publish_path, state_path)]
    assert state_path.exists()
    assert not publish_path.exists()
    assert not publish_path.with_name(f"{publish_path.name}-wal").exists()
    assert not publish_path.with_name(f"{publish_path.name}-shm").exists()


def test_run_demo_retries_transient_publish_replace_permission_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "state.sqlite"
    real_replace = os.replace
    replace_calls = 0
    sleep_calls: list[float] = []

    def flaky_replace(src: Path, dst: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls < 3:
            raise PermissionError("destination is locked")
        real_replace(src, dst)

    monkeypatch.setattr("oep_demo.runner.os.replace", flaky_replace)
    monkeypatch.setattr("oep_demo.runner.time.sleep", sleep_calls.append)

    result = run_demo(state_path)

    assert result.state_path == state_path
    assert replace_calls == 3
    assert sleep_calls == [0.05, 0.1]
    assert state_path.exists()


def test_checkpoint_state_uses_passive_wal_checkpoint() -> None:
    statements: list[str] = []
    connection = sqlite3.connect(":memory:")
    try:
        connection.set_trace_callback(statements.append)
        demo_runner.checkpoint_state(connection)
    finally:
        connection.close()

    assert any("PRAGMA wal_checkpoint(PASSIVE)" in statement for statement in statements)


def test_connect_state_rejects_existing_state(tmp_path: Path) -> None:
    state_path = tmp_path / "state.sqlite"
    state_path.write_bytes(b"placeholder")

    with pytest.raises(RuntimeError, match="refusing to reset existing SQLite state in place"):
        demo_runner.connect_state(state_path)


def test_connect_state_reports_missing_sqlite_json_support(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class JsonlessConnection:
        def execute(self, sql: str, parameters: object = ()) -> object:
            if "json_valid" in sql:
                raise sqlite3.OperationalError("no such function: json_valid")
            return self

        def close(self) -> None:
            return None

    def connect(*args: Any, **kwargs: Any) -> JsonlessConnection:
        return JsonlessConnection()

    monkeypatch.setattr("oep_demo.runner.sqlite3.connect", connect)

    with pytest.raises(RuntimeError, match="SQLite JSON functions are required"):
        demo_runner.connect_state(tmp_path / "state.sqlite")


def test_replay_schema_enforces_foreign_keys(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "state.sqlite")
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        create_schema(connection)
        index_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_%'"
            ).fetchall()
        }
        assert "idx_events_trace_id" not in index_names
        assert "idx_permissions_fk" not in index_names
        assert "idx_events_trace_manifest" in index_names
        assert "idx_permissions_event_id" in index_names
        assert "idx_findings_event_trace" in index_names

        event_unique_indexes = [row for row in connection.execute("PRAGMA index_list('events')").fetchall() if row[2]]
        assert len(event_unique_indexes) == 1

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO artifacts (kind, artifact_id, path, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                ("release_manifest", "rmf_invalid_json", "manifest.json", "{not-json"),
            )

        with pytest.raises(sqlite3.IntegrityError):
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
                    "evt_missing_trace",
                    "11111111111111111111111111111111",
                    "2222222222222222",
                    "rmf_code_review_agent_2026_05_04_v0",
                    "tool_read_diff_0001",
                    "pder_code_review_read_diff_0001",
                    "{}",
                ),
            )

        with pytest.raises(sqlite3.IntegrityError):
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
                    "pder_missing_event",
                    "evt_missing_event",
                    "tool_read_diff_0001",
                    "11111111111111111111111111111111",
                    "2222222222222222",
                    1,
                    "missing event",
                    "{}",
                ),
            )
    finally:
        connection.close()
