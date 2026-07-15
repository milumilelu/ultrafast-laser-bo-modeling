from __future__ import annotations

import json
from zipfile import ZipFile

from ultrafast_memory.agent_runtime.document_input import load_document_from_message
from ultrafast_memory.chat.schemas import ChatRequest
from ultrafast_memory.chat.service import handle_chat


class DocumentPlannerLLM:
    provider = "test"
    model = "document-planner"

    def __init__(self):
        self.messages = None

    def chat(self, messages, **kwargs):
        self.messages = messages
        return {"content": json.dumps({
            "action": "final_answer",
            "decision_summary": "已直接读取需求文档并提取明确加工事实。",
            "message": "已从文档提取材料、厚度和通孔几何。",
            "context_updates": {"task": {
                "material": {"name": "diamond", "description": "金刚石"},
                "process_intent": "hole_drilling",
                "geometry": {"feature_type": "through_hole", "workpiece_thickness_mm": 4,
                             "dimensions": {"diameter_mm": 2}, "through": True},
            }},
        }, ensure_ascii=False)}


def test_pasted_text_document_path_is_read_by_main_llm(isolated_root, tmp_path, monkeypatch):
    path = tmp_path / "加工需求.txt"
    path.write_text("材料：金刚石\n工件厚度：4 mm\n加工直径2 mm通孔\n要求贯穿。", encoding="utf-8")
    llm = DocumentPlannerLLM()
    monkeypatch.setattr("ultrafast_memory.chat.service.create_llm_client", lambda config: llm)

    response = handle_chat(ChatRequest(message=f'"{path}"'))

    assert llm.messages is not None
    planner_input = llm.messages[-1]["content"]
    assert "加工直径2 mm通孔" in planner_input
    assert "不要要求用户重复文档中已有内容" in planner_input
    task = response.workflow_state["task_spec"]
    assert task["material"]["name"] == "diamond"
    assert task["geometry"]["feature_type"] == "through_hole"
    documents = response.workflow_state["working_context"]["documents"]
    assert documents[0]["path"] == str(path.resolve())
    assert documents[0]["sha256"]
    assert any(event["event_type"] == "document_loaded" for event in response.execution_trace)


def test_docx_requirement_text_is_extracted(tmp_path):
    path = tmp_path / "requirement.docx"
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:r><w:t>切割2mm厚碳纤维复合板</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>边缘不得明显分层</w:t></w:r></w:p></w:body></w:document>'
    )
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)

    document = load_document_from_message(str(path))

    assert document is not None
    assert "切割2mm厚碳纤维复合板" in document["text"]
    assert "边缘不得明显分层" in document["text"]
    assert document["suffix"] == ".docx"


def test_powershell_tui_resolves_pasted_document_paths(project_root):
    source = (project_root / "scripts/powershell/AgentTui.psm1").read_text(encoding="utf-8")
    assert "function Resolve-AgentDocumentPath" in source
    assert "Test-Path -LiteralPath $candidate -PathType Leaf" in source
    assert "可直接粘贴加工需求文档路径" in source
    assert "Resolve-AgentDocumentPath -InputText $inputText" in source
