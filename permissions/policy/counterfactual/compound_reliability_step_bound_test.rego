package oep.permissions

base_input := {
	"release_manifest_id": "rmf_code_review_agent_2026_05_04_v0",
	"actor": {"type": "agent", "id": "agent_code_review_reference_demo"},
	"action": {"action_type": "inspect_diff"},
	"tool": {"name": "read_diff", "operation": "read"},
	"resource": {"type": "repository_diff", "mutable": false},
	"checkpoint": {"sequence": 4},
}

test_allows_step_within_bound if {
	result := decision with input as base_input

	result.allow == true
	result.matched_rule == "allow_reference_code_review_diff_read"
	result.decision_code == null
	result.policy_version == "0.3.0-compound-reliability"
}

test_denies_step_above_bound if {
	checkpoint := object.union(base_input.checkpoint, {"sequence": 5})
	test_input := object.union(base_input, {"checkpoint": checkpoint})
	result := decision with input as test_input

	result.allow == false
	result.matched_rule == "deny_compound_reliability_step_bound_exceeded"
	result.decision_code == "STEP_BOUND_EXCEEDED"
}

test_denies_wrong_manifest_by_default if {
	test_input := object.union(base_input, {"release_manifest_id": "rmf_untrusted_release"})
	result := decision with input as test_input

	result.allow == false
	result.matched_rule == "deny_by_default"
	result.reason == "tool call denied by default reference policy"
}

test_denies_missing_checkpoint_input if {
	test_input := object.remove(base_input, {"checkpoint"})
	result := decision with input as test_input

	result.allow == false
	result.matched_rule == "deny_checkpoint_input_missing"
	result.decision_code == "CHECKPOINT_INPUT_MISSING"
	result.reason == "counterfactual step-bound policy requires captured checkpoint.sequence"
}
