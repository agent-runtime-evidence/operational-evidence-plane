# Changelog

All notable changes to this reference implementation are documented here.

## [Unreleased]

No changes yet.

## v0.1.0 - 2026-05-06

Initial public release candidate for the Operational Evidence Plane reference implementation.

### Added

- Added a release manifest schema and code-review-agent release example.
- Added resolved model, prompt, tool schema, policy, workflow, rollout, eval, and data-state layer bindings with content digests.
- Added an agent-step event profile joined to the release manifest.
- Added an OPA-backed tool permission packet and executable policy check.
- Added an operational trace bundle and deterministic eval result.
- Added a deterministic code-review demo that regenerates local SQLite replay state.
- Added a reconstruction packet playbook over the full evidence chain.
- Added Decision Trace Reconstructor JSONL projection, mapping config, and pinned feasibility output for the allowed scenario.
- Added top-level `make regen-dtr-jsonl` and optional `make validate-dtr` targets.
- Added inspectability docs, public-claim guardrails, and release checklist.
- Added optional Bedrock translation notes and mapping data as post-core documentation.
- Added root sdist/wheel release guardrails for canonical resources, package resources, tests, CI metadata, and generated-artifact exclusions.
- Added GitHub Actions verification workflow, SECURITY.md, CITATION.cff, CONTRIBUTING.md, and pytest smoke tests for public-readiness hygiene.

### Notes

- Public API unchanged.
- Schema contract introduced.
- Public package boundary is the root `operational-evidence-plane` distribution; workspace directories are source and development boundaries for this release line.
- This release candidate is not production-ready and does not create compliance readiness, legal-audit sufficiency, or standardization status.
