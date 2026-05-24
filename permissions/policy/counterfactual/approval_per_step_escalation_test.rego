package oep.permissions

read_input := {
	"release_manifest_id": "rmf_code_review_agent_2026_05_04_v0",
	"actor": {"type": "agent", "id": "agent_code_review_reference_demo"},
	"action": {"action_type": "inspect_diff"},
	"tool": {"name": "read_diff", "operation": "read"},
	"resource": {"type": "repository_diff", "mutable": false},
	"checkpoint": {"sequence": 1},
	"approval_capture": null,
}

write_input := {
	"release_manifest_id": "rmf_code_review_agent_2026_05_04_v0",
	"actor": {"type": "agent", "id": "agent_code_review_reference_demo"},
	"action": {"action_type": "write_diff"},
	"tool": {"name": "write_diff", "operation": "write"},
	"resource": {"type": "repository_diff", "mutable": true},
	"checkpoint": {"sequence": 2},
	"approval_capture": null,
}

test_allows_read_operation if {
	result := decision with input as read_input

	result.allow == true
	result.matched_rule == "allow_reference_code_review_diff_read"
	result.policy_version == "0.3.0-approval-per-step"
	result.decision_code == null
}

test_denies_write_without_approval if {
	result := decision with input as write_input

	result.allow == false
	result.matched_rule == "deny_write_requires_per_step_approval"
	result.decision_code == "APPROVAL_REQUIRED"
}

test_allows_write_with_human_approval if {
	approved := object.union(
		write_input,
		{"approval_capture": {"approver": {"type": "human", "id": "human_code_owner"}}},
	)
	result := decision with input as approved

	result.allow == true
	result.matched_rule == "allow_write_with_human_approval"
	result.decision_code == null
}

test_denies_wrong_manifest_by_default if {
	test_input := object.union(read_input, {"release_manifest_id": "rmf_untrusted_release"})
	result := decision with input as test_input

	result.allow == false
	result.matched_rule == "deny_by_default"
	result.reason == "tool call denied by default reference policy"
	result.decision_code == null
}

test_denies_unsupported_operation_by_default if {
	test_input := object.union(read_input, {"action": {"action_type": "inspect_secret"}})
	result := decision with input as test_input

	result.allow == false
	result.matched_rule == "deny_by_default"
	result.reason == "tool call denied by default reference policy"
	result.decision_code == null
}

test_denies_write_without_checkpoint if {
	test_input := object.remove(write_input, {"checkpoint"})
	result := decision with input as test_input

	result.allow == false
	result.matched_rule == "deny_write_requires_per_step_approval"
	result.decision_code == "APPROVAL_REQUIRED"
	result.reason == "counterfactual approval policy requires human approval for write operation"
}
