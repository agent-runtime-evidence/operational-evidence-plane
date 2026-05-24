# Architecture Walkthrough

This repository demonstrates one source-inspectable operational-evidence chain for a deterministic code-review agent. The main chain is deliberately small:

```text
release manifest -> agent-step event -> OPA-backed permission packet -> trace bundle -> SQLite replay state -> deterministic eval result -> reconstruction packet
```

The unreleased v0.3 branch adds a counterfactual path from the stored permission decision:

```text
stored decision record + substituted policy bundle -> OPA re-evaluation -> original-vs-counterfactual decision diff
```

## What Runs

`make verify` runs the full verification chain:

1. Compiles all Python packages.
2. Checks the release manifest.
3. Checks the agent-step event joins to the manifest.
4. Executes `opa eval` and checks the permission packet against the policy result.
5. Validates the counterfactual replay output schema.
6. Runs the deterministic demo and regenerates SQLite replay state.
7. Checks the deterministic eval result against generated state.
8. Checks the trace bundle against all upstream artifacts.
9. Checks the reconstruction packet against all upstream artifacts and SQLite state.
10. Runs counterfactual replay validation and byte-identical determinism checks across the three counterfactual demos.

The generated SQLite file is `demo/state/code_review_agent.sqlite`. Counterfactual replay outputs are generated under `demo/counterfactual/`. They are intentionally ignored because they are reproducible local state and output artifacts.

## Artifact Map

| Layer | File | Role |
|---|---|---|
| Release manifest | `manifest/examples/code_review_agent_release.v0.json` | Binds model, prompt, tool schema, policy, workflow, rollout, eval, and data-state references. |
| Model behavior | `demo/model/deterministic_mock_reviewer.md` | Records the deterministic mocked-reviewer contract used instead of a live LLM. |
| Prompt contract | `demo/prompts/code_review_agent.md` | Records the narrow review instruction and output contract for the reference scenario. |
| Runtime event | `events/examples/code_review_agent_step.v0.json` | Carries `release_manifest_id`, trace/span IDs, checkpoint, `tool_call_id`, permission reference, and replay handle. |
| Permission packet | `permissions/examples/code_review_tool_permission.v0.json` | Records the OPA-backed allow decision for the synthetic `read_diff` tool call. |
| Trace bundle | `traces/examples/code_review_agent_trace.v0.json` | Stitches manifest, event, permission, replay, and eval evidence into one trace view. |
| Replay state recipe | `demo/state/replay_state_recipe.md` | Source artifact that describes how generated replay state is produced and checked. |
| Replay state | `demo/state/code_review_agent.sqlite` | Generated state containing event, permission, trace, eval, and finding rows. |
| Eval result | `traces/examples/code_review_agent_eval.v0.json` | Deterministic smoke eval over one synthetic fixture and the generated state. |
| Reconstruction packet | `playbooks/examples/code_review_reconstruction_packet.v0.json` | Final inspectable summary of reconstruction readiness and remaining limitations. |
| Counterfactual replay schema | `replay/counterfactual_replay.v0.schema.json` | Output contract for original-vs-counterfactual decision diffs. |
| Counterfactual policy bundles | `permissions/policy/counterfactual/*.rego` | Alternative OPA policies applied retroactively to stored decision records. |
| Counterfactual demo runner | `demo/src/oep_demo/counterfactual.py` | Generates the compound reliability, budget-per-run, and approval escalation demos over the same code-review fixture. |
| Counterfactual checker | `replay/scripts/check_counterfactual_replay.py` | Validates the demo outputs and checks byte-identical determinism across runs. |

## Join Keys

| Key | Example | Used by |
|---|---|---|
| `release_manifest_id` | `rmf_code_review_agent_2026_05_04_v0` | Manifest, event, permission packet, trace, eval, reconstruction packet. |
| `trace_id` | `11111111111111111111111111111111` | Event, permission packet, trace, eval, SQLite state. |
| `span_id` | `2222222222222222` | Event, permission packet, trace span. |
| `tool_call_id` | `tool_read_diff_0001` | Event, permission packet, trace span, reconstruction packet. |
| `permission_packet_ref` | `pder_code_review_read_diff_0001` | Event to permission packet join. |
| `replay_handle` | `replay_code_review_agent_0001` | Event and trace to SQLite state. |
| `eval_id` | `eval_code_review_agent_smoke_0001` | Trace, eval result, SQLite state, reconstruction packet. |
| `policy_bundle_version` | `sha256:e0d556...` | Original permission packet and counterfactual diff snapshots. |

## Counterfactual Policy Replay

The counterfactual replay operation starts from a stored v0.2 decision record. `counterfactual_replay_decision(...)` reconstructs the OPA input context from SQLite, injects any captured `nd_builtin_cache`, evaluates a substituted Rego policy bundle with `opa eval`, and returns a schema-validated record containing:

- the original decision snapshot;
- the counterfactual decision snapshot;
- rule-set, workflow, budget, or approval deltas when the demo attaches them;
- replay metadata, including `OEP_REPLAY_MODE=counterfactual` and the explicitly excluded wall-clock timestamp field.

The replay operation reads the existing SQLite store. It does not mutate replay state, call a live model, call a vendor API, or substitute model weights.

OPA is executed as a local subprocess with a bounded timeout. This reference
does not impose portable OS-level memory or CPU-quota limits on the `opa`
process; environments evaluating untrusted substituted policies should run OPA
behind their own containment wrapper, such as `ulimit`, `prlimit`, or an
equivalent container policy.

The three counterfactual demos are scenario-agnostic extensions of the existing code-review fixture:

| Demo | Stored workflow | Substituted policy | Expected counterfactual observation |
|---|---|---|---|
| Compound reliability | 10 deterministic code-review steps | 4-step bounded policy | Step 5 is denied; the original workflow succeeds and the counterfactual workflow fails. |
| Budget-per-run cross-over | 47-step synthetic runaway loop | Stricter `$5000` budget cap | Step 6 is denied with `BUDGET_EXCEEDED`; counterfactual total stops at `$5000`. |
| Approval-per-step escalation | Six-step review workflow with write steps | Every write operation requires human approval | Steps 2, 4, and 5 require additional approval. |

`make validate-counterfactual-replay` runs these demos and validates the output schema. `make check-replay-determinism` runs the demos multiple times and compares SQLite state, counterfactual JSON/JSONL, and DTR JSONL bytes across runs.

Custom counterfactual policy bundles must expose the standard rule contract at
`data.oep.permissions.decision`. OEP evaluates that fixed entry point for
subprocess safety; hyphenated or symbol-bearing package names should be adapted
behind a compatible wrapper rule that exports the standard path.

Counterfactual replay is a static decision-record analysis, not an
active re-simulation of the agent trajectory. When a substituted policy
changes the decision at step `N`, later stored steps `> N` may no longer
represent a coherent execution path under the counterfactual policy. The
budget-per-run demo therefore reports the first divergent/termination
step and treats later OPA evaluations as hypothetical slices over the
original recorded context, not as evidence that those later actions
would have occurred after the counterfactual denial.

The closest commercial precedents are [Styra DAS log-replay](https://docs.styra.com/das/observability-and-audit/decision-logs/log-replay) and [Permit.io Audit Log Replay](https://docs.permit.io/how-to/use-audit-logs/audit-log-replay). OEP uses them as OPA/Rego-oriented, commercial-only authorization-domain precedents, not as products to replace. [Srinivasan, "A Methodology for Selecting and Composing Runtime Architecture Patterns for Production LLM Agents"](https://arxiv.org/abs/2605.20173) names replay divergence as a failure mode for LLM consumers of deterministic logs; the unreleased v0.3 branch demonstrates one policy-substitution mitigation surface inside this repository's bounded evidence chain.

## Evidence Boundary

The demo is replay-ready only for this synthetic fixture and deterministic mocked behavior. Counterfactual replay is not a production-grade replay engine, not a compliance certification, not a substitute for vendor authorization-replay products, and does not constitute legal or regulatory adequacy by itself.
