package oep.permissions

valid_input := {
	"release_manifest_id": "rmf_code_review_agent_2026_05_04_v0",
	"event_id": "evt_code_review_agent_step_0001",
	"tool_call_id": "tool_read_diff_0001",
	"trace_id": "11111111111111111111111111111111",
	"span_id": "2222222222222222",
	"actor": {
		"type": "agent",
		"id": "agent_code_review_reference_demo",
		"display_name": "code-review-agent-reference-demo",
	},
	"action": {
		"action_type": "inspect_diff",
		"name": "inspect synthetic repository diff",
		"input_ref": "demo/fixtures/diff_synthetic_001.patch",
	},
	"tool": {
		"name": "read_diff",
		"version": "0.1.0",
		"operation": "read",
	},
	"resource": {
		"type": "repository_diff",
		"id": "diff_synthetic_001",
		"uri": "demo/fixtures/diff_synthetic_001.patch",
		"mutable": false,
	},
}

test_allows_local_immutable_diff if {
	result := decision with input as valid_input

	result.allow == true
	result.matched_rule == "allow_reference_code_review_diff_read"
	result.reason == "reference code review agent may inspect an immutable synthetic diff"
	result.policy_id == "opa-tool-permission-policy"
	result.policy_version == "0.1.0"
}

test_denies_mutable_resource if {
	resource := object.union(valid_input.resource, {"mutable": true})
	test_input := object.union(valid_input, {"resource": resource})

	deny_by_default(test_input)
}

test_denies_wrong_actor if {
	actor := object.union(valid_input.actor, {"id": "agent_untrusted"})
	test_input := object.union(valid_input, {"actor": actor})

	deny_by_default(test_input)
}

test_denies_wrong_operation if {
	tool := object.union(valid_input.tool, {"operation": "write"})
	test_input := object.union(valid_input, {"tool": tool})

	deny_by_default(test_input)
}

test_denies_wrong_manifest if {
	test_input := object.union(valid_input, {"release_manifest_id": "rmf_untrusted_release"})

	deny_by_default(test_input)
}

deny_by_default(test_input) if {
	result := decision with input as test_input

	result.allow == false
	result.matched_rule == "deny_by_default"
	result.reason == "tool call denied by default reference policy"
}
