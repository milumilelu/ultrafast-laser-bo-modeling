from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from ultrafast_memory.core.hashing import sha256_file


SUPPORTED_DOCUMENT_SUFFIXES = {
    ".txt", ".md", ".markdown", ".json", ".yaml", ".yml", ".csv", ".tsv", ".log",
    ".pdf", ".docx",
}
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_DOCUMENT_CHARACTERS = 60_000


class DocumentReadError(ValueError):
    pass


def load_document_from_message(message: str) -> dict | None:
    """Read an explicitly pasted local file path; ordinary chat text returns None."""
    candidate = _path_candidate(message)
    if candidate is None:
        return None
    path = Path(candidate).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise DocumentReadError(f"文档路径不存在或不可访问：{candidate}") from exc
    if not resolved.is_file():
        raise DocumentReadError(f"该路径不是文件：{resolved}")
    suffix = resolved.suffix.lower()
    if suffix not in SUPPORTED_DOCUMENT_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_DOCUMENT_SUFFIXES))
        raise DocumentReadError(f"不支持的文档格式 {suffix or '(无扩展名)'}；支持：{supported}")
    size = resolved.stat().st_size
    if size > MAX_DOCUMENT_BYTES:
        raise DocumentReadError(f"文档过大（{size} bytes）；当前上限为 {MAX_DOCUMENT_BYTES} bytes")
    text = _extract_text(resolved, suffix).strip()
    if not text:
        raise DocumentReadError("文档未提取到可读文本；扫描版 PDF 需先完成 OCR")
    original_characters = len(text)
    truncated = original_characters > MAX_DOCUMENT_CHARACTERS
    if truncated:
        text = text[:MAX_DOCUMENT_CHARACTERS]
    digest = sha256_file(resolved)
    public = {
        "document_id": f"doc_{digest[:16]}",
        "path": str(resolved),
        "file_name": resolved.name,
        "suffix": suffix,
        "sha256": digest,
        "size_bytes": size,
        "characters": original_characters,
        "truncated": truncated,
    }
    return {
        **public,
        "status": "loaded",
        "text": text,
        "agent_message": _agent_message(public, text),
    }


def public_document_metadata(document: dict) -> dict:
    return {key: value for key, value in document.items() if key not in {"text", "agent_message"}}


def _path_candidate(message: str) -> str | None:
    text = message.strip()
    if not text or "\n" in text or "\r" in text:
        return None
    if text.lower().startswith("/file "):
        text = text[6:].strip()
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()
    if text.lower().startswith("file://"):
        parsed = urlparse(text)
        text = unquote(parsed.path)
        if re.match(r"^/[A-Za-z]:/", text):
            text = text[1:]
    looks_like_path = bool(
        re.match(r"^[A-Za-z]:[\\/]", text)
        or text.startswith("\\\\")
        or text.startswith("./")
        or text.startswith("../")
        or text.lower().startswith("/file ")
    )
    if not looks_like_path and not Path(text).is_file():
        return None
    return text


def _extract_text(path: Path, suffix: str) -> str:
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise DocumentReadError("文本编码无法识别；请转换为 UTF-8 或 GB18030")
    if suffix == ".json":
        try:
            return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            return text
    return text


def _extract_pdf(path: Path) -> str:
    try:
        import fitz  # type: ignore

        document = fitz.open(str(path))
        try:
            pages = [f"[第 {index + 1} 页]\n{page.get_text('text') or ''}" for index, page in enumerate(document)]
        finally:
            document.close()
        return "\n\n".join(pages)
    except DocumentReadError:
        raise
    except Exception as exc:
        raise DocumentReadError(f"PDF 解析失败：{type(exc).__name__}") from exc


def _extract_docx(path: Path) -> str:
    try:
        with ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except (BadZipFile, KeyError, OSError) as exc:
        raise DocumentReadError(f"DOCX 解析失败：{type(exc).__name__}") from exc
    root = ElementTree.fromstring(xml)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        fragments = [node.text or "" for node in paragraph.iter(f"{namespace}t")]
        line = "".join(fragments).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def _agent_message(metadata: dict, text: str) -> str:
    truncation = "\n注意：文档超过上下文上限，以下为前 60000 字。" if metadata["truncated"] else ""
    return (
        "用户通过本地文件路径提交了加工需求文档。请直接阅读文档，"
        "把明确事实写入 context_updates.task，不要要求用户重复文档中已有内容；"
        "若仍有关键歧义，一次合并提出 3–5 个高价值问题。\n"
        f"文件名：{metadata['file_name']}\n"
        f"文件路径：{metadata['path']}\n"
        f"SHA256：{metadata['sha256']}"
        f"{truncation}\n\n--- 文档正文开始 ---\n{text}\n--- 文档正文结束 ---"
    )
