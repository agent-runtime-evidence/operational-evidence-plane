"""SQLite reconstruction of recorded decisions: joins, batching, read-only access."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import oep_permissions.replay as replay_module
import pytest
from helpers import (
    DECISION_ID,
    ROOT,
    _sqlite_payload,
    _sqlite_row_count,
    _sqlite_update_payload,
    _sqlite_update_raw_payload,
)
from oep_demo import run_demo
from oep_demo.counterfactual import (
    run_compound_reliability_counterfactual,
)
from oep_permissions import (
    ReplayError,
)


def test_reconstruct_decision_reads_read_only_sqlite_state(state_path: Path) -> None:
    state_path.chmod(0o444)
    try:
        record = replay_module.reconstruct_decision(state_path, DECISION_ID)
    finally:
        state_path.chmod(0o644)

    assert record.decision_id == DECISION_ID
    assert record.tool_call_id == "tool_read_diff_0001"


def test_replay_state_connection_is_sqlite_read_only(tmp_path: Path) -> None:
    state_path = tmp_path / "state with space.sqlite"
    run_demo(state_path)

    connection = replay_module._connect_read_only_state(state_path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("CREATE TABLE should_not_write (id TEXT)")
    finally:
        connection.close()


def test_reconstruct_decisions_preserves_requested_order_and_duplicates(state_path: Path) -> None:
    records = replay_module.reconstruct_decisions(state_path, [DECISION_ID, DECISION_ID])

    assert [record.decision_id for record in records] == [DECISION_ID, DECISION_ID]
    assert [record.tool_call_id for record in records] == ["tool_read_diff_0001", "tool_read_diff_0001"]
    assert replay_module.reconstruct_decisions(state_path, []) == []
    connection = sqlite3.connect(state_path)
    try:
        connection_records = replay_module.reconstruct_decisions(connection, [DECISION_ID])
        assert [record.decision_id for record in connection_records] == [DECISION_ID]
        assert connection.row_factory is None
        assert connection.execute("SELECT 1").fetchone() == (1,)
    finally:
        connection.close()
    assert (
        replay_module.counterfactual_replay_decisions(
            state_path,
            [],
            ROOT / "permissions" / "policy" / "tool_permissions.rego",
        )
        == []
    )


def test_reconstruct_decision_reports_sqlite_operational_errors(tmp_path: Path) -> None:
    state_path = tmp_path / "empty.sqlite"
    sqlite3.connect(state_path).close()

    with pytest.raises(ReplayError, match="database operational error during replay reconstruction"):
        replay_module.reconstruct_decision(state_path, DECISION_ID)

    with pytest.raises(replay_module.StateNotFoundError, match="replay state not found"):
        replay_module.reconstruct_decision(tmp_path / "missing.sqlite", DECISION_ID)


def test_reconstruct_decision_rejects_corrupt_joined_payloads(tmp_path: Path) -> None:
    bad_event_state_path = tmp_path / "bad_event.sqlite"
    run_demo(bad_event_state_path)
    bad_event = _sqlite_payload(
        bad_event_state_path,
        "SELECT payload_json FROM events WHERE event_id = ?",
        ("evt_code_review_agent_step_0001",),
    )
    bad_event["replay_handle"] = "not-an-object"
    _sqlite_update_payload(
        bad_event_state_path,
        "UPDATE events SET payload_json = ? WHERE event_id = ?",
        bad_event,
        ("evt_code_review_agent_step_0001",),
    )
    with pytest.raises(ReplayError, match="event.replay_handle must be an object"):
        replay_module.reconstruct_decision(bad_event_state_path, DECISION_ID)

    bad_permission_state_path = tmp_path / "bad_permission.sqlite"
    run_demo(bad_permission_state_path)
    _sqlite_update_raw_payload(
        bad_permission_state_path,
        "UPDATE permissions SET payload_json = ? WHERE packet_id = ?",
        "[]",
        (DECISION_ID,),
    )
    with pytest.raises(ReplayError, match="permission payload must decode to a JSON object"):
        replay_module.reconstruct_decision(bad_permission_state_path, DECISION_ID)

    bad_join_state_path = tmp_path / "bad_join.sqlite"
    run_demo(bad_join_state_path)
    bad_packet = _sqlite_payload(
        bad_join_state_path,
        "SELECT payload_json FROM permissions WHERE packet_id = ?",
        (DECISION_ID,),
    )
    bad_packet["event_id"] = "evt_code_review_agent_step_mismatch"
    _sqlite_update_payload(
        bad_join_state_path,
        "UPDATE permissions SET payload_json = ? WHERE packet_id = ?",
        bad_packet,
        (DECISION_ID,),
    )
    with pytest.raises(ReplayError, match="inconsistent joined field"):
        replay_module.reconstruct_decision(bad_join_state_path, DECISION_ID)

    schema_drift_state_path = tmp_path / "schema_drift.sqlite"
    run_demo(schema_drift_state_path)
    schema_drift_packet = _sqlite_payload(
        schema_drift_state_path,
        "SELECT payload_json FROM permissions WHERE packet_id = ?",
        (DECISION_ID,),
    )
    schema_drift_packet["unexpected_extra_field"] = True
    _sqlite_update_payload(
        schema_drift_state_path,
        "UPDATE permissions SET payload_json = ? WHERE packet_id = ?",
        schema_drift_packet,
        (DECISION_ID,),
    )
    with pytest.raises(ReplayError, match="failed schema validation"):
        replay_module.reconstruct_decision(schema_drift_state_path, DECISION_ID)
    assert (
        replay_module.reconstruct_decision(
            schema_drift_state_path,
            DECISION_ID,
            validate_schema=False,
        ).decision_id
        == DECISION_ID
    )

    missing_manifest_state_path = tmp_path / "missing_manifest.sqlite"
    run_demo(missing_manifest_state_path)
    connection = sqlite3.connect(missing_manifest_state_path)
    try:
        connection.execute("DELETE FROM artifacts WHERE kind = ?", ("release_manifest",))
        connection.commit()
    finally:
        connection.close()
    record = replay_module.reconstruct_decision(missing_manifest_state_path, DECISION_ID)
    assert record.release_manifest_summary is None


def test_read_only_state_uses_file_uri_with_percent_encoding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "state with space.sqlite"
    state_path.write_bytes(b"")
    real_connect = sqlite3.connect
    calls: list[tuple[object, dict[str, Any]]] = []

    def connect(database: object, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        calls.append((database, kwargs))
        return real_connect(":memory:")

    monkeypatch.setattr("oep_permissions.replay.sqlite3.connect", connect)

    connect_read_only_state = cast(
        Callable[[Path], sqlite3.Connection],
        vars(replay_module)["_connect_read_only_state"],
    )
    connection = connect_read_only_state(state_path)
    try:
        assert calls[0][1]["uri"] is True
        assert calls[0][1]["timeout"] == 10.0
        assert isinstance(calls[0][0], str)
        assert calls[0][0].startswith("file:///")
        assert calls[0][0].endswith("?mode=ro")
        assert "state%20with%20space.sqlite" in calls[0][0]
        assert len(calls) == 1
    finally:
        connection.close()


def test_decision_id_batch_parameters_use_fixed_placeholder_buckets(monkeypatch: pytest.MonkeyPatch) -> None:
    padded_parameters = cast(
        Callable[[list[str]], tuple[str | None, ...]],
        vars(replay_module)["_padded_decision_id_parameters"],
    )
    placeholders = cast(
        Callable[[int], str],
        vars(replay_module)["_decision_id_placeholders"],
    )

    assert padded_parameters(["a", "b", "c"]) == ("a", "b", "c", None)
    assert placeholders(3) == "?,?,?,?"
    assert len(padded_parameters([str(index) for index in range(513)])) == 900

    monkeypatch.setenv(replay_module.OEP_SQLITE_BATCH_VARIABLE_LIMIT_ENV, "1024")
    assert len(padded_parameters([str(index) for index in range(513)])) == 1024

    monkeypatch.setenv(replay_module.OEP_SQLITE_BATCH_VARIABLE_LIMIT_ENV, "0")
    with pytest.raises(ReplayError, match=replay_module.OEP_SQLITE_BATCH_VARIABLE_LIMIT_ENV):
        placeholders(1)


def test_batch_reconstruction_caches_trace_and_manifest_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = run_compound_reliability_counterfactual(tmp_path / "compound")
    real_loads_object = cast(
        Callable[[object, str], dict[str, Any]],
        vars(replay_module)["_loads_object"],
    )
    load_counts: dict[str, int] = {}

    def counting_loads_object(text: object, field: str) -> dict[str, Any]:
        load_counts[field] = load_counts.get(field, 0) + 1
        return real_loads_object(text, field)

    monkeypatch.setattr("oep_permissions.replay.storage._loads_object", counting_loads_object)
    records = replay_module.reconstruct_decisions(
        result.state_path,
        [
            f"pder_code_review_compound_reliability_step_{index:04d}"
            for index in range(1, result.total_steps + 1)
        ],
    )

    assert len(records) == result.total_steps
    assert load_counts["permission payload"] == result.total_steps
    assert load_counts["event payload"] == result.total_steps
    assert load_counts["trace payload"] == 1
    assert load_counts["manifest payload"] == 1


def test_sqlite_row_count_rejects_unknown_table(state_path: Path) -> None:
    connection = sqlite3.connect(state_path)
    try:
        with pytest.raises(ValueError, match="invalid replay-state table"):
            _sqlite_row_count(connection, "events; DROP TABLE events")
    finally:
        connection.close()
