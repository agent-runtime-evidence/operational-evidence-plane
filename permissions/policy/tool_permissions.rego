package oep.permissions

default allow := false

allow if {
	input.release_manifest_id == "rmf_code_review_agent_2026_05_04_v0"
	input.actor.type == "agent"
	input.actor.id == "agent_code_review_reference_demo"
	input.action.action_type == "inspect_diff"
	input.tool.name == "read_diff"
	input.tool.operation == "read"
	input.resource.type == "repository_diff"
	not input.resource.mutable
}

matched_rule := "allow_reference_code_review_diff_read" if {
	allow
}

matched_rule := "deny_by_default" if {
	not allow
}

reason := "reference code review agent may inspect an immutable synthetic diff" if {
	allow
}

reason := "tool call denied by default reference policy" if {
	not allow
}

decision := {
	"allow": allow,
	"matched_rule": matched_rule,
	"policy_id": "opa-tool-permission-policy",
	"policy_version": "0.1.0",
	"reason": reason,
}
