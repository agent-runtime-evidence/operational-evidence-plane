# Release Checklist

Use this checklist before publishing a public `v0.1.x` tag, GitHub release, or package artifact.

## Required Checks

- [ ] Run `make clean-state`.
- [ ] Run `make verify`.
- [ ] Run `make test` after installing dev dependencies.
- [ ] Run `make coverage` and confirm coverage remains at or above the configured threshold.
- [ ] Run `make build-check` and confirm the root wheel and sdist both pass.
- [ ] Confirm the root sdist contains docs, canonical schemas/examples/scripts, tests, and CI metadata.
- [ ] Confirm the root sdist excludes generated replay state, DTR intermediates, reports, and cache files.
- [ ] Confirm `git status --short` has no tracked changes.
- [ ] Confirm `demo/state/code_review_agent.sqlite` is ignored, not staged.
- [ ] Confirm `.github/workflows/verify.yml`, `SECURITY.md`, and `CITATION.cff` are present.
- [ ] Confirm `CONTRIBUTING.md` describes local checks, artifact updates, and claim boundaries.
- [ ] Confirm CI pins OPA to the intended tested 1.x version.
- [ ] Confirm README quickstart works from a fresh clone on a supported Python version.
- [ ] Confirm `pyproject.toml`, `CHANGELOG.md`, `CITATION.cff`, and the release tag use the same version/date.
- [ ] Confirm `project.urls` and GitHub repository metadata point to the public project.
- [ ] Review [public claims guide](public_claims.md).
- [ ] Confirm Bedrock translation remains post-core documentation under `translations/bedrock/`.
- [ ] Confirm no AWS calls, live LLM calls, production APIs, or services are required.

## Release Boundary

The public Python distribution is the root package, `operational-evidence-plane`. Workspace member directories are source and development boundaries for the reference implementation; they are not independently published packages for `v0.1.x`.

`v0.1.x` means:

- complete inspectable evidence chain;
- deterministic verification over committed artifacts;
- reproducible generated SQLite replay state;
- root wheel and source distribution checks;
- source-safe claim boundaries;
- optional Bedrock translation.

It does not mean production readiness, compliance readiness, standardization, legal-audit sufficiency, or a vendor replacement.

## Publication Steps

1. Create the release branch or commit after all required checks pass.
2. Create an annotated tag for the release version.
3. Publish the GitHub release with the changelog summary and claim boundary.
4. If publishing to PyPI, publish only the root distribution for `v0.1.x`.
5. Verify the release artifact by installing it in a fresh virtual environment and running the packaged entry points.

## Files To Inspect Before Publication

1. `README.md`
2. `CHANGELOG.md`
3. `docs/architecture.md`
4. `docs/public_claims.md`
5. `SECURITY.md`
6. `CITATION.cff`
7. `CONTRIBUTING.md`
8. `pyproject.toml`
9. `playbooks/examples/code_review_reconstruction_packet.v0.json`
10. `translations/bedrock/source_notes.md`
