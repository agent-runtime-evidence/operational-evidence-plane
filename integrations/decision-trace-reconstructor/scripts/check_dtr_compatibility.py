"""Check a versioned external DTR CLI without changing historical fixtures."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def expected_path(version: str, scenario: str) -> Path:
    if scenario != "code_review_agent":
        raise ValueError("Only the allowed scenario has a pinned DTR CLI expectation")
    if version in {"0.1.0", "0.1.1", "0.1.2"}:
        return ROOT / f"{scenario}.expected_feasibility.json"
    if version == "0.2.0":
        return ROOT / "expected/v0.2.0" / f"{scenario}.feasibility.json"
    raise ValueError(f"No reviewed DTR compatibility expectation for {version}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dtr", default="decision-trace")
    parser.add_argument("--version", default="0.2.0")
    parser.add_argument("--scenario", default="code_review_agent")
    args = parser.parse_args()
    expected = json.loads(expected_path(args.version, args.scenario).read_text())
    actual_version = subprocess.check_output([args.dtr, "--version"], text=True).strip().split()[-1]
    if actual_version != args.version:
        raise SystemExit(f"Expected DTR {args.version}, found {actual_version}")
    with tempfile.TemporaryDirectory(prefix="oep-dtr-") as directory:
        work = Path(directory)
        mapping = str(ROOT / "mapping.v0.yaml")
        source = str(ROOT / f"{args.scenario}.jsonl")
        manifest = str(work / "fragments.json")
        subprocess.run(
            [args.dtr, "validate", "generic-jsonl", "--mapping", mapping, "--sample-from", source], check=True
        )
        subprocess.run(
            [
                args.dtr,
                "ingest",
                "generic-jsonl",
                "--from-file",
                source,
                "--mapping",
                mapping,
                "--scenario-id",
                f"oep_{args.scenario}",
                "--out",
                manifest,
            ],
            check=True,
        )
        subprocess.run([args.dtr, "reconstruct", manifest, "--out", str(work / "report"), "--jsonld"], check=True)
        actual = json.loads((work / "report/feasibility.json").read_text())
        if actual != expected:
            raise SystemExit("DTR CLI output differs from the complete versioned expectation")
    print(f"OK: {args.scenario} matches DTR {args.version}; historical fixture unchanged")


if __name__ == "__main__":
    main()
