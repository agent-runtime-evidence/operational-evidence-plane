package oep.permissions

default allow := false

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

has_budget if {
	is_number(input.budget.original_cumulative_usd)
	is_number(input.budget.counterfactual_budget_cap_usd)
}

within_budget if {
	has_budget
	input.budget.original_cumulative_usd <= input.budget.counterfactual_budget_cap_usd
}

budget_exceeded if {
	base_read_diff
	has_budget
	not within_budget
}

missing_budget_input if {
	base_read_diff
	not has_budget
}

default_denied if {
	not allow
	not budget_exceeded
	not missing_budget_input
}

allow if {
	base_read_diff
	within_budget
}

matched_rule := "allow_reference_code_review_diff_read" if {
	allow
}

matched_rule := "deny_budget_per_run_cap_exceeded" if {
	budget_exceeded
}

matched_rule := "deny_budget_input_missing" if {
	missing_budget_input
}

matched_rule := "deny_by_default" if {
	default_denied
}

reason := "reference code review agent may inspect an immutable synthetic diff within budget" if {
	allow
}

reason := sprintf(
	"counterfactual budget cap %v exceeded at cumulative cost %v",
	[input.budget.counterfactual_budget_cap_usd, input.budget.original_cumulative_usd],
) if {
	budget_exceeded
}

reason := "counterfactual budget policy requires captured budget fields" if {
	missing_budget_input
}

reason := "tool call denied by default reference policy" if {
	default_denied
}

decision_code := "BUDGET_EXCEEDED" if {
	budget_exceeded
}

decision_code := "BUDGET_INPUT_MISSING" if {
	missing_budget_input
}

decision_code := null if {
	not budget_exceeded
	not missing_budget_input
}

decision := {
	"allow": allow,
	"matched_rule": matched_rule,
	"policy_id": "opa-tool-permission-policy",
	"policy_version": "0.3.0-budget-per-run",
	"reason": reason,
	"decision_code": decision_code,
}
