# Context shown to the human reviewer

This file is the exact context snapshot the reviewer saw at review time. Its
sha256 is bound into the `human_review_event.v0` record, so the review cannot
later be re-attributed to a different context.

**Decision under review:** code-review agent step `evt_code_review_agent_step_0001`
(trace `11111111111111111111111111111111`, span `2222222222222222`).

**What the agent proposed**
- Action: approve the synthetic diff `diff_synthetic_001` for merge.
- Agent finding: "No security-sensitive changes; the diff touches only
  documentation and a test fixture."
- Confidence: 0.82.

**What the reviewer was shown**
- The full diff `demo/fixtures/diff_synthetic_001.patch`.
- The agent's finding and confidence above.
- The permission packet `pder_code_review_read_diff_0001` (read-only scope).
