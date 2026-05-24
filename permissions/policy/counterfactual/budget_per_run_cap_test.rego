package oep.permissions

base_input := {
	"release_manifest_id": "rmf_code_review_agent_2026_05_04_v0",
	"actor": {"type": "agent", "id": "agent_code_review_reference_demo"},
	"action": {"action_type": "inspect_diff"},
	"tool": {"name": "read_diff", "operation": "read"},
	"resource": {"type": "repository_diff", "mutable": false},
	"budget": {
		"original_cumulative_usd": 5000,
		"counterfactual_budget_cap_usd": 5000,
	},
}

test_allows_at_budget_cap if {
	result := decision with input as base_input

	result.allow == true
	result.matched_rule == "allow_reference_code_review_diff_read"
	result.policy_version == "0.3.0-budget-per-run"
	result.decision_code == null
}

test_denies_above_budget_cap if {
	budget := object.union(base_input.budget, {"original_cumulative_usd": 6000})
	test_input := object.union(base_input, {"budget": budget})
	result := decision with input as test_input

	result.allow == false
	result.matched_rule == "deny_budget_per_run_cap_exceeded"
	result.decision_code == "BUDGET_EXCEEDED"
}

test_denies_wrong_manifest_by_default if {
	test_input := object.union(base_input, {"release_manifest_id": "rmf_untrusted_release"})
	result := decision with input as test_input

	result.allow == false
	result.matched_rule == "deny_by_default"
	result.reason == "tool call denied by default reference policy"
	result.decision_code == null
}

test_denies_missing_budget_input if {
	test_input := object.remove(base_input, {"budget"})
	result := decision with input as test_input

	result.allow == false
	result.matched_rule == "deny_budget_input_missing"
	result.decision_code == "BUDGET_INPUT_MISSING"
	result.reason == "counterfactual budget policy requires captured budget fields"
}
