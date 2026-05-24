# Contributing

Operational Evidence Plane is a reference implementation for inspectable agent
runtime evidence. Contributions should keep the repository small,
deterministic, and vendor-neutral.

## Local Checks

Run the verification chain before opening a pull request:

```bash
make clean-state
make verify
make test
make coverage
```

Run focused checks while iterating:

```bash
make lint
make typecheck
make test-policy
make check-digests
make check-dtr-jsonl
make build-check
```

`make verify` regenerates SQLite replay state and checks cross-artifact joins.
Generated state, coverage files, build outputs, DTR fragments, and report
directories should not be committed.

## Artifact Updates

When changing any file referenced by a resolved release-manifest binding, run:

```bash
make update-digests
```

When changing canonical resources that are mirrored into packages, run:

```bash
make sync-resources
make build-check
```

The sync target copies canonical artifacts into package resource directories.
The package build check fails if canonical artifacts and packaged resources
drift, if required source files are missing from the sdist, or if generated
artifacts enter the release package.

## Claim Boundaries

Keep public wording aligned with `docs/public_claims.md`.

Avoid claims of production readiness, audit readiness, proof of compliance,
standardization, vendor replacement, agent-framework scope, or model-quality
benchmarking.

## Scope

The public distribution is the root `operational-evidence-plane` package.
Workspace member directories are source and development boundaries for the
reference implementation; they are not independently published packages for the
current release line.
