from io import BytesIO
from types import SimpleNamespace

import fitz
import pytest
from PIL import Image

from app.core.config import settings
from app.core.exceptions import AppError
from app.tools.document_parser import parse_document
from app.tools.ocr import OCRResult, recognize_image


def png_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (320, 120), "white").save(stream, format="PNG")
    return stream.getvalue()


def test_image_document_uses_ocr_and_marks_unverified_text(tmp_path, monkeypatch):
    image = tmp_path / "resume.png"
    image.write_bytes(png_bytes())
    monkeypatch.setattr(
        "app.tools.document_parser.recognize_image",
        lambda _: OCRResult("Python 后端开发\nFastAPI 项目", 0.91, 2),
    )

    section = parse_document(image, "image/png")[0]

    assert section.section_type == "ocr_image"
    assert section.page_number == 1
    assert "平均置信度 91%" in section.content
    assert "请对照原图复核" in section.content
    assert "FastAPI 项目" in section.content


def test_scanned_pdf_ocr_preserves_page_number(tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    with fitz.open() as document:
        document.new_page()
        document.save(pdf)
    monkeypatch.setattr(
        "app.tools.document_parser.recognize_image",
        lambda _: OCRResult("数据库备份恢复记录", 0.88, 1),
    )

    section = parse_document(pdf, "application/pdf")[0]

    assert section.section_type == "ocr_page"
    assert section.page_number == 1
    assert "数据库备份恢复记录" in section.content


def test_native_text_pdf_does_not_invoke_ocr(tmp_path, monkeypatch):
    pdf = tmp_path / "native.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "Native FastAPI resume")
        document.save(pdf)

    def forbidden(_):
        pytest.fail("OCR should only run for PDF pages without extractable text")

    monkeypatch.setattr("app.tools.document_parser.recognize_image", forbidden)
    section = parse_document(pdf, "application/pdf")[0]
    assert section.section_type == "page"
    assert "Native FastAPI resume" in section.content


def test_ocr_filters_low_confidence_lines(monkeypatch):
    class FakeEngine:
        def __call__(self, _image, **_kwargs):
            return SimpleNamespace(
                txts=("可信文字", "噪声"),
                scores=(0.93, 0.2),
            )

    monkeypatch.setattr("app.tools.ocr._engine", lambda: FakeEngine())
    monkeypatch.setattr(settings, "ocr_min_confidence", 0.5)
    result = recognize_image(png_bytes())
    assert result.text == "可信文字"
    assert result.average_confidence == pytest.approx(0.93)
    assert result.line_count == 1


def test_image_without_recognized_text_is_rejected(tmp_path, monkeypatch):
    image = tmp_path / "blank.jpg"
    image.write_bytes(png_bytes())
    monkeypatch.setattr(
        "app.tools.document_parser.recognize_image",
        lambda _: OCRResult("", None, 0),
    )
    with pytest.raises(AppError, match="未识别到"):
        parse_document(image, "image/jpeg")
