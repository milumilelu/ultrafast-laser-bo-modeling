from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import json


@pytest.fixture()
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture()
def isolated_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ULTRAFAST_MEMORY_ROOT", str(tmp_path))
    (tmp_path / "configs").mkdir()
    (tmp_path / "data").mkdir()
    return tmp_path


@pytest.fixture()
def isolated_examples(tmp_path: Path, project_root: Path) -> Path:
    dest = tmp_path / "examples"
    shutil.copytree(project_root / "examples", dest)
    return dest


@pytest.fixture()
def mixed_literature_root(tmp_path: Path) -> Path:
    fitz = pytest.importorskip("fitz")
    root = tmp_path / "literature"
    deliverables = root / "deliverables" / "tgv"
    pdf_dir = root / "raw"
    deliverables.mkdir(parents=True)
    pdf_dir.mkdir(parents=True)
    pdf_path = pdf_dir / "tgv_paper.pdf"
    doc = fitz.open()
    pages = [
        ("TGV Laser Drilling Study\nAbstract\n", "This study investigates femtosecond laser drilling of through glass vias with controlled taper and cracks. "),
        ("Results\n", "The TGV drilling results show reduced taper and microcrack formation for the optimized scanning strategy. "),
        ("Conclusion\n", "The traceable experiments support glass wafer TGV quality evaluation but do not establish BO parameter bounds. "),
    ]
    for heading, body in pages:
        page = doc.new_page()
        page.insert_textbox((50, 50, 550, 780), heading + body * 8, fontsize=10)
    doc.set_metadata({"title": "TGV Laser Drilling Study", "author": "Test Author", "subject": "10.1234/tgv.test"})
    doc.save(pdf_path)
    doc.close()
    card = {
        "paper_id": "paper_tgv_test",
        "source_id": "source_tgv_test",
        "title": "TGV Laser Drilling Study",
        "authors": "Test Author",
        "year": "2025",
        "doi": "https://doi.org/10.1234/TGV.TEST",
        "scenario_id": "scenario_05_tgv_drilling",
        "material": "glass_wafer",
        "component_type": "TGV_array",
        "process_type": "TGV_drilling",
        "laser_type": "femtosecond",
    }
    (deliverables / "literature_cards.jsonl").write_text(json.dumps(card) + "\n", encoding="utf-8")
    (deliverables / "paper_table.csv").write_text("paper_id,title\npaper_tgv_test,TGV Laser Drilling Study\n", encoding="utf-8")
    candidate = {
        "candidate_id": "candidate_tgv_test",
        "paper_id": "paper_tgv_test",
        "source_id": "source_tgv_test",
        "claim": "TGV taper and crack behavior depends on the drilling strategy.",
        "material": "glass_wafer",
        "process_type": "TGV_drilling",
    }
    (deliverables / "knowledge_candidates.jsonl").write_text(json.dumps(candidate) + "\n", encoding="utf-8")
    return root
