from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile

import fitz
from docx import Document
from docx.oxml.ns import qn

from app.core.config import settings
from app.core.exceptions import AppError
from app.tools.ocr import marked_ocr_text, recognize_image

# Failures that belong to the *input* rather than to our code, captured only around the
# library call that opens the file. Deliberately narrow: a ValueError or KeyError raised
# later by our own reading/OCR code is a defect in this program and must keep
# propagating, and a process-level failure stays with the isolated worker in
# app.services.task_runner. Password protection is detected explicitly, not by
# exception type.
_PDF_OPEN_ERRORS = (fitz.FileDataError, fitz.FileNotFoundError)
_DOCX_OPEN_ERRORS = (BadZipFile, KeyError, ValueError)


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
        # Only opening the file is classified as an input problem. Everything inside the
        # document (page reads, OCR) runs outside this capture so an internal ValueError
        # is never reported to the user as a corrupt upload.
        try:
            document = fitz.open(path)
        except _PDF_OPEN_ERRORS as error:
            raise AppError(
                "PDF文件无法解析，可能已损坏，请重新导出后上传", code=4024
            ) from error
        with document:
            if document.needs_pass:
                raise AppError("PDF文件已加密，需要密码才能打开，请移除密码后重新上传", code=4024)
            sections = []
            ocr_pages = 0
            for index, page in enumerate(document):
                text = page.get_text("text").strip()
                if text:
                    sections.append(DocumentSection("page", text, index + 1))
                elif settings.ocr_enabled and ocr_pages < settings.ocr_max_pages:
                    matrix = fitz.Matrix(2, 2)
                    bounds = (page.rect * matrix).irect
                    if (
                        bounds.width <= 0
                        or bounds.height <= 0
                        or bounds.width * bounds.height > settings.ocr_max_image_pixels
                    ):
                        raise AppError("PDF页面像素过大，无法安全进行OCR识别", code=4026)
                    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                    if pixmap.width * pixmap.height > settings.ocr_max_image_pixels:
                        raise AppError("PDF页面像素过大，无法安全进行OCR识别", code=4026)
                    result = recognize_image(pixmap.tobytes("png"))
                    ocr_pages += 1
                    if result.text:
                        sections.append(
                            DocumentSection("ocr_page", marked_ocr_text(result), index + 1)
                        )
            if not sections:
                raise AppError(
                    "PDF未提取或识别到可分析文字，请上传清晰扫描件或文字版文档", code=4024
                )
            return sections
    if (
        mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or path.suffix.lower() == ".docx"
    ):
        # Same split as the PDF branch: only the package open is an input problem, while
        # _docx_text (our own traversal) keeps its exceptions.
        try:
            document = Document(path)
            body = document.element.body
        except _DOCX_OPEN_ERRORS as error:
            raise AppError("文档无法解析，可能已损坏，请重新导出后上传", code=4024) from error
        text = _docx_text(body)
        if not text:
            raise AppError("文档没有可分析文字，请检查内容或先进行OCR识别", code=4024)
        return [DocumentSection("document", text, None)]
    if mime_type.startswith("text/") or path.suffix.lower() in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8-sig").strip()
        if not text:
            raise AppError("文档没有可分析文字，请检查内容", code=4024)
        return [DocumentSection("document", text, None)]
    if mime_type.startswith("image/") or path.suffix.lower() in {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
    }:
        result = recognize_image(path.read_bytes())
        if not result.text:
            raise AppError("图片未识别到可分析文字，请上传清晰原图", code=4024)
        return [DocumentSection("ocr_image", marked_ocr_text(result), 1)]
    raise AppError("仅支持PDF、DOCX、TXT或常见图片文件", code=4020, status_code=415)


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
