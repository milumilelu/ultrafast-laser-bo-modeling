from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection

from .schemas import CampaignState, OptimizationCampaign


CAMPAIGN_TRANSITIONS = {
    CampaignState.CAMPAIGN_CREATED: CampaignState.ITERATION_PLANNING,
    CampaignState.ITERATION_PLANNING: CampaignState.DATA_SUPPORT_ASSESSMENT,
    CampaignState.DATA_SUPPORT_ASSESSMENT: CampaignState.PARAMETER_SOURCE_SELECTION,
    CampaignState.PARAMETER_SOURCE_SELECTION: CampaignState.CANDIDATE_GENERATION,
    CampaignState.CANDIDATE_GENERATION: CampaignState.CANDIDATE_FILTERING,
    CampaignState.CANDIDATE_FILTERING: CampaignState.CANDIDATE_APPROVAL_PENDING,
    CampaignState.CANDIDATE_APPROVAL_PENDING: CampaignState.ITERATION_EXECUTION,
    CampaignState.ITERATION_EXECUTION: CampaignState.OBSERVATION_PENDING,
    CampaignState.OBSERVATION_PENDING: CampaignState.OBSERVATION_VALIDATION,
    CampaignState.OBSERVATION_VALIDATION: CampaignState.MODEL_UPDATE,
    CampaignState.MODEL_UPDATE: CampaignState.ITERATION_DECISION,
}


class CampaignService:
    def __init__(self):
        init_database()
        self.campaigns: dict[str, OptimizationCampaign] = {}
        self.observations: dict[str, dict[str, Any]] = {}
        self.snapshots: dict[str, dict[str, Any]] = {}

    def create(self, **data: Any) -> OptimizationCampaign:
        campaign = OptimizationCampaign(**data)
        self.campaigns[campaign.campaign_id] = campaign
        now = utc_now_iso()
        constraints = {"hard": campaign.hard_constraints, "soft": campaign.soft_constraints,
                       "active_variables": campaign.active_variables, "fixed_parameters": campaign.fixed_parameters}
        with get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO optimization_campaign VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                campaign.campaign_id, campaign.task_id, campaign.campaign_type, campaign.fidelity_level,
                json.dumps(campaign.material_context, ensure_ascii=False), campaign.equipment_revision,
                json.dumps(campaign.objectives, ensure_ascii=False), json.dumps(constraints, ensure_ascii=False),
                json.dumps(campaign.search_space, ensure_ascii=False), json.dumps(campaign.budget, ensure_ascii=False),
                campaign.status.value, now, now))
            conn.commit()
        return campaign

    def load(self, campaign_id: str) -> OptimizationCampaign:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM optimization_campaign WHERE campaign_id=?", (campaign_id,)).fetchone()
        if not row:
            raise ValueError(f"campaign not found: {campaign_id}")
        value = dict(row)
        constraints = json.loads(value["constraints_json"])
        campaign = OptimizationCampaign(
            campaign_id=value["campaign_id"], task_id=value["task_id"],
            campaign_type=value["campaign_type"], fidelity_level=value["fidelity_level"],
            material_context=json.loads(value["material_context_json"]),
            equipment_revision=value["equipment_revision"],
            active_variables=constraints.get("active_variables") or [],
            fixed_parameters=constraints.get("fixed_parameters") or {},
            objectives=json.loads(value["objectives_json"]),
            hard_constraints=constraints.get("hard") or [], soft_constraints=constraints.get("soft") or [],
            search_space=json.loads(value["search_space_json"]), budget=json.loads(value["budget_json"]),
            status=value["status"], current_iteration=0)
        self.campaigns[campaign_id] = campaign
        return campaign

    def advance(self, campaign_id: str, target: CampaignState | None = None) -> OptimizationCampaign:
        campaign = self.campaigns[campaign_id]
        expected = CAMPAIGN_TRANSITIONS.get(campaign.status)
        target = target or expected
        if target != expected:
            raise ValueError(f"illegal campaign transition: {campaign.status} -> {target}")
        campaign.status = target
        with get_connection() as conn:
            conn.execute("UPDATE optimization_campaign SET status=?, updated_at=? WHERE campaign_id=?",
                         (target.value, utc_now_iso(), campaign_id))
            conn.commit()
        return campaign

    @staticmethod
    def bo_mode(effective_sample_count: int) -> str:
        return "rule_based_cold_start" if effective_sample_count < 10 else "hybrid_rule_bo" if effective_sample_count < 30 else "data_driven_bo"

    def create_iteration(self, campaign_id: str, data_support: dict[str, Any],
                         candidates: list[dict[str, Any]]) -> dict[str, Any]:
        campaign = self.campaigns[campaign_id]
        iteration_id = stable_id("iteration", campaign_id, str(campaign.current_iteration))
        now = utc_now_iso()
        record = {"iteration_id": iteration_id, "campaign_id": campaign_id,
                  "iteration_index": campaign.current_iteration,
                  "model_mode": self.bo_mode(int(data_support.get("effective_sample_count", 0))),
                  "model_snapshot_id": None, "data_support": data_support,
                  "proposed_candidates": candidates, "selected_candidates": candidates,
                  "decision": None, "decision_reason": None, "started_at": now,
                  "completed_at": None, "status": "candidate_approval_pending"}
        with get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO optimization_iteration VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                iteration_id, campaign_id, campaign.current_iteration, record["model_mode"], None,
                json.dumps(data_support, ensure_ascii=False), json.dumps(candidates, ensure_ascii=False),
                json.dumps(candidates, ensure_ascii=False), None, None, now, None, record["status"]))
            for index, parameters in enumerate(candidates):
                candidate_id = stable_id("candidate", iteration_id, str(index))
                conn.execute("INSERT OR REPLACE INTO optimization_candidate VALUES (?,?,?,?,?,?,?,?,?)", (
                    candidate_id, iteration_id, json.dumps(parameters, ensure_ascii=False),
                    json.dumps({name: "approved_parameter_tool" for name in parameters}), "{}", "{}",
                    None, "low" if campaign.fidelity_level == "formal_process" else "review_required", "selected"))
            conn.commit()
        return record

    def ingest_observation(self, campaign_id: str, observation: dict[str, Any]) -> dict[str, Any]:
        campaign = self.campaigns[campaign_id]
        required = {"parameters", "units", "equipment_revision", "material_batch", "measurements", "attachments"}
        missing = sorted(key for key in required if observation.get(key) in (None, "", {}, []))
        status = "invalid" if missing else "valid"
        if observation.get("equipment_revision") != campaign.equipment_revision:
            status, missing = "invalid", missing + ["equipment_revision_match"]
        record = {**deepcopy(observation), "campaign_id": campaign_id,
                  "observation_id": stable_id("obs", campaign_id, str(len(self.observations))),
                  "data_quality_status": status, "bo_eligible": status == "valid", "missing": missing}
        self.observations[record["observation_id"]] = record
        with get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO optimization_observation VALUES (?,?,?,?,?,?,?,?,?)", (
                record["observation_id"], observation.get("candidate_id") or record["observation_id"],
                observation.get("execution_id"), json.dumps(observation.get("measurements") or {}, ensure_ascii=False),
                json.dumps(observation.get("quality_metrics") or observation.get("measurements") or {}, ensure_ascii=False),
                json.dumps(observation.get("constraint_results") or {}, ensure_ascii=False), status,
                int(record["bo_eligible"]), utc_now_iso()))
            conn.commit()
        return record

    def update_model(self, campaign_id: str) -> dict[str, Any]:
        approved = [o for o in self.observations.values() if o.get("bo_eligible") and o.get("campaign_id", campaign_id) == campaign_id]
        if not approved:
            raise ValueError("observation validation is required before model update")
        campaign = self.campaigns[campaign_id]
        snapshot = {"model_snapshot_id": stable_id("model", campaign_id, str(campaign.current_iteration)),
                    "campaign_id": campaign_id, "iteration_index": campaign.current_iteration,
                    "model_type": self.bo_mode(len(approved)), "training_sample_ids": [o["observation_id"] for o in approved],
                    "metrics": {}, "created_at": utc_now_iso()}
        self.snapshots[snapshot["model_snapshot_id"]] = snapshot
        with get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO model_snapshot VALUES (?,?,?,?,?,?,?,?,?)", (
                snapshot["model_snapshot_id"], campaign_id, campaign.current_iteration, snapshot["model_type"],
                json.dumps(snapshot["training_sample_ids"]), "{}", "{}", None, snapshot["created_at"]))
            conn.commit()
        return snapshot

    @staticmethod
    def local_trust_region(approved_window: dict[str, list[float]], equipment_bounds: dict[str, list[float]],
                           trust_region: dict[str, list[float]]) -> dict[str, list[float]]:
        result = {}
        for name in approved_window.keys() & equipment_bounds.keys() & trust_region.keys():
            low = max(approved_window[name][0], equipment_bounds[name][0], trust_region[name][0])
            high = min(approved_window[name][1], equipment_bounds[name][1], trust_region[name][1])
            if low <= high:
                result[name] = [low, high]
        return result
