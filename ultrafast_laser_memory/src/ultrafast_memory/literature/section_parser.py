from __future__ import annotations

import hashlib
import re

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.literature.schemas import LiteratureSectionData, PageText


PARSER_VERSION = "section-parser-v1"
HEADINGS = [
    ("abstract", r"^(abstract|摘要)$"),
    ("keywords", r"^(keywords?|关键词)\s*[:：]?$"),
    ("introduction", r"^(?:\d+[.\s]*)?(introduction|引言)$"),
    ("methods", r"^(?:\d+[.\s]*)?(materials? and methods?|methods?|experimental|experiment|实验|材料与方法)$"),
    ("results", r"^(?:\d+[.\s]*)?(results?|结果)$"),
    ("discussion", r"^(?:\d+[.\s]*)?(discussion|讨论)$"),
    ("conclusion", r"^(?:\d+[.\s]*)?(conclusions?|结论)$"),
    ("references", r"^(references|bibliography|参考文献)$"),
]


def section_type_for_heading(line: str) -> str | None:
    normalized = " ".join(line.strip().split())
    for section_type, pattern in HEADINGS:
        if re.match(pattern, normalized, re.I):
            return section_type
    return None


def parse_sections(paper_id: str, artifact_id: str, pages: list[PageText]) -> list[LiteratureSectionData]:
    buffers: list[dict] = []
    current = {"type": "unknown", "title": "", "start": 1, "end": 1, "parts": []}
    for page in pages:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", page.text) if part.strip()]
        if not paragraphs and page.text.strip():
            paragraphs = [page.text.strip()]
        for paragraph in paragraphs:
            first_line = paragraph.splitlines()[0].strip()
            heading_type = section_type_for_heading(first_line)
            if heading_type:
                if current["parts"]:
                    buffers.append(current)
                remainder = "\n".join(paragraph.splitlines()[1:]).strip()
                current = {
                    "type": heading_type,
                    "title": first_line,
                    "start": page.page_number,
                    "end": page.page_number,
                    "parts": [remainder] if remainder else [],
                }
            else:
                current["parts"].append(paragraph)
                current["end"] = page.page_number
    if current["parts"]:
        buffers.append(current)
    sections = []
    for index, item in enumerate(buffers):
        text = "\n\n".join(item["parts"]).strip()
        if not text:
            continue
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        sections.append(
            LiteratureSectionData(
                section_id=stable_id("section", paper_id, artifact_id, index, text_hash),
                paper_id=paper_id,
                artifact_id=artifact_id,
                section_type=item["type"],
                section_title=item["title"],
                page_start=item["start"],
                page_end=item["end"],
                text=text,
                text_hash=text_hash,
                parser_version=PARSER_VERSION,
            )
        )
    return sections
