"""Validate v0.3 counterfactual replay demos and determinism gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from oep_demo.counterfactual import (
    DEFAULT_COUNTERFACTUAL_DIR,
    run_approval_escalation_counterfactual,
    run_budget_per_run_counterfactual,
    run_compound_reliability_counterfactual,
)

from oep_verify.scenarios import scenario_names
from oep_verify.verify_support import (
    load_json_object,
    require,
    require_json_list,
    require_json_object,
    validate_json_schema,
)

ROOT = Path(__file__).resolve().parents[2]
COUNTERFACTUAL_SCHEMA_PATH = ROOT / "replay" / "counterfactual_replay.v0.schema.json"
DTR_JSONL_SCRIPT_PATH = ROOT / "integrations" / "decision-trace-reconstructor" / "scripts" / "to_dtr_jsonl.py"


@dataclass(frozen=True)
class DemoSpec:
    name: str
    runner: Callable[[Path], Any]
    expected_total_steps: int
    summary_check: Callable[[dict[str, Any]], None]


DEMO_SPECS = (
    DemoSpec(
        name="compound_reliability",
        runner=run_compound_reliability_counterfactual,
        expected_total_steps=10,
        summary_check=lambda summary: _check_compound_reliability_summary(summary),
    ),
    DemoSpec(
        name="budget_per_run",
        runner=run_budget_per_run_counterfactual,
        expected_total_steps=47,
        summary_check=lambda summary: _check_budget_per_run_summary(summary),
    ),
    DemoSpec(
        name="approval_escalation",
        runner=run_approval_escalation_counterfactual,
        expected_total_steps=6,
        summary_check=lambda summary: _check_approval_escalation_summary(summary),
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs",
        type=int,
        default=2,
        help="Number of independent counterfactual runs to compare; must be at least 2.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_COUNTERFACTUAL_DIR,
        help="Directory for the first generated counterfactual run.",
    )
    parser.add_argument(
        "--temp-only",
        action="store_true",
        help="Run every comparison pass in a temporary directory instead of writing --output-dir.",
    )
    parser.add_argument(
        "--include-dtr",
        action="store_true",
        help="Also regenerate DTR JSONL for committed scenarios and compare it across runs.",
    )
    args = parser.parse_args()

    require(args.runs >= 2, "--runs must be at least 2 for byte-identical comparison")
    schema = load_json_object(COUNTERFACTUAL_SCHEMA_PATH)
    outputs_by_run: list[dict[str, bytes]] = []

    with tempfile.TemporaryDirectory(prefix="oep-counterfactual-") as temp_root:
        temp_path = Path(temp_root)
        if not args.temp_only:
            _counterfactual_outputs(args.output_dir, schema)
        for run_index in range(args.runs):
            run_root = temp_path / f"run-{run_index + 1}"
            run_outputs = _counterfactual_outputs(run_root, schema)
            if args.include_dtr:
                run_outputs.update(_dtr_outputs(temp_path / f"dtr-run-{run_index + 1}"))
            outputs_by_run.append(run_outputs)

    _require_byte_identical(outputs_by_run)
    dtr_note = " and DTR JSONL" if args.include_dtr else ""
    print(f"Counterfactual replay checks passed: {len(DEMO_SPECS)} demos, {args.runs} runs{dtr_note}")


def _counterfactual_outputs(root: Path, schema: dict[str, Any]) -> dict[str, bytes]:
    outputs: dict[str, bytes] = {}
    root.mkdir(parents=True, exist_ok=True)
    for spec in DEMO_SPECS:
        result = spec.runner(root / spec.name)
        require(result.total_steps == spec.expected_total_steps, f"{spec.name}: unexpected total step count")

        json_path = _require_path(result.json_path, f"{spec.name}.json_path")
        jsonl_path = _require_path(result.jsonl_path, f"{spec.name}.jsonl_path")
        state_path = _require_path(result.state_path, f"{spec.name}.state_path")
        summary = load_json_object(json_path)
        step_outputs = _validate_summary(spec, summary, schema)
        _require_jsonl_matches_steps(jsonl_path, step_outputs)
        _require_state_refs(spec.name, state_path, json_path)

        outputs[f"counterfactual/{spec.name}/state.sqlite"] = state_path.read_bytes()
        outputs[f"counterfactual/{spec.name}/summary.json"] = json_path.read_bytes()
        outputs[f"counterfactual/{spec.name}/steps.jsonl"] = jsonl_path.read_bytes()
    return outputs


def _validate_summary(
    spec: DemoSpec,
    summary: dict[str, Any],
    schema: dict[str, Any],
) -> list[Any]:
    step_outputs = require_json_list(summary.get("step_outputs"), f"{spec.name}: step_outputs must be an array")
    require(
        len(step_outputs) == spec.expected_total_steps,
        f"{spec.name}: expected {spec.expected_total_steps} step outputs, got {len(step_outputs)}",
    )
    for index, raw_step in enumerate(step_outputs, start=1):
        step = require_json_object(raw_step, f"{spec.name}: step output {index} must be an object")
        validate_json_schema(schema, step, instance_path=Path(f"{spec.name}#step_outputs/{index}"))
    spec.summary_check(summary)
    return step_outputs


def _require_jsonl_matches_steps(jsonl_path: Path, step_outputs: list[Any]) -> None:
    jsonl_records = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    require(jsonl_records == step_outputs, f"{jsonl_path}: JSONL records must match summary step_outputs")


def _require_state_refs(scenario_name: str, state_path: Path, json_path: Path) -> None:
    output_ref = _stable_artifact_ref(json_path, json_path.parent)
    state_ref = _stable_artifact_ref(state_path, json_path.parent)
    connection = sqlite3.connect(state_path)
    try:
        event_rows = connection.execute("SELECT event_id, payload_json FROM events ORDER BY event_id").fetchall()
        require(bool(event_rows), f"{scenario_name}: replay state must contain events")
        for event_id, payload_json in event_rows:
            event = require_json_object(json.loads(payload_json), f"{scenario_name}: event payload must be an object")
            action = require_json_object(event.get("action"), f"{scenario_name}: event.action must be an object")
            require(action.get("output_ref") == output_ref, f"{scenario_name}: stale event output_ref for {event_id}")
            replay_handle = require_json_object(
                event.get("replay_handle"),
                f"{scenario_name}: event.replay_handle must be an object",
            )
            require(
                replay_handle.get("state_ref") == f"{state_ref}#events/{event_id}",
                f"{scenario_name}: stale replay_handle.state_ref for {event_id}",
            )

        artifact_rows = connection.execute(
            """
            SELECT path FROM artifacts
            WHERE kind IN ('agent_step_event', 'tool_permission_packet')
            ORDER BY kind, artifact_id
            """
        ).fetchall()
        require(bool(artifact_rows), f"{scenario_name}: replay state must contain event and permission artifacts")
        for (artifact_ref,) in artifact_rows:
            require(artifact_ref == output_ref, f"{scenario_name}: stale artifact path {artifact_ref!r}")
    finally:
        connection.close()


def _stable_artifact_ref(path: Path, output_dir: Path) -> str:
    return Path(os.path.relpath(path.resolve(), output_dir.resolve())).as_posix()


def _dtr_outputs(root: Path) -> dict[str, bytes]:
    outputs: dict[str, bytes] = {}
    root.mkdir(parents=True, exist_ok=True)
    for scenario in scenario_names():
        out_path = root / f"{scenario}.jsonl"
        _run(
            [
                sys.executable,
                str(DTR_JSONL_SCRIPT_PATH),
                "--scenario",
                scenario,
                "--out",
                str(out_path),
            ]
        )
        outputs[f"dtr/{scenario}.jsonl"] = out_path.read_bytes()
    return outputs


def _run(args: list[str]) -> None:
    completed = subprocess.run(args, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit(f"command failed with exit code {completed.returncode}: {' '.join(args)}")


def _require_byte_identical(outputs_by_run: list[dict[str, bytes]]) -> None:
    baseline = outputs_by_run[0]
    for run_index, outputs in enumerate(outputs_by_run[1:], start=2):
        require(
            outputs.keys() == baseline.keys(),
            f"run {run_index}: output key set differs from run 1",
        )
        for key in sorted(baseline):
            require(
                outputs[key] == baseline[key],
                (
                    f"{key} is not byte-identical between run 1 "
                    f"({_sha256(baseline[key])}) and run {run_index} ({_sha256(outputs[key])})"
                ),
            )


def _check_compound_reliability_summary(summary: dict[str, Any]) -> None:
    workflow = require_json_object(summary.get("workflow"), "compound_reliability.workflow must be an object")
    require(workflow.get("first_divergent_step") == 5, "compound reliability first divergent step must be 5")
    require(workflow.get("counterfactual_status") == "failed", "compound reliability counterfactual must fail")
    step_outputs = require_json_list(summary.get("step_outputs"), "compound reliability step outputs must be an array")
    divergent = require_json_object(step_outputs[4], "compound reliability divergent step must be an object")
    counterfactual = require_json_object(divergent.get("counterfactual"), "compound divergent counterfactual")
    require(counterfactual.get("decision") == "deny", "compound reliability step 5 must be denied")


def _check_budget_per_run_summary(summary: dict[str, Any]) -> None:
    budget = require_json_object(summary.get("budget"), "budget_per_run.budget must be an object")
    require(budget.get("termination_step") == 6, "budget-per-run termination step must be 6")
    require(budget.get("counterfactual_total_usd") == 5000, "budget-per-run total must stop at 5000")
    step_outputs = require_json_list(summary.get("step_outputs"), "budget-per-run step outputs must be an array")
    termination = require_json_object(step_outputs[5], "budget-per-run termination step must be an object")
    counterfactual = require_json_object(termination.get("counterfactual"), "budget termination counterfactual")
    require(counterfactual.get("decision_code") == "BUDGET_EXCEEDED", "budget step 6 must be budget denied")


def _check_approval_escalation_summary(summary: dict[str, Any]) -> None:
    approval = require_json_object(summary.get("approval"), "approval_escalation.approval must be an object")
    require(
        approval.get("added_approval_steps") == ["approval_step_02", "approval_step_04", "approval_step_05"],
        "approval escalation must add approval at steps 2, 4, and 5",
    )
    step_outputs = require_json_list(summary.get("step_outputs"), "approval escalation step outputs must be an array")
    for step_index in (2, 4, 5):
        step = require_json_object(step_outputs[step_index - 1], "approval escalation step must be an object")
        counterfactual = require_json_object(
            step.get("counterfactual"),
            "approval escalation counterfactual must be an object",
        )
        require(counterfactual.get("decision_code") == "APPROVAL_REQUIRED", f"step {step_index} must require approval")


def _require_path(value: object, field: str) -> Path:
    if not isinstance(value, Path):
        raise AssertionError(f"{field} must be a Path")
    require(value.is_file(), f"{field} does not exist: {value}")
    return value


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


if __name__ == "__main__":
    main()
