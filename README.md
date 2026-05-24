# Operational Evidence Plane

> Vendor-neutral reference implementation for agent runtime evidence:
> release manifests, runtime events, permissioned tool calls, traces,
> and replay state for agentic workflows.

[![Verify](https://github.com/agent-runtime-evidence/operational-evidence-plane/actions/workflows/verify.yml/badge.svg)](https://github.com/agent-runtime-evidence/operational-evidence-plane/actions/workflows/verify.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20051036.svg)](https://doi.org/10.5281/zenodo.20051036)

Operational Evidence Plane is a small, runnable reference implementation for making agent runtime behavior reconstructable after release. It binds release-time intent (model, prompt, tool schema, policy, workflow, rollout, eval, and data-state references) to runtime evidence (events, OPA-backed permission decisions, traces, replay state, eval results, and reconstruction packets).

A quick scan should make three things clear: the repository is code, not a concept note (`make verify` rebuilds replay state and checks joins, including counterfactual replay determinism); it is vendor-neutral, not a replacement for Bedrock, LangSmith, OPA, OTel, MCP, A2A, cloud release tools, Styra DAS, or Permit.io; and it is intentionally bounded to a deterministic code-review demo using mocked LLM behavior, SQLite state, and real OPA decisions.

Use it to inspect whether a runtime action can be joined back to a release manifest, verify policy decisions against trace and replay evidence, replay a stored decision under a substituted policy bundle, and package a minimal evidence chain that humans and CI can review without a vendor-specific control plane.

This repository is an open, vendor-neutral reference implementation. It extends patterns already visible in vendor-native agent versions, prompt registries, policy engines, and telemetry specs, but does not replace them and does not claim standardization or production readiness. The first demo target is a deterministic code-review agent using Python, SQLite, real OPA decisions, scenario-agnostic schemas, and mocked LLM behavior.

## Evidence Chain

![Operational Evidence Plane evidence chain](docs/oep_evidence_chain.svg)

The inspectable path is intentionally narrow: a release manifest names the shipped configuration, runtime events and OPA-backed permission packets record what happened, trace and replay state preserve the joins, eval/reconstruction outputs show what can and cannot be reconstructed, and the v0.3 counterfactual branch composes policy, cost, drift, cache, and identity metadata under a stored decision id.

## Counterfactual Replay

The v0.3 branch adds counterfactual replay primitives over the stored decision record. Given a stored `decision_id`, the policy replay path reconstructs the recorded OPA input context from SQLite, substitutes a different policy bundle, re-runs OPA deterministically, and emits an original-vs-counterfactual decision diff that validates against [`replay/counterfactual_replay.v0.schema.json`](replay/counterfactual_replay.v0.schema.json). Additional v0.3 paths record cost, reserve, five-surface drift, cache, and identity metadata under the same decision id.

```bash
oep replay pder_code_review_read_diff_0001 \
  --counterfactual \
  --policy-bundle permissions/policy/counterfactual/compound_reliability_step_bound.rego \
  --output-format json \
  --replay-timestamp-utc 2026-05-23T00:00:00Z
```

`OEP_REPLAY_MODE=counterfactual` enables the same mode from the environment. `--replay-timestamp-utc` pins the otherwise excluded wall-clock replay timestamp when comparing CLI JSON byte-for-byte; `--strip-exclusions` removes fields listed in `replay_metadata.determinism_exclusions` before printing JSON/JSONL output. `make validate-counterfactual-replay` regenerates the three counterfactual demos; `make check-replay-determinism` checks byte-identical SQLite state, counterfactual JSON/JSONL, and DTR JSONL across runs.

The three demos all extend the existing deterministic code-review fixture:

- compound reliability: a 10-step workflow replayed under a stricter 4-step bounded policy;
- budget-per-run cross-over: a synthetic runaway loop replayed under a stricter budget cap;
- approval-per-step escalation: a workflow replayed under a stricter write-approval policy.

The v0.3 decision metadata is additive under `decision_id`: permission,
cost, five-surface drift, cache, and identity sub-objects can be recorded
under one decision without making old records invalid. See
[Schema migration v0.3](docs/schema_migration_v0.3.md) for the field list
and the backward-compatibility guarantee. The validation gates are exposed
as separate Make targets:

```bash
make validate-5surface-diff
make validate-cost-counterfactual
make validate-reserve-commit-release
make validate-cross-provider-drift
make validate-cache-substitution
make validate-identity-binding
make validate-composite
make validate-backward-compat
```

The composed CLI paths keep deterministic and evaluative replay separate:

```bash
oep diff pder_a pder_b --surface model,policy,prompt,tool,corpus
oep replay pder_code_review_read_diff_0001 \
  --substitute policy=permissions/policy/tool_permissions.rego \
  --substitute-budget per_run_cap_usd=0.005 \
  --substitute-model bedrock:anthropic.claude-opus-4-6 \
  --output-format json
oep reserve --budget-cap-usd 10 \
  --reservation bres_0001:6:4 \
  --reservation bres_0002:8:7
oep project --projected-cost-window 4:9 --budget-cap-usd 10 --approve
```

Policy, budget, reserve accounting, cache staleness, and config-surface
diffs are deterministic replays over recorded fields. Cross-provider model
substitution, cache substitution that implies a fresh model call, and
pre-session projection are labelled `replay_class: evaluative` and should
be read as counterfactual estimates.

Closest commercial precedents are [Styra DAS log-replay](https://docs.styra.com/das/observability-and-audit/decision-logs/log-replay) and [Permit.io Audit Log Replay](https://docs.permit.io/how-to/use-audit-logs/audit-log-replay). Both are useful authorization-domain precedents, but they are OPA/Rego-oriented, commercial-only products rather than an open-source, vendor-neutral, agent-runtime-decision-record-native reference implementation. The v0.3 branch demonstrates how the same replay shape can compose with agent runtime evidence records without claiming to replace those products.

[Srinivasan, "A Methodology for Selecting and Composing Runtime Architecture Patterns for Production LLM Agents"](https://arxiv.org/abs/2605.20173) (arXiv:2605.20173, 19 May 2026) is the Q2 2026 academic anchor for the Replay Divergence Problem: LLM-based consumers of deterministic logs can diverge under model-version or prompt changes. The v0.3 deterministic replay paths mitigate replay divergence for recorded policy, cost, cache-staleness, and config-surface fields. Cross-provider model substitution remains evaluative and does not re-execute the LLM call inside this reference implementation.

The Decision Evidence Maturity Model method specification that underlies the evidence-chain framing is my arXiv preprint at [arXiv:2605.04093](https://arxiv.org/abs/2605.04093) / DOI [`10.48550/arXiv.2605.04093`](https://doi.org/10.48550/arXiv.2605.04093). The v0.3 work implements deterministic policy, cost, reserve-accounting, cache-staleness, and five-surface config replay over recorded fields. Model substitution and cache substitution that implies a fresh model call are labelled evaluative estimates.

AAGATE ([arXiv:2510.25863](https://arxiv.org/abs/2510.25863)) is treated as complementary agent-governance work, not as a competitor. OEP's narrower scope is local evidence wiring and replay output over reference records. Reliability references such as Lusser's Law are used only as intuition for compounded workflow failure risk, not as empirical reliability proof for this repository.

Boundary: this is not a production-grade replay engine, not a compliance certification, not a substitute for vendor authorization-replay products, and does not constitute legal or regulatory adequacy by itself.

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

If OPA is available outside `PATH`, set `OEP_OPA_BIN_PATH=/path/to/opa`.
`OPA_PATH` is also accepted as a fallback override.
Set `OEP_OPA_EVAL_TIMEOUT_SECONDS` to tune the counterfactual OPA
subprocess timeout in seconds; the default is `30` and the minimum is
`0.001`. OPA stdin payloads are capped at 8 MiB; split larger replay
batches before evaluation.
Set `OEP_OPA_COMMAND_WRAPPER` to prepend a local containment command
to OPA invocations, for example `prlimit --as=100000000` in CI
environments that evaluate substituted policy bundles. The wrapper
executable is restricted to `docker`, `nice`, `prlimit`, or `sudo`.
The executable must resolve from `PATH` to a trusted system or local tool
directory such as `/usr/bin`, `/bin`, `/usr/sbin`, `/sbin`,
`/usr/local/bin`, or `/opt/homebrew/bin`.
Wrapper arguments are restricted to allow-listed options and strict
values for the selected wrapper; positional alternate binary targets are
rejected. Docker wrappers must use `docker run`, must include `--init`,
and may only use a constrained option set such as `--rm`,
`--network none`, `--user`, `--cpus`, `--memory`, `--pids-limit`,
`--read-only`, and read-only `-v` / `--volume` bind mounts in
`host_path:container_path:ro` form. When a
read-only bind mount contains the policy bundle path, OEP rewrites the
OPA `--data` argument to the corresponding container path.
Wrappers must keep the OPA child in the spawned process group
or forward termination signals so timeout cleanup can stop the full
evaluation tree.
Set `OEP_SQLITE_BATCH_VARIABLE_LIMIT` to raise the replay reader batch
limit above the default `900` on modern SQLite builds; values must stay
between `1` and `32766`.
The reference implementation invokes OPA through the CLI for each replay
batch. Higher-volume deployments can preserve the same deterministic
input/output contract while routing evaluation through a local OPA server
or a WASM runtime.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install uv==0.11.10
uv sync --extra dev --locked
make verify
```

This compiles the packages, tests and evaluates the OPA policy, validates the counterfactual replay schema, regenerates `demo/state/code_review_agent.sqlite`, checks every cross-artifact join, validates the deterministic eval, checks the reconstruction packet, verifies the committed DTR JSONL projection, checks the MCP -> OEP permission packet projection, exercises the `oep replay` reader against generated replay state, and checks counterfactual replay determinism across generated SQLite, JSON/JSONL, and DTR outputs.
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
make sync-resources
make build-check
make check-digests
make check-dtr-jsonl
make validate-counterfactual-replay
make check-replay-determinism
make update-digests
```

Installed package entry points:

```bash
oep-verify-manifest
oep-run-demo --state-path /tmp/oep-code-review.sqlite
oep-check-reconstruction
oep replay pder_code_review_read_diff_0001
OEP_REPLAY_MODE=counterfactual oep replay pder_code_review_read_diff_0001 --policy-bundle permissions/policy/counterfactual/compound_reliability_step_bound.rego
```

`oep replay <decision_id>` is a read-only reader over the local SQLite
replay store. It joins the recorded permission packet, agent-step event,
trace bundle, and release-manifest summary for a recorded decision id.
It does not make live model or vendor calls.

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
- [Schema migration v0.3](docs/schema_migration_v0.3.md)
- [Public claims guide](docs/public_claims.md)
- [Contributing guide](CONTRIBUTING.md)
- [Bedrock translation](translations/bedrock/README.md)
- [Decision Trace Reconstructor integration](integrations/decision-trace-reconstructor/README.md)
- [Model Context Protocol (MCP) adapter](integrations/mcp/README.md)

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
- [Counterfactual replay output schema](replay/counterfactual_replay.v0.schema.json)
- [Compound reliability counterfactual policy](permissions/policy/counterfactual/compound_reliability_step_bound.rego)
- [Budget-per-run counterfactual policy](permissions/policy/counterfactual/budget_per_run_cap.rego)
- [Approval-per-step counterfactual policy](permissions/policy/counterfactual/approval_per_step_escalation.rego)
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
- [Counterfactual demo runner](demo/src/oep_demo/counterfactual.py)
- [Run script](demo/scripts/run_code_review_demo.py)
- [Replay-state checker](demo/scripts/check_replay_state.py)
- [Counterfactual replay checker](replay/scripts/check_counterfactual_replay.py)

`make verify` regenerates `demo/state/code_review_agent.sqlite` from the committed artifacts, checks that the committed DTR JSONL projection is up to date, and runs the counterfactual replay determinism checks. SQLite files and generated counterfactual JSON/JSONL outputs under `demo/counterfactual/` are intentionally ignored; they are reproducible local state, not source.

The playbook packet is the first reconstruction output:

- [Reconstruction packet schema](playbooks/schema/reconstruction_packet.v0.schema.json)
- [Code-review reconstruction packet](playbooks/examples/code_review_reconstruction_packet.v0.json)
- [Denied blocked reconstruction packet](playbooks/examples/code_review_denied_reconstruction_packet.v0.json)
- [Scenario reconstruction checker](playbooks/scripts/check_reconstruction_packet.py)

The current inspectable chain is:

```text
release manifest -> agent-step event -> OPA-backed permission packet -> trace bundle -> SQLite replay state -> deterministic eval result -> reconstruction packet
```

The v0.3 counterfactual branch starts from the stored permission decision and replay state, substitutes policy, budget, model, cache, or config-surface inputs, and emits schema-validated attribution output. Deterministic surfaces replay over recorded fields; model and cache-fresh-call substitutions are labelled evaluative estimates. The primary eval is a deterministic smoke check over one synthetic fixture. The denied path demonstrates blocked replay readiness when OPA denies a tool call and no SQLite replay state is generated. Neither is a benchmark, model-quality claim, safety certification, or production monitoring result.

## Replayable Permission Trace Fields (v0.2)

The v0.2 release extends the OPA-backed permission packet with optional
replayable permission trace fields. These fields are additive: v0.1
records that omit them still validate. The deterministic code-review
demo populates them so the v0.2 reproducibility walkthrough can show the
new primitives in use.

| Field | Description |
|---|---|
| `tool_call_id` | Identifier for the tool invocation event (also present in v0.1). |
| `scoped_credential_lifetime` | ISO 8601 time-to-live of the scoped credential used at the call (for example `PT15M`). |
| `approval_capture` | Captured human approval (if required), including approver identity, captured-at timestamp, and approval type. `null` when no human approval was required. |
| `policy_bundle_version` | `sha256:` hash of the policy bundle in effect at the call. Matches the release manifest's policy layer digest. |
| `release_manifest_version` | `sha256:` hash of the release manifest in effect at the call. |
| `model_alias` | Model alias as called by the agent (for example `claude-sonnet-4-6`). |
| `resolved_model_version` | Resolved underlying model version at call time. |
| `model_provider` | Provider of the model (for example `anthropic`, `openai`, `google`). |
| `nd_builtin_cache` | Optional replay cache for non-deterministic OPA builtin results such as time or HTTP lookups. `null` or omitted when no non-deterministic builtin capture is needed. |

The `model_*` fields are recorded because API providers can change
underlying model behavior under unchanged aliases. Recording the
resolved version and provider at call time keeps replay records stable
across silent provider-side model changes. This is a record-keeping
addition, not a model-quality claim.

The v0.2 fields are joined by the stable `pder_*` decision id (the
`packet_id` value) and the `replay_handle` primitives carried by the
v0.1 chain.

## Record-Keeping Reference Table

The table below maps OEP record fields to record-keeping requirements
named in well-known frameworks. It illustrates which event fields the
requirements describe; it is documentation and education, not a
compliance or audit claim. The repository does not create compliance,
audit readiness, or legal sufficiency by itself — see [the public
claims guide](docs/public_claims.md) §Required Boundaries.

| OEP record field | EU AI Act event field cited | NIST AI RMF 1.0 function |
|---|---|---|
| `decision_id` + per-event timestamps | Article 12 (Record-keeping) | MEASURE function records |
| `policy_bundle_version` + `release_manifest_version` | Article 13 (Transparency and provision of information to deployers) | MEASURE function records |
| `approval_capture` (human-in-the-loop) | Article 14 (Human oversight) | MANAGE function records |
| Retention notes in README (not code) | Article 18 (Documentation keeping) | GOVERN function records |
| Replay trace as runtime evidence | Article 26(5) (deployer operational monitoring obligation) | MEASURE function records |

NIST AI RMF function-citation specificity is intentionally kept at the
four canonical function names (GOVERN / MAP / MEASURE / MANAGE) without
sub-function commitment. The NIST AI Risk Management Framework primary
source is version 1.0, released January 2023; the Generative AI Profile
(NIST AI 600-1, July 2024) is a separate companion document and is not
versioned as "1.1". Article numbers and titles refer to Regulation (EU)
2024/1689 (the EU AI Act). The table is reference material, not a
binding mapping.

The v0.3 planning notes also track an education-only EU AI Act timing
view for Articles 19, 26(6), 50, and 73. The source baseline is the
European Commission AI Act timeline and FAQ plus the Council/Parliament
Digital Omnibus political agreement announced on 7 May 2026; formal legal
texts remain the controlling source.

| Article | OEP-adjacent record topic | Timing note |
|---|---|---|
| 19 | Provider conformity-assessment evidence for high-risk systems | High-risk application dates are affected by the Digital Omnibus political agreement; planning notes should distinguish stand-alone and product-embedded high-risk systems. |
| 26(6) | Deployer log/evidence retention for high-risk use | Treat as high-risk-system planning material, not as an OEP compliance assertion. |
| 50 | Transparency records for AI-generated or AI-interaction disclosures | Transparency obligations are tracked separately from high-risk timing; some Article 50 timing details were addressed in the Digital Omnibus agreement. |
| 73 | Serious-incident reporting evidence | Incident evidence examples here are educational only and do not implement statutory reporting. |

Sources for the timing notes: [European Commission AI Act timeline](https://ai-act-service-desk.ec.europa.eu/en/ai-act/timeline/timeline-implementation-eu-ai-act), [European Commission AI Act FAQ](https://ai-act-service-desk.ec.europa.eu/en/faq), and [Council press release, 7 May 2026](https://www.consilium.europa.eu/en/press/press-releases/2026/05/07/artificial-intelligence-council-and-parliament-agree-to-simplify-and-streamline-rules/).

**Retention.** This repository is a reference implementation. It does
not retain runtime records on behalf of any deployer. Operators that
choose to reuse the schemas are responsible for record retention,
storage, access controls, and any legal requirements that apply to
their deployment context.

## Replay CLI

```bash
oep replay <decision_id>
oep replay <decision_id> --counterfactual --policy-bundle <path-to-rego-bundle>
```

`oep replay` is a thin read-only reader over the local SQLite replay
store generated by `oep-run-demo` or `make verify`. It reconstructs the
recorded permission trace for a decision id (the `pder_*` packet
identifier) by joining the recorded permission packet, agent-step
event, trace bundle, and release-manifest summary.

The demo runner materializes SQLite state at a temporary path and publishes
the completed database with an atomic replace. Existing replay readers keep
their current file handle; new readers open the completed replacement.

- The CLI does not make live model or vendor API calls.
- It does not introduce new persistence; it only reads existing rows.
- Pass `--state-path` to read from an alternate SQLite path, or set
  `OEP_DEMO_STATE_PATH` before running the demo.
- Pass `--field <name>` to print a specific record field instead of the
  full JSON record.
- Pass `--counterfactual --policy-bundle <path>` to re-derive the
  decision under a substituted policy bundle. `OEP_REPLAY_MODE` accepts
  `read-only` (default) or `counterfactual`.
- Pass `--output-format json`, `jsonl`, or `human`. Read-only replay
  defaults to JSON; counterfactual replay defaults to human output.
- Pass `--replay-timestamp-utc <date-time>` in counterfactual mode when
  CLI JSON must be compared byte-for-byte.
- Pass `--strip-exclusions` in counterfactual JSON/JSONL mode to remove
  fields listed in `replay_metadata.determinism_exclusions` before output.

## MCP Adapter

The [`integrations/mcp/`](integrations/mcp/) directory ships an
illustrative adapter that translates one Model Context Protocol
(MCP) `tools/call` envelope into an OEP permission packet, including
the v0.2 replayable permission trace fields. It is documentation and
mapping data with a standalone script — it does not call MCP servers
or vendor APIs.

The adapter is illustration, not a replacement for MCP, LangSmith,
Bedrock, OTel, A2A, or OPA. Other framework adapters (LangGraph,
OpenAI Assistants, Bedrock) remain post-core translation material.

## Claim Boundaries

- reference implementation, not framework
- not a vendor replacement
- not ready for production use
- not a production-grade replay engine
- not a standardization proposal
- not a compliance certification
- not a substitute for vendor authorization-replay products
- does not create compliance, audit readiness, or legal sufficiency by itself
- does not constitute legal or regulatory adequacy by itself
- demonstrates one wiring pattern among several plausible ones
- designed for inspectability and education first

## Workspace Packages

The public Python distribution is the root package, `operational-evidence-plane`. The workspace directories below are source and development boundaries for the reference implementation; they are not independently published packages for this release line.

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
| Styra DAS / Permit.io | Authorization-domain log replay re-evaluates historical OPA/Rego decisions against changed policy or data. | Closest commercial replay precedent, but not an agent-runtime decision-record chain and not a product this repository replaces. |
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

This is not an agent framework, model gateway, tracing backend, policy language, compliance product, legal-audit package, vendor replacement, production platform, production-grade replay engine, compliance certification, or substitute for vendor authorization-replay products. It does not constitute legal or regulatory adequacy by itself. It is also not a claim that adjacent vendor and open-source tools are absent. The safer claim is narrower: public artifacts mostly expose adjacent slices, and this repository demonstrates one inspectable way to stitch release-time and runtime evidence together.

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
