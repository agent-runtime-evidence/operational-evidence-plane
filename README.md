# Operational Evidence Plane

> Vendor-neutral reference implementation for agent runtime evidence:
> release manifests, runtime events, permissioned tool calls, traces,
> and replay state for agentic workflows.

[![Verify](https://github.com/agent-runtime-evidence/operational-evidence-plane/actions/workflows/verify.yml/badge.svg)](https://github.com/agent-runtime-evidence/operational-evidence-plane/actions/workflows/verify.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20051037.svg?v=2)](https://doi.org/10.5281/zenodo.20051037)

Operational Evidence Plane makes agent behavior reconstructable after a release. It binds what was shipped (model, prompt, tool schema, policy, workflow, rollout, eval, and data-state references) to what happened at runtime (events, permission decisions, traces, replay state, eval results, and reconstruction packets).

Use it to inspect whether a runtime action can be joined back to a release manifest, verify policy decisions against trace and replay evidence, and package a minimal evidence chain that humans and CI can review without a vendor-specific control plane.

This repository is an open, vendor-neutral reference implementation. It extends patterns already visible in vendor-native agent versions, prompt registries, policy engines, and telemetry specs, but does not replace them and does not claim standardization or production readiness. The first demo target is a deterministic code-review agent using Python, SQLite, real OPA decisions, scenario-agnostic schemas, and mocked LLM behavior.

## Quickstart

Prerequisites:

- Python 3.11-3.14, matching the CI matrix
- OPA CLI 1.x, tested with 1.7.1.

OPA install examples:

```bash
# macOS, Homebrew
brew install opa

# Linux, x86_64
curl -L -o opa https://openpolicyagent.org/downloads/v1.7.1/opa_linux_amd64_static
chmod +x opa
sudo mv opa /usr/local/bin/opa
```

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install uv==0.11.10
uv sync --extra dev --locked
make verify
```

This compiles the packages, tests and evaluates the OPA policy, regenerates `demo/state/code_review_agent.sqlite`, checks every cross-artifact join, validates the deterministic eval, checks the reconstruction packet, and verifies the committed DTR JSONL projection.
It also builds the root wheel/sdist, installs the wheel in a temporary virtual environment, and checks that the installed packages keep their typing markers.

Smoke tests run through pytest:

```bash
make test
```

Coverage runs the full verify chain plus pytest and fails below 95%:

```bash
make coverage
```

Linting, type checking, policy tests, and artifact maintenance:

```bash
make lint
make typecheck
make test-policy
make build-check
make check-digests
make check-dtr-jsonl
make update-digests
```

Installed package entry points:

```bash
oep-verify-manifest
oep-run-demo --state-path /tmp/oep-code-review.sqlite
oep-check-reconstruction
```

To inspect generated replay state:

```bash
sqlite3 demo/state/code_review_agent.sqlite \
  "select 'events', count(*) from events union all select 'permissions', count(*) from permissions union all select 'traces', count(*) from traces union all select 'evals', count(*) from evals union all select 'findings', count(*) from findings;"
```

To reset generated state:

```bash
make clean-state
```

To isolate generated state for a test run:

```bash
OEP_DEMO_STATE_PATH=/tmp/oep-code-review.sqlite make verify
python demo/scripts/run_code_review_demo.py --state-path /tmp/oep-code-review.sqlite
```

For the fastest read, open these in order:

1. [Architecture walkthrough](docs/architecture.md)
2. [Release manifest example](manifest/examples/code_review_agent_release.v0.json)
3. [Agent-step event example](events/examples/code_review_agent_step.v0.json)
4. [Tool permission packet](permissions/examples/code_review_tool_permission.v0.json)
5. [Operational trace bundle](traces/examples/code_review_agent_trace.v0.json)
6. [Deterministic eval result](traces/examples/code_review_agent_eval.v0.json)
7. [Reconstruction packet](playbooks/examples/code_review_reconstruction_packet.v0.json)

## Docs

- [Architecture walkthrough](docs/architecture.md)
- [Decision log](docs/decision_log.md)
- [Public claims guide](docs/public_claims.md)
- [Contributing guide](CONTRIBUTING.md)
- [Bedrock translation](translations/bedrock/README.md)
- [Decision Trace Reconstructor integration](integrations/decision-trace-reconstructor/README.md)

## Current Artifacts

The release manifest is the first inspectable release-time layer:

- [Release manifest schema](manifest/schema/release_manifest.v0.schema.json)
- [Code-review-agent release example](manifest/examples/code_review_agent_release.v0.json)
- [Deterministic model-behavior contract](demo/model/deterministic_mock_reviewer.md)
- [Code-review prompt contract](demo/prompts/code_review_agent.md)
- [Rollback and reconstruction rules](playbooks/rollback_reconstruction.md)

The manifest schema binds eight release-time field groups: model, prompt, tool schema, policy, workflow, rollout, eval, and data state.

The event profile is the first runtime join layer:

- [Agent-step event schema](events/schema/agent_step_event.v0.schema.json)
- [Code-review-agent event example](events/examples/code_review_agent_step.v0.json)
- [Denied tool-call event example](events/examples/code_review_agent_denied_step.v0.json)

The event schema carries `release_manifest_id`, `trace_id`, `span_id`, `checkpoint`, `entity_ref`, `action_type`, `tool_call_id`, `permission_packet_ref`, `replay_handle`, and evidence-loss notes.

The permission packet is the first OPA-backed runtime evidence layer:

- [Tool permission packet schema](permissions/schema/tool_permission_packet.v0.schema.json)
- [Code-review tool permission example](permissions/examples/code_review_tool_permission.v0.json)
- [Denied write permission example](permissions/examples/code_review_tool_permission_denied.v0.json)
- [OPA policy](permissions/policy/tool_permissions.rego)
- [OPA input](permissions/policy/input/code_review_read_diff.json)
- [Denied OPA input](permissions/policy/input/code_review_write_diff.json)

The trace bundle is the first stitched reconstruction view:

- [Operational trace schema](traces/schema/operational_trace.v0.schema.json)
- [Code-review-agent trace bundle](traces/examples/code_review_agent_trace.v0.json)
- [Denied trace bundle](traces/examples/code_review_agent_denied_trace.v0.json)
- [Eval result schema](traces/schema/eval_result.v0.schema.json)
- [Code-review-agent eval result](traces/examples/code_review_agent_eval.v0.json)
- [Denied replay-readiness eval result](traces/examples/code_review_agent_denied_eval.v0.json)

The demo materializes local replay state:

- [Synthetic diff fixture](demo/fixtures/diff_synthetic_001.patch)
- [Replay-state recipe](demo/state/replay_state_recipe.md)
- [Deterministic demo runner](demo/src/oep_demo/runner.py)
- [Run script](demo/scripts/run_code_review_demo.py)
- [Replay-state checker](demo/scripts/check_replay_state.py)

`make verify` regenerates `demo/state/code_review_agent.sqlite` from the committed artifacts and checks that the committed DTR JSONL projection is up to date. The SQLite file is intentionally ignored; it is reproducible local state, not source.

The playbook packet is the first reconstruction output:

- [Reconstruction packet schema](playbooks/schema/reconstruction_packet.v0.schema.json)
- [Code-review reconstruction packet](playbooks/examples/code_review_reconstruction_packet.v0.json)
- [Denied blocked reconstruction packet](playbooks/examples/code_review_denied_reconstruction_packet.v0.json)
- [Scenario reconstruction checker](playbooks/scripts/check_reconstruction_packet.py)

The current inspectable chain is:

```text
release manifest -> agent-step event -> OPA-backed permission packet -> trace bundle -> SQLite replay state -> deterministic eval result -> reconstruction packet
```

The primary eval is a deterministic smoke check over one synthetic fixture. The denied path demonstrates blocked replay readiness when OPA denies a tool call and no SQLite replay state is generated. Neither is a benchmark, model-quality claim, safety certification, or production monitoring result.

## Claim Boundaries

- reference implementation, not framework
- not a vendor replacement
- not production-ready
- not a standardization proposal
- does not create compliance, audit readiness, or legal sufficiency by itself
- demonstrates one wiring pattern among several plausible ones
- designed for inspectability and education first

## Workspace Packages

The public Python distribution is the root package, `operational-evidence-plane`. The workspace directories below are source and development boundaries for the reference implementation; they are not independently published packages for `v0.1.0`.

| Package | Intended scope |
|---|---|
| `manifest/` | Release-time binding records for model, prompt, tool schema, policy, workflow, rollout, eval, and data-state references. |
| `events/` | Scenario-agnostic runtime event profile and replay join keys. |
| `permissions/` | Tool-call permission decision records backed by real OPA decisions. |
| `traces/` | Trace and span examples that connect release manifests, events, permissions, evals, and replay handles. |
| `playbooks/` | Rollback and incident reconstruction rules that explain what evidence is sufficient, missing, or stale. |
| `demo/` | Deterministic code-review-agent scenario using mocked LLM behavior and local SQLite state. |

## Substitute Landscape

| Surface | Useful precedent | Boundary for this repository |
|---|---|---|
| Bedrock 5+ layers | Bedrock agent versions and aliases visibly bind foundation model, instructions, prompt templates, action groups, and knowledge-base associations; memory, guardrail, and runtime or collaboration configuration exist on adjacent surfaces. | Treat Bedrock as a strong vendor-native alias precedent. Do not claim vendors only bind four layers or fewer. |
| Azure `azure-ai-projects` 2.1.0 | Azure AI Projects SDK consolidation gives a current Foundry project surface, with 2.1.0 as the verified version anchor from 2026-04-20. | Useful SDK/platform integration, but not a named cross-stack release manifest with runtime replay and incident joins. |
| Vertex | Vertex `ReasoningEngine` and related Google Cloud surfaces expose deployment, model, evaluation, memory, RAG/search, and IAM concepts across separate resources. | A partial resource-binding precedent, not a single vendor-neutral release/runtime evidence artifact. |
| LangSmith | LangSmith Deployment supports managed deployments and revisions; LangSmith prompts support commit history, staging / production environments, rollback, tags, and the public prompt hub. | Strong observability, deployment, and prompt-management precedent, but split from permission packet, replay protocol, and incident playbook scope. |
| OTel GenAI | OpenTelemetry GenAI semantic conventions describe runtime telemetry fields for generative AI systems. | Runtime telemetry substrate, not release management or cross-stack version binding. |
| MCP | Model Context Protocol defines tool and context communication patterns for agentic systems. | Runtime communication protocol, not a release manifest or incident reconstruction model. |
| A2A | Agent2Agent protocol defines inter-agent communication patterns. | Coordination protocol, not release-time binding, rollback, or replay evidence. |

## Prior Art

- Sovereign Agentic Loops: Decoupling AI Reasoning from Execution in Real-World Systems, arXiv:2604.22136, Jun He and Deying Yu, submitted 2026-04-24: [arxiv.org/abs/2604.22136](https://arxiv.org/abs/2604.22136).
  Paraphrased abstract: SAL argues that agents should not pass stochastic model outputs directly into mutating execution layers. It proposes a control-plane architecture where models emit structured intents with justifications, and those intents are validated against real system state and policy before execution, with evidence-chain support for audit and replay.
- Agent Control Protocol: Admission Control for Agent Actions, arXiv:2603.18829, Marcelo Fernandez, submitted 2026-03-19 and revised through v10 on 2026-04-30: [arxiv.org/abs/2603.18829](https://arxiv.org/abs/2603.18829).
  Paraphrased abstract: ACP addresses harmful behavior that can emerge across individually valid agent requests. It combines deterministic, history-aware admission control with static risk scoring and stateful signals such as anomaly accumulation and cooldown, so policy enforcement can account for execution traces rather than only isolated requests.

This repository treats SAL and ACP as legitimate prior conceptual work. The goal here is complementary engineering reference code and evidence wiring, not a competing theory or a claim of uniqueness.

## Adjacent Project Note

AgentReplay is an adjacent local-first desktop project for evals, observability, memory, and replay around agents and coding tools. It is not used as source code here: its desktop scope is different, and its AGPL-3.0 license is not compatible with this repository's permissive Apache-2.0 reuse boundary.

## What This Is NOT

This is not an agent framework, model gateway, tracing backend, policy language, compliance product, legal-audit package, vendor replacement, or production platform. It is also not a claim that adjacent vendor and open-source tools are absent. The safer claim is narrower: public artifacts mostly expose adjacent slices, and this repository demonstrates one inspectable way to stitch release-time and runtime evidence together.

## Reference Stack

- Language: Python.
- Demo model behavior: deterministic mocked LLM.
- Local state: SQLite.
- Policy decisions: real OPA.
- Demo scenario: code-review agent.
- Core schemas: scenario-agnostic first.
- Post-core translation: optional Bedrock-specific examples only after the vendor-neutral core exists.

## Post-Core Translation

The Bedrock translation lives under [translations/bedrock/](translations/bedrock/). It maps the vendor-neutral chain to Bedrock agent versions, aliases, action groups, prompt templates, memory/session state, and `InvokeAgent` trace references. It is documentation and mapping data only; it does not call AWS, deploy Bedrock resources, or make Bedrock the core implementation target.

## License

Apache-2.0
