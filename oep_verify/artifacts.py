"""Registry for canonical artifacts that are mirrored as package resources."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

PACKAGE_NAMES = (
    "oep_verify",
    "oep_manifest",
    "oep_events",
    "oep_permissions",
    "oep_traces",
    "oep_playbooks",
    "oep_demo",
)
PY_TYPED_FILES = tuple(f"{package_name}/py.typed" for package_name in PACKAGE_NAMES)


@dataclass(frozen=True)
class PackagedArtifact:
    canonical_path: str
    workspace: str
    package_file: str

    def canonical_file(self, repo_root: Path) -> Path:
        return repo_root / self.canonical_path

    def packaged_file(self, repo_root: Path) -> Path:
        return repo_root / self.workspace / "src" / self.package_file

    @property
    def packaged_display_path(self) -> str:
        return f"{self.workspace}/src/{self.package_file}"


PACKAGED_ARTIFACTS: tuple[PackagedArtifact, ...] = (
    PackagedArtifact(
        "manifest/schema/release_manifest.v0.schema.json",
        "manifest",
        "oep_manifest/resources/schema/release_manifest.v0.schema.json",
    ),
    PackagedArtifact(
        "manifest/examples/code_review_agent_release.v0.json",
        "manifest",
        "oep_manifest/resources/examples/code_review_agent_release.v0.json",
    ),
    PackagedArtifact(
        "events/schema/agent_step_event.v0.schema.json",
        "events",
        "oep_events/resources/schema/agent_step_event.v0.schema.json",
    ),
    PackagedArtifact(
        "events/examples/code_review_agent_step.v0.json",
        "events",
        "oep_events/resources/examples/code_review_agent_step.v0.json",
    ),
    PackagedArtifact(
        "events/examples/code_review_agent_denied_step.v0.json",
        "events",
        "oep_events/resources/examples/code_review_agent_denied_step.v0.json",
    ),
    PackagedArtifact(
        "permissions/schema/tool_permission_packet.v0.schema.json",
        "permissions",
        "oep_permissions/resources/schema/tool_permission_packet.v0.schema.json",
    ),
    PackagedArtifact(
        "replay/counterfactual_replay.v0.schema.json",
        "permissions",
        "oep_permissions/resources/schema/counterfactual_replay.v0.schema.json",
    ),
    PackagedArtifact(
        "permissions/examples/code_review_tool_permission.v0.json",
        "permissions",
        "oep_permissions/resources/examples/code_review_tool_permission.v0.json",
    ),
    PackagedArtifact(
        "permissions/examples/code_review_tool_permission_denied.v0.json",
        "permissions",
        "oep_permissions/resources/examples/code_review_tool_permission_denied.v0.json",
    ),
    PackagedArtifact(
        "permissions/policy/tool_permissions.rego",
        "permissions",
        "oep_permissions/resources/policy/tool_permissions.rego",
    ),
    PackagedArtifact(
        "permissions/policy/counterfactual/compound_reliability_step_bound.rego",
        "permissions",
        "oep_permissions/resources/policy/counterfactual/compound_reliability_step_bound.rego",
    ),
    PackagedArtifact(
        "permissions/policy/counterfactual/budget_per_run_cap.rego",
        "permissions",
        "oep_permissions/resources/policy/counterfactual/budget_per_run_cap.rego",
    ),
    PackagedArtifact(
        "permissions/policy/counterfactual/approval_per_step_escalation.rego",
        "permissions",
        "oep_permissions/resources/policy/counterfactual/approval_per_step_escalation.rego",
    ),
    PackagedArtifact(
        "permissions/policy/tool_permissions_test.rego",
        "permissions",
        "oep_permissions/resources/policy/tool_permissions_test.rego",
    ),
    PackagedArtifact(
        "permissions/policy/input/code_review_read_diff.json",
        "permissions",
        "oep_permissions/resources/policy/input/code_review_read_diff.json",
    ),
    PackagedArtifact(
        "permissions/policy/input/code_review_write_diff.json",
        "permissions",
        "oep_permissions/resources/policy/input/code_review_write_diff.json",
    ),
    PackagedArtifact(
        "traces/schema/operational_trace.v0.schema.json",
        "traces",
        "oep_traces/resources/schema/operational_trace.v0.schema.json",
    ),
    PackagedArtifact(
        "traces/schema/eval_result.v0.schema.json",
        "traces",
        "oep_traces/resources/schema/eval_result.v0.schema.json",
    ),
    PackagedArtifact(
        "traces/examples/code_review_agent_trace.v0.json",
        "traces",
        "oep_traces/resources/examples/code_review_agent_trace.v0.json",
    ),
    PackagedArtifact(
        "traces/examples/code_review_agent_denied_trace.v0.json",
        "traces",
        "oep_traces/resources/examples/code_review_agent_denied_trace.v0.json",
    ),
    PackagedArtifact(
        "traces/examples/code_review_agent_eval.v0.json",
        "traces",
        "oep_traces/resources/examples/code_review_agent_eval.v0.json",
    ),
    PackagedArtifact(
        "traces/examples/code_review_agent_denied_eval.v0.json",
        "traces",
        "oep_traces/resources/examples/code_review_agent_denied_eval.v0.json",
    ),
    PackagedArtifact(
        "playbooks/rollback_reconstruction.md",
        "playbooks",
        "oep_playbooks/resources/rollback_reconstruction.md",
    ),
    PackagedArtifact(
        "playbooks/schema/reconstruction_packet.v0.schema.json",
        "playbooks",
        "oep_playbooks/resources/schema/reconstruction_packet.v0.schema.json",
    ),
    PackagedArtifact(
        "playbooks/examples/code_review_reconstruction_packet.v0.json",
        "playbooks",
        "oep_playbooks/resources/examples/code_review_reconstruction_packet.v0.json",
    ),
    PackagedArtifact(
        "playbooks/examples/code_review_denied_reconstruction_packet.v0.json",
        "playbooks",
        "oep_playbooks/resources/examples/code_review_denied_reconstruction_packet.v0.json",
    ),
    PackagedArtifact(
        "demo/fixtures/diff_synthetic_001.patch",
        "demo",
        "oep_demo/resources/fixtures/diff_synthetic_001.patch",
    ),
    PackagedArtifact(
        "demo/model/deterministic_mock_reviewer.md",
        "demo",
        "oep_demo/resources/model/deterministic_mock_reviewer.md",
    ),
    PackagedArtifact(
        "demo/prompts/code_review_agent.md",
        "demo",
        "oep_demo/resources/prompts/code_review_agent.md",
    ),
    PackagedArtifact(
        "demo/state/replay_state_recipe.md",
        "demo",
        "oep_demo/resources/state/replay_state_recipe.md",
    ),
)

PACKAGE_RESOURCE_FILES = tuple(artifact.package_file for artifact in PACKAGED_ARTIFACTS)
EXPECTED_PACKAGE_FILES = PY_TYPED_FILES + PACKAGE_RESOURCE_FILES

SOURCE_DISTRIBUTION_FILES = tuple(
    sorted(
        {
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            ".github/ISSUE_TEMPLATE/config.yml",
            ".github/ISSUE_TEMPLATE/docs_question.yml",
            ".github/workflows/verify.yml",
            ".gitattributes",
            "CHANGELOG.md",
            "CITATION.cff",
            "CONTRIBUTING.md",
            "LICENSE",
            "MANIFEST.in",
            "Makefile",
            "README.md",
            "SECURITY.md",
            "demo/counterfactual/.gitkeep",
            "demo/pyproject.toml",
            "demo/scripts/check_replay_state.py",
            "demo/scripts/run_approval_escalation_counterfactual.py",
            "demo/scripts/run_budget_per_run_counterfactual.py",
            "demo/scripts/run_compound_reliability_counterfactual.py",
            "demo/scripts/run_code_review_demo.py",
            "demo/src/oep_demo/__init__.py",
            "demo/src/oep_demo/cli.py",
            "demo/src/oep_demo/counterfactual.py",
            "demo/src/oep_demo/paths.py",
            "demo/src/oep_demo/py.typed",
            "demo/src/oep_demo/runner.py",
            "docs/architecture.md",
            "docs/decision_log.md",
            "docs/oep_evidence_chain.svg",
            "docs/public_claims.md",
            "docs/release_checklist.md",
            "docs/schema_migration_v0.3.md",
            "events/pyproject.toml",
            "events/scripts/check_agent_step_event.py",
            "events/src/oep_events/__init__.py",
            "events/src/oep_events/paths.py",
            "events/src/oep_events/py.typed",
            "integrations/decision-trace-reconstructor/README.md",
            "integrations/decision-trace-reconstructor/code_review_agent.expected_feasibility.json",
            "integrations/decision-trace-reconstructor/code_review_agent.jsonl",
            "integrations/decision-trace-reconstructor/code_review_agent_denied.jsonl",
            "integrations/decision-trace-reconstructor/mapping.v0.yaml",
            "integrations/decision-trace-reconstructor/scripts/to_dtr_jsonl.py",
            "integrations/mcp/README.md",
            "integrations/mcp/__init__.py",
            "integrations/mcp/examples/code_review_mcp_tool_call.v0.json",
            "integrations/mcp/mapping.v0.yaml",
            "integrations/mcp/scripts/__init__.py",
            "integrations/mcp/scripts/to_oep_permission.py",
            "integrations/__init__.py",
            "integrations/langgraph/README.md",
            "integrations/langgraph/__init__.py",
            "integrations/langgraph/examples/code_review_langgraph_checkpoint.v0.json",
            "integrations/langgraph/mapping.v0.yaml",
            "integrations/langgraph/scripts/__init__.py",
            "integrations/langgraph/scripts/to_oep_permission.py",
            "manifest/pyproject.toml",
            "manifest/scripts/check_release_manifest.py",
            "manifest/scripts/update_manifest_digests.py",
            "manifest/src/oep_manifest/__init__.py",
            "manifest/src/oep_manifest/cli.py",
            "manifest/src/oep_manifest/paths.py",
            "manifest/src/oep_manifest/py.typed",
            "oep_verify/__init__.py",
            "oep_verify/artifacts.py",
            "oep_verify/cli.py",
            "oep_verify/py.typed",
            "oep_verify/scenarios.py",
            "oep_verify/verify_support.py",
            "permissions/pyproject.toml",
            "permissions/policy/counterfactual/approval_per_step_escalation.rego",
            "permissions/policy/counterfactual/approval_per_step_escalation_test.rego",
            "permissions/policy/counterfactual/budget_per_run_cap.rego",
            "permissions/policy/counterfactual/budget_per_run_cap_test.rego",
            "permissions/policy/counterfactual/compound_reliability_step_bound.rego",
            "permissions/policy/counterfactual/compound_reliability_step_bound_test.rego",
            "permissions/scripts/check_tool_permission_packet.py",
            "permissions/scripts/update_permission_digests.py",
            "permissions/src/oep_permissions/__init__.py",
            "permissions/src/oep_permissions/paths.py",
            "permissions/src/oep_permissions/py.typed",
            "permissions/src/oep_permissions/replay.py",
            "playbooks/pyproject.toml",
            "playbooks/scripts/check_reconstruction_packet.py",
            "playbooks/src/oep_playbooks/__init__.py",
            "playbooks/src/oep_playbooks/cli.py",
            "playbooks/src/oep_playbooks/paths.py",
            "playbooks/src/oep_playbooks/py.typed",
            "pyproject.toml",
            "replay/counterfactual_replay.v0.schema.json",
            "replay/scripts/check_counterfactual_replay.py",
            "replay/scripts/check_counterfactual_replay_schema.py",
            "replay/scripts/check_v03_features.py",
            "scripts/check_public_docs.py",
            "scripts/check_package_build.py",
            "scripts/sync_packaged_resources.py",
            "tests/test_verify_scripts.py",
            "tests/test_counterfactual_replay.py",
            "traces/pyproject.toml",
            "traces/scripts/check_eval_result.py",
            "traces/scripts/check_operational_trace.py",
            "traces/src/oep_traces/__init__.py",
            "traces/src/oep_traces/paths.py",
            "traces/src/oep_traces/py.typed",
            "translations/bedrock/README.md",
            "translations/bedrock/examples/code_review_bedrock_translation.v0.json",
            "translations/bedrock/layer_mapping.md",
            "translations/bedrock/runtime_mapping.md",
            "translations/bedrock/schema/bedrock_translation.v0.schema.json",
            "translations/bedrock/scripts/check_bedrock_translation.py",
            "translations/bedrock/source_notes.md",
            "uv.lock",
            *(artifact.canonical_path for artifact in PACKAGED_ARTIFACTS),
        }
    )
)
FORBIDDEN_SOURCE_DISTRIBUTION_FILES = (
    "demo/state/code_review_agent.coverage.sqlite",
    "demo/state/code_review_agent.sqlite",
    "integrations/decision-trace-reconstructor/code_review_agent.fragments.json",
)
FORBIDDEN_SOURCE_DISTRIBUTION_SUFFIXES = (
    ".coverage",
    ".db",
    ".db-shm",
    ".db-wal",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite-shm",
    ".sqlite-wal",
    ".sqlite3",
    ".sqlite3-shm",
    ".sqlite3-wal",
)


def packaged_resource_sync_errors(
    repo_root: Path,
    artifacts: Sequence[PackagedArtifact] = PACKAGED_ARTIFACTS,
) -> list[str]:
    errors: list[str] = []
    for artifact in artifacts:
        canonical = artifact.canonical_file(repo_root)
        packaged = artifact.packaged_file(repo_root)
        if not canonical.is_file():
            errors.append(f"missing canonical resource: {artifact.canonical_path}")
        elif not packaged.is_file():
            errors.append(f"missing packaged resource: {artifact.packaged_display_path}")
        elif canonical.read_bytes() != packaged.read_bytes():
            errors.append(
                f"packaged resource drift: {artifact.packaged_display_path} "
                f"differs from {artifact.canonical_path}"
            )

    return errors


__all__ = [
    "EXPECTED_PACKAGE_FILES",
    "FORBIDDEN_SOURCE_DISTRIBUTION_FILES",
    "FORBIDDEN_SOURCE_DISTRIBUTION_SUFFIXES",
    "PACKAGE_NAMES",
    "PACKAGE_RESOURCE_FILES",
    "PACKAGED_ARTIFACTS",
    "PY_TYPED_FILES",
    "SOURCE_DISTRIBUTION_FILES",
    "PackagedArtifact",
    "packaged_resource_sync_errors",
]
