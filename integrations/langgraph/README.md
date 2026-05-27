# LangGraph adapter

This directory ships an illustrative adapter that translates one
LangGraph checkpoint event (extended by a thin wrapper layer with the
operational evidence fields LangGraph does not natively bind) into an
Operational Evidence Plane (OEP) permission-trace record. It exists to
show one wiring pattern that demonstrates the distinction between two
different replay primitives, not to replace or wrap LangGraph.

The adapter is documentation and mapping data with a standalone Python
script. It does not call LangGraph, instantiate a StateGraph, or invoke
checkpointer backends.

## Two replay primitives

LangGraph documents what its checkpoint and time-travel features
provide. Per the
[time-travel documentation](https://docs.langchain.com/oss/python/langgraph/use-time-travel)
(accessed 2026-05-26): "Replay re-executes nodes — it doesn't just read
from cache. LLM calls, API requests, and interrupts fire again and may
return different results." Per the
[persistence documentation](https://docs.langchain.com/oss/python/langgraph/persistence):
"Nodes after the checkpoint re-execute, including any LLM calls, API
requests, or interrupts — which are always re-triggered during replay."

That is **checkpoint fork**: rerun the same graph from a checkpoint with
the same logical inputs and accept that external systems may return
different results each time. Excellent for branched development
exploration and execution recovery.

The OEP counterfactual replay primitive
([`replay/counterfactual_replay.v0.schema.json`](../../replay/counterfactual_replay.v0.schema.json))
solves a different question: given a stored decision, what would the
outcome have been if the policy bundle, the model version, the cache
state, or the scoped credential had been different? This requires
binding configuration surfaces to a stable decision identifier so the
replay can substitute one surface at a time and compare outputs.

The LangGraph `StateSnapshot` captures `values`, `next`, `metadata`,
`created_at`, and `parent_config`. It does not natively bind model
alias / resolved model version, policy bundle version, scoped credential
lifetime, cache hit metadata, or release manifest version. Those fields
have to be injected by a wrapper layer at checkpoint write time. This
adapter demonstrates one such wrapping pattern.

## Files

| File | Role |
|---|---|
| [`mapping.v0.yaml`](mapping.v0.yaml) | Field-by-field translation table from a synthetic LangGraph checkpoint envelope (extended with wrapper-injected operational evidence fields) to the OEP `tool_permission_packet.v0` schema, including v0.2 replayable-permission-trace fields and v0.3 `decision_id` metadata. Each row is labeled `langgraph_native` (captured by LangGraph at checkpoint time) or `wrapper_injected` (added by the wrapper at write time because LangGraph does not bind this field natively). |
| [`examples/code_review_langgraph_checkpoint.v0.json`](examples/code_review_langgraph_checkpoint.v0.json) | Synthetic LangGraph checkpoint event matching the deterministic code-review-agent demo. The values match what the demo records for `pder_code_review_read_diff_0001`. The `wrapper` section carries the fields LangGraph does not natively bind. |
| [`scripts/to_oep_permission.py`](scripts/to_oep_permission.py) | Standalone script that reads the synthetic envelope and emits the OEP permission packet JSON. Verifies that the emitted packet matches the committed canonical permission example for the allowed scenario. |

## What gets mapped

The synthetic LangGraph checkpoint envelope expresses one node
execution: a `read_diff` tool call that LangGraph's wrapping layer
records together with the operational evidence surfaces LangGraph itself
does not bind. The OEP packet records the OPA-backed permission
decision joined to release manifest, runtime event, and trace evidence.
The adapter mapping covers, among other things:

- `langgraph.state_snapshot.values.requested_action.name` -> `requested_action.name`
- `langgraph.state_snapshot.values.requested_action.input_ref` -> `requested_action.input_ref`
- `langgraph.state_snapshot.values.tool.name` -> `tool.name`
- `langgraph.state_snapshot.values.tool.version` -> `tool.version`
- `langgraph.state_snapshot.values.tool.operation` -> `tool.operation`
- `langgraph.state_snapshot.values.resource` -> `resource`
- `wrapper.actor` -> `actor`
- `wrapper.session.tool_call_id` -> `tool_call_id`
- `wrapper.session.event_id` -> `event_id`
- `wrapper.session.trace_id` -> `trace_id`
- `wrapper.session.span_id` -> `span_id`
- `wrapper.session.packet_id` -> `packet_id`
- `wrapper.session.decision_time` -> `decision_time`
- `wrapper.session.release_manifest_id` -> `release_manifest_id`
- `wrapper.session.scoped_credential_lifetime` -> `scoped_credential_lifetime`
- `wrapper.session.approval_capture` -> `approval_capture`
- `wrapper.session.policy_bundle_version` -> `policy_bundle_version`
- `wrapper.session.release_manifest_version` -> `release_manifest_version`
- `wrapper.session.model_binding.alias` -> `model_alias`
- `wrapper.session.model_binding.resolved_version` -> `resolved_model_version`
- `wrapper.session.model_binding.provider` -> `model_provider`
- `wrapper.policy_response.policy_ref` -> `policy`
- `wrapper.policy_response.decision` -> `decision`
- `wrapper.policy_response.links` -> `links`
- `wrapper.session.claim_boundary` -> `claim_boundary`
- `wrapper.session.decision_id` -> `decision_id`

See [`mapping.v0.yaml`](mapping.v0.yaml) for the full table including
the `langgraph_native` / `wrapper_injected` labels.

## Quickstart

```bash
# Regenerate the OEP permission packet projection from the LangGraph
# checkpoint envelope and check that it equals the committed canonical
# example.
python integrations/langgraph/scripts/to_oep_permission.py \
  --langgraph-event integrations/langgraph/examples/code_review_langgraph_checkpoint.v0.json \
  --compare-with permissions/examples/code_review_tool_permission.v0.json
```

The script exits non-zero if the projection drifts from the canonical
permission example. It is also wired into `make validate-langgraph`,
which is part of `make verify`.

## Boundary

The LangGraph adapter is illustration, not a replacement for LangGraph,
LangSmith, LangChain, OPA, OTel, Temporal, Restate, or any agent
framework. It demonstrates one inspectable way to wrap a LangGraph
checkpoint event with the operational evidence fields LangGraph does
not natively bind, so the v0.2 replay primitives
(`scoped_credential_lifetime`, `approval_capture`,
`policy_bundle_version`, `release_manifest_version`, `model_alias`,
`resolved_model_version`, `model_provider`) and the v0.3 `decision_id`
metadata surfaces (cost / drift / cache / identity) have a clear
source-side translation reference.

The point this adapter exists to make in code: LangGraph time-travel
re-executes nodes from a checkpoint with the same logical inputs. OEP
counterfactual replay substitutes a different policy bundle, model
version, cache state, or scoped credential against the same stored
decision and reports the diff. Both primitives are useful; they are not
the same primitive. The wrapper layer that emits this synthetic envelope
is what makes the second primitive possible on top of a LangGraph
runtime.

Other framework adapters (OpenAI Assistants, Bedrock) remain post-core
translation material.

## References

- LangGraph time-travel documentation (accessed 2026-05-26): <https://docs.langchain.com/oss/python/langgraph/use-time-travel>
- LangGraph persistence and checkpointing documentation (accessed 2026-05-26): <https://docs.langchain.com/oss/python/langgraph/persistence>
- LangGraph Python documentation root: <https://docs.langchain.com/oss/python/langgraph/>
- OEP counterfactual replay schema: [`../../replay/counterfactual_replay.v0.schema.json`](../../replay/counterfactual_replay.v0.schema.json)
- OEP tool permission packet schema: [`../../permissions/schema/tool_permission_packet.v0.schema.json`](../../permissions/schema/tool_permission_packet.v0.schema.json)
- OEP architecture walkthrough: [`../../docs/architecture.md`](../../docs/architecture.md)
- OEP decision log (v0.2 + v0.3 Decisions): [`../../docs/decision_log.md`](../../docs/decision_log.md)
- Public claim boundaries: [`../../docs/public_claims.md`](../../docs/public_claims.md)
- Companion MCP adapter (parallel pattern, JSON-RPC source instead of LangGraph): [`../mcp/README.md`](../mcp/README.md)
