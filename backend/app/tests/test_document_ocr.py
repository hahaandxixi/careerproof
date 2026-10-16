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


@pytest.mark.parametrize(
    "width,height,rotation", [(595, 842, 0), (600, 600, 90), (750.5, 400.5, 270)]
)
def test_pdf_pixel_limit_rejects_before_bitmap_allocation(
    tmp_path, monkeypatch, width, height, rotation
):
    pdf = tmp_path / "over-budget.pdf"
    with fitz.open() as document:
        page = document.new_page(width=width, height=height)
        page.set_rotation(rotation)
        document.save(pdf)
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(settings, "ocr_max_image_pixels", 1_000_000)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Over-budget PDF must be rejected before allocating a bitmap")

    monkeypatch.setattr(fitz.Page, "get_pixmap", forbidden)
    with pytest.raises(AppError, match="PDF页面像素过大") as error:
        parse_document(pdf, "application/pdf")
    assert error.value.code == 4026


@pytest.mark.parametrize("rotation", [0, 90])
def test_pdf_exact_pixel_budget_allows_real_rendered_png(tmp_path, monkeypatch, rotation):
    pdf = tmp_path / "within-budget.pdf"
    with fitz.open() as document:
        page = document.new_page(width=510.25, height=500.25)
        page.set_rotation(rotation)
        bounds = (page.rect * fitz.Matrix(2, 2)).irect
        expected_size = (bounds.width, bounds.height)
        document.save(pdf)
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(settings, "ocr_max_image_pixels", expected_size[0] * expected_size[1])
    seen = []

    def synthetic_recognizer(png):
        with Image.open(BytesIO(png)) as image:
            seen.append(image.size)
        return OCRResult("合成识别文字", 0.9, 1)

    monkeypatch.setattr("app.tools.document_parser.recognize_image", synthetic_recognizer)
    sections = parse_document(pdf, "application/pdf")
    assert seen == [expected_size]
    assert sections[0].page_number == 1 and sections[0].section_type == "ocr_page"


async def test_pdf_pixel_limit_crosses_real_isolated_worker(tmp_path, monkeypatch):
    from app.services.task_runner import run_isolated

    pdf = tmp_path / "worker-over-budget.pdf"
    with fitz.open() as document:
        document.new_page(width=600, height=600)
        document.save(pdf)
    monkeypatch.setenv("OCR_ENABLED", "true")
    monkeypatch.setenv("OCR_MAX_IMAGE_PIXELS", "1000000")
    with pytest.raises(AppError, match="PDF页面像素过大") as error:
        await run_isolated(parse_document, pdf, "application/pdf", timeout_seconds=15)
    assert error.value.code == 4026
