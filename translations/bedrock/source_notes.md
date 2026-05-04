# Bedrock Source Notes

Sources checked: 2026-05-04.

Sources used:

- [Automate tasks in your application using AI agents](https://docs.aws.amazon.com/bedrock/latest/userguide/agents.html)
- [Deploy an agent](https://docs.aws.amazon.com/bedrock/latest/userguide/deploy-agent.html)
- [Enhance agent accuracy using advanced prompt templates](https://docs.aws.amazon.com/bedrock/latest/userguide/advanced-prompts.html)
- [Invoke an agent from your application](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-invoke-agent.html)
- [Control agent session context](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-session-state.html)
- [Enable agent memory](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-configure-memory.html)

## Source-Safe Facts

- Bedrock Agents can use action groups, knowledge bases, prompt templates, traces, versions, and aliases.
- Bedrock creates agent versions and uses aliases to point applications at versions.
- AWS documentation describes versions as immutable snapshots and aliases as a way to move between versions.
- `InvokeAgent` can use `agentId`, `agentAliasId`, `sessionId`, and trace enablement in runtime calls.
- Session state can carry session attributes, prompt session attributes, conversation history, files, invocation IDs, and return-control invocation results.
- Agent memory can be enabled/configured and is a managed Bedrock state surface.

## Translation Boundary

These sources support a Bedrock mapping, not a claim that Bedrock lacks versioning, trace, memory, guardrail, action-group, knowledge-base, or prompt-template features.
