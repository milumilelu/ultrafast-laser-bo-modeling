from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from ultrafast_memory.core.ids import stable_id
from ultrafast_memory.core.time_utils import utc_now_iso
from ultrafast_memory.literature.canonicalizer import DOI_RE, normalize_doi
from ultrafast_memory.literature.inventory import sha256_path
from ultrafast_memory.literature.schemas import PageText, ParsedPdf


PARSER_NAME = "pymupdf_literature_parser"
PARSER_VERSION = "1.0.0"
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def parse_pdf(
    pdf_path: str | Path,
    archive_dir: str | Path,
    archive_original: bool = True,
) -> ParsedPdf:
    path = Path(pdf_path).expanduser().resolve()
    sha = sha256_path(path)
    artifact_id = stable_id("lart", sha, "raw_pdf")
    archive_root = Path(archive_dir).expanduser().resolve()
    archived = archive_root / f"{sha[:16]}_{path.name}"
    if archive_original:
        archive_root.mkdir(parents=True, exist_ok=True)
        if not archived.exists():
            shutil.copy2(path, archived)
    else:
        archived = path
    artifact = {
        "artifact_id": artifact_id,
        "original_path": str(path),
        "archived_path": str(archived),
        "asset_type": "raw_pdf",
        "sha256": sha,
        "file_size_bytes": path.stat().st_size,
        "parent_root": str(path.parent),
        "parse_status": "parsed",
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "error_message": "",
        "discovered_at": utc_now_iso(),
        "imported_at": utc_now_iso(),
    }
    try:
        import fitz  # type: ignore

        document = fitz.open(str(path))
        try:
            raw_metadata = document.metadata or {}
            pages = [PageText(page_number=index + 1, text=document[index].get_text("text") or "") for index in range(len(document))]
        finally:
            document.close()
    except Exception as exc:
        artifact["parse_status"] = "failed"
        artifact["error_message"] = str(exc)
        return ParsedPdf(artifact=artifact, metadata=_filename_metadata(path), parse_status="failed", error_message=str(exc))
    total_chars = sum(len(re.sub(r"\s+", "", page.text)) for page in pages)
    average = total_chars / len(pages) if pages else 0.0
    status = "needs_ocr" if pages and average < 50 else "parsed"
    artifact["parse_status"] = status
    artifact["error_message"] = "average extracted characters per page below 50" if status == "needs_ocr" else ""
    joined = "\n".join(page.text for page in pages[:10])
    metadata = extract_pdf_metadata(path, raw_metadata, joined)
    return ParsedPdf(
        artifact=artifact,
        metadata=metadata,
        pages=pages,
        page_count=len(pages),
        average_chars_per_page=average,
        parse_status=status,
        error_message=artifact["error_message"],
    )


def extract_pdf_metadata(path: Path, metadata: dict[str, Any], text: str) -> dict[str, Any]:
    title = str(metadata.get("title") or "").strip()
    if len(title) < 8 or title.lower().startswith(("untitled", "microsoft word", "page ")):
        title = _title_from_text(text) or path.stem
    authors = str(metadata.get("author") or "").strip()
    doi_candidates = []
    for value in metadata.values():
        doi_candidates.extend(DOI_RE.findall(str(value or "")))
    doi_candidates.extend(DOI_RE.findall(text[:30000]))
    year = ""
    for value in list(metadata.values()) + [text[:5000]]:
        match = YEAR_RE.search(str(value or ""))
        if match:
            year = match.group(0)
            break
    sample = text[:80000]
    tags = infer_tags(sample)
    return {
        "title": " ".join(title.split())[:500],
        "authors": " ".join(authors.split())[:500],
        "year": year,
        "doi": normalize_doi(doi_candidates[0]) if doi_candidates else "",
        "source": "",
        **tags,
    }


def infer_tags(text: str) -> dict[str, str]:
    checks = [
        ("scenario_01_film_cooling_hole_repair", r"film cooling|气膜孔|thermal barrier coating"),
        ("scenario_02_surface_microstructure_bonding", r"adhesive bond|lap shear|cfrp|胶接|粘接"),
        ("scenario_03_xray_optics", r"x[- ]?ray|compound refractive lens|\bcrl\b|复合折射透镜"),
        ("scenario_04_3c_cover_glass", r"cover glass|玻璃盖板|smartphone"),
        ("scenario_05_tgv_drilling", r"through glass via|\btgv\b|玻璃通孔"),
    ]
    scenario = next((label for label, pattern in checks if re.search(pattern, text, re.I)), "common_bo_knowledge_base")
    materials = [
        ("CFRP_T300", r"\bT300\b"),
        ("CFRP", r"\bCFRP\b|carbon fib(?:er|re) reinforced"),
        ("TBC_YSZ", r"\bTBC\b|thermal barrier coating|YSZ"),
        ("nickel_superalloy", r"nickel[- ]based superalloy|Inconel|CMSX|镍基高温合金"),
        ("diamond", r"\bdiamond\b|金刚石"),
        ("SiC", r"\bSiC\b|silicon carbide|碳化硅"),
        ("fused_silica", r"fused silica|熔融石英"),
        ("glass_wafer", r"glass wafer|玻璃晶圆|through glass via"),
        ("glass_ceramic", r"glass ceramic|微晶玻璃"),
        ("SiO2", r"\bSiO2\b"),
    ]
    material = next((label for label, pattern in materials if re.search(pattern, text, re.I)), "")
    processes = [
        ("film_cooling_hole_repair", r"film cooling|气膜孔"),
        ("adhesive_bonding_pretreatment", r"adhesive bond|lap shear|胶接|粘接"),
        ("xray_crl_micromachining", r"compound refractive lens|\bCRL\b|复合折射透镜"),
        ("glass_cover_cutting", r"cover glass|玻璃盖板"),
        ("TGV_drilling", r"through glass via|\bTGV\b|玻璃通孔"),
        ("surface_microtexturing", r"surface textur|表面织构|表面微结构"),
        ("femtosecond_laser_drilling", r"femtosecond.{0,40}drill|飞秒.{0,20}(钻孔|打孔)"),
    ]
    process = next((label for label, pattern in processes if re.search(pattern, text, re.I)), "")
    component = {
        "scenario_01_film_cooling_hole_repair": "film_cooling_hole",
        "scenario_03_xray_optics": "X_ray_CRL",
        "scenario_04_3c_cover_glass": "cover_glass",
        "scenario_05_tgv_drilling": "TGV_array",
    }.get(scenario, "")
    laser_type = next((label for label, pattern in (("femtosecond", r"femtosecond|飞秒"), ("picosecond", r"picosecond|皮秒"), ("ultrafast", r"ultrafast|超快")) if re.search(pattern, text, re.I)), "")
    return {
        "scenario_id": scenario,
        "material": material,
        "material_grade": "T300" if material == "CFRP_T300" else "",
        "component_type": component,
        "process_type": process,
        "laser_type": laser_type,
    }


def _title_from_text(text: str) -> str:
    bad = ("abstract", "introduction", "doi", "www.", "http", "journal", "contents")
    for raw in text.splitlines()[:100]:
        line = " ".join(raw.split())
        if 12 <= len(line) <= 300 and not line.lower().startswith(bad) and sum(ch.isalpha() for ch in line) >= 8:
            return line
    return ""


def _filename_metadata(path: Path) -> dict[str, Any]:
    return {"title": path.stem, "authors": "", "year": "", "doi": "", "source": "", **infer_tags(path.stem)}
