from __future__ import annotations

import hashlib
import re
from typing import Any

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.literature.schemas import LiteratureChunkData, LiteratureSectionData


def estimate_tokens(text: str) -> int:
    ascii_words = len(re.findall(r"[A-Za-z0-9_]+", text))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    return max(1, ascii_words + (cjk + 1) // 2)


def normalized_content(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def build_chunks(
    paper: dict[str, Any],
    sections: list[LiteratureSectionData],
    target_tokens: int = 450,
    min_tokens: int = 120,
    max_tokens: int = 700,
    overlap_tokens: int = 80,
    include_references: bool = False,
) -> list[LiteratureChunkData]:
    chunks: list[LiteratureChunkData] = []
    global_index = 0
    for section in sections:
        if section.section_type == "references" and not include_references:
            continue
        units = _units(section.text, max_tokens)
        current: list[str] = []
        current_tokens = 0
        windows: list[str] = []
        for unit in units:
            unit_tokens = estimate_tokens(unit)
            if current and current_tokens + unit_tokens > target_tokens and current_tokens >= min_tokens:
                windows.append("\n\n".join(current))
                current = _overlap_units(current, overlap_tokens)
                current_tokens = sum(estimate_tokens(item) for item in current)
            current.append(unit)
            current_tokens += unit_tokens
            if current_tokens >= max_tokens:
                windows.append("\n\n".join(current))
                current = _overlap_units(current, overlap_tokens)
                current_tokens = sum(estimate_tokens(item) for item in current)
        if current:
            tail = "\n\n".join(current)
            if windows and estimate_tokens(tail) < min_tokens and estimate_tokens(windows[-1] + "\n\n" + tail) <= max_tokens:
                windows[-1] = windows[-1] + "\n\n" + tail
            else:
                windows.append(tail)
        windows = [part for window in windows for part in _hard_split(window, max_tokens)]
        for content in windows:
            content = normalized_content(content)
            if not content:
                continue
            content_hash = hashlib.sha256(f"{paper['paper_id']}\n{content}".encode("utf-8")).hexdigest()
            metadata = _chunk_metadata(paper, section)
            chunks.append(
                LiteratureChunkData(
                    chunk_id=stable_id("chunk", paper["paper_id"], content_hash),
                    paper_id=paper["paper_id"],
                    section_id=section.section_id,
                    artifact_id=section.artifact_id,
                    chunk_index=global_index,
                    page_start=section.page_start,
                    page_end=section.page_end,
                    section_type=section.section_type,
                    section_title=section.section_title,
                    content=content,
                    content_hash=content_hash,
                    token_estimate=estimate_tokens(content),
                    metadata=metadata,
                    evidence_level=paper.get("evidence_level") or "literature_evidence_candidate",
                    review_status=paper.get("review_status") or "pending_review",
                )
            )
            global_index += 1
    return chunks


def _units(text: str, max_tokens: int) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    output = []
    for paragraph in paragraphs or [text]:
        if estimate_tokens(paragraph) <= max_tokens:
            output.append(paragraph)
            continue
        sentences = [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+", paragraph) if part.strip()]
        for sentence in sentences or [paragraph]:
            output.extend(_hard_split(sentence, max_tokens))
    return output


def _hard_split(text: str, max_tokens: int) -> list[str]:
    if estimate_tokens(text) <= max_tokens:
        return [text]
    atoms = re.findall(r"[A-Za-z0-9_]+\s*|[\u4e00-\u9fff]|[^A-Za-z0-9_\u4e00-\u9fff]+", text)
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for atom in atoms:
        atom_tokens = estimate_tokens(atom)
        if current and current_tokens + atom_tokens > max_tokens:
            chunks.append("".join(current).strip())
            current = [atom]
            current_tokens = atom_tokens
        else:
            current.append(atom)
            current_tokens += atom_tokens
    if current:
        chunks.append("".join(current).strip())
    return [item for item in chunks if item]


def _overlap_units(units: list[str], overlap_tokens: int) -> list[str]:
    output: list[str] = []
    total = 0
    for unit in reversed(units):
        output.insert(0, unit)
        total += estimate_tokens(unit)
        if total >= overlap_tokens:
            break
    return output


def _chunk_metadata(paper: dict[str, Any], section: LiteratureSectionData) -> dict[str, Any]:
    keys = [
        "paper_id", "source_id", "title", "authors", "year", "doi", "scenario_id",
        "material", "material_grade", "component_type", "process_type", "laser_type",
        "evidence_level", "review_status", "usable_for", "not_usable_for",
    ]
    metadata = {key: paper.get(key) for key in keys}
    metadata.update(
        {
            "artifact_id": section.artifact_id,
            "section_type": section.section_type,
            "section_title": section.section_title,
            "page_start": section.page_start,
            "page_end": section.page_end,
        }
    )
    return metadata
