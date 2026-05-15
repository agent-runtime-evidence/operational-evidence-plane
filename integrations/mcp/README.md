# Model Context Protocol (MCP) adapter

This directory ships an illustrative adapter that translates one MCP
tool-call event into an Operational Evidence Plane (OEP) permission-trace
record. It is part of the v0.2 scope item «one framework integration for
MCP» and exists to show one wiring pattern, not to replace or wrap MCP.

The adapter is documentation and mapping data with a standalone Python
script. It does not call MCP servers, network endpoints, or vendor APIs.

## Files

| File | Role |
|---|---|
| [`mapping.v0.yaml`](mapping.v0.yaml) | Field-by-field translation table from a synthetic MCP `tools/call` event envelope to the OEP `tool_permission_packet.v0` schema, including the v0.2 replayable-permission-trace fields. |
| [`examples/code_review_mcp_tool_call.v0.json`](examples/code_review_mcp_tool_call.v0.json) | Synthetic MCP tool-call event matching the deterministic code-review-agent demo. The values match what the demo records for `pder_code_review_read_diff_0001`. |
| [`scripts/to_oep_permission.py`](scripts/to_oep_permission.py) | Standalone script that reads the synthetic MCP envelope and emits the OEP permission packet JSON. Verifies that the emitted packet matches the committed canonical permission example for the allowed scenario. |

## What gets mapped

The MCP transport layer is JSON-RPC 2.0; a `tools/call` request carries
a tool name and arguments, and the server returns a result envelope. The
OEP permission packet records the OPA-backed permission decision joined
to release manifest, runtime event, and trace evidence. The adapter
mapping covers:

- `request.params.name` -> `tool.name`
- `request.params.arguments` -> `requested_action.input_ref` (string or dict; the script accepts either)
- `request.params.resource` -> `resource`
- `request.id` -> `tool_call_id`
- `actor` -> `actor`
- `session.policy_bundle_version` -> `policy_bundle_version`
- `session.release_manifest_version` -> `release_manifest_version`
- `session.scoped_credential_lifetime` -> `scoped_credential_lifetime`
- `session.approval_capture` -> `approval_capture`
- `session.model_binding.alias` -> `model_alias`
- `session.model_binding.resolved_version` -> `resolved_model_version`
- `session.model_binding.provider` -> `model_provider`

See [`mapping.v0.yaml`](mapping.v0.yaml) for the full table.

## Quickstart

```bash
# Regenerate the OEP permission packet projection from the MCP envelope
# and check that it equals the committed canonical example.
python integrations/mcp/scripts/to_oep_permission.py \
  --mcp-event integrations/mcp/examples/code_review_mcp_tool_call.v0.json \
  --compare-with permissions/examples/code_review_tool_permission.v0.json
```

The script exits non-zero if the projection drifts from the canonical
permission example. It is also wired into `make validate-mcp`, which is
part of `make verify`.

## Boundary

The MCP adapter is illustration, not a replacement for MCP, LangSmith,
Bedrock, OTel, A2A, or OPA. It demonstrates one inspectable way to map
an MCP-style tool-call envelope into the OEP permission packet record so
that the v0.2 replay primitives (`scoped_credential_lifetime`,
`approval_capture`, `policy_bundle_version`, `release_manifest_version`,
`model_alias`, `resolved_model_version`, `model_provider`) have a clear
source-side translation reference.

Other framework adapters (LangGraph, OpenAI Assistants, Bedrock) remain
post-core translation material and are out of v0.2 scope.

## References

- Model Context Protocol specification: <https://modelcontextprotocol.io/>
- OEP architecture walkthrough: [`../../docs/architecture.md`](../../docs/architecture.md)
- OEP decision log (v0.2 Decisions): [`../../docs/decision_log.md`](../../docs/decision_log.md)
- Public claim boundaries: [`../../docs/public_claims.md`](../../docs/public_claims.md)
