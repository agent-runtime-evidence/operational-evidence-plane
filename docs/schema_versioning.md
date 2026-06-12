# Schema Versioning Policy

How the `oep.<name>.v0` schema contracts evolve, and what consumers can rely
on.

## Version markers

Every record carries a `schema_version` constant such as
`oep.tool_permission_packet.v0`. The suffix names the contract generation,
not the repository release: v0.1 through v0.3 repository releases all extend
the same `.v0` contracts.

## Additive changes stay `.v0`

A change is additive when every record that validated before still validates:
new optional fields, new optional sub-objects under an existing extensibility
point, or new `$defs` that do not change validation semantics. Additive
changes ship within the `.v0` line. The guarantee is enforced, not aspirational:
`make validate-backward-compat` replays v0.1-shaped records against the
current schemas, and [schema migration v0.3](schema_migration_v0.3.md)
documents the additive field list for the v0.3 generation.

Replay code treats absent optional surfaces as `not_recorded` rather than as
errors, so older records remain replayable after additive growth.

## Breaking changes bump the suffix

A change that invalidates previously valid records — removing or renaming a
field, tightening a pattern, making an optional field required — requires a
new schema file (`<name>.v1.schema.json`), a new `schema_version` constant,
and a migration document in `docs/` describing the field-level mapping. The
prior `.v0` schema stays in the tree while any committed example or recorded
state still references it.

## Schema bytes are release-visible

The release manifest's `tool_schema` layer binds the permission packet schema
by content digest, and permission packets pin `release_manifest_version`
over the manifest bytes. Editing a schema file therefore cascades: run
`make update-digests` and `make sync-resources`, and expect example and
adapter fixtures that embed the manifest digest to change in the same
commit. A schema edit is never an invisible change.

## Cross-schema reuse boundary

Identifier and digest patterns are kept byte-identical across schemas (see
the [schema reference](schema_reference.md)) but are deliberately not shared
through cross-file `$ref`: each schema file remains a self-contained
validation unit so it can be vendored, packaged, and validated in isolation.
The same single-file principle applies to OPA policy bundles — each
counterfactual policy is a self-contained `--data` input for replay
substitution.
