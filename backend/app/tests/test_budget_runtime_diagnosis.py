"""Budget admission is a local cost guard failure, never a provider outage."""
import pytest

from app.agents.evidence_workflow import _fallback_reason
from app.services.ai_budget import BudgetAdmissionError


@pytest.mark.parametrize("reason", [
    "budget_cutover_not_enabled", "daily_input_token_limit", "unexpected private diagnostic",
])
def test_budget_admission_is_classified_without_exposing_exception_details(reason):
    assert _fallback_reason(BudgetAdmissionError(reason)) == "budget_admission"


def test_unrelated_provider_failure_remains_generic():
    assert _fallback_reason(RuntimeError("private upstream body")) == "provider_error"
