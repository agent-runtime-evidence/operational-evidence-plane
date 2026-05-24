package oep.permissions

default allow := false

base_code_review if {
	input.release_manifest_id == "rmf_code_review_agent_2026_05_04_v0"
	input.actor.type == "agent"
	input.actor.id == "agent_code_review_reference_demo"
	input.resource.type == "repository_diff"
}

read_operation if {
	input.tool.operation == "read"
	input.action.action_type == "inspect_diff"
	not input.resource.mutable
}

write_operation if {
	input.tool.operation == "write"
	input.action.action_type == "write_diff"
	input.resource.mutable
}

write_has_approval if {
	write_operation
	input.approval_capture.approver.type == "human"
}

approval_required if {
	base_code_review
	write_operation
	not write_has_approval
}

default_denied if {
	not allow
	not approval_required
}

allow if {
	base_code_review
	read_operation
}

allow if {
	base_code_review
	write_operation
	write_has_approval
}

matched_rule := "allow_reference_code_review_diff_read" if {
	allow
	read_operation
}

matched_rule := "allow_write_with_human_approval" if {
	allow
	write_operation
}

matched_rule := "deny_write_requires_per_step_approval" if {
	approval_required
}

matched_rule := "deny_by_default" if {
	default_denied
}

reason := "reference code review agent may inspect an immutable synthetic diff" if {
	allow
	read_operation
}

reason := "write operation has recorded human approval" if {
	allow
	write_operation
}

has_checkpoint if {
	is_number(input.checkpoint.sequence)
}

reason := sprintf("counterfactual approval policy requires human approval at workflow step %v", [input.checkpoint.sequence]) if {
	approval_required
	has_checkpoint
}

reason := "counterfactual approval policy requires human approval for write operation" if {
	approval_required
	not has_checkpoint
}

reason := "tool call denied by default reference policy" if {
	default_denied
}

decision_code := "APPROVAL_REQUIRED" if {
	approval_required
}

decision_code := null if {
	not approval_required
}

decision := {
	"allow": allow,
	"matched_rule": matched_rule,
	"policy_id": "opa-tool-permission-policy",
	"policy_version": "0.3.0-approval-per-step",
	"reason": reason,
	"decision_code": decision_code,
}
