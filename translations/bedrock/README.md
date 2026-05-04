# Bedrock Translation

This optional post-core translation was source-checked against official AWS documentation on 2026-05-04.

This folder maps the vendor-neutral Operational Evidence Plane chain to Amazon Bedrock Agents concepts. It is not a Bedrock implementation, IaC module, deployment recipe, or claim that Bedrock lacks useful versioning and runtime trace surfaces.

## Files

- [Layer mapping](layer_mapping.md)
- [Runtime mapping](runtime_mapping.md)
- [Source notes](source_notes.md)
- [Translation schema](schema/bedrock_translation.v0.schema.json)
- [Code-review translation example](examples/code_review_bedrock_translation.v0.json)
- [Translation checker](scripts/check_bedrock_translation.py)

## Core Mapping

```text
OEP release manifest -> Bedrock agent version plus alias context
OEP event/trace IDs -> InvokeAgent trace plus application-side correlation IDs
OEP permission packet -> application-side OPA evidence around tool/action use
OEP replay/eval/reconstruction -> application-side evidence packet around Bedrock runtime outputs
```

Bedrock aliases and versions are treated as strong vendor-native precedents. The OEP translation adds an external reconstruction packet around release-time and runtime evidence; it does not replace Bedrock aliases, versions, traces, memory, guardrails, action groups, or knowledge bases.

## Boundary

This folder should stay post-core. The vendor-neutral artifacts remain the source of truth for the local demo.
