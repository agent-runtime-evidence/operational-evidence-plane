# Bedrock Runtime Mapping

## InvokeAgent Join Points

Bedrock runtime calls use `InvokeAgent` against an agent runtime endpoint. The application supplies identifiers such as `agentId`, `agentAliasId`, `sessionId`, and request input. The examples in AWS documentation show `enableTrace=True` to receive trace information.

OEP runtime artifacts should keep application-side correlation IDs alongside Bedrock IDs:

| OEP field | Bedrock/application equivalent |
|---|---|
| `release_manifest_id` | Application-side manifest ID that records the Bedrock `agentId`, alias, and intended version context. |
| `trace_id` | Application-side trace/correlation ID plus Bedrock trace output from `InvokeAgent`. |
| `span_id` | Application-side span ID for a single step or action around Bedrock trace chunks. |
| `tool_call_id` | Application-side ID around a Bedrock action-group invocation or return-control flow. |
| `permission_packet_ref` | Application-side OPA/tool authorization packet. |
| `replay_handle` | Application-side replay state reference; Bedrock runtime traces alone are not treated as deterministic replay. |

## Session State

Bedrock session state can carry session attributes, prompt session attributes, conversation history, files, invocation IDs, and return-control invocation results. In OEP terms, those fields are data-state and runtime-context evidence. They are useful reconstruction inputs, but they do not replace an application-side replay packet.

## Alias and Rollback Boundary

Bedrock aliases point applications at agent versions. AWS documentation describes versions as immutable snapshots and aliases as a way to move between versions, including reverting to a previous version. OEP maps this to rollout evidence and rollback references, while keeping the cross-stack manifest outside Bedrock.
