"""DTR JSONL projection and MCP adapter drift checks."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from helpers import (
    ROOT,
    load_script_module,
    run_script,
)

from oep_verify.scenarios import scenario_names


@pytest.mark.parametrize("scenario", scenario_names())
def test_dtr_jsonl_matches_committed_artifact(tmp_path: Path, scenario: str) -> None:
    generated_path = tmp_path / f"{scenario}.jsonl"
    output = run_script(
        "integrations/decision-trace-reconstructor/scripts/to_dtr_jsonl.py",
        args=("--scenario", scenario, "--out", str(generated_path)),
    )

    assert "wrote" in output
    assert generated_path.read_text(encoding="utf-8") == (
        ROOT / "integrations" / "decision-trace-reconstructor" / f"{scenario}.jsonl"
    ).read_text(encoding="utf-8")


def test_dtr_jsonl_sort_uses_kind_and_id_tie_breakers() -> None:
    module = load_script_module(
        "integrations/decision-trace-reconstructor/scripts/to_dtr_jsonl.py",
        "to_dtr_jsonl_sort_test",
    )
    records = [
        {"id": "tool_b", "ts": 1.0, "kind": "tool"},
        {"id": "policy_z", "ts": 1.0, "kind": "policy"},
        {"id": "policy_a", "ts": 1.0, "kind": "policy"},
    ]

    sorted_records = module.sort_jsonl_records(records)

    assert [(record["kind"], record["id"]) for record in sorted_records] == [
        ("policy", "policy_a"),
        ("policy", "policy_z"),
        ("tool", "tool_b"),
    ]


def test_mcp_adapter_rejects_canonical_drift(tmp_path: Path) -> None:
    module = load_script_module(
        "integrations/mcp/scripts/to_oep_permission.py",
        "mcp_projection_test",
    )
    mcp_event = json.loads(
        (ROOT / "integrations" / "mcp" / "examples" / "code_review_mcp_tool_call.v0.json").read_text(encoding="utf-8")
    )
    drifted = dict(mcp_event)
    drifted["session"] = {**mcp_event["session"], "policy_bundle_version": "sha256:" + ("0" * 64)}
    drifted_event_path = tmp_path / "drifted_mcp.json"
    drifted_event_path.write_text(json.dumps(drifted), encoding="utf-8")

    canonical_path = ROOT / "permissions" / "examples" / "code_review_tool_permission.v0.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "integrations" / "mcp" / "scripts" / "to_oep_permission.py"),
            "--mcp-event",
            str(drifted_event_path),
            "--compare-with",
            str(canonical_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "MCP -> OEP projection drift" in result.stderr

    projected = module.project_to_oep_permission(mcp_event)
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    assert projected == canonical


def test_mcp_adapter_serializes_generic_arguments() -> None:
    module = load_script_module(
        "integrations/mcp/scripts/to_oep_permission.py",
        "mcp_projection_generic_args_test",
    )
    mcp_event = json.loads(
        (ROOT / "integrations" / "mcp" / "examples" / "code_review_mcp_tool_call.v0.json").read_text(encoding="utf-8")
    )
    mcp_event["request"]["params"]["arguments"] = {
        "line": 42,
        "path": "src/example.py",
    }

    projected = module.project_to_oep_permission(mcp_event)

    assert projected["requested_action"]["input_ref"] == '{"line":42,"path":"src/example.py"}'
