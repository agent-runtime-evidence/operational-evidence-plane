# Decision Log

## Core Decisions

| Decision | Choice | Reason |
|---|---|---|
| Language | Python | Optimizes inspectability and local iteration speed. |
| Model behavior | Deterministic mocked LLM | Keeps replay and eval stable without live model calls or vendor dependencies. |
| Storage | SQLite | Gives local, inspectable reconstruction state without database infrastructure. |
| Policy engine | Real OPA | Demonstrates a role-native policy decision instead of inventing a toy policy language. |
| Demo scenario | Code-review agent | Fits agent-runtime and platform-engineering proof while staying small. |
| Schema coupling | Scenario-agnostic schemas | Keeps manifest, event, permission, trace, and reconstruction artifacts reusable beyond this demo. |
| Vendor posture | Vendor-neutral core | Keeps the repository as an operational-evidence reference, not a cloud-specific extension. |

## Scope Decisions

The repository builds one inspectable wiring pattern across release-time and runtime evidence. It does not try to become an agent framework, tracing backend, policy engine, model gateway, deployment tool, eval platform, or compliance product.

The first vendor-specific material belongs outside the core chain. Bedrock translation should map concepts to Bedrock aliases, versions, and runtime references without making Bedrock the primary implementation target.

The Bedrock translation is intentionally documentation and mapping data, not a Python workspace package. Its standalone check script is still part of `make verify`.

The root `pyproject.toml` defines the public `operational-evidence-plane` distribution. It packages the reference implementation modules, resources, and entry points together so the first public release has one installable surface. Workspace member `pyproject.toml` files remain source and development boundaries, not independently published packages for `v0.1.x`.

## Verification Decisions

`make verify` is the main local contract. It regenerates state and checks joins rather than relying on hand-inspected examples.

`make test` is a small pytest smoke-test layer over public verification scripts. It is intentionally separate from `make verify` so the default verification path stays dependency-light.

The generated SQLite file is ignored because committed generated state would make the repo noisier and less trustworthy. The source of truth is the committed artifact set plus the verification scripts.
