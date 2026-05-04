"""Build and install the root distribution as a packaging smoke test."""

from __future__ import annotations

import shlex
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import venv
import zipfile
from collections.abc import Sequence
from pathlib import Path

from oep_verify.artifacts import (
    EXPECTED_PACKAGE_FILES,
    FORBIDDEN_SOURCE_DISTRIBUTION_FILES,
    FORBIDDEN_SOURCE_DISTRIBUTION_SUFFIXES,
    PACKAGE_NAMES,
    PACKAGED_ARTIFACTS,
    SOURCE_DISTRIBUTION_FILES,
    PackagedArtifact,
    packaged_resource_sync_errors,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SCENARIOS = ("code_review_agent", "code_review_agent_denied")
CONSOLE_SCRIPTS = ("oep-check-reconstruction", "oep-run-demo", "oep-verify-manifest")


def format_command(args: Sequence[str]) -> str:
    return subprocess.list2cmdline(args) if sys.platform == "win32" else shlex.join(args)


def run(args: Sequence[str], *, cwd: Path = REPO_ROOT, disallowed_output: Sequence[str] = ()) -> str:
    try:
        completed = subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise SystemExit(f"command not found: {args[0]}") from exc

    output = f"{completed.stdout}{completed.stderr}"
    if completed.returncode != 0:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit(f"command failed with exit code {completed.returncode}: {format_command(args)}")

    matched = [marker for marker in disallowed_output if marker in output]
    if matched:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit(f"command output contained disallowed text {matched}: {format_command(args)}")

    return output


def require_single_file(files: Sequence[Path], pattern: str) -> Path:
    if len(files) != 1:
        found = ", ".join(path.name for path in files) or "none"
        raise SystemExit(f"expected exactly one {pattern}; found {found}")
    return files[0]


def check_resource_sync(
    artifacts: Sequence[PackagedArtifact] = PACKAGED_ARTIFACTS,
    *,
    repo_root: Path = REPO_ROOT,
) -> None:
    mismatches = packaged_resource_sync_errors(repo_root, artifacts)
    if mismatches:
        raise SystemExit("\n".join(mismatches))


def build_distribution(dist_dir: Path) -> tuple[Path, Path]:
    run(
        [sys.executable, "-m", "build", "--sdist", "--wheel", "--outdir", str(dist_dir), str(REPO_ROOT)],
        disallowed_output=("SetuptoolsDeprecationWarning",),
    )
    wheel = require_single_file(sorted(dist_dir.glob("*.whl")), "wheel")
    sdist = require_single_file(sorted(dist_dir.glob("*.tar.gz")), "sdist")
    return wheel, sdist


def check_wheel_contents(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())

    missing = [expected_file for expected_file in EXPECTED_PACKAGE_FILES if expected_file not in names]
    if missing:
        raise SystemExit(f"wheel is missing package files: {', '.join(missing)}")


def sdist_member_files(sdist: Path) -> set[str]:
    with tarfile.open(sdist, "r:gz") as archive:
        names = set()
        for member in archive.getmembers():
            if not member.isfile():
                continue
            parts = Path(member.name).parts
            if len(parts) < 2:
                continue
            names.add("/".join(parts[1:]))
    return names


def check_sdist_contents(sdist: Path) -> None:
    names = sdist_member_files(sdist)

    missing_package_files = [
        expected_file
        for expected_file in EXPECTED_PACKAGE_FILES
        if not any(name == expected_file or name.endswith(f"/{expected_file}") for name in names)
    ]
    missing_source_files = [expected_file for expected_file in SOURCE_DISTRIBUTION_FILES if expected_file not in names]
    forbidden_files = sorted(
        name
        for name in names
        if name in FORBIDDEN_SOURCE_DISTRIBUTION_FILES
        or name.endswith(FORBIDDEN_SOURCE_DISTRIBUTION_SUFFIXES)
        or ".report/" in name
    )

    errors = []
    if missing_package_files:
        errors.append(f"sdist is missing package files: {', '.join(missing_package_files)}")
    if missing_source_files:
        errors.append(f"sdist is missing source files: {', '.join(missing_source_files)}")
    if forbidden_files:
        errors.append(f"sdist contains generated or cache files: {', '.join(forbidden_files)}")
    if errors:
        raise SystemExit("\n".join(errors))


def create_venv(venv_dir: Path) -> Path:
    venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
    scripts_dir = "Scripts" if sys.platform == "win32" else "bin"
    executable = "python.exe" if sys.platform == "win32" else "python"
    return venv_dir / scripts_dir / executable


def console_script_path(venv_python: Path, script_name: str) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return venv_python.parent / f"{script_name}{suffix}"


def check_installed_wheel(wheel: Path, venv_python: Path) -> None:
    run([str(venv_python), "-m", "pip", "--disable-pip-version-check", "install", "--no-deps", str(wheel)])
    state_path = venv_python.parent.parent / "oep-smoke-state.sqlite"
    smoke_script = textwrap.dedent(
        f"""
        import json
        from importlib import metadata
        from pathlib import Path

        for package_name in {PACKAGE_NAMES!r}:
            __import__(package_name)

        from oep_verify.scenarios import scenario_names
        from oep_manifest.paths import EXAMPLE_PATH as MANIFEST_PATH, SCHEMA_PATH as MANIFEST_SCHEMA_PATH
        from oep_events.paths import DENIED_EXAMPLE_PATH as DENIED_EVENT_PATH, EXAMPLE_PATH as EVENT_PATH
        from oep_permissions.paths import (
            DENIED_EXAMPLE_PATH as DENIED_PERMISSION_PATH,
            DENIED_INPUT_PATH,
            EXAMPLE_PATH as PERMISSION_PATH,
            INPUT_PATH,
            POLICY_PATH,
            POLICY_TEST_PATH,
            SCHEMA_PATH as PERMISSION_SCHEMA_PATH,
        )
        from oep_traces.paths import (
            DENIED_EVAL_EXAMPLE_PATH,
            DENIED_TRACE_EXAMPLE_PATH,
            EVAL_EXAMPLE_PATH,
            EVAL_SCHEMA_PATH,
            SCHEMA_PATH as TRACE_SCHEMA_PATH,
            TRACE_EXAMPLE_PATH,
        )
        from oep_playbooks.paths import (
            DENIED_EXAMPLE_PATH as DENIED_RECONSTRUCTION_PATH,
            EXAMPLE_PATH as RECONSTRUCTION_PATH,
            RECONSTRUCTION_RULES_PATH,
            SCHEMA_PATH as RECONSTRUCTION_SCHEMA_PATH,
        )
        from oep_demo.paths import (
            FIXTURE_PATH,
            MODEL_CONTRACT_PATH,
            PROMPT_CONTRACT_PATH,
            REPLAY_STATE_RECIPE_PATH,
        )
        from oep_demo import run_demo

        resource_paths = (
            MANIFEST_PATH,
            MANIFEST_SCHEMA_PATH,
            DENIED_EVENT_PATH,
            EVENT_PATH,
            DENIED_PERMISSION_PATH,
            DENIED_INPUT_PATH,
            PERMISSION_PATH,
            INPUT_PATH,
            POLICY_PATH,
            POLICY_TEST_PATH,
            PERMISSION_SCHEMA_PATH,
            DENIED_EVAL_EXAMPLE_PATH,
            DENIED_TRACE_EXAMPLE_PATH,
            EVAL_EXAMPLE_PATH,
            EVAL_SCHEMA_PATH,
            TRACE_SCHEMA_PATH,
            TRACE_EXAMPLE_PATH,
            DENIED_RECONSTRUCTION_PATH,
            RECONSTRUCTION_PATH,
            RECONSTRUCTION_RULES_PATH,
            RECONSTRUCTION_SCHEMA_PATH,
            FIXTURE_PATH,
            MODEL_CONTRACT_PATH,
            PROMPT_CONTRACT_PATH,
            REPLAY_STATE_RECIPE_PATH,
        )
        missing_paths = [str(path) for path in resource_paths if not Path(path).is_file()]
        if missing_paths:
            raise SystemExit(f"installed package resources are missing: {{missing_paths}}")

        scenarios = set(scenario_names())
        missing_scenarios = sorted(set({EXPECTED_SCENARIOS!r}) - scenarios)
        if missing_scenarios:
            raise SystemExit(f"installed scenario registry is missing: {{missing_scenarios}}")

        if json.loads(Path(MANIFEST_SCHEMA_PATH).read_text(encoding="utf-8"))["title"] != (
            "Operational Evidence Plane Release Manifest v0"
        ):
            raise SystemExit("installed manifest schema resource is unreadable")
        if "return None" not in Path(FIXTURE_PATH).read_text(encoding="utf-8"):
            raise SystemExit("installed demo fixture resource is unreadable")

        result = run_demo(Path({str(state_path)!r}))
        if result.finding_count != 1 or not result.state_path.is_file():
            raise SystemExit("installed demo runner did not generate expected replay state")

        requirements = metadata.requires("operational-evidence-plane") or []
        if not any(requirement.startswith("jsonschema") for requirement in requirements):
            raise SystemExit("installed metadata is missing the jsonschema runtime dependency")
        """
    )
    run([str(venv_python), "-c", smoke_script])
    for script_name in CONSOLE_SCRIPTS:
        script_path = console_script_path(venv_python, script_name)
        if not script_path.exists():
            raise SystemExit(f"console script missing after wheel install: {script_name}")
    run(
        [
            str(console_script_path(venv_python, "oep-run-demo")),
            "--state-path",
            str(venv_python.parent.parent / "cli-state.sqlite"),
        ]
    )
    run([str(console_script_path(venv_python, "oep-verify-manifest")), "--help"])
    run([str(console_script_path(venv_python, "oep-check-reconstruction")), "--help"])


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="oep-build-") as temp_root:
        temp_path = Path(temp_root)
        check_resource_sync()
        wheel, sdist = build_distribution(temp_path / "dist")
        check_wheel_contents(wheel)
        check_sdist_contents(sdist)
        check_installed_wheel(wheel, create_venv(temp_path / "venv"))

    print("Package build checks passed.")


if __name__ == "__main__":
    main()
