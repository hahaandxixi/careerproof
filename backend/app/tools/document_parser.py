from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz
from docx import Document
from docx.oxml.ns import qn

from app.core.exceptions import AppError


@dataclass(frozen=True, slots=True)
class DocumentSection:
    section_type: str
    content: str
    page_number: int | None


def _docx_text(root) -> str:
    """Read visible OOXML text, including textboxes and nested tables, once."""
    chunks: list[str] = []
    mc = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"

    def visit(node):
        if node.tag in {qn("w:del"), qn("w:moveFrom")}:
            return
        if node.tag == mc + "AlternateContent":
            # DrawingML and VML can hold two copies of the same textbox.
            branches = list(node)
            branch = next((n for n in branches if n.tag == mc + "Choice"), None)
            if branch is None:
                branch = next((n for n in branches if n.tag == mc + "Fallback"), None)
            if branch is not None:
                visit(branch)
            return
        if node.tag == qn("w:t"):
            chunks.append(node.text or "")
            return
        if node.tag in {qn("w:br"), qn("w:cr")}:
            chunks.append("\n")
        elif node.tag == qn("w:tab"):
            chunks.append("\t")
        for child in node:
            visit(child)
        if node.tag in {qn("w:p"), qn("w:tr")}:
            chunks.append("\n")

    visit(root)
    return "\n".join(line.strip() for line in "".join(chunks).splitlines() if line.strip())


def parse_document(path: Path, mime_type: str) -> list[DocumentSection]:
    if mime_type == "application/pdf" or path.suffix.lower() == ".pdf":
        with fitz.open(path) as document:
            sections = []
            for index, page in enumerate(document):
                text = page.get_text("text").strip()
                if text:
                    sections.append(DocumentSection("page", text, index + 1))
            if not sections:
                raise AppError(
                    "PDF未提取到文字，可能为空白或扫描件；请先进行OCR识别后重新上传", code=4024
                )
            return sections
    if (
        mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or path.suffix.lower() == ".docx"
    ):
        document = Document(path)
        text = _docx_text(document.element.body)
        if not text:
            raise AppError("文档没有可分析文字，请检查内容或先进行OCR识别", code=4024)
        return [DocumentSection("document", text, None)]
    if mime_type.startswith("text/") or path.suffix.lower() in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8-sig").strip()
        if not text:
            raise AppError("文档没有可分析文字，请检查内容", code=4024)
        return [DocumentSection("document", text, None)]
    raise AppError("仅支持PDF、DOCX或TXT简历", code=4020, status_code=415)


def language_for(path: Path) -> str | None:
    return {
        ".py": "Python",
        ".java": "Java",
        ".go": "Go",
        ".js": "JavaScript",
        ".jsx": "JavaScript React",
        ".ts": "TypeScript",
        ".tsx": "TypeScript React",
        ".vue": "Vue",
        ".sql": "SQL",
        ".sh": "Shell",
    }.get(path.suffix.lower())
