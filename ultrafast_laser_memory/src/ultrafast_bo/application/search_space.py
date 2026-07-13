from __future__ import annotations

import hashlib
import json
import math
from statistics import NormalDist
from typing import Any

from ultrafast_bo.domain.search_space import CompiledSearchSpace, ParameterMode, ParameterPolicy


SUPPORTED_CONSTRAINT_TYPES = frozenset(
    {
        "pulse_energy_max", "pulse_energy_min", "line_energy_max", "areal_energy_max",
        "parameter_sum_limit", "parameter_product_limit", "conditional_parameter_required",
        "conditional_parameter_forbidden",
    }
)


class SearchSpaceBuilder:
    def compile(
        self,
        task_spec: dict[str, Any],
        equipment_snapshot: dict[str, Any],
        parameter_policy: dict[str, ParameterPolicy | dict[str, Any]],
        approved_priors: list[dict[str, Any]] | None,
        current_recipe: dict[str, Any] | None,
        trial_mode: str,
    ) -> CompiledSearchSpace:
        equipment_bounds = equipment_snapshot.get("machine_bounds") or equipment_snapshot.get("parameter_bounds") or {}
        variables: dict[str, dict[str, Any]] = {}
        fixed: dict[str, Any] = {}
        forbidden: dict[str, str] = {}
        trace: list[dict[str, Any]] = []
        blocking: list[str] = []
        conflicts: list[dict[str, Any]] = []
        warnings: list[str] = []
        recipe = dict(current_recipe or {})
        priors = list(approved_priors or [])
        for name, raw_policy in parameter_policy.items():
            policy = ParameterPolicy.from_value(raw_policy)
            try:
                mode = ParameterMode(policy.mode)
            except ValueError:
                blocking.append(f"unsupported_parameter_mode:{name}:{policy.mode}")
                continue
            device = _device_spec(equipment_bounds.get(name))
            if mode == ParameterMode.UNKNOWN:
                blocking.append(f"unknown_parameter_policy:{name}")
                continue
            if mode in {ParameterMode.FORBIDDEN, ParameterMode.UNAVAILABLE}:
                forbidden[name] = policy.reason or mode.value
                trace.append({"parameter": name, "source": "parameter_policy", "mode": mode.value})
                continue
            if mode == ParameterMode.DERIVED:
                trace.append({"parameter": name, "source": "parameter_policy", "mode": "derived"})
                continue
            if mode == ParameterMode.FIXED:
                value = policy.value if policy.value is not None else recipe.get(name)
                if value is None:
                    blocking.append(f"fixed_parameter_value_missing:{name}")
                    continue
                if device and not _value_allowed(value, device):
                    blocking.append(f"fixed_parameter_outside_device_boundary:{name}")
                    conflicts.append({"parameter": name, "value": value, "source": "user_fixed", "device": device})
                    continue
                fixed[name] = value
                trace.append({"parameter": name, "source": "user_fixed", "value": value})
                continue
            if mode == ParameterMode.CATEGORICAL:
                device_values = tuple(device.get("allowed_values", ())) if device else ()
                allowed = tuple(policy.allowed_values or device_values)
                if device_values:
                    allowed = tuple(value for value in allowed if value in device_values)
                if not allowed:
                    blocking.append(f"empty_categorical_domain:{name}")
                    conflicts.append({"parameter": name, "equipment": list(device_values), "policy": list(policy.allowed_values)})
                    continue
                variables[name] = {"type": "categorical", "allowed_values": list(allowed), "mode": mode.value, "unit": policy.unit}
                continue
            sources: list[dict[str, Any]] = []
            lower_values: list[tuple[float, str]] = []
            upper_values: list[tuple[float, str]] = []
            if device and device.get("lower") is not None:
                lower_values.append((float(device["lower"]), "equipment_hard_boundary"))
                upper_values.append((float(device["upper"]), "equipment_hard_boundary"))
                sources.append({"source": "equipment_hard_boundary", **device})
            if policy.lower is not None:
                lower_values.append((float(policy.lower), "user_policy"))
            if policy.upper is not None:
                upper_values.append((float(policy.upper), "user_policy"))
            task_range = (task_spec.get("parameter_constraints") or {}).get(name)
            if isinstance(task_range, (list, tuple)) and len(task_range) == 2:
                lower_values.append((float(task_range[0]), "task_requirement"))
                upper_values.append((float(task_range[1]), "task_requirement"))
                sources.append({"source": "task_requirement", "lower": task_range[0], "upper": task_range[1]})
            for prior in priors:
                if prior.get("parameter_name") != name:
                    continue
                if prior.get("status") not in {"approved", "active", "process_prior"} and not prior.get("approval_id"):
                    warnings.append(f"unapproved_prior_ignored:{prior.get('prior_id') or name}")
                    continue
                if prior.get("lower_bound") is not None:
                    lower_values.append((float(prior["lower_bound"]), "approved_process_prior"))
                if prior.get("upper_bound") is not None:
                    upper_values.append((float(prior["upper_bound"]), "approved_process_prior"))
                sources.append({"source": "approved_process_prior", "id": prior.get("prior_id"), "lower": prior.get("lower_bound"), "upper": prior.get("upper_bound")})
            if not lower_values or not upper_values:
                blocking.append(f"parameter_boundary_incomplete:{name}")
                continue
            lower, lower_source = max(lower_values, key=lambda item: item[0])
            upper, upper_source = min(upper_values, key=lambda item: item[0])
            if lower > upper:
                blocking.append(f"infeasible_parameter_range:{name}")
                conflicts.append(
                    {
                        "parameter": name,
                        "lower_candidates": [{"value": v, "source": s} for v, s in lower_values],
                        "upper_candidates": [{"value": v, "source": s} for v, s in upper_values],
                    }
                )
                continue
            kind = "integer" if mode == ParameterMode.INTEGER else ("conditional" if mode == ParameterMode.CONDITIONAL else "continuous")
            step = policy.step if policy.step is not None else (device or {}).get("step")
            variables[name] = {
                "type": kind, "mode": mode.value, "lower": lower, "upper": upper,
                "step": int(step) if kind == "integer" and step else step,
                "condition": dict(policy.condition), "unit": policy.unit or (device or {}).get("unit"),
            }
            trace.append(
                {"parameter": name, "final_lower": lower, "final_upper": upper,
                 "active_lower_source": lower_source, "active_upper_source": upper_source, "sources": sources}
            )
        derived = _validated_constraints(task_spec.get("derived_constraints") or [])
        unsupported = [c.get("constraint_type") for c in (task_spec.get("derived_constraints") or []) if c.get("constraint_type") not in SUPPORTED_CONSTRAINT_TYPES]
        blocking.extend(f"unsupported_constraint_type:{value}" for value in unsupported)
        outcome = list(task_spec.get("outcome_constraints") or [])
        status = "infeasible_search_space" if blocking else ("no_optimizable_parameters" if not variables else "ready")
        canonical = {
            "variables": variables, "fixed_parameters": fixed, "forbidden_parameters": forbidden,
            "derived_constraints": derived, "outcome_constraints": outcome, "trial_mode": trial_mode,
            "equipment_revision": equipment_snapshot.get("revision_id"),
        }
        version = "search_space_" + hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
        return CompiledSearchSpace(
            variables, fixed, forbidden, derived, outcome, trace, version, status,
            blocking, conflicts, warnings,
        )


class ConstraintEvaluator:
    FORMULA_VERSION = "energy-constraints-1.0"

    def evaluate(self, parameters: dict[str, Any], constraint: dict[str, Any]) -> bool:
        kind = constraint["constraint_type"]
        threshold = float(constraint.get("threshold", 0))
        if kind in {"pulse_energy_max", "pulse_energy_min"}:
            value = 1000.0 * float(parameters["laser_power_W"]) / float(parameters["frequency_kHz"])
            return value <= threshold if kind.endswith("max") else value >= threshold
        if kind == "line_energy_max":
            return float(parameters["laser_power_W"]) / float(parameters["scan_speed_mm_s"]) <= threshold
        if kind == "areal_energy_max":
            value = (
                float(parameters["laser_power_W"]) * float(parameters.get("passes", 1)) /
                (float(parameters["scan_speed_mm_s"]) * float(parameters["hatch_spacing_um"]))
            )
            return value <= threshold
        names = list(constraint.get("parameters") or [])
        if kind == "parameter_sum_limit":
            return sum(float(parameters[name]) for name in names) <= threshold
        if kind == "parameter_product_limit":
            return math.prod(float(parameters[name]) for name in names) <= threshold
        condition_name = constraint.get("if_parameter")
        active = parameters.get(condition_name) == constraint.get("equals")
        target = constraint.get("parameter")
        if kind == "conditional_parameter_required":
            return not active or parameters.get(target) is not None
        if kind == "conditional_parameter_forbidden":
            return not active or parameters.get(target) is None
        raise ValueError(f"unsupported constraint type: {kind}")

    def all_satisfied(self, parameters: dict[str, Any], constraints: list[dict[str, Any]]) -> bool:
        return all(self.evaluate(parameters, constraint) for constraint in constraints)


def project_candidate(candidate: dict[str, Any], space: CompiledSearchSpace) -> dict[str, Any]:
    projected = dict(space.fixed_parameters)
    ordered = [
        *((name, spec) for name, spec in space.variables.items() if spec["type"] != "conditional"),
        *((name, spec) for name, spec in space.variables.items() if spec["type"] == "conditional"),
    ]
    for name, spec in ordered:
        if spec["type"] == "conditional" and not _condition_active(projected, candidate, spec.get("condition") or {}):
            continue
        raw = candidate.get(name)
        if spec["type"] == "categorical":
            allowed = spec["allowed_values"]
            if raw not in allowed:
                raw = allowed[0]
        else:
            if raw is None:
                raw = (spec["lower"] + spec["upper"]) / 2
            raw = min(max(float(raw), spec["lower"]), spec["upper"])
            step = spec.get("step")
            if step:
                raw = spec["lower"] + round((raw - spec["lower"]) / step) * step
                raw = min(max(raw, spec["lower"]), spec["upper"])
            if spec["type"] == "integer":
                raw = int(round(raw))
        projected[name] = raw
    return projected


def _condition_active(projected: dict[str, Any], candidate: dict[str, Any], condition: dict[str, Any]) -> bool:
    if not condition:
        return False
    controller = condition.get("if_parameter") or condition.get("parameter")
    if not controller:
        return False
    actual = projected.get(controller, candidate.get(controller))
    if "equals" in condition:
        return actual == condition["equals"]
    if "in" in condition:
        return actual in condition["in"]
    return bool(actual)


def outcome_feasibility_probability(
    predictions: dict[str, dict[str, float]], constraints: list[dict[str, Any]]
) -> tuple[dict[str, float], float]:
    probabilities: dict[str, float] = {}
    for constraint in constraints:
        metric = constraint["metric"]
        estimate = predictions.get(metric) or {}
        mean = estimate.get("mean")
        std = estimate.get("std")
        if mean is None or std is None or float(std) <= 0:
            probabilities[metric] = 0.0
            continue
        z = (float(constraint["threshold"]) - float(mean)) / float(std)
        cdf = NormalDist().cdf(z)
        probabilities[metric] = cdf if constraint.get("operator", "max") == "max" else 1.0 - cdf
    overall = math.prod(probabilities.values()) if probabilities else 1.0
    return probabilities, overall


def _device_spec(value: Any) -> dict[str, Any] | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return {"lower": float(value[0]), "upper": float(value[1])}
    if isinstance(value, dict):
        result = dict(value)
        if "bounds" in result and len(result["bounds"]) == 2:
            result["lower"], result["upper"] = map(float, result["bounds"])
        return result
    return None


def _value_allowed(value: Any, spec: dict[str, Any]) -> bool:
    if spec.get("allowed_values"):
        return value in spec["allowed_values"]
    if spec.get("lower") is not None:
        return float(spec["lower"]) <= float(value) <= float(spec["upper"])
    return True


def _validated_constraints(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**value, "formula_version": ConstraintEvaluator.FORMULA_VERSION} for value in values if value.get("constraint_type") in SUPPORTED_CONSTRAINT_TYPES]
