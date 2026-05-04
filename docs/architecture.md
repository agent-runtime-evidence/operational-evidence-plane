# Architecture Walkthrough

This repository demonstrates one source-inspectable operational-evidence chain for a deterministic code-review agent. The chain is deliberately small:

```text
release manifest -> agent-step event -> OPA-backed permission packet -> trace bundle -> SQLite replay state -> deterministic eval result -> reconstruction packet
```

## What Runs

`make verify` runs the full verification chain:

1. Compiles all Python packages.
2. Checks the release manifest.
3. Checks the agent-step event joins to the manifest.
4. Executes `opa eval` and checks the permission packet against the policy result.
5. Runs the deterministic demo and regenerates SQLite replay state.
6. Checks the deterministic eval result against generated state.
7. Checks the trace bundle against all upstream artifacts.
8. Checks the reconstruction packet against all upstream artifacts and SQLite state.

The generated SQLite file is `demo/state/code_review_agent.sqlite`. It is intentionally ignored because it is reproducible local state.

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

## Evidence Boundary

The demo is replay-ready only for this synthetic fixture and deterministic mocked behavior. It does not prove production readiness, universal replay semantics, compliance sufficiency, or model quality.
