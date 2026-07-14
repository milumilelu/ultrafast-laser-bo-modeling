from __future__ import annotations

import json
from typing import Any

from ultrafast_domain.trial.campaign import TrialCampaign, TrialIteration, TrialObservation
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


class TrialCampaignRepository:
    def save_campaign(self, campaign: TrialCampaign) -> None:
        init_database()
        now = utc_now_iso()
        with get_connection() as connection:
            connection.execute(
                """INSERT INTO trial_campaign_v2 VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(campaign_id) DO UPDATE SET
                   campaign_json=excluded.campaign_json,
                   business_state=excluded.business_state,
                   substatus=excluded.substatus,
                   updated_at=excluded.updated_at""",
                (
                    campaign.campaign_id,
                    campaign.task_id,
                    campaign.workflow_id,
                    json.dumps(campaign.to_dict(), ensure_ascii=False, sort_keys=True),
                    campaign.business_state,
                    campaign.substatus,
                    now,
                    now,
                ),
            )
            connection.commit()

    def get_campaign(self, campaign_id: str) -> TrialCampaign:
        init_database()
        with get_connection() as connection:
            row = connection.execute(
                "SELECT campaign_json FROM trial_campaign_v2 WHERE campaign_id=?",
                (campaign_id,),
            ).fetchone()
        if row is None:
            raise KeyError(campaign_id)
        return TrialCampaign(**json.loads(row[0]))

    def save_iteration(self, iteration: TrialIteration) -> None:
        init_database()
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO trial_iteration_v2 VALUES (?,?,?,?,?,?,?,?)",
                (
                    iteration.iteration_id,
                    iteration.campaign_id,
                    iteration.iteration_number,
                    iteration.recommendation_id,
                    iteration.parent_recommendation_id,
                    iteration.observation_id,
                    iteration.decision,
                    iteration.created_at or utc_now_iso(),
                ),
            )
            connection.commit()

    def get_iteration(self, iteration_id: str) -> dict[str, Any]:
        init_database()
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM trial_iteration_v2 WHERE iteration_id=?", (iteration_id,)
            ).fetchone()
        if row is None:
            raise KeyError(iteration_id)
        return dict(row)

    def get_iteration_for_recommendation(self, recommendation_id: str) -> dict[str, Any]:
        init_database()
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM trial_iteration_v2 WHERE recommendation_id=?",
                (recommendation_id,),
            ).fetchone()
        if row is None:
            raise KeyError(recommendation_id)
        return dict(row)

    def save_observation(
        self,
        observation: TrialObservation,
        *,
        candidate_id: str,
    ) -> None:
        init_database()
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO trial_observation_v2 VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    observation.observation_id,
                    observation.campaign_id,
                    observation.iteration_id,
                    observation.recommendation_id,
                    json.dumps(observation.to_dict(), ensure_ascii=False, sort_keys=True),
                    json.dumps(observation.eligibility_report, ensure_ascii=False, sort_keys=True),
                    candidate_id,
                    observation.dataset_version,
                    observation.created_at or utc_now_iso(),
                ),
            )
            connection.execute(
                "UPDATE trial_iteration_v2 SET observation_id=? WHERE iteration_id=?",
                (observation.observation_id, observation.iteration_id),
            )
            connection.commit()

    def get_observation(self, observation_id: str) -> dict[str, Any]:
        init_database()
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM trial_observation_v2 WHERE observation_id=?",
                (observation_id,),
            ).fetchone()
        if row is None:
            raise KeyError(observation_id)
        value = dict(row)
        value["observation"] = json.loads(value.pop("observation_json"))
        value["eligibility"] = json.loads(value.pop("eligibility_json"))
        return value

    def record_decision(
        self,
        iteration_id: str,
        decision: str,
        dataset_version: str | None = None,
    ) -> None:
        with get_connection() as connection:
            connection.execute(
                "UPDATE trial_iteration_v2 SET decision=? WHERE iteration_id=?",
                (decision, iteration_id),
            )
            if dataset_version:
                connection.execute(
                    "UPDATE trial_observation_v2 SET dataset_version=? WHERE iteration_id=?",
                    (dataset_version, iteration_id),
                )
            connection.commit()

    def list_iterations(self, campaign_id: str) -> list[dict[str, Any]]:
        init_database()
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM trial_iteration_v2 WHERE campaign_id=? ORDER BY iteration_number",
                (campaign_id,),
            ).fetchall()
        return [dict(row) for row in rows]
