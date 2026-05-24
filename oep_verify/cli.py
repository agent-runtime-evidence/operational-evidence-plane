"""`oep` top-level command dispatcher.

Provides the v0.2 read-only `oep replay <decision_id>` path and the v0.3
counterfactual policy replay mode.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_DISPATCH_EPILOG = """\
Examples:
  # Reconstruct the demo's allowed decision (after `oep-run-demo`).
  oep replay pder_code_review_read_diff_0001

  # Print only the v0.2 model alias for a recorded decision.
  oep replay pder_code_review_read_diff_0001 --field model_alias

  # Read from an alternate SQLite path.
  oep replay pder_code_review_read_diff_0001 --state-path /tmp/oep.sqlite

  # Re-derive a stored decision under a substituted policy bundle.
  oep replay pder_code_review_read_diff_0001 --counterfactual \\
      --policy-bundle permissions/policy/tool_permissions.rego \\
      --output-format json
"""

_REPLAY_EPILOG = """\
Examples:
  # Full reconstructed record as JSON.
  oep replay pder_code_review_read_diff_0001

  # Specific fields only (may be repeated).
  oep replay pder_code_review_read_diff_0001 \\
      --field decision_id --field policy_bundle_version

  # Custom state path (also supports OEP_DEMO_STATE_PATH env var).
  oep replay pder_code_review_read_diff_0001 --state-path /tmp/oep.sqlite

  # Counterfactual replay can be enabled by flag or OEP_REPLAY_MODE.
  oep replay pder_code_review_read_diff_0001 --counterfactual \\
      --policy-bundle permissions/policy/tool_permissions.rego

  # Pin the replay timestamp when comparing CLI output byte-for-byte.
  oep replay pder_code_review_read_diff_0001 --counterfactual \\
      --policy-bundle permissions/policy/tool_permissions.rego \\
      --replay-timestamp-utc 2026-05-23T00:00:00Z

  # Strip fields listed in replay_metadata.determinism_exclusions.
  oep replay pder_code_review_read_diff_0001 --counterfactual \\
      --policy-bundle permissions/policy/tool_permissions.rego \\
      --strip-exclusions --output-format jsonl

Denied decisions:
  Denied tool calls do not generate SQLite replay state by design — the
  v0.1 evidence chain marks replay state as missing for those events.
  Inspect the denied permission packet artifact (under
  permissions/examples/) directly instead of using `oep replay`.
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oep",
        description=(
            "Operational Evidence Plane CLI. Subcommands operate on locally "
            "regenerable replay state; they do not make live model calls or "
            "vendor API calls."
        ),
        epilog=_DISPATCH_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    replay_parser = subparsers.add_parser(
        "replay",
        help=(
            "Reconstruct the recorded permission trace for a decision id from "
            "local SQLite replay state."
        ),
        description=(
            "Reconstruct the recorded permission trace for a decision id "
            "(the `pder_*` packet identifier) from the local SQLite replay "
            "state. The output joins the permission packet, agent-step event, "
            "trace bundle, and release-manifest summary recorded for that "
            "decision. The command is a read-only reader over the demo "
            "replay store; it does not call live models or vendor APIs."
        ),
        epilog=_REPLAY_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    replay_parser.add_argument(
        "decision_id",
        help="Decision identifier (the permission packet `pder_*` id).",
    )
    replay_parser.add_argument(
        "--state-path",
        type=Path,
        default=None,
        help=(
            "Path to the SQLite replay state. Defaults to the demo state "
            "(demo/state/code_review_agent.sqlite), overridable via "
            "OEP_DEMO_STATE_PATH."
        ),
    )
    replay_parser.add_argument(
        "--field",
        action="append",
        default=None,
        help=(
            "Optional record field to print on its own line instead of the "
            "full JSON record. May be repeated."
        ),
    )
    replay_parser.add_argument(
        "--counterfactual",
        action="store_true",
        help=(
            "Enable v0.3 counterfactual policy replay. Equivalent to "
            "OEP_REPLAY_MODE=counterfactual for this command."
        ),
    )
    replay_parser.add_argument(
        "--policy-bundle",
        type=Path,
        default=None,
        help=(
            "Path to the substituted OPA policy bundle for counterfactual "
            "replay. Required when --counterfactual or "
            "OEP_REPLAY_MODE=counterfactual is set."
        ),
    )
    replay_parser.add_argument(
        "--output-format",
        choices=("json", "jsonl", "human"),
        default=None,
        help=(
            "Output format. Read-only replay defaults to json; "
            "counterfactual replay defaults to human."
        ),
    )
    replay_parser.add_argument(
        "--replay-timestamp-utc",
        default=None,
        help=(
            "Optional counterfactual replay timestamp. Pin this value when "
            "comparing CLI output byte-for-byte; otherwise the record marks "
            "the wall-clock replay timestamp as a determinism exclusion."
        ),
    )
    replay_parser.add_argument(
        "--strip-exclusions",
        action="store_true",
        help=(
            "For counterfactual replay output, remove fields listed in "
            "replay_metadata.determinism_exclusions before printing."
        ),
    )
    return parser


def _replay(args: argparse.Namespace) -> None:
    from oep_demo.paths import STATE_PATH as DEFAULT_STATE_PATH
    from oep_permissions.replay import ReplayError, counterfactual_replay_decision, reconstruct_decision

    state_path = args.state_path if args.state_path is not None else DEFAULT_STATE_PATH
    replay_mode = _replay_mode(args.counterfactual)
    if replay_mode == "counterfactual":
        if args.field:
            raise SystemExit("--field is only supported for read-only replay output")
        if args.policy_bundle is None:
            raise SystemExit("--policy-bundle is required for counterfactual replay")
        try:
            counterfactual_record = counterfactual_replay_decision(
                state_path,
                args.decision_id,
                args.policy_bundle,
                replay_timestamp_utc=args.replay_timestamp_utc,
            )
        except ReplayError as exc:
            raise SystemExit(str(exc)) from exc
        record = counterfactual_record.to_dict()
        if args.strip_exclusions:
            record = _strip_determinism_exclusions(record)
        _print_record(record, args.output_format or "human")
        return

    if args.policy_bundle is not None:
        raise SystemExit("--policy-bundle requires counterfactual replay mode")
    if args.replay_timestamp_utc is not None:
        raise SystemExit("--replay-timestamp-utc requires counterfactual replay mode")
    if args.strip_exclusions:
        raise SystemExit("--strip-exclusions requires counterfactual replay mode")

    try:
        read_only_record = reconstruct_decision(state_path, args.decision_id)
    except ReplayError as exc:
        raise SystemExit(str(exc)) from exc

    record_dict = read_only_record.to_dict()
    if args.field:
        for field in args.field:
            if field not in record_dict:
                raise SystemExit(f"unknown replay record field: {field}")
            print(json.dumps(record_dict[field], indent=2, sort_keys=True))
        return

    _print_record(record_dict, args.output_format or "json")


def _replay_mode(counterfactual_flag: bool) -> str:
    if counterfactual_flag:
        return "counterfactual"
    env_mode = os.environ.get("OEP_REPLAY_MODE", "read-only")
    if env_mode not in {"read-only", "counterfactual"}:
        raise SystemExit("OEP_REPLAY_MODE must be 'read-only' or 'counterfactual'")
    return env_mode


def _print_record(record: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(record, indent=2, sort_keys=True))
        return
    if output_format == "jsonl":
        print(json.dumps(record, sort_keys=True, separators=(",", ":")))
        return
    if output_format == "human":
        _print_human_record(record)
        return
    raise SystemExit(f"unknown output format: {output_format}")


def _strip_determinism_exclusions(record: dict[str, Any]) -> dict[str, Any]:
    stripped = json.loads(json.dumps(record, sort_keys=True))
    if not isinstance(stripped, dict):
        return record
    metadata = _json_object(stripped.get("replay_metadata"))
    exclusions = metadata.get("determinism_exclusions")
    if not isinstance(exclusions, list):
        return stripped
    for exclusion in exclusions:
        if isinstance(exclusion, str):
            _remove_dotted_path(stripped, exclusion)
    return stripped


def _remove_dotted_path(record: dict[str, Any], dotted_path: str) -> None:
    parts = dotted_path.split(".")
    if not parts or any(part == "" for part in parts):
        return
    parent: Any = record
    for part in parts[:-1]:
        if not isinstance(parent, dict):
            return
        parent = parent.get(part)
    if isinstance(parent, dict):
        parent.pop(parts[-1], None)


def _print_human_record(record: dict[str, Any]) -> None:
    if record.get("replay_mode") == "counterfactual":
        original = _json_object(record.get("original"))
        counterfactual = _json_object(record.get("counterfactual"))
        diff = _json_object(record.get("diff"))
        metadata = _json_object(record.get("replay_metadata"))
        print(f"decision_id: {record.get('decision_id')}")
        print(f"replay_mode: {record.get('replay_mode')}")
        print(f"original: {original.get('decision')} ({original.get('policy_bundle_version')})")
        print(f"counterfactual: {counterfactual.get('decision')} ({counterfactual.get('policy_bundle_version')})")
        print(f"decision_changed: {diff.get('decision_changed')}")
        print(f"rationale_changed: {diff.get('rationale_changed')}")
        print(f"nd_builtin_cache_entries_used: {metadata.get('nd_builtin_cache_entries_used')}")
        print(f"replay_timestamp_utc: {metadata.get('replay_timestamp_utc')}")
        return

    print(f"decision_id: {record.get('decision_id')}")
    print(f"tool_call_id: {record.get('tool_call_id')}")
    print(f"release_manifest_id: {record.get('release_manifest_id')}")
    print(f"trace_id: {record.get('trace_id')}")
    print(f"span_id: {record.get('span_id')}")
    print(f"policy_bundle_version: {record.get('policy_bundle_version')}")
    print(f"replay_handle: {json.dumps(record.get('replay_handle'), sort_keys=True)}")


def _json_object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "replay":
        _replay(args)
        return

    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main(sys.argv[1:])
