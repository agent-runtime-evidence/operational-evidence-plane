# Deterministic Mock Reviewer

This artifact defines the model-behavior substitute used by the reference
code-review-agent scenario.

The reference demo does not call a live LLM or vendor model. Instead, the
workflow uses deterministic mocked review behavior implemented by
`demo/src/oep_demo/runner.py`.

## Contract

- Input: a repository diff fixture.
- Rule: emit one finding for each added line that contains `return None`.
- Finding severity: `medium`.
- Finding category: `correctness`.
- Finding title: `Suspicious return None`.
- Finding identifier: deterministic and line-based.
- Output order: source order.

## Evidence Boundary

This artifact binds the model-behavior layer for replay and reconstruction. It
is not a model-quality claim, benchmark, safety certification, or production
model contract.
