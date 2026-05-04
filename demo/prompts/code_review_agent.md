# Code Review Agent Prompt Contract

The reference code-review agent inspects a repository diff and reports
deterministic findings that can be joined to replay state and eval results.

## Instruction

Inspect the supplied repository diff. Report a correctness finding for each
added line that contains `return None`. Do not mutate repository files. Do not
call external services. Preserve enough evidence to join the finding back to
the release manifest, runtime event, permission packet, trace, replay handle,
and eval result.

## Output Contract

Each finding includes:

- `finding_id`
- `title`
- `severity`
- `category`
- `file`
- `line`
- `message`

## Evidence Boundary

This prompt contract is intentionally narrow so the reference scenario remains
deterministic and source-inspectable. It is not a general code-review prompt or
model behavior benchmark.
