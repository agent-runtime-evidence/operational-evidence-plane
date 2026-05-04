# Rollback and Reconstruction Rules

These rules define the minimum evidence needed to understand what release was intended to run, what runtime action happened, and whether a local deterministic replay can be attempted. They are engineering reference rules, not an audit guarantee or production incident standard.

## Evidence Status

Use these statuses consistently in release manifests and later runtime artifacts:

| Status | Meaning | Reconstruction effect |
|---|---|---|
| `resolved` | The artifact exists and has a stable URI plus digest. | Can be used for replay or deterministic comparison. |
| `declared` | The artifact is named and scoped, but the file, digest, or implementation is not materialized yet. | Can explain intended design, but is not replay-ready. |
| `external` | The artifact exists outside this repository. | Can support reconstruction only if the external reference remains available and versioned. |
| `missing` | The artifact was expected but cannot be identified. | Treat the affected layer as evidence loss. |

## Minimum Release Reconstruction

A runtime action is release-reconstructable only when it can be joined to a release manifest by `release_manifest_id` and the manifest identifies all eight layer groups:

- model
- prompt
- tool schema
- policy
- workflow
- rollout
- eval
- data state

If one of these groups is `declared`, reconstruction may describe intent but must not claim replay readiness. If one of these groups is `missing`, the incident or debug packet must include an evidence-loss note.

## Runtime Join Order

Reconstruct an action in this order:

1. Resolve `runtime_event.release_manifest_id` to a release manifest.
2. Resolve the manifest's layer bindings.
3. Join `trace_id` and `span_id` to place the action in an execution trace.
4. Join `tool_call_id` to the permission packet for tool actions.
5. Resolve `replay_handle` to deterministic local state where replay is claimed.
6. Attach rollout and eval state before making safety or regression claims.

Do not skip directly from trace logs to conclusions about model behavior, policy behavior, or rollout safety. Each claim needs the relevant layer binding.

## Rollback Readiness

A rollback candidate is usable only when:

- the current runtime event identifies the current manifest;
- the previous manifest is available and not marked `missing`;
- policy and tool-schema bindings are compatible with the workflow being rolled back;
- data-state compatibility is known, or the rollback record explicitly says the state cannot be reconstructed;
- eval and rollout bindings describe why the rollback candidate is acceptable.

If policy, tool schema, workflow, or release identity is missing, fail closed: do not claim safe rollback. The reference demo may still show a diagnostic explanation, but it must label the missing evidence.

## Replay Readiness

Replay-ready means:

- all eight release layer bindings are `resolved`;
- runtime events include `release_manifest_id`, `trace_id`, `span_id`, and checkpoint fields;
- tool actions include `tool_call_id` and a permission packet reference;
- deterministic mocked model behavior is bound by version and digest;
- the data-state recipe is bound by digest and generated SQLite reconstruction state has a stable replay handle;
- eval and rollout state can be attached to the reconstructed action.

Anything less is inspectable evidence, not deterministic replay.

## Claim Boundary

These rules demonstrate one wiring pattern for release-time and runtime evidence. They do not define a standard incident format, replace OPA or observability tools, establish legal sufficiency, or prove that vendor-native release/version tools are absent.
