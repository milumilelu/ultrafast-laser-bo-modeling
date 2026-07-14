from __future__ import annotations

import json

from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.rag.index_service import create_index, index_pending_chunks
from ultrafast_shared.db.unit_of_work import UnitOfWork


class DemoFixtureRepository:
    PAPER_ID = "demo-paper-tgv"
    CHUNK_ID = "demo-chunk-tgv"

    def ensure_tgv_evidence(self) -> dict:
        init_database()
        now = utc_now_iso()
        content = (
            "Demo fixture evidence: femtosecond laser TGV drilling quality depends on wafer thickness, "
            "hole diameter, taper, crack control, debris removal, and array pitch. A parameter range "
            "must be reviewed before it is used for recommendation or BO search bounds."
        )
        with UnitOfWork() as uow:
            assert uow.connection is not None
            uow.connection.execute(
                """
                INSERT OR IGNORE INTO literature_paper (
                    paper_id, canonical_title, normalized_title, authors, year, source,
                    scenario_id, material, material_grade, component_type, process_type,
                    laser_type, evidence_level, review_status, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    self.PAPER_ID,
                    "Offline TGV Demo Fixture",
                    "offline tgv demo fixture",
                    "Deterministic repository fixture",
                    "2026",
                    "demo_fixture",
                    "scenario_05_tgv_drilling",
                    "glass_wafer",
                    "TGV",
                    "TGV_array",
                    "TGV_drilling",
                    "femtosecond",
                    "demo_fixture",
                    "pending_review",
                    now,
                    now,
                ),
            )
            uow.connection.execute(
                """
                INSERT OR IGNORE INTO literature_chunk (
                    chunk_id, paper_id, chunk_index, page_start, page_end, section_type,
                    section_title, content, content_hash, token_estimate, metadata_json,
                    evidence_level, review_status, active, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    self.CHUNK_ID,
                    self.PAPER_ID,
                    0,
                    1,
                    1,
                    "results",
                    "Demo evidence",
                    content,
                    "demo-tgv-content-v1",
                    55,
                    json.dumps({"demo_fixture": True}, ensure_ascii=False),
                    "demo_fixture",
                    "pending_review",
                    1,
                    now,
                    now,
                ),
            )
            uow.commit()
        index = create_index(
            {
                "index_name": "literature_default",
                "embedding_provider": "mock",
                "embedding_model": "deterministic-mock-v1",
                "embedding_dimension": 64,
            }
        )
        indexed = index_pending_chunks(index["index_id"])
        return {
            "paper_id": self.PAPER_ID,
            "chunk_id": self.CHUNK_ID,
            "index_id": index["index_id"],
            "indexed_count": indexed["indexed_count"],
            "external_network": False,
        }
