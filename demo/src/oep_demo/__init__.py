"""Deterministic demo package for the Operational Evidence Plane."""

from oep_demo.counterfactual import (
    ApprovalEscalationResult,
    BudgetPerRunResult,
    CompoundReliabilityResult,
    run_approval_escalation_counterfactual,
    run_budget_per_run_counterfactual,
    run_compound_reliability_counterfactual,
)
from oep_demo.runner import DemoResult, deterministic_review, run_demo

__all__ = [
    "ApprovalEscalationResult",
    "BudgetPerRunResult",
    "CompoundReliabilityResult",
    "DemoResult",
    "deterministic_review",
    "run_approval_escalation_counterfactual",
    "run_budget_per_run_counterfactual",
    "run_compound_reliability_counterfactual",
    "run_demo",
]
