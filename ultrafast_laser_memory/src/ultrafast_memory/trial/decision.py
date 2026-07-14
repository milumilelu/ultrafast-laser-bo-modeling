from __future__ import annotations

from typing import Any

from ultrafast_domain.trial.campaign import TrialDecision


class TrialDecisionService:
    """Deterministic trial continuation gate; no LLM or persistence."""

    @classmethod
    def decide(
        cls,
        *,
        measurements: dict[str, Any],
        targets: dict[str, Any],
        constraints: dict[str, Any],
        iteration_number: int,
        iteration_budget: int,
        risk_state: str = "normal",
    ) -> dict[str, Any]:
        missing = sorted(set(targets) - set(measurements))
        if missing:
            return cls._result(TrialDecision.ESCALATE_REVIEW, [f"missing_target:{x}" for x in missing])
        failed_constraints = sorted(
            name for name, passed in constraints.items() if passed is False
        )
        if failed_constraints or risk_state in {"blocked", "alarm", "unsafe"}:
            reasons = [f"constraint_failed:{name}" for name in failed_constraints]
            if risk_state != "normal":
                reasons.append(f"risk_state:{risk_state}")
            return cls._result(TrialDecision.TRIAL_BLOCKED, reasons)
        failed_targets = [
            name for name, target in targets.items()
            if not cls._target_met(float(measurements[name]), target)
        ]
        if not failed_targets:
            return cls._result(TrialDecision.TRIAL_SUCCEEDED, ["all_targets_satisfied"])
        if iteration_number >= iteration_budget:
            return cls._result(
                TrialDecision.ESCALATE_REVIEW,
                [f"iteration_budget_exhausted:{name}" for name in failed_targets],
            )
        return cls._result(
            TrialDecision.CONTINUE_TRIAL,
            [f"target_not_met:{name}" for name in failed_targets],
        )

    @staticmethod
    def _target_met(value: float, target: Any) -> bool:
        if isinstance(target, (int, float)) and not isinstance(target, bool):
            return value <= float(target)
        if not isinstance(target, dict):
            return False
        if target.get("max") is not None and value > float(target["max"]):
            return False
        if target.get("min") is not None and value < float(target["min"]):
            return False
        if target.get("equals") is not None and value != float(target["equals"]):
            return False
        return True

    @staticmethod
    def _result(decision: TrialDecision, reasons: list[str]) -> dict[str, Any]:
        return {"decision": decision.value, "reasons": reasons}
