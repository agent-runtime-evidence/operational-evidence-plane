"""Shared constants and helpers for the test suite."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

DECISION_ID = "pder_code_review_read_diff_0001"

FIXED_REPLAY_TIMESTAMP = "2026-05-23T00:00:00Z"

VERIFY_SCRIPTS = (
    ("manifest/scripts/check_release_manifest.py", "Release manifest checks passed"),
    ("events/scripts/check_agent_step_event.py", "Agent step event checks passed"),
    ("permissions/scripts/check_tool_permission_packet.py", "Tool permission packet checks passed"),
    ("demo/scripts/run_code_review_demo.py", "Generated demo state:"),
    ("demo/scripts/check_replay_state.py", "Demo replay state checks passed"),
    ("traces/scripts/check_eval_result.py", "Eval result checks passed"),
    ("traces/scripts/check_operational_trace.py", "Trace bundle checks passed"),
    ("playbooks/scripts/check_reconstruction_packet.py", "Reconstruction packet checks passed"),
    ("replay/scripts/check_v03_features.py", "v0.3 feature checks passed"),
    ("translations/bedrock/scripts/check_bedrock_translation.py", "Bedrock translation checks passed"),
    ("integrations/mcp/scripts/to_oep_permission.py", "MCP -> OEP permission packet projection checks passed"),
    ("scripts/check_public_docs.py", "Public documentation checks passed"),
)


def load_script_module(relative_path: str, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, ROOT / relative_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_script(
    relative_path: str,
    *,
    args: Sequence[str] = (),
    env: dict[str, str] | None = None,
) -> str:
    result = subprocess.run(
        [sys.executable, str(ROOT / relative_path), *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    return result.stdout


class _FakeOpaProcess:
    pid = 999_999

    def __init__(
        self,
        args: list[str],
        *,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
        timeout: bool = False,
        unexpected_exception: BaseException | None = None,
        expected_timeout: float | None = None,
    ) -> None:
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timeout = timeout
        self.unexpected_exception = unexpected_exception
        self.expected_timeout = expected_timeout
        self.killed = False
        self.waited = False
        self.communicate_calls = 0

    def communicate(
        self,
        input: str | None = None,
        timeout: float | None = None,
    ) -> tuple[str, str]:
        self.communicate_calls += 1
        if self.expected_timeout is not None and timeout is not None:
            assert timeout == self.expected_timeout
        if self.unexpected_exception is not None and self.communicate_calls == 1:
            raise self.unexpected_exception
        if self.timeout and self.communicate_calls == 1:
            raise subprocess.TimeoutExpired(cmd=self.args, timeout=timeout or 0.0)
        return self.stdout, self.stderr

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        self.waited = True
        return self.returncode


def _sqlite_payload(state_path: Path, query: str, parameters: tuple[object, ...]) -> dict[str, Any]:
    connection = sqlite3.connect(state_path)
    try:
        row = connection.execute(query, parameters).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        assert isinstance(payload, dict)
        return payload
    finally:
        connection.close()


def _sqlite_update_payload(
    state_path: Path,
    query: str,
    payload: dict[str, Any],
    parameters: tuple[object, ...],
) -> None:
    _sqlite_update_raw_payload(
        state_path,
        query,
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        parameters,
    )


def _sqlite_update_raw_payload(
    state_path: Path,
    query: str,
    payload_json: str,
    parameters: tuple[object, ...],
) -> None:
    connection = sqlite3.connect(state_path)
    try:
        connection.execute(query, (payload_json, *parameters))
        connection.commit()
    finally:
        connection.close()


def _sqlite_values(state_path: Path, query: str) -> list[object]:
    connection = sqlite3.connect(state_path)
    try:
        return [row[0] for row in connection.execute(query).fetchall()]
    finally:
        connection.close()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


SQLITE_ROW_COUNT_TABLES = frozenset(("artifacts", "events", "permissions", "traces", "findings", "evals"))


def _sqlite_row_counts(state_path: Path) -> dict[str, int]:
    connection = sqlite3.connect(state_path)
    try:
        return {table: _sqlite_row_count(connection, table) for table in sorted(SQLITE_ROW_COUNT_TABLES)}
    finally:
        connection.close()


def _sqlite_row_count(connection: sqlite3.Connection, table: str) -> int:
    if table not in SQLITE_ROW_COUNT_TABLES:
        raise ValueError(f"invalid replay-state table: {table}")
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _inject_nd_builtin_cache(state_path: Path, nd_builtin_cache: dict[str, object]) -> None:
    connection = sqlite3.connect(state_path)
    try:
        row = connection.execute(
            "SELECT payload_json FROM permissions WHERE packet_id = ?",
            (DECISION_ID,),
        ).fetchone()
        assert row is not None
        packet = json.loads(row[0])
        packet["nd_builtin_cache"] = nd_builtin_cache
        connection.execute(
            "UPDATE permissions SET payload_json = ? WHERE packet_id = ?",
            (json.dumps(packet, sort_keys=True, separators=(",", ":")), DECISION_ID),
        )
        connection.commit()
    finally:
        connection.close()


def _write_deny_policy(tmp_path: Path) -> Path:
    alt_policy_path = tmp_path / "counterfactual_policy.rego"
    alt_policy_path.write_text(
        """
package oep.permissions

decision := {
    "allow": false,
    "matched_rule": "deny_replayed_model_alias",
    "policy_id": "opa-tool-permission-policy",
    "policy_version": "0.3-test",
    "reason": "counterfactual policy blocks the stored model alias",
    "decision_code": "COUNTERFACTUAL_POLICY_DENY",
} if {
    input.action.action_type == "inspect_diff"
    input.model_alias == "deterministic-mock-reviewer"
    input.scoped_credential_lifetime == "PT15M"
}
""",
        encoding="utf-8",
    )
    return alt_policy_path
