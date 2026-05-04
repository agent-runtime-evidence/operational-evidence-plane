# Bedrock Layer Mapping

| OEP layer | Bedrock surface | Translation status | Boundary |
|---|---|---|---|
| `model` | Agent foundation model configuration. | Native Bedrock surface. | OEP records the intended model binding; Bedrock remains the model runtime owner. |
| `prompt` | Agent instructions and advanced prompt templates for pre-processing, orchestration, knowledge-base response generation, post-processing, memory summarization, and routing classifier. | Native or adjacent Bedrock surface depending on enabled features. | OEP does not replace Bedrock prompt construction; it records a manifest reference for reconstruction. |
| `tool_schema` | Action groups and their API/function definitions. | Native Bedrock surface. | OEP records the tool/action schema as evidence; Bedrock action groups remain the vendor-native action mechanism. |
| `policy` | IAM, Bedrock guardrails, and application-side OPA policy. | Split surface. | OEP's OPA permission packet is application-side tool authorization evidence, not a Bedrock guardrail replacement. |
| `workflow` | Bedrock agent orchestration, turns, and iterations. | Native Bedrock surface. | OEP records workflow identity and trace joins; it does not implement Bedrock orchestration. |
| `rollout` | Agent versions and aliases. | Native Bedrock surface. | Bedrock versions/aliases are a strong release precedent; OEP adds cross-stack reconstruction joins. |
| `eval` | Bedrock traces plus application-side deterministic eval result. | External in this demo. | This repository's eval is local and synthetic, not a Bedrock benchmark or production monitor. |
| `data_state` | Knowledge bases, session state, prompt session attributes, memory, and application state. | Split surface. | OEP records the data-state/replay reference needed for reconstruction; Bedrock owns its managed state surfaces. |

## Mapping Implication

The Bedrock translation is strongest for release and runtime identity around agent versions, aliases, action groups, prompt templates, trace output, session state, and memory. The OEP-specific contribution remains the external stitching of those surfaces to permission, replay, eval, and reconstruction evidence.
