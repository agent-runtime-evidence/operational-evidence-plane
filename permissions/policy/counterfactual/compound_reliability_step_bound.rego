package oep.permissions

default allow := false

max_checkpoint_sequence := 4

base_read_diff if {
	input.release_manifest_id == "rmf_code_review_agent_2026_05_04_v0"
	input.actor.type == "agent"
	input.actor.id == "agent_code_review_reference_demo"
	input.action.action_type == "inspect_diff"
	input.tool.name == "read_diff"
	input.tool.operation == "read"
	input.resource.type == "repository_diff"
	not input.resource.mutable
}

has_checkpoint if {
	is_number(input.checkpoint.sequence)
}

within_step_bound if {
	has_checkpoint
	input.checkpoint.sequence <= max_checkpoint_sequence
}

step_bound_exceeded if {
	base_read_diff
	has_checkpoint
	not within_step_bound
}

missing_checkpoint_input if {
	base_read_diff
	not has_checkpoint
}

default_denied if {
	not allow
	not step_bound_exceeded
	not missing_checkpoint_input
}

allow if {
	base_read_diff
	within_step_bound
}

matched_rule := "allow_reference_code_review_diff_read" if {
	allow
}

matched_rule := "deny_compound_reliability_step_bound_exceeded" if {
	step_bound_exceeded
}

matched_rule := "deny_checkpoint_input_missing" if {
	missing_checkpoint_input
}

matched_rule := "deny_by_default" if {
	default_denied
}

reason := "reference code review agent may inspect an immutable synthetic diff" if {
	allow
}

reason := sprintf("counterfactual 4-step policy denies workflow step %v", [input.checkpoint.sequence]) if {
	step_bound_exceeded
}

reason := "counterfactual step-bound policy requires captured checkpoint.sequence" if {
	missing_checkpoint_input
}

reason := "tool call denied by default reference policy" if {
	default_denied
}

decision_code := "STEP_BOUND_EXCEEDED" if {
	step_bound_exceeded
}

decision_code := "CHECKPOINT_INPUT_MISSING" if {
	missing_checkpoint_input
}

decision_code := null if {
	not step_bound_exceeded
	not missing_checkpoint_input
}

decision := {
	"allow": allow,
	"matched_rule": matched_rule,
	"policy_id": "opa-tool-permission-policy",
	"policy_version": "0.3.0-compound-reliability",
	"reason": reason,
	"decision_code": decision_code,
}
