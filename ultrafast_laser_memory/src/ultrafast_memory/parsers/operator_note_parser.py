from __future__ import annotations

import json
from pathlib import Path

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.parsers.base import BaseParser, empty_result


KEYWORDS = {
    "surface_blackening": ["表面发黑", "发黑", "blackening"],
    "edge_chipping": ["崩裂", "崩边", "chipping"],
    "depth_insufficient": ["深度不足", "太浅", "深度比预期浅"],
    "roughness_above_target": ["粗糙度大", "Ra 未达标", "Ra未达标"],
}


def _parse_note(text: str) -> tuple[str | None, str]:
    run_id = None
    note_lines = []
    for line in text.splitlines():
        if line.lower().startswith("run_id:"):
            run_id = line.split(":", 1)[1].strip()
        elif line.lower().startswith("note:"):
            note_lines.append(line.split(":", 1)[1].strip())
        else:
            note_lines.append(line.strip())
    return run_id, "\n".join([line for line in note_lines if line])


class OperatorNoteParser(BaseParser):
    name = "operator_note_parser"
    version = "1.0.0"

    def parse(self, file_path: str) -> dict:
        result = empty_result()
        text = Path(file_path).read_text(encoding="utf-8")
        run_id, note = _parse_note(text)
        tags = [tag for tag, words in KEYWORDS.items() if any(word in note for word in words)]
        result["notes"].append({"run_id": run_id, "note": note, "tags": tags})
        if tags:
            claim = f"该加工记录出现 {', '.join(tags)}，需进一步验证原因。"
            result["experience_candidates"] = [
                {
                    "candidate_id": stable_id("candidate", run_id, tags, note),
                    "task_id": None,
                    "run_id": run_id,
                    "source_artifact_ids": None,
                    "extracted_claim": claim,
                    "evidence_json": json.dumps({"tags": tags, "note": note}, ensure_ascii=False),
                    "confidence": 0.4,
                    "status": "candidate",
                    "extracted_by": "rule_based_note_parser",
                    "extracted_at": utc_now_iso(),
                    "review_comment": None,
                }
            ]
        return result
